extends SceneTree
## THE FAR TRAFFIC TIER (PLAN.md R-10, `world.FarTraffic`): script-free cars on the lanes from the simulation ring
## (ZoneManager.traffic_sim_radius) out to `far_radius`, moved by the timetable-free lane rules, drawn as one MultiMesh
## per model. On a world with lanes beyond the ring:
##   1. the tier fills (some cars after 15 s);
##   2. every far car stands inside the ring [sim radius, far radius] round the camera;
##   3. they DRIVE (metres travelled grows);
##   4. they add NO node to the "characters" group and no body: the near tier is unchanged.
##   `-- --control` turns the tier off (`enabled` false): 0 cars, fails 1-3.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_far_traffic.gd [-- --world=island]

var fails := 0
var checks := 0

func _check(ok: bool, what: String) -> void:
	checks += 1
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var control := "--control" in args
	var path := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
	if "--world=island" in args:
		path = "res://src/main/resources/com/openworld/world/World.tscn"
	var w: Node = (load(path) as PackedScene).instantiate()
	root.add_child(w)
	current_scene = w
	await process_frame
	var zm := root.get_node("ZoneManager")
	var ft := zm.get_node_or_null("FarTraffic")
	if ft == null:
		print("RESULT: FAIL (no FarTraffic under ZoneManager)"); quit(2); return
	ft.set("enabled", not control)
	if not ("--world=island" in args):
		# DebugWorld is small: little of its road lies 350-650 m from the spawn, so the simulation ring is shrunk to
		# 100 m there (the island run keeps the shipped 300 m)
		zm.set("traffic_sim_radius", 100.0)
	var chars0 := -1
	for i in 60 * 15:
		await physics_frame
		if i == 60 * 5:
			chars0 = get_nodes_in_group("characters").size()
	var n: int = zm.call("far_traffic_cars_now")
	var t0: float = ft.call("travelled_now")
	for i in 60 * 3:
		await physics_frame
	var t1: float = ft.call("travelled_now")
	var rng := str(ft.call("range_now")).split("|")
	var sim: float = zm.get("traffic_sim_radius")
	var far: float = ft.get("far_radius")
	print("probe: %d far car(s), travelled %.0f m in 3 s, range %s (ring %.0f..%.0f)%s" % [n, t1 - t0, str(rng), sim, far,
			"  (CONTROL)" if control else ""])
	print("probe: diag %s" % str(ft.call("diag_now")))
	_check(n > 0, "the far tier fills")
	_check(rng.size() == 2 and float(rng[0]) >= sim - 15.0 and float(rng[1]) <= far + 35.0,
			"every far car is in the ring beyond the simulation radius")
	_check(t1 - t0 > 10.0 * maxf(1.0, n), "the far cars drive")
	_check(get_nodes_in_group("characters").size() <= chars0 + 10, "no body is added (characters %d -> %d)"
			% [chars0, get_nodes_in_group("characters").size()])
	print("RESULT: %s (%d of %d checks failed)" % ["PASS" if fails == 0 else "FAIL", fails, checks])
	quit(1 if fails else 0)
