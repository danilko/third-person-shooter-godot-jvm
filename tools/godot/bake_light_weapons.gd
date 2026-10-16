extends SceneTree
## Bake every catalog weapon into ONE flat-coloured mesh for the light combatant tier (PLAN.md 2.3,
## ai.light.LightCombatants, assets/characters/crowd/light_weapon.gdshader).
##
##   godot --headless --path . --script tools/godot/bake_light_weapons.gd
##
## WHY. A light combatant is a MultiMesh instance; its weapon is one more instance riding the baked right hand. A
## weapon scene is several MeshInstance3D parts with several materials, which would be a draw call per part per
## body type -- at the 15 m+ this tier is drawn a rifle is 10-20 px long, so each part's material becomes its MEAN
## COLOUR in the vertex colour, and the whole weapon is one surface.
##
## WHAT. The mesh is in the weapon ROOT's frame, which is the grip (the weapon standard puts the model origin on the
## grip: WeaponItem.gripPoint), so the runtime only has to put it on the body's socket and in the hand.
##   assets/characters/crowd/weapons/<ID>.res   ArrayMesh, one surface: position, normal, colour
##   assets/characters/crowd/light_weapons.json id -> {mesh, socket, ranged, archetype}
## Fists, throwables and dual pistols get no row (the tier draws empty hands for them).

const CATALOG := "res://src/main/resources/com/openworld/weapon/weapon_catalog.json"
const OUT_DIR := "res://assets/characters/crowd/weapons/"
const OUT_JSON := "res://assets/characters/crowd/light_weapons.json"
const SOCKET := {"rifle": "SocketRifle", "shotgun": "SocketShotgun", "pistol": "SocketPistol",
	"launcher": "SocketLauncher", "melee": "SocketMelee"}
const RANGED := ["rifle", "shotgun", "pistol", "launcher"]

var _fail := 0

func _initialize() -> void:
	var cat: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(CATALOG))
	DirAccess.make_dir_recursive_absolute(OUT_DIR)
	var table := {}
	for row in cat["weapons"]:
		var id := String(row["id"])
		var arch := String(row["archetype"])
		if not SOCKET.has(arch):
			continue
		var ps := load(String(row["scene"])) as PackedScene
		if ps == null:
			print("[lw] FAIL: %s has no scene" % id)
			_fail += 1
			continue
		var w: Node = ps.instantiate()
		var hs = w.get("hold_socket")
		var socket := String(hs) if hs != null and String(hs) != "" else String(SOCKET[arch])
		var mesh := _merge(w)
		w.free()
		if mesh == null:
			print("[lw] FAIL: %s has no visible mesh" % id)
			_fail += 1
			continue
		var path := OUT_DIR + id + ".res"
		if ResourceSaver.save(mesh, path, ResourceSaver.FLAG_COMPRESS) != OK:
			_fail += 1
			continue
		table[id] = {"mesh": path, "socket": socket, "ranged": RANGED.has(arch), "archetype": arch}
		print("[lw] %-5s %-9s %-14s %5d vertices  aabb %s" % [id, arch, socket,
			(mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX] as PackedVector3Array).size(), mesh.get_aabb().size])
	var fh := FileAccess.open(OUT_JSON, FileAccess.WRITE)
	fh.store_string(JSON.stringify({"generated_by": "tools/godot/bake_light_weapons.gd", "weapons": table}, "  ", true) + "\n")
	fh.close()
	print("[lw] %d weapons -> %s  %s" % [table.size(), OUT_JSON, "PASS" if _fail == 0 else "FAIL (%d)" % _fail])
	quit(_fail)

## Every visible MeshInstance3D of the weapon's Model, in the weapon root's frame, as one surface coloured per part.
func _merge(w: Node) -> ArrayMesh:
	var pos := PackedVector3Array()
	var nrm := PackedVector3Array()
	var col := PackedColorArray()
	var idx := PackedInt32Array()
	# the weapon's MODEL only: a scene also carries effect meshes (the muzzle's glow sphere is visible and 0.3 m wide)
	var model: Node = w.get_node_or_null("Model")
	for m in (model if model != null else w).find_children("*", "MeshInstance3D", true, false):
		var mi := m as MeshInstance3D
		if mi.mesh == null or not _visible(mi, w):
			continue
		var where := String(w.get_path_to(mi))
		if where.contains("Muzzle") or where.contains("VFX") or where.contains("Flash"):
			continue
		var xf := _rel(mi, w)
		var nb := xf.basis.inverse().transposed()
		for si in mi.mesh.get_surface_count():
			var arr := mi.mesh.surface_get_arrays(si)
			var v: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
			var n = arr[Mesh.ARRAY_NORMAL]
			var ix = arr[Mesh.ARRAY_INDEX]
			var c := _colour(mi, si)
			var base := pos.size()
			for i in v.size():
				pos.append(xf * v[i])
				nrm.append((nb * (n[i] if n != null and i < n.size() else Vector3.UP)).normalized())
				col.append(c)
			if ix != null and (ix as PackedInt32Array).size() > 0:
				for i in ix: idx.append(base + i)
			else:
				for i in v.size(): idx.append(base + i)
	if pos.is_empty():
		return null
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = pos
	arrays[Mesh.ARRAY_NORMAL] = nrm
	arrays[Mesh.ARRAY_COLOR] = col
	arrays[Mesh.ARRAY_INDEX] = idx
	var am := ArrayMesh.new()
	am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return am

## A part's colour: its material's albedo colour times the MEAN of its albedo texture (sRGB, as authored).
func _colour(mi: MeshInstance3D, si: int) -> Color:
	var mat := mi.get_surface_override_material(si)
	if mat == null: mat = mi.mesh.surface_get_material(si)
	if mat == null and mi.material_override != null: mat = mi.material_override
	var c := Color(0.25, 0.25, 0.27)
	if mat is BaseMaterial3D:
		var b := mat as BaseMaterial3D
		c = b.albedo_color
		var t := b.albedo_texture
		if t != null:
			var img := t.get_image()
			if img != null:
				if img.is_compressed(): img.decompress()
				img.resize(4, 4, Image.INTERPOLATE_BILINEAR)
				var acc := Color(0, 0, 0)
				for y in 4:
					for x in 4: acc += img.get_pixel(x, y)
				acc /= 16.0
				c = Color(c.r * acc.r, c.g * acc.g, c.b * acc.b)
	return Color(c.r, c.g, c.b, 1.0)

func _visible(n: Node, top: Node) -> bool:
	var p: Node = n
	while p != null and p != top:
		if p is Node3D and not (p as Node3D).visible: return false
		p = p.get_parent()
	return true

func _rel(node: Node3D, ancestor: Node) -> Transform3D:
	var t := Transform3D()
	var n: Node = node
	while n != null and n != ancestor:
		if n is Node3D: t = (n as Node3D).transform * t
		n = n.get_parent()
	return t
