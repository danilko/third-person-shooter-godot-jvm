#!/usr/bin/env python3
"""check_lanekit_connectivity.py -- cross-file connectivity check between two already-baked
combined `.lanekit.json` sidecars (see tools/save_lane_kit.py). Answers the general "does this
piece's boundary road actually reach its neighbor's" question, for ANY two pieces of the road
network:

- **District <-> district (the common case).** Most districts border each other with ordinary
  local streets that just continue across the seam -- no highway/overlay involved at all (GTA/
  Forza-style: the district boundary is an invisible authoring seam, not a special road type).
- **District <-> overlay.** A highway/bridge ramp meeting a district's local road -- the overlay
  geometry is hand-sculpted, but its lane spine still goes through the normal
  `export_segment_from_spine_dict`/`export_dict` pipeline, so it shows up in the overlay's own
  `.lanekit.json` exactly like any other lane and this same check applies unchanged.

No new clustering logic needed: `lib/lane_kit.py`'s `combine_pieces` already accepts any
`{'lanes': [...]}`-shaped dict -- a single Blender piece's own `export_*_dict` output and an
already-combined `.lanekit.json` sidecar look identical to it (both are just a flat lane list) --
so this is a thin CLI wrapper, not a new module. Connectivity itself is never enforced by this
tool (or by anything in the pipeline) -- it's geometry-derived at Godot runtime by `LaneGraph`'s
own endpoint-proximity clustering, same as always. This is purely an authoring-time sanity check,
run BEFORE baking either side: catches "the road doesn't actually reach the border" at authoring
time instead of a runtime "car drives into the void" bug at the district seam.

**World offsets are REQUIRED for a meaningful check, not optional polish.** Every district's own
`.lanekit.json` is authored in LOCAL coordinates relative to that one `.blend`'s own origin
(confirmed by reading `WorldZoneManager` directly: a zone's baked geometry is `marker.addChild
(geo)` -- parented under, and positioned entirely by, its `WorldZoneMarker`'s own world
transform; the district's own content never carries a world-space offset itself). Comparing two
districts' raw sidecar points with NO offset applied answers "would these connect if both sat at
world (0,0,0) simultaneously" -- almost never the real question, and can silently produce
misleading `ambiguous`/`paired` results that are pure coordinate coincidence (found directly this
session building a 2-district streaming test: an unshifted check reported garbage). For a stem
that resolves via `lib/piece_registry.py` (i.e. any registered piece, grid or freestanding),
`--offset-a`/`--offset-b` default to that piece's own registered `position` automatically;
anything else (a hand-named test file that was never registered) needs an explicit `x,y,z` on
the command line.

Usage:
    python3 tools/check_lanekit_connectivity.py <a>.lanekit.json <b>.lanekit.json \\
        [--offset-a x,y,z] [--offset-b x,y,z] [--tolerance m]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BP = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(BP, "lib"))
import lane_kit  # noqa: E402
import piece_registry as pr  # noqa: E402


def _stem(path):
    name = os.path.basename(path)
    return name[:-len(".lanekit.json")] if name.endswith(".lanekit.json") else \
        os.path.splitext(name)[0]


def _auto_offset(stem):
    """(x, y, z) world placement for a stem that resolves via `lib/piece_registry.py` -- i.e. its
    registered `position`, the same number every other tool (build_world.py's region markers,
    WorldZoneMarker placement) already treats as that piece's one true world placement -- or None
    if the stem isn't a registered piece (a hand-named test file: caller must pass an explicit
    --offset-* or accept (0,0,0))."""
    piece = pr.piece_by_id(stem)
    if piece is None:
        return None
    x, y, z = piece["position"]
    return (x, y, z)


def _shift(d, offset):
    if offset is None or offset == (0.0, 0.0, 0.0):
        return d
    ox, oy, oz = offset
    out = json.loads(json.dumps(d))   # cheap deep copy -- these sidecars are small JSON
    for lane in out.get("lanes", []):
        lane["points"] = [[p[0] + ox, p[1] + oy, p[2] + oz] for p in lane["points"]]
    return out


def check(path_a, path_b, tolerance=lane_kit.JUNCTION_RADIUS, offset_a=None, offset_b=None):
    with open(path_a) as f:
        dict_a = json.load(f)
    with open(path_b) as f:
        dict_b = json.load(f)
    stem_a, stem_b = _stem(path_a), _stem(path_b)

    if offset_a is None:
        offset_a = _auto_offset(stem_a) or (0.0, 0.0, 0.0)
    if offset_b is None:
        offset_b = _auto_offset(stem_b) or (0.0, 0.0, 0.0)
    dict_a, dict_b = _shift(dict_a, offset_a), _shift(dict_b, offset_b)

    _, reports = lane_kit.combine_pieces(
        [(stem_a, dict_a, stem_a), (stem_b, dict_b, stem_b)], tolerance=tolerance)

    # Only cross-FILE pairings are the actual question here -- a paired cluster entirely within
    # one file's own lanes was already a connection that file's own combiner already knew about
    # (still counted in the printed summary below, just not what "cross" reports).
    cross = [r for r in reports if r["status"] == "paired"
             and any(m.startswith(stem_a + "::") for m in r["members"])
             and any(m.startswith(stem_b + "::") for m in r["members"])]
    return cross, reports, stem_a, stem_b, offset_a, offset_b


def _parse_xyz(s):
    parts = [float(x) for x in s.split(",")]
    if len(parts) != 3:
        raise SystemExit("--offset-* needs exactly 3 comma-separated numbers, got: %r" % s)
    return tuple(parts)


def main():
    argv = sys.argv[1:]
    positional = [a for a in argv if not a.startswith("--")]
    if len(positional) < 2:
        raise SystemExit(__doc__)
    path_a, path_b = positional[0], positional[1]

    def flag(name, default=None):
        for i, a in enumerate(argv):
            if a == "--" + name and i + 1 < len(argv):
                return argv[i + 1]
            if a.startswith("--" + name + "="):
                return a.split("=", 1)[1]
        return default

    tolerance = float(flag("tolerance", lane_kit.JUNCTION_RADIUS))
    offset_a = _parse_xyz(flag("offset-a")) if flag("offset-a") else None
    offset_b = _parse_xyz(flag("offset-b")) if flag("offset-b") else None

    cross, reports, stem_a, stem_b, used_a, used_b = check(
        path_a, path_b, tolerance, offset_a, offset_b)

    print("check_lanekit_connectivity: '%s' at world-offset %s, '%s' at world-offset %s "
          "(tolerance=%.1fm)" % (stem_a, used_a, stem_b, used_b, tolerance))
    print("check_lanekit_connectivity: %d cross-file connection(s)" % len(cross))
    for r in cross:
        print("  [OK] %s at (%.2f, %.2f, %.2f)" % (
            ", ".join(r["members"]), r["position"][0], r["position"][1], r["position"][2]))
    for line in lane_kit.summarize_reports(reports):
        print(line)
    if not cross:
        print("WARNING: no boundary connection found between '%s' and '%s' at these offsets -- "
              "if these two pieces are meant to be drivable neighbors, either their boundary road "
              "endpoints are further than %.1fm apart, or the offsets above are wrong (pass "
              "--offset-a/--offset-b explicitly for anything that isn't a registered piece in "
              "pieces.json)." % (stem_a, stem_b, tolerance))


if __name__ == "__main__":
    main()
