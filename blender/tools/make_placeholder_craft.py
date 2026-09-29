"""Placeholder AIRCRAFT and small BOATS (user, 2026-09-28: "for vehicles / carriable (airplanes) generate a similar
setup ... prepare a smaller ship for control (a yard / work ship, a short-distance fishing ship) as placeholders").
Ours, CC0. Block models at real Japanese sizes, controllable through the existing carriers: an aircraft inherits
`Airplane.tscn` (carrier/aircraft/Airplane.java: thrust, lift, pitch and roll), a boat `Boat.tscn` (carrier/boat/
Boat.java: four-corner buoyancy, motor, rudder).

    blender -b --factory-startup --python-exit-code 1 --python blender/tools/make_placeholder_craft.py -- [ID ...] [--force]

For each ID it writes `assets/vehicles/<ID>.blend` (the ARTIST'S: named parts in a collection, +Y forward, the
origin at the centre of the craft's collision box -- the frame the carrier's physics uses) unless that file was edited
by hand (no `placeholder_craft` scene property, or --force), then EXPORTS `assets/vehicles/<ID>.glb` from the .blend
(an edited .blend exports too). Then `python3 tools/build_craft_scenes.py` writes the Godot scenes.

  FIJ1  fighter jet (F-2 class)                      15.5 x 11.1 x 5.0 m   flyable (Airplane)
  LIP1  light plane (Cessna 172 class, high wing)     8.3 x 11.0 x 2.7 m   flyable (Airplane)
  WOB1  harbour work boat (作業船 / small tug)         12.0 x 4.2  x 4.5 m  drivable (Boat)
  FIB1  small fishing boat (小型漁船, 集魚灯 line)      10.4 x 2.9  x 3.8 m  drivable (Boat)
The airliner and the container ship are NOT here: too large to control, they are static props / a walkable level
(kits/library Airport_Airliner, kits/interiors CargoShip).
"""
import os
import sys

import bmesh
import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIR = os.path.join(ROOT, "assets", "vehicles")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
FORCE = "--force" in argv
COLOURS = {"jet_grey": (0.42, 0.46, 0.50), "glass": (0.08, 0.12, 0.16), "dark": (0.06, 0.06, 0.07),
           "white": (0.92, 0.92, 0.90), "blue_band": (0.08, 0.20, 0.55), "red": (0.70, 0.08, 0.06),
           "hull_black": (0.07, 0.07, 0.08), "tug_orange": (0.85, 0.40, 0.08), "tyre": (0.04, 0.04, 0.04),
           "lamp": (0.95, 0.92, 0.70), "deck": (0.40, 0.36, 0.30)}


def mat(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    c = COLOURS[name]
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (c[0], c[1], c[2], 1.0)
    b.inputs["Roughness"].default_value = 0.1 if name == "glass" else 0.6
    m.diffuse_color = (c[0], c[1], c[2], 1.0)
    return m


class Part:
    def __init__(self, name):
        self.name, self.bm, self.mats = name, bmesh.new(), []

    def box(self, lo, hi, m, taper=None):
        """A box; `taper` = (dx, dz) pulls the +Y face in (a nose, a bow)."""
        if m not in self.mats:
            self.mats.append(m)
        i = self.mats.index(m)
        vs = []
        for k in range(8):
            x = hi[0] if k & 1 else lo[0]
            y = hi[1] if k & 2 else lo[1]
            z = hi[2] if k & 4 else lo[2]
            if taper and k & 2:
                x = x - taper[0] if k & 1 else x + taper[0]
                z = z - taper[1] if k & 4 else z + taper[1]
            vs.append(self.bm.verts.new((x, y, z)))
        for f in ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)):
            self.bm.faces.new([vs[j] for j in f]).material_index = i
        return self

    def emit(self, coll):
        me = bpy.data.meshes.new(self.name)
        self.bm.normal_update()
        self.bm.to_mesh(me)
        for m in self.mats:
            me.materials.append(mat(m))
        o = bpy.data.objects.new(self.name, me)
        coll.objects.link(o)


