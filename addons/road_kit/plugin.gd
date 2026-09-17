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
const Tool := preload("res://addons/road_kit/road_kit_tool.gd")
const PREVIEW_SETTING := "road_kit/preview_pieces"
const DRAFT_SETTING := "road_kit/draft_surface"
const PARTNERS_SETTING := "road_kit/move_junctions_with_road"
## B10.0/B10.2: how long the network must be quiet after a move or an inspector edit before the overlay,
## the draft surface and the drape run. A drag emits a change every frame; this collapses it.
const SETTLE_SECONDS := 0.25
## A point dragged sideways whose height sat within this band of its ground (metres, height minus ground)
## was AT GRADE, and keeps that height above the ground at its new place. Outside it -- a deck, a pier --
## its height is the artist's and is left alone.
const DRAPE_BAND := Vector2(-0.5, 1.5)
const LABEL_NAME := "_RoadKitLabel"

var dock: VBoxContainer
var status: Label
var findings: ItemList
var link_type: OptionButton
var build_thread: Thread
var preview_pieces: CheckBox
var draft_surface: CheckBox
var move_partners: CheckBox
var gizmo: EditorNode3DGizmoPlugin
var ramp_lanes: SpinBox
var ramp_carriageway: OptionButton
var ramp_entrance: CheckBox
var cross_groups := {}
## The point the artist selected LAST -- the kit's "active" point (Apply Cross-Section's source).
var active_point: Node
var _prev_selection := []
var settle_timer: Timer
## Networks with a change not yet refreshed: instance id -> network.
var _pending := {}
## Per network (instance id): the record text, point positions and ground heights as of the last refresh.
## A settle that finds the same record text does nothing, so a refresh's own re-facing cannot loop.
var _baseline := {}
var _adopted := {}
## Undo history size per history id, to tell a NEW action from an undo or redo (`_on_version_changed`).
var _history_count := {}
## True from an undo/redo until the next settle: points it moves were not dragged, so nothing is draped
## (draping there would commit an action and throw away the redo history).
var _suppress_drape := false
## B10.3: the viewport tool mode and its toolbar (in the 3D viewport's menu bar).
var tool: RefCounted = Tool.new()
var toolbar: HBoxContainer
var tool_buttons := {}
## SELECT mode: where the left button went down (a click selects a road on RELEASE, never on the press).
var _select_press = null
## B10.8: the solver runs on worker threads. Two slots, each LATEST-WINS per network: FAST (centrelines,
## draft, facings, junction labels -- ~0.1 s) and CROSS (the cross-zone successor edges, which need the
## gate and a whole lane export -- seconds). A request made while a slot is busy replaces whatever was
## still waiting for it. `thread` is the running Thread or null; `next` maps network id -> request.
var _live := {"fast": {"thread": null, "next": {}}, "cross": {"thread": null, "next": {}}}
## Per network id: the last FAST result drawn `{"text", "centrelines"}`, the last CROSS edges
## `{"text", "cross"}`, and the record text last sent to FAST from a drag (a drag re-sends nothing unchanged).
var _live_last := {}
var _live_cross := {}
var _live_sent := {}
## While the mouse is held, edits are sent to FAST at most this often (seconds).
const LIVE_TICK := 0.05
const LIVE_DIR := "user://road_kit_live"
## A press and release this close (px) are a click, not a drag.
const CLICK_SLOP_PX := 4.0
var live_timer: Timer

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
	_button("Build Piece (changed zones)", _on_build)
	_button("Rebuild All Pieces", func(): _on_build(false))
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
	# B10.1: the solver's paved footprint drawn on every refresh -- the road you are editing, not the
	# last build. ON by default, remembered.
	draft_surface = CheckBox.new()
	draft_surface.text = "Draft Surface (solver's tarmac + kerbs, live)"
	if not es.has_setting(DRAFT_SETTING):
		es.set_setting(DRAFT_SETTING, true)
	draft_surface.button_pressed = bool(es.get_setting(DRAFT_SETTING))
	draft_surface.toggled.connect(func(on):
		get_editor_interface().get_editor_settings().set_setting(DRAFT_SETTING, on)
		var n := _network()
		if n != null:
			_refresh(n))
	dock.add_child(draft_surface)
	# B10.5: a dragged road takes its junctions along (the other roads' mouths move with it). Remembered.
	move_partners = CheckBox.new()
	move_partners.text = "Dragging a road moves its junctions"
	if not es.has_setting(PARTNERS_SETTING):
		es.set_setting(PARTNERS_SETTING, true)
	move_partners.button_pressed = bool(es.get_setting(PARTNERS_SETTING))
	move_partners.toggled.connect(func(on): get_editor_interface().get_editor_settings().set_setting(PARTNERS_SETTING, on))
	dock.add_child(move_partners)
	findings = ItemList.new()
	findings.custom_minimum_size = Vector2(0, 160)
	findings.item_selected.connect(_on_finding_selected)
	dock.add_child(findings)
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, dock)
	gizmo = GizmoScript.new()
	gizmo.undo = get_undo_redo()
	add_node_3d_gizmo_plugin(gizmo)
	settle_timer = Timer.new()
	settle_timer.one_shot = true
	settle_timer.wait_time = SETTLE_SECONDS
	settle_timer.timeout.connect(_on_settle)
	add_child(settle_timer)
	live_timer = Timer.new()
	live_timer.one_shot = true
	live_timer.wait_time = LIVE_TICK
	live_timer.timeout.connect(_on_live_tick)
	add_child(live_timer)
	get_undo_redo().version_changed.connect(_on_version_changed)
	toolbar = HBoxContainer.new()
	var tl := Label.new()
	tl.text = "Road Kit:"
	toolbar.add_child(tl)
	var group := ButtonGroup.new()
	for m in range(Tool.MODE_NAMES.size()):
		var b := Button.new()
		b.text = Tool.MODE_NAMES[m]
		b.toggle_mode = true
		b.button_group = group
		b.button_pressed = m == Tool.Mode.OFF
		b.tooltip_text = "Road Kit viewport tool: " + Tool.MODE_NAMES[m]
		b.toggled.connect(func(on): if on: _set_tool_mode(m))
		toolbar.add_child(b)
		tool_buttons[m] = b
	add_control_to_container(CONTAINER_SPATIAL_EDITOR_MENU, toolbar)
	# The tool acts wherever the artist clicks, not only while a road node is selected.
	set_input_event_forwarding_always_enabled()
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
	for slot in _live.values():
		if slot["thread"] != null:
			slot["thread"].wait_to_finish()
			slot["thread"] = null
	if _service_thread != null:
		_service_thread.wait_to_finish()
		_service_thread = null
	if toolbar != null:
		remove_control_from_container(CONTAINER_SPATIAL_EDITOR_MENU, toolbar)
		toolbar.queue_free()
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
			_adopt(net)
			return net
	var nets := _networks_in(get_editor_interface().get_edited_scene_root())
	if nets.is_empty():
		return null
	_adopt(nets[0])
	return nets[0]

func _networks_in(root: Node) -> Array:
	if root == null:
		return []
	var out := []
	if root.get_script() == NetworkScript:
		out.append(root)
	for c in root.find_children("*", "Node3D", true, false):
		if c.get_script() == NetworkScript:
			out.append(c)
	return out

