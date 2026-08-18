#!/usr/bin/env python3
"""Render the compressed map from REAL PLATEAU geometry — organic land, water and roads.

The square-district preview was a lie about what the map is. A district is a *streaming
container*; it is not the shape of the land and it is not the road network. Both of those
come from the survey data:

  * WATER is a FIELD layer — the coastline, the Sumida, the canals and the wharf slips
    must warp POINT-WISE or adjacent polygons tear apart and leave gaps. Same rule
    compress.py already applies to terrain/landuse/water.
  * ROADS are compact LOD1 footprint polygons (244k of them across the bbox, each a short
    segment). Each one is translated RIGIDLY by the warp of its own centroid, so every
    carriageway keeps its true width and true shape and only its POSITION moves. This is
    compress.py's "compact blob" rule, and it is why the street mesh stays organic
    instead of collapsing into a grid.

    python3 tokyo6km_real.py --out build/tokyo6km/real.png --size 2600

Data: Project PLATEAU (MLIT), CC BY 4.0.
"""

from __future__ import annotations

import argparse
import json
import math
import os

from PIL import Image, ImageDraw

import tokyo6km_layout as L
import tokyo6km_network as N

# The extractor writes coordinates RELATIVE to --origin. Everything here works in
# absolute EPSG:6677, so add the origin's own projected position back on.
ORIGIN_6677 = L.REAL["tokyo_stn"]        # --origin 139.7671 35.6812 == Tokyo Station

ROAD_DIRS = ("build/plateau_tokyo6km_road",)
WATER_DIRS = ("build/plateau_tokyo6km_water",)
LAND_DIRS = ("build/plateau_tokyo6km",)

# The --bbox the extracts were pulled with, in EPSG:6677 (x0, y0, x1, y1).
# Outside this window there is simply no survey data, which is NOT the same as water.
EXTRACT_BBOX_6677 = (-17400.0, -52400.0, -2600.0, -29200.0)

# THE OPEN BAY IS NOT IN THE DATA. PLATEAU is published per municipality, so every ward
# dataset stops dead at its own shoreline — the `wtr` module's five 海 features are
# 40 m harbour curves, not Tokyo Bay. The coastline is therefore derived the other way
# round, which is also how the reference maps do it:
#
#     LAND  = the union of the luse chōme polygons (they tile every square metre of
#             land and nothing offshore)
#     WATER = the complement, plus the rivers/canals cut back in on top
#
# That yields a genuinely organic coast — wharves, slips, reclaimed islands and the
# Sumida delta all fall out of the survey rather than being hand-drawn.

# Road_function -> (draw order, colour weight). Majors are drawn last and brightest so
# the arterial skeleton reads through the municipal mesh — the reference-map look.
MAJOR = {"1": 3, "2": 2, "3": 1}


def load(dirs, name, root):
    for d in dirs:
        p = os.path.join(root, d, name)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
    raise SystemExit(f"missing {name}; run the extract.py commands in "
                     f"blender/TOKYO_6KM_COMPRESSION.md §7 first")


def abs_pt(p):
    return (p[0] + ORIGIN_6677[0], p[1] + ORIGIN_6677[1])


def centroid(pts):
    n = len(pts)
    return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)


def poly_area(pts):
    n = len(pts)
    return abs(sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
                   for i in range(n))) / 2.0


# A road narrower than this is not a road you can drive, so it is never drawn thinner —
# the point-wise warp squeezes the footprint, the stroke gives the lane back.
MIN_ROAD_M = 6.0

# Landmarks keep EVERY street inside this radius (game metres). The tentpoles are where
# the player actually looks, so detail is spent there and taken from everywhere else.
LANDMARK_KEEP_M = 100.0

# Streets kept per 56 m bucket outside the landmark radii, ranked by width.
CELL_QUOTA = 2


