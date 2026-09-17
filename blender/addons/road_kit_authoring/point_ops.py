"""Operators -- the HEADLESS PIPELINE's gestures (ROAD_POINT_GRAPH.md 4.1), retired to that job by
PLAN.md 3.1 B9 (2026-09-14).

Authoring moved to the Godot editor (`addons/road_kit/`), whose record gestures live in pure
`point_record_ops.py`. What stays here is what a Blender tool still calls: the island seeder
(`seed_district_roads.py`: New Road, Extend Road, Connect, Make Intersection), the builds
(`build_island_base.py`: Auto Setback, Load/Save Record, Export Lanekit, Link
Road Kit) and the helpers `point_build` uses (`sync_facings`, `recentre_all_junctions`). The panels,
the viewport overlay, the flow-preview drawing and the live rebuild are deleted; the interactive
repair and ramp operators (Insert/Merge/Split/Tidy/Renumber/Repair/Make Ramp/Branch Ramp/...) are
deleted in favour of `point_record_ops`.

Every operator in here is a thin shell: it edits the AUTHORED Empties and their `rka_pt` data and
then stops. It never builds geometry, never computes a lateral offset, and never touches
`ROAD_MANAGER_GEN`. That separation is what makes step 2 testable at all -- the whole scene below
is buildable, and gate-checkable, before a single Geometry Nodes socket exists.

Headless discipline, paid for once already: `--background` NEVER calls an operator's `invoke()`,
and `INVOKE_DEFAULT` degrades silently to `EXEC_DEFAULT` with property defaults. So no operator in
this file may compute anything essential in `invoke()`; everything an operator needs is an operator
PROPERTY, and the panel is what fills those in interactively.
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy.types import Operator
from mathutils import Vector

from . import point_model as pm
from . import point_profile as pp
from . import point_solve as psolve
from . import point_validate as pv

import lane_profile as lp


# ------------------------------------------------------------------------------- scene plumbing

def _ensure_collection(name, parent=None):
    """Local-only lookup, then create. A linked library carries same-named collections, so an
    unqualified `bpy.data.collections[name]` can hand back a NEIGHBOUR district's ROAD_MANAGER --
    and a build would then wipe geometry it does not own."""
    c = pm._local(bpy.data.collections, name)
    if c is None:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    elif parent is not None and c.name not in {x.name for x in parent.children}:
        try:
            bpy.context.scene.collection.children.unlink(c)
        except Exception:
            pass
        parent.children.link(c)
    return c


def ensure_roots():
    root = _ensure_collection(pm.ROAD_MANAGER)
    _ensure_collection(pm.JUNCTIONS, root)
    _ensure_collection(pm.ROAD_MANAGER_GEN)
    return root


def road_collection(name):
    return _ensure_collection(name, ensure_roots())


def point_name(coll, i):
    """`<road>_p000`. The road prefix is NOT decoration: Blender object names are GLOBAL, so an
    unprefixed `p000` in a second road becomes `p000.001` and a third `p000.005` -- and since the
    chain order IS the name order, a road's points then sort into an order nobody authored. The
    prefix also makes the outliner legible, which is half of why this rewrite exists."""
    return "%s_p%03d" % (coll.name, i)


def _next_point_name(coll):
    used = {o.name for o in bpy.data.objects}
    i = 0
    while point_name(coll, i) in used:
        i += 1
    return point_name(coll, i)


def new_point(coll, pos, facing=None, **fields):
    """One authored road point. The transform IS the road frame at that station, so it needs no
    extra properties (1.2): position is the station, local +Y is travel direction, roll is banking.

    `ARROWS`, not `SINGLE_ARROW`: a single-arrow Empty draws along +Z, so it would show the artist
    an axis the model never reads while hiding the one it does. Rotating a point only makes sense
    if you can see which way +Y points."""
    obj = bpy.data.objects.new(_next_point_name(coll), None)
    obj.empty_display_type = 'ARROWS'
    obj.empty_display_size = 4.0
    obj.location = Vector(pos)
    coll.objects.link(obj)
    obj.rka_pt.is_point = True
    obj.rka_pt.uid = pm.new_uid()
    for k, v in fields.items():
        setattr(obj.rka_pt, k, v)
    # BORN FACING THE ROAD. A fresh Empty has identity rotation, so its +Y is world +Y -- on any
    # road that does not happen to run north the arrow the artist is looking at was a LIE, and
    # switching that point to MANUAL would snap the road to face north. Stamping the baseline in
    # the same breath is what makes a later hand rotation detectable (`point_model.was_rotated`).
    #
    # NOT `pm.face_matrix` and NOT `pm.facing_of`: both read `matrix_world`, which is STALE until
    # the next depsgraph evaluation -- on an object created microseconds ago it is still identity,
    # so face_matrix would write the station back to the world origin. Rotation and baseline are
    # both set from the vector we already hold.
    d = Vector(facing) if facing is not None else Vector((0.0, 1.0, 0.0))
    d = d.normalized() if d.length > 1e-9 else Vector((0.0, 1.0, 0.0))
    obj.rotation_euler = d.to_track_quat('Y', 'Z').to_euler()
    pm.stamp_baseline(obj, d)
    return obj


def points_in(coll):
    return sorted(pm.point_objects(coll), key=lambda o: o.name)


def collection_of(obj):
    for c in pm.road_collections():
        if obj.name in c.objects:
            return c
    return None


def link_objects(a, b, type=pm.LINK_SEGMENT, symmetric=None):
    """Writes the link on the OBJECTS. Two points carry at most ONE link between them, so this
    RETYPES an existing one rather than adding a second -- an AUX link and a SEGMENT link between
    the same pair would be contradictory. Retyping silently is the sharp edge; `Connect Selected`
    is where the artist is told, which is why this helper stays blunt and the operator does not."""
    if symmetric is None:
        symmetric = (type != pm.LINK_AUX)

    def one(src, dst):
        for l in src.rka_pt.links:
            if l.target is dst:
                l.type = type
                return
        l = src.rka_pt.links.add()
        l.target = dst
        l.type = type

    one(a, b)
    if symmetric:
        one(b, a)


def selected_points(context):
    return [o for o in context.selected_objects
            if getattr(o, "rka_pt", None) is not None and o.rka_pt.is_point]


def is_point(obj):
    return getattr(obj, "rka_pt", None) is not None and obj.rka_pt.is_point


def resolve_pair(context, target_name=""):
    """`(a, b)` for a two-point gesture, where **`a` is always the ACTIVE point**.

    The order is not cosmetic. `AUX` is a DIRECTED link -- mainline -> ramp -- and this used to be
    `a, b = selected_points(context)`, i.e. `context.selected_objects` order, which is arbitrary.
    So the Aux button was a coin flip that disagreed with the panel's own hint ("active =
    mainline") half the time. Anchoring on the active object is also what makes the gesture
    describable in one sentence: whatever you clicked LAST is `a`.

    `target_name` is the panel's "Connect To" field: name one point and the selection stops
    mattering at all, which is the answer to "it is hard to select two points"."""
    act = context.active_object
    act = act if (act is not None and is_point(act)) else None
    if target_name:
        b = bpy.data.objects.get(target_name)
        if act is None or b is None or not is_point(b):
            return None, None
        return act, b
    sel = selected_points(context)
    if len(sel) != 2:
        return None, None
    if act is not None and act in sel:
        other = sel[0] if sel[1] is act else sel[1]
        return act, other
    return sel[0], sel[1]


def declares_aux(obj):
    return obj.rka_pt.aux_fwd > 0 or obj.rka_pt.aux_bwd > 0


def resolve_aux_pair(a, b):
    """`(mainline, ramp)` for an AUX gesture, or `(None, None)` when neither reading works.

    AUX IS DIRECTED, BUT WHICH POINT IS THE MAINLINE IS A FACT ABOUT THE TWO POINTS -- not about
    which one you happened to click last. It used to be the second: `a` (the active point) had to
    be the mainline, so `Aux` on a ramp point with the mainline named in `Connect To` simply
    refused, and the only way to wire a ramp that MERGES into a road was to select it from the
    other end. Since an entrance ramp reads naturally in exactly that order (ramp joins road),
    half the ramps in a network could not be authored with the gesture the panel offers.

    So the two readings are scored and the better one wins. What makes a point the mainline is
    that it declares an aux slot for the ramp to land in; what makes one the ramp is that it is a
    one-way road and/or already carries a ramp role. The active point only breaks a genuine tie,
    which keeps the documented `active = mainline` behaviour true wherever it was ever true."""
    def score(main, ramp):
        s = 0
        if declares_aux(main):
            s += 3
        if pm.is_ramp_role(ramp.rka_pt.role):
            s += 2
        if pm.is_ramp_role(main.rka_pt.role):
            s -= 2
        if declares_aux(ramp):
            s -= 1
        # A ramp is one-way BY CONSTRUCTION (2.1) -- `Make Ramp` writes `lanes_bwd = 0`.
        if ramp.rka_pt.lanes_bwd == 0 or ramp.rka_pt.lanes_fwd == 0:
            s += 1
        if main.rka_pt.lanes_bwd == 0 or main.rka_pt.lanes_fwd == 0:
            s -= 1
        return s
    sa, sb = score(a, b), score(b, a)
    if sa <= 0 and sb <= 0:
        return None, None
    return (a, b) if sa >= sb else (b, a)


def sync_facings(scene=None, net=None):
    """Keep every AUTO arrow pointing along its road, and turn a hand ROTATION into authored shape.

    `(promoted, refaced)` -- both lists of object names.

    TWO HALVES, AND THE ORDER BETWEEN THEM IS THE WHOLE THING. Promotion is tested FIRST, or the
    re-face would overwrite the very rotation it is meant to notice and the gesture would be
    unusable. After that, every point the tool still owns is re-faced to the chain tangent and its
    baseline re-stamped, so the arrow the artist sees is the direction the solver actually uses --
    and so the NEXT rotation is measurable against a known zero.

    A point in SHARP or MANUAL is never touched: those modes mean the artist owns the facing."""
    scene = scene or bpy.context.scene
    net = net if net is not None else pm.read_network(scene)
    want = pp.chain_facings(net)
    promoted, refaced = [], []
    for coll in pm.road_collections(scene):
        for o in points_in(coll):
            pt = o.rka_pt
            if pt.tangent_mode != pm.AUTO:
                continue
            if pm.was_rotated(o):
                pt.tangent_mode = pm.MANUAL          # the rotation IS the gesture
                promoted.append(o.name)
                continue
            d = want.get(pt.uid)
            if d is None:
                continue
            pm.face_matrix(o, d)
            pm.stamp_baseline(o, d)
            refaced.append(o.name)
    return promoted, refaced


# ------------------------------------------------------------------------------- corridor

class RKA_OT_new_road(Operator):
    """Create a road collection and its first point"""
    bl_idname = "rka.new_road"
    bl_label = "New Road"
    bl_options = {'REGISTER', 'UNDO'}

    name: StringProperty(default="road_new")
    x: FloatProperty(default=0.0)
    y: FloatProperty(default=0.0)
    z: FloatProperty(default=0.0)
    lanes_fwd: bpy.props.IntProperty(default=2, min=0)
    lanes_bwd: bpy.props.IntProperty(default=2, min=0)
    lane_width: FloatProperty(default=3.5)
    median_width: FloatProperty(default=1.0)
    road_class: StringProperty(default="street")
    design_speed: FloatProperty(default=50.0)

    def execute(self, context):
        coll = road_collection(self.name)
        coll.rka_road.is_road = True
        coll.rka_road.name = coll.name
        coll.rka_road.road_class = self.road_class
        # The ROAD's base profile (1.2a). A station in INHERIT mode takes this and applies only
        # the four genuine deltas, so changing a 20-station road's lane width is ONE edit.
        b = coll.rka_road.base
        b.lanes_fwd, b.lanes_bwd = self.lanes_fwd, self.lanes_bwd
        b.lane_width, b.median_width = self.lane_width, self.median_width
        b.design_speed = self.design_speed
        p = new_point(coll, (self.x, self.y, self.z),
                      lanes_fwd=self.lanes_fwd, lanes_bwd=self.lanes_bwd)
        context.view_layer.objects.active = p
        self.report({'INFO'}, "%s created" % coll.name)
        return {'FINISHED'}


class RKA_OT_extend_road(Operator):
    """Add a point beyond the road's end, linked SEGMENT -- the E-key loop.

    EITHER END. The chain order IS the object-name order and FWD is increasing index, so a new
    point can only ever be born at one end of the names -- and this used to be the LAST one
    unconditionally, whichever point was active. Extending from `..._p000` therefore produced a
    point that was:

    * placed in the FORWARD direction, i.e. back down the road it was supposed to grow away from
      (with only the head's own arrow to go on, `prev` was None and the +Y facing is the way the
      road already runs); and
    * named `..._p00N`, i.e. sorted to the far end of a road it sits at the START of, so the chain
      order disagreed with the geometry and the link, and Build reported `chain_unlinked` on a
      pair of points nobody had touched.

    Both halves are the same fix: grow AWAY from the chain, and renumber so the name order still
    matches the road. Extending the head prepends; extending the tail appends, exactly as before.
    An interior point is refused by name rather than guessed at -- "extend" has no meaning in the
    middle of a chain, and picking an end for the artist is how a road silently grows the wrong
    way."""
    bl_idname = "rka.extend_road"
    bl_label = "Extend Road"
    bl_options = {'REGISTER', 'UNDO'}

    distance: FloatProperty(default=100.0)
    dx: FloatProperty(default=0.0)
    dy: FloatProperty(default=0.0)
    dz: FloatProperty(default=0.0)
    use_delta: BoolProperty(default=False,
                            description="Use dx/dy/dz verbatim instead of the chain tangent")

    def execute(self, context):
        obj = context.active_object
        coll = collection_of(obj) if obj else None
        if coll is None:
            self.report({'ERROR'}, "no active road point")
            return {'CANCELLED'}
        pts = points_in(coll)
        i = pts.index(obj)
        # Which END is this, in NAME order? That is the only order the chain has.
        at_head, at_tail = (i == 0), (i == len(pts) - 1)
        if not (at_head or at_tail):
            self.report({'ERROR'},
                        "%s is in the middle of %s -- extend from an end (%s or %s), or "
                        "Insert Point to add a station between two, or Branch Ramp Here to "
                        "start a new road leaving this one"
                        % (obj.name, coll.name, pts[0].name, pts[-1].name))
            return {'CANCELLED'}
        # The neighbour we are growing AWAY from. At the tail that is the point before; at the
        # head it is the point after, and the sign flip is the whole of the head fix.
        nb = pts[i - 1] if at_tail and i > 0 else (pts[1] if at_head and len(pts) > 1 else None)
        if self.use_delta:
            off = Vector((self.dx, self.dy, self.dz))
        else:
            # Along the chain tangent, so extending a curving road keeps curving. With one point
            # there is no chord yet, so the Empty's own +Y is the direction -- which is exactly
            # what the arrow in the viewport is showing the artist.
            if nb is not None:
                d = (obj.matrix_world.translation - nb.matrix_world.translation)
            else:
                d = obj.matrix_world.to_quaternion() @ Vector((0.0, 1.0, 0.0))
            d = d.normalized() if d.length > 1e-9 else Vector((0.0, 1.0, 0.0))
            off = d * self.distance
        # +Y IS TRAVEL, and travel runs with increasing index. A point prepended at the head faces
        # back INTO the road (toward the old p000); one appended at the tail faces on out.
        facing = off if at_tail else -off
        p = new_point(coll, obj.matrix_world.translation + off, facing=facing)
        for n in pm.DELTA_FIELDS:
            setattr(p.rka_pt, n, getattr(obj.rka_pt, n))
        link_objects(obj, p, pm.LINK_SEGMENT)
        if at_head and len(pts) > 1:
            # `_next_point_name` can only ever hand out the NEXT free index, so a head extension is
            # always born misfiled. Renaming is safe by construction: identity is the uid.
            _renumber(coll, inserted=p, at=0)
        # ...and the point we grew FROM. Extending a one-point road turns the start station into a
        # station with a chain direction, and until this ran its arrow still pointed at world +Y.
        sync_facings(context.scene)
        for o in context.selected_objects:
            o.select_set(False)
        p.select_set(True)
        context.view_layer.objects.active = p
        return {'FINISHED'}


def _renumber(coll, after=None, inserted=None, before=None, at=None):
    """Rename every point so the chain order IS the name order. Renaming is safe: a uid survives
    a rename by construction, which is precisely why identity is a uid and not a name.

    `after` puts `inserted` straight after that point (Insert Point); `at` puts it at an absolute
    index (Extend Road prepending to the head, `at=0`).

    CALLER RULE, because object names are GLOBAL and this cannot see past its own collection: when
    points MOVE between collections, renumber the DESTINATION first. The two passes below only
    protect against collisions WITHIN `pts`; a point that has left this collection but not yet been
    renamed still holds a `<coll>_pNNN` name, and pass two then gets `<coll>_pNNN.001` back from
    Blender -- a point whose name sorts outside the chain it belongs to, which is the one thing the
    name order is supposed to guarantee."""
    pts = points_in(coll)
    if inserted is not None and (after is not None or at is not None):
        pts.remove(inserted)
        pts.insert(pts.index(after) + 1 if after is not None
                   else max(0, min(int(at), len(pts))), inserted)
    # Two passes: renaming straight into the target names would collide with the points still
    # holding them and Blender would suffix them instead. Renaming is safe -- a uid survives a
    # rename by construction, which is precisely why identity is a uid and not a name.
    for i, o in enumerate(pts):
        o.name = "__tmp_%s_%03d" % (coll.name, i)
    for i, o in enumerate(pts):
        o.name = point_name(coll, i)
    return pts


#: The pad handle's object-name prefix. One owner: `_junction_name` allocates them and
#: `complete_junction_cliques` recognises them.
JCT_PREFIX = "JCT_"


# ------------------------------------------------------------------------------- connections

class RKA_OT_connect_selected(Operator):
    """Link two selected points, validating the roles BEFORE writing"""
    bl_idname = "rka.connect_selected"
    bl_label = "Connect Selected"
    bl_options = {'REGISTER', 'UNDO'}

    type: EnumProperty(items=[(t, t.title(), "") for t in pm.LINK_TYPES], default=pm.LINK_SEGMENT)
    #: Optional: connect the ACTIVE point to this named one instead of to the other selected one.
    #: Selecting exactly two points in a dense network is fiddly; naming one is not.
    target: StringProperty(default="")

    def execute(self, context):
        a, b = resolve_pair(context, self.target)
        if a is None:
            self.report({'ERROR'}, "select exactly 2 points, or pick a target in the panel")
            return {'CANCELLED'}
        if a is b:
            return {'CANCELLED'}
        if self.type == pm.LINK_JUNCTION:
            for o in (a, b):
                o.rka_pt.role = pm.INTERSECTION
        elif self.type == pm.LINK_AUX:
            # EITHER ORDER. `resolve_aux_pair` decides which of the two is the mainline from what
            # they declare, so wiring a ramp that merges INTO a road (select the ramp, name the
            # road) works exactly as well as one that leaves it. The link itself stays directed.
            main, ramp = resolve_aux_pair(a, b)
            if main is None:
                self.report({'ERROR'}, "neither %s nor %s declares an aux lane -- set aux_fwd (or "
                                       "aux_bwd) on the MAINLINE point first, then connect"
                                       % (a.name, b.name))
                return {'CANCELLED'}
            if not declares_aux(main):
                self.report({'ERROR'}, "%s declares no aux lane for the ramp to align to"
                            % main.name)
                return {'CANCELLED'}
            # ONE ramp role. The direction (exit or entrance) is derived at export time from the
            # ramp's own chain, so there is nothing here for the artist to get the wrong way round.
            if not pm.is_ramp_role(ramp.rka_pt.role):
                ramp.rka_pt.role = pm.RAMP
            a, b = main, ramp
        # Validated BEFORE writing, and AFTER the AUX orientation is resolved, or the warning would
        # name the pair the artist typed rather than the one being written. The model's `link_to`
        # retypes an existing link silently, which is right for the data layer and wrong as a
        # gesture -- this is where the artist is told.
        existing = next((l for l in a.rka_pt.links if l.target is b), None)
        if existing is not None and existing.type != self.type:
            self.report({'WARNING'}, "retyping the existing %s link to %s"
                        % (existing.type, self.type))
        link_objects(a, b, self.type)
        self.report({'INFO'}, "%s: %s -> %s" % (self.type, a.name, b.name)
                    if self.type == pm.LINK_AUX
                    else "%s: %s <-> %s" % (self.type, a.name, b.name))
        return {'FINISHED'}


def _junction_name():
    used = {c.name for c in bpy.data.objects}
    i = 1
    while ((JCT_PREFIX + "%04d") % i) in used:
        i += 1
    return (JCT_PREFIX + "%04d") % i


def make_junction(context, points, fillet_radius=6.0):
    """N points -> one pad: the JCT_* parent at the centroid, the roles, and the FULL clique.

    Extracted so `Make Intersection` and the sample-network builder cannot disagree about what a
    junction is. Everything subtle about it lives here once: the parent's locked transform, the
    stale-`matrix_world` ordering, `matrix_parent_inverse`, and writing the complete clique."""
    centre = Vector((0.0, 0.0, 0.0))
    for o in points:
        centre += o.matrix_world.translation
    centre /= len(points)

    jct = bpy.data.objects.new(_junction_name(), None)
    jct.empty_display_type = 'SPHERE'
    jct.empty_display_size = 3.0
    jct.location = centre
    # SCALE IS LOCKED, and so is rotation OUT OF PLANE -- but Z is not.
    #
    # Both used to be locked, under one justification: "a mouth's width is its lane count -- not
    # something a transform may quietly restate." That is exactly right about SCALE and does not
    # transfer to rotation. A mouth's DIRECTION is already a transform: the authored facing
    # (`point_model.station_axis`), which 8f made the single owner of an arm's direction precisely
    # so that rotating a mouth turns its cap, its fillets and its turn paths. Turning the whole
    # crossing is that same gesture one level up, and the model already supports it -- `facing_of`
    # reads `matrix_world`, so all N arms turn together and every derived thing follows with no new
    # code. X/Y stay locked because the pad is solved in plan: tilting it has no meaning.
    jct.lock_rotation = (True, True, False)
    jct.lock_scale = (True, True, True)
    _ensure_collection(pm.JUNCTIONS, ensure_roots()).objects.link(jct)
    # `matrix_world` is STALE until the depsgraph updates, and the next lines read the parent's.
    # Never read a world position in the same pass that created or moved its parent.
    context.view_layer.update()

    for o in points:
        o.rka_pt.role = pm.INTERSECTION
        o.rka_pt.fillet_radius = fillet_radius
        world = o.matrix_world.copy()
        o.parent = jct
        # `obj.parent = x` does NOT set this, and `parent_set(keep_transform=True)` needs a
        # context override headless. Without it every mouth jumps by the parent's offset.
        o.matrix_parent_inverse = jct.matrix_world.inverted()
        o.matrix_world = world
    # The FULL clique, written here once. A component that is not a clique builds one pad as two
    # overlapping ones, and the gate reports it -- so the gesture must never leave one out.
    for i, a in enumerate(points):
        for b in points[i + 1:]:
            link_objects(a, b, pm.LINK_JUNCTION)
    # A no-op right here -- the Empty was just placed at that centroid. It runs anyway so that ONE
    # function is the answer to "where does the handle sit", rather than this line being a second
    # copy of it that the two can drift apart from. Which is exactly what happened.
    recentre_junction(jct, context)
    return jct


def junction_centre(jct):
    """The live centroid of a `JCT_*`'s mouths, in world space, or None if it has none."""
    kids = [c for c in jct.children if is_point(c)]
    if not kids:
        return None
    acc = Vector((0.0, 0.0, 0.0))
    for c in kids:
        acc += c.matrix_world.translation
    return acc / len(kids)


