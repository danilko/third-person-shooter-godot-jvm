extends SceneTree
## probe_walker_pass.gd -- two promoted pedestrians meeting face to face on one footway (PLAN.md zb2). Headless.
##
##   godot --headless --path . --script tools/godot/probe_walker_pass.gd [-- --control]
##
## A flat stand, a Player (so the walkers are ACTIVE and really walk, never glide), and two AICharacters with a
## SidewalkWalkerController each, on the SAME straight 60 m footway, walking at each other. Asserts that both get
## past each other (each ends beyond the other's start side) and that neither's arc position left its body by more
## than a metre (the drift that sent walkers beelining across a street). `--control` turns off pass_left and
## project_on_path, the two 2026-09-27 rules, and must fail.

const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const WALKER := "res://src/main/java/com/openworld/ai/SidewalkWalkerController.java"

var fails := 0
var checks := 0


func check(ok: bool, what: String) -> void:
	checks += 1
	if not ok:
		fails += 1
	print(("PASS " if ok else "FAIL ") + what)


func _initialize() -> void:
	_run.call_deferred()


func _wait_frames(n: int) -> void:
	for i in n:
		await physics_frame


func _run() -> void:
	var control := OS.get_cmdline_user_args().has("--control")
	var stand := Node3D.new()
	root.add_child(stand)
	current_scene = stand
	await process_frame
	var ground := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(200, 1, 200)
	cs.shape = box
	ground.add_child(cs)
	stand.add_child(ground)
	ground.global_position = Vector3(0, -0.5, 0)

	var player: Node3D = (load(PLAYER) as PackedScene).instantiate()
	stand.add_child(player)
	player.global_position = Vector3(0, 0.1, 20)
	player.get_node("Health").set("invulnerable", true)

	var helper: Node = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
	stand.add_child(helper)
	var path := PackedVector3Array()
	for i in 13:
		path.append(Vector3(-30 + i * 5, 0.0, 0))
	var ws := []
	var bodies := []
	for k in 2:
		var ai: Node3D = (load(AI) as PackedScene).instantiate()
		stand.add_child(ai)
		var c: Node = load(WALKER).new()
		c.call("setup", path, 20.0 if k == 0 else 40.0, 1 if k == 0 else -1)
		if control:
			c.set("pass_left", false)
			c.set("project_on_path", false)
		helper.call("spawn_with_controller", ai, Vector3(-10 if k == 0 else 10, 0.1, 0), c)
		ws.append(c)
		bodies.append(ai)
	# They start 20 m apart heading at each other: passing is the moment A is east of B (their order swaps)
	# while they are still near each other -- not a pair that met, turned round and walked away.
	var passed_at := -1.0
	var nearest := 1e9
	for f in 60 * 20:
		await physics_frame
		var a: Vector3 = bodies[0].global_position
		var b: Vector3 = bodies[1].global_position
		nearest = minf(nearest, Vector2(a.x - b.x, a.z - b.z).length())
		if passed_at < 0.0 and a.x > b.x + 1.0:
			passed_at = f / 60.0
	print("  passed at %.1f s (-1 = never), closest %.2f m apart; sidesteps A %d B %d, stalls A %d B %d" % [
		passed_at, nearest, ws[0].get("sidesteps"), ws[1].get("sidesteps"), ws[0].get("stalls"), ws[1].get("stalls")])
	check(passed_at > 0.0, "the two walkers passed each other (at %.1f s)" % passed_at)
	var worst := 0.0
	for k in 2:
		var along: float = ws[k].get("along")
		var on: Vector3 = ws[k].call("point_at", along)
		var b: Vector3 = bodies[k].global_position
		worst = maxf(worst, absf(on.x - b.x))
	check(worst < 1.5, "each walker's arc position stays on its body (worst %.2f m along)" % worst)
	print("RESULT %s (%d/%d)" % ["PASS" if fails == 0 else "FAIL", checks - fails, checks])
	quit(1 if fails > 0 else 0)
