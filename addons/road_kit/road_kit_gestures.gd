@tool
extends RefCounted
## Road Kit AUTHORING GESTURES (PLAN.md 3.1 B4) — the kit's Blender operators rebuilt as pure
## functions over RoadKitNetwork / RoadKitRoad / RoadKitPoint nodes. No editor API here, so every
## gesture runs (and is tested) headless; the plugin wraps each in an undo step that restores the
## network's record. Rules are the kit's (`point_ops.py`), restated where cited:
##   * a road's CHILD ORDER is its chain (FWD = increasing index), and names follow it;
##   * SEGMENT and JUNCTION links are symmetric, AUX is directed mainline -> ramp;
##   * a junction is a CLIQUE over JUNCTION links, every member typed INTERSECTION;
##   * `Extend Road` works from EITHER end and refuses an interior point.
## Each gesture returns {"ok": bool, "message": String, "node": created-or-affected node or null}.

const RoadScript := preload("res://addons/road_kit/road_kit_road.gd")
const PointScript := preload("res://addons/road_kit/road_kit_point.gd")
const NetworkScript := preload("res://addons/road_kit/road_kit_network.gd")
const Fields := preload("res://addons/road_kit/road_kit_fields.gd")
const Ground := preload("res://addons/road_kit/road_kit_ground.gd")

## Default spacing of a new station along its road, metres.
const STEP := 40.0

static func _ok(msg: String, node = null) -> Dictionary:
	return {"ok": true, "message": msg, "node": node}

static func _fail(msg: String) -> Dictionary:
	return {"ok": false, "message": msg, "node": null}

static func is_point(n) -> bool:
	return n is Node and n.get_script() == PointScript

static func is_road(n) -> bool:
	return n is Node and n.get_script() == RoadScript

static func network_of(n: Node) -> Node:
	var cur := n
	while cur != null:
		if cur.get_script() == NetworkScript:
			return cur
		cur = cur.get_parent()
	return null

static func new_uid(net: Node) -> String:
	var taken := {}
	for p in net.all_points():
		taken[p.uid] = true
	while true:
		var u := "p_%08x" % (randi() & 0xffffffff)
		if not taken.has(u):
			return u
	return ""

static func _own(node: Node, net: Node) -> void:
	node.owner = net.owner if net.owner != null else net

## Names follow the chain: `<road>_p000..`. Two passes so a rename never collides mid-way.
static func renumber(road: Node) -> void:
	var pts: Array = road.points()
	for i in pts.size():
		pts[i].name = "__rk_tmp_%d" % i
	for i in pts.size():
		pts[i].name = "%s_p%03d" % [road.name, i]

static func _new_point(net: Node, road: Node, at_index: int, xf: Transform3D) -> Node:
	var p: Node3D = PointScript.new()
	p.uid = new_uid(net)
	for f in Fields.DELTA_FIELDS:
		p.fields[f] = road.base.get(f, p.fields[f])
	p.fields["lane_width"] = road.base.get("lane_width", p.fields["lane_width"])
	road.add_child(p)
	road.move_child(p, at_index)
	_own(p, net)
	p.set_network_transform(xf)
	p.auto_facing = -xf.basis.z.normalized()      # born facing its road: that is the tool's facing
	return p

static func link(a: Node, b: Node, type: String) -> void:
	a.link_to(b.uid, type)
	if type != "AUX":
		b.link_to(a.uid, type)

static func unlink(a: Node, b: Node) -> int:
	return a.unlink(b.uid) + b.unlink(a.uid)

