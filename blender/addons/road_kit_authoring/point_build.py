"""point_build.py -- authored points in, Blender geometry out.

TWO LIFETIME RULES, AND EVERY OBJECT IN THIS FILE OBEYS THEM (1.1):

1. **Authored and generated never share a collection.** A rebuild only ever clears inside
   `ROAD_MANAGER_GEN`. Nothing under `ROAD_MANAGER` is deleted by any build, ever. That is what
   makes Build safe to press with a selection active, mid-edit, at any time.
2. **One generated surface object per road run**, plus its edge furniture and its collision
   proxies. Layers are MODIFIERS, not sibling objects -- object-lifetime bookkeeping was half the
   previous addon (redesign defect 4).

WHAT BUILD DOES, IN ORDER:

    solve   -- `point_solve` resolves every run and every clique into numbers
    ground  -- `ground_sampler` raycasts the terrain under each sample, ALWAYS (3.3 rule 1)
    bands   -- `point_edges` collects every paved footprint
    carrier -- one polyline per run carrying every `point_solve.CARRIER_ATTRS` value
    stack   -- the GN layer stack, one modifier per band that has content
    edges   -- kerb / footway carriers over the OPEN RUNS only, so a gore opens by itself
    pads    -- one triangle-fan mesh per junction clique
    cut     -- the terrain is cut to each road's own footprint, as part of Build
    colonly -- separate carriageway and footway proxies, tagged for surface type and ped access

GROUND CONFORMING IS A STEP, NOT A BUTTON. `Cut Ground Under Road` being a manual panel step the
bake pipeline never called is the confirmed root cause of the "mesh holes" reports, so here the
footprint is a by-product of the outline and the cut runs inside `Build All`.

COLLISION IS A DELIVERABLE. The previous model's roads exported NONE, which silently cost the
pedestrian navmesh, bullet-impact surfaces, car ground and the player's footing all at once (3.5).
"""

import bpy
import bmesh
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "lib"))

import road_support as rs                                                    # noqa: E402

try:
    from . import point_edges as pe, point_model as pm, point_nodes as gn, point_solve as ps
except ImportError:
    import point_edges as pe                                                 # noqa: E402
    import point_model as pm                                                 # noqa: E402
    import point_nodes as gn                                                 # noqa: E402
    import point_solve as ps                                                 # noqa: E402


SUFFIX_CARRIER = "__surface"
SUFFIX_EDGE = "__edges"
SUFFIX_PAD = "__pad"
SUFFIX_COL = "-colonly"
SUFFIX_GORE = "__gore"

#: Godot reads the surface type off the proxy's own name suffix, the same convention the rest of
#: the kit already uses. Two proxies, never one merged: the navmesh and `ImpactManager` must be
#: able to tell a pavement from a road, and one mesh cannot say it.
COL_ROAD = "road"
COL_WALK = "walk"

#: A road whose `ped_access` is False routes its proxy to a layer `NavBaker` skips. Without this a
#: PIER deck bakes as walkable and an on-ramp is a continuous walkable slope -- AI walk onto the
#: expressway. `AGENT_MAX_CLIMB = 0.5` already makes a 0.15 m kerb climbable and a 1.0 m
#: expressway wall not, so the at-grade case is right already; the elevated case is not.
NO_PED_SUFFIX = "-noped"

MATERIALS = {
    "asphalt": (0.05, 0.05, 0.055, 1.0),
    "concrete": (0.55, 0.54, 0.52, 1.0),
    "footway": (0.42, 0.41, 0.40, 1.0),
    "median": (0.20, 0.30, 0.16, 1.0),
    "barrier": (0.68, 0.67, 0.64, 1.0),
}


def material(key):
    """Get-or-create a flat material by key, so a rebuild reuses the same datablock and any
    hand-edited shading on it survives."""
    mat = bpy.data.materials.get("rka_%s" % key)
    if mat is None:
        mat = bpy.data.materials.new("rka_%s" % key)
        mat.use_nodes = True
        mat.diffuse_color = MATERIALS.get(key, (0.5, 0.5, 0.5, 1.0))
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = MATERIALS.get(key, (0.5, 0.5, 0.5, 1.0))
            bsdf.inputs["Roughness"].default_value = 0.9
    return mat


# ------------------------------------------------------------------------------- GEN lifetime

def _local(collections, name):
    """Local-only lookup. Linked libraries carry same-named collections (several linked `STREET`s
    from `link_neighbors.py`), and picking one up would have this build clear a NEIGHBOUR's
    geometry."""
    for c in collections:
        if c.name == name and c.library is None:
            return c
    return None


def gen_root(scene=None):
    """`ROAD_MANAGER_GEN`, created on demand. Never holds anything hand-authored."""
    scene = scene or bpy.context.scene
    c = _local(bpy.data.collections, pm.ROAD_MANAGER_GEN)
    if c is None:
        c = bpy.data.collections.new(pm.ROAD_MANAGER_GEN)
    if _local(scene.collection.children, pm.ROAD_MANAGER_GEN) is None:
        scene.collection.children.link(c)
    return c


