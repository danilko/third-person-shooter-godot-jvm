extends SceneTree
## MEASURE a body, so nothing about it is typed in by hand (PLAN.md 6.9, blender/SKELETON_CONTRACT.md).
##
##   godot --headless --path . --script tools/godot/measure_body.gd -- --body=shino [--check]
##
## The skeleton CONTRACT (bone names, rest orientations) is what makes one clip library play on every
## body. Everything else a character needs is a fact about THAT BODY and does not come free: where the
## eye is, where a grip sits in the fist, where a stock meets the shoulder, how a rifle hangs on the
## back, how wide the body is for its stance capsule, how thick each limb is for its hitbox. Godot-chan's
## were measured and hand-tuned over the whole W series; a second body must not inherit them, and must
## not have them guessed either.
##
## So this is the ONE owner of those numbers. It reads a body's own `.glb` -- its rest skeleton and its
## SKINNED mesh -- and writes `assets/characters/<body>/<body>.body.json`, which
## `tools/godot/build_character_visuals.gd` turns into that body's `CharacterVisuals_*.tscn`. The file is
## reviewed like the road record: it is derived, a re-run reproduces it, and a diff is readable.
##
## **Its control is Godot-chan.** Run it on the reference and the numbers it derives must land on the
## numbers the shipped scene was hand-tuned to -- that is what says a rule is a rule and not a fit to one
## body. Where a number is genuinely an ARTIST's choice with no rule behind it (which way a pistol sits in
## the fist), it is not invented here: it is TRANSFERRED from the reference through a frame built out of
## the body's own bones, so the reference reproduces itself exactly and another body gets the same
## relationship to its own hand. `--check` re-derives and fails if the file on disk is stale.
##
## Frames, stated once because every mistake here is invisible:
##   - GAME frame = `MeshRoot`'s: +X right, +Y up, **-Z forward**, which is the frame every rule in
##     this codebase is written in.
##   - BONE frame = what `Skeleton3D.get_bone_global_rest` hands back, and it is NOT the same one:
##     the model scene turns the armature 180 deg about Y, so in bone space the character's FACE is
##     at +Z. Measured on the reference -- the backpack sits at bone z -0.22..-0.10 and the eyes at
##     +0.05..+0.07, and the toe is in front of the ankle at +0.08. Getting this backwards is
##     silent and survives every sanity check: the back sling comes out on the CHEST, and the
##     shoulder pocket lands behind the shoulder instead of on it (both measured, both were here).
##   - a `.tscn` Transform3D literal's 9 basis floats are ROWS, so every transform written here goes
##     through `var_to_str`, the engine's own serialization (W28 paid for this once: printing
##     basis.x/y/z in order transposes it, which lays a slung rifle flat across the back with the
##     position still exactly right).

const REFERENCE_BODY := "godot_chan"
const BODIES := {
	"godot_chan": "res://assets/characters/godot_chan/merged_animation.glb",
	"shino": "res://assets/characters/shino/shino.glb",
	"fumiriya": "res://assets/characters/fumiriya/fumiriya.glb",
}
## The reference's authored sockets, in `hand_r`'s local frame, exactly as
## CharacterVisuals_GodotChan.tscn holds them. They are an artist's placement of a grip in a fist --
## there is no rule to re-derive -- so they are transferred through the HAND frame below.
const REFERENCE_SCENE := "res://src/main/resources/com/openworld/character/CharacterVisuals_GodotChan.tscn"

const SOCKETS := ["SocketRifle", "SocketPistol", "SocketLauncher", "SocketMelee", "SocketThrowable", "SocketFist"]
## Bone frame -> game frame. Its own inverse.
const GAME_FROM_BONE := Basis(Vector3(-1, 0, 0), Vector3(0, 1, 0), Vector3(0, 0, -1))
const OUT_DIR := "res://assets/characters/"
## The pose every skin reading is taken in: standing, arms down, which is what "the shoulder", "the
## back" and "how wide is this body" mean.
const STAND_CLIP := "upright_idle"
## The pose the shoulder is read in: the weapon hold, which is where a stock has to seat.
const HOLD_CLIP := "upright_hold_rifle"

var _body := ""
var _check := false
var _fail := 0
var _eye_point := Vector3.ZERO

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	_check = "--check" in args
	for a in args:
		if a.begins_with("--body="): _body = a.substr(7)
	if not BODIES.has(_body):
		push_error("give --body=<%s>" % String("|").join(PackedStringArray(BODIES.keys())))
		quit(1); return
	_run()

func _run() -> void:
	var ref := Rig.of(root, BODIES[REFERENCE_BODY])
	var rig := ref if _body == REFERENCE_BODY else Rig.of(root, BODIES[_body])

	var doc := {}
	doc["body"] = _body
	doc["glb"] = BODIES[_body]
	doc["generated_by"] = "tools/godot/measure_body.gd"
	doc["reference"] = REFERENCE_BODY
	doc["armature"] = rig.armature.name
	doc["skeleton"] = String(rig.armature.get_path_to(rig.skel))

	# Every skin reading is taken STANDING (see Rig.pose). The bones' RESTS are what the socket
	# and ragdoll frames are built from, and those are pose-independent by definition.
	rig.pose(STAND_CLIP)
	ref.pose(STAND_CLIP)

	_meshes(doc, rig)
	_size(doc, rig)
	_hand(doc, rig, ref)
	_camera(doc, rig, ref)
	_shoulder(doc, rig, ref)
	_holsters(doc, rig, ref)
	_stances(doc, rig, ref)
	_ragdoll(doc, rig)

	var path := OUT_DIR + _body + "/" + _body + ".body.json"
	var text := JSON.stringify(doc, "  ", true) + "\n"
	var old := ""
	if FileAccess.file_exists(path):
		old = FileAccess.get_file_as_string(path)
	if _check:
		if old == text:
			print("[measure-body] %s is up to date" % path)
			quit(0)
		else:
			print("[measure-body] STALE: %s does not match a fresh measurement of %s" % [path, doc["glb"]])
			quit(1)
		return
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_string(text)
	f.close()
	print("[measure-body] wrote %s%s" % [path, "" if old == "" else (" (unchanged)" if old == text else " (CHANGED)")])
	quit(1 if _fail > 0 else 0)

