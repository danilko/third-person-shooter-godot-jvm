extends SceneTree
## build_building_scenes.gd -- write one scene per building from a layout (tools/building_kit/layout_buildings.py).
##
##   godot --headless --path . --script tools/godot/build_building_scenes.gd -- <layout.json> [--only=Id,Id]
##
## For each building: every placed piece's surfaces are MERGED, one surface per material, into one ArrayMesh
## (`<Id>_mesh.res`), so a seven-storey building is one MeshInstance3D and ~8 draw calls, not 300 nodes. The
## layout's boxes become one StaticBody3D (world layer 1); a kit example gets a trimesh collider instead
## (`<Id>_collision.res`). Doors become Marker3D nodes facing out of the building, and the layout's facts are
## the root's `building` meta, which is what `probe_buildings.gd` checks.
##
## Materials have ONE copy per kit: `<kit>/materials/<name>.tres`, written from the imported glTF material the
## first time it is seen and NEVER overwritten, so a hand edit (a Japanese tile tint) survives every rebuild.
## Written with vertex colour OFF as albedo (see `_kit_material`).
## Nothing here decides where a piece goes: that is the layout's.

const OUT_DIR := "res://src/main/resources/com/openworld/world/buildings"
const LOD_NORMAL_MERGE_DEG := 25.0
const LOD_NORMAL_SPLIT_DEG := 60.0
const VIS_BASE_M := 300.0        # visibility_range_end = base + per_height x roof height, clamped
const VIS_PER_HEIGHT := 12.0
const VIS_MIN_M := 350.0
const VIS_MAX_M := 900.0
const VIS_FADE_M := 40.0
const OCCLUDER_TYPES := ["Mansion", "OfficeMid", "PencilBuilding", "ShopHouse", "Apartment", "Warehouse"]
# EVERY building is shut by default (user, 2026-09-19): a city of open doorways into hollow shells reads worse than
# a city you cannot walk into, and an interior is authored content. A building a MISSION needs entered is placed as
# its `<Id>_Open` variant instead, whose doors are real `world.Door` nodes, LOCKED until the mission unlocks them.
const OPEN_VARIANT_SUFFIX := "_Open"
const SHOP_VARIANT_SUFFIX := "_Shop"
const DOOR_SCRIPT := "res://src/main/java/com/openworld/world/Door.java"
const DOOR_LEAF := "res://assets/world_source/kits/quaternius_downtown_city/pieces/doors/Door_1.gltf"
const GLASS_T := 0.06        # a shopfront pane's thickness (its frame reads, not its glass)
const FRAME_T := 0.04        # the slim aluminium stile/rail of a Japanese automatic door
# Two leaves that meet exactly at the doorway centre share a face, and a ray straight down that seam can pass
# between them (measured: probe_buildings' shut-door ray did). A real pair overlaps at the meeting stile, so the
# COLLIDER of each leaf is this much wider each way -- the pane is not, so nothing changes to look at.
const LEAF_MEET := 0.02
const OCCLUDER_INSET := 0.6      # inside the walls, so the box never occludes its own building
const OCCLUDER_FLOOR := 0.3
# PLAN.md 3.18p: the merged mesh is per TYPE and shared, so a per-BUILDING facade tone has to be an INSTANCE
# override -- and an override is addressed by surface INDEX, which only this merge knows. Which material is the
# facade is the kit's fact and is read from the record the retone tool writes, never named twice.
const FACADE_TONES_JSON := "res://assets/world_source/kits/quaternius_downtown_city/materials/facade_tones.json"

# A JAPANESE SHOP WINDOW IS CLEAR GLASS WITH A STRIP ACROSS THE MIDDLE (user, 2026-09-21). What hid the
# customers was never the glass: the kit's shopfront panel carries an opaque `MI_FakeInterior` card BEHIND the
# pane (measured: a 2.53 m quad at z -0.067, right behind a 2.21 m pane at z -0.061). That card is correct for a
# tower with nothing modelled inside it and wrong for a konbini that has a room. So on a building the layout
# says HAS an interior, a shopfront panel loses its card and gains the 目隠しシート -- a white gloss strip at eye
# height with the store's livery stripes through it, leaving the panel clear above and below.
const FAKE_INTERIOR := "MI_FakeInterior"
const BAND_MAT := "MI_ShopBand"
const BAND_DEFAULT_STRIPE := "MI_ShopStripe_Blue"
const BAND_BOTTOM := 1.25       # m above the panel's own FLOOR: a real 1.25-1.70 m strip is at face height
const BAND_HEIGHT := 0.45
const BAND_STRIPE_H := 0.06     # each livery stripe inside the white strip
const BAND_PROUD := 0.012       # in front of the glass plane, so it is applied TO the window and cannot z-fight
const SHOP_GLASS := "MI_GlassShopfront"   # a shop window is clearer than a tower's glazing

