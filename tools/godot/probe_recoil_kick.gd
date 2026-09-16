extends SceneTree
## Does firing kick the weapon visibly, stack under full auto, and settle back to rest?
##
##   godot --headless --fixed-fps 60 --path . --script tools/godot/probe_recoil_kick.gd
##   ... -- --control      # WeaponRecoilModifier.weight = 0: the kick is off, checks 2/3 must FAIL
##
## PLAN.md A3 / CLAUDE.md W27. The kick is `character.WeaponRecoilModifier`: a per-shot step on two
## springs (push-back along the bore, muzzle pitch up), the firing hand turned about the shoulder
## joint by the pitch and pushed back along the bore, and `TwoBoneIK` swinging the arm to follow.
##
## Two things make this probe honest, and both cost a wrong reading first if skipped:
##
##   1. THE CLIP MOVES THE HAND BY ITSELF. The aim pose breathes, so "the hand moved 5 mm" is not
##      evidence of anything. Every case measures a QUIET window of the same length first and reports
##      the clip's own wobble; the kick has to beat it by a clear multiple.
##   2. "BACK TO REST" IS THE SPRING'S QUESTION, NOT THE HAND'S. The hand never returns to an exact
##      position, because the clip has carried on. So rest is asserted on the modifier's own state
##      (< 1 mm / < 0.05 deg) and the hand only has to come back INSIDE the clip's wobble.
##
## Read through a BoneAttachment3D, never `get_bone_global_pose`: a modifier writes into the FINAL
## pose only, so the pre-modifier accessors report a working kick as completely inert (W14/W5).

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const WEAPON_DIR := "res://src/main/resources/com/openworld/weapon/%s.tscn"

## weapon, frames of held fire, shots that should come out of it, its authored kick.
const CASES := [
	{"id": "AR4", "fire_frames": 48, "min_shots": 6},   # full auto, 10 rps: the stacking case
	{"id": "SG1", "fire_frames": 10, "min_shots": 1},   # one heavy shot, the slowest settle
]

const QUIET_FRAMES := 60
const SETTLE_FRAMES := 45          # 0.75 s: longer than 4/kick_spring for either weapon (0.18 / 0.29 s)
const SETTLE_BACK := 0.001         # m — the plan's "< 1 mm"
const SETTLE_PITCH := 0.05         # deg
## The hand has to move at least this far. 2 cm, not "more than nothing": the camera recoil lifts the
## aim point and the aim modifiers swing the whole arm after it, which alone moves the hand 0.008 m
## (AR4) to 0.011 m (SG1) -- measured with `--control`. Anything under that is not evidence of a kick.
const MIN_KICK_M := 0.020
const MIN_RISE_DEG := 1.0
const WOBBLE_MULTIPLE := 3.0       # ... and clear the clip's own motion by this much
const SUPPORT_TOLERANCE := 0.05    # the off hand stays on the gun THROUGHOUT (probe_weapon_fit's number)
const YAW_TOLERANCE := 1.0         # the kick is pitch-only: yaw must not move (W21's fire gate)

var control := false
var fails := 0

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

## Spawn a Player, drop `weapon_id` on it (auto-pickup) and bring it to the hand. [player, gun] or [].
func _armed_player(world: Node3D, weapon_id: String, at: Vector3) -> Array:
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
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

## Gun pitch/yaw in the mesh's frame (the mesh is -Z forward).
func _gun_angles(mesh_root: Node3D, gun: Node3D) -> Vector2:
	var fwd: Vector3 = mesh_root.global_transform.basis.inverse() * (-gun.global_transform.basis.z)
	return Vector2(rad_to_deg(atan2(fwd.x, -fwd.z)), rad_to_deg(asin(clampf(fwd.y, -1.0, 1.0))))

