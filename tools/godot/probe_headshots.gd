extends SceneTree
## HOW MANY HEADSHOTS EACH GUN TAKES (user 2026-10-08: "2 for a rifle, but the M4 2 vs the AK 1, to tell them apart;
## a sniper rifle one-shots"). WeaponStats.headshot_scale scales a head hit before Health's x4.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_headshots.gd [-- --control]
##
## Per weapon, a fresh Player (first person, aim held, spread 0) takes the gun through a real pickup and fires ONE
## round through Input at a still AICharacter's head 12 m away. Asserted: the head took damage x4 x headshot_scale,
## and the target died or lived as the table says. --control sets every headshot_scale back to 1 (ASR2, PIS1, DUP1 then
## one-tap) and fails exactly those 3.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const AI     := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const IMPACT := "res://src/main/java/com/openworld/world/manager/ImpactManager.java"
const WEAPONS := "res://src/main/resources/com/openworld/weapon/"

## id -> one headshot kills a 100 HP body
const TABLE := {"ASR1": true, "ASR2": false, "SMG1": false, "PIS1": false, "DUP1": false,
	"PIS2": true, "REV1": true}   # SNR1 (600, one-shot) is probe_sniper_hits.gd's

var world: Node3D
var fails := 0
var control := false

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

func _one(id: String, kills: bool, slot_x: float) -> void:
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(slot_x, 1.2, 0)
	await _tick(30)
	var gun: Node3D = (load(WEAPONS + id + ".tscn") as PackedScene).instantiate() as Node3D
	world.add_child(gun)
	gun.global_position = p.global_position + Vector3(0, 0.3, 0)
	await _tick(30)
	var wc: Node = p.get_node("WeaponController")
	for slot in range(7):
		if String(gun.get_parent().name).begins_with("Socket"):
			break
		wc.call("on_set_weapon", slot)
		await _tick(40)
	if control:
		gun.set("headshot_scale", 1.0)
	gun.set("spread", 0.0)
	gun.set("magazine", 30)
	var scope = gun.get("scope")
	if scope != null:
		scope.set("sway", 0.0)
	var base: float = float(gun.get("damage"))
	var scale: float = float(gun.get("headshot_scale"))
	p.set("is_fps_mode", true)
	Input.action_press("aim")
	await _tick(60)
	# the target: its head_2 bone where the camera ray lands
	var t: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	world.add_child(t)
	t.set_physics_process(false)
	var mc: Node = t.get_node_or_null("MovementController")
	if mc != null:
		mc.set_physics_process(false)
	var at: Node = _find(t, "AnimationTree")
	if at != null:
		at.set("active", false)
	var cam: Camera3D = p.get_node("ActiveCamera") as Camera3D
	t.global_position = Vector3(cam.global_position.x, 0, cam.global_position.z - 12.0)
	t.global_rotation = Vector3(0, PI, 0)
	await _tick(5)
	var head: Node3D = _find(t, "Physical Bone head_2") as Node3D
	t.global_position.y += cam.global_position.y - head.global_position.y
	await _tick(10)
	var hits: Array = []
	var health: Node = t.get_node("Health")
	health.connect("hit", func(d): hits.append(d))
	var ray: RayCast3D = p.get_node("ActiveCamera/AimRay") as RayCast3D
	var sight := String(ray.get_collider().name) if ray.is_colliding() else "-"
	Input.action_press("fire")
	await _tick(3)
	Input.action_release("fire")
	await _tick(30)
	Input.action_release("aim")
	var want := base * 4.0 * scale
	var got: float = float(hits[0]) if hits.size() > 0 else -1.0
	var dead: bool = float(health.call("health_now")) <= 0.0
	_check("%s: one head hit does %.1f" % [id, want], absf(got - want) < 0.05,
		"got %s (aim on %s, %.0f x4 x%.2f)" % [hits, sight, base, scale])
	_check("%s: one headshot %s" % [id, "kills" if kills else "does not kill"], dead == kills,
		"health %.1f" % float(health.call("health_now")))
	p.queue_free()
	t.queue_free()
	gun.queue_free()
	await _tick(5)

func _initialize() -> void:
	control = "--control" in OS.get_cmdline_user_args()
	world = Node3D.new()
	root.add_child(world)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(400, 2, 400)
	cs.shape = sh
	floor.add_child(cs)
	world.add_child(floor)
	floor.position = Vector3(0, -1, 0)
	world.add_child(load(IMPACT).new())
	await _tick(3)
	var x := 0.0
	for id in TABLE:
		await _one(id, TABLE[id], x)
		x += 30.0
	print("")
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails > 0 else 0)
