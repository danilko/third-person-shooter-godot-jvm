"""What colour a Japanese WALL is, per building, from the user's PLATEAU reference (PLAN.md 3.19(e)).

    blender -b /data/danilko/concept_arts/japan_city.blend --python blender/tools/measure_plateau_wall_colours.py \
        -- [--k 8] [--json assets/world_source/buildings/plateau_wall_palette.json]

The sibling of `measure_plateau_facades.py`, which averages every texel of every facade IMAGE -- roof and wall
together, one number per image -- and so could only answer "how light". This one answers "what colour": for each
building it samples its texture only where its WALLS are (points spread over the vertical faces by area, looked up
through that face's own UVs), so a grey concrete roof cannot pull a beige tile building towards grey. The per
building colours are then clustered (k-means in CIE L*a*b*, so a cluster is a colour a person would call one
colour) and each cluster reports its sRGB centre and its SHARE of the buildings. That palette + share is what
`tools/building_kit/retone_downtown_kit.py` tints the facade tones to, and what `tools/island_buildings.py` draws
from, so the city's mixture IS central Tokyo's.

Read-only and outside the repo: only these numbers enter it (CREDITS.md "Real-world data"). PLATEAU facades are
aerial photogrammetry, so a sampled colour carries the day's light and some shadow; it is a palette, not an
albedo measurement, and the darkest cluster is partly shade.
"""
import json
import random
import sys

import numpy as np

import bpy

SAMPLES_PER_BUILDING = 160
MIN_WALL_M2 = 20.0


def srgb_byte(lin):
    lin = np.clip(lin, 0.0, 1.0)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055) * 255.0


def to_lab(rgb255):
    c = np.asarray(rgb255, float) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


_PIX = {}


def pixels(img):
    if img.name not in _PIX:
        try:
            a = np.array(img.pixels[:], dtype=np.float32)
            _PIX[img.name] = a.reshape(img.size[1], img.size[0], img.channels)[..., :3] if a.size else None
        except Exception:
            _PIX[img.name] = None
    return _PIX[img.name]


def image_of(mat):
    if mat is None or not mat.use_nodes:
        return None
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            s = n.inputs.get("Base Color")
            if s is not None and s.is_linked and s.links[0].from_node.type == "TEX_IMAGE":
                return s.links[0].from_node.image
    return None


def wall_colour(o, rnd):
    me = o.data
    uv = me.uv_layers.active
    if uv is None:
        return None
    walls, areas = [], []
    for p in me.polygons:
        if abs(p.normal.z) < 0.3 and p.area > 0.05:
            walls.append(p)
            areas.append(p.area)
    if sum(areas) < MIN_WALL_M2:
        return None
    areas = np.array(areas) / sum(areas)
    got = []
    for pi in np.random.choice(len(walls), SAMPLES_PER_BUILDING, p=areas):
        p = walls[pi]
        img = image_of(me.materials[p.material_index] if p.material_index < len(me.materials) else None)
        if img is None:
            continue
        px = pixels(img)
        if px is None:
            continue
        loops = list(p.loop_indices)
        # a random point in a random fan triangle of the face
        k = rnd.randrange(1, len(loops) - 1)
        a, b, c = (np.array(uv.data[loops[i]].uv[:]) for i in (0, k, k + 1))
        r1, r2 = rnd.random(), rnd.random()
        if r1 + r2 > 1:
            r1, r2 = 1 - r1, 1 - r2
        t = a + r1 * (b - a) + r2 * (c - a)
        u, v = t[0] % 1.0, t[1] % 1.0
        h, w = px.shape[:2]
        got.append(px[min(h - 1, int(v * h)), min(w - 1, int(u * w))])
    if len(got) < SAMPLES_PER_BUILDING // 3:
        return None
    lin = np.median(np.array(got), axis=0)          # median: a window or a sign does not move it
    return srgb_byte(lin)


