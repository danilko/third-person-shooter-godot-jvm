"""Build the Road Kit's POLE pieces (traffic signal, street lamp, median lamp) from the Zombie Apocalypse kit.

    blender -b --factory-startup --python-exit-code 1 --python blender/tools/build_street_poles.py

Writes `assets/world_source/kits/quaternius_zombie_apocalypse/pieces/props/<Piece>.gltf + .bin`, the pieces
`assets/world_source/kits/road_kit/furniture.json` names and `point_furniture.py` places. The sources are CC0
(Quaternius, "Zombie Apocalypse Kit", see the kit's License.txt):

  * `TrafficLight_2_Japan.blend` (kit root) -- Quaternius' TrafficLight_2 re-made as a Japanese signal by the
    project owner: a horizontal three-lamp head (green, yellow, red from the left) on a mast arm, a pedestrian
    signal on the pole. It is the OWNER of the signal's shape; edit it there and re-run this.
  * `blends/StreetLights.blend` -- the download's, untouched (copied out of `source/` so the download can go).

What the SIGNAL is, and why (Japanese road standards) -- all of it IN `TrafficLight_2_Japan.blend`, where the artist
tracks it (the build only verifies and joins):

  * the vehicle head's LOWER edge ~`SIGNAL_HEAD_BOTTOM` (4.7 m; Japan: >= 4.5 m over a carriageway), the pedestrian
    head's at 2.5 m (the Japanese minimum), no "E 12 St" plate;
  * the parts are SEPARATE objects (2026-09-26): `Pole`, `TrafficLight` (arm + vehicle head), `PedLight` and each
    LENS (`TrafficLight_Lamp_Green/Yellow/Red` -- double-faced, the head serves both approaches of its phase --
    and `Lamp_Ped_Red/Green`); two pieces are joined from them (`build_signals`): `TrafficLight_JP` (pole + arm +
    vehicle head, NO pedestrian head -- see SECOND_HEAD's note) and `PedSignal_JP` (pole + pedestrian head, one at
    every crosswalk end). Each piece's `<Piece>.lamps.json`
    carries its lens MESHES (world.TrafficSignals lights the lens itself) and its name plates (`NamePlateSide1/2`
    Empties, custom props width/height: the street's Japanese name, one each side of the arm).
  Built HERE from the other download (no authored file to edit):
  * STREET LAMP: the SHAFT is stretched (the base, the collar, the arm and the luminaire stay rigid) so the
    luminaire hangs at ~`LAMP_HEIGHT` (10 m), the usual mounting height of Japanese arterial road lighting; the
    download's is 6.4 m, a residential lamp.
  * MEDIAN LAMP: the stretched lamp with its arm and luminaire mirrored, the twin-arm pole Japanese roads stand
    on a raised median.

The piece frame is the kit's (`furniture.json`): metres, +Y up, forward -Z, i.e. Blender +Y is FORWARD.
  * signal: pole at the origin, the arm reaching +X (to the RIGHT of forward), the heads facing -Y (back
    against forward). `point_furniture` passes the APPROACH direction as forward, so the arm reaches over the
    arriving lanes from a pole on their left kerb -- keep-left, the far-side corner.
  * pedestrian signal: pole at the origin, the head facing -Y (Godot +Z), toward the crosswalk's far end.
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


#: The objects of TrafficLight_2_Japan.blend (the artist's split, 2026-09-26: "split the ped object / ped signals /
#: traffic pole"): the POLE, the ARM with the vehicle head, the PEDESTRIAN head, and each LENS as its own mesh, so the
#: runtime lights the lens itself instead of a ball in front of it. Two pieces are made of them:
#:   * TrafficLight_JP -- pole + arm + vehicle head + pedestrian head (a signalised junction's far-side pole);
#:   * PedSignal_JP   -- pole + pedestrian head only (a crosswalk end no vehicle pole serves), turned so its head
#:     faces the piece's -Y (Godot +Z), the convention point_furniture places a pedestrian signal by.
POLE, ARM, PED = "Pole", "TrafficLight", "PedLight"
LENSES = {"TrafficLight_Lamp_Green": ("vehicle", "green"), "TrafficLight_Lamp_Yellow": ("vehicle", "yellow"),
          "TrafficLight_Lamp_Red": ("vehicle", "red"), "Lamp_Ped_Red": ("pedestrian", "red"),
          "Lamp_Ped_Green": ("pedestrian", "green")}
PLATES = ("NamePlateSide1", "NamePlateSide2")
#: The material the baked (unlit) lenses wear: dark glass, so an OFF lens does not read as lit
#: (`materials/MI_SignalLens.tres`; the lit one is the runtime's, world.TrafficSignals).
LENS_OFF = "MI_SignalLens"
#: PedSignal_JP's turn about Z: the pedestrian head faces +X in the .blend, the piece wants it facing -Y.
PED_TURN = -math.pi / 2.0
#: ONE PEDESTRIAN HEAD PER CROSSWALK END, ON ITS OWN POLE (user, 2026-09-27: "avoid 2 formats / 2 pedestrian lights
#: for the same direction"). Japan mounts a pedestrian head on the vehicle-signal pole (共架) only where that pole
#: stands AT the crosswalk end; ours stands at the far-side corner, metres past it, so its own head doubled the
#: standalone one. So the vehicle signal carries NO pedestrian head, and every crosswalk end gets a PedSignal_JP. The
#: corner-pole variants (a second head at 90 degrees) went with it.
SECOND_HEAD = {}


def second_turn(name):
    return SECOND_HEAD.get(name, 0.0)


def load_signal_objects():
    """Every object of the signal .blend, appended, transforms applied (the model is the size)."""
    fresh()
    with bpy.data.libraries.load(SIGNAL_SRC, link=False) as (src, dst):
        dst.objects = [n for n in src.objects]
    got = {o.name: o for o in dst.objects if o is not None}
    need = [POLE, ARM, PED] + list(LENSES) + list(PLATES)
    missing = [n for n in need if n not in got]
    if missing:
        raise SystemExit("build_street_poles: %s has no object(s) %s" % (SIGNAL_SRC, missing))
    for o in got.values():
        if o.parent is not None:
            raise SystemExit("build_street_poles: %s is parented in %s" % (o.name, SIGNAL_SRC))
        if o.type == "MESH":
            o.data = o.data.copy()
            o.data.transform(o.matrix_basis)
            o.matrix_basis = Matrix.Identity(4)
    return got


def join_piece(name, parts, lens_names, turn=0.0):
    """One mesh object named `name` from copies of `parts` (an object, or `(object, turn about Z)` for a turned copy --
    a second pedestrian head), the faces of `lens_names` re-materialled LENS_OFF, the whole turned `turn` about Z."""
    off = bpy.data.materials.get(LENS_OFF)
    if off is None:
        off = bpy.data.materials.new(LENS_OFF)
        off.diffuse_color = (0.04, 0.045, 0.05, 1.0)
        off.use_nodes = True
        bsdf = next(n for n in off.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        bsdf.inputs["Base Color"].default_value = (0.04, 0.045, 0.05, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.5
    objs = []
    for o in parts:
        o, own = o if isinstance(o, tuple) else (o, 0.0)
        c = o.copy()
        c.data = o.data.copy()
        if own:
            c.data.transform(Matrix.Rotation(own, 4, "Z"))
        if o.name in lens_names:
            c.data.materials.clear()
            c.data.materials.append(off)
            for poly in c.data.polygons:
                poly.material_index = 0
        bpy.context.scene.collection.objects.link(c)
        objs.append(c)
    for sc in bpy.data.scenes:
        for ob in list(sc.objects):
            ob.select_set(ob in objs)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    if turn:
        o.data.transform(Matrix.Rotation(turn, 4, "Z"))
    o.name = o.data.name = name
    return o


def lens_record(o, turn, head=0):
    """One lens in the GODOT piece frame (x, z, -y): its triangles (for the runtime's lit copy), the centre and
    facing of its FRONT lens (the faces whose normal points most nearly the way the lens looks), a radius."""
    rot = Matrix.Rotation(turn, 4, "Z")
    me = o.data
    me.calc_loop_triangles()

    def g(v):
        return [round(v[0], 4), round(v[2], 4), round(-v[1], 4)]
    tris = []
    for t in me.loop_triangles:
        for i in t.vertices:
            tris.extend(g(rot @ me.vertices[i].co))
    # the lens faces: the largest group of near-parallel normals (a double-faced vehicle head has two, front and
    # back: the FRONT is the one facing -Y in the .blend, or +X for a pedestrian lens)
    want = Vector((1.0, 0.0, 0.0)) if LENSES[o.name][0] == "pedestrian" else Vector((0.0, -1.0, 0.0))
    front = [p for p in me.polygons if p.normal.dot(want) > 0.8]
    if not front:
        raise SystemExit("build_street_poles: %s has no face looking %s" % (o.name, tuple(want)))
    area = sum(p.area for p in front)
    c = sum((p.center * p.area for p in front), Vector()) / area
    r = max((me.vertices[i].co - c).length for p in front for i in p.vertices)
    n = (rot.to_3x3() @ want).normalized()
    return {"colour": LENSES[o.name][1], "mesh": o.name, "pos": g(rot @ c), "normal": g(n),
            "radius": round(r, 4), "tris": tris, "head": head}


def plate_record(e):
    m = e.matrix_basis
    fwd = (m.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
    return {"marker": e.name, "pos": [round(m.translation[0], 4), round(m.translation[2], 4),
                                      round(-m.translation[1], 4)],
            "normal": [round(fwd[0], 4), round(fwd[2], 4), round(-fwd[1], 4)],
            "size": [round(float(e.get("width", 1.4)), 4), round(float(e.get("height", 0.4)), 4)]}


def write_lamps(name, lenses, plates, turn, second=None):
    out = {"vehicle": [], "pedestrian": [], "plates": [plate_record(p) for p in plates],
           "notes": "Written by blender/tools/build_street_poles.py from TrafficLight_2_Japan.blend: %s's lenses "
                    "(the lens MESHES, triangles in the Godot piece frame, lit by world.TrafficSignals) and its "
                    "name plates (the NamePlateSide* Empties)." % name}
    for o in lenses:
        out[LENSES[o.name][0]].append(lens_record(o, turn))
    for o in (second or ()):                 # the second pedestrian head: its lenses turned with it, `head` 1
        out["pedestrian"].append(lens_record(o, second_turn(name), head=1))
    for k in ("vehicle", "pedestrian"):
        out[k].sort(key=lambda d: (d.get("head", 0), ("green", "yellow", "red").index(d["colour"])))
    with open(os.path.join(OUT, name + ".lamps.json"), "w") as fh:
        fh.write(json.dumps(out, indent=1, sort_keys=True) + "\n")
    return out


def build_signals():
    """The two signal pieces as TrafficLight_2_Japan.blend holds them (every shape edit is made IN the .blend, where
    the artist tracks it; this only verifies, joins and exports), plus each piece's lamps.json."""
    got = load_signal_objects()
    head = [v.co for v in got[ARM].data.vertices if v.co.x > SIGNAL_HEAD_MIN_X]
    bottom = min(v.z for v in head)
    if abs(bottom - SIGNAL_HEAD_BOTTOM) > 0.15:
        raise SystemExit("build_street_poles: %s's vehicle head bottom is %.3f m, not ~%.1f"
                         % (SIGNAL_SRC, bottom, SIGNAL_HEAD_BOTTOM))
    ped_bottom = min(v.co.z for v in got[PED].data.vertices)
    veh = [got[n] for n in LENSES if LENSES[n][0] == "vehicle"]
    ped = [got[n] for n in LENSES if LENSES[n][0] == "pedestrian"]
    plates = [got[n] for n in PLATES]
    out = []
    full = write_lamps("TrafficLight_JP", veh, plates, 0.0)
    o = join_piece("TrafficLight_JP", [got[POLE], got[ARM]] + veh, set(LENSES))
    out.append((o, {"head_bottom": round(bottom, 4), "ped_bottom": round(ped_bottom, 4),
                    "lenses": len(full["vehicle"]) + len(full["pedestrian"]), "plates": len(full["plates"])}))
    for var, t2 in SECOND_HEAD.items():
        v = write_lamps(var, veh + ped, plates, 0.0, second=ped)
        o = join_piece(var, [got[POLE], got[ARM], got[PED], (got[PED], t2)] + veh + ped + [(q, t2) for q in ped],
                       set(LENSES))
        out.append((o, {"head_bottom": round(bottom, 4), "ped_bottom": round(ped_bottom, 4),
                        "lenses": len(v["vehicle"]) + len(v["pedestrian"]), "plates": len(v["plates"])}))
    only = write_lamps("PedSignal_JP", ped, [], PED_TURN)
    o = join_piece("PedSignal_JP", [got[POLE], got[PED]] + ped, set(LENSES), PED_TURN)
    out.append((o, {"ped_bottom": round(ped_bottom, 4), "lenses": len(only["pedestrian"])}))
    return out


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
    for o, info in build_signals():
        export(o, info)
    export(*build_lamp(twin=False))
    export(*build_lamp(twin=True))


main()
