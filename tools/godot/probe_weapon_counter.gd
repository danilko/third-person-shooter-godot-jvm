extends SceneTree
## The safe-house start and the weapon counter (user, 2026-09-22), on the real World.tscn.
##   stdbuf -oL <godot> --headless --path . --script tools/godot/probe_weapon_counter.gd
##
##   1. the scene has a PlayerSpawn, and the Player starts on it, standing, by the safe house's door
##      (the map's own "Safehouse" place, so the check reads the record, not the spawn it is checking);
##   2. the counter has one pad per weapon and every pad names a catalog weapon;
##   3. stepping onto a pad puts that weapon in the inventory, once;
##   4. standing on it hands nothing more;
##   5. stepping off and back after the cooldown REFILLS the weapon instead of adding a second one.

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const PLACES := "res://src/main/resources/com/openworld/world/places/World.places.json"
var fails := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-60s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _weapons_under(n: Node, id: String, out: Array) -> void:
	if n.get("weapon_id") != null and String(n.get("weapon_id")) == id and not (n is Area3D):
		out.append(n)
	for c in n.get_children():
		_weapons_under(c, id, out)

func _pad_holders(n: Node) -> Array:
	var out: Array = []
	for c in n.get_children():
		if str(c.name).begins_with("Pads_") and c.get_child_count() > 0:
			out.append(c)
		else:
			out.append_array(_pad_holders(c))
	return out

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var w: Node = (load(WORLD) as PackedScene).instantiate()
	root.add_child(w)
	current_scene = w
	await process_frame
	var zm := root.get_node_or_null("/root/ZoneManager")
	if zm != null:
		zm.set("debug_log", false)
	var spawn := w.get_node_or_null("PlayerSpawn") as Node3D
	var p := w.get_node_or_null("Characters/Player") as CharacterBody3D
	_check("World.tscn has a PlayerSpawn and a Player", spawn != null and p != null)
	if spawn == null or p == null:
		print("RESULT FAIL")
		quit(1)
		return
	p.get_node("Health").set("max_health", 1000000.0)
	var home := Vector3.INF
	var places: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(PLACES))
	for pl in places["places"]:
		if pl["name"] == "Safehouse":
			home = Vector3(pl["go"][0], pl["go"][1], pl["go"][2])
	var d0 := Vector2(p.global_position.x - spawn.global_position.x, p.global_position.z - spawn.global_position.z).length()
	_check("the Player starts on PlayerSpawn", d0 < 0.1, "%.2f m" % d0)
	var dh := Vector2(spawn.global_position.x - home.x, spawn.global_position.z - home.z).length()
	_check("PlayerSpawn is at the safe house's door", dh < 3.0, "%.2f m from the Safehouse place" % dh)
	var car := w.get_node_or_null("VehicleRoot") as RigidBody3D
	var car0 := car.global_position if car != null else Vector3.ZERO
	await _tick(240)
	if car != null:
		var moved := Vector2(car.global_position.x - car0.x, car.global_position.z - car0.z).length()
		# on the ground beside the player (the plain stands at 5.6 m since the land raise: not an absolute height)
		_check("the starting car rests where it was parked (off the street)", moved < 0.5 and car.global_position.y > 0.3 \
				and absf(car.global_position.y - p.global_position.y) < 2.0 and car.linear_velocity.length() < 0.5,
				"moved %.2f m, y %.2f, %.2f m/s" % [moved, car.global_position.y, car.linear_velocity.length()])
	_check("the player stands there (on the ground, not fallen)", p.is_on_floor() and p.global_position.y > 0.3,
			"y %.2f, on floor %s" % [p.global_position.y, p.is_on_floor()])

	# every konbini sells weapons (user, 2026-09-26): the store beside the safe house carries its pads in its own
	# streamed cell like every other konbini, so the "counter" is the Pads_ holder nearest the spawn
	var counter: Node = null
	var best := 1e9
	for h in _pad_holders(w):
		var d := spawn.global_position.distance_to((h.get_child(0) as Node3D).global_position)
		if d < best:
			best = d
			counter = h
	var pads: Array = counter.get_children() if counter != null else []
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://src/main/resources/com/openworld/weapon/weapon_catalog.json"))
	var ids := {}
	for r in catalog["weapons"]:
		ids[r["id"]] = true
	var ok := pads.size() >= 10
	var seen := {}
	for pad in pads:
		var id := String(pad.get("weapon_id"))
		ok = ok and ids.has(id) and not seen.has(id)
		seen[id] = true
	_check("the konbini beside the safe house sells every weapon, one pad each", ok and best < 80.0,
			"%d pads, %.0f m from the spawn" % [pads.size(), best])

	var pad := counter.get_node_or_null("Pad_ASR1") as Area3D
	# stand on the pad (the shop's cell has had four seconds to stream in under the player's feet)
	p.global_position = pad.global_position + Vector3(0, 0.3, 0)
	p.velocity = Vector3.ZERO
	await _tick(30)
	var got: Array = []
	_weapons_under(p, "ASR1", got)
	_check("stepping onto the ASR1 pad puts an ASR1 in the inventory", got.size() == 1 and int(pad.call("grants_now")) == 1,
			"%d ASR1 on the body, %d grants" % [got.size(), int(pad.call("grants_now"))])
	await _tick(90)
	_check("standing on it hands nothing more", int(pad.call("grants_now")) == 1, "%d grants" % int(pad.call("grants_now")))
	if got.size() == 1:
		got[0].set("magazine", 0)
		got[0].set("reserve", 0)
	# step OFF: out to the spawn point in the street (a fixed sideways step can land against a shelf or a wall,
	# depending on which store is the counter, and then the player never leaves the pad)
	p.global_position = spawn.global_position + Vector3(0, 0.3, 0)
	await _tick(160)
	p.global_position = pad.global_position + Vector3(0, 0.3, 0)
	await _tick(30)
	var again: Array = []
	_weapons_under(p, "ASR1", again)
	var full: bool = got.size() == 1 and int(got[0].get("magazine")) == int(got[0].get("magazine_size")) \
			and int(got[0].get("reserve")) == int(got[0].get("reserve_max"))
	_check("stepping back on after the cooldown refills it, no second copy", full and again.size() == 1,
			"%d grants, %d ASR1" % [int(pad.call("grants_now")), again.size()])
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
