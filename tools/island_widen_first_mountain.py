#!/usr/bin/env python3
"""island_widen_first_mountain.py -- give the shrine plateau a 1:3 east face (2026-09-17, user decision).

    godot --headless --path . --script tools/godot/dump_height_grid.gd -- <out.f32> -2200 -2000 1301 1351 2.0
    python3 tools/island_widen_first_mountain.py <in.f32> <out.f32> [--preview <png>]
    godot --headless --path . --script tools/godot/apply_height_grid.gd -- res://assets/terrain3d/island <out.f32> -2200 -2000 1301 1351 2.0

WHY. The "first mountain" of the two-phase shrine touge is the ~281 m plateau lobe on the massif's
south-west (centre plan (-1250, 770)). Its east face fell at ~62% on average and up to 200% on the
ridges `shape_terrain.gd` laid over it, so a road could only climb it in tight hairpins cut metres into
ridges. The user chose to WIDEN the mountain east to a 1:3 (33%, ~18 deg) face, which moves its toe from
x ~ -500 to x ~ -110 and re-routes the three arterials that ran along the old foot.

WHAT IT DOES, in plan metres (x east, y north; a Godot position is (x, h, -y)):
  * the plateau's own edge is measured per degree (first sample below `EDGE_Z`), not assumed round;
  * below that edge the target is `TOP - (r - edge) / 3`, eased onto the city floor at `FLOOR_Z` over
    `TOE_EASE` metres so the toe has no crease;
  * the face is RAISED to the target wherever it is lower (the widening) and LOWERED to it where a
    ridge stands low above it (a clean face for a benched road), blending to no cut at all by
    `3 * RIDGE_CUT` above it (the massif's own foot, which is not this mountain);
  * all of it only inside the east sector (`SECTOR_*`, degrees about the plateau centre, faded so the
    cone's own toe draws the outline -- a spatial clip drew a boxy apron) and west of `EAST_LIMIT_X`,
    a safety line that keeps the toe off chuo_dori;
  * the sea is never raised (a cell at or below 0 stays), so the coastline does not move.

NOT idempotent, on purpose refused instead: a soft blend moves a partially-weighted cell again on every
pass. The tool checks the full-strength cells first and refuses when they already sit on the target
(`--force` to apply anyway).
"""
import argparse, math, struct, sys, zlib
import numpy as np

X0, Y0, ST = -2200.0, 2000.0, 2.0          # plan x = X0 + i*ST, plan y = Y0 - j*ST (Godot z0 = -Y0)
NX, NY = 1301, 1351
C = (-1250.0, 770.0)                        # plateau centre, plan
TOP = 280.6                                 # plateau height (Godot Y)
EDGE_Z = 276.0
RUN = 3.0                                   # 1:3 face
FLOOR_Z = 0.6                               # the city floor (Godot Y)
TOE_EASE = 40.0
RIDGE_CUT = 30.0
SECTOR_FULL = (-35.0, 0.0)                  # degrees, 0 = east, +90 = north
SECTOR_FADE = 25.0
EAST_LIMIT_X = (-40.0, -100.0)              # weight 0 east of the first, 1 west of the second


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def plateau_edge(H):
    def h(x, y):
        i = int(round((x - X0) / ST)); j = int(round((Y0 - y) / ST))
        return float(H[j, i]) if 0 <= i < NX and 0 <= j < NY else -24.0
    edge = np.zeros(360)
    for d in range(360):
        a = math.radians(d); r = 0.0
        while r < 900.0 and h(C[0] + math.cos(a) * r, C[1] + math.sin(a) * r) >= EDGE_Z:
            r += ST
        edge[d] = r
    k = np.ones(15) / 15.0                  # +-7 deg circular average: an edge, not a coastline
    return np.convolve(np.concatenate([edge[-7:], edge, edge[:7]]), k, mode="valid"), edge


