#!/usr/bin/env python3
"""Generate the bullet-hole decal textures, one per surface (DecalManager picks by SurfaceType).

    python3 tools/vfx/make_bullet_holes.py      # writes assets/vfx/decals/bullet_hole_<surface>.png

Generated, not downloaded (PLAN.md P2b: nothing in the CC0 packs at hand fits, and one sprite per surface does not
justify a pack). 128 px RGBA, the hole centred, transparent outside; the alpha is what the Decal projects. Seeded, so
a re-run is byte-identical. MIT (this project).

  stone  dark pit, a ring of chipped lighter dust round it, a few radial chips
  metal  small dark hole, a bright dented ring (bare metal), soft dark smudge
  wood   dark hole, splinter streaks along the grain (vertical), lighter torn fibres
  glass  small hole, white crushed ring, cracks radiating to the edge
Flesh gets no decal: a hole on a moving body would float (DecalManager skips it).
"""
import os
import numpy as np
from PIL import Image

N = 128
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   "assets", "vfx", "decals")


def grid():
    y, x = np.mgrid[0:N, 0:N].astype(np.float64)
    x = (x + 0.5) / N * 2 - 1
    y = (y + 0.5) / N * 2 - 1
    return x, y, np.hypot(x, y), np.arctan2(y, x)


def noise(rng, scale=8):
    """Smooth value noise in 0..1."""
    g = rng.random((scale + 1, scale + 1))
    img = Image.fromarray((g * 255).astype(np.uint8)).resize((N, N), Image.BICUBIC)
    return np.asarray(img, np.float64) / 255


def smooth(edge0, edge1, v):
    t = np.clip((v - edge0) / (edge1 - edge0), 0, 1)
    return t * t * (3 - 2 * t)


def compose(layers):
    """layers: list of (rgb tuple 0..1, alpha array), painted in order (over)."""
    rgb = np.zeros((N, N, 3)); a = np.zeros((N, N))
    for col, al in layers:
        al = np.clip(al, 0, 1)
        rgb = rgb * (1 - al[..., None]) * a[..., None] + np.array(col) * al[..., None]
        na = al + a * (1 - al)
        rgb = np.where(na[..., None] > 1e-6, rgb / np.maximum(na[..., None], 1e-6), 0)
        a = na
    return rgb, a


def save(name, rgb, a):
    img = np.dstack([np.clip(rgb, 0, 1), np.clip(a, 0, 1)])
    Image.fromarray((img * 255 + 0.5).astype(np.uint8), "RGBA").save(os.path.join(OUT, f"bullet_hole_{name}.png"))


def stone(rng):
    x, y, r, th = grid()
    n = noise(rng, 10)
    jag = r + 0.08 * (n - 0.5)
    chips = (np.sin(th * 7 + rng.random() * 6) * 0.5 + 0.5) ** 6 * smooth(0.55, 0.2, r)
    dust = smooth(0.62, 0.25, jag) * 0.7 + chips * 0.5
    ring = smooth(0.34, 0.2, jag) * 0.85
    pit = smooth(0.17, 0.09, jag)
    return compose([((0.78, 0.76, 0.72), dust * (0.6 + 0.4 * n)),
                    ((0.45, 0.43, 0.40), ring),
                    ((0.06, 0.06, 0.06), pit)])


def metal(rng):
    x, y, r, th = grid()
    n = noise(rng, 12)
    smudge = smooth(0.7, 0.2, r) * 0.45
    ring = smooth(0.30, 0.22, r) * smooth(0.08, 0.17, r)
    dent = smooth(0.24, 0.12, r) * 0.8
    hole = smooth(0.10, 0.06, r + 0.02 * (n - 0.5))
    return compose([((0.10, 0.10, 0.11), smudge),
                    ((0.30, 0.30, 0.32), dent),
                    ((0.66, 0.66, 0.68), ring * 0.8),
                    ((0.02, 0.02, 0.02), hole)])


def wood(rng):
    x, y, r, th = grid()
    n = noise(rng, 6)
    grain = np.abs(np.sin((x + 0.15 * (n - 0.5)) * 34)) ** 4
    split = smooth(0.85, 0.0, np.abs(y) * 0.9 + np.abs(x) * 2.6)          # torn along the grain (vertical)
    fibre = split * (0.5 + 0.5 * grain)
    burn = smooth(0.45, 0.15, r) * 0.7
    hole = smooth(0.16, 0.08, r + 0.06 * (n - 0.5))
    return compose([((0.86, 0.72, 0.52), fibre * 0.9),
                    ((0.22, 0.14, 0.08), burn),
                    ((0.05, 0.03, 0.02), hole)])


def glass(rng):
    x, y, r, th = grid()
    cracks = np.zeros((N, N))
    for k in range(9):
        a0 = rng.random() * 2 * np.pi
        wob = 0.08 * np.sin(r * 9 + k)
        d = np.abs(np.angle(np.exp(1j * (th - a0 - wob))))
        w = 0.012 + 0.025 * (1 - r)
        cracks = np.maximum(cracks, smooth(w, 0.0, d * r + 0.002) * smooth(0.95, 0.5, r) * (0.6 + 0.4 * rng.random()))
    ring_r = 0.35 + 0.1 * rng.random()
    rings = smooth(0.02, 0.0, np.abs(r - ring_r)) * 0.6 * (np.sin(th * 5) > -0.2)
    crush = smooth(0.24, 0.1, r) * 0.9
    hole = smooth(0.07, 0.04, r)
    return compose([((0.95, 0.97, 1.0), np.maximum(cracks, rings)),
                    ((0.92, 0.95, 0.98), crush),
                    ((0.05, 0.05, 0.06), hole)])


def main():
    os.makedirs(OUT, exist_ok=True)
    for i, (name, f) in enumerate([("stone", stone), ("metal", metal), ("wood", wood), ("glass", glass)]):
        rgb, a = f(np.random.default_rng(100 + i))
        save(name, rgb, a)
        print(f"bullet_hole_{name}.png  coverage {float((a > 0.05).mean()):.2f}")


if __name__ == "__main__":
    main()
