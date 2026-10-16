extends SceneTree
## THE LIGHT COMBATANT TIER (PLAN.md 2.3 / F8; docs/game-systems.md "The light combatant tier and the AI blackboard")
## on DebugWorld: ai.light.LightCombatants with the real EnforcementDispatch spawning the full bodies.
##
##   ./gradlew build && stdbuf -oL godot --headless --path . --script tools/godot/probe_light_tier.gd [-- --control]
##
##   A. a melee horde of 30 round the player with NO full budget: every one is light (no character added), they
##      converge, they hold back on the ring, they are drawn (MultiMesh instances = bodies), the player takes NO damage;
##   B. a budget of 6: bodies are promoted inside 15 m, never more than the budget, each a real AICharacter carrying
##      the blackboard (hunts players, owner "horde") and the id light:<n>;
##   C. hits: a lethal hit kills in the tier (death, no promotion), a non-lethal one promotes past the budget to the
##      ceiling; a shot through FirearmItem's path (LightCombatants.shoot) finds a light body;
##   D. demotion: the player leaves; a calm, far, unhurt promoted body goes back to the tier with its hit points;
##   E. ranged: a gang_heavy squad 70 m out stops near the 25 m standoff and holds (aims), not running in;
##   F. the CONTROL (--control, lightTier off): the same horde comes up as full bodies -- A's "no character added"
##      and "drawn" fail.

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const TIER := "res://src/main/java/com/openworld/ai/light/LightCombatants.java"

var fails := 0
var world: Node
var player: CharacterBody3D
var tier: Node
var control := false

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _ground(x: float, z: float, y: float) -> Variant:
	var sp := world.get_viewport().world_3d.direct_space_state
	var hit := sp.intersect_ray(PhysicsRayQueryParameters3D.create(Vector3(x, y + 30.0, z), Vector3(x, y - 30.0, z)))
	return null if hit.is_empty() else hit["position"]

func _put(at: Vector3) -> void:
	player.global_position = at + Vector3(0, 0.3, 0)
	player.velocity = Vector3.ZERO
	player.get_node("MovementController").call("clear_motion")
	await _tick(4)

## [id, state, x, y, z, hp, promoted] per light combatant.
func _dump() -> Array:
	var out := []
	var s := String(tier.call("dump_now"))
	if s == "":
		return out
	for row in s.split("|"):
		var f := row.split(";")
		out.append([int(f[0]), int(f[1]), float(f[2]), float(f[3]), float(f[4]), float(f[5]), int(f[6])])
	return out

func _stats() -> PackedStringArray:
	return String(tier.call("stats_now")).split(",")

func _characters() -> int:
	var n := 0
	for c in world.get_tree().get_nodes_in_group("characters"):
		if c is CharacterBody3D and c != player:
			n += 1
	return n

func _drawn() -> int:
	var n := 0
	for c in tier.get_children():
		if c is MultiMeshInstance3D and (c as MultiMeshInstance3D).material_override != null \
				and String((c as MultiMeshInstance3D).material_override.shader.resource_path).ends_with("ped_vat.gdshader"):
			n += (c as MultiMeshInstance3D).multimesh.visible_instance_count
	return n

func _mean_dist(rows: Array, at: Vector3) -> float:
	var s := 0.0
	var n := 0
	for r in rows:
		if r[1] <= 3:
			s += Vector2(r[2] - at.x, r[4] - at.z).length()
			n += 1
	return s / maxf(1, n)

func _clear_world_ai() -> void:
	for c in world.get_node("Characters").get_children():
		if c != player and c is CharacterBody3D:
			c.queue_free()
	await _tick(10)

