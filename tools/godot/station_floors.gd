extends SceneTree
## WHERE CAN A BODY STAND IN THIS BUILDING? Lists sample walkable points per floor height, in WORLD coordinates when
## the building's World.tscn placement is given, so a probe's --at point is measured rather than guessed (2026-10-08:
## a station's place point is its track centre, and a guessed platform point landed in a lift car).
##
##   godot --headless --path . --script tools/godot/station_floors.gd -- --scene=Station_Bay_Shop \
##       [--origin=205,5.74,135 --yaw=90] [--step=4]
## Rays straight down every --step metres over the scene's AABB; each hit's height is binned to 0.5 m; per bin the
## count and up to 5 sample points (spread along the building) are printed, plus what the hit collider is.
const DIR := "res://src/main/resources/com/openworld/world/buildings/"

func _arg(k: String, d: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--" + k + "="):
			return a.substr(k.length() + 3)
	return d

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var sc: Node3D = (load(DIR + _arg("scene", "Station_Bay_Shop") + ".tscn") as PackedScene).instantiate()
	var o := _arg("origin", "0,0,0").split(",")
	var origin := Vector3(float(o[0]), float(o[1]), float(o[2]))
	var yaw := deg_to_rad(float(_arg("yaw", "0")))
	var step := float(_arg("step", "4"))
	var w := Node3D.new()
	root.add_child(w)
	w.add_child(sc)
	sc.global_transform = Transform3D(Basis(Vector3.UP, yaw), origin)
	for i in 4:
		await physics_frame
	var meta: Dictionary = sc.get_meta("building", {})
	var bb: Array = meta.get("aabb", [Vector3(-60, -10, -40), Vector3(120, 30, 80)])
	var lo: Vector3 = bb[0]
	var size: Vector3 = bb[1]
	var space := sc.get_world_3d().direct_space_state
	var bins := {}
	var x := lo.x + 1.0
	while x < lo.x + size.x:
		var z := lo.z + 1.0
		while z < lo.z + size.z:
			var top := lo.y + size.y + 1.0
			var guard := 0
			while top > lo.y - 1.0 and guard < 8:
				guard += 1
				var a := sc.global_transform * Vector3(x, top, z)
				var b := sc.global_transform * Vector3(x, lo.y - 1.0, z)
				var q := PhysicsRayQueryParameters3D.create(a, b, 1)
				var h := space.intersect_ray(q)
				if h.is_empty():
					break
				var p: Vector3 = h["position"]
				var nrm: Vector3 = h["normal"]
				if nrm.y > 0.8:
					var k := snappedf(p.y, 0.5)
					if not bins.has(k):
						bins[k] = []
					(bins[k] as Array).append([p, str((h["collider"] as Node).name)])
				top = (sc.global_transform.affine_inverse() * p).y - 0.3
			z += step
		x += step
	var keys := bins.keys()
	keys.sort()
	for k in keys:
		var arr: Array = bins[k]
		var picks := []
		for i in 5:
			picks.append(arr[int(float(i) / 5.0 * arr.size())])
		var txt := ""
		for e in picks:
			var p: Vector3 = e[0]
			txt += " (%.1f,%.2f,%.1f)%s" % [p.x, p.y, p.z, e[1]]
		print("y %6.2f  %4d hits:%s" % [k, arr.size(), txt])
	quit(0)