var _piece_cache := {}   # path -> Array of [Mesh, surface, Transform3D]
var _materials := {}     # "<kit>/<name>" -> Material


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty():
		push_error("usage: -- <layout.json> [--only=Id,Id]")
		quit(2)
		return
	var only := []
	for a in args:
		if a.begins_with("--only="):
			only = a.substr(7).split(",")
	var doc = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	if doc == null:
		push_error("cannot read " + args[0])
		quit(2)
		return
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUT_DIR))
	var failed := 0
	for b in doc["buildings"]:
		if not only.is_empty() and not only.has(b["id"]):
			continue
		if not _build(b, ""):
			failed += 1
		elif not (b.get("doors", []) as Array).is_empty():
			# ... and the two enterable variants: `_Open` (a mission's, doors LOCKED until it unlocks them) and
			# `_Shop` (a shop or the player's home base: unlocked, automatic doors, GTA's always-open store)
			if not _build(b, OPEN_VARIANT_SUFFIX):
				failed += 1
			if not _build(b, SHOP_VARIANT_SUFFIX):
				failed += 1
	print("BUILD %s" % ("FAIL %d" % failed if failed else "OK"))
	quit(1 if failed else 0)


## Every doorway of a building, as {xf, w, h, frame}: the transform is the door's own frame (origin at the opening's
## centre at floor level, +X along the wall, -Z... the leaf sits in the wall plane), `frame` true when the kit's own
## `DoorFrame_Metal_Single` sits there (then the kit leaf fits it exactly) and false for a doorway modelled into a
## library piece (a terminal's glass front, a station hall), which gets a plain leaf of the declared size.
func _openings(b: Dictionary) -> Array:
	var out := []
	var frames := []
	for p in b["pieces"]:
		if p["piece"] == "DoorFrame_Metal_Single":
			var fpos: Array = p["pos"]
			frames.append(Transform3D(Basis(Vector3.UP, deg_to_rad(float(p["yaw"]))), Vector3(fpos[0], fpos[1], fpos[2])))
	var used := {}
	for d in b["doors"]:
		var c := Vector3(d["center"][0], d["center"][1], d["center"][2])
		var best := -1
		var bd := 0.6
		for i in frames.size():
			if used.has(i):
				continue
			var dist: float = (frames[i] as Transform3D).origin.distance_to(c)
			if dist < bd:
				bd = dist
				best = i
		var style := str(d.get("style", b.get("door_style", "swing")))
		if best >= 0:
			used[best] = true
			out.append({"xf": frames[best], "w": 0.91, "h": 2.002, "frame": true, "style": style})
		else:
			var ov := Vector3(d["outward"][0], 0.0, d["outward"][2])
			var yaw := atan2(ov.x, ov.z) if ov.length() > 0.01 else 0.0
			var op := {"xf": Transform3D(Basis(Vector3.UP, yaw), c), "w": float(d["width"]), "h": float(d["height"]),
					"frame": false, "style": style}
			if d.has("shopfront"):
				op["shopfront"] = d["shopfront"]        # {module, storey}: glaze the rest of the module
			out.append(op)
	# a frame with no meta door (a roof stair house): shut as well, never left as a hole
	for i in frames.size():
		if not used.has(i):
			out.append({"xf": frames[i], "w": 0.91, "h": 2.002, "frame": true,
					"style": str(b.get("door_style", "swing"))})
	return out


var _leaf_mesh: ArrayMesh = null
var _lib_mats := {}

## How many leaves this opening has. A sliding entrance is TWO, parting from the middle (user, 2026-09-20:
## "two door panel, and open on both side"); a hinged door, and a slide too narrow to halve, is one. ONE owner,
## because the shut mesh and the Door nodes must agree about what the door is.
func _panels(b: Dictionary, op: Dictionary) -> int:
	if str(op.get("style", b.get("door_style", "swing"))) != "slide":
		return 1
	return 2 if float(op["w"]) >= 1.2 else 1

## A library material by name (the palette owns its look: `assets/world_source/kits/library/palette.json`).
func _lib_material(name: String) -> Material:
	if not _lib_mats.has(name):
		var path := "res://assets/world_source/kits/library/materials/%s.tres" % name
		_lib_mats[name] = load(path) if ResourceLoader.exists(path) else null
	return _lib_mats[name]

## The fixed glass round a sliding shop entrance: the header over the doors and a sidelight each side, filling
## the module to the storey top. The leaves slide BEHIND these, which is what makes the entrance read as one
## glass shopfront rather than a door punched in a wall (user, 2026-09-20). Returns [{mesh box, xf, mat}].
func _shopfront_glazing(op: Dictionary) -> Array:
	var sf: Dictionary = op["shopfront"]
	var module := float(sf["module"])
	var storey := float(sf["storey"])
	var w := float(op["w"])
	var h := float(op["h"])
	var xf: Transform3D = op["xf"]
	var glass := _lib_material("MI_GlassClear")
	var frame := _lib_material("MI_PaintedMetal")
	var out := []
	var side := maxf((module - w) / 2.0, 0.0)          # the mullion each side of the opening
	if storey - h > 0.01:                              # header glazing, opening head -> storey top
		out.append({"size": Vector3(module, storey - h, GLASS_T),
				"xf": xf * Transform3D(Basis.IDENTITY, Vector3(0.0, (h + storey) / 2.0, 0.0)), "mat": glass})
	for sgn in [-1.0, 1.0]:
		if side > 0.01:
			out.append({"size": Vector3(side, h, GLASS_T),
					"xf": xf * Transform3D(Basis.IDENTITY, Vector3(sgn * (w + side) / 2.0, h / 2.0, 0.0)),
					"mat": frame})
	# the head rail: what the leaves hang from, and the line a Japanese shopfront reads by
	out.append({"size": Vector3(module, FRAME_T * 2.0, GLASS_T * 1.6),
			"xf": xf * Transform3D(Basis.IDENTITY, Vector3(0.0, h, 0.0)), "mat": frame})
	return out


