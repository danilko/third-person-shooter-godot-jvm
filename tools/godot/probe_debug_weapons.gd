extends SceneTree
## The debug console's weapon commands (DebugConsole: weapons / give / drop / ammo), typed through its own
## on_submit exactly as a player would, against a real Player on a floor.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_debug_weapons.gd

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
var fails := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-54s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _weapons_under(n: Node, out: Array) -> void:
	if n.get("weapon_id") != null and String(n.get("weapon_id")) != "":
		out.append(n)
	for c in n.get_children():
		_weapons_under(c, out)

func _initialize() -> void:
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	cs.shape = BoxShape3D.new()
	(cs.shape as BoxShape3D).size = Vector3(60, 1, 60)
	floor.add_child(cs)
	floor.position = Vector3(0, -0.5, 0)
	world.add_child(floor)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate()
	world.add_child(p)
	await _tick(20)
	var console: Node = load("res://src/main/java/com/openworld/debug/DebugConsole.java").new()
	root.add_child(console)
	await _tick(2)

	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://src/main/resources/com/openworld/weapon/weapon_catalog.json"))
	var ids: Array = []
	for r in catalog["weapons"]:
		if r["archetype"] != "fist":      # built in, never spawned
			ids.append(r["id"])

	print("== give")
	var before: Array = []
	_weapons_under(p, before)
	console.call("on_submit", "give snr1")
	await _tick(10)
	var held: Array = []
	_weapons_under(p, held)
	var got := false
	for w in held:
		got = got or String(w.get("weapon_id")) == "SNR1"
	_check("give snr1 puts SNR1 in the player's inventory", got, "%d -> %d weapons on the body" % [before.size(), held.size()])
	console.call("on_submit", "give nope")
	await _tick(2)
	var after_bad: Array = []
	_weapons_under(p, after_bad)
	_check("an unknown id gives nothing", after_bad.size() == held.size())

	print("== ammo")
	var snr: Node = null
	for w in held:
		if String(w.get("weapon_id")) == "SNR1":
			snr = w
	snr.set("magazine", 0)
	snr.set("reserve", 0)
	console.call("on_submit", "ammo")
	_check("ammo refills magazine and reserve", int(snr.get("magazine")) == int(snr.get("magazine_size")) and int(snr.get("reserve")) == int(snr.get("reserve_max")),
		"%d/%d" % [snr.get("magazine"), snr.get("reserve")])

	print("== drop all")
	console.call("on_submit", "drop all")
	await _tick(150)
	var bodies := 0
	var dropped: Array = []
	var resting := true
	for c in world.get_children():
		if c is RigidBody3D:
			var ws: Array = []
			_weapons_under(c, ws)
			if ws.size() > 0:
				bodies += 1
				dropped.append(String(ws[0].get("weapon_id")))
				resting = resting and (c as RigidBody3D).linear_velocity.length() < 0.2 and (c as Node3D).global_position.y > -0.2
	dropped.sort()
	var want := ids.duplicate()
	want.sort()
	_check("one pickup per catalog weapon (%d)" % ids.size(), dropped == want, str(dropped))
	_check("every pickup came to rest on the floor", resting)
	var near := true
	for c in world.get_children():
		if c is RigidBody3D and (c as Node3D).global_position.distance_to(p.global_position) > 12.0:
			near = false
	_check("all within reach, in front of the player", near)

	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails > 0 else 0)
