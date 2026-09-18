extends SceneTree
## A weapon pose's CLIP TRUTH: the clip on a bare AnimationPlayer, no AnimationTree, no modifiers.
##
##   godot --headless --path . --script tools/godot/probe_pose_clip.gd -- \
##       [--visuals=res://...CharacterVisuals_X.tscn] [--clip=upright_aim_rifle] \
##       [--compare=res://assets/characters/godot_chan/merged_animation.tscn]
##
## PLAN.md A2.0. `probe_weapon_fit.gd` measures a pose THROUGH the rig, and the rig changes what it
## shows: the WeaponBlend filter drops the clip's spine and head, and both aim modifiers add their own
## rotation. A2.1-A2.3 change all three, so the pose has to be judged by what is in the clip itself.
##
## With the tree and every SkeletonModifier3D switched off, `get_bone_global_pose` IS the final pose (the
## usual "pre-modifier" trap does not apply), so bones are read directly and each weapon is hung from
## `hand_r` at `SocketRifle`'s authored transform -- W20: a weapon's origin is its grip, so the socket is
## the weapon's transform. Weapon markers are read off the PackedScene's state, so no weapon script runs.
##
## Reported per sample time and as mean / spread over the loop (a single frame of a loop is not a
## measurement, W10), all in MeshRoot's frame (-Z forward, +X right):
##   - blade: yaw of the shoulder line (upperarm_r - upperarm_l) against the hips (thigh_r - thigh_l),
##     split into the SPINE share (`spine_03`'s own +X, which W1 measured lands on the clavicle axis in
##     the rest pose) and the COLLARBONE share (the rest). The clavicle ORIGINS are NOT usable for this:
##     they sit a few cm apart, so a 5 deg spine_03 change read as a 32 deg "spine share";
##   - gun yaw / pitch against the body's forward (the aim, target ~0);
##   - stock vs the shoulder pocket (probe_weapon_fit.POCKET_IN_CLAVICLE) per weapon;
##   - the right-hand IK delta A2.2 would apply: turn the gun onto the forward line about its stock,
##     put the stock on the pocket, and report how far the hand moves and turns;
##   - head vs the bore line (cheek weld): the head's offset from the line through the stock along the bore;
##   - the left hand vs SupportPoint.
## With --compare, the clip's local bone rotations are diffed against the same clip in another export
## (max quaternion component delta, the unit the 2026-09-14 snapshot used, and the angle in degrees).

const DEFAULT_VISUALS := "res://src/main/resources/com/openworld/character/CharacterVisuals_GodotChan.tscn"
const WEAPONS := ["ASR1", "ASR2", "SHG1"]
const WEAPON_DIR := "res://src/main/resources/com/openworld/weapon/%s.tscn"
const POCKET_IN_CLAVICLE := Vector3(-0.0280, -0.0419, 0.0880)
const SAMPLES := 12
const TRACK_PREFIX := "Godot_Chan_Stealth/Skeleton3D:"

var visuals_path := DEFAULT_VISUALS
var clip := "upright_aim_rifle"
var compare_path := ""
## With --compare, also list every OTHER clip that differs from the compared export (what else was edited).
var compare_all := false

func _find(n: Node, nm: String) -> Node:
	if n.name == nm:
		return n
	for c in n.get_children():
		var r: Node = _find(c, nm)
		if r != null:
			return r
	return null

func _find_type(n: Node, cls: String) -> Node:
	if n.is_class(cls):
		return n
	for c in n.get_children():
		var r: Node = _find_type(c, cls)
		if r != null:
			return r
	return null

## name -> local Transform3D of every direct child of the weapon scene's root.
func _markers(weapon_id: String) -> Dictionary:
	var st: SceneState = (load(WEAPON_DIR % weapon_id) as PackedScene).get_state()
	var out := {}
	for i in st.get_node_count():
		if String(st.get_node_path(i, true)) != ".":
			continue
		var xf := Transform3D.IDENTITY
		for p in st.get_node_property_count(i):
			if st.get_node_property_name(i, p) == &"transform":
				xf = st.get_node_property_value(i, p)
		out[String(st.get_node_name(i))] = xf
	return out

func _yaw_of(v: Vector3) -> float:
	return rad_to_deg(atan2(v.z, v.x))  # angle of a right-pointing pair; + = its right end is BEHIND

