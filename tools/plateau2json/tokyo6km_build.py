#!/usr/bin/env python3
"""Emit the compressed-Tokyo layout: layout.json (for the Blender tools) + preview.png.

    python3 tokyo6km_build.py --out build/tokyo6km

layout.json is the injection surface for blender/tools/build_world.py and the
road_kit_authoring addon: every position is a GAME metre in world_grid.py's
centre-origin space, so a district builder reads a cell straight out of `districts[]`
and a road tool reads a polyline straight out of `roads`/`rail`.

Data: Project PLATEAU (MLIT), CC BY 4.0.
"""

from __future__ import annotations

import argparse
import json
import math
import os

import tokyo6km_layout as L
import tokyo6km_network as N


def poly_len(pts, closed=False):
    p = list(pts) + ([pts[0]] if closed else [])
    return sum(math.dist(a, b) for a, b in zip(p, p[1:]))


def districts():
    out = []
    for gy in range(L.GRID_N):
        for gx in range(L.GRID_N):
            th = L.theme_at(gx, gy)
            x0, y0, x1, y1 = L.cell_bounds(gx, gy)
            cx, cy = L.cell_center(gx, gy)
            r = N.STREET_RULES.get(th)
            out.append(dict(
                id=f"Piece_{gx}_{gy}", gx=gx, gy=gy, theme=th,
                center=[round(cx, 1), round(cy, 1)],
                bounds=[round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
                size_m=L.DISTRICT,
                street_rules=r,
            ))
    return out


def build(outdir):
    os.makedirs(outdir, exist_ok=True)
    hw = N.highways()
    rw = N.railways()

    doc = dict(
        schema="tokyo6km/1",
        note=("Authored spatial compression of PLATEAU Tokyo 23-ku onto a 6.048 km "
              "square. All positions are GAME metres, centre-origin, X=east Y=north, "
              "matching blender/lib/world_grid.py."),
        attribution="Data: Project PLATEAU (MLIT), CC BY 4.0",
        grid=dict(cell_m=L.CELL, district_m=L.DISTRICT, grid_n=L.GRID_N,
                  world_m=L.WORLD, origin_shift_m=L.ORIGIN,
                  world_min=[-L.ORIGIN, -L.ORIGIN], world_max=[L.ORIGIN, L.ORIGIN]),
        source_extent=dict(
            crs="EPSG:6677",
            real_bbox=[-16616.8, -51809.5, -3018.6, -30003.7],
            real_size_km=[13.6, 21.8],
            compressed_size_km=[L.WORLD / 1000.0, L.WORLD / 1000.0],
            linear_ratio=[round(13598.2 / L.WORLD, 3), round(21805.8 / L.WORLD, 3)],
            area_ratio=round((13.6 * 21.8) / ((L.WORLD / 1000.0) ** 2), 2)),
        warp=dict(tier_a=dict(x=L.WARP_X.to_json(), y=L.WARP_Y.to_json()),
                  tier_b=L.MTN_XFORM),
        matrix=L.MAP_ROWS,
        matrix_text=L.matrix_text(),
        tentpoles=L.tentpoles(),
        runway=L.runway(),
        buffers=N.buffers(),
        districts=districts(),
        roads=dict(
            tiers=dict(
                T1=dict(label="elevated expressway", width_m=22.0, deck_z=N.DECK_Z,
                        ramp_len_m=N.RAMP_LEN, at_grade_junctions=False),
                T2=dict(label="arterial", width_m=N.ARTERIAL_W, spacing_m=L.DISTRICT),
                T3=dict(label="local street", width_m=14.0, spacing_m=168.0),
                T4=dict(label="alley (roji)", width_m=4.5, spacing_m="per theme")),
            highways=[dict(h, length_m=round(poly_len(h["points"], h.get("closed", False)), 1))
                      for h in hw],
            outer_circuit=N.outer_circuit(),
            arterials=N.arterials()),
        rail=[dict(r, length_m=round(poly_len(r["points"], r.get("closed", False)), 1))
              for r in rw],
        land=N.land(),
        street_rules=N.STREET_RULES,
    )

    path = os.path.join(outdir, "layout.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
    return doc, path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="build/tokyo6km")
    a = ap.parse_args()
    doc, path = build(a.out)
    print(doc["matrix_text"])
    print()
    print("TIER A warp — X (west->east)")
    for s in doc["warp"]["tier_a"]["x"]["segments"]:
        print(f"   real {s['real_len_m']:8.0f} m -> game {s['game_len_m']:7.0f} m "
              f"| scale {s['scale']:.3f} | deleted {s['deleted_m']:8.0f} m")
    print("TIER A warp — Y (south->north)")
    for s in doc["warp"]["tier_a"]["y"]["segments"]:
        print(f"   real {s['real_len_m']:8.0f} m -> game {s['game_len_m']:7.0f} m "
              f"| scale {s['scale']:.3f} | deleted {s['deleted_m']:8.0f} m")
    print()
    for h in doc["roads"]["highways"]:
        print(f"   {h['id']:14s} {h['length_m']:8.0f} m  {h['label']}")
    for r in doc["rail"]:
        print(f"   {r['id']:14s} {r['length_m']:8.0f} m  {r['label']}")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
