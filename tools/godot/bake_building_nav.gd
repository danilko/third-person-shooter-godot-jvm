extends SceneTree
## A NAVMESH PER ENTERABLE BUILDING TYPE? -- the measurement (PLAN.md 1d review, user 2026-10-07: "use a navmesh if
## its performance allows, else waypoints"). For each building scene given, bakes a NavigationMesh from the scene's
## own static colliders (plus a flat apron round the footprint, so the door's outside is on it) and reports what a
## shipped per-type bake would cost: bake time, polygon / vertex count, the saved resource's size, whether every
## Door_* marker's inside point is ON the mesh, and the cost of a path query across it.
##
##   godot --headless --path . --script tools/godot/bake_building_nav.gd -- --scenes=KonbiniL_Shop,PoliceStation_Shop
##       [--cell=0.1] [--radius=0.3] [--height=1.8] [--save=<dir>]   (--save writes <Type>_nav.res there, for the runtime test)
##   ... -- --all --write   THE BUILD STEP: every enterable type (a _Shop or _Open scene) baked from its _Shop
##                          variant (else _Open) into buildings/nav/<Type>_nav.res, which world.InteriorNav loads.
##                          Re-run after build_building_scenes.gd changes a building.

const BUILDINGS := "res://src/main/resources/com/openworld/world/buildings/"
const APRON := 1.0


