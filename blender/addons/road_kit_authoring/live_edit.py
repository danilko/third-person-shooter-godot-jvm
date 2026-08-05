"""Live-editing: drag an arm_*/segend_*/segbend_* marker Empty, or edit a spine Curve's own
control points, and the owning intersection/segment/transition piece's VISUAL geometry stays live.

Data vs visual split (see `lib/intersection_kit.py`'s module docstring): arm layout, lane
centerlines, ports, and JSON export are pure Python -- untouched by this handler, still the single
source of truth `.lanekit.json`/`WorldBaker` consume, so there is no dual-implementation risk.
VISUAL mesh generation (curb walls, pavement) IS Geometry Nodes now (`GN_JunctionPad`/`GN_CurbLoop`
via `kit_common.junction_pad`/`curb_loop`, `GN_RoadProfile` via `kit_common.road_spine`) -- for a
segment/transition's PAVEMENT specifically, this handler does nothing at all: the spine Curve
object carries a live `GN_RoadProfile` modifier directly, so Blender's own dependency graph keeps
the pavement correct automatically the instant a control point moves or is added, with zero Python
involvement. This handler's remaining job is: (1) for an intersection, re-derive its boundary
polygon from the current `arm_*` Empty positions and rebuild the pad/curb objects
(`ops_intersection.rebuild_intersection_in_place` -- still a delete+recreate of those two small
GN-modifier objects each drag, which is fine at their vertex counts and was never the fragile part;
the FIX here was catching a near-degenerate corner instead of raising mid-rebuild, see
`intersection_kit.build_curb_corners`); (2) for a segment/transition, re-sample its spine's CURRENT
points and regenerate ONLY the separately-offset curb walls + `lanecl_*` centerline data curves
(`ops_segment.rebuild_segment_gn_in_place` / `rebuild_lane_transition_in_place` -- the spine object
itself is never touched, its own edits already ARE the live state).

`RKA_SceneSettings.live_edit_enabled` (panel checkbox) is the escape hatch, and any single piece
can opt out via its own `rka_live_edit` custom property.

BUG FIXED HERE (persistence): `bpy.app.handlers.depsgraph_update_post.append(...)` handlers are
NOT persistent by default -- Blender clears every non-persistent handler on ANY new file load
(File > New, File > Open, `read_homefile`), including a freshly re-opened .blend the addon was
already "enabled" in. Without `@bpy.app.handlers.persistent` below, live-edit would silently stop
working the moment a user opened a saved file (the exact, very common workflow this addon
targets) -- Blender's own addon auto-enable only calls `register()` ONCE, at Blender startup, so
the handler was never re-added afterward, and there is no error/warning shown for a missing
depsgraph handler; drags on markers/curve points would then just do nothing, indistinguishable
from "live-edit is broken." This is very plausibly a root cause behind past reports that
curve/slope live-editing "never really worked" across sessions.

BUG FIXED HERE (crash on whole-piece transform): rebuilding used to run SYNCHRONOUSLY, inline,
inside `depsgraph_update_post` -- i.e. `clear_generated_mesh_objects` (which calls
`bpy.data.objects.remove`) followed by fresh `bpy.data.objects.new`/curve/modifier creation, on
EVERY single depsgraph tick fired while a drag was in progress. That is fine for dragging ONE
marker Empty alone (the object being transformed is never one of the objects
`clear_generated_mesh_objects` deletes). It reliably CRASHED Blender, however, when a user
selected an entire piece's Outliner collection (arm_*/pad_*/curb_*/lanecl_*/mark_* + markers all
at once) and Grab/Rotate'd it as a unit: the pad_/curb_/lanecl_/mark_ objects are THEN part of the
same active selection Blender's own modal Transform operator is mid-way through transforming, and
this handler was deleting+recreating those exact objects out from under it, many times a second,
while the dependency graph was itself mid-evaluation for that same transform step -- a reentrant
scene-mutation-during-depsgraph-evaluation pattern the Blender manual explicitly calls unsafe
("don't run functions that manipulate the dependency graph from inside a handler"; `bpy.app.timers`
is the documented escape hatch). The fix: a depsgraph tick no longer mutates anything itself -- it
only records which collections are dirty and (de)bounces a SINGLE `bpy.app.timers` callback, which
runs the actual rebuilds outside the depsgraph callback / outside the transform operator's own
step, once activity settles (`_DEBOUNCE_SECONDS`). This also coalesces a whole rapid drag into one
rebuild instead of dozens, which was wasted work even in the safe (single-marker) case.
"""
import contextlib
import math

import bpy
from mathutils import Vector

RKA_LINKED_TO_KEY = "rka_linked_to"
# One-directional live connectivity between pieces (2026-08, "connected pieces don't follow each
# other"): a marker carrying this custom property (its own object-name string value) FOLLOWS
# whatever marker that name resolves to -- stamped by `ops_segment._stamp_link` (the
# `Extend From Arm`/`Extend From Port` build-time path) or `ops_intersection.RKA_OT_connect_markers`
# (the after-the-fact path, for two independently-built pieces). See `_propagate_links` below for
# what happens when the TARGET side of a link moves. Plain name-reference, matching the
# `rka_curve_object`/`rka_arm_name` convention every other cross-object pointer in this addon
# already uses -- NOT physical Blender parenting, which was considered and rejected: several
# rebuild functions read a marker's `.location` directly as an absolute WORLD position, an
# assumption that only holds today because these markers are never parented; parenting would
# silently corrupt that math the instant a parent moved.
_MAX_PROPAGATION_ITERATIONS = 10   # generous headroom for any real chain; refuses to loop forever
                                    # on an accidental link cycle

_rebuilding_depth = 0
_pending_inter = set()
_pending_seg = set()
_pending_curve_seg = set()
_pending_curve_transition = set()
_pending_port_markers = set()   # port_A/port_B markers dragged directly this window (2026-08,
                                  # "moving a port has no effect") -- see _flush_port_drags
_pending_dirty_markers = set()   # candidate LINK TARGETS this debounce window -- see
                                  # _propagate_links; a superset of what feeds _pending_inter/
                                  # _pending_seg (also includes port_*/origin markers, which don't
                                  # drive their OWN piece's geometry but can still be another
                                  # piece's link target)
_timer_scheduled = False

_undo_in_progress = False   # 2026-08 (the Ctrl+Z crash fix) -- see _on_undo_pre/_on_undo_post

_DEBOUNCE_SECONDS = 0.2   # long enough that an in-progress Grab/Rotate has released control back
                           # to Blender's main loop between ticks; short enough to still feel live

_GUARD_RELEASE_SECONDS = _DEBOUNCE_SECONDS + 0.1   # see rebuilding()'s docstring


def _clear_pending():
    """Discard every pending set with no flush -- used when whatever they were tracking is about
    to become stale/meaningless (an undo/redo just replaced the whole scene state) or on
    unregister. NOT a substitute for `_flush_rebuilds` in the normal case -- this drops work,
    it doesn't do it."""
    global _timer_scheduled
    _pending_inter.clear()
    _pending_seg.clear()
    _pending_curve_seg.clear()
    _pending_curve_transition.clear()
    _pending_dirty_markers.clear()
    _pending_port_markers.clear()
    if _timer_scheduled and bpy.app.timers.is_registered(_flush_rebuilds):
        bpy.app.timers.unregister(_flush_rebuilds)
    _timer_scheduled = False


@bpy.app.handlers.persistent
def _on_undo_pre(scene):
    """Ctrl+Z crash fix (2026-08): Blender's undo/redo is a full scene-state memfile snapshot/
    restore -- every generated object's data (curb/pad/spine/lanecl_*/mark_* point/mesh data) is
    ALREADY part of that snapshot, so it's restored correctly with zero help from this addon.
    But restoring old transforms/geometry still fires ordinary `depsgraph_update_post` events, and
    without this guard `_on_depsgraph_update` would schedule a rebuild reacting to them -- mutating
    `bpy.data` from a handler while Blender's own undo/redo system is mid-restore is a documented-
    unsafe pattern (a different hazard than the reentrant-modal-transform one `rebuilding()`
    guards against), and is plausibly the cause of a crash specifically on Ctrl+Z. There is also
    nothing useful such a rebuild could DO -- the correct post-undo state is already sitting there
    from the snapshot restore; recomputing it from scratch only risks disagreeing with it."""
    global _undo_in_progress
    _undo_in_progress = True


