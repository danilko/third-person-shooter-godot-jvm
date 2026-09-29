extends SceneTree
## A player cannot shove a parked car like a crate (user, 2026-09-28). The step-up (MovementController.stepUpLedge)
## used to climb a car's sloped nose and, with the body now standing on the dynamic car while walking into it, drove it
## ~20 m. A real Player sprints into a parked car through `Input` for 10 s from several spots round it; the car must
## barely move. A car is pushed by a CAR, never by a person (GTA V: a ped leaning on a car rocks it, nothing more).
##   godot --headless --path . --script tools/godot/probe_car_push.gd [-- --car=SPC1] [--control]
## --control turns the fix off (MovementController.stepPushesBodies): the car is driven off.
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const MAX_MOVE := 0.5
var fails := 0
var checks := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	checks += 1
	if not ok:
		fails += 1
	print("  %s  %-56s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _body_box(car: Node3D) -> AABB:
	var out := AABB()
	var first := true
	for n in car.find_children("*", "MeshInstance3D", true, false):
		var mi := n as MeshInstance3D
		if not mi.is_visible_in_tree() or mi.mesh == null:
			continue
		var bb: AABB = car.global_transform.affine_inverse() * mi.global_transform * mi.get_aabb()
		out = bb if first else out.merge(bb)
		first = false
	return out

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var car_id := "SPC1"
	var control := "--control" in OS.get_cmdline_user_args()
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--car="):
			car_id = a.substr(6)
	var w := Node3D.new()
	root.add_child(w)
	current_scene = w
	var f := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var b := BoxShape3D.new()
	b.size = Vector3(400, 1, 400)
	cs.shape = b
	f.add_child(cs)
	f.position.y = -0.5
	w.add_child(f)
	var helper: Node = load(HELPER).new()
	w.add_child(helper)
	for ci in 4:
		var car: RigidBody3D = load("res://src/main/resources/com/openworld/vehicle/%s.tscn" % car_id).instantiate()
		car.position = Vector3(0, 1.0, 0)
		w.add_child(car)
		await _tick(180)
		# start 2 m clear of THIS car's body (a 7.5 m truck swallows a fixed 5 m start)
		var box := _body_box(car)
		var hl := maxf(absf(box.position.z), absf(box.end.z)) + 2.0
		var hw := maxf(absf(box.position.x), absf(box.end.x)) + 2.0
		# [label, start, walk direction]
		var c: Array = [
			["the nose, off centre", Vector3(0.6, 1, -hl), Vector3(0, 0, 1)],
			["the nose, at the corner", Vector3(box.end.x - 0.2, 1, -hl), Vector3(0, 0, 1)],
			["the tail", Vector3(0.3, 1, hl), Vector3(0, 0, -1)],
			["the side", Vector3(hw, 1, 0.2), Vector3(-1, 0, 0)],
		][ci]
		var p: CharacterBody3D = load(PLAYER).instantiate()
		p.position = c[1]                  # BEFORE add_child: one frame at the origin, inside the car, launches it
		w.add_child(p)
		if control:
			p.get_node("MovementController").set("step_pushes_bodies", true)
		await _tick(30)
		var to: Vector3 = c[2]
		helper.call("set_view", p, rad_to_deg(atan2(-to.x, -to.z)), 0.0)
		var c0 := car.global_position
		Input.action_press("forward")
		Input.action_press("sprint")
		await _tick(600)
		Input.action_release("forward")
		Input.action_release("sprint")
		await _tick(60)
		var moved := car.global_position.distance_to(c0)
		_check("sprinting 10 s into %s moves it under %.1f m" % [c[0], MAX_MOVE], moved < MAX_MOVE, "%.2f m" % moved)
		car.queue_free()
		p.queue_free()
		await _tick(5)
	print("RESULT %s (%d passed, %d failed)" % ["PASS" if fails == 0 else "FAIL", checks - fails, fails])
	quit(0 if fails == 0 else 1)
