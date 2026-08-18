"""Prototype intersection builder: curb corners + lane-movement centerlines + a visual driving
ribbon, generated from nothing but a handful of approach-arm angles.

This is the resolved answer to Kit geometry v2 item 4's open turn-connector question (see
road_blender_godot.md): corners round to a FIXED radius via closed-form 2D fillet math
(`lib/intersection_kit.py`, no bpy, self-tested with `python3 lib/intersection_kit.py`), not a
hand-tagged curve and not a revived `road_graph.py` bezier. The default radius is deliberately
RELAXED well past the tight ~3.5 m real-world minimum-vehicle-turning-radius (see the reference
image this was designed against) -- a game AI driver should get a wide, easy arc, not a tight hug
of the curb.

Every object this operator creates is new (a fresh collection each run) -- it never edits
`lane_kit.blend` or any existing kit piece.

The actual build logic lives in `build_intersection_geometry()`, a plain function with no
`bpy.ops` dispatch of its own -- `RKA_OT_build_intersection.execute()` is a thin wrapper around
it, and so is `RKA_OT_insert_intersection_on_segment` (`ops_segment.py`). Calling this function
directly (instead of `bpy.ops.rka.build_intersection(...)`) from inside another operator's
`execute()` is what keeps a compound action (like "insert") a SINGLE undo step with a working F9
'Adjust Last Operation' panel -- a nested `bpy.ops.rka.X()` call pushes its own separate undo
step, and Blender's redo panel then shows that INNER operator's properties, not the outer one you
actually meant to tweak (arm name, split fraction, curb style, ...) -- this was the concrete cause
of "F9 doesn't work" and "curb style toggle doesn't work" after Extend/Insert.
"""
import math

import bpy

from . import custom_props, live_edit, paths
from . import spine_io
from .props import TRAFFIC_SIDE_ITEMS
import session_common as sc   # lib/ already on sys.path via paths.py, same import ops_world_session.py uses

_ik = None


def ik():
    """Lazy-import lib/intersection_kit.py (sys.path already set up by paths.py)."""
    global _ik
    if _ik is None:
        import intersection_kit as _mod
        _ik = _mod
    return _ik


class RkaBuildError(Exception):
    """Raised by build_intersection_geometry/build_segment_geometry for a hard failure BEFORE any
    geometry is created (bad input, e.g. malformed NWAY angles or an out-of-range lane_map) -- the
    calling operator reports it and returns CANCELLED. Export failures are different: geometry
    already exists by the time those run, so they're collected in the return dict's `warnings`
    list instead and the operator still returns FINISHED."""


def parse_lane_map(text):
    """Parse the 'Lane Map Override' mini-syntax into `lib/intersection_kit.py`'s `lane_map`
    dict shape: 'From>To:in-out,in-out; From2>To2:in-out' -> {(from,to): [(in,out), ...]}.
    Semicolon-separates arm-pair clauses; each clause is 'From>To' then ':' then comma-separated
    'in-out' index pairs. Blank/whitespace-only text -> None (no override, default i->i pairing
    everywhere -- unchanged behavior). Raises ValueError with the offending clause on malformed
    syntax, so a typo surfaces as an operator error instead of silently doing nothing."""
    text = (text or "").strip()
    if not text:
        return None
    result = {}
    for clause in text.split(";"):
        clause = clause.strip()
        if not clause:
            continue
        if ">" not in clause or ":" not in clause:
            raise ValueError("expected 'From>To:in-out,in-out' in %r" % clause)
        arms_part, pairs_part = clause.split(":", 1)
        frm, to = (s.strip() for s in arms_part.split(">", 1))
        pairs = []
        for p in pairs_part.split(","):
            p = p.strip()
            if not p:
                continue
            if "-" not in p:
                raise ValueError("expected 'in-out' (e.g. '0-1') in %r" % p)
            li, lo = p.split("-", 1)
            pairs.append((int(li.strip()), int(lo.strip())))
        if not pairs:
            raise ValueError("no lane pairs given for %r" % clause)
        result[(frm, to)] = pairs
    return result


CURB_STYLE_ITEMS = (
    ('NONE', "None (no curb)", "No curb geometry at all for this piece/side -- e.g. a rural "
     "shoulder, a merge zone, or a transition into open pavement with no curb wall"),
    ('PROFILE', "Profile (asset shape, continuous)", "Sweep the resolved kit piece's own real "
     "cross-section CONTINUOUSLY along the curve -- no discrete tiling, so no per-joint corner "
     "gap at all, even on a tight turn. Link the kit library first via 'Link Curb Kit Library', "
     "then set 'Curb Asset Piece' below"),
)
# 'BOX' and 'ASSET' retired (2026-08, user-requested: "remove the original box/asset while extend
# for curb/median/sidewalk (so only have none/profile) to simplify the code base"). PROFILE
# (`kit_common.curb_loop(curb_style='PROFILE')`, see its own docstring) supersedes BOTH: it sweeps
# the resolved kit piece's own real cross-section continuously, so it gives BOX's zero-seam
# behavior (no discrete tiling at all, unlike the OLD ASSET style, which left a real ~cm-scale gap
# on the outer edge of every corner joint -- a rigid-piece-on-a-curve geometric limit, not a bug,
# see `curb_asset_row`'s own docstring history) while ALSO carrying the chosen piece's own real
# silhouette (unlike the OLD flat-rectangle-only BOX style). `kit_common._curb_profile_object`'s
# BOX/GUTTER branches, and `ops_intersection.build_curb`'s ASSET (`curb_asset_row`) branch, are
# UNCHANGED CODE, kept as library primitives (`curb_asset_row` is still `median_merge.py`'s own
# chain-continuity mechanism, a genuinely different use case), not deleted, in case a future need
# resurfaces -- `build_curb`'s ASSET branch specifically is no longer reachable from any current
# build/rebuild path for CURB (the `if style == 'ASSET': build_curb(...) else: curb_loop(...)`
# split at every curb call site retired along with the picker option). Effect on an already-saved
# piece with a stale `rka_curb_l_style`/`rka_curb_r_style`/`rka_curb_style` value, discovered by
# direct headless verification against a synthetic old-style piece (NOT a symmetric claim across
# curb/median -- the two behave differently here, see below): a stored 'BOX'/'GUTTER' value keeps
# rendering EXACTLY as before, since `kit_common.curb_loop`'s own dispatch still recognizes both
# internally (its `else` branch calls `_curb_profile_object`, unchanged) -- the picker just stopped
# OFFERING them going forward, nothing about the geometry changes. A stored 'ASSET' value is
# different: `curb_loop` has no dedicated ASSET branch of its own, so it falls into that SAME
# `else` -> BOX-fallback path -- meaning an old ASSET-style curb now silently re-renders as a plain
# default-thickness BOX wall on its next rebuild (still real, visible geometry, just NOT the
# resolved kit piece's own shape anymore), not "no curb." Either way, the piece's Curb Style should
# be explicitly re-picked to 'Profile' to restore its ORIGINAL configured look -- the SAME "old
# value needs an explicit re-pick" precedent this exact enum already established for the earlier
# GUTTER retirement below, not a new convention.
#
# GUTTER was retired earlier (2026-08, user-reported: a real segment in world_session.blend showed
# a large gap between its sidewalk and its actual curb). Root cause, confirmed by direct
# measurement: `kit_common.gutter_curb_profile`'s cross-section is ONE-SIDED (road edge at local
# x=0 -> curb top at x=width), and the GN sweep's local-X direction is a FIXED physical direction
# for a given spine tangent -- so it can only ever be "outward" on ONE of the two curb lines (L or
# R) built from the SAME spine, and is silently "inward" (into the road) on the other, with
# nothing in this codebase compensating for it (unlike ASSET's `curb_asset_rot_offset_r=180`,
# built specifically to solve this exact L/R-flip problem for kit pieces). BOX's profile was
# symmetric, so it never had this bug. `kit_common.gutter_curb_profile`/`_curb_profile_object`'s
# GUTTER branch are UNCHANGED (still reachable by raw `curb_loop(curb_style='GUTTER', ...)` Python
# calls, and by any already-existing `rka_curb_l_style`/`rka_curb_r_style`/`rka_median_style`
# value of 'GUTTER' saved in old content) -- only the PICKER stops offering it going forward.
# Existing GUTTER content should be switched
# to 'Profile' by hand the next time that piece is touched.

# Median-only styles -- a SEPARATE enum from CURB_STYLE_ITEMS (not an extension of it): a median
# only ever needs "nothing" or "the resolved kit piece's own real shape, swept continuously along
# the centerline." 2026-08, user-requested ("only have none/profile... to simplify the code
# base"): 'ASSET' (a discrete repeated row, `curb_asset_row`) replaced by 'PROFILE' -- the SAME
# continuous-sweep mechanism `CURB_STYLE_ITEMS` uses (`kit_common.curb_loop(curb_style='PROFILE')`,
# see that function's own docstring), applied to the median's own spine instead of a corner/side
# boundary. Two example pieces ship in `kit/curb_kit.blend`: `Kit_Median_YellowSeparator` (flat
# painted divider) and `Kit_Median_Island` (raised barrier) -- pick either via 'Median Asset
# Piece' after linking the library. `kit_common.swept_profile_between`/`MEDIAN_PROFILES` (an
# EARLIER, now-unused procedural silhouette system, predates even the retired ASSET-row approach)
# stay in `kit_common.py`, unused by this picker -- kept as a library primitive, not deleted. An
# already-saved piece with `rka_median_style` still set to 'ASSET' (or an older procedural value)
# is simply inert until the piece's Median Style is explicitly re-picked to 'Profile' -- the SAME
# "old value goes inert, re-pick required" precedent this exact enum already established for the
# earlier BOX/GUTTER/ASSET-dual/SINGLE-procedural collapse, not a new convention.
MEDIAN_STYLE_ITEMS = (
    ('NONE', "None", "No median mesh at all -- just the gap distance (Median Width), a flush "
     "painted boundary between the lane markings"),
    ('PROFILE', "Profile (asset shape, continuous)", "RECOMMENDED. Sweep ONE kit-library piece's "
     "own real cross-section continuously along the median's own centerline -- e.g. "
     "'Kit_Median_YellowSeparator' (flat painted divider) or 'Kit_Median_Island' (raised "
     "barrier). Link the library first via 'Link Curb Kit Library', then set 'Median Asset "
     "Piece' below"),
)


def _resolve_curb_asset(name):
    """A linked/appended kit/curb_kit.blend Collection name -> its one PRIMARY mesh Object, or
    None if the name is blank/unresolvable (caller must warn and skip -- never silently crash a
    build or a live-edit rebuild).

    Prefers the piece's own recorded `rka_curb_asset_object` (`tools/build_curb_kit.py` stamps
    this to the exact mesh name a multi-part piece's collection was built around, e.g.
    `kit_curb_street_lamp_l1m`, NOT its `_Pole`/`_Arm`/`_Post`/`-colonly` helper meshes) -- 2026-08,
    user-reported: "the lamp/street lamp seem never show up" and traffic lights "not generate...
    even when set." Root cause (confirmed via direct headless inspection): the OLD fallback
    ("first MESH object found in the collection", Blender's own link order) silently resolved
    every multi-part piece to whichever sub-mesh happened to be linked FIRST -- for
    `Kit_Curb_StreetLamp_L1`/`Kit_TrafficLight_L1` that's the bare support pole (built before the
    decorated head/arm in `tools/build_curb_kit.py`'s own function bodies), and for
    `Kit_Curb_FencePost_L1` its plain post instead of the railed piece -- so every one of these
    "worked" in the sense of placing SOME geometry, just an easy-to-miss stub, reading as "nothing
    was generated." Falls back to the old first-mesh rule when the property is absent (a
    hand-authored collection, or a kit library built before this fix) so single-mesh pieces are
    unaffected either way."""
    if not name:
        return None
    coll = bpy.data.collections.get(name)
    if coll is None:
        return None
    primary_name = coll.get("rka_curb_asset_object")
    if primary_name:
        obj = coll.objects.get(primary_name)
        if obj is not None and obj.type == 'MESH':
            return obj
    return next((o for o in coll.objects if o.type == 'MESH'), None)


_ASSET_PICKER_NONE = "NONE"   # EnumProperty item identifier for "clear this picker" -- Blender
                              # enum identifiers must be non-empty, so this sentinel (never a real
                              # collection name -- `bpy.data.collections.new` rejects an all-caps
                              # 'NONE' colliding with a real kit piece is not a realistic authoring
                              # accident) stands in for the blank-string custom-property value
                              # every "ASSET + no piece = nothing" convention in this addon expects.


def linked_asset_picker_items(self, context):
    """Dynamic `EnumProperty` items for an asset-piece DROPDOWN (`layout.operator_menu_enum`):
    every LOCAL collection carrying `rka_curb_asset_length` (the marker every real kit/
    curb_kit.blend piece stamps -- see `tools/build_curb_kit.py`) plus a leading 'None' entry.
    2026-08, user-requested: "is it possible to also do drop down selection on asset or none,
    instead of current 'Set' and try use the op[era]tional panel and seem not unset/remove
    completely" -- the OLD text-typed `collection_name` (only editable via Blender's F9 'Adjust
    Last Operation' panel, easy to miss/mistype, with no discoverable way to clear it back to
    blank) is replaced by this real dropdown everywhere an asset piece is picked. Clearing DOES
    already correctly remove the built geometry on the next rebuild (`clear_generated_mesh_objects`
    unconditionally deletes every `sidewalk_*`/`prop_*`/`trafficlight_*`/ASSET-style `curb_*`
    object up front, and nothing rebuilds one when the resolved asset is `None`) -- the missing
    piece was purely a discoverable way to GET to blank, not a cleanup bug.

    Sorted by name for a stable, predictable menu. Must return a list each call (a Blender
    requirement for dynamic enum callbacks, and the returned tuples must stay valid for the
    callback's own lifetime -- plain `str`s already satisfy that). Deliberately does NOT filter by
    `c.library` -- unlike a piece collection (always LOCAL, hand-authored per-file), a real kit
    piece is normally LIBRARY-LINKED from `kit/curb_kit.blend` (`RKA_OT_link_curb_kit_library`),
    so excluding linked collections here would exclude every real piece -- confirmed the direct
    cause of an early version of this function returning an empty dropdown ('NONE' only) even
    right after linking the library."""
    names = sorted(c.name for c in bpy.data.collections if "rka_curb_asset_length" in c.keys())
    items = [(_ASSET_PICKER_NONE, "None", "Clear -- no asset piece (removes any built geometry)")]
    items += [(n, n, "") for n in names]
    return items


def _asset_picker_value(enum_value):
    """The stored custom-property value for a `linked_asset_picker_items` selection -- '' (this
    addon's universal 'no asset' convention) for the `_ASSET_PICKER_NONE` sentinel, else the
    chosen collection name unchanged."""
    return "" if enum_value == _ASSET_PICKER_NONE else enum_value


def build_curb(name, pts3, coll, style, height, thickness, asset_obj=None, asset_spacing=3.0,
                asset_rot_offset=0.0):
    """Dispatch on `curb_style`: 'NONE' -> no geometry at all (returns None, caller must skip it);
    'ASSET' -> repeat `asset_obj` along `pts3` at `asset_spacing` m intervals
    (`kit_common.curb_asset_row`; returns None if `asset_obj` wasn't resolved -- the caller
    already warned); 'BOX' -> the original flat `swept_wall`; 'GUTTER' -> a curb-and-gutter
    cross-section (`swept_profile` + `gutter_curb_profile`) swept along the same exact points.
    Shared by `ops_segment.build_segment_geometry` (intersections build curbs via
    `kit_common.curb_loop`/`curb_asset_row` directly instead -- see `_populate_intersection_mesh`)."""
    if style == 'NONE':
        return None
    if style == 'ASSET':
        if asset_obj is None:
            return None
        return paths.kc.curb_asset_row(name, pts3, coll, asset_obj, asset_spacing, asset_rot_offset)
    if style == 'GUTTER':
        return paths.kc.swept_profile(
            name, pts3, paths.kc.gutter_curb_profile(thickness, height), coll, matkey="concrete")
    return paths.kc.swept_wall(name, pts3, h=height, coll=coll, matkey="concrete",
                                thickness=thickness, z0=0.0)


def join_meshes(context, objs, name):
    """Join a list of freshly-created, already-linked-into-the-view-layer Objects into ONE mesh
    Object -- the "let the intersection mesh be one mesh" request: separate curb/pad/ribbon pieces
    are convenient to generate (and independently colour/debug during authoring), but a single
    combined mesh is what actually gets handed to Godot/an artist for export. A 0- or 1-object list
    is a no-op (just a rename, so callers can unconditionally use the returned object's name).

    Any non-Mesh object (e.g. `kit_common.junction_pad`/`curb_loop`'s Curve objects, whose actual
    visible geometry comes from a live Nodes modifier) is converted to a real Mesh datablock first
    (`bpy.ops.object.convert`, which bakes the modifier's evaluated output and removes it) --
    `bpy.ops.object.join()` itself can't combine mixed Curve/Mesh types, and joining a Curve
    object's own un-evaluated control points (instead of its GN-modifier mesh output) would silently
    join the wrong geometry."""
    if not objs:
        return None
    if len(objs) == 1:
        obj = objs[0]
        if obj.type != 'MESH':
            for o in context.selected_objects:
                o.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
            bpy.ops.object.convert(target='MESH')
            obj.select_set(False)
        obj.name = name
        return obj
    for o in context.selected_objects:
        o.select_set(False)
    for o in objs:
        if o.type != 'MESH':
            o.select_set(True)
            context.view_layer.objects.active = o
            bpy.ops.object.convert(target='MESH')
            o.select_set(False)
    for o in objs:
        o.select_set(True)
    context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    joined = context.view_layer.objects.active
    joined.name = name
    joined.select_set(False)
    return joined


