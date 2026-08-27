"""point_overlay.py -- the GPU overlay (4.3).

A NETWORK OF HUNDREDS OF POINTS IS ILLEGIBLE WITHOUT THIS. The previous model presented the world
as 1619 identical grey edges with no per-road identity and no viewport feedback of any authored
value -- so the only way to know what a piece of road was set to was to select it and read a
panel, one piece at a time. That is the defect this file exists to close, and it is also half of
`point_live`'s answer: the overlay is what follows a drag in real time, because a draw handler
needs no `bpy.data` write and is therefore always safe, even mid-modal.

WHAT IT DRAWS

    per road      the RESOLVED CENTRELINE -- the actual swept spine, tangents and all. It is what
                  makes rotating a point legible in real time: the read side promotes a rotated
                  point to MANUAL, so the spine bends under the R-drag with no rebuild at all
    per point     lane counts per direction, a travel arrow, an aux badge, the paved extent, and
                  an OVERRIDE glyph -- because a whole-profile INHERIT/OVERRIDE switch that the
                  artist cannot see is exactly the invisible state this rewrite exists to kill
    per link      a coloured line by type, with a TAPER-RATE VIOLATION DRAWN IN RED so a lane drop
                  that is too abrupt for its design speed is visible at the place it happens
    per junction  the clique ring and the member bearings
    per mouth     a LOCK glyph when `setback_locked`, so a mouth that Auto Setback will skip says
                  so before the artist wonders why it never moves

Colour is the only channel used for advisory findings (5): superelevation and sight distance are
NOT gate failures -- a gate that fires on every hand-authored road and gets overridden is a dead
gate -- so they tint here and report in the panel instead.
"""

import math

import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

try:
    from . import point_model as pm, point_profile as pp, point_validate as pv
except ImportError:
    import point_model as pm                                                 # noqa: E402
    import point_profile as pp                                               # noqa: E402
    import point_validate as pv                                              # noqa: E402


COL_SEGMENT = (0.35, 0.75, 1.00, 0.9)
COL_JUNCTION = (1.00, 0.80, 0.25, 0.9)
COL_AUX = (0.45, 1.00, 0.55, 0.9)
COL_BAD = (1.00, 0.20, 0.15, 1.0)
COL_EXTENT = (0.80, 0.80, 0.85, 0.35)
COL_LOCK = (1.00, 0.45, 0.90, 1.0)
COL_SPINE = (1.00, 1.00, 1.00, 0.75)

_handle_3d = None
_handle_2d = None

#: Refreshed on demand rather than every frame: the gate walks the whole network, and a draw
#: handler runs per viewport per redraw. Invalidated by any operator that edits the graph.
_cache = {"net": None, "bad_uids": set(), "centre": [], "stamp": -1}


#: Bumped by `invalidate()`. The cache key USED to be the object count, which meant a move or a
#: rotation -- the two things the overlay exists to show -- did not invalidate it. It is now an
#: explicit revision driven by `point_live.on_depsgraph`, which fires for both.
_rev = [0]


def invalidate():
    _rev[0] += 1
    _cache["stamp"] = -1


def _network(scene):
    """The authored network, re-read at most once per depsgraph revision."""
    stamp = _rev[0]
    if _cache["stamp"] != stamp or _cache["net"] is None:
        try:
            net = pm.read_network(scene)
        except Exception:
            return None
        # A taper finding names the point the artist must MOVE (`Finding.obj`), which is the
        # upstream end of the offending link -- so the link leaving it is the one to draw red.
        bad = {f.obj for f in pv.validate(net, checks=(pv.check_tapers,))}
        # THE RESOLVED CENTRELINE, recomputed with the network and drawn in `_draw_3d`. This is the
        # answer to "can the rotation be real time instead of a rebuild": a draw handler needs no
        # `bpy.data` write, so it is safe mid-modal, and `read_point` already promotes a rotated
        # point to MANUAL at READ time -- so the ribbon's spine bends under an R-drag, frame by
        # frame, with no build. Without it the overlay drew a fixed 8 m arrow per point and the
        # road's actual shape was invisible until you pressed Build.
        try:
            centre = pp.centreline_runs(net)
        except Exception:
            centre = []
        _cache.update({"net": net, "bad_uids": bad, "centre": centre, "stamp": stamp})
    return _cache["net"]


def _shader():
    return gpu.shader.from_builtin('UNIFORM_COLOR')


def _lines(coords, colour, width=1.6):
    if not coords:
        return
    sh = _shader()
    gpu.state.line_width_set(width)
    gpu.state.blend_set('ALPHA')
    batch = batch_for_shader(sh, 'LINES', {"pos": coords})
    sh.bind()
    sh.uniform_float("color", colour)
    batch.draw(sh)
    gpu.state.line_width_set(1.0)


def _point_frame(net, uid):
    """`(pos, forward, left)` for one point -- its own arrow direction and lateral frame."""
    p = net.points[uid]
    if p.tangent_mode == pm.MANUAL and p.tangent is not None:
        # THE LIVE FEEDBACK LOOP. A draw handler needs no `bpy.data` write, so it is safe mid-modal
        # -- which means the arrow follows an R-drag frame by frame, before any rebuild. Rotating a
        # point and watching the road's direction turn with it is the whole point of MANUAL.
        fwd = Vector(p.tangent)
        fwd = fwd.normalized() if fwd.length > 1e-9 else Vector((1.0, 0.0, 0.0))
        return Vector(p.pos), fwd, Vector((-fwd.y, fwd.x, 0.0))
    road = net.road_of(uid)
    chain = [u for u in road.points if u in net.points] if road else [uid]
    i = chain.index(uid) if uid in chain else 0
    nxt = chain[i + 1] if i + 1 < len(chain) else None
    prv = chain[i - 1] if i > 0 else None
    ref = nxt or prv
    if ref is None:
        fwd = Vector((1.0, 0.0, 0.0))
    else:
        d = Vector(net.points[ref].pos) - Vector(p.pos)
        if nxt is None:
            d = -d
        fwd = d.normalized() if d.length > 1e-9 else Vector((1.0, 0.0, 0.0))
    left = Vector((-fwd.y, fwd.x, 0.0))
    return Vector(p.pos), fwd, left


