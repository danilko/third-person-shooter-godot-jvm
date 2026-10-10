extends SceneTree
## The front end and the settings (PLAN.md 1.3 / F2 + H3, 2026-10-09).
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_front_end.gd
##
## 1. the title is the main scene, its first enabled button has focus (a pad works at once), Continue is enabled only
##    with an autosave;
## 2. New game loads the world with a local player;
## 3. QualitySettings: LOW sets the sun's shadow distance, the render scale and the view distance; HIGH restores them;
##    the fairness floors hold (view >= 250 m, shadows >= 80 m) -- control: the value asked for was below the floor;
## 4. Settings opens from the pause menu, and closing it writes user://settings.cfg (read back);
## 5. Quit to title returns to the title, unpaused.
## The user's own settings.cfg is backed up first and put back at the end.

const CFG := "user://settings.cfg"

var fails := 0

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

func _sun() -> DirectionalLight3D:
	return _find(current_scene, "SunLight") as DirectionalLight3D

func _initialize() -> void:
	var backup := FileAccess.get_file_as_string(CFG) if FileAccess.file_exists(CFG) else ""
	var qs: Node = root.get_node("QualitySettings")
	var fe: Node = root.get_node("FrontEnd")

	print("=== 1. the title ===")
	var main := String(ProjectSettings.get_setting("application/run/main_scene"))
	_check("the main scene is the title", main.ends_with("TitleScreen.tscn"), main)
	change_scene_to_file(main)
	await _frames(10)
	_check("the title is up", current_scene != null and current_scene.name == "TitleScreen",
		str(current_scene.name) if current_scene else "-")
	var focus := root.gui_get_focus_owner()
	_check("a button has focus (pad-ready)", focus is Button, str(focus.name) if focus else "none")
	var cont := _find(current_scene, "Continue") as Button
	var save: Node = root.get_node("SaveSystem")
	var has_save: bool = save.call("has_slot", 0)
	_check("Continue is enabled exactly when there is an autosave", cont != null and cont.disabled == (not has_save),
		"save %s, disabled %s" % [has_save, cont.disabled if cont else "-"])

	print("=== 2. New game ===")
	(_find(current_scene, "Newgame") as Button).emit_signal("pressed")
	var me: Node = null
	for i in range(1200):
		await process_frame
		if current_scene != null and current_scene.name != "TitleScreen":
			me = _find(current_scene, "Player") as CharacterBody3D   # World.tscn's own player
		if me != null:
			break
	_check("the world is up with a local player", me != null and current_scene.name != "TitleScreen",
		str(current_scene.name))
	await _frames(90)   # QualitySettings re-applies within 1 s of a new scene / player

	print("=== 3. presets and floors ===")
	qs.call("set_preset_now", "LOW")
	await _frames(2)
	var sun := _sun()
	var vd: Node = root.get_node_or_null("ViewDistance")   # an AutoLoad
	_check("LOW: the sun's shadows reach 150 m", sun != null and is_equal_approx(sun.directional_shadow_max_distance, 150.0),
		str(sun.directional_shadow_max_distance) if sun else "no sun")
	_check("LOW: render scale 0.67", is_equal_approx(root.scaling_3d_scale, 0.67), str(root.scaling_3d_scale))
	_check("LOW: view distance 300 m", vd == null or is_equal_approx(float(vd.get("street_distance")), 300.0),
		str(vd.get("street_distance")) if vd else "no ViewDistance node")
	qs.call("set_view_distance_now", 100.0)
	qs.call("set_shadow_distance_now", 10.0)
	_check("floors: view 100 -> 250 m, shadows 10 -> 80 m (control: asked below the floor)",
		is_equal_approx(float(qs.call("view_distance_now")), 250.0) and is_equal_approx(float(qs.call("shadow_distance_now")), 80.0),
		"%s / %s" % [qs.call("view_distance_now"), qs.call("shadow_distance_now")])
	_check("  ... a hand value makes the preset Custom", String(qs.call("preset_now")) == "CUSTOM", String(qs.call("preset_now")))
	qs.call("set_preset_now", "HIGH")
	await _frames(2)
	_check("HIGH: shadows 600 m, render scale 1.0", is_equal_approx(_sun().directional_shadow_max_distance, 600.0)
		and is_equal_approx(root.scaling_3d_scale, 1.0), "%s / %s" % [_sun().directional_shadow_max_distance, root.scaling_3d_scale])

	print("=== 4. settings from the pause menu ===")
	var pm := _find(current_scene, "PauseMenu")
	_check("the pause menu has Settings and Quit to title", pm != null and _find(pm, "Settings") is Button
		and _find(pm, "QuitToTitle") is Button)
	pm.call("on_settings_pressed")
	await _frames(3)
	var sm := _find(current_scene, "SettingsMenu")
	_check("Settings opens", sm != null)
	if FileAccess.file_exists(CFG):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(CFG))
	if sm:
		sm.call("close")
	await _frames(3)
	var cf := ConfigFile.new()
	_check("closing it writes settings.cfg", cf.load(CFG) == OK and String(cf.get_value("graphics", "preset", "")) == "HIGH",
		String(cf.get_value("graphics", "preset", "-")))

	print("=== 5. quit to title ===")
	paused = true
	pm.call("on_quit_to_title_pressed")
	await _frames(20)
	_check("back on the title, unpaused", current_scene != null and current_scene.name == "TitleScreen" and not paused,
		"%s paused %s" % [str(current_scene.name) if current_scene else "-", paused])

	if backup != "":
		var f := FileAccess.open(CFG, FileAccess.WRITE)
		f.store_string(backup)
		f.close()
	elif FileAccess.file_exists(CFG):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(CFG))
	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
