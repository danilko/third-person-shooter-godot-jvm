extends SceneTree
##
## Assert a world scene's vertical and horizontal envelope, read from the INSTANTIATED scene
## rather than from the numbers someone typed into it.
##
##     Godot_v4.7.2-stable_linux.x86_64 --headless --script tools/godot/check_world_envelope.gd \
##         -- res://.../World.tscn res://.../DebugWorld.tscn
##
## The rule every world scene has to satisfy:
##
##     kill-Z  <  water bottom  <  terrain min  <  ground  <  water top (= sea level Y 0)
##     wall (WorldBounds.half_extent)  <  terrain half-extent
##     water half-span  >  terrain half-extent
##     every Road Kit station + ROAD_REACH  <  the wall's warning band (half_extent - warn_margin)
##
## The last rule is PLAN.md P0 0.3/0.6: the band only warns now (no push), but a road you are warned
## off is still a design error.
##
## A body can only ever be in the water box or on terrain. If the terrain dipped below the box,
## the sea floor there would be outside the swim volume — you would walk off the bottom of the
## ocean and stop being in water. If the wall stood outside the terrain, there would be a band of
## world with no floor before it. Both were real defects, found by measuring rather than reading.
##

var scenes: Array = []
var idx := -1
var n: Node
var failures := 0

## How far paving reaches past a station's centreline: a T2 half-width (29 m / 2) plus a verge.
const ROAD_REACH := 18.0


func _initialize() -> void:
	scenes = OS.get_cmdline_user_args()
	if scenes.is_empty():
		push_error("usage: -- <scene path> [<scene path> ...]")
		quit(2)
		return
	_next()


func _next() -> void:
	if n:
		n.free()
		n = null
	idx += 1
	if idx >= scenes.size():
		print("\n%s" % ("ALL ENVELOPES OK" if failures == 0 else "%d FAILURE(S)" % failures))
		quit(1 if failures else 0)
		return
	var ps: PackedScene = load(scenes[idx])
	if ps == null:
		print("FAIL  cannot load %s" % scenes[idx])
		failures += 1
		_next()
		return
	n = ps.instantiate()
	root.add_child(n)


func _process(_delta: float) -> bool:
	if n:
		_check(scenes[idx])
	_next()
	return false


func _check(path: String) -> void:
	print("\n%s" % path.get_file())
	var terrain: Variant = n.get_node_or_null("NavigationRegion3D/Terrain3D")
	var wv: Variant = n.get_node_or_null("WaterVolume")
	var wb: Variant = n.get_node_or_null("WorldBounds")
	if terrain == null or wv == null or wb == null:
		print("  FAIL missing %s%s%s" % ["Terrain3D " if terrain == null else "",
			"WaterVolume " if wv == null else "", "WorldBounds" if wb == null else ""])
		failures += 1
		return

	var data: Variant = terrain.get("data")
	var hr: Vector2 = data.get_height_range()
	var rs: int = terrain.get("region_size")
	var vs: float = terrain.get("vertex_spacing")
	var locs: Array = data.get("region_locations")
	var span := float(rs) * vs
	var thalf := 0.0
	for l in locs:
		thalf = maxf(thalf, maxf(absf(float(l.x)), absf(float(l.y) + 1.0)) * span)
		thalf = maxf(thalf, maxf(absf(float(l.x) + 1.0), absf(float(l.y))) * span)

	var cs: CollisionShape3D = wv.get_node_or_null("CollisionShape3D")
	var mi: MeshInstance3D = wv.get_node_or_null("Surface")
	var box: BoxShape3D = cs.shape as BoxShape3D
	var top := cs.global_position.y + box.size.y * 0.5
	var bottom := cs.global_position.y - box.size.y * 0.5
	var whalf := box.size.x * 0.5
	var wall: float = wb.get("half_extent")
	var kill: float = wb.get("floor_y")
	var band: float = wall - float(wb.get("warn_margin"))
	var road_reach := _road_reach()

	print("  terrain    %d regions of %d @ %.1f m  ->  +/-%.0f m, height %.2f .. %.2f" % [
		locs.size(), rs, vs, thalf, hr.x, hr.y])
	print("  water      top %.2f (getSurfaceY %.2f), bottom %.2f, half-span %.0f m" % [
		top, wv.get_surface_y(), bottom, whalf])
	print("  bounds     wall %.0f m, warning band from %.0f m, kill-Z %.2f m" % [wall, band, kill])
	if road_reach >= 0.0:
		print("  roads      stations reach +/-%.1f m (+%.0f m of paving)" % [road_reach, ROAD_REACH])

	var checks := [
		["water top is sea level Y 0", is_zero_approx(top)],
		["kill-Z below water bottom", kill < bottom],
		["water bottom below deepest ground", bottom < hr.x],
		["deepest ground below sea level", hr.x < 0.0],
		["wall inside the terrain edge", wall < thalf],
		["water reaches past the terrain edge", whalf > thalf],
		["water mask sees characters (layer 2)", int(wv.get("collision_mask")) & 2 != 0],
		["mesh box matches the collision box",
			mi != null and (mi.mesh as BoxMesh) != null and (mi.mesh as BoxMesh).size == box.size
			and mi.position == cs.position],
		["roads clear the wall's warning band", road_reach < 0.0 or road_reach + ROAD_REACH < band],
		["terrain background is NONE (FLAT is infinite ground)",
			int(terrain.get("material").get("world_background")) == 0],
	]
	var bad := 0
	for c in checks:
		if not c[1]:
			print("  FAIL %s" % c[0])
			bad += 1
	if bad == 0:
		print("  OK   %d checks   (%.1f m water under the sea floor, %.1f m ground past the wall)" % [
			checks.size(), hr.x - bottom, thalf - wall])
	failures += bad


## The furthest |x| or |z| of any Road Kit station in the scene, world space; -1 when there is no network.
func _road_reach() -> float:
	var reach := -1.0
	for net in n.find_children("*", "Node3D", true, false):
		var rp: Variant = net.get("record_path")
		if not (rp is String) or not str(rp).ends_with(".roads.json"):
			continue
		var f := FileAccess.open(str(rp), FileAccess.READ)
		if f == null:
			continue
		var doc: Variant = JSON.parse_string(f.get_as_text())
		if not (doc is Dictionary):
			continue
		var xf: Transform3D = (net as Node3D).global_transform if (net as Node3D).is_inside_tree() else (net as Node3D).transform
		for pt in doc.get("points", []):
			var pos: Array = pt.get("pos", [])
			if pos.size() < 3:
				continue
			# kit (x, y, z) -> Godot (x, z, -y), in the network's frame
			var w := xf * Vector3(float(pos[0]), float(pos[2]), -float(pos[1]))
			reach = maxf(reach, maxf(absf(w.x), absf(w.z)))
	return reach
