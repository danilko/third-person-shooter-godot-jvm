"""spine_io.py -- read/write a piece's spine control points without caring which CARRIER holds
them: the legacy POLY-`Curve` object, or the MESH polyline `road_stack` uses.

WHY BOTH EXIST. A `bpy.types.Curve` datablock has no `.attributes` collection at all (verified:
`AttributeError`), so it can carry exactly two per-point floats -- the built-in `radius` and
`tilt`. That is the hard limit that forced a taper or a ramp to be cut into several pieces: there
was nowhere to put a per-point cross-section. A Mesh can carry as many named per-vertex attributes
as we like, and `Mesh to Curve` preserves them into the curve domain, so the mesh carrier is what
makes `lane_profile`'s per-station profile expressible along ONE spine (see
`lib/road_stack.py`). New pieces are built on the mesh carrier; every piece already in
`island_v3_roads.blend` is still on a Curve until that file is regenerated after the last phase.

THE ADAPTER PRESENTS THE CURVE SHAPE, deliberately. `points(obj)` yields objects with a 4-tuple
`.co` and a float `.radius` -- exactly what `bpy.types.SplinePoint` offers -- because roughly a
dozen call sites in `live_edit.py` do real geometry on them (`_blend_endpoints_range`,
`_bend_near_end_to_angle`, `_ensure_bend_room`, the port-drag sync) and that code is correct,
subtle, and has its own smoketests. Rewriting it to a different point API would be a large edit
with nothing to gain. For a Curve carrier `points()` returns the genuine `SplinePoint`s with zero
indirection; only the mesh carrier pays for a proxy.

`radius` on a mesh carrier maps to the `rka_halfw` per-vertex attribute -- the same quantity the
Curve carrier stored in its built-in radius (half the paved width at that point), so callers that
read or write a radius keep working unchanged and keep meaning the same thing.
"""
import bpy

_rs = None


def rs():
    """Lazy `lib/road_stack` import -- the same deferred-import idiom `lane_export.ik()` uses, so
    this module stays importable before `blender/lib` is on `sys.path`."""
    global _rs
    if _rs is None:
        import road_stack as _mod
        _rs = _mod
    return _rs


def is_spine(obj):
    """True if `obj` is a piece spine of EITHER carrier kind. Use this in place of a bare
    `obj.type == 'CURVE'` wherever the question is "is this a road spine" -- a mesh-carried spine
    answers no to the type check while being exactly what the caller wanted."""
    if obj is None:
        return False
    if obj.type == 'CURVE':
        return bool(obj.data.splines)
    if obj.type == 'MESH':
        return any(m.type == 'NODES' and m.node_group
                   and m.node_group.name == "GN_SpineCurve" for m in obj.modifiers)
    return False


def is_stack_carrier(obj):
    """True only for the MESH carrier -- for the few places that genuinely need to know which one
    they have (writing per-vertex attributes, rebuilding the modifier stack)."""
    return obj is not None and obj.type == 'MESH' and is_spine(obj)


class _PointCo(object):
    """A WRITE-THROUGH, 4-component stand-in for a `SplinePoint.co`, backed by a mesh vertex.

    Why not just hand back a `Vector`? Because a `SplinePoint.co` is LIVE -- `pt.co.x += 5` moves
    the road -- while a freshly-built `Vector((...))` is a copy, so the same line would compute a
    new x, store it in a temporary, and throw it away. Silent data loss in an adapter whose entire
    job is to be indistinguishable from the thing it replaces is the worst possible failure mode:
    every call site keeps working except the ones that mutate in place, and those go quiet rather
    than loud.

    The 4th component is real and read (`live_edit` preserves `p.co[3]` across whole-tuple writes),
    even though a POLY point's `w` is always 1.0 here -- so this presents 4, not 3. Vector maths on
    `.co` is deliberately NOT provided: nothing does it (`.x`, `.y`, `.copy()` and indexing are the
    entire surface in use), and offering half of `Vector`'s API would invite the next silent gap."""

    __slots__ = ("_v",)

    def __init__(self, vertex_co):
        self._v = vertex_co        # the live `MeshVertex.co` Vector -- writes go straight through

    def __getitem__(self, i):
        return 1.0 if i == 3 else self._v[i]

    def __setitem__(self, i, value):
        if i != 3:                 # w is structural, not data -- a POLY point is always 1.0
            self._v[i] = value

    def __len__(self):
        return 4

    def __iter__(self):
        return iter((self._v.x, self._v.y, self._v.z, 1.0))

    def __repr__(self):
        return "<spine point (%.4f, %.4f, %.4f, 1.0)>" % (self._v.x, self._v.y, self._v.z)

    @property
    def x(self):
        return self._v.x

    @x.setter
    def x(self, value):
        self._v.x = value

    @property
    def y(self):
        return self._v.y

    @y.setter
    def y(self, value):
        self._v.y = value

    @property
    def z(self):
        return self._v.z

    @z.setter
    def z(self, value):
        self._v.z = value

    @property
    def w(self):
        return 1.0

    def copy(self):
        from mathutils import Vector
        return Vector((self._v.x, self._v.y, self._v.z, 1.0))

    def to_3d(self):
        return self._v.copy()


