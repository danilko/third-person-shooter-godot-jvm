#!/usr/bin/env python3
"""
smoketest_median_chain_merge.py -- headless verification for `median_merge.py` (2026-08,
user-reported: "change the current median to [a] single mesh of curb instead of curb on each way",
explicitly chosen as fully-automatic/always-live-synced -- runs from `live_edit._flush_rebuilds`'s
tail, no manual button). A wall-style ('BOX') median chain of 2+ linked segments should collapse
into ONE continuous merged wall object per side (`curb_medianchain_<n>_A`/`_B` in the dedicated
`RKA_MedianChains` collection), with each member's own individual `curb_<coll>_median_A`/`_B`
objects removed -- otherwise the two would visibly overlap.

Deliberately constructs a "meet in the middle" topology (two segments built from TWO SEPARATE
intersections, linked far-end-to-far-end -- port_B to port_B) specifically because it's the one
topology where a member piece's own natural point order runs OPPOSITE the chain's overall flow
direction, exercising `median_merge._order_chain`'s `aligned=False` reversal path -- the ordinary
"keep extending forward" authoring pattern never produces a reversed member at all.

RUN: blender --background --python addons/road_kit_authoring/smoketest_median_chain_merge.py
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
from road_kit_authoring import ops_intersection as opint  # noqa: E402
from road_kit_authoring import live_edit                   # noqa: E402
from road_kit_authoring import median_merge                # noqa: E402
import kit_common as kc                                     # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    scene_coll = bpy.context.scene.collection
    context = bpy.context

    # --- Segment_1: off intersection A, port_A near the arm, port_B far -- a real median (BOX).
    resultA = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 2, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    interA = resultA["coll"]
    arm_n_a = next(o for o in interA.objects if o.get("rka_arm_name") == "N")
    for o in bpy.data.objects:
        o.select_set(False)
    arm_n_a.select_set(True)
    context.view_layer.objects.active = arm_n_a
    ret = bpy.ops.rka.extend_from_arm('EXEC_DEFAULT', arm_name="N", length=40.0, median_width=4.0)
    _assert(ret == {'FINISHED'}, "extend_from_arm (1) did not finish: %s" % (ret,))
    seg1 = next(c for c in bpy.data.collections
                if c.get("rka_curve_object") and "rka_lanes_a" not in c.keys() and c is not interA)
    _assert(seg1.get("rka_median_style", "BOX") == "BOX", "sanity: default median style is BOX")
    n1_before = len(bpy.data.objects[seg1["rka_curve_object"]].data.splines[0].points)

    # --- Segment_2: off a SEPARATE intersection B, far away -- also a real BOX median.
    resultB = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 500.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 2, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    interB = resultB["coll"]
    arm_s_b = next(o for o in interB.objects if o.get("rka_arm_name") == "S")
    for o in bpy.data.objects:
        o.select_set(False)
    arm_s_b.select_set(True)
    context.view_layer.objects.active = arm_s_b
    ret = bpy.ops.rka.extend_from_arm('EXEC_DEFAULT', arm_name="S", length=40.0, median_width=4.0)
    _assert(ret == {'FINISHED'}, "extend_from_arm (2) did not finish: %s" % (ret,))
    seg2 = next(c for c in bpy.data.collections
                if c.get("rka_curve_object") and "rka_lanes_a" not in c.keys()
                and c is not interA and c is not interB and c is not seg1)
    n2_before = len(bpy.data.objects[seg2["rka_curve_object"]].data.splines[0].points)

    # extend_from_arm already auto-linked seg2's OWN start to arm_S (the normal "keep tracking
    # where it came from" behavior) -- disconnect that first, or linking its FAR end below would
    # make it a genuine DUAL-linked piece (pinned at both arm_S AND seg1, correctly stretching to
    # span the real ~500m gap between the two intersections -- a legitimate, but here unwanted,
    # feature of the dual-end-link system, not what this test means to exercise).
    origin2 = opint.get_or_create_origin_marker(seg2)
    for o in bpy.data.objects:
        o.select_set(False)
    origin2.select_set(True)
    context.view_layer.objects.active = origin2
    ret = bpy.ops.rka.disconnect_marker('EXEC_DEFAULT')
    _assert(ret == {'FINISHED'}, "disconnect_marker (seg2 origin) did not finish: %s" % (ret,))

    # --- link FAR END to FAR END (port_B <-> port_B) -- the reversal-exercising topology.
    port_b1 = next(o for o in seg1.objects if o.get("rka_port") == "B")
    port_b2 = next(o for o in seg2.objects if o.get("rka_port") == "B")
    for o in bpy.data.objects:
        o.select_set(False)
    port_b1.select_set(True)
    port_b2.select_set(True)
    context.view_layer.objects.active = port_b2
    ret = bpy.ops.rka.connect_markers('EXEC_DEFAULT')
    _assert(ret == {'FINISHED'}, "connect_markers (port_B <-> port_B) did not finish: %s" % (ret,))

    # A live drag anywhere in the chain re-triggers a flush -- nudge arm N (intersection A) so the
    # whole pipeline (per-piece rebuild -> median_merge.sync_median_chains) actually runs the way
    # a real edit would, not just relying on connect_markers' own one-shot sync.
    with live_edit.rebuilding():
        live_edit._propagate_links({arm_n_a.name})
    median_merge.sync_median_chains(context, live_edit.RKA_LINKED_TO_KEY, opint.ORIGIN_MARKER_KEY)

    seg1 = opint.local_collection(seg1.name)
    seg2 = opint.local_collection(seg2.name)
    # seg2's tangent correction (see move_dependent_marker) may have inserted a bend point --
    # re-read the ACTUAL post-connect counts rather than trusting the pre-connect ones.
    n1_after = len(bpy.data.objects[seg1["rka_curve_object"]].data.splines[0].points)
    n2_after = len(bpy.data.objects[seg2["rka_curve_object"]].data.splines[0].points)

    # --- chain detection + ordering: seg1 aligned (natural order), seg2 REVERSED.
    chains = median_merge._median_chains(live_edit.RKA_LINKED_TO_KEY, opint.ORIGIN_MARKER_KEY)
    _assert(len(chains) == 1, "expected exactly one median chain, got %d" % len(chains))
    chain = chains[0]
    _assert(len(chain) == 2, "expected a 2-member chain, got %d" % len(chain))
    by_name = dict(chain)
    _assert(by_name.get(seg1.name) is True,
            "segment 1 (chain start, connects via its own port_B) should be ALIGNED")
    _assert(by_name.get(seg2.name) is False,
            "segment 2 (meets seg1 at ITS OWN port_B, opposite the chain's flow) should be REVERSED")
    print("median_chain_merge smoketest: chain detected with the expected order/alignment "
          "(seg1=aligned, seg2=reversed)")

    # --- ONE merged wall object per side exists, spanning the full chain.
    chain_coll = bpy.data.collections.get(median_merge.MEDIAN_CHAIN_COLLECTION)
    _assert(chain_coll is not None, "the dedicated median-chain collection should exist")
    merged = [o for o in chain_coll.objects if o.name.startswith("curb_medianchain_")]
    _assert(len(merged) == 2, "expected exactly 2 merged objects (one per median side), got %d: %s"
            % (len(merged), [o.name for o in merged]))
    for obj in merged:
        n_pts = len(obj.data.splines[0].points)
        expected = n1_after + n2_after - 1   # one shared joint point dropped
        _assert(n_pts == expected,
                "%s should have %d points (seg1's %d + seg2's %d, joint point shared) -- got %d"
                % (obj.name, expected, n1_after, n2_after, n_pts))
    print("median_chain_merge smoketest: exactly 2 merged wall objects exist, each spanning the "
          "full chain's point count with no duplicate joint point")

    # --- both segments sit exactly on the X axis (seg1: (12,0)->(52,0); seg2 dual-pinned by the
    # rigid translate to also land on the X axis) -- a CORRECTLY ordered/reversed/side-matched
    # concatenation must therefore be perfectly MONOTONIC in X (12 -> 52 -> ... -> 92, never
    # doubling back), and every point's Y must be the SAME sign (same physical side) throughout.
    # The natural ~6m spacing around the bend point is expected and NOT itself a problem -- a
    # naive small "gap at the seam" threshold doesn't distinguish that from a real mis-ordering,
    # this monotonicity/sign check does.
    for obj in merged:
        pts = [tuple(p.co)[:3] for p in obj.data.splines[0].points]
        xs = [p[0] for p in pts]
        _assert(all(xs[i] < xs[i + 1] for i in range(len(xs) - 1)),
                "%s: X coordinates should be strictly increasing (12 -> 52 -> ... -> 92) for a "
                "correctly ordered concatenation of two collinear segments -- got %s"
                % (obj.name, xs))
        # seg1's own median tapers from 0 (right at arm N, which has no median of its own -- the
        # arm-median joint-sync tapering it down, working as intended) up to its authored 4m --
        # ignore near-zero points (neither side, a degenerate taper-through-zero point) and check
        # every NONZERO point shares one sign.
        ys = [p[1] for p in pts if abs(p[1]) > 1e-6]
        _assert(len({y > 0 for y in ys}) <= 1,
                "%s: every nonzero-offset point should be on the SAME physical side (same Y "
                "sign) -- a side swap/mis-match would show up as a sign flip partway through -- "
                "got %s" % (obj.name, ys))
    print("median_chain_merge smoketest: the seam between the two members is continuous "
          "(no mis-ordered/mis-reversed jump)")

    # --- endpoints land where expected: the merged wall's FIRST point is seg1's own far/
    # unconnected end (near arm N, since seg1 is aligned/natural order), and its LAST point is
    # seg2's own far/unconnected end (near arm S, since seg2 is walked in REVERSE, so its chain-
    # order "last" point is its own natural FIRST point/port_A near arm S).
    seg1_spine = bpy.data.objects[seg1["rka_curve_object"]]
    seg2_spine = bpy.data.objects[seg2["rka_curve_object"]]
    seg1_port_a = tuple(seg1_spine.data.splines[0].points[0].co)[:3]
    seg2_port_a = tuple(seg2_spine.data.splines[0].points[0].co)[:3]
    for obj in merged:
        pts = [tuple(p.co)[:3] for p in obj.data.splines[0].points]
        # The merged wall sits `median_half` off the spine centerline, not ON it -- compare against
        # a generous tolerance (the median offset itself, ~2-3m) rather than an exact point match.
        d_first = math.dist(pts[0][:2], seg1_port_a[:2])
        d_last = math.dist(pts[-1][:2], seg2_port_a[:2])
        _assert(d_first < 5.0, "%s: first point should be near seg1's port_A (near arm N), off by "
                                "%.2fm" % (obj.name, d_first))
        _assert(d_last < 5.0, "%s: last point should be near seg2's port_A (near arm S), off by "
                               "%.2fm" % (obj.name, d_last))
    print("median_chain_merge smoketest: merged wall endpoints land at each chain terminus' own "
          "unconnected end, confirming seg2 was walked in the correct (reversed) direction")

    # --- each member's own individual median wall objects are gone (superseded by the merge).
    for coll in (seg1, seg2):
        for tag in ("median_A", "median_B"):
            name = "curb_%s_%s" % (coll.name, tag)
            _assert(coll.objects.get(name) is None,
                    "%s's own individual median wall '%s' should have been removed once merged"
                    % (coll.name, name))
    print("median_chain_merge smoketest: each member's own individual median wall was removed")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
