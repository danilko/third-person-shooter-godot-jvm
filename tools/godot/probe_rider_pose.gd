extends SceneTree
## THE RIDER (PLAN.md 3.1b: rider poses option (b), feet down at a stop, helmet): character.RiderPoseModifier bends the
## car's seated clip per bike (VehicleConfig.rider*), puts the left foot on the ground at a stop, and the rider wears a
## helmet -- built by Motorcycle as a rider gets on, removed as they get off.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_rider_pose.gd [-- --control]
##   xvfb-run -a godot --fixed-fps 60 --path . --script tools/godot/probe_rider_pose.gd -- --shot=<dir>   (pictures)
## --control: Motorcycle.riderGear off (the car's clip as it is, bare-headed) -- the pose / foot / helmet checks fail.
##
## On a bare floor, each of the five bikes gets an AI rider seated the way traffic seats one:
##   1. the rider wears the gear (the modifier ahead of the aim modifiers, a helmet on the head bone);
##   2. the sport bike's rider TUCKS: head >= 0.10 m further forward of the hip than on the scooter;
##   3. standing still, the left foot is on the ground beside the bike (foot bone <= 0.15 m above the floor, out to
##      the left) and the bike leans on it a few degrees;
##   4. riding (a scripted throttle), the foot comes up (weight < 0.05) and goes down again at a stop;
##   5. off the bike, the gear is gone.

const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const BIKES := ["SCT1", "POB1", "TRB1", "SSB1", "PMB1"]

var fails := 0
var seen := {}      # rider instance id -> {head, pelvis, foot_l} world, sampled AFTER the modifiers (skeleton_updated)

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-66s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _bone_world(skel: Skeleton3D, bone: String) -> Vector3:
	var i := skel.find_bone(bone)
	if i < 0:
		i = skel.find_bone("head_2") if bone == "head" else -1
	return skel.global_transform * skel.get_bone_global_pose(i).origin if i >= 0 else Vector3.ZERO

