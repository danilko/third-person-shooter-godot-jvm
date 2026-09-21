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
## Every archetype's weapons (blender/tools/weapon_archetypes.json `holds`): rifles mount a StockPoint, the
## launcher a ShoulderRestPoint, the pistol mounts nothing and only has a support grip.
## The weapons with a hold row, off the one catalog (PLAN.md 2.8 item 7).
var WEAPONS: Array = _catalog_weapons(func(row, holds): return holds.has(row["archetype"]))

static func _catalog_weapons(keep: Callable) -> Array:
	var cat: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://src/main/resources/com/openworld/weapon/weapon_catalog.json"))
	var holds: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://blender/tools/weapon_archetypes.json"))["holds"]
	var out := []
	for row in cat["weapons"]:
		if keep.call(row, holds):
			out.append(row["id"])
	return out
const WEAPON_DIR := "res://src/main/resources/com/openworld/weapon/%s.tscn"

## The shoulder pocket relative to `upperarm_r`, in `clavicle_r`'s orthonormalised global basis.
## Derived 2026-09-14 on CharacterVisuals_GodotChan (see header); body frame it reads as
## 4.3 cm inboard, 3.3 cm below and 8.6 cm in front of the joint centre. The OWNER is
## `StockMountIKModifier.mount_offsets` for `StockPoint` (PLAN.md A2.2, W25), which this probe reads when the body has one;
## the constant is only the fallback for a body without the modifier.
const POCKET_IN_CLAVICLE := Vector3(-0.0280, -0.0419, 0.0880)
## Gun yaw off the aim line allowed in the aim pose (A2.1 aims the bore itself, so this is ~0).
const GUN_ON_AIM_DEG := 2.0
## How far the authored pocket may sit from the skin-derived one. Since W25 the pocket is AUTHORED (adopted from a
## rifle the artist placed in the pose), so this is "still on this body's shoulder", not "equal to the derivation".
const POCKET_DRIFT_TOLERANCE := 0.02
## A butt pad is ~12 cm tall and the pocket is a hollow, not a point: 4 cm is "on it".
const STOCK_TOLERANCE := 0.04
const SETTLE_FRAMES := 90

## `-- --visuals=res://...CharacterVisuals_X.tscn` measures another body or an exported pose study.
var visuals_path := ""
var emit_pocket := ""
## `-- --aim-reference=chest` turns off A2.1's gun-referenced aim on both aim modifiers (the control).
var chest_reference := false
## `-- --stock-weight=0` sets StockMountIKModifier.max_weight (0 is the A2.2 control: the clip's arm).
var stock_weight := -1.0
## `-- --torso-layer=off` turns off Stance.weapon_torso_layer on Upright (the A2.3 control).
var torso_layer_off := false
## `-- --stance=crouch|crawl|swim` holds (swim: builds a pool instead) that stance's input for the whole case (A2.5). Crawl does not mount the
## stock (Stance.stock_mount_enabled is off), so its stock/support lines are reported, not asserted.
var stance := "upright"
const SWIM_ORDINAL := 4   # movement.character.StanceName.SWIM
## `-- --torso-layer-on=Crouch` turns Stance.weapon_torso_layer ON for another stance (an A2.5 experiment).
var torso_layer_on := ""
## `-- --neck-front=off` holds the NeckFront layer at 0 (the artist's authored head pose instead of
## the T-pose). It is the measurement behind removing that layer: with the head aimed at the target
## on its own, the T-pose has nothing left to hide.
var neck_front_off := false

var fails := 0
var support_misses: Array[float] = []
## Support-hand grip tolerance in the aim pose, per weapon. The rifles' SupportPoints sit where this body's
## 0.416 m arm reaches (the rear of the handguard); SHG1's pump is further than that arm reaches with the
## stock shouldered (PLAN.md A2.4), so its number is a regression guard on the known shortfall, not a fit.
var support_limit := {"ASR1": 0.05, "ASR2": 0.05, "SHG1": 0.05, "SNR1": 0.05, "PIS1": 0.05, "REV1": 0.05, "SMG1": 0.05, "ATL1": 0.05}

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

