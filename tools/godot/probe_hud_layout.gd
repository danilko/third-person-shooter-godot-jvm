extends SceneTree
## The HUD layout (ui/HUDManager.tscn): the corners own one panel each and nothing overlaps, the weapon panel,
## the pop-up inventory column, the health colour ramp, and the in-car rules (the driver gets the speedometer;
## the weapon panel takes the corner only while aiming a drive-by; your own car carries no nameplate).
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --path . --script tools/godot/probe_hud_layout.gd
## Pictures: tools/godot/shot_hud.gd (needs a display).

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const HUD := "res://src/main/resources/com/openworld/ui/HUDManager.tscn"
const CAR := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
var fails := 0
var hud: Node

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await process_frame

## Real time: the weapon switch, the column's fade and the drive-by hold are timers, and headless frames are
## not paced, so a frame count says nothing about how much time has passed.
func _wait(seconds: float) -> void:
	await create_timer(seconds).timeout
	await process_frame

## The on-screen rectangles of every visible HUD panel.
func _panels() -> Dictionary:
	var out := {}
	var rects := {
		"health": hud.get_node("FootHUD/Health"), "minimap": hud.get_node("Minimap"),
		"weapon": hud.get_node("WeaponHUD"), "slots": hud.get_node("WeaponSlotsUI"),
		"speed": hud.get_node("VehicleHUD/Speed"), "killfeed": hud.get_node("Feed/VBoxContainer"),
		"notices": hud.get_node("StatusFeed/VBoxContainer"),
	}
	for k in rects:
		var c: Control = rects[k]
		if c.is_visible_in_tree() and c.modulate.a > 0.05 and c.get_global_rect().size.y > 1.0:
			out[k] = c.get_global_rect()
	return out

func _overlaps(p: Dictionary) -> Array:
	var bad := []
	var keys := p.keys()
	for i in range(keys.size()):
		for j in range(i + 1, keys.size()):
			if (p[keys[i]] as Rect2).intersects(p[keys[j]]):
				bad.append("%s/%s" % [keys[i], keys[j]])
	return bad

