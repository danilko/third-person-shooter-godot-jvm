"""ops_lane_preview.py -- a manual, on-demand "does this match what Godot will get" visualization:
one real Blender Curve object per exported lane, built directly from the same `points` data
`tools/save_lane_kit.py` writes to the `.lanekit.json` sidecar (via `lane_export.py`, shared by
both). 2026-08, user-requested: "a manual one-time click to form the curve, and remove afterward
with button click, to ensure the port/other data will form current path3d logic is correct in
blender."

Deliberately manual/on-demand, NOT a live-synced overlay like `traffic_viz.py`'s arrows/lane-index
ticks: a prior ALWAYS-regenerating version of this idea (`lanecl_*` lane-centerline curves) was
removed in 2026-08 specifically because live-edit-triggered regeneration cost real authoring-time
churn with no offsetting payoff (see `ops_intersection._populate_intersection_mesh`'s own comment
on their removal) -- a one-click build + a separate one-click clear sidesteps exactly that, the
same way `median_merge.py`'s dedicated-collection idiom does for its own delete+recreate-from-
scratch geometry.

Built in Blender-native space (no Godot axis-flip/z-lift -- see `lane_export.export_piece_dict`'s
`godot_space` parameter) so a preview curve sits directly over the authored mesh in the same space
you're looking at it in, for an easy visual cross-check -- not a byte-for-byte reproduction of the
exported file's own coordinate convention."""
import bpy

from . import lane_export
from . import paths

LANE_PREVIEW_COLLECTION = "RKA_LanePreview"


