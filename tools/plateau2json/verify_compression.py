#!/usr/bin/env python3
"""Check that a compressed extract kept its promises.

Run after compress.py.  It is deliberately blunt: these five checks are the ones that
catch a bad squeeze, and a bad squeeze is otherwise very hard to see by eye.

    python3 verify_compression.py --raw build/plateau_json --compressed build/plateau_json_6km
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys


def load(d: str) -> dict[str, list[dict]]:
    out = {}
    for path in sorted(glob.glob(os.path.join(d, "*.json"))):
        base = os.path.basename(path)
        if base in ("manifest.json", "warp.json"):
            continue
        with open(path, encoding="utf-8") as fh:
            out[base.rsplit(".", 1)[0]] = json.load(fh).get("features", [])
    return out


def shapes(rec):
    for g in rec.get("geometry", []):
        yield g["points"]
    for tri in rec.get("triangles", []):
        yield tri
    for ta in rec.get("traffic_areas", []):
        for g in ta.get("geometry", []):
            yield g["points"]


def ring_area(pts) -> float:
    a = 0.0
    for i in range(len(pts) - 1):
        a += pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1]
    return abs(a) / 2.0


def min_width(pts) -> float:
    """Rotating-calipers-lite: smallest extent across the ring's principal axis.

    For a road slab or a building footprint this is the cross-section we must not
    have shrunk.
    """
    n = len(pts)
    if n < 3:
        return 0.0
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    sxx = sxy = syy = 0.0
    for p in pts:
        dx, dy = p[0] - cx, p[1] - cy
        sxx += dx * dx
        sxy += dx * dy
        syy += dy * dy
    theta = 0.5 * math.atan2(2 * sxy, sxx - syy)
    ux, uy = math.cos(theta), math.sin(theta)
    projs = [(-(p[0] - cx) * uy + (p[1] - cy) * ux) for p in pts]
    return max(projs) - min(projs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--compressed", required=True)
    ap.add_argument("--size", type=float, default=6144.0)
    ap.add_argument("--tolerance", type=float, default=1.0, help="cross-section drift, %%")
    args = ap.parse_args()

    raw = load(args.raw)
    com = load(args.compressed)
    warp = json.load(open(os.path.join(args.compressed, "warp.json"), encoding="utf-8"))
    half = args.size / 2.0
    failures = []

    # 1. everything inside the target box -------------------------------------
    # Rigidly-preserved models (a 1 km bridge span kept at true size) legitimately
    # overhang the nominal edge when their centroid lands near it — that overhang is
    # reported, not failed.  Compressed geometry escaping is a real bug.
    rigid_layers = set(warp.get("modes", {}).get("rigid", []))
    bounds: dict[str, list] = {}
    zmin = zmax = None
    for name, feats in com.items():
        lo = hi = None
        for rec in feats:
            for pts in shapes(rec):
                for p in pts:
                    lo = p[0] if lo is None else min(lo, p[0], p[1])
                    hi = p[0] if hi is None else max(hi, p[0], p[1])
                    zmin = p[2] if zmin is None else min(zmin, p[2])
                    zmax = p[2] if zmax is None else max(zmax, p[2])
        bounds[name] = [lo, hi]
        tag = "rigid model" if name in rigid_layers else "compressed"
        over = max(0.0, -half - (lo or 0), (hi or 0) - half)
        print(f"1. bounds        {name:9s} XY [{lo:.1f}, {hi:.1f}]  "
              f"overhang {over:6.1f} m  ({tag})")
        if name not in rigid_layers and over > 50:
            failures.append(f"{name} escapes the target box by {over:.0f} m")
    print(f"1. bounds        Z [{zmin:.2f}, {zmax:.2f}] (never scaled)")

    # 2. feature counts preserved ---------------------------------------------
    ok = True
    for name in raw:
        if len(raw.get(name, [])) != len(com.get(name, [])):
            ok = False
            failures.append(f"feature count changed in {name}")
    print(f"2. counts        {'preserved' if ok else 'CHANGED'} "
          f"({ {k: len(v) for k, v in com.items()} })")

    # 3. warp monotonic + continuous ------------------------------------------
    mono = True
    for axis in ("x", "y"):
        edges = warp[axis]["compressed_edges_m"]
        if any(b <= a for a, b in zip(edges, edges[1:])):
            mono = False
        if any(s <= 0 for s in warp[axis]["band_scales"]):
            mono = False
    print(f"3. warp          {'monotonic + continuous' if mono else 'NOT MONOTONIC'} "
          f"(x span {warp['x']['compressed_span_m']:.0f} m, "
          f"y span {warp['y']['compressed_span_m']:.0f} m)")
    if not mono:
        failures.append("axis warp is not strictly monotonic")

    # 4. cross-sections preserved ---------------------------------------------
    for name in sorted(set(raw) & set(com)):
        pairs = []
        for r, c in zip(raw[name], com[name]):
            rs = [p for p in shapes(r) if len(p) >= 4]
            cs = [p for p in shapes(c) if len(p) >= 4]
            for a, b in zip(rs, cs):
                # A near-vertical ring (a bridge/building wall quad) has no meaningful
                # width in plan view — measuring one is noise, so skip it.
                if ring_area(a) < 1.0:
                    continue
                wa, wb = min_width(a), min_width(b)
                if wa > 1.0:                     # ignore slivers
                    pairs.append(abs(wb - wa) / wa * 100.0)
        if not pairs:
            continue
        pairs.sort()
        med = pairs[len(pairs) // 2]
        p90 = pairs[int(len(pairs) * 0.9)]
        verdict = "OK" if med <= args.tolerance else "DRIFT"
        print(f"4. cross-section {name:9s} median {med:6.2f}%  p90 {p90:6.2f}%  [{verdict}]")
        if med > args.tolerance:
            failures.append(f"{name} cross-sections drifted {med:.2f}% (median)")

    # 5. area ratio: how much did the world actually shrink? --------------------
    for name in sorted(set(raw) & set(com)):
        ra = sum(ring_area(p) for r in raw[name] for p in shapes(r) if len(p) >= 4)
        ca = sum(ring_area(p) for c in com[name] for p in shapes(c) if len(p) >= 4)
        if ra:
            print(f"5. footprint     {name:9s} {ca / ra * 100:.1f}% of real area retained")

    print()
    if failures:
        print("FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("all compression invariants hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