## A bone's forward, in MeshRoot's frame. WHICH local axis is "forward" is a fact about the import,
## not something to assume (W1 cost a wrong conclusion by taking a bone PAIR instead), so it is read
## off the REST pose: the local axis whose rest direction lies closest to the mesh forward (-Z)
## wins, and its sign with it. The rest is in SKELETON space and the Skeleton3D node carries the
## glTF import's own orientation (W5), so it is brought into the body frame before being compared.
## `live` is the bone's FINAL basis, which must come from a BoneAttachment3D: a modifier writes into
## the final pose only, and `get_bone_global_pose` returns the pre-modifier one (and, in a headless
## `--script` run, the rest pose outright -- W41).
func _bone_forward(sk: Skeleton3D, bone: String, mesh_root: Node3D, live: Basis) -> Vector3:
	var to_body: Basis = mesh_root.global_transform.basis.inverse()
	var i: int = sk.find_bone(bone)
	if i < 0:
		return Vector3(0, 0, -1)
	var rest_axes: Basis = (to_body * sk.global_transform.basis * sk.get_bone_global_rest(i).basis).orthonormalized()
	var best := 0
	var flip := 1.0
	var score := -2.0
	for axis in range(3):
		for sign in [1.0, -1.0]:
			var d: float = (rest_axes[axis] * sign).dot(Vector3(0, 0, -1))
			if d > score:
				score = d
				best = axis
				flip = sign
	return ((to_body * live)[best] * flip).normalized()

func _v(v: Vector3) -> String:
	return "(%+.3f, %+.3f, %+.3f)" % [v.x, v.y, v.z]

## Body-frame components of an offset: + lateral = right, + up, + fwd = toward the aim (-Z).
func _parts(d: Vector3) -> String:
	return "right %+.3f  up %+.3f  fwd %+.3f" % [d.x, d.y, -d.z]

