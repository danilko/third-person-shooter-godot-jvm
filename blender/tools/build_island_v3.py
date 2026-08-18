#!/usr/bin/env python3
"""
build_island_v3.py -> assets/world_source/island_v3.blend

The OVERALL 2D MAP for Tokyo-Bay Island v3, built in Blender at true game scale
(2016 x 2016 m, centre origin, X east / Y north) from two pure-Python sources:

    tools/island_v3_geom.py   — the SHAPE of the island (coast, water, terrain, centrelines)
    tools/island_v3_plan.py   — the PLANNING RULES (block gradient, ramps, parcels, support)

This is a **layout source**, in exactly the sense BLENDER_CONVENTIONS.md means it: a
traceable, true-scale plan you author road_kit_authoring pieces ON TOP OF. It is not the
shipped world and it is not baked — nothing here is meant to survive into Godot untouched.

WHY FLAT BY DEFAULT: the ground is drawn as a flat 2D plan so it reads as a map and so a
piece dropped on it lands predictably. The ELEVATED network (expressway deck, ramps, rail
viaduct, bridges) is always placed at its TRUE Z, because the whole point of §6 below is
that what goes underneath a surface is derived from how high that surface sits. Pass
`--relief` to step the terrain bands to their real elevations as well.

SUPPORT (§6 of tokyo-bay-island-v3-cityplanning.md) is the idea worth reading the file for:
there is no separate "highway builder" and "ground road builder". Every surface is drawn the
same way, and `island_v3_plan.support_kind(surface_z, ground_z)` decides — per sample, from
one number — whether it gets nothing, an embankment, or a pier line. Change a height and the
understructure changes with it. This script bakes that decision once for the layout preview;
the live authoring version of the same rule belongs in Geometry Nodes so it re-evaluates
while a height is dragged (see the addon work in the companion doc).

RUN:
  blender --background --python blender/tools/build_island_v3.py
  blender --background --python blender/tools/build_island_v3.py -- --relief --streets --parcels
  blender --background assets/world_source/island_v3.blend --python blender/tools/render.py -- _island 0 0 2600
"""
import bpy, os, sys, math

BLENDER_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))    # blender/
REPO        = os.path.dirname(BLENDER_SRC)
ROOT        = os.path.join(REPO, "assets", "world_source")
sys.path.insert(0, os.path.join(BLENDER_SRC, "lib"))
sys.path.insert(0, os.path.join(REPO, "tools"))

import kit_common as kc
import assemble as asm
import island_v3_geom as G
import island_v3_plan as P


# --------------------------------------------------------------------------- layers
# Z bands, chosen only so coincident flat plates never z-fight. They carry no meaning
# beyond draw order — the REAL heights in this file are P.DECK_Z / P.RAIL_Z / terrain.
Z_SEA, Z_LAND, Z_WATER, Z_ZONE = -0.60, 0.00, 0.05, 0.12
Z_BLOCK, Z_T3, Z_T2, Z_MARK = 0.18, 0.22, 0.30, 0.40

HALF = {"T1": 11.0, "T2": 13.5, "T3": 7.0, "T4": 2.25, "RAIL": 5.0, "RAMP": 4.5}


# ------------------------------------------------------------------------- ground fn
def make_ground_fn(relief):
    """Terrain height under any XY — the OTHER half of the support rule. Flat mode still
    returns real values for the reclaimed surfaces (harbour +2, airport island +4), because
    those genuinely are at a different level and the bridge/ramp geometry depends on it."""
    bands = []
    if relief:
        for spec in (G.MASSIF, G.SPUR):
            cx, cy = spec["cx"], spec["cy"]
            for (rx, ry, label) in spec["bands"]:
                z = 0.0
                for tok in label.replace("+", " +").split():
                    if tok.startswith("+") and tok[1:].isdigit():
                        z = float(tok[1:])
                bands.append((cx, cy, rx, ry, z))
        bands.sort(key=lambda b: b[4])

    def ground(x, y):
        if G.inside(G.AIRPORT, x, y):
            return P.ISLAND_Z
        if G.inside(G.HARBOUR, x, y):
            return 2.0
        z = 0.0
        for (cx, cy, rx, ry, bz) in bands:
            if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0:
                z = max(z, bz)
        return z
    return ground


