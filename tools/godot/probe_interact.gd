extends SceneTree
## The interact key uses ONE thing, the thing its prompt names (PLAN.md AR4 input half, 2026-10-09: control.Interactions).
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_interact.gd
##
## A real Player beside a MANUAL door (its sensor reported by hand) and, offered after it, a second pistol lying at the
## player's feet (the pistol slot is full, so it waits for E: a swap). Both prompts are up. E once: the pistol -- the
## newest prompt, the one the HUD shows -- is taken and the door does NOT move. E again: now the door is the only
## offer and it opens. Control: both offers really were up together (offers = 2), so "only one acted" is arbitration,
## not a missing offer. Before AR4 each polled E itself and one press did both.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const SYSTEMS := "res://src/main/resources/com/openworld/world/WorldSystems.tscn"
const DOOR := "res://src/main/resources/com/openworld/world/buildings/Door.tscn"
const PIS1 := "res://src/main/resources/com/openworld/weapon/PIS1.tscn"

var fails := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _press(action: String) -> void:
	Input.action_press(action)
	await physics_frame
	await process_frame
	Input.action_release(action)
	await _tick(20)

func _pistols(p: Node) -> int:
	var n := 0
	var stack := [p]
	while not stack.is_empty():
		var x: Node = stack.pop_back()
		if x.scene_file_path == PIS1:
			n += 1
		stack.append_array(x.get_children())
	return n

func _initialize() -> void:
	var world := Node3D.new()
	root.add_child(world)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(100, 2, 100)
	cs.shape = sh
	floor.add_child(cs)
	world.add_child(floor)
	floor.position = Vector3(0, -1, 0)
	var sys: Node = (load(SYSTEMS) as PackedScene).instantiate()
	for c in sys.get_children():
		if c.name == "HUDManager":
			c.free()
	world.add_child(sys)
	var gm: Node = root.get_node("GameManager")
	await _tick(3)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(0, 1.0, 0)
	await _tick(40)
	# the first pistol fills the slot (auto pickup)
	var g1: Node3D = (load(PIS1) as PackedScene).instantiate() as Node3D
	world.add_child(g1)
	g1.global_position = p.global_position + Vector3(0, 0.2, 0)
	await _tick(60)
	_check("the first pistol is picked up by walking over it", _pistols(p) == 1, "%d on the body" % _pistols(p))

	var door: Node3D = (load(DOOR) as PackedScene).instantiate() as Node3D
	door.set("auto_open", false)
	world.add_child(door)
	door.global_position = p.global_position + Vector3(-0.65, -1.0, -1.2)
	await _tick(5)
	door.call("on_sensor_body_entered", p)   # the building's sensor, reported by hand
	await _tick(5)
	var g2: Node3D = (load(PIS1) as PackedScene).instantiate() as Node3D
	g2.set("require_interact", true)
	world.add_child(g2)
	g2.global_position = p.global_position + Vector3(0, 0.2, 0.3)
	await _tick(30)
	var offers: int = gm.call("interact_offers_now")
	_check("control: the door and the pistol both offer (two prompts up)", offers == 2, "%d offers" % offers)

	var s0: int = door.call("door_sounds_now")
	var u0: int = gm.call("interact_uses_now")
	await _press("interact")
	await _tick(30)
	var s1: int = door.call("door_sounds_now")
	var taken := not is_instance_valid(g2) or (g2.get_parent() != world and p.is_ancestor_of(g2))
	_check("E takes the newest offer: the pistol is swapped in", taken,
		"now under %s" % (str(g2.get_parent().name) if is_instance_valid(g2) and g2.get_parent() else "-"))
	_check("  ... and the door does not move", s1 == s0, "door sounds %d -> %d" % [s0, s1])
	_check("  ... one use for one press", int(gm.call("interact_uses_now")) == u0 + 1, "%d" % (int(gm.call("interact_uses_now")) - u0))
	await _tick(20)
	await _press("interact")
	await _tick(60)
	_check("E again: the door, now the only offer, opens", int(door.call("door_sounds_now")) > s1,
		"door sounds %d" % int(door.call("door_sounds_now")))
	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
