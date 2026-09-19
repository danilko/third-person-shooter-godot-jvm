"""Placeholder models at real-world size, for an artist to redesign.

    blender --background --factory-startup --python blender/tools/make_placeholder_models.py -- [ids...] [--force]

Writes assets/weapons/<id>.blend for FRG1 (a cylindrical hand grenade), ATL1_Rocket (an 84 mm shoulder-launched
rocket) and SHI1 (a hand-held ballistic shield with a viewport), each to blender/WEAPON_AUTHORING.md's standard:
1 unit = 1 m, forward is Blender +Y (Godot -Z), every transform applied, every mesh in ONE collection named after
the id, one Principled BSDF per material. The sizes are the `weapon_models.json` rows; `build_weapon.py` then
proves the model still matches them and exports the .glb. With no ids it builds all three. REFUSES to overwrite
an existing file (that is the artist's work now) unless --force.

Origins: the grenade's is the centre of its body (where the hand closes; the fuze points forward), the rocket's
the middle of its length (where it detonates), the shield's the centre of its handle (the grip).
"""
import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "assets", "weapons")
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
FORCE = "--force" in ARGS
WANTED = {a for a in ARGS if not a.startswith("--")}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.render.fps = 60


def material(name, rgb, metallic=0.0, roughness=0.6):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return m


def add(col, name, mesh_fn, mat, matrix):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    mesh_fn(bm)
    bmesh.ops.transform(bm, matrix=matrix, verts=bm.verts)      # baked into the vertices: no object transform
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    return ob


def along_y(length_axis_z=True):
    """bmesh primitives are built along Z; the model's forward is +Y."""
    return Matrix.Rotation(-math.pi / 2, 4, 'X')


def cyl(r1, r2, depth, seg=32):
    return lambda bm: bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r1, radius2=r2, depth=depth)


def save(wid):
    path = os.path.join(OUT, wid + ".blend")
    if os.path.exists(path) and not FORCE:
        print(f"[placeholders] {path} exists: left alone (--force to rebuild the placeholder)")
        return
    bpy.ops.wm.save_as_mainfile(filepath=path)
    print(f"[placeholders] wrote {path}")


def grenade():
    """A cylindrical grenade: 56 mm body, 90 mm long, fuze forward; 112 mm overall."""
    reset()
    col = bpy.data.collections.new("FRG1")
    bpy.context.scene.collection.children.link(col)
    body = material("M_FRG1_Body", (0.20, 0.24, 0.13))
    band = material("M_FRG1_Band", (0.75, 0.62, 0.10))
    metal = material("M_FRG1_Fuze", (0.55, 0.55, 0.52), metallic=0.8, roughness=0.4)
    R = 0.028
    add(col, "FRG1", cyl(R, R, 0.090), body, along_y())                        # y -0.045 .. +0.045
    add(col, "FRG1_Band", cyl(R + 0.001, R + 0.001, 0.010), band,             # marking band
        Matrix.Translation((0, 0.020, 0)) @ along_y())
    add(col, "FRG1_Fuze", cyl(0.010, 0.010, 0.020), metal,                    # y +0.045 .. +0.065
        Matrix.Translation((0, 0.055, 0)) @ along_y())
    add(col, "FRG1_Lever", lambda bm: bmesh.ops.create_cube(bm, size=1.0), metal,   # down the body's side
        Matrix.Translation((0, 0.020, R + 0.0015)) @ Matrix.Diagonal((0.012, 0.080, 0.003, 1)))
    # pull ring beside the fuze; its far edge is the front: 45 + 67 = 112 mm overall
    add(col, "FRG1_Ring", lambda bm: _torus(bm, 0.009, 0.0015), metal, Matrix.Translation((0.016, 0.0565, 0)))
    save("FRG1")


def _torus(bm, major, minor, seg_major=48, seg_minor=12):
    rings = []
    for i in range(seg_major):
        a = 2 * math.pi * i / seg_major
        ring = []
        for j in range(seg_minor):
            b = 2 * math.pi * j / seg_minor
            r = major + minor * math.cos(b)
            ring.append(bm.verts.new((r * math.cos(a), r * math.sin(a), minor * math.sin(b))))
        rings.append(ring)
    for i in range(seg_major):
        for j in range(seg_minor):
            a, b = rings[i], rings[(i + 1) % seg_major]
            bm.faces.new((a[j], b[j], b[(j + 1) % seg_minor], a[(j + 1) % seg_minor]))


