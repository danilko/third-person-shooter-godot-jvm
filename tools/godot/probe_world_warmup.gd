extends SceneTree
## THE LOADING SCREEN AND ITS WARM-UP TOUR (game.WorldWarmup; user, 2026-10-10). World.tscn; the probe adds the
## warm-up itself (FrontEnd never starts it under --script), with short timings.
##   stdbuf -oL <godot> --headless --fixed-fps 60 --path . --script tools/godot/probe_world_warmup.gd [-- --control]
## Asserted: the cover is up from the first frame to the end; the PLAYER DOES NOT MOVE while the focus travels; at a
## toured site the streamer really loads zones the player's own position would not (loaded zones rise, and the
## streaming focus is set); the body is held and invulnerable meanwhile; at the end the focus is cleared, the hold and
## the invulnerability are gone, the node has removed itself, and the streamer is quiet round the player.
## --control: max_sites = 0 -- no tour: no zone beyond the player's own is ever loaded (so the rise above is the tour's).
const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const WARMUP := "res://src/main/java/com/openworld/game/WorldWarmup.java"
var fails := 0
var control := false

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", label, detail])

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		if a == "--control":
			control = true
	_run.call_deferred()

func _run() -> void:
	var w: Node = (load(WORLD) as PackedScene).instantiate()
	root.add_child(w)
	current_scene = w
	await process_frame
	var zm := root.get_node("/root/ZoneManager")
	zm.set("debug_log", false)
	var p := w.get_node("Characters/Player") as CharacterBody3D
	# let the world round the start stream in first, so "more zones" below is the tour's doing
	var waited := 0
	while waited < 60 * 120:
		await physics_frame
		waited += 1
		if waited > 300 and int(zm.call("streaming_pending_now")) == 0:
			break
	var home_zones: int = zm.call("loaded_zone_count_now")
	var start := p.global_position
	var health := p.get_node("Health")
	var warm: Node = load(WARMUP).new()
	warm.set("max_sites", 0 if control else 3)
	warm.set("per_site_min_seconds", 1.0)
	warm.set("per_site_max_seconds", 20.0)
	warm.set("max_seconds", 90.0)
	w.add_child(warm)
	await process_frame
	_check("the cover is up at once", bool(warm.call("cover_up_now")), "")
	var peak := home_zones
	var drift := 0.0
	var focus_seen := false
	var held_seen := false
	var invuln_seen := false
	var cover_always := true
	var sites: int = warm.call("sites_now")
	var frames := 0
	while is_instance_valid(warm) and frames < 60 * 200:
		await physics_frame
		frames += 1
		if not is_instance_valid(warm):
			break
		cover_always = cover_always and bool(warm.call("cover_up_now"))
		peak = maxi(peak, int(zm.call("loaded_zone_count_now")))
		var d := p.global_position - start
		d.y = 0
		drift = maxf(drift, d.length())
		if str(warm.call("phase_now")) == "TOUR":
			focus_seen = focus_seen or bool(zm.call("has_stream_focus_now"))
			held_seen = held_seen or bool(p.call("input_blocked_now"))
			invuln_seen = invuln_seen or bool(health.call("invulnerable_now"))
	_check("the warm-up finished and removed itself", not is_instance_valid(warm), "%.0f s" % (frames / 60.0))
	_check("the cover stayed up until then", cover_always, "")
	_check("the player never moved", drift < 1.0, "%.2f m" % drift)
	if control:
		_check("control: with no sites nothing beyond the player's own zones loads", peak <= home_zones, "%d -> peak %d" % [home_zones, peak])
	else:
		_check("there were sites to tour", sites == 3, "%d" % sites)
		_check("the streaming focus was set during the tour", focus_seen, "")
		_check("zones the player's position does not reach were loaded", peak > home_zones, "%d -> peak %d" % [home_zones, peak])
		_check("the body was held and invulnerable meanwhile", held_seen and invuln_seen, "held %s invulnerable %s" % [held_seen, invuln_seen])
	_check("the focus is cleared", not bool(zm.call("has_stream_focus_now")), "")
	_check("the hold and the invulnerability are gone", not bool(p.call("input_blocked_now")) and not bool(health.call("invulnerable_now")), "")
	var settle := 0
	while settle < 60 * 60 and int(zm.call("streaming_pending_now")) > 0:
		await physics_frame
		settle += 1
	_check("the streamer is quiet round the player again", int(zm.call("streaming_pending_now")) == 0,
		"%d zones loaded (home %d)" % [int(zm.call("loaded_zone_count_now")), home_zones])
	print("")
	print("PASS (0 failures)" if fails == 0 else "RESULT FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
