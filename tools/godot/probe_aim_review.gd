extends SceneTree
## The one place to LOOK at every body x weapon x stance, on the shipped path.
##
##   godot --headless --fixed-fps 60 --path . --script tools/godot/probe_aim_review.gd 2>&1 | grep AimBench
##
## It asserts NOTHING, on purpose. The gates (`probe_weapon_fit`, `probe_weapon_holster`,
## AimDebugAuto) answer "did this regress"; the Blender side (`pose_weapon_hold.py measure`) answers
## "what does the CLIP carry, before any modifier". This answers "show me", which is the question
## that had no single home: `V`+`M` cover body x weapon at ONE stance and `probe_weapon_fit` covers
## weapon x stance for ONE body per run, so judging a shared pose meant stitching two tools together.
##
## Each line is body / stance / weapon and then the three numbers that decide whether a SHARED pose
## fits THIS body with THIS weapon: how far the stock mount had to drag the firing hand and whether
## it still fell short, the support hand's grip miss with the reach it was asked for against the
## reach that arm HAS and the shoulder that cost, and the gun's angle off what the body aims at.
##
## Read `gun` last: the stand spawns the mannequin facing away from the aim ball, so until the ball
## is moved round in front that number is measuring the stance's yaw clamp, not the pose.

const BENCH := "res://src/main/resources/com/openworld/world/hosts/AimWorkbench.tscn"
var host: Node

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _key(code: Key, shift: bool) -> void:
	var ev := InputEventKey.new()
	ev.physical_keycode = code
	ev.pressed = true
	ev.shift_pressed = shift
	host.call("_input", ev)

func _initialize() -> void:
	host = (load(BENCH) as PackedScene).instantiate()
	root.add_child(host)
	await _tick(150)
	# NOT `4`: that key TOGGLES combat and the mannequin spawns in it, so pressing it turns the aim
	# branch off. The review sets combat on itself, and turns the body onto the ball.
	await _tick(60)
	_key(KEY_M, true)                  # shift+M: the whole matrix
	# bodies x stances x weapons, each cell a respawn plus the shipped equip
	await _tick(60 * 60 * 6)
	quit()
