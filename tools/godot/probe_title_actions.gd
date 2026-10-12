extends SceneTree
## The title screen's three world actions, pressed as BUTTONS (PLAN.md 1.3 rest, 2026-10-10): Continue, Host, Join.
## They run through FrontEnd (the choice crosses the scene change, runs once the world's local player exists) and had
## no gate of their own (Host was only ever exercised as the F6 debug key, Join as F7).
##
##   --role=new (one process): New game wipes everything but settings and key bindings (see _new_game)
##   --role=continue (one process):
##       stdbuf -oL <godot> --headless --fixed-fps 60 --path . --script tools/godot/probe_title_actions.gd -- --role=continue
##     New game -> walk the player 6 m off the spawn -> autosave -> Quit to title -> Continue is ENABLED -> press it ->
##     the world comes back with the player where the save put it (not the spawn). Control: the spawn is >= 5 m away.
##     (Under --script the slots are user://test/saves -- SaveSystem's harness rule -- so the player's own autosave is
##     never touched; the backup below is belt and braces.)
##   --role=host / --role=join (two processes, tools/net/run_title_coop.sh): Host on one title, Join 127.0.0.1 on the
##     other; each side must see the session (NetworkManager.session_now) and BOTH players in its PlayerRegistry.
##     Then the PROFILE HANDSHAKE (PLAN.md 1.4, AR2): the joiner grants its own profile 4321 dollars on the title; the
##     host must hold that as the joiner's session copy, then pays the joiner's body 1000 (money moves on the host);
##     the joiner must receive its profile back at 5321 and save it (reloaded from its file).

var fails := 0
var role := "continue"

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", label, detail])

func _frames(n: int) -> void:
	for i in range(n):
		await process_frame

func _find(n: Node, nm: String) -> Node:
	if n.name == nm:
		return n
	for c in n.get_children():
		var r := _find(c, nm)
		if r != null:
			return r
	return null

