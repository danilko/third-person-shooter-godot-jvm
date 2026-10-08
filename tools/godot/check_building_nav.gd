extends SceneTree
## IS EVERY ENTERABLE BUILDING'S INTERIOR NAVMESH ONE WALKABLE PIECE? (2026-10-08: police units never reached a
## player in a station because Central's navmesh was 122 islands -- the bake's apron stood at the track bed and cut
## every stairwell, and a 0.175 m cell rounded the ticket-gate lanes shut.)
##
##   godot --headless --path . --script tools/godot/check_building_nav.gd [-- --verbose] [--all] [--doors=T1,T2]
##   --doors: per type, the components a street door (meta "doors", 0.8 m inside) reaches, and the rest by height --
##   a roof is unreachable by design, a FLOOR unreachable from every door is a defect.
##
## For each buildings/nav/Station_*_nav.res: polygons joined by shared (welded, 2 cm) vertices into components; the
## largest must hold at least MAIN_SHARE of all polygons (the leftovers are roofs and bed strips nobody walks to).
## ACCEPT names a type whose split is known and why. Re-run after bake_building_nav.gd --all --write.
## Other types are only REPORTED (--all): a kit building's walkable roof is an island by design, so a share rule cannot
## tell a defect there -- that wants a door-to-floor check.

const NAV := "res://src/main/resources/com/openworld/world/buildings/nav/"
const MAIN_SHARE := 0.85
const ACCEPT := {
	"Station_CastleTown": "open-air: the far platform is reached by the street's level crossing, outside the building",
}

func _components(nm: NavigationMesh) -> Array:
	var verts := nm.get_vertices()
	var key := {}
	var vid := PackedInt32Array()
	vid.resize(verts.size())
	for i in verts.size():
		var v := verts[i]
		var k := Vector3i(roundi(v.x * 50), roundi(v.y * 50), roundi(v.z * 50))
		if not key.has(k):
			key[k] = key.size()
		vid[i] = key[k]
	var par := PackedInt32Array()
	par.resize(key.size())
	for i in key.size():
		par[i] = i
	var polys := []
	for p in nm.get_polygon_count():
		polys.append(nm.get_polygon(p))
	for poly in polys:
		var r0 := vid[poly[0]]
		while par[r0] != r0: r0 = par[r0]
		for j in range(1, poly.size()):
			var r := vid[poly[j]]
			while par[r] != r: r = par[r]
			if r != r0:
				par[r] = r0
	var n := {}
	for poly in polys:
		var r := vid[poly[0]]
		while par[r] != r: r = par[r]
		n[r] = n.get(r, 0) + 1
	var sizes := n.values()
	sizes.sort()
	sizes.reverse()
	return sizes

## --doors=<Type,...>: which components a street door reaches. Each polygon's component root, by index.
func _labels(nm: NavigationMesh) -> PackedInt32Array:
	var verts := nm.get_vertices()
	var key := {}
	var vid := PackedInt32Array()
	vid.resize(verts.size())
	for i in verts.size():
		var v := verts[i]
		var k := Vector3i(roundi(v.x * 50), roundi(v.y * 50), roundi(v.z * 50))
		if not key.has(k):
			key[k] = key.size()
		vid[i] = key[k]
	var par := PackedInt32Array()
	par.resize(key.size())
	for i in key.size():
		par[i] = i
	for p in nm.get_polygon_count():
		var poly := nm.get_polygon(p)
		var r0 := vid[poly[0]]
		while par[r0] != r0: r0 = par[r0]
		for j in range(1, poly.size()):
			var r := vid[poly[j]]
			while par[r] != r: r = par[r]
			if r != r0:
				par[r] = r0
	var out := PackedInt32Array()
	out.resize(nm.get_polygon_count())
	for p in nm.get_polygon_count():
		var r := vid[nm.get_polygon(p)[0]]
		while par[r] != r: r = par[r]
		out[p] = r
	return out

