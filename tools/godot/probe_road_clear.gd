extends SceneTree
## PLAN.md 3.35 gate: NOTHING SOLID STANDS IN A CARRIAGEWAY.
##
##   godot --headless --path . --script tools/godot/probe_road_clear.gd [-- <scene.tscn>] [--control]
##
## A road the game generates is assembled from several owners that each place solid things NEAR a
## lane and none of which sees the others: the Road Kit's own piers (`point_mesh.pillars`, dropped
## only by `pier_on_road`), median and sound walls, rock-shed columns, the 3 m vehicle-only car wall
## along every barrier, `point_furniture`'s poles, planters, bollards and street trees, and — outside
## the road pipeline entirely — building lots, sites and landmarks. Every one of them has its own
## clearance rule, and every one of those rules is a rule about the LANE EDGE. None of them asks the
## question a player asks: *can a car actually drive down this lane*.
##
## So this probe asks exactly that, of the BAKED COLLISION rather than of any placement rule: it
## sweeps a car-sized box along every exported lane of every streamed piece and reports anything
## it hits. The box is the car's own envelope (`CAR_HALF` either side of the lane centre, from
## `CLEAR_LOW` above the road surface to `CLEAR_HIGH`), queried on a vehicle's own mask
## (`WORLD | CAR_WALL`), so the road surface below it, a kerb, a median wall, a barrier and a deck
## overhead are all legitimately outside it and only an obstruction in the driving space is a hit.
##
## Pieces are instanced by the probe (`Zone.placeGeometry`'s rule) and every ZoneMarker is then freed,
## so the ZoneManager AutoLoad cannot stream a second copy of anything into the same physics space.
##
## It asks the question TWICE, because the two answers want different remedies:
##   * OBSTRUCTION (`CLEAR_LOW`..`BONNET_HIGH`) -- a post, a wall, a pier or a kerb standing in front of
##     the bumper. A car cannot pass at all; the remedy is to move the thing or the lane.
##   * HEADROOM (`BONNET_HIGH`..`CLEAR_HIGH`) -- something only the roof would meet: a soffit, a sign,
##     a deck too low over the lane it spans. The remedy is a grade, not a placement.
## Both are reported; only the OBSTRUCTION half fails the gate, so a low soffit cannot mask a bollard.
##
## What it does NOT answer, on purpose: the GROUND standing proud of a road (Terrain3D builds its collision at
## runtime and a headless run has none) -- that is `probe_road_stamp.gd`'s check, which measures the height field
## directly; and whether a lane is DRIVEABLE (grades, corner radii), which is `probe_road_launch.gd`'s.
##
## `-- --control` drops a 1 m post into the middle of every 40th lane: the gate must FAIL, and by
## exactly that many.
## `-- --no-buildings` skips the building cells (the road pieces alone are the usual suspect and cost
## a fraction of the memory); `-- --only=<substr>` narrows to the pieces whose name contains it.

const DEFAULT_SCENE := "res://src/main/resources/com/openworld/world/World.tscn"

## The driving envelope. A car here is 2.0 m wide with its wheels at +-1.1 m (`SPC1`), so `CAR_HALF`
## is the hull, not the lane: the question is whether a CAR fits, never whether the lane is clear to
## its own edges (a kerb, a lane line and a median all legitimately sit inside a lane's width).
const CAR_HALF := 1.10
## Above the road surface. The surface itself, its crossfall (~2% over 1.1 m = 2 cm) and a 0.15 m kerb
## are all under this, so none of them is an obstruction; anything at 0.30 m above the tarmac is.
const CLEAR_LOW := 0.30
## A van's roof. Grade separation is solved at 5.5 m (`point_solve.CLEARANCE`) and a rock shed's
## soffit at 5.5 m, so a legitimate deck or roof overhead is well clear of this.
const CLEAR_HIGH := 2.00
## Bonnet height: the split between "a car cannot pass" and "only its roof would touch". A car here is
## ~1.5 m tall and its bonnet ~1.1 m, so anything under this is in front of the driver, not over them.
const BONNET_HIGH := 1.20
const STEP := 2.0
const BOX_LONG := 0.60
## WORLD | CAR_WALL -- a vehicle body's own mask, minus the layers that hold other vehicles and people.
const CAR_MASK := 1 | 32

var fails := 0
var world: Node
var pieces: Array[Node3D] = []
var road_piece := {}     # piece node -> true when its source scene is a road piece (Roads_*)
var controls: Array[Node3D] = []

