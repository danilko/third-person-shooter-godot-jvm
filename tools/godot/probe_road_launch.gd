extends SceneTree
## PLAN.md 0.1 -- a car at speed on a Road Kit road must not be thrown into the air.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_road_launch.gd
##       (the gate: GATE_CASES)   or   -- --lane=link_R1 --speed=35 --offset=-3 --seconds=15   (one case)
##       -- --world=res://src/main/resources/com/openworld/world/World.tscn --lane=shrine_touge_F0 ...   (another scene)
##       -- ... --corner-accel=0   (a single case drives with the traffic brain's own corner governor unless told
##       otherwise; GATE_CASES turn it off, because they exist to reach the parapets at speed)
##       -- ... --park=x,z   put the (disabled) streaming player over (x, z) instead of PARK
##       -- ... --see-obstacles=1   let the brain BRAKE for other cars (it is blind by default): 0.7 cause 1 is
##       rear-ending ambient traffic at 45 m/s, which masks the road defects underneath it
##       -- ... --follow=1   keep the streaming player 400 m over the car, for a drive longer than one zone
##       -- ... --wheel-sensor=1   drive with the sphere ground sensor (2 = tyre cylinder, 0 = the shipped rays);
##       the review measured all three equal in cost and sphere/cylinder 15x smoother over a kerb, so this is how
##       a kerb strike at speed is compared between them (PLAN.md 0.7)
##       -- ... --phys=120   run the physics at 120 Hz instead of the project's 60 (PLAN.md 0.7: is a launch the
##       solver running out of steps at speed? compare the same case at 60 and 120 -- half the travel per step)
##       A FALL (the car metres below the lane it is on: through or over a wall, off a deck edge) counts like a launch;
##       drive with --offset beside a barrier (e.g. +7 on a 2-lane ramp) to test a wall at speed.
##
## It also counts what a car MEETS on the way (PLAN.md 0.8): every body contact with a street pole, and every pole
## knocked down (`BreakableProps.breaksTotalNow`, summed over the scene -- at speed a pole is knocked down BEFORE
## the contact, so the knock-down is the number, not the contact). A drive down a lane centre must report 0 of both.
##
## Runs the real DebugWorld with its two streamed Road Kit pieces, puts one Vehicle.tscn on a named lane
## with LaneDriveProbeController (the ordinary traffic brain, aimable by name, blind to other cars,
## optionally riding `offset` metres right of the lane -- beside the kerb/barrier on purpose) and drives
## it at `speed` m/s through the lane chain. Every physics tick it watches the body's vertical velocity;
## a LAUNCH is the body's vertical velocity RELATIVE TO THE ROAD (the lane's own rise rate removed, so a
## grade or a sag does not count) rising more than RISE_DV within WINDOW ticks while the car is on the road. Each launch is printed with
## what produced it: every body contact (collider, point, normal, impulse) and every wheel ray's hit.

const WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const VEHICLE := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
const CTRL := "res://src/main/java/com/openworld/debug/LaneDriveProbeController.java"
const VEHICLE_CFG := "res://src/main/resources/com/openworld/vehicle/SPC1Config.tres"
const TRACE_DV := 0.6            # a tick gaining this much upward velocity is printed with its contacts
const RISE_DV := 3.0             # a LAUNCH: vertical velocity rising this much within WINDOW ticks
const WINDOW := 15
const SETTLE_TICKS := 30         # the suspension settling onto the road after a spawn is not a launch
const ON_ROAD_M := 8.0          # a lane centre +-8 m is still carriageway/kerb/footway on DebugRoads
const PARK := Vector3(10, 400, 10)   # keeps both DebugRoads zones inside their load radius

var world: Node
var player: Node3D
var car: RigidBody3D
var ctrl: Node
var HZ := 60.0     # the live physics rate (--phys); every printed time and rate is in it

