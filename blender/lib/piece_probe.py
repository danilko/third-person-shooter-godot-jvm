"""piece_probe.py -- measure what a road piece IS, independently of what objects it is made of.

WHY THIS EXISTS. `ROAD_KIT_REDESIGN.md` §7 is blunt about it: the tests must assert *properties*,
not object names. Nineteen smoketests asserted things like "an object called `curb_Segment_001_L`
exists", which is a statement about the sibling-object build path rather than about the road -- so
the modifier-stack path could not be switched on without every one of them failing for a reason
that has nothing to do with whether the road is correct. The same road built as one carrier with a
`CurbL` modifier is still a road with a curb; only the bookkeeping changed.

So this module answers the questions the tests actually care about, in terms both build paths can
satisfy:

    "is there raised geometry on the left, and how far out?"    -> `raised_span`
    "is the piece as long as the alignment it was given?"       -> `length`
    "did the curb move outward when the road widened?"          -> `raised_span` before/after
    "is there any median?"                                      -> `raised_span(..., inner=True)`
    "does the collision proxy cover the drivable surface?"      -> `span` on the colonly pass

EVERYTHING IS MEASURED FROM THE SPINE, not from world axes, so a bent or rotated piece measures the
same as an axis-aligned one and a test written against a straight segment keeps meaning what it
says if the fixture ever bends. Each evaluated vertex is projected onto the spine polyline and
reported as `(s, lat, dz)`: distance along the spine, signed lateral offset, and height above the
spine at that station.

SIGN CONVENTION: `+lat` is to the LEFT of the direction the spine runs, i.e. the standard left
normal `(-t.y, t.x)` of the XY tangent. This is a measurement frame, deliberately NOT
`lane_profile`'s driving frame -- a probe that flipped with `traffic_side` would make a test's
"the left curb sits at +8.75" silently mean the other side on a keep-right road. Tests that care
about the driving frame should compare against `lane_profile.slot_offset` directly (see
`smoketest_segment_stack`), which is the one owner of that question.
"""
import contextlib

import bpy
from mathutils import Vector


@contextlib.contextmanager
def _measuring():
    """Mark this block as a READ, so the addon's live-edit watcher does not mistake it for an edit.

    Measuring a piece forces a depsgraph evaluation, and from `live_edit._on_depsgraph_update`'s
    point of view that is indistinguishable from the user having changed something: it queues a
    debounced rebuild of the collection. Measure a piece and then run an operator that rebuilds it
    -- exactly what a test does -- and two rebuilds land back to back on the same piece, which is
    the confirmed segfault inside `clear_generated_mesh_objects` that `live_edit.rebuilding()`
    exists to prevent (see its docstring, and `smoketest_rebuild_guard`). Measured here: 7 crashes
    in 15 runs before this guard, 0 after.

    The import is lazy and optional -- the same deferred-import idiom `spine_io.rs()` uses -- so
    `lib/` keeps no hard dependency on the addon and this module still works standalone."""
    live_edit = None
    try:
        from road_kit_authoring import live_edit as _le
        live_edit = _le if hasattr(_le, "rebuilding") else None
    except Exception:
        live_edit = None
    if live_edit is None:
        yield
        return
    with live_edit.rebuilding():
        yield

# A piece's collision proxies are excluded from every measurement by default: they are a *copy* of
# the visual geometry made at export time, so counting them in would double every span and make a
# "did anything move" check pass on the stale copy alone.
COLONLY_SUFFIX = "-colonly"

# Anything at or below this height above the spine is the road surface (pavement, painted
# markings); anything above it is raised -- a curb, a sidewalk slab, a median island. 3 cm is well
# under the smallest curb this kit builds (0.15 m) and well over the marking objects' z-fight lift.
RAISED_MIN_DZ = 0.03


class _EvalMesh(object):
    """A real, owned Mesh datablock of `obj`'s evaluated geometry, freed on exit.

    NOT `obj.evaluated_get(dg).to_mesh()`. That returns a TEMPORARY mesh owned by the evaluated
    object, and its lifetime is tied to a depsgraph that any subsequent operator invalidates --
    measuring a piece and then running a rebuild operator on it segfaulted Blender in 7 of 15 runs
    (a `to_mesh()` bake during authoring is the same crash surface that got `-colonly` proxy baking
    moved out of live rebuilds to export time; see `smoketest_collision`'s header).

    `bpy.data.meshes.new_from_object` hands back an ordinary datablock instead -- the pattern
    `kit_common.colonly_mesh_evaluated` already uses for exactly this reason -- which nothing else
    owns and which is explicitly removed here. Measuring can then be interleaved with operators
    freely, which is the whole point of a probe used by tests."""

    __slots__ = ("_obj", "me")

    def __init__(self, obj, depsgraph):
        self._obj = obj
        self.me = None
        try:
            self.me = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
        except (RuntimeError, AttributeError):
            self.me = None

    def __enter__(self):
        return self.me

    def __exit__(self, *_exc):
        if self.me is not None:
            bpy.data.meshes.remove(self.me)
            self.me = None
        return False


