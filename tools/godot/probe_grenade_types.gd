extends SceneTree
## The four throwables beyond the frag grenade, each thrown the real way (a Player picks it up, `fire` through
## Input) on a bare stand, and each one's EFFECT measured where the preview says it lands:
##
##   1. PIB1 pipe bomb  - a frag: an AI standing where it lands loses health.
##   2. FLA1 flashbang  - an AI in the open near it is blinded, one behind a wall is not, and the local player
##                        (looking at it) gets the white screen. The wall case is the control.
##   3. SMO1 smoke      - a cloud forms, a sight line through it is blocked and one beside it is not.
##   4. REC1 charge     - two charges stick where they land and do NOT go off by themselves (5 s); the
##                        `detonate` key sets both off, and an AI next to them loses health.
##
##   godot --headless --fixed-fps 60 --path . --script tools/godot/probe_grenade_types.gd

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const AI     := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const W      := "res://src/main/resources/com/openworld/weapon/"
const IMPACT := "res://src/main/java/com/openworld/world/manager/ImpactManager.java"
const EXPL   := "res://src/main/java/com/openworld/world/manager/ExplosionManager.java"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const THROW_SLOT := 5

var fails := 0
var world: Node3D
var helper: Node

func _check(label: String, ok: bool, detail: String) -> void:
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", label, detail])
	if not ok:
		fails += 1

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _box(size: Vector3, pos: Vector3) -> StaticBody3D:
	var b := StaticBody3D.new()
	var s := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = size
	s.shape = bs
	b.add_child(s)
	world.add_child(b)
	b.global_position = pos
	return b

func _still(ai: Node3D) -> void:
	ai.set_physics_process(false)
	var mc: Node = ai.get_node_or_null("MovementController")
	if mc != null:
		mc.set_physics_process(false)

func _health(c: Node) -> float:
	return c.get_node("Health").call("health_now")

## A fresh Player at `at`, holding `count` of weapon `wid` in its throwable slot, looking level down -Z.
func _armed(at: Vector3, wid: String, count: int) -> Node3D:
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.global_position = at
	await _tick(30)
	var item: Node3D = (load(W + wid + ".tscn") as PackedScene).instantiate() as Node3D
	world.add_child(item)
	item.global_position = at + Vector3(4, 1, 0)
	await _tick(3)
	item.set("magazine", count)
	(item.get_parent() as Node3D).global_position = p.global_position + Vector3(0, 0.6, 0)
	await _tick(20)
	p.get_node("WeaponController").call("on_set_weapon", THROW_SLOT)
	p.set("is_fps_mode", true)                     # first person: combat, so the preview shows
	for i in range(60):
		helper.call("set_view", p, 0.0, 0.0)
		await physics_frame
	return p

## Press fire once; return the projectile it threw.
func _throw(p: Node3D) -> Node3D:
	var seen := {}
	for n in world.get_children():
		seen[n.get_instance_id()] = true
	Input.action_press("fire")
	await _tick(2)
	Input.action_release("fire")
	await _tick(2)
	for n in world.get_children():
		if not seen.has(n.get_instance_id()) and n is RigidBody3D:
			return n
	return null

func _ai_at(pos: Vector3) -> Node3D:
	var a: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	world.add_child(a)
	a.global_position = pos
	await _tick(20)
	_still(a)
	return a

## Where the held throwable's preview says it will land (the item hangs under the Player's hand socket).
func _landing(p: Node3D) -> Vector3:
	for c in p.find_children("*", "Node3D", true, false):
		if c.has_method("preview_end_now") and c.call("preview_shown_now"):
			return c.call("preview_end_now")
	return p.global_position + Vector3(0, 0, -14)