const KIT_MATERIALS := "res://assets/world_source/kits/quaternius_downtown_city/materials/"

## A hinged door LEAF's material (PLAN.md 3.18l, user: "most doors should be sliding glass; the few hinged ones
## should be white or wood, not grey with aged red"). The kit's own leaf wears the WALL's material, so a door read
## as a panel of the wall. A type says `door_leaf`: "white" (the default -- a Japanese 玄関ドア is white painted
## steel) or "wood".
func _door_material(b := {}) -> Material:
	var want := str(b.get("door_leaf", "white")).to_lower()
	var path := KIT_MATERIALS + ("MI_DoorLeaf_Wood.tres" if want == "wood" else "MI_DoorLeaf_White.tres")
	if _lib_mats.has(path):
		return _lib_mats[path]
	var m: Material = load(path) if ResourceLoader.exists(path) else null
	if m == null:
		var sf := _surfaces(DOOR_LEAF)     # fall back to the kit leaf's own material
		m = null if sf.is_empty() else _kit_material(_kit_res(DOOR_LEAF), sf[0][3])
	_lib_mats[path] = m
	return m

func _door_leaf_mesh() -> ArrayMesh:
	## The kit's own door leaf as one mesh, shared by every Door node (written once).
	if _leaf_mesh != null:
		return _leaf_mesh
	var path := "%s/DoorLeaf_mesh.res" % OUT_DIR
	var tools := {}
	var mats := {}
	var order := []
	for sf in _surfaces(DOOR_LEAF):
		var mat := _kit_material(_kit_res(DOOR_LEAF), sf[3])
		var key := mat.resource_path if mat != null else "<none>"
		if not tools.has(key):
			tools[key] = SurfaceTool.new()
			mats[key] = mat
			order.append(key)
		(tools[key] as SurfaceTool).append_from(sf[0], sf[1], sf[2] as Transform3D)
	var m := ArrayMesh.new()
	for key in order:
		(tools[key] as SurfaceTool).commit(m)
		m.surface_set_material(m.get_surface_count() - 1, mats[key])
	ResourceSaver.save(m, path, ResourceSaver.FLAG_COMPRESS)
	_leaf_mesh = load(path)
	return _leaf_mesh


var _glass_leaves := {}

## One sliding leaf of a Japanese automatic door: a full pane of glass in a slim aluminium frame, built at the
## kit leaf's own convention (it spans the node's local -X and stands on y = 0) so a Door node needs no offset.
func _glass_leaf_mesh(lw: float, h: float) -> ArrayMesh:
	var key := "%.3f_%.3f" % [lw, h]
	if _glass_leaves.has(key):
		return _glass_leaves[key]
	var path := "%s/GlassLeaf_%s_mesh.res" % [OUT_DIR, key.replace(".", "")]
	var pane := SurfaceTool.new()
	var bars := SurfaceTool.new()
	var pm := BoxMesh.new()
	pm.size = Vector3(lw - FRAME_T * 2.0, h - FRAME_T * 2.0, GLASS_T)
	pane.append_from(pm, 0, Transform3D(Basis.IDENTITY, Vector3(-lw / 2.0, h / 2.0, 0.0)))
	for b in [[Vector3(FRAME_T, h, GLASS_T * 1.2), Vector3(-FRAME_T / 2.0, h / 2.0, 0.0)],
			[Vector3(FRAME_T, h, GLASS_T * 1.2), Vector3(-lw + FRAME_T / 2.0, h / 2.0, 0.0)],
			[Vector3(lw, FRAME_T, GLASS_T * 1.2), Vector3(-lw / 2.0, FRAME_T / 2.0, 0.0)],
			[Vector3(lw, FRAME_T, GLASS_T * 1.2), Vector3(-lw / 2.0, h - FRAME_T / 2.0, 0.0)]]:
		var bm := BoxMesh.new()
		bm.size = b[0]
		bars.append_from(bm, 0, Transform3D(Basis.IDENTITY, b[1]))
	var m := ArrayMesh.new()
	pane.commit(m)
	m.surface_set_material(m.get_surface_count() - 1, _lib_material("MI_GlassClear"))
	bars.commit(m)
	m.surface_set_material(m.get_surface_count() - 1, _lib_material("MI_PaintedMetal"))
	ResourceSaver.save(m, path, ResourceSaver.FLAG_COMPRESS)
	_glass_leaves[key] = load(path)
	return _glass_leaves[key]


func _kit_res(piece_path: String) -> String:
	# res://assets/world_source/kits/<kit>/pieces/<cat>/<name>.gltf -> res://assets/world_source/kits/<kit>
	return piece_path.get_base_dir().get_base_dir().get_base_dir()


func _surfaces(path: String) -> Array:
	if _piece_cache.has(path):
		return _piece_cache[path]
	var ps: PackedScene = load(path)
	if ps == null:
		push_error("cannot load piece " + path)
		return []
	var root := ps.instantiate()
	var found := []
	_collect(root, Transform3D.IDENTITY, found)
	root.free()
	_piece_cache[path] = found
	return found