## Make a network editable: load its record if the scene holds only the node (B10.0 -- the points used to
## appear only after the dock's Load Record, which nothing prompted), and listen for its edits. Loading is
## not an undoable action, so opening a scene does not mark it modified.
func _adopt(net: Node) -> void:
	var warnings: Array = net.ensure_loaded()
	if not warnings.is_empty():
		push_warning("Road Kit: %s: %s" % [net.name, "; ".join(PackedStringArray(warnings))])
	var id := net.get_instance_id()
	if not _adopted.has(id):
		_adopted[id] = true
		net.edited.connect(_on_network_edited.bind(net))

func _set_tool_mode(m: int) -> void:
	tool.set_mode(m)
	if tool_buttons.has(m) and not tool_buttons[m].button_pressed:
		tool_buttons[m].set_pressed_no_signal(true)
	if m != Tool.Mode.OFF:
		status.text = "tool: %s" % Tool.MODE_NAMES[m]

## B10.3: the viewport tool. Every click that changes the network is ONE undo step restoring the record.
func _forward_3d_gui_input(camera: Camera3D, event: InputEvent) -> int:
	if tool.mode == Tool.Mode.OFF:
		return EditorPlugin.AFTER_GUI_INPUT_PASS
	var net: Node3D = _network()
	if net == null:
		return EditorPlugin.AFTER_GUI_INPUT_PASS
	if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		if tool.finish():
			status.text = "tool: %s -- finished" % Tool.MODE_NAMES[tool.mode]
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		return EditorPlugin.AFTER_GUI_INPUT_PASS
	if not (event is InputEventMouseButton):
		return EditorPlugin.AFTER_GUI_INPUT_PASS
	# SELECT NEVER TAKES THE PRESS. A press may be the start of a drag on the move gizmo, and an arrow lying
	# along a road sits exactly over its centreline -- taking the press there selected the road instead, so
	# the point could not be dragged. A CLICK (released where it was pressed) selects the road under it,
	# deferred until the editor's own click-select has run. Alt-click on a mouth still selects its junction.
	if tool.mode == Tool.Mode.SELECT and event.button_index == MOUSE_BUTTON_LEFT and not event.alt_pressed:
		if event.pressed:
			_select_press = event.position
		else:
			if _select_press != null and event.position.distance_to(_select_press) <= CLICK_SLOP_PX:
				_select_click.call_deferred(net, camera, event.position)
			_select_press = null
		return EditorPlugin.AFTER_GUI_INPUT_PASS
	if not event.pressed:
		return EditorPlugin.AFTER_GUI_INPUT_PASS
	if event.button_index == MOUSE_BUTTON_RIGHT:
		return EditorPlugin.AFTER_GUI_INPUT_STOP if tool.finish() else EditorPlugin.AFTER_GUI_INPUT_PASS
	if event.button_index != MOUSE_BUTTON_LEFT:
		return EditorPlugin.AFTER_GUI_INPUT_PASS
	return tool_click(net, camera, event.position, event.alt_pressed)

## SELECT: a click that missed every point selects the road whose centreline it landed on.
func _select_click(net: Node3D, camera: Camera3D, screen: Vector2) -> void:
	if is_instance_valid(net) and is_instance_valid(camera) and tool.mode == Tool.Mode.SELECT:
		tool_click(net, camera, screen, false)

## One tool click, as the viewport delivers it -- public for the editor self-test.
func tool_click(net: Node3D, camera: Camera3D, screen: Vector2, alt: bool = false) -> int:
	var root := get_editor_interface().get_edited_scene_root()
	var terrains := root.find_children("*", "Terrain3D", true, false) if root != null else []
	var ov = net.get_node_or_null("_RoadKitOverlay")
	var ctx := {"net": net, "camera": camera, "terrain": terrains[0] if not terrains.is_empty() else null,
			"runs": ov.runs_drawn if ov != null else [], "alt": alt}
	var before: Dictionary = net.to_record()
	var r: Dictionary = tool.click(ctx, screen)
	if r.has("ramp"):
		_make_ramp(r["ramp"][0], r["ramp"][1])
		return EditorPlugin.AFTER_GUI_INPUT_STOP
	if r.get("changed", false):
		var ur := get_undo_redo()
		ur.create_action("Road Kit: " + Tool.MODE_NAMES[tool.mode], UndoRedo.MERGE_DISABLE, net)
		ur.add_do_method(net, "from_record", net.to_record())
		ur.add_undo_method(net, "from_record", before)
		ur.commit_action(false)
		_refresh(net)
	var sel: Array = r.get("select", [])
	if not sel.is_empty():
		get_editor_interface().get_selection().clear()
		for n in sel:
			if is_instance_valid(n):
				get_editor_interface().get_selection().add_node(n)
	if str(r.get("message", "")) != "":
		_say(r)
	return EditorPlugin.AFTER_GUI_INPUT_STOP if r.get("consume", true) else EditorPlugin.AFTER_GUI_INPUT_PASS

func _on_version_changed() -> void:
	var root := get_editor_interface().get_edited_scene_root()
	if root == null:
		return
	var ur := get_undo_redo()
	var hid := ur.get_object_history_id(root)
	var count := ur.get_history_undo_redo(hid).get_history_count()
	_suppress_drape = count <= int(_history_count.get(hid, -1))
	_history_count[hid] = count

func _on_network_edited(net: Node) -> void:
	if not is_instance_valid(net) or net.is_loading():
		return
	_pending[net.get_instance_id()] = net
	settle_timer.start()
	if Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT) and live_timer.is_stopped():
		live_timer.start()

## B10.8: WHILE THE MOUSE IS HELD the road follows it. Every LIVE_TICK the networks being dragged are sent
## to the FAST solver slot (latest wins, so a slow solve never queues up behind the mouse). Nothing is
## saved, draped or faced mid-drag -- the point under the gizmo is the gizmo's until release.
func _on_live_tick() -> void:
	if not Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT):
		return
	for id in _pending.keys():
		var net: Node = _pending[id]
		if is_instance_valid(net) and net.is_inside_tree():
			_request_live_drag(net)

func _request_live_drag(net: Node) -> void:
	var text: String = net.record_text()
	if _live_sent.get(net.get_instance_id(), "") == text:
		return
	_request_live(net, false, text)

## The network has been quiet for SETTLE_SECONDS. Still held (a drag paused): the draft follows, nothing
## else. Released: points renumber, the moved ones are draped, and the network is refreshed.
func _on_settle() -> void:
	var dragging := Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT)
	for id in _pending.keys():
		var net: Node = _pending[id]
		if not is_instance_valid(net) or not net.is_inside_tree():
			_pending.erase(id)
			continue
		if dragging:
			_request_live_drag(net)
			continue
		_pending.erase(id)
		# Godot's own Delete, a paste or a Scene-dock reorder changes the chain: names follow it.
		net.renumber()
		if _reload_if_changed_on_disk(net):
			continue
		var base = _baseline.get(id)
		if base != null and net.record_text() == base["record"]:
			continue
		if not _suppress_drape:
			_drape_moved(net)
		_refresh(net)
	if dragging and not _pending.is_empty():
		settle_timer.start()
	elif not dragging:
		_suppress_drape = false

