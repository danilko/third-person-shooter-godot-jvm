extends SceneTree
## PLAN.md 0.16: how long has each level crossing (踏切) been CLOSED when a train reaches it? Sweeps a whole
## timetable cycle per crossing through TrainSystem.crossing_lead_now. A car that entered just before the
## crossing closed must still clear it: the shortest lead must beat that. Usage:
##   godot --headless --path . --script tools/godot/probe_lx_lead.gd [-- --world=island] [--min=<s>]
const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"

func _initialize() -> void:
	_run()

func _run() -> void:
	var island := false
	var need := 8.0
	for a in OS.get_cmdline_user_args():
		if a == "--world=island": island = true
		elif a.begins_with("--min="): need = float(a.substr(6))
	await process_frame
	var world: Node = (load(ISLAND if island else DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	var player: Node3D = world.get_node_or_null("Characters/Player")
	if player != null:
		player.process_mode = Node.PROCESS_MODE_DISABLED
	var tr: Node = root.get_node("TrainSystem")
	for i in 600:
		await physics_frame
		if tr.crossing_count_now() > 0 and tr.set_count_now() > 0: break
	var n: int = tr.crossing_count_now()
	print("[lx_lead] crossings ", n, " sets ", tr.set_count_now())
	var t0: float = tr.clock_now()
	var worst := INF
	var fails := 0
	for i in n:
		var info: PackedFloat64Array = tr.crossing_now(i)
		if info.size() == 0 or info[0] < 0: continue
		var period: float = tr.set_state_at(int(info[0]), t0)[8]
		var r: PackedFloat64Array = tr.crossing_lead_now(i, t0, t0 + period * 1.05, 0.05)
		if r.size() < 2 or is_nan(r[0]): continue
		worst = min(worst, r[0])
		var ok: bool = r[0] >= need
		if not ok: fails += 1
		print("  %s crossing %d at (%.0f, %.0f): closed %.1f s before the train (worst, t+%.0f s)"
				% ["PASS" if ok else "FAIL", i, info[2], info[4], r[0], r[1] - t0])
	print("RESULT %s worst lead %.1f s (need %.1f), %d short" % ["PASS" if fails == 0 else "FAIL", worst, need, fails])
	quit(1 if fails else 0)
