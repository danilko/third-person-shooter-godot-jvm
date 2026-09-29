extends SceneTree
## Bake a crowd body into a VERTEX ANIMATION TEXTURE (user, 2026-09-27; PLAN.md 3.32 crowd tiers).
##
##   godot --headless --path . --script tools/godot/bake_ped_vat.gd -- --body=shino [--verts=5000] [--fps=15]
##
## WHY. Measured on a bare stand (this PC): 600 light peds as skinned bodies cost 18.9 ms/frame walking and
## 4.2 ms paused -- the CPU animation + skinning of a 158-bone skeleton, ~26 us per ped per frame even when the
## ped is hidden; the GPU drew them for under 1 ms. A VAT moves the whole animation into the vertex shader:
## a ped becomes one MultiMesh instance (a transform + 4 floats), a body type ONE draw call, and a frame costs
## what writing the transforms costs.
##
## WHAT. Built FROM the body's light-ped mesh (`<body>_ped.tscn`, blender/tools/build_ped_body.py: one surface,
## one atlas) -- so it can never drift from the body -- simplified with Godot's own LOD generator to about
## `--verts` vertices (at the distances this tier is drawn a 21k-vertex body is ~14 px tall), animated by the
## SHARED library clips of the body's GAIT (character_gaits.json: a female body walks her own walk), skinned
## here on the CPU once, and written as positions, one texel per vertex, one texture ROW per frame:
##
##   <body>_vat_mesh.res  ArrayMesh: the simplified body at rest (UV + index; VERTEX_ID reads the texture)
##   <body>_vat_pos.res   ImageTexture RGBAH, width = vertex count, height = total frames
##   <body>_vat.json      clip -> {row, frames, fps}, the atlas, the vertex count
##
## Positions are in the ped ROOT's frame (the armature's 180-degree turn included), so a MultiMesh transform
## is the ped's own world transform, exactly what PedCrowd already writes.

const CLIPS := {
	"idle": "upright_idle_relaxed",
	"walk": "upright_walk",              # the NORMAL walk, a gait clip: each gait library holds its own
	"run": "upright_sprint_forward",
	"cower": "crouch_idle",
	"phone": "upright_phone",
	"talk": "upright_talk",
}
const GAITS := "res://src/main/resources/com/openworld/character/anim/character_gaits.json"
## A body whose default simplification tears (measured 2026-09-27: Fumiriya's trousers opened at 4k-5k
## vertices, LOD 2-3) gets its own budget. --verts overrides.
const BODY_VERTS := {"fumiriya": 8000}
const MAX_WIDTH := 8192

var _fail := 0

