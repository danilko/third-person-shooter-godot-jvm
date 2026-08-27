"""What goes UNDER a road surface -- the `delta = surface_z - ground_z` rule, and nothing else.

    delta = surface_z - ground_z   ->   support kind

    delta >  FILL_MAX (4.0)      PIER     soffit slab + columns every PIER_SPACING (30 m)
    delta >  AT_GRADE_TOL (0.4)  FILL     earth embankment, 1:1.5 batter
   |delta| <= AT_GRADE_TOL       NONE     the road sits on the ground; CUT the terrain under it
    delta >= -CUT_MAX (3.0)      CUT      trench walls
    else                         TUNNEL   bored, with a portal at each end

That is the whole idea. A road drawn at ground level gets nothing under it; lift the same road 2 m
and it grows an embankment; lift it to 12 m and the embankment becomes a pier line. Nothing about
the road changed -- only its height did. Because the rule is a PURE FUNCTION of delta it can live
in Geometry Nodes and re-evaluate live while a height is dragged, which is why `ground_z` is
sampled inside Build unconditionally and never behind a button the artist has to remember.

WHY THIS FILE EXISTS AT ALL. These rules were owned by `tools/island_v3_plan.py`, which is the
island PLANNER; the road BUILDER needs the identical rules. Two copies of "what goes under a
surface" is defect 1 one level up -- the planner would decide a ramp needs a pier line and the
builder would draw an embankment, and nothing would report the disagreement. So the definitions
live here, in a `bpy`-free lib both can import, and `island_v3_plan` re-exports them for its own
callers rather than restating them.
"""

import math

# --------------------------------------------------------------------------------- vocabulary

SUPPORT_NONE = "NONE"        # |delta| small -- surface sits on the ground
SUPPORT_FILL = "FILL"        # low lift -- earth embankment, side slope FILL_SLOPE
SUPPORT_PIER = "PIER"        # high lift -- soffit slab + columns every PIER_SPACING
SUPPORT_CUT = "CUT"          # shallow dig -- trench walls
SUPPORT_TUNNEL = "TUNNEL"    # deep dig -- bored, portal at each end

KINDS = (SUPPORT_NONE, SUPPORT_FILL, SUPPORT_PIER, SUPPORT_CUT, SUPPORT_TUNNEL)

AT_GRADE_TOL = 0.40          # |delta| under this = at grade, nothing underneath
FILL_MAX = 4.00              # embankment stops being credible above this
CUT_MAX = 3.00               # trench becomes a tunnel below this
FILL_SLOPE = 1.5             # 1:1.5 earth batter (run per unit of rise)
PIER_SPACING = 30.0          # Shuto viaduct bent spacing, 30-40 m typical
PIER_SECTION = 2.20          # square column side
DECK_THICK = 1.60            # structural depth under the driving surface

#: Maximum grade by road kind. A ramp may be steep; a mainline may not.
MAX_GRADE = {"ramp": 0.06, "street": 0.08, "arterial": 0.05, "expressway": 0.04}


def support_kind(surface_z, ground_z):
    """THE rule. A pure function of the height difference -- see the module header."""
    d = surface_z - ground_z
    if d > FILL_MAX:
        return SUPPORT_PIER
    if d > AT_GRADE_TOL:
        return SUPPORT_FILL
    if d >= -AT_GRADE_TOL:
        return SUPPORT_NONE
    if d >= -CUT_MAX:
        return SUPPORT_CUT
    return SUPPORT_TUNNEL


def fill_footprint(surface_z, ground_z, half_width):
    """Half-width of the embankment TOE -- how much ground an at-fill road actually eats.

    This is the number the ground cut must use, and the reason it exists: the old model drew the
    embankment as a VERTICAL-SIDED BOX at road width and separately fed it the toe width, giving a
    16.5 m embankment under a 4.5 m ramp. The visible batter uses `FILL_SLOPE`; the cut uses this.
    Returns `half_width` unchanged when there is no fill, so a caller may use it unconditionally."""
    d = surface_z - ground_z
    if d <= AT_GRADE_TOL or d > FILL_MAX:
        return half_width
    return half_width + d * FILL_SLOPE


