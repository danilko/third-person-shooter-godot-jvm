extends SceneTree
## Road-system evaluation (PLAN.md 3.1): the SAME traffic measurement on two road systems.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_road_traffic.gd -- --scene=roadkit
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_road_traffic.gd -- --scene=debugworld
##
## roadkit    = world/hosts/RoadKitTraffic.tscn — the Blender road kit's sample network, baked.
## debugworld = world/DebugWorld.tscn — road-generator + RoadNetworkBridge.
##
## Every 0.25 s each streamed car is attributed to the lane it is on (nearest PathLaneRoute curve within
## 1.5 m), so a car's path becomes a lane sequence. Reported, not asserted: cars spawned, lane hand-overs,
## junction lanes driven (a lane with a junction_id, or a road-generator intersection lane), distinct
## junction movements, metres driven per car, cars left idle, and ZoneManager's reclaim reasons.

const SCENES := {
	"roadkit": "res://src/main/resources/com/openworld/world/hosts/RoadKitTraffic.tscn",
	"debugworld": "res://src/main/resources/com/openworld/world/DebugWorld.tscn",
}
const SECONDS := 180

var lanes: Array = []    # {name, path, junction}
var cars := {}

func _collect(n: Node) -> void:
	var s = n.get_script()
	if s != null and str(s.resource_path).ends_with("PathLaneRoute.java"):
		var p: Path3D = null
		var sp = n.get("source_path")
		if sp != null and str(sp) != "":
			p = n.get_node_or_null(sp)
		if p == null:
			p = n.get_node_or_null("Path3D")
		if p != null and p.curve != null:
			var jid := str(n.get("junction_id"))
			lanes.append({"name": str(n.name), "path": p, "junction": jid != "" or str(n.name).begins_with("cj")})
	for c in n.get_children():
		_collect(c)

func _lane_at(pos: Vector3) -> String:
	var best := ""
	var bd := 1.5
	for l in lanes:
		var path: Path3D = l["path"]
		var c: Curve3D = path.curve
		var at := path.to_global(c.sample_baked(c.get_closest_offset(path.to_local(pos))))
		var d := Vector2(at.x - pos.x, at.z - pos.z).length()
		if d < bd:
			bd = d
			best = l["name"]
	return best

func _initialize() -> void:
	var which := "roadkit"
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--scene="):
			which = a.substr(8)
	var w: Node = (load(SCENES[which]) as PackedScene).instantiate()
	root.add_child(w)
	current_scene = w
	var player: Node3D = w.get_node("Characters/Player")
	var health: Node = player.get_node("Health")
	health.set("max_health", 1000000.0)
	for i in range(20):
		await physics_frame
	var junction_names := {}
	for f in range(SECONDS * 60):
		await physics_frame
		if f % 30 == 0:
			health.call("heal", 1000000.0)
		if f % 15 != 0:
			continue
		if lanes.is_empty() or f % 600 == 0:
			lanes.clear()
			_collect(w)
			for l in lanes:
				if l["junction"]:
					junction_names[l["name"]] = true
		for v in get_nodes_in_group("streamed_vehicle"):
			var id := v.get_instance_id()
			var p: Vector3 = (v as Node3D).global_position
			if not cars.has(id):
				cars[id] = {"node": v, "seq": [], "dist": 0.0, "last": p, "idle": 0.0, "max_idle": 0.0, "mark": p}
			var c: Dictionary = cars[id]
			c["dist"] += Vector2(p.x - c["last"].x, p.z - c["last"].z).length()
			c["last"] = p
			if p.distance_to(c["mark"]) > 1.0:
				c["mark"] = p
				c["idle"] = 0.0
			else:
				c["idle"] += 0.25
				c["max_idle"] = max(c["max_idle"], c["idle"])
			var ln := _lane_at(p)
			if ln != "" and (c["seq"].is_empty() or c["seq"][-1] != ln):
				c["seq"].append(ln)
	var handovers := 0
	var junction_drives := 0
	var movements := {}
	var dists: Array = []
	var stuck := 0
	for id in cars:
		var c: Dictionary = cars[id]
		handovers += max(0, c["seq"].size() - 1)
		for n in c["seq"]:
			if junction_names.has(n):
				junction_drives += 1
				movements[n] = true
		dists.append(c["dist"])
		if c["max_idle"] > 12.0:
			stuck += 1
	dists.sort()
	var median: float = dists[dists.size() / 2] if not dists.is_empty() else 0.0
	print("ROADTRAFFIC scene=%s lanes=%d junction_lanes=%d cars=%d handovers=%d junction_drives=%d distinct_movements=%d median_drive_m=%.0f max_drive_m=%.0f stuck_cars=%d"
			% [which, lanes.size(), junction_names.size(), cars.size(), handovers, junction_drives, movements.size(),
			median, dists[-1] if not dists.is_empty() else 0.0, stuck])
	quit()
