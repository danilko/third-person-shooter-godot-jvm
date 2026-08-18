#!/usr/bin/env python3
"""Tokyo-Bay island plate v2 — the 3024 m map plate.

Draws `tokyo-bay-island-modeling-plate-v2.svg` from geometry authored in GAME METRES
(X = east, Y = north, centre origin, world spans [-1512, +1512]) — i.e. exactly
`blender/lib/world_grid.py`'s convention at GRID_N = 6, DISTRICT = 504 m.

    python3 tools/island_plate_v2.py --out tokyo-bay-island-modeling-plate-v2.svg

Companion spec: tokyo-bay-island-design-spec-v2.md
Layout source: real Tokyo topology (Project PLATEAU, MLIT, CC BY 4.0), decimated.
"""

from __future__ import annotations

import argparse
import math
import random

# --------------------------------------------------------------------------- grid
DISTRICT = 504.0
GRID_N = 6
WORLD = DISTRICT * GRID_N          # 3024
ORIGIN = WORLD / 2.0               # 1512

S = 0.335                          # px per metre
MX, MY = 58.0, 54.0
W = int(WORLD * S + MX * 2)
H = int(WORLD * S + MY + 250)


def px(x, y):
    return (MX + (x + ORIGIN) * S, MY + (ORIGIN - y) * S)


def path(pts, close=True):
    d = "M" + " L".join(f"{a:.1f} {b:.1f}" for a, b in (px(*p) for p in pts))
    return d + (" Z" if close else "")


def plen(pts, close=False):
    q = pts + [pts[0]] if close else pts
    return sum(math.dist(a, b) for a, b in zip(q, q[1:]))


# --------------------------------------------------------------------------- land
# Main island: organic north/west coast (natural), straight south-east (reclaimed).
# Sized to leave only a ~120-200 m sea margin — the water is the boundary, not filler.
MAIN = [
    (-60, 1478), (330, 1440), (700, 1340), (1000, 1180), (1210, 950), (1330, 690),
    (1380, 420), (1350, 170), (1250, -30), (1120, -170), (980, -260), (800, -330),
    (600, -390), (400, -440), (200, -560), (-40, -680), (-320, -740), (-600, -730),
    (-840, -620), (-1030, -480), (-1210, -360), (-1350, -170), (-1428, 110),
    (-1430, 430), (-1350, 760), (-1190, 1050), (-950, 1270), (-660, 1410),
    (-360, 1470),
]
HARBOUR = [(-620, -728), (180, -690), (180, -1080), (-190, -1150), (-620, -1030)]
SHIBAURA = [(230, -430), (470, -430), (470, -690), (230, -650)]
ODAIBA = [(430, -880), (960, -880), (1030, -950), (1030, -1180), (430, -1180)]
AIRPORT = [(600, -1250), (1470, -1250), (1470, -1500), (600, -1500)]

LAND = [MAIN, HARBOUR, SHIBAURA, ODAIBA, AIRPORT]


def inside(poly, x, y):
    n, ins = len(poly), False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            ins = not ins
        j = i
    return ins


def on_land(x, y):
    return any(inside(p, x, y) for p in LAND)


def pull_ashore(cx, cy, pts, inset=26.0):
    """Shrink each point toward the centre until it sits on land — clips a contour
    band to the coastline without a real polygon-clip library."""
    out = []
    for (x, y) in pts:
        for k in range(40):
            t = 1.0 - k * 0.025
            qx, qy = cx + (x - cx) * t, cy + (y - cy) * t
            if on_land(qx, qy):
                out.append((cx + (x - cx) * max(0.0, t - inset / 1000.0),
                            cy + (y - cy) * max(0.0, t - inset / 1000.0)))
                break
        else:
            out.append((cx, cy))
    return out


def ellipse(cx, cy, rx, ry, n=40, rot=0.0):
    out = []
    c, s = math.cos(rot), math.sin(rot)
    for k in range(n):
        a = 2 * math.pi * k / n
        ex, ey = rx * math.cos(a), ry * math.sin(a)
        out.append((cx + ex * c - ey * s, cy + ex * s + ey * c))
    return out


