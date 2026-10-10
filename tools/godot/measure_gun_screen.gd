## Where the held gun sits and points in the PLAYER'S OWN camera (user 2026-10-09: "the crosshair seems not the
## centre, or the weapon not aligned, both TPS and FPS; the FPS hand gun, especially DUP, sits toward the right").
## A real Player picks up the weapon, holds `aim` (and once not, `--hip`) in TPS and FPS, and for each gun prints,
## in the active camera's frame (x right, y up, looking down -z):
##   * the muzzle's offset and its angle off the screen centre (where the gun DRAWS),
##   * the bore's yaw / pitch against the camera's forward (where the gun POINTS),
##   * the sideways miss of the bore line from the camera's centre ray at the aim point's range.
##
##   godot --headless --fixed-fps 60 --path . --script tools/godot/measure_gun_screen.gd -- [--weapons=PIS1,DUP1,ASR1] [--hip]
## `--no-mods` switches off every SkeletonModifier3D (the aim / recoil / IK layers): what the CLIP alone holds.
## `--out=<dir>` (NEEDS A DISPLAY: drop --headless, use xvfb-run -a) also saves the camera's frame per gun and view,
## with a red cross on the exact screen centre -- where the HUD's crosshair is anchored.
extends SceneTree

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const WEAPON := "res://src/main/resources/com/openworld/weapon/%s.tscn"

func _arg(name: String, def: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--%s=" % name):
			return a.substr(name.length() + 3)
	return def

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _find(n: Node, nm: String) -> Node:
	if n.name == nm:
		return n
	for c in n.get_children():
		var r: Node = _find(c, nm)
		if r != null:
			return r
	return null

func _report(label: String, cam: Camera3D, muzzle: Node3D, aim: Vector3) -> void:
	var inv: Transform3D = cam.global_transform.affine_inverse()
	var p: Vector3 = inv * muzzle.global_position
	var d: Vector3 = inv.basis * (-muzzle.global_transform.basis.z)
	var a: Vector3 = inv * aim
	# the bore line at the aim point's depth, against the camera's centre ray there
	var t: float = (a.z - p.z) / d.z if absf(d.z) > 1e-4 else 0.0
	var at: Vector3 = p + d * t
	print("    %-6s muzzle cam (%+.3f, %+.3f, %+.3f) m = %+.1f deg right, %+.1f deg up of centre | bore yaw %+.2f pitch %+.2f deg | at %.1f m the bore is %+.3f m right, %+.3f m up of the centre ray (aim point %+.3f, %+.3f)"
		% [label, p.x, p.y, p.z, rad_to_deg(atan2(p.x, -p.z)), rad_to_deg(atan2(p.y, -p.z)),
		rad_to_deg(atan2(d.x, -d.z)), rad_to_deg(atan2(d.y, Vector2(d.x, d.z).length())),
		-a.z, at.x, at.y, a.x, a.y])

func _initialize() -> void:
	var hip := "--hip" in OS.get_cmdline_user_args()
	var world := Node3D.new()
	root.add_child(world)
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(80, 1, 80)
	cs.shape = box
	b.add_child(cs)
	b.position = Vector3(0, -0.5, 0)
	world.add_child(b)
	var wall := StaticBody3D.new()   # something for the camera ray to hit 20 m ahead
	var ws := CollisionShape3D.new()
	var wb := BoxShape3D.new()
	wb.size = Vector3(40, 20, 1)
	ws.shape = wb
	wall.add_child(ws)
	world.add_child(wall)
	await _tick(3)
	for wname in _arg("weapons", "PIS1,DUP1,ASR1").split(","):
		var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
		world.add_child(p)
		p.position = Vector3(0, 1.2, 0)
		await _tick(40)
		# the wall straight ahead of where the body faces
		var mesh_root: Node3D = _find(p, "MeshRoot") as Node3D
		var fwd: Vector3 = -mesh_root.global_transform.basis.z
		fwd.y = 0
		fwd = fwd.normalized()
		wall.global_position = p.global_position + fwd * 20.0 + Vector3(0, 2, 0)
		wall.look_at(p.global_position + Vector3(0, 2, 0))
		var gun: Node3D = (load(WEAPON % wname) as PackedScene).instantiate() as Node3D
		world.add_child(gun)
		gun.global_position = p.global_position + Vector3(0, 0.3, 0)
		await _tick(30)
		var wc: Node = p.get_node_or_null("WeaponController")
		for slot in range(6):
			if String(gun.get_parent().name).begins_with("Socket"):
				break
			wc.call("on_set_weapon", slot)
			await _tick(50)
		print("== %s (in %s)" % [wname, gun.get_parent().name])
		for fps in [false, true]:
			p.set("is_fps_mode", fps)
			if not hip:
				Input.action_press("aim")
			await _tick(150)
			if "--no-mods" in OS.get_cmdline_user_args():
				for m in _find(p, "Skeleton3D").get_children():
					if m is SkeletonModifier3D:
						m.active = false
				await _tick(10)
			var cam: Camera3D = root.get_viewport().get_camera_3d()
			var aim_node: Node3D = _find(p, "AimTarget") as Node3D
			var aim: Vector3 = aim_node.global_position if aim_node != null else cam.global_position - cam.global_transform.basis.z * 20.0
			var body: Vector3 = cam.global_transform.affine_inverse() * mesh_root.global_position
			print("  %s %s: camera %s, body centre %+.3f m right of the camera, ads %.2f" % ["FPS" if fps else "TPS", "hip" if hip else "aim", cam.get_path(), body.x, wc.call("aim_down_sights_now")])
			var m: Node3D = _find(gun, "Muzzle") as Node3D
			if m != null:
				_report("right", cam, m, aim)
			var ml: Node3D = _find(p, "MuzzleLeft") as Node3D
			if ml != null and ml.is_visible_in_tree():
				_report("left", cam, ml, aim)
			var out := _arg("out", "")
			if out != "":
				await process_frame
				await RenderingServer.frame_post_draw
				var img: Image = root.get_viewport().get_texture().get_image()
				var c := Vector2i(img.get_width() / 2, img.get_height() / 2)
				for k in range(-14, 15):
					for w in range(-1, 2):
						img.set_pixel(c.x + k, c.y + w, Color.RED)
						img.set_pixel(c.x + w, c.y + k, Color.RED)
				DirAccess.make_dir_recursive_absolute(out)
				img.save_png("%s/%s_%s_%s.png" % [out, wname, "fps" if fps else "tps", "hip" if hip else "aim"])
			Input.action_release("aim")
		p.queue_free()
		gun.queue_free()
		await _tick(5)
	quit(0)
