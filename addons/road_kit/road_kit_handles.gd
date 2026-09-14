@tool
extends RefCounted
## Road Kit B10.4: the intersection HANDLES' logic -- which handles a point offers, where each is drawn, and
## what dragging one does -- apart from the editor gizmo (road_kit_gizmo.gd), which only draws them and
## turns a mouse drag into a ray. An `EditorNode3DGizmoPlugin` cannot be instantiated outside the editor,
## so the logic lives here, where `test_roadkit_handles.gd` runs exactly what a drag runs. EDITOR TOOLING.

const Gestures := preload("res://addons/road_kit/road_kit_gestures.gd")
const HANDLE_OUT := 0
const HANDLE_IN := 1
const HANDLE_SETBACK := 2
const HANDLE_LANES_FWD := 3
const HANDLE_LANES_BWD := 4
const HANDLE_FILLET := 5
const HANDLE_JCT_MOVE := 6
const HANDLE_JCT_ROTATE := 7
const NAMES := ["handle_out", "handle_in", "setback", "lanes_fwd", "lanes_bwd", "fillet_radius", "move junction", "rotate junction"]
## Where a bend handle whose length is 0 (the chord) is drawn, so it can be grabbed at all.
const IDLE_HANDLE := 6.0
## The setback handle sits this far up the point's post, clear of the editor's own move gizmo.
const SETBACK_LIFT := 2.5
## The junction rotate handle's distance from the pad centre.
const ROTATE_RADIUS := 10.0

## The drag in progress: {"uid", "id", "record", "starts", "members", "angle"}.
var drag := {}

## Which handles a point offers: every point its two bend lengths and two lane counts; a junction mouth
## also its setback, fillet and the junction's move and rotate.
static func ids_for(point: Node) -> Array:
	var ids := [HANDLE_OUT, HANDLE_IN, HANDLE_LANES_FWD, HANDLE_LANES_BWD]
	if Gestures.is_mouth(point):
		ids.append_array([HANDLE_SETBACK, HANDLE_FILLET, HANDLE_JCT_MOVE, HANDLE_JCT_ROTATE])
	return ids

static func members_of(p: Node) -> Array:
	var m: Array = Gestures.junction_members(p)
	return m if not m.is_empty() else [p]

## Where handle `id` of `p` is drawn, in the point's LOCAL frame.
func position(p: Node3D, id: int) -> Vector3:
	match id:
		HANDLE_OUT:
			return Vector3(0, 0, -draw_length(float(p.fields.get("handle_out", 0.0))))
		HANDLE_IN:
			return Vector3(0, 0, draw_length(float(p.fields.get("handle_in", 0.0))))
		HANDLE_SETBACK:
			return Vector3(0, SETBACK_LIFT, 0)
		HANDLE_LANES_FWD, HANDLE_LANES_BWD:
			var fwd := id == HANDLE_LANES_FWD
			var sec := Gestures.section_of(p)
			var off := Gestures.lane_edge_offset(sec, int(sec["lanes_fwd" if fwd else "lanes_bwd"]), fwd)
			return Vector3(-off if fwd else off, 0.3, 0)
	var inv: Transform3D = p.network_transform().affine_inverse()
	var centre := Gestures.junction_centre(members_of(p))
	match id:
		HANDLE_FILLET:
			var local_c := inv * centre
			var toward := -1.0 if local_c.z < 0.0 else 1.0
			var sec := Gestures.section_of(p)
			return Vector3(Gestures.lane_edge_offset(sec, int(sec["lanes_bwd"]), false), 0.3, toward * float(p.fields.get("fillet_radius", 6.0)))
		HANDLE_JCT_MOVE:
			return inv * (centre + Vector3.UP)
		HANDLE_JCT_ROTATE:
			var ang: float = drag.get("angle", 0.0) if drag.get("uid", "") == p.uid else 0.0
			return inv * (centre + Vector3.UP + Basis(Vector3.UP, ang) * Vector3(ROTATE_RADIUS, 0, 0))
	return Vector3.ZERO

## The state a drag of `handle_id` is applied relative to. Idempotent for one drag.
func begin(p: Node, handle_id: int) -> Dictionary:
	if drag.get("uid", "") == p.uid and drag.get("id", -1) == handle_id:
		return drag
	var net := Gestures.network_of(p)
	var members := members_of(p) if handle_id in [HANDLE_JCT_MOVE, HANDLE_JCT_ROTATE] else [p]
	drag = {"uid": p.uid, "id": handle_id, "record": net.to_record(), "members": members,
			"starts": Gestures.junction_starts(members), "angle": 0.0}
	return drag

