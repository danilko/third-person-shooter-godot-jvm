extends SceneTree
## Blood on a hit body (2026-10-09, user: "the blood effect of a hit character is no longer there"): a real
## Player shot through WorldSystems.tscn's own ImpactManager + ParticleManager lands on an AI 25 m out and the
## FLESH pool bursts once, AT the hit (the emitter within 0.5 m of the chest) and emitting. The look is pictured
## by shot_impacts.gd (blood_12m / blood_25m); this gates that the real shot path still asks for it.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_blood_hit.gd
##

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const AI     := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const SNR1    := "res://src/main/resources/com/openworld/weapon/SNR1.tscn"
const SYSTEMS := "res://src/main/resources/com/openworld/world/WorldSystems.tscn"
const SENS := 0.07

var p: Node3D
var cam_ctrl: Node
var fails := 0

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-52s %s" % ["PASS" if ok else "FAIL", label, detail])

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

func _steer_to(target: Vector3, frames: int) -> void:
	for i in range(frames):
		var cam := p.get_node("ActiveCamera") as Node3D
		var to: Vector3 = target - cam.global_position
		var f := -cam.global_transform.basis.z
		var dy := wrapf(rad_to_deg(atan2(-to.x, -to.z)) - rad_to_deg(atan2(-f.x, -f.z)), -180.0, 180.0)
		var dp := rad_to_deg(atan2(to.y, Vector2(to.x, to.z).length())) - rad_to_deg(asin(clampf(f.y, -1.0, 1.0)))
		if absf(dy) + absf(dp) < 0.003:
			return
		var ev := InputEventMouseMotion.new()
		ev.relative = Vector2(-dy / SENS, -dp / SENS)
		cam_ctrl.call("_input", ev)
		await physics_frame

func _fire(gun: Node) -> void:
	gun.set("magazine", 5)
	Input.action_press("fire")
	await _tick(2)
	Input.action_release("fire")
	await _tick(8)

func _initialize() -> void:
	var world := Node3D.new()
	root.add_child(world)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(400, 2, 400)
	cs.shape = sh
	floor.add_child(cs)
	world.add_child(floor)
	floor.position = Vector3(0, -1, 0)
	var sys: Node = (load(SYSTEMS) as PackedScene).instantiate()
	for c in sys.get_children():
		if c.name in ["MenuManager", "HUDManager"]:
			c.free()
	world.add_child(sys)
	var pm: Node = sys.get_node("ParticleManager")
	await _tick(3)
	p = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
	await _tick(40)
	var gun: Node3D = (load(SNR1) as PackedScene).instantiate() as Node3D
	world.add_child(gun)
	gun.global_position = p.global_position + Vector3(0, 0.3, 0)
	await _tick(30)
	var wc: Node = p.get_node("WeaponController")
	for slot in range(7):
		if String(gun.get_parent().name).begins_with("Socket"):
			break
		wc.call("on_set_weapon", slot)
		await _tick(40)
	cam_ctrl = p.get_node("TPSCameraController")
	var t: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	t.get_node("Health").set("max_health", 1000.0)
	world.add_child(t)
	t.global_position = Vector3(0, 0, -25)
	t.global_rotation = Vector3(0, PI, 0)
	(t.get("character_info") as Resource).set("faction", "neutral")
	t.get_node("MovementController").set_physics_process(false)
	var att := BoneAttachment3D.new()
	att.bone_name = "spine_03"
	(_find(t, "Skeleton3D") as Skeleton3D).add_child(att)
	var hb := _find(t, "Physical Bone spine_03") as PhysicalBone3D
	await _tick(90)
	var dealt := []
	t.get_node("Health").connect("hit", func(d): dealt.append(d))
	Input.action_press("aim")
	await _tick(30)
	var chest: Vector3 = (att.global_transform * hb.body_offset).origin
	await _steer_to(chest, 90)
	await _tick(10)
	var f0 := int(pm.call("bursts_now", "FLESH"))
	var d0 := int(pm.call("bursts_now", "DEFAULT"))
	await _fire(gun)
	_check("the shot hit the body", dealt.size() == 1, str(dealt))
	_check("the hit bursts blood (FLESH) once", int(pm.call("bursts_now", "FLESH")) == f0 + 1,
		"FLESH +%d, DEFAULT +%d" % [int(pm.call("bursts_now", "FLESH")) - f0, int(pm.call("bursts_now", "DEFAULT")) - d0])
	var near := 1e9
	var lit := false
	for e in pm.get_node("FLESH").get_children():
		var em := e as GPUParticles3D
		var dd := em.global_position.distance_to(chest)
		if dd < near:
			near = dd
			lit = em.get_child_count() > 0 and em.get_child(0) is GPUParticles3D   # the droplet layer rides along
	_check("  ... at the hit, with its droplet layer", near < 0.5 and lit, "%.2f m from the chest, droplets %s" % [near, lit])
	Input.action_release("aim")
	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
