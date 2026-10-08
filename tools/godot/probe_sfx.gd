extends SceneTree
## The non-weapon sounds (audio.Sound, built by tools/audio/build_sfx.py) load, and each call site plays them.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script res://tools/godot/probe_sfx.gd
##
## A bare stand: a floor, a wall, a real Player driven through Input, an AI to punch, a Door, an ExplosionManager.
## Every check reads Sounds' own play counter (GameManager.sound_plays_now), so a call site that runs but finds no
## file, or a file nothing plays, both fail. A missing file is silent in game with one log line, which is why this
## gate exists.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const AI     := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const SNR1   := "res://src/main/resources/com/openworld/weapon/SNR1.tscn"
const IMPACT := "res://src/main/java/com/openworld/world/manager/ImpactManager.java"
const EXPLO  := "res://src/main/java/com/openworld/world/manager/ExplosionManager.java"
const DOOR   := "res://src/main/java/com/openworld/world/Door.java"
const DECALS := "res://src/main/java/com/openworld/world/manager/DecalManager.java"
const CAR    := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
## Sounds that may have no file yet (README "Wired in code" says missing).
const ALLOWED_MISSING := ["SIREN"]

var fails := 0
var checks := 0
var gm: Node
var world: Node3D

func _check(label: String, ok: bool, detail: String = "") -> void:
	checks += 1
	if not ok:
		fails += 1
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _plays(name: String) -> int:
	return int(gm.call("sound_plays_now", name))

func _box(size: Vector3, at: Vector3) -> StaticBody3D:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = size
	cs.shape = sh
	b.add_child(cs)
	world.add_child(b)
	b.position = at
	return b

func _press(action: String, frames: int) -> void:
	Input.action_press(action)
	await _tick(frames)
	Input.action_release(action)
	await _tick(2)

