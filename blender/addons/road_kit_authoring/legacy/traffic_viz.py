"""Viewport-only overlay: a short blue arrow (+'IN'/'FWD' label) for arriving/forward lanes and a
short orange arrow (+'OUT'/'BACK' label) for departing/backward lanes, drawn at every intersection
`arm_*` marker and every segment `segend_A`/`segend_B` marker. Answers "which physical lane here
is incoming vs. departing" without opening Custom Properties or rebuilding anything -- pure GPU
draw, reads the SAME marker/collection custom properties `ops_intersection.py`/`ops_segment.py`
already maintain (`rka_arm_angle`/`rka_arm_lanes`/`rka_arm_lanes_out`/`rka_arm_oneway`/
`rka_traffic_side`/`rka_lanes`/`rka_lanes_backward`), so it never drifts out of sync with the
actual geometry and never triggers a rebuild of its own.

Color convention (consistent everywhere): BLUE = lanes whose vehicles are traveling TOWARD this
marker (an arm's arriving lanes; a segment's forward lanes at its B end, backward lanes at its A
end); ORANGE = lanes traveling AWAY from this marker (an arm's departing lanes; a segment's
forward lanes at its A end, backward lanes at its B end). Lateral placement and direction use the
SAME `lane_perp`/`Arm.in_offset`/`out_offset` math `lib/intersection_kit.py` uses for the real
geometry (approximated to the two-endpoint chord for a segment, close enough for a schematic
gizmo -- the actual pavement/curb offsets are computed per-point elsewhere).

Toggle: `scene.rka.show_traffic_indicators` (Live Edit box). Pure viewport aid -- never written to
any exported data, never affects geometry.

Per-lane index tags (2026-08, `scene.rka.show_lane_indices`, independent toggle): a short tick +
"L0"/"L1"/... label at each INDIVIDUAL lane's own lateral position at every connection point (an
arm, or a segment/transition end) -- the viewport-visible replacement for `lanecl_*` lane-
centerline curves, which were removed from live generation the same day (confirmed export-
redundant -- `tools/save_lane_kit.py` recomputes lane centerlines independently from spine +
metadata -- and carried no mesh of their own, so they cost live-edit object-churn with zero
authoring-time payoff; see `ops_intersection.py`'s `_populate_intersection_mesh`). Reuses the
exact same (base, tip, color, label) tuple shape and `_arrow_segments`/draw pipeline the traffic
arrows already use -- a lane tick IS just a very short arrow with a numeric label instead of a
"FWD n" one, so no separate drawing code is needed."""
import math

import blf
import bpy

from . import spine_io
import gpu
from gpu_extras.batch import batch_for_shader

IN_COLOR = (0.25, 0.55, 1.0, 0.95)
OUT_COLOR = (1.0, 0.6, 0.15, 0.95)
ARROW_LENGTH = 3.0
LANE_TICK_LENGTH = 0.8   # short, deliberately -- a tick is an identity tag, not a direction cue


def _lane_ticks(base_xy, base_z, perp, sign, group_dir, lane_width, count, color, prefix):
    """One short tick + '<prefix><i>' label per individual lane in a same-direction group of
    `count` lanes, laid out from the centerline outward (`(i + 0.5) * lane_width`, the same
    per-lane spacing convention `Arm.in_offset`/`out_offset` and the real pavement/marking offsets
    already use -- see this module's own docstring for why an approximation here is fine: this is
    a schematic viewport aid, not exported geometry). `sign` flips which side of centerline the
    group sits on (matches `Arm.in_offset`'s negative / `out_offset`'s positive convention);
    `group_dir` is the tick's own pointing direction (purely cosmetic, distinguishes at a glance
    which way that lane's traffic runs)."""
    out = []
    for i in range(count):
        lat = sign * (i + 0.5) * lane_width
        p = (base_xy[0] + perp[0] * lat, base_xy[1] + perp[1] * lat, base_z)
        tip = (p[0] + group_dir[0] * LANE_TICK_LENGTH, p[1] + group_dir[1] * LANE_TICK_LENGTH, base_z)
        out.append((p, tip, color, "%s%d" % (prefix, i)))
    return out

