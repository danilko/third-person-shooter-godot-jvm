@tool
extends RefCounted
## The door to the kit's solver (`blender/tools/roadkit_cli.py`, plain python3) and to the headless
## mesh build (`blender/tools/build_roads_piece.sh`). Editor tooling only.

const Gestures := preload("res://addons/road_kit/road_kit_gestures.gd")
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

## The whole build (lanes, meshes, bake). Blocking — call it from a Thread. With a zones sidecar
## (`road_kit_zones.gd`) `piece` is a prefix and the network is cut into one piece per zone.
## With a ground sidecar (`road_kit_ground.gd`, B6b) the supports stand on the sampled Terrain3D.
static func build_piece(record_path: String, piece: String, zones_path: String = "", ground_path: String = "") -> Dictionary:
	var out := []
	var args := [ProjectSettings.globalize_path(BUILD), ProjectSettings.globalize_path(record_path), piece]
	args.append(ProjectSettings.globalize_path(zones_path) if zones_path != "" else "")
	if ground_path != "":
		args.append(ProjectSettings.globalize_path(ground_path))
	var code := OS.execute("bash", args, out, true)
	return {"ok": code == 0, "log": "".join(out)}

## B8: a gesture the SOLVER owns, applied to the record -- save (which promotes any hand-rotated point
## first), run `cmd`, reload the network from the rewritten record and face the points the tool owns.
## The caller wraps it in an undo step. Returns the CLI's object (`failed`/`error` on a refusal).
static func record_gesture(net: Node, cmd: String, args: Array = []) -> Dictionary:
	if net.save_record() != OK:
		return {"failed": true, "error": "could not save " + str(net.record_path)}
	var r := run(cmd, net.record_path, args)
	if r.get("failed", false):
		return r
	net.load_record(net.record_path)
	face_network(net)
	return r

## Face every AUTO point along its road (`roadkit_cli.py facings`), promoting rotated ones first.
static func face_network(net: Node) -> Dictionary:
	var f := run("facings", net.record_path)
	if f.get("failed", false):
		return {"ok": false, "message": str(f.get("error", ""))}
	return Gestures.apply_facings(net, f["facings"])
