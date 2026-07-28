#!/usr/bin/env python3
"""save_lane_kit.py -- combine every road_kit_authoring piece in the open .blend (a district OR
the future arterial overlay -- same mechanism, just a different file/stem) into ONE combined
git-diffable sidecar `<stem>.lanekit.json`, replacing `tools/save_roads.py`/`gen_roads_only.py`'s
role for the OLD `road_graph.py` pipeline (see road_blender_godot.md Phase 6 for the full
replacement plan). `WorldBaker`'s sidecar loader consumes this file exactly as it already
consumes a single piece's own `export_*_json` output -- no Java changes needed.

Authoring loop:
  1. Build/edit intersections/segments/transitions with the road_kit_authoring addon as usual (no
     export_path needed on the individual build operators -- this tool supersedes per-piece export).
  2. Run:  blender <district_or_overlay>.blend --background --python tools/save_lane_kit.py
  3. Rebuild (tools/build_piece.sh <name> / tools/build_overlay.sh <name>) -- P6.6 wires
     `lanekit_path` in automatically once `<stem>.lanekit.json` exists next to the .blend.

Every piece collection in the file (`road_kit_authoring.ops_intersection._is_piece_collection`)
is rebuilt into its `export_*_dict` form straight from its own `rka_*` custom properties -- the
same permanent build-settings record `custom_props.write_build_settings` already writes at
build/rebuild time, so this tool needs no separate "did you remember to set an export path"
step per piece. Piece-type dispatch mirrors `ops_intersection._rebuild_piece_in_place`'s exact
check order (transition's `rka_lanes_a` MUST be checked before the GN-segment `rka_curve_object`
check, since a transition also carries `rka_curve_object`).

Every lane/arm id is namespaced `<piece>__<id>` and tagged `zone_id` (`lib/lane_kit.py`'s
`combine_pieces`) -- the property-based replacement for the old `<stem>__` name-prefix convention
`WorldZoneManager.findRoute` used to rely on. `zone_id` defaults to this file's own stem, override
per-piece via a manually-added `rka_zone_id` custom property on that piece's collection (same
"hand-edit via the Custom Properties panel" convention `rka_lane_map` overrides already use).

Connectivity between pieces (and eventually between an overlay and its neighboring districts) is
never asserted by this tool -- it's geometry-derived at Godot runtime by `LaneGraph`'s own
endpoint-proximity clustering, same as always. What this tool DOES check, via `lane_kit.py`'s
authoring-time equivalent of that same clustering: whether two pieces' lane endpoints land close
enough to plausibly be an intended connection, and flags anything that isn't a clean 1:1 pairing
(`isolated` = dangling end, informational; `ambiguous` = 3+ candidates, needs manual review) --
printed to stdout, never fatal (a `.lanekit.json` is still written either way; use your judgement,
or route it through `ops_connect.py`'s review UI once that exists).
"""
import bpy, json, os, sys

BP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # assets/world_source
sys.path.insert(0, os.path.join(BP, "lib"))
sys.path.insert(0, os.path.join(BP, "addons"))
import lane_kit                                    # noqa: E402
import road_kit_authoring as rka                    # noqa: E402
from road_kit_authoring import custom_props          # noqa: E402
from road_kit_authoring import ops_intersection as opint  # noqa: E402
from road_kit_authoring import ops_segment as opseg  # noqa: E402

_ik = None


def ik():
    global _ik
    if _ik is None:
        import intersection_kit as _mod
        _ik = _mod
    return _ik


def _lane_surface_z():
    return bpy.context.scene.rka.lane_surface_z


def _export_intersection(coll):
    k = ik()
    arms = custom_props.read_arms_full(coll, k.Arm)
    origin = custom_props.read_origin(coll)
    if arms is None or origin is None or len(arms) < 3:
        return None
    kerb_radius = coll.get("rka_kerb_radius", 9.0)
    tail_length = coll.get("rka_tail_length", 12.0)
    segments = coll.get("rka_segments", 8)
    lane_map = custom_props.read_lane_map_override(coll)
    z = origin[2] + _lane_surface_z()
    # Same z-lift AND world-center translation `intersection_kit.export_json` applies -- done by
    # hand here so this tool can call the dict-only `export_dict` directly instead of round-
    # tripping through a temp file. `center=(origin[0], origin[1])` is REQUIRED, not optional --
    # export_dict's own geometry is junction-LOCAL (see its docstring); omitting this silently
    # exported every off-origin intersection at the wrong world position (found this session).
    d = k.export_dict(arms, kerb_radius, junction_id=coll.name, segments=segments,
                       tail_length=tail_length, lane_map=lane_map, center=(origin[0], origin[1]))
    for lane in d["lanes"]:
        lane["points"] = [[p[0], z, -p[1]] for p in lane["points"]]
    for port in d["ports"]:
        port["position"] = [port["position"][0], z, -port["position"][1]]
    return d