# ---------------------------------------------------------------------------------------------
# The rig, and the one place a mesh is skinned by hand.
#
# `MeshInstance3D.bake_mesh_from_current_skeleton_pose` is refused headless ("The source mesh must
# have its skin registered with a valid skeleton"), so every skinned reading here is computed from
# the bind poses and the bone poses, exactly as probe_weapon_fit.gd does for the shoulder pocket.
# ---------------------------------------------------------------------------------------------
class Rig:
	var node: Node3D
	var armature: Node3D
	var skel: Skeleton3D
	var meshes: Array = []

	static func of(parent: Node, glb: String) -> Rig:
		var r := Rig.new()
		r.node = (load(glb) as PackedScene).instantiate()
		parent.add_child(r.node)
		r.skel = Rig._first(r.node, "Skeleton3D") as Skeleton3D
		r.armature = r.skel.get_parent()
		for c in r.skel.get_children():
			if c is MeshInstance3D: r.meshes.append(c)
		r.skel.reset_bone_poses()
		return r

	static func _first(n: Node, cls: String) -> Node:
		if n.get_class() == cls: return n
		for c in n.get_children():
			var x := Rig._first(c, cls)
			if x != null: return x
		return null

	func rest(bone: String) -> Transform3D:
		var i := skel.find_bone(bone)
		return skel.get_bone_global_rest(i) if i >= 0 else Transform3D.IDENTITY

	## The bone's frame in the POSE currently applied -- which is what a marker under a
	## BoneAttachment3D is measured in, and what a skin reading must be taken in.
	func posed(bone: String) -> Transform3D:
		var i := skel.find_bone(bone)
		return gpose(i) if i >= 0 else Transform3D.IDENTITY

	## A bone's global pose, walked up the parent chain from the LOCAL poses.
	##
	## `Skeleton3D.get_bone_global_pose()` is NOT usable here: in a headless `--script` run nothing
	## drives the skeleton's own processing, so it keeps handing back the rest pose however the bones
	## are posed -- and `force_update_all_bone_transforms()` does not clear it either. Measured: with
	## `crawl_idle` applied, the local poses put the head at 0.322 m while that call still answered
	## 1.357. A stale reading there is silent and looks exactly like "this body measures the same in
	## every stance", which is how it was found.
	func gpose(i: int) -> Transform3D:
		var t := Transform3D.IDENTITY
		while i >= 0:
			t = skel.get_bone_pose(i) * t
			i = skel.get_bone_parent(i)
		return t

	## Stand the body in a clip from the shared library. Every skin measurement here is taken
	## standing, never in the imported T-pose: a column of shoulder skin, the back's surface and the
	## width of a crouch are all different pieces of anatomy with the arms out sideways.
	##
	## `seek(0.0, true, true)` right after `play()` applies NOTHING -- it seeks to the position the
	## player is already at -- and leaves the rest pose standing, which reads as a body that simply
	## measures the same in every stance. `advance()` is what applies a pose.
	## The pose the game holds a weapon in, which is NOT one clip: the AnimationTree takes the legs
	## and spine from the locomotion idle and only the clavicles, arms, hands and fingers from the
	## hold clip, through `WeaponBlend`'s filter. Posing the hold clip whole instead moves the chest
	## too, and the shoulder then reads somewhere the game never puts it.
	func pose_hold(idle: String, hold: String) -> bool:
		if not pose(hold): return false
		var kept := {}
		for i in skel.get_bone_count():
			var n := skel.get_bone_name(i)
			for pre in ["clavicle_", "upperarm_", "lowerarm_", "hand_", "thumb_", "index_",
						"middle_", "ring_", "pinky_"]:
				if n.begins_with(pre):
					kept[i] = skel.get_bone_pose(i)
					break
		if not pose(idle): return false
		for i in kept:
			skel.set_bone_pose_position(i, (kept[i] as Transform3D).origin)
			skel.set_bone_pose_rotation(i, (kept[i] as Transform3D).basis.get_rotation_quaternion())
			skel.set_bone_pose_scale(i, (kept[i] as Transform3D).basis.get_scale())
		return true

	func pose(clip: String, at: float = 0.0) -> bool:
		if _ap == null:
			_ap = AnimationPlayer.new()
			node.add_child(_ap)
			_ap.root_node = _ap.get_path_to(armature)
			_ap.add_animation_library(&"", load("res://src/main/resources/com/openworld/character/anim/character_anims.res"))
		if not _ap.has_animation(clip): return false
		skel.reset_bone_poses()
		_ap.play(clip)
		_ap.advance(maxf(0.001, at))
		return true
	var _ap: AnimationPlayer = null

	func has(bone: String) -> bool:
		return skel.find_bone(bone) >= 0

	## Every vertex of `mesh`, skinned by the skeleton's CURRENT pose, in the armature's frame,
	## with the surface index it came from. Returns [PackedVector3Array verts, PackedInt32Array surf,
	## PackedInt32Array dominant_bone].
	func skinned(mesh: MeshInstance3D) -> Array:
		var skin: Skin = mesh.skin
		var binds: Array[Transform3D] = []
		for bi in skin.get_bind_count():
			var bone: int = skin.get_bind_bone(bi)
			if bone < 0: bone = skel.find_bone(skin.get_bind_name(bi))
			binds.append(gpose(bone) * skin.get_bind_pose(bi))
		var out := PackedVector3Array()
		var surf := PackedInt32Array()
		var dom := PackedInt32Array()
		for si in mesh.mesh.get_surface_count():
			var arr: Array = mesh.mesh.surface_get_arrays(si)
			var verts: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
			var bones: PackedInt32Array = arr[Mesh.ARRAY_BONES]
			var weights: PackedFloat32Array = arr[Mesh.ARRAY_WEIGHTS]
			var k: int = bones.size() / maxi(1, verts.size())
			for vi in verts.size():
				var w := Vector3.ZERO
				var best_w := -1.0
				var best_b := -1
				for j in k:
					var ww: float = weights[vi * k + j]
					if ww > 0.0:
						var bi2: int = bones[vi * k + j]
						w += (binds[bi2] * verts[vi]) * ww
						if ww > best_w:
							best_w = ww
							best_b = skin.get_bind_bone(bi2)
							if best_b < 0: best_b = skel.find_bone(skin.get_bind_name(bi2))
				out.append(w)
				surf.append(si)
				dom.append(best_b)
		return [out, surf, dom]

	func material_name(mesh: MeshInstance3D, si: int) -> String:
		var m: Material = mesh.mesh.surface_get_material(si)
		return m.resource_name if m != null else ""

