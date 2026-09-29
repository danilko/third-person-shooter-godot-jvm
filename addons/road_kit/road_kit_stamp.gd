@tool
extends RefCounted
## Road Kit B7 (PLAN.md 3.1): the roads written INTO Terrain3D's height field. EDITOR TOOLING ONLY.
##
## The island's rule (`island_v3_terrain.Carve`, CLAUDE.md "THE ROAD DEFORMS THE GROUND; IT DOES NOT
## CUT IT") is a heightfield deformation, never a boolean, and so is this: every terrain vertex near a
## road is set from the NATURAL ground and the road corridors (`roadkit_cli.py corridors` -- the same
## `point_edges.band_corridors` the island carve reads, pads included), so the collider IS the visual.
##
##   inside the paved half-width + VERGE    ground = road surface - CLEARANCE
##   outside it, by e metres                 cap   = that + e / CUT_SLOPE    (the cut batter; on the uphill side of
##                                                   a `cut_batter` road, that + e * cut_batter -- PLAN.md 3.15)
##                                           floor = that - e / FILL_SLOPE   (the fill batter)
##   new height = min(cap over every corridor, max(natural, floor over the corridors that may fill))
##
## CARVE AND FILL, WHERE THE ISLAND IS CARVE-ONLY -- and the measurement that decides it. The island's
## carve refuses to raise ground because "`road_support` already owns FILL and builds the embankment
## toes". It computes them (`rka_fill_w`) and NOTHING SWEEPS THEM: `point_build` has no embankment
## layer, so on DebugRoads 120 lane samples between 0.4 and 4 m over the user's lowered ground stood on
## air (`probe_road_ground.gd`, B6b). In a Terrain3D world the height field is the only thing that can
## carry them. The island's second reason -- a raise would fill the bay under a bridge -- is kept by the
## classification: a corridor point may fill only where `road_support.support_kind` of it and the
## natural ground is not PIER/TUNNEL, so a deck on columns still stands over open ground, and the last
## fill point before a bridge is its abutment.
##
## IDEMPOTENT BY CONSTRUCTION: every height is derived from the NATURAL ground (the network's ground
## sidecar, `road_kit_ground.gd`), never from the terrain as it stands, and every vertex the PREVIOUS
## stamp reached is re-derived too -- so stamping twice changes nothing, and a road that moved leaves
## no trench behind. The stamp record (`<stem>.stamp.json`) is what says the terrain is no longer
## natural; `restore` puts the natural ground back and deletes it.

