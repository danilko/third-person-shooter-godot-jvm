extends SceneTree
## Key REBINDING and the rest of F2's settings (PLAN.md 1.3 rest, 2026-10-10: control.BindingTable / KeyBindings,
## ui.KeyBindingsMenu, QualitySettings fov_offset / [display] / [bindings]).
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_rebind.gd
##
## A real Player with the real HUD (WorldSystems.tscn):
##  1. the PAGE: Settings -> Key bindings -> press "Use"'s button -> press Y (a real key event): interact is Y, E is
##     gone from it, its pad events are kept;
##  2. a SWAP: Use -> R (Reload's key): Reload now has Y;
##  3. a SHARED row: forward -> Up arrow moves forward, throttle AND the movement action, and movement keeps six keys;
##  4. the HUD prompt follows: a "Door (E)" prompt shows the key bound now (control: before any rebind it shows E);
##  5. settings.cfg round trip: save, reset to defaults, reload -> the bindings come back from the file;
##  6. the FOV offset: +10 deg moves the camera's FOV by +10 (on foot).
## The user's own settings.cfg is backed up first and put back at the end (and the bindings reset).

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const SYSTEMS := "res://src/main/resources/com/openworld/world/WorldSystems.tscn"
const CFG := "user://settings.cfg"
const KEY_Y := 89      # a free key (T is the flashlight since PLAN.md 3.2)
const KEY_R := 82
const KEY_UP := 4194320

var fails := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _find(n: Node, nm: String) -> Node:
	if n.name == nm:
		return n
	for c in n.get_children():
		var r: Node = _find(c, nm)
		if r != null:
			return r
	return null

func _keys(action: String) -> Array:
	var out := []
	for e in InputMap.action_get_events(action):
		if e is InputEventKey:
			out.append(int(e.physical_keycode))
		elif e is InputEventMouseButton:
			out.append("mouse%d" % e.button_index)
	return out

func _pads(action: String) -> int:
	var n := 0
	for e in InputMap.action_get_events(action):
		if e is InputEventJoypadButton or e is InputEventJoypadMotion:
			n += 1
	return n

## an action's pad events: "pad:<button>" / "axis:<axis>"
func _padspec(action: String) -> Array:
	var out := []
	for e in InputMap.action_get_events(action):
		if e is InputEventJoypadButton:
			out.append("pad:%d" % e.button_index)
		elif e is InputEventJoypadMotion:
			out.append("axis:%d" % e.axis)
	return out

func _padbutton(index: int) -> void:
	for pressed in [true, false]:
		var ev := InputEventJoypadButton.new()
		ev.button_index = index
		ev.pressed = pressed
		Input.parse_input_event(ev)
		await process_frame

func _key(code: int) -> void:
	for pressed in [true, false]:
		var ev := InputEventKey.new()
		ev.physical_keycode = code
		ev.keycode = code
		ev.pressed = pressed
		Input.parse_input_event(ev)
		await process_frame

## a click: the button takes focus on the press, "pressed" fires on the release
func _click(b: Button) -> void:
	b.grab_focus()
	b.emit_signal("pressed")

func _prompt_text(hud: Node) -> String:
	var l := _find(hud, "InteractPrompt") as Label
	if l == null:
		l = _find(hud, "InteractPromptLabel") as Label
	return l.text if l != null else "?"