def _export_gn_segment(coll):
    spine_name = coll.get("rka_curve_object")
    if not spine_name:
        return None
    spine_obj = opint.local_object(spine_name)
    if spine_obj is None or spine_obj.type != 'CURVE':
        return None
    # Raw control points, NOT the GN-evaluated pavement-sweep mesh -- see
    # `ops_segment._spine_control_points`'s own docstring for why `to_mesh()` would be wrong here.
    spine = opseg._spine_control_points(spine_obj)
    if len(spine) < 2:
        return None
    lane_width = coll.get("rka_lane_width", 5.0)
    lanes = coll.get("rka_lanes", 1)
    lanes_backward = coll.get("rka_lanes_backward", lanes)
    traffic_side = coll.get("rka_traffic_side", "LEFT")
    return ik().export_segment_from_spine_dict(
        spine, lane_width=lane_width, lanes=lanes, lanes_backward=lanes_backward,
        segment_id=coll.name, traffic_side=traffic_side)


def _export_transition(coll):
    spine_name = coll.get("rka_curve_object")
    if not spine_name:
        return None
    spine_obj = opint.local_object(spine_name)
    if spine_obj is None or spine_obj.type != 'CURVE':
        return None
    spine = opseg._spine_control_points(spine_obj)
    if len(spine) < 2:
        return None
    p0, p1 = spine[0], spine[-1]
    lane_width = coll.get("rka_lane_width", 5.0)
    lanes_a = coll.get("rka_lanes_a", 2)
    lanes_b = coll.get("rka_lanes_b", 1)
    lanes_backward_a = coll.get("rka_lanes_backward_a", 0) or None
    lanes_backward_b = coll.get("rka_lanes_backward_b", 0) or None
    align = coll.get("rka_align", 'right')
    traffic_side = coll.get("rka_traffic_side", "LEFT")
    return ik().export_lane_transition_dict(
        p0, p1, lane_width=lane_width, lanes_a=lanes_a, lanes_b=lanes_b,
        lanes_backward_a=lanes_backward_a, lanes_backward_b=lanes_backward_b, align=align,
        segment_id=coll.name, traffic_side=traffic_side)


def _export_point_segment(coll):
    if "rka_p0" not in coll.keys() or "rka_p1" not in coll.keys():
        return None
    p0_raw, p1_raw = coll["rka_p0"], coll["rka_p1"]
    lane_width = coll.get("rka_lane_width", 5.0)
    lanes = coll.get("rka_lanes", 1)
    lanes_backward = coll.get("rka_lanes_backward", lanes)
    bend = coll.get("rka_bend", 0.0)
    bend_z = coll.get("rka_bend_z", 0.0)
    curve_segments = coll.get("rka_curve_segments", 8)
    traffic_side = coll.get("rka_traffic_side", "LEFT")
    z = float(p0_raw[2]) + _lane_surface_z()
    return ik().export_segment_dict(
        (p0_raw[0], p0_raw[1]), (p1_raw[0], p1_raw[1]), lane_width=lane_width, lanes=lanes,
        segment_id=coll.name, z=z, bend=bend, segments=curve_segments, z0=0.0,
        z1=float(p1_raw[2]) - float(p0_raw[2]), bend_z=bend_z, lanes_backward=lanes_backward,
        traffic_side=traffic_side)


def export_piece_dict(coll):
    """Dispatch mirrors `ops_intersection._rebuild_piece_in_place`'s own check order exactly --
    keep the two in sync if either changes."""
    if "rka_arm_names" in coll.keys():
        return _export_intersection(coll)
    elif "rka_lanes_a" in coll.keys():
        return _export_transition(coll)
    elif "rka_curve_object" in coll.keys():
        return _export_gn_segment(coll)
    else:
        return _export_point_segment(coll)


def collect_pieces(stem):
    pieces = []
    colls = sorted((c for c in bpy.data.collections
                     if c.library is None and opint._is_piece_collection(c)),
                    key=lambda c: c.name)
    for coll in colls:
        d = export_piece_dict(coll)
        if d is None:
            print("  skipping %s: could not reconstruct build params from its rka_* properties"
                  % coll.name)
            continue
        zone_id = coll.get("rka_zone_id", stem)
        pieces.append((coll.name, d, zone_id))
    return pieces


def main():
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()
    blend = bpy.data.filepath
    if not blend:
        raise SystemExit("save_lane_kit.py: open a district/overlay .blend first")
    stem = os.path.splitext(os.path.basename(blend))[0]
    out_path = os.path.join(os.path.dirname(blend), stem + ".lanekit.json")

    pieces = collect_pieces(stem)
    if not pieces:
        raise SystemExit("save_lane_kit.py: no road_kit_authoring pieces found in %s.blend" % stem)

    combined, reports = lane_kit.combine_pieces(pieces)
    for line in lane_kit.summarize_reports(reports):
        print(line)
    with open(out_path, "w") as f:
        json.dump(combined, f, indent=1)
    print("save_lane_kit: wrote %d lane(s) from %d piece(s) -> %s"
          % (len(combined["lanes"]), len(pieces), out_path))


if __name__ == "__main__":
    main()
