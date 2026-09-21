extends SceneTree
## Write a body's CharacterVisuals scene from its measurements (PLAN.md 6.9).
##
##   godot --headless --path . --script tools/godot/build_character_visuals.gd -- --body=shino
##
## `CharacterVisuals_GodotChan.tscn` is 1400 lines, and ~640 of them are an AnimationTree that is
## body-INDEPENDENT by construction (W40: a track path names `Skeleton3D:<bone>`, the filters name
## bones, and the tree carries the shared library itself). Hand-writing that per body would be the
## same fact in three files, which is the defect this codebase spends most of its rules closing. So
## a body's scene is GENERATED: the tree is copied from the reference, the layout is the one every
## body needs, and every number comes from `<body>.body.json`, which `measure_body.gd` derived.
##
## The reference's own scene is NOT generated. It is the tree's owner and the control every
## measurement is read against, and it carries a decade of hand-tuning this tool would quietly
## round off. `--check` re-generates into memory and fails if the file on disk differs, so a tree
## edit that never reached the other bodies is caught.
##
## What the generator does NOT decide: which body ships as the player. That is an art call.

const REFERENCE_SCENE := "res://src/main/resources/com/openworld/character/CharacterVisuals_GodotChan.tscn"
const OUT_DIR := "res://src/main/resources/com/openworld/character/"
const FIST := "res://src/main/resources/com/openworld/weapon/Fist.tscn"
const ANIM_LIB := "res://src/main/resources/com/openworld/character/anim/character_anims.res"
const S_VISUALS := "res://src/main/java/com/openworld/character/CharacterVisuals.java"
const S_MESHCFG := "res://src/main/java/com/openworld/character/MeshConfig.java"
const S_SHOULDER := "res://src/main/java/com/openworld/character/ShoulderAimModifier.java"
const S_SUPPORT := "res://src/main/java/com/openworld/character/SupportHandIKModifier.java"
const S_STOCK := "res://src/main/java/com/openworld/character/StockMountIKModifier.java"
const S_RECOIL := "res://src/main/java/com/openworld/character/WeaponRecoilModifier.java"

## Bone frame -> game frame; see measure_body.gd. Its own inverse.
const ARMATURE_TURN := Basis(Vector3(-1, 0, 0), Vector3(0, 1, 0), Vector3(0, 0, -1))
const HITBOX_LAYER := 8          # CollisionLayers.HITBOX -- these bones are also what a bullet hits
const SOCKETS := ["SocketRifle", "SocketPistol", "SocketLauncher", "SocketMelee", "SocketThrowable", "SocketFist"]
const BACK_MARKERS := ["LongWeaponHolsterMaker1", "LongWeaponHolsterMaker2",
					   "LongWeaponHolsterMaker3", "LongWeaponHolsterMaker4"]
const HIP_MARKERS := ["ShortWeaponHolsterMaker1", "ShortWeaponHolsterMaker2",
					  "ShortWeaponHolsterMaker3", "ShortWeaponHolsterMaker4"]

var _body := ""
var _check := false
var _skel_path := ""     # "MeshRoot/Model/<armature>/Skeleton3D", relative to the scene root

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	_check = "--check" in args
	for a in args:
		if a.begins_with("--body="): _body = a.substr(7)
	if _body == "" or _body == "godot_chan":
		push_error("give --body=<a body other than the reference>")
		quit(1); return
	var facts_path := "res://assets/characters/%s/%s.body.json" % [_body, _body]
	if not FileAccess.file_exists(facts_path):
		push_error("no %s -- run tools/godot/measure_body.gd first" % facts_path)
		quit(1); return
	var facts: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(facts_path))
	_build(facts)

func _title(body: String) -> String:
	var out := ""
	for part in body.split("_"):
		out += part.substr(0, 1).to_upper() + part.substr(1)
	return out

