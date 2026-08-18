#!/usr/bin/env python3
"""
island_v3_assemble.py -> assets/world_source/island_v3_full.blend

Bring LAND + ROADS + BUILDINGS into ONE blend so the fit can actually be looked at and measured,
instead of three files that each look fine on their own.

Two jobs, and the second is the one that earns the script:

1. ASSEMBLE — library-link the three sources as collection instances at the origin. They already
   share one coordinate frame (game metres, centre origin), so nothing is transformed. Linked,
   not appended, so re-running any upstream builder shows up here on reload and this file can
   never corrupt a source.

2. FIT REPORT — check the three layers against each other and say where they disagree. The
   checks run on the PLAN DATA (centrelines, lot positions), not on mesh intersections: it is
   both far faster and far more useful, because a mesh overlap tells you two triangles touch
   while the data tells you *a building is standing in the roadway*.

   * buildings standing inside a road corridor (half width + setback)
   * buildings, roads and building blocks off land / in water
   * road surfaces that sit at a height where they would fight the terrain

Sources are whatever the other three tools last wrote:
    assets/world_source/island_v3.blend            (build_island_v3.py)
    assets/world_source/island_v3_roads.blend      (island_v3_to_roadkit.py)
    assets/world_source/island_v3_buildings.blend  (island_v3_buildings.py)

RUN:
  blender --background --python blender/tools/island_v3_assemble.py
  blender --background --python blender/tools/island_v3_assemble.py -- --report-only
"""
import bpy, os, sys, math, random

BLENDER_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO        = os.path.dirname(BLENDER_SRC)
ROOT        = os.path.join(REPO, "assets", "world_source")
sys.path.insert(0, os.path.join(BLENDER_SRC, "lib"))
sys.path.insert(0, os.path.join(REPO, "tools"))

import kit_common as kc
import island_v3_geom as G
import island_v3_plan as P

SOURCES = [
    ("island_v3.blend", ["SEA", "LAND", "WATER", "TERRAIN", "CASTLE", "BRIDGES", "PLANNING",
                         "PARCELS", "MARKERS", "GRID"]),
    # RK_GROUND is deliberately NOT linked: it is the flat proxy the road builder
    # raycasts against for support derivation, not terrain. Linking it drops an opaque
    # plane over the whole island and hides the real land underneath.
    ("island_v3_roads.blend", ["RK_CURVES", "RK_CROSSINGS", "RK_SPLITS"]),
    ("island_v3_buildings.blend", ["BLD_neonA", "BLD_neonB", "BLD_neonC", "BLD_resid",
                                   "BLD_port", "BLD_air"]),
]

# Road corridor half-widths for the clearance test, by tier — pavement plus sidewalk, i.e. the
# width a building genuinely must not stand in.
CORRIDOR = {"T1": 11.0, "T2": 17.5, "T3": 10.5, "RAMP": 6.0, "TOUGE": 4.0}


def assemble():
    linked = 0
    for fname, colls in SOURCES:
        path = os.path.join(ROOT, fname)
        if not os.path.exists(path):
            print("  MISSING: %s — run its builder first; skipping" % fname)
            continue
        got = kc.link_collections(path, colls)
        dest = kc.get_coll(os.path.splitext(fname)[0].upper())
        for c in got:
            kc.instance_collection(dest, "%s__%s" % (os.path.splitext(fname)[0], c.name),
                                   c, (0.0, 0.0, 0.0))
            linked += 1
    return linked


# ------------------------------------------------------------------------------- fit checks
# Corridors, nearest-road and the corridor test all live in island_v3_plan now — the
# BUILDING GENERATOR uses the same functions to decide what to skip, so the report and
# the thing it reports on can never drift apart. Duplicating them here is exactly how a
# check starts passing while the world stays broken.


def buildings_from_plan():
    """Regenerate the building lot positions from the same seeds island_v3_buildings.py uses, so
    the fit check measures what that tool actually placed without having to open its blend."""
    out = []
    for zi, (zname, rects, *_rest) in enumerate(G.ZONES):
        if zname == "farm":
            continue
        for ri, rect in enumerate(rects):
            cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
            _q, spec = P.block_spec_at(cx, cy, zname)
            if spec is None:
                continue
            for bi, cell in enumerate(P.block_cells(rect, spec, seed=zi * 17 + ri)):
                bx, by = (cell[0] + cell[2]) / 2, (cell[1] + cell[3]) / 2
                q, qspec = P.block_spec_at(bx, by, zname)
                if qspec is None:
                    continue
                for si, sub in enumerate(P.subdivide(cell, qspec["alley"])):
                    for (x, y, _brg, f, d) in P.lots(sub, qspec, seed=bi * 31 + si):
                        if P.in_road_corridor(x, y, max(f, d)):
                            continue        # the generator skips these too — same function
                        out.append((x, y, f, d, q, zname))
    return out


def fit_report():
    corridors = P.road_corridors()
    blds = buildings_from_plan()

    in_road, off_land, worst = [], [], []
    for (x, y, f, d, q, zname) in blds:
        if not G.on_land(x, y):
            off_land.append((x, y, zname))
            continue
        dist, who, tier = P.nearest_road(x, y)
        need = P.CORRIDOR.get(tier, 12.0) + max(f, d) / 2.0
        if dist < need:
            in_road.append((x, y, zname, who, dist, need))
    in_road.sort(key=lambda r: r[4])

    road_off = []
    for nm, tier, pts in corridors:
        bad = sum(1 for (x, y) in pts if not G.on_land(x, y))
        if bad:
            road_off.append((nm, bad, len(pts)))

    print("FIT REPORT  (%d buildings, %d roads)" % (len(blds), len(corridors)))
    print("  buildings standing in a road corridor : %d  (%.1f%%)"
          % (len(in_road), 100.0 * len(in_road) / max(1, len(blds))))
    for (x, y, zname, who, dist, need) in in_road[:8]:
        print("      %-7s at (%7.1f,%7.1f)  %5.1f m from %-14s (needs %.1f m)"
              % (zname, x, y, dist, who, need))
    if len(in_road) > 8:
        print("      ... and %d more" % (len(in_road) - 8))
    print("  buildings off land / in water          : %d" % len(off_land))
    print("  roads with points off land             : %d" % len(road_off))
    for (nm, bad, tot) in road_off[:8]:
        print("      %-14s %d of %d points over water or void" % (nm, bad, tot))
    print("  road surface lift above terrain        : %.2f m  (curb is %.2f m — a lift larger "
          "than the curb inverts the cross-section)" % (P.ROAD_LIFT, 0.15))
    return len(in_road), len(off_land), len(road_off)


def parse_args():
    import argparse
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="island_v3_assemble.py")
    ap.add_argument("--report-only", action="store_true",
                    help="run the fit checks without linking or writing a blend")
    ap.add_argument("--out", default="island_v3_full.blend")
    return ap.parse_args(argv)


def main():
    opts = parse_args()
    if opts.report_only:
        fit_report()
        return
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    n = assemble()
    a, b, c = fit_report()
    print("ASSEMBLE: %d linked collection instance(s) -> %s" % (n, opts.out))
    if a or b or c:
        print("  (the fit issues above are DATA, not blockers — fix them by moving a zone rect "
              "or easing a road, then re-run the two builders)")
    if bpy.app.background:
        kc.save_blend(ROOT, opts.out)


if __name__ == "__main__":
    main()
