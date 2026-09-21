extends SceneTree
## Does the arm oscillate while aiming at a STATIONARY target? (user-reported, crawl only)
##
##   godot --headless --fixed-fps 60 --path . --script tools/godot/probe_crawl_jitter.gd -- [--stance=crawl]
##
## A static target means nothing should move, so anything that does is a per-frame feedback loop.
## What is logged is chosen to tell the candidates apart rather than merely to show movement:
##   hand_l          the support hand -- "the arm moves in and out" is this, in metres
##   clavicle_l deg  the support shoulder's own channel (SupportHandIKModifier's protraction)
##   grip / reach    what that solve was asked for; a reach that CHANGES on a still target is the loop
##   clavicle_r deg  the firing shoulder, which the bore aim drives
## The PERIOD separates the suspects: ~1-2 frames is an IK solve fighting itself, ~9 frames is the
## 0.15 s bore blend or an AnimationTree crossfade being re-requested.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const WEAPON := "res://src/main/resources/com/openworld/weapon/ASR1.tscn"
var stance := "crawl"
var frames := 180
## `-- --hold-stance` keeps the stance key down for the whole run (the control).
var hold_stance_key := false
var aim_branch := ""

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _find(n: Node, nm: String) -> Node:
	if n.name == nm: return n
	for c in n.get_children():
		var r := _find(c, nm)
		if r != null: return r
	return null

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--stance="): stance = a.substr("--stance=".length())
		elif a.begins_with("--frames="): frames = int(a.substr("--frames=".length()))
		elif a == "--hold-stance": hold_stance_key = true
		elif a.begins_with("--aim-branch="): aim_branch = a.substr("--aim-branch=".length())
	var world := Node3D.new()
	root.add_child(world)
	var b := StaticBody3D.new(); var cs := CollisionShape3D.new(); var box := BoxShape3D.new()
	box.size = Vector3(60, 1, 60); cs.shape = box; b.add_child(cs); b.position = Vector3(0, -0.5, 0)
	world.add_child(b)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate()
	world.add_child(p)
	p.global_position = Vector3(0, 1.2, 0)
	var gun: Node3D = (load(WEAPON) as PackedScene).instantiate()
	world.add_child(gun)
	gun.global_position = Vector3(0, 1.2, 0)
	await _tick(60)
	# Armed the GAME's way: the weapon is dropped on the player and the auto-pickup takes it into a
	# free slot, then the slot is selected. `request_equip` is not a registered method, so calling it
	# aborts the script -- which in a `--script` run reads as a HANG, not an error.
	print("[jitter] player up; waiting for the pickup")
	await _tick(90)
	var wc: Node = p.get_node_or_null("WeaponController")
	for slot in range(1, 4):
		if wc != null:
			wc.call("on_set_weapon", slot)
			await _tick(30)
			if String(gun.get_parent().name).begins_with("Socket"):
				break
	print("[jitter] holding: %s" % gun.get_parent().name)

	if stance != "upright":
		Input.action_press(stance)
		await _tick(30)
		# RELEASE it: the stance keys are edge-driven, and a key held down for the whole run is a
		# different test from being IN the stance. Which of the two jitters is the diagnosis.
		if not hold_stance_key:
			Input.action_release(stance)
	Input.action_press("aim")
	await _tick(150)                       # settle: the stance change, the equip, the aim blend

	print("[jitter] settled; looking up the skeleton")
	var sk: Skeleton3D = _find(p, "Skeleton3D") as Skeleton3D
	if sk == null:
		print("[jitter] FAIL: no Skeleton3D under the Player")
		quit(); return
	var sup: Node = sk.get_node_or_null("SupportHandIKModifier")
	var att := func(bone: String) -> BoneAttachment3D:
		var a := BoneAttachment3D.new(); sk.add_child(a); a.bone_name = bone; return a
	var hand_l: BoneAttachment3D = att.call("hand_l")
	var mesh_root: Node3D = _find(p, "MeshRoot") as Node3D
	# `-- --aim-branch=Default` forces the aim branch back to the standing blendspace, i.e. the
	# behaviour before the crawl aim branch existed. It separates "the new branch oscillates" from
	# "the crawl aim solve oscillates".
	if aim_branch != "":
		var tree: AnimationTree = _find(p, "AnimationTree") as AnimationTree
		tree.set("parameters/AimStanceTransition/transition_request", aim_branch)
		await _tick(60)
	await _tick(5)

	var pos: Array[Vector3] = []
	var clav: Array[float] = []
	var reach: Array[float] = []
	for i in range(frames):
		await physics_frame
		pos.append(mesh_root.global_transform.affine_inverse() * hand_l.global_position)
		clav.append(sup.call("last_clavicle_deg") if sup else 0.0)
		reach.append(sup.call("last_target_reach") if sup else 0.0)

	var spread := func(a: Array) -> float:
		var lo = a[0]; var hi = a[0]
		for v in a: lo = min(lo, v); hi = max(hi, v)
		return hi - lo
	# how far the hand moves between consecutive frames, and over the whole window
	var step := 0.0
	for i in range(1, pos.size()):
		step = max(step, pos[i].distance_to(pos[i - 1]))
	var lo := pos[0]; var hi := pos[0]
	for v in pos:
		lo = Vector3(min(lo.x, v.x), min(lo.y, v.y), min(lo.z, v.z))
		hi = Vector3(max(hi.x, v.x), max(hi.y, v.y), max(hi.z, v.z))
	# The stance the BODY is in, not the key that was pressed: a stance that silently did not latch
	# reports a perfectly steady arm because it is standing up.
	print("[jitter] asked=%s  BODY stance ordinal=%d  over %d frames, target STATIONARY"
		% [stance, int(p.get("stance_ordinal")), frames])
	print("[jitter]   hand_l travel: peak-to-peak %.4f m (x %.4f y %.4f z %.4f), worst frame step %.4f m"
		% [(hi - lo).length(), hi.x - lo.x, hi.y - lo.y, hi.z - lo.z, step])
	print("[jitter]   support clavicle: %.2f..%.2f deg (spread %.2f)" % [clav.min(), clav.max(), spread.call(clav)])
	print("[jitter]   target reach: %.4f..%.4f m (spread %.4f)" % [reach.min(), reach.max(), spread.call(reach)])
	# a crude period: count sign changes of the frame-to-frame x motion
	var flips := 0
	var prev := 0.0
	for i in range(1, pos.size()):
		var d: float = pos[i].x - pos[i - 1].x
		if absf(d) > 1e-5:
			if prev != 0.0 and signf(d) != signf(prev): flips += 1
			prev = d
	print("[jitter]   direction reversals: %d in %d frames (%s)"
		% [flips, frames, "steady" if flips < 4 else "~%.1f frames per cycle" % (2.0 * frames / maxf(1.0, float(flips)))])
	Input.action_release("aim")
	quit()
