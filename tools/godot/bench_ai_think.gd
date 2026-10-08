extends SceneTree
## WHAT DOES THE AI THINK BUDGET BUY (PLAN.md 1g d): the physics-process time per tick at an enforcement peak, with
## AIController.think_budget ON (decisions every 2nd / 4th tick, staggered) and OFF (every tick), alternated so a
## drift in the scene does not read as a difference.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/bench_ai_think.gd [-- --world=island] [--stars=5]
##        [--secs=6] [--rounds=3]
##
## The player is invulnerable and police/enemy are neutral (as probe_enforcement), so the units keep fighting.

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"

var args := {}


func _player(world: Node) -> CharacterBody3D:
	for p in get_nodes_in_group("characters"):
		if p is CharacterBody3D and p.get_script() != null and String(p.get_script().resource_path).ends_with("Player.java"):
			return p
	return world.get_node_or_null("Characters/Player")


func _set_budget(on: bool) -> int:
	var n := 0
	for c in get_nodes_in_group("characters"):
		var ctrl = c.get("controller")
		if ctrl != null and ctrl.get("think_budget") != null:
			ctrl.set("think_budget", on)
			n += 1
	return n


func _measure(secs: float, ws: Node, pid: String, stars: int) -> Array:
	var sum := 0.0
	var over := 0
	var n := 0
	var t0 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < secs * 1000.0:
		await physics_frame
		ws.call("set_stars_now", pid, stars, false)
		var ms := Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0
		sum += ms
		n += 1
	return [sum / max(1, n), n]


func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=")
		args[kv[0]] = kv[1] if kv.size() > 1 else "1"
	var island: bool = args.get("world", "") == "island"
	var stars: int = int(args.get("stars", "5"))
	var secs: float = float(args.get("secs", "6"))
	var rounds: int = int(args.get("rounds", "3"))
	var world: Node = (load(ISLAND if island else DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	for i in 240:
		await physics_frame
	var gm: Node = root.get_node("GameManager")
	var ws: Node = gm.get_node("WantedSystem")
	var ed: Node = gm.get_node("EnforcementDispatch")
	var fm: Node = root.get_node("FactionManager")
	for pair in [["police", "enemy"], ["enemy", "police"]]:
		fm.call("flip_relationship", pair[0], pair[1], "NEUTRAL")
	var player := _player(world)
	player.get_node("Health").set("invulnerable", true)
	var pid: String = player.get("character_info").get("character_id")
	# fill to the peak
	var t0 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < 25000:
		await physics_frame
		ws.call("set_stars_now", pid, stars, false)
	print("  units at %d stars: %s" % [stars, String(ed.call("units_now"))])
	var on_sum := 0.0
	var off_sum := 0.0
	for r in rounds:
		for on in [true, false]:
			ed.call("set_think_budget_now", on)
			var bodies := String(ed.call("units_now"))
			await _measure(1.0, ws, pid, stars)   # settle
			var c0 := String(ed.call("think_counts_now")).split(",")
			var m: Array = await _measure(secs, ws, pid, stars)
			var c1 := String(ed.call("think_counts_now")).split(",")
			var thinks := int(c1[0]) - int(c0[0])
			var skipped := int(c1[1]) - int(c0[1])
			print("  round %d budget %s: physics %.2f ms/tick over %d ticks, units %s, decisions %d skipped %d" % [
				r, "ON " if on else "OFF", m[0], m[1], bodies, thinks, skipped])
			if on:
				on_sum += m[0]
			else:
				off_sum += m[0]
	print("RESULT think budget ON %.2f ms/tick, OFF %.2f ms/tick (saves %.2f)" % [
		on_sum / rounds, off_sum / rounds, (off_sum - on_sum) / rounds])
	quit(0)