## How far the bore sits ABOVE the aim line, degrees -- the measurement that isolates THIS layer.
## The muzzle also rises because the camera recoil that already existed (FirearmItem.applyRecoil ->
## ControlRotation.recoilPitch) lifts the aim point and the aim modifiers follow it: measured against
## the world, the kick is indistinguishable from that, and a control with the kick switched off still
## reads +1.3 deg of "muzzle rise". Against the aim line the camera layer cancels, because both the
## gun and the target move with it.
func _gun_above_aim(gun: Node3D, aim_target: Node3D) -> float:
	var bore: Vector3 = (-gun.global_transform.basis.z).normalized()
	var to_aim: Vector3 = (aim_target.global_position - gun.global_position)
	if to_aim.length() < 0.01:
		return 0.0
	return rad_to_deg(asin(clampf(bore.y, -1.0, 1.0)) - asin(clampf(to_aim.normalized().y, -1.0, 1.0)))

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		if a == "--control":
			control = true
	print("kick: %s" % ("OFF (control: WeaponRecoilModifier.weight = 0)" if control else "on"))
	var world := Node3D.new()
	root.add_child(world)
	_floor(world)
	await _tick(3)

	var x := 0.0
	for case in CASES:
		var weapon_id: String = case["id"]
		print("")
		print("=== %s ===" % weapon_id)
		var armed: Array = await _armed_player(world, weapon_id, Vector3(x, 1.2, 0))
		x += 6.0
		if armed.is_empty():
			continue
		var p: Node3D = armed[0]
		var gun: Node3D = armed[1]
		var sk: Skeleton3D = _find(p, "Skeleton3D") as Skeleton3D
		var mesh_root: Node3D = _find(p, "MeshRoot") as Node3D
		var hand := _attach(sk, "hand_r")
		var aim_target: Node3D = _find(p, "AimTarget") as Node3D
		var recoil: Node = sk.get_node_or_null("WeaponRecoilModifier")
		var support: Node = sk.get_node_or_null("SupportHandIKModifier")
		if recoil == null:
			_check("%s: the body has a WeaponRecoilModifier" % weapon_id, false, "no such node under Skeleton3D")
			p.queue_free()
			continue
		if control:
			recoil.set("weight", 0.0)
		print("  authored kick: back %.3f m  pitch %.1f deg  spring %.1f  damping %.1f" % [
			float(gun.get("kick_back")), float(gun.get("kick_pitch")),
			float(gun.get("kick_spring")), float(gun.get("kick_damping"))])

		Input.action_press("aim")
		await _tick(90)

		# ── quiet: what the clip does on its own over the same window ───────────────────────────
		var to_body: Transform3D = mesh_root.global_transform.affine_inverse()
		var rest: Vector3 = to_body * hand.global_position
		var rest_ang: Vector2 = _gun_angles(mesh_root, gun)
		var wobble := 0.0
		var wobble_pitch := 0.0
		var wobble_above := 0.0
		for i in range(QUIET_FRAMES):
			await physics_frame
			to_body = mesh_root.global_transform.affine_inverse()
			wobble = maxf(wobble, (to_body * hand.global_position).distance_to(rest))
			wobble_pitch = maxf(wobble_pitch, absf(_gun_angles(mesh_root, gun).y - rest_ang.y))
			wobble_above = maxf(wobble_above, absf(_gun_above_aim(gun, aim_target)))
		print("  quiet: the clip alone moves the hand %.4f m, the muzzle %.2f deg, the bore %.2f deg off the aim"
			% [wobble, wobble_pitch, wobble_above])

		# ── burst ──────────────────────────────────────────────────────────────────────────────
		var mag_before := int(gun.get("magazine"))
		var peak := 0.0
		var peak_rise := 0.0
		var peak_above := 0.0
		var peak_yaw := 0.0
		var peak_back := 0.0
		var worst_support := 0.0
		Input.action_press("fire")
		for i in range(int(case["fire_frames"])):
			await physics_frame
			to_body = mesh_root.global_transform.affine_inverse()
			peak = maxf(peak, (to_body * hand.global_position).distance_to(rest))
			var ang: Vector2 = _gun_angles(mesh_root, gun)
			peak_rise = maxf(peak_rise, ang.y - rest_ang.y)
			peak_above = maxf(peak_above, _gun_above_aim(gun, aim_target))
			peak_yaw = maxf(peak_yaw, absf(ang.x - rest_ang.x))
			peak_back = maxf(peak_back, absf(float(recoil.call("current_back"))))
			if support != null:
				var miss: float = support.call("last_grip_miss")
				if miss >= 0.0:
					worst_support = maxf(worst_support, miss)
		Input.action_release("fire")
		var shots: int = mag_before - int(gun.get("magazine"))
		print("  burst: %d shots, %d kicks taken; hand peak %.4f m, muzzle +%.2f deg (bore +%.2f deg off the aim), spring peak %.4f m; yaw drift %.2f deg"
			% [shots, int(recoil.call("kick_count")), peak, peak_rise, peak_above, peak_back, peak_yaw])

		# ── settle ─────────────────────────────────────────────────────────────────────────────
		await _tick(SETTLE_FRAMES)
		to_body = mesh_root.global_transform.affine_inverse()
		var after: float = (to_body * hand.global_position).distance_to(rest)
		var s_back: float = absf(float(recoil.call("current_back")))
		var s_pitch: float = absf(float(recoil.call("current_pitch")))
		print("  settle: spring back %.5f m, pitch %.4f deg; hand %.4f m from where it was" % [s_back, s_pitch, after])

		_check("%s: fired the burst" % weapon_id, shots >= int(case["min_shots"]),
			"%d shots (the kick must not eat presses; expected >= %d)" % [shots, int(case["min_shots"])])
		_check("%s: one kick per shot" % weapon_id, int(recoil.call("kick_count")) == (0 if control else shots),
			"%d kicks for %d shots" % [int(recoil.call("kick_count")), shots])
		_check("%s: the hand visibly kicks" % weapon_id,
			peak > MIN_KICK_M and peak > wobble * WOBBLE_MULTIPLE,
			"%.4f m vs the clip's own %.4f m (need > %.3f and > %.1fx)" % [peak, wobble, MIN_KICK_M, WOBBLE_MULTIPLE])
		_check("%s: the muzzle kicks OFF THE AIM LINE" % weapon_id,
			peak_above > MIN_RISE_DEG and peak_above > wobble_above * WOBBLE_MULTIPLE,
			"+%.2f deg off the aim vs the clip's own %.2f deg (world rise was +%.2f, which the camera recoil also causes)"
				% [peak_above, wobble_above, peak_rise])
		_check("%s: settles back to rest" % weapon_id, s_back < SETTLE_BACK and s_pitch < SETTLE_PITCH,
			"back %.5f m / pitch %.4f deg after %.2f s" % [s_back, s_pitch, SETTLE_FRAMES / 60.0])
		_check("%s: the hand comes back" % weapon_id, after < wobble + SETTLE_BACK,
			"%.4f m from rest, inside the clip's %.4f m" % [after, wobble])
		_check("%s: the support hand stays on the gun" % weapon_id, worst_support < SUPPORT_TOLERANCE,
			"worst grip miss %.4f m during the burst (tolerance %.2f)" % [worst_support, SUPPORT_TOLERANCE])
		_check("%s: pitch only, no yaw kick" % weapon_id, peak_yaw < YAW_TOLERANCE,
			"gun yaw drifted %.2f deg (W21 gates firing on yaw)" % peak_yaw)

		Input.action_release("aim")
		p.queue_free()
		await _tick(5)

	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
