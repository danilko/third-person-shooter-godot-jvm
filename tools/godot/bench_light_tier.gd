extends SceneTree
## HOW MANY HOSTILES? The light combatant tier measured on the Steam Deck proxy (PLAN.md 2.3 / F8, R-9; docs/game-systems.md
## "The light combatant tier and the AI blackboard"). NEEDS A DISPLAY (the real renderer: the GPU half is the point).
##
##   ./gradlew build && godot --path . --script tools/godot/bench_light_tier.gd [-- --deck] [--cases=N:B,N:B,...]
##       [--seconds=15]
##
## DebugWorld, an invulnerable player standing still under its own third-person camera, its zones' AI cleared. Each
## case spawns N hunters (half gang_member -- guns and bats -- half fists as zombies) 40-60 m out with a full budget of
## B, lets them close for 5 s, then records every frame for `--seconds`: frame ms (CPU wall), GPU ms, the Deck proxy's
## deck_ms = max(cpu x cpu_factor, gpu x gpu_factor) (tools/godot/perf_budget.json), physics-process ms, draw calls,
## and how many are light / promoted. `full:N` is the control row: N full AICharacters (lightTier off), the cost the
## tier is there to avoid. Prints `BENCH <case> ...` lines and a table.

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const TIER := "res://src/main/java/com/openworld/ai/light/LightCombatants.java"

var world: Node
var player: CharacterBody3D
var tier: Node
var vp_rid: RID
var cfg := {"cpu_factor": 1.0, "gpu_factor": 1.0}
var args := {}

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _pct(a: Array, p: float) -> float:
	if a.is_empty():
		return 0.0
	var s := a.duplicate()
	s.sort()
	return float(s[clampi(int(p * (s.size() - 1)), 0, s.size() - 1)])

func _clear() -> void:
	tier.call("clear_now")
	for c in world.get_node("Characters").get_children():
		if c != player and c is CharacterBody3D:
			c.queue_free()
	await _tick(20)

func _case(label: String, n: int, budget: int, light: bool, seconds: float) -> String:
	await _clear()
	var home := player.global_position
	tier.call("tune_now", 400, budget, 15.0, 4, light)
	tier.call("horde_now", home, n / 2, 50.0, "gang_a", "gang_member", false)
	tier.call("horde_now", home, n - n / 2, 45.0, "gang_a", "", true)
	await _tick(300)
	var ft := []
	var gp := []
	var dk := []
	var ph := []
	var dc := []
	var t_prev := Time.get_ticks_usec()
	var t_end := t_prev + int(seconds * 1e6)
	while Time.get_ticks_usec() < t_end:
		await process_frame
		var t := Time.get_ticks_usec()
		var dt := (t - t_prev) / 1000.0
		t_prev = t
		var gpu := RenderingServer.viewport_get_measured_render_time_gpu(vp_rid)
		ft.append(dt)
		gp.append(gpu)
		dk.append(maxf(dt * float(cfg["cpu_factor"]), gpu * float(cfg["gpu_factor"])))
		ph.append(Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0)
		dc.append(RenderingServer.viewport_get_render_info(vp_rid, RenderingServer.VIEWPORT_RENDER_INFO_TYPE_VISIBLE,
				RenderingServer.VIEWPORT_RENDER_INFO_DRAW_CALLS_IN_FRAME))
	var st := String(tier.call("stats_now")).split(",")
	var chars := 0
	for c in get_nodes_in_group("characters"):
		if c is CharacterBody3D and c != player:
			chars += 1
	var line := "BENCH %-12s cpu p50 %6.2f p95 %6.2f | gpu p50 %5.2f p95 %5.2f | deck p50 %6.2f p95 %6.2f | phys p50 %5.2f | draws p95 %4d | light %s promoted %s bodies %d" % [
		label, _pct(ft, 0.5), _pct(ft, 0.95), _pct(gp, 0.5), _pct(gp, 0.95), _pct(dk, 0.5), _pct(dk, 0.95),
		_pct(ph, 0.5), int(_pct(dc, 0.95)), st[0], st[1], chars]
	print(line)
	return line

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=", true, 1)
		args[kv[0]] = kv[1] if kv.size() > 1 else true
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	Engine.max_fps = 0
	if args.has("deck"):
		cfg = JSON.parse_string(FileAccess.get_file_as_string("res://tools/godot/perf_budget.json"))
		var res: Array = cfg.get("resolution", [1280, 800])
		DisplayServer.window_set_size(Vector2i(int(res[0]), int(res[1])))
		print("DECK PROXY: %dx%d, cpu x%.1f, gpu x%.1f" % [int(res[0]), int(res[1]), float(cfg["cpu_factor"]), float(cfg["gpu_factor"])])
	world = (load(DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	await _tick(120)
	# QualitySettings applies the player's saved vsync when the game starts (settings.cfg): turn it off again, or every
	# frame reads 16.7 ms whatever it costs
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	Engine.max_fps = 0
	vp_rid = root.get_viewport_rid()
	RenderingServer.viewport_set_measure_render_time(vp_rid, true)
	player = world.get_node("Characters/Player")
	player.get_node("Health").set("invulnerable", true)
	tier = load(TIER).new()
	world.add_child(tier)
	await _tick(2)
	var seconds := float(args.get("seconds", "15"))
	var cases: String = args.get("cases", "0:12,40:12,80:12,160:12,80:8,80:16,full:12,full:24")
	var out := []
	for c in cases.split(","):
		var kv := c.split(":")
		if kv[0] == "full":
			out.append(await _case("full " + kv[1], int(kv[1]), 0, false, seconds))
		else:
			out.append(await _case("%s light b%s" % [kv[0], kv[1]], int(kv[0]), int(kv[1]), true, seconds))
	print("\n".join(out))
	quit(0)
