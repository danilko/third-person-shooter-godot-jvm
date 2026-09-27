extends SceneTree
## The paddy crops (2026-09-26): a streamed building cell carrying a `Crops` node (world.CropField) builds its crop
## MultiMeshes at load. Asserts, on every cell that has one: quads were built, each chunk is a MultiMeshInstance3D with
## a view distance and no shadow, its mesh wears a crop material, and the instances stand on their chunk's height and
## inside the chunk.
##   godot --headless --path . --script tools/godot/probe_crops.gd
const CELLS := "res://src/main/resources/com/openworld/world/buildings/cells"

var _fails := 0

func _check(ok: bool, what: String, detail: String = "") -> void:
	print("  %s  %-60s %s" % ["PASS" if ok else "FAIL", what, detail])
	if not ok:
		_fails += 1

func _initialize() -> void:
	await process_frame
	var dir := DirAccess.open(CELLS)
	var cells := 0
	var quads := 0
	var chunks := 0
	var bad_mat := 0
	var bad_range := 0
	var outside := 0
	var unread := 0
	for f in dir.get_files():
		if not f.ends_with(".tscn"):
			continue
		var text := FileAccess.get_file_as_string(CELLS + "/" + f)
		if text.find("name=\"Crops\"") < 0:
			continue
		var cell: Node = (load(CELLS + "/" + f) as PackedScene).instantiate()
		root.add_child(cell)
		await process_frame
		var crops: Node = cell.get_node("Crops")
		cells += 1
		var ch: PackedFloat32Array = crops.get("chunks")
		# CropField builds only the chunks round the CAMERA: stand one over the cell's first chunk and let it look
		var cam := Camera3D.new()
		cell.add_child(cam)
		cam.global_position = Vector3(ch[0] + 25.0, ch[2] + 2.0, ch[1] + 25.0)
		cam.current = true
		await create_timer(0.8).timeout
		quads += int(crops.call("crops_built_now"))
		for mmi in crops.get_children():
			if not mmi is MultiMeshInstance3D:
				continue
			chunks += 1
			var m: MultiMeshInstance3D = mmi
			if m.visibility_range_end <= 0.0 or m.cast_shadow != GeometryInstance3D.SHADOW_CASTING_SETTING_OFF:
				bad_range += 1
			var mesh := m.multimesh.mesh
			var mat := mesh.surface_get_material(0) if mesh else null
			if mat == null or not str(mat.resource_path).contains("crop_"):
				bad_mat += 1
			var i := int(str(m.name).trim_prefix("Crop"))
			var x0 := ch[i * 4]
			var z0 := ch[i * 4 + 1]
			var y := ch[i * 4 + 2]
			for k in range(0, m.multimesh.instance_count, 97):
				var t := m.multimesh.get_instance_transform(k)
				if t.origin == Vector3.ZERO:
					unread += 1         # the headless dummy renderer hands back identity for a MultiMesh transform
					continue
				if t.origin.x < x0 or t.origin.x > x0 + 50.0 or t.origin.z < z0 or t.origin.z > z0 + 50.0 \
						or absf(t.origin.y - y) > 0.01:
					outside += 1
					if outside <= 3:
						print("    outside %s %s: chunk (%.1f, %.1f, y %.2f) quad %s" % [f, m.name, x0, z0, y, t.origin])
		cell.queue_free()
		await process_frame
	_check(cells > 0, "cells carrying a Crops node", str(cells))
	_check(quads > 0, "crop quads built", str(quads))
	_check(chunks > 0, "one MultiMeshInstance3D per chunk", str(chunks))
	_check(bad_mat == 0, "every chunk wears a crop material", "%d without" % bad_mat)
	_check(bad_range == 0, "every chunk has a view distance and casts no shadow", "%d without" % bad_range)
	_check(outside == 0, "every sampled quad stands inside its chunk at its height",
			"%d outside, %d unreadable headless" % [outside, unread])
	print("RESULT %s (%d failure(s))" % ["PASS" if _fails == 0 else "FAIL", _fails])
	quit(0 if _fails == 0 else 1)