func _collect(n: Node, xf: Transform3D, found: Array) -> void:
	var here := xf
	if n is Node3D:
		here = xf * (n as Node3D).transform
	if n is MeshInstance3D and (n as MeshInstance3D).mesh != null:
		var mi := n as MeshInstance3D
		for s in mi.mesh.get_surface_count():
			var mat: Material = mi.get_surface_override_material(s)
			if mat == null:
				mat = mi.mesh.surface_get_material(s)
			found.append([mi.mesh, s, here, mat])
	for c in n.get_children():
		_collect(c, here, found)


func _kit_material(kit_res: String, mat: Material) -> Material:
	if mat == null:
		return null
	var name := mat.resource_name
	if name.is_empty():
		push_error("a piece surface has an unnamed material")
		return mat
	var key := kit_res + "/" + name
	if _materials.has(key):
		return _materials[key]
	var dir := kit_res + "/materials"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(dir))
	var path := dir + "/" + name + ".tres"
	if not ResourceLoader.exists(path):
		var copy := mat.duplicate()
		copy.resource_name = name
		# The kit's COLOR_0 is a wear/tint MASK for the Source version's shader, not a colour. The glTF importer
		# multiplies it into albedo, which turned MetalConcrete near-black and splashed red over the examples.
		if copy is BaseMaterial3D:
			(copy as BaseMaterial3D).vertex_color_use_as_albedo = false
		var err := ResourceSaver.save(copy, path)
		if err != OK:
			push_error("cannot save %s (%d)" % [path, err])
			return mat
		print("  material %s written" % path)
	var loaded: Material = load(path)
	_materials[key] = loaded
	return loaded


