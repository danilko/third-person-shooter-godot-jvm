extends SceneTree
## Armour and the helicopter shot down (user 2026-10-07: "the helicopter / tank cannot be shot down").
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_vehicle_armour.gd
##
## 1. Rockets (ATL1's own numbers, a blast on the hull's side) and ASR1 rounds (ImpactManager.processHit) to destroy
##    each enforcement vehicle: HLC-1 2 rockets / ~100 rounds; ARV-1 2 rockets; LTK-1 3; TNK-1 4; a rifle still hurts a tank
##    (one damage rule, early-GTA style), it just takes hundreds of rounds.
## 2. An HLC-1 hovering 40 m over the floor and killed by a rocket FALLS (it is "downed", it loses height), then is
##    destroyed on impact; its wreck lies on the floor, not in the air.

const W := "res://src/main/resources/com/openworld/weapon/"
const V := "res://src/main/resources/com/openworld/vehicle/"

var fails := 0
var helper: Node
var em: Node
var im: Node
var stand: Node3D

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", label, detail])

func _spawn(id: String, at: Vector3, frozen: bool) -> RigidBody3D:
	var c: RigidBody3D = (load(V + id + ".tscn") as PackedScene).instantiate()
	stand.add_child(c)
	c.global_position = at
	c.freeze = frozen
	for i in 3:
		await physics_frame
	return c

func _hp(n: Node) -> float:
	return float(n.get_node("Health").call("health_now"))