@bpy.app.handlers.persistent
def _on_undo_post(scene):
    """Undo has fully settled -- clear the guard, and drop whatever was pending before/during the
    undo step (it describes a scene state that no longer exists; letting a stale entry schedule a
    rebuild against the just-restored scene would be reacting to leftover noise, not a real edit)."""
    global _undo_in_progress
    _undo_in_progress = False
    _clear_pending()


# Redo shares the exact same reasoning/hazard as undo -- same guard, same handlers.
_on_redo_pre = _on_undo_pre
_on_redo_post = _on_undo_post


@contextlib.contextmanager
def rebuilding():
    """Set a guard so `_on_depsgraph_update` ignores the depsgraph updates a rebuild's OWN object
    mutations generate -- `clear_generated_mesh_objects` deleting/recreating curb/pad/lanecl_*
    objects, or an operator writing to the spine curve's own point data first (e.g.
    `RKA_OT_adjust_segment_lanes` rewriting `spine_obj.data.splines[0].points[i].radius` before
    calling `rebuild_segment_gn_in_place`).

    `_flush_rebuilds` (the debounced path) already guarded itself this way. But every OTHER
    caller -- `RKA_OT_adjust_segment_lanes`/`RKA_OT_adjust_transition_lanes`/
    `RKA_OT_adjust_arm_lanes`/`RKA_OT_add_arm`/`RKA_OT_remove_arm`/`RKA_OT_set_arm_oneway`/
    `RKA_OT_adjust_arm_lanes_out`/`RKA_OT_rebuild_from_handles`/`_propagate_links`'s own
    per-iteration cascade rebuild --
    calls a `rebuild_*_in_place` function DIRECTLY from its own `execute()`, entirely bypassing
    `_flush_rebuilds`, and none of them guarded themselves this way. Left unguarded, a direct
    rebuild that touches the spine's geometry (as `adjust_segment_lanes` does) gets picked up as
    fresh "dirt" by `_on_depsgraph_update`, which schedules a SECOND, entirely unprompted rebuild
    of the SAME collection ~`_DEBOUNCE_SECONDS` later via `bpy.app.timers` -- outside any operator/
    undo context, racing whatever the user does next. This was the confirmed cause of a real
    segfault inside `clear_generated_mesh_objects` (a double rebuild landing back-to-back on one
    segment right after a single 'Adjust Segment Lanes' click -- see the crash log's Python
    backtrace: `_flush_rebuilds` → `rebuild_segment_gn_in_place` → `clear_generated_mesh_objects`,
    with no user action in between).

    IMPORTANT: `_on_depsgraph_update` for a plain property write (e.g. a curve's point radius) does
    NOT fire synchronously inside the `with`/decorated call that made the write -- confirmed
    empirically (forcing an immediate `depsgraph.update()` right after a guarded operator returns
    still observes the dirtying) -- Blender evaluates and delivers it on a LATER tick, by which
    point an immediate "reset on `__exit__`" would already have cleared the guard, never actually
    covering the callback it exists to suppress. So the guard is reference-counted
    (`_rebuilding_depth`, supporting nesting -- `_flush_rebuilds` is itself inside a `rebuilding()`
    block calling rebuild functions that enter it again) and each `__exit__` releases its own count
    via a delayed one-shot `bpy.app.timers` callback (`_GUARD_RELEASE_SECONDS`, comfortably past
    both a same-tick and a next-redraw-cycle delivery) instead of releasing immediately -- keeping
    the suppression window open long enough to actually catch the deferred callback.

    Every `rebuild_*_in_place` function wraps its own body in this (see `ops_intersection.
    rebuild_intersection_in_place` / `ops_segment.rebuild_segment_in_place` / `...
    rebuild_segment_gn_in_place` / `...rebuild_lane_transition_in_place`), so BOTH call paths --
    the debounced flush and every direct operator button -- are covered from ONE place. An operator
    that mutates spine/marker data of its OWN, outside any rebuild function (`RKA_OT_
    adjust_segment_lanes`'s pre-rebuild radius write), must wrap that mutation in its own
    `with rebuilding():` block too -- wrapping only the subsequent rebuild call is not enough."""
    global _rebuilding_depth
    _rebuilding_depth += 1
    try:
        yield
    finally:
        def _release():
            global _rebuilding_depth
            _rebuilding_depth = max(0, _rebuilding_depth - 1)
            return None   # one-shot -- do not repeat
        bpy.app.timers.register(_release, first_interval=_GUARD_RELEASE_SECONDS)


@bpy.app.handlers.persistent
def _on_depsgraph_update(scene, depsgraph):
    global _timer_scheduled
    if _rebuilding_depth > 0 or _undo_in_progress:
        return
    rka = getattr(scene, "rka", None)
    if rka is not None and not rka.live_edit_enabled:
        return

    dirty_curve_names = set()
    dirty_marker_names = set()
    for update in depsgraph.updates:
        obj = update.id
        if isinstance(obj, bpy.types.Object) and obj.type == 'EMPTY' and update.is_updated_transform:
            keys = obj.keys()
            # Broader than the piece-rebuild check just below: a port/origin marker doesn't drive
            # ITS OWN piece's geometry, but it can still be some OTHER piece's link TARGET (e.g.
            # `Extend From Port` stamps a link onto the target port marker's name) -- so any of
            # this addon's own marker kinds is worth waking `_propagate_links` for.
            if (RKA_LINKED_TO_KEY in keys or "rka_origin_marker" in keys or "rka_port" in keys
                    or "rka_arm_name" in keys or "rka_segend" in keys or "rka_segbend" in keys):
                _pending_dirty_markers.add(obj.name)
            if "rka_port" in keys:
                # A port is now a genuine drag handle for its OWN segment's spine endpoint (see
                # _flush_port_drags), not just a candidate link target -- queued separately since
                # it needs its owning spine's point data rewritten, not a piece-level rebuild flag.
                _pending_port_markers.add(obj.name)
            if "rka_arm_name" not in keys and "rka_segend" not in keys and "rka_segbend" not in keys:
                continue
            dirty_marker_names.add(obj.name)
        elif isinstance(obj, bpy.types.Object) and obj.type == 'CURVE' \
                and (update.is_updated_geometry or update.is_updated_transform):
            # Moving the whole curve object OR editing its control points in Edit Mode -- either
            # way, any segment driven by this curve (RKA_OT_build_segment_from_curve) needs a
            # rebuild. Editing points in Edit Mode can report the Curve DATA id instead of the
            # Object in some Blender versions -- caught by the branch below.
            dirty_curve_names.add(obj.name)
        elif isinstance(obj, bpy.types.Curve) and update.is_updated_geometry:
            for o in bpy.data.objects:
                if o.data == obj:
                    dirty_curve_names.add(o.name)

    if dirty_marker_names:
        # NOTE: deliberately NOT using obj.users_collection here -- inside a depsgraph_update_post
        # callback, an updated Object's `users_collection` can read back as EMPTY even though the
        # object genuinely belongs to a collection (verified: a plain arm_* Empty transform-only
        # update reports `users_collection == []` here, while the exact same object queried
        # normally, outside a callback, correctly reports its collection) -- this was the concrete
        # cause of "dragging an arm to change its angle does nothing": the marker branch found the
        # right Empty but could never resolve which collection to rebuild. Scanning
        # `bpy.data.collections` and matching by NAME (same technique the curve-object lookup
        # below already used) sidesteps the stale/unpopulated cache entirely.
        for coll in bpy.data.collections:
            if coll.library is not None:
                continue   # a linked neighbor's own marker could share a locally-dirtied name
            if not coll.get("rka_live_edit", True):
                continue
            if "rka_arm_names" in coll.keys():
                if any(name in coll.objects for name in dirty_marker_names):
                    _pending_inter.add(coll.name)
            elif "rka_p0" in coll.keys():
                if any(name in coll.objects for name in dirty_marker_names):
                    _pending_seg.add(coll.name)

    if dirty_curve_names:
        for coll in bpy.data.collections:
            if coll.library is not None:
                continue
            curve_name = coll.get("rka_curve_object")
            if curve_name in dirty_curve_names and coll.get("rka_live_edit", True):
                # Both plain curve-backed segments AND lane-transition pieces store their spine
                # under the same 'rka_curve_object' key (see ops_segment.py) -- 'rka_lanes_a' only
                # exists on a transition (plain segments use singular 'rka_lanes'), so check it
                # FIRST to route a transition's spine edit to its own tapering rebuild instead of
                # the plain segment's constant-width one (which would silently un-taper it).
                if "rka_lanes_a" in coll.keys():
                    _pending_curve_transition.add(coll.name)
                else:
                    _pending_curve_seg.add(coll.name)

    if not (_pending_inter or _pending_seg or _pending_curve_seg or _pending_curve_transition
             or _pending_dirty_markers or _pending_port_markers):
        return
    # TRUE debounce: cancel + re-arm on EVERY dirtying tick, not just the first. A modal Grab/
    # Rotate fires a depsgraph update on nearly every mouse-move step, so a fire-once timer
    # scheduled from the FIRST tick goes off mid-drag for anything longer than
    # _DEBOUNCE_SECONDS -- i.e. virtually every real drag -- landing right back in the unsafe
    # "delete objects the modal operator is still actively transforming" window this was meant
    # to avoid. Re-arming on every tick means the timer only ever fires after activity has
    # actually gone quiet for a full _DEBOUNCE_SECONDS (mouse released/operator confirmed, or at
    # minimum paused), not on a fixed clock that ignores whether the drag is still live.
    if bpy.app.timers.is_registered(_flush_rebuilds):
        bpy.app.timers.unregister(_flush_rebuilds)
    bpy.app.timers.register(_flush_rebuilds, first_interval=_DEBOUNCE_SECONDS)
    _timer_scheduled = True


