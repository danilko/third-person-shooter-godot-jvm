extends SceneTree
## MOTORCYCLES AS TRAFFIC AND AS POLICE (PLAN.md 3.1b's rest): the four civilian bikes (SCT1 / POB1 / TRB1 / SSB1)
## ride the lanes like any ambient car, and the police send a 白バイ (PMB1) with one officer from one star.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_traffic_bikes.gd [-- --world=island] [--control]
## DebugWorld keeps 3 cars at a time, so its ride numbers are noisy (three bikes at one red is the whole sample); the
## island run (20 cars) is the one that judges the riding.
##
## The run forces a bikes-heavy traffic mix through a table OVERRIDE (util.DataTable, user://test/overrides_bikes/
## traffic.json: every row's bikes weighted 400) so there are enough bikes to judge; the shipped weights are only
## printed. --control: no override -- the shipped mix (a few bikes at most), so the "many bikes" checks fail.
##   1. bikes are spawned as traffic, and their ids are the civilian four (never the 白バイ);
##   2. they ride: the median bike covers >= 100 m in 100 s, and at most one stands > 40 s other than at a red;
##   3. they stay upright (body up . Y >= 0.8) and nobody is thrown off without a crash (throws <= 1);
##   4. a bike near the player gets its lazy driver (ZoneManager seats one inside ~70 m);
##   5. the far tier draws bikes too (its model list names one);
##   6. one star: a PMB1 comes, lights on, ONE officer aboard (the pillion seat stays empty).

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const CIVIL_BIKES := ["SCT1", "POB1", "TRB1", "SSB1"]
const OV_DIR := "user://test/overrides_bikes/"

var fails := 0
var world: Node

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _id(v: Node) -> String:
	return String(v.scene_file_path).get_file().get_basename()

