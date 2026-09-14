@tool
extends RefCounted
## Road Kit B6c (PLAN.md 3.1): see the BUILT roads while editing. EDITOR TOOLING ONLY.
##
## A road piece is instanced by `ZoneManager` at RUNTIME, so while editing the scene shows only the
## dock's centreline overlay: none of the tarmac, kerbs, piers or zone boxes the build produced. This
## instances every ZoneMarker's geometry piece (and the network's resident piece, when the build made
## one) under ONE editor-only node that nothing saves:
##
## * the node has NO OWNER, and neither does anything under it (a piece's internals are un-owned too, so
##   the 3D editor gives them no gizmo and a click passes through to the road points) --
##   `PackedScene.pack` writes only nodes owned by the scene root, so a save writes none of it (`test_roadkit_preview.gd` asserts that, with a control that sets an owner);
## * it is `top_level`, so a child's `transform` IS its world transform, whatever the scene root does;
## * placement is `Zone.placeGeometry`'s rule, re-stated for a tool script (the Java is not `@Tool`):
##   a `geometry_world_placed` zone at `geometry_world_transform`, any other at its marker's position.
##   The resident piece `Roads_<network>` is authored in the network's frame and goes at the network.

const Zones := preload("res://addons/road_kit/road_kit_zones.gd")
const NAME := "_RoadKitPiecePreview"
const PIECES_DIR := "res://src/main/resources/com/openworld/world/pieces"

static func find(root: Node) -> Node3D:
	return root.get_node_or_null(NAME) as Node3D if root != null else null

static func clear(root: Node) -> void:
	var old := find(root)
	if old != null:
		root.remove_child(old)
		old.free()

## `{"ok", "message", "node", "pieces": [{"name", "path", "transform"}]}`. `reload` re-reads each scene
## from disk -- after a Build the cached PackedScene is the previous bake.
static func build(root: Node, net: Node3D, markers: Array, reload: bool = false) -> Dictionary:
	clear(root)
	var holder := Node3D.new()
	holder.name = NAME
	holder.top_level = true
	holder.set_meta("_road_kit_editor_only", true)
	root.add_child(holder)
	var placed := []
	var notes := []
	var seen := {}
	for m in markers:
		var zone = m.get("zone")
		if zone == null:
			continue
		var path := str(zone.get("geometry_path"))
		if path == "":
			continue
		var xf: Transform3D
		if zone.get("geometry_world_placed"):
			xf = zone.get("geometry_world_transform")
		else:
			xf = Transform3D(Basis.IDENTITY, Zones.world_xf(m).origin)
		var name := str(zone.get("zone_id"))
		if _add(holder, path, name if name != "" else str(m.name), xf, reload, placed, notes):
			seen[path] = true
	if net != null:
		var resident := PIECES_DIR.path_join("Roads_%s.tscn" % net.name)
		if not seen.has(resident) and ResourceLoader.exists(resident):
			_add(holder, resident, "resident", Zones.world_xf(net), reload, placed, notes)
	var msg := "previewing %d piece(s)" % placed.size()
	if not notes.is_empty():
		msg += " -- " + "; ".join(PackedStringArray(notes))
	return {"ok": notes.is_empty(), "message": msg, "node": holder, "pieces": placed}

static func _add(holder: Node3D, path: String, name: String, xf: Transform3D, reload: bool, placed: Array, notes: Array) -> bool:
	if not ResourceLoader.exists(path):
		notes.append("%s: no scene at %s (build first)" % [name, path])
		return false
	var mode := ResourceLoader.CACHE_MODE_REPLACE if reload else ResourceLoader.CACHE_MODE_REUSE
	var ps := ResourceLoader.load(path, "PackedScene", mode) as PackedScene
	if ps == null:
		notes.append("%s: %s is not a scene" % [name, path])
		return false
	var inst := ps.instantiate() as Node3D
	if inst == null:
		notes.append("%s: %s has no Node3D root" % [name, path])
		return false
	inst.name = name
	holder.add_child(inst)
	inst.transform = xf
	# NOT PICKABLE. A piece's internals are owned by its own root, and the 3D editor gives a gizmo -- and
	# so a click target -- to any owned node under the edited scene; a click then resolved to the nearest
	# editable ancestor, which is the SCENE ROOT, and a road point sitting on the tarmac could not be
	# clicked at all (B10.0). The preview is a picture, so nothing in it is owned.
	for n in inst.find_children("*", "", true, false):
		n.owner = null
	placed.append({"name": name, "path": path, "transform": xf})
	return true
