extends SceneTree
## ENGAGEMENT v2, STEPS 4-7 (PLAN.md P1e): per-target hostility, the witness call-in, an activity's hold on the
## enforcement, AI-vs-AI incidents and their responders, and radio items.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_engagement_v2.gd [-- --control]
##   --hold-fire-off: AIs fire through bodies they may not shoot (the control for case 1's stray-fire check)
##   --control: per-target hostility OFF, call-in 0 s, AI-vs-AI incidents OFF, no hold -- each case's "with" half
##              must then fail the way the old code did.
##
## DebugWorld (the force pools are unlimited there: no places record):
##   1. PER TARGET: player A at 3 stars (invulnerable), player B 10 m away with none: in 30 s police hurt A's
##      neighbour B not at all (control: B is hurt -- the faction was hostile to every player);
##   2. CALL-IN: a civilian 12 m off sees an assault: no star for the first seconds, a star once it is called in, and
##      the police search where it HAPPENED (lost=true at the crime spot). Killed before it calls, nothing comes;
##   3. HOLD (an activity's Plan.wantedAtLeast(2) + noDispatch("police") + reserve, by holdNow): B is held at 2
##      stars, yet no police come for B; released, both end;
##   4. AI ON AI: a gang_b member hits a gang_a member 15 m from the player: one incident, answered by gang_a
##      responders (control: none). The same 400 m from every player: nothing;
##   5. RADIO: A hears nothing of an incident without a radio; given gang_a's radio, a line and a marker; sitting in a
##      patrol car takes the police scanner; a respawn takes every radio away.

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const POC1 := "res://src/main/resources/com/openworld/vehicle/POC1.tscn"

var fails := 0
var ed: Node
var ws: Node


func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1


func _tick(n: int) -> void:
	for i in n:
		await physics_frame


func _units() -> int:
	return int(String(ed.call("units_now")).split(",")[0]) + int(String(ed.call("units_now")).split(",")[1])


## Every living non-player character within r of p but `keep` (a witness is the NEAREST one: a leftover officer
## from case 1 or a crowd body would be the witness instead of the probe's civilian -- the case's flake).
func _bystanders(p: Vector3, r: float, keep: Node) -> Array:
	var out := []
	for c in get_nodes_in_group("characters"):
		if c == keep or not (c is CharacterBody3D) or c.get("character_info") == null:
			continue
		if c.is_in_group("players") or c.has_node("PlayerController") or String(c.get("character_info").get("faction")) == "player":
			continue
		if (c as Node3D).global_position.distance_to(p) <= r and float(c.get_node("Health").call("health_now")) > 0.0:
			out.append(c)
	return out


func _clear_bystanders(p: Vector3, keep: Node) -> int:
	var gone := _bystanders(p, 50.0, keep)
	for c in gone:
		c.queue_free()
	return gone.size()


func _settle(ids: Array) -> void:
	for id in ids:
		ws.call("clear_now", id)
	var t := 0.0
	while t < 60.0 and _units() > 0:
		await _tick(60)
		t += 1.0


