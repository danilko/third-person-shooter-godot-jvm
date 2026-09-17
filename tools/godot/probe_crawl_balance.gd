extends SceneTree
## Is the prone (crawl) upper body balanced -- no constant lean to one side, no side-to-side sway while moving?
##
##   godot --headless --fixed-fps 60 --path . --script tools/godot/probe_crawl_balance.gd [-- --weapon=ASR1] [-- --no-aim]
##
## User report (2026-09-15): in crawl the character always leans LEFT and rocks left/right whenever it moves, where
## upright and crouch hold steady. A Player armed through a real pickup is put in each stance and each case below,
## and every frame the yaw (about world up, against MeshRoot's facing) of the CHEST (spine_03 +X, the clavicle
## axis), the HIPS (thigh_l - thigh_r), the HEAD (head_2 +X) and the GUN (-Z) is sampled over SAMPLE_FRAMES.
## Reported per case: mean (the constant lean) and peak-to-peak (the sway). Asserted only for crawl, against the
## same numbers upright produces, so the gate says "crawl is as balanced as upright", not an absolute taste.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const WEAPON_DIR := "res://src/main/resources/com/openworld/weapon/%s.tscn"
const SETTLE := 90
const SAMPLE_FRAMES := 120
## Crawl may lean / sway this much more than upright does before the gate calls it unbalanced.
const LEAN_MARGIN := 10.0
const SWAY_MARGIN := 10.0
## The prone LEAN the user saw is not a chest yaw (yaw about world up barely sees a prone body): it is the legs
## splayed to one side and the hips yawed with them. So the crawl-specific limits are on those.
const HIP_YAW_MEAN_LIMIT := 3.0     # idle: the hips square to the aim line
const KNEE_ASYM_LIMIT := 0.05       # idle: (left knee + right knee) lateral offset from the chest, metres
const HIP_SWAY_LIMIT := 10.0        # moving: hip yaw peak-to-peak

var fails := 0
var weapon := "ASR1"
var aim := true
## `-- --dump=res://...json` writes the FINAL in-game pose (every bone through a BoneAttachment3D, i.e. after the aim
## and IK modifiers, in skeleton space) and the gun, for chosen frames of each case, so
## `blender/tools/pose_weapon_hold.py -- render-dump <json>` can render exactly what the game shows, headless.
var dump_path := ""
var dump := {}

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-40s %s" % ["PASS" if ok else "FAIL", label, detail])

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

func _yaw(v: Vector3, ref: Vector3) -> float:
	var a := Vector3(v.x, 0, v.z)
	var b := Vector3(ref.x, 0, ref.z)
	if a.length_squared() < 1e-8 or b.length_squared() < 1e-8:
		return 0.0
	return rad_to_deg(b.normalized().signed_angle_to(a.normalized(), Vector3.UP))

func _stats(xs: Array) -> Array:
	var lo := INF
	var hi := -INF
	var s := 0.0
	for x in xs:
		lo = minf(lo, x)
		hi = maxf(hi, x)
		s += x
	return [s / xs.size(), hi - lo]

func _xf(t: Transform3D) -> Array:
	var b := t.basis
	return [b.x.x, b.y.x, b.z.x, b.x.y, b.y.y, b.z.y, b.x.z, b.y.z, b.z.z, t.origin.x, t.origin.y, t.origin.z]

