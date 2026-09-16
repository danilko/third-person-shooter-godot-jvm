extends SceneTree
## Does a scoped SR3 shot land on the bone under the scope's centre, at every range?
## (user report 2026-09-16: "hit the enemy but it seems not hit ... or needs several shots ... distance?")
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_sniper_hits.gd
##
## A still AICharacter is set at 30/60/120/260 m, raised so the level scope line meets its head, chest
## or belly, and offset 0 / 0.08 m (on the body) or 0.40 m (beside it). One shot each through real
## Input, scoped, a full bolt cycle apart. Asserted per shot:
##   - scope centre on a hitbox -> the shot registers, with THAT bone's damage (head x4 = 600, upper
##     torso x1 = 150, lower torso x0.75 = 112.5, legs x0.5 = 75);
##   - scope centre beside the body -> nothing registers.
##
## Found and fixed with it (CLAUDE.md W31): 12 of 24 on-body shots registered, several on the wrong
## bone, because every shot carried the weapon's own per-shot bloom (0.605 deg cone on a 0.005 deg
## rifle), and the scoped shot left the muzzle rather than the scope.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const AI     := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const SR3    := "res://src/main/resources/com/openworld/weapon/SR3.tscn"
const IMPACT := "res://src/main/java/com/openworld/world/manager/ImpactManager.java"

var world: Node3D
var fails := 0

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-46s %s" % ["PASS" if ok else "FAIL", label, detail])

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

var log_hits: Array = []
var shot_index := 0

## Damage SR3 (150) does to the bone the scope is on, per Health's built-in table; -1 = not checked.
func _expected(bone: String) -> float:
	var b := bone.replace("Physical Bone ", "")
	if b.begins_with("head") or b.begins_with("neck"):
		return 600.0
	if b in ["spine_03", "clavicle_l", "clavicle_r"]:
		return 150.0
	if b in ["spine_02", "spine_01", "pelvis"]:
		return 112.5
	if b.begins_with("thigh") or b.begins_with("calf") or b.begins_with("foot"):
		return 75.0
	return -1.0

## One still target, one shot. Returns [fired, scopeCollider, damages registered on this target].
func _shoot(p: Node3D, gun: Node3D, d: float, raise: float, lat: float) -> Array:
	shot_index += 1
	var my_index := shot_index
	var t: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	world.add_child(t)
	var stand := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(1, maxf(raise, 0.01), 1)
	cs.shape = sh
	stand.add_child(cs)
	world.add_child(stand)
	stand.global_position = Vector3(lat, maxf(raise, 0.01) * 0.5 - 0.005, -d)
	t.global_position = Vector3(lat, raise, -d)
	t.global_rotation = Vector3(0, PI, 0)
	t.set_physics_process(false)
	var mc: Node = t.get_node_or_null("MovementController")
	if mc != null:
		mc.set_physics_process(false)
	var at: Node = _find(t, "AnimationTree")
	if at != null:
		at.set("active", false)
	t.get_node("Health").connect("hit", func(dmg): log_hits.append([Engine.get_physics_frames(), my_index, dmg]))
	await _tick(10)
	var ray: RayCast3D = p.get_node("ActiveCamera/AimRay") as RayCast3D
	var sight := "-"
	if ray.is_colliding():
		sight = String(ray.get_collider().name)
	var mag0: int = int(gun.get("magazine"))
	var press := Engine.get_physics_frames()
	Input.action_press("fire")
	var fired := -1
	var sight_at_shot := sight
	for i in range(95):
		await physics_frame
		if i == 2:
			Input.action_release("fire")
		if fired < 0 and int(gun.get("magazine")) != mag0:
			fired = Engine.get_physics_frames()
			# The scope line on the frame the shot resolved. A line on a bone BOUNDARY can meet the next
			# bone one frame later (the eye settles by a centimetre after the zoom returns); either is a
			# shot that went where the scope was.
			sight_at_shot = String(ray.get_collider().name) if ray.is_colliding() else "-"
	var mine := log_hits.filter(func(e): return e[1] == my_index)
	t.queue_free()
	stand.queue_free()
	await _tick(3)
	return [fired >= 0, sight, mine.map(func(e): return e[2]), sight_at_shot]

func _initialize() -> void:
	world = Node3D.new()
	root.add_child(world)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(1200, 2, 1200)
	cs.shape = sh
	floor.add_child(cs)
	world.add_child(floor)
	floor.position = Vector3(0, -1, 0)
	world.add_child(load(IMPACT).new())
	await _tick(3)

	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
	await _tick(40)
	var gun: Node3D = (load(SR3) as PackedScene).instantiate() as Node3D
	world.add_child(gun)
	gun.global_position = p.global_position + Vector3(0, 0.3, 0)
	await _tick(30)
	var wc: Node = p.get_node("WeaponController")
	for slot in range(6):
		if String(gun.get_parent().name).begins_with("Socket"):
			break
		wc.call("on_set_weapon", slot)
		await _tick(40)
	# Base spread 0, so a scope line on a bone's edge is not a coin toss on SR3's 0.005 deg cone (~1 cm
	# at 260 m; the cone itself is SpreadPatternTest's). Bloom is left AS SHIPPED on purpose: the defect
	# this gate caught was the 0.6 deg per-shot bloom landing on the shot that caused it, and that would
	# still scatter every shot here.
	gun.set("spread", 0.0)
	gun.get("scope").set("sway", 0.0)
	gun.set("magazine", 99)
	p.set("is_fps_mode", true)
	Input.action_press("aim")
	await _tick(60)
	print("scoped %s" % p.call("scoped_now"))

	# Grid: distance x where on the body the scope's centre sits (the target is raised so the level
	# eye ray meets a lower part) x lateral offset (0 = centre line, then toward the silhouette edge).
	var on_body := 0
	var right := 0
	var beside := 0
	var beside_clean := 0
	for d in [30.0, 60.0, 120.0, 260.0]:
		for part in [["head", 0.0], ["chest", 0.30], ["belly", 0.45]]:
			for lat in [0.0, 0.08, 0.40]:
				var r: Array = await _shoot(p, gun, d, float(part[1]), lat)
				var sight: String = r[1]
				var got: Array = r[2]
				var verdict := ""
				if sight == "-":
					beside += 1
					if got.is_empty():
						beside_clean += 1
						verdict = "clean miss"
					else:
						verdict = "WRONG: registered %s" % str(got)
				else:
					on_body += 1
					var want: float = _expected(sight)
					var want2: float = _expected(String(r[3]))
					if got.size() == 1 and (want < 0.0 or absf(float(got[0]) - want) < 0.01 or absf(float(got[0]) - want2) < 0.01):
						right += 1
						verdict = "hit %s" % got[0]
					else:
						verdict = "WRONG: got %s, %s wants %s" % [str(got), sight, want]
				print("  %5.0f m  %-5s lat %.2f  scope on %-24s  %s" % [d, part[0], lat, sight, verdict])
	print("")
	_check("every shot on a hitbox lands on THAT bone", right == on_body, "%d/%d" % [right, on_body])
	_check("every shot beside the body misses", beside_clean == beside, "%d/%d" % [beside_clean, beside])

	Input.action_release("aim")
	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