def gen_group(name, scene=None):
    """A per-road child of `ROAD_MANAGER_GEN`, emptied before use. Emptying by NAME PREFIX would
    be the bug: two roads called `art` and `art_2` share one."""
    root = gen_root(scene)
    c = _local(root.children, name)
    if c is None:
        c = bpy.data.collections.new(name)
        root.children.link(c)
    clear_collection(c)
    return c


def clear_collection(coll):
    """Free every object in a generated collection, recursively. Objects, not just links: an
    unlinked object is a zero-collection zombie held by its users and survives Purge Orphans."""
    for child in list(coll.children):
        clear_collection(child)
        bpy.data.collections.remove(child)
    for o in list(coll.objects):
        data = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if data is not None and data.users == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Curve):
                bpy.data.curves.remove(data)


def clear_all(scene=None):
    """Wipe every generated object. `ROAD_MANAGER` is not touched -- that is rule 1."""
    root = _local(bpy.data.collections, pm.ROAD_MANAGER_GEN)
    if root is not None:
        clear_collection(root)


# ------------------------------------------------------------------------------- ground sampling

TERRAIN_COLLECTIONS = ("TERRAIN", "GROUND", "MANUAL")


def ground_sampler(scene=None, depsgraph=None, top=2000.0):
    """`f(x, y) -> z` -- a downward raycast against the scene's terrain, or None when there is no
    terrain to hit.

    Returned as a CLOSURE and passed into the solve, rather than a method the solve calls, so
    `point_solve` stays free of bpy and every one of its numbers stays testable under plain
    `python3`. 3.3 rule 1: Build calls this unconditionally -- there is no "sample ground" button
    to forget, because forgetting it is the confirmed cause of the mesh-hole reports."""
    scene = scene or bpy.context.scene
    depsgraph = depsgraph or bpy.context.evaluated_depsgraph_get()

    # A ROAD'S OWN OUTPUT IS NOT TERRAIN, and getting this wrong is not a cosmetic bug: the ray
    # lands on the surface the LAST build swept, so `ground_z` climbs to the road's own height,
    # the support flips to NONE, and every rebuild walks the road a little further up. The first
    # version of this check tested the collection NAME for a `ROAD_MANAGER_GEN` prefix -- and
    # generated collections are named after their ROAD (`main`, `cross`, `ramp`), so it matched
    # nothing and skipped nothing. Membership, computed once, is the answer; a name is not.
    skip = gen_collection_names()

    def sample(x, y):
        hit, loc, _n, _i, obj, _m = scene.ray_cast(
            depsgraph, (x, y, top), (0.0, 0.0, -1.0))
        if not hit or obj is None:
            return None
        if any(c.name in skip for c in obj.users_collection):
            return None
        return loc.z

    return sample


def gen_collection_names():
    """Every collection name inside `ROAD_MANAGER_GEN`, root included. Recomputed on demand: a
    build creates a per-road child, so a cached set is stale exactly when it matters."""
    root = _local(bpy.data.collections, pm.ROAD_MANAGER_GEN)
    if root is None:
        return frozenset()
    names, stack = {root.name}, [root]
    while stack:
        c = stack.pop()
        for child in c.children:
            if child.name not in names:
                names.add(child.name)
                stack.append(child)
    return frozenset(names)


# ------------------------------------------------------------------------------- the carrier

def _carrier_mesh(name, solve):
    """One polyline, every `CARRIER_ATTRS` value written onto the point domain.

    ASSERTS the full attribute set. A Named Attribute node pointing at a name the mesh does not
    carry reads 0 and sweeps a zero-width band -- silently -- which at thirty-odd names is
    indistinguishable from "my change had no effect" (3.1)."""
    me = bpy.data.meshes.new(name)
    verts = [tuple(s.pos) for s in solve.samples]
    edges = [(i, i + 1) for i in range(len(verts) - 1)]
    if solve.is_loop and len(verts) > 2:
        edges.append((len(verts) - 1, 0))
    me.from_pydata(verts, edges, [])
    me.update()
    for a in ps.CARRIER_ATTRS:
        att = me.attributes.new(name=a.name, type='FLOAT', domain='POINT')
        att.data.foreach_set("value", [float(v.get(a.name, a.default)) for v in solve.values])
    missing = [a.name for a in ps.CARRIER_ATTRS if me.attributes.get(a.name) is None]
    assert not missing, "carrier is missing declared attributes: %s" % missing
    return me


def _mesh_object(name, me, coll):
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    return o


def build_carrier(solve, coll, name):
    """`<road>__surface` -- the swept road. One object, N modifiers."""
    obj = _mesh_object(name + SUFFIX_CARRIER, _carrier_mesh(name + SUFFIX_CARRIER, solve), coll)
    build_stack(obj)
    return obj


def _polyline_object(name, pts, coll, values=None, closed=False):
    """A carrier polyline carrying PER-POINT attribute dicts -- exactly how a kerb run, a footway
    run and a marking line are all emitted. One shape, so a new piece of edge furniture is a call,
    not a code path. `values` is `[{attr: v}]`, one per point; anything absent takes its declared
    default."""
    me = bpy.data.meshes.new(name)
    edges = [(i, i + 1) for i in range(len(pts) - 1)]
    if closed and len(pts) > 2:
        edges.append((len(pts) - 1, 0))
    me.from_pydata([tuple(p) for p in pts], edges, [])
    me.update()
    vals = values or [{}] * len(pts)
    for a in ps.CARRIER_ATTRS:
        att = me.attributes.new(name=a.name, type='FLOAT', domain='POINT')
        att.data.foreach_set("value", [float(v.get(a.name, a.default)) for v in vals])
    return _mesh_object(name, me, coll)


