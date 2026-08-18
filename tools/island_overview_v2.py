#!/usr/bin/env python3
"""Tokyo-Bay island v2 — OVERVIEW plate (legibility-first).

The companion to `island_plate_v2.py`. Same geometry, same game metres, but no building
texture: district themes as flat colour, road hierarchy, rail, landmarks, race circuit,
and a legend column. This is the "read the plan in 10 seconds" map; the modeling plate is
the "trace it in Blender" map.

    python3 tools/island_overview_v2.py --out tokyo-bay-island-overview-v2.svg
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import os

_here = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("plate", os.path.join(_here, "island_plate_v2.py"))
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)

DISTRICT, GRID_N, WORLD, ORIGIN = P.DISTRICT, P.GRID_N, P.WORLD, P.ORIGIN

S = 0.355
MX, MY = 54.0, 78.0
MAPW = WORLD * S
LEGW = 316.0
W = int(MX * 2 + MAPW + LEGW)
H = int(MY + MAPW + 96)


def px(x, y):
    return (MX + (x + ORIGIN) * S, MY + (ORIGIN - y) * S)


def path(pts, close=True):
    d = "M" + " L".join(f"{a:.1f} {b:.1f}" for a, b in (px(*p) for p in pts))
    return d + (" Z" if close else "")


# gy5 (north) -> gy0 (south); land fraction drives the assignment, see the spec §2
MATRIX = [
    ["void", "mtn", "rural", "rural", "rural", "void"],      # gy5
    ["mtn", "mtn", "rural", "rural", "rural", "resid"],      # gy4
    ["resid", "resid", "city", "CITY", "city", "resid"],     # gy3
    ["resid", "resid", "CITY", "city", "city", "void"],      # gy2
    ["void", "indus", "indus", "harbor", "harbor", "void"],  # gy1
    ["void", "void", "harbor", "harbor", "HARBOR", "harbor"],  # gy0
]

THEME = {
    "mtn":    ("#9DB47F", "Mountain / touge", "0.59 km²"),
    "rural":  ("#C6D5A6", "Rural valley", "1.36 km²"),
    "resid":  ("#DCCFA8", "Residential", "1.16 km²"),
    "city":   ("#C99C86", "Neon core", "1.44 km²"),
    "harbor": ("#8FA6A0", "Harbour / waterfront", "0.58 km²"),
    "indus":  ("#B0A694", "Industry (Keihin)", "0.36 km²"),
    "void":   (None, "Void — streams nothing", "6 cells"),
}

PINS = [
    ("1", "Tokyo Tower — 333 m, kept 1:1", 185, -470, "asset"),
    ("2", "Zojo-ji / Shiba park", 115, -510, "kit"),
    ("3", "Imperial Palace — the central void", 60, 45, "kit"),
    ("4", "Tokyo Station / Marunouchi", 392, -62, "kit"),
    ("5", "Akihabara — under-guard strip", 700, 300, "kit"),
    ("6", "Shinjuku / Kabukicho", -812, 336, "kit"),
    ("7", "Shibuya scramble — crowd set piece", -545, -168, "kit"),
    ("8", "Meiji shrine", -665, 440, "kit"),
    ("9", "Pass shrine — same kit, re-dressed", -1070, 1118, "kit"),
    ("10", "Rainbow Bridge — 460 m double-deck", 425, -668, "asset"),
    ("11", "Odaiba + ferry pier", 700, -1050, ""),
    ("12", "Haneda terminal + drag strip", 1300, -1400, "asset"),
    ("13", "Keihin industry — kojo yakei", -410, -900, ""),
    ("14", "Ginza", 500, -270, ""),
    ("15", "Ueno", 500, 715, ""),
    ("16", "Tunnel portal — hides the Tier-B seam", -1196, 736, "asset"),
]

SECTORS = [("S1", 60, 500, "Kanda straight — flat out"),
           ("S2", 600, 240, "Akiba esses — walls close"),
           ("S3", 470, -380, "Shiodome hairpin — braking point"),
           ("S4", -180, -380, "Shiba sweep — Tokyo Tower shot"),
           ("S5", -410, 120, "Yotsuya cutting — blind crest"),
           ("S6", -280, 500, "moat straight — start/finish")]


def build():
    o = []
    a = o.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
      f'viewBox="0 0 {W} {H}" font-family="sans-serif">')
    a('<style>'
      '.h{font:700 17px sans-serif;fill:#1e1e1a}'
      '.sub{font:400 10.5px sans-serif;fill:#67655c}'
      '.lh{font:700 10px sans-serif;fill:#1e1e1a;letter-spacing:.6px}'
      '.li{font:400 9.5px sans-serif;fill:#3a382f}'
      '.lm{font:600 9.5px sans-serif;fill:#3a382f}'
      '.cell{font:600 8px sans-serif;fill:#5c5949}'
      '.z{font:700 12px sans-serif;fill:#23231f}'
      '.pin{font:700 8.5px sans-serif;fill:#fff}'
      '.sea{font:500 9.5px sans-serif;fill:#42687e;letter-spacing:2px}'
      '</style>')
    a(f'<rect width="{W}" height="{H}" fill="#F1EDE1"/>')

    a(f'<text class="h" x="{MX}" y="34">Tokyo-Bay Island v2 — plan overview</text>')
    a(f'<text class="sub" x="{MX}" y="52">3024 x 3024 m · 6 x 6 districts of 504 m · '
      f'centre origin — blender/lib/world_grid.py unchanged (GRID_N = 6). '
      f'Layout: real Tokyo topology, PLATEAU decimated 272:1.</text>')

    a(f'<rect x="{MX:.0f}" y="{MY:.0f}" width="{MAPW:.0f}" height="{MAPW:.0f}" '
      f'fill="#9EB8C6"/>')

    # land clip
    a('<defs><clipPath id="land">')
    for p in P.LAND:
        a(f'<path d="{path(p)}"/>')
    a('</clipPath></defs>')

    a(f'<g clip-path="url(#land)">')
    a(f'<rect x="{MX:.0f}" y="{MY:.0f}" width="{MAPW:.0f}" height="{MAPW:.0f}" '
      f'fill="#E5E0CF"/>')
    for r, row in enumerate(MATRIX):
        gy = 5 - r
        for gx, key in enumerate(row):
            col = THEME[key.lower()][0]
            if not col:
                continue
            x0, y0 = px(-ORIGIN + gx * DISTRICT, -ORIGIN + (gy + 1) * DISTRICT)
            a(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{DISTRICT*S:.1f}" '
              f'height="{DISTRICT*S:.1f}" fill="{col}"/>')
    a('</g>')

    for p in P.LAND:
        a(f'<path d="{path(p)}" fill="none" stroke="#4E7183" stroke-width="1.8"/>')

    # snow cap + summit
    cx, cy = -900, 1000
    snow = P.pull_ashore(cx, cy, P.ellipse(cx, cy, 185, 138, 40, math.radians(-12)))
    a(f'<path d="{path(snow)}" fill="#F2F4EE" stroke="#8fa07c" stroke-width="0.8"/>')
    sx, sy = px(cx, 1010)
    a(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="2.6" fill="#4f4c42"/>')

    # palace + river
    a(f'<path d="{path(P.MOAT)}" fill="#7FA3B8"/>')
    a(f'<path d="{path(P.PALACE)}" fill="#A8BE8C" stroke="#7d8a6b" stroke-width="0.8"/>')
    a(f'<path d="{path(P.RIVER, False)}" fill="none" stroke="#7FA3B8" stroke-width="4" '
      f'stroke-linecap="round" stroke-linejoin="round"/>')

    # district seams + cell ids
    for i in range(GRID_N + 1):
        v = -ORIGIN + i * DISTRICT
        x, _ = px(v, 0)
        _, y = px(0, v)
        a(f'<line x1="{x:.1f}" y1="{MY}" x2="{x:.1f}" y2="{MY+MAPW:.0f}" '
          f'stroke="#00000030"/>')
        a(f'<line x1="{MX}" y1="{y:.1f}" x2="{MX+MAPW:.0f}" y2="{y:.1f}" '
          f'stroke="#00000030"/>')
    for r, row in enumerate(MATRIX):
        gy = 5 - r
        for gx, key in enumerate(row):
            sx, sy = px(-ORIGIN + (gx + .5) * DISTRICT, -ORIGIN + (gy + .08) * DISTRICT)
            tag = key if key.isupper() else key
            a(f'<text class="cell" x="{sx:.0f}" y="{sy:.0f}" text-anchor="middle" '
              f'opacity="{0.85 if key.isupper() else 0.55}">{gx}{gy} {tag}</text>')

    # T2 arterial backbone (thin — structure only)
    for ln in P.arterials():
        for run in P.clipped(ln, 14):
            a(f'<path d="{path(run, False)}" fill="none" stroke="#FBF8EF" '
              f'stroke-width="3.4" stroke-linecap="round"/>')

    # rail
    for pl, closed in ((P.YAMANOTE, True), (P.CHUO, False), (P.SHINKANSEN, False),
                       (P.YURIKAMOME, False), (P.MONORAIL, False)):
        q = pl + [pl[0]] if closed else pl
        a(f'<path d="{path(q, False)}" fill="none" stroke="#33604C" stroke-width="1.7" '
          f'stroke-dasharray="8 4" stroke-linejoin="round"/>')

    # T1 expressway
    for pl, closed in ((P.C1, True), (P.WANGAN, False), (P.R4, False), (P.R5, False),
                       (P.R1, False)):
        q = pl + [pl[0]] if closed else pl
        a(f'<path d="{path(q, False)}" fill="none" stroke="#8a5320" stroke-width="9.4" '
          f'stroke-linejoin="round" stroke-linecap="round" stroke-opacity="0.45"/>')
        a(f'<path d="{path(q, False)}" fill="none" stroke="#EE9B4E" stroke-width="7.2" '
          f'stroke-linejoin="round" stroke-linecap="round"/>')

    a(f'<path d="{path(P.TOUGE, False)}" fill="none" stroke="#6f6a58" '
      f'stroke-width="4.4" stroke-linejoin="round" stroke-linecap="round"/>')
    a(f'<path d="{path(P.TOUGE, False)}" fill="none" stroke="#FBF8EF" '
      f'stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>')

    # hero spans
    for (p0, p1) in (((350, -455), (505, -885)), ((1030, -1035), (1230, -1258))):
        x0, y0 = px(*p0)
        x1, y1 = px(*p1)
        a(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
          f'stroke="#B23A18" stroke-width="5.4" stroke-linecap="round"/>')

    # runway
    x0, y0 = px(660, -1470)
    x1, y1 = px(1420, -1300)
    a(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
      f'stroke="#F7F4EA" stroke-width="{60*S:.1f}"/>')
    a(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
      f'stroke="#C9A24A" stroke-width="1" stroke-dasharray="7 7"/>')

    # race sectors
    for (lab, x, y, _n) in SECTORS:
        sx, sy = px(x, y)
        a(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="8" fill="#B23A18" stroke="#fff" '
          f'stroke-width="1.4"/>')
        a(f'<text class="pin" x="{sx:.1f}" y="{sy+3:.1f}" text-anchor="middle">{lab}</text>')

    # landmark pins
    for (n, _lab, x, y, kind) in PINS:
        sx, sy = px(x, y)
        col = {"asset": "#7A1F0B", "kit": "#6B4A1E"}.get(kind, "#3f3d36")
        a(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="8" fill="{col}" stroke="#fff" '
          f'stroke-width="1.4"/>')
        a(f'<text class="pin" x="{sx:.1f}" y="{sy+3:.1f}" text-anchor="middle">{n}</text>')

    for (lab, x, y) in (("BAY", 800, -560), ("OPEN SEA", -1270, -1150),
                        ("OPEN SEA", 1290, 1250)):
        sx, sy = px(x, y)
        a(f'<text class="sea" x="{sx:.0f}" y="{sy:.0f}" text-anchor="middle">{lab}</text>')

    nx, ny = MX + MAPW - 22, MY + 30
    a(f'<path d="M{nx} {ny-19} L{nx+4.5} {ny-9} L{nx-4.5} {ny-9} Z" fill="#23231f"/>')
    a(f'<text class="sub" x="{nx}" y="{ny+3}" text-anchor="middle">N</text>')
    by = MY + MAPW + 22
    a(f'<line x1="{MX}" y1="{by}" x2="{MX+504*S:.1f}" y2="{by}" stroke="#23231f" '
      f'stroke-width="2"/>')
    a(f'<text class="sub" x="{MX+504*S+9:.0f}" y="{by+4:.0f}">504 m = 1 district</text>')
    a(f'<text class="sub" x="{MX}" y="{by+22:.0f}">Detail plate (roads, blocks, 3797 '
      f'building footprints): tokyo-bay-island-modeling-plate-v2.svg</text>')

    # ------------------------------------------------------------------ legend
    lx = MX + MAPW + 26
    y = MY + 6

    def head(txt, y):
        o.append(f'<text class="lh" x="{lx}" y="{y}">{txt.upper()}</text>')
        o.append(f'<line x1="{lx}" y1="{y+5}" x2="{lx+LEGW-40}" y2="{y+5}" '
                 f'stroke="#00000022"/>')
        return y + 19

    y = head("District themes — 30 built of 36", y)
    for key in ("mtn", "rural", "resid", "city", "harbor", "indus", "void"):
        col, name, note = THEME[key]
        if col:
            a(f'<rect x="{lx}" y="{y-8}" width="13" height="11" fill="{col}" '
              f'stroke="#00000030"/>')
        else:
            a(f'<rect x="{lx}" y="{y-8}" width="13" height="11" fill="#9EB8C6" '
              f'stroke="#00000030" stroke-dasharray="2 2"/>')
        a(f'<text class="lm" x="{lx+20}" y="{y+1}">{name}</text>')
        a(f'<text class="li" x="{lx+LEGW-40}" y="{y+1}" text-anchor="end">{note}</text>')
        y += 16
    a(f'<text class="li" x="{lx}" y="{y+3}">Land 5.57 km² of the 9.14 km² box — '
      f'Vice City 5.62, GTA III 4.38.</text>')
    y += 26

    y = head("Road hierarchy", y)
    for (col, wdt, name, note) in (
            ("#EE9B4E", 7.0, "T1 expressway", "22 m deck, +12 m"),
            ("#FBF8EF", 3.4, "T2 arterial", "27 m, every 504 m seam"),
            ("#B23A18", 5.0, "hero span", "Rainbow Br. 460 m"),
            ("#33604C", 1.7, "rail viaduct", "+8 / +11 / +13 m")):
        a(f'<line x1="{lx}" y1="{y-3}" x2="{lx+16}" y2="{y-3}" stroke="{col}" '
          f'stroke-width="{wdt}" stroke-linecap="round"'
          f'{" stroke-dasharray=\"6 3\"" if name.startswith("rail") else ""}/>')
        a(f'<text class="lm" x="{lx+24}" y="{y+1}">{name}</text>')
        a(f'<text class="li" x="{lx+LEGW-40}" y="{y+1}" text-anchor="end">{note}</text>')
        y += 16
    a(f'<text class="li" x="{lx}" y="{y+3}">T3 local 14 m @168 m and T4 alley 4.5 m '
      f'@45-60 m are</text>')
    a(f'<text class="li" x="{lx}" y="{y+15}">generated per block, not drawn here.</text>')
    y += 34

    y = head("Race circuit — C1 lap 3475 m, ~95 s", y)
    for (lab, _x, _y, note) in SECTORS:
        a(f'<circle cx="{lx+7}" cy="{y-3}" r="7" fill="#B23A18"/>')
        a(f'<text class="pin" x="{lx+7}" y="{y}" text-anchor="middle">{lab}</text>')
        a(f'<text class="li" x="{lx+21}" y="{y+1}">{note}</text>')
        y += 15
    a(f'<text class="li" x="{lx}" y="{y+4}">Long lap 6.3 km via the bridge + Wangan · '
      f'780 m</text>')
    a(f'<text class="li" x="{lx}" y="{y+16}">drag strip · hillclimb to the pass '
      f'(+300 m, 8 %).</text>')
    y += 36

    y = head("Landmarks", y)
    for (n, lab, _x, _y, kind) in PINS:
        col = {"asset": "#7A1F0B", "kit": "#6B4A1E"}.get(kind, "#3f3d36")
        a(f'<circle cx="{lx+7}" cy="{y-3}" r="7" fill="{col}"/>')
        a(f'<text class="pin" x="{lx+7}" y="{y}" text-anchor="middle">{n}</text>')
        a(f'<text class="li" x="{lx+21}" y="{y+1}">{lab}</text>')
        y += 14.6
    y += 6
    a(f'<circle cx="{lx+7}" cy="{y-3}" r="6" fill="#7A1F0B"/>')
    a(f'<text class="li" x="{lx+19}" y="{y+1}">hand-modelled hero asset '
      f'(3 already exist)</text>')
    y += 15
    a(f'<circle cx="{lx+7}" cy="{y-3}" r="6" fill="#6B4A1E"/>')
    a(f'<text class="li" x="{lx+19}" y="{y+1}">assembled from the shared kit + '
      f'Geometry Nodes</text>')
    y += 24

    y = head("Budget", y)
    for (k, v) in (("building instances", "~3,280 (GTA III ~3-4 k)"),
                   ("unique building meshes", "~112 (52 kit + 60 hero)"),
                   ("PLATEAU road footprints", "244,452 -> ~900 edges"),
                   ("PLATEAU building meshes", "0 shipped")):
        a(f'<text class="lm" x="{lx}" y="{y}">{k}</text>')
        a(f'<text class="li" x="{lx+LEGW-40}" y="{y}" text-anchor="end">{v}</text>')
        y += 15

    a('</svg>')
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tokyo-bay-island-overview-v2.svg")
    args = ap.parse_args()
    with open(args.out, "w") as f:
        f.write(build())
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
