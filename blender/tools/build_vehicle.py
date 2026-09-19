"""Vehicle models: the artist's .blend is the SOURCE and is never written; the build splits it in memory.

    blender -b --python blender/tools/build_vehicle.py -- [id ...] [--save-parts <path.blend>]

For `assets/vehicles/<id>.blend` (default: SPC1) it opens the file, and IN MEMORY ONLY
  1. evaluates every modifier exactly as authored (Mirrors, the tyres' Subdivision) - except the two
     honeycomb grilles, which ship as a placeholder plane each (PLACEHOLDER_PLANES)
     and drops the helper objects they used (the honeycomb sheets, lattices, camera, empty meshes) and
     any stray vertex that belongs to no face (it renders nothing, but skews bounds and hinges);
  2. splits the authoring objects into the GTA III / San Andreas component set - chassis, bonnet,
     boot, bump_front, bump_rear, door_lf/rf, wing_lf/rf, windscreen, wheel_lf/rf/lb/rb - taking the
     objects that carry BOTH sides (doors, wings, tyres) apart by side;
  3. turns the car to face +Y (Godot -Z) with its origin on the ground at mid-wheelbase - a rigid move,
     the shape is untouched;
  4. puts each component's ORIGIN ON ITS HINGE (door: front edge, bonnet: rear edge, boot: front
     edge, bumper: one end), because the runtime swings a loose part about its origin;
  5. adds a `dam` shape key to every damageable component - the crumpled version the runtime blends in
     as the part takes damage (San Andreas swapped an `_ok` mesh for a `_dam` one; a shape key is the
     same idea with the in-between states for free). It is a separate key at value 0: the exported
     model is the model as authored;
  6. replaces ONLY the materials glTF cannot carry (a Translucent BSDF exports with no colour and
     renders opaque white) - every other material keeps its name and values;
then verifies the result and writes
  * `assets/vehicles/<id>.glb`
  * `assets/vehicles/<id>.vehicle.json` - MEASURED facts in GODOT axes (x, z, -y) that `Car.tscn` is
    built from and `tools/godot/probe_car.gd` checks it against: wheel centres + radius, seats, hinges,
    a convex hull for the RigidBody, bounds.
`--save-parts` also saves the split result to another .blend for inspection; it refuses the source path.

The split table (SOURCE_GROUPS) names the source objects, so renaming an object in the source file
means updating it here; the build fails loudly on any object it does not know rather than dropping it.
See blender/VEHICLE_AUTHORING.md.
"""
import bpy, bmesh, json, math, os, struct, sys
from mathutils import Vector, Matrix, noise

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIR = os.path.join(ROOT, "assets", "vehicles")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SAVE_PARTS = argv[argv.index("--save-parts") + 1] if "--save-parts" in argv else None
ids = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] != "--save-parts")]

# ── the source layout: which authoring objects make which component ─────────────────────────────
SOURCE_GROUPS = {
    "chassis":    ["back.side", "top", "Interior", "back.glass", "backdoorglass", "door frame.back",
                   "front.windo.rubber", "back.side.exhaust", "exhaust", "front.light", "back.light", "door"],
    "bonnet":     ["front.top"],
    "boot":       ["back"],
    "bump_front": ["front", "front_grill_down", "front_grill_top", "grail.holder", "grail.inside.1", "front.plate"],
    "bump_rear":  ["Bumper", "back.plate"],
    "windscreen": ["door.001"],
}
SPLIT_BY_SIDE = {"door": ["door.003", "door.window", "FrontBackGlass"], "wing": ["front.side"]}
TYRES = "Tires"
HELPERS = ("HoneyComb",)                     # Boolean operands: consumed by the evaluation, never shipped
OPTIONAL_SOURCE = {"exhaust", "back.side.exhaust"}
# Honeycomb grilles are a Boolean of a 61 k-vertex sheet: ~20 k vertices each, doubled again by the `dam` morph.
# They ship as a PLACEHOLDER PLANE for now - a quad grid covering the evaluated grille, facing forward, same
# material - until a baked alpha-cut honeycomb texture replaces it (VEHICLE_AUTHORING.md, "Grilles").
PLACEHOLDER_PLANES = ("front_grill_down", "front_grill_top")

