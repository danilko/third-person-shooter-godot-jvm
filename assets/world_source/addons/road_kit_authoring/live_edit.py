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

BUG FIXED HERE: `bpy.app.handlers.depsgraph_update_post.append(...)` handlers are NOT persistent
by default -- Blender clears every non-persistent handler on ANY new file load (File > New, File >
Open, `read_homefile`), including a freshly re-opened .blend the addon was already "enabled" in.
Without `@bpy.app.handlers.persistent` below, live-edit would silently stop working the moment a
user opened a saved file (the exact, very common workflow this addon targets) -- Blender's own
addon auto-enable only calls `register()` ONCE, at Blender startup, so the handler was never
re-added afterward, and there is no error/warning shown for a missing depsgraph handler; drags on
markers/curve points would then just do nothing, indistinguishable from "live-edit is broken."
This is very plausibly a root cause behind past reports that curve/slope live-editing "never
really worked" across sessions.
"""
import bpy

_rebuilding = False


@bpy.app.handlers.persistent
def _on_depsgraph_update(scene, depsgraph):
    global _rebuilding
    if _rebuilding:
        return
    rka = getattr(scene, "rka", None)
    if rka is not None and not rka.live_edit_enabled:
        return

    dirty_inter = set()
    dirty_seg = set()
    dirty_curve_names = set()
    dirty_marker_names = set()
    for update in depsgraph.updates:
        obj = update.id
        if isinstance(obj, bpy.types.Object) and obj.type == 'EMPTY' and update.is_updated_transform:
            keys = obj.keys()
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
            if not coll.get("rka_live_edit", True):
                continue
            if "rka_arm_names" in coll.keys():
                if any(name in coll.objects for name in dirty_marker_names):
                    dirty_inter.add(coll.name)
            elif "rka_p0" in coll.keys():
                if any(name in coll.objects for name in dirty_marker_names):
                    dirty_seg.add(coll.name)

    dirty_curve_seg = set()
    dirty_curve_transition = set()
    if dirty_curve_names:
        for coll in bpy.data.collections:
            curve_name = coll.get("rka_curve_object")
            if curve_name in dirty_curve_names and coll.get("rka_live_edit", True):
                # Both plain curve-backed segments AND lane-transition pieces store their spine
                # under the same 'rka_curve_object' key (see ops_segment.py) -- 'rka_lanes_a' only
                # exists on a transition (plain segments use singular 'rka_lanes'), so check it
                # FIRST to route a transition's spine edit to its own tapering rebuild instead of
                # the plain segment's constant-width one (which would silently un-taper it).
                if "rka_lanes_a" in coll.keys():
                    dirty_curve_transition.add(coll.name)
                else:
                    dirty_curve_seg.add(coll.name)

    if not dirty_inter and not dirty_seg and not dirty_curve_seg and not dirty_curve_transition:
        return

    from . import ops_intersection, ops_segment
    _rebuilding = True
    try:
        ctx = bpy.context
        for name in dirty_inter:
            coll = bpy.data.collections.get(name)
            if coll is not None:
                ops_intersection.rebuild_intersection_in_place(ctx, coll)
        for name in dirty_seg:
            coll = bpy.data.collections.get(name)
            if coll is not None:
                ops_segment.rebuild_segment_in_place(ctx, coll)
        for name in dirty_curve_seg:
            coll = bpy.data.collections.get(name)
            if coll is not None:
                ops_segment.rebuild_segment_gn_in_place(ctx, coll)
        for name in dirty_curve_transition:
            coll = bpy.data.collections.get(name)
            if coll is not None:
                ops_segment.rebuild_lane_transition_in_place(ctx, coll)
    finally:
        _rebuilding = False


def register():
    if _on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)


def unregister():
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