# ---------------------------------------------------------------------------------------------
# 1. Meshes and regions.
#
# A material's NAME says which part of the body it is -- VRoid stamps a `_SKIN`/`_CLOTH`/`_FACE`/
# `_EYE`/`_HAIR` suffix on every one, and Godot-chan's read the same way with a keyword. That
# classification is what tells FPS which meshes are the head, tells the crown measurement to ignore
# hair, finds the eye, and is the list 6.10's one-toon-material-per-region pass will merge along.
# ---------------------------------------------------------------------------------------------
## First match wins, lower case. A backpack and a pair of headphones land in OTHER on purpose: an
## ACCESSORY is not the body's silhouette, and every rule that reads a surface -- how tall the
## character is, where its back is, how wide a stance capsule must be -- means the body.
const REGION_RULES := [
	["eyebrow|eyelash|eyeline|eyeextra|eyehighlight|brow|lash", "FACE"],
	["eye", "EYE"],
	["hair", "HAIR"],
	["face|_skin|body_material", "SKIN"],
	["cloth|tops|bottoms|shoes|armor", "CLOTH"],
	["", "OTHER"],
]

func _region(mat: String) -> String:
	var m := mat.to_lower()
	for rule in REGION_RULES:
		if rule[0] == "": return rule[1]
		if RegEx.create_from_string(rule[0]).search(m) != null: return rule[1]
	return "OTHER"

func _meshes(doc: Dictionary, rig: Rig) -> void:
	var head_bone := rig.skel.find_bone("head_2")
	var neck_bone := rig.skel.find_bone("neck_01")
	var head_set := {}
	for i in rig.skel.get_bone_count():
		var b := i
		while b >= 0:
			if b == head_bone or b == neck_bone:
				head_set[i] = true
				break
			b = rig.skel.get_bone_parent(b)

	var names := PackedStringArray()
	var heads := PackedStringArray()
	var regions := {}
	for m in rig.meshes:
		names.append(m.name)
		var sk: Array = rig.skinned(m)
		var dom: PackedInt32Array = sk[2]
		var surf: PackedInt32Array = sk[1]
		var on_head := 0
		for i in dom.size():
			if head_set.has(dom[i]): on_head += 1
		for si in m.mesh.get_surface_count():
			var mat := rig.material_name(m, si)
			regions[m.name + "/" + str(si)] = {"material": mat, "region": _region(mat)}
		# A mesh is hidden in first person when it is MOSTLY head/neck skin. Per mesh, because
		# visibility is per node: a body mesh carrying one back-hair surface stays visible, and that
		# is a known wart, not a rule -- W36 had to split Godot-chan's collar out of `armor` for the
		# same reason.
		if float(on_head) / float(maxi(1, dom.size())) > 0.5:
			heads.append(m.name)
	doc["meshes"] = names
	doc["head_meshes"] = heads
	doc["surface_regions"] = regions

# ---------------------------------------------------------------------------------------------
# 2. Size and the eye.
#
# `height_m` is the whole silhouette; `crown_m` excludes HAIR and OTHER, because hair and headphones
# are not how tall someone is (Godot-chan: crown 1.435, hair and headphones 1.458 and 1.469) and the
# holster solver measures a butt's clearance against the SKULL.
#
# The eye is the EYE surfaces' centroid. That is a real measurement on every body here, and it is
# what the first-person camera mount wants -- W5's rig filters the neck bone and keeps a slow
# baseline, so the mount only has to BE the eye.
# ---------------------------------------------------------------------------------------------
func _size(doc: Dictionary, rig: Rig) -> void:
	var top := -INF
	var crown := -INF
	var eye := Vector3.ZERO
	var eye_n := 0
	for m in rig.meshes:
		var sk: Array = rig.skinned(m)
		var verts: PackedVector3Array = sk[0]
		var surf: PackedInt32Array = sk[1]
		var reg := {}
		for si in m.mesh.get_surface_count():
			reg[si] = _region(rig.material_name(m, si))
		for i in verts.size():
			var v := verts[i]
			var r: String = reg[surf[i]]
			top = maxf(top, v.y)
			if r == "SKIN" or r == "FACE" or r == "EYE": crown = maxf(crown, v.y)
			if r == "EYE":
				eye += v
				eye_n += 1
	doc["height_m"] = snappedf(top, 0.0001)
	doc["crown_m"] = snappedf(crown, 0.0001)
	var e: Vector3 = eye / maxf(1.0, float(eye_n)) if eye_n > 0 else rig.posed("head_2").origin
	doc["eye"] = _v(GAME_FROM_BONE * e)          # game frame, so -z is in front of the face
	doc["eye_samples"] = eye_n
	_eye_point = e

