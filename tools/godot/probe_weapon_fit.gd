extends SceneTree
## Does a long gun's stock sit in the shoulder pocket when aimed, and below the shoulder when held?
##
##   godot --headless --fixed-fps 60 --path . --script tools/godot/probe_weapon_fit.gd
##
## PLAN.md A1. W20 put every long gun's GRIP on the palm (0.042 m) and left the stock wherever the arm
## pose puts it: the rifle aim clip holds the hand ~0.17 m in front of the shoulder where a shouldered
## stock needs ~0.27 m (grip-to-butt), so the butt pad ends up BEHIND the shoulder joint. That is an
## authored-pose defect (A2 re-authors the clips), and this probe is its target -- it is written first
## and is EXPECTED TO FAIL on the poses that ship today.
##
## What is measured, for each stocked weapon in the table below:
##   - `StockPoint`, a Marker3D on the weapon at the centre of the butt pad (measured off each model's
##     side silhouette in its .blend; see the weapon scenes).
##   - the SHOULDER POCKET: the hollow in front of the shoulder joint, inboard of the deltoid, where a
##     butt pad actually rests. It is a fixed offset from `upperarm_r`, carried in `clavicle_r`'s frame
##     so it follows the shoulder when the aim modifier rolls it. The offset was DERIVED from the
##     character's own skinned mesh, not guessed: in the hold pose (no aim modifier active, arm hanging
##     clear) the frontmost `armor` skin vertex in a column 2-7 cm inboard of the joint and 0-4 cm below
##     it. The probe re-derives it every run and fails if the mesh has moved away from the written
##     constant, because a new body (W18) invalidates the number silently.
##
## Assertions, in MeshRoot's frame (the mesh is -Z forward):
##   aim  : StockPoint within STOCK_TOLERANCE of the pocket
##   hold : StockPoint below the shoulder joint (a low ready, stock by the hip/armpit, muzzle down)
##
## Every bone is read through a BoneAttachment3D (the FINAL pose, after the aim modifiers). The one
## exception is the pocket derivation, which skins vertices by hand from `get_bone_global_pose` -- the
## PRE-modifier pose -- and is therefore only ever done in the hold pose, where no modifier is running.
## (`MeshInstance3D.bake_mesh_from_current_skeleton_pose` is refused headless: "The source mesh must
## have its skin registered with a valid skeleton".)
##
## Weapons are equipped the game's way: dropped on the Player (auto-pickup into the free PRIMARY slot)
## and selected with `on_set_weapon` until the item hangs off a `Socket*`. `aim` is held through the
## real Input singleton so PlayerController -> combat -> the aim branch is what runs.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const WEAPONS := ["AR4", "AR212", "SG1"]
const WEAPON_DIR := "res://src/main/resources/com/openworld/weapon/%s.tscn"

## The shoulder pocket relative to `upperarm_r`, in `clavicle_r`'s orthonormalised global basis.
## Derived 2026-09-14 on CharacterVisuals_GodotChan (see header); body frame it reads as
## 4.3 cm inboard, 3.3 cm below and 8.6 cm in front of the joint centre. The OWNER is
## `StockMountIKModifier.pocketOffset` (PLAN.md A2.2), which this probe reads when the body has one;
## the constant is only the fallback for a body without the modifier.
const POCKET_IN_CLAVICLE := Vector3(-0.0280, -0.0419, 0.0880)
## Gun yaw off the aim line allowed in the aim pose (A2.1 aims the bore itself, so this is ~0).
const GUN_ON_AIM_DEG := 2.0
## How far the live derivation may drift from the constant before the constant is called stale.
const POCKET_DRIFT_TOLERANCE := 0.015
## A butt pad is ~12 cm tall and the pocket is a hollow, not a point: 4 cm is "on it".
const STOCK_TOLERANCE := 0.04
const SETTLE_FRAMES := 90