def _translate_spine(spine_obj, delta):
    """Rigidly shift EVERY control point of `spine_obj` (a `kit_common.road_spine`-built
    POLY-spline Curve -- see `_build_segment_from_points`) by `delta` (a `Vector`). This, not any
    marker Empty, is what actually drives a curve-backed segment/transition's geometry
    (`_spine_control_points` reads the curve's own point data -- see `move_dependent_marker`'s
    docstring for why the link is nonetheless stored ON a marker). Translating the WHOLE spine
    (not just its start point) carries the piece's entire shape/length/direction along with its
    link target unchanged -- a start-point-only snap would instead stretch/distort the piece by
    dragging its near end while its far end stayed put. `road_spine` always builds a 'POLY'
    spline (never Bezier) at an identity object transform (points are baked as absolute world
    coordinates -- see `kit_common.road_spine`'s own docstring), so a plain per-point add is
    correct with no matrix work needed."""
    if not spine_obj.data.splines:
        return
    for p in spine_obj.data.splines[0].points:
        p.co = (p.co[0] + delta.x, p.co[1] + delta.y, p.co[2] + delta.z, p.co[3])


def _spine_tangent_angle(spine_obj, end):
    """`spine_obj`'s own CURRENT tangent direction (radians, world XY) at its `'start'` (first
    control point) or `'end'` (last control point), measured directly from its own two nearest
    points -- the actual ground-truth orientation of the ROAD ITSELF continuing through that
    point, matching `_arm_joint_state`'s own angle convention (an arm's angle is the direction a
    car travels LEAVING the intersection along it) exactly: for `'start'`, direction FROM the
    joint INTO the interior (`pts[0]` -> `pts[1]`, "departing the joint"); for `'end'`, direction
    FROM the interior TO the joint (`pts[-2]` -> `pts[-1]`, "arriving at the joint") -- these are
    the SAME kind of quantity (the direction of travel as the road passes through/continues past
    that point in its own natural flow), NOT mirror images of each other, even though the two
    point-pairs are read in opposite order. (A 2026-08 attempt to "symmetrize" this to `pts[-1]
    -> pts[-2]` for 'end' was itself a regression -- confirmed by re-deriving from
    `smoketest_median_chain_merge.py`'s own concrete numbers: `_bend_near_end_to_angle` needs
    THIS "arriving" value, not its negation, to place a bend point on the correct side of the
    joint -- reverted; the actual bug that test caught was `_blend_endpoints_range`'s swapped
    arguments for 'end', not this function.) None if the spline has fewer than 2 points (nothing
    to measure a tangent from -- a degenerate mid-drag state)."""
    pts = spine_obj.data.splines[0].points
    if len(pts) < 2:
        return None
    a, b = (pts[0].co, pts[1].co) if end == "start" else (pts[-2].co, pts[-1].co)
    return math.atan2(b[1] - a[1], b[0] - a[0])


def _angle_diff(a, b):
    """Shortest signed difference `a - b` wrapped to (-pi, pi] -- turns two ABSOLUTE angles into
    the one correction `_bend_near_end_to_angle` should apply this flush."""
    return (a - b + math.pi) % (2.0 * math.pi) - math.pi


def _arm_joint_state(arm_obj):
    """For `arm_obj` (an `arm_*` marker Empty), return `(angle_rad, lane_width, lanes_forward,
    lanes_backward, median_width)` -- the joint's current outward direction and the width/lane-
    count/median a piece linked to it should match, or None if `arm_obj` isn't a live arm marker
    of a local intersection.

    `median_width` is this arm's OWN `rka_arm_median_width` (2026-08, user-reported: "each
    intersection arm... have idea of median... one arm can use as transition to ease out the
    median from high count to low count") -- 0.0 by default (`intersection_kit.Arm.median_width`'s
    own back-compat default, a plain arm with no median authored on it), so a segment linking to an
    UNTOUCHED arm still tapers its own median down to 0 by the joint, same as before this field
    existed; but ONE specific arm can now carry a real median of its own (via
    `RKA_OT_adjust_arm_median_width`), and a segment linked there tapers against THAT value instead
    -- the same "transition" `_sync_linked_width` already gives lane count/width. See
    `_segment_joint_state` for the segment-to-segment case (identical shape, target segment's own
    median instead of an arm's).

    2026-08 fix (world_session.blend, "move arm w... edge start to rotate... pulled by center"):
    angle used to be recomputed FRESH from the marker's POSITION every call (`atan2` relative to
    the intersection's origin) -- oversensitive to ordinary hand-drag imprecision, since a drag
    meant only to adjust an arm's distance almost never lands perfectly radially, so it always
    changed the angle at least slightly too, which then rigidly rotated a WHOLE linked segment
    (including its already-correctly-placed far end) by that same small, unintended amount on
    every drag (see `move_dependent_marker`). Angle now comes directly from `arm_obj.rotation_
    euler.z` instead -- a pure Grab/translate never touches the rotation channel at all, so it can
    no longer move the angle by even a fraction of a degree; only an explicit Rotate or
    `RKA_OT_set_arm_angle` does. `ops_intersection.ensure_arm_angle_migrated` seeds `rotation_
    euler.z` from the OLD position-derived angle the first time this runs on an arm authored/
    dragged before this fix (so already-existing content's current visual state is preserved
    exactly, not silently snapped back to its creation-time angle) -- called here too (not just
    from `rebuild_intersection_in_place`) since this function can run first in a flush
    (`_propagate_links` runs before the normal per-collection rebuild dispatch).

    The lane mapping mirrors `RKA_OT_extend_from_arm`'s build-time formula (`ops_segment.py`,
    `forward_lanes`/`lanes_forward`/`lanes_backward`) exactly, so a LIVE joint sync can never
    disagree with what building fresh from that same arm would produce."""
    coll = None
    for c in bpy.data.collections:
        if c.library is not None:
            continue
        if "rka_arm_names" in c.keys() and arm_obj.name in c.objects:
            coll = c
            break
    if coll is None:
        return None
    from . import ops_intersection
    origin = ops_intersection.get_or_create_origin_marker(coll)
    if origin is None:
        return None
    ops_intersection.ensure_arm_angle_migrated(arm_obj, origin.location.x, origin.location.y)
    dx, dy = arm_obj.location.x - origin.location.x, arm_obj.location.y - origin.location.y
    if math.hypot(dx, dy) < 1e-9:
        return None
    angle = arm_obj.rotation_euler.z
    lane_width = coll.get("rka_lane_width", 5.0)
    arm_lanes = int(arm_obj.get("rka_arm_lanes", 1))
    arm_lanes_out = int(arm_obj.get("rka_arm_lanes_out", 0))
    arm_oneway = arm_obj.get("rka_arm_oneway", "") or None
    forward_lanes = arm_lanes_out if arm_lanes_out > 0 else arm_lanes
    lanes_forward = 0 if arm_oneway == 'IN' else forward_lanes
    lanes_backward = 0 if arm_oneway == 'OUT' else arm_lanes
    # This arm's OWN median (2026-08, user-reported: "each intersection arm... have idea of
    # median... one arm can use as transition to ease out the median from high count to low
    # count") -- 0.0 unless genuinely two-way, the SAME gate `Arm.median_half` applies, so a
    # linked segment and this arm can never disagree on whether a median is active here.
    arm_median = float(arm_obj.get("rka_arm_median_width", 0.0))
    median_width = arm_median if (lanes_forward > 0 and lanes_backward > 0) else 0.0
    return angle, lane_width, lanes_forward, lanes_backward, median_width


