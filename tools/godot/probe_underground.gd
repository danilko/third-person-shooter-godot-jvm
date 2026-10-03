extends SceneTree
## UNDER THE MAP (user, 2026-10-03: a rider was left under the island's terrain with no way back). WorldBounds puts a
## body that is more than `underground_depth` under the Terrain3D surface back on the surface at the same spot.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_underground.gd [-- --world=island]
##   ... -- --control      (underground_depth 0: the check is off, and the player stays under the map)
##
##   1. a player put 6 m under the terrain is back on the surface within a second, at the same XZ;
##   2. a player standing normally on the ground is never moved (no false rescue over 3 s).

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"

var fails := 0

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var control := "--control" in args
	var world: Node = (load(ISLAND if "--world=island" in args else DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	for i in 90:
		await physics_frame
	var wb: Node = world.find_child("WorldBounds", true, false)
	if wb == null:
		for n in world.get_children():
			if n.get_script() != null and str(n.get_script().resource_path).ends_with("WorldBounds.java"):
				wb = n
	_check(wb != null, "the world has a WorldBounds")
	if wb == null:
		quit(1)
		return
	if control:
		wb.set("underground_depth", 0.0)
	var player: CharacterBody3D = world.get_node("Characters/Player")
	var spawn: Vector3 = player.global_position
	# 2. standing on the ground: nothing moves it
	var r0 := int(wb.call("underground_rescue_count"))
	for i in 180:
		await physics_frame
	_check(int(wb.call("underground_rescue_count")) == r0 and player.global_position.distance_to(spawn) < 2.0,
			"a player standing on the ground is left alone (moved %.2f m)" % player.global_position.distance_to(spawn))
	# 1. under the map
	var h: float = wb.call("terrain_height", spawn.x + 20.0, spawn.z)
	var under := Vector3(spawn.x + 20.0, h - 6.0, spawn.z)
	player.global_position = under
	player.velocity = Vector3.ZERO
	var back := false
	for i in 90:
		await physics_frame
		if player.global_position.y > h - 0.3:
			back = true
			break
	var p := player.global_position
	print("probe_underground: terrain %.2f at (%.0f, %.0f); player now (%.1f, %.2f, %.1f)" % [h, under.x, under.z, p.x, p.y, p.z])
	if control:
		_check(not back, "control: with the check off the player stays under the map (y %.1f)" % p.y)
	else:
		_check(back and Vector2(p.x, p.z).distance_to(Vector2(under.x, under.z)) < 0.5,
				"a player 6 m under the terrain is put back on the surface at the same spot (y %.2f, terrain %.2f)" % [p.y, h])
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
