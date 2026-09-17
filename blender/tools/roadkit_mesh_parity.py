#!/usr/bin/env python3
"""roadkit_mesh_parity.py -- is the pure-Python sweep (`point_mesh`) the Blender build? (PLAN.md 3.1 B10.7)

    python3 blender/tools/roadkit_mesh_parity.py <record.roads.json> <piece.gltf> [<piece.gltf> ...] [--ground g.json]

Per object and material present in either: triangle count, area, bounding box, and the SURFACE distance
both ways (points sampled every ~1 m2 on one, nearest point on the other's triangles: p95 and max). Then
the thing traffic and characters actually stand on: under every lane sample of the pieces' lanekits (every
4 m), the height of the road surface (asphalt: carriageway, pad, gore) directly below in each build.
Timing of the Python sweep is printed. Prints one JSON summary line last.
"""
import argparse, json, math, os, random, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(os.path.dirname(HERE), "lib"), os.path.join(os.path.dirname(HERE), "addons", "road_kit_authoring")]
import gltf_tris                                   # noqa: E402
import point_model as pm                           # noqa: E402
import point_mesh as pmsh                          # noqa: E402
import point_ground as pg                          # noqa: E402
import point_export as pe                          # noqa: E402

CELL = 4.0
#: `--assert` thresholds. The road surface a car drives on must agree to 2 cm; every shared layer's surface
#: to 3 cm p95 both ways and its area to 1%. The BARRIER is exempt from the distance test only: Blender
#: evaluates an extrusion's thickness per FACE, so a wall's first and last segment step through a quarter of
#: its height where the solver's per-vertex value (which `point_mesh` sweeps) ramps -- area still gated.
LANE_DY_MAX = 0.02
SURFACE_P95 = 0.03
AREA_TOL = 0.01

def area(t):
    a, b, c = t
    u = [b[i] - a[i] for i in range(3)]; v = [c[i] - a[i] for i in range(3)]
    n = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
    return 0.5 * math.sqrt(sum(x*x for x in n))

def closest(p, a, b, c):
    ab = [b[i]-a[i] for i in range(3)]; ac = [c[i]-a[i] for i in range(3)]; ap = [p[i]-a[i] for i in range(3)]
    dot = lambda x, y: x[0]*y[0]+x[1]*y[1]+x[2]*y[2]
    d1, d2 = dot(ab, ap), dot(ac, ap)
    if d1 <= 0 and d2 <= 0: return a
    bp = [p[i]-b[i] for i in range(3)]; d3, d4 = dot(ab, bp), dot(ac, bp)
    if d3 >= 0 and d4 <= d3: return b
    vc = d1*d4 - d3*d2
    if vc <= 0 and d1 >= 0 and d3 <= 0: return [a[i]+ab[i]*d1/(d1-d3) for i in range(3)]
    cp = [p[i]-c[i] for i in range(3)]; d5, d6 = dot(ab, cp), dot(ac, cp)
    if d6 >= 0 and d5 <= d6: return c
    vb = d5*d2 - d1*d6
    if vb <= 0 and d2 >= 0 and d6 <= 0: return [a[i]+ac[i]*d2/(d2-d6) for i in range(3)]
    va = d3*d6 - d5*d4
    if va <= 0 and (d4-d3) >= 0 and (d5-d6) >= 0:
        w = (d4-d3)/((d4-d3)+(d5-d6)); return [b[i]+(c[i]-b[i])*w for i in range(3)]
    den = 1.0/(va+vb+vc) if (va+vb+vc) else 0.0
    return [a[i]+ab[i]*vb*den+ac[i]*vc*den for i in range(3)]

def grid(tris):
    g = {}
    for t in tris:
        if area(t) < 1e-8:
            continue            # a degenerate triangle has no closest point, and covers nothing
        xs = [p[0] for p in t]; zs = [p[2] for p in t]
        for gx in range(int(math.floor(min(xs)/CELL)), int(math.floor(max(xs)/CELL))+1):
            for gz in range(int(math.floor(min(zs)/CELL)), int(math.floor(max(zs)/CELL))+1):
                g.setdefault((gx, gz), []).append(t)
    return g

def dist(g, p):
    best = float("inf")
    cx, cz = int(math.floor(p[0]/CELL)), int(math.floor(p[2]/CELL))
    for dx in (-1, 0, 1):
        for dz in (-1, 0, 1):
            for t in g.get((cx+dx, cz+dz), ()):
                d = math.dist(p, closest(p, *t))
                if d < best: best = d
    return best

