extends SceneTree
## ENGINE SOUND PROFILES (carrier.vehicle.EngineProfile, VehicleConfig.engineSound; user 2026-10-16: "different engine
## sound options, replaceable later, or GTA-like the same sound"). On a bare floor five vehicles idle with a driver:
## SPC1 (car), KEC1 (kei), CRT1 (truck), SCT1 (scooter), SSB1 (sport).
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_engine_profiles.gd
##
##   1. each names the profile its config gives (SPC1 = car);
##   2. each has an engine voice;
##   3. idling, each plays the car's take (no profile has its own files yet) at its profile's pitch: the idle pitch
##      against SPC1's is the profile's fallbackPitch (truck < car < kei < scooter < sport), within 3 %.
## The control is SPC1 itself: the car profile, pitch 1. When a profile gets its own loops in
## assets/audio/engine/<profile>/, check 3 reads 1.0 for it instead -- change the EXPECT row with the files.

const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const EXPECT := {"SPC1": ["car", 1.0], "KEC1": ["kei", 1.18], "CRT1": ["truck", 0.72], "SCT1": ["scooter", 1.45], "SSB1": ["sport", 1.52]}

var fails := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _idle_pitch(v: Node) -> float:
	var best := 0.0
	var loudest := -1000.0
	for n in v.get_children():
		if n is AudioStreamPlayer3D and String(n.name).begins_with("Engine") and n.playing and n.volume_db > loudest:
			loudest = n.volume_db
			best = n.pitch_scale
	return best

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var w := Node3D.new()
	root.add_child(w)
	current_scene = w
	var f := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var b := BoxShape3D.new()
	b.size = Vector3(400, 1, 400)
	cs.shape = b
	f.add_child(cs)
	f.position.y = -0.5
	w.add_child(f)
	var cam := Camera3D.new()
	w.add_child(cam)
	cam.position = Vector3(12, 3, 12)
	cam.current = true
	var helper: Node = load(HELPER).new()
	w.add_child(helper)
	var cars := {}
	var i := 0
	for id in EXPECT:
		var v: RigidBody3D = (load("res://src/main/resources/com/openworld/vehicle/%s.tscn" % id) as PackedScene).instantiate()
		v.position = Vector3(i * 6.0, 1.0, 0.0)
		w.add_child(v)
		cars[id] = v
		i += 1
	await _tick(90)
	for id in cars:
		var d: Node3D = (load(AI) as PackedScene).instantiate()
		d.position = cars[id].global_position
		w.add_child(d)
		helper.call("seat_driver_quietly", cars[id], d)
	await _tick(120)
	var base := _idle_pitch(cars["SPC1"])
	for id in EXPECT:
		var v: Node = cars[id]
		var prof := String(v.call("engine_profile_now"))
		var voices := int(v.call("engine_voices_now"))
		var pitch := _idle_pitch(v)
		var ratio := pitch / base if base > 0.0 else 0.0
		print("  %s: profile %s, voices %d, idle pitch %.3f (x%.2f of the car)" % [id, prof, voices, pitch, ratio])
		_check("%s names its engine '%s'" % [id, EXPECT[id][0]], prof == EXPECT[id][0], prof)
		_check("%s has an engine voice" % id, voices >= 1, str(voices))
		_check("%s idles at its profile's pitch (x%.2f)" % [id, EXPECT[id][1]], absf(ratio - EXPECT[id][1]) <= 0.03 * EXPECT[id][1],
				"x%.3f" % ratio)
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
