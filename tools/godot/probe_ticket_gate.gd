extends SceneTree
## A station's fare barrier (PLAN.md "the paid area"; since step 7a on a KIT station, `Station_Farm_Shop.tscn`):
## the street door opens onto the UNPAID hall, and the only way to the platform is a ticket-gate lane, whose two
## `world.TicketGate` flaps open for a character in the lane and shut behind them.
##   stdbuf -oL <godot> --headless --path . --script tools/godot/probe_ticket_gate.gd [-- --control] [-- --scene=<tscn>]
##
##   1. the station carries its gate lanes, two TicketGate flaps each;
##   2. with nobody near, the first lane is SHUT (a ray down it hits a flap);
##   3. the gate bodies beside the lane block it (a ray down each side hits something);
##   4. a player standing in the lane on its unpaid side opens both flaps and the lane is CLEAR;
##   5. the player walking away shuts them again.
## Each lane's frame is its sensor's (`build_building_scenes.gd _add_gate`): origin mid-lane, +Z the unpaid side, the
## lane `w` wide along X. `--control` makes the flaps manual (auto_open false): case 4 fails.

const DEFAULT_SCENE := "res://src/main/resources/com/openworld/world/buildings/Station_Farm_Shop.tscn"
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
var fails := 0
var world: Node3D

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-60s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _gates(n: Node, out: Array) -> void:
	if str(n.name).begins_with("Gate") and n.get("open_mode") != null:
		out.append(n)
	for c in n.get_children():
		_gates(c, out)

func _ray(a: Vector3, b: Vector3, exclude: Array) -> Dictionary:
	var q := PhysicsRayQueryParameters3D.create(a, b, 1)
	q.exclude = exclude
	return world.get_world_3d().direct_space_state.intersect_ray(q)

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var control := OS.get_cmdline_user_args().has("--control")
	world = Node3D.new()
	root.add_child(world)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(60, 0.2, 60)
	cs.shape = box
	floor.add_child(cs)
	world.add_child(floor)
	floor.position = Vector3(0, -0.1, 0)
	var scene_path := DEFAULT_SCENE
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--scene="):
			scene_path = a.substr(8)
	var b: Node3D = (load(scene_path) as PackedScene).instantiate()
	world.add_child(b)
	await _tick(2)
	var gates: Array = []
	_gates(b, gates)
	var sensors: Array = []
	for n in b.find_child("Doors", true, false).get_children():
		if str(n.name).begins_with("GateSensor"):
			sensors.append(n)
	_check("the station has gate lanes of two TicketGate flaps each",
		sensors.size() >= 1 and gates.size() == 2 * sensors.size(), "%d lanes, %d flaps" % [sensors.size(), gates.size()])
	if sensors.is_empty():
		print("RESULT FAIL")
		quit(1)
		return
	# the first lane and its two flaps (the ones whose sensor_path names it)
	var sensor: Area3D = sensors[0]
	var xf: Transform3D = sensor.global_transform
	var mine: Array = gates.filter(func(g): return str(g.get("sensor_path")).ends_with(str(sensor.name)))
	var w := ((sensor.get_child(0) as CollisionShape3D).shape as BoxShape3D).size.x
	if control:
		for g in gates:
			g.set("auto_open", false)
	var yaw0: Array = mine.map(func(g): return (g as Node3D).global_rotation.y)
	var L := func(x: float, z: float) -> Vector3: return xf * Vector3(x, 0.6, z)
	var hit := _ray(L.call(0.0, 1.2), L.call(0.0, -1.2), [])
	_check("nobody near: the lane is shut (a ray down it hits a flap)",
		mine.size() == 2 and not hit.is_empty() and str(hit["collider"].name).begins_with("Gate"),
		str(hit.get("collider", null)))
	for x in [w / 2.0 + 0.3, -(w / 2.0 + 0.3)]:
		var fh := _ray(L.call(x, 1.2), L.call(x, -1.2), [])
		_check("beside the lane at x %+.2f the way is blocked" % x, not fh.is_empty(), str(fh.get("collider", null)))
	var p: CharacterBody3D = (load(PLAYER) as PackedScene).instantiate()
	world.add_child(p)
	p.global_position = xf * Vector3(0, 0.05, 0.9)
	p.set_physics_process(false)
	await _tick(40)
	var turned: Array = []
	for i in range(mine.size()):
		turned.append(rad_to_deg(absf(angle_difference((mine[i] as Node3D).global_rotation.y, yaw0[i]))))
	var clear := _ray(L.call(0.0, 0.6), L.call(0.0, -1.5), [p.get_rid()])
	_check("a player in the lane opens both flaps", turned.size() == 2 and turned[0] > 80.0 and turned[1] > 80.0,
		"turned %s deg" % str(turned))
	_check("...and the lane is clear to the paid side", clear.is_empty(), str(clear.get("collider", null)))
	p.global_position = xf * Vector3(0, 0.05, 8.0)
	await _tick(40)
	var back := true
	for i in range(mine.size()):
		back = back and absf(angle_difference((mine[i] as Node3D).global_rotation.y, yaw0[i])) < 0.01
	_check("walking away shuts them again", back)
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
