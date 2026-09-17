@tool
extends RefCounted
## Road Kit B10.3: the VIEWPORT TOOL MODE -- what a click in the 3D viewport does in each mode. EDITOR TOOLING.
##
## road-generator's feel: pick a mode, then work on the terrain itself. The plugin forwards viewport input
## here (`_forward_3d_gui_input`) and wraps every click that CHANGES the network in one record-restoring
## undo step; nothing here touches the editor, so `test_roadkit_tool.gd` drives exactly what a click runs.
##
##   SELECT   a click on a centreline selects that road; Alt-click a mouth selects its whole junction; a click
##            on a point is left to the editor's own picking.
##   DRAW     click on the ground to start a road, each click adds a station at the click (on the ground,
##            at the drape height), Esc or right-click ends it. The second click creates the road.
##   INSERT   a click on a centreline inserts a station there, in the span the click falls in.
##   DELETE   a click on a point deletes it.
##   CONNECT  click two points: two road ENDS of one road are joined by a SEGMENT; points of different roads
##            make (or grow) an intersection -- unless one is an interior station carrying aux lanes, which
##            is a ramp (`request_ramp`: the solver places it, so the plugin runs `roadkit_cli.py ramp`).
##
## The ground is the scene's Terrain3D (its NATURAL height, `road_kit_ground.natural_height`, so a stamped
## terrain does not lift a new road onto the old one), else the network's own ground plane.

const Gestures := preload("res://addons/road_kit/road_kit_gestures.gd")
const Ground := preload("res://addons/road_kit/road_kit_ground.gd")

enum Mode { OFF, SELECT, DRAW, INSERT, DELETE, CONNECT }
const MODE_NAMES := ["Off", "Select", "Draw Road", "Insert", "Delete", "Connect"]
## A click within this many pixels of a point picks it.
const PICK_POINT_PX := 14.0
## ...and within this of a centreline picks that run.
const PICK_LINE_PX := 12.0
## How far above the ground a drawn station sits -- the drape offset every DebugRoads station carries.
const DRAPE := 0.10

var mode: int = Mode.OFF
## DRAW: the road being drawn (null before its second click) and the first click's position.
var draw_road: Node = null
var draw_start = null
## CONNECT: the first point picked.
var connect_first: Node = null

func set_mode(m: int) -> void:
	mode = m
	reset()

## Drop any half-finished click sequence (a road being drawn, a first connect pick).
func reset() -> void:
	draw_road = null
	draw_start = null
	connect_first = null

# ── picking ──────────────────────────────────────────────────────────────────────────────────────

## The point nearest `screen` within PICK_POINT_PX, or null. Points behind the camera do not count.
static func pick_point(net: Node3D, camera: Camera3D, screen: Vector2) -> Node:
	var best: Node = null
	var best_d := PICK_POINT_PX
	for p in net.all_points():
		var w: Vector3 = p.global_position
		if camera.is_position_behind(w):
			continue
		var d := camera.unproject_position(w).distance_to(screen)
		if d < best_d:
			best_d = d
			best = p
	return best

## `{"road", "uids", "at": Vector3 (network frame), "span": [uid_a, uid_b]}` for the centreline nearest
## `screen` within PICK_LINE_PX, or {}. `runs` is the overlay's last `centrelines` (Godot axes, network frame).
static func pick_centreline(net: Node3D, camera: Camera3D, screen: Vector2, runs: Array) -> Dictionary:
	var to_world: Transform3D = net.global_transform
	var best := {}
	var best_d := PICK_LINE_PX
	for run in runs:
		var pts: Array = run.get("points", [])
		for i in pts.size() - 1:
			var a := Vector3(pts[i][0], pts[i][1], pts[i][2])
			var b := Vector3(pts[i + 1][0], pts[i + 1][1], pts[i + 1][2])
			var wa := to_world * a
			var wb := to_world * b
			var vis := visible_part(camera, wa, wb)
			if vis.is_empty():
				continue
			var va: Vector3 = wa.lerp(wb, vis[0])
			var vb: Vector3 = wa.lerp(wb, vis[1])
			var sa := camera.unproject_position(va)
			var sb := camera.unproject_position(vb)
			var seg := sb - sa
			var t := 0.0 if seg.length_squared() < 1e-9 else clampf((screen - sa).dot(seg) / seg.length_squared(), 0.0, 1.0)
			var d := (sa + seg * t).distance_to(screen)
			if d < best_d:
				best_d = d
				var s := lerpf(vis[0], vis[1], world_param(camera, va, vb, t))
				best = {"road": run["road"], "uids": run.get("uids", []), "at": a.lerp(b, s)}
	if best.is_empty():
		return best
	best["span"] = span_at(net, best["uids"], best["at"])
	return best