def _settled_depsgraph():
    """An evaluated depsgraph that is safe to build meshes from RIGHT AFTER an operator ran.

    A rebuild operator deletes and recreates a piece's objects; asking for their evaluated geometry
    before the dependency graph has caught up crashes Blender inside `new_from_object` (reproduced:
    a hard segfault in 3 of 15 runs, Python backtrace ending exactly there). Flushing the view
    layer first, then re-evaluating, is the same `_settle()` sequence `smoketest_rebuild_guard`
    uses for the same reason -- an interactive session gets this flush for free between operators,
    a script does not."""
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    return depsgraph


def _evaluated_verts(obj, depsgraph):
    """World-space vertices of `obj` AFTER modifiers. A road piece is mostly geometry nodes, so
    reading `obj.data.vertices` sees the bare spine polyline and none of the road -- the single
    most common way a geometry assertion silently measures nothing."""
    with _EvalMesh(obj, depsgraph) as me:
        if me is None:
            return []
        mat = obj.matrix_world
        return [mat @ v.co.copy() for v in me.vertices]


def _measurable(obj, include_colonly):
    if obj.type not in ('MESH', 'CURVE'):
        return False              # empties (origin/arm/port markers) carry no geometry
    if obj.name.endswith(COLONLY_SUFFIX):
        return include_colonly
    return True


def spine_object(coll):
    """The piece's spine, of EITHER carrier kind -- resolved through the collection's own
    `rka_curve_object` pointer rather than by guessing a name."""
    name = coll.get("rka_curve_object")
    if not name:
        return None
    return coll.objects.get(name) or bpy.data.objects.get(name)


def spine_points(coll):
    """The spine's world-space control points. Raw, never evaluated: evaluating a spine returns the
    swept pavement, not the centreline."""
    obj = spine_object(coll)
    if obj is None:
        return []
    if obj.type == 'CURVE':
        pts = obj.data.splines[0].points if obj.data.splines else []
        return [obj.matrix_world @ Vector((p.co[0], p.co[1], p.co[2])) for p in pts]
    return [obj.matrix_world @ v.co.copy() for v in obj.data.vertices]


def _station(pts, v):
    """Project `v` onto the spine polyline. Returns `(s, lat, dz)` for the nearest segment.

    `lat` is signed by the left normal of that segment's XY tangent; `dz` is height above the
    spine's own interpolated z, so a piece built on a grade measures the same as a flat one."""
    best = None
    s_base = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        ab = b - a
        seg_len = ab.length
        if seg_len <= 1e-9:
            continue
        t = max(0.0, min(1.0, (v - a).dot(ab) / (seg_len * seg_len)))
        proj = a + ab * t
        d = (v - proj).length
        if best is None or d < best[0]:
            tan = Vector((ab.x, ab.y, 0.0))
            if tan.length <= 1e-9:
                tan = Vector((1.0, 0.0, 0.0))
            tan.normalize()
            nrm = Vector((-tan.y, tan.x, 0.0))
            best = (d, s_base + seg_len * t, (v - proj).dot(nrm), v.z - proj.z)
        s_base += seg_len
    if best is None:
        return (0.0, 0.0, 0.0)
    return (best[1], best[2], best[3])


def stations(coll, include_colonly=False, objects=None):
    """Every evaluated vertex of the piece as `(s, lat, dz)` against its own spine.

    `objects` overrides which objects are measured (default: the whole collection) -- used by the
    collision test, which wants the colonly pass in isolation rather than mixed in."""
    pts = spine_points(coll)
    if len(pts) < 2:
        return []
    out = []
    with _measuring():
        depsgraph = _settled_depsgraph()
        src = objects if objects is not None else list(coll.objects)
        # The spine object is measured like any other: its EVALUATED geometry is the swept pavement
        # on the sibling path and the entire road (pavement + every layer) on the stack path.
        # Skipping it as "just the centreline" would measure nothing once the stack is the path.
        for obj in src:
            if not _measurable(obj, include_colonly):
                continue
            for v in _evaluated_verts(obj, depsgraph):
                out.append(_station(pts, v))
    return out


def length(coll):
    """The piece's spine length in metres -- what "as long as the alignment it was given" means."""
    pts = spine_points(coll)
    return sum((pts[i + 1] - pts[i]).length for i in range(len(pts) - 1))