func _build(f: Dictionary) -> void:
	var out_path := OUT_DIR + "CharacterVisuals_" + _title(_body) + ".tscn"

	var root3 := Node3D.new()
	root3.name = "CharacterVisuals"
	root3.set_script(load(S_VISUALS))

	# --- the body ------------------------------------------------------------------------------
	var mesh_root := Node3D.new()
	mesh_root.name = "MeshRoot"
	root3.add_child(mesh_root)
	_made_node(mesh_root)
	# GEN_EDIT_STATE_INSTANCE is what lets `pack()` tell an instance's own state from an override.
	# Without it the saved scene carries the whole body: measured, 2.0 MB of ArrayMesh and material
	# for Shino, against 40 KB with it -- and it fails the other way too, because without
	# `set_editable_instance` the additions inside the instance are simply not stored at all. Both
	# are needed, and each failure is silent in a different direction.
	var model := (load(String(f["glb"])) as PackedScene).instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE)
	model.name = "Model"
	mesh_root.add_child(model)
	var skel := _find_class(model, "Skeleton3D") as Skeleton3D
	var armature := skel.get_parent() as Node3D
	# The armature is turned 180 deg about Y, exactly as `merged_animation.tscn` turns the
	# reference's: in bone space the character's face is at +Z, and every rule in the game is
	# written in MeshRoot's frame, where forward is -Z.
	armature.transform = Transform3D(ARMATURE_TURN, Vector3.ZERO)
	_skel_path = "MeshRoot/Model/%s/%s" % [armature.name, skel.name]

	# --- the AnimationTree: the reference's, copied whole ---------------------------------------
	var ref := (load(REFERENCE_SCENE) as PackedScene).instantiate()
	var ref_tree := _find_class(ref, "AnimationTree") as AnimationTree
	var tree := AnimationTree.new()
	tree.name = "AnimationTree"
	root3.add_child(tree)
	_made_node(tree)
	tree.tree_root = (ref_tree.tree_root as AnimationRootNode).duplicate(true)
	tree.add_animation_library(&"", load(ANIM_LIB))
	tree.root_node = NodePath("../MeshRoot/Model/%s" % armature.name)
	for p in ref_tree.get_property_list():
		var n: String = p["name"]
		if n.begins_with("parameters/"):
			tree.set(n, ref_tree.get(n))
	tree.active = ref_tree.active
	tree.callback_mode_process = ref_tree.callback_mode_process
	tree.deterministic = ref_tree.deterministic

	# THE SHARED LIBRARY'S POSITION KEYS ARE ABSOLUTE METRES, AND `motion_scale` IS GODOT'S OWN
	# ANSWER TO THAT. W40 keeps position tracks only on `Root` and `pelvis` because everything else
	# is a fact about the BODY -- but the two that are kept are still metres authored on a 1.49 m
	# reference, and the biggest of them is the stance DROP: `crawl_idle` takes Root to -0.601 and
	# `crouch_idle` to -0.289 whoever is playing it. On a taller body that is not enough drop, and
	# the body ends up standing in the air: measured, in `crawl_idle` the foot sits at 0.163 m on the
	# reference, 0.334 on Shino and 0.525 on Fumiriya (user-reported as "other models float when
	# shooting in crawl"), and in `crouch_idle` 0.014 / 0.103 / 0.178.
	#
	# `Skeleton3D.motion_scale` multiplies exactly those animated positions, which is what it is for
	# (retargeting position tracks onto a differently-sized skeleton) -- so it needs no modifier, no
	# per-frame work and no second copy of the library. The scalar is the body's own PELVIS REST
	# HEIGHT over the reference's: the drop is the pelvis travelling from standing to prone, so it
	# scales with the leg. Measured after: Fumiriya's crawl foot 0.525 -> 0.237 against a
	# proportional target of 0.241, and his crouch foot 0.178 -> 0.040 against 0.021 -- within a
	# centimetre, where it was out by 36 cm. The reference's scalar is 1.0, so it is untouched.
	#
	# W41 recorded this as needing FOOT GROUNDING and rejected leg-length scaling on paper ("the leg
	# rotations fold a longer leg further by themselves"). Measured, that reasoning was wrong: the
	# ratio lands within a centimetre on both bodies and in both stances. Foot grounding is still the
	# exact answer for uneven ground; this is the proportional one, and it is free.
	if f.has("motion_scale"):
		skel.motion_scale = float(f["motion_scale"])

	_weapon_sockets(skel, f)
	_aim_modifiers(skel, ref)
	_camera_and_holsters(skel, f)
	_ragdoll_nodes(skel, f)
	_ik_modifiers(skel, ref, f)
	_stances(root3, f)
	ref.free()

	# --- owners ---------------------------------------------------------------------------------
	# `pack()` stores only nodes that the scene root OWNS, and it stores an INSTANCE (one line plus
	# its overrides) only for a node whose own children it does not own. Owning everything
	# recursively therefore inlines the whole body -- measured, a 2.5 MB scene with every vertex of
	# the mesh in it. So exactly the nodes this tool made are owned, and the model's own subtree is
	# left alone.
	for n in _made:
		n.owner = root3
	model.owner = root3
	root3.set_editable_instance(model, true)

	root3.set("mesh_config", _mesh_config(f))

	var packed := PackedScene.new()
	var err := packed.pack(root3)
	if err != OK:
		push_error("pack failed: %d" % err)
		quit(1); return
	if _check:
		# Saved BESIDE the real file, never to `user://`: a .tscn's ext_resource paths are written
		# relative to where it is being saved, so a check written elsewhere differs from the real
		# one for a reason that is nothing to do with the scene. It keeps the `.tscn` extension
		# too: ResourceSaver picks its format from that, and silently writes nothing without it.
		var tmp := out_path.get_basename() + ".check.tscn"
		ResourceSaver.save(packed, tmp)
		var fresh := FileAccess.get_file_as_string(tmp)
		DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))
		var have := FileAccess.get_file_as_string(out_path) if FileAccess.file_exists(out_path) else ""
		if not _same(fresh, have):
			var fa := _norm(fresh).split("\n")
			var ha := _norm(have).split("\n")
			for i in mini(fa.size(), ha.size()):
				if fa[i] != ha[i]:
					print("  first difference at line %d:\n    fresh: %s\n    disk : %s" % [i + 1, fa[i].substr(0, 140), ha[i].substr(0, 140)])
					break
			print("  lines fresh=%d disk=%d" % [fa.size(), ha.size()])
		if _same(fresh, have):
			print("[build-visuals] %s is up to date" % out_path)
			quit(0)
		else:
			print("[build-visuals] STALE: %s does not match a fresh build" % out_path)
			quit(1)
		return
	err = ResourceSaver.save(packed, out_path)
	print("[build-visuals] %s %s" % [out_path, "written" if err == OK else "FAILED %d" % err])
	quit(0 if err == OK else 1)