def junction_drift(jct):
    """How far the handle currently sits from the centre it should be on, in metres."""
    centre = junction_centre(jct)
    return 0.0 if centre is None else (jct.matrix_world.translation - centre).length



def recentre_junction(jct, context=None):
    """Move the `JCT_*` Empty's origin onto the LIVE centre of its mouths, moving no mouth.

    THE HANDLE MUST SIT WHERE THE THING IT HANDLES IS. `make_junction` set this origin to the
    mouths' centroid once, at creation, and nothing ever re-derived it -- while
    `point_solve.JunctionSolve.centre` recomputes that centroid every solve and is what the pad,
    the fillets, the turn paths and the export all use. Two owners of "where is this junction", one
    of them frozen. Measured on the sample network: dragging a single mouth 42 m to widen its
    approach left the Empty **10.44 m** from the real centre, so G and R pivoted around a point
    with nothing there -- the artist's report, exactly. `Auto Setback` makes it worse by design,
    since it moves every unlocked mouth, so the first thing the recommended workflow does after
    `Make Intersection` slides the centre out from under the handle.

    No geometry moves: the solve never reads this Empty's position. Only the grip changes.

    Moving a parent moves its children, so each mouth's world transform is captured BEFORE and
    restored after -- the same dance `make_junction` performs when it parents, and with the same
    trap: `matrix_world` is stale until the depsgraph updates, so the parent inverse must be taken
    after `view_layer.update()` and never in the same breath as the move.

    Returns the distance the handle travelled."""
    kids = [c for c in jct.children if is_point(c)]
    centre = junction_centre(jct)
    if centre is None:
        return 0.0
    moved = (jct.matrix_world.translation - centre).length
    if moved <= 1e-6:
        return 0.0
    worlds = [c.matrix_world.copy() for c in kids]
    jct.matrix_world.translation = centre
    view = getattr(context or bpy.context, "view_layer", None)
    if view is not None:
        view.update()
    for c, w in zip(kids, worlds):
        c.matrix_parent_inverse = jct.matrix_world.inverted()
        c.matrix_world = w
    return moved


