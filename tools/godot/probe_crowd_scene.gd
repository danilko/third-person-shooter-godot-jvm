extends SceneTree
## probe_crowd_scene.gd (diagnosis) -- shooting a LIGHT crowd ped lands like shooting an AI (user, 2026-10-06: "shooting into a
## crowd, even a shotgun or a powerful handgun after 3-4 shots cannot knock one down, while it works on an AI").
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_crowd_hits.gd
##
## World.tscn with the real ZoneManager; one probe zone of light peds frozen in place (speed 0, no reactions, no
## proximity promotion), so the only thing that turns a ped into a body is the shot. A real Player fires through
## Input with the view steered onto the drawn ped:
##   1. REV1 at a light ped's HEAD: the ped is promoted and dies to that one shot (70 x 4 head) -- before the fix the
##      promoting shot landed on the capsule at x1 and left it on 30 hp;
##   2. REV1 at another ped's CHEST: promoted, 70 x 1.0 on spine_03, alive (the multiplier is the torso's, not a kill);
##   3. SHG1, ONE pull at a ped 7 m off: more than one pellet lands on the promoted body -- before the fix only the
##      first pellet counted (the ped was gone before the other seven looked for it).

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const ZONE_JAVA := "res://src/main/java/com/openworld/world/Zone.java"
const MARKER_JAVA := "res://src/main/java/com/openworld/world/ZoneMarker.java"
const SPAWN_JAVA := "res://src/main/java/com/openworld/world/SpawnConfig.java"
## Downtown, where `tools/island_buildings.py` derived footways: the crowd needs a sidewalk to stand on.
const AT := Vector3(560, 0.75, -350)
## Far enough that nothing promotes (the crowd's 80 m), near enough that the zone still STREAMS (its 900 m
## load radius): a player who leaves the load radius unloads the zone, which would test nothing.
const FAR := Vector3(560, 0.75, -50)

var w: Node
var player: Node3D
var args := {}


func _arg(k: String, d = null):
	return args.get(k, d)


func check(ok: bool, what: String) -> void:
	if not ok: fails += 1
	print("%s %s" % ["PASS" if ok else "FAIL", what])


func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=")
		args[kv[0]] = kv[1] if kv.size() > 1 else true
	_run.call_deferred()


func _zm() -> Node:
	return root.get_node_or_null("/root/ZoneManager")


func _crowds() -> Array:
	var out := []
	_collect(w, "PedCrowd.java", out)
	return out


func _collect(n: Node, ends: String, out: Array) -> void:
	var s = n.get_script()
	if s != null and str(s.resource_path).ends_with(ends):
		out.append(n)
	for c in n.get_children():
		_collect(c, ends, out)


func _ped_total() -> int:
	var n := 0
	for c in _crowds():
		n += int(c.call("ped_count"))
	return n


func _walkers() -> Array:
	# Every full body driven by the sidewalk brain: the promoted tier.
	var out := []
	for n in get_nodes_in_group("characters"):
		if not (n is CharacterBody3D):
			continue
		for c in n.get_children():
			var s = c.get_script()
			if s != null and str(s.resource_path).ends_with("SidewalkWalkerController.java"):
				out.append(n)
				break
	return out


func _put_player(at: Vector3) -> void:
	# never under the terrain (user, 2026-10-04): the typed heights predate the 5.6 m plain
	var wb := current_scene.find_child("WorldBounds", true, false) if current_scene else null
	if wb != null:
		var h: float = wb.call("terrain_height", at.x, at.z)
		if not is_nan(h):
			at.y = maxf(at.y, h + 0.5)
	player.global_position = at


func _wait(seconds: float) -> void:
	var t := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t < int(seconds * 1000.0):
		await process_frame