class _MeshPoint(object):
    """A `SplinePoint`-shaped view of one mesh vertex: 4-component `.co` (w pinned to 1.0, which is
    what every `road_spine` POLY point carried anyway) and `.radius` backed by `rka_halfw`."""

    __slots__ = ("_me", "_i")

    def __init__(self, me, i):
        self._me = me
        self._i = i

    @property
    def co(self):
        return _PointCo(self._me.vertices[self._i].co)

    @co.setter
    def co(self, value):
        self._me.vertices[self._i].co = (value[0], value[1], value[2])

    @property
    def radius(self):
        attr = self._me.attributes.get(rs().ATTR_HALFW)
        return attr.data[self._i].value if attr is not None else 1.0

    @radius.setter
    def radius(self, value):
        attr = self._me.attributes.get(rs().ATTR_HALFW)
        if attr is None:
            attr = self._me.attributes.new(name=rs().ATTR_HALFW, type='FLOAT', domain='POINT')
        attr.data[self._i].value = float(value)


def points(spine_obj):
    """The spine's control points in order, as `.co`/`.radius` objects.

    Curve carrier -> the real `SplinePoint`s (writes go straight through, no sync step).
    Mesh carrier  -> `_MeshPoint` proxies over the vertices, also writing straight through.

    Mesh vertices are returned in INDEX order, which is the order `road_stack.make_spine_mesh`
    creates them in and the order its edges chain them in -- so index order IS path order for any
    spine this addon builds."""
    if spine_obj is None:
        return []
    if spine_obj.type == 'CURVE':
        return spine_obj.data.splines[0].points if spine_obj.data.splines else []
    me = spine_obj.data
    return [_MeshPoint(me, i) for i in range(len(me.vertices))]


def has_points(spine_obj):
    if spine_obj is None:
        return False
    if spine_obj.type == 'CURVE':
        return bool(spine_obj.data.splines) and bool(spine_obj.data.splines[0].points)
    return spine_obj.type == 'MESH' and len(spine_obj.data.vertices) > 0


def world_points(spine_obj):
    """World-space `(x, y, z)` tuples -- the RAW control points, with NO depsgraph/modifier
    evaluation. Evaluating would return the swept pavement mesh instead of the centreline (see
    `ops_segment._sample_curve_world_points`'s docstring for that trap)."""
    if not has_points(spine_obj):
        return []
    from mathutils import Vector
    mat = spine_obj.matrix_world
    return [tuple(mat @ Vector((p.co[0], p.co[1], p.co[2]))) for p in points(spine_obj)]


def append_point(spine_obj):
    """Grow the spine by ONE control point (value-initialised from the existing last point) and
    return the refreshed point list. Callers then rewrite the whole list -- which is what
    `live_edit._ensure_bend_room` already does, because Blender's curve API only appends and never
    inserts, so an insertion is always "grow by one, then shift the values along"."""
    if spine_obj.type == 'CURVE':
        sp = spine_obj.data.splines[0]
        sp.points.add(1)
        return sp.points
    me = spine_obj.data
    n = len(me.vertices)
    last = me.vertices[n - 1].co.copy() if n else None
    me.vertices.add(1)
    if last is not None:
        me.vertices[n].co = last
    me.edges.add(1)
    me.edges[len(me.edges) - 1].vertices = (n - 1, n)
    me.update()
    return points(spine_obj)
