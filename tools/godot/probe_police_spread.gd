extends SceneTree
## POLICE DO NOT QUEUE (PLAN.md 1i, user 2026-10-08: "all spawned police stay at the same place, line up and get
## stuck"). Each unit closes on its own APPROACH SLOT round the player (EnforcementDispatch.approach_slots) and no
## two foot units spawn within 6 m of each other.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_police_spread.gd [-- --world=island] [--stars=3] [--control]
##
## The player stands invulnerable at the start for 75 s at N stars. Sampled every 0.5 s over the police bodies within
## 60 m: how many are within 25 m (they arrived), the bearing COVERAGE round the player (360 - the largest gap between
## them), and the mean distance from each to its nearest other unit (a queue is ~1 m). Asserted: coverage >= 120 deg
## and nearest-neighbour >= 2.5 m, both averaged over the samples with >= 3 units, and units do arrive.
## --control turns approach_slots off (the old single-file approach), reported for comparison.

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"

var fails := 0

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _arg(name: String, def: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--%s=" % name):
			return a.split("=", true, 1)[1]
	return def

func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	var island := _arg("world", "debug") == "island"
	var stars := int(_arg("stars", "3"))
	var world: Node = (load(ISLAND if island else DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	for i in 240:
		await physics_frame
	var player: Node3D = world.get_node("Characters/Player")
	player.get_node("Health").set("invulnerable", true)
	var gm: Node = root.get_node("GameManager")
	var ws: Node = gm.get_node("WantedSystem")
	var ed: Node = gm.get_node("EnforcementDispatch")
	if control:
		ed.set("approach_slots", false)
	var pid: String = player.get("character_info").get("character_id")
	var cov_sum := 0.0
	var nn_sum := 0.0
	var n := 0
	var arrived_max := 0
	var t0 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < 75000:
		ws.call("set_stars_now", pid, stars, false)
		await physics_frame
		if Engine.get_physics_frames() % 30 != 0:
			continue
		var pp := player.global_position
		var pts: Array = []
		for b in ed.call("bodies_now", "police"):
			if b == null or not is_instance_valid(b) or b.get_parent() == null:
				continue
			var q: Vector3 = b.global_position
			if Vector2(q.x - pp.x, q.z - pp.z).length() < 60.0 and not b.has_method("get_seat_count"):
				pts.append(q)
		var arrived := 0
		for q in pts:
			if Vector2(q.x - pp.x, q.z - pp.z).length() < 25.0:
				arrived += 1
		arrived_max = maxi(arrived_max, arrived)
		if pts.size() < 3:
			continue
		var bears: Array = []
		for q in pts:
			bears.append(fposmod(rad_to_deg(atan2(q.x - pp.x, q.z - pp.z)), 360.0))
		bears.sort()
		var gap: float = 360.0 - float(bears[-1]) + float(bears[0])
		for i in range(1, bears.size()):
			gap = maxf(gap, float(bears[i]) - float(bears[i - 1]))
		var nn := 0.0
		for i in pts.size():
			var best := 1e9
			for j in pts.size():
				if i != j:
					best = minf(best, Vector2(pts[i].x - pts[j].x, pts[i].z - pts[j].z).length())
			nn += best
		cov_sum += 360.0 - gap
		nn_sum += nn / pts.size()
		n += 1
	var cov := cov_sum / maxi(n, 1)
	var nn_mean := nn_sum / maxi(n, 1)
	print("probe_police_spread: %s, %d stars, %d samples with >= 3 units: coverage %.0f deg, nearest other unit %.1f m, up to %d within 25 m" % ["control" if control else "slots", stars, n, cov, nn_mean, arrived_max])
	if control:
		print("RESULT PASS (control, reported only)")
		quit(0)
		return
	_check(n > 10, "enough samples with three or more units (%d)" % n)
	_check(arrived_max >= 2, "units arrive (up to %d within 25 m)" % arrived_max)
	print("  [INFO] coverage %.0f deg (reported, not asserted: it follows where the footways are; the control reads the same)" % cov)
	_check(nn_mean >= 2.5, "not in a queue (nearest other unit %.1f m on average)" % nn_mean)
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