func _initialize() -> void:
	stand = Node3D.new()
	root.add_child(stand)
	current_scene = stand
	var floor_body := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(400, 1, 400)
	cs.shape = box
	floor_body.add_child(cs)
	stand.add_child(floor_body)
	floor_body.position = Vector3(0, -0.5, 0)
	helper = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
	em = load("res://src/main/java/com/openworld/world/manager/ExplosionManager.java").new()
	im = load("res://src/main/java/com/openworld/world/manager/ImpactManager.java").new()
	stand.add_child(helper)
	stand.add_child(em)
	stand.add_child(im)
	var atl: Node = (load(W + "ATL1.tscn") as PackedScene).instantiate()
	var rr: float = atl.get("explosion_radius")
	var rd: float = atl.get("explosion_max_damage")
	atl.free()
	var asr := float((load(W + "stats/ASR1.tres")).get("damage"))
	await physics_frame

	print("== 1. rockets and rifle rounds to destroy each vehicle")
	var want := {"HLC1": 2, "ARV1": 2, "LTK1": 3, "TNK1": 4}
	for id in ["HLC1", "ARV1", "LTK1", "TNK1"]:
		var c := await _spawn(id, Vector3(0, 20, 0), true)
		var hp0 := _hp(c)
		helper.call("weapon_hit", im, c, asr)
		await physics_frame
		var per_round := hp0 - _hp(c)
		var rounds := ceili(hp0 / maxf(per_round, 1e-6))
		c.free()
		c = await _spawn(id, Vector3(0, 20, 0), true)
		var n := 0
		while is_instance_valid(c) and _hp(c) > 0.0 and n < 40:
			helper.call("blast", em, c.global_position, rr, rd)       # a direct hit: the rocket bursts on the hull
			n += 1
			await physics_frame
		_check("%s: %d rocket(s) to destroy (want %d)" % [id, n, want[id]], n == want[id],
			"%.0f HP, %.1f per ASR1 round = %d rounds" % [hp0, per_round, rounds])
		if id == "HLC1":
			_check("HLC1: a rifle brings it down in about 100 rounds", rounds >= 80 and rounds <= 120, "%d rounds" % rounds)
		if id == "TNK1":
			_check("TNK1: a rifle hurts it, but it takes hundreds of rounds", per_round > 0.0 and rounds >= 400 and rounds <= 900, "%d rounds" % rounds)
		if is_instance_valid(c):
			c.queue_free()
		for i in 5:
			await physics_frame

	print("== 1b. the damage KIND: the target decides (world.DamageKind)")
	var knife_heavy := 100.0
	var axe_heavy := 120.0
	var fist := 14.0
	var car := await _spawn("SPC1", Vector3(10, 20, 0), true)
	var person: Node3D = (load("res://src/main/resources/com/openworld/character/AICharacter.tscn") as PackedScene).instantiate()
	stand.add_child(person)
	person.global_position = Vector3(-10, 0, 0)
	for i in 5:
		await physics_frame
	var lost := {}
	for k in [["BLADE", knife_heavy], ["BLUNT", fist], ["HEAVY", axe_heavy], ["BULLET", asr]]:
		var h0 := _hp(car)
		helper.call("kind_hit", im, car, k[1], k[0])
		await physics_frame
		lost[k[0]] = h0 - _hp(car)
	# San Andreas style (user 2026-10-07): melee hurts a vehicle, a tenth as much (a 500 HP car ~360 punches)
	_check("a knife's heavy stab does a tenth to a car", is_equal_approx(lost["BLADE"], knife_heavy * 0.1), "%.1f HP" % lost["BLADE"])
	_check("a punch does a tenth to a car", is_equal_approx(lost["BLUNT"], fist * 0.1), "%.1f HP" % lost["BLUNT"])
	_check("an axe's heavy chop hurts a car like gunfire does", is_equal_approx(lost["HEAVY"], axe_heavy * 0.4), "%.1f HP" % lost["HEAVY"])
	_check("a rifle round is unchanged on a car", is_equal_approx(lost["BULLET"], asr * 0.4), "%.1f HP" % lost["BULLET"])
	var p0 := _hp(person)
	helper.call("kind_hit", im, person, 30.0, "BLADE")
	await physics_frame
	_check("a knife is full damage on a person", is_equal_approx(p0 - _hp(person), 30.0), "%.1f HP" % (p0 - _hp(person)))
	car.queue_free()
	person.queue_free()
	for i in 5:
		await physics_frame

	print("== 2. a helicopter shot down in the air falls and wrecks on the ground")
	var h := await _spawn("HLC1", Vector3(0, 40, 0), false)
	var tgt := Node3D.new()
	stand.add_child(tgt)
	tgt.global_position = Vector3(0, 2, 0)
	h.set("ai_target", tgt)
	for i in 120:
		await physics_frame
	var y0 := h.global_position.y
	_check("it hovers before it is hit", y0 > 20.0, "y %.1f" % y0)
	var rotor := h.get_node("Model/rotor") as MeshInstance3D
	var hub_local := rotor.get_aabb().get_center()
	var hub0 := h.to_local(rotor.global_transform * hub_local)
	var b0 := rotor.transform.basis
	await physics_frame
	await physics_frame
	var turned := rad_to_deg(b0.get_rotation_quaternion().angle_to(rotor.transform.basis.get_rotation_quaternion()))
	var drift := h.to_local(rotor.global_transform * hub_local).distance_to(hub0)
	_check("the rotor turns, a visible step a frame (no strobing)", turned > 5.0 and turned < 45.0, "%.1f deg in 2 frames" % turned)
	_check("the rotor turns about its own hub", drift < 0.01, "hub moved %.4f m" % drift)
	while is_instance_valid(h) and _hp(h) > 0.0:
		helper.call("blast", em, h.global_position + Vector3(0.0, -2.5, 0.0), rr, rd)
		await physics_frame
	_check("at 0 HP in the air it is downed, not gone", is_instance_valid(h) and bool(h.call("downed_now")))
	for i in 60:
		await physics_frame
	var y1: float = h.global_position.y if is_instance_valid(h) else -1.0
	_check("it falls (loses height)", not is_instance_valid(h) or y1 < y0 - 3.0, "y %.1f -> %.1f" % [y0, y1])
	var t := 0
	var last_y := y1
	while is_instance_valid(h) and t < 60 * 10:
		last_y = h.global_position.y
		await physics_frame
		t += 1
	print("    destroyed at y %.1f" % last_y)
	_check("it reached the ground before it blew up", last_y < 4.0, "y %.1f" % last_y)
	_check("it is destroyed on impact", not is_instance_valid(h), "%.1f s" % (t / 60.0))
	var wreck: Node3D = null
	for n2 in stand.get_children():
		if n2.name.begins_with("VehicleWreck") or str(n2.name).contains("Wreck"):
			wreck = n2
	if wreck == null:
		for n2 in root.get_children():
			if str(n2.name).contains("Wreck"):
				wreck = n2
	_check("its wreck lies on the floor", wreck != null and wreck.global_position.y < 1.5,
		"wreck y %s" % (str(snappedf(wreck.global_position.y, 0.01)) if wreck else "none"))
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