# ------------------------------------------------------------------------- §6 support
def build_support(name, pts3, half_w, coll, ground, sample=P.PIER_SPACING):
    """THE uniform rule, applied. Walk the surface, ask `support_kind` at each station, and
    emit what it asks for — nothing, an embankment skirt, or a pier bent. One function
    serves the expressway deck, the ramps, the rail viaduct and the bridges, because from
    here they are all just "a surface at some height over some ground"."""
    made = {P.SUPPORT_NONE: 0, P.SUPPORT_FILL: 0, P.SUPPORT_PIER: 0,
            P.SUPPORT_CUT: 0, P.SUPPORT_TUNNEL: 0}
    run = 0.0
    for i, (x, y, z) in enumerate(pts3):
        if i:
            run += math.dist(pts3[i - 1][:2], (x, y))
        if i and run < sample:
            continue
        run = 0.0
        gz = ground(x, y)
        kind = P.support_kind(z, gz)
        made[kind] += 1
        if kind == P.SUPPORT_PIER:
            a = pts3[max(0, i - 1)]; b = pts3[min(len(pts3) - 1, i + 1)]
            tx, ty = b[0] - a[0], b[1] - a[1]
            L = math.hypot(tx, ty) or 1.0
            nx, ny = -ty / L, tx / L
            off = max(0.0, half_w - 2.0)
            # soffit — the structural depth the deck actually needs
            kc.box(f"{name}_soffit_{i}", x - half_w, x + half_w, y - 1.2, y + 1.2,
                   z - P.DECK_THICK, z - 0.05, coll, "concrete")
            for s in (-1.0, 1.0):
                px, py = x + nx * off * s, y + ny * off * s
                h = P.PIER_SECTION / 2.0
                kc.box(f"{name}_pier_{i}{'L' if s < 0 else 'R'}",
                       px - h, px + h, py - h, py + h, gz, z - P.DECK_THICK, coll, "concrete")
        elif kind == P.SUPPORT_FILL:
            toe = P.fill_footprint(z, gz, half_w)
            kc.box(f"{name}_fill_{i}", x - toe, x + toe, y - sample / 2, y + sample / 2,
                   gz - 0.2, z - 0.1, coll, "dirt")
    return made


# --------------------------------------------------------------------------- builders
def build_water_and_land(relief, ground):
    sea = kc.get_coll("SEA"); land = kc.get_coll("LAND"); water = kc.get_coll("WATER")
    h = G.ORIGIN + 120.0
    kc.box("Sea", -h, h, -h, h, Z_SEA - 0.4, Z_SEA, sea, "accent")
    kc.prism("Land_Main", G.MAIN, Z_SEA, Z_LAND, land, "leaf")
    kc.prism("Land_Harbour", G.HARBOUR, Z_SEA, 2.0, land, "concrete")
    kc.prism("Land_Airport", G.AIRPORT, Z_SEA, P.ISLAND_Z, land, "concrete")
    for i, islet in enumerate(G.ISLETS):
        kc.prism(f"Islet_{i}", islet, Z_SEA, 1.5, land, "trim")
    kc.prism("Water_Bay", G.BAY, Z_SEA, Z_WATER, water, "accent")
    kc.prism("Water_Lagoon", G.LAGOON, Z_SEA, Z_WATER, water, "accent")
    kc.flat_ribbon("Water_River", [(x, y, Z_WATER) for (x, y) in G.RIVER], 16.0,
                   water, "accent")
    if relief:
        terr = kc.get_coll("TERRAIN")
        for spec, nm in ((G.MASSIF, "Massif"), (G.SPUR, "Spur")):
            cx, cy = spec["cx"], spec["cy"]
            for k, (rx, ry, label) in enumerate(spec["bands"]):
                z = ground(cx, cy) if k else 0.0
                ring = G.pull_ashore(cx, cy, G.ellipse(cx, cy, rx, ry))
                zz = 0.0
                for tok in label.replace("+", " +").split():
                    if tok.startswith("+") and tok[1:].isdigit():
                        zz = float(tok[1:])
                kc.prism(f"{nm}_band_{k}", ring, Z_LAND, zz, terr, "leaf")
    return 3 + len(G.ISLETS)


