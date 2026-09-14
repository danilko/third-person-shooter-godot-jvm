extends SceneTree
## PLAN.md 3.1 B10.3 gate: the viewport TOOL MODE, through the same `road_kit_tool.gd` `click` the plugin's
## `_forward_3d_gui_input` runs, with a real Camera3D looking down on the network.
##   godot --headless --path . --script tools/godot/test_roadkit_tool.gd
##
##   * picking: a click on a point's screen position picks it, 30 px off picks nothing;
##   * SELECT: a click on a centreline selects its road; Alt-click on a mouth selects its whole junction;
##   * INSERT: a click mid-span adds ONE station to that road, at the click, and the kit's gate stays at 0
##     errors;
##   * DELETE: a click on a point removes it;
##   * DRAW: three clicks on the ground make a 3-station road at the clicks (drape height); Esc finishes, and
##     the next click starts a new road rather than extending the old one;
##   * CONNECT: two ends of one road join by a SEGMENT; two points of different roads make a junction;
##   * on DebugWorld the ground is TERRAIN3D's natural ground: a drawn station lands at its natural height
##     plus the drape, wherever the stamped surface is.

const NetworkScript := preload("res://addons/road_kit/road_kit_network.gd")
const Gestures := preload("res://addons/road_kit/road_kit_gestures.gd")
const Service := preload("res://addons/road_kit/road_kit_service.gd")
const Ground := preload("res://addons/road_kit/road_kit_ground.gd")
const Tool := preload("res://addons/road_kit/road_kit_tool.gd")
const SAMPLE := "res://assets/world_source/pieces/RoadKitSample.roads.json"
const SCRATCH := "user://test_roadkit_tool.roads.json"
const WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"

var fails := 0

func check(ok: bool, what: String, detail: String = "") -> void:
	print("  %s  %-70s %s" % ["PASS" if ok else "FAIL", what, detail])
	fails += 0 if ok else 1

func _runs(net: Node) -> Array:
	net.save_record(SCRATCH, true)
	var r := Service.run("centrelines", SCRATCH)
	return r.get("runs", [])

func _gate(net: Node) -> int:
	net.save_record(SCRATCH, true)
	var r := Service.run("validate", SCRATCH)
	return -1 if r.get("failed", false) else int(r["errors"])

func _camera_over(net: Node3D, height: float) -> Camera3D:
	var c := Vector3.ZERO
	for p in net.all_points():
		c += p.global_position
	c /= maxf(1.0, net.all_points().size())
	var cam := Camera3D.new()
	root.add_child(cam)
	cam.far = 20000.0
	cam.global_transform = Transform3D(Basis.looking_at(Vector3.DOWN, Vector3.FORWARD), c + Vector3.UP * height)
	cam.make_current()
	return cam

