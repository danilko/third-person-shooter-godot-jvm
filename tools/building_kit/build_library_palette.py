#!/usr/bin/env python3
"""build_library_palette.py -- write the library materials from its palette (PLAN.md 3.6b step 2: one owner of a look).

    python3 tools/building_kit/build_library_palette.py [--check]

Reads `assets/world_source/kits/library/palette.json` and writes, for every entry, `materials/<name>.tres` (a
StandardMaterial3D, world-space triplanar so a mesh needs no UVs of its own), plus the textures this project
GENERATES itself (`textures/T_*.png`: shelf goods and two brand-neutral fascia bands; deterministic, CC0, ours).
AmbientCG sets are referenced where they sit (`textures/<set>_Color.jpg` ...). `--check` writes nothing and exits 1
when a file on disk differs from what this would write (so CI can catch a hand edit of a generated file).

The .tres are GENERATED: edit palette.json, never a .tres (a hand edit is overwritten, and --check fails on it).
"""
import json
import os
import random
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
KIT = os.path.join(ROOT, "assets", "world_source", "kits", "library")
RES = "res://assets/world_source/kits/library"


# ── generated textures (ours) ────────────────────────────────────────────────────────────────────────────────

def goods_texture(size=512, seed=7):
    """Shelf goods: four shelf rows of packages of random width and colour, with a lighter label band and a dark
    gap under each row. Wraps horizontally and vertically (a row never crosses the edge)."""
    from PIL import Image, ImageDraw
    rnd = random.Random(seed)
    img = Image.new("RGB", (size, size), (38, 38, 40))
    d = ImageDraw.Draw(img)
    rows = 4
    rh = size // rows
    palette = [(214, 60, 50), (240, 180, 40), (60, 140, 200), (80, 170, 90), (235, 235, 230), (200, 90, 160),
               (250, 130, 40), (40, 70, 140), (170, 40, 40), (230, 210, 150), (120, 190, 200), (60, 60, 60)]
    for r in range(rows):
        y0, y1 = r * rh + 4, (r + 1) * rh - 10
        x = 0
        while x < size:
            w = rnd.randint(10, 44)
            if x + w > size:
                w = size - x
            h = rnd.randint(int((y1 - y0) * 0.55), y1 - y0)
            c = rnd.choice(palette)
            d.rectangle([x + 1, y1 - h, x + w - 2, y1], fill=c)
            lab = tuple(min(255, int(v * 0.4 + 150)) for v in c)
            ly = y1 - h + int(h * rnd.uniform(0.25, 0.55))
            d.rectangle([x + 3, ly, x + w - 4, ly + max(3, h // 6)], fill=lab)
            x += w
        d.rectangle([0, y1 + 1, size, y1 + 9], fill=(150, 150, 152))   # the shelf lip
    return img


def fascia_texture(stripes, size=512):
    """A brand-neutral fascia: white, with horizontal stripes [(centre 0..1, height 0..1, rgb)], repeating."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (size, size), (244, 244, 240))
    d = ImageDraw.Draw(img)
    for c, h, rgb in stripes:
        y0, y1 = int((c - h / 2) * size), int((c + h / 2) * size)
        d.rectangle([0, y0, size, y1], fill=rgb)
    return img


GENERATED = {
    "T_Goods": goods_texture,
    "T_FasciaKonbini": lambda: fascia_texture([(0.2, 0.08, (0, 150, 140)), (0.34, 0.05, (245, 120, 20)),
                                                   (0.7, 0.08, (0, 150, 140)), (0.84, 0.05, (245, 120, 20))]),
    "T_FasciaGas": lambda: fascia_texture([(0.25, 0.1, (30, 70, 160)), (0.36, 0.03, (30, 70, 160)),
                                               (0.75, 0.1, (30, 70, 160)), (0.86, 0.03, (30, 70, 160))]),
}


# ── materials ───────────────────────────────────────────────────────────────────────────────────────────────

def fmt(v):
    return ("%.4f" % v).rstrip("0").rstrip(".") if "." in ("%.4f" % v) else str(v)


def color(c):
    c = list(c) + [1.0] * (4 - len(c))
    return "Color(%s)" % ", ".join(fmt(x) for x in c)


def material_tres(name, m):
    ext = []            # (path, id)

    def tex(path):
        rid = "%d_t" % (len(ext) + 1)
        ext.append((path, rid))
        return 'ExtResource("%s")' % rid

    props = ['resource_name = "%s"' % name, "cull_mode = 2"]
    col = m.get("color", [1, 1, 1])
    tr = m.get("transparent", False)
    if tr:
        props.append("transparency = 1")
    base = None
    if "tex" in m:
        base = RES + "/textures/" + m["tex"]
    elif "tex_path" in m:
        base = m["tex_path"]
    generated = "tex" in m and m["tex"] in GENERATED
    if base and m.get("albedo_tex", True):
        suffix = ".png" if generated else "_BaseColor.png" if "tex_path" in m else "_Color.jpg"
        props.append("albedo_texture = %s" % tex(base + suffix))
    props.insert(2, "albedo_color = %s" % color(col))
    if base and not generated and "tex_path" not in m:
        if os.path.exists(os.path.join(KIT, "textures", m["tex"] + "_Metalness.jpg")) and m.get("metallic", 0) > 0:
            props.append("metallic = %s" % fmt(m.get("metallic", 1.0)))
            props.append("metallic_texture = %s" % tex(base + "_Metalness.jpg"))
            props.append("metallic_texture_channel = 0")
        elif "metallic" in m:
            props.append("metallic = %s" % fmt(m["metallic"]))
        props.append("roughness_texture = %s" % tex(base + "_Roughness.jpg"))
        props.append("roughness_texture_channel = 0")
        props.append("normal_enabled = true")
        props.append("normal_texture = %s" % tex(base + "_NormalGL.jpg"))
    elif "tex_path" in m and m.get("orm"):
        props.append("metallic_texture = %s" % tex(base + "_ORM.png"))
        props.append("metallic_texture_channel = 2")
        props.append("roughness_texture = %s" % tex(base + "_ORM.png"))
        props.append("roughness_texture_channel = 1")
        props.append("normal_enabled = true")
        props.append("normal_texture = %s" % tex(base + "_Normal.png"))
    else:
        if "metallic" in m:
            props.append("metallic = %s" % fmt(m["metallic"]))
        props.append("roughness = %s" % fmt(m.get("roughness", 0.8)))
    if "emission" in m:
        props.append("emission_enabled = true")
        props.append("emission = %s" % color(m["emission"]))
        props.append("emission_energy_multiplier = %s" % fmt(m.get("emission_energy", 1.0)))
    if base:
        s = 1.0 / float(m.get("size_m", 1.0))
        props.append("uv1_scale = Vector3(%s, %s, %s)" % (fmt(s), fmt(s), fmt(s)))
        props.append("uv1_triplanar = true")
        props.append("uv1_world_triplanar = true")
        props.append("texture_filter = 5")
    head = '[gd_resource type="StandardMaterial3D" load_steps=%d format=3]\n\n' % (len(ext) + 1)
    body = "".join('[ext_resource type="Texture2D" path="%s" id="%s"]\n' % (p, i) for p, i in ext)
    return head + body + ("\n" if ext else "") + "[resource]\n" + "\n".join(props) + "\n"


def main(argv):
    check = "--check" in argv
    pal = json.load(open(os.path.join(KIT, "palette.json")))
    stale = []
    os.makedirs(os.path.join(KIT, "materials"), exist_ok=True)
    for tname, fn in GENERATED.items():
        path = os.path.join(KIT, "textures", tname + ".png")
        import io
        buf = io.BytesIO()
        fn().save(buf, "PNG", optimize=True)
        data = buf.getvalue()
        if not os.path.exists(path) or open(path, "rb").read() != data:
            stale.append(path)
            if not check:
                open(path, "wb").write(data)
    for name, m in pal["materials"].items():
        if "tex" in m and m["tex"] not in GENERATED:
            for part in ("_Color.jpg", "_NormalGL.jpg", "_Roughness.jpg"):
                if not os.path.exists(os.path.join(KIT, "textures", m["tex"] + part)):
                    raise SystemExit("%s: texture set %s has no %s" % (name, m["tex"], part))
        text = material_tres(name, m)
        path = os.path.join(KIT, "materials", name + ".tres")
        if not os.path.exists(path) or open(path).read() != text:
            stale.append(path)
            if not check:
                open(path, "w").write(text)
    known = set(pal["materials"])
    for f in os.listdir(os.path.join(KIT, "materials")):
        if f.endswith(".tres") and f[:-5] not in known:
            stale.append(os.path.join(KIT, "materials", f) + " (not in palette.json)")
            if not check:
                os.remove(os.path.join(KIT, "materials", f))
    for s in stale:
        print(("STALE " if check else "wrote ") + os.path.relpath(s, ROOT))
    print("build_library_palette: %d materials, %d generated textures, %d %s" % (
        len(pal["materials"]), len(GENERATED), len(stale), "stale" if check else "written"))
    sys.exit(1 if (check and stale) else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
