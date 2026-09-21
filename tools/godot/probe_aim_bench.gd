extends SceneTree
## Smoke-drives the AimWorkbench shooting bench headless: presses its keys through the host's own
## `_input` and lets it print its `[AimBench]` shot log, which is what this run is read for.
##
##   godot --headless --path . --script tools/godot/probe_aim_bench.gd 2>&1 | grep AimBench
##
## It asserts only what it can see from outside (the scene loads, nothing errors); whether each
## shot hit what it should is read off the log, the same log a human reads in the overlay.

const BENCH := "res://src/main/resources/com/openworld/world/hosts/AimWorkbench.tscn"

var host: Node

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _key(code: Key, label: String) -> void:
	print("[AimBenchProbe] press %s" % label)
	var ev := InputEventKey.new()
	ev.physical_keycode = code
	ev.pressed = true
	host.call("_input", ev)

func _initialize() -> void:
	host = (load(BENCH) as PackedScene).instantiate()
	root.add_child(host)
	await _tick(120)                               # visuals, stances, the mannequin's equip

	# The fit sweep first, while nothing has been shot or moved: it arms the mannequin with every
	# bench weapon in turn and logs how far each one misses on THIS body. That is the readout the
	# workbench exists to show, so it is also the first thing this run proves still works.
	_key(KEY_4, "4  combat on (the aim and IK layers only run in combat)")
	# Aim at the PLAYER, which the mannequin faces: the aim ball sits behind it at spawn, and a
	# reading taken with the gun clamped at the stance's yaw limit is a reading of the clamp.
	_key(KEY_T, "T  target the player")
	await _tick(180)                               # let the body turn onto the ball before measuring
	_key(KEY_M, "M  fit sweep: every weapon's miss on this body")
	await _tick(1800)
	# and the same sweep on the next body, because a fit is a fact about a BODY: the point of the
	# readout is that these two columns of numbers differ.
	_key(KEY_V, "V  next mannequin body")
	await _tick(240)
	_key(KEY_M, "M  fit sweep on that body")
	await _tick(1800)

	_key(KEY_P, "P  player invulnerable")
	await _tick(90)                                # the AI camera tracks at 90 deg/s
	_key(KEY_Y, "Y  one AI shot at the player")
	await _tick(40)
	_key(KEY_C, "C  flick: turn away, then shoot")
	await _tick(40)
	_key(KEY_C, "C  flick back")
	await _tick(60)
	_key(KEY_B, "B  cover wall between mannequin and player")
	await _tick(10)
	_key(KEY_Y, "Y  shot into the wall")
	await _tick(40)
	_key(KEY_B, "B  wall off")
	_key(KEY_BRACKETRIGHT, "]  ASR2")
	_key(KEY_BRACKETRIGHT, "]  SHG1")
	await _tick(150)
	_key(KEY_Y, "Y  shotgun shot at the player")
	await _tick(60)
	_key(KEY_N, "N  real AI opponent (SHG1)")
	await _tick(600)
	_key(KEY_B, "B  cover wall between opponent and player")
	await _tick(400)
	print("[AimBenchProbe] done")
	quit(0)