## A new road of two stations `STEP` apart, starting at `origin` and running along `facing`
## (network frame, Godot axes).
static func new_road(net: Node, road_name: String, origin: Vector3, facing: Vector3 = Vector3.FORWARD) -> Dictionary:
	if net.get_node_or_null(NodePath(road_name)) != null:
		return _fail("a road named %s already exists" % road_name)
	var dir := Vector3(facing.x, 0, facing.z).normalized()
	if dir.length() < 0.5:
		dir = Vector3.FORWARD
	var road: Node3D = RoadScript.new()
	road.name = road_name
	net.add_child(road)
	_own(road, net)
	var basis := Basis.looking_at(dir, Vector3.UP)
	var a := _new_point(net, road, 0, Transform3D(basis, origin))
	var b := _new_point(net, road, 1, Transform3D(basis, origin + dir * STEP))
	link(a, b, "SEGMENT")
	renumber(road)
	return _ok("new road %s" % road_name, road)

## Grow the chain from either END by one station, continuing the end's direction.
static func extend_road(point: Node) -> Dictionary:
	if not is_point(point):
		return _fail("select a road point")
	var road: Node = point.get_parent()
	var net := network_of(point)
	var pts: Array = road.points()
	var i := pts.find(point)
	var at_tail := i == pts.size() - 1
	var at_head := i == 0
	if not (at_tail or at_head):
		return _fail("%s is interior -- extend from an end, or use Insert Point" % point.name)
	var xf: Transform3D = point.network_transform()
	var dir: Vector3
	if pts.size() >= 2:
		var nb: Node = pts[i - 1] if at_tail else pts[i + 1]
		dir = (xf.origin - nb.network_transform().origin)
	else:
		dir = -xf.basis.z
	dir.y = 0.0
	dir = dir.normalized() if dir.length() > 1e-6 else Vector3.FORWARD
	var pos := xf.origin + dir * STEP
	# A head extension runs the other way: the chain's travel direction still points INTO the road.
	var facing := dir if at_tail else -dir
	var p := _new_point(net, road, (pts.size() if at_tail else 0), Transform3D(Basis.looking_at(facing, Vector3.UP), pos))
	link(point, p, "SEGMENT")
	renumber(road)
	return _ok("extended %s from its %s" % [road.name, "tail" if at_tail else "head"], p)

## Split the span after `point` (to the next chain point it is SEGMENT-linked to) at its midpoint.
static func insert_after(point: Node) -> Dictionary:
	if not is_point(point):
		return _fail("select a road point")
	var road: Node = point.get_parent()
	var pts: Array = road.points()
	var i := pts.find(point)
	if i >= pts.size() - 1:
		return _fail("%s is the last point -- use Extend Road" % point.name)
	var nxt: Node = pts[i + 1]
	var linked: bool = point.links.any(func(l): return l["target"] == nxt.uid and l["type"] == "SEGMENT")
	if not linked:
		return _fail("%s and %s are not a span (no SEGMENT link) -- a junction gap is not split" % [point.name, nxt.name])
	var a: Transform3D = point.network_transform()
	var b: Transform3D = nxt.network_transform()
	var mid := (a.origin + b.origin) * 0.5
	var dir := (b.origin - a.origin)
	dir.y = 0.0
	var names := [String(point.name), String(nxt.name)]
	var p := _new_point(network_of(point), road, i + 1, Transform3D(Basis.looking_at(dir.normalized(), Vector3.UP), mid))
	unlink(point, nxt)
	link(point, p, "SEGMENT")
	link(p, nxt, "SEGMENT")
	renumber(road)
	return _ok("inserted a point between %s and %s" % names, p)

## Delete a point: INBOUND links are stripped first, so nothing dangles (the kit's zombie rule).
static func delete_point(point: Node) -> Dictionary:
	if not is_point(point):
		return _fail("select a road point")
	var net := network_of(point)
	var road: Node = point.get_parent()
	for p in net.all_points():
		if p != point:
			p.unlink(point.uid)
	road.remove_child(point)
	point.free()
	renumber(road)
	return _ok("deleted a point from %s" % road.name)

