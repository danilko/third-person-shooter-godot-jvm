extends SceneTree
## Build THE shared character animation library from the clip source .glb.
##
##   godot --headless --path . --script tools/godot/build_character_anims.gd [-- --check]
##
## Why this exists (PLAN.md 6.9, "animate once"): every body used to carry its own copy of all 171
## clips inside its own .glb -- measured byte-identical between `merged_animation.glb` and
## `merged_animation_f.glb` (sha1 40a70d1f... over every sampler). A clip is a fact about the
## SKELETON CONTRACT, not about a body's appearance, so it has one owner and one file, and a new
## body ships with no clips at all.
##
## Two things the build does, and both are what make a clip portable to a differently-proportioned
## body (see blender/SKELETON_CONTRACT.md):
##
##  * the track path loses the armature node's name: `Godot_Chan_Stealth/Skeleton3D:spine_03` becomes
##    `Skeleton3D:spine_03`, so the library binds to whatever the AnimationPlayer's `root_node` is.
##    A body may name its armature anything.
##  * a POSITION track that never leaves the rest position is DROPPED. A position key is an absolute
##    bone-local offset in metres, so a kept one overrides the target body's own bone length -- play
##    Godot-chan's constant `pelvis` position on a 1.9 m body and its hips snap 36 cm down for the
##    whole clip. Measured on the source: only `Root`, `pelvis`, `head` and the two clavicles ever
##    move (0.0095-0.746 m); every other bone's position track deviates by at most 4.2e-05 m, which
##    is exporter float noise. The two populations are 20x apart, so the cut is not a judgement call.
##    The build prints both sides of the gap and fails if they ever overlap.
## The only bones whose POSITION travels with the clip rather than with the body.
const TRANSLATING_BONES := ["Root", "pelvis"]
const POS_EPS := 1.0e-3        # metres; between the 4.2e-05 noise floor and the 9.5e-03 real motion
const SKELETON_NODE := "Skeleton3D"

const SOURCE := "res://assets/characters/godot_chan/merged_animation.glb"
const OUT_RES := "res://src/main/resources/com/openworld/character/anim/character_anims.res"
const OUT_JSON := "res://src/main/resources/com/openworld/character/anim/character_anims.json"

var _fail := 0

