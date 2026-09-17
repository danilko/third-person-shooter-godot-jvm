#!/usr/bin/env python3
"""island_shrine_touge.py -- the two-phase shrine touge on the widened plateau (2026-09-17, user decision).

    godot --headless --path . --script tools/godot/dump_height_grid.gd -- <grid.f32> -2200 -2000 1301 1351 2.0
    python3 tools/island_shrine_touge.py <grid.f32> assets/world_source/pieces/IslandRoads.roads.json [--phase 1|2] [--report]

WHAT THE USER ASKED FOR. The shrine road climbs in TWO PHASES so its driving can be watched one at a time:
phase 1 at no more than 10% up the first mountain (the ~281 m plateau, whose east face
`island_widen_first_mountain.py` widened to 1:3) to a STOP on the plateau, then phase 2 on to the 793 m
massif summit. The widening buried the old foot of the plateau, so the three arterials that ran along
it -- nishi_dori, and the west ends of yamate_dori and nogyo_michi -- move to the new toe with it.

HOW. Everything reads the Terrain3D heights AS THEY ARE (the dump), in plan metres (x east, y north) and
the record's own z (Godot Y - `NET_Y`, the network node's offset):
  * the arterials' affected stations are MOVED (same uids, so every junction link survives), one station
    whose span no longer exists is dropped with its neighbours re-joined, and each junction's mouths are
    placed on their roads' own lines ~20 m out; `roadkit_cli.py setback` then solves the real distances;
  * each phase's alignment is `island_v3_terrain.hill_road` -- the switchback walk this codebase already
    owns -- on the dumped field, inside a region that keeps it on its own mountain and clear of the
    arterials; its stations are `island_v3_terrain.stations`, its heights `bench_profile` at the phase's
    limit, so the benches are what the Terrain3D stamp cuts and fills;
  * a STOP is a level straight stretch on the flat top; phase 1 ends there, and phase 2 (road
    `shrine_touge_2`) starts where phase 1 ends and runs on along the same line, so the two roads meet
    straight (a joint, not a junction: a 2-arm pad is refused by the kit).

DRIVEN, THEN FIXED (PLAN.md 3.2d). The first build had 9 + 4 launches at 11 m/s and a dead end. Now:
  * every corner nobody drew is a circular arc (`fillet`), and a hairpin keeps all seven arc points as stations
    (`island_v3_terrain.stations(vertices_first=True)`) -- it had been swept at 7-14 m;
  * the profile has vertical curves (`vertical_curves`, an 80 m moving average: grade-legal by construction);
  * the summit ends in a teardrop turnaround (`summit_loop`, road `shrine_touge_loop`, a 3-arm junction).
The INPUT is the pre-sculpt ground, which is on disk nowhere: `tools/island_touge_presculpt.sh` rebuilds it
exactly, and lists the restore / delta-apply / build / stamp order. The arterial re-route runs once only.
"""
import argparse
import json
import math
import os
import random
import sys

import numpy as np

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import island_v3_terrain as IT                                  # noqa: E402
import island_widen_first_mountain as WM                        # noqa: E402

NET_Y = 0.6                         # the IslandRoads node's Y offset: record z = Godot Y - NET_Y
LIMIT = 0.10                        # both phases: at most 10% (user)
HAIRPIN_R = 18.0                    # a touge, but one a 40 km/h car can take
TOE_Z = 1.2                         # the widened face "starts" where the ground passes this (Godot Y)
TOE_CLEAR = 45.0                    # a phase-1 leg keeps this far west of the toe (the arterial is there)
PLATEAU_TOP_Z = 275.0               # record z of the plateau stop (the face ends at 275.5 Godot Y)
WALK_TOP_Z = 262.0                  # the walk stops here: above it the smooth face meets the ridged rim and
                                    # the walk tangles; a straight ramp at the limit carries the road on up
STOP_LENGTH = 90.0                  # the level stop on the plateau

# The arterials on the new toe. Stations are moved, never re-created, so their uids and links survive.
# Its first span leaves rinkai_dori at 71 deg: a first version ran out at 15 deg, nearly along rinkai, and the
# kit rightly solved that shallow crossing to a 102 m setback. Every centreline sample, and 22 m either side,
# stands on ground no higher than 0.48 m (the city floor), i.e. clear of the widened face.
NISHI_INTERIOR = [(-810.0, -200.0), (-640.0, -240.0), (-420.0, -210.0), (-250.0, -30.0), (-175.0, 170.0), (-140.0, 370.0)]
NISHI_UIDS = ["p_fe587f30", "p_1db97bb0", "p_cbe1f86f", "p_80306ef1"]   # + new stations for the rest
JN = (-90.0, 700.0)                 # nishi_dori end x nogyo_michi x shrine_touge
JY = (NISHI_INTERIOR[-1][0] + (JN[0] - NISHI_INTERIOR[-1][0]) * (500.0 - NISHI_INTERIOR[-1][1]) / (JN[1] - NISHI_INTERIOR[-1][1]),
      500.0)                        # nishi_dori x yamate_dori (T), on nishi's own line
LEAD_IN = 40.0                      # the touge leaves its junction level: climbing at the stop line bent the pad 21%
MOUTH = 20.0


