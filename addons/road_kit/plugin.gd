@tool
extends EditorPlugin
## Road Kit editor plugin (PLAN.md 3.1 option B). EDITOR TOOLING ONLY — never runtime gameplay.
##
## Authoring lives here, in the Godot editor, next to zones, Terrain3D and building scenes. The kit's
## solver runs in plain python3 (`roadkit_cli.py`) and only the mesh sweep runs in Blender, headless
## (`build_roads_piece.sh`). The `.roads.json` record is the source of truth: every gesture is one undo
## step that restores the record as it was.

const Gestures := preload("res://addons/road_kit/road_kit_gestures.gd")
const Service := preload("res://addons/road_kit/road_kit_service.gd")
const NetworkScript := preload("res://addons/road_kit/road_kit_network.gd")
const OverlayScript := preload("res://addons/road_kit/road_kit_overlay.gd")

var dock: VBoxContainer
var status: Label
var findings: ItemList
var link_type: OptionButton
var build_thread: Thread

func _enter_tree() -> void:
	dock = VBoxContainer.new()
	dock.name = "Road Kit"
	status = Label.new()
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.text = "Select a RoadKitNetwork, a road or a point."
	dock.add_child(status)
	_section("Network")
	_button("New Network", _on_new_network)
	_button("Load Record", _on_load_record)
	_button("Save Record", _on_save_record)
	_section("Author")
	_button("New Road", _on_new_road)
	_button("Extend Road", func(): _gesture_one("Extend Road", Gestures.extend_road))
	_button("Insert Point After", func(): _gesture_one("Insert Point", Gestures.insert_after))
	_button("Delete Point", func(): _gesture_one("Delete Point", Gestures.delete_point))
	var row := HBoxContainer.new()
	link_type = OptionButton.new()
	for t in ["SEGMENT", "JUNCTION", "AUX"]:
		link_type.add_item(t)
	row.add_child(link_type)
	var cb := Button.new()
	cb.text = "Connect"
	cb.pressed.connect(_on_connect)
	row.add_child(cb)
	dock.add_child(row)
	_button("Make Intersection", _on_make_intersection)
	_button("Make Ramp", _on_make_ramp)
	_section("Solve / Build")
	_button("Validate", _on_validate)
	_button("Auto Setback", _on_setback)
	_button("Refresh Preview", _on_refresh)
	_button("Build Piece", _on_build)
	findings = ItemList.new()
	findings.custom_minimum_size = Vector2(0, 160)
	findings.item_selected.connect(_on_finding_selected)
	dock.add_child(findings)
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, dock)
	get_editor_interface().get_selection().selection_changed.connect(_on_selection_changed)

func _exit_tree() -> void:
	if build_thread != null and build_thread.is_started():
		build_thread.wait_to_finish()
	remove_control_from_docks(dock)
	dock.queue_free()

func _section(title: String) -> void:
	var l := Label.new()
	l.text = title
	l.add_theme_color_override("font_color", Color(0.6, 0.8, 1.0))
	dock.add_child(l)

func _button(text: String, cb: Callable) -> void:
	var b := Button.new()
	b.text = text
	b.pressed.connect(cb)
	dock.add_child(b)

# ── selection ──────────────────────────────────────────────────────────────────

func _selected() -> Array:
	return get_editor_interface().get_selection().get_selected_nodes()

func _selected_points() -> Array:
	return _selected().filter(func(n): return Gestures.is_point(n))

func _network() -> Node:
	for n in _selected():
		var net := Gestures.network_of(n)
		if net != null:
			return net
	var root := get_editor_interface().get_edited_scene_root()
	if root == null:
		return null
	if root.get_script() == NetworkScript:
		return root
	for c in root.find_children("*", "Node3D", true, false):
		if c.get_script() == NetworkScript:
			return c
	return null

func _on_selection_changed() -> void:
	var pts := _selected_points()
	if pts.size() == 1:
		status.text = "%s  uid %s  role %s  links %d" % [pts[0].name, pts[0].uid, pts[0].fields["role"], pts[0].links.size()]
	elif pts.size() > 1:
		status.text = "%d points selected" % pts.size()

func _say(r: Dictionary) -> void:
	status.text = ("" if r.get("ok", false) else "✗ ") + str(r.get("message", ""))

# ── undo: the record is the source of truth ───────────────────────────────────