def render(out, size, root, road_keep=1.0, overlay=True,
           min_area=100.0, quota=CELL_QUOTA):
    road = load(ROAD_DIRS, "road.json", root)["features"]
    water = load(WATER_DIRS, "water.json", root)["features"]

    LAND = (150, 214, 173)      # the reference's land green
    SEA = (39, 58, 74)          # deep slate water
    ROADC = (255, 255, 255)

    img = Image.new("RGB", (size, size), LAND)
    d = ImageDraw.Draw(img)
    mpp = L.WORLD / size

    def P(x, y):
        return ((x + L.ORIGIN) / mpp, (L.ORIGIN - y) / mpp)

    inb = lambda g: -L.ORIGIN - 400 <= g[0] <= L.ORIGIN + 400 and \
                    -L.ORIGIN - 400 <= g[1] <= L.ORIGIN + 400

    # "No land-use polygon here" only means WATER inside the window the extract actually
    # covers. Outside it (the rural/mountain rows to the north, which are Tier B and not
    # extracted at all) absence means "no data" — painting that sea would invent an ocean
    # across the whole north of the map, which the first pass did.
    ex = EXTRACT_BBOX_6677
    w0, w1 = L.warp((ex[0], ex[1])), L.warp((ex[2], ex[3]))
    d.rectangle([P(w0[0], w1[1]), P(w1[0], w0[1])], fill=SEA)

    # ---- land: FIELD layer -> warp every point, or adjacent chōme tear apart.
    land = load(LAND_DIRS, "landuse.json", root)["features"]
    nl = 0
    for r in land:
        for g in r.get("geometry", []):
            pts = g["points"]
            if len(pts) < 3:
                continue
            gp = [L.warp(abs_pt(p)) for p in pts]
            if not any(inb(q) for q in gp):
                continue
            d.polygon([P(*q) for q in gp], fill=LAND)
            nl += 1

    # ---- water: FIELD layer -> warp every point. Rings only (surfaces), not curves.
    nw = 0
    for r in water:
        for g in r.get("geometry", []):
            if "MultiSurface" not in (g.get("lod") or ""):
                continue
            pts = g["points"]
            if len(pts) < 3:
                continue
            gp = [L.warp(abs_pt(p)) for p in pts]
            if not any(inb(q) for q in gp):
                continue
            d.polygon([P(*q) for q in gp], fill=SEA)
            nw += 1

    # ---- roads: compact blobs -> rigid translation, so every carriageway keeps its
    # TRUE width and shape and only its position moves.
    #
    # Rigid translation alone is not enough, and the first render proved it: at a local
    # scale of 0.12 the same road area is being packed into an eighth of the space, so
    # 244k footprints merged into one solid white sheet. That IS the design's own rule
    # arriving as a picture — when a band cannot fit, you DELETE roads, you do not thin
    # them. So the municipal mesh is decimated to the LOCAL WARP SCALE (jacobian at that
    # point), which is exactly `block_retention`; majors (national expressway / national
    # highway / prefectural) are NEVER dropped, so the arterial skeleton survives intact
    # and the deletion lands only on the interchangeable side streets.
    tent = [t["game_xy"] for t in L.tentpoles()]

    def near_landmark(g):
        return any((g[0] - t[0]) ** 2 + (g[1] - t[1]) ** 2 < LANDMARK_KEEP_M ** 2
                   for t in tent)

    cell_roads: dict = {}
    nr = nkept = 0
    majors = []
    for r in road:
        fn = r.get("function")
        code = fn.get("code") if isinstance(fn, dict) else None
        rid = r.get("id") or ""
        for gi, g in enumerate(r.get("geometry", [])):
            pts = g["points"]
            if len(pts) < 3:
                continue
            c = centroid([abs_pt(p) for p in pts])
            wc = L.warp(c)
            nr += 1
            if not inb(wc):
                continue
            if code not in MAJOR and not near_landmark(wc):
                # There is NO literal duplication to remove — all 244,452 footprints are
                # distinct (checked). What reads as "duplicated" is fragmentation plus
                # redundant parallel streets, so the reduction is essentiality, not dedup:
                #
                #  1. SLIVERS. Half the polygons are under 100 m² and carry only 10% of
                #     total road area — PLATEAU splits one street into many pieces at tile
                #     and attribute boundaries. They add cost and no legibility.
                #  2. PER-CELL QUOTA. Every other street is ranked by area inside its own
                #     56 m bucket and only the top few survive, so density drops evenly
                #     and the WIDEST (most drivable) road in each neighbourhood is the one
                #     that lives — far better than the uniform random thinning this
                #     replaces, which chewed holes in arterials at random.
                if poly_area(pts) < min_area:
                    continue
                bucket = (int(wc[0] // 56.0), int(wc[1] // 56.0))
                cell_roads.setdefault(bucket, []).append((poly_area(pts), rid, gi, pts))
                continue
            nkept += 1
            # REGISTRATION BEATS RIGIDITY. Land and water warp point-wise; roads used to
            # be translated rigidly (compact) or warped on one axis only (elongated).
            # Three different transforms cannot register, so roads drifted off their own
            # blocks and read as horizontally squeezed against the land. Everything now
            # takes the SAME point-wise warp — the road lands exactly on its block.
            #
            # The width the point-wise warp costs is given back as a STROKE, not by
            # refusing to warp: a road is never drawn thinner than MIN_ROAD_M. That
            # honours "never compress the thing itself" while keeping the map coherent.
            poly = [P(*L.warp(abs_pt(q))) for q in pts]
            if code in MAJOR:
                majors.append(poly)
            else:
                d.polygon(poly, fill=ROADC, outline=ROADC,
                          width=max(1, int(MIN_ROAD_M / mpp)))
    # drain the per-cell quota: widest streets win their bucket
    stroke = max(1, int(MIN_ROAD_M / mpp))
    for bucket, cands in cell_roads.items():
        cands.sort(key=lambda t: -t[0])
        for _a, _rid, _gi, pts in cands[:max(0, int(quota * road_keep))]:
            poly = [P(*L.warp(abs_pt(q))) for q in pts]
            d.polygon(poly, fill=ROADC, outline=ROADC, width=stroke)
            nkept += 1
    for poly in majors:                      # majors on top, always widest
        d.polygon(poly, fill=ROADC, outline=ROADC, width=stroke + 1)
    nr = nkept

    # ---- game-space overlay: district seams + tentpoles. Drawn LAST and thin, because
    # the point of this render is that the grid is a streaming container laid OVER the
    # organic city — not the shape of it.
    if overlay:
        ov = ImageDraw.Draw(img, "RGBA")
        for k in range(L.GRID_N + 1):
            c = L.to_world(k * L.DISTRICT)
            ov.line([P(c, -L.ORIGIN), P(c, L.ORIGIN)], fill=(20, 30, 40, 90), width=1)
            ov.line([P(-L.ORIGIN, c), P(L.ORIGIN, c)], fill=(20, 30, 40, 90), width=1)
        for t in L.tentpoles():
            x, y = P(*t["game_xy"])
            r = 9
            ov.ellipse([x - r, y - r, x + r, y + r], fill=(214, 64, 40, 235),
                       outline=(255, 255, 255), width=2)
            ov.text((x + 13, y - 7), t["label"], fill=(255, 255, 255),
                    stroke_width=3, stroke_fill=(20, 30, 40))
        rw = L.runway()
        ov.line([P(*rw["north_end"]), P(*rw["south_end"])],
                fill=(255, 255, 255, 230), width=max(2, int(rw["width_m"] / mpp)))
        ov.text((10, 10), f"PLATEAU Tokyo 23-ku compressed to {L.WORLD:.0f} m  "
                          f"({L.GRID_N}x{L.GRID_N} x {L.DISTRICT:.0f} m districts)",
                fill=(255, 255, 255), stroke_width=3, stroke_fill=(20, 30, 40))
        ov.text((10, 26), "land + water + roads are REAL survey geometry warped into "
                          "game space; the grid is only the streaming container",
                fill=(240, 240, 240), stroke_width=3, stroke_fill=(20, 30, 40))
        ov.text((10, 42), "Data: Project PLATEAU (MLIT), CC BY 4.0",
                fill=(225, 225, 225), stroke_width=3, stroke_fill=(20, 30, 40))

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    img.save(out)
    with open(os.path.splitext(out)[0] + ".json", "w") as fh:
        json.dump(dict(metres_per_pixel=mpp, extent_m=L.WORLD, origin="centre",
                       axes="X=east, Y=north", water_rings=nw, road_polygons=nr), fh,
                  indent=1)
    return nw, nr, mpp


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="build/tokyo6km/real.png")
    ap.add_argument("--size", type=int, default=2600)
    ap.add_argument("--root", default=".")
    ap.add_argument("--min-area", type=float, default=100.0,
                    help="drop road fragments below this many m2")
    ap.add_argument("--quota", type=int, default=CELL_QUOTA,
                    help="streets kept per 56 m bucket outside landmarks")
    ap.add_argument("--no-overlay", action="store_true",
                    help="omit the district grid / tentpole overlay")
    ap.add_argument("--road-keep", type=float, default=1.0,
                    help="extra multiplier on the area-scale road retention")
    a = ap.parse_args()
    nw, nr, mpp = render(a.out, a.size, a.root, a.road_keep, not a.no_overlay,
                              a.min_area, a.quota)
    print(f"wrote {a.out}  {nw:,} water rings, {nr:,} road polygons, {mpp:.3f} m/px")
