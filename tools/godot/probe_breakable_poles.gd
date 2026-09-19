extends SceneTree
## PLAN.md 3.11 -- a car knocks a street lamp down and keeps most of its speed; a slow car stops against it; the
## lamp comes back only where nobody sees it.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_breakable_poles.gd
##   ... -- --control      (every BreakableProps' breaking_enabled off: the pre-3.11 world, the car stops dead)
##
## Runs the real DebugWorld with its two streamed Road Kit pieces and drives Vehicle.tscn at REAL lamps (the
## `Breakable_StreetLight_JP` batches the bake made from furniture.json). The car starts on the lane 22 m back and
## is held at its speed, aimed at the lamp, until it is 7 m away (so every case meets the pole at the speed it
## names), then coasts. Cases:
##   1. 15 m/s: the lamp goes down (collider off, a falling body), the car passes it keeping >= 70 % of its speed,
##      and a ray straight down the shaft now finds nothing (no static box left behind in the piece);
##   2. 3 m/s: the lamp stands and the car stops against it;
##   3. the lamp from case 1, aged past its respawn time, with a camera 20 m away LOOKING at it: still down;
##      the camera turned away: back up, solid, its falling body gone;
##   4. a frozen car moved kinematically (a PUPPET) knocks another lamp down on this peer by itself (3.11b: no
##      message; the two-process half is tools/net/run_net_pole_test.sh).

const WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const VEHICLE := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
const PARK := Vector3(10, 400, 10)
const RELEASE_M := 7.0
const START_BACK := 22.0

var world: Node
var fails := 0

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _batches(asset: String) -> Array:
	var out := []
	for n in world.find_children("Breakable_*", "MultiMeshInstance3D", true, false):
		if str(n.get("asset_name")) == asset:
			out.append(n)
	return out

func _through_lanes() -> Array:
	var out := []
	for n in world.find_children("*", "Node", true, false):
		var s = n.get_script()
		if s != null and str(s.resource_path).ends_with("PathLaneRoute.java") and not str(n.name).begins_with("c"):
			out.append(n)
	return out

## [lane path, offset along it] of the lane point nearest `p` in plan, or [] when none within 20 m.
func _nearest_lane(p: Vector3) -> Array:
	var best := []
	var best_d := 20.0
	for lane in _through_lanes():
		var path: Path3D = lane.get_node_or_null("Path3D")
		if path == null or path.curve == null or path.curve.get_baked_length() < 60.0:
			continue
		var off := path.curve.get_closest_offset(path.to_local(p))
		if not is_finite(off):
			continue
		var at := path.to_global(path.curve.sample_baked(off))
		var d := Vector2(at.x - p.x, at.z - p.z).length()
		if d < best_d:
			best_d = d
			best = [path, off]
	return best

## A lamp with a lane beside it that runs straight START_BACK m before it, near the lamp's height.
func _pick_lamp(skip: Array) -> Array:
	for b in _batches("StreetLight_JP"):
		for i in int(b.call("pole_count_now")):
			var key := str(b.call("pole_key_now", i))
			if key in skip:
				continue
			var p: Vector3 = b.call("pole_world_position_now", i)
			var near := _nearest_lane(p)
			if near.is_empty():
				continue
			var path: Path3D = near[0]
			var off: float = near[1]
			if off < START_BACK + 10.0:
				continue
			var start := path.to_global(path.curve.sample_baked(off - START_BACK))
			var at := path.to_global(path.curve.sample_baked(off))
			if absf(at.y - p.y) > 0.6 or absf(start.y - at.y) > 1.5:
				continue
			# the lane must be straight enough that the approach line stays on the road
			var mid := path.to_global(path.curve.sample_baked(off - START_BACK * 0.5))
			var chord := (at - start)
			var dev := Vector2(mid.x - (start.x + at.x) * 0.5, mid.z - (start.z + at.z) * 0.5).length()
			if dev > 0.8 or chord.length() < START_BACK * 0.9:
				continue
			return [b, i, start, key]
	return []