func _undoable(label: String, net: Node, change: Callable) -> Dictionary:
	var before: Dictionary = net.to_record()
	var r: Dictionary = change.call()
	if not r.get("ok", false):
		net.from_record(before)
		return r
	var after: Dictionary = net.to_record()
	var ur := get_undo_redo()
	ur.create_action("Road Kit: " + label, UndoRedo.MERGE_DISABLE, net)
	ur.add_do_method(net, "from_record", after)
	ur.add_undo_method(net, "from_record", before)
	ur.commit_action(false)
	_refresh(net)
	return r

func _gesture_one(label: String, fn: Callable) -> void:
	var pts := _selected_points()
	if pts.size() != 1:
		_say({"ok": false, "message": "%s: select exactly one road point" % label})
		return
	var p: Node = pts[0]
	var net := Gestures.network_of(p)
	var r := _undoable(label, net, func(): return fn.call(p))
	_say(r)
	if r.get("node") != null:
		get_editor_interface().get_selection().clear()
		get_editor_interface().get_selection().add_node(r["node"])

func _on_new_network() -> void:
	var root := get_editor_interface().get_edited_scene_root()
	if root == null:
		_say({"ok": false, "message": "open a scene first"})
		return
	var net: Node3D = NetworkScript.new()
	net.name = "RoadKitNetwork"
	root.add_child(net, true)
	net.owner = root
	net.record_path = root.scene_file_path.get_base_dir().path_join(root.name + ".roads.json")
	_say({"ok": true, "message": "network created; record -> " + net.record_path})

func _on_new_road() -> void:
	var net := _network()
	if net == null:
		_say({"ok": false, "message": "no RoadKitNetwork in this scene -- New Network first"})
		return
	var n: int = net.roads().size()
	var road_name := "road_%d" % n
	while net.get_node_or_null(NodePath(road_name)) != null:
		n += 1
		road_name = "road_%d" % n
	var origin := Vector3.ZERO
	var pts := _selected_points()
	if pts.size() == 1:
		origin = pts[0].network_transform().origin + Vector3(20, 0, 0)
	_say(_undoable("New Road", net, func(): return Gestures.new_road(net, road_name, origin)))

func _on_connect() -> void:
	var pts := _selected_points()
	if pts.size() != 2:
		_say({"ok": false, "message": "Connect: select exactly two road points"})
		return
	var t := link_type.get_item_text(link_type.selected)
	_say(_undoable("Connect " + t, Gestures.network_of(pts[0]), func(): return Gestures.connect_points(pts[0], pts[1], t)))

func _on_make_intersection() -> void:
	var pts := _selected_points()
	if pts.is_empty():
		_say({"ok": false, "message": "select the mouths"})
		return
	_say(_undoable("Make Intersection", Gestures.network_of(pts[0]), func(): return Gestures.make_intersection(pts)))

func _on_make_ramp() -> void:
	var pts := _selected_points()
	if pts.size() != 2 or pts[0].get_parent() == pts[1].get_parent():
		_say({"ok": false, "message": "Make Ramp: select a mainline point and the mouth of the ramp's own road"})
		return
	var net := Gestures.network_of(pts[0])
	if not _save_for_service(net):
		return
	var before: Dictionary = net.to_record()
	var r := Service.run("ramp", net.record_path, [pts[0].uid, pts[1].uid])
	if r.get("failed", false):
		_say({"ok": false, "message": r["error"]})
		return
	net.load_record(net.record_path)
	var ur := get_undo_redo()
	ur.create_action("Road Kit: Make Ramp", UndoRedo.MERGE_DISABLE, net)
	ur.add_do_method(net, "from_record", net.to_record())
	ur.add_undo_method(net, "from_record", before)
	ur.commit_action(false)
	_say({"ok": r["errors"] == 0, "message": "ramp: slot %s opened over %d station(s)%s; gate %d error(s)" % [r["field"], r["slot_stations"], "" if r["aligned"] else " (NOT aligned -- no aux slot)", r["errors"]]})
	_refresh(net)

# ── record / solver / build ───────────────────────────────────────────────────

func _record_path(net: Node) -> String:
	if net.record_path == "":
		var root := get_editor_interface().get_edited_scene_root()
		net.record_path = root.scene_file_path.get_base_dir().path_join(String(net.name) + ".roads.json")
	return net.record_path

func _on_save_record() -> void:
	var net := _network()
	if net == null:
		return
	var err: int = net.save_record(_record_path(net))
	_say({"ok": err == OK, "message": "saved %s (%s)" % [net.record_path, error_string(err)]})

