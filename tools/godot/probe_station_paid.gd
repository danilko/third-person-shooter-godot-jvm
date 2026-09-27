extends SceneTree
## THE PAID AREA (PLAN.md P3, 2026-09-27): a station's platforms are reached ONLY through the ticket gates.
##   stdbuf -oL <godot> --headless --path . --script tools/godot/probe_station_paid.gd [-- --only=<Station>] [--control]
##
## For every open-air station of the rail reserve (IslandRailReserve.json; the hub is 3.36's), on the real World.tscn
## with the real ZoneManager: stream the station in, then FLOOD-FILL where a standing character can be -- a grid of
## 0.25 m cells, every walkable surface in each cell (so a stair, a platform and a footbridge deck over the bed are all
## nodes), a step of at most 0.4 m between neighbours, and a capsule that must fit standing at each node.
##   1. from the street in front of each station building, with the gate flaps SHUT, no platform is reached;
##   2. from the track bed past a platform end (a trespasser who walked in at a 踏切), no platform is reached;
##   3. with the flaps OPEN, the platform IS reached from the street -- the route through the gates exists.
## Every door that opens by itself (a shop's sliding entrance, the building's back door) is treated as open.
## `--control`: the flaps are opened for cases 1 and 2 too -- they must then fail.

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const RESERVE := "res://assets/world_source/buildings/IslandRailReserve.json"
const NET_Y := 0.6
const CELL := 0.25
const R := 0.2                  # the probing capsule (a character is 0.35; 0.2 finds every opening it could use)
const H := 1.6
const STEP := 0.4
const PLATFORM_W := {8.0: 3.0, 10.0: 4.0, 15.0: 5.0, 20.0: 5.0}
const EDGE := 3.55

var fails := 0
var zm: Node
var space: PhysicsDirectSpaceState3D
var shape: CapsuleShape3D
var levels := {}               # Vector2i -> PackedFloat32Array of surface heights

func check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-70s %s" % ["PASS" if ok else "FAIL", label, detail])

func _initialize() -> void:
	_run.call_deferred()

func _settle(seconds: float) -> void:
	for i in int(seconds * 60):
		await physics_frame
		if zm != null and int(zm.call("streaming_pending_now")) == 0 and i > 30:
			return

func _nodes_of(n: Node, pred: Callable, out: Array) -> void:
	if pred.call(n):
		out.append(n)
	for c in n.get_children():
		_nodes_of(c, pred, out)

func _surfaces(c: Vector2i, top: float, bottom: float) -> PackedFloat32Array:
	if levels.has(c):
		return levels[c]
	var out := PackedFloat32Array()
	# a cell's CENTRE is half a cell off the grid lines: station geometry is authored on a 0.05 m grid, so a ray on a
	# multiple of CELL stood exactly on a wall's face, grazed it down, and read the doorway as having no floor
	var x := (c.x + 0.5) * CELL
	var z := (c.y + 0.5) * CELL
	var from := top
	for k in 24:
		var q := PhysicsRayQueryParameters3D.create(Vector3(x, from, z), Vector3(x, bottom, z), 1)
		var h := space.intersect_ray(q)
		if h.is_empty():
			break
		var y: float = h["position"].y
		if (h["normal"] as Vector3).y > 0.6:
			out.append(y)
			from = y - 0.05
		else:
			from = y - 0.25          # a graze down a face or an underside: step past it
	levels[c] = out
	return out

func _fits(p: Vector3) -> bool:
	var q := PhysicsShapeQueryParameters3D.new()
	q.shape = shape
	q.collision_mask = 1
	# the capsule's foot one STEP up: a character steps up 0.35 m, so a stair's next riser (or a kerb) is not a wall.
	# Standing it 5 cm up made every 0.18 m riser on 0.30 m treads block the probe on a 0.25 m grid (a stair read
	# as impassable: the elevated stations' "unreachable even with the gates open" on the island, 2026-09-27)
	q.transform = Transform3D(Basis.IDENTITY, p + Vector3(0, STEP + H / 2.0 + R, 0))
	return space.intersect_shape(q, 1).is_empty()