def widen(H):
    edge, raw = plateau_edge(H)
    jj, ii = np.mgrid[0:NY, 0:NX]
    x = X0 + ii * ST; y = Y0 - jj * ST
    dx, dy = x - C[0], y - C[1]
    r = np.hypot(dx, dy)
    deg = np.degrees(np.arctan2(dy, dx))
    e = np.interp(np.mod(deg, 360.0), np.arange(361), np.append(edge, edge[0]))
    # The face is SHAPED from the smoothed edge but only ever APPLIED past the raw one (+ a cell): a cell
    # between the two stands at the plateau height, and lowering it would move the measured edge.
    e_raw = np.interp(np.mod(deg, 360.0), np.arange(361), np.append(raw, raw[0])) + 2.0 * ST
    # The face starts just UNDER `EDGE_Z`: starting it at TOP raised the first ~13 m past the edge above
    # the threshold the edge is measured with, so the edit moved its own reference and a second run
    # shifted the whole face by ~4 m.
    cone = (EDGE_Z - 0.5) - np.maximum(r - e, 0.0) / RUN
    # ease onto the floor: a smooth max of (cone, FLOOR_Z) over TOE_EASE
    k = TOE_EASE / RUN
    target = FLOOR_Z + 0.5 * ((cone - FLOOR_Z) + np.sqrt((cone - FLOOR_Z) ** 2 + k * k)) - 0.5 * k
    target = np.maximum(target, FLOOR_Z)
    lo, hi = SECTOR_FULL
    w = smoothstep(lo - SECTOR_FADE, lo, deg) * (1.0 - smoothstep(hi, hi + SECTOR_FADE, deg))
    w *= smoothstep(EAST_LIMIT_X[0], EAST_LIMIT_X[1], x)
    w *= (r > np.maximum(e, e_raw))         # the plateau top itself is not touched
    w *= (H > 0.0)                          # the sea is not raised
    raise_ = np.maximum(target - H, 0.0)
    over = H - target
    # Ground standing `over` above the target keeps `over * smoothstep(RIDGE_CUT/2, 3*RIDGE_CUT, over)`:
    # a low ridge on the face is cut to it, the massif's own foot is kept, and the kept height GROWS
    # smoothly between the two. A cut that simply stopped at `2*RIDGE_CUT` stood a 60 m wall there.
    kept = over * smoothstep(0.5 * RIDGE_CUT, 3.0 * RIDGE_CUT, over)
    cut = np.where(over > 0.0, over - kept, 0.0)
    # ...and only on the plateau's own south-east/east face. North of east the ground above the target is
    # the MASSIF's foot; cutting its lower part steepened the rest (2989 new >100% cells, all at y ~ 900).
    cut *= 1.0 - smoothstep(-10.0, 0.0, deg)
    out = H + w * (raise_ - cut)
    return out.astype(np.float32), w, target


def png(path, rgb):
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[r].tobytes() for r in range(h))
    def ch(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                           + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--preview", default="")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    H = np.fromfile(a.src, dtype=np.float32).reshape(NY, NX)
    out, w, target = widen(H)
    core = (w > 0.999) & (target > FLOOR_Z + 5.0)
    on = float(np.mean(np.abs(H[core] - target[core]) < 0.25)) if core.any() else 0.0
    print("full-strength face cells already on the target: %.0f%%" % (100.0 * on))
    if on > 0.9 and not a.force:
        print("REFUSED: the face is already widened (use --force to blend again)")
        return 2
    d = out - H
    print("raised %d cells (max %.1f m), lowered %d cells (max %.1f m), weight>0 on %d"
          % ((d > 0.01).sum(), d.max(), (d < -0.01).sum(), -d.min(), (w > 0).sum()))
    out.tofile(a.dst)
    if a.preview:
        g = np.clip(out / 400.0, 0, 1)
        rgb = np.stack([60 + g * 195, 90 + g * 165, 40 + g * 215], -1).astype(np.uint8)
        rgb[out <= 0.3] = (10, 20, 70)
        band = (np.floor(out / 20.0) % 2 == 0) & (out > 0.3)
        rgb[band] = (rgb[band] * 0.85).astype(np.uint8)
        rgb[(d > 0.5)] = (np.array(rgb[(d > 0.5)]) * [1.0, 0.7, 0.7]).astype(np.uint8)
        png(a.preview, rgb[::2, ::2].copy())
    return 0


if __name__ == "__main__":
    sys.exit(main())
