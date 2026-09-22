extends SceneTree
## PLAN.md 3.26 gate: the postal code, typed through the debug console exactly as a player would.
##   stdbuf -oL <godot> --headless --path . --script tools/godot/probe_postal.gd
##
## The code is checked against an INDEPENDENT reading of the rule written here (x = floor((X + 2304) / 192) + 1,
## y the same on Z, the keypad sub-cell row-major from the top-left), not against the Java owner, so the probe
## cannot agree with the implementation by construction.
##   1. `postal 12-7-5` puts the waypoint inside that 64 m sub-cell;
##   2. `postal 3-20-1 tp` moves the player into 3-20-1, standing on the ground (not inside it);
##   3. `tp x y z` moves the player there;
##   4. `where` prints a bug-report line that carries the player's own code and position;
##   5. a code that is not one (`postal 25-1`) changes nothing.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
var fails := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", label, detail])

func _code(p: Vector3) -> String:
	var u := p.x + 2304.0
	var v := p.z + 2304.0
	var cx := clampi(int(floor(u / 192.0)) + 1, 1, 24)
	var cy := clampi(int(floor(v / 192.0)) + 1, 1, 24)
	var col := clampi(int(floor((u - (cx - 1) * 192.0) / 64.0)), 0, 2)
	var row := clampi(int(floor((v - (cy - 1) * 192.0) / 64.0)), 0, 2)
	return "%d-%d-%d" % [cx, cy, row * 3 + col + 1]

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _label_text(n: Node) -> String:
	for c in n.find_children("*", "Label", true, false):
		return (c as Label).text
	return ""

func _initialize() -> void:
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	cs.shape = BoxShape3D.new()
	(cs.shape as BoxShape3D).size = Vector3(4700, 1, 4700)
	floor.add_child(cs)
	floor.position = Vector3(0, -0.5, 0)
	world.add_child(floor)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate()
	world.add_child(p)
	await _tick(20)
	var console: Node = load("res://src/main/java/com/openworld/debug/DebugConsole.java").new()
	root.add_child(console)
	await _tick(2)

	console.call("on_submit", "postal 12-7-5")
	var w: Vector3 = p.call("waypoint_now")
	_check("postal 12-7-5 sets the waypoint in that sub-cell", p.call("has_waypoint_now") and _code(w) == "12-7-5",
			"waypoint (%.0f, %.0f) = %s" % [w.x, w.z, _code(w)])

	console.call("on_submit", "postal 3-20-1 tp")
	await _tick(10)
	var at: Vector3 = p.global_position
	_check("postal 3-20-1 tp moves the player into 3-20-1", _code(at) == "3-20-1",
			"(%.1f, %.1f, %.1f) = %s" % [at.x, at.y, at.z, _code(at)])
	_check("...standing on the ground, not in it or 400 m up", at.y > -0.5 and at.y < 3.0, "y %.2f" % at.y)

	console.call("on_submit", "tp 100 5 -300")
	await _tick(10)
	at = p.global_position
	_check("tp x y z moves the player there", absf(at.x - 100.0) < 0.5 and absf(at.z + 300.0) < 0.5,
			"(%.1f, %.1f, %.1f)" % [at.x, at.y, at.z])

	console.call("on_submit", "where")
	var line := _label_text(console)
	var mine := _code(p.global_position)
	_check("where prints the player's own code and position", line.contains(mine) and line.contains("x 100."),
			line.get_slice("\n", line.count("\n")).substr(0, 110))

	var before: Vector3 = p.call("waypoint_now")
	console.call("on_submit", "postal 25-1")
	_check("a code that is not one changes nothing", (p.call("waypoint_now") as Vector3).is_equal_approx(before), "")

	print("RESULT: %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
