extends SceneTree
## The PLAYER PROFILE and save v2 (PLAN.md 1.4: AR2 + CR4 + CR5, 2026-10-10).
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_profile.gd
##
## 1. under --script the profile is the TEST file (never the player's real user://profile.json), fresh each run;
## 2. money is the profile's, not the body's: a grant through the body reaches the profile; a PURCHASE the balance
##    cannot cover is refused and changes nothing; a BILL runs into debt (CR4: a negative balance);
## 3. the profile file is written with a checksum and two backups; a TORN file falls back to the newest good backup
##    (control: the torn file itself is unreadable -- its checksum fails);
## 4. a v1 world slot (no checksum line, schema 1) is MIGRATED and loads; a slot from a newer build is refused;
## 5. coalesced autosave: two beats inside the window write once; the window passing writes the rest; a mission end
##    always writes.
## Co-op (the handshake) is gated by tools/net/run_title_coop.sh --profile.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const SLOT := 7

var fails := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _global(p: String) -> String:
	return p if not p.begins_with("user://") else ProjectSettings.globalize_path(p)

func _initialize() -> void:
	var saves: Node = root.get_node("SaveSystem")
	var director: Node = root.get_node("MissionDirector")
	saves.set("autosave_enabled", false)
	var world := Node3D.new()
	root.add_child(world)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(60, 2, 60)
	cs.shape = sh
	floor.add_child(cs)
	world.add_child(floor)
	floor.position = Vector3(0, -1, 0)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(0, 1.0, 0)
	await _tick(30)

	print("=== 1. the test profile ===")
	var path := String(saves.call("profile_path_now"))
	_check("a probe uses the TEST profile file", path.contains("/test/") and path.ends_with("profile.json"), path)
	_check("... and starts fresh", int(saves.call("profile_balance_now")) == 0, str(saves.call("profile_balance_now")))

	print("=== 2. money is the profile's ===")
	p.call("give_cash_now", 1000)
	_check("a grant through the body reaches the profile", int(saves.call("profile_balance_now")) == 1000
		and int(p.call("cash_now")) == 1000, "profile %d, body reads %d" % [saves.call("profile_balance_now"), p.call("cash_now")])
	_check("a purchase it cannot cover is refused", not bool(saves.call("spend_profile_now", 5000))
		and int(saves.call("profile_balance_now")) == 1000, str(saves.call("profile_balance_now")))
	_check("one it can is taken", bool(saves.call("spend_profile_now", 400)) and int(saves.call("profile_balance_now")) == 600, "")
	saves.call("bill_profile_now", 2600)
	_check("a bill runs into DEBT (CR4)", int(saves.call("profile_balance_now")) == -2000, str(saves.call("profile_balance_now")))
	_check("... and the body shows it", int(p.call("cash_now")) == -2000, str(p.call("cash_now")))

	print("=== 3. the profile file: checksum, backups, a torn file ===")
	_check("flush writes it", bool(saves.call("flush_profile")) and FileAccess.file_exists(path), path)
	var text := FileAccess.get_file_as_string(path)
	_check("... with a checksum line", text.begins_with("#sha256:"), text.substr(0, 20))
	saves.call("grant_profile_now", 5000)          # balance 3000
	saves.call("flush_profile")
	_check("the second write rotated the first to .bak1", FileAccess.file_exists(path + ".bak1"), "")
	var reread := String(saves.call("reload_profile_now"))
	_check("a clean reload reads the file itself", reread == "file" and int(saves.call("profile_balance_now")) == 3000,
		"%s, %d" % [reread, saves.call("profile_balance_now")])
	var torn := FileAccess.get_file_as_string(path).replace("3000", "9999")
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_string(torn)
	f.close()
	reread = String(saves.call("reload_profile_now"))
	_check("a TORN file falls back to .bak1 (the previous good write)", reread == "bak1"
		and int(saves.call("profile_balance_now")) == -2000, "%s, %d" % [reread, saves.call("profile_balance_now")])
	_check("control: the torn value never loaded", int(saves.call("profile_balance_now")) != 9999, "")

	print("=== 4. a v1 world slot is migrated, a newer one refused ===")
	var slot_path := String(saves.call("slot_path", SLOT))
	saves.call("delete_slot", SLOT)
	DirAccess.make_dir_recursive_absolute(_global(slot_path).get_base_dir())
	f = FileAccess.open(slot_path, FileAccess.WRITE)
	f.store_string('{"schema":1,"scene":"","campaign":{"achieved":[],"completed":["m_v1_probe"],"unlocked":[],"granted_unique":[],"fired_beats":[]},"factions":[],"campaign_factions":[],"mission":{"active":false,"id":"","path":""},"players":[]}')
	f.close()
	director.call("reset_campaign")
	var loaded: bool = saves.call("load_slot", SLOT)
	_check("a v1 slot (no checksum, schema 1) LOADS (it was refused before)", loaded, String(saves.call("last_save_message")))
	_check("... and its campaign came through", bool(director.call("has_completed", "m_v1_probe")), "")
	f = FileAccess.open(slot_path, FileAccess.WRITE)
	f.store_string('{"schema":99,"campaign":{}}')
	f.close()
	_check("a slot from a NEWER build is refused", not bool(saves.call("load_slot", SLOT)), String(saves.call("last_save_message")))
	saves.call("delete_slot", SLOT)

	print("=== 5. coalesced autosave ===")
	saves.call("delete_slot", 0)
	saves.set("autosave_enabled", true)
	saves.set("autosave_min_seconds", 2.0)
	await _tick(130)                                 # the window since any earlier write has passed
	var w0 := int(saves.call("saves_written"))
	director.call("trigger_beat", "coalesce_a")
	await _tick(2)
	director.call("trigger_beat", "coalesce_b")
	await _tick(2)
	_check("two beats inside the window wrote ONCE", int(saves.call("saves_written")) == w0 + 1,
		"%d writes" % (int(saves.call("saves_written")) - w0))
	await _tick(150)
	_check("the window passing wrote the second", int(saves.call("saves_written")) == w0 + 2,
		"%d writes" % (int(saves.call("saves_written")) - w0))
	saves.call("on_mission_completed", "probe_mission", "police", "DONE")
	_check("a mission end writes at once", int(saves.call("saves_written")) == w0 + 3, "")
	saves.set("autosave_enabled", false)
	saves.call("delete_slot", 0)

	print("=== 6. a mission the players win pays the table's reward; one the police win pays nothing ===")
	var missions: Node = root.get_node("MissionManager")
	const MISSION := "res://src/main/resources/com/openworld/game/mission/GangA_vs_Police_Mission.tres"
	var b0 := int(p.call("cash_now"))
	missions.call("start_mission_from_path", MISSION)
	await _tick(4)
	missions.call("complete_mission_now", "police", "ELIMINATED")
	await _tick(4)
	_check("control: the police won -- nothing paid", int(p.call("cash_now")) == b0, "%+d" % (int(p.call("cash_now")) - b0))
	missions.call("start_mission_from_path", MISSION)
	await _tick(4)
	missions.call("complete_mission_now", "player", "CLEAN")
	await _tick(4)
	_check("the players won: the mission reward (economy.json mission_default)", int(p.call("cash_now")) - b0 == 10000,
		"%+d" % (int(p.call("cash_now")) - b0))

	print("RESULT: %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
