#!/usr/bin/env python3
"""Generate the PADDY SOIL terrain surface (user, 2026-09-25: "for the block, please use soil on ground"), packed the
way Terrain3D wants it, beside `make_urban_texture.py`'s aggregate:

    assets/terrain3d/textures/soil_alb_ht.png   RGB = albedo, A = height
    assets/terrain3d/textures/soil_nrm_rgh.png  RGB = normal (tangent space, +Y up), A = roughness

Dark grey-brown wet paddy soil (田んぼの土) with shallow FURROWS along the texture's +X -- which the terrain lays
along world X, i.e. along the long east-west side of the island's 100 x 300 m paddy sections -- `FURROWS` per tile.
Tileable; the tile's size in the world is the texture asset's `uv_scale` (terrain_assets.tres "Soil", id 5).

    python3 tools/make_soil_texture.py
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from make_urban_texture import SIZE, OUT, _tileable_noise

WET = np.array([0.255, 0.215, 0.170])    # the soil between the rows, damp
DRY = np.array([0.365, 0.315, 0.250])    # the ridge tops, drier
FURROWS = 8                              # per tile (uv_scale 0.25 -> a 4 m tile -> a row every 0.5 m)


def main() -> int:
    rng = np.random.default_rng(20260925)
    grain = rng.random((SIZE, SIZE)).astype(np.float32)
    clods = _tileable_noise(rng, SIZE, 128)
    patch = _tileable_noise(rng, SIZE, 8)
    v = np.linspace(0.0, 1.0, SIZE, endpoint=False)[:, None]
    # furrows run along +X (rows vary with Y); a little wobble so they are hand-made, not ruled
    wob = 0.015 * np.sin(2 * np.pi * (np.linspace(0, 1, SIZE, endpoint=False)[None, :] * 3.0))
    ridge = 0.5 + 0.5 * np.cos(2 * np.pi * FURROWS * (v + wob))
    height = 0.55 * ridge + 0.30 * clods + 0.15 * grain
    height = (height - height.min()) / (height.max() - height.min())
    t = np.clip(0.65 * ridge + 0.35 * patch, 0.0, 1.0)[:, :, None]
    albedo = WET[None, None, :] * (1 - t) + DRY[None, None, :] * t
    albedo = albedo * (0.90 + 0.10 * grain[:, :, None])
    albedo = np.clip(albedo, 0.0, 1.0)
    Image.fromarray((np.dstack([albedo, height]) * 255).round().astype(np.uint8), mode="RGBA").save(
        "%s/soil_alb_ht.png" % OUT)
    strength = 5.0
    dzdx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * strength
    dzdy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * strength
    nx, ny, nz = -dzdx, -dzdy, np.ones_like(height)
    inv = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    normal = np.dstack([nx * inv, ny * inv, nz * inv]) * 0.5 + 0.5
    rough = np.clip(0.92 - 0.10 * (1 - ridge), 0.0, 1.0)      # damp furrows a touch less rough
    Image.fromarray((np.dstack([normal, rough]) * 255).round().astype(np.uint8), mode="RGBA").save(
        "%s/soil_nrm_rgh.png" % OUT)
    print("wrote %s/soil_alb_ht.png and soil_nrm_rgh.png (%dx%d); albedo mean %s" % (
        OUT, SIZE, SIZE, np.round(albedo.reshape(-1, 3).mean(0) * 255, 1)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
