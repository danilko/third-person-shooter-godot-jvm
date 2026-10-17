extends SceneTree
## Does a DROPPED weapon rest ON the ground, or does its model sink into it / float above it? (user 2026-10-16:
## "weapon seem sometime sink to ground")
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_pickup_rest.gd [-- --only=ASR1] [--verbose]
##   [--control]    shrink every world shape to 40 % first: the sink check must then FAIL (it can see a sink)
##
## A world item rides a PickupBody whose collision shape is the item's authored CollisionShape3D (item.Pickup). What
## the player sees is the MODEL; what stops on the floor is the SHAPE. When the shape does not wrap the model, the
## model's far side goes through the floor (sinks) or hangs over it (floats). Each catalog weapon is dropped onto a flat
## box floor in three attitudes (flat, on its side, nose-down tipped) and left to settle 3 s; the lowest MODEL VERTEX
## (real vertices, not a rotated AABB, which over-reaches) is measured against the floor top.
##
## Section 2 is the DEATH DROP onto a THIN MESH DECK (a road / floor plate is a trimesh with nothing under its top
## face, with the ground ~0.5 m below): a body dies, each weapon is thrown 3-6 m/s up from 1.5 m with a 2.5 m/s
## scatter (WeaponController.returnWeaponToWorldOnDeath) and lands at ~8 m/s, 13 cm a 60 Hz step -- more than a
## pistol's 3-4 cm box. One that passes through the deck lies on the ground under the road: "sunk".
##   --ccd=off / --ccd=on   force every world body's continuous collision detection (default: what each item authors)
##
## Gate: no model goes more than SINK_TOL into the floor, every body came to rest, and no death drop passes the deck.

const CATALOG := "res://src/main/resources/com/openworld/weapon/weapon_catalog.json"
const SINK_TOL := 0.03      # 3 cm: Jolt's contact slop lets a resting box 2-2.5 cm in; that reads as lying on it
const FLOAT_TOL := 0.06     # a model hanging > 6 cm over the floor reads as floating (reported, not gated)
const ATTITUDES := {
	"flat": Vector3(0, 0, 0),
	"side": Vector3(0, 0, 90),
	"tipped": Vector3(70, 30, 0),
}

var fails := 0
var verbose := false
var control := false
var only := ""
var ccd := ""

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-34s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _floor(parent: Node) -> void:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(200, 1, 20)
	cs.shape = box
	b.add_child(cs)
	b.position = Vector3(0, -0.5, 0)       # top at y = 0
	parent.add_child(b)

## Lowest world-space vertex of the item's MODEL (its `Model` child; the muzzle-flash Glow quad under Muzzle is a
## visible mesh too, and it alone read as a 10.9 cm sink on every firearm lying on its side).
func _lowest_model(item: Node) -> float:
	var m: Node = item.get_node_or_null("Model")
	return _lowest(m if m != null else item)

func _lowest(n: Node) -> float:
	var lo := INF
	if n.name == "MuzzleVFX":
		return INF
	for c in n.get_children():
		if c is MeshInstance3D and (c as MeshInstance3D).is_visible_in_tree() and (c as MeshInstance3D).mesh != null:
			var mi := c as MeshInstance3D
			var xf: Transform3D = mi.global_transform
			for s in range(mi.mesh.get_surface_count()):
				var arr: Array = mi.mesh.surface_get_arrays(s)
				var verts: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
				for v in verts:
					lo = min(lo, (xf * v).y)
		lo = min(lo, _lowest(c))
	return lo

func _shrink_shapes(item: Node) -> void:
	for c in item.get_children():
		if c is CollisionShape3D and (c as CollisionShape3D).shape is BoxShape3D:
			var b := ((c as CollisionShape3D).shape as BoxShape3D).duplicate() as BoxShape3D
			b.size *= 0.4
			(c as CollisionShape3D).shape = b

## A one-face trimesh plate, top at y = 0 (a road deck / floor slab as the Road Kit and the building kits bake them).
func _deck(parent: Node, z: float) -> void:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var tri := ConcavePolygonShape3D.new()
	var h := 120.0
	tri.set_faces(PackedVector3Array([
		Vector3(-h, 0, -4), Vector3(h, 0, -4), Vector3(h, 0, 4),
		Vector3(-h, 0, -4), Vector3(h, 0, 4), Vector3(-h, 0, 4)]))
	cs.shape = tri
	b.add_child(cs)
	b.position = Vector3(0, 0, z)
	parent.add_child(b)
	var g := StaticBody3D.new()            # the ground under the deck
	var gs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(260, 1, 10)
	gs.shape = box
	g.add_child(gs)
	g.position = Vector3(0, -1.0, z)       # top at y = -0.5
	parent.add_child(g)

