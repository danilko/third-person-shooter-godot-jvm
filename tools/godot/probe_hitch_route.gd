extends SceneTree
## WHAT causes a freeze while walking or driving? (user, 2026-09-28: "2-3 blocks of walk/drive still freeze").
## Loads World.tscn WITH A DISPLAY, settles `--settle` s at the start, then moves the real Player along the
## polyline `--path=x,z;x,z;...` at `--speed` m/s, printing every frame over `--slow` ms as a `HITCH` line with the
## engine time (ms since start), so it can be lined up with the interleaved log: ZoneManager's own lines (spawn,
## reclaim, load), `ZM_TRACE=1` streaming steps, and a JVM GC log taken with
##   JAVA_TOOL_OPTIONS="-Xlog:gc:file=<f>:uptimemillis"
## Each HITCH line also carries what changed that frame: characters in the tree, vehicles, nodes, objects.
##   <godot> --path . --script tools/godot/probe_hitch_route.gd -- --path=80,-100;1150,-100 [--speed=6] [--slow=33]
const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
var args := {}

func _arg(k: String, d = null):
	return args.get(k, d)

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=")
		args[kv[0]] = kv[1] if kv.size() > 1 else true
	_run.call_deferred()

func _count(group: String) -> int:
	return get_nodes_in_group(group).size()

func _run() -> void:
	Engine.max_fps = 0
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	var w: Node = (load(WORLD) as PackedScene).instantiate()
	root.add_child(w)
	current_scene = w
	var player := w.get_node("Characters/Player") as Node3D
	player.get_node("Health").set("max_health", 1000000.0)
	var pts: Array[Vector2] = []
	for s in str(_arg("path", "80,-100;1150,-100")).split(";"):
		var p := s.split(",")
		pts.append(Vector2(float(p[0]), float(p[1])))
	var speed := float(_arg("speed", "6"))
	var slow := float(_arg("slow", "33"))
	var settle := float(_arg("settle", "15"))
	var fly := float(_arg("y", "-1"))
	player.global_position = Vector3(pts[0].x, player.global_position.y if fly < 0 else fly, pts[0].y)
	var t0 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < settle * 1000.0:
		player.global_position = Vector3(pts[0].x, player.global_position.y if fly < 0 else fly, pts[0].y)
		await process_frame
	print("ROUTE_START t=%d" % Time.get_ticks_msec())
	var seg := 0
	var along := 0.0
	var prev := Time.get_ticks_usec()
	var n := 0
	var worst := []
	var ft := []
	var chars_prev := _count("characters")
	var obj_prev := int(Performance.get_monitor(Performance.OBJECT_COUNT))
	while seg < pts.size() - 1:
		await process_frame
		var t := Time.get_ticks_usec()
		var dt := (t - prev) / 1000.0
		prev = t
		n += 1
		ft.append(dt)
		along += speed * minf(dt, 100.0) / 1000.0
		var len := pts[seg].distance_to(pts[seg + 1])
		while along > len and seg < pts.size() - 1:
			along -= len
			seg += 1
			if seg < pts.size() - 1:
				len = pts[seg].distance_to(pts[seg + 1])
		if seg >= pts.size() - 1:
			break
		var p := pts[seg].lerp(pts[seg + 1], along / len)
		player.global_position = Vector3(p.x, player.global_position.y if fly < 0 else fly, p.y)
		var chars := _count("characters")
		var objs := int(Performance.get_monitor(Performance.OBJECT_COUNT))
		if dt > slow:
			worst.append(dt)
			print("HITCH t=%d frame %.1f ms at (%.0f,%.0f) chars %d (%+d) objects %d (%+d) nodes %d" % [Time.get_ticks_msec(), dt,
					p.x, p.y, chars, chars - chars_prev, objs, objs - obj_prev, int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT))])
		chars_prev = chars
		obj_prev = objs
	worst.sort()
	worst.reverse()
	ft.sort()
	print("RESULT %d frames, p50 %.2f p99 %.2f, %d over %.0f ms, worst %s" % [n, ft[n / 2], ft[int(n * 0.99)], worst.size(), slow,
			str(worst.slice(0, 12))])
	quit(0)