# ------------------------------------------------------------------------------------ the stack

def _layer(name, inner, offset=0.0, offset_attr="", z=0.0, z_attr="", require_attr="", **inputs):
    return {"name": name, "inner": inner, "offset": offset, "offset_attr": offset_attr,
            "z": z, "z_attr": z_attr, "require_attr": require_attr, "inputs": inputs}


def surface_spec():
    """THE ROAD SURFACE, AS DATA. Adding a band is one entry here, not a node tree (3.3a).

    Every entry names the attributes it reads, and every one of those names is declared in
    `point_solve.CARRIER_ATTRS`. Nothing in this list computes a lateral offset -- each layer is
    handed one, and every offset came from `lane_profile.slot_offset` by way of the solve.

    NOTE WHAT IS NOT HERE: the kerb and the footway. They ride the OUTLINE, on their own carriers
    over `point_edges.open_runs`, because a kerb swept along the road's own centreline runs
    straight through the asphalt at every gore and merge (3.2 -- measured at 257 of 3736 samples
    on the previous model). Keeping them out of this list is what makes that structural rather
    than a rule someone has to remember."""
    band, deck = gn.make_band_group(), gn.make_deck_group()
    pillars = gn.make_pillars_group()
    return [
        _layer("Carriageway", band, offset_attr="rka_shift", WidthAttr="rka_halfw",
               Material=material("asphalt")),
        # A PAINTED median is flush with the road, which is the same coplanar-surface trap the
        # deck fell into, just narrower -- so lift the paint by the matching bias. A raised median
        # already clears the asphalt and is unaffected.
        _layer("Median", band, WidthAttr="rka_med_h", z=ps.PAINT_Z_BIAS, z_attr="rka_med_z",
               Material=material("median")),
        # THE DECK TOP MUST SIT BELOW THE ROAD, NOT ON IT -- a top face at z = 0 is coplanar with
        # the asphalt over the entire road, which is z-fighting across the whole network. It spans
        # the FULL outline (`rka_deck_w`), not just the carriageway, so a viaduct carrying a
        # footway carries the footway too.
        _layer("Deck", deck, offset_attr="rka_deck_c", z=ps.DECK_Z_BIAS,
               WidthAttr="rka_deck_w", ThicknessAttr="rka_deck_h",
               Material=material("concrete")),
        _layer("Pillars", pillars, offset_attr="rka_deck_c", SpacingAttr="rka_sp_pillar",
               Material=material("concrete"), require_attr="rka_pillar_param"),
    ]


def edge_spec():
    """THE EDGE FURNITURE, swept along an `__edges` carrier whose polyline IS the kerb line.

    Same two node groups, same attribute names, no second implementation of "what a kerb looks
    like" -- which is the point. Because the polyline is already the line, `rka_curb_ol` is 0 on
    these carriers and the footway is offset outboard by its own half-width; the sign is carried in
    the value, so one spec serves both sides."""
    band, deck = gn.make_band_group(), gn.make_deck_group()
    return [
        _layer("Curb", deck, offset_attr="rka_curb_ol", z_attr="rka_curb_hl",
               WidthAttr="rka_curb_tl", ThicknessAttr="rka_curb_hl",
               Material=material("concrete")),
        _layer("Sidewalk", band, offset_attr="rka_walk_cl", z_attr="rka_walk_zl",
               WidthAttr="rka_walk_hl", Material=material("footway")),
        # THE BARRIER, and it belongs here for the same structural reason the kerb does: swept
        # along the OUTLINE, so `point_edges.open_runs` opens it wherever another road's asphalt
        # is -- at a gore, at a merge, at a junction mouth. A wall on the centreline would run
        # straight across the ramp join, which is the "sometimes missed an entire section of wall"
        # failure the previous model never got on top of. It is the same `deck` group as the kerb:
        # a bar of `WidthAttr` half-thickness whose TOP is at `z_attr`, extruded down by its
        # height, so there is no second idea of what a wall is either.
        _layer("Barrier", deck, offset_attr="rka_wall_c", z_attr="rka_wall_z",
               WidthAttr="rka_wall_hw", ThicknessAttr="rka_wall_h",
               Material=material("barrier")),
    ]


def _attr_values(mesh, name):
    att = mesh.attributes.get(name)
    if att is None or not hasattr(att, "data"):
        return None
    try:
        return [d.value for d in att.data]
    except AttributeError:
        return None


