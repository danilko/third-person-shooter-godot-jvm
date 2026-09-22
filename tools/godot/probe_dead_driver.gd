extends SceneTree
## PLAN.md 0.2 -- an AI car whose driver is killed stops driving, and the body stays in the seat (GTA).
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_dead_driver.gd
##
## Runs the real DebugWorld. Two traffic cars are built the way ZoneManager builds one -- the lane brain
## on the VEHICLE, an AICharacter seated at the wheel -- and driven down long lanes at DRIVE_SPEED. After
## WARMUP seconds the VICTIM's driver is killed; the CONTROL's is not. Then one of the zone's own ambient
## cars has its driver killed too, to see ZoneManager reclaim it once it has come to rest.
##
## Asserted, victim: the brain is dropped the tick the driver dies; the carrier nameplate goes neutral;
## the car is at rest (< 1 m/s) within REST_SECONDS; the corpse is still in the seat the whole time; it is
## a seated corpse (bones NOT simulating) and slumped -- its chest leaning toward the car's nose at least
## SLUMP_MIN_DEG more than while alive; a carjack pulls it out as a ragdoll (bones simulating) and seats the player.
## Control: brain kept, still driving at speed, driver alive. Ambient: reclaimed as abandoned, at rest.

const WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const VEHICLE := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const CTRL := "res://src/main/java/com/openworld/debug/LaneDriveProbeController.java"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const PARK := Vector3(10, 400, 10)
const DRIVE_SPEED := 20.0
const WARMUP := 3.0
const REST_SECONDS := 20.0
const SLUMP_MIN_DEG := 15.0
const SEAT_TOL := 0.05             # plus one tick of travel: the seat pin runs before the physics step moves the car

var world: Node
var helper: Node
var fails := 0

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-52s %s" % ["PASS" if ok else "FAIL", label, detail])

func _lane(name: String) -> Node:
	for n in world.find_children(name, "Node", true, false):
		var s = n.get_script()
		if s != null and str(s.resource_path).ends_with("PathLaneRoute.java"):
			return n
	return null

## A traffic car on `lane_name` with an AI at the wheel, already at DRIVE_SPEED. [car, driver, head marker]
func _traffic_car(lane_name: String) -> Array:
	var path: Path3D = _lane(lane_name).get_node("Path3D")
	var at := path.to_global(path.curve.sample_baked(20.0))
	var ahead := path.to_global(path.curve.sample_baked(24.0))
	var dir := Vector3(ahead.x - at.x, 0, ahead.z - at.z).normalized()
	var car: RigidBody3D = (load(VEHICLE) as PackedScene).instantiate()
	var ctrl: Node = load(CTRL).new()
	ctrl.set("cruise_speed", DRIVE_SPEED)
	ctrl.set("cruise_throttle", 1.0)
	car.add_child(ctrl)
	world.add_child(car)
	car.global_position = at + Vector3(0, 0.8, 0)
	car.look_at(car.global_position + dir, Vector3.UP)
	car.linear_velocity = dir * DRIVE_SPEED
	ctrl.call("drive_lane", lane_name)
	var ai: Node3D = (load(AI) as PackedScene).instantiate()
	world.add_child(ai)
	ai.global_position = car.global_position + Vector3(3, 0, 0)
	helper.call("seat_driver", car, ai)
	var skel: Skeleton3D = ai.find_children("*", "Skeleton3D", true, false)[0]
	var chest := BoneAttachment3D.new()
	chest.bone_name = "spine_03"
	skel.add_child(chest)
	var neck := BoneAttachment3D.new()
	neck.bone_name = "neck_01"
	skel.add_child(neck)
	return [car, ai, [chest, neck]]

## How far the chest (spine_03 -> neck_01) leans off the car's up axis toward its nose, degrees.
func _chest_lean(car: Node3D, marks: Array) -> float:
	var d := car.to_local((marks[1] as Node3D).global_position) - car.to_local((marks[0] as Node3D).global_position)
	return rad_to_deg(atan2(-d.z, d.y))

func _simulating(ai: Node) -> bool:
	var sims := ai.find_children("*", "PhysicalBoneSimulator3D", true, false)
	return not sims.is_empty() and (sims[0] as PhysicalBoneSimulator3D).is_simulating_physics()

