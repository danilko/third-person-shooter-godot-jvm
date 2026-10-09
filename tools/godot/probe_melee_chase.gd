extends SceneTree
## Does a melee-armed AI CLOSE on a hostile player? (the "AI only hits when very close" report, 2026-10-09). Bare flat
## stand, a still Player and an AICharacter (faction enemy) armed with MEW1 through a pickup, --dist m apart. Logs the
## AI's distance, state and speed every second; asserts it reaches 2.5 m and lands damage within 20 s.
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_melee_chase.gd [-- --dist=25] [--weapon=MEW1]
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"

func _arg(name: String, def = null):
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--" + name + "="):
			return a.substr(name.length() + 3)
	return def

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _initialize() -> void:
	var dist := float(_arg("dist", "25"))
	var wid := String(_arg("weapon", "MEW1"))
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(400, 2, 400)
	cs.shape = sh
	floor.add_child(cs)
	floor.position = Vector3(0, -1, 0)
	world.add_child(floor)
	world.add_child(load("res://src/main/java/com/openworld/world/manager/ImpactManager.java").new())
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate()
	p.position = Vector3(0, 0.2, 0)
	world.add_child(p)
	var h: Node = p.get_node("Health")
	await _tick(10)
	h.set("max_health", 100000.0)
	h.call("apply_replicated_health", 100000.0)
	var ai: Node3D = (load(AI) as PackedScene).instantiate()
	var info: Resource = ai.get("character_info")
	ai.position = Vector3(0, 0.2, -dist)
	world.add_child(ai)
	await _tick(5)
	ai.get("character_info").set("faction", "enemy")
	var gun: Node3D = (load("res://src/main/resources/com/openworld/weapon/%s.tscn" % wid) as PackedScene).instantiate()
	world.add_child(gun)
	gun.global_position = ai.global_position + Vector3(0, 0.3, 0)
	var h0 := float(h.call("health_now"))
	var best := 1e9
	var hit_at := -1.0
	for s in 25:
		await _tick(60)
		var d: float = Vector2(ai.global_position.x - p.global_position.x, ai.global_position.z - p.global_position.z).length()
		best = minf(best, d)
		var st := "-"
		for c in ai.get_children():
			if c.has_method("current_state_name_now"):
				st = String(c.call("current_state_name_now"))
		var lost := h0 - float(h.call("health_now"))
		if lost > 0 and hit_at < 0:
			hit_at = s + 1
		print("t=%2d d %5.1f %s v%.1f swings %d held %s lost %.0f" % [s + 1, d, st, ai.velocity.length(), int(ai.get_node("WeaponController").call("fires_now")),
				ai.get_node("WeaponController").call("get_current_weapon_id_now"), lost])
	print("RESULT %s closest %.1f m, first damage at %s s" % ["PASS" if best < 2.5 and hit_at > 0 else "FAIL", best, hit_at])
	quit(0)
