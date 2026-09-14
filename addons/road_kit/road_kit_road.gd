@tool
class_name RoadKitRoad
extends Node3D
## An ORDERED corridor — the kit's `RoadData`. Its RoadKitPoint children, in child order, ARE the
## chain (FWD = increasing index). The road's name is the node's name. `base_*` is the base
## cross-section an INHERIT station takes (only the four delta fields come from the point).

const Fields := preload("res://addons/road_kit/road_kit_fields.gd")
const FieldSet := preload("res://addons/road_kit/road_kit_fieldset.gd")
const PointScript := preload("res://addons/road_kit/road_kit_point.gd")
const PREFIX := "rk_"
const BASE := "base_"

var fields: Dictionary = FieldSet.defaults(Fields.ROAD_FIELDS)
var base: Dictionary = FieldSet.defaults(Fields.POINT_FIELDS)

func _get_property_list() -> Array[Dictionary]:
	var out: Array[Dictionary] = FieldSet.property_list(Fields.ROAD_FIELDS, PREFIX, "Road", ["name"])
	out.append_array(FieldSet.property_list(Fields.POINT_FIELDS, BASE, "Base Cross-Section", ["uid", "schema_ver", "role"]))
	return out

func _get(property: StringName):
	var s := String(property)
	if s.begins_with(PREFIX) and fields.has(s.substr(PREFIX.length())):
		return fields[s.substr(PREFIX.length())]
	if s.begins_with(BASE) and base.has(s.substr(BASE.length())):
		return base[s.substr(BASE.length())]
	return null

func _set(property: StringName, value) -> bool:
	var s := String(property)
	if s.begins_with(PREFIX):
		var row := FieldSet.row_of(Fields.ROAD_FIELDS, s.substr(PREFIX.length()))
		if not row.is_empty():
			fields[row[0]] = FieldSet.coerce(row, value)
			_edited()
			return true
	if s.begins_with(BASE):
		var row := FieldSet.row_of(Fields.POINT_FIELDS, s.substr(BASE.length()))
		if not row.is_empty():
			base[row[0]] = FieldSet.coerce(row, value)
			_edited()
			return true
	return false

func _edited() -> void:
	var net := get_parent()
	if net != null and net.has_method("notify_edited"):
		net.notify_edited()

## A dragged ROAD node moves its points (a point's record position composes the road's transform), so it
## reports its moves too.
func _enter_tree() -> void:
	if Engine.is_editor_hint():
		set_notify_transform(true)
		# A point added, removed or re-ordered (Godot's own Delete, a paste, dragging it in the Scene dock,
		# an undo of any of those) changes the chain.
		if not child_order_changed.is_connected(_edited):
			child_order_changed.connect(_edited)

func _notification(what: int) -> void:
	if what == NOTIFICATION_TRANSFORM_CHANGED:
		_edited()

func points() -> Array:
	return get_children().filter(func(c): return c.get_script() == PointScript)

func to_record() -> Dictionary:
	var f := fields.duplicate()
	f["name"] = String(name)
	var d := FieldSet.to_dict(Fields.ROAD_FIELDS, f, ["name"])
	var b := base.duplicate()
	b["uid"] = ""
	var bd := FieldSet.to_dict(Fields.POINT_FIELDS, b, ["uid"])
	bd["pos"] = [0.0, 0.0, 0.0]
	bd["links"] = []
	d["base"] = bd
	d["points"] = points().map(func(p): return p.uid)
	return d

func from_record(d: Dictionary) -> void:
	fields = FieldSet.from_dict(Fields.ROAD_FIELDS, d)
	name = str(d.get("name", name))
	base = FieldSet.from_dict(Fields.POINT_FIELDS, d.get("base", {}))
