extends SceneTree
## A BUILDING's multi-stop lift carries a real Player floor by floor (user, 2026-09-28: the mission buildings --
## office, hospital, hotel, police -- have lifts with several stops and one door face; world.Elevator sweeps).
##   stdbuf -oL <godot> --headless --path . --script tools/godot/probe_building_lift.gd [-- --scene=<X_Shop.tscn>]
##       [--control]
##
##   1. the building carries a world.Elevator with more than two stops (or exactly its expected count), IDLE, shut;
##   2. a player walking up to the ground-floor door calls it: the doors open;
##   3. the player steps in and STAYS: the car goes up a floor at a time -- it stops at EVERY floor (never skips, never
##      turns round with the rider in it) and ends at the top stop, the rider on its floor;
##   4. the rider steps out onto the top floor's slab and stands there (the landing is a real floor);
##   5. with the rider gone the car stays at the top, shut.
## `--control` puts the lift OUT OF SERVICE: cases 2, 3 and 5 fail (4 checks).

const DEFAULT_SCENE := "res://src/main/resources/com/openworld/world/buildings/OfficeHQ_Shop.tscn"
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
var fails := 0
var world: Node3D

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-66s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _lifts(n: Node, out: Array) -> void:
	if n.has_method("phase_now"):
		out.append(n)
	for c in n.get_children():
		_lifts(c, out)

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var control := args.has("--control")
	var scene := DEFAULT_SCENE
	for a in args:
		if a.begins_with("--scene="):
			scene = a.substr(8)
	world = Node3D.new()
	root.add_child(world)
	var st: Node3D = (load(scene) as PackedScene).instantiate()
	world.add_child(st)
	await _tick(3)
	var lifts := []
	_lifts(st, lifts)
	_check("the building carries a lift", not lifts.is_empty(), scene.get_file())
	if lifts.is_empty():
		print("RESULT FAIL (%d failures)" % fails)
		quit(1)
		return
	var lift: Node3D = lifts[0]
	var stops: PackedFloat64Array = PackedFloat64Array()
	for s in str(lift.get("stop_heights")).split(","):
		stops.append(float(s))
	var n := int(lift.stop_count_now())
	_check("1. it has %d stops, is IDLE and shut" % n, n >= 2 and n == stops.size() and str(lift.phase_now()) == "IDLE"
		and float(lift.door_now()) == 0.0, str(stops))
	var xf: Transform3D = lift.global_transform
	var low := xf.origin
	var w := float(lift.get("shaft_width"))
	var faces := int(lift.get("faces"))
	var out_dir := -xf.basis.x.normalized() if (faces & 1) else xf.basis.x.normalized()
	var door_x := w / 2.0 + 0.03
	if control:
		lift.set("in_service", false)
	var p: CharacterBody3D = (load(PLAYER) as PackedScene).instantiate()
	world.add_child(p)
	p.global_position = low + out_dir * (door_x + 0.8) + Vector3(0, 0.05, 0)
	await _tick(150)
	_check("2. a player at the ground-floor door calls it: the doors open", str(lift.phase_now()) == "OPEN" and
		float(lift.door_now()) > 0.99, "%s %.2f" % [lift.phase_now(), lift.door_now()])
	p.global_position = low + Vector3(0, 0.05, 0)
	var visited := []
	var last_stop := -1
	var turned_round := false
	for k in range(60 * 90):
		await physics_frame
		var s := int(lift.stop_now())
		if str(lift.phase_now()) == "OPEN" and s != last_stop:
			if last_stop >= 0 and s < last_stop:
				turned_round = true
			visited.append(s)
			last_stop = s
			if s == n - 1:
				break
	var want := []
	for i in range(n):
		want.append(i)
	_check("3. staying aboard, it stops at every floor in turn to the top", visited == want and not turned_round,
		"visited %s" % [visited])
	var dy := p.global_position.y - (low.y + stops[n - 1])
	_check("   ...the rider on its floor at the top stop", absf(dy) < 0.12 and last_stop == n - 1,
		"rider %.2f m off the top stop" % dy)
	p.global_position = low + Vector3(0, stops[n - 1] + 0.05, 0) + out_dir * (door_x + 1.3)
	await _tick(30)
	var stood := p.global_position.y - (low.y + stops[n - 1])
	_check("4. the rider steps out onto the top floor's slab", absf(stood) < 0.15, "%.2f m" % stood)
	await _tick(700)
	_check("5. with nobody aboard it stays at the top, shut", int(lift.stop_now()) == n - 1 and
		str(lift.phase_now()) == "IDLE", "stop %d %s" % [lift.stop_now(), lift.phase_now()])
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