def recentre_all_junctions(context=None):
    """Every `JCT_*` in the file. `(count moved, worst drift)`."""
    n, worst = 0, 0.0
    for o in list(bpy.data.objects):
        if o.parent is None and o.name.startswith("JCT_") and o.type == 'EMPTY':
            d = recentre_junction(o, context)
            if d > 1e-6:
                n += 1
                worst = max(worst, d)
    return n, worst


class RKA_OT_make_intersection(Operator):
    """N selected points -> one pad: the full JUNCTION clique plus a JCT_* parent at the centroid"""
    bl_idname = "rka.make_intersection"
    bl_label = "Make Intersection"
    bl_options = {'REGISTER', 'UNDO'}

    fillet_radius: FloatProperty(default=6.0)

    def execute(self, context):
        sel = selected_points(context)
        if len(sel) < 2:
            self.report({'ERROR'}, "select at least 2 points")
            return {'CANCELLED'}
        jct = make_junction(context, sel, self.fillet_radius)
        context.view_layer.objects.active = jct
        self.report({'INFO'}, "%s: %d arms" % (jct.name, len(sel)))
        return {'FINISHED'}


# ------------------------------------------------------------------------------- the record

def default_record_path():
    """`<stem>.roads.json` beside the .blend -- the same sibling-sidecar convention
    `.lanekit.json` and `.seam.json` already use."""
    import os
    blend = bpy.data.filepath
    if not blend:
        return ""
    return os.path.splitext(blend)[0] + ".roads.json"