const Ground := preload("res://addons/road_kit/road_kit_ground.gd")
const Service := preload("res://addons/road_kit/road_kit_service.gd")
const SCHEMA_VER := 1
## The ground under a paved surface sits this far below it. The island uses 0.30 m against a 12 m mesh
## grid; Terrain3D's 2 m grid follows the road closely enough for the terrain to show only as a hairline.
## 0.10 m since 2026-09-17 (user: "let road always be 0.1 m above ground"): 0.05 left the terrain's
## bilinear triangles a few cm under the lane on a cross-fall, so a 2 m cell could still poke through.
const CLEARANCE := 0.10
const CHANGE_TOL := 0.002
## Flat shelf past the PAVED edge. A band's half-width is the carriageway (`band_corridors` reads it off
## the paved outline), so the shelf must carry a footway (4 m on a T2) plus one 2 m terrain cell --
## the island's "the verge is one ground cell" rule: no terrain triangle spanning the road may have a
## raised corner.
const VERGE := 6.0
## How far a batter may run. A cut 25 m deep (`CUT_MAX`, past which it is a tunnel) at 1:1 is 25 m;
## a fill batter at 1:1.5 reaches 20 m of drop in 30 m, which is the spill slope of a bridge abutment
## into the valley it crosses.
const MAX_REACH := 30.0
const BUCKET := 16.0
## Kinds of corridor point the ground may be raised to (`road_support.support_kind`). Not PIER or
## TUNNEL, and not UNKNOWN (no natural ground to judge from).
const FILLABLE := ["NONE", "FILL", "CUT"]
## A BENCH road's point (`cut_batter`, PLAN.md 3.15) fills over LAND only: where the natural ground is under
## `LAND_Z` (the water line) the ground is left alone, so a coast road never pushes an embankment into the sea.
const LAND_ONLY := "BENCH"
const LAND_Z := 0.3
## Two corridors whose surfaces at one spot differ by more than this are a road passing UNDER another
## (the lower keeps its ground); by less, they are one paved area meeting itself -- a junction mouth, a
## ramp's gore -- and the NEAREST decides.
const UNDERPASS := 3.0
## THE BLOCK LAYER (PLAN.md 3.30 L2, CLAUDE.md "The block owns its ground"). `tools/island_ground.py` writes the city
## blocks' own surface into the terrain AFTER the road stamp, and `apply_paint_grid.gd` leaves two files in the data
## directory: the marker `paint_terrain.gd` refuses over, and the layer itself, sparse (`URBAN_LAYER`). A stamp run
## afterwards re-derives every vertex it reaches from the NATURAL ground and so wipes the block ground there, with
## nothing to say so -- a dock Stamp after `tools/island_world.sh` took the kerb-level fill back down 0.15 m. So
## `stamp_network` refuses while the marker exists (rebuild with `island_world.sh --from terrain`), and `stamp` takes
## the layer, applied OVER the stamp where it has a value, which is exactly the order the pipeline built it in: a
## probe re-stamping with it must change nothing.
const URBAN_MARKER := "urban_paint.marker"
const URBAN_LAYER := "urban_block.layer"
const LAYER_MAGIC := 0x314C4255   # "UBL1", little-endian
## THE RAIL IS A GUARD (2026-09-29, `probe_rail_track` gauge sweep). A road stamp's fill batter never raises ground over
## another network's RAIL corridor: the ring lifted over the Main line near the Rainbow Bridge spilled its 1:1.5 batter
## 8 m up onto the elevated track, into the train's gauge. The rail is stamped first and its record is read here, so a
## road stamp caps its result (never below the natural ground) at the rail's surface - CLEARANCE out to its paved edge
## + GUARD_MARGIN, rising 1:1 beyond: the train's gauge (1.5 m past a track centre, 4 m inside the rail band's edge) is
## clear by construction. A guard network is one whose record's roads are all `road_class` "rail".
const GUARD_MARGIN := 0.5

## `{"segments": [...], "buckets": {Vector2i: [int]}, "rect": Rect2 (world XZ)}` from the CLI's corridors
## (Godot axes, network frame) placed by `to_world`.
static func _index(corridors: Array, to_world: Transform3D, params: Dictionary) -> Dictionary:
	var segs := []
	var buckets := {}
	var rect := Rect2()
	var first := true
	for ci in corridors.size():
		var pts: Array = corridors[ci].get("points", [])
		for i in range(pts.size() - 1):
			var a: Array = pts[i]
			var b: Array = pts[i + 1]
			var aw: Vector3 = to_world * Vector3(a[0], a[1], a[2])
			var bw: Vector3 = to_world * Vector3(b[0], b[1], b[2])
			# 0 never, 1 fill, 2 fill over land only
			var fa: int = 1 if str(a[5]) in FILLABLE else (2 if str(a[5]) == LAND_ONLY else 0)
			var fb: int = 1 if str(b[5]) in FILLABLE else (2 if str(b[5]) == LAND_ONLY else 0)
			var reach := maxf(float(a[3]), float(b[3])) + VERGE + MAX_REACH
			# The steep cut face (PLAN.md 3.15, `roadkit_cli._steep_side`): rise per metre across on the uphill side,
			# signed by which side that is (Godot XZ cross product), 0 = the ordinary batter both sides.
			var sa := float(a[6]) if a.size() > 6 and a[6] != null else 0.0
			var sb := float(b[6]) if b.size() > 6 and b[6] != null else 0.0
			segs.append({"a": aw, "b": bw, "ha": float(a[3]), "hb": float(b[3]), "fa": fa, "fb": fb, "c": ci,
					"sa": sa, "sb": sb})
			var lo := Vector2(minf(aw.x, bw.x) - reach, minf(aw.z, bw.z) - reach)
			var hi := Vector2(maxf(aw.x, bw.x) + reach, maxf(aw.z, bw.z) + reach)
			var r := Rect2(lo, hi - lo)
			rect = r if first else rect.merge(r)
			first = false
			for bx in range(int(floor(lo.x / BUCKET)), int(floor(hi.x / BUCKET)) + 1):
				for bz in range(int(floor(lo.y / BUCKET)), int(floor(hi.y / BUCKET)) + 1):
					var k := Vector2i(bx, bz)
					if not buckets.has(k):
						buckets[k] = []
					buckets[k].append(segs.size() - 1)
	return {"segments": segs, "buckets": buckets, "rect": rect}

