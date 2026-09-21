extends SceneTree
## probe_buildings.gd -- gate for the generated building scenes (tools/building_kit/, world/buildings/).
##
##   godot --headless --path . --script tools/godot/probe_buildings.gd [-- --only=Id,Id]
##
## Every scene whose root carries `building` meta (written by build_building_scenes.gd) is instanced and asked:
##   size      the merged mesh is the declared footprint (within the cornice/column overhang, 0.6 m) and height;
##   materials every surface has a material, and it is the kit's shared `.tres`, not an import-embedded copy;
##   roof      a ray from above lands on the roof slab at the wall top;
##   floor     a ray down inside the ground storey lands on the ground slab;
##   door      every shipped building is SHUT (user, 2026-09-19): the capsule and a ray are blocked at each doorway.
##             Its `<Id>_Open` variant (what a mission places) has a `world.Door` per doorway, LOCKED -- also blocked
##             -- and once unlocked and opened the capsule fits through; its `<Id>_Shop` variant (a shop, or the
##             player's home base) is the same but UNLOCKED with automatic doors;
##   wall      the SAME capsule and ray at a solid module of that side are blocked (the paired control: a
##             collider that never blocked anything passes every door check).
## A kit example (trimesh, no doors) is asked size, materials and roof only.

const DIR := "res://src/main/resources/com/openworld/world/buildings"
const CAPSULE_R := 0.35
const CAPSULE_H := 1.75
const PLAN_TOL := 0.6
const HEIGHT_TOL := 0.2

var _fails := 0
var _passes := 0


## The style of the doorway nearest a Door node, from the layout's own per-door fact.
func _door_style(meta: Dictionary, at: Vector3) -> String:
	var best := ""
	var bd := 6.0
	for d in meta.get("doors", []):
		var c := Vector3(d["center"][0], at.y, d["center"][2])
		var dist := c.distance_to(Vector3(at.x, at.y, at.z))
		if dist < bd:
			bd = dist
			best = str(d.get("style", meta.get("door_style", "swing")))
	return best if best != "" else str(meta.get("door_style", "swing"))


func _check(ok: bool, msg: String) -> void:
	if ok:
		_passes += 1
	else:
		_fails += 1
	print(("PASS " if ok else "FAIL ") + msg)


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var only := []
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--only="):
			only = a.substr(7).split(",")
	var ids := []
	for f in DirAccess.get_files_at(DIR):
		if f.ends_with(".tscn"):
			var id := f.get_basename()
			if only.is_empty() or only.has(id):
				ids.append(id)
	var x := 0.0
	var probed := 0
	for id in ids:
		var ps: PackedScene = load("%s/%s.tscn" % [DIR, id])
		var inst: Node3D = ps.instantiate()
		if not inst.has_meta("building"):
			inst.free()
			continue
		probed += 1
		inst.position = Vector3(x, 0, 0)
		root.add_child(inst)
		var meta: Dictionary = inst.get_meta("building")
		x += 120.0
		for i in 3:
			await physics_frame
		await _probe(id, inst, meta)
		inst.queue_free()
		await physics_frame
	_check(probed >= 10, "%d building scenes probed" % probed)
	if only.is_empty():
		_probe_cell_tones()
	print("RESULT %s (%d passed, %d failed)" % ["PASS" if _fails == 0 else "FAIL", _passes, _fails])
	quit(1 if _fails else 0)