def layer_has_content(mesh, entry):
    """Would this layer build anything on THIS mesh?

    A layer whose width is zero everywhere still gets swept: Geometry Nodes happily extrudes a
    zero-width band and emits the polygons anyway. On the previous model that swept the full
    thirteen-layer road stack over every junction corner, producing 11,400 concrete polygons
    totalling 392 m2 of real area. Asking the mesh is better than hand-listing which layers a
    kerb run gets: it stays correct when a layer is added."""
    inputs = entry.get("inputs") or {}
    req = entry.get("require_attr")
    if req:
        vals = _attr_values(mesh, req)
        if vals is None or not any(abs(v) > 1e-6 for v in vals):
            return False
    for key in ("WidthAttr", "ThicknessAttr"):
        name = inputs.get(key)
        if not name:
            continue
        vals = _attr_values(mesh, name)
        if vals is None or not any(abs(v) > 1e-6 for v in vals):
            return False
    return True


def _set(mod, ids, name, value):
    """Set one Geometry Nodes modifier input by interface-socket identifier.

    NOT `mod[socket_id] = value`: this Blender's `NodesModifier` does not support IDProperties at
    all, for any socket type. Inputs live on `mod.properties.inputs`, whose per-socket attributes
    are read-only pointers to a struct carrying the mutable `.value`."""
    if name in ids:
        getattr(mod.properties.inputs, ids[name]).value = value


def build_stack(carrier_obj, spec=None):
    """(Re)build the carrier's modifier stack: head, every layer that has content, finish.

    Rebuilt wholesale rather than reconciled -- the stack is DERIVED from the spec, and
    reconciling a live stack against a spec is exactly the bookkeeping this design deletes. It is
    cheap: modifiers hold no geometry."""
    for m in list(carrier_obj.modifiers):
        carrier_obj.modifiers.remove(m)
    head = carrier_obj.modifiers.new("Spine", 'NODES')
    head.node_group = gn.make_spine_group()
    for s in (spec if spec is not None else surface_spec()):
        if not layer_has_content(carrier_obj.data, s):
            continue
        wrapper, ids = gn.wrap_layer(s["inner"], "GN_PointLayer_" + s["inner"].name)
        mod = carrier_obj.modifiers.new(s["name"], 'NODES')
        mod.node_group = wrapper
        _set(mod, ids, "Offset", float(s.get("offset", 0.0)))
        _set(mod, ids, "OffsetAttr", s.get("offset_attr", "") or "")
        _set(mod, ids, "ZOffset", float(s.get("z", 0.0)))
        _set(mod, ids, "ZOffsetAttr", s.get("z_attr", "") or "")
        for k, v in (s.get("inputs") or {}).items():
            if v is not None:
                _set(mod, ids, k, v)
    tail = carrier_obj.modifiers.new("Finish", 'NODES')
    tail.node_group = gn.make_finish_group()
    return carrier_obj


# ------------------------------------------------------------------------------- edge furniture

def edge_run_values(walk, kerb, wall, sgn):
    """Per-vertex `edge_spec()` attributes for ONE edge run, given what it carries and which way
    its furniture faces (`sgn`: +1 = the polyline's left).

    ONE OWNER, and that is the point of it: a road's flank, a junction corner and a gore's nose
    are all "a polyline that IS the kerb line", they all sweep the same stack, and three separate
    copies of this arithmetic is how the wall on one of them ends up half a kerb-width from where
    it is on the other two. `walk` is a HALF-width throughout, as `rka_walk_hl` is.

    The kerb's own lateral offset is zero -- the polyline is already the line. The footway sits
    outboard of it by its own half-width, on top of the kerb. The barrier stands at the OUTBOARD
    edge of whatever furniture is there: on the deck edge past the footway when there is one,
    right on the kerb line when there is not."""
    out = []
    half_t = ps.BARRIER_THICKNESS * 0.5
    for k in range(len(kerb)):
        h, w, wl = float(kerb[k]), float(walk[k]), float(wall[k])
        out.append({
            "rka_curb_ol": 0.0,
            "rka_curb_hl": h,
            "rka_curb_tl": h * ps.KERB_THICKNESS,
            "rka_walk_cl": sgn * w,
            "rka_walk_hl": w,
            "rka_walk_zl": h,
            "rka_wall_h": wl,
            "rka_wall_hw": half_t if wl > 0.0 else 0.0,
            "rka_wall_c": sgn * (2.0 * w + half_t),
            "rka_wall_z": h + wl,
        })
    return out


def build_edge_run(points, walk, kerb, wall, sgn, coll, name):
    """One `__edges` carrier: the polyline, its per-vertex furniture, the `edge_spec()` stack."""
    o = _polyline_object(name, points, coll, edge_run_values(walk, kerb, wall, sgn))
    build_stack(o, edge_spec())
    return o


def build_edges(solve, bands, coll, name):
    """`<road>__edges_<side>_<n>` -- kerb and footway, over the OPEN RUNS only.

    THIS IS WHERE THE GORE OPENS, and nothing here knows what a gore is. `point_edges.kerb_runs`
    reports the stretches of each paved boundary that are not buried in another road's asphalt;
    the furniture is built on those and nowhere else. There is no `RAMP_WALL_OPEN` constant, no
    merge-corridor solve and no ramp-specific branch -- the previous model needed all three and
    still "sometimes missed an entire section of wall"."""
    out = []
    runs = pe.kerb_runs(solve, bands)
    for side, edge in (("left", solve.edges_left), ("right", solve.edges_right)):
        sgn = 1.0 if side == "left" else -1.0
        kerb_key = "rka_curb_hl" if side == "left" else "rka_curb_hr"
        walk_key = "rka_walk_hl" if side == "left" else "rka_walk_hr"
        for n, run in enumerate(runs[side]):
            pts = pe.sub_polyline(edge, run)
            if len(pts) < 2:
                continue
            # `run_values` and `sub_polyline` are two readings of the same run, clipped ends and
            # all, so the polyline and its attributes cannot come out different lengths.
            vals = pe.run_values(solve.values, run)
            out.append(build_edge_run(
                pts,
                [v[walk_key] for v in vals],
                [v[kerb_key] for v in vals],
                [v["rka_wall_h"] for v in vals],
                sgn, coll, "%s%s_%s_%d" % (name, SUFFIX_EDGE, side, n)))
    return out


