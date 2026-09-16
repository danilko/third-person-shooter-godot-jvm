extends SceneTree
## Does the scope put BOTH views behind the shooter's eye -- and can anything strand them there?
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_sniper_scope.gd
##   ... -- --control      # the preference-writing implementation this design refuses
##
## PLAN.md 2.7 piece 1. The view question was DECIDED (user, 2026-09-16): a scoped shot is FIRST
## PERSON and a TPS player scoping sees exactly what an FPS player sees. The trap that creates is the
## one W6 already closed for the carrier seam -- an implementation that WRITES `is_fps_mode` when the
## scope goes up and writes it back when it comes down cannot survive an interruption between the two
## writes, and leaves the player stuck in first person with no way out. So the view is DERIVED
## (`Character.isFirstPersonView() == isFpsMode || scoped`) and the preference is never touched.
##
## Every case here is either that rule or an interruption that would strand a latched implementation:
##
##   1. TPS -> scope -> release. The camera moves to the FPS rig and back, the FOV reaches the
##      weapon's `scopedFov` and returns, the head hides and comes back, the overlay shows and hides,
##      and `is_fps_mode` is FALSE at every step -- the preference was not written.
##   2. FPS -> scope -> release. First person throughout, `is_fps_mode` still TRUE at every step.
##   3. A non-scoped weapon (AR4). Holding aim does not scope, does not move the camera, does not
##      change the FOV. The control for every measurement above.
##   4-6. INTERRUPTIONS, each with the aim button STILL HELD: a weapon switch, sitting in a carrier,
##      and death. Each must leave the camera on the TPS boom with the preference intact. A latched
##      implementation passes 1-3 and fails these.
##
## `--control` reproduces the refused implementation by writing `is_fps_mode` itself on the way in
## and leaving it (the interruption happens before the write back). Cases 1 and 2 still pass -- which
## is the point of running it -- and the interruptions fail.
##
## The rig a frame is being drawn from is measured, not asked: ActiveCamera is written by whichever
## controller is active, so the probe compares its world position with the TPS boom's Proxy and the
## FPS rig's Pivot and reports whichever it is sitting on. They are ~3 m apart, so there is no
## ambiguity.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const WEAPON := "res://src/main/resources/com/openworld/weapon/%s.tscn"
const OVERLAY := "res://src/main/java/com/openworld/ui/ScopeOverlay.java"
## Killing goes through Health, which is not registered; this is the probe helper that reaches it.
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"

## Scoping is a tween of the weapon's own scopeZoomTime (0.12 s on SR3) plus the rig handover.
const SETTLE := 30
## Coming back OUT is slower to measure than going in, and for a reason that is not the scope: the
## aim-stay timer holds combat for 0.5 s after the button (so the camera does not snap out of the
## combat framing on a twitch), and the combat/movement FOV tween is another 0.5 s on top. A short
## settle here would read the ordinary combat FOV and call it a scope that did not zoom back.
const RELEASE_SETTLE := 120

var fails := 0
var control := false

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

func _floor(world: Node3D) -> void:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(200, 2, 200)
	cs.shape = sh
	b.add_child(cs)
	b.position = Vector3(0, -1, 0)
	world.add_child(b)

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

## Which rig is writing ActiveCamera this frame: "FPS", "TPS", or "?" when neither is close.
func _rig(p: Node3D) -> String:
	var cam: Node3D = _find(p, "ActiveCamera") as Node3D
	var tps: Node3D = p.get_node_or_null("TPSCameraController/Yaw/Pitch/Pivot/SpringArm/Proxy")
	var fps: Node3D = p.get_node_or_null("FPSCameraController/Yaw/Pitch/Pivot")
	if cam == null or tps == null or fps == null:
		return "?"
	var dt := cam.global_position.distance_to(tps.global_position)
	var df := cam.global_position.distance_to(fps.global_position)
	if df < 0.05 and df < dt:
		return "FPS"
	if dt < 0.05 and dt < df:
		return "TPS"
	return "?"

func _fov(p: Node3D) -> float:
	var cam: Node3D = _find(p, "ActiveCamera") as Node3D
	return float(cam.get("fov")) if cam != null else -1.0

## Attach a ScopeOverlay to this body so the optic can be measured with no HUDManager/EventBus.
func _overlay(p: Node3D) -> Node:
	var script: Script = load(OVERLAY)
	var ov: Control = script.new() as Control
	ov.anchor_right = 1.0
	ov.anchor_bottom = 1.0
	root.add_child(ov)
	ov.call("wire_character", p)
	return ov

func _aim_down(p: Node3D, control_latch: bool) -> void:
	Input.action_press("aim")
	if control_latch:
		p.set("is_fps_mode", true)     # the REFUSED implementation: write the preference
	await _tick(SETTLE)