func _make_zone(id: String, at: Vector3, count: int) -> Node3D:
	var z: Resource = load(ZONE_JAVA).new()
	z.set("zone_id", id)
	z.set("size", Vector3(360, 20, 360))
	z.set("load_radius", 900.0)
	z.set("unload_radius", 1400.0)
	var sc: Resource = load(SPAWN_JAVA).new()
	sc.set("count", count)
	sc.set("behavior", "sidewalk")
	sc.set("faction", "neutral")
	sc.set("weapon_scene_path", "")
	z.get("spawn_configs").append(sc)
	var m: Node3D = load(MARKER_JAVA).new()
	m.set("zone", z)
	m.set("show_debug_volume", false)
	w.add_child(m)
	m.global_position = at
	return m


const SENS := 0.07
var cam_ctrl: Node

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _steer_to(target, frames: int) -> void:
	for i in range(frames):
		if target is Callable:
			target = target
		var cam := player.get_node("ActiveCamera") as Node3D
		var tgt: Vector3 = target.call() if target is Callable else target
		var to: Vector3 = tgt - cam.global_position
		var f := -cam.global_transform.basis.z
		var dy := wrapf(rad_to_deg(atan2(-to.x, -to.z)) - rad_to_deg(atan2(-f.x, -f.z)), -180.0, 180.0)
		var dp := rad_to_deg(atan2(to.y, Vector2(to.x, to.z).length())) - rad_to_deg(asin(clampf(f.y, -1.0, 1.0)))
		if absf(dy) + absf(dp) < 0.003 and not (target is Callable):
			return
		var ev := InputEventMouseMotion.new()
		ev.relative = Vector2(-dy / SENS, -dp / SENS)
		cam_ctrl.call("_input", ev)
		await physics_frame

func _arm(id: String) -> Node3D:
	var gun: Node3D = (load("res://src/main/resources/com/openworld/weapon/%s.tscn" % id) as PackedScene).instantiate() as Node3D
	w.add_child(gun)
	gun.global_position = player.global_position + Vector3(0, 0.3, 0)
	await _tick(30)
	var wc: Node = player.get_node("WeaponController")
	for slot in range(7):
		if String(gun.get_parent().name).begins_with("Socket"):
			break
		wc.call("on_set_weapon", slot)
		await _tick(40)
	return gun

func _chest_of(body: Node3D) -> Vector3:
	var pb := body.find_child("Physical Bone spine_03", true, false) as Node3D
	return pb.global_position if pb != null else body.global_position + Vector3(0, 1.2, 0)

var fails := 0

func _all_peds() -> Array:
	var out := []
	for c in _crowds():
		for v in c.call("ped_positions_now"):
			out.append(v)
	return out

## Stand at one light ped's spot and return another ped lo..hi m off it with a clear line (INF if none).
func _stand_and_pick(lo: float, hi: float, h: float) -> Vector3:
	var ps := _all_peds()
	for a in ps:
		for b in ps:
			var d := (a as Vector3).distance_to(b)
			if d < lo or d > hi:
				continue
			var q := PhysicsRayQueryParameters3D.create((a as Vector3) + Vector3(0, 1.7, 0), (b as Vector3) + Vector3(0, h, 0), 1)
			if player.get_world_3d().direct_space_state.intersect_ray(q).is_empty():
				_put_player((a as Vector3) + Vector3(0, 1.0, 0))
				await _wait(1.0)
				return b
	return Vector3.INF

## The height of the light ped standing at `at` (its hit cylinder's), or 1.6.
func _height_at(at: Vector3) -> float:
	for c in _crowds():
		var ps: PackedVector3Array = c.call("ped_positions_now")
		var hs: PackedFloat32Array = c.call("ped_heights_now")
		for i in range(ps.size()):
			if ps[i].distance_to(at) < 0.05: return hs[i]
	return 1.6

