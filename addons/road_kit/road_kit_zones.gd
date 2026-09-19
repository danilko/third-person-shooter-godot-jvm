@tool
extends RefCounted
## Road Kit B6 (PLAN.md 3.1): the scene's ZoneMarkers -> the zones sidecar the solver cuts a network
## by, and the built pieces -> each marker's Zone. EDITOR TOOLING ONLY.
##
## Which zone a run, pad or gore goes with is decided in ONE place, `point_zones.py`, and never here:
## this file only states where the zones ARE (in the network's frame, in the kit's axes) and writes
## back what the build reports. Pure static functions over nodes, so a headless test drives exactly
## what the dock does.

const Frame := preload("res://addons/road_kit/road_kit_frame.gd")
const SCHEMA_VER := 1
const MARKER_SCRIPT := "ZoneMarker.java"

static func is_marker(n: Node) -> bool:
	var s = n.get_script()
	return s != null and str(s.resource_path).ends_with(MARKER_SCRIPT)

static func markers_in(root: Node) -> Array:
	var out := []
	if root == null:
		return out
	if is_marker(root):
		out.append(root)
	for c in root.get_children():
		out.append_array(markers_in(c))
	return out

## A node's transform in the world, composed up its Node3D ancestors — so it answers the same inside
## the editor, in a running tree and on a node that was never added to one.
static func world_xf(n: Node) -> Transform3D:
	var xf := Transform3D.IDENTITY
	var cur := n
	while cur != null:
		if cur is Node3D:
			xf = (cur as Node3D).transform * xf
		cur = cur.get_parent()
	return xf

## The sidecar's path for a record: `X.roads.json` -> `X.zones.json`.
static func sidecar_path(record_path: String) -> String:
	var base := record_path
	if base.ends_with(".roads.json"):
		base = base.substr(0, base.length() - ".roads.json".length())
	else:
		base = base.get_basename()
	return base + ".zones.json"

## A zone that takes no part in the road cut: one that only spawns traffic (vehicle configs, no geometry, no
## AI), or a SITE zone that streams a building scene (`tools/island_sites.py`). (A zone that streams a piece AND
## spawns traffic, like DebugWorld's `debug_a`, is a road zone.)
static func is_traffic_only(zone) -> bool:
	var geo := str(zone.get("geometry_path"))
	# a SITE zone streams a building scene (tools/island_sites.py), not a road piece: its box must not claim roads
	if geo.contains("/world/buildings/"):
		return true
	if geo != "":
		return false
	var vcs = zone.get("vehicle_spawn_configs")
	var scs = zone.get("spawn_configs")
	var ncs = zone.get("named_characters")
	return vcs != null and vcs.size() > 0 and (scs == null or scs.size() == 0) \
			and (ncs == null or ncs.size() == 0)

## `{"schema_ver", "zones": [...], "warnings": [...]}` — each marker's centre in the NETWORK's frame
## (the frame the record is written in) converted to the kit's axes, and the XZ footprint of
## `Zone.size` as kit `half = [x, y]`. A box is axis-aligned in the network frame, so a network turned
## against its zones is reported rather than silently cut on the wrong axes.
static func zones_record(net: Node3D, markers: Array) -> Dictionary:
	var zones := []
	var warnings := []
	var seen := {}
	var net_inv := world_xf(net).affine_inverse()
	for m in markers:
		var zone = m.get("zone")
		if zone == null:
			warnings.append("%s has no Zone -- ignored" % m.name)
			continue
		var zid := str(zone.get("zone_id"))
		if is_traffic_only(zone):
			# A traffic zone (`tools/island_traffic_zones.py`) is a spawn source around a junction
			# cluster, with a 60 m box: in the cut it would be the SMALLEST box holding those stations
			# and take the island's pads away from their road cells. It owns no road.
			continue
		if zid == "":
			warnings.append("%s's Zone has no zone_id -- ignored" % m.name)
			continue
		if seen.has(zid):
			warnings.append("%s repeats zone_id '%s' (first on %s) -- ignored" % [m.name, zid, seen[zid]])
			continue
		seen[zid] = m.name
		var local := net_inv * world_xf(m)
		var yaw := absf(rad_to_deg(local.basis.get_euler().y))
		if fmod(yaw, 90.0) > 1.0 and fmod(yaw, 90.0) < 89.0:
			warnings.append("%s is turned %.0f deg against the network -- its box is cut axis-aligned in the network frame" % [m.name, yaw])
		var k := Frame.to_kit(local.origin)
		var size: Vector3 = zone.get("size")
		zones.append({"zone_id": zid, "centre": Frame.to_array(k),
				"half": [snappedf(size.x * 0.5, 0.000001), snappedf(size.z * 0.5, 0.000001)],
				"load_radius": float(zone.get("load_radius")), "unload_radius": float(zone.get("unload_radius")),
				"marker": str(m.name)})
	return {"schema_ver": SCHEMA_VER, "zones": zones, "warnings": warnings}

