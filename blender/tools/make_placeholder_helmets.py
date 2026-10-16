"""Placeholder motorcycle HELMETS, a .blend an artist can rework (PLAN.md 3.1b, user 2026-10-16).

    blender -b --factory-startup --python-exit-code 1 --python blender/tools/make_placeholder_helmets.py -- [--force]

Writes `assets/characters/gear/Helmet_<kind>.blend` (the artist's file) and exports `Helmet_<kind>.glb` from it
(the runtime's: `Motorcycle` loads `res://assets/characters/gear/Helmet_<VehicleConfig.riderHelmet>.glb`). An existing
.blend is NOT regenerated without --force: it may hold an artist's work -- re-export it with `--export-only` instead.

    --export-only   re-export every existing Helmet_*.blend to its .glb, changing nothing in it

Kinds (user 2026-10-16: "a regular helmet as standard size, let hair poke through for now"):
  open   a jet (open-face) helmet with a clear shield -- SCT1 / POB1 / TRB1, and the 白バイ PMB1's (tinted white)
  full   a full-face helmet with a tinted visor -- SSB1

THE CONTRACT the runtime reads (and an artist keeps):
  * the object ORIGIN is the rider's head-bone pivot (`head_2`, the top of the neck); +Z up, the face looks along -Y
    (glTF/Godot: up +Y, face +Z -- the bodies' head-bone frame);
  * material `shell` is the paint: Motorcycle tints it per rider (one of five shells, white on a 白バイ). `visor` is the
    shield / visor (transparent), `trim` the rim and liner edge;
  * Empty `grab` = where the RIGHT hand holds the helmet while putting it on (the hand's grip point, RiderHandsModifier).
Sizes: a real helmet's outer shell is ~0.29 x 0.24 x 0.25 m (size M); the bodies' heads are anime-sized (hair to
x +-0.15, z -0.17..0.14 round the head bone, measured 2026-10-16 on shino / fumiriya / bibi / vita / victoria / shibu),
so the shell is the size of a large real one, 0.28 wide x 0.32 long, and long hair is allowed to show through.
"""
import math
import os
import sys

import bmesh
import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIR = os.path.join(ROOT, "assets", "characters", "gear")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
FORCE = "--force" in argv
EXPORT_ONLY = "--export-only" in argv

# the shell: an ellipsoid round CENTRE (head-bone space, Blender axes: x right-is-minus, -y forward, z up)
CENTRE_Z, CENTRE_Y = 0.095, 0.005     # 9.5 cm over the pivot, 5 mm behind it (glTF z -0.005)
SEMI_X, SEMI_LEN, SEMI_UP = 0.140, 0.160, 0.150
THICK = 0.014                          # shell + liner, solidified inward

COLOURS = {"shell": ((0.85, 0.85, 0.82, 1.0), 0.35), "trim": ((0.04, 0.04, 0.045, 1.0), 0.8),
           "visor": ((0.55, 0.60, 0.65, 0.30), 0.05), "visor_dark": ((0.05, 0.05, 0.07, 0.75), 0.05)}

KINDS = {
    # rim: the shell's lower edge (head space z) at the back / at the sides; face: the opening
    "open": dict(semi_down=0.150, len_scale=1.0, rim_back=-0.035, rim_side=-0.005,
                 opening=lambda gx, gz, fwd: fwd > 0.045 and gz < 0.165,
                 visor=lambda gx, gz, fwd: fwd > 0.03 and -0.03 < gz < 0.175, visor_mat="visor", visor_out=0.022),
    "full": dict(semi_down=0.200, len_scale=1.07, rim_back=-0.060, rim_side=-0.060,
                 opening=lambda gx, gz, fwd: fwd > 0.05 and 0.035 < gz < 0.150 and abs(gx) < 0.105,
                 visor=lambda gx, gz, fwd: fwd > 0.04 and 0.025 < gz < 0.160 and abs(gx) < 0.115,
                 visor_mat="visor_dark", visor_out=0.006),
}


