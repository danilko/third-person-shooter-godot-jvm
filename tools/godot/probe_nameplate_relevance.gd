extends SceneTree
## A plate only where one means something (user, 2026-09-27; NameplateTarget.isNameplateRelevant).
##
##   godot --headless --path . --script tools/godot/probe_nameplate_relevance.gd [-- --control]
##
## A bare stand: the local Player, a NEUTRAL pedestrian AI, a mission (story) AI and an enemy AI that fights
## the player. (Another PLAYER's plate is a networked case -- in single player every Player is local.) Asserts:
##   * the local player's own plate is hidden;
##   * the mission character and the fighting enemy show a plate;
##   * the neutral pedestrian does NOT -- and its SubViewport stops rendering;
##   * once the pedestrian is hurt its plate comes up.
## `--control` asks every target to be relevant (the old always-on plate): the pedestrian case then fails.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const INFO := "res://src/main/java/com/openworld/character/CharacterInfo.java"

var world: Node3D
var fails := 0
var passes := 0
var control := false

func _check(ok: bool, msg: String) -> void:
	if ok:
		passes += 1
		print("  PASS  " + msg)
	else:
		fails += 1
		print("  FAIL  " + msg)

func _tick(n: int) -> void:
	for i in n: await physics_frame

func _spawn(scene: String, id: String, faction: String, pos: Vector3, story := false) -> Node3D:
	var b: Node3D = (load(scene) as PackedScene).instantiate() as Node3D
	var info: Resource = load(INFO).new()
	info.set("character_id", id)
	info.set("display_name", id)
	info.set("faction", faction)
	b.set("character_info", info)
	if story: b.set("story_character", true)
	world.add_child(b)
	b.global_position = pos
	await _tick(2)
	return b

func _plate(b: Node) -> Node:
	return b.get_node_or_null("Nameplate")

func _initialize() -> void:
	control = "--control" in OS.get_cmdline_user_args()
	await process_frame
	world = Node3D.new()
	root.add_child(world)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(200, 1, 200)
	cs.shape = box
	floor.add_child(cs)
	floor.position = Vector3(0, -0.5, 0)
	world.add_child(floor)

	var me: Node3D = await _spawn(PLAYER, "me", "player", Vector3(0, 0, 0))
	var ped: Node3D = await _spawn(AI, "ped", "neutral", Vector3(-4, 0, 8))
	var boss: Node3D = await _spawn(AI, "boss", "enemy", Vector3(4, 0, 8), true)
	var foe: Node3D = await _spawn(AI, "foe", "enemy", Vector3(0, 0, 14))
	if control:
		for b in [ped]:
			# the old rule: every plate up
			b.get_node("Health").call("apply_replicated_health", 50.0)
	await _tick(120)                 # the enemy sees the player and fights (its own AI)

	print("")
	print("=== nameplates ===")
	_check(not _plate(me).visible, "the local player's own plate is hidden")
	_check(_plate(boss).visible, "a mission character shows a plate")
	_check(_plate(foe).visible, "a hostile in a fight shows a plate")
	_check(not _plate(ped).visible, "a neutral pedestrian shows NO plate")
	var vp: SubViewport = _plate(ped).get_node_or_null("SubViewport")
	_check(vp != null and vp.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"its hidden plate renders nothing (update mode %s)" % (vp.render_target_update_mode if vp else -1))
	ped.get_node("Health").call("apply_replicated_health", 60.0)
	await _tick(30)
	_check(_plate(ped).visible, "once hurt, the pedestrian's plate comes up")

	print("RESULT %s (%d passed, %d failed)" % ["PASS" if fails == 0 else "FAIL", passes, fails])
	quit(1 if fails > 0 else 0)