def clear_generated_mesh_objects(coll, keep_gn_boundaries=False):
    """Remove every curb_*/pad_*/pave_*/lanecl_*/ribbon_*/mesh_*/sidewalk_*/prop_*/trafficlight_*/
    trafficgantry_* object (+ its now-orphaned mesh/curve data) from `coll`, leaving marker Empties
    (arm_*/segend_*/segbend_*) untouched. The
    "delete the old generated geometry, keep the live-edit drag handles" step shared by both
    in-place rebuild paths (`rebuild_intersection_in_place`, `ops_segment.rebuild_segment_in_place`).
    `pave_*` is the pavement collision proxy (`kit_common.colonly_swept_between`) -- without it in
    this list, a rebuild would leave the old one orphaned and pile up a new one on every drag.

    `keep_gn_boundaries` (2026-08, the crash-surface fix): when True, an object identified as one
    of these update-in-place-capable kinds is SPARED here but stamped `_rka_touched = False`
    instead of `True` -- a "provisionally kept, prove yourself" mark, not an unconditional keep:
      1. a `_poly_curve_with_radius`-built boundary curve -- has a "Pad" or "Curb" GN modifier.
      2. a collision proxy -- name ends `-colonly` AND carries `proxy_for` (so this can never
         accidentally spare an unrelated mesh that merely happens to share the suffix). Covers
         both the export-time GN proxies (`colonly_mesh_evaluated`) AND the legacy point-segment
         path's own live pavement proxy (`colonly_swept_between`/`colonly_swept`) -- both stamp
         `proxy_for`, so no separate condition is needed for the legacy one.
      3. an ASSET-style curb instancer -- name starts with `curb_` (this addon's curb/median
         ASSET-row naming, see `curb_asset_row`'s callers) AND has a "GN" modifier; deliberately
         NOT any other `prop_`/`sidewalk_` instancer, which haven't been verified safe to spare.
      4. a `lanecl_*` lane-centerline data curve (`poly_curve`) -- plain CURVE type.
      5. a `mark_*` lane-marking mesh (`marking_ribbon`) -- plain MESH type.
      6. a legacy BOX/GUTTER-style curb wall (`swept_wall`/`swept_profile`, the point-segment
         path's own curb, e.g. `curb_L`/`curb_R`) -- name starts with `curb_` AND is a plain MESH
         with NO "GN" modifier (distinguishes it from #3's ASSET instancer, which always has one,
         and from a GN-based `curb_loop` object, which is a CURVE with a "Curb" modifier and
         already matches #1).
      7. a `ribbon_*` legacy pavement strip (`flat_ribbon`) -- plain MESH type.
    Every update-in-place builder (`junction_pad`/`curb_loop`/`colonly_mesh_evaluated`/
    `instancer`/`poly_curve`/`marking_ribbon`/`swept_wall`/`swept_profile`/`flat_ribbon`/
    `colonly_swept`) re-stamps `_rka_touched = True` on whichever object it actually reuses or
    creates this pass. The catch this closes: a count that can SHRINK between two rebuilds (fewer
    lanes -> fewer `lanecl_*`, median width dropped to 0 -> its curb objects never regenerated,
    curb style switched away from ASSET) previously would have left the now-unwanted old object
    behind forever, since nothing ever calls its builder again to delete it.
    `sweep_untouched_boundaries` (called by the rebuild function AFTER population finishes)
    deletes anything still `_rka_touched == False` -- provisionally spared here, never
    reconfirmed, so genuinely stale. Callers that pass `keep_gn_boundaries=True` only ever do so
    from the live-drag hot path (`rebuild_intersection_in_place`/`rebuild_segment_gn_in_place`/
    `ops_segment.rebuild_segment_in_place`), and MUST call `sweep_untouched_boundaries` afterward
    or stale objects leak; every other caller keeps the unconditional-delete default and never
    needs the sweep."""
    prefixes = ("curb_", "pad_", "pave_", "lanecl_", "ribbon_", "mesh_", "mark_", "sidewalk_",
                "prop_", "trafficlight_", "trafficgantry_")
    for obj in list(coll.objects):
        if not obj.name.startswith(prefixes):
            continue
        if keep_gn_boundaries and (
                obj.modifiers.get("Pad") is not None or obj.modifiers.get("Curb") is not None
                or (obj.name.endswith("-colonly") and obj.get("proxy_for") is not None)
                or (obj.name.startswith("curb_") and obj.modifiers.get("GN") is not None)
                or (obj.name.startswith("lanecl_") and obj.type == 'CURVE')
                or (obj.name.startswith("mark_") and obj.type == 'MESH')
                or (obj.name.startswith("curb_") and obj.type == 'MESH'
                    and obj.modifiers.get("GN") is None)
                or (obj.name.startswith("ribbon_") and obj.type == 'MESH')):
            obj["_rka_touched"] = False
            continue
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and data.users == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Curve):
                bpy.data.curves.remove(data)


def sweep_untouched_boundaries(coll):
    """The other half of `clear_generated_mesh_objects(coll, keep_gn_boundaries=True)`: delete
    any surviving-by-default object still stamped `_rka_touched == False` -- provisionally spared
    by that call, but its builder was never called again this pass to reconfirm it (a shrunk lane/
    median/curb-style count, see that function's docstring). Call this ONCE, after population
    fully finishes, from every rebuild function that passed `keep_gn_boundaries=True`."""
    for obj in list(coll.objects):
        if obj.get("_rka_touched") is False:
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data is not None and data.users == 0:
                if isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)
                elif isinstance(data, bpy.types.Curve):
                    bpy.data.curves.remove(data)


def active_marker_position(context):
    """If the active object is one of this addon's marker Empties (`rka_arm_name`/`rka_segend`/
    `rka_segbend`/`rka_port` -- the last being a plain GN segment's end-of-road click target, see
    `ops_segment._place_segment_ports`), return `((x, y), z_raw, parent_coll)` so a NEW piece can
    be built starting exactly there instead of at the 3D cursor -- `z_raw` is already converted
    back to the pre-`lane_surface_z` convention every `build_*_geometry` function expects, and
    `parent_coll` is the marker's own piece's parent (so the new piece lands as a SIBLING of it).
    This is the fix for "Build Intersection always uses the cursor, not wherever the
    segment/arm/port I just selected actually is" -- callers fall back to the 3D cursor when this
    returns None (no marker is the active object)."""
    obj = context.active_object
    if obj is None or not obj.users_collection:
        return None
    keys = obj.keys()
    if ("rka_arm_name" not in keys and "rka_segend" not in keys and "rka_segbend" not in keys
            and "rka_port" not in keys):
        return None
    rka = context.scene.rka
    loc = obj.location
    return ((loc.x, loc.y), loc.z - rka.lane_surface_z, parent_collection_of(obj.users_collection[0]))


def arm_or_port_anchor(context):
    """If the active object is an `arm_*` (intersection) or `port_A`/`port_B` (plain segment)
    marker, return `(pos_xy, z_raw, heading_deg, lanes_forward, lanes_backward, parent_coll)` --
    everything `RKA_OT_build_intersection`/`RKA_OT_build_lane_transition` need to anchor a NEW
    piece exactly where AND facing the way this marker does, with matching lane counts, instead of
    only picking up position the way `active_marker_position` does. None if the active object is
    neither kind of marker (callers fall back to their normal cursor/manual-property behavior).

    `heading_deg` always points OUTWARD, away from the source piece (`Arm.angle_deg`'s own
    convention, and `rka_port_heading_deg`'s) -- a straight piece continuing forward from here
    should face this heading directly; an intersection anchored here needs to place one of ITS OWN
    arms facing BACK at `heading_deg + 180` instead, since an intersection's `arm_*` tips sit away
    from its own center, not at it (see `RKA_OT_build_intersection.execute()`).

    `lanes_forward`/`lanes_backward` mirror the oneway-aware resolution `RKA_OT_extend_from_arm`
    already uses for an arm (an 'IN'-only arm has 0 lanes_forward, asymmetric `lanes_out` wins over
    the symmetric count when set), or the segment's own `rka_lanes`/`rka_lanes_backward` for a
    port (same as `RKA_OT_extend_from_port`) -- so a piece built here can seed itself with the
    source's actual lane counts instead of a generic default."""
    obj = context.active_object
    if obj is None or not obj.users_collection:
        return None
    coll = obj.users_collection[0]
    rka = context.scene.rka
    loc = obj.location
    pos_xy, z_raw = (loc.x, loc.y), loc.z - rka.lane_surface_z
    parent_coll = parent_collection_of(coll)
    if "rka_arm_name" in obj.keys():
        arms = custom_props.read_arms(coll)
        match = next((a for a in (arms or []) if a[0] == obj["rka_arm_name"]), None)
        if match is None:
            return None
        _, angle_deg, arm_lanes, arm_lanes_out = match
        oneway = obj.get("rka_arm_oneway", "") or None
        forward_lanes = arm_lanes_out if arm_lanes_out > 0 else arm_lanes
        lanes_forward = 0 if oneway == 'IN' else forward_lanes
        lanes_backward = 0 if oneway == 'OUT' else arm_lanes
        return pos_xy, z_raw, angle_deg, lanes_forward, lanes_backward, parent_coll
    if "rka_port" in obj.keys():
        heading_deg = obj.get("rka_port_heading_deg", 0.0)
        lanes_forward = coll.get("rka_lanes", 1)
        lanes_backward = coll.get("rka_lanes_backward", lanes_forward)
        return pos_xy, z_raw, heading_deg, lanes_forward, lanes_backward, parent_coll
    return None


def local_collection(name):
    """`bpy.data.collections[name]`, but skipping any READ-ONLY LINKED collection sharing that
    name -- mirrors `kit_common.get_coll()`'s own `c.library is None` filter, which the rest of
    the pipeline (`kit_common.get_coll`, `tools/link_neighbors.py`'s `_local_coll`) already relies
    on for the same reason: Blender's own duplicate-name auto-suffixing (`Segment_001.001`) only
    applies WITHIN local data, so a linked library's collection CAN carry the exact bare name a
    local one also uses, with no rename. This addon's own deterministic auto-naming
    (`Intersection_<preset>_%03d`, `Segment_%03d`, `Transition_%03d`) makes that collision likely
    the moment another road_kit_authoring-authored file is linked in read-only (neighbor-district
    reference while authoring a cross-district network, or two independently-built files sharing
    numbering) -- an unqualified `bpy.data.collections.get(name)` can then silently resolve onto
    the wrong (linked) collection instead of the local one being edited, and a rebuild attempt on
    it either raises (mutating library data) or silently misfires. Returns None if no LOCAL
    collection has this name (unlike `kit_common.get_coll`, never creates one -- this is a
    resolve-my-own-piece helper, not a get-or-create one)."""
    return next((c for c in bpy.data.collections if c.name == name and c.library is None), None)


def local_object(name):
    """Same as `local_collection` but for `bpy.data.objects` -- see its docstring. Used for
    by-name object lookups (a piece's own spine curve, an arm marker) that must resolve to the
    LOCAL object even when a linked file's same-named object is also present."""
    return next((o for o in bpy.data.objects if o.name == name and o.library is None), None)


def parent_collection_of(coll, root=None):
    """Walk the collection hierarchy from `root` (default: the current scene's root collection)
    to find whichever collection directly contains `coll` as a child -- Blender's Collection API
    has no direct '.parent' pointer. Used so a piece built FROM an existing one (extend-from-arm,
    insert-on-segment) lands as a SIBLING of it, not nested inside it. Falls back to `root` itself
    if `coll` isn't found nested anywhere."""
    root = root or bpy.context.scene.collection

    def search(node):
        for child in node.children:
            if child == coll:
                return node
            found = search(child)
            if found is not None:
                return found
        return None

    return search(root) or root


PRESET_ITEMS = (
    ('4WAY', "4-way", "Four arms, evenly spaced 90 deg apart -- 4 filleted corners"),
    ('3WAY_T', "3-way (T, direct through)", "Two collinear arms (through street -- straight, no "
     "fillet needed there) plus one side arm -- 2 filleted corners"),
    ('3WAY_Y', "3-way (Y, all turns)", "Three arms at generic angles, no through-street -- every "
     "movement is a turn, all 3 corners filleted"),
    ('NWAY', "N-way (custom angles)", "Any number of arms at arbitrary angles -- set via "
     "'Arm Angles' (comma-separated degrees, e.g. '0,60,130,200,280')"),
)


def _arm_lane_list(lanes, lane_arm_overrides, n):
    """`lanes` (a single scalar) applied to every arm, UNLESS one of the `lane_arm_overrides`
    (0 = "use the default") is set, in which case a list is built so each arm gets its own count
    -- e.g. a 2-lane main street crossing a 1-lane side street."""
    overrides = list(lane_arm_overrides) + [0] * max(0, 4 - len(lane_arm_overrides))
    if not any(overrides[:min(n, 4)]):
        return lanes
    return [overrides[i] if i < 4 and overrides[i] > 0 else lanes for i in range(n)]


def _populate_intersection_mesh(context, coll, arms, kerb_radius, tail_length, segments,
                                 lane_width, curb_style, curb_height, curb_thickness, lane_map,
                                 join_visual_mesh, origin_xy, z, curb_asset_obj=None,
                                 curb_asset_spacing=3.0, curb_asset_rot_offset=0.0,
                                 sidewalk_width=0.0, sidewalk_height=0.15, sidewalk_asset_obj=None,
                                 sidewalk_asset_spacing=2.0, traffic_light_obj=None):
    """Build the pad + curb + lane-centerline objects for one intersection INTO `coll` (already
    created/linked) and return `(boundary, movements, visual_objs)`. Shared by
    `build_intersection_geometry` (fresh build, also creates the arm_* marker Empties afterward)
    and `rebuild_intersection_in_place` (live-edit rebuild, keeps the existing markers) so the two
    paths can never drift apart -- exactly the same geometry math either way.

    Visual pavement is ONE `kit_common.junction_pad` (GN-backed, Fillet Curve + Fill Curve) from
    `intersection_kit.build_junction_boundary` (the FULL closed footprint, arm tail-caps included)
    -- purely a function of arm angles/widths, never of which lane movements happen to exist,
    which is what fixes the old "widen an arm -> curb moves but pavement has a gap" bug (the pad
    used to be the union of thin per-movement ribbons, capped at `min(a.lanes, b.lanes)` between
    arm pairs). Curb is ONE `kit_common.curb_loop(closed=False)` object PER CORNER, from
    `intersection_kit.build_junction_curb_segments` -- deliberately narrower than the pad's
    boundary: it excludes every arm's own tail-cap (a road can't have a curb wall across its own
    lanes where it enters the junction) and every through-pair (no wall needed where a road just
    continues straight). `lanecl_*` lane-centerline data curves (the AI/export layer) are
    untouched -- still one per legal movement from `build_lane_movements`, still what
    `export_json` reads.

    `tail_length` is floored to `intersection_kit.recommended_tail_length(arms, kerb_radius,
    start=tail_length)` before anything else uses it -- never shrinks the requested value (the
    search starts from it), only raises it for wide (3-4 lane) arms where the requested
    tail_length would otherwise leave some turn's own arc stranded well past the pad (see that
    function's docstring for why this needs a numerical search, not a formula). Both the pad/curb
    boundary and the lane movements use this SAME effective value, so they never disagree."""
    k = ik()
    tail_length = k.recommended_tail_length(arms, kerb_radius, start=tail_length)
    try:
        movements = k.build_lane_movements(arms, kerb_radius, segments, tail_length=tail_length,
                                            lane_map=lane_map)
    except ValueError as exc:
        raise RkaBuildError("Lane Map Override: %s" % exc)
    boundary = k.build_junction_boundary(arms, kerb_radius, tail_length=tail_length)
    curb_segments = k.build_junction_curb_segments(arms, kerb_radius, tail_length=tail_length)

    cx, cy = origin_xy

    def to3(pt2):
        return (cx + pt2[0], cy + pt2[1], z)

    def to3r(pt3):
        return (cx + pt3[0], cy + pt3[1], z, pt3[2])

    boundary3 = [to3r(p) for p in boundary]

    # Short, collection-relative names -- Blender's Outliner already nests these under their
    # collection (which itself carries the full junction_id), and nothing downstream parses these
    # specific names (WorldBaker's prefix table doesn't include curb_/pad_/lanecl_/arm_ at all --
    # every Godot-side lookup goes through the exported JSON's own `id`).
    # Read directly off `coll` (not threaded as a parameter, unlike curb_style etc.) -- both
    # build_intersection_geometry (fresh build, property absent -> the same "asphalt"/"concrete"
    # default as before) and rebuild_intersection_in_place (live-edit rebuild, coll already has
    # whatever RKA_OT_set_piece_matkey last set) read the SAME live value with zero signature
    # changes, and a fresh build's default behavior is unchanged. See RKA_OT_set_piece_matkey
    # (2026-07-28, user-reported: material was a hardcoded literal, no way to change it after the
    # initial build at all -- not even via F9, there was no exposed property anywhere).
    pad_matkey = coll.get("rka_pad_matkey", "asphalt")
    curb_matkey = coll.get("rka_curb_matkey", "concrete")

    visual_objs = []   # pad + curb(s) only -- fed to gltf_export_path / join_visual_mesh
    pad = paths.kc.junction_pad("pad_%s" % coll.name, boundary3, coll, matkey=pad_matkey,
                                 segments=segments)
    if pad is not None:
        visual_objs.append(pad)
        # `-colonly` collision proxy no longer baked here (2026-08) -- zero authoring-time value,
        # moved to export-time (`kit_common.bake_colonly_proxies`, called from
        # `tools/export_world.py`) as the single most expensive/crash-prone live rebuild op.
    # One curb object PER CORNER (build_junction_curb_segments already excludes every arm's own
    # tail-cap and every through-pair -- an arm opening must never have a curb wall across its own
    # lanes) instead of a single loop spanning the whole boundary.
    for idx, seg in enumerate(curb_segments):
        seg3 = [to3r(p) for p in seg]
        name = "curb_%s_%d" % (coll.name, idx)
        # Both styles (NONE/PROFILE) go through this ONE `curb_loop` call -- the old
        # `if curb_style == 'ASSET': build_curb(...) else: ...` split retired with the ASSET style
        # itself (2026-08, "only have none/profile... to simplify the code base"; `curb_asset_obj`
        # matters only for PROFILE, harmless/unused for NONE -- see `curb_loop`'s own docstring).
        # `-colonly` collision proxy no longer baked here -- see the pad's matching comment above;
        # `bake_colonly_proxies` picks up every "Curb"-modifier object generically.
        curb = paths.kc.curb_loop(name, seg3, coll,
                                   curb_style=curb_style, curb_height=curb_height,
                                   curb_thickness=curb_thickness, matkey=curb_matkey,
                                   segments=segments, closed=False, asset_obj=curb_asset_obj)
        if curb is not None:
            visual_objs.append(curb)

    # `lanecl_*` lane-centerline curves are no longer built here (2026-08): confirmed export-
    # redundant -- `tools/save_lane_kit.py` recomputes lane centerlines directly from `movements`/
    # spine + `rka_*` metadata, never from these live objects -- and they carried no visual mesh
    # of their own, so they added live-edit object-churn cost with zero authoring-time payoff.
    # See `traffic_viz.py`'s per-lane tag overlay for the viewport-visible replacement.

    # Sidewalk (see `_populate_intersection_sidewalks`'s own docstring) -- one strip per CORNER,
    # the same segmentation the curb wall itself uses. No-op (empty list) when off.
    curb_clearance = paths.kc.curb_outer_clearance(curb_style, curb_thickness, curb_asset_obj)
    visual_objs += _populate_intersection_sidewalks(
        coll, arms, kerb_radius, tail_length, segments, z, origin_xy, sidewalk_width,
        sidewalk_height, curb_matkey, sidewalk_asset_obj, sidewalk_asset_spacing,
        curb_clearance=curb_clearance)

    # Traffic lights (see `_populate_intersection_traffic_lights`'s own docstring) -- one PER ARM
    # that has it enabled, not a spaced row. No-op (empty list) if no kit piece is set or no arm
    # has it enabled.
    visual_objs += _populate_intersection_traffic_lights(
        coll, arms, kerb_radius, tail_length, z, origin_xy, traffic_light_obj)

    if join_visual_mesh and visual_objs:
        joined = join_meshes(context, visual_objs, "mesh_%s" % coll.name)
        visual_objs = [joined] if joined else visual_objs

    return boundary, movements, visual_objs, tail_length


def _arm_neighbors(arms):
    """Map each arm name -> (prev_arm, next_arm) in the same angular (CCW) order
    `consecutive_pairs` uses for corner-fillet pairs -- so an arm's OUT-side corner is always the
    pair (this arm, next arm) and its IN-side corner the pair (prev arm, this arm), matching
    `build_junction_curb_segments`'s own per-corner convention exactly (see
    `_populate_intersection_traffic_lights`, which needs a specific arm's own corner rather than
    iterating pairs directly)."""
    ordered = sorted(arms, key=lambda a: a.angle_deg)
    n = len(ordered)
    return {ordered[i].name: (ordered[(i - 1) % n], ordered[(i + 1) % n]) for i in range(n)}


