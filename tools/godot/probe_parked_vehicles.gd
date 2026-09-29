extends SceneTree
## PARKED VEHICLES in the mission buildings (user, 2026-09-28): every MARK_vehicle that names a model spawns that
## model, drivable, where the building says -- and a building streamed in again spawns no second one.
##   stdbuf -oL <godot> --headless --path . --script tools/godot/probe_parked_vehicles.gd [-- --scene=<X_Shop.tscn>]
##
##   1. the building carries its ParkedVehicle markers;
##   2. each spawns ONE vehicle of its model (a Vehicle, not a child of the building), set down on the floor at the
##      marker: after settling it rests within 0.6 m of the marker in plan, on its wheels (its body origin 0.8 m up, the model hanging under it), its nose
##      the way the marker faces (within 10 deg);
##   3. the building freed and instanced again (a cell streaming out and back in) spawns NOTHING new while the
##      first vehicles exist.

const SCENES := ["FireStation_Shop", "FireBranch_Shop", "Hospital_Shop", "PoliceStation_Shop", "WarehouseYard_Shop",
		"SupermarketSite_Shop", "MilHangar_Shop", "MilitaryBase_Shop", "AirportAirside_Shop"]
const DIR := "res://src/main/resources/com/openworld/world/buildings/"
var fails := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-70s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _find(n: Node, out: Array) -> void:
	if n.has_method("spawned_now"):
		out.append(n)
	for c in n.get_children():
		_find(c, out)

func _vehicles() -> Array:
	var out := []
	for n in current_scene.get_children():
		if n.has_method("get_boost_fraction") or n.is_in_group("streamed_vehicle"):
			out.append(n)
	return out

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var only := ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--scene="):
			only = a.substr(8).get_file().get_basename()
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(4000, 0.2, 400)
	cs.shape = box
	floor.add_child(cs)
	floor.position = Vector3(0, -0.1, 0)
	world.add_child(floor)
	var x := 0.0
	for sid in SCENES:
		if only != "" and sid != only:
			continue
		print("== %s" % sid)
		var ps: PackedScene = load(DIR + sid + ".tscn")
		var b: Node3D = ps.instantiate()
		b.position = Vector3(x, 0, 0)
		x += 150.0
		world.add_child(b)
		await _tick(2)
		var marks := []
		_find(b, marks)
		_check("1. %d parked-vehicle markers" % marks.size(), not marks.is_empty())
		await _tick(240)
		for m in marks:
			var v: Node3D = m.spawned_now()
			var label := "2. %s at %s" % [m.get("vehicle_id"), m.name]
			if v == null:
				_check(label + " spawned", false)
				continue
			var d: Vector3 = v.global_position - (m as Node3D).global_position
			var fwd: Vector3 = -v.global_transform.basis.z
			var want: Vector3 = -(m as Node3D).global_transform.basis.z
			var ang := rad_to_deg(Vector2(fwd.x, fwd.z).angle_to(Vector2(want.x, want.z)))
			var model := str(v.scene_file_path).get_file().get_basename()
			_check(label + ": the model, on the floor, facing the marker's way", model == str(m.get("vehicle_id"))
				and v.get_parent() != b and Vector2(d.x, d.z).length() < 0.6 and absf(ang) < 10.0 and d.y < 1.2
				and d.y > -0.2, "%s  plan %.2f m  y %+.2f  yaw off %.1f" % [model, Vector2(d.x, d.z).length(), d.y, ang])
		var before := _vehicles().size()
		var bpos := b.position
		b.queue_free()
		await _tick(3)
		var b2: Node3D = ps.instantiate()
		b2.position = bpos
		world.add_child(b2)
		await _tick(20)
		_check("3. streamed in again: no second set of vehicles", _vehicles().size() == before,
			"%d -> %d vehicles" % [before, _vehicles().size()])
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