func _arg(name: String, def: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--%s=" % name):
			return a.substr(name.length() + 3)
	return def

func _lane(name: String) -> Node:
	for n in world.find_children(name, "Node", true, false):
		var s = n.get_script()
		if s != null and str(s.resource_path).ends_with("PathLaneRoute.java"):
			return n
	return null

## [signed XZ distance of `p` to the RIGHT of lane `ln`'s centreline, the lane's height there] -- [INF, NAN]
## when the lane is not streamed. The lane's height is the road's own vertical profile, which is what lets a
## launch be told apart from a grade: a car following the road rises exactly as fast as the lane does.
func _lane_offset(ln: String, p: Vector3) -> Array:
	var lane := _lane(ln) if ln != "" else null
	if lane == null:
		return [INF, NAN]
	var path: Path3D = lane.get_node("Path3D")
	var c: Curve3D = path.curve
	var off := c.get_closest_offset(path.to_local(p))
	var a := path.to_global(c.sample_baked(maxf(0.0, off - 0.5)))
	var b := path.to_global(c.sample_baked(minf(c.get_baked_length(), off + 0.5)))
	var at := path.to_global(c.sample_baked(off))
	var dir := Vector3(b.x - a.x, 0, b.z - a.z).normalized()
	var right := Vector3(-dir.z, 0, dir.x)
	return [Vector3(p.x - at.x, 0, p.z - at.z).dot(right), at.y]

func _name_of(o: Object) -> String:
	if o == null:
		return "<none>"
	if o is Node:
		var n: Node = o
		var p := n.get_parent()
		return "%s/%s" % [p.name if p != null else "", n.name]
	return str(o)

## One traced tick: body contacts (collider, normal, impulse) and each wheel's ray. Returns the colliders.
func _trace(f: int, vy: float, dv: float, ln: String, lat: float, p: Vector3) -> Dictionary:
	var e := car.global_basis.get_euler()
	var line := "    t=%.2f vy %+.2f (%+.2f)  %.1f m/s  lat %+.2f  roll %+.1f pitch %+.1f  y %.2f |" % [f / HZ, vy, dv,
			car.linear_velocity.length(), lat, rad_to_deg(e.z), rad_to_deg(e.x), p.y]
	var st := PhysicsServer3D.body_get_direct_state(car.get_rid())
	var causes := {}
	for i in range(st.get_contact_count()):
		var who := _name_of(st.get_contact_collider_object(i))
		var j := st.get_contact_impulse(i).length()
		if j < 1.0:
			continue
		causes[who] = true
		var n := st.get_contact_local_normal(i)
		var cp := st.get_contact_collider_position(i)
		line += " [%s J%.0f n(%.2f,%.2f,%.2f) @(%.1f,%.2f,%.1f)]" % [who.get_file(), j, n.x, n.y, n.z, cp.x, cp.y, cp.z]
	line += " | wheels"
	for w in car.get_node("Wheels").get_children():
		var r: RayCast3D = w
		if r.is_colliding():
			line += " %s:%s %.2f@%.2f" % [r.name, _name_of(r.get_collider()).get_file().left(14), r.global_position.distance_to(r.get_collision_point()), r.get_collision_point().y]
		else:
			line += " %s:-" % r.name
	print(line)
	return causes

## Every BreakableProps node in the scene -- the street poles (PLAN.md 3.11). Re-found each case because
## zones stream in and out.
func _pole_nodes() -> Array:
	var out: Array = []
	for n in world.find_children("Breakable_*", "MultiMeshInstance3D", true, false):
		if n.has_method("breaks_total_now"):
			out.append(n)
	return out

func _breaks_total() -> int:
	var t := 0
	for n in _pole_nodes():
		t += int(n.call("breaks_total_now"))
	return t


func _spawn(lane_name: String, speed: float, offset: float, corner_accel: float = -1.0) -> bool:
	var lane := _lane(lane_name)
	if lane == null:
		return false
	var path: Path3D = lane.get_node("Path3D")
	var c: Curve3D = path.curve
	var at := path.to_global(c.sample_baked(6.0))
	var ahead := path.to_global(c.sample_baked(10.0))
	var dir := Vector3(ahead.x - at.x, 0, ahead.z - at.z).normalized()
	if car != null and is_instance_valid(car):
		car.queue_free()
	car = (load(VEHICLE) as PackedScene).instantiate()
	ctrl = load(CTRL).new()
	ctrl.set("cruise_speed", speed)
	ctrl.set("cruise_throttle", 1.0)
	ctrl.set("junction_throttle_scale", 1.0)
	ctrl.set("turn_slowdown", 0.3)
	# The edge cases mean "the car's OUTER WHEELS on the kerb line", and -3 m was that for the prototype's wheels at
	# +-1.1 m. A narrower track needs the same wheels-on-the-kerb line, not the same number: at -3 m SPC-1 (wheels at
	# +-0.82) was spawned 0.28 m further out, its body already in the kerb, and read that as launches and falls.
	if absf(offset) >= 3.0:
		var track_half := absf((car.get_node("Wheels/FL") as Node3D).position.x)
		offset += signf(offset) * (track_half - PROTOTYPE_TRACK_HALF)
	ctrl.set("lateral_offset", offset)
	if corner_accel >= 0.0:
		ctrl.set("corner_lateral_accel", corner_accel)
	# Normally blind to other cars, so a launch run is not spoiled by traffic it did not mean to measure --
	# but rear-ending an ambient car IS one of 0.7's causes, and it masks the rest, so it can be switched on.
	if _arg("see-obstacles", "") != "":
		ctrl.set("see_obstacles", _arg("see-obstacles", "0") != "0")
	car.add_child(ctrl)
	world.add_child(car)
	car.global_position = at + Vector3(0, 0.8, 0) + dir.cross(Vector3.UP) * offset
	car.look_at(car.global_position + dir, Vector3.UP)
	# Start at the target speed: a launch run-up would spend half the lane accelerating.
	car.linear_velocity = dir * speed
	return bool(ctrl.call("drive_lane", lane_name))

## The gate (PLAN.md 0.1): each case drives one lane at speed, some deliberately on the edge line where a
## parapet begins (`offset` -3 m on the bridge's `link` lanes -- the car's outer wheels on the kerb line).
## Control: the pieces built before `point_edges.step_walls` launch on both edge cases every lap.
const PROTOTYPE_TRACK_HALF := 1.1     # the wheel track the edge offsets were written for

const GATE_CASES := [
	["link_F1", 35.0, -3.0, 6.0], ["link_R1", 35.0, -3.0, 6.0],
	["link_F1", 35.0, 0.0, 8.0], ["link_R1", 35.0, 3.0, 6.0],
	["east_R1", 35.0, 3.0, 8.0], ["east_R1", 35.0, -3.0, 8.0],
]

func _initialize() -> void:
	if _arg("wheel-sensor", "") != "":
		# The config is a shared .tres, loaded from the resource cache, so writing it here reaches every car
		# built afterwards -- which is what a sensor comparison wants. It must happen BEFORE any car enters
		# the tree (VehicleWheel._ready builds its probe there), and it cannot be done through the car node:
		# a godot-jvm @Export resource reads as null while its node is off-tree.
		var cfg := load(VEHICLE_CFG)
		cfg.set("wheel_sensor", int(_arg("wheel-sensor", "0")))
		print("probe: wheel sensor %s (0 rays, 1 sphere, 2 tyre cylinder)" % str(cfg.get("wheel_sensor")))
	if _arg("phys", "") != "":
		Engine.physics_ticks_per_second = int(_arg("phys", "60"))
		HZ = float(Engine.physics_ticks_per_second)
		print("probe: physics at %d Hz" % Engine.physics_ticks_per_second)
	world = (load(_arg("world", WORLD)) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	player = world.get_node("Characters/Player")
	player.process_mode = Node.PROCESS_MODE_DISABLED
	player.global_position = PARK
	if _arg("park", "") != "":
		var xz := _arg("park", "").split(",")
		player.global_position = Vector3(float(xz[0]), 400.0, float(xz[1]))
	var cases: Array = GATE_CASES
	if _arg("lane", "") != "":
		cases = [[_arg("lane", ""), float(_arg("speed", "35")), float(_arg("offset", "0")), float(_arg("seconds", "15")),
				float(_arg("corner-accel", "-1"))]]
	var total := 0
	var failed := []
	for c in cases:
		var n: int = await _case(c[0], c[1], c[2], c[3], c[4] if c.size() > 4 else 0.0)
		if n < 0:
			print("RESULT: FAIL (lane %s never streamed in)" % c[0])
			quit(2)
			return
		total += n
		if n > 0:
			failed.append("%s@%+.0f" % [c[0], c[2]])
	print("=== %d launches on the road over %d cases %s" % [total, cases.size(), failed])
	print("RESULT: %s" % ["PASS" if total == 0 else "FAIL"])
	quit(0 if total == 0 else 1)

func _case(lane_name: String, speed: float, offset: float, seconds: float, corner_accel: float) -> int:
	var waited := 0
	while _lane(lane_name) == null and waited < 60 * 30:
		await physics_frame
		waited += 1
	if not _spawn(lane_name, speed, offset, corner_accel):
		return -1
	print("probe: %s at %.0f m/s, offset %.1f m, corner governor %s, streamed after %.1f s" % [lane_name, speed, offset,
			str(ctrl.get("corner_lateral_accel")) + " m/s2", waited / 60.0])

	var prev_vy := 0.0
	var pole_hits := 0
	var breaks0 := _breaks_total()
	var prev_breaks := breaks0
	var launches := 0
	var off_road_launches := 0
	var worst_lat := 0.0
	var by_cause := {}
	var max_rise := 0.0
	var respawns := 0
	var falls := 0
	var last_lane := ""
	var dist := 0.0
	var last_pos := car.global_position
	var prev_lane := ""
	var prev_lane_y := NAN
	var hist: Array = []          # [vy, causes] per tick, last WINDOW ticks
	var cooldown := 0
	var hz := HZ
	for f in range(int(seconds * hz)):
		await physics_frame
		if not is_instance_valid(car):
			break
		var p := car.global_position
		if _arg("follow", "") != "":
			# the streaming player rides 400 m over the car, so a long drive (the island's expressway) stays streamed
			player.global_position = Vector3(p.x, 400.0, p.z)
		dist += Vector2(p.x - last_pos.x, p.z - last_pos.z).length()
		last_pos = p
		var ln := str(ctrl.call("current_lane_name"))
		var lo_res := _lane_offset(ln, p)
		var lat: float = lo_res[0]
		var lane_y: float = lo_res[1]
		# Vertical velocity RELATIVE TO THE ROAD: the lane's own rise rate is removed, so a grade or a sag
		# is not a launch. A lane change (junction) resets the reference.
		var road_vy := 0.0
		if ln == prev_lane and is_finite(lane_y) and is_finite(prev_lane_y):
			road_vy = (lane_y - prev_lane_y) * hz
		prev_lane = ln
		prev_lane_y = lane_y
		var on_road := is_finite(lat) and absf(lat) <= ON_ROAD_M
		if is_finite(lat):
			worst_lat = maxf(worst_lat, absf(lat))
		if ln != last_lane:
			print("  t=%5.1f  lane %s  speed %.1f m/s  at (%.1f, %.1f, %.1f)" % [f / HZ, ln, car.linear_velocity.length(), p.x, p.y, p.z])
			last_lane = ln
		# PLAN.md 0.8: what the car MEETS. A pole at or above break_speed is knocked down before the contact
		# happens, so the knock-down is what a fast drive shows and the contact what a slow one shows.
		var breaks := _breaks_total()
		if breaks != prev_breaks:
			print("  POLE t=%5.1f  %d knocked down  speed %.1f m/s  lane %s  %.2f m right of it  at (%.0f, %.0f, %.0f)"
					% [f / HZ, breaks - prev_breaks, car.linear_velocity.length(), ln, lat, p.x, p.y, p.z])
			prev_breaks = breaks
		var cst := PhysicsServer3D.body_get_direct_state(car.get_rid())
		for i in range(cst.get_contact_count()):
			if not _name_of(cst.get_contact_collider_object(i)).contains("Breakable_"):
				continue
			pole_hits += 1
			print("  POLE HIT t=%5.1f  speed %.1f m/s  lane %s  %.2f m right of it  at (%.0f, %.0f, %.0f)"
					% [f / HZ, car.linear_velocity.length(), ln, lat, p.x, p.y, p.z])
			break
		var vy := car.linear_velocity.y - road_vy
		var dv := vy - prev_vy
		prev_vy = vy
		var causes := {}
		if dv > TRACE_DV:
			causes = _trace(f, vy, dv, ln, lat, p)
		hist.append([vy, causes])
		if hist.size() > int(WINDOW * hz / 60.0):
			hist.pop_front()
		var lo := INF
		for h in hist:
			lo = minf(lo, h[0])
		var rise := vy - lo
		if on_road:
			max_rise = maxf(max_rise, rise)
		cooldown -= 1
		if rise > RISE_DV and cooldown <= 0 and f > SETTLE_TICKS * hz / 60.0:
			cooldown = int(WINDOW * hz / 60.0)
			var why := {}
			for h in hist:
				for k in h[1]:
					why[k] = true
			if why.is_empty():
				why["<wheel forces only>"] = true
			if on_road:
				launches += 1
				for k in why:
					by_cause[k] = int(by_cause.get(k, 0)) + 1
			else:
				off_road_launches += 1
			print("  %s t=%.2f  vy rose %.2f m/s in %.2f s  speed %.1f  lane %s  %.2f m right of it  at (%.0f, %.0f, %.0f)  from: %s"
					% ["LAUNCH" if on_road else "off-road bounce", f / HZ, rise, WINDOW / 60.0,
					car.linear_velocity.length(), ln, lat, p.x, p.y, p.z, ", ".join(why.keys())])
		# A FALL: the car is metres below the lane it is on (through or over a wall, off a deck edge). On an elevated
		# road that is the defect the wall test (--offset beside a barrier) exists to find.
		if f > hz and is_finite(lane_y) and p.y < lane_y - 3.0 and not (is_finite(lat) and absf(lat) > 25.0):
			falls += 1
			print("  FELL t=%.1f  %.1f m below lane %s, %.2f m right of it, at (%.0f, %.0f, %.0f), %.1f m/s" % [f / HZ,
					lane_y - p.y, ln, lat, p.x, p.y, p.z, car.linear_velocity.length()])
			respawns += 1
			if respawns > 2 or not _spawn(lane_name, speed, offset, corner_accel):
				break
			prev_vy = 0.0
			hist.clear()
			prev_lane = ""
			last_lane = ""
			last_pos = car.global_position
			continue
		if f > hz and (p.y < -30.0 or (is_finite(lat) and absf(lat) > 25.0)):
			respawns += 1
			print("  t=%.1f car off the network (y %.1f, lane '%s', %.1f m right of it) -- respawning" % [f / HZ, p.y, ln, lat])
			if respawns > 2 or not _spawn(lane_name, speed, offset, corner_accel):
				break
			prev_vy = 0.0
			hist.clear()
			prev_lane = ""
			last_lane = ""
			last_pos = car.global_position
	if is_instance_valid(car):
		car.queue_free()
		car = null
	var broke := _breaks_total() - breaks0
	print("--- %s at %.0f m/s, offset %+.1f m: drove %.0f m, %d launches on the road (vy +%.1f m/s within %.2f s), %d more off it, worst on-road rise %.2f m/s, worst lateral %.1f m, %d falls, %d respawns, %d poles knocked down, %d pole contacts"
			% [lane_name, speed, offset, dist, launches, RISE_DV, WINDOW / 60.0, off_road_launches, max_rise, worst_lat, falls, respawns, broke, pole_hits])
	for k in by_cause:
		print("    %3d  %s" % [by_cause[k], k])
	return launches + falls