def fij1(P):
    P("fuselage").box((-0.8, -7.5, -0.9), (0.8, 6.0, 0.9), "jet_grey")
    P("nose").box((-0.8, 6.0, -0.9), (0.8, 7.75, 0.9), "jet_grey", taper=(0.7, 0.75))
    P("canopy").box((-0.45, 2.8, 0.9), (0.45, 5.4, 1.4), "glass")
    P("wing_l").box((-5.55, -4.5, -0.25), (-0.8, 0.5, -0.05), "jet_grey")
    P("wing_r").box((0.8, -4.5, -0.25), (5.55, 0.5, -0.05), "jet_grey")
    P("tail_fin").box((-0.09, -7.5, 0.9), (0.09, -4.8, 3.9), "jet_grey")
    P("stabilizer").box((-2.8, -7.5, -0.1), (2.8, -6.0, 0.05), "jet_grey")
    P("nozzle").box((-0.6, -7.75, -0.6), (0.6, -7.5, 0.6), "dark")
    P("intakes").box((-1.0, 1.0, -0.8), (1.0, 3.0, -0.2), "dark")
    return {"seats": [(0.0, 4.4, 0.35), (0.0, 3.2, 0.35)], "eye": (0.0, 4.2, 1.2)}


def lip1(P):
    P("fuselage").box((-0.55, -4.0, -0.6), (0.55, 3.0, 0.6), "white")
    P("cowling").box((-0.55, 3.0, -0.6), (0.55, 3.9, 0.5), "white", taper=(0.15, 0.15))
    P("cabin_glass").box((-0.57, 0.3, 0.15), (0.57, 2.3, 0.9), "glass")
    P("wing").box((-5.5, 0.2, 0.95), (5.5, 1.8, 1.08), "white")
    P("struts").box((-2.0, 0.9, -0.3), (-1.9, 1.1, 0.95), "white").box((1.9, 0.9, -0.3), (2.0, 1.1, 0.95), "white")
    P("tail_fin").box((-0.06, -4.1, 0.6), (0.06, -3.1, 2.0), "white")
    P("stabilizer").box((-1.7, -4.1, 0.5), (1.7, -3.2, 0.58), "white")
    P("stripe").box((-0.56, -4.0, -0.1), (0.56, 3.0, 0.05), "red")
    P("propeller").box((-0.95, 3.92, -0.12), (0.95, 3.96, 0.12), "dark")
    return {"seats": [(-0.28, 1.1, 0.05), (0.28, 1.1, 0.05)], "eye": (-0.28, 1.1, 0.75)}


def wob1(P):
    P("hull").box((-2.1, -6.0, -0.8), (2.1, 4.5, 0.7), "hull_black")
    P("bow").box((-2.1, 4.5, -0.8), (2.1, 6.0, 0.7), "hull_black", taper=(1.6, 0.0))
    P("deck").box((-2.0, -5.9, 0.7), (2.0, 5.2, 0.75), "deck")
    P("wheelhouse").box((-1.3, 0.5, 0.75), (1.3, 3.5, 2.0), "tug_orange")
    P("wheelhouse_glass").box((-1.31, 0.6, 2.0), (1.31, 3.51, 2.8), "glass")
    P("wheelhouse_roof").box((-1.4, 0.4, 2.8), (1.4, 3.6, 2.95), "tug_orange")
    P("mast").box((-0.08, 1.9, 2.95), (0.08, 2.1, 4.5), "white")
    for y in (-4.0, -1.5, 3.8):                          # tyre fenders along both sides
        P("fenders").box((-2.25, y - 0.4, -0.2), (-2.1, y + 0.4, 0.5), "tyre").box((2.1, y - 0.4, -0.2), (2.25, y + 0.4, 0.5), "tyre")
    P("bollards").box((-0.3, -5.4, 0.75), (0.3, -4.9, 1.2), "dark")
    return {"seats": [(0.0, 2.6, 0.95), (-0.9, 1.2, 0.95), (0.9, 1.2, 0.95), (0.0, -3.0, 0.95)], "eye": (0.0, 2.6, 2.3)}


