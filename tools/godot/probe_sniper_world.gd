extends SceneTree
## Scoped SNR1 STANDING shots in DebugWorld itself (PLAN.md P0 0.4). The flat-arena studies
## (probe_sniper_hits / probe_sniper_live) could not reproduce "standing still, first shot at a still
## enemy does not hit", so this runs on the real scene: Terrain3D, the streamed road pieces, zone AI,
## pickups, the real pre-placed Player.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_sniper_world.gd  [-- --dirs=8 --dists=100,175,250 --live]
##
## For each target spot (a ring of directions x distances around the Player, on the ground, with a clear
## line of sight to the chest) an AICharacter is placed (movement off unless --live), the view is steered
## onto the DRAWN bone by injected mouse motion (the probe_sniper_live idiom) and one shot is fired
## through real Input with the scope held. Per shot it logs: every collider on the scope line up to the
## target (what the shot meets FIRST), the player's speed and is_on_floor at the press, the target's
## speed, the current cone, and every Health.hit on the target. Spots whose chest is not visible are
## reported with what blocks them and whether that blocker has anything DRAWN (candidate: an invisible
## collider) instead of being shot at.
##
## Result 2026-09-16 (P0 0.4): 28 / 33 on the aimed bone; the other 5 all OCCLUDED by a collider that is
## drawn where it collides -- a building, a zone AI walking across the line at 34 m, and the crest of
## DebugRoads' `loop` (the proxy's top 13.361 m == the drawn __surface 13.361 m) hiding the chest while
## the head cleared it. 0 true misses: the standing-miss report was NOT reproduced on the real scene.
## Gate: exit 0 when there is no true miss and no wrong bone.

const WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const SNR1 := "res://src/main/resources/com/openworld/weapon/SNR1.tscn"
const SENS := 0.07
const AIM_MASK := 29

var world: Node3D
var p: CharacterBody3D
var gun: Node3D
var cam_ctrl: Node
var fails := 0

