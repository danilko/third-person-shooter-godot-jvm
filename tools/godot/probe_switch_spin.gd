extends SceneTree
## Does the upper body spin while a character switches weapon IN COMBAT?
##
##   godot --headless --fixed-fps 60 --path . --script tools/godot/probe_switch_spin.gd [-- --control]
##
## User report (2026-09-15): an AI switching from a pistol (or anything not a rifle) to a rifle turned its upper
## body through a large, near-360-degree rotation before settling. The cause: `ShoulderAimModifier` aims the HELD
## WEAPON's bore (W23), and at the end of the switch the new rifle is in the hand while the `WeaponChange` draw
## one-shot still swings it up from the holster -- so the spine chases a bore pointing down or backwards. An AI is in
## combat while it switches; a player usually is not, which is why the player looked fine.
##
## A character is armed with PI52 and AR4 through real pickups, held in combat (`aim` through Input), switched pistol
## -> rifle -> pistol -> rifle, and each frame of each switch window the CHEST (spine_03's own +X, flattened, against
## MeshRoot's right) and the BORE (the held weapon's -Z, flattened, against MeshRoot's forward) are sampled.
## Asserted: the chest never swings more than CHEST_SWING_LIMIT from where it rests aiming, and its total travel
## (sum of |frame-to-frame yaw change|) stays under TRAVEL_LIMIT -- a spin shows up in the travel even when it
## happens to end where it began. `-- --control` turns the fix off (ShoulderAimModifier.bore_during_one_shots) and
## must FAIL.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const WEAPON_DIR := "res://src/main/resources/com/openworld/weapon/%s.tscn"
const CHEST_SWING_LIMIT := 15.0
const TRAVEL_LIMIT := 120.0
const WINDOW_FRAMES := 90

var fails := 0

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-44s %s" % ["PASS" if ok else "FAIL", label, detail])

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

func _floor(parent: Node) -> void:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(200, 1, 200)
	cs.shape = box
	b.add_child(cs)
	b.position = Vector3(0, -0.5, 0)
	parent.add_child(b)

func _yaw_about_up(v: Vector3, ref: Vector3) -> float:
	var a := Vector3(v.x, 0, v.z)
	var b := Vector3(ref.x, 0, ref.z)
	if a.length_squared() < 1e-8 or b.length_squared() < 1e-8:
		return 0.0
	return rad_to_deg(b.normalized().signed_angle_to(a.normalized(), Vector3.UP))

func _slot_of(wc: Node, gun: Node) -> int:
	for s in range(8):
		wc.call("on_set_weapon", s)
		await _tick(45)
		if String(gun.get_parent().name).begins_with("Socket"):
			return s
	return -1

func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	var world := Node3D.new()
	root.add_child(world)
	_floor(world)
	await _tick(3)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
	await _tick(40)
	var guns := {}
	for id in ["PI52", "AR4"]:
		var g: Node3D = (load(WEAPON_DIR % id) as PackedScene).instantiate() as Node3D
		world.add_child(g)
		g.global_position = p.global_position + Vector3(0, 0.3, 0)
		guns[id] = g
		await _tick(30)
	var wc: Node = p.get_node("WeaponController")
	var slots := {}
	for id in guns:
		slots[id] = await _slot_of(wc, guns[id])
	print("slots: %s" % slots)
	var sk: Skeleton3D = _find(p, "Skeleton3D") as Skeleton3D
	var spine_mod: Node = sk.get_node("SpineAimModifier")
	if control:
		for m in ["SpineAimModifier", "ShoulderAimModifier"]:
			sk.get_node(m).set("bore_during_one_shots", true)
		print("CONTROL: the bore is trusted during one-shots (the pre-fix behaviour)")
	var mesh_root: Node3D = _find(p, "MeshRoot") as Node3D
	var chest := BoneAttachment3D.new()
	sk.add_child(chest)
	chest.bone_name = "spine_03"

	wc.call("on_set_weapon", slots["PI52"])
	Input.action_press("aim")
	await _tick(90)

	for step in ["AR4", "PI52", "AR4"]:
		await _tick(30)
		var rest_chest := _yaw_about_up(chest.global_transform.basis.x, mesh_root.global_transform.basis.x)
		wc.call("on_set_weapon", slots[step])
		var worst := 0.0
		var travel := 0.0
		var prev := rest_chest
		var bore_frames := 0
		var samples: Array[float] = []
		var trace := PackedStringArray()
		for f in range(WINDOW_FRAMES):
			await physics_frame
			var y := _yaw_about_up(chest.global_transform.basis.x, mesh_root.global_transform.basis.x)
			var d := wrapf(y - prev, -180.0, 180.0)
			travel += absf(d)
			prev = y
			samples.append(wrapf(y - rest_chest, -180.0, 180.0))
			if bool(spine_mod.call("aimed_with_bore")):
				bore_frames += 1
			if f % 6 == 0 or (f > 64 and "--trace" in OS.get_cmdline_user_args()):
				var tree: AnimationTree = _find(p, "AnimationTree") as AnimationTree
				var shots := ""
				for n in ["WeaponChange", "Reload", "Attack"]:
					if bool(tree.get("parameters/%s/active" % n)):
						shots += n.substr(0, 1)
				trace.append("%+.0f%s%s" % [wrapf(y - rest_chest, -180.0, 180.0), shots, ("b" if bool(spine_mod.call("aimed_with_bore")) else "") + ("" if bool(p.get("combat")) else "!c") + ("" if spine_mod.get("active") else "!a") + ("" if String(guns[step].get_parent().name).begins_with("Socket") else "!s")])
		# OVERSHOOT, not raw swing: switching between a bladed rifle and a square pistol legitimately moves the chest
		# by the blade difference (~25 deg), so what is measured is how far it goes outside [rest, settled].
		var settled: float = samples.back()
		var lo := minf(0.0, settled)
		var hi := maxf(0.0, settled)
		for v in samples:
			worst = maxf(worst, maxf(lo - v, v - hi))
		var bore := _yaw_about_up(-guns[step].global_transform.basis.z, -mesh_root.global_transform.basis.z)
		print("  -> %-4s chest overshoot %5.1f deg, travel %6.1f deg, bore frames %2d/%d, settled bore yaw %+.1f | chest trace %s"
			% [step, worst, travel, bore_frames, WINDOW_FRAMES, bore, " ".join(trace)])
		_check("switch to %s: chest overshoot" % step, worst < CHEST_SWING_LIMIT, "%.1f deg (limit %.0f)" % [worst, CHEST_SWING_LIMIT])
		_check("switch to %s: chest travel" % step, travel < TRAVEL_LIMIT, "%.1f deg (limit %.0f)" % [travel, TRAVEL_LIMIT])
		_check("switch to %s: gun ends on the aim line" % step, absf(bore) < 3.0, "bore yaw %+.1f" % bore)
	Input.action_release("aim")
	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
