extends SceneTree
## HOW MANY CARS ARE ROUND THE PLAYER, BY DISTRICT (user, 2026-10-10: "barely more than 3 cars even in the busy city /
## suburb, residential barely any, the west centre the most crowded"). World.tscn with the real ZoneManager: the
## player is stood at each site in turn, the streamer is given time to go quiet, then the ambient cars are counted
## every 2 s for --seconds (default 40).
##   stdbuf -oL <godot> --headless --fixed-fps 60 --path . --script tools/godot/probe_traffic_census.gd -- \
##       [--seconds=40] [--sites=downtown_core,farm] [--budget=N] [--near-target=N] [--along-lanes | --along-share=0.5] [--on-road] [--no-grid-at-spawn]
##       [--at=trunk:15:420,street:-958:657] [--big-road-bias=0]
## --at adds sites by hand (name:x:z, Godot frame) and implies --on-road for them: each is moved to the nearest
## street and ALSO reports the cars ON THE PLAYER'S OWN ROAD within 150 m (the user, 2026-10-12: "on a big road I
## barely see any") -- a car counts when its lane's name starts with the road's (`chuo_dori__3_F1` -> `chuo_dori`).
## --big-road-bias=0 is that measurement's control (ZoneManager.trafficBigRoadBias: the uniform lane draw).
## --drive=<m/s> [--drive-metres=1500]: after the standing sample at an --at site the player is CARRIED along that
## road's lanes at that speed (30 m above them, the velocity set, so the spawn rules see a moving player and no car
## brakes for a person), straight on at each junction, and the own-road count is taken again every 2 s -- the user's
## words were "in current driving", and a standing census cannot see what the corridor and view rules refuse.
## A MEASUREMENT (it prints a table and exits 0); --min-near=<n> turns it into a gate: every site's mean count of
## simulated cars within 200 m must reach n.
const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
## name, Godot x, z -- the centre of the region's box in tools/island_buildings.REGIONS (z = -y)
const SITES := [
	["downtown_core", 760.0, -70.0], ["nightlife", 750.0, -370.0], ["akiba", 1080.0, -250.0],
	["residential_north", 685.0, -810.0], ["residential_west", -525.0, -100.0], ["residential", -975.0, 680.0],
	["suburb", 1085.0, 665.0], ["west_centre", -675.0, 540.0], ["industry", -400.0, 820.0],
	["harbour", -285.0, 1300.0], ["farm", 1100.0, -1410.0],
]
var args := {}

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=")
		args[kv[0]] = kv[1] if kv.size() > 1 else true
	_run.call_deferred()

func _cars(p: Vector3, r: float) -> Array:
	var out := []
	for n in get_nodes_in_group("characters"):
		if n is RigidBody3D and is_instance_valid(n):
			var d: Vector3 = n.global_position - p
			d.y = 0
			if d.length() <= r:
				out.append(n)
	return out

## The point of the through lane nearest `p` in plan (a street the player would stand on), or `p` when none
## within 300 m. --on-road: a box centre is often the inside of a block, where no car can ever be within 60 m.
func _on_road(p: Vector3) -> Vector3:
	var best := p
	var best_d := 300.0
	for n in root.find_children("*", "Node3D", true, false):
		var sc: Script = n.get_script()
		if sc == null or not str(sc.resource_path).ends_with("PathLaneRoute.java") or str(n.name).begins_with("c"):
			continue
		var path: Path3D = n.get_node_or_null("Path3D")
		if path == null or path.curve == null or path.curve.get_baked_length() < 60.0:
			continue
		var off := path.curve.get_closest_offset(path.to_local(p))
		if not is_finite(off):
			continue
		var at := path.to_global(path.curve.sample_baked(off))
		var d := Vector2(at.x - p.x, at.z - p.z).length()
		if d < best_d:
			best_d = d
			best = Vector3(at.x, p.y, at.z)
	return best