def samples(tris, per_m2=1.0, cap=4000, rng=None):
    rng = rng or random.Random(7)
    tot = sum(area(t) for t in tris)
    n = min(cap, max(len(tris), int(tot * per_m2)))
    weights = [area(t) for t in tris]
    out = []
    for t in rng.choices(tris, weights=weights, k=n) if tot > 0 else []:
        r1, r2 = rng.random(), rng.random()
        if r1 + r2 > 1: r1, r2 = 1-r1, 1-r2
        out.append([t[0][i] + (t[1][i]-t[0][i])*r1 + (t[2][i]-t[0][i])*r2 for i in range(3)])
    return out

def pct(xs, q):
    if not xs: return 0.0
    xs = sorted(xs); return xs[min(len(xs)-1, int(q*len(xs)))]

def height_below(g, x, z, y_hint):
    best = None
    for t in g.get((int(math.floor(x/CELL)), int(math.floor(z/CELL))), ()):
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = t
        d = (bz-cz)*(ax-cx) + (cx-bx)*(az-cz)
        if abs(d) < 1e-12: continue
        l1 = ((bz-cz)*(x-cx) + (cx-bx)*(z-cz))/d; l2 = ((cz-az)*(x-cx) + (ax-cx)*(z-cz))/d; l3 = 1-l1-l2
        if min(l1, l2, l3) < -1e-6: continue
        y = l1*ay + l2*by + l3*cy
        if abs(y - y_hint) < 2.0 and (best is None or abs(y - y_hint) < abs(best - y_hint)):
            best = y
    return best

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("record"); ap.add_argument("gltf", nargs="+"); ap.add_argument("--ground", default="")
    ap.add_argument("--built", nargs="*", default=[],
                    help="B11: compare these glTFs written by point_gltf (collision proxies included) instead of "
                         "sweeping in memory")
    ap.add_argument("--lanekit-dir", default="", help="where <gltf stem>.lanekit.json lives (default: the pieces dir)")
    ap.add_argument("--assert", dest="check", action="store_true",
                    help="exit 1 unless the two builds agree (the thresholds below)")
    a = ap.parse_args()
    t0 = time.time()
    net = pm.load_network(a.record)
    ground = pg.load_ground(a.ground) if a.ground else None
    if a.built:
        py = {}
        for path in a.built:
            for o, mats in gltf_tris.load(path).items():
                for m, tris in mats.items():
                    py.setdefault(o, {}).setdefault(m, []).extend(tris)
    else:
        py = pmsh.build(net, ground)
        py = {o: {(m or "-"): [tuple(pe.godot(p) for p in t) for t in tris] for m, tris in mats.items()}
              for o, mats in py.items()}
    ms = (time.time() - t0) * 1000.0
    bl = {}
    for path in a.gltf:
        for o, mats in gltf_tris.load(path).items():
            for m, tris in mats.items():
                bl.setdefault(o, {}).setdefault(m, []).extend(tris)
    rows = []
    fam = {}
    for o in sorted(set(py) | set(bl)):
        if ("-colonly" in o) and not a.built:
            continue
        # A proxy's triangles are compared whatever material Blender left on them: it has no look.
        if "-colonly" in o:
            py[o] = {"-": [t for ts in py.get(o, {}).values() for t in ts]}
            bl[o] = {"-": [t for ts in bl.get(o, {}).values() for t in ts]}
        for m in sorted(set(py.get(o, {})) | set(bl.get(o, {}))):
            P, B = py.get(o, {}).get(m, []), bl.get(o, {}).get(m, [])
            row = {"obj": o, "mat": m, "tris_b": len(B), "tris_p": len(P),
                   "area_b": round(sum(map(area, B)), 1), "area_p": round(sum(map(area, P)), 1)}
            if P and B:
                gb, gp = grid(B), grid(P)
                pb = [dist(gb, s) for s in samples(P)]
                bp = [dist(gp, s) for s in samples(B)]
                row.update({"p2b_p95": round(pct(pb, .95), 3), "p2b_max": round(max(pb), 3),
                            "b2p_p95": round(pct(bp, .95), 3), "b2p_max": round(max(bp), 3)})
            rows.append(row)
            kind = ("colonly/" + o.rsplit("_", 1)[-1].split("-")[0]) if "-colonly" in o else (o.split("__")[-1].split("_")[0] + "/" + m)
            f = fam.setdefault(kind, {"n": 0, "missing_p": 0, "missing_b": 0, "p2b_p95": 0.0, "b2p_p95": 0.0, "area_b": 0.0, "area_p": 0.0})
            f["n"] += 1; f["area_b"] += row["area_b"]; f["area_p"] += row["area_p"]
            if not P: f["missing_p"] += 1
            if not B: f["missing_b"] += 1
            f["p2b_p95"] = max(f["p2b_p95"], row.get("p2b_p95", 0.0)); f["b2p_p95"] = max(f["b2p_p95"], row.get("b2p_p95", 0.0))
    for r in rows:
        print("%-34s %-15s tris %5d/%5d area %9.1f/%9.1f  p->b p95 %6s max %6s  b->p p95 %6s max %6s" % (
            r["obj"], r["mat"], r["tris_b"], r["tris_p"], r["area_b"], r["area_p"],
            r.get("p2b_p95", "-"), r.get("p2b_max", "-"), r.get("b2p_p95", "-"), r.get("b2p_max", "-")))
    print("\nby layer (blender/python):")
    for k, f in sorted(fam.items()):
        print("  %-24s objs %3d  area %10.1f/%10.1f  worst p95 p->b %.3f b->p %.3f  only-in-blender %d only-in-python %d" % (
            k, f["n"], f["area_b"], f["area_p"], f["p2b_p95"], f["b2p_p95"], f["missing_p"], f["missing_b"]))
    # The drivable surface under every lane sample.
    road = lambda d: [t for o, mats in d.items() if o.endswith("__surface") or o.endswith("__pad") or o.endswith("__gore") for t in mats.get("M_Asphalt", [])]
    gb, gp = grid(road(bl)), grid(road(py))
    deltas, miss = [], 0
    for path in a.gltf:
        stem = os.path.splitext(os.path.basename(path))[0]
        lk = os.path.join(a.lanekit_dir or os.path.join(os.path.dirname(HERE), "..", "assets", "world_source", "pieces"),
                          stem + ".lanekit.json")
        if not os.path.exists(lk):
            continue
        for lane in json.load(open(lk))["lanes"]:
            pts = lane["points"]
            for i in range(len(pts) - 1):
                n = max(1, int(math.dist(pts[i], pts[i+1]) / 4.0))
                for k in range(n):
                    q = [pts[i][j] + (pts[i+1][j]-pts[i][j]) * k / n for j in range(3)]
                    hb, hp = height_below(gb, q[0], q[2], q[1]), height_below(gp, q[0], q[2], q[1])
                    if hb is None or hp is None:
                        miss += 1
                    else:
                        deltas.append(abs(hb - hp))
    print("\nroad surface under %d lane samples: |dy| p95 %.4f max %.4f, %d on only one build" % (len(deltas), pct(deltas, .95), max(deltas) if deltas else 0, miss))
    print("python %s: %.0f ms" % ("glTF read" if a.built else "sweep", ms))
    print(json.dumps({"python_ms": round(ms), "lane_samples": len(deltas), "lane_dy_p95": round(pct(deltas, .95), 4),
                      "lane_dy_max": round(max(deltas) if deltas else 0, 4), "lane_one_sided": miss,
                      "layers": {k: {kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in f.items()} for k, f in fam.items()}}))
    if a.check:
        bad = []
        if not deltas or max(deltas) > LANE_DY_MAX:
            bad.append("road surface under the lanes differs by %.4f m" % (max(deltas) if deltas else -1))
        for k, f in fam.items():
            if f["missing_p"] or f["missing_b"]:
                bad.append("%s: %d object(s) in only one build" % (k, f["missing_p"] + f["missing_b"]))
            if abs(f["area_b"] - f["area_p"]) > AREA_TOL * max(1.0, f["area_b"]):
                bad.append("%s: area %.1f vs %.1f" % (k, f["area_b"], f["area_p"]))
            if not k.startswith("edges/M_Barrier") and max(f["p2b_p95"], f["b2p_p95"]) > SURFACE_P95:
                bad.append("%s: surface distance p95 %.3f" % (k, max(f["p2b_p95"], f["b2p_p95"])))
        for b in bad:
            print("PARITY FAIL: " + b)
        sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
