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
const Zones := preload("res://addons/road_kit/road_kit_zones.gd")
const Ground := preload("res://addons/road_kit/road_kit_ground.gd")
const Preview := preload("res://addons/road_kit/road_kit_preview.gd")
const Stamp := preload("res://addons/road_kit/road_kit_stamp.gd")
const GizmoScript := preload("res://addons/road_kit/road_kit_gizmo.gd")
const Fields := preload("res://addons/road_kit/road_kit_fields.gd")
## Where Refresh Preview writes the zones it colours by -- NOT the network's own `<stem>.zones.json`,
## which is the build's input and is written only by Build.
const PREVIEW_ZONES := "user://road_kit_preview.zones.json"
const PREVIEW_SETTING := "road_kit/preview_pieces"

var dock: VBoxContainer
var status: Label
var findings: ItemList
var link_type: OptionButton
var build_thread: Thread
var preview_pieces: CheckBox
var gizmo: EditorNode3DGizmoPlugin
var ramp_lanes: SpinBox
var ramp_carriageway: OptionButton
var ramp_entrance: CheckBox
var cross_groups := {}
## The point the artist selected LAST -- the kit's "active" point (Apply Cross-Section's source).
var active_point: Node
var _prev_selection := []

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
	var rrow := HBoxContainer.new()
	ramp_lanes = SpinBox.new()
	ramp_lanes.min_value = 1
	ramp_lanes.max_value = 4
	ramp_lanes.value = 1
	ramp_lanes.tooltip_text = "lanes that leave with the ramp"
	rrow.add_child(ramp_lanes)
	ramp_carriageway = OptionButton.new()
	ramp_carriageway.add_item("FWD")
	ramp_carriageway.add_item("BWD")
	rrow.add_child(ramp_carriageway)
	ramp_entrance = CheckBox.new()
	ramp_entrance.text = "entrance"
	rrow.add_child(ramp_entrance)
	dock.add_child(rrow)
	_button("Branch Ramp Here", _on_branch_ramp)
	_button("Merge Points", func(): _selection_gesture("Merge Points", "merge", 2))
	_button("Split To New Road", func(): _selection_gesture("Split To New Road", "split", 1))
	_button("Select Junction", _on_select_junction)
	_button("Follow Road (Auto)", _on_follow_road)
	var grow := HFlowContainer.new()
	for g in Fields.MASK_GROUPS:
		var cb2 := CheckBox.new()
		cb2.text = g.capitalize()
		grow.add_child(cb2)
		cross_groups[g] = cb2
	dock.add_child(grow)
	_button("Apply Cross-Section (last selected -> others)", _on_cross_section)
	_section("Repair")
	_button("Tidy Roads", func(): _network_gesture("Tidy Roads", "tidy"))
	_button("Renumber Roads", func(): _network_gesture("Renumber Roads", "renumber"))
	_button("Repair Links", func(): _network_gesture("Repair Links", "repair"))
	_section("Solve / Build")
	_button("Validate", _on_validate)
	_button("Auto Setback", _on_setback)
	_button("Refresh Preview", _on_refresh)
	_button("Build Piece", _on_build)
	_button("Flow Report", _on_flow_report)
	_section("Terrain")
	_button("Stamp Terrain", func(): _on_stamp(false))
	_button("Restore Terrain", func(): _on_stamp(true))
	preview_pieces = CheckBox.new()
	preview_pieces.text = "Preview Pieces (built roads + zones, never saved)"
	# ON by default and remembered: a scene with road pieces SHOWS them when it opens. Off, the editor
	# showed an empty network and nothing else, which read as "the roads did not load".
	var es := get_editor_interface().get_editor_settings()
	if not es.has_setting(PREVIEW_SETTING):
		es.set_setting(PREVIEW_SETTING, true)
	preview_pieces.button_pressed = bool(es.get_setting(PREVIEW_SETTING))
	preview_pieces.toggled.connect(func(on):
		get_editor_interface().get_editor_settings().set_setting(PREVIEW_SETTING, on)
		_on_preview_pieces(on))
	dock.add_child(preview_pieces)
	findings = ItemList.new()
	findings.custom_minimum_size = Vector2(0, 160)
	findings.item_selected.connect(_on_finding_selected)
	dock.add_child(findings)
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, dock)
	gizmo = GizmoScript.new()
	gizmo.undo = get_undo_redo()
	add_node_3d_gizmo_plugin(gizmo)
	get_editor_interface().get_selection().selection_changed.connect(_on_selection_changed)
	scene_changed.connect(_on_scene_changed)
	_on_scene_changed.call_deferred(get_editor_interface().get_edited_scene_root())
	# Editor self-test: `ROADKIT_EDITOR_SELFTEST=res://scene.tscn godot --headless --editor --path .`
	# runs the dock's scene-level paths INSIDE the editor, where a non-@tool JVM script is a placeholder
	# -- the environment a SceneTree test never sees.
	if OS.get_environment("ROADKIT_EDITOR_SELFTEST") != "":
		_selftest.call_deferred(OS.get_environment("ROADKIT_EDITOR_SELFTEST"))