## Breadth-first over (cell, level) from `start`; `is_goal(p)` ends it. Returns [reached goal, nodes visited].
func _flood(start: Vector3, lo: Vector2, hi: Vector2, top: float, bottom: float, is_goal: Callable) -> Array:
	var c0 := Vector2i(floori(start.x / CELL), floori(start.z / CELL))
	var s0 := _surfaces(c0, top, bottom)
	var best := -1
	for i in s0.size():
		if absf(s0[i] - start.y) < 1.0 and (best < 0 or absf(s0[i] - start.y) < absf(s0[best] - start.y)):
			best = i
	if best < 0:
		return [false, 0, "no floor at the start"]
	var seen := {}
	var queue: Array = [[c0, s0[best]]]
	seen[Vector3(c0.x, c0.y, snappedf(s0[best], 0.05))] = true
	var head := 0
	while head < queue.size():
		var cur: Array = queue[head]
		head += 1
		var cc: Vector2i = cur[0]
		var y: float = cur[1]
		var p := Vector3((cc.x + 0.5) * CELL, y, (cc.y + 0.5) * CELL)
		if is_goal.call(p):
			return [true, head, p]
		for d in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
			var nc: Vector2i = cc + d
			if (nc.x + 0.5) * CELL < lo.x or (nc.x + 0.5) * CELL > hi.x or (nc.y + 0.5) * CELL < lo.y \
					or (nc.y + 0.5) * CELL > hi.y:
				continue
			for ny in _surfaces(nc, top, bottom):
				if absf(ny - y) > STEP:
					continue
				var key := Vector3(nc.x, nc.y, snappedf(ny, 0.05))
				if seen.has(key):
					continue
				seen[key] = true
				if _fits(Vector3((nc.x + 0.5) * CELL, ny, (nc.y + 0.5) * CELL)):
					queue.append([nc, ny])
	return [false, head, null]

## STAND MODE (`--scene=<Station_X_Shop.tscn>`): one station scene on flat ground at the origin, nothing else -- the
## probe is debugged here before it is trusted on the island. Every point it needs (each platform's band, the street
## outside each entrance, the bed past each platform end) comes from the scene's own `building.station` meta, written
## by tools/station_layout.py, so the stand needs no copy of the station's geometry.
func _run_stand(path: String, control: bool) -> void:
	var w := Node3D.new()
	root.add_child(w)
	var ground := StaticBody3D.new()
	var gs := CollisionShape3D.new()
	var gb := BoxShape3D.new()
	gb.size = Vector3(400, 1, 400)
	gs.shape = gb
	gs.position = Vector3(0, -0.5, 0)
	ground.add_child(gs)
	w.add_child(ground)
	var sc: Node3D = (load(path) as PackedScene).instantiate()
	w.add_child(sc)
	await physics_frame
	await physics_frame
	space = w.get_world_3d().direct_space_state
	shape = CapsuleShape3D.new()
	shape.radius = R
	shape.height = H + 2.0 * R
	var meta: Dictionary = sc.get_meta("building")
	var st: Dictionary = meta["station"]
	var half := float(st["length"]) / 2.0
	var ptop := float(st["platform_top"])
	var bands: Array = st["platforms"]
	var flaps: Array = []
	var doors: Array = []
	_nodes_of(sc, func(n): return n is StaticBody3D and n.get("open_mode") != null, doors)
	for d in doors:
		if str(d.get_script().resource_path).ends_with("TicketGate.java"):
			flaps.append(d)
		elif bool(d.get("auto_open")) and not bool(d.get("locked")):
			(d as CollisionObject3D).collision_layer = 0
	check("%s: the scene has ticket-gate flaps" % st["name"], flaps.size() > 0, "%d" % flaps.size())
	# across: the station's own footprint (a ground hub's cap and annex reach ~40 m off the axis) plus the street
	var across := maxf(40.0, float(meta.get("footprint_m", [0, 0])[1]) / 2.0 + 15.0)
	var aabb := AABB(Vector3(-half - 40, -2, -across), Vector3(2 * half + 80, 20, 2 * across))
	var lo := Vector2(aabb.position.x, aabb.position.z)
	var hi := Vector2(aabb.end.x, aabb.end.z)
	var on_platform := func(p: Vector3) -> bool:
		if absf(p.x) > half - 5.0 or p.y < ptop - 0.3 or p.y > ptop + 0.5:
			return false
		for bd in bands:
			if p.z > float(bd[0]) + 0.2 and p.z < float(bd[1]) - 0.2:
				return true
		return false
	var starts: Array = []
	for e in st["entrances"]:
		starts.append(["the street outside an entrance", Vector3(e[0], 0.0, e[2])])
	for e in st["bed_points"]:
		starts.append(["the track bed past a platform end", Vector3(e[0], 0.0, e[2])])
	for f in flaps:
		(f as CollisionObject3D).collision_layer = 0 if control else 1
	for sp in starts:
		levels.clear()
		var r := _flood(sp[1], lo, hi, 12.0, -2.0, on_platform)
		check("%s: from %s %s, gates shut, no platform" % [st["name"], sp[0], str(sp[1])], not r[0],
			"visited %d%s" % [r[1], (", reached %s" % str(r[2])) if r[0] else ""])
	for f in flaps:
		(f as CollisionObject3D).collision_layer = 0
	for e in st["entrances"]:
		levels.clear()
		var r2 := _flood(Vector3(e[0], 0.0, e[2]), lo, hi, 12.0, -2.0, on_platform)
		check("%s: gates open, a platform is reached from %s" % [st["name"], str(e)], r2[0], "visited %d" % r2[1])
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)