# ------------------------------------------------------------------------------- the pad

def build_pad(jsolve, coll, name):
    """One junction pad, tessellated by `point_solve.pad_triangles` and by nothing here.

    A fan and not an n-gon: n-gon tessellation of a concave, non-planar pad left measured
    0.38-0.49 m holes. But the fan's apex is the ring's KERNEL point, not the centroid -- and when
    even that does not exist the solve ear-clips -- so this always receives a watertight triangle
    list and a pad can no longer be a black crater OR a refused build. The gate still reports that
    the apex had to move, as a warning, because it usually means a mouth wants pulling out."""
    me = bpy.data.meshes.new(name + SUFFIX_PAD)
    tris = jsolve.fan
    verts, faces, seen = [], [], {}
    for tri in tris:
        face = []
        for v in tri:
            key = (round(v[0], 5), round(v[1], 5), round(v[2], 5))
            if key not in seen:
                seen[key] = len(verts)
                verts.append(tuple(float(c) for c in v))
            face.append(seen[key])
        if len(set(face)) == 3:
            faces.append(tuple(face))
    me.from_pydata(verts, [], faces)
    me.update()
    me.validate()
    o = _mesh_object(name + SUFFIX_PAD, me, coll)
    o.data.materials.append(material("asphalt"))
    return o


def build_junction_edges(jsolve, coll, name):
    """`JCT_*__edges_c<N>` -- the pad's own kerb and footway, one object per corner.

    Same `edge_spec()` as a road's edges, on the same kind of carrier, deliberately: a junction
    corner IS an edge run, it just happens to be an arc rather than a road's flank, and giving it
    its own idea of what a kerb looks like is how the two drift apart. What it fixes is a plain
    hole in the world -- every crossing was bare asphalt to its own boundary, with each street's
    footway stopping dead at its mouth.

    Outboard is to the RIGHT here: `intersection_kit` emits the pad's boundary CCW, so a corner
    that runs CCW around it has the outside on its right, which is the opposite of a road's LEFT
    flank. That sign is the only thing that differs from `build_edges`."""
    out = []
    for i, c in enumerate(jsolve.corners):
        if len(c.points) < 2:
            continue
        out.append(build_edge_run(c.points, c.walk, c.kerb, c.wall, -1.0, coll,
                                  "%s%s_c%d" % (name, SUFFIX_EDGE, i)))
    return out


# ------------------------------------------------------------------------------- the gore

def build_gore(gsolve, coll, name):
    """The paved wedge where a ramp leaves its mainline, as a triangle strip.

    2.4's rule is edge alignment and NO pad -- and that is still right for the JOIN. But a join
    that is a line has nothing under it a metre later: the mainline's edge peels one way, the
    ramp's the other, and the widening wedge between them was nobody's geometry, so the demo read
    as a ramp glued to the side of a road with a hole beside it. This is not a pad (no ring, no
    fan, no fillets): it is a strip between the two roads' OWN paved edges, which is why it cannot
    drift away from either one, and it stops at the nose where a real gore's paint stops."""
    me = bpy.data.meshes.new(name + SUFFIX_GORE)
    verts, faces, seen = [], [], {}
    for tri in gsolve.tris:
        face = []
        for v in tri:
            key = (round(v[0], 5), round(v[1], 5), round(v[2], 5))
            if key not in seen:
                seen[key] = len(verts)
                verts.append(tuple(float(c) for c in v))
            face.append(seen[key])
        if len(set(face)) != 3:
            continue
        # NORMALS UP, always. Which side of the mainline's edge the ramp's lies on flips with
        # `side`, so the strip's winding flips with it -- and a gore whose faces point at the
        # ground is invisible from above and shades black in-engine. The area sign in XY is the
        # cheapest correct test; a gore is never near-vertical.
        a, b, c = (verts[i] for i in face)
        area2 = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
        # The pair at the theoretical gore is by definition nearly coincident, so the first
        # triangle is a sliver whose normal is float noise. Drop anything under a square
        # millimetre: it covers nothing and shades badly.
        if abs(area2) < 2e-3:
            continue
        if area2 < 0.0:
            face = [face[0], face[2], face[1]]
        faces.append(tuple(face))
    if not faces:
        bpy.data.meshes.remove(me)
        return None
    me.from_pydata(verts, [], faces)
    me.update()
    me.validate()
    o = _mesh_object(name + SUFFIX_GORE, me, coll)
    o.data.materials.append(material("asphalt"))
    return o


