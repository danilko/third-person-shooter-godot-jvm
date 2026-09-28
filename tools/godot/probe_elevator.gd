extends SceneTree
## A station LIFT carries a real Player from F1 up to the platform (user, 2026-09-27: a lift beside every hub
## platform stair, "big as the stair case", two-leaf doors sliding to both sides, along the track).
##   stdbuf -oL <godot> --headless --path . --script tools/godot/probe_elevator.gd [-- --scene=<Station_X_Shop.tscn>]
##       [--lift=N] [--control]
##
##   1. the station carries a world.Elevator per platform (and a ground hub's annex one), each IDLE with its doors shut;
##   2. with the car at the bottom, the TOP landing is shut: a ray into the shaft through its door opening hits a leaf;
##   3. a player walking up to the bottom door calls it: the doors open (both leaves slide apart) and the doorway is
##      clear;
##   4. the player steps in: the doors shut, the car rises with the player standing in it, and NO landing is open
##      while it moves;
##   5. it arrives exactly at the platform, the player on its floor at platform height;
##   6. the player steps out onto the platform, and the car STAYS there (no ride back without a rider).
## `--control` puts the lift OUT OF SERVICE (it neither opens nor moves): cases 3 to 6 fail, and the rider never
## reaches the platform.

const DEFAULT_SCENE := "res://src/main/resources/com/openworld/world/buildings/Station_Suburb_Shop.tscn"
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
var fails := 0
var world: Node3D

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-66s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _lifts(n: Node, out: Array) -> void:
	if n.has_method("phase_now"):
		out.append(n)
	for c in n.get_children():
		_lifts(c, out)

func _ray(a: Vector3, b: Vector3, exclude: Array) -> Dictionary:
	var q := PhysicsRayQueryParameters3D.create(a, b, 1)
	q.exclude = exclude
	return world.get_world_3d().direct_space_state.intersect_ray(q)

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var control := args.has("--control")
	var scene := DEFAULT_SCENE
	var which := 0
	for a in args:
		if a.begins_with("--scene="):
			scene = a.substr(8)
		elif a.begins_with("--lift="):
			which = int(a.substr(7))
	world = Node3D.new()
	root.add_child(world)
	var st: Node3D = (load(scene) as PackedScene).instantiate()
	world.add_child(st)
	var meta: Dictionary = st.get_meta("building", {}).get("station", {}) if st.has_meta("building") else {}
	var street := float(meta.get("street", 0.0))
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(200, 0.2, 200)
	cs.shape = box
	floor.add_child(cs)
	world.add_child(floor)
	floor.position = Vector3(0, street - 0.1, 0)
	await _tick(3)
	var lifts: Array = []
	_lifts(st, lifts)
	_check("the station carries its lifts", lifts.size() >= 2, "%d" % lifts.size())
	var all_idle := true
	for l in lifts:
		all_idle = all_idle and str(l.phase_now()) == "IDLE" and float(l.door_now()) == 0.0
	_check("every lift rests IDLE, doors shut", all_idle)
	if lifts.is_empty():
		print("RESULT FAIL")
		quit(1)
		return
	var lift: Node3D = lifts[mini(which, lifts.size() - 1)]
	var w := float(lift.get("shaft_width"))
	var rise := float(lift.get("rise"))
	var xf: Transform3D = lift.global_transform
	var low := xf.origin
	var door_x := w / 2.0 + 0.03                      # the landing leaves' plane, along the lift's +X
	var out_dir := xf.basis.x.normalized()
	# 2. the top landing is shut while the car is at the bottom
	var top := low + Vector3(0, rise + 1.0, 0)
	var hit := _ray(top + out_dir * (door_x + 1.0), top, [])
	_check("car at the bottom: the TOP landing is shut", not hit.is_empty() and
		str(hit["collider"].name).begins_with("Landing"), str(hit.get("collider", null)))
	# 3. a player walking up to the bottom door calls it
	if control:
		lift.set("in_service", false)
	var p: CharacterBody3D = (load(PLAYER) as PackedScene).instantiate()
	world.add_child(p)
	p.global_position = low + out_dir * (door_x + 0.8) + Vector3(0, 0.05, 0)
	await _tick(150)
	_check("a player at the bottom door calls it: the doors open", str(lift.phase_now()) == "OPEN" and
		float(lift.door_now()) > 0.99, "%s %.2f" % [lift.phase_now(), lift.door_now()])
	var way := _ray(low + out_dir * (door_x + 0.5) + Vector3(0, 1.0, 0), low + Vector3(0, 1.0, 0), [p.get_rid()])
	_check("...and the doorway is clear into the car", way.is_empty() or not
		str(way["collider"].name).begins_with("Landing"), str(way.get("collider", null)))
	# 4. the player steps in; the car shuts and rises with them
	p.global_position = low + Vector3(0, 0.05, 0)
	var moved_open := false
	var saw_moving := false
	for k in range(900):
		await physics_frame
		if str(lift.phase_now()) == "MOVING":
			saw_moving = true
			for s in [0, 1]:
				var y: float = rise * s + 1.0
				var a := low + Vector3(0, y, 0) + out_dir * (door_x + 0.8)
				var hh := _ray(a, low + Vector3(0, y, 0) + out_dir * (w / 2.0 - 0.3), [p.get_rid()])
				if hh.is_empty():
					moved_open = true
		if int(lift.trips_now()) >= 1 and str(lift.phase_now()) == "OPEN":
			break
	_check("the doors shut and the car moves with the rider", saw_moving, lift.phase_now())
	_check("no landing is open while it moves", saw_moving and not moved_open)
	var dy := p.global_position.y - (low.y + rise)
	_check("it arrives at the platform with the rider on its floor", int(lift.trips_now()) == 1 and
		absf(float(lift.car_height_now()) - rise) < 1e-6 and absf(dy) < 0.12,
		"trips %d  car %.2f  rider %.2f m off the platform" % [lift.trips_now(), lift.car_height_now(), dy])
	# 6. out onto the platform; the car stays
	p.global_position = low + Vector3(0, rise + 0.05, 0) + out_dir * (door_x + 1.2)
	await _tick(20)
	var stood := p.global_position.y - (low.y + rise)
	await _tick(700)
	_check("the rider steps out onto the platform", absf(stood) < 0.15, "%.2f m" % stood)
	_check("...and the car stays there, doors shut", int(lift.stop_now()) == 1 and int(lift.trips_now()) == 1
		and str(lift.phase_now()) == "IDLE", "stop %d trips %d %s" % [lift.stop_now(), lift.trips_now(),
		lift.phase_now()])
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
