@tool
class_name RoadKitPoint
extends Node3D
## One road point: a station (cross-section) AND a port (typed links) — the kit's `PointData`.
## Its TRANSFORM is the road frame: position is the station, local -Z (Godot forward) is travel
## direction. The record stores the kit's frame; conversion lives only in road_kit_frame.gd.

const Fields := preload("res://addons/road_kit/road_kit_fields.gd")
const FieldSet := preload("res://addons/road_kit/road_kit_fieldset.gd")
const Frame := preload("res://addons/road_kit/road_kit_frame.gd")
const PREFIX := "rk_"

var fields: Dictionary = FieldSet.defaults(Fields.POINT_FIELDS)
## [{"target": uid, "type": "SEGMENT"|"JUNCTION"|"AUX"}] — by uid, which survives a rename.
@export var links: Array[Dictionary] = []

func _get_property_list() -> Array:
	return FieldSet.property_list(Fields.POINT_FIELDS, PREFIX, "Road Point")

func _get(property: StringName):
	var s := String(property)
	if s.begins_with(PREFIX) and fields.has(s.substr(PREFIX.length())):
		return fields[s.substr(PREFIX.length())]
	return null

func _set(property: StringName, value) -> bool:
	var s := String(property)
	if s.begins_with(PREFIX):
		var row := FieldSet.row_of(Fields.POINT_FIELDS, s.substr(PREFIX.length()))
		if not row.is_empty():
			fields[row[0]] = FieldSet.coerce(row, value)
			return true
	return false

var uid: String:
	get: return fields.get("uid", "")
	set(v): fields["uid"] = v

static func new_uid() -> String:
	return "p_%08x" % (randi() & 0x7fffffff | (randi() & 1) << 31)

## The facing (network frame, Godot axes) the TOOL last gave this point, or ZERO if it never has. Derived
## state -- not in the record, like the kit's `RKA_Point.auto_tangent`. A hand rotation is measured
## against it (`was_rotated`), which is what separates a ROTATION from a DRAG: a translate leaves the
## basis alone, so it can never read as one.
var auto_facing := Vector3.ZERO

## Face `dir` (network frame) and stamp it as the tool's facing. Keeps the position.
func face(dir: Vector3) -> void:
	var d := dir.normalized()
	if d.length() < 0.5:
		return
	var up := Vector3.UP if absf(d.y) < 0.99 else Vector3.FORWARD
	var xf := network_transform()
	set_network_transform(Transform3D(Basis.looking_at(d, up), xf.origin))
	auto_facing = d

## THE ROTATION IS THE BEND GESTURE (`point_model.was_rotated`). An AUTO point the artist turned away
## from the facing the tool gave it has been shaped by hand.
func was_rotated() -> bool:
	if auto_facing == Vector3.ZERO:
		return false
	var now := -network_transform().basis.z.normalized()
	return rad_to_deg(now.angle_to(auto_facing)) > Fields.ROTATED_TOL_DEG

## Promote a hand-rotated AUTO point to MANUAL -- the write half of the gesture, run before the record
## is read so the tangent the artist gave is the one the solver sweeps. Returns true when it promoted.
func sync_promotion() -> bool:
	if fields.get("tangent_mode", "AUTO") == "AUTO" and was_rotated():
		fields["tangent_mode"] = "MANUAL"
		return true
	return false

func link_to(target_uid: String, type: String = "SEGMENT") -> void:
	for l in links:
		if l["target"] == target_uid:
			l["type"] = type
			return
	links.append({"target": target_uid, "type": type})

func unlink(target_uid: String) -> int:
	var n := links.size()
	links = links.filter(func(l): return l["target"] != target_uid)
	return n - links.size()

## This point's transform in its NETWORK's frame — the frame the record is written in. Composed from
## local transforms up to the road's parent, so it works outside the scene tree (import, tests) and
## a network moved in the world does not rewrite its record.
func network_transform() -> Transform3D:
	var xf := transform
	var road := get_parent() as Node3D
	if road != null:
		xf = road.transform * xf
	return xf

func set_network_transform(xf: Transform3D) -> void:
	var road := get_parent() as Node3D
	transform = (road.transform.affine_inverse() * xf) if road != null else xf

## Travel direction in the kit's frame, from this node's -Z.
func kit_tangent() -> Vector3:
	return Frame.to_kit(-network_transform().basis.z).normalized()

func to_record() -> Dictionary:
	sync_promotion()
	var d := FieldSet.to_dict(Fields.POINT_FIELDS, fields, ["uid"])
	d["pos"] = Frame.to_array(Frame.to_kit(network_transform().origin))
	d["links"] = links.map(func(l): return {"target": l["target"], "type": l["type"]})
	if fields.get("tangent_mode", "AUTO") == "MANUAL":
		d["tangent"] = Frame.to_array(kit_tangent())
	return d

func from_record(d: Dictionary) -> void:
	fields = FieldSet.from_dict(Fields.POINT_FIELDS, d)
	links.clear()
	for l in d.get("links", []):
		links.append({"target": str(l.get("target", "")), "type": str(l.get("type", "SEGMENT"))})
	var pos := Frame.to_godot(Frame.from_array(d.get("pos", [0, 0, 0])))
	var basis := Basis.IDENTITY
	if d.has("tangent"):
		var t := Frame.to_godot(Frame.from_array(d["tangent"]))
		if t.length() > 1e-9:
			var up := Vector3.UP if absf(t.normalized().y) < 0.99 else Vector3.FORWARD
			basis = Basis.looking_at(t.normalized(), up)
	set_network_transform(Transform3D(basis, pos))
	# A MANUAL facing is the artist's; an AUTO point has no facing until the tool gives it one
	# (`Gestures.apply_facings`), so there is nothing yet to have been rotated away from.
	auto_facing = Vector3.ZERO
