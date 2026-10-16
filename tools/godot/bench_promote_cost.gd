extends SceneTree
## What a light combatant's PROMOTION costs, step by step (PLAN.md 2.3 follow-up "a cheaper promoted body").
##   stdbuf -oL godot --headless --path . --script tools/godot/bench_promote_cost.gd [-- --n=20]
## DebugWorld; N times, the way EnforcementDispatch.spawnPlacedAs builds one: instantiate AICharacter.tscn with a body's
## CharacterVisuals set (no add), add it to the tree (its _ready and the visuals' instancing), an outfit, a weapon
## grant; then the physics-tick cost of N live promoted bodies standing (EngineProfile-free: the frame's physics time
## from Performance). Prints the median and p90 of each step in ms. A MEASUREMENT: it exits 0.
const WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const VIS := "res://src/main/resources/com/openworld/character/CharacterVisuals_Fumiriya.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"

func _initialize() -> void:
	_run.call_deferred()

func _stats(a: Array) -> String:
	a.sort()
	return "median %6.2f  p90 %6.2f  max %6.2f" % [a[a.size() / 2], a[int(a.size() * 0.9)], a[-1]]

func _run() -> void:
	var n := 20
	var off: PackedStringArray = []
	for x in OS.get_cmdline_user_args():
		if x.begins_with("--n="):
			n = int(x.substr(4))
		elif x.begins_with("--off="):
			off = x.substr(6).split(",")
	var world: Node = (load(WORLD) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	for i in 240:
		await physics_frame
	var helper: Node = load(HELPER).new()
	world.add_child(helper)
	var scene: PackedScene = load(AI)
	var vis: PackedScene = load(VIS)
	var t_inst := []
	var t_add := []
	var t_weapon := []
	var bodies := []
	var base := Vector3(40, 0, 40)
	# warm the caches once (the first instance loads every sub-resource)
	var warm: Node3D = scene.instantiate()
	warm.set("character_visuals", vis)
	world.add_child(warm)
	await physics_frame
	warm.queue_free()
	await physics_frame
	for i in n:
		var t0 := Time.get_ticks_usec()
		var ai: Node3D = scene.instantiate()
		ai.set("character_visuals", vis)
		var t1 := Time.get_ticks_usec()
		world.add_child(ai)
		ai.global_position = base + Vector3((i % 5) * 3.0, 0.5, (i / 5) * 3.0)
		var t2 := Time.get_ticks_usec()
		helper.call("give_weapon", ai, "PIS1")
		var t3 := Time.get_ticks_usec()
		t_inst.append((t1 - t0) / 1000.0)
		t_add.append((t2 - t1) / 1000.0)
		t_weapon.append((t3 - t2) / 1000.0)
		bodies.append(ai)
		await physics_frame
		await physics_frame
	print("PROMOTE instantiate        %s" % _stats(t_inst))
	print("PROMOTE add (+ _ready)     %s" % _stats(t_add))
	print("PROMOTE weapon grant       %s" % _stats(t_weapon))
	# --off=<Class>[,..]: those nodes of every body switched off (process disabled; a SkeletonModifier3D inactive), to
	# split the standing cost; "Body" = the CharacterBody3D's own script tick
	var disabled := 0
	for b in bodies:
		for cls in off:
			if cls.begins_with("@"):
				# "@Name": the body's child nodes of that name, subtree and all
				for k in (b as Node).find_children(cls.substr(1), "", true, false):
					k.process_mode = Node.PROCESS_MODE_DISABLED
					for kk in k.find_children("*", "SpringArm3D", true, false):
						(kk as SpringArm3D).spring_length = 0.0
					disabled += 1
				continue
			if cls == "Body":
				(b as Node).set_physics_process(false)
				(b as Node).set_process(false)
				disabled += 1
				continue
			for k in (b as Node).find_children("*", cls, true, false):
				if k is SkeletonModifier3D:
					(k as SkeletonModifier3D).active = false
				k.process_mode = Node.PROCESS_MODE_DISABLED
				disabled += 1
	if not off.is_empty():
		print("PROMOTE off %s: %d nodes" % [",".join(off), disabled])
	# the standing cost: physics time per frame with the N bodies vs without
	var with_ := []
	for i in 180:
		await physics_frame
		if i >= 60:
			with_.append(Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0)
	var proc := []
	for i in 120:
		await process_frame
		proc.append(Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0)
	for b in bodies:
		b.queue_free()
	for i in 30:
		await physics_frame
	var without := []
	for i in 180:
		await physics_frame
		if i >= 60:
			without.append(Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0)
	print("PROMOTE physics ms/frame with %d bodies  %s" % [n, _stats(with_)])
	print("PROMOTE process ms/frame with %d bodies  %s" % [n, _stats(proc)])
	print("PROMOTE physics ms/frame without       %s" % _stats(without))
	quit(0)
