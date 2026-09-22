#!/usr/bin/env python3
"""island_plan_picture.py -- the island's 2D PLAN as one picture, drawn from what the game reads (PLAN.md 3.30).

    python3 tools/island_plan_picture.py [--out <png>] [--no-grid] [--title "..."]

* the land from `assets/world_source/terrain/island_natural.f32` (hill-shaded, 100 m contours, snow over 380 m);
* every road from the DERIVED record `IslandRoads.roads.json`, coloured by what it is (Wangan, Shuto, coastal ring,
  mountain road, arterial, block street);
* the building regions (`island_buildings.REGIONS`), the frozen sites (`IslandSites.json`) and the summit crest;
* the POSTAL grid (PLAN.md 3.26, `world.PostalGrid`): 24 x 24 cells of 192 m, x numbered across the top, y down the
  side -- the same code the minimap prints and `postal 12-7` in the console goes to, so a mark drawn on this picture
  can be named exactly.

Pure Python + PIL, no Godot: regenerate it after any layout run.
"""
import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import island_buildings as ib        # noqa: E402
import island_reshape as R           # noqa: E402

N = 2305
X0, X1, Y0, Y1 = -1700.0, 1700.0, -2050.0, 1950.0      # record frame window (y north = -Godot z)
S = 0.5                                                 # px per metre
HALF, CELL, CELLS = 2304.0, 192.0, 24                   # world.PostalGrid
COL = {"nightlife": (196, 64, 128), "downtown": (232, 96, 64), "city": (230, 150, 70), "industry": (150, 150, 165),
       "harbour": (110, 118, 140), "residential": (110, 176, 120), "residential_north": (120, 190, 130),
       "residential_west": (100, 170, 110), "suburb": (150, 196, 130), "farm": (206, 196, 118)}
STYLE = {"street": ((175, 175, 175), 2), "arterial": ((245, 245, 245), 4), "coast": ((120, 230, 220), 4),
         "touge": ((255, 120, 40), 3), "shuto": ((255, 170, 0), 5), "wangan": ((255, 60, 220), 6)}


