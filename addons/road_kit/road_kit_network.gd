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

## Emitted when anything the record describes may have changed: a point moved or rotated, a field set in
## the inspector, the network reloaded. The plugin debounces it into a refresh (B10.2).
signal edited

## True while this network is an EDITOR VIEW whose points have not been read from its record yet: a saved
## scene holds the network node and none of its roads (they are stripped at save, the record is the only
## copy), so until `load_record` the scene shows an empty network that must never be saved over a real
## record. Set in `_ready` in the editor only -- a `--script` tool or the game builds its own network.
var needs_load := false
var _loading := false

func _ready() -> void:
	if Engine.is_editor_hint() and roads().is_empty() and record_has_points():
		needs_load = true

## A road added or removed (Godot's own Delete, a paste, an undo of either) is an edit too.
func _enter_tree() -> void:
	if Engine.is_editor_hint() and not child_order_changed.is_connected(notify_edited):
		child_order_changed.connect(notify_edited)

## The record file exists and names at least one point.
func record_has_points(path: String = "") -> bool:
	var p := path if path != "" else record_path
	if p == "" or not FileAccess.file_exists(p):
		return false
	var old = JSON.parse_string(FileAccess.get_file_as_string(p))
	return typeof(old) == TYPE_DICTIONARY and not (old.get("points", []) as Array).is_empty()

## Load the record if this is an unloaded editor view (see `needs_load`). Returns the load warnings.
func ensure_loaded() -> Array:
	return load_record() if needs_load else []

## Called by a point or road whose recorded state changed. Silent while a record is being applied.
func notify_edited() -> void:
	if not _loading:
		edited.emit()

func is_loading() -> bool:
	return _loading

## The record as the text `save_record` writes -- one owner of the file format.
func record_text() -> String:
	return JSON.stringify(to_record(), " ", true) + "\n"

## THE RECORD IS THE ONLY SAVED COPY. On an editor scene save the network writes its record (only when
## the text changed) and then takes its roads out of the save by clearing their owner, which is how
## `PackedScene.pack` decides what belongs to the scene (an unowned node's whole subtree is skipped). The
## owner comes back right after the save -- on POST_SAVE, and deferred as well in case a failed save
## never sends it.
func _notification(what: int) -> void:
	if not Engine.is_editor_hint():
		return
	if what == NOTIFICATION_EDITOR_PRE_SAVE:
		if record_changed_on_disk():
			push_warning("RoadKitNetwork %s: %s changed on disk since it was loaded -- not saving over it (the Road Kit plugin reloads it)" % [name, record_path])
		elif not needs_load and record_path != "" and not roads().is_empty():
			save_record()
		_set_road_owners(null)
		_restore_owners.call_deferred()
	elif what == NOTIFICATION_EDITOR_POST_SAVE:
		_restore_owners()

func _restore_owners() -> void:
	if is_inside_tree():
		_set_road_owners(owner if owner != null else self)

func _set_road_owners(o: Node) -> void:
	for r in roads():
		r.owner = o
		for p in r.points():
			p.owner = o

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
	var derived := record_links()
	var ps := all_points().map(func(p): return p.to_record(derived["links"][p.uid], derived["roles"].get(p.uid, "")))
	ps.sort_custom(func(a, b): return a["uid"] < b["uid"])
	return {"schema_ver": Fields.SCHEMA_VER, "roads": rs, "points": ps}

## Every link any point of this network has carried this session, by uid -- including points that have
## since left the tree. A deleted point's node is not freed by the editor (it waits in the undo history)
## but it is no longer a child, so this is how the record still knows what it was joined to.
var _known_links := {}

