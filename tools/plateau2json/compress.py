#!/usr/bin/env python3
"""Squeeze an extracted PLATEAU world into a fixed square (default 6144 m x 6144 m).

The rule this whole file exists to enforce:

    Compress the distance *between* things.  Never compress the things themselves.

A plain uniform scale would fit the box but would also make a 3.25 m lane 1.1 m wide.
So instead:

  * a *monotonic piecewise-linear warp* per axis moves everything closer together,
    with band scales chosen from feature density — dense bands (a downtown core, the
    bay waterfront, the airport) stay near 1:1 while empty bands (open water, gaps)
    collapse hard, until the total fits;
  * the same warp is applied to every layer, so nothing tears or de-registers;
  * elongated network geometry (road and rail slabs) is compressed along its own
    axis while its across-axis coordinate is copied verbatim, so a carriageway gets
    shorter without ever getting thinner — no gain factor, nothing to clamp;
  * authored 3D models (buildings, bridges) and compact blobs (junction plazas,
    intersection polygons) are translated rigidly and never deformed at all;
  * Z is left completely alone — viaduct clearances, terrain slope and building
    heights stay real against the shortened plan.

    python3 compress.py --in build/plateau_json --out build/plateau_json_6km --size 6144

Data: Project PLATEAU (MLIT), CC BY 4.0.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys

# Layers whose geometry is a continuous field tiling the plane (coastline, ground,
# zoning).  These must warp point-wise or they would leave gaps between neighbours.
FIELD_LAYERS = {"terrain", "landuse", "water"}

# Authored 3D assets.  A building or a bridge is a *model* — you want it intact and
# repositioned, never deformed — so these are translated rigidly, whole, at true size.
# The cost is that a kilometre-long bridge near the edge can overhang the nominal box;
# that is the correct trade (deforming it into a shorter, sharper curve is worse), and
# verify_compression.py reports such overhang separately instead of failing on it.
RIGID_LAYERS = {"building", "bridge"}

# Network geometry: flat plan-view slabs that are meant to get shorter.  Elongated ones
# are compressed along their own axis with the cross-section held exactly; compact ones
# (junction plazas, 交差部 polygons) fall back to rigid — re-shaping a blob by its
# perpendicular scale is what blew geometry far outside the box in an early version.
CORRIDOR_LAYERS = {"road", "rail"}

# Layers whose features are weighted highest when choosing where to keep detail.
DENSITY_WEIGHTS = {"road": 3.0, "rail": 3.0, "bridge": 1.0, "building": 1.0}


# ---------------------------------------------------------------------------
# the axis warp
# ---------------------------------------------------------------------------


class AxisWarp:
    """Monotonic piecewise-linear map from real metres to compressed metres.

    Built from a density histogram: `scales[i]` is how much band *i* keeps of its
    original length.  The result is centred on 0 and spans exactly `target`.
    """

    def __init__(self, lo: float, hi: float, scales: list[float]):
        self.lo, self.hi = lo, hi
        self.n = len(scales)
        self.band = (hi - lo) / self.n
        self.scales = scales
        # cumulative compressed position of each band edge
        self.edges = [0.0]
        for s in scales:
            self.edges.append(self.edges[-1] + s * self.band)
        total = self.edges[-1]
        self.total = total
        # centre on 0
        self.edges = [e - total / 2.0 for e in self.edges]

    def __call__(self, v: float) -> float:
        t = (v - self.lo) / self.band
        i = int(math.floor(t))
        if i < 0:
            return self.edges[0] + (v - self.lo) * self.scales[0]
        if i >= self.n:
            return self.edges[-1] + (v - self.hi) * self.scales[-1]
        return self.edges[i] + (t - i) * self.scales[i] * self.band

    def jacobian(self, v: float) -> float:
        """Local scale factor (d out / d in) at `v` — the band's own scale."""
        i = int(math.floor((v - self.lo) / self.band))
        return self.scales[min(max(i, 0), self.n - 1)]

    def to_json(self) -> dict:
        return {
            "real_range": [self.lo, self.hi],
            "bands": self.n,
            "band_width_m": self.band,
            "band_scales": [round(s, 4) for s in self.scales],
            "compressed_span_m": round(self.total, 3),
            "compressed_edges_m": [round(e, 3) for e in self.edges],
        }