## Two saves of the same scene differ in their generated resource ids and per-node unique ids,
## which say nothing about the scene. Compare everything else.
func _same(a: String, b: String) -> bool:
	return _norm(a) == _norm(b)

## Godot mints a fresh id for every resource and node on each save, so two saves of the same scene
## never match as text. Each id is renumbered by ORDER OF FIRST APPEARANCE rather than stripped:
## stripping them would also hide a genuine re-wiring, which is the thing this check is for.
func _norm(t: String) -> String:
	var out := t
	var uniq := RegEx.create_from_string('unique_id=[0-9]+')
	out = uniq.sub(out, "unique_id=#", true)
	var uid := RegEx.create_from_string('uid="[^"]*"')
	out = uid.sub(out, 'uid="#"', true)
	var seen := {}
	var re := RegEx.create_from_string('"[A-Za-z0-9]+_[A-Za-z0-9]+"')
	var res := re.search_all(out)
	var rebuilt := ""
	var at := 0
	for m in res:
		var key: String = m.get_string()
		if not seen.has(key): seen[key] = "\"#%d\"" % seen.size()
		rebuilt += out.substr(at, m.get_start() - at) + String(seen[key])
		at = m.get_end()
	return rebuilt + out.substr(at)

## Every node this tool created, in creation order, so `pack()` can be told exactly what is ours.
var _made: Array[Node] = []

func _made_node(n: Node) -> Node:
	_made.append(n)
	return n

# ---------------------------------------------------------------------------------------------
func _find_class(n: Node, cls: String) -> Node:
	if n.get_class() == cls: return n
	for c in n.get_children():
		var r := _find_class(c, cls)
		if r != null: return r
	return null

func _find_name(n: Node, nm: String) -> Node:
	if n.name == nm: return n
	for c in n.get_children():
		var r := _find_name(c, nm)
		if r != null: return r
	return null

func _t(s: Variant) -> Transform3D:
	return str_to_var(String(s)) as Transform3D

func _attach(skel: Skeleton3D, node_name: String, bone: String) -> BoneAttachment3D:
	var a := BoneAttachment3D.new()
	a.name = node_name
	skel.add_child(a)
	_made_node(a)
	a.bone_name = bone
	a.bone_idx = skel.find_bone(bone)
	return a

func _marker(parent: Node, nm: String, t: Transform3D) -> Marker3D:
	var m := Marker3D.new()
	m.name = nm
	parent.add_child(m)
	_made_node(m)
	m.transform = t
	return m

func _modifier(skel: Skeleton3D, nm: String, script_path: String) -> Node:
	var n := SkeletonModifier3D.new()
	n.name = nm
	skel.add_child(n)
	_made_node(n)
	n.set_script(load(script_path))
	return n