func _arg(name: String, def: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--%s=" % name):
			return a.substr(name.length() + 3)
		if a == "--%s" % name:
			return "true"
	return def

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

func _drawn(att: BoneAttachment3D, hb: PhysicalBone3D) -> Vector3:
	return (att.global_transform * hb.body_offset).origin

func _space() -> PhysicsDirectSpaceState3D:
	return world.get_world_3d().direct_space_state

## Ground height under (x, z) on the world layer, or NAN.
func _ground(x: float, z: float) -> float:
	var rq := PhysicsRayQueryParameters3D.create(Vector3(x, 400, z), Vector3(x, -200, z), 1)
	var hit := _space().intersect_ray(rq)
	return hit["position"].y if not hit.is_empty() else NAN

func _owned_by(n: Object, owner: Node) -> bool:
	var x: Node = n as Node
	while x != null:
		if x == owner:
			return true
		x = x.get_parent()
	return false

func _has_visual(n: Node) -> bool:
	if n == null:
		return false
	for c in n.find_children("*", "VisualInstance3D", true, false):
		if (c as VisualInstance3D).is_visible_in_tree():
			return true
	var par := n.get_parent()
	return par is VisualInstance3D or (par != null and par.find_children("*", "MeshInstance3D", false, false).size() > 0)

## Every collider from `from` to `to` on the AimRay mask, in order, skipping the shooter. [name, dist, node]
func _line(from: Vector3, to: Vector3, skip: Node) -> Array:
	var out := []
	var exclude := []
	for k in range(12):
		var rq := PhysicsRayQueryParameters3D.create(from, to, AIM_MASK, exclude)
		rq.collide_with_areas = false
		var hit := _space().intersect_ray(rq)
		if hit.is_empty():
			break
		exclude.append(hit["rid"])
		var who: Object = hit["collider"]
		if _owned_by(who, skip):
			continue
		out.append([str((who as Node).get_path()) if who is Node else str(who), from.distance_to(hit["position"]), who])
	return out

func _vec(report: String, key: String) -> Vector3:
	var i := report.find(key + "=(")
	var j := report.find(")", i)
	var parts := report.substr(i + key.length() + 2, j - i - key.length() - 2).split(",")
	return Vector3(float(parts[0]), float(parts[1]), float(parts[2]))

## Re-trace the shot exactly as reported (origin, aim) and say what it met, and how close the scope line
## (the probe's own pre-press line) and the shot pass above the terrain collider on the way.
func _explain_shot(report: String, d: float, t: Node, line: Array) -> void:
	var o := _vec(report, "origin")
	var a := _vec(report, "aim").normalized()
	var hits := _line(o, o + a * (d + 30.0), p)
	for e in hits:
		print("      shot retrace: %s at %.3f m" % [(e[0] as String).replace("/root/DebugWorld/", ""), e[1]])
	var terrain: Node = world.find_child("Terrain3D", true, false)
	if terrain == null:
		return
	var data: Object = terrain.get("data")
	var worst := 1e9
	var worst_at := 0.0
	var s := 2.0
	while s < d - 3.0:
		var q := o + a * s
		var h: float = data.call("get_height", q)
		if not is_nan(h) and q.y - h < worst:
			worst = q.y - h
			worst_at = s
		s += 0.25
	print("      shot line clearance over Terrain3D height: min %.3f m at %.1f m" % [worst, worst_at])

## Perpendicular distance from `pt` to the ray (o, dir).
func _ray_gap(o: Vector3, dir: Vector3, pt: Vector3) -> float:
	var v := pt - o
	return (v - dir * v.dot(dir)).length()

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
	var ndirs := int(_arg("dirs", "16"))
	var max_targets := int(_arg("max", "5"))
	var origins := _arg("from", "player;-150,60;150,30;60,-120").split(";")
	var dists := []
	for s in _arg("dists", "100,175,250").split(","):
		dists.append(float(s))
	var live := _arg("live", "false") == "true"
	var repeat := int(_arg("repeat", "1"))
	var only := []
	for s2 in _arg("only-dirs", "").split(",", false):
		only.append(float(s2))
	var bones := _arg("bones", "head_2,spine_03,thigh_l").split(",")

	world = (load(WORLD) as PackedScene).instantiate() as Node3D
	root.add_child(world)
	current_scene = world
	p = world.get_node("Characters/Player") as CharacterBody3D
	await _tick(240)
	# Raise the max AND refill: setting max_health alone leaves the player at 100, and the zone AI shot it dead
	# mid-run, after which every "shot" read as NO SHOT with the view frozen (a probe artefact, not a hit bug).
	p.get_node("Health").set("max_health", 1.0e9)
	p.get_node("Health").call("heal", 1.0e9)  # heal is registered; reset_full is not

	gun = (load(SNR1) as PackedScene).instantiate() as Node3D
	# --control: the trace without the precise small-shape pass (WeaponItem.nearerSmallShape), i.e. one long
	# Jolt query, which steps over a thigh hitbox from ~230 m (util.RayWindows).
	gun.set("small_shape_windows", _arg("control", "false") != "true")
	world.add_child(gun)
	gun.global_position = p.global_position + Vector3(0, 0.3, 0)
	await _tick(40)
	var wc: Node = p.get_node("WeaponController")
	for slot in range(7):
		if String(gun.get_parent().name).begins_with("Socket"):
			break
		wc.call("on_set_weapon", slot)
		await _tick(40)
	print("SNR1 held: %s" % String(gun.get_parent().name).begins_with("Socket"))
	cam_ctrl = p.get_node("TPSCameraController")
	var stats := {"total": 0, "ok": 0, "blocked": 0, "occluded": 0, "wrong": 0, "true_miss": 0}
	for o in origins:
		if o != "player":
			var xz: PackedStringArray = o.split(",")
			var oy := _ground(float(xz[0]), float(xz[1]))
			if is_nan(oy) or oy < 0.3:
				print("\n=== origin %s: no land" % o)
				continue
			p.global_position = Vector3(float(xz[0]), oy + 1.0, float(xz[1]))
			p.velocity = Vector3.ZERO
			await _tick(90)
		print("\n=== origin %s at %s on_floor %s" % [o, p.global_position, p.is_on_floor()])
		for r in range(repeat):
			await _shoot_from(p.global_position, ndirs, dists, max_targets, live, wc, stats, only, bones)
	print("\nSUMMARY %d / %d shots on the aimed bone, %d occluded by a drawn collider first on the scope line, %d TRUE misses (the target first on the line, no damage), %d on the wrong bone; %d spots skipped (chest not visible)" % [
		stats["ok"], stats["total"], stats["occluded"], stats["true_miss"], stats["wrong"], stats["blocked"]])
	var clean: bool = stats["true_miss"] == 0 and stats["wrong"] == 0 and stats["ok"] > 0
	print("PASS" if clean else "FAIL")
	quit(0 if clean else 1)

func _shoot_from(origin: Vector3, ndirs: int, dists: Array, max_targets: int, live: bool, wc: Node, stats: Dictionary, only: Array, bones: PackedStringArray) -> void:
	var shot_here := 0
	for di in range(ndirs):
		var ang := TAU * di / ndirs
		if not only.is_empty() and not only.any(func(o): return absf(o - rad_to_deg(ang)) < 0.6):
			continue
		for d in dists:
			if shot_here >= max_targets:
				return
			var x: float = origin.x + sin(ang) * d
			var z: float = origin.z - cos(ang) * d
			var gy := _ground(x, z)
			if is_nan(gy) or gy < 0.3:
				continue
			# cheap pre-check before spawning a body: eye to a chest-high point
			var eye0 := origin + Vector3(0, 1.4, 0)
			var pre := _line(eye0, Vector3(x, gy + 1.3, z), p)
			if pre.size() > 0:
				stats["blocked"] += 1
				print("  dir %.0f deg %.0f m: blocked by %s at %.1f m (drawn %s)" % [rad_to_deg(ang), d, pre[0][0].replace("/root/DebugWorld/", ""), pre[0][1], _has_visual(pre[0][2] as Node)])
				continue
			shot_here += 1
			var t: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
			var h: Node = t.get_node("Health")
			h.set("max_health", 1.0e9)
			world.get_node("Characters").add_child(t)
			t.global_position = Vector3(x, gy + 0.1, z)
			t.look_at(Vector3(origin.x, gy + 0.1, origin.z), Vector3.UP, true)
			var info: Resource = t.get("character_info")
			if info != null:
				info.set("faction", "neutral")
			if not live:
				var mc: Node = t.get_node_or_null("MovementController")
				if mc != null:
					mc.set_physics_process(false)
			var hits: Array = []
			h.connect("hit", func(dmg): hits.append(dmg))
			var skel: Skeleton3D = _find(t, "Skeleton3D") as Skeleton3D
			var pairs := {}
			for bone in ["head_2", "spine_03", "thigh_l"]:
				var att := BoneAttachment3D.new()
				att.bone_name = bone
				skel.add_child(att)
				pairs[bone] = [att, _find(t, "Physical Bone " + bone) as PhysicalBone3D]
			await _tick(90)
			Input.action_press("aim")
			await _tick(30)
			print("\n--- dir %.0f deg %.0f m: target on ground %.2f, LOD %s" % [rad_to_deg(ang), d, gy, t.call("lod_level_now")])
			var dmg := {"head_2": 600.0, "spine_03": 150.0, "thigh_l": 75.0}
			for bone in bones:
				var target := [bone, dmg[bone]]
				var att: BoneAttachment3D = pairs[target[0]][0]
				var hb: PhysicalBone3D = pairs[target[0]][1]
				var aim_at := func() -> Vector3:
					return _drawn(att, hb)
				# `target v` is the body's STORED velocity (each hit adds 7.5 m/s and nothing with movement off clears
				# it); the body does not move, which `drift` shows (0.00 m over every shot, 2026-09-17).
				var pos0: Vector3 = t.global_position
				var err: float = await _steer_to(aim_at, 90)
				await _tick(20)
				var cam := _cam()
				var fwd := -cam.global_transform.basis.z
				var line := _line(cam.global_position, cam.global_position + fwd * (d + 30.0), p)
				var first: String = "%s @%.1f" % [line[0][0].replace("/root/DebugWorld/", ""), line[0][1]] if line.size() > 0 else "nothing"
				var t_vel: float = (t as CharacterBody3D).velocity.length()
				var speed := p.velocity.length()
				var floor := p.is_on_floor()
				var spread: float = float(wc.call("spread_now_deg"))
				var n0 := hits.size()
				gun.set("magazine", 5)
				var mag0 := int(gun.get("magazine"))
				var mon := int(_arg("monitor", "0"))
				if mon > 0:
					var miss_frames := []
					var worst_srv := 0.0
					for f in range(mon):
						await physics_frame
						var c0 := _cam()
						var aim_pt: Vector3 = _drawn(att, hb)
						var dir := (aim_pt - c0.global_position).normalized()
						var rq := PhysicsRayQueryParameters3D.create(c0.global_position, aim_pt + dir * 2.0, AIM_MASK, [p.get_rid()])
						var hh := _space().intersect_ray(rq)
						var srv: Transform3D = PhysicsServer3D.body_get_state(hb.get_rid(), PhysicsServer3D.BODY_STATE_TRANSFORM)
						var dsrv: float = srv.origin.distance_to(hb.global_position)
						worst_srv = maxf(worst_srv, dsrv)
						if hh.is_empty() or hh["collider"] != hb:
							miss_frames.append("%d:%s(srv %.2f m)" % [f, (hh["collider"] as Node).name if not hh.is_empty() else "none", dsrv])
					print("      monitor %d frames: ray to drawn thigh misses the hitbox on %d %s; worst server-vs-node %.3f m" % [
						mon, miss_frames.size(), str(miss_frames.slice(0, 12)), worst_srv])
				var hb_off0: float = hb.global_position.distance_to(_drawn(att, hb))
				var miss0: float = _ray_gap(cam.global_position, fwd, hb.global_position)
				Input.action_press("fire")
				await _tick(1)
				var hb_off1: float = hb.global_position.distance_to(_drawn(att, hb))
				var miss1: float = _ray_gap(_cam().global_position, -_cam().global_transform.basis.z, hb.global_position)
				await _tick(1)
				Input.action_release("fire")
				await _tick(6)
				var report: String = str(gun.call("last_shot_report"))
				var drift: float = t.global_position.distance_to(pos0)
				var got: Array = hits.slice(n0)
				var fired := int(gun.get("magazine")) < mag0
				var verdict := "MISS" if fired else "NO SHOT"
				var occluder: bool = line.size() > 0 and not _owned_by(line[0][2], t)
				if got.size() == 1 and absf(float(got[0]) - float(target[1])) < 0.01:
					verdict = "ok"
					stats["ok"] += 1
				elif not got.is_empty():
					verdict = "WRONG %s" % str(got)
					stats["wrong"] += 1
				elif fired and occluder:
					verdict = "OCCLUDED"
					stats["occluded"] += 1
				else:
					stats["true_miss"] += 1
				stats["total"] += 1
				print("  %-9s err %.4f  speed %.3f floor %s  spread %.4f  target v %.2f drift %.2f m  first: %s -> %s" % [
					target[0], err, speed, floor, spread, t_vel, drift, first, verdict])
				if verdict != "ok" or _arg("verbose", "false") == "true":
					print("      hitbox-vs-drawn %.3f m -> %.3f m; scope line to hitbox centre %.3f m -> %.3f m; shot %s" % [
						hb_off0, hb_off1, miss0, miss1, report])
				if verdict != "ok":
					_explain_shot(report, d, t, line)
				if verdict != "ok":
					for e in line:
						print("      line: %s at %.2f m (drawn %s)" % [e[0], e[1], _has_visual(e[2] as Node)])
				await _tick(95)
			var late := hits.size()
			await _tick(120)
			if hits.size() != late:
				print("  LATE HITS after the last shot: %s" % str(hits.slice(late)))
			Input.action_release("aim")
			t.queue_free()
			await _tick(20)