def _segment_joint_state(target_obj):
    """The segment-port counterpart to `_arm_joint_state`, same `(angle_rad, lane_width,
    lanes_forward, lanes_backward, median_width)` shape, for when a segment links to ANOTHER
    SEGMENT's `port_A`/`port_B`/origin marker instead of an `arm_*` (2026-08, user-reported:
    "support segment to segment alignment... for both arm and segment" -- until now the
    tangent/Z/width sync in `move_dependent_marker` only ever ran for an arm target, gated on
    `"rka_arm_name" in target_obj.keys()`, so linking two segments together got a rigid position
    carry but NEVER a tangent match -- only the linked endpoint's raw position moved, regardless
    of how many interior points either spine has).

    `angle_rad` is the OTHER (target) segment's own tangent AT `target_obj`'s end
    (`_spine_tangent_angle`) -- already OUTWARD (away from the joint, continuing into that piece),
    the exact same convention `_arm_joint_state` returns, so both feed `_bend_near_end_to_angle`
    identically regardless of which kind of piece is on the other end of the link.
    `lane_width`/`lanes_forward`/`lanes_backward`/`median_width` are read from the target's own
    END-AWARE properties (`rka_lanes`/`rka_lanes_backward`/`rka_median_width` for its start,
    `rka_lanes_end`/`rka_lanes_backward_end`/`rka_median_width_end` for its end -- the SAME set
    `_sync_linked_width` itself writes), so a chain of segments propagates width/lane-count/median
    taper exactly like an arm does, and a further link off THIS segment sees whatever taper this
    end actually ended up with. This is the actual "median from a high number to a low number acts
    like a transition" ask (2026-08): linking a wide-median segment's end to a narrow-median (or
    median-less) one's port now tapers the median across the link the same way a lane-count
    mismatch already tapers lanes -- no separate/new transition PIECE needed, since
    `intersection_kit.build_segment_from_spine`'s tapered path already supports
    `median_width`/`median_width_end` differing (Option B, ROAD_JOINT_TRANSITION_STUDY.md finding
    #2) -- the missing piece was only that the JOINT SYNC never read/wrote it.

    None if `target_obj` isn't a valid segment port/origin marker, its owning collection is a
    lane-count TRANSITION piece (`rka_lanes_a` in keys -- a separate, more complex per-end shape
    this doesn't apply to), or its spine is missing/degenerate (fewer than 2 points, a momentary
    mid-drag state)."""
    from . import ops_intersection
    is_port = target_obj.get("rka_port") in ("A", "B")
    is_origin = ops_intersection.ORIGIN_MARKER_KEY in target_obj.keys()
    if not (is_port or is_origin):
        return None
    coll = None
    for c in bpy.data.collections:
        if c.library is not None:
            continue
        if "rka_curve_object" in c.keys() and target_obj.name in c.objects:
            coll = c
            break
    if coll is None or "rka_lanes_a" in coll.keys():
        return None
    spine_name = coll.get("rka_curve_object")
    spine_obj = coll.objects.get(spine_name) if spine_name else None
    if spine_obj is None or spine_obj.type != 'CURVE':
        return None
    end = _dependent_spine_end(target_obj)
    angle = _spine_tangent_angle(spine_obj, end)
    if angle is None:
        return None
    lane_width = coll.get("rka_lane_width", 5.0)
    if end == "end":
        lanes_forward = coll.get("rka_lanes_end", coll.get("rka_lanes", 1))
        lanes_backward = coll.get("rka_lanes_backward_end", coll.get("rka_lanes_backward", 0))
        median_width = coll.get("rka_median_width_end", coll.get("rka_median_width", 0.0))
    else:
        lanes_forward = coll.get("rka_lanes", 1)
        lanes_backward = coll.get("rka_lanes_backward", 0)
        median_width = coll.get("rka_median_width", 0.0)
    return angle, lane_width, lanes_forward, lanes_backward, median_width


def _joint_state(target_obj):
    """Unified dispatch behind `move_dependent_marker`'s tangent/Z/width sync: `_arm_joint_state`
    if `target_obj` is an `arm_*` marker, `_segment_joint_state` if it's a segment port/origin
    marker, else None -- so the sync no longer depends on WHAT KIND of piece a segment is linked
    to, only on the target having a well-defined outward angle at all (2026-08, "support segment
    to segment alignment... for both arm and segment")."""
    if "rka_arm_name" in target_obj.keys():
        return _arm_joint_state(target_obj)
    return _segment_joint_state(target_obj)


def _sync_linked_width(coll, spine_obj, lane_width, lanes_forward, lanes_backward, median_width, end):
    """Keep a segment's OWN start- or end-side lane/median properties (`end`: `'start'` ->
    `rka_lanes`/`rka_lanes_backward`/`rka_median_width`, `'end'` -> `rka_lanes_end`/
    `rka_lanes_backward_end`/`rka_median_width_end`) matching the joint linked at THAT end, and
    refresh the spine's per-point pavement RADIUS to match (`ops_segment._refresh_pavement_radius`,
    which correctly TAPERS between start and end instead of flattening the whole piece to one
    value -- see that function's own docstring) -- without this, the pad/curb boundary at the
    joint can be positioned exactly right and still visibly step/overlap because the two sides'
    WIDTHS were independent stored numbers. Skipped for a lane-count TRANSITION piece (`rka_lanes_a`
    in keys) -- its per-end taper model is a separate, more complex shape this pass doesn't touch.
    No-op if nothing actually changed (avoids dirtying the collection -- and re-triggering another
    flush -- on every no-op cascade tick).

    2026-08 fix: this used to always write the START-side keys regardless of which end `joint_loc`
    actually matched -- harmless while a segment could only ever have ONE end genuinely linked
    (the far port was never a valid link dependent), but a real bug the moment that restriction
    lifted (see `move_dependent_marker`'s dual-end path) -- a far-end joint sync would otherwise
    silently overwrite the segment's START lane count with the far arm's values instead of
    recording a genuine taper. See ROAD_JOINT_TRANSITION_STUDY.md finding #1.

    2026-08 fix: `median_width` added (previously this function never touched median width at all
    -- a segment's median stayed whatever it was independently authored as, even when linked to a
    joint with a very different one, e.g. an arm which always has 0). Threading it through here is
    the actual fix for "median from a high number to a low number acts like a transition" -- see
    `_segment_joint_state`'s docstring; `ops_segment.build_segment_from_spine`'s tapered path
    already renders a `median_width` != `median_width_end` correctly, this was only ever missing
    from the LIVE sync.

    2026-08 fix (surfaced by the above -- confirmed via `smoketest_median_chain_merge.py`): the
    END-side keys (`rka_lanes_end`/`rka_lanes_backward_end`/`rka_median_width_end`) FALL BACK to
    the START-side ones when never independently set (`ops_segment._effective_end_lanes`/
    `_effective_end_median` -- "an untapered piece's end IS its start until something diverges
    them"). Writing the START side here (`end == 'start'`) used to write straight through that
    fallback -- silently changing the FAR end's EFFECTIVE value too, for any piece that was never
    independently tapered, even though only the NEAR end's joint actually changed. This is exactly
    the failure mode every other joint-sync fix this session went to lengths to avoid (see
    `_bend_near_end_to_angle`'s far-end pinning) -- an untouched far port (or a further link off
    it) must never see its own effective lane/median state drift just because the OTHER end's
    joint changed. Fixed by MATERIALIZING the end side's current resolved value into an explicit
    property FIRST, whenever it isn't already explicit -- so the fallback can never again silently
    inherit a start-side change after this point. (The reverse direction needs no such guard: the
    start-side keys have no fallback of their own, so writing the END side can never implicitly
    change the effective START.)"""
    if coll is None or "rka_lanes_a" in coll.keys():
        return
    from . import ops_segment
    if end == "start":
        if coll.get("rka_lanes_end") is None:
            coll["rka_lanes_end"] = ops_segment._effective_end_lanes(coll, backward=False)
        if coll.get("rka_lanes_backward_end") is None:
            coll["rka_lanes_backward_end"] = ops_segment._effective_end_lanes(coll, backward=True)
        if coll.get("rka_median_width_end") is None:
            coll["rka_median_width_end"] = ops_segment._effective_end_median(coll)
    lanes_key = "rka_lanes_end" if end == "end" else "rka_lanes"
    back_key = "rka_lanes_backward_end" if end == "end" else "rka_lanes_backward"
    median_key = "rka_median_width_end" if end == "end" else "rka_median_width"
    changed = (coll.get("rka_lane_width") != lane_width or coll.get(lanes_key) != lanes_forward
               or coll.get(back_key) != lanes_backward or coll.get(median_key) != median_width)
    if not changed:
        return
    coll["rka_lane_width"] = lane_width
    coll[lanes_key] = lanes_forward
    coll[back_key] = lanes_backward
    coll[median_key] = median_width
    ops_segment._refresh_pavement_radius(coll, spine_obj)


