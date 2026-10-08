extends SceneTree
## PLATFORM LADDERS (user 2026-10-07: "a vertical stair at the platform ... like early CS 1.6, the character flows up
## and down along it"): world.Ladder on each track-facing platform edge (tools/station_layout.py `ladders`), climbed by
## MovementController's ladder branch. A real Player through Input on DebugWorld's station A:
##   1. on the track bed facing the ladder, holding forward (looking level): on the ladder, then up onto the platform;
##   2. on the ladder half way, looking DOWN, holding forward: down to the bed;
##   3. jump on the ladder lets go of it.
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
	# 2. down: on the ladder half way, looking down
	_place(base - into * 0.4 + Vector3(0, top * 0.6, 0), into, -60.0)
	for i in 3:
		await physics_frame
	r = await _hold("forward", 2.0, into, -60.0)
	y = player.global_position.y - base.y
	_check(y < 0.3, "looking down, forward climbs down to the bed (%.2f m)" % y)
	# 3. jump lets go
	_place(base - into * 0.4 + Vector3(0, top * 0.5, 0), into, 0.0)
	for i in 3:
		await physics_frame
	var on_before := bool(player.get_node("MovementController").call("on_ladder_now"))
	Input.action_press("jump")
	for i in 3:
		await physics_frame
	Input.action_release("jump")
	for i in 6:
		await physics_frame
	var off := (player.global_position - base).dot(-into)
	_check(on_before and off > 0.6, "jump lets go of the ladder (on it before: %s, %.2f m out after)" % [on_before, off])
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0)
