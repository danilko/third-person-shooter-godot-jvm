extends SceneTree
## Every weapon scene names its OWN sounds, and every one of them loads.
##   godot --headless --path . --script res://tools/godot/probe_weapon_audio.gd
## Firearms carry fire + reload, melee weapons a swing (fire_audio), all from assets/audio/weapons/ (built by
## tools/audio/build_weapon_sfx.py). A missing or shared stream is silent or wrong in game with no error.

const DIR := "res://src/main/resources/com/openworld/weapon/"
const FIREARMS := ["PIS1", "PIS2", "DUP1", "REV1", "SMG1", "ASR1", "ASR2", "SHG1", "SNR1"]
const MELEE := ["MEW1", "MEW2", "MEW3", "MEW4", "MEW5", "MEW6", "MEW7", "BAT1", "Fist"]

var fails := 0
var checks := 0

func _check(ok: bool, msg: String) -> void:
	checks += 1
	if not ok:
		fails += 1
	print(("PASS " if ok else "FAIL ") + msg)

func _stream_path(w: Node, prop: String) -> String:
	var s = w.get(prop)
	if s == null or not (s is AudioStream):
		return ""
	return s.resource_path

func _initialize() -> void:
	var seen := {}
	for id in FIREARMS + MELEE:
		var w := (load(DIR + id + ".tscn") as PackedScene).instantiate()
		var fire := _stream_path(w, "fire_audio")
		var want := "res://assets/audio/weapons/%s_%s.wav" % [id, "swing" if id in MELEE else "fire"]
		_check(fire == want, "%s fire_audio = %s" % [id, fire if fire != "" else "<none>"])
		if id in FIREARMS:
			var rel := _stream_path(w, "reload_audio")
			_check(rel == "res://assets/audio/weapons/%s_reload.wav" % id, "%s reload_audio = %s" % [id, rel if rel != "" else "<none>"])
			_check(not seen.has(fire), "%s has a fire sound no other weapon uses" % id)
			seen[fire] = true
		var s = w.get("fire_audio")
		_check(s != null and s.get_length() > 0.1, "%s fire stream decodes (%.2f s)" % [id, s.get_length() if s else 0.0])
		w.free()
	var hm := load("res://assets/audio/hit_marker.wav") as AudioStream
	_check(hm != null, "hit_marker.wav loads (Sounds.HIT_MARKER)")
	print("RESULT %s (%d checks, %d failures)" % ["PASS" if fails == 0 else "FAIL", checks, fails])
	quit(1 if fails else 0)