## The stamped height at world XZ `(x, z)` over `natural`, or NAN where no corridor reaches.
##
## Every corridor is represented by its NEAREST segment only. Taking every segment in reach measured a
## graded road's own further segments from their end caps and capped the ground at the lowest of them:
## 0.75 m of air under a 7% stretch of DebugRoads `loop`.
##
## ON A ROAD, THE ROAD DECIDES; OFF EVERY ROAD, THE BATTERS DO. Within some corridor's paved half-width
## + VERGE the ground is the NEAREST corridor's surface (raised to it only where that corridor may fill),
## lowered further to any corridor it stands ON (inside that one's paved edge -- where a road's end meets
## a pad's edge at a slightly different height) or to one more than UNDERPASS below (a street under a
## deck). Batters of
## other corridors do not reach in: a hairpin's lower leg must not cut under the upper leg's
## carriageway, and a junction's lower approach must not cut under the pad. Outside every corridor, the
## cut batter is the min over the corridors and the fill batter is the nearest one's.
static func height_at(index: Dictionary, params: Dictionary, x: float, z: float, natural: float, cell: float = 2.0) -> float:
	var cut_slope := float(params.get("cut_slope", 1.0))
	var fill_slope := float(params.get("fill_slope", 1.5))
	var segs: Array = index["segments"]
	var per := {}   # corridor -> [sd (distance past the paved edge), surface, fill]
	for i in index["buckets"].get(Vector2i(int(floor(x / BUCKET)), int(floor(z / BUCKET))), []):
		var s: Dictionary = segs[i]
		var a: Vector3 = s["a"]
		var b: Vector3 = s["b"]
		var dx := b.x - a.x
		var dz := b.z - a.z
		var l2 := dx * dx + dz * dz
		var t := 0.0 if l2 < 1e-9 else clampf(((x - a.x) * dx + (z - a.z) * dz) / l2, 0.0, 1.0)
		var d := Vector2(x - (a.x + dx * t), z - (a.z + dz * t)).length()
		var sd := d - lerpf(s["ha"], s["hb"], t)
		if sd - VERGE > MAX_REACH:
			continue
		var c: int = s["c"]
		if not per.has(c) or sd < per[c][0]:
			# The fill decision follows the NEARER end: the kit decides support per sample, so the
			# half of a segment beside a PIER sample is the bridge's and the other half is the fill's.
			# The cut batter on this side: the steep face where this vertex is on the corridor's uphill side.
			var steep: float = s["sa"] if t < 0.5 else s["sb"]
			var rise := 1.0 / cut_slope
			if steep != 0.0:
				var side := dx * (z - a.z) - dz * (x - a.x)
				if side * steep > 0.0:
					rise = absf(steep)
			var fk: int = s["fa"] if t < 0.5 else s["fb"]
			per[c] = [sd, lerpf(a.y, b.y, t) - CLEARANCE, fk == 1 or (fk == 2 and natural >= LAND_Z), rise]
	if per.is_empty():
		return NAN
	var near: Array = []
	for c in per:
		if near.is_empty() or per[c][0] < near[0]:
			near = per[c]
	if near[0] <= VERGE:
		var cap: float = near[1]
		for c in per:
			# Standing ON a surface (inside its paved edge, or within one terrain CELL of it -- the grid
			# interpolates between vertices, so a vertex one cell out decides the ground under the edge)
			# always caps: where a road's end runs under the edge of a pad a few cm higher, the road is
			# what the lane is on. A surface whose VERGE alone reaches here caps only when it is a road
			# passing under.
			if (per[c][0] <= cell or per[c][1] < near[1] - UNDERPASS) and per[c][0] <= VERGE:
				cap = minf(cap, per[c][1])
		return minf(cap, maxf(natural, near[1] if near[2] else -INF))
	var cap_out := INF
	for c in per:
		cap_out = minf(cap_out, per[c][1] + maxf(0.0, per[c][0] - VERGE) * per[c][3])
	# The fill batter runs on down until it meets the ground (`max(natural, floor)` stops it there) --
	# NOT to a fixed toe: cutting it off at `FILL_MAX * FILL_SLOPE` left a vertical wall wherever the
	# ground beside a filled road fell away further than that (measured: +20.81 m on DebugRoads). And
	# only the NEAREST corridor may fill: the highest floor of every corridor in reach let the last filled
	# stretch before a bridge spill its batter 30 m out under the deck, burying 116 of 199 clear-span
	# samples. Nearest-only stops the fill where the bridge starts -- the abutment.
	var floor_out: float = near[1] - (near[0] - VERGE) / fill_slope if near[2] else -INF
	return minf(cap_out, maxf(natural, floor_out))

