extends SceneTree
## Overlays layer on a body's INPUT CONTEXT STACK (PLAN.md AR4 input half, 2026-10-10: control.InputContextStack).
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_input_contexts.gd
##   (under xvfb-run -a without --headless it also checks the pointer mode)
##
## A real Player with the real HUD (WorldSystems.tscn). Open the MAP, then hold the WEAPON WHEEL over it, then close the
## map while the wheel is still held: the body must stay blocked (and the pointer free) because the wheel is still
## open -- before, every overlay wrote one `inputBlocked` boolean, so closing the map handed the input and a captured
## pointer back under the open wheel. Release the wheel: the body is free again. Then a stray wheel RELEASE (no press,
## as after a reload refused the press) while the map is open must not unblock the body either.
## Control: `--legacy` makes the map's close also clear the wheel's entry -- what the old single flag did -- and the
## "still blocked under the wheel" case must FAIL.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const SYSTEMS := "res://src/main/resources/com/openworld/world/WorldSystems.tscn"

var fails := 0
var legacy := false
var headless := true

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _action(action: String, pressed: bool) -> void:
	var ev := InputEventAction.new()
	ev.action = action
	ev.pressed = pressed
	Input.parse_input_event(ev)
	await process_frame
	await _tick(3)

func _state(p: Node) -> String:
	var s := "[%s] blocked=%s" % [p.call("input_contexts_now"), p.call("input_blocked_now")]
	if not headless:
		s += " mouse=%d" % Input.mouse_mode
	return s

func _cursor_free() -> bool:
	return headless or Input.mouse_mode == Input.MOUSE_MODE_VISIBLE

func _cursor_captured() -> bool:
	return headless or Input.mouse_mode == Input.MOUSE_MODE_CAPTURED

func _initialize() -> void:
	legacy = "--legacy" in OS.get_cmdline_user_args()
	headless = DisplayServer.get_name() == "headless"
	var world := Node3D.new()
	root.add_child(world)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(100, 2, 100)
	cs.shape = sh
	floor.add_child(cs)
	world.add_child(floor)
	floor.position = Vector3(0, -1, 0)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(0, 1.0, 0)
	var sys: Node = (load(SYSTEMS) as PackedScene).instantiate()
	world.add_child(sys)
	await _tick(60)
	print("start: %s" % _state(p))
	_check("nothing holds the body at the start", not bool(p.call("input_blocked_now")), _state(p))

	await _action("map", true)
	await _action("map", false)
	_check("the map is open and holds the body", bool(p.call("input_blocked_now")) and _cursor_free(), _state(p))

	await _action("radialmenu", true)
	_check("the wheel opens over the map", String(p.call("input_contexts_now")).ends_with("radial:MENU"), _state(p))

	await _action("map", true)   # toggles the map shut
	await _action("map", false)
	if legacy:
		p.call("pop_input_context", "radial")   # the old ONE flag: the map's close cleared the wheel's hold too
	_check("map closed, the wheel still held: STILL blocked, pointer free",
		bool(p.call("input_blocked_now")) and _cursor_free(), _state(p))

	await _action("radialmenu", false)
	_check("wheel released: the body is free, pointer captured",
		not bool(p.call("input_blocked_now")) and _cursor_captured(), _state(p))

	await _action("map", true)
	await _action("map", false)
	await _action("radialmenu", false)   # a stray release: no wheel was shown
	_check("a stray wheel release does not free the body under the map", bool(p.call("input_blocked_now")), _state(p))
	await _action("map", true)
	await _action("map", false)
	_check("map closed: free again", not bool(p.call("input_blocked_now")), _state(p))

	print("RESULT: %s (%d failure(s))%s" % ["PASS" if fails == 0 else "FAIL", fails, " [legacy control]" if legacy else ""])
	quit(0 if fails == 0 else 1)