# Same order of magnitude as LaneGraph's own JUNCTION_RADIUS endpoint-clustering tolerance --
# "close enough to this arm/segend to be the road it actually continues into."
ARM_LINK_RADIUS = 5.0

_handle_3d = None
_handle_2d = None
_last_items = []   # [(base_xyz, tip_xyz, color, label), ...] -- shared 3D->2D between the two passes


def _arrow_segments(base, tip):
    """3 line-segment pairs (shaft + a 2-stroke arrowhead) for GL_LINES, roughly planar in XY
    (every use here is a near-horizontal road-plane arrow)."""
    bx, by, bz = base
    tx, ty, tz = tip
    dx, dy = tx - bx, ty - by
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    head_len = min(0.6, length * 0.35)
    head_w = head_len * 0.6
    h1 = (tx - ux * head_len + px * head_w, ty - uy * head_len + py * head_w, tz)
    h2 = (tx - ux * head_len - px * head_w, ty - uy * head_len - py * head_w, tz)
    return [base, tip, tip, h1, tip, h2]


def _segment_arrows(k, marker_pos, is_a_end, tangent, lane_width, lanes_fwd, lanes_back,
                     traffic_side):
    """Shared FWD/BACK arrow pair for one end of a segment/transition -- used both by the legacy
    `segend_A`/`segend_B` marker path and the curve-backed spine-endpoint path (the only path
    `RKA_OT_build_straight_segment`/`extend_from_arm`/`build_segment_from_curve` actually use)."""
    out = []
    perp = k.lane_perp(tangent, traffic_side)
    fwd_lat = lanes_fwd * lane_width * 0.5
    back_lat = -lanes_back * lane_width * 0.5
    # Arrows always point along the lane group's ACTUAL direction of travel (forward = +tangent,
    # A->B; backward = -tangent, B->A) regardless of which end we're drawing at -- only the COLOR
    # (arriving vs. departing FROM THIS MARKER) depends on the end.
    fwd_color = OUT_COLOR if is_a_end else IN_COLOR
    back_color = IN_COLOR if is_a_end else OUT_COLOR
    mx, my, mz = marker_pos
    if lanes_fwd > 0:
        b = (mx + perp[0] * fwd_lat, my + perp[1] * fwd_lat, mz)
        tip = (b[0] + tangent[0] * ARROW_LENGTH, b[1] + tangent[1] * ARROW_LENGTH, b[2])
        out.append((b, tip, fwd_color, "FWD %d" % lanes_fwd))
    if lanes_back > 0:
        b = (mx + perp[0] * back_lat, my + perp[1] * back_lat, mz)
        tip = (b[0] - tangent[0] * ARROW_LENGTH, b[1] - tangent[1] * ARROW_LENGTH, b[2])
        out.append((b, tip, back_color, "BACK %d" % lanes_back))
    return out


def _end_tangent(pts, at_end):
    """Unit XY direction of travel AT ONE END of a spine, from the last two DISTINCT points.

    Not the whole-piece chord (`p0 -> p1`), which this used to be, for two reasons that both bite
    on real roads:

      * A CURVED piece leaves its ends at an angle to its own chord. Every island road is a
        Catmull-Rom fit resampled every few metres, so the chord can be tens of degrees off the
        direction the road actually runs where the arrow is drawn -- an arrow pointing somewhere
        the lane does not go is worse than no arrow, because it is read as the answer.
      * A piece whose ends COINCIDE in XY has no chord at all. A vertical connector ramp (island
        `SegmentCurve_062`: 22 points, one XY position, z 12 -> 4) made `vnorm` raise
        `cannot normalize a zero-length vector`, and since `_gather` builds the whole overlay in
        one pass, that ONE piece blanked the traffic arrows for the entire file. That is the
        "lost the ability to show in/out at each connection point" report.

    Returns None when the spine is genuinely degenerate in XY (every point stacked), which the
    caller skips -- a purely vertical piece has no meaningful ground-plane direction to draw, and
    inventing one would point the arrow at an arbitrary compass bearing."""
    idx = range(len(pts) - 1, -1, -1) if at_end else range(len(pts))
    ref = None
    for i in idx:
        p = pts[i]
        if ref is None:
            ref = p
            continue
        dx, dy = ref[0] - p[0], ref[1] - p[1]
        if not at_end:
            dx, dy = -dx, -dy
        n = math.hypot(dx, dy)
        if n > 1e-9:
            return (dx / n, dy / n)
    return None


