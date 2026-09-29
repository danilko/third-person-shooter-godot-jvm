extends SceneTree
## Does a real train FIT? (user, 2026-09-29: "the platform seems narrower than the railway's wall ... a real train has
## some width ... generate a Japan rail/metro train and use it on the rail to measure"). The train is EMU1
## (blender/tools/make_train.py: a 20 m, 2.95 m wide-body commuter car, the largest standard 1067 mm car, doors proud to
## 2.98 m), and every number here comes from its `EMU1.train.json`, never a constant.
##
##   godot --headless --path . --script tools/godot/probe_train_fit.gd -- --scene=res://.../Station_Farm_Shop.tscn
##   godot --headless --path . --script tools/godot/probe_train_fit.gd -- --world=island|debug
##
## STAND (`--scene=`, one station scene, or `--stations` for every Station_*_Shop.tscn): a 4-car set stands on EVERY
## track of every lane, centred on the platform, and
##   1. its body (the section swept 19.5 m, doors included), its roof equipment and its bogies touch nothing;
##   2. at every door the platform edge is found by a ray (never read off the layout) and the gap from the car's side at
##      the platform's top to that edge is 0.03-0.20 m (Japan's straight-platform practice is ~0.05-0.10);
##   3. the step from the platform up to the car floor is 0-0.08 m.
## WORLD (`--world=`): every rail and road piece, building cell, site and landmark is instanced where its zone puts it
## (probe_rail_track's way), and a 4-car set is driven along every rail lane, each car on its two BOGIE CENTRES ON THE
## TRACK (so on a curve the body chord overhangs outward at its ends and inward at its middle, as a real car does), every
## 3 m. Its body, roof and bogies must touch nothing; beside the track, what stands nearest the car at 2 m up (a wall,
## a fence, a pier) is reported as the clearance a train actually has.
## `-- --control` widens the car by 0.3 m a side: check 1 must FAIL at the platforms.

const TRAIN := "res://assets/vehicles/trains/EMU1.train.json"
const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const DEBUG_WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const PIECES := "res://assets/world_source/pieces/%s.lanekit.json"
const BUILDINGS := "res://src/main/resources/com/openworld/world/buildings/"
const MASK := 1 | 32           # WORLD + CAR_WALL: what a vehicle collides with
const TRACK_HALF := 2.0        # station_layout.TRACK_HALF: a lane's two tracks
const RAIL_H := 0.16           # the rail head over the bed

var fails := 0
var train: Dictionary
var half_w := 0.0
var widen := 0.0
var body_shape: ConvexPolygonShape3D
var roof_shape: BoxShape3D
var bogie_shape: BoxShape3D
var space: PhysicsDirectSpaceState3D
var holder: Node

func check(label: String, ok: bool, detail := "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-70s %s" % ["PASS" if ok else "FAIL", label, detail])

## The car's body as a convex hull in the CAR's frame (Godot: -Z forward, origin on the rail head at the car centre):
## its section (train.json `profile`, half width over the rail head) swept the body's length, and the doors' proud
## faces (the car's `half_width`) over the door height.
func _shapes() -> void:
	var L := float(train["body_length_m"]) / 2.0
	var pts := PackedVector3Array()
	for p in train["profile"]:
		var x := float(p[0]) + widen
		for zz in [-L, L]:
			pts.append(Vector3(x, float(p[1]), zz))
			pts.append(Vector3(-x, float(p[1]), zz))
	var fl := float(train["floor_m"])
	for zz in [-L + 0.5, L - 0.5]:
		for yy in [fl, fl + 1.85]:
			pts.append(Vector3(half_w + widen, yy, zz))
			pts.append(Vector3(-half_w - widen, yy, zz))
	body_shape = ConvexPolygonShape3D.new()
	body_shape.points = pts
	roof_shape = BoxShape3D.new()
	roof_shape.size = Vector3(1.9, float(train["height_m"]) - 3.6, 2.0 * L - 3.0)
	bogie_shape = BoxShape3D.new()
	bogie_shape.size = Vector3(2.3, 0.55, 3.2)

## What the car at `xf` (its frame: origin on the rail head, -Z forward) touches: ["owner/collider", ...].
func _touches(xf: Transform3D) -> Array:
	var out := []
	var q := PhysicsShapeQueryParameters3D.new()
	q.collision_mask = MASK
	var half := float(train["bogie_centres_m"]) / 2.0
	var parts := [[body_shape, Transform3D.IDENTITY],
			[roof_shape, Transform3D(Basis.IDENTITY, Vector3(0, 3.6 + roof_shape.size.y / 2.0, 0))],
			[bogie_shape, Transform3D(Basis.IDENTITY, Vector3(0, 0.575, -half))],
			[bogie_shape, Transform3D(Basis.IDENTITY, Vector3(0, 0.575, half))]]
	for pr in parts:
		q.shape = pr[0]
		q.transform = xf * pr[1]
		for hit in space.intersect_shape(q, 8):
			var col = hit["collider"]
			var n := col as Node
			while n != null and n.get_parent() != holder and n.get_parent() != null and n.get_parent() != root:
				n = n.get_parent()
			out.append("%s/%s" % [str(n.name) if n != null else "?", str(col.name)])
	return out

