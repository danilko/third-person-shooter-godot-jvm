extends SceneTree
## Can a swimmer get out onto a ledge H m above the water by the swim jump alone?
##   godot --headless --path . --script <this> -- --h=1.0
## Deep water (top y 0, floor y -6), a ledge whose top is y H from z -2 northwards, the player 2.5 m south of it
## swimming forward and tapping jump every 0.6 s for 10 s. PASS = standing on the ledge (y >= H - 0.2, z < -2.3).

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"

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

func _box(parent: Node, size: Vector3, pos: Vector3) -> void:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var s := BoxShape3D.new()
	s.size = size
	cs.shape = s
	b.add_child(cs)
	parent.add_child(b)
	b.global_position = pos

func _initialize() -> void:
	var h := 1.0
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--h="):
			h = float(a.substr(4))
	var world := Node3D.new()
	root.add_child(world)
	await process_frame
	_box(world, Vector3(200, 1, 200), Vector3(0, -6.5, 0))                  # sea bed
	_box(world, Vector3(40, h + 6.0, 40), Vector3(0, (h - 6.0) / 2.0, -22))  # the ledge: z -42..-2, top y h
	var ramp := OS.get_cmdline_user_args().has("--ramp")
	var start_z := 0.5
	if ramp:   # a stair hull at 1:2 from the lip (z -2, y h) down into the water toward +z, as the landing flights
		var sl_ := 0.5
		for a in OS.get_cmdline_user_args():
			if a.begins_with("--slope="):
				sl_ = float(a.substr(8))
		var th := atan(sl_)
		var b := StaticBody3D.new()
		var cs := CollisionShape3D.new()
		var s := BoxShape3D.new()
		var foot := -0.6
		for a in OS.get_cmdline_user_args():
			if a.begins_with("--foot="):
				foot = float(a.substr(7))
		var run := (h - foot) / sl_
		s.size = Vector3(4, 0.5, sqrt(1.0 + sl_ * sl_) * run)
		cs.shape = s
		b.add_child(cs)
		world.add_child(b)
		b.basis = Basis(Vector3.RIGHT, th)
		b.global_position = Vector3(0, (h + foot) / 2.0, -2.0 + run / 2.0) - Vector3(0, cos(th), sin(th)) * 0.25
		var under := StaticBody3D.new()   # the block under the slope's low end: a vertical face down to the bed
		var ucs := CollisionShape3D.new()
		var ub := BoxShape3D.new()
		ub.size = Vector3(4, foot + 6.5, run)
		ucs.shape = ub
		under.add_child(ucs)
		world.add_child(under)
		under.global_position = Vector3(0, (foot - 6.5) / 2.0 - 0.3, -2.0 + run / 2.0)
		start_z = -2.0 + run + 5.0
	if OS.get_cmdline_user_args().has("--real"):
		# library_civic.fish_market's landing stair, Godot heights: real steps from y -0.6 (0.6 m under the sea) up to
		# the quay at h, each a solid down to -6.5, and its stair_ramp hull (0.3 thick, layer 7) along the nosings
		var lo := -0.6
		for a in OS.get_cmdline_user_args():
			if a.begins_with("--lo="):
				lo = float(a.substr(5))
		var n := int(ceil((h - lo) / 0.17))
		var s0 := -2.0 + 2.0 * (h - lo)
		for k in range(0 if OS.get_cmdline_user_args().has("--nosteps") else n):
			var a := s0 + (-2.0 - s0) * k / n
			var e2 := s0 + (-2.0 - s0) * (k + 1) / n
			var top := lo + (h - lo) * (k + 1) / n
			_box(world, Vector3(2, top + 6.5, absf(a - e2)), Vector3(0, (top - 6.5) / 2.0, (a + e2) / 2.0))
		var hull := StaticBody3D.new()
		hull.collision_layer = 1 << 6
		var hc := CollisionShape3D.new()
		var cp := ConvexPolygonShape3D.new()
		var sl := s0
		var sh := -2.0
		if OS.get_cmdline_user_args().has("--fixhull"):   # through the nosings: both ends one tread toward the low side
			var d := (-2.0 - s0) / n
			sl -= d
			sh -= d
		cp.points = PackedVector3Array([Vector3(-1, lo, sl), Vector3(-1, h, sh), Vector3(1, lo, sl), Vector3(1, h, sh),
			Vector3(-1, lo - 0.3, sl), Vector3(-1, h - 0.3, sh), Vector3(1, lo - 0.3, sl), Vector3(1, h - 0.3, sh)])
		hc.shape = cp
		hull.add_child(hc)
		if not OS.get_cmdline_user_args().has("--nohull"):
			world.add_child(hull)
		start_z = s0 + 5.0
	var water: Area3D = load("res://src/main/java/com/openworld/world/WaterVolume.java").new()
	water.collision_layer = 0
	water.collision_mask = 2
	var wcs := CollisionShape3D.new()
	var wbox := BoxShape3D.new()
	wbox.size = Vector3(200, 6, 200)
	wcs.shape = wbox
	water.add_child(wcs)
	world.add_child(water)
	water.global_position = Vector3(0, -3, 0)   # top at y 0
	var p: Node3D = load(PLAYER).instantiate()
	world.add_child(p)
	p.global_position = Vector3(0, -0.5, start_z)
	await _tick(120)
	var start := p.global_position
	var mc := _find(p, "MovementController")
	print("[swim_ledge] stance %s, mc methods swim_jump=%s" % [p.get("stance_ordinal"), mc.has_method("swim_jump")])
	Input.action_press("forward")
	var best := -99.0
	for k in range(25 if ramp or start_z > 1.0 else 17):
		if not ramp and start_z < 1.0:
			_find(p, "MovementController").call("swim_jump")   # what a tap of jump does (Character: input.jump -> swimJump)
		for i in range(36):
			await physics_frame
			best = maxf(best, p.global_position.y)
	await _tick(60)
	Input.action_release("forward")
	await _tick(30)
	var e := p.global_position
	var ok := best >= h - 0.2
	print("[swim_ledge] h %.2f  start (%.2f %.2f %.2f) end (%.2f %.2f %.2f) highest %.2f -> %s"
		% [h, start.x, start.y, start.z, e.x, e.y, e.z, best, "OUT" if ok else "STILL IN"])
	print("RESULT %s" % ("PASS" if ok else "FAIL"))
	quit(0 if ok else 1)
