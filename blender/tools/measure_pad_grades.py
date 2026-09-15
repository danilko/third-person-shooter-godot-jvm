#!/usr/bin/env python3
"""Steepest grade and worst grade change along every junction turn path of a `.roads.json` (PLAN.md 3.1 B12).

    python3 blender/tools/measure_pad_grades.py assets/world_source/pieces/DebugRoads.roads.json

Each legal turn path is resampled every 0.5 m and its heights read three ways: off the pad's own triangles
(`point_solve.pad_z` -- what is built and driven on), and off the IDW field the pad is built from at power 2
(`_idw_z`, what the build uses) and power 1. Grades are averaged over 2 m, so a crease reads as a grade change
per 2 m. Found with `tools/godot/probe_road_launch.gd`: DebugRoads' west pad is 40.5% off its fan, 22% off the
field itself.
"""
import math
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "addons", "road_kit_authoring"))
import point_model as pm, point_solve as ps
net = pm.load_network(sys.argv[1])
for j in ps.solve_junctions(net):
    for label, fn in (("fan pad_z", lambda xy: ps.pad_z(j.fan, xy)), ("IDW p2", lambda xy: ps._idw_z(j.mouths, xy)),
                      ("IDW p1", lambda xy: ps._idw_z(j.mouths, xy, power=1.0))):
        steep = dg = 0.0
        for t in j.turns:
            pts = t["points"]
            if len(pts) < 3: continue
            # dense resample 0.5 m
            dense = []
            for a, b in zip(pts, pts[1:]):
                h = math.hypot(b[0]-a[0], b[1]-a[1]); n = max(1, int(h / 0.5))
                for k in range(n):
                    u = k / n; dense.append((a[0]+(b[0]-a[0])*u, a[1]+(b[1]-a[1])*u))
            zs = [fn(p) for p in dense]
            if any(z is None for z in zs): continue
            grades = []
            for i in range(1, len(dense)):
                h = math.hypot(dense[i][0]-dense[i-1][0], dense[i][1]-dense[i-1][1])
                if h > 1e-6: grades.append((zs[i]-zs[i-1])/h)
            # smooth over 2 m (4 samples) so a crease reads as grade change per 2 m
            g2 = [sum(grades[i:i+4])/4 for i in range(0, len(grades)-3)]
            if g2:
                steep = max(steep, max(abs(g) for g in g2))
                dg = max(dg, max(abs(g2[i]-g2[i-4]) for i in range(4, len(g2))) if len(g2) > 4 else 0)
        print("pad %s %-10s steepest %.1f%%  worst grade change per 2 m %.1f%%" % (j.uids[0], label, steep*100, dg*100))