## The nearest light ped between lo and hi metres with a clear line from the camera to `h` above its feet.
func _pick(lo: float, hi: float, h: float) -> Vector3:
	var cam := player.get_node("ActiveCamera") as Node3D
	var best := Vector3.INF
	var bd := 1e9
	for v in _all_peds():
		var d := (v as Vector3).distance_to(player.global_position)
		if d < lo or d > hi or d >= bd:
			continue
		var q := PhysicsRayQueryParameters3D.create(cam.global_position, (v as Vector3) + Vector3(0, h, 0), 1)
		q.exclude = [player.get_rid()]
		if player.get_world_3d().direct_space_state.intersect_ray(q).is_empty():
			bd = d; best = v
	return best

## Fire one pull at `ped` + h; returns [the new body nearest the ped (or null), its health after].
func _shoot(gun: Node3D, ped: Vector3, h: float) -> Array:
	await _steer_to(ped + Vector3(0, h, 0), 90)
	var before := get_nodes_in_group("characters").duplicate()
	gun.set("magazine", 6)
	Input.action_press("fire")
	await _tick(2)
	Input.action_release("fire")
	await _tick(8)
	var body: Node3D = null
	var bd := 3.0
	for n in get_nodes_in_group("characters"):
		if n is CharacterBody3D and not before.has(n) and (n as Node3D).global_position.distance_to(ped) < bd:
			bd = (n as Node3D).global_position.distance_to(ped); body = n
	var hp := -1.0
	if body != null:
		hp = float(body.get_node("Health").call("health_now"))
	print("   %s at %.1f m: %s, body %s hp %.0f" % [gun.name, ped.distance_to(player.global_position),
		str(gun.call("last_shot_report")).substr(0, str(gun.call("last_shot_report")).find(" origin")), body.name if body else "-", hp])
	return [body, hp]

func _walker_ctrl(n: Node) -> Node:
	for c in n.get_children():
		var sc = c.get_script()
		if sc != null and str(sc.resource_path).ends_with("SidewalkWalkerController.java"):
			return c
	return null

