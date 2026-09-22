extends SceneTree
## Where does the game FREEZE right after it starts? (user, 2026-09-22: "from the initial spawn point to 12-18-5 a
## sudden stuck/freeze for a while, then it loads up"). Loads World.tscn WITH A DISPLAY, does NOT settle, and walks
## the real Player from --from to --to at 6 m/s from the first frame, printing every frame over --slow ms with the
## time since start and the player's postal code. Run with ZM_TRACE=1 to see, interleaved, which streaming step ran
## in that frame.
##   ZM_TRACE=1 <godot> --path . --script tools/godot/probe_start_hitch.gd -- [--from=x,z] [--to=x,z] [--secs=40]
const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
var args := {}

func _arg(k: String, d = null):
	return args.get(k, d)

func _xz(s: String) -> Vector2:
	var p := s.split(",")
	return Vector2(float(p[0]), float(p[1]))

func _code(p: Vector3) -> String:
	var u := p.x + 2304.0
	var v := p.z + 2304.0
	return "%d-%d" % [clampi(int(floor(u / 192.0)) + 1, 1, 24), clampi(int(floor(v / 192.0)) + 1, 1, 24)]

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=")
		args[kv[0]] = kv[1] if kv.size() > 1 else true
	_run.call_deferred()

func _run() -> void:
	Engine.max_fps = 0
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	var w: Node = (load(WORLD) as PackedScene).instantiate()
	root.add_child(w)
	current_scene = w
	var player := w.get_node("Characters/Player") as Node3D
	var a := _xz(str(_arg("from", "-20,1180")))
	var b := _xz(str(_arg("to", "-96,1056")))
	var secs := float(_arg("secs", "40"))
	var slow := float(_arg("slow", "40"))
	var y := 1.0
	player.global_position = Vector3(a.x, player.global_position.y, a.y)
	var t0 := Time.get_ticks_usec()
	var prev := t0
	var worst := []
	var n := 0
	var over := 0
	while (Time.get_ticks_usec() - t0) / 1e6 < secs:
		await process_frame
		var t := Time.get_ticks_usec()
		var dt := (t - prev) / 1000.0
		prev = t
		var el := (t - t0) / 1e6
		n += 1
		var along := clampf((el - 3.0) * 6.0 / a.distance_to(b), 0.0, 1.0)   # 3 s standing, then walk
		var p := a.lerp(b, along)
		player.global_position = Vector3(p.x, player.global_position.y, p.y)
		if dt > slow:
			over += 1
			print("SLOW t=%6.2fs frame %7.1f ms at %s (%.0f, %.0f)" % [el, dt, _code(player.global_position), p.x, p.y])
			worst.append(dt)
	worst.sort()
	worst.reverse()
	print("RESULT %d frames, %d over %.0f ms, worst %s" % [n, over, slow, str(worst.slice(0, 8))])
	quit(0)
