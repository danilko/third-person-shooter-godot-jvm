extends SceneTree
## A second BODY works, and the clip names are the contract that makes it free.
##
##   godot --headless --path . --script tools/godot/probe_character_variant.gd
##
## `Character.characterVisuals` is one exported PackedScene: swapping it swaps the whole appearance,
## and the MeshConfig embedded in that scene rewires every dependent path. A second body (a female
## variant, a different model) is therefore a second CharacterVisuals over its own animation export.
##
## What holds it together is that **every clip keeps the same NAME**. All the Java addresses clips by
## name — `playMeleeAttack("attack_chop_mw2")`, `parameters/<Stance>MovementBlend/...` — so identical
## names mean the second body needs no code, no scene rewiring and no second probe suite. This gate
## asserts exactly that contract, because the failure mode is silent: a renamed or missing clip does
## not error, the branch simply goes quiet and the skeleton drifts to its REST pose, which by eye
## looks like a neutral authored pose (the W12 lesson).
##
## The variant ships as a COPY of the base body's animation, so it must measure identically here.
## When its locomotion is genuinely authored these parity cases are what tell you the eye mounts need
## re-measuring (W11: a pose measured in the wrong state is not a measurement of that pose) — a
## failure here then is the gate doing its job, not a regression.

const PLAYER  := "res://src/main/resources/com/openworld/character/Player.tscn"
const BASE    := "res://src/main/resources/com/openworld/character/CharacterVisuals_GodotChan.tscn"
const VARIANT := "res://src/main/resources/com/openworld/character/CharacterVisuals_GodotChanF.tscn"
const AI      := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const IMPACT  := "res://src/main/java/com/openworld/world/manager/ImpactManager.java"

var fails := 0
var world: Node3D

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-46s %s" % ["PASS" if ok else "FAIL", label, detail])

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

func _spawn(visuals: String, at: Vector3) -> Node3D:
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	# BEFORE add_child: Character._ready() instantiates whatever this names.
	p.set("character_visuals", load(visuals))
	world.add_child(p)
	p.global_position = at
	return p

## The resting eye offset of BOTH bodies, averaged over a second of the SAME frames.
##
## Averaging matters because a single frame of a 57-frame clip is not a measurement (W10). Sampling
## the two bodies over the same frames matters for a second reason, found here: measured one after
## the other they read 5 mm apart on a byte-identical copy, because each window caught the shared
## idle loop at a different phase and the neck this mount rides was simply somewhere else.
func _eye_offsets(a: Node3D, b: Node3D) -> Array:
	var ma: Node3D = _find(a, "MarkerFPSCamera") as Node3D
	var mb: Node3D = _find(b, "MarkerFPSCamera") as Node3D
	if ma == null or mb == null:
		return [Vector3.INF, Vector3.INF]
	var sa := Vector3.ZERO
	var sb := Vector3.ZERO
	for i in range(60):
		await physics_frame
		sa += ma.global_position - a.global_position
		sb += mb.global_position - b.global_position
	return [sa / 60.0, sb / 60.0]

func _initialize() -> void:
	world = Node3D.new()
	root.add_child(world)
	var floor_body := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(200, 1, 200)
	cs.shape = box
	floor_body.add_child(cs)
	floor_body.position = Vector3(0, -0.5, 0)
	world.add_child(floor_body)
	world.add_child(load(IMPACT).new())
	await _tick(3)

	var base := _spawn(BASE, Vector3(0, 1.2, 0))
	var variant := _spawn(VARIANT, Vector3(30, 1.2, 0))
	await _tick(60)

	# ── 1. the swap actually took ──────────────────────────────────────────────────────────────
	print("")
	print("=== 1. the body really is the variant ===")
	var v_model: Node = _find(variant, "Model")
	var b_model: Node = _find(base, "Model")
	_check("variant loads its own animation export",
		v_model != null and String(v_model.scene_file_path).ends_with("merged_animation_f.tscn"),
		"variant Model <- %s" % ("none" if v_model == null else v_model.scene_file_path.get_file()))
	_check("base body is untouched",
		b_model != null and String(b_model.scene_file_path).ends_with("merged_animation.tscn"),
		"base Model <- %s" % ("none" if b_model == null else b_model.scene_file_path.get_file()))

	# ── 2. the contract: identical clip names ──────────────────────────────────────────────────
	print("")
	print("=== 2. clip names are identical (the whole contract) ===")
	var b_tree: AnimationTree = _find(base, "AnimationTree") as AnimationTree
	var v_tree: AnimationTree = _find(variant, "AnimationTree") as AnimationTree
	var b_clips: Array = Array(b_tree.get_animation_list())
	var v_clips: Array = Array(v_tree.get_animation_list())
	b_clips.sort()
	v_clips.sort()
	var missing := []
	for c in b_clips:
		if not v_clips.has(c):
			missing.append(c)
	_check("variant has every clip the base body has", missing.is_empty(),
		"%d clips each; missing from variant: %s" % [b_clips.size(), "none" if missing.is_empty() else str(missing)])
	_check("and no extra ones to diverge on", b_clips.size() == v_clips.size(),
		"base %d vs variant %d" % [b_clips.size(), v_clips.size()])

	# ── 3. the eye, which is authored per body and must be re-measured when one diverges ───────
	print("")
	print("=== 3. the eye offset (per-body measurement) ===")
	var eyes: Array = await _eye_offsets(base, variant)
	var b_eye: Vector3 = eyes[0]
	var v_eye: Vector3 = eyes[1]
	_check("both bodies expose an FPS eye mount", b_eye != Vector3.INF and v_eye != Vector3.INF,
		"base %s variant %s" % [b_eye, v_eye])
	if b_eye != Vector3.INF and v_eye != Vector3.INF:
		var d: float = (b_eye - v_eye).length()
		_check("a COPY measures identically (diverge -> re-measure mounts)", d < 0.002,
			"base y=%.3f fwd=%.3f | variant y=%.3f fwd=%.3f | delta %.4f m"
				% [b_eye.y, b_eye.z, v_eye.y, v_eye.z, d])

	# ── 4. it fights: the melee path runs on the second body, unchanged ────────────────────────
	print("")
	print("=== 4. the variant swings and lands ===")
	var target: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	world.add_child(target)
	target.global_position = variant.global_transform * Vector3(0, 0, -1.1)
	target.set_physics_process(false)
	var t_mc: Node = target.get_node_or_null("MovementController")
	if t_mc != null:
		t_mc.set_physics_process(false)
	var t_at: Node = _find(target, "AnimationTree")
	if t_at != null:
		t_at.set("active", false)
	var damage := []
	var th: Node = target.get_node_or_null("Health")
	if th != null:
		th.connect("hit", func(d): damage.append(d))
	# Park the base body far away and pointing elsewhere: both Players poll the same Input, so the
	# press below swings them both, and only the variant must have something in front of it.
	base.global_position = Vector3(-120, 1.2, 0)
	await _tick(20)

	var states := {}
	Input.action_press("fire")
	for i in range(2):
		await physics_frame
	Input.action_release("fire")
	for i in range(40):
		await physics_frame
		states[String(v_tree.get("parameters/AttackClip/current_state"))] = true
	_check("variant's fist lands a hit", damage.size() == 1, "%d hits %s" % [damage.size(), str(damage)])
	_check("variant plays its own attack clip", states.has("attack_jab_fist"),
		"clips seen %s" % str(states.keys()))

	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
