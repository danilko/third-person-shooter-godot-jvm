extends SceneTree
## Every weapon is its real-world size, and no scene compensates for a model that is not.
##
##   godot --headless --path . --script tools/godot/probe_weapon_scale.gd
##
## The standard (blender/WEAPON_AUTHORING.md, table in blender/tools/weapon_models.json):
##   * 1 unit = 1 METRE, and a weapon is its real-world length. The character is metric and a weapon
##     is held in its hand, so the size is not a free parameter. (The 4.5 m arcade road lane is a
##     VEHICLE-scale decision and does not reach hand props.)
##   * -Z is the muzzle/blade direction, +Y up — the character mesh's own convention.
##   * the ORIGIN is the GRIP, so `WeaponItem.alignmentFor` is identity and the socket carries no
##     per-weapon fudge.
##
## The rule this gate really enforces is the LAST one: **a conforming model needs no transform on its
## scene instance.** Before this, every weapon was instanced at `scale 0.1` with a yawed basis to undo
## a source convention, and because each 0.1 was a guess rather than a conversion nothing agreed with
## life — the bayonet measured 39% of a real bayonet and the grenade 300% of a real grenade. A
## non-identity instance transform is how that comes back, so it is asserted directly.
##
## It reads the same JSON the build script does, so the gate and the build cannot disagree about what
## a weapon is supposed to be.

const TABLE := "res://blender/tools/weapon_models.json"
const SCENES := "res://src/main/resources/com/openworld/weapon/%s.tscn"
## Fraction of the declared length a measurement may be out by. Tight: this is a bake, not a guess.
const LENGTH_TOL := 0.02
## A world pickup rests on a heightfield; a collider thinner than this sinks through it. MW1 shipped
## a 0.04 m box and fell to y = -59 in World.tscn for exactly that reason (W15/W16).
const MIN_COLLIDER := 0.05

var fails := 0

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-40s %s" % ["PASS" if ok else "FAIL", label, detail])

func _visual(n: Node, root: Node3D, acc: AABB, got: Array) -> AABB:
	if n is MeshInstance3D and n.mesh != null:
		var local := root.global_transform.affine_inverse() * (n as Node3D).global_transform
		var a: AABB = local * (n.mesh as Mesh).get_aabb()
		acc = a if not got[0] else acc.merge(a)
		got[0] = true
	for c in n.get_children():
		acc = _visual(c, root, acc, got)
	return acc

func _initialize() -> void:
	var cfg: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(TABLE))
	if cfg == null:
		print("FAIL: cannot read " + TABLE)
		quit(1)
		return

	# id -> declared real-world length, from the one table the build script also reads.
	var want := {}
	for w in cfg["weapons"]:
		want[w["id"]] = float(w["length_m"])
	for id in cfg["primitives"]:
		# the table carries a "note" string beside the entries; only the dictionaries are weapons
		if typeof(cfg["primitives"][id]) != TYPE_DICTIONARY:
			continue
		var s: Array = cfg["primitives"][id]["size"]
		want[id] = max(float(s[0]), max(float(s[1]), float(s[2])))

	var world := Node3D.new()
	root.add_child(world)
	await physics_frame

	print("")
	print("=== every weapon is its real-world size ===")
	var ids: Array = want.keys()
	ids.sort()
	for id in ids:
		var packed: PackedScene = load(SCENES % id)
		if packed == null:
			_check(id, false, "no scene")
			continue
		var inst: Node3D = packed.instantiate() as Node3D
		world.add_child(inst)
		# Say it is CARRIED, as WeaponController does before it reparents onto a socket. Left loose
		# the item wraps itself in a PickupBody (W15) and LENDS it the authored CollisionShape3D
		# children -- so they stop being the item's own, and the collider checks below silently
		# measured nothing at all.
		inst.call("on_picked_up")
		await physics_frame

		var got := [false]
		var box := _visual(inst, inst, AABB(), got)
		var size: Vector3 = box.size
		var longest: float = max(size.x, max(size.y, size.z))
		var target: float = want[id]
		var err: float = absf(longest - target) / target

		# 1. real-world size
		_check("%s is %.2f m" % [id, target], got[0] and err <= LENGTH_TOL,
			"measured %.3f m (%.1f%% out)" % [longest, err * 100.0])

		# 2. nothing left compensating in the scene
		var compensating := ""
		for c in inst.get_children():
			if c is Node3D and String(c.scene_file_path).ends_with(".glb"):
				if not (c as Node3D).transform.is_equal_approx(Transform3D.IDENTITY):
					compensating = c.name
		_check("%s: model instanced at identity" % id, compensating == "",
			"the asset conforms" if compensating == "" else "%s still carries a transform" % compensating)

		# 3. the muzzle is where the weapon points
		var muzzle: Node3D = null
		for c in inst.get_children():
			if c is Marker3D and c.name == "Muzzle":
				muzzle = c as Node3D
		if muzzle != null:
			_check("%s: muzzle is on -Z" % id, muzzle.position.z < 0.0,
				"muzzle z = %.3f" % muzzle.position.z)

		# 4. a collider a physics engine can actually rest on a heightfield
		var thinnest := 1e9
		var col_len := 0.0
		for c in inst.get_children():
			if c is CollisionShape3D and c.shape is BoxShape3D:
				var bs: Vector3 = (c.shape as BoxShape3D).size
				thinnest = min(thinnest, min(bs.x, min(bs.y, bs.z)))
				col_len = max(col_len, max(bs.x, max(bs.y, bs.z)))
		if thinnest < 1e8:
			_check("%s: collider is not paper-thin" % id, thinnest >= MIN_COLLIDER,
				"thinnest axis %.3f m (>= %.2f, or it sinks through ground)" % [thinnest, MIN_COLLIDER])
			_check("%s: collider matches the weapon" % id, col_len >= target * 0.6 and col_len <= target * 1.4,
				"collider %.3f m vs weapon %.3f m" % [col_len, target])

		inst.queue_free()
		await physics_frame

	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
