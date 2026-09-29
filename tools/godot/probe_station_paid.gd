extends SceneTree
## THE PAID AREA (PLAN.md P3, 2026-09-27): a station's platforms are reached ONLY through the ticket gates.
##   stdbuf -oL <godot> --headless --path . --script tools/godot/probe_station_paid.gd [-- --only=<Station>] [--control]
##
## For every station of the rail reserve (IslandRailReserve.json; every one a kit station since PLAN.md step 7), on the real World.tscn
## with the real ZoneManager: stream the station in, then FLOOD-FILL where a standing character can be -- a grid of
## 0.25 m cells, every walkable surface in each cell (so a stair, a platform and a concourse deck over the bed are all
## nodes), a step of at most 0.4 m between neighbours, and a capsule that must fit standing at each node.
##   1. from the street in front of each station building, with the gate flaps SHUT, no platform is reached;
##   2. from the track bed past a platform end (a trespasser who walked in at a 踏切), no platform is reached;
##   3. with the flaps OPEN, the platform IS reached from the street -- the route through the gates exists.
## Every door that opens by itself (a shop's sliding entrance, the building's back door) is treated as open.
## `--control`: the flaps are opened for cases 1 and 2 too -- they must then fail.
## `--trace`: print the route of every flood that reaches a platform (where a leak goes).

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const RESERVE := "res://assets/world_source/buildings/IslandRailReserve.json"
const NET_Y := 0.6
const CELL := 0.25
const R := 0.2                  # the probing capsule (a character is 0.35; 0.2 finds every opening it could use)
const H := 1.6
const STEP := 0.4
## the most a STEP-FREE route (a wheelchair on the entry slope) may rise between two 0.25 m cells: the slope is 1:12
## (0.021 m a cell); its step colliders stand 0.042 m apart every 0.5 m
var max_step := STEP

var fails := 0
var trace := OS.get_cmdline_user_args().has("--trace")
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
			# a graze down a face or an underside. A floor whose EDGE lies on the cell centre (a landing ending exactly
			# on the grid: Castle Town's entry slope, 2026-09-28) grazes its own side face and would read as a one-cell
			# gap across the slope, so look a few cm aside for a floor at that height before stepping past it
			var q2 := PhysicsRayQueryParameters3D.create(Vector3(x + 0.03, y + 0.05, z + 0.03),
				Vector3(x + 0.03, y - 0.25, z + 0.03), 1)
			var h2 := space.intersect_ray(q2)
			if not h2.is_empty() and (h2["normal"] as Vector3).y > 0.6 and absf(h2["position"].y - y) < 0.1:
				out.append(h2["position"].y)
				from = h2["position"].y - 0.05
			else:
				from = y - 0.25
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

## What a standing capsule collides with at `p` and at the four cells round it (a flood that dies at its start).
func _blockers(p: Vector3) -> Array:
	var out := []
	for d in [Vector3.ZERO, Vector3(CELL, 0, 0), Vector3(-CELL, 0, 0), Vector3(0, 0, CELL), Vector3(0, 0, -CELL)]:
		var q := PhysicsShapeQueryParameters3D.new()
		q.shape = shape
		q.collision_mask = 1
		q.transform = Transform3D(Basis.IDENTITY, p + d + Vector3(0, STEP + H / 2.0 + R, 0))
		for h in space.intersect_shape(q, 4):
			var n := str((h["collider"] as Node).get_path()).replace("/root/World/", "")
			if not out.has(n):
				out.append(n)
	return out


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
	var parent := {}
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
			if trace:
				_print_path(parent, Vector3(cc.x, cc.y, snappedf(y, 0.05)))
			return [true, head, p]
		for d in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
			var nc: Vector2i = cc + d
			if (nc.x + 0.5) * CELL < lo.x or (nc.x + 0.5) * CELL > hi.x or (nc.y + 0.5) * CELL < lo.y \
					or (nc.y + 0.5) * CELL > hi.y:
				continue
			for ny in _surfaces(nc, top, bottom):
				if absf(ny - y) > max_step:
					continue
				var key := Vector3(nc.x, nc.y, snappedf(ny, 0.05))
				if seen.has(key):
					continue
				seen[key] = true
				if _fits(Vector3((nc.x + 0.5) * CELL, ny, (nc.y + 0.5) * CELL)):
					queue.append([nc, ny])
					parent[key] = Vector3(cc.x, cc.y, snappedf(y, 0.05))
	return [false, head, null]