## Apply a drag of handle `handle_id` of `p` to the mouse ray `from`/`dir` (NETWORK frame). Every drag is
## projected onto the horizontal plane through the point (or the pad centre). Returns the nodes it moved.
func drag_to(p: Node, handle_id: int, from: Vector3, dir: Vector3) -> Array:
	var st := begin(p, handle_id)
	var start: Transform3D = st["starts"][p.uid][0]
	var members: Array = st["members"]
	var pivot := start.origin
	if handle_id in [HANDLE_JCT_MOVE, HANDLE_JCT_ROTATE]:
		pivot = Vector3.ZERO
		for m in members:
			pivot += (st["starts"][m.uid][0] as Transform3D).origin
		pivot /= maxf(1.0, members.size())
	var hit = plane_hit(from, dir, pivot.y)
	if hit == null:
		return []
	match handle_id:
		HANDLE_SETBACK:
			var axis := -start.basis.z
			axis.y = 0.0
			Gestures.slide_along_axis(p, start, snappedf((hit - start.origin).dot(axis.normalized()), 0.1))
		HANDLE_LANES_FWD, HANDLE_LANES_BWD:
			var fwd := handle_id == HANDLE_LANES_FWD
			var lat := -start.basis.x if fwd else start.basis.x
			lat.y = 0.0
			var n := Gestures.lanes_for_offset(Gestures.section_of(p), (hit - start.origin).dot(lat.normalized()), fwd)
			var other := int(p.fields["lanes_bwd" if fwd else "lanes_fwd"])
			p.fields["lanes_fwd" if fwd else "lanes_bwd"] = maxi(n, 1 if other == 0 else 0)
			p._edited()
		HANDLE_FILLET:
			var inv := start.affine_inverse()
			var local_hit: Vector3 = inv * hit
			var local_c: Vector3 = inv * Gestures.junction_centre(members_of(p))
			var toward := -1.0 if local_c.z < 0.0 else 1.0
			p.fields["fillet_radius"] = maxf(0.5, snappedf(local_hit.z * toward, 0.5))
			p._edited()
		HANDLE_JCT_MOVE:
			var d: Vector3 = hit - pivot
			d.y = 0.0
			Gestures.junction_translate(members, st["starts"], d.snapped(Vector3(0.1, 0.1, 0.1)))
		HANDLE_JCT_ROTATE:
			var v: Vector3 = hit - pivot
			var ang := snappedf(atan2(-v.z, v.x), deg_to_rad(1.0))
			st["angle"] = ang
			Gestures.junction_rotate(members, st["starts"], pivot, ang)
	return members

## End a drag. On `cancel` the record it started from is put back and `{}` is returned; otherwise
## `{"net", "before", "after", "name"}` for ONE undo step.
func end(p: Node, handle_id: int, cancel: bool) -> Dictionary:
	var st := begin(p, handle_id)
	var net: Node = Gestures.network_of(p)
	var before: Dictionary = st["record"]
	drag = {}
	if cancel:
		net.from_record(before)
		return {}
	return {"net": net, "before": before, "after": net.to_record(), "name": NAMES[handle_id]}

## Where the ray `from` + t*`dir` crosses the horizontal plane at height `y`, or null when it runs along it
## or away from it.
static func plane_hit(from: Vector3, dir: Vector3, y: float):
	if absf(dir.y) < 1e-6:
		return null
	var t := (y - from.y) / dir.y
	if t < 0.0:
		return null
	return from + dir * t

## Where a bend handle of authored length `length` is drawn: the length itself, or IDLE_HANDLE for 0 (chord).
static func draw_length(length: float) -> float:
	return length if length > 0.05 else IDLE_HANDLE

## The bend-handle length a mouse ray asks for: the parameter along `axis` (from `origin`) of the point on
## that axis closest to the ray -- a length, clamped at 0 so a handle cannot be dragged through its point.
static func handle_length(origin: Vector3, axis: Vector3, ray_from: Vector3, ray_dir: Vector3) -> float:
	var a := axis.normalized()
	var d := ray_dir.normalized()
	var w := origin - ray_from
	var b := a.dot(d)
	var denom := 1.0 - b * b
	if denom < 1e-6:
		return 0.0              # the ray runs along the axis: no closest point, keep the chord
	var t := (b * d.dot(w) - a.dot(w)) / denom
	return maxf(0.0, t)