## Every point dragged sideways since the last refresh: an AT-GRADE one keeps its height above the natural
## ground at its new place (the road follows the terrain it was moved over), and a junction mouth gets
## `setback_locked` so Auto Setback leaves the stop line the artist placed. One undo step.
func _drape_moved(net: Node) -> int:
	var base = _baseline.get(net.get_instance_id())
	if base == null:
		return 0
	# B10.5: a dragged ROAD node is baked into its points first (and its junctions follow), and the whole
	# move -- bake, partners, drape -- is ONE undo step back to the record as it was before the drag.
	var road_move := false
	for road in net.roads():
		if Gestures.bake_road_transform(road):
			road_move = true
			if move_partners == null or move_partners.button_pressed:
				Gestures.move_junction_partners(net, road, base["pos"])
	var root := get_editor_interface().get_edited_scene_root()
	var terrains := root.find_children("*", "Terrain3D", true, false) if root != null else []
	var terrain: Node = terrains[0] if not terrains.is_empty() else null
	var src := Ground.natural_source(net) if terrain != null else {}
	var to_world: Transform3D = net.global_transform
	var before: Dictionary = {}
	var moved := 0
	var changed := road_move
	if road_move:
		before = JSON.parse_string(base["record"])
	for p in net.all_points():
		var old = base["pos"].get(p.uid)
		if old == null:
			continue
		var xf: Transform3D = p.network_transform()
		var now: Vector3 = xf.origin
		if Vector2(now.x - old.x, now.z - old.z).length() < 0.01:
			continue
		if before.is_empty():
			before = net.to_record()   # after the move, before the drape: the move is the editor's own undo step
		moved += 1
		if p.fields.get("role", "") == "INTERSECTION" and not p.fields.get("setback_locked", false):
			p.fields["setback_locked"] = true
			changed = true
		var ground = base["ground"].get(p.uid)
		if terrain == null or ground == null or absf(now.y - old.y) > 0.01:
			continue
		var offset: float = old.y - float(ground)
		if offset < DRAPE_BAND.x or offset > DRAPE_BAND.y:
			continue
		var world: Vector3 = to_world * now
		var h: float = Ground.natural_height(net, terrain, src, world)
		if is_nan(h):
			continue
		var ground_local: float = (to_world.affine_inverse() * Vector3(world.x, h, world.z)).y
		if absf(xf.origin.y - (ground_local + offset)) > 0.001:
			xf.origin.y = ground_local + offset
			p.set_network_transform(xf)
			changed = true
	if changed:
		var ur := get_undo_redo()
		ur.create_action("Road Kit: Move Road" if road_move else "Road Kit: Drape Moved Points", UndoRedo.MERGE_DISABLE, net)
		ur.add_do_method(net, "from_record", net.to_record())
		ur.add_undo_method(net, "from_record", before)
		ur.commit_action(false)
	return moved

func _set_baseline(net: Node) -> void:
	var pos := {}
	var ground := {}
	for p in net.all_points():
		pos[p.uid] = p.network_transform().origin
		if p.fields.get("has_ground_z", false):
			ground[p.uid] = float(p.fields.get("ground_z", 0.0))
	_baseline[net.get_instance_id()] = {"record": net.record_text(), "pos": pos, "ground": ground}

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
	_update_label(pts[0] if pts.size() == 1 else null)

## A selected point's identity in the viewport, above it: road / chain index / role / uid, and the two
## facts a hand edit changes (tangent mode, a locked setback). An unowned child of the network, never saved.
func _update_label(p: Node) -> void:
	for net in _networks_in(get_editor_interface().get_edited_scene_root()):
		var old = net.get_node_or_null(LABEL_NAME)
		if old != null and (p == null or Gestures.network_of(p) != net):
			net.remove_child(old)
			old.free()
	if p == null:
		return
	var net := Gestures.network_of(p)
	var label: Label3D = net.get_node_or_null(LABEL_NAME)
	if label == null:
		label = Label3D.new()
		label.name = LABEL_NAME
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.no_depth_test = true
		label.fixed_size = true
		label.pixel_size = 0.0012
		label.font_size = 28
		label.outline_size = 8
		label.modulate = Color(1.0, 0.95, 0.7)
		net.add_child(label)
	label.text = label_text(p)
	label.position = p.network_transform().origin + Vector3.UP * 3.0

static func label_text(p: Node) -> String:
	var road: Node = p.get_parent()
	var extra := []
	if p.fields.get("tangent_mode", "AUTO") != "AUTO":
		extra.append(str(p.fields["tangent_mode"]))
	if p.fields.get("setback_locked", false):
		extra.append("setback locked")
	return "%s  #%d  %s\n%s%s" % [road.name, road.points().find(p), p.fields.get("role", ""), p.uid,
			("  " + ", ".join(PackedStringArray(extra))) if not extra.is_empty() else ""]

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
	_make_ramp(pts[0], pts[1])

func _make_ramp(a: Node, b: Node) -> void:
	var net := Gestures.network_of(a)
	if not _save_for_service(net):
		return
	var before: Dictionary = net.to_record()
	var r := Service.run("ramp", net.record_path, [a.uid, b.uid])
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
	if net.record_changed_on_disk():
		_reload_if_changed_on_disk(net)
		return false
	var root := get_editor_interface().get_edited_scene_root()
	if root != null:
		var terrains := root.find_children("*", "Terrain3D", true, false)
		if not terrains.is_empty():
			Gestures.sample_ground(net, terrains[0])
	return net.save_record(_record_path(net)) == OK

## A slow CLI command (Validate, Flow Report: seconds on a real network) on a worker thread; `done` gets
## the answer on the main thread. One at a time -- a second press while one runs is refused.
var _service_thread: Thread

func _service_async(label: String, cmd: String, record: String, done: Callable) -> void:
	if _service_thread != null:
		_say({"ok": false, "message": "%s: still running the previous check" % label})
		return
	status.text = "%s..." % label
	_service_thread = Thread.new()
	_service_thread.start(func():
		var r := Service.run(cmd, record)
		_service_finished.call_deferred(r, done))

func _service_finished(r: Dictionary, done: Callable) -> void:
	if _service_thread != null:
		_service_thread.wait_to_finish()
		_service_thread = null
	done.call(r)

func _on_validate() -> void:
	var net := _network()
	if net == null or not _save_for_service(net):
		return
	_service_async("validating", "validate", net.record_path, _validated.bind(net))

func _validated(r: Dictionary, net: Node) -> void:
	if not is_instance_valid(net):
		return
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
	var msg := "auto setback: %d mouth(s) moved over %d junction(s)" % [r["moved"].size(), r["cliques"]]
	var held: Array = r.get("clamped", [])
	if not held.is_empty():
		msg += "; %d held short of the next station (delete it, or lock the mouth): %s" % [
			held.size(), ", ".join(held.map(func(h): return "%s %.1f of %.1f m" % [h["uid"], h["placed"], h["solved"]]))]
	_say({"ok": true, "message": msg})
	_refresh(net)

func _on_refresh() -> void:
	var net := _network()
	if net != null:
		_refresh(net)

## Save the record (ground re-sampled) and send the network to the solver. The overlay, the draft surface,
## the junction labels and the facings of the points the tool owns arrive from the worker thread
## (`_live_done`) -- the editor never waits for python. `cross`: also re-solve the cross-zone successor
## edges (seconds on a real network, in their own slot).
func _refresh(net: Node, cross: bool = true) -> void:
	_adopt(net)
	# A network with no points has nothing to draw -- and an unloaded one nothing to save.
	if net.record_path == "" or net.all_points().is_empty() or not _save_for_service(net):
		return
	_set_baseline(net)
	_request_live(net, cross, net.record_text())
	var sel := _selected_points()
	_update_label(sel[0] if sel.size() == 1 else null)

