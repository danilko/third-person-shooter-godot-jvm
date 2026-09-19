extends SceneTree
## The Binbun3D VFX (assets/vfx/, CC0) driven by Java (com.openworld.vfx): every effect scene loads on its
## Java script with no GDScript left, muzzle flashes point down −Z and own their materials, a flash lights
## and goes dark, ExplosionManager pools and reuses blasts, a smoke plume switches on and off, and the game
## scenes are wired to them.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_vfx.gd

const VFX := "res://assets/vfx"
const JAVA := "res://src/main/java/com/openworld/vfx/"
const SCRIPT_OF := {"explosion": "VfxEffect.java", "muzzle_flash": "MuzzleFlashVfx.java", "smoke": "SmokeVfx.java"}
const WEAPONS := ["ASR1", "ASR2", "SMG1", "PIS1", "REV1", "SHG1", "SNR1", "ATL1"]
const EXPLOSION_MANAGER := "res://src/main/java/com/openworld/world/manager/ExplosionManager.java"

var fails := 0
var stand: Node3D

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _files(dir: String, ext: String) -> Array[String]:
	var out: Array[String] = []
	var d := DirAccess.open(dir)
	if d == null:
		return out
	for f in d.get_files():
		if f.ends_with(ext):
			out.append(dir + "/" + f)
	for sub in d.get_directories():
		out.append_array(_files(dir + "/" + sub, ext))
	return out

func _script_path(n: Node) -> String:
	var s: Script = n.get_script()
	return s.resource_path if s != null else ""

func _energy(light: Node) -> float:
	return (light as Light3D).light_energy