def _nearby_outward_direction(pos, endpoints, radius=ARM_LINK_RADIUS):
    """Given `endpoints` = [(p0_xy, p1_xy, tangent_xy), ...] gathered from every curve-backed
    segment/transition, return the OUTWARD unit direction (pointing AWAY from `pos`, i.e. along
    the road as it actually continues) of whichever endpoint sits closest to `pos` within
    `radius`, or None if nothing is within range.

    This is the fix for an arm's IN/OUT gizmo arrow being drawn along the bearing from the
    intersection's ORIGIN marker through the arm (`rka_arm_angle`, re-derived fresh on every
    rebuild) instead of the direction the physically-attached road actually runs: that bearing is
    a GLOBAL quantity -- it shifts, however slightly, any time the origin/other arms/kerb radius
    change, even though the connected segment itself didn't move -- so the gizmo could visibly
    swing to a different angle on an unrelated edit, which is what made it hard to read. Preferring
    the LOCAL tangent of whatever segment/transition is actually plugged in here (the same value
    that segment endpoint's OWN arrows already use) ties the gizmo to something that only changes
    when that specific road actually does."""
    best_dir, best_dist = None, radius
    for p0, p1, t_a, t_b in endpoints:
        # Each end carries its OWN tangent now (see `_end_tangent`); both point along travel,
        # A->B. So from an arm sitting at the A end the road continues along `+t_a`, and from one
        # at the B end along `-t_b` -- the per-end form of the old chord's `+1/-1` sign.
        for near, direction in ((p0, t_a), (p1, (-t_b[0], -t_b[1]))):
            d = math.hypot(near[0] - pos[0], near[1] - pos[1])
            if d < best_dist:
                best_dist = d
                best_dir = direction
    return best_dir


