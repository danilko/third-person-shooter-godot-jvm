extends SceneTree
## Is this body's GENERATED CharacterVisuals scene a body the game can drive? (PLAN.md 6.9)
##
##   godot --headless --fixed-fps 60 --path . --script tools/godot/probe_character_visuals.gd -- \
##       --visuals=res://src/main/resources/com/openworld/character/CharacterVisuals_Shino.tscn [--control]
##
## `build_character_visuals.gd` writes a 70 KB scene out of numbers a tool measured. Nearly every
## way it can be wrong is SILENT: a MeshConfig path that resolves to nothing leaves a modifier
## unwired and the body simply stands slightly wrong; a socket in the wrong place puts the gun
## through the hand; a ragdoll bone on the wrong layer is a character bullets pass through; a
## missing armature turn is a character that walks backwards; a stance capsule the body does not
## fit inside is a character that clips through walls. None of them errors.
##
## So this drives a REAL Player with the scene and measures the body, not the file.
##
## `--control` builds the same body with the armature turn left out -- one line, and the single
## most consequential thing the generator does -- and the facing checks must fail.
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const WEAPON := "res://src/main/resources/com/openworld/weapon/ASR1.tscn"

var visuals_path := ""
var control := false
var _pass := 0
var _fail := 0

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--visuals="): visuals_path = a.substr(10)
		if a == "--control": control = true
	if visuals_path == "":
		print("  FAIL  give --visuals=res://...CharacterVisuals_<Body>.tscn")
		quit(1); return
	_run()

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _run() -> void:
	var world := Node3D.new()
	root.add_child(world)
	var floor_body := StaticBody3D.new()
	var fs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(40, 1, 40)
	fs.shape = box
	floor_body.add_child(fs)
	world.add_child(floor_body)
	floor_body.position = Vector3(0, -0.5, 0)

	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	p.set("character_visuals", load(visuals_path))
	world.add_child(p)
	p.position = Vector3(0, 0.2, 0)
	await _tick(60)

	var cv := _by_name(p, "CharacterVisuals")
	if control:
		# Undo the one line the generator adds inside the model instance. Everything still loads,
		# every path still resolves, every socket is still in the right hand -- the character just
		# faces backwards, which is what makes this worth a check of its own.
		var arm := (_by_name(cv, "MeshRoot") as Node3D).get_child(0).get_child(0) as Node3D
		arm.transform = arm.transform.rotated_local(Vector3.UP, PI)
		await _tick(10)
	var cfg: Resource = cv.get("mesh_config")
	var skel := _by_class(cv, "Skeleton3D") as Skeleton3D
	var mesh_root := _by_name(cv, "MeshRoot") as Node3D

	# --- 1. every path in the MeshConfig resolves --------------------------------------------
	var missing: PackedStringArray = []
	for prop in ["animation_tree_path", "mesh_root_path", "physical_bone_simulator_path",
				 "weapon_attachment_path", "aim_spine_modifier_path", "shoulder_aim_modifier_path",
				 "stock_mount_modifier_path", "recoil_modifier_path", "fps_camera_marker_path"]:
		var np: NodePath = cfg.get(prop)
		if String(np) != "" and cv.get_node_or_null(np) == null: missing.append(prop)
	for key in ["head_mesh_paths", "socket_paths"]:
		for np in (cfg.get(key) as Array):
			if cv.get_node_or_null(np) == null: missing.append("%s:%s" % [key, np])
	# A stance with no collider or no ceiling ray declares an EMPTY path (DriveCarrier and Swim are
	# physics-free, and Crawl asks no ceiling question), so only a non-empty one has to resolve.
	for d in ["stance_collider_paths", "stance_raycast_paths"]:
		var dict: Dictionary = cfg.get(d)
		for k in dict:
			var np: NodePath = dict[k]
			if String(np) != "" and cv.get_node_or_null(np) == null: missing.append("%s:%s" % [d, k])
	_check("every MeshConfig path resolves", missing.is_empty(),
		"none missing" if missing.is_empty() else String(", ").join(missing))

	# --- 2. the body faces the way the game thinks it does -----------------------------------
	# The armature is turned 180 deg, so in MeshRoot's frame forward is -Z. Asked of the FEET,
	# which cannot be argued with: the ball of the foot is in front of the ankle.
	var to_mesh := mesh_root.global_transform.affine_inverse()
	var ankle := to_mesh * _bone_world(skel, "foot_l")
	var toe := to_mesh * _bone_world(skel, "ball_l")
	_check("the body faces -Z in MeshRoot's frame", toe.z < ankle.z - 0.02,
		"toe z %+.3f vs ankle %+.3f" % [toe.z, ankle.z])
	var eye := to_mesh * (cv.get_node(cfg.get("fps_camera_marker_path")) as Node3D).global_position
	_check("the first-person mount is in front of the head", eye.z < 0.0,
		"eye z %+.3f, height %.3f m" % [eye.z, eye.y])

	# --- 3. the AnimationTree drives this body ------------------------------------------------
	var tree := cv.get_node(cfg.get("animation_tree_path")) as AnimationTree
	var head0 := _bone_world(skel, "head_2").y
	tree.set("parameters/StanceTransition/transition_request", "Crouch")
	await _tick(40)
	var head1 := _bone_world(skel, "head_2").y
	tree.set("parameters/StanceTransition/transition_request", "Upright")
	await _tick(40)
	_check("the shared library poses this body", head0 - head1 > 0.15,
		"head %.3f standing, %.3f crouched (%.3f m)" % [head0, head1, head0 - head1])

	# --- 4. the hitboxes are on the body, and big enough to be hit ----------------------------
	var sim := cv.get_node(cfg.get("physical_bone_simulator_path"))
	var bones := 0
	var off_layer := 0
	var far := 0.0
	var thinnest := INF
	var thinnest_name := ""
	for c in sim.get_children():
		if not (c is PhysicalBone3D): continue
		bones += 1
		if (c as PhysicalBone3D).collision_layer != 8: off_layer += 1
		var bw := _bone_world(skel, (c as PhysicalBone3D).bone_name)
		far = maxf(far, c.global_position.distance_to(bw))
		var shape := c.get_node_or_null("CollisionShape3D") as CollisionShape3D
		if shape != null and shape.shape is CapsuleShape3D:
			var r: float = (shape.shape as CapsuleShape3D).radius
			if r < thinnest:
				thinnest = r
				thinnest_name = (c as PhysicalBone3D).bone_name
	_check("every hitbox bone is on the HITBOX layer", bones >= 17 and off_layer == 0,
		"%d bones, %d off layer" % [bones, off_layer])
	_check("every hitbox sits on its bone", far < 0.35, "worst %.3f m from its bone" % far)
	# Jolt's ray test steps over a capsule whose radius is under ~2.4e-4 x the distance it starts
	# from, so a 1.4 cm hand is unhittable past 60 m (CLAUDE.md, "A long ray steps over a small,
	# far hitbox"). The skin-derived radii exist to stop that.
	# The REFERENCE fails this on purpose and is the reason the rule exists: its ragdoll came from
	# the editor's "create physical skeleton", which sizes a capsule at 0.1 x the bone, giving it
	# 0.9 cm hands. A generated body's radii are read off its own skin.
	_check("no hitbox is too thin to hit at range", thinnest >= 0.02,
		"thinnest %.4f m (%s) -> a long ray steps over it past %.0f m" % [thinnest, thinnest_name, thinnest / 2.4e-4])

	# --- 5. the standing body fits inside its stance capsule -----------------------------------
	var cols: Dictionary = cfg.get("stance_collider_paths")
	var up := cv.get_node(cols["Upright"]) as CollisionShape3D
	var cap := up.shape as CapsuleShape3D
	var top: float = up.position.y + cap.height * 0.5
	var head := to_mesh * _bone_world(skel, "head_2")
	_check("the upright capsule covers the head", top > head.y,
		"capsule top %.3f, head bone %.3f, radius %.3f" % [top, head.y, cap.radius])

	# --- 6. a weapon reaches a socket on THIS body ---------------------------------------------
	var gun: Node3D = (load(WEAPON) as PackedScene).instantiate() as Node3D
	world.add_child(gun)
	gun.global_position = p.global_position + Vector3(0, 0.3, 0)
	await _tick(30)
	var wc: Node = p.get_node_or_null("WeaponController")
	for slot in range(6):
		if String(gun.get_parent().name).begins_with("Socket"): break
		wc.call("on_set_weapon", slot)
		await _tick(50)
	var socketed := String(gun.get_parent().name).begins_with("Socket")
	var palm := 0.0
	if socketed:
		palm = gun.global_position.distance_to(_bone_world(skel, "hand_r"))
	_check("a rifle reaches a hand socket", socketed and palm < 0.12,
		"parent %s, grip %.3f m from hand_r" % [gun.get_parent().name, palm])

	# --- 7. first person hides this body's head ------------------------------------------------
	var heads: Array = cfg.get("head_mesh_paths")
	var before := 0
	for np in heads:
		if (cv.get_node(np) as GeometryInstance3D).visible: before += 1
	p.set("is_fps_mode", true)
	await _tick(20)
	var after := 0
	for np in heads:
		if (cv.get_node(np) as GeometryInstance3D).visible: after += 1
	p.set("is_fps_mode", false)
	_check("first person hides the head meshes", heads.size() > 0 and before == heads.size() and after == 0,
		"%d head meshes, %d visible before, %d after" % [heads.size(), before, after])

	print("[character-visuals] %s%s: %d passed, %d failed" % [visuals_path.get_file(), " [control: armature turn undone]" if control else "", _pass, _fail])
	quit(1 if _fail > 0 else 0)

func _bone_world(skel: Skeleton3D, bone: String) -> Vector3:
	var i := skel.find_bone(bone)
	return skel.global_transform * skel.get_bone_global_pose(i).origin if i >= 0 else Vector3.ZERO

func _check(what: String, ok: bool, detail: String) -> void:
	if ok: _pass += 1
	else: _fail += 1
	print("  %s  %-46s %s" % ["PASS" if ok else "FAIL", what, detail])

func _by_name(n: Node, nm: String) -> Node:
	if n.name == nm: return n
	for c in n.get_children():
		var r := _by_name(c, nm)
		if r != null: return r
	return null

func _by_class(n: Node, cls: String) -> Node:
	if n.get_class() == cls: return n
	for c in n.get_children():
		var r := _by_class(c, cls)
		if r != null: return r
	return null
