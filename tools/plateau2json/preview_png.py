#!/usr/bin/env python3
"""Top-down PNG of an extracted (or compressed) PLATEAU world.

A debug view, not a product — but a useful one: it writes a sidecar with the exact
metres-per-pixel and world extent, so the image drops straight onto a Blender plane at
1:1 real-world scale as a background reference.

    python3 preview_png.py --in build/plateau_json_6km --out build/preview.png --size 4096

Colours follow the request: black background, roads white, rail green.  Water is blue
and buildings dark grey so the coastline and the built-up areas are readable; pass
--plain for strictly white/green/black.

Data: Project PLATEAU (MLIT), CC BY 4.0.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

from PIL import Image, ImageDraw

# Road_function -> stroke weight in px at 4096.  Expressways read thickest so the
# Shuto network is instantly visible against the municipal street mesh.
WEIGHT_BY_FUNCTION = {"1": 7, "5": 7, "2": 5, "3": 5, "4": 3}
WEIGHT_BY_WIDTH = {"1": 5, "2": 3, "3": 2, "4": 1}

WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
BLUE = (40, 90, 190)
GREY = (70, 70, 70)
LAND = (26, 26, 26)

# TrafficArea_function -> colour.  This is the point of the v5 data: carriageway,
# sidewalk, intersection and median are separate polygons, so show them separately.
TRAFFIC_COLOURS = {
    "1000": ((235, 235, 235), "車道部 carriageway"),
    "1020": ((240, 150, 40), "車道交差部 intersection"),
    "2000": ((105, 120, 150), "歩道部 sidewalk"),
    "2010": ((105, 120, 150), "自転車歩行者道"),
    "2020": ((105, 120, 150), "歩道 sidewalk"),
    "2030": ((150, 105, 150), "自転車道 cycle track"),
    "3000": ((150, 130, 45), "島 median island"),
    "1030": ((200, 200, 200), "すりつけ区間 taper"),
}

# Road_function -> colour for the LOD1 road footprint underneath.
ROAD_COLOURS = {
    "1": (200, 70, 70),    # 高速自動車国道
    "5": (200, 70, 70),    # 都市高速道路 (Shuto)
    "2": (120, 100, 70),   # 一般国道
    "3": (95, 85, 65),     # 都道府県道
}
ROAD_DEFAULT = (58, 58, 58)

VEG = (24, 52, 28)
SHINKANSEN = (120, 255, 140)


def load_layers(src: str) -> dict[str, list[dict]]:
    out = {}
    for path in sorted(glob.glob(os.path.join(src, "*.json"))):
        base = os.path.basename(path)
        if base in ("manifest.json", "warp.json"):
            continue
        with open(path, encoding="utf-8") as fh:
            out[base.rsplit(".", 1)[0]] = json.load(fh).get("features", [])
    return out


def shapes(rec):
    for g in rec.get("geometry", []):
        yield g
    for tri in rec.get("triangles", []):
        yield {"kind": "ring", "points": tri}
    for ta in rec.get("traffic_areas", []):
        for g in ta.get("geometry", []):
            yield g


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=4096)
    ap.add_argument("--crop", type=float, nargs="?", const=500.0, default=None,
                    metavar="PAD_M",
                    help="crop to the road network's extent plus PAD_M metres (default "
                         "500) — keeps whole-river water polygons from stretching the frame")
    ap.add_argument("--bbox-m", nargs=4, type=float, metavar=("X0", "Y0", "X1", "Y1"),
                    help="explicit crop in local metres (overrides --crop)")
    ap.add_argument("--legend", action="store_true",
                    help="draw a colour key in the top-left corner")
    ap.add_argument("--plain", action="store_true",
                    help="strict white roads / green rail / black background only")
    args = ap.parse_args()

    layers = load_layers(args.src)
    if not layers:
        print(f"no layer files in {args.src}", file=sys.stderr)
        return 2

    xs, ys = [], []
    for feats in layers.values():
        for rec in feats:
            for g in shapes(rec):
                for p in g["points"]:
                    xs.append(p[0])
                    ys.append(p[1])
    if not xs:
        print("no geometry", file=sys.stderr)
        return 2

    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)

    if args.crop:
        # The `wtr` module carries whole prefecture-managed river courses, so a ward
        # extract's raw bounds can run tens of km past the built-up area (the Tama and
        # Arakawa trail off west and north).  Crop to where the *roads* actually are.
        rxs = [p[0] for rec in layers.get("road", []) for g in rec.get("geometry", [])
               for p in g["points"]]
        rys = [p[1] for rec in layers.get("road", []) for g in rec.get("geometry", [])
               for p in g["points"]]
        if rxs:
            pad = args.crop
            x0, x1 = min(rxs) - pad, max(rxs) + pad
            y0, y1 = min(rys) - pad, max(rys) + pad
            print(f"cropped to road extent +{pad:.0f} m: "
                  f"{x1 - x0:.0f} x {y1 - y0:.0f} m")

    if args.bbox_m:
        x0, y0, x1, y1 = args.bbox_m
    # one metres-per-pixel on BOTH axes (letterboxed) — anything else silently breaks
    # the "drop it on a plane at real scale" promise this file exists for
    mpp = max((x1 - x0), (y1 - y0)) / args.size
    w = max(int((x1 - x0) / mpp), 1)
    h = max(int((y1 - y0) / mpp), 1)

    img = Image.new("RGB", (w, h), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    def px(p):
        return ((p[0] - x0) / mpp, h - (p[1] - y0) / mpp)   # flip Y so north is up

    def poly(points, fill=None, outline=None, width=1):
        # Skip shapes entirely outside the frame — Pillow would happily rasterise a
        # 40 km river polygon's clipped edge, which is slow and adds nothing.
        if all(p[0] < x0 for p in points) or all(p[0] > x1 for p in points) \
           or all(p[1] < y0 for p in points) or all(p[1] > y1 for p in points):
            return
        pts = [px(p) for p in points]
        if len(pts) < 2:
            return
        if fill and len(pts) >= 3:
            draw.polygon(pts, fill=fill, outline=outline)
        else:
            draw.line(pts, fill=outline or fill, width=width, joint="curve")

    used: dict[str, tuple] = {}     # legend entries actually drawn

    # Painter's order, bottom to top: ground -> water -> vegetation -> buildings ->
    # road footprints -> traffic areas (carriageway/sidewalk/intersection) -> rail.
    for name in ("terrain", "landuse"):
        if args.plain:
            break
        for rec in layers.get(name, []):
            colour = BLUE if rec.get("is_water") else LAND
            for g in shapes(rec):
                poly(g["points"], fill=colour)

    if not args.plain:
        for rec in layers.get("water", []):
            for g in shapes(rec):
                if g["kind"] == "ring":
                    poly(g["points"], fill=BLUE)
        used["water"] = BLUE
        for rec in layers.get("vegetation", []):
            for g in shapes(rec):
                poly(g["points"], fill=VEG)
        if layers.get("vegetation"):
            used["vegetation"] = VEG
        for rec in layers.get("building", []):
            for g in shapes(rec):
                if g.get("lod") in (None, "lod0RoofEdge"):
                    poly(g["points"], fill=GREY)
        if layers.get("building"):
            used["building footprint"] = GREY

    # road footprints (LOD1), tinted by real road class so expressways stand out
    for rec in layers.get("road", []) + layers.get("bridge", []):
        fn = (rec.get("function") or {}).get("code")
        wt = (rec.get("width_type") or {}).get("code")
        colour = WHITE if args.plain else ROAD_COLOURS.get(fn, ROAD_DEFAULT)
        weight = WEIGHT_BY_FUNCTION.get(fn) or WEIGHT_BY_WIDTH.get(wt, 2)
        weight = max(1, round(weight * args.size / 4096))
        for g in rec.get("geometry", []):
            poly(g["points"], fill=colour if g["kind"] == "ring" else None,
                 outline=colour, width=weight)
        if fn in ROAD_COLOURS and not args.plain:
            used["expressway / national road"] = ROAD_COLOURS[fn]

    # traffic areas on top — the v5 detail worth seeing
    for rec in layers.get("road", []):
        for ta in rec.get("traffic_areas", []):
            code = (ta.get("function") or {}).get("code")
            entry = TRAFFIC_COLOURS.get(code)
            if entry is None:
                continue
            colour, label = entry
            if args.plain:
                colour = WHITE
            else:
                used[label] = colour
            for g in ta.get("geometry", []):
                poly(g["points"], fill=colour if g["kind"] == "ring" else None,
                     outline=colour, width=1)

    for rec in layers.get("rail", []):
        colour = SHINKANSEN if rec.get("is_shinkansen") else GREEN
        width = max(2, round((5 if rec.get("is_shinkansen") else 3) * args.size / 4096))
        for g in shapes(rec):
            poly(g["points"], fill=colour if g["kind"] == "ring" else None,
                 outline=colour, width=width)
        used["shinkansen" if rec.get("is_shinkansen") else "railway"] = colour

    if args.legend and used and not args.plain:
        pad, box, line = 14, 13, 20
        entries = sorted(used.items())
        bw = 300
        bh = pad * 2 + line * len(entries)
        draw.rectangle([pad, pad, pad + bw, pad + bh], fill=(0, 0, 0), outline=(90, 90, 90))
        for i, (label, colour) in enumerate(entries):
            y = pad * 2 + i * line
            draw.rectangle([pad + 12, y, pad + 12 + box, y + box], fill=colour)
            draw.text((pad + 12 + box + 10, y), label, fill=(225, 225, 225))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    img.save(args.out)

    sidecar = {
        "image": os.path.basename(args.out),
        "size_px": [w, h],
        "extent_m": {"width": round(x1 - x0, 3), "height": round(y1 - y0, 3)},
        "metres_per_pixel": round(mpp, 6),
        "world_bounds_m": {"x": [round(x0, 3), round(x1, 3)],
                           "y": [round(y0, 3), round(y1, 3)]},
        "origin": "bottom-left of the image = (x0, y0); +X east, +Y north",
        "blender": f"add a plane {x1 - x0:.1f} m x {y1 - y0:.1f} m and map this image to it",
        "attribution": "Data: Project PLATEAU (MLIT), CC BY 4.0",
    }
    side_path = os.path.splitext(args.out)[0] + ".json"
    with open(side_path, "w", encoding="utf-8") as fh:
        json.dump(sidecar, fh, ensure_ascii=False, indent=2)

    print(f"wrote {args.out}  {w}x{h} px  @ {mpp:.3f} m/px "
          f"({x1 - x0:.0f} x {y1 - y0:.0f} m)")
    print(f"wrote {side_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
