#!/usr/bin/env python3
"""Top-down 2D preview of the compressed 6 km Tokyo map.

    python3 tokyo6km_preview.py --out build/tokyo6km/preview.png --size 2400

Same contract as preview_png.py: writes a sidecar with metres_per_pixel + extent, so the
image drops onto a Blender plane at 1:1 and lines up with the layout.json coordinates.
"""

from __future__ import annotations

import argparse
import json
import math
import os

from PIL import Image, ImageDraw

import tokyo6km_layout as L
import tokyo6km_network as N

THEME_COL = {
    "city":     (46, 30, 62),
    "resid":    (38, 40, 46),
    "industry": (52, 42, 30),
    "harbor":   (16, 30, 48),
    "rural":    (30, 48, 32),
    "mtn":      (58, 54, 44),
    "snow":     (74, 78, 84),
    "void":     (8, 12, 20),
}
WATER = (18, 38, 66)
BG = (10, 10, 12)
ART = (128, 128, 136)
HWY = (232, 96, 72)
TOUGE_C = (250, 176, 64)
RAIL = (86, 214, 128)
SHINK = (150, 255, 180)
TXT = (232, 232, 236)
TENT = (255, 226, 96)


def make(out, size):
    img = Image.new("RGB", (size, size), BG)
    d = ImageDraw.Draw(img, "RGBA")
    mpp = L.WORLD / size            # metres per pixel

    def P(x, y):
        """game metres -> pixel (Y flipped: +Y north = up)."""
        return ((x + L.ORIGIN) / mpp, (L.ORIGIN - y) / mpp)

    def line(pts, col, w, closed=False):
        q = [P(*p) for p in pts]
        if closed:
            q.append(q[0])
        d.line(q, fill=col, width=max(1, int(w)), joint="curve")

    # --- district themes
    for gy in range(L.GRID_N):
        for gx in range(L.GRID_N):
            th = L.theme_at(gx, gy)
            x0, y0, x1, y1 = L.cell_bounds(gx, gy)
            a, b = P(x0, y1), P(x1, y0)
            d.rectangle([a, b], fill=THEME_COL.get(th, BG))

    # --- T3/T4 street texture: draw the actual local-street spacing per theme so the
    # density gradient (neon -> resid -> rural -> nothing) is visible, not just asserted.
    for gy in range(L.GRID_N):
        for gx in range(L.GRID_N):
            r = N.STREET_RULES.get(L.theme_at(gx, gy))
            if not r or not r["local_spacing_m"]:
                continue
            x0, y0, x1, y1 = L.cell_bounds(gx, gy)
            for sp, col in ((r["local_spacing_m"], (112, 112, 120, 190)),
                            (r["alley_spacing_m"], (84, 84, 92, 150))):
                if not sp:
                    continue
                n = int(L.DISTRICT // sp)
                for i in range(1, n + 1):
                    d.line([P(x0 + i * sp, y0), P(x0 + i * sp, y1)], fill=col, width=1)
                    d.line([P(x0, y0 + i * sp), P(x1, y0 + i * sp)], fill=col, width=1)

    lg = N.land()
    d.polygon([P(*p) for p in lg["bay"]["points"]], fill=WATER)
    line(lg["river"]["points"], WATER, lg["river"]["width_m"] / mpp)
    isl = lg["haneda_island"]
    d.rectangle([P(isl["min"][0], isl["max"][1]), P(isl["max"][0], isl["min"][1])],
                fill=(48, 50, 54))

    # mountain block hatch — reads as terrain, not a district
    mb = lg["mountain_block"]
    for i in range(0, 40):
        t = i / 40.0
        y = mb["min"][1] + t * (mb["max"][1] - mb["min"][1])
        d.line([P(mb["min"][0], y), P(mb["max"][0], y)], fill=(96, 90, 74, 110), width=1)

    # --- T2 arterial backbone (district seams)
    for a in N.arterials():
        line(a["points"], ART, max(1, N.ARTERIAL_W / mpp * 0.6))

    # --- rail
    for r in N.railways():
        col = SHINK if r["id"] == "SHINKANSEN" else RAIL
        line(r["points"], col, max(2, 9.0 / mpp), r.get("closed", False))

    # --- T1 expressway (drawn last, on top — it is the map's read)
    for h in N.highways():
        col = TOUGE_C if h["id"] == "TOUGE" else HWY
        w = max(2, (22.0 if h["tier"] == "T1" else 8.0) / mpp)
        line(h["points"], (0, 0, 0, 200), w + 3, h.get("closed", False))
        line(h["points"], col, w, h.get("closed", False))

    # --- runway
    rw = L.runway()
    line([rw["north_end"], rw["south_end"]], (210, 210, 215), max(2, rw["width_m"] / mpp))

    # --- tentpoles
    for t in L.tentpoles():
        x, y = P(*t["game_xy"])
        r = 7
        d.ellipse([x - r, y - r, x + r, y + r], fill=TENT, outline=(0, 0, 0), width=2)
        d.text((x + 11, y - 7), t["label"], fill=TXT)

    # --- grid labels
    for gx in range(L.GRID_N):
        px, _ = P(*L.cell_center(gx, 0))
        d.text((px - 8, size - 16), f"gx{gx}", fill=(120, 120, 128))
    for gy in range(L.GRID_N):
        _, py = P(*L.cell_center(0, gy))
        d.text((3, py - 6), f"gy{gy}", fill=(120, 120, 128))

    d.text((10, 10), f"Tokyo 23-ku compressed  {L.WORLD:.0f} x {L.WORLD:.0f} m  "
                     f"({L.GRID_N}x{L.GRID_N} x {L.DISTRICT:.0f} m districts)", fill=TXT)
    d.text((10, 26), "red = elevated expressway   amber = touge   green = rail   "
                     "grey = arterial backbone", fill=(170, 170, 176))
    d.text((10, 42), "Data: Project PLATEAU (MLIT), CC BY 4.0", fill=(120, 120, 128))

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    img.save(out)
    with open(os.path.splitext(out)[0] + ".json", "w") as fh:
        json.dump(dict(metres_per_pixel=mpp, extent_m=L.WORLD,
                       origin="centre", axes="X=east, Y=north"), fh, indent=1)
    return out, mpp


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="build/tokyo6km/preview.png")
    ap.add_argument("--size", type=int, default=2400)
    a = ap.parse_args()
    p, mpp = make(a.out, a.size)
    print(f"wrote {p}  ({mpp:.3f} m/px)")