func _initialize() -> void:
	control = OS.get_cmdline_user_args().has("--control")
	world = (load(DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	await _tick(120)
	player = world.get_node("Characters/Player")
	await _clear_world_ai()
	tier = load(TIER).new()
	world.add_child(tier)
	await _tick(2)
	var home := player.global_position
	var hp0: float = player.get_node("Health").call("current_health_now")

	# A. ─────────────────────────────────────────────────────────────────────
	print("A. a melee horde with no full budget: light, converging, held back, drawn, harmless")
	tier.call("tune_now", 80, 0, 15.0, 4, not control)
	var before := _characters()
	var made: int = tier.call("horde_now", home, 30, 45.0, "gang_a", "", true)
	await _tick(2)
	var rows := _dump()
	_check(made == 30 and rows.size() == 30, "the tier took 30 (made %d, %d rows)" % [made, rows.size()])
	_check(_characters() == before, "no character body added (%d -> %d)" % [before, _characters()])
	await _tick(6)
	_check(_drawn() == 30, "every one drawn as a MultiMesh instance (%d)" % _drawn())
	var d0 := _mean_dist(_dump(), home)
	await _tick(60 * 25)
	rows = _dump()
	var d1 := _mean_dist(rows, home)
	_check(d1 < d0 - 15.0, "they converge (mean %.1f -> %.1f m)" % [d0, d1])
	var inside := 0
	var closest := 999.0
	for r in rows:
		var d := Vector2(r[2] - home.x, r[4] - home.z).length()
		closest = minf(closest, d)
		if d < 4.5:
			inside += 1
	_check(inside == 0, "a refused horde holds back on the 6 m ring (closest %.1f m, %d inside 4.5 m)" % [closest, inside])
	var hp1: float = player.get_node("Health").call("current_health_now")
	_check(hp1 == hp0, "the player took no damage from the light horde (%.0f -> %.0f)" % [hp0, hp1])
	var thinks := int(_stats()[8])
	print("  stats light,promoted,dead,promotedTotal,demotedTotal,killedInTier,refused,paths,thinks: %s" % ",".join(_stats()))

	# B. ─────────────────────────────────────────────────────────────────────
	print("B. a budget of 6: promoted inside 15 m, never past the budget, carrying the blackboard")
	tier.call("tune_now", 80, 6, 15.0, 4, not control)
	var peak := 0
	for i in 120:
		await _tick(5)
		peak = maxi(peak, int(_stats()[1]))
	_check(peak > 0 and peak <= 6, "promoted up to the budget (peak %d of 6)" % peak)
	var body: Node = null
	for c in world.get_tree().get_nodes_in_group("characters"):
		var info = c.get("character_info") if c != player else null
		if info != null and String(info.get("character_id")).begins_with("light:"):
			body = c
			break
	_check(body != null, "a promoted body is announced as light:<n>")
	if body != null:
		var bb = body.get("blackboard")
		print("  promoted body %s at %.1f m" % [body.name, body.global_position.distance_to(player.global_position)])
		_check(body.global_position.distance_to(player.global_position) < 25.0, "it was promoted near the player")

	# C. ─────────────────────────────────────────────────────────────────────
	print("C. hits: lethal dies in the tier, non-lethal promotes to the ceiling; a ray finds a light body")
	rows = _dump()
	var light_ids := []
	for r in rows:
		if r[1] <= 3 and r[6] == 0:
			light_ids.append(r[0])
	if light_ids.size() >= 2:
		var k0 := int(_stats()[5])
		var r1: int = tier.call("hit_now", light_ids[0], 500.0)
		_check(r1 == 1 and int(_stats()[5]) == k0 + 1, "a lethal hit kills it in the tier (result %d)" % r1)
		await _tick(3)
		var dead_row = null
		for r in _dump():
			if r[0] == light_ids[0]:
				dead_row = r
		_check(dead_row != null and dead_row[1] == 4, "it lies dead, drawn (state %s)" % (dead_row[1] if dead_row != null else "gone"))
		var p0 := int(_stats()[1])
		var r2: int = tier.call("hit_now", light_ids[1], 20.0)
		_check(r2 == 2 or p0 >= 6 + 4, "a non-lethal hit promotes past the budget (result %d, promoted %d)" % [r2, p0])
	else:
		_check(false, "light bodies left to hit (%d)" % light_ids.size())

	# D. ─────────────────────────────────────────────────────────────────────
	print("D. demotion: the player leaves, calm far bodies go back to the tier")
	tier.set("demote_calm_seconds", 1.0)
	tier.set("demote_unhurt_seconds", 0.0)
	tier.set("demote_distance", 40.0)
	tier.call("tune_now", 80, 0, 15.0, 4, not control)   # nothing new is promoted while it leaves
	var away = _ground(home.x + 260.0, home.z, home.y + 20.0)
	if away == null:
		away = home + Vector3(260, 0, 0)
	await _put(away)
	var dem0 := int(_stats()[4])
	for i in 60:
		await _tick(10)
		if int(_stats()[1]) == 0:
			break
	if int(_stats()[1]) > 0:
		print("  still promoted: %s" % tier.call("promoted_readout_now"))
	_check(int(_stats()[4]) > dem0 and int(_stats()[1]) == 0,
		"every promoted body was demoted (demoted %d, still promoted %s)" % [int(_stats()[4]) - dem0, _stats()[1]])
	tier.call("clear_now")
	await _tick(10)
	await _put(home)
	await _clear_world_ai()

	# E. ─────────────────────────────────────────────────────────────────────
	print("E. ranged: a gang_heavy squad stops near the standoff and holds")
	tier.call("tune_now", 80, 0, 15.0, 4, not control)
	tier.call("horde_now", home, 10, 60.0, "gang_a", "gang_heavy", false)
	await _tick(60 * 25)
	rows = _dump()
	var holding := 0
	var dist := []
	for r in rows:
		var d := Vector2(r[2] - home.x, r[4] - home.z).length()
		dist.append(snappedf(d, 0.1))
		if r[1] == 2 and d > 15.0 and d < 35.0:
			holding += 1
	_check(holding >= 6, "%d of 10 hold between 15 and 35 m (%s)" % [holding, dist])
	# a ray from the player through one of them hits it
	if rows.size() > 0:
		var r = rows[0]
		var eye := player.global_position + Vector3(0, 1.6, 0)
		var at := Vector3(r[2], r[3] + 1.2, r[4])
		var hit: Vector3 = tier.call("shoot_probe_now", eye, (at - eye).normalized(), 200.0)
		_check(hit.y > -1000.0 and hit.distance_to(at) < 1.0, "a ray at a light body finds it (%s vs %s)" % [hit, at])
	print("  stats: %s" % ",".join(_stats()))
	tier.call("clear_now")
	await _tick(10)

	# F. ─────────────────────────────────────────────────────────────────────
	print("F. an encounter's overflow: waves \"5\" with full_cap 2 -> 2 full bodies + 3 light, all counted, all released")
	tier.call("tune_now", 80, 0, 15.0, 4, not control)
	var e: Node3D = load("res://src/main/java/com/openworld/game/encounter/Encounter.java").new()
	e.set("encounter_id", "overflow")
	e.set("faction", "gang_a")
	e.set("loadout", "gang_heavy")
	e.set("waves", "5")
	e.set("manual", true)
	e.set("spawn_near", 200.0)
	e.set("despawn_far", 400.0)
	e.set("full_cap", 2)
	world.add_child(e)
	e.global_position = home + Vector3(30, 0, 0)
	await _tick(10)
	var c0 := _characters()
	e.call("start_now")
	await _tick(30)
	var full_added := _characters() - c0
	_check(full_added == 2, "2 full bodies stand up (%d)" % full_added)
	_check(int(tier.call("light_now")) == 3, "3 more in the light tier (%d)" % int(tier.call("light_now")))
	_check(int(e.call("live_now")) == 5, "the encounter counts all 5 alive (%d)" % int(e.call("live_now")))
	e.call("stop_now")
	await _tick(10)
	_check(int(tier.call("light_now")) == 0 and int(e.call("live_now")) == 0,
		"stop takes the light ones away too (light %d, live %d)" % [int(tier.call("light_now")), int(e.call("live_now"))])
	e.queue_free()

	print("RESULT %s (%d failed)%s" % ["PASS" if fails == 0 else "FAIL", fails, " [CONTROL]" if control else ""])
	quit(fails)
