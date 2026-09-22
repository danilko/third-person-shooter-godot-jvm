"""What a Japanese facade's ALBEDO actually measures, from the user's PLATEAU reference (PLAN.md 3.18p).

    blender -b /data/danilko/concept_arts/japan_city.blend --python blender/tools/measure_plateau_facades.py

Read-only, and outside the repo by design: PLATEAU's own textures are not redistributed here (the licence audit),
only the NUMBERS they yield, which is what `tools/building_kit/retone_downtown_kit.py`'s tone targets are set
from. This exists because those numbers were previously carried in a comment with no way to re-derive them -- and
a re-measurement of the same 3048 materials came out ~10 luminance levels darker than the comment said.

Method, stated because it is what makes the number arguable: a facade material here is TEXTURED, so its tone is
the mean of its own base-colour IMAGE (not a constant base colour -- only 6 materials in the file have one).
Blender holds image pixels LINEAR, so each is converted to an sRGB byte before averaging, and the tone is the
Rec.709 luminance of the three channel means. Large images are sampled (a mean needs no more).
"""
import numpy as np

import bpy

SAMPLE = 200000        # texels per image: a mean is stable long before this


def srgb(a):
    a = np.clip(a, 0.0, 1.0)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * a ** (1 / 2.4) - 0.055) * 255.0


def main():
    seen, tones = {}, []
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is None:
            continue
        slot = bsdf.inputs.get("Base Color")
        if slot is None or not slot.is_linked:
            continue
        src = slot.links[0].from_node
        if src.type != "TEX_IMAGE" or src.image is None:
            continue
        img = src.image
        if img.name in seen:
            tones.append(seen[img.name])
            continue
        try:
            px = np.array(img.pixels[:], dtype=np.float32)
        except Exception:
            continue
        if px.size < 16:
            continue
        px = px.reshape(-1, img.channels)[:, :3]
        if px.shape[0] > SAMPLE:
            px = px[:: max(1, px.shape[0] // SAMPLE)]
        b = srgb(px)
        r, g, bl = (float(b[:, i].mean()) for i in range(3))
        seen[img.name] = (0.2126 * r + 0.7152 * g + 0.0722 * bl, r - bl)
        tones.append(seen[img.name])

    lum = np.array([t[0] for t in tones])
    rmb = np.array([t[1] for t in tones])
    print("[plateau_facades] %d textured facade materials over %d distinct images" % (lum.size, len(seen)))
    for p in (5, 10, 25, 35, 50, 65, 75, 90, 95):
        print("[plateau_facades]   p%-3d %6.1f" % (p, np.percentile(lum, p)))
    print("[plateau_facades]   mean %6.1f   R-B mean %+.1f (Tokyo is GREY: the variation is in how light)"
          % (lum.mean(), rmb.mean()))


main()
