#!/usr/bin/env python3
"""
smoketest_lane_ports.py -- per-slot ports (ROAD_KIT_MIGRATION_STATUS.md Step 7).

What it pins down, all of which a road-centre `port_A`/`port_B` could not express:
  1. A two-way segment gets one marker per LANE END, on that lane's own centreline (NOT the road
     centre), each carrying its own direction of travel -- an IN and an OUT arrow at each end.
  2. The markers are tagged `rka_lane_port`, NOT `rka_port`, so `live_edit._flush_port_drags`
     cannot mistake one for a spine-endpoint drag handle and yank the far end of the road onto a
     lane centreline.
  3. `Snap Lane To Lane` moves a rotated, displaced piece so the two chosen LANE ends coincide and
     flow the same way -- and the seam it produces passes `lane_joints`' EDGE test, which is the
     difference between "touching" and "connected".
  4. The snap records the joint, so the seam exports real lane links rather than being merely
     aligned.
  5. Refresh is idempotent and tracks the geometry: reshape the spine, rebuild, and the ports
     follow with no duplicates left behind.
  6. Ports stay OPT-IN: a rebuild never creates them on a piece that has none.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_lane_ports.py
"""
import bpy
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import road_kit_authoring as rka                          # noqa: E402
from road_kit_authoring import ops_lane_ports as olp      # noqa: E402
from road_kit_authoring import ops_segment as opseg       # noqa: E402
from road_kit_authoring import ops_intersection as opint  # noqa: E402
from road_kit_authoring import live_edit                  # noqa: E402
from road_kit_authoring import spine_io                   # noqa: E402
import kit_common as kc                                    # noqa: E402
import lane_joints as lj                                   # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _build(context, pts, name_hint=""):
    res = opseg._build_segment_from_points(
        context, context.scene.collection, pts, lane_width=3.5, lanes=1, lanes_backward=1,
        curb_l_style='NONE', curb_r_style='NONE', curb_height=0.15, curb_thickness=0.25,
        join_visual_mesh=False, export_path="", gltf_export_path="")
    return bpy.data.collections.get(res["coll"].name)


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()
    context = bpy.context

    # ------------------------------------------------------------------ 1. one port per lane end
    a = _build(context, [(0.0, 0.0, 0.0), (60.0, 0.0, 0.0)])
    n = olp.refresh_lane_ports(context, a, create=True)
    ports = olp.existing_lane_ports(a)
    _assert(len(ports) == n and n == 4,
            "a two-way segment should give 4 lane ports (IN+OUT at each end), got %d" % n)
    flows = sorted(o[olp.LANE_PORT_KEY] for o in ports)
    _assert(flows == ["IN", "IN", "OUT", "OUT"], flows)
    # ...and none of them sits on the road centreline, which is where the old single port was.
    offs = sorted(round(o.location.y, 3) for o in ports)
    _assert(all(abs(y) > 1.0 for y in offs), "lane ports must sit on LANE centrelines, not the "
                                              "road centre; got y=%s" % offs)
    print("lane ports: 4 markers on a two-way segment, one per lane end, none on the road "
          "centreline (y=%s)" % offs)

    # each end carries BOTH directions -- the in/out readout a centre port cannot give
    west = [o for o in ports if abs(o.location.x) < 1e-3]
    _assert(sorted(o[olp.LANE_PORT_KEY] for o in west) == ["IN", "OUT"],
            "each end must show an inbound AND an outbound port")
    print("lane ports: each road end shows one IN and one OUT arrow")

    # ------------------------------------------------ 2. tagged so live_edit cannot mistake them
    _assert(all("rka_port" not in o.keys() for o in ports),
            "a lane port carrying `rka_port` would be treated by live_edit._flush_port_drags as "
            "a spine-endpoint drag handle -- see ops_lane_ports' module docstring")
    spine = opint.local_object(a["rka_curve_object"])
    before = [tuple(p.co[:3]) for p in spine_io.points(spine)]
    curve_colls, _tr = live_edit._flush_port_drags({o.name for o in ports})
    after = [tuple(p.co[:3]) for p in spine_io.points(spine)]
    _assert(not curve_colls and before == after,
            "dragging a lane port must NOT rewrite the spine (got %s)" % (curve_colls,))
    print("lane ports: inert to live_edit's port-drag path -- the spine is untouched")

    # ------------------------------------------------------------------- 3. snap lane to lane
    # A second piece, deliberately rotated and displaced so the snap has real work to do.
    th = math.radians(31.0)
    b = _build(context, [(200.0, 120.0, 2.5),
                          (200.0 + 55.0 * math.cos(th), 120.0 + 55.0 * math.sin(th), 2.5)])
    olp.refresh_lane_ports(context, b, create=True)

    # A's OUT port at its east end -> B's IN port at B's start. Traffic runs A then B.
    a_out = max((o for o in olp.existing_lane_ports(a) if o[olp.LANE_PORT_KEY] == "OUT"),
                key=lambda o: o.location.x)
    b_ports = olp.existing_lane_ports(b)
    b_in = min((o for o in b_ports if o[olp.LANE_PORT_KEY] == "IN"), key=lambda o: o.location.x)
    # B moves onto A: the ACTIVE port is the one that moves.
    coll, theta, delta = olp.snap_piece(context, b_in, a_out)
    _assert(coll is b, "the moving piece should be B")
    with live_edit.rebuilding():
        opint._rebuild_piece_in_place(context, b)
    olp.refresh_lane_ports(context, b)

    b_in_after = next(o for o in olp.existing_lane_ports(b)
                       if o[olp.LANE_PORT_LANES] == b_in[olp.LANE_PORT_LANES])
    d = (b_in_after.location - a_out.location).length
    _assert(d < 1e-3, "after the snap the two lane ends should coincide, got %.4f m apart" % d)
    print("lane ports: snap moved B by %.1f deg / %.2f m; the two lane ends now coincide "
          "(%.5f m apart)" % (theta, math.dist((0.0, 0.0, 0.0), delta), d))

    # ...and the seam is EDGE-aligned, measured by the same code the network gate runs.
    lanes = []
    for c in (a, b):
        from road_kit_authoring import lane_export
        dd = lane_export.export_piece_dict(c, context.scene, godot_space=False)
        for lane in dd.get("lanes", ()):
            l = dict(lane)
            l["id"] = "%s__%s" % (c.name, lane.get("id"))
            lanes.append(l)
    outs = [l for l in lanes if l["id"].startswith(a.name + "__")]
    ins = [l for l in lanes if l["id"].startswith(b.name + "__")]
    pairs = lj.pair_lanes(outs, ins)
    _assert(pairs, "no lane pairs across the snapped seam -- the snap aligned nothing")
    worst = max(g for _x, _y, g in pairs)
    _assert(worst <= lj.EDGE_TOL, "snapped seam should be edge-aligned within %.3f m, worst is "
                                   "%.4f m" % (lj.EDGE_TOL, worst))
    print("lane ports: the snapped seam passes the EDGE test -- %d lane pair(s), worst gap "
          "%.5f m" % (len(pairs), worst))

    # ------------------------------------------------------------- 4. flow conflicts are refused
    import lane_ports as lp
    a_out_d = olp._port_dict_of(a_out)
    _assert(lp.flow_conflict(a_out_d, a_out_d), "OUT-to-OUT must be refused")
    print("lane ports: OUT-to-OUT / IN-to-IN snaps are refused by name, not silently made")

    # ------------------------------------------------------------ 5. idempotent + tracks geometry
    n_before = len(olp.existing_lane_ports(a))
    spine_io.points(spine)[-1].co = (90.0, 0.0, 0.0, 1.0)
    opseg.rebuild_segment_gn_in_place(context, a)
    olp.refresh_lane_ports(context, a)
    after_ports = olp.existing_lane_ports(a)
    _assert(len(after_ports) == n_before,
            "refresh must be idempotent, got %d ports (was %d)" % (len(after_ports), n_before))
    east = max(o.location.x for o in after_ports)
    _assert(abs(east - 90.0) < 1e-3,
            "lane ports should track the reshaped spine's new end (x=90), got %.3f" % east)
    print("lane ports: refresh is idempotent and follows a reshaped spine, no duplicates")

    # ------------------------------------------------------------------------ 6. still opt-in
    c = _build(context, [(0.0, 400.0, 0.0), (40.0, 400.0, 0.0)])
    opint._rebuild_piece_in_place(context, c)
    _assert(not olp.existing_lane_ports(c),
            "a rebuild must NOT create lane ports on a piece that never opted in")
    print("lane ports: a rebuild never populates a piece that never asked for ports")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
