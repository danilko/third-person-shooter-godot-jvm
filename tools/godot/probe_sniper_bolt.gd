extends SceneTree
## SR3's bolt works on every shot (PLAN.md 2.7 piece 6): the handle is its own node (`Model/Bolt`, split out of
## the model), and `fire_animation = "bolt_cycle"` plays on the weapon's own AnimationPlayer (W13) — lift about
## the bore, draw back 4 cm, run home, lower — inside the 1.46 s fire interval, back at rest before the next shot.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_sniper_bolt.gd   [-- --control]
##
## Measured on the bolt node's local transform through a real pickup and a real `fire` press. `--control`
## clears fire_animation: the bolt must not move.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const SR3 := "res://src/main/resources/com/openworld/weapon/SR3.tscn"
var fails := 0

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-52s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	var world := Node3D.new()
	root.add_child(world)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(60, 2, 60)
	cs.shape = sh
	floor.add_child(cs)
	world.add_child(floor)
	floor.position = Vector3(0, -1, 0)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate()
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
	await _tick(40)
	var gun: Node3D = (load(SR3) as PackedScene).instantiate()
	world.add_child(gun)
	gun.global_position = p.global_position + Vector3(0, 0.3, 0)
	await _tick(30)
	var wc: Node = p.get_node("WeaponController")
	for slot in range(7):
		if String(gun.get_parent().name).begins_with("Socket"):
			break
		wc.call("on_set_weapon", slot)
		await _tick(40)
	if control:
		gun.set("fire_animation", "")
	var bolt: Node3D = gun.get_node("Model/Bolt")
	_check("the bolt is its own node", bolt != null, str(gun.get_path_to(bolt)) if bolt else "missing")
	Input.action_press("aim")
	await _tick(90)
	var mag0 := int(gun.get("magazine"))
	Input.action_press("fire")
	await _tick(2)
	Input.action_release("fire")
	var max_angle := 0.0
	var max_back := 0.0
	var max_up := 0.0
	var t_back := -1.0
	for f in range(int(1.46 * 60)):
		await physics_frame
		var xf := bolt.transform
		var ang := rad_to_deg(xf.basis.get_rotation_quaternion().get_angle())
		max_angle = maxf(max_angle, ang)
		# the knob tip (rest: +0.049 m right of the bore at the receiver) — how far up it went
		var tip := xf * Vector3(0.049, 0.061, -0.045)
		max_up = maxf(max_up, tip.y - 0.061)
		max_back = maxf(max_back, xf.origin.z - (xf.basis * Vector3(0, 0, 0)).z)
		if xf.origin.z > 0.035 and t_back < 0.0:
			t_back = f / 60.0
	Input.action_release("aim")
	var rest := bolt.transform
	_check("the shot fired", int(gun.get("magazine")) == mag0 - 1, "mag %d -> %d" % [mag0, int(gun.get("magazine"))])
	if control:
		_check("control: no fire_animation, the bolt does not move", max_angle < 0.5 and max_back < 0.005, "angle %.1f back %.3f" % [max_angle, max_back])
	else:
		_check("the handle lifts ~60 deg about the bore", absf(max_angle - 60.0) < 3.0, "%.1f deg" % max_angle)
		_check("the knob rises, not falls", max_up > 0.03, "tip up %.3f m" % max_up)
		_check("the bolt draws back ~4 cm", max_back > 0.035, "%.3f m (at %.2f s)" % [max_back, t_back])
		_check("the bolt is home before the next shot is allowed", rest.origin.length() < 0.002 and rad_to_deg(rest.basis.get_rotation_quaternion().get_angle()) < 0.5,
			"after the 1.46 s cycle: offset %.4f m, angle %.2f deg" % [rest.origin.length(), rad_to_deg(rest.basis.get_rotation_quaternion().get_angle())])
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