def build_zones_and_blocks(streets, ground):
    zc = kc.get_coll("ZONES")
    n_zone = n_street = 0
    for (zname, rects, _f, _d, _r, _i, _col) in G.ZONES:
        for k, (x0, y0, x1, y1) in enumerate(rects):
            # OUTLINE, not a filled plate — a zone is an envelope you author inside, and a
            # solid plate buries the coast and terrain you need to see while doing it.
            ring = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
            kc.flat_ribbon(f"zone_{zname}_{k}", [(x, y, Z_ZONE) for (x, y) in ring],
                           3.0, zc, "line_y")
            n_zone += 1
    if not streets:
        return n_zone, 0
    sc = kc.get_coll("T3")
    for zi, (zname, rects, *_rest) in enumerate(G.ZONES):
        if zname == "farm":
            continue
        for k, rect in enumerate(rects):
            cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
            quarter, spec = P.block_spec_at(cx, cy, zname)
            for j, line in enumerate(P.street_grid(rect, spec, seed=zi * 17 + k)):
                kc.flat_ribbon(f"T3_{zname}{k}_{quarter}_{j}",
                               [(x, y, Z_T3) for (x, y) in line], HALF["T3"], sc, "asphalt")
                n_street += 1
    return n_zone, n_street


def build_castle():
    c = kc.get_coll("CASTLE")
    kc.prism("Moat_water", G.MOAT, Z_SEA, Z_WATER, c, "accent")
    kc.prism("Castle_ground", G.CASTLE, Z_LAND, 3.0, c, "trim")
    kc.box("Tenshu", -140, -100, 60, 96, 3.0, 27.0, c, "roof")
    for nm, poly in (("Park_Shiba", G.SHIBA_PK), ("Park_Shrine", G.SHRINE_PK)):
        kc.prism(nm, poly, Z_LAND, Z_ZONE, c, "leaf")
    # the castle-town rings — the §2 gradient made visible, so block sizes can be checked
    ring = kc.get_coll("PLANNING")
    for r, q in P.CASTLE_RINGS:
        pts = [(P.CASTLE_C[0] + r * math.cos(a * math.pi / 32),
                P.CASTLE_C[1] + r * math.sin(a * math.pi / 32)) for a in range(64)]
        kc.flat_ribbon(f"castle_ring_{int(r)}_{q or 'moat'}",
                       [(x, y, Z_MARK) for (x, y) in pts] + [(pts[0][0], pts[0][1], Z_MARK)],
                       1.2, ring, "line_y")


def build_roads(ground):
    t2 = kc.get_coll("T2")
    kc.flat_ribbon("T2_RING", [(x, y, Z_T2) for (x, y) in P.RING + [P.RING[0]]],
                   HALF["T2"], t2, "asphalt")
    for name, pts in G.ARTERIALS:
        kc.flat_ribbon(f"T2_{name.replace(' ', '_')}",
                       [(x, y, Z_T2) for (x, y) in pts], HALF["T2"], t2, "asphalt")

    t1 = kc.get_coll("T1"); sup = kc.get_coll("SUPPORT")
    stats = {}
    deck = P.loop_deck()
    kc.flat_ribbon("T1_LOOP", deck, HALF["T1"], t1, "asphalt")
    stats["LOOP"] = build_support("LOOP", deck, HALF["T1"], sup, ground)

    for rid, p3, par, grade, ok, kind in P.ramps():
        kc.flat_ribbon(f"T1_{rid}", p3, HALF["RAMP"], t1, "asphalt")
        stats[rid] = build_support(rid, p3, HALF["RAMP"], sup, ground, sample=22.0)
        if not ok:
            print(f"  WARNING: {rid} grade {grade*100:.1f}% exceeds "
                  f"{P.MAX_GRADE['ramp']*100:.0f}% — lengthen the run, do not steepen it")

    spiral, sg = P.spiral_ramp((905.0, -720.0))
    kc.flat_ribbon("T1_SPIRAL_AIRPORT", spiral, HALF["RAMP"], t1, "asphalt")
    stats["SPIRAL"] = build_support("SPIRAL", spiral, HALF["RAMP"], sup, ground, sample=22.0)

    # at-grade T1 continuations: these DRAPE, so the same support call gives them nothing —
    # which is the point of the rule being uniform.
    for nm, pts in (("WESTRAD", G.WESTRAD), ("PORTSPUR", G.PORTSPUR), ("TOUGE", G.TOUGE),
                    ("AIRPORT_ROAD", G.AIRPORT_ROAD)):
        p3 = [(x, y, ground(x, y) + 0.25) for (x, y) in pts]
        kc.flat_ribbon(f"T1_{nm}", p3, HALF["RAMP"], t1, "asphalt")
        stats[nm] = build_support(nm, p3, HALF["RAMP"], sup, ground)
    return stats