## The car's half width at height `h` over the rail head, off the section.
func _half_at(h: float) -> float:
	var prof: Array = train["profile"]
	for i in range(prof.size() - 1):
		var a: Array = prof[i]
		var b: Array = prof[i + 1]
		if h >= float(a[1]) and h <= float(b[1]):
			var t := (h - float(a[1])) / maxf(1e-6, float(b[1]) - float(a[1]))
			return lerpf(float(a[0]), float(b[0]), t) + widen
	return float(prof[0][0]) + widen

func _ray(from: Vector3, to: Vector3) -> Dictionary:
	var q := PhysicsRayQueryParameters3D.create(from, to, MASK)
	return space.intersect_ray(q)

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	train = JSON.parse_string(FileAccess.get_file_as_string(TRAIN))
	half_w = float(train["half_width_m"])
	widen = 0.3 if "--control" in args else 0.0
	_shapes()
	print("probe_train_fit: %s, body %.2f m wide (%.2f over the doors), %.2f m high, bogie centres %.1f m"
			% [train["id"], 2.0 * float(train["profile"][3][0]), 2.0 * half_w, float(train["height_m"]),
			float(train["bogie_centres_m"])])
	var scenes := []
	var world := ""
	for a in args:
		if a.begins_with("--scene="):
			scenes.append(a.substr(8))
		elif a.begins_with("--world="):
			world = a.substr(8)
		elif a == "--stations":
			for f in DirAccess.get_files_at(BUILDINGS):
				if f.begins_with("Station_") and f.ends_with("_Shop.tscn"):
					scenes.append(BUILDINGS + f)
	if world != "":
		await _run_world(world == "debug")
	for s in scenes:
		await _run_stand(s)
	print("RESULT %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)

func _run_stand(path: String) -> void:
	var w := Node3D.new()
	root.add_child(w)
	holder = w
	var sc: Node3D = (load(path) as PackedScene).instantiate()
	w.add_child(sc)
	await physics_frame
	await physics_frame
	space = w.get_world_3d().direct_space_state
	var st: Dictionary = sc.get_meta("building")["station"]
	var ptop := float(st["platform_top"])            # over the bed; the rail head is RAIL_H over it
	var coupled := float(train["coupled_length_m"])
	var ncars := 4
	var bad_touch := {}
	var gaps := []
	var steps := []
	var bad_gap := []
	for ln in st["lanes"]:
		for tsg in [-1.0, 1.0]:
			var tz: float = -(float(ln[1]) + tsg * TRACK_HALF)          # the track's Godot z in the station frame
			for k in ncars:
				var cx := (float(k) - (ncars - 1) / 2.0) * coupled
				# the car faces +X along the axis: its -Z onto +X is a yaw of -90 deg
				var xf := Transform3D(Basis(Vector3.UP, -PI / 2.0), Vector3(cx, RAIL_H, tz))
				for t in _touches(xf):
					bad_touch[t] = "%s track z %.2f car %d" % [ln[0], tz, k]
				# the platform edge at each door, both sides: a horizontal ray from the track's centre just under
				# the platform's top
				for dy in train["door_y_m"]:
					var x := cx + float(dy)
					for side in [-1.0, 1.0]:
						var y := ptop - 0.03
						var hit := _ray(Vector3(x, y, tz), Vector3(x, y, tz + side * 2.5))
						if hit.is_empty():
							continue
						var d := absf((hit["position"] as Vector3).z - tz)
						var gap := d - _half_at(ptop - RAIL_H)
						gaps.append(gap)
						# the platform's top there, against the car floor
						var top := _ray(Vector3(x, ptop + 1.0, tz + side * (d + 0.3)),
								Vector3(x, ptop - 1.0, tz + side * (d + 0.3)))
						if not top.is_empty():
							steps.append(RAIL_H + float(train["floor_m"]) - (top["position"] as Vector3).y)
						if gap < 0.03 or gap > 0.20:
							bad_gap.append("%s z %.2f door x %.1f: %.3f" % [ln[0], tz, x, gap])
	var name := str(st["name"])
	var tl := []
	for k in bad_touch:
		tl.append("%s (%s)" % [k, bad_touch[k]])
		print("    touches: %s  %s" % [k, bad_touch[k]])
	check("%s: a 4-car EMU1 on every track touches nothing" % name, bad_touch.is_empty(), str(tl.slice(0, 3)))
	var gmin := 99.0
	var gmax := -99.0
	for g in gaps:
		gmin = minf(gmin, g)
		gmax = maxf(gmax, g)
	check("%s: platform gap at every door 0.03-0.20 m" % name, not gaps.is_empty() and bad_gap.is_empty(),
			"%d door(s), gap %.3f..%.3f m %s" % [gaps.size(), gmin, gmax, str(bad_gap.slice(0, 3))])
	var smin := 99.0
	var smax := -99.0
	for s in steps:
		smin = minf(smin, s)
		smax = maxf(smax, s)
	check("%s: step from the platform up to the car floor 0-0.08 m" % name,
			not steps.is_empty() and smin >= -0.01 and smax <= 0.08, "%.3f..%.3f m" % [smin, smax])
	w.queue_free()
	await process_frame

func _collect(n: Node, script_end: String, out: Array) -> void:
	var s = n.get_script()
	if s != null and str(s.resource_path).ends_with(script_end):
		out.append(n)
	for c in n.get_children():
		_collect(c, script_end, out)

func _run_world(debug: bool) -> void:
	var rail_prefix := "Roads_DebugRail_" if debug else "Roads_IslandRail_"
	var rail_node := "DebugRail" if debug else "IslandRail"
	var w: Node3D = (load(DEBUG_WORLD if debug else WORLD) as PackedScene).instantiate()
	var markers := []
	_collect(w, "ZoneMarker.java", markers)
	var pieces := []
	var rail_pieces := []
	for m in markers:
		var z = m.get("zone")
		if z == null:
			continue
		var gp := str(z.get("geometry_path"))
		if gp == "" or gp == "<null>" or not ResourceLoader.exists(gp):
			continue
		var xf: Transform3D = z.get("geometry_world_transform") if z.get("geometry_world_placed") else (m as Node3D).global_transform
		pieces.append([gp, xf])
		if gp.get_file().begins_with(rail_prefix):
			rail_pieces.append(gp)
	for m in markers:
		m.get_parent().remove_child(m)
		m.free()
	root.add_child(w)
	await process_frame
	holder = Node3D.new()
	w.add_child(holder)
	for pr in pieces:
		var n := (load(pr[0]) as PackedScene).instantiate() as Node3D
		holder.add_child(n)
		n.global_transform = pr[1]
	for i in 3:
		await physics_frame
	space = w.get_world_3d().direct_space_state
	var rail_y := 0.0
	var rn := w.find_child(rail_node, true, false) as Node3D
	if rn != null:
		rail_y = rn.global_position.y
	var lanes := []
	for gp in rail_pieces:
		var doc = JSON.parse_string(FileAccess.get_file_as_string(PIECES % str(gp).get_file().get_basename()))
		for l in doc["lanes"]:
			if str(l.get("road_class", "")) == "rail":
				lanes.append(l)
	print("probe_train_fit: %d piece(s), %d rail lane(s)" % [pieces.size(), lanes.size()])
	check("the world has rail lanes to run the train on", not lanes.is_empty())
	var bc := float(train["bogie_centres_m"])
	var touch := {}
	var samples := 0
	var side_min := 99.0
	var side_at := ""
	for l in lanes:
		var pts := []
		for p in l["points"]:
			pts.append(Vector3(float(p[0]), float(p[1]) + rail_y + RAIL_H, float(p[2])))
		var cum := [0.0]
		for i in range(1, pts.size()):
			cum.append(float(cum[-1]) + (pts[i] as Vector3).distance_to(pts[i - 1]))
		var total: float = cum[-1]
		var s := 0.0
		while s + bc <= total:
			var a := _at(pts, cum, s)
			var b := _at(pts, cum, s + bc)
			var mid := (a + b) * 0.5
			var fwd := b - a
			fwd.y = 0.0
			if fwd.length() > 0.1:
				# the car's -Z along the chord from its rear bogie to its front bogie
				var xf := Transform3D(Basis(Vector3.UP, atan2(-fwd.x, -fwd.z)), mid)
				samples += 1
				for t in _touches(xf):
					if not touch.has(t):
						touch[t] = "%s @ (%.0f, %.1f, %.0f)" % [l["id"], mid.x, mid.y, mid.z]
				# the nearest thing beside the car at 2 m up (a wall, a fence, a pier), off both sides
				var side := xf.basis.x.normalized()
				for sg in [-1.0, 1.0]:
					var o := mid + Vector3(0, 2.0, 0)
					var hit := _ray(o, o + side * sg * 6.0)
					if not hit.is_empty():
						var d := o.distance_to(hit["position"]) - half_w
						if d < side_min:
							side_min = d
							side_at = "%s @ (%.0f, %.0f) %s" % [l["id"], mid.x, mid.z, str(hit["collider"].name)]
			s += 3.0
	var tl := []
	for k in touch:
		tl.append("%s [%s]" % [k, touch[k]])
		print("    touches: %s  first at %s" % [k, touch[k]])
	check("a 4-car EMU1 run along every track (bogies on the rails) touches nothing", samples > 0 and touch.is_empty(),
			"%d car position(s), %d collider(s) %s" % [samples, touch.size(), str(tl.slice(0, 3))])
	print("  INFO  nearest thing beside the car at 2 m up: %.2f m past its side (%s)" % [side_min, side_at])
	w.queue_free()
	await process_frame

func _at(pts: Array, cum: Array, s: float) -> Vector3:
	for i in range(1, pts.size()):
		if float(cum[i]) >= s:
			var t := (s - float(cum[i - 1])) / maxf(1e-6, float(cum[i]) - float(cum[i - 1]))
			return (pts[i - 1] as Vector3).lerp(pts[i], t)
	return pts[-1]
