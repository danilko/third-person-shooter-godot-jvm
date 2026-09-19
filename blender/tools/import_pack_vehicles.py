"""One-time extraction of the two cars in the elbolilloduro "Vegetation" pack into the vehicle component standard.

    blender -b --python blender/tools/import_pack_vehicles.py -- <path/to/Vegetation.fbx> [--force]

Writes `assets/vehicles/PIT1.blend` (pickup truck, the pack's `Car`) and `assets/vehicles/POC1.blend` (police car,
the pack's `Car_sheriff`), which from then on ARE those vehicles: edit them directly, then run
`build_vehicle.py -- PIT1 POC1`. It refuses to overwrite either unless `--force` (hand edits would be lost).

LICENCE — read before re-running. The pack page (elbolilloduro.itch.io/vegetation) licenses "the MODELS in this
package" as CC0. It says nothing about the textures, and this author's packs mix textures from sources that may not
be redistributed (CLAUDE.md, "NEVER commit or import an elbolilloduro download"). So only the MESHES are taken:
every material is replaced by a flat one of our own, no image is read, and the download itself is never imported
into the project (it carries a .gdignore) and should be deleted once this has run. Credited in CREDITS.md.

What it does (each a fact about the pack's layout, written down once):
  * keeps the objects of each car and drops everything else in the pack (vegetation, props, buildings);
  * applies every transform, puts the origin on the ground at mid-wheelbase, facing +Y (both cars already face +Y
    and are real-world size - the police car matches a Crown Victoria's 5.38 m - so nothing is scaled);
  * names the parts by the GTA component set (door_lf/rf/lr/rr, wheel_lf/rf/lb/rb, chassis) and SEPARATES the
    bonnet, boot and bumpers out of each single-mesh body by selecting its existing faces by region (the cut lines
    below, read off side views on a 0.5 m grid) - no geometry is added or moved;
  * flat materials: `car` (the body colour the game repaints per car) on the pickup; the Japanese patrol-car scheme
    on the police car (black below the beltline, white above, a red light bar) since its livery was a texture;
  * seat Empties on the top of each seat cushion (where a seated body's hips go).
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector, Matrix

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "assets", "vehicles")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
FORCE = "--force" in argv
paths = [a for a in argv if not a.startswith("--")]
if not paths:
    raise SystemExit("usage: blender -b --python import_pack_vehicles.py -- <Vegetation.fbx> [--force]")
FBX = paths[0]

# Cut lines are in the PACK's coordinates (the side views: front is +Y). A body face goes to a component by its
# centre; everything not claimed stays chassis.
CARS = {
    "PIT1": {
        "body": "Car",
        "parts": ["Cube.237", "Glove_box", "Pedal", "Pedal_01", "Pedal_02", "Seating", "Steering_wheel"],
        "doors": {"door_lf": "Car_Door", "door_rf": "Car_Door.001"},
        "tyres": ["Tire", "Tire.001", "Tire.002", "Tire.003"],
        "regions": {                                   # component: (y_min, y_max, z_min, z_max, top_only)
            "bump_front": (-46.98, 9e9, -9e9, 0.28, False),
            "bonnet":     (-48.07, -46.95, 0.20, 9e9, True),
            "bump_rear":  (-9e9, -51.90, -9e9, -0.30, False),
        },
        "materials": {"Car_ex": "car", "Car_in": "interior", "Tire": "tyre"},
        "seats": "Seating",                             # a bench: two seats across it
        "rear_seats": None,
    },
    "POC1": {
        "body": "Car_sheriff",
        "parts": ["Car_sheriff_In.002", "Cube.238", "Cube.239", "Cube.242", "Cube.243", "Steering_wheel.001"],
        "doors": {"door_lf": "Car_sheriff_D", "door_lr": "Car_sheriff_D.001",
                  "door_rf": "Car_sheriff_D.002", "door_rr": "Car_sheriff_D.003"},
        "tyres": ["Tire.004", "Tire.005", "Tire.006", "Tire.007"],
        "regions": {
            "bump_front": (-46.70, 9e9, -9e9, -0.20, False),
            "bonnet":     (-48.00, -46.62, 0.00, 9e9, True),
            "boot":       (-9e9, -50.95, 0.00, 9e9, True),
            "bump_rear":  (-9e9, -51.66, -9e9, -0.20, False),
            "windscreen": (-48.35, -47.40, 0.10, 9e9, False),   # only its glass faces (see GLASS_ONLY)
        },
        "materials": {"Car_sheriff": "police", "Car_sheriff_In": "interior", "Glass.001": "glass"},
        "seats": "Cube.243",                            # the front bench
        "rear_seats": "Car_sheriff_In.002",
        "beltline": -0.01,                              # below: black, above: white (the Japanese patrol car)
        "lightbar_z": 0.66,                             # faces above this are the light bar
    },
}
GLASS_ONLY = {"windscreen"}
TYRE_MAT = {"Tire", "Car_sheriff"}                    # the police car's tyres were painted from the body texture


def fail(msg):
    raise SystemExit(f"[import_pack_vehicles] {msg}")


def flat(name, color, metal=0.0, rough=0.6, alpha=1.0, emit=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial'); out.target = 'ALL'
    p = nt.nodes.new('ShaderNodeBsdfPrincipled')
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Metallic'].default_value = metal
    p.inputs['Roughness'].default_value = rough
    p.inputs['Alpha'].default_value = alpha
    if emit:
        p.inputs['Emission Color'].default_value = (*emit, 1)
        p.inputs['Emission Strength'].default_value = 2.0
    nt.links.new(p.outputs['BSDF'], out.inputs['Surface'])
    m.diffuse_color = (*color, alpha)
    if alpha < 1:
        m.surface_render_method = 'BLENDED'
    return m


def build(vid, spec):
    target = os.path.join(OUT, vid + ".blend")
    if os.path.exists(target) and not FORCE:
        print(f"[import_pack_vehicles] {vid}: {target} exists - it is the vehicle now; --force to rebuild it")
        return
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=FBX)
    OBJ = bpy.data.objects
    wanted = [spec["body"]] + spec["parts"] + list(spec["doors"].values()) + spec["tyres"]
    missing = [n for n in wanted if n not in OBJ]
    if missing:
        fail(f"{vid}: the pack no longer has {missing}")

    # keep only this car; apply transforms (parents included) into each mesh
    for n in wanted:
        o = OBJ[n]
        if o.data.users > 1:
            o.data = o.data.copy()
        o.data.transform(o.matrix_world)
    for n in wanted:
        OBJ[n].parent = None
        OBJ[n].matrix_world = Matrix.Identity(4)
    for o in list(OBJ):
        if o.name not in wanted:
            bpy.data.objects.remove(o, do_unlink=True)

    MAT = {
        "car": flat("car", (0.18, 0.32, 0.55), metal=0.4, rough=0.4),
        "interior": flat("interior", (0.12, 0.11, 0.1), rough=0.9),
        "tyre": flat("tyre", (0.02, 0.02, 0.02), rough=0.9),
        "glass": flat("glass", (0.04, 0.055, 0.06), rough=0.05, alpha=0.4),
        "police_black": flat("police_black", (0.02, 0.02, 0.025), metal=0.3, rough=0.35),
        "police_white": flat("police_white", (0.9, 0.9, 0.88), metal=0.3, rough=0.35),
        "lightbar": flat("lightbar", (0.8, 0.03, 0.03), rough=0.3, emit=(1.0, 0.05, 0.03)),
    }

    def remap(o, is_tyre=False):
        """Our flat materials, by the pack material's name; the police body is painted by height."""
        me = o.data
        old = [m.name if m else "" for m in me.materials]
        was = [p.material_index for p in me.polygons]        # read BEFORE clear(): clearing resets every index to 0
        me.materials.clear()
        index = {}
        def slot(key):
            if key not in index:
                me.materials.append(MAT[key]); index[key] = len(me.materials) - 1
            return index[key]
        for p in me.polygons:
            name = old[was[p.index]] if was[p.index] < len(old) else ""
            key = "tyre" if is_tyre else spec["materials"].get(name)
            if key is None:
                fail(f"{vid}: {o.name} uses material {name!r} with no mapping")
            if key == "police":
                c = p.center
                key = "lightbar" if c.z > spec["lightbar_z"] else ("police_white" if c.z > spec["beltline"] else "police_black")
            p.material_index = slot(key)

    for n in wanted:
        remap(OBJ[n], is_tyre=n in spec["tyres"])

    # the body's regions become components - its own faces, nothing added
    body = OBJ[spec["body"]]
    def take(name, rule, glass_only):
        y0, y1, z0, z1, top_only = rule
        bm = bmesh.new(); bm.from_mesh(body.data)
        glass = {i for i, m in enumerate(body.data.materials) if m.name == "glass"}
        pick = [f for f in bm.faces if y0 <= f.calc_center_median().y <= y1 and z0 <= f.calc_center_median().z <= z1
                and (not top_only or f.normal.z > 0.35) and ((f.material_index in glass) == glass_only)]
        if not pick:
            mats = [m.name for m in body.data.materials]
            near = sorted({(round(f.calc_center_median().y, 2), mats[f.material_index]) for f in bm.faces
                           if f.material_index in glass})[:6]
            bm.free(); fail(f"{vid}: region {name} selects no faces (materials {mats}, glass faces at {near})")
        part = bmesh.new()
        me = body.data.copy()
        bm2 = bmesh.new(); bm2.from_mesh(me)
        keep = {f.index for f in pick}
        bmesh.ops.delete(bm2, geom=[f for f in bm2.faces if f.index not in keep], context='FACES')
        bm2.to_mesh(me); bm2.free(); part.free()
        bmesh.ops.delete(bm, geom=pick, context='FACES_ONLY')
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
        bm.to_mesh(body.data); bm.free()
        o = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(o)
        return o
    for name, rule in spec["regions"].items():
        take(name, rule, name in GLASS_ONLY)

    # tyres by quadrant, doors by the table
    # centred on the WHEELS (the axle line), not on the body's vertex average, which a lopsided mesh pulls aside
    ys, xs = [], []
    for n in spec["tyres"]:
        c = sum((v.co for v in OBJ[n].data.vertices), Vector()) / len(OBJ[n].data.vertices)
        ys.append(c.y); xs.append(c.x)
    cx = (min(xs) + max(xs)) / 2
    mid_y = (min(ys) + max(ys)) / 2
    for n in spec["tyres"]:
        c = sum((v.co for v in OBJ[n].data.vertices), Vector()) / len(OBJ[n].data.vertices)
        OBJ[n].name = "wheel_" + ("l" if c.x < cx else "r") + ("f" if c.y > mid_y else "b")
    for comp, n in spec["doors"].items():
        OBJ[n].name = comp

    # seats, from the seat blocks (before the interior joins the chassis)
    seats = {}
    def seat_pair(obj_name, row):
        ps = [v.co for v in OBJ[obj_name].data.vertices]
        lo = Vector([min(p[k] for p in ps) for k in range(3)]); hi = Vector([max(p[k] for p in ps) for k in range(3)])
        half = (hi.x - lo.x) / 4
        front = [p for p in ps if p.y > lo.y + 0.5 * (hi.y - lo.y)]      # the cushion, not the backrest
        top = max(p.z for p in front)
        y = (lo.y + 0.5 * (hi.y - lo.y) + hi.y) / 2
        for s, x in (("l", cx - max(half, 0.35)), ("r", cx + max(half, 0.35))):
            seats[f"seat_{row}_{s}"] = Vector((x, y, top))
    seat_pair(spec["seats"], "front")
    if spec["rear_seats"]:
        seat_pair(spec["rear_seats"], "rear")

    # everything else is the chassis
    rest = [OBJ[spec["body"]]] + [OBJ[n] for n in spec["parts"]]
    with bpy.context.temp_override(active_object=rest[0], selected_editable_objects=rest, selected_objects=rest):
        bpy.ops.object.join()
    rest[0].name = "chassis"

    # origin: ground at mid-wheelbase, centred across; facing +Y already (steering wheel ahead of the seats)
    ground = min(v.co.z for n in ("wheel_lf", "wheel_rf", "wheel_lb", "wheel_rb") for v in OBJ[n].data.vertices)
    shift = Matrix.Translation((-cx, -mid_y, -ground))
    col = bpy.data.collections.new(vid)
    bpy.context.scene.collection.children.link(col)
    for o in list(bpy.context.scene.collection.objects):
        if o.type == 'MESH':
            o.data.transform(shift)
            o.data.name = o.name
            bpy.context.scene.collection.objects.unlink(o)
            col.objects.link(o)
    for name, p in seats.items():
        e = bpy.data.objects.new(name, None)
        e.empty_display_type = 'ARROWS'; e.empty_display_size = 0.2
        e.location = shift @ p
        col.objects.link(e)
    for m in list(bpy.data.materials):
        if m.users == 0:
            bpy.data.materials.remove(m)
    for img in list(bpy.data.images):                       # nothing of the pack's textures is kept
        bpy.data.images.remove(img)
    bpy.context.scene.render.fps = 60
    bpy.ops.wm.save_as_mainfile(filepath=target, compress=True)
    print(f"[import_pack_vehicles] {vid}: wrote {target} with "
          f"{sorted(o.name for o in col.objects if o.type == 'MESH')} and seats {sorted(seats)}")


for vid, spec in CARS.items():
    build(vid, spec)