## `(mainline, ramp)` for an AUX pair — scored like `point_ops.resolve_aux_pair`, not click order.
static func resolve_aux_pair(a: Node, b: Node) -> Array:
	var score := func(main: Node, ramp: Node) -> int:
		var s := 0
		if int(main.fields["aux_fwd"]) + int(main.fields["aux_bwd"]) > 0: s += 3
		if ["RAMP", "RAMP_ENTRY", "RAMP_EXIT"].has(ramp.fields["role"]): s += 2
		if ["RAMP", "RAMP_ENTRY", "RAMP_EXIT"].has(main.fields["role"]): s -= 2
		if int(ramp.fields["aux_fwd"]) + int(ramp.fields["aux_bwd"]) > 0: s -= 1
		if int(ramp.fields["lanes_bwd"]) == 0 or int(ramp.fields["lanes_fwd"]) == 0: s += 1
		if int(main.fields["lanes_bwd"]) == 0 or int(main.fields["lanes_fwd"]) == 0: s -= 1
		return s
	return [a, b] if score.call(a, b) >= score.call(b, a) else [b, a]

## Connect two points. SEGMENT and JUNCTION are symmetric; AUX is directed and its direction is
## derived (`resolve_aux_pair`). A pair carries at most ONE link.
static func connect_points(a: Node, b: Node, type: String) -> Dictionary:
	if not (is_point(a) and is_point(b)) or a == b:
		return _fail("select two different road points")
	if not Fields.LINK_TYPES.has(type):
		return _fail("unknown link type %s" % type)
	unlink(a, b)
	if type == "AUX":
		var pair := resolve_aux_pair(a, b)
		link(pair[0], pair[1], "AUX")
		return _ok("AUX %s -> %s" % [pair[0].name, pair[1].name])
	link(a, b, type)
	return _ok("%s %s <-> %s" % [type, a.name, b.name])

## A junction: every selected point linked to every other (a clique) and typed INTERSECTION. The
## kit's rule that a gesture handing out a JUNCTION link owes the WHOLE pad (ROAD_POINT_GRAPH 8q).
static func make_intersection(points: Array) -> Dictionary:
	var pts := points.filter(func(p): return is_point(p))
	if pts.size() < 2:
		return _fail("select at least two mouths")
	var roads := {}
	for p in pts:
		roads[p.get_parent()] = true
	if roads.size() < 2:
		return _fail("a junction joins different roads -- these are all on one")
	# Complete an existing clique the selection touches, never leave a component.
	var net := network_of(pts[0])
	var members := {}
	for p in pts:
		members[p.uid] = p
	var grew := true
	while grew:
		grew = false
		for uid in members.keys():
			for l in members[uid].links:
				if l["type"] == "JUNCTION" and not members.has(l["target"]):
					var q = net.find_point(l["target"])
					if q != null:
						members[q.uid] = q
						grew = true
	var ms: Array = members.values()
	for i in ms.size():
		ms[i].fields["role"] = "INTERSECTION"
		for j in range(i + 1, ms.size()):
			link(ms[i], ms[j], "JUNCTION")
	return _ok("junction of %d mouths" % ms.size())

## Face every point the tool still owns along its road (`facings` is `roadkit_cli.py facings`, the
## solver's `point_profile.chain_facings`, Godot axes) -- AFTER promoting the ones the artist rotated,
## or the re-face would overwrite the very rotation it is meant to notice (`point_ops.sync_facings`).
## `{"ok", "message", "promoted", "refaced"}`.
static func apply_facings(net: Node, facings: Dictionary) -> Dictionary:
	var promoted := 0
	var refaced := 0
	for p in net.all_points():
		if p.fields.get("tangent_mode", "AUTO") != "AUTO":
			continue
		if p.sync_promotion():
			promoted += 1
			continue
		var f = facings.get(p.uid)
		if f == null:
			continue
		var d := Vector3(float(f[0]), float(f[1]), float(f[2]))
		if p.auto_facing == Vector3.ZERO or rad_to_deg((-p.network_transform().basis.z).angle_to(d)) > Fields.ROTATED_TOL_DEG:
			refaced += 1
		p.face(d)
	return {"ok": true, "message": "%d rotated point(s) now shape their road, %d re-faced" % [promoted, refaced],
			"promoted": promoted, "refaced": refaced}

