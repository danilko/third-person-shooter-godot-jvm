#!/usr/bin/env python3
"""WHAT A STATION IS -- the one owner (PLAN.md "NEXT STEP 2026-09-27": every station rebuilt from the three layout
sketches, `assets/world_source/reference/stations_layout_*_2026-09-27.png`).

    python3 tools/station_layout.py [--self-test] [--report] [--layout tokyo_straight]

Three FORMS, and a station is one of them (`FORMS`):
  * `open_air`      (地上駅): one two-way lane at grade, a SIDE PLATFORM each side (相対式), each with a shed and a
                    fence along its outer edge, and its OWN building IN LINE with the platform's END -- platform ->
                    gates inside the building -> the street. No footbridge, no yard.
  * `ground_hub`    (橋上駅): lanes at grade with island / side platforms; a walled building CAPS the passenger lanes
                    and carries an airbridge over them: street -> gates -> up into the airbridge -> down to a platform.
  * `elevated_hub`  (高架駅): platforms on the viaduct; the F1 building fills the ground floor up to the deck (the
                    rail's own piers stand inside it): street -> gates -> up to a platform. Outer rail walls rise past
                    the deck; shed roofs stand on the platforms and on the rail walls.
Each drawn "rail" in the sketches is ONE TWO-WAY LANE (a double track, up + down).

What this file owns, and nothing else:
  * the CONTRACT every station piece keeps (`PLATFORM_EDGE`, `PLATFORM_H`, the train's GAUGE), taken from the rail
    record's own owner (`island_rail_record`) so the track and the platform can never disagree;
  * which form each station takes, from the rail plan (how many lanes stop there, and whether the track is elevated);
  * each station's PLAN as boxes in the station's own frame (`Station.elements`), which the layout-to-pieces step
    tiles with the station kit's modules;
  * the checks: nothing a station owns in any track's gauge, the platform edge exactly where the train expects it,
    and nothing in a FREIGHT BRANCH'S THROAT (a turnout never lies inside a platform, and nothing a station owns stands
    where a branch will diverge -- JR Freight trains share the passenger track and leave it at a turnout, PLAN.md).

STATION FRAME (plan, like the record): origin on the station's axis at the platform centre, at BED level; `a` along
the axis (the direction `u` the rail plan's line runs at the station), `c` across it, positive to the LEFT of `u`,
`h` up from the bed. `to_godot_local` turns (a, c, h) into the scene's local frame (+X along the axis, +Z to the RIGHT,
+Y up), so a scene placed with `godot_yaw(u)` at the station's centre lands every element where this file said.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "building_kit"))

import island_rail_record as IRR   # noqa: E402  (the platform contract's owner)

# ── the contract ────────────────────────────────────────────────────────────────────────────────────────────────
TRACK_HALF = 2.0                  # a lane's two track centres stand +-2.0 m off its centreline (the `rail` preset)
PLATFORM_EDGE = IRR.PLATFORM_EDGE  # platform edge from its track's centre (1.55: a 2.9 m car leaves ~5 cm)
PLATFORM_H = IRR.PLATFORM_H        # platform top over the BED (1.1 m over the rail head + the rail)
PLATFORM_W = IRR.PLATFORM_W        # side platform width by station kind
ISLAND_MAX = 13.0                  # the widest gap between two lanes' facing tracks that one ISLAND platform fills
#: the train's gauge, as probe_rail_track check 5 sweeps it: 2.7 m wide, 0.5-4.2 m over the bed
GAUGE_HALF = 1.35
GAUGE_H = (0.5, 4.2)
#: a turnout's throat: the stretch of the station's line, beyond the end of a branch, where the branch will diverge
#: (a No. 10 turnout plus the curve out to a 20 m track spacing)
THROAT_LEN = 60.0

# the open-air form's dimensions (the station kit's modules tile these)
SHED_CLEAR = 3.0                   # shed soffit over the platform top
SHED_T = 0.25
FENCE_H = 1.8                      # the platform's back fence (駅の柵), over the platform top
FENCE_T = 0.1
BUILDING_LEN = 9.0                 # an open-air end building, along the track
BUILDING_OUT = 3.0                 # how far an end building reaches past its platform's outer edge
BUILDING_H = 4.2                   # its wall height over the STREET (the floor)
ENTRANCE_STEP = 0.8               # an end building's floor (the bed) may stand this far off the street outside its door
GATE_LANES = 2                     # ticket-gate lanes across an end building
GATE_W = 0.9                       # one lane (world.TicketGate)

FORMS = ("open_air", "ground_hub", "elevated_hub")
#: the forms whose station is laid out from the station kit (the rest still use the rail record's own platforms)
KIT_FORMS = ("open_air", "ground_hub")

# the ground hub's dimensions (橋上駅: a walled CAP over the passenger lanes carrying the airbridge concourse)
CAP_LEN = 30.0                     # the cap along the track: a whole number of MODULEs, centred on the platform centre
AF = 6.2                           # the airbridge floor's top over the bed (soffit 5.9: the gauge tops out at 4.2)
AF_T = 0.3
ROOF = 9.6                         # the cap's roof slab, underside over the bed
ROOF_T = 0.25
WALL_T = 0.3                       # the cap's outer side walls
ANNEX_D = 8.5                      # the entrance annex, across, outside the cap wall: paid strip, gate line, unpaid
ANNEX_PAID = 4.2                   # the annex's paid strip (the stair up to the airbridge), next to the cap wall
STAIR_RISE = 0.18                  # the most a riser may be (both stairs round their count up to keep under it)
STAIR_RUN = 0.29
CAP_STAIR_X = 6.0                  # a platform stair's foot, along the axis from the station centre (rises toward -a)
ANNEX_STAIR_X = 13.5               # the annex stair's foot (rises toward -a)
ANNEX_DOOR = (9.0, 13.0)           # the annex's street door, along the axis
WALL_DOOR = (-8.0, -2.0)
DOOR_STEPS_MAX = 8                 # the most exterior steps down from an annex door (GH_DoorSteps_<n> pieces)
PLINTH = 1.6                       # how far a hub's annex floor and cap walls reach below the bed (they stand on it)           # the cap wall's opening from the annex landing onto the airbridge, along the axis



@dataclass
class Lane:
    line: str
    c: float                      # the lane's centreline, across the station axis

    def tracks(self):
        return (self.c - TRACK_HALF, self.c + TRACK_HALF)


@dataclass
class Box:
    """An axis-aligned box in the station frame: a (along), c (across, + left), h (up from the bed)."""
    kind: str
    a0: float
    a1: float
    c0: float
    c1: float
    h0: float
    h1: float
    tag: str = ""

    def overlaps(self, o: "Box", eps: float = 1e-6) -> bool:
        return (self.a0 < o.a1 - eps and o.a0 < self.a1 - eps and self.c0 < o.c1 - eps and o.c0 < self.c1 - eps
                and self.h0 < o.h1 - eps and o.h0 < self.h1 - eps)


@dataclass
class Station:
    name: str
    kind: str                     # the rail plan's kind (small / standard / large / junction / hub)
    x: float                      # record frame, the platform centre on the station's own line
    y: float
    ux: float                     # the axis
    uy: float
    bed: float                    # record height of the bed at the centre
    length: float                 # platform length
    elevated: bool
    lanes: list = field(default_factory=list)
    branches: list = field(default_factory=list)    # [(line, (a, c) of the branch's end nearest the station)]
    building_end: dict = field(default_factory=dict)  # {"left"/"right": +1 | -1}: which end its building stands at
    entrance: str = ""            # a ground hub's entrance annex: "left" / "right" of the axis ("" = not chosen yet)
    door_step: float = 0.0        # how far the street outside that door lies below the annex's floor (the bed)

    @property
    def form(self):
        if self.elevated:
            return "elevated_hub"
        return "open_air" if len(self.lanes) == 1 and self.kind in ("small", "standard") else "ground_hub"


def godot_yaw(ux, uy):
    """The scene yaw (radians, Godot's Y rotation) that turns local +X onto the record axis (ux, uy): Godot's plan is
    (x, -y) of the record, and a yaw t sends +X to (cos t, 0, -sin t)."""
    return math.atan2(uy, ux)


def to_godot_local(a, c, h):
    """(a, c, h) of the station frame -> the scene's local (x, y, z): +X along, +Y up, +Z to the RIGHT (-c)."""
    return (a, h, -c)


# ── the plan of one station ─────────────────────────────────────────────────────────────────────────────────────
def platforms(st: Station):
    """[(c0, c1, facing lanes)] -- the platforms across the station: a side platform outside each outermost track, and
    between two lanes an ISLAND platform filling the gap (or two side platforms when the gap is too wide for one)."""
    w = PLATFORM_W.get(st.kind, PLATFORM_W["standard"])
    lanes = sorted(st.lanes, key=lambda ln: ln.c)
    out = []
    lo = lanes[0].tracks()[0] - PLATFORM_EDGE
    out.append((lo - w, lo, (lanes[0].line,)))
    for a, b in zip(lanes, lanes[1:]):
        e0, e1 = a.tracks()[1] + PLATFORM_EDGE, b.tracks()[0] - PLATFORM_EDGE
        if e1 - e0 <= ISLAND_MAX:
            out.append((e0, e1, (a.line, b.line)))
        else:
            out.append((e0, e0 + w, (a.line,)))
            out.append((e1 - w, e1, (b.line,)))
    hi = lanes[-1].tracks()[1] + PLATFORM_EDGE
    out.append((hi, hi + w, (lanes[-1].line,)))
    return out


def elements(st: Station):
    """The station's plan as `Box`es. The elevated hub is not laid out yet (PLAN.md order), so it raises: nothing
    silently ships a half station."""
    if st.form == "ground_hub":
        return hub_elements(st)
    if st.form != "open_air":
        raise NotImplementedError("%s: the %s form is not laid out yet" % (st.name, st.form))
    half = st.length / 2.0
    top = PLATFORM_H
    out = []
    for c0, c1, _faces in platforms(st):
        side = "left" if c0 > 0 else "right"
        sg = 1.0 if side == "left" else -1.0
        inner, outer = (c0, c1) if side == "left" else (c1, c0)
        out.append(Box("platform", -half, half, min(c0, c1), max(c0, c1), 0.0, top, side))
        out.append(Box("shed", -half, half, min(c0, c1), max(c0, c1), top + SHED_CLEAR, top + SHED_CLEAR + SHED_T, side))
        # the back fence along the outer edge, and across the platform's far end (the end without the building)
        fc = (outer - FENCE_T, outer) if side == "left" else (outer, outer + FENCE_T)
        out.append(Box("fence", -half, half, fc[0], fc[1], top, top + FENCE_H, side))
        end = st.building_end.get(side, 1)
        fa = (-half, -half + FENCE_T) if end > 0 else (half - FENCE_T, half)
        out.append(Box("fence", fa[0], fa[1], min(c0, c1), max(c0, c1), top, top + FENCE_H, side + "_end"))
        # the end building: in line with the platform, from the platform's end outward, and past its outer edge
        ba = (half, half + BUILDING_LEN) if end > 0 else (-half - BUILDING_LEN, -half)
        bc = sorted((inner, outer + sg * BUILDING_OUT))
        out.append(Box("building", ba[0], ba[1], bc[0], bc[1], 0.0, BUILDING_H, side))
        # the gate lanes cross the building mid-depth; their line is what splits unpaid (street) from paid (platform)
        mid = 0.5 * (ba[0] + ba[1])
        span = bc[1] - bc[0]
        for i in range(GATE_LANES):
            cc = bc[0] + span * (i + 1) / (GATE_LANES + 1)
            out.append(Box("gate", mid - 0.05, mid + 0.05, cc - GATE_W / 2, cc + GATE_W / 2, 0.0, 1.0,
                           "%s_%d" % (side, i)))
    return out


# ── the GROUND HUB (橋上駅) ─────────────────────────────────────────────────────────────────────────────────────────
# The passenger lanes at grade with their platforms; a walled CAP over all of them, CAP_LEN long at the platform
# centre, carrying the airbridge concourse (floor top AF) between its two outer side walls; a stair from the concourse
# down onto EVERY platform; and on one side (`Station.entrance`) the ENTRANCE ANNEX against the cap wall: the street
# door in its outer face, the fare line along it (gates), and in its paid strip a stair up to a landing at AF that
# passes through the cap wall onto the concourse. So: street -> gates -> up -> the airbridge -> down -> a platform.
# The tracks run through the cap under the concourse (its soffit is AF - AF_T, over the 4.2 m gauge).

def stair_steps(rise):
    """(n risers, riser height) for a flight rising `rise` with no riser over STAIR_RISE."""
    n = int(math.ceil(rise / STAIR_RISE - 1e-9))
    return n, rise / n


def hub_band(st: Station):
    """(lo, hi): the across extent of the platforms, i.e. the cap's inside."""
    pl = platforms(st)
    return min(p[0] for p in pl), max(p[1] for p in pl)


def annex_band(st: Station, side):
    lo, hi = hub_band(st)
    if side == "left":
        return hi + WALL_T, hi + WALL_T + ANNEX_D
    return lo - WALL_T - ANNEX_D, lo - WALL_T


def door_steps(st: Station):
    """(n, riser): the flight outside the annex door down to the street, or (0, 0) when the street is at the floor."""
    if st.door_step < 0.2:
        return 0, 0.0
    n = int(round(st.door_step / STAIR_RISE + 0.49))
    if n > DOOR_STEPS_MAX:
        raise SystemExit("%s: the street is %.2f m below its entrance annex's door (over %d steps)"
                         % (st.name, st.door_step, DOOR_STEPS_MAX))
    return n, st.door_step / n


def hub_entrance(st: Station, side):
    """(a, c) of the street 3 m outside the annex's door (past its steps down to the street, if any)."""
    c0, c1 = annex_band(st, side)
    out = 3.0 + door_steps(st)[0] * STAIR_RUN
    return (0.5 * (ANNEX_DOOR[0] + ANNEX_DOOR[1]), c1 + out if side == "left" else c0 - out)


def hub_elements(st: Station):
    half, hc = st.length / 2.0, CAP_LEN / 2.0
    lo, hi = hub_band(st)
    top = ROOF + ROOF_T
    out = []
    for c0, c1, faces in platforms(st):
        tag = "island" if len(faces) == 2 else ("left" if c0 > 0 else "right")
        out.append(Box("platform", -half, half, c0, c1, 0.0, PLATFORM_H, tag))
        if len(faces) == 1:
            left = c0 > 0
            outer = c1 if left else c0
            fc = (outer - FENCE_T, outer) if left else (outer, outer + FENCE_T)
            for a0, a1 in ((-half, -hc), (hc, half)):
                out.append(Box("fence", a0, a1, fc[0], fc[1], PLATFORM_H, PLATFORM_H + FENCE_H, tag))
        for a0 in (-half, half - FENCE_T):
            out.append(Box("fence", a0, a0 + FENCE_T, c0, c1, PLATFORM_H, PLATFORM_H + FENCE_H, tag + "_end"))
    out.append(Box("concourse", -hc, hc, lo, hi, AF - AF_T, AF, "cap"))
    out.append(Box("roof", -hc, hc, lo - WALL_T, hi + WALL_T, ROOF, top, "cap"))
    out.append(Box("wall", -hc, hc, hi, hi + WALL_T, 0.0, top, "left"))
    out.append(Box("wall", -hc, hc, lo - WALL_T, lo, 0.0, top, "right"))
    if st.entrance:
        c0, c1 = annex_band(st, st.entrance)
        out.append(Box("annex", -hc, hc, c0, c1, 0.0, top, st.entrance))
    return out


def hub_props(st: Station):
    n = st.length / MODULE
    if abs(n - round(n)) > 1e-6 or abs(CAP_LEN / MODULE - round(CAP_LEN / MODULE)) > 1e-6:
        raise SystemExit("%s: platform %.2f m / cap %.1f m is not a whole number of %.0f m modules"
                         % (st.name, st.length, CAP_LEN, MODULE))
    if st.entrance not in ("left", "right"):
        raise SystemExit("%s: a ground hub needs its entrance side (the rail reserve chooses it)" % st.name)
    n = int(round(n))
    half, hc = st.length / 2.0, CAP_LEN / 2.0
    lo, hi = hub_band(st)
    out = []
    pl = platforms(st)
    for (c0, c1, _f), (d0, _d1, _g) in zip(pl, pl[1:]):
        if d0 - c1 > 2 * (TRACK_HALF + PLATFORM_EDGE) + 1e-6:
            raise SystemExit("%s: two platforms %.2f m apart hold no single lane (the cap has no filler piece)"
                             % (st.name, d0 - c1))
    for c0, c1, faces in pl:
        w = c1 - c0
        ws = _wname(w)
        cc = (c0 + c1) / 2.0
        if len(faces) == 2:
            plat, shed, endf, cap, yaw = ("GH_IslandPlatform_" + ws, "GH_IslandShed_" + ws, "GH_EndFence_" + ws,
                                          "GH_CapIsland_" + ws, 0.0)
            outer = None
        else:
            left = c0 > 0
            plat, shed, endf, yaw = "GH_Platform_" + ws, "GH_Shed_" + ws, "GH_EndFence_" + ws, (0.0 if left else 180.0)
            cap = "GH_CapPlatform_%s_%s" % (ws, "L" if left else "R")
            outer = c1 - FENCE_T / 2 if left else c0 + FENCE_T / 2
        for k in range(n):
            a = -half + MODULE * (k + 0.5)
            out += _piece_props(plat, a, cc, 0.0, yaw)
            if abs(a) < hc:
                continue                      # under the cap: its concourse is the roof, its wall the fence
            out += _piece_props(shed, a, cc, PLATFORM_H, yaw)
            if outer is not None:
                out += _piece_props("GH_Fence", a, outer, PLATFORM_H, 0.0)
        for sg in (1.0, -1.0):
            out += _piece_props(endf, sg * (half - FENCE_T / 2), cc, PLATFORM_H, 0.0)
        out += _piece_props(cap, 0.0, cc, 0.0, 0.0)
    for ln in st.lanes:
        out += _piece_props("GH_CapLane", 0.0, ln.c, 0.0, 0.0)
    for side, c in (("left", hi + WALL_T / 2), ("right", lo - WALL_T / 2)):
        out += _piece_props("GH_CapWall_Door" if side == st.entrance else "GH_CapWall", 0.0, c, 0.0, 0.0)
    c0, c1 = annex_band(st, st.entrance)
    out += _piece_props("GH_Annex_" + ("L" if st.entrance == "left" else "R"), 0.0, 0.5 * (c0 + c1), 0.0, 0.0)
    n, _r = door_steps(st)
    if n:
        # the steps down to the street, from the door's sill outward (the piece descends along its +Y: yaw 0 on the
        # left, 180 on the right)
        c = c1 if st.entrance == "left" else c0
        out += _piece_props("GH_DoorSteps_%d" % n, 0.5 * (ANNEX_DOOR[0] + ANNEX_DOOR[1]), c, 0.0,
                            0.0 if st.entrance == "left" else 180.0)
    return out


def choose_entrance(st: Station, clear, cost):
    """The side ('left' / 'right') the ground hub's entrance annex stands on: among the sides where `clear(cx, cy,
    ux, uy, half along, half across)` (record frame) says it stands clear and it keeps out of every gauge and turnout
    throat, the one whose street door has the lower `cost(x, y)`; None when neither side does."""
    best = None
    for side in ("left", "right"):
        c0, c1 = annex_band(st, side)
        cx, cy = to_record(st, 0.0, 0.5 * (c0 + c1))
        if not clear(cx, cy, st.ux, st.uy, CAP_LEN / 2.0 + 0.5, ANNEX_D / 2.0 + 0.5):
            continue
        was, st.entrance = st.entrance, side
        bad = check(st)
        st.entrance = was
        if bad:
            continue
        k = cost(*to_record(st, *hub_entrance(st, side)))
        if best is None or k < best[0]:
            best = (k, side)
    return best[1] if best else None


# ── the layout the scene builder reads ─────────────────────────────────────────────────────────────────────────
KITS = os.path.join(ROOT, "assets", "world_source", "kits")
KIT = "stations"
MODULE = 5.0                     # a platform / shed / fence module (the station kit's pieces, build_station_blends.py)


def _wname(w):
    return ("%g" % w).replace(".", "")


def _piece_props(ref, a, c, h, yaw):
    """A layout_buildings prop for kit piece `ref` whose origin lands at station-frame (a, c, h), turned `yaw` degrees
    (Godot's sense about +Y), colliding with the piece's own COL_ boxes; plus a door-only prop per GATE_ lane."""
    import layout_buildings as LB
    _path, entry, _name = LB.lib_piece(KIT + ":" + ref, KITS)
    x, y, z = to_godot_local(a, c, h)
    out = [{"piece": KIT + ":" + ref, "at": [x, z], "y": y, "yaw": yaw,
            "collide": {"boxes": entry.get("collide_boxes", [])} if entry.get("collide_boxes") else "none"}]
    for g in entry.get("gates", ()):
        gx, gz = LB.rot_xz(yaw, g["pos"][0], g["pos"][2])
        ox, oz = LB.rot_xz(yaw, g["out"][0], g["out"][2])
        out.append({"at": [x + gx, z + gz], "y": y + g["pos"][1], "yaw": math.degrees(math.atan2(ox, oz)),
                    "door": {"kind": "gate", "w": g["w"], "h": g["h"]}})
    return out


def props(st: Station):
    """The station as layout_buildings props (see `elements` for the same plan as boxes)."""
    if st.form == "ground_hub":
        return hub_props(st)
    if st.form != "open_air":
        raise NotImplementedError("%s: the %s form is not laid out yet" % (st.name, st.form))
    n = st.length / MODULE
    if abs(n - round(n)) > 1e-6:
        raise SystemExit("%s: platform %.2f m is not a whole number of %.0f m modules" % (st.name, st.length, MODULE))
    n = int(round(n))
    half = st.length / 2.0
    out = []
    for c0, c1, _faces in platforms(st):
        left = c0 > 0
        w = c1 - c0
        ws = _wname(w)
        cc = (c0 + c1) / 2.0
        yaw = 0.0 if left else 180.0              # the piece's track side (Godot +Z) toward the track
        outer = c1 if left else c0
        for k in range(n):
            a = -half + MODULE * (k + 0.5)
            out += _piece_props("OA_Platform_" + ws, a, cc, 0.0, yaw)
            out += _piece_props("OA_Shed_" + ws, a, cc, PLATFORM_H, yaw)
            out += _piece_props("OA_Fence", a, outer - (FENCE_T / 2 if left else -FENCE_T / 2), PLATFORM_H, 0.0)
        side = "left" if left else "right"
        end = st.building_end.get(side, 1)
        out += _piece_props("OA_EndFence_" + ws, -end * (half - FENCE_T / 2), cc, PLATFORM_H, 0.0)
        # the end building: a platform on the LEFT with its building at +a is hand L as modelled; every other case
        # is a hand turned 180 deg (L <-> R swap sides when turned), so the platform always comes in its -X face
        hand = "L" if left == (end > 0) else "R"
        byaw = 0.0 if end > 0 else 180.0
        bc = cc + (1.0 if left else -1.0) * BUILDING_OUT / 2.0
        out += _piece_props("OA_Building_%s_%s" % (ws, hand), end * (half + BUILDING_LEN / 2.0), bc, 0.0, byaw)
    return out


def layout(st: Station):
    """{id, kit, pieces, boxes, inner_doors, ...}: the station in `layout_buildings`' schema, which
    `tools/godot/build_building_scenes.gd` turns into `Station_<Name>.tscn` (+ `_Shop`, the one placed: its gates
    open for a walker)."""
    import layout_buildings as LB
    half = st.length / 2.0
    # what a probe needs to judge the paid area, in the SCENE's local frame (Godot): each platform's lateral band,
    # a point on the street outside each end building's entrance, and a point on the track bed past each platform end
    entr, bed = [], []
    if st.form == "ground_hub":
        entr.append(list(to_godot_local(*hub_entrance(st, st.entrance), -st.door_step)))
    for c0, c1, _f in (platforms(st) if st.form == "open_air" else ()):
        side = "left" if c0 > 0 else "right"
        end = st.building_end.get(side, 1)
        bc = (c0 + c1) / 2.0 + (1.0 if c0 > 0 else -1.0) * BUILDING_OUT / 2.0
        entr.append(list(to_godot_local(end * (half + BUILDING_LEN + 3.0), bc, 0.0)))
    for sg in (1.0, -1.0):
        for ln in st.lanes:
            bed.append(list(to_godot_local(sg * (half + BUILDING_LEN + 12.0), ln.c, 0.0)))
    out = {"id": "Station_" + st.name.replace(" ", ""), "kit": KIT, "pieces": [], "boxes": [], "doors": [],
           "station": {"form": st.form, "name": st.name, "length": st.length,
                       "lanes": [[ln.line, ln.c] for ln in st.lanes],
                       "platforms": [[-c1, -c0] for c0, c1, _f in platforms(st)],   # Godot z band of each
                       "platform_top": PLATFORM_H, "entrances": entr, "bed_points": bed}}
    LB.place_props(props(st), out, KITS)
    out["boxes"] = LB.merge_boxes(out["boxes"])
    xs = [abs(b["center"][0]) + b["size"][0] / 2 for b in out["boxes"]]
    zs = [abs(b["center"][2]) + b["size"][2] / 2 for b in out["boxes"]]
    out["footprint_m"] = [round(2 * max(xs), 3), round(2 * max(zs), 3)]
    out["height_m"] = round(max(b["center"][1] + b["size"][1] / 2 for b in out["boxes"]), 3)
    return out


# ── where each end building goes (the reserve asks; PLAN.md step 3) ────────────────────────────────────────────
def to_record(st: Station, a, c):
    """Station-frame (a, c) -> record-frame (x, y): `a` along the axis, `c` to its LEFT."""
    return (st.x + st.ux * a - st.uy * c, st.y + st.uy * a + st.ux * c)


def end_building(st: Station, side, end):
    """(centre a, centre c, half along, half across) of `side`'s end building standing at end `end` (+1 / -1)."""
    half = st.length / 2.0
    for c0, c1, _f in platforms(st):
        if ("left" if c0 > 0 else "right") != side:
            continue
        sg = 1.0 if side == "left" else -1.0
        inner, outer = (c0, c1) if side == "left" else (c1, c0)
        bc = sorted((inner, outer + sg * BUILDING_OUT))
        return (end * (half + BUILDING_LEN / 2.0), 0.5 * (bc[0] + bc[1]), BUILDING_LEN / 2.0, 0.5 * (bc[1] - bc[0]))
    raise KeyError(side)


def entrance(st: Station, side, end):
    """(a, c) of the street outside `side`'s end building at end `end`: 3 m out from its street door."""
    a, c, ha, _hc = end_building(st, side, end)
    return (a + end * (ha + 3.0), c)


def extent(st: Station):
    """(half along, half across) of everything the station owns, whichever ends its buildings stand at (a ground
    hub: whichever side its entrance annex stands on)."""
    if st.form == "ground_hub":
        lo, hi = hub_band(st)
        return st.length / 2.0, max(-lo, hi) + WALL_T + ANNEX_D
    hc = max(abs(v) for c0, c1, _f in platforms(st) for v in (c0, c1)) + BUILDING_OUT
    return st.length / 2.0 + BUILDING_LEN, hc


def choose_ends(st: Station, clear, cost):
    """{side: +1 | -1}: for each platform, the end its building stands at -- among the ends where `clear(cx, cy, ux,
    uy, half along, half across)` (record frame) says the building stands clear, the one whose street entrance has the
    lower `cost(x, y)` (the town is nearer). A side with no clear end is left out, and the caller reports it."""
    out = {}
    for side in ("left", "right"):
        best = None
        for end in (1, -1):
            a, c, ha, hc = end_building(st, side, end)
            cx, cy = to_record(st, a, c)
            if not clear(cx, cy, st.ux, st.uy, ha + 0.5, hc + 0.5):
                continue
            k = cost(*to_record(st, *entrance(st, side, end)))
            if best is None or k < best[0]:
                best = (k, end)
        if best is not None:
            out[side] = best[1]
    return out


# ── the checks ──────────────────────────────────────────────────────────────────────────────────────────────────
def gauge_boxes(st: Station, extra=20.0):
    """Every track's gauge over the station and `extra` beyond it, including tracks of lanes that do not stop here."""
    half = st.length / 2.0 + BUILDING_LEN + extra
    out = []
    for ln in st.lanes:
        for t in ln.tracks():
            out.append(Box("gauge", -half, half, t - GAUGE_HALF, t + GAUGE_HALF, *GAUGE_H, tag=ln.line))
    for line, (a_end, c_end) in st.branches:
        for t in (c_end - TRACK_HALF, c_end + TRACK_HALF):
            out.append(Box("gauge", -half, half, t - GAUGE_HALF, t + GAUGE_HALF, *GAUGE_H, tag=line))
    return out


def throat_boxes(st: Station):
    """Where each freight branch will leave the station's line: from the branch's end nearest the station, THROAT_LEN
    further on along the axis, across everything between the station's lane and the branch."""
    out = []
    for line, (a_end, c_end) in st.branches:
        own = min(st.lanes, key=lambda ln: abs(ln.c - c_end))
        sg = 1.0 if a_end >= 0 else -1.0
        a0, a1 = sorted((a_end, a_end + sg * THROAT_LEN))
        c0, c1 = sorted((own.c, c_end))
        out.append(Box("throat", a0, a1, c0 - TRACK_HALF - GAUGE_HALF, c1 + TRACK_HALF + GAUGE_HALF,
                       -1.0, 10.0, tag=line))
    return out


def check(st: Station, els=None):
    """[finding] -- empty when the station keeps its contract."""
    els = elements(st) if els is None else els
    bad = []
    for e in els:
        if e.kind == "gate":
            continue
        for g in gauge_boxes(st):
            if e.overlaps(g):
                bad.append("%s: %s %s stands in the %s gauge" % (st.name, e.kind, e.tag, g.tag))
        for t in throat_boxes(st):
            if e.overlaps(t):
                bad.append("%s: %s %s stands in the %s turnout's throat" % (st.name, e.kind, e.tag, t.tag))
    for c0, c1, faces in platforms(st):
        for line in faces:
            ln = next(x for x in st.lanes if x.line == line)
            edge = min(abs(c - t) for c in (c0, c1) for t in ln.tracks())
            if abs(edge - PLATFORM_EDGE) > 1e-6:
                bad.append("%s: a platform's edge is %.3f m from its track (%.2f)" % (st.name, edge, PLATFORM_EDGE))
    half = st.length / 2.0
    for line, (a_end, _c) in st.branches:
        if -half < a_end < half:
            bad.append("%s: the %s branch leaves inside the platform (a %.1f)" % (st.name, line, a_end))
    return bad


def kit_widths(sts):
    """{"side": {w}, "island": {w}}: every platform width the kit stations need (the station kit's generator makes a
    piece per width, `blender/tools/build_station_blends.py`)."""
    out = {"side": set(), "island": set()}
    for st in sts.values():
        if st.form not in KIT_FORMS:
            continue
        for c0, c1, faces in platforms(st):
            out["island" if len(faces) == 2 else "side"].add(round(c1 - c0, 3))
    return out


# ── from the rail plan ──────────────────────────────────────────────────────────────────────────────────────────
RESERVE = os.path.join(ROOT, "assets", "world_source", "buildings", "IslandRailReserve.json")


def reserve_ends(path=RESERVE):
    """{station name: {side: +1 | -1}} -- the end buildings' ends the rail reserve chose (`island_rail_layout
    .reserve`), or {} before it has been written."""
    import json
    if not os.path.exists(path):
        return {}
    return {b["id"].partition(":")[2]: b["ends"] for b in json.load(open(path))["boxes"]
            if b["id"].startswith("station:") and "ends" in b}


def reserve_entrances(path=RESERVE):
    """{station name: ('left' | 'right', door step)} -- the ground hubs' entrance sides the rail reserve chose."""
    import json
    if not os.path.exists(path):
        return {}
    return {b["id"].partition(":")[2]: (b["entrance"], b.get("door_step", 0.0)) for b in json.load(open(path))["boxes"]
            if b["id"].startswith("station:") and "entrance" in b}


def stations(res, ends=None, entrances=None):
    """{name: Station} from `island_rail_layout.analyse()`'s result; `ends` ({name: {side: end}}, the reserve's
    choice) says which end each open-air building stands at."""
    import island_rail_layout as R
    chosen = reserve_ends() if ends is None else ends
    doors = reserve_entrances() if entrances is None else entrances
    out = {}
    for name, sd in res["stations"].items():
        L = res["lines"][sd["line"]]
        x, y, tx, ty = IRR.point_at(L, sd["s"])
        lanes, branches = [], []
        for ln, L2 in res["lines"].items():
            s2, d = R.project(L2["pts"], L2["cum"], x, y)
            if d > 40.0:
                continue
            x2, y2, _, _ = IRR.point_at(L2, s2)
            c = (x2 - x) * -ty + (y2 - y) * tx
            stops = any(a - 5.0 <= s2 <= b + 5.0 for a, b, _k in IRR.platform_spans(res, ln))
            if stops:
                lanes.append(Lane(ln, round(c, 3)))
            else:
                # a line passing without stopping: its end nearest the station is a branch end (the turnout's side)
                ends = [(L2["pts"][0], 0), (L2["pts"][-1], -1)]
                (ex, ey), _ = min(ends, key=lambda e: math.hypot(e[0][0] - x, e[0][1] - y))
                branches.append((ln, ((ex - x) * tx + (ey - y) * ty, round(c, 3))))
        z = sd.get("z", 0.0)
        out[name] = Station(name, sd["kind"], x, y, tx, ty, z - 0.16, sd["platform_m"],
                            elevated=z > 4.0, lanes=lanes, branches=branches,
                            building_end=dict(chosen.get(name, {})), entrance=doors.get(name, ("", 0.0))[0],
                            door_step=doors.get(name, ("", 0.0))[1])
    return out


# ── self-test ───────────────────────────────────────────────────────────────────────────────────────────────────
def self_test():
    st = Station("Test", "standard", 0.0, 0.0, 1.0, 0.0, 0.0, 90.0, False, [Lane("L", 0.0)])
    assert st.form == "open_air"
    pl = platforms(st)
    assert len(pl) == 2 and abs(pl[0][1] + 3.55) < 1e-9 and abs(pl[1][0] - 3.55) < 1e-9, pl
    assert check(st) == [], check(st)
    # control: a building pulled 0.5 m toward the track stands in the gauge
    els = elements(st)
    b = next(e for e in els if e.kind == "building" and e.tag == "left")
    b.c0 -= 0.5
    assert any("gauge" in f for f in check(st, els)), "the gauge check does not see a building in the train"
    # two lanes 20 m apart: an island platform fills the 12.9 m gap
    st2 = Station("Two", "junction", 0, 0, 1, 0, 0, 100.0, False, [Lane("A", 0.0), Lane("B", -20.0)])
    assert st2.form == "ground_hub"
    isl = [p for p in platforms(st2) if len(p[2]) == 2]
    assert len(isl) == 1 and abs(isl[0][1] - isl[0][0] - 12.9) < 1e-9, platforms(st2)
    # a freight branch ending 60 m past the platform on the left: an open-air end building there stands in its
    # throat, so that platform's building must go to the other end
    st3 = Station("Frt", "standard", 0, 0, 1, 0, 0, 90.0, False, [Lane("L", 0.0)], branches=[("F", (50.0, 20.0))])
    st3.building_end = {"left": 1, "right": 1}
    assert any("throat" in f for f in check(st3)), check(st3)
    st3.building_end = {"left": -1, "right": 1}
    assert check(st3) == [], check(st3)
    # a turnout inside the platform is refused
    st4 = Station("Frt2", "standard", 0, 0, 1, 0, 0, 90.0, False, [Lane("L", 0.0)], branches=[("F", (10.0, 20.0))])
    assert any("inside the platform" in f for f in check(st4)), check(st4)
    # the end chooser: a road just past the +a end of the LEFT platform takes that building there; a road blocking
    # the right platform's +a end pushes its building to the -a end; nothing clear -> the side is left out
    st5 = Station("Ends", "standard", 100.0, 50.0, 0.0, 1.0, 0.0, 90.0, False, [Lane("L", 0.0)])
    left_plus = to_record(st5, *entrance(st5, "left", 1))
    right_plus = end_building(st5, "right", 1)
    rp = to_record(st5, right_plus[0], right_plus[1])
    clear = lambda cx, cy, ux, uy, ha, hc: math.hypot(cx - rp[0], cy - rp[1]) > 1.0
    cost = lambda x, y: math.hypot(x - left_plus[0], y - left_plus[1])
    assert choose_ends(st5, clear, cost) == {"left": 1, "right": -1}, choose_ends(st5, clear, cost)
    assert choose_ends(st5, lambda *a_: False, cost) == {}
    # the record frame: +c is to the LEFT of the axis (axis north -> left is west)
    assert to_record(st5, 0.0, 10.0) == (90.0, 50.0), to_record(st5, 0.0, 10.0)
    # the frame: a scene yawed by godot_yaw puts local +X on the axis and local +Z on the RIGHT of it
    for ux, uy in ((1, 0), (0, -1), (-1, 0), (0.6, 0.8)):
        t = godot_yaw(ux, uy)
        gx = (math.cos(t), -math.sin(t))              # Godot (x, z) of local +X
        assert abs(gx[0] - ux) < 1e-9 and abs(-gx[1] - uy) < 1e-9
        gz = (math.sin(t), math.cos(t))               # local +Z
        right = (uy, -ux)                             # record right of the axis
        assert abs(gz[0] - right[0]) < 1e-9 and abs(-gz[1] - right[1]) < 1e-9
    # the ground hub: two lanes 20 m apart, an island platform between them; the annex clears every gauge on either
    # side, and the cap's concourse passes over the tracks (its soffit over the gauge's top)
    st6 = Station("Hub", "junction", 0, 0, 1, 0, 0, 100.0, False, [Lane("A", 0.0), Lane("B", -20.0)])
    for side in ("left", "right"):
        st6.entrance = side
        assert check(st6) == [], (side, check(st6))
    assert AF - AF_T > GAUGE_H[1] + 1.0
    # control: a freight branch 20 m off the left lane -- the left annex stands in its gauge, so the chooser takes right
    st7 = Station("Frt3", "large", 0, 0, 1, 0, 0, 90.0, False, [Lane("L", 0.0)], branches=[("F", (-47.0, 20.0))])
    st7.entrance = "left"
    assert any("gauge" in f for f in check(st7)), check(st7)
    assert choose_entrance(st7, lambda *a_: True, lambda x, y: -y) == "right"   # the left side is cheaper, but blocked
    st7.entrance = ""
    assert stair_steps(AF)[1] <= STAIR_RISE and stair_steps(AF - PLATFORM_H)[1] <= STAIR_RISE
    print("station_layout: self-test OK")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--layout", default="tokyo_straight")
    ap.add_argument("--write", metavar="JSON", help="write the laid-out stations (the scene builder's input)")
    ap.add_argument("--only", default="", help="comma-separated station names")
    a = ap.parse_args(argv)
    if a.self_test:
        self_test()
        return 0
    import island_rail_layout as R
    R.use_layout(a.layout)
    sts = stations(R.analyse())
    bad = 0
    only = {n for n in a.only.split(",") if n}
    if a.write:
        import json
        done = [layout(st) for st in sts.values() if (not only or st.name in only) and st.form in KIT_FORMS]
        json.dump({"buildings": done}, open(a.write, "w"), indent=1)
        print("station_layout: %d station(s) -> %s" % (len(done), a.write))
    for st in sts.values():
        lanes = ", ".join("%s c%+.1f" % (ln.line, ln.c) for ln in st.lanes)
        br = ", ".join("%s end a%+.0f c%+.0f" % (b[0], b[1][0], b[1][1]) for b in st.branches)
        print("%-18s %-12s %-9s %5.0f m  bed %5.2f  lanes [%s]%s" % (st.name, st.form, st.kind, st.length, st.bed,
                                                                   lanes, ("  branches [%s]" % br) if br else ""))
        if st.form in KIT_FORMS:
            for f in check(st):
                print("   FINDING " + f)
                bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
