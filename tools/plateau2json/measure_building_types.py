#!/usr/bin/env python3
"""measure_building_types.py -- typical Japanese building sizes, measured from raw PLATEAU CityGML.

    python3 tools/plateau2json/measure_building_types.py <citygml dir or .zip> [...] [--json out.json]

PLATEAU is a MEASUREMENT reference here, never shipped data (CLAUDE.md, the map-data licence rule): this reads the
raw download outside the repo and prints only statistics (percentiles of plan size, height and storey height per
class). Only rounded numbers taken from the output go into `building_types.json`.

A PLATEAU building carries its use (`bldg:usage`, `uro:detailedUsage`), `bldg:storeysAboveGround` and
`bldg:measuredHeight`, and a footprint (`lod0RoofEdge`/`lod0FootPrint`, else the bottom face of `lod1Solid`), but
no brand: a convenience store is not labelled as one, so each class below is a USE + SIZE window chosen to
catch the building type, and the output says how many buildings fell in it. The plan size is the minimum-area
rectangle round the footprint (short side, long side), in metres from the lat/lon ring (equirectangular about the
ring's own centroid, exact to well under a centimetre at this size).
"""
import json
import math
import re
import sys
import zipfile

# class: (description, predicate(usage, detailed, storeys, area, height))
COMMERCIAL = {"402", "404"}
COMMERCIAL_D = {"1221"}
TRANSPORT = {"431"}
TRANSPORT_D = {"1431"}


def is_commercial(u, d):
    return u in COMMERCIAL or d in COMMERCIAL_D


CLASSES = {
    "shop_small":       ("single-storey commercial, 30-120 m2 (small shop, kiosk)",
                         lambda u, d, s, a, h: is_commercial(u, d) and s == 1 and 30 <= a < 120),
    "konbini":          ("single-storey commercial, 120-350 m2 (convenience store, the usual stand-alone size)",
                         lambda u, d, s, a, h: is_commercial(u, d) and s == 1 and 120 <= a < 350),
    "restaurant":       ("single-storey commercial, 350-900 m2 (family restaurant, drugstore, supermarket)",
                         lambda u, d, s, a, h: is_commercial(u, d) and s == 1 and 350 <= a < 900),
    "station_small":    ("1-2 storey transport building, 30-400 m2 (small station building, depot office)",
                         lambda u, d, s, a, h: (u in TRANSPORT or d in TRANSPORT_D) and s in (1, 2) and 30 <= a < 400),
    "shop_house":       ("shop + dwelling (店舗等併用住宅), 2-3 storeys",
                         lambda u, d, s, a, h: (u == "413" or d == "1230") and s in (2, 3) and 20 <= a < 200),
    "house":            ("detached house (住宅), 2 storeys",
                         lambda u, d, s, a, h: (u == "411" or d == "1310") and s == 2 and 40 <= a < 200),
}

TAG_USAGE = re.compile(r"<bldg:usage[^>]*>(\d+)</bldg:usage>")
TAG_DET = re.compile(r"<uro:detailedUsage[^>]*>(\d+)</uro:detailedUsage>")
TAG_STOREYS = re.compile(r"<bldg:storeysAboveGround>(\d+)</bldg:storeysAboveGround>")
TAG_HEIGHT = re.compile(r"<bldg:measuredHeight[^>]*>([-\d.]+)</bldg:measuredHeight>")
LOD0 = re.compile(r"<bldg:lod0(?:RoofEdge|FootPrint)>.*?<gml:posList>(.*?)</gml:posList>", re.S)
LOD1 = re.compile(r"<bldg:lod1Solid>.*?<gml:posList>(.*?)</gml:posList>", re.S)
BUILDING = re.compile(r"<bldg:Building [^>]*>(.*?)</bldg:Building>", re.S)


def ring_xy(poslist):
    v = [float(x) for x in poslist.split()]
    pts = [(v[i], v[i + 1]) for i in range(0, len(v) - 2, 3)]      # lat, lon
    if len(pts) < 3:
        return []
    lat0 = sum(p[0] for p in pts) / len(pts)
    kx = 111320.0 * math.cos(math.radians(lat0))
    ky = 110574.0
    lon0 = sum(p[1] for p in pts) / len(pts)
    return [((p[1] - lon0) * kx, (p[0] - lat0) * ky) for p in pts]


def area(poly):
    return abs(sum(poly[i][0] * poly[i - 1][1] - poly[i - 1][0] * poly[i][1] for i in range(len(poly)))) / 2.0


