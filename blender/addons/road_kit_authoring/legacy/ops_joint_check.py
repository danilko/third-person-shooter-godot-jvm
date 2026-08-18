"""ops_joint_check.py -- "are my connections real?", answered in the viewport.

TOUCHING IS NOT CONNECTING (see `lib/lane_joints` for the measurement itself). Two lanes whose
centrelines end at the same point can still be a full lane width apart at their EDGES -- different
widths, a heading break, or a head-on pairing -- and nothing about that is visible while looking
down at a road from 200 m up. This is the authoring-time half of the gate that
`tools/check_road_network.py` runs on the exported sidecar: same code, same numbers, but on the
live scene while there is still something to drag.

WHAT IT REPORTS. Every joint it can find, worst first, in metres, naming the two lanes. A seam
0.4 m out is a car clipping a curb; a seam 3.5 m out is a link joining the wrong pair of lanes.
Those want different fixes, so the report says which it is (`MISALIGNED` vs `DISJOINT`) rather than
collapsing both into "bad".

WHY AN OPERATOR AND NOT A LIVE OVERLAY. The check needs every piece's exported lane data, which
means running the exporters over the whole scene -- far too expensive per depsgraph tick. It is a
button you press when you have finished a junction, the same way `Preview Lane Curves` is.
"""
import bpy

from . import lane_export
from . import ops_intersection as opint


def _lj():
    """Lazy `lib/lane_joints` import -- the deferred-import idiom `spine_io.rs()` uses, so this
    module stays importable before `blender/lib` is on `sys.path`."""
    import lane_joints
    return lane_joints


def collect_scene_lanes(context):
    """Every piece's lanes, in ONE flat list with globally-unique ids -- the same shape
    `tools/check_road_network.py` reads out of the sidecar, so both sides run identical checks.

    Blender-native coordinates (`godot_space=False`): the alignment maths is frame-agnostic, but
    the numbers a user is shown must match what the viewport's N-panel shows them, or a 0.4 m gap
    is impossible to go and find."""
    # `collect_pieces` returns `(coll_name, export_dict, zone_id)` triples, and namespaces ids by
    # the COLLECTION name -- the same key `_select_piece_of` uses to jump to the offending piece.
    stem = bpy.path.basename(bpy.data.filepath).rsplit(".", 1)[0] or "session"
    pieces = lane_export.collect_pieces(stem, context.scene, bpy.data, godot_space=False)
    out = []
    for coll_name, d, _zone in pieces:
        for lane in d.get("lanes", []):
            l = dict(lane)
            l["id"] = "%s__%s" % (coll_name, lane.get("id"))
            l["piece_id"] = coll_name
            out.append(l)
    return out


def _resolve_links(lanes):
    """Turn each lane's symbolic `next_refs` into concrete `(from_id, to_id, kind)` triples.

    `lane_kit.combine_pieces` does this on the export path; doing it again here rather than
    exporting first keeps the button instant and keeps it working on a scene that has never been
    exported. Unresolvable refs are returned too, as links to a missing id, so the report says
    "that link points at nothing" instead of quietly checking one fewer seam."""
    by_role = {}
    for l in lanes:
        key = (l.get("link_group"), l.get("link_role"))
        by_role.setdefault(key, []).append(l)
    by_piece_lane = {(l.get("piece_id"), l.get("id", "").split("__", 1)[-1]): l for l in lanes}
    by_piece_slot = {(l.get("piece_id"), l.get("slot_id")): l for l in lanes if l.get("slot_id")}
    links = []
    for l in lanes:
        for ref in l.get("next_refs") or []:
            if ref.get("piece"):
                # An ordinary joint between two collections -- resolved by piece + lane, the same
                # addressing `lane_kit.resolve_links` uses for these. `lane_id` is preferred over
                # `slot`: two arbitrary pieces can both own a slot called `F0`.
                hit = (by_piece_lane.get((ref["piece"], ref.get("lane_id")))
                       or by_piece_slot.get((ref["piece"], ref.get("slot"))))
                label = "<%s:%s>" % (ref["piece"], ref.get("lane_id") or ref.get("slot"))
            else:
                group = ref.get("group") or l.get("link_group")
                targets = by_role.get((group, ref.get("role")), [])
                hit = next((t for t in targets if t.get("slot_id") == ref.get("slot")), None)
                label = "<%s/%s:%s>" % (group, ref.get("role"), ref.get("slot"))
            links.append((l["id"], hit["id"] if hit else label, ref.get("kind", "")))
        for dst in l.get("next") or []:
            links.append((l["id"], dst, "THROUGH"))
    return links


