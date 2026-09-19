extends SceneTree
## ZoneTrigger (PLAN.md 4.3 / F3): the caller MissionDirector.triggerBeat was missing. Asserted on
## real Player / AICharacter / Vehicle bodies against the real autoloads, never on a stand-in.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_zone_trigger.gd
##   ... -- --control    # both control knobs off: `one_shot` becomes a node-local flag (so a
##                       # re-streamed zone re-arms its ambush) and the mask drops VEHICLE (so a
##                       # player who drives in trips nothing). Fails 3.
##
## Why a Player stands in the scene even for the cases it does not trip: an AICharacter with no
## player within 80 m is LOD-FROZEN and never thinks, so the escort case would measure a body that
## never moves.

const AI      := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const PLAYER  := "res://src/main/resources/com/openworld/character/Player.tscn"
const VEHICLE := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
const TRIGGER := "res://src/main/java/com/openworld/world/ZoneTrigger.java"
const HELPER  := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const INFO    := "res://src/main/java/com/openworld/character/CharacterInfo.java"
const MISSION := "res://src/main/resources/com/openworld/game/mission/GangA_vs_Police_Mission.tres"

const BOSS := "boss_01"

var fails := 0
var control := false
var world: Node3D
var director: Node
var bus: Node
var helper: Node
var beats: Array[String] = []

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-60s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _trigger(beat: String, pos: Vector3, size := Vector3(8, 6, 8)) -> Area3D:
	var t: Area3D = load(TRIGGER).new()
	t.set("beat_id", beat)
	if control:
		t.set("campaign_one_shot", false)
		t.set("carrier_aware", false)
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	cs.shape = box
	t.add_child(cs)
	world.add_child(t)
	t.global_position = pos
	return t

func _spawn_ai(id: String, faction: String, story: bool, pos: Vector3) -> Node3D:
	var b: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	b.set("story_character", story)
	# A fresh CharacterInfo, never the scene's: a .tscn-embedded sub-resource is SHARED by every
	# instantiation (CLAUDE.md "Known Quirks"), and Character._ready only privatizes one whose id is
	# still empty — so stamping the scene's own resource renames every AI spawned before this one.
	var info: Resource = load(INFO).new()
	info.set("character_id", id)
	info.set("display_name", id)
	info.set("faction", faction)
	b.set("character_info", info)
	world.add_child(b)
	b.global_position = pos
	await _tick(2)
	return b