func _aim_up(p: Node3D, control_latch: bool) -> void:
	Input.action_release("aim")
	if control_latch:
		p.set("is_fps_mode", false)    # ... and write it back, if nothing interrupted first
	await _tick(RELEASE_SETTLE)

func _initialize() -> void:
	control = "--control" in OS.get_cmdline_user_args()
	var world := Node3D.new()
	root.add_child(world)
	_floor(world)
	await _tick(3)
	var x := 0.0

	print("")
	print("=== SR3, from THIRD person: scoping is first person and the preference is untouched ===")
	var a: Array = await _armed(world, "SR3", Vector3(x, 1.2, 0))
	x += 12.0
	if not a.is_empty():
		var p: Node3D = a[0]
		var gun: Node3D = a[1]
		var wc: Node = a[2]
		var head: Node3D = _find(p, "head") as Node3D
		var ov: Node = _overlay(p)
		var want_fov := float(gun.get("scope").get("fov"))
		await _tick(90)   # let the resting FOV finish its own tween before it is used as a baseline
		var rig0 := _rig(p)
		var fov0 := _fov(p)
		print("  before: rig %s  fov %.1f  head %s  fps_mode %s" % [rig0, fov0, head.visible, p.get("is_fps_mode")])
		_check("starts on the TPS boom", rig0 == "TPS", "rig %s" % rig0)

		await _aim_down(p, control)
		var rig1 := _rig(p)
		var fov1 := _fov(p)
		print("  scoped: rig %s  fov %.1f  head %s  fps_mode %s  scoped %s" % [
			rig1, fov1, head.visible, p.get("is_fps_mode"), wc.call("scoped_now")])
		_check("the scope is up", bool(wc.call("scoped_now")), "WeaponController.scopedNow()")
		_check("the camera moved to the FPS rig", rig1 == "FPS", "rig %s" % rig1)
		_check("the FOV reached scopedFov", absf(fov1 - want_fov) < 1.0,
			"fov %.2f, weapon declares %.2f" % [fov1, want_fov])
		_check("the head is hidden", not head.visible, "head.visible = %s" % head.visible)
		_check("the optic is on screen", bool(ov.call("scope_shown")), "ScopeOverlay.visible")
		_check("the view PREFERENCE was not written", control or not bool(p.get("is_fps_mode")),
			"is_fps_mode = %s%s" % [p.get("is_fps_mode"), "  (control writes it on purpose)" if control else ""])

		await _aim_up(p, control)
		var rig2 := _rig(p)
		var fov2 := _fov(p)
		print("  released: rig %s  fov %.1f  head %s  fps_mode %s" % [rig2, fov2, head.visible, p.get("is_fps_mode")])
		_check("the camera returned to the TPS boom", rig2 == "TPS", "rig %s" % rig2)
		_check("the FOV came back", absf(fov2 - fov0) < 1.0, "fov %.2f, was %.2f" % [fov2, fov0])
		_check("the head came back", head.visible, "head.visible = %s" % head.visible)
		_check("the optic is gone", not bool(ov.call("scope_shown")), "ScopeOverlay.visible")
		ov.queue_free()
		p.queue_free()
		await _tick(5)

	print("")
	print("=== SR3, from FIRST person: scoping changes the FOV and nothing else ===")
	a = await _armed(world, "SR3", Vector3(x, 1.2, 0))
	x += 12.0
	if not a.is_empty():
		var p: Node3D = a[0]
		var gun: Node3D = a[1]
		p.set("is_fps_mode", true)
		# In FPS `wantCombat` is unconditionally true (PlayerController), so the resting FOV here is
		# the COMBAT one and it has to finish tweening before it means anything.
		await _tick(90)
		var fov0 := _fov(p)
		_check("starts on the FPS rig", _rig(p) == "FPS", "rig %s" % _rig(p))
		await _aim_down(p, false)
		print("  scoped: rig %s  fov %.1f  fps_mode %s" % [_rig(p), _fov(p), p.get("is_fps_mode")])
		_check("stays first person while scoped", _rig(p) == "FPS", "rig %s" % _rig(p))
		_check("the FOV reached scopedFov", absf(_fov(p) - float(gun.get("scope").get("fov"))) < 1.0,
			"fov %.2f" % _fov(p))
		await _aim_up(p, false)
		print("  released: rig %s  fov %.1f  fps_mode %s" % [_rig(p), _fov(p), p.get("is_fps_mode")])
		_check("returns to FIRST person, not third", _rig(p) == "FPS", "rig %s" % _rig(p))
		_check("the preference survived", bool(p.get("is_fps_mode")), "is_fps_mode = %s" % p.get("is_fps_mode"))
		_check("the FOV came back", absf(_fov(p) - fov0) < 1.0, "fov %.2f, was %.2f" % [_fov(p), fov0])
		p.queue_free()
		await _tick(5)

	print("")
	print("=== AR4, the control: a weapon with no scope does not scope ===")
	a = await _armed(world, "AR4", Vector3(x, 1.2, 0))
	x += 12.0
	if not a.is_empty():
		var p: Node3D = a[0]
		var wc: Node = a[2]
		await _tick(90)
		var fov0 := _fov(p)
		Input.action_press("aim")
		await _tick(SETTLE)
		var aimed_fov := _fov(p)
		print("  aiming: rig %s  fov %.1f (idle %.1f)  scoped %s" % [_rig(p), aimed_fov, fov0, wc.call("scoped_now")])
		_check("an unscoped weapon does not scope", not bool(wc.call("scoped_now")), "scopedNow()")
		_check("the camera stayed on the boom", _rig(p) == "TPS", "rig %s" % _rig(p))
		# Aiming an AR4 moves the FOV -- that is the ordinary combat framing, and it is NOT a scope.
		_check("the FOV is nowhere near a scope", aimed_fov > 40.0,
			"fov %.2f while aiming; SR3's scope is 20" % aimed_fov)
		await _aim_up(p, false)
		_check("the ordinary aim FOV returns as before", absf(_fov(p) - fov0) < 1.0,
			"fov %.2f, idle was %.2f" % [_fov(p), fov0])
		p.queue_free()
		await _tick(5)

	print("")
	print("=== SR3: the bolt and the reload leave the scope; aim still held brings it back (piece 4) ===")
	a = await _armed(world, "SR3", Vector3(x, 1.2, 0))
	x += 12.0
	if not a.is_empty():
		var p: Node3D = a[0]
		var gun: Node3D = a[1]
		var wc: Node = a[2]
		var ov: Node = _overlay(p)
		var cycle := 1.0 / float(gun.get("fire_rate"))
		await _tick(90)
		await _aim_down(p, false)
		_check("scoped before the shot", bool(p.call("scoped_now")) and absf(_fov(p) - 20.0) < 1.0,
			"scoped %s fov %.1f" % [p.call("scoped_now"), _fov(p)])
		var mag0 := int(gun.get("magazine"))
		Input.action_press("fire")
		await _tick(3)
		Input.action_release("fire")
		await _tick(20)
		print("  cycling: mag %d -> %d  scoped %s  raised %s  rig %s  fov %.1f  optic %s  fps_mode %s" % [
			mag0, gun.get("magazine"), p.call("scoped_now"), wc.call("scope_raised_now"), _rig(p), _fov(p),
			ov.call("scope_shown"), p.get("is_fps_mode")])
		_check("the shot fired", int(gun.get("magazine")) == mag0 - 1, "mag %d -> %d" % [mag0, gun.get("magazine")])
		_check("... named CYCLING (2.8 item 2)", str(wc.call("weapon_state_now")) == "CYCLING", str(wc.call("weapon_state_now")))
		_check("the bolt cycle drops the zoom", not bool(p.call("scoped_now")) and _fov(p) > 40.0,
			"scoped %s fov %.1f" % [p.call("scoped_now"), _fov(p)])
		_check("... and the optic", not bool(ov.call("scope_shown")), "ScopeOverlay.visible")
		_check("... but the view stays first person", _rig(p) == "FPS" and not bool(p.get("is_fps_mode")),
			"rig %s, is_fps_mode %s" % [_rig(p), p.get("is_fps_mode")])
		await _tick(int(cycle * 60.0) + 20)
		print("  bolt home (%.2f s): scoped %s  fov %.1f" % [cycle, p.call("scoped_now"), _fov(p)])
		_check("aim still held: the scope comes back after the bolt", bool(p.call("scoped_now")) and absf(_fov(p) - 20.0) < 1.0,
			"scoped %s fov %.1f" % [p.call("scoped_now"), _fov(p)])

		var reloads0 := int(wc.call("reloads_started"))
		Input.action_press("reload")
		await _tick(3)
		Input.action_release("reload")
		await _tick(20)
		print("  reloading: reloading %s  scoped %s  rig %s  fov %.1f" % [
			wc.call("reloading_now"), p.call("scoped_now"), _rig(p), _fov(p)])
		_check("a reload started", int(wc.call("reloads_started")) > reloads0, "reloads %d" % wc.call("reloads_started"))
		_check("... named RELOADING", str(wc.call("weapon_state_now")) == "RELOADING", str(wc.call("weapon_state_now")))
		_check("the reload drops the zoom, first person kept", not bool(p.call("scoped_now")) and _rig(p) == "FPS",
			"scoped %s rig %s" % [p.call("scoped_now"), _rig(p)])
		var waited := 0
		while bool(wc.call("reloading_now")) and waited < 600:
			await physics_frame
			waited += 1
		await _tick(20)
		_check("the scope comes back after the reload", bool(p.call("scoped_now")) and absf(_fov(p) - 20.0) < 1.0,
			"scoped %s fov %.1f after %.2f s of reload" % [p.call("scoped_now"), _fov(p), waited / 60.0])

		# 2.8 item 2: the draw SETTLE is not a cycle — switching back to the rifle with aim held, the zoom
		# returns on the frame the draw ends and stays up through the settle (it used to drop with it).
		wc.call("on_set_weapon", 0)
		await _tick(60)
		var settle_frames := 0
		var settle_scoped := 0
		for sl in range(1, 7):
			wc.call("on_set_weapon", sl)
			await _tick(2)
			if str(wc.call("weapon_state_now")) == "SWITCHING":
				break
		for i in range(120):
			await physics_frame
			if str(wc.call("weapon_state_now")) == "SETTLING":
				settle_frames += 1
				if bool(wc.call("scoped_now")):
					settle_scoped += 1
		_check("the draw settle is named SETTLING and keeps the zoom", settle_frames > 0 and settle_scoped == settle_frames,
			"%d settle frames, %d scoped" % [settle_frames, settle_scoped])
		await _tick(30)

		Input.action_press("fire")
		await _tick(3)
		Input.action_release("fire")
		await _tick(10)
		await _aim_up(p, false)
		_check("letting go of aim mid-cycle returns to third person", _rig(p) == "TPS" and not bool(p.call("scoped_now")),
			"rig %s scoped %s" % [_rig(p), p.call("scoped_now")])

		# The control: a scoped rifle that does NOT leave the eye keeps its zoom through the cycle.
		gun.get("scope").set("unscope_to_cycle", false)
		await _tick(int(cycle * 60.0) + 10)
		await _aim_down(p, false)
		Input.action_press("fire")
		await _tick(3)
		Input.action_release("fire")
		await _tick(20)
		_check("control: unscope_to_cycle = false stays zoomed", bool(p.call("scoped_now")) and absf(_fov(p) - 20.0) < 1.0,
			"scoped %s fov %.1f" % [p.call("scoped_now"), _fov(p)])
		await _aim_up(p, false)
		ov.queue_free()
		p.queue_free()
		await _tick(5)

	# ── The interruptions. Each holds the aim button THROUGHOUT: the scope must end anyway. ──
	await _interruption(world, Vector3(x, 1.2, 0), "a weapon switch",
		func(p: Node3D, wc: Node) -> void: wc.call("on_set_weapon", 0))
	x += 12.0
	await _interruption(world, Vector3(x, 1.2, 0), "sitting in a carrier",
		func(p: Node3D, wc: Node) -> void: p.set("current_vehicle_node", p))
	x += 12.0
	var helper: Node = (load(HELPER) as Script).new() as Node
	root.add_child(helper)
	await _interruption(world, Vector3(x, 1.2, 0), "death",
		func(p: Node3D, wc: Node) -> void: helper.call("kill", p))

	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)

