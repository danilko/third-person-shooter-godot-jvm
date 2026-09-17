#!/usr/bin/env python3
"""Steepest grade and worst grade change along every junction turn path of a `.roads.json` (PLAN.md 3.1 B12).

    python3 blender/tools/measure_pad_grades.py assets/world_source/pieces/DebugRoads.roads.json

Heights are read four ways over the same paths (`point_solve.turn_grades`, 0.5 m samples averaged over 2 m):
off the pad's own triangles (`pad_z` -- what is built and driven on), off its `PadField` directly, and, for
comparison, off the IDW rule at power 2 and a one-apex fan over the ring (the pad before B12). The last column
is the floor: a movement's end-to-end rise over its plan length, which no surface can go below.
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "addons", "road_kit_authoring"))
import point_model as pm, point_solve as ps  # noqa: E402

net = pm.load_network(sys.argv[1])
for j in ps.solve_junctions(net):
    fan = [(j.fan_apex, j.boundary[i], j.boundary[(i + 1) % len(j.boundary)]) for i in range(len(j.boundary))]
    rules = (("pad (built)", None), ("field", j.fan.field.z), ("IDW p2", lambda xy: ps._idw_z(j.mouths, xy)),
             ("old fan", lambda xy: ps.pad_z(fan, xy)))
    for label, zfn in rules:
        g = ps.turn_grades(j, zfn=zfn)
        if not g:
            continue
        floor = max(abs(x[4]) / max(x[3], 1e-6) for x in g)
        print("pad %s %-11s %4d tris  steepest %5.1f%%  worst grade change per 2 m %5.1f%%  floor %5.1f%%" % (
            j.uids[0], label, len(j.fan), max(x[1] for x in g) * 100, max(x[2] for x in g) * 100, floor * 100))