## Stamp `corridors` (the CLI's `corridors` object) into `terrain` under `net`. `previous` is the last
## stamp record's corridors (re-derived so a moved road leaves nothing behind). Writes the heights and
## updates the maps; SAVING is the caller's (the tool saves the data directory, the editor its scene).
## `{"ok", "message", "changed", "carved", "filled", "restored", "lowest", "highest"}`.
static func stamp(net: Node3D, terrain: Node, corridors: Dictionary, previous: Array = [], restore_only: bool = false, layer: Dictionary = {}, dirty = null) -> Dictionary:
	var natural := Ground.load_grid(Ground.sidecar_path(str(net.get("record_path"))))
	if natural.is_empty():
		return {"ok": false, "message": "no ground sidecar for %s -- sample the natural ground first (write_roadkit_ground.gd / Build)" % net.name}
	var data = terrain.get("data")
	if data == null:
		return {"ok": false, "message": "no Terrain3D data"}
	var spacing := float(terrain.get("vertex_spacing"))
	var to_world := Ground._world_xf(net)
	var from_world := to_world.affine_inverse()
	var now := _index([] if restore_only else corridors.get("corridors", []), to_world, corridors)
	var old := _index(previous, to_world, corridors)
	var rect: Rect2 = now["rect"]
	if old["segments"].size() > 0:
		rect = old["rect"] if now["segments"].is_empty() else rect.merge(old["rect"])
	if now["segments"].is_empty() and old["segments"].is_empty():
		return {"ok": true, "message": "nothing to stamp", "changed": 0, "carved": 0, "filled": 0, "restored": 0, "lowest": 0.0, "highest": 0.0}
	var ctx := {"data": data, "natural": natural, "now": now, "corridors": corridors, "layer": layer,
			"guard": _index(guard_corridors(net), to_world, corridors),
			"to_world": to_world, "from_world": from_world, "spacing": spacing, "changed": 0, "carved": 0,
			"filled": 0, "restored": 0, "lowest": 0.0, "highest": 0.0, "regions": {}}
	if dirty is Array:
		# INCREMENTAL (`stamp_network`): only the vertices a CHANGED corridor reaches, old or new -- a vertex no changed
		# corridor's buckets cover has exactly the candidate segments it had at the last stamp, so its height is the
		# same. Walked by bucket cell (BUCKET is a whole number of vertex spacings, so each vertex once).
		var d := _index(dirty, to_world, corridors)
		var n := int(round(BUCKET / spacing))
		for k in d["buckets"]:
			for i in n:
				for j in n:
					_stamp_vertex(ctx, k.x * BUCKET + i * spacing, k.y * BUCKET + j * spacing)
	else:
		var x0 := floorf(rect.position.x / spacing) * spacing
		var z0 := floorf(rect.position.y / spacing) * spacing
		var x := x0
		while x <= rect.end.x:
			var z := z0
			while z <= rect.end.y:
				_stamp_vertex(ctx, x, z)
				z += spacing
			x += spacing
	var regions: Dictionary = ctx["regions"]
	for loc in regions:
		data.set_region_modified(loc, true)
	var changed: int = ctx["changed"]
	if changed > 0:
		data.update_maps(0, true, false)
		data.calc_height_range(true)
	return {"ok": true, "changed": changed, "carved": ctx["carved"], "filled": ctx["filled"], "restored": ctx["restored"],
			"lowest": ctx["lowest"], "highest": ctx["highest"], "regions": regions.size(),
			"message": "%s %d vertex(es) in %d region(s): %d carved (to %.2f m), %d filled (to +%.2f m), %d restored to natural%s" % [
				"restored" if restore_only else "stamped", changed, regions.size(), ctx["carved"], ctx["lowest"],
				ctx["filled"], ctx["highest"], ctx["restored"],
				"" if not (dirty is Array) else " (incremental: %d changed corridor(s))" % dirty.size()]}

