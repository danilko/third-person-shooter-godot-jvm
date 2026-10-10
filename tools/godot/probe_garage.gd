extends SceneTree
## The safe house's GARAGE (PLAN.md 1.4 / F4, 2026-10-10: world.Garage, PlayerProfile.vehicles), on the real World.tscn.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_garage.gd
##
## 1. the world has a HomeGarage beside the starting car, and its bay is clear;
## 2. control: a car merely DROPPED in the bay (nobody drove it there) is not kept;
## 3. the player drives a KET1 in (seated in the bay), gets out, it stops: it is KEPT -- one profile row (its id, its
##    model, garage "home", its condition) and it is in the owned group (streaming never reclaims it);
## 3b. driven out of the bay it is still the player's but its row names no garage; driven back in it is kept again;
## 4. the profile is written and read back from its FILE, the world is loaded again: the car is back in the bay, with
##    the same id (so the same paint) and its damage.

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const KET1 := "res://src/main/resources/com/openworld/vehicle/KET1.tscn"

var fails := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _wait(cond: Callable, limit: int) -> bool:
	for i in range(limit):
		if cond.call():
			return true
		await physics_frame
	return cond.call()

func _car(at: Transform3D, id: String) -> Node3D:
	var v: Node3D = (load(KET1) as PackedScene).instantiate() as Node3D
	var info: Resource = load("res://src/main/java/com/openworld/character/CharacterInfo.java").new()
	info.set("character_id", id)
	v.set("character_info", info)
	current_scene.add_child(v)
	v.global_transform = Transform3D(at.basis, at.origin + Vector3(0, 0.4, 0))
	return v

func _initialize() -> void:
	var saves: Node = root.get_node("SaveSystem")
	var reg: Node = root.get_node("PlayerRegistry")
	saves.set("autosave_enabled", false)
	change_scene_to_file(WORLD)
	var up := await _wait(func(): return reg.call("local_player_now") != null and current_scene != null \
		and current_scene.get_node_or_null("HomeGarage") != null, 3600)
	_check("World.tscn has a HomeGarage beside the starting car", up)
	if not up:
		print("RESULT: FAIL (%d failure(s))" % (fails))
		quit(1)
		return
	var g: Node3D = current_scene.get_node("HomeGarage")
	var start: Node3D = current_scene.get_node("VehicleRoot")
	_check("... one bay from it", absf(g.global_position.distance_to(start.global_position) - 2.5) < 0.6
		or absf(g.global_position.distance_to(start.global_position) - 5.0) < 0.6,
		"%.2f m" % g.global_position.distance_to(start.global_position))
	_check("... marked on the ground (4 painted strips, no HUD)", g.get_child_count() == 4, str(g.get_child_count()))
	var p: Node3D = reg.call("local_player_now")
	var helper: Node = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
	current_scene.add_child(helper)
	await _tick(30)

	print("=== 2. control: a car merely dropped in the bay ===")
	var dropped := _car(g.global_transform, "probe-dropped-car")
	await _tick(120)
	_check("is not kept (nobody drove it in)", int(g.call("stores_now")) == 0 and String(saves.call("profile_vehicles_now")) == "",
		String(saves.call("profile_vehicles_now")))
	dropped.queue_free()
	await _tick(10)

	print("=== 3. the player drives one in and gets out ===")
	var car := _car(g.global_transform, "probe-garage-car")
	await _tick(30)
	var health: Node = car.get_node("Health")
	health.call("apply_replicated_health", float(health.get("max_health")) * 0.6)
	helper.call("seat_driver", car, p)
	await _tick(60)
	_check("the player is driving it in the bay", helper.call("occupant_of", car) == p and bool(g.call("contains_now", car.global_position)), "")
	helper.call("exit_driver", car)
	var kept := await _wait(func(): return int(g.call("stores_now")) == 1, 600)
	var rows := String(saves.call("profile_vehicles_now"))
	_check("got out, it stopped: KEPT in the profile", kept and rows.begins_with("probe-garage-car|") and rows.contains("KET1.tscn|home|0.60"), rows)
	_check("... and owned (streaming never reclaims it)", car.is_in_group("owned_vehicle"), "")

	print("=== 3b. driven out, then back ===")
	var bay := car.global_transform
	helper.call("seat_driver", car, p)
	await _tick(30)
	car.global_position = bay.origin + bay.basis.z.normalized() * 12.0 + Vector3(0, 0.3, 0)
	var out := await _wait(func(): return String(saves.call("profile_vehicles_now")).contains("KET1.tscn||"), 300)
	_check("driven out: still the player's, no longer in the garage", out and car.is_in_group("owned_vehicle"),
		String(saves.call("profile_vehicles_now")))
	car.global_transform = bay
	car.set("linear_velocity", Vector3.ZERO)
	await _tick(60)
	helper.call("exit_driver", car)
	var again := await _wait(func(): return int(g.call("stores_now")) == 2, 600)
	rows = String(saves.call("profile_vehicles_now"))
	_check("driven back in: kept again, still ONE row", again and rows.contains("|home|") and not rows.contains(";"), rows)

	print("=== 4. from the FILE, after a world reload ===")
	_check("the profile is written", bool(saves.call("flush_profile")), "")
	var from := String(saves.call("reload_profile_now"))
	_check("... and read back from it", from == "file" and String(saves.call("profile_vehicles_now")) == rows, "%s: %s" % [from, saves.call("profile_vehicles_now")])
	change_scene_to_file(WORLD)
	await _tick(10)
	var back := await _wait(func(): return current_scene != null and current_scene.get_node_or_null("HomeGarage") != null \
		and int(current_scene.get_node("HomeGarage").call("restores_now")) == 1, 3600)
	_check("the reloaded world put the car back", back, "")
	if back:
		var g2: Node3D = current_scene.get_node("HomeGarage")
		var found: Node3D = null
		for n in get_nodes_in_group("characters"):
			var ci = n.get("character_info") if n is RigidBody3D else null
			if ci != null and String(ci.get("character_id")) == "probe-garage-car":
				found = n
		_check("... the same car (its id, so its paint) in the bay", found != null and bool(g2.call("contains_now", found.global_position)),
			str(found.global_position) if found != null else "missing")
		if found != null:
			var hf: float = float(found.get_node("Health").call("health_now")) / float(found.get_node("Health").get("max_health"))
			_check("... with its damage (60 %)", absf(hf - 0.6) < 0.02, "%.2f" % hf)
			_check("... and owned", found.is_in_group("owned_vehicle"), "")
	print("RESULT: %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
