extends SceneTree
## WHAT DOES A TRAFFIC CAR COST PER PHYSICS TICK, AND WHICH PART OF IT (PLAN.md 2d, measure before the dummy tier).
##
##   stdbuf -oL godot --headless --path . --script tools/godot/bench_traffic_cost.gd [-- --at=x,z] [--secs=6]
##
## World.tscn, the player parked downtown, traffic filled to its budget. Then the physics-process time
## (Performance.TIME_PHYSICS_PROCESS, ms per tick) is averaged over --secs for each mode, cumulative:
##   base        -- as shipped
##   drivers     -- every SEATED character's processing off (its AnimationTree, skeleton, controller)
##   damage      -- + every car's VehicleDamageModel processing off
##   cars        -- + every traffic car frozen with its processing off (= what is left is NOT traffic)
## The differences are the per-part cost; divided by the car count, the per-car cost.

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"

var args := {}


func _arg(k: String, d = null):
	return args.get(k, d)


func _cars() -> Array:
	var out := []
	for n in get_nodes_in_group("characters"):
		if n is RigidBody3D and n.get_node_or_null("DamageModel") != null:
			out.append(n)
	return out


func _measure(secs: float) -> float:
	var sum := 0.0
	var n := 0
	var t0 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < secs * 1000.0:
		await physics_frame
		sum += Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0
		n += 1
	return sum / max(1, n)


func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=", true, 1)
		args[kv[0]] = kv[1] if kv.size() > 1 else true
	var at := Vector2(500, -100)
	if _arg("at") != null:
		var p: PackedStringArray = str(_arg("at")).split(",")
		at = Vector2(float(p[0]), float(p[1]))
	var secs := float(_arg("secs", "6"))
	var w: Node = (load(WORLD) as PackedScene).instantiate()
	for k in ["PedZones"]:
		var h := w.get_node_or_null(k)
		if h != null:
			w.remove_child(h)
			h.free()
	root.add_child(w)
	current_scene = w
	var zm := root.get_node_or_null("ZoneManager")
	if zm != null:
		zm.set("debug_log", false)
	var player: Node3D = w.get_node("Characters/Player")
	player.set_physics_process(false)
	player.global_position = Vector3(at.x, 7.0, at.y)
	for i in 60 * 40:
		await physics_frame
		if i > 600 and _cars().size() >= int(zm.get("traffic_budget")) and int(zm.call("streaming_pending_now")) == 0:
			break
	for i in 120:
		await physics_frame
	var cars := _cars()
	var drivers := []
	for n in get_nodes_in_group("characters"):
		if n is CharacterBody3D and n.get("current_vehicle_node") != null:
			drivers.append(n)
	print("bench_traffic_cost: %d cars, %d drivers" % [cars.size(), drivers.size()])
	var base := await _measure(secs)
	for d in drivers:
		(d as Node).process_mode = Node.PROCESS_MODE_DISABLED
	var no_drivers := await _measure(secs)
	for c in cars:
		var dm := (c as Node).get_node_or_null("DamageModel")
		if dm != null:
			dm.process_mode = Node.PROCESS_MODE_DISABLED
	var no_damage := await _measure(secs)
	for c in cars:
		(c as RigidBody3D).freeze = true
		(c as Node).process_mode = Node.PROCESS_MODE_DISABLED
	var no_cars := await _measure(secs)
	var n: int = max(1, cars.size())
	print("  base        %.2f ms/tick" % base)
	print("  drivers off %.2f ms/tick  (seated drivers %.3f ms per car)" % [no_drivers, (base - no_drivers) / n])
	print("  damage off  %.2f ms/tick  (damage model %.3f ms per car)" % [no_damage, (no_drivers - no_damage) / n])
	print("  cars off    %.2f ms/tick  (car body + wheels + AI %.3f ms per car)" % [no_cars, (no_damage - no_cars) / n])
	print("  traffic total %.2f ms/tick = %.3f ms per car" % [base - no_cars, (base - no_cars) / n])
	quit(0)