func _apply_ccd(item: Node) -> void:
	var body := item.get_parent() as RigidBody3D
	if body != null and ccd != "":
		body.continuous_cd = ccd == "on"

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		if a == "--verbose": verbose = true
		elif a == "--control": control = true
		elif a.begins_with("--only="): only = a.substr(7).to_upper()
		elif a.begins_with("--ccd="): ccd = a.substr(6)
	var world := Node3D.new()
	root.add_child(world)
	_floor(world)
	await _tick(3)

	var rows: Array = (JSON.parse_string(FileAccess.get_file_as_string(CATALOG)) as Dictionary)["weapons"]
	var x := -90.0
	var results := []      # [id, attitude, item, body]
	for row in rows:
		var id: String = row["id"]
		if id == "Fist":        # born held: never lies in the world
			continue
		if only != "" and id != only:
			continue
		var ps := load(row["scene"]) as PackedScene
		if ps == null:
			print("  skip %s (no scene)" % id)
			continue
		for att in ATTITUDES.keys():
			var item := ps.instantiate() as Node3D
			if control:
				_shrink_shapes(item)
			world.add_child(item)
			item.global_position = Vector3(x, 0.5, 0)
			item.rotation_degrees = ATTITUDES[att]
			results.append([id, att, item])
			x += 1.6
	await _tick(2)
	for r in results:
		_apply_ccd(r[2])
	await _tick(200)

	print("")
	print("=== dropped weapons on a flat floor (top y = 0), %d drops ===" % results.size())
	var worst_sink := 0.0
	var worst := ""
	var floats := []
	var sinks := []
	var restless := []
	for r in results:
		var item: Node3D = r[2]
		var body := item.get_parent() as RigidBody3D
		var lo := _lowest_model(item)
		var sink := -lo
		if verbose:
			print("    %-6s %-7s lowest vertex %+.3f m  body v %.3f" % [r[0], r[1], lo,
				body.linear_velocity.length() if body else -1.0])
		if body == null or body.linear_velocity.length() > 0.05:
			restless.append("%s/%s" % [r[0], r[1]])
		if sink > SINK_TOL:
			sinks.append("%s/%s %.1f cm" % [r[0], r[1], sink * 100.0])
		if lo > FLOAT_TOL:
			floats.append("%s/%s %.1f cm" % [r[0], r[1], lo * 100.0])
		if sink > worst_sink:
			worst_sink = sink
			worst = "%s/%s" % [r[0], r[1]]
	_check("every drop came to rest", restless.is_empty(), "moving: %s" % ", ".join(restless))
	_check("no model sinks > %d cm into the floor" % int(SINK_TOL * 100), sinks.is_empty(),
		"worst %.1f cm (%s); %d sink: %s" % [worst_sink * 100.0, worst, sinks.size(), ", ".join(sinks)])
	print("  info  floating > %d cm: %d %s" % [int(FLOAT_TOL * 100), floats.size(), ", ".join(floats)])

	# ── 2. the death drop onto a thin deck ───────────────────────────────────────────────────
	_deck(world, 30.0)
	await _tick(3)
	var drops := []
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	x = -110.0
	for row in rows:
		var id: String = row["id"]
		if id == "Fist" or (only != "" and id != only):
			continue
		var ps := load(row["scene"]) as PackedScene
		for k in range(4):
			var item := ps.instantiate() as Node3D
			world.add_child(item)
			item.global_position = Vector3(x, 1.5, 30.0)
			drops.append([id, item])
			x += 2.4
	await _tick(2)
	for d in drops:
		var item: Node3D = d[1]
		_apply_ccd(item)
		var body := item.get_parent() as RigidBody3D
		if body == null:
			continue
		var ang := rng.randf() * TAU
		body.linear_velocity = Vector3.ZERO
		body.apply_central_impulse((Vector3(cos(ang), 0, sin(ang)) * 2.5 + Vector3(0, rng.randf_range(3.0, 6.0), 0)) * body.mass)
		body.angular_velocity = Vector3(rng.randf_range(-6, 6), rng.randf_range(-6, 6), rng.randf_range(-6, 6))
	await _tick(240)
	var through := []
	var ccd_on := 0
	for d in drops:
		var item: Node3D = d[1]
		var body := item.get_parent() as RigidBody3D
		if body != null and body.continuous_cd:
			ccd_on += 1
		var lo := _lowest_model(item)
		if verbose:
			print("    deck %-6s lowest vertex %+.3f m" % [d[0], lo])
		if lo < -0.1:
			through.append("%s %.2f m" % [d[0], lo])
	print("")
	print("=== death drops onto a thin mesh deck (ground 0.5 m below), %d drops, %d with CCD ===" % [drops.size(), ccd_on])
	_check("no death drop passes the deck", through.is_empty(), "%d under it: %s" % [through.size(), ", ".join(through)])
	print("")
	print("probe_pickup_rest: %s (%d fail)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails > 0 else 0)