def span(coll, min_dz=None, max_dz=None, include_colonly=False, objects=None):
    """Signed lateral extent `(min_lat, max_lat)` of the piece's geometry, optionally restricted to
    a height band above the spine. Returns `None` when the band holds no geometry at all, which is
    itself the assertion for "this part was removed" -- distinguishable from a zero-width span."""
    lats = [lat for (_s, lat, dz) in stations(coll, include_colonly, objects)
            if (min_dz is None or dz >= min_dz) and (max_dz is None or dz <= max_dz)]
    if not lats:
        return None
    return (min(lats), max(lats))


def raised_span(coll, side=None, min_dz=RAISED_MIN_DZ, include_colonly=False):
    """Lateral extent of the piece's RAISED geometry -- curb, sidewalk, median island -- i.e. what
    a test means when it says "the curb". `side` restricts to `'L'` (+lat) or `'R'` (-lat).

    `None` means there is no raised geometry on that side: the invariant form of "no curb object
    exists", and the one that stays true when the curb becomes a modifier."""
    vals = [lat for (_s, lat, dz) in stations(coll, include_colonly)
            if dz >= min_dz and (side is None
                                 or (lat > 0.0 if side == 'L' else lat < 0.0))]
    if not vals:
        return None
    return (min(vals), max(vals))


def raised_outer_edge(coll, side, min_dz=RAISED_MIN_DZ):
    """How far out the raised geometry reaches on `side`, as a positive distance from the spine.
    `None` when that side carries none. This is the number a widening test watches."""
    sp = raised_span(coll, side=side, min_dz=min_dz)
    if sp is None:
        return None
    return max(abs(sp[0]), abs(sp[1]))


def has_raised_between(coll, lat_lo, lat_hi, min_dz=RAISED_MIN_DZ):
    """True when raised geometry exists anywhere in the lateral band `[lat_lo, lat_hi]` -- the
    "is there a median island between the carriageways" question, asked without naming an object."""
    return any(dz >= min_dz and lat_lo <= lat <= lat_hi
               for (_s, lat, dz) in stations(coll))


def surface_span(coll, max_dz=RAISED_MIN_DZ, include_colonly=False, objects=None):
    """Lateral extent of the piece's geometry AT ROAD LEVEL: the pavement, the painted markings,
    and the base course of anything raised (a curb's own footprint sits at dz = 0). It is
    deliberately not "the drivable width" -- a sidewalk's underside is at road level too."""
    return span(coll, max_dz=max_dz, include_colonly=include_colonly, objects=objects)


def raised_world_points(coll, min_dz=RAISED_MIN_DZ, include_colonly=False):
    """WORLD-space positions of the piece's raised geometry.

    Everything else in this module reports spine-relative coordinates, which are invariant under a
    rigid move of the whole piece -- exactly the wrong frame for asking "did the piece actually
    move". This is the escape hatch for that one question."""
    pts = spine_points(coll)
    if len(pts) < 2:
        return []
    out = []
    with _measuring():
        depsgraph = _settled_depsgraph()
        for obj in coll.objects:
            if not _measurable(obj, include_colonly):
                continue
            for v in _evaluated_verts(obj, depsgraph):
                if _station(pts, v)[2] >= min_dz:
                    out.append(v)
    return out


def raised_centroid(coll, min_dz=RAISED_MIN_DZ):
    """World-space centroid of the raised geometry, or `None` when there is none. A single number
    pair a move test can compare before and after."""
    ws = raised_world_points(coll, min_dz)
    if not ws:
        return None
    n = float(len(ws))
    return (sum(v.x for v in ws) / n, sum(v.y for v in ws) / n, sum(v.z for v in ws) / n)


def raised_vert_count(coll, side=None, min_dz=RAISED_MIN_DZ):
    """How many evaluated vertices sit above the road surface, optionally on one side only.

    This is the invariant form of "exactly one curb object, not a stray `.001` duplicate": a
    duplicate is a second copy of the same shell in the same place, which changes no span and no
    object name a test could sensibly assert, but doubles this. Compare it across two identical
    edits rather than against a literal -- the absolute number is a property of the build path,
    the fact that it does not grow is a property of the road."""
    return sum(1 for (_s, lat, dz) in stations(coll)
               if dz >= min_dz and (side is None
                                    or (lat > 0.0 if side == 'L' else lat < 0.0)))