def apply_network(net):
    """NetworkData -> Empties. The record is the source of truth and this is the projection, so it
    REPLACES what is in ROAD_MANAGER rather than merging into it -- a merge would silently keep an
    object the record no longer mentions, which is the exact drift 1.2c exists to prevent."""
    for coll in pm.road_collections():
        for o in points_in(coll):
            bpy.data.objects.remove(o, do_unlink=True)
    made = {}
    for name in sorted(net.roads):
        r = net.roads[name]
        coll = road_collection(name)
        coll.rka_road.is_road = True
        for n, _k, _d in pm.ROAD_FIELDS:
            setattr(coll.rka_road, n, getattr(r, n))
        coll.rka_road.name = coll.name
        for n, _k, _d in pm.POINT_FIELDS:
            setattr(coll.rka_road.base, n, getattr(r.base, n))
        for uid in r.points:
            p = net.points.get(uid)
            if p is None:
                continue
            obj = new_point(coll, p.pos)
            pm.write_point(obj, p, move=True)
            made[uid] = obj
    for uid, obj in made.items():
        for l in net.points[uid].links:
            if l.target in made:
                link_objects(obj, made[l.target], l.type, symmetric=False)
    return made


class RKA_OT_save_record(Operator):
    """Write the authored roads to a git-diffable <stem>.roads.json"""
    bl_idname = "rka.save_record"
    bl_label = "Save Road Record"
    bl_options = {'REGISTER'}

    filepath: StringProperty(default="", subtype='FILE_PATH')

    def execute(self, context):
        path = self.filepath or default_record_path()
        if not path:
            self.report({'ERROR'}, "save the .blend first, or pass filepath")
            return {'CANCELLED'}
        net = pm.read_network()
        pm.save_network(net, path)
        self.report({'INFO'}, "%d road(s), %d point(s) -> %s"
                    % (len(net.roads), len(net.points), path))
        return {'FINISHED'}


