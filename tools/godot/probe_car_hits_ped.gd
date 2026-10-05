extends SceneTree
## A CAR HITS A PEDESTRIAN (user, 2026-10-04: "when a vehicle hits a crowd character, the character is like a tree or
## a wall: the car takes the damage and the person has no issue"). A real SPC-1 is driven at a standing person on
## DebugWorld's flat ground, through the car's own controls held at speed until 6 m short, then coasting; measured:
## the person's health, whether they were knocked down / thrown, the car's speed just after, and the car's health.
##
##   <godot> --headless --path . --script tools/godot/probe_car_hits_ped.gd [-- --speed=15] [--control]
##   --control: the old behaviour switch (Vehicle.knock_people off)
const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const CAR := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
var fails := 0
var checks := 0

func _check(ok: bool, what: String) -> void:
	checks += 1
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _initialize() -> void:
	_run.call_deferred()

func _arg(k: String, d: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--" + k + "="):
			return a.substr(k.length() + 3)
	return d

func _run() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	var speed := float(_arg("speed", "15"))
	# a bare flat stand: nothing on it but the car and the person
	var w := Node3D.new()
	root.add_child(w)
	current_scene = w
	var ground := StaticBody3D.new()
	var gs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(400, 1, 400)
	gs.shape = box
	ground.add_child(gs)
	w.add_child(ground)
	ground.position = Vector3(0, -0.5, 0)
	for i in 10:
		await physics_frame
	var px := 0.0
	var pz := -20.0
	var h := 0.0
	var person: CharacterBody3D = (load(AI) as PackedScene).instantiate()
	w.add_child(person)
	person.global_position = Vector3(px, h + 0.1, pz)
	for i in 10:
		await physics_frame
	var mc := person.get_node_or_null("MovementController")
	if mc != null:
		mc.process_mode = Node.PROCESS_MODE_DISABLED
	var ctrl := person.get_node_or_null("AIController")
	if ctrl != null:
		ctrl.process_mode = Node.PROCESS_MODE_DISABLED
	person.global_position = Vector3(px, h + 0.1, pz)
	var health: Node = person.get_node("Health")
	# the CHEST's ragdoll bone: on death the body's root stays where it stood and the ragdoll is what is thrown
	var chest: Node3D = null
	for b in person.find_children("*", "PhysicalBone3D", true, false):
		if "spine_03" in b.name:
			chest = b
	var chest0: Vector3 = chest.global_position if chest != null else Vector3.ZERO
	var hp0 := float(health.call("health_now"))
	var car: RigidBody3D = (load(CAR) as PackedScene).instantiate()
	w.add_child(car)
	var hc := 0.0
	car.global_position = Vector3(px, hc + 0.9, pz + 45.0)
	if control:
		car.set("knock_people", false)
	for i in 60:
		await physics_frame
		if not is_instance_valid(car):
			print("  car freed at frame %d" % i)
			quit(1)
			return
		if i % 10 == 0:
			print("  car at %s" % car.global_position)
	var chp0 := float(car.get_node("Health").call("health_now"))
	var v_before := 0.0
	var v_after := -1.0
	var hit_at := -1
	var wrecked := false
	var last_hp := chp0
	for f in 360:
		if not is_instance_valid(car):
			wrecked = true
			print("  the car was WRECKED at frame %d (hp %.0f a frame before)" % [f, last_hp])
			break
		last_hp = float(car.get_node("Health").call("health_now"))
		var d := car.global_position.z - pz
		if absf(d) < 8.0 and f % 2 == 0:
			print("  f%d d %.2f v %.1f car hp %.0f person hp %.0f" % [f, d, car.linear_velocity.length(), last_hp,
					float(health.call("health_now")) if is_instance_valid(health) else -1.0])
		if d > 6.0:
			car.linear_velocity = Vector3(0, car.linear_velocity.y, -speed)
		if d > 1.5:
			v_before = absf(car.linear_velocity.z)
		elif hit_at < 0:
			hit_at = f
		if hit_at >= 0 and f == hit_at + 6:
			v_after = absf(car.linear_velocity.z)
		await physics_frame
	var hp1 := float(health.call("health_now")) if is_instance_valid(health) else 0.0
	var chp1 := 0.0 if wrecked else float(car.get_node("Health").call("health_now"))
	var moved := 99.0
	if is_instance_valid(person):
		moved = Vector2(person.global_position.x - px, person.global_position.z - pz).length()
		if chest != null:
			moved = maxf(moved, chest.global_position.distance_to(chest0))
	print("  person hp %.0f -> %.0f, moved %.2f m; car %.1f -> %.1f m/s, car hp %.0f -> %.0f, reached the person: %s"
			% [hp0, hp1, moved, v_before, v_after, chp0, chp1, hit_at >= 0])
	_check(hit_at >= 0, "the car reached the person")
	_check(hp1 < hp0 - 30.0, "the person is hurt by the car (%.0f HP)" % (hp0 - hp1))
	_check(moved > 1.0, "the person is thrown, not a post (%.2f m)" % moved)
	if wrecked:
		v_after = 0.0
	_check(v_after > v_before * 0.6, "the car keeps most of its speed (%.1f of %.1f m/s)" % [v_after, v_before])
	_check(chp0 - chp1 < 20.0, "the car is not wrecked by a person (%.0f HP)" % (chp0 - chp1))
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 and checks == 5 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
