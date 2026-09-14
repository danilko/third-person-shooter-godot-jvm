@tool
extends EditorNode3DGizmoPlugin
## Road Kit B8: the 3D handles on a road point. EDITOR TOOLING ONLY.
##
## A point's transform IS its road frame (position = station, local -Z = travel direction), so rotating
## it is the bend gesture and needs no handle. What the gizmo adds is the two BEZIER HANDLE LENGTHS the
## kit sweeps a MANUAL point with (`handle_in` / `handle_out`, metres, 0 = the chord): a handle ahead of
## the point along -Z for `handle_out`, one behind it along +Z for `handle_in`, and an arrow showing the
## travel direction. Dragging a handle projects the mouse ray onto the point's own axis
## (`handle_length`), so a handle can only slide along the road -- it is a length, not a position.
## Dragging one makes the point MANUAL: a length only shapes a tangent the artist owns.

const PointScript := preload("res://addons/road_kit/road_kit_point.gd")
## Where a handle whose length is 0 (the chord) is drawn, so it can be grabbed at all.
const IDLE_HANDLE := 6.0
const ARROW := 4.0
const HANDLE_OUT := 0
const HANDLE_IN := 1

var undo: EditorUndoRedoManager

func _init() -> void:
	create_material("axis", Color(1.0, 0.85, 0.2), false, true)
	create_material("handle_line", Color(0.4, 0.9, 1.0, 0.8), false, true)
	create_handle_material("handles")

func _get_gizmo_name() -> String:
	return "RoadKitPoint"

func _has_gizmo(node: Node3D) -> bool:
	return node.get_script() == PointScript

func _redraw(gizmo: EditorNode3DGizmo) -> void:
	gizmo.clear()
	var p: Node3D = gizmo.get_node_3d()
	var out_len := handle_draw_length(float(p.fields.get("handle_out", 0.0)))
	var in_len := handle_draw_length(float(p.fields.get("handle_in", 0.0)))
	gizmo.add_lines(PackedVector3Array([Vector3.ZERO, Vector3(0, 0, -ARROW),
			Vector3(0, 0, -ARROW), Vector3(0.6, 0, -ARROW + 1.0),
			Vector3(0, 0, -ARROW), Vector3(-0.6, 0, -ARROW + 1.0)]), get_material("axis", gizmo))
	gizmo.add_lines(PackedVector3Array([Vector3(0, 0, -out_len), Vector3(0, 0, in_len)]), get_material("handle_line", gizmo))
	gizmo.add_handles(PackedVector3Array([Vector3(0, 0, -out_len), Vector3(0, 0, in_len)]), get_material("handles", gizmo), PackedInt32Array([HANDLE_OUT, HANDLE_IN]))

func _get_handle_name(_gizmo: EditorNode3DGizmo, handle_id: int, _secondary: bool) -> String:
	return "handle_out" if handle_id == HANDLE_OUT else "handle_in"

func _get_handle_value(gizmo: EditorNode3DGizmo, handle_id: int, _secondary: bool) -> Variant:
	var p: Node3D = gizmo.get_node_3d()
	return [float(p.fields.get(_get_handle_name(gizmo, handle_id, false), 0.0)), str(p.fields.get("tangent_mode", "AUTO"))]

func _set_handle(gizmo: EditorNode3DGizmo, handle_id: int, _secondary: bool, camera: Camera3D, screen_pos: Vector2) -> void:
	var p: Node3D = gizmo.get_node_3d()
	var xf := p.global_transform
	var axis := -xf.basis.z.normalized() if handle_id == HANDLE_OUT else xf.basis.z.normalized()
	var length := handle_length(xf.origin, axis, camera.project_ray_origin(screen_pos), camera.project_ray_normal(screen_pos))
	p.fields[_get_handle_name(gizmo, handle_id, false)] = snappedf(length, 0.1)
	p.fields["tangent_mode"] = "MANUAL"
	p.update_gizmos()

func _commit_handle(gizmo: EditorNode3DGizmo, handle_id: int, _secondary: bool, restore: Variant, cancel: bool) -> void:
	var p: Node3D = gizmo.get_node_3d()
	var field := _get_handle_name(gizmo, handle_id, false)
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

func _apply(p: Node3D, field: String, value: float, mode: String) -> void:
	p.fields[field] = value
	p.fields["tangent_mode"] = mode
	p.update_gizmos()

## Where a handle of authored length `length` is drawn: the length itself, or IDLE_HANDLE for 0 (chord).
static func handle_draw_length(length: float) -> float:
	return length if length > 0.05 else IDLE_HANDLE

## The handle length a mouse ray asks for: the parameter along `axis` (from `origin`) of the point on
## that axis closest to the ray -- a length, clamped at 0 so a handle cannot be dragged through its point.
static func handle_length(origin: Vector3, axis: Vector3, ray_from: Vector3, ray_dir: Vector3) -> float:
	var a := axis.normalized()
	var d := ray_dir.normalized()
	var w := origin - ray_from
	var b := a.dot(d)
	var denom := 1.0 - b * b
	if denom < 1e-6:
		return 0.0              # the ray runs along the axis: no closest point, keep the chord
	var t := (b * d.dot(w) - a.dot(w)) / denom
	return maxf(0.0, t)
