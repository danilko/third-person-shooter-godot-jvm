"""ops_lane_ports.py -- per-slot ports: the viewport half of `lib/lane_ports`.

A piece has always had exactly two markers, `port_A`/`port_B`, and both sit on the road
CENTRELINE. `ROAD_KIT_MIGRATION_STATUS.md` Step 7 traces three separate authoring complaints back
to that one fact -- lane cannot be snapped to lane, segment<->intersection snapping is a
proximity guess, and there is no way to see which way traffic goes through a connection point.
None of them is fixable while the only anchor a piece offers is a point 10 m from the lane you
meant, carrying no direction.

WHAT THIS ADDS. One marker per lane end, sitting exactly on that lane's own centreline, with an
arrow pointing the way its traffic drives:

    lp_IN_<label>    traffic ENTERS the piece here   (the lane's first point)
    lp_OUT_<label>   traffic LEAVES the piece here   (the lane's last point)

so a two-way road end shows an inbound and an outbound arrow side by side instead of one
directionless dot in the middle of the asphalt.

THEY ARE OPT-IN, PER PIECE. Materialising ports for all 111 pieces of the island at once would be
a couple of thousand Empties nobody asked for. `Show Lane Ports` builds them for the selected
piece(s); `Hide Lane Ports` removes them. Once a piece HAS them they are refreshed automatically
by every rebuild (`refresh_lane_ports`, wired into `ops_intersection._rebuild_piece_in_place` and
`live_edit._flush_rebuilds`), so they never drift away from the geometry they describe -- but a
piece you never asked about stays clean.

TAGGED `rka_lane_port`, DELIBERATELY NOT `rka_port`. `live_edit._flush_port_drags` treats any
`rka_port`-tagged Empty as a drag handle for its piece's spine ENDPOINT, resolving the end as
`"A" -> first point, anything else -> last point`. A lane port carrying that key would therefore
drag the spine's far end to a lane centreline the moment it was nudged. This is the same trap
`_place_segment_ports` documents about `rka_segend`: a key the live-edit handler does not
recognise at all makes the marker inert, which is what a click target should be.

SNAPPING IS A RIGID MOVE OF THE SPINE, THEN A REBUILD -- never a geometry edit. `Snap Lane To
Lane` rotates and translates the moving piece's spine control points so the two chosen lane ends
coincide and flow the same way, then rebuilds through the normal dispatcher, so every derived
object (pavement, curbs, markers, the piece's own ports) is re-derived rather than transformed
into a state nothing else agrees with.
"""
import bpy
import math

from mathutils import Vector

from . import lane_export
from . import live_edit
from . import ops_intersection as opint
from . import spine_io

#: "IN"/"OUT" -- see the module docstring for why this is not `rka_port`.
LANE_PORT_KEY = "rka_lane_port"
#: Comma-joined lane ids this port is the end of. Also the port's IDENTITY across a rebuild: the
#: geometry moves, the set of lanes meeting there does not.
LANE_PORT_LANES = "rka_lane_port_lanes"
LANE_PORT_SLOTS = "rka_lane_port_slots"
LANE_PORT_HEADING = "rka_lane_port_heading_deg"
LANE_PORT_WIDTH = "rka_lane_port_width"

_PREFIX = "lp_"


def _lp():
    """Lazy `lib/lane_ports` import -- the deferred-import idiom `ops_joint_check._lj()` uses."""
    import lane_ports
    return lane_ports


# ------------------------------------------------------------------------------- build / refresh

def piece_ports(context, coll):
    """Every lane port of `coll`, as `lib/lane_ports` dicts in Blender-native coordinates.

    Derived from `lane_export.export_piece_dict` -- the SAME lane data the sidecar, the preview
    overlay and the alignment gate read. That is the point rather than an implementation detail: a
    port computed independently from the profile could disagree with the lane it names, and then
    snapping to the port would not align the lane."""
    d = lane_export.export_piece_dict(coll, context.scene, godot_space=False)
    if not d:
        return []
    return _lp().ports_from_lanes(d.get("lanes", ()), axes=_lp().BLENDER_AXES)


def _label(port):
    return ("-".join(s for s in port["slots"] if s)
            or "-".join(a for a in port["arms"] if a)
            or "lane")


def existing_lane_ports(coll):
    return [o for o in coll.objects if LANE_PORT_KEY in o.keys()]


def has_lane_ports(coll):
    return any(LANE_PORT_KEY in o.keys() for o in coll.objects)