class RKA_OT_load_record(Operator):
    """Rebuild the Empties from <stem>.roads.json -- the record is the source of truth"""
    bl_idname = "rka.load_record"
    bl_label = "Load Road Record"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: StringProperty(default="", subtype='FILE_PATH')

    def execute(self, context):
        path = self.filepath or default_record_path()
        if not path:
            self.report({'ERROR'}, "save the .blend first, or pass filepath")
            return {'CANCELLED'}
        net = pm.load_network(path)
        made = apply_network(net)
        self.report({'INFO'}, "%d point(s) from %s" % (len(made), path))
        return {'FINISHED'}


class RKA_OT_export_lanekit(Operator):
    """Write the Godot `.lanekit.json` v2 sidecar. Refuses if the gate is not green"""
    bl_idname = "rka.export_lanekit"
    bl_label = "Export .lanekit (v2)"
    bl_options = {'REGISTER'}

    filepath: StringProperty(default="", subtype='FILE_PATH')
    force: BoolProperty(default=False, description="Export even with gate errors")

    def execute(self, context):
        import os
        from . import point_export as pe
        path = self.filepath
        if not path:
            blend = bpy.data.filepath
            if not blend:
                self.report({'ERROR'}, "save the .blend first, or pass filepath")
                return {'CANCELLED'}
            path = os.path.splitext(blend)[0] + ".lanekit.json"
        net = pm.read_network()
        errs = pv.errors(pv.validate(net))
        if errs and not self.force:
            # A build that fails the connectivity check is a FAILED build (5). Exporting anyway
            # ships a network whose defects only show up as cars falling through the world.
            for f in errs[:5]:
                self.report({'ERROR'}, pv.describe(f, net.labels))
            self.report({'ERROR'}, "%d gate error(s) -- not exporting" % len(errs))
            return {'CANCELLED'}
        doc = pe.write(net, path)
        self.report({'INFO'}, "%d lane(s), %d junction(s) -> %s"
                    % (len(doc["lanes"]), len(doc["junctions"]), path))
        return {'FINISHED'}