## An OPEN-AIR station on the island (PLAN.md step 3): one scene placed by island_sites at the reserve's frame. Every
## point the judgement needs comes from that scene's own `building.station` meta (as in the stand), carried into the
## world by the placed scene's transform, so the probe holds no copy of the layout.
func _island_open_air(w: Node, player: Node3D, name: String, st: Dictionary, control: bool) -> void:
	var c := Vector3(float(st["x"]), float(st["bed"]) + NET_Y, -float(st["y"]))
	player.global_position = c + Vector3(0, 3.0, 0)
	await _settle(90.0)
	levels.clear()
	var found: Array = []
	var is_it := func(n: Node) -> bool:
		if not (n is Node3D and n.has_meta("building")):
			return false
		var m: Dictionary = n.get_meta("building")
		return m.has("station") and str(m["station"]["name"]) == name
	_nodes_of(w, is_it, found)
	check("%s: its station scene streamed in" % name, not found.is_empty(), "%d" % found.size())
	if found.is_empty():
		return
	var sc := found[0] as Node3D
	var xf := sc.global_transform
	var inv := xf.affine_inverse()
	var sm: Dictionary = sc.get_meta("building")["station"]
	var half := float(sm["length"]) / 2.0
	var ptop := float(sm["platform_top"])
	var bands: Array = sm["platforms"]
	var flaps: Array = []
	var doors: Array = []
	_nodes_of(sc, func(n): return n is StaticBody3D and n.get("open_mode") != null, doors)
	for d in doors:
		if str(d.get_script().resource_path).ends_with("TicketGate.java"):
			flaps.append(d)
		elif bool(d.get("auto_open")) and not bool(d.get("locked")):
			(d as CollisionObject3D).collision_layer = 0
	check("%s: the scene has ticket-gate flaps" % name, flaps.size() > 0, "%d" % flaps.size())
	var span := half + 40.0
	var lo := Vector2(INF, INF)
	var hi := Vector2(-INF, -INF)
	for sg in [Vector2(1, 1), Vector2(1, -1), Vector2(-1, 1), Vector2(-1, -1)]:
		var q := xf * Vector3(span * sg.x, 0, maxf(40.0, float(sc.get_meta("building").get("footprint_m", [0, 0])[1]) / 2.0 + 15.0) * sg.y)
		lo = Vector2(minf(lo.x, q.x), minf(lo.y, q.z))
		hi = Vector2(maxf(hi.x, q.x), maxf(hi.y, q.z))
	var top := c.y + 12.0
	var bottom := c.y - 12.0
	var on_platform := func(p: Vector3) -> bool:
		var l := inv * p
		if absf(l.x) > half - 5.0 or l.y < ptop - 0.3 or l.y > ptop + 0.5:
			return false
		for bd in bands:
			if l.z > float(bd[0]) + 0.2 and l.z < float(bd[1]) - 0.2:
				return true
		return false
	var starts: Array = []
	for e in sm["entrances"]:
		starts.append(["the street outside an entrance", xf * Vector3(e[0], 0.0, e[2]), true])
	for e in sm["bed_points"]:
		starts.append(["the track bed past a platform end", xf * Vector3(e[0], 0.0, e[2]), false])
	for sp in starts:
		var g: Vector3 = sp[1]
		var s := _surfaces(Vector2i(floori(g.x / CELL), floori(g.z / CELL)), top, bottom)
		sp[1] = Vector3(g.x, s[s.size() - 1] if s.size() > 0 else g.y, g.z)
	for f in flaps:
		(f as CollisionObject3D).collision_layer = 0 if control else 1
	for sp in starts:
		var r := _flood(sp[1], lo, hi, top, bottom, on_platform)
		check("%s: from %s, gates shut, no platform" % [name, sp[0]], not r[0],
			"visited %d%s" % [r[1], (", reached %s" % str(r[2])) if r[0] else ""])
	for f in flaps:
		(f as CollisionObject3D).collision_layer = 0
	for sp in starts:
		if not sp[2]:
			continue
		var r2 := _flood(sp[1], lo, hi, top, bottom, on_platform)
		check("%s: gates open, a platform is reached from %s" % [name, str(sp[1])], r2[0], "visited %d" % r2[1])
	for f in flaps:
		(f as CollisionObject3D).collision_layer = 1


