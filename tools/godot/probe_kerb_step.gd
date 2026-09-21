extends SceneTree
## PLAN.md 0.9 -- a character must be able to walk off the road onto the pavement (user, 2026-09-20:
## "the player will stuck on road after hijack, as seem not able to walk up to sidewalk").
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_kerb_step.gd
##       [-- --control]        step_height 0: the behaviour before MovementController.stepUpLedge existed
##       [-- --street=nishi_cho_530_R0 --at=-1175,530]
##
## A REAL walk on a REAL street of World.tscn: the player's own PlayerController reading the `forward`
## action, up the kerb the Road Kit built (measured: road top 0.600 m, footway top 0.750 m, so 0.15 m
## against MovementController.stepHeight 0.35). The walk direction is CALIBRATED, not assumed: the probe
## presses forward for a moment, measures which way the body actually went, and turns the view by the
## difference -- so it cannot pass or fail on a camera-convention mistake.
##
## Case 2 is the user's own path: take the car (the ordinary `use_carrier` seat request), get out again,
## then walk the same kerb. A step-up that works on foot and not after a seat is a state defect, and the
## two cases are the only way to tell that apart from a kerb that was never climbable.

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const VEHICLE := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const STREET_AT := Vector2(-1175, 530)     # a city street measured E-W, so its kerb is crossed in +-Z
const KERB_REACH := 14.0                   # how far to look across the road for the pavement edge
const WALK_SECONDS := 6.0
const CLIMB_MIN := 0.12                    # the pavement stands 0.15 m over the road
const STEP_LIMIT := 0.35                   # MovementController.stepHeight: past this the player cannot get up

var world: Node
var player: Node3D
var helper: Node
var checks := 0
var failures := 0

