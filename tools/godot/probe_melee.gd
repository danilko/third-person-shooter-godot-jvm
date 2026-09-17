extends SceneTree
## Melee: two legs, a chain, cleave, and a swing that is actually animated.
##
##   godot --headless --path . --script tools/godot/probe_melee.gd
##
## Drives a real Player through the real input path -- the `fire` action through PlayerController ->
## Character -> WeaponController -> MeleeItem -- and measures what a swing DID through each target's
## own Health `hit` signal, never through a debug counter on the weapon. Targets are real
## AICharacters, so what the sweep has to find are their ragdoll hitboxes (HITBOX layer), as in play.
##
## `hit` carries the FINAL damage, after the bone multiplier. Every chain assertion is therefore a
## RATIO of two swings into the same target from the same place, where the multiplier cancels --
## an absolute number would be testing which bone the capsule met, not which swing was played.
##
## What each case separates (a case that cannot fail is not a case):
##   reach      -- a target 3.5 m out sits on the camera's line but past the swing's reach. It must
##                 take nothing, or the reach is being measured from somewhere other than the chest.
##   behind     -- a thin wall BETWEEN the camera and the character (on a layer the camera's spring
##                 arm ignores, which is how foliage or glass pokes through a real boom). The camera
##                 ray stops on it, behind the character. A camera-origin swing hits that wall and
##                 whiffs; a chest-origin swing must still land on the target in front.
##   cover      -- a wall between the chest and the target must block the swing, as it blocks a bullet.
##   cleave     -- two targets side by side: ONE swing hits both, and each exactly once however many
##                 of its bones the capsule overlaps over the whole contact window.
##   chain      -- jab then cross inside comboResetSeconds, then after a pause the jab again.
##   buffer     -- a tap that lands during recovery must still produce the next swing.
##   hitstop    -- the attack one-shot's time scale is held at 0 on contact, then given back.
##   fps        -- first person resolves from the same chest, so the same target is hit.
##   axe        -- "light first, big second": 120 / 60.
##   knife      -- tap stabs, hold slashes: 100 / 40.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const AI     := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const IMPACT := "res://src/main/java/com/openworld/world/manager/ImpactManager.java"
const MEW1    := "res://src/main/resources/com/openworld/weapon/MEW1.tscn"
const MEW2    := "res://src/main/resources/com/openworld/weapon/MEW2.tscn"
const FIST   := "res://src/main/resources/com/openworld/weapon/Fist.tscn"
const MELEE_SLOT := 4
const COMBO_RESET_FRAMES := 60     # > comboResetSeconds (0.6 s) at 60 Hz

var fails := 0
var world: Node3D
var player: Node3D
var wc: Node
var tree_node: AnimationTree
var hits := {}                    # target instance id -> Array of damage values

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-44s %s" % ["PASS" if ok else "FAIL", label, detail])

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

func _box(size: Vector3, pos: Vector3, layer: int) -> StaticBody3D:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	cs.shape = box
	b.add_child(cs)
	b.collision_layer = layer
	b.collision_mask = 0
	world.add_child(b)
	b.global_position = pos
	return b

## A standing target at `local` (relative to the player, in the player's own frame: -Z is ahead).
func _target(local: Vector3) -> Node3D:
	var t: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	world.add_child(t)
	t.global_position = player.global_transform * local
	t.global_rotation = player.global_rotation + Vector3(0, PI, 0)   # facing the player
	# Stand still. With no PlayerRegistry autoload in a --script tree these AI run their full FSM and
	# walk, which makes every ratio a comparison of two DIFFERENT bones: the first run read
	# 10x0.75, 14x0.75, then 10x4.0 -- a headshot -- and called the chain broken. Their skeletons
	# still pose (the AnimationTree is its own node), so the hitboxes are where they look.
	t.set_physics_process(false)
	var mc: Node = t.get_node_or_null("MovementController")
	if mc != null:
		mc.set_physics_process(false)
	# ...and hold the POSE. Its AnimationTree is a separate node and keeps playing, so the bone the
	# capsule meets drifts between swings -- measured 10x0.75 then 14x1.00, an arm and then a torso,
	# which makes a ratio of two swings a ratio of two bones.
	var at: Node = _find(t, "AnimationTree")
	if at != null:
		at.set("active", false)
	var h: Node = t.get_node_or_null("Health")
	var key := t.get_instance_id()
	hits[key] = []
	if h != null:
		h.connect("hit", func(d): hits[key].append(d))
	return t

func _hits(t: Node3D) -> Array:
	return hits.get(t.get_instance_id(), [])

