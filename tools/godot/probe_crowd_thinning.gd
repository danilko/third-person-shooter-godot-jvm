extends SceneTree
## THE CROWD MAKES ROOM FOR A FIGHT (PLAN.md 2.3 step 8, user 2026-10-16: "reduce peds when more engagement comes ...
## the crowd runs around in big chunks"; docs/crowd.md "Panic thinning"). Headless, World.tscn, the real ZoneManager.
##
##   godot --headless --path . --script tools/godot/probe_crowd_thinning.gd [-- --control]
##
##   A. PANIC THINNING: a gunshot in a 120-ped crowd; the fleeing peds that are out of view and 30 m from it go
##      INSIDE (some, never more than 70 %), none of them where the camera looks; after insideSeconds they come back;
##   B. COMBAT LOAD: the light tier's promoted bodies count -- ZoneManager's walker budget drops with them;
##   C. SHED: walkers promoted before the fight are handed back over the reduced budget (out of view, 20 m+ away).
##   --control: panic_thinning and shed_walkers off -- A's "some go inside" and C's "shed" fail.

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const ZONE_JAVA := "res://src/main/java/com/openworld/world/Zone.java"
const MARKER_JAVA := "res://src/main/java/com/openworld/world/ZoneMarker.java"
const SPAWN_JAVA := "res://src/main/java/com/openworld/world/SpawnConfig.java"
const AT := Vector3(560, 0.75, -350)

var w: Node
var player: Node3D
var control := false
var fails := 0

func check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _initialize() -> void:
	control = OS.get_cmdline_user_args().has("--control")
	_run.call_deferred()

func _wait(seconds: float) -> void:
	var t := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t < int(seconds * 1000.0):
		await process_frame

func _put_player(at: Vector3) -> void:
	var wb := current_scene.find_child("WorldBounds", true, false) if current_scene else null
	if wb != null:
		var h: float = wb.call("terrain_height", at.x, at.z)
		if not is_nan(h):
			at.y = maxf(at.y, h + 0.5)
	player.global_position = at
	player.velocity = Vector3.ZERO
	player.get_node("MovementController").call("clear_motion")

func _crowd() -> Node:
	var out := []
	_collect(w, out)
	return out[0] if out.size() > 0 else null

func _collect(n: Node, out: Array) -> void:
	var s = n.get_script()
	if s != null and str(s.resource_path).ends_with("PedCrowd.java"):
		out.append(n)
	for c in n.get_children():
		_collect(c, out)

func _count_crowds() -> int:
	var out := []
	_collect(w, out)
	return out.size()

func _make_zone(id: String, at: Vector3, count: int) -> Node3D:
	var z: Resource = load(ZONE_JAVA).new()
	z.set("zone_id", id)
	z.set("size", Vector3(360, 20, 360))
	z.set("load_radius", 900.0)
	z.set("unload_radius", 1400.0)
	var sc: Resource = load(SPAWN_JAVA).new()
	sc.set("count", count)
	sc.set("behavior", "sidewalk")
	sc.set("faction", "neutral")
	sc.set("weapon_scene_path", "")
	z.get("spawn_configs").append(sc)
	var m: Node3D = load(MARKER_JAVA).new()
	m.set("zone", z)
	m.set("show_debug_volume", false)
	w.add_child(m)
	m.global_position = at
	return m

func _load(zm: Node) -> PackedStringArray:
	return String(zm.call("combat_load_now")).split(",")

