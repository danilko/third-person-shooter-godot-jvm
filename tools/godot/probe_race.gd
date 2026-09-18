extends SceneTree
## Race missions (PLAN.md 4.5 / R2): RaceDirector + RaceCheckpoint, asserted on a real Player, a real
## Vehicle and a real AI body against the real autoloads, and started through the shipped
## MissionManager path (a MissionInfo .tres handed to start_mission_from_path) — never by calling
## startRace directly.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_race.gd
##   ... -- --control    # ordered_checkpoints off: the refused implementation in which ANY gate the
##                       # racer has not taken counts, in any order, so cutting a corner skips a
##                       # checkpoint. Fails exactly 4 (case 3).
##
## What is asserted here and what is NOT: the ordering rule, the lap rule, the countdown and clock,
## the time trial, the placings, the mission seam, the carrier case, the HUD gate and the GPS target
## are all measured. The AI racer's LANE-FOLLOWING is not — a bare stand has no road network, and
## driving a lane is probe_road_traffic's / probe_traffic_spawn's gate. What this asserts of an AI
## racer is that it is scored by the same rules as a player, and that `racing` is the one behavioural
## exception it gets: it does not yield at a junction another car holds.

const PLAYER  := "res://src/main/resources/com/openworld/character/Player.tscn"
const AI      := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const VEHICLE := "res://src/main/resources/com/openworld/vehicle/Vehicle.tscn"
const CP      := "res://src/main/java/com/openworld/world/RaceCheckpoint.java"
const INFO    := "res://src/main/java/com/openworld/character/CharacterInfo.java"
const MINFO   := "res://src/main/java/com/openworld/game/mission/MissionInfo.java"
const IZONE   := "res://src/main/java/com/openworld/world/IntersectionZone.java"
const HELPER  := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const HUDSCN  := "res://src/main/resources/com/openworld/ui/HUDManager.tscn"

const RACE_ID := "probe_circuit"
const PARK    := Vector3(0, 0, 300)      # off every gate, where a racer waits between touches

var fails := 0
var control := false
var world: Node3D
var race: Node
var mission: Node
var bus: Node
var helper: Node
var hud: Node
var player: Node3D
var player_id := ""
var completed: Array = []
var failed: Array = []
var gates: Array[Area3D] = []
var mission_seq := 0

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

## A circle of `count` gates, `r` metres from `at`.
func _circuit(at: Vector3, r: float, count: int) -> void:
	for g in gates:
		if is_instance_valid(g):
			g.queue_free()
	gates.clear()
	await _tick(2)
	for i in range(count):
		gates.append(_gate(i, at + Vector3(sin(TAU * i / count) * r, 1.0, -cos(TAU * i / count) * r)))
	await _tick(4)

func _gate(index: int, at: Vector3) -> Area3D:
	var cp: Area3D = load(CP).new()
	cp.set("race_id", RACE_ID)
	cp.set("checkpoint_index", index)
	cp.set("show_marker", false)   # headless: the marker is a MeshInstance3D nothing renders
	cp.set("marker_radius", 6.0)
	cp.set("marker_height", 8.0)
	world.add_child(cp)
	cp.global_position = at
	return cp

## Start a RACE mission the shipped way: write the MissionInfo as a .tres and hand its path to
## MissionManager.start_mission_from_path, which is what a beat script or the console would do.
func _start(laps: int, time_limit: float, race_id := RACE_ID) -> bool:
	mission_seq += 1
	var info: Resource = load(MINFO).new()
	info.set("mission_id", "probe_race_%d" % mission_seq)
	info.set("objective_type", "RACE")
	info.set("race_id", race_id)
	info.set("race_laps", laps)
	info.set("time_limit", time_limit)
	var path := "user://probe_race_%d.tres" % mission_seq
	var err := ResourceSaver.save(info, path)
	if err != OK:
		_check("saving the probe MissionInfo", false, "error %d" % err)
		return false
	var ok: bool = bool(mission.call("start_mission_from_path", path))
	await _tick(6)
	return ok

## Drive the racer through gate `i` — teleport in, out again. A checkpoint is an Area3D and the
## ENTRY is what is under test, not the driving.
func _touch(body: Node3D, i: int) -> void:
	body.global_position = gates[i].global_position + Vector3(0, -0.5, 0)
	await _tick(6)
	body.global_position = PARK
	await _tick(4)

