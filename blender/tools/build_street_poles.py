"""Build the Road Kit's POLE pieces (traffic signal, street lamp, median lamp) from the Zombie Apocalypse kit.

    blender -b --factory-startup --python-exit-code 1 --python blender/tools/build_street_poles.py

Writes `assets/world_source/kits/quaternius_zombie_apocalypse/pieces/props/<Piece>.gltf + .bin`, the pieces
`assets/world_source/kits/road_kit/furniture.json` names and `point_furniture.py` places. The sources are CC0
(Quaternius, "Zombie Apocalypse Kit", see the kit's License.txt):

  * `TrafficLight_2_Japan.blend` (kit root) -- Quaternius' TrafficLight_2 re-made as a Japanese signal by the
    project owner: a horizontal three-lamp head (green, yellow, red from the left) on a mast arm, a pedestrian
    signal on the pole. It is the OWNER of the signal's shape; edit it there and re-run this.
  * `blends/StreetLights.blend` -- the download's, untouched (copied out of `source/` so the download can go).

What this changes, and why (Japanese road standards, so the kit reads as a Japanese street):

  * SIGNAL: scaled uniformly so the vehicle head's LOWER edge is `SIGNAL_HEAD_BOTTOM` (4.7 m). Japan requires a
    vehicle signal over the carriageway to clear 4.5 m; the download's head sits at 4.28 m. The pedestrian
    signal is then lifted to put its lower edge at `PED_BOTTOM` (2.5 m, the Japanese minimum for a pedestrian
    head), because a uniform scale leaves it at 2.0 m.
  * STREET LAMP: the SHAFT is stretched (the base, the collar, the arm and the luminaire stay rigid) so the
    luminaire hangs at ~`LAMP_HEIGHT` (10 m), the usual mounting height of Japanese arterial road lighting; the
    download's is 6.4 m, a residential lamp.
  * MEDIAN LAMP: the stretched lamp with its arm and luminaire mirrored, the twin-arm pole Japanese roads stand
    on a raised median.

The piece frame is the kit's (`furniture.json`): metres, +Y up, forward -Z, i.e. Blender +Y is FORWARD.
  * signal: pole at the origin, the arm reaching +X (to the RIGHT of forward), the heads facing -Y (back
    against forward). `point_furniture` passes the APPROACH direction as forward, so the arm reaches over the
    arriving lanes from a pole on their left kerb -- keep-left, the far-side corner.
  * lamp: pole at the origin, the arm reaching FORWARD (+Y). `point_furniture` passes the direction from the pole
    toward the road.
  * median lamp: arms reach +-X, forward is along the road.
The model is the size (W19): each object is exported with its transforms applied, nothing scaled at placement.
Material names are the kit's `materials/<name>.tres` (WorldBaker resolves them by name); the atlas texture is
referenced in `../../textures/`, never copied.
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KIT = os.path.join(ROOT, "assets", "world_source", "kits", "quaternius_zombie_apocalypse")
OUT = os.path.join(KIT, "pieces", "props")
TEXTURE = os.path.join(KIT, "textures", "Zombie_Atlas.png")
SIGNAL_SRC = os.path.join(KIT, "TrafficLight_2_Japan.blend")
LAMP_SRC = os.path.join(KIT, "blends", "StreetLights.blend")

SIGNAL_HEAD_BOTTOM = 4.7      # m, the vehicle head's lower edge (Japan: >= 4.5 m over a carriageway)
SIGNAL_HEAD_MIN_X = 4.2       # m in the source, where the arm ends and the head begins
PED_BOTTOM = 2.5              # m, the pedestrian head's lower edge (Japan: >= 2.5 m)
PED_BAND = (1.6, 2.7)         # m in the source (after the uniform scale), what counts as the pedestrian head
LAMP_HEIGHT = 10.0            # m, the luminaire's height
LAMP_STRETCH = (1.35, 4.5)    # m in the source: the plain shaft between the base and the collar
MAT_NAMES = {"Atlas": "MI_ZombieAtlas", "Light": "MI_LampGlass"}


def fresh():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def append_mesh(path):
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = [n for n in src.objects]
    objs = [o for o in dst.objects if o is not None and o.type == "MESH"]
    if len(objs) != 1:
        raise SystemExit("build_street_poles: expected one mesh in %s, found %d" % (path, len(objs)))
    o = objs[0]
    bpy.context.scene.collection.objects.link(o)
    o.data = o.data.copy()
    if o.parent is not None:
        raise SystemExit("build_street_poles: %s is parented in %s" % (o.name, path))
    o.data.transform(o.matrix_basis)              # apply every transform: the model is the size
    o.matrix_basis = Matrix.Identity(4)
    return o


def verts(o):
    return [v.co for v in o.data.vertices]


def components(bm):
    """Loose parts of a bmesh, as lists of BMVerts."""
    seen, out = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, part = [v], []
        seen.add(v.index)
        while stack:
            a = stack.pop()
            part.append(a)
            for e in a.link_edges:
                b = e.other_vert(a)
                if b.index not in seen:
                    seen.add(b.index)
                    stack.append(b)
        out.append(part)
    return out


def build_signal():
    fresh()
    o = append_mesh(SIGNAL_SRC)
    head = [v for v in verts(o) if v.x > SIGNAL_HEAD_MIN_X]
    bottom = min(v.z for v in head)
    s = SIGNAL_HEAD_BOTTOM / bottom
    o.data.transform(Matrix.Scale(s, 4))
    # lift the pedestrian head (and its brackets): the loose parts lying wholly in the band, off the shaft axis
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.verts.ensure_lookup_table()
    lo_band, hi_band = PED_BAND[0] * s, PED_BAND[1] * s
    ped = [p for p in components(bm)
           if min(v.co.z for v in p) > lo_band and max(v.co.z for v in p) < hi_band
           and max(math.hypot(v.co.x, v.co.y) for v in p) > 0.25]
    if not ped:
        raise SystemExit("build_street_poles: no pedestrian head found in %s" % SIGNAL_SRC)
    lift = PED_BOTTOM - min(v.co.z for p in ped for v in p)
    for p in ped:
        for v in p:
            v.co.z += lift
    bm.to_mesh(o.data)
    bm.free()
    o.name = o.data.name = "TrafficLight_JP"
    return o, {"scale": s, "head_bottom": SIGNAL_HEAD_BOTTOM, "ped_lift": lift, "ped_parts": len(ped)}


def stretch_lamp(o):
    glass = [o.matrix_world @ o.data.vertices[i].co for p in o.data.polygons
             if o.material_slots[p.material_index].name == "Light" for i in p.vertices]
    lamp_z = min(v.z for v in glass)
    d = LAMP_HEIGHT - lamp_z
    z0, z1 = LAMP_STRETCH
    k = (z1 - z0 + d) / (z1 - z0)
    for v in o.data.vertices:
        if v.co.z > z1:
            v.co.z += d
        elif v.co.z > z0:
            v.co.z = z0 + (v.co.z - z0) * k
    return d


def build_lamp(twin):
    fresh()
    o = append_mesh(LAMP_SRC)
    d = stretch_lamp(o)
    # the download's arm reaches -Y: turn it to reach forward (+Y), or across (+X) for the twin
    o.data.transform(Matrix.Rotation(math.pi if not twin else math.pi / 2.0, 4, "Z"))
    if twin:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        top = max(v.co.z for v in bm.verts if math.hypot(v.co.x, v.co.y) < 0.2 and v.co.z < LAMP_HEIGHT - 3.0)
        faces = [f for f in bm.faces if all(v.co.z > top + 0.05 for v in f.verts)]
        dup = bmesh.ops.duplicate(bm, geom=faces)
        new = [g for g in dup["geom"] if isinstance(g, bmesh.types.BMVert)]
        bmesh.ops.scale(bm, vec=Vector((-1.0, 1.0, 1.0)), verts=new)
        bmesh.ops.reverse_faces(bm, faces=[g for g in dup["geom"] if isinstance(g, bmesh.types.BMFace)])
        bm.to_mesh(o.data)
        bm.free()
    o.data.update()
    o.name = o.data.name = "StreetLight_JP_Twin" if twin else "StreetLight_JP"
    return o, {"stretch": d}


def export(o, info):
    img = bpy.data.images.load(TEXTURE, check_existing=True)
    for slot in o.material_slots:
        m = slot.material
        if m is None:
            continue
        m.name = MAT_NAMES.get(m.name, m.name)
        for n in (m.node_tree.nodes if m.use_nodes else ()):
            if n.type == "TEX_IMAGE":
                n.image = img
    for sc in bpy.data.scenes:
        for ob in list(sc.objects):
            ob.select_set(ob is o)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, o.name + ".gltf")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLTF_SEPARATE", use_selection=True, export_yup=True,
                              export_apply=True, export_keep_originals=True, export_extras=False,
                              export_cameras=False, export_lights=False, export_animations=False)
    gltf = json.load(open(path))
    for im in gltf.get("images", []):
        im["uri"] = "../../textures/" + os.path.basename(im["uri"])
    lo = [min(v.co[i] for v in o.data.vertices) for i in range(3)]
    hi = [max(v.co[i] for v in o.data.vertices) for i in range(3)]
    gltf.setdefault("asset", {})["extras"] = dict(
        {"exported_by": "blender/tools/build_street_poles.py",
         "bounds_blender": [[round(x, 4) for x in lo], [round(x, 4) for x in hi]]},
        **{k: round(v, 4) if isinstance(v, float) else v for k, v in info.items()})
    with open(path, "w") as fh:
        fh.write(json.dumps(gltf, indent=1) + "\n")
    print("build_street_poles: %s  x %.2f..%.2f  y %.2f..%.2f  z %.2f..%.2f  %s"
          % (os.path.relpath(path, ROOT), lo[0], hi[0], lo[1], hi[1], lo[2], hi[2], info))


def main():
    for f in (SIGNAL_SRC, LAMP_SRC, TEXTURE):
        if not os.path.exists(f):
            raise SystemExit("build_street_poles: missing %s" % f)
    export(*build_signal())
    export(*build_lamp(twin=False))
    export(*build_lamp(twin=True))


main()
