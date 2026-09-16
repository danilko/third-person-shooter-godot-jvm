extends SceneTree
## Does a scoped view drift, does a held breath steady it, and does holding too long cost more than
## never holding at all?  (PLAN.md 2.7 piece 2, CLAUDE.md W30)
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_scope_sway.gd
##   ... -- --control      # both rifles declare no sway: every drift check must fail
##
## SR3 SHIPS WITH NO SWAY (a still, CS-style scope); this gate sets scope_sway = 0.5 on the pair to
## keep the mechanism honest for a weapon that opts in.
##
## THE MEASUREMENT IS PAIRED. The drift is a function of a phase clock, so "the drift was smaller
## while the breath was held" measured one window after another compares two different stretches of
## the same wave, and a quiet stretch reads as a working breath. So two Players are driven by the same
## Input on the same frames, both scoping on the same frame -- their clocks are identical -- and they
## differ in ONE thing: A cannot hold its breath (`breath_hold_seconds` ~0, so a press winds it for a
## single tick and it recovers the next). Every assertion about the breath is a ratio B/A over the
## same frames, so the wave cancels and only the breath is left. The first window, where neither
## holds, has to read 1.00 -- that is the check that the pairing is real.
##
## The drift is measured off the CAMERA, never off the helper's numbers: both Players are put in first
## person BEFORE scoping (the preference, so scoping does not change rig), their view direction is
## recorded with no scope up, and every later sample is the angle from that rest direction. No mouse
## input arrives in a headless tree, so the rest direction does not move on its own.
##
##   1. open drift: visible (> 40% of the rifle's amplitude), bounded by it (yaw <= amp, pitch <= 70%),
##      and identical in the pair (ratio 1.00);
##   2. the aim point is on the scope's centre line at every sample -- the drift moves where the shot
##      goes, it is not a picture drawn over a still aim;
##   3. holding breath: B's drift under a quarter of A's, B's breath spending, A never holding;
##   4. holding too long: B winded at ~breath_hold_seconds, and its drift then WORSE than A's;
##   5. the key still held through the recovery starts no second hold; a fresh press does;
##   6. letting go of aim settles both views back onto their rest direction.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const WEAPON := "res://src/main/resources/com/openworld/weapon/%s.tscn"

var fails := 0
var control := false

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-52s %s" % ["PASS" if ok else "FAIL", label, detail])

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

func _box(world: Node3D, size: Vector3, pos: Vector3) -> void:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = size
	cs.shape = sh
	b.add_child(cs)
	world.add_child(b)
	b.position = pos

## Spawn a Player and bring `weapon_id` to the hand through a real pickup + on_set_weapon.
func _armed(world: Node3D, weapon_id: String, at: Vector3) -> Array:
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = at
	await _tick(40)
	var gun: Node3D = (load(WEAPON % weapon_id) as PackedScene).instantiate() as Node3D
	world.add_child(gun)
	gun.global_position = p.global_position + Vector3(0, 0.3, 0)
	await _tick(30)
	var wc: Node = p.get_node_or_null("WeaponController")
	for slot in range(6):
		if String(gun.get_parent().name).begins_with("Socket"):
			break
		wc.call("on_set_weapon", slot)
		await _tick(40)
	if not String(gun.get_parent().name).begins_with("Socket"):
		_check("%s reached the hand" % weapon_id, false, "parent %s" % gun.get_parent().name)
		return []
	return [p, gun, wc]

func _cam(p: Node3D) -> Node3D:
	return _find(p, "ActiveCamera") as Node3D

## (yaw, pitch) of a direction, degrees, in the camera's own convention (-Z forward, +Y up).
func _angles(fwd: Vector3) -> Vector2:
	return Vector2(rad_to_deg(atan2(-fwd.x, -fwd.z)), rad_to_deg(asin(clampf(fwd.y, -1.0, 1.0))))

func _forward(p: Node3D) -> Vector3:
	return -_cam(p).global_transform.basis.z

## Deviation from the rest direction this frame, degrees: (yaw, pitch, total angle).
func _dev(p: Node3D, rest: Vector3) -> Vector3:
	var f := _forward(p)
	var a := _angles(f)
	var r := _angles(rest)
	return Vector3(wrapf(a.x - r.x, -180.0, 180.0), a.y - r.y, rad_to_deg(f.angle_to(rest)))