def _populate_intersection_sidewalks(coll, arms, kerb_radius, tail_length, segments, z, origin_xy,
                                      sidewalk_width, sidewalk_height, matkey,
                                      sidewalk_asset_obj, sidewalk_asset_spacing,
                                      curb_clearance=0.0):
    """One sidewalk strip PER CORNER -- the SAME segmentation the curb wall itself uses
    (`intersection_kit.build_junction_curb_segments`, unchanged except for its new `extra_offset`
    param), just pushed further out. 2026-08, user-reported (against real content,
    `world_session.blend`): a PRIOR per-arm-per-side approximation ("one strip per arm's own
    IN/OUT edge, running from an approximated near-corner point out to the tail cap") produced a
    "strange half bake" at the ends and, worse, didn't follow the pad's own curve at all -- "the
    original curb following alignment is working better... should use original curb logic for
    intersection, and side[walk] will just be bigger side[walk] mesh along the curve, instead of
    per way." This IS that: literally the curb's own corner-following logic (follows the pad's
    curve, automatically skipped at every arm's own tail-cap opening and every through-pair,
    exactly like the curb already is), offset outward -- so a sidewalk can never disagree with the
    curb it sits flush against, by construction, since both now come from the same function.

    The corner-segment LINE itself is offset by `curb_clearance + sidewalk_width / 2` (its
    CENTERLINE, since `curb_loop`'s BOX profile -- and `curb_asset_row`'s tiled pieces -- straddle
    whatever line they're given, same convention `ops_segment._populate_segment_mesh_gn`'s own
    sidewalk offset already uses), not `sidewalk_width` alone -- an earlier version of this
    function used the bare width, which left a `sidewalk_width / 2` GAP between the curb's own
    outer edge and the sidewalk's near edge. `curb_clearance` (see
    `kit_common.curb_outer_clearance`, shared with the segment path) is how far the curb wall
    itself already extends past the boundary line -- 0 for a plain BOX curb at this call site
    (curb_thickness's own half is already folded into `curb_clearance` by that shared function),
    nonzero for an ASSET curb whose real kit-mesh footprint extends further.

    `sidewalk_asset_obj` (optional) switches each corner strip from a procedural `curb_loop`(BOX)
    sweep to a `curb_asset_row` of a real kit piece (e.g. `Kit_Curb_SidewalkTile_L2`) -- 2026-08,
    user-requested: "will it be simpler and easily to regenerate all curb/side way from asset...
    just follow the asset library ones" -- mirrors the curb/median ASSET branches exactly. Falls
    back to the procedural sweep when no asset is set. No-op (returns an empty list immediately)
    when the sidewalk is off, matching every other optional-geometry block in this addon. The
    lamp/prop row that used to live here has moved to `_populate_intersection_traffic_lights` -- a
    per-arm signal, not a spaced row (see its own docstring for why).

    `centerline_offset`'s own `sidewalk_width` term uses the resolved ASSET piece's REAL measured
    width (`kit_common.asset_row_width`) instead of the configured `sidewalk_width` dial whenever
    `sidewalk_asset_obj` is set -- 2026-08, user-reported: an ASSET sidewalk read as broken/
    misaligned against real content (`world_session.blend`'s own intersection: `sidewalk_width`
    configured to 3.5m against a `Kit_Curb_SidewalkTile_L2` piece that's actually a fixed 3.0m
    wide). Using the dial value here placed the tile's centerline 0.25m further out than its own
    half-width reaches, opening a real gap at the curb side (and an unexplained overhang on the
    far side) -- see `asset_row_width`'s own docstring for the full root-cause writeup, shared
    verbatim with the segment path's identical fix (`ops_segment._sidewalk_offset_width`)."""
    if sidewalk_width <= 0.0:
        return []
    k = ik()
    cx, cy = origin_xy
    effective_width = (paths.kc.asset_row_width(sidewalk_asset_obj)
                        if sidewalk_asset_obj is not None else sidewalk_width)
    centerline_offset = curb_clearance + effective_width / 2.0
    corner_segments = k.build_junction_curb_segments(arms, kerb_radius, tail_length,
                                                       extra_offset=centerline_offset)
    # 2026-08, user-requested ("only have none/profile... to simplify the code base"): collapsed
    # from procedural-BOX/discrete-ASSET-tiling down to one CONTINUOUS curb_loop(PROFILE) sweep
    # per corner -- see `ops_segment._populate_segment_mesh_gn`'s matching sidewalk comment for
    # the full rationale (identical here, corner vs. straight run).
    visual = []
    for idx, seg in enumerate(corner_segments):
        seg3 = [(cx + p[0], cy + p[1], z, p[2]) for p in seg]
        name = "sidewalk_%s_%d" % (coll.name, idx)
        sw = paths.kc.curb_loop(name, seg3, coll, curb_style='PROFILE', curb_height=sidewalk_height,
                                 curb_thickness=sidewalk_width, matkey=matkey, segments=segments,
                                 closed=False, asset_obj=sidewalk_asset_obj)
        if sw is not None:
            visual.append(sw)
    return visual


# Diagonal offset (m) beyond the curb corner a fresh arm's traffic light sits at by default --
# "about 3 meter[s]" per the user's own worked example, adjustable per arm afterward (see
# `RKA_OT_adjust_arm_traffic_light_radius`).
TRAFFIC_LIGHT_DEFAULT_RADIUS = 3.5


def _populate_intersection_traffic_lights(coll, arms, kerb_radius, tail_length, z, origin_xy,
                                           traffic_light_obj):
    """One traffic-light prop PER ARM -- replaces the old spaced prop-row (2026-08, user-
    requested: "remove the lamp logic for intersection, but rather leave called 'traffic light'
    where if enable, will try to propose at the 45 degree outside of c[u]rb about 3 meter
    location... so traffic light is position[ed] at approximate equivalent logic in [] each
    intersection side, and able to adjust each ['light']... the lamp is per arm (as each arm is
    going/incoming)"). Only arms with `Arm.traffic_light` enabled get one (off by default on every
    arm, same as `median_width` -- toggle it on a specific arm via
    `RKA_OT_toggle_arm_traffic_light`). No-op immediately if no kit piece is set.

    Position: this arm's own OUT-side corner (the same TRUE corner `_populate_intersection_
    sidewalks` now uses, between this arm and its CCW neighbor), offset further out RADIALLY FROM
    THE JUNCTION'S OWN CENTER by `Arm.traffic_light_radius` meters PLUS that corner's own fillet
    radius -- i.e. diagonally outside the curb, set back from both the roadway and the corner,
    matching a real-world signal pole. Falls back to a synthetic corner (`kerb_radius` out along
    the arm, at the OUT lateral offset) for a through-pair arm with no real fillet corner on that
    side.

    2026-08, user-reported (against `world_session.blend`'s real, non-symmetric arm angles --
    342.35/73.24/160.11/245.50 deg, none exactly 90 deg apart): the light sat outside the curb for
    some arms but not others. Root cause, confirmed by direct measurement (headless, comparing
    each candidate formula's distance to the ACTUAL evaluated curb mesh): the OLD direction --
    `normalize(this arm's own direction + its own lateral perpendicular)` -- is only a good
    approximation of the corner's true outward bisector when the two arms meeting there happen to
    be ~90 deg apart (the historical default-preset case); on a hand-tuned intersection it can be
    off by several degrees, and worse, it entirely ignored the corner's own FILLET RADIUS (already
    computed by `_junction_corner_vertex`, previously discarded here) -- a corner between two wide
    (multi-lane) arms rounds with a much bigger radius (measured: 1.1-10.4m across this one real
    intersection's 4 corners) than the flat `Arm.traffic_light_radius` (3.5m default) accounts
    for, so a wide corner's own curb arc can bulge out far enough to leave barely any real
    clearance. Fixed with a formula that's correct for ANY corner shape without needing a
    per-corner bisector at all: since a junction's own footprint is convex-ish AROUND ITS CENTER,
    the vector from that center THROUGH the corner vertex, extended outward, is unambiguously
    'away from the junction' regardless of how far that corner's own angle deviates from 90 deg --
    and adding the corner's own fillet radius (not just the flat per-arm setting) to the offset
    distance guarantees the light clears the ACTUAL rounded curb surface, not just the sharp
    unrounded vertex. Verified: this raised the worst-case corner's clearance from ~1.5m to ~6.5m
    while barely changing the already-fine corners, using the SAME formula uniformly (no per-arm
    special case).

    2026-08 follow-up, user-requested (a full Japanese-intersection signal placement model, "MIP/
    SCP/CAP/SL" anchors): each enabled arm now gets TWO poles, not one --
    - **P1 (near-side)**: this arm's own corner, exactly as before (unchanged formula/position).
    - **P2 (far-side)**: the SAME formula applied to the arm most nearly OPPOSITE `a`
      (`intersection_kit.opposite_arm`, angularly-nearest to `a.angle_deg + 180`) -- its own
      corner, landing diagonally across the junction from P1 by construction (no separate
      sightline-angle computation is done; a real 15-30-degree visibility check would need a
      driver-eye-point + occlusion model this addon has no data for yet -- documented
      simplification, not a hidden gap).
    - **Cantilever Rule**: when `a`'s own busiest direction has 2+ lanes (`max(lanes_in_count(),
      lanes_out_count()) >= 2` -- "Road_Lanes > 2" read as a real lane-count trigger, since every
      arm in this project is realistically 1-2 lanes, not one 3+ lane arm), BOTH P1 and P2 use the
      overhead `Kit_TrafficGantry_L1` cantilever gantry instead of a standalone pole -- resolved by
      a fixed name (not a separate asset-picker property, to keep this addition scoped) with the
      SAME 'unresolved = build nothing for that spot' convention every other asset lookup in this
      addon already has. A gantry's arm points TOWARD the road (see `tools/build_curb_kit.py`'s
      `traffic_gantry` docstring for why its pivot convention is deliberately reversed from every
      other piece) -- its rotation is the POLE's own outward heading plus 180 degrees.
    Both poles/gantries for every enabled arm still land in AT MOST two instancer objects total
    per intersection (`trafficlight_<name>` for every pole point, `trafficgantry_<name>` for every
    gantry point). Deduped by CORNER IDENTITY before building either instancer (see the loop's own
    comment) -- a mutually-opposite pair of enabled arms (the common case) would otherwise each
    place a point at the SAME corner (one's own P1, the other's P2), landing exactly on top of
    each other rather than the one real light that corner should have."""
    if traffic_light_obj is None:
        return []
    k = ik()
    cx, cy = origin_xy
    gantry_obj = _resolve_curb_asset("Kit_TrafficGantry_L1")
    neighbors = _arm_neighbors(arms)

    def corner_offset(arm_for_corner, next_of_that_arm, radius_extra):
        """(world x, world y, rot_z_rad) for a signal pole/gantry at `arm_for_corner`'s own
        OUT-side corner -- the single shared formula both P1 (arm_for_corner=a) and P2
        (arm_for_corner=opposite_arm(a)) use, see this function's own docstring."""
        d = k.arm_dir(arm_for_corner.angle_deg)
        perp = k.lane_perp(d, arm_for_corner.traffic_side)
        corner = k._junction_corner_vertex(arm_for_corner, next_of_that_arm, kerb_radius, tail_length)
        if corner is not None:
            vx, vy = corner[0]
            fillet_radius = corner[1]
        else:
            near_c = k.vscale(d, min(kerb_radius, arm_for_corner.eff_tail_length(tail_length)))
            vx = near_c[0] + perp[0] * arm_for_corner.out_width()
            vy = near_c[1] + perp[1] * arm_for_corner.out_width()
            fillet_radius = 0.0
        diag = (k.vnorm((vx, vy)) if (abs(vx) + abs(vy)) > 1e-6
                else k.vnorm((d[0] + perp[0], d[1] + perp[1])))
        radius = max(0.0, radius_extra) + fillet_radius
        px = cx + vx + diag[0] * radius
        py = cy + vy + diag[1] * radius
        return px, py, math.atan2(diag[1], diag[0])

    pole_coords, pole_rots = [], []
    gantry_coords, gantry_rots = [], []
    # Dedupe by CORNER IDENTITY (arm_for_corner, its own CCW-next neighbor), first-seen wins --
    # 2026-08, user-reported: "traffic light seem add additional light/object, instead of should
    # just be one object at each, have double on the arm_e side (4 instead of 2)". Root cause,
    # confirmed by direct headless inspection (every one of a real intersection's 8 point-cloud
    # positions was an EXACT duplicate of another, 4 distinct corners x 2 copies each): whenever
    # two enabled arms are each other's `opposite_arm` (the common/expected case for a roughly
    # 4-way intersection, e.g. N<->S and E<->W here) -- arm E's own P1 lands at E's own corner,
    # AND arm W's own P2 (since `opposite_arm(W) == E`) ALSO lands at that SAME corner -- and since
    # every arm shares the same default `traffic_light_radius` unless individually customized, the
    # two land at the EXACT same (px, py), not just visually close. This is a mutual/symmetric
    # relationship BY CONSTRUCTION (`opposite_arm` is nearest-to-180 in both directions for a
    # roughly-symmetric junction), so it fires for every corner, not just one arm -- the user
    # likely just noticed it most clearly on the E/W side. Keeping only the FIRST arm to reach a
    # given corner (in `arms` list order) also resolves the pole-vs-gantry ambiguity for free when
    # the two contributing arms would've disagreed on `use_gantry` (a real but rare edge case) --
    # whichever arm gets there first owns that corner's signal entirely, gantry-or-pole included.
    seen_corners = set()
    for a in arms:
        if not a.traffic_light:
            continue
        _prev_a, next_a = neighbors[a.name]
        opp = k.opposite_arm(a, arms)
        positions = [(a, next_a)]
        if opp is not None:
            opp_prev, opp_next = neighbors[opp.name]
            positions.append((opp, opp_next))
        use_gantry = max(a.lanes_in_count(), a.lanes_out_count()) >= 2 and gantry_obj is not None
        for arm_for_corner, next_of_that_arm in positions:
            corner_key = (arm_for_corner.name, next_of_that_arm.name)
            if corner_key in seen_corners:
                continue
            seen_corners.add(corner_key)
            px, py, rot = corner_offset(arm_for_corner, next_of_that_arm, a.traffic_light_radius)
            if use_gantry:
                gantry_coords.append((px, py, z))
                gantry_rots.append((0.0, 0.0, rot + math.pi))
            else:
                pole_coords.append((px, py, z))
                pole_rots.append((0.0, 0.0, rot))

    out = []
    if pole_coords:
        obj = paths.kc.instancer("trafficlight_%s" % coll.name, pole_coords, traffic_light_obj,
                                  coll, rots=pole_rots)
        if obj is not None:
            out.append(obj)
    if gantry_coords:
        obj = paths.kc.instancer("trafficgantry_%s" % coll.name, gantry_coords, gantry_obj,
                                  coll, rots=gantry_rots)
        if obj is not None:
            out.append(obj)
    return out


ORIGIN_MARKER_KEY = "rka_origin_marker"


def get_or_create_origin_marker(coll, fallback_xyz=None):
    """The LIVE Empty object anchoring an intersection's origin (created in
    `build_intersection_geometry`, tagged `rka_origin_marker`). Every place that used to derive a
    world position from the frozen `rka_origin` custom property (`rebuild_intersection_in_place`,
    `RKA_OT_add_arm`, `RKA_OT_extend_from_arm`) must read THIS object's current `.location`
    instead: `rka_origin` is a plain coordinate that does not move, so selecting an intersection's
    WHOLE collection (this marker included, since it's just another object in it) and Grab/
    Rotate-ing it as a rigid group correctly carries the origin along -- every arm's angle,
    re-derived as a bearing FROM this point, comes out identical to before the move, so the
    intersection reproduces itself at the new location/orientation instead of snapping back
    toward a stale coordinate that got left behind. `fallback_xyz`, if given, self-heals a piece
    built before this marker existed (or loaded from an old file) by creating one there the first
    time it's needed -- from then on it's a normal object and moves with the rest of the piece.
    Returns None if no marker exists and no `fallback_xyz` was given to create one."""
    markers = [o for o in coll.objects if o.get(ORIGIN_MARKER_KEY)]
    if markers:
        if len(markers) > 1:
            # A stray second marker (e.g. a Shift+D linked-duplicate landed in the same
            # collection) would otherwise make every future rebuild pick an ARBITRARY one of the
            # two -- silently "snapping" the piece back to whichever marker iteration happens to
            # return first. Keep the oldest-created (lowest name suffix sorts first for the
            # "origin_<coll.name>"/"origin_<coll.name>.001" naming Blender itself assigns to a
            # duplicate) and warn instead of guessing wrong forever.
            markers.sort(key=lambda o: o.name)
            print("road_kit_authoring: '%s' has %d origin markers (%s) -- using '%s', "
                  "delete the extra(s) by hand" %
                  (coll.name, len(markers), ", ".join(o.name for o in markers), markers[0].name))
        return markers[0]
    if fallback_xyz is None:
        return None
    marker = bpy.data.objects.new("origin_%s" % coll.name, None)
    marker.empty_display_type = 'PLAIN_AXES'
    marker.empty_display_size = 0.5
    marker.location = fallback_xyz
    marker[ORIGIN_MARKER_KEY] = True
    coll.objects.link(marker)
    return marker


def ensure_arm_angle_migrated(arm_obj, ox, oy):
    """One-time migration (2026-08, decoupling an arm's angle from its marker POSITION --
    user-reported, confirmed directly in world_session.blend: "move arm w... edge start to
    rotate... even though [an unrelated] segment... is original in correct location"). Before
    this fix, an arm's angle was always recomputed fresh from its marker's POSITION (`atan2`
    relative to the intersection origin) on every rebuild -- oversensitive to ordinary hand-drag
    imprecision (a drag meant only to adjust distance almost never lands perfectly radially, so it
    always changed the angle at least slightly too), which cascaded into
    `live_edit.move_dependent_marker` rigidly rotating a WHOLE linked segment -- including its
    already-correctly-placed FAR end -- by that same small, unintended angle on every drag.

    Angle is now read directly from the arm Empty's own `rotation_euler.z` (position only ever
    supplies its DISTANCE from origin, via plain Euclidean `hypot` -- unaffected by this change,
    and not oversensitive the way angle was) -- a pure Grab/translate (Blender's G key) never
    touches the rotation channel at all, so it can no longer change the angle by even a fraction
    of a degree; only an explicit Rotate (R key) or `RKA_OT_set_arm_angle` does.

    `rka_arm_angle_migrated` stays False for every arm authored/dragged before this fix, whose
    `rotation_euler.z` was only ever set ONCE at creation time and never kept in sync (angle used
    to come from position instead) -- it can be arbitrarily stale relative to wherever the arm has
    actually been dragged to since. This seeds `rotation_euler.z` from the CURRENT position-
    derived angle -- preserving the intersection's existing visual state exactly -- the ONE time
    this runs per arm, before rotation becomes authoritative from then on. A freshly-created arm
    (`build_intersection_geometry`/`RKA_OT_add_arm`) stamps the flag itself at creation (position
    and rotation already agree by construction), so this is really only ever exercised by
    already-existing content loaded from before this fix. No-op (and does not stamp the flag) if
    the arm currently sits exactly on the origin -- a degenerate position has no angle to migrate
    from; the next rebuild after it moves off-origin will retry."""
    if arm_obj.get("rka_arm_angle_migrated", False):
        return
    dx, dy = arm_obj.location.x - ox, arm_obj.location.y - oy
    if math.hypot(dx, dy) < 1e-9:
        return
    arm_obj.rotation_euler = (0.0, 0.0, math.atan2(dy, dx))
    arm_obj["rka_arm_angle_migrated"] = True


