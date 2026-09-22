"""Conform Quaternius pistols (CC0, quaternius.itch.io, the "Ultimate Guns" set: Pistol_1..6.blend) to the
weapon standard, as assets/weapons/<id>.blend. A one-shot, like import_guns_pack.py: this file is the record of
what was done to each model. The downloads live outside the repo (/data/danilko/game_assets/quaternius.itch.io/).

    blender --background --factory-startup --python blender/tools/import_quaternius_pistols.py -- [id ...]

Raw frame (all six): muzzle +X, top +Z, the grip hanging below the rear of the slide, the file origin near the
top of the grip. For each: world transforms applied (Pistol_5 carries a 0.889 lateral object scale), turned so
the muzzle points down Blender +Y, moved so the origin is the centre of the firing fist on the grip, scaled,
joined into one object named <id> in a collection named <id>, and every material given ONE output node (the
kit ships an EEVEE and a Cycles output per material, which exports no base colour -- the SR3 trap).
`build_weapon.py` then verifies and exports the .glb.

PIS1 is Pistol_5 again (2026-09-21, user): it WAS PIS1 before the Makarov import (commit 8eeacbf), at 0.22 m
with its grip at raw (-0.031, 0, 0.027); those numbers are re-derived here from that conformed file.
PIS2 is Pistol_6, the large pistol (user: "the desert eagle ... should be larger"). Sized by HEIGHT, not length:
a Desert Eagle Mark XIX is 0.149 m tall, and scaling Pistol_6 to the Deagle's 0.273 m LENGTH would leave its grip
8% smaller than PIS1's, a large pistol with a small handle. At 0.149 m tall the model's long slide reads 0.314 m,
a Deagle with a longer barrel. Same kit, same grip layout, so it takes Pistol_5's raw grip point.
DUP1 is Pistol_1, the dual pistols' model (one per hand): picked from Pistol_1..4 for dual wield -- 1 and 2 are
one frame in two finishes, the classic 1911 / Beretta shape; 3 carries tactical rails, 4 a long magazine.
"""
import os
import sys

import bpy
from mathutils import Matrix, Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = "/data/danilko/game_assets/quaternius.itch.io"
OUT = os.path.join(ROOT, "assets", "weapons")

# scale: raw units -> metres. grip: fist centre in RAW (world, scale applied) coordinates.
MODELS = {
    "PIS1": dict(src="Pistol_5.blend", scale=0.22 / 1.8193, grip=(-0.0311, 0.0, 0.0268)),
    "PIS2": dict(src="Pistol_6.blend", scale=0.149 / 1.1616, grip=(-0.0311, 0.0, 0.0268)),
    # the dual pistols: one of these in each hand (DualPistolItem). Pistol_1 is the classic 1911 / Beretta frame
    # of CS's Dual Berettas and L4D's dual pistols; the same frame size as Pistol_5, so the same scale and grip.
    "DUP1": dict(src="Pistol_1.blend", scale=0.22 / 1.8193, grip=(-0.0311, 0.0, 0.0268)),
}
# raw (muzzle +X, up +Z) -> standard (muzzle +Y, up +Z): 90 deg about Z
TURN = Matrix.Rotation(1.5707963267948966, 4, 'Z')


def conform(wid, m):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with bpy.data.libraries.load(os.path.join(SRC, m["src"]), link=False) as (src, dst):
        dst.objects = [n for n in src.objects]
    col = bpy.data.collections.new(wid)
    bpy.context.scene.collection.children.link(col)
    meshes = []
    for ob in dst.objects:
        if ob is None or ob.type != 'MESH':
            continue
        col.objects.link(ob)
        ob.hide_render = False
        ob.hide_viewport = False
        meshes.append(ob)
    bpy.context.view_layer.update()      # an appended object's matrix_world is stale until the scene updates
    s = m["scale"]
    place = Matrix.Scale(s, 4) @ TURN @ Matrix.Translation(-Vector(m["grip"]))
    for ob in meshes:
        ob.data.transform(place @ ob.matrix_basis)   # no parents in the kit
        ob.matrix_world = Matrix.Identity(4)
    bpy.context.view_layer.objects.active = meshes[0]
    for ob in meshes:
        ob.select_set(True)
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = ob.data.name = wid
    for mat in ob.data.materials:
        nt = mat.node_tree
        outs = [n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL']
        bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
        for n in outs:
            nt.nodes.remove(n)
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        out.target = 'ALL'
        nt.links.new(bsdf.outputs[0], out.inputs['Surface'])
        for n in [n for n in nt.nodes if n not in (bsdf, out)]:
            nt.nodes.remove(n)
    pts = [v.co for v in ob.data.vertices]
    mn = Vector([min(p[i] for p in pts) for i in range(3)])
    mx = Vector([max(p[i] for p in pts) for i in range(3)])
    print("[pistols] %s from %s: length %.3f m, height %.3f m, grip->rear %.3f m, bbox %s..%s"
          % (wid, m["src"], mx.y - mn.y, mx.z - mn.z, -mn.y, tuple(round(v, 4) for v in mn), tuple(round(v, 4) for v in mx)))
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, wid + ".blend"), compress=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    for wid in (argv or list(MODELS)):
        conform(wid, MODELS[wid])


main()