## Skeleton3D restores the clip's pose after its modifiers run (Godot 4.3+), so a bone read from a physics frame is the
## UNMODIFIED pose: the modified one is only visible inside skeleton_updated.
func _watch(rider: Node) -> void:
	var skel: Skeleton3D = rider.find_child("Skeleton3D", true, false)
	var k := rider.get_instance_id()
	skel.skeleton_updated.connect(func():
		seen[k] = {"head": _bone_world(skel, "head"), "pelvis": _bone_world(skel, "pelvis"), "foot_l": _bone_world(skel, "foot_l")})

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var control := "--control" in args
	var shot_dir := ""
	for a in args:
		if a.begins_with("--shot="):
			shot_dir = a.substr(7)
	var w := Node3D.new()
	root.add_child(w)
	current_scene = w
	var f := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var b := BoxShape3D.new()
	b.size = Vector3(400, 1, 400)
	cs.shape = b
	f.add_child(cs)
	f.position.y = -0.5
	var floor_mesh := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(400, 400)
	floor_mesh.mesh = pm
	floor_mesh.position.y = 0.5
	f.add_child(floor_mesh)
	w.add_child(f)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, -30, 0)
	w.add_child(sun)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.55, 0.65, 0.8)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color(0.6, 0.6, 0.6)
	w.add_child(env)
	var helper: Node = load(HELPER).new()
	w.add_child(helper)

	var bikes := {}
	var riders := {}
	for i in BIKES.size():
		var id: String = BIKES[i]
		var bike: RigidBody3D = (load("res://src/main/resources/com/openworld/vehicle/%s.tscn" % id) as PackedScene).instantiate()
		bike.position = Vector3(0.0, 0.6, i * 6.0)
		w.add_child(bike)
		bikes[id] = bike
	await _tick(90)
	bikes["SCT1"].call("set_rider_gear_now", not control)
	for id in BIKES:
		var d: CharacterBody3D = (load(AI) as PackedScene).instantiate()
		d.position = bikes[id].global_position
		w.add_child(d)
		helper.call("seat_driver_quietly", bikes[id], d)
		riders[id] = d
		_watch(d)
	await _tick(120)

	# 1-3. standing still
	var fwd := {}
	for id in BIKES:
		var bike: RigidBody3D = bikes[id]
		var d: CharacterBody3D = riders[id]
		var skel: Skeleton3D = d.find_child("Skeleton3D", true, false)
		var mod := skel.get_node_or_null("RiderPoseModifier")
		var aim := skel.get_node_or_null("SpineAimModifier")
		var helmet := skel.get_node_or_null("RiderHelmet")
		var inv := bike.global_transform.affine_inverse()
		var bones: Dictionary = seen.get(d.get_instance_id(), {"head": Vector3.ZERO, "pelvis": Vector3.ZERO, "foot_l": Vector3.ZERO})
		var head: Vector3 = inv * bones["head"]
		var hip: Vector3 = inv * bones["pelvis"]
		fwd[id] = hip.z - head.z          # + = head ahead of the hip (the bike's nose is -Z)
		var foot: Vector3 = bones["foot_l"]
		var foot_local := inv * foot
		var lean := float(bike.call("lean_degrees_now"))
		print("  %s: head %.2f m ahead of hip, head %.2f m up; left foot %.2f m above the floor, %.2f m to the side; lean %.1f deg; foot weight %s"
				% [id, fwd[id], (bike.global_transform * head).y, foot.y, foot_local.x, lean, str(mod.call("foot_weight_now")) if mod else "-"])
		_check("%s: the rider wears the pose modifier and a helmet" % id, mod != null and helmet != null)
		_check("%s: ... the modifier runs before the aim modifiers" % id, mod != null and aim != null and mod.get_index() < aim.get_index(),
				"%d < %d" % [mod.get_index() if mod else -1, aim.get_index() if aim else -1])
		_check("%s: at a stop the left foot is on the ground beside the bike" % id, foot.y < 0.15 and foot_local.x < -0.15,
				"%.2f m up, x %.2f" % [foot.y, foot_local.x])
		_check("%s: ... and the bike leans on it (2-6 deg left)" % id, lean > 2.0 and lean < 6.0, "%.1f" % lean)
	_check("the sport bike's rider tucks: head >= 0.10 m further forward than on the scooter",
			fwd["SSB1"] - fwd["SCT1"] >= 0.10, "%.2f vs %.2f" % [fwd["SSB1"], fwd["SCT1"]])

	if shot_dir != "":
		DirAccess.make_dir_recursive_absolute(shot_dir)
		var cam := Camera3D.new()
		w.add_child(cam)
		cam.current = true
		cam.fov = 40
		for id in BIKES:
			var at: Vector3 = bikes[id].global_position
			for view in [["side", Vector3(-3.2, 0.6, 0.0)], ["front", Vector3(-1.2, 0.9, -3.0)]]:
				cam.global_position = at + view[1]
				cam.look_at(at + Vector3(0, 0.7, 0), Vector3.UP)
				await process_frame
				await process_frame
				await RenderingServer.frame_post_draw
				root.get_texture().get_image().save_png("%s/rider_%s_%s%s.png" % [shot_dir, id, view[0], "_control" if control else ""])
		print("  pictures in %s" % shot_dir)

	# 4. riding lifts the foot; stopping puts it down
	var up_w := {}
	for id in BIKES:
		helper.call("drive_craft", bikes[id], 0.5, 0.0, false)
	await _tick(120)
	for id in BIKES:
		var mod := (riders[id] as Node).find_child("RiderPoseModifier", true, false)
		up_w[id] = float(mod.call("foot_weight_now")) if mod else -1.0
	for id in BIKES:
		helper.call("drive_craft", bikes[id], 0.0, 0.0, true)
	for i in 60:                 # brought to a stop by hand (the scripted brake is not what is measured here)
		for id in BIKES:
			var bk: RigidBody3D = bikes[id]
			bk.linear_velocity = bk.linear_velocity * 0.85
			bk.angular_velocity = Vector3.ZERO
		await physics_frame
	await _tick(120)
	for id in BIKES:
		var mod := (riders[id] as Node).find_child("RiderPoseModifier", true, false)
		var down_w := float(mod.call("foot_weight_now")) if mod else -1.0
		var speed := (bikes[id] as RigidBody3D).linear_velocity.length()
		_check("%s: riding lifts the foot, stopping puts it down again" % id, up_w[id] >= 0.0 and up_w[id] < 0.05 and down_w > 0.95,
				"riding %.2f, stopped %.2f (%.1f m/s)" % [up_w[id], down_w, speed])

	# 5. off the bike
	for id in BIKES:
		helper.call("release_driver", bikes[id], riders[id])
	await _tick(10)
	for id in BIKES:
		var skel: Skeleton3D = (riders[id] as Node).find_child("Skeleton3D", true, false)
		_check("%s: off the bike the gear is gone" % id, skel.get_node_or_null("RiderPoseModifier") == null
				and skel.get_node_or_null("RiderHelmet") == null and int(bikes[id].call("rider_gear_now")) == 0)
	bikes["SCT1"].call("set_rider_gear_now", true)
	print("RESULT %s (%d failures)%s" % ["PASS" if fails == 0 else "FAIL", fails, "  (CONTROL)" if control else ""])
	quit(0 if fails == 0 else 1)