@live_edit.rebuilding()
def rebuild_intersection_in_place(context, coll):
    """Live-editing counterpart to `build_intersection_geometry`: read each arm's ANGLE from its
    `arm_*` marker Empty's own `rotation_euler.z` (see `ensure_arm_angle_migrated` for why NOT
    position) and its DISTANCE from the marker's position (bearing from the LIVE origin marker --
    see `get_or_create_origin_marker`), then rebuild curb/lane objects in place -- no new
    collection, the arm Empties themselves are the drag handles ("bevel-style" adjustment).
    Called from `live_edit.py`'s `depsgraph_update_post` handler whenever an arm Empty's transform
    changes.

    Each arm's RADIUS (distance from origin) IS now taken from the drag, same as its angle --
    `intersection_kit.Arm.tail_length` is a per-arm override (`eff_tail_length`), so an arm
    dragged/snapped to an arbitrary distance (e.g. Grab+Ctrl-snapped onto an external segment's
    port -- see `RKA_OT_select_arm`) keeps EXACTLY that distance after rebuild instead of being
    forced back onto one shared radius.
    An arm that was never deliberately moved off the shared `tail_length` simply keeps reporting
    that same distance, so this is a strict generalization of the old "arms share one radius"
    behavior, not a separate mode. The per-arm value is persisted on the arm Empty itself
    (`rka_arm_tail_length`, alongside `rka_arm_angle`) so it survives across rebuilds/reloads. A
    no-op (returns immediately) if there's no stored origin, fewer than 3 arms survive the current
    drag position (e.g. one was dropped exactly on the origin), or the lane-map/angle combination
    is momentarily degenerate mid-drag -- the next tick, once the drag moves past it, recovers on
    its own."""
    k = ik()
    prev_origin = custom_props.read_origin(coll)
    marker = get_or_create_origin_marker(coll, prev_origin)
    if marker is None:
        return
    ox, oy, oz = marker.location.x, marker.location.y, marker.location.z
    rka = context.scene.rka
    z = oz + rka.lane_surface_z
    tail_length = coll.get("rka_tail_length", 12.0)
    kerb_radius = coll.get("rka_kerb_radius", 9.0)
    lane_width = coll.get("rka_lane_width", 5.0)
    segments = coll.get("rka_segments", 8)
    curb_style = coll.get("rka_curb_style", 'NONE')
    curb_height = coll.get("rka_curb_height", 0.15)
    curb_thickness = coll.get("rka_curb_thickness", 0.25)
    curb_asset_obj = _resolve_curb_asset(coll.get("rka_curb_asset_collection", ""))
    curb_asset_spacing = coll.get("rka_curb_asset_spacing", 2.0)
    sidewalk_width = coll.get("rka_sidewalk_width", 0.0)
    sidewalk_height = coll.get("rka_sidewalk_height", 0.15)
    sidewalk_asset_obj = _resolve_curb_asset(coll.get("rka_sidewalk_asset_collection", ""))
    sidewalk_asset_spacing = coll.get("rka_sidewalk_asset_spacing", 2.0)
    traffic_light_obj = _resolve_curb_asset(coll.get("rka_traffic_light_asset_collection", ""))
    lane_map = custom_props.read_lane_map_override(coll)
    join_visual_mesh = any(o.name.startswith("mesh_") for o in coll.objects)
    traffic_side = coll.get("rka_traffic_side", "LEFT")

    arm_empties = [o for o in coll.objects if "rka_arm_name" in o.keys()]

    # If the origin marker itself moved since the LAST rebuild (its previously-persisted
    # position, `prev_origin`, differs from its current `marker.location`), carry every arm that
    # DIDN'T also move along with it, by that same delta, before re-deriving bearings below.
    # Without this, dragging JUST the origin marker to relocate the whole intersection (the
    # natural, single-handle way to use it -- the "regenerate along that arm/empty" ask this
    # marker exists for) instead re-derives each arm's angle against a now-mismatched center,
    # collapsing every arm onto a tiny bogus angular range while forcibly re-snapping each back
    # onto the `tail_length` radius -- the intersection "blows up" into a degenerate cluster
    # instead of relocating intact. An arm that already moved on its own (the correct "select the
    # WHOLE collection including the origin, Grab/Rotate together" workflow, or a normal one-arm
    # reshape drag) is left alone -- it no longer sits at its last-known position, so its NEW
    # position is trusted as intentional, exactly as before this carry existed.
    if prev_origin is not None:
        odx = ox - prev_origin[0]
        ody = oy - prev_origin[1]
        odz = oz - prev_origin[2]
        if abs(odx) > 1e-4 or abs(ody) > 1e-4 or abs(odz) > 1e-4:
            for o in arm_empties:
                prev_angle = o.get("rka_arm_angle")
                if prev_angle is None:
                    continue
                # This arm's OWN previous tail length (falls back to the shared scalar for an
                # older piece built before rka_arm_tail_length existed) -- using the shared value
                # here for an arm that already has its own override would wrongly predict its
                # last-known position, making a piece-wide move falsely look like an independent
                # arm drag.
                prev_tail = o.get("rka_arm_tail_length", tail_length)
                d = k.arm_dir(prev_angle)
                want_prev = (prev_origin[0] + d[0] * prev_tail,
                             prev_origin[1] + d[1] * prev_tail,
                             prev_origin[2] + rka.lane_surface_z)
                cur = (o.location.x, o.location.y, o.location.z)
                if math.dist(want_prev, cur) < 1e-3:
                    o.location.x += odx
                    o.location.y += ody
                    o.location.z += odz

    arms = []
    for o in arm_empties:
        ensure_arm_angle_migrated(o, ox, oy)
        dx, dy = o.location.x - ox, o.location.y - oy
        dist = math.hypot(dx, dy)
        if dist < 1e-9:
            continue   # dropped exactly on the origin mid-drag -- degenerate, skip this arm
        angle_deg = math.degrees(o.rotation_euler.z) % 360.0
        oneway = o.get("rka_arm_oneway", "") or None
        lanes_out_raw = int(o.get("rka_arm_lanes_out", 0))
        # tail_pos = this arm's REAL current local position, always -- for an ordinary (never
        # off-ray-matched) arm this is just `dist * direction(angle_deg)` anyway (byte-identical
        # to before `Arm.tail_pos` existed), so passing it unconditionally changes nothing for the
        # common case; see `Arm.tail_center`'s docstring for the case where it's genuinely off-ray.
        arms.append(k.Arm(o["rka_arm_name"], angle_deg, lane_width, int(o.get("rka_arm_lanes", 1)),
                           oneway=oneway, lanes_out=lanes_out_raw or None,
                           traffic_side=traffic_side, tail_length=dist, tail_pos=(dx, dy),
                           median_width=float(o.get("rka_arm_median_width", 0.0)),
                           traffic_light=bool(o.get("rka_arm_traffic_light", False)),
                           traffic_light_radius=float(o.get("rka_arm_traffic_light_radius",
                                                             TRAFFIC_LIGHT_DEFAULT_RADIUS))))
    if len(arms) < 3:
        return

    clear_generated_mesh_objects(coll, keep_gn_boundaries=True)
    try:
        _, _, _, tail_length = _populate_intersection_mesh(
            context, coll, arms, kerb_radius, tail_length, segments, lane_width, curb_style,
            curb_height, curb_thickness, lane_map, join_visual_mesh, (ox, oy), z,
            curb_asset_obj=curb_asset_obj, curb_asset_spacing=curb_asset_spacing,
            sidewalk_width=sidewalk_width, sidewalk_height=sidewalk_height,
            sidewalk_asset_obj=sidewalk_asset_obj, sidewalk_asset_spacing=sidewalk_asset_spacing,
            traffic_light_obj=traffic_light_obj)
    except RkaBuildError:
        return   # e.g. two arms briefly coincide mid-drag -- leave geometry as the last-good state
    sweep_untouched_boundaries(coll)   # delete anything provisionally spared above but never
                                        # reconfirmed this pass (see clear_generated_mesh_objects)
    # `tail_length` above is now the EFFECTIVE value (floored to recommended_tail_length inside
    # _populate_intersection_mesh) -- re-snapping arm markers and persisting rka_tail_length below
    # must use THIS value, not the original request, or the markers/stored setting would silently
    # drift out of sync with where the pad/curb/movements actually ended up.
    coll["rka_tail_length"] = tail_length

    # Re-snap each arm empty onto ITS OWN effective tail length (its live drag distance, or the
    # shared scalar if it was never individually overridden -- see the docstring) and keep its
    # arrow aligned with the new angle. Guarded by an epsilon so a clean drag (already exactly at
    # its own resolved distance) doesn't rewrite the transform and retrigger this same handler
    # pass -- in practice this is a near-no-op for the radius (each arm's `Arm.tail_length` was
    # itself just measured FROM this same marker's current position above), it mainly exists to
    # correct float drift and to keep every OTHER arm's stored `rka_arm_tail_length` in sync after
    # a `_populate_intersection_mesh` call that grew the shared scalar for wide-arm clearance.
    #
    # 2026-08 EXCEPTION: an arm stamped `rka_arm_tail_pos_locked` (`RKA_OT_aim_arm_at`, matched
    # exactly onto an external target's position -- see `Arm.tail_pos`) is skipped here entirely.
    # Without this, THIS SAME re-snap would silently pull the marker back onto its clean angle-ray
    # on the very next rebuild, undoing the match it took an explicit operator to make -- the
    # user-reported regression ("arm w position should adjust to match that segment" kept not
    # sticking). A locked arm's position is only ever changed by another explicit user action
    # (a further drag, or `RKA_OT_set_arm_angle`/`RKA_OT_nudge_arm_angle`, which clear the lock).
    by_name = {a.name: a for a in arms}
    for o in arm_empties:
        a = by_name.get(o["rka_arm_name"])
        if a is None:
            continue
        eff_tail = a.tail_length if a.tail_length is not None else tail_length
        if not o.get("rka_arm_tail_pos_locked"):
            d = k.arm_dir(a.angle_deg)
            want = (ox + d[0] * eff_tail, oy + d[1] * eff_tail, z)
            cur = (o.location.x, o.location.y, o.location.z)
            if math.dist(want, cur) > 1e-4:
                o.location = want
        o["rka_arm_angle"] = a.angle_deg
        o["rka_arm_tail_length"] = eff_tail

    custom_props.write_build_settings(
        coll, arm_names=[a.name for a in arms], arm_angles=[a.angle_deg for a in arms],
        arm_lanes=[a.lanes for a in arms], arm_oneway=[a.oneway or "" for a in arms],
        arm_lanes_out=[a.lanes_out or 0 for a in arms],
        arm_tail_lengths=[(a.tail_length if a.tail_length is not None else tail_length)
                           for a in arms],
        # Each arm's own resolved local tail-CENTER point (`Arm.tail_center` -- `tail_pos`
        # directly for a matched/off-ray arm, else the plain angle-ray point) -- 2026-08,
        # user-reported: lane preview (and, confirmed the same root cause, the REAL exported
        # `.lanekit.json`/Godot Path3D data) landed far from a `tail_pos`-locked arm's actual
        # matched segment. Root cause: `_lane_far_point` (round 2's live-rebuild fix) only ever
        # got fed a real `tail_pos` from THIS in-memory rebuild path, which reconstructs it fresh
        # from the arm marker's own current position every time -- but `lane_export.py`'s preview/
        # export path goes through the SEPARATE `custom_props.read_arms_full` reconstruction
        # (angle/tail_length arrays only, `tail_pos` never persisted at all), so it silently fell
        # back to the plain on-ray point for EVERY matched arm, undoing round 2's fix specifically
        # for anything downstream of an export (exactly the case that matters for Godot). Persist
        # it here so `read_arms_full` can recover it -- always written (byte-identical to the
        # on-ray point for any never-matched arm), not conditional on `tail_pos_locked`, matching
        # `Arm.tail_pos`'s own "None = standard ray point" contract.
        arm_tail_pos_x=[a.tail_center(tail_length)[0] for a in arms],
        arm_tail_pos_y=[a.tail_center(tail_length)[1] for a in arms],
        arm_medians=[a.median_width for a in arms],
        arm_traffic_lights=[a.traffic_light for a in arms],
        arm_traffic_light_radii=[a.traffic_light_radius for a in arms],
        # Keep the fallback-seed prop in sync with the LIVE marker on every rebuild -- otherwise
        # it freezes at the build-time position forever, and if the marker object is ever lost
        # (accidental delete, a linked-duplicate collision -- see get_or_create_origin_marker's
        # dedupe note) self-heal would resurrect it at the stale PRE-MOVE location instead of
        # where the piece actually is now.
        origin=[ox, oy, oz])


def build_intersection_geometry(context, parent_coll, cursor, preset, rotation_deg, side_angle,
                                 arm_angles_str, lane_width, lanes, lane_arm_overrides, kerb_radius,
                                 tail_length, segments, curb_style, curb_height, curb_thickness,
                                 lane_map, join_visual_mesh, export_path, gltf_export_path,
                                 traffic_side='LEFT', curb_asset_collection="",
                                 curb_asset_spacing=2.0, sidewalk_width=0.0, sidewalk_height=0.15,
                                 sidewalk_asset_collection="", sidewalk_asset_spacing=2.0,
                                 traffic_light_asset_collection=""):
    """Pure build logic behind `RKA_OT_build_intersection` -- no `bpy.ops` dispatch, so a caller
    that needs to build an intersection as ONE STEP of a larger flat operator
    (`RKA_OT_insert_intersection_on_segment`) can call this directly instead of going through
    `bpy.ops.rka.build_intersection(...)` (see module docstring for why that matters for F9).

    `cursor` is `(x, y, z)` -- `z` is the RAW cursor-equivalent height, before
    `context.scene.rka.lane_surface_z` is added (this function is the one place that offset is
    applied, same as before). `lane_map` is an already-resolved `{(from,to): [(in,out),...]}`
    dict or None (callers resolve a collection-custom-property override / mini-syntax string
    BEFORE calling this, since that resolution is itself context/UI-specific and doesn't belong in
    the pure geometry-building step).

    Returns a dict: `{'coll', 'arms', 'boundary', 'movements', 'visual_objs', 'export_note',
    'warnings'}` (`boundary` is the `[(x, y, radius), ...]` pad/curb polygon from
    `intersection_kit.build_junction_boundary`; `warnings` is a list of str -- non-fatal export
    failures the caller should
    surface via `self.report({'WARNING'}, ...)` but that don't prevent FINISHED). Raises
    `RkaBuildError` for anything that must abort before any geometry is created."""
    rka = context.scene.rka
    k = ik()

    if preset == '4WAY':
        arms = k.preset_4way(lane_width=lane_width,
                              lanes=_arm_lane_list(lanes, lane_arm_overrides, 4),
                              traffic_side=traffic_side)
    elif preset == '3WAY_T':
        arms = k.preset_3way_t(side_angle=side_angle, lane_width=lane_width,
                                lanes=_arm_lane_list(lanes, lane_arm_overrides, 3),
                                traffic_side=traffic_side)
    elif preset == '3WAY_Y':
        arms = k.preset_3way_y(angles=(0.0, side_angle, 2.0 * side_angle), lane_width=lane_width,
                                lanes=_arm_lane_list(lanes, lane_arm_overrides, 3),
                                traffic_side=traffic_side)
    else:   # NWAY
        try:
            angles = [float(a.strip()) for a in arm_angles_str.split(",") if a.strip()]
        except ValueError:
            raise RkaBuildError("Arm Angles must be comma-separated numbers, e.g. '0,60,130,200,280'")
        if len(angles) < 3:
            raise RkaBuildError("NWAY needs at least 3 arm angles")
        arms = k.preset_nway(angles, lane_width=lane_width,
                              lanes=_arm_lane_list(lanes, lane_arm_overrides, len(angles)),
                              traffic_side=traffic_side)

    if rotation_deg != 0.0:
        for a in arms:
            a.angle_deg = (a.angle_deg + rotation_deg) % 360.0

    cx, cy, cz_raw = cursor
    z = cz_raw + rka.lane_surface_z

    n = 1
    base_name = "Intersection_%s" % preset
    # local_collection (not a bare name-in-bpy.data.collections test) so a linked neighbor's
    # same-numbered piece never perturbs local auto-numbering -- see its docstring.
    while local_collection(base_name + ("_%03d" % n)) is not None:
        n += 1
    coll = bpy.data.collections.new(base_name + ("_%03d" % n))
    parent_coll.children.link(coll)
    get_or_create_origin_marker(coll, (cx, cy, cz_raw))

    curb_asset_obj = _resolve_curb_asset(curb_asset_collection)
    sidewalk_asset_obj = _resolve_curb_asset(sidewalk_asset_collection)
    traffic_light_obj = _resolve_curb_asset(traffic_light_asset_collection)
    boundary, movements, visual_objs, tail_length = _populate_intersection_mesh(
        context, coll, arms, kerb_radius, tail_length, segments, lane_width, curb_style,
        curb_height, curb_thickness, lane_map, join_visual_mesh, (cx, cy), z,
        curb_asset_obj=curb_asset_obj, curb_asset_spacing=curb_asset_spacing,
        sidewalk_width=sidewalk_width, sidewalk_height=sidewalk_height,
        sidewalk_asset_obj=sidewalk_asset_obj, sidewalk_asset_spacing=sidewalk_asset_spacing,
        traffic_light_obj=traffic_light_obj)
    # `tail_length` above is now the EFFECTIVE value (floored to recommended_tail_length inside
    # _populate_intersection_mesh) -- every use below (arm marker placement, the persisted
    # rka_tail_length, JSON export) must use THIS value, not the original request, or the markers
    # would be placed at the OLD (too-small) radius while the pad/curb/movements already reflect
    # the new one.

    # Arm marker Empties -- one per arm, at the tail's far end (the same port RKA_OT_extend_from_arm
    # extends from). This is the concrete "place arm at end of each intersection" handle: visible
    # and selectable in the viewport, carries the arm's angle/lane count as inspectable custom
    # properties, doubles as a click target for Extend From Arm (no typing the arm name), and is
    # also the LIVE-EDIT drag handle -- moving one re-derives its angle and rebuilds this
    # intersection in place (see `rebuild_intersection_in_place`, wired via `live_edit.py`'s
    # depsgraph handler).
    for a in arms:
        d = k.arm_dir(a.angle_deg)
        pos = (cx + d[0] * tail_length, cy + d[1] * tail_length, z)
        arm_obj = bpy.data.objects.new("arm_%s" % a.name, None)
        arm_obj.empty_display_type = 'SINGLE_ARROW'
        arm_obj.empty_display_size = min(2.0, lane_width * 0.4)
        arm_obj.location = pos
        arm_obj.rotation_euler = (0.0, 0.0, math.radians(a.angle_deg))
        arm_obj["rka_arm_name"] = a.name
        arm_obj["rka_arm_angle"] = a.angle_deg
        arm_obj["rka_arm_lanes"] = a.lanes
        arm_obj["rka_arm_oneway"] = a.oneway or ""
        arm_obj["rka_arm_lanes_out"] = a.lanes_out or 0
        arm_obj["rka_arm_tail_length"] = tail_length
        arm_obj["rka_arm_angle_migrated"] = True   # fresh -- position/rotation already agree
        coll.objects.link(arm_obj)

    # Permanent record of exactly how this was built -- native custom properties on the
    # collection, editable via Blender's Object/Collection Properties panel even without the
    # addon's redo panel (which is lost the moment you close the file). See custom_props.py.
    custom_props.write_build_settings(
        coll, preset=preset, kerb_radius=kerb_radius, lane_width=lane_width,
        tail_length=tail_length, segments=segments, curb_style=curb_style,
        curb_height=curb_height, curb_thickness=curb_thickness,
        curb_asset_collection=curb_asset_collection or None, curb_asset_spacing=curb_asset_spacing,
        sidewalk_width=sidewalk_width, sidewalk_height=sidewalk_height,
        sidewalk_asset_collection=sidewalk_asset_collection or None,
        sidewalk_asset_spacing=sidewalk_asset_spacing,
        traffic_light_asset_collection=traffic_light_asset_collection or None,
        arm_names=[a.name for a in arms], arm_angles=[a.angle_deg for a in arms],
        arm_lanes=[a.lanes for a in arms], arm_lanes_out=[a.lanes_out or 0 for a in arms],
        arm_oneway=[a.oneway or "" for a in arms],
        arm_tail_lengths=[tail_length for a in arms],
        # See `rebuild_intersection_in_place`'s matching write for the full rationale -- at a
        # fresh build no arm is matched yet, so this is byte-identical to the plain ray point,
        # but writing it unconditionally means a NEVER-rebuilt-since fresh piece already has it
        # (no "only appears after the first rebuild" gap).
        arm_tail_pos_x=[a.tail_center(tail_length)[0] for a in arms],
        arm_tail_pos_y=[a.tail_center(tail_length)[1] for a in arms],
        arm_medians=[a.median_width for a in arms],
        arm_traffic_lights=[a.traffic_light for a in arms],
        arm_traffic_light_radii=[a.traffic_light_radius for a in arms],
        lane_map=lane_map, traffic_side=traffic_side,
        # Raw (pre-lane_surface_z-offset) cursor position -- lets RKA_OT_extend_from_arm
        # reconstruct exact world-space port positions/tangents from this collection's own stored
        # arm data, without guessing where it was built.
        origin=[cx, cy, cz_raw])

    warnings = []
    # `recommended_tail_length`'s numerical search grows `tail_length` to contain every turn
    # movement inside the pad boundary -- but that search can only widen STRAIGHT tail-caps along
    # each arm's own axis; it cannot enlarge a DIFFERENT, unrelated corner's own fillet radius. Two
    # (or more) very wide arms meeting near a much narrower third arm can produce a movement whose
    # real diagonal sweep no amount of tail_length growth resolves (confirmed: plateaus above the
    # margin instead of converging) -- surface that here so the artist knows to widen kerb_radius,
    # add more lanes to the narrow arm, or accept a straighter/manually-overridden lane_map instead
    # of silently shipping geometry with a lane visibly poking outside the pavement.
    remaining_overshoot = k.worst_movement_overshoot(arms, kerb_radius, tail_length)
    if remaining_overshoot > 2.0:
        warnings.append(
            "One or more wide-arm turn lanes still reach ~%.1fm outside the pad after "
            "auto-widening (tail_length=%.1f) -- try a larger Kerb Radius, or check whether two "
            "very wide arms meet near a much narrower one." % (remaining_overshoot, tail_length))
    export_note = ""
    if export_path:
        try:
            k.export_json(bpy.path.abspath(export_path), arms, kerb_radius, junction_id=coll.name,
                           segments=segments, tail_length=tail_length, z=z, lane_map=lane_map,
                           center=(cx, cy))
            export_note += ", json -> '%s'" % export_path
        except OSError as exc:
            warnings.append("Built geometry OK, but json export failed: %s" % exc)
    if gltf_export_path:
        try:
            paths.kc.export_gltf(visual_objs, bpy.path.abspath(gltf_export_path))
            export_note += ", glb -> '%s'" % gltf_export_path
        except Exception as exc:   # noqa: BLE001 -- bpy.ops export can raise a variety of types
            warnings.append("Built geometry OK, but glTF export failed: %s" % exc)

    return {"coll": coll, "arms": arms, "boundary": boundary, "movements": movements,
            "visual_objs": visual_objs, "export_note": export_note, "warnings": warnings,
            "tail_length": tail_length}