func _run() -> void:
	w = (load(WORLD) as PackedScene).instantiate()
	root.add_child(w)
	current_scene = w
	await process_frame
	_zm().set("debug_log", false)
	player = w.get_node_or_null("Characters/Player")
	player.get_node("Health").set("invulnerable", true)
	cam_ctrl = player.get_node("TPSCameraController")
	_put_player(AT)
	await _wait(12.0)
	var ps := _all_peds()
	_put_player(ps[int(_arg("pick", 0)) % ps.size()] + Vector3(0, 1.0, 0))
	await _wait(6.0)
	var gun := await _arm("REV1")
	var walkers := []
	for n in get_nodes_in_group("characters"):
		if n is CharacterBody3D and n != player and _walker_ctrl(n) != null:
			walkers.append(n)
	print("light %d, promoted walkers %d" % [_all_peds().size(), walkers.size()])
	for n in walkers:
		print("  walker %s at %.1f m ctrl=%s" % [n.name, (n as Node3D).global_position.distance_to(player.global_position),
			str(_walker_ctrl(n).get("flee"))])
	Input.action_press("aim")
	await _tick(30)
	var hits := 0
	for k in range(int(_arg("shots", 4))):
		var tgt: Node3D = null
		var bd := 1e9
		for n in walkers:
			if is_instance_valid(n) and float(n.get_node("Health").call("health_now")) > 0.0:
				var d := (n as Node3D).global_position.distance_to(player.global_position)
				if d > float(_arg("min", 3.0)) and d < float(_arg("max", 1000.0)) and d < bd: bd = d; tgt = n
		if tgt == null: break
		if _arg("close", "") != "":
			var cl := float(_arg("close"))
			var away := (player.global_position - tgt.global_position)
			away.y = 0
			_put_player(tgt.global_position + away.normalized() * cl + Vector3(0, 1.0, 0))
			await _tick(5)
			bd = tgt.global_position.distance_to(player.global_position)
		await _steer_to(_chest_of(tgt), 60)
		var ray: RayCast3D = player.get_node("ActiveCamera/AimRay")
		ray.force_raycast_update()
		var aimon := str(ray.get_collider().get_path()) if ray.is_colliding() else "nothing"
		var hp0 := float(tgt.get_node("Health").call("health_now"))
		var sc0 := 0
		for c in _crowds(): sc0 += int(c.call("scares_now"))
		gun.set("magazine", 6)
		var wc: Node = player.get_node("WeaponController")
		print("   before: socket %s state %s mag %d" % [gun.get_parent().name, str(wc.call("weapon_state_now")), int(gun.get("magazine"))])
		var hpall := {}
		for n in get_nodes_in_group("characters"):
			if n.get_node_or_null("Health") != null: hpall[n] = float(n.get_node("Health").call("health_now"))
		Input.action_press("fire")
		await _tick(2)
		Input.action_release("fire")
		await _tick(30)
		for n in hpall:
			if is_instance_valid(n) and float(n.get_node("Health").call("health_now")) != hpall[n]:
				print("   DAMAGED %s %.0f -> %.0f" % [n.name, hpall[n], float(n.get_node("Health").call("health_now"))])
		var rp := str(gun.call("last_shot_report"))
		if rp.contains("Physical Bone"):
			var oi := rp.find("origin=(") + 8
			var oo := rp.substr(oi, rp.find(")", oi) - oi).split(",")
			var org := Vector3(float(oo[0]), float(oo[1]), float(oo[2]))
			var ei := rp.find("ends=(") + 6
			var ee := rp.substr(ei, rp.find(")", ei) - ei).split(",")
			var en := Vector3(float(ee[0]), float(ee[1]), float(ee[2]))
			var q := PhysicsRayQueryParameters3D.create(org, en + (en - org).normalized() * 0.3, 8)
			var r := player.get_world_3d().direct_space_state.intersect_ray(q)
			if not r.is_empty():
				var o: Node = r.collider
				while o != null and not (o is CharacterBody3D): o = o.get_parent()
				var h = o.get_node_or_null("Health") if o else null
				print("   BONE OWNER %s groups %s hp %s dead %s ctrl %s script %s" % [o.get_path() if o else "?", str(o.get_groups()) if o else "",
					str(h.call("health_now")) if h else "-", str(o.get("is_dead")) if o else "", str(_walker_ctrl(o) != null) if o else "",
					str(o.get_script().resource_path) if o and o.get_script() else ""])
		var hpn = tgt.get_node("Health")
		print("   target health node: inv %s max %s" % [str(hpn.get("invulnerable")), str(hpn.get("max_health"))])
		print("   fire state: cam fwd vs gun %s" % str(gun.call("last_shot_report")).length())
		print("   after: mag %d state %s" % [int(gun.get("magazine")), str(wc.call("weapon_state_now"))])
		var sc1 := 0
		for c in _crowds(): sc1 += int(c.call("scares_now"))
		var hp1 := float(tgt.get_node("Health").call("health_now")) if is_instance_valid(tgt) else -1.0
		var rep := str(gun.call("last_shot_report"))
		var cam := player.get_node("ActiveCamera") as Node3D
		var muz := player.find_child("Muzzle", true, false) as Node3D
		print("   cam %s  tgt chest %s  aimpoint %s" % [cam.global_position, _chest_of(tgt), ray.get_collision_point() if ray.is_colliding() else Vector3.ZERO])
		print("shot %d at %s %.1f m: hp %.0f -> %.0f | aim ray on %s | %s | light scares +%d" % [k, tgt.name, bd, hp0, hp1, aimon,
			rep.substr(0, rep.find(" origin")) + " ends " + rep.substr(rep.find("ends="), 80) + " tgt@" + str(_chest_of(tgt)), sc1 - sc0])
		for n in walkers:
			if is_instance_valid(n):
				var c = _walker_ctrl(n)
				if c != null: print("    %s flee %s vel %.1f" % [n.name, str(c.get("flee")), (n as CharacterBody3D).velocity.length()])
		if hp1 < hp0: hits += 1
		await _tick(30)
	print("RESULT %d of shots damaged" % hits)
	quit(0)
