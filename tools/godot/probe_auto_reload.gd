extends SceneTree
## Does the last round start the reload by itself -- and does an EMPTY, DRY weapon sit still?
##
##   godot --headless --fixed-fps 60 --path . --script tools/godot/probe_auto_reload.gd
##
## User-asked (2026-09-16), with the right worry attached: auto-reload is the modern-shooter default
## (CS, PUBG, COD -- a player who has just fired their last round should not have to press a dead
## trigger to find out), but "reload when empty" invites an INFINITE RELOAD LOOP once the reserve is
## dry. The implementation answers that structurally rather than with a flag: the shot that empties
## the magazine calls `WeaponController.onWeaponReload`, which returns immediately when the reserve is
## 0 or a reload is already running. So there is no timer to retry, no state to get stuck in, and a
## weapon that is empty AND dry does nothing however often the hook fires.
##
## This probe is that argument, measured. Four cases, each able to fail for one reason:
##   1. SNR1 with reserve      -- the 5th shot starts a reload with NO further input; ammo moves.
##   2. SNR1 with a dry reserve -- the magazine empties and `reloadsStarted()` never advances again,
##      through a long idle AND through twenty more trigger presses (the loop check).
##   3. autoReloadOnEmpty off  -- no reload starts by itself, and the pre-existing dry-PRESS path
##      still starts one, so the flag turns the feature off without breaking manual reloading.
##   4. A THROWABLE never auto-reloads -- an emptied grenade stack CLEARS ITS SLOT
##      (ThrowableItem.onMagazineEmpty), and reloading into itself instead would strand the slot.
##
## Known, harmless log in case 4: `ThrowableItem.launch` parents the grenade under
## `getTree().getCurrentScene()`, which is null in a bare SceneTree probe, so the throw prints a
## NullPointerException from the spawn. The round is still consumed and the empty path still runs,
## which is what this case measures.
##
## Fire rate and reload speed are raised at runtime: this measures the reload RULE, not the weapon's
## tuning, and a bolt rifle's real 1.1 s cadence would make the run four times longer for nothing.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const WEAPON_DIR := "res://src/main/resources/com/openworld/weapon/%s.tscn"
## Shots are pressed through the real Input singleton, so PlayerController -> WeaponController is the
## path under test. SNR1 is semi-auto, so every shot needs its own press.
const PRESS_FRAMES := 3
const RELEASE_FRAMES := 9
## Frames to sit still after a case's last shot: long enough for a started reload to finish.
const SETTLE_FRAMES := 60

var fails := 0

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

func _floor(parent: Node) -> void:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(200, 1, 200)
	cs.shape = box
	b.add_child(cs)
	b.position = Vector3(0, -0.5, 0)
	parent.add_child(b)

## Spawn a Player, drop `weapon_id` on it and bring it to the hand. Returns [player, gun, controller].
func _armed(world: Node3D, weapon_id: String, at: Vector3, brisk: bool = true) -> Array:
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
		if _in_hand(gun):
			break
		wc.call("on_set_weapon", slot)
		await _tick(40)
	if not _in_hand(gun):
		print("  FAIL  %s never became the active weapon (parent %s)" % [weapon_id, gun.get_parent().name])
		fails += 1
		return []
	# Combat, so the W21 aim gate is not what blocks a shot, and (unless the case is measuring the
	# weapon's own cadence) a brisk one, because these cases are about the reload RULE, not the tuning.
	p.set("combat", true)
	if brisk:
		gun.set("fire_rate", 8.0)
		gun.set("reload_speed", 4.0)
	await _tick(20)
	return [p, gun, wc]

## Is this weapon the active one? A weapon with a holdSocket hangs off `Socket*`; a THROWABLE has
## none and is stowed on `WeaponAttachment` itself (W15), which is where it is carried from.
func _in_hand(gun: Node3D) -> bool:
	var parent := String(gun.get_parent().name)
	return parent.begins_with("Socket") or parent == "WeaponAttachment"

## One trigger pull.
func _shoot() -> void:
	Input.action_press("fire")
	await _tick(PRESS_FRAMES)
	Input.action_release("fire")
	await _tick(RELEASE_FRAMES)

## Press until the magazine reads 0 (or `cap` presses have gone by). The first press after a draw is
## eaten by WeaponController's draw-settle window, so pressing magazine_size times is NOT the same
## thing as emptying the magazine -- and this probe is about what happens AT empty.
func _empty(gun: Node3D, wc: Node, cap: int) -> int:
	var presses := 0
	while int(gun.get("magazine")) > 0 and presses < cap:
		await _shoot()
		presses += 1
		print("  press %d: %s" % [presses, _state(gun, wc)])
	return presses