func _initialize() -> void:
	world = Node3D.new()
	root.add_child(world)
	current_scene = world
	_box(Vector3(600, 1, 600), Vector3(0, -0.5, 0))
	world.add_child(load(IMPACT).new())
	world.add_child(load(EXPL).new())
	helper = load(HELPER).new()
	world.add_child(helper)
	await _tick(3)

	# ── 1. pipe bomb ───────────────────────────────────────────────────────────────────────────
	print("\n=== 1. PIB1 pipe bomb (frag) ===")
	var p1 := await _armed(Vector3(0, 0.05, 0), "PIB1", 1)
	var land1 := _landing(p1)
	var victim := await _ai_at(land1 + Vector3(1.5, 0, 0))
	var h0 := _health(victim)
	var g1 := await _throw(p1)
	_check("PIB1 throws a projectile", g1 != null, "")
	await _tick(240)
	_check("it went off by itself (fuse)", g1 == null or not is_instance_valid(g1), "")
	_check("an AI 1.5 m from where it lands is hurt", _health(victim) < h0, "health %.0f -> %.0f" % [h0, _health(victim)])

	# ── 2. flashbang ───────────────────────────────────────────────────────────────────────────
	print("\n=== 2. FLA1 flashbang ===")
	var p2 := await _armed(Vector3(100, 0.05, 0), "FLA1", 1)
	var land2 := _landing(p2)
	var open_ai := await _ai_at(land2 + Vector3(-5, 0, 0))
	var hidden_ai := await _ai_at(land2 + Vector3(8, 0, 0))
	_box(Vector3(0.4, 4, 6), land2 + Vector3(4, 2, 0))         # a wall between the flash and hidden_ai
	await _tick(5)
	var g2 := await _throw(p2)
	_check("FLA1 throws a projectile", g2 != null, "")
	var blind_open := 0.0
	var blind_hidden := 0.0
	var screen := 0.0
	for i in range(150):
		await physics_frame
		blind_open = maxf(blind_open, open_ai.call("blind_now"))
		blind_hidden = maxf(blind_hidden, hidden_ai.call("blind_now"))
		var fo: Node = root.get_node_or_null("FlashOverlay")
		if fo != null:
			screen = maxf(screen, fo.call("remaining_now"))
	_check("an AI in the open near it is blinded", blind_open > 0.5, "%.2f s" % blind_open)
	_check("an AI behind a wall is NOT blinded (control)", blind_hidden == 0.0, "%.2f s" % blind_hidden)
	_check("the local player looking at it gets the white screen", screen > 0.5, "%.2f s" % screen)
	_check("no blast damage from a flashbang", _health(open_ai) >= 99.0, "health %.0f" % _health(open_ai))

	# ── 3. smoke ───────────────────────────────────────────────────────────────────────────────
	print("\n=== 3. SMO1 smoke ===")
	var p3 := await _armed(Vector3(200, 0.05, 0), "SMO1", 1)
	var g3 := await _throw(p3)
	_check("SMO1 throws a projectile", g3 != null, "")
	var cloud: Node3D = null
	for i in range(300):
		await physics_frame
		for n in world.get_children():
			if n.name.begins_with("SmokeCloud"):
				cloud = n
		if cloud != null and cloud.call("radius_now") > 4.5:
			break
	_check("a smoke cloud forms and grows", cloud != null and cloud.call("radius_now") > 4.5,
		"radius %.2f" % (cloud.call("radius_now") if cloud != null else -1.0))
	if cloud != null:
		var c := cloud.global_position + Vector3(0, 1.2, 0)
		_check("a sight line THROUGH the cloud is blocked", cloud.call("blocks_sight_now", c + Vector3(-15, 0, 0), c + Vector3(15, 0, 0)), "")
		_check("a sight line 8 m beside it is not", not cloud.call("blocks_sight_now", c + Vector3(-15, 0, 8), c + Vector3(15, 0, 8)), "")

	# ── 4. remote charge ───────────────────────────────────────────────────────────────────────
	print("\n=== 4. REC1 remote charge ===")
	var p4 := await _armed(Vector3(300, 0.05, 0), "REC1", 2)
	var land4 := _landing(p4)
	var near_ai := await _ai_at(land4 + Vector3(1.5, 0, 0))
	var h4 := _health(near_ai)
	var c1 := await _throw(p4)
	await _tick(40)
	var c2 := await _throw(p4)
	await _tick(300)
	_check("two charges thrown", c1 != null and c2 != null, "")
	_check("both stuck where they landed", c1 != null and c2 != null and c1.call("stuck_now") and c2.call("stuck_now"), "")
	_check("they do not go off by themselves (5 s)", is_instance_valid(c1) and is_instance_valid(c2), "")
	_check("the thrower has 2 armed", p4.call("armed_charges_now") == 2, "armed %d" % p4.call("armed_charges_now"))
	_check("the AI is unhurt before the detonator", _health(near_ai) == h4, "health %.0f" % _health(near_ai))
	Input.action_press("detonate")
	await _tick(2)
	Input.action_release("detonate")
	await _tick(10)
	_check("the detonator sets both off", not is_instance_valid(c1) and not is_instance_valid(c2), "")
	_check("the thrower has none armed after", p4.call("armed_charges_now") == 0, "armed %d" % p4.call("armed_charges_now"))
	_check("the AI next to them is hurt", _health(near_ai) < h4, "health %.0f -> %.0f" % [h4, _health(near_ai)])

	print("\n%s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
