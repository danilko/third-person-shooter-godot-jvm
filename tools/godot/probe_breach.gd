extends SceneTree
## UNITS FOLLOW THE PLAYER INTO A BUILDING (PLAN.md W6, user 2026-10-06: "they stop at the konbini and wait outside").
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_breach.gd [-- --stars=N] [--control]
##   (default 1 star: police come in to ARREST; --stars=4: armed, lethal. --control: EnforcementDispatch.breaching off
##   -- nobody plans a way in. User 2026-10-06: units always get in, at every star level.)
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
	for a in args:
		if a.begins_with("--stars="):
			stars = int(a.substr(8))
	var doc: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(PLACES))
	var home := Vector3.ZERO
	for pl in doc["places"]:
		if pl["name"] == "Safehouse":
			home = Vector3(pl["at"][0], pl["at"][1], pl["at"][2])
	var shop: Dictionary = {}
	var bd := 1e9
	for pl in doc["places"]:
		if pl["name"] == "Convenience Store":
			var d := Vector3(pl["at"][0], pl["at"][1], pl["at"][2]).distance_to(home)
			if d < bd:
				bd = d
				shop = pl
	var at := Vector3(shop["at"][0], shop["at"][1], shop["at"][2])
	var go := Vector3(shop["go"][0], shop["go"][1], shop["go"][2])
	var inside := go + (at - go).normalized() * 3.0
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
	var gm: Node = root.get_node("GameManager")
	var ws: Node = gm.get_node("WantedSystem")
	var ed: Node = gm.get_node("EnforcementDispatch")
	var pid: String = player.get("character_info").get("character_id")
	if control:
		ed.set("breaching", false)
	print("probe_breach: player in the store at %s (%.0f m from the safe house), %d stars" % [player.global_position, bd, stars])
	var routes := 0
	var inn := 0
	var forced := 0
	var nearest_in := 1e9
	var t0 := Time.get_ticks_msec()
	var space := (world as Node3D).get_world_3d().direct_space_state
	while Time.get_ticks_msec() - t0 < (45000 if control else 90000):
		ws.call("set_stars_now", pid, stars, stars >= 3)
		await physics_frame
		if Engine.get_physics_frames() % 20 != 0:
			continue
		var e := String(ed.call("escalation_now")).split(";")
		routes = maxi(routes, int(e[7]))
		inn = maxi(inn, int(e[8]))
		forced = maxi(forced, int(e[9]))
		for b in ed.call("bodies_now", "police"):
			var bp: Vector3 = (b as Node3D).global_position
			var d := bp.distance_to(player.global_position)
			if d > 15.0:
				continue
			var q := PhysicsRayQueryParameters3D.create(bp + Vector3(0, 1.7, 0), bp + Vector3(0, 25, 0), 1)
			var hit := space.intersect_ray(q)
			if not hit.is_empty():
				nearest_in = minf(nearest_in, d)
		if not control and inn > 0 and nearest_in < 15.0:
			break
	print("probe_breach: readout '%s', nearest officer indoors %.1f m" % [String(ed.call("escalation_now")), nearest_in])
	if control:
		_check(routes == 0, "with breaching off nobody plans a way in (%d routes)" % routes)
	else:
		_check(routes > 0, "units plan a route through the store's door (%d)" % routes)
		_check(inn > 0, "a unit gets IN (%d)" % inn)
		_check(nearest_in < 15.0, "an officer stands under the store's roof near the player (%.1f m)" % nearest_in)
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