def mat(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    c, rough = COLOURS[name]
    bsdf.inputs["Base Color"].default_value = c
    bsdf.inputs["Roughness"].default_value = rough
    if c[3] < 1.0:
        bsdf.inputs["Alpha"].default_value = c[3]     # glTF alphaMode comes from the node tree (Blender 4.2+)
        m.surface_render_method = 'BLENDED'
    m.diffuse_color = c
    return m


def ellipsoid(k, scale=1.0, segs=40, rings=24):
    """Vertices of the helmet's ellipsoid; the lower half is taller on a full-face (the chin bar)."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=1.0)
    for v in bm.verts:
        x, y, z = v.co
        up = SEMI_UP if z >= 0 else k["semi_down"]
        v.co = (x * SEMI_X * scale, y * SEMI_LEN * k["len_scale"] * scale + CENTRE_Y, z * up * scale + CENTRE_Z)
    return bm


def head_space(co):
    """(gx, gz, fwd): sideways, up, and forward (+ = toward the face) in head-bone space."""
    return co.x, co.z, -co.y


def shell(kind, k):
    bm = ellipsoid(k)
    rim = []
    for v in bm.verts:
        gx, gz, fwd = head_space(v.co)
        # the rim drops from the sides to the back of the neck
        back = max(0.0, min(1.0, -fwd / (SEMI_LEN * 0.8)))
        floor = k["rim_side"] + (k["rim_back"] - k["rim_side"]) * back
        if gz < floor or k["opening"](gx, gz, fwd):
            rim.append(v)
    bmesh.ops.delete(bm, geom=rim, context='VERTS')
    me = bpy.data.meshes.new("Helmet_" + kind)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Helmet_" + kind, me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat("shell"))
    ob.data.materials.append(mat("trim"))
    for p in me.polygons:
        p.use_smooth = True
    sol = ob.modifiers.new("liner", 'SOLIDIFY')
    sol.thickness = THICK
    sol.offset = -1.0                    # inward: the outside is the size above
    sol.material_offset = 1              # the inner face (the liner) and the rim are trim
    sol.material_offset_rim = 1
    sol.use_rim = True
    return ob


def visor(kind, k):
    bm = ellipsoid(k, scale=1.0 + k["visor_out"] / SEMI_LEN)
    gone = [v for v in bm.verts if not k["visor"](*head_space(v.co))]
    bmesh.ops.delete(bm, geom=gone, context='VERTS')
    me = bpy.data.meshes.new("Visor_" + kind)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("visor", me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat(k["visor_mat"]))
    for p in me.polygons:
        p.use_smooth = True
    sol = ob.modifiers.new("thickness", 'SOLIDIFY')
    sol.thickness = 0.003
    return ob


def build(kind, k):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = shell(kind, k)
    v = visor(kind, k)
    v.parent = s
    # the right hand's hold while putting it on: the rim at the right side, low (the chin-strap end)
    g = bpy.data.objects.new("grab", None)
    g.empty_display_type = 'SPHERE'
    g.empty_display_size = 0.02
    g.location = (-SEMI_X - 0.01, CENTRE_Y + 0.02, k["rim_side"] + 0.04)
    g.parent = s
    bpy.context.collection.objects.link(g)
    return s


def export(path_blend):
    bpy.ops.wm.open_mainfile(filepath=path_blend)
    out = path_blend[:-len(".blend")] + ".glb"
    bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', export_yup=True, export_apply=True,
                              export_animations=False, export_cameras=False, export_lights=False)
    print("exported", out)


def main():
    os.makedirs(DIR, exist_ok=True)
    for kind, k in KINDS.items():
        path = os.path.join(DIR, f"Helmet_{kind}.blend")
        if not EXPORT_ONLY:
            if os.path.exists(path) and not FORCE:
                print("kept", path, "(an artist's file: --force to regenerate)")
            else:
                build(kind, k)
                bpy.ops.wm.save_as_mainfile(filepath=path)
                print("wrote", path)
        if os.path.exists(path):
            export(path)


main()