func _initialize() -> void:
	var backup := FileAccess.get_file_as_string(CFG) if FileAccess.file_exists(CFG) else ""
	var qs: Node = root.get_node("QualitySettings")
	qs.call("reset_bindings_now")
	var world := Node3D.new()
	root.add_child(world)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(100, 2, 100)
	cs.shape = sh
	floor.add_child(cs)
	world.add_child(floor)
	floor.position = Vector3(0, -1, 0)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(0, 1.0, 0)
	var sys: Node = (load(SYSTEMS) as PackedScene).instantiate()
	world.add_child(sys)
	await _tick(60)
	var hud: Node = _find(sys, "FootHUD")
	var bus: Node = root.get_node("EventBus")
	var door := Node3D.new()
	world.add_child(door)

	print("=== 4 (control). the prompt before any rebind ===")
	bus.emit_signal("interact_prompt_changed", door, true, "Door (E)")
	await _tick(3)
	var before: String = hud.call("prompt_key_now") if hud != null else "?"
	_check("control: a Door (E) prompt shows E with the default keys", before == "E", "key '%s'" % before)

	print("=== 1. the page ===")
	var layer := CanvasLayer.new()
	root.add_child(layer)
	var holder := Control.new()
	layer.add_child(holder)
	var settings: Node = load("res://src/main/java/com/openworld/ui/SettingsMenu.java").new()
	settings.name = "SettingsMenu"
	holder.add_child(settings)
	await _tick(3)
	_check("the title's settings have CONTROLS / DISPLAY / GAME", String(settings.call("tabs_now")) == "CONTROLS,DISPLAY,GAME",
		String(settings.call("tabs_now")))
	settings.call("select_tab_now", "CONTROLS")
	await _tick(3)
	var page := settings
	_check("CONTROLS lists the keyboard rows AND the controller rows", _find(page, "key_interact") is Button and _find(page, "pad_jump") is Button)
	var pads_before := _pads("interact")
	_click(_find(page, "key_interact") as Button)
	await _tick(2)
	_check("pressing Use's button waits for a key", String(page.call("capturing_now")) == "key_interact")
	await _key(KEY_Y)
	await _tick(2)
	_check("Y is now Use: interact = [Y], E gone", _keys("interact") == [KEY_Y], str(_keys("interact")))
	_check("... its pad events are kept", _pads("interact") == pads_before and pads_before > 0,
		"%d -> %d" % [pads_before, _pads("interact")])
	_check("... the button shows it", (_find(page, "key_interact") as Button).text == "Y", (_find(page, "key_interact") as Button).text)

	print("=== 4. the HUD prompt follows ===")
	bus.emit_signal("interact_prompt_changed", door, false, "")
	bus.emit_signal("interact_prompt_changed", door, true, "Door (E)")
	await _tick(3)
	var shown := String(hud.call("prompt_key_now"))
	var text := _prompt_text(hud)
	_check("the Door prompt now names Y", shown == "Y" or text.contains("[ Y ]"), "key '%s', text '%s'" % [shown, text])

	print("=== 2. a swap ===")
	_click(_find(page, "key_interact") as Button)
	await _tick(2)
	await _key(KEY_R)
	await _tick(2)
	_check("Use -> R takes Reload's key", _keys("interact") == [KEY_R], str(_keys("interact")))
	_check("... and Reload gets Y (swapped, not double-bound)", _keys("reload") == [KEY_Y], str(_keys("reload")))

	print("=== 3. a shared row ===")
	var moves_before := _keys("movement").size()
	qs.call("rebind_now", "forward", "key:%d" % KEY_UP)
	_check("forward -> Up", _keys("forward") == [KEY_UP], str(_keys("forward")))
	_check("... the car's throttle moved with it", _keys("throttle") == [KEY_UP], str(_keys("throttle")))
	var mv := _keys("movement")
	_check("... movement has Up, no W, still %d keys" % moves_before, mv.has(KEY_UP) and not mv.has(87) and mv.size() == moves_before, str(mv))
	qs.call("rebind_now", "forward", "key:83")   # S: Move back's key -> a swap inside the shared action
	mv = _keys("movement")
	_check("a swap inside the shared action loses no key", mv.size() == moves_before and mv.has(83) and mv.has(KEY_UP), str(mv))

	print("=== 7. the controller ===")
	_check("control: jump is A, reload is X, forward is the stick only", _padspec("jump") == ["pad:0"] and _padspec("reload") == ["pad:2"]
		and _padspec("forward") == ["axis:1"], "%s %s %s" % [_padspec("jump"), _padspec("reload"), _padspec("forward")])
	_check("... the button shows A", (_find(page, "pad_jump") as Button).text == "A", (_find(page, "pad_jump") as Button).text)
	_click(_find(page, "pad_jump") as Button)
	await _tick(2)
	_check("pressing Jump's controller button waits", String(page.call("capturing_now")) == "pad_jump")
	await _padbutton(JOY_BUTTON_X)
	await _tick(2)
	_check("X is now Jump on the pad (and handbrake with it)", _padspec("jump") == ["pad:2"] and _padspec("handbrake") == ["pad:2"],
		"%s %s" % [_padspec("jump"), _padspec("handbrake")])
	_check("... Reload got A (swapped)", _padspec("reload") == ["pad:0"], str(_padspec("reload")))
	_check("... jump's KEY is untouched", _keys("jump") == [32], str(_keys("jump")))
	_click(_find(page, "pad_fire") as Button)
	await _tick(2)
	await _padbutton(JOY_BUTTON_START)
	await _tick(2)
	_check("Start cannot be taken (it is pause)", _padspec("fire") == ["axis:5"] and String(page.call("capturing_now")) == "", str(_padspec("fire")))
	_click(_find(page, "pad_fire") as Button)
	await _tick(2)
	var tr := InputEventJoypadMotion.new()
	tr.axis = JOY_AXIS_TRIGGER_LEFT
	tr.axis_value = 0.9
	Input.parse_input_event(tr)
	await _tick(3)
	_check("a trigger can be captured: fire -> LT, aim -> RT", _padspec("fire") == ["axis:4"] and _padspec("aim") == ["axis:5"]
		and _padspec("throttle") == ["axis:4"], "%s %s %s" % [_padspec("fire"), _padspec("aim"), _padspec("throttle")])
	var want_jump: String = qs.call("pad_binding_now", "jump")

	print("=== 5. settings.cfg round trip ===")
	var want_interact: String = qs.call("binding_now", "interact")
	var want_forward: String = qs.call("binding_now", "forward")
	page.call("close")   # saves
	await _tick(2)
	var cfg := ConfigFile.new()
	cfg.load(CFG)
	_check("the page's close wrote [bindings]", String(cfg.get_value("bindings", "interact", "")) == want_interact,
		"interact=%s" % cfg.get_value("bindings", "interact", "-"))
	_check("... and [pad_bindings]", String(cfg.get_value("pad_bindings", "jump", "")) == "pad:2", str(cfg.get_value("pad_bindings", "jump", "-")))
	qs.call("reset_bindings_now")
	_check("reset puts the defaults back", _keys("interact") == [69] and _keys("forward") == [87], "%s %s" % [_keys("interact"), _keys("forward")])
	_check("... the pad's too", _padspec("jump") == ["pad:0"] and _padspec("fire") == ["axis:5"], "%s %s" % [_padspec("jump"), _padspec("fire")])
	qs.call("reload_now")
	_check("reload brings the saved bindings back", String(qs.call("binding_now", "interact")) == want_interact
		and String(qs.call("binding_now", "forward")) == want_forward and _keys("interact") == [KEY_R],
		"%s %s" % [qs.call("binding_now", "interact"), qs.call("binding_now", "forward")])
	_check("... and the pad's", String(qs.call("pad_binding_now", "jump")) == want_jump and _padspec("jump") == ["pad:2"], str(_padspec("jump")))

	print("=== 6. the FOV offset ===")
	var cam: Camera3D = root.get_viewport().get_camera_3d()
	await _tick(60)
	var fov0 := cam.fov
	qs.call("set_fov_offset_now", 10.0)
	await _tick(90)
	var fov1 := cam.fov
	_check("+10 deg of FOV reaches the camera", absf((fov1 - fov0) - 10.0) < 0.5, "%.2f -> %.2f" % [fov0, fov1])
	qs.call("set_fov_offset_now", 0.0)

	# put the user's settings back
	qs.call("reset_bindings_now")
	if backup == "":
		DirAccess.remove_absolute(ProjectSettings.globalize_path(CFG))
	else:
		var f := FileAccess.open(CFG, FileAccess.WRITE)
		f.store_string(backup)
		f.close()
	qs.call("reload_now")
	print("RESULT: %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