def _frange(a, b, step):
    x = a
    while x < b:
        yield x
        x += step


def pier_stations(length, spacing=PIER_SPACING, start=None):
    """Distances along a run at which columns land.

    Laid from the run's MIDPOINT outward, not from one end, so a symmetric span gets a symmetric
    bent line instead of a stub at one abutment."""
    if length <= 0:
        return []
    if start is None:
        n = max(1, int(round(length / spacing)))
        step = length / n
        return [step * (i + 0.5) for i in range(n)]
    return [s for s in _frange(start, length, spacing)]


def run_needed(dz, kind="ramp"):
    """Minimum horizontal run to change height by `dz` -- the number that decides whether a ramp
    fits BEFORE it is drawn, rather than a gate complaining afterwards. A +12 m deck at 6% needs
    200 m, plus taper."""
    return abs(dz) / MAX_GRADE.get(kind, 0.06)


def grade_profile(pts, z0, z1, kind="ramp"):
    """Distribute a z0 -> z1 change along `pts` at a constant grade.
    Returns `(points_with_z, grade, ok)`."""
    segs = [math.dist(a[:2], b[:2]) for a, b in zip(pts, pts[1:])]
    total = sum(segs) or 1.0
    grade = abs(z1 - z0) / total
    out, run = [], 0.0
    for i, p in enumerate(pts):
        if i:
            run += segs[i - 1]
        out.append((p[0], p[1], z0 + (z1 - z0) * (run / total)))
    return out, grade, grade <= MAX_GRADE.get(kind, 0.06) + 1e-9


# --------------------------------------------------------------------------------- profiles

def support_profile(surface_z, ground_z, half_width, deck_thickness=DECK_THICK):
    """Everything the geometry layer needs for ONE station, as plain numbers.

    A dict rather than five parallel functions, because every consumer wants the whole set and a
    caller that fetches four of the five is how a deck ends up holding nothing (defect 7: bare
    columns under no deck). `toe_half_width` is what the GROUND CUT uses; `half_width` is what the
    visible batter starts from."""
    kind = support_kind(surface_z, ground_z)
    d = surface_z - ground_z
    return {
        "kind": kind,
        "delta": d,
        "half_width": half_width,
        "toe_half_width": fill_footprint(surface_z, ground_z, half_width),
        # A deck exists only where the road is genuinely off the ground. A FILL carries the
        # surface on earth, so it has no soffit -- giving it one is what puts a slab inside an
        # embankment.
        "deck_thickness": deck_thickness if kind == SUPPORT_PIER else 0.0,
        "pier_height": max(0.0, d - deck_thickness) if kind == SUPPORT_PIER else 0.0,
        "wall_height": (-d) if kind in (SUPPORT_CUT, SUPPORT_TUNNEL) else 0.0,
        "batter_slope": FILL_SLOPE if kind == SUPPORT_FILL else 0.0,
    }


def kind_runs(kinds):
    """`[(kind, i0, i1)]` -- contiguous runs of one support kind along a chain.

    Transitions between runs are where a structure actually needs something built: a FILL->PIER
    boundary is an abutment, a CUT->TUNNEL boundary is a portal. Finding them is a run-length
    encode, not a special case per pair, which is what keeps 3.3a's "adding a band is cheap"
    true."""
    out = []
    for i, k in enumerate(kinds):
        if out and out[-1][0] == k:
            out[-1][2] = i
        else:
            out.append([k, i, i])
    return [tuple(r) for r in out]


# --------------------------------------------------------------------------------- self-test