func _exit_tree() -> void:
	if build_thread != null and build_thread.is_started():
		build_thread.wait_to_finish()
	Preview.clear(get_editor_interface().get_edited_scene_root())
	if gizmo != null:
		remove_node_3d_gizmo_plugin(gizmo)
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
	for p in pts:
		if not _prev_selection.has(p):
			active_point = p
	if pts.size() == 1:
		active_point = pts[0]
	_prev_selection = pts
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
	# An unloaded network (a freshly opened scene) has nothing to draw yet -- and nothing to save.
	if net.record_path == "" or net.all_points().is_empty() or not _save_for_service(net):
		return
	# B6c: colour by zone. The zones are written to a scratch path, so a refresh never touches the
	# build's own sidecar.
	var markers := Zones.markers_in(get_editor_interface().get_edited_scene_root())
	var extra := []
	if not markers.is_empty() and Zones.write_sidecar(PREVIEW_ZONES, Zones.zones_record(net, markers)) == OK:
		extra = ["--zones", ProjectSettings.globalize_path(PREVIEW_ZONES)]
	var r := Service.run("centrelines", net.record_path, extra)
	if r.get("failed", false):
		return
	var ov = net.get_node_or_null("_RoadKitOverlay")
	if ov == null:
		ov = OverlayScript.new()
		ov.name = "_RoadKitOverlay"
		net.add_child(ov)
	ov.redraw(net, r, markers)
	# Face the points the tool owns (after `_save_for_service` has promoted the rotated ones).
	Service.face_network(net)

## B7: write the roads into the scene's Terrain3D (carve + fill, derived from the natural ground) or put
## the natural ground back. Saves the terrain data directory -- Terrain3D's own undo does not cover a
## scripted edit, and Restore Terrain is the way back.
func _on_stamp(restore: bool) -> void:
	var net := _network()
	var root := get_editor_interface().get_edited_scene_root()
	var terrains := root.find_children("*", "Terrain3D", true, false) if root != null else []
	if net == null or terrains.is_empty():
		_say({"ok": false, "message": "Stamp Terrain needs a RoadKitNetwork and a Terrain3D in the scene"})
		return
	if not restore and not _save_for_service(net):
		return
	var terrain: Node = terrains[0]
	var r := Stamp.stamp_network(net, terrain, restore)
	if r["ok"] and r.get("changed", 0) > 0:
		terrain.data.save_directory(str(terrain.get("data_directory")))
	_say(r)

# ── B8: gestures the solver owns, over the record ─────────────────────────────

## Run a `roadkit_cli.py` gesture on the record as ONE undo step: the network before, the network the
## rewritten record describes after. `select` names uids (from the CLI's answer) to select afterwards.
func _record_gesture(label: String, net: Node, cmd: String, args: Array, select: Array = []) -> Dictionary:
	if not _save_for_service(net):
		return {"failed": true, "error": "could not save the record"}
	var before: Dictionary = net.to_record()
	var r := Service.record_gesture(net, cmd, args)
	if r.get("failed", false):
		net.from_record(before)
		_say({"ok": false, "message": "%s: %s" % [label, r.get("error", "")]})
		return r
	var ur := get_undo_redo()
	ur.create_action("Road Kit: " + label, UndoRedo.MERGE_DISABLE, net)
	ur.add_do_method(net, "from_record", net.to_record())
	ur.add_undo_method(net, "from_record", before)
	ur.commit_action(false)
	_refresh(net)
	var keys := []
	for k in select:
		if r.has(k):
			keys.append(str(r[k]))
	if not keys.is_empty():
		get_editor_interface().get_selection().clear()
		for uid in keys:
			var p = net.find_point(uid)
			if p != null:
				get_editor_interface().get_selection().add_node(p)
	_say({"ok": int(r.get("errors", 0)) == 0, "message": "%s -- gate %d error(s), %d warning(s)" % [r.get("message", label), r.get("errors", 0), r.get("warnings", 0)]})
	return r

func _selection_gesture(label: String, cmd: String, need: int) -> void:
	var pts := _selected_points()
	if pts.size() < need:
		_say({"ok": false, "message": "%s: select %d or more road points" % [label, need]})
		return
	var net := Gestures.network_of(pts[0])
	var uids := ",".join(PackedStringArray(pts.map(func(p): return p.uid)))
	_record_gesture(label, net, cmd, [uids], ["keep"])

func _network_gesture(label: String, cmd: String) -> void:
	var net := _network()
	if net != null:
		_record_gesture(label, net, cmd, [])