func _stats(xs: Array) -> String:
	var lo := INF
	var hi := -INF
	var sum := 0.0
	for x in xs:
		lo = minf(lo, x)
		hi = maxf(hi, x)
		sum += x
	return "%+7.3f  (%+.3f .. %+.3f)" % [sum / xs.size(), lo, hi]

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--visuals="):
			visuals_path = a.substr(10)
		elif a.begins_with("--clip="):
			clip = a.substr(7)
		elif a == "--all":
			compare_all = true
		elif a.begins_with("--compare="):
			compare_path = a.substr(10)
	print("visuals %s   clip %s" % [visuals_path, clip])
	var vis: Node3D = (load(visuals_path) as PackedScene).instantiate() as Node3D
	root.add_child(vis)
	await process_frame
	var tree: AnimationTree = _find_type(vis, "AnimationTree") as AnimationTree
	tree.active = false
	var sk: Skeleton3D = _find(vis, "Skeleton3D") as Skeleton3D
	for c in sk.get_children():
		if c is SkeletonModifier3D:
			(c as SkeletonModifier3D).active = false
	var mesh_root: Node3D = _find(vis, "MeshRoot") as Node3D
	var ap: AnimationPlayer = _find_type(mesh_root, "AnimationPlayer") as AnimationPlayer
	if not ap.has_animation(clip):
		print("FAIL: no clip %s" % clip)
		quit(1)
		return
	var anim: Animation = ap.get_animation(clip)
	print("clip length %.3f s, %d tracks" % [anim.length, anim.get_track_count()])
	var socket: Node3D = _find(sk, "SocketRifle") as Node3D
	var socket_local: Transform3D = socket.transform

	var guns := {}
	for w in WEAPONS:
		guns[w] = _markers(w)

	var ids := {}
	for b in ["thigh_l", "thigh_r", "upperarm_l", "upperarm_r", "clavicle_l", "clavicle_r", "hand_r",
			"hand_l", "head_2", "spine_03"]:
		ids[b] = sk.find_bone(b)

	var rows := {}
	ap.play(clip)
	for s in SAMPLES:
		var t: float = anim.length * float(s) / float(SAMPLES)
		ap.seek(t, true)
		var to_body: Transform3D = mesh_root.global_transform.affine_inverse() * sk.global_transform
		var P := func(b: String) -> Vector3: return to_body * sk.get_bone_global_pose(ids[b]).origin
		var hips: Vector3 = P.call("thigh_r") - P.call("thigh_l")
		var shoulders: Vector3 = P.call("upperarm_r") - P.call("upperarm_l")
		var chest_x: Vector3 = to_body.basis * sk.get_bone_global_pose(ids["spine_03"]).basis.x
		var hips_first: Vector3 = P.call("thigh_r") - P.call("thigh_l")
		if chest_x.dot(hips_first) < 0.0:
			chest_x = -chest_x  # the glTF import's 180 deg flip puts the bone's +X on the body's left
		var hip_yaw := _yaw_of(hips)
		var r := {
			"blade vs hips (deg)": _yaw_of(shoulders) - hip_yaw,
			"  spine share (spine_03 +X)": _yaw_of(chest_x) - hip_yaw,
			"  collarbone share": _yaw_of(shoulders) - _yaw_of(chest_x),
			"hips vs MeshRoot (deg)": hip_yaw,
		}
		var hand_xf: Transform3D = to_body * sk.get_bone_global_pose(ids["hand_r"])
		var gun_xf: Transform3D = hand_xf * socket_local
		var bore: Vector3 = (-gun_xf.basis.z).normalized()
		r["gun yaw (deg, + = right)"] = rad_to_deg(atan2(bore.x, -bore.z))
		r["gun pitch (deg)"] = rad_to_deg(asin(clampf(bore.y, -1, 1)))
		var joint: Vector3 = P.call("upperarm_r")
		var cb: Basis = (to_body.basis * sk.get_bone_global_pose(ids["clavicle_r"]).basis).orthonormalized()
		var pocket: Vector3 = joint + cb * POCKET_IN_CLAVICLE
		var head: Vector3 = P.call("head_2")
		for w in WEAPONS:
			var m: Dictionary = guns[w]
			var stock: Vector3 = gun_xf * (m["StockPoint"] as Transform3D).origin
			var d: Vector3 = stock - pocket
			r["%s stock-pocket right" % w] = d.x
			r["%s stock-pocket up" % w] = d.y
			r["%s stock-pocket fwd" % w] = -d.z
			r["%s stock-pocket dist" % w] = d.length()
			# A2.2's delta: turn the gun about its stock onto the forward line, stock onto the pocket.
			var turn := Quaternion(bore, Vector3(0, 0, -1)) if bore.dot(Vector3(0, 0, -1)) < 0.99999 else Quaternion.IDENTITY
			var want_basis := Basis(turn) * gun_xf.basis
			var stock_local: Vector3 = (m["StockPoint"] as Transform3D).origin
			var want_origin: Vector3 = pocket - want_basis * stock_local
			var want_hand: Transform3D = Transform3D(want_basis, want_origin) * socket_local.affine_inverse()
			r["%s IK hand move (m)" % w] = want_hand.origin.distance_to(hand_xf.origin)
			r["%s IK hand turn (deg)" % w] = rad_to_deg(want_hand.basis.get_rotation_quaternion().angle_to(hand_xf.basis.get_rotation_quaternion()))
			# cheek weld: head_2 against the bore line through the muzzle marker's height
			var muzzle: Vector3 = gun_xf * (m["Muzzle"] as Transform3D).origin
			var rel: Vector3 = head - muzzle
			var perp: Vector3 = rel - bore * rel.dot(bore)
			r["%s head off bore right" % w] = perp.x
			r["%s head off bore up" % w] = perp.y
			if m.has("SupportPoint"):
				var sup: Vector3 = gun_xf * (m["SupportPoint"] as Transform3D).origin
				# the hand's GRIP point, 0.75 of the way to the middle knuckle (SupportHandIKModifier.gripFraction)
				var hl: Vector3 = P.call("hand_l")
				var grip_pt: Vector3 = hl + (to_body * sk.get_bone_global_pose(sk.find_bone("middle_01_l")).origin - hl) * 0.75
				r["%s left grip - SupportPoint (m)" % w] = sup.distance_to(grip_pt)
		r["palm(hand_r) in front of joint (m)"] = joint.z - hand_xf.origin.z
		for k in r:
			if not rows.has(k):
				rows[k] = []
			rows[k].append(r[k])
	print("%-36s %s" % ["measure", "mean     (min .. max over %d samples)" % SAMPLES])
	for k in rows:
		print("%-36s %s" % [k, _stats(rows[k])])

	if compare_path != "":
		_compare(anim, compare_path)
		if compare_all:
			_compare_all(ap, compare_path)
	quit(0)