# ── B10.8: the solver off the main thread ────────────────────────────────────────────────────────

func _request_live(net: Node, cross: bool, text: String) -> void:
	var id := net.get_instance_id()
	var markers := Zones.markers_in(get_editor_interface().get_edited_scene_root())
	var draft: bool = draft_surface != null and draft_surface.button_pressed
	# B11: once the mouse is up the draft is the FULL mesh Build will write; while it is held, the fast bands.
	var ground := Ground.sidecar_path(str(net.record_path))
	var req := {"id": id, "text": text, "draft": draft,
			"mesh": draft and not Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT),
			"ground": ProjectSettings.globalize_path(ground) if FileAccess.file_exists(ground) else "",
			"zones": Zones.zones_record(net, markers) if not markers.is_empty() else {}}
	_live_sent[id] = text
	_live["fast"]["next"][id] = req.merged({"slot": "fast"})
	if cross and not req["zones"].is_empty():
		_live["cross"]["next"][id] = req.merged({"slot": "cross"})
	_pump_live("fast")
	_pump_live("cross")

func _pump_live(slot_name: String) -> void:
	var slot: Dictionary = _live[slot_name]
	if slot["thread"] != null or slot["next"].is_empty():
		return
	var id = slot["next"].keys()[0]
	var req: Dictionary = slot["next"][id]
	slot["next"].erase(id)
	var t := Thread.new()
	slot["thread"] = t
	t.start(_live_work.bind(req))

## Worker thread: the request's record and zones go to scratch files under user:// (never the network's own
## record), and ONE `roadkit_cli.py live` process answers.
func _live_work(req: Dictionary) -> void:
	var base := "%s/%s_%d" % [LIVE_DIR, req["slot"], req["id"]]
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(LIVE_DIR))
	var f := FileAccess.open(base + ".roads.json", FileAccess.WRITE)
	var r := {"failed": true, "error": "could not write " + base + ".roads.json"}
	if f != null:
		f.store_string(req["text"])
		f.close()
		var args := []
		if not req["zones"].is_empty() and Zones.write_sidecar(base + ".zones.json", req["zones"]) == OK:
			args += ["--zones", ProjectSettings.globalize_path(base + ".zones.json")]
		if req["slot"] == "cross":
			args.append("--cross")
		elif req["draft"]:
			args.append("--draft")
			if req["mesh"]:
				args.append("--mesh")
				if req["ground"] != "":
					args += ["--ground", req["ground"]]
		r = Service.run("live", base + ".roads.json", args)
		if r.has("mesh"):
			r["mesh_arrays"] = OverlayScript.prepare_mesh(r["mesh"])
	_live_done.call_deferred(req, r)

func _live_done(req: Dictionary, r: Dictionary) -> void:
	var slot: Dictionary = _live[req["slot"]]
	if slot["thread"] != null:
		slot["thread"].wait_to_finish()
		slot["thread"] = null
	var net = instance_from_id(req["id"])
	if r.get("failed", false):
		if req["slot"] == "fast":
			_say({"ok": false, "message": "road kit solver: " + str(r.get("error", ""))})
	elif is_instance_valid(net) and net.is_inside_tree():
		_apply_live(net, req, r)
	_pump_live(req["slot"])

func _apply_live(net: Node, req: Dictionary, r: Dictionary) -> void:
	var id: int = req["id"]
	if req["slot"] == "cross":
		_live_cross[id] = {"text": req["text"], "cross": r["centrelines"].get("cross", [])}
		var last = _live_last.get(id)
		if last != null and last["text"] == req["text"]:
			_draw_centrelines(net, last["centrelines"], req["text"])
		return
	_live_last[id] = {"text": req["text"], "centrelines": r["centrelines"]}
	var ov = _draw_centrelines(net, r["centrelines"], req["text"])
	if req["draft"] and r.has("mesh_arrays"):
		ov.full_mesh(r["mesh_arrays"], OverlayScript.materials_from(Preview.find(get_editor_interface().get_edited_scene_root())))
	elif req["draft"] and r.has("bands"):
		ov.draft(r["bands"], OverlayScript.materials_from(Preview.find(get_editor_interface().get_edited_scene_root())))
	else:
		ov.clear_draft()
	ov.junction_labels(net, r.get("junctions", []))
	# Face the points the tool owns -- only once the drag is over, and only if nothing moved since this
	# record was sent (the answer would face them along a chain that is no longer there).
	if not Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT) and net.record_text() == req["text"]:
		Gestures.apply_facings(net, r.get("facings", {}))
	var sel := _selected_points()
	_update_label(sel[0] if sel.size() == 1 else null)

func _draw_centrelines(net: Node, centrelines: Dictionary, text: String) -> Node:
	var ov = net.get_node_or_null("_RoadKitOverlay")
	if ov == null:
		ov = OverlayScript.new()
		ov.name = "_RoadKitOverlay"
		net.add_child(ov)
	var data: Dictionary = centrelines.duplicate()
	var c = _live_cross.get(net.get_instance_id())
	if c != null and c["text"] == text:
		data["cross"] = c["cross"]
	ov.redraw(net, data, Zones.markers_in(get_editor_interface().get_edited_scene_root()))
	return ov

func live_busy() -> bool:
	return _live.values().any(func(slot): return slot["thread"] != null or not slot["next"].is_empty())

## Waits (up to `seconds`) until no solve is running or queued -- for the self-test.
func _live_idle(seconds: float = 30.0) -> void:
	var until := Time.get_ticks_msec() + int(seconds * 1000.0)
	while live_busy() and Time.get_ticks_msec() < until:
		await get_tree().create_timer(0.05).timeout

## The record on disk is not the one this network last read or wrote -- a git checkout, a merge, another
## editor. THE DISK WINS: the network reloads from it (one undo step) rather than writing its own copy over
## the change, which is how a commit made while the editor was open could lose a record's content.
func _reload_if_changed_on_disk(net: Node) -> bool:
	if not net.record_changed_on_disk():
		return false
	var before: Dictionary = net.to_record()
	var warnings: Array = net.load_record()
	var ur := get_undo_redo()
	ur.create_action("Road Kit: Reload Changed Record", UndoRedo.MERGE_DISABLE, net)
	ur.add_do_method(net, "from_record", net.to_record())
	ur.add_undo_method(net, "from_record", before)
	ur.commit_action(false)
	_say({"ok": true, "message": "%s changed on disk -- reloaded it%s" % [net.record_path, "" if warnings.is_empty() else " (" + "; ".join(warnings) + ")"]})
	_refresh(net)
	return true

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
	_service_async("flow report", "flow", net.record_path, _flow_reported)

func _flow_reported(r: Dictionary) -> void:
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
	if root == null or preview_pieces == null:
		return
	# B10.0: every network in the scene is loaded from its record, so its points are in the Scene dock and
	# clickable in the viewport without pressing anything.
	var nets := _networks_in(root)
	var ur := get_undo_redo()
	var hid := ur.get_object_history_id(root)
	_history_count[hid] = ur.get_history_undo_redo(hid).get_history_count()
	for net in nets:
		_adopt(net)
	if preview_pieces.button_pressed and (not Zones.markers_in(root).is_empty() or not nets.is_empty()) and Preview.find(root) == null:
		_on_preview_pieces(true)
	for net in nets:
		if not _baseline.has(net.get_instance_id()):
			_refresh(net)

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

