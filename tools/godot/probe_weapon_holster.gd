extends SceneTree
## Where does a weapon HANG when it is holstered, now that it hangs by its grip?
##
##   godot --headless --fixed-fps 60 --path . --script tools/godot/probe_weapon_holster.gd
##
## PLAN.md A4. W20 moved every model's ORIGIN onto the grip and replaced the per-weapon markers on
## the character with one socket per grip archetype. `WeaponController.reparentWeapon` asks the
## weapon how it sits (`WeaponItem.alignmentFor(holstered)`), and since no shipped weapon declares a
## `holsterPoint`, a HOLSTERED weapon now puts its GRIP on the back/hip socket -- where it used to
## put its arbitrary old origin. The holster sockets themselves were authored against the old
## origins and were never re-checked, so this measures what they hold now.
##
## Measured per weapon, in MeshRoot's frame (the mesh is -Z forward, so `fwd` = -z):
##   - the socket it actually reached (or that it was stowed hidden)
##   - its own collision box's 8 corners -> the rear point, the muzzle-end point and the envelope
##   - POKE: a grid of points inside that box, queried against this character's own hitbox bones
##     (PhysicalBone3D, layer 4 -- the same bodies a bullet hits on a live character, so they track
##     the pose), plus the deepest overlap `collide_shape` reports for the box itself. This is the
##     one number that says "the gun is inside the body" rather than resting against it.
##   - HEAD: how close the box comes to head_2, because a long gun hanging by its grip swings its
##     butt up behind the neck.
##   - GROUND: the lowest corner, because one hanging by its grip can reach past the knee.
##
## The weapon is holstered the game's way: dropped on a Player whose FIST is the active weapon, so
## `WeaponController.requestEquip` files it in an inactive slot and calls `moveWeaponToHolster`.
## Nothing here poses the character -- a holstered weapon hangs off a BoneAttachment3D, so the
## measurement is of the socket and the weapon's own holster alignment, not of an animation.
##
## `-- --visuals=res://...CharacterVisuals_X.tscn` measures another body (W18).

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const WEAPON_DIR := "res://src/main/resources/com/openworld/weapon/%s.tscn"
## Every weapon that declares holster sockets: the four long guns (back) and the three short (hip).
## Everything that holsters: the catalog minus the fist and the throwable (PLAN.md 2.8 item 7).
var WEAPONS: Array = _catalog_weapons()

static func _catalog_weapons() -> Array:
	var cat: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://src/main/resources/com/openworld/weapon/weapon_catalog.json"))
	var out := []
	for row in cat["weapons"]:
		if not (row["archetype"] in ["fist", "throwable"]):
			out.append(row["id"])
	return out

## A holstered weapon rests AGAINST the body, so some hitbox contact is expected. These are the
## limits for "inside it": POKE_DEPTH is the deepest overlap `collide_shape` may report against the
## ragdoll bones, POKE_FRACTION the share of the weapon's own volume that may sit inside one.
const POKE_DEPTH := 0.06
const POKE_FRACTION := 0.10
## A weapon may not reach into the head. head_2 is the skull bone; a skull is ~0.09 m in radius here.
const HEAD_CLEARANCE := 0.10
## Nor may any part of it rise past the top of the head -- unmistakably wrong however the rest of it
## hangs, and the vertical back sling put ATL1's tube 2.5 cm above it. The crown is MEASURED off the
## skinned `head` mesh every run (1.435 m on GodotChan, against head_2's bone at 1.357 and hair and
## headphones reaching 1.458/1.469), because a second body (W18) would make a written constant
## silently wrong. Hair and headphones are deliberately not the line: W25 already accepted a held
## launcher's tube 3.3 cm inside the headphone cup.
const CROWN_MARGIN := 0.02
## The lowest point of a holstered weapon, above the character's origin (the feet).
const GROUND_CLEARANCE := 0.25
const SETTLE_FRAMES := 60
## Samples along the weapon box's long axis / its two short axes, for the volume-inside fraction.
const GRID_LONG := 25
const GRID_SHORT := 3
## PhysicalBone3D ragdoll bones (util.CollisionLayers.HITBOX) and a layer nothing in the game uses,
## for the weapon-vs-weapon proxies below.
const HITBOX_LAYER := 8
const PROXY_LAYER := 1 << 19
## Two holstered weapons may touch (a stack of two slung guns does) but not occupy each other.
const PAIR_OVERLAP := 0.03
## The real cases: everything holstered at once because the FIST is active. This is the only way the
## SECOND socket of each pair is reached, and the only thing that can see two holstered weapons
## occupying the same space. The second is the axe, which is a long weapon (0.81 m) and rides the
## back sling, so it takes the second sling when one long gun is carried.
const LOADOUTS := [["ASR1", "SHG1", "PIS1", "MEW1"], ["ASR1", "MEW2", "PIS1"]]

