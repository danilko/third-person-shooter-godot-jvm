extends SceneTree
## Does this body present the SKELETON CONTRACT? (PLAN.md 6.9, blender/SKELETON_CONTRACT.md)
##
##   godot --headless --path . --script tools/godot/probe_body_contract.gd -- \
##       --body=res://assets/characters/shino/shino.glb [--control]
##
## Every body plays the ONE shared clip library, so a body's whole obligation is: our bone NAMES,
## in our rest ORIENTATIONS, facing the way we face. Limb LENGTHS are free -- that is what a second
## body is for -- and the library carries no position track that could overrule them.
##
## The failure this gate exists for is SILENT. A rig whose rest orientations are a few degrees off
## does not error: every clip still plays, and the body simply stands and walks slightly wrong, in a
## way that reads as bad animation rather than as a bad rig. A rig whose rest is wholly different --
## a raw VRM, whose bones all rest at identity -- plays every clip as a heap. So the measurement is
## taken against the reference body, pose by pose, over every clip in the library.
##
## `--control` puts 20 deg of error into one bone's rest, which is what a mis-conformed rig is, and
## the gate must fail.
const REFERENCE := "res://assets/characters/godot_chan/merged_animation.glb"
const SHARED := "res://src/main/resources/com/openworld/character/anim/character_anims.res"
const SAMPLES := 4
const REST_TOL_DEG := 1.0     # a body's rest orientation vs the contract's
const POSE_TOL_DEG := 1.0     # the same clip, the same world orientation, on both bodies
const CONTROL_BONE := "upperarm_r"

var _pass := 0
var _fail := 0

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var control := "--control" in args
	var body_path := ""
	for a in args:
		if a.begins_with("--body="): body_path = a.substr(7)
	if body_path == "":
		print("  FAIL  no --body=res://... given")
		quit(1)
		return

	var ref := _rig(REFERENCE, "reference")
	var body := _rig(body_path, "body")
	if ref == null or body == null:
		quit(1)
		return

	var lib: AnimationLibrary = load(SHARED)
	var clips := lib.get_animation_list()
	clips.sort()

	# ---- 1. the names -----------------------------------------------------------------------
	var missing: PackedStringArray = []
	for i in ref.skel.get_bone_count():
		var n := ref.skel.get_bone_name(i)
		if body.skel.find_bone(n) < 0: missing.append(n)
	_check("every contract bone is present", missing.is_empty(),
		"%d contract bones, %d in this body's skeleton, missing: %s"
			% [ref.skel.get_bone_count(), body.skel.get_bone_count(),
			   "none" if missing.is_empty() else String(", ").join(missing)])

	if control:
		var bi := body.skel.find_bone(CONTROL_BONE)
		var r := body.skel.get_bone_rest(bi)
		r.basis = r.basis.rotated(Vector3.UP, deg_to_rad(20.0))
		body.skel.set_bone_rest(bi, r)
		body.skel.reset_bone_poses()

	# ---- 2. the rest orientations -----------------------------------------------------------
	var worst_rest := 0.0
	var worst_rest_bone := ""
	for i in ref.skel.get_bone_count():
		var n := ref.skel.get_bone_name(i)
		var bj := body.skel.find_bone(n)
		if bj < 0: continue
		var qa := ref.skel.get_bone_global_rest(i).basis.get_rotation_quaternion()
		var qb := body.skel.get_bone_global_rest(bj).basis.get_rotation_quaternion()
		var d := rad_to_deg(qa.angle_to(qb))
		if d > worst_rest:
			worst_rest = d; worst_rest_bone = n
	_check("rest orientations match the contract", worst_rest <= REST_TOL_DEG,
		"worst %.2f deg (%s), tolerance %.1f" % [worst_rest, worst_rest_bone, REST_TOL_DEG])

	# ---- 3. the same clip is the same pose --------------------------------------------------
	var worst_pose := 0.0
	var worst_pose_bone := ""
	var worst_pose_clip := ""
	var worst_pos := 0.0
	var worst_pos_bone := ""
	for n in clips:
		var len_s: float = lib.get_animation(n).length
		for s in SAMPLES:
			var t: float = len_s * float(s) / float(maxi(1, SAMPLES - 1))
			ref.ap.play(n); ref.ap.seek(t, true, true)
			body.ap.play(n); body.ap.seek(t, true, true)
			for i in ref.skel.get_bone_count():
				var bn := ref.skel.get_bone_name(i)
				var bj := body.skel.find_bone(bn)
				if bj < 0: continue
				var ta := ref.skel.get_bone_global_pose(i)
				var tb := body.skel.get_bone_global_pose(bj)
				var d := rad_to_deg(ta.basis.get_rotation_quaternion()
					.angle_to(tb.basis.get_rotation_quaternion()))
				if d > worst_pose:
					worst_pose = d; worst_pose_bone = bn; worst_pose_clip = n
				var dp := (ta.origin - tb.origin).length()
				if dp > worst_pos:
					worst_pos = dp; worst_pos_bone = bn
	_check("the shared library poses this body like the contract", worst_pose <= POSE_TOL_DEG,
		"worst %.2f deg (%s in %s) over %d clips x %d samples, tolerance %.1f"
			% [worst_pose, worst_pose_bone, worst_pose_clip, clips.size(), SAMPLES, POSE_TOL_DEG])
	print("         (bone POSITIONS differ by up to %.3f m at %s -- that is this body's own"
		% [worst_pos, worst_pos_bone])
	print("          proportions, which the contract deliberately leaves free)")

	# ---- 4. what this body is ---------------------------------------------------------------
	for r in [ref, body]:
		print("  %-10s height %.3f m   arm %.3f   leg %.3f   hip %.3f   bones %d"
			% [r.label, _height(r), _span(r, "upperarm_l", "hand_l"), _span(r, "thigh_l", "foot_l"),
			   r.skel.get_bone_global_rest(r.skel.find_bone("pelvis")).origin.y,
			   r.skel.get_bone_count()])

	print("[body-contract] %s: %d passed, %d failed" % [body_path, _pass, _fail])
	quit(1 if _fail > 0 else 0)


