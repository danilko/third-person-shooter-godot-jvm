extends SceneTree
## Explosives beat bullets on vehicles, and people stay as they were: the damage kinds on Health
## (hitDamageMultiplier / explosionDamageMultiplier) and blast distance measured to the target's SURFACE.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_explosive_damage.gd [-- --control]
##
## --control puts the car's damage kinds back to 1.0 / 1.0 (the old behaviour): the sniper then kills a car in
## 4 rounds and every explosive case on the car fails.
##
## Real Vehicle.tscn and AICharacter.tscn bodies; the rocket and grenade numbers are read off ATL1.tscn and
## FRG1Projectile.tscn and the bullet numbers off the weapon stats, so the probe asserts the shipped tuning.
## Blasts go through ExplosionManager.triggerExplosion and hits through ImpactManager.processHit (the paths
## every rocket, grenade and bullet take), via debug/VehicleProbeHelper.

const W := "res://src/main/resources/com/openworld/weapon/"
const CAR := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"

var fails := 0
var helper: Node
var em: Node
var im: Node
var stand: Node3D

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", label, detail])

func _car() -> RigidBody3D:
	var c: RigidBody3D = (load(CAR) as PackedScene).instantiate()
	stand.add_child(c)
	c.global_position = Vector3(0, 5, 0)
	c.freeze = true
	if OS.get_cmdline_user_args().has("--control"):
		c.get_node("Health").set("hit_damage_multiplier", 1.0)
		c.get_node("Health").set("explosion_damage_multiplier", 1.0)
	await physics_frame
	await physics_frame
	return c

func _ai(at: Vector3) -> Node3D:
	var a: Node3D = (load(AI) as PackedScene).instantiate()
	stand.add_child(a)
	a.global_position = at
	await physics_frame
	await physics_frame
	return a

func _hp(n: Node) -> float:
	return float(n.get_node("Health").call("health_now"))

func _rocket_on_car(offset_m: float) -> float:
	var c := await _car()
	var hp0 := _hp(c)
	# the hull's side is 1.0 m from the car's centre line
	helper.call("blast", em, c.global_position + Vector3(1.0 + offset_m, 0.2, 0), rocket_r, rocket_d)
	await physics_frame
	var lost := hp0 - _hp(c)
	c.free()
	return lost

var rocket_r: float
var rocket_d: float
var grenade_r: float
var grenade_d: float

func _initialize() -> void:
	stand = Node3D.new()
	root.add_child(stand)
	helper = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
	em = load("res://src/main/java/com/openworld/world/manager/ExplosionManager.java").new()
	im = load("res://src/main/java/com/openworld/world/manager/ImpactManager.java").new()
	stand.add_child(helper)
	stand.add_child(em)
	stand.add_child(im)
	var atl: Node = (load(W + "ATL1.tscn") as PackedScene).instantiate()
	rocket_r = atl.get("explosion_radius"); rocket_d = atl.get("explosion_max_damage")
	atl.free()
	var frg: Node = (load(W + "FRG1Projectile.tscn") as PackedScene).instantiate()
	grenade_r = frg.get("explosion_radius"); grenade_d = frg.get("explosion_max_damage")
	frg.free()
	var snr := float((load(W + "stats/SNR1.tres")).get("damage"))
	var asr := float((load(W + "stats/ASR1.tres")).get("damage"))
	await physics_frame
	print("rocket %.0f over %.1f m, grenade %.0f over %.1f m, SNR1 %.0f, ASR1 %.0f" % [rocket_d, rocket_r, grenade_d, grenade_r, snr, asr])

	print("== 1. a car (500 HP) folds to a rocket and soaks bullets")
	var probe := await _car()
	var car_hp := _hp(probe)
	helper.call("weapon_hit", im, probe, snr)
	await physics_frame
	var per_snr := car_hp - _hp(probe)
	probe.free()
	_check("one SNR1 round takes %.0f of a car's %.0f" % [per_snr, car_hp], is_equal_approx(per_snr, snr * 0.4))
	_check("SNR1 needs 8+ rounds for a car (was 4)", ceili(car_hp / per_snr) >= 8, "%d rounds" % ceili(car_hp / per_snr))
	var per_asr := asr * per_snr / snr        # the same measured multiplier
	_check("ASR1 needs over a magazine (30) for a car", ceili(car_hp / per_asr) > 30, "%d rounds" % ceili(car_hp / per_asr))
	var direct := await _rocket_on_car(0.05)
	_check("a rocket ON the car destroys it", direct >= car_hp, "%.0f damage" % direct)
	var one_m := await _rocket_on_car(1.0)
	_check("a rocket 1 m off the car still destroys it", one_m >= car_hp, "%.0f damage" % one_m)
	var two_m := await _rocket_on_car(2.0)
	_check("a rocket 2 m off wrecks but does not destroy it", two_m < car_hp and two_m > car_hp * 0.5, "%.0f damage" % two_m)
	var c := await _car()
	helper.call("blast", em, c.global_position + Vector3(0, -0.1, 0.5), grenade_r, grenade_d)
	await physics_frame
	_check("a grenade UNDER the car destroys it", _hp(c) <= 0.0, "%.0f HP left" % _hp(c))
	c.free()
	c = await _car()
	helper.call("blast", em, c.global_position + Vector3(2.0, 0.2, 0), grenade_r, grenade_d)
	await physics_frame
	var after_one := _hp(c)
	helper.call("blast", em, c.global_position + Vector3(2.0, 0.2, 0), grenade_r, grenade_d)
	await physics_frame
	_check("a grenade 1 m off does not, two do", after_one > 0.0 and _hp(c) <= 0.0, "%.0f then %.0f HP" % [after_one, _hp(c)])
	c.free()

	print("== 2. the surface, not the centre: a rocket on the bumper is a direct hit")
	c = await _car()
	helper.call("blast", em, c.global_position + Vector3(0, 0.2, 2.05), rocket_r, rocket_d)
	await physics_frame
	_check("a rocket on the bumper (2 m from the centre) destroys it", _hp(c) <= 0.0, "%.0f HP left" % _hp(c))
	c.free()

	print("== 3. people: explosives kill close, bullets unchanged")
	var cases := [["rocket", 3.0, true], ["rocket", 5.0, false], ["grenade", 2.5, true], ["grenade", 4.0, false]]
	for k in cases:
		var a := await _ai(Vector3(20, 0, 0))
		var hp0 := _hp(a)
		var r: float = rocket_r if k[0] == "rocket" else grenade_r
		var d: float = rocket_d if k[0] == "rocket" else grenade_d
		helper.call("blast", em, a.global_position + Vector3(k[1], 0, 0), r, d)
		await physics_frame
		var dead := _hp(a) <= 0.0
		_check("a %s %.1f m from a person %s" % [k[0], k[1], "kills" if k[2] else "hurts, not kills"],
			dead == k[2] and (k[2] or _hp(a) < hp0), "%.0f of %.0f HP left" % [_hp(a), hp0])
		a.free()
	var p := await _ai(Vector3(20, 0, 0))
	helper.call("weapon_hit", im, p, snr)
	await physics_frame
	_check("one SNR1 round still kills a person (x1.0)", _hp(p) <= 0.0, "%.0f HP left" % _hp(p))
	p.free()

	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails > 0 else 0)