class RKA_OT_build_intersection(bpy.types.Operator):
    """Build one intersection (a GN-filled pavement pad + one continuous GN-swept curb loop, both
    from the arm-angle-driven boundary polygon, plus a lanecl_* centerline for every legal
    single-lane movement and an 'arm_*' marker Empty at each arm's tail) at the 3D cursor. Purely
    additive: creates a new collection, never touches lane_kit.blend or
    any existing piece. Re-run with different settings and compare -- each run gets its own
    collection."""
    bl_idname = "rka.build_intersection"
    bl_label = "Build Intersection"
    bl_options = {'REGISTER', 'UNDO'}

    preset: bpy.props.EnumProperty(name="Preset", items=PRESET_ITEMS, default='4WAY')
    rotation_deg: bpy.props.FloatProperty(
        name="Rotation", description="Degrees added to EVERY arm's angle after the preset is "
        "built -- rotates the whole intersection in place, e.g. to align a 3-way T's through "
        "street with an existing road's direction (RKA_OT_insert_intersection_on_segment sets "
        "this automatically)", default=0.0)
    side_angle: bpy.props.FloatProperty(
        name="Side/3rd Arm Angle", description="Degrees from the first arm -- the side street "
        "for 3-way T, or the spacing between all 3 arms for 3-way Y",
        default=90.0, min=1.0, max=179.0)
    arm_angles: bpy.props.StringProperty(
        name="Arm Angles", description="NWAY preset only: comma-separated approach angles in "
        "degrees, at least 3, e.g. '0,60,130,200,280'", default="0,90,180,270")
    lane_width: bpy.props.FloatProperty(
        name="Lane Width", default=5.0, min=0.5, unit='LENGTH')
    lanes: bpy.props.IntProperty(
        name="Lanes Per Direction", description="Default lane count applied to every arm, "
        "overridden per-arm by 'Lanes: Arm N' below (0 = use this default)",
        default=1, min=1, max=4)
    lanes_arm1: bpy.props.IntProperty(name="Lanes: Arm 1", default=0, min=0, max=4)
    lanes_arm2: bpy.props.IntProperty(name="Lanes: Arm 2", default=0, min=0, max=4)
    lanes_arm3: bpy.props.IntProperty(name="Lanes: Arm 3", default=0, min=0, max=4)
    lanes_arm4: bpy.props.IntProperty(name="Lanes: Arm 4", default=0, min=0, max=4)
    kerb_radius: bpy.props.FloatProperty(
        name="Kerb Radius",
        description="Curb corner fillet radius, in meters. Real-world urban minimum is ~3.5 m "
                     "(tight, delivery-truck-feasible -- see the reference diagram this tool was "
                     "designed against); the default here is deliberately more RELAXED so AI "
                     "drivers get a wide, comfortable arc instead of hugging the corner",
        default=9.0, min=1.0, unit='LENGTH')
    tail_length: bpy.props.FloatProperty(
        name="Approach Tail Length",
        description="How far each generated centerline/curb extends out from the corner along "
                     "its arm, in meters -- long enough to reach into an approach lane tile",
        default=12.0, min=1.0, unit='LENGTH')
    segments: bpy.props.IntProperty(
        name="Fillet Segments", description="Polyline segments per rounded corner/turn arc",
        default=8, min=2, max=32)
    curb_style: bpy.props.EnumProperty(
        name="Curb Style", items=CURB_STYLE_ITEMS, default='NONE',
        description="PROFILE = the resolved kit piece's own real cross-section, swept "
                     "continuously around every corner (set 'Curb Asset Piece' below). NONE = no "
                     "curb at all")
    traffic_side: bpy.props.EnumProperty(
        name="Traffic Side", items=TRAFFIC_SIDE_ITEMS, default='LEFT',
        description="Which physical lateral half of every arm is arriving vs. departing. Must "
                     "match every segment/transition this intersection connects to")
    curb_height: bpy.props.FloatProperty(name="Curb Height", default=0.15, min=0.01, unit='LENGTH')
    curb_thickness: bpy.props.FloatProperty(
        name="Curb Thickness", description="BOX style: wall thickness. GUTTER style: total "
        "curb+gutter width (the real piece this mirrors is 0.6m)",
        default=0.25, min=0.01, unit='LENGTH')
    curb_asset_collection: bpy.props.StringProperty(
        name="Curb Asset Piece", description="Name of a linked kit/curb_kit.blend collection's "
        "mesh object to repeat around every curb corner, when Curb Style is 'Asset'. Use 'Link "
        "Curb Kit Library' first", default="")
    curb_asset_spacing: bpy.props.FloatProperty(
        name="Curb Asset Spacing", description="Distance between repeated instances -- should "
        "equal the chosen piece's own local X length (see its 'rka_curb_asset_length' custom "
        "property) for seamless tiling", default=2.0, min=0.1, unit='LENGTH')
    sidewalk_width: bpy.props.FloatProperty(
        name="Sidewalk Width", description="A raised paved strip beyond every arm's own curb, "
        "both sides -- 0 (default) is no sidewalk. Same convention as a segment's own Sidewalk "
        "Width fields (see RKA_OT_build_straight_segment)", default=0.0, min=0.0, unit='LENGTH')
    sidewalk_height: bpy.props.FloatProperty(
        name="Sidewalk Height", default=0.15, min=0.01, unit='LENGTH')
    sidewalk_asset_collection: bpy.props.StringProperty(
        name="Sidewalk Asset Piece", description="Name of a linked collection's mesh object to "
        "tile along every arm's sidewalk instead of a procedural sweep -- e.g. "
        "'Kit_Curb_SidewalkTile_L2'. Blank (default) = procedural BOX sweep. Use 'Link Curb Kit "
        "Library' first", default="")
    sidewalk_asset_spacing: bpy.props.FloatProperty(
        name="Sidewalk Asset Spacing", default=2.0, min=0.1, unit='LENGTH')
    traffic_light_asset_collection: bpy.props.StringProperty(
        name="Traffic Light Asset Piece", description="Name of a linked collection's mesh "
        "object placed once per arm that has its own Traffic Light enabled (see the per-arm "
        "'Traffic Light' toggle) -- e.g. 'Kit_TrafficLight_L1'. Blank (default) = no signal even "
        "on arms with it enabled. Use 'Link Curb Kit Library' first", default="")
    lane_map: bpy.props.StringProperty(
        name="Lane Map Override", description="Optional: hand-author exactly which incoming "
        "lane feeds which outgoing lane for specific arm pairs, instead of the default lane-i-"
        "feeds-lane-i pairing. Syntax: 'From>To:in-out,in-out; From2>To2:in-out', e.g. "
        "'N>E:0-1,1-0' to swap. Blank = default pairing everywhere", default="")
    join_visual_mesh: bpy.props.BoolProperty(
        name="Join Into One Mesh", default=False,
        description="Combine every curb wall + lane ribbon into a single mesh object after "
                     "building (instead of one object per curb/ribbon)")
    export_path: bpy.props.StringProperty(
        name="Export .lanekit.json", description="Optional: write the graph-shaped lane/port "
        "sidecar (lib/intersection_kit.py's export_json) here after building. Blank = skip -- "
        "geometry-only, no file written", default="", subtype='FILE_PATH')
    gltf_export_path: bpy.props.StringProperty(
        name="Export .glb", description="Optional: export the built visual geometry (curb walls "
        "+ driving-surface ribbons -- NOT the lanecl_* data curves, which carry no separate "
        "meaning once exported since the .lanekit.json sidecar is the data source of truth) to a "
        ".glb here, ready for Godot to import. Blank = skip", default="", subtype='FILE_PATH')

    def invoke(self, context, event):
        self.traffic_side = context.scene.rka.default_traffic_side
        # Anchored build: an arm_*/port_* marker is active -- prefill Rotation and Arm 1's lane
        # count so the redo panel already shows a correctly-oriented, lane-matched intersection
        # (see `execute()`'s origin-offset math for the position half of this). `heading_deg + 180`
        # lands the FIRST preset arm (raw angle 0 deg in every built-in preset -- 4WAY/3WAY_T/
        # 3WAY_Y/NWAY's default "0,90,180,270" all start there) facing back at the source, so "Arm
        # 1" is always the one that ends up connected. A hand-typed NWAY 'Arm Angles' whose first
        # value isn't 0 breaks that assumption -- re-dial Rotation/Preset on the F9 panel if so.
        anchor = arm_or_port_anchor(context)
        if anchor is not None:
            _, _, heading_deg, lanes_forward, _, _ = anchor
            self.rotation_deg = (heading_deg + 180.0) % 360.0
            if lanes_forward > 0:
                self.lanes_arm1 = max(1, min(4, lanes_forward))
        return self.execute(context)

    def execute(self, context):
        active_coll = context.view_layer.active_layer_collection.collection

        # A custom property on the ACTIVE collection wins over the string field entirely -- lets
        # you hand-edit a native nested dict via Blender's own Object/Collection Properties panel
        # instead of the 'From>To:in-out,in-out' mini-syntax (see custom_props.py).
        lane_map = custom_props.read_lane_map_override(active_coll)
        lane_map_source = "custom property" if lane_map is not None else None
        if lane_map is None:
            try:
                lane_map = parse_lane_map(self.lane_map)
            except ValueError as exc:
                self.report({'ERROR'}, "Lane Map Override: %s" % exc)
                return {'CANCELLED'}
            if lane_map is not None:
                lane_map_source = "string field"

        # Anchored build (arm_*/port_* active): place the intersection's CENTER `tail_length`
        # further out along the source's own outward heading, so the back-facing arm's own tip
        # (see `build_intersection_geometry`'s arm marker placement, the identical `origin + dir *
        # tail_length` formula) lands EXACTLY on the source arm/port tip -- zero gap, no connecting
        # stub segment needed. Otherwise, fall back to `active_marker_position` (position only, no
        # offset -- covers segend_*/segbend_* markers, unchanged) or the 3D cursor.
        anchor = arm_or_port_anchor(context)
        if anchor is not None:
            (ax, ay), cz_raw, heading_deg, _, _, parent_coll = anchor
            rad = math.radians(heading_deg)
            cx = ax + self.tail_length * math.cos(rad)
            cy = ay + self.tail_length * math.sin(rad)
        else:
            marker = active_marker_position(context)
            if marker is not None:
                (cx, cy), cz_raw, parent_coll = marker
            else:
                cursor = context.scene.cursor.location
                cx, cy, cz_raw, parent_coll = cursor.x, cursor.y, cursor.z, active_coll

        try:
            result = build_intersection_geometry(
                context, parent_coll, (cx, cy, cz_raw), self.preset,
                self.rotation_deg, self.side_angle, self.arm_angles, self.lane_width, self.lanes,
                [self.lanes_arm1, self.lanes_arm2, self.lanes_arm3, self.lanes_arm4],
                self.kerb_radius, self.tail_length, self.segments, self.curb_style,
                self.curb_height, self.curb_thickness, lane_map, self.join_visual_mesh,
                self.export_path, self.gltf_export_path, self.traffic_side,
                curb_asset_collection=self.curb_asset_collection,
                curb_asset_spacing=self.curb_asset_spacing,
                sidewalk_width=self.sidewalk_width, sidewalk_height=self.sidewalk_height,
                sidewalk_asset_collection=self.sidewalk_asset_collection,
                sidewalk_asset_spacing=self.sidewalk_asset_spacing,
                traffic_light_asset_collection=self.traffic_light_asset_collection)
        except RkaBuildError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        for w in result["warnings"]:
            self.report({'WARNING'}, w)

        note = result["export_note"]
        if lane_map_source:
            note += " (lane_map from %s)" % lane_map_source

        for o in context.selected_objects:
            o.select_set(False)
        corner_count = len([p for p in result["boundary"] if p[2] > 0])
        if result["tail_length"] > self.tail_length + 1e-3:
            note += " (tail_length auto-grown %.1fm -> %.1fm for wide arms)" % (
                self.tail_length, result["tail_length"])
        self.report(
            {'INFO'},
            "Built '%s': %d arm(s), %d curb corner(s), %d lane movement(s) (radius=%.1fm)%s"
            % (result["coll"].name, len(result["arms"]), corner_count,
               len(result["movements"]), self.kerb_radius, note))
        return {'FINISHED'}


def _is_piece_collection(coll):
    """True if `coll` carries one of this addon's piece-identifying custom properties --
    `rka_arm_names` (intersection), `rka_curve_object` (a GN segment OR a lane transition, both
    spine-backed), or `rka_p0` (the legacy ribbon-based segment, no spine)."""
    return coll is not None and ("rka_arm_names" in coll.keys() or "rka_p0" in coll.keys()
                                  or "rka_curve_object" in coll.keys())


def _live_edit_target_collection(context):
    """The collection a manual 'Rebuild From Handles' should act on. Resolution order:

    1. ANY object the active object's own collection membership already identifies as a piece --
       not just a marker Empty (arm/segend/segbend/port/origin): a `curb_*`/`pad_*`/`lanecl_*`/
       `mark_*`/`ribbon_*`/`mesh_*`/`spine_*` object is linked into the exact same collection as
       every marker of that same piece, so this alone covers clicking (or box-selecting, making
       active) ANY part of a piece -- previously only the small marker Empties resolved, so
       selecting/making-active one of the far more numerous and visually larger generated mesh
       objects (very plausible during a "select everything, Grab" pass) made the old Freeze For
       Move's poll() silently fail (that operator, and the crash-avoidance need for it, no longer
       exist -- see `clear_generated_mesh_objects`'s `keep_gn_boundaries` docstring for the actual
       fix -- but this broader resolution is still the right behavior for any manual rebuild
       trigger regardless).
    2. Back-compat fallback for an object that (unusually) isn't linked into its own piece's
       collection directly: the old marker-tag check, or an `rka_curve_object`-name search across
       every collection for a Curve object.
    3. The active LAYER collection itself, if it IS a piece (Outliner collection click, no object
       necessarily active/selected).

    None if nothing resolves."""
    obj = context.active_object
    if obj is not None and obj.users_collection:
        for coll in obj.users_collection:
            if _is_piece_collection(coll):
                return coll
        keys = obj.keys()
        if ("rka_arm_name" in keys or "rka_segend" in keys or "rka_segbend" in keys
                or "rka_port" in keys or ORIGIN_MARKER_KEY in keys):
            return obj.users_collection[0]
        # `is_spine` covers BOTH carrier kinds -- the legacy POLY Curve and the modifier-stack
        # MESH. As a bare `type == 'CURVE'` test this fallback could never resolve a stack piece.
        from . import spine_io
        if spine_io.is_spine(obj):
            for coll in bpy.data.collections:
                if coll.library is not None:
                    continue   # a linked neighbor's spine could share this curve's exact name
                if coll.get("rka_curve_object") == obj.name:
                    return coll
    coll = context.view_layer.active_layer_collection.collection
    if _is_piece_collection(coll):
        return coll
    return None


def _rebuild_piece_in_place(context, coll):
    """Dispatch to the right rebuild function for whatever kind of piece `coll` is -- shared by
    every caller that needs to rebuild an arbitrary piece by its collection alone
    (`RKA_OT_rebuild_from_handles`, `live_edit._propagate_links`'s per-iteration cascade rebuild)
    so they can never drift apart on which check runs first (lane-transition's own discriminator,
    `rka_lanes_a`, MUST be checked before the plain-curve-segment one, since a transition also
    carries `rka_curve_object` and would otherwise silently un-taper)."""
    from . import ops_segment
    from . import ops_lane_ports
    if "rka_arm_names" in coll.keys():
        rebuild_intersection_in_place(context, coll)
    elif "rka_lanes_a" in coll.keys():
        ops_segment.rebuild_lane_transition_in_place(context, coll)
    elif "rka_curve_object" in coll.keys():
        ops_segment.rebuild_segment_gn_in_place(context, coll)
    else:
        ops_segment.rebuild_segment_in_place(context, coll)
    # Lane-port markers describe the geometry that just changed, so they are re-derived here
    # rather than left to go stale (a port a user is about to snap to must be where the lane
    # actually ends). No-op unless this piece already has them -- see `refresh_lane_ports`.
    ops_lane_ports.refresh_if_present(context, (coll.name,))


class RKA_OT_rebuild_from_handles(bpy.types.Operator):
    """Manual fallback for live-editing: re-derive geometry from the CURRENT positions of an
    intersection's arm_* Empties (or a segment's segend_A/segend_B/segbend Empties) and rebuild in
    place, exactly what the automatic depsgraph handler (`live_edit.py`) does on every drag.
    Use this if 'Live Edit From Handles' is off, or if a drag's automatic update didn't fire for
    any reason -- selecting the piece (or one of its handles) and pressing this always works."""
    bl_idname = "rka.rebuild_from_handles"
    bl_label = "Rebuild From Handles"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _live_edit_target_collection(context) is not None

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        if coll is None:
            self.report({'ERROR'}, "Select an intersection/segment (or one of its handle "
                                    "Empties) first")
            return {'CANCELLED'}
        _rebuild_piece_in_place(context, coll)
        self.report({'INFO'}, "Rebuilt '%s' from its current handle positions" % coll.name)
        return {'FINISHED'}