## The through lane nearest `p`: its node name and speed limit (km/h), or ["", 0.0].
func _lane_at(p: Vector3) -> Array:
	var best := ["", 0.0]
	var best_d := 60.0
	for n in root.find_children("*", "Node3D", true, false):
		var sc: Script = n.get_script()
		if sc == null or not str(sc.resource_path).ends_with("PathLaneRoute.java") or str(n.name).begins_with("c"):
			continue
		var path: Path3D = n.get_node_or_null("Path3D")
		if path == null or path.curve == null:
			continue
		var off := path.curve.get_closest_offset(path.to_local(p))
		if not is_finite(off):
			continue
		var at := path.to_global(path.curve.sample_baked(off))
		var d := Vector2(at.x - p.x, at.z - p.z).length()
		if d < best_d:
			best_d = d
			best = [str(n.name), float(n.get("speed_limit"))]
	return best

## The lane node called `name` (a PathLaneRoute currently in the tree), or null.
func _lane_node(name: String) -> Node3D:
	for n in root.find_children(name, "Node3D", true, false):
		var sc: Script = n.get_script()
		if sc != null and str(sc.resource_path).ends_with("PathLaneRoute.java"):
			return n
	return null

## Carry the player `metres` along `lane` and its straightest successors at `speed`; returns [mean cars on `road`
## within 150 m, mean of those AHEAD of the player, samples, metres actually covered].
var _drive_cam: Camera3D = null
var _way_near := [0.0, 0.0]   # cars ahead within 150 m heading [the player's way, against], summed over the samples
var _way_far := [0.0, 0.0]    # the same out to 400 m

func _drive(p: CharacterBody3D, lane: String, road: String, speed: float, metres: float) -> Array:
	_way_near = [0.0, 0.0]
	_way_far = [0.0, 0.0]
	var node := _lane_node(lane)
	var done := 0.0
	var own := 0.0
	var ahead := 0.0
	var any_ahead := 0.0      # any ambient car within 150 m ahead and 25 m either side of the line of travel
	var faced := 0.0          # how squarely this peer's camera looked along the travel (1 = dead ahead)
	var n := 0
	var frame := 0
	var s := -1.0
	while node != null and done < metres:
		var path: Path3D = node.get_node_or_null("Path3D")
		if path == null or path.curve == null:
			break
		var total := path.curve.get_baked_length()
		if s < 0.0:
			s = path.curve.get_closest_offset(path.to_local(p.global_position))
		var dir := Vector3.FORWARD
		while s < total and done < metres:
			var at := path.to_global(path.curve.sample_baked(s))
			var nxt := path.to_global(path.curve.sample_baked(minf(total, s + 1.0)))
			if nxt.distance_to(at) > 0.01:
				dir = (nxt - at).normalized()
			p.global_position = at + Vector3(0, 30.0, 0)
			p.velocity = dir * speed
			# a driver looks where they are going, and "never born in view within 160 m" is asked of this camera
			# (the probe's OWN camera, made current every frame: the player's rig rewrites its own and read -0.7)
			if _drive_cam == null:
				_drive_cam = Camera3D.new()
				_drive_cam.far = 1200.0
				root.add_child(_drive_cam)
			_drive_cam.global_transform = Transform3D(Basis.looking_at(dir, Vector3.UP), at + Vector3(0, 2.0, 0))
			_drive_cam.make_current()
			await physics_frame
			s += speed / 60.0
			done += speed / 60.0
			frame += 1
			if frame % 120 == 0:
				n += 1
				var cam2 := root.get_viewport().get_camera_3d()
				if cam2 != null:
					faced += (-cam2.global_transform.basis.z).dot(dir)
				for c in _cars(p.global_position, 400.0):
					var ai := false
					var lane_now := ""
					for ch in c.get_children():
						var sc: Script = ch.get_script()
						if sc != null and str(sc.resource_path).ends_with("VehicleAIController.java"):
							ai = true
							lane_now = str(ch.call("lane_now"))
					if not ai:
						continue
					var rel: Vector3 = c.global_position - p.global_position
					var along := rel.x * dir.x + rel.z * dir.z
					var near := Vector2(rel.x, rel.z).length() <= 150.0
					if along > 0.0 and absf(rel.x * dir.z - rel.z * dir.x) < 25.0 + 0.1 * along:
						var h: float = (-c.global_transform.basis.z).dot(dir)
						var k := 0 if h > 0.6 else (1 if h < -0.6 else -1)
						if k >= 0:
							_way_far[k] += 1
							if near:
								_way_near[k] += 1
						if near:
							any_ahead += 1
					if near and _road_of(lane_now) == road:
						own += 1
						if along > 0.0:
							ahead += 1
		# straight on: of the lanes this one names, the one whose first metre runs most nearly the way this ended
		var end_a := path.to_global(path.curve.sample_baked(maxf(0.0, total - 1.0)))
		var end_b := path.to_global(path.curve.sample_baked(total))
		var out := (end_b - end_a).normalized()
		var best: Node3D = null
		var best_dot := -2.0
		for nm in str(node.get("next_routes")).split(",", false):
			var cand := _lane_node(nm.strip_edges())
			if cand == null:
				continue
			var cp: Path3D = cand.get_node_or_null("Path3D")
			if cp == null or cp.curve == null or cp.curve.get_baked_length() < 1.0:
				continue
			var d0 := (cp.to_global(cp.curve.sample_baked(1.0)) - cp.to_global(cp.curve.sample_baked(0.0))).normalized()
			if d0.dot(out) > best_dot:
				best_dot = d0.dot(out)
				best = cand
		node = best
		s = 0.0
	p.velocity = Vector3.ZERO
	return [own / maxf(n, 1), ahead / maxf(n, 1), n, done, any_ahead / maxf(n, 1), faced / maxf(n, 1)]

