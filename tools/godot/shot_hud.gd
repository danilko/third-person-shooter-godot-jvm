extends SceneTree
## Screenshots of the in-game HUD (needs a display): on foot with a full loadout, a kill feed and the minimap,
## then seated in a car at speed. The real HUDManager wired to a real Player, so what is saved is what a player sees.
##
##   /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --path . --script tools/godot/shot_hud.gd -- <out_dir>

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const HUD := "res://src/main/resources/com/openworld/ui/HUDManager.tscn"
const CAR := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
const WEAPONS := ["SNR1", "PIS1", "MEW1", "FRG1"]
var out := "user://shot_hud"

func _tick(n: int) -> void:
	for i in range(n):
		await process_frame

func _snap(name: String) -> void:
	RenderingServer.force_draw()
	await process_frame
	root.get_texture().get_image().save_png(out + "/" + name + ".png")
	print("saved ", out + "/" + name + ".png")

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() > 0:
		out = args[0]
	DirAccess.make_dir_recursive_absolute(out)
	root.size = Vector2i(1920, 1080)
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.55, 0.65, 0.75)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color(0.7, 0.7, 0.7)
	world.add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, 30, 0)
	world.add_child(sun)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	cs.shape = BoxShape3D.new()
	(cs.shape as BoxShape3D).size = Vector3(400, 2, 400)
	floor.add_child(cs)
	var mesh := MeshInstance3D.new()
	mesh.mesh = BoxMesh.new()
	(mesh.mesh as BoxMesh).size = Vector3(400, 2, 400)
	floor.add_child(mesh)
	floor.position = Vector3(0, -1, 0)
	world.add_child(floor)
	var hud: Node = (load(HUD) as PackedScene).instantiate()
	root.add_child(hud)
	await _tick(2)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate()
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
	await _tick(30)
	for id in WEAPONS:
		var g: Node3D = (load("res://src/main/resources/com/openworld/weapon/%s.tscn" % id) as PackedScene).instantiate()
		world.add_child(g)
		g.global_position = p.global_position + Vector3(0, 0.3, 0)
		await _tick(30)
	var bus := root.get_node_or_null("/root/EventBus")
	if bus != null:
		for k in 3:
			# attacker, attacker faction, victim, victim faction, weapon, icon, headshot (EventBus.characterEliminated)
			bus.emit_signal("character_eliminated", "Player", "player", "Enemy %d" % k, "enemy", "ASR-1", null, k == 1)
	await _tick(20)
	await _snap("hud_foot")
	var wc: Node = p.get_node("WeaponController")
	wc.call("on_set_weapon", 1)          # a switch: the inventory column pops up
	await _tick(50)
	await _snap("hud_foot_switch")
	await _tick(240)
	await _snap("hud_foot_rest")
	Input.action_press("aim")      # the SNR1 is in hand: scope in
	await _tick(90)
	await _snap("hud_scope")
	Input.action_release("aim")
	await _tick(60)

	var car: RigidBody3D = (load(CAR) as PackedScene).instantiate()
	world.add_child(car)
	car.global_position = p.global_position + Vector3(4, 1.0, 0)
	await _tick(20)
	var helper: Node = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
	world.add_child(helper)
	helper.call("seat_driver", car, p)
	await _tick(20)
	car.linear_velocity = -car.global_basis.z * 16.0
	car.get_node("Health").call("apply_replicated_health", float(car.get_node("Health").get("max_health")) * 0.45)
	helper.call("flatten_tire", car, 1)        # the damage diagram: amber body, one red wheel
	await _tick(150)       # past the inventory column's fade
	await _snap("hud_vehicle")
	quit()