func _on_build(dirty_only: bool = true) -> void:
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
		var r := Service.build_piece(record, piece, zones_path, ground_path, dirty_only)
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
	var rebuilt: Array = r.get("dirty", [])
	var msg := ("built %s -- %s" % [piece, ("rebuilt " + ", ".join(PackedStringArray(rebuilt))) if not rebuilt.is_empty() else "nothing changed, no piece rebuilt"]
			if r["ok"] else "build FAILED") + wired
	# B10.6: the terrain carries the roads as they were last STAMPED; a rebuilt road wants a re-stamp.
	if r["ok"] and not rebuilt.is_empty() and is_instance_valid(net) and FileAccess.file_exists(Ground.stamp_record_path(str(net.record_path))):
		notes.append("the terrain was stamped from the previous roads -- press Stamp Terrain")
	for n in notes:
		msg += "\n• " + str(n)
	_say({"ok": r["ok"], "message": msg + "\n" + tail})
	get_editor_interface().get_resource_filesystem().scan()
	if r["ok"] and preview_pieces.button_pressed:
		_on_preview_pieces(true, true)

func _selftest(scene_path: String) -> void:
	for i in 30:
		await get_tree().process_frame
	# The self-test edits and SAVES the real scene and record: both are backed up first and put back
	# byte for byte, whatever happens.
	var scene_abs := ProjectSettings.globalize_path(scene_path)
	var m := RegEx.create_from_string('record_path = "([^"]+)"').search(FileAccess.get_file_as_string(scene_path))
	var record_res := m.get_string(1) if m != null else ""
	var backups := {scene_path: FileAccess.get_file_as_bytes(scene_path)}
	if record_res != "":
		backups[record_res] = FileAccess.get_file_as_bytes(record_res)
	var ok: bool = await _selftest_run(scene_path, record_res, backups)
	for path in backups:
		var f := FileAccess.open(path, FileAccess.WRITE)
		f.store_buffer(backups[path])
		f.close()
	print("[selftest] RESULT ", "PASS" if ok else "FAIL")
	get_tree().quit(0 if ok else 1)

func _check(ok: bool, what: String) -> bool:
	print("[selftest] %s %s" % ["ok  " if ok else "FAIL", what])
	return ok

func _selftest_run(scene_path: String, record_res: String, backups: Dictionary) -> bool:
	get_editor_interface().open_scene_from_path(scene_path)
	for i in 30:
		await get_tree().process_frame
	var root := get_editor_interface().get_edited_scene_root()
	print("[selftest] scene root: ", root)
	var markers := Zones.markers_in(root)
	print("[selftest] markers: ", markers.size())
	for mk in markers:
		var z = mk.get("zone")
		print("[selftest]   ", mk.name, " zone=", z, " path=", z.get("geometry_path") if z != null else "-", " placed=", z.get("geometry_world_placed") if z != null else "-")
	var net := _network()
	var rec_points := 0
	if record_res != "":
		var rec = JSON.parse_string(backups[record_res].get_string_from_utf8())
		rec_points = (rec.get("points", []) as Array).size() if typeof(rec) == TYPE_DICTIONARY else 0
	print("[selftest] network: ", net, " points: ", net.all_points().size() if net != null else -1, " (record: %d)" % rec_points)
	var ok := true
	# B10.0: the points are there without pressing anything, owned (Scene dock, viewport picking), and
	# opening neither dirtied the scene nor rewrote the record.
	ok = _check(net != null and not net.needs_load and net.all_points().size() == rec_points and rec_points > 0, "points loaded on open") and ok
	if net == null:
		return false
	ok = _check(net.all_points().all(func(p): return p.owner == root), "every point owned by the scene root") and ok
	var ur := get_undo_redo()
	var hid := ur.get_object_history_id(root)
	ok = _check(not ur.get_history_undo_redo(hid).has_undo(), "opening did not mark the scene modified") and ok
	ok = _check(FileAccess.get_file_as_bytes(record_res) == backups[record_res], "record intact after open (byte for byte)") and ok
	var holder: Node3D = Preview.find(root)
	print("[selftest] preview shown on open: ", holder != null, " (", holder.get_child_count() if holder != null else 0, " piece(s))")
	if holder == null:
		return false
	for c in holder.get_children():
		var meshes := c.find_children("*", "MeshInstance3D", true, false)
		var aabb := AABB()
		for mi in meshes:
			aabb = aabb.merge(mi.global_transform * mi.get_aabb())
		print("[selftest]   ", c.name, " visible=", c.is_visible_in_tree(), " meshes=", meshes.size(), " aabb=", aabb)
	# The at-grade junction mouth and sideways move that cross the most natural ground -- a drape that did
	# nothing would pass on flat ground.
	var terrains := root.find_children("*", "Terrain3D", true, false)
	var src := Ground.natural_source(net) if not terrains.is_empty() else {}
	var mouth: Node3D = null
	var step := Vector3(12.0, 0.0, 9.0)
	var best := -1.0
	for p in net.all_points():
		if p.fields.get("role", "") != "INTERSECTION" or not p.fields.get("has_ground_z", false) \
				or absf(p.network_transform().origin.y - float(p.fields["ground_z"])) > 1.0:
			continue
		if mouth == null:
			mouth = p
		if terrains.is_empty():
			break
		var h0: float = Ground.natural_height(net, terrains[0], src, p.global_position)
		for c in [Vector3(12, 0, 9), Vector3(-12, 0, -9), Vector3(12, 0, -9), Vector3(-12, 0, 9), Vector3(15, 0, 0), Vector3(-15, 0, 0), Vector3(0, 0, 15), Vector3(0, 0, -15)]:
			var hc: float = Ground.natural_height(net, terrains[0], src, p.global_position + c)
			if not is_nan(hc) and absf(hc - h0) > best:
				best = absf(hc - h0)
				mouth = p
				step = c
	print("[selftest] editing %s, move %s crosses %.3f m of ground" % [mouth.name if mouth != null else "-", step, best])
	ok = _check(mouth != null and (terrains.is_empty() or best > 0.2), "an at-grade junction mouth to edit, over sloping ground") and ok
	if mouth == null:
		return false
	ok = await _selftest_pick(mouth) and ok
	# Move the mouth sideways and set one of its own fields, as the stock gizmo and the inspector do.
	var old_xf: Transform3D = mouth.network_transform()
	var offset: float = old_xf.origin.y - float(mouth.fields["ground_z"])
	var count0 := ur.get_history_undo_redo(hid).get_history_count()
	var ov_before = net.get_node_or_null("_RoadKitOverlay")
	var lines_before: Mesh = ov_before.mesh if ov_before != null else null
	ur.create_action("selftest: move a mouth")
	ur.add_do_property(mouth, "position", mouth.position + step)
	ur.add_undo_property(mouth, "position", mouth.position)
	ur.commit_action()
	await get_tree().create_timer(SETTLE_SECONDS * 4).timeout
	await _live_idle()
	var now: Vector3 = mouth.network_transform().origin
	if not terrains.is_empty():
		var world: Vector3 = net.global_transform * now
		var h: float = Ground.natural_height(net, terrains[0], Ground.natural_source(net), world)
		var want: float = (net.global_transform.affine_inverse() * Vector3(world.x, h, world.z)).y + offset
		ok = _check(absf(now.y - want) < 0.01, "moved mouth draped onto the ground (y %.3f, want %.3f, was %.3f)" % [now.y, want, old_xf.origin.y]) and ok
	ok = _check(mouth.fields.get("setback_locked", false), "a hand-moved junction mouth gets setback_locked") and ok
	var draft = net.get_node_or_null("_RoadKitOverlay/" + OverlayScript.DRAFT_NAME)
	var ov_after = net.get_node_or_null("_RoadKitOverlay")
	# B10.2: nothing was pressed -- the move alone redrew the centrelines and the draft.
	ok = _check(draft != null and ov_after != null and lines_before != null and ov_after.mesh != lines_before,
			"the move alone redrew the overlay (no button pressed)") and ok
	ur.create_action("selftest: fillet")
	ur.add_do_property(mouth, "rk_fillet_radius", 9.5)
	ur.add_undo_property(mouth, "rk_fillet_radius", mouth.get("rk_fillet_radius"))
	ur.commit_action()
	await get_tree().create_timer(SETTLE_SECONDS * 4).timeout
	var err := get_editor_interface().save_scene()
	for i in 5:
		await get_tree().process_frame
	ok = _check(err == OK, "scene saved (%s)" % error_string(err)) and ok
	var saved := FileAccess.get_file_as_string(scene_path)
	ok = _check(not saved.contains("road_kit_point.gd") and not saved.contains("road_kit_road.gd"), "the saved scene holds no roads or points (the record is the only copy)") and ok
	ok = _check(net.all_points().all(func(p): return p.owner == root), "owners restored after the save") and ok
	ok = _check(_record_diff(backups[record_res].get_string_from_utf8(), FileAccess.get_file_as_string(record_res), mouth.uid), "the save rewrote the record with exactly the mouth's changes") and ok
	# Undo all three: nothing is draped on the way back, so no action is committed and redo survives.
	var h_ur := ur.get_history_undo_redo(hid)
	var count1 := h_ur.get_history_count()
	for i in count1 - count0:
		# Ctrl+Z as the artist presses it: the editor's own undo, which is what emits `version_changed`.
		var z := InputEventKey.new()
		z.keycode = KEY_Z
		z.physical_keycode = KEY_Z
		z.ctrl_pressed = true
		z.pressed = true
		get_editor_interface().get_base_control().get_viewport().push_input(z)
		await get_tree().create_timer(SETTLE_SECONDS * 3).timeout
	ok = _check(h_ur.get_history_count() == count1, "undo commits nothing (history %d -> %d)" % [count1, h_ur.get_history_count()]) and ok
	ok = _check(mouth.network_transform().origin.distance_to(old_xf.origin) < 0.001 and not mouth.fields.get("setback_locked", false),
			"undo puts the mouth back (%.4f m)" % mouth.network_transform().origin.distance_to(old_xf.origin)) and ok
	ok = _check(h_ur.has_redo(), "redo history survives") and ok
	ok = await _selftest_rotate_handle(mouth, net) and ok
	ok = await _selftest_tool_insert(net) and ok
	ok = await _selftest_move_road(net) and ok
	ok = await _selftest_live_cost(net) and ok
	ok = await _selftest_select_click(net) and ok
	ok = await _selftest_native_delete(net) and ok
	ok = await _selftest_disk_change(net) and ok
	# B10.1: the draft surface wears the kit's materials, taken off the preview's base meshes.
	if draft_surface.button_pressed:
		_refresh(net)
		await _live_idle()
		ok = _check(net.get_node("_RoadKitOverlay").get_children().filter(func(c): return String(c.name).begins_with(OverlayScript.JCT_LABEL)).size() == 2,
				"a label floats over each of the network's 2 junctions") and ok
		draft = net.get_node_or_null("_RoadKitOverlay/" + OverlayScript.DRAFT_NAME)
		var mats := []
		if draft != null:
			for si in draft.mesh.get_surface_count():
				var mat: Material = draft.mesh.surface_get_material(si)
				mats.append(mat.resource_name if mat != null else "<default>")
		print("[selftest] draft surface: ", draft != null, " materials ", mats)
		ok = _check(draft != null and not mats.has("<default>"), "draft surface wears the kit's materials") and ok
		# B11: with the mouse up the draft is the FULL mesh Build writes -- kerbs and barriers too, not the bands.
		var tris := 0
		if draft != null:
			for si in draft.mesh.get_surface_count():
				tris += draft.mesh.surface_get_array_len(si) / 3
		ok = _check(mats.has("M_Barrier") and mats.has("M_Concrete") and tris > 10000,
				"after a release the draft is the full mesh Build writes (%d tris, %s)" % [tris, mats]) and ok
	return ok