def _dependent_spine_end(obj):
    """Which end of its owning segment's spine `obj` (a valid link dependent -- an origin marker,
    `port_A`, or `port_B`, see `ops_intersection._is_link_dependent_marker`) represents: `'end'`
    (spine's LAST control point) for `port_B`, `'start'` (spine's FIRST control point) for
    everything else (the origin marker and `port_A` are both always re-snapped to the spine's
    first point, see `ops_segment._place_segment_ports`/`get_or_create_origin_marker` -- either
    one means the same thing here)."""
    return "end" if obj.get("rka_port") == "B" else "start"


def _other_end_link(coll, this_end, exclude):
    """The `(dependent, target)` pair for the spine end OTHER than `this_end`, if THAT end also
    carries its own live `RKA_LINKED_TO_KEY` -- `(None, None)` if not linked, dangling, or no such
    marker exists (e.g. this coll isn't curve-backed at all). `exclude` is the marker already
    being processed this call (never matches itself). Feeds `move_dependent_marker`'s dual-end
    branch: a segment whose FAR end is ALSO linked can no longer be handled by one anchor's rigid
    transform alone -- see that function's docstring."""
    if coll is None:
        return None, None
    from . import ops_intersection
    want_end = "start" if this_end == "end" else "end"
    for obj in coll.objects:
        if obj is exclude or obj.type != 'EMPTY':
            continue
        if obj.get("rka_port") not in ("A", "B") and ops_intersection.ORIGIN_MARKER_KEY not in obj.keys():
            continue   # not a spine-end marker at all
        if _dependent_spine_end(obj) != want_end:
            continue
        target_name = obj.get(RKA_LINKED_TO_KEY)
        if not target_name:
            continue
        target_obj = bpy.data.objects.get(target_name)
        if target_obj is None:
            continue   # dangling link -- treat as unlinked
        return obj, target_obj
    return None, None


def _blend_endpoints_range(pts, indices, start_new, end_new):
    """Reshape just the points at `indices` (a list of point-array indices, given in spine order --
    not necessarily the WHOLE spline) so the FIRST one lands EXACTLY on `start_new` and the LAST
    EXACTLY on `end_new` (both `Vector`, absolute world-space), blending every point between by its
    own normalized cumulative arc length WITHIN just this sub-range -- the shared core behind
    `_blend_spine_endpoints` (the whole spline, the dual-end-linked case) and
    `_bend_near_end_to_angle`'s stage 2 (a SUB-range from a freshly-placed bend point to the far
    end, the single-end case). A SHEAR, not a rigid rotation+scale: never risks swinging an
    interior point unpredictably the way a rotation could. Fewer than 2 indices is a no-op
    (nothing to blend). Reassigns the WHOLE `co` tuple at once, never a single element
    (`p.co[0] = ...`) -- partial element assignment on a bpy_prop_array can silently corrupt the
    underlying curve data instead of writing through cleanly, surfacing later as an unrelated
    crash in a completely different GN evaluation (confirmed empirically: this was the actual
    cause of a flaky segfault in smoketest_matkey_panel.py, nothing to do with materials)."""
    n = len(indices)
    if n < 2:
        return
    old = [Vector(pts[i].co[:3]) for i in indices]
    delta_start = start_new - old[0]
    delta_end = end_new - old[-1]
    cum = [0.0] * n
    for i in range(1, n):
        a, b = old[i - 1], old[i]
        cum[i] = cum[i - 1] + math.hypot(b.x - a.x, b.y - a.y)
    total = cum[-1]
    for i, idx in enumerate(indices):
        t = cum[i] / total if total > 1e-9 else 0.0
        d = delta_start.lerp(delta_end, t)
        new_pt = old[i] + d
        pts[idx].co = (new_pt.x, new_pt.y, new_pt.z, pts[idx].co[3])


def _blend_spine_endpoints(spine_obj, start_new, end_new):
    """Reshape `spine_obj`'s spline so its first point lands EXACTLY on `start_new` and its last
    point lands EXACTLY on `end_new` (both `Vector`, absolute world-space), while every interior
    point keeps as much of its own relative shape as possible -- the dual-end-linked case (see
    `move_dependent_marker`), used when BOTH of a segment's ends are independently linked to a
    live joint, so neither end's rigid single-anchor transform alone can satisfy both endpoints at
    once. Thin wrapper over `_blend_endpoints_range` for the common "the whole spline" case -- see
    that function for the blend itself. A single-point (degenerate) spline is left untouched."""
    pts = spine_obj.data.splines[0].points
    n = len(pts)
    if n < 2:
        return
    _blend_endpoints_range(pts, list(range(n)), start_new, end_new)


def _ensure_bend_room(spine_obj, this_end, bend_fraction=0.15, max_bend_len=10.0):
    """If `spine_obj`'s spline is a plain 2-point straight line, insert ONE new interior control
    point near `this_end` so a subsequent local tangent correction there
    (`_bend_near_end_to_angle`) has actual geometry to bend -- a straight 2-point line has no
    interior at all, so matching the NEAR endpoint's exact position AND tangent while ALSO pinning
    the FAR endpoint exactly is mathematically impossible without room to bend somewhere (verified
    against `world_session.blend`: `Segment_001`, the real reported case, is exactly this -- a
    plain 2-point line, not an edge case).

    The new point sits `bend_fraction` of the spine's CURRENT length from `this_end` (capped at
    `max_bend_len` so a very long segment doesn't put the bend implausibly far from the joint it's
    fixing), on the CURRENT straight line -- it starts perfectly co-linear, so this alone changes
    nothing visually; it purely adds a point for the caller to then bend. Radius (pavement
    half-width) is linearly interpolated to match the existing start/end taper. No-op (returns
    False) if the spline already has 3+ points -- an authored bend/hill already has interior
    points to use, nothing needs inserting."""
    sp = spine_obj.data.splines[0]
    pts = sp.points
    if len(pts) != 2:
        return False
    p0 = Vector(pts[0].co[:3])
    p1 = Vector(pts[1].co[:3])
    total = (p1 - p0).length
    if total < 1e-6:
        return False
    dist = min(total * bend_fraction, max_bend_len)
    t = (dist / total) if this_end == "start" else (1.0 - dist / total)
    new_pt = p0.lerp(p1, t)
    new_radius = pts[0].radius + (pts[1].radius - pts[0].radius) * t
    old_r0, old_r1 = pts[0].radius, pts[1].radius
    old_co0, old_co1 = tuple(pts[0].co), tuple(pts[1].co)
    sp.points.add(1)
    pts = sp.points
    pts[0].co, pts[0].radius = old_co0, old_r0
    pts[1].co, pts[1].radius = (new_pt.x, new_pt.y, new_pt.z, 1.0), new_radius
    pts[2].co, pts[2].radius = old_co1, old_r1
    return True