# ---------------------------------------------------------------------------------------------
# 3. The hand, and the six weapon sockets.
#
# A socket is where a weapon's GRIP sits in the firing fist (W19/W20: the model's origin IS its
# grip, so the socket carries the whole placement and the character needs one per grip ARCHETYPE,
# not one per weapon). Where exactly inside a fist a pistol grip sits is an artist's choice --
# Godot-chan's rifle and pistol sockets were ADOPTED from a pose the artist made (W25) -- so there
# is no rule here to re-derive, and inventing one would quietly move a fit that four gates measure.
#
# So it is TRANSFERRED, through a frame built out of the hand's OWN bones:
#     along  = wrist -> the knuckle line          (down the hand)
#     across = index knuckle -> pinky knuckle     (the line a handle runs along)
#     normal = the palm's outward normal
#     L      = |wrist -> knuckles|, the hand's own length
# A socket is recorded as (position / L, rotation) in that frame, so feeding the reference its own
# hand reproduces its authored transform EXACTLY, and another body gets the same grip in its own
# fist. **It is a transfer, not a measurement**: the gates that decide whether it landed are
# `probe_weapon_sockets.gd`, `probe_weapon_fit.gd` and the poke check in `probe_weapon_holster.gd`.
#
# The hand is NOT proportional to the body, which is exactly why it has its own scale: Godot-chan's
# hand is 0.086 m long on a 1.49 m body and Fumiriya's is 0.072 m on a 1.91 m one.
# ---------------------------------------------------------------------------------------------
const KNUCKLES := ["index_01_r", "middle_01_r", "ring_01_r", "pinky_01_r"]

func _hand_frame(rig: Rig) -> Dictionary:
	var hand := rig.rest("hand_r")
	var inv := hand.affine_inverse()
	var k := Vector3.ZERO
	for b in KNUCKLES: k += inv * rig.rest(b).origin
	k /= float(KNUCKLES.size())
	var along := k.normalized()
	var across_raw := (inv * rig.rest("pinky_01_r").origin) - (inv * rig.rest("index_01_r").origin)
	var normal := along.cross(across_raw).normalized()
	var across := normal.cross(along).normalized()
	return {"basis": Basis(across, along, normal), "length": k.length()}

func _hand(doc: Dictionary, rig: Rig, ref: Rig) -> void:
	var hf := _hand_frame(rig)
	var rf := _hand_frame(ref)
	doc["hand_length_m"] = snappedf(hf["length"], 0.0001)

	var authored := _reference_sockets()
	var out := {}
	for name in SOCKETS:
		if not authored.has(name):
			continue
		var t: Transform3D = authored[name]
		# into the reference hand frame, normalised by its hand length
		var p: Vector3 = (rf["basis"] as Basis).inverse() * t.origin / float(rf["length"])
		var b: Basis = (rf["basis"] as Basis).inverse() * t.basis
		# and back out through this body's
		var t2 := Transform3D((hf["basis"] as Basis) * b, (hf["basis"] as Basis) * (p * float(hf["length"])))
		out[name] = var_to_str(_round_t(t2))
	doc["sockets"] = out

## The authored socket transforms on the reference, read from the scene that holds them so there is
## no second copy of them in this file.
func _reference_sockets() -> Dictionary:
	var sc := (load(REFERENCE_SCENE) as PackedScene).instantiate()
	var out := {}
	var attach := Rig._first(sc, "BoneAttachment3D")
	for name in SOCKETS:
		var n := _by_name(sc, name)
		if n != null: out[name] = (n as Node3D).transform
	sc.free()
	return out

func _by_name(n: Node, nm: String) -> Node:
	if n.name == nm: return n
	for c in n.get_children():
		var r := _by_name(c, nm)
		if r != null: return r
	return null

# ---------------------------------------------------------------------------------------------
# 3b. The first-person eye.
#
# `MarkerFPSCamera` hangs off a BoneAttachment3D on `neck_01`, because that is the bone W5's rig
# FILTERS -- it splits the bone's motion into a slow baseline (which IS the resting eye point, so
# the mount's height and forward offset come for free) and a scaled, clamped residual. Its
# ORIENTATION is never used: the view is `ControlRotation`. So the only thing that has to be right
# is the position, and that is this body's own measured eye.
#
# The reference's marker is NOT at its eye -- it sits 15 cm behind it, at the back of the skull,
# which on a body whose head is hidden in first person is invisible and was never re-measured (W11
# found the same thing on the cockpit mount). A new body gets its eye.
func _camera(doc: Dictionary, rig: Rig, ref: Rig) -> void:
	var ref_marker := _reference_markers(["MarkerFPSCamera"])
	var basis_game := Basis.IDENTITY
	if ref_marker.has("MarkerFPSCamera"):
		basis_game = (GAME_FROM_BONE * ref.posed("neck_01").basis * (ref_marker["MarkerFPSCamera"] as Transform3D).basis).orthonormalized()
	var neck := rig.posed("neck_01")
	var design := Transform3D(basis_game, GAME_FROM_BONE * _eye_point)
	doc["fps_marker"] = var_to_str(_round_t(neck.affine_inverse() * Transform3D(GAME_FROM_BONE) * design))
	doc["eye_above_ground_m"] = snappedf(_eye_point.y, 0.0001)

# ---------------------------------------------------------------------------------------------
# 4. The shoulder: where a stock is mounted, and where a launcher tube rests.
#
# `StockMountIKModifier.mountOffsets` are anchors relative to `upperarm_r`'s origin, in
# `clavicle_r`'s orthonormalised basis. The reference's were ADOPTED from a pose the artist made
# (W25), and `probe_weapon_fit.gd` keeps an eye on them by re-deriving the pocket off the skin every
# run (W22's rule: the frontmost skin vertex in a column just inboard of and below the joint) and
# failing on more than 2 cm of drift -- measured 1.5 cm.
#
# So the STOCK anchor is `the skin's pocket + the reference's own correction` -- the 1.4 cm by which
# the artist's pose differs from the reference's skin reading, carried across. One rule for every
# body: it reproduces the reference exactly, and on another body it follows that body's shoulder
# instead of the reference's. Transferring the authored value outright was tried and the probe
# refused it, which is the probe doing its job: scaled by shoulder width it lands 4.9 cm (Shino) and
# 4.1 cm (Fumiriya) from where those shoulders actually are, against its 2 cm tolerance.
#
# The launcher's shoulder rest has no surface rule -- it is a spot on the deltoid the artist chose
# (W25) -- so it stays a scaled transfer.
## The column, in metres and NOT scaled by the body: `probe_weapon_fit.gd` is the owner of this
## check and states it in metres, and a shoulder is about the same size on any adult-ish body.
## Scaling it was tried, and a scaled column is a different strip of anatomy rather than the same
## one smaller -- it put the anchor 2.6 cm from where the probe then found Shino's shoulder.
const POCKET_INBOARD := Vector2(0.02, 0.07)
const POCKET_BELOW := 0.04
const MOUNT_NODE := "StockMountIKModifier"

