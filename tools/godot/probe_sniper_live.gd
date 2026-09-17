extends SceneTree
## GATE (PLAN.md 2.8 item 10; was a study): scoped SNR1 accuracy against a LIVE AI -- animating, its distance LOD running --
## aimed the way a player aims: injected mouse motion steers the view onto the DRAWN bone
## (BoneAttachment3D x the hitbox's body_offset), then one shot through real Input.
## (user report 2026-09-16, after W31: "aim at a still enemy, first shot does not hit, the second does")
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_sniper_live.gd
##
## Matrix: idle / hostile AI x 50 / 150 / 260 m x five player situations (scope held, quick-scope,
## first-person preference, moving, just stopped) x five aim points (head, chest, upper arm, thigh, head
## edge). The magazine is refilled before every shot and a press that does not fire is reported as NO
## SHOT, not as a miss (the first run emptied a 99-round magazine and read the rest as misses).
##
## Asserted (2.8 items 3/4/10): every stationary (held, quick, fps) and JUST-STOPPED (10 frames after
## release — the scoped stop and the standing threshold) HEAD and CHEST shot lands on the aimed bone, and
## every limb / edge shot too (it was held to 90% as "a 3 cm capsule at 260 m can be grazed" -- the 3 misses in
## 72 were Jolt stepping over a small far capsule, fixed 2026-09-17, CLAUDE.md "A long ray steps over"); a
## MOVING scoped shot's cone is wide by design (> 5x the base) and the scoped speed is ScopeConfig's
## move_speed_factor x the unscoped max (0.4 x 8 = 3.2 m/s, +-0.3); and hitboxes match the drawn body.
##
## History — result 2026-09-16 before items 3/4 (the study): hitboxes match the drawn body to 0.000 m at every LOD tier; every
## STATIONARY shot lands on the aimed bone, 90/90; every miss is a MOVING (7.98 m/s, the scope does not
## slow the player) or JUST-STOPPED (2.74 m/s, 10 frames after release) shot -- SNR1's cone grows
## 0.03 deg per m/s.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const AI     := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const SNR1    := "res://src/main/resources/com/openworld/weapon/SNR1.tscn"
const IMPACT := "res://src/main/java/com/openworld/world/manager/ImpactManager.java"
const SENS := 0.07

var world: Node3D
var p: Node3D
var gun: Node3D
var cam_ctrl: Node

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

func _cam() -> Node3D:
	return p.get_node("ActiveCamera") as Node3D

## Where the DRAWN bone puts this hitbox: attachment (final pose) x body_offset.
## Aimed at the hitbox SHAPE's centre, not the body origin: a limb capsule is offset along its bone, and
## aiming at the body origin put the upper arm's 3 cm capsule edge-on (a 1 cm cone grazed past it at 260 m).
func _drawn(att: BoneAttachment3D, hb: PhysicalBone3D) -> Vector3:
	var shape_xf := Transform3D.IDENTITY
	for c in hb.get_children():
		if c is CollisionShape3D:
			shape_xf = (c as CollisionShape3D).transform
			break
	return (att.global_transform * hb.body_offset * shape_xf).origin

func _shape_centre(hb: PhysicalBone3D) -> Vector3:
	for c in hb.get_children():
		if c is CollisionShape3D:
			return (c as CollisionShape3D).global_position
	return hb.global_position

func _steer_to(target: Callable, frames: int) -> float:
	var err := 99.0
	for i in range(frames):
		var cam := _cam()
		var to: Vector3 = (target.call() as Vector3) - cam.global_position
		var f := -cam.global_transform.basis.z
		var want_yaw := rad_to_deg(atan2(-to.x, -to.z))
		var want_pitch := rad_to_deg(atan2(to.y, Vector2(to.x, to.z).length()))
		var yaw := rad_to_deg(atan2(-f.x, -f.z))
		var pitch := rad_to_deg(asin(clampf(f.y, -1.0, 1.0)))
		var dy := wrapf(want_yaw - yaw, -180.0, 180.0)
		var dp := want_pitch - pitch
		err = rad_to_deg(f.angle_to(to.normalized()))
		if err < 0.003:
			return err
		var ev := InputEventMouseMotion.new()
		ev.relative = Vector2(-dy / SENS, -dp / SENS)
		cam_ctrl.call("_input", ev)
		await physics_frame
	return err