## Drive at a lamp: held at `speed`, aimed at it, until `release_m` away (or for `hold_s` seconds when > 0), then
## coasting for `coast_s`. Returns {release_speed, speed_after (0.2 s after a break), broke_tick, along_max (how far
## the car's centre got past the lamp along the approach), final_speed, car}. Holding the velocity INTO a contact
## is an infinite force that slides the car round a thin pole, so every case lets the car coast the last metres.
func _drive(b: Node, i: int, start: Vector3, speed: float, hold_s: float, coast_s: float, release_m: float = RELEASE_M) -> Dictionary:
	var pole: Vector3 = b.call("pole_world_position_now", i)
	var dir := Vector3(pole.x - start.x, 0, pole.z - start.z).normalized()
	var car: RigidBody3D = (load(VEHICLE) as PackedScene).instantiate()
	world.add_child(car)
	car.global_position = start + Vector3(0, 0.8, 0)
	car.look_at(car.global_position + dir, Vector3.UP)   # the car's nose is -Z
	var r := {"side_at_pole": -1.0, "release_speed": 0.0, "speed_after": 0.0, "broke_tick": -1, "along_max": -INF}
	var held := true
	var tick := 0
	var after_ticks := -1
	var total := int((hold_s if hold_s > 0.0 else 10.0) * 60.0 + coast_s * 60.0)
	for f in range(total):
		var p := car.global_position
		var along := Vector3(p.x - pole.x, 0, p.z - pole.z).dot(dir)
		r["along_max"] = maxf(r["along_max"], along)
		var side := absf(Vector3(p.x - pole.x, 0, p.z - pole.z).cross(dir).y)
		if absf(along) < 0.5:
			r["side_at_pole"] = side
		if OS.get_environment("PROBE_TRACE") != "" and f % 10 == 0:
			print("    t %d along %.2f side %.2f v %.2f y %.2f" % [f, along, side, car.linear_velocity.length(), p.y])
		var flat := Vector2(p.x - pole.x, p.z - pole.z).length()
		if held:
			# re-aimed at the lamp every tick: the road's crossfall walks a slow car 1.5 m sideways over 22 m
			var aim := Vector3(pole.x - p.x, 0, pole.z - p.z).normalized()
			var v := car.linear_velocity
			car.linear_velocity = Vector3(aim.x * speed, v.y, aim.z * speed)
			car.look_at(p + aim, Vector3.UP)
			if hold_s > 0.0:
				held = f < int(hold_s * 60.0)
			elif flat < release_m:
				held = false
				r["release_speed"] = speed
		if r["broke_tick"] < 0 and bool(b.call("pole_broken_now", i)):
			r["broke_tick"] = tick
			after_ticks = 12
		if after_ticks > 0:
			after_ticks -= 1
			if after_ticks == 0:
				r["speed_after"] = Vector2(car.linear_velocity.x, car.linear_velocity.z).length()
		if hold_s <= 0.0 and not held and after_ticks == 0 and r["along_max"] > 3.0:
			break
		if not held and car.linear_velocity.length() < 0.3 and f > 60:
			break   # stopped (the control, or the slow case after its hold)
		await physics_frame
		tick += 1
	r["final_speed"] = Vector2(car.linear_velocity.x, car.linear_velocity.z).length()
	r["car"] = car
	return r

func _ray_down(p: Vector3, height: float) -> Dictionary:
	var q := PhysicsRayQueryParameters3D.create(p + Vector3(0, height + 2.0, 0), p + Vector3(0, height - 1.0, 0))
	return world.get_world_3d().direct_space_state.intersect_ray(q)