class RKA_OT_auto_setback(Operator):
    """Solve the whole clique's stop-line distances and move every UNLOCKED mouth there"""
    bl_idname = "rka.auto_setback"
    bl_label = "Auto Setback"
    bl_options = {'REGISTER', 'UNDO'}

    margin: FloatProperty(name="Margin", default=2.0, min=0.0,
                          description="How far a turn may reach outside the pad before the "
                                      "solve grows the setback")

    def execute(self, context):
        net = pm.read_network()
        by_uid = {}
        for coll in pm.road_collections():
            for o in points_in(coll):
                by_uid[o.rka_pt.uid] = o
        sel = {o.rka_pt.uid for o in selected_points(context)}
        moved = seen = 0
        for uids in net.junction_cliques():
            # WHOLE-CLIQUE, always. The solver's couplings do not survive being applied one mouth
            # at a time -- it takes the max over both corners at a node and clamps per chain
            # jointly. Drag one mouth in isolation and the neighbouring fillet silently stops
            # being tangent. A selection PICKS a clique; it never narrows one.
            if sel and not (sel & set(uids)):
                continue
            for uid, _old, _new in psolve.auto_setback(net, uids, self.margin):
                obj = by_uid.get(uid)
                if obj is None:
                    continue
                pos = net.points[uid].pos
                obj.matrix_world.translation = Vector(pos)
                moved += 1
            for uid in uids:
                if uid in by_uid:
                    by_uid[uid].rka_pt.setback_solved = net.points[uid].setback_solved
            seen += 1
        if not seen:
            self.report({'WARNING'}, "no junction selected -- select a mouth, or nothing, to "
                                     "solve every pad")
            return {'CANCELLED'}
        # THIS operator is the biggest single source of handle drift -- it moves every unlocked
        # mouth, which is exactly what moves the centre out from under the `JCT_*` Empty. It has to
        # put the handle back on the centre it just created, or the recommended workflow
        # (Make Intersection, then Auto Setback) ships a wrong grip by default.
        recentre_all_junctions(context)
        # FINISHED even at zero, deliberately. This operator is what the pad findings tell the
        # artist to run, and a remedy that answers "moved 0 mouth(es)" AND reports CANCELLED reads
        # as "it did not work" when it means "they are already where I would put them".
        self.report({'INFO'}, "%d pad(s): moved %d mouth(es)%s"
                    % (seen, moved, "" if moved else " -- already at the solved setback"))
        return {'FINISHED'}