## `-- --visuals=res://...CharacterVisuals_X.tscn` measures another body or an exported pose study.
var visuals_path := ""
## `-- --aim-reference=chest` turns off A2.1's gun-referenced aim on both aim modifiers (the control).
var chest_reference := false
## `-- --stock-weight=0` sets StockMountIKModifier.max_weight (0 is the A2.2 control: the clip's arm).
var stock_weight := -1.0
## `-- --torso-layer=off` turns off Stance.weapon_torso_layer on Upright (the A2.3 control).
var torso_layer_off := false

var fails := 0

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-42s %s" % ["PASS" if ok else "FAIL", label, detail])

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

func _floor(parent: Node) -> void:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(200, 1, 200)
	cs.shape = box
	b.add_child(cs)
	b.position = Vector3(0, -0.5, 0)
	parent.add_child(b)

func _attach(sk: Skeleton3D, bone: String) -> BoneAttachment3D:
	var a := BoneAttachment3D.new()
	sk.add_child(a)
	a.bone_name = bone
	return a

func _v(v: Vector3) -> String:
	return "(%+.3f, %+.3f, %+.3f)" % [v.x, v.y, v.z]

## Body-frame components of an offset: + lateral = right, + up, + fwd = toward the aim (-Z).
func _parts(d: Vector3) -> String:
	return "right %+.3f  up %+.3f  fwd %+.3f" % [d.x, d.y, -d.z]

## The frontmost skin vertex of `mesh` in a column just inboard of and below the shoulder joint,
## in MeshRoot's frame. Hand-skinned from the PRE-modifier pose, so call it only in the hold pose.
func _skin_pocket(sk: Skeleton3D, mesh: MeshInstance3D, to_body: Transform3D, joint: Vector3) -> Vector3:
	var skin: Skin = mesh.skin
	var binds: Array[Transform3D] = []
	for bi in skin.get_bind_count():
		var bone: int = skin.get_bind_bone(bi)
		if bone < 0:
			bone = sk.find_bone(skin.get_bind_name(bi))
		binds.append(to_body * sk.global_transform * sk.get_bone_global_pose(bone) * skin.get_bind_pose(bi))
	var best := Vector3(0, 0, INF)
	var side: float = signf(joint.x)
	for si in mesh.mesh.get_surface_count():
		var arr: Array = mesh.mesh.surface_get_arrays(si)
		var verts: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
		var bones: PackedInt32Array = arr[Mesh.ARRAY_BONES]
		var weights: PackedFloat32Array = arr[Mesh.ARRAY_WEIGHTS]
		var k: int = bones.size() / verts.size()
		for vi in verts.size():
			var w := Vector3.ZERO
			for j in k:
				var ww: float = weights[vi * k + j]
				if ww > 0.0:
					w += (binds[bones[vi * k + j]] * verts[vi]) * ww
			var inboard: float = absf(joint.x) - absf(w.x)
			if signf(w.x) == side and inboard > 0.02 and inboard < 0.07 \
					and w.y < joint.y and w.y > joint.y - 0.04 and w.z < best.z:
				best = w
	return best

