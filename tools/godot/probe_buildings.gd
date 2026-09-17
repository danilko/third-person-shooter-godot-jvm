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
##   door      the character's own upright capsule (r 0.35, h 1.75, Character.tscn) fits in every doorway,
##             and a ray walks in through it;
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
		_probe(id, inst, meta)
		inst.queue_free()
		await physics_frame
	_check(probed >= 10, "%d building scenes probed" % probed)
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

	var space := inst.get_world_3d().direct_space_state
	var o := inst.global_position
	var top := float(meta["wall_top_m"])
	var hit := _ray(space, o + Vector3(0.3, top + 10.0, 0.3), o + Vector3(0.3, -1.0, 0.3))
	if example:
		_check(not hit.is_empty() and hit.position.y > 0.5 * top, "%s roof hit at %s" % [id, hit.get("position")])
		return
	_check(not hit.is_empty() and absf(hit.position.y - top) < 0.05, "%s roof at %.2f (wall top %.2f)" % [id,
		hit.position.y if not hit.is_empty() else -1.0, top])
	hit = _ray(space, o + Vector3(0.3, 1.0, 0.3), o + Vector3(0.3, -1.0, 0.3))
	_check(not hit.is_empty() and absf(hit.position.y) < 0.02, "%s ground slab at %.3f" % [id,
		hit.position.y if not hit.is_empty() else -9.0])

	for d in meta["doors"]:
		var c := o + Vector3(d["center"][0], 0, d["center"][2])
		var out := Vector3(d["outward"][0], 0, d["outward"][2])
		var at := c - out * 0.09
		var blocked := _capsule_hits(space, at)
		var r := _ray(space, c + out * 2.0 + Vector3(0, 1.0, 0), c - out * 1.5 + Vector3(0, 1.0, 0))
		_check(not blocked and r.is_empty(), "%s door %s/%d: capsule fits (%s), ray walks in (%s), opening %.2f x %.2f m" % [
			id, d["side"], d["module"], not blocked, r.is_empty(), d["width"], d["height"]])
	for sp in meta["solid_probes"]:
		var c := o + Vector3(sp["center"][0], 0, sp["center"][2])
		var out := Vector3(sp["outward"][0], 0, sp["outward"][2])
		var blocked := _capsule_hits(space, c - out * 0.09)
		var r := _ray(space, c + out * 2.0 + Vector3(0, 1.0, 0), c - out * 1.5 + Vector3(0, 1.0, 0))
		var at_wall := not r.is_empty() and absf((r.position - c).dot(out)) < 0.05
		_check(blocked and at_wall, "%s wall %s/%d blocks the capsule (%s) and the ray at the facade (%s)" % [
			id, sp["side"], sp["module"], blocked, at_wall])


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