## `--trace`: print the route to a goal a flood reached (where a leak goes), condensed to its turns and level changes.
func _print_path(parent: Dictionary, k: Vector3) -> void:
	var pts: Array = []
	while true:
		pts.push_front(k)
		if not parent.has(k):
			break
		k = parent[k]
	var line := "    path:"
	var last_y := -999.0
	for i in pts.size():
		var q: Vector3 = pts[i]
		if i == 0 or i == pts.size() - 1 or absf(q.z - last_y) > 0.3 or i % 40 == 0:
			line += " (%.2f, %.2f, %.2f)" % [(q.x + 0.5) * CELL, q.z, (q.y + 0.5) * CELL]
			last_y = q.z
	print(line)

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
	var meta: Dictionary = sc.get_meta("building")
	var st: Dictionary = meta["station"]
	var half := float(st["length"]) / 2.0
	# the street lies `street` below the bed (an elevated hub's F1); the rail's own viaduct deck is not in the station
	# scene, so the stand builds it along each lane (the bed past a platform end is ON it)
	var street := float(st.get("street", 0.0))
	gs.position = Vector3(0, street - 0.5, 0)
	# an OPEN-AIR station's two streets need not be one height: each side's entry (stair + slope) is sized from ITS
	# street (`entry_rise`), and each entrance point carries that street's height. A flat stand at one of them buries
	# the other side's slope foot under the stand (Castle Town, 2026-09-28: 0.55 m), so the stand's ground is the
	# plane through the entrances' own heights across the axis -- a real street rising a few percent round the station.
	var tilt_a := street
	var tilt_b := 0.0
	var tilt_z := Vector2(-1e9, 1e9)
	var ents: Array = st.get("entrances", [])
	if str(st.get("form", "")) == "open_air" and ents.size() >= 2:
		var n := float(ents.size())
		var sz := 0.0
		var sy := 0.0
		var szz := 0.0
		var szy := 0.0
		for e in ents:
			sz += float(e[2])
			sy += float(e[1])
			szz += float(e[2]) * float(e[2])
			szy += float(e[2]) * float(e[1])
		var den := n * szz - sz * sz
		if absf(den) > 1e-6:
			tilt_b = (n * szy - sz * sy) / den
			tilt_a = (sy - tilt_b * sz) / n
			# tilted only BETWEEN the entrances; past each one the street stays at that entrance's own height (a
			# tilt carried on dropped the ground away from the far end of the lower side's slope)
			var zlo := 1e9
			var zhi := -1e9
			for e in ents:
				zlo = minf(zlo, float(e[2]))
				zhi = maxf(zhi, float(e[2]))
			tilt_z = Vector2(zlo, zhi)
			var ang := atan(tilt_b)
			var zm := 0.5 * (zlo + zhi)
			gb.size = Vector3(400, 1, (zhi - zlo) / cos(ang))
			gs.rotation = Vector3(-ang, 0, 0)
			gs.position = Vector3(0, tilt_a + tilt_b * zm - 0.5 / cos(ang), zm)
			for side in [[zlo - 200.0, zlo], [zhi, zhi + 200.0]]:
				var fs := CollisionShape3D.new()
				var fb := BoxShape3D.new()
				fb.size = Vector3(400, 1, side[1] - side[0])
				fs.shape = fb
				var edge: float = zlo if side[1] == zlo else zhi
				fs.position = Vector3(0, tilt_a + tilt_b * edge - 0.5, 0.5 * (side[0] + side[1]))
				ground.add_child(fs)
	var street_at := func(z: float) -> float:
		return tilt_a + tilt_b * clampf(z, tilt_z.x, tilt_z.y)
	var deck: Array = st.get("deck", [])
	if deck.size() == 2:
		for ln in st["lanes"]:
			var ds := CollisionShape3D.new()
			var db := BoxShape3D.new()
			db.size = Vector3(2 * half + 160, float(deck[1]), 2 * float(deck[0]))
			ds.shape = db
			ds.position = Vector3(0, -float(deck[1]) / 2.0, -float(ln[1]))
			ground.add_child(ds)
	await physics_frame
	await physics_frame
	space = w.get_world_3d().direct_space_state
	shape = CapsuleShape3D.new()
	shape.radius = R
	shape.height = H + 2.0 * R
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
	var along := half + 40.0
	# ...and every collider the scene carries, plus room to step off it: an entry slope runs along the building's
	# front and can end past the drawn footprint (Castle Town's 11-riser slope ends ~40 m off the axis, 2026-09-28,
	# and a flood bounded at 40 m never reached its foot)
	var shapes: Array = []
	_nodes_of(sc, func(n): return n is CollisionShape3D and (n as CollisionShape3D).shape != null, shapes)
	for cs in shapes:
		var bb: AABB = (cs as CollisionShape3D).global_transform * (cs as CollisionShape3D).shape.get_debug_mesh().get_aabb()
		across = maxf(across, maxf(absf(bb.position.z), absf(bb.end.z)) + 5.0)
		along = maxf(along, maxf(absf(bb.position.x), absf(bb.end.x)) + 5.0)
	# ...and along, past every collider and street entrance (an open-air entry ramp runs ~48 m past the platform's
	# end since 2026-09-28; a bound at 40 m put its street start outside the flood)
	for e in ents:
		along = maxf(along, absf(float(e[0])) + 5.0)
	var aabb := AABB(Vector3(-along, street - 2, -across), Vector3(2 * along, 20, 2 * across))
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
		starts.append(["the street outside an entrance", Vector3(e[0], street_at.call(float(e[2])), e[2])])
	for e in st["bed_points"]:
		starts.append(["the track bed past a platform end", Vector3(e[0], street_at.call(float(e[2])), e[2])])
	for f in flaps:
		(f as CollisionObject3D).collision_layer = 0 if control else 1
	for sp in starts:
		levels.clear()
		var r := _flood(sp[1], lo, hi, 12.0, street - 2.0, on_platform)
		check("%s: from %s %s, gates shut, no platform" % [st["name"], sp[0], str(sp[1])], not r[0],
			"visited %d%s" % [r[1], (", reached %s" % str(r[2])) if r[0] else ""])
	for f in flaps:
		(f as CollisionObject3D).collision_layer = 0
	for e in st["entrances"]:
		levels.clear()
		var r2 := _flood(Vector3(e[0], street_at.call(float(e[2])), e[2]), lo, hi, 12.0, street - 2.0, on_platform)
		check("%s: gates open, a platform is reached from %s" % [st["name"], str(e)], r2[0], "visited %d" % r2[1])
	# ...and EVERY platform from EVERY entrance, not just the nearest one: an island platform's stair (Central's, in
	# the gap between two decks; a ground hub's, down from the concourse) is its own route and must work on its own,
	# and an open-air station's far platform is reached round by the street through its own building.
	for e in st["entrances"]:
		for bd in bands:
			var z0 := float(bd[0])
			var z1 := float(bd[1])
			var on_this := func(p: Vector3) -> bool:
				return absf(p.x) <= half - 5.0 and p.y >= ptop - 0.3 and p.y <= ptop + 0.5 \
					and p.z > z0 + 0.2 and p.z < z1 - 0.2
			levels.clear()
			var r3 := _flood(Vector3(e[0], street_at.call(float(e[2])), e[2]), lo, hi, 12.0, street - 2.0, on_this)
			check("%s: gates open, from %s the platform at z %.2f..%.2f is reached" % [st["name"], str(e), z0, z1],
				r3[0], "visited %d" % r3[1])
	# an OPEN-AIR station has no lift: its entry SLOPE is the accessible route (user, 2026-09-27), so every platform
	# must be reached from every entrance with no step a wheelchair could not roll over
	if str(st["form"]) == "open_air":
		max_step = 0.06
		for e in st["entrances"]:
			var ok := true
			for bd in bands:
				var z0b := float(bd[0])
				var z1b := float(bd[1])
				var on_b := func(p: Vector3) -> bool:
					return absf(p.x) <= half - 5.0 and p.y >= ptop - 0.3 and p.y <= ptop + 0.5 \
						and p.z > z0b + 0.2 and p.z < z1b - 0.2
				levels.clear()
				var r4 := _flood(Vector3(e[0], street_at.call(float(e[2])), e[2]), lo, hi, 12.0, street - 2.0, on_b)
				ok = ok and r4[0]
			check("%s: step-free (the slope), every platform reached from %s" % [st["name"], str(e)], ok, "")
		max_step = STEP
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
	# along: past every street entrance too (an open-air entry ramp runs ~48 m past the platform's end since
	# 2026-09-28; at half + 40 every open-air station's street start lay OUTSIDE the flood's box and it visited 1 cell)
	var span := half + 40.0
	for e in sm["entrances"]:
		span = maxf(span, absf(float(e[0])) + 20.0)
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
		starts.append(["the street outside an entrance", xf * Vector3(e[0], e[1], e[2]), true])
	for e in sm["bed_points"]:
		starts.append(["the track bed past a platform end", xf * Vector3(e[0], e[1], e[2]), false])
	for sp in starts:
		# snap to the walkable surface NEAREST the point the meta names (an elevated hub's bed is on the viaduct, over
		# the ground; its street is under it)
		var g: Vector3 = sp[1]
		var s := _surfaces(Vector2i(floori(g.x / CELL), floori(g.z / CELL)), top, bottom)
		var yy := g.y
		var bestd := INF
		for v in s:
			if absf(v - g.y) < bestd:
				bestd = absf(v - g.y)
				yy = v
		sp[1] = Vector3(g.x, yy, g.z)
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
		if not r2[0] and int(r2[1]) <= 3:
			print("    blocked at its start by: %s" % str(_blockers(sp[1])))
			var c0 := Vector2i(floori(sp[1].x / CELL), floori(sp[1].z / CELL))
			for d in [Vector2i(0, 0), Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
				print("    floors at %s: %s" % [str(c0 + d), str(_surfaces(c0 + d, top, bottom))])
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
	# the WHOLE body stands still: MovementController is its own node and kept moving it, so the teleported player fell
	# through ground that had not streamed yet, died, and the stations after it never streamed (2026-09-28)
	player.process_mode = Node.PROCESS_MODE_DISABLED
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
		if str(st.get("form", "")) in ["open_air", "ground_hub", "elevated_hub"]:
			n_st += 1
			await _island_open_air(w, player, name, st, control)
			continue
		# every station is a KIT station (PLAN.md step 7): one with no form is a stale reserve
		check("%s: a kit station (its reserve names a form)" % name, false, str(st.get("form", "")))
	check("stations checked", n_st > 0, "%d" % n_st)
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
