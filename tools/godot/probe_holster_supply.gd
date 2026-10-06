extends SceneTree
## THE HOLSTER KEY AND HEALING SUPPLIES AS A WEAPON (user, 2026-10-06). A real Player on a bare stand, driven through
## Input:
##   1. a body starts holstered; holding aim + fire while holstered gives NO combat (no aim, nothing to alarm anyone);
##   2. H (`holster`) with empty hands raises the fists, H again drops them;
##   3. a supply stack lying at the feet is collected into the CONSUMABLE slot; key 6 draws it (not holstered);
##   4. hurt, FIRE eats one and heals the player;
##   5. a hurt AI 1.8 m ahead: holding AIM outlines it (an overlay material on its meshes), FIRE heals IT, not the
##      player, and letting go of aim removes the outline;
##   6. H with the stack in hand puts it away (holstered), H again brings the same stack back.
##
##   <godot> --headless --path . --script tools/godot/probe_holster_supply.gd [-- --control]
##   --control: the stack's give reach is 0, so case 5 heals the player instead (fails the case-5 checks).
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const SUPPLY := "res://src/main/resources/com/openworld/weapon/Supply.tscn"

var world: Node3D
var fails := 0
var checks := 0


func _check(what: String, ok: bool, detail: String = "") -> void:
	checks += 1
	if not ok:
		fails += 1
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", what, detail])


func _tick(n: int) -> void:
	for i in n:
		await physics_frame


func _tap(action: String) -> void:
	Input.action_press(action)
	await physics_frame
	await process_frame
	Input.action_release(action)
	await _tick(2)


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	world = Node3D.new()
	root.add_child(world)
	current_scene = world
	var ground := StaticBody3D.new()
	var gs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(80, 1, 80)
	gs.shape = box
	ground.add_child(gs)
	world.add_child(ground)
	ground.position = Vector3(0, -0.5, 0)
	await _tick(3)

	var p := (load(PLAYER) as PackedScene).instantiate() as CharacterBody3D
	world.add_child(p)
	p.position = Vector3(0, 0.1, 0)
	await _tick(40)
	var wc: Node = p.get_node("WeaponController")
	var h: Node = p.get_node("Health")
	var mh := float(h.get("max_health"))

	print("=== 1. holstered: aim + fire do nothing ===")
	_check("the player starts holstered", bool(wc.call("holstered_now")))
	Input.action_press("aim")
	Input.action_press("fire")
	await _tick(12)
	var combat := bool(p.call("combat_now"))
	Input.action_release("fire")
	Input.action_release("aim")
	await _tick(4)
	_check("holding aim + fire while holstered: no combat", not combat and bool(wc.call("holstered_now")),
			"combat %s" % combat)

	print("=== 2. H toggles the hands ===")
	await _tap("holster")
	var up := not bool(wc.call("holstered_now"))
	await _tap("holster")
	_check("H raises the fists, H again drops them", up and bool(wc.call("holstered_now")))

	print("=== 3. a supply stack is collected and drawn with key 6 ===")
	var stack: Node3D = (load(SUPPLY) as PackedScene).instantiate()
	stack.set("supply_id", "bandage")
	world.add_child(stack)
	stack.global_position = p.global_position + Vector3(0, 0.6, 0)
	await _tick(30)
	var n0 := int(p.call("supply_count_now", "bandage"))
	_check("the stack is in the consumable slot", n0 == 5, "%d bandages" % n0)
	await _tap("weapon_slot_6")
	await _tick(60)
	_check("key 6 draws it (not holstered)", not bool(wc.call("holstered_now")))

	print("=== 4. fire: used on yourself ===")
	h.call("apply_replicated_health", mh - 40.0)
	await _tap("fire")
	await _tick(6)
	var self_heal := float(h.call("health_now")) - (mh - 40.0)
	_check("fire eats one and heals the player", self_heal > 20.0 and int(p.call("supply_count_now", "bandage")) == n0 - 1,
			"+%.0f HP, %d left" % [self_heal, int(p.call("supply_count_now", "bandage"))])

	print("=== 5. aim at someone + fire: used on them, outlined while targeted ===")
	var ai := (load(AI) as PackedScene).instantiate() as CharacterBody3D
	world.add_child(ai)
	ai.global_position = Vector3(0, 0.1, -1.8)
	await _tick(10)
	for n in ["MovementController", "AIController"]:
		var c: Node = ai.get_node_or_null(n)
		if c != null:
			c.process_mode = Node.PROCESS_MODE_DISABLED
	ai.global_position = Vector3(0, 0.1, -1.8)
	var item: Node = null
	for c in p.find_children("*", "", true, false):
		if c.get_script() != null and str(c.get_script().resource_path).ends_with("SupplyItem.java"):
			item = c
	if control and item != null:
		item.set("give_reach", 0.0)
	var ah: Node = ai.get_node("Health")
	var amh := float(ah.get("max_health"))
	ah.call("apply_replicated_health", amh - 40.0)
	h.call("apply_replicated_health", mh - 40.0)
	await _tick(60)                                   # one use a second: let the last one's interval run out
	Input.action_press("aim")
	await _tick(20)
	var outlined := str(item.call("outlined_now")) if item != null else ""
	var ai_id := str(ai.get("character_info").get("character_id"))
	var overlays := 0
	for m in ai.find_children("*", "MeshInstance3D", true, false):
		if (m as MeshInstance3D).material_overlay != null:
			overlays += 1
	_check("aiming at the AI outlines it", outlined == ai_id and overlays > 0,
			"outlined '%s', %d meshes with the overlay" % [outlined, overlays])
	await _tap("fire")
	await _tick(6)
	var ai_heal := float(ah.call("health_now")) - (amh - 40.0)
	var me_heal := float(h.call("health_now")) - (mh - 40.0)
	_check("fire while aiming at it heals the AI, not the player", ai_heal > 20.0 and me_heal < 1.0,
			"AI +%.0f, player +%.0f" % [ai_heal, me_heal])
	Input.action_release("aim")
	await _tick(6)
	overlays = 0
	for m in ai.find_children("*", "MeshInstance3D", true, false):
		if (m as MeshInstance3D).material_overlay != null:
			overlays += 1
	_check("letting go of aim removes the outline", overlays == 0, "%d meshes still outlined" % overlays)

	print("=== 6. H puts the stack away and brings it back ===")
	await _tap("holster")
	await _tick(60)
	var away := bool(wc.call("holstered_now"))
	await _tap("holster")
	await _tick(60)
	var back := not bool(wc.call("holstered_now")) and int(wc.call("active_slot_now")) == 6
	_check("H holsters the stack, H again draws it back", away and back,
			"holstered %s, then slot %d" % [away, int(wc.call("active_slot_now"))])

	print("RESULT %s (%d/%d)" % ["PASS" if fails == 0 else "FAIL", checks - fails, checks])
	quit(0 if fails == 0 else 1)
