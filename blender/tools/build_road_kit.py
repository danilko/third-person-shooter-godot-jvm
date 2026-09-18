"""build_road_kit.py -- the PROFILE ASSET kit for road_kit_authoring.

    blender --background --python-exit-code 1 --python blender/tools/build_road_kit.py

Writes `assets/world_source/kit/road_kit.blend`, which is TWO things and deliberately one file:

  * one `ROAD_KIT` collection of profile CURVES. A road names one of these in a style slot
    (`RoadData.kerb_asset`, ...) and `GN_PointProfile` sweeps it along the road's own edge, at
    the section's own authored size;
  * the repo's MATERIAL LIBRARY. Every `kit_common.MATS` / `TILED_MATS` entry is written here
    with a fake user, and `kit_common.mat()` LINKS from this file rather than creating its own
    copy in whichever `.blend` is building (see that function's own comment). So the world's look
    is authored in a `.blend` an artist can open, not in a Python table, and a kerb section's
    concrete is the SAME datablock as the deck's beside it.

One file, one link, one resolver: the addon already links this kit for its sections
(`RKA_OT_link_road_kit`), and a second library plus a link chain would buy nothing.

WHY THESE ARE CURVES AND NOT KIT PIECES. The previous model instanced rigid meshes along an edge.
Round a 9 m corner a 2 m piece sits ~12.7 deg from its neighbour and opens a real ~7.8 cm gap at
every joint -- an inherent limit of tiling rigid geometry on a curve (the same reason real
guardrail systems show visible joints on bends), not a phase bug, and eventually the reason that
whole style was retired. A swept section has no joints to open, at any curvature.

HOW TO AUTHOR A NEW ONE. Draw the cross-section in the XY plane: **+X is outward from the road,
+Y is up**, origin at the point the road hands it (the kerb line for a kerb, the wall's foot for a
barrier). That is the natural way round -- `GN_PointProfile` applies the measured
profile-to-world correction, so what you draw is what you get. Give it a material; the addon reads
it off the asset, because `Curve to Mesh` drops it. Name it `RKA_PROFILE_<slot>_<variant>`.

PIER ASSETS (PLAN.md 3.5). A `RKA_PIER_<variant>` MESH in the same collection is a column a road
names in `RoadData.pillar_asset`; the road build (`point_mesh.pillars`) stands one wherever the
solve puts a column, in place of the plain box. Model it Z-up with its **origin at the top centre**
-- the soffit, where it meets the deck -- **+Y along the road, +X across it**, at its REAL size
(a pier owns its size, like a profile: it is never scaled to the deck). Everything above the
object's `rka_stretch_z` custom property (metres, <= 0) is RIGID -- the cap, the bearings; every
vertex below it STRETCHES linearly so the pier's lowest point lands on the ground, however tall the
column has to be. Model the shaft ~10 m long; the length is only a reference. Any number of
materials; each face keeps its own. `add_piers()` (re)makes only the `RKA_PIER_*` objects this
script ships, so it can be run on a hand-edited kit without touching anything else.

The file is LIBRARY-LINKED into a district (`Author > Style > Link Road Kit`), so editing one
section here restyles every road in the world that names it.
"""

import os
import sys

import bpy

HERE = os.path.dirname(os.path.realpath(__file__))
BLENDER_SRC = os.path.dirname(HERE)
REPO = os.path.dirname(BLENDER_SRC)
sys.path.insert(0, os.path.join(BLENDER_SRC, "lib"))

import kit_common as kc                                                      # noqa: E402

# THE TOOL THAT AUTHORS THE LIBRARY MUST NOT CONSULT IT. `kc.mat()` links from
# `road_kit.blend`; this script IS `road_kit.blend`, so it takes the bootstrap path and builds
# every material from the tables. Without this the second run would link the first run's output
# into itself.
kc.USE_MATERIAL_LIBRARY = False

OUT = os.path.join(REPO, "assets", "world_source", "kit", "road_kit.blend")
COLLECTION = "ROAD_KIT"
PREFIX = "RKA_PROFILE_"