def build_gore_edges(gsolve, coll, name):
    """`GORE_*__edges_nose` -- the cap that closes the open V at the gore's wide end.

    A gore is bare paint, so both flanking walls OPEN across it (`point_edges.Band.carries_edge`
    is False for a gore, deliberately) -- right along the join, where a wall would stand in the
    exit lane, and wrong at the wide end, where the two roads have parted and their own walls
    restart `nose_gap` metres apart with nothing between them.

    Same `edge_spec()`, same carrier, same `build_edge_run` as a road's flank and a junction
    corner, for the same reason (8g): a gore with its own idea of what a wall looks like is how
    the two drift apart. WHAT it carries came from the two roads' own solved furniture
    (`point_solve._gore_nose`), so a highway's barrier meeting a ramp's barrier is a wall, an
    approach that declares a footway gets a kerbed island, and a pair that declares neither builds
    nothing -- which is what the empty check below is for, not a special case for expressways."""
    c = getattr(gsolve, "nose", None)
    if c is None or len(c.points) < 2:
        return []
    if math.dist(c.points[0][:2], c.points[-1][:2]) < 1e-3:
        return []                     # a degenerate cap: two coincident edges, nothing to close
    if not any(abs(v) > 1e-6 for v in list(c.kerb) + list(c.walk) + list(c.wall)):
        return []
    return [build_edge_run(c.points, c.walk, c.kerb, c.wall, gsolve.nose_sgn, coll,
                           name + SUFFIX_EDGE + "_nose")]


# ------------------------------------------------------------------------------- the ground cut

def cut_ground(footprints, terrain_objects, depth=40.0):
    """Cut the terrain to each road footprint, as part of Build -- never a button.

    The union polygon the plan reached for is not needed: difference distributes over union, so
    cutting with each band in turn gives the same terrain as cutting with their union once
    (`point_edges`'s module docstring works this through). That is why there is no polygon clipper
    anywhere in this addon.

    Returns the cutter objects, which the caller frees. Skips silently when there is no terrain --
    a district authored without ground is a valid work-in-progress, not an error to raise into an
    artist's Build."""
    if not terrain_objects:
        return []
    cutters = []
    for owner, poly in footprints:
        if len(poly) < 3:
            continue
        me = bpy.data.meshes.new("rka_cut_" + owner)
        bm = bmesh.new()
        vs = [bm.verts.new((x, y, -depth)) for (x, y) in poly]
        try:
            face = bm.faces.new(vs)
        except ValueError:
            bm.free()
            bpy.data.meshes.remove(me)
            continue                      # a self-touching footprint: the gate reports it
        bmesh.ops.solidify(bm, geom=[face], thickness=2.0 * depth)
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new("rka_cut_" + owner, me)
        bpy.context.scene.collection.objects.link(o)
        cutters.append(o)
    for t in terrain_objects:
        for c in cutters:
            mod = t.modifiers.new("rka_cut", 'BOOLEAN')
            mod.operation = 'DIFFERENCE'
            mod.object = c
    return cutters


# ------------------------------------------------------------------------------- collision

def _evaluated_copy(obj, name, coll):
    """A plain mesh copy of `obj` AS THE VIEWER SEES IT -- modifiers applied.

    Copying the truth rather than approximating it: the previous kit's hand-rolled proxies (a
    corner-squared-off pad boundary that ignored the fillet radius, a per-vertex swept wall)
    visibly diverged from the real curved geometry, which reads in-game as an invisible wall in a
    place that looks walkable."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(depsgraph)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=False, depsgraph=depsgraph)
    me.name = name
    o = bpy.data.objects.new(name, me)
    o.matrix_world = obj.matrix_world.copy()
    coll.objects.link(o)
    return o


def collision_name(base, kind, ped_access):
    """`<base>-<kind>[-noped]-colonly`.

    TWO PROXIES, NEVER ONE MERGED. `NavBaker` needs to know a pavement from a road, and
    `ImpactManager.resolveSurfaceType` needs an asphalt-or-concrete answer -- one merged proxy
    cannot say either. The `-noped` marker routes a proxy to the layer `NavBaker` skips, which is
    what stops an on-ramp baking as a continuous walkable slope onto the expressway (3.5)."""
    return "%s-%s%s%s" % (base, kind, "" if ped_access else NO_PED_SUFFIX, SUFFIX_COL)


def build_collision(surface_objs, edge_objs, coll, name, ped_access):
    """A `-colonly` proxy per road run: one for the carriageway, one for the footway/kerb.

    Road collision stays a SEPARATE mesh from ground/terrain collision -- they change on
    independent schedules, and merging them means a road edit re-bakes the terrain."""
    out = []
    for objs, kind, ped in ((surface_objs, COL_ROAD, False), (edge_objs, COL_WALK, ped_access)):
        parts = [o for o in objs if o is not None]
        if not parts:
            continue
        merged = None
        for o in parts:
            c = _evaluated_copy(o, "%s_tmp_%s" % (name, kind), coll)
            if merged is None:
                merged = c
                continue
            merged.data = _joined(merged, c)
            bpy.data.objects.remove(c, do_unlink=True)
        if merged is None:
            continue
        merged.name = collision_name(name + "_" + kind, kind, ped)
        merged.data.name = merged.name
        merged.display_type = 'WIRE'
        merged.hide_render = True
        out.append(merged)
    return out


def _joined(a, b):
    """Merge `b`'s mesh into `a`'s and return the new mesh. `bmesh` rather than
    `bpy.ops.object.join`, which needs an active object and a context override and is the usual
    reason a headless build dies three steps later."""
    bm = bmesh.new()
    bm.from_mesh(a.data)
    tmp = bmesh.new()
    tmp.from_mesh(b.data)
    me = bpy.data.meshes.new(a.data.name)
    tmp.to_mesh(me)
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)
    tmp.free()
    out = bpy.data.meshes.new(a.data.name)
    bm.to_mesh(out)
    bm.free()
    return out


# ------------------------------------------------------------------------------- the whole build

def terrain_objects(scene=None):
    """The meshes the ground cut applies to: anything in a terrain-ish collection that is not
    generated. Local-only, so a linked neighbour's terrain is never cut by this district."""
    scene = scene or bpy.context.scene
    out = []
    for name in TERRAIN_COLLECTIONS:
        c = _local(bpy.data.collections, name)
        if c is None:
            continue
        for o in c.all_objects:
            if o.type == 'MESH' and o.library is None and not o.name.startswith("rka_"):
                out.append(o)
    return out