func _door_report(t: String) -> void:
	var nm: NavigationMesh = load(NAV + t + "_nav.res")
	var b: Node = (load("res://src/main/resources/com/openworld/world/buildings/%s_Shop.tscn" % t) as PackedScene).instantiate()
	var meta: Dictionary = b.get_meta("building", {})
	b.free()
	var lab := _labels(nm)
	var verts := nm.get_vertices()
	var info := {}   # root -> [polys, ymin, ymax, cx, cz, reached]
	var cent := []
	for p in nm.get_polygon_count():
		var poly := nm.get_polygon(p)
		var c := Vector3.ZERO
		for i in poly:
			c += verts[i]
		c /= poly.size()
		cent.append(c)
		var r := lab[p]
		if not info.has(r):
			info[r] = [0, 1e9, -1e9, 0.0, 0.0, false]
		var e: Array = info[r]
		e[0] += 1
		e[1] = minf(e[1], c.y)
		e[2] = maxf(e[2], c.y)
		e[3] += c.x
		e[4] += c.z
	var doors: Array = meta.get("doors", [])
	for d in doors:
		var c: Array = d["center"]
		var o: Array = d.get("outward", [0, 0, 1])
		var inside := Vector3(c[0], c[1], c[2]) - Vector3(o[0], 0, o[2]) * 0.8
		var best := -1
		var bd := 1.5
		for p in cent.size():
			var q: Vector3 = cent[p]
			var dd := Vector2(q.x - inside.x, q.z - inside.z).length()
			if absf(q.y - inside.y) < 1.2 and dd < bd:
				bd = dd
				best = p
		if best >= 0:
			info[lab[best]][5] = true
	# an open yard is entered from the street at its edge, not through a door: a component with ground-level
	# polygons within 2 m of the footprint's edge counts as reached
	var fp: Array = meta.get("footprint_m", [])
	if fp.size() >= 2:
		var hx := float(fp[0]) * 0.5
		var hz := float(fp[1]) * 0.5
		for p in cent.size():
			var q: Vector3 = cent[p]
			if q.y < 1.0 and (absf(q.x) > hx - 2.0 or absf(q.z) > hz - 2.0):
				info[lab[p]][5] = true
	var total := nm.get_polygon_count()
	var reached := 0
	var rows := info.values()
	rows.sort_custom(func(a, b): return a[0] > b[0])
	for e in rows:
		if e[5]:
			reached += e[0]
	print("  %-22s %d doors, %d polys, %.1f%% reached from a door; wall top %.1f m" % [t, doors.size(), total,
			100.0 * reached / maxf(1, total), float(meta.get("wall_top_m", meta.get("height_m", 0.0)))])
	for e in rows.slice(0, 8):
		print("    %s %5d polys  y %.2f..%.2f  centre (%.0f, %.0f)" % ["DOOR " if e[5] else "     ", e[0], e[1], e[2], e[3] / e[0], e[4] / e[0]])

func _initialize() -> void:
	var verbose := "--verbose" in OS.get_cmdline_user_args()
	var all := "--all" in OS.get_cmdline_user_args()
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--doors="):
			for t in a.substr(8).split(","):
				_door_report(t)
			quit(0)
			return
	var fails := 0
	var files := Array(DirAccess.get_files_at(NAV)).filter(func(f): return f.ends_with("_nav.res"))
	files.sort()
	for f in files:
		var t: String = f.trim_suffix("_nav.res")
		var sizes := _components(load(NAV + f))
		var total := 0
		for s in sizes: total += s
		var share: float = float(sizes[0]) / maxf(1.0, total) if sizes.size() > 0 else 0.0
		var gated := t.begins_with("Station_")
		if not gated and not all:
			continue
		var ok := share >= MAIN_SHARE or ACCEPT.has(t) or not gated
		if not ok:
			fails += 1
		if verbose or not ok or (not gated and share < MAIN_SHARE):
			print("  %s  %-28s %5d polys, main %5.1f%%, largest %s%s" % ["PASS" if (ok and gated) else ("INFO" if not gated else "FAIL"), t, total, share * 100.0,
				str(sizes.slice(0, 4)), ("  (accepted: " + ACCEPT[t] + ")") if ACCEPT.has(t) and share < MAIN_SHARE else ""])
	print("RESULT %s (%d stations split)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails > 0 else 0)
