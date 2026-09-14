"""point_flow.py -- the lane-graph FLOW REPORT, pure python3 (PLAN.md 3.1 B8).

Moved out of the Blender flow preview (deleted in B9 with the rest of the Blender authoring UI) so the Godot plugin's Flow Report can ask
`roadkit_cli.py flow` for the same diagnosis the Blender Preview panel shows -- one owner, two views.
It is the one owner of the report.
"""

import math

try:
    from . import point_export as pe
except ImportError:
    import point_export as pe                                                # noqa: E402


class _V(object):
    """Just enough of `mathutils.Vector` for the report: subtraction, length, normalized, x/y/z."""
    __slots__ = ("x", "y", "z")

    def __init__(self, x, y, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)

    def __sub__(self, o):
        return _V(self.x - o.x, self.y - o.y, self.z - o.z)

    def __mul__(self, k):
        return _V(self.x * k, self.y * k, self.z * k)

    @property
    def length(self):
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def normalized(self):
        n = self.length
        return _V(self.x / n, self.y / n, self.z / n) if n > 1e-12 else _V(0.0, 0.0, 0.0)


#: A dead end whose tail is within this of ANOTHER lane's head is a BROKEN LINK, not the edge of
#: the world -- the two lanes are touching and simply were never wired. Deliberately wider than
#: `LaneGraph`'s 4.5 m chain radius: the point is to catch the near-misses too.
JOIN_TOL = 8.0

#: How closely two lanes must agree in heading before "your tail is on my head" means they were
#: meant to chain. Without it, every road in the world reports itself broken: a lane's tail at the
#: edge of the network sits exactly on the head of its OWN opposite-direction twin, which is not a
#: missing link, it is the other carriageway.
JOIN_MAX_TURN_DEG = 75.0


def _end_dir(pts, at_end):
    d = (pts[-1] - pts[-2]) if at_end else (pts[1] - pts[0])
    d.z = 0.0
    return d.normalized() if d.length > 1e-9 else _V(1.0, 0.0, 0.0)


def _compatible(a, b):
    dot = max(-1.0, min(1.0, a.x * b.x + a.y * b.y))
    return math.degrees(math.acos(dot)) <= JOIN_MAX_TURN_DEG


#: How far a successor's head may sit from its predecessor's tail before the edge is nonsense.
#: Generous on purpose -- a connector's ends are solved, not snapped, and `LaneGraph`'s own
#: junction radius is 4.5 m. This is for edges that are WRONG, not edges that are loose.
MISJOIN_TOL = 12.0


def flow_report(doc):
    """THE DIAGNOSIS -- the whole reason a flow preview beats reading the JSON.

    Four facts, all of them about REACHABILITY rather than geometry, because geometry already has
    a gate and reachability had nothing:

        broken       a lane with no successor whose tail is sitting on the head of a lane going
                     the SAME WAY. The two are touching; the edge was simply never written. This
                     is the one that matters -- a car reaching it is reclaimed as route-finished
                     and vanishes.
        open_end     a lane with no successor that genuinely runs off the edge of the network.
                     Expected, and separated out so it cannot drown the previous line.
        unreached    a lane no successor points at, whose head is on the tail of a lane going the
                     same way -- the mirror of `broken`, and equally a missing edge. A lane whose
                     head touches nothing is a road entering the world and is not listed.
        misjoined    a lane whose declared successor's HEAD is not where this lane's TAIL is.
                     The edge exists and points somewhere else entirely -- which every other line
                     here reads as healthy, because they only ever ask whether an edge exists.
        ramp_orphans every lane on a road classed `ramp` that nothing leads to, listed whether or
                     not it touches anything, because "the ramp is always empty" is the in-game
                     symptom of exactly this and nobody ever attributes it to authoring.

    The direction gate is what makes the first three usable. Reachability is a property of a
    DIRECTED graph, and a report that cannot tell a carriageway's far end from its opposite
    carriageway names every road in the world -- which is a report nobody reads."""
    lanes = {l["id"]: l for l in doc.get("lanes", ())}
    road_class = {r["name"]: r.get("road_class", "") for r in doc.get("roads", ())}
    geo = {}
    for l in doc.get("lanes", ()):
        pts = [_V(*pe.blender(p)) for p in l["points"]]
        if len(pts) >= 2:
            geo[l["id"]] = (pts[0], _end_dir(pts, False), pts[-1], _end_dir(pts, True))
    reached = set()
    for l in doc.get("lanes", ()):
        for n in l.get("next") or ():
            reached.add(n)
    broken, open_end, unreached, ramp_orphans, misjoined = [], [], [], [], []
    for lid, l in lanes.items():
        g = geo.get(lid)
        if g is None:
            continue
        head, head_d, tail, tail_d = g
        # A SUCCESSOR THAT IS NOWHERE NEAR (8l). Every check below asks whether an edge EXISTS;
        # none of them asked whether the edge it found goes anywhere. An entrance ramp handed
        # into the stretch of aux slot UPSTREAM of its merge -- 600 m back down the road -- and
        # it was invisible to all four: the ramp had a successor, so not `broken`; the lane was
        # reached, so not `unreached`. In game that is a car reaching the end of a ramp and
        # teleporting, or being reclaimed as route-finished.
        kinds = l.get("next_kinds") or []
        for i, n in enumerate(l.get("next") or ()):
            # A `merge` edge is a lateral hand-over -- "this lane tapers into that one" -- and its
            # target legitimately spans the whole run, so its head is nowhere near this tail. Only
            # edges a car FOLLOWS end to end are chains.
            if (kinds[i] if i < len(kinds) else "chain") == "merge":
                continue
            o = geo.get(n)
            if o is not None and (o[0] - tail).length > MISJOIN_TOL:
                misjoined.append((lid, n, round((o[0] - tail).length, 1)))
        if not l.get("next"):
            near = [i for i, o in geo.items()
                    if i != lid and (o[0] - tail).length <= JOIN_TOL
                    and _compatible(tail_d, o[1])]
            (broken if near else open_end).append((lid, near[:3]))
        if lid not in reached:
            if road_class.get(l["road_name"]) == "ramp":
                ramp_orphans.append(lid)
                continue
            # A LANE THAT OPENS INSIDE ITS RUN IS SUPPOSED TO HAVE NO PREDECESSOR (8l): a
            # deceleration lane that appears after a junction is entered by a LANE CHANGE, and a
            # lane-change edge is `inner_lane`/`outer_lane`, not `next`. `spawnable` is exactly
            # "full width at both ends of its run", which is the question -- and it stays false
            # for a lane that dies inside too, which is equally not a missing predecessor.
            if not l.get("spawnable"):
                continue
            back = [i for i, o in geo.items()
                    if i != lid and (o[2] - head).length <= JOIN_TOL
                    and _compatible(head_d, o[3])]
            if back:
                unreached.append(lid)
    return {"lanes": len(lanes), "junctions": len(doc.get("junctions", ())),
            "broken": broken, "open_end": open_end, "misjoined": misjoined,
            "unreached": unreached, "ramp_orphans": ramp_orphans,
            # THE PATH IS NOT THE LANE. Every other line here is about reachability, which is a
            # property of the graph; this one is about the geometry that graph is drawn on, and it
            # is the only line that can catch a car driving somewhere the road is not.
            "path_off_road": pe.deviating_lanes(doc),
            "spawnable": sum(1 for l in doc.get("lanes", ()) if l.get("spawnable"))}
