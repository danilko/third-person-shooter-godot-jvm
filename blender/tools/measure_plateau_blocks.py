"""What Japanese buildings MEASURE, as massing, from the user's PLATEAU reference (PLAN.md 3.17, 3.18).

    blender -b /data/danilko/concept_arts/japan_city.blend --python blender/tools/measure_plateau_blocks.py \
        [-- --json <out.json>]

The sibling of `measure_plateau_facades.py` (which measures tone). Read-only, outside the repo by design: PLATEAU
geometry is not redistributed, only the NUMBERS it yields enter the repo (CREDITS.md "Real-world data"). It is
what `assets/world_source/buildings/JAPAN_ART_REVIEW.md` quotes, so every target there can be re-derived.

The file is four PLATEAU LOD2 tiles of central Tokyo (third mesh 5339-35-85/86/95/96), one mesh per building,
in metres with Z up. Per building, from its own vertices (nothing typed in):
* **footprint** = the minimum-area rectangle of the plan hull: short side (the frontage, for a street building),
  long side, and the hull's own area;
* **height** = top minus bottom, and `storeys` = height / `STOREY_M` (a mixed-use Tokyo mean; residential runs
  ~2.9, office ~3.8, so it is a guide, not a count);
* **roof**: FLAT when the up-facing area near the top covers most of the plan, PITCHED when sloped faces do;
* **tiering**: the plan area of the top third against the footprint (a podium + tower, a 斜線 setback);
* **the gap to the nearest neighbour**, hull to hull (Tokyo buildings mostly do not TOUCH: 民法 art. 234 asks
  50 cm from the boundary, so two neighbours stand ~1 m apart, and in a dense core they do touch).
"""
import json
import math
import sys

import numpy as np

import bpy

STOREY_M = 3.3
TOP_BAND = 1.0          # m under the top that counts as "the roof"
NEAR = 40.0             # m: neighbours looked at for the gap


def hull(pts):
    pts = sorted(set(map(tuple, np.round(pts, 2))))
    if len(pts) < 3:
        return np.array(pts)

    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2 and ((out[-1][0] - out[-2][0]) * (p[1] - out[-2][1])
                                     - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0])) <= 0:
                out.pop()
            out.append(p)
        return out
    lo, hi = half(pts), half(reversed(pts))
    return np.array(lo[:-1] + hi[:-1])