## THE LINKS THE RECORD WRITES ARE DERIVED FROM THE LIVE TREE, so Godot's own Delete (Scene dock, the
## viewport's Delete key) is a road gesture with no hook, and its undo -- which simply puts the node back --
## restores everything exactly:
##   * a link whose target is no longer a point of this network is not written;
##   * a SEGMENT/JUNCTION link is written on BOTH ends if either end carries it (an undo can bring a node back
##     whose partner was rewritten meanwhile; AUX is directed, mainline -> ramp, and stays one-sided);
##   * two points left chain-adjacent by a deleted station -- joined to it by SEGMENT links, through any run
##     of deleted stations -- are joined to each other, so deleting an interior station never cuts a road;
##   * a SEGMENT link that skips exactly one live station which links both its ends is not written (the
##     bridge above, left in the nodes by a later reload, once that station is undeleted);
##   * an INTERSECTION with no JUNCTION link left is written as a plain SEGMENT station.
## Returns `{"links": {uid: [link]}, "roles": {uid: role}}` (roles only where they differ).
func record_links() -> Dictionary:
	var live := {}
	for p in all_points():
		live[p.uid] = p
		_known_links[p.uid] = p.links.duplicate(true)
	var out := {}
	for u in live:
		out[u] = []
	var add := func(a: String, b: String, type: String) -> void:
		for l in out[a]:
			if l["target"] == b:
				return
		out[a].append({"target": b, "type": type})
	# A point's own links first and in their own order (the record reads in a diff), then the other halves.
	for u in live:
		for l in live[u].links:
			var t := str(l["target"])
			if t != u and live.has(t):
				add.call(u, t, str(l["type"]))
	for u in live:
		for l in live[u].links:
			var t := str(l["target"])
			if t != u and live.has(t) and l["type"] != "AUX":
				add.call(t, u, str(l["type"]))
	for r in roads():
		var pts: Array = r.points()
		var index := {}
		for i in pts.size():
			index[pts[i].uid] = i
		for i in pts.size() - 1:
			var a: String = pts[i].uid
			var b: String = pts[i + 1].uid
			if out[a].any(func(l): return l["target"] == b):
				continue
			if _joined_through_deleted(a, b, live):
				add.call(a, b, "SEGMENT")
				add.call(b, a, "SEGMENT")
		for i in range(1, pts.size() - 1):
			var a: String = pts[i - 1].uid
			var m: String = pts[i].uid
			var b: String = pts[i + 1].uid
			var seg := func(x: String, y: String) -> bool:
				return out[x].any(func(l): return l["target"] == y and l["type"] == "SEGMENT")
			if seg.call(a, b) and seg.call(a, m) and seg.call(m, b):
				out[a] = out[a].filter(func(l): return l["target"] != b)
				out[b] = out[b].filter(func(l): return l["target"] != a)
	var roles := {}
	var aux_targets := {}
	for u in live:
		if str(live[u].fields.get("role", "")) == "INTERSECTION" and not out[u].any(func(l): return l["type"] == "JUNCTION"):
			roles[u] = "SEGMENT"
		for l in out[u]:
			if l["type"] == "AUX":
				aux_targets[l["target"]] = true
	return {"links": out, "roles": roles, "aux_targets": aux_targets}

## True when `a` reaches `b` over SEGMENT links whose every intermediate point has been deleted.
func _joined_through_deleted(a: String, b: String, live: Dictionary) -> bool:
	var seen := {a: true}
	var frontier := [a]
	while not frontier.is_empty():
		var u: String = frontier.pop_back()
		for l in _known_links.get(u, []):
			if l["type"] != "SEGMENT":
				continue
			var t := str(l["target"])
			if t == b and u != a:
				return true
			if seen.has(t) or live.has(t):
				continue
			seen[t] = true
			frontier.append(t)
	return false

## What a point IS, as its name says it (`RoadKitPoint.point_name`), from the links the record writes.
func name_tag(p: Node, road_points: Array, derived: Dictionary) -> String:
	var ls: Array = derived["links"].get(p.uid, [])
	var role: String = derived["roles"].get(p.uid, str(p.fields.get("role", "")))
	if ls.any(func(l): return l["type"] == "JUNCTION"):
		return "_jct"
	if role.begins_with("RAMP") or derived["aux_targets"].has(p.uid):
		return "_ramp"
	if ls.any(func(l): return l["type"] == "AUX"):
		return "_aux"
	if role == "TERMINUS":
		return "_end"
	var i := road_points.find(p)
	if (i == 0 or i == road_points.size() - 1) and ls.size() <= (0 if road_points.size() == 1 else 1):
		return "_end"
	return ""

## The Scene dock's tooltip for a point: its role and every link, by road/point name.
func describe(p: Node, derived: Dictionary, names: Dictionary) -> String:
	var role: String = derived["roles"].get(p.uid, str(p.fields.get("role", "")))
	var lines := ["%s  (%s)" % [role, p.uid]]
	for l in derived["links"].get(p.uid, []):
		lines.append("%s -> %s" % [l["type"], names.get(l["target"], l["target"])])
	return "\n".join(PackedStringArray(lines))

## Rename every point to `RoadKitPoint.point_name` (chain index + what it is) and give it a Scene-dock
## tooltip listing its links. Returns how many names changed. Two passes, so a rename never collides mid-way.
func renumber() -> int:
	var derived := record_links()
	var changed := 0
	var names := {}
	for r in roads():
		var pts: Array = r.points()
		var want := []
		var here := 0
		for i in pts.size():
			want.append(PointScript.point_name(String(r.name), i, name_tag(pts[i], pts, derived)))
			names[pts[i].uid] = "%s/%s" % [r.name, want[i]]
			if String(pts[i].name) != want[i]:
				here += 1
		changed += here
		if here == 0:
			continue
		for i in pts.size():
			if String(pts[i].name) != want[i]:
				pts[i].name = "__rk_tmp_%d" % pts[i].get_instance_id()
		for i in pts.size():
			pts[i].name = want[i]
	for p in all_points():
		var text := describe(p, derived, names)
		if p.editor_description != text:
			p.editor_description = text
	return changed

