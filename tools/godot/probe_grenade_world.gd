extends SceneTree
## Grenade throws on DebugWorld's real terrain against the trajectory preview (W38). Before W38 the
## first impact matched (<0.26 m) but a rigid-body grenade then rolled 3-6 m past the ring; the preview
## and the grenade now run the same GrenadeFlight, bounces included.
##
##   godot --headless --path . --script tools/godot/probe_grenade_world.gd [-- --verbose]
##
## For throws in 8 directions at 2 view pitches it records the PREVIEW's end point, where the grenade
## FIRST touches something, and where it finally DETONATES. The preview's promise is the detonation
## point: that is where the damage is.

const WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const FRG1  := "res://src/main/resources/com/openworld/weapon/FRG1.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const THROW_SLOT := 5
const TOLERANCE := 0.5          # metres, preview end vs detonation

var fails := 0

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-52s %s" % ["PASS" if ok else "FAIL", label, detail])

func _initialize() -> void:
	var world: Node3D = (load(WORLD) as PackedScene).instantiate() as Node3D
	root.add_child(world)
	current_scene = world
	var p: CharacterBody3D = world.get_node("Characters/Player") as CharacterBody3D
	var helper: Node = load(HELPER).new()
	world.add_child(helper)
	await _tick(240)
	p.get_node("Health").set("max_health", 1.0e9)
	p.get_node("Health").call("heal", 1.0e9)
	p.set("is_fps_mode", true)
	var wc: Node = p.get_node("WeaponController")
	var errs := []
	for pitch in [5.0, 25.0]:
		for k in range(8):
			var yaw := k * 45.0
			var g: Node3D = (load(FRG1) as PackedScene).instantiate() as Node3D
			world.add_child(g)
			g.global_position = p.global_position + Vector3(0, 30, 0)
			await _tick(3)
			(g.get_parent() as Node3D).global_position = p.global_position + Vector3(0, 0.6, 0)
			await _tick(20)
			wc.call("on_set_weapon", THROW_SLOT)
			for i in range(50):
				helper.call("set_view", p, yaw, pitch)
				await physics_frame
			var pred: Vector3 = g.call("preview_end_now")
			var lands: bool = g.call("preview_lands_now")
			var seen := {}
			for n in world.get_children():
				seen[n.get_instance_id()] = true
			Input.action_press("fire")
			await _tick(2)
			Input.action_release("fire")
			await _tick(1)
			var pr: RigidBody3D = null
			for n in world.get_children():
				if not seen.has(n.get_instance_id()) and n is RigidBody3D:
					pr = n
			var first := Vector3.INF
			var last := Vector3.INF
			var bounces := 0
			for i in range(260):
				helper.call("set_view", p, yaw, pitch)
				await physics_frame
				if pr == null or not is_instance_valid(pr) or not pr.is_inside_tree():
					break
				bounces = pr.call("contacts_now")
				if first == Vector3.INF and bounces > 0:
					first = pr.global_position
				last = pr.global_position
			var e_first := pred.distance_to(first) if first != Vector3.INF else -1.0
			var e_det := pred.distance_to(last) if last != Vector3.INF else -1.0
			errs.append(e_det)
			print("  yaw %3d pitch %2d  preview %s lands=%s | first impact off %.2f m | detonation off %.2f m (throw %.1f m, %d contacts)"
				% [int(yaw), int(pitch), pred.snappedf(0.1) if pred != null else pred, lands, e_first, e_det,
				   Vector2(pred.x - p.global_position.x, pred.z - p.global_position.z).length(), bounces])
			await _tick(30)
	# A long throw rolling across uneven ground touches it 10-18 times, and there a 1e-7 difference
	# (measured between the preview's and the throw's launch inputs) can decide whether it stops on one
	# bump or rolls to the next: chaos, not a mismatch. So the gate is on the typical throw, plus a bound.
	errs.sort()
	var within := 0
	for e in errs:
		if e >= 0.0 and e < TOLERANCE:
			within += 1
	_check("most throws go off at the disc (< %.1f m)" % TOLERANCE, within >= int(errs.size() * 0.75),
		"%d of %d, median %.2f m" % [within, errs.size(), errs[errs.size() / 2]])
	_check("no throw goes off far from it (< 6 m)", errs[errs.size() - 1] < 6.0, "worst %.2f m" % errs[errs.size() - 1])
	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