def font(size, bold=False):
    for f in ("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans%s.ttf" % ("-Bold" if bold else ""),
              "/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if bold else "")):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def P(x, y):
    return ((x - X0) * S, (Y1 - y) * S)


def road_class(name, rd):
    if name.startswith("shuto_wangan"):
        return "wangan"
    if name.startswith("shuto_"):
        return "shuto"
    if name.startswith("shrine_touge"):
        return "touge"
    if name.startswith(("kaigan", "ring_")):
        return "coast"
    lanes = (rd.get("base") or {}).get("lanes_fwd") or 1
    return "arterial" if lanes >= 2 or rd.get("road_class") in ("arterial", "trunk") else "street"


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "assets/world_source/reference/island_plan_latest.png"))
    ap.add_argument("--no-grid", action="store_true")
    ap.add_argument("--title", default="ISLAND PLAN (derived) -- tools/island_plan_picture.py")
    a = ap.parse_args(argv)
    H = np.fromfile(os.path.join(ROOT, "assets/world_source/terrain/island_natural.f32"), "<f4").reshape(N, N)
    W, Hh = int((X1 - X0) * S), int((Y1 - Y0) * S)
    xs = X0 + (np.arange(W) + 0.5) / S
    ys = Y1 - (np.arange(Hh) + 0.5) / S
    I = np.clip(((xs + HALF) / 2).astype(int), 0, N - 1)
    J = np.clip(((-ys + HALF) / 2).astype(int), 0, N - 1)
    h = H[np.ix_(J, I)].astype(float)
    gz, gx = np.gradient(h)
    shade = np.clip(0.75 + 0.9 * (-gx * 0.7 + gz * 0.7) / 2.0, 0.35, 1.25)
    land = h > 0.35
    t = np.clip(h / 440, 0, 1)[..., None]
    base = np.array([70, 92, 72]) * (1 - t) + np.array([196, 188, 160]) * t
    base = base * shade[..., None]
    base[h > 380] = [235, 238, 242]
    d = np.clip(-h / 24, 0, 1)[..., None]
    sea = np.array([46, 96, 122]) * (1 - d) + np.array([26, 48, 78]) * d
    base[~land] = sea[~land]
    c = land & (np.floor(h / 100) != np.floor(np.roll(h, 1, 0) / 100))
    base[c] *= 0.7
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert("RGBA")
    F, FB, FT = font(14), font(18, True), font(26, True)
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    do = ImageDraw.Draw(ov)
    for r in ib.REGIONS:
        name, (x0, y0, x1, y1) = r[0], r[1]
        col = COL.get(name, (200, 200, 200))
        do.rectangle([P(x0, y1), P(x1, y0)], fill=col + (38,), outline=col + (160,), width=2)
    if not a.no_grid:
        for k in range(CELLS + 1):
            v = -HALF + k * CELL
            do.line([P(v, Y0), P(v, Y1)], fill=(255, 255, 255, 40), width=1)
            do.line([P(X0, -v), P(X1, -v)], fill=(255, 255, 255, 40), width=1)
    img = Image.alpha_composite(img, ov)
    dr = ImageDraw.Draw(img)
    for r in ib.REGIONS:
        name, (x0, _y0, _x1, y1) = r[0], r[1]
        q = P(x0, y1)
        dr.text((q[0] + 6, q[1] + 4), name.replace("_", " "), fill=COL.get(name, (220, 220, 220)), font=F)
    rec = json.load(open(os.path.join(ROOT, "assets/world_source/pieces/IslandRoads.roads.json")))
    pts = {p["uid"]: p for p in rec["points"]}
    layers = {k: [] for k in STYLE}
    for rd in rec["roads"]:
        line = [pts[u]["pos"] for u in rd["points"] if u in pts]
        if len(line) >= 2:
            layers[road_class(rd["name"], rd)].append(line)
    for k in ("street", "arterial", "coast", "touge", "shuto", "wangan"):
        col, w = STYLE[k]
        for line in layers[k]:
            dr.line([P(p[0], p[1]) for p in line], fill=col, width=w)
    A, B = R.crest()
    dr.line([P(A[0], -A[1]), P(B[0], -B[1])], fill=(160, 40, 40), width=5)
    for st in json.load(open(os.path.join(ROOT, "assets/world_source/buildings/IslandSites.json")))["sites"]:
        x, y = st["x"], st["y"]
        sx, sy = (st.get("size") or [60, 60])[:2]
        ang = math.radians(st.get("yaw", 0))
        ca, sa = math.cos(ang), math.sin(ang)
        cs = [(x + ca * u - sa * v, y + sa * u + ca * v) for u, v in
              ((-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2), (-sx / 2, sy / 2))]
        dr.polygon([P(*q) for q in cs], outline=(255, 255, 255), fill=(90, 40, 160))
        dr.text((P(x, y)[0] + 10, P(x, y)[1] + 6), st["id"].replace("_", " "), fill=(255, 255, 255), font=F)
    if not a.no_grid:
        # postal numbers: x across the top, y down the left side (Godot z grows south, so y 1 is the north row)
        for k in range(1, CELLS + 1):
            mid = -HALF + (k - 0.5) * CELL
            px = P(mid, 0)[0]
            if 0 < px < W:
                dr.text((px - 6, 4), str(k), fill=(255, 255, 160), font=FB)
            py = P(0, -mid)[1]
            if 0 < py < Hh:
                dr.text((W - 30, py - 9), str(k), fill=(255, 255, 160), font=FB)
    x0t, y0t = 10, Hh - 190
    dr.rectangle([x0t, y0t, 700, Hh - 10], fill=(0, 0, 0, 180))
    dr.text((x0t + 12, y0t + 8), a.title, fill=(255, 255, 255), font=FB)
    yy = y0t + 36
    for k, text in (("wangan", "Wangan (elevated)"), ("shuto", "Shuto C1 + airport spur + diamond (elevated)"),
                    ("coast", "coastal ring + NW coast road"), ("touge", "mountain road"),
                    ("arterial", "arterials / trunk"), ("street", "block streets / lanes")):
        col, w = STYLE[k]
        dr.line([(x0t + 12, yy + 9), (x0t + 62, yy + 9)], fill=col, width=w)
        dr.text((x0t + 72, yy), text, fill=(255, 255, 255), font=F)
        yy += 20
    dr.text((x0t + 12, yy + 4), "postal grid: x across the top, y down the right side (console: postal x-y)",
            fill=(255, 255, 160), font=F)
    img.convert("RGB").save(a.out)
    print("island_plan_picture: %s %dx%d" % (os.path.relpath(a.out, ROOT), W, Hh))


if __name__ == "__main__":
    main(sys.argv[1:])