func _on_branch_ramp() -> void:
	var pts := _selected_points()
	if pts.size() != 1:
		_say({"ok": false, "message": "Branch Ramp Here: select the one mainline station to branch from"})
		return
	var args := [pts[0].uid, "--lanes", str(int(ramp_lanes.value)), "--carriageway", ramp_carriageway.get_item_text(ramp_carriageway.selected)]
	if ramp_entrance.button_pressed:
		args.append("--entrance")
	_record_gesture("Branch Ramp Here", Gestures.network_of(pts[0]), "branch_ramp", args, ["far"])

func _on_cross_section() -> void:
	var pts := _selected_points()
	if pts.size() < 2 or active_point == null or not pts.has(active_point):
		_say({"ok": false, "message": "Apply Cross-Section: select the targets, then the source point last"})
		return
	var groups := []
	for g in cross_groups:
		if cross_groups[g].button_pressed:
			groups.append(g)
	var others := pts.filter(func(p): return p != active_point).map(func(p): return p.uid)
	_record_gesture("Apply Cross-Section", Gestures.network_of(active_point), "cross_section",
			[active_point.uid, ",".join(PackedStringArray(others)), ",".join(PackedStringArray(groups))])

func _on_select_junction() -> void:
	var pts := _selected_points()
	var members: Array = Gestures.junction_members(pts[0]) if pts.size() >= 1 else []
	if members.is_empty():
		_say({"ok": false, "message": "Select Junction: select a junction mouth"})
		return
	get_editor_interface().get_selection().clear()
	for p in members:
		get_editor_interface().get_selection().add_node(p)
	_say({"ok": true, "message": "%d mouth(s) -- move or rotate them together to move the crossing" % members.size()})

func _on_follow_road() -> void:
	var pts := _selected_points()
	if pts.is_empty():
		_say({"ok": false, "message": "Follow Road (Auto): select road points"})
		return
	var net := Gestures.network_of(pts[0])
	if not _save_for_service(net):
		return
	var f := Service.run("facings", net.record_path)
	if f.get("failed", false):
		_say({"ok": false, "message": str(f.get("error", ""))})
		return
	_gesture_many("Follow Road (Auto)", net, func(): return Gestures.follow_road(pts, f["facings"]))

func _gesture_many(label: String, net: Node, fn: Callable) -> void:
	_say(_undoable(label, net, fn))

func _on_flow_report() -> void:
	var net := _network()
	if net == null or not _save_for_service(net):
		return
	var r := Service.run("flow", net.record_path)
	findings.clear()
	if r.get("failed", false) or r.get("report") == null:
		_say({"ok": false, "message": "flow report: %s" % r.get("error", "the gate is red -- Validate first")})
		return
	var rep: Dictionary = r["report"]
	for key in ["broken", "misjoined", "unreached", "ramp_orphans", "path_off_road", "open_end"]:
		for item in rep.get(key, []):
			findings.add_item("[%s] %s" % [key, str(item)])
	_say({"ok": rep["broken"].is_empty() and rep["misjoined"].is_empty() and rep["unreached"].is_empty() and rep["ramp_orphans"].is_empty(),
			"message": "flow: %d lanes, %d junctions, %d broken, %d misjoined, %d unreached, %d ramp orphan(s), %d open end(s), %d spawnable" % [
				rep["lanes"], rep["junctions"], rep["broken"].size(), rep["misjoined"].size(), rep["unreached"].size(),
				rep["ramp_orphans"].size(), rep["open_end"].size(), rep["spawnable"]]})

## A scene was opened or switched to: show its road pieces (the preview lives under ONE scene root, so
## every switch rebuilds it for the scene now in front of the artist).
func _on_scene_changed(root: Node) -> void:
	if root == null or preview_pieces == null or not preview_pieces.button_pressed:
		return
	if Zones.markers_in(root).is_empty() and _network() == null:
		return
	if Preview.find(root) == null:
		_on_preview_pieces(true)

func _on_preview_pieces(on: bool, reload: bool = false) -> void:
	var root := get_editor_interface().get_edited_scene_root()
	if root == null:
		return
	if not on:
		Preview.clear(root)
		_say({"ok": true, "message": "piece preview off"})
		return
	var r := Preview.build(root, _network(), Zones.markers_in(root), reload)
	_say(r)
	var net := _network()
	if net != null:
		_refresh(net)

