extends SceneTree
## Screenshots of the Binbun3D VFX in the real renderer (needs a display): a muzzle flash on each weapon
## from the side, each explosive's own blast (rocket, grenade, car) and the two smoke plumes beside a 1.49 m figure.
##
##   /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --path . --script tools/godot/shot_vfx.gd -- <out_dir>

const VFX := "res://assets/vfx"
var out := "user://shot_vfx"
var cam: Camera3D

func _snap(name: String) -> void:
	RenderingServer.force_draw()
	await process_frame
	root.get_viewport().get_texture().get_image().save_png(out + "/" + name + ".png")
	print("saved ", out + "/" + name + ".png")

func _frames(n: int) -> void:
	for i in range(n):
		await process_frame

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() > 0:
		out = args[0]
	DirAccess.make_dir_recursive_absolute(out)
	root.size = Vector2i(1280, 720)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.45, 0.55, 0.65)
	env.environment.ambient_light_color = Color(0.6, 0.6, 0.6)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.glow_enabled = true
	root.add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, 30, 0)
	root.add_child(sun)
	var ground := MeshInstance3D.new()
	ground.mesh = PlaneMesh.new()
	(ground.mesh as PlaneMesh).size = Vector2(60, 60)
	root.add_child(ground)
	var figure := MeshInstance3D.new()
	figure.mesh = CapsuleMesh.new()
	(figure.mesh as CapsuleMesh).height = 1.49
	(figure.mesh as CapsuleMesh).radius = 0.2
	root.add_child(figure)
	cam = Camera3D.new()
	root.add_child(cam)
	cam.current = true

	# muzzle flashes: the weapon 1.3 m up, seen from its right side
	figure.position = Vector3(0, 0.745, 1.0)
	for w in ["ASR1", "PIS1", "SHG1", "SNR1"]:
		var gun: Node3D = (load("res://src/main/resources/com/openworld/weapon/%s.tscn" % w) as PackedScene).instantiate()
		root.add_child(gun)
		await _frames(2)
		var body := gun.get_parent() if gun.get_parent() != root else gun
		var holder := gun
		for n in root.get_children():
			if n is RigidBody3D:
				n.freeze = true
				holder = n
		holder.global_position = Vector3(0, 1.3, 0)
		cam.global_position = Vector3(2.2, 1.4, -0.6)
		cam.look_at(Vector3(0, 1.3, -0.6))
		await _frames(3)
		gun.get_node("Muzzle/MuzzleVFX").call("play")
		await _frames(2)
		await _snap("flash_" + w)
		holder.queue_free()
		await _frames(2)

	# explosion + smoke beside the figure
	figure.position = Vector3(-3.0, 0.745, 0)
	cam.global_position = Vector3(0, 3.5, 12)
	cam.look_at(Vector3(0, 2, 0))
	# each explosive's own blast, as shipped: sized by ExplosionManager's rule (damage radius / measured shockwave
	# reach), with a red ring on the ground at the damage radius, so the two can be compared
	var W := "res://src/main/resources/com/openworld/weapon/"
	var atl: Node = (load(W + "ATL1.tscn") as PackedScene).instantiate()
	var rk: Node = (load(W + "ATL1Projectile.tscn") as PackedScene).instantiate()
	var gr: Node = (load(W + "FRG1Projectile.tscn") as PackedScene).instantiate()
	var car_cfg: Resource = ((load("res://src/main/resources/com/openworld/vehicle/SPC1.tscn") as PackedScene).instantiate()).get("vehicle_config")
	var blasts := {
		"rocket": [rk.get("explosion_vfx"), float(atl.get("explosion_radius"))],
		"grenade": [gr.get("explosion_vfx"), float(gr.get("explosion_radius"))],
		"car": [car_cfg.get("explosion_vfx"), float(car_cfg.get("explosion_radius"))],
	}
	cam.global_position = Vector3(0, 14, 22)
	cam.look_at(Vector3(0, 1, 0))
	figure.position = Vector3(-2.0, 0.745, 2.0)
	for key in blasts:
		var radius: float = blasts[key][1]
		var ring := MeshInstance3D.new()
		ring.mesh = TorusMesh.new()
		(ring.mesh as TorusMesh).inner_radius = radius - 0.08
		(ring.mesh as TorusMesh).outer_radius = radius + 0.08
		var rm := StandardMaterial3D.new()
		rm.albedo_color = Color(1, 0.1, 0.1)
		rm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		ring.material_override = rm
		ring.position = Vector3(0, 0.05, 0)
		root.add_child(ring)
		var ex: Node3D = (blasts[key][0] as PackedScene).instantiate()
		root.add_child(ex)
		# ExplosionManager.playBlast's rule: the fireball covers half the damage radius, the shockwave reaches it
		var br := float(ex.get("blast_radius"))
		var fr := float(ex.get("fireball_radius"))
		var sc := 0.5 * radius / fr if fr > 0.0 else 1.0
		ex.scale = Vector3.ONE * sc
		(ex.get_node("Rings") as Node3D).scale = Vector3.ONE * ((radius / br) / sc if br > 0.0 else 1.0)
		await _frames(2)
		ex.call("play")
		for t in [12, 30]:
			await _frames(t - (0 if t == 12 else 12))
			await _snap("blast_%s_f%d" % [key, t])
		print("%s: damage radius %.1f m -> fireball %.1f m, shockwave %.1f m (scale %.2f)" % [key, radius, fr * sc,
			br * sc * (ex.get_node("Rings") as Node3D).scale.x, sc])
		ex.queue_free()
		ring.queue_free()
		await _frames(3)
	for s in ["smoke_thin/smoke_thin_vfx_01", "smoke_big/smoke_big_vfx_01"]:
		var sm: Node3D = (load(VFX + "/smoke/effects/%s.tscn" % s) as PackedScene).instantiate()
		root.add_child(sm)
		await _frames(150)
		await _snap(s.get_file())
		sm.queue_free()
	quit()