def _bend_near_end_to_angle(spine_obj, this_end, joint_loc, angle_rad, far_pin):
    """Re-point `spine_obj`'s end at `this_end` to land EXACTLY on `joint_loc` (X, Y, AND Z) and,
    if `angle_rad` is given (world XY bearing, its live joint's current outward angle), EXACTLY
    match that tangent too -- while leaving the FAR end pinned EXACTLY at `far_pin` -- the answer
    to "only move the connecting end to the arm['s tangent/elevation], don't move the [already
    correct/independently-anchored] far port" (2026-08, user-reported: the old rigid whole-spine
    rotation swung a far end that may already be correctly connected elsewhere, potentially by
    many meters for a long segment and a large angle correction -- see `move_dependent_marker`'s
    docstring for the full history; extended 2026-08 to cover VERTICAL/Z the same way, user-
    reported: "3d vertical level is not aligned, need to manually adjust" after an arm was matched
    to a segment's XY+tangent exactly but not its Z, since an intersection pad is flat and cannot
    itself tilt to close a vertical gap -- see `move_dependent_marker`'s XY-only translate).

    `angle_rad=None` means "don't touch the tangent, only fix Z" -- the bend point keeps its
    CURRENT XY direction from `this_end`, only the Z lineage shifts by however much the near end's
    own Z just changed (a locally-consistent starting point that stage 2, below, then blends down
    to nothing by the far end -- Z is never a rigid whole-piece shift, the same reasoning as the
    tangent case: a joint's own grade is a per-joint fitting concern, not something that should
    drag an already-correct far port up or down).

    Corrected in two EXACT stages, not one rigid rotation + best-effort cleanup (which would only
    ever be approximately right -- see the superseded approach in this function's own git history
    if reused for reference):

    1. `_ensure_bend_room` guarantees an interior point immediately after `this_end` exists. `this_
       end`'s own point is set to EXACTLY `joint_loc` (all 3 coords). The bend point right after it
       is placed EXACTLY `(joint_loc.x, joint_loc.y, old_bend.z + delta_z) + (its own original
       distance from `this_end`) * direction(angle_rad or the unchanged current XY direction)` --
       this alone makes the tangent (when `angle_rad` is given) and Z both land correctly at the
       joint, by direct construction. No approximation, no residual.
    2. Every point from THAT bend point through the far end is reshaped by `_blend_endpoints_range`
       (arc-length-blended shear, scoped to just this sub-range) so the far end lands back EXACTLY
       on `far_pin` (X, Y, AND Z). The bend point itself is one of this blend's own two pinned
       ends, so stage 1's exact joint fit is completely untouched by this pass -- the two stages
       don't fight."""
    _ensure_bend_room(spine_obj, this_end)
    pts = spine_obj.data.splines[0].points
    n = len(pts)
    near_idx = 0 if this_end == "start" else n - 1
    bend_idx = 1 if this_end == "start" else n - 2
    old_near = Vector(pts[near_idx].co[:3])
    old_bend = Vector(pts[bend_idx].co[:3])
    dist_near_bend = (old_bend - old_near).length
    if angle_rad is not None:
        d = Vector((math.cos(angle_rad), math.sin(angle_rad), 0.0))
    else:
        old_dir_xy = Vector((old_bend.x - old_near.x, old_bend.y - old_near.y, 0.0))
        d = old_dir_xy.normalized() if old_dir_xy.length > 1e-9 else Vector((1.0, 0.0, 0.0))
    delta_z = joint_loc.z - old_near.z
    new_bend = Vector((joint_loc.x, joint_loc.y, old_bend.z + delta_z)) + d * dist_near_bend
    pts[near_idx].co = (joint_loc.x, joint_loc.y, joint_loc.z, pts[near_idx].co[3])
    pts[bend_idx].co = (new_bend.x, new_bend.y, new_bend.z, pts[bend_idx].co[3])

    # `_blend_endpoints_range(pts, indices, start_new, end_new)` pins `pts[indices[0]]` to
    # `start_new` and `pts[indices[-1]]` to `end_new` -- for 'start' `sub`'s first index IS
    # `bend_idx` (pin to `new_bend`) and its last IS the far end (pin to `far_pin`), so
    # `(new_bend, far_pin)` is correct as-is. For 'end' `sub` runs the OPPOSITE way -- its first
    # index is the FAR end (0) and its last is `bend_idx` -- so the two arguments must swap too,
    # or the far end and the just-placed bend point get pinned to each other's targets (2026-08
    # fix, surfaced by `smoketest_median_chain_merge.py`: the first coverage of a single-end
    # correction at a piece's 'end' -- this silently swapped the far-pinned point with the
    # bend point, producing an inserted "overshoot and double back" zigzag instead of a smooth
    # local bend).
    if this_end == "start":
        sub = list(range(bend_idx, n))
        _blend_endpoints_range(pts, sub, new_bend, Vector(far_pin))
    else:
        sub = list(range(0, bend_idx + 1))
        _blend_endpoints_range(pts, sub, Vector(far_pin), new_bend)


def move_dependent_marker(coll, obj, target_obj):
    """Carry DEPENDENT marker `obj` (belonging to piece `coll`) to match link target `target_obj`
    -- the one shared "make this marker match its link target" primitive used both by
    `_propagate_links` (every automatic cascade) and `ops_intersection.RKA_OT_connect_markers`
    (the one-time initial snap when a link is first created), so the two can never drift apart on
    what "matching" means. For an intersection's `arm_*` marker, the marker's OWN `.location` IS
    the geometry driver (`rebuild_intersection_in_place` reads arm positions directly) -- moving
    it is sufficient. For anything else (a curve-backed segment/transition's origin marker or
    `port_A`/`port_B`, the only other kinds `_stamp_link`/`RKA_OT_connect_markers` target), the
    marker itself is cosmetic -- its owning piece's spine is reshaped to match instead.

    2026-08 (joint unification -- "gap/overlap when an arm rotates"): when `target_obj` is an
    `arm_*` marker, position alone is no longer enough -- the spine is ALSO rotated around the
    now-matched joint point to track the arm's current outward angle (`_arm_joint_state` +
    `_rotate_spine_points`), and the segment's own width/lane counts are synced to the arm's
    (`_sync_linked_width`). Translation-only was the root cause of a kink at the joint (POLY
    spines have no tangent continuity, so `GN_RoadProfile`'s sweep visibly twists there) and of
    the width mismatch producing a visible step even when positions matched exactly.

    2026-08 fix (world_session.blend, user-reported: "move arm W... edge start to rotate
    clockwise... major gap... adjust the pad may work temporary, but when move arm/intersection,
    that strange angle is back again"): the rotation used to be tracked INCREMENTALLY -- an
    `rka_joint_last_angle` value stashed on `obj`, applying only the DELTA between the arm's
    previous and current angle each call. That can only ever correct for CHANGES since the link
    was last processed -- any mismatch already baked in before `rka_joint_last_angle` was first
    seeded (e.g. `RKA_OT_connect_markers`'s one-time initial snap syncs POSITION but, on that very
    first call, has no previous angle to diff against yet, so applies NO rotation at all) persists
    FOREVER, since every later delta is measured from that same wrong baseline. Confirmed directly
    in `world_session.blend`: a linked segment's spine sat EXACTLY on its arm (0.0000 m position
    gap) with a ~12 deg tangent mismatch that no amount of further arm dragging ever closed.
    Replaced with an ABSOLUTE, self-correcting measurement (`_spine_tangent_angle`): every call
    measures the spine's own CURRENT tangent directly and rotates by however much that actually
    differs from the target's angle right now -- idempotent and immune to any stale/never-seeded
    bookkeeping, matching the same "re-derive from ground truth every time" philosophy
    `_blend_spine_endpoints` already uses for the dual-end case below.

    2026-08 (dual-end linking, ROAD_JOINT_TRANSITION_STUDY.md's "hard to align/adjust edge angle"
    finding #3): a segment's FAR port can now ALSO be a link dependent (see
    `ops_intersection._is_link_dependent_marker`) -- when `_other_end_link` finds the OTHER end is
    independently linked too, a single rigid whole-spine transform anchored at just THIS end would
    undo whatever already positioned the other end (whichever call happens to run last would win),
    so this branches to `_blend_spine_endpoints` instead: BOTH ends' live target positions are
    read directly and the spine is reshaped to match both at once, order-independent (re-derived
    fresh from absolute positions every call, not from an incremental delta) -- calling this
    function for either end of a dual-linked segment, in either order, converges to the same
    result. Width is synced independently at each linked end (`end='start'`/`'end'`).

    2026-08 fix (single-end tangent correction no longer swings the far end, user-reported: "the
    end port [the non-connecting end] is not moved, only move the connect spine to the arm
    tangent" -- a whole-spine rigid rotation, the previous behavior below, swings the FAR end by
    however far the segment is long times the correction angle, even though that far end may
    already be correctly connected/anchored elsewhere on its own): HORIZONTAL (X, Y) position is
    still a plain rigid `_translate_spine` (this genuinely SHOULD carry the whole piece, including
    the far end -- see `smoketest_link_propagation.py`'s multi-hop cascade, still relying on
    exactly this for a pure move). TANGENT and VERTICAL (Z) corrections changed: instead of
    `_rotate_spine_points` rigidly rotating (or a uniform Z shift silently carrying) every point,
    `_bend_near_end_to_angle` re-points ONLY the near end's local tangent/elevation (inserting a
    bend point first if the spine is a plain straight 2-point line and has no interior point to
    bend at all -- confirmed the common case, `world_session.blend`'s own `Segment_001`) while the
    far end is pinned EXACTLY at wherever the plain XY-only translate already put it -- so a
    tangent or elevation fix at one joint never disturbs a far port that's already correctly in
    place, horizontally OR vertically.

    2026-08 fix (user-reported: "3d vertical level is not aligned, need to manually adjust" --
    `RKA_OT_aim_arm_at` matches an arm to a target's XY position + tangent exactly, since an
    intersection pad is flat and has no Z of its own to give -- see `intersection_kit.py`'s "all
    geometry is 2D, callers add one constant world Z" convention -- so a real Z difference between
    the arm and the segment's port survived even after a perfect XY+tangent match): the plain
    translate above now only ever carries X and Y -- Z is corrected the SAME LOCAL way as tangent
    (`_bend_near_end_to_angle`, which now takes an optional `angle_rad=None` for "fix Z only, keep
    the current tangent"), so linking a segment to an arm now closes BOTH the horizontal gap
    (rigid carry, as before) AND the vertical one (a local grade fit near the joint), while a far
    port that's already correctly connected elsewhere is disturbed in neither X/Y, Z, nor tangent."""
    target_loc = target_obj.location.copy()
    old_loc = obj.location.copy()
    obj.location = target_loc
    if "rka_arm_name" in obj.keys():
        return
    spine_name = coll.get("rka_curve_object") if coll is not None else None
    spine_obj = bpy.data.objects.get(spine_name) if spine_name else None
    if spine_obj is None or spine_obj.type != 'CURVE':
        return

    this_end = _dependent_spine_end(obj)
    other_dep, other_target = _other_end_link(coll, this_end, obj)

    if other_dep is not None and other_target is not None:
        other_loc = other_target.location.copy()
        start_new, end_new = (target_loc, other_loc) if this_end == "start" else (other_loc, target_loc)
        _blend_spine_endpoints(spine_obj, start_new, end_new)
    else:
        _translate_spine(spine_obj, Vector((target_loc.x - old_loc.x, target_loc.y - old_loc.y, 0.0)))
        pts = spine_obj.data.splines[0].points
        near_idx = 0 if this_end == "start" else -1
        far_idx = -1 if this_end == "start" else 0
        far_pin = Vector(pts[far_idx].co[:3])   # AFTER the XY-only translate above -- a pure
                                                 # horizontal move still carries this far end
                                                 # rigidly; a tangent/Z fix below must not move it
                                                 # any further.
        angle_rad = None
        joint = _joint_state(target_obj)
        if joint is not None:
            current_tangent = _spine_tangent_angle(spine_obj, this_end)
            if current_tangent is not None and abs(_angle_diff(joint[0], current_tangent)) > 1e-9:
                angle_rad = joint[0]
        z_mismatch = abs(pts[near_idx].co[2] - target_loc.z) > 1e-9
        if angle_rad is not None or z_mismatch:
            _bend_near_end_to_angle(spine_obj, this_end, target_loc, angle_rad, far_pin)

    joint = _joint_state(target_obj)
    if joint is not None:
        _, lane_width, lanes_fwd, lanes_bwd, median_width = joint
        _sync_linked_width(coll, spine_obj, lane_width, lanes_fwd, lanes_bwd, median_width,
                            end=this_end)
    if other_dep is not None and other_target is not None:
        other_joint = _joint_state(other_target)
        if other_joint is not None:
            _, lane_width, lanes_fwd, lanes_bwd, median_width = other_joint
            other_end = "start" if this_end == "end" else "end"
            _sync_linked_width(coll, spine_obj, lane_width, lanes_fwd, lanes_bwd, median_width,
                                end=other_end)