def _lane_preview_collection(context):
    """The one dedicated collection every preview curve lives in, created + linked to the scene
    root on first use -- same idiom as `median_merge.py`'s own `_median_chain_collection`."""
    coll = bpy.data.collections.get(LANE_PREVIEW_COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(LANE_PREVIEW_COLLECTION)
    if coll.name not in context.scene.collection.children:
        context.scene.collection.children.link(coll)
    return coll


def _clear_collection(coll):
    """Delete every object in `coll` + its now-orphaned curve data, but not the collection itself
    -- the shared body of both operators below (Preview clears any stale prior preview before
    rebuilding; Clear removes everything including the collection)."""
    count = len(coll.objects)
    for obj in list(coll.objects):
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and data.users == 0:
            bpy.data.curves.remove(data)
    return count


# Movement kind -> the material its preview link is drawn in. Deliberately reusing the kit's own
# keys rather than inventing new ones: yellow reads as "crossing traffic" (a turn through a
# junction), white as "staying on this road".
_LINK_MAT = {"THROUGH": "line_w", "EXIT": "accent", "ENTRY": "accent",
             "TURN": "line_y", "LANE_CHANGE": "line_w"}


def _link_curve(name, a, b, coll, matkey, lift=0.35):
    """A short tube from one lane's tail to another's head -- the movement itself, drawn.

    Lifted slightly so it reads above the lane tubes it joins instead of z-fighting them."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = 0.22          # fatter than a lane tube, so a link stands out
    cu.materials.append(paths.kc.mat(matkey))
    sp = cu.splines.new('POLY')
    sp.points.add(2)
    mid = [(a[i] + b[i]) / 2.0 for i in range(3)]
    for i, p in enumerate((a, [mid[0], mid[1], mid[2] + lift], b)):
        sp.points[i].co = (p[0], p[1], p[2] + (lift if i != 1 else 0.0), 1.0)
    obj = bpy.data.objects.new(name, cu)
    coll.objects.link(obj)
    return obj


def _build_connection_preview(pieces, coll):
    """Draw the AUTHORED connections between lanes, resolved exactly as the export resolves them.

    WHY THIS IS WORTH DRAWING. Lane curves alone show where traffic can be, not where it may GO,
    and those are different questions -- an interchange whose geometry looks perfect can still be
    unusable because nothing records the movement (the defect that had 717 lanes carrying zero
    successors). At a junction every lane end sits within a few metres of every other, so looking
    at the curves cannot tell you whether the exit is wired to the right lane; an arrow from the
    source lane's tail to the target lane's head can.

    It runs `lane_kit.combine_pieces`, so what is drawn is the resolved graph the sidecar will
    contain -- `next_refs` turned into real ids and `neighbor_in/out` into `inner_lane`/
    `outer_lane` -- not a separate approximation of it. Objects are named
    `link_<KIND>_<src>__<dst>` so the outliner is searchable, and lane-change links are drawn too
    (thinner, in white) because an exit lane is reachable ONLY by changing lanes and a missing one
    is invisible otherwise."""
    import lane_kit
    combined, _reports = lane_kit.combine_pieces(list(pieces))
    by_id = {l["id"]: l for l in combined.get("lanes", [])}
    n_link = n_lc = 0
    for l in combined.get("lanes", []):
        pts = l.get("points")
        if not pts or len(pts) < 2:
            continue
        tail = pts[-1]
        for k, nid in enumerate(l.get("next", [])):
            tgt = by_id.get(nid)
            if tgt is None or len(tgt.get("points", ())) < 2:
                continue
            kinds = l.get("next_kinds", [])
            kind = kinds[k] if k < len(kinds) else "THROUGH"
            _link_curve("link_%s_%s__%s" % (kind, l["id"], nid), tail, tgt["points"][0],
                        coll, _LINK_MAT.get(kind, "accent"))
            n_link += 1
        # Lane change is drawn from each lane's MIDPOINT, because it is available along the
        # overlap rather than at an endpoint -- drawing it tail-to-head would imply a junction.
        for key in ("inner_lane", "outer_lane"):
            nid = l.get(key)
            tgt = by_id.get(nid) if nid else None
            if tgt is None or len(tgt.get("points", ())) < 2:
                continue
            a = pts[len(pts) // 2]
            b = tgt["points"][len(tgt["points"]) // 2]
            _link_curve("link_LANE_CHANGE_%s__%s" % (l["id"], nid), a, b, coll,
                        _LINK_MAT["LANE_CHANGE"], lift=0.15)
            n_lc += 1
    return n_link, n_lc


class RKA_OT_preview_lane_curves(bpy.types.Operator):
    """Build one real Curve object per exported lane, for EVERY road_kit_authoring piece in the
    current file, in a dedicated 'RKA_LanePreview' collection -- reuses `lane_export.
    collect_pieces` (the exact same per-piece dict reconstruction `tools/save_lane_kit.py` uses
    for the real `.lanekit.json` export), so what you see here is genuinely the same lane data
    that gets ported to Godot's `Path3D`/`Curve3D`, not a separate approximation
    (`traffic_viz.py`'s schematic arrows/ticks are a lighter-weight, always-on alternative for
    "which lane is which" -- this is for verifying the actual curve shape/point data itself).

    Re-running clears and rebuilds from scratch (safe here -- this only ever runs from a direct
    user click, never inside a depsgraph callback, the same precondition `median_merge.py`'s own
    delete+recreate relies on)."""
    bl_idname = "rka.preview_lane_curves"
    bl_label = "Preview Lane Curves"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import os
        stem = (os.path.splitext(os.path.basename(bpy.data.filepath))[0]
                if bpy.data.filepath else "preview")
        pieces = lane_export.collect_pieces(stem, context.scene, bpy.data, godot_space=False)
        if not pieces:
            self.report({'WARNING'}, "No road_kit_authoring pieces found in this file")
            return {'CANCELLED'}

        coll = _lane_preview_collection(context)
        _clear_collection(coll)   # drop any stale preview from a previous run first

        accent_mat = paths.kc.mat("accent")
        count = 0
        for _piece_name, d, _zone_id in pieces:
            for lane in d["lanes"]:
                pts = lane["points"]
                if len(pts) < 2:
                    continue
                cu = bpy.data.curves.new("lanepreview_%s" % lane["id"], 'CURVE')
                cu.dimensions = '3D'
                cu.bevel_depth = 0.15   # a thin visible tube, not a zero-width invisible line
                cu.materials.append(accent_mat)
                sp = cu.splines.new('POLY')
                sp.points.add(len(pts) - 1)
                for i, p in enumerate(pts):
                    sp.points[i].co = (p[0], p[1], p[2], 1.0)
                obj = bpy.data.objects.new(cu.name, cu)
                coll.objects.link(obj)
                count += 1

        n_link, n_lc = _build_connection_preview(pieces, coll)
        self.report({'INFO'}, "Preview: %d lane curve(s) from %d piece(s), %d movement link(s), "
                     "%d lane-change link(s) in 'RKA_LanePreview' (Blender-native space)"
                     % (count, len(pieces), n_link, n_lc))
        return {'FINISHED'}


class RKA_OT_clear_lane_curve_preview(bpy.types.Operator):
    """Delete every curve `RKA_OT_preview_lane_curves` built, plus the 'RKA_LanePreview'
    collection itself. A no-op (still reports FINISHED) if there's nothing to clear."""
    bl_idname = "rka.clear_lane_curve_preview"
    bl_label = "Clear Lane Curve Preview"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        coll = bpy.data.collections.get(LANE_PREVIEW_COLLECTION)
        if coll is None:
            self.report({'INFO'}, "No lane curve preview to clear")
            return {'FINISHED'}
        count = _clear_collection(coll)
        bpy.data.collections.remove(coll)
        self.report({'INFO'}, "Cleared %d lane preview curve(s)" % count)
        return {'FINISHED'}


CLASSES = (RKA_OT_preview_lane_curves, RKA_OT_clear_lane_curve_preview)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
