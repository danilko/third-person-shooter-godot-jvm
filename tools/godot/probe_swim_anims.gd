extends SceneTree
## Gate for PLAN.md 6.4: Swim plays its OWN branch, two postures (tread upright / stroke horizontal).
##
##   godot --headless --path . --script tools/godot/probe_swim_anims.gd [-- --control]
##
## A real Player in a real WaterVolume, driven through Input. Asserts: the body swims and the tree is on
## the "Swim" input; at rest it TREADS (the trunk near vertical); holding forward it STROKES (the trunk
## near horizontal); letting go treads again; and holding aim while moving forward TREADS (a swimmer
## aims with head and chest out of the water). `-- --control` puts the old borrowed key back
## (animation_stance_key = "Crawl"): the body is prone at rest and never strokes, and the gate fails.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const SWIM_ORDINAL := 4   # movement.character.StanceName.SWIM
const TREAD_MAX_DEG := 45.0
const STROKE_MIN_DEG := 55.0

var fails := 0
var control := false

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-48s %s" % ["PASS" if ok else "FAIL", label, detail])

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

func _attach(sk: Skeleton3D, bone: String) -> BoneAttachment3D:
	var a := BoneAttachment3D.new()
	sk.add_child(a)
	a.bone_name = bone
	return a

## Degrees between the trunk (pelvis -> head) and world up, averaged over 30 frames (a stroke cycles).
func _trunk_tilt(pelvis: Node3D, head: Node3D) -> float:
	var sum := 0.0
	for i in range(30):
		await physics_frame
		var v: Vector3 = head.global_position - pelvis.global_position
		sum += rad_to_deg(v.angle_to(Vector3.UP))
	return sum / 30.0

func _initialize() -> void:
	control = OS.get_cmdline_user_args().has("--control")
	print("[swim] %s" % ("CONTROL: Swim borrows Crawl's ring" if control else "Swim's own branch"))
	var world := Node3D.new()
	root.add_child(world)
	await process_frame
	var floor := StaticBody3D.new()
	var fcs := CollisionShape3D.new()
	var fbox := BoxShape3D.new()
	fbox.size = Vector3(200, 1, 200)
	fcs.shape = fbox
	floor.add_child(fcs)
	world.add_child(floor)
	floor.global_position = Vector3(0, -0.5, 0)
	var water: Area3D = load("res://src/main/java/com/openworld/world/WaterVolume.java").new()
	water.collision_layer = 0
	water.collision_mask = 2
	var wcs := CollisionShape3D.new()
	var wbox := BoxShape3D.new()
	wbox.size = Vector3(200, 6, 200)
	wcs.shape = wbox
	water.add_child(wcs)
	world.add_child(water)
	water.global_position = Vector3(0, 0, 0)   # top at y 3, floor at y 0

	var p: Node3D = load(PLAYER).instantiate()
	if control:
		var sw: Node = p.get_node_or_null("Stances/Swim")
		sw.set("animation_stance_key", "Crawl")
	world.add_child(p)
	p.global_position = Vector3(0, 1.2, 0)
	await _tick(90)

	var ac: Node = _find(p, "AnimationController")
	var tree: AnimationTree = _find(p, "AnimationTree") as AnimationTree
	var sk: Skeleton3D = _find(p, "Skeleton3D") as Skeleton3D
	var pelvis := _attach(sk, "pelvis")
	var head := _attach(sk, "head_2" if sk.find_bone("head_2") >= 0 else "head")
	await _tick(2)

	_check("the body is swimming", int(p.get("stance_ordinal")) == SWIM_ORDINAL,
		"stance ordinal %d" % int(p.get("stance_ordinal")))
	var state: String = str(tree.get("parameters/StanceTransition/current_state"))
	_check("the tree is on the Swim input", state == "Swim", "StanceTransition = %s" % state)

	var t: float = await _trunk_tilt(pelvis, head)
	_check("at rest it treads (trunk upright)", t < TREAD_MAX_DEG and str(ac.call("swim_posture_now")) == "Tread",
		"trunk %.1f deg off vertical, posture '%s'" % [t, ac.call("swim_posture_now")])

	Input.action_press("forward")
	await _tick(40)
	t = await _trunk_tilt(pelvis, head)
	_check("holding forward it strokes (trunk horizontal)", t > STROKE_MIN_DEG and str(ac.call("swim_posture_now")) == "Stroke",
		"trunk %.1f deg off vertical, posture '%s'" % [t, ac.call("swim_posture_now")])

	Input.action_press("aim")
	await _tick(40)
	t = await _trunk_tilt(pelvis, head)
	_check("aiming while moving forward it treads", t < TREAD_MAX_DEG and str(ac.call("swim_posture_now")) == "Tread",
		"trunk %.1f deg off vertical, posture '%s'" % [t, ac.call("swim_posture_now")])
	Input.action_release("aim")
	Input.action_release("forward")
	await _tick(90)
	t = await _trunk_tilt(pelvis, head)
	_check("letting go it treads again", t < TREAD_MAX_DEG and str(ac.call("swim_posture_now")) == "Tread",
		"trunk %.1f deg off vertical, posture '%s'" % [t, ac.call("swim_posture_now")])

	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails > 0 else 0)