var visuals_path := ""
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

func _attach(sk: Skeleton3D, bone: String) -> BoneAttachment3D:
	var a := BoneAttachment3D.new()
	sk.add_child(a)
	a.bone_name = bone
	return a

## Body-frame components: + lateral = right, + up, + fwd = the way the mesh faces (-Z).
func _parts(d: Vector3) -> String:
	return "right %+.3f  up %+.3f  fwd %+.3f" % [d.x, d.y, -d.z]

## The weapon's own body collision box (a direct CollisionShape3D child holding a BoxShape3D; the
## PickupArea's roomy detection box is a child of the area, not of the item -- W19).
func _box_of(gun: Node3D) -> CollisionShape3D:
	for c in gun.get_children():
		if c is CollisionShape3D and (c as CollisionShape3D).shape is BoxShape3D:
			return c as CollisionShape3D
	return null

## Drop `weapon_id` on `p`. The fist is the active weapon, so `WeaponController.requestEquip` files
## the pickup in an inactive slot and `moveWeaponToHolster` hangs it on a socket.
func _give(world: Node3D, p: Node3D, weapon_id: String) -> Node3D:
	var gun: Node3D = (load(WEAPON_DIR % weapon_id) as PackedScene).instantiate() as Node3D
	world.add_child(gun)
	gun.global_position = p.global_position + Vector3(0, 0.3, 0)
	await _tick(SETTLE_FRAMES)
	return gun

func _spawn_player(world: Node3D, at: Vector3) -> Node3D:
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	if visuals_path != "":
		p.set("character_visuals", load(visuals_path))
	world.add_child(p)
	p.position = at
	await _tick(40)
	return p

## A body carrying a copy of `cs`'s box where it stands, on a layer nothing else uses, so the engine's
## own OBB test can answer "do these two holstered weapons occupy the same space".
func _proxy(world: Node3D, cs: CollisionShape3D) -> StaticBody3D:
	var b := StaticBody3D.new()
	b.collision_layer = PROXY_LAYER
	b.collision_mask = 0
	var c := CollisionShape3D.new()
	c.shape = cs.shape
	b.add_child(c)
	world.add_child(b)
	b.global_transform = cs.global_transform
	return b

## Deepest overlap of `cs`'s box with whatever is on `mask`, in metres (0.0 = clear).
func _overlap(space: PhysicsDirectSpaceState3D, cs: CollisionShape3D, mask: int) -> float:
	var sq := PhysicsShapeQueryParameters3D.new()
	sq.shape = cs.shape
	sq.transform = cs.global_transform
	sq.collide_with_bodies = true
	sq.collision_mask = mask
	var pairs: Array = space.collide_shape(sq, 16)
	var depth := 0.0
	for i in range(0, pairs.size() - 1, 2):
		depth = maxf(depth, (pairs[i] as Vector3).distance_to(pairs[i + 1] as Vector3))
	return depth