DAMAGEABLE = ["chassis", "bonnet", "boot", "bump_front", "bump_rear", "door_lf", "door_rf", "door_lr", "door_rr",
              "wing_lf", "wing_rf", "windscreen"]
REQUIRED = ["chassis"]                   # every other damageable part is optional: a pickup has no boot
# Vehicles whose .blend is an artist's AUTHORING layout, split by the tables above. Any other vehicle's .blend is
# already in component form (named parts + seat_* Empties, e.g. the pack cars from import_pack_vehicles.py).
SOURCE_LAYOUT = {"SPC1"}
WHEELS = ["wheel_lf", "wheel_rf", "wheel_lb", "wheel_rb"]
HULL_EXCLUDE = WHEELS + ["windscreen"]

# (outward direction of the part's exposed side, inward push there, noise amplitude) - metres
CRUMPLE = {
    "bump_front": ((0, 1, 0), 0.22, 0.06), "bump_rear": ((0, -1, 0), 0.18, 0.06),
    "bonnet": ((0, 1, 0), 0.16, 0.05),     "boot": ((0, -1, 0), 0.12, 0.05),
    "door_lf": ((-1, 0, 0), 0.12, 0.045),  "door_rf": ((1, 0, 0), 0.12, 0.045),
    "door_lr": ((-1, 0, 0), 0.12, 0.045),  "door_rr": ((1, 0, 0), 0.12, 0.045),
    "wing_lf": ((-1, 0.5, 0), 0.12, 0.05), "wing_rf": ((1, 0.5, 0), 0.12, 0.05),
    "windscreen": ((0, 0, 1), 0.03, 0.015), "chassis": (None, 0.0, 0.04),
}
SEED = Vector((13.7, 5.1, 2.9))


def fail(vid, msg):
    raise SystemExit(f"[build_vehicle] {vid}: {msg}")


def godot(v):
    return [round(v.x, 4), round(v.z, 4), round(-v.y, 4)]


def components(me):
    """Loose parts of a mesh as vertex-index sets."""
    bm = bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()
    seen, out = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, comp = [v], set()
        seen.add(v.index)
        while stack:
            x = stack.pop(); comp.add(x.index)
            for e in x.link_edges:
                y = e.other_vert(x)
                if y.index not in seen:
                    seen.add(y.index); stack.append(y)
        out.append(comp)
    bm.free()
    return out


def cushion_top(ps):
    """Where a seated body's hips go: the highest point of the seat's FRONT half (the cushion, not the backrest),
    at the middle of that half. A seat Empty marks this; the scene hangs the seat marker from it."""
    lo, hi = box(ps)
    front = [p for p in ps if p.y > lo.y + 0.5 * (hi.y - lo.y)]
    return Vector(((lo.x + hi.x) / 2, (lo.y + 0.5 * (hi.y - lo.y) + hi.y) / 2, max(p.z for p in front)))


def box(ps):
    lo = Vector([min(p[k] for p in ps) for k in range(3)])
    hi = Vector([max(p[k] for p in ps) for k in range(3)])
    return lo, hi


def placeholder_plane(name, evaluated):
    """A 6 x 2 quad grid over the evaluated grille's front, facing the grille's front (-Y in the source frame)."""
    lo, hi = box([v.co for v in evaluated.vertices])
    mats = list(evaluated.materials)
    bpy.data.meshes.remove(evaluated)
    me = bpy.data.meshes.new(name)
    nx, nz = 6, 2
    verts = [(lo.x + (hi.x - lo.x) * i / nx, lo.y, lo.z + (hi.z - lo.z) * j / nz)
             for j in range(nz + 1) for i in range(nx + 1)]
    faces = [(j * (nx + 1) + i, j * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i)
             for j in range(nz) for i in range(nx)]
    me.from_pydata(verts, [], faces)
    for m in mats:
        me.materials.append(m)
    me.update()
    return me


