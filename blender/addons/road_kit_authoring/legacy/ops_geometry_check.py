"""ops_geometry_check.py -- "is this road drivable?", answered in the viewport.

The counterpart of `ops_joint_check` (which asks whether two pieces really CONNECT) for the
question of whether one piece is a road at all. Same shape, deliberately: same library
(`lib/road_geometry`), same numbers as `tools/check_road_network.py` check 6 runs on the exported
sidecar, but on the live scene while there is still something to drag.

WHAT IT ANSWERS, AND WHY A RADIUS CHECK WAS NOT ENOUGH. `road_geometry` reports five kinds of
problem and they want five different fixes:

    GRADE      too steep over a real distance -- the climb needs more length
    KINK       grade changes abruptly -- a vertical curve is missing
    RADIUS     too tight to bank into compliance at this speed
    CORNER     ONE control point turns too sharply -- a facet in the pavement, not a curve

`CORNER` was added on 2026-08-15, and it is the one thing no radius test can report. Every radius
measure here samples a fixed ARC LENGTH either side of a point -- that is what makes it immune to
sampling density -- so a single bad vertex is averaged into the curve around it. A road polyline
is SWEPT, though, not smoothed: whatever angle sits at a control point is the angle the driver
gets. `road_geometry` also reports `turn_excursion_deg` as a measurement, for a consumer that must
reject a folded alignment (a ramp search); it is deliberately not a verdict here, because ring
roads, switchbacks and loop ramps all reverse on purpose.

**NO, "smooth" DOES NOT FIX IT.** Blender's Smooth / Subdivide operators move control points, and
a road's control points are load-bearing: its ends are matched edge-to-edge against its
neighbours' lanes (`lib/lane_joints`), and its middle is the alignment a lane graph was exported
from. Smoothing rounds off the reported angle while silently breaking the seam and moving the road
off its authored line -- it hides the warning rather than answering it. A corner in a road is an
authoring error with a location, which is why this reports WHERE, in metres along the piece, and
puts a marker there.

THE ON-SCREEN SIGNAL is one mesh object, `RKA_GeometryWarnings` -- a vertical stick at each
flagged station, rebuilt from scratch on every run and removed by `Clear`. One object rather than
one Empty per finding, so a scene-wide check on a big network costs the outliner nothing and is
deleted in one step.

THE AUTOMATION SIGNAL is `check_scene_geometry(context)`, which returns the findings as data. A
batch build calls that and decides for itself; nothing about the report format is in its way.
"""
import bpy

from . import ops_joint_check

WARN_OBJ = "RKA_GeometryWarnings"

#: How tall the viewport marker sticks are, in metres. Tall enough to read from the height you
#: look at a district from, short enough not to hide the road it is pointing at.
MARKER_HEIGHT = 12.0


def _rg():
    """Lazy `lib/road_geometry` import -- the deferred-import idiom `ops_joint_check._lj()` uses."""
    import road_geometry
    return road_geometry


def _station_point(points, station):
    """The point `station` metres along a polyline, for placing a marker where a finding is."""
    import math
    if not points:
        return None
    run = 0.0
    for a, b in zip(points, points[1:]):
        seg = math.dist(a[:2], b[:2])
        if run + seg >= station or seg <= 0.0:
            t = 0.0 if seg <= 0.0 else (station - run) / seg
            return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))
        run += seg
    return tuple(points[-1])


def check_scene_geometry(context, default_speed=0.0):
    """`[(lane_id, piece, code, detail, where_xyz), ...]` for every lane in the file.

    A lane with no `design_speed` is SKIPPED for the speed-dependent verdicts rather than given an
    invented one -- a made-up design speed produces made-up findings, which is the same rule
    `check_road_network` check 6 follows. `CORNER` is speed-INDEPENDENT, so it is reported on
    every lane: a facet in the pavement is wrong at any limit."""
    rg = _rg()
    lanes = ops_joint_check.collect_scene_lanes(context)
    out = []
    for lane in lanes:
        pts = lane.get("points") or ()
        if len(pts) < 3:
            continue
        speed = float(lane.get("design_speed") or default_speed or 0.0)
        # `collect_scene_lanes` reads Blender-native coordinates, so the default ground-plane axes
        # are the right ones (see `lane_joints.BLENDER_AXES` for what getting this wrong looks
        # like -- it is silent and looks like geometry).
        res = rg.analyse(pts, speed or 1.0, axes=(0, 1))
        for code, detail in res["problems"]:
            if not speed and code != "CORNER":
                continue
            station = res["corner_at"] if code == "CORNER" else res.get("at_station", 0.0)
            out.append((lane["id"], lane.get("piece_id", ""), code, detail,
                        _station_point(pts, station)))
    return out