def area(h):
    x, y = h[:, 0], h[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def min_rect(h):
    best = None
    for i in range(len(h)):
        e = h[(i + 1) % len(h)] - h[i]
        n = np.hypot(*e)
        if n < 1e-6:
            continue
        u = e / n
        v = np.array([-u[1], u[0]])
        a, b = h @ u, h @ v
        w, d = a.max() - a.min(), b.max() - b.min()
        if best is None or w * d < best[0]:
            best = (w * d, min(w, d), max(w, d), math.degrees(math.atan2(u[1], u[0])) % 90.0)
    return best


def seg_dist(p, q, a, b):
    def pt_seg(x, s, t):
        d = t - s
        L = float(d @ d)
        k = 0.0 if L < 1e-12 else max(0.0, min(1.0, float((x - s) @ d) / L))
        return float(np.hypot(*(x - (s + k * d))))
    return min(pt_seg(p, a, b), pt_seg(q, a, b), pt_seg(a, p, q), pt_seg(b, p, q))


def inside(pt, h):
    x, y = pt
    c = False
    for i in range(len(h)):
        (x1, y1), (x2, y2) = h[i], h[(i + 1) % len(h)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def poly_gap(h1, h2):
    if any(inside(p, h2) for p in h1) or any(inside(p, h1) for p in h2):
        return 0.0
    best = 1e9
    for i in range(len(h1)):
        a, b = h1[i], h1[(i + 1) % len(h1)]
        for j in range(len(h2)):
            best = min(best, seg_dist(a, b, h2[j], h2[(j + 1) % len(h2)]))
    return best


def measure(o):
    me = o.data
    mw = o.matrix_world
    v = np.array([(mw @ x.co)[:] for x in me.vertices])
    if len(v) < 4:
        return None
    z0, z1 = v[:, 2].min(), v[:, 2].max()
    h = z1 - z0
    ph = hull(v[:, :2])
    if len(ph) < 3:
        return None
    a = area(ph)
    rect = min_rect(ph)
    if rect is None or a < 8.0 or h < 2.0:
        return None
    flat_top = sloped = 0.0
    for p in me.polygons:
        n = (mw.to_3x3() @ p.normal).normalized()
        c = mw @ p.center
        if n.z > 0.95 and c.z > z1 - TOP_BAND:
            flat_top += p.area
        elif 0.2 < n.z <= 0.95:
            sloped += p.area
    top = v[v[:, 2] > z0 + h * 2.0 / 3.0][:, :2]
    th = hull(top) if len(top) >= 3 else None
    top_share = area(th) / a if th is not None and len(th) >= 3 else 1.0
    return {"short": rect[1], "long": rect[2], "area": a, "height": h, "angle": rect[3], "hull": ph,
            "roof": "flat" if flat_top >= 0.5 * a else ("pitched" if sloped >= 0.3 * a else "mixed"),
            "top_share": min(1.0, top_share), "cx": ph[:, 0].mean(), "cy": ph[:, 1].mean()}


def pct(a, ps=(10, 50, 90)):
    a = np.asarray(a, float)
    return [round(float(np.percentile(a, p)), 1) for p in ps] if a.size else []


# a use-agnostic CLASS by massing, so the PLATEAU buildings can be set beside our types (PLATEAU's own `usage`
# attribute is not in this export). Order matters: first match wins.
CLASSES = [
    ("low_small", "1-2 storeys, under 150 m2 (house, shop-house, konbini-class)",
     lambda b: b["height"] < 8.5 and b["area"] < 150),
    ("low_large", "1-2 storeys, 150 m2 and over (shop, warehouse, family restaurant)",
     lambda b: b["height"] < 8.5),
    ("pencil", "a narrow frontage (short side under 9 m) standing 3+ storeys (ペンシルビル)",
     lambda b: b["short"] < 9.0 and b["height"] >= 10.0),
    ("mid", "3-7 storeys (mansion, 雑居ビル, small office)", lambda b: b["height"] < 25.0),
    ("tall", "8-15 storeys (office, tower mansion)", lambda b: b["height"] < 50.0),
    ("tower", "over 15 storeys", lambda b: True),
]


def main():
    out_json = None
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--json" in argv:
        out_json = argv[argv.index("--json") + 1]
    blds = []
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name.startswith("bldg"):
            m = measure(o)
            if m is not None:
                blds.append(m)
    print("[plateau_blocks] %d buildings measured" % len(blds))

    # the gap to the nearest neighbour, hull to hull
    cs = np.array([[b["cx"], b["cy"]] for b in blds])
    rad = np.array([np.hypot(*(b["hull"] - [b["cx"], b["cy"]]).T).max() for b in blds])
    for i, b in enumerate(blds):
        d = np.hypot(*(cs - cs[i]).T) - rad - rad[i]
        cand = [j for j in np.argsort(d)[:12] if j != i and d[j] < NEAR]
        b["gap"] = min((poly_gap(b["hull"], blds[j]["hull"]) for j in cand), default=NEAR)

    # how straight the street wall is: a building's plan angle against the median of its 8 nearest neighbours
    for i, b in enumerate(blds):
        near = [j for j in np.argsort(np.hypot(*(cs - cs[i]).T))[1:9]]
        diffs = [((blds[j]["angle"] - b["angle"] + 45.0) % 90.0) - 45.0 for j in near]
        b["skew"] = abs(float(np.median(diffs))) if diffs else 0.0

    doc = {"source": "PLATEAU LOD2, central Tokyo, third mesh 5339-35-85/86/95/96 (user's japan_city.blend)",
           "storey_m": STOREY_M, "classes": {}}
    for key, what, test in CLASSES:
        sel = [b for b in blds if b.get("cls") is None and test(b)]
        for b in sel:
            b["cls"] = key
        if not sel:
            continue
        row = {
            "what": what, "count": len(sel), "share": round(len(sel) / len(blds), 3),
            "short_m": pct([b["short"] for b in sel]), "long_m": pct([b["long"] for b in sel]),
            "area_m2": pct([b["area"] for b in sel]), "height_m": pct([b["height"] for b in sel]),
            "storeys": pct([b["height"] / STOREY_M for b in sel]),
            "aspect_long_over_short": pct([b["long"] / b["short"] for b in sel]),
            "roof_flat_share": round(sum(b["roof"] == "flat" for b in sel) / len(sel), 3),
            "roof_pitched_share": round(sum(b["roof"] == "pitched" for b in sel) / len(sel), 3),
            "top_third_plan_share": pct([b["top_share"] for b in sel]),
            "tiered_share": round(sum(b["top_share"] < 0.8 for b in sel) / len(sel), 3),
            "gap_to_neighbour_m": pct([b["gap"] for b in sel]),
            "touching_share": round(sum(b["gap"] < 0.3 for b in sel) / len(sel), 3),
        }
        doc["classes"][key] = row
    allb = {
        "count": len(blds), "height_m": pct([b["height"] for b in blds], (10, 25, 50, 75, 90)),
        "gap_to_neighbour_m": pct([b["gap"] for b in blds], (10, 25, 50, 75, 90)),
        "touching_share": round(sum(b["gap"] < 0.3 for b in blds) / len(blds), 3),
        "gap_under_1m_share": round(sum(b["gap"] < 1.0 for b in blds) / len(blds), 3),
        "skew_to_neighbours_deg": pct([b["skew"] for b in blds], (50, 75, 90)),
        "roof_flat_share": round(sum(b["roof"] == "flat" for b in blds) / len(blds), 3),
    }
    doc["all"] = allb
    print(json.dumps(doc, indent=1, ensure_ascii=False))
    if out_json:
        json.dump(doc, open(out_json, "w"), indent=1, ensure_ascii=False)


main()
