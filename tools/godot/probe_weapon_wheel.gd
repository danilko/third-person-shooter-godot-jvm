extends SceneTree
## The weapon wheel (PLAN 2026-09-16): upright cards on an ellipse, selection by the pointer's ANGLE, and
## 10 pt outlined text in the wheel and the slot bar. Runs WITH A DISPLAY (not --headless) and saves a screenshot.
##
##   /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --path . --script tools/godot/probe_weapon_wheel.gd -- [--shot=<png>]
##
## Real HUDManager + a real Player armed through pickups. Asserted: one card per slot; no two cards overlap; every
## card is on screen; pointing at each card's centre selects that slot, through the menu's own angle function AND
## through a real mouse-motion event; a pointer inside the dead zone changes nothing; every text control in the
## wheel's cards and the slot bar draws at 10 pt with a dark outline.
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const HUD := "res://src/main/resources/com/openworld/ui/HUDManager.tscn"
const WEAPONS := ["AR4", "SR3", "PI52", "MW1", "T1"]
var fails := 0

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-56s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _texts(n: Node, out: Array) -> void:
	if n is Label or n is RichTextLabel:
		out.append(n)
	for c in n.get_children():
		_texts(c, out)

func _initialize() -> void:
	var shot := ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--shot="):
			shot = a.substr(7)
	var world := Node3D.new()
	root.add_child(world)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(60, 2, 60)
	cs.shape = box
	floor.add_child(cs)
	world.add_child(floor)
	floor.position = Vector3(0, -1, 0)
	var hud: Node = (load(HUD) as PackedScene).instantiate()
	root.add_child(hud)
	await _tick(2)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate()
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
	await _tick(30)
	for id in WEAPONS:
		var g: Node3D = (load("res://src/main/resources/com/openworld/weapon/%s.tscn" % id) as PackedScene).instantiate()
		world.add_child(g)
		g.global_position = p.global_position + Vector3(0, 0.3, 0)
		await _tick(40)
	var menu: Control = hud.get_node("WeaponRadialMenu")
	menu.call("wire_character_node", p)
	menu.call("open_menu")
	await _tick(90)   # the Zoom animation
	var circle: Control = menu.get_node("Panel/Circle")
	var cards := []
	for c in circle.get_children():
		if c.get_script() != null and str(c.get_script().resource_path).ends_with("WeaponRadialMenuItem.java"):
			cards.append(c)
	var slots: int = p.get_node("WeaponController").call("get_slot_count") if p.get_node("WeaponController").has_method("get_slot_count") else cards.size()
	_check("one card per slot", cards.size() == slots and cards.size() > 0, "%d cards, %d slots" % [cards.size(), slots])
	var overlap := 0
	for i in range(cards.size()):
		for j in range(i + 1, cards.size()):
			if (cards[i] as Control).get_global_rect().intersects((cards[j] as Control).get_global_rect()):
				overlap += 1
	_check("no two cards overlap", overlap == 0, "%d overlapping pairs" % overlap)
	var vp := menu.get_viewport_rect()
	var off := 0
	for c in cards:
		if not vp.encloses((c as Control).get_global_rect()):
			off += 1
	_check("every card is on screen", off == 0, "%d off screen (viewport %s)" % [off, vp.size])
	var wrong := []
	for c in cards:
		menu.call("select_from_pointer", (c as Control).get_global_rect().get_center())
		if int(menu.call("selected_slot")) != int(c.get("index")) or not bool(c.call("highlighted_now")):
			wrong.append(c.get("index"))
	_check("pointing at each card selects its slot (angle function)", wrong.is_empty(), "wrong: %s" % str(wrong))
	var wrong_ev := []
	for c in cards:
		var ev := InputEventMouseMotion.new()
		ev.position = root.get_final_transform() * (c as Control).get_global_rect().get_center()
		ev.global_position = ev.position
		Input.parse_input_event(ev)
		await process_frame
		await process_frame
		if int(menu.call("selected_slot")) != int(c.get("index")):
			wrong_ev.append(c.get("index"))
	_check("... and through a real mouse-motion event", wrong_ev.is_empty(), "wrong: %s" % str(wrong_ev))
	var keys_ok := true
	for c in cards:
		var want := "[%d]" % int(c.get("index"))
		if (c.get_node("Key") as Label).text != want:
			keys_ok = false
	_check("each card shows its slot's key, as the slot bar does (0 = fist)", keys_ok, "")
	var before: int = menu.call("selected_slot")
	var centre := menu.get_global_rect().get_center()
	menu.call("select_from_pointer", centre + Vector2(10, -10))
	_check("a pointer in the dead zone changes nothing", int(menu.call("selected_slot")) == before, "")
	menu.call("select_from_pointer", (cards[0] as Control).get_global_rect().get_center())
	await _tick(30)

	var texts := []
	for c in cards:
		_texts(c, texts)
	_texts(hud.get_node("WeaponSlotsUI"), texts)
	var bad := []
	for t in texts:
		var size: int = (t as Control).get_theme_font_size("font_size" if t is Label else "normal_font_size")
		var outline: int = (t as Control).get_theme_constant("outline_size")
		if size != 10 or outline <= 0:
			bad.append("%s size %d outline %d" % [t.name, size, outline])
	_check("every wheel and slot-bar text is 10 pt with an outline", bad.is_empty() and texts.size() > 0, "%d texts; %s" % [texts.size(), str(bad.slice(0, 4))])
	var plain := Label.new()
	root.add_child(plain)
	_check("any other in-game Label gets the dark outline (game theme)", plain.get_theme_constant("outline_size") > 0 and plain.get_theme_color("font_outline_color").a > 0.5,
		"outline %d" % plain.get_theme_constant("outline_size"))
	if shot != "":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(shot)
		print("  screenshot: %s" % shot)
		menu.call("close_menu")
		await _tick(10)
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(shot.get_basename() + "_closed.png")
		print("  screenshot: %s" % (shot.get_basename() + "_closed.png"))
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