## Replaces this network's roads with the record's — the record is the source of truth, and a merge
## would silently keep a point the record no longer mentions. Nodes are RECONCILED, not rebuilt: a road
## keeps its node by name and a point by uid (moved between roads and re-ordered as the record says), so
## a gesture or an undo leaves the editor's selection and its own undo entries (a Move, an inspector edit)
## pointing at live nodes. Only what the record no longer mentions is freed.
func from_record(d: Dictionary) -> Array:
	var warnings := []
	_loading = true
	var by_uid := {}
	for pd in d.get("points", []):
		by_uid[str(pd.get("uid", ""))] = pd
	var old_roads := {}
	for r in roads():
		old_roads[String(r.name)] = r
	var old_points := {}
	for p in all_points():
		old_points[p.uid] = p
	# Every kept node gets a temporary name first, so no rename below collides mid-way.
	for r in old_roads.values():
		r.name = "__rk_road_%d" % r.get_instance_id()
	for p in old_points.values():
		p.name = "__rk_pt_%d" % p.get_instance_id()
	var own: Node = owner if owner != null else self
	var placed := {}
	var kept_roads := {}
	for rd in d.get("roads", []):
		var road_name := str(rd.get("name", ""))
		var road: Node3D = old_roads.get(road_name)
		if road == null:
			road = RoadScript.new()
			add_child(road)
		kept_roads[road] = true
		road.from_record(rd)
		road.name = road_name
		road.owner = own
		var i := 0
		for uid in rd.get("points", []):
			var pd = by_uid.get(str(uid))
			if pd == null:
				warnings.append("road %s names missing point %s" % [road.name, uid])
				continue
			var p: Node3D = old_points.get(str(uid))
			if p == null:
				p = PointScript.new()
				road.add_child(p)
			elif p.get_parent() != road:
				p.get_parent().remove_child(p)
				road.add_child(p)
			road.move_child(p, i)
			p.owner = own
			p.from_record(pd)
			p.update_gizmos()   # a gizmo is requested only for a node the edited scene OWNS -- ask again now
			placed[str(uid)] = true
			i += 1
	for r in old_roads.values():
		if not kept_roads.has(r):
			remove_child(r)
			r.free()
	for uid in old_points:
		var p: Node = old_points[uid]
		if not placed.has(uid) and is_instance_valid(p):
			p.get_parent().remove_child(p)
			p.free()
	for uid in by_uid:
		_known_links[uid] = by_uid[uid].get("links", []).duplicate(true)
	renumber()
	for uid in by_uid:
		if not placed.has(uid):
			warnings.append("point %s belongs to no road -- dropped" % uid)
	needs_load = false
	_loading = false
	edited.emit()
	return warnings

## The record text this network last read from or wrote to `record_path` ("" = neither, this session).
var _disk_text := ""

func load_record(path: String = "") -> Array:
	var p := path if path != "" else record_path
	var text := FileAccess.get_file_as_string(p)
	var parsed = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		return ["could not parse %s" % p]
	if p == record_path:
		_disk_text = text
	return from_record(parsed)

## True when the record file holds something this network neither read nor wrote -- a git checkout, a
## merge, a hand edit, another editor. A MISSING file is not a change (the next save puts it back).
func record_changed_on_disk() -> bool:
	if record_path == "" or needs_load or _disk_text == "" or not FileAccess.file_exists(record_path):
		return false
	return FileAccess.get_file_as_string(record_path) != _disk_text

## Refuses (ERR_ALREADY_IN_USE) to write an editor view that was never loaded (`needs_load`), or an EMPTY
## network over a record that has points. The first cost `DebugRoads.roads.json` twice: once as an empty
## network written by the preview-on-open path, and once (committed, 2026-09-14) as `New Road` pressed on
## the unloaded view, which wrote one 2-point `road_0` over 21 points. Clearing a record on purpose is
## `force`.
##
## THE WRITE IS ATOMIC and skipped when nothing changed: the text goes to `<record>.tmp` and is renamed over
## the record, so an editor that crashes or is killed mid-save leaves the old record whole instead of an
## empty or half-written one; and an unchanged record is not touched (no mtime churn for the editor's
## filesystem scan or for git).
func save_record(path: String = "", force: bool = false) -> Error:
	var p := path if path != "" else record_path
	if not force and (needs_load or all_points().is_empty()) and record_has_points(p):
		push_warning("RoadKitNetwork %s: not saving an unloaded network over %s -- Load Record first" % [name, p])
		return ERR_ALREADY_IN_USE
	var text := record_text()
	if FileAccess.file_exists(p) and FileAccess.get_file_as_string(p) == text:
		if p == record_path:
			_disk_text = text
		return OK
	var tmp := p + ".tmp"
	var f := FileAccess.open(tmp, FileAccess.WRITE)
	if f == null:
		return FileAccess.get_open_error()
	f.store_string(text)
	f.close()
	var err := DirAccess.rename_absolute(ProjectSettings.globalize_path(tmp), ProjectSettings.globalize_path(p))
	if err != OK:
		return err
	if p == record_path:
		_disk_text = text
	return OK
