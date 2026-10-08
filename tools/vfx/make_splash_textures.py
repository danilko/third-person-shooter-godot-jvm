#!/usr/bin/env python3
"""Make the water-splash particle textures (ParticleManager WATER pool, WorldSystems.tscn), once.

    python3 tools/vfx/make_splash_textures.py [--kenney /data/danilko/game_assets/kenney_visual_cc0/particle-pack]

  splash_ring.png   the ripple ring that spreads on the surface   (Kenney Particle Pack circle_04, CC0)
  splash_drop.png   a soft round droplet / spray blob             (Kenney Particle Pack circle_05, CC0)
Kenney's shapes are white on transparency; luminance x alpha becomes the alpha and the colour is white, so the
particle colour ramp tints and fades them. 128 px RGBA.
"""
import argparse, os
import numpy as np
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, "assets", "vfx", "splash")


def convert(src, dst, n=128):
    im = Image.open(src).convert("RGBA").resize((n, n), Image.LANCZOS)
    a = np.asarray(im, np.float64) / 255
    alpha = a[..., :3].mean(axis=2) * a[..., 3]
    out = np.zeros((n, n, 4), np.uint8)
    out[..., :3] = 255
    out[..., 3] = np.clip(alpha * 255, 0, 255).astype(np.uint8)
    Image.fromarray(out, "RGBA").save(dst)
    print("wrote", os.path.relpath(dst, REPO))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kenney", default="/data/danilko/game_assets/kenney_visual_cc0/particle-pack")
    k = os.path.join(ap.parse_args().kenney, "PNG (Transparent)")
    os.makedirs(OUT, exist_ok=True)
    convert(os.path.join(k, "circle_04.png"), os.path.join(OUT, "splash_ring.png"))
    convert(os.path.join(k, "circle_05.png"), os.path.join(OUT, "splash_drop.png"))


if __name__ == "__main__":
    main()