def _flush_port_drags(port_names, skip_colls=frozenset()):
    """Ports (`port_A`/`port_B`) were originally pure click-targets, re-snapped to the spine's
    endpoint every rebuild and otherwise inert by design (see `ops_segment._place_segment_ports`'s
    docstring) -- 2026-08 (joint unification, "moving a port has no effect"): dragging one now
    writes its new position directly into the spine's corresponding endpoint control point, the
    same way `arm_*` already drives its intersection. Returns `(curve_colls, transition_colls)`
    -- the set of collection names needing `rebuild_segment_gn_in_place` /
    `rebuild_lane_transition_in_place` respectively as a result, so the caller can fold them into
    the same dispatch the normal spine-edit path already uses.

    `skip_colls`: collection names to ignore even if one of their ports is pending -- see
    `_flush_rebuilds`'s call site for why a same-flush spine edit must always win over a
    possibly-stale queued port drag for the same piece."""
    from . import ops_intersection
    curve_colls, transition_colls = set(), set()
    for name in port_names:
        port = bpy.data.objects.get(name)
        if port is None or "rka_port" not in port.keys():
            continue
        coll = None
        for c in bpy.data.collections:
            if c.library is not None:
                continue
            if "rka_curve_object" in c.keys() and port.name in c.objects:
                coll = c
                break
        if coll is None or coll.name in skip_colls:
            continue
        spine_name = coll.get("rka_curve_object")
        spine_obj = bpy.data.objects.get(spine_name) if spine_name else None
        if spine_obj is None or spine_obj.type != 'CURVE' or not spine_obj.data.splines:
            continue
        pts = spine_obj.data.splines[0].points
        if not pts:
            continue
        idx = 0 if port.get("rka_port") == "A" else len(pts) - 1
        old = Vector(pts[idx].co[:3])
        new = port.location.copy()
        if (old - new).length < 1e-6:
            continue
        pts[idx].co = (new.x, new.y, new.z, pts[idx].co[3])   # whole-tuple write -- see
                                                                # _blend_endpoints_range's note
        if idx == 0:
            # Keep the piece's link ANCHOR (always coincident with point 0 -- see
            # get_or_create_origin_marker/_stamp_link) in sync, so a future cascade from whatever
            # THIS piece is linked to doesn't drag point 0 back from a now-stale remembered spot.
            origin = ops_intersection.get_or_create_origin_marker(coll)
            if origin is not None and (Vector(origin.location) - old).length < 1e-3:
                origin.location = new
        if "rka_lanes_a" in coll.keys():
            transition_colls.add(coll.name)
        else:
            curve_colls.add(coll.name)
    return curve_colls, transition_colls


def _propagate_links(seed_marker_names):
    """One-directional live connectivity (`RKA_LINKED_TO_KEY`, see the module-level docstring
    above): `seed_marker_names` are markers that moved this debounce window. Any OTHER local
    piece's own anchor marker carrying a `rka_linked_to` naming one of them is a DEPENDENT --
    carry it (and its whole piece, see `move_dependent_marker`) to match its target's CURRENT
    position, then rebuild that piece immediately via the same dispatcher
    `RKA_OT_rebuild_from_handles` uses (`ops_intersection._rebuild_piece_in_place`) so it reflects
    the move in THIS flush, not one debounce cycle later -- and so any of ITS OWN markers a
    rebuild re-derives (a segment's `port_A`/`port_B`, re-computed from its now-translated spine)
    are correct BEFORE being offered as seeds for the next iteration. This per-iteration rebuild
    (rather than batching every rebuild to the very end) is what makes a chain cascade correctly:
    a `port_*` marker's position only becomes accurate once its owning piece has actually
    rebuilt, and the NEXT piece in the chain may be linked to that exact port, not to this piece's
    origin marker. Bounded by `_MAX_PROPAGATION_ITERATIONS` so an accidental link cycle can't loop
    forever. A dangling link (target object deleted) is a silent no-op, matching this addon's
    established self-heal philosophy (`get_or_create_origin_marker`, `build_curb_corners`'s
    degenerate-skip).

    Must run from inside a `rebuilding()` block (see caller) -- it mutates marker/spine positions
    itself, which would otherwise re-dirty and re-schedule another flush."""
    from . import ops_intersection
    ctx = bpy.context
    moved = set(seed_marker_names)
    for _ in range(_MAX_PROPAGATION_ITERATIONS):
        if not moved:
            break
        next_moved = set()
        touched = set()
        for coll in bpy.data.collections:
            if coll.library is not None or not coll.get("rka_live_edit", True):
                continue
            for obj in coll.objects:
                target_name = obj.get(RKA_LINKED_TO_KEY)
                if not target_name or target_name not in moved:
                    continue
                target_obj = bpy.data.objects.get(target_name)
                if target_obj is None:
                    continue   # dangling link -- leave it, nothing to follow
                already_synced = (obj.location - target_obj.location).length < 1e-6
                if already_synced and _joint_state(target_obj) is None:
                    continue   # already in sync -- nothing to cascade from here
                # NOTE: a target with a real joint state (an arm, OR a segment port/origin, see
                # _joint_state) is NOT skipped on a position match alone -- its TANGENT can still
                # have changed with this marker's own position untouched: an arm's angle from a
                # lane/oneway button or a sibling arm's rebuild re-deriving this one's tail_length
                # (_arm_joint_state's fresh-angle-every-time contract), OR -- 2026-08, "support
                # segment to segment alignment" -- a segment port's OWN tangent, since
                # _bend_near_end_to_angle's far-end pin keeps a port's ABSOLUTE POSITION fixed
                # while still reshaping the interior point right before it, which is exactly what
                # that port's tangent is measured from. Either way move_dependent_marker's
                # tangent/width sync must still run.
                move_dependent_marker(coll, obj, target_obj)
                touched.add(coll.name)
        for name in touched:
            coll = ops_intersection.local_collection(name)
            if coll is None:
                continue
            ops_intersection._rebuild_piece_in_place(ctx, coll)
            for o in coll.objects:
                if o.type == 'EMPTY' and ("rka_arm_name" in o.keys() or "rka_port" in o.keys()
                                           or "rka_origin_marker" in o.keys()):
                    next_moved.add(o.name)
        moved = next_moved