# ------------------------------------------------------------------- green voids
PALACE = [(-190, 250), (-120, 275), (300, 262), (345, 190), (340, -130),
          (255, -175), (-120, -165), (-190, -100)]
MOAT = [(-232, 272), (-132, 318), (322, 302), (388, 212), (382, -152),
        (280, -218), (-140, -206), (-236, -120)]
MEIJI = [(-790, 300), (-570, 335), (-505, 495), (-635, 590), (-825, 528)]
UENO_PK = [(400, 700), (615, 712), (635, 872), (432, 880)]
SHIBA_PK = [(75, -545), (275, -535), (280, -410), (80, -415)]
PARKS = (MOAT, MEIJI, UENO_PK, SHIBA_PK)

# --------------------------------------------------------------------------- T1
def chamfer(x0, y0, x1, y1, c):
    return [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1),
            (x0 + c, y1), (x0, y1 - c), (x0, y0 + c)]


C1 = chamfer(-410, -380, 600, 500, 130)          # Inner Circular, closed
WANGAN = [(560, -300), (470, -420), (350, -455), (505, -885), (660, -965),
          (880, -1010), (1030, -1035), (1140, -1150), (1230, -1258), (1090, -1330)]
R4 = [(-410, 220), (-560, 262), (-720, 300), (-870, 350), (-1010, 480),
      (-1130, 620), (-1196, 736)]
R5 = [(150, 500), (280, 640), (430, 770), (530, 920), (580, 1060)]
R1 = [(-180, -380), (-280, -510), (-370, -640), (-430, -800), (-455, -950)]
TOUGE = [(-1240, 812), (-1050, 852), (-1170, 922), (-1000, 962), (-1120, 1022),
         (-985, 1062), (-1070, 1118)]

# --------------------------------------------------------------------------- rail
YAMANOTE = [(392, -62), (620, 130), (700, 300), (610, 545), (470, 700), (180, 830),
            (-180, 810), (-520, 700), (-760, 470), (-812, 336), (-800, 90),
            (-660, -90), (-545, -168), (-430, -330), (-230, -450), (-40, -520),
            (200, -450), (330, -320)]
CHUO = [(392, -62), (60, 60), (-300, 190), (-620, 300), (-812, 336), (-1010, 500),
        (-1180, 700), (-1240, 812)]
SHINKANSEN = [(392, -80), (200, -350), (20, -580), (-190, -720)]
YURIKAMOME = [(320, -420), (490, -872), (680, -960), (900, -1000)]
MONORAIL = [(960, -1020), (1130, -1160), (1220, -1262), (1050, -1350)]

# --------------------------------------------------------------------------- river
RIVER = [(-880, 1030), (-640, 880), (-330, 812), (60, 790), (420, 748), (700, 630),
         (870, 430), (930, 180), (912, -60), (846, -250), (770, -400)]

# ----------------------------------------------------------------------- landmark
# (label, x, y, kind, dx, dy, anchor)
LANDMARKS = [
    ("Tokyo Tower", 185, -470, "asset", 8, -6, "start"),
    ("Zojo-ji / Shiba park", 115, -498, "kit", -8, 12, "end"),
    ("Imperial Palace", 60, 45, "kit", 8, 3, "start"),
    ("Tokyo Station", 392, -62, "kit", 8, 3, "start"),
    ("Akihabara", 700, 300, "kit", 8, 3, "start"),
    ("Ginza", 500, -270, "", 8, 3, "start"),
    ("Ueno", 500, 715, "", 8, 3, "start"),
    ("Shinjuku / Kabukicho", -812, 336, "kit", -8, 3, "end"),
    ("Shibuya scramble", -545, -168, "kit", -8, 3, "end"),
    ("Meiji shrine", -665, 440, "kit", -8, 3, "end"),
    ("Odaiba", 700, -1050, "", 8, 3, "start"),
    ("Haneda terminal", 1300, -1400, "asset", -8, 3, "end"),
    ("Keihin industry", -410, -900, "", 8, 3, "start"),
    ("Pass shrine (touge)", -1070, 1118, "kit", 8, -4, "start"),
]

