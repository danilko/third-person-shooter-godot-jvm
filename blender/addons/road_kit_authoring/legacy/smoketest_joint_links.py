#!/usr/bin/env python3
"""
smoketest_joint_links.py -- an authored joint must become REAL per-lane connections, and a seam
that does not actually line up must be reported rather than claimed.

TOUCHING IS NOT CONNECTING (migration Step 4). Before this, connecting two pieces produced a marker
link and nothing else: the exported graph had 717 lanes and zero successors, so every joint fell
back to the runtime's endpoint-proximity guess -- which cannot tell a mainline continuing from a
ramp departing, and cannot tell a clean seam from one where the two ribbons are a full lane width
apart at their edges.

THE DIVISION OF LABOUR under test here:
  * WHICH PIECES connect is AUTHORED -- the user linked a port (`Extend From Port` stamps it).
  * WHICH LANE continues into which is MEASURED -- `lane_joints.pair_lanes` pairs the ribbons that
    genuinely meet edge-to-edge, so a mirrored joint and a ramp's aux lane both fall out with no
    special case.
  * A seam that does not line up produces NO link, and the checker names it in metres.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_joint_links.py
"""
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import road_kit_authoring as rka                          # noqa: E402
from road_kit_authoring import ops_joint_check as ojc      # noqa: E402
from road_kit_authoring import ops_segment as opseg        # noqa: E402
from road_kit_authoring import spine_io                    # noqa: E402
import kit_common as kc                                     # noqa: E402
import lane_joints as lj                                    # noqa: E402

LW = 5.0


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()
    context = bpy.context
    scene_coll = context.scene.collection

    # ------------------------------------------------------------------ author a joint the way a
    # user does: build a segment, then extend from its end port.
    r1 = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0)], LW, 2, 2,
        'NONE', 'NONE', 0.15, 0.25, False, "", "")
    coll1 = r1["coll"]
    port_b = next(o for o in coll1.objects if o.get("rka_port") == "B")
    for o in bpy.data.objects:
        o.select_set(False)
    port_b.select_set(True)
    context.view_layer.objects.active = port_b
    ret = bpy.ops.rka.extend_from_port('EXEC_DEFAULT', length=30.0)
    _assert(ret == {'FINISHED'}, "extend_from_port did not finish: %s" % (ret,))

    lanes = ojc.collect_scene_lanes(context)
    _assert(len(lanes) == 8, "sanity: two 2+2 segments should export 8 lanes, got %d" % len(lanes))
    _assert(all(l.get("width_start") for l in lanes),
            "every lane must export its width, or its ribbon EDGES cannot be derived and the "
            "alignment check silently measures nothing")

    problems, n_links, _n = ojc.check_scene_joints(context)
    _assert(n_links == 4,
            "a joint between two 2+2 segments should produce 4 per-lane connections (2 each way), "
            "got %d -- if 0, the authored link never became lane data at all" % n_links)
    _assert(not problems,
            "every connection across a freshly authored joint must be edge-aligned, got:\n  %s"
            % "\n  ".join(lj.describe(p) for p in problems))
    print("smoketest_joint_links: an authored joint produced %d real per-lane connections, all "
          "edge-aligned" % n_links)

    # --------------------------------------------------------------- links are PER LANE, and each
    # lane continues into exactly one lane -- not into "the other piece".
    with_refs = [l for l in lanes if l.get("next_refs")]
    _assert(len(with_refs) == 4,
            "4 lanes should carry a successor, got %d" % len(with_refs))
    for l in with_refs:
        refs = l["next_refs"]
        _assert(len(refs) == 1,
                "lane %s claims %d successors across a plain butt joint; a through lane continues "
                "into exactly one" % (l["id"], len(refs)))
        _assert(refs[0].get("lane_id"),
                "a joint ref must name the TARGET LANE, not just the target piece -- %r" % refs[0])
        _assert(refs[0].get("kind") == "THROUGH",
                "segment-to-segment continuation should be THROUGH, got %r" % refs[0].get("kind"))
    print("smoketest_joint_links: each connection names one specific target LANE, typed THROUGH")

    # ------------------------------------------------------------------ now break the seam. Move
    # the second piece's first spine point sideways: the centres still nearly meet, but the
    # ribbons no longer continue. This is the case a proximity join happily accepts.
    coll2 = next(c for c in bpy.data.collections
                 if "rka_curve_object" in c.keys() and c is not coll1)
    spine2 = bpy.data.objects.get(coll2["rka_curve_object"])
    pts = spine_io.points(spine2)
    pts[0].co.y += 0.4
    problems2, n_links2, _n2 = ojc.check_scene_joints(context)
    broken = [p for p in problems2 if p["status"] != "UNMEASURABLE"]
    _assert(broken or n_links2 < n_links,
            "nudging a joined piece 0.4m sideways must be visible -- either as a reported "
            "misalignment or as connections that no longer form, but got %d clean links"
            % n_links2)
    print("smoketest_joint_links: a 0.4m sideways nudge broke the seam -- %d link(s) survived, "
          "%d reported misaligned (a proximity join would have accepted it silently)"
          % (n_links2, len(broken)))

    # ------------------------------------------------------------------ and the operator itself
    # runs clean and reports through the normal channel.
    ret = bpy.ops.rka.check_joint_alignment(select_worst=False)
    _assert(ret == {'FINISHED'}, "check_joint_alignment did not finish: %s" % (ret,))
    print("smoketest_joint_links: the Check Joint Alignment operator runs over the live scene")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