def build_rail(ground):
    rc = kc.get_coll("RAIL"); sup = kc.get_coll("SUPPORT")
    stats = {}
    for nm, pts in (("RAIL_MAIN", G.RAIL_MAIN), ("RAIL_BRANCH", G.RAIL_BRANCH),
                    ("RAIL_AIRPORT", G.RAIL_AIRPORT)):
        total = G.plen(pts) or 1.0
        run, p3 = 0.0, []
        for i, (x, y) in enumerate(pts):
            if i:
                run += math.dist(pts[i - 1], (x, y))
            p3.append((x, y, P.rail_z_at(nm, run / total, ground(x, y))))
        kc.flat_ribbon(nm, p3, HALF["RAIL"], rc, "rail")
        stats[nm] = build_support(nm, p3, HALF["RAIL"], sup, ground)
        tight = [r for r in P.curvature_radii(pts) if r < P.RAIL_MIN_RADIUS]
        if tight:
            print(f"  WARNING: {nm} has {len(tight)} vertex/vertices under the "
                  f"{P.RAIL_MIN_RADIUS:.0f} m mainline radius (tightest {min(tight):.0f} m) "
                  f"— ease it or accept it as a local line")
    return stats


def build_bridges(ground):
    bc = kc.get_coll("BRIDGES"); sup = kc.get_coll("SUPPORT")
    for nm, (a, b), z, half in (("Arch_bridge", G.ARCH_BRIDGE, 6.0, HALF["T2"]),
                                ("Bay_bridge", G.BAY_BRIDGE, 9.0, HALF["T2"]),
                                ("Airport_bridge", G.AIRPORT_BRIDGE, P.DECK_Z, HALF["T1"])):
        n = max(2, int(math.dist(a, b) / 20.0))
        p3 = [(a[0] + (b[0]-a[0])*i/n, a[1] + (b[1]-a[1])*i/n, z) for i in range(n + 1)]
        kc.flat_ribbon(nm, p3, half, bc, "concrete")
        build_support(nm, p3, half, sup, ground, sample=40.0)
        print(f"  {nm}: {math.dist(a, b):.0f} m span at +{z:.0f} m")
    (rx0, ry0), (rx1, ry1) = G.RUNWAY
    n = 24
    kc.flat_ribbon("Runway", [(rx0 + (rx1-rx0)*i/n, ry0 + (ry1-ry0)*i/n, P.ISLAND_Z + 0.1)
                              for i in range(n + 1)], 22.5, bc, "asphalt")


def build_parcels():
    pc = kc.get_coll("PARCELS")
    n = 0
    for (zname, rects, *_r) in G.ZONES:
        if zname != "farm":
            continue
        for i, rect in enumerate(rects):
            grain = P.FARM_RECT_GRAIN[i]
            for j, poly in enumerate(P.parcels(rect, grain, seed=i)):
                kc.prism(f"parcel_{grain}_{i}_{j}", poly, Z_BLOCK, Z_BLOCK + 0.03, pc, "leaf")
                n += 1
    return n


