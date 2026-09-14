@tool
extends EditorNode3DGizmoPlugin
## Road Kit: the 3D gizmo on a road point -- its pick cross and travel arrow, and its HANDLES. EDITOR TOOLING.
##
## A point's transform IS its road frame (position = station, local -Z = travel direction), so rotating
## it is the bend gesture and needs no handle. The handles (road_kit_handles.gd owns what each does):
##   * B8: the two BEZIER HANDLE LENGTHS the kit sweeps a MANUAL point with (`handle_in` / `handle_out`,
##     metres, 0 = the chord) -- a length along the point's own axis, and dragging one makes the point
##     MANUAL: a length only shapes a tangent the artist owns;
##   * B10.4, the intersection tweak: two LANE-COUNT handles at the outer edge of each carriageway (drag
##     sideways past a lane width to step `lanes_fwd` / `lanes_bwd`), and on a junction mouth a SETBACK
##     handle (slide the stop line along its own road; locks the setback), a FILLET handle (the corner
##     radius the pad starts from) and the whole JUNCTION's MOVE and ROTATE handles at its centre, which
##     move every mouth together -- a turned crossing promotes no mouth to MANUAL.
## Every B10.4 drag commits as ONE undo step that restores the network's record, like every Road Kit gesture.

const PointScript := preload("res://addons/road_kit/road_kit_point.gd")
const Handles := preload("res://addons/road_kit/road_kit_handles.gd")
const ARROW := 4.0
## Half-size of the pick cross drawn at every point. Its segments are the gizmo's COLLISION, which is what
## the 3D viewport ray-picks: without them a point could only be selected in the Scene dock (B10.0).
const CROSS := 1.5
## A point's marker colour by role: a junction mouth (a stop line) must be obvious at a glance.
const ROLE_COLORS := {"INTERSECTION": Color(1.0, 0.85, 0.1), "RAMP": Color(0.2, 0.8, 1.0),
		"RAMP_ENTRY": Color(0.2, 0.8, 1.0), "RAMP_EXIT": Color(0.2, 0.8, 1.0), "TERMINUS": Color(1.0, 0.4, 0.3)}
const DEFAULT_COLOR := Color(0.35, 1.0, 0.45)

var undo: EditorUndoRedoManager
var handles: RefCounted = Handles.new()

func _init() -> void:
	create_material("axis", Color(1.0, 0.85, 0.2), false, true)
	create_material("marker_default", DEFAULT_COLOR, false, true)
	for role in ROLE_COLORS:
		create_material("marker_" + role, ROLE_COLORS[role], false, true)
	create_material("handle_line", Color(0.4, 0.9, 1.0, 0.8), false, true)
	create_material("junction_line", Color(1.0, 0.85, 0.1, 0.7), false, true)
	create_handle_material("handles")

func _get_gizmo_name() -> String:
	return "RoadKitPoint"

func _has_gizmo(node: Node3D) -> bool:
	return node.get_script() == PointScript

func _redraw(gizmo: EditorNode3DGizmo) -> void:
	gizmo.clear()
	var p: Node3D = gizmo.get_node_3d()
	var arrow := PackedVector3Array([Vector3.ZERO, Vector3(0, 0, -ARROW),
			Vector3(0, 0, -ARROW), Vector3(0.6, 0, -ARROW + 1.0),
			Vector3(0, 0, -ARROW), Vector3(-0.6, 0, -ARROW + 1.0)])
	var cross := marker_segments()
	var role := str(p.fields.get("role", "SEGMENT"))
	gizmo.add_lines(arrow, get_material("axis", gizmo))
	gizmo.add_lines(cross, get_material("marker_" + role if ROLE_COLORS.has(role) else "marker_default", gizmo))
	var pick := PackedVector3Array(cross)
	pick.append_array(arrow)
	gizmo.add_collision_segments(pick)
	var pos := {}
	for id in Handles.ids_for(p):
		pos[id] = handles.position(p, id)
	gizmo.add_lines(PackedVector3Array([pos[Handles.HANDLE_OUT], pos[Handles.HANDLE_IN]]), get_material("handle_line", gizmo))
	if pos.has(Handles.HANDLE_JCT_MOVE):
		gizmo.add_lines(PackedVector3Array([Vector3.ZERO, pos[Handles.HANDLE_JCT_MOVE], pos[Handles.HANDLE_JCT_MOVE], pos[Handles.HANDLE_JCT_ROTATE]]), get_material("junction_line", gizmo))
	var ids := PackedInt32Array()
	var pts := PackedVector3Array()
	for id in pos:
		ids.append(id)
		pts.append(pos[id])
	gizmo.add_handles(pts, get_material("handles", gizmo), ids)