func _build(b: Dictionary, variant: String) -> bool:
	var id: String = b["id"]
	var out_id: String = id + variant
	var open_variant := variant != ""
	var shop := variant == SHOP_VARIANT_SUFFIX
	var tools := {}          # material key -> SurfaceTool
	var mats := {}           # material key -> Material
	var order := []
	var pieces: Array = b["pieces"].duplicate()
	var leaves := []         # Transform3D of each closed door leaf
	if not open_variant:
		# EVERY building is shut: the kit's own leaf where there is a door frame, a plain leaf of the declared size
		# where the doorway is modelled into a library piece. The leaf's pivot edge is its local x = 0 and it spans
		# -0.91..0, so a kit leaf is placed half a leaf along the frame's +X and in the middle of the frame's depth.
		for op in _openings(b):
			var oxf: Transform3D = op["xf"]
			if op["frame"]:
				var lxf := oxf * Transform3D(Basis.IDENTITY, Vector3(0.455, 0.0, -0.09))
				leaves.append({"xf": lxf, "w": 0.91, "h": 2.0})
				pieces.append({"piece": "Door_1", "path": DOOR_LEAF,
						"pos": [lxf.origin.x, lxf.origin.y, lxf.origin.z], "yaw": rad_to_deg(oxf.basis.get_euler().y)})
			elif _panels(b, op) == 2:
				# shut, the two leaves meet in the middle: each spans its own half, from its outer edge inward
				var lw := float(op["w"]) / 2.0
				for li in range(2):
					leaves.append({"xf": oxf * Transform3D(Basis.IDENTITY, Vector3(float(op["w"]) / 2.0 - lw * li, 0.0, 0.0)),
							"w": lw, "lw": lw, "h": float(op["h"]), "glass": true,
							"c": Vector3(-lw / 2.0, float(op["h"]) / 2.0, 0.0)})
			else:
				leaves.append({"xf": oxf * Transform3D(Basis.IDENTITY, Vector3(0.0, float(op["h"]) / 2.0, 0.0)),
						"w": float(op["w"]), "h": float(op["h"]), "plain": true})
	var shop_rows := _shopfront_rows(b)
	var see_through: bool = bool(b.get("has_interior", false))
	var band_panels := []       # [transform, glass AABB] of every shopfront panel that gets the strip
	for p in pieces:
		var path: String = p["path"]
		var kit_res := _kit_res(path)
		var pos: Array = p["pos"]
		var xf := Transform3D(Basis(Vector3.UP, deg_to_rad(float(p["yaw"]))), Vector3(pos[0], pos[1], pos[2]))
		var surfs := _surfaces(path)
		if surfs.is_empty():
			return false
		var shop_window := see_through and shop_rows.has(str(p.get("row", "")))
		var glass := AABB()
		var has_glass := false
		for s in surfs:
			var mat := _kit_material(kit_res, s[3])
			var mname := mat.resource_name if mat != null else ""
			if shop_window and mname == FAKE_INTERIOR:
				continue                     # the card behind the pane: there is a real room behind it
			if shop_window and mname == "MI_Glass":
				var gb := _surface_aabb(s)
				glass = gb if not has_glass else glass.merge(gb)
				has_glass = true
				mat = _kit_named(SHOP_GLASS)
			var key := mat.resource_path if mat != null else "<none>"
			if not tools.has(key):
				var st := SurfaceTool.new()
				tools[key] = st
				mats[key] = mat
				order.append(key)
			(tools[key] as SurfaceTool).append_from(s[0], s[1], xf * (s[2] as Transform3D))
		if shop_window and has_glass:
			band_panels.append([xf, glass])
	# the fixed shopfront glazing is not a door: it is in BOTH variants, shut and open
	var extra := []
	for op in _openings(b):
		if op.has("shopfront"):
			extra += _shopfront_glazing(op)
	for lf in leaves:
		if lf.get("glass", false):
			var gm := _glass_leaf_mesh(float(lf["lw"]), float(lf["h"]))
			for si in gm.get_surface_count():
				var gmat := gm.surface_get_material(si)
				var gkey: String = gmat.resource_path if gmat != null else "<none>"
				if not tools.has(gkey):
					tools[gkey] = SurfaceTool.new()
					mats[gkey] = gmat
					order.append(gkey)
				(tools[gkey] as SurfaceTool).append_from(gm, si, lf["xf"])
	for g in extra:
		var gmat2: Material = g["mat"]
		var gkey2: String = gmat2.resource_path if gmat2 != null else "<none>"
		if not tools.has(gkey2):
			tools[gkey2] = SurfaceTool.new()
			mats[gkey2] = gmat2
			order.append(gkey2)
		var gbox := BoxMesh.new()
		gbox.size = g["size"]
		(tools[gkey2] as SurfaceTool).append_from(gbox, 0, g["xf"])
	for lf in leaves:
		if not lf.get("plain", false):
			continue
		# a plain leaf: a box of the declared opening, in the kit's door material
		var pm := BoxMesh.new()
		pm.size = Vector3(float(lf["w"]), float(lf["h"]), 0.1)
		var pmat := _door_material()
		var pkey: String = pmat.resource_path if pmat != null else "<none>"
		if not tools.has(pkey):
			tools[pkey] = SurfaceTool.new()
			mats[pkey] = pmat
			order.append(pkey)
		(tools[pkey] as SurfaceTool).append_from(pm, 0, lf["xf"])
	for bp in band_panels:
		for box in _shop_band_boxes(bp[0], bp[1], str(b.get("shop_band", ""))):
			var bmat: Material = box["mat"]
			var bkey: String = bmat.resource_path if bmat != null else "<none>"
			if not tools.has(bkey):
				tools[bkey] = SurfaceTool.new()
				mats[bkey] = bmat
				order.append(bkey)
			var bm := BoxMesh.new()
			bm.size = box["size"]
			(tools[bkey] as SurfaceTool).append_from(bm, 0, box["xf"])

	# Indexed and LOD'd (PLAN.md 3.6, `probe_city_perf.gd`): a streamed city put 10-30 M triangles in view at street
	# level with the full meshes, most of them in buildings a few pixels tall. `generate_lods` (meshoptimizer) makes
	# the chain the renderer picks from by screen-space error, so a near building is drawn exactly as built.
	var im := ImporterMesh.new()
	for key in order:
		var st: SurfaceTool = tools[key]
		st.index()
		# a kit piece may carry custom vertex channels (the Standard kit's wear data): their format rides in the flags
		var flags := 0
		for c in 4:
			var cf := st.get_custom_format(c)
			if cf != SurfaceTool.CUSTOM_MAX:
				flags |= int(cf) << (Mesh.ARRAY_FORMAT_CUSTOM_BASE + c * Mesh.ARRAY_FORMAT_CUSTOM_BITS)
		im.add_surface(Mesh.PRIMITIVE_TRIANGLES, st.commit_to_arrays(), [], {}, mats[key],
				(mats[key] as Material).resource_name if mats[key] else "none", flags)
	im.generate_lods(LOD_NORMAL_MERGE_DEG, LOD_NORMAL_SPLIT_DEG, [])
	var mesh: ArrayMesh = im.get_mesh()
	var mesh_path := "%s/%s_mesh.res" % [OUT_DIR, id + (OPEN_VARIANT_SUFFIX if open_variant else "")]
	if ResourceSaver.save(mesh, mesh_path, ResourceSaver.FLAG_COMPRESS) != OK:
		push_error("cannot save " + mesh_path)
		return false
	mesh = load(mesh_path)

	var root := Node3D.new()
	root.name = out_id
	var mi := MeshInstance3D.new()
	mi.name = "Mesh"
	mi.mesh = mesh
	# Past this the building is not drawn: a street-level city needs no 1 km horizon of kit geometry, and a tall
	# building is seen further than a house. Faded (dithered), not popped.
	# R11 (PLAN.md review): NOT a landmark. Tokyo Tower faded out at 900 m while its zone loads at 3 km, so the one
	# thing the skyline is for vanished from the expressway; a landmark is drawn as far as it is streamed.
	if not bool(b.get("landmark", false)):
		mi.visibility_range_end = clampf(VIS_BASE_M + VIS_PER_HEIGHT * mesh.get_aabb().end.y, VIS_MIN_M, VIS_MAX_M)
		mi.visibility_range_end_margin = VIS_FADE_M
		mi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
	root.add_child(mi)
	mi.owner = root
	if OCCLUDER_TYPES.has(id):
		# The streamed city draws every building behind the frontage row without occlusion culling (probe_city_perf.gd:
		# ~2000 in the tree, ~10 M triangles in view at street level). A solid building's box, shrunk inside its own
		# walls so it never hides itself, lets the renderer skip what stands behind it. Glass-fronted and hollow types
		# (konbini, restaurant, stations, landmarks with halls) get none: a character inside must stay visible.
		var bb := mesh.get_aabb()
		var top := float(b.get("roofline_m", b.get("wall_top_m", bb.end.y)))
		var occ := OccluderInstance3D.new()
		occ.name = "Occluder"
		var box := BoxOccluder3D.new()
		box.size = Vector3(maxf(bb.size.x - 2.0 * OCCLUDER_INSET, 0.5), maxf(top - OCCLUDER_FLOOR, 0.5),
				maxf(bb.size.z - 2.0 * OCCLUDER_INSET, 0.5))
		occ.occluder = box
		occ.position = Vector3(bb.get_center().x, OCCLUDER_FLOOR + box.size.y / 2.0, bb.get_center().z)
		root.add_child(occ)
		occ.owner = root

	var body := StaticBody3D.new()
	body.name = "Collision"
	body.collision_layer = 1
	body.collision_mask = 0
	root.add_child(body)
	body.owner = root
	var k := 0
	for lf in leaves:
		var dcs := CollisionShape3D.new()
		dcs.name = "DoorLeaf%d" % k
		k += 1
		var dshape := BoxShape3D.new()
		dshape.size = Vector3(float(lf["w"]) + (LEAF_MEET * 2.0 if lf.get("glass", false) else 0.0),
				float(lf["h"]), 0.14)
		dcs.shape = dshape
		var coff: Vector3 = lf.get("c", Vector3.ZERO if lf.get("plain", false) else Vector3(-0.455, 1.0, 0.0))
		dcs.transform = (lf["xf"] as Transform3D) * Transform3D(Basis.IDENTITY, coff)
		body.add_child(dcs)
		dcs.owner = root
	for bx in b["boxes"]:
		var cs := CollisionShape3D.new()
		cs.name = "Box%d" % k
		k += 1
		var shape := BoxShape3D.new()
		shape.size = Vector3(bx["size"][0], bx["size"][1], bx["size"][2])
		cs.shape = shape
		cs.position = Vector3(bx["center"][0], bx["center"][1], bx["center"][2])
		body.add_child(cs)
		cs.owner = root
	var hi := 0
	for h in b.get("hulls", []):
		# a convex hull of a library piece (a ramp): its own mesh, placed as the layout says
		var hpos: Array = h["pos"]
		var hxf := Transform3D(Basis(Vector3.UP, deg_to_rad(float(h["yaw"]))), Vector3(hpos[0], hpos[1], hpos[2]))
		var pts := PackedVector3Array()
		for s in _surfaces(h["path"]):
			var arr := (s[0] as Mesh).surface_get_arrays(s[1])
			for v in arr[Mesh.ARRAY_VERTEX]:
				pts.append(hxf * ((s[2] as Transform3D) * v))
		var hull := ConvexPolygonShape3D.new()
		hull.points = pts
		var hs := CollisionShape3D.new()
		hs.name = "Hull%d" % hi
		hi += 1
		hs.shape = hull
		body.add_child(hs)
		hs.owner = root
	if b.get("collision", "") == "trimesh":
		# the collider is the building's own shell (the first `trimesh_pieces` placed pieces), never its cladding or
		# furniture: a clad facade is ~100k visual vertices a physics server has no business testing
		var n_col := int(b.get("trimesh_pieces", b["pieces"].size()))
		var tri: Shape3D
		if n_col >= b["pieces"].size():
			tri = mesh.create_trimesh_shape()
		else:
			var faces := PackedVector3Array()
			for pi in n_col:
				var pp: Dictionary = b["pieces"][pi]
				var ppos: Array = pp["pos"]
				var pxf := Transform3D(Basis(Vector3.UP, deg_to_rad(float(pp["yaw"]))), Vector3(ppos[0], ppos[1], ppos[2]))
				for sf in _surfaces(pp["path"]):
					var fx: Transform3D = pxf * (sf[2] as Transform3D)
					var st2 := SurfaceTool.new()
					st2.append_from(sf[0], sf[1], fx)
					var m2 := st2.commit()
					for v in m2.get_faces():
						faces.append(v)
			var cps := ConcavePolygonShape3D.new()
			cps.set_faces(faces)
			tri = cps
		var shape_path := "%s/%s_collision.res" % [OUT_DIR, id + (OPEN_VARIANT_SUFFIX if open_variant else "")]
		ResourceSaver.save(tri, shape_path, ResourceSaver.FLAG_COMPRESS)
		var cs := CollisionShape3D.new()
		cs.name = "Trimesh"
		cs.shape = load(shape_path)
		body.add_child(cs)
		cs.owner = root

	if open_variant:
		# one `world.Door` per frame: the node sits at the HINGE edge (the leaf spans its local -X), MANUAL (the
		# player presses interact) and LOCKED, so only a mission's unlock lets anyone in.
		var doors_root := Node3D.new()
		doors_root.name = "Doors"
		root.add_child(doors_root)
		doors_root.owner = root
		# SLIDING or hinged is the TYPE's own fact, carried here by the layout (user, 2026-09-19: a Japanese
		# store, office, terminal or konbini has a 自動ドア, not a swing door). A slide wide enough for two
		# leaves gets two, parting from the middle, which is what an automatic entrance looks like; a narrow
		# one gets a single 片引き戸. Each leaf is its own `world.Door` with its own sensor, so nothing new was
		# needed in the Door class -- `open_mode = "SLIDE"` and `slide_offset` have been there since I2.
		var dn := 0
		# ...and the INTERIOR doors (a staff room, a toilet): a hinged leaf in a `Wall_PartitionDoor`'s hole, which
		# the layout records from a prop's `door` entry (user, 2026-09-26: only the street entrance slides)
		var ops := _openings(b)
		for idr in b.get("inner_doors", []):
			var io := Vector3(idr["outward"][0], 0.0, idr["outward"][2])
			ops.append({"xf": Transform3D(Basis(Vector3.UP, atan2(io.x, io.z)),
					Vector3(idr["center"][0], idr["center"][1], idr["center"][2])),
					"w": float(idr["width"]), "h": float(idr["height"]), "frame": false, "style": "swing",
					"inner": true})
		for op in ops:
			# per OPENING: a SITE holds parts of different types, so its kiosk's 自動ドア and a back gate's
			# swing door stand on one footprint (user-reported, PLAN.md 3.18f)
			var slide := str(op.get("style", b.get("door_style", "swing"))) == "slide"
			var oxf: Transform3D = op["xf"]
			var w := float(op["w"])
			var h := float(op["h"])
			var panels := _panels(b, op)
			for li in range(panels):
				var lw := w / float(panels)
				# hinged: the node is the HINGE edge and the leaf hangs along its local -X.
				# sliding: the node is the leaf's own outer edge, and it slides OUTWARD along the wall by lw.
				var edge := w / 2.0 if not slide else (w / 2.0 - lw * li)
				var door := StaticBody3D.new()
				door.set_script(load(DOOR_SCRIPT))
				door.name = "Door%d" % dn
				dn += 1
				door.transform = oxf * Transform3D(Basis.IDENTITY,
						Vector3(edge, 0.0, -0.09 if op["frame"] else 0.0))
				door.collision_layer = 1
				door.collision_mask = 0
				doors_root.add_child(door)
				door.owner = root
				var leaf := MeshInstance3D.new()
				leaf.name = "IntactVisual"
				if slide:
					# full glass in a slim frame, the Japanese shop entrance; it already spans local -X from 0
					leaf.mesh = _glass_leaf_mesh(lw, h)
				elif op["frame"] and panels == 1:
					leaf.mesh = _door_leaf_mesh()
					leaf.material_override = _door_material(b)
				else:
					var lm := BoxMesh.new()
					lm.size = Vector3(lw, h, 0.1)
					leaf.mesh = lm
					leaf.material_override = _door_material(b)
					leaf.position = Vector3(-lw / 2.0, h / 2.0, 0.0)
				door.add_child(leaf)
				leaf.owner = root
				var lcs := CollisionShape3D.new()
				lcs.name = "CollisionShape3D"
				var lshape := BoxShape3D.new()
				lshape.size = Vector3(lw + (LEAF_MEET * 2.0 if panels > 1 else 0.0), h, 0.14)
				lcs.shape = lshape
				lcs.position = Vector3(-lw / 2.0, h / 2.0, 0.0)
				door.add_child(lcs)
				lcs.owner = root
				var sensor := Area3D.new()
				sensor.name = "Sensor"
				sensor.collision_layer = 0
				sensor.collision_mask = 2          # CollisionLayers.CHARACTER
				var scs := CollisionShape3D.new()
				scs.name = "CollisionShape3D"
				var sbox := BoxShape3D.new()
				sbox.size = Vector3(w + 1.4, h + 0.2, 2.4)
				scs.shape = sbox
				# the sensor covers the WHOLE doorway whichever leaf this is, so both leaves open together
				scs.position = Vector3((w / 2.0) - edge - (w / 2.0), h / 2.0, 0.0)
				sensor.add_child(scs)
				door.add_child(sensor)
				sensor.owner = root
				scs.owner = root
				if slide:
					door.set("open_mode", "SLIDE")
					# slide_offset is in the door's PARENT frame (Door adds it to its own position), so the
					# direction is the opening's own +X, away from the middle
					var dir := oxf.basis.x.normalized() * (lw if li == 0 else -lw)
					door.set("slide_offset", dir)
				var inner := bool(op.get("inner", false))
				# a shop's door is automatic; a mission's is MANUAL (press interact); an interior door opens as you
				# walk up and is never locked (once you are in, the rooms are yours)
				door.set("auto_open", shop or inner)
				door.set("locked", not shop and not inner)
				door.set("breakable", false)
				door.set("sensor_path", NodePath("Sensor"))
	var di := 0
	for d in b["doors"]:
		var mk := Marker3D.new()
		mk.name = "Door_%s_%d" % [d["side"], d["module"]]
		var out := Vector3(d["outward"][0], d["outward"][1], d["outward"][2])
		# -Z of the marker points OUT of the building (the way a player leaving it walks)
		mk.transform = Transform3D(Basis.looking_at(out, Vector3.UP), Vector3(d["center"][0], d["center"][1], d["center"][2]))
		root.add_child(mk)
		mk.owner = root
		di += 1

	var meta := b.duplicate(true)
	meta.erase("pieces")
	meta.erase("boxes")
	meta.erase("hulls")
	meta["piece_count"] = b["pieces"].size()
	meta["doors_closed"] = not open_variant
	meta["doors_locked"] = open_variant and not shop
	meta["doors_shop"] = shop
	meta["aabb"] = [mesh.get_aabb().position, mesh.get_aabb().size]
	# which merged surface each facade family is, for the per-building tone override (PLAN.md 3.18p). An empty
	# map is a legitimate answer (a landmark built of library pieces wears neither), not a failure.
	meta["facade_surfaces"] = _facade_surfaces(order, mats)
	root.set_meta("building", meta)

	var packed := PackedScene.new()
	if packed.pack(root) != OK:
		push_error("cannot pack " + out_id)
		root.free()
		return false
	var scene_path := "%s/%s.tscn" % [OUT_DIR, out_id]
	var err := ResourceSaver.save(packed, scene_path)
	root.free()
	var aabb := mesh.get_aabb()
	print("%-18s %5d pieces -> %d surfaces, %d verts, aabb %s, %s" % [out_id, b["pieces"].size(), mesh.get_surface_count(),
		_vert_count(mesh), aabb.size, "OK" if err == OK else "SAVE FAILED"])
	return err == OK


