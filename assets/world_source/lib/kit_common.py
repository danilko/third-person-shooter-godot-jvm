#!/usr/bin/env python3
"""
kit_common.py — shared Blender helpers for the modular town kit.

Used by every kit/ builder and towns/ assembler. Holds: unit setup, collection
helpers, the material set, low-poly mesh primitives (box/cyl/gable/combine/cut),
the `-colonly` collision-proxy helper, glTF export, and the Geometry-Nodes
instancing core (GN_Instance group + instancer/place_side).

CONVENTIONS (locked — see README / BLENDER_CONVENTIONS.md):
  * 1 Blender unit = 1 m. Blender Z up; Godot importer flips to Y up (don't pre-rotate).
  * Forward face authored on +Y (imports to Godot +Z = forward).
  * PIVOTS by asset class:
      - walls / fences / facade modules .. ENDPOINT: origin at base START corner
        (x=0 end), front face +Y, length runs +X, base z=0.   (easy abutting)
      - floor / ceiling slab ............. TOP corner (top face on storey datum).
      - road / grid tiles ................ footprint CENTRE at ground (z=0)
        (90deg rotation snaps; tiles abut on grid lines).
      - standalone props ................. bottom CENTRE of footprint, base z=0.
  * Collision: each leaf gets a sibling box proxy `<Name>-colonly` (visual removed
    on import -> Godot CollisionShape3D). Authored by colonly().
  * Road grid = 7 m cell, 3.5 m lane. Zone cell = 56 m.
"""
import bpy
import bmesh
import math
import os
from mathutils import Matrix

# ---------------------------------------------------------------- dimensions
T      = 0.20      # wall thickness
R_BAY  = 2.0       # residential bay width
R_H    = 3.0       # residential floor-to-floor
K_H    = 3.6       # konbini wall height
SLAB   = 0.30      # floor/ceiling slab thickness
CELL   = 7.0       # road grid cell (matches game Road2LaneStraight 7 m)
LANE   = 3.5       # single lane width
ZONE   = 56.0      # streaming zone cell (= 8 road tiles = 14 wall runs)


# ----------------------------------------------------------------- scene/units
def reset_scene(coll_names):
    """Wipe objects in the given collections, then purge orphan meshes."""
    for cn in coll_names:
        coll = bpy.data.collections.get(cn)
        if coll:
            for obj in list(coll.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.collections.remove(coll)
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)


# Default far clip baked into every generated .blend (viewports + script-made cameras): the
# 3 km world vanishes past Blender's 1 km viewport default the moment you zoom out to frame it.
VIEW_CLIP_END = 100000.0


def setup_view_clip(end=VIEW_CLIP_END):
    """Set the far clip on every 3D viewport of every screen/workspace stored in the file, so
    the saved .blend opens showing the whole world. Works headless too — bpy.data.screens is
    the file's saved UI data, no window needed."""
    for scr in bpy.data.screens:
        for area in scr.areas:
            if area.type == 'VIEW_3D':
                for sp in area.spaces:
                    if sp.type == 'VIEW_3D':
                        sp.clip_end = end


def setup_units():
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.scale_length = 1.0
    sc.unit_settings.length_unit = 'METERS'
    setup_view_clip()


def get_coll(name):
    # local-only lookup: with neighbour districts library-linked in (tools/link_neighbors.py),
    # several libraries can each contribute a same-named collection (e.g. STREET) — a bare
    # bpy.data.collections.get() may return a read-only linked one instead of ours.
    coll = next((c for c in bpy.data.collections
                 if c.name == name and c.library is None), None)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def link_collections(abspath, names):
    """TRUE library-link (link=True) the named collections from `abspath` in ONE library load;
    returns those found. Linked data is a live, read-only reference to the source .blend —
    edit + save the source, reload the linking file, the edit is there; nothing is copied and
    the linking file can never corrupt the source. Shared mechanism of tools/link_world.py,
    tools/link_neighbors.py and the master's linked-district layer (towns/build_world.py)."""
    with bpy.data.libraries.load(abspath, link=True) as (src, dst):
        dst.collections = [c for c in src.collections if c in names]
    return [c for c in dst.collections if c is not None]


def instance_collection(dest, name, coll, loc):
    """Collection-Instance empty placing (linked) collection `coll` at world `loc`."""
    inst = bpy.data.objects.new(name, None)
    inst.instance_type = 'COLLECTION'
    inst.instance_collection = coll
    inst.location = loc
    dest.objects.link(inst)
    return inst


# ----------------------------------------------------------------- materials
MATS = {
    "concrete": ("M_Concrete", (0.82, 0.80, 0.76, 1)),
    "trim":     ("M_Trim",     (0.74, 0.69, 0.58, 1)),
    "glass":    ("M_Glass",    (0.55, 0.78, 0.85, 1)),
    "metal":    ("M_Metal",    (0.55, 0.60, 0.64, 1)),
    "accent":   ("M_Accent",   (0.18, 0.42, 0.87, 1)),
    "asphalt":  ("M_Asphalt",  (0.28, 0.30, 0.33, 1)),
    "roof":     ("M_RoofTile", (0.32, 0.36, 0.42, 1)),
    "wood":     ("M_Wood",     (0.45, 0.30, 0.18, 1)),
    "leaf":     ("M_Leaf",     (0.28, 0.42, 0.22, 1)),
    "red":      ("M_Red",      (0.72, 0.16, 0.13, 1)),
    "line_y":   ("M_LineY",    (0.86, 0.74, 0.20, 1)),   # yellow lane line
    "line_w":   ("M_LineW",    (0.90, 0.90, 0.90, 1)),   # white lane line
    "dirt":     ("M_Dirt",     (0.40, 0.34, 0.26, 1)),   # ground fill
    "rail":     ("M_Rail",     (0.40, 0.40, 0.44, 1)),   # rail steel
    "col":      ("M_Collision", (0.90, 0.20, 0.55, 0.25)),  # debug proxy tint
    # --- Tokyo urban set ---
    "neon":        ("M_Neon",        (0.95, 0.25, 0.55, 1)),   # emissive pink neon
    "screen":      ("M_Screen",      (0.45, 0.70, 1.00, 1)),   # emissive media facade
    "brick":       ("M_Brick",       (0.50, 0.22, 0.16, 1)),   # red-brick viaduct
    "glasscurtain":("M_GlassCurtain", (0.42, 0.58, 0.70, 1)),  # tinted curtain wall
    "steel":       ("M_Steel",       (0.58, 0.60, 0.64, 1)),   # train / structure steel
    "shink":       ("M_Shink",       (0.92, 0.93, 0.96, 1)),   # shinkansen white body
}

# emissive keys -> emission strength
EMISSIVE = {"M_Neon": 5.0, "M_Screen": 3.5}


def get_mat(name, rgba):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = rgba
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = rgba
            if name == "M_Glass":
                bsdf.inputs["Roughness"].default_value = 0.05
                if "Transmission Weight" in bsdf.inputs:
                    bsdf.inputs["Transmission Weight"].default_value = 0.9
            elif name == "M_GlassCurtain":
                bsdf.inputs["Roughness"].default_value = 0.08
                if "Metallic" in bsdf.inputs:
                    bsdf.inputs["Metallic"].default_value = 0.5
            elif name in EMISSIVE:
                if "Emission Color" in bsdf.inputs:
                    bsdf.inputs["Emission Color"].default_value = rgba
                if "Emission Strength" in bsdf.inputs:
                    bsdf.inputs["Emission Strength"].default_value = EMISSIVE[name]
    return mat


def mat(key):
    n, c = MATS[key]
    return get_mat(n, c)


def _new_obj(name, me, coll, matkey):
    obj = bpy.data.objects.new(name, me)
    coll.objects.link(obj)
    if matkey:
        obj.data.materials.append(mat(matkey))
    return obj


