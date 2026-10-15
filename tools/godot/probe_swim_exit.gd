extends SceneTree
## A SWIMMER GETS OUT OF THE SEA by each of the FishMarket's ways out (PLAN S13, 2026-10-14; re-laid for the S15 quay,
## PLAN S16 H; docs/island-world.md "The fish market rebuilt for cars"): the built scene, not a replica.
##
##   godot --headless --path . --script tools/godot/probe_swim_exit.gd [-- --exit=NAME] [--control]
##
## NAME (default: all, one after another, each in a fresh world):
##   stair436 / stair512 / stair600 -- the landing stairs on the z 842 quay, the z 848 band, the z 808 quay (heads at
##                                    Godot x 436 / 512 / 600, rising EAST along the wall's face, 1.5 m under the sea)
##   seawall                        -- the stairs up the strip's 5.6 m sea wall (x 645.8 foot, a landing at the yard's
##                                    level, head x 662, z 808)
##   slipway                        -- the 船揚場 off the 物揚場 (x 289.5-297.5, rising NORTH to the 1.0 m 物揚場)
##   pontoon                        -- the 浮桟橋's boarding steps (its east end x 360, rising WEST onto the 0.45 m deck)
## --control: the swimmer swims NORTH into the plain z 842 quay wall at x 415 (between a moored boat and the x 436
## stair, no ladder, no step) and must STAY in: the probe can fail (the swim jump clears no lip).
##
## Numbers are Godot world (x, z) of the island; the piece's origin is the reserve's centre (island_plan RESERVES
## "fish_market" = (290, 712)-(610, 848) -> (450, 780)), its yard at y 1.5 (the sea at y 0). The piece is turned so the
## exit's climb points along -Z (the probe's "forward") and the swimmer starts 4 m off its foot, holding forward 15 s.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const MARKET := "res://src/main/resources/com/openworld/world/buildings/FishMarket.tscn"
const CX := 450.0
const CZ := 780.0
# name: [foot x, foot z, climb dir x, climb dir z, the height (world y) that counts as OUT]
const EXITS := {
	"stair436": [430.0, 844.6, 1.0, 0.0, 1.3],
	"stair512": [506.0, 850.6, 1.0, 0.0, 1.3],
	"stair600": [594.0, 810.6, 1.0, 0.0, 1.3],
	"seawall": [645.8, 810.6, 1.0, 0.0, 5.4],
	"slipway": [293.5, 873.6, 0.0, -1.0, 0.9],
	"pontoon": [363.9, 848.0, -1.0, 0.0, 0.35],
}

# the control: "foot" = the wall's face at x 415, the climb into it (north)
const CONTROL := [415.0, 843.6, 0.0, -1.0, 1.3]

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _initialize() -> void:
	var only := ""
	var control := false
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--exit="):
			only = a.substr(7)
		elif a == "--control":
			control = true
	var names: Array = [only] if only != "" else EXITS.keys()
	if control:
		names = ["control"]
	var fails := 0
	for n in names:
		var ok := await _run(n)
		if ok != (n != "control"):
			fails += 1
	print("RESULT %s" % ("PASS" if fails == 0 else "FAIL (%d)" % fails))
	quit(0 if fails == 0 else 1)

func _run(name: String) -> bool:
	var e: Array = CONTROL if name == "control" else EXITS[name]
	var foot := Vector2(e[0], e[1])
	var dir := Vector2(e[2], e[3])
	var world := Node3D.new()
	root.add_child(world)
	await process_frame
	var m: Node3D = load(MARKET).instantiate()
	world.add_child(m)
	# turn the piece so `dir` (a Godot world direction in the piece's frame) points along -Z: yaw a with
	# R(a) * (dx, 0, dz) = (0, 0, -1)
	var a := atan2(dir.x, -dir.y)         # dir (1, 0) -> +90 deg, (0, -1) -> 0, (-1, 0) -> -90
	m.rotation = Vector3(0, a, 0)
	m.position = Vector3(0, 1.5, 0)
	var bed := StaticBody3D.new()
	var bcs := CollisionShape3D.new()
	var bb := BoxShape3D.new()
	bb.size = Vector3(1000, 1, 1000)
	bcs.shape = bb
	bed.add_child(bcs)
	world.add_child(bed)
	bed.position = Vector3(0, -7.5, 0)
	var water: Area3D = load("res://src/main/java/com/openworld/world/WaterVolume.java").new()
	water.collision_layer = 0
	water.collision_mask = 2
	var wcs := CollisionShape3D.new()
	var wbox := BoxShape3D.new()
	wbox.size = Vector3(1000, 7, 1000)
	wcs.shape = wbox
	water.add_child(wcs)
	world.add_child(water)
	water.position = Vector3(0, -3.5, 0)    # top at y 0
	var st := foot - dir * 4.0              # 4 m off the foot, in the water
	var start := m.transform * Vector3(st.x - CX, -2.0 - 1.5, st.y - CZ)
	var p: Node3D = load(PLAYER).instantiate()
	world.add_child(p)
	p.global_position = start
	await _tick(120)
	var s := p.global_position
	Input.action_press("forward")
	var best := -99.0
	for i in range(900):
		await physics_frame
		best = maxf(best, p.global_position.y)
	Input.action_release("forward")
	var en := p.global_position
	var ok := best >= float(e[4])
	print("[swim_market] %s: start (%.2f %.2f %.2f) end (%.2f %.2f %.2f) highest %.2f (out at %.2f) -> %s"
		% [name, s.x, s.y, s.z, en.x, en.y, en.z, best, e[4], "OUT" if ok else "STILL IN"])
	world.queue_free()
	await process_frame
	await process_frame
	return ok