## Sample `frames` frames of both players. Returns
## [sumA, sumB, peakYawA, peakPitchA, worstAimOff, aimTravelA, aimRangeA].
## aimTravelA is how far A's aim point moved on the wall from where A's REST line meets it: the shot
## point really moving, which is what makes aimOff (the view line vs the aim point) not a tautology of
## AimTarget hanging off the camera.
func _window(a: Node3D, b: Node3D, rest_a: Vector3, rest_b: Vector3, frames: int) -> Array:
	var rest_hit := _cam(a).global_position + rest_a * ((-39.5 - _cam(a).global_position.z) / rest_a.z)
	var travel := 0.0
	var rng := 0.0
	var sa := 0.0
	var sb := 0.0
	var py := 0.0
	var pp := 0.0
	var aim_off := 0.0
	for i in range(frames):
		await physics_frame
		var da := _dev(a, rest_a)
		var db := _dev(b, rest_b)
		sa += da.z
		sb += db.z
		py = maxf(py, absf(da.x))
		pp = maxf(pp, absf(da.y))
		var ta: Node3D = a.get_node_or_null("ActiveCamera/AimRay/AimTarget") as Node3D
		if ta != null:
			travel = maxf(travel, ta.global_position.distance_to(rest_hit))
			rng = maxf(rng, ta.global_position.distance_to(_cam(a).global_position))
		for p in [a, b]:
			var cam := _cam(p)
			var target: Node3D = p.get_node_or_null("ActiveCamera/AimRay/AimTarget") as Node3D
			if target != null:
				var to_t: Vector3 = target.global_position - cam.global_position
				if to_t.length() > 1.0:
					aim_off = maxf(aim_off, rad_to_deg(to_t.angle_to(-cam.global_transform.basis.z)))
	return [sa, sb, py, pp, aim_off, travel, rng]

func _ratio(w: Array) -> float:
	return float(w[1]) / float(w[0]) if float(w[0]) > 1e-9 else NAN

