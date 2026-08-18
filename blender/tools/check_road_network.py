#!/usr/bin/env python3
"""
check_road_network.py -- is the exported road actually ONE NETWORK, and does it say what an
interchange is?

Pure Python, no Blender: it reads a combined `.lanekit.json` (what `save_lane_kit.py` writes and
what `WorldBaker` bakes into `PathLaneRoute`s) and walks it exactly the way the runtime does.

WHAT IT ANSWERS, and why each matters:

1. IS AN INTERCHANGE CONNECTED AT ALL? A split's trunk must reach both of its branches. Before the
   profile rewrite the interchange pieces exported ZERO lanes, so this question could not even be
   asked; the ramp was pavement with no data behind it.

2. CAN A CAR REACH THE RAMP? This is the one a longitudinal-only graph gets wrong. An auxiliary
   exit lane BEGINS mid-carriageway -- nothing upstream flows into it, which is why the
   `save_lane_kit` lint correctly calls its free end ISOLATED. It is reachable only by CHANGING
   LANES. So reachability is walked over successors AND lane-change adjacency together; a network
   that models only successors leaves every ramp stranded.

3. DOES THE NETWORK KNOW WHICH MOVEMENT IS WHICH? At a gore every lane end sits within a few
   metres of every other, so endpoint proximity cannot distinguish a mainline continuing from a
   ramp departing. `next_kinds` carries the authored answer (THROUGH / EXIT / ENTRY). An AI
   chasing or racing a target through an interchange needs exactly this: "did they take the exit".

4. IS ANYTHING DANGLING? An explicit successor naming a lane that does not exist would silently
   drop a car back to proximity guessing, so unresolved references are an error, not a warning.

RUN:
  python3 blender/tools/check_road_network.py assets/world_source/island_v3_roads.lanekit.json
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))

import lane_joints as lj      # noqa: E402  (needs the sys.path line above)
import road_geometry as rg    # noqa: E402


def load(path):
    """`(lanes_by_id, whole_sidecar)`. The whole document, not just the lanes: check 2c needs the
    `joints` list, which is about the lanes that are MISSING and so cannot live among them."""
    with open(path) as f:
        d = json.load(f)
    return {l["id"]: l for l in d.get("lanes", [])}, d


JUNCTION_RADIUS = 4.5   # must equal LaneGraph.JUNCTION_RADIUS / lane_kit.JUNCTION_RADIUS


def proximity_edges(lanes, radius=JUNCTION_RADIUS):
    """The edges `LaneGraph` derives at RUNTIME: lane A -> lane B when A's last point is within
    `radius` of B's first. Rebuilt here so this check walks the same graph the game walks --
    the `.lanekit.json` stores only the AUTHORED links, because proximity is derived on load.

    Without this pass an interchange looks like an island: its own three pieces are explicitly
    linked to each other and to nothing else, since the ordinary road either side of it is joined
    the ordinary way. Testing "does the trunk reach the central road network" means testing the
    combination, which is what the runtime actually has."""
    heads = [(l["id"], l["points"][0]) for l in lanes.values() if l.get("points")]
    out = defaultdict(list)
    r2 = radius * radius
    for l in lanes.values():
        pts = l.get("points")
        if not pts:
            continue
        tail = pts[-1]
        for oid, head in heads:
            if oid == l["id"]:
                continue
            dx, dy, dz = tail[0] - head[0], tail[1] - head[1], tail[2] - head[2]
            if dx * dx + dy * dy + dz * dz <= r2:
                out[l["id"]].append(oid)
    return out


def reachable(lanes, start, use_lane_change=True, prox=None):
    """Every lane reachable from `start`, following explicit successors and -- unless disabled --
    lane changes. Lane change is a real edge of a road network, not a shortcut: an exit lane has
    no other way in."""
    seen, stack = {start}, [start]
    while stack:
        cur = lanes.get(stack.pop())
        if cur is None:
            continue
        nxt = list(cur.get("next", []))
        if use_lane_change:
            nxt += [n for n in (cur.get("inner_lane"), cur.get("outer_lane")) if n]
        if prox is not None:
            nxt += prox.get(cur["id"], [])
        for n in nxt:
            if n not in seen and n in lanes:
                seen.add(n)
                stack.append(n)
    return seen


def _explicit_edges(lanes):
    """`{lane_id: [lane_id, ...]}` from AUTHORED data only -- successors plus lane-change
    adjacency, with proximity deliberately excluded.

    Proximity is a runtime convenience for joining pieces that were authored separately; it is not
    a substitute for knowing where traffic may go. Walking it here would hide exactly the defect
    this gate exists to catch, because at a gore every lane end sits within a few metres of every
    other and proximity therefore "connects" a ramp whether or not anything says traffic may take
    it."""
    out = defaultdict(list)
    for l in lanes.values():
        out[l["id"]] += [n for n in l.get("next", []) if n in lanes]
        for key in ("inner_lane", "outer_lane"):
            n = l.get(key)
            if n and n in lanes:
                # SYMMETRIC. A lane change is physically available in both directions, and the
                # sidecar records it single-valued from one side only -- a travel lane can name
                # just one neighbour outward, while several auxiliary lanes at different stations
                # each name it inward. Walking these one-way would leave every one of those exit
                # lanes unreachable from the carriageway they sit beside.
                out[l["id"]].append(n)
                out[n].append(l["id"])
    return out


def _drivable(l):
    return l.get("slot_kind", "TRAVEL") in ("TRAVEL", "AUX") and len(l.get("points", ())) >= 2


def main(path):
    lanes, data = load(path)
    print("lanes: %d  (from %s)" % (len(lanes), path))
    fails = []

    # ------------------------------------------------------------------ 1. no dangling references
    dangling = []
    for l in lanes.values():
        for n in l.get("next", []):
            if n not in lanes:
                dangling.append((l["id"], "next", n))
        for key in ("inner_lane", "outer_lane"):
            n = l.get(key)
            if n and n not in lanes:
                dangling.append((l["id"], key, n))
    if dangling:
        for a, k, b in dangling[:10]:
            print("  DANGLING %s.%s -> %s" % (a, k, b))
        fails.append("%d dangling lane reference(s)" % len(dangling))
    else:
        print("1. no dangling references                         OK")

    # ---------------------------------------------- 2. the graph exists at all, in authored form
    exp = _explicit_edges(lanes)
    n_succ = sum(len(l.get("next", ())) for l in lanes.values())
    n_lc = sum(1 for l in lanes.values() if l.get("inner_lane") or l.get("outer_lane"))
    drivable = [l for l in lanes.values() if _drivable(l)]
    orphans = [l["id"] for l in drivable if not exp.get(l["id"])
               and not any(l["id"] in v for v in exp.values())]
    print("2. authored graph: %d successor link(s), %d lane(s) with lane-change adjacency"
          % (n_succ, n_lc))
    if n_succ == 0:
        fails.append("no explicit successors anywhere -- the network is proximity-only, so "
                     "nothing records where traffic may actually go")
    if orphans:
        print("   %d drivable lane(s) with NO authored edge in or out, e.g.:" % len(orphans))
        for o in orphans[:6]:
            print("     %s" % o)
        fails.append("%d drivable lane(s) unreachable by authored data alone" % len(orphans))

    # ------------------------------------------------ 2b. every link is EDGE-ALIGNED, not merely
    # touching. A link is a promise that a car can cross the seam; two lanes whose centrelines
    # coincide can still be a full lane width apart at their edges (different widths, a heading
    # break, or a head-on pairing). See `lib/lane_joints` for why edges are the right test and why
    # it is one check rather than three.
    # A `.lanekit.json` is written in GODOT space -- `(x, height, -northing)` -- so the
    # ground plane is axes (0, 2), NOT the default (0, 1). Measuring x-against-elevation
    # here silently collapses every lane's edges onto its centreline and reports plausible
    # nonsense (found 2026-08-15, same root cause as `emit_joint_links`).
    align_problems = lj.check_links(list(lanes.values()), axes=lj.GODOT_AXES)
    unmeasurable = [p for p in align_problems if p["status"] == "UNMEASURABLE"]
    real = [p for p in align_problems if p["status"] != "UNMEASURABLE"]
    if real:
        worst = sorted(real, key=lambda p: -(p.get("gap_left") or 0.0))
        for p in worst[:8]:
            print("   %s" % lj.describe(p))
        fails.append("%d link(s) are not edge-aligned -- the lanes touch but their ribbons do not "
                     "continue" % len(real))
    else:
        n_links = sum(len(l.get("next", ())) for l in lanes.values())
        print("2b. every link is edge-aligned                    OK (%d of %d measurable)"
              % (n_links - len(unmeasurable), n_links))
    if unmeasurable:
        # Not a failure: an older sidecar predates the width fields. Say so plainly rather than
        # passing silently, because a check that quietly measures nothing is the failure mode this
        # whole gate exists to prevent.
        print("   note: %d link(s) could not be measured (lanes carry no width -- re-export to "
              "get edge checking on them)" % len(unmeasurable))

    # ------------------------------------------------- 2c. an authored joint that NO lane crosses.
    # The above measures links; this is about their ABSENCE. Break a seam badly enough and the
    # links stop forming, so 2b goes quiet and the file reads as clean -- the failure hiding behind
    # the fix. `joints` records what the user connected in the .blend (only the .blend knows), so
    # the two questions can be told apart here with no Blender.
    joints = data.get("joints")
    if joints is None:
        print("2c. authored joints all crossed by a lane   SKIP (sidecar predates 'joints' -- "
              "re-export to check this)")
    else:
        piece_of = {lid: l.get("piece_id") for lid, l in lanes.items()}
        crossed = set()
        for lid, l in lanes.items():
            src = l.get("piece_id")
            for dst in l.get("next", ()):
                other = piece_of.get(dst)
                if src and other and other != src:
                    crossed.add(tuple(sorted((src, other))))
        unjoined = [j for j in joints
                    if tuple(sorted((j.get("a"), j.get("b")))) not in crossed]
        if unjoined:
            for j in unjoined[:8]:
                print("   %s" % lj.describe(lj.unjoined(j.get("a"), j.get("b"))))
            fails.append("%d authored joint(s) have NO lane crossing them -- the pieces were "
                         "connected but their ribbons never meet" % len(unjoined))
        else:
            print("2c. authored joints all crossed by a lane        OK (%d joint(s))" % len(joints))

    # ------------------------------------------------------------- 3. movement kinds are present
    kinds = defaultdict(int)
    for l in lanes.values():
        for k in l.get("next_kinds", []):
            kinds[k] += 1
    print("3. movement kinds: %s" % (", ".join("%s=%d" % kv for kv in sorted(kinds.items()))
                                     or "NONE"))
    if not kinds:
        fails.append("no typed movements (EXIT/ENTRY/THROUGH/TURN) anywhere -- at a gore every "
                     "lane end is metres from every other, so nothing can tell a mainline "
                     "continuing from a ramp departing")

    # --------------------------------------------------- 4. every ramp is usable from its road
    # Grouped pieces: one `mainline` role plus one piece per ramp (see ROAD_KIT_REDESIGN.md 2.3).
    groups = defaultdict(list)
    for l in lanes.values():
        if l.get("link_group"):
            groups[l["link_group"]].append(l)
    if groups:
        print("4. ramps usable from their carriageway:")
        for gname in sorted(groups):
            members = groups[gname]
            roles = defaultdict(list)
            for l in members:
                roles[l.get("link_role", "-")].append(l)
            main_lanes = [l for l in roles.get("mainline", []) if _drivable(l)]
            ramp_lanes = [l for r, ls in roles.items() if r != "mainline"
                          for l in ls if _drivable(l)]
            if not main_lanes or not ramp_lanes:
                print("     %-18s SKIP (mainline=%d ramp=%d)"
                      % (gname, len(main_lanes), len(ramp_lanes)))
                continue
            # DIRECTION IS PER RAMP, not per group. A two-direction carriageway carries exits AND
            # entries on the same piece (ROAD_KIT_REDESIGN.md 2.3), so asking the group as a whole
            # gets one of them backwards -- and testing an on-ramp as "mainline reaches ramp"
            # fails a perfectly good on-ramp. Each ramp says which it is through its own edges:
            # a mainline lane pointing AT it is an exit, it pointing at a mainline lane is an entry.
            main_ids = {m["id"] for m in main_lanes}
            missed, n_exit, n_entry = [], 0, 0
            for rl in ramp_lanes:
                is_entry = any(n in main_ids for n in rl.get("next", []))
                if is_entry:
                    n_entry += 1
                    ok_one = any(m in reachable(lanes, rl["id"]) for m in main_ids)
                else:
                    n_exit += 1
                    ok_one = any(rl["id"] in reachable(lanes, m) for m in main_ids)
                if not ok_one:
                    missed.append(rl["id"])
            label = "%d exit / %d entry" % (n_exit, n_entry)
            if missed:
                print("     %-18s FAIL %d of %d ramp lane(s) unreachable (%s)"
                      % (gname, len(missed), len(ramp_lanes), label))
                for m in missed[:4]:
                    print("        %s" % m)
                fails.append("%s: %s broken" % (gname, label))
            else:
                print("     %-18s OK   all %d ramp lane(s) reachable (%s)"
                      % (gname, len(ramp_lanes), label))
    else:
        print("4. no grouped carriageway/ramp pieces found")

    # ------------------------------------------------- 5. nothing is an island (proximity ALLOWED)
    # Here proximity IS included: this asks whether a piece attaches to the rest of the map at
    # all, which is a weaker and different question from "is the movement authored".
    prox = proximity_edges(lanes)
    print("5. runtime proximity edges: %d" % sum(len(v) for v in prox.values()))
    for gname in sorted(groups):
        ids = {l["id"] for l in groups[gname]}
        # From ANY of the group's lanes -- the question is whether this piece is attached to the
        # map at all, and reachability is directional, so seeding from one arbitrary lane answers
        # a narrower question than the one being asked (a ring's mainline reaches its own ramps
        # but an entry ramp reaches only inward).
        outside = set()
        for l in groups[gname]:
            if _drivable(l):
                outside |= reachable(lanes, l["id"], prox=prox)
        outside -= ids
        if not outside:
            print("     %-18s FAIL isolated from the wider network" % gname)
            fails.append("%s isolated from the wider network" % gname)
        else:
            print("     %-18s OK   reaches %d lane(s) outside itself" % (gname, len(outside)))

    # -------------------------------------------- 6. is every lane actually DRIVABLE at its speed?
    # Runs on the LANE polylines -- the same points `Preview Lane Curves` draws as
    # `lanepreview_<piece>_<slot>` -- not on the piece centreline, because a car drives a lane and
    # on a curve the inner lane is tighter than the centreline it was offset from. `design_speed`
    # rides on each lane; a sidecar written before that field existed says so rather than assuming.
    speeds = [l.get("design_speed") for l in lanes.values() if _drivable(l)]
    known = [s for s in speeds if s]
    if not known:
        print("6. alignment vs design speed              SKIP (no lane carries 'design_speed' -- "
              "re-export to check grade/curvature)")
    else:
        worst = []
        by_code = defaultdict(int)
        for l in lanes.values():
            if not _drivable(l) or not l.get("design_speed"):
                continue
            res = rg.analyse(l["points"], float(l["design_speed"]), axes=lj.GODOT_AXES)
            for code, detail in res["problems"]:
                by_code[code] += 1
                worst.append((-abs(res["required_e"]) if code in ("RADIUS", "SUPERELEV")
                              else -abs(res["max_grade"]), l["id"], code, detail))
        if worst:
            worst.sort()
            for _k, lid, code, detail in worst[:8]:
                print("   %s: %s -- %s" % (lid, code, detail))
            print("6. alignment vs design speed: %s"
                  % ", ".join("%s=%d" % kv for kv in sorted(by_code.items())))
            # RADIUS is the only one that cannot be fixed by banking or by a vertical curve, so
            # it alone fails the build; the rest are reported to be worked through.
            if by_code.get("RADIUS"):
                fails.append("%d lane(s) are too tight to bank into compliance at their design "
                             "speed -- the geometry has to change" % by_code["RADIUS"])
        else:
            print("6. alignment vs design speed                     OK (%d lane(s), %.0f-%.0f km/h)"
                  % (len(known), min(known), max(known)))

    print()
    if fails:
        for f in fails:
            print("FAIL: %s" % f)
        raise SystemExit("network gate FAILED (%d problem(s))" % len(fails))
    print("network gate PASSED")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1
         else "assets/world_source/island_v3_roads.lanekit.json")