class Rig:
	var label: String
	var skel: Skeleton3D
	var ap: AnimationPlayer
	var root: Node


func _rig(path: String, label: String) -> Rig:
	var ps := load(path) as PackedScene
	if ps == null:
		_check("%s loads (%s)" % [label, path], false, "cannot load")
		return null
	var r := Rig.new()
	r.label = label
	r.root = ps.instantiate()
	root.add_child(r.root)
	r.skel = _find(r.root, "Skeleton3D") as Skeleton3D
	if r.skel == null:
		_check("%s has a Skeleton3D" % label, false, path)
		return null
	r.ap = AnimationPlayer.new()
	r.root.add_child(r.ap)
	r.ap.root_node = r.ap.get_path_to(r.skel.get_parent())
	r.ap.add_animation_library(&"", load(SHARED))
	return r


func _height(r: Rig) -> float:
	var top := 0.0
	for n in _meshes(r.root):
		var mi := n as MeshInstance3D
		var aabb := mi.get_aabb()
		for c in 8:
			var p := aabb.get_endpoint(c)
			top = maxf(top, (mi.global_transform * p).y)
	return top


func _meshes(n: Node) -> Array:
	var out: Array = []
	if n is MeshInstance3D: out.append(n)
	for c in n.get_children(): out.append_array(_meshes(c))
	return out


func _span(r: Rig, a: String, b: String) -> float:
	var ia := r.skel.find_bone(a)
	var ib := r.skel.find_bone(b)
	if ia < 0 or ib < 0: return NAN
	return (r.skel.get_bone_global_rest(ia).origin - r.skel.get_bone_global_rest(ib).origin).length()


func _check(what: String, ok: bool, detail: String) -> void:
	if ok: _pass += 1
	else: _fail += 1
	print("  %s  %-52s %s" % ["PASS" if ok else "FAIL", what, detail])


func _find(n: Node, cls: String) -> Node:
	if n.get_class() == cls: return n
	for c in n.get_children():
		var r := _find(c, cls)
		if r != null: return r
	return null