static func _stamp_vertex(ctx: Dictionary, x: float, z: float) -> void:
	var data = ctx["data"]
	var world := Vector3(x, 0.0, z)
	var cur: float = data.get_height(world)
	if is_nan(cur):
		return
	var from_world: Transform3D = ctx["from_world"]
	var to_world: Transform3D = ctx["to_world"]
	var local := from_world * world
	var k := Ground.Frame.to_kit(local)
	var nat := Ground.lookup(ctx["natural"], k.x, k.y)
	if is_nan(nat):
		return
	nat = (to_world * Vector3(local.x, nat, local.z)).y
	var h := height_at(ctx["now"], ctx["corridors"], x, z, nat, ctx["spacing"])
	if is_nan(h):
		h = nat
	h = minf(h, maxf(nat, guard_cap(ctx["guard"], x, z)))
	var layer: Dictionary = ctx["layer"]
	if not layer.is_empty():
		var lv := layer_height(layer, x, z)
		if not is_nan(lv):
			h = lv
	# 2 mm, not 0.5: a height round-trips through float32 (dump -> numpy -> apply), and a re-stamp
	# read 3 of 855 845 vertices 1 mm off with nothing moved (probe_road_stamp, 3.30 L2)
	if absf(h - cur) > CHANGE_TOL:
		if OS.get_environment("STAMP_DEBUG") != "" and ctx["changed"] < 20:
			print("  stamp changes (%.1f, %.1f): %.3f -> %.3f (natural %.3f)" % [x, z, cur, h, nat])
		data.set_height(world, h)
		ctx["regions"][data.get_region_location(world)] = true
		ctx["changed"] += 1
		if h < nat - 0.0005:
			ctx["carved"] += 1
		elif h > nat + 0.0005:
			ctx["filled"] += 1
		else:
			ctx["restored"] += 1
	ctx["lowest"] = minf(ctx["lowest"], h - nat)
	ctx["highest"] = maxf(ctx["highest"], h - nat)