class Field:
    """Bilinear heights over the dump, in record z."""

    def __init__(self, path):
        self.h = np.fromfile(path, dtype=np.float32).reshape(WM.NY, WM.NX)

    def __call__(self, x, y):
        fi = (x - WM.X0) / WM.ST
        fj = (WM.Y0 - y) / WM.ST
        i = int(math.floor(fi)); j = int(math.floor(fj))
        if not (0 <= i < WM.NX - 1 and 0 <= j < WM.NY - 1):
            return -24.0 - NET_Y
        tx, ty = fi - i, fj - j
        h = self.h
        top = h[j, i] * (1 - tx) + h[j, i + 1] * tx
        bot = h[j + 1, i] * (1 - tx) + h[j + 1, i + 1] * tx
        return float(top * (1 - ty) + bot * ty) - NET_Y

    def smoothed(self, radius):
        """A box-blurred copy (radius in metres), for walking an alignment over ridge noise."""
        k = max(1, int(round(radius / WM.ST)))
        h = np.pad(self.h.astype(np.float64), k, mode="edge")
        c = h.cumsum(0).cumsum(1)
        c = np.pad(c, ((1, 0), (1, 0)))
        n = 2 * k + 1
        s = (c[n:, n:] - c[:-n, n:] - c[n:, :-n] + c[:-n, :-n]) / float(n * n)
        out = Field.__new__(Field)
        out.h = s.astype(np.float32)
        return out

    def toe_x(self, y):
        """The easternmost x (scanning west from +100) where the ground stands above `TOE_Z`."""
        for x in np.arange(100.0, -1100.0, -2.0):
            if self(x, y) + NET_Y > TOE_Z:
                return float(x)
        return None


def unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1.0
    return dx / n, dy / n


def new_uid(taken, rng):
    while True:
        u = "p_%08x" % rng.getrandbits(32)
        if u not in taken:
            taken.add(u)
            return u


class Record:
    def __init__(self, path):
        self.path = path
        self.d = json.load(open(path))
        self.P = {p["uid"]: p for p in self.d["points"]}
        self.R = {r["name"]: r for r in self.d["roads"]}
        self.rng = random.Random(20260917)
        self.taken = set(self.P)

    def link(self, a, b, kind="SEGMENT"):
        for x, y in ((a, b), (b, a)):
            L = self.P[x]["links"]
            if not any(l["target"] == y for l in L):
                L.append({"target": y, "type": kind})

    def unlink(self, a, b):
        for x, y in ((a, b), (b, a)):
            self.P[x]["links"] = [l for l in self.P[x]["links"] if l["target"] != y]

    def delete(self, uid):
        """Drop a station and join its chain neighbours (a SEGMENT across the gap)."""
        for r in self.d["roads"]:
            if uid in r["points"]:
                k = r["points"].index(uid)
                prev = r["points"][k - 1] if k > 0 else None
                nxt = r["points"][k + 1] if k + 1 < len(r["points"]) else None
                r["points"].remove(uid)
                for l in list(self.P[uid]["links"]):
                    self.unlink(uid, l["target"])
                if prev and nxt:
                    self.link(prev, nxt)
        self.d["points"] = [p for p in self.d["points"] if p["uid"] != uid]
        del self.P[uid]

    def add_point(self, road, index, xy, z, template=None):
        u = new_uid(self.taken, self.rng)
        p = {"uid": u, "pos": [xy[0], xy[1], z], "links": [], "has_ground_z": True, "ground_z": z}
        for k in ("lanes_fwd", "lanes_bwd"):
            if template and k in template:
                p[k] = template[k]
        self.d["points"].append(p)
        self.P[u] = p
        self.R[road]["points"].insert(index, u)
        return u

    def move(self, uid, xy, field):
        z = field(*xy)
        p = self.P[uid]
        p["pos"] = [round(xy[0], 3), round(xy[1], 3), round(z, 4)]
        p["ground_z"] = round(z, 4)
        p["has_ground_z"] = True
        p.pop("setback_locked", None)

    def save(self):
        with open(self.path + ".tmp", "w") as f:
            json.dump(self.d, f, indent=1, sort_keys=True)
            f.write("\n")
        os.replace(self.path + ".tmp", self.path)


REROUTED_MARK = "p_bfc37122"         # yamate_dori's first-span station, which the re-route deletes


def reroute_arterials(rec, field):
    """nishi_dori, yamate_dori and nogyo_michi onto the widened mountain's new toe."""
    nishi = rec.R["nishi_dori"]["points"]
    # interior stations: four existing + one new, between the rinkai mouth (0) and the yamate mouths
    for uid, xy in zip(NISHI_UIDS, NISHI_INTERIOR):
        rec.move(uid, xy, field)
    tail = NISHI_UIDS[-1]
    mouth_s = nishi[nishi.index(tail) + 1]                   # p_6021a109, the yamate T's south mouth
    rec.unlink(tail, mouth_s)
    for xy in NISHI_INTERIOR[len(NISHI_UIDS):]:
        new = rec.add_point("nishi_dori", nishi.index(tail) + 1, xy, field(*xy), template=rec.P[tail])
        rec.link(tail, new)
        tail = new
    rec.link(tail, mouth_s)
    u = unit(NISHI_INTERIOR[-1], JN)                          # nishi runs on to its end at JN
    rec.move("p_6021a109", (JY[0] - u[0] * MOUTH, JY[1] - u[1] * MOUTH), field)
    rec.move("p_460522ba", (JY[0] + u[0] * MOUTH, JY[1] + u[1] * MOUTH), field)
    rec.move("p_00da7b07", (JN[0] - u[0] * MOUTH, JN[1] - u[1] * MOUTH), field)
    # yamate_dori: its first span now ends inside the T's reach -- drop that station, place the mouth
    rec.delete("p_bfc37122")
    ye = rec.P["p_9007ec27"]["pos"]
    uy = unit(JY, ye)
    rec.move("p_e98e479f", (JY[0] + uy[0] * MOUTH, JY[1] + uy[1] * MOUTH), field)
    # chuo_dori's station 10 m past the chuo x yamate mouth: with yamate's short first span gone that junction
    # solves 1.5 m wider and the mouth would sit on top of it (`station_crowds_mouth`)
    rec.delete("p_22bef844")
    # nogyo_michi: the same
    rec.delete("p_e5aac241")
    ne = rec.P["p_c4b031c5"]["pos"]
    un = unit(JN, ne)
    rec.move("p_e7ee8c1f", (JN[0] + un[0] * MOUTH, JN[1] + un[1] * MOUTH), field)