func _compare(anim: Animation, path: String) -> void:
	var other_root: Node = (load(path) as PackedScene).instantiate()
	var ap: AnimationPlayer = _find_type(other_root, "AnimationPlayer") as AnimationPlayer
	if ap == null or not ap.has_animation(clip):
		print("compare: %s has no clip %s" % [path, clip])
		other_root.free()
		return
	var other: Animation = ap.get_animation(clip)
	print("")
	print("clip diff vs %s (local rotation; max |quat component| delta, max angle)" % path)
	var out := []
	for ti in anim.get_track_count():
		if anim.track_get_type(ti) != Animation.TYPE_ROTATION_3D:
			continue
		var tp: String = String(anim.track_get_path(ti))
		var oi: int = other.find_track(NodePath(tp), Animation.TYPE_ROTATION_3D)
		if oi < 0:
			continue
		var comp := 0.0
		var ang := 0.0
		for s in SAMPLES:
			var t: float = anim.length * float(s) / float(SAMPLES)
			var a: Quaternion = anim.rotation_track_interpolate(ti, t)
			var b: Quaternion = other.rotation_track_interpolate(oi, minf(t, other.length))
			if a.dot(b) < 0.0:
				b = -b
			comp = maxf(comp, maxf(absf(a.x - b.x), maxf(absf(a.y - b.y), maxf(absf(a.z - b.z), absf(a.w - b.w)))))
			ang = maxf(ang, rad_to_deg(a.angle_to(b)))
		if ang > 0.5:
			out.append([ang, tp.trim_prefix(TRACK_PREFIX), comp])
	out.sort_custom(func(x, y): return x[0] > y[0])
	for e in out:
		print("  %-16s  comp %.3f   angle %5.1f deg" % [e[1], e[2], e[0]])
	if out.is_empty():
		print("  (no bone differs by more than 0.5 deg)")
	other_root.free()

func _compare_all(ap: AnimationPlayer, path: String) -> void:
	var other_root: Node = (load(path) as PackedScene).instantiate()
	var oap: AnimationPlayer = _find_type(other_root, "AnimationPlayer") as AnimationPlayer
	print("")
	print("every clip that differs from %s (worst bone, max local rotation angle)" % path)
	var mine: PackedStringArray = ap.get_animation_list()
	for nm in mine:
		if not oap.has_animation(nm):
			print("  %-32s NEW (not in the compared export)" % nm)
			continue
		var a: Animation = ap.get_animation(nm)
		var b: Animation = oap.get_animation(nm)
		var worst := 0.0
		var worst_bone := ""
		for ti in a.get_track_count():
			if a.track_get_type(ti) != Animation.TYPE_ROTATION_3D:
				continue
			var oi: int = b.find_track(a.track_get_path(ti), Animation.TYPE_ROTATION_3D)
			if oi < 0:
				continue
			for s in SAMPLES:
				var t: float = a.length * float(s) / float(SAMPLES)
				var qa: Quaternion = a.rotation_track_interpolate(ti, t)
				var qb: Quaternion = b.rotation_track_interpolate(oi, minf(t, b.length))
				var ang: float = rad_to_deg(qa.angle_to(qb))
				if ang > worst:
					worst = ang
					worst_bone = String(a.track_get_path(ti)).trim_prefix(TRACK_PREFIX)
		if worst > 0.5 or absf(a.length - b.length) > 0.001:
			print("  %-32s %-14s %5.1f deg   length %.3f vs %.3f" % [nm, worst_bone, worst, a.length, b.length])
	for nm in oap.get_animation_list():
		if not ap.has_animation(nm):
			print("  %-32s REMOVED" % nm)
	other_root.free()