func _clear(nodes: Array) -> void:
	for n in nodes:
		if is_instance_valid(n):
			n.queue_free()
	await _tick(3)

## Press `fire` for `frames` physics frames through the real Input singleton, then release it.
## Returns the lowest AttackScale seen and every AttackClip state seen over the next `watch` frames.
func _press(frames: int, watch: int = 0) -> Dictionary:
	var min_scale := 999.0
	var states := {}
	var active_seen := false
	Input.action_press("fire")
	for i in range(frames + watch):
		if i == frames:
			Input.action_release("fire")
		await physics_frame
		var sc: float = tree_node.get("parameters/AttackScale/scale")
		min_scale = min(min_scale, sc)
		states[String(tree_node.get("parameters/AttackClip/current_state"))] = true
		if tree_node.get("parameters/Attack/active"):
			active_seen = true
	if frames + watch <= frames:
		Input.action_release("fire")
	return {"min_scale": min_scale, "states": states.keys(), "active": active_seen}

## Swap the MELEE slot to `scene`: drop whatever holds it, wait out that item's pickup cooldown so it
## cannot win the slot back, then let the new one auto-collect into the now-free slot.
var _last_melee: Node3D = null

func _swap_melee(scene: String) -> Node3D:
	# Unconditional: drop_current_weapon returns on its own for the fist, which is not droppable.
	wc.call("drop_current_weapon")
	await _tick(5)
	# Move the dropped weapon away. Left at the player's feet it simply auto-collects back into the
	# MELEE slot it just vacated the moment its pickup cooldown expires, and wins the race with the
	# weapon being swapped in.
	if _last_melee != null and is_instance_valid(_last_melee):
		var old_body: Node3D = _last_melee.get_parent() as Node3D
		if old_body != null:
			old_body.global_position = player.global_position + Vector3(60, 1, 0)
	await _tick(15)
	_last_melee = await _equip_melee(scene)
	return _last_melee

func _equip_melee(scene: String) -> Node3D:
	var item: Node3D = (load(scene) as PackedScene).instantiate() as Node3D
	world.add_child(item)
	item.global_position = player.global_position + Vector3(4, 1, 0)
	await _tick(3)                                  # it wraps itself in a PickupBody (W15)
	var body: Node3D = item.get_parent() as Node3D
	body.global_position = player.global_position + Vector3(0, 0.6, 0)
	await _tick(20)                                 # the MELEE slot is free: auto-collect
	wc.call("on_set_weapon", MELEE_SLOT)
	await _tick(60)                                 # holster -> draw
	return item