## Spawn a Player, hand it `weapon_id`, and bring the weapon to the hand. Returns [player, gun] or [].
func _armed_player(world: Node3D, weapon_id: String, at: Vector3) -> Array:
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	if visuals_path != "":
		p.set("character_visuals", load(visuals_path))
	world.add_child(p)
	p.position = at
	await _tick(40)
	var gun: Node3D = (load(WEAPON_DIR % weapon_id) as PackedScene).instantiate() as Node3D
	world.add_child(gun)
	gun.global_position = p.global_position + Vector3(0, 0.3, 0)
	await _tick(30)
	var wc: Node = p.get_node_or_null("WeaponController")
	for slot in range(6):
		if String(gun.get_parent().name).begins_with("Socket"):
			break
		wc.call("on_set_weapon", slot)
		await _tick(50)
	if not String(gun.get_parent().name).begins_with("Socket"):
		print("  FAIL  %s never reached a hand socket (parent %s)" % [weapon_id, gun.get_parent().name])
		fails += 1
		return []
	return [p, gun]

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--visuals="):
			visuals_path = a.substr("--visuals=".length())
		elif a == "--aim-reference=chest":
			chest_reference = true
		elif a == "--torso-layer=off":
			torso_layer_off = true
		elif a.begins_with("--stock-weight="):
			stock_weight = float(a.substr("--stock-weight=".length()))
	print("visuals: %s" % ("(Player.tscn default)" if visuals_path == "" else visuals_path))
	print("aim reference: %s" % ("CHEST (control)" if chest_reference else "held weapon's bore"))
	if stock_weight >= 0.0:
		print("stock mount weight: %.2f" % stock_weight)
	if torso_layer_off:
		print("weapon torso layer: OFF (control)")
	var world := Node3D.new()
	root.add_child(world)
	_floor(world)
	await _tick(3)

	var x := 0.0
	var pocket_checked := false
	for weapon_id in WEAPONS:
		print("")
		print("=== %s ===" % weapon_id)
		var armed: Array = await _armed_player(world, weapon_id, Vector3(x, 1.2, 0))
		x += 6.0
		if armed.is_empty():
			continue
		var p: Node3D = armed[0]
		var gun: Node3D = armed[1]
		var stock: Node3D = gun.get_node_or_null("StockPoint") as Node3D
		if stock == null:
			_check("weapon declares a StockPoint", false, "no StockPoint marker on %s" % weapon_id)
			p.queue_free()
			continue

		var sk: Skeleton3D = _find(p, "Skeleton3D") as Skeleton3D
		for m in ["SpineAimModifier", "ShoulderAimModifier"]:
			var mod: Node = sk.get_node_or_null(m)
			if mod != null:
				mod.set("aim_held_weapon", not chest_reference)
		if torso_layer_off:
			var upright: Node = p.get_node_or_null("Stances/Upright")
			if upright != null:
				upright.set("weapon_torso_layer", false)
		var stock_mod: Node = sk.get_node_or_null("StockMountIKModifier")
		if stock_mod != null and stock_weight >= 0.0:
			stock_mod.set("max_weight", stock_weight)
		var pocket_offset: Vector3 = POCKET_IN_CLAVICLE if stock_mod == null else stock_mod.get("pocket_offset")
		var mesh_root: Node3D = _find(p, "MeshRoot") as Node3D
		var shoulder := _attach(sk, "upperarm_r")
		var clavicle := _attach(sk, "clavicle_r")
		var hand := _attach(sk, "hand_r")
		var middle := _attach(sk, "middle_01_r")
		var shoulder_l := _attach(sk, "upperarm_l")
		var hand_l := _attach(sk, "hand_l")
		var lowerarm_l := _attach(sk, "lowerarm_l")
		var head := _attach(sk, "head_2")

		# ── hold ─────────────────────────────────────────────────────────────────────────────
		Input.action_release("aim")
		await _tick(SETTLE_FRAMES)
		var to_body: Transform3D = mesh_root.global_transform.affine_inverse()
		var joint: Vector3 = to_body * shoulder.global_position
		var s_hold: Vector3 = to_body * stock.global_position
		print("  hold: stock rel shoulder joint  %s" % _parts(s_hold - joint))

		if not pocket_checked:
			pocket_checked = true
			var skin_pt: Vector3 = _skin_pocket(sk, sk.get_node("armor") as MeshInstance3D, to_body, joint)
			var cb: Basis = clavicle.global_transform.basis.orthonormalized()
			var live: Vector3 = cb.inverse() * (mesh_root.global_transform.basis * (skin_pt - joint))
			print("  pocket from the skin: body %s  -> clavicle frame %s  (constant %s)"
				% [_parts(skin_pt - joint), _v(live), _v(pocket_offset)])
			_check("pocket offset matches the mesh", live.distance_to(pocket_offset) < POCKET_DRIFT_TOLERANCE,
				"drift %.3f m" % live.distance_to(pocket_offset))

		_check("%s hold: stock below the shoulder" % weapon_id, s_hold.y < joint.y,
			"stock %+.3f m vs the joint" % (s_hold.y - joint.y))

		# ── aim ──────────────────────────────────────────────────────────────────────────────
		Input.action_press("aim")
		await _tick(SETTLE_FRAMES)
		_check("%s aim: in combat" % weapon_id, bool(p.get("combat")), "combat=%s" % p.get("combat"))
		to_body = mesh_root.global_transform.affine_inverse()
		joint = to_body * shoulder.global_position
		var cb_aim: Basis = clavicle.global_transform.basis.orthonormalized()
		var pocket: Vector3 = joint + mesh_root.global_transform.basis.inverse() * (cb_aim * pocket_offset)
		var s_aim: Vector3 = to_body * stock.global_position
		var palm: Vector3 = (to_body * hand.global_position + to_body * middle.global_position) * 0.5
		print("  aim : stock rel shoulder joint  %s" % _parts(s_aim - joint))
		print("  aim : stock rel pocket          %s" % _parts(s_aim - pocket))
		print("  aim : palm in front of joint    %.3f m" % (joint.z - palm.z))
		# Diagnostics for A2 (not asserted): how bladed the torso is, where the gun points, whether the
		# support hand still reaches, and where the eye line sits over the stock.
		var jl: Vector3 = to_body * shoulder_l.global_position
		var blade: float = rad_to_deg(atan2(joint.z - jl.z, joint.x - jl.x))
		var fwd: Vector3 = mesh_root.global_transform.basis.inverse() * (-gun.global_transform.basis.z)
		var gun_yaw: float = rad_to_deg(atan2(fwd.x, -fwd.z))
		var gun_pitch: float = rad_to_deg(asin(clampf(fwd.y, -1.0, 1.0)))
		var sp: Node3D = gun.get_node_or_null("SupportPoint") as Node3D
		var sup: String = "no SupportPoint"
		if sp != null:
			var elbow_l: Vector3 = lowerarm_l.global_position
			var arm_len: float = shoulder_l.global_position.distance_to(elbow_l) + elbow_l.distance_to(hand_l.global_position)
			sup = "%.3f m (left arm %.3f m long, SupportPoint %.3f m from its shoulder)" % [
				hand_l.global_position.distance_to(sp.global_position), arm_len,
				shoulder_l.global_position.distance_to(sp.global_position)]
		var hd: Vector3 = to_body * head.global_position
		print("  aim : blade (right shoulder behind left) %+.1f deg ; gun yaw %+.1f pitch %+.1f ; support hand %s"
			% [blade, gun_yaw, gun_pitch, sup])
		var tree: AnimationTree = _find(p, "AnimationTree") as AnimationTree
		print("  aim : head rel stock  %s ; spine modifier aimed the bore: %s ; torso layer %.2f"
			% [_parts(hd - s_aim), sk.get_node("SpineAimModifier").call("aimed_with_bore"),
				float(tree.get("parameters/WeaponTorsoBlend/blend_amount"))])
		if stock_mod != null:
			print("  aim : stock mount weight %.2f  hand moved %.3f m  shortfall %.3f m"
				% [stock_mod.call("current_weight"), stock_mod.call("last_hand_move"), stock_mod.call("last_shortfall")])
		_check("%s aim: gun on the aim line" % weapon_id, absf(gun_yaw) < GUN_ON_AIM_DEG,
			"gun yaw %+.1f deg (tolerance %.0f)" % [gun_yaw, GUN_ON_AIM_DEG])
		_check("%s aim: stock in the shoulder pocket" % weapon_id, s_aim.distance_to(pocket) < STOCK_TOLERANCE,
			"%.3f m off (tolerance %.2f)" % [s_aim.distance_to(pocket), STOCK_TOLERANCE])
		Input.action_release("aim")
		p.queue_free()
		await _tick(5)

	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