func _on_build() -> void:
	var net := _network()
	if net == null or not _save_for_service(net):
		return
	if build_thread != null and build_thread.is_started():
		_say({"ok": false, "message": "a build is already running"})
		return
	var piece := "Roads_" + String(net.name)
	var record: String = net.record_path
	# B6: the scene's ZoneMarkers cut the network into a piece per zone. No markers -> one piece.
	var markers := Zones.markers_in(get_editor_interface().get_edited_scene_root())
	var zones_path := ""
	var notes := []
	if not markers.is_empty():
		var rec := Zones.zones_record(net, markers)
		notes.append_array(rec["warnings"])
		zones_path = Zones.sidecar_path(record)
		if Zones.write_sidecar(zones_path, rec) != OK:
			_say({"ok": false, "message": "could not write " + zones_path})
			return
	# B6b: the ground every support stands on, sampled from the scene's Terrain3D over the whole
	# footprint. No terrain -> no sidecar, and the build lerps the stations' own ground_z as before.
	var ground_path := ""
	var terrains := get_editor_interface().get_edited_scene_root().find_children("*", "Terrain3D", true, false)
	if not terrains.is_empty():
		var g := Ground.write_for(net, terrains[0])
		notes.append(g["message"])
		if g["ok"]:
			ground_path = g["path"]
	status.text = "building %s%s (python3 lanes -> Blender meshes -> bake)..." % [piece, " per zone (%d marker(s))" % markers.size() if zones_path != "" else ""]
	build_thread = Thread.new()
	build_thread.start(func():
		var r := Service.build_piece(record, piece, zones_path, ground_path)
		call_deferred("_build_done", piece, r, net, notes))

func _build_done(piece: String, r: Dictionary, net: Node, notes: Array) -> void:
	build_thread.wait_to_finish()
	var log_text: String = r["log"]
	var lines := Array(log_text.split("\n")).filter(func(l): return not l.begins_with("ROADKIT_PIECES "))
	var tail := "\n".join(PackedStringArray(lines.slice(-6)))
	var wired := ""
	if r["ok"] and is_instance_valid(net):
		var markers := Zones.markers_in(get_editor_interface().get_edited_scene_root())
		var pieces := Zones.pieces_from_log(log_text)
		var plan := Zones.plan_wiring(net, markers, pieces, piece)
		notes.append_array(plan["notes"])
		if not plan["changes"].is_empty():
			# One undo step for the whole wiring, as a property change on each Zone -- so the scene is
			# marked modified and Ctrl+Z puts every marker back.
			var ur := get_undo_redo()
			ur.create_action("Road Kit: Wire Road Pieces", UndoRedo.MERGE_DISABLE, net)
			for c in plan["changes"]:
				ur.add_do_property(c["zone"], c["property"], c["new"])
				ur.add_undo_property(c["zone"], c["property"], c["old"])
			ur.commit_action()
		wired = "\n%d piece(s), %d zone field(s) wired" % [pieces.size(), plan["changes"].size()]
	var msg := ("built %s" % piece if r["ok"] else "build FAILED") + wired
	for n in notes:
		msg += "\n• " + str(n)
	_say({"ok": r["ok"], "message": msg + "\n" + tail})
	get_editor_interface().get_resource_filesystem().scan()
	if r["ok"] and preview_pieces.button_pressed:
		_on_preview_pieces(true, true)

func _selftest(scene_path: String) -> void:
	for i in 30:
		await get_tree().process_frame
	get_editor_interface().open_scene_from_path(scene_path)
	for i in 30:
		await get_tree().process_frame
	var root := get_editor_interface().get_edited_scene_root()
	print("[selftest] scene root: ", root)
	var markers := Zones.markers_in(root)
	print("[selftest] markers: ", markers.size())
	for m in markers:
		var z = m.get("zone")
		print("[selftest]   ", m.name, " zone=", z, " path=", z.get("geometry_path") if z != null else "-", " placed=", z.get("geometry_world_placed") if z != null else "-")
	var net := _network()
	print("[selftest] network: ", net, " points: ", net.all_points().size() if net != null else -1)
	var rec_ok := true
	if net != null and FileAccess.file_exists(net.record_path):
		var rec = JSON.parse_string(FileAccess.get_file_as_string(net.record_path))
		rec_ok = typeof(rec) == TYPE_DICTIONARY and not (rec.get("points", []) as Array).is_empty()
	print("[selftest] record intact after open: ", rec_ok)
	if not rec_ok:
		get_tree().quit(1)
		return
	var holder: Node3D = Preview.find(root)
	print("[selftest] preview shown on open: ", holder != null, " (", holder.get_child_count() if holder != null else 0, " piece(s))")
	if holder == null:
		get_tree().quit(1)
		return
	for c in holder.get_children():
		var meshes := c.find_children("*", "MeshInstance3D", true, false)
		var aabb := AABB()
		for mi in meshes:
			aabb = aabb.merge(mi.global_transform * mi.get_aabb())
		print("[selftest]   ", c.name, " visible=", c.is_visible_in_tree(), " meshes=", meshes.size(), " aabb=", aabb)
	get_tree().quit()