## The top of the skinned `head` mesh in MeshRoot's frame: this body's crown. Hand-skinned from
## `get_bone_global_pose` (the PRE-modifier pose), which is what the head is in while idle and not
## aiming -- the same restriction probe_weapon_fit's pocket derivation works under.
func _crown(sk: Skeleton3D, to_body: Transform3D) -> float:
	var mesh: MeshInstance3D = sk.get_node_or_null("head") as MeshInstance3D
	if mesh == null or mesh.skin == null:
		return INF
	var binds: Array[Transform3D] = []
	for bi in mesh.skin.get_bind_count():
		var bone: int = mesh.skin.get_bind_bone(bi)
		if bone < 0:
			bone = sk.find_bone(mesh.skin.get_bind_name(bi))
		binds.append(to_body * sk.global_transform * sk.get_bone_global_pose(bone) * mesh.skin.get_bind_pose(bi))
	var top := -INF
	for si in mesh.mesh.get_surface_count():
		var arr: Array = mesh.mesh.surface_get_arrays(si)
		var verts: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
		var bones: PackedInt32Array = arr[Mesh.ARRAY_BONES]
		var weights: PackedFloat32Array = arr[Mesh.ARRAY_WEIGHTS]
		var k: int = bones.size() / verts.size()
		for vi in verts.size():
			var w := Vector3.ZERO
			for j in k:
				var ww: float = weights[vi * k + j]
				if ww > 0.0:
					w += (binds[bones[vi * k + j]] * verts[vi]) * ww
			top = maxf(top, w.y)
	return top