def evaluate_all(objs):
    """Bakes every modifier and transform into its mesh and drops stray points; the object keeps its name."""
    dg = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
        me.transform(o.matrix_world)
        o.modifiers.clear()
        o.parent = None
        if o.data.shape_keys:
            o.shape_key_clear()
        o.data = me
        o.matrix_world = Matrix.Identity(4)
        bm = bmesh.new(); bm.from_mesh(me)
        stray = [v for v in bm.verts if not v.link_faces]
        if stray:
            bmesh.ops.delete(bm, geom=stray, context='VERTS')
        bm.to_mesh(me); bm.free()


def components_in_memory(vid):
    """A .blend already in component form: named parts, seat_* Empties, facing +Y on the ground."""
    OBJ = bpy.data.objects
    meshes = [o for o in OBJ if o.type == 'MESH']
    known = set(DAMAGEABLE) | set(WHEELS)
    unknown = sorted(o.name for o in meshes if o.name not in known)
    missing = sorted(n for n in REQUIRED + WHEELS if n not in OBJ)
    if unknown or missing:
        fail(vid, f"component names: missing {missing}, unknown {unknown}. A part is found BY NAME at runtime "
                  f"(VEHICLE_AUTHORING.md lists them); an unknown mesh would ship but never break.")
    seats = {o.name: o.matrix_world.translation.copy() for o in OBJ if o.type == 'EMPTY' and o.name.startswith("seat_")}
    evaluate_all(meshes)
    for o in list(OBJ):
        if o.type != 'MESH':
            bpy.data.objects.remove(o, do_unlink=True)
    return {o.name: o for o in meshes}, seats


