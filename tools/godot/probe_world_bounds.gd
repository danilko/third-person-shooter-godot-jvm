extends SceneTree
## The world edge: ONE physical rule (the hard wall) and a band that only WARNS.  (PLAN.md P0 0.6)
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_world_bounds.gd            [-- --control]
##
## History: P0 0.3 found the soft band cancelling outward velocity (an invisible wall on DebugWorld's
## loop corner); 0.6 (user decision) removed the push entirely. Three bodies head straight out along
## -Z from z = -300 with DebugWorld's numbers (half_extent 432, warn_margin 80):
##   1. a Player pressing `forward` (confined every frame, the real input path);
##   2. a RigidBody3D in "characters" holding 10 m/s (a car; confined on the 0.5 s sweep);
##   3. a CharacterBody3D in the group at 6 m/s (an AI; confined on the sweep).
## Asserted: NO body loses speed anywhere inside the wall (band included), each is turned back at the
## wall (swept bodies within speed x sweep), the Player ends inside it, `leaving_area` fires exactly
## once on entering the band and `returned_to_area` exactly once when the player walks back out of it,
## the HUD warning is shown while in the band and hidden after, and nothing is emitted for the AI or car.
## `-- --control` puts back a soft push the way it used to act (a velocity cancel from the band's
## inner edge, driven from the probe): the band speed checks fail.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const BOUNDS := "res://src/main/java/com/openworld/world/WorldBounds.java"
const WARNING := "res://src/main/java/com/openworld/ui/AreaWarning.java"
const HALF := 432.0
const MARGIN := 80.0

var fails := 0
var leaving := []
var returned := 0

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", label, detail])

class Car extends RigidBody3D:
	func _physics_process(delta: float) -> void:
		linear_velocity.z = move_toward(linear_velocity.z, -10.0, 6.0 * delta)

class Walker extends CharacterBody3D:
	var speed := 6.0
	func _physics_process(delta: float) -> void:
		velocity.z = -speed
		velocity.y -= 9.8 * delta
		move_and_slide()

func _on_leaving(d: float) -> void:
	leaving.append(d)

func _on_returned() -> void:
	returned += 1

func _vz(b: Node3D) -> float:
	return (b as RigidBody3D).linear_velocity.z if b is RigidBody3D else (b as CharacterBody3D).velocity.z