func _initialize() -> void:
	control = "--control" in OS.get_cmdline_user_args()
	var world := Node3D.new()
	root.add_child(world)
	_box(world, Vector3(200, 2, 200), Vector3(0, -1, 0))
	# A wall down-range so the aim ray finds a real point to put the aim target on.
	_box(world, Vector3(200, 60, 1), Vector3(0, 10, -40))
	await _tick(3)

	var ra: Array = await _armed(world, "SR3", Vector3(0, 1.2, 0))
	var rb: Array = await _armed(world, "SR3", Vector3(12, 1.2, 0))
	if ra.is_empty() or rb.is_empty():
		print("FAIL (could not arm the pair)")
		quit(1)
		return
	var a: Node3D = ra[0]
	var b: Node3D = rb[0]
	# SR3 ships with a still scope (scope_sway 0, user decision 2026-09-16), so the MECHANISM is gated
	# on a rifle given the drift it was built for.
	var amp := 0.5
	ra[1].get("scope").set("sway", 0.0 if control else amp)
	rb[1].get("scope").set("sway", 0.0 if control else amp)
	if control:
		print("  CONTROL: both rifles declare scope_sway = 0")
	# A cannot hold its breath: a press empties it in one tick and it is back the next, so A's drift is
	# the OPEN drift on exactly B's frames.
	a.set("breath_hold_seconds", 0.0001)
	a.set("breath_recover_seconds", 0.0001)
	var hold_s := float(b.get("breath_hold_seconds"))
	print("  SR3 scope_sway %.2f deg; B holds %.1f s, recovers %.1f s" % [
		amp, hold_s, float(b.get("breath_recover_seconds"))])

	a.set("is_fps_mode", true)
	b.set("is_fps_mode", true)
	await _tick(90)
	var rest_a := _forward(a)
	var rest_b := _forward(b)

	print("")
	print("=== 1-2. open drift, the pair on the same frames ===")
	Input.action_press("aim")
	await _tick(60)
	_check("both scoped", bool(a.call("scoped_now")) and bool(b.call("scoped_now")),
		"A %s  B %s" % [a.call("scoped_now"), b.call("scoped_now")])
	var w: Array = await _window(a, b, rest_a, rest_b, 360)
	print("  6 s: peak yaw %.3f  peak pitch %.3f  mean A %.3f  mean B %.3f  ratio %.3f" % [
		w[2], w[3], w[0] / 360.0, w[1] / 360.0, _ratio(w)])
	_check("the scoped view drifts visibly", float(w[2]) > 0.4 * amp,
		"peak yaw %.3f deg against an amplitude of %.2f" % [w[2], amp])
	_check("the drift is bounded by the amplitude", float(w[2]) <= amp + 0.02 and float(w[3]) <= 0.7 * amp + 0.02,
		"yaw %.3f <= %.2f, pitch %.3f <= %.2f" % [w[2], amp, w[3], 0.7 * amp])
	_check("the pair is on the same wave (ratio 1.00)", absf(_ratio(w) - 1.0) < 0.03, "B/A %.3f" % _ratio(w))
	_check("the aim point is on the scope's centre line", float(w[4]) < 0.1,
		"worst %.4f deg between the view and the aim target" % w[4])
	# ... and that line is on the WALL and moves with the drift: at 40 m a 0.5 deg drift is ~0.35 m.
	# Floored at 5 cm so a view that does not drift at all cannot pass this by expecting nothing.
	var expect := maxf(deg_to_rad(float(w[2])) * 39.5 * 0.6, 0.05)
	_check("the shot point on the wall moves with the drift", float(w[5]) > expect and float(w[6]) < 45.0,
		"moved %.3f m off the rest line (expected > %.3f), aim range %.1f m" % [w[5], expect, w[6]])

	print("")
	print("=== 3. holding breath ===")
	Input.action_press("hold_breath")
	await _tick(45)
	var breath0 := float(b.call("breath_now"))
	w = await _window(a, b, rest_a, rest_b, 120)
	print("  2 s held: mean A %.4f  mean B %.4f  ratio %.3f  B breath %.2f -> %.2f" % [
		w[0] / 120.0, w[1] / 120.0, _ratio(w), breath0, b.call("breath_now")])
	_check("B is holding its breath, A cannot", bool(b.call("holding_breath_now")) and not bool(a.call("holding_breath_now")),
		"B %s  A %s" % [b.call("holding_breath_now"), a.call("holding_breath_now")])
	_check("a held breath steadies the scope (B/A < 0.25)", _ratio(w) < 0.25, "B/A %.3f" % _ratio(w))
	_check("holding spends the breath", float(b.call("breath_now")) < breath0 and breath0 < 1.0,
		"%.2f -> %.2f" % [breath0, b.call("breath_now")])

	print("")
	print("=== 4. holding too long ===")
	var waited := (45 + 120) / 60.0
	while not bool(b.call("winded_now")) and waited < hold_s + 2.0:
		await physics_frame
		waited += 1.0 / 60.0
	print("  winded after %.2f s of holding" % waited)
	_check("B runs out at ~breath_hold_seconds", bool(b.call("winded_now")) and absf(waited - hold_s) < 0.3,
		"%.2f s, declared %.1f" % [waited, hold_s])
	await _tick(36)
	w = await _window(a, b, rest_a, rest_b, 90)
	print("  1.5 s winded: mean A %.4f  mean B %.4f  ratio %.3f" % [w[0] / 90.0, w[1] / 90.0, _ratio(w)])
	_check("winded is WORSE than never holding (B/A > 1.4)", _ratio(w) > 1.4, "B/A %.3f" % _ratio(w))

	print("")
	print("=== 5. the key held through the recovery ===")
	await _tick(150)
	_check("the winded spell ends", not bool(b.call("winded_now")), "winded %s, breath %.2f" % [
		b.call("winded_now"), b.call("breath_now")])
	_check("no second hold starts with the key still down", not bool(b.call("holding_breath_now")),
		"holding %s" % b.call("holding_breath_now"))
	Input.action_release("hold_breath")
	await _tick(2)
	Input.action_press("hold_breath")
	await _tick(2)
	_check("a fresh press holds again", bool(b.call("holding_breath_now")), "holding %s" % b.call("holding_breath_now"))
	Input.action_release("hold_breath")

	print("")
	print("=== 6. letting go of aim ===")
	Input.action_release("aim")
	await _tick(120)
	var da := _dev(a, rest_a)
	var db := _dev(b, rest_b)
	print("  after release: A %.4f deg  B %.4f deg off rest  scoped %s/%s" % [
		da.z, db.z, a.call("scoped_now"), b.call("scoped_now")])
	_check("both views settle back onto their rest direction", da.z < 0.01 and db.z < 0.01,
		"A %.4f  B %.4f deg" % [da.z, db.z])

	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