def _aim(obj, heading_deg):
    """Point an Empty's arrow (`SINGLE_ARROW` draws along local +Z) along a ground-plane heading,
    so the marker reads as a direction of travel at a glance rather than needing its name read."""
    d = Vector((math.cos(math.radians(heading_deg)), math.sin(math.radians(heading_deg)), 0.0))
    obj.rotation_euler = d.to_track_quat('Z', 'Y').to_euler()


def refresh_lane_ports(context, coll, create=False):
    """Rebuild `coll`'s lane-port markers from its current geometry. Returns the number of ports.

    `create=False` (the default, and what every rebuild hook passes) makes this a NO-OP on a piece
    that has none -- ports stay opt-in, and a rebuild never silently populates a scene with
    markers. Existing ports are matched by `LANE_PORT_LANES`, not by name or position, so a port
    keeps its identity across a move: Blender's own name auto-suffixing would otherwise turn every
    refresh into a fresh `lp_OUT_F0.001`.

    Idempotent, and it PRUNES: a port whose lanes no longer exist (a slot tapered away, an arm
    removed) is deleted rather than left behind pointing at nothing."""
    if coll is None:
        return 0
    old = {o.get(LANE_PORT_LANES, ""): o for o in existing_lane_ports(coll)}
    if not old and not create:
        return 0
    try:
        ports = piece_ports(context, coll)
    except Exception as exc:                          # noqa: BLE001 -- markers must never break a rebuild
        print("  lane ports: could not export %s (%s)" % (coll.name, exc))
        return 0
    seen = set()
    for port in ports:
        lanes_val = ",".join(sorted(str(l) for l in port["lanes"]))
        seen.add(lanes_val)
        obj = old.get(lanes_val)
        if obj is None:
            obj = bpy.data.objects.new("%s%s_%s" % (_PREFIX, port["flow"], _label(port)), None)
            obj.empty_display_type = 'SINGLE_ARROW'
            obj.show_name = True
            coll.objects.link(obj)
        obj.empty_display_size = max(1.0, min(3.0, port["width"] or 1.0))
        obj.location = port["pos"]
        _aim(obj, port["heading"])
        obj[LANE_PORT_KEY] = port["flow"]
        obj[LANE_PORT_LANES] = lanes_val
        obj[LANE_PORT_SLOTS] = ",".join(str(s) for s in port["slots"] if s)
        obj[LANE_PORT_HEADING] = float(port["heading"])
        obj[LANE_PORT_WIDTH] = float(port["width"])
    for lanes_val, obj in old.items():
        if lanes_val not in seen:
            bpy.data.objects.remove(obj, do_unlink=True)
    return len(ports)


def clear_lane_ports(coll):
    n = 0
    for obj in existing_lane_ports(coll):
        bpy.data.objects.remove(obj, do_unlink=True)
        n += 1
    return n


def refresh_if_present(context, coll_names):
    """Refresh lane ports for every named collection that already has some -- the hook shape the
    rebuild paths call, so they never need to know whether a piece opted in."""
    for name in coll_names:
        coll = opint.local_collection(name)
        if coll is not None and has_lane_ports(coll):
            refresh_lane_ports(context, coll)


# ------------------------------------------------------------------------------------- selection

def _piece_of(obj):
    """The LOCAL piece collection an object belongs to. Membership, not naming -- an Empty's name
    is auto-suffixed by Blender and carries no reliable owner."""
    if obj is None:
        return None
    for c in bpy.data.collections:
        if c.library is None and opint._is_piece_collection(c) and obj.name in c.objects:
            return c
    return None


def _selected_pieces(context):
    out = []
    for obj in context.selected_objects:
        coll = _piece_of(obj)
        if coll is not None and coll not in out:
            out.append(coll)
    return out


def _port_dict_of(obj):
    """The `lib/lane_ports` dict an existing marker Empty stands for -- read back off the object
    so the snap works on what is actually in the file, with no re-export."""
    return {"flow": obj.get(LANE_PORT_KEY),
            "pos": tuple(obj.location),
            "heading": float(obj.get(LANE_PORT_HEADING, 0.0)),
            "width": float(obj.get(LANE_PORT_WIDTH, 0.0)),
            "lanes": [s for s in str(obj.get(LANE_PORT_LANES, "")).split(",") if s],
            "slots": [s for s in str(obj.get(LANE_PORT_SLOTS, "")).split(",") if s],
            "arms": []}