func _arg(n: String, d: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--" + n + "="):
			return a.substr(n.length() + 3)
	return d


func _initialize() -> void:
	var cell := float(_arg("cell", "0.1"))   # = InteriorNav.CELL; 0.175 closed the station gate lanes (2026-10-08)
	var radius := float(_arg("radius", "0.3"))   # a 0.35 capsule passes a 0.7 m lane; 0.35 here erodes it shut
	var save := _arg("save", "")
	var names := _arg("scenes", "KonbiniS_Shop,KonbiniL_Shop").split(",")
	var write := "--write" in OS.get_cmdline_user_args()
	if "--all" in OS.get_cmdline_user_args():
		var bases := {}
		for f in DirAccess.get_files_at(BUILDINGS):
			if f.ends_with("_Shop.tscn") or f.ends_with("_Open.tscn"):
				var base := f.substr(0, f.length() - 10)
				if f.ends_with("_Shop.tscn") or not bases.has(base):
					bases[base] = f.substr(0, f.length() - 5)
		names = PackedStringArray(bases.values())
		names.sort()
	if write:
		save = BUILDINGS + "nav"
		DirAccess.make_dir_recursive_absolute(save)
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	await process_frame
	print("bake_building_nav: cell %.2f m, agent radius %.2f m" % [cell, radius])
	for nm in names:
		var path := BUILDINGS + nm + ".tscn"
		if not ResourceLoader.exists(path):
			print("  %s: no scene" % nm)
			continue
		var b: Node3D = (load(path) as PackedScene).instantiate()
		# a door (and a ticket gate) opens for whoever walks into it: its leaves are not walls for a path
		var leaves := 0
		for n in b.find_children("*", "", true, false):
			if not is_instance_valid(n):
				continue
			var sc = n.get_script()
			if sc != null and (str(sc.resource_path).ends_with("/Door.java") or str(sc.resource_path).ends_with("/TicketGate.java")):
				n.get_parent().remove_child(n)
				n.free()
				leaves += 1
		world.add_child(b)
		await physics_frame
		# the footprint: every collision shape's box, in the building's frame
		var lo := Vector3(1e9, 1e9, 1e9)
		var hi := -lo
		for cs in b.find_children("*", "CollisionShape3D", true, false):
			var sh: Shape3D = (cs as CollisionShape3D).shape
			if sh == null:
				continue
			var ab: AABB = sh.get_debug_mesh().get_aabb()
			var t: Transform3D = b.global_transform.affine_inverse() * (cs as Node3D).global_transform
			for i in 8:
				var p: Vector3 = t * ab.get_endpoint(i)
				lo = lo.min(p)
				hi = hi.max(p)
		var apron := StaticBody3D.new()
		var acs := CollisionShape3D.new()
		var box := BoxShape3D.new()
		box.size = Vector3(hi.x - lo.x + 2 * APRON, 0.1, hi.z - lo.z + 2 * APRON)
		acs.shape = box
		apron.add_child(acs)
		# the apron is the STREET round the building. A station's origin is its track bed (an elevated hub's street is
		# 7.84 m below it, a ground hub's entry stairs come down to its street), so there the street is the lowest
		# collider; an apron left at the origin cut every elevated stairwell with a floor in mid-air (2026-10-08:
		# Central's platforms and concourse were separate navmesh islands)
		var street_y := _street_y(b, lo, hi) if nm.begins_with("Station_") else 0.0
		apron.position = Vector3((lo.x + hi.x) * 0.5, street_y - 0.07, (lo.z + hi.z) * 0.5)
		b.add_child(apron)
		await physics_frame
		var nm_res := NavigationMesh.new()
		nm_res.geometry_parsed_geometry_type = NavigationMesh.PARSED_GEOMETRY_STATIC_COLLIDERS
		nm_res.cell_size = cell
		nm_res.cell_height = 0.1
		nm_res.agent_radius = radius
		nm_res.agent_height = float(_arg("height", "1.8"))
		nm_res.agent_max_climb = 0.5
		nm_res.agent_max_slope = 46.0
		nm_res.filter_baking_aabb = AABB(lo - Vector3(APRON, 1, APRON), (hi - lo) + Vector3(2 * APRON, 2, 2 * APRON))
		var src := NavigationMeshSourceGeometryData3D.new()
		var t0 := Time.get_ticks_usec()
		NavigationServer3D.parse_source_geometry_data(nm_res, src, b)
		NavigationServer3D.bake_from_source_geometry_data(nm_res, src)
		var bake_ms := (Time.get_ticks_usec() - t0) / 1000.0
		var polys := nm_res.get_polygon_count()
		if "--verbose" in OS.get_cmdline_user_args():
			var ys := {}
			for v in nm_res.get_vertices():
				ys[snappedf(v.y, 0.5)] = ys.get(snappedf(v.y, 0.5), 0) + 1
			print("    vertex heights (0.5 m bins): %s; bake box %s" % [ys, nm_res.filter_baking_aabb])
		var verts := nm_res.get_vertices().size()
		var size_kb := 0.0
		if save != "":
			DirAccess.make_dir_recursive_absolute(save)
			var out := save.path_join((nm.substr(0, nm.length() - 5) if write else nm) + "_nav.res")
			ResourceSaver.save(nm_res, out, ResourceSaver.FLAG_COMPRESS)
			size_kb = FileAccess.get_file_as_bytes(out).size() / 1024.0
		else:
			var tmp := "user://_nav_probe.res"
			ResourceSaver.save(nm_res, tmp, ResourceSaver.FLAG_COMPRESS)
			size_kb = FileAccess.get_file_as_bytes(tmp).size() / 1024.0
		# a region on its own map: are the doors on it, and what does a path cost?
		# the WORLD's own map (cell 0.5, the project default), which is what the game would add these regions to
		var map: RID = world.get_world_3d().navigation_map
		var it0 := NavigationServer3D.map_get_iteration_id(map)
		# as the game would carry it: a NavigationRegion3D child of the building
		var region := NavigationRegion3D.new()
		region.navigation_mesh = nm_res
		var tadd := Time.get_ticks_usec()
		b.add_child(region)
		var add_ms := (Time.get_ticks_usec() - tadd) / 1000.0
		var t1 := Time.get_ticks_usec()
		var waited := 0
		while NavigationServer3D.map_get_iteration_id(map) == it0 and waited < 120:
			await physics_frame
			waited += 1
		var sync_ms := (Time.get_ticks_usec() - t1) / 1000.0   # wall time to the next sync: frames waited, an upper bound
		for k in 10:
			await physics_frame
		if "--verbose" in OS.get_cmdline_user_args():
			print("    map regions %d, active %s, iteration %d (waited %d), region polys %d, region map %s vs %s" % [
				NavigationServer3D.map_get_regions(map).size(), NavigationServer3D.map_is_active(map),
				NavigationServer3D.map_get_iteration_id(map), waited, nm_res.get_polygon_count(), region.get_navigation_map(), map])
		var doors := 0
		var on := 0
		var inside_pts: Array[Vector3] = []
		for d in b.find_children("Door_*", "Node3D", false, false):
			doors += 1
			var dn := d as Node3D
			var o := -dn.global_transform.basis.z
			o.y = 0
			o = o.normalized() if o.length() > 1e-3 else Vector3(0, 0, 1)
			var ins := dn.global_position - o * 2.5
			var snap := NavigationServer3D.map_get_closest_point(map, ins)
			if "--verbose" in OS.get_cmdline_user_args():
				print("    door %s at %s inside %s -> snap %s" % [dn.name, dn.global_position, ins, snap])
			if snap.distance_to(Vector3(ins.x, snap.y, ins.z)) < 0.6:
				on += 1
				inside_pts.append(snap)
		# path queries: from each inside point to 40 random reachable points on the mesh
		var q := 0
		var reached := 0
		var tq := 0
		var rng := RandomNumberGenerator.new()
		rng.seed = 7
		for s in inside_pts:
			for k in 40:
				var g := NavigationServer3D.map_get_random_point(map, 1, false)
				var tries := 0
				while absf(g.y - s.y) > 0.8 and tries < 30:   # same floor as the door (not a roof, not an upper storey)
					g = NavigationServer3D.map_get_random_point(map, 1, false)
					tries += 1
				var t2 := Time.get_ticks_usec()
				var pth := NavigationServer3D.map_get_path(map, s, g, true)
				tq += Time.get_ticks_usec() - t2
				q += 1
				if pth.size() > 0 and pth[pth.size() - 1].distance_to(g) < 0.5:
					reached += 1
		print("  %-26s footprint %5.1f x %5.1f m | bake %7.1f ms | %5d polys %6d verts | %6.1f KB | add %.2f ms, synced after %5.2f ms | doors on mesh %d/%d | paths %d/%d, %.1f us each" % [
			nm + " (-%d doors)" % leaves, hi.x - lo.x, hi.z - lo.z, bake_ms, polys, verts, size_kb, add_ms, sync_ms, on, doors, reached, q,
			float(tq) / maxf(1.0, q)])
		b.queue_free()
		await process_frame
	quit(0)


## A station's street height: bake it once with no apron and take the lowest walkable floor within EDGE m of the
## footprint's edge -- an entrance floor (an elevated hub's F1 hall, a ground hub's entry stair foot) reaches the edge;
## a plinth or a foundation is not walkable, so the lowest COLLIDER is not the street (it read 1.6 m low at Central).
const EDGE := 1.5
func _street_y(b: Node3D, lo: Vector3, hi: Vector3) -> float:
	var nm_res := NavigationMesh.new()
	nm_res.geometry_parsed_geometry_type = NavigationMesh.PARSED_GEOMETRY_STATIC_COLLIDERS
	nm_res.cell_size = 0.25
	nm_res.cell_height = 0.1
	nm_res.agent_radius = 0.35
	nm_res.agent_height = 1.8
	nm_res.agent_max_climb = 0.5
	nm_res.filter_baking_aabb = AABB(lo - Vector3(1, 1, 1), (hi - lo) + Vector3(2, 2, 2))
	var src := NavigationMeshSourceGeometryData3D.new()
	NavigationServer3D.parse_source_geometry_data(nm_res, src, b)
	NavigationServer3D.bake_from_source_geometry_data(nm_res, src)
	var best := INF
	for v in nm_res.get_vertices():
		var edge := minf(minf(v.x - lo.x, hi.x - v.x), minf(v.z - lo.z, hi.z - v.z))
		if edge < EDGE + 0.4:
			best = minf(best, v.y)
	return 0.0 if best == INF else best - 0.1   # a navmesh vertex sits a cell over its floor

