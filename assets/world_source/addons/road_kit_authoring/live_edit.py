"""Live-editing: drag an arm_*/segend_*/segbend_* marker Empty in the viewport and the owning
intersection/segment mesh rebuilds immediately -- the "bevel-style handle" interaction.

Deliberately NOT a Geometry Nodes rewrite. A true GN rewrite would mean re-deriving the
corner-fillet trig, through-pair detection, variable arm-count handling, and curb-style dispatch
entirely as a node graph -- and since GN can't write the `.lanekit.json` sidecar Godot/WorldBaker
actually consume, the tested Python geometry in `lib/intersection_kit.py` would still have to run
for export, making a GN graph a SECOND, parallel implementation of the same math with real risk of
silently drifting from what gets exported. Instead, a `depsgraph_update_post` handler here detects
a moved marker and reruns the exact same functions that back the fresh-build operators and the
export path (`ops_intersection.rebuild_intersection_in_place`, `ops_segment.rebuild_segment_in_place`)
-- one source of truth for the math, genuinely live in the viewport, no dual-implementation risk.

Trade-off, stated plainly: each drag step triggers a full delete+regenerate of that piece's
curb/lane objects in Python, not a GPU-evaluated node graph, so it won't be as silky as true GN on
a very complex piece. `RKA_SceneSettings.live_edit_enabled` (panel checkbox) is the escape hatch,
and any single piece can opt out via its own `rka_live_edit` custom property.
"""
import bpy

_rebuilding = False


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
    for update in depsgraph.updates:
        obj = update.id
        if isinstance(obj, bpy.types.Object) and obj.type == 'EMPTY' and update.is_updated_transform:
            keys = obj.keys()
            if "rka_arm_name" not in keys and "rka_segend" not in keys and "rka_segbend" not in keys:
                continue
            for coll in obj.users_collection:
                if not coll.get("rka_live_edit", True):
                    continue
                if "rka_arm_names" in coll.keys():
                    dirty_inter.add(coll.name)
                elif "rka_p0" in coll.keys():
                    dirty_seg.add(coll.name)
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

    dirty_curve_seg = set()
    if dirty_curve_names:
        for coll in bpy.data.collections:
            curve_name = coll.get("rka_curve_object")
            if curve_name in dirty_curve_names and coll.get("rka_live_edit", True):
                dirty_curve_seg.add(coll.name)

    if not dirty_inter and not dirty_seg and not dirty_curve_seg:
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
                ops_segment.rebuild_segment_from_curve_in_place(ctx, coll)
    finally:
        _rebuilding = False


def register():
    if _on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)


def unregister():
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