class RKA_OT_set_lane_map(bpy.types.Operator):
    """Change the 'Lane Map Override' on an ALREADY-BUILT intersection and rebuild in place --
    the persistent counterpart to `RKA_OT_build_intersection`'s own `lane_map` field, which only
    ever appears on Blender's own F9 'Adjust Last Operation' panel and (like every F9 field)
    silently stops applying the moment any other action runs. Previously the only way to change
    it afterward was hand-editing the `rka_lane_map` Custom Property's raw nested dict directly via
    Blender's Object/Collection Properties panel, then separately triggering a rebuild yourself --
    workable but unfriendly, and easy to typo since there's no validation until the next
    (unrelated) rebuild silently reads it. This pops up a text-entry dialog with the SAME
    'From>To:in-out,in-out; From2>To2:in-out' mini-syntax the build operator uses
    (`parse_lane_map`), pre-filled with the intersection's current override if it has one, and
    validates immediately on OK -- a malformed clause reports an error and changes nothing, rather
    than corrupting the stored override.

    Blank text clears the override entirely (reverts to the default i->i lane pairing everywhere),
    the same as never having set one."""
    bl_idname = "rka.set_lane_map"
    bl_label = "Set Lane Map Override"
    bl_options = {'REGISTER', 'UNDO'}

    lane_map_text: bpy.props.StringProperty(
        name="Lane Map Override", description="'From>To:in-out,in-out; From2>To2:in-out' -- "
        "blank clears the override (default i->i pairing everywhere)", default="")

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and "rka_arm_names" in coll.keys()

    def invoke(self, context, event):
        coll = _live_edit_target_collection(context)
        if coll is not None and custom_props.LANE_MAP_KEY in coll.keys():
            current = custom_props.read_lane_map_override(coll)
            self.lane_map_text = "; ".join(
                "%s>%s:%s" % (frm, to, ",".join("%d-%d" % p for p in pairs))
                for (frm, to), pairs in current.items())
        else:
            self.lane_map_text = ""
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        if coll is None or "rka_arm_names" not in coll.keys():
            self.report({'ERROR'}, "No active intersection piece")
            return {'CANCELLED'}
        try:
            lane_map = parse_lane_map(self.lane_map_text)
        except ValueError as exc:
            self.report({'ERROR'}, "Lane Map Override: %s" % exc)
            return {'CANCELLED'}
        if lane_map is None:
            if custom_props.LANE_MAP_KEY in coll.keys():
                del coll[custom_props.LANE_MAP_KEY]
        else:
            coll[custom_props.LANE_MAP_KEY] = custom_props.lane_map_to_custom(lane_map)
        _rebuild_piece_in_place(context, coll)
        self.report({'INFO'}, "'%s' lane map override -> %s"
                     % (coll.name, "cleared" if lane_map is None else "%d clause(s)" % len(lane_map)))
        return {'FINISHED'}


# 2026-08, user-reported: the pavement/curb material dropdowns listed every one of
# kit_common.MATS's 21 entries, including Tokyo-urban-set/building-only materials (glass, neon,
# screen, brick, glasscurtain, steel, shink, roof, wood, leaf, accent, trim, metal) that no road
# code ever assigns -- confirmed by inspection, the actual road call sites only ever use these 5
# keys (asphalt=pavement, concrete=curb/median/sidewalk default, line_y/line_w=lane markings,
# dirt=occasional ground fill). `MATS` itself stays untouched (other kits still need the rest);
# only the picker is scoped down, to reduce the maintenance/confusion surface. Replaces the old
# MATKEY_ITEMS (= every sorted(MATS.keys()), no callers left).
#
# 'concrete_tile' (2026-08, user-asked how to keep a tiled-paving LOOK on a sidewalk/curb without
# discrete rigid ASSET tiles that pinch on a curve) -- a procedural, world-position-based checker
# pattern, see `kit_common.TILED_MATS`'s own module comment. Sidewalk currently shares Curb's own
# matkey (`_populate_segment_mesh_gn`'s procedural sidewalk sweep passes `matkey=curb_matkey`), so
# it's already reachable from THIS one picker with no separate sidewalk-material control needed.
ROAD_MATKEY_ITEMS = tuple((k, k, "") for k in
                           ("asphalt", "concrete", "concrete_tile", "line_y", "line_w", "dirt"))


def _set_piece_matkey(context, target, matkey):
    """Shared by RKA_OT_set_pavement_matkey/RKA_OT_set_curb_matkey -- see either's docstring for
    the full rationale (2026-07-28, user-reported: material was a hardcoded Python literal at
    every build call site, never exposed or persisted anywhere, so there was no way to change it
    after the initial build at all). Returns (coll, error_message_or_None)."""
    coll = _live_edit_target_collection(context)
    if coll is None:
        return None, "No active piece"
    key = "rka_curb_matkey" if target == 'CURB' else (
        "rka_pad_matkey" if "rka_arm_names" in coll.keys() else "rka_pave_matkey")
    coll[key] = matkey
    _rebuild_piece_in_place(context, coll)
    if target == 'PAVEMENT':
        # An intersection's pad is fully regenerated by _rebuild_piece_in_place (reads
        # rka_pad_matkey fresh every time) -- this direct update is only needed for a GN
        # segment/transition's spine, which a rebuild deliberately never deletes/recreates (its
        # own control points ARE the live-edited shape), so it wouldn't otherwise pick up the new
        # rka_pave_matkey. local_object() simply won't resolve "spine_<name>" on an intersection
        # collection, so this is a safe no-op there.
        spine = local_object("spine_%s" % coll.name)
        if spine is not None:
            paths.kc.set_road_spine_material(spine, matkey)
    return coll, None


class RKA_OT_set_pavement_matkey(bpy.types.Operator):
    """Change the pavement (segment/transition spine) or pad (intersection) material on an
    ALREADY-BUILT piece -- see `_set_piece_matkey`'s docstring for the full rationale. A separate
    operator (not a shared one with a `target` enum property) specifically so the panel can use
    `layout.operator_menu_enum` for a clean dropdown over the full material list -- that API
    invokes the operator with only the ONE enum property (`matkey`) set from the menu choice, with
    no way to also pre-select a second `target` property per button."""
    bl_idname = "rka.set_pavement_matkey"
    bl_label = "Set Pavement/Pad Material"
    bl_options = {'REGISTER', 'UNDO'}

    matkey: bpy.props.EnumProperty(name="Material", items=ROAD_MATKEY_ITEMS, default='asphalt')

    @classmethod
    def poll(cls, context):
        return _live_edit_target_collection(context) is not None

    def execute(self, context):
        coll, err = _set_piece_matkey(context, 'PAVEMENT', self.matkey)
        if err:
            self.report({'ERROR'}, err)
            return {'CANCELLED'}
        self.report({'INFO'}, "'%s' pavement/pad material -> %s" % (coll.name, self.matkey))
        return {'FINISHED'}


class RKA_OT_set_curb_matkey(bpy.types.Operator):
    """Change the curb material on an ALREADY-BUILT piece -- see `_set_piece_matkey`'s docstring
    for the full rationale, and `RKA_OT_set_pavement_matkey`'s for why this is a separate operator
    rather than one shared class with a `target` property."""
    bl_idname = "rka.set_curb_matkey"
    bl_label = "Set Curb Material"
    bl_options = {'REGISTER', 'UNDO'}

    matkey: bpy.props.EnumProperty(name="Material", items=ROAD_MATKEY_ITEMS, default='concrete')

    @classmethod
    def poll(cls, context):
        return _live_edit_target_collection(context) is not None

    def execute(self, context):
        coll, err = _set_piece_matkey(context, 'CURB', self.matkey)
        if err:
            self.report({'ERROR'}, err)
            return {'CANCELLED'}
        self.report({'INFO'}, "'%s' curb material -> %s" % (coll.name, self.matkey))
        return {'FINISHED'}


def _select_piece_objects(context, coll):
    """Select every object in `coll` (a piece collection), origin marker active + Pivot Point set
    to 'Active Element'. Shared by `RKA_OT_select_piece` (from whatever's already active) and
    `RKA_OT_select_piece_by_name` (from a name, no active-object precondition)."""
    for o in context.selected_objects:
        o.select_set(False)
    for o in coll.objects:
        o.select_set(True)
    marker = get_or_create_origin_marker(coll, custom_props.read_origin(coll))
    if marker is not None:
        marker.select_set(True)
        context.view_layer.objects.active = marker
        context.scene.tool_settings.transform_pivot_point = 'ACTIVE_ELEMENT'
    return marker


class RKA_OT_select_piece(bpy.types.Operator):
    """Select EVERY object belonging to the active piece (intersection/segment/lane transition) --
    the "select the whole thing" answer, instead of manually hunting through the Outliner or
    box-selecting in the viewport (which can miss a small marker Empty). Reuses the same
    `_live_edit_target_collection` resolution `Freeze For Move` uses, so it works from any object
    (or Outliner collection) belonging to the piece, frozen or not -- this is a pure selection
    convenience, it never touches `rka_live_edit`. The piece's origin marker ends up active (and
    Pivot Point set to 'Active Element'), so a follow-up Grab/Rotate pivots sensibly whether or not
    you've also run `Freeze For Move`.

    **This operator's `poll()` needs something piece-related ALREADY active/selected** -- it's a
    "select the REST of this piece" tool, not a bootstrapping one. To pick a FIRST piece from
    nothing (no Outliner click needed), use `RKA_OT_select_piece_by_name` instead (the panel's
    piece list button -- see `panel.py`)."""
    bl_idname = "rka.select_piece"
    bl_label = "Select Piece"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _live_edit_target_collection(context) is not None

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        if coll is None:
            self.report({'ERROR'}, "Select an intersection/segment (or one of its handle "
                                    "Empties) first")
            return {'CANCELLED'}
        _select_piece_objects(context, coll)
        self.report({'INFO'}, "Selected all %d object(s) in '%s'" % (len(coll.objects), coll.name))
        return {'FINISHED'}


class RKA_OT_select_piece_by_name(bpy.types.Operator):
    """Select a piece by its COLLECTION NAME directly -- 2026-07-28, user-reported: with nothing
    already selected, `RKA_OT_select_piece`'s poll() always failed (it needs something
    piece-related ALREADY active), so there was no panel-only way to select a FIRST piece at all,
    only via the Outliner. Unconditional poll (`coll_name` just needs to resolve to a real LOCAL
    piece collection) -- the panel's "Pieces in this file" list (see `panel.py`) is built from
    every `_is_piece_collection` match and wires one of these per piece, `coll_name` preset to that
    piece's own name via the button's own operator properties."""
    bl_idname = "rka.select_piece_by_name"
    bl_label = "Select Piece By Name"
    bl_options = {'REGISTER', 'UNDO'}

    coll_name: bpy.props.StringProperty(name="Piece", default="")

    def execute(self, context):
        coll = local_collection(self.coll_name)
        if coll is None or not _is_piece_collection(coll):
            self.report({'ERROR'}, "'%s' is not a local road_kit_authoring piece collection"
                         % self.coll_name)
            return {'CANCELLED'}
        _select_piece_objects(context, coll)
        self.report({'INFO'}, "Selected all %d object(s) in '%s'" % (len(coll.objects), coll.name))
        return {'FINISHED'}


class RKA_OT_select_road_network(bpy.types.Operator):
    """Select EVERY object belonging to EVERY local road piece (intersection/segment/lane
    transition) in this file in one click -- the missing "select everything" step the "Moving/
    rotating MANY pieces at once" workflow (see panel: 'Freeze ALL For Move' -> select everything
    -> Grab/Rotate/Move -> 'Unfreeze ALL & Rebuild') previously left to manual Outliner/box-select.

    Deliberately a PURE SELECTION tool -- no parenting, no joining, nothing moved or re-parented.
    Blender's own multi-object Grab/Rotate (any pivot, 'Median Point' is fine here -- unlike
    `Freeze For Move`'s single-piece warning against it, which is about a piece's own LOCAL-space
    generated sub-objects, not a whole-network multi-select) already moves/rotates every selected
    object together as a genuinely rigid group -- confirmed the same mechanism
    `get_or_create_origin_marker`'s own docstring documents for relocating a single piece (select
    its whole collection, Grab/Rotate it). Parenting every piece under a shared root Empty was
    considered and REJECTED instead: several rebuild functions (e.g.
    `rebuild_intersection_in_place`) read an arm/origin marker's `.location` directly as an
    absolute WORLD position, never `.matrix_world` -- an assumption that only holds today because
    these markers are never parented. Parenting them would silently break every parented piece's
    own live-edit angle math the instant a shared parent moved (`.location` staying stale/local
    while the piece visually moved with its parent) -- a real correctness regression for a cosmetic
    convenience. A pure selection tool gets the same practical outcome with none of that risk.

    Run `Freeze ALL For Move` FIRST if you want zero risk of live-edit regenerating anything
    mid-drag (recommended for more than a couple of pieces) -- this operator doesn't freeze
    anything itself, it only selects."""
    bl_idname = "rka.select_road_network"
    bl_label = "Select Whole Road Network"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(coll.library is None and _is_piece_collection(coll)
                   for coll in bpy.data.collections)

    def execute(self, context):
        for o in context.selected_objects:
            o.select_set(False)
        pieces = [coll for coll in bpy.data.collections
                  if coll.library is None and _is_piece_collection(coll)]
        total = 0
        last_marker = None
        for coll in pieces:
            for o in coll.objects:
                o.select_set(True)
                total += 1
            marker = get_or_create_origin_marker(coll, custom_props.read_origin(coll))
            if marker is not None:
                last_marker = marker
        if last_marker is not None:
            context.view_layer.objects.active = last_marker
        self.report({'INFO'}, "Selected %d object(s) across %d road piece(s)" %
                     (total, len(pieces)))
        return {'FINISHED'}


class RKA_OT_delete_piece(bpy.types.Operator):
    """Fully delete the active piece (intersection/segment/lane transition) -- every marker
    (arm_*/port_*/segend_*/segbend_*/origin) AND every generated object AND the collection itself,
    not just the generated mesh `clear_generated_mesh_objects` clears for a live-edit rebuild
    (which deliberately keeps markers -- the wrong tool for actually removing a piece).

    Reuses `session_common.remove_collection_recursive` (`blender/lib/session_common.py`) --
    already reachable from this addon via the same `sys.path` `paths.py` sets up (the same
    one-line import `ops_world_session.py` already uses), the SAME recursive collection+contents
    removal every world-session tool already relies on, just applied to an in-file piece
    collection instead of a whole-piece `Piece__<id>` wrapper -- no new removal logic.

    Safe with respect to other pieces: lane connectivity is proximity-based at bake time (never a
    stored object reference -- see CLAUDE.md/LaneGraph), and this session's own `rka_linked_to`
    (live connectivity between pieces) already treats a link to a deleted marker as a silent
    no-op, so deleting a piece other pieces were extended from/linked to never dangles or crashes
    anything -- it just stops propagating to whatever depended on it.

    Confirms first (X/Delete on a whole piece can remove a lot of authored work in one click) --
    the same `invoke_confirm` pattern this addon already uses for other bulk-destructive
    operators."""
    bl_idname = "rka.delete_piece"
    bl_label = "Delete Piece"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _live_edit_target_collection(context) is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        if coll is None:
            self.report({'ERROR'}, "Select an intersection/segment (or one of its handle "
                                    "Empties) first")
            return {'CANCELLED'}
        name, n_objects = coll.name, len(coll.objects)
        sc.remove_collection_recursive(coll)
        self.report({'INFO'}, "Deleted '%s' (%d object(s))" % (name, n_objects))
        return {'FINISHED'}


def _is_link_target_marker(obj):
    """True if `obj` is a valid link TARGET -- any of this addon's own anchor Empties: an
    intersection's `arm_*`, a plain segment's `port_A`/`port_B`, or another piece's own
    `rka_origin_marker` (so links can chain: segment -> segment -> ...). See
    `live_edit.RKA_LINKED_TO_KEY`'s module-docstring for the connectivity model this feeds."""
    return (obj is not None and obj.type == 'EMPTY'
            and ("rka_arm_name" in obj.keys() or "rka_port" in obj.keys()
                 or ORIGIN_MARKER_KEY in obj.keys()))


def _is_link_dependent_marker(obj):
    """True if `obj` is a valid link DEPENDENT for `RKA_OT_connect_markers` -- narrower than a
    target: an intersection's `arm_*` (its own position IS the geometry driver, see
    `live_edit.move_dependent_marker`), a curve-backed segment/transition's own origin marker (the
    same anchor `ops_segment._stamp_link` already uses for the automatic `Extend From Arm`/
    `Extend From Port` case, always == the spine's FIRST point), or -- 2026-08, the dual-end
    linking fix (ROAD_JOINT_TRANSITION_STUDY.md finding #3) -- a plain segment's `port_A`/`port_B`
    marker (== the spine's first/last point respectively).

    `port_*` used to be excluded entirely ("purely derived/cosmetic... making it the dependent
    would have no lasting effect: the next rebuild would silently snap it back to the spine's own
    endpoint") -- true only because nothing ever WROTE a link-driven position into the spine's
    endpoint before `live_edit.move_dependent_marker` gained that ability alongside the origin
    marker case (see its own docstring): a live-edit rebuild now re-derives `port_A`/`port_B`'s
    position FROM the spine's current endpoint, which a link on that port already moved -- so the
    re-snap is consistent, not a silent revert. This is what lets a segment's FAR end (previously
    only ever a freely-dragged, never-auto-following point) also track a joint automatically, and
    -- when BOTH ends are linked -- lets `move_dependent_marker` solve the whole spine's shape
    instead of one rigid single-anchor transform."""
    if obj is None or obj.type != 'EMPTY':
        return False
    if "rka_arm_name" in obj.keys():
        return True
    if not obj.users_collection or "rka_curve_object" not in obj.users_collection[0].keys():
        return False
    return ORIGIN_MARKER_KEY in obj.keys() or obj.get("rka_port") in ("A", "B")


class RKA_OT_connect_markers(bpy.types.Operator):
    """Link two ALREADY-BUILT, independently-positioned pieces so one follows the other from now
    on -- the after-the-fact counterpart to the link `Extend From Arm`/`Extend From Port` already
    stamp automatically when building a brand-new piece off an arm/port (see
    `live_edit.RKA_LINKED_TO_KEY`'s docstring for the full connectivity model).

    Select the TARGET marker first (an `arm_*`/`port_*`/origin anchor on the piece that should
    stay put and be followed), then Shift-click the DEPENDENT marker last so it becomes the
    active object (an `arm_*` or a curve-backed segment/transition's origin anchor, on the piece
    that should move to and from then on follow the target) -- the same "active = last selected"
    convention Blender's own multi-object operators use (Snap To Active, Ctrl+P Parent, ...).

    Snaps the dependent to the target's exact current position (a one-time correction so linking
    two pieces that don't already meet leaves no visible gap/overlap), stamps `rka_linked_to`,
    and rebuilds the dependent's own piece immediately."""
    bl_idname = "rka.connect_markers"
    bl_label = "Connect Markers (Dependent Follows Target)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        dependent = context.active_object
        others = [o for o in context.selected_objects if o is not dependent]
        return (_is_link_dependent_marker(dependent) and len(others) == 1
                and _is_link_target_marker(others[0]))

    def execute(self, context):
        from . import live_edit
        dependent = context.active_object
        target = next(o for o in context.selected_objects if o is not dependent)
        dep_coll = dependent.users_collection[0] if dependent.users_collection else None
        tgt_coll = target.users_collection[0] if target.users_collection else None
        if dep_coll is not None and dep_coll == tgt_coll:
            self.report({'ERROR'}, "Can't link a piece's marker to another marker on the SAME piece")
            return {'CANCELLED'}
        with live_edit.rebuilding():
            live_edit.move_dependent_marker(dep_coll, dependent, target)
        dependent[live_edit.RKA_LINKED_TO_KEY] = target.name
        if dep_coll is not None:
            _rebuild_piece_in_place(context, dep_coll)
        self.report({'INFO'}, "'%s' now follows '%s'" % (dependent.name, target.name))
        return {'FINISHED'}