static func write_sidecar(path: String, record: Dictionary) -> Error:
	var d := record.duplicate()
	d.erase("warnings")
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f == null:
		return FileAccess.get_open_error()
	f.store_string(JSON.stringify(d, " ", true) + "\n")
	return OK

## The last `ROADKIT_PIECES {...}` line of a build log, parsed; `[]` when there is none.
static func pieces_from_log(log_text: String) -> Array:
	var lines := log_text.split("\n")
	for i in range(lines.size() - 1, -1, -1):
		if lines[i].begins_with("ROADKIT_PIECES "):
			var d = JSON.parse_string(lines[i].substr("ROADKIT_PIECES ".length()))
			if typeof(d) == TYPE_DICTIONARY:
				return d.get("pieces", [])
	return []

## What wiring the built `pieces` into the markers would change, WITHOUT changing it:
## `{"changes": [{"zone": Resource, "marker": name, "property": p, "old": v, "new": v}], "notes": [...]}`.
## The dock applies the changes as one undo action; a test applies them directly.
##
## A marker's Zone takes its piece's scene and the network's world transform. A Zone whose
## `geometry_path` already names something that is NOT one of this network's road pieces keeps it
## (one geometry per zone; that zone's roads are reported, not wired over a district). A Zone that
## held one of this network's pieces and received none this build is CLEARED — the stale piece file
## would otherwise stream roads that are no longer there.
static func plan_wiring(net: Node3D, markers: Array, pieces: Array, prefix: String) -> Dictionary:
	var changes := []
	var notes := []
	var by_zone := {}
	for p in pieces:
		by_zone[str(p["zone"])] = p
	var net_xf := world_xf(net)
	for m in markers:
		var zone = m.get("zone")
		if zone == null or str(zone.get("zone_id")) == "":
			continue
		var zid := str(zone.get("zone_id"))
		var current := str(zone.get("geometry_path"))
		var ours := current == "" or current.get_file().get_basename() == prefix \
				or current.get_file().begins_with(prefix + "_")
		if not by_zone.has(zid):
			if current != "" and ours:
				_change(changes, zone, m, "geometry_path", current, "")
				_change(changes, zone, m, "geometry_world_placed", zone.get("geometry_world_placed"), false)
				notes.append("%s: no roads this build -- cleared %s" % [zid, current])
			continue
		var scene := str(by_zone[zid]["scene"])
		by_zone.erase(zid)
		if not ours:
			notes.append("%s already streams %s -- its road piece %s is NOT wired (one geometry per zone)" % [zid, current, scene])
			continue
		if zone.get("geometry") != null:
			notes.append("%s has a directly-assigned geometry scene, which wins over geometry_path -- clear it to stream %s" % [zid, scene])
		_change(changes, zone, m, "geometry_path", current, scene)
		_change(changes, zone, m, "geometry_world_placed", zone.get("geometry_world_placed"), true)
		_change(changes, zone, m, "geometry_world_transform", zone.get("geometry_world_transform"), net_xf)
	for zid in by_zone:
		if zid == "":
			notes.append("%s holds the roads in no zone and no marker streams it -- instance it in the scene, or cover those roads with a zone" % by_zone[zid]["piece"])
		else:
			notes.append("zone '%s' got %s but has no marker in this scene" % [zid, by_zone[zid]["piece"]])
	return {"changes": changes, "notes": notes}

static func _change(changes: Array, zone, marker: Node, prop: String, old, new) -> void:
	if typeof(old) == typeof(new) and (old.is_equal_approx(new) if old is Transform3D else old == new):
		return
	changes.append({"zone": zone, "marker": str(marker.name), "property": prop, "old": old, "new": new})

static func apply_wiring(plan: Dictionary) -> void:
	for c in plan["changes"]:
		c["zone"].set(c["property"], c["new"])