def split_in_memory(vid):
    OBJ = bpy.data.objects
    known = {n for g in SOURCE_GROUPS.values() for n in g} | {n for g in SPLIT_BY_SIDE.values() for n in g} | {TYRES}
    meshes = [o for o in OBJ if o.type == 'MESH' and not o.name.startswith(HELPERS) and len(o.data.vertices)]
    unknown = sorted(o.name for o in meshes if o.name not in known)
    missing = sorted(n for n in known if n not in OBJ and n not in OPTIONAL_SOURCE)
    if unknown or missing:
        fail(vid, f"source objects not in the split table: {unknown}; table objects missing from the file: {missing}. "
                  f"Add a new object to SOURCE_GROUPS in blender/tools/build_vehicle.py (which component it "
                  f"belongs to), or rename it back.")

    # 1. evaluate every modifier as authored; everything else goes
    dg = bpy.context.evaluated_depsgraph_get()
    for o in meshes:
        me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
        me.transform(o.matrix_world)
        if o.name in PLACEHOLDER_PLANES:
            me = placeholder_plane(o.name, me)
        o.modifiers.clear()
        o.parent = None
        o.data = me
        o.matrix_world = Matrix.Identity(4)
        bm = bmesh.new(); bm.from_mesh(me)                     # stray points with no face render nothing,
        stray = [v for v in bm.verts if not v.link_faces]       # but they would skew every bound and hinge
        if stray:
            bmesh.ops.delete(bm, geom=stray, context='VERTS')
        bm.to_mesh(me); bm.free()
    keep = {o.name for o in meshes}
    for o in list(OBJ):
        if o.name not in keep:
            bpy.data.objects.remove(o, do_unlink=True)

    # 3. face +Y, origin on the ground at mid-wheelbase (rigid)
    tyres = OBJ[TYRES].data
    ys = [sum(tyres.vertices[i].co.y for i in c) / len(c) for c in components(tyres)]
    axles = [[y for y in ys if y < 0], [y for y in ys if y >= 0]]
    if not all(axles):
        fail(vid, f"expected two axles in {TYRES!r}, found wheel parts at y = {[round(y, 2) for y in ys]}")
    ground = min(v.co.z for v in tyres.vertices)
    mid_y = sum(sum(a) / len(a) for a in axles) / 2
    faces_minus_y = min(v.co.y for v in OBJ["front"].data.vertices) < mid_y
    turn = Matrix.Rotation(math.pi, 4, 'Z') if faces_minus_y else Matrix.Identity(4)
    M = Matrix.Translation((0.0, mid_y if faces_minus_y else -mid_y, -ground)) @ turn
    for o in OBJ:
        o.data.transform(M)

    # 6. only what glTF cannot carry
    for m in bpy.data.materials:
        nodes = m.node_tree.nodes if m.node_tree else []
        if any(n.type == 'BSDF_TRANSLUCENT' for n in nodes) and not any(n.type == 'BSDF_PRINCIPLED' for n in nodes):
            col = tuple(next(n for n in nodes if n.type == 'BSDF_TRANSLUCENT').inputs['Color'].default_value)   # copy: clear() frees the node
            nodes.clear()
            out = nodes.new('ShaderNodeOutputMaterial'); out.target = 'ALL'
            p = nodes.new('ShaderNodeBsdfPrincipled')
            p.inputs['Base Color'].default_value = (col[0] * 0.3, col[1] * 0.3, col[2] * 0.35, 1)
            p.inputs['Roughness'].default_value = 0.05
            p.inputs['Alpha'].default_value = 0.4
            m.node_tree.links.new(p.outputs['BSDF'], out.inputs['Surface'])
            m.surface_render_method = 'BLENDED'

    # 2. split by side / corner, then join into components
    def split(name, key_of):
        src = OBJ[name]
        groups = {}
        for comp in components(src.data):
            c = sum((src.data.vertices[i].co for i in comp), Vector()) / len(comp)
            groups.setdefault(key_of(c), set()).update(comp)
        out = {}
        for key, idx in groups.items():
            me = src.data.copy()
            bm = bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.index not in idx], context='VERTS')
            bm.to_mesh(me); bm.free()
            o = bpy.data.objects.new(f"{name}__{key}", me)
            bpy.context.scene.collection.objects.link(o)
            out[key] = o
        bpy.data.objects.remove(src, do_unlink=True)
        return out

    side = lambda c: "l" if c.x < 0 else "r"                      # facing +Y, left is -X
    groups = {k: [n for n in v if n in OBJ] for k, v in SOURCE_GROUPS.items()}
    for kind, names in SPLIT_BY_SIDE.items():
        parts = [split(n, side) for n in names]
        for s in "lr":
            groups[f"{kind}_{s}f"] = [p[s].name for p in parts if s in p]
    for k, o in split(TYRES, lambda c: side(c) + ("f" if c.y > 0 else "b")).items():
        groups[f"wheel_{k}"] = [o.name]

    col = bpy.data.collections.new(vid)
    bpy.context.scene.collection.children.link(col)
    parts = {}
    for part, names in groups.items():
        objs = [OBJ[n] for n in names]
        if not objs:
            fail(vid, f"component {part} came out empty")
        with bpy.context.temp_override(active_object=objs[0], selected_editable_objects=objs, selected_objects=objs):
            bpy.ops.object.join()
        o = objs[0]
        o.name = part; o.data.name = part
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)
        parts[part] = o

    parts = finish(vid, parts)
    # seats: the two tall interior blocks are the front seats; a seat marker sits at the cushion's base
    chassis = parts["chassis"]
    seats = {}
    for comp in components(chassis.data):
        ps = [chassis.data.vertices[i].co for i in comp]
        lo, hi = box(ps)
        cx = (lo.x + hi.x) / 2
        if (hi.z - lo.z) > 0.7 and (hi.y - lo.y) < 0.9 and 0.1 < abs(cx) < 0.6 and lo.z < 0.5:
            seats["seat_front_" + ("l" if cx < 0 else "r")] = cushion_top(ps)
        elif (hi.z - lo.z) > 0.7 and lo.x < -0.3 < 0.3 < hi.x and hi.y < -0.2 and lo.z < 0.5:
            bench = cushion_top(ps)                                # the rear bench, two seats across it
            for side, x in (("l", -0.35), ("r", 0.35)):
                seats["seat_rear_" + side] = Vector((x, bench.y, bench.z))
    if not {"seat_front_l", "seat_front_r"} <= set(seats):
        fail(vid, f"could not find the two front seat blocks in the interior (found {sorted(seats)})")
    return parts, seats


