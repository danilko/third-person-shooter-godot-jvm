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
	var x := c.x * CELL
	var z := c.y * CELL
	var from := top
	for k in 5:
		var q := PhysicsRayQueryParameters3D.create(Vector3(x, from, z), Vector3(x, bottom, z), 1)
		var h := space.intersect_ray(q)
		if h.is_empty():
			break
		var y: float = h["position"].y
		if (h["normal"] as Vector3).y > 0.6:
			out.append(y)
		from = y - 0.05
	levels[c] = out
	return out

func _fits(p: Vector3) -> bool:
	var q := PhysicsShapeQueryParameters3D.new()
	q.shape = shape
	q.collision_mask = 1
	q.transform = Transform3D(Basis.IDENTITY, p + Vector3(0, 0.05 + H / 2.0 + R, 0))
	return space.intersect_shape(q, 1).is_empty()

## Breadth-first over (cell, level) from `start`; `is_goal(p)` ends it. Returns [reached goal, nodes visited].
func _flood(start: Vector3, lo: Vector2, hi: Vector2, top: float, bottom: float, is_goal: Callable) -> Array:
	var c0 := Vector2i(roundi(start.x / CELL), roundi(start.z / CELL))
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
		var p := Vector3(cc.x * CELL, y, cc.y * CELL)
		if is_goal.call(p):
			return [true, head, p]
		for d in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
			var nc: Vector2i = cc + d
			if nc.x * CELL < lo.x or nc.x * CELL > hi.x or nc.y * CELL < lo.y or nc.y * CELL > hi.y:
				continue
			for ny in _surfaces(nc, top, bottom):
				if absf(ny - y) > STEP:
					continue
				var key := Vector3(nc.x, nc.y, snappedf(ny, 0.05))
				if seen.has(key):
					continue
				seen[key] = true
				if _fits(Vector3(nc.x * CELL, ny, nc.y * CELL)):
					queue.append([nc, ny])
	return [false, head, null]

func _run() -> void:
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
		if not boxes.has("building:" + name) or (only != "" and only != name):
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
				var s := _surfaces(Vector2i(roundi(p.x / CELL), roundi(p.z / CELL)), top, bottom)
				if s.size() > 0:
					starts.append(["the street in front of the %s building" % key.get_slice(":", 0), Vector3(p.x, s[s.size() - 1], p.z)])
		var bedp := c + u * (half + 8.0)
		var sb := _surfaces(Vector2i(roundi(bedp.x / CELL), roundi(bedp.z / CELL)), top, bottom)
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
