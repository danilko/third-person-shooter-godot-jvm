#!/usr/bin/env python3
"""
smoketest_ramp_seed_radius.py -- `ops_split.seed_ramp` must MOVE a ramp, not reshape it.

A ramp is authored on the loop's own centreline; its gore seed sits on the carriageway's
auxiliary-lane slot, tens of metres away. Re-anchoring it onto that seed is the last thing that
happens to the alignment `island_v3_plan.fit_ramp` searched for -- and for a long time it was
done by decaying the shift LINEARLY over the whole length, which is a shear, not a translation.
A shear across a curving path rescales its radius: measured on the real ramps, a 15 m seed
offset took IC_RINKAI_W from 74.2 m to 27.5 m and IC_PORT from 48.4 m to 23.5 m, silently
undoing the search that had just proved them.

This pins the property that matters: the governing radius survives the seed, and the touchdown
does not move. The fixture is a real ramp's shape -- parallel run, governing curve, run-out --
built around a circular arc of a KNOWN radius, so a failure reports how much of the road's
geometry the seed step ate, in metres, rather than just "different".

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_ramp_seed_radius.py
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

from road_kit_authoring import ops_split                   # noqa: E402
import road_geometry as rg                                  # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _ramp_fixture(radius, sweep_deg, lead=100.0, tail=300.0, step=8.0, z=12.0):
    """A ramp shaped like the real ones: a straight parallel run off the gore, the governing
    curve, then a straight run-out to the touchdown. Uniformly sampled -- a windowed radius
    measured on a wildly non-uniform polyline is a property of the sampling, not of the road
    (Step 6, defect 2).

    The shape matters to what this test proves: the seed's release window is supposed to land in
    the RUN-OUT, leaving the governing curve translated bodily. A bare arc would conflate 'the
    blend is bounded' with 'the blend happens to miss the curve'. The default `tail` is therefore
    long enough to hold the whole window (`RAMP_SEED_TAIL_CLEAR + RAMP_SEED_BLEND`) -- a ramp with
    a shorter run-out than that has nowhere clear to absorb the seed, which is an authoring fact
    about that ramp, not a property of this function."""
    pts = [(-d, 0.0, z) for d in range(int(lead), 0, -int(step))]
    n = max(3, int(radius * math.radians(sweep_deg) / step))
    pts += [(radius * math.sin(i / n * math.radians(sweep_deg)),
             radius * (1.0 - math.cos(i / n * math.radians(sweep_deg))), z)
            for i in range(n + 1)]
    ex, ey, _ = pts[-1]
    hx, hy = math.cos(math.radians(sweep_deg)), math.sin(math.radians(sweep_deg))
    pts += [(ex + hx * d, ey + hy * d, z)
            for d in range(int(step), int(tail) + 1, int(step))]
    return pts


def _radius(pts):
    xy = [(p[0], p[1]) for p in pts]
    return min(rg.min_radius_along(xy, 25.0), rg.min_radius_along(xy, 12.0))


def main():
    R = 220.0
    ramp = _ramp_fixture(R, 70.0)
    measured = _radius(ramp)
    _assert(abs(measured - R) < R * 0.05,
            "fixture is not a %.0f m arc (measures %.1f m)" % (R, measured))

    for offset in (8.0, 15.0, 22.0):
        # Seed the gore end sideways, the way a real auxiliary-lane slot sits off the centreline.
        seed = (ramp[0][0], ramp[0][1] - offset, ramp[0][2])
        out = ops_split.seed_ramp(ramp, seed, (1.0, 0.0), 'split')

        _assert(len(out) == len(ramp), "seed_ramp must not resample the alignment")
        d0 = math.dist(out[0][:2], seed[:2])
        _assert(d0 < 1e-9, "the gore end must land exactly on the seed, got %.4f m off" % d0)
        d1 = math.dist(out[-1][:2], ramp[-1][:2])
        _assert(d1 < 1e-6, "the touchdown must not move, got %.4f m off" % d1)

        got = _radius(out)
        # The release window is a bounded smoothstep in the RUN-OUT, so the governing curve is
        # translated bodily and keeps its radius. A whole-length blend fails this by a mile --
        # it shears the curve itself, which is what took the real IC_PORT to 18 m.
        _assert(got > R * 0.9,
                "seed_ramp ate the ramp's geometry at a %.0f m offset: %.1f m radius, was %.1f m "
                "(a whole-length blend instead of a bounded one?)" % (offset, got, measured))
        print("seed radius: offset %4.1f m -> gore exact, touchdown fixed, radius %.1f m of "
              "%.1f m (%.0f%% kept)" % (offset, got, measured, 100.0 * got / measured))

    # ...and the parallel run really is PARALLEL: the first stretch is translated bodily, so the
    # departure heading at the gore is the authored one, not one bent by the re-anchoring.
    seed = (ramp[0][0], ramp[0][1] - 15.0, ramp[0][2])
    out = ops_split.seed_ramp(ramp, seed, (1.0, 0.0), 'split')
    h_in = math.degrees(math.atan2(ramp[1][1] - ramp[0][1], ramp[1][0] - ramp[0][0]))
    h_out = math.degrees(math.atan2(out[1][1] - out[0][1], out[1][0] - out[0][0]))
    _assert(abs((h_out - h_in + 180.0) % 360.0 - 180.0) < 0.05,
            "the gore departure heading changed by %.2f deg -- the ramp should LEAVE tangent to "
            "the traffic it is exiting, exactly as authored" % (h_out - h_in))
    print("seed radius: the departure heading at the gore is unchanged (%.3f deg) -- the ramp "
          "still leaves tangent to the mainline" % h_in)

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
