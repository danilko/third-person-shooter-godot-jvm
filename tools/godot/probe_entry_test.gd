extends SceneTree
## The VEHICLE ENTRY comparison (user, 2026-10-04: "build one test street for comparison"). The EntryTest street
## (tools/roadkit_entry_test.py: one lane each way, 3 m footways, 15 cm kerbs) on the ground the ISLAND gives a street:
## stamped 10 cm under the asphalt out to `island_ground.KERB_KEEP` past the kerb, and the block ground at footway - 2 cm
## (0.13 m, `island_buildings.LOT_RAISE`) from there back, under the footway's outer part and on into the lot. Four kerbs, side by side:
##
##     x =  30  the ordinary kerb (no entry)
##     x =  50  DROP          the 切り下げ: a 5 cm lip, the footway sloping up to its own height at the property line
##     x = 100  DROP_ASPHALT  the same, the lowered footway in asphalt
##     x = 150  CUT           the kerb and footway removed, the ground exposed
##
## For each: the SURFACE PROFILE from the lane to the lot (every step over 2 cm named), then a real drive straight in
## from the far lane -- the low SPC-1 coupe and the CRT-1 truck, a constant throttle through VehicleProbeHelper --
## reporting whether it reaches the lot, the worst vertical jolt (the change of vertical speed in one tick) and any
## stall. It asserts nothing: it is the comparison the user asked for, printed side by side.
##
##   godot --headless --fixed-fps 60 --path . --script tools/godot/probe_entry_test.gd
##   godot --path . --script tools/godot/probe_entry_test.gd -- --shot=<dir>     (pictures; needs a display)

const PIECE := "res://src/main/resources/com/openworld/world/pieces/Roads_EntryTest.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const LOT_MAT := "res://assets/world_source/buildings/materials/M_LotConcrete.tres"
const CARS := ["SPC1", "CRT1"]
const CASES := [[30.0, "ordinary kerb"], [50.0, "DROP"], [100.0, "DROP_ASPHALT"], [150.0, "CUT"]]
const STAMPED := -0.10          # the ground under a road band (road_kit_stamp CLEARANCE)
const LOT_TOP := 0.13           # the block ground: footway 0.15 + LOT_RAISE (-0.02 since 2026-10-04)
const KERB_KEEP := 1.25         # island_ground: the block ground reaches under the footway beyond this from the kerb
const ENTRY_SPEED := 3.0       # m/s (~11 km/h): a car turning into a lot, not a run at the kerb
const EDGE := 7.5               # the property line: paved half 4.5 + footway 3.0 (Godot z = -EDGE on the left)

var world: Node3D
var helper: Node

