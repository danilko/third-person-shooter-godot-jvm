#!/usr/bin/env python3
"""
smoketest_junction_links.py -- a road meeting an INTERSECTION must produce the junction's real
movements: every legal turn out of the approach lane, and the way back out onto the road.

WHY THIS IS ITS OWN TEST, separate from `smoketest_joint_links.py`. A junction is a different SHAPE
of joint, not a bigger one. Between two segments a lane continues into exactly one lane, so pairing
is one-to-one and a tie means one of the two candidates is wrong. At a junction the approach lane
feeds EVERY movement that starts on it -- left, straight and right all begin on that same ribbon at
the same stop line, so all three are exactly, equally aligned and a tie is the correct answer. Run
the segment rule here and the closest movement wins: a junction cars can only drive straight
through, built out of geometry that is perfectly correct. That is the failure this test exists to
catch, and nothing about it is visible in the viewport.

It also pins the two things the exported graph is actually read for: a movement's `kind` comes from
the movement's own `turn` (a straight crossing is THROUGH even though a junction is involved -- the
runtime's straight-bias weighting is meaningless otherwise), and every one of those links is
measured edge-to-edge like any other, so an arm whose lanes do not line up with the road bolted
onto it is reported in metres rather than assumed.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_junction_links.py
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
import kit_common as kc                                    # noqa: E402
import lane_joints as lj                                   # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()
    context = bpy.context

    # ------------------------------------------------------------------ a plain 4-way, then a
    # road extended off one arm -- the way a user builds it.
    ret = bpy.ops.rka.build_intersection('EXEC_DEFAULT', preset='4WAY', lanes=1)
    _assert(ret == {'FINISHED'}, "build_intersection did not finish: %s" % (ret,))
    inter = next(c for c in bpy.data.collections
                 if c.library is None and "rka_arm_names" in c.keys())
    arm_names = list(inter["rka_arm_names"])
    arm = next(o for o in inter.objects if o.get("rka_arm_name") == arm_names[0])
    for o in bpy.data.objects:
        o.select_set(False)
    arm.select_set(True)
    context.view_layer.objects.active = arm
    ret = bpy.ops.rka.extend_from_arm('EXEC_DEFAULT', arm_name=arm_names[0], length=40.0)
    _assert(ret == {'FINISHED'}, "extend_from_arm did not finish: %s" % (ret,))

    lanes = ojc.collect_scene_lanes(context)
    by_id = {l["id"]: l for l in lanes}
    junction_lanes = [l for l in lanes if l.get("piece_id") == inter.name]
    _assert(junction_lanes, "the intersection exported no lanes at all")
    _assert(all(l.get("width_start") for l in junction_lanes),
            "every junction movement must export its width, or its ribbon EDGES cannot be derived "
            "and the alignment check silently measures nothing")

    problems, n_links, _n = ojc.check_scene_joints(context)
    _assert(n_links > 0,
            "a road extended from an arm produced NO lane connections -- the authored link never "
            "became lane data, so every vehicle falls back to the runtime's proximity guess")
    _assert(not problems,
            "every connection across a freshly extended arm must be edge-aligned, got:\n  %s"
            % "\n  ".join(lj.describe(p) for p in problems))
    print("smoketest_junction_links: a road extended from an arm produced %d edge-aligned "
          "connections" % n_links)

    # ------------------------------------------------------------- THE FAN. The approach lane
    # must reach every movement leaving that arm, not just the one that measured closest.
    seg_lanes = [l for l in lanes if l.get("piece_id") != inter.name]
    approach = [l for l in seg_lanes
                if any(r.get("piece") == inter.name for r in (l.get("next_refs") or []))]
    _assert(len(approach) == 1,
            "exactly one of the road's lanes drives INTO the junction, got %d" % len(approach))
    refs = approach[0]["next_refs"]
    _assert(len(refs) >= 3,
            "the approach lane feeds only %d movement(s); a 4-way offers left, straight AND right "
            "off the same stop line, so one-to-one pairing has silently deleted the turns"
            % len(refs))
    turns = sorted({(by_id.get("%s__%s" % (inter.name, r.get("lane_id"))) or {}).get("turn")
                    for r in refs})
    _assert(turns == ["L", "R", "S"],
            "the approach should reach one movement per turn direction, got %r" % (turns,))
    print("smoketest_junction_links: the approach lane feeds all %d movements (%s) -- the fan "
          "survived" % (len(refs), "/".join(t for t in turns if t)))

    # A junction movement is only a TURN when it actually turns.
    kinds = {(by_id.get("%s__%s" % (inter.name, r.get("lane_id"))) or {}).get("turn"):
             r.get("kind") for r in refs}
    _assert(kinds.get("S") == "THROUGH",
            "a straight crossing is a THROUGH movement even though a junction is involved -- "
            "labelling it TURN makes the runtime's straight-bias weighting meaningless, got %r"
            % kinds.get("S"))
    _assert(kinds.get("L") == "TURN" and kinds.get("R") == "TURN", kinds)
    print("smoketest_junction_links: kinds come from the movement's own turn (S=THROUGH, "
          "L/R=TURN), not from 'a junction is involved'")

    # ------------------------------------------------------------- and the way back OUT: the
    # movements ending on this arm all hand over to the one lane leaving on the road.
    out_refs = [(l, r) for l in junction_lanes for r in (l.get("next_refs") or [])
                if r.get("piece") != inter.name]
    _assert(len(out_refs) >= 3,
            "only %d movement(s) hand back out onto the road; every movement arriving at this arm "
            "feeds the single lane leaving it" % len(out_refs))
    targets = {r.get("lane_id") for _l, r in out_refs}
    _assert(len(targets) == 1,
            "all movements leaving by this arm should feed the SAME departure lane, got %r"
            % (targets,))
    print("smoketest_junction_links: %d movements hand back out onto the road's single departure "
          "lane" % len(out_refs))

    # ------------------------------------------------------------- a mis-sized arm is REPORTED,
    # not absorbed. Widening the arm's lanes leaves the road's ribbon a different width from the
    # movements bolted to it: the centrelines still meet exactly.
    inter["rka_lane_width"] = float(inter.get("rka_lane_width", 5.0)) + 1.0
    bpy.ops.rka.rebuild_from_handles('EXEC_DEFAULT')
    problems2, n_links2, _n2 = ojc.check_scene_joints(context)
    _assert(n_links2 < n_links,
            "widening the junction's lanes by 1m left all %d connections intact -- a road and an "
            "arm of different widths cannot be edge-aligned" % n_links2)
    # And the complaint must not vanish along with the links. This is the whole reason UNJOINED
    # exists: no link survives to be measured, so a checker that only measures links now sees a
    # perfectly clean scene with a hole in it.
    _assert(any(p["status"] == "UNJOINED" for p in problems2),
            "the seam broke SILENTLY -- %d link(s), %d problem(s). An authored joint that no lane "
            "crosses must be reported, or breaking a seam badly enough makes the complaint "
            "disappear with the links" % (n_links2, len(problems2)))
    print("smoketest_junction_links: a 1m arm/road width mismatch broke the seam -- %d link(s) "
          "survived and it is reported as UNJOINED, not as a clean scene" % n_links2)
    print("  %s" % lj.describe(next(p for p in problems2 if p["status"] == "UNJOINED")))

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