def raised_face_spans(coll, side, min_dz=RAISED_MIN_DZ):
    """The lateral interval each raised POLYGON covers, on `side`.

    Faces, not vertices, because a flat slab -- a sidewalk, a median island top -- carries vertices
    only at its edges. Sampling the vertex cloud would report the slab's own uncrossed middle as a
    hole in the pavement, which is the opposite of the truth. A face spans what it covers."""
    pts = spine_points(coll)
    if len(pts) < 2:
        return []
    out = []
    with _measuring():
      depsgraph = _settled_depsgraph()
      for obj in coll.objects:
        if not _measurable(obj, False):
            continue
        with _EvalMesh(obj, depsgraph) as me:
            if me is None:
                continue
            mat = obj.matrix_world
            st = [_station(pts, mat @ v.co) for v in me.vertices]
            for poly in me.polygons:
                vs = [st[i] for i in poly.vertices]
                if max(dz for (_s, _l, dz) in vs) < min_dz:
                    continue
                lats = [lat for (_s, lat, _d) in vs]
                lo, hi = min(lats), max(lats)
                if side == 'L' and hi <= 0.0:
                    continue
                if side == 'R' and lo >= 0.0:
                    continue
                out.append((lo, hi))
    return out


def raised_gaps(coll, side, min_dz=RAISED_MIN_DZ, min_gap=0.05):
    """Lateral intervals on `side` where the raised geometry BREAKS -- where a curb ends and its
    sidewalk has not started. Returns `(lat_lo, lat_hi)` gaps wider than `min_gap`, empty when the
    raised band runs unbroken.

    This is the invariant behind the "curb/sidewalk gap" family of tests. They measured two NAMED
    objects' Y bounds and subtracted; what they were really asserting is that the raised surface
    runs continuously outward from the kerb, which is true or false about the road no matter how
    many objects express it -- one curb object plus one sidewalk object, or one carrier with a
    `CurbL` and a `SidewalkL` modifier."""
    spans = sorted(raised_face_spans(coll, side, min_dz))
    if not spans:
        return []
    gaps = []
    reach = spans[0][1]
    for lo, hi in spans[1:]:
        if lo > reach + min_gap:
            gaps.append((reach, lo))
        reach = max(reach, hi)
    return gaps


def clusters_along(coll, lat_lo, lat_hi, min_dz=RAISED_MIN_DZ, gap=1.0):
    """How many SEPARATE blobs of geometry sit in the lateral band `[lat_lo, lat_hi]`, counted
    along the piece. Two blobs are separate when more than `gap` metres of empty spine lies between
    them.

    This is how a row of props (streetlights, bollards) is counted without naming objects: on the
    sibling path each is its own object, on the stack path they are geometry-node instances inside
    the carrier's mesh and no object exists to count. Both give the same number of blobs."""
    ss = sorted(s for (s, lat, dz) in stations(coll)
                if dz >= min_dz and lat_lo <= lat <= lat_hi)
    if not ss:
        return 0
    n = 1
    for a, b in zip(ss, ss[1:]):
        if b - a > gap:
            n += 1
    return n


# NO `materials()` HERE, DELIBERATELY (2026-08-13). A "what material is this part made of" probe
# was written, worked, and had to be removed: reading materials off a piece's EVALUATED geometry is
# not safe on this Blender build. Two independent failures, both reproduced:
#
#   * a GN-modifier-backed Curve's evaluated material slot can hand back a bare `ID` instead of a
#     `Material`, whose `.name` is a dangling read (observed as the literal string
#     "Scene Collection" one run and the piece's real material the next);
#   * building an evaluated mesh from those objects right after a rebuild operator SEGFAULTS
#     Blender roughly one run in five -- hard crash inside `new_from_object`, and neither settling
#     the depsgraph first nor holding no Python references to the temporary mesh prevents it.
#
# Ask the GN modifier's own Material input instead (`kit_common.get_mod_input`, as
# `smoketest_matkey_panel._spine_mat_name` / `_curb_mat_name` do). That is a plain property read
# with no evaluation, it is stable, and it is where the material actually lives until glTF export
# bakes it. Geometry POSITION probing below is unaffected -- it is only the material access that is
# broken.


def geometry_summary(coll, include_colonly=False):
    """One dict of everything above, for a test's failure message. A geometry assertion that fails
    with only `False != True` costs an hour; one that prints the piece's actual span costs none."""
    st = stations(coll, include_colonly)
    return {
        "length": round(length(coll), 3),
        "verts": len(st),
        "span": span(coll, include_colonly=include_colonly),
        "surface_span": surface_span(coll, include_colonly=include_colonly),
        "raised_L": raised_span(coll, 'L'),
        "raised_R": raised_span(coll, 'R'),
        "max_dz": round(max((dz for (_s, _l, dz) in st), default=0.0), 3),
    }