class RKA_OT_link_road_kit(Operator):
    """Library-link the profile asset kit into this file, so roads can name a section

    LINKED and not appended, deliberately: every district points at the one `road_kit.blend`, so
    editing a kerb section there restyles every road in the world that names it. Appending would
    make each district's copy drift"""
    bl_idname = "rka.link_road_kit"
    bl_label = "Link Road Kit"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import os
        from . import paths, point_style as pstyle
        if pstyle.kit_collection() is not None:
            self.report({'INFO'}, "%s is already in this file" % pstyle.KIT_COLLECTION)
            return {'FINISHED'}
        path = paths.ROAD_KIT_BLEND
        if not os.path.exists(path):
            self.report({'ERROR'}, "%s does not exist -- run blender/tools/build_road_kit.py"
                        % path)
            return {'CANCELLED'}
        with bpy.data.libraries.load(path, link=True) as (src, dst):
            if pstyle.KIT_COLLECTION not in src.collections:
                dst.collections = []
            else:
                dst.collections = [pstyle.KIT_COLLECTION]
        coll = pstyle.kit_collection()
        if coll is None:
            self.report({'ERROR'}, "%s holds no %s collection" % (path, pstyle.KIT_COLLECTION))
            return {'CANCELLED'}
        # Linked but NOT instanced into the scene: these are sections to sweep, not props to
        # place, and an Empty full of cross-sections standing at the origin is one more thing in
        # the viewport that looks like a mistake.
        self.report({'INFO'}, "%d profile section(s) linked from %s"
                    % (len(pstyle.kit_assets()), os.path.basename(path)))
        return {'FINISHED'}


CLASSES = (RKA_OT_new_road, RKA_OT_extend_road, RKA_OT_connect_selected,
           RKA_OT_make_intersection, RKA_OT_auto_setback, RKA_OT_save_record,
           RKA_OT_load_record, RKA_OT_export_lanekit, RKA_OT_link_road_kit)


def register():
    pm.register()
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
    pm.unregister()