func _shoulder_width(rig: Rig) -> float:
	return absf(rig.rest("upperarm_r").origin.x - rig.rest("upperarm_l").origin.x)

func _shoulder(doc: Dictionary, rig: Rig, ref: Rig) -> void:
	# The shoulder is read in the HOLD pose, which is what `probe_weapon_fit.gd` measures against --
	# the weapon-hold clips blade the shoulders (W24), so the same column of skin is a different
	# piece of anatomy standing idle. Measured on Shino, reading it in `upright_idle` instead puts
	# the anchor 2.6 cm from where the probe then finds her shoulder.
	rig.pose_hold(STAND_CLIP, HOLD_CLIP)
	ref.pose_hold(STAND_CLIP, HOLD_CLIP)
	var s: float = _shoulder_width(rig) / _shoulder_width(ref)
	var joint := rig.posed("upperarm_r").origin
	var pocket := _skin_pocket(rig, joint)
	var cb := rig.posed("clavicle_r").basis.orthonormalized()
	# `probe_weapon_fit.gd --emit-pocket` measures this on the body the GAME poses, with the whole
	# animation tree running, and is the owner of the number. This file's own reading is the
	# bootstrap that lets a body's scene be built in the first place.
	var measured := _measured_pocket()

	var authored := _reference_mount()
	var markers: Array = authored["markers"]
	var ref_joint := ref.posed("upperarm_r").origin
	var ref_pocket := _skin_pocket(ref, ref_joint)
	var ref_cb := ref.posed("clavicle_r").basis.orthonormalized()
	var correction := Vector3.ZERO
	if ref_pocket != Vector3.INF and authored["offsets"].size() > 0:
		correction = (authored["offsets"][0] as Vector3) - ref_cb.inverse() * (ref_pocket - ref_joint)
	var offsets: Array = []
	for i in authored["offsets"].size():
		var v: Vector3 = authored["offsets"][i] as Vector3
		if i == 0 and measured != Vector3.INF:
			v = measured
		elif i == 0 and pocket != Vector3.INF:
			v = cb.inverse() * (pocket - joint) + correction * s
		else:
			v = v * s
		offsets.append(var_to_str(_round_v(v)))
	doc["shoulder_width_m"] = snappedf(_shoulder_width(rig), 0.0001)
	doc["mount_markers"] = markers
	doc["mount_offsets"] = offsets
	doc["pocket_from_skin"] = _v(cb.inverse() * (pocket - joint)) if pocket != Vector3.INF else "<no skin>"
	doc["pocket_correction"] = _v(correction)
	doc["pocket_source"] = "probe_weapon_fit" if measured != Vector3.INF else "estimate"
	rig.pose(STAND_CLIP)
	ref.pose(STAND_CLIP)

## The pocket `probe_weapon_fit.gd --emit-pocket` last measured on this body, if it has been run.
func _measured_pocket() -> Vector3:
	var path := OUT_DIR + _body + "/" + _body + ".pocket.json"
	if not FileAccess.file_exists(path): return Vector3.INF
	var d: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	return str_to_var(String(d["pocket"])) as Vector3

func _reference_mount() -> Dictionary:
	var sc := (load(REFERENCE_SCENE) as PackedScene).instantiate()
	var n := _by_name(sc, MOUNT_NODE)
	var out := {"markers": [], "offsets": []}
	if n != null:
		for m in (n.get("mount_markers") as Array): out["markers"].append(String(m))
		for v in (n.get("mount_offsets") as Array): out["offsets"].append(v as Vector3)
	sc.free()
	return out

## The frontmost skin vertex in a column just inboard of and below the shoulder joint, in the bone
## frame. Hold pose only. Returns Vector3.INF when the body has no skin there.
func _skin_pocket(rig: Rig, joint: Vector3) -> Vector3:
	var mesh := _torso_mesh(rig)
	if mesh == null: return Vector3.INF
	var best := Vector3(0, 0, -INF)      # frontmost = the LARGEST bone-space z (the face is at +Z)
	var found := false
	var side := signf(joint.x)
	var sk: Array = rig.skinned(mesh)
	var verts: PackedVector3Array = sk[0]
	for i in verts.size():
		var w := verts[i]
		var inboard: float = absf(joint.x) - absf(w.x)
		if signf(w.x) == side and inboard > POCKET_INBOARD.x and inboard < POCKET_INBOARD.y \
				and w.y < joint.y and w.y > joint.y - POCKET_BELOW and w.z > best.z:
			best = w
			found = true
	return best if found else Vector3.INF

## The mesh the SHOULDER is part of -- asked of the skin, never by name (`armor` on the reference,
## `Body` on a VRoid body). The same rule as `probe_weapon_fit._torso_mesh`, so the deriver and the
## gate agree about what they are measuring.
func _torso_mesh(rig: Rig) -> MeshInstance3D:
	var want := {}
	for b in ["clavicle_r", "upperarm_r", "spine_03"]:
		var bi := rig.skel.find_bone(b)
		if bi >= 0: want[bi] = true
	var best: MeshInstance3D = null
	var best_n := -1
	for m in rig.meshes:
		var sk: Array = rig.skinned(m)
		var dom: PackedInt32Array = sk[2]
		var n := 0
		for d in dom:
			if want.has(d): n += 1
		if n > best_n:
			best_n = n
			best = m
	return best

