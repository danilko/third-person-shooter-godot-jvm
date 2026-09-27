extends SceneTree
## The station building's fare barrier (PLAN.md P3 "the paid area", 2026-09-27): the street door opens onto the
## UNPAID hall, a railing runs across the building, and the only way to the back (platform) door is the ticket-gate
## lane, whose two `world.TicketGate` flaps open for a character in the lane and shut behind them.
##   stdbuf -oL <godot> --headless --path . --script tools/godot/probe_ticket_gate.gd [-- --control]
##
##   1. the gate scene carries two TicketGate flaps;
##   2. with nobody near, the lane is SHUT (a ray down the lane hits a flap);
##   3. the railing beside the gates blocks the hall from the paid side;
##   4. a player standing in the lane opens both flaps and the lane is CLEAR;
##   5. the player walking away shuts them again.
## `--control` makes the flaps manual (auto_open false): case 4 fails.

const SCENE := "res://src/main/resources/com/openworld/world/buildings/StationBuilding_Shop.tscn"
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const GATE_Z := -1.6
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
	var b: Node3D = (load(SCENE) as PackedScene).instantiate()
	world.add_child(b)
	await _tick(2)
	var gates: Array = []
	_gates(b, gates)
	_check("the gate lane has two TicketGate flaps", gates.size() == 2, "%d" % gates.size())
	if gates.size() != 2:
		print("RESULT FAIL")
		quit(1)
		return
	if control:
		for g in gates:
			g.set("auto_open", false)
	var yaw0: Array = gates.map(func(g): return (g as Node3D).rotation.y)
	var lane_a := Vector3(0, 0.6, -0.4)
	var lane_b := Vector3(0, 0.6, -2.9)
	var hit := _ray(lane_a, lane_b, [])
	_check("nobody near: the lane is shut (a ray down it hits a flap)",
		not hit.is_empty() and str(hit["collider"].name).begins_with("Gate"),
		str(hit.get("collider", null)))
	for x in [2.5, 4.5, -2.5, -4.5]:
		var fh := _ray(Vector3(x, 0.6, -0.4), Vector3(x, 0.6, -2.9), [])
		_check("the railing at x %.1f blocks the hall from the paid side" % x, not fh.is_empty(),
			str(fh.get("collider", null)))
	var p: CharacterBody3D = (load(PLAYER) as PackedScene).instantiate()
	world.add_child(p)
	p.global_position = Vector3(0, 0.05, -0.6)
	p.set_physics_process(false)
	for k in range(8):
		await _tick(5)
		if OS.get_cmdline_user_args().has("--verbose"):
			print("   t%d yaw %.1f %.1f speed %s angle %s" % [k * 5, rad_to_deg((gates[0] as Node3D).rotation.y), rad_to_deg((gates[1] as Node3D).rotation.y), gates[0].get("open_speed"), gates[0].get("open_angle_deg")])
	var turned: Array = []
	for i in range(2):
		turned.append(rad_to_deg(absf(angle_difference((gates[i] as Node3D).rotation.y, yaw0[i]))))
	var clear := _ray(Vector3(0, 0.6, -1.0), lane_b, [p.get_rid()])
	_check("a player in the lane opens both flaps", turned[0] > 80.0 and turned[1] > 80.0,
		"turned %.1f / %.1f deg" % [turned[0], turned[1]])
	_check("...and the lane is clear to the paid side", clear.is_empty(), str(clear.get("collider", null)))
	p.global_position = Vector3(0, 0.05, 6.0)
	await _tick(40)
	var back := true
	for i in range(2):
		back = back and absf(angle_difference((gates[i] as Node3D).rotation.y, yaw0[i])) < 0.01
	_check("walking away shuts them again", back)
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