def write_ground_back(net, solves, ground, scene=None):
    """Stamp the sampled `ground_z` onto the AUTHORED Empties, not just the transient network.

    THE BUG THIS FIXES, and why it was invisible: `build_network` reads a fresh `NetworkData` and
    the solve writes the sampled ground onto THAT -- which the operator then drops on the floor.
    So the panel's "Ground Z (sampled)" readout stayed 0 forever, `.roads.json` never carried a
    ground height, and the gate's `ground_unsampled` warning could never clear no matter how many
    times Build ran. Nothing failed; the number simply never arrived. Found by driving the whole
    plugin end to end and reading the gate's own output afterwards.

    A MISS IS NOT A SAMPLE. `has_ground_z` is set only where the raycast actually hit something --
    a road over water, or past the terrain's edge, keeps whatever it had and keeps saying so.
    Claiming a sample that never happened would silently hand the support solver a 0.

    Returns `(hits, misses)`."""
    if ground is None:
        return (0, 0)
    by_uid = {}
    for coll in _local_road_collections(scene):
        for o in coll.objects:
            pt = getattr(o, "rka_pt", None)
            if pt is not None and pt.is_point and pt.uid:
                by_uid[pt.uid] = o
    hits = misses = 0
    for s in solves:
        for sm in s.samples:
            if sm.at_station is None:
                continue
            uid = s.uids[sm.at_station]
            z = ground(sm.pos[0], sm.pos[1])
            if z is None:
                misses += 1
                continue
            hits += 1
            data = net.points.get(uid)
            if data is not None:
                data.ground_z, data.has_ground_z = z, True
            obj = by_uid.get(uid)
            if obj is not None:
                obj.rka_pt.ground_z = z
                obj.rka_pt.has_ground_z = True
    return (hits, misses)


def _local_road_collections(scene=None):
    """Road collections under `ROAD_MANAGER`, local-only. Mirrors `point_model.road_collections`
    without importing it at module scope -- this module is imported BY the operators."""
    root = _local(bpy.data.collections, pm.ROAD_MANAGER)
    if root is None:
        return []
    return [c for c in root.children if c.library is None and c.name != pm.JUNCTIONS]