## How far in front of the camera a WORLD point is, along its view axis (1 for an orthogonal camera, whose
## projection does not divide by it).
static func view_depth(camera: Camera3D, w: Vector3) -> float:
	if camera.projection == Camera3D.PROJECTION_ORTHOGONAL:
		return 1.0
	return -camera.global_transform.basis.z.dot(w - camera.global_transform.origin)

## The part of the WORLD segment `wa`-`wb` in front of the camera's near plane, as `[s0, s1]` parameters
## along it, or [] when none is. A road passing beside and behind a close camera is still on screen
## where it is in front of it: skipping every segment with an end behind the camera left a zoomed-in
## artist unable to click the road right under the view (the editor self-test's close framing).
static func visible_part(camera: Camera3D, wa: Vector3, wb: Vector3) -> Array:
	if camera.projection == Camera3D.PROJECTION_ORTHOGONAL:
		return [0.0, 1.0]
	var lim := camera.near * 1.01
	var da := view_depth(camera, wa)
	var db := view_depth(camera, wb)
	if da < lim and db < lim:
		return []
	if da >= lim and db >= lim:
		return [0.0, 1.0]
	var s := (lim - da) / (db - da)
	return [s, 1.0] if da < lim else [0.0, s]

## The world parameter along `va`-`vb` (both in front of the camera) of the point a fraction `t` of the way
## along their SCREEN segment. Perspective does not preserve ratios: screen t maps to world s by
## s = t·da / (t·da + (1 − t)·db), so the far half of a segment covers fewer pixels.
static func world_param(camera: Camera3D, va: Vector3, vb: Vector3, t: float) -> float:
	var da := view_depth(camera, va)
	var db := view_depth(camera, vb)
	var den := t * da + (1.0 - t) * db
	return t if absf(den) < 1e-9 else t * da / den

## The two consecutive stations of a run (`uids`, chain order) whose stretch holds `at` (network frame): the
## pair whose segment `at` projects onto closest, in plan view.
static func span_at(net: Node, uids: Array, at: Vector3) -> Array:
	var best := []
	var best_d := INF
	for i in uids.size() - 1:
		var a = net.find_point(uids[i])
		var b = net.find_point(uids[i + 1])
		if a == null or b == null:
			continue
		var pa: Vector3 = a.network_transform().origin
		var pb: Vector3 = b.network_transform().origin
		var ab := Vector2(pb.x - pa.x, pb.z - pa.z)
		var ap := Vector2(at.x - pa.x, at.z - pa.z)
		var t := 0.0 if ab.length_squared() < 1e-9 else clampf(ap.dot(ab) / ab.length_squared(), 0.0, 1.0)
		var d := (ab * t - ap).length()
		if d < best_d:
			best_d = d
			best = [uids[i], uids[i + 1]]
	return best

## Where the mouse ray `from`/`dir` (WORLD) meets the ground, in the network frame at drape height: the
## Terrain3D surface's plan position with the NATURAL ground's height, else the network's own y = 0 plane.
static func ground_hit(net: Node3D, terrain: Node, from: Vector3, dir: Vector3):
	var inv: Transform3D = net.global_transform.affine_inverse()
	if terrain != null and terrain.get("data") != null:
		var hit: Vector3 = terrain.get_intersection(from, dir, false)
		if not (hit.z > 3.4e38 or is_nan(hit.y)):
			var h: float = Ground.natural_height(net, terrain, Ground.natural_source(net), hit)
			if not is_nan(h):
				hit.y = h
			return inv * hit + Vector3.UP * DRAPE
	var lf := inv * from
	var ld := (inv.basis * dir).normalized()
	if absf(ld.y) < 1e-6:
		return null
	var t := -lf.y / ld.y
	return null if t < 0.0 else lf + ld * t + Vector3.UP * DRAPE

# ── clicks ───────────────────────────────────────────────────────────────────────────────────────

