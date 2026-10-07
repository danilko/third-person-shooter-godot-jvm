extends SceneTree
## UNITS FOLLOW THE PLAYER INTO A BUILDING (PLAN.md W6, user 2026-10-06: "they stop at the konbini and wait outside").
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_breach.gd [-- --stars=N] [--control]
##   [--place="Police Station"] [--deep=8] [--inner] [--secs=90] [--no-stop] [--no-interior-nav]
##   (--stars=N held for the run; --control: EnforcementDispatch.breaching off -- nobody plans a way in. User 2026-10-06:
##   units always get in, at every star level. --place: the place nearest the safe house of that name, the player put
##   --deep metres in from its door along the door->centre line; --no-stop runs the whole --secs and reports the REACH:
##   how many distinct units came within 3 m of the player, and when the first did -- the PLAN.md 1d pathing measure.)
##
## World.tscn, the player invulnerable, standing 3 m inside the convenience store nearest the safe house, held at N
## stars for up to 90 s (lethal from 3). Asserted: units plan a route through the store's door, at least one gets
## IN (the dispatch's count, and a live police body under the same roof within 15 m of the player).

const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"
const PLACES := "res://src/main/resources/com/openworld/world/places/World.places.json"

var fails := 0


func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var control := "--control" in args
	var stars := 1
	var place := "Convenience Store"
	var deep := 3.0
	var secs := 90.0
	var no_stop := "--no-stop" in args
	for a in args:
		if a.begins_with("--stars="):
			stars = int(a.substr(8))
		elif a.begins_with("--place="):
			place = a.substr(8)
		elif a.begins_with("--deep="):
			deep = float(a.substr(7))
		elif a.begins_with("--secs="):
			secs = float(a.substr(7))
	var doc: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(PLACES))
	var home := Vector3.ZERO
	for pl in doc["places"]:
		if pl["name"] == "Safehouse":
			home = Vector3(pl["at"][0], pl["at"][1], pl["at"][2])
	var shop: Dictionary = {}
	var bd := 1e9
	for pl in doc["places"]:
		if pl["name"] == place:
			var d := Vector3(pl["at"][0], pl["at"][1], pl["at"][2]).distance_to(home)
			if d < bd:
				bd = d
				shop = pl
	var at := Vector3(shop["at"][0], shop["at"][1], shop["at"][2])
	var go := Vector3(shop["go"][0], shop["go"][1], shop["go"][2])
	var inside := go + (at - go).normalized() * deep
	var world: Node = (load(ISLAND) as PackedScene).instantiate()
	var pz := world.get_node_or_null("PedZones")
	if pz != null:
		world.remove_child(pz)
		pz.free()
	var player: Node3D = world.get_node("Characters/Player")
	player.position = inside + Vector3(0, 0.3, 0)
	root.add_child(world)
	current_scene = world
	player.get_node("Health").set("invulnerable", true)
	for i in 300:
		await physics_frame
	# a compound (a police station, a hospital) has its place point in the yard: stand the player INSIDE the building,
	# --deep metres in from the nearest Door_* marker of the nearest enterable building (its scene ends _Shop/_Open)
	var best_b: Node3D = null
	var bb := 1e9
	for n in world.find_children("*", "Node3D", true, false):
		if not n.has_meta("building"):
			continue
		var sp := str(n.scene_file_path)
		if not (sp.ends_with("_Shop.tscn") or sp.ends_with("_Open.tscn")):
			continue
		var d := (n as Node3D).global_position.distance_to(at)
		if d < bb:
			bb = d
			best_b = n
	if best_b != null and bb < 60.0:
		var door: Node3D = null
		var dd := 1e9
		for c in best_b.get_children():
			if str(c.name).begins_with("Door_") and (c as Node3D).global_position.distance_to(go) < dd:
				dd = (c as Node3D).global_position.distance_to(go)
				door = c
		var meta: Dictionary = best_b.get_meta("building")
		if "--inner" in args and meta.has("inner_doors") and (meta["inner_doors"] as Array).size() > 0:
			# a room deep inside: beside an interior doorway (inside the building by definition), the one furthest
			# from the street door
			var far_c := Vector3.ZERO
			var far_d := -1.0
			for idr in meta["inner_doors"]:
				var c: Array = idr["center"]
				var w := best_b.global_transform * Vector3(c[0], 0.0, c[2])
				var dg := w.distance_to(go)
				if dg > far_d and absf(float(c[1])) < 0.5:
					far_d = dg
					far_c = w
			if far_d >= 0.0:
				player.global_position = far_c + Vector3(1.0, 0.3, 0.0)
				player.get_node("MovementController").call("clear_motion")
				print("probe_breach: inside %s, beside an interior doorway %.0f m from the street door" % [best_b.name, far_d])
				for i in 60:
					await physics_frame
				door = null
		if door != null:
			var o := -door.global_transform.basis.z
			o.y = 0
			o = o.normalized()
			inside = door.global_position - o * deep
			player.global_position = inside + Vector3(0, 0.3, 0)
			player.get_node("MovementController").call("clear_motion")
			print("probe_breach: inside %s, %.0f m in from %s" % [best_b.name, deep, door.name])
			for i in 60:
				await physics_frame
	var gm: Node = root.get_node("GameManager")
	var ws: Node = gm.get_node("WantedSystem")
	var ed: Node = gm.get_node("EnforcementDispatch")
	var pid: String = player.get("character_info").get("character_id")
	if control:
		ed.set("breaching", false)
	if "--no-interior-nav" in args:
		ed.set("interior_nav", false)
		for r in world.find_children("InteriorNav", "NavigationRegion3D", true, false):
			r.queue_free()
	var roof := (world as Node3D).get_world_3d().direct_space_state.intersect_ray(PhysicsRayQueryParameters3D.create(player.global_position + Vector3(0, 1.7, 0), player.global_position + Vector3(0, 25, 0), 1))
	print("probe_breach: a roof over the player: %s" % ("yes, " + str((roof["collider"] as Node).get_path()) if not roof.is_empty() else "NO (outdoors: nothing to breach)"))
	print("probe_breach: player in the store at %s (%.0f m from the safe house), %d stars" % [player.global_position, bd, stars])
	var routes := 0
	var inn := 0
	var forced := 0
	var nearest_in := 1e9
	var t0 := Time.get_ticks_msec()
	var space := (world as Node3D).get_world_3d().direct_space_state
	var reached := {}
	var first_reach := -1.0
	var phys_ms := 0.0
	var phys_n := 0
	while Time.get_ticks_msec() - t0 < (45000 if control else int(secs * 1000.0)):
		ws.call("set_stars_now", pid, stars, stars >= 3)
		await physics_frame
		if Engine.get_physics_frames() % 20 != 0:
			continue
		var e := String(ed.call("escalation_now")).split(";")
		routes = maxi(routes, int(e[7]))
		inn = maxi(inn, int(e[8]))
		forced = maxi(forced, int(e[9]))
		if "--verbose" in args and Engine.get_physics_frames() % 600 == 0:
			print("  t=%.0f %s" % [(Time.get_ticks_msec() - t0) / 1000.0, String(ed.call("debug_units_now"))])
		phys_ms += Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0
		phys_n += 1
		for b in ed.call("bodies_now", "police"):
			var bp: Vector3 = (b as Node3D).global_position
			var d := bp.distance_to(player.global_position)
			if d < 3.0 and absf(bp.y - player.global_position.y) < 1.5:
				reached[(b as Node).get_instance_id()] = true
				if first_reach < 0.0:
					first_reach = (Time.get_ticks_msec() - t0) / 1000.0
			if d > 15.0:
				continue
			var q := PhysicsRayQueryParameters3D.create(bp + Vector3(0, 1.7, 0), bp + Vector3(0, 25, 0), 1)
			var hit := space.intersect_ray(q)
			if not hit.is_empty():
				nearest_in = minf(nearest_in, d)
		if not control and not no_stop and inn > 0 and nearest_in < 15.0:
			break
	print("probe_breach: readout '%s', nearest officer indoors %.1f m" % [String(ed.call("escalation_now")), nearest_in])
	print("probe_breach: REACH %s deep %.0f m: %d unit(s) came within 3 m, first at %.1f s; units now %s; physics %.2f ms/frame avg" % [
		place, deep, reached.size(), first_reach, String(ed.call("units_now")), phys_ms / maxf(1.0, phys_n)])
	print("probe_breach: interior nav (units switched onto it, regions attached) %s" % String(ed.call("interior_nav_now")))
	if control:
		_check(routes == 0, "with breaching off nobody plans a way in (%d routes)" % routes)
	else:
		_check(routes > 0, "units plan a route through the store's door (%d)" % routes)
		_check(inn > 0 or reached.size() > 0, "a unit gets IN (%d through the door, %d reached the player)" % [inn, reached.size()])
		_check(nearest_in < 15.0, "an officer stands under the store's roof near the player (%.1f m)" % nearest_in)
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