func _initialize() -> void:
	world = Node3D.new()
	root.add_child(world)
	_box(Vector3(80, 1, 80), Vector3(0, -0.5, 0), 1)
	var im: Node = load(IMPACT).new()
	world.add_child(im)
	await _tick(3)

	player = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(player)
	player.position = Vector3(0, 1.2, 0)
	await _tick(40)
	wc = player.get_node_or_null("WeaponController")
	tree_node = _find(player, "AnimationTree") as AnimationTree
	if wc == null or tree_node == null:
		print("FAIL: wc=%s tree=%s" % [wc != null, tree_node != null])
		quit(1)
		return

	# ── 0. every authored step names a clip the tree can play ──────────────────────────────────
	print("")
	print("=== 0. every step's clip resolves ===")
	var clip_node: AnimationNode = (tree_node.tree_root as AnimationNodeBlendTree).get_node("AttackClip")
	var inputs := {}
	for i in range(clip_node.get_input_count()):
		inputs[clip_node.get_input_name(i)] = true
	for scene in [FIST, MEW1, MEW2]:
		var w: Node = (load(scene) as PackedScene).instantiate()
		for s in w.get("attack_steps"):
			var a: String = s.get("animation")
			_check("%s: %s" % [scene.get_file(), a],
				tree_node.has_animation(a) and inputs.has(a),
				"in export: %s, AttackClip input: %s" % [tree_node.has_animation(a), inputs.has(a)])
		w.free()

	# ── 1. fist: reach, chain, hitstop, animation ──────────────────────────────────────────────
	print("")
	print("=== 1. fist -- reach from the chest, jab -> cross -> (pause) -> jab ===")
	var near := _target(Vector3(0, 0, -1.1))
	var far := _target(Vector3(0, 0, -3.5))
	await _tick(10)
	var s1 := await _press(2, 30)
	var after1: int = _hits(near).size()
	await _tick(4)                                           # < comboResetSeconds: the chain goes on
	var s2 := await _press(2, 30)
	var after2: int = _hits(near).size()
	await _tick(COMBO_RESET_FRAMES)                          # > comboResetSeconds: it starts over
	var s3 := await _press(2, 30)
	print("   [diag] hits after each swing: %d, %d, %d" % [after1, after2, _hits(near).size()])
	var h: Array = _hits(near)
	_check("reach: the target in front is hit", h.size() == 3, "%d hits %s" % [h.size(), str(h)])
	_check("reach: 3.5 m out is past the swing", _hits(far).size() == 0,
		"%d hits (on the camera's line, beyond the chest's reach)" % _hits(far).size())
	if h.size() == 3:
		_check("chain: the 2nd swing is the cross", absf(h[1] / h[0] - 1.4) < 0.05,
			"cross/jab = %.2f (want 14/10 = 1.40)" % (h[1] / h[0]))
		_check("chain: a pause restarts it", absf(h[2] / h[0] - 1.0) < 0.01,
			"3rd/1st = %.2f (want 1.00)" % (h[2] / h[0]))
	_check("anim: the attack one-shot plays", s1["active"], "Attack/active seen: %s" % s1["active"])
	_check("anim: jab clip, then cross clip",
		s1["states"].has("attack_jab_fist") and s2["states"].has("attack_cross_fist"),
		"swing 1 %s | swing 2 %s" % [str(s1["states"]), str(s2["states"])])
	_check("hitstop: the swing freezes on contact", s1["min_scale"] == 0.0,
		"lowest AttackScale %.3f during swing 1" % s1["min_scale"])
	_check("hitstop: and is given back", float(tree_node.get("parameters/AttackScale/scale")) > 0.0,
		"AttackScale now %.3f" % float(tree_node.get("parameters/AttackScale/scale")))
	await _clear([near, far])

	# ── 2. cleave + hit-once ───────────────────────────────────────────────────────────────────
	print("")
	print("=== 2. cleave -- one swing, two targets, one hit each ===")
	await _tick(COMBO_RESET_FRAMES)
	var left := _target(Vector3(-0.3, 0, -1.1))
	var right := _target(Vector3(0.3, 0, -1.1))
	await _tick(10)
	await _press(2, 40)
	_check("cleave: both targets hit by one swing", _hits(left).size() >= 1 and _hits(right).size() >= 1,
		"left %d, right %d" % [_hits(left).size(), _hits(right).size()])
	_check("hit-once: never twice in one swing", _hits(left).size() == 1 and _hits(right).size() == 1,
		"left %d, right %d (several bones, several frames, ONE hit)" % [_hits(left).size(), _hits(right).size()])
	await _clear([left, right])

	# ── 3. cover blocks ────────────────────────────────────────────────────────────────────────
	print("")
	print("=== 3. cover -- a wall between the chest and the target ===")
	await _tick(COMBO_RESET_FRAMES)
	var behind_wall := _target(Vector3(0, 0, -1.3))
	var wall := _box(Vector3(3, 3, 0.1), player.global_transform * Vector3(0, 1.5, -0.6), 1)
	await _tick(10)
	await _press(2, 40)
	_check("cover: the swing does not pass through", _hits(behind_wall).size() == 0,
		"%d hits" % _hits(behind_wall).size())
	await _clear([behind_wall, wall])

	# ── 4. something between the camera and the character ──────────────────────────────────────
	print("")
	print("=== 4. behind -- the camera ray stops BEHIND the character ===")
	await _tick(COMBO_RESET_FRAMES)
	var front := _target(Vector3(0, 0, -1.1))
	# Layer 8 (HITBOX): on the AimRay's mask (29) but not the spring arm's (17), so the boom does not
	# pull in and the camera ray really does end on this, between the camera and the player.
	var screen := _box(Vector3(3, 3, 0.1), player.global_transform * Vector3(0, 1.5, 1.4), 8)
	await _tick(10)
	var ray: RayCast3D = player.get_node_or_null("ActiveCamera/AimRay") as RayCast3D
	ray.force_raycast_update()
	var stops_behind: bool = ray.is_colliding() and ray.get_collider() == screen
	_check("setup: the camera ray stops on the screen", stops_behind,
		"collider %s" % (ray.get_collider().name if ray.is_colliding() else "none"))
	await _press(2, 40)
	_check("behind: the swing still lands in front", _hits(front).size() == 1,
		"%d hits (a camera-origin swing strikes the screen and whiffs)" % _hits(front).size())
	await _clear([front, screen])

	# ── 5. input buffer ────────────────────────────────────────────────────────────────────────
	print("")
	print("=== 5. buffer -- a tap during recovery is not eaten ===")
	await _tick(COMBO_RESET_FRAMES)
	var buf := _target(Vector3(0, 0, -1.1))
	await _tick(10)
	await _press(2, 13)          # jab: 0.35 s swing; now ~0.25 s in, i.e. in recovery
	await _press(2, 40)          # tapped mid-recovery: must come out as the next swing
	_check("buffer: the mid-recovery tap still swings", _hits(buf).size() == 2,
		"%d hits from 2 taps" % _hits(buf).size())
	await _clear([buf])

	# ── 6. first person resolves from the same chest ───────────────────────────────────────────
	print("")
	print("=== 6. fps -- same chest, same result ===")
	await _tick(COMBO_RESET_FRAMES)
	player.set("is_fps_mode", true)
	await _tick(20)
	var fps_t := _target(Vector3(0, 0, -1.1))
	var fps_far := _target(Vector3(0, 0, -3.5))
	await _tick(10)
	await _press(2, 40)
	_check("fps: the target in front is hit", _hits(fps_t).size() == 1, "%d hits" % _hits(fps_t).size())
	_check("fps: 3.5 m out is still past reach", _hits(fps_far).size() == 0, "%d hits" % _hits(fps_far).size())
	player.set("is_fps_mode", false)
	await _clear([fps_t, fps_far])

	# ── 7. knife: tap stabs, hold slashes ──────────────────────────────────────────────────────
	print("")
	print("=== 7. knife -- tap stabs, hold slashes ===")
	var knife := await _swap_melee(MEW1)             # the fist holds slot 0, so the MELEE slot is free
	var kn_t := _target(Vector3(0, 0, -1.2))
	await _tick(COMBO_RESET_FRAMES)
	var k1 := await _press(2, 50)                   # tap
	await _tick(COMBO_RESET_FRAMES)
	var k2 := await _press(40, 60)                  # hold 0.67 s > chargeThreshold 0.5 s
	var kh: Array = _hits(kn_t)
	_check("knife: equipped (its own clips play)",
		k1["states"].has("attack_stab_mw1"), "swing 1 clips %s" % str(k1["states"]))
	_check("knife: tap and hold both land", kh.size() == 2, "%d hits %s" % [kh.size(), str(kh)])
	if kh.size() == 2:
		_check("knife: the hold is the slash", absf(kh[1] / kh[0] - 2.5) < 0.05,
			"slash/stab = %.2f (want 100/40 = 2.50)" % (kh[1] / kh[0]))
	_check("knife: stab clip, then slash clip",
		k1["states"].has("attack_stab_mw1") and k2["states"].has("attack_slash_mw1"),
		"%s | %s" % [str(k1["states"]), str(k2["states"])])
	await _clear([kn_t])

	# ── 8. axe: light first, big second ────────────────────────────────────────────────────────
	print("")
	print("=== 8. axe -- light first, big second ===")
	var axe := await _swap_melee(MEW2)
	var axe_t := _target(Vector3(0, 0, -1.2))
	await _tick(COMBO_RESET_FRAMES)
	var a1 := await _press(2, 50)
	await _tick(4)
	var a2 := await _press(2, 60)
	var ah: Array = _hits(axe_t)
	_check("axe: equipped (its own clips play)",
		a1["states"].has("attack_swing_mw2"), "swing 1 clips %s" % str(a1["states"]))
	_check("axe: two swings, two hits", ah.size() == 2, "%d hits %s" % [ah.size(), str(ah)])
	if ah.size() == 2:
		_check("axe: the 2nd swing is the heavy one", absf(ah[1] / ah[0] - 2.0) < 0.05,
			"heavy/light = %.2f (want 120/60 = 2.00)" % (ah[1] / ah[0]))
	_check("axe: light clip, then heavy clip",
		a1["states"].has("attack_swing_mw2") and a2["states"].has("attack_chop_mw2"),
		"%s | %s" % [str(a1["states"]), str(a2["states"])])

	# ── 9. an AI swings too ────────────────────────────────────────────────────────────────────
	#
	# Everything above drives a Player. An AI is the other half of the melee path and shares none of
	# its rig: no PlayerController, no FPS mode, an AICameraController instead of a boom. What it does
	# share is the chest bone, the aim ray and ImpactManager, so this is where a player-only
	# assumption would show. Its weapon is collected the way an AI actually gets one (walking over a
	# pickup), and fired through WeaponController exactly as AttackState fires it: one frame of
	# `fire`, which is also why an AI knife always taps rather than charging.
	print("")
	print("=== 9. an AI's swing lands ===")
	var ai_pos := Vector3(12, 0, 0)
	var attacker: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	world.add_child(attacker)
	attacker.global_position = ai_pos
	await _tick(5)
	var ai_wc: Node = attacker.get_node_or_null("WeaponController")
	# An AI walks off on its own in a bare tree (no PlayerRegistry, so it never drops to a low LOD).
	# Freeze it BEFORE anything is placed relative to it: on the first run it had strolled 1.14 m by
	# the time the pickup was dropped on its old position, so it simply never collected it.
	attacker.set_physics_process(false)
	var ai_mc: Node = attacker.get_node_or_null("MovementController")
	if ai_mc != null:
		ai_mc.set_physics_process(false)
	await _tick(2)
	attacker.global_position = ai_pos

	var ai_axe: Node3D = (load(MEW2) as PackedScene).instantiate() as Node3D
	world.add_child(ai_axe)
	ai_axe.global_position = attacker.global_position + Vector3(3, 1, 0)
	await _tick(3)
	(ai_axe.get_parent() as Node3D).global_position = attacker.global_position + Vector3(0, 0.6, 0)
	await _tick(25)                                  # the AI's own MELEE slot is free: auto-collect
	ai_wc.call("on_set_weapon", MELEE_SLOT)
	await _tick(60)

	var ai_fwd: Vector3 = -attacker.global_transform.basis.z
	var ai_t := _target(Vector3.ZERO)
	ai_t.global_position = attacker.global_position + ai_fwd * 1.2
	await _tick(10)
	var ai_tree: AnimationTree = _find(attacker, "AnimationTree") as AnimationTree
	var ai_ray: RayCast3D = _find(attacker, "AimRay") as RayCast3D
	print("   [diag] ai at %s target at %s" % [attacker.global_position, ai_t.global_position])
	if ai_ray != null:
		var f: Vector3 = (ai_ray.to_global(ai_ray.target_position) - ai_ray.global_position).normalized()
		ai_ray.force_raycast_update()
		print("   [diag] ai ray BEFORE the snap: from %s fwd %s hits %s" % [ai_ray.global_position, f,
			ai_ray.get_collider().name if ai_ray.is_colliding() else "nothing"])
	# What AttackState does on the frame it fires: snapAimRay(target) -- aim the ray AT the victim.
	# (`snap_aim_ray` is not a registered method, so its two lines are reproduced here.) Without it
	# the swing follows whatever the camera rig happens to rest at, which for a frozen AI in a bare
	# tree was -X, 90 degrees off its own facing, and the swing went nowhere.
	var aim_at: Vector3 = ai_t.global_position + Vector3(0, 1.2, 0)
	ai_ray.target_position = ai_ray.to_local(aim_at)
	ai_ray.force_raycast_update()
	ai_wc.call("on_weapon_fire")                     # AttackState fires for exactly one frame
	await _tick(2)
	ai_wc.call("on_weapon_not_fire")
	await _tick(50)
	if ai_tree != null:
		print("   [diag] ai clip state %s" % String(ai_tree.get("parameters/AttackClip/current_state")))
	var ath: Array = _hits(ai_t)
	_check("ai: the swing lands", ath.size() == 1, "%d hits %s" % [ath.size(), str(ath)])
	_check("ai: it is the axe's light swing", ath.size() == 1 and ath[0] >= 30.0,
		"damage %s (axe light is 60 before the bone multiplier)" % (str(ath[0]) if ath.size() == 1 else "-"))

	# ── 10. a puppet replays the OWNER's swing, and deals nothing ──────────────────────────────
	#
	# Fire is replicated as state: `fireSeq` says only THAT a weapon fired. Which swing it was now
	# rides beside it in the snapshot's spare flag bits, because a puppet reconstructing the step
	# from its own chain cursor guesses -- and for a knife (tap vs hold) cannot guess at all. This
	# drives the puppet path directly: apply the owner's step, then play the cue.
	print("")
	print("=== 10. puppet replay ===")
	await _tick(COMBO_RESET_FRAMES)                  # the local chain has reset, so its next step is 0
	var pup_t := _target(Vector3.ZERO)
	pup_t.global_position = player.global_transform * Vector3(0, 0, -1.2)
	await _tick(10)
	wc.call("apply_replicated_fire_step", 1)         # the owner swung its HEAVY step
	wc.call("play_remote_fire_cue")
	var pup_states := {}
	for i in range(50):
		await physics_frame
		pup_states[String(tree_node.get("parameters/AttackClip/current_state"))] = true
	_check("puppet: replays the owner's step, not its own chain",
		pup_states.has("attack_chop_mw2"),
		"clips seen %s (a local chain would have picked step 0, the light swing)" % str(pup_states.keys()))
	_check("puppet: deals no damage", _hits(pup_t).size() == 0,
		"%d hits (damage is authority-only)" % _hits(pup_t).size())

	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