func _arg(name: String, def: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--%s=" % name):
			return a.substr(name.length() + 3)
	return def

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _slab(x0: float, x1: float, z0: float, z1: float, top: float, mat: Material) -> void:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(x1 - x0, 1.0, z1 - z0)
	cs.shape = box
	b.add_child(cs)
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = box.size
	bm.material = mat
	mi.mesh = bm
	b.add_child(mi)
	b.position = Vector3((x0 + x1) * 0.5, top - 0.5, (z0 + z1) * 0.5)
	world.add_child(b)

func _top(x: float, z: float) -> float:
	var space := world.get_world_3d().direct_space_state
	var rq := PhysicsRayQueryParameters3D.create(Vector3(x, 5.0, z), Vector3(x, -5.0, z))
	var hit := space.intersect_ray(rq)
	return hit.position.y if hit else NAN

func _profile(x: float) -> String:
	var steps := []
	var prev := NAN
	var line := ""
	var z := 1.0
	while z >= -12.0:
		var h := _top(x, z)
		if not is_nan(prev) and absf(h - prev) > 0.02:
			steps.append("%+.2f m at z %.1f" % [h - prev, z])
		prev = h
		z -= 0.05
	for zz in [-3.0, -4.4, -4.6, -6.0, -7.4, -7.6, -10.0]:
		line += " %.1f:%+.3f" % [zz, _top(x, zz)]
	return "   surface (z:height)%s\n   steps %s" % [line, ", ".join(steps) if steps else "none"]

func _drive(id: String, x: float) -> String:
	var v: RigidBody3D = (load("res://src/main/resources/com/openworld/vehicle/%s.tscn" % id) as PackedScene).instantiate()
	world.add_child(v)
	v.global_position = Vector3(x, 1.2, 2.5)
	v.rotation = Vector3.ZERO                       # nose -Z: across the street toward the left lot
	helper.drive_craft(v, 0.0, 0.0, false)
	await _tick(90)                                  # settle on the road
	helper.drive_craft(v, 0.35, 0.0, false)
	var worst := 0.0
	var worst_at := 0.0
	var vy_prev := v.linear_velocity.y
	var stalled := 0.0
	var t := 0.0
	var reached := false
	var top_speed := 0.0
	while t < 12.0:
		await physics_frame
		t += 1.0 / 60.0
		var vy := v.linear_velocity.y
		if absf(vy - vy_prev) > worst:
			worst = absf(vy - vy_prev)
			worst_at = v.global_position.z
		vy_prev = vy
		var sp := Vector2(v.linear_velocity.x, v.linear_velocity.z).length()
		top_speed = maxf(top_speed, sp)
		helper.drive_craft(v, 0.35 if sp < ENTRY_SPEED else 0.0, 0.0, false)     # hold a turning-in speed
		stalled = stalled + 1.0 / 60.0 if (t > 1.5 and sp < 0.3) else 0.0
		if v.global_position.z < -14.0:
			reached = true
			break
		if stalled > 1.5:
			break
	var out := "   %-5s %s in %.1f s, worst jolt %.2f m/s at z %.1f, top speed %.1f m/s%s" % [
		id, "REACHED the lot" if reached else "did NOT reach the lot", t, worst, worst_at, top_speed,
		"  (stalled at z %.1f)" % v.global_position.z if stalled > 1.5 else ""]
	v.queue_free()
	await _tick(2)
	return out

func _shots(dir: String) -> void:
	DirAccess.make_dir_recursive_absolute(dir)
	var cam := Camera3D.new()
	world.add_child(cam)
	cam.current = true
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55.0, 30.0, 0.0)
	world.add_child(sun)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.62, 0.72, 0.82)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color(0.7, 0.7, 0.7)
	world.add_child(env)
	for c in CASES:
		var x: float = c[0]
		for view in [["street", Vector3(x + 7.0, 1.7, 1.0), Vector3(x, 0.0, -6.0)],
				["above", Vector3(x + 0.01, 9.0, -3.0), Vector3(x, 0.0, -6.0)]]:
			cam.look_at_from_position(view[1], view[2])
			await process_frame
			await process_frame
			RenderingServer.force_draw()
			await process_frame
			var img := root.get_viewport().get_texture().get_image()
			var path := "%s/entry_%s_%s.png" % [dir, String(c[1]).to_lower().replace(" ", "_"), view[0]]
			img.save_png(path)
			print("   saved %s" % path)
	var overview := [Vector3(90.0, 14.0, 14.0), Vector3(90.0, 0.0, -6.0)]
	cam.look_at_from_position(overview[0], overview[1])
	await process_frame
	RenderingServer.force_draw()
	await process_frame
	root.get_viewport().get_texture().get_image().save_png("%s/entry_overview.png" % dir)

func _initialize() -> void:
	world = Node3D.new()
	root.add_child(world)
	await process_frame
	helper = load(HELPER).new()
	world.add_child(helper)
	var piece: Node3D = (load(PIECE) as PackedScene).instantiate()
	world.add_child(piece)
	var lot: Material = load(LOT_MAT)
	var kerb_line := 4.5
	_slab(-20.0, 220.0, -(kerb_line + KERB_KEEP), kerb_line + KERB_KEEP, STAMPED, lot)   # the stamped ground at the kerb
	_slab(-20.0, 220.0, -40.0, -EDGE, LOT_TOP, lot)                   # the block ground behind the property line...
	# ...and under the footway's outer part, except under a DROPPED entry (and its ramps, + 1 m), where island_ground
	# caps it at the lip less 2 cm so it can never stand through the lowered paving
	var x := -20.0
	for e in [50.0, 100.0]:
		_slab(x, e - 5.5, -EDGE, -(kerb_line + KERB_KEEP), LOT_TOP, lot)
		_slab(e - 5.5, e + 5.5, -EDGE, -(kerb_line + KERB_KEEP), 0.03, lot)
		x = e + 5.5
	_slab(x, 220.0, -EDGE, -(kerb_line + KERB_KEEP), LOT_TOP, lot)
	_slab(-20.0, 220.0, kerb_line + KERB_KEEP, 40.0, LOT_TOP, lot)
	await _tick(4)
	var shot := _arg("shot", "")
	if shot != "":
		await _shots(shot)
	for c in CASES:
		print("── x %.0f  %s" % [c[0], c[1]])
		print(_profile(c[0]))
		if shot == "":
			for id in CARS:
				print(await _drive(id, c[0]))
	print("RESULT done")
	quit(0)