def build_network(net, scene=None, sample_ground=True, cut=True):
    """Build everything. Returns a report dict the panel and the smoketests both read.

    ORDER MATTERS AND IS NOT NEGOTIABLE: solve every road and every clique FIRST, collect the
    bands, and only then emit. The edge furniture is a fact about TWO roads at once -- how far a
    ramp is from the road it runs alongside -- so it cannot be answered inside a loop that only
    ever holds one. That was the previous model's `merge_corridor_ends` staging, and it is the one
    structural lesson from it worth keeping."""
    scene = scene or bpy.context.scene
    ground = ground_sampler(scene) if sample_ground else None

    solves, jsolves = [], ps.solve_junctions(net, ground_fn=ground)
    for road in net.roads.values():
        for uids in ps.road_runs(net, road):
            s = ps.solve_road(net, road, uids, ground)
            if s is not None:
                solves.append(s)
    # The gore is solved from the finished carriers, not alongside them: its two boundaries ARE
    # the two roads' own paved edges, so it cannot exist until both roads have some.
    gsolves = ps.solve_gores(net, solves)
    bands = pe.collect_bands(solves, jsolves, gsolves)

    report_ground = write_ground_back(net, solves, ground, scene)

    report = {"roads": 0, "runs": 0, "pads": 0, "gores": 0, "edges": 0, "colonly": 0,
              "not_star": [], "objects": [], "ground": report_ground}
    clear_all(scene)
    by_road = {}
    for s in solves:
        by_road.setdefault(s.road.name, []).append(s)

    for road_name, runs in by_road.items():
        coll = gen_group(road_name, scene)
        report["roads"] += 1
        for i, s in enumerate(runs):
            name = road_name if len(runs) == 1 else "%s_%d" % (road_name, i)
            surf = build_carrier(s, coll, name)
            edges = build_edges(s, bands, coll, name)
            report["runs"] += 1
            report["edges"] += len(edges)
            report["objects"].append(surf.name)
            cols = build_collision([surf], edges, coll, name, bool(s.road.ped_access))
            report["colonly"] += len(cols)

    if jsolves:
        jcoll = gen_group(pm.JUNCTIONS, scene)
        for j in jsolves:
            name = "JCT_" + j.uids[0][:8]
            if not j.star_ok:
                report["not_star"].append((name, round(j.star_worst, 3)))
            pad = build_pad(j, jcoll, name)
            report["pads"] += 1
            report["objects"].append(pad.name)
            corners = build_junction_edges(j, jcoll, name)
            report["edges"] += len(corners)
            # The corner footway is walkable, so it must reach the navmesh as a WALK proxy --
            # otherwise AI cross the road at the pad and never use the pavement they can see.
            report["colonly"] += len(build_collision([pad], corners, jcoll, name, True))

    if gsolves:
        gcoll = gen_group(pm.GORES, scene)
        for g in gsolves:
            gore = build_gore(g, gcoll, "GORE_" + g.ramp_uid[:8])
            if gore is None:
                continue
            report["gores"] += 1
            report["objects"].append(gore.name)
            nose = build_gore_edges(g, gcoll, "GORE_" + g.ramp_uid[:8])
            report["edges"] += len(nose)
            report["objects"] += [o.name for o in nose]
            # `ped_access` is BOTH flanks' answer (`GoreSolve.ped_access`), not a constant: an
            # island between an expressway and its ramp is not a refuge, and a walkable proxy
            # there is an invitation to stroll onto the carriageway -- but a gore between two
            # ordinary streets is a pedestrian island and must bake as one.
            report["colonly"] += len(build_collision([gore], nose, gcoll,
                                                     "GORE_" + g.ramp_uid[:8], g.ped_access))

    if cut:
        cutters = cut_ground([(b.owner, b.poly) for b in bands], terrain_objects(scene))
        report["cutters"] = len(cutters)
    return report


# ------------------------------------------------------------------------------- operators

class RKA_OT_point_build(bpy.types.Operator):
    """Build every road, junction and support from the authored points"""
    bl_idname = "rka.point_build"
    bl_label = "Build Roads"
    bl_options = {'REGISTER', 'UNDO'}

    cut_ground: bpy.props.BoolProperty(
        name="Cut Ground", default=True,
        description="Cut the terrain to each road's own footprint, as part of the build")

    def execute(self, context):
        try:
            from . import point_validate as pv
        except ImportError:
            import point_validate as pv
        try:
            from . import point_ops as po
        except ImportError:
            import point_ops as po
        # BEFORE the read. A point the artist rotated is adopted as MANUAL here, and every arrow
        # the tool still owns is re-faced to the chain -- so what the build sweeps is what the
        # viewport was showing, not a facing that silently went stale two drags ago.
        promoted, _refaced = po.sync_facings(context.scene)
        for name in promoted[:4]:
            self.report({'INFO'}, "%s was rotated -- its facing now shapes the road" % name)
        net = pm.read_network(context.scene)
        findings = pv.validate(net)
        errs = pv.errors(findings)
        if errs:
            # A BUILD THAT FAILS THE GATE IS A FAILED BUILD (5). Reported by OBJECT NAME, because
            # the artist fixes objects, not indices -- `pv.describe` resolves every uid in the
            # line, not just the subject.
            label = net.labels
            for f in errs[:5]:
                self.report({'ERROR'}, pv.describe(f, label))
            self.report({'ERROR'}, "%d gate error(s) -- nothing built" % len(errs))
            return {'CANCELLED'}
        rep = build_network(net, context.scene, cut=self.cut_ground)
        for name, worst in rep["not_star"]:
            self.report({'WARNING'}, "%s pad ring folds %.2f m -- ear-clipped instead of fanned; "
                                     "Auto Setback tidies it" % (name, worst))
        hits, misses = rep.get("ground", (0, 0))
        if misses:
            # Not an error: a road over water or past the terrain's edge legitimately has no
            # ground under it. But the artist should hear the number rather than discover it as a
            # column growing 40 m to nothing.
            self.report({'WARNING'}, "%d station(s) found no terrain below -- their support "
                                     "still uses the last sampled ground" % misses)
        self.report({'INFO'}, "%d road(s), %d run(s), %d pad(s), %d gore(s), %d edge run(s), "
                              "%d proxy(ies), %d ground sample(s)"
                    % (rep["roads"], rep["runs"], rep["pads"], rep["gores"], rep["edges"],
                       rep["colonly"], hits))
        return {'FINISHED'}


class RKA_OT_point_clear(bpy.types.Operator):
    """Delete every generated road object. Authored points are never touched"""
    bl_idname = "rka.point_clear"
    bl_label = "Clear Generated"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        clear_all(context.scene)
        self.report({'INFO'}, "ROAD_MANAGER_GEN cleared")
        return {'FINISHED'}


CLASSES = (RKA_OT_point_build, RKA_OT_point_clear)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