func _arg(name: String, def: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--%s=" % name):
			return a.substr(name.length() + 3)
		if a == "--%s" % name:
			return "1"
	return def

func _check(what: String, ok: bool, detail: String = "") -> void:
	checks += 1
	if not ok:
		failures += 1
	print("  %s  %s%s" % ["PASS" if ok else "FAIL", what, "" if detail == "" else "   (%s)" % detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

## The top collider a vertical ray meets at (x, z), as [name, height]; ["", NAN] for nothing.
func _top(x: float, z: float) -> Array:
	var space := player.get_world_3d().direct_space_state
	var rq := PhysicsRayQueryParameters3D.create(Vector3(x, 60.0, z), Vector3(x, -40.0, z), 0xFFFFFFFF)
	var hit := space.intersect_ray(rq)
	if hit.is_empty():
		return ["", NAN]
	return [str(hit["collider"].name), float(hit["position"].y)]

## Walk from `from` toward `dir` for WALK_SECONDS. Returns [y_start, y_end, metres travelled].
func _walk(from: Vector3, dir: Vector3) -> Array:
	player.global_position = from
	await _tick(20)                                    # settle onto the road before measuring
	var start := player.global_position
	# CALIBRATE: press forward briefly, see which way the body went, and turn the view by the difference.
	Input.action_press("forward")
	await _tick(18)
	var went := player.global_position - start
	Input.action_release("forward")
	var flat := Vector2(went.x, went.z)
	if flat.length() > 0.05:
		var want := Vector2(dir.x, dir.z).normalized()
		var turn := rad_to_deg(want.angle_to(flat))     # how far the walk is from where we want it
		helper.call("set_view", player, turn, 0.0)
	player.global_position = from
	await _tick(20)
	var y0 := player.global_position.y
	var p0 := player.global_position
	Input.action_press("forward")
	await _tick(int(WALK_SECONDS * 60))
	Input.action_release("forward")
	await _tick(10)
	var p1 := player.global_position
	return [y0, p1.y, Vector2(p1.x - p0.x, p1.z - p0.z).length()]

## SWEEP: every streamed lane near the player, sampled along its length, asking at each sample what a
## character walking off the road onto the pavement would MEET -- the first surface outboard of the kerb line
## and how far above the road it stands. Anything over `stepHeight` is a place the player cannot get up.
func _sweep(at: Vector2) -> void:
	var lanes := []
	for n in world.find_children("*", "Node", true, false):
		var sc = n.get_script()
		if sc != null and str(sc.resource_path).ends_with("PathLaneRoute.java") and n.has_node("Path3D"):
			lanes.append(n)
	print("  %d streamed lanes near (%.0f, %.0f)" % [lanes.size(), at.x, at.y])
	var worst := []
	var samples := 0
	var blocked := 0
	for lane in lanes:
		var path: Path3D = lane.get_node("Path3D")
		var c: Curve3D = path.curve
		var len_m := c.get_baked_length()
		var d := 4.0
		while d < len_m:
			var a := path.to_global(c.sample_baked(maxf(0.0, d - 0.5)))
			var b := path.to_global(c.sample_baked(minf(len_m, d + 0.5)))
			var mid := path.to_global(c.sample_baked(d))
			d += 12.0
			if Vector2(mid.x - at.x, mid.z - at.y).length() > 180.0:
				continue
			var dir := Vector3(b.x - a.x, 0, b.z - a.z).normalized()
			if dir.length() < 0.5:
				continue
			var right := Vector3(-dir.z, 0, dir.x)
			var road := _top(mid.x, mid.z)
			if road[0] == "" or not road[0].contains("_road"):
				continue
			samples += 1
			# walk outward both ways; the first surface that is NOT this road is what the player meets
			for sgn in [-1.0, 1.0]:
				var o := 1.0
				while o <= 11.0:
					var q: Vector3 = mid + right * sgn * o
					var t := _top(q.x, q.z)
					o += 0.5
					if t[0] == "" or t[0].contains("_road") or not is_finite(t[1]):
						continue
					var step: float = t[1] - float(road[1])
					# a DROP is the same complaint from the other side: a trench beside the road that a
					# character falls into and then cannot climb out of
					if step > STEP_LIMIT or step < -STEP_LIMIT:
						blocked += 1
						worst.append([absf(step), "%s %s" % [t[0], "UP" if step > 0.0 else "DOWN"], q])
					break
	worst.sort_custom(func(x, y): return x[0] > y[0])
	print("  %d road samples; %d edges taller than %.2f m" % [samples, blocked, STEP_LIMIT])
	for w in worst.slice(0, 12):
		print("    %.2f m  %-44s at (%.0f, %.1f, %.0f)" % [w[0], w[1], (w[2] as Vector3).x, (w[2] as Vector3).y,
			(w[2] as Vector3).z])
	_check("nothing beside a road is a step a character cannot take", blocked == 0,
		"%d of %d samples" % [blocked, samples])


func _initialize() -> void:
	var control := _arg("control", "") != ""
	world = (load(WORLD) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	player = world.get_node("Characters/Player")
	helper = load(HELPER).new()
	world.add_child(helper)
	var at := STREET_AT
	if _arg("at", "") != "":
		var xz := _arg("at", "").split(",")
		at = Vector2(float(xz[0]), float(xz[1]))
	player.global_position = Vector3(at.x, 30.0, at.y)
	print("probe: %s at (%.0f, %.0f)%s" % [WORLD.get_file(), at.x, at.y, "   CONTROL: step_height 0" if control else ""])

	# wait for the street's piece to stream in under the player
	var waited := 0
	while waited < 60 * 40:
		await _tick(10)
		waited += 10
		var t := _top(at.x, at.y)
		if t[0] != "" and t[0].contains("_road"):
			break
	var road := _top(at.x, at.y)
	print("  road under the player: %s at %.3f m after %.1f s" % [road[0], road[1], waited / 60.0])
	if road[0] == "":
		print("RESULT: FAIL (no road streamed at that point)")
		quit(2)
		return

	# find the pavement edge: march both ways across the street for the first *_walk* surface
	var edge := Vector3.ZERO
	var walk_y := NAN
	var dir := Vector3.ZERO
	for sign in [-1.0, 1.0]:
		var d := 0.5
		while d <= KERB_REACH:
			var z: float = at.y + sign * d
			var t := _top(at.x, z)
			if t[0].contains("_walk") and t[1] > road[1] + 0.05:
				edge = Vector3(at.x, t[1], z)
				walk_y = t[1]
				dir = Vector3(0, 0, sign)
				break
			d += 0.25
		if dir != Vector3.ZERO:
			break
	if dir == Vector3.ZERO:
		print("RESULT: FAIL (no pavement within %.0f m of the lane)" % KERB_REACH)
		quit(2)
		return
	var kerb: float = walk_y - road[1]
	print("  pavement %s at %.3f m, %.2f m %s of the start: a %.3f m kerb (stepHeight %s)"
		% [_top(edge.x, edge.z)[0], walk_y, absf(edge.z - at.y), "+Z" if dir.z > 0 else "-Z", kerb,
		str(player.get_node("MovementController").get("step_height"))])
	_check("the kerb is inside the step height", kerb <= float(player.get_node("MovementController").get("step_height")),
		"%.3f m" % kerb)

	if control:
		player.get_node("MovementController").set("step_height", 0.0)

	if _arg("sweep", "") != "":
		print("")
		print("=== sweep: what a character meets stepping off the road, all round this part of the city ===")
		await _sweep(at)
		print("")
		print("RESULT: %s (%d/%d)" % ["PASS" if failures == 0 else "FAIL (%d failures)" % failures,
			checks - failures, checks])
		quit(1 if failures else 0)
		return

	# --- 1. on foot: walk off the road, up the kerb, onto the pavement
	print("")
	print("=== 1. a plain walk up the kerb ===")
	var start := Vector3(edge.x, road[1] + 1.0, edge.z - dir.z * 2.5)
	var r: Array = await _walk(start, dir)
	print("  walked %.2f m, y %.3f -> %.3f" % [r[2], r[0], r[1]])
	_check("the player walked onto the pavement", r[1] - r[0] >= CLIMB_MIN and r[2] >= 1.5,
		"rose %.3f m over %.2f m" % [r[1] - r[0], r[2]])

	# --- 2. the user's path: take a car, get out, then walk the same kerb
	print("")
	print("=== 2. the same kerb after taking and leaving a car ===")
	var car := (load(VEHICLE) as PackedScene).instantiate()
	world.add_child(car)
	car.global_position = Vector3(edge.x + 6.0, road[1] + 1.0, edge.z - dir.z * 3.0)
	await _tick(30)
	player.global_position = car.global_position + Vector3(2.0, 0.0, 0.0)
	await _tick(20)
	Input.action_press("use_carrier")
	await _tick(6)
	Input.action_release("use_carrier")
	await _tick(60)
	var seated: bool = player.get("current_vehicle_node") != null
	_check("the player took the car", seated, str(player.get("current_vehicle_node")))
	Input.action_press("use_carrier")
	await _tick(6)
	Input.action_release("use_carrier")
	await _tick(60)
	_check("the player got out again", player.get("current_vehicle_node") == null)
	var r2: Array = await _walk(start, dir)
	print("  walked %.2f m, y %.3f -> %.3f" % [r2[2], r2[0], r2[1]])
	_check("the player walked onto the pavement after the car", r2[1] - r2[0] >= CLIMB_MIN and r2[2] >= 1.5,
		"rose %.3f m over %.2f m" % [r2[1] - r2[0], r2[2]])

	print("")
	print("RESULT: %s (%d/%d)" % ["PASS" if failures == 0 else "FAIL (%d failures)" % failures,
		checks - failures, checks])
	quit(1 if failures else 0)