class RKA_OT_disconnect_marker(bpy.types.Operator):
    """Clear `rka_linked_to` from the active marker -- an explicit break of a live connectivity
    link without first moving anything. (The common case doesn't need this: dragging a linked
    dependent marker away from its target auto-breaks the link on its own -- see
    `live_edit._break_stale_links`. This is for breaking a link while leaving the piece exactly
    where it currently sits.)"""
    bl_idname = "rka.disconnect_marker"
    bl_label = "Disconnect Marker"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from . import live_edit
        obj = context.active_object
        return obj is not None and live_edit.RKA_LINKED_TO_KEY in obj.keys()

    def execute(self, context):
        from . import live_edit
        obj = context.active_object
        target_name = obj.get(live_edit.RKA_LINKED_TO_KEY, "?")
        del obj[live_edit.RKA_LINKED_TO_KEY]
        self.report({'INFO'}, "'%s' no longer follows '%s'" % (obj.name, target_name))
        return {'FINISHED'}


class RKA_OT_select_arm(bpy.types.Operator):
    """Isolate a single arm_* marker Empty as the sole selection/active object -- the quick way to
    go from 'everything selected' (e.g. after `Select Piece`) back to just one arm, so its own
    origin is what a subsequent Grab+snap (Shift+S / Ctrl-drag) moves and pivots around. Safe to
    do while the intersection is frozen (`Freeze For Move`): a frozen piece's `live_edit.py`
    handler skips it entirely, so nothing fights a manual reposition of one arm until you run
    `Unfreeze & Rebuild` -- see `rebuild_intersection_in_place`'s docstring for how a deliberately
    snapped arm's exact position (angle AND distance) is now preserved on that rebuild.

    Resolves the arm WITHIN the active piece's own collection (via
    `_live_edit_target_collection`), not by a global `arm_<name>` object-name lookup -- arm names
    are only unique PER intersection ('A', 'B', ... on every one of them), so a global lookup could
    silently select a same-named arm belonging to a completely different intersection."""
    bl_idname = "rka.select_arm"
    bl_label = "Select Arm"
    bl_options = {'REGISTER', 'UNDO'}

    arm_name: bpy.props.StringProperty(name="Arm", default="")

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and "rka_arm_names" in coll.keys()

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        if coll is None:
            self.report({'ERROR'}, "Activate an intersection's collection, or one of its "
                                    "markers/objects, first")
            return {'CANCELLED'}
        obj = next((o for o in coll.objects if o.get("rka_arm_name") == self.arm_name), None)
        if obj is None:
            self.report({'ERROR'}, "No arm named '%s' in '%s'" % (self.arm_name, coll.name))
            return {'CANCELLED'}
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {'FINISHED'}


def _next_arm_name(existing):
    """First unused single letter A-Z, else 'ArmN' -- matches `preset_nway`'s default naming."""
    for i in range(26):
        c = chr(ord('A') + i)
        if c not in existing:
            return c
    n = 0
    while ("Arm%d" % n) in existing:
        n += 1
    return "Arm%d" % n


def _widest_gap_angle(angles):
    """Midpoint angle (deg) of the largest angular gap between `angles` (wrapping) -- where a
    newly added arm is placed by default so it doesn't collide with an existing one."""
    if not angles:
        return 0.0
    ordered = sorted(a % 360.0 for a in angles)
    n = len(ordered)
    best_gap, best_mid = -1.0, 0.0
    for i in range(n):
        a, b = ordered[i], ordered[(i + 1) % n]
        gap = (b - a) % 360.0
        if gap == 0.0:
            gap = 360.0
        if gap > best_gap:
            best_gap, best_mid = gap, (a + gap / 2.0) % 360.0
    return best_mid


def _propagate_from_arm(context, arm_obj):
    """After a button (not a drag) changes an arm's width-affecting state (`rka_arm_lanes`/
    `rka_arm_lanes_out`/`rka_arm_oneway`) and rebuilds its OWN intersection, cascade the same
    width/lane sync to any segment linked to this arm -- these operators bypass the depsgraph
    handler entirely (they mutate a custom property + call `rebuild_intersection_in_place`
    directly), so without this a linked segment's width would only catch up the next time the
    arm ALSO happens to get dragged. Wrapped in `live_edit.rebuilding()` per
    `live_edit._propagate_links`'s own contract (it mutates marker/spine state itself)."""
    from . import live_edit
    with live_edit.rebuilding():
        live_edit._propagate_links({arm_obj.name})


class RKA_OT_adjust_arm_lanes(bpy.types.Operator):
    """+/- the active arm_* marker's lane count (`rka_arm_lanes`) and immediately rebuild its
    intersection in place. The live-edit drag handler only watches for TRANSFORM changes, not
    custom-property edits, so hand-editing `rka_arm_lanes` in the Custom Properties panel needs a
    manual 'Rebuild From Handles' afterward to take effect -- this button does both in one click,
    the reliable answer to "still can't tweak lane count"."""
    bl_idname = "rka.adjust_arm_lanes"
    bl_label = "Adjust Arm Lanes"
    bl_options = {'REGISTER', 'UNDO'}

    delta: bpy.props.IntProperty(default=1)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and "rka_arm_name" in obj.keys()

    def execute(self, context):
        obj = context.active_object
        coll = obj.users_collection[0]
        new_lanes = max(1, min(4, int(obj.get("rka_arm_lanes", 1)) + self.delta))
        obj["rka_arm_lanes"] = new_lanes
        rebuild_intersection_in_place(context, coll)
        _propagate_from_arm(context, obj)
        self.report({'INFO'}, "Arm '%s' lanes -> %d" % (obj.get("rka_arm_name", "?"), new_lanes))
        return {'FINISHED'}


class RKA_OT_adjust_arm_median_width(bpy.types.Operator):
    """+/- the active arm_* marker's OWN median width (`rka_arm_median_width`) and immediately
    rebuild its intersection in place -- the per-arm counterpart to
    `ops_segment.RKA_OT_adjust_median_width`/`_end` (2026-08, user-reported: "each intersection arm
    [should]... have [an] idea of median[,] to expand the median of the incoming arm... one arm can
    use as transition to ease out the median from high count to low count"). PER-ARM, not shared
    across the intersection -- `intersection_kit.Arm.median_width` is a field on that ONE arm, so
    one busy approach can carry a wide median while its neighbors stay flush. Feeds straight into
    `in_width`/`out_width`/`in_offset`/`out_offset` (see `Arm.median_half`), so the pad/curb cap
    AND every lane centerline at this arm shift outward together -- and into
    `live_edit._arm_joint_state`, so a segment linked here now tapers its own median against this
    arm's REAL value instead of always collapsing to 0. Only applies while this arm has lanes in
    BOTH directions (`Arm.median_half`'s "genuine two-way" rule) -- a one-way arm's median is
    silently inert, matching a segment's identical rule."""
    bl_idname = "rka.adjust_arm_median_width"
    bl_label = "Adjust Arm Median Width"
    bl_options = {'REGISTER', 'UNDO'}

    delta: bpy.props.FloatProperty(default=1.0)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and "rka_arm_name" in obj.keys()

    def execute(self, context):
        obj = context.active_object
        coll = obj.users_collection[0]
        new_median = max(0.0, obj.get("rka_arm_median_width", 0.0) + self.delta)
        obj["rka_arm_median_width"] = new_median
        rebuild_intersection_in_place(context, coll)
        _propagate_from_arm(context, obj)
        self.report({'INFO'}, "Arm '%s' median -> %.1fm" % (obj.get("rka_arm_name", "?"), new_median))
        return {'FINISHED'}


class RKA_OT_toggle_arm_traffic_light(bpy.types.Operator):
    """Toggle the active arm_* marker's OWN traffic light (`rka_arm_traffic_light`) on/off and
    immediately rebuild its intersection in place -- 2026-08, user-requested: "remove the lamp
    logic for intersection, but rather leave called 'traffic light'... the lamp is per arm". Off
    by default on every arm (same convention as `rka_arm_median_width`'s 0.0 default), so a fresh
    intersection has none until switched on per-arm here. See
    `ops_intersection._populate_intersection_traffic_lights` for placement math and
    `RKA_OT_adjust_arm_traffic_light_radius` for the per-arm offset knob."""
    bl_idname = "rka.toggle_arm_traffic_light"
    bl_label = "Toggle Arm Traffic Light"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and "rka_arm_name" in obj.keys()

    def execute(self, context):
        obj = context.active_object
        coll = obj.users_collection[0]
        new_state = not obj.get("rka_arm_traffic_light", False)
        obj["rka_arm_traffic_light"] = new_state
        rebuild_intersection_in_place(context, coll)
        self.report({'INFO'}, "Arm '%s' traffic light -> %s"
                     % (obj.get("rka_arm_name", "?"), "ON" if new_state else "OFF"))
        return {'FINISHED'}


class RKA_OT_adjust_arm_traffic_light_radius(bpy.types.Operator):
    """+/- the active arm_* marker's OWN traffic-light diagonal offset (`rka_arm_traffic_light_
    radius`, meters beyond the curb corner -- see `_populate_intersection_traffic_lights`'s own
    docstring for the placement math) and rebuild in place. Refuses to go below 0."""
    bl_idname = "rka.adjust_arm_traffic_light_radius"
    bl_label = "Adjust Arm Traffic Light Radius"
    bl_options = {'REGISTER', 'UNDO'}

    delta: bpy.props.FloatProperty(default=0.5, unit='LENGTH')

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and "rka_arm_name" in obj.keys()

    def execute(self, context):
        obj = context.active_object
        coll = obj.users_collection[0]
        cur = obj.get("rka_arm_traffic_light_radius", TRAFFIC_LIGHT_DEFAULT_RADIUS)
        new_radius = max(0.0, cur + self.delta)
        obj["rka_arm_traffic_light_radius"] = new_radius
        rebuild_intersection_in_place(context, coll)
        self.report({'INFO'}, "Arm '%s' traffic light radius -> %.1fm"
                     % (obj.get("rka_arm_name", "?"), new_radius))
        return {'FINISHED'}


class RKA_OT_adjust_intersection_sidewalk_width(bpy.types.Operator):
    """+/- an intersection's sidewalk width (`rka_sidewalk_width`, applied around every arm, both
    edges -- see `_populate_intersection_sidewalks`) and rebuild in place -- the
    intersection counterpart of `ops_segment.RKA_OT_adjust_sidewalk_width` (2026-08, user-reported:
    intersections had NO persistent sidewalk control at all, only the build-time F9 field). One
    value for the whole intersection (not per-side/per-arm -- a corner isn't a single 2-endpoint
    direction the way a segment is). Refuses to go negative."""
    bl_idname = "rka.adjust_intersection_sidewalk_width"
    bl_label = "Adjust Intersection Sidewalk Width"
    bl_options = {'REGISTER', 'UNDO'}

    delta: bpy.props.FloatProperty(default=1.0, unit='LENGTH')

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and "rka_arm_names" in coll.keys()

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        if coll is None or "rka_arm_names" not in coll.keys():
            self.report({'ERROR'}, "No active intersection")
            return {'CANCELLED'}
        new_val = max(0.0, coll.get("rka_sidewalk_width", 0.0) + self.delta)
        coll["rka_sidewalk_width"] = new_val
        _rebuild_piece_in_place(context, coll)
        self.report({'INFO'}, "'%s' sidewalk width -> %.2fm" % (coll.name, new_val))
        return {'FINISHED'}


class RKA_OT_set_intersection_sidewalk_asset(bpy.types.Operator):
    """Set (or clear) an intersection's sidewalk kit piece (`rka_sidewalk_asset_collection`) and
    rebuild in place -- the intersection counterpart of `ops_segment.RKA_OT_set_sidewalk_asset`.
    Blank `collection_name` (default) falls back to the procedural BOX sweep, matching the
    build-time convention (`_populate_intersection_sidewalks` uses `curb_loop` when
    `sidewalk_asset_obj is None`)."""
    bl_idname = "rka.set_intersection_sidewalk_asset"
    bl_label = "Set Intersection Sidewalk Asset"
    bl_options = {'REGISTER', 'UNDO'}

    collection_name: bpy.props.StringProperty(
        name="Sidewalk Asset", description="Name of a linked collection's mesh object to tile "
        "along every arm's sidewalk -- e.g. 'Kit_Curb_SidewalkTile_L2'. Blank = procedural BOX "
        "sweep", default="")

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and "rka_arm_names" in coll.keys()

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        if coll is None or "rka_arm_names" not in coll.keys():
            self.report({'ERROR'}, "No active intersection")
            return {'CANCELLED'}
        coll["rka_sidewalk_asset_collection"] = self.collection_name
        _rebuild_piece_in_place(context, coll)
        self.report({'INFO'}, "'%s' sidewalk asset -> '%s'"
                     % (coll.name, self.collection_name or "(procedural)"))
        return {'FINISHED'}


class RKA_OT_pick_intersection_sidewalk_asset(bpy.types.Operator):
    """Real DROPDOWN picker for an intersection's `rka_sidewalk_asset_collection` -- the
    discoverable counterpart to `RKA_OT_set_intersection_sidewalk_asset`'s text-typed field (see
    `ops_segment.RKA_OT_pick_curb_asset`'s docstring for the shared rationale). 'None' reverts to
    the procedural BOX sweep (this picker has no separate on/off -- `Sidewalk Width` is the
    on/off, same as before)."""
    bl_idname = "rka.pick_intersection_sidewalk_asset"
    bl_label = "Intersection Sidewalk Asset"
    bl_options = {'REGISTER', 'UNDO'}

    collection_name: bpy.props.EnumProperty(name="Sidewalk Asset", items=linked_asset_picker_items)

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and "rka_arm_names" in coll.keys()

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        if coll is None or "rka_arm_names" not in coll.keys():
            self.report({'ERROR'}, "No active intersection")
            return {'CANCELLED'}
        value = _asset_picker_value(self.collection_name)
        coll["rka_sidewalk_asset_collection"] = value
        _rebuild_piece_in_place(context, coll)
        self.report({'INFO'}, "'%s' sidewalk asset -> '%s'" % (coll.name, value or "(procedural)"))
        return {'FINISHED'}


class RKA_OT_set_intersection_traffic_light_asset(bpy.types.Operator):
    """Set (or clear) an intersection's traffic-light kit piece (`rka_traffic_light_asset_
    collection`) and rebuild in place. Choosing a piece here also needs a per-arm enable (see
    `RKA_OT_toggle_arm_traffic_light`) -- an arm with the light enabled but no piece set here (or
    vice versa) builds nothing, same as every other asset-piece convention in this addon.

    2026-08, user-reported: "traffic light not generate... even when set (no objects are added)."
    Confirmed directly against `world_session.blend`: the asset piece genuinely WAS set, but every
    arm's own `rka_arm_traffic_light` was still False -- from "Set" alone this reads as "doesn't
    work," not as a second required step. Fix: the FIRST time a real (non-blank) piece is set with
    NO arm enabled yet, every arm's own light is auto-enabled too -- mirrors the "first click also
    seeds a sensible default" convention this addon already uses everywhere else (see panel.py's
    module-level "fallback default asset pieces" comment). Only fires when no arm is enabled yet,
    so it can never silently override a deliberately partial per-arm setup (e.g. only 2 of 4 arms
    wired with signals) -- re-setting the SAME or a different piece afterward never re-triggers it."""
    bl_idname = "rka.set_intersection_traffic_light_asset"
    bl_label = "Set Intersection Traffic Light Asset"
    bl_options = {'REGISTER', 'UNDO'}

    collection_name: bpy.props.StringProperty(
        name="Traffic Light Asset", description="Name of a linked collection's mesh object "
        "placed once per arm with its own Traffic Light enabled -- e.g. 'Kit_TrafficLight_L1'. "
        "Blank = no signal built even where enabled", default="")

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and "rka_arm_names" in coll.keys()

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        if coll is None or "rka_arm_names" not in coll.keys():
            self.report({'ERROR'}, "No active intersection")
            return {'CANCELLED'}
        _apply_intersection_traffic_light_asset(context, coll, self.collection_name, self)
        return {'FINISHED'}


def _apply_intersection_traffic_light_asset(context, coll, value, op):
    """Shared body for `RKA_OT_set_intersection_traffic_light_asset` (text field, scripting) and
    `RKA_OT_pick_intersection_traffic_light_asset` (dropdown) -- sets the piece, auto-enables
    every arm on a genuine first-set (see the text-field operator's own docstring for the full
    rationale), rebuilds, and reports through `op`."""
    coll["rka_traffic_light_asset_collection"] = value
    auto_enabled = 0
    if value:
        arm_objs = [o for o in coll.objects if o.name.startswith("arm_")]
        if arm_objs and not any(o.get("rka_arm_traffic_light", False) for o in arm_objs):
            for o in arm_objs:
                o["rka_arm_traffic_light"] = True
            auto_enabled = len(arm_objs)
    _rebuild_piece_in_place(context, coll)
    suffix = " (auto-enabled on %d arm(s))" % auto_enabled if auto_enabled else ""
    op.report({'INFO'}, "'%s' traffic light asset -> '%s'%s" % (coll.name, value or "(none)", suffix))


class RKA_OT_pick_intersection_traffic_light_asset(bpy.types.Operator):
    """Real DROPDOWN picker for an intersection's `rka_traffic_light_asset_collection` -- the
    discoverable counterpart to `RKA_OT_set_intersection_traffic_light_asset`'s text-typed field
    (see `ops_segment.RKA_OT_pick_curb_asset`'s docstring for the shared rationale, and that
    operator's own docstring for the auto-enable-every-arm-on-first-set behaviour, unchanged
    here)."""
    bl_idname = "rka.pick_intersection_traffic_light_asset"
    bl_label = "Intersection Traffic Light Asset"
    bl_options = {'REGISTER', 'UNDO'}

    collection_name: bpy.props.EnumProperty(name="Traffic Light Asset", items=linked_asset_picker_items)

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and "rka_arm_names" in coll.keys()

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        if coll is None or "rka_arm_names" not in coll.keys():
            self.report({'ERROR'}, "No active intersection")
            return {'CANCELLED'}
        _apply_intersection_traffic_light_asset(context, coll, _asset_picker_value(self.collection_name), self)
        return {'FINISHED'}


class RKA_OT_adjust_intersection_sidewalk_asset_spacing(bpy.types.Operator):
    """+/- an intersection's sidewalk-asset tiling spacing (`rka_sidewalk_asset_spacing`) and
    rebuild in place. Clamped to a minimum of 0.1m (matches the build-time property's own
    `min=0.1` -- `kit_common.sample_polyline` divides by spacing). Only visible/relevant while a
    Sidewalk Asset piece is set; harmless (just unused) otherwise."""
    bl_idname = "rka.adjust_intersection_sidewalk_asset_spacing"
    bl_label = "Adjust Intersection Sidewalk Asset Spacing"
    bl_options = {'REGISTER', 'UNDO'}

    delta: bpy.props.FloatProperty(default=0.5, unit='LENGTH')

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and "rka_arm_names" in coll.keys()

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        if coll is None or "rka_arm_names" not in coll.keys():
            self.report({'ERROR'}, "No active intersection")
            return {'CANCELLED'}
        new_val = max(0.1, coll.get("rka_sidewalk_asset_spacing", 2.0) + self.delta)
        coll["rka_sidewalk_asset_spacing"] = new_val
        _rebuild_piece_in_place(context, coll)
        self.report({'INFO'}, "'%s' sidewalk asset spacing -> %.2fm" % (coll.name, new_val))
        return {'FINISHED'}