func _probe(id: String, inst: Node3D, meta: Dictionary) -> void:
	var mi: MeshInstance3D = inst.get_node("Mesh")
	var aabb := mi.mesh.get_aabb()
	var fp: Array = meta["footprint_m"]
	var example: bool = meta.get("example", false)
	var tol := 0.01 if example else PLAN_TOL
	_check(absf(aabb.size.x - fp[0]) <= tol and absf(aabb.size.z - fp[1]) <= tol
		and absf(aabb.size.y - float(meta["height_m"])) <= HEIGHT_TOL,
		"%s size %.2f x %.2f x %.2f m (declared %.2f x %.2f, height %.2f)" % [id, aabb.size.x, aabb.size.z, aabb.size.y,
		fp[0], fp[1], meta["height_m"]])
	var bad := []
	for s in mi.mesh.get_surface_count():
		var m := mi.mesh.surface_get_material(s)
		if m == null or not m.resource_path.contains("/materials/MI_"):
			bad.append(s)
	_check(bad.is_empty(), "%s %d surfaces, all on kit materials %s" % [id, mi.mesh.get_surface_count(), bad])

	# PLAN.md 3.18o follow-up, user 2026-09-21: a Japanese shop window is CLEAR GLASS with a privacy strip
	# across the middle, not a panel you cannot see through. What hid the shop was the kit's opaque
	# fake-interior card BEHIND the pane, so this asserts both halves of the rule and its control at once: a
	# building with a room has no card and wears the strip; one without keeps its card, because a lit fake
	# interior is exactly what makes an unenterable tower read as occupied.
	var surf_names := {}
	var faked := false
	for s in mi.mesh.get_surface_count():
		var sm := mi.mesh.surface_get_material(s)
		if sm != null:
			surf_names[sm.resource_name] = true
			# the kit ships one card and its numbered variants (MI_FakeInterior, _1.._4)
			faked = faked or sm.resource_name.begins_with("MI_FakeInterior")
	if surf_names.has("MI_GlassShopfront"):
		_check(not faked and surf_names.has("MI_ShopBand"),
			"%s: a shop window is clear (no fake-interior card) and wears the privacy strip" % id)
	elif surf_names.has("MI_Glass"):
		_check(faked and not surf_names.has("MI_ShopBand"),
			"%s: glazing that is not a shop window keeps its lit fake interior and gets no strip" % id)

	var space := inst.get_world_3d().direct_space_state
	var o := inst.global_position
	var top := float(meta["wall_top_m"])
	# a composite site names a clear spot to look at (a canopy, not a pump island); a building its centre
	var pxz: Array = meta.get("probe_xz", [0.3, 0.3])
	var px := float(pxz[0])
	var pz := float(pxz[1])
	var hit := _ray(space, o + Vector3(px, top + 10.0, pz), o + Vector3(px, -1.0, pz))
	if example:
		_check(not hit.is_empty() and hit.position.y > 0.5 * top, "%s roof hit at %s" % [id, hit.get("position")])
		if (meta["doors"] as Array).is_empty():
			return   # a solid kit example; a landmark with hollow halls goes on to its floor and doors
	else:
		_check(not hit.is_empty() and absf(hit.position.y - top) < 0.05, "%s roof at %.2f (wall top %.2f)" % [id,
			hit.position.y if not hit.is_empty() else -1.0, top])
	hit = _ray(space, o + Vector3(px, 1.0, pz), o + Vector3(px, -1.0, pz))
	_check(not hit.is_empty() and absf(hit.position.y) < 0.02, "%s ground slab at %.3f" % [id,
		hit.position.y if not hit.is_empty() else -9.0])

	for q in meta.get("clear_probes", []):
		var at := o + Vector3(float(q[0]), 0.0, float(q[1]))
		_check(not _capsule_hits(space, at), "%s open at (%.1f, %.1f): the capsule fits (a crane's portal)" % [id, q[0], q[1]])
	for d in meta["doors"]:
		var c := o + Vector3(d["center"][0], 0, d["center"][2])
		var out := Vector3(d["outward"][0], 0, d["outward"][2])
		var at := c - out * 0.09
		var blocked := _capsule_hits(space, at)
		var r := _ray(space, c + out * 2.0 + Vector3(0, 1.0, 0), c - out * 1.5 + Vector3(0, 1.0, 0))
		if meta.get("doors_shop", false):
			# a SHOP (or the player's home base): the door is shut but UNLOCKED and automatic -- anyone may walk in
			_check(blocked, "%s door %s/%d is a shop door: shut (%s) but unlocked" % [id, d["side"], d["module"], blocked])
		elif meta.get("doors_locked", false):
			# the `_Open` variant: a real `world.Door`, LOCKED, so it still blocks until a mission unlocks it
			_check(blocked and not r.is_empty(), "%s door %s/%d is LOCKED shut: blocks the capsule (%s), ray (%s)" % [
				id, d["side"], d["module"], blocked, not r.is_empty()])
		elif meta.get("doors_closed", false):
			# every shipped building is shut (user, 2026-09-19): the leaf and its collider stop the character
			_check(blocked and not r.is_empty(), "%s door %s/%d is SHUT: blocks the capsule (%s) and the ray (%s)" % [
				id, d["side"], d["module"], blocked, not r.is_empty()])
		else:
			_check(not blocked and r.is_empty(), "%s door %s/%d: capsule fits (%s), ray walks in (%s), opening %.2f x %.2f m" % [
				id, d["side"], d["module"], not blocked, r.is_empty(), d["width"], d["height"]])
	if meta.get("doors_locked", false) or meta.get("doors_shop", false):
		await _probe_unlock(id, inst, meta)
	for sp in meta["solid_probes"]:
		var c := o + Vector3(sp["center"][0], 0, sp["center"][2])
		var out := Vector3(sp["outward"][0], 0, sp["outward"][2])
		var blocked := _capsule_hits(space, c - out * 0.09)
		var r := _ray(space, c + out * 2.0 + Vector3(0, 1.0, 0), c - out * 1.5 + Vector3(0, 1.0, 0))
		var at_wall := not r.is_empty() and absf((r.position - c).dot(out)) < 0.05
		_check(blocked and at_wall, "%s wall %s/%d blocks the capsule (%s) and the ray at the facade (%s)" % [
			id, sp["side"], sp["module"], blocked, at_wall])