def check_scene_joints(context):
    """`(problems, n_links, n_lanes)` for the whole scene.

    Two different questions, both answered here. Every link that EXISTS is measured -- that is
    `check_links`. But an authored joint across which NO lane pairs is invisible to that: there is
    no link to measure, and the lane data looks exactly like two pieces that were never connected.
    So the authored joints are asked for separately and any that produced nothing is reported as
    `UNJOINED`. Without this, breaking a seam badly enough makes the complaint disappear along
    with the links, which reads as a clean scene."""
    lj = _lj()
    lanes = collect_scene_lanes(context)
    links = _resolve_links(lanes)
    # `collect_scene_lanes` deliberately reads Blender-native coordinates, so the default
    # ground-plane axes are the right ones here (see `lane_joints.BLENDER_AXES`).
    problems = lj.check_links(lanes, links, axes=lj.BLENDER_AXES)
    problems += [lj.unjoined(a, b) for a, b in lane_export.unjoined_joints(lanes, bpy.data)]
    return problems, len(links), len(lanes)


class RKA_OT_check_joint_alignment(bpy.types.Operator):
    """Measure every authored lane connection in the scene and report the ones that are not
    genuinely edge-to-edge.

    A connection is only real when the outgoing lane's ribbon EDGES land on the incoming lane's --
    left on left, right on right. Coincident centrelines are not enough: a width mismatch, a
    heading break, or a head-on pairing all leave the edges apart while the centres sit exactly on
    top of each other, and a car crossing that seam jumps sideways or clips a curb that only
    exists on one side.

    Results go to the Info log and the status bar, worst seam first, in metres."""
    bl_idname = "rka.check_joint_alignment"
    bl_label = "Check Joint Alignment"
    bl_options = {'REGISTER'}

    tolerance: bpy.props.FloatProperty(
        name="Tolerance (m)", default=0.01, min=0.0, max=1.0, precision=4,
        description="Edges closer than this count as the same edge. The default (1 cm) is "
                    "tighter than any hand-placed spine and looser than float noise")
    select_worst: bpy.props.BoolProperty(
        name="Select Worst Piece", default=True,
        description="Select and frame the piece owning the worst seam, so the report leads "
                    "somewhere instead of just naming an id")

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        lj = _lj()
        old_tol = lj.EDGE_TOL
        lj.EDGE_TOL = self.tolerance
        try:
            problems, n_links, n_lanes = check_scene_joints(context)
        except Exception as exc:                      # noqa: BLE001 -- a report beats a traceback
            lj.EDGE_TOL = old_tol
            self.report({'ERROR'}, "joint check failed: %s" % exc)
            return {'CANCELLED'}
        lj.EDGE_TOL = old_tol

        if not n_links:
            self.report({'WARNING'},
                        "%d lane(s), but NO authored connections at all -- nothing to check. "
                        "Connectivity is authored data, not inferred from distance." % n_lanes)
            return {'FINISHED'}

        real = [p for p in problems if p["status"] != "UNMEASURABLE"]
        unmeasurable = [p for p in problems if p["status"] == "UNMEASURABLE"]
        if not real:
            msg = "all %d connection(s) are edge-aligned within %.3fm" % (
                n_links - len(unmeasurable), self.tolerance)
            if unmeasurable:
                msg += " (%d unmeasurable -- those lanes carry no width)" % len(unmeasurable)
            self.report({'INFO'}, msg)
            return {'FINISHED'}

        # An UNJOINED joint first: it is a seam with NO connection at all, which outranks any
        # connection that merely measures badly. Below that, worst gap first.
        real.sort(key=lambda p: (p["status"] != "UNJOINED", -(p.get("gap_left") or 0.0)))
        for p in real:
            print("  joint: %s" % lj.describe(p))
        if self.select_worst:
            self._select_piece_of(context, real[0]["from"])
        n_unjoined = sum(1 for p in real if p["status"] == "UNJOINED")
        head = "%d problem(s) across %d connection(s)" % (len(real), n_links)
        if n_unjoined:
            head += ", %d authored joint(s) with NO lane crossing them" % n_unjoined
        self.report({'WARNING'}, "%s; worst: %s (see Info log for all)"
                                 % (head, lj.describe(real[0])))
        return {'FINISHED'}

    @staticmethod
    def _select_piece_of(context, lane_id):
        """Select the piece a lane id belongs to. The id is `<piece>__<lane>`, and the piece part
        is the collection name, so this is a lookup rather than a search."""
        piece = (lane_id or "").split("__")[0]
        coll = opint.local_collection(piece)
        if coll is None:
            return
        for o in context.selected_objects:
            o.select_set(False)
        for o in coll.objects:
            o.select_set(True)
        marker = opint.get_or_create_origin_marker(coll)
        if marker is not None:
            context.view_layer.objects.active = marker


CLASSES = (RKA_OT_check_joint_alignment,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