## `chuo_dori__3_F1` -> `chuo_dori`: a road cut into several records keeps one name before the first `__`.
func _road_of(lane: String) -> String:
	var cut := lane.rfind("_")
	var road := lane.substr(0, cut) if cut > 0 else lane
	var split := road.find("__")
	return road.substr(0, split) if split > 0 else road

## How many ambient cars within `r` of `p` drive a lane of `road`.
func _on_own_road(p: Vector3, r: float, road: String) -> int:
	var n := 0
	for c in _cars(p, r):
		for ch in c.get_children():
			var sc: Script = ch.get_script()
			if sc != null and str(sc.resource_path).ends_with("VehicleAIController.java"):
				if _road_of(str(ch.call("lane_now"))) == road:
					n += 1
	return n

func _run() -> void:
	var w: Node = (load(WORLD) as PackedScene).instantiate()
	root.add_child(w)
	current_scene = w
	await process_frame
	var zm := root.get_node("/root/ZoneManager")
	zm.set("debug_log", false)
	if args.has("budget"):
		zm.set("traffic_budget", int(args["budget"]))
	if args.has("ring"):
		zm.set("traffic_sim_radius", float(args["ring"]))
	if args.has("idle"):
		zm.set("traffic_idle_recycle_seconds", float(args["idle"]))
	if args.has("recycle"):
		zm.set("traffic_recycle_dist", float(args["recycle"]))
	if args.has("near-radius"):
		zm.set("traffic_near_radius", float(args["near-radius"]))
	if args.has("near-target"):
		zm.set("traffic_near_target", int(args["near-target"]))
	# --fixed-fps game time is not wall time: the lights keep game time too (on the wall clock a 40 s sample sees a
	# few seconds of one phase, and a car at a red reads as standing for ever)
	var ts := root.find_child("TrafficSignals", true, false)
	if ts != null:
		ts.set("game_clock", true)
	if args.has("no-lazy-drivers"):
		zm.set("traffic_lazy_drivers", false)
	if args.has("no-cross-gap"):
		zm.set("traffic_gap_across_lanes", false)   # the control: an on-rails car joins a queue it cannot see
	if args.has("no-grid-at-spawn"):
		zm.set("traffic_grid_at_spawn", false)   # the control: a new car is at the world origin in the grid for 0.25 s
	if args.has("no-cap"):
		zm.set("traffic_speed_cap", false)   # V6's control: the brain fades its own throttle, the car has no limit
	if args.has("along-share"):
		zm.set("traffic_spawn_along_share", float(args["along-share"]))
	if args.has("along-lanes"):
		zm.set("traffic_spawn_along_lanes", true)
	if args.has("lead"):
		zm.set("traffic_lead_seconds", float(args["lead"]))    # 0 = the control: the ring stays on the player
	if args.has("balance-ways"):
		zm.set("traffic_balance_ways", int(args["balance-ways"]) != 0)   # 0 = the control: oncoming wins every draw
	if args.has("view-lead"):
		zm.set("traffic_spawn_view_lead", float(args["view-lead"]))      # 0 = the control: born in view from 160 m
	if args.has("big-road-bias"):
		zm.set("traffic_big_road_bias", float(args["big-road-bias"]))
	var sites := SITES.duplicate()
	var by_hand := {}
	for spec in str(args.get("at", "")).split(",", false):
		var f := spec.split(":")
		if f.size() == 3:
			sites.append([f[0], float(f[1]), float(f[2])])
			by_hand[f[0]] = true
	var car := w.get_node_or_null("VehicleRoot")
	if car != null:
		car.queue_free()
	var p := w.get_node("Characters/Player") as CharacterBody3D
	p.get_node("Health").set("max_health", 1000000.0)
	p.get_node("Health").set("invulnerable", true)
	p.set_physics_process(false)
	var seconds := float(args.get("seconds", "40"))
	var only: PackedStringArray = str(args.get("sites", "")).split(",", false)
	var min_near := float(args.get("min-near", "-1"))
	var fails := 0
	print("budget %d, near target %d within %.0f m, sim ring %.0f m" % [int(zm.get("traffic_budget")),
		int(zm.get("traffic_near_target")), float(zm.get("traffic_near_radius")), float(zm.get("traffic_sim_radius"))])
	print("%-18s %6s %6s %6s %6s %6s %6s  %s" % ["site", "<60m", "<100m", "<200m", "alive", "far", "refuse", "traffic models at the end"])
	for site in sites:
		if not only.is_empty() and not only.has(site[0]):
			continue
		if only.is_empty() and not by_hand.is_empty() and not by_hand.has(site[0]):
			continue      # --at alone: only the sites named by hand
		if not is_instance_valid(p):
			# the respawn system replaced the body (something killed it between sites): take the new one
			p = current_scene.get_node("Characters/Player") as CharacterBody3D
			p.get_node("Health").set("invulnerable", true)
			p.set_physics_process(false)
			print("    (the player body was replaced before %s: taken again)" % site[0])
		p.global_position = Vector3(site[1], 30.0, site[2])
		p.velocity = Vector3.ZERO
		var waited := 0
		while waited < 60 * 90:
			await physics_frame
			waited += 1
			if waited > 240 and int(zm.call("streaming_pending_now")) == 0:
				break
		var moved := 0.0
		var own_road := ""
		var own_lane := ""
		var own_limit := 0.0
		var own := 0.0
		if args.has("on-road") or by_hand.has(site[0]):
			var q := _on_road(p.global_position)
			moved = (q - p.global_position).length()
			p.global_position = q
			for i in 600:
				await physics_frame
			var la := _lane_at(p.global_position)
			own_lane = la[0]
			own_road = _road_of(la[0])
			own_limit = la[1]
		var refused0: int = zm.call("traffic_spawns_refused_now")
		var s60 := 0.0
		var s100 := 0.0
		var s200 := 0.0
		var alive := 0.0
		var far := 0.0
		var mov := 0.0
		var why := {}
		var n := 0
		var frames := int(seconds * 60.0)
		for f in range(frames):
			await physics_frame
			if f % 120 == 119:
				# ambient traffic only (ZoneManager's own cars): parked vehicles and police units are not traffic
				s60 += int(zm.call("traffic_near_now", 60.0))
				s100 += int(zm.call("traffic_near_now", 100.0))
				s200 += int(zm.call("traffic_near_now", 200.0))
				alive += int(zm.call("traffic_alive_now"))
				far += int(zm.call("far_traffic_cars_now"))
				# what the cars are DOING (an on-rails body's velocity reads zero: the brain is asked)
				mov += int(zm.call("traffic_moving_now", 200.0))
				if own_road != "":
					own += _on_own_road(p.global_position, 150.0, own_road)
				for kv in str(zm.call("traffic_state_now", 200.0)).split(" "):
					var e := kv.split("=")
					if e[0] != "n" and e[0] != "moving":
						why[e[0]] = int(why.get(e[0], 0)) + int(e[1])
				n += 1
		var models: String = str(zm.call("traffic_models_now")) if zm.has_method("traffic_models_now") else "?"
		var d: int = maxi(n, 1)
		print("%-18s %6.1f %6.1f %6.1f %6.1f %6.1f %6d  %s  (settled in %.0f s, region '%s')" % [site[0], s60 / d, s100 / d,
			s200 / d, alive / d, far / d, int(zm.call("traffic_spawns_refused_now")) - refused0, models, waited / 60.0,
			str(zm.call("traffic_region_now")) if zm.has_method("traffic_region_now") else "?"])
		print("    drivers: %s" % str(zm.call("traffic_drivers_now")))
		print("    safety: %s" % str(zm.call("traffic_safety_now")))
		if args.has("lanes"):
			# where each ambient car is at the end: its lane, its distance and height against the player
			for c in _cars(p.global_position, 400.0):
				for ch in c.get_children():
					var sc: Script = ch.get_script()
					if sc != null and str(sc.resource_path).ends_with("VehicleAIController.java"):
						print("      %-44s %5.0f m  y %6.1f  %s" % [ch.call("lane_now"),
							Vector2(c.global_position.x - p.global_position.x, c.global_position.z - p.global_position.z).length(),
							c.global_position.y, "rails" if ch.call("dummy_now") else "real"])
		var parts := []
		for k in why:
			parts.append("%s %.1f" % [k, float(why[k]) / d])
		print("    of the %.1f within 200 m: moving %.1f; %s%s" % [s200 / d, mov / d, ", ".join(parts),
			"  (stood on a street %.0f m from the site)" % moved if args.has("on-road") else ""])
		if own_road != "":
			print("    OWN ROAD '%s' (%.0f km/h): %.1f cars on it within 150 m" % [own_road, own_limit, own / d])
		if own_lane != "" and args.has("drive"):
			var r := await _drive(p, own_lane, own_road, float(args["drive"]), float(args.get("drive-metres", "1500")))
			print("    DRIVEN at %.0f m/s for %.0f m (%d samples): %.1f cars AHEAD within 150 m x 25 m (any road); on '%s' %.1f, %.1f of them ahead; camera along the travel %.2f" % [
				float(args["drive"]), r[3], r[2], r[4], own_road, r[0], r[1], r[5]])
			var nn := maxf(float(r[2]), 1.0)
			print("      ahead by heading, same way / oncoming: within 150 m %.1f / %.1f, within 400 m %.1f / %.1f; top-ups placed by the both-ways rule %d" % [
				_way_near[0] / nn, _way_near[1] / nn, _way_far[0] / nn, _way_far[1] / nn, int(zm.call("traffic_spawns_balanced_now"))])
		if min_near >= 0.0 and s200 / d < min_near:
			fails += 1
	if min_near >= 0.0:
		print("PASS" if fails == 0 else "RESULT FAIL (%d site(s) under %.1f cars within 200 m)" % [fails, min_near])
	quit(1 if fails > 0 else 0)