func _probe_unlock(id: String, inst: Node3D, meta: Dictionary) -> void:
	## An `_Open` variant is what a MISSION places: unlocking and opening its doors must let the character in.
	var doors := inst.get_node_or_null("Doors")
	var n := 0 if doors == null else doors.get_child_count()
	_check(n >= (meta["doors"] as Array).size(), "%s has a Door node per doorway (%d for %d doors)" % [
		id, n, (meta["doors"] as Array).size()])
	if doors == null:
		return
	var shop: bool = meta.get("doors_shop", false)
	var want_locked: bool = not shop
	for d in doors.get_children():
		_check(bool(d.get("locked")) == want_locked, "%s %s starts %s" % [id, d.name,
			"LOCKED" if want_locked else "unlocked (a shop)"])
		_check(bool(d.get("auto_open")) == shop, "%s %s is %s" % [id, d.name,
			"AUTOMATIC (a shop door)" if shop else "manual (press interact)"])
		# WHO may open it is the flags above (and `world.Door`'s own sensor rule: only a Character opens a shop
		# door). What the BUILDER owns is that the leaf clears the doorway when it does, so the door is driven
		# directly here: auto off, unlock, open.
		d.set("auto_open", false)
		d.call("set_locked", false)
		d.call("open_door")
	# A shop, office, terminal or konbini has a SLIDING automatic entrance (自動ドア), a house a hinged 玄関ドア
	# (user, 2026-09-19). It is the TYPE's fact, carried by the layout, so it is asserted per building here --
	# and by MOVEMENT, not by the flag: a leaf that reads "SLIDE" and swings is the failure worth catching.
	# Asked per DOOR, not per building: a SITE holds parts of different types, so a gas station's kiosk has the
	# konbini's 自動ドア while another part keeps a swing door (user-reported, PLAN.md 3.18f). Which meta door a
	# leaf belongs to is answered geometrically -- a Door node sits at its doorway's edge, and a leaf that
	# belongs to no meta door (a roof stair house's frame) takes the building's own style.
	var slide_want: bool = str(meta.get("door_style", "swing")) == "slide"
	var want := {}
	for d in doors.get_children():
		want[d.name] = _door_style(meta, d.position)
		var s: bool = want[d.name] == "slide"
		_check((str(d.get("open_mode")) == "SLIDE") == s, "%s %s is a %s door" % [
			id, d.name, "sliding" if s else "hinged"])
	var before := {}
	for d in doors.get_children():
		before[d.name] = [d.position, d.rotation.y]
	for i in 90:
		await physics_frame
	var slid_dirs := []
	for d in doors.get_children():
		var moved: float = (d.position - (before[d.name][0] as Vector3)).length()
		var turned: float = absf(d.rotation.y - float(before[d.name][1]))
		if want[d.name] == "slide":
			_check(moved > 0.3 and turned < 0.05, "%s %s slid %.2f m and turned %.1f deg" % [
				id, d.name, moved, rad_to_deg(turned)])
			slid_dirs.append((d.position - (before[d.name][0] as Vector3)).normalized())
		else:
			_check(turned > 0.5 and moved < 0.05, "%s %s swung %.0f deg and slid %.2f m" % [
				id, d.name, rad_to_deg(turned), moved])
	# A Japanese automatic entrance is TWO leaves parting to OPPOSITE sides, in full glass (user, 2026-09-20).
	# Counted per doorway, because one wide entrance and two separate single doors both give two Door nodes.
	if slide_want and not (meta["doors"] as Array).is_empty():
		# counted GEOMETRICALLY, per doorway: a building can carry Door nodes that belong to no meta door (a roof
		# stair house's frame is shut too), so dividing by the doorway count is not the same question.
		var per_door := 0
		for d in meta["doors"]:
			# measured on the CLOSED positions (`before`): by now the doors are open, and an open leaf has slid
			# a leaf's width clear of its own doorway, which is the point of it
			var dc := Vector2(d["center"][0], d["center"][2])
			var n2 := 0
			for leaf in doors.get_children():
				var cp: Vector3 = before[leaf.name][0]
				if Vector2(cp.x, cp.z).distance_to(dc) <= float(d["width"]) / 2.0 + 0.05:
					n2 += 1
			per_door = maxi(per_door, n2)
			_check(n2 == 2, "%s doorway %s/%d has %d leaves" % [id, d["side"], d["module"], n2])
		if slid_dirs.size() >= 2:
			_check(slid_dirs[0].dot(slid_dirs[1]) < -0.9, "%s: the two leaves part to opposite sides (dot %.2f)"
				% [id, slid_dirs[0].dot(slid_dirs[1])])
		var glassy := 0
		for d in doors.get_children():
			var lm: MeshInstance3D = d.get_node_or_null("IntactVisual")
			if lm != null and lm.mesh != null:
				for si in (lm.mesh as Mesh).get_surface_count():
					var lmat := (lm.mesh as Mesh).surface_get_material(si)
					if lmat != null and str(lmat.resource_path).contains("MI_GlassClear"):
						glassy += 1
						break
		_check(glassy == doors.get_child_count(), "%s: %d of %d leaves are glass" % [
			id, glassy, doors.get_child_count()])

	var space := inst.get_world_3d().direct_space_state
	var o := inst.global_position
	var opened := 0
	for d in meta["doors"]:
		var c := o + Vector3(d["center"][0], 0, d["center"][2])
		var out := Vector3(d["outward"][0], 0, d["outward"][2])
		if not _capsule_hits(space, c - out * 0.09):
			opened += 1
	_check(opened == (meta["doors"] as Array).size(), "%s %s: the capsule fits %d of %d doorways" % [
		id, "opened" if meta.get("doors_shop", false) else "unlocked and opened", opened,
		(meta["doors"] as Array).size()])