func _initialize() -> void:
	await process_frame
	gm = root.get_node("GameManager")

	print("=== every Sound loads ===")
	for row in String(gm.call("sound_report_now")).split(","):
		var kv := row.split(":")
		var ok := int(kv[1]) > 0 or kv[0] in ALLOWED_MISSING
		_check("%s loads" % kv[0], ok, "%s take(s)" % kv[1])

	world = Node3D.new()
	root.add_child(world)
	_box(Vector3(200, 2, 200), Vector3(0, -1, 0))
	world.add_child(load(IMPACT).new())
	world.add_child(load(EXPLO).new())
	var dm: Node = load(DECALS).new()          # a DecalManager with one template, as WorldSystems.tscn has
	var tmpl := Decal.new()
	tmpl.size = Vector3(0.1, 0.1, 0.1)
	dm.add_child(tmpl)
	world.add_child(dm)
	await _tick(3)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
	await _tick(60)
	var wc: Node = p.get_node("WeaponController")

	print("=== footsteps and landing ===")
	var f0 := _plays("FOOTSTEP_CONCRETE")
	var s0 := int(p.call("footsteps_now"))
	await _press("forward", 150)
	var f1 := _plays("FOOTSTEP_CONCRETE")
	_check("walking 2.5 s plays concrete footsteps", f1 - f0 >= 3, "%d played, body counted %d" % [f1 - f0, int(p.call("footsteps_now")) - s0])
	await _tick(30)
	var l0 := _plays("LAND")
	p.global_position += Vector3(0, 4.0, 0)
	await _tick(90)
	_check("a 4 m drop lands with a thud", _plays("LAND") == l0 + 1, "LAND +%d" % (_plays("LAND") - l0))

	print("=== melee contact ===")
	var t: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	t.get_node("Health").set("max_health", 5000.0)
	world.add_child(t)
	var fwd: Vector3 = -(p.get_node("ActiveCamera") as Node3D).global_transform.basis.z
	fwd.y = 0.0
	t.global_position = p.global_position + fwd.normalized() * 1.3 - Vector3(0, p.global_position.y, 0)
	(t.get("character_info") as Resource).set("faction", "neutral")
	t.get_node("MovementController").set_physics_process(false)
	await _tick(30)
	await _press("weapon_slot_0", 2)      # draw the fists
	await _tick(40)
	var m0 := _plays("MELEE_HIT_FLESH")
	for i in range(3):
		await _press("fire", 2)
		await _tick(40)
	_check("a punch on a body plays a flesh hit", _plays("MELEE_HIT_FLESH") > m0, "+%d" % (_plays("MELEE_HIT_FLESH") - m0))
	_check("  ... and leaves no mark", int(dm.call("decals_spawned_now")) == 0 and int(dm.call("marks_spawned_now", "SLASH")) == 0,
		"holes %d slashes %d" % [int(dm.call("decals_spawned_now")), int(dm.call("marks_spawned_now", "SLASH"))])
	t.queue_free()
	await _tick(5)

	print("=== firearm: draw, impact, dry fire ===")
	_box(Vector3(30, 20, 1), p.global_position + fwd.normalized() * 12.0 + Vector3(0, 5, 0))
	var gun: Node3D = (load(SNR1) as PackedScene).instantiate() as Node3D
	world.add_child(gun)
	gun.global_position = p.global_position + Vector3(0, 0.3, 0)
	await _tick(30)
	var d0 := _plays("WEAPON_DRAW")
	for slot in range(7):
		if String(gun.get_parent().name).begins_with("Socket"):
			break
		wc.call("on_set_weapon", slot)
		await _tick(50)
	_check("raising a firearm plays a draw", _plays("WEAPON_DRAW") > d0, "+%d" % (_plays("WEAPON_DRAW") - d0))
	var i0 := _plays("IMPACT_STONE")
	gun.set("magazine", 5)
	await _press("fire", 2)
	await _tick(20)
	_check("a bullet into the wall plays a stone impact", _plays("IMPACT_STONE") > i0, "+%d" % (_plays("IMPACT_STONE") - i0))
	var shown := ""
	for c in dm.get_children():
		if c is Decal and (c as Decal).visible and (c as Decal).texture_albedo != null:
			shown = (c as Decal).texture_albedo.resource_path
	_check("  ... and leaves a bullet hole", int(dm.call("decals_spawned_now")) == 1 and shown.ends_with("impact_hole.png"), shown)
	await _tick(100)                       # the bolt cycle
	gun.set("magazine", 0)
	gun.set("reserve", 0)
	var y0 := _plays("DRY_FIRE")
	await _press("fire", 2)
	await _tick(10)
	_check("the trigger on an empty, dry gun clicks", _plays("DRY_FIRE") == y0 + 1, "+%d" % (_plays("DRY_FIRE") - y0))

	print("=== door, explosion ===")
	var door: Node3D = load(DOOR).new()
	door.set("auto_open", false)          # a manual door: open_door / close_door decide (an auto door follows its sensor)
	world.add_child(door)
	door.global_position = p.global_position + Vector3(3, 0, 0)
	await _tick(5)
	var o0 := _plays("DOOR_OPEN")
	var c0 := _plays("DOOR_CLOSE")
	door.call("open_door")
	await _tick(90)
	door.call("close_door")
	await _tick(90)
	_check("a hinged door opens and shuts with a sound each", _plays("DOOR_OPEN") == o0 + 1 and _plays("DOOR_CLOSE") == c0 + 1,
		"open +%d close +%d" % [_plays("DOOR_OPEN") - o0, _plays("DOOR_CLOSE") - c0])
	var e0 := _plays("EXPLOSION")
	(world.get_child(2) as Node).call("spawn_explosion", p.global_position + Vector3(8, 0, 0))
	await _tick(5)
	_check("an explosion bangs", _plays("EXPLOSION") == e0 + 1, "+%d" % (_plays("EXPLOSION") - e0))
	_check("  ... and scorches the ground under it", int(dm.call("marks_spawned_now", "SCORCH")) == 1,
		"%d" % int(dm.call("marks_spawned_now", "SCORCH")))

	print("=== marks on a car ride with it ===")
	var car: Node3D = (load(CAR) as PackedScene).instantiate() as Node3D
	world.add_child(car)
	car.global_position = p.global_position + Vector3(0, 0.5, 10)
	await _tick(30)
	var helper: Node = load(HELPER).new()
	world.add_child(helper)
	var im: Node = world.get_child(1)
	helper.call("kind_hit", im, car, 5.0, "BULLET")
	helper.call("kind_hit", im, car, 5.0, "BLADE")
	helper.call("kind_hit", im, car, 5.0, "BLUNT")
	await _tick(2)
	var marks := car.get_children().filter(func(c): return c is Decal and c.is_in_group("impact_mark"))
	_check("a bullet and a blade mark the car, a blunt blow does not", marks.size() == 2 and int(dm.call("marks_attached_now")) == 2,
		"%d on the car" % marks.size())
	for i in 20:
		helper.call("kind_hit", im, car, 1.0, "BULLET")
	await _tick(2)
	marks = car.get_children().filter(func(c): return c is Decal and c.is_in_group("impact_mark") and not c.is_queued_for_deletion())
	_check("  ... capped per car", marks.size() <= 14, "%d kept" % marks.size())
	var before: Vector3 = (marks[0] as Node3D).global_position - car.global_position
	car.global_position += Vector3(5, 0, 0)
	await _tick(1)
	var after: Vector3 = (marks[0] as Node3D).global_position - car.global_position
	_check("  ... and move with it", before.distance_to(after) < 0.01, "%.3f m" % before.distance_to(after))

	print("")
	print("RESULT %s (%d checks, %d failures)" % ["PASS" if fails == 0 else "FAIL", checks, fails])
	quit(1 if fails > 0 else 0)