func _attach(sk: Skeleton3D, bone: String) -> BoneAttachment3D:
	var a := BoneAttachment3D.new()
	sk.add_child(a)
	a.bone_name = bone
	return a

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--weapon="):
			weapon = a.substr(9)
		elif a == "--no-aim":
			aim = false
		elif a.begins_with("--dump="):
			dump_path = a.substr(7)
	var world := Node3D.new()
	root.add_child(world)
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(400, 1, 400)
	cs.shape = box
	b.add_child(cs)
	b.position = Vector3(0, -0.5, 0)
	world.add_child(b)
	await _tick(3)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
	await _tick(40)
	var g: Node3D = null
	if weapon != "":
		g = (load(WEAPON_DIR % weapon) as PackedScene).instantiate() as Node3D
		world.add_child(g)
		g.global_position = p.global_position + Vector3(0, 0.3, 0)
		await _tick(30)
		var wc: Node = p.get_node("WeaponController")
		for s in range(6):
			if String(g.get_parent().name).begins_with("Socket"):
				break
			wc.call("on_set_weapon", s)
			await _tick(45)
	var sk: Skeleton3D = _find(p, "Skeleton3D") as Skeleton3D
	var mesh_root: Node3D = _find(p, "MeshRoot") as Node3D
	var chest := _attach(sk, "spine_03")
	var tl := _attach(sk, "thigh_l")
	var tr := _attach(sk, "thigh_r")
	var head := _attach(sk, "head_2")
	var kl := _attach(sk, "calf_l")
	var kr := _attach(sk, "calf_r")
	var all_bones := {}
	if dump_path != "":
		for i in sk.get_bone_count():
			all_bones[sk.get_bone_name(i)] = _attach(sk, sk.get_bone_name(i))
	print("weapon %s, aim %s" % [weapon, aim])
	print("%-26s %16s %16s %16s %16s" % ["case", "chest mean/p2p", "hips mean/p2p", "head mean/p2p", "gun mean/p2p"])
	var results := {}
	for stance in ["upright", "crawl"]:
		for move in ["idle", "forward", "left", "right"]:
			if stance != "upright":
				Input.action_press(stance)
			if aim:
				Input.action_press("aim")
			if move != "idle":
				Input.action_press(move)
			await _tick(SETTLE)
			var rows := {"chest": [], "hips": [], "head": [], "gun": [], "knees": []}
			for f in range(SAMPLE_FRAMES):
				await physics_frame
				var mb: Basis = mesh_root.global_transform.basis
				var right := mb.x
				rows["chest"].append(_yaw(chest.global_transform.basis.x, right) if chest.global_transform.basis.x.dot(tr.global_position - tl.global_position) >= 0 else _yaw(-chest.global_transform.basis.x, right))
				rows["hips"].append(_yaw(tr.global_position - tl.global_position, right))
				var c3: float = right.dot(chest.global_position)
				rows["knees"].append(right.dot(kl.global_position) - c3 + right.dot(kr.global_position) - c3)
				rows["head"].append(_yaw(head.global_transform.basis.x, right) if head.global_transform.basis.x.dot(right) >= 0 else _yaw(-head.global_transform.basis.x, right))
				rows["gun"].append(_yaw(-g.global_transform.basis.z, -mb.z) if g != null else 0.0)
				if dump_path != "" and f % 15 == 0:
					var fr := {}
					for bn in all_bones:
						fr[bn] = _xf(all_bones[bn].transform)
					if g != null:
						fr["__gun__"] = _xf(sk.global_transform.affine_inverse() * g.global_transform)
					dump["%s %s %03d" % [stance, move, f]] = fr
			var line := "%-26s" % ("%s %s" % [stance, move])
			var r := {}
			for k in ["chest", "hips", "head", "gun", "knees"]:
				var st := _stats(rows[k])
				r[k] = st
				line += (" %7.1f / %6.1f" if k != "knees" else "  knees %+.3f / %.3f m") % [st[0], st[1]]
			print(line)
			results["%s %s" % [stance, move]] = r
			if move != "idle":
				Input.action_release(move)
			Input.action_release("aim")
			if stance != "upright":
				Input.action_release(stance)
			await _tick(30)
	if dump_path != "":
		var fa := FileAccess.open(dump_path, FileAccess.WRITE)
		fa.store_string(JSON.stringify({"weapon": weapon, "frames": dump}))
		fa.close()
		print("dumped %d frames to %s" % [dump.size(), dump_path])
	print("")
	var ci: Dictionary = results["crawl idle"]
	_check("crawl idle: hips square to the aim", absf(ci["hips"][0]) < HIP_YAW_MEAN_LIMIT, "hip yaw %+.1f deg (limit %.0f)" % [ci["hips"][0], HIP_YAW_MEAN_LIMIT])
	_check("crawl idle: legs symmetric", absf(ci["knees"][0]) < KNEE_ASYM_LIMIT, "knee asymmetry %+.3f m (limit %.2f)" % [ci["knees"][0], KNEE_ASYM_LIMIT])
	for move in ["forward", "left", "right"]:
		var cm: Dictionary = results["crawl %s" % move]
		_check("crawl %s: hip sway" % move, cm["hips"][1] < HIP_SWAY_LIMIT, "%.1f deg p2p (limit %.0f)" % [cm["hips"][1], HIP_SWAY_LIMIT])
	for move in ["idle", "forward", "left", "right"]:
		var u: Dictionary = results["upright %s" % move]
		var c: Dictionary = results["crawl %s" % move]
		_check("crawl %s: chest lean" % move, absf(c["chest"][0]) <= absf(u["chest"][0]) + LEAN_MARGIN,
			"%+.1f deg (upright %+.1f)" % [c["chest"][0], u["chest"][0]])
		_check("crawl %s: chest sway" % move, c["chest"][1] <= u["chest"][1] + SWAY_MARGIN,
			"%.1f deg p2p (upright %.1f)" % [c["chest"][1], u["chest"][1]])
		_check("crawl %s: head sway" % move, c["head"][1] <= u["head"][1] + SWAY_MARGIN,
			"%.1f deg p2p (upright %.1f)" % [c["head"][1], u["head"][1]])
	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