class RKA_OT_set_arm_angle(bpy.types.Operator):
    """Set the active arm_* marker's bearing (and, optionally, its distance from the
    intersection origin) to an EXACT numeric value and rebuild in place -- the answer to "hard to
    align/adjust edge angle" (2026-08, user-reported): getting an arm to land on an exact bearing
    (e.g. squaring it up at 90 deg to match a linked segment, or fine-tuning by a fraction of a
    degree) by freehand Grab/mouse-drag alone is genuinely fiddly -- Blender's own angle snapping
    doesn't apply to a plain Translate on an Empty. This operator sets the marker's `rotation_
    euler.z` (the arm's now-authoritative angle, see `ensure_arm_angle_migrated`) directly, plus
    its `(x, y)` from `angle_deg`/`tail_length` (-1 = keep the arm's current distance) so the
    visual marker position matches too, exactly like `RKA_OT_add_arm` places a fresh arm -- the
    result is pixel/degree-exact and immediately re-runs the SAME `rebuild_intersection_in_place`
    + link-propagation cascade a real drag would trigger (`_propagate_from_arm`) -- any segment
    linked to this arm re-aligns to the new angle in the same click, not just this intersection."""
    bl_idname = "rka.set_arm_angle"
    bl_label = "Set Arm Angle"
    bl_options = {'REGISTER', 'UNDO'}

    angle_deg: bpy.props.FloatProperty(
        name="Angle", description="Exact bearing (degrees from world +X) to place this arm at",
        default=0.0, min=-360.0, max=360.0)
    tail_length: bpy.props.FloatProperty(
        name="Distance", description="Distance from the intersection origin -- -1 (default) "
        "keeps the arm's current distance, only the angle changes", default=-1.0, min=-1.0,
        unit='LENGTH')

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and "rka_arm_name" in obj.keys()

    def invoke(self, context, event):
        obj = context.active_object
        self.angle_deg = obj.get("rka_arm_angle", 0.0)
        self.tail_length = -1.0
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        obj = context.active_object
        coll = obj.users_collection[0]
        try:
            eff_tail = _apply_arm_angle(context, obj, coll, self.angle_deg, self.tail_length)
        except RkaBuildError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, "Arm '%s' -> %.2f deg at %.2fm" %
                    (obj.get("rka_arm_name", "?"), self.angle_deg, eff_tail))
        return {'FINISHED'}


def _apply_arm_angle(context, obj, coll, angle_deg, tail_length=-1.0):
    """Shared core behind `RKA_OT_set_arm_angle`/`RKA_OT_nudge_arm_angle`: set arm `obj`'s
    `rotation_euler.z` + `.location` to the classic RAY-BASED position (`origin + tail_length *
    direction(angle_deg)`, `tail_length` -1 = keep its current distance from origin) and re-run
    the same rebuild + link-propagation cascade a real drag would trigger. Raises `RkaBuildError`
    if `coll` has no stored origin or the resolved distance isn't positive -- callers report and
    cancel. Returns the effective tail_length actually used.

    Always clears `rka_arm_tail_pos_locked` (2026-08) -- an explicit numeric angle/nudge is the
    classic ray-based workflow, so it deliberately RESETS an arm that was previously matched
    exactly onto an external target (`RKA_OT_aim_arm_at`) back onto its clean ray; re-run that
    operator afterward to re-match if a locked arm's angle needed fine-tuning."""
    k = ik()
    marker = get_or_create_origin_marker(coll, custom_props.read_origin(coll))
    if marker is None:
        raise RkaBuildError("'%s' has no stored origin" % coll.name)
    ox, oy, oz = marker.location.x, marker.location.y, marker.location.z
    rka = context.scene.rka
    z = oz + rka.lane_surface_z
    cur_dist = math.hypot(obj.location.x - ox, obj.location.y - oy)
    eff_tail = cur_dist if tail_length < 0.0 else tail_length
    if eff_tail < 1e-6:
        raise RkaBuildError("Distance must be positive")
    d = k.arm_dir(angle_deg)
    obj.location = (ox + d[0] * eff_tail, oy + d[1] * eff_tail, z)
    obj.rotation_euler = (0.0, 0.0, math.radians(angle_deg))
    obj["rka_arm_angle_migrated"] = True
    obj["rka_arm_tail_pos_locked"] = False
    rebuild_intersection_in_place(context, coll)
    _propagate_from_arm(context, obj)
    return eff_tail


def _resolve_target_angle_deg(target, ox, oy):
    """The angle (deg) `RKA_OT_aim_arm_at` should assign to an arm pointing "at" `target` --
    prefers the TARGET'S OWN facing direction over the raw bearing from the intersection origin
    `(ox, oy)` to the target's position whenever that's available and meaningful, since those two
    are only the SAME value when the target's own piece happens to run exactly radially through
    THIS origin, which is not generally true.

    2026-08 fix, confirmed directly in world_session.blend (user-reported: "even when t[w]o
    points matches" the edges still don't overlap): arm_E's bearing-from-origin to Segment_001's
    `port_A` measured 236.3 deg, while the segment's own ACTUAL tangent there measured 241.2 deg
    -- a real ~5 deg gap that aiming-by-position-bearing alone can never close, because it isn't
    even the right quantity -- position and facing direction are independent unless the piece
    happens to point straight through the origin.

    - `port_A`/`port_B`, or a curve-backed piece's own origin marker (always `== port_A`'s
      position): the OWNING segment's spine tangent AT THAT END
      (`live_edit._spine_tangent_angle`) -- the EXACT value the live joint-sync
      (`_arm_joint_state`, used whenever two pieces are actually LINKED) already treats as "what
      a properly joined arm's angle must equal" for a flush, gap-free cap. Deliberately NOT the
      port's own stored `rka_port_heading_deg` -- that is the OPPOSITE direction (the "extend a
      NEW piece from here" heading a fresh `Extend From Port` would use, see
      `ops_segment._place_segment_ports`), 180 deg off from what an arm butting AGAINST this end
      needs.
    - Another `arm_*` marker: no tangent to defer to (an arm's own angle is already a bearing
      from ITS OWN origin, meaningless to copy directly onto a different intersection) -- always
      the raw bearing from `(ox, oy)` to the target's position.
    - Anything else (a bare Empty, ...): the same raw-bearing fallback, the only sensible
      definition for a target with no direction of its own.

    Returns None if no bearing/tangent can be determined at all (target sits exactly on the
    origin, or -- for a port/origin target -- its segment's spine is missing/degenerate, in which
    case this silently falls through to the position-bearing fallback instead of failing outright)."""
    port_tag = target.get("rka_port")
    is_piece_origin = bool(target.get(ORIGIN_MARKER_KEY, False))
    if port_tag in ("A", "B") or is_piece_origin:
        coll = target.users_collection[0] if target.users_collection else None
        spine_name = coll.get("rka_curve_object") if coll is not None else None
        spine_obj = coll.objects.get(spine_name) if (coll is not None and spine_name) else None
        if spine_io.is_spine(spine_obj):
            end = "end" if port_tag == "B" else "start"
            tangent = live_edit._spine_tangent_angle(spine_obj, end)
            if tangent is not None:
                return math.degrees(tangent) % 360.0
    dx, dy = target.location.x - ox, target.location.y - oy
    if math.hypot(dx, dy) < 1e-6:
        return None
    return math.degrees(math.atan2(dy, dx)) % 360.0


class RKA_OT_aim_arm_at(bpy.types.Operator):
    """Move the active arm_* marker EXACTLY onto a target's position AND rotate it to EXACTLY
    match the target's own facing/tangent -- BOTH at once, not a choice between them -- the
    "visually align this arm with the road it should connect to" answer (2026-08, user-reported,
    with a screenshot: a road stub runs off diagonally but the arm/pad edge cuts straight across
    it; eyeballing or computing the exact angle by hand is slow and error-prone).

    Select the TARGET first, Shift-click the ARM LAST so IT becomes the active object (the one
    this operator repositions) -- same "active = the one being changed" convention
    `RKA_OT_connect_markers` already uses (there: select target, Shift-click the dependent last).

    2026-08 history -- this used to be two separate modes ("Aim At" = tangent-exact, "Snap To" =
    position-exact), because an arm's PAD/CURB cap position used to be locked to `origin + distance
    * direction(angle)` -- one shared-origin ray, the SAME angle driving both where the cap sits
    AND which way it faces, so at most one of position/tangent could ever be exact for a target
    that doesn't happen to sit exactly on that ray. User-reported (world_session.blend, "arm w
    position/edge should adjust to match that segment -- segment/other arms/intersection center
    should NOT move"): the cap's POSITION is now independently settable
    (`intersection_kit.Arm.tail_pos` -- see its docstring) while `angle_deg` still alone controls
    the cap's ORIENTATION and this arm's own corner-fillet geometry with its neighbors (an off-ray
    match on ONE arm cannot distort a neighbor's corner -- `curb_edges`/`_junction_corner_vertex`
    never read `tail_pos` at all), so both position and tangent can now land exactly, together, in
    one click -- the two modes collapsed back into one operator/button.

    Stamps `rka_arm_tail_pos_locked` so future rebuilds (dragging any OTHER arm, adjusting lanes,
    etc.) don't silently pull this arm's marker back onto its clean angle-ray -- see
    `rebuild_intersection_in_place`'s re-snap step. `RKA_OT_set_arm_angle`/`RKA_OT_nudge_arm_angle`
    both CLEAR this lock (an explicit numeric angle/nudge is the classic ray-based workflow) -- if
    an already-matched arm needs fine-tuning afterward, re-run this operator rather than nudging.

    Does NOT move the target or create a link -- run `Connect Markers` afterward if you also want
    this arm to keep tracking the target automatically as it moves later."""
    bl_idname = "rka.aim_arm_at"
    bl_label = "Match Arm To Selected"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj is None or "rka_arm_name" not in obj.keys():
            return False
        others = [o for o in context.selected_objects if o is not obj]
        return len(others) == 1

    def execute(self, context):
        obj = context.active_object
        target = next(o for o in context.selected_objects if o is not obj)
        coll = obj.users_collection[0]
        marker = get_or_create_origin_marker(coll, custom_props.read_origin(coll))
        if marker is None:
            self.report({'ERROR'}, "'%s' has no stored origin" % coll.name)
            return {'CANCELLED'}
        ox, oy, oz = marker.location.x, marker.location.y, marker.location.z
        angle_deg = _resolve_target_angle_deg(target, ox, oy)
        if angle_deg is None:
            self.report({'ERROR'}, "'%s' sits exactly on the intersection origin -- no bearing "
                                    "to aim at" % target.name)
            return {'CANCELLED'}
        rka = context.scene.rka
        z = oz + rka.lane_surface_z
        obj.location = (target.location.x, target.location.y, z)
        obj.rotation_euler = (0.0, 0.0, math.radians(angle_deg))
        obj["rka_arm_angle_migrated"] = True
        obj["rka_arm_tail_pos_locked"] = True
        rebuild_intersection_in_place(context, coll)
        _propagate_from_arm(context, obj)
        self.report({'INFO'}, "Arm '%s' matched to '%s' EXACTLY -- position AND %.2f deg tangent "
                    "both exact, every other arm/the intersection center untouched" %
                    (obj.get("rka_arm_name", "?"), target.name, angle_deg))
        return {'FINISHED'}


class RKA_OT_nudge_arm_angle(bpy.types.Operator):
    """+/- the active arm's angle by a fixed step and rebuild in place -- a quick keyboard/click
    way to fine-tune a facing direction (2026-08, user-reported: setting an exact angle "seem not
    accurate and kind of hard to change") without opening `Set Arm Angle`'s numeric dialog every
    time. Distance from origin is unchanged, matching `RKA_OT_set_arm_angle`."""
    bl_idname = "rka.nudge_arm_angle"
    bl_label = "Nudge Arm Angle"
    bl_options = {'REGISTER', 'UNDO'}

    delta_deg: bpy.props.FloatProperty(default=5.0)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and "rka_arm_name" in obj.keys()

    def execute(self, context):
        obj = context.active_object
        coll = obj.users_collection[0]
        new_angle = (math.degrees(obj.rotation_euler.z) + self.delta_deg) % 360.0
        try:
            _apply_arm_angle(context, obj, coll, new_angle)
        except RkaBuildError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, "Arm '%s' -> %.2f deg" % (obj.get("rka_arm_name", "?"), new_angle))
        return {'FINISHED'}


class RKA_OT_add_arm(bpy.types.Operator):
    """Add a new arm to an existing intersection, placed at the widest angular gap between its
    current arms, and rebuild in place. The answer to "still can't tweak number of arms per
    intersection" -- `rebuild_intersection_in_place` already generalizes to whatever `arm_*`
    Empties exist in the collection (no preset/arm-count is hardcoded downstream), so adding one
    marker is enough. Activate the intersection's collection, or any of its markers, first."""
    bl_idname = "rka.add_arm"
    bl_label = "Add Arm"
    bl_options = {'REGISTER', 'UNDO'}

    lanes: bpy.props.IntProperty(name="Lanes", default=1, min=1, max=4)

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and "rka_arm_names" in coll.keys()

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        k = ik()
        marker = get_or_create_origin_marker(coll, custom_props.read_origin(coll))
        if marker is None:
            self.report({'ERROR'}, "'%s' has no stored origin" % coll.name)
            return {'CANCELLED'}
        ox, oy, oz = marker.location.x, marker.location.y, marker.location.z
        rka = context.scene.rka
        z = oz + rka.lane_surface_z
        tail_length = coll.get("rka_tail_length", 12.0)

        existing = [o for o in coll.objects if "rka_arm_name" in o.keys()]
        existing_names = {o["rka_arm_name"] for o in existing}
        existing_angles = [o.get("rka_arm_angle", 0.0) for o in existing]
        angle_deg = _widest_gap_angle(existing_angles)
        name = _next_arm_name(existing_names)

        d = k.arm_dir(angle_deg)
        arm_obj = bpy.data.objects.new("arm_%s" % name, None)
        arm_obj.empty_display_type = 'SINGLE_ARROW'
        arm_obj.empty_display_size = min(2.0, coll.get("rka_lane_width", 5.0) * 0.4)
        arm_obj.location = (ox + d[0] * tail_length, oy + d[1] * tail_length, z)
        arm_obj.rotation_euler = (0.0, 0.0, math.radians(angle_deg))
        arm_obj["rka_arm_name"] = name
        arm_obj["rka_arm_angle"] = angle_deg
        arm_obj["rka_arm_lanes"] = self.lanes
        arm_obj["rka_arm_oneway"] = ""
        arm_obj["rka_arm_lanes_out"] = 0
        arm_obj["rka_arm_tail_length"] = tail_length
        arm_obj["rka_arm_angle_migrated"] = True   # fresh -- position/rotation already agree
        coll.objects.link(arm_obj)

        rebuild_intersection_in_place(context, coll)
        self.report({'INFO'}, "Added arm '%s' at %.1f deg to '%s'" % (name, angle_deg, coll.name))
        return {'FINISHED'}


class RKA_OT_remove_arm(bpy.types.Operator):
    """Remove the active arm_* marker from its intersection and rebuild in place. Refuses to drop
    below 3 arms (a 2-arm 'intersection' is just a through street -- use a Straight Segment
    instead; this tool only ever adds/removes ARMS, never converts collection types)."""
    bl_idname = "rka.remove_arm"
    bl_label = "Remove Arm"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and "rka_arm_name" in obj.keys()

    def execute(self, context):
        obj = context.active_object
        coll = obj.users_collection[0]
        remaining = len([o for o in coll.objects if "rka_arm_name" in o.keys()]) - 1
        if remaining < 3:
            self.report({'ERROR'}, "Can't remove -- an intersection needs at least 3 arms "
                                    "(has %d)" % (remaining + 1))
            return {'CANCELLED'}
        name = obj.get("rka_arm_name", "?")
        bpy.data.objects.remove(obj, do_unlink=True)
        rebuild_intersection_in_place(context, coll)
        self.report({'INFO'}, "Removed arm '%s' from '%s'" % (name, coll.name))
        return {'FINISHED'}


class RKA_OT_set_arm_oneway(bpy.types.Operator):
    """Set the active arm_* marker's traffic direction and rebuild in place: BOTH (default,
    symmetric -- lanes arrive and leave), IN (this arm only ever RECEIVES traffic -- no outgoing
    lanes, e.g. a one-way street feeding INTO this junction), OUT (this arm only ever SENDS
    traffic -- no incoming lanes, e.g. a one-way exit). Combine with 1 lane
    (`RKA_OT_adjust_arm_lanes`) for a true single-lane one-way arm -- the concrete "can an
    intersection accommodate a one-way, one-lane road" answer."""
    bl_idname = "rka.set_arm_oneway"
    bl_label = "Set Arm Direction"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(name="Direction", items=(
        ('BOTH', "Both Ways", "Symmetric -- lanes arrive and leave"),
        ('IN', "In Only", "Traffic only arrives via this arm (no outgoing lanes)"),
        ('OUT', "Out Only", "Traffic only leaves via this arm (no incoming lanes)"),
    ), default='BOTH')

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and "rka_arm_name" in obj.keys()

    def execute(self, context):
        obj = context.active_object
        coll = obj.users_collection[0]
        obj["rka_arm_oneway"] = "" if self.mode == 'BOTH' else self.mode
        rebuild_intersection_in_place(context, coll)
        _propagate_from_arm(context, obj)
        self.report({'INFO'}, "Arm '%s' direction -> %s" % (obj.get("rka_arm_name", "?"), self.mode))
        return {'FINISHED'}


class RKA_OT_adjust_arm_lanes_out(bpy.types.Operator):
    """ASYMMETRIC WIDENING: +/- the active arm_* marker's `rka_arm_lanes_out` override -- the
    DEPARTING (CCW) lane count only, independent of `rka_arm_lanes` (which keeps governing the
    ARRIVING/CW count) -- and immediately rebuild in place. 0 means "no override, symmetric with
    Lanes" (`Arm.lanes_out=None`, `intersection_kit.py`'s back-compat default); the FIRST press
    from 0 seeds it at the current symmetric lane count before nudging, so pressing +/- from a
    fresh arm feels like "peel this side off and adjust it independently" rather than jumping
    straight to 1. This is the actual "widen only one side" answer -- since arriving lanes occupy
    the CW curb-to-centerline half and departing lanes occupy the CCW half, growing ONE of
    lanes/lanes_out moves ONLY that side's curb edge (see `Arm`'s docstring for why a raw sideways
    shift of an otherwise-symmetric width can't do this correctly)."""
    bl_idname = "rka.adjust_arm_lanes_out"
    bl_label = "Adjust Arm Departing Lanes"
    bl_options = {'REGISTER', 'UNDO'}

    delta: bpy.props.IntProperty(default=1)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and "rka_arm_name" in obj.keys()

    def execute(self, context):
        obj = context.active_object
        coll = obj.users_collection[0]
        current = int(obj.get("rka_arm_lanes_out", 0))
        base = current if current > 0 else int(obj.get("rka_arm_lanes", 1))
        new_lanes_out = max(0, min(4, base + self.delta))
        obj["rka_arm_lanes_out"] = new_lanes_out
        rebuild_intersection_in_place(context, coll)
        _propagate_from_arm(context, obj)
        label = "symmetric (0)" if new_lanes_out == 0 else str(new_lanes_out)
        self.report({'INFO'}, "Arm '%s' departing lanes -> %s" %
                     (obj.get("rka_arm_name", "?"), label))
        return {'FINISHED'}


CLASSES = (RKA_OT_build_intersection, RKA_OT_rebuild_from_handles,
           RKA_OT_select_piece, RKA_OT_select_piece_by_name, RKA_OT_select_road_network,
           RKA_OT_delete_piece, RKA_OT_connect_markers, RKA_OT_disconnect_marker, RKA_OT_select_arm,
           RKA_OT_adjust_arm_lanes, RKA_OT_adjust_arm_median_width,
           RKA_OT_toggle_arm_traffic_light, RKA_OT_adjust_arm_traffic_light_radius,
           RKA_OT_adjust_intersection_sidewalk_width, RKA_OT_set_intersection_sidewalk_asset,
           RKA_OT_pick_intersection_sidewalk_asset,
           RKA_OT_adjust_intersection_sidewalk_asset_spacing,
           RKA_OT_set_intersection_traffic_light_asset,
           RKA_OT_pick_intersection_traffic_light_asset,
           RKA_OT_set_arm_angle, RKA_OT_aim_arm_at,
           RKA_OT_nudge_arm_angle, RKA_OT_add_arm, RKA_OT_remove_arm,
           RKA_OT_set_arm_oneway,
           RKA_OT_adjust_arm_lanes_out, RKA_OT_set_lane_map, RKA_OT_set_pavement_matkey,
           RKA_OT_set_curb_matkey)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
