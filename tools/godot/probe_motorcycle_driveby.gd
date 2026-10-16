extends SceneTree
## PLAN.md 3.1b -- a motorcycle's rider shoots ONE-HANDED weapons only (WeaponItem.oneHanded: the pistols, DUP1, SMG1).
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_motorcycle_driveby.gd [-- --bike=SSB1]
## A real Player picks up ASR1 (a rifle) and PIS1 (a pistol) the game's way, raises the RIFLE, and gets on:
##   1. on the bike the rifle is put away and the pistol comes up by itself;
##   2. the rifle's slot key is refused -- the pistol stays;
##   3. held fire shoots the pistol from the saddle (shots fired go up);
##   4. CONTROL, the same in a car (SPC1): the rifle stays up and fires -- a car's driver is not one-handed.
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const DIR := "res://src/main/resources/com/openworld/vehicle/"
const RIFLE := "res://src/main/resources/com/openworld/weapon/ASR1.tscn"
const PISTOL := "res://src/main/resources/com/openworld/weapon/PIS1.tscn"
var fails := 0
var checks := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	checks += 1
	if not ok:
		fails += 1
	print("  %s  %-52s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var bike := "SSB1"
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--bike="):
			bike = a.substr(7)
	var w := Node3D.new()
	root.add_child(w)
	current_scene = w
	var f := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var b := BoxShape3D.new()
	b.size = Vector3(200, 1, 200)
	cs.shape = b
	f.add_child(cs)
	f.position.y = -0.5
	w.add_child(f)
	var helper: Node = load(HELPER).new()
	w.add_child(helper)
	await _case(w, helper, bike, true)
	await _case(w, helper, "SPC1", false)
	var want := 6
	if checks != want:
		fails += 1
		print("  FAIL  %d checks reported, %d expected (a case aborted)" % [checks, want])
	print("RESULT %s (%d passed, %d failed)" % ["PASS" if fails == 0 else "FAIL", checks - fails, fails])
	quit(0 if fails == 0 else 1)

## the slot holding the weapon whose id starts with `prefix`, found by raising each slot in turn
func _slot_of(wc: Node, prefix: String) -> int:
	for slot in range(1, 7):
		wc.call("on_set_weapon", slot)
		await _tick(40)
		if String(wc.call("get_current_weapon_id_now")).begins_with(prefix):
			return slot
	return -1

func _case(w: Node3D, helper: Node, id: String, is_bike: bool) -> void:
	print("-- %s" % id)
	var at := Vector3(0, 1.0, 0) if is_bike else Vector3(30, 1.0, 0)
	var veh: RigidBody3D = load(DIR + id + ".tscn").instantiate()
	veh.position = at
	w.add_child(veh)
	var p: CharacterBody3D = load(PLAYER).instantiate()
	# placed BEFORE it enters the tree: a body readied at the origin inside a hull flings the vehicle (any car, too)
	p.position = at + Vector3(5, 0.3, 0)
	w.add_child(p)
	for path in [RIFLE, PISTOL]:
		var gun: Node3D = load(path).instantiate()
		w.add_child(gun)
		gun.global_position = p.global_position
		await _tick(60)
	await _tick(60)
	var wc: Node = p.get_node("WeaponController")
	var rifle: int = await _slot_of(wc, "ASR")
	var pistol: int = await _slot_of(wc, "PIS")
	wc.call("on_set_weapon", rifle)
	await _tick(60)
	var before := String(wc.call("get_current_weapon_id_now"))
	helper.call("seat_character", veh, p)
	await _tick(90)
	var held := String(wc.call("get_current_weapon_id_now"))
	if is_bike:
		_check(id + ": the rifle is put away for the pistol", before.begins_with("ASR") and held.begins_with("PIS"),
				"slots rifle %d pistol %d; held %s -> %s" % [rifle, pistol, before, held])
	else:
		_check(id + " (control): the rifle stays up in a car", held.begins_with("ASR"), "held %s -> %s" % [before, held])
	var key := "weapon_slot_%d" % rifle
	Input.action_press(key)
	await _tick(2)
	Input.action_release(key)
	await _tick(60)
	var after := String(wc.call("get_current_weapon_id_now"))
	if is_bike:
		_check(id + ": the rifle's key is refused", after.begins_with("PIS"), "held %s after %s" % [after, key])
	else:
		_check(id + " (control): the rifle's key works", after.begins_with("ASR"), "held %s after %s" % [after, key])
	var shots0: int = wc.call("shots_fired_now")
	Input.action_press("vehicle_fire")
	await _tick(90)
	Input.action_release("vehicle_fire")
	await _tick(5)
	var shots: int = int(wc.call("shots_fired_now")) - shots0
	_check(id + ": held fire shoots %s" % after.left(4), shots > 0, "%d shots" % shots)
	helper.call("exit_driver", veh)
	await _tick(5)
	p.queue_free()
	veh.queue_free()
	await _tick(5)