## Measure and check one holstered weapon. Returns its CollisionShape3D, or null if it never hung.
func _measure(space: PhysicsDirectSpaceState3D, p: Node3D, gun: Node3D, weapon_id: String) -> CollisionShape3D:
	var socket: String = String(gun.get_parent().name)
	var stowed: bool = not gun.visible
	print("  socket: %s%s" % [socket, "  (STOWED, hidden)" if stowed else ""])
	var hung: bool = not stowed and (socket.begins_with("LongWeaponHolsterMaker") or socket.begins_with("ShortWeaponHolsterMaker"))
	_check("%s reached a holster socket" % weapon_id, hung, "parent %s%s" % [socket, ", hidden" if stowed else ""])
	if not hung:
		return null

	var sk: Skeleton3D = _find(p, "Skeleton3D") as Skeleton3D
	var mesh_root: Node3D = _find(p, "MeshRoot") as Node3D
	var head := _attach(sk, "head_2")
	await _tick(2)
	var to_body: Transform3D = mesh_root.global_transform.affine_inverse()

	var cs: CollisionShape3D = _box_of(gun)
	var size: Vector3 = (cs.shape as BoxShape3D).size
	var bt: Transform3D = cs.global_transform
	# The weapon's long axis is -Z, so the box's -Z face is the muzzle/blade end (W19's convention).
	print("  grip on the socket        %s" % _parts(to_body * gun.global_position))
	print("  muzzle/blade end          %s" % _parts(to_body * (bt * Vector3(0, 0, -size.z * 0.5))))
	print("  butt/rear end             %s" % _parts(to_body * (bt * Vector3(0, 0, size.z * 0.5))))
	var axis: Vector3 = mesh_root.global_transform.basis.inverse() * (-gun.global_transform.basis.z)
	print("  sling direction           %s   [%.0f deg from vertical, %s]" % [
		_parts(axis), rad_to_deg(acos(clampf(-axis.y, -1.0, 1.0))),
		"muzzle down-left" if axis.x < 0.0 else "muzzle down-right"])

	# ── poke: is the weapon inside this character's own hitbox bones? ──────────────────────────
	# The PhysicalBone3D bodies (layer 4) track the live pose -- they are what a bullet hits -- so
	# they are the body the weapon is measured against. A holstered weapon RESTS on the body, so
	# contact is expected and it is the DEPTH that says whether it is inside it.
	var pq := PhysicsPointQueryParameters3D.new()
	pq.collide_with_bodies = true
	pq.collision_mask = HITBOX_LAYER
	var inside := 0
	var total := 0
	var bones := {}
	for iz in range(GRID_LONG):
		for ix in range(GRID_SHORT):
			for iy in range(GRID_SHORT):
				total += 1
				pq.position = bt * Vector3(
					(float(ix) / (GRID_SHORT - 1) - 0.5) * size.x,
					(float(iy) / (GRID_SHORT - 1) - 0.5) * size.y,
					(float(iz) / (GRID_LONG - 1) - 0.5) * size.z)
				var hits: Array = space.intersect_point(pq, 4)
				if not hits.is_empty():
					inside += 1
					for h in hits:
						bones[String((h["collider"] as Node).name)] = true
	var depth: float = _overlap(space, cs, HITBOX_LAYER)
	var frac := float(inside) / float(total)
	print("  poke: %d/%d samples inside (%.1f%%), deepest overlap %.3f m %s" % [
		inside, total, frac * 100.0, depth, bones.keys()])

	# ── head, crown and ground ────────────────────────────────────────────────────────────────
	var head_p: Vector3 = head.global_position
	var head_d := INF
	var low := INF
	var high := -INF
	for sx in [-0.5, 0.5]:
		for sy in [-0.5, 0.5]:
			for sz in [-0.5, 0.5]:
				var w: Vector3 = bt * Vector3(sx * size.x, sy * size.y, sz * size.z)
				head_d = minf(head_d, w.distance_to(head_p))
				low = minf(low, w.y - p.global_position.y)
				high = maxf(high, w.y - p.global_position.y)
	var crown: float = _crown(sk, to_body)
	print("  nearest corner to head_2  %.3f m ;  corners span %.3f .. %.3f m above the feet (crown %.3f, head_2 %.3f)"
		% [head_d, low, high, crown, (to_body * head_p).y])

	_check("%s holster: not inside the body" % weapon_id, depth < POKE_DEPTH and frac < POKE_FRACTION,
		"deepest %.3f m (limit %.2f), %.1f%% of its volume inside (limit %.0f%%)"
			% [depth, POKE_DEPTH, frac * 100.0, POKE_FRACTION * 100.0])
	_check("%s holster: clear of the head" % weapon_id, head_d > HEAD_CLEARANCE,
		"%.3f m to head_2 (limit %.2f)" % [head_d, HEAD_CLEARANCE])
	_check("%s holster: below the crown" % weapon_id, high < crown + CROWN_MARGIN,
		"highest corner %.3f m vs the crown %.3f (+%.2f allowed)" % [high, crown, CROWN_MARGIN])
	_check("%s holster: clear of the ground" % weapon_id, low > GROUND_CLEARANCE,
		"lowest corner %.3f m up (limit %.2f)" % [low, GROUND_CLEARANCE])
	return cs

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--visuals="):
			visuals_path = a.substr("--visuals=".length())
	print("visuals: %s" % ("(Player.tscn default)" if visuals_path == "" else visuals_path))
	var world := Node3D.new()
	root.add_child(world)
	_floor(world)
	await _tick(3)
	var space := root.get_world_3d().direct_space_state

	# ── one weapon at a time: what the FIRST socket of each pair holds ────────────────────────
	var x := 0.0
	for weapon_id in WEAPONS:
		print("")
		print("=== %s ===" % weapon_id)
		var p: Node3D = await _spawn_player(world, Vector3(x, 1.2, 0))
		x += 6.0
		var gun: Node3D = await _give(world, p, weapon_id)
		await _measure(space, p, gun, weapon_id)
		p.queue_free()
		await _tick(5)

	# ── the loadouts: every socket occupied, and no two weapons in the same place ─────────────
	for loadout in LOADOUTS:
		print("")
		print("=== loadout %s (fist active, so every one of them is holstered) ===" % str(loadout))
		var lp: Node3D = await _spawn_player(world, Vector3(x, 1.2, 0))
		x += 6.0
		var shapes := {}
		for weapon_id in loadout:
			print("  --- %s" % weapon_id)
			var gun: Node3D = await _give(world, lp, weapon_id)
			var cs: CollisionShape3D = await _measure(space, lp, gun, weapon_id)
			if cs != null:
				shapes[weapon_id] = cs
		var ids: Array = shapes.keys()
		for i in range(ids.size()):
			for j in range(i + 1, ids.size()):
				var other: StaticBody3D = _proxy(world, shapes[ids[j]])
				await _tick(2)
				var d: float = _overlap(space, shapes[ids[i]], PROXY_LAYER)
				other.queue_free()
				await _tick(2)
				_check("holstered %s vs %s" % [ids[i], ids[j]], d < PAIR_OVERLAP,
					"overlap %.3f m (limit %.2f)" % [d, PAIR_OVERLAP])
		lp.queue_free()
		await _tick(5)

	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