## The rows the KIT calls a shop's glazed front. Named there, not here: which rows those are is a fact about
## the kit's own row table.
var _shop_rows_cache := {}
func _shopfront_rows(b: Dictionary) -> Dictionary:
	var kit := str(b.get("kit", ""))
	if _shop_rows_cache.has(kit):
		return _shop_rows_cache[kit]
	var out := {}
	var path := "res://assets/world_source/kits/%s/kit.json" % kit
	if FileAccess.file_exists(path):
		var doc = JSON.parse_string(FileAccess.get_file_as_string(path))
		if typeof(doc) == TYPE_DICTIONARY:
			for r in doc.get("shopfront_rows", []):
				out[str(r)] = true
	_shop_rows_cache[kit] = out
	return out


func _surface_aabb(s: Array) -> AABB:
	var arr := (s[0] as Mesh).surface_get_arrays(s[1])
	var v: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
	var sxf: Transform3D = s[2]
	var lo := Vector3(INF, INF, INF)
	var hi := -lo
	for q in v:
		var w: Vector3 = sxf * q
		lo = lo.min(w)
		hi = hi.max(w)
	return AABB(lo, hi - lo)


## The 目隠しシート across one panel: a white strip at eye height with two livery stripes through it. Its width,
## its plane and its floor all come from the panel's OWN glass, so a narrower or lower pane gets a strip that
## fits it rather than a constant that happens to suit the konbini.
func _shop_band_boxes(xf: Transform3D, glass: AABB, stripe_mat: String) -> Array:
	var w: float = glass.size.x
	if w < 0.2 or glass.end.y < glass.position.y + BAND_HEIGHT:
		return []                            # too small or too short to carry a strip
	var z: float = glass.position.z - BAND_PROUD          # the pane faces the panel's -Z (the street)
	# Measured from the panel's own FLOOR (its local y = 0), never from the pane's bottom edge: on this kit the
	# glass starts 0.47 m up, so adding the offset to it put the strip at 1.72-2.17 m -- over a head rather than
	# across a face, and near the top of the pane rather than its middle. Clamped to stay on the glass.
	var y0: float = clampf(BAND_BOTTOM, glass.position.y, glass.end.y - BAND_HEIGHT)
	var cx: float = glass.position.x + w * 0.5
	var band := _kit_named(BAND_MAT)
	var stripe := _kit_named(stripe_mat if stripe_mat != "" else BAND_DEFAULT_STRIPE)
	var out := []
	out.append({"mat": band, "size": Vector3(w, BAND_HEIGHT, 0.012),
			"xf": xf * Transform3D(Basis.IDENTITY, Vector3(cx, y0 + BAND_HEIGHT * 0.5, z))})
	for k in 2:
		var sy: float = y0 + (BAND_HEIGHT * 0.20 if k == 0 else BAND_HEIGHT * 0.80)
		out.append({"mat": stripe, "size": Vector3(w, BAND_STRIPE_H, 0.016),
				"xf": xf * Transform3D(Basis.IDENTITY, Vector3(cx, sy, z))})
	return out


