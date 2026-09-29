"""EMU1 -- a Japanese commuter EMU (通勤形電車) built to the LARGEST standard conventional-line size, so every station,
track spacing and clearance measured against it holds for any real train that runs on the 1067 mm lines.

    blender -b --python-exit-code 1 --python blender/tools/make_train.py [-- --force]

Writes `assets/vehicles/trains/EMU1.blend` (it OWNS the model afterwards: a regenerate refuses to overwrite an edited
file without `--force`), `EMU1_Tc.glb` (the cab car) and `EMU1_M.glb` (the middle car, with a pantograph), and
`EMU1.train.json` -- every number MEASURED off the built meshes, which the stations and the gauge checks read
(`tools/godot/probe_train_fit.gd`). A 4-car set is Tc + M + M + Tc (turned).

THE SIZE (user, 2026-09-29: "assume the largest Japan metro/rail train width to be on the safe side"). Numbers are the
published norms for a 20 m, 4-door, wide-body commuter car on the 1067 mm gauge (the JR East E231/E233 family and the
private lines built to the same envelope); no line's livery, logo or name is copied:
  * car body 19.5 m long, 20.0 m over the couplers; bogie centres 13.8 m apart, 2.1 m wheelbase, 0.86 m wheels;
  * WIDE BODY 2.95 m at the waist (the widest standard car; a subway car is 2.8-2.85 m), narrowing to 2.80 m at the
    side sill below the floor -- the curve that lets the car overhang a platform whose top is at its floor;
  * floor 1.13 m over the rail head (a platform is 1.10: a 3 cm step), roof 3.62 m, roof equipment to 3.98 m, the
    pantograph folded to 4.05 m (the conventional-line vehicle gauge is 3.0 m wide, 4.1 m high);
  * four 1.3 m doors a side on a 4.82 m pitch.
Blender frame (the vehicle convention, blender/VEHICLE_AUTHORING.md): the car FACES +Y (Godot -Z), X across, Z up;
origin at the car's centre on the RAIL HEAD plane between the two rails.
"""
import json
import math
import os
import sys

import bmesh
import bpy

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(ROOT, "assets", "vehicles", "trains")
BLEND = os.path.join(OUT, "EMU1.blend")

BODY_L = 19.5
COUPLED_L = 20.0
BOGIE_C = 13.8 / 2.0
WHEELBASE = 2.1
WHEEL_R = 0.43
GAUGE = 1.067
FLOOR_Z = 1.13
DOOR_W = 1.3
DOOR_H = 1.85
DOOR_Y = (-7.23, -2.41, 2.41, 7.23)
# the body's cross-section, (half width, z over the rail head) from the sill up to the roof's crown: the wide body
PROFILE = [(1.40, 0.95), (1.44, 1.10), (1.465, 1.30), (1.475, 1.60), (1.475, 2.20), (1.465, 2.60), (1.44, 3.00),
           (1.40, 3.20), (1.30, 3.36), (1.10, 3.50), (0.80, 3.58), (0.40, 3.615), (0.0, 3.62)]
MATS = {"stainless": (0.72, 0.74, 0.76, 1.0), "band": (0.10, 0.55, 0.45, 1.0), "glass": (0.05, 0.07, 0.09, 1.0),
        "under": (0.12, 0.12, 0.13, 1.0), "roof": (0.35, 0.36, 0.38, 1.0), "door": (0.68, 0.70, 0.72, 1.0),
        "light": (1.0, 0.95, 0.80, 1.0), "sign": (0.02, 0.02, 0.02, 1.0), "rubber": (0.08, 0.08, 0.08, 1.0)}


def mat(name):
    m = bpy.data.materials.get("M_Train_" + name)
    if m is None:
        m = bpy.data.materials.new("M_Train_" + name)
        m.use_nodes = True
        bsdf = m.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = MATS[name]
        bsdf.inputs["Metallic"].default_value = 0.8 if name in ("stainless", "door") else 0.0
        bsdf.inputs["Roughness"].default_value = 0.35 if name in ("stainless", "door", "glass") else 0.7
        if name == "light":
            bsdf.inputs["Emission Color"].default_value = MATS[name]
            bsdf.inputs["Emission Strength"].default_value = 3.0
        m.diffuse_color = MATS[name]
    return m