func _run() -> void:
	w = (load(WORLD) as PackedScene).instantiate()
	root.add_child(w)
	current_scene = w
	await process_frame
	var zm := root.get_node("/root/ZoneManager")
	player = w.get_node("Characters/Player")
	player.get_node("Health").set("invulnerable", true)
	zm.set("shed_walkers", not control)
	_put_player(AT + Vector3(0, 1, 0))
	_make_zone("thin_probe", AT, 120)
	await _wait(8.0)
	var crowd := _crowd()
	check(crowd != null and int(crowd.call("ped_count")) > 60, "a 120-ped crowd streamed in (%d)" % (int(crowd.call("ped_count")) if crowd else 0))
	if crowd == null:
		print("RESULT FAIL"); quit(1); return
	crowd.set("panic_thinning", not control)
	crowd.set("inside_seconds", 6.0)
	crowd.set("cower_percent", 0)
	crowd.set("fight_percent", 0)
	crowd.call("reroll_temper_now")

	# A ────────────────────────────────────────────────────────────────────────
	print("A. panic thinning")
	var here: Vector3 = crowd.call("ped_positions_now")[0]
	_put_player(here + Vector3(0, 1, 60))
	# whatever scared the crowd while it streamed in is over (the island's own fights can reach it)
	crowd.call("calm_now")
	await _wait(1.0)
	var s0 := String(crowd.call("thinning_stats_now")).split(",")
	var total := int(crowd.call("ped_count"))
	print("  before the shot: states %s, inside %d" % [crowd.call("states_now"), int(crowd.call("inside_now"))])
	root.get_node("StimulusManager").call("post_noise", 0, here, 150.0)
	var peak := 0
	var flee_view := 0
	for i in 40:
		await _wait(0.1)
		peak = maxi(peak, int(crowd.call("inside_now")))
		flee_view = maxi(flee_view, int(String(crowd.call("thinning_stats_now")).split(",")[3]))
	print("  scared %d, inside at most %d of %d, fleeing in view at most %d" % [int(crowd.call("scares_now")), peak, total, flee_view])
	var went := int(String(crowd.call("thinning_stats_now")).split(",")[0]) - int(s0[0])
	check(went > 0, "fleeing peds out of view went inside (%d went in)" % went)
	check(peak <= int(ceil(0.7 * total)), "never more than 70 %% inside (%d of %d)" % [peak, total])
	check(flee_view > 0, "the ones in view keep running (at most %d fleeing in view)" % flee_view)
	await _wait(14.0)
	var s1 := String(crowd.call("thinning_stats_now")).split(",")
	var after := int(crowd.call("inside_now"))
	print("  went in %d, came out %d (%d in view), inside now %d" % [int(s1[0]) - int(s0[0]), int(s1[1]) - int(s0[1]), int(s1[2]) - int(s0[2]), after])
	check(int(s1[1]) - int(s0[1]) > 0, "they come back after inside_seconds (%d came out, inside %d -> %d)" % [int(s1[1]) - int(s0[1]), peak, after])
	check(int(s1[2]) == int(s0[2]), "nobody came back out in front of the camera (%d)" % (int(s1[2]) - int(s0[2])))

	# B ────────────────────────────────────────────────────────────────────────
	print("B. the light tier's bodies are combat load")
	var b0 := _load(zm)
	var tier: Node = load("res://src/main/java/com/openworld/ai/light/LightCombatants.java").new()
	w.add_child(tier)
	await process_frame
	tier.call("tune_now", 80, 6, 15.0, 4, true)
	var made: int = tier.call("horde_now", player.global_position, 12, 11.0, "gang_a", "", false)
	await _wait(10.0)
	var b1 := _load(zm)
	print("  combat,walkerBudget,fighterBudget,walkers: %s -> %s (light promoted %s)" % [",".join(b0), ",".join(b1), String(tier.call("stats_now")).split(",")[1]])
	var lp := int(String(tier.call("stats_now")).split(",")[1])
	check(lp > 0 and absi(int(b1[0]) - int(b0[0]) - lp) <= 1, "the %d promoted bodies count as combat load (%s -> %s)" % [lp, b0[0], b1[0]])
	check(int(b1[1]) < int(b0[1]), "the walker budget made room (%s -> %s)" % [b0[1], b1[1]])
	tier.call("clear_now")
	await _wait(1.0)

	# C ────────────────────────────────────────────────────────────────────────
	print("C. walkers over the reduced budget are shed")
	zm.call("set_combat_load_now", "probe", 0)
	crowd.call("calm_now")
	_put_player(here + Vector3(0, 1, 0))
	await _wait(8.0)
	var w0 := int(_load(zm)[3])
	_put_player(here + Vector3(0, 1, 28))         # inside the 40 m demote ring, past the 20 m shed floor
	zm.call("set_combat_load_now", "probe", 16)  # a big fight elsewhere: the walker budget drops to its floor
	await _wait(6.0)
	var c1 := _load(zm)
	var shed := int(zm.get("walkers_shed"))
	print("  walkers %d -> %s, budget now %s, shed %d" % [w0, c1[3], c1[1], shed])
	check(w0 > int(c1[1]), "the crowd had more walkers than the reduced budget (%d > %s)" % [w0, c1[1]])
	check(shed > 0 and int(c1[3]) < w0, "walkers were shed (%d shed, %d -> %s)" % [shed, w0, c1[3]])
	zm.call("set_combat_load_now", "probe", 0)

	print("RESULT %s (%d failed)%s" % ["PASS" if fails == 0 else "FAIL", fails, " [CONTROL]" if control else ""])
	quit(fails)
