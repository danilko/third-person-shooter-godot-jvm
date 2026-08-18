"""road_geometry.py -- pure-Python (no bpy), self-tested. Can a car actually take this at speed?
`python3 lib/road_geometry.py` self-tests, same convention as `lane_joints.py`/`lane_kit.py`.

`lane_joints` asks whether two lanes MEET. This asks whether one lane is DRIVABLE: is the climb too
steep, is the curve too tight for its design speed, and how much bank would it need. Those are the
same question asked three ways, and they are linked by one equation, so they live together.

THE ONE EQUATION (AASHTO, metric). A vehicle on a curve is held by banking plus tyre grip:

    e + f = V^2 / (127 R)          V km/h, R metres, e and f as rates (0.06 = 6%)

`e` is superelevation (the road's cross-slope INTO the turn) and `f` is the side-friction factor a
comfortable driver will accept -- not the tyre's limit, a comfort figure, which is why it FALLS as
speed rises (see `SIDE_FRICTION`). Everything here is that equation rearranged:

    the tightest legal curve         R_min  = V^2 / (127 (e_max + f))
    the bank this curve demands      e_req  = V^2 / (127 R) - f
    the speed this curve supports    V_max  = sqrt(127 R (e_max + f))

WHY THAT MATTERS FOR A RAMP, and why banking is not a free fix. A ramp at R = 20 m asked to carry
45 km/h needs `e_req = 45^2/(127*20.6) - 0.21 = 0.58` -- **58% superelevation**, a wall, not a road.
There is no bank that rescues a curve that tight; the geometry has to change (a bigger radius, which
costs length). So a report that only said "add more bank" would be worse than useless. This module
reports the required bank AND, when that exceeds what a road may physically carry, says what radius
or what speed would actually work.

GRADE IS MEASURED OVER A WINDOW, NOT PER SPAN. A resampled polyline draped over terrain has metre-
scale noise in z; a single 12 m span can read 10% while the road climbs 0.2 m over its whole length.
Grade is what a vehicle experiences over a distance, so it is measured over `GRADE_WINDOW_M` and a
short spike is reported separately as a KINK (a comfort/scrape defect, a different fix).
"""

import math

#: Side friction factor by design speed (km/h) -- AASHTO Green Book comfort values, linearly
#: interpolated between. Falls with speed: at 100 km/h a driver tolerates far less lateral push
#: before a curve feels wrong than at 30.
SIDE_FRICTION = [
    (20, 0.35), (30, 0.28), (40, 0.23), (50, 0.19), (60, 0.17),
    (70, 0.15), (80, 0.14), (90, 0.13), (100, 0.12), (110, 0.11), (120, 0.09),
]

#: Ramp grade. The user-stated guideline is 5%-7%: 5% is the design target, 7% the absolute cap
#: (steeper is used only on short, low-speed connectors).
GRADE_TARGET = 0.05
GRADE_MAX = 0.07

#: Superelevation. 6% is the normal urban maximum (it must stay drivable at a crawl and in the wet;
#: a steeply banked road is unpleasant and unsafe when stopped on it). 10% is the absolute ceiling
#: used on high-speed rural interchange loops with no ice.
SUPERELEVATION_MAX = 0.06
SUPERELEVATION_CEILING = 0.10

#: Grade is averaged over this distance -- see the module docstring.
GRADE_WINDOW_M = 20.0

#: A change of grade sharper than this between successive windows is a vertical kink: cars scrape
#: or take air, independently of whether either grade on its own is legal.
KINK_GRADE_DELTA = 0.04

#: Radii above this are a straight for our purposes; reporting "R = 71524 m" as a curve is noise.
STRAIGHT_R_M = 5000.0


def side_friction(speed_kmh):
    """Comfort side-friction factor `f` at a design speed, interpolated from `SIDE_FRICTION`."""
    tbl = SIDE_FRICTION
    if speed_kmh <= tbl[0][0]:
        return tbl[0][1]
    if speed_kmh >= tbl[-1][0]:
        return tbl[-1][1]
    for (v0, f0), (v1, f1) in zip(tbl, tbl[1:]):
        if v0 <= speed_kmh <= v1:
            t = (speed_kmh - v0) / float(v1 - v0)
            return f0 + (f1 - f0) * t
    return tbl[-1][1]