func _initialize() -> void:
	var check := false
	var source := SOURCE
	for a in OS.get_cmdline_user_args():
		if a == "--check": check = true
		elif a.begins_with("--source="): source = a.substr(9)
	var ps := load(source) as PackedScene
	if ps == null:
		_die("cannot load %s" % source)
		return
	var root := ps.instantiate()
	var skel := _find(root, "Skeleton3D") as Skeleton3D
	var ap := _find(root, "AnimationPlayer") as AnimationPlayer
	if skel == null or ap == null:
		_die("source has no Skeleton3D (%s) / AnimationPlayer (%s)" % [skel, ap])
		return

	var rest := {}
	for i in skel.get_bone_count():
		rest[skel.get_bone_name(i)] = skel.get_bone_rest(i).origin

	var lib := AnimationLibrary.new()
	var clips: PackedStringArray = []
	var kept_pos := 0
	var dropped_pos := 0
	var rot := 0
	var other := 0
	var worst_dropped := 0.0
	var worst_dropped_bone := ""
	var by_rule := 0
	var by_rule_worst := 0.0
	var by_rule_bone := ""
	var least_kept := INF
	var least_kept_bone := ""
	var moving := {}
	var bones := {}

	var src_lib := ap.get_animation_library(ap.get_animation_library_list()[0])
	var names := src_lib.get_animation_list()
	names.sort()
	for n in names:
		var a: Animation = (src_lib.get_animation(n) as Animation).duplicate(true)
		for i in range(a.get_track_count() - 1, -1, -1):
			var p := a.track_get_path(i)
			var sub := p.get_concatenated_subnames()
			var node_name := String(p.get_name(p.get_name_count() - 1))
			if node_name != SKELETON_NODE:
				other += 1
				continue
			bones[sub] = true
			a.track_set_path(i, NodePath("%s:%s" % [SKELETON_NODE, sub]))
			if a.track_get_type(i) == Animation.TYPE_POSITION_3D:
				var r: Vector3 = rest.get(sub, Vector3.ZERO)
				var dev := 0.0
				for k in a.track_get_key_count(i):
					dev = maxf(dev, ((a.track_get_key_value(i, k) as Vector3) - r).length())
				# ONLY Root and pelvis may translate. Every other bone's position is a fact about the
				# BODY -- its own bone length -- and a kept key is an ABSOLUTE offset in metres that
				# silently overrides it. Measured 2026-09-20: `upright_aim_rifle` keyed both CLAVICLES
				# (the artist shrugged the shoulder by MOVING the bone, posing by eye with no IK), and
				# those keys cleared the old deviation test because they wobble 0.0097 m with
				# breathing. On the reference that is ~0; on Fumiriya it yanked the whole shoulder
				# girdle up **0.092 m** and on Shino **0.126 m** -- the visible "shoulder held up,
				# arms twisted" on both VRoid bodies. 1 cm of authored motion is not worth 13 cm of
				# error, and no epsilon can separate them: the value is wrong, not the movement.
				if not (sub in TRANSLATING_BONES) or dev < POS_EPS:
					a.remove_track(i)
					dropped_pos += 1
					# Only an ELIGIBLE bone says anything about where the epsilon sits. A bone dropped
					# by the allow-list is dropped whatever it does, so counting it here would make
					# the separation test fail on a rule it is not testing (clavicle_r, 0.0097 m).
					if (sub in TRANSLATING_BONES) and dev > worst_dropped:
						worst_dropped = dev
						worst_dropped_bone = sub
					if not (sub in TRANSLATING_BONES):
						by_rule += 1
						if dev > by_rule_worst:
							by_rule_worst = dev
							by_rule_bone = sub
				else:
					kept_pos += 1
					moving[sub] = maxf(float(moving.get(sub, 0.0)), dev)
					if dev < least_kept:
						least_kept = dev
						least_kept_bone = sub
			else:
				rot += 1
		lib.add_animation(StringName(n), a)
		clips.append(n)

	var bone_list := bones.keys()
	bone_list.sort()
	var moving_list := moving.keys()
	moving_list.sort()
	print("[anims] source          %s" % source)
	print("[anims] clips           %d" % clips.size())
	print("[anims] rotation tracks %d" % rot)
	print("[anims] position tracks %d kept, %d dropped as constant-at-rest" % [kept_pos, dropped_pos])
	print("[anims] of those, %d dropped BY RULE (not %s); most authored motion given up %.6f m (%s)"
		% [by_rule, str(TRANSLATING_BONES), by_rule_worst, by_rule_bone])
	print("[anims] worst DROPPED deviation %.6f m (%s)   least KEPT %.6f m (%s)"
		% [worst_dropped, worst_dropped_bone, least_kept, least_kept_bone])
	print("[anims] bones %d, of which these translate:" % bone_list.size())
	for b in moving_list:
		print("[anims]    %-12s max %.6f m" % [b, moving[b]])
	if other > 0:
		print("[anims] WARNING: %d tracks target something other than %s and were left alone" % [other, SKELETON_NODE])
	if least_kept <= worst_dropped * 4.0:
		_fail += 1
		print("[anims] FAIL: the noise floor and real motion are not separated -- retune POS_EPS")

	var manifest := {
		"source": source,
		"clips": clips,
		"bones": bone_list,
		"moving_bones": moving_list,
		"rotation_tracks": rot,
		"position_tracks": kept_pos,
		"pos_eps": POS_EPS,
	}
	var text := JSON.stringify(manifest, "  ") + "\n"

	if check:
		var prev := FileAccess.get_file_as_string(OUT_JSON)
		if prev != text:
			_fail += 1
			print("[anims] FAIL: %s is stale -- re-run without --check" % OUT_JSON)
		else:
			print("[anims] check: manifest up to date")
	else:
		var err := ResourceSaver.save(lib, OUT_RES, ResourceSaver.FLAG_COMPRESS)
		if err != OK:
			_fail += 1
			print("[anims] FAIL: cannot save %s (%d)" % [OUT_RES, err])
		var f := FileAccess.open(OUT_JSON, FileAccess.WRITE)
		f.store_string(text)
		f.close()
		print("[anims] wrote %s (%d bytes) and %s"
			% [OUT_RES, FileAccess.open(OUT_RES, FileAccess.READ).get_length(), OUT_JSON])

	root.free()
	print("[anims] %s" % ("PASS" if _fail == 0 else "FAIL (%d)" % _fail))
	quit(_fail)

func _die(msg: String) -> void:
	print("[anims] FAIL: %s" % msg)
	quit(1)

func _find(n: Node, cls: String) -> Node:
	if n.get_class() == cls: return n
	for c in n.get_children():
		var r := _find(c, cls)
		if r != null: return r
	return null