func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	world = (load(WORLD) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	var player: Node3D = world.get_node("Characters/Player")
	player.process_mode = Node.PROCESS_MODE_DISABLED
	player.global_position = PARK
	var waited := 0
	while _batches("StreetLight_JP").size() < 2 and waited < 60 * 30:
		await physics_frame
		waited += 1
	var batches := _batches("StreetLight_JP")
	var poles := 0
	for b in batches:
		poles += int(b.call("pole_count_now"))
	print("probe: %d lamp batches, %d lamps, streamed after %.1f s%s" % [batches.size(), poles, waited / 60.0,
			" (CONTROL: breaking off)" if control else ""])
	_check(batches.size() >= 2 and poles > 10, "both DebugRoads pieces carry a BreakableProps lamp batch")
	if control:
		for n in world.find_children("Breakable_*", "MultiMeshInstance3D", true, false):
			n.set("breaking_enabled", false)
	for f in 30:
		await physics_frame

	# --- 1. 15 m/s into a lamp
	var fast := _pick_lamp([])
	if fast.is_empty():
		print("RESULT: FAIL (no lamp with a straight lane beside it)")
		quit(2)
		return
	var b: Node = fast[0]
	var i: int = fast[1]
	var pole: Vector3 = b.call("pole_world_position_now", i)
	var height: float = b.get("pole_height")
	print("case 1: %s at (%.1f, %.1f, %.1f), 15 m/s" % [fast[3], pole.x, pole.y, pole.z])
	var hit := _ray_down(pole, height)
	_check(not hit.is_empty() and str(hit.collider.name) == "Poles",
			"a standing lamp's shaft is its BreakableProps collider (ray hit %s)" % [hit.collider.name if not hit.is_empty() else "nothing"])
	var r := await _drive(b, i, fast[2], 15.0, 0.0, 2.0)
	var keep: float = r["speed_after"] / 15.0
	print("  broke at tick %d, speed 0.2 s after %.2f m/s (kept %.0f %%), passed %.1f m beyond, final %.2f m/s" % [
			r["broke_tick"], r["speed_after"], keep * 100.0, r["along_max"], r["final_speed"]])
	_check(bool(b.call("pole_broken_now", i)), "the lamp went down")
	_check(not bool(b.call("pole_solid_now", i)), "its collider is off")
	_check(b.call("pole_debris_now", i) != null, "a falling body took its place")
	_check(keep >= 0.7, "the car kept >= 70 %% of its speed (%.0f %%)" % [keep * 100.0])
	_check(r["along_max"] > 3.0, "the car drove on past the lamp (%.1f m)" % r["along_max"])
	hit = _ray_down(pole, height)
	_check(hit.is_empty() or str(hit.collider.name) != "Poles",
			"nothing is left standing in the shaft (ray hit %s)" % [hit.collider.name if not hit.is_empty() else "nothing"])
	(r["car"] as Node).queue_free()

	# --- 2. 3 m/s held against another lamp
	var slow := _pick_lamp([fast[3]])
	if not slow.is_empty():
		var sb: Node = slow[0]
		var si: int = slow[1]
		print("case 2: %s, 3 m/s, released 1 m before the bumper meets it" % slow[3])
		var r2 := await _drive(sb, si, slow[2], 3.0, 0.0, 4.0, 3.3)
		print("  the car's centre stopped %.2f m short of the lamp, final %.2f m/s" % [-r2["along_max"], r2["final_speed"]])
		_check(not bool(sb.call("pole_broken_now", si)), "the slow lamp stands")
		_check(bool(sb.call("pole_solid_now", si)), "its collider is on")
		_check(r2["along_max"] < -1.0 and r2["final_speed"] < 0.5,
				"the car stopped against it (centre %.2f m short, %.2f m/s)" % [-r2["along_max"], r2["final_speed"]])
		(r2["car"] as Node).queue_free()
	else:
		_check(false, "a second lamp for the slow case")

	# --- 3. the return, only unseen
	if bool(b.call("pole_broken_now", i)):
		var cam := Camera3D.new()
		world.add_child(cam)
		cam.global_position = pole + Vector3(20, 6, 0)
		cam.look_at(pole + Vector3(0, height * 0.5, 0), Vector3.UP)
		cam.current = true
		b.call("age_break_now", i, float(b.get("respawn_seconds")) + 1.0)
		for f in 90:
			await physics_frame
		_check(bool(b.call("pole_broken_now", i)), "past its respawn time, a lamp the camera looks at stays down")
		cam.look_at(pole + Vector3(60, 6, 0), Vector3.UP)
		for f in 90:
			await physics_frame
		_check(not bool(b.call("pole_broken_now", i)), "with the camera turned away it comes back")
		_check(bool(b.call("pole_solid_now", i)), "its collider is back")
		_check(b.call("pole_debris_now", i) == null, "its falling body is gone")
		hit = _ray_down(pole, height)
		_check(not hit.is_empty() and str(hit.collider.name) == "Poles", "the shaft is solid again")
	else:
		_check(false, "case 3 needs the lamp from case 1 down")

	# --- 4. a PUPPET car (frozen, placed kinematically -- how another peer's car moves here) knocks a lamp down
	# on this peer by itself (3.11b: every peer decides locally, nothing is sent), and its motion is not touched
	var pup := _pick_lamp([fast[3], slow[3] if not slow.is_empty() else ""])
	if not pup.is_empty():
		var pb: Node = pup[0]
		var pi: int = pup[1]
		var pp: Vector3 = pb.call("pole_world_position_now", pi)
		var start: Vector3 = pup[2]
		var dir := Vector3(pp.x - start.x, 0, pp.z - start.z).normalized()
		var car: RigidBody3D = (load(VEHICLE) as PackedScene).instantiate()
		world.add_child(car)
		car.freeze = true
		var y := start.y + 0.8
		car.global_position = Vector3(start.x, y, start.z)
		car.look_at(car.global_position + dir, Vector3.UP)
		print("case 4: %s, a frozen (puppet) car moved at 15 m/s" % pup[3])
		var moved := 0.0
		for f in 150:
			await physics_frame
			var step := dir * (15.0 / 60.0)
			car.global_position += step
			moved += step.length()
			if moved > START_BACK + 6.0:
				break
		_check(bool(pb.call("pole_broken_now", pi)), "a puppet car knocks the lamp down on this peer")
		_check(car.linear_velocity.length() < 0.01, "and nothing touched the puppet's own motion (v %.2f)" % car.linear_velocity.length())
		car.queue_free()
	else:
		_check(false, "a third lamp for the puppet case")

	print("RESULT: %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