## The block layer of `terrain`'s data directory, `{}` when there is none: `{"nx", "nz", "x0", "z0", "step", "h":
## PackedFloat32Array (dense, NAN where the layer has no value)}`. The file is sparse: "UBL1", nx, nz (i32), x0, z0,
## step (f32), count (i32), then count x (index i32, height f32), index = row * nx + column on the
## `dump_height_grid.gd` vertex grid.
static func load_layer(terrain: Node) -> Dictionary:
	var path := str(terrain.get("data_directory")).path_join(URBAN_LAYER)
	if not FileAccess.file_exists(path):
		return {}
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null or f.get_32() != LAYER_MAGIC:
		return {}
	var nx := f.get_32()
	var nz := f.get_32()
	var out := {"nx": nx, "nz": nz, "x0": f.get_float(), "z0": f.get_float(), "step": f.get_float()}
	var n := f.get_32()
	var h := PackedFloat32Array()
	h.resize(nx * nz)
	h.fill(NAN)
	var raw := f.get_buffer(n * 8)
	var idx := raw.to_int32_array()
	var val := raw.to_float32_array()
	for i in n:
		h[idx[2 * i]] = val[2 * i + 1]
	out["h"] = h
	out["count"] = n
	return out

## The layer's height at world XZ, NAN off the layer. Snapped to the grid: the layer is written per vertex.
static func layer_height(layer: Dictionary, x: float, z: float) -> float:
	var st: float = layer["step"]
	var i := int(round((x - float(layer["x0"])) / st))
	var j := int(round((z - float(layer["z0"])) / st))
	if i < 0 or j < 0 or i >= int(layer["nx"]) or j >= int(layer["nz"]):
		return NAN
	return (layer["h"] as PackedFloat32Array)[j * int(layer["nx"]) + i]

static func has_block_layer(terrain: Node) -> bool:
	return FileAccess.file_exists(str(terrain.get("data_directory")).path_join(URBAN_MARKER))

## The corridors of every OTHER network beside `net` that is a rail network (`GUARD_MARGIN`) and has been stamped,
## in its own frame -- the same frame as `net`'s on both worlds (one network node transform), which `stamp` asserts.
static func guard_corridors(net: Node) -> Array:
	var out := []
	var parent := net.get_parent()
	if parent == null:
		return out
	for n in parent.get_children():
		if n == net or n.get_script() != net.get_script() or not _is_rail(str(n.get("record_path"))):
			continue
		if not Ground._world_xf(n).is_equal_approx(Ground._world_xf(net)):
			push_warning("road_kit_stamp: %s is not in %s's frame; not a guard" % [n.name, net.name])
			continue
		out.append_array(read_record(n).get("corridors", []))
	return out

static func _is_rail(record_path: String) -> bool:
	if not FileAccess.file_exists(record_path):
		return false
	var d = JSON.parse_string(FileAccess.get_file_as_string(record_path))
	if typeof(d) != TYPE_DICTIONARY or typeof(d.get("roads")) != TYPE_ARRAY or d["roads"].is_empty():
		return false
	for r in d["roads"]:
		if typeof(r) != TYPE_DICTIONARY or str(r.get("road_class", "")) != "rail":
			return false
	return true

## The highest the ground may stand at world XZ beside the guard corridors, INF where none is near.
static func guard_cap(index: Dictionary, x: float, z: float) -> float:
	var cap := INF
	for i in index["buckets"].get(Vector2i(int(floor(x / BUCKET)), int(floor(z / BUCKET))), []):
		var s: Dictionary = index["segments"][i]
		var a: Vector3 = s["a"]
		var b: Vector3 = s["b"]
		var dx := b.x - a.x
		var dz := b.z - a.z
		var l2 := dx * dx + dz * dz
		var t := 0.0 if l2 < 1e-9 else clampf(((x - a.x) * dx + (z - a.z) * dz) / l2, 0.0, 1.0)
		var d := Vector2(x - (a.x + dx * t), z - (a.z + dz * t)).length()
		var sd := d - lerpf(s["ha"], s["hb"], t) - GUARD_MARGIN
		cap = minf(cap, lerpf(a.y, b.y, t) - CLEARANCE + maxf(0.0, sd))
	return cap

static func read_record(net: Node) -> Dictionary:
	var path := Ground.stamp_record_path(str(net.get("record_path")))
	if not FileAccess.file_exists(path):
		return {}
	var d = JSON.parse_string(FileAccess.get_file_as_string(path))
	return d if typeof(d) == TYPE_DICTIONARY else {}