# ----------------------------------------------------------------- primitives
def recalc_normals(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()


def box(name, x0, x1, y0, y1, z0, z1, coll, matkey=None):
    """Axis-aligned box. Object origin stays at world (0,0,0); the LOCAL pivot is
    wherever (0,0,0) falls relative to the verts you pass."""
    verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    faces = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1),
             (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    recalc_normals(me)
    return _new_obj(name, me, coll, matkey)


def cyl(name, radius, z0, z1, coll, matkey=None, seg=16):
    """Vertical cylinder, base centre at local (0,0,z0)."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg,
                          radius1=radius, radius2=radius, depth=(z1 - z0))
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, (z0 + z1) / 2.0))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    recalc_normals(me)
    return _new_obj(name, me, coll, matkey)


def gable(name, w, d, peak, coll, matkey="roof", eave=0.3):
    """Pitched gable roof prism. Ridge runs along X; eaves overhang by `eave`."""
    x0, x1 = -eave, w + eave
    y0, y1 = -eave, d + eave
    ym = d / 2.0
    verts = [(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0),
             (x0, ym, peak), (x1, ym, peak)]
    faces = [(0, 1, 5, 4), (4, 5, 2, 3), (0, 4, 3), (1, 2, 5)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    recalc_normals(me)
    return _new_obj(name, me, coll, matkey)


def combine(name, parts, coll):
    """One mesh from several boxes, each with its own material.
       parts = [((x0,x1,y0,y1,z0,z1), matkey), ...]"""
    bm = bmesh.new()
    mats, midx = [], {}
    for (x0, x1, y0, y1, z0, z1), mk in parts:
        if mk not in midx:
            midx[mk] = len(mats); mats.append(mk)
        ret = bmesh.ops.create_cube(bm, size=1.0)
        vs = ret["verts"]
        bmesh.ops.scale(bm, vec=(x1-x0, y1-y0, z1-z0), verts=vs)
        bmesh.ops.translate(bm, vec=((x0+x1)/2, (y0+y1)/2, (z0+z1)/2), verts=vs)
        for f in {f for v in vs for f in v.link_faces}:
            f.material_index = midx[mk]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new(name, me)
    coll.objects.link(obj)
    for mk in mats:
        obj.data.materials.append(mat(mk))
    return obj


def wedge(name, parts, coll):
    """One mesh from sloped slabs (a ramp deck). Each part:
       ((x0,x1, y0,y1, z_y0, z_y1, thick), matkey)
    builds a slab of vertical thickness `thick` whose TOP runs from z_y0 (at y0) to
    z_y1 (at y1) — the rise is along +Y. Same box topology, just y-dependent z."""
    bm = bmesh.new(); mats, midx = [], {}
    for (x0, x1, y0, y1, za, zb, th), mk in parts:
        if mk not in midx:
            midx[mk] = len(mats); mats.append(mk)
        vs = [bm.verts.new(p) for p in [
            (x0, y0, za-th), (x1, y0, za-th), (x1, y1, zb-th), (x0, y1, zb-th),
            (x0, y0, za),    (x1, y0, za),    (x1, y1, zb),    (x0, y1, zb)]]
        for fi in [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1),
                   (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]:
            bm.faces.new([vs[i] for i in fi]).material_index = midx[mk]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new(name, me)
    coll.objects.link(obj)
    for mk in mats:
        obj.data.materials.append(mat(mk))
    return obj


def cut(target, x0, x1, y0, y1, z0, z1):
    """Boolean-difference a box opening out of `target` (applies + cleans up)."""
    cutter = box("__cutter", x0, x1, y0, y1, z0, z1, get_coll("__tmp"))
    m = target.modifiers.new("cut", 'BOOLEAN')
    m.operation = 'DIFFERENCE'
    m.object = cutter
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    tmp = bpy.data.collections.get("__tmp")
    if tmp and not tmp.objects:
        bpy.data.collections.remove(tmp)


# ----------------------------------------------------- collision proxy / export
def colonly(visual, coll=None, inset=0.0):
    """Author a `<Name>-colonly` box proxy spanning the visual's local bounds.
    On Godot import the visual is dropped and the box becomes a CollisionShape3D."""
    bb = [v[:] for v in visual.bound_box]      # 8 local corners
    xs = [p[0] for p in bb]; ys = [p[1] for p in bb]; zs = [p[2] for p in bb]
    x0, x1 = min(xs)+inset, max(xs)-inset
    y0, y1 = min(ys)+inset, max(ys)-inset
    z0, z1 = min(zs), max(zs)
    c = coll or (visual.users_collection[0] if visual.users_collection else get_coll("ENV"))
    p = box(visual.name + "-colonly", x0, x1, y0, y1, z0, z1, c, "col")
    p["proxy_for"] = visual.name
    return p


def colonly_mesh(visual, coll=None):
    """Author a `<Name>-colonly` proxy that COPIES the visual's own mesh geometry instead of its
    bounding box. Same Godot import contract as colonly() (the `-colonly` suffix drops the visual
    half on import and builds a CollisionShape3D from this mesh) -- but for an irregular real-world
    footprint (a PLATEAU building/bridge) a box proxy blocks empty space the visual never occupied
    (an L-shaped or angled building reads as a solid rectangle to collision), which shows up as an
    invisible wall in an area that looks walkable. Use this instead of colonly() wherever the
    visual mesh is already low-poly enough to serve directly as its own (concave) collider -- real
    PLATEAU buildings/bridges/landmarks, not modular kit pieces (those keep the box proxy).
    Deliberately NOT a convex-hull option: a bridge or archway's real open span under/through it
    would become solid under a convex hull (found on Rainbow Bridge during walk-testing), which is
    worse than the box proxy this replaces -- concave is the only shape that keeps real holes."""
    c = coll or (visual.users_collection[0] if visual.users_collection else get_coll("ENV"))
    me = visual.data.copy()
    p = bpy.data.objects.new(visual.name + "-colonly", me)
    c.objects.link(p)
    p.data.materials.clear()
    p.data.materials.append(mat("col"))
    p["proxy_for"] = visual.name
    return p


def colonly_mesh_evaluated(visual, coll=None, name=None):
    """Like `colonly_mesh()`, but for a GN-modifier-backed object (a Curve with a live Nodes
    modifier -- `junction_pad`/`road_spine`/`curb_loop`, all of the road_kit_authoring visual
    pieces) whose OWN `.data` is unevaluated source data (raw curve control points), not the real
    swept/filled/filleted mesh a viewer actually sees -- `colonly_mesh()`'s plain `visual.data.
    copy()` would copy the WRONG (pre-modifier) geometry for these. Evaluates the object through
    the depsgraph first (`bpy.data.meshes.new_from_object`, the same bake glTF export itself
    performs) so the collision proxy is an EXACT copy of the real, on-screen shape -- corner
    fillets, tapers, bends, all of it -- with zero hand-rolled approximation math to keep in sync.

    2026-07-27, user-reported/screenshotted (twice): road_kit_authoring's hand-rolled collision
    helpers (`colonly_polygon`'s corner-squared-off boundary ignoring fillet radius,
    `colonly_swept`'s per-vertex sweep) visibly diverged from the real curved/filleted visual mesh
    at corners -- a real, structural coarseness problem, not a one-off bug, and NOT what
    `colonly_mesh()` already does correctly for real-world (PLATEAU building/landmark) geometry.
    This closes that gap the same way: don't approximate, copy the truth. Replaces `colonly_polygon`
    (pad) and `colonly_swept`/`colonly_swept_between` (curb walls, pavement) as the road-piece
    collision source; `colonly_swept`'s own point-list-driven signature stays available for the few
    truly synthetic uses that were never GN-Curve objects to begin with (none as of this writing --
    kept for API stability, not because anything still calls it for road pieces).

    `name` overrides the proxy's own base name (default `visual.name`) -- needed for the pavement
    case specifically: the pavement collision proxy is built from `spine_<piece>` (the spine object
    itself is never deleted/recreated by any rebuild, per `rebuild_segment_gn_in_place`'s own
    docstring), but `clear_generated_mesh_objects`'s cleanup sweep matches a `pave_` prefix, not
    `spine_` -- passing `name="pave_<piece>"` keeps that convention (and the existing cleanup code)
    working unchanged; without it, a fresh `pave_`-less orphan would pile up on every rebuild."""
    c = coll or (visual.users_collection[0] if visual.users_collection else get_coll("ENV"))
    base = name or visual.name
    deps = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(visual.evaluated_get(deps))
    p = bpy.data.objects.new(base + "-colonly", me)
    p.matrix_world = visual.matrix_world
    c.objects.link(p)
    p.data.materials.clear()
    p.data.materials.append(mat("col"))
    p["proxy_for"] = base
    return p


# ------------------------------------------------------------- lane centerlines
def centerlines_from_vertex_group(obj, group_name="lanedata"):
    """Extract ordered, directional lane polylines from `group_name` on mesh `obj`. Reused by the
    interactive `RKA_OT_centerline_from_vertex_group` operator (road_kit_authoring addon) so kit
    pieces get their lane data from hand-tagged mesh topology instead of a guessed bbox midline.

    Each edge-connected component of tagged vertices is treated as ONE lane -- this is what lets
    a single 'lanedata' group carry several distinct lane paths in one mesh (e.g. every turn
    movement through an intersection piece), disambiguated purely by mesh connectivity, no extra
    grouping convention needed. A component must be a simple path (both ends degree <=1) or a
    closed loop (every vertex degree 2); anything branchier is a tagging mistake, not a lane.

    Direction: a non-loop lane's point order (index 0 = tail, index -1 = head) follows the tagged
    verts' GROUP WEIGHT when the two path endpoints differ (lower weight = tail) -- tag weight 0.0
    at a lane's start and 1.0 at its end (Blender's Vertex Weights panel) to make direction
    explicit. This is what lets ONE lane-tile mesh serve both directions of a 2-way street: place
    it normally for one direction, rotate it 180 degrees for the other -- the weight travels with
    the vertex data, so which physical end is "head" survives the rotation even though the
    topological walk alone (arbitrary tie-break) would not. Equal/default weights (e.g. both ends
    at the vertex-group default of 1.0) fall back to the topological walk order -- no behavior
    change for data tagged before this convention existed.

    Returns (lanes, warnings): `lanes` is a list of {"points": [world-space Vector, ...],
    "loop": bool}; `warnings` is a list of human-readable strings (isolated tagged verts with no
    edge partner -- skipped, not an error, since a piece may be tagged incrementally)."""
    vg = obj.vertex_groups.get(group_name)
    if vg is None:
        return [], []
    gi = vg.index
    me = obj.data
    tagged = {}
    for v in me.vertices:
        for g in v.groups:
            if g.group == gi:
                tagged[v.index] = g.weight
    if not tagged:
        return [], []

    adjacency = {vi: set() for vi in tagged}
    for e in me.edges:
        a, b = e.vertices[0], e.vertices[1]
        if a in tagged and b in tagged:
            adjacency[a].add(b)
            adjacency[b].add(a)

    mw = obj.matrix_world
    lanes, warnings = [], []
    visited = set()
    for start in sorted(tagged):
        if start in visited:
            continue
        component, stack = set(), [start]
        while stack:
            v = stack.pop()
            if v in component:
                continue
            component.add(v)
            stack.extend(adjacency[v] - component)
        visited |= component

        if len(component) == 1:
            warnings.append("%s: isolated tagged vertex %d has no edge partner -- skipped"
                             % (obj.name, start))
            continue

        degrees = {v: len(adjacency[v]) for v in component}
        branchy = [v for v, d in degrees.items() if d > 2]
        if branchy:
            raise ValueError(
                "%s: vertex %d in '%s' has %d tagged neighbours -- a lane centerline must be a "
                "simple path or loop, not a branch" % (obj.name, branchy[0], group_name, degrees[branchy[0]]))

        endpoints = [v for v, d in degrees.items() if d <= 1]
        is_loop = not endpoints
        start_v = endpoints[0] if endpoints else next(iter(component))

        ordered = [start_v]
        prev, cur = None, start_v
        while True:
            nxt = [n for n in adjacency[cur] if n != prev]
            if not nxt or nxt[0] == ordered[0]:
                break
            cur, prev = nxt[0], cur
            ordered.append(cur)

        if not is_loop and tagged[ordered[0]] > tagged[ordered[-1]]:
            ordered.reverse()

        lanes.append({"points": [mw @ me.vertices[vi].co for vi in ordered], "loop": is_loop})
    return lanes, warnings


def lane_marking_strip(name, x_center, y0, y1, z, width, matkey, coll):
    """Thin flat lane-boundary marking, centered on local `x_center`, spanning `y0..y1`, sitting
    on the road surface at height `z`. `matkey` is 'line_w' (same-direction divider) or 'line_y'
    (opposite-direction divider) from `MATS`. Used by `RKA_OT_combine_lanes` to mark the seam
    between two adjacent lane tiles -- kept as its own small object (not joined into the lane
    mesh) so it can later be swapped for a dashed/textured decal without touching lane geometry."""
    return box(name, x_center - width / 2.0, x_center + width / 2.0, y0, y1, z, z + 0.01, coll, matkey)


def poly_curve(name, pts, coll, loop=False, lane_width=None, oneway=True, end_behavior='CHAIN'):
    """A plain POLY-spline Curve object through pts=[(x,y,z), ...] EXACTLY (no NURBS smoothing/
    approximation -- every point is a real control point on a straight-segment spline). Same
    `lanecl_*`-shape object `RKA_OT_centerline_from_vertex_group` builds by hand from tagged mesh
    topology (see ops_centerline.py) -- this is the computed-geometry counterpart, used by
    `RKA_OT_build_intersection` for corner/turn centerlines generated from `lib/intersection_kit.py`.
    Sets `curve.rka_curve` (lane_width/oneway/loop/end_behavior) when `lane_width` is given."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for i, (x, y, z) in enumerate(pts):
        sp.points[i].co = (x, y, z, 1.0)
    sp.use_cyclic_u = loop
    if lane_width is not None:
        cu.rka_curve.lane_width = lane_width
        cu.rka_curve.oneway = oneway
        cu.rka_curve.loop = loop
        cu.rka_curve.end_behavior = end_behavior
    obj = bpy.data.objects.new(name, cu)
    coll.objects.link(obj)
    return obj


def flat_ribbon(name, pts, half_width, coll, matkey="asphalt"):
    """A flat, constant-`half_width` quad-strip mesh following the 3D polyline pts=[(x,y,z), ...]
    EXACTLY (same tangent-offset technique as `swept_wall`, just horizontal instead of vertical) --
    the visual driving surface under a computed lane centerline (see `poly_curve` /
    `lib/intersection_kit.py`), so a generated turn reads as an actual road, not a bare line."""
    n = len(pts)
    if n < 2:
        return None
    verts, faces = [], []
    for i, (x, y, z) in enumerate(pts):
        a = pts[max(0, i - 1)]
        b = pts[min(n - 1, i + 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        L = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / L * half_width, tx / L * half_width
        verts += [(x - nx, y - ny, z), (x + nx, y + ny, z)]
    for i in range(n - 1):
        a, b = i * 2, (i + 1) * 2
        faces.append((a, a + 1, b + 1, b))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    recalc_normals(me)
    obj = bpy.data.objects.new(name, me)
    coll.objects.link(obj)
    obj.data.materials.append(mat(matkey))
    return obj


def marking_ribbon(name, pts, half_width, coll, matkey, dash_len=0.0, gap_len=0.0,
                    exclude_ranges=None, z_lift=0.01):
    """Flat marking strip following `pts` EXACTLY (same tangent-offset quad-strip technique as
    `flat_ribbon`), lifted `z_lift` (default 0.01m) above the pavement it rides on -- otherwise
    the marking is exactly coplanar with the road surface (both sample the same spine Z) and
    z-fights with it in render (2026-07-28, user-requested). Optionally DASHED (both `dash_len`
    and `gap_len` > 0; either <= 0 means solid -- one continuous strip) and/or with
    `exclude_ranges` ([(t0, t1), ...], t = normalized cumulative arc length along `pts`, 0 at
    pts[0] / 1 at pts[-1]) fully OMITTED -- the
    'survive a live-edit rebuild' answer to clearing a marking across a driveway/merge zone:
    `exclude_ranges` is meant to be read back from the owning segment's `rka_marking_gaps`
    custom property on every rebuild, never from hand-deleting a generated object (which the
    addon's delete-and-rebuild-from-scratch cleanup would silently recreate on the next drag).

    Deliberately does NOT resample `pts` at a fixed spacing (an earlier version called
    `sample_polyline(pts, 0.25)` unconditionally, which put a vertex every 25 cm regardless of the
    road spine's own control-point density -- a 40 m straight two-point segment's SOLID yellow
    line got ~160 quads for what needs exactly one, since `road_spine`/`_spine_control_points`
    already establish that the pavement itself is straight between consecutive control points, no
    resolution subdivision -- see their docstrings). Instead this walks `pts` at ITS OWN
    resolution and inserts extra vertices ONLY exactly where something actually changes: a dash
    on/off transition, or an exclude-range boundary -- so a solid, ungapped marking on a 2-point
    straight spine is exactly 2 vertices/1 quad, matching the pavement's own resolution, while a
    dashed one only gets the handful of extra vertices its dash cycle actually needs, placed at
    the exact transition arc-length (not snapped to a sampling grid). Returns None if every
    sub-run ends up skipped (e.g. a gap spanning the whole line)."""
    exclude_ranges = exclude_ranges or []
    n = len(pts)
    if n < 2:
        return None
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    total_len = cum[-1]
    if total_len < 1e-6:
        return None
    dashed = dash_len > 0.0 and gap_len > 0.0
    cycle = dash_len + gap_len

    # Breakpoints: every ORIGINAL point's own arc length (the spine's own resolution) plus every
    # dash on/off transition and exclude-range boundary that actually falls on this line --
    # inserted exactly where needed instead of marching a fixed step across the whole length.
    breaks = set(cum)
    if dashed:
        k = 0
        while k * cycle < total_len:
            on_end = k * cycle + dash_len
            if 0.0 < on_end < total_len:
                breaks.add(on_end)
            off_end = (k + 1) * cycle
            if 0.0 < off_end < total_len:
                breaks.add(off_end)
            k += 1
    for t0, t1 in exclude_ranges:
        a, b = t0 * total_len, t1 * total_len
        if 0.0 < a < total_len:
            breaks.add(a)
        if 0.0 < b < total_len:
            breaks.add(b)
    positions = sorted(breaks)

    def point_at(s):
        """(x, y, z), heading_rad at arc length `s` along the ORIGINAL `pts` (linear
        interpolation within whichever original segment contains it -- never off the spine's own
        straight chords)."""
        s = max(0.0, min(total_len, s))
        i = 1
        while i < n - 1 and cum[i] < s:
            i += 1
        a, b = pts[i - 1], pts[i]
        seg_len = cum[i] - cum[i - 1]
        t = 0.0 if seg_len < 1e-9 else (s - cum[i - 1]) / seg_len
        pos = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)
        return pos, math.atan2(b[1] - a[1], b[0] - a[0])

    def excluded(t):
        return any(t0 <= t <= t1 for (t0, t1) in exclude_ranges)

    verts, faces = [], []
    run = []   # arc-length positions of a contiguous "on" run, flushed into a quad-strip

    def flush():
        if len(run) < 2:
            run.clear()
            return
        base = len(verts)
        for s in run:
            (x, y, z), hd = point_at(s)
            nx, ny = -math.sin(hd) * half_width, math.cos(hd) * half_width
            z += z_lift
            verts.extend([(x - nx, y - ny, z), (x + nx, y + ny, z)])
        for i in range(len(run) - 1):
            a, b = base + i * 2, base + (i + 1) * 2
            faces.append((a, a + 1, b + 1, b))
        run.clear()

    for j in range(len(positions) - 1):
        s0, s1 = positions[j], positions[j + 1]
        if s1 - s0 < 1e-9:
            continue
        mid = (s0 + s1) / 2.0
        on = (not excluded(mid / total_len)) and (not dashed or (mid % cycle) < dash_len)
        if on:
            if not run:
                run.append(s0)
            run.append(s1)
        else:
            flush()
    flush()
    if not verts:
        return None
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    recalc_normals(me)
    obj = bpy.data.objects.new(name, me)
    coll.objects.link(obj)
    obj.data.materials.append(mat(matkey))
    return obj


def swept_profile(name, pts, profile_2d, coll, matkey="concrete"):
    """A solid mesh sweeping an arbitrary 2D cross-section (`profile_2d`, an ordered list of
    `(lateral_offset, height)` pairs) along the 3D polyline `pts=[(x,y,z), ...]` EXACTLY -- the
    same tangent/right-normal-offset technique as `swept_wall`/`flat_ribbon`, generalized from a
    fixed rectangle/ribbon to any cross-section (e.g. a curb-and-gutter L-shape, see
    `gutter_curb_profile`). `lateral_offset` is signed distance from the path (right-hand normal,
    same sign convention as `swept_wall`'s `thickness`); `height` is added to each point's Z.
    Produces the walls between consecutive profile points only (no end caps or a top/bottom
    closing face) -- fine for a curb/gutter that abuts other geometry on its unseen sides; add
    caps yourself if the profile is meant to be a free-standing closed solid."""
    n = len(pts)
    m = len(profile_2d)
    if n < 2 or m < 2:
        return None
    verts, faces = [], []
    for i, (x, y, z) in enumerate(pts):
        a = pts[max(0, i - 1)]
        b = pts[min(n - 1, i + 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        L = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / L, tx / L   # unit right-normal
        for off, h in profile_2d:
            verts.append((x + nx * off, y + ny * off, z + h))
    for i in range(n - 1):
        for j in range(m - 1):
            a, b = i * m + j, (i + 1) * m + j
            faces.append((a, a + 1, b + 1, b))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    recalc_normals(me)
    obj = bpy.data.objects.new(name, me)
    coll.objects.link(obj)
    obj.data.materials.append(mat(matkey))
    return obj


def gutter_curb_profile(width, height):
    """A simple 'city gutter' curb cross-section -- flush road-facing apron stepping up to a
    flat-topped curb face -- matching the overall SILHOUETTE of the hand-modeled
    `kit_side_straight_city_gutter_curb_w0p6m_l5m` piece (`kit/lane_kit.blend`, inspected
    read-only, never modified) reduced to just its width/height (per the author's own
    instruction -- not a literal geometry extraction, which that piece's actual topology doesn't
    trivially reduce to for an arbitrary-length swept curve). Points ordered by increasing
    lateral offset: road edge (flush, height 0) -> apron edge (flush) -> curb base -> curb top."""
    return [(0.0, 0.0), (width * 0.4, 0.0), (width * 0.4, height), (width, height)]


def export_gltf(objs, filepath):
    """Export the given objects (+ their data) to a .glb at filepath."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    for o in bpy.data.objects:
        o.select_set(False)
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=filepath, use_selection=True,
                              export_format='GLB', export_apply=True)
    print("exported", filepath)


def save_blend(here, fname):
    out = os.path.join(here, fname)
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("Saved", out)
    return out


# -------------------------------------------------------- Geometry-Nodes core
def make_gn_group():
    """GN_Instance: Object Info (As Instance) -> Instance on Points, with an
    optional per-point FLOAT_VECTOR `rot` attribute driving instance Rotation.
    Returns (node_group, object_socket_identifier)."""
    ng = bpy.data.node_groups.get("GN_Instance")
    if ng:
        return ng, ng["obj_id"]
    ng = bpy.data.node_groups.new("GN_Instance", "GeometryNodeTree")
    ifc = ng.interface
    ifc.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    obj_sock = ifc.new_socket("Object", in_out="INPUT", socket_type="NodeSocketObject")
    ifc.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nin = ng.nodes.new("NodeGroupInput"); nin.location = (-500, 0)
    nout = ng.nodes.new("NodeGroupOutput"); nout.location = (400, 0)
    oi = ng.nodes.new("GeometryNodeObjectInfo"); oi.location = (-250, -180)
    oi.transform_space = "ORIGINAL"
    if "As Instance" in oi.inputs:
        oi.inputs["As Instance"].default_value = True
    attr = ng.nodes.new("GeometryNodeInputNamedAttribute"); attr.location = (-250, 180)
    attr.data_type = "FLOAT_VECTOR"
    attr.inputs["Name"].default_value = "rot"
    iop = ng.nodes.new("GeometryNodeInstanceOnPoints"); iop.location = (100, 0)
    # Realize the instances into real mesh at the group OUTPUT. Without this the modifier emits bare
    # 'Instance on Points' instances, which render fine in Blender but the glTF exporter DROPS (they
    # collapse to the source at origin) — so every instanced layer (streetwall, road tiles, props)
    # piled up at center in the exported district pieces. Realizing bakes the placement into geometry
    # the exporter keeps. (Cost is Blender-side render/export memory only; the game uses the baked
    # .tscn, and the .blend still stores the compact GN setup, not realized geometry.)
    real = ng.nodes.new("GeometryNodeRealizeInstances"); real.location = (250, 0)
    L = ng.links.new
    L(nin.outputs["Geometry"], iop.inputs["Points"])
    L(nin.outputs["Object"], oi.inputs["Object"])
    L(oi.outputs["Geometry"], iop.inputs["Instance"])
    L(attr.outputs["Attribute"], iop.inputs["Rotation"])
    L(iop.outputs["Instances"], real.inputs["Geometry"])
    L(real.outputs["Geometry"], nout.inputs["Geometry"])
    ng["obj_id"] = obj_sock.identifier
    return ng, obj_sock.identifier


def src(name):
    o = bpy.data.objects.get(name)
    if o is None:
        raise RuntimeError("missing source object: " + name)
    return o


# ---- scene-instance MARKER mode (for the district-piece pipeline) --------------------------------
# When ON, world-space (parent=None) placements emit an `instance_<piece>` EMPTY carrying an
# `asset_path` meta = MARKER_KIT_DIR/<piece>.glb, instead of GN-instancing. The Java WorldBaker then
# swaps each into a real scene `instance=` reference to the kit leaf .glb — so a district piece is a
# tiny list of references (not baked mega-geometry) AND inherits the leaf's -colonly collision for
# free (BLENDER_CONVENTIONS "nested instancing"). Parented placements (tower modules via place_side)
# keep GN — they are few and stay real geometry. glTF cannot carry res:// instances, hence the marker.
MARKER_MODE = False
MARKER_KIT_DIR = "res://src/main/resources/com/openworld/world/kit/"


def _emit_markers(name, coords, piece_name, coll, loc, rot_z, rots):
    """Emit one instance_ marker per point (world space): pos = Rz(rot_z)·point + loc, and the
    per-marker Z rotation folds in rot_z + the point's own `rots` z. asset_path -> the kit .glb."""
    asset = MARKER_KIT_DIR + piece_name + ".glb"
    lx, ly, lz = loc
    a = math.radians(rot_z); ca, sa = math.cos(a), math.sin(a)
    for i, c in enumerate(coords):
        px, py, pz = c
        # mmesh_ -> WorldBaker folds all same-asset markers into ONE MultiMeshInstance3D (GPU
        # instancing: one node + one draw call, and NO collision body). Collision comes from
        # separate coarse proxies, so a dense district stays under the physics-body cap.
        e = bpy.data.objects.new("mmesh_" + piece_name, None)
        e.empty_display_size = 0.4
        e.location = (ca * px - sa * py + lx, sa * px + ca * py + ly, pz + lz)
        rz = rot_z + (math.degrees(rots[i][2]) if rots is not None else 0.0)
        e.rotation_euler = (0, 0, math.radians(rz))
        e["asset_path"] = asset
        coll.objects.link(e)
    return None


_PROXY_MESH_CACHE = {}   # asset_path -> imported visual Mesh datablock (imported once, reused)


def _res_to_abspath(res_path):
    """res://... -> absolute filesystem path (repo root is 4 dirnames up from lib/kit_common.py:
    lib -> assets/world_source -> assets -> repo root)."""
    if not res_path.startswith("res://"):
        return res_path
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(repo_root, res_path[len("res://"):])


def _attach_proxy(marker, asset_path, coll):
    """Import (once per unique asset_path — cached in _PROXY_MESH_CACHE) the kit .glb's VISUAL
    mesh only (skips any -colonly/-convcolonly collision-only object) and parent a linked
    duplicate (shared Mesh datablock, no geometry copy — same pattern as Blender's own Alt+D) under
    `marker` at local identity, so it moves/rotates with the marker but costs no extra mesh data
    per placement. Purely a viewport aid: WorldBaker's freeEmpty() discards the whole marker
    (proxy included) once it resolves asset_path, so this never reaches the baked output — verified
    producing byte-identical `instance=` results with or without it (see AUTHORING_GUIDE.md)."""
    mesh_data = _PROXY_MESH_CACHE.get(asset_path)
    if asset_path not in _PROXY_MESH_CACHE:
        abspath = _res_to_abspath(asset_path)
        if not abspath or not os.path.exists(abspath):
            mesh_data = None   # can't preview (e.g. asset not staged yet) — marker still bakes fine
        else:
            before = set(bpy.data.objects)
            bpy.ops.import_scene.gltf(filepath=abspath)
            imported = [o for o in bpy.data.objects if o not in before]
            visual = next((o for o in imported if o.type == 'MESH'
                           and not o.name.endswith(("-colonly", "-convcolonly"))), None)
            mesh_data = visual.data if visual else None
            for o in imported:   # drop the temporary import objects — only the Mesh datablock is kept
                bpy.data.objects.remove(o, do_unlink=True)
        _PROXY_MESH_CACHE[asset_path] = mesh_data
    if mesh_data is None:
        return
    proxy = bpy.data.objects.new(marker.name + "_proxy", mesh_data)
    coll.objects.link(proxy)
    proxy.parent = marker
    proxy.matrix_parent_inverse = Matrix.Identity(4)
    proxy.hide_select = True   # visual aid only — don't let it get accidentally moved/selected


def instance_marker(name, asset_path, loc, rot_z, coll, show_proxy=True):
    """Place an `instance_`/`asset_path` marker — the hand-authoring contract
    `WorldBaker.buildInstance` resolves at bake time (see BLENDER_CONVENTIONS.md "Nested
    instancing") — at `loc`/`rot_z`, optionally with a REAL visual proxy (see `_attach_proxy`) so
    you see the actual kit piece while hand-placing it, not a bare axis gizmo. Use this (not a
    bare `bpy.data.objects.new` + manual `asset_path` meta) for any hand-crafted building/district
    content going forward — it's the same marker contract either way, just with the viewport aid
    built in. Distinct from `_emit_markers` (the `mmesh_` bulk-content path) — that one stays
    proxy-free on purpose (thousands of repeats would make the proxy overhead real; a hand-placed
    building is a few dozen pieces at most)."""
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = 'PLAIN_AXES'
    e.empty_display_size = 0.3
    e.location = loc
    e.rotation_euler = (0, 0, math.radians(rot_z))
    e["asset_path"] = asset_path
    coll.objects.link(e)
    if show_proxy:
        _attach_proxy(e, asset_path, coll)
    return e


def instancer(name, coords, piece, coll, loc=(0, 0, 0), rot_z=0.0, parent=None, rots=None):
    """Instance `piece` (object or source-name) at each point in `coords`.
    rots: optional list of (rx,ry,rz) radians per point -> per-instance rotation."""
    if not coords:
        return None
    piece_name = piece if isinstance(piece, str) else piece.name
    if MARKER_MODE and parent is None:            # world-space layer -> scene-instance markers
        return _emit_markers(name, coords, piece_name, coll, loc, rot_z, rots)
    ng, obj_id = make_gn_group()
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(c) for c in coords], [], [])
    me.update()
    if rots is not None:
        a = me.attributes.new("rot", 'FLOAT_VECTOR', 'POINT')
        for i, rv in enumerate(rots):
            a.data[i].vector = rv
    obj = bpy.data.objects.new(name, me)
    coll.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (0, 0, math.radians(rot_z))
    if parent is not None:
        obj.parent = parent
        obj.matrix_parent_inverse = Matrix.Identity(4)
    mod = obj.modifiers.new("GN", "NODES")
    mod.node_group = ng
    mod[obj_id] = piece if isinstance(piece, bpy.types.Object) else src(piece)
    return obj


def make_gn_group_scaled():
    """Like GN_Instance but also reads a per-point FLOAT_VECTOR `scl` -> instance Scale
    (e.g. tapered ramp piers: one unit pillar scaled to each cell's height)."""
    ng = bpy.data.node_groups.get("GN_InstanceScaled")
    if ng:
        return ng, ng["obj_id"]
    ng = bpy.data.node_groups.new("GN_InstanceScaled", "GeometryNodeTree")
    ifc = ng.interface
    ifc.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    obj_sock = ifc.new_socket("Object", in_out="INPUT", socket_type="NodeSocketObject")
    ifc.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nin = ng.nodes.new("NodeGroupInput"); nin.location = (-500, 0)
    nout = ng.nodes.new("NodeGroupOutput"); nout.location = (400, 0)
    oi = ng.nodes.new("GeometryNodeObjectInfo"); oi.location = (-250, -180)
    oi.transform_space = "ORIGINAL"
    if "As Instance" in oi.inputs:
        oi.inputs["As Instance"].default_value = True
    rot = ng.nodes.new("GeometryNodeInputNamedAttribute"); rot.location = (-250, 200)
    rot.data_type = "FLOAT_VECTOR"; rot.inputs["Name"].default_value = "rot"
    scl = ng.nodes.new("GeometryNodeInputNamedAttribute"); scl.location = (-250, 60)
    scl.data_type = "FLOAT_VECTOR"; scl.inputs["Name"].default_value = "scl"
    iop = ng.nodes.new("GeometryNodeInstanceOnPoints"); iop.location = (100, 0)
    L = ng.links.new
    L(nin.outputs["Geometry"], iop.inputs["Points"])
    L(nin.outputs["Object"], oi.inputs["Object"])
    L(oi.outputs["Geometry"], iop.inputs["Instance"])
    L(rot.outputs["Attribute"], iop.inputs["Rotation"])
    L(scl.outputs["Attribute"], iop.inputs["Scale"])
    L(iop.outputs["Instances"], nout.inputs["Geometry"])
    ng["obj_id"] = obj_sock.identifier
    return ng, obj_sock.identifier


def instancer_scaled(name, coords, piece, coll, rots, scls):
    """Instance `piece` at each point with per-point rot AND scl (both FLOAT_VECTOR,
    same length as coords). Used for tapered piers (a unit pillar scaled per point)."""
    if not coords:
        return None
    ng, obj_id = make_gn_group_scaled()
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(c) for c in coords], [], [])
    me.update()
    ar = me.attributes.new("rot", 'FLOAT_VECTOR', 'POINT')
    asc = me.attributes.new("scl", 'FLOAT_VECTOR', 'POINT')
    for i, (rv, sv) in enumerate(zip(rots, scls)):
        ar.data[i].vector = rv
        asc.data[i].vector = sv
    obj = bpy.data.objects.new(name, me)
    coll.objects.link(obj)
    mod = obj.modifiers.new("GN", "NODES")
    mod.node_group = ng
    mod[obj_id] = piece if isinstance(piece, bpy.types.Object) else src(piece)
    return obj


def make_road_profile_group():
    """GN_RoadProfile: sweep a flat road ribbon along a curve via Curve to Mesh and assign a
    Material (group input) -- one filled pavement surface, shade-smooth, no thickness/volume.
    The curve's per-point RADIUS scales the profile -> a VARIABLE-WIDTH carriageway (true
    3->2->1 lane taper); its per-point TILT banks the deck. Mirrors `make_junction_pad_group()`'s
    shape exactly (Fillet/Fill-Curve there, Curve-to-Mesh here, otherwise the same "one flat
    filled mesh, materialed, shade-smooth" idiom) -- deliberately, see below. Returns
    `(node_group, (mat_id, thick_id))`; `thick_id`/"Thickness" is kept as an accepted-but-unused
    input purely so `road_spine()`/`road_from_curve()`/`assemble.py`'s existing
    `mod[thick_id] = thickness` calls keep working unchanged -- it no longer drives any geometry.

    **Simplified from a solid extruded slab to a flat plane (2026-07-28, user's own question after
    the bug below was found and fixed: "why is the road segment a box being pushed down, why not
    just a plane, like the intersection [pad]?").** That question was correct and is the real fix.
    The previous version swept the ribbon, then Extrude-Mesh'd it downward for a `Thickness`-deep
    solid deck, which needed a whole apparatus (endpoint tagging, cap-face deletion, a
    flatten-then-selective-reshade shading pass, and eventually a Join Geometry to restore a
    missing top face -- see git history / road_blender_godot.md for that chain of fixes) just to
    behave like a normal road surface. NONE of that is needed: nothing in the codebase reads or
    depends on the pavement having actual volume (collision, rendering, and every gameplay system
    only ever care about the top drivable surface), and `GN_JunctionPad` already proves a flat,
    zero-thickness swept/filled mesh collides and renders correctly for exactly the same kind of
    surface. A flat ribbon has no side walls, no end caps, and no top/bottom distinction to get
    wrong -- this eliminates the entire bug class the extrude approach kept reintroducing, for
    segments AND transitions alike (both go through this same group via `road_spine()`)."""
    ng = bpy.data.node_groups.get("GN_RoadProfile")
    if ng:
        return ng, (ng["mat_id"], ng["thick_id"])
    ng = bpy.data.node_groups.new("GN_RoadProfile", "GeometryNodeTree")
    ifc = ng.interface
    ifc.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    mat_sock = ifc.new_socket("Material", in_out="INPUT", socket_type="NodeSocketMaterial")
    thick_sock = ifc.new_socket("Thickness", in_out="INPUT", socket_type="NodeSocketFloat")
    thick_sock.default_value = 0.4   # accepted, unused -- see docstring
    ifc.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nin = ng.nodes.new("NodeGroupInput"); nin.location = (-700, 0)
    nout = ng.nodes.new("NodeGroupOutput"); nout.location = (500, 0)
    line = ng.nodes.new("GeometryNodeCurvePrimitiveLine"); line.location = (-500, -220)
    line.inputs["Start"].default_value = (-1.0, 0.0, 0.0)   # profile spans the curve normal
    line.inputs["End"].default_value = (1.0, 0.0, 0.0)
    c2m = ng.nodes.new("GeometryNodeCurveToMesh"); c2m.location = (-250, 0)
    # Blender 5.x Curve to Mesh has an explicit per-point "Scale" field (radius no longer
    # auto-scales) — drive it from the spine's Radius so half_w controls carriageway width.
    rad = ng.nodes.new("GeometryNodeInputRadius"); rad.location = (-500, -60)
    setm = ng.nodes.new("GeometryNodeSetMaterial"); setm.location = (60, 0)
    ss = ng.nodes.new("GeometryNodeSetShadeSmooth"); ss.location = (280, 0)
    L = ng.links.new
    L(nin.outputs["Geometry"], c2m.inputs["Curve"])
    L(line.outputs["Curve"], c2m.inputs["Profile Curve"])
    L(rad.outputs["Radius"], c2m.inputs["Scale"])
    L(c2m.outputs["Mesh"], setm.inputs["Geometry"])
    L(nin.outputs["Material"], setm.inputs["Material"])
    L(setm.outputs["Geometry"], ss.inputs["Geometry"])
    L(ss.outputs["Geometry"], nout.inputs["Geometry"])
    ng["mat_id"] = mat_sock.identifier
    ng["thick_id"] = thick_sock.identifier
    return ng, (mat_sock.identifier, thick_sock.identifier)


def swept_wall(name, pts, h, coll, matkey="concrete", thickness=0.18, z0=0.0):
    """A CONTINUOUS vertical barrier following the 3D polyline pts=[(x,y,z), ...]: a thin
    solid wall (box section) from z+z0 up by `h`, welded end-to-end with NO gaps — the fix
    for instanced straight panels that gap/overlap on a tight curve. Stays world-vertical
    (Curve-to-Mesh can't keep a wall profile upright on a banked/climbing spine)."""
    n = len(pts)
    if n < 2:
        return None
    verts, faces = [], []
    for i, (x, y, z) in enumerate(pts):
        a = pts[max(0, i - 1)]; b = pts[min(n - 1, i + 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        L = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / L * thickness / 2.0, tx / L * thickness / 2.0   # half-thickness normal
        base = z + z0
        verts += [(x - nx, y - ny, base), (x + nx, y + ny, base),
                  (x + nx, y + ny, base + h), (x - nx, y - ny, base + h)]
    for i in range(n - 1):
        a, b = i * 4, (i + 1) * 4
        faces += [(a + 3, a + 2, b + 2, b + 3),       # top
                  (a + 1, a + 2, b + 2, b + 1),       # +normal face
                  (a, a + 3, b + 3, b)]               # -normal face
    faces += [(0, 1, 2, 3), ((n-1)*4, (n-1)*4 + 3, (n-1)*4 + 2, (n-1)*4 + 1)]   # end caps
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces); me.update(); recalc_normals(me)
    obj = bpy.data.objects.new(name, me); coll.objects.link(obj)
    obj.data.materials.append(mat(matkey))
    return obj


def road_from_curve(name, pts, coll, matkey="asphalt", thickness=0.4, z_lift=0.0,
                    resolution=24):
    """Build a NURBS spine from pts=[(x,y,z,tilt,half_w), ...] (radius=half_w, tilt=bank)
    and apply GN_RoadProfile -> one swept, variable-width, banked, climbing road surface.
    Used for every ramp/connector/merge tail. Returns the road object (modifier live; glTF
    export bakes it)."""
    cu = bpy.data.curves.new(name + "_curve", 'CURVE')
    cu.dimensions = '3D'
    cu.resolution_u = resolution
    sp = cu.splines.new('NURBS')
    sp.points.add(len(pts) - 1)
    for i, (x, y, z, tl, hw) in enumerate(pts):
        sp.points[i].co = (x, y, z + z_lift, 1.0)
        sp.points[i].radius = max(hw, 1e-3)
        sp.points[i].tilt = tl
    sp.order_u = min(4, len(pts))
    sp.use_endpoint_u = True
    obj = bpy.data.objects.new(name, cu)
    coll.objects.link(obj)
    ng, (mat_id, thick_id) = make_road_profile_group()
    mod = obj.modifiers.new("Road", "NODES")
    mod.node_group = ng
    mod[mat_id] = mat(matkey)
    mod[thick_id] = thickness
    return obj


def road_spine(name, pts, coll, radius, matkey="asphalt", thickness=0.4):
    """A live-editable POLY-spline Curve object through pts=[(x,y,z), ...] with `GN_RoadProfile`
    attached DIRECTLY to it -- unlike `road_from_curve` (a fresh throwaway NURBS curve rebuilt
    from scratch every call), this object IS the persistent, user-editable spine: entering Edit
    Mode and adding/dragging a control point reshapes the pavement immediately via Blender's own
    dependency graph, no Python rebuild step for the pavement itself (only separately-offset L/R
    curb walls and lane-centerline data curves need re-sampling afterward -- see
    `road_kit_authoring/ops_segment.py`). `radius` is either one scalar (every point, a
    constant-width road) or a list matching `pts` (e.g. a linear lane-count-transition taper --
    `GN_RoadProfile`'s per-point Radius already does variable-width sweeps natively, no extra GN
    work needed for a taper). Returns the object (modifier live; glTF export bakes it)."""
    cu = bpy.data.curves.new(name + "_spine", 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    radii = radius if isinstance(radius, (list, tuple)) else [radius] * len(pts)
    for i, p in enumerate(pts):
        sp.points[i].co = (p[0], p[1], p[2], 1.0)
        sp.points[i].radius = max(radii[min(i, len(radii) - 1)], 1e-3)
    obj = bpy.data.objects.new(name, cu)
    coll.objects.link(obj)
    ng, (mat_id, thick_id) = make_road_profile_group()
    mod = obj.modifiers.new("Road", "NODES")
    mod.node_group = ng
    mod[mat_id] = mat(matkey)
    mod[thick_id] = thickness
    return obj


def set_road_spine_material(spine_obj, matkey):
    """Update an EXISTING `road_spine()` object's pavement material in place, without touching its
    shape/thickness -- for changing a segment/transition's pavement material after the fact
    (2026-07-28, user-reported: material was a build-time-only hardcoded literal, no way to change
    it afterward at all). `rebuild_segment_gn_in_place`/`rebuild_lane_transition_in_place`
    deliberately never delete/recreate the spine object itself (its own control points ARE the
    live-edited shape state), so a material change can't go through the normal "clear + rebuild"
    path curb/lane data uses -- this updates the live "Road" GN modifier's Material input directly,
    the same input `road_spine()` itself sets at creation time. No-op (returns False) if `spine_obj`
    doesn't have a "Road" modifier (not actually a road_spine() object)."""
    mod = spine_obj.modifiers.get("Road")
    if mod is None:
        return False
    _ng, (mat_id, _thick_id) = make_road_profile_group()
    mod[mat_id] = mat(matkey)
    return True


def make_barrier_profile_group():
    """GN_BarrierProfile: sweep a CONSTANT thin vertical rectangle (thickness x height, both
    group inputs, NOT scaled by the spine radius) along an EDGE curve via Curve to Mesh -> one
    continuous upright barrier following the ramp exactly, gap-free, at UNIFORM height while the
    deck lane width varies. The wall counterpart of GN_RoadProfile; both sweep the SAME densified
    spine so pavement edge and wall never diverge (the old bug: road swept a smooth curve while the
    wall chorded sparse control points). Profile-X maps to the curve normal (lateral) and profile-Y
    to world up (same frame the road relies on), so the rectangle is Width=Thickness (X) by
    Height (Y), lifted +Height/2 so the wall base sits on the deck edge. Returns
    (ng, (mat_id, h_id, t_id))."""
    ng = bpy.data.node_groups.get("GN_BarrierProfile")
    if ng:
        return ng, (ng["mat_id"], ng["h_id"], ng["t_id"])
    ng = bpy.data.node_groups.new("GN_BarrierProfile", "GeometryNodeTree")
    ifc = ng.interface
    ifc.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    mat_sock = ifc.new_socket("Material", in_out="INPUT", socket_type="NodeSocketMaterial")
    h_sock = ifc.new_socket("Height", in_out="INPUT", socket_type="NodeSocketFloat")
    h_sock.default_value = 1.1
    t_sock = ifc.new_socket("Thickness", in_out="INPUT", socket_type="NodeSocketFloat")
    t_sock.default_value = 0.18
    ifc.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nin = ng.nodes.new("NodeGroupInput"); nin.location = (-800, 0)
    nout = ng.nodes.new("NodeGroupOutput"); nout.location = (700, 0)
    quad = ng.nodes.new("GeometryNodeCurvePrimitiveQuadrilateral"); quad.location = (-560, -220)
    quad.mode = 'RECTANGLE'                              # Width -> X (lateral), Height -> Y (up)
    half = ng.nodes.new("ShaderNodeMath"); half.location = (-560, -400)
    half.operation = 'MULTIPLY'; half.inputs[1].default_value = -0.5   # profile-Y -> world -Z here,
    # so a -Height/2 lift puts the wall base ON the deck edge (0..H upward), not hanging below it
    comb = ng.nodes.new("ShaderNodeCombineXYZ"); comb.location = (-380, -400)
    sp = ng.nodes.new("GeometryNodeSetPosition"); sp.location = (-200, -220)  # lift base to 0..H
    c2m = ng.nodes.new("GeometryNodeCurveToMesh"); c2m.location = (40, 0)
    if "Fill Caps" in c2m.inputs:
        c2m.inputs["Fill Caps"].default_value = True
    setm = ng.nodes.new("GeometryNodeSetMaterial"); setm.location = (320, 0)
    ss = ng.nodes.new("GeometryNodeSetShadeSmooth"); ss.location = (500, 0)
    L = ng.links.new
    L(nin.outputs["Thickness"], quad.inputs["Width"])
    L(nin.outputs["Height"], quad.inputs["Height"])
    L(nin.outputs["Height"], half.inputs[0])
    L(half.outputs["Value"], comb.inputs["Y"])          # translate +Height/2 in profile-up (Y)
    L(quad.outputs["Curve"], sp.inputs["Geometry"])
    L(comb.outputs["Vector"], sp.inputs["Offset"])
    L(nin.outputs["Geometry"], c2m.inputs["Curve"])
    L(sp.outputs["Geometry"], c2m.inputs["Profile Curve"])
    L(c2m.outputs["Mesh"], setm.inputs["Geometry"])
    L(nin.outputs["Material"], setm.inputs["Material"])
    L(setm.outputs["Geometry"], ss.inputs["Geometry"])
    L(ss.outputs["Geometry"], nout.inputs["Geometry"])
    ng["mat_id"] = mat_sock.identifier
    ng["h_id"] = h_sock.identifier
    ng["t_id"] = t_sock.identifier
    return ng, (mat_sock.identifier, h_sock.identifier, t_sock.identifier)


def barrier_from_curve(name, edge_pts, coll, h=1.1, thickness=0.18, matkey="concrete",
                       resolution=24):
    """Build a NURBS edge spine from edge_pts=[(x,y,z), ...] and apply GN_BarrierProfile -> one
    continuous upright wall of constant height/thickness that follows the ramp edge. The GN
    swept-barrier replacement for the hand-welded swept_wall: fed the SAME densified edge as the
    road (same curve type/resolution), so wall and pavement never gap. Returns the wall object
    (modifier live; glTF export bakes it)."""
    if len(edge_pts) < 2:
        return None
    cu = bpy.data.curves.new(name + "_curve", 'CURVE')
    cu.dimensions = '3D'
    cu.resolution_u = resolution
    sp = cu.splines.new('NURBS')
    sp.points.add(len(edge_pts) - 1)
    for i, p in enumerate(edge_pts):
        sp.points[i].co = (p[0], p[1], p[2], 1.0)
    sp.order_u = min(4, len(edge_pts))
    sp.use_endpoint_u = True
    obj = bpy.data.objects.new(name, cu)
    coll.objects.link(obj)
    ng, (mat_id, h_id, t_id) = make_barrier_profile_group()
    mod = obj.modifiers.new("Barrier", "NODES")
    mod.node_group = ng
    mod[mat_id] = mat(matkey)
    mod[h_id] = h
    mod[t_id] = thickness
    return obj


# ---------------------------------------------- intersection pad/curb (road_kit_authoring, GN)
def _poly_curve_with_radius(name, pts_radius, coll, closed=True):
    """A POLY-spline Curve object through pts_radius=[(x,y,z,radius), ...] -- `radius` sets each
    point's built-in `.radius` (read by `GeometryNodeInputRadius` inside `GN_JunctionPad`/
    `GN_CurbLoop`, exactly the per-point-radius convention `GN_RoadProfile` already uses for lane
    width, reused here for per-corner FILLET radius: near-zero on straight/tail points, the
    corner's own (already clamped by `intersection_kit.build_curb_corners`) fillet radius on
    actual corner vertices; a `curb_loop(closed=False)` open path -- a segment/transition's own L/R
    curb line, no corners -- just passes 0 everywhere). Shared by `junction_pad` (always closed)
    and `curb_loop` (closed for an intersection loop, open for a segment's curb line) -- each
    builds its OWN boundary object from the same `pts_radius` (two small curve datablocks, not two
    GN outputs off one object) since a pad (Fill Curve) and a curb (Curve to Mesh) are genuinely
    different meshes that both need to coexist as separate exportable objects, same as this
    addon's other pieces."""
    cu = bpy.data.curves.new(name + "_bound", 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts_radius) - 1)
    for i, (x, y, z, r) in enumerate(pts_radius):
        sp.points[i].co = (x, y, z, 1.0)
        sp.points[i].radius = max(r, 1e-4)   # exactly 0 confuses Fillet Curve's Poly mode
    sp.use_cyclic_u = closed
    obj = bpy.data.objects.new(name + "_bound", cu)
    coll.objects.link(obj)
    return obj


def make_junction_pad_group():
    """GN_JunctionPad: a closed boundary curve (per-point Radius, see `_poly_curve_with_radius`) ->
    Fillet Curve (Poly mode, radius from the curve's own per-point Radius, `Limit Radius` on as a
    second, GN-native safety net alongside `intersection_kit`'s own tangent-length clamp) -> Fill
    Curve (N-gons) -> one filled pavement mesh, materialed, shade-smooth.

    This is the direct fix for the "widen one arm -> curb moves but pavement doesn't" bug: the pad
    is generated PURELY from the boundary polygon's own geometry, never from the union of
    per-lane-movement ribbons (which was capped at `min(a.lanes, b.lanes)` between arm pairs and
    could leave bare gaps) -- so it can never have a coverage gap regardless of how lane counts
    differ across arms. Returns `(node_group, (mat_id, seg_id, z_id))`.

    **Z-restore step (2026-07-27, user-reported "collision far from real mesh"/vehicles floating
    above the visual pad):** `Fill Curve` (N-gons mode) empirically FLATTENS every output vertex
    to world Z=0 regardless of the input curve's actual height -- confirmed directly: a plain flat
    closed curve with every point at Z=0.15 fed through Fill Curve alone (no fillet involved)
    still evaluates to Z=0.0 everywhere. This silently sank every intersection's visual pavement to
    Z=0 while `colonly_polygon`'s collision proxy (built independently straight from the same
    boundary points, never routed through Fill Curve) correctly sat at the real height
    (`lane_surface_z`, ~0.15m by default) -- a ~15-20cm vertical gap between the visible road
    surface and where vehicles/characters actually rest, exactly the reported symptom. Since every
    junction pad is flat by construction (`_populate_intersection_mesh.to3r` uses one single `z`
    for the whole boundary, never per-point height), the fix doesn't need to preserve arbitrary
    per-point Z through the fill -- a `Separate XYZ` -> `Combine XYZ` (X/Y passthrough, Z replaced
    by a new `Pad Z` input) -> `Set Position` (Position, not Offset -- REPLACES the wrong Z instead
    of stacking onto it) restores the correct flat height unconditionally, regardless of whatever
    height Fill Curve's internals happen to compute."""
    ng = bpy.data.node_groups.get("GN_JunctionPad")
    if ng:
        return ng, (ng["mat_id"], ng["seg_id"], ng["z_id"])
    ng = bpy.data.node_groups.new("GN_JunctionPad", "GeometryNodeTree")
    ifc = ng.interface
    ifc.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    mat_sock = ifc.new_socket("Material", in_out="INPUT", socket_type="NodeSocketMaterial")
    seg_sock = ifc.new_socket("Segments", in_out="INPUT", socket_type="NodeSocketInt")
    seg_sock.default_value = 8
    z_sock = ifc.new_socket("Pad Z", in_out="INPUT", socket_type="NodeSocketFloat")
    z_sock.default_value = 0.0
    ifc.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nin = ng.nodes.new("NodeGroupInput"); nin.location = (-700, 0)
    nout = ng.nodes.new("NodeGroupOutput"); nout.location = (900, 0)
    fillet = ng.nodes.new("GeometryNodeFilletCurve"); fillet.location = (-450, 0)
    fillet.inputs["Mode"].default_value = "Poly"
    fillet.inputs["Limit Radius"].default_value = True
    rad = ng.nodes.new("GeometryNodeInputRadius"); rad.location = (-650, -220)
    fill = ng.nodes.new("GeometryNodeFillCurve"); fill.location = (-180, 0)
    fill.inputs["Mode"].default_value = "N-gons"
    pos = ng.nodes.new("GeometryNodeInputPosition"); pos.location = (-180, -240)
    sepxyz = ng.nodes.new("ShaderNodeSeparateXYZ"); sepxyz.location = (20, -240)
    combxyz = ng.nodes.new("ShaderNodeCombineXYZ"); combxyz.location = (220, -240)
    setpos = ng.nodes.new("GeometryNodeSetPosition"); setpos.location = (280, 0)  # restore real Z
    setm = ng.nodes.new("GeometryNodeSetMaterial"); setm.location = (460, 0)
    ss = ng.nodes.new("GeometryNodeSetShadeSmooth"); ss.location = (680, 0)
    L = ng.links.new
    L(nin.outputs["Geometry"], fillet.inputs["Curve"])
    L(rad.outputs["Radius"], fillet.inputs["Radius"])
    L(nin.outputs["Segments"], fillet.inputs["Count"])
    L(fillet.outputs["Curve"], fill.inputs["Curve"])
    L(pos.outputs["Position"], sepxyz.inputs["Vector"])
    L(sepxyz.outputs["X"], combxyz.inputs["X"])
    L(sepxyz.outputs["Y"], combxyz.inputs["Y"])
    L(nin.outputs["Pad Z"], combxyz.inputs["Z"])
    L(fill.outputs["Mesh"], setpos.inputs["Geometry"])
    L(combxyz.outputs["Vector"], setpos.inputs["Position"])
    L(setpos.outputs["Geometry"], setm.inputs["Geometry"])
    L(nin.outputs["Material"], setm.inputs["Material"])
    L(setm.outputs["Geometry"], ss.inputs["Geometry"])
    L(ss.outputs["Geometry"], nout.inputs["Geometry"])
    ng["mat_id"] = mat_sock.identifier
    ng["seg_id"] = seg_sock.identifier
    ng["z_id"] = z_sock.identifier
    return ng, (mat_sock.identifier, seg_sock.identifier, z_sock.identifier)


def junction_pad(name, boundary_pts_radius, coll, matkey="asphalt", segments=8):
    """A filled intersection pavement pad from a closed boundary polygon (see
    `_poly_curve_with_radius`) via `GN_JunctionPad`. Returns the boundary/pad object (modifier
    live; glTF export bakes it, same convention as `road_from_curve`/`barrier_from_curve`).

    `Pad Z` is read off `boundary_pts_radius[0][2]` -- every point in a junction boundary shares
    the same Z by construction (a junction pad is always flat), so the first point's Z is the
    correct flat height for the whole pad; see `make_junction_pad_group`'s docstring for why this
    needs restoring at all (Fill Curve silently flattens to 0 otherwise)."""
    bound = _poly_curve_with_radius(name, boundary_pts_radius, coll, closed=True)
    ng, (mat_id, seg_id, z_id) = make_junction_pad_group()
    mod = bound.modifiers.new("Pad", "NODES")
    mod.node_group = ng
    mod[mat_id] = mat(matkey)
    mod[seg_id] = segments
    mod[z_id] = boundary_pts_radius[0][2] if boundary_pts_radius else 0.0
    bound.name = name
    return bound


def make_curb_loop_group():
    """GN_CurbLoop: the same filleted boundary curve as `GN_JunctionPad`, swept with a
    caller-supplied cross-section PROFILE object via Curve to Mesh -> one continuous,
    correctly-mitered curb loop (native Curve to Mesh handles corner miters for free; the old
    per-corner `swept_wall` code did not). `Profile` is a `NodeSocketObject` (NOT Geometry --
    assigning an Object directly to a Geometry-typed modifier input silently no-ops in this
    Blender version; routing it through an Object socket into an internal `Object Info` node is
    what actually works, verified against Blender 5.1) wired through this group's own `Object
    Info` node, so `curb_loop` can hand it a small cached BOX/GUTTER cross-section object (see
    `_curb_profile_object`) without duplicating profile geometry per curb. Returns
    `(node_group, (mat_id, seg_id, prof_id))`."""
    ng = bpy.data.node_groups.get("GN_CurbLoop")
    if ng:
        return ng, (ng["mat_id"], ng["seg_id"], ng["prof_id"])
    ng = bpy.data.node_groups.new("GN_CurbLoop", "GeometryNodeTree")
    ifc = ng.interface
    ifc.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    mat_sock = ifc.new_socket("Material", in_out="INPUT", socket_type="NodeSocketMaterial")
    seg_sock = ifc.new_socket("Segments", in_out="INPUT", socket_type="NodeSocketInt")
    seg_sock.default_value = 8
    prof_sock = ifc.new_socket("Profile", in_out="INPUT", socket_type="NodeSocketObject")
    ifc.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nin = ng.nodes.new("NodeGroupInput"); nin.location = (-700, 0)
    nout = ng.nodes.new("NodeGroupOutput"); nout.location = (700, 0)
    fillet = ng.nodes.new("GeometryNodeFilletCurve"); fillet.location = (-450, 100)
    fillet.inputs["Mode"].default_value = "Poly"
    fillet.inputs["Limit Radius"].default_value = True
    rad = ng.nodes.new("GeometryNodeInputRadius"); rad.location = (-650, -140)
    oi = ng.nodes.new("GeometryNodeObjectInfo"); oi.location = (-450, -260)
    c2m = ng.nodes.new("GeometryNodeCurveToMesh"); c2m.location = (-180, 0)
    # Fill Caps was unconditionally True (2026-07-28, user-reported: EVERY segment's curb shows a
    # solid box-shaped end wall exactly where it meets an intersection/another segment -- "align is
    # at top of the curb, not at road level" -- confirmed directly: an exported curb's end ring at
    # the connection point has all 4 cross-section corners present, a fully closed box face, not an
    # open end). Root cause: this curb loop is built from an OPEN (non-cyclic) boundary curve for a
    # segment's own L/R curb (`curb_loop(..., closed=False)`) -- Curve to Mesh's Fill Caps then caps
    # BOTH ends of that boundary with the profile's own shape, i.e. a solid curb-height block right
    # at the connection, the exact same class of bug `GN_RoadProfile`'s pavement had (fixed
    # 2026-07-28 earlier the same day) but never applied here. Fix is simpler here: Curve to Mesh
    # has a direct boolean for this (no manual endpoint-tag/delete-geometry plumbing needed like the
    # pavement fix required). False is safe unconditionally: a CLOSED intersection curb loop
    # (`closed=True`) is a cyclic boundary curve with no ends at all, so Fill Caps was already a
    # no-op there -- this only ever changed behavior for open (segment/transition) curbs, which is
    # exactly the case that needed it.
    c2m.inputs["Fill Caps"].default_value = False
    setm = ng.nodes.new("GeometryNodeSetMaterial"); setm.location = (60, 0)
    ss = ng.nodes.new("GeometryNodeSetShadeSmooth"); ss.location = (280, 0)
    L = ng.links.new
    L(nin.outputs["Geometry"], fillet.inputs["Curve"])
    L(rad.outputs["Radius"], fillet.inputs["Radius"])
    L(nin.outputs["Segments"], fillet.inputs["Count"])
    L(nin.outputs["Profile"], oi.inputs["Object"])
    L(fillet.outputs["Curve"], c2m.inputs["Curve"])
    L(oi.outputs["Geometry"], c2m.inputs["Profile Curve"])
    L(c2m.outputs["Mesh"], setm.inputs["Geometry"])
    L(nin.outputs["Material"], setm.inputs["Material"])
    L(setm.outputs["Geometry"], ss.inputs["Geometry"])
    L(ss.outputs["Geometry"], nout.inputs["Geometry"])
    ng["mat_id"] = mat_sock.identifier
    ng["seg_id"] = seg_sock.identifier
    ng["prof_id"] = prof_sock.identifier
    return ng, (mat_sock.identifier, seg_sock.identifier, prof_sock.identifier)


_CURB_PROFILE_CACHE = {}


def _curb_profile_object(style, height, thickness):
    """A cached, un-transformed helper Curve object at the origin representing ONE curb
    cross-section (local X = lateral offset from the spine, local Y = up -- the same profile-plane
    convention `GN_BarrierProfile`/`GN_RoadProfile` already use), fed into `GN_CurbLoop`'s Profile
    input. Cached by `(style, height, thickness)` so repeated builds/rebuilds (live-edit!) reuse
    one object instead of leaking a new datablock per rebuild; deliberately NOT linked into any
    scene collection (referenced only by GN modifiers via Object Info, never rendered/exported
    itself -- `export_gltf` only ever selects the objects it's explicitly given).

    The cache is a plain Python module global, so it survives a File > New / File > Open in the
    SAME Blender session (Python globals aren't reset by loading a different .blend) -- the
    PREVIOUS file's cached object is by then a freed RNA struct, and accessing ANY attribute on it
    (including `.name`, for the staleness check itself) raises `ReferenceError`, not a clean
    "not found." Guard with `GD`-style `try/except` instead of a bare attribute read so a stale
    cross-file reference is treated as a cache miss (rebuilt) rather than crashing the next build."""
    key = (style, round(height, 4), round(thickness, 4))
    obj = _CURB_PROFILE_CACHE.get(key)
    try:
        obj_valid = obj is not None and obj.name in bpy.data.objects
    except ReferenceError:
        obj_valid = False
    if obj_valid:
        return obj
    if style == 'GUTTER':
        pts2d = gutter_curb_profile(thickness, height)   # open profile: road edge -> curb top
        cyclic = False
    else:   # BOX (default/fallback for any unrecognized style)
        half_t = thickness / 2.0
        pts2d = [(-half_t, 0.0), (half_t, 0.0), (half_t, height), (-half_t, height)]
        cyclic = True
    cu = bpy.data.curves.new("RKA_CurbProfile_%s" % style, 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts2d) - 1)
    # `GN_CurbLoop`'s Curve to Mesh sweep maps this profile's local +Y to world -Z, the exact
    # same quirk `GN_BarrierProfile` already documents/compensates for ("profile-Y -> world -Z
    # here") -- `_curb_profile_object` never got the matching negation, so every curb hung DOWN
    # from the road surface instead of rising above it (2026-07-28, user-reported: "intersection
    # generated mesh is on upper of curb rather than bottom of curb" -- confirmed directly, a
    # flat curb line at Z=5.0 evaluated to [4.85, 5.0] instead of [5.0, 5.15]; same bug on both
    # segments and intersections, since both go through this one shared helper). Negate the
    # height component here, NOT inside `gutter_curb_profile()` itself, which is also used by
    # `ops_intersection.build_curb`'s GUTTER branch through `swept_profile` -- a different,
    # hand-rolled sweep with its own (already-correct, un-inverted) Z convention.
    for i, (lat, h) in enumerate(pts2d):
        sp.points[i].co = (lat, -h, 0.0, 1.0)
    sp.use_cyclic_u = cyclic
    obj = bpy.data.objects.new("RKA_CurbProfile_%s" % style, cu)
    _CURB_PROFILE_CACHE[key] = obj
    return obj


def curb_loop(name, boundary_pts_radius, coll, curb_style='BOX', curb_height=0.15,
              curb_thickness=0.25, matkey="concrete", segments=8, closed=True):
    """One continuous, correctly-mitered curb from a boundary/edge polygon via `GN_CurbLoop`.
    `closed=True` (default) is an intersection's full loop (same boundary `junction_pad` uses);
    `closed=False` is an OPEN edge line -- a straight/transition segment's own L or R curb, no
    corners to fillet (pass 0 radius for every point; Fillet Curve is then a no-op). Returns
    `None` for `curb_style == 'NONE'` (curb toggled off -- the caller skips linking/using the
    result, no wasted empty object is created at all)."""
    if curb_style == 'NONE':
        return None
    bound = _poly_curve_with_radius(name, boundary_pts_radius, coll, closed=closed)
    ng, (mat_id, seg_id, prof_id) = make_curb_loop_group()
    prof_obj = _curb_profile_object(curb_style, curb_height, curb_thickness)
    mod = bound.modifiers.new("Curb", "NODES")
    mod.node_group = ng
    mod[mat_id] = mat(matkey)
    mod[seg_id] = segments
    mod[prof_id] = prof_obj
    bound.name = name
    return bound


def curb_asset_row(name, boundary_pts_radius, coll, asset_obj, spacing, rot_offset_deg=0.0):
    """Repeat `asset_obj` (a mesh Object, e.g. from a linked kit/curb_kit.blend collection) along
    the edge polyline `boundary_pts_radius` (same 4-tuple-or-3-tuple shape `curb_loop()` accepts
    -- any 4th 'radius' element is ignored here, since ASSET-style curbs never fillet through GN:
    every boundary this addon ever builds is already an explicit polyline, arcs included as
    point density, so there is no live corner radius left to resolve at this style). Combines
    two existing generic building blocks for the first time: `sample_polyline` (position+heading
    every ~`spacing` m) feeds `instancer` (GN Instance-on-Points, per-point Z-rotation from
    heading). `rot_offset_deg` (typically 0 or 180) additionally spins every instance around its
    own Z -- the R-side curb of a two-way segment/corner typically needs 180 relative to the L
    side so an ASYMMETRIC piece's authored 'front' face (local +Y, see
    kit/build_curb_kit.py's worked example) keeps facing AWAY from the road on both sides, since
    both boundaries are sampled in the same spine direction. Returns the single GN-backed
    instancer Object (None if the boundary has fewer than 2 points after sampling), so it slots
    into the same 'one curb object per side/corner' convention every other curb style returns."""
    pts3 = [(p[0], p[1], p[2]) for p in boundary_pts_radius]
    samples = sample_polyline(pts3, spacing)
    if not samples:
        return None
    coords = [pos for pos, _hd in samples]
    rots = [(0.0, 0.0, hd + math.radians(rot_offset_deg)) for _pos, hd in samples]
    return instancer(name, coords, asset_obj, coll, rots=rots)


def colonly_swept(name, cpts, half_w, coll, z0=-0.4, z1=0.0, miter_limit=4.0):
    """A `<name>-colonly` swept solid slab following cpts=[(x,y,z[,...]), ...] with lateral
    half-width `half_w` (scalar OR per-point list), from z+z0 to z+z1. This is the drivable/solid
    COLLISION proxy a swept GN road/wall otherwise LACKS (importer drops the visual and builds a
    CollisionShape3D from the -colonly mesh). Low-poly by construction (one ring per densified
    point) so seg_len keeps the collider cheap while every segment still spans a vehicle.

    Per-vertex lateral direction is a proper MITER JOIN (2026-07-27, user-reported/screenshotted:
    a wedge of collision fanning out well past the curb at a sharp corner, well above the visual
    road) -- bisects the INCOMING edge's own left-normal and the OUTGOING edge's own left-normal,
    then scales the half-width by `1/cos(half the turn angle)` so both edges' offset lines still
    meet exactly at the corner (standard 2D polyline-offset miter join). The previous version used
    a single central-difference chord (`cpts[i+1] - cpts[i-1]`) for the normal at every point --
    fine for a gentle curve, but at a SHARP corner that chord doesn't match either adjacent edge's
    true perpendicular, so the swept quad connecting two corner rings could skew/twist into
    exactly this kind of overshooting wedge, while the visual mesh (Blender's native Curve-to-Mesh/
    Fillet Curve, which DOES miter corners correctly) stayed clean -- explaining why only the
    COLLISION looked wrong, never the road surface itself. `miter_limit` (default 4, i.e. never
    more than 4x half_w) caps the scale for a near-reversal turn (where the two edges point almost
    opposite ways and a true miter would run to infinity) -- falls back to the incoming edge's own
    plain perpendicular past that limit, a small square-ish notch instead of a spike, matching
    ordinary vector-graphics miter-limit behavior."""
    n = len(cpts)
    if n < 2:
        return None
    hw = list(half_w) if isinstance(half_w, (list, tuple)) else [half_w] * n
    verts, faces = [], []
    for i, p in enumerate(cpts):
        x, y, z = p[0], p[1], p[2]
        ein = eout = None
        if i > 0:
            ax, ay = p[0] - cpts[i - 1][0], p[1] - cpts[i - 1][1]
            La = math.hypot(ax, ay) or 1.0
            ein = (ax / La, ay / La)
        if i < n - 1:
            bx, by = cpts[i + 1][0] - p[0], cpts[i + 1][1] - p[1]
            Lb = math.hypot(bx, by) or 1.0
            eout = (bx / Lb, by / Lb)
        ein = ein or eout
        eout = eout or ein
        n1x, n1y = -ein[1], ein[0]      # incoming edge's own left normal
        n2x, n2y = -eout[1], eout[0]    # outgoing edge's own left normal
        mx, my = n1x + n2x, n1y + n2y
        mL = math.hypot(mx, my)
        if mL < 1e-6:
            nx, ny, scale = n1x, n1y, 1.0     # near-180 reversal -- no well-defined bisector
        else:
            nx, ny = mx / mL, my / mL
            cos_half = max(nx * n1x + ny * n1y, 1.0 / miter_limit)
            scale = 1.0 / cos_half
        w = hw[i] * scale
        verts += [(x - nx*w, y - ny*w, z+z0), (x + nx*w, y + ny*w, z+z0),
                  (x + nx*w, y + ny*w, z+z1), (x - nx*w, y - ny*w, z+z1)]
    for i in range(n - 1):
        a, b = i * 4, (i + 1) * 4
        faces += [(a+3, a+2, b+2, b+3),                 # top (drivable surface)
                  (a, b, b+1, a+1),                     # bottom
                  (a+1, b+1, b+2, a+2),                 # +normal side
                  (a, a+3, b+3, b)]                     # -normal side
    faces += [(0, 1, 2, 3), ((n-1)*4, (n-1)*4+3, (n-1)*4+2, (n-1)*4+1)]   # end caps
    me = bpy.data.meshes.new(name + "-colonly")
    me.from_pydata(verts, [], faces); me.update(); recalc_normals(me)
    obj = bpy.data.objects.new(name + "-colonly", me)
    coll.objects.link(obj)
    obj.data.materials.append(mat("col"))
    obj["proxy_for"] = name
    return obj


SHOULDER_MARGIN = 0.4   # m, extra collision-only half-width beyond the curb line -- see docstring
SEAM_OVERLAP = 0.5      # m, extra collision-only LENGTH past each end -- see docstring
# Both shrunk 2026-07-27 (from 2.0/1.5) once a much bigger contributor was found and fixed
# (VehicleAIController.cruiseSpeed 11->7 m/s cut departures from dozens starting at t=2.5s to two
# starting at t=41.5s on its own) -- the wide margin was then mostly just extra invisible collision
# floating past the visible curb with little safety benefit left to justify it (and was itself
# reported as visible: character/vehicle collision sitting perceptibly off the curb line). Kept
# small and nonzero rather than 0 -- still a bit of forgiveness for ordinary wheel/foot clipping,
# just not enough to read as a mismatch against the visual road.


def colonly_swept_between(name, left_pts, right_pts, coll, z0=-0.4, z1=0.0,
                           margin=SHOULDER_MARGIN, end_overlap=SEAM_OVERLAP):
    """A `<name>-colonly` swept solid slab for the PAVEMENT between two parallel offset lines
    (e.g. a segment/transition's own `curbs` field -- the exact `[left_pts, right_pts]` its visual
    ribbon/GN sweep already uses), built as `colonly_swept` from the pointwise midpoint centerline
    with pointwise half-width = half the left/right separation -- so it naturally follows a
    tapering width (a lane-count transition) with no extra per-caller math.

    This is the drivable-surface collision a segment/transition otherwise LACKS: only the curb
    EDGES got `colonly_swept` collision (a thin strip at each side), leaving the open lanes between
    them collision-free -- a vehicle driving the middle of the road fell straight through to
    whatever's below (ground/terrain, or nothing), landing well beneath the visual pavement while
    still correctly following its `PathLaneRoute` (a pure geometric path, unaffected by missing
    collision).

    `margin` (2026-07-27, user-reported "vehicle still on ground even at the beginning" -- traced
    via a per-vehicle raycast diagnostic to widespread, near-immediate collision departures, not a
    rare edge case): curb walls are only `curb_height` (~0.15m) tall -- trivially easy for a moving
    vehicle to hop over. `margin` extends the COLLISION ONLY (never the visual pavement/curb, which
    are built from the unmodified `left_pts`/`right_pts` elsewhere) a couple meters past each curb
    line, an invisible shoulder catching ordinary lateral steering drift. **Confirmed (via a
    per-tick position/velocity trace) NOT the dominant cause on its own** -- widening this alone
    left departures just as frequent, because most observed falls were a vehicle moving STEADILY
    FORWARD (accelerating out of a stop, not turning) that cleanly lost support and free-fell
    (velocity.y matching -9.8 m/s^2 exactly) while still advancing -- a LENGTHWISE gap, not a
    lateral one.

    `end_overlap` is the fix for that: each piece's collision slab starts/ends EXACTLY at its own
    p0/p1, meeting the NEXT piece's slab (built independently, from that piece's own p0/p1) at the
    same point -- geometrically touching, but two separate static colliders meeting at an EXACT
    shared boundary is exactly the classic "gap between tiles" scenario a fast-moving physics body
    can tunnel through in a single substep (Jolt, like most engines, doesn't guarantee catching a
    boundary-straddling contact between two disjoint meshes at speed). `end_overlap` extends the
    first/last centerline point backward/forward along its own local tangent by that many meters,
    so consecutive pieces' collision volumes OVERLAP instead of exactly touching, eliminating the
    seam a vehicle could otherwise slip through mid-crossing. Purely a safety net -- it does not
    change where a vehicle is intended to drive, only what happens if it strays slightly or crosses
    a seam at speed."""
    n = min(len(left_pts), len(right_pts))
    if n < 2:
        return None
    cpts, half_w = [], []
    for i in range(n):
        lx, ly, lz = left_pts[i][0], left_pts[i][1], left_pts[i][2]
        rx, ry, rz = right_pts[i][0], right_pts[i][1], right_pts[i][2]
        cpts.append(((lx + rx) / 2.0, (ly + ry) / 2.0, (lz + rz) / 2.0))
        half_w.append(math.hypot(rx - lx, ry - ly) / 2.0 + margin)
    if end_overlap > 0.0:
        def extend(p_from, p_to, dist):
            dx, dy, dz = p_to[0] - p_from[0], p_to[1] - p_from[1], p_to[2] - p_from[2]
            L = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
            return (p_to[0] + dx / L * dist, p_to[1] + dy / L * dist, p_to[2] + dz / L * dist)
        # Compute both extensions from the ORIGINAL (pre-mutation) points -- for a 2-point
        # polyline cpts[-2] IS cpts[0], so mutating cpts[0] before computing the far end would
        # feed the far end's tangent an already-extended (wrong) reference point.
        new_first = extend(cpts[1], cpts[0], end_overlap)
        new_last = extend(cpts[-2], cpts[-1], end_overlap)
        cpts[0] = new_first
        cpts[-1] = new_last
    return colonly_swept(name, cpts, half_w, coll, z0=z0, z1=z1)


def colonly_polygon(name, pts_radius, coll, z0=-0.4, z1=0.0, margin=SHOULDER_MARGIN):
    """A `<name>-colonly` flat filled-polygon collision slab for an intersection PAD footprint
    (`junction_pad`'s own `boundary_pts_radius`, the same `[(x,y,z,radius), ...]` shape
    `_poly_curve_with_radius` takes) -- fan-triangulated from the centroid (safe: every boundary
    `intersection_kit.build_junction_boundary` produces is star-shaped from the junction's own
    center by construction, since it's built from arm angles radiating outward) and extruded from
    z+z0 to z+z1, mirroring `colonly_swept`'s low-poly-by-construction philosophy.

    Deliberately built from the RAW control points, ignoring each point's fillet `radius` (a
    slightly-squared-off coarse footprint instead of the exact filleted arc) -- `junction_pad`'s
    own object is a GN-modifier-backed Curve with no real mesh data until glTF export bakes the
    modifier, so there is nothing to read back at author time the way `colonly_mesh()` reads a
    real visual mesh; a coarse polygon is more than adequate for a collision proxy, same standard
    every other `-colonly` helper in this module already accepts (`colonly()`'s own box proxy is
    coarser still). Godot import contract matches every other `-colonly` proxy: visual dropped,
    `CollisionShape3D` built from this mesh.

    `margin` -- same collision-only shoulder as `colonly_swept_between` (see its docstring for the
    full rationale: 15cm curb walls are trivially hoppable, and a vehicle that clears one over an
    elevated road otherwise free-falls). Pushes each boundary point directly away from the pad's
    own centroid by `margin` meters before triangulating -- valid for this star-shaped boundary
    (every point already radiates outward from the center by construction), and naturally extends
    thin arm-tail stubs further along their own already-outward direction rather than sideways.

    `z1` default changed 0.05 -> 0.0 (2026-07-27, user-reported: characters/vehicles visibly
    floating above the road instead of standing on it) -- the collision top no longer sits above
    the actual pad height at all; nothing about the coarse-polygon-vs-fillet approximation needs
    a positive margin here specifically (that concern is about the fillet corners' XY shape, not
    Z), so there was no real tradeoff in removing it."""
    n = len(pts_radius)
    if n < 3:
        return None
    cx = sum(p[0] for p in pts_radius) / n
    cy = sum(p[1] for p in pts_radius) / n
    z_ref = pts_radius[0][2]

    def push(p):
        dx, dy = p[0] - cx, p[1] - cy
        d = math.hypot(dx, dy) or 1.0
        return (p[0] + dx / d * margin, p[1] + dy / d * margin, p[2])

    pts_radius = [push(p) for p in pts_radius]
    bot_c = 0
    bot = [1 + i for i in range(n)]                # bottom boundary verts
    top_c = 1 + n
    top = [2 + n + i for i in range(n)]             # top boundary verts
    verts = [(cx, cy, z_ref + z0)] + [(p[0], p[1], p[2] + z0) for p in pts_radius] \
          + [(cx, cy, z_ref + z1)] + [(p[0], p[1], p[2] + z1) for p in pts_radius]
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.append((bot_c, bot[j], bot[i]))                  # bottom fan, normal down
        faces.append((top_c, top[i], top[j]))                  # top fan, normal up
        faces.append((bot[i], bot[j], top[j], top[i]))         # outward-facing side quad
    me = bpy.data.meshes.new(name + "-colonly")
    me.from_pydata(verts, [], faces); me.update(); recalc_normals(me)
    obj = bpy.data.objects.new(name + "-colonly", me)
    coll.objects.link(obj)
    obj.data.materials.append(mat("col"))
    obj["proxy_for"] = name
    return obj


def ramp_section_sweep(name, cpts, coll, deck_t=0.4, wall_h=1.1, wall_t=0.22, gaps=None,
                       grip="asphalt", wall_mat="concrete", collide=True):
    """Sweep the COMBINED ramp cross-section — deck slab + BOTH parapet walls — along the densified
    centreline cpts=[(x,y,z,bank,half_w), ...] as ONE welded mesh. Road and wall are the SAME object
    so they can never gap: the deck spans ±(half_w+wall_t), the wall sits directly ON that deck edge,
    and the drivable lane is ±half_w at v=0. This is `SM_Ramp_Grade_Wall_7`'s profile made CONTINUOUS
    (swept, not arrayed as tiles that facet a tight loop) — the fix for both the tile-faceting AND the
    shy-line gap of separate road+barrier sweeps. `gaps`=[(t0,t1)] OPEN the parapets (merge landing /
    ramp foot) while the deck continues. Emits a matching `<name>-colonly` (deck+walls) when `collide`.
    Returns the visual object."""
    n = len(cpts)
    if n < 2:
        return None
    gaps = gaps or []
    in_gap = lambda t: any(g0 <= t <= g1 for (g0, g1) in gaps)
    ring = []
    for i, p in enumerate(cpts):
        a = cpts[max(0, i - 1)]; b = cpts[min(n - 1, i + 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        L = math.hypot(tx, ty) or 1.0
        ring.append((p[0], p[1], p[2], -ty / L, tx / L, p[4]))    # x, y, z, nx, ny, half_w
    verts, faces, fmat = [], [], []
    def tube(idx, uL, uR, vB, vT, mi):
        """Swept rectangular tube over the ring indices `idx` (contiguous run); uL/uR are lateral
        offset functions of the point's half_w, vB/vT the vertical span. Records material index mi."""
        m = len(idx)
        if m < 2:
            return
        base = len(verts)
        for i in idx:
            x, y, z, nx, ny, hw = ring[i]
            for (u, v) in ((uL(hw), vB), (uR(hw), vB), (uR(hw), vT), (uL(hw), vT)):
                verts.append((x + u*nx, y + u*ny, z + v))
        for k in range(m - 1):
            a, b = base + k*4, base + (k+1)*4
            for f in ((a+3, a+2, b+2, b+3), (a, b, b+1, a+1),
                      (a+1, b+1, b+2, a+2), (a, a+3, b+3, b)):
                faces.append(f); fmat.append(mi)
        e = base + (m-1)*4
        faces.append((base, base+1, base+2, base+3)); fmat.append(mi)
        faces.append((e, e+3, e+2, e+1)); fmat.append(mi)
    WW = wall_t
    tube(list(range(n)), lambda hw: -(hw+WW), lambda hw: hw+WW, -deck_t, 0.0, 0)   # deck (mat 0)
    run = []                                                                        # walls (mat 1)
    for i in range(n):
        if in_gap(i / (n - 1)):
            if len(run) >= 2:
                tube(run, lambda hw: -(hw+WW), lambda hw: -hw, 0.0, wall_h, 1)      # left parapet
                tube(run, lambda hw: hw, lambda hw: hw+WW, 0.0, wall_h, 1)          # right parapet
            run = []
        else:
            run.append(i)
    if len(run) >= 2:
        tube(run, lambda hw: -(hw+WW), lambda hw: -hw, 0.0, wall_h, 1)
        tube(run, lambda hw: hw, lambda hw: hw+WW, 0.0, wall_h, 1)
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces]); me.update()
    me.materials.append(mat(grip)); me.materials.append(mat(wall_mat))
    for f, mi in zip(me.polygons, fmat):
        f.material_index = mi
    recalc_normals(me)
    obj = bpy.data.objects.new(name, me)
    coll.objects.link(obj)
    if collide:
        cme = bpy.data.meshes.new(name + "-colonly")
        cme.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces]); cme.update()
        cme.materials.append(mat("col")); recalc_normals(cme)
        cobj = bpy.data.objects.new(name + "-colonly", cme)
        coll.objects.link(cobj)
        cobj["proxy_for"] = name
    return obj


def sample_polyline(pts, spacing):
    """Resample a 3D polyline pts=[(x,y,z), ...] at ~`spacing` m -> [(pos, heading_rad)].
    For dropping discrete edge pieces (barriers, lights, piers) along a curve at grade."""
    if len(pts) < 2:
        return []
    out, carry = [], 0.0
    for (a, b) in zip(pts, pts[1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if seg < 1e-6:
            continue
        hd = math.atan2(b[1] - a[1], b[0] - a[0])
        d = carry
        while d < seg:
            t = d / seg
            out.append(((a[0] + (b[0]-a[0])*t, a[1] + (b[1]-a[1])*t, a[2] + (b[2]-a[2])*t), hd))
            d += spacing
        carry = d - seg
    out.append(((pts[-1][0], pts[-1][1], pts[-1][2]),
                math.atan2(pts[-1][1]-pts[-2][1], pts[-1][0]-pts[-2][0])))
    return out


def new_root(name, coll, loc, rot_z):
    root = bpy.data.objects.new(name, None)
    coll.objects.link(root)
    root.location = loc
    root.rotation_euler = (0, 0, math.radians(rot_z))
    root.empty_display_size = 0.4
    return root


def place_side(root, coll, tag, edge_loc, rot_z, nbays, floors, h, piece_for, z0=0.0,
               batch=None, base_loc=(0, 0, 0), base_rot=0.0):
    """Lay a wall grid (nbays x floors) along an edge, grouped by piece for fewer
    instancers. piece_for(floor, bay, nbays) -> piece name or None.
    If `batch` (a Batch) is given, accumulate world-space instances into it instead of
    creating per-call instancer objects — base_loc/base_rot are the building root's
    world loc/Z-rotation (deg), edge_loc/rot_z this side's own loc/rot (deg)."""
    groups = {}
    for j in range(floors):
        for i in range(nbays):
            pn = piece_for(j, i, nbays)
            if pn:
                groups.setdefault(pn, []).append((i * R_BAY, 0, z0 + j * h))
    if batch is not None:
        for pn, pts in groups.items():
            batch.add(pn, base_loc, base_rot, edge_loc, rot_z, pts)
        return
    for pn, pts in groups.items():
        instancer(f"{tag}_{pn.split('_')[-1]}", pts, pn, coll,
                  loc=edge_loc, rot_z=rot_z, parent=root)


def _rotz2(x, y, deg):
    """Rotate (x, y) about Z by `deg` degrees."""
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    return (c * x - s * y, s * x + c * y)


class Batch:
    """Consolidates many buildings' GN instances into ONE point cloud per piece — the
    lay_roads pattern applied to buildings. Each instance is baked into world space with
    a per-point Z rotation, so a whole streetwall flushes to a few dozen instancer
    objects instead of thousands of per-building point clouds + modifier stacks.

    The world transform reproduces the old object hierarchy exactly:
        world = T(base_loc) . Rz(base_rot) . T(edge_loc) . Rz(edge_rot) . p
    and the instance's Z rotation = base_rot + edge_rot (both rotations are about Z)."""

    def __init__(self):
        self.groups = {}                  # piece_name -> ([points], [rots])

    def add(self, piece, base_loc, base_rot, edge_loc, edge_rot, local_pts):
        rz = (0.0, 0.0, math.radians(base_rot + edge_rot))
        pts, rots = self.groups.setdefault(piece, ([], []))
        bx, by, bz = base_loc
        ex, ey, ez = edge_loc
        for (px, py, pz) in local_pts:
            qx, qy = _rotz2(px, py, edge_rot)         # edge frame
            wx, wy = _rotz2(qx + ex, qy + ey, base_rot)  # root frame
            pts.append((wx + bx, wy + by, pz + ez + bz))
            rots.append(rz)

    def flush(self, coll, tag="Front"):
        """Emit one instancer per accumulated piece, then clear. Returns the objects."""
        objs = [instancer(f"{tag}_{piece}", pts, piece, coll, rots=rots)
                for piece, (pts, rots) in self.groups.items()]
        self.groups = {}
        return objs


def append_kit(here, blendname, coll_name):
    """Append a collection (with its objects) from <here>/<blendname> into the scene.
    Idempotent: if the kit collection is already present (e.g. regen reopened the
    file), do nothing rather than create a .001 duplicate."""
    if bpy.data.collections.get(coll_name):
        return
    path = os.path.join(here, blendname)
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        if coll_name in src.collections:
            dst.collections = [coll_name]
    for col in dst.collections:
        if col is not None and col.name not in {c.name for c in
                                                bpy.context.scene.collection.children}:
            bpy.context.scene.collection.children.link(col)


def place_landmark(coll, blend_path, collection_name, loc):
    """Append a hand-modeled building-tier asset (its own top-level collection, e.g.
    PLATEAU_TokyoTower.blend's "TokyoTower" collection) and place its objects at `loc` (world/
    local coordinates in the CALLER's own frame -- a district piece's post-recenter local origin,
    or build_world.py's grid-space-then-to_world() frame; this helper only translates by `loc`,
    it doesn't know or care which frame that is). Distinct from `append_kit` (which links a shared
    kit-source collection once and leaves it hidden for GN instancing) -- a landmark is placed
    directly as real geometry, once, no reuse. Shared by build_district.py (precinct landmarks)
    and build_world.py (harbor landmarks) -- the one place this append-and-place pattern lives."""
    with bpy.data.libraries.load(blend_path, link=False) as (src, dst):
        if collection_name in src.collections:
            dst.collections = [collection_name]
    for landmark_coll in dst.collections:
        if landmark_coll is None:
            continue
        for obj in list(landmark_coll.objects):
            coll.objects.link(obj)
            if obj.parent is None:
                obj.location.x += loc[0]
                obj.location.y += loc[1]
                obj.location.z += loc[2]
    # the appended collection itself (now empty of useful content at the top level) isn't needed
    for c in list(dst.collections):
        if c is not None and c.name in bpy.data.collections and not c.objects:
            bpy.data.collections.remove(c)


def load_kits(here, kits=(("roads_kit.blend", "ROADS"), ("walls_kit.blend", "WALLS"),
                          ("props_kit.blend", "PROPS"), ("townextra_kit.blend", "EXTRAS"))):
    """Append every kit collection so all SOURCE pieces are available by name."""
    for blendname, coll in kits:
        append_kit(here, blendname, coll)
    return [coll for _, coll in kits]


def hide_sources(coll_names):
    """Hide kit SOURCE objects so they stay evaluated (for GN) but out of render."""
    for cn in coll_names:
        c = bpy.data.collections.get(cn)
        if not c:
            continue
        for o in c.objects:
            o.hide_render = True
            try:
                o.hide_set(True)
            except Exception:
                pass
