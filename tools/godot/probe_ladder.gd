extends SceneTree
## PLATFORM LADDERS (user 2026-10-07: "a vertical stair at the platform ... like early CS 1.6, the character flows up
## and down along it"): world.Ladder on each track-facing platform edge (tools/station_layout.py `ladders`), climbed by
## MovementController's ladder branch. A real Player through Input on DebugWorld's station A:
##   1. on the track bed facing the ladder, holding forward (looking level): on the ladder, then up onto the platform;
##   2. looking DOWN, holding forward still climbs UP (pitch plays no part, user 2026-10-07);
##   3. no input hangs on the ladder;
##   4. looking UP, holding back climbs down to the bed, then steps off the ladder;
##   5. jump on the ladder lets go of it;
##   6. walking ALONG the bed past the ladder does not grab it (grab on intent only, 2026-10-08);
##   7. walking along the platform edge over the ladder does not grab it;
##   8. interact on the platform grabs it from the top, and back then climbs down to the bed;
##   9. interact on the ladder lets go;
##  10. with ladder_auto_grab off, walking into it does not grab it and interact does.
##   ... -- --control   (the station's ladders removed: the player stays on the bed)

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"

var fails := 0
var player: CharacterBody3D
var helper: Node


func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1


func _place(at: Vector3, look: Vector3, pitch: float) -> void:
	player.global_position = at
	player.velocity = Vector3.ZERO
	player.get_node("MovementController").call("clear_motion")
	helper.call("set_view", player, rad_to_deg(atan2(-look.x, -look.z)), pitch)


func _hold(action: String, seconds: float, look: Vector3, pitch: float) -> Array:
	var on := false
	Input.action_press(action)
	for i in int(seconds * 60.0):
		helper.call("set_view", player, rad_to_deg(atan2(-look.x, -look.z)), pitch)
		await physics_frame
		if bool(player.get_node("MovementController").call("on_ladder_now")):
			on = true
	Input.action_release(action)
	return [on]


func _mc() -> Node:
	return player.get_node("MovementController")


func _on() -> bool:
	return bool(_mc().call("on_ladder_now"))


func _tap(action: String) -> void:
	Input.action_press(action)
	await physics_frame
	await physics_frame
	Input.action_release(action)
	await physics_frame


## Put the body on the ladder where it hangs (the interact key, as a player would).
func _grab() -> void:
	if not _on():
		await _tap("interact")