func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	var hold_off := "--hold-fire-off" in OS.get_cmdline_user_args()
	var world: Node = (load(DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	await _tick(240)
	var gm: Node = root.get_node("GameManager")
	ws = gm.get_node("WantedSystem")
	ed = gm.get_node("EnforcementDispatch")
	var helper: Node = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
	world.add_child(helper)
	if control:
		ed.call("set_per_target_hostility_now", false)
		ws.call("set_call_in_now", 0.0)
		ed.call("set_ai_incidents_now", false)
	if hold_off:
		ed.call("set_hold_fire_on_bystanders_now", false)
	var a: Node3D = world.get_node("Characters/Player")
	var b: Node3D = (load(PLAYER) as PackedScene).instantiate()
	world.get_node("Characters").add_child(b)
	b.global_position = a.global_position + Vector3(10, 0.3, 0)
	await _tick(30)
	a.get_node("Health").set("invulnerable", true)
	var ida: String = a.get("character_info").get("character_id")
	var idb: String = b.get("character_info").get("character_id")
	var hp_b := float(b.get_node("Health").call("health_now"))

	# 1. per-target hostility
	print("== 1. A wanted at 3 stars, B beside them and not wanted")
	# The check is on TARGETING: an officer firing at A can still hit B standing 10 m off (stray fire is not
	# hostility -- it made the old health check fail ~1 run in 3), so B's health is only reported.
	var t := 0.0
	var aimed_b := 0
	var aimed_a := 0
	while t < 30.0:
		ws.call("set_stars_now", ida, 3, false)
		await _tick(30)
		t += 0.5
		for c in get_nodes_in_group("characters"):
			if c.has_method("target_id_now") and c.get("character_info") != null \
					and String(c.get("character_info").get("faction")) == "police":
				var tid := String(c.call("target_id_now"))
				aimed_b += 1 if tid == idb else 0
				aimed_a += 1 if tid == ida else 0
		# control: B IS a target there -- stop before B dies (a dead B is respawned as a NEW body, and every later
		# case still holds the old one)
		if control and float(b.get_node("Health").call("health_now")) < 300.0:
			break
	var hp_b_after := float(b.get_node("Health").call("health_now"))
	print("  B's health %.0f -> %.0f with %d police round them; officer-samples aimed at A %d, at B %d"
			% [hp_b, hp_b_after, _units(), aimed_a, aimed_b])
	_check(aimed_a > 0, "the police went for A (%d samples)" % aimed_a)
	if control:
		_check(aimed_b > 0, "control: the police went for B too (%d samples)" % aimed_b)
	else:
		_check(aimed_b == 0, "no officer ever targets B, who is not wanted (%d samples)" % aimed_b)

	# (skipped under --control: per-target hostility off makes B a TARGET, not a bystander)
	if not control:
		# 1b. B kept ON the line from one officer to A, 1.6 m BEHIND A: a miss at A goes on into B, so the officer holds
		# its fire (B BETWEEN them is no test: B then blocks the officer's sight of A and it never fires at all)
		print("== 1b. B on the line just BEHIND A from an officer (hold fire: %s)" % ("off" if hold_off else "on"))
		var cop: Node3D = ed.call("spawn_body_now", "police", a.global_position + Vector3(0, 0.3, -16), "ASR1")
		var hp_b0 := float(b.get_node("Health").call("health_now"))
		t = 0.0
		while t < 12.0:
			ws.call("set_stars_now", ida, 3, false)
			if is_instance_valid(cop):
				var away: Vector3 = (a.global_position - cop.global_position) * Vector3(1, 0, 1)
				var on_line: Vector3 = a.global_position + away.normalized() * 1.6
				b.global_position = Vector3(on_line.x, a.global_position.y, on_line.z)
				b.get_node("MovementController").call("clear_motion")
			await _tick(15)
			t += 0.25
		var hp_b1 := float(b.get_node("Health").call("health_now"))
		print("  B's health %.0f -> %.0f standing 1.6 m behind A on the officer's line for 12 s (target '%s')"
				% [hp_b0, hp_b1, String(cop.call("target_id_now")) if is_instance_valid(cop) else "?"])
		# (whether a shot fired through B also HITS B is chance -- A takes most of them -- so the control counts shots
		# fired with B in the line, not B's health)
		var fired := int(cop.call("shots_fired_now")) if is_instance_valid(cop) else 0
		var cop_held := int(cop.call("shots_held_now")) if is_instance_valid(cop) else 0
		var through := int(cop.call("shots_through_now")) if is_instance_valid(cop) else 0
		if hold_off:
			_check(through > 0, "control (--hold-fire-off): the officer fires with B in the line (%d of %d shots)" % [through, fired])
		else:
			_check(cop_held > 0 and through == 0, "the officer holds its fire while B is in the line (%d held, %d through)" % [cop_held, through])
			_check(hp_b1 == hp_b0, "and B is never hit (%.0f)" % hp_b1)
		if is_instance_valid(cop):
			cop.queue_free()
		b.global_position = a.global_position + Vector3(10, 0.3, 0)
		b.get_node("MovementController").call("clear_motion")
	b.get_node("Health").set("invulnerable", true)
	await _settle([ida, idb])

	# 2. the call-in
	print("== 2. an assault seen by a civilian")
	var civ: Node3D = ed.call("spawn_body_now", "civilian", a.global_position + Vector3(0, 0.3, 12), "")
	await _tick(30)
	print("  cleared %d other bodies round the spot (the civilian must be the nearest witness)" % _clear_bystanders(a.global_position, civ))
	await _tick(2)
	var crime_at := a.global_position
	ws.call("report_now", "assault", ida)
	await _tick(60)
	var stars_1s := int(ws.call("stars_now", ida))
	# gone from the scene before the call lands: the police are told where it HAPPENED
	a.global_position = crime_at + Vector3(150, 0, 0)
	a.get_node("MovementController").call("clear_motion")
	await _tick(60 * 4)
	var stars_5s := int(ws.call("stars_now", ida))
	var sight := String(ed.call("sight_now", ida))
	print("  stars at 1 s %d, at 5 s %d; call-ins %s; police sight: %s" % [stars_1s, stars_5s, String(ws.call("call_ins_now")), sight])
	if control:
		_check(stars_1s >= 1, "control: the star comes at once (%d)" % stars_1s)
	else:
		_check(stars_1s == 0, "no star while the witness is still calling it in")
		_check(stars_5s >= 1, "a star once it is called in (%d)" % stars_5s)
		_check(sight.contains("lost=true") and sight.contains("known=(%.1f" % crime_at.x),
				"the police know where it happened (%.1f), not where the player went" % crime_at.x)
	await _settle([ida])
	a.global_position = crime_at
	a.get_node("MovementController").call("clear_motion")
	await _tick(30)
	print("  cleared %d other bodies round the spot" % _clear_bystanders(a.global_position, civ))
	await _tick(2)
	ws.call("report_now", "assault", ida)
	await _tick(30)
	if is_instance_valid(civ):
		helper.call("kill", civ)
	await _tick(60 * 6)
	var stars_silenced := int(ws.call("stars_now", ida))
	print("  the witness killed before calling: %d stars; call-ins %s" % [stars_silenced, String(ws.call("call_ins_now"))])
	if not control:
		_check(stars_silenced == 0, "a dead witness calls nobody (%d stars)" % stars_silenced)
	await _settle([ida])

	# 3. an activity's hold
	print("== 3. held at two stars with no police dispatch")
	if not control:
		ed.call("hold_now", "probe@1", 2, -1, "police", "", 0, "", 0)
	var peak := 0
	t = 0.0
	while t < 15.0:
		await _tick(30)
		t += 0.5
		peak = maxi(peak, _units())
	var held := int(ws.call("stars_now", idb))
	print("  B held at %d stars, at most %d police units sent" % [held, peak])
	if not control:
		_check(held == 2, "Plan.wantedAtLeast(2) holds B at 2 stars (%d)" % held)
		_check(peak == 0, "Plan.noDispatch(police) sends nobody (%d)" % peak)
		ed.call("release_hold_now", "probe@1")
		await _tick(30)
		ws.call("clear_now", ida)
		ws.call("clear_now", idb)
		await _tick(30)
		_check(int(ws.call("stars_now", idb)) == 0, "released: the stars can go")

	# 4. AI on AI
	print("== 4. a gang_b member hits a gang_a member near the player")
	var i0 := String(ed.call("incidents_now")).split(",")
	var victim: Node3D = ed.call("spawn_body_now", "gang_a", a.global_position + Vector3(14, 0.3, 4), "")
	var attacker: Node3D = ed.call("spawn_body_now", "gang_b", a.global_position + Vector3(18, 0.3, 4), "")
	await _tick(20)
	helper.call("hit_by", victim, attacker, 10.0)
	helper.call("hit_by", victim, attacker, 10.0)
	await _tick(30)
	var far_v: Node3D = ed.call("spawn_body_now", "gang_a", a.global_position + Vector3(400, 0.3, 0), "")
	var far_a: Node3D = ed.call("spawn_body_now", "gang_b", a.global_position + Vector3(403, 0.3, 0), "")
	await _tick(20)
	helper.call("hit_by", far_v, far_a, 10.0)
	await _tick(60)
	var i1 := String(ed.call("incidents_now")).split(",")
	var ai_inc := int(i1[3]) - int(i0[3])
	var answered := int(i1[5]) - int(i0[5])
	var list := String(ed.call("incident_list_now"))
	# the attack on gang_a's member, near the player: ONE incident of 2 acts; nothing at the far pair (x + 400)
	var on_a := 0
	var far := 0
	for row in list.split(";"):
		var f := row.split("|")
		if f.size() < 6 or f[2] == "player":
			continue
		if f[0] == "gang_attack" and f[1] == "gang_a" and absf(float(f[3]) - (a.global_position.x + 400)) < 50:
			far += 1
		elif f[0] == "gang_attack" and f[1] == "gang_a":
			on_a += 1
	print("  incidents %s (ai %d, answered %d, live responders %s) | %s" % [String(ed.call("incidents_now")), ai_inc, answered, i1[6], list])
	if control:
		_check(ai_inc == 0 and answered == 0, "control: no AI-vs-AI incident, nobody answers")
	else:
		_check(on_a == 1 and far == 0, "two hits near the player are ONE incident on gang_a, the far one none (%d, %d)" % [on_a, far])
		_check(answered >= 1 and int(i1[6]) >= 1, "gang_a answers the attack on its member (%s responders)" % i1[6])
		# (gang_b answering gang_a's fire back is ANOTHER incident -- the escalation the rate limit and pools cap)

	# 5. radio items
	print("== 5. radios")
	# away from case 4's bodies (a radio is taken off a dead member), every radio taken
	a.global_position = crime_at + Vector3(0, 0, 160)
	a.get_node("MovementController").call("clear_motion")
	b.global_position = crime_at + Vector3(10, 0, 160)
	await _tick(60)
	ed.call("lose_radios_now", ida)
	ed.call("lose_radios_now", idb)
	await _tick(10)
	var r0 := String(ed.call("radio_now_counts")).split(",")
	ed.call("raise_incident_now", "gang_attack", a.global_position + Vector3(0, 0, 90), "gang_a", "gang_b")
	await _tick(30)
	var r1 := String(ed.call("radio_now_counts")).split(",")
	_check(int(r1[0]) == int(r0[0]), "no radio: nothing heard of another incident")
	ed.call("give_radio_now", ida, "gang_a")
	await _tick(30)
	var r2 := String(ed.call("radio_now_counts")).split(",")
	print("  radio counts %s -> %s, channels '%s'" % [",".join(r1), ",".join(r2), String(ed.call("radio_of_now", ida))])
	_check(int(r2[0]) > int(r1[0]) and int(r2[2]) >= 1, "with gang_a's radio: a line and a minimap marker")
	var car: Node3D = (load(POC1) as PackedScene).instantiate()
	world.add_child(car)
	car.global_position = a.global_position + Vector3(-8, 0.6, 0)
	await _tick(60)
	helper.call("seat_character", car, a)
	await _tick(90)
	_check(String(ed.call("radio_of_now", ida)).contains("police"), "sitting in a patrol car takes its police scanner")
	helper.call("exit_driver", car)
	await _tick(60)
	a.get_node("Health").set("invulnerable", false)
	var had := String(ed.call("radio_of_now", ida))
	# standing over a dead gang member TAKES its radio, and the respawn point is beside case 4's bodies: clear the
	# dead first, or the respawned player picks a radio up again (the case's flake)
	# (and the living: case 4's responders keep fighting, and a member who dies later is a radio again)
	for c in get_nodes_in_group("characters"):
		if c != a and c != b and c is CharacterBody3D:
			c.queue_free()
	await _tick(2)
	helper.call("kill", a)
	var gone := false
	t = 0.0
	while t < 20.0 and not gone:
		await _tick(15)
		t += 0.25
		for p in get_nodes_in_group("characters"):
			if p is CharacterBody3D and p != a and p.get("character_info") != null and p.get("character_info").get("character_id") == ida \
					and float(p.get_node("Health").call("health_now")) > 0.0 and String(ed.call("radio_of_now", ida)) == "":
				gone = true
	_check(gone, "respawned: every radio is gone ('%s' before, '%s' now)" % [had, String(ed.call("radio_of_now", ida))])
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