func _initialize() -> void:
	world = (load(WORLD) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	helper = load(HELPER).new()
	root.add_child(helper)
	var player: Node3D = world.get_node("Characters/Player")
	player.process_mode = Node.PROCESS_MODE_DISABLED
	player.global_position = PARK
	for i in range(600):
		await physics_frame
		if _lane("east_R1") != null and _lane("loop_F1") != null:
			break
	var v := _traffic_car("east_R1")
	var c := _traffic_car("loop_F1")
	var car: RigidBody3D = v[0]
	var ctl_car: RigidBody3D = c[0]
	var driver: Node3D = v[1]
	var seat: Node3D = car.get_node("Seats/Seat0")
	# a low car's bucket seat holds the occupant VehicleConfig.seat_drop below the marker (SPC-1: 0.07 m)
	var seat_drop: float = float(car.get("vehicle_config").get("seat_drop"))
	for i in range(int(WARMUP * 60)):
		await physics_frame
	var lean_alive := 0.0
	for i in range(30):                 # averaged: the seated idle loop moves the chest a little
		await physics_frame
		lean_alive += _chest_lean(car, v[2]) / 30.0
	var speed_at_kill := car.linear_velocity.length()
	_check("victim at speed before the kill", speed_at_kill > DRIVE_SPEED * 0.7, "%.1f m/s" % speed_at_kill)
	_check("victim is AI-driven before the kill", helper.call("is_ai_driven", car), "")
	_check("nameplate not neutral while the driver lives", not helper.call("nameplate_is_neutral", car), "")

	helper.call("kill", driver)
	await physics_frame
	await physics_frame
	_check("brain dropped when the driver died", not helper.call("is_ai_driven", car), "")
	_check("carrier nameplate neutral", helper.call("nameplate_is_neutral", car), "")
	_check("corpse still occupies the driver seat", helper.call("occupant_of", car) == driver, "")

	var rest_at := -1.0
	var worst_seat := 0.0
	var lean_dead := 0.0
	var ever_simulating := false
	for i in range(int(REST_SECONDS * 60)):
		await physics_frame
		var seat_point: Vector3 = seat.global_position - car.global_transform.basis.y * seat_drop
		worst_seat = maxf(worst_seat, driver.global_position.distance_to(seat_point)
				- car.linear_velocity.length() / 60.0)
		if i >= 30 and i < 60:          # measured while still coasting straight, before any crash can move it
			lean_dead += _chest_lean(car, v[2]) / 30.0
		ever_simulating = ever_simulating or _simulating(driver)
		if rest_at < 0.0 and car.linear_velocity.length() < 1.0:
			rest_at = i / 60.0
		if i % 120 == 0:
			print("    t+%4.1f  victim %.1f m/s   control %.1f m/s" % [i / 60.0, car.linear_velocity.length(), ctl_car.linear_velocity.length()])
	_check("victim comes to rest", rest_at >= 0.0, "from %.1f m/s, at rest after %.1f s" % [speed_at_kill, rest_at])
	_check("corpse held in the seat throughout", worst_seat <= SEAT_TOL, "worst %.2f m from Seat0" % worst_seat)
	_check("seated corpse is not a simulating ragdoll", not ever_simulating, "")
	_check("corpse slumped forward over the wheel", lean_dead - lean_alive >= SLUMP_MIN_DEG,
			"chest leans %.1f deg alive, %.1f deg dead" % [lean_alive, lean_dead])

	# Control: nothing happened to it.
	_check("control still AI-driven", helper.call("is_ai_driven", ctl_car), "")
	_check("control still driving", ctl_car.linear_velocity.length() > DRIVE_SPEED * 0.5,
			"%.1f m/s" % ctl_car.linear_velocity.length())
	_check("control driver alive, not slumped", not helper.call("has_defeated_driver", ctl_car) and not _simulating(c[1]), "")

	# The carjack pulls the corpse out, and it falls as a ragdoll.
	player.process_mode = Node.PROCESS_MODE_INHERIT
	player.global_position = car.global_position + car.global_basis.x * -3.0 + Vector3(0, 1, 0)
	helper.call("carjack", car, player)
	for i in range(20):
		await physics_frame
	_check("carjack seats the player", helper.call("occupant_of", car) == player, "")
	_check("pulled-out corpse ragdolls", _simulating(driver), "")
	# Out again, or the car's seat pin keeps the player 250 m east -- far enough to unload zone debug_a
	# and every ambient car in it.
	helper.call("exit_driver", car)
	player.process_mode = Node.PROCESS_MODE_DISABLED
	player.global_position = PARK
	for i in range(60):
		await physics_frame

	# Ambient: one of the zone's own cars loses its driver and is reclaimed once at rest, out of sight.
	var amb: RigidBody3D = null
	for i in range(30 * 60):
		for n in get_nodes_in_group("streamed_vehicle"):
			var b := n as RigidBody3D
			if helper.call("is_ai_driven", b) and helper.call("occupant_of", b) != null:
				amb = b
				break
		if amb != null:
			break
		await physics_frame
	_check("found an ambient traffic car with a driver", amb != null, "")
	if amb != null:
		# Out of sight: ZoneManager only reclaims a stopped car beyond stallReclaimMinDist (60 m, XZ) of
		# every player, so the player is parked 120 m away from it -- still inside both zones.
		var far := amb.global_position + Vector3(0, 400, 0)
		far += (Vector3(10, 0, 10) - Vector3(amb.global_position.x, 0, amb.global_position.z)).normalized() * 120.0
		player.global_position = far
		helper.call("kill", helper.call("occupant_of", amb))
		var gone_at := -1.0
		var last_speed := 99.0
		for i in range(40 * 60):
			await physics_frame
			if not is_instance_valid(amb):
				gone_at = i / 60.0
				break
			last_speed = amb.linear_velocity.length()
		_check("ambient car reclaimed after coming to rest", gone_at >= 0.0 and last_speed < 1.0,
				"gone after %.1f s, last speed %.2f m/s" % [gone_at, last_speed])
	print("RESULT: %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