## Press (repeatedly, if the draw-settle eats the first one) until the magazine DROPS, and return the
## physics frame it dropped on. -1 if it never did.
func _shoot_until_drop(gun: Node3D, budget_frames: int) -> int:
	var before: int = int(gun.get("magazine"))
	var waited := 0
	while waited < budget_frames:
		Input.action_press("fire")
		await _tick(PRESS_FRAMES)
		Input.action_release("fire")
		waited += PRESS_FRAMES
		for i in range(RELEASE_FRAMES):
			await physics_frame
			waited += 1
			if int(gun.get("magazine")) < before:
				return Engine.get_physics_frames()
	return -1

func _state(gun: Node3D, wc: Node) -> String:
	return "mag %d/%d reserve %d reloads %d%s" % [
		int(gun.get("magazine")), int(gun.get("magazine_size")), int(gun.get("reserve")),
		int(wc.call("reloads_started")), "  (reloading)" if bool(wc.call("reloading_now")) else ""]

func _initialize() -> void:
	var world := Node3D.new()
	root.add_child(world)
	_floor(world)
	await _tick(3)
	var x := 0.0

	# ── 1. the last round starts the reload by itself ─────────────────────────────────────────
	print("")
	print("=== SNR1, reserve 20: the shot that empties the magazine reloads ===")
	var a: Array = await _armed(world, "SNR1", Vector3(x, 1.2, 0))
	x += 8.0
	if not a.is_empty():
		var p: Node3D = a[0]
		var gun: Node3D = a[1]
		var wc: Node = a[2]
		var mag_size: int = int(gun.get("magazine_size"))
		var before: int = int(wc.call("reloads_started"))
		print("  start: %s" % _state(gun, wc))
		await _empty(gun, wc, mag_size + 3)
		var started: int = int(wc.call("reloads_started")) - before
		_check("the empty magazine started a reload", started == 1, "%d reload(s) started, no further input" % started)
		await _tick(SETTLE_FRAMES)
		print("  settled: %s" % _state(gun, wc))
		_check("the magazine refilled", int(gun.get("magazine")) == mag_size,
			"mag %d/%d" % [int(gun.get("magazine")), mag_size])
		_check("the ammo came from the reserve", int(gun.get("reserve")) == 20 - mag_size,
			"reserve %d (was 20, magazine holds %d)" % [int(gun.get("reserve")), mag_size])
		p.queue_free()
		await _tick(5)

	# ── 2. the loop check: empty AND dry ─────────────────────────────────────────────────────
	print("")
	print("=== SNR1, reserve 0: an empty, dry weapon must sit still ===")
	a = await _armed(world, "SNR1", Vector3(x, 1.2, 0))
	x += 8.0
	if not a.is_empty():
		var p: Node3D = a[0]
		var gun: Node3D = a[1]
		var wc: Node = a[2]
		gun.set("reserve", 0)
		var mag_size: int = int(gun.get("magazine_size"))
		await _empty(gun, wc, mag_size + 3)
		var after_empty: int = int(wc.call("reloads_started"))
		print("  emptied: %s" % _state(gun, wc))
		_check("no reload started with a dry reserve", after_empty == 0, "%d reload(s) started" % after_empty)
		# a long idle: a retrying implementation would climb here
		await _tick(180)
		_check("idle does not retry", int(wc.call("reloads_started")) == after_empty,
			"%d reload(s) after 3 s of idle" % int(wc.call("reloads_started")))
		# and twenty more presses: the dry-PRESS path must not loop either
		for i in range(20):
			await _shoot()
		_check("20 presses on an empty weapon do not loop", int(wc.call("reloads_started")) == after_empty,
			"%d reload(s) after 20 presses" % int(wc.call("reloads_started")))
		_check("the weapon is still empty and idle", int(gun.get("magazine")) == 0 and not bool(wc.call("reloading_now")),
			_state(gun, wc))
		# ammo arriving later still reloads on the next press (the manual fallback)
		gun.set("reserve", 5)
		await _shoot()
		_check("a press after ammo arrives reloads", int(wc.call("reloads_started")) == after_empty + 1,
			"%d reload(s) once the reserve was refilled" % int(wc.call("reloads_started")))
		p.queue_free()
		await _tick(5)

	# ── 3. the control: the flag turns it off without breaking manual reloads ────────────────
	print("")
	print("=== SNR1 with autoReloadOnEmpty = false (the control) ===")
	a = await _armed(world, "SNR1", Vector3(x, 1.2, 0))
	x += 8.0
	if not a.is_empty():
		var p: Node3D = a[0]
		var gun: Node3D = a[1]
		var wc: Node = a[2]
		gun.set("auto_reload_on_empty", false)
		var mag_size: int = int(gun.get("magazine_size"))
		await _empty(gun, wc, mag_size + 3)
		print("  emptied: %s" % _state(gun, wc))
		_check("no reload started with the flag off", int(wc.call("reloads_started")) == 0,
			"%d reload(s) started" % int(wc.call("reloads_started")))
		await _shoot()
		_check("a dry PRESS still reloads manually", int(wc.call("reloads_started")) == 1,
			"%d reload(s) after one more press" % int(wc.call("reloads_started")))
		p.queue_free()
		await _tick(5)

	# ── 4. a throwable clears its slot instead ───────────────────────────────────────────────
	print("")
	print("=== FRG1 (throwable): the last grenade clears the slot, it does not reload ===")
	a = await _armed(world, "FRG1", Vector3(x, 1.2, 0))
	if not a.is_empty():
		var p: Node3D = a[0]
		var gun: Node3D = a[1]
		var wc: Node = a[2]
		# slot 5 is THROWABLE (WeaponController.slotTypes). A throwable has no holdSocket, so it is
		# stowed on WeaponAttachment active or not -- the parent cannot say which, so ask for the slot.
		wc.call("on_set_weapon", 5)
		await _tick(60)
		# Give it a reserve it could reload FROM, or the case proves nothing: FRG1 ships with 0 and any
		# rule at all would look correct. With a reserve, a throwable that auto-reloaded would refill
		# itself and keep the slot instead of clearing it.
		gun.set("reserve", 3)
		await _tick(10)
		print("  before the throw: %s" % _state(gun, wc))
		await _shoot()
		await _tick(30)
		var thrown: bool = is_instance_valid(gun) and int(gun.get("magazine")) == 0
		print("  after the throw: %s" % (_state(gun, wc) if is_instance_valid(gun) else "(freed with its slot)"))
		_check("the throw emptied the stack", thrown or not is_instance_valid(gun),
			"magazine %s" % (str(gun.get("magazine")) if is_instance_valid(gun) else "(freed)"))
		_check("no reload started for the throwable", int(wc.call("reloads_started")) == 0,
			"%d reload(s) started with 3 in reserve" % int(wc.call("reloads_started")))
		_check("the stack did not refill itself", not is_instance_valid(gun) or int(gun.get("magazine")) == 0,
			"magazine %s, reserve %s" % [str(gun.get("magazine")) if is_instance_valid(gun) else "-",
				str(gun.get("reserve")) if is_instance_valid(gun) else "-"])
		p.queue_free()
		await _tick(5)

	# ── 5. a BOLT ACTION is the fire rate, not a reload ──────────────────────────────────────
	# The design question this settles (user, 2026-09-16): a bolt cycle needs a hard per-shot
	# cooldown and one shot per trigger pull, and `auto = false` + `fireRate` are exactly that. If it
	# were built on the reload path instead, every shot would move reserve into the magazine, bump the
	# replicated reloadSeq (so every peer would play a reload cue per shot) and read as "reloading" to
	# the HUD ring. So the assertion is BOTH halves: the cadence is 1/fire_rate, and nothing reloads
	# while the magazine still has rounds.
	print("")
	print("=== SNR1 at its shipped rate: the bolt cycle is the fire timer, not a reload ===")
	a = await _armed(world, "SNR1", Vector3(x + 8.0, 1.2, 0), false)
	if not a.is_empty():
		var p: Node3D = a[0]
		var gun: Node3D = a[1]
		var wc: Node = a[2]
		var want: float = 1.0 / float(gun.get("fire_rate"))
		var f0: int = await _shoot_until_drop(gun, 300)
		var f1: int = await _shoot_until_drop(gun, 300)
		var got: float = float(f1 - f0) / 60.0
		print("  two shots %d frames apart = %.3f s (1/fire_rate = %.3f s); %s" % [f1 - f0, got, want, _state(gun, wc)])
		_check("the bolt cadence is 1/fire_rate", f0 > 0 and f1 > 0 and absf(got - want) < 0.12,
			"%.3f s between shots, wanted %.3f" % [got, want])
		_check("no reload while the magazine has rounds", int(wc.call("reloads_started")) == 0 and int(gun.get("magazine")) > 0,
			"%d reload(s), %s" % [int(wc.call("reloads_started")), _state(gun, wc)])
		p.queue_free()
		await _tick(5)

	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