## `Follow Road (Auto)`: hand the facing back to the tool -- AUTO, re-faced along the chain.
static func follow_road(points: Array, facings: Dictionary) -> Dictionary:
	var n := 0
	for p in points:
		if not is_point(p):
			continue
		p.fields["tangent_mode"] = "AUTO"
		var f = facings.get(p.uid)
		if f != null:
			p.face(Vector3(float(f[0]), float(f[1]), float(f[2])))
		n += 1
	return _ok("%d point(s) follow their road again" % n) if n > 0 else _fail("select road points")

## Every mouth of the junction `point` belongs to (the JUNCTION component), for Select Junction: moving
## or turning that selection moves the whole crossing. There is no handle node in Godot -- a road's
## CHILD ORDER is its chain, so a mouth cannot be re-parented under one -- and the editor's own
## multi-selection pivot is the handle.
static func junction_members(point: Node) -> Array:
	if not is_point(point):
		return []
	var net := network_of(point)
	var seen := {point.uid: point}
	var stack := [point]
	while not stack.is_empty():
		var cur: Node = stack.pop_back()
		for l in cur.links:
			if l["type"] == "JUNCTION" and not seen.has(l["target"]):
				var q = net.find_point(l["target"])
				if q != null:
					seen[q.uid] = q
					stack.append(q)
	return seen.values() if seen.size() > 1 else []

## A RAMP is not a GDScript gesture on purpose: where its mouth belongs (the gore line), which
## carriageway feeds it and how far back the aux slot must open for the taper are solver facts owned
## by `point_solve`, reached through `roadkit_cli.py ramp` (the plugin's Make Ramp button).

## Write each point's ground height from Terrain3D into the record (`ground_z`, `has_ground_z`) — the
## terrain the GAME has, which is the whole reason authoring moved to Godot. Blender's mesh build keeps
## a sampled height when its own scene has no terrain (`point_build.sample_ground` returns early), so
## supports and embankments follow this. `terrain` is a Terrain3D node; its `data.get_height(global)`
## is NaN off the map, and such a point keeps whatever height it had.
##
## SAMPLE THE NATURAL GROUND. Once roads are stamped into the height map, sampling again reads the
## road's own height back as ground — the kit's CARVED_FLAG trap (a second build "found" the ground
## meeting the road at 195 of 225 stations). So a stamped network reads its ground sidecar, which is
## the natural ground, wherever it covers (`road_kit_ground.natural_height`).
static func sample_ground(net: Node, terrain: Node) -> Dictionary:
	if terrain == null or terrain.get("data") == null:
		return _fail("no Terrain3D data to sample")
	var src: Dictionary = Ground.natural_source(net)
	if src.is_empty() and FileAccess.file_exists(Ground.stamp_record_path(str(net.get("record_path")))):
		return _fail("%s is stamped into the terrain but its natural ground sidecar is missing -- not re-sampling the stamped roads as ground" % net.name)
	var in_tree: bool = net.is_inside_tree()
	var to_world: Transform3D = net.global_transform if in_tree else net.transform
	var hits := 0
	var misses := 0
	for p in net.all_points():
		var local: Vector3 = p.network_transform().origin
		var world: Vector3 = to_world * local
		var h: float = Ground.natural_height(net, terrain, src, world)
		if is_nan(h):
			misses += 1
			continue
		var ground_local: Vector3 = to_world.affine_inverse() * Vector3(world.x, h, world.z)
		p.fields["ground_z"] = ground_local.y
		p.fields["has_ground_z"] = true
		hits += 1
	return _ok("ground sampled at %d point(s), %d off the terrain" % [hits, misses])
