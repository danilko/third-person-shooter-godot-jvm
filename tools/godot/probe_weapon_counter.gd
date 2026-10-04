extends SceneTree
## The safe-house start and the weapon counter (user, 2026-09-22), on the real World.tscn.
##   stdbuf -oL <godot> --headless --path . --script tools/godot/probe_weapon_counter.gd
##
##   1. the scene has a PlayerSpawn, and the Player starts on it, standing, by the safe house's door
##      (the map's own "Safehouse" place, so the check reads the record, not the spawn it is checking);
##   2. the armoury konbini has ONE shop counter (PLAN.md W3) whose stock is catalog weapons and healing supplies;
##   3. standing at it and pressing `interact` opens the menu; buying a weapon puts it in the inventory, once;
##   4. buying it again REFILLS it, no second copy;
##   5. buying food carries it; hurt, `use_supply` heals with it;
##   6. `ui_cancel` closes the menu and gives the player their input back.

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
## -- --world=debug: DebugWorld's konbini (tools/debug_world_layout.py) -- the small store's 7 pads, no safe house
const DEBUG_WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
var debug := false
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

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	debug = "--world=debug" in OS.get_cmdline_user_args()
	var w: Node = (load(DEBUG_WORLD if debug else WORLD) as PackedScene).instantiate()
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
	if debug:
		await _debug_counter(w, spawn, p)
		return
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

	# the ARMOURY is the full-catalog store the safe house was placed beside (the record's `roles.armoury`)
	var anchor := spawn.global_position
	var rec = JSON.parse_string(FileAccess.get_file_as_string("res://assets/world_source/buildings/IslandBuildings.json"))
	if rec is Dictionary and rec.get("roles", {}).has("armoury"):
		var ap: Array = rec["roles"]["armoury"]["pos"]
		anchor = Vector3(float(ap[0]), float(ap[1]), float(ap[2]))
	var counter: Area3D = null
	var best := 1e9
	for c in _counters(w):
		var d := anchor.distance_to(c.global_position)
		if d < best:
			best = d
			counter = c
	await _counter_cycle(counter, p, spawn, "ASR1", 10)
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)


func _counters(n: Node) -> Array:
	var out: Array = []
	if n.has_method("stock_now"):
		out.append(n)
	for c in n.get_children():
		out.append_array(_counters(c))
	return out


func _menu(n: Node) -> Node:
	if n.has_method("rows_now"):
		return n
	for c in n.get_children():
		var m := _menu(c)
		if m != null:
			return m
	return null


func _press(action: String) -> void:
	Input.action_press(action)
	await physics_frame
	await process_frame
	Input.action_release(action)
	await process_frame


## The counter's whole cycle: stock, open, buy, refill, food, heal, close.
func _counter_cycle(counter: Area3D, p: CharacterBody3D, spawn: Node3D, weapon: String, min_weapons: int) -> void:
	if counter == null:
		_check("the shop has a counter", false)
		return
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://src/main/resources/com/openworld/weapon/weapon_catalog.json"))
	var ids := {}
	for r in catalog["weapons"]:
		ids[r["id"]] = true
	var stock := String(counter.call("stock_now")).split(",")
	var weapons := 0
	var food := ""
	for id in stock:
		if ids.has(id):
			weapons += 1
		elif food == "":
			food = id
	_check("the counter sells weapons and food", weapons >= min_weapons and food != "", "%d weapons, food %s, %.0f m from the spawn"
			% [weapons, food, spawn.global_position.distance_to(counter.global_position)])
	p.global_position = counter.global_position + Vector3(0, 0.3, 0)
	p.velocity = Vector3.ZERO
	await _tick(20)
	_check("standing at the counter is seen", bool(counter.call("player_at_counter_now")))
	await _press("interact")
	await _tick(2)
	var menu := _menu(root)
	_check("interact opens the menu", menu != null and int(menu.call("rows_now")) == stock.size(),
			"%s rows" % (str(menu.call("rows_now")) if menu != null else "no menu"))
	if menu == null:
		return
	menu.call("select_now", stock.find(weapon))
	menu.call("buy_now")
	await _tick(20)
	var got: Array = []
	_weapons_under(p, weapon, got)
	_check("buying %s puts one in the inventory" % weapon, got.size() == 1, "%d on the body" % got.size())
	if got.size() == 1:
		got[0].set("magazine", 0)
		got[0].set("reserve", 0)
	menu.call("buy_now")
	await _tick(20)
	var again: Array = []
	_weapons_under(p, weapon, again)
	var full: bool = got.size() == 1 and int(got[0].get("magazine")) == int(got[0].get("magazine_size"))
	_check("buying it again refills it, no second copy", full and again.size() == 1, "%d on the body" % again.size())
	menu.call("select_now", stock.find(food))
	menu.call("buy_now")
	await _tick(2)
	_check("buying %s carries one" % food, int(p.call("supply_count_now", food)) == 1)
	await _press("ui_cancel")
	await _tick(2)
	_check("ui_cancel closes the menu and gives the input back", _menu(root) == null and not bool(p.get("input_blocked")))
	var h: Node = p.get_node("Health")
	var mh := float(h.get("max_health"))
	h.call("apply_replicated_health", mh - 40.0)
	await _press("use_supply")
	await _tick(4)
	var healed := float(h.call("health_now")) - (mh - 40.0)
	_check("use_supply eats it and heals", healed > 1.0 and int(p.call("supply_count_now", food)) == 0, "+%.0f HP" % healed)


## DebugWorld: the konbini's counter (`KonbiniCounter`), the same cycle as the island's.
func _debug_counter(w: Node, spawn: Node3D, p: CharacterBody3D) -> void:
	await _tick(240)
	await _counter_cycle(w.get_node_or_null("KonbiniCounter") as Area3D, p, spawn, "PIS1", 5)
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
