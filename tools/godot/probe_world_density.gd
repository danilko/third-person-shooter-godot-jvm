extends SceneTree
## WORLD DENSITY (game.WorldDensity, user 2026-10-10): the host's one setting for how much is simulated.
##   stdbuf -oL <godot> --headless --path . --script tools/godot/probe_world_density.gd
## Each level reaches the three things it scales -- ZoneManager's car and promoted-ped budgets and the dispatch's
## attack-token bonus -- and NORMAL is exactly what the game shipped with (the Steam Deck baseline). Control: under a
## probe the player's own settings.cfg is NOT applied (budgets stay the shipped ones until this probe asks).
var fails := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", label, detail])

func _initialize() -> void:
	await process_frame
	await process_frame
	var q: Node = root.get_node_or_null("QualitySettings")
	var zm: Node = root.get_node_or_null("ZoneManager")
	var ed: Node = root.get_node_or_null("GameManager/EnforcementDispatch")
	if q == null or zm == null or ed == null:
		print("RESULT FAIL (QualitySettings / ZoneManager / EnforcementDispatch missing)")
		quit(1)
		return
	_check("control: a probe starts on the shipped budgets, whatever settings.cfg says",
		int(zm.get("traffic_budget")) == 20 and int(zm.get("walker_budget")) == 8 and int(ed.call("attack_token_bonus_now")) == 0,
		"cars %d walkers %d tokens +%d" % [int(zm.get("traffic_budget")), int(zm.get("walker_budget")), int(ed.call("attack_token_bonus_now"))])
	var want := {"HIGH": [26, 12, 8, 1, 60], "ULTRA": [32, 16, 10, 2, 72], "NORMAL": [20, 8, 6, 0, 48]}
	for level in ["HIGH", "ULTRA", "NORMAL"]:
		q.call("set_world_density_now", level)
		var got := [int(zm.get("traffic_budget")), int(zm.get("walker_budget")), int(zm.get("fighter_budget")),
				int(ed.call("attack_token_bonus_now")), int(String(ed.call("body_cap_now")).split(",")[1])]
		_check("%s reaches the car / ped / fighter budgets, the tokens and the enforcement body cap" % level, got == want[level], str(got))
	q.call("set_world_density_now", "nonsense")
	_check("an unknown level is NORMAL", str(q.call("world_density_now")) == "NORMAL", "")
	# a HOST's / tester's override (util.DataTable.overridesIn): a density.json patch in a directory of their own
	var gm: Node = root.get_node("GameManager")
	DirAccess.make_dir_recursive_absolute("user://test/overrides")
	var f := FileAccess.open("user://test/overrides/density.json", FileAccess.WRITE)
	f.store_string('{"levels": {"NORMAL": {"body_cap": 7, "traffic": 11}}}')
	f.close()
	gm.call("set_table_overrides_now", "user://test/overrides/")
	q.call("set_world_density_now", "NORMAL")
	var cap := int(String(ed.call("body_cap_now")).split(",")[1])
	_check("an override file patches the shipped table: NORMAL body cap 7, 11 cars", cap == 7 and int(zm.get("traffic_budget")) == 11,
		"cap %d cars %d" % [cap, int(zm.get("traffic_budget"))])
	_check("  ... and the rest of the row stays shipped", int(zm.get("walker_budget")) == 8, "walkers %d" % int(zm.get("walker_budget")))
	gm.call("set_table_overrides_now", "")
	q.call("set_world_density_now", "NORMAL")
	_check("  ... and with no overrides the shipped numbers are back", int(String(ed.call("body_cap_now")).split(",")[1]) == 48
		and int(zm.get("traffic_budget")) == 20, String(ed.call("body_cap_now")))
	DirAccess.remove_absolute("user://test/overrides/density.json")
	print("")
	print("PASS (0 failures)" if fails == 0 else "RESULT FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
