extends SceneTree
## A player cannot shove a parked car like a crate (user, 2026-09-28). The step-up (MovementController.stepUpLedge)
## used to climb a car's sloped nose and, with the body now standing on the dynamic car while walking into it, drove it
## ~20 m. A real Player sprints into a parked car through `Input` for 10 s from several spots round it; the car must
## barely move. A car is pushed by a CAR, never by a person (GTA V: a ped leaning on a car rocks it, nothing more).
##   godot --headless --fixed-fps 60 --path . --script tools/godot/probe_car_push.gd [-- --car=SPC1] [--control]
##       [--state=asleep|vacated|fresh] [--pusher=player|ai] [--all]
## --control turns the fix off (MovementController.stepPushesBodies): the car is driven off.
## PLAN.md V4 (user, 2026-10-11: "a character shoves an empty car far in some setups and not in others") added the
## axes the first version did not cover. --state: asleep = parked and sleeping (the 09-28 case); vacated = a driver
## got out a moment ago (the car is awake, on its park dwell); fresh = just set down, never slept. --pusher=ai walks
## an AICharacter into it with a scripted brain. --all runs every state x pusher for the car (the gate).
## --park-control: Vehicle.heldWhenEmpty off = the car as it shipped before V4.
## PLAN.md 2c.2 (the rest of "an enormous push makes it slide"): --move=overlap sets the body down HALF INSIDE the hull
## and does it again every second (a respawn / teleport / stair or ladder snap); --move=ragdoll kills a body pressed
## into the hull so its ragdoll falls inside; --state=occupied has someone sitting in the car (V4's hold is only for an
## EMPTY car). --shove-control: Vehicle.capCharacterShove off. --all2c2 runs the 2c.2 matrix (the gate with --all).
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

const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"

func _run() -> void:
	var car_id := "SPC1"
	var control := "--control" in OS.get_cmdline_user_args()
	var park_control := "--park-control" in OS.get_cmdline_user_args()
	var shove_control := "--shove-control" in OS.get_cmdline_user_args()
	var trace := "--trace" in OS.get_cmdline_user_args()
	var states: Array = ["asleep"]
	var pushers: Array = ["player"]
	var move := "sprint"      # sprint | jump (sprint, jumping every 0.7 s: onto the hull) | roof (set down on the roof, sprinting to and fro)
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--car="):
			car_id = a.substr(6)
		elif a.begins_with("--state="):
			states = [a.substr(8)]
		elif a.begins_with("--pusher="):
			pushers = [a.substr(9)]
		elif a.begins_with("--move="):
			move = a.substr(7)
		elif a == "--all":
			states = ["asleep", "vacated", "fresh"]
			pushers = ["player", "ai"]
		elif a == "--all2c2":
			states = ["asleep", "vacated", "occupied"]
			pushers = ["player", "ai"]
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
	var cases: Array = []
	for st in states:
		for pu in pushers:
			for ci in 4:
				cases.append([st, pu, ci])
	for case in cases:
		var state: String = case[0]
		var pusher: String = case[1]
		var ci: int = case[2]
		var car: RigidBody3D = load("res://src/main/resources/com/openworld/vehicle/%s.tscn" % car_id).instantiate()
		car.position = Vector3(0, 1.0, 0)
		w.add_child(car)
		if park_control:
			car.set("held_when_empty", false)
		if shove_control:
			car.set("cap_character_shove", false)
		await _tick(180)
		var rider: CharacterBody3D = null
		if state == "occupied":
			# someone sits in it, idle (the car parks with them in it): V4's empty-car hold does not apply
			rider = load(AI).instantiate()
			rider.position = Vector3(0, 1, 60)
			w.add_child(rider)
			helper.call("seat_driver", car, rider)
			await _tick(60)
		if state == "vacated":
			# someone drove it and got out: seated, then a real exit, the body taken away at once
			var drv: CharacterBody3D = load(AI).instantiate()
			drv.position = Vector3(0, 1, 60)
			w.add_child(drv)
			helper.call("seat_driver", car, drv)
			await _tick(30)
			helper.call("exit_driver", car)
			drv.queue_free()
			await _tick(2)
		elif state == "fresh":
			car.queue_free()
			await _tick(2)
			car = load("res://src/main/resources/com/openworld/vehicle/%s.tscn" % car_id).instantiate()
			car.position = Vector3(0, 0.6, 0)
			w.add_child(car)
			if park_control:
				car.set("held_when_empty", false)
			await _tick(20)
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
		# overlap / ragdoll: 0.15 m inside the hull's face (each start is 2 m clear of it)
		var inside: Vector3 = c[1] + (c[2] as Vector3) * 2.15
		var p: CharacterBody3D = load(PLAYER if pusher == "player" else AI).instantiate()
		p.position = c[1] if move != "roof" else Vector3(0, box.end.y + 1.2, 0)   # BEFORE add_child: one frame at the origin, inside the car, launches it
		if move == "overlap" or move == "ragdoll":
			p.position = inside
		w.add_child(p)
		if control:
			p.get_node("MovementController").set("step_pushes_bodies", true)
		await _tick(10 if state != "asleep" else 30)
		var to: Vector3 = c[2]
		var c0 := car.global_position
		var far := 0.0
		var still := move == "overlap" or move == "ragdoll"
		if still:
			if pusher == "ai":
				helper.call("scripted_walk", p, Vector3.ZERO, false)
			if move == "ragdoll":
				helper.call("kill", p)
		elif pusher == "player":
			helper.call("set_view", p, rad_to_deg(atan2(-to.x, -to.z)), 0.0)
			Input.action_press("forward")
			Input.action_press("sprint")
		else:
			helper.call("scripted_walk", p, to, true)
		for i in 600:
			await physics_frame
			far = maxf(far, car.global_position.distance_to(c0))
			if pusher == "player" and move == "jump":
				if i % 42 == 0:
					Input.action_press("jump")
				elif i % 42 == 3:
					Input.action_release("jump")
			if trace and i % 15 == 0:
				print("    t %.2f car %s v %.2f sleep %s | body %s v %.2f" % [i / 60.0, car.global_position - c0,
						car.linear_velocity.length(), car.sleeping, p.global_position - c0, p.velocity.length()])
			if move == "overlap" and i % 60 == 59:
				p.global_position = car.global_position + (inside - c0)    # set down in the hull again, where it is now
			if pusher == "player" and move == "roof" and i % 90 == 89:
				to = -to
				helper.call("set_view", p, rad_to_deg(atan2(-to.x, -to.z)), 0.0)
		if pusher == "player":
			Input.action_release("forward")
			Input.action_release("sprint")
		else:
			helper.call("scripted_walk", p, Vector3.ZERO, false)
		await _tick(60)
		var moved := maxf(far, car.global_position.distance_to(c0))
		var reached := still or p.global_position.distance_to(c[1]) > 0.8
		Input.action_release("jump")
		_check("%s car, %s %s 10 s into %s: under %.1f m" % [state, pusher, move, c[0], MAX_MOVE],
				moved < MAX_MOVE and reached, "%.2f m%s" % [moved, "" if reached else " (the pusher never moved)"])
		if rider != null:
			helper.call("exit_driver", car)
			rider.queue_free()
		car.queue_free()
		if is_instance_valid(p):
			p.queue_free()
		await _tick(5)
	print("RESULT %s (%d passed, %d failed)" % ["PASS" if fails == 0 else "FAIL", checks - fails, fails])
	quit(0 if fails == 0 else 1)
