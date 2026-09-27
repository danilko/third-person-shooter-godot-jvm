"""Build the Road Kit's POLE pieces (traffic signal, street lamp, median lamp) from the Zombie Apocalypse kit.

    blender -b --factory-startup --python-exit-code 1 --python blender/tools/build_street_poles.py

Writes `assets/world_source/kits/quaternius_zombie_apocalypse/pieces/props/<Piece>.gltf + .bin`, the pieces
`assets/world_source/kits/road_kit/furniture.json` names and `point_furniture.py` places. The sources are CC0
(Quaternius, "Zombie Apocalypse Kit", see the kit's License.txt):

  * `TrafficLight_2_Japan.blend` (kit root) -- Quaternius' TrafficLight_2 re-made as a Japanese signal by the
    project owner: a horizontal three-lamp head (green, yellow, red from the left) on a mast arm, a pedestrian
    signal on the pole. It is the OWNER of the signal's shape; edit it there and re-run this.
  * `blends/StreetLights.blend` -- the download's, untouched (copied out of `source/` so the download can go).

What the SIGNAL is, and why (Japanese road standards) -- made IN `TrafficLight_2_Japan.blend` (2026-09-26, user:
"modify blender directly, so the artist can track the changes"), by the one-shot `-- --japanize`; the build only
verifies it (`build_signal`) and reads its markers:

  * SIGNAL: scaled uniformly so the vehicle head's LOWER edge is `SIGNAL_HEAD_BOTTOM` (4.7 m). Japan requires a
    vehicle signal over the carriageway to clear 4.5 m; the download's head sat at 4.28 m. The pedestrian
    signal lifted to put its lower edge at `PED_BOTTOM` (2.5 m, the Japanese minimum for a pedestrian head). The
    download's "E 12 St" name plate deleted. EMPTIES (collection `Markers`): `Lamp_Green/Yellow/Red` and
    `Lamp_Ped_Red/Green` on the lenses (arrow = the way the lens faces), `NamePlate` where the runtime draws the
    street's Japanese name plate (custom props width/height). Move a marker in the .blend and re-run this.
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
    """The Japanese signal as the .blend holds it. The scale to the 4.7 m head, the 2.5 m pedestrian head and the
    removal of the kit's "E 12 St" plate are made IN `TrafficLight_2_Japan.blend` (`japanize_signal_blend`, run once
    on 2026-09-26 at the user's ask: "modify blender directly, so the artist can track the changes") -- so what the
    artist opens is what ships, and this build only VERIFIES it and exports. The lamp lenses and the name-plate
    anchor are EMPTIES in the same file (`LAMP_MARKERS`, `PLATE_MARKER`): move one there and the runtime lights /
    plates follow on the next build."""
    fresh()
    o = append_mesh(SIGNAL_SRC)
    head = [v for v in verts(o) if v.x > SIGNAL_HEAD_MIN_X]
    bottom = min(v.z for v in head)
    if abs(bottom - SIGNAL_HEAD_BOTTOM) > 0.01:
        raise SystemExit("build_street_poles: %s's vehicle head bottom is %.3f m, not %.1f -- run "
                         "`-- --japanize` once on it (see japanize_signal_blend)" % (SIGNAL_SRC, bottom,
                                                                                  SIGNAL_HEAD_BOTTOM))
    o.name = o.data.name = "TrafficLight_JP"
    lamps = read_markers(SIGNAL_SRC)
    with open(os.path.join(OUT, "TrafficLight_JP.lamps.json"), "w") as fh:
        fh.write(json.dumps(lamps, indent=1, sort_keys=True) + "\n")
    return o, {"head_bottom": round(bottom, 4), "markers": len(lamps["vehicle"]) + len(lamps["pedestrian"]) + 1}


#: The markers in TrafficLight_2_Japan.blend (Empties, Blender frame, their -Y / +X arrow the lens's facing):
#: name -> (group, colour). The runtime (world.TrafficSignals) reads them from TrafficLight_JP.lamps.json.
LAMP_MARKERS = {"Lamp_Green": ("vehicle", "green"), "Lamp_Yellow": ("vehicle", "yellow"),
                "Lamp_Red": ("vehicle", "red"), "Lamp_Ped_Red": ("pedestrian", "red"),
                "Lamp_Ped_Green": ("pedestrian", "green")}
PLATE_MARKER = "NamePlate"


def read_markers(path):
    """The lamp and plate EMPTIES of `path`, in the GODOT piece frame (x, z, -y)."""
    # append_mesh has appended every object of the file already (the markers with the mesh)
    got = {n: bpy.data.objects[n] for n in list(LAMP_MARKERS) + [PLATE_MARKER] if n in bpy.data.objects}
    missing = [n for n in list(LAMP_MARKERS) + [PLATE_MARKER] if n not in got]
    if missing:
        raise SystemExit("build_street_poles: %s has no marker(s) %s" % (path, missing))

    def g(v):
        return [round(v[0], 4), round(v[2], 4), round(-v[1], 4)]
    out = {"vehicle": [], "pedestrian": [],
           "notes": "Written by blender/tools/build_street_poles.py from the EMPTIES in TrafficLight_2_Japan.blend "
                    "(Lamp_*, NamePlate): TrafficLight_JP's lamp lenses and name plate in the Godot piece frame; "
                    "read by world.TrafficSignals."}
    for n, (grp, colour) in LAMP_MARKERS.items():
        e = got[n]
        m = e.matrix_basis              # unparented, and an appended object is in no scene: basis = world
        fwd = (m.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()       # an Empty's arrow is its local +Z
        out[grp].append({"colour": colour, "pos": g(m.translation), "normal": g(fwd),
                         "radius": round(float(e.get("radius", 0.12)), 4)})
    p = got[PLATE_MARKER]
    fwd = (p.matrix_basis.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
    out["plate"] = {"pos": g(p.matrix_basis.translation), "normal": g(fwd),
                    "size": [round(float(p.get("width", 1.4)), 4), round(float(p.get("height", 0.4)), 4)]}
    for k in ("vehicle", "pedestrian"):
        out[k].sort(key=lambda d: ("green", "yellow", "red").index(d["colour"]))
    return out


def japanize_signal_blend():
    """ONE-SHOT, run on `TrafficLight_2_Japan.blend` itself (`-- --japanize`), which it then SAVES: the edits the
    build used to make in memory, now visible to the artist in the file. Refuses a file already done.
      * scaled so the vehicle head's lower edge is SIGNAL_HEAD_BOTTOM (Japan: >= 4.5 m over a carriageway);
      * the pedestrian head lifted to PED_BOTTOM (Japan: >= 2.5 m);
      * the download's "E 12 St" name plate deleted (a Manhattan street); a NamePlate EMPTY marks where the runtime
        draws the Japanese plate -- the street's real name in kanji and romaji (world.TrafficSignals);
      * EMPTIES on the three front lenses of the vehicle head and the two of the pedestrian head (Lamp_*), each
        arrow pointing the way the lens faces: where the runtime lights them."""
    bpy.ops.wm.open_mainfile(filepath=SIGNAL_SRC)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if len(meshes) != 1 or any(n in bpy.data.objects for n in LAMP_MARKERS):
        raise SystemExit("build_street_poles: %s is already japanized (or has %d meshes)" % (SIGNAL_SRC, len(meshes)))
    o = meshes[0]
    o.data.transform(o.matrix_basis)
    o.matrix_basis = Matrix.Identity(4)
    head = [v.co for v in o.data.vertices if v.co.x > SIGNAL_HEAD_MIN_X]
    s = SIGNAL_HEAD_BOTTOM / min(v.z for v in head)
    o.data.transform(Matrix.Scale(s, 4))
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.verts.ensure_lookup_table()
    lo_band, hi_band = PED_BAND[0] * s, PED_BAND[1] * s
    ped = [p for p in components(bm)
           if min(v.co.z for v in p) > lo_band and max(v.co.z for v in p) < hi_band
           and max(math.hypot(v.co.x, v.co.y) for v in p) > 0.25]
    lift = PED_BOTTOM - min(v.co.z for p in ped for v in p)
    for p in ped:
        for v in p:
            v.co.z += lift
    plate = [p for p in components(bm)
             if min(v.co.x for v in p) > PLATE_X[0] and max(v.co.x for v in p) < PLATE_X[1]
             and min(v.co.z for v in p) > head_z_of(bm) - 0.3]
    pb = [(min(v.co[i] for p in plate for v in p), max(v.co[i] for p in plate for v in p)) for i in range(3)]
    lamps = lamp_positions(bm, ped)
    bmesh.ops.delete(bm, geom=list({f for p in plate for v in p for f in v.link_faces}), context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(o.data)
    bm.free()
    o.data.update()
    col = bpy.data.collections.get("Markers") or bpy.data.collections.new("Markers")
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)

    def empty(name, pos, aim, props):
        e = bpy.data.objects.new(name, None)
        e.empty_display_type = "SINGLE_ARROW"
        e.empty_display_size = 0.3
        e.location = pos
        e.rotation_euler = Vector(aim).to_track_quat("Z", "Y").to_euler()
        for k, v in props.items():
            e[k] = v
        col.objects.link(e)
    for name, (grp, colour) in LAMP_MARKERS.items():
        d = next(d for d in lamps[grp] if d["colour"] == colour)
        empty(name, d["pos"], d["aim"], {"radius": d["radius"]})
    empty(PLATE_MARKER, ((pb[0][0] + pb[0][1]) / 2, pb[1][0] - 0.01, (pb[2][0] + pb[2][1]) / 2), (0.0, -1.0, 0.0),
          {"width": 1.4, "height": 0.4})
    bpy.ops.wm.save_mainfile()
    print("build_street_poles: japanized %s (scale %.4f, pedestrian head +%.3f m, %d plate parts deleted, %d markers)"
          % (SIGNAL_SRC, s, lift, len(plate), len(LAMP_MARKERS) + 1))


PLATE_X = (2.3, 3.9)          # m, the plate's span along the arm (after scaling): parts wholly inside it go


def head_z_of(bm):
    """The vehicle head's lower edge (the arm's height at its end)."""
    return min(v.co.z for v in bm.verts if v.co.x > SIGNAL_HEAD_MIN_X)


def lamp_positions(bm, ped):
    """The lenses, measured off the geometry (Blender frame), for japanize_signal_blend's markers: the three FRONT
    hoods of the vehicle head (it faces -Y: green, yellow, red from the left as a driver sees them -- ascending x),
    each lens at its hood's back rim; the pedestrian head's two lenses (red man above, green man below) on its +X
    face."""
    parts = components(bm)
    hoods = sorted((p for p in parts if min(v.co.x for v in p) > SIGNAL_HEAD_MIN_X and len(p) == 48
                    and max(v.co.y for v in p) < 0.0), key=lambda p: min(v.co.x for v in p))
    if len(hoods) != 3:
        raise SystemExit("build_street_poles: expected 3 front hoods on the vehicle head, found %d" % len(hoods))
    veh = []
    for colour, p in zip(("green", "yellow", "red"), hoods):
        cx = sum(v.co.x for v in p) / len(p)
        cz = (min(v.co.z for v in p) + max(v.co.z for v in p)) / 2
        lens_y = max(v.co.y for v in p) - 0.02
        r = (max(v.co.x for v in p) - min(v.co.x for v in p)) / 2 * 0.8
        veh.append({"colour": colour, "pos": (cx, lens_y, cz), "aim": (0.0, -1.0, 0.0), "radius": round(r, 4)})
    boxes = sorted((p for p in ped if len(p) == 32), key=lambda p: -min(v.co.z for v in p))
    if len(boxes) != 2:
        raise SystemExit("build_street_poles: expected 2 pedestrian lamp boxes, found %d" % len(boxes))
    pl = []
    for colour, p in zip(("red", "green"), boxes):
        x1 = max(v.co.x for v in p) + 0.01
        cy = (min(v.co.y for v in p) + max(v.co.y for v in p)) / 2
        cz = (min(v.co.z for v in p) + max(v.co.z for v in p)) / 2
        half = (max(v.co.z for v in p) - min(v.co.z for v in p)) / 2 * 0.8
        pl.append({"colour": colour, "pos": (x1, cy, cz), "aim": (1.0, 0.0, 0.0), "radius": round(half, 4)})
    return {"vehicle": veh, "pedestrian": pl}


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
    if "--japanize" in sys.argv:
        japanize_signal_blend()
        return
    export(*build_signal())
    export(*build_lamp(twin=False))
    export(*build_lamp(twin=True))


main()