func check(label: String, ok: bool, detail := "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-64s %s" % ["PASS" if ok else "FAIL", label, detail])

func _arg(name: String, dflt := ""):
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--%s=" % name):
			return a.substr(name.length() + 3)
	return dflt

func _markers(n: Node, out: Array) -> void:
	var s = n.get_script()
	if s != null and str(s.resource_path).ends_with("ZoneMarker.java"):
		out.append(n)
	for c in n.get_children():
		_markers(c, out)

func _place(path: String, xf: Transform3D, nm: String) -> void:
	var ps := load(path) as PackedScene
	if ps == null:
		return
	var inst: Node3D = ps.instantiate()
	inst.name = nm
	root.add_child(inst)
	inst.global_transform = xf
	pieces.append(inst)
	road_piece[inst] = path.get_file().begins_with("Roads_")

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var scene := DEFAULT_SCENE
	for a in args:
		if a.ends_with(".tscn"):
			scene = a
	var control := "--control" in args
	var no_buildings := "--no-buildings" in args
	var only := str(_arg("only"))
	world = (load(scene) as PackedScene).instantiate()
	root.add_child(world)
	await process_frame

	# Read every zone's geometry, then FREE the markers: the probe owns the only copy of each piece in
	# this physics space, so a streamed duplicate cannot answer a query the probe did not ask.
	var ms := []
	_markers(world, ms)
	var plan := []
	for m in ms:
		var z = m.get("zone")
		if z == null:
			continue
		var gp := str(z.get("geometry_path"))
		if gp == "" or not ResourceLoader.exists(gp):
			continue
		if no_buildings and gp.get_file().begins_with("Bld_"):
			continue
		if only != "" and not gp.get_file().contains(only):
			continue
		var xf: Transform3D = z.get("geometry_world_transform") if z.get("geometry_world_placed") else (m as Node3D).global_transform
		plan.append([gp, xf, "Probe_" + str(z.get("zone_id"))])
	for m in ms:
		m.get_parent().remove_child(m)
		m.queue_free()
	await process_frame
	for p in plan:
		_place(p[0], p[1], p[2])
	# A network with no zones builds ONE resident piece at the network (road_kit_preview.gd's rule).
	for net in world.find_children("*", "Node3D", true, false):
		if not str(net.get("record_path")).ends_with(".roads.json"):
			continue
		var resident := "res://src/main/resources/com/openworld/world/pieces/Roads_%s.tscn" % net.name
		if ResourceLoader.exists(resident) and (only == "" or resident.contains(only)):
			_place(resident, (net as Node3D).global_transform, "Probe_resident_" + str(net.name))
	check("the scene placed road geometry", not pieces.is_empty(), "%d piece(s)" % pieces.size())
	if pieces.is_empty():
		_finish()
		return

	# Collect every lane first, so the control can be dropped on known ones.
	var lanes := []      # [Path3D, lane name, piece name]
	for p in pieces:
		if not road_piece.get(p, false):
			continue
		for path3d in p.find_children("*", "Path3D", true, false):
			var cv: Curve3D = path3d.curve
			if cv != null and cv.get_baked_length() >= STEP:
				lanes.append([path3d, str(path3d.get_parent().name), str(p.name)])
	check("the pieces carry exported lanes", lanes.size() > 0, "%d lane(s)" % lanes.size())

	if control:
		# A 1 m post in the middle of every 40th lane -- the obstruction the gate exists to find.
		var i := 0
		while i < lanes.size():
			var path3d: Path3D = lanes[i][0]
			var cv: Curve3D = path3d.curve
			var mid: Vector3 = path3d.global_transform * cv.sample_baked(cv.get_baked_length() * 0.5)
			var b := StaticBody3D.new()
			b.name = "CONTROL_post_%d" % i
			b.collision_layer = 1
			b.collision_mask = 0
			var cs := CollisionShape3D.new()
			var sh := BoxShape3D.new()
			sh.size = Vector3(0.6, 1.0, 0.6)
			cs.shape = sh
			b.add_child(cs)
			root.add_child(b)
			b.global_position = mid + Vector3(0, 0.8, 0)
			controls.append(b)
			i += 40
		print("CONTROL: %d post(s) dropped in lanes" % controls.size())

	# Godot needs a step before a body added this frame answers a query.
	for i in 4:
		await physics_frame

	var space := root.world_3d.direct_space_state
	var bands := [
		{"name": "obstruction", "lo": CLEAR_LOW, "hi": BONNET_HIGH, "fails": true},
		{"name": "headroom", "lo": BONNET_HIGH, "hi": CLEAR_HIGH, "fails": false},
	]
	for b in bands:
		var sh := BoxShape3D.new()
		sh.size = Vector3(CAR_HALF * 2.0, b["hi"] - b["lo"], BOX_LONG)
		var qq := PhysicsShapeQueryParameters3D.new()
		qq.shape = sh
		qq.collision_mask = CAR_MASK
		qq.collide_with_areas = false
		qq.collide_with_bodies = true
		b["q"] = qq
		b["mid"] = (b["lo"] + b["hi"]) * 0.5
		b["blocked"] = {}
		b["by_owner"] = {}

	var t0 := Time.get_ticks_msec()
	var samples := 0
	var control_found := {}
	for row in lanes:
		var path3d: Path3D = row[0]
		var lane: String = row[1]
		var cv: Curve3D = path3d.curve
		var xf := path3d.global_transform
		var total := cv.get_baked_length()
		var d := STEP * 0.5
		while d <= total:
			var here: Vector3 = xf * cv.sample_baked(d)
			var ahead: Vector3 = xf * cv.sample_baked(minf(d + 0.5, total))
			var back: Vector3 = xf * cv.sample_baked(maxf(d - 0.5, 0.0))
			d += STEP
			samples += 1
			var fwd := (ahead - back)
			fwd.y = 0.0
			if fwd.length() < 0.01:
				continue
			fwd = fwd.normalized()
			var basis := Basis(fwd.cross(Vector3.UP).normalized(), Vector3.UP, fwd)
			for b in bands:
				b["q"].transform = Transform3D(basis, here + Vector3(0, b["mid"], 0))
				for h in space.intersect_shape(b["q"], 8):
					var col = h["collider"]
					# The NAME alone is "StaticBody3D" for every baked proxy, so what identifies an owner is
					# its PATH: `.../Roads_island_3_4/chuo_dori_road-colonly/StaticBody3D` names the road and
					# the proxy, `.../Bld_island_7_12/ShopHouse_12/...` names the building.
					var nm := "?"
					if col != null:
						nm = str(root.get_path_to(col)).trim_prefix("Probe_")
					if nm.contains("CONTROL_post"):
						control_found[nm.get_file()] = true
						continue
					b["by_owner"][nm] = int(b["by_owner"].get(nm, 0)) + 1
					if not b["blocked"].has(lane):
						b["blocked"][lane] = []
					if b["blocked"][lane].size() < 3:
						b["blocked"][lane].append("%s @ (%.0f, %.0f, %.0f)" % [nm, here.x, here.y, here.z])

	print("  swept %d sample(s) on %d lane(s) in %d ms" % [samples, lanes.size(), Time.get_ticks_msec() - t0])
	for b in bands:
		var blocked: Dictionary = b["blocked"]
		var by_owner: Dictionary = b["by_owner"]
		var worst := by_owner.keys()
		worst.sort_custom(func(a, c): return by_owner[a] > by_owner[c])
		if not blocked.is_empty():
			print("  %s -- %d lane(s):" % [str(b["name"]).to_upper(), blocked.size()])
			for lane in blocked.keys().slice(0, 14):
				print("    %-40s %s" % [lane, str(blocked[lane])])
			print("    by collider: %s" % str(worst.slice(0, 10).map(func(k): return "%s x%d" % [k, by_owner[k]])))
		if b["fails"]:
			check("no lane is blocked in front of the bumper (%.2f-%.2f m)" % [b["lo"], b["hi"]],
					blocked.is_empty(), "%d lane(s), %d collider(s)" % [blocked.size(), by_owner.size()])
		else:
			print("  INFO  headroom (%.2f-%.2f m): %d lane(s), %d collider(s)"
					% [b["lo"], b["hi"], blocked.size(), by_owner.size()])
	if control:
		# DISTINCT posts, not hits: one post is met by several samples and by both bands, so a count of
		# hits can clear the bar while whole posts went unseen.
		check("CONTROL: every dropped post was found", control_found.size() == controls.size(),
				"%d of %d post(s)" % [control_found.size(), controls.size()])
	_finish()

func _finish() -> void:
	print("RESULT %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
