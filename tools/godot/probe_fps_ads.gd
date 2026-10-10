## GATE for first-person AIM DOWN SIGHTS (PLAN.md 0.43, user 2026-10-10: "yes, add FPS ADS"). A real Player picks up
## each gun and, in its own camera:
##   * FPS + aim held: the gun comes up to the eye line -- ads reaches 1, the bore is parallel to the camera's centre
##     ray (< 0.5 deg), the muzzle is on the centre line (< 1.5 cm sideways), and the gun's highest point is UNDER the
##     crosshair but close to it (0 .. 3 cm below; the 2026-10-07 rule "the gun must not block the crosshair");
##   * FPS hip and TPS aim: no ADS (ads 0) -- third person keeps its shoulder hold, the hip keeps the clip's.
##
##   godot --headless --fixed-fps 60 --path . --script tools/godot/probe_fps_ads.gd -- [--weapons=ASR1,PIS1] [--control]
## `--control` sets the recoil modifier's adsSpeed to 0 (no ADS): the FPS cases must FAIL.
extends SceneTree

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const WEAPON := "res://src/main/resources/com/openworld/weapon/%s.tscn"

var _pass := 0
var _fail := 0

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

func _check(ok: bool, what: String) -> void:
	print("  %s  %s" % ["PASS" if ok else "FAIL", what])
	if ok:
		_pass += 1
	else:
		_fail += 1

func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
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
	await _tick(3)
	for wname in _arg("weapons", "ASR1,PIS1,SMG1,SHG1").split(","):
		var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
		world.add_child(p)
		p.position = Vector3(0, 1.2, 0)
		await _tick(40)
		if control:
			for m in _find(p, "Skeleton3D").get_children():
				if m.get_script() != null and String(m.get_script().resource_path).ends_with("WeaponRecoilModifier.java"):
					m.set("ads_speed", 0.0)
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
		var top: float = gun.call("sight_top_above_bore")
		print("== %s (in %s), top of the gun %.3f m over the bore" % [wname, gun.get_parent().name, top])
		for c in [["TPS aim", false, true], ["FPS hip", true, false], ["FPS aim", true, true]]:
			p.set("is_fps_mode", c[1])
			if c[2]:
				Input.action_press("aim")
			await _tick(120)
			var ads: float = wc.call("aim_down_sights_now")
			var cam: Camera3D = root.get_viewport().get_camera_3d()
			var inv: Transform3D = cam.global_transform.affine_inverse()
			var mz: Node3D = _find(gun, "Muzzle") as Node3D
			var mp: Vector3 = inv * mz.global_position
			var d: Vector3 = inv.basis * (-mz.global_transform.basis.z)
			var off: float = rad_to_deg(Vector3(0, 0, -1).angle_to(d.normalized()))
			var gun_top: float = mp.y + top
			print("  %s: ads %.2f, muzzle (%+.3f, %+.3f, %+.3f), bore %.2f deg off the centre ray, top of the gun %+.3f m"
				% [c[0], ads, mp.x, mp.y, mp.z, off, gun_top])
			if c[0] == "FPS aim":
				_check(ads > 0.99, "%s FPS aim: the gun is up at the eye line (ads %.2f)" % [wname, ads])
				_check(off < 0.5, "%s FPS aim: bore parallel to the centre ray (%.2f deg)" % [wname, off])
				_check(absf(mp.x) < 0.015, "%s FPS aim: muzzle on the centre line (%+.3f m)" % [wname, mp.x])
				_check(gun_top < 0.0 and gun_top > -0.03, "%s FPS aim: top of the gun just under the crosshair (%+.3f m)" % [wname, gun_top])
			else:
				_check(ads < 0.01, "%s %s: no ADS (ads %.2f)" % [wname, c[0], ads])
			Input.action_release("aim")
			await _tick(30)
		p.queue_free()
		gun.queue_free()
		await _tick(5)
	print("probe_fps_ads: %d passed, %d failed%s" % [_pass, _fail, " (CONTROL)" if control else ""])
	quit(0 if _fail == 0 else 1)
