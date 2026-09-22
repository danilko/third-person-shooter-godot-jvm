extends SceneTree
## Measure every melee attack clip's CONTACT moment (PLAN.md 6.6): the frame its striking hand moves fastest.
##
##   godot --headless --path . --script tools/godot/measure_attack_clips.gd [-- --body=res://.../x.glb]
##
## W16's rule is that the CODE owns a swing's timing and the clip is time-warped to fit it, and that "when
## real swing clips land, set the step to the clip's own contact frames and the scale comes out at 1".
## This is the measurement that sets them: the clip plays from the shared library on a bare AnimationPlayer
## (no tree, no modifiers, so a bone's global pose IS the clip's pose), each hand is sampled at 120 Hz, and
## the contact is the peak of the hand that moves most. Prints one line per clip; `--json` prints a table.

const LIB := "res://src/main/resources/com/openworld/character/anim/character_anims.res"
const CLIPS := ["attack_stab_mw1", "attack_slash_mw1", "attack_swing_mw2", "attack_chop_mw2",
		"attack_jab_fist", "attack_cross_fist", "attack_throw"]
const RATE := 120.0

func _find_skel(n: Node) -> Skeleton3D:
	if n is Skeleton3D:
		return n
	for c in n.get_children():
		var r := _find_skel(c)
		if r != null:
			return r
	return null

## The bone's pose in skeleton space, walking the parent chain from the LOCAL poses (headless, the
## skeleton's cached global pose is not refreshed -- W41's measured trap).
func _global(sk: Skeleton3D, b: int) -> Transform3D:
	var t := Transform3D.IDENTITY
	while b >= 0:
		t = Transform3D(Basis(sk.get_bone_pose_rotation(b)).scaled(sk.get_bone_pose_scale(b)),
				sk.get_bone_pose_position(b)) * t
		b = sk.get_bone_parent(b)
	return t

func _initialize() -> void:
	var body := "res://assets/characters/shino/shino.glb"
	var as_json := false
	var curve := false
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--body="):
			body = a.substr("--body=".length())
		elif a == "--json":
			as_json = true
		elif a == "--curve":                       # print each hand's speed every 0.05 s
			curve = true
	var inst: Node3D = (load(body) as PackedScene).instantiate()
	root.add_child(inst)
	await process_frame
	var sk := _find_skel(inst)
	var ap := AnimationPlayer.new()
	sk.get_parent().add_child(ap)
	ap.root_node = ap.get_path_to(sk.get_parent())
	ap.add_animation_library("", load(LIB))
	var out := {}
	for clip in CLIPS:
		if not ap.has_animation(clip):
			print("  %-20s MISSING" % clip)
			continue
		var length: float = ap.get_animation(clip).length
		ap.play(clip)
		var best := {"t": 0.0, "v": 0.0, "hand": ""}
		for hand in ["hand_r", "hand_l"]:
			var b := sk.find_bone(hand)
			var prev := Vector3.ZERO
			var n := int(length * RATE)
			for i in range(n + 1):
				var t: float = i / RATE
				ap.seek(t, true)
				var p: Vector3 = _global(sk, b).origin
				if i > 0:
					var v: float = (p - prev).length() * RATE
					if curve and i % 6 == 0:
						print("    %s %s t=%.2f v=%.2f" % [clip, hand, t, v])
					if v > best["v"]:
						best = {"t": t - 0.5 / RATE, "v": v, "hand": hand}
				prev = p
		out[clip] = {"length": snappedf(length, 0.001), "contact": snappedf(best["t"], 0.001),
				"peak_speed": snappedf(best["v"], 0.01), "hand": best["hand"]}
		print("  %-20s length %.3f s  contact %.3f s (%.0f%%)  %s peak %.2f m/s" % [clip, length, best["t"],
				100.0 * best["t"] / length, best["hand"], best["v"]])
	if as_json:
		print(JSON.stringify(out))
	quit(0)
