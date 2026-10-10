extends SceneTree
## The debug console in the REAL game (user, 2026-10-10): backtick opens the command line in World.tscn -- which has
## no DebugHarness (no F-key spawns there, user 2026-10-09) -- and its `traffic` / `activity` / `hud` commands answer.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_console.gd -- --no-warmup
##
## `-- --control` runs on the title screen instead: there is no world, and the key must open nothing.

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
var fails := 0

func check(label: String, ok: bool, detail := "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", label, detail])

func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	var gm: Node = root.get_node("GameManager")
	if not control:
		var w: Node = (load(WORLD) as PackedScene).instantiate()
		root.add_child(w)
		current_scene = w
	for i in 120:
		await physics_frame
	if control:
		check("CONTROL: with no world the key opens nothing", not gm.call("toggle_console_now"))
		check("the backtick key opens the console in the real game", gm.call("toggle_console_now"))
		print("RESULT %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
		quit(0 if fails == 0 else 1)
		return
	check("World.tscn has no DebugHarness", current_scene.find_child("DebugHarness", true, false) == null)
	check("the backtick key opens the console in the real game", gm.call("toggle_console_now"))
	var t := str(gm.call("console_run_now", "traffic"))
	print(t)
	check("`traffic` reports cars by distance and by side", t.contains("within 200 m by side of the camera") and t.contains("budget of"))
	var a := str(gm.call("console_run_now", "activity why m01_konbini"))
	check("`activity why` answers from the activity runtime", a.contains("replay: not completed yet"), a)
	var h := str(gm.call("console_run_now", "hud 2"))
	check("`hud 2` builds the perf HUD without a harness", h.contains("hud level 2"), h)
	check("the key closes it again", not gm.call("toggle_console_now"))
	print("RESULT %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
