extends SceneTree
## SPC-1, the component-damage car (assets/vehicles/SPC1.blend -> SPC1.glb -> SPC1.tscn, VehicleDamageModel).
##
##   godot --headless --path . --script tools/godot/probe_component_car.gd [-- --car=SPC1|PIT1|POC1] [--visuals=res://.../CharacterVisuals_X.tscn] [--control]
##
## 1. the scene agrees with the MEASURED model facts (assets/vehicles/SPC1.vehicle.json, written by
##    blender/tools/build_vehicle.py): wheel mounts, hull, the model offset;
## 2. the modelled wheels replaced the placeholder cylinders, and on a flat floor the settled car puts each one
##    on the ground and inside its own arch;
## 3. a crash at the front dents the front bumper, a harder one takes it off as debris, and crashes cost health;
## 4. bullets through ImpactManager loosen the door they hit;
## 5. a loose door SWINGS under the car's own motion - on a frozen (puppet) body moved kinematically;
## 6. the part mask carried to another car (a remote peer's copy) reproduces every part's state;
## 7. getting in and out swings the door open and shut (a real AI through tryEnter/tryExit), and the open door's
##    own collider is solid only while it is open;
## 8. the destroyed car's wreck is the car burnt, not the grey box.
## `--control` turns the damage model off: every damage case must fail and the geometry cases must still pass.

var CAR := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
var FACTS := "res://assets/vehicles/SPC1.vehicle.json"
const IMPACT := "res://src/main/java/com/openworld/world/manager/ImpactManager.java"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const WHEELS := {"RR": "wheel_rb", "RL": "wheel_lb", "FR": "wheel_rf", "FL": "wheel_lf"}
var PARTS := []
const MODEL_Y := -0.8

var fails := 0

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-44s %s" % ["PASS" if ok else "FAIL", label, detail])

func _floor(parent: Node) -> void:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(200, 1, 200)
	cs.shape = box
	b.add_child(cs)
	b.position = Vector3(0, -0.5, 0)
	parent.add_child(b)

func _skeleton(n: Node) -> Skeleton3D:
	if n is Skeleton3D:
		return n
	for c in n.get_children():
		var r := _skeleton(c)
		if r != null:
			return r
	return null

func _blend(mi: MeshInstance3D) -> float:
	var i := mi.find_blend_shape_by_name("dam")
	return mi.get_blend_shape_value(i) if i >= 0 else -1.0

