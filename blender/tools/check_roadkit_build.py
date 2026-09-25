#!/usr/bin/env python3
"""check_roadkit_build.py -- the road build without Blender, gated (PLAN.md 3.1 B11).

    python3 blender/tools/check_roadkit_build.py

Two questions, each answered by building again into a temp dir with `roadkit_cli.py gltf`:

  1. ARE THE COMMITTED PIECES THE BUILD OF THEIR RECORDS? DebugRoads (both zones, over its ground sidecar) and
     RoadKitZones (the sample network, both zones) are rebuilt and compared with the committed `.gltf` by
     `roadkit_mesh_parity.py --built --assert` -- every object, material and collision proxy, and the road surface
     under every lane. A piece left stale after a record change, or a builder that stopped being deterministic,
     fails here. (Before B11 this step compared the Python sweep with the Blender build; the Blender build is gone,
     and the measured parity it left behind is recorded in CLAUDE.md "B11".)
  2. DO STYLES AND PROFILE ASSETS BUILD? `RoadKitStyled.roads.json` is the sample network with material slots and
     profile assets on four roads and one deliberately MISSING material name. Asserted: the missing name is
     reported and nothing else is; each named material is on the object it styles; each asset's layer is its
     section swept -- two triangles per section segment per carrier span, in the asset's own material, standing
     as tall as the section; no vertex normal is inverted or further than the smoothing angle from its face.
     PIER ASSETS (PLAN.md 3.5): demo_hwy stands the hammerhead at every column (a whole number of the pier's
     triangles, in its own material, the full column height), demo_ramp_b's 16 m portal is reported as reaching
     past its 7 m deck, and demo_spur's missing pier name is reported.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PIECES = os.path.join(REPO, "assets", "world_source", "pieces")
RES = os.path.join(REPO, "src", "main", "resources", "com", "openworld", "world", "pieces")
sys.path[:0] = [HERE, os.path.join(os.path.dirname(HERE), "lib"), os.path.join(os.path.dirname(HERE), "addons", "road_kit_authoring")]
import gltf_tris                                   # noqa: E402
import point_kit as pk                             # noqa: E402
import point_gltf as pgl                           # noqa: E402

fails = []


def check(ok, what, detail=""):
    print("  %s  %-72s %s" % ("PASS" if ok else "FAIL", what, detail))
    if not ok:
        fails.append(what)


def cli(*args):
    out = subprocess.run([sys.executable, os.path.join(HERE, "roadkit_cli.py")] + list(args),
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def committed(record, zones, prefix, ground, tmp):
    d = cli("gltf", record, zones, tmp, prefix, "--ground", ground, "--gated")
    built = [p["gltf"] for p in d["pieces"]]
    refs = [os.path.join(RES, p["piece"] + ".gltf") for p in d["pieces"]]
    missing = [r for r in refs if not os.path.exists(r)]
    check(not missing, "%s: every piece is committed" % prefix, ", ".join(missing))
    if missing:
        return
    args = [sys.executable, os.path.join(HERE, "roadkit_mesh_parity.py"), record] + refs + ["--built"] + built + ["--assert"]
    r = subprocess.run(args, capture_output=True, text=True)
    bad = [l for l in r.stdout.splitlines() if l.startswith("PARITY FAIL")]
    check(r.returncode == 0, "%s: the committed pieces are the build of the record" % prefix, "; ".join(bad[:3]))


def styled(tmp):
    record = os.path.join(PIECES, "RoadKitStyled.roads.json")
    d = cli("gltf", record, "", tmp, "RoadKitStyled")
    check(d.get("written") and len(d["pieces"]) == 1, "RoadKitStyled builds")
    check([tuple(m) for m in d["missing_style"]] == [("demo_cross", "footway", "material", "M_DoesNotExist"),
                                                     ("demo_spur", "pillar", "asset", "RKA_PIER_DoesNotExist")],
          "exactly the missing material and pier names are reported", str(d["missing_style"]))
    over = [tuple(m) for m in d.get("pier_overhang", [])]
    check([m[:2] for m in over] == [("demo_ramp_b", "RKA_PIER_portal")] and abs(over[0][2] - 4.5) < 0.05,
          "only the portal on the 7 m ramp deck is reported as overhanging (4.5 m)", str(over))
    piece = d["pieces"][0]
    check(piece["inverted_normals"] == 0 and piece["worst_normal_deg"] <= pgl.SMOOTH_ANGLE_DEG + 1e-6,
          "no normal inverted, none past the smoothing angle",
          "%d inverted, worst %.2f deg" % (piece["inverted_normals"], piece["worst_normal_deg"]))
    objs = gltf_tris.load(piece["gltf"])
    for obj, mat in (("demo_main_0__surface", "M_Brick"), ("demo_main_0__surface", "M_Leaf"),
                     ("demo_main_0__marks_w", "M_Neon"), ("demo_hwy__surface", "M_Steel"),
                     ("demo_hwy__edges_left_0", "M_Red"), ("demo_cross_0__marks_y", "M_Accent"),
                     ("demo_ramp__surface", "M_Dirt"), ("demo_cross_0__edges_left_0", __import__("point_kit").DEFAULT_MATERIAL["footway"])):  # a missing footway_mat falls back to the default
        check(mat in objs.get(obj, {}), "%s wears %s" % (obj, mat), str(sorted(objs.get(obj, {}))))
    kit = pk.load()
    pier = kit.pier("RKA_PIER_hammerhead")
    per = sum(len(ts) for ts in pier["tris"].values())
    cols = objs.get("demo_hwy__surface", {}).get("M_Concrete", [])
    zs = [p[1] for t in cols for p in t]                                     # glTF is Y-up
    check(cols and len(cols) % per == 0 and len(cols) // per >= 10,
          "demo_hwy__surface stands the hammerhead pier (%d tris, %d per pier)" % (len(cols), per))
    check(zs and max(zs) - min(zs) >= 12.4 - 1e-3, "the hammerhead reaches from the soffit to the ground",
          "%.2f m" % ((max(zs) - min(zs)) if zs else 0.0))
    for obj, asset in (("demo_main_0__edges_left_0", "RKA_PROFILE_kerb_granite"),
                       ("demo_hwy__edges_left_0", "RKA_PROFILE_wall_jersey"),
                       ("demo_ramp__edges_left_0", "RKA_PROFILE_wall_parapet"),
                       ("demo_main_0__edges_left_0", "RKA_PROFILE_footway_slab")):
        prof = kit.profile(asset)
        tris = objs.get(obj, {}).get(prof["material"], [])
        segs = sum(len(sp["points"]) - 1 for sp in prof["splines"])
        ys = [p[1] for p in prof["splines"][0]["points"]]
        height = max(ys) - min(ys)
        # A kerb and a footway slab share a material with nothing else on the run; a wall shares M_Barrier with
        # nothing, so the triangle count is a whole number of sweeps of this section.
        whole = tris and len(tris) % (2 * segs) == 0
        tall = max((max(p[1] for p in t) for t in tris), default=0) - min((min(p[1] for p in t) for t in tris), default=0)
        check(whole, "%s is %s swept (%d tris, %d per span)" % (obj, asset, len(tris), 2 * segs))
        check(tall >= height - 1e-3, "%s stands at least as tall as the section" % obj, "%.3f m vs %.3f m" % (tall, height))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        committed(os.path.join(PIECES, "DebugRoads.roads.json"), os.path.join(PIECES, "DebugRoads.zones.json"),
                  "Roads_DebugRoads", os.path.join(PIECES, "DebugRoads.ground.json"), os.path.join(tmp, "debug"))
        committed(os.path.join(PIECES, "RoadKitSample.roads.json"), os.path.join(PIECES, "RoadKitSample.zones.json"),
                  "Roads_RoadKitZones", "", os.path.join(tmp, "zones"))
        styled(os.path.join(tmp, "styled"))
    print("RESULT: %s (%d failures)" % ("PASS" if not fails else "FAIL", len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