def rocket():
    reset()
    col = bpy.data.collections.new("ATL1_Rocket")
    bpy.context.scene.collection.children.link(col)
    body = material("M_ATL1_Rocket_Body", (0.24, 0.27, 0.16))
    nose = material("M_ATL1_Rocket_Nose", (0.08, 0.08, 0.08), roughness=0.4)
    band = material("M_ATL1_Rocket_Band", (0.75, 0.62, 0.10))
    R = 0.042                                              # 84 mm calibre; 0.46 m overall, origin mid-length
    # warhead body y -0.17 .. +0.12
    add(col, "ATL1_Rocket", cyl(R, R, 0.29), body, Matrix.Translation((0, -0.025, 0)) @ along_y())
    # ogive nose (a cone for now) +0.12 .. +0.23 — the front of the model
    add(col, "ATL1_Rocket_Nose", cyl(R, 0.008, 0.11), nose, Matrix.Translation((0, 0.175, 0)) @ along_y())
    # HEAT marking band
    add(col, "ATL1_Rocket_Band", cyl(R + 0.001, R + 0.001, 0.02), band,
        Matrix.Translation((0, 0.09, 0)) @ along_y())
    # tail boom -0.23 .. -0.17, and four fins inside the calibre (they have to fit the tube)
    add(col, "ATL1_Rocket_Tail", cyl(0.02, 0.02, 0.06), body, Matrix.Translation((0, -0.20, 0)) @ along_y())
    for k in range(4):
        rot = Matrix.Rotation(k * math.pi / 2, 4, 'Y')
        add(col, f"ATL1_Rocket_Fin{k}", lambda bm: bmesh.ops.create_cube(bm, size=1.0), body,
            rot @ Matrix.Translation((0.031, -0.21, 0)) @ Matrix.Diagonal((0.022, 0.04, 0.003, 1)))
    save("ATL1_Rocket")



def shield():
    """A hand-held ballistic shield: 0.50 x 0.90 m plate, 25 x 10 cm viewport, vertical handle behind."""
    reset()
    col = bpy.data.collections.new("SHI1")
    bpy.context.scene.collection.children.link(col)
    plate = material("M_SHI1_Plate", (0.10, 0.11, 0.12), roughness=0.5)
    glass = material("M_SHI1_Viewport", (0.35, 0.45, 0.50), metallic=0.2, roughness=0.05)
    grip = material("M_SHI1_Grip", (0.05, 0.05, 0.05), roughness=0.8)
    W, H, T, AHEAD = 0.50, 0.90, 0.025, 0.10      # plate width, height, thickness; plate face this far ahead of the grip
    box = lambda bm: bmesh.ops.create_cube(bm, size=1.0)
    # the plate, split round the viewport so the window is its own object an artist can swap
    VW, VH, VZ = 0.25, 0.10, 0.30                 # viewport width, height, centre height above the grip
    y = AHEAD - T / 2
    z0, z1 = -H / 2 + 0.05, H / 2 + 0.05          # the plate rides slightly high: the window sits at eye level
    add(col, "SHI1", box, plate, Matrix.Translation((0, y, (z0 + VZ - VH / 2) / 2))
        @ Matrix.Diagonal((W, T, (VZ - VH / 2) - z0, 1)))
    add(col, "SHI1_Top", box, plate, Matrix.Translation((0, y, (VZ + VH / 2 + z1) / 2))
        @ Matrix.Diagonal((W, T, z1 - (VZ + VH / 2), 1)))
    for side in (-1, 1):
        add(col, "SHI1_Side%d" % (side > 0), box, plate,
            Matrix.Translation((side * (VW / 2 + (W - VW) / 4), y, VZ)) @ Matrix.Diagonal(((W - VW) / 2, T, VH, 1)))
    add(col, "SHI1_Viewport", box, glass, Matrix.Translation((0, y, VZ)) @ Matrix.Diagonal((VW, T * 0.6, VH, 1)))
    # vertical handle (the origin) on two stand-offs, and an arm cuff above it
    add(col, "SHI1_Handle", cyl(0.016, 0.016, 0.13, 16), grip, Matrix())
    for dz in (-0.055, 0.055):
        add(col, "SHI1_Standoff%d" % (dz > 0), box, grip,
            Matrix.Translation((0, (AHEAD - T) / 2 - 0.008, dz)) @ Matrix.Diagonal((0.02, AHEAD - T + 0.016, 0.02, 1)))
    add(col, "SHI1_Cuff", box, grip, Matrix.Translation((0, AHEAD - T - 0.03, 0.20))
        @ Matrix.Diagonal((0.12, 0.06, 0.05, 1)))
    save("SHI1")


for wid, build in (("FRG1", grenade), ("ATL1_Rocket", rocket), ("SHI1", shield)):
    if not WANTED or wid in WANTED:
        build()