static func write_record(net: Node, corridors: Dictionary) -> Error:
	var f := FileAccess.open(Ground.stamp_record_path(str(net.get("record_path"))), FileAccess.WRITE)
	if f == null:
		return FileAccess.get_open_error()
	f.store_string(JSON.stringify({"schema_ver": SCHEMA_VER, "clearance": CLEARANCE, "verge": VERGE,
			"rule": rule_md5(), "corridors": corridors.get("corridors", [])}) + "\n")
	return OK

## The stamp rule itself: an incremental stamp is only valid over a terrain the SAME rule stamped.
static func rule_md5() -> String:
	return FileAccess.get_md5("res://addons/road_kit/road_kit_stamp.gd")

## `[changed corridors]` (old AND new) between the last stamp record and `now`, or `null` when an incremental stamp is
## not valid (no record, a different rule or parameters): then the whole footprint is walked.
static func dirty_corridors(prev: Dictionary, now: Array):
	if prev.is_empty() or prev.get("rule", "") != rule_md5() or float(prev.get("clearance", -1.0)) != CLEARANCE \
			or float(prev.get("verge", -1.0)) != VERGE or int(prev.get("schema_ver", -1)) != SCHEMA_VER:
		return null
	var count := {}
	var keep := {}
	for c in prev.get("corridors", []):
		var t := JSON.stringify(c)
		count[t] = int(count.get(t, 0)) + 1
		keep[t] = c
	var out := []
	for c in now:
		var t := JSON.stringify(c)
		if int(count.get(t, 0)) > 0:
			count[t] -= 1
		else:
			out.append(c)
	for t in count:
		for i in int(count[t]):
			out.append(keep[t])
	return out

static func delete_record(net: Node) -> void:
	var path := Ground.stamp_record_path(str(net.get("record_path")))
	if FileAccess.file_exists(path):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(path))

## The whole sequence, shared by the dock and `tools/godot/stamp_roadkit_terrain.gd`: sample the natural
## ground (a stamped network keeps its sidecar as the natural record where it covers), solve the
## corridors over it, stamp, record. `restore` puts the natural ground back and forgets the stamp.
## Saving the terrain data is the caller's.
static func stamp_network(net: Node3D, terrain: Node, restore: bool = false, force: bool = false, full: bool = false) -> Dictionary:
	if has_block_layer(terrain) and not force:
		return {"ok": false, "changed": 0, "message": ("REFUSED: %s carries the city's block ground (%s). A %s would "
				+ "re-derive every vertex it reaches from the natural ground and take the block ground there back down "
				+ "with nothing to say so. Rebuild in order instead: tools/island_world.sh --from terrain.")
				% [str(terrain.get("data_directory")), URBAN_MARKER, "restore" if restore else "stamp"]}
	var prev: Dictionary = read_record(net)
	if restore:
		if prev.is_empty():
			return {"ok": true, "changed": 0, "message": "%s was not stamped" % net.name}
		var rr := stamp(net, terrain, {}, prev.get("corridors", []), true)
		if rr["ok"]:
			delete_record(net)
		return rr
	var g := Ground.write_for(net, terrain)
	if not g["ok"]:
		return g
	var corr := Service.run("corridors", net.record_path, ["--ground", ProjectSettings.globalize_path(g["path"])])
	if corr.get("failed", false) or corr.get("errors", 0) > 0:
		return {"ok": false, "message": "corridors: %s" % corr.get("error", "%d gate error(s)" % corr.get("errors", 0))}
	# INCREMENTAL where the terrain still holds the last stamp by this rule: only the ground a changed corridor reaches
	# (`dirty_corridors`). A terrain stage deletes the record, so a rebuilt terrain is always stamped whole.
	var dirty = null if full else dirty_corridors(prev, corr.get("corridors", []))
	var r := stamp(net, terrain, corr, prev.get("corridors", []), false, {}, dirty)
	if r["ok"]:
		write_record(net, corr)
		r["message"] = g["message"] + "\n" + r["message"] + " (corridor kinds %s)" % str(corr.get("kinds", {}))
	return r
