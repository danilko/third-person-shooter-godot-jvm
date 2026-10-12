extends SceneTree
## The sign string table (user, 2026-10-12): names by id, one column per language, read at run time.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_sign_text.gd
##
## `src/main/resources/com/openworld/i18n/signs.csv` is read by world.SignText and every column is registered with
## Godot's TranslationServer. Asserted, through the engine's own API (so `tr()` would say the same):
##   1. the table's languages are loaded as locales (ja, zh_TW, en) with a row for every street of the lanekits;
##   2. one id reads differently per language: `street.nishi_dori` is 西通り / 西通 / Nishi-dori, and no zh_TW cell
##      carries kana;
##   3. the sign-language setting switches (QualitySettings.set_sign_language_now) and refuses an unknown column
##      (it stays on the source language);
##   4. both sign fonts hold every character of their column (a name the font cannot draw is a box on a sign).

const TABLE := "res://src/main/resources/com/openworld/i18n/signs.csv"
const FONTS := {"ja": "res://src/main/resources/com/openworld/ui/fonts/NotoSansJP-Signs.otf",
		"zh_TW": "res://src/main/resources/com/openworld/ui/fonts/NotoSansTC-Signs.otf"}

var fails := 0

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _initialize() -> void:
	for i in 5:
		await process_frame
	var q: Node = root.get_node_or_null("QualitySettings")
	if q == null:
		print("RESULT: FAIL (no QualitySettings autoload)")
		quit(1)
		return
	q.call("set_sign_language_now", "zh_TW")
	_check(str(q.call("sign_language_now")) == "zh_TW", "the sign language switches to zh_TW (%s)" % q.call("sign_language_now"))
	var locales := TranslationServer.get_loaded_locales()
	_check("ja" in locales and "zh_TW" in locales and "en" in locales, "ja, zh_TW and en are registered locales (%s)" % [locales])
	var ja := TranslationServer.get_translation_object("ja")
	var zh := TranslationServer.get_translation_object("zh_TW")
	var en := TranslationServer.get_translation_object("en")
	if ja == null or zh == null or en == null:
		print("RESULT: FAIL (a translation object is missing)")
		quit(1)
		return
	var key := "street.nishi_dori"
	print("  %s: ja %s | zh_TW %s | en %s" % [key, ja.get_message(key), zh.get_message(key), en.get_message(key)])
	_check(str(ja.get_message(key)) == "西通り" and str(zh.get_message(key)) == "西通" and str(en.get_message(key)) == "Nishi St",
			"one id, three languages")
	# every street of the built lanekits has a row
	var bases := {}
	for f in DirAccess.get_files_at("res://assets/world_source/pieces"):
		if f.begins_with("Roads_IslandRoads_island_") and f.ends_with(".lanekit.json"):
			var doc = JSON.parse_string(FileAccess.get_file_as_string("res://assets/world_source/pieces/" + f))
			for l in doc["lanes"]:
				if l.has("road_name"):
					bases[str(l["road_name"]).split("__")[0]] = true
	var missing := []
	for b in bases:
		if str(ja.get_message("street." + b)) == "":
			missing.append(b)
	_check(bases.size() > 50 and missing.is_empty(), "every one of the %d island streets has a row (missing %s)" % [bases.size(), missing.slice(0, 5)])
	# no kana in zh_TW; both fonts cover their column
	var kana := RegEx.new()
	kana.compile("[\\x{3040}-\\x{30FF}]")
	var bad := []
	for m in zh.get_message_list():
		if kana.search(str(zh.get_message(m))) != null:
			bad.append(m)
	_check(bad.is_empty(), "no zh_TW cell carries kana (%s)" % [bad.slice(0, 5)])
	for lang in FONTS:
		var font: FontFile = load(FONTS[lang])
		var tr := TranslationServer.get_translation_object(lang)
		var lost := {}
		for m in tr.get_message_list():
			var text := str(tr.get_message(m))
			for i in text.length():
				var c := text.unicode_at(i)
				if c > 32 and c != 123 and c != 125 and not font.has_char(c):
					lost[text[i]] = true
		_check(font != null and lost.is_empty(), "the %s sign font draws every character of its column (missing %s)" % [lang, lost.keys().slice(0, 12)])
	q.call("set_sign_language_now", "klingon")
	_check(str(q.call("sign_language_now")) == "ja", "an unknown column keeps the source language (%s)" % q.call("sign_language_now"))
	print("RESULT: %s (%d fail)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