def fib1(P):
    P("hull").box((-1.45, -5.2, -0.6), (1.45, 3.8, 0.6), "white")
    P("bow").box((-1.45, 3.8, -0.6), (1.45, 5.2, 0.75), "white", taper=(1.2, 0.0))
    P("band").box((-1.46, -5.2, -0.1), (1.46, 3.8, 0.05), "blue_band")
    P("deck").box((-1.35, -5.1, 0.6), (1.35, 4.2, 0.63), "deck")
    P("wheelhouse").box((-0.9, -2.2, 0.63), (0.9, 0.2, 1.8), "white")
    P("wheelhouse_glass").box((-0.91, -0.6, 1.8), (0.91, 0.21, 2.5), "glass")
    P("wheelhouse_roof").box((-1.0, -2.3, 2.5), (1.0, 0.3, 2.6), "white")
    P("mast").box((-0.06, 1.8, 0.63), (0.06, 2.0, 3.8), "white")
    for k in range(6):                                   # the 集魚灯 (fish-attracting lamps) on their wire
        y = 3.6 - k * 1.4
        P("lamps").box((-0.15, y - 0.15, 2.9), (0.15, y + 0.15, 3.2), "lamp")
    return {"seats": [(0.0, -0.4, 0.85), (-0.7, 2.5, 0.85), (0.7, 2.5, 0.85), (0.0, -4.0, 0.85)], "eye": (0.0, -0.4, 2.1)}


CRAFT = {"FIJ1": fij1, "LIP1": lip1, "WOB1": wob1, "FIB1": fib1}


def generated(path):
    if not os.path.exists(path):
        return True
    bpy.ops.wm.open_mainfile(filepath=path)
    return "placeholder_craft" in bpy.context.scene


def build(cid):
    path = os.path.join(DIR, cid + ".blend")
    if FORCE or generated(path):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        parts = {}
        info = CRAFT[cid](lambda n: parts.setdefault(n, Part(n)))
        coll = bpy.data.collections.new(cid)
        bpy.context.scene.collection.children.link(coll)
        for p in parts.values():
            p.emit(coll)
        for i, s in enumerate(info["seats"]):
            e = bpy.data.objects.new("seat_%d" % i, None)
            e.location = s
            e.empty_display_size = 0.2
            coll.objects.link(e)
        e = bpy.data.objects.new("eye", None)
        e.location = info["eye"]
        coll.objects.link(e)
        bpy.context.scene["placeholder_craft"] = ("generated by blender/tools/make_placeholder_craft.py: replace the "
                                                  "parts (+Y forward, the origin at the collision box's centre), keep "
                                                  "the seat_N and eye Empties")
        bpy.ops.wm.save_as_mainfile(filepath=path)
        print("[make_placeholder_craft] %s: %d parts, %d seats -> %s" % (cid, len(parts), len(info["seats"]), path))
    else:
        print("[make_placeholder_craft] %s: KEPT (edited by hand); exporting it" % cid)
    # export the .blend (generated or the artist's) and its seats / eye in Godot axes
    import json
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in bpy.context.view_layer.objects:
        o.select_set(o in meshes)
    bpy.ops.export_scene.gltf(filepath=os.path.join(DIR, cid + ".glb"), export_format="GLB", use_selection=True,
                              export_yup=True, export_apply=True, export_cameras=False, export_lights=False)
    g = lambda v: [round(v[0], 4), round(v[2], 4), round(-v[1], 4)]
    seats = [g(o.location) for o in sorted(bpy.context.scene.objects, key=lambda o: o.name) if o.name.startswith("seat_")]
    eye = next(g(o.location) for o in bpy.context.scene.objects if o.name == "eye")
    json.dump({"id": cid, "seats": seats, "eye": eye}, open(os.path.join(DIR, cid + ".craft.json"), "w"), indent=1)


for cid in [a for a in argv if not a.startswith("--")] or list(CRAFT):
    build(cid)
