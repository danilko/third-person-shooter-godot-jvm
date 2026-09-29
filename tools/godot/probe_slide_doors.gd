extends SceneTree
## A SLIDING door (a shop's 自動ドア, a restroom's 引き戸, a station store's glass front) must OPEN for a character
## standing in front of it and STAY open while they stand there (user, 2026-09-28: the station's accessible restroom
## door "keeps trying to open but immediately slides back"). probe_buildings.gd drives each door directly, so it cannot
## see a door that chatters; this one stands a real AICharacter in front of every sliding door, by its own sensor.
##
##   godot --headless --path . --script tools/godot/probe_slide_doors.gd [-- --scenes=Id,Id]
## Default: a konbini and three stations. CONTROL: `-- --control` gives each sliding leaf its sensor back as a child
## (the old build), and the long single leaves fail.

const DIR := "res://src/main/resources/com/openworld/world/buildings"
const BODY := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
var _fails := 0
var _passes := 0

func _check(ok: bool, msg: String) -> void:
	if ok:
		_passes += 1
	else:
		_fails += 1
	print(("  PASS  " if ok else "  FAIL  ") + msg)

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var ids := ["KonbiniL_Shop", "Station_Farm_Shop", "Station_Bay_Shop", "Station_Central_Shop"]
	var control := false
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--scenes="):
			ids = a.substr(9).split(",")
		elif a == "--control":
			control = true
	var body: CharacterBody3D = (load(BODY) as PackedScene).instantiate()
	body.process_mode = Node.PROCESS_MODE_DISABLED
	# a disabled CollisionObject leaves the physics space by default; keep it there so the sensor sees it
	body.disable_mode = CollisionObject3D.DISABLE_MODE_KEEP_ACTIVE
	root.add_child(body)
	body.global_position = Vector3(0, -500, 0)
	for id in ids:
		var inst: Node3D = (load("%s/%s.tscn" % [DIR, id]) as PackedScene).instantiate()
		root.add_child(inst)
		await physics_frame
		var doors := inst.get_node_or_null("Doors")
		var tried := 0
		var held := 0
		for d in ([] if doors == null else doors.get_children()):
			if str(d.get("open_mode")) != "SLIDE" or not bool(d.get("auto_open")):
				continue
			var sensor: Node3D = d.get_node_or_null(d.get("sensor_path"))
			if sensor == null:
				_check(false, "%s %s has a sensor" % [id, d.name])
				continue
			if control and sensor.get_parent() != d:
				var xf: Transform3D = sensor.global_transform
				sensor.reparent(d)
				sensor.global_transform = xf
				d.set("sensor_path", NodePath(str(sensor.name)))
			tried += 1
			var closed: Vector3 = d.position
			var want: float = (d.get("slide_offset") as Vector3).length()
			# stand 0.8 m in front of the doorway, on the side the leaf is hung (local +Z), feet on the floor
			var sxf: Transform3D = sensor.global_transform
			body.global_position = sxf.origin + sxf.basis.z.normalized() * 0.8 + Vector3(0, 0.05, 0)
			for i in 90:
				await physics_frame
			var a: float = ((d.position as Vector3) - closed).length()
			var track := []
			for i in 60:
				await physics_frame
				track.append(((d.position as Vector3) - closed).length())
			var lo: float = track.min()
			if a >= want * 0.9 and lo >= want * 0.9:
				held += 1
			else:
				_check(false, "%s %s (%.2f m slide): open %.2f m after 1.5 s, least %.2f m over the next 1 s" % [
					id, d.name, want, a, lo])
			body.global_position = Vector3(0, -500, 0)
			for i in 90:
				await physics_frame
		_check(tried > 0 and held == tried, "%s: %d of %d sliding doors open for a character and stay open" % [id, held, tried])
		inst.queue_free()
		await physics_frame
	print("RESULT %s (%d passed, %d failed)" % ["PASS" if _fails == 0 else "FAIL", _passes, _fails])
	quit(1 if _fails else 0)