def min_radius(speed_kmh, e_max=SUPERELEVATION_MAX):
    """Tightest curve a `speed_kmh` design speed may use, given `e_max` of available bank."""
    return speed_kmh * speed_kmh / (127.0 * (e_max + side_friction(speed_kmh)))


def required_superelevation(speed_kmh, radius_m):
    """Bank this curve needs at this speed. NEGATIVE means friction alone is more than enough --
    a gentle curve needs no banking at all, which is the common case and not a defect."""
    if radius_m <= 0 or radius_m == float("inf"):
        return 0.0
    return speed_kmh * speed_kmh / (127.0 * radius_m) - side_friction(speed_kmh)


def comfortable_speed(radius_m, e=SUPERELEVATION_MAX):
    """The speed this radius genuinely supports with `e` of bank -- what to SIGN the ramp at if the
    geometry is not going to change. Solved by iteration because `f` itself depends on speed."""
    if radius_m <= 0:
        return 0.0
    v = 30.0
    for _ in range(40):
        v = math.sqrt(127.0 * radius_m * (e + side_friction(v)))
    return v


def _xy(p, axes):
    return (float(p[axes[0]]), float(p[axes[1]]))


def _z(p, axes):
    """The height component -- whichever index is not one of the two ground axes."""
    return float(p[({0, 1, 2} - set(axes)).pop()])


#: Curvature is measured across this arc length, never between adjacent points -- see
#: `min_radius_along`.
CURVATURE_WINDOW_M = 25.0