def build_markers():
    mk = kc.get_coll("MARKERS")
    for label, x, y, kind in G.LANDMARKS:
        e = bpy.data.objects.new(f"slot_{label.split('—')[0].strip().replace(' ', '_')}", None)
        e.empty_display_type = 'ARROWS'; e.empty_display_size = 30.0
        e.location = (x, y, Z_MARK)
        e["landmark"] = label; e["kind"] = kind
        mk.objects.link(e)
    for sid, x, y, note in G.SECTORS:
        e = bpy.data.objects.new(f"sector_{sid}", None)
        e.empty_display_type = 'SPHERE'; e.empty_display_size = 22.0
        e.location = (x, y, P.DECK_Z + 4.0)
        e["sector"] = sid; e["note"] = note
        mk.objects.link(e)
    for name, (sx, sy) in P.STATIONS:
        e = bpy.data.objects.new(f"station_{name}", None)
        e.empty_display_type = 'CONE'; e.empty_display_size = 26.0
        e.location = (sx, sy, P.RAIL_Z)
        e["station"] = name; e["walk_radius"] = P.STATION_WALK
        mk.objects.link(e)
    for rid, gore, touch, kind, note in P.INTERCHANGES:
        e = bpy.data.objects.new(f"ic_{rid}", None)
        e.empty_display_type = 'PLAIN_AXES'; e.empty_display_size = 18.0
        e.location = (gore[0], gore[1], P.DECK_Z)
        e["interchange"] = rid; e["kind"] = kind; e["serves"] = note
        mk.objects.link(e)


def build_grid():
    gc = kc.get_coll("GRID")
    for gy in range(G.GRID_N):
        for gx in range(G.GRID_N):
            theme = G.MATRIX[G.GRID_N - 1 - gy][gx]
            cx = gx * G.DISTRICT + G.DISTRICT / 2 - G.ORIGIN
            cy = gy * G.DISTRICT + G.DISTRICT / 2 - G.ORIGIN
            e = bpy.data.objects.new(f"region_Piece_{gx}_{gy}", None)
            e.empty_display_type = 'CUBE'; e.empty_display_size = G.DISTRICT / 2.0
            e.location = (cx, cy, 0.0)
            e["size"] = [G.DISTRICT, 40.0, G.DISTRICT]
            e["theme"] = theme.lower()
            e["built"] = theme.lower() != "void"
            gc.objects.link(e)


# ------------------------------------------------------------------------------- main
def parse_args():
    import argparse
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="build_island_v3.py")
    ap.add_argument("--relief", action="store_true",
                    help="step the terrain bands to real elevations (default: flat 2D plan)")
    ap.add_argument("--streets", action="store_true",
                    help="generate T3 local streets from the block gradient (heavier)")
    ap.add_argument("--parcels", action="store_true",
                    help="generate farmland parcels across the three grains (heavier)")
    ap.add_argument("--full", action="store_true", help="relief + streets + parcels")
    a = ap.parse_args(argv)
    if a.full:
        a.relief = a.streets = a.parcels = True
    return a


def build(opts):
    kc.setup_units()
    asm.wipe_scene()
    for name in ("SEA", "LAND", "WATER", "TERRAIN", "ZONES", "PLANNING", "CASTLE",
                 "T1", "T2", "T3", "RAIL", "BRIDGES", "SUPPORT", "PARCELS",
                 "MARKERS", "GRID"):
        kc.get_coll(name)

    ground = make_ground_fn(opts.relief)
    n_land = build_water_and_land(opts.relief, ground)
    n_zone, n_street = build_zones_and_blocks(opts.streets, ground)
    build_castle()
    road_stats = build_roads(ground)
    rail_stats = build_rail(ground)
    build_bridges(ground)
    n_parcel = build_parcels() if opts.parcels else 0
    build_markers()
    build_grid()

    asm.add_camera_sun(kc.get_coll("MARKERS"), target=(0.0, 0.0, 0.0),
                       cam_loc=(0.0, -G.WORLD * 0.75, G.WORLD * 0.85), lens=32)

    tot = {}
    for st in list(road_stats.values()) + list(rail_stats.values()):
        for k, v in st.items():
            tot[k] = tot.get(k, 0) + v
    print("ISLAND v3: %.0fx%.0f m  relief=%s  land=%d  zones=%d  T3=%d  parcels=%d"
          % (G.WORLD, G.WORLD, opts.relief, n_land, n_zone, n_street, n_parcel))
    print("  support stations derived: " +
          "  ".join(f"{k}={v}" for k, v in sorted(tot.items()) if v))


def main():
    build(parse_args())
    if bpy.app.background:
        kc.save_blend(ROOT, "island_v3.blend")


if __name__ == "__main__":
    main()
