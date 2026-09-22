#!/usr/bin/env python3
"""island_region_map.py -- draw the island's DISTRICT PLAN as one picture (PLAN.md 3.18n / 3.6).

    python3 tools/island_region_map.py <heights.f32> [--out <png>] [--px 1400]

A top-down plan of what the world is ZONED as, so a region that is in the wrong place can be pointed at rather
than argued about from coordinates. Everything on it is DERIVED from what the game actually reads:

  * the land, from a Terrain3D height dump (`tools/godot/dump_height_grid.gd -- <out> -2304 -2304 2305 2305 2`);
  * the roads, from the built lanekits, so the streets shown are the streets that exist;
  * the region boxes, their names and their draw ORDER, from `island_buildings.REGIONS` -- including the
    first-match-wins rule, so a box hidden behind an earlier one is drawn hidden, which is what it is;
  * every building, coloured by the region the placement gave it (not by the box it sits in);
  * the landmarks and sites from World.tscn, by name.

Pure Python + PIL: no display, no Godot, so it can be regenerated in any session.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import island_buildings as ib                       # noqa: E402

HALF = 2304.0
COLOURS = {                                         # a district's plan colour, warm = busy, cool = quiet
    "nightlife":   (196, 64, 128),
    "downtown":    (232, 96, 64),
    "city":        (230, 150, 70),
    "industry":    (120, 120, 132),
    "harbour":     (86, 92, 108),
    "residential": (110, 176, 120),
    "suburb":      (150, 196, 130),
    "farm":        (206, 196, 118),
}
SEA = (28, 54, 82)
LAND = (44, 58, 52)
ROAD = (150, 155, 160)
MARK = (250, 240, 210)


def draw(heights, out, px):
    from PIL import Image, ImageDraw
    import numpy as np
    n2 = int(round(2 * HALF / 2.0)) + 1
    h = np.fromfile(heights, dtype="<f4").reshape(n2, n2)
    land = h > ib.LAND_Z
    img = Image.new("RGB", (px, px), SEA)
    # the land, downsampled to the picture
    small = np.array(Image.fromarray((land * 255).astype("uint8")).resize((px, px), Image.BILINEAR))
    base = np.zeros((px, px, 3), dtype="uint8")
    base[:] = SEA
    base[small > 110] = LAND
    img = Image.fromarray(base)
    d = ImageDraw.Draw(img, "RGBA")

    def to_px(gx, gz):
        return ((gx + HALF) / (2 * HALF) * px, (gz + HALF) / (2 * HALF) * px)

    # region boxes, in REGIONS order, so an earlier box covers a later one exactly as the rule does
    for r in ib.REGIONS:
        x0, y0, x1, y1 = r[1]                       # record frame -> godot: z = -y
        a = to_px(x0, -y1)
        b = to_px(x1, -y0)
        c = COLOURS.get(r[0], (200, 200, 200))
        d.rectangle([a, b], fill=c + (70,), outline=c + (220,), width=2)

    # the roads, from the built lanekits
    lanes = 0
    for f in sorted(os.listdir(ib.PIECES)):
        if not f.startswith("Roads_IslandRoads_") or not f.endswith(".lanekit.json"):
            continue
        doc = json.load(open(os.path.join(ib.PIECES, f)))
        for ln in doc.get("lanes", []):
            # A lanekit point is [x, HEIGHT, z] in GODOT axes -- already placed, no record->godot flip. Reading
            # it as a record (x, y) pair drew every road at z = -height, i.e. one line through the middle of
            # the picture, and the street-like pattern left on it was the BUILDINGS.
            pts = ln.get("points") or []
            if len(pts) < 2:
                continue
            lanes += 1
            d.line([to_px(q[0], q[2]) for q in pts], fill=ROAD + (150,), width=1)

    # every placed building, in its region's colour
    doc = json.load(open(ib.OUT))
    for bld in doc["buildings"]:
        c = COLOURS.get(bld.get("region"), (220, 220, 220))
        x, z = to_px(bld["pos"][0], bld["pos"][2])
        d.rectangle([x - 1, z - 1, x + 1, z + 1], fill=c + (255,))

    # region names, at each box's centre
    for r in ib.REGIONS:
        x0, y0, x1, y1 = r[1]
        cx, cz = to_px((x0 + x1) / 2, -(y0 + y1) / 2)
        d.text((cx - 22, cz - 5), r[0].upper(), fill=(255, 255, 255, 235))

    # the landmarks and sites, by name
    places = json.load(open(ib.PLACES))["places"] if os.path.exists(ib.PLACES) else []
    for pl in places:
        if int(pl.get("tier", 0)) < 2:
            continue
        x, z = to_px(pl["at"][0], pl["at"][2])
        d.rectangle([x - 4, z - 4, x + 4, z + 4], fill=MARK + (255,), outline=(0, 0, 0, 255))
        d.text((x + 7, z - 5), pl["name"], fill=MARK + (255,))

    # a north arrow and a scale bar, so the picture can be read without this file
    d.text((12, 12), "ISLAND DISTRICT PLAN  (north is UP; +x east, +z south)", fill=(255, 255, 255, 230))
    bar = 1000.0 / (2 * HALF) * px
    d.line([(14, px - 20), (14 + bar, px - 20)], fill=(255, 255, 255, 230), width=3)
    d.text((14, px - 36), "1 km", fill=(255, 255, 255, 230))
    img.save(out)
    print("island_region_map: %d regions, %d lanes, %d buildings, %d landmarks -> %s"
          % (len(ib.REGIONS), lanes, len(doc["buildings"]), sum(1 for p in places if int(p.get("tier", 0)) >= 2),
             out))


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    out = "island_regions.png"
    px = 1400
    for i, a in enumerate(argv):
        if a == "--out":
            out = argv[i + 1]
        elif a == "--px":
            px = int(argv[i + 1])
    draw(argv[0], out, px)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