def _gather(context):
    scene = context.scene
    rka = getattr(scene, "rka", None)
    if rka is None:
        return []
    show_arrows = rka.show_traffic_indicators
    show_lanes = rka.show_lane_indices
    if not show_arrows and not show_lanes:
        return []
    from . import ops_intersection, ops_segment
    k = ops_intersection.ik()

    items = []
    endpoints = []   # [(p0_xy, p1_xy, tangent_xy), ...] -- every curve-backed segment/transition's
                      # own endpoints+tangent, consulted below so an arm gizmo can prefer the
                      # ACTUAL attached road's direction over a bearing re-derived from origin.

    # Curve-backed segments/transitions -- the DEFAULT path (RKA_OT_build_straight_segment,
    # extend_from_arm, build_segment_from_curve, build_lane_transition) has no segend_A/B marker
    # Empties at all; the spine Curve's own first/last control points ARE the endpoints.
    for coll in bpy.data.collections:
        spine_name = coll.get("rka_curve_object")
        if not spine_name:
            continue
        spine_obj = bpy.data.objects.get(spine_name)
        if not spine_io.is_spine(spine_obj) or spine_obj.name not in scene.objects:
            continue
        try:
            pts = ops_segment._spine_control_points(spine_obj)
        except Exception:                    # noqa: BLE001
            continue
        if len(pts) < 2:
            continue
        p0, p1 = pts[0], pts[-1]
        # Per-END tangents, not one shared chord -- see `_end_tangent`. `t_a` points ALONG travel
        # at the A end (into the piece), `t_b` along travel at the B end (out of it).
        t_a, t_b = _end_tangent(pts, at_end=False), _end_tangent(pts, at_end=True)
        if t_a is None or t_b is None:
            continue        # no ground-plane direction to draw (a purely vertical connector)
        endpoints.append(((p0[0], p0[1]), (p1[0], p1[1]), t_a, t_b))
        traffic_side = coll.get("rka_traffic_side", "LEFT")
        lane_width = coll.get("rka_lane_width", 5.0)
        is_transition = "rka_lanes_a" in coll.keys()
        if is_transition:
            fwd_a, back_a = coll.get("rka_lanes_a", 2), coll.get("rka_lanes_backward_a", 0)
            fwd_b, back_b = coll.get("rka_lanes_b", 1), coll.get("rka_lanes_backward_b", 0)
            back_a = back_a or fwd_a
            back_b = back_b or fwd_b
        else:
            fwd_a = fwd_b = coll.get("rka_lanes", 1)
            back_a = back_b = coll.get("rka_lanes_backward", fwd_a)
        if show_arrows:
            items += _segment_arrows(k, p0, True, t_a, lane_width, fwd_a, back_a, traffic_side)
            items += _segment_arrows(k, p1, False, t_b, lane_width, fwd_b, back_b, traffic_side)
        if show_lanes:
            perp = k.lane_perp(t_a, traffic_side)
            perp_b = k.lane_perp(t_b, traffic_side)
            neg_a = (-t_a[0], -t_a[1])
            neg_b = (-t_b[0], -t_b[1])
            # Same per-end color/side/direction convention `_segment_arrows` already uses: at the
            # A-end, forward lanes are DEPARTING (OUT_COLOR) and backward lanes are ARRIVING
            # (IN_COLOR); at the B-end it's the mirror. Forward/backward groups sit on opposite
            # sides of centerline (sign flip), same as `_segment_arrows`'s `fwd_lat`/`back_lat`.
            items += _lane_ticks(p0, p0[2], perp, 1.0, t_a, lane_width, fwd_a, OUT_COLOR, "F")
            items += _lane_ticks(p0, p0[2], perp, -1.0, neg_a, lane_width, back_a, IN_COLOR, "B")
            items += _lane_ticks(p1, p1[2], perp_b, 1.0, t_b, lane_width, fwd_b, IN_COLOR, "F")
            items += _lane_ticks(p1, p1[2], perp_b, -1.0, neg_b, lane_width, back_b, OUT_COLOR, "B")

    for obj in scene.objects:
        keys = obj.keys()
        if "rka_arm_name" in keys:
            coll = obj.users_collection[0] if obj.users_collection else None
            traffic_side = coll.get("rka_traffic_side", "LEFT") if coll is not None else "LEFT"
            lane_width = coll.get("rka_lane_width", 5.0) if coll is not None else 5.0
            angle = obj.get("rka_arm_angle", 0.0)
            lanes = int(obj.get("rka_arm_lanes", 1))
            oneway = obj.get("rka_arm_oneway", "") or None
            lanes_out_raw = int(obj.get("rka_arm_lanes_out", 0))
            a = k.Arm("_viz", angle, lane_width, lanes, oneway=oneway,
                      lanes_out=lanes_out_raw or None, traffic_side=traffic_side)
            pos = obj.location
            d = (_nearby_outward_direction((pos.x, pos.y), endpoints)
                 or k.arm_dir(angle))
            perp = k.lane_perp(d, traffic_side)
            base = (pos.x, pos.y, pos.z)
            n_in, n_out = a.lanes_in_count(), a.lanes_out_count()
            if show_arrows and n_in > 0:
                lat = -a.in_width() * 0.5
                b = (base[0] + perp[0] * lat, base[1] + perp[1] * lat, base[2])
                tip = (b[0] - d[0] * ARROW_LENGTH, b[1] - d[1] * ARROW_LENGTH, b[2])
                items.append((b, tip, IN_COLOR, "IN %d" % n_in))
            if show_arrows and n_out > 0:
                lat = a.out_width() * 0.5
                b = (base[0] + perp[0] * lat, base[1] + perp[1] * lat, base[2])
                tip = (b[0] + d[0] * ARROW_LENGTH, b[1] + d[1] * ARROW_LENGTH, b[2])
                items.append((b, tip, OUT_COLOR, "OUT %d" % n_out))
            if show_lanes:
                # Uses Arm.in_offset/out_offset directly -- the REAL per-lane lateral offset this
                # arm's own curb/pavement geometry is built from (not an approximation), so a
                # lane's tick lines up exactly with its actual pavement lane.
                for i in range(n_in):
                    lat = a.in_offset(i)
                    p = (base[0] + perp[0] * lat, base[1] + perp[1] * lat, base[2])
                    tip = (p[0] - d[0] * LANE_TICK_LENGTH, p[1] - d[1] * LANE_TICK_LENGTH, base[2])
                    items.append((p, tip, IN_COLOR, "L%d" % i))
                for i in range(n_out):
                    lat = a.out_offset(i)
                    p = (base[0] + perp[0] * lat, base[1] + perp[1] * lat, base[2])
                    tip = (p[0] + d[0] * LANE_TICK_LENGTH, p[1] + d[1] * LANE_TICK_LENGTH, base[2])
                    items.append((p, tip, OUT_COLOR, "L%d" % i))
        elif obj.get("rka_segend") in ("A", "B"):
            # Legacy 2-point ribbon path (only RKA_OT_insert_intersection_on_segment's internal
            # `extend()` still uses this, via `build_segment_geometry`) -- every OTHER segment
            # builder is curve-backed with no segend_A/B markers at all, handled above.
            coll = obj.users_collection[0] if obj.users_collection else None
            if coll is None:
                continue
            other_key = "B" if obj["rka_segend"] == "A" else "A"
            other = next((o for o in coll.objects if o.get("rka_segend") == other_key), None)
            if other is None:
                continue
            lane_width = coll.get("rka_lane_width", 5.0)
            lanes_fwd = int(coll.get("rka_lanes", 1))
            lanes_back = int(coll.get("rka_lanes_backward", lanes_fwd))
            traffic_side = coll.get("rka_traffic_side", "LEFT")
            pa, pb = obj.location, other.location
            if obj["rka_segend"] == "B":
                pa, pb = other.location, obj.location
            tangent = _end_tangent([(pa.x, pa.y), (pb.x, pb.y)], at_end=True)
            if tangent is None:
                continue        # the two ends coincide in XY -- no direction to draw
            marker = (obj.location.x, obj.location.y, obj.location.z)
            items += _segment_arrows(k, marker, obj["rka_segend"] == "A", tangent, lane_width,
                                      lanes_fwd, lanes_back, traffic_side)
    return items