# 5. The holsters.
#
# The back pair is a DESIGN in the body's frame (W28: a sling running down-left across the back,
# tilted 22 deg from vertical, the gun lying flat against it, the pair separated in DEPTH because
# laterally it cannot be). What the BODY supplies is where that back is: the shoulder line, the
# spine, and the back's own skin surface. What the WEAPON supplies is the clearance behind it, which
# does not scale with the body -- a rifle is the same thickness on a small character as on a big one.
#
# The hip pair keeps the reference's authored bases (a sling direction is a design choice, and the
# contract guarantees a bone's rest means the same thing on every body); only the position scales,
# with the hips' own width.
# ---------------------------------------------------------------------------------------------
const SLING_TILT_DEG := 22.0
## Each back socket as (fraction of the shoulder half-width, fraction of spine_03 -> clavicle, metres
## behind the back's skin). Reproduces the reference's solved (0.120, 1.090, 0.200) / (0.020, 1.055, 0.320).
const BACK_SLINGS := {
	"LongWeaponHolsterMaker1": {"across": 0.812, "up": 0.513, "behind": 0.070},
	"LongWeaponHolsterMaker2": {"across": 0.135, "up": 0.349, "behind": 0.190},
}
const HIP_SOCKETS := ["ShortWeaponHolsterMaker1", "ShortWeaponHolsterMaker2",
					  "ShortWeaponHolsterMaker3", "ShortWeaponHolsterMaker4"]
const BACK_SPARE := ["LongWeaponHolsterMaker3", "LongWeaponHolsterMaker4"]

func _holsters(doc: Dictionary, rig: Rig, ref: Rig) -> void:
	var out := {}
	var back_bone := rig.posed("spine_03")
	var clav := rig.posed("clavicle_r").origin
	var half := absf(rig.posed("upperarm_r").origin.x)
	var back_z := _back_surface(rig, back_bone.origin.y, clav.y)
	for name in BACK_SLINGS:
		var d: Dictionary = BACK_SLINGS[name]
		var design := Transform3D(_sling_basis(), Vector3(
			float(d["across"]) * half,
			back_bone.origin.y + float(d["up"]) * (clav.y - back_bone.origin.y),
			back_z + float(d["behind"])))
		out[name] = var_to_str(_round_t(back_bone.affine_inverse() * Transform3D(GAME_FROM_BONE) * design))
	# the spare back pair and the hips: the reference's own transforms, position scaled by the body
	var authored := _reference_markers(BACK_SPARE + HIP_SOCKETS)
	var hip_s: float = _hip_width(rig) / _hip_width(ref)
	var sh_s: float = _shoulder_width(rig) / _shoulder_width(ref)
	for name in authored:
		var t: Transform3D = authored[name]
		var s: float = sh_s if name in BACK_SPARE else hip_s
		out[name] = var_to_str(_round_t(Transform3D(t.basis, t.origin * s)))
	doc["holsters"] = out
	doc["back_surface_z"] = snappedf(back_z, 0.0001)

## The sling's basis in the BODY frame: local -Z down the sling (tilted toward the body's left),
## local X straight out of the back so the weapon lies FLAT against it. W28's rule, restated.
func _sling_basis() -> Basis:
	var down := Vector3(0, -1, 0).rotated(Vector3(0, 0, 1), deg_to_rad(-SLING_TILT_DEG)).normalized()
	var out_of_back := Vector3(0, 0, 1)
	var x := out_of_back
	var z := -down
	var y := z.cross(x).normalized()
	x = y.cross(z).normalized()
	return Basis(x, y, z)

## How far BEHIND the body origin the back's skin sits (game frame, so behind is +z), between the
## spine_03 and shoulder heights.
func _back_surface(rig: Rig, y0: float, y1: float) -> float:
	var z := -INF
	for m in rig.meshes:
		var sk: Array = rig.skinned(m)
		var verts: PackedVector3Array = sk[0]
		var surf: PackedInt32Array = sk[1]
		var reg := {}
		for si in m.mesh.get_surface_count():
			reg[si] = _region(rig.material_name(m, si))
		for i in verts.size():
			var r: String = reg[surf[i]]
			if r == "HAIR" or r == "OTHER": continue
			var v := verts[i]
			if v.y > y0 and v.y < y1 and absf(v.x) < 0.10 and -v.z > z: z = -v.z
	return z

func _hip_width(rig: Rig) -> float:
	return absf(rig.rest("thigh_r").origin.x - rig.rest("thigh_l").origin.x)

func _reference_markers(names: Array) -> Dictionary:
	var sc := (load(REFERENCE_SCENE) as PackedScene).instantiate()
	var out := {}
	for name in names:
		var n := _by_name(sc, name)
		if n != null: out[name] = (n as Node3D).transform
	sc.free()
	return out

# ---------------------------------------------------------------------------------------------
# 6. The stance capsules.
#
# A stance collider is what the WORLD pushes against, so the only thing that makes one right is that
# the body fits inside it. The reference's were hand-tuned; a second body's start from those scaled
# by height and are then WIDENED to whatever the body actually measures in that stance's idle pose,
# skinned from the shared clip library. Hair is left out: it is not something a wall should stop.
#
# Both ceiling rays start at the crouch capsule's centre -- one waist-height point on the body --
# and reach their own stance's top, which is the question `Stance.isBlocked` asks.
# ---------------------------------------------------------------------------------------------
const SHARED_LIB := "res://src/main/resources/com/openworld/character/anim/character_anims.res"
const STANCE_CLIPS := {"Upright": "upright_idle", "Crouch": "crouch_idle", "Crawl": "crawl_idle"}
const STANCE_MARGIN := 0.02
const STANCE_SAMPLES := 4