func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	var vid := "SPC1"
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--car="):
			vid = a.substr(6)
	CAR = "res://src/main/resources/com/openworld/vehicle/%s.tscn" % vid
	FACTS = "res://assets/vehicles/%s.vehicle.json" % vid
	print("== ", vid)
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	_floor(world)
	var facts: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(FACTS))
	for k in facts["pivots"]:
		if k != "chassis":
			PARTS.append(k)
	var nose: float = facts["bounds"]["min"][2]
	var im: Node = load(IMPACT).new()
	world.add_child(im)
	var helper: Node = load(HELPER).new()
	world.add_child(helper)

	var car: Node3D = (load(CAR) as PackedScene).instantiate() as Node3D
	world.add_child(car)
	# Set down at its suspension's resting height, as a spawner should: an UNOCCUPIED car's parking lock zeroes its
	# velocity below 0.5 m/s, and this overdamped suspension is still easing down at that speed, so a car dropped
	# from higher freezes wherever it is mid-settle - its ride height would be the drop's, not the car's.
	var cfg: Resource = car.get("vehicle_config")
	var spring_eq: float = cfg.rest_distance - car.mass * 9.8 / (4.0 * cfg.spring_strength)
	var ride_h: float = cfg.wheel_radius + spring_eq - (car.get_node("Wheels/FL") as Node3D).position.y
	car.position = Vector3(0, ride_h, 0)
	var dm: Node = car.get_node("DamageModel")
	if control:
		dm.set("damage_enabled", false)
	var model: Node3D = car.get_node("Model")
	await _tick(300)

	print("-- 1. the scene agrees with the measured model")
	_check("model sits %.2f m under the body origin" % MODEL_Y, is_equal_approx(model.position.y, MODEL_Y), "y %.3f" % model.position.y)
	for k in WHEELS:
		var w: Node3D = car.get_node("Wheels/" + k)
		var c: Array = facts["wheels"][WHEELS[k]]["centre"]
		var off := Vector2(w.position.x - c[0], w.position.z - c[2]).length()
		_check("%s mount over %s" % [k, WHEELS[k]], off < 0.005, "%.4f m off in plan" % off)
	var hull: ConvexPolygonShape3D = (car.get_node("CollisionShape3D") as CollisionShape3D).shape
	_check("hull is the measured one", hull.points.size() == facts["hull"].size(), "%d points" % hull.points.size())
	_check("damage model found every part", int(dm.call("part_count_now")) == PARTS.size() + 1, "%d parts" % dm.call("part_count_now"))

	print("-- 2. modelled wheels, settled on a flat floor")
	var speed: float = (car as RigidBody3D).linear_velocity.length()
	_check("car has settled", speed < 0.05, "%.3f m/s" % speed)
	_check("it rests at its suspension's height", absf(car.global_position.y - ride_h) < 0.03,
			"body %.3f m, spring equilibrium says %.3f" % [car.global_position.y, ride_h])
	for k in WHEELS:
		var w: Node3D = car.get_node("Wheels/" + k)
		var holder: MeshInstance3D = w.get_node("Wheel")
		var m: Node3D = holder.get_node_or_null(WHEELS[k])
		_check("%s placeholder retired, %s adopted" % [k, WHEELS[k]], holder.mesh == null and m != null, "")
		if m == null:
			continue
		var r: float = facts["wheels"][WHEELS[k]]["radius"]
		var c: Array = facts["wheels"][WHEELS[k]]["centre"]
		var authored := car.global_transform * Vector3(c[0], c[1] + MODEL_Y, c[2])
		_check("%s tyre on the floor" % k, absf(m.global_position.y - r) < 0.03, "centre %.3f m up, radius %.3f" % [m.global_position.y, r])
		_check("%s inside its arch" % k, absf(m.global_position.y - authored.y) < 0.06,
				"%.3f m from where it was modelled" % (m.global_position.y - authored.y))

	# a car set down ABOVE its rest height must still end at it: the parking lock used to freeze an unoccupied car
	# mid-settle (it zeroed the velocity once it fell slower than 0.5 m/s), leaving it hovering
	var dropped: Node3D = (load(CAR) as PackedScene).instantiate() as Node3D
	world.add_child(dropped)
	dropped.position = Vector3(24, ride_h + 0.3, 0)
	await _tick(360)
	_check("set down 0.3 m high, it settles at its rest height", absf(dropped.global_position.y - ride_h) < 0.03,
			"body %.3f m, rest %.3f" % [dropped.global_position.y, ride_h])

	print("-- 3. crashes")
	var bump: MeshInstance3D = model.get_node("bump_front")
	var hp0: float = car.get_node("Health").call("health_now")
	dm.call("crash_at", Vector3(0, -0.4, nose + 0.05), 7.0)
	await _tick(4)
	_check("7 m/s front crash dents the front bumper", int(dm.call("part_state_now", "bump_front")) >= 1 and _blend(bump) > 0.1,
			"state %d, dam %.2f" % [dm.call("part_state_now", "bump_front"), _blend(bump)])
	_check("…and leaves the rear bumper alone", int(dm.call("part_state_now", "bump_rear")) == 0,
			"bump_rear state %d" % dm.call("part_state_now", "bump_rear"))
	var debris0: int = dm.call("debris_count_now")
	dm.call("crash_at", Vector3(0, -0.4, nose + 0.05), 14.0)
	await _tick(4)
	_check("14 m/s takes the bumper off", int(dm.call("part_state_now", "bump_front")) == 3 and not bump.visible
			and int(dm.call("debris_count_now")) > debris0,
			"state %d, visible %s, debris %d" % [dm.call("part_state_now", "bump_front"), bump.visible, dm.call("debris_count_now")])
	var hp1: float = car.get_node("Health").call("health_now")
	_check("crashes cost the car health", hp1 < hp0, "%.0f -> %.0f" % [hp0, hp1])

	print("-- 4. bullets")
	var door: MeshInstance3D = model.get_node("door_lf")
	var aabb := door.get_aabb()
	var at := door.global_transform * (aabb.position + aabb.size * 0.5)
	for i in range(4):
		helper.call("weapon_hit_at", im, car, at, 40.0)
	await _tick(2)
	_check("four 40-damage shots loosen the left door", int(dm.call("part_state_now", "door_lf")) == 2,
			"state %d, %.0f points" % [dm.call("part_state_now", "door_lf"), dm.call("part_damage_now", "door_lf")])
	_check("…and not the right one", int(dm.call("part_state_now", "door_rf")) == 0, "")

	print("-- 5. a loose door swings with the car's motion (frozen body, moved like a puppet)")
	(car as RigidBody3D).freeze = true
	var v := 0.0
	var widest := 0.0
	for i in range(60):                                     # 1 s at 20 m/s² to the RIGHT: the left door flies out
		v += 20.0 / 60.0
		car.global_position += car.global_basis.x * v / 60.0
		await physics_frame
		widest = maxf(widest, dm.call("part_angle_now", "door_lf"))
	_check("accelerating right swings the left door open", widest > 15.0, "%.1f deg" % widest)
	(car as RigidBody3D).freeze = false

	print("-- 6. the part mask reproduces the car on another peer")
	var twin: Node3D = (load(CAR) as PackedScene).instantiate() as Node3D
	world.add_child(twin)
	twin.position = Vector3(12, ride_h, 0)
	await _tick(5)
	var mask: int = dm.call("part_mask_now")
	twin.get_node("DamageModel").call("apply_replicated_mask", mask)
	await _tick(2)
	var same := true
	var diff := ""
	for p in PARTS:
		var a: int = dm.call("part_state_now", p)
		var b: int = twin.get_node("DamageModel").call("part_state_now", p)
		if a != b:
			same = false
			diff += "%s %d/%d " % [p, a, b]
	_check("twin matches every part", same and mask != 0, "mask %d %s" % [mask, diff])
	_check("twin dropped its front bumper too", not (twin.get_node("Model/bump_front") as Node3D).visible, "")

	print("-- 7. getting in and out opens and shuts the door, and the open door is solid")
	# a fresh car: the twin now carries the first car's LOOSE left door, which physics owns, not the enter/exit door
	var fresh: Node3D = (load(CAR) as PackedScene).instantiate() as Node3D
	world.add_child(fresh)
	fresh.position = Vector3(-14, ride_h, 0)
	await _tick(5)
	var tdm: Node = fresh.get_node("DamageModel")
	var ai: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--visuals="):                     # another body in the seat (before _ready)
			ai.set("character_visuals", load(a.substr("--visuals=".length())))
	world.add_child(ai)
	ai.global_position = fresh.global_position + Vector3(-2.5, 0.2, 0)
	await _tick(5)
	helper.call("seat_character", fresh, ai)                  # Vehicle.tryEnter, seat 0 = the left seat
	await _tick(20)                                          # ~0.33 s: fully open, holding
	var open_in: float = tdm.call("part_angle_now", "door_lf")
	var solid_in: bool = tdm.call("door_collider_solid_now", "door_lf")
	_check("entering opens the driver's (left) door", open_in > 55.0, "%.1f deg" % open_in)
	_check("…and its collider is solid while open", solid_in, "")
	_check("…the right door stays shut", float(tdm.call("part_angle_now", "door_rf")) < 1.0, "")
	await _tick(60)
	_check("…and it is shut again", float(tdm.call("part_angle_now", "door_lf")) < 1.0
			and not bool(tdm.call("door_collider_solid_now", "door_lf")),
			"%.1f deg, collider %s" % [tdm.call("part_angle_now", "door_lf"), tdm.call("door_collider_solid_now", "door_lf")])
	# the seated pose has blended in by now (a standing pelvis reads ~0.3 m higher mid-transition)
	var skel: Skeleton3D = _skeleton(ai)
	var pelvis := skel.global_transform * skel.get_bone_global_pose(skel.find_bone("pelvis"))
	var cushion: Array = facts["seats"]["seat_front_l"]
	var cushion_y: float = (fresh.global_transform * Vector3(cushion[0], cushion[1] + MODEL_Y, cushion[2])).y
	var drop: float = float(fresh.get("vehicle_config").get("seat_drop"))   # a low car's bucket seat
	_check("the driver's hips sit on the cushion", absf(pelvis.origin.y - (cushion_y + 0.08 - drop)) < 0.05,
			"pelvis %.3f m above the cushion, ai lod %d" % [pelvis.origin.y - cushion_y, ai.call("lod_level_now")])
	var eye: Node3D = fresh.get_node("Seats/Seat0/CockpitCameraMount")
	var roof: float = (fresh.global_transform * Vector3(0, facts["bounds"]["max"][1] + MODEL_Y, 0)).y
	_check("the driver's eye is under the roof", eye.global_position.y < roof - 0.05,
			"eye %.3f m below the roof top" % (roof - eye.global_position.y))
	# THE HEAD, not the camera mount: the mount is a fixed marker on the seat and cannot see the body
	# (user-reported "seated, the character goes through the roof" passed the check above). The crown's
	# height above the head bone is the body's own measurement (<body>.body.json crown_m against the
	# head bone's rest height), placed on the seated head bone.
	var hb: int = skel.find_bone("head_2") if skel.find_bone("head_2") >= 0 else skel.find_bone("head")
	var body_scene: Node = skel.get_parent()
	while body_scene != null and body_scene.scene_file_path == "":
		body_scene = body_scene.get_parent()
	var body_json := "" if body_scene == null else body_scene.scene_file_path.get_basename() + ".body.json"
	if body_json != "" and not FileAccess.file_exists(body_json):   # the reference's glb is not named after it
		var dir: String = body_json.get_base_dir()
		body_json = dir + "/" + dir.get_file() + ".body.json"
	if hb >= 0 and body_json != "" and FileAccess.file_exists(body_json):
		var body: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(body_json))
		var rest_head_h: float = (skel.global_transform.basis * skel.get_bone_global_rest(hb).origin).y
		var crown_off: float = float(body["crown_m"]) - rest_head_h
		var head_y: float = (skel.global_transform * skel.get_bone_global_pose(hb)).origin.y
		_check("the driver's head is under the roof", head_y + crown_off < roof - 0.05,
				"crown %.3f m below the roof top (%s)" % [roof - head_y - crown_off, body_json.get_file()])
	else:
		_check("the driver's head is under the roof", false, "no head bone or no body record (%s)" % body_json)
	helper.call("exit_driver", fresh)                         # Vehicle.tryExit
	var fastest := 0.0
	for i in range(20):
		await physics_frame
		fastest = maxf(fastest, (fresh as RigidBody3D).linear_velocity.length())
	# the driver steps out where the door opens: the door must not throw the car (a door that was a shape of the
	# car's own body did - 100 m/s in one frame)
	_check("stepping out beside the opening door leaves the car still", fastest < 1.0, "fastest %.2f m/s" % fastest)
	_check("getting out opens it again", float(tdm.call("part_angle_now", "door_lf")) > 55.0,
			"%.1f deg" % tdm.call("part_angle_now", "door_lf"))

	print("-- 8. the wreck is the car, burnt")
	helper.call("kill", car)
	await _tick(3)
	var shell: Node = null
	for n in world.get_children():
		if n.get_node_or_null("BurntShell") != null:
			shell = n.get_node("BurntShell")
	var names := []
	if shell != null:
		for c in shell.get_children():
			names.append(String(c.name))
	var box: Node3D = shell.get_parent().get_node_or_null("Shell/Body") if shell != null else null
	var whole := "chassis" in names and "wheel_lf" in names and "wheel_rf" in names and "wheel_lb" in names and "wheel_rb" in names
	_check("wreck is the burnt chassis on its four wheels", whole and box != null and not box.visible, str(names))

	print("PROBE %s (%d failures)%s" % ["PASS" if fails == 0 else "FAIL", fails, " [control]" if control else ""])
	quit(1 if fails > 0 else 0)