## B10.4 in the real editor: drag the junction's ROTATE handle through the gizmo plugin with the viewport's
## own camera, commit, and undo it with Ctrl+Z.
func _selftest_rotate_handle(mouth: Node3D, net: Node) -> bool:
	var giz: EditorNode3DGizmo = null
	for g in mouth.get_gizmos():
		if g is EditorNode3DGizmo and g.get_plugin() == gizmo:
			giz = g
	if not _check(giz != null, "the mouth carries the Road Kit gizmo"):
		return false
	var members: Array = Gestures.junction_members(mouth)
	var before: Dictionary = net.to_record()
	var starts := {}
	for m in members:
		starts[m.uid] = m.global_position
	var cam := get_editor_interface().get_editor_viewport_3d(0).get_camera_3d()
	var id := 7   # road_kit_handles.gd HANDLE_JCT_ROTATE
	var restore = gizmo._get_handle_value(giz, id, false)
	gizmo._begin_handle_action(giz, id, false)
	var centre := Vector3.ZERO
	for m in members:
		centre += m.global_position
	centre /= members.size()
	var target: Vector3 = centre + Basis(Vector3.UP, deg_to_rad(30.0)) * Vector3(10.0, 0.0, 0.0)
	gizmo._set_handle(giz, id, false, cam, cam.unproject_position(target))
	var moved := 0
	for m in members:
		moved += 1 if m.global_position.distance_to(starts[m.uid]) > 0.5 else 0
	var ur := get_undo_redo()
	var hid := ur.get_object_history_id(net)
	gizmo._commit_handle(giz, id, false, restore, false)
	# The redo history left by the undo checks is truncated by this commit, so the action is identified by
	# name, not by a count.
	var action := ur.get_history_undo_redo(hid).get_current_action_name()
	var ok := _check(moved == members.size() and action == "Road Kit: rotate junction",
			"a ROTATE handle drag turns all %d mouths and commits one undo step (%d moved, action '%s')" % [members.size(), moved, action])
	await get_tree().create_timer(SETTLE_SECONDS * 4).timeout
	for i in 3:
		if net.to_record() == before:
			break
		var z := InputEventKey.new()
		z.keycode = KEY_Z
		z.physical_keycode = KEY_Z
		z.ctrl_pressed = true
		z.pressed = true
		get_editor_interface().get_base_control().get_viewport().push_input(z)
		await get_tree().create_timer(SETTLE_SECONDS * 3).timeout
	return _check(net.to_record() == before, "Ctrl+Z puts the crossing back") and ok