func _stances(doc: Dictionary, rig: Rig, ref: Rig) -> void:
	var scale: float = float(doc["crown_m"]) / _crown(ref)
	var width_s: float = _shoulder_width(rig) / _shoulder_width(ref)
	var authored := _reference_stances()
	# ONE radius for every capsule stance, and it is a fact about the BODY, not about what a stance's
	# limbs do. Every shooter walks a crouched character on the cylinder it stands on and lets the
	# knees clip; measured on the reference, widening to whatever `crouch_idle` reaches instead gives
	# a 1.17 m wide collider -- the crouch leans the torso forward, so even the TRUNK is half a metre
	# off the body's own axis. So: the reference's radius scaled by this body's shoulders, floored by
	# what the trunk measures standing over its own feet.
	var body_radius: float = float(authored["Upright"]["radius"]) * width_s
	for k in STANCE_SAMPLES:
		if not rig.pose(STANCE_CLIPS["Upright"], float(k) * 0.37): break
		body_radius = maxf(body_radius, float(_extent(rig)["torso"]) + STANCE_MARGIN)
	body_radius = snappedf(body_radius, 0.001)

	var out := {}
	for stance in STANCE_CLIPS:
		var clip: String = STANCE_CLIPS[stance]
		var m := {"top": -INF, "radius": 0.0, "torso": 0.0}
		for k in STANCE_SAMPLES:
			if not rig.pose(clip, float(k) * 0.37): break
			var e := _extent(rig)
			m["top"] = maxf(float(m["top"]), float(e["top"]))
			m["radius"] = maxf(float(m["radius"]), float(e["radius"]))
			m["torso"] = maxf(float(m["torso"]), float(e["torso"]))
		var a: Dictionary = authored[stance]
		var top: float = maxf(float(a["top"]) * scale, float(m["top"]) + STANCE_MARGIN)

		var rad: float = body_radius
		if a["shape"] != "capsule":
			rad = maxf(float(a["radius"]) * scale, float(m["radius"]) + STANCE_MARGIN)
		var row := {"shape": a["shape"], "radius": snappedf(rad, 0.001)}
		if a["shape"] == "capsule":
			row["height"] = snappedf(top, 0.001)
			row["y"] = snappedf(top * 0.5, 0.001)
		else:
			# the crawl cylinder: a flat disc the body lies inside, so its height is the body's
			# THICKNESS lying down and its radius is the longest reach across the ground.
			var h: float = maxf(float(a["height"]) * scale, float(m["top"]) + STANCE_MARGIN)
			row["height"] = snappedf(h, 0.001)
			row["y"] = snappedf(h * 0.5, 0.001)
		out[stance] = row
	rig.pose(STAND_CLIP)

	var waist: float = float((out["Crouch"] as Dictionary)["y"])
	var rays := {}
	for stance in ["Upright", "Crouch"]:
		var r: Dictionary = out[stance]
		rays[stance] = {"y": snappedf(waist - float(r["y"]), 0.001),
						"reach": snappedf(float(r["height"]) - waist, 0.001)}
	doc["stances"] = out
	doc["stance_rays"] = rays
	doc["body_radius_m"] = body_radius

## Top and horizontal reach of the posed, skinned body, hair excluded.
func _extent(rig: Rig) -> Dictionary:
	var top := -INF
	var rad := 0.0
	var torso := 0.0
	var trunk := {}
	for b in ["pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head_2", "clavicle_l", "clavicle_r"]:
		var bi := rig.skel.find_bone(b)
		if bi >= 0: trunk[bi] = true
	for m in rig.meshes:
		var sk: Array = rig.skinned(m)
		var verts: PackedVector3Array = sk[0]
		var surf: PackedInt32Array = sk[1]
		var dom: PackedInt32Array = sk[2]
		var reg := {}
		for si in m.mesh.get_surface_count():
			reg[si] = _region(rig.material_name(m, si))
		for i in verts.size():
			var r: String = reg[surf[i]]
			if r == "HAIR" or r == "OTHER": continue
			var v := verts[i]
			top = maxf(top, v.y)
			var h := Vector2(v.x, v.z).length()
			rad = maxf(rad, h)
			if trunk.has(dom[i]): torso = maxf(torso, h)
	return {"top": top, "radius": rad, "torso": torso}

func _crown(rig: Rig) -> float:
	var crown := -INF
	for m in rig.meshes:
		var sk: Array = rig.skinned(m)
		var verts: PackedVector3Array = sk[0]
		var surf: PackedInt32Array = sk[1]
		var reg := {}
		for si in m.mesh.get_surface_count():
			reg[si] = _region(rig.material_name(m, si))
		for i in verts.size():
			var r: String = reg[surf[i]]
			if r == "SKIN" or r == "FACE" or r == "EYE": crown = maxf(crown, verts[i].y)
	return crown

func _reference_stances() -> Dictionary:
	var sc := (load(REFERENCE_SCENE) as PackedScene).instantiate()
	var out := {}
	for stance in STANCE_CLIPS:
		var n := _by_name(sc, stance) as CollisionShape3D
		var sh: Shape3D = n.shape
		if sh is CapsuleShape3D:
			out[stance] = {"shape": "capsule", "radius": (sh as CapsuleShape3D).radius,
						   "height": (sh as CapsuleShape3D).height, "top": n.position.y * 2.0}
		else:
			out[stance] = {"shape": "cylinder", "radius": (sh as CylinderShape3D).radius,
						   "height": (sh as CylinderShape3D).height, "top": n.position.y * 2.0}
	sc.free()
	return out