func _arg(name: String, def: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--%s=" % name):
			return a.substr(name.length() + 3)
	return def

func _local_player() -> Node3D:
	return root.get_node("PlayerRegistry").call("local_player_now")

func _players() -> int:
	return int(root.get_node("PlayerRegistry").call("player_count_now"))

## wait (in frames) until `cond` (a Callable) is true or `limit` frames pass; true when it became true
func _wait(cond: Callable, limit: int) -> bool:
	for i in range(limit):
		if cond.call():
			return true
		await process_frame
	return cond.call()

func _to_title() -> void:
	change_scene_to_file(String(ProjectSettings.get_setting("application/run/main_scene")))
	await _frames(10)

func _press(name: String) -> void:
	var b := _find(current_scene, name) as Button
	if b == null:
		_check("the title has a %s button" % name, false)
		return
	b.emit_signal("pressed")

func _initialize() -> void:
	role = _arg("role", "continue")
	print("=== probe_title_actions role=%s ===" % role)
	match role:
		"continue":
			await _continue()
		"new":
			await _new_game()
		"host", "join":
			await _coop()
	print("RESULT: %s (%d failure(s)) role=%s" % ["PASS" if fails == 0 else "FAIL", fails, role])
	quit(0 if fails == 0 else 1)

func _continue() -> void:
	var save: Node = root.get_node("SaveSystem")
	var fe: Node = root.get_node("FrontEnd")
	await _to_title()
	# read AFTER the first frames: the SaveSystem AutoLoad's _ready (which moves a --script run to user://test/saves)
	# has not run yet inside _initialize
	var path: String = save.call("slot_path", 0)
	var backup := FileAccess.get_file_as_string(path) if FileAccess.file_exists(path) else ""
	_press("Newgame")
	var up := await _wait(func(): return _local_player() != null, 3600)
	_check("New game reaches the world with a local player", up)
	if not up:
		return
	await _frames(60)
	var p := _local_player()
	var spawn := p.global_position
	# 6 m off the spawn along the ground; teardown-free move: velocity AND the movement controller's own fall speed
	var target := spawn + Vector3(6.0, 0.5, 0.0)
	p.global_position = target
	p.set("velocity", Vector3.ZERO)
	var mc: Node = _find(p, "MovementController")
	if mc != null:
		mc.call("clear_motion")   # a hand teleport keeps the controller's own fall speed otherwise (CLAUDE.md)
	await _frames(90)
	var saved_at := p.global_position
	var ok: bool = save.call("save_slot", 0)
	_check("autosave written", ok and FileAccess.file_exists(path), "%s at %s" % [path, saved_at])
	_check("control: the saved spot is away from the spawn", saved_at.distance_to(spawn) >= 5.0,
		"%.2f m" % saved_at.distance_to(spawn))
	_quit_to_title()
	await _frames(15)
	var cont := _find(current_scene, "Continue") as Button
	_check("back on the title, Continue is enabled", cont != null and not cont.disabled,
		"scene %s" % (current_scene.name if current_scene else "-"))
	if cont == null or cont.disabled:
		return
	_press("Continue")
	var ran := await _wait(func(): return String(fe.call("last_run_now")).begins_with("continue"), 3600)
	_check("FrontEnd ran the continue", ran and String(fe.call("last_run_now")) == "continue true",
		String(fe.call("last_run_now")))
	await _wait(func(): return int(save.call("pending_player_count")) == 0, 300)
	await _frames(30)
	p = _local_player()
	var d: float = p.global_position.distance_to(saved_at) if p != null else 1e9
	_check("the player is back where the save put it", d < 1.0, "%.2f m from the saved spot, %.2f from the spawn"
		% [d, p.global_position.distance_to(spawn) if p != null else -1.0])
	# put the user's own autosave back
	if backup == "":
		DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	else:
		var f := FileAccess.open(path, FileAccess.WRITE)
		f.store_string(backup)
		f.close()

## --role=new: NEW GAME IS NEW (user, 2026-10-11: "New game seems not to start a new game, but rather continues";
## "wipe everything except settings and key bindings"). A first game is DIRTIED -- money granted, a car's worth spent
## into a debt, police stars, the player moved, an autosave written -- then Quit to title and New game again: the
## balance is the starting one, nobody is wanted, the player stands at the spawn, the mission log has nothing
## completed or in progress, and the old autosave is gone (Continue is disabled until the new game saves).
func _new_game() -> void:
	var save: Node = root.get_node("SaveSystem")
	var fe: Node = root.get_node("FrontEnd")
	await _to_title()
	var path: String = save.call("slot_path", 0)
	var backup := FileAccess.get_file_as_string(path) if FileAccess.file_exists(path) else ""
	_press("Newgame")
	var up := await _wait(func(): return _local_player() != null, 3600)
	_check("New game reaches the world with a local player", up)
	if not up:
		return
	await _frames(60)
	var p := _local_player()
	var spawn := p.global_position
	var start_balance := int(save.call("profile_balance_now"))
	var ws: Node = root.get_node("GameManager").get_node("WantedSystem")
	var rt: Node = root.get_node("ActivityRuntime")
	var pid: String = p.get("character_info").get("character_id")
	# dirty it
	save.call("grant_profile_now", 77000)
	ws.call("set_stars_now", pid, 3, true)
	p.global_position = spawn + Vector3(6.0, 0.5, 0.0)
	p.set("velocity", Vector3.ZERO)
	var mc: Node = _find(p, "MovementController")
	if mc != null:
		mc.call("clear_motion")
	await _frames(60)
	save.call("save_slot", 0)
	_check("control: the first game is dirty (money, stars, an autosave)", int(save.call("profile_balance_now")) == start_balance + 77000
		and int(ws.call("stars_now", pid)) == 3 and FileAccess.file_exists(path),
		"balance %d, stars %d" % [int(save.call("profile_balance_now")), int(ws.call("stars_now", pid))])
	_quit_to_title()
	await _frames(15)
	_press("Newgame")
	await _wait(func(): return _local_player() != null and int(fe.call("new_games_now")) == 2, 3600)
	await _frames(90)
	p = _local_player()
	_check("a second New game was started", p != null and int(fe.call("new_games_now")) == 2, str(fe.call("new_games_now")))
	if p == null:
		return
	pid = p.get("character_info").get("character_id")
	_check("the balance is the starting one again", int(save.call("profile_balance_now")) == start_balance,
		"%d (started with %d)" % [int(save.call("profile_balance_now")), start_balance])
	_check("nobody is wanted", int(ws.call("stars_now", pid)) == 0, "%d star(s)" % int(ws.call("stars_now", pid)))
	_check("the player stands at the spawn", p.global_position.distance_to(spawn) < 2.0, "%.2f m from it" % p.global_position.distance_to(spawn))
	var log := str(rt.call("mission_log_now"))
	_check("the mission log has nothing completed or in progress", not log.contains("|COMPLETED|") and not log.contains("|IN PROGRESS|"), log)
	_check("no car is owned", str(save.call("profile_vehicles_now")) == "" or str(save.call("profile_vehicles_now")) == "[]", str(save.call("profile_vehicles_now")))
	_check("the old game's autosave is gone", not FileAccess.file_exists(path))
	if backup != "":
		var f := FileAccess.open(path, FileAccess.WRITE)
		f.store_string(backup)
		f.close()

## the pause menu's "Quit to title" button (FrontEnd.toTitle is static Java, so it is reached the way the player does)
func _quit_to_title() -> void:
	var btn := _find(current_scene, "QuitToTitle") as Button
	_check("the pause menu has Quit to title", btn != null)
	if btn != null:
		btn.emit_signal("pressed")

func _coop() -> void:
	var fe: Node = root.get_node("FrontEnd")
	var net: Node = root.get_node("NetworkManager")
	var saves: Node = root.get_node("SaveSystem")
	await _to_title()
	if role == "join":
		saves.call("grant_profile_now", 4321)
	if role == "host":
		_press("Hostco-op")
	else:
		var addr := _find(current_scene, "Address") as LineEdit
		if addr != null:
			addr.text = "127.0.0.1"
		_press("Joinco-op")
	var ran := await _wait(func(): return String(fe.call("last_run_now")).begins_with(role), 4800)
	var last := String(fe.call("last_run_now"))
	_check("FrontEnd ran the %s" % role, ran and last.ends_with("true"), last)
	var want := "host" if role == "host" else "client"
	var joined := await _wait(func(): return String(net.call("session_now")).begins_with(want + " peers=1") and _players() >= 2, 6000)
	_check("the session is up with the other peer, and both players exist", joined,
		"%s, players %d" % [net.call("session_now"), _players()])
	print("[title] SUMMARY role=%s session=%s players=%d" % [role, String(net.call("session_now")).replace(" ", "_"), _players()])
	if role == "host":
		var held := await _wait(func(): return String(saves.call("remote_balances_now")).ends_with("=4321"), 1200)
		_check("the host holds the joiner's profile (4321 dollars)", held, String(saves.call("remote_balances_now")))
		var other: Node = root.get_node("PlayerRegistry").call("remote_player_now")
		_check("the joiner's body is here", other != null)
		if other != null:
			other.call("give_cash_now", 1000)
		_check("money moved on the host's copy", String(saves.call("remote_balances_now")).ends_with("=5321"),
			String(saves.call("remote_balances_now")))
		await _frames(900)   # stay up while the client checks
	else:
		var back := await _wait(func(): return int(saves.call("profile_balance_now")) == 5321, 1800)
		_check("the joiner got its profile back from the host (5321)", back, str(saves.call("profile_balance_now")))
		saves.call("flush_profile")
		var from := String(saves.call("reload_profile_now"))
		_check("... and saved it (reloaded from its file)", int(saves.call("profile_balance_now")) == 5321,
			"%s, %d" % [from, saves.call("profile_balance_now")])