## B10.5 in the real editor: drag a whole ROAD node (the editor's own Move action on it). On release its
## transform is baked into its points, the other roads' mouths at its junctions follow, and it is ONE undo
## step that Ctrl+Z takes back to the record as it was.
func _selftest_move_road(net: Node3D) -> bool:
	var road: Node3D = null
	for r in net.roads():
		if r.points().any(func(p): return Gestures.is_mouth(p)):
			road = r
			break
	if not _check(road != null, "a road with a junction to move"):
		return false
	var before: Dictionary = net.to_record()
	var starts := {}
	for p in net.all_points():
		starts[p.uid] = p.network_transform().origin
	var partners := []
	for m in road.points():
		if Gestures.is_mouth(m):
			partners.append_array(Gestures.junction_members(m).filter(func(q): return q.get_parent() != road))
	var delta := Vector3(6.0, 0.0, 4.0)
	var ur := get_undo_redo()
	ur.create_action("selftest: move a road")
	ur.add_do_property(road, "position", road.position + delta)
	ur.add_undo_property(road, "position", road.position)
	ur.commit_action()
	await get_tree().create_timer(SETTLE_SECONDS * 4).timeout
	var own_ok: bool = road.points().all(func(p): return Vector2(p.network_transform().origin.x - starts[p.uid].x - delta.x, p.network_transform().origin.z - starts[p.uid].z - delta.z).length() < 0.05)
	var partners_ok: bool = not partners.is_empty() and partners.all(func(q): return Vector2(q.network_transform().origin.x - starts[q.uid].x, q.network_transform().origin.z - starts[q.uid].z).length() > 1.0)
	var action := ur.get_history_undo_redo(ur.get_object_history_id(net)).get_current_action_name()
	var ok := _check(road.transform.is_equal_approx(Transform3D.IDENTITY) and own_ok and partners_ok and action == "Road Kit: Move Road",
			"dragging road %s bakes into its points, moves its %d junction partner(s), one '%s' step" % [road.name, partners.size(), action])
	for i in 4:
		if net.to_record() == before:
			break
		var z := InputEventKey.new()
		z.keycode = KEY_Z
		z.physical_keycode = KEY_Z
		z.ctrl_pressed = true
		z.pressed = true
		get_editor_interface().get_base_control().get_viewport().push_input(z)
		await get_tree().create_timer(SETTLE_SECONDS * 3).timeout
	return _check(net.to_record() == before, "Ctrl+Z puts the road and its junctions back") and ok

## B10.3 in the real editor: a left click in INSERT mode, delivered through `_forward_3d_gui_input`, adds
## a station on the clicked centreline as one undo step, and Ctrl+Z takes it away.
func _selftest_tool_insert(net: Node3D) -> bool:
	await _live_idle()
	var cam := get_editor_interface().get_editor_viewport_3d(0).get_camera_3d()
	var target = _centreline_on_screen(net, cam)
	if not _check(target != null, "a centreline on screen to click"):
		return false
	var before: Dictionary = net.to_record()
	var n0: int = net.all_points().size()
	_set_tool_mode(Tool.Mode.INSERT)
	var ev := InputEventMouseButton.new()
	ev.button_index = MOUSE_BUTTON_LEFT
	ev.pressed = true
	ev.position = cam.unproject_position(target)
	var ret := _forward_3d_gui_input(cam, ev)
	_set_tool_mode(Tool.Mode.OFF)
	var ur := get_undo_redo()
	var action := ur.get_history_undo_redo(ur.get_object_history_id(net)).get_current_action_name()
	var ok := _check(ret == EditorPlugin.AFTER_GUI_INPUT_STOP and net.all_points().size() == n0 + 1 and action == "Road Kit: Insert",
			"an INSERT click through _forward_3d_gui_input adds a station as one undo step (%d -> %d, '%s')" % [n0, net.all_points().size(), action])
	await get_tree().create_timer(SETTLE_SECONDS * 4).timeout
	for i in 3:
		if net.to_record() == before:
			break
		var z := InputEventKey.new()
		z.keycode = KEY_Z
		z.physical_keycode = KEY_Z
		z.ctrl_pressed = true
		z.pressed = true
		get_editor_interface().get_base_control().get_viewport().push_input(z)
		await get_tree().create_timer(SETTLE_SECONDS * 3).timeout
	return _check(net.to_record() == before, "Ctrl+Z removes the inserted station") and ok

## A point on a drawn centreline that is on screen and 40 px clear of every station (a click there is a
## centreline click, not a pick), in world space; null if there is none.
func _centreline_on_screen(net: Node3D, cam: Camera3D):
	var ov = net.get_node_or_null("_RoadKitOverlay")
	var screen := Rect2(Vector2.ZERO, cam.get_viewport().get_visible_rect().size).grow(-40.0)
	var stations: Array = net.all_points().filter(func(p): return not cam.is_position_behind(p.global_position)) \
			.map(func(p): return cam.unproject_position(p.global_position))
	# Along each segment's visible part, not only at its samples: a camera framed a few metres from a mouth
	# sees one or two 4 m samples at most, and the stretch between them is what is under the cursor.
	for run in (ov.runs_drawn if ov != null else []):
		var pts: Array = run["points"]
		for i in pts.size() - 1:
			var wa: Vector3 = net.global_transform * Vector3(pts[i][0], pts[i][1], pts[i][2])
			var wb: Vector3 = net.global_transform * Vector3(pts[i + 1][0], pts[i + 1][1], pts[i + 1][2])
			var vis: Array = Tool.visible_part(cam, wa, wb)
			if vis.is_empty():
				continue
			for k in 9:
				var w := wa.lerp(wb, lerpf(vis[0], vis[1], (k + 0.5) / 9.0))
				var sp := cam.unproject_position(w)
				if screen.has_point(sp) and stations.all(func(st): return st.distance_to(sp) > 40.0):
					return w
	return null

## B10.8: what a drag costs the EDITOR per live tick -- serialising the record and sending it to the worker.
## The solve itself is off the main thread; this is the part the artist can feel.
const LIVE_TICK_BUDGET_MS := 8.0

func _selftest_live_cost(net: Node3D) -> bool:
	await _live_idle()
	var n := 20
	var t0 := Time.get_ticks_usec()
	for i in n:
		_request_live(net, false, net.record_text())
	var per_ms := float(Time.get_ticks_usec() - t0) / 1000.0 / n
	var t1 := Time.get_ticks_msec()
	await _live_idle()
	var solve_ms := Time.get_ticks_msec() - t1
	return _check(per_ms < LIVE_TICK_BUDGET_MS,
			"a live tick costs the editor %.2f ms of main thread (budget %.0f); the queued solves drained in %d ms off it" % [per_ms, LIVE_TICK_BUDGET_MS, solve_ms])

## B10.8: in SELECT mode the viewport tool never takes a PRESS (it may start a gizmo drag), and a click --
## press and release in one place -- on a centreline selects that road.
func _selftest_select_click(net: Node3D) -> bool:
	await _live_idle()
	var cam := get_editor_interface().get_editor_viewport_3d(0).get_camera_3d()
	var target = _centreline_on_screen(net, cam)
	if not _check(target != null, "a centreline on screen for a SELECT click"):
		return false
	get_editor_interface().get_selection().clear()
	_set_tool_mode(Tool.Mode.SELECT)
	var rets := []
	for pressed in [true, false]:
		var ev := InputEventMouseButton.new()
		ev.button_index = MOUSE_BUTTON_LEFT
		ev.pressed = pressed
		ev.position = cam.unproject_position(target)
		rets.append(_forward_3d_gui_input(cam, ev))
	for i in 3:
		await get_tree().process_frame
	_set_tool_mode(Tool.Mode.OFF)
	var sel := get_editor_interface().get_selection().get_selected_nodes()
	get_editor_interface().get_selection().clear()
	return _check(rets.all(func(r): return r == EditorPlugin.AFTER_GUI_INPUT_PASS) and sel.size() == 1 and sel[0].get_script() == Gestures.RoadScript,
			"SELECT passes the press and the release to the editor, and the click selects the road (%s)" % [sel])