def _chain(rec, road, first_uid, st, z, ground):
    """Stations 1.. of `st` appended to `road` after `first_uid`, SEGMENT-linked in order. Returns uids."""
    uids = [first_uid]
    for k in range(1, len(st)):
        u = rec.add_point(road, len(rec.R[road]["points"]), st[k], round(z[k], 4),
                          template={"lanes_fwd": 1, "lanes_bwd": 1})
        rec.P[u]["ground_z"] = round(ground[k], 4)
        rec.link(uids[-1], u)
        uids.append(u)
    return uids


def _stats(st, z, ground, arcs, reached, end):
    length = sum(math.dist(a, b) for a, b in zip(st, st[1:]))
    grades = [abs(z[k + 1] - z[k]) / (math.dist(st[k], st[k + 1]) or 1.0) for k in range(len(st) - 1)]
    dz = [a - b for a, b in zip(z, ground)]
    kinks = 0
    for k in range(1, len(st) - 1):
        a = math.atan2(st[k][1] - st[k - 1][1], st[k][0] - st[k - 1][0])
        b = math.atan2(st[k + 1][1] - st[k][1], st[k + 1][0] - st[k][0])
        turn = abs((b - a + math.pi) % (2 * math.pi) - math.pi)
        # a hairpin's own stations turn ~30 deg each on a 18 m arc; a KINK is a sharper turn on a short span
        if turn > math.radians(45.0) and min(math.dist(st[k], st[k - 1]), math.dist(st[k], st[k + 1])) < 25.0:
            kinks += 1
    return {"reached": reached, "kinks": kinks, "stations": len(st), "length": round(length), "hairpins": len(arcs) // IT.HAIRPIN_POINTS,
            "max_grade": round(max(grades) * 100, 1), "rise": round(z[-1] - z[0], 1),
            "fill_max": round(max(dz), 1), "cut_max": round(-min(dz), 1), "end": [round(c) for c in end]}


SPACING = 20.0                      # station spacing on the touge: a vertical curve needs stations to be followed
ARC_KEEP = 8.0                      # below the 9.3 m chord of an 18 m hairpin's 30 deg step, so no arc point merges
CORNER_RADIUS = 40.0                # an unarced corner is rounded to this (40 km/h: 3 m/s2 at 11 m/s) ...
CORNER_MIN_RADIUS = 18.0            # ...and never tighter than a hairpin, or it is reported
CORNER_MIN_DEG = 20.0               # a vertex turning less than this is left to the kit's own curve
END_STRAIGHT = 20.0                 # a fillet stops this short of a road END (a junction mouth stays straight)
VC_LENGTH = 80.0                    # vertical curve: an 80 m moving average, K = 8 m/% on a 10% break


