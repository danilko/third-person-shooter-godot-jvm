extends SceneTree
## THE RIDER (PLAN.md 3.1b: rider poses option (b), feet down at a stop, helmet): character.RiderPoseModifier bends the
## car's seated clip per bike (VehicleConfig.rider*), puts the left foot on the ground at a stop, and the rider wears a
## helmet -- built by Motorcycle as a rider gets on, removed as they get off.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_rider_pose.gd [-- --control | --no-hands]
##   xvfb-run -a godot --fixed-fps 60 --path . --script tools/godot/probe_rider_pose.gd -- --shot=<dir>   (pictures)
## --control: Motorcycle.riderGear off (the car's clip as it is, bare-headed) -- the pose / foot / helmet / hand checks fail.
## --no-hands: only the hand IK off (RiderPoseModifier.handsOnBars) -- the hand checks fail, the rest pass.
##
## On a bare floor, each of the five bikes gets an AI rider seated the way traffic seats one, once per BODY (Shino, the
## shortest arms, and Fumiriya, the tallest):
##   1. the rider wears the gear (the modifier ahead of the aim modifiers, a helmet on the head bone);
##   2. the sport bike's rider TUCKS: head >= 0.10 m further forward of the hip than on the scooter;
##   3. standing still, the left foot is on the ground beside the bike (foot bone <= 0.15 m above the floor, out to
##      the left) and the bike leans on it a few degrees;
##   4. riding (a scripted throttle), the foot comes up (weight < 0.05) and goes down again at a stop;
##   5. HANDS ON THE BARS (3.1b): each hand's grip point (3/4 of the way from the wrist to the middle knuckle, read from
##      the posed bones) within 3 cm of the bike's grip_l / grip_r marker, standing and riding;
##   6. with a pistol in hand the right hand is off the bar (> 0.10 m), the left still on it;
##   7. off the bike, the pose goes at once and the helmet comes off by the right hand: gone within 0.6 s;
##   8. THE HELMET (3.1b, the artist's model): the bike's .glb (Helmet_full on the SSB1, Helmet_open on the rest), its
##      shell tinted (white on the 白バイ), put on by the right hand -- the hand on the helmet's `grab` mid-way, the helmet
##      on the head (its model at the head pivot) within 0.6 s of sitting down.

const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const BIKES := ["SCT1", "POB1", "TRB1", "SSB1", "PMB1"]
const BODIES := {"shino": "res://src/main/resources/com/openworld/character/CharacterVisuals_Shino.tscn",
		"fumiriya": "res://src/main/resources/com/openworld/character/CharacterVisuals_Fumiriya.tscn"}
const HAND_TOL := 0.03
const GRIP_FRACTION := 0.75

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
func _watch(rider: Node, bike: Node3D) -> void:
	var skel: Skeleton3D = rider.find_child("Skeleton3D", true, false)
	var k := rider.get_instance_id()
	skel.skeleton_updated.connect(func():
		var d := {}
		# the bars and the bike AS THEY ARE when the modifiers ran: a bone sampled here against a marker read on a later
		# physics frame differs by one tick of travel (0.33 m at 20 m/s), which is the probe's timing, not the pose's
		for side in ["_l", "_r"]:
			var g: Node3D = bike.get_node_or_null("Model/grip" + side)
			d["grip" + side] = g.global_position if g else Vector3(1e6, 1e6, 1e6)
		# the helmet's grab from the head bone's pose IN THIS PASS (the attachment's global transform is a frame old)
		var at := skel.get_node_or_null("RiderHelmet") as BoneAttachment3D
		var grab: Node3D = at.find_child("grab", true, false) if at else null
		d["grab"] = Vector3(1e6, 1e6, 1e6)
		if grab:
			var under := grab.transform
			var n: Node = grab.get_parent()
			while n != at:
				under = (n as Node3D).transform * under
				n = n.get_parent()
			d["grab"] = skel.global_transform * skel.get_bone_global_pose(skel.find_bone(at.bone_name)) * under.origin
		d["bike_inv"] = bike.global_transform.affine_inverse()
		for bone in ["head", "pelvis", "foot_l", "hand_l", "hand_r", "middle_01_l", "middle_01_r", "upperarm_l"]:
			d[bone] = _bone_world(skel, bone)
		seen[k] = d)