def _draw_3d():
    context = bpy.context
    scene = context.scene
    if not getattr(scene, "rka_overlay", True):
        return
    net = _network(scene)
    if net is None:
        return

    spine = []
    for _name, poly in _cache.get("centre") or ():
        for a, b in zip(poly, poly[1:]):
            spine += [Vector(a), Vector(b)]

    seg, jct, aux, bad, extent, lock = [], [], [], [], [], []
    for uid, p in net.points.items():
        try:
            pos, fwd, left = _point_frame(net, uid)
        except Exception:
            continue
        prof = pp.build_profile(net.resolved(uid) or p)
        import lane_profile as lp
        neg, pos_e = lp.paved_extents(prof)
        a = pos + left * pos_e
        b = pos - left * neg
        extent += [a, b]
        # The travel arrow: the Empty already shows one, but the overlay's is scaled to the road
        # so it reads at map zoom where a 4 m Empty does not.
        tip = pos + fwd * 8.0
        seg += [pos, tip]
        seg += [tip, tip - fwd * 2.5 + left * 1.2, tip, tip - fwd * 2.5 - left * 1.2]
        if p.setback_locked:
            for dx, dy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
                lock += [pos + Vector((dx * 2.0, dy * 2.0, 1.0)),
                         pos + Vector((dy * 2.0, -dx * 2.0, 1.0))]
        for l in p.links:
            t = net.points.get(l.target)
            if t is None:
                continue
            pair = [pos, Vector(t.pos)]
            if l.type == pm.LINK_SEGMENT and uid in _cache["bad_uids"]:
                bad += pair
            elif l.type == pm.LINK_JUNCTION:
                jct += pair
            elif l.type == pm.LINK_AUX:
                aux += pair
            else:
                seg += pair

    _lines(spine, COL_SPINE, 2.4)
    _lines(extent, COL_EXTENT, 1.2)
    _lines(seg, COL_SEGMENT)
    _lines(jct, COL_JUNCTION, 2.2)
    _lines(aux, COL_AUX, 2.2)
    _lines(lock, COL_LOCK, 2.0)
    # LAST and THICKEST: a taper too abrupt for its design speed must be the thing you see.
    _lines(bad, COL_BAD, 3.2)


def _draw_2d():
    """Lane counts and badges, in screen space so they stay readable at any zoom."""
    context = bpy.context
    scene = context.scene
    if not getattr(scene, "rka_overlay", True) or not getattr(scene, "rka_overlay_text", True):
        return
    net = _network(scene)
    if net is None:
        return
    region = context.region
    rv3d = context.region_data
    if rv3d is None:
        return
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    blf.size(0, 11)
    for uid, p in net.points.items():
        co = location_3d_to_region_2d(region, rv3d, Vector(p.pos))
        if co is None:
            continue
        r = net.resolved(uid) or p
        # `3+1|3`, NOT `3|3 +1/0`. An aux lane IS a lane -- it is paved, it is exported, and a car
        # drives on it -- so a label that prints the through count as THE lane count and hangs the
        # aux off the end as a suffix is read as "three lanes" by everyone who looks at it. That
        # is a user-reported confusion, on this exact demo: a four-lane carriageway whose outermost
        # lane becomes the exit ramp was counted as three, and the aux slot hand-authored back in.
        # The written form says the total by construction: three through plus one auxiliary.
        def _side(n, aux):
            return "%d+%d" % (int(n), int(aux)) if int(aux) else "%d" % int(n)
        label = "%s|%s" % (_side(r.lanes_fwd, r.aux_fwd), _side(r.lanes_bwd, r.aux_bwd))
        if p.profile_mode == pm.OVERRIDE:
            label += " *"                 # the OVERRIDE glyph -- see the module docstring
        if p.tangent_mode == pm.MANUAL:
            label += " R"                 # this point's ROTATION is shaping the road here
        blf.position(0, co.x + 6, co.y + 6, 0)
        blf.color(0, 1.0, 1.0, 1.0, 0.9 if p.profile_mode == pm.INHERIT else 1.0)
        blf.draw(0, label)


def register():
    global _handle_3d, _handle_2d
    bpy.types.Scene.rka_overlay = bpy.props.BoolProperty(
        name="Road Overlay", default=True,
        description="Draw lane counts, link types and taper violations in the viewport")
    bpy.types.Scene.rka_overlay_text = bpy.props.BoolProperty(
        name="Overlay Labels", default=True)
    if _handle_3d is None:
        _handle_3d = bpy.types.SpaceView3D.draw_handler_add(
            _draw_3d, (), 'WINDOW', 'POST_VIEW')
    if _handle_2d is None:
        _handle_2d = bpy.types.SpaceView3D.draw_handler_add(
            _draw_2d, (), 'WINDOW', 'POST_PIXEL')


def unregister():
    global _handle_3d, _handle_2d
    if _handle_3d is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle_3d, 'WINDOW')
        _handle_3d = None
    if _handle_2d is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle_2d, 'WINDOW')
        _handle_2d = None
    del bpy.types.Scene.rka_overlay_text
    del bpy.types.Scene.rka_overlay
