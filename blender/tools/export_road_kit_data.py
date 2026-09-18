"""export_road_kit_data.py -- `road_kit.blend` AS DATA, for the road build that has no Blender (PLAN.md 3.1 B11).

    blender --background --python-exit-code 1 assets/world_source/kit/road_kit.blend \
        --python blender/tools/export_road_kit_data.py

Writes `assets/world_source/kit/road_kit.json` next to the kit:

  * `materials` -- every material, as the glTF `materials[]` entry `export_world.py` + Blender's glTF exporter
    produce for it: `pbrMetallicRoughness.baseColorFactor` (the Principled BSDF's Base Color when it is a
    constant; the mean of a Checker's two colours; else the viewport `diffuse_color` -- `export_world.py`'s
    `_flatten_base_colours` rule, restated), `metallicFactor`, `roughnessFactor`, `doubleSided` (not
    `use_backface_culling`) and `alphaMode: BLEND` when the colour is not opaque;
  * `profiles` -- every `ROAD_KIT` section: its material and its splines' points in the section's own XY
    plane (+X outward, +Y up), the object's transform applied (`GN_PointProfile` reads the asset RELATIVE);
  * `piers` -- every `RKA_PIER_*` MESH in `ROAD_KIT` (PLAN.md 3.5): its `stretch_z` (the object's
    `rka_stretch_z`) and its triangles by material name, `[x,y,z]*3` flattened per triangle, in the object's own
    frame (rotation and scale applied, location NOT -- the origin is the pier's top centre wherever the object
    stands in the kit file);
  * `blend_sha1` -- the kit file this was read from, so `point_kit.load` can say when the JSON is stale.

`build_road_kit.py` runs this at the end of every kit build, so the two cannot drift. The kit `.blend` stays the
place an artist authors a material or a section; this file is only how a Python process reads it.
"""
import hashlib
import json
import os
import sys

import bpy
from mathutils import geometry

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
KIT_COLLECTION = "ROAD_KIT"


def _principled(m):
    if m.node_tree is None:
        return None
    return next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)


def material_entry(m):
    bsdf = _principled(m)
    colour, metallic, rough = tuple(m.diffuse_color), 0.0, 0.5
    if bsdf is not None:
        sock = bsdf.inputs["Base Color"]
        if not sock.is_linked:
            colour = tuple(sock.default_value)
        else:
            src = sock.links[0].from_node
            if src.type == 'TEX_CHECKER':
                c1, c2 = tuple(src.inputs["Color1"].default_value), tuple(src.inputs["Color2"].default_value)
                colour = tuple((a + b) * 0.5 for a, b in zip(c1, c2))
        metallic = float(bsdf.inputs["Metallic"].default_value)
        rough = float(bsdf.inputs["Roughness"].default_value)
    entry = {"name": m.name, "doubleSided": not m.use_backface_culling,
             "pbrMetallicRoughness": {"baseColorFactor": [round(float(c), 6) for c in colour],
                                      "metallicFactor": round(metallic, 6), "roughnessFactor": round(rough, 6)}}
    if colour[3] < 1.0:
        entry["alphaMode"] = "BLEND"
    return entry


def spline_points(sp, mw):
    """A spline's evaluated points in the section plane: a POLY spline's own points, a BEZIER spline sampled at
    its `resolution_u` (what `Curve to Mesh` sweeps)."""
    if sp.type == 'BEZIER':
        bp = list(sp.bezier_points)
        segs = list(zip(bp, bp[1:] + (bp[:1] if sp.use_cyclic_u else [])))
        pts = []
        for a, b in segs:
            run = geometry.interpolate_bezier(a.co, a.handle_right, b.handle_left, b.co, max(2, sp.resolution_u) + 1)
            pts += run[:-1]
        if not sp.use_cyclic_u and bp:
            pts.append(bp[-1].co)
    else:
        pts = [p.co.xyz for p in sp.points]
    return [[round((mw @ p)[0], 6), round((mw @ p)[1], 6)] for p in pts]


PIER_PREFIX = "RKA_PIER_"


def pier_entry(o):
    """A pier mesh as data: `{"stretch_z", "tris": {material: [9 floats per triangle]}}`."""
    me = o.data
    me.calc_loop_triangles()
    m3 = o.matrix_world.to_3x3()
    names = [m.name if m is not None else "" for m in me.materials]
    tris = {}
    for lt in me.loop_triangles:
        mat = names[lt.material_index] if lt.material_index < len(names) else ""
        flat = []
        for vi in lt.vertices:
            c = m3 @ me.vertices[vi].co
            flat += [round(c[0], 5), round(c[1], 5), round(c[2], 5)]
        tris.setdefault(mat, []).append(flat)
    return {"stretch_z": round(float(o.get("rka_stretch_z", 0.0)), 5), "tris": tris}


def export(out=None):
    blend = bpy.data.filepath
    out = out or os.path.join(os.path.dirname(blend), "road_kit.json")
    with open(blend, "rb") as fh:
        sha = hashlib.sha1(fh.read()).hexdigest()
    mats = {m.name: material_entry(m) for m in bpy.data.materials if m.library is None}
    profiles = {}
    coll = bpy.data.collections.get(KIT_COLLECTION)
    for o in (coll.all_objects if coll else ()):
        if o.type != 'CURVE':
            continue
        mat = next((m.name for m in o.data.materials if m is not None), "")
        profiles[o.name] = {"material": mat,
                            "splines": [{"cyclic": bool(sp.use_cyclic_u), "points": spline_points(sp, o.matrix_world)}
                                        for sp in o.data.splines]}
    piers = {}
    for o in (coll.all_objects if coll else ()):
        if o.type != 'MESH' or not o.name.startswith(PIER_PREFIX):
            continue
        piers[o.name] = pier_entry(o)
    doc = {"blend_sha1": sha, "materials": dict(sorted(mats.items())), "profiles": dict(sorted(profiles.items())),
           "piers": dict(sorted(piers.items()))}
    tmp = out + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(doc, fh, indent=1)
        fh.write("\n")
    os.replace(tmp, out)
    print("export_road_kit_data: %d material(s), %d profile(s), %d pier(s) -> %s"
          % (len(mats), len(profiles), len(piers), out))
    return out


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    export(argv[0] if argv else None)
