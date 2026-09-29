extends SceneTree
## Car windows (user 2026-09-28). Ordinary glass (every car) gives ONE hit of protection: a pistol or SMG round
## breaks it and stops in it, the next goes through; a rifle-class round (20+) or heavier breaks it and goes through at
## full damage; a shotgun pull puts its first pellet into the glass and the rest through. A special vehicle's armoured
## glass (VehicleConfig.glassArmor > 0) is a pool instead. The expected pull and damage are worked out from the car's own
## armour, so the same probe runs on every car. A blast beside the car breaks its windows. A real Player, armed with ASR1 through the ordinary
## pickup, fires through `Input` at the head of an AI seated in a real car, from the side the seat is on; the rifle's
## damage and pellet count are set per case (a pistol round, a sniper round, a shotgun pull), each on a fresh car.
##   godot --headless --path . --script tools/godot/probe_vehicle_glass.gd [-- --car=SPC1] [--front] [--control]
## --control turns `shoot_through_glass` off on the gun: the windows are steel again and the occupant is never hit.
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const ASR1 := "res://src/main/resources/com/openworld/weapon/ASR1.tscn"
const IMPACT := "res://src/main/java/com/openworld/world/manager/ImpactManager.java"
const EXPLOSION := "res://src/main/java/com/openworld/world/manager/ExplosionManager.java"
const PIERCE_AT := 20.0     # VehicleDamageRules.PANE_PIERCE_AT
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const SENS := 0.07
var p: Node3D
var cam_ctrl: Node
var fails := 0
var checks := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	checks += 1
	if not ok:
		fails += 1
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _find(n: Node, nm: String) -> Node:
	if n.name == nm:
		return n
	for c in n.get_children():
		var r: Node = _find(c, nm)
		if r != null:
			return r
	return null

func _steer_to(target: Vector3, frames: int) -> float:
	var err := 99.0
	for i in frames:
		var cam := p.get_node("ActiveCamera") as Node3D
		var to: Vector3 = target - cam.global_position
		var f := -cam.global_transform.basis.z
		var dy := wrapf(rad_to_deg(atan2(-to.x, -to.z)) - rad_to_deg(atan2(-f.x, -f.z)), -180.0, 180.0)
		var dp := rad_to_deg(atan2(to.y, Vector2(to.x, to.z).length())) - rad_to_deg(asin(clampf(f.y, -1.0, 1.0)))
		err = rad_to_deg(f.angle_to(to.normalized()))
		if err < 0.01:
			return err
		var ev := InputEventMouseMotion.new()
		ev.relative = Vector2(-dy / SENS, -dp / SENS)
		cam_ctrl.call("_input", ev)
		await physics_frame
	return err