def _break_stale_links():
    """Auto-break on manual drag (see module docstring): for every marker anywhere still carrying
    `RKA_LINKED_TO_KEY`, a position mismatch against its target can ONLY mean the dependent marker
    itself was independently dragged away -- `_propagate_links` always leaves the two exactly
    equal -- so the link is cleared rather than left to silently snap back the next time the
    target happens to move. Run once, after every rebuild pass (propagation + the normal
    dispatch), so this sees each marker's final settled position for this flush."""
    for coll in bpy.data.collections:
        if coll.library is not None:
            continue
        for obj in coll.objects:
            target_name = obj.get(RKA_LINKED_TO_KEY)
            if not target_name:
                continue
            target_obj = bpy.data.objects.get(target_name)
            if target_obj is None:
                continue   # dangling link -- nothing to compare against, leave it
            if (obj.location - target_obj.location).length >= 1e-6:
                del obj[RKA_LINKED_TO_KEY]


def _flush_rebuilds():
    """Runs OUTSIDE the depsgraph callback (on Blender's main-loop timer queue -- see module
    docstring's crash fix) once drag activity has settled. Snapshots + clears the pending sets
    FIRST so any new dirtying that arrives while this runs (or that arrived in the debounce
    window) schedules its own fresh timer rather than being silently dropped."""
    global _timer_scheduled
    inter, seg, curve_seg, curve_transition = (
        set(_pending_inter), set(_pending_seg), set(_pending_curve_seg), set(_pending_curve_transition))
    markers = set(_pending_dirty_markers)
    port_markers = set(_pending_port_markers)
    _pending_inter.clear()
    _pending_seg.clear()
    _pending_curve_seg.clear()
    _pending_curve_transition.clear()
    _pending_dirty_markers.clear()
    _pending_port_markers.clear()
    _timer_scheduled = False

    from . import ops_intersection, ops_segment
    with rebuilding():
        if port_markers:
            # A piece whose SPINE was directly/geometrically edited this same flush (`curve_seg`/
            # `curve_transition`, from a genuine dirty-curve depsgraph event) is a more authoritative
            # signal than a QUEUED port-drag intent that may have gone stale sitting in
            # `_pending_port_markers` across several debounce windows (the port's `.location` at
            # flush time could predate a later, more direct spine edit reaching the same piece --
            # confirmed by `smoketest_ports.py`'s step 4, which edits the spine directly right
            # after an earlier, unrelated port dirty event was still pending) -- replaying that
            # stale port position into the spine would silently UNDO the newer, more direct edit.
            # Drop any pending port drag whose owning piece already has a spine dirty this flush;
            # the normal rebuild dispatch below re-snaps that port to the spine's real state anyway.
            already_spine_dirty = curve_seg | curve_transition
            port_curve, port_transition = _flush_port_drags(port_markers, already_spine_dirty)
            curve_seg |= port_curve
            curve_transition |= port_transition
        if markers:
            # Before the normal dispatch below: a dirtied TARGET marker (an arm, a port, another
            # piece's origin marker) may have dependents linked to it elsewhere in the file --
            # cascade those first so they rebuild in this same flush. See its own docstring.
            _propagate_links(markers)
        ctx = bpy.context
        for name in inter:
            # local_collection, not a bare bpy.data.collections.get(name) -- a linked neighbor's
            # same-named piece must never be the one silently rebuilt in place. See its docstring.
            coll = ops_intersection.local_collection(name)
            if coll is not None:
                ops_intersection.rebuild_intersection_in_place(ctx, coll)
        for name in seg:
            coll = ops_intersection.local_collection(name)
            if coll is not None:
                ops_segment.rebuild_segment_in_place(ctx, coll)
        for name in curve_seg:
            coll = ops_intersection.local_collection(name)
            if coll is not None:
                ops_segment.rebuild_segment_gn_in_place(ctx, coll)
        for name in curve_transition:
            coll = ops_intersection.local_collection(name)
            if coll is not None:
                ops_segment.rebuild_lane_transition_in_place(ctx, coll)
        if markers:
            _break_stale_links()
        # One continuous median WALL mesh spanning a whole linked run of segments, instead of one
        # per piece (2026-08, "single mesh of curb instead of curb on each way") -- runs AFTER
        # every per-piece rebuild above, so every member's spine/median state is current this
        # flush. Fully recomputes every chain from scratch every call -- see median_merge's own
        # docstring for why delete+recreate is safe specifically here (this whole block already
        # only ever runs in the post-drag deferred context, never the raw depsgraph callback).
        from . import median_merge
        median_merge.sync_median_chains(ctx, RKA_LINKED_TO_KEY, ops_intersection.ORIGIN_MARKER_KEY)
    return None   # one-shot -- do not repeat


def register():
    if _on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)
    if _on_undo_pre not in bpy.app.handlers.undo_pre:
        bpy.app.handlers.undo_pre.append(_on_undo_pre)
    if _on_undo_post not in bpy.app.handlers.undo_post:
        bpy.app.handlers.undo_post.append(_on_undo_post)
    if _on_redo_pre not in bpy.app.handlers.redo_pre:
        bpy.app.handlers.redo_pre.append(_on_redo_pre)
    if _on_redo_post not in bpy.app.handlers.redo_post:
        bpy.app.handlers.redo_post.append(_on_redo_post)


def unregister():
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
    if _on_undo_pre in bpy.app.handlers.undo_pre:
        bpy.app.handlers.undo_pre.remove(_on_undo_pre)
    if _on_undo_post in bpy.app.handlers.undo_post:
        bpy.app.handlers.undo_post.remove(_on_undo_post)
    if _on_redo_pre in bpy.app.handlers.redo_pre:
        bpy.app.handlers.redo_pre.remove(_on_redo_pre)
    if _on_redo_post in bpy.app.handlers.redo_post:
        bpy.app.handlers.redo_post.remove(_on_redo_post)
    global _timer_scheduled, _rebuilding_depth, _undo_in_progress
    if _timer_scheduled and bpy.app.timers.is_registered(_flush_rebuilds):
        bpy.app.timers.unregister(_flush_rebuilds)
    _timer_scheduled = False
    # Any pending `_release` timer(s) from `rebuilding()` are anonymous closures (a fresh function
    # object per call), so they can't be targeted by `bpy.app.timers.unregister` individually --
    # they're harmless no-ops if they fire after unregister (just decrement a counter this module
    # no longer reads until `register()` runs again), so just reset the counter itself here.
    _rebuilding_depth = 0
    _undo_in_progress = False
    _pending_inter.clear()
    _pending_seg.clear()
    _pending_curve_seg.clear()
    _pending_curve_transition.clear()
    _pending_dirty_markers.clear()
    _pending_port_markers.clear()