def finish(vid, parts):
    # 4. origins on hinges
    def paint_box(o):
        paint = {i for i, m in enumerate(o.data.materials)
                 if m and not any(w in m.name.lower() for w in ("glass", "window", "interior", "trim", "rubber"))}
        idx = {i for p in o.data.polygons if p.material_index in paint for i in p.vertices} or range(len(o.data.vertices))
        return box([o.data.vertices[i].co for i in idx])

    def top_near(o, axis, value, band=0.05):
        return max(v.co.z for v in o.data.vertices if abs(v.co[axis] - value) < band)

    for name, o in parts.items():
        lo, hi = box([v.co for v in o.data.vertices])
        mid = (lo + hi) / 2
        if name.startswith("door_"):
            lo, hi = paint_box(o)                                      # the skin, not the mirror on it
            p = Vector((lo.x + 0.03 if name[5] == "l" else hi.x - 0.03, hi.y - 0.03, (lo.z + hi.z) / 2))
        elif name == "bonnet":
            p = Vector((0.0, lo.y, top_near(o, 1, lo.y)))
        elif name == "boot":
            p = Vector((0.0, hi.y, top_near(o, 1, hi.y)))
        elif name == "bump_front":
            p = Vector((hi.x - 0.08, mid.y, hi.z - 0.05))
        elif name == "bump_rear":
            p = Vector((lo.x + 0.08, mid.y, hi.z - 0.05))
        elif name == "chassis":
            p = Vector()
        else:
            p = mid
        o.data.transform(Matrix.Translation(-p))
        o.location = p
    bpy.context.view_layer.update()                             # matrix_world follows the new locations

    # 5. the crumpled shape, a separate key at value 0
    for name, (out, push, amp) in CRUMPLE.items():
        o = parts.get(name)
        if o is None:
            continue
        o.shape_key_add(name="Basis", from_mix=False)
        key = o.shape_key_add(name="dam", from_mix=False)
        world = [o.location + v.co for v in o.data.vertices]
        d = Vector(out).normalized() if out else None
        if d:
            s = [p.dot(d) for p in world]; s0, s1 = min(s), max(s)
        ymin = min(p.y for p in world)
        for i, p in enumerate(world):
            w = ((s[i] - s0) / max(s1 - s0, 1e-6)) ** 2 if d else 0.5
            q = p * 2.5 + SEED                                    # one field in car space: touching parts agree
            disp = (noise.noise_vector(q) + noise.noise_vector(q * 2.3) * 0.5) * amp * (0.35 + 0.65 * w)
            if d:
                disp -= d * push * w
            if name == "bonnet":                                   # a crushed bonnet buckles up
                disp.z += 0.14 * math.sin(math.pi * min(max((p.y - ymin) / 1.2, 0.0), 1.0)) * w
            if name == "chassis":                                  # the roof caves in
                disp.z -= 0.09 * min(max((p.z - 1.1) / 0.3, 0.0), 1.0)
            key.data[i].co = o.data.vertices[i].co + disp
        key.value = 0.0                                            # shape_key_add leaves a new key at 1.0
        o.active_shape_key_index = 0

    return parts