## GODOT'S OWN DELETE, as the Scene dock performs it (`SceneTreeDock::_delete_confirm`: remove_child, and an
## undo that adds the node back, re-orders it and restores its owner). The record loses the station and
## joins its neighbours, names renumber, and Ctrl+Z brings back the record exactly.
func _selftest_native_delete(net: Node3D) -> bool:
	await _live_idle()
	var road: Node = null
	for r in net.roads():
		if r.points().size() >= 4:
			road = r
			break
	if not _check(road != null, "a road with an interior station to delete"):
		return false
	var root := get_editor_interface().get_edited_scene_root()
	var victim: Node = road.points()[2]
	var prev_uid: String = road.points()[1].uid
	var next_uid: String = road.points()[3].uid
	var idx := victim.get_index()
	var name0 := String(victim.name)
	var before: Dictionary = net.to_record()
	var ur := get_undo_redo()
	ur.create_action("Remove Node(s)", UndoRedo.MERGE_DISABLE, victim)
	ur.add_do_method(road, "remove_child", victim)
	ur.add_undo_method(road, "add_child", victim, true)
	ur.add_undo_method(road, "move_child", victim, idx)
	ur.add_undo_property(victim, "owner", root)
	ur.add_undo_reference(victim)
	ur.commit_action()
	await get_tree().create_timer(SETTLE_SECONDS * 4).timeout
	await _live_idle()
	var rec = JSON.parse_string(FileAccess.get_file_as_string(net.record_path))
	var named := 0
	var joined := false
	for pd in rec["points"]:
		for l in pd["links"]:
			named += 1 if l["target"] == victim.uid else 0
			if pd["uid"] == prev_uid and l["target"] == next_uid and l["type"] == "SEGMENT":
				joined = true
	var ok := _check(named == 0 and joined and String(road.points()[2].name).begins_with("%s_p002" % road.name),
			"Delete in the Scene dock: the saved record names the station nowhere, joins its neighbours, and names renumber (%d link(s) left, joined %s, now %s)" % [named, joined, road.points()[2].name])
	var z := InputEventKey.new()
	z.keycode = KEY_Z
	z.physical_keycode = KEY_Z
	z.ctrl_pressed = true
	z.pressed = true
	get_editor_interface().get_base_control().get_viewport().push_input(z)
	await get_tree().create_timer(SETTLE_SECONDS * 4).timeout
	await _live_idle()
	return _check(net.to_record() == before and victim.get_parent() == road and String(victim.name) == name0 and victim.owner == root,
			"Ctrl+Z puts the station back: record identical, name %s, owned" % victim.name) and ok

## A record changed on disk behind the editor's back (a git checkout) is RELOADED, never written over.
func _selftest_disk_change(net: Node3D) -> bool:
	await _live_idle()
	var path: String = net.record_path
	var original := FileAccess.get_file_as_string(path)
	var d = JSON.parse_string(original)
	var p0: Dictionary = d["points"][0]
	p0["pos"][0] = float(p0["pos"][0]) + 5.0
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_string(JSON.stringify(d, " ", true) + "\n")
	f.close()
	var pt: Node3D = net.find_point(str(p0["uid"]))
	var x0: float = pt.network_transform().origin.x
	var saved := _save_for_service(net)
	var ok := _check(not saved and absf(pt.network_transform().origin.x - x0 - 5.0) < 0.01 and FileAccess.get_file_as_string(path) != original,
			"a record changed on disk is reloaded, not saved over (moved %.2f m)" % (pt.network_transform().origin.x - x0))
	f = FileAccess.open(path, FileAccess.WRITE)
	f.store_string(original)
	f.close()
	saved = _save_for_service(net)
	await _live_idle()
	return _check(not saved and absf(pt.network_transform().origin.x - x0) < 0.01, "and changed back, reloaded back") and ok

## Picking: frame the point in the 3D viewport, then click where it is on screen with nothing selected --
## the gizmo's collision segments must make that select it.
func _selftest_pick(p: Node3D) -> bool:
	get_editor_interface().set_main_screen_editor("3D")
	for i in 10:
		await get_tree().process_frame
	var sub := get_editor_interface().get_editor_viewport_3d(0)
	var vp_ctl: Control = sub.get_parent().get_parent() if sub != null else null
	var surface: Control = null
	if vp_ctl != null:
		for c in vp_ctl.get_children():
			if c is Control and not (c is SubViewportContainer) and not c.get_signal_connection_list("gui_input").is_empty():
				surface = c
				break
	if not _check(surface != null, "found the 3D viewport's input surface"):
		return false
	var sel := get_editor_interface().get_selection()
	sel.clear()
	sel.add_node(p)
	await get_tree().process_frame
	var key := InputEventKey.new()
	key.keycode = KEY_F
	key.physical_keycode = KEY_F
	key.pressed = true
	surface.gui_input.emit(key)
	for i in 90:
		await get_tree().process_frame
	var cam := sub.get_camera_3d()
	var world := p.global_position
	if cam.is_position_behind(world):
		return _check(false, "point in front of the framed camera")
	var at := cam.unproject_position(world) * (surface.size / Vector2(sub.size))
	print("[selftest] pick: camera ", cam.global_position, " point ", world, " screen ", at, " surface ", surface.size, " sub ", sub.size)
	sel.clear()
	await get_tree().process_frame
	for pressed in [true, false]:
		var mb := InputEventMouseButton.new()
		mb.button_index = MOUSE_BUTTON_LEFT
		mb.pressed = pressed
		mb.position = at
		mb.global_position = at
		surface.gui_input.emit(mb)
		await get_tree().process_frame
	for i in 5:
		await get_tree().process_frame
	var picked := sel.get_selected_nodes()
	return _check(picked.size() == 1 and picked[0] == p, "a click on the point selects it (got %s)" % [picked])

## Every point except `uid` identical in both records, and `uid` differing only in what the edit changes.
func _record_diff(before_text: String, after_text: String, uid: String) -> bool:
	var a = JSON.parse_string(before_text)
	var b = JSON.parse_string(after_text)
	if typeof(a) != TYPE_DICTIONARY or typeof(b) != TYPE_DICTIONARY:
		return false
	var index := func(d: Dictionary) -> Dictionary:
		var out := {}
		for pd in d["points"]:
			out[pd["uid"]] = pd
		return out
	var ia: Dictionary = index.call(a)
	var ib: Dictionary = index.call(b)
	var allowed := ["pos", "ground_z", "setback_locked", "fillet_radius"]
	var changed := []
	for k in ia:
		if not ib.has(k):
			print("[selftest]   missing point ", k)
			return false
		if k == uid:
			for key in ia[k].keys() + ib[k].keys():
				if ia[k].get(key) != ib[k].get(key) and not changed.has(key):
					changed.append(key)
		elif ia[k] != ib[k]:
			print("[selftest]   unexpected change on ", k, ": ", ia[k], " -> ", ib[k])
			return false
	print("[selftest]   mouth fields changed: ", changed, "; roads equal: ", a["roads"] == b["roads"])
	return a["roads"] == b["roads"] and changed.all(func(c): return allowed.has(c)) \
			and changed.has("pos") and changed.has("setback_locked") and changed.has("fillet_radius")
