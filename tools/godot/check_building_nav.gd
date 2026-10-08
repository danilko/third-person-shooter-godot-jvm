extends SceneTree
## IS EVERY ENTERABLE BUILDING'S INTERIOR NAVMESH ONE WALKABLE PIECE? (2026-10-08: police units never reached a
## player in a station because Central's navmesh was 122 islands -- the bake's apron stood at the track bed and cut
## every stairwell, and a 0.175 m cell rounded the ticket-gate lanes shut.)
##
##   godot --headless --path . --script tools/godot/check_building_nav.gd [-- --verbose] [--all]
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

func _initialize() -> void:
	var verbose := "--verbose" in OS.get_cmdline_user_args()
	var all := "--all" in OS.get_cmdline_user_args()
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