def _selected_lane_ports(context):
    """`(active_port_obj, other_port_obj)` -- the ACTIVE one is the port that moves. Which piece
    moves has to be stated, not guessed: snapping is not symmetric, and picking the "smaller" or
    "newer" piece would silently relocate whichever one the user had already positioned."""
    sel = [o for o in context.selected_objects if LANE_PORT_KEY in o.keys()]
    act = context.view_layer.objects.active
    if len(sel) != 2 or act is None or LANE_PORT_KEY not in act.keys():
        return None, None
    other = next(o for o in sel if o is not act)
    return act, other


# ---------------------------------------------------------------------------------------- snap

def snap_piece(context, src_obj, dst_obj):
    """Rigidly move `src_obj`'s whole piece so `src_obj` lands on `dst_obj`, flowing the same way.
    Returns `(coll, theta_deg, delta)`; raises `ValueError` with a readable reason if it cannot.

    Only the SPINE control points and the piece's free-standing markers are transformed -- every
    other object is re-derived by the rebuild. Transforming derived geometry instead would leave
    the piece in a state its own rebuild disagrees with, which is the same class of bug as baking
    the spine into a mesh (see `_join_visuals_keeping_spine`)."""
    lp = _lp()
    src, dst = _port_dict_of(src_obj), _port_dict_of(dst_obj)
    reason = lp.flow_conflict(src, dst)
    if reason:
        raise ValueError(reason)
    coll = _piece_of(src_obj)
    if coll is None:
        raise ValueError("the active lane port does not belong to a piece collection")
    spine_name = coll.get("rka_curve_object")
    spine_obj = opint.local_object(spine_name) if spine_name else None
    if not spine_io.is_spine(spine_obj):
        raise ValueError("the moving piece has no spine -- select a lane port on a SEGMENT as the "
                          "active object (an intersection is positioned by its arms, so snap the "
                          "road onto the junction, not the junction onto the road)")

    theta, delta = lp.snap_transform(src, dst)
    pivot = src["pos"]
    pts = spine_io.points(spine_obj)
    for p in pts:
        x, y, z = lp.apply_transform(tuple(p.co[:3]), pivot, theta, delta,
                                      axes=lp.BLENDER_AXES)
        p.co = (x, y, z, p.co[3])                     # whole-tuple write -- see live_edit's note
    # Free-standing markers move with the piece so a rebuild that reads one (the origin marker IS
    # the piece's link anchor) does not drag it straight back to where it used to be.
    for obj in list(coll.objects):
        if obj.type != 'EMPTY' or obj is spine_obj:
            continue
        obj.location = lp.apply_transform(tuple(obj.location), pivot, theta, delta,
                                           axes=lp.BLENDER_AXES)
    return coll, theta, delta


class RKA_OT_show_lane_ports(bpy.types.Operator):
    """Build (or refresh) one marker per LANE END on the selected piece(s).

    Each marker sits exactly on its lane's own centreline and points the way that lane's traffic
    drives -- inbound arrows where traffic enters the piece, outbound where it leaves. That is the
    anchor lane-to-lane snapping needs, and the in/out readout a single road-centre port could
    never give."""
    bl_idname = "rka.show_lane_ports"
    bl_label = "Show Lane Ports"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects)

    def execute(self, context):
        pieces = _selected_pieces(context)
        if not pieces:
            self.report({'ERROR'}, "select something belonging to a road piece first")
            return {'CANCELLED'}
        total = 0
        for coll in pieces:
            try:
                total += refresh_lane_ports(context, coll, create=True)
            except Exception as exc:                  # noqa: BLE001
                self.report({'ERROR'}, "%s: %s" % (coll.name, exc))
                return {'CANCELLED'}
        if not total:
            self.report({'WARNING'}, "%d piece(s) produced NO lane ports -- they export no lanes "
                                      "(check the piece rebuilds cleanly)" % len(pieces))
            return {'FINISHED'}
        self.report({'INFO'}, "%d lane port(s) on %d piece(s)" % (total, len(pieces)))
        return {'FINISHED'}


class RKA_OT_hide_lane_ports(bpy.types.Operator):
    """Remove the lane-port markers from the selected piece(s) -- or from every piece in the file
    when nothing is selected."""
    bl_idname = "rka.hide_lane_ports"
    bl_label = "Hide Lane Ports"
    bl_options = {'REGISTER', 'UNDO'}

    all_pieces: bpy.props.BoolProperty(
        name="Every Piece", default=False,
        description="Clear lane ports across the whole file, not just the selected piece(s)")

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        pieces = ([c for c in bpy.data.collections
                   if c.library is None and opint._is_piece_collection(c)]
                  if self.all_pieces else _selected_pieces(context))
        n = sum(clear_lane_ports(c) for c in pieces)
        self.report({'INFO'}, "removed %d lane port marker(s)" % n)
        return {'FINISHED'}


