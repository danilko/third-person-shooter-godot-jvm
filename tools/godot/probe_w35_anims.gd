extends SceneTree
## W35 gate: the Universal Animation Library clips wired into the game.
##
##   godot --headless --path . --script tools/godot/probe_w35_anims.gd
##
## Real bodies on a bare stand, driven through the shipped paths:
##   1. JUMP — the ground jump rises ~1 m (W36). (A ledge climb was gated here; it was removed in W39.)
##   2. HIT REACTION — a weapon hit on an AI fires the HitReact one-shot, `hit_head` for a head-bone
##      hit, and a killing hit fires none (the ragdoll takes the body).
##   3. THROW — FRG1 thrown through `fire` plays `attack_throw` on the Attack one-shot.
##   4. PASSENGER — a seated passenger's tree is on "Passenger", the driver's on "DriveCarrier".
##   5. BLAST DEATH — a body killed by a blast is thrown by it (its pelvis moves), not dropped.
## W36: the ground jump is ~1 m; the throwable's trajectory preview shows while aimed and the grenade
##      lands where it says; at full range it lands (2.5 s fuse) rather than bursting in the air.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const AI     := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const CAR    := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
const FRG1   := "res://src/main/resources/com/openworld/weapon/FRG1.tscn"
const IMPACT := "res://src/main/java/com/openworld/world/manager/ImpactManager.java"
const EXPL   := "res://src/main/java/com/openworld/world/manager/ExplosionManager.java"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const THROW_SLOT := 5

var fails := 0
var world: Node3D
var helper: Node
var im: Node
var em: Node

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-46s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _find(n: Node, nm: String) -> Node:
	if n.name == nm:
		return n
	for c in n.get_children():
		var r: Node = _find(c, nm)
		if r != null:
			return r
	return null

func _box(size: Vector3, pos: Vector3) -> StaticBody3D:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var bx := BoxShape3D.new()
	bx.size = size
	cs.shape = bx
	b.add_child(cs)
	world.add_child(b)
	b.global_position = pos
	return b

func _tree(n: Node) -> AnimationTree:
	return _find(n, "AnimationTree") as AnimationTree

func _still(ai: Node3D) -> void:
	ai.set_physics_process(false)
	var mc: Node = ai.get_node_or_null("MovementController")
	if mc != null:
		mc.set_physics_process(false)

## Put the player at `pos`, press jump, and report the highest point over 1.2 s.
func _jump_at(p: Node3D, pos: Vector3) -> Dictionary:
	p.global_position = pos
	p.set("velocity", Vector3.ZERO)
	await _tick(20)
	var peak := -1e9
	Input.action_press("jump")
	for i in range(72):
		await physics_frame
		if i == 2:
			Input.action_release("jump")
		peak = maxf(peak, p.global_position.y)
	Input.action_release("jump")
	await _tick(30)
	return {"end": p.global_position, "peak": peak}

## Kill an AI with a blast 1.5 m to its -X side; return how far its pelvis moved in 0.5 s.
func _blast_victim(at: Vector3, push: float) -> Vector3:
	var v: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	world.add_child(v)
	v.global_position = at
	await _tick(30)
	_still(v)
	var pelvis: Node3D = _find(v, "Physical Bone pelvis") as Node3D
	if pelvis == null:
		return Vector3.ZERO
	var p0: Vector3 = pelvis.global_position
	helper.call("blast_push", em, at + Vector3(-1.5, 0.25, 0), 6.0, 5000.0, push)
	await _tick(30)
	return pelvis.global_position - p0

## Follow a thrown grenade until it goes off; return the last place it was (its detonation point).
func _fly(pr: Node3D, holder: Node3D = null, pitch: float = 0.0) -> Vector3:
	var last := pr.global_position if pr != null else Vector3.INF
	for i in range(260):
		if holder != null:
			helper.call("set_view_pitch", holder, pitch)
		await physics_frame
		if pr == null or not is_instance_valid(pr) or not pr.is_inside_tree():
			break
		last = pr.global_position
	return last