func _initialize() -> void:
	stand = Node3D.new()
	root.add_child(stand)
	await _tick(2)
	print("== 1. every effect scene is on its Java script; no GDScript is left")
	_check("no .gd under assets/vfx", _files(VFX, ".gd").is_empty(), str(_files(VFX, ".gd")))
	for kind in SCRIPT_OF:
		var scenes := _files(VFX + "/" + kind + "/effects", ".tscn")
		var bad: Array[String] = []
		for path in scenes:
			var ps := load(path) as PackedScene
			var inst: Node = ps.instantiate() if ps != null else null
			if inst == null or _script_path(inst) != JAVA + SCRIPT_OF[kind]:
				bad.append(path.get_file())
			for c in (inst.get_children() if inst != null else []):
				if c is OmniLight3D and _script_path(c) != JAVA + "VfxLight.java":
					bad.append(path.get_file() + ":" + c.name)
			if inst != null:
				inst.free()
		_check("%s: %d scenes on %s" % [kind, scenes.size(), SCRIPT_OF[kind]], bad.is_empty() and scenes.size() > 0, str(bad))

	print("== 2. muzzle flashes point down -Z (the Muzzle marker's forward)")
	var off: Array[String] = []
	for path in _files(VFX + "/muzzle_flash/effects", ".tscn"):
		var fx: Node3D = (load(path) as PackedScene).instantiate()
		stand.add_child(fx)
		var glow := fx.get_node_or_null("Glow") as Node3D
		if glow == null or glow.position.z > -0.1 or Vector2(glow.position.x, glow.position.y).length() > 0.001:
			off.append("%s glow %s" % [path.get_file(), glow.position if glow else "missing"])
		for c in fx.get_children():
			# a long/side flash is a quad offset along its own +Y: that axis must be the barrel's
			if c is GPUParticles3D and (c.name == "Flash_Long" or c.name == "Flash_Side") \
					and (c as Node3D).basis.y.dot(Vector3(0, 0, -1)) < 0.999:
				off.append("%s %s +Y %s" % [path.get_file(), c.name, (c as Node3D).basis.y])
		fx.free()
	_check("every flash: glow on the -Z axis, long/side flashes along -Z", off.is_empty(), str(off))

	print("== 3. a flash lights on play and goes dark; instances do not share materials")
	var ps3 := load(VFX + "/muzzle_flash/effects/muzzle_flash/muzzle_flash_01.tscn") as PackedScene
	var a: Node3D = ps3.instantiate()
	var b: Node3D = ps3.instantiate()
	stand.add_child(a)
	stand.add_child(b)
	await _tick(2)
	var la := a.get_node("Light")
	var glow_a := func(fx: Node) -> float:
		return float((fx.get_node("Glow") as GeometryInstance3D).material_override.get_shader_parameter("alpha_multiplier"))
	_check("dark before the first shot (light and glow)", _energy(la) == 0.0 and glow_a.call(a) == 0.0,
		"energy %.3f glow %.2f" % [_energy(la), glow_a.call(a)])
	var ga := (a.get_node("Glow") as GeometryInstance3D).material_override
	var gb := (b.get_node("Glow") as GeometryInstance3D).material_override
	_check("each instance owns its glow material", ga != gb and ga != null)
	var shared := load(VFX + "/muzzle_flash/material/flash_01/flash_01_glow.tres")
	_check("the colour is the effect's, not the shared .tres", ga.get_shader_parameter("primary_color") == a.get("primary_color")
		and shared.get_shader_parameter("primary_color") != a.get("primary_color"),
		"%s" % ga.get_shader_parameter("primary_color"))
	a.call("play")
	await _tick(2)
	_check("lit right after play", _energy(la) > 0.5, "energy %.3f" % _energy(la))
	_check("its emitters emit", (a.get_node("Flash_Long") as GPUParticles3D).emitting)
	_check("lit glow right after play", glow_a.call(a) > 0.5, "glow %.2f" % glow_a.call(a))
	_check("the other instance stays dark", _energy(b.get_node("Light")) == 0.0 and glow_a.call(b) == 0.0)
	await _tick(30)
	_check("dark again after the flash (0.2 s)", _energy(la) < 0.01 and glow_a.call(a) < 0.01 and not a.call("playing_now"),
		"energy %.3f glow %.2f" % [_energy(la), glow_a.call(a)])
	a.free()
	b.free()

	print("== 4. every weapon's Muzzle/MuzzleVFX is a flash pointing out of the barrel")
	for w in WEAPONS:
		var gun: Node3D = (load("res://src/main/resources/com/openworld/weapon/%s.tscn" % w) as PackedScene).instantiate()
		stand.add_child(gun)
		await _tick(1)
		var fx := gun.get_node_or_null("Muzzle/MuzzleVFX") as Node3D
		var ok := fx != null and _script_path(fx) == JAVA + "MuzzleFlashVfx.java"
		var ahead := 0.0
		if ok:
			var muzzle := gun.get_node("Muzzle") as Node3D
			var glow := fx.get_node("Glow") as Node3D
			var d := glow.global_position - muzzle.global_position
			ahead = d.dot(-muzzle.global_basis.z)
			ok = ok and (d - (-muzzle.global_basis.z) * ahead).length() < 0.001
		_check("%s flash under the muzzle, glow %.2f m out along the barrel" % [w, ahead], ok and ahead > 0.1)
		if fx != null:
			var ga2 := float((fx.get_node("Glow") as GeometryInstance3D).material_override.get_shader_parameter("alpha_multiplier"))
			_check("%s flash dark while the gun lies unfired" % w, ga2 == 0.0 and _energy(fx.get_node("Light")) == 0.0, "glow %.2f" % ga2)
		gun.free()

	print("== 5. ExplosionManager pools blasts and reuses the oldest when all are busy")
	var em: Node = load(EXPLOSION_MANAGER).new()
	em.set("explosion_scene", load(VFX + "/explosion/effects/ground/vfx_ground_explosion_01.tscn"))
	em.set("pool_size", 3)
	stand.add_child(em)
	await _tick(1)
	_check("pool of 3 blast effects", em.get_child_count() == 3, "%d" % em.get_child_count())
	for i in range(4):
		em.call("spawn_explosion", Vector3(10.0 * i, 0, 0))
		await _tick(1)
	var playing := 0
	var xs: Array = []
	for c in em.get_children():
		playing += 1 if c.call("playing_now") else 0
		xs.append(c.global_position.x)
	xs.sort()
	_check("all three playing", playing == 3, "%d" % playing)
	_check("the 4th blast took the oldest effect (x 10, 20, 30)", xs == [10.0, 20.0, 30.0], str(xs))
	var lit := false
	for c in em.get_children():
		for l in c.get_children():
			if l is OmniLight3D and _energy(l) > 0.1:
				lit = true
	_check("a blast lights its light", lit)
	await _tick(200)
	playing = 0
	for c in em.get_children():
		playing += 1 if c.call("playing_now") else 0
	_check("all done after 3.3 s", playing == 0, "%d" % playing)
	# sizing: a blast of radius R draws its fireball over R/2 and its shockwave out to R (ExplosionManager.playBlast)
	var helper: Node = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
	stand.add_child(helper)
	helper.call("blast", em, Vector3(0, 0, 50), 7.0, 0.0)
	await _tick(1)
	var sized: Node3D = null
	for c in em.get_children():
		if c.global_position.z > 49.0:
			sized = c
	var fire := float(sized.get("fireball_radius")) * sized.scale.x
	var wave := float(sized.get("blast_radius")) * sized.scale.x * (sized.get_node("Rings") as Node3D).scale.x
	_check("a 7 m blast: fireball over 3.5 m, shockwave out to 7 m", absf(fire - 3.5) < 0.01 and absf(wave - 7.0) < 0.01,
		"fireball %.2f m, shockwave %.2f m" % [fire, wave])
	var unmeasured := 0
	for path in _files(VFX + "/explosion/effects", ".tscn"):
		var t := FileAccess.get_file_as_string(path)
		if not (t.contains("blast_radius = ") and t.contains("fireball_radius = ")):
			unmeasured += 1
	_check("every explosion effect carries its measured radii", unmeasured == 0, "%d unmeasured" % unmeasured)
	em.free()

	print("== 6. a smoke plume switches on and off")
	var sm: Node3D = (load(VFX + "/smoke/effects/smoke_thin/smoke_thin_vfx_01.tscn") as PackedScene).instantiate()
	sm.set("emitting", false)
	stand.add_child(sm)
	await _tick(1)
	var em_all := func(n: Node) -> Array:
		var out := []
		for c in n.get_children():
			if c is GPUParticles3D:
				out.append(c.emitting)
		return out
	_check("starts off when asked", em_all.call(sm) == [false, false], str(em_all.call(sm)))
	sm.set("emitting", true)
	_check("turns on (plume + shadow caster)", em_all.call(sm) == [true, true], str(em_all.call(sm)))
	sm.free()

	print("== 7. the game scenes are wired to the packs")
	var car: Node = (load("res://src/main/resources/com/openworld/vehicle/SPC1.tscn") as PackedScene).instantiate()
	var dmg := car.get_node_or_null("DamageVfx/Smoke")
	_check("Vehicle DamageVfx/Smoke is a SmokeVfx, off", dmg != null and _script_path(dmg) == JAVA + "SmokeVfx.java"
		and dmg.get("emitting") == false)
	car.free()
	var wreck: Node = (load("res://src/main/resources/com/openworld/vehicle/VehicleWreck.tscn") as PackedScene).instantiate()
	var ws := wreck.get_node_or_null("Smoke")
	_check("VehicleWreck Smoke is a SmokeVfx, on", ws != null and _script_path(ws) == JAVA + "SmokeVfx.java" and ws.get("emitting") == true)
	wreck.free()
	var sys_scene := FileAccess.get_file_as_string("res://src/main/resources/com/openworld/world/WorldSystems.tscn")
	_check("WorldSystems' ExplosionManager plays a pack blast", sys_scene.contains("explosion_scene = ExtResource") and
		sys_scene.contains("res://assets/vfx/explosion/effects/"))
	for w in ["World", "DebugWorld"]:
		var t := FileAccess.get_file_as_string("res://src/main/resources/com/openworld/world/%s.tscn" % w)
		_check("%s's sea uses assets/vfx/water/water_toon.gdshader" % w, t.contains("res://assets/vfx/water/water_toon.gdshader"))
	var toon := load(VFX + "/water/water_toon.gdshader") as Shader
	_check("water_toon includes the shared body with the distance LOD", toon != null and toon.code.contains("water_common.gdshaderinc")
		and FileAccess.get_file_as_string(VFX + "/water/water_common.gdshaderinc").contains("detail_fade_start"))

	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails > 0 else 0)