class Mesh:
    def __init__(self, name):
        self.name = name
        self.bm = bmesh.new()
        self.mats = []

    def mi(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def box(self, lo, hi, m):
        vs = [self.bm.verts.new((x, y, z)) for z in (lo[2], hi[2]) for y in (lo[1], hi[1]) for x in (lo[0], hi[0])]
        k = self.mi(m)
        for f in ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)):
            self.bm.faces.new([vs[i] for i in f]).material_index = k

    def cyl_x(self, cx, cy, cz, r, w, m, n=16):
        """A cylinder along X (a wheel), centred at (cx, cy, cz)."""
        k = self.mi(m)
        rings = []
        for x in (cx - w / 2, cx + w / 2):
            rings.append([self.bm.verts.new((x, cy + r * math.cos(2 * math.pi * i / n),
                                             cz + r * math.sin(2 * math.pi * i / n))) for i in range(n)])
        for i in range(n):
            j = (i + 1) % n
            self.bm.faces.new([rings[0][i], rings[0][j], rings[1][j], rings[1][i]]).material_index = k
        self.bm.faces.new(rings[0][::-1]).material_index = k
        self.bm.faces.new(rings[1]).material_index = k

    def prism_y(self, prof, y0, y1, m, cap0=True, cap1=True):
        """The closed section `prof` [(x, z)] extruded along Y from y0 to y1."""
        k = self.mi(m)
        a = [self.bm.verts.new((x, y0, z)) for x, z in prof]
        b = [self.bm.verts.new((x, y1, z)) for x, z in prof]
        n = len(prof)
        for i in range(n):
            j = (i + 1) % n
            self.bm.faces.new([a[i], a[j], b[j], b[i]]).material_index = k
        if cap0:
            self.bm.faces.new(a[::-1]).material_index = k
        if cap1:
            self.bm.faces.new(b).material_index = k

    def done(self, coll):
        me = bpy.data.meshes.new(self.name)
        bmesh.ops.recalc_face_normals(self.bm, faces=list(self.bm.faces))
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.mats:
            me.materials.append(mat(m))
        ob = bpy.data.objects.new(self.name, me)
        coll.objects.link(ob)
        return ob


def section():
    """The full closed body section (x, z): the right half up, the left half down."""
    right = [(x, z) for x, z in PROFILE]
    left = [(-x, z) for x, z in reversed(PROFILE[:-1])]
    return right + left


def body(cab):
    """The body shell, windows, doors, band, ends. `cab`: a driving cab at +Y."""
    m = Mesh("Body")
    half = BODY_L / 2.0
    m.prism_y(section(), -half, half, "stainless")
    # the colour band under the windows and the roof's grey
    for sg in (-1.0, 1.0):
        x = sg * (1.475 + 0.004)
        m.box((min(x, x - sg * 0.01), -half + 0.2, 1.70), (max(x, x - sg * 0.01), half - 0.2, 1.80), "band")
    m.box((-1.25, -half + 0.3, 3.50), (1.25, half - 0.3, 3.63), "roof")
    # windows: the bays between doors, and the doors (with their own windows)
    edges = [-half + 0.9] + [v for y in DOOR_Y for v in (y - DOOR_W / 2 - 0.35, y + DOOR_W / 2 + 0.35)] + [half - 0.9]
    for sg in (-1.0, 1.0):
        x0, x1 = sorted((sg * 1.476, sg * 1.486))
        for a, b in zip(edges[0::2], edges[1::2]):
            if b - a > 0.6:
                m.box((x0, a, 1.95), (x1, b, 2.75), "glass")
        for y in DOOR_Y:
            m.box((x0, y - DOOR_W / 2, FLOOR_Z), (x1, y + DOOR_W / 2, FLOOR_Z + DOOR_H), "door")
            m.box((sorted((sg * 1.487, sg * 1.491))[0], y - DOOR_W / 2 + 0.12, 1.95),
                  (sorted((sg * 1.487, sg * 1.491))[1], y + DOOR_W / 2 - 0.12, 2.70), "glass")
            m.box((sorted((sg * 1.487, sg * 1.491))[0], y - 0.01, FLOOR_Z), (sorted((sg * 1.487, sg * 1.491))[1],
                  y + 0.01, FLOOR_Z + DOOR_H), "rubber")
    for end in (-1.0, 1.0):
        y = end * half
        if cab and end > 0:
            # the cab front: a full-width windscreen, the destination sign over it, two headlights under it
            m.box((-1.30, y, 1.95), (1.30, y + 0.03, 2.85), "glass")
            m.box((-0.80, y, 2.95), (0.80, y + 0.04, 3.20), "sign")
            for sx in (-1.0, 1.0):
                m.box((sx * 1.0 - 0.18, y, 1.45), (sx * 1.0 + 0.18, y + 0.05, 1.60), "light")
            m.box((-1.40, y, 1.10), (1.40, y + 0.12, 1.30), "band")
        else:
            # a gangway (貫通路) and its rubber bellows to the next car
            m.box((-0.55, y if end > 0 else y - 0.25, FLOOR_Z), (0.55, y + 0.25 if end > 0 else y, 3.05), "rubber")
            m.box((-0.45, y + (0.001 if end > 0 else -0.004), 1.95), (0.45, y + (0.004 if end > 0 else -0.001),
                                                                       2.80), "glass")
    return m


