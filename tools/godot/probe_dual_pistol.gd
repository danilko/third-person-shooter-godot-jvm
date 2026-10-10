## Gate for DUP1 (weapon.DualPistolItem): the second pistol rides the LEFT hand while the pair is held, both
## barrels point where the character aims, and the second gun goes away when the weapon is put up.
##
##   godot --headless --fixed-fps 60 --path . --script tools/godot/probe_dual_pistol.gd [-- --control]
##
## `--toe-in=DEG` sets the item's toe-in (the left barrel then reads DEG inward; the check allows it).
## `--control` turns the left gun 5 deg inward WITHOUT telling the check, and must fail "both barrels". It used to
## set `align_left_bore` off, which failed at -9.69 deg while the clip was bladed (the mirror doubled the right gun's
## correction on the left). Since the dual clips are symmetric in the world (2026-10-10) the left barrel is parallel
## without it -- even against the 3 m wall the barrels are read at, a near aim point that makes the modifiers
## correct -- so that control passed and proved nothing. `align_left_bore` stays on as a safety net.
## `--pistol-clip-control` plays the PISTOL aim clip under the pair (what DUP1 looked like before its poses were
## made symmetric in the world, 2026-10-10: the right gun on the centre line, the left 12 cm out) and must fail
## "the pair straddles the centre line".
## Yaw is read about world up in the body's frame (MeshRoot: -Z forward, +X right). A gun "inward" is one whose
## barrel heads toward the body's centre line: for the left gun that is +X, for the right gun -X.
extends SceneTree

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const DUP1 := "res://src/main/resources/com/openworld/weapon/DUP1.tscn"
const MAX_YAW_OFF := 1.0     # deg: each barrel's heading off the aim direction
const MAX_CENTRE_OFF := 0.025   # m: the pair's centre off the body's centre line
const MIN_SPAN := 0.15     # m: the two guns at least this far apart
var fails := 0
var control := false

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

func _check(ok: bool, what: String, detail: String) -> void:
	print("  %s  %-44s %s" % ["PASS" if ok else "FAIL", what, detail])
	if not ok:
		fails += 1

func _yaw_in_body(dir: Vector3, mesh_root: Node3D) -> float:
	var d: Vector3 = mesh_root.global_transform.basis.inverse() * dir
	return rad_to_deg(atan2(d.x, -d.z))   # + = toward the body's right