func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	var world: Node = (load(DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	for i in 120:
		await physics_frame
	helper = (load(HELPER) as Script).new()
	root.add_child(helper)
	player = world.get_node("Characters/Player")
	player.get_node("Health").set("invulnerable", true)
	var ladders := []
	for n in world.find_children("Ladder*", "Area3D", true, false):
		if n.get_script() != null:
			ladders.append(n)
	print("  %d ladders in the world" % ladders.size())
	_check(ladders.size() >= 2, "station platforms carry ladders (%d)" % ladders.size())
	if ladders.is_empty():
		print("RESULT FAIL (%d failures)" % fails)
		quit(0)
		return
	var ld: Area3D = ladders[0]
	var top: float = float(ld.get("top"))
	var into: Vector3 = -ld.global_transform.basis.z.normalized()
	var base: Vector3 = ld.global_position
	print("  ladder %s at %s, top %.2f m" % [ld.get_path(), base, top])
	if control:
		for n in ladders:
			n.queue_free()
		await physics_frame
	# 1. up from the bed
	_place(base - into * 0.6 + Vector3(0, 0.1, 0), into, 0.0)
	for i in 10:
		await physics_frame
	var r: Array = await _hold("forward", 4.0, into, 0.0)
	var y: float = player.global_position.y - base.y
	var onto: float = (player.global_position - base).dot(into)
	print("  after 4 s forward: %.2f m over the bed, %.2f m in from the face, was on the ladder: %s" % [y, onto, r[0]])
	if control:
		_check(y < 0.5, "control: with no ladder the player stays on the bed (%.2f m)" % y)
		print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
		quit(0)
		return
	_check(r[0], "the player was on the ladder")
	_check(y > top - 0.15 and onto > 0.2, "...and climbed onto the platform (%.2f m up, %.2f m in)" % [y, onto])
	# 2. looking DOWN, forward still climbs UP (the view's pitch plays no part)
	_place(base - into * 0.4 + Vector3(0, top * 0.4, 0), into, -60.0)
	for i in 3:
		await physics_frame
	await _grab()
	var y0: float = player.global_position.y - base.y
	r = await _hold("forward", 0.5, into, -60.0)
	y = player.global_position.y - base.y
	_check(y > y0 + 0.5, "looking down, forward still climbs up (%.2f -> %.2f m)" % [y0, y])
	# 3. no input: hangs where it is
	_place(base - into * 0.4 + Vector3(0, top * 0.5, 0), into, 0.0)
	for i in 3:
		await physics_frame
	await _grab()
	y0 = player.global_position.y - base.y
	for i in 60:
		await physics_frame
	y = player.global_position.y - base.y
	var hanging := bool(player.get_node("MovementController").call("on_ladder_now"))
	_check(hanging and absf(y - y0) < 0.05, "no input stays on the ladder (%.2f -> %.2f m, on: %s)" % [y0, y, hanging])
	# 4. back (looking UP) climbs down to the bed, and at the foot steps off the ladder
	r = await _hold("back", 3.0, into, 30.0)
	y = player.global_position.y - base.y
	var out_m := (player.global_position - base).dot(-into)
	_check(y < 0.3, "looking up, back climbs down to the bed (%.2f m)" % y)
	_check(out_m > 0.8, "...and at the foot back steps off the ladder (%.2f m out)" % out_m)
	# 5. jump lets go
	_place(base - into * 0.4 + Vector3(0, top * 0.5, 0), into, 0.0)
	for i in 3:
		await physics_frame
	await _grab()
	var on_before := bool(player.get_node("MovementController").call("on_ladder_now"))
	Input.action_press("jump")
	for i in 3:
		await physics_frame
	Input.action_release("jump")
	for i in 6:
		await physics_frame
	var off := (player.global_position - base).dot(-into)
	_check(on_before and off > 0.6, "jump lets go of the ladder (on it before: %s, %.2f m out after)" % [on_before, off])
	var along := Vector3(-into.z, 0.0, into.x)
	# 6. walking ALONG the bed past the ladder: not grabbed
	_place(base - into * 0.5 - along * 2.5 + Vector3(0, 0.1, 0), along, 0.0)
	for i in 20:
		await physics_frame
	r = await _hold("forward", 2.0, along, 0.0)
	y = player.global_position.y - base.y
	_check(not r[0] and y < 0.3, "walking along the bed past the ladder does not grab it (on: %s, %.2f m up)" % [r[0], y])
	# 7. walking along the platform edge over the ladder: not grabbed
	_place(base + into * 0.4 - along * 2.5 + Vector3(0, top + 0.1, 0), along, 0.0)
	for i in 20:
		await physics_frame
	r = await _hold("forward", 2.0, along, 0.0)
	y = player.global_position.y - base.y
	_check(not r[0] and y > top - 0.1, "walking the platform edge over the ladder does not grab it (on: %s, %.2f m up)" % [r[0], y])
	# 8. interact on the platform grabs it from the top; back climbs down
	_place(base + into * 0.4 + Vector3(0, top + 0.1, 0), -into, 0.0)
	for i in 20:
		await physics_frame
	await _tap("interact")
	var grabbed := _on()
	y = player.global_position.y - base.y
	_check(grabbed and y < top, "interact on the platform grabs the ladder from the top (on: %s, %.2f m up)" % [grabbed, y])
	r = await _hold("back", 3.0, into, 0.0)
	y = player.global_position.y - base.y
	_check(y < 0.3, "...and back climbs down to the bed (%.2f m)" % y)
	# 9. interact on the ladder lets go
	_place(base - into * 0.4 + Vector3(0, top * 0.5, 0), into, 0.0)
	for i in 3:
		await physics_frame
	await _grab()
	on_before = _on()
	await _tap("interact")
	for i in 6:
		await physics_frame
	_check(on_before and not _on(), "interact on the ladder lets go (on before: %s, after: %s)" % [on_before, _on()])
	# 10. auto-grab off: walking into it does not grab, interact does
	_mc().set("ladder_auto_grab", false)
	_place(base - into * 0.6 + Vector3(0, 0.1, 0), into, 0.0)
	for i in 20:
		await physics_frame
	r = await _hold("forward", 1.0, into, 0.0)
	await _tap("interact")
	_check(not r[0] and _on(), "auto-grab off: walking in does not grab (%s), interact does (%s)" % [r[0], _on()])
	_mc().set("ladder_auto_grab", true)
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0)