def solve_scales(density: list[float], band_w: float, target: float,
                 s_min: float, s_max: float) -> list[float]:
    """Pick a scale per band so denser bands keep more length and the total fits.

    Bands are seeded from normalised density, then a single global multiplier is
    solved for.  Any band that would end up *stretched* (scale > s_max) is pinned and
    the remainder re-solved, so compression never inflates a dense area.
    """
    n = len(density)
    lo, hi = min(density), max(density)
    span = (hi - lo) or 1.0
    seed = [s_min + (s_max - s_min) * ((d - lo) / span) for d in density]

    pinned = [False] * n
    scales = list(seed)
    for _ in range(32):
        fixed_len = sum(scales[i] * band_w for i in range(n) if pinned[i])
        free_len = sum(seed[i] * band_w for i in range(n) if not pinned[i])
        if free_len <= 0:
            break
        k = (target - fixed_len) / free_len
        newly = False
        for i in range(n):
            if pinned[i]:
                continue
            s = seed[i] * k
            if s > s_max:
                scales[i] = s_max
                pinned[i] = True
                newly = True
            else:
                scales[i] = max(s, 1e-4)
        if not newly:
            break
    return scales


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------


def iter_points(rec: dict):
    """Yield every mutable point list in a record, across all its geometry shapes."""
    for g in rec.get("geometry", []):
        yield g["points"]
    for tri in rec.get("triangles", []):
        yield tri
    for ta in rec.get("traffic_areas", []):
        for g in ta.get("geometry", []):
            yield g["points"]


def centroid(rec: dict):
    sx = sy = 0.0
    n = 0
    for pts in iter_points(rec):
        for p in pts:
            sx += p[0]
            sy += p[1]
            n += 1
    return (sx / n, sy / n) if n else None


def principal_axis(rec: dict):
    """`(ux, uy, elongation)` from a PCA of the feature's XY points.

    `elongation` is the ratio of the two principal standard deviations.  It is what
    tells a 400 m road slab (elongated, safe to re-widen along its short axis) from a
    junction plaza or a `sectionType=4` intersection polygon (compact — re-widening
    such a blob by its perpendicular scale would inflate it wildly, which is exactly
    how an early version of this blew geometry far outside the target box).
    """
    cx = cy = 0.0
    n = 0
    for pts in iter_points(rec):
        for p in pts:
            cx += p[0]
            cy += p[1]
            n += 1
    if n < 2:
        return (1.0, 0.0, 1.0)
    cx /= n
    cy /= n
    sxx = sxy = syy = 0.0
    for pts in iter_points(rec):
        for p in pts:
            dx, dy = p[0] - cx, p[1] - cy
            sxx += dx * dx
            sxy += dx * dy
            syy += dy * dy
    sxx /= n
    sxy /= n
    syy /= n
    # eigenvalues / principal eigenvector of [[sxx, sxy], [sxy, syy]]
    tr, det = sxx + syy, sxx * syy - sxy * sxy
    disc = max(tr * tr / 4.0 - det, 0.0) ** 0.5
    l1, l2 = tr / 2.0 + disc, max(tr / 2.0 - disc, 1e-9)
    theta = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
    return (math.cos(theta), math.sin(theta), (l1 / l2) ** 0.5)


def translate(rec: dict, dx: float, dy: float) -> None:
    for pts in iter_points(rec):
        for p in pts:
            p[0] += dx
            p[1] += dy


# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="src", required=True, help="directory written by extract.py")
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=float, default=6144.0, help="target square edge, metres")
    ap.add_argument("--bands", type=int, default=96, help="warp bands per axis")
    ap.add_argument("--min-scale", type=float, default=0.12,
                    help="hardest squeeze applied to the emptiest band")
    ap.add_argument("--max-scale", type=float, default=1.0,
                    help="loosest squeeze; 1.0 keeps the densest bands at true scale")
    ap.add_argument("--margin", type=float, default=None,
                    help="metres of the target box reserved for preserved cross-sections "
                         "(default: auto, the p99.5 corridor half-width)")
    ap.add_argument("--cross-section-scale", type=float, default=1.0,
                    help="1.0 keeps carriageway/deck widths exactly true; lower it if a "
                         "hard-collapsed region leaves neighbouring roads overlapping")
    ap.add_argument("--min-elongation", type=float, default=3.0,
                    help="objects below this length:width ratio (buildings, junction "
                         "plazas, intersection polygons) are translated rigidly instead")
    ap.add_argument("--no-rewiden", action="store_true",
                    help="treat every object as rigid — skips axial shortening (debug)")
    args = ap.parse_args()

    layer_files = sorted(glob.glob(os.path.join(args.src, "*.json")) +
                         glob.glob(os.path.join(args.src, "*.jsonl")))
    layer_files = [p for p in layer_files
                   if os.path.basename(p) not in ("manifest.json", "warp.json")]
    if not layer_files:
        print(f"no layer files in {args.src}", file=sys.stderr)
        return 2

    layers: dict[str, list[dict]] = {}
    headers: dict[str, dict] = {}
    for path in layer_files:
        name = os.path.basename(path).rsplit(".", 1)[0]
        if path.endswith(".jsonl"):
            with open(path, encoding="utf-8") as fh:
                layers[name] = [json.loads(line) for line in fh if line.strip()]
            headers[name] = {}
        else:
            with open(path, encoding="utf-8") as fh:
                blob = json.load(fh)
            layers[name] = blob.get("features", [])
            headers[name] = blob.get("header", {})
        print(f"loaded {name}: {len(layers[name])} features")

    # --- density histograms (feature centroids, not vertices: a dense mesh must not
    #     outvote a dense *neighbourhood*) -----------------------------------------
    cents: list[tuple[float, float, float]] = []   # x, y, weight
    xs: list[float] = []
    ys: list[float] = []
    for name, feats in layers.items():
        w = DENSITY_WEIGHTS.get(name, 0.25)
        for rec in feats:
            c = centroid(rec)
            if c is None:
                continue
            cents.append((c[0], c[1], w))
            for pts in iter_points(rec):
                for p in pts:
                    xs.append(p[0])
                    ys.append(p[1])
    if not xs:
        print("no geometry found", file=sys.stderr)
        return 2

    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys), max(ys)
    print(f"real extent: X {x_hi - x_lo:.0f} m, Y {y_hi - y_lo:.0f} m "
          f"-> target {args.size:.0f} x {args.size:.0f} m")

    def histogram(lo, hi, index):
        h = [0.0] * args.bands
        bw = (hi - lo) / args.bands
        for c in cents:
            i = int((c[index] - lo) / bw)
            h[min(max(i, 0), args.bands - 1)] += c[2]
        return h, bw

    # --- margin for preserved cross-sections -----------------------------------
    # The warp positions *centres*; a corridor then keeps its true half-width on each
    # side of that centre, so warping to the full box edge would let a wide slab sit
    # half outside it.  Inset the warp by a margin taken from the corridor half-widths
    # actually present.  It is the *max* rather than a percentile — a single wide slab
    # sitting on the edge is exactly the case that breaks the fit — but capped at 5% of
    # the box so one freak feature cannot squeeze the whole map.
    hx, bwx = histogram(x_lo, x_hi, 0)
    hy, bwy = histogram(y_lo, y_hi, 1)

    if args.margin is not None:
        margin = args.margin
    else:
        # Provisional full-size warp, used only to see *which* features land near an
        # edge.  Sizing the margin off those, rather than off the widest feature
        # anywhere in the map, keeps a huge inland apron from shrinking the whole world.
        pv_x = AxisWarp(x_lo, x_hi, solve_scales(hx, bwx, args.size,
                                                 args.min_scale, args.max_scale))
        pv_y = AxisWarp(y_lo, y_hi, solve_scales(hy, bwy, args.size,
                                                 args.min_scale, args.max_scale))
        edge = args.size / 2.0
        margin = 0.0
        for name in CORRIDOR_LAYERS & set(layers):
            for rec in layers[name]:
                c = centroid(rec)
                if c is None:
                    continue
                wx, wy = pv_x(c[0]), pv_y(c[1])
                if min(edge - abs(wx), edge - abs(wy)) > args.size * 0.05:
                    continue                      # comfortably inland; can't overhang
                ux, uy, elong = principal_axis(rec)
                if elong < args.min_elongation:   # rigid blob: its whole half-extent
                    hw = max(max(abs(p[0] - c[0]), abs(p[1] - c[1]))
                             for pts in iter_points(rec) for p in pts)
                else:                             # shortened: only the cross-section
                    hw = max(abs((p[0] - c[0]) * -uy + (p[1] - c[1]) * ux)
                             for pts in iter_points(rec) for p in pts)
                margin = max(margin, hw)
        margin = min(margin, args.size * 0.05)

    inner = max(args.size - 2.0 * margin, args.size * 0.5)
    print(f"cross-section margin: {margin:.1f} m -> warp target {inner:.0f} m")

    warp_x = AxisWarp(x_lo, x_hi, solve_scales(hx, bwx, inner, args.min_scale, args.max_scale))
    warp_y = AxisWarp(y_lo, y_hi, solve_scales(hy, bwy, inner, args.min_scale, args.max_scale))

    for axis, w in (("X", warp_x), ("Y", warp_y)):
        print(f"  {axis}: span {w.total:.0f} m, "
              f"band scales min {min(w.scales):.3f} / max {max(w.scales):.3f}")

    # --- apply -----------------------------------------------------------------
    os.makedirs(args.out, exist_ok=True)
    stats = {}

    mode_counts: dict[str, dict[str, int]] = {}

    for name, feats in layers.items():
        mode = ("corridor" if name in CORRIDOR_LAYERS else
                "rigid" if name in RIGID_LAYERS else "field")
        counts = {"rigid": 0, "shortened": 0, "field": 0}

        for rec in feats:
            if mode == "field":
                for pts in iter_points(rec):
                    for p in pts:
                        p[0] = warp_x(p[0])
                        p[1] = warp_y(p[1])
                counts["field"] += 1
                continue

            c = centroid(rec)
            if c is None:
                continue
            ux, uy, elong = principal_axis(rec)

            if mode == "rigid" or args.no_rewiden or elong < args.min_elongation:
                # authored model, or a compact blob (junction plaza, 交差部 polygon):
                # translate it whole, shape and size completely untouched
                translate(rec, warp_x(c[0]) - c[0], warp_y(c[1]) - c[1])
                counts["rigid"] += 1
                continue

            # Elongated object (road slab, rail corridor, long bridge span): shorten it
            # along its own axis, keep its cross-section exactly.
            #
            # In the feature's local frame (u = long axis, v = across), the *axial*
            # coordinate is taken from the warped point — so a road spanning bands of
            # different scale still compresses non-uniformly along its length — while
            # the *across* coordinate is copied verbatim from the original.  Nothing
            # perpendicular is ever scaled, so a 15 m carriageway stays 15 m wide with
            # no gain factor to tune and nothing to clamp.
            vx, vy = -uy, ux
            wcx, wcy = warp_x(c[0]), warp_y(c[1])
            for pts in iter_points(rec):
                for p in pts:
                    across = (p[0] - c[0]) * vx + (p[1] - c[1]) * vy
                    across *= args.cross_section_scale
                    wx, wy = warp_x(p[0]), warp_y(p[1])
                    along = (wx - wcx) * ux + (wy - wcy) * uy
                    p[0] = wcx + along * ux + across * vx
                    p[1] = wcy + along * uy + across * vy
            counts["shortened"] += 1

        mode_counts[name] = counts

        header = dict(headers.get(name) or {})
        header.update({"layer": name, "compressed": True,
                       "compression_mode": mode,
                       "target_size_m": args.size})
        out_path = os.path.join(args.out, f"{name}.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({"header": header, "features": feats}, fh, ensure_ascii=False)
        stats[name] = {"features": len(feats), "mode": mode,
                       "treated_as": mode_counts.get(name, {}),
                       "bytes": os.path.getsize(out_path)}
        print(f"[{name:9s}] {mode:8s} {mode_counts.get(name, {})} "
              f"-> {out_path} ({stats[name]['bytes'] / 1e6:.1f} MB)")

    warp = {
        "attribution": "Data: Project PLATEAU (MLIT), CC BY 4.0",
        "target_size_m": args.size,
        "real_extent_m": {"x": x_hi - x_lo, "y": y_hi - y_lo},
        "rule": "positions compress; cross-sections and Z do not",
        "cross_section_margin_m": round(margin, 2),
        "warp_target_m": round(inner, 2),
        "modes": {"corridor": sorted(CORRIDOR_LAYERS),
                  "rigid": sorted(RIGID_LAYERS),
                  "field": sorted(FIELD_LAYERS)},
        "min_elongation": args.min_elongation,
        "cross_section_scale": args.cross_section_scale,
        "x": warp_x.to_json(),
        "y": warp_y.to_json(),
        "layers": stats,
    }
    with open(os.path.join(args.out, "warp.json"), "w", encoding="utf-8") as fh:
        json.dump(warp, fh, ensure_ascii=False, indent=2)
    print(f"wrote {os.path.join(args.out, 'warp.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
