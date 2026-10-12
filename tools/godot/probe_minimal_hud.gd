extends SceneTree
## The minimal HUD (PLAN.md F13, 2026-10-09): show on change, then fade.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_minimal_hud.gd
##
## A real Player in WorldSystems.tscn (its HUDManager). Control first: HUD mode FULL -> health, weapon panel, minimap
## and clock stay at alpha 1 after 6 s idle. Then MINIMAL: after 6 s idle all four have faded to 0; a hit brings health
## back to 1 at once and it fades again after the hold; below 35 % health it stays; a weapon switch brings the weapon
## panel back; aiming holds it. QualitySettings' own hud mode is restored at the end (nothing is saved).

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const SYSTEMS := "res://src/main/resources/com/openworld/world/WorldSystems.tscn"

var fails := 0
var hud: Node

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-60s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _a(id: String) -> float:
	return float(hud.call("reveal_alpha_now", id))

func _dollars(v: int) -> String:
	var t := str(absi(v))
	var out := ""
	while t.length() > 3:
		out = "," + t.substr(t.length() - 3) + out
		t = t.substr(0, t.length() - 3)
	return ("-$" if v < 0 else "$") + t + out

func _all() -> String:
	return "health %.2f weapon %.2f minimap %.2f clock %.2f" % [_a("health"), _a("weapon"), _a("minimap"), _a("clock")]

func _initialize() -> void:
	var world := Node3D.new()
	root.add_child(world)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(100, 2, 100)
	cs.shape = sh
	floor.add_child(cs)
	world.add_child(floor)
	floor.position = Vector3(0, -1, 0)
	var sys: Node = (load(SYSTEMS) as PackedScene).instantiate()
	world.add_child(sys)
	hud = sys.get_node("HUDManager")
	var qs: Node = root.get_node("QualitySettings")
	var was_minimal: bool = qs.call("hud_minimal_now")
	await _tick(3)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(0, 1.0, 0)
	await _tick(60)
	var h: Node = p.get_node("Health")

	qs.call("set_hud_minimal_now", false)
	await _tick(360)
	_check("control: FULL keeps all four up after 6 s idle", _a("health") == 1.0 and _a("weapon") == 1.0
		and _a("minimap") == 1.0 and _a("clock") == 1.0, _all())

	qs.call("set_hud_minimal_now", true)
	await _tick(360)
	_check("MINIMAL: all four fade out after 6 s idle", _a("health") == 0.0 and _a("weapon") == 0.0
		and _a("minimap") == 0.0 and _a("clock") == 0.0, _all())

	h.call("apply_replicated_health", float(h.call("health_now")) - 50.0)   # a hit, as the HUD sees it
	await _tick(3)
	_check("a hit brings health back at once", _a("health") == 1.0, _all())
	await _tick(360)
	_check("  ... and it fades again after the hold", _a("health") == 0.0, _all())

	var mx: float = h.get("max_health")
	h.call("apply_replicated_health", mx * 0.2)
	await _tick(360)
	_check("below 35 % health it stays up", _a("health") == 1.0, "%s, hp %.0f / %.0f" % [_all(), float(h.call("health_now")), mx])

	p.get_node("WeaponController").call("on_set_weapon", 0)
	await _tick(3)
	var before := _a("weapon")
	Input.action_press("weapon_slot_0")
	await _tick(2)
	Input.action_release("weapon_slot_0")
	Input.action_press("holster")
	await _tick(2)
	Input.action_release("holster")
	await _tick(30)
	_check("a weapon change brings the weapon panel back", _a("weapon") == 1.0, "%.2f -> %.2f" % [before, _a("weapon")])

	# the money row (user, 2026-10-10): shown on change with the amount moved, faded after the hold, kept up in debt
	var saves: Node = root.get_node("SaveSystem")
	var cash: Node = hud.get_node("CashReadout")
	saves.call("grant_profile_now", 5000)
	await _tick(20)
	_check("cash: income brings it up, with the amount", _a("cash") == 1.0 and String(cash.call("cash_text_now")).begins_with("+$5,000  "),
		String(cash.call("cash_text_now")))
	await _tick(360)
	var bal := int(saves.call("profile_balance_now"))
	_check("cash: faded when nothing changed", _a("cash") == 0.0, "%.2f '%s'" % [_a("cash"), cash.call("cash_text_now")])
	saves.call("bill_profile_now", 1500)
	await _tick(20)
	_check("cash: a bill brings it back, with the amount", _a("cash") == 1.0
		and String(cash.call("cash_text_now")) == "-$1,500  %s" % _dollars(bal - 1500), String(cash.call("cash_text_now")))
	await _tick(360)
	_check("cash:  ... and it fades, the amount gone", _a("cash") == 0.0 and String(cash.call("cash_text_now")) == _dollars(bal - 1500),
		"%.2f '%s'" % [_a("cash"), cash.call("cash_text_now")])
	saves.call("bill_profile_now", bal)
	await _tick(360)
	_check("cash: in DEBT it stays up", _a("cash") == 1.0 and String(cash.call("cash_text_now")) == "-$1,500",
		"%.2f '%s'" % [_a("cash"), cash.call("cash_text_now")])

	qs.call("set_hud_minimal_now", was_minimal)
	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