def underframe(pantograph):
    m = Mesh("Underframe")
    half = BODY_L / 2.0
    # under-floor equipment between the bogies, the couplers
    m.box((-1.20, -BOGIE_C + 2.0, 0.40), (1.20, BOGIE_C - 2.0, 0.95), "under")
    for end in (-1.0, 1.0):
        y = end * half
        m.box((-0.18, min(y, y + end * 0.25), 0.72), (0.18, max(y, y + end * 0.25), 0.95), "under")
    # roof: two air-conditioning units, and on a motor car a folded pantograph
    for yc in (-4.8, 4.8):
        m.box((-0.95, yc - 1.3, 3.60), (0.95, yc + 1.3, 3.98), "roof")
    if pantograph:
        m.box((-0.8, -0.8, 3.62), (0.8, 0.8, 3.72), "under")
        m.box((-0.05, -0.9, 3.72), (0.05, 0.9, 3.95), "under")
        m.box((-0.85, -0.12, 3.97), (0.85, 0.12, 4.05), "under")
    return m


def bogies():
    m = Mesh("Bogies")
    for yc in (-BOGIE_C, BOGIE_C):
        m.box((-1.15, yc - 1.6, 0.30), (1.15, yc + 1.6, 0.85), "under")
        for dy in (-WHEELBASE / 2, WHEELBASE / 2):
            for sx in (-1.0, 1.0):
                m.cyl_x(sx * (GAUGE / 2 + 0.035), yc + dy, WHEEL_R, WHEEL_R, 0.13, "under")
            m.box((-GAUGE / 2, yc + dy - 0.07, WHEEL_R - 0.07), (GAUGE / 2, yc + dy + 0.07, WHEEL_R + 0.07), "under")
    return m


def build_car(name, cab, pantograph):
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    obs = [body(cab).done(coll), underframe(pantograph).done(coll), bogies().done(coll)]
    return coll, obs


def measure(obs):
    """Every number the gauge / platform checks need, off the built vertices (not the constants above)."""
    xs, ys, zs = [], [], []
    for ob in obs:
        for v in ob.data.vertices:
            xs.append(v.co.x)
            ys.append(v.co.y)
            zs.append(v.co.z)
    body_ob = obs[0]
    bx = [abs(v.co.x) for v in body_ob.data.vertices]
    return {"half_width": round(max(abs(x) for x in xs), 4), "body_half_width": round(max(bx), 4),
            "length": round(max(ys) - min(ys), 3), "height": round(max(zs), 3), "bottom": round(min(zs), 3)}


def main():
    force = "--force" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(BLEND) and not force:
        # the .blend is the owner once it exists: export what is there, never rebuild it over an artist's edit
        bpy.ops.wm.open_mainfile(filepath=BLEND)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        build_car("EMU1_Tc", cab=True, pantograph=False)
        build_car("EMU1_M", cab=False, pantograph=True)
        bpy.data.collections["EMU1_M"].hide_render = False
        bpy.ops.wm.save_as_mainfile(filepath=BLEND)
    facts = {"id": "EMU1", "gauge_m": GAUGE, "body_length_m": BODY_L, "coupled_length_m": COUPLED_L,
             "bogie_centres_m": 2 * BOGIE_C, "wheelbase_m": WHEELBASE, "floor_m": FLOOR_Z,
             "profile": [[x, z] for x, z in PROFILE], "door_y_m": list(DOOR_Y), "door_w_m": DOOR_W, "cars": {}}
    for cname in ("EMU1_Tc", "EMU1_M"):
        coll = bpy.data.collections[cname]
        obs = [o for o in coll.objects if o.type == "MESH"]
        facts["cars"][cname] = measure(obs)
        for o in bpy.context.scene.objects:
            o.select_set(False)
        for o in obs:
            o.select_set(True)
        path = os.path.join(OUT, cname + ".glb")
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_yup=True,
                                  export_apply=True)
        print("[make_train] %s -> %s %s" % (cname, os.path.relpath(path, ROOT), facts["cars"][cname]))
    # the whole envelope the checks use: the widest point of any car, over the rail head
    facts["half_width_m"] = max(c["half_width"] for c in facts["cars"].values())
    facts["height_m"] = max(c["height"] for c in facts["cars"].values())
    with open(os.path.join(OUT, "EMU1.train.json"), "w") as fh:
        json.dump(facts, fh, indent=1)
        fh.write("\n")
    print("[make_train] EMU1: half width %.3f m, height %.3f m" % (facts["half_width_m"], facts["height_m"]))


main()