def _wipe():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for cu in list(bpy.data.curves):
        bpy.data.curves.remove(cu)
    # The startup file's default `Material` would otherwise ship in the library and be offered
    # as a road material — a datablock nobody authored, named after nothing.
    for m in list(bpy.data.materials):
        if not m.name.startswith("M_"):
            bpy.data.materials.remove(m)


def build_materials():
    """Every material the repo declares, written into the kit with a fake user.

    A FAKE USER IS WHAT MAKES A MATERIAL LIBRARY POSSIBLE: a `.blend` drops any datablock with
    zero users on save, and most of these are used by no object in this file — the kit holds six
    cross-sections, not a scene. Without the flag the library would ship exactly the handful of
    materials the sections happen to carry, which is how it behaved until now."""
    made = []
    for key in list(kc.MATS) + list(kc.TILED_MATS):
        m = kc.mat(key)
        m.use_fake_user = True
        made.append(m)
    return made


def profile(name, points, matkey, coll):
    """One section, as a POLY curve in the XY plane. `points` are `(x_outward, y_up)` metres."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '2D'
    sp = cu.splines.new('POLY')
    sp.points.add(len(points) - 1)
    for i, (x, y) in enumerate(points):
        sp.points[i].co = (float(x), float(y), 0.0, 1.0)
    cu.materials.append(kc.mat(matkey))
    o = bpy.data.objects.new(name, cu)
    coll.objects.link(o)
    return o


#: `(name, matkey, [(x_outward, y_up)])`. Every section starts at the origin -- the line the road
#: hands it -- so two of them stacked (a kerb and the footway above it) meet by construction.
SECTIONS = (
    # -- kerbs ------------------------------------------------------------------------------------
    ("kerb_std", "concrete",
     [(0.0, 0.0), (0.0, 0.15), (0.30, 0.15), (0.30, 0.0)]),
    # A real kerb is chamfered at the top edge -- it is the single detail that reads as "kerb"
    # rather than "step" at driving speed.
    ("kerb_granite", "concrete",
     [(0.0, 0.0), (0.0, 0.12), (0.03, 0.16), (0.14, 0.17), (0.32, 0.17), (0.32, 0.0)]),
    # A dished gutter, INBOARD of the kerb line: negative X, because the channel belongs on the
    # road side of the line the kerb stands on.
    ("gutter_dish", "concrete",
     [(-0.45, 0.02), (-0.30, -0.03), (-0.10, -0.02), (0.0, 0.0), (0.0, 0.14), (0.26, 0.14),
      (0.26, 0.0)]),
    # -- barriers ---------------------------------------------------------------------------------
    ("wall_parapet", "barrier",
     [(0.0, 0.0), (0.0, 1.0), (0.22, 1.0), (0.22, 0.0)]),
    # The New Jersey section: a near-vertical face, the 55-degree slope, and the toe.
    ("wall_jersey", "barrier",
     [(0.0, 0.0), (0.0, 0.81), (0.09, 0.81), (0.16, 0.33), (0.32, 0.08), (0.32, 0.0)]),
    # -- footways ---------------------------------------------------------------------------------
    # A slab with a fall toward the road, which is what makes a wet street read as drained.
    ("footway_slab", "concrete_tile",
     [(0.0, 0.0), (0.0, 0.02), (2.0, 0.06), (2.0, 0.0)]),
)


PIER_PREFIX = "RKA_PIER_"
#: Reference shaft length: the shipped piers are modelled down to this depth; the build stretches them.
PIER_REF_DEPTH = 10.0


def _prism_y(bm, outline_xz, y_half):
    """An XZ outline extruded along Y (+-y_half): a cap or a crossbeam."""
    import bmesh  # noqa: F401
    front = [bm.verts.new((x, -y_half, z)) for x, z in outline_xz]
    back = [bm.verts.new((x, y_half, z)) for x, z in outline_xz]
    bm.faces.new(front[::-1])
    bm.faces.new(back)
    n = len(outline_xz)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((front[i], front[j], back[j], back[i]))


def _prism_z(bm, outline_xy, z_top, z_bottom):
    """An XY outline extruded down Z: a column."""
    top = [bm.verts.new((x, y, z_top)) for x, y in outline_xy]
    bot = [bm.verts.new((x, y, z_bottom)) for x, y in outline_xy]
    bm.faces.new(top)
    bm.faces.new(bot[::-1])
    n = len(outline_xy)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((top[i], bot[i], bot[j], top[j]))


def _circle(cx, cy, r, n=20):
    import math
    return [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def _rect(hx, hy):
    return [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]


#: `(variant, stretch_z, [parts])`. A part is `("cap", outline_xz, y_half)` or `("col", outline_xy, z_top)`
#: (a column runs from z_top down to -PIER_REF_DEPTH). Real-world sizes, Shuto viaduct practice.
PIERS = (
    # A plain round column, the whole of it stretching.
    ("round", 0.0, [("col", _circle(0.0, 0.0, 0.9), 0.0)]),
    # The Shuto expressway T-pier: a tapered 12 m cap on one rectangular column.
    ("hammerhead", -1.8, [("cap", [(-6.0, 0.0), (6.0, 0.0), (6.0, -0.7), (1.6, -1.8), (-1.6, -1.8), (-6.0, -0.7)], 1.2),
                          ("col", _rect(1.3, 1.0), -1.2)]),
    # A portal bent for a wide deck: a crossbeam on two round columns.
    ("portal", -1.5, [("cap", [(-8.0, 0.0), (8.0, 0.0), (8.0, -1.5), (-8.0, -1.5)], 1.0),
                      ("col", _circle(-5.5, 0.0, 0.8), -1.0), ("col", _circle(5.5, 0.0, 0.8), -1.0)]),
)


def add_piers(coll=None, matkey="concrete"):
    """(Re)make the shipped `RKA_PIER_*` objects in the `ROAD_KIT` collection, leaving everything else alone."""
    import bmesh
    coll = coll or bpy.data.collections.get(COLLECTION)
    made = []
    for variant, stretch_z, parts in PIERS:
        name = PIER_PREFIX + variant
        old = bpy.data.objects.get(name)
        if old is not None:
            me_old = old.data
            bpy.data.objects.remove(old, do_unlink=True)
            if me_old is not None and me_old.users == 0:
                bpy.data.meshes.remove(me_old)
        bm = bmesh.new()
        for kind, outline, arg in parts:
            if kind == "cap":
                _prism_y(bm, outline, arg)
            else:
                _prism_z(bm, outline, arg, -PIER_REF_DEPTH)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(kc.mat(matkey))
        o = bpy.data.objects.new(name, me)
        o["rka_stretch_z"] = float(stretch_z)
        coll.objects.link(o)
        made.append(o)
    return made


def build():
    _wipe()
    mats = build_materials()
    coll = bpy.data.collections.new(COLLECTION)
    bpy.context.scene.collection.children.link(coll)
    made = []
    for name, matkey, pts in SECTIONS:
        made.append(profile(PREFIX + name, pts, matkey, coll))
    add_piers(coll)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    print("build_road_kit: %d profile(s), %d material(s) -> %s" % (len(made), len(mats), OUT))
    # B11: the road build reads the kit as DATA (`road_kit.json`), so it is rewritten with every kit build.
    sys.path.insert(0, HERE)
    import export_road_kit_data
    export_road_kit_data.export()
    for o in made:
        xs = [v[0] for v in o.bound_box]
        ys = [v[1] for v in o.bound_box]
        print("   %-28s %.2f m wide, %.2f m tall" % (o.name, max(xs) - min(xs), max(ys) - min(ys)))
    return made


if __name__ == "__main__":
    if "--add-piers" in sys.argv:
        # Additive: open the kit, (re)make only the shipped piers, save, re-export the JSON. Hand edits survive.
        bpy.ops.wm.open_mainfile(filepath=OUT)
        kc.USE_MATERIAL_LIBRARY = False
        add_piers()
        bpy.ops.wm.save_as_mainfile(filepath=OUT)
        sys.path.insert(0, HERE)
        import export_road_kit_data
        export_road_kit_data.export()
    else:
        build()
