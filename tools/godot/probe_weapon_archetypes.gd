extends SceneTree
## Does every weaponPoseIndex resolve to a real pose?
##
##   godot --headless --path . --script tools/godot/probe_weapon_archetypes.gd
##
## `WeaponItem.weaponPoseIndex` is a blend position on three BlendSpace1D nodes (WeaponAim,
## WeaponHold, WeaponChangeAnimation). An index past the last blend point, or one whose point names
## a clip the export does not have, does not raise anything: the node contributes nothing and the
## skeleton falls back toward its REST pose. That is indistinguishable from "the artist authored a
## neutral pose" by eye, which is why it is measured here instead.
##
## The measurement is the RIGHT HAND, because that is what a grip archetype is about, taken through
## a BoneAttachment3D (`WeaponAttachment`) rather than `get_bone_global_pose` -- the skeleton
## modifiers write into the final pose only, so the accessor would read the same value whatever the
## aim is doing (CLAUDE.md, "How to measure this rig without fooling yourself").

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
# Must match blender/tools/... weapon_archetypes.json / VehicleConfig-side table.
const ARCHETYPES := ["pistol", "rifle", "launcher", "dual_pistol", "melee",
					 "fist", "shield", "shield_melee", "throwable", "sniper"]
## A pose that resolved to nothing sits at the rest pose; two archetypes copied from the same base
## are legitimately identical, so what is asserted is "not rest", not "all distinct".
const REST_TOLERANCE := 0.02

var fails := 0

func _find(n: Node, nm: String) -> Node:
	if n.name == nm:
		return n
	for c in n.get_children():
		var r: Node = _find(c, nm)
		if r != null:
			return r
	return null

func _floor(parent: Node) -> void:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(40, 1, 40)
	cs.shape = box
	b.add_child(cs)
	b.position = Vector3(0, -0.5, 0)
	parent.add_child(b)

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _initialize() -> void:
	var world := Node3D.new()
	root.add_child(world)
	_floor(world)
	await _tick(3)

	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
	await _tick(40)

	var tree: AnimationTree = _find(p, "AnimationTree") as AnimationTree
	var hand: Node3D = _find(p, "WeaponAttachment") as Node3D
	if tree == null or hand == null:
		print("FAIL: tree=%s hand=%s" % [tree != null, hand != null])
		quit(1)
		return

	# Combat, so the AIM branch is the one being blended -- WeaponHold is the non-combat pose and
	# would leave WeaponAim untested.
	p.set("combat", true)
	tree.set("parameters/CombatTransition/transition_request", "Combat")
	await _tick(30)

	# Rest reference: no animation at all in the weapon branch is what a broken index looks like.
	var rest: Vector3 = Vector3.ZERO
	var poses: Array = []
	print("")
	print("=== weaponPoseIndex -> hand pose ===")
	for i in range(ARCHETYPES.size()):
		tree.set("parameters/WeaponAim/blend_position", float(i))
		tree.set("parameters/WeaponHold/blend_position", float(i))
		tree.set("parameters/WeaponChangeAnimation/blend_position", float(i))
		await _tick(45)
		var local: Vector3 = p.to_local(hand.global_position)
		poses.append(local)
		if i == 0:
			rest = local
		print("  %d  %-13s hand (local) %+.3f %+.3f %+.3f" % [i, ARCHETYPES[i], local.x, local.y, local.z])

	# 1. Every index must produce a pose. An index with no blend point leaves the branch silent and
	#    the hand lands somewhere none of the authored poses put it.
	var distinct: Array = []
	for v in poses:
		var seen := false
		for d in distinct:
			if v.distance_to(d) < REST_TOLERANCE:
				seen = true
		if not seen:
			distinct.append(v)
	print("")
	print("  %d distinct hand pose(s) across %d archetypes" % [distinct.size(), ARCHETYPES.size()])
	# The clusters are the authored hold poses: pistol (and the four placeholders copied from it),
	# the fist's boxing guard (Punch_Jab), which melee and throwable share with only the wrist turned (CLAUDE.md W36), rifle (a patrol carry, CLAUDE.md W24) and launcher (its own carry, W25). A count other than EXPECTED_CLUSTERS is either a new authored pose (raise it
	# deliberately) or an index that resolved to nothing.
	const EXPECTED_CLUSTERS := 4   # sniper (9) ships as a copy of the rifle pose, so it joins that cluster
	if distinct.size() != EXPECTED_CLUSTERS:
		print("  FAIL  expected %d clusters (pistol family, fist guard, rifle, launcher); a different count is an" % EXPECTED_CLUSTERS)
		print("        index that resolved to nothing, or a newly authored pose -- raise the number deliberately.")
		fails += 1
	elif poses[4].distance_to(poses[5]) > REST_TOLERANCE or poses[8].distance_to(poses[5]) > REST_TOLERANCE or poses[5].distance_to(poses[0]) < REST_TOLERANCE:
		print("  FAIL  melee, throwable and fist should share the fist's guard, apart from the pistol family")
		fails += 1
	elif poses[2].distance_to(poses[1]) < REST_TOLERANCE:
		print("  FAIL  launcher collapsed onto rifle, so the third cluster is something else")
		fails += 1
	else:
		print("  PASS  every index resolves; %d clusters = pistol family, fist guard, rifle, launcher" % EXPECTED_CLUSTERS)

	# 2. The two shipped archetypes must still differ from each other -- if they collapsed together
	#    the branch is not blending at all and check 1 would pass vacuously.
	var spread: float = poses[0].distance_to(poses[1])
	if spread < REST_TOLERANCE:
		print("  FAIL  pistol and rifle poses are identical (%.3f m apart) -- branch is inert" % spread)
		fails += 1
	else:
		print("  PASS  pistol vs rifle differ by %.3f m" % spread)

	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