func _fired(beat: String) -> int:
	return int(director.call("beat_fire_count", beat))

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		if a == "--control":
			control = true
	await process_frame

	director = root.get_node_or_null("MissionDirector")
	bus = root.get_node_or_null("EventBus")
	var mm: Node = root.get_node_or_null("MissionManager")
	if director == null or bus == null or mm == null:
		print("RESULT FAIL (MissionDirector / EventBus / MissionManager autoload missing)")
		quit(1)
		return
	bus.connect("mission_beat_triggered", func(b): beats.append(b))

	world = Node3D.new()
	root.add_child(world)
	var ground := StaticBody3D.new()
	var gcs := CollisionShape3D.new()
	var gbox := BoxShape3D.new()
	gbox.size = Vector3(400, 1, 400)
	gcs.shape = gbox
	ground.add_child(gcs)
	ground.position = Vector3(0, -0.5, 0)
	world.add_child(ground)
	helper = load(HELPER).new()
	world.add_child(helper)
	await _tick(2)

	var player: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(player)
	player.global_position = Vector3(0, 0, 0)
	await _tick(4)
	player.get("character_info").set("faction", "player")

	print("")
	print("=== 1. the spec's verify: walk in -> the beat fires -> the boss escorts you ===")
	# A real walk, not a teleport: the player's own PlayerController reads the `forward` action, and
	# the camera rig rests at yaw 0, so forward is -Z.
	var gate := _trigger("ambush_gate", Vector3(0, 1.5, -12))
	var boss: Node3D = await _spawn_ai(BOSS, "player", true, Vector3(14, 0, -12))
	# The beat's handler, standing in for the Java one a mission would register: the director's event
	# fires on every peer, which is what dialogue/HUD/story code hangs off.
	bus.connect("mission_beat_triggered", func(b):
		if b == "ambush_gate":
			director.call("command_escort_player", BOSS))
	await _tick(4)

	var boss_start: float = boss.global_position.distance_to(player.global_position)
	Input.action_press("forward")
	var walked := 0
	while walked < 60 * 8 and _fired("ambush_gate") == 0:
		await _tick(10)
		walked += 10
	Input.action_release("forward")
	await _tick(4)
	_check("walking in fired the beat",
		_fired("ambush_gate") == 1, "z %.1f after %.1f s" % [player.global_position.z, walked / 60.0])
	_check("the beat reached EventBus", "ambush_gate" in beats, str(beats))
	_check("the trigger counted its own firing", int(gate.get("trigger_count")) == 1,
		str(gate.get("trigger_count")))
	_check("the boss took the escort order", str(director.call("state_name_of", BOSS)) == "ESCORT",
		str(director.call("state_name_of", BOSS)))

	# The escort MOTION is EscortState's and is nav-driven; this bare stand has no NavigationRegion3D,
	# where a NavAgent reports "not finished" forever and hands back the body's own position (the trap
	# CLAUDE.md records under the story layer), so what is asserted here is the ORDER the trigger
	# delivered — the state and who is being escorted — not metres walked.
	var escortee: String = str(boss.call("escort_target_id_now"))
	var player_id: String = str(player.get("character_info").get("character_id"))
	_check("and it is escorting the player who tripped it", escortee == player_id and escortee != "",
		"%s (boss started %.1f m off)" % [escortee, boss_start])

	print("")
	print("=== 2. one-shot is the DIRECTOR's answer, so a re-streamed zone does not re-arm ===")
	player.global_position = Vector3(0, 0, 40)
	await _tick(6)
	player.global_position = Vector3(0, 0, -12)
	await _tick(6)
	_check("walking back in does not fire it again", _fired("ambush_gate") == 1,
		"%d firings" % _fired("ambush_gate"))
	# The zone streams out and back: the node is freed and a fresh one instanced from the same scene.
	gate.queue_free()
	await _tick(4)
	player.global_position = Vector3(0, 0, 40)
	await _tick(4)
	var gate2 := _trigger("ambush_gate", Vector3(0, 1.5, -12))
	await _tick(4)
	player.global_position = Vector3(0, 0, -12)
	await _tick(8)
	_check("a FRESH trigger node for a spent beat stays silent (the re-stream case)",
		_fired("ambush_gate") == 1, "%d firings" % _fired("ambush_gate"))
	player.global_position = Vector3(0, 0, 40)
	await _tick(4)

	print("")
	print("=== 3. a non-player does not trip a player trigger ===")
	var ambient: Node3D = await _spawn_ai("ambient_01", "enemy", false, Vector3(60, 0, 60))
	var marker := _trigger("objective_1", Vector3(60, 1.5, 40))
	await _tick(4)
	ambient.global_position = Vector3(60, 0, 40)
	await _tick(8)
	_check("an ambient AI walking through fires nothing", _fired("objective_1") == 0,
		"%d firings" % _fired("objective_1"))
	ambient.global_position = Vector3(60, 0, 60)
	await _tick(4)

	print("")
	print("=== 4. requires_beat: an objective marker waits for its predecessor ===")
	var second := _trigger("objective_2", Vector3(-40, 1.5, 0))
	second.set("requires_beat", "objective_1")
	await _tick(4)
	player.global_position = Vector3(-40, 0, 0)
	await _tick(8)
	_check("silent while its prerequisite has not fired", _fired("objective_2") == 0,
		str(second.call("refusal_now", player)))
	player.global_position = Vector3(0, 0, 40)
	await _tick(4)
	director.call("trigger_beat", "objective_1")
	await _tick(2)
	player.global_position = Vector3(-40, 0, 0)
	await _tick(8)
	_check("fires once the prerequisite has", _fired("objective_2") == 1,
		"%d firings" % _fired("objective_2"))
	player.global_position = Vector3(0, 0, 40)
	await _tick(4)

	print("")
	print("=== 5. required_mission_id: an ambush does not fire before its mission ===")
	var ambush := _trigger("mission_ambush", Vector3(-70, 1.5, 0))
	var mission_id: String = str((load(MISSION) as Resource).get("mission_id"))
	ambush.set("required_mission_id", mission_id)
	await _tick(4)
	player.global_position = Vector3(-70, 0, 0)
	await _tick(8)
	_check("silent while the mission is not active", _fired("mission_ambush") == 0,
		str(ambush.call("refusal_now", player)))
	player.global_position = Vector3(0, 0, 40)
	await _tick(4)
	director.call("reset_campaign")
	beats.clear()
	_check("the mission started", bool(director.call("start_mission_from_path", MISSION)), mission_id)
	player.global_position = Vector3(-70, 0, 0)
	await _tick(8)
	_check("fires while it IS active", _fired("mission_ambush") == 1,
		"%d firings" % _fired("mission_ambush"))
	player.global_position = Vector3(0, 0, 40)
	await _tick(4)

	print("")
	print("=== 6. required_character_id: the escortee's drop-off, not the player's ===")
	var dropoff := _trigger("dropoff", Vector3(90, 1.5, 0))
	dropoff.set("required_character_id", BOSS)
	await _tick(4)
	player.global_position = Vector3(90, 0, 0)
	await _tick(8)
	_check("the player standing in it fires nothing", _fired("dropoff") == 0,
		str(dropoff.call("refusal_now", player)))
	player.global_position = Vector3(0, 0, 40)
	await _tick(4)
	director.call("release_character", BOSS)
	boss.global_position = Vector3(90, 0, 0)
	await _tick(12)
	_check("the named character does fire it", _fired("dropoff") == 1,
		"%d firings, boss at %s, would_fire=%s refusal='%s'" % [_fired("dropoff"),
			str(boss.global_position.round()), str(dropoff.call("would_fire_for", boss)),
			str(dropoff.call("refusal_now", boss))])

	print("")
	print("=== 7. driving in trips it: a seated occupant is on NO collision layer ===")
	var car: Node3D = (load(VEHICLE) as PackedScene).instantiate() as Node3D
	world.add_child(car)
	car.global_position = Vector3(-120, 0.6, 30)
	car.set("freeze", true)
	await _tick(4)
	player.global_position = Vector3(-120, 0, 32)
	await _tick(4)
	helper.call("seat_character", car, player)
	await _tick(6)
	var seated: bool = helper.call("occupant_of", car) == player
	_check("the player is in the driver's seat", seated, str(helper.call("occupant_of", car)))
	var drive_in := _trigger("checkpoint", Vector3(-120, 1.5, 0))
	await _tick(4)
	car.global_position = Vector3(-120, 0.6, 0)
	await _tick(10)
	_check("the car carrying the player fires the beat", _fired("checkpoint") == 1,
		"%d firings, mask %d" % [_fired("checkpoint"), int(drive_in.get("collision_mask"))])

	print("")
	print("=== 8. a trigger is inert until the beat has a name ===")
	var blank: Area3D = load(TRIGGER).new()
	var bcs := CollisionShape3D.new()
	var bbox := BoxShape3D.new()
	bbox.size = Vector3(8, 6, 8)
	bcs.shape = bbox
	blank.add_child(bcs)
	world.add_child(blank)
	blank.global_position = Vector3(150, 1.5, 0)
	await _tick(4)
	_check("fire_now on a nameless trigger does nothing", not bool(blank.call("fire_now")), "")

	print("")
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