def hull(pts):
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts

    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2 and ((out[-1][0] - out[-2][0]) * (p[1] - out[-2][1])
                                     - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0])) <= 0:
                out.pop()
            out.append(p)
        return out
    lo, hi = half(pts), half(reversed(pts))
    return lo[:-1] + hi[:-1]


def min_rect(poly):
    """(short side, long side) of the minimum-area rectangle round `poly` (edge-aligned, rotating calipers)."""
    h = hull(poly)
    best = None
    for i in range(len(h)):
        ex, ey = h[(i + 1) % len(h)][0] - h[i][0], h[(i + 1) % len(h)][1] - h[i][1]
        n = math.hypot(ex, ey)
        if n < 1e-9:
            continue
        ux, uy = ex / n, ey / n
        us = [p[0] * ux + p[1] * uy for p in h]
        vs = [-p[0] * uy + p[1] * ux for p in h]
        a, b = max(us) - min(us), max(vs) - min(vs)
        if best is None or a * b < best[0] * best[1]:
            best = (a, b)
    if best is None:
        return None
    return (min(best), max(best))


def buildings(path):
    """Yield the text of every bldg:Building in a CityGML dir or zip (bldg files only)."""
    import os
    if path.endswith(".zip"):
        zf = zipfile.ZipFile(path)
        names = [n for n in zf.namelist() if "/bldg/" in n and n.endswith(".gml")]
        for n in names:
            text = zf.read(n).decode("utf-8", "replace")
            yield from (m.group(1) for m in BUILDING.finditer(text))
    else:
        d = os.path.join(path, "udx", "bldg")
        for n in sorted(os.listdir(d)):
            if n.endswith(".gml"):
                text = open(os.path.join(d, n), encoding="utf-8", errors="replace").read()
                yield from (m.group(1) for m in BUILDING.finditer(text))


def pct(vals, q):
    s = sorted(vals)
    if not s:
        return None
    k = (len(s) - 1) * q
    f, c = math.floor(k), math.ceil(k)
    return s[f] + (s[c] - s[f]) * (k - f)


def main(argv):
    out_json = None
    if "--json" in argv:
        i = argv.index("--json")
        out_json = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if not argv:
        raise SystemExit(__doc__)
    rows = {k: [] for k in CLASSES}
    total = 0
    for src in argv:
        for b in buildings(src):
            total += 1
            u = (TAG_USAGE.search(b) or [None, ""])[1]
            d = (TAG_DET.search(b) or [None, ""])[1]
            sm = TAG_STOREYS.search(b)
            hm = TAG_HEIGHT.search(b)
            if not sm or not hm:
                continue
            s, h = int(sm.group(1)), float(hm.group(1))
            ring = LOD0.search(b) or LOD1.search(b)
            if not ring:
                continue
            poly = ring_xy(ring.group(1))
            if len(poly) < 3:
                continue
            a = area(poly)
            for k, (_, pred) in CLASSES.items():
                if pred(u, d, s, a, h):
                    r = min_rect(poly)
                    if r:
                        rows[k].append({"short": r[0], "long": r[1], "area": a, "height": h, "storeys": s})
    report = {"sources": [src.split("/")[-1] for src in argv], "buildings_read": total, "classes": {}}
    print(f"{total} buildings read from {', '.join(report['sources'])}")
    for k, (desc, _) in CLASSES.items():
        rs = rows[k]
        entry = {"description": desc, "count": len(rs)}
        print(f"\n{k}: {desc} -- {len(rs)} buildings")
        for f in ("short", "long", "area", "height"):
            vals = [r[f] for r in rs]
            entry[f] = [round(pct(vals, q), 2) if vals else None for q in (0.25, 0.5, 0.75)]
            print(f"  {f:8s} p25 {entry[f][0]}  p50 {entry[f][1]}  p75 {entry[f][2]}")
        sh = [r["height"] / r["storeys"] for r in rs if r["storeys"]]
        entry["height_per_storey"] = [round(pct(sh, q), 2) if sh else None for q in (0.25, 0.5, 0.75)]
        print(f"  h/storey p25 {entry['height_per_storey'][0]}  p50 {entry['height_per_storey'][1]}  "
              f"p75 {entry['height_per_storey'][2]}")
        report["classes"][k] = entry
    if out_json:
        json.dump(report, open(out_json, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1:])