def build(vid):
    src = os.path.join(DIR, vid + ".blend")
    bpy.ops.wm.open_mainfile(filepath=src)
    if vid in SOURCE_LAYOUT:
        parts, seats = split_in_memory(vid)
    else:
        parts, seats = components_in_memory(vid)
        parts = finish(vid, parts)

    world = lambda o: [o.matrix_world @ v.co for v in o.data.vertices]
    lo, hi = box([p for o in parts.values() for p in world(o)])
    wheels = {}
    for n in WHEELS:
        a, b = box(world(parts[n]))
        wheels[n] = {"centre": godot((a + b) / 2), "radius": round((b.z - a.z) / 2, 4)}

    bm = bmesh.new()
    for n, o in parts.items():
        if n not in HULL_EXCLUDE:
            for p in world(o):
                bm.verts.new(p)
    bmesh.ops.convex_hull(bm, input=list(bm.verts))
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(18), verts=list(bm.verts), edges=list(bm.edges))
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    hull = [godot(v.co) for v in bm.verts]
    bm.free()

    if SAVE_PARTS:
        if os.path.abspath(SAVE_PARTS) == os.path.abspath(src):
            fail(vid, "--save-parts must not be the source file")
        bpy.ops.wm.save_as_mainfile(filepath=SAVE_PARTS, copy=True)

    out = os.path.join(DIR, vid + ".glb")
    bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', export_yup=True, export_apply=False,
                              export_morph=True, export_morph_normal=True, export_animations=False,
                              export_cameras=False, export_lights=False)
    data = open(out, "rb").read()
    gltf = json.loads(data[20:20 + struct.unpack("<I", data[12:16])[0]])
    # a material glTF cannot read exports with no pbr block at all (a Translucent/Diffuse/Glass BSDF):
    # Godot then draws it opaque white. (A MISSING baseColorFactor alone is fine - it means white.)
    blank = [m.get("name", "?") for m in gltf.get("materials", [])
             if "pbrMetallicRoughness" not in m and "emissiveFactor" not in m]
    if blank:
        fail(vid, f"material(s) {blank} use a shader glTF cannot carry (white in Godot): use a Principled BSDF.")
    no_morph = [m.get("name") for m in gltf["meshes"]
                if m.get("name") in DAMAGEABLE and not any(pr.get("targets") for pr in m["primitives"])]
    if no_morph:
        fail(vid, f"{no_morph} exported without their `dam` morph target.")
    on = [m.get("name") for m in gltf["meshes"] if any(w != 0 for w in m.get("weights", []))]
    if on:
        fail(vid, f"{on} export with the `dam` key switched on - the model would load crumpled.")

    facts = {
        "id": vid,
        "note": f"MEASURED by blender/tools/build_vehicle.py from assets/vehicles/{vid}.blend - Godot axes. Do not edit.",
        "bounds": {"min": godot(Vector((lo.x, hi.y, lo.z))), "max": godot(Vector((hi.x, lo.y, hi.z)))},
        "wheels": wheels,
        "seats": {n: godot(p) for n, p in sorted(seats.items())},
        "pivots": {n: godot(parts[n].location) for n in DAMAGEABLE if n in parts},
        "hull": hull,
    }
    with open(os.path.join(DIR, vid + ".vehicle.json"), "w") as f:
        json.dump(facts, f, indent=1)
    print(f"[build_vehicle] {vid}: {hi.y - lo.y:.3f} x {hi.x - lo.x:.3f} x {hi.z:.3f} m, "
          f"wheel r {wheels['wheel_lf']['radius']:.3f}, {sum(len(o.data.vertices) for o in parts.values())} verts, "
          f"hull {len(hull)} points, wrote {os.path.basename(out)} ({os.path.getsize(out)} bytes)")


for vid in ids or ["SPC1"]:
    build(vid)
