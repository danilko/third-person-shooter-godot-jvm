extends SceneTree
## The parity gate for THE shared character animation library (PLAN.md 6.9).
##
##   godot --headless --path . --script tools/godot/probe_shared_anims.gd [-- --control]
##
## `build_character_anims.gd` rewrites every track path and DROPS every position track that never
## leaves the rest pose. Both are silent changes: a dropped track that was carrying real motion
## makes a clip subtly wrong, not broken, and nothing on screen says so. So this plays every clip
## twice on two real skeletons -- once from the body .glb's own AnimationPlayer, once from the
## shared library -- and compares EVERY BONE's global pose at several times through the clip.
##
## `--control` keeps the constant position tracks (i.e. does not run the drop) on a skeleton whose
## bone rest is shifted, which is what a differently-proportioned body is: the dropped tracks then
## override that body's own bone lengths and the check fails, which is the whole reason they go.
## The CLIP SOURCE -- the body whose .glb the shared library is built from. Overridable so the gate
## can be pointed at a new home when the library moves (PLAN.md: Shino as the base), and so the
## migration can be proven BEFORE any constant is flipped.
const SOURCE := "res://assets/characters/shino/shino.glb"
const SHARED := "res://src/main/resources/com/openworld/character/anim/character_anims.res"
## The builder records what it deliberately left out (a clip carrying blend-shape tracks is not a
## body clip -- a VRoid face's 42 shape keys export as one). Read from its manifest rather than
## re-tested here, or the gate and the builder would each own a copy of the rule.
const MANIFEST := "res://src/main/resources/com/openworld/character/anim/character_anims.json"
const SAMPLES := 5
const POS_TOL := 0.0005      # m, per bone, global
const ROT_TOL := 0.10        # deg, per bone, global -- measured worst 0.056 deg on a
                             # fingertip four bones down the chain, i.e. float32 key noise, against
                             # 0.000001 m of position error. Nothing here is a pose difference.

var _pass := 0
var _fail := 0

func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	var source := SOURCE
	for cli in OS.get_cmdline_user_args():
		if cli.begins_with("--source="):
			source = cli.substr(9)
	var ps := load(source) as PackedScene

	var a_root := ps.instantiate()
	root.add_child(a_root)
	var a_skel := _find(a_root, "Skeleton3D") as Skeleton3D
	var a_ap := _find(a_root, "AnimationPlayer") as AnimationPlayer

	var b_root := ps.instantiate()
	root.add_child(b_root)
	var b_skel := _find(b_root, "Skeleton3D") as Skeleton3D
	var b_arm := b_skel.get_parent()
	var b_ap := AnimationPlayer.new()
	b_root.add_child(b_ap)
	b_ap.root_node = b_ap.get_path_to(b_arm)
	b_ap.add_animation_library(&"", load(SHARED))

	# The control: a body whose bones are NOT Godot-chan's. One bone is lengthened by 5 cm, which
	# is less than the difference between Shino's upper arm and Godot-chan's (0.434 vs 0.416 m).
	var moved := ""
	if control:
		var bi := b_skel.find_bone("upperarm_r")
		var r := b_skel.get_bone_rest(bi)
		r.origin += Vector3(0.0, 0.05, 0.0)
		b_skel.set_bone_rest(bi, r)
		b_skel.reset_bone_poses()
		var ai := a_skel.find_bone("upperarm_r")
		var ar := a_skel.get_bone_rest(ai)
		ar.origin += Vector3(0.0, 0.05, 0.0)
		a_skel.set_bone_rest(ai, ar)
		a_skel.reset_bone_poses()
		moved = " [control: upperarm_r rest +0.05 m on both]"

	var names := a_ap.get_animation_list()
	names.sort()
	var skipped := {}
	if FileAccess.file_exists(MANIFEST):
		var man = JSON.parse_string(FileAccess.get_file_as_string(MANIFEST))
		if man is Dictionary:
			for n in (man.get("skipped", []) as Array):
				skipped[String(n)] = true
	var missing: PackedStringArray = []
	for n in names:
		if skipped.has(String(n)): continue
		if not b_ap.has_animation(n): missing.append(n)
	_check("every clip is in the shared library", missing.is_empty(),
		"%d clips (%d deliberately skipped: %s), missing: %s"
		% [names.size(), skipped.size(),
		   "none" if skipped.is_empty() else String(", ").join(PackedStringArray(skipped.keys())),
		   "none" if missing.is_empty() else String(", ").join(missing)])

	var worst_pos := 0.0
	var worst_rot := 0.0
	var worst_clip := ""
	var worst_bone := ""
	var worst_rot_clip := ""
	var worst_rot_bone := ""
	var over := 0
	for n in names:
		if not b_ap.has_animation(n): continue
		var len_s: float = a_ap.get_animation(n).length
		for s in SAMPLES:
			var t: float = len_s * float(s) / float(maxi(1, SAMPLES - 1))
			a_ap.play(n); a_ap.seek(t, true, true)
			b_ap.play(n); b_ap.seek(t, true, true)
			for i in a_skel.get_bone_count():
				var bn := a_skel.get_bone_name(i)
				var bj := b_skel.find_bone(bn)
				if bj < 0: continue
				var ta := a_skel.get_bone_global_pose(i)
				var tb := b_skel.get_bone_global_pose(bj)
				var dp := (ta.origin - tb.origin).length()
				var dr := rad_to_deg(ta.basis.get_rotation_quaternion().angle_to(tb.basis.get_rotation_quaternion()))
				if dp > worst_pos:
					worst_pos = dp; worst_clip = n; worst_bone = bn
				if dr > worst_rot:
					worst_rot = dr; worst_rot_clip = n; worst_rot_bone = bn
				if dp > POS_TOL or dr > ROT_TOL: over += 1

	var ok := worst_pos <= POS_TOL and worst_rot <= ROT_TOL
	_check("the shared library poses every bone identically%s" % moved, ok,
		"worst %.6f m (%s/%s) / %.4f deg (%s/%s) over %d clips x %d samples x %d bones, %d over tolerance"
			% [worst_pos, worst_clip, worst_bone, worst_rot, worst_rot_clip, worst_rot_bone,
			   names.size(), SAMPLES, a_skel.get_bone_count(), over])

	print("[shared-anims] %d passed, %d failed" % [_pass, _fail])
	quit(1 if _fail > 0 else 0)

func _check(what: String, ok: bool, detail: String) -> void:
	if ok: _pass += 1
	else: _fail += 1
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", what, detail])

func _find(n: Node, cls: String) -> Node:
	if n.get_class() == cls: return n
	for c in n.get_children():
		var r := _find(c, cls)
		if r != null: return r
	return null