func _write_override() -> void:
	var shipped: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://src/main/resources/com/openworld/game/traffic.json"))
	var bikes := {}
	for b in CIVIL_BIKES:
		bikes[b] = 400
	var patch := {"default": {"mix": bikes}, "regions": {}}
	for k in (shipped["regions"] as Dictionary).keys():
		patch["regions"][k] = {"mix": bikes}
	DirAccess.make_dir_recursive_absolute(OV_DIR)
	var f := FileAccess.open(OV_DIR + "traffic.json", FileAccess.WRITE)
	f.store_string(JSON.stringify(patch))
	f.close()

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	var gm: Node = root.get_node("GameManager")
	if not control:
		_write_override()
		gm.call("set_table_overrides_now", OV_DIR)
	var island := "--world=island" in OS.get_cmdline_user_args()
	world = (load(ISLAND if island else DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	var helper: Node = (load(HELPER) as Script).new()
	root.add_child(helper)
	var zm: Node = root.get_node("ZoneManager")
	var player: Node3D = world.get_node("Characters/Player")
	var helper_wait := 60 if not island else 600     # the island streams its first zones for a few seconds
	var health: Node = player.get_node("Health")
	health.set("invulnerable", true)
	await _tick(helper_wait)

	# 1-4. a hundred seconds of traffic (every streamed vehicle is followed: the cars are the bikes' baseline)
	var rides := {}         # instance id -> {id, bike, dist, last, mark, idle, max_idle, min_up, node, why}
	var non_civil := {}
	var near_seated := 0
	var near_seen := 0
	for f in range(100 * 4):
		await _tick(15)
		for v in get_nodes_in_group("streamed_vehicle"):
			if not is_instance_valid(v):
				continue
			var id := _id(v)
			var bike: bool = v.has_method("throw_riders_now")
			if bike and not (id in CIVIL_BIKES):
				non_civil[id] = true
			var p: Vector3 = (v as Node3D).global_position
			var k := v.get_instance_id()
			if not rides.has(k):
				rides[k] = {"id": id, "bike": bike, "dist": 0.0, "last": p, "mark": p, "idle": 0.0, "max_idle": 0.0, "min_up": 1.0, "node": v, "why": {}}
			var b: Dictionary = rides[k]
			b["dist"] += Vector2(p.x - b["last"].x, p.z - b["last"].z).length()
			b["last"] = p
			if p.distance_to(b["mark"]) > 1.0:
				b["mark"] = p
				b["idle"] = 0.0
			else:
				b["idle"] += 0.25
				b["max_idle"] = maxf(b["max_idle"], b["idle"])
				var why := String(helper.call("standing_reason_of", v))
				b["why"][why] = int(b["why"].get(why, 0)) + 1
			b["min_up"] = minf(b["min_up"], (v as Node3D).global_basis.y.dot(Vector3.UP))
			if bike and p.distance_to(player.global_position) < 50.0:
				near_seen += 1
				if helper.call("occupant_of", v) != null:
					near_seated += 1
		if f % 80 == 0:
			print("    t=%d %s" % [f / 4, String(zm.call("traffic_state_now", 1000.0))])
	var bikes := {}
	var car_dists: Array = []
	var car_stuck := 0
	for k in rides:
		if rides[k]["bike"]:
			bikes[k] = rides[k]
		elif not rides[k]["why"].has("no-brain"):      # a parked truck is not traffic
			car_dists.append(rides[k]["dist"])
			if rides[k]["max_idle"] > 40.0 and int(rides[k]["why"].get("signal", 0)) < 0.8 * (rides[k]["why"].values().reduce(func(a, x): return a + x, 0) - int(rides[k]["why"].get("moving", 0))):
				car_stuck += 1
			print("    car %s ride %.0f m, max stand %.1f s, standing %s" % [rides[k]["id"], rides[k]["dist"], rides[k]["max_idle"], rides[k]["why"]])
	car_dists.sort()
	print("  cars (baseline): %d, median %.0f m, %d stood > 40 s not at a signal" % [car_dists.size(), car_dists[car_dists.size() / 2] if not car_dists.is_empty() else 0.0, car_stuck])
	var throws := 0
	var dists: Array = []
	var stuck := 0
	var tipped := 0
	var by_id := {}
	for k in bikes:
		var b: Dictionary = bikes[k]
		print("    bike %s ride %.0f m, max stand %.1f s, min up %.2f, standing %s" % [b["id"], b["dist"], b["max_idle"], b["min_up"], b["why"]])
		if is_instance_valid(b["node"]):
			throws += int(b["node"].call("throws_now"))
		dists.append(b["dist"])
		# a red on a 3-4 group junction is up to ~80 s (TrafficSignals: 22 + 3 + 2 s a group): standing at one is
		# the signal's doing, not the bike's
		var at_signal := int(b["why"].get("signal", 0))
		var standing := 0
		for w in b["why"]:
			if w != "moving":
				standing += int(b["why"][w])
		if b["max_idle"] > 40.0 and at_signal < standing * 0.8:
			stuck += 1
		if b["min_up"] < 0.8:
			tipped += 1
		by_id[b["id"]] = int(by_id.get(b["id"], 0)) + 1
	dists.sort()
	var median: float = dists[dists.size() / 2] if not dists.is_empty() else 0.0
	print("  traffic: %d vehicles seen, %d bikes %s; median ride %.0f m, stuck %d, tipped %d, throws %d (live bikes only); near samples %d, seated %d%s"
			% [rides.size(), bikes.size(), by_id, median, stuck, tipped, throws, near_seen, near_seated, "  (CONTROL)" if control else ""])
	_check(bikes.size() >= 4, "bikes are spawned as ambient traffic (%d of %d vehicles)" % [bikes.size(), rides.size()])
	_check(non_civil.is_empty(), "every traffic bike is a civilian model, never the 白バイ (%s)" % [non_civil.keys()])
	_check(bikes.size() >= 4 and median >= 100.0, "they ride the lanes: median %.0f m in 100 s" % median)
	_check(bikes.size() >= 4 and stuck <= 1, "at most one bike stands > 40 s other than at a red (%d)" % stuck)
	_check(tipped == 0, "no bike body tipped over (%d)" % tipped)
	_check(throws <= 1, "nobody is thrown off without a crash (%d throws)" % throws)
	_check(near_seen > 0 and near_seated > near_seen / 2, "a bike near the player carries its lazy driver (%d of %d samples)" % [near_seated, near_seen])

	# 5. the far tier
	var ft: Node = zm.get_node_or_null("FarTraffic")
	var diag := String(ft.call("diag_now")) if ft != null else ""
	var far_bike := false
	for b in CIVIL_BIKES:
		far_bike = far_bike or diag.contains(b)
	print("  far tier: %s" % diag)
	_check(far_bike, "the far tier draws bikes too")

	# 6. one star: the 白バイ
	if control:
		gm.call("set_table_overrides_now", "")
	var ws: Node = gm.get_node("WantedSystem")
	var ed: Node = gm.get_node("EnforcementDispatch")
	var fm: Node = root.get_node("FactionManager")
	for pair in [["police", "enemy"], ["enemy", "police"]]:
		fm.call("flip_relationship", pair[0], pair[1], "NEUTRAL")
	var pid: String = player.get("character_info").get("character_id")
	var pmb: Node = null
	var lit := false
	var crew := -1
	var models := {}
	var t := 0.0
	while t < 60.0:
		await _tick(30)
		t += 0.5
		ws.call("set_stars_now", pid, 1, false)
		for m in String(ed.call("escalation_now")).split(";")[0].split(" ", false):
			models[m] = true
		if pmb == null:
			for v in get_nodes_in_group("characters"):
				if is_instance_valid(v) and _id(v) == "PMB1" and v.has_method("emergency_now") and bool(v.call("emergency_now")):
					pmb = v
					break
		if pmb != null and is_instance_valid(pmb) and crew < 0:
			crew = int(helper.call("seated_count", pmb))
			lit = bool(pmb.call("emergency_now"))
		if crew >= 0 and t > 5.0:
			break
	print("  one star: models sent %s, PMB1 found %s, crew %d, lights %s, %.1f s" % [models.keys(), pmb != null, crew, lit, t])
	_check(models.has("PMB1"), "one star sends a 白バイ (%s)" % [models.keys()])
	_check(pmb != null and lit, "it rides with its lights on")
	_check(crew == 1, "one officer aboard, the pillion seat empty (%d)" % crew)
	ws.call("clear_now", pid)
	DirAccess.remove_absolute(OV_DIR + "traffic.json")
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