# ---------------------------------------------------------------------------------------------
# The hand: one BoneAttachment3D on `hand_r` carrying one socket per grip ARCHETYPE (W20), and the
# built-in Fist, which `WeaponController.discoverPrePlacedWeapons` finds by looking under each
# socket for a WeaponItem.
func _weapon_sockets(skel: Skeleton3D, f: Dictionary) -> void:
	var a := _attach(skel, "WeaponAttachment", "hand_r")
	var sockets: Dictionary = f["sockets"]
	for nm in SOCKETS:
		var m := _marker(a, nm, _t(sockets[nm]) if sockets.has(nm) else Transform3D.IDENTITY)
		if nm == "SocketFist":
			var fist := (load(FIST) as PackedScene).instantiate()
			fist.name = "Fist"
			m.add_child(fist)
			_made_node(fist)

# The two aim modifiers, in tree order: the spine squares the chest, then the shoulders and neck
# carry whatever is left (W5, W7 -- they COMPOSE, so the order is the design).
func _aim_modifiers(skel: Skeleton3D, ref: Node) -> void:
	var spine := _modifier(skel, "SpineAimModifier", S_SHOULDER)
	var ref_spine := _find_name(ref, "SpineAimModifier")
	spine.set("driven_bones", ref_spine.get("driven_bones"))
	_modifier(skel, "ShoulderAimModifier", S_SHOULDER)

# The first-person eye, and the holster slings. The eye marker sits on `neck_01` because that is
# the bone the FPS rig filters (W5); where it sits on it is this body's own measured eye.
func _camera_and_holsters(skel: Skeleton3D, f: Dictionary) -> void:
	var neck := _attach(skel, "NeckAttachment", "neck_01")
	_marker(neck, "MarkerFPSCamera", _t(f["fps_marker"]))
	var back := _attach(skel, "BackHolster", "spine_03")
	var hip := _attach(skel, "HipWeaponHolster", "spine_01")
	var h: Dictionary = f["holsters"]
	for nm in BACK_MARKERS:
		_marker(back, nm, _t(h[nm]))
	for nm in HIP_MARKERS:
		_marker(hip, nm, _t(h[nm]))

# ---------------------------------------------------------------------------------------------
# The ragdoll, which is also the hitbox set. Layout follows the editor's own "create physical
# skeleton" rule -- the body looks down the bone with its origin half way along it, and the pin
# joint sits at the child -- so the joints behave as they always have. What does NOT follow it is
# the capsule's RADIUS: the editor's `0.1 x bone length` gives a 1.4 cm hand, which is exactly the
# size Jolt's ray test steps over at range (CLAUDE.md, "A long ray steps over a small, far
# hitbox"). The radius is the body's own thickness around that bone, measured off the skin.
func _ragdoll_nodes(skel: Skeleton3D, f: Dictionary) -> void:
	var sim := PhysicalBoneSimulator3D.new()
	sim.name = "PhysicalBoneSimulator3D"
	skel.add_child(sim)
	_made_node(sim)
	var bones: Dictionary = f["ragdoll"]
	# In the order the deriver measured them, so the file reads down the body the way the
	# reference's does, and the simulator's chain is built parent-first.
	for bone in f["ragdoll_order"]:
		if not bones.has(bone): continue
		var d: Dictionary = bones[bone]
		var child_local: Vector3 = str_to_var(String(d["child"])) as Vector3
		var length := float(d["length"])
		if length < 0.001: continue
		var pb := PhysicalBone3D.new()
		pb.name = "Physical Bone " + bone
		sim.add_child(pb)
		_made_node(pb)
		pb.bone_name = bone
		pb.collision_layer = HITBOX_LAYER
		pb.collision_mask = 0
		pb.joint_type = PhysicalBone3D.JOINT_TYPE_PIN
		var body := Transform3D.IDENTITY
		body = body.looking_at(child_local, Vector3.UP, true)
		body.origin = body.basis * Vector3(0, 0, -length * 0.5)
		pb.body_offset = body
		var joint := Transform3D.IDENTITY
		joint.origin = Vector3(0, 0, length)
		pb.joint_offset = joint
		var shape := CollisionShape3D.new()
		shape.name = "CollisionShape3D"
		pb.add_child(shape)
		_made_node(shape)
		var cap := CapsuleShape3D.new()
		cap.radius = float(d["radius"])
		cap.height = maxf(length, float(d["radius"]) * 2.0 + 0.001)
		shape.shape = cap
		# a CapsuleShape3D runs along its own +Y; the body runs down its -Z
		shape.transform = Transform3D(Basis(Vector3(1, 0, 0), Vector3(0, 0, -1), Vector3(0, 1, 0)), Vector3.ZERO)