## Where a hand closes on a bar, from the POSED bones: 3/4 of the way from the wrist to the middle knuckle.
func _grip_point(rider: Node, side: String) -> Vector3:
	var d: Dictionary = seen.get(rider.get_instance_id(), {})
	if not d.has("hand" + side):
		return Vector3(1e6, 1e6, 1e6)
	return d["hand" + side].lerp(d["middle_01" + side], GRIP_FRACTION)

## [miss left, miss right] (m): each hand's grip point to its bar marker.
func _hand_miss(bike: Node, rider: Node) -> Array:
	var out := []
	for side in ["_l", "_r"]:
		var d: Dictionary = seen.get(rider.get_instance_id(), {})
		out.append(_grip_point(rider, side).distance_to(d["grip" + side]) if d.has("grip" + side) else 1e6)
	return out

## The helmet model under the rider's RiderHelmet attachment (null: none, or the sphere stand-in).
func _helmet_model(rider: Node) -> Node3D:
	var at := rider.find_child("RiderHelmet", true, false)
	if at == null:
		return null
	for c in at.get_children():
		if String(c.name).begins_with("Helmet_"):
			return c
	return null

## The tint on the helmet's `shell` surface (null: no override).
func _shell_colour(model: Node3D):
	if model == null:
		return null
	for mi in model.find_children("*", "MeshInstance3D", true, false):
		for i in mi.mesh.get_surface_count():
			var m: Material = mi.mesh.surface_get_material(i)
			if m and m.resource_name == "shell" and mi.get_surface_override_material(i) is BaseMaterial3D:
				return (mi.get_surface_override_material(i) as BaseMaterial3D).albedo_color
	return null

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

	var no_hands := "--no-hands" in args
	var bikes := {}
	var riders := {}
	var keys := []
	var row := 0
	for body in BODIES:
		for i in BIKES.size():
			var key: String = "%s@%s" % [BIKES[i], body]
			var bike: RigidBody3D = (load("res://src/main/resources/com/openworld/vehicle/%s.tscn" % BIKES[i]) as PackedScene).instantiate()
			bike.position = Vector3(row * 8.0, 0.6, i * 6.0)
			w.add_child(bike)
			bikes[key] = bike
			keys.append(key)
		row += 1
	await _tick(90)
	var any_bike: Node = bikes[keys[0]]
	any_bike.call("set_rider_gear_now", not control)
	any_bike.call("set_hands_on_bars_now", not no_hands)
	for key in keys:
		var d: CharacterBody3D = (load(AI) as PackedScene).instantiate()
		d.set("character_visuals", load(BODIES[key.split("@")[1]]))
		d.position = bikes[key].global_position + Vector3(2.0, 0.3, 0.0)
		w.add_child(d)
		helper.call("seat_driver_quietly", bikes[key], d)
		riders[key] = d
		_watch(d, bikes[key])
	# 8. the helmet goes on: the right hand carries it (mid-way), on the head within 0.6 s
	await _tick(15)
	for id in keys:
		var d: Dictionary = seen.get((riders[id] as Node).get_instance_id(), {})
		var miss := _grip_point(riders[id], "_r").distance_to(d.get("grab", Vector3(1e6, 1e6, 1e6)))
		var model := _helmet_model(riders[id])
		var hm := (riders[id] as Node).find_child("RiderHandsModifier", true, false)
		_check("%s: putting the helmet on, the right hand holds it (<= 1 cm of grab)" % id, miss <= 0.01 and model != null
				and model.position.length() > 0.05, "%.3f m (solver's own %s, reach %s); helmet %.2f m from the head" % [miss,
				str(hm.call("grip_miss_now", 1)) if hm else "-", str(hm.call("reach_ratio_now", 1)) if hm else "-",
				model.position.length() if model else -1.0])
	await _tick(21)          # 36 ticks = 0.6 s since seating
	for id in keys:
		var model := _helmet_model(riders[id])
		var want := "Helmet_full" if id.begins_with("SSB1") else "Helmet_open"
		_check("%s: the helmet is the bike's model (%s) and ON within 0.6 s" % [id, want], model != null and String(model.name) == want
				and model.position.length() < 0.005 and model.basis.is_equal_approx(Basis.IDENTITY),
				"%s at %.3f m" % [String(model.name) if model else "none", model.position.length() if model else -1.0])
		var tint: Variant = _shell_colour(model)
		var white: bool = id.begins_with("PMB1")
		var c: Color = tint if tint is Color else Color(0, 0, 0, 0)
		_check("%s: ... its shell tinted%s" % [id, " white (白バイ)" if white else ""], tint is Color
				and (c.r > 0.9 and c.g > 0.9 and c.b > 0.9 if white else true), str(tint))
	await _tick(84)

	# 1-3. standing still
	var fwd := {}
	for id in keys:
		var bike: RigidBody3D = bikes[id]
		var d: CharacterBody3D = riders[id]
		var skel: Skeleton3D = d.find_child("Skeleton3D", true, false)
		var mod := skel.get_node_or_null("RiderPoseModifier")
		var aim := skel.get_node_or_null("SpineAimModifier")
		var helmet := skel.get_node_or_null("RiderHelmet")
		var hands := skel.get_node_or_null("RiderHandsModifier")
		var last_mod := -1
		for c in skel.get_children():
			if c is SkeletonModifier3D:
				last_mod = c.get_index()
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
		_check("%s: ... the hands modifier runs LAST, after the aim modifiers" % id, hands != null and hands.get_index() == last_mod,
				"%d of %d" % [hands.get_index() if hands else -1, last_mod])
		_check("%s: at a stop the left foot is on the ground beside the bike" % id, foot.y < 0.15 and foot_local.x < -0.15,
				"%.2f m up, x %.2f" % [foot.y, foot_local.x])
		_check("%s: ... and the bike leans on it (2-6 deg left)" % id, lean > 2.0 and lean < 6.0, "%.1f" % lean)
		var miss := _hand_miss(bike, d)
		_check("%s: both hands on the bars at a stop (<= %.0f cm)" % [id, HAND_TOL * 100], miss[0] <= HAND_TOL and miss[1] <= HAND_TOL,
				"left %.3f, right %.3f m (solver's own %s / %s, weights %s / %s); the reach leaned the back %s deg more" % [miss[0], miss[1],
				str(hands.call("grip_miss_now", 0)) if hands else "-", str(hands.call("grip_miss_now", 1)) if hands else "-",
				str(hands.call("hand_weight_now", 0)) if hands else "-", str(hands.call("hand_weight_now", 1)) if hands else "-",
				str(mod.call("reach_lean_now")) if mod else "-"])
	for body in BODIES:
		var sport: String = "SSB1@" + body
		var scoot: String = "SCT1@" + body
		_check("%s: the sport bike's rider tucks: head >= 0.10 m further forward than on the scooter" % body,
				fwd[sport] - fwd[scoot] >= 0.10, "%.2f vs %.2f" % [fwd[sport], fwd[scoot]])

	if shot_dir != "":
		DirAccess.make_dir_recursive_absolute(shot_dir)
		var cam := Camera3D.new()
		w.add_child(cam)
		cam.current = true
		cam.fov = 40
		for id in BIKES:
			var at: Vector3 = bikes[id + "@shino"].global_position
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
	for id in keys:
		helper.call("drive_craft", bikes[id], 0.5, 0.25, false)     # a gentle turn, so the bike leans too
	await _tick(120)
	for id in keys:
		var mod := (riders[id] as Node).find_child("RiderPoseModifier", true, false)
		up_w[id] = float(mod.call("foot_weight_now")) if mod else -1.0
		var hands := (riders[id] as Node).find_child("RiderHandsModifier", true, false)
		var miss := _hand_miss(bikes[id], riders[id])
		_check("%s: both hands on the bars riding (<= %.0f cm)" % [id, HAND_TOL * 100], miss[0] <= HAND_TOL and miss[1] <= HAND_TOL,
				"left %.3f, right %.3f m at %.1f m/s, lean %.1f deg (solver's own %s / %s)" % [miss[0], miss[1], (bikes[id] as RigidBody3D).linear_velocity.length(),
				float(bikes[id].call("lean_degrees_now")), str(hands.call("grip_miss_now", 0)) if hands else "-", str(hands.call("grip_miss_now", 1)) if hands else "-"])
	for id in keys:
		var dd: Dictionary = seen.get((riders[id] as Node).get_instance_id(), {})
		print("    %s riding: pelvis in the bike's frame at the modifier pass %s (now %s)" % [id, dd["bike_inv"] * dd["pelvis"], (bikes[id] as Node3D).global_transform.affine_inverse() * dd["pelvis"]])
	for id in keys:
		helper.call("drive_craft", bikes[id], 0.0, 0.0, true)
	for i in 60:                 # brought to a stop by hand (the scripted brake is not what is measured here)
		for id in keys:
			var bk: RigidBody3D = bikes[id]
			bk.linear_velocity = bk.linear_velocity * 0.85
			bk.angular_velocity = Vector3.ZERO
		await physics_frame
	await _tick(120)
	for id in keys:
		var mod := (riders[id] as Node).find_child("RiderPoseModifier", true, false)
		var down_w := float(mod.call("foot_weight_now")) if mod else -1.0
		var speed := (bikes[id] as RigidBody3D).linear_velocity.length()
		_check("%s: riding lifts the foot, stopping puts it down again" % id, up_w[id] >= 0.0 and up_w[id] < 0.05 and down_w > 0.95,
				"riding %.2f, stopped %.2f (%.1f m/s)" % [up_w[id], down_w, speed])

	# 6. a pistol in the right hand: it lets go of the bar, the left keeps it
	for id in keys:
		helper.call("give_weapon", riders[id], "PIS1")
	await _tick(30)
	for id in keys:
		var wc: Node = (riders[id] as Node).get_node("WeaponController")
		for slot in range(1, 7):
			wc.call("on_set_weapon", slot)
			await _tick(2)
			if String(wc.call("get_current_weapon_id_now")).begins_with("PIS"):
				break
	await _tick(90)
	for id in keys:
		var wc: Node = (riders[id] as Node).get_node("WeaponController")
		var miss := _hand_miss(bikes[id], riders[id])
		_check("%s: holding a pistol the right hand is off the bar, the left on it" % id,
				miss[1] > 0.10 and miss[0] <= HAND_TOL, "held %s; left %.3f, right %.3f m" % [str(wc.call("get_current_weapon_id_now")), miss[0], miss[1]])

	# 7. off the bike: the pose at once, the helmet taken off by the right hand
	for id in keys:
		helper.call("release_driver", bikes[id], riders[id])
	await _tick(10)
	for id in keys:
		var skel: Skeleton3D = (riders[id] as Node).find_child("Skeleton3D", true, false)
		var model := _helmet_model(riders[id])
		_check("%s: off the bike the pose is gone and the helmet is coming off" % id, skel.get_node_or_null("RiderPoseModifier") == null
				and int(bikes[id].call("rider_gear_now")) == 0 and model != null and model.position.length() > 0.02
				and int(bikes[id].call("riders_leaving_now")) == 1, "helmet %.2f m off the head" % [model.position.length() if model else -1.0])
	await _tick(30)          # 40 ticks = 0.67 s since getting off
	for id in keys:
		var skel: Skeleton3D = (riders[id] as Node).find_child("Skeleton3D", true, false)
		_check("%s: ... and within 0.67 s every piece of gear is gone" % id, skel.get_node_or_null("RiderPoseModifier") == null
				and skel.get_node_or_null("RiderHandsModifier") == null
				and skel.get_node_or_null("RiderHelmet") == null and int(bikes[id].call("riders_leaving_now")) == 0)
	any_bike.call("set_rider_gear_now", true)
	any_bike.call("set_hands_on_bars_now", true)
	print("RESULT %s (%d failures)%s" % ["PASS" if fails == 0 else "FAIL", fails, "  (CONTROL)" if control else ""])
	quit(0 if fails == 0 else 1)