func _panes(dm: Node) -> String:
	var out := []
	for e in str(dm.call("panes_now")).split(","):
		var slot := e.split("/")[0]
		out.append("%s=%d" % [slot, int(dm.call("pane_state_now", slot))])
	return " ".join(out)

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var car_id := "SPC1"
	var control := "--control" in OS.get_cmdline_user_args()
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--car="):
			car_id = a.substr(6)
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(200, 1, 200)
	cs.shape = box
	floor.add_child(cs)
	floor.position.y = -0.5
	world.add_child(floor)
	world.add_child(load(IMPACT).new())
	var helper: Node = load(HELPER).new()
	world.add_child(helper)
	var cases := [
		["pistol rounds (10)", 10.0, 1],
		["rifle round (20)", 20.0, 1],
		["sniper round (150)", 150.0, 1],
		["shotgun pull (8 x 15)", 15.0, 8],
	]
	p = (load(PLAYER) as PackedScene).instantiate()
	world.add_child(p)
	p.global_position = Vector3(0, 1, 30)
	await _tick(40)
	var gun: Node3D = (load(ASR1) as PackedScene).instantiate()
	world.add_child(gun)
	gun.global_position = p.global_position + Vector3(0, 0.3, 0)
	await _tick(30)
	var wc: Node = p.get_node("WeaponController")
	for slot in range(6):
		if String(gun.get_parent().name).begins_with("Socket"):
			break
		wc.call("on_set_weapon", slot)
		await _tick(40)
	if control:
		gun.set("shoot_through_glass", false)
		print("CONTROL: shoot_through_glass off")
	p.set("is_fps_mode", true)
	cam_ctrl = p.get_node("TPSCameraController")
	var ci := 0
	for c in cases:
		var at_x := -40.0 + 40.0 * ci
		ci += 1
		var car: RigidBody3D = (load("res://src/main/resources/com/openworld/vehicle/%s.tscn" % car_id) as PackedScene).instantiate()
		car.position = Vector3(at_x, 1.2, 0)
		world.add_child(car)
		var ai: Node3D = (load(AI) as PackedScene).instantiate()
		ai.position = Vector3(at_x, 0.5, 8)
		world.add_child(ai)
		var h: Node = ai.get_node("Health")
		h.set("max_health", 1.0e9)
		var hits: Array = []
		h.connect("hit", func(dmg): hits.append(dmg))
		await _tick(90)
		helper.call("seat_character", car, ai)
		await _tick(40)
		car.freeze = true
		var dm: Node = car.get_node("DamageModel")
		var head := _find(ai, "Physical Bone head_2") as PhysicalBone3D
		print("== %s  %s  windows: %s" % [car_id, c[0], dm.call("panes_now")])
		if ci == 1:
			_check("the car has windows", str(dm.call("panes_now")) != "")
			_check("the seated occupant keeps a head hitbox on the HITBOX layer", head != null and (head.collision_layer & 8) != 0)
		var side := signf(car.to_local(head.global_position).x)
		var from := car.to_global(Vector3(side * 7.0, 0.0, car.to_local(head.global_position).z))
		if "--front" in OS.get_cmdline_user_args():               # through the windscreen instead of a side window
			from = car.to_global(Vector3(car.to_local(head.global_position).x, 0.0, -9.0))
		from.y = 0.2
		p.global_position = from
		await _tick(40)
		gun.set("damage", c[1])
		gun.set("pellet_count", c[2])
		var armor: float = float(car.get("vehicle_config").get("glass_armor"))
		# which pull first reaches the occupant, and with how much of a round, from the armour alone
		var taken := 0.0
		var want_shot := -1
		var want_carry := 0.0
		for shot in 30:
			for pel in int(c[2]):
				var carry: float
				if armor <= 0.0:
					carry = c[1] if (taken > 0.0 or c[1] >= PIERCE_AT) else 0.0
				else:
					carry = c[1] if taken >= armor else maxf(0.0, c[1] - maxf(0.0, armor - taken))
				taken += c[1]
				if carry > 0.0 and want_shot < 0:
					want_shot = shot
					want_carry = carry
			if want_shot >= 0:
				break
		var mask0 := int(dm.call("part_mask_now"))
		var got := -1
		var got_dmg := 0.0
		var states := []
		for shot in want_shot + 1:
			var target := (head.get_child(0) as Node3D).global_position if head.get_child_count() > 0 else head.global_position
			var err: float = await _steer_to(target, 90)
			gun.set("magazine", 30)
			var n0 := hits.size()
			Input.action_press("fire")
			await _tick(2)
			Input.action_release("fire")
			await _tick(40)
			states.append(_panes(dm))
			if hits.size() > n0 and got < 0:
				got = shot
				got_dmg = hits[n0]
			print("  shot %d  aim err %.3f deg  occupant hits %d  windows: %s" % [shot + 1, err, hits.size() - n0, states[-1]])
		if control:
			_check("CONTROL: %s -- nothing reaches the occupant" % c[0], got < 0, str(got))
			continue
		_check("%s through armour %.0f: the occupant is first hit on pull %d" % [c[0], armor, want_shot + 1], got == want_shot,
				"got pull %d" % [got + 1])
		# the first hit carries what the glass left of the round, times the bone's multiplier (Health's table)
		if int(c[2]) == 1:
			var ok := false
			for m in [4.0, 1.0, 0.75, 0.5]:
				ok = ok or absf(got_dmg - want_carry * m) < 0.05
			_check("...with what the glass left of the round (%.0f x the bone)" % want_carry, ok, "hit %.2f" % got_dmg)
		_check("...and the window is broken", "=3" in states[-1], states[-1])
		if ci == 1:
			var mask1 := int(dm.call("part_mask_now"))
			_check("the broken window is in the replicated mask", mask1 != mask0, "%x -> %x" % [mask0, mask1])
			var twin: RigidBody3D = (load("res://src/main/resources/com/openworld/vehicle/%s.tscn" % car_id) as PackedScene).instantiate()
			twin.position = Vector3(at_x, 1.2, 60)
			world.add_child(twin)
			await _tick(10)
			var tdm: Node = twin.get_node("DamageModel")
			tdm.call("apply_replicated_mask", mask1)
			_check("a peer applying the mask breaks the same window", _panes(tdm) == states[-1], "%s vs %s" % [_panes(tdm), states[-1]])
	if not control:
		print("== %s  a blast 3 m from the driver's door" % car_id)
		var em: Node = load(EXPLOSION).new()
		world.add_child(em)
		var bcar: RigidBody3D = (load("res://src/main/resources/com/openworld/vehicle/%s.tscn" % car_id) as PackedScene).instantiate()
		bcar.position = Vector3(80, 1.2, 0)
		world.add_child(bcar)
		var bai: Node3D = (load(AI) as PackedScene).instantiate()
		bai.position = Vector3(80, 0.5, 8)
		world.add_child(bai)
		bai.get_node("Health").set("max_health", 1.0e9)
		var bhits: Array = []
		bai.get_node("Health").connect("hit", func(dmg): bhits.append(dmg))
		await _tick(90)
		helper.call("seat_character", bcar, bai)
		await _tick(40)
		bcar.freeze = true
		var bdm: Node = bcar.get_node("DamageModel")
		var bhead := _find(bai, "Physical Bone head_2") as PhysicalBone3D
		var bside := signf(bcar.to_local(bhead.global_position).x)
		var at := bcar.to_global(Vector3(bside * 3.0, 0.0, bcar.to_local(bhead.global_position).z))
		helper.call("blast", em, at, 7.0, 220.0)
		await _tick(10)
		var st := _panes(bdm)
		print("  windows: %s  occupant hits %d" % [st, bhits.size()])
		_check("a blast beside the car breaks the window nearest it", "=3" in st, st)
		_check("...and the people inside are caught by the blast", bhits.size() > 0, str(bhits))
	print("RESULT %s (%d passed, %d failed)" % ["PASS" if fails == 0 else "FAIL", checks - fails, fails])
	quit(0 if fails == 0 else 1)