func _run() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--scene="):
			await _run_stand(a.substr(8), OS.get_cmdline_user_args().has("--control"))
			return
	var only := ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--only="):
			only = a.substr(7)
	var control := OS.get_cmdline_user_args().has("--control")
	var w: Node = (load(WORLD) as PackedScene).instantiate()
	root.add_child(w)
	current_scene = w
	await process_frame
	zm = root.get_node_or_null("/root/ZoneManager")
	if zm != null:
		zm.set("debug_log", false)
	var player := w.get_node_or_null("Characters/Player") as CharacterBody3D
	player.set_physics_process(false)
	player.collision_layer = 0
	space = w.get_world_3d().direct_space_state
	shape = CapsuleShape3D.new()
	shape.radius = R
	shape.height = H + 2.0 * R
	var doc: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(RESERVE))
	var boxes := {}
	for b in doc["boxes"]:
		boxes[str(b["id"])] = b
	var n_st := 0
	for id in boxes:
		if not str(id).begins_with("station:"):
			continue
		var name := str(id).substr(8)
		var st: Dictionary = boxes[id]
		if only != "" and only != name:
			continue
		if str(st.get("form", "")) in ["open_air", "ground_hub"]:
			n_st += 1
			await _island_open_air(w, player, name, st, control)
			continue
		if not boxes.has("building:" + name):
			continue
		n_st += 1
		var c := Vector3(float(st["x"]), 0.0, -float(st["y"]))
		var u := Vector3(float(st["ux"]), 0.0, -float(st["uy"]))
		var nrm := Vector3(-u.z, 0.0, u.x)          # the record's (-uy, ux), turned into Godot
		var bed := float(st["z"]) + NET_Y
		var hw := float(st["h_across"])
		var half := float(st["h_along"])
		var pw: float = PLATFORM_W.get(hw, 4.0)
		player.global_position = c + Vector3(0, bed + 3.0, 0)
		await _settle(90.0)
		levels.clear()
		# every door that opens by itself stands open; the gate flaps are what is under test
		var doors: Array = []
		_nodes_of(w, func(n): return n is StaticBody3D and n.get("open_mode") != null, doors)
		var flaps: Array = []
		for d in doors:
			var near: bool = (d as Node3D).global_position.distance_to(c + Vector3(0, bed, 0)) < half + 40.0
			if not near:
				continue
			if str(d.get_script().resource_path).ends_with("TicketGate.java"):
				flaps.append(d)
			elif bool(d.get("auto_open")) and not bool(d.get("locked")):
				(d as CollisionObject3D).collision_layer = 0
		var span := half + 12.0
		var lo := Vector2(minf(c.x - u.x * span - nrm.x * 26.0, c.x + u.x * span + nrm.x * 26.0),
			minf(c.z - u.z * span - nrm.z * 26.0, c.z + u.z * span + nrm.z * 26.0))
		var hi := Vector2(maxf(c.x - u.x * span - nrm.x * 26.0, c.x + u.x * span + nrm.x * 26.0),
			maxf(c.z - u.z * span - nrm.z * 26.0, c.z + u.z * span + nrm.z * 26.0))
		# rotated boxes: widen the axis-aligned bounds to cover the whole rectangle
		for sgn in [Vector2(1, 1), Vector2(1, -1), Vector2(-1, 1), Vector2(-1, -1)]:
			var q: Vector3 = c + u * span * sgn.x + nrm * 26.0 * sgn.y
			lo = Vector2(minf(lo.x, q.x), minf(lo.y, q.z))
			hi = Vector2(maxf(hi.x, q.x), maxf(hi.y, q.z))
		var top := bed + 12.0
		var bottom := bed - 12.0
		var on_platform := func(p: Vector3) -> bool:
			var rel := p - c
			var along := absf(rel.dot(u))
			var lat := absf(rel.dot(nrm))
			return along < half - 5.0 and lat > EDGE + 0.2 and lat < EDGE + pw - 0.2 and p.y > bed + 0.9
		var starts: Array = []
		for key in ["building:" + name, "building_far:" + name]:
			if boxes.has(key):
				var b: Dictionary = boxes[key]
				var bc := Vector3(float(b["x"]), 0.0, -float(b["y"]))
				var bn := Vector3(float(b["nx"]), 0.0, -float(b["ny"]))
				var p := bc + bn * (float(b["h_across"]) + 3.0)
				var s := _surfaces(Vector2i(floori(p.x / CELL), floori(p.z / CELL)), top, bottom)
				if s.size() > 0:
					starts.append(["the street in front of the %s building" % key.get_slice(":", 0), Vector3(p.x, s[s.size() - 1], p.z)])
		var bedp := c + u * (half + 8.0)
		var sb := _surfaces(Vector2i(floori(bedp.x / CELL), floori(bedp.z / CELL)), top, bottom)
		if sb.size() > 0:
			starts.append(["the track bed past the platform end", Vector3(bedp.x, sb[sb.size() - 1], bedp.z)])
		for f in flaps:
			(f as CollisionObject3D).collision_layer = 0 if control else 1
		for sp in starts:
			var r := _flood(sp[1], lo, hi, top, bottom, on_platform)
			check("%s: from %s, gates shut, no platform" % [name, sp[0]], not r[0],
				"visited %d%s" % [r[1], (", reached %s" % str(r[2])) if r[0] else ""])
		for f in flaps:
			(f as CollisionObject3D).collision_layer = 0
		if starts.size() > 0 and str(starts[0][0]).contains("building"):
			var r2 := _flood(starts[0][1], lo, hi, top, bottom, on_platform)
			check("%s: gates open, the platform is reached from the street" % name, r2[0],
				"visited %d, %d flaps" % [r2[1], flaps.size()])
		for f in flaps:
			(f as CollisionObject3D).collision_layer = 1
	check("stations checked", n_st > 0, "%d" % n_st)
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