func _next(id: String) -> int:
	return int(race.call("racer_next_index", id))

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		if a == "--control":
			control = true
	await process_frame

	race = root.get_node_or_null("RaceDirector")
	mission = root.get_node_or_null("MissionManager")
	bus = root.get_node_or_null("EventBus")
	if race == null or mission == null or bus == null:
		print("RESULT FAIL (RaceDirector / MissionManager / EventBus autoload missing)")
		quit(1)
		return
	race.set("debug_log", true)
	if control:
		race.set("ordered_checkpoints", false)
	bus.connect("mission_completed", func(_id, _faction, variant): completed.append(variant))
	bus.connect("mission_failed", func(_id, reason): failed.append(reason))

	world = Node3D.new()
	root.add_child(world)
	var ground := StaticBody3D.new()
	var gcs := CollisionShape3D.new()
	var gbox := BoxShape3D.new()
	gbox.size = Vector3(1400, 1, 1400)
	gcs.shape = gbox
	ground.add_child(gcs)
	ground.position = Vector3(0, -0.5, 0)
	world.add_child(ground)
	helper = load(HELPER).new()
	world.add_child(helper)
	hud = (load(HUDSCN) as PackedScene).instantiate()
	root.add_child(hud)
	await _tick(2)

	player = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(player)
	player.global_position = PARK
	await _tick(6)
	player_id = str(player.get("character_info").get("character_id"))

	print("")
	print("=== 1. a route needs checkpoints, and a mission naming one that is not there is refused ===")
	await _start(1, 0.0, "no_such_circuit")
	_check("no circuit -> no race runs", not bool(race.call("race_active_now")),
		str(race.call("race_phase_now")))

	print("")
	print("=== 2. the countdown, then the clock ===")
	await _circuit(Vector3.ZERO, 80.0, 4)
	_check("the four gates registered themselves", int(race.call("checkpoint_count", RACE_ID)) == 4,
		"%d" % int(race.call("checkpoint_count", RACE_ID)))
	race.set("countdown_seconds", 1.0)
	await _start(1, 0.0)
	_check("the mission started the race in COUNTDOWN",
		str(race.call("race_phase_now")) == "COUNTDOWN", str(race.call("race_phase_now")))
	_check("the player was enrolled with no authoring", bool(race.call("is_racer", player_id)),
		str(race.call("racer_ids_now")))
	_check("the clock has not started", race.call("race_elapsed") < 0.05,
		"%.2f s" % float(race.call("race_elapsed")))
	await _touch(player, 0)
	_check("a gate cleared during the countdown does not count", _next(player_id) == 0,
		"next #%d" % _next(player_id))
	await _tick(80)
	_check("the countdown ran out into RUNNING", str(race.call("race_phase_now")) == "RUNNING",
		str(race.call("race_phase_now")))
	_check("and the clock is running", race.call("race_elapsed") > 0.2,
		"%.2f s" % float(race.call("race_elapsed")))
	race.set("countdown_seconds", 0.0)

	print("")
	print("=== 3. only the racer's OWN next gate counts (the control's 4 failures) ===")
	await _start(1, 0.0)
	await _touch(player, 2)
	_check("a gate taken out of order is refused", _next(player_id) == 0, "next #%d" % _next(player_id))
	await _touch(player, 0)
	_check("the next gate advances the racer", _next(player_id) == 1, "next #%d" % _next(player_id))
	await _touch(player, 0)
	_check("driving back through the one just taken is not progress", _next(player_id) == 1,
		"next #%d" % _next(player_id))
	_check("the gate counted only the clearing that counted",
		int(gates[0].get("cleared_count")) == 1, str(gates[0].get("cleared_count")))

	print("")
	print("=== 4. the GPS target and the HUD follow the race with no situation change ===")
	await _start(1, 0.0)
	await _touch(player, 0)
	var next_pos: Vector3 = race.call("next_checkpoint_position", player_id)
	_check("next_checkpoint_position is the gate after the one just cleared",
		bool(race.call("has_next_checkpoint", player_id))
			and next_pos.distance_to(gates[1].global_position) < 0.01,
		"%.3f m off gate #1" % next_pos.distance_to(gates[1].global_position))
	var race_hud: Control = hud.get_node_or_null("RaceHUD")
	_check("the RaceHUD showed itself", race_hud != null and race_hud.visible,
		"visible=%s" % (str(race_hud.visible) if race_hud != null else "no node"))

	print("")
	print("=== 5. the lap closes, the racer finishes, the MISSION completes ===")
	completed.clear()
	await _touch(player, 1)
	await _touch(player, 2)
	await _touch(player, 3)
	_check("clearing the last gate closed the lap",
		int(race.call("racer_lap", player_id)) == 1 and _next(player_id) == 0,
		"lap %d next #%d" % [int(race.call("racer_lap", player_id)), _next(player_id)])
	_check("the racer finished", bool(race.call("racer_finished", player_id)),
		"%.2f s" % float(race.call("racer_finish_time", player_id)))
	_check("first across the line, alone on the course", int(race.call("racer_place", player_id)) == 1,
		"place %d" % int(race.call("racer_place", player_id)))
	await _tick(4)
	_check("the mission completed as WON", completed == ["WON"], str(completed))
	_check("the race is no longer active", not bool(race.call("race_active_now")),
		str(race.call("race_phase_now")))
	_check("but its results are still readable (the finish panel's whole point)",
		bool(race.call("racer_finished", player_id)),
		str(race.call("status_line")).split("\n")[0])
	_check("the HUD stays up on the finished race", race_hud != null and race_hud.visible,
		str(race_hud.visible))

	print("")
	print("=== 6. two laps: the same four gates, twice ===")
	completed.clear()
	await _start(2, 0.0)
	for lap in range(2):
		for i in range(4):
			await _touch(player, i)
	_check("two laps of four gates finished it", bool(race.call("racer_finished", player_id)),
		"lap %d" % int(race.call("racer_lap", player_id)))
	_check("and completed the mission exactly once", completed.size() == 1, str(completed))

	print("")
	print("=== 7. the time trial: MissionInfo.timeLimit fails the mission ===")
	completed.clear()
	failed.clear()
	await _start(1, 1.0)
	_check("time remaining is reported", race.call("race_time_remaining") > 0.0,
		"%.2f s" % float(race.call("race_time_remaining")))
	await _tick(110)
	_check("running out of time failed the mission", failed.size() == 1, str(failed))
	_check("and ended the race", not bool(race.call("race_active_now")),
		str(race.call("race_phase_now")))
	_check("with nothing completed", completed.is_empty(), str(completed))

	print("")
	print("=== 8. a car carrying the racer clears the gate (a seated occupant is on NO layer) ===")
	completed.clear()
	await _start(1, 0.0)
	var car: Node3D = (load(VEHICLE) as PackedScene).instantiate() as Node3D
	world.add_child(car)
	car.global_position = PARK + Vector3(4, 0.6, 0)
	car.set("freeze", true)
	await _tick(4)
	player.global_position = PARK + Vector3(2, 0, 0)
	await _tick(4)
	helper.call("seat_character", car, player)
	await _tick(6)
	_check("the player is in the seat", helper.call("occupant_of", car) == player,
		str(helper.call("occupant_of", car)))
	car.global_position = gates[0].global_position
	await _tick(8)
	_check("driving through the gate counted for the DRIVER", _next(player_id) == 1,
		"next #%d, gate mask %d" % [_next(player_id), int(gates[0].get("collision_mask"))])
	helper.call("exit_driver", car)
	await _tick(6)
	player.global_position = PARK
	await _tick(4)

	print("")
	print("=== 9. an AI racer is scored by the same rules ===")
	var ai: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	var info: Resource = load(INFO).new()
	# A fresh CharacterInfo, never the scene's: a .tscn-embedded sub-resource is SHARED by every
	# instantiation (CLAUDE.md "Known Quirks").
	info.set("character_id", "ai_racer_01")
	info.set("display_name", "Rival")
	info.set("faction", "player")
	ai.set("character_info", info)
	world.add_child(ai)
	ai.global_position = PARK + Vector3(20, 0, 0)
	await _tick(6)
	race.call("add_racer", "ai_racer_01")
	_check("an AI can be enrolled mid-race", bool(race.call("is_racer", "ai_racer_01")),
		str(race.call("racer_ids_now")))
	ai.global_position = gates[1].global_position
	await _tick(8)
	ai.global_position = PARK + Vector3(20, 0, 0)
	await _tick(4)
	_check("and only from ITS own next gate", _next("ai_racer_01") == (1 if control else 0),
		"next #%d" % _next("ai_racer_01"))
	ai.global_position = gates[0].global_position
	await _tick(8)
	ai.global_position = PARK + Vector3(20, 0, 0)
	await _tick(4)
	_check("clearing its own next gate scores it", _next("ai_racer_01") >= 1,
		"next #%d" % _next("ai_racer_01"))

	print("")
	print("=== 10. standings: further round the course is ahead ===")
	await _touch(player, 1)
	await _tick(30)
	_check("the player leads the AI racer",
		int(race.call("racer_place", player_id)) < int(race.call("racer_place", "ai_racer_01")),
		"player %d, ai %d (of %d)" % [int(race.call("racer_place", player_id)),
			int(race.call("racer_place", "ai_racer_01")), int(race.call("racer_count"))])

	print("")
	print("=== 11. `racing` is the one behavioural exception an AI racer gets ===")
	var junction: Area3D = load(IZONE).new()
	var jcs := CollisionShape3D.new()
	var jbox := BoxShape3D.new()
	jbox.size = Vector3(14, 6, 14)
	jcs.shape = jbox
	junction.add_child(jcs)
	junction.collision_mask = 16      # CollisionLayers.VEHICLE — the mask a baked junction is given
	world.add_child(junction)
	junction.global_position = Vector3(400, 1, 0)
	await _tick(2)
	var holder: Node3D = (load(VEHICLE) as PackedScene).instantiate() as Node3D
	var follower: Node3D = (load(VEHICLE) as PackedScene).instantiate() as Node3D
	for v in [holder, follower]:
		world.add_child(v)
		v.set("freeze", true)
	# The brain has to exist BEFORE the car enters: the arbiter registers a vehicle on body_entered
	# and skips one with no VehicleAIController, so attaching afterwards leaves it unregistered — a
	# car that reads as "not yielding" for the wrong reason.
	holder.global_position = Vector3(360, 0.6, 0)
	follower.global_position = Vector3(364, 0.6, 0)
	await _tick(2)
	helper.call("attach_traffic_brain", holder, false)
	helper.call("attach_traffic_brain", follower, false)
	await _tick(4)
	holder.global_position = Vector3(398, 0.6, 0)
	await _tick(4)
	follower.global_position = Vector3(402, 0.6, 0)
	await _tick(6)
	_check("an ambient car yields to the one holding the junction",
		bool(helper.call("yielding_now", follower)) and not bool(helper.call("yielding_now", holder)),
		"holder=%s follower=%s" % [str(helper.call("yielding_now", holder)),
			str(helper.call("yielding_now", follower))])
	# The SAME brain, still in the same junction — a re-attach would lose its membership and read as
	# "not yielding" for the wrong reason.
	helper.call("set_racing", follower, true)
	await _tick(4)
	_check("the same car as a race entrant does not",
		not bool(helper.call("yielding_now", follower)),
		"follower=%s" % str(helper.call("yielding_now", follower)))

	print("")
	print("=== 12. the co-op mirror: what the host puts on the wire is what a client reads ===")
	# Not two processes (that is run_net_*.sh's shape) — what is asserted is that the PRODUCER and the
	# CONSUMER of the race payload agree, which is where an off-by-one would hide: a client that read
	# an AI racer as a human would wait for it to finish before ending the mission, with nothing on
	# either peer to say so.
	var wire: String = str(race.call("remote_start_args_now"))
	var host_ids: String = str(race.call("racer_ids_now"))
	var host_laps: int = int(race.call("race_lap_count"))
	var host_next: int = _next(player_id)
	var host_lap: int = int(race.call("racer_lap", player_id))
	race.call("apply_remote_event_csv", 9, "someone_elses_race", 0.0, "other_mission,1,wiped,1")
	await _tick(2)
	_check("a foreign start wipes this peer's roster (the mirror is a REPLACE)",
		str(race.call("racer_ids_now")) == "wiped", str(race.call("racer_ids_now")))
	race.call("apply_remote_event_csv", 9, RACE_ID, 0.0, wire)
	await _tick(2)
	_check("replaying the host's own start rebuilds its roster in order",
		str(race.call("racer_ids_now")) == host_ids and int(race.call("race_lap_count")) == host_laps,
		"%s laps %d" % [str(race.call("racer_ids_now")), int(race.call("race_lap_count"))])
	race.call("apply_remote_event_csv", 10, player_id, 4.5,
		"%s,%d,%d" % [RACE_ID, host_next, host_lap])                                # RACE_CHECKPOINT
	await _tick(2)
	_check("a mirrored checkpoint restores the racer's progress",
		_next(player_id) == host_next and int(race.call("racer_lap", player_id)) == host_lap,
		"next #%d lap %d" % [_next(player_id), int(race.call("racer_lap", player_id))])
	race.call("apply_remote_event_csv", 11, "ai_racer_01", 12.25, "%s,2" % RACE_ID)  # RACE_FINISH
	await _tick(2)
	_check("a mirrored finish lands the time and the place",
		bool(race.call("racer_finished", "ai_racer_01"))
			and int(race.call("racer_place", "ai_racer_01")) == 2
			and abs(float(race.call("racer_finish_time", "ai_racer_01")) - 12.25) < 0.01,
		"%.2f s, place %d" % [float(race.call("racer_finish_time", "ai_racer_01")),
			int(race.call("racer_place", "ai_racer_01"))])
	_check("a client never adjudicates: it counts only what it was told",
		int(race.call("finished_racer_count")) == 1, str(race.call("finished_racer_count")))

	print("")
	print("=== 13. a duplicate index is refused; a freed gate leaves the route ===")
	var dupe := _gate(2, Vector3(600, 1, 600))
	await _tick(4)
	_check("a second gate claiming an index does not join the route",
		int(race.call("checkpoint_count", RACE_ID)) == 4,
		"%d" % int(race.call("checkpoint_count", RACE_ID)))
	dupe.queue_free()
	gates[3].queue_free()
	await _tick(6)
	_check("a freed gate leaves it", int(race.call("checkpoint_count", RACE_ID)) == 3,
		"%d" % int(race.call("checkpoint_count", RACE_ID)))

	print("")
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