def clear_markers():
    obj = bpy.data.objects.get(WARN_OBJ)
    if obj is not None:
        bpy.data.objects.remove(obj, do_unlink=True)
        return True
    return False


def place_markers(context, findings):
    """Rebuild `RKA_GeometryWarnings` as one stick per finding. Returns the object (or None)."""
    clear_markers()
    spots = [f[4] for f in findings if f[4] is not None]
    if not spots:
        return None
    verts, edges = [], []
    for p in spots:
        i = len(verts)
        verts.append((p[0], p[1], p[2]))
        verts.append((p[0], p[1], p[2] + MARKER_HEIGHT))
        edges.append((i, i + 1))
    me = bpy.data.meshes.new(WARN_OBJ)
    me.from_pydata(verts, edges, [])
    me.update()
    obj = bpy.data.objects.new(WARN_OBJ, me)
    obj.show_in_front = True
    context.scene.collection.objects.link(obj)
    return obj


class RKA_OT_check_road_geometry(bpy.types.Operator):
    """Measure every road in the file against its design speed and report what a driver could not
    do: too steep, a missing vertical curve, a curve too tight to bank, or a single control point
    turning too sharply.

    Findings are listed worst-first in the Info log, the worst piece is selected, and a marker
    stick is dropped at each one so the report leads somewhere instead of naming an id. Note that
    smoothing the curve is NOT the fix -- it moves control points the seams and the exported lane
    graph depend on, and hides the warning instead of answering it."""
    bl_idname = "rka.check_road_geometry"
    bl_label = "Check Road Geometry"
    bl_options = {'REGISTER'}

    drop_markers: bpy.props.BoolProperty(
        name="Drop Markers", default=True,
        description="Build a marker stick at every finding (one mesh object, removed by Clear)")
    select_worst: bpy.props.BoolProperty(
        name="Select Worst Piece", default=True,
        description="Select the piece owning the first finding, so the report leads somewhere")

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        try:
            findings = check_scene_geometry(context)
        except Exception as exc:                      # noqa: BLE001 -- a report beats a traceback
            self.report({'ERROR'}, "road geometry check failed: %s" % exc)
            return {'CANCELLED'}

        if not findings:
            self.report({'INFO'}, "every road in the file is drivable at its design speed "
                                   "(no grade, kink, radius or corner problems)")
            clear_markers()
            return {'FINISHED'}

        # CORNER first: it is a ONE-POINT fix and it makes every other measurement on the piece
        # suspect, since a facet distorts the curve around it.
        rank = {"CORNER": 0, "RADIUS": 1, "KINK": 2, "GRADE": 3, "SUPERELEV": 4}
        findings.sort(key=lambda f: rank.get(f[2], 9))
        for lane_id, _piece, code, detail, _where in findings:
            print("  road geometry: %s: %s -- %s" % (lane_id, code, detail))
        if self.drop_markers:
            place_markers(context, findings)
        if self.select_worst:
            ops_joint_check.RKA_OT_check_joint_alignment._select_piece_of(context, findings[0][0])

        counts = {}
        for f in findings:
            counts[f[2]] = counts.get(f[2], 0) + 1
        summary = ", ".join("%s=%d" % kv for kv in sorted(counts.items()))
        self.report({'WARNING'}, "%d finding(s) [%s]; worst: %s -- %s (see Info log for all)"
                                 % (len(findings), summary, findings[0][2], findings[0][3]))
        return {'FINISHED'}


class RKA_OT_clear_geometry_warnings(bpy.types.Operator):
    """Remove the geometry-warning markers."""
    bl_idname = "rka.clear_geometry_warnings"
    bl_label = "Clear Warnings"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        self.report({'INFO'}, "warning markers removed" if clear_markers() else "none to remove")
        return {'FINISHED'}


CLASSES = (RKA_OT_check_road_geometry, RKA_OT_clear_geometry_warnings)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