## Scope, then interrupt with the button still held, and assert the scope ended and the preference
## is intact. This is the whole reason the state is derived rather than latched.
func _interruption(world: Node3D, at: Vector3, what: String, interrupt: Callable) -> void:
	print("")
	print("=== interrupted by %s, with the aim button still HELD ===" % what)
	var a: Array = await _armed(world, "SR3", at)
	if a.is_empty():
		return
	var p: Node3D = a[0]
	var wc: Node = a[2]
	await _tick(20)
	await _aim_down(p, control)
	if not bool(p.call("scoped_now")):
		_check("scoped before the interruption", false, "the scope never came up")
		p.queue_free()
		await _tick(5)
		return
	interrupt.call(p, wc)
	await _tick(SETTLE * 3)
	print("  after: rig %s  scoped %s (weapon says %s)  fps_mode %s" % [
		_rig(p), p.call("scoped_now"), wc.call("scoped_now"), p.get("is_fps_mode")])
	# The CHARACTER is what the camera, the head and the HUD ask -- it adds the two conditions the
	# weapon cannot see (dead, or in a seat), which is exactly what two of these three cases are.
	_check("the scope ended", not bool(p.call("scoped_now")), "Character.scopedNow()")
	_check("the camera is not stranded in first person", _rig(p) == "TPS", "rig %s" % _rig(p))
	_check("the preference is intact", not bool(p.get("is_fps_mode")),
		"is_fps_mode = %s" % p.get("is_fps_mode"))
	Input.action_release("aim")
	p.queue_free()
	await _tick(5)
