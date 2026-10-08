extends SceneTree
## THE DUMMY CAR TIER (PLAN.md 1g e / 2d): a traffic car far from every player drives ON RAILS (Vehicle.setDummy:
## frozen kinematic, posed from its lane by VehicleAIController.dummyInput) and is made real again near a player.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_dummy_cars.gd [-- --world=island] [--control]
##
##   1. the player stands still; cars beyond ZoneManager.dummy_out_dist become dummies (control: dummy_out_dist 0, none);
##   2. a dummy keeps driving: its lane progress grows and it stays on its lane's height;
##   3. promotion (dummy_out_dist set to 0 = everyone real): every former dummy is real, moving at about the speed it
##      had on rails (no stop, no launch), and does not jump in position or fall.

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"

var fails := 0


func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1


func _brain(car: Node) -> Node:
	for c in car.get_children():
		if c.has_method("dummy_now"):
			return c
	return null


func _cars() -> Array:
	var out := []
	for n in get_nodes_in_group("characters"):
		if n is RigidBody3D and _brain(n) != null:
			out.append(n)
	return out


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var control := "--control" in args
	var island := "--world=island" in args
	var world: Node = (load(ISLAND if island else DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	var zm: Node = root.get_node("ZoneManager")
	if control:
		zm.set("dummy_out_dist", 0.0)
	var t0 := Time.get_ticks_msec()
	var peak := 0
	while Time.get_ticks_msec() - t0 < 40000:
		await physics_frame
		peak = max(peak, int(zm.call("dummies_now")))
		if peak >= 2 and Time.get_ticks_msec() - t0 > 15000:
			break
	var cars := _cars()
	print("  %d traffic cars, %d dummies (peak %d)" % [cars.size(), int(zm.call("dummies_now")), peak])
	if control:
		_check(peak == 0, "control: no dummies with dummy_out_dist 0")
		print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
		quit(0)
		return
	_check(peak >= 1, "cars far from the player drive on rails (%d)" % peak)

	# 2. a dummy keeps driving on its lane
	var dummies := []
	for c in cars:
		if is_instance_valid(c) and bool(_brain(c).call("dummy_now")):
			dummies.append(c)
	var p0 := {}
	for c in dummies:
		p0[c] = [float(_brain(c).call("progress_now")), String(_brain(c).call("lane_now")), c.global_position]
	for i in 180:
		await physics_frame
	var moved := 0
	var low := 0
	for c in dummies:
		if not is_instance_valid(c) or not bool(_brain(c).call("dummy_now")):
			continue
		var b := _brain(c)
		var same_lane: bool = String(b.call("lane_now")) == p0[c][1]
		var dp: float = float(b.call("progress_now")) - float(p0[c][0])
		var dpos: float = (c.global_position - p0[c][2]).length()
		if (same_lane and dp > 2.0) or (not same_lane and dpos > 2.0):
			moved += 1
		if c.global_position.y < float(p0[c][2].y) - 5.0:
			low += 1
	print("  over 3 s: %d of %d dummies moved along their lanes, %d dropped" % [moved, dummies.size(), low])
	_check(moved >= 1, "a dummy keeps driving along its lane (%d)" % moved)
	_check(low == 0, "no dummy drops off its lane (%d)" % low)

	# 3. promotion: everyone real again
	var before := {}
	for c in _cars():
		if is_instance_valid(c) and bool(_brain(c).call("dummy_now")):
			before[c] = [float(_brain(c).call("dummy_speed_now")), c.global_position]
	zm.set("dummy_out_dist", 0.0)
	var t1 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t1 < 2000 and int(zm.call("dummies_now")) > 0:
		await physics_frame
	for i in 30:
		await physics_frame
	var real := 0
	var keep := 0
	var jumped := 0
	for c in before.keys():
		if not is_instance_valid(c):
			continue
		if not bool(_brain(c).call("dummy_now")):
			real += 1
		var v: float = (c as RigidBody3D).linear_velocity.length()
		var was: float = before[c][0]
		if was < 1.0 or abs(v - was) < max(4.0, was * 0.5):   # 4 m/s: a car braking for a light at 4 m/s^2
			keep += 1
		else:
			print("    speed %.1f -> %.1f" % [was, v])
		var moved_by: float = (c.global_position - before[c][1]).length()
		if moved_by > max(was, 1.0) * 1.0 + 6.0:   # 0.5 s of driving plus slack
			jumped += 1
			print("    moved %.1f m in ~0.5 s at %.1f m/s" % [moved_by, was])
	print("  promoted %d of %d; speed kept %d; jumped %d" % [real, before.size(), keep, jumped])
	_check(before.size() == 0 or real == before.size(), "every dummy is real once nobody may be one")
	_check(keep == before.size(), "a promoted car keeps its pace (no stop, no launch)")
	_check(jumped == 0, "a promoted car does not jump")
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0)
