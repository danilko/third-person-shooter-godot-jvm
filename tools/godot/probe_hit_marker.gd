extends SceneTree
## Hit feedback (PLAN.md 2.8 item 9): a confirmed hit by the LOCAL player shows the marker; a kill shows
## the kill variant; a miss and someone else's damage show nothing.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_hit_marker.gd
##
## A real Player with SNR1 (through a pickup), a HitMarker bound to it, an AI 40 m out. The view is steered
## onto the drawn chest (probe_sniper_live idiom) and fire is pressed through Input. Co-op is gated in
## tools/net/run_net_shot_test.sh (hit_confirmed_local).

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const AI     := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const SNR1    := "res://src/main/resources/com/openworld/weapon/SNR1.tscn"
const IMPACT := "res://src/main/java/com/openworld/world/manager/ImpactManager.java"
const MARKER := "res://src/main/java/com/openworld/ui/HitMarker.java"
const SENS := 0.07

var p: Node3D
var cam_ctrl: Node
var fails := 0

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-52s %s" % ["PASS" if ok else "FAIL", label, detail])

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

func _steer_to(target: Vector3, frames: int) -> void:
	for i in range(frames):
		var cam := p.get_node("ActiveCamera") as Node3D
		var to: Vector3 = target - cam.global_position
		var f := -cam.global_transform.basis.z
		var dy := wrapf(rad_to_deg(atan2(-to.x, -to.z)) - rad_to_deg(atan2(-f.x, -f.z)), -180.0, 180.0)
		var dp := rad_to_deg(atan2(to.y, Vector2(to.x, to.z).length())) - rad_to_deg(asin(clampf(f.y, -1.0, 1.0)))
		if absf(dy) + absf(dp) < 0.003:
			return
		var ev := InputEventMouseMotion.new()
		ev.relative = Vector2(-dy / SENS, -dp / SENS)
		cam_ctrl.call("_input", ev)
		await physics_frame

func _fire(gun: Node) -> void:
	gun.set("magazine", 5)
	Input.action_press("fire")
	await _tick(2)
	Input.action_release("fire")
	await _tick(8)

func _initialize() -> void:
	var world := Node3D.new()
	root.add_child(world)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(400, 2, 400)
	cs.shape = sh
	floor.add_child(cs)
	world.add_child(floor)
	floor.position = Vector3(0, -1, 0)
	world.add_child(load(IMPACT).new())
	await _tick(3)
	p = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
	await _tick(40)
	var gun: Node3D = (load(SNR1) as PackedScene).instantiate() as Node3D
	world.add_child(gun)
	gun.global_position = p.global_position + Vector3(0, 0.3, 0)
	await _tick(30)
	var wc: Node = p.get_node("WeaponController")
	for slot in range(7):
		if String(gun.get_parent().name).begins_with("Socket"):
			break
		wc.call("on_set_weapon", slot)
		await _tick(40)
	cam_ctrl = p.get_node("TPSCameraController")
	var marker: Control = load(MARKER).new()
	marker.size = Vector2(1920, 1080)
	world.add_child(marker)
	marker.call("wire_character", p)
	marker.set("play_sound", false)

	var t: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	var h: Node = t.get_node("Health")
	h.set("max_health", 1000.0)
	world.add_child(t)
	t.global_position = Vector3(0, 0, -40)
	t.global_rotation = Vector3(0, PI, 0)
	var info: Resource = t.get("character_info")
	info.set("faction", "neutral")
	t.get_node("MovementController").set_physics_process(false)
	var skel: Skeleton3D = _find(t, "Skeleton3D") as Skeleton3D
	var att := BoneAttachment3D.new()
	att.bone_name = "spine_03"
	skel.add_child(att)
	var hb := _find(t, "Physical Bone spine_03") as PhysicalBone3D
	await _tick(90)
	var dealt := []
	h.connect("hit", func(d): dealt.append(d))

	Input.action_press("aim")
	await _tick(30)
	# 1. a hit
	await _steer_to((att.global_transform * hb.body_offset).origin, 90)
	await _tick(10)
	var n0: int = marker.call("markers_shown")
	await _fire(gun)
	var n1: int = marker.call("markers_shown")
	_check("a confirmed hit shows the marker", n1 == n0 + 1, "shown %d -> %d, target took %s" % [n0, n1, str(dealt)])
	_check("  ... on screen right after the shot", bool(marker.call("marker_visible")), "")
	await _tick(40)
	_check("  ... and gone again", not bool(marker.call("marker_visible")), "")

	# 2. a miss (aim 5 m above the target at the sky)
	await _tick(90)
	await _steer_to((att.global_transform * hb.body_offset).origin + Vector3(6, 6, 0), 90)
	await _tick(10)
	await _fire(gun)
	_check("a miss shows nothing", int(marker.call("markers_shown")) == n1, "shown %d" % int(marker.call("markers_shown")))

	# 3. someone else's damage (no attacker id, then another attacker's id)
	var ev_bus := root.get_node("EventBus")
	ev_bus.emit_signal("damage_dealt", "someone-else", 50.0, false, false)
	await _tick(2)
	_check("another attacker's damage shows nothing", int(marker.call("markers_shown")) == n1, "")

	# 4. a kill: a second, 100 HP target in the same spot (SNR1's chest is 150)
	t.queue_free()
	await _tick(5)
	var t2: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	t2.get_node("Health").set("max_health", 100.0)
	world.add_child(t2)
	t2.global_position = Vector3(0, 0, -40)
	t2.global_rotation = Vector3(0, PI, 0)
	(t2.get("character_info") as Resource).set("faction", "neutral")
	t2.get_node("MovementController").set_physics_process(false)
	var att2 := BoneAttachment3D.new()
	att2.bone_name = "spine_03"
	(_find(t2, "Skeleton3D") as Skeleton3D).add_child(att2)
	var hb2 := _find(t2, "Physical Bone spine_03") as PhysicalBone3D
	await _tick(90)
	await _steer_to((att2.global_transform * hb2.body_offset).origin, 90)
	await _tick(10)
	var killed := [false]
	ev_bus.connect("damage_dealt", func(a, d, hs, k): killed[0] = killed[0] or k)
	await _fire(gun)
	_check("a kill shows the marker, flagged killed", int(marker.call("markers_shown")) == n1 + 1 and killed[0],
		"shown %d killed %s" % [int(marker.call("markers_shown")), killed[0]])
	Input.action_release("aim")
	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
