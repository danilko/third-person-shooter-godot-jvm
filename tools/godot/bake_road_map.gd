extends SceneTree
## PLAN.md 4.7b -- bake each world's road map: the road picture of the whole world (to the WorldBounds
## wall) and the routing graph + its constant-time cell index, into
## src/main/resources/com/openworld/world/roadmap/<Scene>.roadmap.{bin,res}.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/bake_road_map.gd            # both worlds
##   ... -- --world=debugworld|island
##   ... -- --check          write nothing; exit 1 if a committed bake does not match its scene
##
## Re-run after any road build (a lanekit sidecar changed), a zone moved, or the WorldBounds wall
## moved. The game never draws a stale bake -- RoadMap builds live and says so -- but that costs the
## load time the bake exists to save, and the probes assert the bake is fresh.

const WORLDS := {
	"debugworld": "res://src/main/resources/com/openworld/world/DebugWorld.tscn",
	"island": "res://src/main/resources/com/openworld/world/World.tscn",
}

func _initialize() -> void:
	var which := ["debugworld", "island"]
	var check := false
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--world="):
			which = [a.substr(8)]
		elif a == "--check":
			check = true
	var failed := 0
	for w in which:
		var world: Node = (load(WORLDS[w]) as PackedScene).instantiate()
		root.add_child(world)
		for i in 5:
			await process_frame
		var baker: Node = load("res://src/main/java/com/openworld/world/RoadMapBaker.java").new()
		root.add_child(baker)
		var report: String
		if check:
			report = baker.call("bake_status_now")
			if report != "fresh":
				failed += 1
		else:
			report = baker.call("bake_now")
			if not report.begins_with("OK"):
				failed += 1
			else:
				var status: String = baker.call("bake_status_now")
				if status != "fresh":
					failed += 1
					report += " -- but the status right after is: " + status
		print("  %-10s %s" % [w, report])
		baker.queue_free()
		world.queue_free()
		for i in 3:
			await process_frame
	print("RESULT %s" % ["PASS" if failed == 0 else "FAIL"])
	quit(0 if failed == 0 else 1)
