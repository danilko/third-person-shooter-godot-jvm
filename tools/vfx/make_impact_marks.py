#!/usr/bin/env python3
"""Generate the impact-mark decal textures (world.manager.DecalManager), once.

    python3 tools/vfx/make_impact_marks.py [--kenney /data/danilko/game_assets/kenney_visual_cc0/particle-pack]

One mark per KIND of hit, never per surface (the surface only tints it, DecalManager.tintFor):
  impact_hole.png    a bullet: a dark pit with a soft chipped rim (generated here, seeded, MIT)
  impact_slash.png   a blade / axe blow: three parallel cuts   (Kenney Particle Pack scratch_01, CC0)
  impact_scorch.png  an explosion on the ground: a burnt star  (Kenney Particle Pack scorch_01, CC0)
Kenney's particle textures are white shapes on transparency, made to be tinted: their luminance x alpha becomes the
mark's alpha and the colour is near-black, so the decal darkens what it lands on. 256 px RGBA (the scorch 512).
"""
import argparse, os
import numpy as np
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, "assets", "vfx", "decals")


def smooth(e0, e1, v):
    t = np.clip((v - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def hole(n=256, seed=7):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    x = (x + 0.5) / n * 2 - 1
    y = (y + 0.5) / n * 2 - 1
    r = np.hypot(x, y)
    th = np.arctan2(y, x)
    g = Image.fromarray((rng.random((11, 11)) * 255).astype(np.uint8)).resize((n, n), Image.BICUBIC)
    noise = np.asarray(g, np.float64) / 255
    jag = r + 0.07 * (noise - 0.5)
    chips = (np.sin(th * 7 + 1.3) * 0.5 + 0.5) ** 6 * smooth(0.5, 0.2, r)
    a = np.maximum.reduce([smooth(0.55, 0.22, jag) * 0.55 * (0.6 + 0.4 * noise),   # soot / dust ring
                           chips * 0.45,
                           smooth(0.3, 0.16, jag) * 0.85,                           # crushed rim
                           smooth(0.15, 0.08, jag)])                                # the pit
    shade = np.where(r < 0.16, 0.04, 0.22 + 0.12 * noise)                           # pit black, rim grey
    rgb = np.dstack([shade] * 3)
    return Image.fromarray((np.dstack([rgb, a]) * 255 + 0.5).astype(np.uint8), "RGBA")


def from_kenney(path, colour, strength, size):
    im = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
    p = np.asarray(im, np.float64) / 255
    a = np.clip(p[..., :3].mean(axis=2) * p[..., 3] * strength, 0, 1)
    rgb = np.ones((size, size, 3)) * np.array(colour)
    return Image.fromarray((np.dstack([rgb, a]) * 255 + 0.5).astype(np.uint8), "RGBA")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kenney", default="/data/danilko/game_assets/kenney_visual_cc0/particle-pack")
    a = ap.parse_args()
    src = os.path.join(a.kenney, "PNG (Transparent)")
    os.makedirs(OUT, exist_ok=True)
    hole().save(os.path.join(OUT, "impact_hole.png"))
    from_kenney(os.path.join(src, "scratch_01.png"), (0.10, 0.09, 0.08), 1.6, 256).save(
        os.path.join(OUT, "impact_slash.png"))
    from_kenney(os.path.join(src, "scorch_01.png"), (0.04, 0.035, 0.03), 1.4, 512).save(
        os.path.join(OUT, "impact_scorch.png"))
    for f in ("impact_hole", "impact_slash", "impact_scorch"):
        print(f"{f}.png")


if __name__ == "__main__":
    main()