## The mesh the SHOULDER is part of. Asked of the skin, never by name: `armor` is what the mesh is
## called on Godot-chan and `Body` on a VRoid body, and a name lookup that misses simply errors
## halfway through the check.
func _torso_mesh(sk: Skeleton3D) -> MeshInstance3D:
	var want := {}
	for b in ["clavicle_r", "upperarm_r", "spine_03"]:
		var bi: int = sk.find_bone(b)
		if bi >= 0: want[bi] = true
	var best: MeshInstance3D = null
	var best_n := -1
	for c in sk.get_children():
		if not (c is MeshInstance3D): continue
		var mi: MeshInstance3D = c
		if mi.skin == null: continue
		var n := 0
		for si in mi.mesh.get_surface_count():
			var arr: Array = mi.mesh.surface_get_arrays(si)
			var bones: PackedInt32Array = arr[Mesh.ARRAY_BONES]
			for bi2 in bones:
				var bone: int = mi.skin.get_bind_bone(bi2)
				if bone < 0: bone = sk.find_bone(mi.skin.get_bind_name(bi2))
				if want.has(bone): n += 1
		if n > best_n:
			best_n = n
			best = mi
	return best

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
		if a.begins_with("--emit-pocket="): emit_pocket = a.substr(14)
		if a.begins_with("--visuals="):
			visuals_path = a.substr("--visuals=".length())
		elif a == "--aim-reference=chest":
			chest_reference = true
		elif a == "--torso-layer=off":
			torso_layer_off = true
		elif a.begins_with("--stance="):
			stance = a.substr("--stance=".length())
		elif a.begins_with("--torso-layer-on="):
			torso_layer_on = a.substr("--torso-layer-on=".length())
		elif a.begins_with("--stock-weight="):
			stock_weight = float(a.substr("--stock-weight=".length()))
		elif a == "--neck-front=off":
			neck_front_off = true
	print("visuals: %s" % ("(Player.tscn default)" if visuals_path == "" else visuals_path))
	print("stance: %s" % stance)
	print("aim reference: %s" % ("CHEST (control)" if chest_reference else "held weapon's bore"))
	if stock_weight >= 0.0:
		print("stock mount weight: %.2f" % stock_weight)
	if torso_layer_off:
		print("weapon torso layer: OFF (control)")
	var world := Node3D.new()
	root.add_child(world)
	_floor(world)
	if stance == "swim":
		# A pool over the whole row of stands: 3.5 m deep, so every body swims (A2.5 swim case).
		var water: Area3D = load("res://src/main/java/com/openworld/world/WaterVolume.java").new()
		water.collision_layer = 0
		water.collision_mask = 2
		var wcs := CollisionShape3D.new()
		var wbox := BoxShape3D.new()
		wbox.size = Vector3(200, 6, 60)
		wcs.shape = wbox
		water.add_child(wcs)
		world.add_child(water)
		water.global_position = Vector3(20, 0, 0)   # top at y 3, floor at y 0
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

		var sk: Skeleton3D = _find(p, "Skeleton3D") as Skeleton3D
		for m in ["SpineAimModifier", "ShoulderAimModifier"]:
			var mod: Node = sk.get_node_or_null(m)
			if mod != null:
				mod.set("aim_held_weapon", not chest_reference)
		if torso_layer_off:
			var upright: Node = p.get_node_or_null("Stances/Upright")
			if upright != null:
				upright.set("weapon_torso_layer", false)
		if torso_layer_on != "":
			var st_node: Node = p.get_node_or_null("Stances/%s" % torso_layer_on)
			if st_node != null:
				st_node.set("weapon_torso_layer", true)
		if stance != "upright" and stance != "swim":
			Input.action_press(stance)
		var stock_mod: Node = sk.get_node_or_null("StockMountIKModifier")
		if stock_mod != null and stock_weight >= 0.0:
			stock_mod.set("max_weight", stock_weight)
		# The mount this weapon uses: the modifier's first marker the weapon declares (W25), with its body anchor.
		var stock: Node3D = null
		var pocket_offset: Vector3 = POCKET_IN_CLAVICLE
		var stock_anchor: Vector3 = POCKET_IN_CLAVICLE
		var mount_name := ""
		if stock_mod != null:
			var names: Array = stock_mod.get("mount_markers")
			var offs: Array = stock_mod.get("mount_offsets")
			for i in range(mini(names.size(), offs.size())):
				if String(names[i]) == "StockPoint":
					pocket_offset = offs[i]
				if stock == null and gun.get_node_or_null(String(names[i])) != null:
					stock = gun.get_node(String(names[i])) as Node3D
					stock_anchor = offs[i]
					mount_name = String(names[i])
		print("  mount: %s" % ("none (the weapon declares no mount marker)" if stock == null else "%s -> anchor %s" % [mount_name, _v(stock_anchor)]))
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
		var s_hold: Vector3 = to_body * (stock.global_position if stock != null else gun.global_position)
		print("  hold: %s rel shoulder joint  %s" % [mount_name if stock != null else "grip", _parts(s_hold - joint)])

		# THE SUPPORT HAND RUNS IN THE HOLD TOO, and nothing measured it (user walk-test,
		# 2026-09-21: "SHG floats high with the support hand twisted, the pistol sinks"). The stock
		# mount stands down out of combat (W23), so the hold is the CLIP's arms plus this modifier
		# alone -- which is exactly where a short reach shows, and the aim-phase numbers cannot
		# stand in for it: the carry is across the body (W24) and the aim is out in front.
		var sp_h: Node3D = gun.get_node_or_null("SupportPoint") as Node3D
		var sup_h: Node = sk.get_node_or_null("SupportHandIKModifier")
		if sp_h != null:
			var elbow_h: Vector3 = lowerarm_l.global_position
			var arm_h: float = shoulder_l.global_position.distance_to(elbow_h) + elbow_h.distance_to(hand_l.global_position)
			var reach_h: float = shoulder_l.global_position.distance_to(sp_h.global_position)
			var miss_h: float = sup_h.call("last_grip_miss") if sup_h != null else -1.0
			var clav_h: float = sup_h.call("last_clavicle_deg") if sup_h != null else 0.0
			print("  hold: support grip %.3f m off, shoulder protracted %.1f deg (arm %.3f m, reach asked %.3f m, over %+.3f m)"
				% [miss_h, clav_h, arm_h, reach_h, reach_h - arm_h])

		if not pocket_checked and stance == "upright":  # the skin derivation is only valid in the upright hold
			pocket_checked = true
			var skin_pt: Vector3 = _skin_pocket(sk, _torso_mesh(sk), to_body, joint)
			var cb: Basis = clavicle.global_transform.basis.orthonormalized()
			var live: Vector3 = cb.inverse() * (mesh_root.global_transform.basis * (skin_pt - joint))
			print("  pocket from the skin: body %s  -> clavicle frame %s  (constant %s)"
				% [_parts(skin_pt - joint), _v(live), _v(pocket_offset)])
			_check("pocket offset matches the mesh", live.distance_to(pocket_offset) < POCKET_DRIFT_TOLERANCE,
				"drift %.3f m" % live.distance_to(pocket_offset))
			# `--emit-pocket=<file>` makes this probe the OWNER of the number instead of merely its
			# eye. `measure_body.gd` derives a first estimate off the rest rig, which is enough to
			# build a body's scene; this is the same rule measured on the body the game actually
			# poses, and a second measure/build round takes the anchor to it. Measured, the estimate
			# lands within 2 cm on two of the three bodies and 4.9 cm on the third, so it is a
			# bootstrap, not an answer.
			if emit_pocket != "":
				var fh := FileAccess.open(emit_pocket, FileAccess.WRITE)
				fh.store_string(JSON.stringify({"pocket": var_to_str(live),
					"measured_by": "tools/godot/probe_weapon_fit.gd", "visuals": visuals_path}, "  ", true) + "\n")
				fh.close()
				print("  wrote %s" % emit_pocket)

		if stance == "swim":
			_check("%s swim: the body is swimming" % weapon_id, int(p.get("stance_ordinal")) == SWIM_ORDINAL,
				"stance ordinal %d (SWIM = %d)" % [int(p.get("stance_ordinal")), SWIM_ORDINAL])
		if mount_name == "StockPoint" and stance != "swim":
			_check("%s hold: stock below the shoulder" % weapon_id, s_hold.y < joint.y,
				"stock %+.3f m vs the joint" % (s_hold.y - joint.y))

		# ── aim ──────────────────────────────────────────────────────────────────────────────
		Input.action_press("aim")
		await _tick(SETTLE_FRAMES)
		if neck_front_off:
			# AFTER combat is entered: AnimationController writes this parameter on the combat EDGE,
			# so setting it earlier is overwritten by the press above.
			(_find(p, "AnimationTree") as AnimationTree).set("parameters/NeckFront/blend_amount", 0.0)
			await _tick(20)
		_check("%s aim: in combat" % weapon_id, bool(p.get("combat")), "combat=%s" % p.get("combat"))
		to_body = mesh_root.global_transform.affine_inverse()
		joint = to_body * shoulder.global_position
		var cb_aim: Basis = clavicle.global_transform.basis.orthonormalized()
		var pocket: Vector3 = joint + mesh_root.global_transform.basis.inverse() * (cb_aim * stock_anchor)
		var s_aim: Vector3 = to_body * (stock.global_position if stock != null else gun.global_position)
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
		var sup_mod: Node = sk.get_node_or_null("SupportHandIKModifier")
		if sp != null:
			var elbow_l: Vector3 = lowerarm_l.global_position
			var arm_len: float = shoulder_l.global_position.distance_to(elbow_l) + elbow_l.distance_to(hand_l.global_position)
			# the modifier's own grip point (A2.4: SupportPoint is where the hand GRIPS, not the wrist)
			var miss: float = sup_mod.call("last_grip_miss") if sup_mod != null else -1.0
			# and how far the SUPPORT SHOULDER had to protract to get there (W44). It is the
			# left-shoulder over-bend number: a clavicle swung to force a contact reads as a shrug,
			# and GTA's own hand IK stops short instead.
			var clav_deg: float = sup_mod.call("last_clavicle_deg") if sup_mod != null else 0.0
			sup = "grip %.3f m off, support shoulder protracted %.1f deg (left arm %.3f m long, SupportPoint %.3f m from its shoulder)" % [
				miss, clav_deg, arm_len, shoulder_l.global_position.distance_to(sp.global_position)]
			support_misses.append(miss)
		var hd: Vector3 = to_body * head.global_position
		# Where the EYE LINE points, which is what an FPS camera rides (W5: the rig hangs off
		# `neck_01`). The gun is on the aim line by construction -- `ShoulderAimModifier` aims the
		# BORE (W23) -- so a clip rotation the arms carry and the spine does not is absorbed by the
		# clavicles and the NECK instead, and only the head shows it. Measured, never assumed: the
		# head bone's own forward is taken as the axis whose rest direction lands on the mesh
		# forward, the same derivation W1 records for `spine_03`.
		var hf: Vector3 = _bone_forward(sk, "head_2", mesh_root, head.global_transform.basis)
		var head_yaw: float = rad_to_deg(atan2(hf.x, -hf.z))
		# The head's ROLL: how far its own up leans off the world vertical. A look-at aims a
		# direction and says nothing about the twist about it, so this is what the T-pose layer was
		# also flattening and the number to watch when it goes.
		var head_up: Vector3 = head.global_transform.basis.y
		var head_roll: float = rad_to_deg(acos(clampf(head_up.normalized().dot(Vector3.UP), -1.0, 1.0)))
		print("  aim : blade (right shoulder behind left) %+.1f deg ; gun yaw %+.1f pitch %+.1f ; support hand %s"
			% [blade, gun_yaw, gun_pitch, sup])
		print("  aim : head yaw off aim %+.1f deg ; head tilt %.1f deg off vertical ; head %+.3f m right of the body centre line"
			% [head_yaw, head_roll, hd.x])
		var tree: AnimationTree = _find(p, "AnimationTree") as AnimationTree
		print("  aim : head rel stock  %s ; spine modifier aimed the bore: %s ; torso layer %.2f"
			% [_parts(hd - s_aim), sk.get_node("SpineAimModifier").call("aimed_with_bore"),
				float(tree.get("parameters/WeaponTorsoBlend/blend_amount"))])
		if stock_mod != null:
			print("  aim : stock mount weight %.2f  hand moved %.3f m  shortfall %.3f m"
				% [stock_mod.call("current_weight"), stock_mod.call("last_hand_move"), stock_mod.call("last_shortfall")])
		var mounts: bool = stance != "crawl" and stance != "swim"
		if not mounts:
			print("  (%s: the stock is not mounted by design; stock and support reported above, not asserted)" % stance)
		_check("%s aim: gun on the aim line" % weapon_id, absf(gun_yaw) < GUN_ON_AIM_DEG,
			"gun yaw %+.1f deg (tolerance %.0f)" % [gun_yaw, GUN_ON_AIM_DEG])
		if mounts and sp != null and support_limit.has(weapon_id):
			_check("%s aim: support hand on the gun" % weapon_id, support_misses.back() >= 0.0 and support_misses.back() < support_limit[weapon_id],
				"grip %.3f m off (tolerance %.2f)" % [support_misses.back(), support_limit[weapon_id]])
		if mounts and stock != null:
			_check("%s aim: %s on its anchor" % [weapon_id, mount_name], s_aim.distance_to(pocket) < STOCK_TOLERANCE,
				"%.3f m off (tolerance %.2f)" % [s_aim.distance_to(pocket), STOCK_TOLERANCE])
		Input.action_release("aim")
		if stance != "upright" and stance != "swim":
			Input.action_release(stance)
		p.queue_free()
		await _tick(5)

	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
