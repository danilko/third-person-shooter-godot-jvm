"""The island's rail network as a 2-D PLAN, for review before anything is built (PLAN.md 3.25).

    python3 tools/island_rail_plan.py [--base <district plan png>] [--out <png>]

Draws the draft stations and lines over the district plan (`tools/island_region_map.py`'s picture, which is in the
same projection: the 4 608 m world square, north up, +x east, +z south). The stations and lines below are DRAFT
DATA -- positions read off the district plan by hand and meant to be argued with; once the user approves the layout
they seed the rail record (a Road Kit `rail` network, 3.25) and this file stops being the owner.

A line's `form` per stretch follows the study in 3.25: ELEVATED through the core, AT GRADE (with level crossings at
block streets) in the residential districts, the suburb and the farm, and a VIADUCT over water. The drawing shows
the form by line style so the review can argue about it too.
"""
import argparse
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
BASE = os.path.join(ROOT, "assets/world_source/reference/island_districts_2026-09-21.png")
OUT = os.path.join(ROOT, "assets/world_source/reference/rail_plan_draft_2026-09-21.png")
HALF = 2304.0

# name: (x, z Godot world metres, class, note). Class: hub / junction / standard / small.
STATIONS = {
    "Central":           (704.0, -305.0, "hub", "the Tokyo Station site; the forecourt rotary (3.23)"),
    "Residential North": (757.0, -823.0, "standard", ""),
    "Farm":              (1185.0, -1218.0, "small", "terminus"),
    "West Junction":     (-66.0, 197.0, "junction", "city-edge split: to Residential, and to Industry / SW Junction"),
    "South-West Junction": (-527.0, 690.0, "junction", "the residential/industry split: to Residential and Harbour"),
    "Residential":       (-757.0, 427.0, "standard", "the castle spur starts here"),
    "Harbour":           (-329.0, 1086.0, "standard", ""),
    "Industry":          (-250.0, 470.0, "standard", ""),
    "Castle":            (-461.0, 0.0, "small", "terminus, at the mountain's foot by Shuri Castle"),
    "Suburb / Bay":      (1316.0, 427.0, "standard", "the 'sub-harbour' shore (3.18(h)/(t))"),
    "Airport":           (1481.0, 1727.0, "standard", "terminus"),
}

# line: (colour, [(x, z) waypoints, station names as strings], [form per segment])
# Waypoints between stations are only there to keep the drawing on land and near the roads; the real alignment
# comes from the Road Kit rail network (radius >= ~160 m, grade <= 3.5%).
LINES = {
    "North line": ((230, 90, 90), ["Central", (760.0, -560.0), "Residential North", (1000.0, -1000.0), "Farm"],
                   ["elevated", "elevated", "grade", "grade"]),
    "West line": ((60, 150, 230), ["Central", (560.0, 130.0), (200.0, 190.0), "West Junction"],
                  ["elevated", "elevated", "grade"]),
    "South-west triangle": ((40, 180, 120), ["West Junction", (-400.0, 250.0), "Residential", "South-West Junction",
                                             "Industry", "West Junction"],
                            ["grade", "grade", "grade", "grade", "grade"]),
    "Harbour branch": ((30, 150, 150), ["South-West Junction", (-420.0, 900.0), "Harbour"], ["grade", "grade"]),
    "Castle spur": ((200, 150, 60), ["Residential", (-560.0, 200.0), "Castle"], ["grade", "grade"]),
    "South line": ((180, 90, 220), ["Central", (1000.0, 160.0), "Suburb / Bay", (1700.0, 560.0),
                                    (1760.0, 1000.0), (1760.0, 1500.0), "Airport"],
                   ["elevated", "grade", "grade", "viaduct", "viaduct", "grade"]),
}

STATION_R = {"hub": 16, "junction": 13, "standard": 9, "small": 7}


def pt(p, px):
    x, z = STATIONS[p][:2] if isinstance(p, str) else p
    return ((x + HALF) / (2 * HALF) * px, (z + HALF) / (2 * HALF) * px)


def dashed(d, a, b, colour, width, dash, gap):
    (x0, y0), (x1, y1) = a, b
    length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    if length == 0:
        return
    t = 0.0
    while t < length:
        u0, u1 = t / length, min(1.0, (t + dash) / length)
        d.line([(x0 + (x1 - x0) * u0, y0 + (y1 - y0) * u0), (x0 + (x1 - x0) * u1, y0 + (y1 - y0) * u1)],
               fill=colour, width=width)
        t += dash + gap