# The IK layer, after the aim modifiers and in the order the weapon fit depends on: the stock is
# seated, the kick moves the gun, and the support hand follows wherever the gun ENDED UP (W27).
func _ik_modifiers(skel: Skeleton3D, ref: Node, f: Dictionary) -> void:
	var stock := _modifier(skel, "StockMountIKModifier", S_STOCK)
	stock.set("mount_markers", PackedStringArray(f["mount_markers"]))
	var offs: Array[Vector3] = []
	for v in f["mount_offsets"]: offs.append(str_to_var(String(v)) as Vector3)
	stock.set("mount_offsets", offs)
	_modifier(skel, "WeaponRecoilModifier", S_RECOIL)
	_modifier(skel, "SupportHandIKModifier", S_SUPPORT)

# The stance colliders. Each ceiling ray starts at one waist-height point on the body and reaches
# its own stance's top, which is the question `Stance.isBlocked` asks.
func _stances(root3: Node3D, f: Dictionary) -> void:
	var holder := Node3D.new()
	holder.name = "StanceCollisions"
	root3.add_child(holder)
	_made_node(holder)
	var stances: Dictionary = f["stances"]
	var rays: Dictionary = f["stance_rays"]
	for nm in ["Upright", "Crouch", "Crawl"]:
		var d: Dictionary = stances[nm]
		var cs := CollisionShape3D.new()
		cs.name = nm
		holder.add_child(cs)
		_made_node(cs)
		cs.position = Vector3(0, float(d["y"]), 0)
		cs.disabled = nm != "Upright"
		if String(d["shape"]) == "capsule":
			var cap := CapsuleShape3D.new()
			cap.radius = float(d["radius"])
			cap.height = maxf(float(d["height"]), cap.radius * 2.0 + 0.001)
			cs.shape = cap
		else:
			var cyl := CylinderShape3D.new()
			cyl.radius = float(d["radius"])
			cyl.height = float(d["height"])
			cs.shape = cyl
		if rays.has(nm):
			var r: Dictionary = rays[nm]
			var ray := RayCast3D.new()
			ray.name = "RayCast3D"
			cs.add_child(ray)
			_made_node(ray)
			ray.position = Vector3(0, float(r["y"]), 0)
			ray.target_position = Vector3(0, float(r["reach"]), 0)

# ---------------------------------------------------------------------------------------------
# MeshConfig: the one place that says where everything above lives, so the rest of the game never
# has to know the shape of a particular body's scene.
func _mesh_config(f: Dictionary) -> Resource:
	var mc := Resource.new()
	mc.set_script(load(S_MESHCFG))
	mc.set("animation_tree_path", NodePath("AnimationTree"))
	mc.set("mesh_root_path", NodePath("MeshRoot"))
	mc.set("physical_bone_simulator_path", NodePath(_skel_path + "/PhysicalBoneSimulator3D"))
	mc.set("weapon_attachment_path", NodePath(_skel_path + "/WeaponAttachment"))
	mc.set("aim_spine_modifier_path", NodePath(_skel_path + "/SpineAimModifier"))
	mc.set("shoulder_aim_modifier_path", NodePath(_skel_path + "/ShoulderAimModifier"))
	mc.set("stock_mount_modifier_path", NodePath(_skel_path + "/StockMountIKModifier"))
	mc.set("recoil_modifier_path", NodePath(_skel_path + "/WeaponRecoilModifier"))
	mc.set("fps_camera_marker_path", NodePath(_skel_path + "/NeckAttachment/MarkerFPSCamera"))
	var heads: Array[NodePath] = []
	for m in f["head_meshes"]: heads.append(NodePath(_skel_path + "/" + String(m)))
	mc.set("head_mesh_paths", heads)
	var sockets: Array[NodePath] = []
	for nm in SOCKETS: sockets.append(NodePath(_skel_path + "/WeaponAttachment/" + nm))
	for nm in BACK_MARKERS: sockets.append(NodePath(_skel_path + "/BackHolster/" + nm))
	for nm in HIP_MARKERS: sockets.append(NodePath(_skel_path + "/HipWeaponHolster/" + nm))
	mc.set("socket_paths", sockets)
	var cols := {}
	var rays := {}
	for nm in ["Upright", "Crouch", "Crawl"]:
		cols[nm] = NodePath("StanceCollisions/" + nm)
	for nm in (f["stance_rays"] as Dictionary):
		rays[nm] = NodePath("StanceCollisions/%s/RayCast3D" % nm)
	mc.set("stance_collider_paths", cols)
	mc.set("stance_raycast_paths", rays)
	return mc