func _kit_named(name: String) -> Material:
	return load(KIT_MATERIALS + name + ".tres")


## {facade material name: merged surface index} for the facade families this building wears. `order` is the
## surface order the merge emitted, so this cannot drift from what `surface_material_override/<i>` addresses.
func _facade_surfaces(order: Array, mats: Dictionary) -> Dictionary:
	var out := {}
	var want := _facade_names()
	for i in order.size():
		var m: Material = mats[order[i]]
		if m != null and want.has(m.resource_name) and not out.has(m.resource_name):
			out[m.resource_name] = i
	return out


var _facade_cache: PackedStringArray
var _facade_read := false
func _facade_names() -> PackedStringArray:
	if _facade_read:
		return _facade_cache
	_facade_read = true
	if not FileAccess.file_exists(FACADE_TONES_JSON):
		push_warning("no %s: buildings get no per-building facade tone" % FACADE_TONES_JSON)
		return _facade_cache
	var doc = JSON.parse_string(FileAccess.get_file_as_string(FACADE_TONES_JSON))
	if typeof(doc) == TYPE_DICTIONARY:
		for k in (doc.get("facades", {}) as Dictionary).keys():
			_facade_cache.append(str(k))
	return _facade_cache


func _vert_count(mesh: ArrayMesh) -> int:
	var n := 0
	for s in mesh.get_surface_count():
		n += (mesh.surface_get_arrays(s)[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
	return n