func _initialize() -> void:
	world = Node3D.new()
	root.add_child(world)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(1400, 2, 1400)
	cs.shape = sh
	floor.add_child(cs)
	world.add_child(floor)
	floor.position = Vector3(0, -1, 0)
	world.add_child(load(IMPACT).new())
	await _tick(3)

	p = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
	await _tick(40)
	gun = (load(SNR1) as PackedScene).instantiate() as Node3D
	world.add_child(gun)
	gun.global_position = p.global_position + Vector3(0, 0.3, 0)
	await _tick(30)
	var wc: Node = p.get_node("WeaponController")
	for slot in range(6):
		if String(gun.get_parent().name).begins_with("Socket"):
			break
		wc.call("on_set_weapon", slot)
		await _tick(40)
	gun.set("magazine", 99)
	if "--control" in OS.get_cmdline_user_args():
		# the rules before 2.8 items 3/4: no standing threshold, no scoped slowdown, the ordinary stop
		gun.set("standing_speed_fraction", 0.0)
		gun.get("scope").set("move_speed_factor", 1.0)
		gun.get("scope").set("stop_acceleration_factor", 1.0)
		print("CONTROL: standing_speed_fraction 0, move_speed_factor 1, stop_acceleration_factor 1")
	cam_ctrl = p.get_node("TPSCameraController")
	print("player controller %s  cam %s" % [p.get("controller"), cam_ctrl])

	var totals := {}
	var fails := [0]
	var check := func(label: String, ok: bool, detail: String) -> void:
		if not ok:
			fails[0] += 1
		print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", label, detail])
	var moving_speeds := []
	var moving_spreads := []
	var worst_gap := 0.0
	for variant in ["idle", "hostile"]:
		for d in [50.0, 150.0, 260.0]:
			print("")
			print("=== %s AI at %.0f m ===" % [variant, d])
			var t: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
			var h: Node = t.get_node("Health")
			h.set("max_health", 1.0e9)
			world.add_child(t)
			t.global_position = Vector3(0.0, 0.0, -d)
			t.global_rotation = Vector3(0, PI, 0)
			if variant == "idle":
				var info: Resource = t.get("character_info")
				if info != null:
					info.set("faction", "neutral")
			var mc: Node = t.get_node_or_null("MovementController")
			if mc != null:
				mc.set_physics_process(false)
			var log: Array = []
			h.connect("hit", func(dmg): log.append(dmg))
			var skel: Skeleton3D = _find(t, "Skeleton3D") as Skeleton3D
			var pairs := {}
			for bone in ["head_2", "spine_03", "upperarm_r", "thigh_l"]:
				var att := BoneAttachment3D.new()
				att.bone_name = bone
				skel.add_child(att)
				pairs[bone] = [att, _find(t, "Physical Bone " + bone) as PhysicalBone3D]
			await _tick(180)
			var worst := 0.0
			for i2 in range(60):
				await physics_frame
				for bone in pairs:
					worst = maxf(worst, _drawn(pairs[bone][0], pairs[bone][1]).distance_to(_shape_centre(pairs[bone][1])))
			print("  LOD %s  drawn-vs-hitbox worst over 1 s: %.3f m" % [t.call("lod_level_now"), worst])
			worst_gap = maxf(worst_gap, worst)
			for scen in ["held", "quick", "fps", "moving", "stopped"]:
				p.set("is_fps_mode", scen == "fps")
				for target in [["head_2", 600.0, 0.0], ["spine_03", 150.0, 0.0], ["upperarm_r", 112.5, 0.0], ["thigh_l", 75.0, 0.0], ["head_2", 600.0, 0.07]]:
					var att: BoneAttachment3D = pairs[target[0]][0]
					var hb: PhysicalBone3D = pairs[target[0]][1]
					var side := float(target[2])
					var aim_at := func() -> Vector3:
						return _drawn(att, hb) + _cam().global_transform.basis.x * side
					# Every shot from the firing spot: the moving run-ups used to walk the player ~180 m sideways,
					# and from 70 deg off the target's own arm really is in front of its chest.
					(p as CharacterBody3D).velocity = Vector3.ZERO
					var moved: bool = p.global_position.distance_to(Vector3(0, 1.2, 0)) > 0.5
					p.global_position = Vector3(0, 1.2, 0)
					# the camera rigs (TPS follow lerp, FPS eye baseline filter) settle after a jump
					await _tick(120 if moved else 5)
					if scen == "quick":
						Input.action_release("aim")
						await _tick(60)
						Input.action_press("aim")
					else:
						Input.action_press("aim")
					if scen == "moving":
						Input.action_press("left")
						await _tick(45)   # a run-up: fire while actually moving, not on the first frame of it
					if scen == "stopped":
						Input.action_press("left")
						await _tick(60)
						Input.action_release("left")
					var err: float = await _steer_to(aim_at, 10 if scen in ["quick", "stopped"] else 90)
					var gap := _drawn(att, hb).distance_to(_shape_centre(hb))
					var speed: float = (p as CharacterBody3D).velocity.length()
					var spread: float = float(wc.call("spread_now_deg"))
					if scen == "moving":
						moving_speeds.append(speed)
						moving_spreads.append(spread)
					var n0 := log.size()
					gun.set("magazine", 5)
					var mag0 := int(gun.get("magazine"))
					var why: String = str(wc.call("fire_gate_state")) if wc.has_method("fire_gate_state") else ""
					Input.action_press("fire")
					await _tick(2)
					Input.action_release("fire")
					await _tick(4)
					if scen == "moving":
						Input.action_release("left")
					var got: Array = log.slice(n0)
					var fired := int(gun.get("magazine")) < mag0
					var verdict := "MISS" if fired else "NO SHOT (%s)" % why
					if got.size() == 1 and absf(float(got[0]) - float(target[1])) < 0.01:
						verdict = "ok"
					elif not got.is_empty():
						verdict = "WRONG %s" % str(got)
					if verdict != "ok" and not (side > 0.0 and got.size() == 1):
						print("      shot: %s  target drawn %s" % [gun.call("last_shot_report"), _drawn(att, hb)])
					var key := "%s/%s" % [variant, scen]
					if not totals.has(key):
						totals[key] = [0, 0]
					totals[key][1] += 1
					if verdict == "ok" or (side > 0.0 and got.size() == 1):
						totals[key][0] += 1
					var vital: bool = target[0] in ["head_2", "spine_03"] and side == 0.0
					var vk := key + (":vital" if vital else ":limb")
					if not totals.has(vk):
						totals[vk] = [0, 0]
					totals[vk][1] += 1
					if verdict == "ok":
						totals[vk][0] += 1
					print("  %-7s %-10s side %.2f  err %.4f deg  gap %.3f m  speed %.2f  spread %.3f  -> %s" % [
						scen, target[0], side, err, gap, speed, spread, verdict])
					await _tick(95)
			Input.action_release("aim")
			t.queue_free()
			await _tick(30)
	print("")
	for key in totals:
		print("  SUMMARY %-18s %d / %d" % [key, totals[key][0], totals[key][1]])
	print("")
	# Every stationary / stopped shot must land. Limbs were held to 90% as "grazes" until 2026-09-17: the misses
	# were a long Jolt ray stepping over a small far capsule (WeaponItem.nearerSmallShape), 69/72 -> 72/72.
	var limb_ok := 0
	var limb_n := 0
	for variant in ["idle", "hostile"]:
		for scen in ["held", "quick", "fps", "stopped"]:
			var k := "%s/%s:vital" % [variant, scen]
			check.call("%s: every head/chest shot on the aimed bone" % k, totals.has(k) and totals[k][0] == totals[k][1],
				"%d / %d" % [totals[k][0], totals[k][1]] if totals.has(k) else "no shots")
			var l := "%s/%s" % [variant, scen]
			limb_ok += totals[l][0] - totals[k][0]
			limb_n += totals[l][1] - totals[k][1]
	check.call("stationary + stopped limb / edge shots all land", limb_ok == limb_n, "%d / %d" % [limb_ok, limb_n])
	var mean_speed := 0.0
	var min_spread := 1e9
	for v in moving_speeds:
		mean_speed += float(v) / moving_speeds.size()
	for v in moving_spreads:
		min_spread = minf(min_spread, float(v))
	check.call("scoped move speed = 0.4 x 8 m/s", absf(mean_speed - 3.2) < 0.3, "mean %.2f m/s over %d shots" % [mean_speed, moving_speeds.size()])
	check.call("a moving scoped shot is wide by design (> 5x base)", min_spread > 0.025, "narrowest %.4f deg (base 0.005)" % min_spread)
	check.call("hitboxes match the drawn body at every LOD tier", worst_gap < 0.01, "worst %.3f m" % worst_gap)
	print("PASS (0 failures)" if fails[0] == 0 else "FAIL (%d failures)" % fails[0])
	quit(1 if fails[0] > 0 else 0)