def self_test():
    ok = 0

    assert support_kind(0.0, 0.0) == SUPPORT_NONE
    assert support_kind(0.3, 0.0) == SUPPORT_NONE, "0.3 m is inside AT_GRADE_TOL"
    assert support_kind(2.0, 0.0) == SUPPORT_FILL
    assert support_kind(4.0, 0.0) == SUPPORT_FILL, "FILL_MAX is inclusive"
    assert support_kind(12.0, 0.0) == SUPPORT_PIER
    assert support_kind(-1.0, 0.0) == SUPPORT_CUT
    assert support_kind(-9.0, 0.0) == SUPPORT_TUNNEL
    # The same ROAD at three heights, no other edit -- 9 of the plan's verification list.
    assert [support_kind(z, 0.0) for z in (0.0, 2.0, 12.0)] == \
        [SUPPORT_NONE, SUPPORT_FILL, SUPPORT_PIER]
    print("OK: one road at z = 0 / 2 / 12 gives NONE / FILL / PIER with no other change")
    ok += 1

    # A 4.5 m ramp lifted 3 m: the TOE is what eats ground, not the road width.
    assert abs(fill_footprint(3.0, 0.0, 2.25) - (2.25 + 4.5)) < 1e-9
    assert fill_footprint(0.0, 0.0, 2.25) == 2.25, "no fill, no extra footprint"
    assert fill_footprint(12.0, 0.0, 2.25) == 2.25, "a PIER stands on columns, not on earth"
    p = support_profile(3.0, 0.0, 2.25)
    assert p["kind"] == SUPPORT_FILL and abs(p["batter_slope"] - 1.5) < 1e-9
    assert p["deck_thickness"] == 0.0, "an embankment has no soffit slab inside it"
    assert abs(p["toe_half_width"] - 6.75) < 1e-9
    print("OK: FILL is a battered trapezoid -- toe 6.75 m under a 2.25 m half-width, no deck")
    ok += 1

    p = support_profile(12.0, 0.0, 8.0)
    assert p["kind"] == SUPPORT_PIER and p["deck_thickness"] == DECK_THICK
    assert abs(p["pier_height"] - (12.0 - DECK_THICK)) < 1e-9, \
        "the columns carry the SOFFIT, not the driving surface -- or the deck floats"
    assert p["toe_half_width"] == 8.0, "a viaduct does not eat ground between its columns"
    # The deck is sized from the road's own half-width, so an aux lane opening widens it for free.
    wide = support_profile(12.0, 0.0, 11.5)
    assert wide["half_width"] > p["half_width"] and wide["pier_height"] == p["pier_height"]
    print("OK: PIER carries deck + columns, deck widens with the road, ground untouched")
    ok += 1

    st = pier_stations(120.0)
    assert len(st) == 4 and abs(st[0] - 15.0) < 1e-9 and abs(st[-1] - 105.0) < 1e-9
    assert all(abs((st[i] + st[-1 - i]) - 120.0) < 1e-9 for i in range(len(st))), \
        "piers are laid from the MIDPOINT out, so a span is symmetric, not stubbed at one end"
    assert pier_stations(0.0) == [] and pier_stations(-5.0) == []
    print("OK: %d piers on a 120 m span, symmetric about the midpoint" % len(st))
    ok += 1

    assert abs(run_needed(12.0, "ramp") - 200.0) < 1e-9, "a +12 m deck at 6% needs 200 m"
    assert run_needed(12.0, "expressway") > run_needed(12.0, "ramp")
    pts = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (200.0, 0.0, 0.0)]
    got, grade, good = grade_profile(pts, 0.0, 12.0, "ramp")
    assert abs(grade - 0.06) < 1e-9 and good and abs(got[1][2] - 6.0) < 1e-9
    _g2, _r2, bad = grade_profile(pts[:2], 0.0, 12.0, "ramp")
    assert not bad, "12 m over 100 m is 12% -- refused for a ramp"
    print("OK: run_needed/grade_profile agree -- 200 m for +12 m at 6%, 100 m refused")
    ok += 1

    runs = kind_runs([SUPPORT_NONE, SUPPORT_NONE, SUPPORT_FILL, SUPPORT_FILL, SUPPORT_PIER])
    assert runs == [(SUPPORT_NONE, 0, 1), (SUPPORT_FILL, 2, 3), (SUPPORT_PIER, 4, 4)]
    # The BOUNDARIES are where an abutment or a portal goes -- found by run-length encoding, not
    # by a special case per pair of kinds.
    assert len(runs) - 1 == 2
    print("OK: kind_runs finds the transitions an abutment/portal has to sit on")
    ok += 1

    print("\nALL SELF-TESTS PASSED (%d)" % ok)
    return True


if __name__ == "__main__":
    self_test()
