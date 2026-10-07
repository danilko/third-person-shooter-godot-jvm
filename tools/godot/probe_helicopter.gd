extends SceneTree
## THE HELICOPTER CARRIER (PLAN.md W6, user 2026-10-06; carrier/helicopter/Helicopter.java, model HLC1).
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_helicopter.gd [-- --control]
##   (--control: the Airplane script in place of the Helicopter's -- it must not hover or orbit)
##
## On a bare stand (a floor), a real Player:
##   1. parked with nobody aboard, it rests on the floor (no drift, rotor still);
##   2. a seated player holding the climb key (space = handbrake) climbs it (> 10 m in 4 s) and it HOVERS when let go (holds height within 2 m);
##   3. holding FORWARD moves it along its heading (> 15 m in 3 s), holding steer turns it (> 30 deg in 3 s);
##   4. empty again with an AI target set, it climbs to its orbit and holds it: 25-55 m over the target, within
##      90 m of it, after 25 s.

const HELI := "res://src/main/resources/com/openworld/vehicle/HLC1.tscn"
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"

var fails := 0


func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1


func _tick(n: int) -> void:
	for i in n:
		await physics_frame


func _press(a: String, frames: int) -> void:
	Input.action_press(a)
	await _tick(frames)
	Input.action_release(a)


func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	var floor_body := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(400, 1, 400)
	cs.shape = box
	floor_body.add_child(cs)
	floor_body.position = Vector3(0, -0.5, 0)
	world.add_child(floor_body)
	var cam := Camera3D.new()
	world.add_child(cam)
	cam.position = Vector3(0, 20, 40)
	var h: RigidBody3D = (load(HELI) as PackedScene).instantiate()
	if control:
		h.set_script(load("res://src/main/java/com/openworld/carrier/aircraft/Airplane.java"))
	world.add_child(h)
	h.global_position = Vector3(0, 2.5, 0)
	await _tick(180)
	var rest := h.global_position
	await _tick(120)
	_check(h.global_position.distance_to(rest) < 0.2 and h.global_position.y < 3.0, "parked, it rests on the floor (%.2f m drift, y %.2f)" % [h.global_position.distance_to(rest), h.global_position.y])
	var p: CharacterBody3D = (load(PLAYER) as PackedScene).instantiate()
	p.position = Vector3(4, 1, 0)       # BEFORE add_child: one frame at the origin inside the hull launches it
	world.add_child(p)
	p.get_node("Health").set("invulnerable", true)
	await _tick(30)
	var helper: Node = load(HELPER).new()
	world.add_child(helper)
	p.collision_layer = 0          # seating moves the body into the hull; the real entry path clears it first
	p.collision_mask = 0
	helper.call("seat_character", h, p)
	await _tick(30)
	var y0 := h.global_position.y
	await _press("handbrake", 240)
	var y1 := h.global_position.y
	_check(y1 - y0 > 10.0, "holding the climb key (space = handbrake) climbs (%.1f m in 4 s)" % (y1 - y0))
	await _tick(60)                      # let the climb's momentum settle (it glides on a few metres)
	var y1b := h.global_position.y
	await _tick(120)
	var y2 := h.global_position.y
	_check(absf(y2 - y1b) < 1.0 and y2 > 8.0, "let go, it HOVERS (moved %.2f m over 2 s, at %.1f m)" % [y2 - y1b, y2])
	var x0 := h.global_position
	await _press("forward", 180)
	_check(h.global_position.distance_to(x0) > 15.0, "holding FORWARD flies it (%.1f m in 3 s)" % h.global_position.distance_to(x0))
	var yaw0 := h.global_rotation.y
	await _press("left", 180)
	var turned := rad_to_deg(absf(wrapf(h.global_rotation.y - yaw0, -PI, PI)))
	_check(turned > 30.0, "holding steer turns it (%.0f deg in 3 s)" % turned)
	# the AI's orbit: the player gets out (fly on alone with a target)
	helper.call("exit_driver", h)
	await _tick(30)
	var target := Node3D.new()
	world.add_child(target)
	target.global_position = Vector3(60, 0, 60)
	h.set("ai_target", target)
	await _tick(60 * 25)
	var hp := h.global_position
	var flat := Vector2(hp.x - target.global_position.x, hp.z - target.global_position.z).length()
	var over := hp.y - target.global_position.y
	_check(over > 25.0 and over < 55.0 and flat < 90.0, "the AI orbits its target (%.1f m over, %.1f m out)" % [over, flat])
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