## One left click at `screen`. `ctx` = {"net", "camera", "terrain", "runs", "alt"}. Returns
## {"ok", "message", "changed" (wrap in undo), "select": [nodes], "consume": bool, "ramp": [a, b]}.
func click(ctx: Dictionary, screen: Vector2) -> Dictionary:
	var net: Node3D = ctx["net"]
	var cam: Camera3D = ctx["camera"]
	var r := {"ok": true, "message": "", "changed": false, "select": [], "consume": true}
	match mode:
		Mode.SELECT:
			var p := pick_point(net, cam, screen)
			if p != null:
				if ctx.get("alt", false) and Gestures.is_mouth(p):
					r["select"] = Gestures.junction_members(p)
					r["message"] = "junction: %d mouths" % r["select"].size()
					return r
				r["consume"] = false            # the editor's own picking selects the point
				return r
			var hit := pick_centreline(net, cam, screen, ctx.get("runs", []))
			if hit.is_empty():
				r["consume"] = false
				return r
			var road = net.get_node_or_null(NodePath(str(hit["road"])))
			r["select"] = [road] if road != null else []
			r["message"] = "road %s" % hit["road"]
		Mode.DELETE:
			var p := pick_point(net, cam, screen)
			if p == null:
				return _nothing(r, "click a point to delete it")
			var g := Gestures.delete_point(p)
			r["changed"] = g["ok"]
			r["message"] = g["message"]
		Mode.INSERT:
			var hit := pick_centreline(net, cam, screen, ctx.get("runs", []))
			if hit.is_empty() or hit["span"].size() < 2:
				return _nothing(r, "click on a road's centreline to insert a station")
			var a = net.find_point(hit["span"][0])
			var g := Gestures.insert_after(a)
			if not g["ok"]:
				r["ok"] = false
				r["message"] = g["message"]
				return r
			var node: Node3D = g["node"]
			var xf: Transform3D = node.network_transform()
			node.set_network_transform(Transform3D(xf.basis, hit["at"]))
			r["changed"] = true
			r["select"] = [node]
			r["message"] = "inserted a station in %s" % hit["road"]
		Mode.DRAW:
			var at = ground_hit(net, ctx.get("terrain"), cam.project_ray_origin(screen), cam.project_ray_normal(screen))
			if at == null:
				return _nothing(r, "click on the ground")
			if draw_road == null and draw_start == null:
				draw_start = at
				r["message"] = "road started -- click to add stations, Esc or right-click to finish"
				return r
			if draw_road == null:
				var name := _free_road_name(net)
				var facing: Vector3 = at - draw_start
				facing.y = 0.0
				if facing.length() < 0.5:
					return _nothing(r, "click further from the first station")
				var g := Gestures.new_road(net, name, draw_start, facing.normalized())
				if not g["ok"]:
					r["ok"] = false
					r["message"] = g["message"]
					return r
				draw_road = g["node"]
				var second: Node3D = draw_road.points()[1]
				second.set_network_transform(Transform3D(second.network_transform().basis, at))
				draw_start = null
				r["changed"] = true
				r["select"] = [second]
				r["message"] = "new road %s" % name
				return r
			var tail: Node = draw_road.points()[-1]
			var e := Gestures.extend_road(tail)
			if not e["ok"]:
				r["ok"] = false
				r["message"] = e["message"]
				return r
			var node: Node3D = e["node"]
			node.set_network_transform(Transform3D(node.network_transform().basis, at))
			r["changed"] = true
			r["select"] = [node]
			r["message"] = "%s: %d stations" % [draw_road.name, draw_road.points().size()]
		Mode.CONNECT:
			var p := pick_point(net, cam, screen)
			if p == null:
				return _nothing(r, "click a point")
			if connect_first == null or not is_instance_valid(connect_first):
				connect_first = p
				r["select"] = [p]
				r["message"] = "now click the point to connect %s to" % p.name
				return r
			var a := connect_first
			connect_first = null
			if a == p:
				return _nothing(r, "pick two different points")
			if a.get_parent() == p.get_parent():
				var pts: Array = a.get_parent().points()
				var ends := [pts[0], pts[-1]]
				if not (ends.has(a) and ends.has(p)):
					r["ok"] = false
					r["message"] = "two points of one road connect only end to end"
					return r
				var g := Gestures.connect_points(a, p, "SEGMENT")
				r["changed"] = g["ok"]
				r["message"] = g["message"]
				return r
			var ramp_main := _aux_interior(a) if _aux_interior(a) != null else _aux_interior(p)
			if ramp_main != null:
				r["ramp"] = [a, p]
				r["message"] = "ramp"
				return r
			var g := Gestures.make_intersection([a, p])
			r["changed"] = g["ok"]
			r["ok"] = g["ok"]
			r["message"] = g["message"]
			r["select"] = [a, p]
		_:
			r["consume"] = false
	return r

## Esc or right-click: finish whatever sequence is open. True when there was one.
func finish() -> bool:
	var open := draw_road != null or draw_start != null or connect_first != null
	reset()
	return open

func _nothing(r: Dictionary, msg: String) -> Dictionary:
	r["message"] = msg
	return r

static func _free_road_name(net: Node) -> String:
	var n: int = net.roads().size()
	while net.get_node_or_null(NodePath("road_%d" % n)) != null:
		n += 1
	return "road_%d" % n

## `p` when it is an interior station of its road carrying aux lanes -- a mainline a ramp can leave from.
static func _aux_interior(p: Node) -> Node:
	var pts: Array = p.get_parent().points()
	var i := pts.find(p)
	if i <= 0 or i >= pts.size() - 1:
		return null
	return p if int(p.fields.get("aux_fwd", 0)) + int(p.fields.get("aux_bwd", 0)) > 0 else null
