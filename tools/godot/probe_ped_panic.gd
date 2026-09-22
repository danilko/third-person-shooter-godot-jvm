extends SceneTree
## probe_ped_panic.gd -- the light crowd REACTS (PLAN.md 3.32): a far pedestrian that hears a gunshot runs away
## along its footway and calms down after `panic_seconds`, with no promotion. Headless, bare stand.
##
##   godot --headless --path . --script tools/godot/probe_ped_panic.gd [-- --control]
##
## One PedCrowd (no ZoneManager, so nothing is ever promoted) on a straight 400 m footway along +X: five peds
## 20-40 m from a gunshot at the origin, five 200 m out. After the shot the near five must run (4.5 m/s, not
## the 1.4 m/s walk) and AWAY from the shot, the far five must not notice, and all of them walk again once the
## panic has run out. `--control` turns `reactions` off, and the near-ped cases fail.

const CROWD_JAVA := "res://src/main/java/com/openworld/world/PedCrowd.java"
const SHOT := Vector3(0, 0, 0)

var pass_n := 0
var fail_n := 0
var crowd: Node3D


func check(ok: bool, what: String) -> void:
	if ok:
		pass_n += 1
		print("PASS ", what)
	else:
		fail_n += 1
		print("FAIL ", what)


func _initialize() -> void:
	_run.call_deferred()


func _xs() -> Array:
	var out := []
	for c in crowd.get_children():
		if c is Node3D:
			out.append(c.global_position.x)
	return out


func _frames(n: int) -> void:
	for i in n:
		await physics_frame


func _run() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	await process_frame
	var sm := root.get_node_or_null("/root/StimulusManager")
	check(sm != null, "the StimulusManager AutoLoad is present")
	crowd = load(CROWD_JAVA).new()
	root.add_child(crowd)
	await process_frame
	crowd.set("panic_seconds", 3.0)
	crowd.set("reactions", not control)
	var path := PackedVector3Array()
	for i in 41:
		path.append(Vector3(-200.0 + i * 10.0, 0.0, 0.0))
	# along is metres from the path's start (x = -200): near peds at x 20..40 walking TOWARD the shot (-X),
	# far peds at x 200..199 (the path ends at x 200)
	for k in 5:
		crowd.add_ped(path, 220.0 + k * 5.0, -1)
	for k in 5:
		crowd.add_ped(path, 390.0 - k * 2.0, -1)
	await _frames(20)
	var x0 := _xs()
	await _frames(60)
	var x1 := _xs()
	var walk := absf(x1[0] - x0[0]) / 1.0
	check(absf(walk - 1.4) < 0.2, "before the shot a ped walks at 1.4 m/s (%.2f)" % walk)
	sm.post_noise(0, SHOT, 150.0)
	await _frames(15)
	var a := _xs()
	await _frames(60)
	var b := _xs()
	var near_ok := 0
	for k in 5:
		var v: float = (b[k] - a[k]) / 1.0
		if v > 3.5:
			near_ok += 1
		print("  near ped %d at x %.1f: %+.2f m/s" % [k, a[k], v])
	check(near_ok == 5, "all 5 peds within earshot run AWAY from the shot (%d of 5 at > 3.5 m/s, +X)" % near_ok)
	var far_ok := 0
	for k in range(5, 10):
		if absf(absf(b[k] - a[k]) - 1.4) < 0.25:
			far_ok += 1
	check(far_ok == 5, "the 5 peds 200 m out keep walking (%d of 5 at 1.4 m/s)" % far_ok)
	check(int(crowd.fleeing_now()) == (0 if control else 5), "fleeing_now reads %d" % int(crowd.fleeing_now()))
	await _frames(150)
	var c := _xs()
	await _frames(60)
	var d := _xs()
	var calm := 0
	for k in 10:
		if absf(absf(d[k] - c[k]) - 1.4) < 0.25:
			calm += 1
	check(calm == 10, "after the panic runs out every ped walks again (%d of 10)" % calm)
	check(int(crowd.fleeing_now()) == 0, "nobody is fleeing any more")
	print("RESULT %s (%d passed, %d failed)" % ["PASS" if fail_n == 0 else "FAIL", pass_n, fail_n])
	crowd.queue_free()
	quit(0 if fail_n == 0 else 1)