def kmeans(x, k, iters=60, seed=1):
    rng = np.random.default_rng(seed)
    c = x[rng.choice(len(x), k, replace=False)]
    for _ in range(iters):
        lab = np.argmin(((x[:, None, :] - c[None]) ** 2).sum(-1), 1)
        nc = np.array([x[lab == i].mean(0) if (lab == i).any() else c[i] for i in range(k)])
        if np.allclose(nc, c):
            break
        c = nc
    return c, lab


# The whole-facade median luminance `measure_plateau_facades.py` reads over the same file (roof + wall atlases,
# sRGB): the level the city's walls are LIFTED to. A wall sampled from an aerial photograph is mostly in shade,
# and our renderer shades it again, so the raw wall colour would double-count the shadow; the lift keeps every
# cluster's hue and its lightness ORDER, and moves the population median onto the de-lit facade median.
FACADE_MEDIAN_SRGB = 135.6


def from_lab(lab):
    L, a, b = lab
    fy = (L + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200
    f = np.array([fx, fy, fz])
    xyz = np.where(f ** 3 > 0.008856, f ** 3, (f - 16 / 116) / 7.787) * np.array([0.95047, 1.0, 1.08883])
    m = np.array([[3.2406, -1.5372, -0.4986], [-0.9689, 1.8758, 0.0415], [0.0557, -0.2040, 1.0570]])
    lin = np.clip(m @ xyz, 0, 1)
    return srgb_byte(lin)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    k = int(argv[argv.index("--k") + 1]) if "--k" in argv else 8
    out = argv[argv.index("--json") + 1] if "--json" in argv else None
    rnd = random.Random(7)
    np.random.seed(7)
    cols = []
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name.startswith("bldg"):
            c = wall_colour(o, rnd)
            if c is not None:
                cols.append(c)
    cols = np.array(cols)
    lab = to_lab(cols)
    print("[plateau_walls] %d buildings with a textured wall" % len(cols))
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    print("[plateau_walls] L* p10/50/90 %s   chroma p50/90 %s   mean sRGB %s"
          % (np.percentile(lab[:, 0], [10, 50, 90]).round(1), np.percentile(chroma, [50, 90]).round(1),
             cols.mean(0).round(1)))
    cen, labels = kmeans(lab, k)
    rows = []
    for i in range(k):
        sel = labels == i
        rgb = cols[sel].mean(0)
        rows.append({"srgb": [round(float(v), 1) for v in rgb], "share": round(float(sel.mean()), 4),
                     "L": round(float(cen[i][0]), 1), "a": round(float(cen[i][1]), 1),
                     "b": round(float(cen[i][2]), 1)})
    lift = float(to_lab([FACADE_MEDIAN_SRGB] * 3)[0]) - float(np.median(lab[:, 0]))
    for r in rows:
        r["lit_srgb"] = [round(float(v), 1) for v in from_lab((r["L"] + lift, r["a"], r["b"]))]
    rows.sort(key=lambda r: -r["share"])
    for r in rows:
        print("[plateau_walls]   share %5.1f%%  sRGB %5.1f %5.1f %5.1f   L* %5.1f a* %+5.1f b* %+5.1f"
              "   -> lifted %5.1f %5.1f %5.1f" % (100 * r["share"], *r["srgb"], r["L"], r["a"], r["b"], *r["lit_srgb"]))
    print("[plateau_walls] L* lift %+.1f (wall median onto the facade median %.1f)" % (lift, FACADE_MEDIAN_SRGB))
    doc = {"_comment": "Written by blender/tools/measure_plateau_wall_colours.py -- do not hand-edit. Numbers "
                       "measured from PLATEAU (MLIT, CC BY 4.0); no PLATEAU data is in the repo. `srgb` is the raw "
                       "wall colour, `lit_srgb` the same colour with L* lifted by `lift_L` (see the script).",
           "source": "PLATEAU LOD2, central Tokyo (third mesh 5339-35-85/86/95/96), wall faces only",
           "buildings": len(cols), "k": k, "lift_L": round(lift, 2), "chroma_p50": round(float(np.percentile(chroma, 50)), 2),
           "chroma_p90": round(float(np.percentile(chroma, 90)), 2), "clusters": rows}
    if out:
        open(out, "w").write(json.dumps(doc, indent=1) + "\n")


main()