# ------------------------------------------------------------------ urban blocks
# name, rects, frontage, depth, perimeter retention, interior fill, colour
ZONES = [
    ("core",  [(180, -400, 1010, 560)],                  6, 12, 0.90, 0.30, "#8b8577"),
    ("core",  [(-1010, 150, -430, 560)],                 7, 13, 0.80, 0.18, "#8b8577"),
    ("core",  [(-820, -320, -320, 110)],                 7, 13, 0.72, 0.14, "#8b8577"),
    ("resid", [(-1400, -700, -260, 640), (-260, 640, 400, 1000),
               (1010, -180, 1330, 620)],                 8,  9, 0.30, 0.00, "#b0ab99"),
    ("indus", [(-620, -1150, 180, -690)],               34, 46, 0.34, 0.00, "#9d9686"),
    ("indus", [(230, -690, 470, -430)],                 30, 40, 0.30, 0.00, "#9d9686"),
    ("water", [(430, -1180, 1030, -880)],               22, 30, 0.20, 0.00, "#9d9686"),
    ("rural", [(-500, 660, 1150, 1300)],                14, 11, 0.05, 0.00, "#a9af92"),
]

BLOCK = 168.0
STREET = 14.0


def in_void(x, y):
    for p in PARKS:
        if inside(p, x, y):
            return True
    for pl in (C1 + [C1[0]], WANGAN, R4, R5, R1):
        for a, b in zip(pl, pl[1:]):
            if seg_dist(x, y, a, b) < 24:
                return True
    for a, b in zip(RIVER, RIVER[1:]):
        if seg_dist(x, y, a, b) < 34:
            return True
    return False


def seg_dist(px_, py_, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    if L == 0:
        return math.hypot(px_ - ax, py_ - ay)
    t = max(0.0, min(1.0, ((px_ - ax) * dx + (py_ - ay) * dy) / L))
    return math.hypot(px_ - (ax + t * dx), py_ - (ay + t * dy))


def ok(cx, cy, x0, y0, x1, y1):
    return (x0 <= cx <= x1 and y0 <= cy <= y1 and on_land(cx, cy)
            and not in_void(cx, cy))


def block_buildings(out, gx, gy, rect, spec, rng):
    x0, y0, x1, y1 = rect
    _, _, frontage, depth, keep, infill, col = spec
    ix0, iy0 = gx + STREET / 2, gy + STREET / 2
    ix1, iy1 = gx + BLOCK - STREET / 2, gy + BLOCK - STREET / 2

    for b in (iy0, iy1 - depth):                       # south & north frontage
        t = ix0
        while t + frontage <= ix1:
            w = frontage * rng.uniform(0.75, 1.55)
            w = min(w, ix1 - t)
            if ok(t + w / 2, b + depth / 2, *rect) and rng.random() < keep:
                out.append((t, b, w, depth, col))
            t += w + rng.uniform(0.0, frontage * 0.2)
    for b in (ix0, ix1 - depth):                       # west & east frontage
        t = iy0 + depth
        while t + frontage <= iy1 - depth:
            w = frontage * rng.uniform(0.75, 1.55)
            w = min(w, iy1 - depth - t)
            if ok(b + depth / 2, t + w / 2, *rect) and rng.random() < keep:
                out.append((b, t, depth, w, col))
            t += w + rng.uniform(0.0, frontage * 0.2)
    if infill <= 0:
        return
    u = ix0 + depth + 3                                # solid interior (zero setback)
    while u + depth < ix1 - depth:
        v = iy0 + depth + 3
        while v + frontage < iy1 - depth:
            w = frontage * rng.uniform(0.8, 1.4)
            if ok(u + depth / 2, v + w / 2, *rect) and rng.random() < infill:
                out.append((u, v, depth, w, col))
            v += w + 2.5
        u += depth + 3.5


def scatter(spec):
    out = []
    for rect in spec[1]:
        x0, y0, x1, y1 = rect
        bx = math.floor(x0 / BLOCK) * BLOCK
        while bx < x1:
            by = math.floor(y0 / BLOCK) * BLOCK
            while by < y1:
                block_buildings(out, bx, by, rect, spec,
                                random.Random((int(bx) * 733 + int(by) * 17) & 0xffff))
                by += BLOCK
            bx += BLOCK
    return out


# --------------------------------------------------------------------- clipping
def clipped(pts, step=10.0):
    runs, cur = [], []
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(math.dist(a, b) / step))
        for i in range(n + 1):
            t = i / n
            p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            if on_land(*p):
                cur.append(p)
            elif cur:
                runs.append(cur)
                cur = []
    if cur:
        runs.append(cur)
    return [r for r in runs if len(r) > 1]


