#!/usr/bin/env python3
"""Generate the URBAN ground surface: the fine grey aggregate a city block's own yard, back lot and
forecourt is, packed the way Terrain3D wants it (PLAN.md 3.18(c3)).

The project ships two PBR sets -- Ground037 (a dirt) and Rock023 -- plus a generated sand. Neither works
here and both were tried on screen first: Ground037's albedo is strongly yellow-green (measured mean
155/150/92), so any tint of it reads as earth; Rock023 is neutral (140/139/137) but its features are
BOULDER-scale, and stretched over a block it reads as cracked slabs rather than ground. What a Japanese
back lot, 駐車場 apron or unbuilt block interior actually is, is fine grey aggregate -- low contrast, no
large features, so it disappears under the eye instead of drawing it.

    <name>_alb_ht.png   RGB = albedo, A = height
    <name>_nrm_rgh.png  RGB = normal (tangent space, +Y up), A = roughness

    python3 tools/make_urban_texture.py                  # the generated aggregate (the original)
    python3 tools/make_urban_texture.py --from-footway   # the FOOTWAY's own concrete (shipped, 2026-09-22)

**`--from-footway` is what ships** (user, 2026-09-22: "use the same fill for a street block's ground as the
sidewalk; currently the two differ, prefer one"). It packs the footway material's own maps
(`M_ConcreteTile` = `T_Concrete_{BaseColor,Normal,ORM}`, downtown kit) into Terrain3D's two layers, resized to the
terrain array's size: albedo + a height from the albedo's luminance, and the normal + the ORM's roughness. The
footway's TINT and TILE live on the texture asset (`terrain_assets.tres` "Urban": `albedo_color` = the material's
`albedo_color`, `uv_scale` = its `uv1_scale`), so the kerb-to-door surface is one material seen twice.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

SIZE = 1024
OUT = "assets/terrain3d/textures"

BASE = np.array([0.470, 0.474, 0.487])   # mid grey, a shade cool: concrete/asphalt aggregate
DARK = np.array([0.300, 0.302, 0.315])   # the stones between


def _tileable_noise(rng, size, cells):
    """Value noise that wraps, so the texture tiles without a seam (the sand generator's, shared idea)."""
    g = rng.random((cells, cells)).astype(np.float32)
    g = np.pad(g, ((0, 1), (0, 1)), mode="wrap")
    ys = np.linspace(0, cells, size, endpoint=False)
    xs = np.linspace(0, cells, size, endpoint=False)
    y0 = ys.astype(int); x0 = xs.astype(int)
    fy = (ys - y0)[:, None]; fx = (xs - x0)[None, :]
    fy = fy * fy * (3 - 2 * fy); fx = fx * fx * (3 - 2 * fx)
    a = g[y0][:, x0]; b = g[y0][:, x0 + 1]
    c = g[y0 + 1][:, x0]; d = g[y0 + 1][:, x0 + 1]
    return (a * (1 - fx) * (1 - fy) + b * fx * (1 - fy)
            + c * (1 - fx) * fy + d * fx * fy)


FOOTWAY = "assets/world_source/kits/quaternius_downtown_city/textures/T_Concrete_%s.png"


def from_footway() -> int:
    """Pack the footway's concrete into the Terrain3D layers (see the module docstring)."""
    def load(name, mode):
        im = Image.open(FOOTWAY % name).convert(mode)
        if im.size != (SIZE, SIZE):
            im = im.resize((SIZE, SIZE), Image.LANCZOS)
        return np.asarray(im).astype(np.float32) / 255.0

    albedo = load("BaseColor", "RGB")
    normal = load("Normal", "RGB")
    orm = load("ORM", "RGB")
    lum = albedo @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    height = (lum - lum.min()) / max(1e-6, float(lum.max() - lum.min()))
    alb_ht = np.dstack([albedo, height])
    Image.fromarray((alb_ht * 255).round().astype(np.uint8), mode="RGBA").save("%s/urban_alb_ht.png" % OUT)
    nrm_rgh = np.dstack([normal, orm[..., 1]])
    Image.fromarray((nrm_rgh * 255).round().astype(np.uint8), mode="RGBA").save("%s/urban_nrm_rgh.png" % OUT)
    print("wrote %s/urban_alb_ht.png and urban_nrm_rgh.png (%dx%d) from the footway's T_Concrete" % (OUT, SIZE, SIZE))
    print("  albedo mean %s, roughness mean %.2f" % (np.round(albedo.reshape(-1, 3).mean(0) * 255, 1),
                                                    float(orm[..., 1].mean())))
    return 0


def main() -> int:
    import sys
    if "--from-footway" in sys.argv:
        return from_footway()
    rng = np.random.default_rng(20260921)

    grain = rng.random((SIZE, SIZE)).astype(np.float32)       # the aggregate itself
    chips = _tileable_noise(rng, SIZE, 256)                   # stones, a few cm across
    patch = _tileable_noise(rng, SIZE, 16)                    # wear, very gentle

    # THE LARGE SCALE IS DELIBERATELY WEAK. A ground texture seen from a metre away and from thirty must
    # not grow features at the far end: that is what made the rock look like slabs.
    height = 0.55 * chips + 0.30 * grain + 0.15 * patch
    height = (height - height.min()) / (height.max() - height.min())

    shade = 0.86 + 0.14 * height
    albedo = BASE[None, None, :] * shade[:, :, None]
    mix = (0.35 * grain + 0.25 * chips)[:, :, None]
    albedo = albedo * (1 - mix) + DARK[None, None, :] * mix
    albedo = np.clip(albedo, 0.0, 1.0)

    alb_ht = np.dstack([albedo, height]).astype(np.float32)
    Image.fromarray((alb_ht * 255).astype(np.uint8), mode="RGBA").save("%s/urban_alb_ht.png" % OUT)

    strength = 4.0
    dzdx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * strength
    dzdy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * strength
    nx, ny, nz = -dzdx, -dzdy, np.ones_like(height)
    inv = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    normal = np.dstack([nx * inv, ny * inv, nz * inv]) * 0.5 + 0.5
    roughness = np.clip(0.80 - 0.12 * height, 0.0, 1.0)
    nrm_rgh = np.dstack([normal, roughness]).astype(np.float32)
    Image.fromarray((nrm_rgh * 255).astype(np.uint8), mode="RGBA").save("%s/urban_nrm_rgh.png" % OUT)

    print("wrote %s/urban_alb_ht.png and urban_nrm_rgh.png (%dx%d)" % (OUT, SIZE, SIZE))
    print("  albedo mean %s (neutral: R-B %.3f)" % (
        np.round(albedo.reshape(-1, 3).mean(0) * 255, 1),
        float(albedo[..., 0].mean() - albedo[..., 2].mean()) * 255))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