func _get_handle_name(_gizmo: EditorNode3DGizmo, handle_id: int, _secondary: bool) -> String:
	return Handles.NAMES[handle_id] if handle_id >= 0 and handle_id < Handles.NAMES.size() else ""

func _is_bend(handle_id: int) -> bool:
	return handle_id == Handles.HANDLE_OUT or handle_id == Handles.HANDLE_IN

func _get_handle_value(gizmo: EditorNode3DGizmo, handle_id: int, _secondary: bool) -> Variant:
	var p: Node3D = gizmo.get_node_3d()
	if _is_bend(handle_id):
		return [float(p.fields.get(Handles.NAMES[handle_id], 0.0)), str(p.fields.get("tangent_mode", "AUTO"))]
	return handles.begin(p, handle_id)["record"]

func _begin_handle_action(gizmo: EditorNode3DGizmo, handle_id: int, _secondary: bool) -> void:
	if not _is_bend(handle_id):
		handles.drag = {}
		handles.begin(gizmo.get_node_3d(), handle_id)

func _set_handle(gizmo: EditorNode3DGizmo, handle_id: int, _secondary: bool, camera: Camera3D, screen_pos: Vector2) -> void:
	var p: Node3D = gizmo.get_node_3d()
	var from := camera.project_ray_origin(screen_pos)
	var dir := camera.project_ray_normal(screen_pos)
	if _is_bend(handle_id):
		var xf := p.global_transform
		var axis := -xf.basis.z.normalized() if handle_id == Handles.HANDLE_OUT else xf.basis.z.normalized()
		p.fields[Handles.NAMES[handle_id]] = snappedf(Handles.handle_length(xf.origin, axis, from, dir), 0.1)
		p.fields["tangent_mode"] = "MANUAL"
		p.update_gizmos()
		return
	var to_net: Transform3D = Handles.Gestures.network_of(p).global_transform.affine_inverse()
	for m in handles.drag_to(p, handle_id, to_net * from, (to_net.basis * dir).normalized()):
		m.update_gizmos()

func _commit_handle(gizmo: EditorNode3DGizmo, handle_id: int, _secondary: bool, restore: Variant, cancel: bool) -> void:
	var p: Node3D = gizmo.get_node_3d()
	if _is_bend(handle_id):
		var field: String = Handles.NAMES[handle_id]
		if cancel:
			p.fields[field] = restore[0]
			p.fields["tangent_mode"] = restore[1]
			p.update_gizmos()
			return
		if undo == null:
			return
		undo.create_action("Road Kit: %s" % field)
		undo.add_do_method(self, "_apply", p, field, p.fields[field], p.fields["tangent_mode"])
		undo.add_undo_method(self, "_apply", p, field, restore[0], restore[1])
		undo.commit_action(false)
		return
	var step: Dictionary = handles.end(p, handle_id, cancel)
	if step.is_empty() or undo == null:
		return
	undo.create_action("Road Kit: " + step["name"], UndoRedo.MERGE_DISABLE, step["net"])
	undo.add_do_method(step["net"], "from_record", step["after"])
	undo.add_undo_method(step["net"], "from_record", step["before"])
	undo.commit_action(false)

func _apply(p: Node3D, field: String, value: float, mode: String) -> void:
	p.fields[field] = value
	p.fields["tangent_mode"] = mode
	p.update_gizmos()
	p._edited()

## The pick cross at a point: three axes through its origin plus a vertical post, as segment pairs (local).
static func marker_segments() -> PackedVector3Array:
	return PackedVector3Array([Vector3(-CROSS, 0, 0), Vector3(CROSS, 0, 0), Vector3(0, 0, -CROSS), Vector3(0, 0, CROSS),
			Vector3(0, -CROSS * 0.5, 0), Vector3(0, CROSS * 2.0, 0)])

## Kept for callers of the B8 API (test_roadkit_b8.gd).
static func handle_length(origin: Vector3, axis: Vector3, ray_from: Vector3, ray_dir: Vector3) -> float:
	return Handles.handle_length(origin, axis, ray_from, ray_dir)

static func handle_draw_length(length: float) -> float:
	return Handles.draw_length(length)