func _initialize() -> void:
	world = Node3D.new()
	root.add_child(world)
	current_scene = world                            # a thrown grenade spawns into the current scene
	_box(Vector3(300, 1, 300), Vector3(0, -0.5, 0))
	im = load(IMPACT).new()
	em = load(EXPL).new()
	helper = load(HELPER).new()
	world.add_child(im)
	world.add_child(em)
	world.add_child(helper)
	await _tick(3)

	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.global_position = Vector3(0, 0.05, 0)
	await _tick(40)

	# ── 1. jump ────────────────────────────────────────────────────────────────────────────────
	print("\n=== 1. jump ===")
	# W36: the ground jump is ~1.0 m (it was 4.0): measured on open floor.
	var j := await _jump_at(p, Vector3(30, 0.05, 0))
	var rise: float = j.peak - 0.05
	_check("W36: the ground jump rises about 1.0 m", rise > 0.85 and rise < 1.15, "rise %.2f m" % rise)

	# ── 2. hit reaction ────────────────────────────────────────────────────────────────────────
	print("\n=== 2. hit reaction ===")
	p.global_position = Vector3(40, 0.05, 0)
	var ai: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	world.add_child(ai)
	ai.global_position = Vector3(40, 0.05, -4)
	await _tick(30)
	_still(ai)
	var at := _tree(ai)
	helper.call("weapon_hit", im, ai, 5.0)
	await _tick(2)
	_check("a body hit fires HitReact", at.get("parameters/HitReact/active"),
		"active=%s" % at.get("parameters/HitReact/active"))
	_check("...with hit_chest", str(at.get("parameters/HitReactClip/current_state")) == "hit_chest",
		"clip=%s" % at.get("parameters/HitReactClip/current_state"))
	await _tick(40)
	var head: Node = _find(ai, "Physical Bone head_2")
	if head != null:
		helper.call("weapon_hit", im, head, 1.0)
		await _tick(2)
		_check("a head-bone hit plays hit_head", str(at.get("parameters/HitReactClip/current_state")) == "hit_head",
			"clip=%s" % at.get("parameters/HitReactClip/current_state"))
	else:
		_check("a head-bone hit plays hit_head", false, "no 'Physical Bone head_2'")
	await _tick(40)
	helper.call("kill", ai)
	await _tick(2)
	_check("a killing hit plays no flinch", not at.get("parameters/HitReact/active"),
		"active=%s" % at.get("parameters/HitReact/active"))

	# ── 3. throw ───────────────────────────────────────────────────────────────────────────────
	print("\n=== 3. throw ===")
	p.global_position = Vector3(60, 0.05, 0)
	await _tick(10)
	var nade: Node3D = (load(FRG1) as PackedScene).instantiate() as Node3D
	world.add_child(nade)
	nade.global_position = Vector3(64, 1, 0)
	await _tick(3)
	(nade.get_parent() as Node3D).global_position = p.global_position + Vector3(0, 0.6, 0)
	await _tick(20)
	var wc: Node = p.get_node("WeaponController")
	wc.call("on_set_weapon", THROW_SLOT)
	await _tick(60)
	var pt := _tree(p)
	Input.action_press("fire")
	var thrown := false
	var clip := ""
	for i in range(12):
		await physics_frame
		if i == 2:
			Input.action_release("fire")
		if pt.get("parameters/Attack/active"):
			thrown = true
			clip = str(pt.get("parameters/AttackClip/current_state"))
	Input.action_release("fire")
	_check("a grenade throw plays attack_throw", thrown and clip == "attack_throw", "active=%s clip=%s" % [thrown, clip])
	await _tick(200)                                     # let the grenade go off away from what follows

	# W36: the trajectory preview, against the grenade it predicts. First person forces combat, so
	# the arc shows with no button held; the view is level, so the throw is the long one (~14 m).
	var nade2: Node3D = (load(FRG1) as PackedScene).instantiate() as Node3D
	world.add_child(nade2)
	nade2.global_position = Vector3(64, 1, 0)
	await _tick(3)
	(nade2.get_parent() as Node3D).global_position = p.global_position + Vector3(0, 0.6, 0)
	await _tick(20)
	wc.call("on_set_weapon", THROW_SLOT)
	p.set("is_fps_mode", true)
	await _tick(60)
	_check("W36: the preview shows while a throwable is aimed", nade2.call("preview_shown_now"), "")
	var predicted: Vector3 = nade2.call("preview_end_now")
	var lands: bool = nade2.call("preview_lands_now")
	var before := {}
	for n in world.get_children():
		before[n.get_instance_id()] = true
	Input.action_press("fire")
	await _tick(2)
	Input.action_release("fire")
	await _tick(2)
	var proj: RigidBody3D = null
	for n in world.get_children():
		if not before.has(n.get_instance_id()) and n is RigidBody3D:
			proj = n
	var last: Vector3 = await _fly(proj)
	var dist := Vector2(last.x - predicted.x, last.z - predicted.z).length()
	_check("W36: the preview says it lands (no air burst at full range)", lands, "lands=%s end=%s" % [lands, predicted])
	_check("W36/W38: it goes off where the preview's disc is (< 0.3 m)", dist < 0.3,
		"predicted (%.2f, %.2f) actual (%.2f, %.2f) -- %.2f m" % [predicted.x, predicted.z, last.x, last.z, dist])
	p.set("is_fps_mode", false)
	await _tick(200)

	# W37: CS 1.6's throw -- aiming up throws harder and further. Throw at three view pitches and
	# measure where each grenade first comes down; the longest must pass 30 m (the old fixed throw
	# managed ~14 m), and every one must land where its own preview said.
	p.set("is_fps_mode", true)
	var ranges := []
	for pitch in [0.0, 20.0, 40.0]:
		var g: Node3D = (load(FRG1) as PackedScene).instantiate() as Node3D
		world.add_child(g)
		g.global_position = Vector3(64, 1, 0)
		await _tick(3)
		(g.get_parent() as Node3D).global_position = p.global_position + Vector3(0, 0.6, 0)
		await _tick(20)
		wc.call("on_set_weapon", THROW_SLOT)
		for i in range(60):
			helper.call("set_view_pitch", p, pitch)
			await physics_frame
		var pred: Vector3 = g.call("preview_end_now")
		var seen := {}
		for n in world.get_children():
			seen[n.get_instance_id()] = true
		Input.action_press("fire")
		await _tick(2)
		Input.action_release("fire")
		await _tick(2)
		var pr: RigidBody3D = null
		for n in world.get_children():
			if not seen.has(n.get_instance_id()) and n is RigidBody3D:
				pr = n
		var hitp: Vector3 = await _fly(pr, p, pitch)
		var r := Vector2(hitp.x - p.global_position.x, hitp.z - p.global_position.z).length()
		var err := Vector2(hitp.x - pred.x, hitp.z - pred.z).length()
		ranges.append(r)
		_check("W37: pitch %2d throw goes off where its preview said" % int(pitch), err < 0.3,
			"range %.1f m, preview off by %.2f m" % [r, err])
		await _tick(160)
	_check("W37: aiming up throws further (CS 1.6)", ranges[1] > ranges[0] + 3.0 and ranges[2] > ranges[1],
		"ranges %s" % str(ranges))
	_check("W37: the long throw passes 30 m", ranges[2] > 30.0, "%.1f m" % ranges[2])
	helper.call("set_view_pitch", p, 0.0)
	p.set("is_fps_mode", false)
	await _tick(60)

	# ── 4. passenger ───────────────────────────────────────────────────────────────────────────
	print("\n=== 4. passenger ===")
	var car: Node3D = (load(CAR) as PackedScene).instantiate() as Node3D
	world.add_child(car)
	car.global_position = Vector3(80, 0.98, 0)
	car.set("freeze", true)
	await _tick(10)
	var drv: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	var pas: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	world.add_child(drv)
	world.add_child(pas)
	drv.global_position = Vector3(84, 0.05, 0)
	pas.global_position = Vector3(86, 0.05, 0)
	await _tick(20)
	helper.call("seat_driver", car, drv)
	helper.call("seat_passenger", car, pas, 1)
	await _tick(20)
	var ds := str(_tree(drv).get("parameters/StanceTransition/current_state"))
	var ps := str(_tree(pas).get("parameters/StanceTransition/current_state"))
	_check("the driver sits on DriveCarrier (hands on the wheel)", ds == "DriveCarrier", "state=%s" % ds)
	_check("a passenger sits on Passenger (sit_idle)", ps == "Passenger", "state=%s" % ps)

	# ── 5. blast death ─────────────────────────────────────────────────────────────────────────
	print("\n=== 5. blast death ===")
	# Two bodies killed by the same blast, 20 m apart; one with the blast's push and one without.
	var pushed := await _blast_victim(Vector3(100, 0.05, 0), 400.0)
	var dropped := await _blast_victim(Vector3(120, 0.05, 0), 0.0)
	_check("a blast kill throws the body away from the blast", pushed.x > dropped.x + 0.5,
		"pelvis dx %.2f m with the push vs %.2f without (moved %s vs %s)" % [pushed.x, dropped.x, pushed, dropped])

	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