func _initialize() -> void:
	var net: Node3D = NetworkScript.new()
	root.add_child(net)
	net.record_path = SCRATCH
	net.from_record(JSON.parse_string(FileAccess.get_file_as_string(SAMPLE)))
	await process_frame
	var cam := _camera_over(net, 900.0)
	await process_frame
	var tool = Tool.new()
	var ctx := {"net": net, "camera": cam, "terrain": null, "runs": _runs(net), "alt": false}

	# ── picking ──
	var p0: Node3D = net.all_points()[3]
	var s0 := cam.unproject_position(p0.global_position)
	check(Tool.pick_point(net, cam, s0) == p0, "a click on a point picks it")
	check(Tool.pick_point(net, cam, s0 + Vector2(30, 30)) == null or Tool.pick_point(net, cam, s0 + Vector2(30, 30)) != p0, "30 px away does not pick it")

	# ── SELECT ──
	tool.set_mode(Tool.Mode.SELECT)
	var run: Dictionary = {}
	for r in ctx["runs"]:
		if (r["uids"] as Array).size() >= 3:
			run = r
			break
	var mid: Array = run["points"][run["points"].size() / 3]
	var mid_w: Vector3 = net.global_transform * Vector3(mid[0], mid[1], mid[2])
	var sel: Dictionary = tool.click(ctx, cam.unproject_position(mid_w))
	check(sel["select"].size() == 1 and String(sel["select"][0].name) == run["road"], "SELECT: a centreline click selects its road", str(run["road"]))
	var mouth: Node = null
	for p in net.all_points():
		if Gestures.is_mouth(p):
			mouth = p
			break
	ctx["alt"] = true
	var jsel: Dictionary = tool.click(ctx, cam.unproject_position(mouth.global_position))
	ctx["alt"] = false
	check(jsel["select"].size() == Gestures.junction_members(mouth).size() and jsel["select"].size() >= 2, "SELECT: Alt-click on a mouth selects its junction", "%d mouths" % jsel["select"].size())

	# ── INSERT ──
	tool.set_mode(Tool.Mode.INSERT)
	var road: Node = net.get_node(NodePath(str(run["road"])))
	var n_before: int = road.points().size()
	var ins: Dictionary = tool.click(ctx, cam.unproject_position(mid_w))
	var new_pt: Node3D = ins["select"][0] if not ins["select"].is_empty() else null
	var err := _gate(net)
	check(ins["changed"] and road.points().size() == n_before + 1 and new_pt != null
			and Vector2(new_pt.global_position.x - mid_w.x, new_pt.global_position.z - mid_w.z).length() < 1.0 and err == 0,
			"INSERT: a centreline click adds one station there, gate still 0 errors", "%d -> %d stations, %d error(s)" % [n_before, road.points().size(), err])
	ctx["runs"] = _runs(net)

	# ── DELETE ──
	tool.set_mode(Tool.Mode.DELETE)
	var victim_uid: String = new_pt.uid
	var del: Dictionary = tool.click(ctx, cam.unproject_position(new_pt.global_position))
	check(del["changed"] and net.find_point(victim_uid) == null and road.points().size() == n_before, "DELETE: a click on a point removes it")
	ctx["runs"] = _runs(net)

	# ── DRAW on the network's own plane ──
	tool.set_mode(Tool.Mode.DRAW)
	var roads_before: int = net.roads().size()
	var origin := cam.global_position * Vector3(1, 0, 1)
	var clicks := [origin + Vector3(-300, 0, 600), origin + Vector3(-250, 0, 640), origin + Vector3(-200, 0, 660)]
	for w in clicks:
		tool.click(ctx, cam.unproject_position(w))
	var drawn: Node = tool.draw_road
	var at_clicks: bool = drawn != null and drawn.points().size() == 3
	if at_clicks:
		for i in 3:
			var q: Vector3 = drawn.points()[i].global_position
			at_clicks = at_clicks and Vector2(q.x - clicks[i].x, q.z - clicks[i].z).length() < 0.5 and absf(q.y - Tool.DRAPE) < 1e-3
	check(net.roads().size() == roads_before + 1 and at_clicks, "DRAW: three ground clicks make a 3-station road at the clicks")
	check(tool.finish() and tool.draw_road == null, "DRAW: Esc finishes the road")
	tool.click(ctx, cam.unproject_position(origin + Vector3(300, 0, 600)))
	check(drawn.points().size() == 3 and tool.draw_start != null, "DRAW: the next click starts a NEW road, the old one is untouched")
	tool.finish()

	# ── CONNECT ──
	tool.set_mode(Tool.Mode.CONNECT)
	var ends: Array = drawn.points()
	tool.click(ctx, cam.unproject_position(ends[0].global_position))
	var seg: Dictionary = tool.click(ctx, cam.unproject_position(ends[-1].global_position))
	var linked: bool = ends[0].links.any(func(l): return l["target"] == ends[-1].uid and l["type"] == "SEGMENT")
	check(seg["changed"] and linked, "CONNECT: two ends of one road join by a SEGMENT")
	var other_end: Node = null
	for r in net.roads():
		if r != drawn and r.points().size() >= 2 and not Gestures.is_mouth(r.points()[-1]):
			other_end = r.points()[-1]
			break
	tool.click(ctx, cam.unproject_position(ends[1].global_position))
	var jct: Dictionary = tool.click(ctx, cam.unproject_position(other_end.global_position))
	check(jct["changed"] and Gestures.junction_members(ends[1]).has(other_end), "CONNECT: points of different roads make a junction")

	# ── DRAW on Terrain3D (DebugWorld) ──
	var world: Node = (load(WORLD) as PackedScene).instantiate()
	root.add_child(world)
	await process_frame
	var terrain: Node = world.find_children("*", "Terrain3D", true, false)[0]
	var dnet: Node3D = null
	for c in world.find_children("*", "Node3D", true, false):
		if c.get_script() == NetworkScript:
			dnet = c
	dnet.load_record()
	await process_frame
	var dcam := _camera_over(dnet, 400.0)
	await process_frame
	var dt = Tool.new()
	dt.set_mode(Tool.Mode.DRAW)
	var target: Vector3 = dnet.all_points()[0].global_position + Vector3(20, 0, 20)
	var hit = Tool.ground_hit(dnet, terrain, dcam.global_position + Vector3(target.x - dcam.global_position.x, 0, target.z - dcam.global_position.z), Vector3.DOWN)
	var want: float = Ground.natural_height(dnet, terrain, Ground.natural_source(dnet), target)
	var want_local: float = (dnet.global_transform.affine_inverse() * Vector3(target.x, want, target.z)).y + Tool.DRAPE
	check(hit != null and absf(hit.y - want_local) < 0.05, "on Terrain3D a drawn station lands on the NATURAL ground + drape",
			"hit %s, natural+drape %.3f" % [str(hit), want_local])
	world.free()

	print("RESULT: %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
