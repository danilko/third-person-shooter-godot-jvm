extends SceneTree
## THE SHARED EXPLOSIVE COOLDOWN (PLAN.md P1e step 1; weapon.ExplosiveCooldown, item/ammo_supply.json ai_ammo).
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_explosives.gd [-- --control] [--seconds=150]
##   --control: the cooldown OFF (every AI explosive fires as soon as its own weapon allows).
##
## World.tscn, the player invulnerable at the safe house, held at 5 lethal stars for --seconds (default 150): ATL1
## rockets from the 5-star units and LTK1 / TNK1 main guns. Counted: AI explosives fired (launchers, grenades, main
## guns) and shots the cooldown held back. Asserted: at least one explosive fired, and the rate stays within one per
## explosive_cooldown per area (the player stands still, so the fight is one area): fired <= seconds / cooldown + 1.
## The control prints the uncapped rate to compare; it asserts only that something fired.

const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"
const COOLDOWN := 6.0

var fails := 0


func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var control := "--control" in args
	var seconds := 150.0
	for a in args:
		if a.begins_with("--seconds="):
			seconds = float(a.substr(10))
	var world: Node = (load(ISLAND) as PackedScene).instantiate()
	var pz := world.get_node_or_null("PedZones")
	if pz != null:
		world.remove_child(pz)
		pz.free()
	root.add_child(world)
	current_scene = world
	for i in 240:
		await physics_frame
	var player: Node3D = world.get_node("Characters/Player")
	player.get_node("Health").set("invulnerable", true)
	var gm: Node = root.get_node("GameManager")
	var ws: Node = gm.get_node("WantedSystem")
	var ed: Node = gm.get_node("EnforcementDispatch")
	ed.call("set_ai_ammo_rules_now", true, not control)
	var pid: String = player.get("character_info").get("character_id")
	var c0 := String(ed.call("ai_ammo_counts_now")).split(",")
	var t0 := Time.get_ticks_msec()
	var first_ms := -1
	while Time.get_ticks_msec() - t0 < int(seconds * 1000.0):
		ws.call("set_stars_now", pid, 5, true)
		await physics_frame
		if Engine.get_physics_frames() % 60 != 0:
			continue
		var c := String(ed.call("ai_ammo_counts_now")).split(",")
		if first_ms < 0 and int(c[0]) > int(c0[0]):
			first_ms = Time.get_ticks_msec()
		if Engine.get_physics_frames() % 600 == 0:
			print("    t=%.0f s fired %d held %d | %s" % [(Time.get_ticks_msec() - t0) / 1000.0, int(c[0]) - int(c0[0]),
					int(c[1]) - int(c0[1]), String(ed.call("escalation_now"))])
	var c1 := String(ed.call("ai_ammo_counts_now")).split(",")
	var fired := int(c1[0]) - int(c0[0])
	var held := int(c1[1]) - int(c0[1])
	# the rate is judged from the first explosive on: armour and launchers take a while to arrive
	var window := (Time.get_ticks_msec() - first_ms) / 1000.0 if first_ms > 0 else seconds
	var per_min := fired * 60.0 / maxf(window, 1.0)
	print("probe_explosives: %s, %d AI explosives in %.0f s since the first (%.1f / min), %d held by the cooldown" % [
			"CONTROL (no cooldown)" if control else "cooldown on", fired, window, per_min, held])
	_check(fired >= 1, "AI explosives were fired in a 5-star fight (%d)" % fired)
	if not control:
		var cap := int(window / COOLDOWN) + 1
		_check(fired <= cap, "at most one per %.0f s in the fight's area (%d <= %d)" % [COOLDOWN, fired, cap])
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
