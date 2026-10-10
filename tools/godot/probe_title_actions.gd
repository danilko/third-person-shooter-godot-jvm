extends SceneTree
## The title screen's three world actions, pressed as BUTTONS (PLAN.md 1.3 rest, 2026-10-10): Continue, Host, Join.
## They run through FrontEnd (the choice crosses the scene change, runs once the world's local player exists) and had
## no gate of their own (Host was only ever exercised as the F6 debug key, Join as F7).
##
##   --role=continue (one process):
##       stdbuf -oL <godot> --headless --fixed-fps 60 --path . --script tools/godot/probe_title_actions.gd -- --role=continue
##     New game -> walk the player 6 m off the spawn -> autosave -> Quit to title -> Continue is ENABLED -> press it ->
##     the world comes back with the player where the save put it (not the spawn). Control: the spawn is >= 5 m away.
##     The user's own autosave is backed up first and put back at the end.
##   --role=host / --role=join (two processes, tools/net/run_title_coop.sh): Host on one title, Join 127.0.0.1 on the
##     other; each side must see the session (NetworkManager.session_now) and BOTH players in its PlayerRegistry.

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
		"host", "join":
			await _coop()
	print("RESULT: %s (%d failure(s)) role=%s" % ["PASS" if fails == 0 else "FAIL", fails, role])
	quit(0 if fails == 0 else 1)

func _continue() -> void:
	var save: Node = root.get_node("SaveSystem")
	var fe: Node = root.get_node("FrontEnd")
	var path: String = save.call("slot_path", 0)
	var backup := FileAccess.get_file_as_string(path) if FileAccess.file_exists(path) else ""
	await _to_title()
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

## the pause menu's "Quit to title" button (FrontEnd.toTitle is static Java, so it is reached the way the player does)
func _quit_to_title() -> void:
	var btn := _find(current_scene, "QuitToTitle") as Button
	_check("the pause menu has Quit to title", btn != null)
	if btn != null:
		btn.emit_signal("pressed")

func _coop() -> void:
	var fe: Node = root.get_node("FrontEnd")
	var net: Node = root.get_node("NetworkManager")
	await _to_title()
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
		await _frames(600)   # stay up while the client checks