def arterials():
    out, rng = [], random.Random(7)
    for i in range(1, GRID_N):
        base = -ORIGIN + i * DISTRICT
        v, h = [], []
        for k in range(GRID_N + 1):
            t = -ORIGIN + k * DISTRICT
            j = 0 if k % 2 else rng.choice((-52.0, -30.0, 30.0, 52.0))
            v.append((base + j, t))
            h.append((t, base + j))
        out += [v, h]
    return out


def locals_():
    out = []
    for z in ZONES:
        if z[0] not in ("core", "resid", "indus", "water"):
            continue
        for (x0, y0, x1, y1) in z[1]:
            v = math.ceil(x0 / BLOCK) * BLOCK
            while v < x1:
                out.append([(v, y0), (v, y1)])
                v += BLOCK
            v = math.ceil(y0 / BLOCK) * BLOCK
            while v < y1:
                out.append([(x0, v), (x1, v)])
                v += BLOCK
    return out


# ------------------------------------------------------------------------ render
def build():
    o = []
    a = o.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
      f'viewBox="0 0 {W} {H}" font-family="sans-serif">')
    a('<style>'
      '.t{font:700 12px sans-serif;fill:#23231f}'
      '.s{font:400 9px sans-serif;fill:#6a685e}'
      '.r{font:600 8.5px sans-serif}'
      '.hero{font:700 9px sans-serif;fill:#B23A18}'
      '.z{font:700 12.5px sans-serif;fill:#23231f}'
      '.zs{font:400 8.5px sans-serif;fill:#5f5d54}'
      '.g{font:600 8px sans-serif;fill:#7d7a6c}'
      '.w{font:500 9px sans-serif;fill:#3f6379}'
      '</style>')
    a(f'<rect width="{W}" height="{H}" fill="#EBE6D8"/>')
    a(f'<rect x="{MX:.0f}" y="{MY:.0f}" width="{WORLD*S:.0f}" height="{WORLD*S:.0f}" '
      f'fill="#9EB8C6"/>')

    for i in range(31):                                        # 100.8 m minor grid
        v = -ORIGIN + i * 100.8
        x, _ = px(v, 0)
        _, y = px(0, v)
        a(f'<line x1="{x:.1f}" y1="{MY}" x2="{x:.1f}" y2="{MY+WORLD*S:.0f}" '
          f'stroke="#0000000e"/>')
        a(f'<line x1="{MX}" y1="{y:.1f}" x2="{MX+WORLD*S:.0f}" y2="{y:.1f}" '
          f'stroke="#0000000e"/>')

    a(f'<path d="{path(MAIN)}" fill="#E5E0CF" stroke="#5D7E90" stroke-width="1.7"/>')
    for p in (HARBOUR, SHIBAURA, ODAIBA, AIRPORT):
        a(f'<path d="{path(p)}" fill="#E0DAC7" stroke="#5D7E90" stroke-width="1.5"/>')

    # terrain bands, clipped to the coast
    for (rx, ry, col) in ((700, 545, "#BDCDA4"), (505, 390, "#A6BE8B"),
                          (325, 245, "#8FAE74"), (185, 138, "#E7ECE0")):
        cx, cy = -900, 1000
        pts = pull_ashore(cx, cy, ellipse(cx, cy, rx, ry, 44, math.radians(-12)))
        a(f'<path d="{path(pts)}" fill="{col}" fill-opacity="0.95" stroke="#798a64" '
          f'stroke-width="0.8"/>')
    for (lab, x, y) in (("+120 m", -520, 700), ("+240 m", -640, 790),
                        ("+360 m", -760, 880), ("snow +420", -890, 1130)):
        sx, sy = px(x, y)
        a(f'<text class="s" x="{sx:.0f}" y="{sy:.0f}" text-anchor="middle" '
          f'fill="#7c8a68">{lab}</text>')
    sx, sy = px(-900, 1010)
    a(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="3" fill="#5d5a4e"/>')
    a(f'<text class="s" x="{sx+7:.0f}" y="{sy-4:.0f}">summit +520 · scenery only</text>')

    # rural paddy wash, clipped
    pts = pull_ashore(330, 960, ellipse(330, 960, 940, 370, 44))
    a(f'<path d="{path(pts)}" fill="#CBD8AE" fill-opacity="0.5" stroke="none"/>')

    for p, col in ((MOAT, "#7FA3B8"), (PALACE, "#B4C79A"), (MEIJI, "#9CB681"),
                   (UENO_PK, "#A6BD8A"), (SHIBA_PK, "#A6BD8A")):
        a(f'<path d="{path(p)}" fill="{col}" stroke="#7d8a6b" stroke-width="0.8"/>')

    a(f'<path d="{path(RIVER, False)}" fill="none" stroke="#7FA3B8" '
      f'stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')

    total = 0
    for z in ZONES:
        out = scatter(z)
        total += len(out)
        for (x, y, w, h, col) in out:
            bx, by = px(x, y + h)
            a(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{max(w*S,0.7):.1f}" '
              f'height="{max(h*S,0.7):.1f}" fill="{col}" fill-opacity="0.92"/>')

    for ln in locals_():                                       # T3
        for run in clipped(ln, 14):
            a(f'<path d="{path(run, False)}" fill="none" stroke="#F1EDE1" '
              f'stroke-width="{14*S:.1f}" stroke-opacity="0.8"/>')

    for ln in arterials():                                     # T2
        for run in clipped(ln, 12):
            a(f'<path d="{path(run, False)}" fill="none" stroke="#FCFAF3" '
              f'stroke-width="{27*S:.1f}" stroke-linecap="round"/>')
            a(f'<path d="{path(run, False)}" fill="none" stroke="#B9B29C" '
              f'stroke-width="0.6" stroke-dasharray="5 5" stroke-opacity="0.7"/>')

    for pl, closed in ((YAMANOTE, True), (CHUO, False), (SHINKANSEN, False),
                       (YURIKAMOME, False), (MONORAIL, False)):
        q = pl + [pl[0]] if closed else pl
        a(f'<path d="{path(q, False)}" fill="none" stroke="#38614F" stroke-width="1.6" '
          f'stroke-dasharray="8 4" stroke-linejoin="round"/>')

    for pl, closed in ((C1, True), (WANGAN, False), (R4, False), (R5, False),
                       (R1, False)):
        q = pl + [pl[0]] if closed else pl
        a(f'<path d="{path(q, False)}" fill="none" stroke="#8a5320" '
          f'stroke-width="{22*S+2.2:.1f}" stroke-linejoin="round" '
          f'stroke-linecap="round" stroke-opacity="0.5"/>')
        a(f'<path d="{path(q, False)}" fill="none" stroke="#EE9B4E" '
          f'stroke-width="{22*S:.1f}" stroke-linejoin="round" stroke-linecap="round"/>')

    a(f'<path d="{path(TOUGE, False)}" fill="none" stroke="#6f6a58" '
      f'stroke-width="4.4" stroke-linejoin="round" stroke-linecap="round"/>')
    a(f'<path d="{path(TOUGE, False)}" fill="none" stroke="#FCFAF3" '
      f'stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>')

    for (p0, p1, lab, span, up) in (
            ((350, -455), (505, -885), "Rainbow Bridge · road+rail · 460 m", 460, True),
            ((1030, -1035), (1230, -1258), "Wangan viaduct · 300 m", 300, False)):
        x0, y0 = px(*p0)
        x1, y1 = px(*p1)
        a(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
          f'stroke="#B23A18" stroke-width="5" stroke-linecap="round"/>')
        mxp, myp = (x0 + x1) / 2, (y0 + y1) / 2
        a(f'<circle cx="{mxp:.1f}" cy="{myp:.1f}" r="4.2" fill="#EBE6D8" '
          f'stroke="#B23A18" stroke-width="2"/>')
        if up:
            a(f'<text class="hero" x="{mxp-10:.0f}" y="{myp-6:.0f}" '
              f'text-anchor="end">{lab}</text>')
        else:
            a(f'<text class="hero" x="{mxp+10:.0f}" y="{myp+12:.0f}">{lab}</text>')

    r0, r1 = (660, -1470), (1420, -1300)
    x0, y0 = px(*r0)
    x1, y1 = px(*r1)
    a(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
      f'stroke="#F5F2E8" stroke-width="{60*S:.1f}"/>')
    a(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
      f'stroke="#C9A24A" stroke-width="1" stroke-dasharray="7 7"/>')
    a(f'<text class="s" x="{(x0+x1)/2:.0f}" y="{(y0+y1)/2+17:.0f}" '
      f'text-anchor="middle">runway 780 x 60 m · drag strip</text>')

    for i in range(GRID_N + 1):                                # district seams
        v = -ORIGIN + i * DISTRICT
        x, _ = px(v, 0)
        _, y = px(0, v)
        a(f'<line x1="{x:.1f}" y1="{MY}" x2="{x:.1f}" y2="{MY+WORLD*S:.0f}" '
          f'stroke="#00000030" stroke-width="1"/>')
        a(f'<line x1="{MX}" y1="{y:.1f}" x2="{MX+WORLD*S:.0f}" y2="{y:.1f}" '
          f'stroke="#00000030" stroke-width="1"/>')
    for gx in range(GRID_N):
        for gy in range(GRID_N):
            sx, sy = px(-ORIGIN + (gx + .5) * DISTRICT, -ORIGIN + (gy + .5) * DISTRICT)
            a(f'<text class="g" x="{sx:.0f}" y="{sy:.0f}" text-anchor="middle" '
              f'opacity="0.42">{gx}{gy}</text>')

    for (lab, sub, x, y, anc) in (
            ("MOUNTAIN / TOUGE", "annexed 1:1 slope · pass +300", -880, 1240, "middle"),
            ("RURAL VALLEY", "paddies · river spine · Z +30", 480, 1230, "middle"),
            ("RESIDENTIAL", "danchi + detached · west plateau", -1080, -240, "middle"),
            ("NEON CORE", "zakkyo 6x12 m · zero setback", 760, 640, "middle"),
            ("HARBOUR / KEIHIN", "reclaimed", -270, -1110, "middle"),
            ("ODAIBA", "waterfront", 730, -930, "middle"),
            ("AIRPORT ISLAND", "reclaimed", 1000, -1290, "middle")):
        sx, sy = px(x, y)
        a(f'<text class="z" x="{sx:.0f}" y="{sy:.0f}" text-anchor="{anc}">{lab}</text>')
        a(f'<text class="zs" x="{sx:.0f}" y="{sy+11:.0f}" '
          f'text-anchor="{anc}">{sub}</text>')
    for (lab, x, y) in (("BAY", 760, -560), ("OPEN SEA", -1290, -1150),
                        ("OPEN SEA", 1300, 1250)):
        sx, sy = px(x, y)
        a(f'<text class="w" x="{sx:.0f}" y="{sy:.0f}" text-anchor="middle" '
          f'letter-spacing="2">{lab}</text>')

    for (lab, x, y, kind, dx, dy, anc) in LANDMARKS:
        sx, sy = px(x, y)
        col = {"asset": "#B23A18", "kit": "#7A5A2E"}.get(kind, "#43413a")
        a(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="3.6" fill="{col}" stroke="#EBE6D8" '
          f'stroke-width="1"/>')
        a(f'<text class="r" x="{sx+dx:.0f}" y="{sy+dy:.0f}" text-anchor="{anc}" '
          f'fill="{col}">{lab}</text>')

    for (lab, x, y, note) in (
            ("S1", 60, 500, "Kanda straight"), ("S2", 600, 240, "Akiba esses"),
            ("S3", 470, -380, "Ginza / Shiodome hairpin"),
            ("S4", -180, -380, "Shiba sweep, tower on the left"),
            ("S5", -410, 120, "Yotsuya cutting, blind crest"),
            ("S6", -280, 500, "moat straight to start/finish")):
        sx, sy = px(x, y)
        a(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="7.5" fill="#B23A18"/>')
        a(f'<text x="{sx:.1f}" y="{sy+3:.1f}" text-anchor="middle" '
          f'font-size="8" font-weight="700" fill="#FFF">{lab}</text>')

    sx, sy = px(-1196, 736)
    a(f'<rect x="{sx-5:.1f}" y="{sy-5:.1f}" width="10" height="10" fill="#EBE6D8" '
      f'stroke="#B23A18" stroke-width="1.6"/>')
    a(f'<text class="hero" x="{sx+9:.0f}" y="{sy+14:.0f}">tunnel portal · '
      f'hides the Tier-B seam</text>')

    nx, ny = MX + WORLD * S - 24, MY + 32
    a(f'<path d="M{nx} {ny-20} L{nx+4.5} {ny-10} L{nx-4.5} {ny-10} Z" fill="#23231f"/>')
    a(f'<text class="s" x="{nx}" y="{ny+2}" text-anchor="middle">N</text>')
    by = MY + WORLD * S + 24
    a(f'<line x1="{MX}" y1="{by}" x2="{MX+504*S:.1f}" y2="{by}" stroke="#23231f" '
      f'stroke-width="2"/>')
    a(f'<text class="s" x="{MX+504*S+9:.0f}" y="{by+4:.0f}">504 m = 1 district '
      f'(minor grid 100.8 m)</text>')

    ly = MY + WORLD * S + 52
    lap = plen(C1, True)
    for i, (cls, txt) in enumerate([
        ("t", "World 3024 x 3024 m · 6 x 6 districts of 504 m · centre origin "
              "[-1512,+1512] — blender/lib/world_grid.py unchanged (GRID_N = 6)"),
        ("s", f"Land 5.57 km² of the 9.14 km² box (GTA III 4.38 · Vice City 5.62) · "
              f"buildings on this plate: {total} instances · "
              f"C1 flagship lap {lap:.0f} m · Wangan run {plen(WANGAN):.0f} m · "
              f"touge {plen(TOUGE):.0f} m"),
        ("s", "Roads  T1 expressway 22 m, elevated +12 m (orange) · T2 arterial 27 m on "
              "every 504 m district seam, doglegged (white) · T3 local 14 m @ 168 m · "
              "T4 alley 4.5 m @ 45-60 m (generated, not drawn)"),
        ("s", "Rail (dashed) Yamanote loop +8 m · Chuo to the mountain terminus · "
              "Shinkansen +13 m · Yurikamome on the bridge lower deck · Monorail to the "
              "airport — every viaduct doubles as a streaming occluder"),
        ("s", "Red = hero asset, hand-modelled from PLATEAU LOD2 · brown = landmark "
              "assembled from the shared kit + Geometry Nodes · black = named place, "
              "generic kit only"),
        ("s", "Z  sea 0 · reclaimed +4 · core +3..6 · west plateau +8..18 · valley +30 · "
              "flank +90..240 · pass +300 · summit +520 (snow line +420)"),
        ("s", "Layout source: real Tokyo topology — Project PLATEAU (MLIT), CC BY 4.0 — "
              "decimated to a road skeleton + block outlines + 8 landmark meshes. "
              "No PLATEAU building mesh ships in the game."),
    ]):
        a(f'<text class="{cls}" x="{MX}" y="{ly + i*15.5:.0f}">{txt}</text>')

    a('</svg>')
    return "\n".join(o), total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tokyo-bay-island-modeling-plate-v2.svg")
    args = ap.parse_args()
    svg, total = build()
    with open(args.out, "w") as f:
        f.write(svg)
    print(f"wrote {args.out}  buildings={total}")
    for lab, pl, cl in (("C1 lap", C1, True), ("Wangan", WANGAN, False),
                        ("R4 west", R4, False), ("R1 south", R1, False),
                        ("R5 north", R5, False), ("touge", TOUGE, False),
                        ("Yamanote", YAMANOTE, True), ("Chuo", CHUO, False)):
        print(f"  {lab:10s} {plen(pl, cl):6.0f} m")


if __name__ == "__main__":
    main()