func _initialize() -> void:
	var body := ""
	var target := -1
	var fps := 15.0
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--body="): body = a.substr(7)
		elif a.begins_with("--verts="): target = int(a.substr(8))
		elif a.begins_with("--fps="): fps = float(a.substr(6))
	if body == "":
		_die("give --body=<name>")
		return
	if target < 0: target = int(BODY_VERTS.get(body, 5000))
	var dir := "res://assets/characters/%s/" % body
	var ped_scene := dir + "%s_ped.tscn" % body
	if not ResourceLoader.exists(ped_scene):
		_die("no %s -- run blender/tools/build_ped_body.py first" % ped_scene)
		return
	var gaits: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(GAITS))
	var gait := String(gaits["bodies"].get(body, "m"))
	var lib_path := String(gaits["gaits"][gait]["library"])
	var lib: AnimationLibrary = load(lib_path)

	var inst: Node3D = (load(ped_scene) as PackedScene).instantiate()
	root.add_child(inst)
	var skel := inst.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
	var mi := inst.find_children("*", "MeshInstance3D", true, false)[0] as MeshInstance3D
	var arm := skel.get_parent() as Node3D
	for old in inst.find_children("*", "AnimationPlayer", true, false):
		(old as AnimationPlayer).stop()
		old.get_parent().remove_child(old)
		old.free()
	var ap := AnimationPlayer.new()
	inst.add_child(ap)
	ap.root_node = ap.get_path_to(arm)
	ap.add_animation_library(&"", lib)

	# -- the mesh, simplified ---------------------------------------------------------------------
	var src: Array = mi.mesh.surface_get_arrays(0)
	var n_src: int = (src[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
	var per: int = (src[Mesh.ARRAY_BONES] as PackedInt32Array).size() / n_src
	var im := ImporterMesh.new()
	im.add_surface(Mesh.PRIMITIVE_TRIANGLES, src)
	im.generate_lods(25.0, 60.0, [])
	var indices: PackedInt32Array = src[Mesh.ARRAY_INDEX]
	var chosen := -1
	for lod in im.get_surface_lod_count(0):
		var li := im.get_surface_lod_indices(0, lod)
		var used := {}
		for v in li: used[v] = true
		if used.size() <= target:
			indices = li
			chosen = lod
			break
	var remap := {}
	var order: PackedInt32Array = []
	for v in indices:
		if not remap.has(v):
			remap[v] = order.size()
			order.append(v)
	var n := order.size()
	if n > MAX_WIDTH:
		_die("%d vertices after simplification, over the %d-wide texture -- lower --verts" % [n, MAX_WIDTH])
		return
	print("[vat] %s: gait %s (%s); %d -> %d vertices (LOD %d), %d triangles"
		% [body, gait, lib_path.get_file(), n_src, n, chosen, indices.size() / 3])

	var s_pos: PackedVector3Array = src[Mesh.ARRAY_VERTEX]
	var s_uv: PackedVector2Array = src[Mesh.ARRAY_TEX_UV]
	var s_bones: PackedInt32Array = src[Mesh.ARRAY_BONES]
	var s_w: PackedFloat32Array = src[Mesh.ARRAY_WEIGHTS]
	var pos := PackedVector3Array(); pos.resize(n)
	var uv := PackedVector2Array(); uv.resize(n)
	var vb := PackedInt32Array(); vb.resize(n * per)
	var vw := PackedFloat32Array(); vw.resize(n * per)
	for i in n:
		var o := order[i]
		pos[i] = s_pos[o]
		uv[i] = s_uv[o]
		for k in per:
			vb[i * per + k] = s_bones[o * per + k]
			vw[i * per + k] = s_w[o * per + k]
	var idx := PackedInt32Array(); idx.resize(indices.size())
	for i in indices.size(): idx[i] = remap[indices[i]]

	# -- the skin binds -> skeleton bones ------------------------------------------------------------
	var skin := mi.skin
	var bind_bone := PackedInt32Array(); bind_bone.resize(skin.get_bind_count())
	for b in skin.get_bind_count():
		var bb := skin.get_bind_bone(b)
		if bb < 0: bb = skel.find_bone(skin.get_bind_name(b))
		bind_bone[b] = bb
	# skeleton space -> ped root space (the armature's own 180-degree turn, the mesh node's offset)
	var to_root: Transform3D = arm.transform * skel.transform
	var mesh_to_skel: Transform3D = mi.transform

	# -- bake every clip, frame by frame -------------------------------------------------------------
	var rows: Array[PackedFloat32Array] = []
	var table := {}
	for key in CLIPS:
		var clip := String(CLIPS[key])
		if not ap.has_animation(clip):
			print("[vat] FAIL: %s has no clip %s (%s)" % [lib_path.get_file(), clip, key])
			_fail += 1
			continue
		var length := ap.get_animation(clip).length
		var frames := maxi(1, int(round(length * fps)))
		table[key] = {"clip": clip, "row": rows.size(), "frames": frames, "fps": frames / maxf(length, 1e-3)}
		ap.play(clip)
		for f in frames:
			ap.seek(length * f / frames, true)
			var gp := _globals(skel)
			var mats: Array[Transform3D] = []
			mats.resize(bind_bone.size())
			for b in bind_bone.size():
				mats[b] = gp[bind_bone[b]] * skin.get_bind_pose(b) if bind_bone[b] >= 0 else Transform3D()
			var row := PackedFloat32Array(); row.resize(n * 4)
			for i in n:
				var p := mesh_to_skel * pos[i]
				var acc := Vector3.ZERO
				var wsum := 0.0
				for k in per:
					var w := vw[i * per + k]
					if w <= 0.0: continue
					acc += w * (mats[vb[i * per + k]] * p)
					wsum += w
				if wsum > 0.0: acc /= wsum
				var r := to_root * acc
				row[i * 4] = r.x
				row[i * 4 + 1] = r.y
				row[i * 4 + 2] = r.z
				row[i * 4 + 3] = 1.0
			rows.append(row)
		print("[vat]   %-6s %-26s %3d frames at %.1f fps" % [key, clip, frames, table[key]["fps"]])

	# -- write --------------------------------------------------------------------------------------
	var data := PackedFloat32Array()
	for r in rows: data.append_array(r)
	var img := Image.create_from_data(n, rows.size(), false, Image.FORMAT_RGBAF, data.to_byte_array())
	img.convert(Image.FORMAT_RGBAH)
	var tex := ImageTexture.create_from_image(img)
	var am := ArrayMesh.new()
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = _rest_pose(pos, to_root, mesh_to_skel)
	arrays[Mesh.ARRAY_TEX_UV] = uv
	arrays[Mesh.ARRAY_INDEX] = idx
	am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var mat := mi.mesh.surface_get_material(0)
	if mi.get_surface_override_material(0) != null: mat = mi.get_surface_override_material(0)
	var atlas: Texture2D = mat.get("albedo_texture") if mat != null else null
	var cutoff: float = mat.get("alpha_scissor_threshold") if mat != null else 0.5

	var mesh_path := dir + "%s_vat_mesh.res" % body
	var tex_path := dir + "%s_vat_pos.res" % body
	var meta_path := dir + "%s_vat.json" % body
	if ResourceSaver.save(am, mesh_path, ResourceSaver.FLAG_COMPRESS) != OK: _fail += 1
	if ResourceSaver.save(tex, tex_path, ResourceSaver.FLAG_COMPRESS) != OK: _fail += 1
	var meta := {
		"generated_by": "tools/godot/bake_ped_vat.gd",
		"body": body, "gait": gait, "library": lib_path,
		"vertices": n, "rows": rows.size(),
		"mesh": mesh_path, "positions": tex_path,
		"atlas": atlas.resource_path if atlas != null else "",
		"alpha_scissor": cutoff,
		"clips": table,
	}
	var fh := FileAccess.open(meta_path, FileAccess.WRITE)
	fh.store_string(JSON.stringify(meta, "  ", true) + "\n")
	fh.close()
	print("[vat] wrote %s (%dx%d) + %s + %s" % [tex_path, n, rows.size(), mesh_path.get_file(), meta_path.get_file()])
	inst.free()
	print("[vat] %s" % ("PASS" if _fail == 0 else "FAIL (%d)" % _fail))
	quit(_fail)

## Skeleton-space global pose of every bone, from the LOCAL poses (headless, get_bone_global_pose can
## return the rest pose: W41's trap).
func _globals(skel: Skeleton3D) -> Array[Transform3D]:
	var out: Array[Transform3D] = []
	out.resize(skel.get_bone_count())
	var done := PackedByteArray(); done.resize(skel.get_bone_count())
	for b in skel.get_bone_count(): _global(skel, b, out, done)
	return out

func _global(skel: Skeleton3D, b: int, out: Array[Transform3D], done: PackedByteArray) -> Transform3D:
	if done[b] == 1: return out[b]
	var p := skel.get_bone_parent(b)
	var t := skel.get_bone_pose(b)
	if p >= 0: t = _global(skel, p, out, done) * t
	out[b] = t
	done[b] = 1
	return t

func _rest_pose(pos: PackedVector3Array, to_root: Transform3D, mesh_to_skel: Transform3D) -> PackedVector3Array:
	var out := PackedVector3Array(); out.resize(pos.size())
	for i in pos.size(): out[i] = to_root * (mesh_to_skel * pos[i])
	return out

func _die(msg: String) -> void:
	print("[vat] FAIL: %s" % msg)
	quit(1)
