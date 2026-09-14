@tool
extends RefCounted
## The door to the kit's solver (`blender/tools/roadkit_cli.py`, plain python3) and to the headless
## mesh build (`blender/tools/build_roads_piece.sh`). Editor tooling only.

const CLI := "res://blender/tools/roadkit_cli.py"
const BUILD := "res://blender/tools/build_roads_piece.sh"

static func python() -> String:
	return OS.get_environment("ROADKIT_PYTHON") if OS.get_environment("ROADKIT_PYTHON") != "" else "python3"

## Runs one CLI command and returns its JSON object ({"failed": true, "error": ...} on any failure).
static func run(cmd: String, record_path: String, extra: Array = []) -> Dictionary:
	var args := [ProjectSettings.globalize_path(CLI), cmd, ProjectSettings.globalize_path(record_path)]
	args.append_array(extra)
	var out := []
	var code := OS.execute(python(), args, out, true)
	var text := "".join(out)
	var parsed = JSON.parse_string(text.strip_edges().split("\n")[-1] if text.strip_edges() != "" else "")
	if typeof(parsed) != TYPE_DICTIONARY:
		return {"failed": true, "error": "roadkit_cli %s exited %d: %s" % [cmd, code, text.substr(0, 400)]}
	return parsed

## The whole build (lanes, meshes, bake). Blocking — call it from a Thread.
static func build_piece(record_path: String, piece: String) -> Dictionary:
	var out := []
	var code := OS.execute("bash", [ProjectSettings.globalize_path(BUILD), ProjectSettings.globalize_path(record_path), piece], out, true)
	return {"ok": code == 0, "log": "".join(out)}