def min_radius_along(pts_xy, window_m=CURVATURE_WINDOW_M):
    """Tightest radius along a polyline, measured over a FIXED ARC-LENGTH WINDOW.

    USE THIS, never `curvature_radius` on adjacent triples, whenever the answer is compared against
    a design minimum. Menger radius through three ADJACENT points measures the discretisation
    sagitta rather than the curve, so it gets WORSE the finer the sampling -- `tools/island_v3_plan
    .min_radius_windowed`, which this mirrors, records one 140 m arc reading 140.9 at a 20 m
    resample, 77.1 at 12 m and 38.8 at 6 m. Sampling the outer two points a fixed DISTANCE away
    makes the result a property of the geometry instead of the resample step.

    This module shipped with the adjacent-triple version for one afternoon and the gate immediately
    "found" R = 3 m kinks in an 80 km/h expressway -- a number produced by two nearly-coincident
    points at a ramp taper, not by anything on the ground. A check that cries wolf on its first run
    is worse than no check, because the next real finding gets ignored with it.

    ONE BLIND SPOT, AND IT IS THE PRICE OF THE ABOVE. Sampling by ARC LENGTH is what makes this
    immune to sampling density, and at a HAIRPIN it is exactly what defeats it: 25 m of arc back
    and 25 m of arc forward land on the two LEGS of the U, only a few metres apart in space, and
    the circle through three nearly-collinear points is enormous. Measured on a built ramp spine
    that visibly doubles back -- (151.2, 499.7) -> (145.3, 505.2) -> (148.5, 502.2) -- this
    function returned 70.2 m, comfortably inside a 45 km/h ramp's 59.1 m minimum.

    So a radius test is NOT a validity test. A polyline that reverses on itself has to be caught
    by TURNING, not by curvature: see `tools/island_v3_plan.turns_back`, which any search that
    optimises against this function must apply first, or it will buy its radius by folding."""
    clean = [pts_xy[0]]
    for p in pts_xy[1:]:
        if math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 0.5:
            clean.append(p)
    n = len(clean)
    if n < 3:
        return float("inf")
    cum = [0.0]
    for a, b in zip(clean, clean[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    if cum[-1] < 2.0 * window_m:
        window_m = max(4.0, cum[-1] / 2.5)
    best = float("inf")
    for i in range(n):
        lo = hi = i
        while lo > 0 and cum[i] - cum[lo] < window_m:
            lo -= 1
        while hi < n - 1 and cum[hi] - cum[i] < window_m:
            hi += 1
        if cum[i] - cum[lo] < window_m * 0.6 or cum[hi] - cum[i] < window_m * 0.6:
            continue                      # too near an end to have a full window either side
        best = min(best, curvature_radius(clean[lo], clean[i], clean[hi]))
    return best


def curvature_radius(a, b, c):
    """Radius of the circle through three points (the menger curvature), `inf` when collinear.

    For per-point inspection only -- `min_radius_along` is what a design minimum is compared to."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    la = math.hypot(bx - ax, by - ay)
    lb = math.hypot(cx - bx, cy - by)
    lc = math.hypot(cx - ax, cy - ay)
    area2 = abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay))
    if area2 < 1e-12 or la < 1e-9 or lb < 1e-9:
        return float("inf")
    return la * lb * lc / (2.0 * area2)


def _windowed_grades(pts, axes, window_m):
    """`[(station_m, grade), ...]` -- rise over run measured across `window_m`, not per span."""
    if len(pts) < 2:
        return []
    xy = [_xy(p, axes) for p in pts]
    z = [_z(p, axes) for p in pts]
    station = [0.0]
    for i in range(len(xy) - 1):
        station.append(station[-1] + math.hypot(xy[i + 1][0] - xy[i][0], xy[i + 1][1] - xy[i][1]))
    out = []
    j = 0
    for i in range(len(pts)):
        while j < len(pts) - 1 and station[j] - station[i] < window_m:
            j += 1
        run = station[j] - station[i]
        if run < window_m:
            # The remaining tail is shorter than a full window. Stop rather than measure a short
            # one: a partial window is exactly as noise-prone as a single span, which is the whole
            # thing this function exists to avoid (a half-window tail on a wobbling near-flat road
            # reported -3.2% while every full window read 0.2%).
            break
        out.append((station[i], (z[j] - z[i]) / run))
    if not out and station[-1] > 1e-6:
        # A piece shorter than half a window still has a grade; measure it end to end rather than
        # reporting nothing, or every short connector silently escapes the check.
        out.append((0.0, (z[-1] - z[0]) / station[-1]))
    return out


#: Degrees a SINGLE vertex may turn through before it stops being a curve and starts being a
#: corner. A road polyline is swept, not smoothed, so whatever angle sits at a control point is
#: the angle the driver gets: 25 deg in one step is a visible facet in the pavement and a
#: steering input no vehicle makes at speed. Deliberately independent of the radius checks --
#: those measure the curve over a WINDOW and are blind to a single bad vertex by design (that is
#: what makes them immune to sampling density), so nothing else in this module reports one.
CORNER_DEG = 25.0

#: Degrees of NET turn past which a road has doubled back on itself. Mirrors
#: `tools/island_v3_plan.MAX_RAMP_TURN_DEG` -- see `min_radius_along` for why a radius test
#: cannot catch this and a turning test must.
REVERSAL_DEG = 135.0


def heading_deltas(points, axes=(0, 1)):
    """`[(station, degrees_turned), ...]` at each interior vertex -- the raw per-point steering
    input the alignment asks for. Coincident points are skipped rather than reported as a 0 deg
    turn, so sampling artefacts cannot dilute the maximum."""
    xy = [_xy(p, axes) for p in points]
    out, prev_h, station = [], None, 0.0
    for i in range(len(xy) - 1):
        dx, dy = xy[i + 1][0] - xy[i][0], xy[i + 1][1] - xy[i][1]
        seg = math.hypot(dx, dy)
        if seg < 1e-9:
            continue
        h = math.degrees(math.atan2(dy, dx))
        if prev_h is not None:
            out.append((station, (h - prev_h + 180.0) % 360.0 - 180.0))
        prev_h, station = h, station + seg
    return out


def turn_excursion(points, axes=(0, 1)):
    """The largest NET heading change from the start, in degrees. An S-curve swings one way then
    the other and comes back toward zero; a hairpin accumulates and does not."""
    cum, worst = 0.0, 0.0
    for _st, d in heading_deltas(points, axes):
        cum += d
        worst = max(worst, abs(cum))
    return worst


def analyse(points, speed_kmh, axes=(0, 1), e_max=SUPERELEVATION_MAX,
            grade_max=GRADE_MAX, window_m=GRADE_WINDOW_M):
    """Everything measurable about one lane's alignment, as a dict.

    `max_grade`/`at_station`, `max_kink`, `min_radius_m`, `required_e` (bank the tightest curve
    demands at `speed_kmh`), `supported_speed_kmh` (what the tightest curve actually carries with
    `e_max`), `length_m`, and `problems` -- a list of `(code, detail)`.

    Codes, deliberately distinct because each wants a different fix:
        `GRADE`       too steep over a real distance -- the climb needs more length
        `KINK`        grade changes too abruptly -- a vertical curve is missing
        `RADIUS`      too tight to bank into compliance at this speed -- geometry must change
        `SUPERELEV`   needs more bank than `e_max` but is still within the physical ceiling
        `CORNER`      one vertex turns too sharply -- a facet in the road, not a curve

    `turn_excursion_deg` is also reported, as a MEASUREMENT and never as a verdict. Doubling back
    is not an error in itself -- a ring road turns through 360 deg, and a switchback, a loop ramp
    and a junction's U-turn movement all reverse on purpose -- so a consumer that cares (a ramp
    SEARCH, which must not buy its radius by folding; see `tools/island_v3_plan.turns_back`)
    applies its own threshold. What matters here is that the number exists at all: at a hairpin a
    windowed radius reads the two legs of the U as nearly straight, so `min_radius_m` can be
    comfortably wrong and nothing else in this dict would say so.
    """
    res = {"max_grade": 0.0, "at_station": 0.0, "max_kink": 0.0, "min_radius_m": float("inf"),
           "required_e": 0.0, "supported_speed_kmh": None, "length_m": 0.0,
           "max_corner_deg": 0.0, "corner_at": 0.0, "turn_excursion_deg": 0.0, "problems": []}
    if len(points) < 2:
        return res
    xy = [_xy(p, axes) for p in points]
    res["length_m"] = sum(math.hypot(xy[i + 1][0] - xy[i][0], xy[i + 1][1] - xy[i][1])
                          for i in range(len(xy) - 1))

    grades = _windowed_grades(points, axes, window_m)
    for st, g in grades:
        if abs(g) > abs(res["max_grade"]):
            res["max_grade"], res["at_station"] = g, st
    for (_s0, g0), (_s1, g1) in zip(grades, grades[1:]):
        res["max_kink"] = max(res["max_kink"], abs(g1 - g0))

    res["min_radius_m"] = min_radius_along(xy)

    # PER-VERTEX HEADING, which nothing else here measures. `min_radius_along` samples a fixed arc
    # length either side of each point precisely so that a finer resample cannot make a road look
    # worse -- and that same property makes it unable to see either a single sharp vertex or a
    # hairpin. Both are alignment errors a driver feels immediately, so they are reported here
    # rather than left to be noticed in the viewport.
    deltas = heading_deltas(points, axes)
    for st, d in deltas:
        if abs(d) > abs(res["max_corner_deg"]):
            res["max_corner_deg"], res["corner_at"] = d, st
    res["turn_excursion_deg"] = turn_excursion(points, axes)

    if abs(res["max_corner_deg"]) > CORNER_DEG:
        res["problems"].append(
            ("CORNER", "%.0f deg turn at a single vertex, station %.0f m (max %.0f deg) -- the "
                       "pavement is swept through this point, so that angle is a facet in the "
                       "road. Move or subdivide the control point"
             % (abs(res["max_corner_deg"]), res["corner_at"], CORNER_DEG)))
    if abs(res["max_grade"]) > grade_max:
        res["problems"].append(
            ("GRADE", "%.1f%% grade at station %.0f m (max %.1f%%) -- the climb needs about "
                      "%.0f m more length"
             % (res["max_grade"] * 100.0, res["at_station"], grade_max * 100.0,
                res["length_m"] * (abs(res["max_grade"]) / grade_max - 1.0))))
    if res["max_kink"] > KINK_GRADE_DELTA:
        res["problems"].append(
            ("KINK", "grade changes by %.1f%% between adjacent %.0f m windows (max %.1f%%) -- "
                     "a vertical curve is missing here"
             % (res["max_kink"] * 100.0, window_m, KINK_GRADE_DELTA * 100.0)))

    R = res["min_radius_m"]
    if R < STRAIGHT_R_M:
        res["required_e"] = required_superelevation(speed_kmh, R)
        res["supported_speed_kmh"] = comfortable_speed(R, e_max)
        need = min_radius(speed_kmh, e_max)
        if res["required_e"] > SUPERELEVATION_CEILING:
            res["problems"].append(
                ("RADIUS", "R=%.0f m needs %.0f%% bank at %.0f km/h -- past the %.0f%% ceiling, so "
                           "NO amount of banking fixes it. Either open the curve to R>=%.0f m or "
                           "sign it at %.0f km/h"
                 % (R, res["required_e"] * 100.0, speed_kmh, SUPERELEVATION_CEILING * 100.0,
                    need, res["supported_speed_kmh"])))
        elif res["required_e"] > e_max:
            res["problems"].append(
                ("SUPERELEV", "R=%.0f m needs %.0f%% bank at %.0f km/h, above the %.0f%% norm "
                              "(ceiling %.0f%%) -- bankable, but it must actually be banked"
                 % (R, res["required_e"] * 100.0, speed_kmh, e_max * 100.0,
                    SUPERELEVATION_CEILING * 100.0)))

    return res


def describe(name, res):
    """One line per problem, naming the lane and what to do about it."""
    return ["%s: %s -- %s" % (name, code, detail) for code, detail in res["problems"]]


# ------------------------------------------------------------------------------------ self-test

def _line(n, dx, dz, x0=0.0, z0=0.0):
    return [(x0 + i * dx, 0.0, z0 + i * dz) for i in range(n)]


def _arc(radius, sweep_deg, n=20, z=0.0):
    return [(radius * math.sin(math.radians(sweep_deg) * i / (n - 1)),
             radius * (1.0 - math.cos(math.radians(sweep_deg) * i / (n - 1))), z)
            for i in range(n)]


def self_test():
    # --- the equation itself, both ways round.
    f50 = side_friction(50)
    assert abs(f50 - 0.19) < 1e-9, f50
    assert abs(side_friction(45) - 0.21) < 1e-9, side_friction(45)
    R = min_radius(45, 0.06)
    assert abs(R - 45 * 45 / (127.0 * (0.06 + 0.21))) < 1e-9, R
    assert abs(required_superelevation(45, R) - 0.06) < 1e-9, \
        "at exactly R_min the required bank must equal e_max -- the two are one equation"
    print("OK: R_min(45 km/h, e=6%%) = %.1f m, and that radius demands exactly 6%% back" % R)

    # --- a gentle curve needs NO bank; that is not a defect.
    assert required_superelevation(45, 400.0) < 0, "friction alone carries a 400 m curve at 45"
    print("OK: a 400 m curve at 45 km/h needs no superelevation at all (negative requirement)")

    # --- comfortable_speed inverts min_radius.
    v = comfortable_speed(R, 0.06)
    assert abs(v - 45.0) < 0.5, v
    print("OK: comfortable_speed inverts min_radius (%.1f km/h back from %.1f m)" % (v, R))

    # --- GRADE: 4% over 200 m passes, 9% fails and the report says how much longer it must be.
    ok = analyse(_line(21, 10.0, 0.4), 45)
    assert abs(ok["max_grade"] - 0.04) < 1e-9 and not ok["problems"], ok
    bad = analyse(_line(21, 10.0, 0.9), 45)
    codes = [c for c, _d in bad["problems"]]
    assert "GRADE" in codes, bad
    print("OK: 4%% grade passes; 9%% is reported (%s)" % bad["problems"][0][1])

    # --- NOISE IS NOT A GRADE. A road that climbs 0.2 m over 120 m but wobbles +/-0.4 m point to
    # point must NOT report the per-span 10%; that is the false positive the window exists for.
    noisy = [(i * 12.0, 0.0, 0.4 * (i % 2) + 0.2 * i / 10.0) for i in range(11)]
    res = analyse(noisy, 45)
    assert abs(res["max_grade"]) < 0.03, \
        "a wobble around a near-flat road must not read as a steep grade, got %.1f%%" % (
            res["max_grade"] * 100.0)
    print("OK: point-to-point z noise (per-span 3.3%%) averages to %.1f%% over a 20 m window "
          "instead of being reported as a climb" % (res["max_grade"] * 100.0))

    # --- RADIUS: the real island case. A 20 m ramp radius at 45 km/h cannot be banked into
    # compliance at all, and the message must say so rather than asking for more bank.
    tight = analyse(_arc(20.6, 90.0), 45)
    codes = [c for c, _d in tight["problems"]]
    assert "RADIUS" in codes, tight
    assert tight["required_e"] > SUPERELEVATION_CEILING, tight["required_e"]
    assert 20.0 < tight["supported_speed_kmh"] < 32.0, tight["supported_speed_kmh"]
    print("OK: R=20.6 m at 45 km/h -> %.0f%% bank required, past the ceiling; reported as "
          "RADIUS with a %.0f km/h honest speed"
          % (tight["required_e"] * 100.0, tight["supported_speed_kmh"]))

    # --- SUPERELEV: a curve that IS bankable into compliance is a different, lesser problem.
    mid = analyse(_arc(58.0, 90.0), 45)
    codes = [c for c, _d in mid["problems"]]
    assert codes == ["SUPERELEV"], (codes, mid)
    assert SUPERELEVATION_MAX < mid["required_e"] <= SUPERELEVATION_CEILING, mid["required_e"]
    print("OK: R=58 m at 45 km/h needs %.1f%% -- SUPERELEV (bankable), not RADIUS (hopeless)"
          % (mid["required_e"] * 100.0))

    # --- SAMPLING MUST NOT CHANGE THE ANSWER. The same 140 m arc at three resample steps: the
    # adjacent-triple measure fell from 141 to 39 as sampling got finer, which is what made the
    # gate report R=3 m kinks in a straight expressway on its first run.
    for step_deg, want in ((8.0, 140.0), (4.0, 140.0), (1.5, 140.0)):
        n = int(90.0 / step_deg) + 1
        arc = [(140.0 * math.sin(math.radians(90.0) * i / (n - 1)),
                140.0 * (1.0 - math.cos(math.radians(90.0) * i / (n - 1))), 0.0)
               for i in range(n)]
        got = min_radius_along([(p[0], p[1]) for p in arc])
        assert abs(got - want) / want < 0.06, (step_deg, got)
    print("OK: a 140 m arc measures ~140 m at every resample step (the adjacent-triple measure "
          "read 141 / 77 / 39 for the same curve)")

    # --- a straight is never a radius problem however long.
    assert not analyse(_line(30, 10.0, 0.0), 100)["problems"]
    print("OK: a flat straight raises nothing at any speed")

    # --- KINK: two legal grades meeting abruptly is still a defect.
    kinked = _line(11, 10.0, 0.5) + [(100.0 + i * 10.0, 0.0, 5.0 - i * 0.5) for i in range(1, 11)]
    codes = [c for c, _d in analyse(kinked, 45)["problems"]]
    assert "KINK" in codes, analyse(kinked, 45)
    print("OK: +5%% meeting -5%% is a KINK even though both grades are individually legal")

    # --- GODOT AXES: the same road measured in the exported frame gives the same answer. This is
    # the `lane_joints` axis bug's twin -- height and northing swap, and a silent mix-up here would
    # read the road's northing as its elevation and report a cliff.
    blender = _line(21, 10.0, 0.4)
    godot = [(p[0], p[2], -p[1]) for p in blender]
    a = analyse(blender, 45, axes=(0, 1))
    b = analyse(godot, 45, axes=(0, 2))
    assert abs(a["max_grade"] - b["max_grade"]) < 1e-9, (a["max_grade"], b["max_grade"])
    print("OK: identical result in Blender (0,1) and Godot (0,2) frames -- %.1f%% either way"
          % (a["max_grade"] * 100.0))

    # --- a single sharp vertex is a CORNER, and it is reported EVEN WHEN THE ROAD PASSES ITS
    # SPEED. The two tests answer different questions and are both worth asking: `RADIUS` asks
    # "can a car hold this at the design speed", and stays quiet on a slow street; `CORNER` asks
    # "is this a curve at all", and a 40 deg step at one control point is a visible facet in the
    # swept pavement whatever the speed limit says. They also point at different fixes -- open
    # the curve, versus move or subdivide this one point.
    dog = [(0.0, 0.0, 0.0), (60.0, 0.0, 0.0), (100.0, 34.0, 0.0), (160.0, 84.0, 0.0)]
    r = analyse(dog, 30)
    codes = [c for c, _d in r["problems"]]
    assert "CORNER" in codes and "RADIUS" not in codes, r
    assert abs(abs(r["max_corner_deg"]) - 40.4) < 1.0, r["max_corner_deg"]
    print("OK: a 40 deg dogleg on a 30 km/h street is reported as CORNER while RADIUS stays "
          "silent -- 'can a car hold it' and 'is it a curve' are different questions")

    # --- ...and a genuine curve of the same total turn is NOT a corner. The check must not
    # punish a road for bending, only for bending all at once.
    smooth = [(p[0], p[1], 0.0) for p in _arc(200.0, 40.0, n=25)]
    assert "CORNER" not in [c for c, _d in analyse(smooth, 50)["problems"]], analyse(smooth, 50)
    print("OK: a 40 deg arc sampled at 25 points is NOT a corner -- turning is fine, turning in "
          "one step is not")

    # --- a fold is MEASURED but never a verdict. `turn_excursion` exists because a windowed
    # radius cannot see a hairpin (see `min_radius_along`), so a consumer that must not fold --
    # a ramp SEARCH -- has a number to reject on. It is not raised as a problem here: a ring road
    # turns through 360 deg, and a switchback, a loop ramp and a junction U-turn all reverse on
    # purpose. Measured on the island, treating a fold as an error flagged 31 mostly-correct
    # roads; the one case that mattered belongs to `island_v3_plan.turns_back`, at the search.
    hair = [(0.0, 0.0, 0.0), (300.0, 0.0, 0.0), (360.0, 20.0, 0.0), (390.0, 60.0, 0.0),
            (360.0, 100.0, 0.0), (300.0, 120.0, 0.0), (0.0, 120.0, 0.0)]
    r = analyse(hair, 45)
    assert r["turn_excursion_deg"] > 170.0, r["turn_excursion_deg"]
    assert "REVERSAL" not in [c for c, _d in r["problems"]], r
    assert turn_excursion(_line(20, 20.0, 0.0)) < 1e-9
    print("OK: a U-turn is MEASURED (%.0f deg of net turn) but not called an error -- ring roads, "
          "switchbacks and loop ramps all reverse on purpose" % r["turn_excursion_deg"])

    # --- a straight road reports neither, and a two-point line does not divide by zero.
    assert analyse(_line(20, 20.0, 0.0), 80)["problems"] == []
    assert heading_deltas([(0, 0, 0), (10, 0, 0)]) == []
    assert turn_excursion([(0, 0, 0)]) == 0.0
    print("OK: a straight road is clean and a degenerate one is silent, not a false positive")

    print("ALL SELF-TESTS PASSED")


if __name__ == "__main__":
    self_test()
