extends SceneTree

# The LIGHT-PED body (PLAN.md 3.6d / the A1 perf item): PedCrowd's far tier draws a script-free body
# between promoteDistance (80 m) and drawDistance (180 m), and what costs anything at that range is
# DRAW CALLS. The shipped body is 3 MeshInstance3D but 17 surfaces with 17 materials -- ~17 draws per
# light ped, ~100 in range downtown. blender/tools/build_ped_body.py collapses that to ONE.
#
#   godot --headless --path . --script tools/godot/probe_ped_body.gd
#   ... -- --control      # measure the FULL body instead, which must fail the surface checks
#
# EVERY FAILURE HERE IS SILENT IN GAME. A ped scene that quietly kept 17 surfaces looks identical and
# costs 17x; one whose clips were renamed stands still (AnimationPlayer.play of a missing clip is a
# no-op); one whose skeleton lost a bone plays the walk on a body that does not move. So each is
# asserted, and the control proves the surface checks can fail.

const PED := "res://assets/characters/shino/shino_ped.tscn"
const FULL := "res://assets/characters/shino/shino.tscn"
# PedCrowd.java: WALK_CLIP / RUN_CLIP. A rename there without one here is what this catches.
const CLIPS := ["upright_walk_forward", "upright_sprint_forward"]

var checks := 0
var fails := 0

func ok(cond: bool, msg: String) -> void:
	checks += 1
	if not cond:
		fails += 1
	print(("  ok   " if cond else "  FAIL ") + msg)

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var control := args.has("--control")
	var path := FULL if control else PED
	print("probe_ped_body: %s%s" % [path, " (CONTROL: the full body)" if control else ""])

	var scene: PackedScene = load(path)
	ok(scene != null, "the ped scene loads")
	if scene == null:
		_finish()
		return
	var body: Node3D = scene.instantiate()
	root.add_child(body)
	await process_frame

	# ---- one surface, one material -------------------------------------------------------------
	var mis: Array[MeshInstance3D] = []
	for n in body.find_children("*", "MeshInstance3D", true, false):
		mis.append(n)
	var surfaces := 0
	var mats := {}
	var tris := 0
	for mi in mis:
		var m := mi.mesh
		if m == null:
			continue
		surfaces += m.get_surface_count()
		for s in m.get_surface_count():
			var mat := mi.get_active_material(s)
			if mat != null:
				mats[mat.resource_name if mat.resource_name != "" else str(mat)] = true
			tris += int(m.surface_get_array_len(s))
	print("  %d MeshInstance3D, %d surface(s), %d material(s), %d verts"
		% [mis.size(), surfaces, mats.size(), tris])
	ok(mis.size() == 1, "ONE MeshInstance3D (draw batching cannot merge two nodes)")
	ok(surfaces == 1, "ONE surface: %d" % surfaces)
	ok(mats.size() == 1, "ONE material: %d" % mats.size())

	# ---- the material matches the body it stands beside ------------------------------------------
	var mat: BaseMaterial3D = null
	if mis.size() > 0 and mis[0].mesh != null and mis[0].mesh.get_surface_count() > 0:
		mat = mis[0].get_active_material(0) as BaseMaterial3D
	ok(mat != null, "the surface has a BaseMaterial3D")
	if mat != null:
		# The shipped body is KHR_materials_unlit (a VRoid artefact that survives the export), so a
		# LIT ped would change brightness at the 80 m moment it promotes. build_ped_body clones the
		# body's own material graph so this can never drift; assert what that produced.
		ok(mat.shading_mode == BaseMaterial3D.SHADING_MODE_UNSHADED,
			"unshaded, like the full body (shading_mode=%d)" % mat.shading_mode)
		ok(mat.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR,
			"alpha SCISSOR, not blend (transparency=%d)" % mat.transparency)
		ok(mat.cull_mode == BaseMaterial3D.CULL_DISABLED,
			"double sided: the hair is single-sided cards")
		var tex := mat.albedo_texture
		ok(tex != null and tex.get_width() > 0, "an atlas texture (%s)"
			% ("%dx%d" % [tex.get_width(), tex.get_height()] if tex != null else "none"))

	# ---- the clips PedCrowd plays ---------------------------------------------------------------
	var ap := body.get_node_or_null("AnimationPlayer") as AnimationPlayer
	ok(ap != null, "an AnimationPlayer where PedCrowd looks for it (a direct child)")
	if ap != null:
		var have := ap.get_animation_list()
		for c in CLIPS:
			var a := ap.get_animation(c)
			ok(a != null, "clip %s is present" % c)
			if a != null:
				ok(a.loop_mode != Animation.LOOP_NONE,
					"clip %s LOOPS (a walk cycle that plays once stops the ped)" % c)
		print("  %d clip(s) in the ped body (the full body ships 173)" % have.size())

	# ---- the skeleton is the body's ---------------------------------------------------------------
	var sk := body.find_children("*", "Skeleton3D", true, false)
	ok(sk.size() == 1, "one Skeleton3D")
	if sk.size() == 1:
		var s: Skeleton3D = sk[0]
		print("  %d bones" % s.get_bone_count())
		ok(s.get_bone_count() >= 53, "at least the 53 contract bones: %d" % s.get_bone_count())
		ok(s.find_bone("head_2") >= 0, "head_2 is present (the contract's name, W40)")

	# ---- the turn the scene exists to state -------------------------------------------------------
	var turned := body.get_node_or_null("shino") as Node3D
	ok(turned != null, "the armature node the scene turns")
	if turned != null:
		var fwd := -turned.global_transform.basis.z
		ok(fwd.z > 0.9, "the body faces +Z after the 180-degree turn (%.2f)" % fwd.z)

	_finish()

func _finish() -> void:
	print("probe_ped_body: %d checks, %d failures" % [checks, fails])
	print("RESULT " + ("PASS" if fails == 0 else "FAIL"))
	quit(0 if fails == 0 else 1)