func _ray(space: PhysicsDirectSpaceState3D, a: Vector3, b: Vector3) -> Dictionary:
	var q := PhysicsRayQueryParameters3D.create(a, b, 1)
	return space.intersect_ray(q)


func _capsule_hits(space: PhysicsDirectSpaceState3D, foot: Vector3) -> bool:
	var shape := CapsuleShape3D.new()
	shape.radius = CAPSULE_R
	shape.height = CAPSULE_H
	var q := PhysicsShapeQueryParameters3D.new()
	q.shape = shape
	q.collision_mask = 1
	# the capsule stands 2 cm off the floor, as a character on the ground does
	q.transform = Transform3D(Basis.IDENTITY, foot + Vector3(0, CAPSULE_H / 2.0 + 0.02, 0))
	return not space.intersect_shape(q, 4).is_empty()

const CELLS := "res://src/main/resources/com/openworld/world/buildings/cells"
const TONES_JSON := "res://assets/world_source/kits/quaternius_downtown_city/materials/facade_tones.json"

## PLAN.md 3.18p, and it is the half a text check cannot make: LOAD every streamed cell and read the facade tone
## overrides back off the live MeshInstance3D. A `.tscn` whose override syntax Godot silently drops reads exactly
## like a city that was never given a mixture, and `island_buildings.py tones` -- which reads the same text --
## would pass on it. Skipped where there are no cells, so a kit-only build still runs.
func _probe_cell_tones() -> void:
	if not DirAccess.dir_exists_absolute(ProjectSettings.globalize_path(CELLS)):
		return
	if not FileAccess.file_exists(TONES_JSON):
		return
	var doc = JSON.parse_string(FileAccess.get_file_as_string(TONES_JSON))
	var fams: Dictionary = doc.get("facades", {})
	var owner_of := {}            # tone material name -> its family
	for fam in fams:
		for n in fams[fam]:
			owner_of[n] = fam
	var meshes := 0
	var overrides := 0
	var worn := {}
	var bad := []
	for f in DirAccess.get_files_at(CELLS):
		if not f.ends_with(".tscn"):
			continue
		var ps: PackedScene = load("%s/%s" % [CELLS, f])
		if ps == null:
			bad.append("%s does not load" % f)
			continue
		var cell: Node = ps.instantiate()
		for c in cell.get_children():
			var mi := c.get_node_or_null("Mesh") as MeshInstance3D
			if mi == null or mi.mesh == null:
				continue
			meshes += 1
			var surf := {}       # family -> the surface it is on, read off the SHARED mesh
			for s in mi.mesh.get_surface_count():
				var bm := mi.mesh.surface_get_material(s)
				if bm != null and fams.has(bm.resource_name):
					surf[bm.resource_name] = s
			for s in mi.mesh.get_surface_count():
				var m := mi.get_surface_override_material(s)
				if m == null:
					continue
				overrides += 1
				worn[m.resource_name] = int(worn.get(m.resource_name, 0)) + 1
				var fam: String = str(owner_of.get(m.resource_name, ""))
				if fam == "":
					bad.append("%s/%s surface %d wears %s, which is no facade tone" % [f, c.name, s, m.resource_name])
				elif int(surf.get(fam, -1)) != s:
					bad.append("%s/%s: %s on surface %d, its %s is surface %s"
						% [f, c.name, m.resource_name, s, fam, surf.get(fam, -1)])
		cell.free()
	_check(bad.is_empty(), "cell facade tones: %d overrides on %d building meshes, %s" % [overrides, meshes, worn])
	for b in bad.slice(0, 5):
		print("  ", b)
	# a mixture is a mixture: every tone past the base is really worn
	var missing := []
	for fam in fams:
		for i in range((fams[fam] as Array).size()):
			if i > 0 and not worn.has(fams[fam][i]):
				missing.append(fams[fam][i])
	_check(missing.is_empty(), "every facade tone is worn by some building (%s unused)" % [missing])