func _initialize() -> void:
	control = "--control" in OS.get_cmdline_user_args()
	var world := Node3D.new()
	root.add_child(world)
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(60, 1, 60)
	cs.shape = box
	b.add_child(cs)
	b.position = Vector3(0, -0.5, 0)
	world.add_child(b)
	await _tick(3)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
	await _tick(40)
	var gun: Node3D = (load(DUP1) as PackedScene).instantiate() as Node3D
	world.add_child(gun)
	gun.global_position = p.global_position + Vector3(0, 0.3, 0)
	await _tick(30)
	var wc: Node = p.get_node_or_null("WeaponController")
	var dup_slot := -1
	for slot in range(6):
		if String(gun.get_parent().name).begins_with("Socket"):
			break
		wc.call("on_set_weapon", slot)
		dup_slot = slot
		await _tick(50)
	_check(String(gun.get_parent().name).begins_with("Socket"), "DUP1 reached the right-hand socket", "parent %s" % gun.get_parent().name)
	var toe := 0.0   # what the check is told
	if control:
		gun.set("toe_in_deg", 5.0)
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--toe-in="):   # a converging pair: the left barrel reads this many degrees inward
			toe = float(a.substr(9))
			gun.set("toe_in_deg", toe)
	var pistol_clip := "--pistol-clip-control" in OS.get_cmdline_user_args()
	if pistol_clip:
		var tree: AnimationTree = _find(p, "AnimationTree") as AnimationTree
		for bs in ["WeaponAim", "WeaponAimCrawl", "WeaponAimCrouch", "WeaponAimTorso", "WeaponAimTorsoCrouch", "WeaponHold"]:
			tree.set("parameters/%s/blend_position" % bs, 0)   # GripArchetype.PISTOL
	Input.action_press("aim")
	await _tick(150)
	var sk: Skeleton3D = _find(p, "Skeleton3D") as Skeleton3D
	var mesh_root: Node3D = _find(p, "MeshRoot") as Node3D
	var att: Node = sk.get_node_or_null("DualPistolLeftHand")
	var left: Node3D = _find(att, "ModelLeft") as Node3D if att != null else null
	_check(att != null and att is BoneAttachment3D and String(att.get("bone_name")) == "hand_l",
		"a bone attachment on hand_l carries the 2nd gun", str(att))
	_check(left != null and left.is_visible_in_tree(), "the second gun is in the left hand, shown", str(left))
	if left != null:
		# the pair straddles the body's centre line (far aim: no correction turns the upper body)
		var inv: Basis = mesh_root.global_transform.basis.inverse()
		var xr: float = (inv * (gun.global_position - mesh_root.global_position)).x
		var xl: float = (inv * (left.global_position - mesh_root.global_position)).x
		_check(absf((xr + xl) * 0.5) <= MAX_CENTRE_OFF and xr - xl >= MIN_SPAN, "the pair straddles the centre line",
			"right %+.3f, left %+.3f m (centre %+.3f, limit %.3f; span %.3f, need %.2f)" % [xr, xl, (xr + xl) * 0.5, MAX_CENTRE_OFF, xr - xl, MIN_SPAN])
		# a wall 3 m ahead: the aim point comes near and the aim modifiers must correct
		var wall := StaticBody3D.new()
		var ws := CollisionShape3D.new()
		var wb := BoxShape3D.new()
		wb.size = Vector3(20, 10, 0.5)
		ws.shape = wb
		wall.add_child(ws)
		world.add_child(wall)
		var fwd: Vector3 = -mesh_root.global_transform.basis.z
		fwd.y = 0
		wall.global_position = p.global_position + fwd.normalized() * 3.0
		wall.look_at(p.global_position, Vector3.UP)
		await _tick(90)
		# the AimTarget marker is what the aim modifiers aim at (get_aim_target_position is not registered)
		var aim_at: Vector3 = (_find(p, "AimTarget") as Node3D).global_position
		print("  aim point %.2f m from the gun" % aim_at.distance_to(gun.global_position))
		var aim_dir: Vector3 = (aim_at - gun.global_position).normalized()
		var right_dir: Vector3 = -gun.global_transform.basis.z
		var left_dir: Vector3 = -left.global_transform.basis.z
		var a := _yaw_in_body(aim_dir, mesh_root)
		var r := _yaw_in_body(right_dir, mesh_root) - a
		var l := _yaw_in_body(left_dir, mesh_root) - a
		var sep: float = (mesh_root.global_transform.basis.inverse() * (gun.global_position - left.global_position)).x
		print("  right barrel %+.2f deg off the aim (%s), left barrel %+.2f deg off (%s), guns %.3f m apart"
			% [r, "inward" if r < 0 else "outward", l, "inward" if l > 0 else "outward", sep])
		_check(absf(r) <= MAX_YAW_OFF and absf(l - toe) <= MAX_YAW_OFF, "both barrels point where the body aims",
			"right %+.2f, left %+.2f deg (limit %.1f)" % [r, l, MAX_YAW_OFF])
		_check(sep > 0.08, "the two guns do not overlap", "%.3f m apart" % sep)
	Input.action_release("aim")
	wc.call("on_set_weapon", 0)   # the fist: the pair is put up
	await _tick(80)
	var left_now: Node3D = _find(gun, "ModelLeft") as Node3D
	_check(left_now != null and not left_now.visible, "put up, the second gun is back on the item, hidden",
		"parent %s, visible %s" % [left_now.get_parent().name if left_now != null else "?", left_now.visible if left_now != null else "?"])
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
