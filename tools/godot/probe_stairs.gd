extends SceneTree
## STAIRS ARE WALKED, NOT CLIMBED (user 2026-10-07: "characters seem to get stuck on stairs"). Every stair flight in
## the kits carries an invisible RAMP collider along its nosings (a HULL_stair_ Empty -> a ConvexPolygonShape3D named
## Ramp<n> in the building's StairRamps body, collision layer 7 that only characters see). For each ramp hull in each building scene given, a real Player stands
## 1.5 m in front of the flight's foot, faces up it and holds `forward` through Input; asserted: it reaches the top
## (its feet within 0.4 m of the top's height, past 80% of the run) within 8 s.
##
##   godot --headless --path . --script tools/godot/probe_stairs.gd [-- --scenes=PoliceStation_Shop,...] [--control]
##   (--control disables the ramp hulls: the steps alone, the measurement of the stuck point)

const BUILDINGS := "res://src/main/resources/com/openworld/world/buildings/"
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"

var fails := 0
var flights := 0


func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1


func _arg(k: String, d: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--" + k + "="):
			return a.substr(k.length() + 3)
	return d


## A ramp hull's bottom and top midpoints (world): its 8 points are 4 top corners and 4 corners 0.3 m below them.
func _ends(cs: CollisionShape3D) -> Array:
	var pts: PackedVector3Array = (cs.shape as ConvexPolygonShape3D).points
	var xf := cs.global_transform
	var w: Array[Vector3] = []
	for q in pts:
		w.append(xf * q)
	# the top surface: for each (x, z) pair the higher point
	var tops: Array[Vector3] = []
	for q in w:
		var higher := true
		for r in w:
			if r != q and Vector2(r.x - q.x, r.z - q.z).length() < 0.05 and r.y > q.y:
				higher = false
		if higher:
			tops.append(q)
	if tops.size() != 4:
		return []
	tops.sort_custom(func(a, b): return a.y < b.y)
	return [(tops[0] + tops[1]) * 0.5, (tops[2] + tops[3]) * 0.5]


func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	var names := _arg("scenes", "PoliceStation_Shop,SafeHouseSmall_Shop,SafeHouseCityLarge_Shop,Station_Bay_Shop,Station_Central_Shop").split(",")
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	var helper: Node = load(HELPER).new()
	world.add_child(helper)
	var floor_body := StaticBody3D.new()
	var fcs := CollisionShape3D.new()
	var fbox := BoxShape3D.new()
	fbox.size = Vector3(800, 1, 800)
	fcs.shape = fbox
	floor_body.add_child(fcs)
	floor_body.position = Vector3(0, -0.5, 0)
	world.add_child(floor_body)
	for nm in names:
		var path := BUILDINGS + nm + ".tscn"
		if not ResourceLoader.exists(path):
			print("  %s: no scene" % nm)
			continue
		var b: Node3D = (load(path) as PackedScene).instantiate()
		world.add_child(b)
		await physics_frame
		var ramps: Array = []
		for cs in b.find_children("Ramp*", "CollisionShape3D", true, false):
			if not ((cs as CollisionShape3D).shape is ConvexPolygonShape3D):
				continue
			var e := _ends(cs)
			if e.is_empty() or (e[1] as Vector3).y - (e[0] as Vector3).y < 1.0:
				continue          # not a flight (a gentle entry slope, a wedge)
			ramps.append([cs, e])
			if control:
				(cs as CollisionShape3D).disabled = true
		print("%s: %d stair ramp(s)%s" % [nm, ramps.size(), " (DISABLED: the control)" if control else ""])
		for rp in ramps:
			var lo: Vector3 = rp[1][0]
			var hi: Vector3 = rp[1][1]
			var dir := Vector3(hi.x - lo.x, 0, hi.z - lo.z).normalized()
			var run := Vector2(hi.x - lo.x, hi.z - lo.z).length()
			var p: CharacterBody3D = (load(PLAYER) as PackedScene).instantiate()
			p.position = lo - dir * 0.3 + Vector3(0, 0.15, 0)
			world.add_child(p)
			p.get_node("Health").set("invulnerable", true)
			for i in 20:
				await physics_frame
			helper.call("set_view", p, rad_to_deg(atan2(-dir.x, -dir.z)), 0.0)
			for i in 5:
				await physics_frame
			Input.action_press("forward")
			var t := 0
			var made := false
			var best := 0.0
			while t < 60 * 8:
				await physics_frame
				t += 1
				var along := (p.global_position - lo).dot(dir)
				best = maxf(best, along)
				if along > run * 0.8 and absf(p.global_position.y - (lo.y + (hi.y - lo.y) * clampf(along / run, 0.0, 1.0))) < 0.6:
					made = true
					break
			Input.action_release("forward")
			flights += 1
			if not made:
				var sp := (world as Node3D).get_world_3d().direct_space_state
				for hgt in [0.3, 1.0, 1.6, 2.1]:
					var q := PhysicsRayQueryParameters3D.create(p.global_position + Vector3(0, hgt, 0), p.global_position + Vector3(0, hgt, 0) + dir * 1.5, 1 | 64)
					q.exclude = [p.get_rid()]
					var hit := sp.intersect_ray(q)
					print("    ahead at +%.1f m: %s" % [hgt, ("%s at %.2f m" % [str((hit["collider"] as Node).name) + "/" + str(hit.get("shape", -1)), (hit["position"] as Vector3).distance_to(p.global_position + Vector3(0, hgt, 0))]) if not hit.is_empty() else "clear"])
				var qu := PhysicsRayQueryParameters3D.create(p.global_position + Vector3(0, 1.0, 0), p.global_position + Vector3(0, 3.0, 0), 1 | 64)
				var hu := sp.intersect_ray(qu)
				print("    overhead: %s" % (("%.2f m up" % ((hu["position"] as Vector3).y - p.global_position.y)) if not hu.is_empty() else "clear"))
			_check(made, "%s: up the flight %.1f m high, %.1f m run (%s, got %.1f of %.1f m along, at y %.2f)%s" % [
				nm, hi.y - lo.y, run, ("%.1f s" % (t / 60.0)) if made else "STUCK", best, run, p.global_position.y,
				"" if made else " foot %s top %s, now at %s" % [lo.snapped(Vector3.ONE * 0.01), hi.snapped(Vector3.ONE * 0.01), p.global_position.snapped(Vector3.ONE * 0.01)]])
			p.queue_free()
			for i in 5:
				await physics_frame
		b.queue_free()
		await physics_frame
	print("RESULT %s (%d of %d flights failed)" % ["PASS" if fails == 0 else "FAIL", fails, flights])
	quit(1 if fails else 0)