func _initialize() -> void:
	root.size = Vector2i(1152, 648)
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	cs.shape = BoxShape3D.new()
	(cs.shape as BoxShape3D).size = Vector3(400, 2, 400)
	floor.add_child(cs)
	floor.position = Vector3(0, -1, 0)
	world.add_child(floor)
	hud = (load(HUD) as PackedScene).instantiate()
	root.add_child(hud)
	await _tick(2)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate()
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
	await _tick(30)
	for id in ["ASR1", "PIS1", "MEW1"]:
		var g: Node3D = (load("res://src/main/resources/com/openworld/weapon/%s.tscn" % id) as PackedScene).instantiate()
		world.add_child(g)
		g.global_position = p.global_position + Vector3(0, 0.3, 0)
		await _tick(30)
	var bus := root.get_node_or_null("/root/EventBus")
	for k in 3:
		bus.emit_signal("character_eliminated", "Player", "player", "Enemy %d" % k, "enemy", "ASR-1", null, false)
	await _tick(10)

	print("== on foot")
	var wc: Node = p.get_node("WeaponController")
	wc.call("on_set_weapon", 1)
	await _wait(0.8)
	var slots: Node = hud.get_node("WeaponSlotsUI")
	var shown := float(slots.call("shown_now"))
	var foot := _panels()
	_check("the inventory column comes up to full on a switch", shown > 0.9, "alpha %.2f" % shown)
	_check("nothing overlaps (with the column up)", _overlaps(foot).is_empty(), "%s / %s" % [_overlaps(foot), foot.keys()])
	var heights := {}
	for r in hud.get_node("WeaponSlotsUI/Slots").get_children():
		if r.visible:
			heights[r.get_node("Icon/NameLabel").text] = r.size.y
	var hs := heights.values()
	_check("every inventory row is the same height (fist included)", hs.size() >= 4 and hs.min() == hs.max(), str(heights))
	# common height, capped by the box's width: every silhouette is drawn either at the box's full height or, if
	# it is too long and thin for that (a knife), at the box's full width
	var off := []
	for r in hud.get_node("WeaponSlotsUI/Slots").get_children():
		var ic: TextureRect = r.get_node("Icon")
		if r.visible and ic.texture != null:
			var ts: Vector2 = ic.texture.get_size()
			var k := minf(ic.size.x / ts.x, ic.size.y / ts.y)
			if absf(ts.y * k - ic.size.y) > 0.5 and absf(ts.x * k - ic.size.x) > 0.5:
				off.append("%s %.1fx%.1f" % [r.get_node("Icon/NameLabel").text, ts.x * k, ts.y * k])
	_check("every silhouette at the common height (or the full width, if long)", off.is_empty(), str(off))
	var wtext: String = hud.get_node("WeaponHUD").call("text_now")
	_check("the weapon panel: name, magazine, reserve", wtext == "ASR-1 30 / 60", wtext)
	wc.call("on_set_weapon", 4)
	await _wait(0.8)
	var ktext: String = hud.get_node("WeaponHUD").call("text_now")
	_check("a melee weapon shows no ammo count", ktext == "MEW-1", ktext)
	await _wait(3.2)
	var idle := float(slots.get("idle_alpha"))
	_check("the column settles back to its quiet resting level", absf(float(slots.call("shown_now")) - idle) < 0.02,
		"alpha %.2f (idle %.2f)" % [float(slots.call("shown_now")), idle])
	_check("and stays on screen (the loadout is always readable)", idle > 0.3 and slots.is_visible_in_tree())
	var corners := {"health": Vector2(0, 1), "minimap": Vector2(0, 1), "weapon": Vector2(1, 1), "killfeed": Vector2(1, 0), "notices": Vector2(0, 0)}
	var vp := (hud.get_node("FootHUD") as Control).get_viewport_rect().size
	var wrong := []
	for k in corners:
		if not foot.has(k):
			continue
		var c: Vector2 = (foot[k] as Rect2).get_center()
		if Vector2(1 if c.x > vp.x / 2 else 0, 1 if c.y > vp.y / 2 else 0) != corners[k]:
			wrong.append(k)
	_check("each panel sits in its corner", wrong.is_empty(), str(wrong))

	print("== health colour ramp")
	var h: Node = p.get_node("Health")
	var foothud: Node = hud.get_node("FootHUD")
	var mh := float(h.get("max_health"))
	foothud.call("on_health_changed", mh * 0.4)
	var amber: Color = (foothud.get_node("Health/Value") as Control).modulate
	foothud.call("on_health_changed", mh * 0.2)
	var red: Color = (foothud.get_node("Health/Value") as Control).modulate
	foothud.call("on_health_changed", mh)
	var white: Color = (foothud.get_node("Health/Value") as Control).modulate
	_check("white, amber under half, red under a quarter", white == Color(1, 1, 1, 1) and amber.g > 0.6 and amber.b < 0.4 and red.g < 0.4,
		"%s %s %s" % [white, amber, red])

	print("== driving")
	var car: RigidBody3D = (load(CAR) as PackedScene).instantiate()
	world.add_child(car)
	car.global_position = p.global_position + Vector3(4, 1.0, 0)
	await _tick(10)
	var helper: Node = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
	world.add_child(helper)
	helper.call("seat_driver", car, p)
	car.linear_velocity = -car.global_basis.z * 12.0
	await _tick(20)
	var drive := _panels()
	_check("the driver gets the vehicle cluster with the weapon stacked above", drive.has("speed") and drive.has("weapon")
		and not drive.has("slots"), str(drive.keys()))
	if drive.has("speed") and drive.has("weapon"):
		_check("the weapon line sits above the cluster", (drive["weapon"] as Rect2).end.y <= (drive["speed"] as Rect2).position.y + 0.5,
			"%s over %s" % [drive["weapon"], drive["speed"]])
	var sp: String = hud.get_node("VehicleHUD").call("speed_text_now")
	_check("speed in km/h", sp.is_valid_int() and int(sp) > 20, sp + " km/h")
	var hp_text: String = hud.get_node("VehicleHUD").call("health_text_now")
	_check("the car's health is shown as a percentage", hp_text == "100%", hp_text)
	_check("your own car carries no nameplate", not (car.get_node("Nameplate") as Node3D).visible)
	_check("nothing overlaps in the car", _overlaps(drive).is_empty(), str(_overlaps(drive)))
	Input.action_press("aim")
	await _wait(0.2)
	var aimed := _panels()
	_check("aiming changes nothing in the corner (no flicker)", aimed.keys() == drive.keys(), str(aimed.keys()))
	Input.action_release("aim")

	print("== vehicle damage diagram")
	var status: Node = hud.get_node("VehicleHUD/Speed/Status")
	var s0: String = status.call("state_now")
	_check("a sound car: body 1.00, every wheel 1.00", s0.begins_with("body 1.00") and not s0.contains("flat") and s0.count("1.00") == 5, s0)
	car.get_node("Health").call("apply_replicated_health", float(car.get_node("Health").get("max_health")) * 0.3)
	helper.call("flatten_tire", car, 0)
	await _wait(0.1)
	var s1: String = status.call("state_now")
	_check("damage shows: body at 30%, one tire flat", s1.begins_with("body 0.30") and s1.count("(flat)") == 1, s1)
	var hp30: String = hud.get_node("VehicleHUD").call("health_text_now")
	var hp_col: Color = (hud.get_node("VehicleHUD/Speed/Health") as Label).modulate
	_check("the percentage follows: 30%, amber", hp30 == "30%" and hp_col.b < 0.5 and hp_col.r > 0.8, "%s %s" % [hp30, hp_col])

	print("== underwater, seated")
	var water: Area3D = load("res://src/main/java/com/openworld/world/WaterVolume.java").new()
	var wcs := CollisionShape3D.new()
	wcs.shape = BoxShape3D.new()
	(wcs.shape as BoxShape3D).size = Vector3(400, 60, 400)
	water.add_child(wcs)
	world.add_child(water)
	water.global_position = Vector3(0, 0, 0)        # surface at y = 30: every camera here is under it
	await _wait(0.1)
	var cam := root.get_viewport().get_camera_3d()
	_check("the car's camera under water tints the screen", bool(hud.get_node("UnderwaterOverlay").call("underwater_now")),
		"camera %s y %.1f" % [cam.name if cam else "none", cam.global_position.y if cam else 0.0])
	water.queue_free()
	await _wait(0.1)
	_check("and clears when it is not", not bool(hud.get_node("UnderwaterOverlay").call("underwater_now")))

	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails > 0 else 0)