# The ALTERNATIVE the review compares against (PLAN.md 3.25): ONE junction instead of two. West Junction becomes an
# ordinary through station; the trunk runs West Junction -> Industry -> South-West Junction, which splits to
# Residential (and on to the castle) and to Harbour. Through trains Central -> Residential and Central -> Harbour.
VARIANT_Y = {
    "West line": ((60, 150, 230), ["Central", (560.0, 130.0), (200.0, 190.0), "West Junction", "Industry",
                                   "South-West Junction"], ["elevated", "elevated", "grade", "grade", "grade"]),
    "Residential branch": ((40, 180, 120), ["South-West Junction", "Residential"], ["grade"]),
    "Harbour branch": ((30, 150, 150), ["South-West Junction", (-420.0, 900.0), "Harbour"], ["grade", "grade"]),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--variant", choices=("triangle", "y"), default="triangle")
    a = ap.parse_args()
    if a.variant == "y":
        for k in ("West line", "South-west triangle", "Harbour branch"):
            LINES.pop(k, None)
        LINES.update(VARIANT_Y)
        STATIONS["West Junction"] = STATIONS["West Junction"][:2] + ("standard", "an ordinary through station")
    img = Image.open(a.base).convert("RGB")
    px = img.size[0]
    d = ImageDraw.Draw(img, "RGBA")
    try:
        font = ImageFont.truetype(os.path.join(ROOT, "assets/ui/Aldrich-Regular.ttf"), 15)
        small = ImageFont.truetype(os.path.join(ROOT, "assets/ui/Aldrich-Regular.ttf"), 12)
    except OSError:
        font = small = ImageFont.load_default()

    for name, (col, pts, forms) in LINES.items():
        for (p, q), form in zip(zip(pts, pts[1:]), forms):
            a0, b0 = pt(p, px), pt(q, px)
            if form == "elevated":
                d.line([a0, b0], fill=(255, 255, 255, 230), width=11)
                d.line([a0, b0], fill=col + (255,), width=7)
            elif form == "viaduct":
                dashed(d, a0, b0, col + (255,), 7, 14, 7)
            else:
                d.line([a0, b0], fill=col + (255,), width=6)
                # the level-crossing hint: small ticks across an at-grade stretch
                dashed(d, a0, b0, (255, 255, 255, 200), 2, 2, 22)

    for name, (x, z, cls, note) in STATIONS.items():
        cx, cy = pt(name, px)
        r = STATION_R[cls]
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 255), outline=(20, 20, 20, 255), width=3)
        if cls in ("hub", "junction"):
            d.ellipse([cx - r / 2, cy - r / 2, cx + r / 2, cy + r / 2], fill=(20, 20, 20, 255))
        d.text((cx + r + 5, cy - 9), name, fill=(255, 255, 255, 255), font=font, stroke_width=3,
               stroke_fill=(0, 0, 0, 255))

    # legend
    lx, ly = 20, 40
    d.rectangle([lx - 8, ly - 8, lx + 420, ly + 22 * (len(LINES) + 6)], fill=(10, 20, 30, 215))
    d.text((lx, ly), "RAIL PLAN -- DRAFT FOR REVIEW (PLAN.md 3.25)", fill=(255, 255, 255), font=font)
    ly += 26
    for name, (col, _pts, _f) in LINES.items():
        d.line([(lx, ly + 8), (lx + 40, ly + 8)], fill=col, width=6)
        d.text((lx + 50, ly), name, fill=(255, 255, 255), font=small)
        ly += 20
    ly += 4
    d.line([(lx, ly + 8), (lx + 40, ly + 8)], fill=(255, 255, 255), width=11)
    d.line([(lx, ly + 8), (lx + 40, ly + 8)], fill=(120, 120, 120), width=7)
    d.text((lx + 50, ly), "elevated (the core)", fill=(255, 255, 255), font=small)
    ly += 20
    d.line([(lx, ly + 8), (lx + 40, ly + 8)], fill=(120, 120, 120), width=6)
    dashed(d, (lx, ly + 8), (lx + 40, ly + 8), (255, 255, 255, 200), 2, 2, 12)
    d.text((lx + 50, ly), "at grade, level crossings at block streets", fill=(255, 255, 255), font=small)
    ly += 20
    dashed(d, (lx, ly + 8), (lx + 40, ly + 8), (120, 120, 120), 7, 12, 6)
    d.text((lx + 50, ly), "viaduct over water", fill=(255, 255, 255), font=small)
    ly += 20
    d.text((lx, ly), "big dot = hub / junction (cross-platform change); all double track", fill=(255, 255, 255), font=small)
    img.save(a.out)
    print("island_rail_plan: %d stations, %d lines -> %s" % (len(STATIONS), len(LINES), a.out))


if __name__ == "__main__":
    main()