# ---------------------------------------------------------------------------------------------
# 7. The ragdoll, which is also the HITBOX set.
#
# Every `PhysicalBone3D` here is two things at once: a ragdoll link, and the shape a bullet has to
# hit (`CollisionLayers.HITBOX`, and `Health`'s per-bone damage table addresses it by name). The
# editor's "create physical skeleton" sizes a capsule at `radius = 0.1 x bone length`, which is why
# Godot-chan's hands are 1.4 cm across -- and a capsule that small is exactly what Jolt's ray test
# steps over at range (CLAUDE.md, "A long ray steps over a small, far hitbox"). So the LENGTH comes
# from the bone and the RADIUS comes from the SKIN: the body's own thickness around that bone.
#
# Bone order and layout follow the editor's rule so the joints behave as they always have: the body
# looks down the bone, its origin half way along it, and the pin joint sits at the child.
# ---------------------------------------------------------------------------------------------
const RAGDOLL := {
	"pelvis": "spine_01", "spine_01": "spine_02", "spine_02": "spine_03", "spine_03": "neck_01",
	"head_2": "", "upperarm_l": "lowerarm_l", "lowerarm_l": "hand_l", "hand_l": "middle_01_l",
	"upperarm_r": "lowerarm_r", "lowerarm_r": "hand_r", "hand_r": "middle_01_r",
	"thigh_l": "calf_l", "calf_l": "foot_l", "foot_l": "ball_l",
	"thigh_r": "calf_r", "calf_r": "foot_r", "foot_r": "ball_r",
}
const RAGDOLL_ORDER := ["pelvis", "spine_01", "spine_02", "spine_03", "head_2",
	"upperarm_l", "lowerarm_l", "hand_l", "upperarm_r", "lowerarm_r", "hand_r",
	"thigh_l", "calf_l", "foot_l", "thigh_r", "calf_r", "foot_r"]
const RADIUS_PERCENTILE := 0.75   # of the skin's distance from the bone axis; the tail is a sleeve
const MIN_RADIUS := 0.02          # m; under this Jolt loses the shape to a long ray anyway

func _ragdoll(doc: Dictionary, rig: Rig) -> void:
	var per_bone := _skin_by_bone(rig)
	var out := {}
	for bone in RAGDOLL_ORDER:
		if not rig.has(bone): continue
		var bi := rig.skel.find_bone(bone)
		var child: String = RAGDOLL[bone]
		# The capsule's AXIS is the child's rest offset in the bone's own frame -- a fact about the
		# skeleton, pose-independent, and what the PhysicalBone3D's body offset is built from.
		var local_child := Vector3.ZERO
		var axis_len := 0.0
		if child != "" and rig.has(child):
			local_child = rig.skel.get_bone_rest(rig.skel.find_bone(child)).origin
			axis_len = local_child.length()
		# The RADIUS is read in the POSE the skin was measured in, or the reading is taken in a
		# frame the skin is not in: measured, doing it in the rest frame gave a 0.44 m hand.
		var posed := rig.gpose(bi)
		var pts: Array = per_bone.get(bi, [])
		if axis_len < 0.001:
			axis_len = _leaf_length(posed, pts)
			local_child = Vector3(0, axis_len, 0)
		out[bone] = {
			"length": snappedf(axis_len, 0.0001),
			"radius": snappedf(maxf(MIN_RADIUS, _sleeve_radius(posed, local_child, pts)), 0.0001),
			"child": var_to_str(_round_v(local_child)),
			"samples": pts.size(),
		}
	doc["ragdoll"] = out
	doc["ragdoll_order"] = RAGDOLL_ORDER

## Every skinned vertex, filed under the bone that dominates it (hair and eyes left out: they are
## not a hitbox).
##
## The lists are `Array`, not `PackedVector3Array`: a Packed array is a VALUE in GDScript, so
## `out[b].append(v)` appends to a COPY and throws it away -- silently, leaving every bone with
## zero samples and every hitbox radius on its floor. (The same shape as godot-jvm's mutating
## `Transform3D.times`: an expression that reads like it edits in place and does not.)
func _skin_by_bone(rig: Rig) -> Dictionary:
	var out := {}
	for m in rig.meshes:
		var sk: Array = rig.skinned(m)
		var verts: PackedVector3Array = sk[0]
		var surf: PackedInt32Array = sk[1]
		var dom: PackedInt32Array = sk[2]
		var reg := {}
		for si in m.mesh.get_surface_count():
			reg[si] = _region(rig.material_name(m, si))
		for i in verts.size():
			var r: String = reg[surf[i]]
			if r == "HAIR" or r == "EYE": continue
			var b := dom[i]
			if not out.has(b): out[b] = []
			(out[b] as Array).append(verts[i])
	return out

## How thick the body is around this bone: a percentile of its skin's distance from the bone's axis,
## so a sleeve, a cuff or a stray vertex does not set the radius.
func _sleeve_radius(rest: Transform3D, axis_local: Vector3, pts: Array) -> float:
	if pts.is_empty(): return 0.0
	var inv := rest.affine_inverse()
	var dir := axis_local.normalized()
	var ds := PackedFloat32Array()
	for p in pts:
		var lp: Vector3 = inv * (p as Vector3)
		ds.append((lp - dir * lp.dot(dir)).length())
	ds.sort()
	return ds[mini(ds.size() - 1, int(float(ds.size()) * RADIUS_PERCENTILE))]

## A leaf bone's length from its own skin: how far it reaches along the bone's +Y.
func _leaf_length(rest: Transform3D, pts: Array) -> float:
	var inv := rest.affine_inverse()
	var top := 0.0
	for p in pts:
		top = maxf(top, (inv * (p as Vector3)).y)
	return maxf(0.05, top)

# ---------------------------------------------------------------------------------------------
func _v(v: Vector3) -> String:
	return var_to_str(_round_v(v))

func _round_v(v: Vector3) -> Vector3:
	return Vector3(snappedf(v.x, 0.000001), snappedf(v.y, 0.000001), snappedf(v.z, 0.000001))

func _round_t(t: Transform3D) -> Transform3D:
	var b := t.basis
	for i in 3:
		b[i] = Vector3(snappedf(b[i].x, 0.000001), snappedf(b[i].y, 0.000001), snappedf(b[i].z, 0.000001))
	return Transform3D(b, _round_v(t.origin))