def _draw_3d():
    global _last_items
    context = bpy.context
    _last_items = _gather(context)
    if not _last_items:
        return

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(3.0)
    gpu.state.depth_test_set('LESS_EQUAL')
    for base, tip, color, _label in _last_items:
        verts = _arrow_segments(base, tip)
        batch = batch_for_shader(shader, 'LINES', {"pos": verts})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)
    gpu.state.depth_test_set('NONE')
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


def _draw_2d():
    if not _last_items:
        return
    context = bpy.context
    region = context.region
    rv3d = context.region_data
    if region is None or rv3d is None:
        return
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    font_id = 0
    blf.size(font_id, 13)
    for base, tip, color, label in _last_items:
        co2d = location_3d_to_region_2d(region, rv3d, tip)
        if co2d is None:
            continue
        blf.color(font_id, color[0], color[1], color[2], 1.0)
        blf.position(font_id, co2d.x + 4.0, co2d.y + 4.0, 0.0)
        blf.draw(font_id, label)


def register():
    global _handle_3d, _handle_2d
    if _handle_3d is None:
        _handle_3d = bpy.types.SpaceView3D.draw_handler_add(_draw_3d, (), 'WINDOW', 'POST_VIEW')
    if _handle_2d is None:
        _handle_2d = bpy.types.SpaceView3D.draw_handler_add(_draw_2d, (), 'WINDOW', 'POST_PIXEL')


def unregister():
    global _handle_3d, _handle_2d
    if _handle_3d is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle_3d, 'WINDOW')
        _handle_3d = None
    if _handle_2d is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle_2d, 'WINDOW')
        _handle_2d = None