func _on_load_record() -> void:
	var net := _network()
	if net == null:
		return
	var before: Dictionary = net.to_record()
	var warnings: Array = net.load_record(_record_path(net))
	var ur := get_undo_redo()
	ur.create_action("Road Kit: Load Record", UndoRedo.MERGE_DISABLE, net)
	ur.add_do_method(net, "from_record", net.to_record())
	ur.add_undo_method(net, "from_record", before)
	ur.commit_action(false)
	_say({"ok": warnings.is_empty(), "message": "loaded %s%s" % [net.record_path, "" if warnings.is_empty() else " -- " + "; ".join(warnings)]})
	_refresh(net)

## Every service call sees the terrain the game has: ground heights are re-sampled from the scene's
## Terrain3D (if any) into the record before it is written.
func _save_for_service(net: Node) -> bool:
	var root := get_editor_interface().get_edited_scene_root()
	if root != null:
		var terrains := root.find_children("*", "Terrain3D", true, false)
		if not terrains.is_empty():
			Gestures.sample_ground(net, terrains[0])
	return net.save_record(_record_path(net)) == OK

func _on_validate() -> void:
	var net := _network()
	if net == null or not _save_for_service(net):
		return
	var r := Service.run("validate", net.record_path)
	findings.clear()
	if r.get("failed", false):
		_say({"ok": false, "message": r["error"]})
		return
	var labels := {}
	for p in net.all_points():
		labels[p.uid] = "%s/%s" % [p.get_parent().name, p.name]
	for f in r["findings"]:
		var msg: String = f["message"]
		for uid in labels:
			msg = msg.replace(uid, labels[uid])
		var i := findings.add_item("[%s] %s: %s -- %s" % [f["severity"], f["code"], labels.get(f["obj"], f["obj"]), msg])
		findings.set_item_metadata(i, f["obj"])
	_say({"ok": r["errors"] == 0, "message": "gate: %d error(s), %d warning(s)" % [r["errors"], r["warnings"]]})

func _on_finding_selected(index: int) -> void:
	var net := _network()
	var p = net.find_point(str(findings.get_item_metadata(index))) if net != null else null
	if p != null:
		get_editor_interface().get_selection().clear()
		get_editor_interface().get_selection().add_node(p)

func _on_setback() -> void:
	var net := _network()
	if net == null or not _save_for_service(net):
		return
	var before: Dictionary = net.to_record()
	var r := Service.run("setback", net.record_path)
	if r.get("failed", false):
		_say({"ok": false, "message": r["error"]})
		return
	net.load_record(net.record_path)
	var ur := get_undo_redo()
	ur.create_action("Road Kit: Auto Setback", UndoRedo.MERGE_DISABLE, net)
	ur.add_do_method(net, "from_record", net.to_record())
	ur.add_undo_method(net, "from_record", before)
	ur.commit_action(false)
	_say({"ok": true, "message": "auto setback: %d mouth(s) moved over %d junction(s)" % [r["moved"].size(), r["cliques"]]})
	_refresh(net)

func _on_refresh() -> void:
	var net := _network()
	if net != null:
		_refresh(net)

func _refresh(net: Node) -> void:
	if net.record_path == "" or not _save_for_service(net):
		return
	var r := Service.run("centrelines", net.record_path)
	if r.get("failed", false):
		return
	var ov = net.get_node_or_null("_RoadKitOverlay")
	if ov == null:
		ov = OverlayScript.new()
		ov.name = "_RoadKitOverlay"
		net.add_child(ov)
	ov.redraw(net, r["runs"])

func _on_build() -> void:
	var net := _network()
	if net == null or not _save_for_service(net):
		return
	if build_thread != null and build_thread.is_started():
		_say({"ok": false, "message": "a build is already running"})
		return
	var piece := "Roads_" + String(net.name)
	var record: String = net.record_path
	status.text = "building %s (python3 lanes -> Blender meshes -> bake)..." % piece
	build_thread = Thread.new()
	build_thread.start(func():
		var r := Service.build_piece(record, piece)
		call_deferred("_build_done", piece, r))

func _build_done(piece: String, r: Dictionary) -> void:
	build_thread.wait_to_finish()
	var log_text: String = r["log"]
	var tail := "\n".join(log_text.split("\n").slice(-6))
	_say({"ok": r["ok"], "message": ("built %s" % piece if r["ok"] else "build FAILED") + "\n" + tail})
	get_editor_interface().get_resource_filesystem().scan()
