extends SceneTree
## BREAKABLE SHOP GLASS (PLAN.md 1g g): in an enterable (`_Shop` / `_Open`) building every shop window is its own
## world.Breakable pane on the WORLD layer -- it stops a ray (a bullet, a body) until it breaks -- and AI sight passes
## an intact pane, so a hostile outside SEES a player inside, fires, the glass breaks and the shots go through.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_shop_glass.gd
##   OW_NO_GLASS_SIGHT=1 ... -- --control     (a pane blocks sight like a wall: the AI never fires at the player)
##
## On DebugWorld's konbini (KonbiniS_Shop, node "Konbini").

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const AI_SCENE := "res://src/main/resources/com/openworld/character/AICharacter.tscn"

var fails := 0


func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1


func _ray(from: Vector3, to: Vector3) -> Dictionary:
	var q := PhysicsRayQueryParameters3D.create(from, to, 1)
	return root.get_world_3d().direct_space_state.intersect_ray(q)


func _pane_of(n: Object) -> Node:
	var x: Node = n as Node
	while x != null:
		if x.is_in_group("glass_pane"):
			return x
		x = x.get_parent()
	return null


func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	var world: Node = (load(DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	for i in 120:
		await physics_frame
	var shop: Node3D = world.get_node("Konbini")
	var panes := []
	for n in get_nodes_in_group("glass_pane"):
		if shop.is_ancestor_of(n):
			panes.append(n)
	print("  %d panes in %s" % [panes.size(), shop.scene_file_path.get_file()])
	_check(panes.size() >= 3, "the enterable konbini's shop windows are breakable panes (%d)" % panes.size())
	if panes.is_empty():
		print("RESULT FAIL (%d failures)" % fails)
		quit(0)
		return
	# the FRONT is the building's +Z; take the pane nearest the front's middle
	var front: Vector3 = shop.global_transform.basis.z.normalized()
	var pane: Node3D = panes[0]
	for p in panes:
		if abs((p as Node3D).position.x) < abs(pane.position.x):
			pane = p
	var glass: CollisionShape3D = pane.get_node("Glass")
	var at: Vector3 = glass.global_position
	var outside := at + front * 4.0
	var inside := at - front * 3.0
	var hit := _ray(outside, inside)
	if not hit.is_empty():
		print("  first hit: %s at %s (pane at %s)" % [(hit["collider"] as Node).get_path(), hit["position"], at])
	_check(not hit.is_empty() and _pane_of(hit["collider"]) == pane, "an intact pane stops a ray through the window")
	var im: Node = get_first_node_in_group("impact_manager")
	var helper: Node = (load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java") as Script).new()
	root.add_child(helper)
	helper.call("weapon_hit_at", im, pane, at, 40.0)
	for i in 3:
		await physics_frame
	hit = _ray(outside, inside)
	var vis: Node3D = pane.get_node("IntactVisual")
	var through := hit.is_empty() or ((hit["position"] as Vector3) - at).dot(front) < -0.5
	_check(through, "a 40-damage hit breaks it and the window is open (nothing in the window's plane)")
	_check(not vis.visible, "the broken pane's glass is hidden")
	pane.call("restore_now")
	for i in 3:
		await physics_frame
	_check(vis.visible and not _ray(outside, inside).is_empty(), "restored: glass back, the window closed again")

	# a hostile outside sees a player inside through intact glass, and shoots the glass out
	var player: CharacterBody3D = world.get_node("Characters/Player")
	player.get_node("Health").set("invulnerable", true)
	player.global_position = Vector3(inside.x, shop.global_position.y + 0.1, inside.z)
	player.velocity = Vector3.ZERO
	player.get_node("MovementController").call("clear_motion")
	var info = load("res://src/main/java/com/openworld/character/CharacterInfo.java").new()
	info.set("character_id", "glass_probe_ai")
	info.set("faction", "enemy")
	var ai: Node3D = (load(AI_SCENE) as PackedScene).instantiate()
	ai.set("character_info", info)
	ai.position = Vector3(outside.x, shop.global_position.y + 0.1, outside.z) + front * 4.0
	world.get_node("Characters").add_child(ai)
	helper.call("give_weapon", ai, "ASR1")
	var broken_at := -1.0
	var t := 0.0
	while t < 25.0:
		for i in 30:
			await physics_frame
		t += 0.5
		for p in panes:
			if bool(p.call("broken_now")):
				broken_at = t
		if broken_at >= 0:
			break
	print("  AI target: '%s'; a pane broken at %.1f s" % [String(ai.call("target_id_now")), broken_at])
	if control:
		_check(broken_at < 0, "control: with glass blocking sight the AI never shoots the window")
	else:
		_check(broken_at >= 0, "the hostile saw the player through the glass and shot the window out (%.1f s)" % broken_at)
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0)
