@tool
class_name RoadKitNetwork
extends Node3D
## Every road in one world — the kit's `NetworkData`, and the owner of its `.roads.json` record.
## Children: RoadKitRoad. Sibling scripts are referenced by PRELOAD, never by class_name: a headless
## `--script` run and a fresh checkout have no global class cache yet, and a class_name type hint then
## fails to parse and the whole script is dead. The record is written in the kit's own schema and frame, so the pure-Python
## solver (blender/tools/roadkit_cli.py) and the headless Blender mesh build read it unchanged.

const Fields := preload("res://addons/road_kit/road_kit_fields.gd")
const RoadScript := preload("res://addons/road_kit/road_kit_road.gd")
const PointScript := preload("res://addons/road_kit/road_kit_point.gd")

## Where this network's record lives (res:// or absolute). The record, not the scene, is what the
## solver and the builder read; the scene is its editable view.
@export_file("*.json") var record_path := ""

func roads() -> Array:
	return get_children().filter(func(c): return c.get_script() == RoadScript)

func all_points() -> Array:
	var out := []
	for r in roads():
		out.append_array(r.points())
	return out

func find_point(uid: String) -> Node3D:
	for p in all_points():
		if p.uid == uid:
			return p
	return null

func to_record() -> Dictionary:
	var rs := roads().map(func(r): return r.to_record())
	rs.sort_custom(func(a, b): return a["name"] < b["name"])
	var ps := all_points().map(func(p): return p.to_record())
	ps.sort_custom(func(a, b): return a["uid"] < b["uid"])
	return {"schema_ver": Fields.SCHEMA_VER, "roads": rs, "points": ps}

## Replaces this network's roads with the record's — the record is the source of truth, and a merge
## would silently keep a point the record no longer mentions.
func from_record(d: Dictionary) -> Array:
	var warnings := []
	for r in roads():
		remove_child(r)
		r.free()
	var by_uid := {}
	for pd in d.get("points", []):
		by_uid[str(pd.get("uid", ""))] = pd
	var placed := {}
	for rd in d.get("roads", []):
		var road: Node3D = RoadScript.new()
		road.from_record(rd)
		add_child(road, true)
		road.owner = owner if owner != null else self
		var i := 0
		for uid in rd.get("points", []):
			var pd = by_uid.get(str(uid))
			if pd == null:
				warnings.append("road %s names missing point %s" % [road.name, uid])
				continue
			var p: Node3D = PointScript.new()
			p.name = "%s_p%03d" % [road.name, i]
			road.add_child(p, true)
			p.owner = road.owner
			p.from_record(pd)
			placed[str(uid)] = true
			i += 1
	for uid in by_uid:
		if not placed.has(uid):
			warnings.append("point %s belongs to no road -- dropped" % uid)
	return warnings

func load_record(path: String = "") -> Array:
	var p := path if path != "" else record_path
	var text := FileAccess.get_file_as_string(p)
	var parsed = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		return ["could not parse %s" % p]
	return from_record(parsed)

func save_record(path: String = "") -> Error:
	var p := path if path != "" else record_path
	var f := FileAccess.open(p, FileAccess.WRITE)
	if f == null:
		return FileAccess.get_open_error()
	f.store_string(JSON.stringify(to_record(), " ", true) + "\n")
	return OK