class RKA_OT_snap_lane_to_lane(bpy.types.Operator):
    """Move the ACTIVE lane port's whole piece so that lane end meets the other selected lane end
    exactly, travelling the same way.

    Select two lane-port markers; the active one is the end that moves. The piece is rotated and
    translated as a rigid body about that port and then rebuilt, so the seam is edge-to-edge by
    construction rather than by eye -- and the result is measured and reported, in metres, by the
    same `lib/lane_joints` test the network gate runs."""
    bl_idname = "rka.snap_lane_to_lane"
    bl_label = "Snap Lane To Lane"
    bl_options = {'REGISTER', 'UNDO'}

    stamp_link: bpy.props.BoolProperty(
        name="Also Connect The Pieces", default=True,
        description="Record the joint (rka_linked_to) as well as aligning it. Alignment is "
                    "geometry; connectivity is authored data -- a snapped seam that nobody "
                    "declared connected exports no lane links at all")

    @classmethod
    def poll(cls, context):
        if context.mode != 'OBJECT':
            return False
        sel = [o for o in context.selected_objects if LANE_PORT_KEY in o.keys()]
        return len(sel) == 2

    def execute(self, context):
        src_obj, dst_obj = _selected_lane_ports(context)
        if src_obj is None:
            self.report({'ERROR'}, "select exactly two lane ports; the ACTIVE one is the end "
                                    "that moves")
            return {'CANCELLED'}
        try:
            coll, theta, delta = snap_piece(context, src_obj, dst_obj)
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        dst_coll = _piece_of(dst_obj)
        with live_edit.rebuilding():
            opint._rebuild_piece_in_place(context, coll)
            refresh_lane_ports(context, coll)
            if dst_coll is not None and has_lane_ports(dst_coll):
                refresh_lane_ports(context, dst_coll)
        if self.stamp_link and dst_coll is not None and dst_coll is not coll:
            self._stamp(coll, dst_coll)

        gap = self._measure(context, coll, dst_coll, src_obj, dst_obj)
        self.report({'INFO'}, "snapped %s by %.1f deg / %.2f m%s"
                              % (coll.name, theta, Vector(delta).length, gap))
        return {'FINISHED'}

    @staticmethod
    def _stamp(coll, dst_coll):
        """Record the joint the same way every other authoring gesture does -- the moving piece's
        origin marker points at the target piece's anchor (`live_edit.RKA_LINKED_TO_KEY`). Which
        lanes then continue into which is MEASURED at export by `lane_export.emit_joint_links`,
        and after a snap the measurement is exactly what the snap produced."""
        marker = opint.get_or_create_origin_marker(coll)
        target = opint.get_or_create_origin_marker(dst_coll)
        if marker is not None and target is not None:
            marker[live_edit.RKA_LINKED_TO_KEY] = target.name

    @staticmethod
    def _measure(context, coll, dst_coll, src_obj, dst_obj):
        """Re-measure the seam the snap just made, edge to edge. Reporting the promise back as a
        number is the whole difference between "snapped" and "aligned"."""
        if dst_coll is None:
            return ""
        try:
            import lane_joints as lj
            lanes = []
            for c in (coll, dst_coll):
                d = lane_export.export_piece_dict(c, context.scene, godot_space=False)
                for lane in (d or {}).get("lanes", ()):
                    l = dict(lane)
                    l["id"] = "%s__%s" % (c.name, lane.get("id"))
                    lanes.append(l)
            outs = [l for l in lanes if l["id"].startswith(coll.name + "__")]
            ins = [l for l in lanes if l["id"].startswith(dst_coll.name + "__")]
            pairs = lj.pair_lanes(outs, ins)
            if not pairs:
                return "; NO lane pairs across the seam yet -- check the two ends really face"
            worst = max(g for _a, _b, g in pairs)
            return "; %d lane pair(s), worst edge gap %.3f m" % (len(pairs), worst)
        except Exception as exc:                      # noqa: BLE001
            return "; (could not measure: %s)" % exc


CLASSES = (RKA_OT_show_lane_ports, RKA_OT_hide_lane_ports, RKA_OT_snap_lane_to_lane)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