def _heading(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def _turn(a, b, c):
    return (_heading(b, c) - _heading(a, b) + math.pi) % (2 * math.pi) - math.pi


def fillet(line, keep=(), nodrop=()):
    """Round every corner of `line` that turns more than `CORNER_MIN_DEG` and is not in `keep` (a hairpin
    arc, a stop's own arc), with a circular arc of `CORNER_RADIUS` or as much as the two spans allow.

    THE WALK AND THE RAMPS MEET AT CORNERS NOBODY DREW. `hill_road` draws its hairpins as arcs, but the
    level lead-in joins the walk's first leg, and the walk's top joins the ramp onto the plateau, at a single
    vertex: 110 and 100 deg in one station, which the kit's Catmull-Rom swept at 18 m and 7.7 m -- the two
    worst launches in the 11 m/s drive (PLAN.md 3.2d). Collinear vertices are dropped first so a straight run
    counts as ONE span, and corners are served sharpest first, each taking what its spans have left, so a
    gentle bend next to a sharp one does not halve the sharp one's room. Returns `(points, arc_points)`."""
    keep = set(keep)
    nodrop = set(nodrop) | keep
    pts = [line[0]]
    for k in range(1, len(line) - 1):
        if line[k] in keep or abs(_turn(pts[-1], line[k], line[k + 1])) > math.radians(0.5):
            pts.append(line[k])
    pts.append(line[-1])
    while True:
        tangent, worst = _tangents(pts, keep, nodrop)
        if worst is None:
            break
        # A corner with no room for even a hairpin's radius is not a bend anybody drew: it is the walk
        # wobbling over ridge noise beside a hairpin (+36, +31, then the hairpin's -26 deg steps, 10 m apart).
        # Dropping the vertex straightens the wobble; the profile is re-solved from the ground anyway.
        del pts[worst]
    n = len(pts)
    out, arc = [pts[0]], set()
    for k in range(1, n - 1):
        t = tangent.get(k, 0.0)
        th = _turn(pts[k - 1], pts[k], pts[k + 1])
        if t < 0.5:
            out.append(pts[k])
            continue
        r = t / math.tan(abs(th) / 2.0)
        h0 = _heading(pts[k - 1], pts[k])
        p0 = (pts[k][0] - math.cos(h0) * t, pts[k][1] - math.sin(h0) * t)
        side = 1.0 if th > 0 else -1.0
        cx, cy = p0[0] - math.sin(h0) * r * side, p0[1] + math.cos(h0) * r * side
        m = max(2, int(math.ceil(abs(th) * r / 9.5)))
        a0 = math.atan2(p0[1] - cy, p0[0] - cx)
        for j in range(m + 1):
            q = (cx + r * math.cos(a0 + th * j / m), cy + r * math.sin(a0 + th * j / m))
            out.append(q)
            arc.add(q)
    out.append(pts[-1])
    return out, arc


def _tangents(pts, keep, nodrop):
    """`fillet`'s allocation: `({vertex: tangent length}, index of the worst corner that cannot be rounded to
    `CORNER_MIN_RADIUS`, or None)`. Sharpest corners are served first from what their two spans have left."""
    n = len(pts)
    span = [math.dist(pts[k], pts[k + 1]) for k in range(n - 1)]
    left = [s - (END_STRAIGHT if k == 0 else 0.0) - (END_STRAIGHT if k == n - 2 else 0.0) for k, s in enumerate(span)]
    corners = sorted((k for k in range(1, n - 1) if pts[k] not in keep
                      and abs(_turn(pts[k - 1], pts[k], pts[k + 1])) > math.radians(CORNER_MIN_DEG)),
                     key=lambda k: -abs(_turn(pts[k - 1], pts[k], pts[k + 1])))
    tangent, worst, worst_r = {}, None, CORNER_MIN_RADIUS
    for k in corners:
        th = abs(_turn(pts[k - 1], pts[k], pts[k + 1]))
        t = min(CORNER_RADIUS * math.tan(th / 2.0), max(0.0, left[k - 1]), max(0.0, left[k]))
        left[k - 1] -= t
        left[k] -= t
        tangent[k] = t
        r = t / math.tan(th / 2.0)
        if r < worst_r and 1 < k < n - 2 and pts[k] not in nodrop:
            worst, worst_r = k, r
    return tangent, worst


def _protect_hairpins(arcs):
    """`(for simplify and fillet's nodrop, for fillet's keep)`: a hairpin's arc AND the walk point it starts
    from are never dropped (Douglas-Peucker dropped that start, and the first arc point met the walk 18 m back
    at a 22 deg kink; `fillet` dropped it for want of room and left an S-bend), and only the arc's INTERIOR is
    kept unrounded. The walk picks its next heading at the moment it turns, so an arc is tangent to that
    heading and not to the leg it arrives on: measured 50 deg into a hairpin and 32-36 deg out of it, each
    at a vertex the kit swept at a 7-15 m radius. Its two boundary corners are ordinary corners."""
    arcs = set(arcs)
    starts = {i - 1 for i in arcs if i - 1 not in arcs and i >= 1}
    interior = {i for i in arcs if i - 1 in arcs and i + 1 in arcs}
    return arcs | starts, interior


def _stations(line):
    """The touge's stations: every vertex (hairpin, fillet and walk points) plus even marks at `SPACING`."""
    return IT.stations(line, spacing=SPACING, keep=ARC_KEEP, vertices_first=True)


def vertical_curves(st, z, length=VC_LENGTH):
    """Round every grade break with a vertical curve: the profile's moving average over `length` metres of
    arc length, the ends held level (both ends of every touge road are level: a junction lead-in, a stop).

    A MOVING AVERAGE IS A VERTICAL CURVE AND CANNOT BREAK THE GRADE LIMIT. Averaging a piecewise-linear
    profile over a window turns each break of A into a parabola `length` long (K = length / A), and the
    derivative of the average is the average of the derivative, so no span can come out steeper than the
    steepest it was built from. The profile had none: `_profile` holds the limit per span and says nothing
    about the CHANGE, so a level stop met a 10% climb in one station and the car rose 6-9 m/s there."""
    s = [0.0]
    for a, b in zip(st, st[1:]):
        s.append(s[-1] + math.dist(a, b))
    xs = np.arange(0.0, s[-1] + 1.0, 1.0)
    zs = np.interp(xs, s, z)
    h = int(round(length / 2.0))
    pad = np.concatenate([np.full(h, zs[0]), zs, np.full(h, zs[-1])])
    c = np.concatenate([[0.0], np.cumsum(pad)])
    sm = (c[2 * h + 1:] - c[:-2 * h - 1]) / float(2 * h + 1)
    return [float(v) for v in np.interp(s, xs, sm)]


def _worst_grade(st, z):
    return max(abs(z[k + 1] - z[k]) / (math.dist(st[k], st[k + 1]) or 1.0) for k in range(len(st) - 1))


def _profile(st, ground, fixed):
    """`bench_profile` at `LIMIT` with the stations in `fixed` ({index: z}) held, made grade-legal FROM them: the
    downward cone first (a fixed LOW station -- the level lead-in at a junction -- must pull what follows down to
    it; the raise-only cone lifted the lead-in 12 m off its pad instead), then the upward cone (a fixed HIGH
    stop pulls what precedes it up)."""
    z = IT.bench_profile(st, ground, LIMIT)
    for k, v in fixed.items():
        z[k] = v
    z = IT.grade_cone_down(st, z, LIMIT)
    for k, v in fixed.items():
        z[k] = v
    z = IT.grade_cone(st, z, LIMIT)
    for k, v in fixed.items():
        z[k] = v
    return z


def phase1(rec, field):
    """Replace shrine_touge with phase 1: JN up the widened face to a stop on the plateau."""
    road = rec.R["shrine_touge"]
    mouth = road["points"][0]                                 # p_8f08defd, keeps its junction links
    for uid in list(road["points"][1:]):
        rec.delete(uid)
    rec.move(mouth, (JN[0] - MOUTH, JN[1]), field)
    toes = {}

    def toe(y):
        k = int(round(y / 10.0)) * 10
        if k not in toes:
            toes[k] = field.toe_x(k)
        return toes[k]

    def inside(x, y):
        t = toe(y)
        return 40.0 <= y <= 830.0 and t is not None and x <= t - TOE_CLEAR

    start = (toe(JN[1]) - TOE_CLEAR - 5.0, JN[1])             # the first point already inside the region
    # Walked on a lightly smoothed field: where the widened face meets the ridged rim the raw gradient
    # flips every step, and the walk drew ten 70-97 deg zigzags 10 m apart there.
    walk = field.smoothed(SMOOTH_P1)
    lead = (JN[0] - MOUTH - LEAD_IN, JN[1])
    # The walk starts ~15 m up the face, and the road starts level at its junction: that climb has to come out
    # of the walk's own budget, so the walk's grade is lowered until the WHOLE road fits the limit.
    for walk_limit in (LIMIT, 0.095, 0.09, 0.085, 0.08, 0.075, 0.07):
        climb, arcs = IT.hill_road(walk, start, WALK_TOP_Z, walk_limit, leg=700.0, step=10.0, inside=inside,
                                   radius=HAIRPIN_R, heading=(-1.0, 0.0), lookahead=HAIRPIN_R + 10.0)
        reached = walk(*climb[-1]) >= WALK_TOP_Z - 1.0
        h = unit(climb[-1], WM.C)                             # the ramp: up the fall line, onto the plateau
        ramp = (PLATEAU_TOP_Z - WALK_TOP_Z) / LIMIT + 20.0
        arrive = (climb[-1][0] + h[0] * ramp, climb[-1][1] + h[1] * ramp)
        stop, u = _stop_turning(arrive, h, unit(arrive, MASSIF_FOOT))
        pins, inner = _protect_hairpins(arcs)
        line = [(JN[0] - MOUTH, JN[1]), lead] + IT.simplify(climb, 3.0, protect=pins) + [arrive] + stop
        line, _ = fillet(line, keep={climb[i] for i in inner} | set(stop), nodrop={climb[i] for i in pins})
        st = _stations(line)
        ground = [walk(x, y) for (x, y) in st]
        fixed = {k: field(*st[0]) for k in range(len(st)) if math.dist(st[k], st[0]) <= LEAD_IN + 0.5}
        fixed.update({k: PLATEAU_TOP_Z for k in _tail_from(st, arrive)})
        z = vertical_curves(st, _profile(st, ground, fixed))
        worst = _worst_grade(st, z)
        if reached and worst <= LIMIT + 1e-6:
            break
    uids = _chain(rec, "shrine_touge", mouth, st, z, ground)
    return _stats(st, z, [field(*p) for p in st], arcs, reached, st[-1]), (st, z, uids, u)


STOP_RADIUS = 45.0                  # the plateau stop turns on this radius to face the massif


def _stop_turning(arrive, heading, target):
    """The level STOP on the flat plateau: an arc of `STOP_RADIUS` from `heading` round to `target`, then straight
    to `STOP_LENGTH`. Returns (points, final heading). Straight on toward the plateau centre, the stop pointed
    WEST while phase 2 has to go north-east, and the hand-off became a 120 deg bend over a 10 m span whose inside
    lane cut the corner (ground 0.17 m proud of it)."""
    cross = heading[0] * target[1] - heading[1] * target[0]
    dot = heading[0] * target[0] + heading[1] * target[1]
    theta = math.atan2(cross, dot)                            # signed turn, + = left
    side = 1.0 if theta >= 0.0 else -1.0
    nx, ny = -heading[1] * side, heading[0] * side            # toward the centre of the turn
    cx, cy = arrive[0] + nx * STOP_RADIUS, arrive[1] + ny * STOP_RADIUS
    rx, ry = arrive[0] - cx, arrive[1] - cy
    n = max(1, int(math.ceil(abs(theta) * STOP_RADIUS / 10.0)))
    pts = []
    for k in range(1, n + 1):
        a = theta * k / n
        ca, sa = math.cos(a), math.sin(a)
        pts.append((cx + rx * ca - ry * sa, cy + rx * sa + ry * ca))
    fh = (heading[0] * math.cos(theta) - heading[1] * math.sin(theta),
          heading[0] * math.sin(theta) + heading[1] * math.cos(theta))
    arc = abs(theta) * STOP_RADIUS
    rest = max(20.0, STOP_LENGTH - arc)
    end = pts[-1] if pts else arrive
    pts.append((end[0] + fh[0] * rest, end[1] + fh[1] * rest))
    return pts, fh


def _along(p, origin, u):
    return (p[0] - origin[0]) * u[0] + (p[1] - origin[1]) * u[1]


def _tail_from(st, arrive):
    """The trailing stations from the one nearest `arrive` to the end (a stop that TURNS has no single axis)."""
    k0 = min(range(len(st)), key=lambda k: math.dist(st[k], arrive) + (0.0 if k > len(st) // 2 else 1e9))
    return list(range(k0, len(st)))


def _tail(st, arrive, u):
    """The indices of the STOP: the trailing stations at or past `arrive` along `u`, counted back from the end.
    Asked of any station near `arrive` instead, it caught a switchback leg passing 76 m below the summit
    stop, pinned it at the summit height, and the grade cone lifted the whole road ~50 m off its mountain."""
    out = []
    for k in range(len(st) - 1, -1, -1):
        if _along(st[k], arrive, u) < -1.0:
            break
        out.append(k)
    return out


MASSIF_FOOT = (-1000.0, 1150.0)     # the plateau runs north-east into the massif's foot here at ~274 m, level
SUMMIT = (-640.0, 1704.0)           # the massif top (plan), 793 m
SUMMIT_Z = 750.0                    # record z the walk climbs to (the smoothed top is ~760); a stop runs on
SMOOTH_P1 = 20.0                    # phase 1's walk smoothing (the face itself is smooth; the rim is not)
FACE_X = (-1180.0, -300.0)          # the massif's south face, where phase 2 switchbacks (west of -1180 is the sea cliff)
FACE_Y = (1120.0, 1620.0)
SMOOTH_R = 40.0                     # phase 2 walks a box-blurred massif: the ridges are 38 m tall


P2_LEAD = VC_LENGTH / 2.0 + 5.0      # phase 2 leaves the joint level for this long, so the vertical curve at
                                    # the foot of its climb cannot reach the joint and bend phase 1's stop
LOOP_ROAD = "shrine_touge_loop"
LOOP_GAP = 20.0                     # junction centre past the stem's mouth, and each loop mouth from the centre
LOOP_ARM_DEG = 35.0                 # the loop's two arms leave the junction this far either side of straight on
LOOP_REACHES = (70.0, 90.0, 110.0)  # the loop's far side stands this far past the junction centre...
LOOP_AXIS_MAX = 60                  # ...along an axis up to this far either side of straight on, whichever pair
                                    # sits flattest on the summit (straight on, the loop hung 54 m over a slope)


def _loop_line(stem_xy, u, axis, reach):
    """The teardrop for one candidate: junction centre `LOOP_GAP` past the stem, arms `LOOP_ARM_DEG` either
    side of an axis turned `axis` deg from `u`, corners at `reach` along the axis, rounded by `fillet`."""
    J = (stem_xy[0] + u[0] * LOOP_GAP, stem_xy[1] + u[1] * LOOP_GAP)
    ua = _rot(u, axis)
    a_l, a_r = _rot(ua, LOOP_ARM_DEG), _rot(ua, -LOOP_ARM_DEG)
    H = (J[0] + a_l[0] * LOOP_GAP, J[1] + a_l[1] * LOOP_GAP)
    T = (J[0] + a_r[0] * LOOP_GAP, J[1] + a_r[1] * LOOP_GAP)
    far = reach / math.cos(math.radians(LOOP_ARM_DEG))
    A = (J[0] + a_l[0] * far, J[1] + a_l[1] * far)
    B = (J[0] + a_r[0] * far, J[1] + a_r[1] * far)
    return fillet([H, A, B, T])[0]


def _densify(line, step):
    out = [line[0]]
    for a, b in zip(line, line[1:]):
        n = max(1, int(math.ceil(math.dist(a, b) / step)))
        out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(1, n + 1)]
    return out


def phase2(rec, field, p1):
    """shrine_touge_2: from phase 1's stop, level north along the plateau to the massif's foot, switchbacks up
    its south face, a summit stop, and the summit turnaround (`summit_loop`)."""
    st1, z1, uids1, u = p1
    for name in ("shrine_touge_2", LOOP_ROAD):
        if name in rec.R:
            for uid in list(rec.R[name]["points"]):
                rec.delete(uid)
    if "shrine_touge_2" not in rec.R:
        base = json.loads(json.dumps(rec.R["shrine_touge"]["base"]))
        rec.d["roads"].append({"name": "shrine_touge_2", "road_class": rec.R["shrine_touge"]["road_class"],
                               "base": base, "points": []})
        rec.R["shrine_touge_2"] = rec.d["roads"][-1]
    smooth = field.smoothed(SMOOTH_R)
    end1 = st1[-1]
    # the joint: phase 2's first station IS phase 1's last position, and its first span runs on along `u`
    lead = (end1[0] + u[0] * P2_LEAD, end1[1] + u[1] * P2_LEAD)     # u already faces the massif foot
    first = rec.add_point("shrine_touge_2", 0, end1, round(z1[-1], 4), template={"lanes_fwd": 1, "lanes_bwd": 1})
    rec.P[first]["ground_z"] = round(field(*end1), 4)
    rec.link(uids1[-1], first)

    # The SOUTH FACE only, as a band, and "on land" asked of the RAW ground 60 m out: the smoothed field
    # blurs the north-west sea cliff into 250 m of land, and an unbounded walk ran along it and then
    # spiralled the summit.
    def inside(x, y):
        return (FACE_X[0] <= x <= FACE_X[1] and FACE_Y[0] <= y <= FACE_Y[1]
                and min(field(x + dx, y + dy) for dx, dy in ((120, 0), (-120, 0), (0, 120), (0, -120))) > 60.0)

    climb, arcs = IT.hill_road(smooth, MASSIF_FOOT, SUMMIT_Z, LIMIT, leg=1100.0, step=10.0, inside=inside,
                               radius=HAIRPIN_R, heading=unit(lead, MASSIF_FOOT), lookahead=HAIRPIN_R + 10.0)
    arrive = climb[-1]
    reached = smooth(*arrive) >= SUMMIT_Z - 1.0
    us = unit(climb[-2], arrive)                              # the stop runs straight on: a turn onto it was 100 deg
    stop = [(arrive[0] + us[0] * s, arrive[1] + us[1] * s) for s in (STOP_LENGTH / 2.0, STOP_LENGTH)]
    pins, inner = _protect_hairpins(arcs)
    line = [end1, lead] + IT.simplify(climb, 3.0, protect=pins) + stop
    line, _ = fillet(line, keep={climb[i] for i in inner}, nodrop={climb[i] for i in pins})
    st = _stations(line)
    ground = [smooth(x, y) for (x, y) in st]
    fixed = {k: z1[-1] for k in range(len(st)) if math.dist(st[k], end1) <= P2_LEAD + 0.5}
    top = max(SUMMIT_Z, max(smooth(*p) for p in stop))
    fixed.update({k: top for k in _tail(st, arrive, us)})
    z = vertical_curves(st, _profile(st, ground, fixed))
    z[0] = z1[-1]                                             # exact already (level for P2_LEAD); stated, not hoped
    rec.P[first]["pos"][2] = round(z[0], 4)
    uids = _chain(rec, "shrine_touge_2", first, st, z, ground)
    loop_st = summit_loop(rec, field, uids[-1], st[-1], us, z[-1])
    raw = [field(x, y) for (x, y) in st]
    info = _stats(st, z, raw, arcs, reached, st[-1])
    info["worst_grade_after_curves"] = round(_worst_grade(st, z) * 100, 2)
    info["loop_stations"] = len(loop_st)
    info["loop_ground"] = [round(min(field(*p) for p in loop_st) - z[-1], 1), round(max(field(*p) for p in loop_st) - z[-1], 1)]
    return info, (st, z)


def _rot(v, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def summit_loop(rec, field, stem_uid, stem_xy, u, z):
    """The summit TURNAROUND: a level teardrop loop joined to the end of `shrine_touge_2` by a 3-arm junction.

    The summit was a dead end, and a dead end is where a car stops being traffic: the ambient brain finishes
    its lane and `ZoneManager` reclaims it, and the 11 m/s drive ran off the end of the road into the
    hillside. A loop gives every lane a successor -- up the stem, round, and back down -- and the kit already
    owns everything it needs (a junction is three mouths in a clique; a pad with two arms is refused, which is
    why this is not a single pad). The stem's end station becomes a junction mouth; the loop road's head and
    tail are the other two, `LOOP_ARM_DEG` either side of straight on, and the teardrop between them is two
    corners `fillet` rounds at whatever radius the reach leaves room for, placed where the summit is flattest. `roadkit_cli.py setback` then
    solves where the three mouths really stand. Returns the loop's stations."""
    best = None
    for axis in range(-LOOP_AXIS_MAX, LOOP_AXIS_MAX + 1, 5):
        for reach in LOOP_REACHES:
            line = _loop_line(stem_xy, u, axis, reach)
            probe = [stem_xy] + _densify(line, 4.0)
            worst = max(abs(field(*p) - z) for p in probe)
            if best is None or worst < best[0]:
                best = (worst, axis, reach, line)
    worst, axis, reach, line = best
    print("  summit loop: axis %+d deg, reach %d m, ground within %.1f m of the loop" % (axis, reach, worst))
    st = _stations(line)
    if LOOP_ROAD not in rec.R:
        base = json.loads(json.dumps(rec.R["shrine_touge"]["base"]))
        rec.d["roads"].append({"name": LOOP_ROAD, "road_class": rec.R["shrine_touge"]["road_class"],
                               "base": base, "points": []})
        rec.R[LOOP_ROAD] = rec.d["roads"][-1]
    head = rec.add_point(LOOP_ROAD, 0, st[0], round(z, 4), template={"lanes_fwd": 1, "lanes_bwd": 1})
    rec.P[head]["ground_z"] = round(field(*st[0]), 4)
    uids = _chain(rec, LOOP_ROAD, head, st, [z] * len(st), [field(*p) for p in st])
    clique = [stem_uid, uids[0], uids[-1]]
    for i, a in enumerate(clique):
        rec.P[a]["role"] = "INTERSECTION"
        for b in clique[i + 1:]:
            rec.link(a, b, "JUNCTION")
    return st


ROAD_HALF = 8.0                     # the touge's paved half-width: 4.5 m lane + 3.5 m footway
VERGE = 6.0                         # the stamp's flat shelf past the paved edge
CLEARANCE = 0.10                    # road_kit_stamp.gd CLEARANCE
FILL_SLOPE, CUT_SLOPE = 1.5, 1.0    # road_support's batters
SCULPT_REACH = 120.0                # bounds the search
BLEND = 8.0                         # a batter fades back to the natural ground over this


def sculpt(field, rec, roads=("shrine_touge", "shrine_touge_2", LOOP_ROAD)):
    """The mountain CARRIES its road: ground moved onto the touge's own profile, with batters that daylight.

    The kit puts a road more than `FILL_MAX` (4 m) over its natural ground on PIERS, and the Terrain3D stamp
    never fills under a pier -- right for a bay bridge, wrong for a mountain road, where the benches this
    alignment needs would stand the touge on stilts over a hillside. So the natural ground is shaped first:
      * within `ROAD_HALF + VERGE` of the centreline it is the road less `CLEARANCE`;
      * a FILL batter (1:`FILL_SLOPE`) exists only where the road stands above the ground under its own
        centreline, and runs only as wide as that fill's toe (`depth * FILL_SLOPE`) -- a road already ON the
        rim of a steep slope needs no fill down it, and a batter that "fills" any slope steeper than itself
        raised a whole cliff (633 m) and walled the valley rim;
      * a CUT batter (1:`CUT_SLOPE`) likewise runs as wide as its own cut, which is where it daylights on
        ground no steeper than itself; uphill of that the natural face stands (a rock cut);
      * each fades back to the natural ground over `BLEND` metres; the NEAREST segment decides; the sea is
        never filled.
    Returns a new grid (Godot Y, the dump's layout)."""
    H = field.h.astype(np.float64)
    best_d = np.full(H.shape, np.inf)
    best_z = np.zeros(H.shape)
    best_c = np.zeros(H.shape)                                 # the natural ground under the nearest centreline point
    W = ROAD_HALF + VERGE
    segs = []
    for name in roads:
        pts = [rec.P[u]["pos"] for u in rec.R.get(name, {"points": []})["points"]]
        segs += list(zip(pts, pts[1:]))
    # The summit junction's pad: each mouth to the clique's centre, level (a pad is not a road's chord).
    mouths = [u for name in roads for u in rec.R.get(name, {"points": []})["points"]
              if rec.P[u].get("role") == "INTERSECTION" and any(l["type"] == "JUNCTION" for l in rec.P[u]["links"])
              and all(rec.P[l["target"]]["pos"][2] > 100.0 for l in rec.P[u]["links"] if l["type"] == "JUNCTION")]
    if mouths:
        c = [sum(rec.P[u]["pos"][i] for u in mouths) / len(mouths) for i in range(3)]
        segs += [(rec.P[u]["pos"], c) for u in mouths]
    for a, b in segs:
        x0 = min(a[0], b[0]) - SCULPT_REACH - W; x1 = max(a[0], b[0]) + SCULPT_REACH + W
        y0 = min(a[1], b[1]) - SCULPT_REACH - W; y1 = max(a[1], b[1]) + SCULPT_REACH + W
        i0 = max(0, int((x0 - WM.X0) / WM.ST)); i1 = min(WM.NX, int((x1 - WM.X0) / WM.ST) + 1)
        j0 = max(0, int((WM.Y0 - y1) / WM.ST)); j1 = min(WM.NY, int((WM.Y0 - y0) / WM.ST) + 1)
        if i0 >= i1 or j0 >= j1:
            continue
        jj, ii = np.mgrid[j0:j1, i0:i1]
        x = WM.X0 + ii * WM.ST; y = WM.Y0 - jj * WM.ST
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy or 1.0
        t = np.clip(((x - a[0]) * dx + (y - a[1]) * dy) / l2, 0.0, 1.0)
        px, py = a[0] + dx * t, a[1] + dy * t
        d = np.hypot(x - px, y - py)
        zr = a[2] + (b[2] - a[2]) * t + NET_Y - CLEARANCE          # Godot Y of the ground under the road
        ci = np.clip(np.round((px - WM.X0) / WM.ST).astype(int), 0, WM.NX - 1)
        cj = np.clip(np.round((WM.Y0 - py) / WM.ST).astype(int), 0, WM.NY - 1)
        win = best_d[j0:j1, i0:i1]
        nearer = d < win
        win[nearer] = d[nearer]
        best_z[j0:j1, i0:i1][nearer] = zr[nearer]
        best_c[j0:j1, i0:i1][nearer] = H[cj, ci][nearer]
    near = best_d <= SCULPT_REACH + W
    over = np.maximum(best_d - W, 0.0)
    fill = np.maximum(best_z - best_c, 0.0)                    # how far the road stands above its own ground
    cut = np.maximum(best_c - best_z, 0.0)                     # ...or below it
    floor = best_z - over / FILL_SLOPE
    cap = best_z + over / CUT_SLOPE
    target = np.clip(H, floor, cap)
    reach = np.where(target > H, fill * FILL_SLOPE, cut * CUT_SLOPE) + 1.0
    w = 1.0 - np.clip((over - reach) / BLEND, 0.0, 1.0)
    w = w * w * (3.0 - 2.0 * w)
    w[best_d <= W] = 1.0
    out = H.copy()
    out[near] = (H + w * (target - H))[near]
    sea = H <= 0.0
    out[sea] = np.minimum(out[sea], H[sea])                   # the sea is never filled: the coast does not move
    return out.astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("grid")
    ap.add_argument("record")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sculpt", default="", help="write the terrain grid that carries the touge here")
    a = ap.parse_args()
    field = Field(a.grid)
    rec = Record(a.record)
    # The re-route is applied ONCE: it drops stations, and a second pass would find them gone. A record whose
    # arterials are already on the new toe keeps them and only the touge is rebuilt (PLAN.md 3.2d).
    if REROUTED_MARK in rec.P:
        reroute_arterials(rec, field)
    else:
        print("arterials: already on the new toe (%s dropped), not re-routed" % REROUTED_MARK)
    info1, p1 = phase1(rec, field)
    print("phase 1:", json.dumps(info1))
    info2, p2 = phase2(rec, field, p1)
    print("phase 2:", json.dumps(info2))
    if a.sculpt:
        g = sculpt(field, rec)
        d = g - field.h
        print("sculpt: raised %d cells (max %.1f m), lowered %d cells (max %.1f m)"
              % ((d > 0.05).sum(), d.max(), (d < -0.05).sum(), -d.min()))
        g.tofile(a.sculpt)
    if not a.dry_run:
        rec.save()
        print("saved", a.record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