func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	var bus := root.get_node("EventBus")
	bus.connect("leaving_area", _on_leaving)
	bus.connect("returned_to_area", _on_returned)

	var world := Node3D.new()
	root.add_child(world)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(40, 2, 1200)
	cs.shape = sh
	floor.add_child(cs)
	world.add_child(floor)
	floor.position = Vector3(0, -1, 0)

	var bounds: Node3D = load(BOUNDS).new()
	bounds.set("half_extent", HALF)
	bounds.set("warn_margin", MARGIN)
	bounds.set("debug_log", true)
	world.add_child(bounds)
	await physics_frame

	var player: CharacterBody3D = (load(PLAYER) as PackedScene).instantiate()
	world.add_child(player)
	player.position = Vector3(-8, 1.2, -300)

	var warn: Control = load(WARNING).new()
	world.add_child(warn)
	warn.call("wire_character", player)

	var car := Car.new()
	var ccs := CollisionShape3D.new()
	var cbox := BoxShape3D.new()
	cbox.size = Vector3(2, 1, 4)
	ccs.shape = cbox
	car.add_child(ccs)
	car.gravity_scale = 0.0
	car.linear_damp_mode = RigidBody3D.DAMP_MODE_REPLACE
	car.linear_damp = 0.0
	car.can_sleep = false
	car.add_to_group("characters")
	world.add_child(car)
	car.position = Vector3(0, 3, -300)
	car.linear_velocity = Vector3(0, 0, -10)

	var ai := Walker.new()
	var acs := CollisionShape3D.new()
	acs.shape = CapsuleShape3D.new()
	ai.add_child(acs)
	ai.add_to_group("characters")
	world.add_child(ai)
	ai.position = Vector3(8, 1.2, -300)

	for i in range(60):
		await physics_frame
	var outward_speed := {"player": 0.0}
	for i in range(60):
		await physics_frame
		outward_speed["player"] = maxf(outward_speed["player"], -player.velocity.z)
	Input.action_press("forward")
	for i in range(60):
		await physics_frame
	outward_speed["player"] = -player.velocity.z
	outward_speed["car"] = 10.0
	outward_speed["ai"] = 6.0

	var bodies := {"player": player, "car": car, "ai": ai}
	var deepest := {}
	var band_speed := {}
	var shown_in_band := false
	for k in bodies:
		deepest[k] = 0.0
		band_speed[k] = []
	for i in range(60 * 30):
		await physics_frame
		for k in bodies:
			var b: Node3D = bodies[k]
			var z := b.global_position.z
			if control and z < -(HALF - MARGIN):
				# the old soft band: outward velocity cancelled in the band
				if b is RigidBody3D:
					(b as RigidBody3D).linear_velocity.z = maxf((b as RigidBody3D).linear_velocity.z, 0.0)
				else:
					(b as CharacterBody3D).velocity.z = maxf((b as CharacterBody3D).velocity.z, 0.0)
			deepest[k] = minf(deepest[k], z)
			# the band, and anything inside the wall at all, stopping 3 m short of it
			if z < -(HALF - MARGIN) + 5.0 and z > -HALF + 3.0:
				band_speed[k].append(-_vz(b))
		if player.global_position.z < -(HALF - MARGIN) - 10.0 and warn.call("warning_shown"):
			shown_in_band = true
	Input.action_release("forward")
	var player_leaving := leaving.size()
	print("  hard corrections %d; leaving_area x%d %s; returned_to_area x%d" % [
		bounds.call("hard_correction_count"), leaving.size(), str(leaving), returned])

	for k in bodies:
		var sp: Array = band_speed[k]
		var mn := 1e9
		var mean := 0.0
		for v in sp:
			mn = minf(mn, float(v))
			mean += float(v)
		mean = mean / sp.size() if sp.size() > 0 else 0.0
		print("  %-6s deepest z %.2f   band speed min %.2f mean %.2f m/s (%d samples, full %.2f)" % [
			k, deepest[k], mn, mean, sp.size(), outward_speed[k]])
		_check("%s crosses the whole warning band" % k, float(deepest[k]) < -HALF + 3.0,
			"deepest %.2f" % deepest[k])
		_check("%s loses no speed anywhere inside the wall" % k, sp.size() > 0 and mn > 0.9 * float(outward_speed[k]),
			"min %.2f of %.2f m/s" % [mn, outward_speed[k]])
		var slack: float = {"player": 0.5, "car": 10.0 * 0.5 + 0.5, "ai": 6.0 * 0.5 + 0.5}[k]
		_check("%s is turned back at the wall" % k, float(deepest[k]) > -HALF - slack,
			"deepest %.2f vs wall %.0f (+%.1f sweep slack)" % [deepest[k], -HALF, slack])
	_check("player ends inside the wall", player.global_position.z > -HALF - 0.1,
		"final z %.2f" % player.global_position.z)
	_check("leaving_area fired once, for the player only", player_leaving == 1,
		"%d emissions (the AI and car went through the band too)" % player_leaving)
	_check("  ... with the distance to the wall on entry", player_leaving == 1 and absf(float(leaving[0]) - MARGIN) < 1.0,
		str(leaving))
	_check("the HUD warning is shown in the band", shown_in_band, "")

	# walk back in
	Input.action_press("back")
	for i in range(60 * 25):
		await physics_frame
		if player.global_position.z > -(HALF - MARGIN) + 20.0:
			break
	Input.action_release("back")
	for i in range(10):
		await process_frame
	_check("returned_to_area fired once on leaving the band", returned == 1, "x%d, player z %.1f" % [returned, player.global_position.z])
	_check("the HUD warning hides again", not warn.call("warning_shown"), "")
	_check("leaving_area did not fire again", leaving.size() == 1, "x%d" % leaving.size())

	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
