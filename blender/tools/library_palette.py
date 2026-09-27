"""The central library's palette as Blender materials: one owner for every generator that models library-palette pieces
(build_library.py, build_station_blends.py). A material's LOOK in game is `kits/library/materials/MI_*.tres`
(tools/building_kit/build_library_palette.py); here it only gets a flat viewport colour close to that look."""
import json
import os

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KIT = os.path.join(ROOT, "assets", "world_source", "kits", "library")

PALETTE = json.load(open(os.path.join(KIT, "palette.json")))["materials"]


def _mean_colour(entry):
    """A flat viewport colour for a palette entry: its colour, times its albedo texture's mean when it has one."""
    col = list(entry.get("color", [1, 1, 1]))[:3]
    path = None
    if "tex" in entry and entry.get("albedo_tex", True):
        for suffix in ("_Color.jpg", ".png"):
            p = os.path.join(KIT, "textures", entry["tex"] + suffix)
            if os.path.exists(p):
                path = p
    elif "tex_path" in entry:
        p = os.path.join(ROOT, entry["tex_path"].replace("res://", "") + "_BaseColor.png")
        path = p if os.path.exists(p) else None
    if path:
        img = bpy.data.images.load(path, check_existing=True)
        import numpy as np
        px = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        m = px.reshape(-1, 4)[:, :3].mean(axis=0)
        col = [col[i] * float(m[i]) for i in range(3)]
        bpy.data.images.remove(img)
    return col + [entry.get("color", [1, 1, 1, 1])[3] if len(entry.get("color", [])) > 3 else 1.0]


def material(name):
    if name not in PALETTE:
        raise SystemExit("build_library: %s is not in palette.json" % name)
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_fake_user = False
        c = _mean_colour(PALETTE[name])
        m.diffuse_color = c
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = c
            bsdf.inputs["Roughness"].default_value = float(PALETTE[name].get("roughness", 0.7))
            bsdf.inputs["Metallic"].default_value = float(PALETTE[name].get("metallic", 0.0))
            if "emission" in PALETTE[name]:
                bsdf.inputs["Emission Color"].default_value = list(PALETTE[name]["emission"]) + [1.0]
                bsdf.inputs["Emission Strength"].default_value = float(PALETTE[name].get("emission_energy", 1.0))
    return m


