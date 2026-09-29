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
import json
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
# the train's gauge, off the TRAIN (blender/tools/make_train.py's EMU1.train.json: the largest standard 1067 mm car,
# 2.98 m over its doors, 4.05 m to its folded pantograph over the rail head), rounded up to the conventional-line
# vehicle gauge's 3.0 x 4.1 m; over the BED (the rail head is 0.16 m above it)
def _train_gauge():
    try:
        with open(os.path.join(ROOT, "assets", "vehicles", "trains", "EMU1.train.json")) as fh:
            t = json.load(fh)
        return math.ceil(t["half_width_m"] * 20.0) / 20.0, (0.5, math.ceil((t["height_m"] + 0.16) * 20.0) / 20.0)
    except (OSError, KeyError, ValueError):
        return 1.5, (0.5, 4.25)


GAUGE_HALF, GAUGE_H = _train_gauge()
#: a turnout's throat: the stretch of the station's line, beyond the end of a branch, where the branch will diverge
#: (a No. 10 turnout plus the curve out to a 20 m track spacing)
THROAT_LEN = 60.0

# the open-air form's dimensions (the station kit's modules tile these)
SHED_CLEAR = 3.0                   # shed soffit over the platform top
SHED_T = 0.25
FENCE_H = 1.8                      # the platform's back fence (駅の柵), over the platform top
FENCE_T = 0.1
# THE OPEN-AIR END BUILDING (user, 2026-09-27: "increase the length and width of the station, opposite of rail facing,
# to accommodate restrooms and a service area"). Its whole floor is at PLATFORM level, so the platform runs straight
# in; outside the street door a stair and an accessible SLOPE come down to the sidewalk (`OA_Entry_*`). Inside, from
# the platform: the paid hall with its restroom block, the fare line (GATE_LANES lanes and the station staff's
# service counter on it), the unpaid hall with its restroom block and the ticket / ATM / vending machines, the door.
BUILDING_LEN = 22.0                # along the track, from the platform's end to the street face
BUILDING_D = 9.5                   # across, from the platform's track edge outward (away from the rail): the gate lanes
                                   # (4.3 m with two) and the restroom block (WC_D) side by side; 9.5 is what fits
                                   # Waterpark, whose south platform has wangan_dori's paved edge ~10 m off it
BUILDING_H = 3.4                   # the hall's height over its floor (the platform top)
BUILDING_T = 0.2                   # its walls
GATE_X = 11.0                      # the fare line, from the platform-end face
GATE_LANES = 2                     # ticket-gate lanes across an end building (user: "at least 2"); the service
                                   # counter's window beside them is the staffed (wide) gate
GATE_W = 0.9                       # one lane (world.TicketGate)
DOOR_OFF = 3.0                     # the street door's centre, across from the track-side wall
DOOR_W = 4.0                       # its opening: two roller-shutter bays (see SHUTTER_*)
ENTRANCE_STEP = 0.8               # the street outside a door may stand this far off the bed (the stair + slope take it)
# THE RESTROOM BLOCK (駅のトイレ, the standard modern-station set; user: "3 stalls, or 1 stall + 2 urinals + 3 sinks"):
# men (1 stall, 2 urinals, 3 sinks), women (3 stalls, 3 sinks) and an accessible room (多機能トイレ, 2.2 m wide), one
# block inside the gates and one outside. WC_L along its open (hall) face, WC_D deep.
WC_L = 8.6
WC_D = 5.0
COUNTER_L = 3.0                    # the service counter's box (有人改札 / 駅務室 window), along the fare line's axis
# THE ENTRANCE RAMP (`OA_Ramp_<n>`, user 2026-09-28: "remove the stairs, and have the slope in line with the
# entrance, so the station can move close to the sidewalk"): ONE straight slope out of the street door, as wide as the
# door and in line with it -- a RAMP_LAND landing at the sill, then 1:RAMP_SLOPE legs with a RAMP_LAND landing every
# RAMP_SEG_RISE of rise (the barrier-free standard), down to the street. No stair: the slope IS the way in. Its foot
# stops FOOT_GAP short of the street's footway (a paved apron: the 踏切's warning unit stands there when the street
# crosses the line beside the station). One piece per riser count; the layout picks the count nearest the street's
# real height. (The ground hub's annex keeps its stair + slope entry, `GH_Entry_*`.)
ENTRY_RISE = 0.165                 # one riser step of the rise table (the ramp's height is n x this)
ENTRY_N = (3, 14)                  # the rise counts the kit carries (0.5 .. 2.3 m)
ENTRY_KINDS = ("side", "out")      # the GROUND HUB's entry: the slope along the front, or straight out beside the stair
ENTRY_LAND = 2.0                   # the ground hub entry's landing outside the door
FOOT_GAP = 1.5                     # the open-air ramp's foot this far short of the street's paved edge (an apron)
RAMP_W = 1.5
RAMP_SLOPE = 15.0                  # 1:15, the Japanese OUTDOOR barrier-free guideline (1:12 is the most any ramp may
                                   # be; user, 2026-09-27: "ideally 1/20 or gentler for a long, busy public path" --
                                   # 1:20 would run a typical station's slope ~29 m, more than most fronts hold)
RAMP_SEG_RISE = 0.75
RAMP_LAND = 1.5

# EVERY STATION ENTRANCE IS A ROLLER-SHUTTER OPENING (user, 2026-09-27): no swing or slide door, open all day, one
# shutter rolled up into a housing over it (modelled rolled up; one that comes down between the last and first trains
# is a later runtime item). An ENTRANCE has no post in between, only its frame at each side (user, 2026-09-28); its
# width is still sized as bays (DOOR_BAYS, LARGE_BAYS; `shutter_bays`). A STORE has no shutter: a glass front with a
# sliding glass door (STORE_DOOR_*).
SHUTTER_POST = 0.2                 # a post between two bays (the shutters' guide rails run in it)
SHUTTER_H = 2.6                    # the bays' clear height (the housing sits over it, in the header)
DOOR_BAYS = 2                      # an ordinary station's entrance (DOOR_W): two bays
# THE LARGE HUBS (user, 2026-09-27: "all the larger hubs" -- every hub but a standard-size station squeezed onto a hub
# form, FORM_OVERRIDE): a SIX-BAY entrance (~11.8 m: Japan sets only barrier-free minimums, a doorway >= 0.9 m and a
# passage >= 1.4 m; an operator sizes a big station's entrance from peak flow, so six bays is a design choice) and
# SHOPS along the building's side.
LARGE_BAYS = 6
LARGE_BAY_W = 1.8
LARGE_ENTRANCE_W = LARGE_BAYS * LARGE_BAY_W + (LARGE_BAYS - 1) * SHUTTER_POST
SHOP_UNIT = 5.0                    # one shop's frontage (a module)
SHOP_H = 4.0                       # a ground hub's single-storey shop row, its roof's top over its floor

FORMS = ("open_air", "ground_hub", "elevated_hub")
#: a station whose site does not take its natural form. WATERPARK (2026-09-27): its south platform has wangan_dori (a
#: 3+3 trunk road) ~6.5 m off it, no room for an open-air end building with gates and restrooms (BUILDING_D), so it is a
#: one-lane GROUND HUB (橋上駅) -- the concourse over the track, the entrance annex on the open north side.
FORM_OVERRIDE = {"Waterpark": "ground_hub"}
#: the forms whose station is laid out from the station kit (the rest still use the rail record's own platforms); an
#: elevated hub is a kit station only with ONE lane for now (Suburb, Airport) -- Central's three is PLAN.md step 6
KIT_FORMS = ("open_air", "ground_hub", "elevated_hub")
#: a station whose site does not take its natural form. WATERPARK (2026-09-27): its south platform has wangan_dori (a
#: 3+3 trunk road) ~6.5 m off it, no room for an open-air end building with gates and restrooms (BUILDING_D), so it is a
#: one-lane GROUND HUB (橋上駅) -- the concourse over the track, the entrance annex on the open north side.
FORM_OVERRIDE = {"Waterpark": "ground_hub"}

# the ground hub's dimensions (橋上駅: a walled CAP over the passenger lanes carrying the airbridge concourse)
CAP_LEN = 30.0                     # the cap along the track: a whole number of MODULEs, centred on the platform centre
AF = 6.2                           # the airbridge floor's top over the bed (soffit 5.9: the gauge tops out at 4.2)
AF_T = 0.3
ROOF = 9.6                         # the cap's roof slab, underside over the bed
ROOF_T = 0.25
WALL_T = 0.3                       # the cap's outer side walls
ANNEX_D = 15.5                     # the entrance annex, across, outside the cap wall: paid strip, gate line, unpaid
ANNEX_PAID = 8.0                   # the annex's paid strip next to the cap wall: the stair up to the airbridge, the lift,
#                                    and under the mezzanine landing a RESTROOM BLOCK (WC_D deep) with a walkway past it;
#                                    the unpaid strip (ANNEX_D - ANNEX_PAID) holds the other restroom block and the machines
ANNEX_GATES = 8.3                  # the fare line's gate lanes, their centre along the axis (the SERVICE COUNTER stands
#                                    on the line beyond them, to the annex's +a end wall)
STAIR_RISE = 0.18                  # the most a riser may be (both stairs round their count up to keep under it)
STAIR_RUN = 0.29
CAP_STAIR_X = 6.0                  # a platform stair's foot, along the axis from the station centre (rises toward -a)
ANNEX_STAIR_X = 13.5               # the annex stair's foot (rises toward -a)
ANNEX_DOOR = (9.0, 13.0)           # the annex's street door (DOOR_W, two shutter bays), along the axis
ANNEX_DOOR_LARGE = (2.6, 2.6 + LARGE_ENTRANCE_W)   # a large hub's six-bay entrance: from past the machines to 0.3 m
                                   # short of the +X end wall
ANNEX_STORE = 2 * SHOP_UNIT        # a large ground hub's ONE store, past the annex's +X end along the track (user,
                                   # 2026-09-28): it opens INTO the annex's unpaid hall through the annex's end wall
                                   # (a glass sliding door; that wall's paid part stays solid), display glass on the
                                   # street, its floor the annex floor
# A STATION STORE's door is a SLIDING GLASS door (user, 2026-09-28): two leaves parting from the middle where the front
# is wide enough (STORE_DOOR_W2), else one (STORE_DOOR_W1); never a shutter
STORE_DOOR_W1 = 0.9
STORE_DOOR_W2 = 1.6
STORE_DOOR_H = 2.2
STORE_FRONT_2 = 4.0                # a front at least this wide gets the two-leaf door
WALL_DOOR = (-8.0, -2.0)
CAP_SW_SIDE = 2.2                  # a side platform's stair down from the concourse (and its lift), against the cap wall
CAP_SW_ISLAND = 3.0                # an island platform's stair (and its lift), on its centre line
PLINTH = 1.6                       # how far a hub's annex floor and cap walls reach below the bed (they stand on it)

# the ELEVATED hub's dimensions (高架駅: the F1 building fills the ground floor under the viaduct up to the deck)
EH_LIFT = 7.84                     # the bed over the ground at every elevated station: the rail plan's ELEVATED_Z (8.0
#                                    rail head over the ground) less the 0.16 m rail; the pieces are built at it
EH_LIFT_TOL = 0.05
EH_DECK_HALF = 5.0                 # the rail's own viaduct deck, half width (the `rail` preset: a 4.0 m lane + 1.0 m
#                                    shoulder); the station's slabs meet it there
EH_DECK_T = 0.8                    # its depth (point_model deck_thickness): the F1 ceiling and the slabs' underside
EH_SW = 2.5                        # the stair band between a platform's outer edge and the outer rail wall
EH_WALL_T = 0.3
EH_FLIGHTS = 3                     # the stair from F1 to the platform: three flights with two landings
EH_LAND = 1.5
EH_STAIR_LEN = 20.0                # the stair piece, along the axis (four modules)
EH_STAIR_FOOT = 9.5                # its foot, along the piece from its centre (the stair rises toward -a)
EH_GATE_LANES = 4                  # the gate lanes across the hall at each end of the paid box
EH_SIDE_GATE_LANES = 2             # the lanes of a gate bank in a long side's fare line (in half a module)
EH_SIDE_GATE_CAB = 0.2             # its cabinets
EH_WING = 5.0                      # the F1 wing past each rail wall: the unpaid hall along the long side
EH_WING_H = 4.6                    # its roof's top over the street
EH_CEIL = 3.8                      # the F1 hall's lowered ceiling over the street (the deck's underside is ~7 m up)
EH_COL = 0.4                       # a column in the rail wall's line at F1, at each module's -X end

# the LIFT (エレベーター) beside every platform stair of a hub (user, 2026-09-27): a square shaft as wide as the stair it
# serves, in the stair's own band, LIFT_GAP beyond the stair's TOP end so its doors never open into the stair's queue.
# Its doors face ALONG the track (both ends, a through car: in at one end, out at the other), never the rail side, and
# each is a two-leaf centre-opening SLIDE. The shaft is the kit piece's; the car, its doors and the landing doors are
# built at runtime by `world.Elevator` from the piece's `LIFT_` Empty.
LIFT_GAP = 3.0                     # from the stair's top end to the lift's nearer face, along the axis
LIFT_WALL_T = 0.12                 # the shaft's walls (the square is the stair's width OUTSIDE these)
LIFT_DOOR_W = 1.1                  # the clear door opening (a wheelchair and a suitcase: Japan's barrier-free >= 0.9)
LIFT_DOOR_H = 2.1
LIFT_HEAD = 2.6                    # the shaft rises this far over its top stop (the car, machine-room-less)
EH_ISLAND_SW = 2.5                 # an island platform's stair (and lift), on its centre line in the gap between decks
EH_LONG = 150.0                    # a station at least this long gets street entrances beside its paid box too
EH_LIFT_MODULE = 5.0               # an elevated hub's lift stands in its own 5 m module, beyond the stair piece
EH_WC_EDGE = 4.05                  # an elevated hub's restroom block stands under the MIDDLE lane, between the deck's
                                   # two column rows (their faces at +-4.1): its back this far to one side of the lane,
                                   # its open face WC_D back toward the other, a 3.2 m walkway before it
EH_WC_CLEAR = 1.0                  # the unpaid block's inner end, this far outside the low gate module
EH_COUNTER_WALL = 0.6              # the service counter on an end fare line stops this far short of the rail wall's
                                   # line (the long side's gate cabinets reach 0.45 m inside it)



@dataclass
class Lane:
    line: str
    c: float                      # the lane's centreline, across the station axis
    cover: tuple = None           # (a0, a1): where the lane's own platform span runs along the axis (None: whole)

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
    lift: float = 0.0             # the bed over the ground under the station centre (an elevated station's F1 height)
    entry_rise: dict = field(default_factory=dict)  # {"left"/"right": the open-air door sill over its street, m}
    entry_kind: dict = field(default_factory=dict)  # {"left"/"right": "side" | "out"}: which way its slope runs

    @property
    def kit(self):
        """Laid out from the station kit (PLAN.md): every station -- since step 6 (Central, three lanes) the elevated hub
        over any number of lanes too."""
        return self.form in KIT_FORMS

    @property
    def form(self):
        if self.elevated:
            return "elevated_hub"
        if self.name in FORM_OVERRIDE:
            return FORM_OVERRIDE[self.name]
        return "open_air" if len(self.lanes) == 1 and self.kind in ("small", "standard") else "ground_hub"


def shutter_bays(u0, u1, n):
    """[(b0, b1)] of the n roller-shutter bays of an opening from u0 to u1: equal bays, SHUTTER_POST between two."""
    w = (u1 - u0 - (n - 1) * SHUTTER_POST) / n
    if w < 0.9:
        raise SystemExit("an opening %.2f m wide holds no %d shutter bays of 0.9 m" % (u1 - u0, n))
    return [(u0 + k * (w + SHUTTER_POST), u0 + k * (w + SHUTTER_POST) + w) for k in range(n)]


def is_large(st):
    """A LARGE hub (six-bay entrance, shops): every hub form but a standard-size station squeezed onto one."""
    return st.form in ("ground_hub", "elevated_hub") and st.name not in FORM_OVERRIDE


def annex_door(st):
    """(a0, a1): the annex's street opening along the axis."""
    return ANNEX_DOOR_LARGE if is_large(st) else ANNEX_DOOR


def annex_span(st):
    """(a0, a1): the annex along the axis, a large hub's store (past its +X end) included."""
    return -CAP_LEN / 2.0, CAP_LEN / 2.0 + (ANNEX_STORE if is_large(st) else 0.0)


def store_door_w(front):
    """A station store's sliding glass door for a front `front` wide: 2 leaves when it is wide enough, else 1."""
    return STORE_DOOR_W2 if front >= STORE_FRONT_2 else STORE_DOOR_W1


def entry_n(rise):
    """The entry piece (`OA_Entry_<n>`) whose n risers of ENTRY_RISE come nearest `rise` (the door sill over the
    street): within half a riser, which the piece's plinth absorbs."""
    return max(ENTRY_N[0], min(ENTRY_N[1], int(round(rise / ENTRY_RISE))))


def ramp_segments(n):
    """[(run, rise)] of the entry slope for an n-riser entry, the door end first: 1:RAMP_SLOPE, no segment rising more
    than RAMP_SEG_RISE (a RAMP_LAND landing between two)."""
    rise = n * ENTRY_RISE
    k = int(math.ceil(rise / RAMP_SEG_RISE - 1e-9))
    return [(RAMP_SLOPE * rise / k, rise / k)] * k


def ramp_len(n):
    """The slope's whole length along the front, from the door landing's edge (segments and the landings between)."""
    segs = ramp_segments(n)
    return sum(r for r, _h in segs) + RAMP_LAND * (len(segs) - 1)


def ramp_run(n):
    """The open-air entrance ramp's whole length out from the door (`OA_Ramp_<n>`): the landing at the sill, then the
    legs and the landings between them."""
    return RAMP_LAND + ramp_len(n)


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
    if st.form == "elevated_hub":
        return eh_elements(st)
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
        # the end building: in line with the platform, from the platform's end outward, BUILDING_D across from the
        # platform's track edge (away from the rail)
        ba = (half, half + BUILDING_LEN) if end > 0 else (-half - BUILDING_LEN, -half)
        bc = sorted((inner, inner + sg * BUILDING_D))
        out.append(Box("building", ba[0], ba[1], bc[0], bc[1], top, top + BUILDING_H, side))
        # the gate lanes cross it GATE_X in from the platform-end face, near the track-side wall; their line is what
        # splits unpaid (street) from paid (platform)
        ga = end * (half + GATE_X)
        for i in range(GATE_LANES):
            cc = inner + sg * (BUILDING_T + 0.8 + (i + 0.5) * (GATE_W + 0.25))
            out.append(Box("gate", ga - 0.05, ga + 0.05, cc - GATE_W / 2, cc + GATE_W / 2, top, top + 1.0,
                           "%s_%d" % (side, i)))
        # the entry outside the door: ONE straight ramp, door-wide, in line with the door, down to the street
        n = entry_n(st.entry_rise.get(side, PLATFORM_H))
        a_door = end * (half + BUILDING_LEN)
        dc = inner + sg * DOOR_OFF
        out.append(Box("entry", *sorted((a_door, a_door + end * ramp_run(n))),
                       *sorted((dc - DOOR_W / 2, dc + DOOR_W / 2)), top - n * ENTRY_RISE, top, side))
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


def lift_door_w(inner_d):
    """A lift door's clear opening in a shaft `inner_d` wide inside (across the door): LIFT_DOOR_W, or less where the
    shaft is too narrow to pocket a two-leaf centre-opening door (each leaf slides beside the opening, so the opening
    is at most half the inside)."""
    return round(min(LIFT_DOOR_W, inner_d / 2.0 - 0.05), 3)


def hub_lift(sw):
    """(x0, x1) of a ground hub platform's lift along its cap piece (the stair's foot at CAP_STAIR_X rises toward -x;
    the lift is LIFT_GAP beyond the stair's top end, as wide as the stair `sw` along x too: a square)."""
    n, _r = stair_steps(AF - PLATFORM_H)
    x_top = CAP_STAIR_X - (n - 1) * STAIR_RUN
    return x_top - LIFT_GAP - sw, x_top - LIFT_GAP


def hub_band(st: Station):
    """(lo, hi): the across extent of the platforms, i.e. the cap's inside."""
    pl = platforms(st)
    return min(p[0] for p in pl), max(p[1] for p in pl)


def annex_band(st: Station, side):
    lo, hi = hub_band(st)
    if side == "left":
        return hi + WALL_T, hi + WALL_T + ANNEX_D
    return lo - WALL_T - ANNEX_D, lo - WALL_T


def annex_entry_n(st: Station):
    """The risers of the entry (stair + smooth slope, `GH_Entry_<n>`) outside the annex door down to the street, or 0
    when the street is at the floor (under 0.2 m: the door's sill takes it)."""
    if st.door_step < 0.2:
        return 0
    if st.door_step > (ENTRY_N[1] + 0.5) * ENTRY_RISE:
        raise SystemExit("%s: the street is %.2f m below its entrance annex's door (the entry pieces carry %.2f)"
                         % (st.name, st.door_step, ENTRY_N[1] * ENTRY_RISE))
    return entry_n(st.door_step)


def annex_entry_depth(st: Station):
    """How far the entry reaches out from the annex's street face (its landing and its stair), 0 with none."""
    n = annex_entry_n(st)
    return ENTRY_LAND + (n - 1) * STAIR_RUN if n else 0.0


def hub_entrance(st: Station, side):
    """(a, c) of the street 3 m outside the annex's door (past its steps down to the street, if any)."""
    c0, c1 = annex_band(st, side)
    out = 3.0 + annex_entry_depth(st)
    d0, d1 = annex_door(st)
    return (0.5 * (d0 + d1), c1 + out if side == "left" else c0 - out)


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
        # the lift beside this platform's stair (the cap piece's own; `hub_lift`), against the cap wall on a side
        # platform, on the centre line on an island
        sw = CAP_SW_ISLAND if len(faces) == 2 else CAP_SW_SIDE
        lx0, lx1 = hub_lift(sw)
        if len(faces) == 2:
            lc = ((c0 + c1) / 2 - sw / 2, (c0 + c1) / 2 + sw / 2)
        else:
            lc = (c1 - sw, c1) if c0 > 0 else (c0, c0 + sw)
        out.append(Box("lift", lx0, lx1, lc[0], lc[1], PLATFORM_H, AF + LIFT_HEAD, tag))
    out.append(Box("concourse", -hc, hc, lo, hi, AF - AF_T, AF, "cap"))
    out.append(Box("roof", -hc, hc, lo - WALL_T, hi + WALL_T, ROOF, top, "cap"))
    out.append(Box("wall", -hc, hc, hi, hi + WALL_T, 0.0, top, "left"))
    out.append(Box("wall", -hc, hc, lo - WALL_T, lo, 0.0, top, "right"))
    if st.entrance:
        c0, c1 = annex_band(st, st.entrance)
        out.append(Box("annex", -hc, hc, c0, c1, 0.0, top, st.entrance))
        if is_large(st):
            out.append(Box("store", hc, annex_span(st)[1], c0, c1, 0.0, SHOP_H, st.entrance))
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
    left = st.entrance == "left"
    hand = "L" if left else "R"
    large = is_large(st)
    out += _piece_props("GH_%s_%s" % ("AnnexLarge" if large else "Annex", hand), 0.0, 0.5 * (c0 + c1), 0.0, 0.0)
    if large:
        # the ONE store past the annex's +X end, its floor the annex's: it opens into the unpaid hall through the
        # annex's end wall (the glass door is GH_AnnexLarge's), display glass toward the street
        out += _piece_props("GH_AnnexStore_" + hand, hc + ANNEX_STORE / 2.0, 0.5 * (c0 + c1), 0.0, 0.0)
    n = annex_entry_n(st)
    if n:
        # the entry down to the street (the open-air form's stair + smooth 1:15 slope): its origin on the door's centre
        # at the floor, its +X turned out to the street (yaw 90 on the left, -90 on the right), so its slope runs
        # along the annex's front toward -a, away from the door's end of the annex. A large hub's stair spans its
        # whole six-bay opening (`GH_EntryWide_*`)
        c = c1 if left else c0
        d0, d1 = annex_door(st)
        out += _piece_props("GH_%s_%d_%s" % ("EntryWide" if large else "Entry", n, hand), 0.5 * (d0 + d1), c,
                            0.0, 90.0 if left else -90.0)
    return out


def choose_entrance(st: Station, clear, cost):
    """The side ('left' / 'right') the ground hub's entrance annex stands on: among the sides where `clear(cx, cy,
    ux, uy, half along, half across)` (record frame) says it stands clear and it keeps out of every gauge and turnout
    throat, the one whose street door has the lower `cost(x, y)`; None when neither side does."""
    best = None
    for side in ("left", "right"):
        c0, c1 = annex_band(st, side)
        a0, a1 = annex_span(st)
        cx, cy = to_record(st, 0.5 * (a0 + a1), 0.5 * (c0 + c1))
        if not clear(cx, cy, st.ux, st.uy, 0.5 * (a1 - a0) + 0.5, ANNEX_D / 2.0 + 0.5):
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


# ── the ELEVATED HUB (高架駅) ───────────────────────────────────────────────────────────────────────────────────────
# One two-way lane on the rail's own viaduct deck (EH_DECK_HALF either side of the lane, EH_DECK_T deep, carried over
# the station by the building itself: the rail record puts no pier there). Across, from the lane outward on each side:
# the platform (on the deck and on the building's roof slab), the STAIR BAND (a slab at platform level beside it, with
# the stair opening), and the outer RAIL WALL, which rises from the ground past the deck to carry the shed roof over
# platform and band. Under all of it, the F1 building fills the ground floor end to end, its floor at the street
# (EH_LIFT below the bed), and reaches EH_WING past each rail wall in a single-storey WING (user, 2026-09-27: the
# larger-station plan). F1 is a PAID BOX in the middle -- both stairs and both lifts inside it -- ringed by the unpaid
# hall: the wings along the long sides (a street entrance in each near both ends: four) and the ends of the hall. The
# box is closed by FARE LINES on all four sides: across the hall at each end (`EH_FloorGate`), and along each long side
# in the line of the rail wall, whose F1 storey is columns and a railing (`EH_FareSide`) with a GATE BANK at each
# corner (`EH_FareSideGate`); along the stair the rail wall comes down to the floor (the stair's own wall). A lowered
# CEILING (EH_CEIL) closes the hall under the viaduct deck, open over the stairs.

def eh_band(st: Station):
    """(P0, P1, B1, W1): across from the lane's centre, the platform's track edge, its outer edge, the stair band's
    outer edge (the rail wall's inner face) and the wall's outer face."""
    w = PLATFORM_W.get(st.kind, PLATFORM_W["standard"])
    p0 = TRACK_HALF + PLATFORM_EDGE
    p1 = p0 + w
    return p0, p1, p1 + EH_SW, p1 + EH_SW + EH_WALL_T


def eh_outer(st: Station):
    """The F1 wing's outer face, across from the lane's centre."""
    return eh_band(st)[3] + EH_WING


def eh_span(st: Station):
    """(lo, hi): the outermost lanes' centres, across. The outer side structure (platform, stair band, rail wall, wing)
    stands outside each of them (`eh_band` measured from it); between two lanes the platform is an ISLAND."""
    cs = sorted(ln.c for ln in st.lanes)
    return cs[0], cs[-1]


def eh_mid(st: Station):
    """The across centre of the lanes: the origin of the pieces that span the whole building (`EH_Floor*`,
    `EH_EndWall`)."""
    lo, hi = eh_span(st)
    return 0.5 * (lo + hi)


def eh_islands(st: Station):
    """[(c0, c1, cm)]: each ISLAND platform between two neighbouring lanes -- its two track edges and its centre line,
    where its stair and lift stand in the gap between the two lanes' viaduct decks (EH_ISLAND_SW wide: a stairwell cut
    through the platform). Refused when the decks leave no room for them."""
    cs = sorted(ln.c for ln in st.lanes)
    p0 = TRACK_HALF + PLATFORM_EDGE
    out = []
    for a, b in zip(cs, cs[1:]):
        gap = (b - a) - 2 * EH_DECK_HALF
        if gap < EH_ISLAND_SW + 0.4:
            raise SystemExit("%s: lanes %.1f m apart leave %.2f m between their decks, under the %.1f m an island "
                             "platform's stair needs" % (st.name, b - a, gap, EH_ISLAND_SW + 0.4))
        if (b - a) - 2 * p0 > ISLAND_MAX:
            raise SystemExit("%s: lanes %.1f m apart are too far for one island platform" % (st.name, b - a))
        out.append((a + p0, b - p0, 0.5 * (a + b)))
    return out


def eh_core(st: Station):
    """The name suffix of the whole-building pieces: the platform width, and for more than one lane the lane count and
    spacing (`EH_Floor_345_3x14`), since those pieces are as wide as the building."""
    w = PLATFORM_W.get(st.kind, PLATFORM_W["standard"])
    if len(st.lanes) == 1:
        return _wname(w)
    cs = sorted(ln.c for ln in st.lanes)
    sp = {round(b - a, 3) for a, b in zip(cs, cs[1:])}
    if len(sp) != 1:
        raise SystemExit("%s: an elevated hub's lanes must be evenly spaced (%s)" % (st.name, sorted(sp)))
    return "%s_%dx%s" % (_wname(w), len(cs), _wname(sp.pop()))


def eh_stairs():
    """[(x front, z top)] of every step of the F1 -> platform stair in its piece's frame (x along from the piece's
    centre, z over the bed), the lowest first, and x_top (where the platform-level floor begins): EH_FLIGHTS flights of
    equal risers under STAIR_RISE, an EH_LAND landing between two, rising toward -x from EH_STAIR_FOOT."""
    z0, z1 = -EH_LIFT, PLATFORM_H
    n = int(math.ceil((z1 - z0) / STAIR_RISE - 1e-9))
    n += (-n) % EH_FLIGHTS
    r, nf = (z1 - z0) / n, n // EH_FLIGHTS
    x, z, out = EH_STAIR_FOOT, z0, []
    for f in range(EH_FLIGHTS):
        for k in range(nf):
            z += r
            if f == EH_FLIGHTS - 1 and k == nf - 1:
                break
            out.append((x, z))
            x -= EH_LAND if k == nf - 1 else STAIR_RUN
    return out, x


def eh_lift():
    """(x0, x1) of an elevated hub's lift in ITS module's frame (the module just beyond the stair piece, toward -a):
    LIFT_GAP beyond the stair's top end, EH_SW square."""
    _s, x_top = eh_stairs()
    face = x_top - LIFT_GAP + EH_STAIR_LEN / 2 + EH_LIFT_MODULE / 2      # its +x face, in the module's frame
    return face - EH_SW, face


EH_ENTRANCE_MODULES = 3            # a wing's six-bay ENTRANCE spans three modules (LARGE_ENTRANCE_W in 15 m)


def eh_modules(st: Station):
    """({a centre: role}, stair centre): the station's 5 m modules along the axis. The PAID BOX, centred on the
    station: 'gate_lo' | 'lift' | the stair piece's four | 'gate_hi' (a gate module's fare line across the hall is
    at its centre, its side gate banks in its inner half); an ENTRANCE (the wings' six-bay street openings) of three
    modules at each end of the station -- 'entrance' its centre (the piece's), 'entrance_flank' the two beside it
    (no wing piece of their own); everything else 'plain' (its wing a SHOP)."""
    half = st.length / 2.0
    n = st.length / MODULE
    if abs(n - round(n)) > 1e-6:
        raise SystemExit("%s: platform %.2f m is not a whole number of %.0f m modules" % (st.name, st.length, MODULE))
    ew = EH_ENTRANCE_MODULES * MODULE
    if st.length < 2 * ew + EH_STAIR_LEN + 3 * MODULE:
        raise SystemExit("%s: an elevated hub needs a %.0f m platform at least (%.0f)"
                         % (st.name, 2 * ew + EH_STAIR_LEN + 3 * MODULE, st.length))
    # the box spans [s0 - 10, s0 + 25] (gate, lift, the stair's four modules, gate): centred, snapped to the grid
    s0 = -half + MODULE * round((half - 7.5) / MODULE)
    stair_c = s0 + EH_STAIR_LEN / 2
    roles = {s0 - 7.5: "gate_lo", s0 - 2.5: "lift", s0 + EH_STAIR_LEN + 2.5: "gate_hi"}
    ents = [-half + ew / 2, half - ew / 2]
    if st.length >= EH_LONG:
        # a long station (Central, 300 m) also has entrances right outside each end of its paid box, so nobody walks
        # the length of the building in the unpaid hall to reach the gates (user, 2026-09-27: "several entrances")
        ents += [s0 - 10.0 - ew / 2, s0 + EH_STAIR_LEN + 5.0 + ew / 2]
    for e in ents:
        roles[e] = "entrance"
        for f in (e - MODULE, e + MODULE):
            roles[f] = "entrance_flank"
    out = {}
    for k in range(int(round(n))):
        a = -half + MODULE * (k + 0.5)
        if s0 < a < s0 + EH_STAIR_LEN:
            continue
        out[a] = next((r for c, r in roles.items() if abs(a - c) < 1e-6), "plain")
    vals = list(out.values())
    if vals.count("entrance") != len(ents) or vals.count("entrance_flank") != 2 * len(ents) \
            or vals.count("gate_lo") != 1 or vals.count("gate_hi") != 1 or vals.count("lift") != 1:
        raise SystemExit("%s: %.0f m is too short for the paid box and its entrances" % (st.name, st.length))
    return out, stair_c


def eh_box(st: Station):
    """(a0, a1): the paid box along the axis, between the two end fare lines (the gate modules' centres)."""
    mods, _sc = eh_modules(st)
    return (next(a for a, r in mods.items() if r == "gate_lo"), next(a for a, r in mods.items() if r == "gate_hi"))


def eh_restrooms(st: Station):
    """[(a, c, role)]: the two restroom blocks of an elevated hub (PLAN.md step 6b), each WC_L along the axis under the
    MIDDLE lane, between its deck's column rows, back EH_WC_EDGE to the +c side and open toward -c: 'paid' centred on
    the stair span inside the paid box, 'unpaid' in the end hall just outside the low fare line. Neither widens the
    building: the F1 under the lane is otherwise an open hall."""
    mods, stair_c = eh_modules(st)
    lanes = sorted(ln.c for ln in st.lanes)
    c = lanes[len(lanes) // 2] + EH_WC_EDGE - WC_D / 2.0
    ga = next(a for a, r in mods.items() if r == "gate_lo")
    ua = ga - MODULE / 2.0 - EH_WC_CLEAR - WC_L / 2.0
    if ua - WC_L / 2.0 < -st.length / 2.0 + 1.0:
        raise SystemExit("%s: no room for the unpaid restroom block before the low end wall" % st.name)
    return [(stair_c, c, "paid"), (ua, c, "unpaid")]


def eh_elements(st: Station):
    half = st.length / 2.0
    lo, hi = eh_span(st)
    p0, p1, b1, w1 = eh_band(st)
    wo = eh_outer(st)
    sh = PLATFORM_H + SHED_CLEAR
    f1 = -EH_LIFT
    out = [Box("floor", -half, half, lo - wo, hi + wo, f1 - 0.3, f1, "f1")]
    ba0, ba1 = eh_box(st)
    for sg, tag, base in ((1.0, "left", hi), (-1.0, "right", lo)):
        def band(u0, u1):
            return sorted((base + sg * u0, base + sg * u1))
        out.append(Box("platform", -half, half, *band(p0, p1), 0.0, PLATFORM_H, tag))
        out.append(Box("roof", -half, half, *band(EH_DECK_HALF, p1), -EH_DECK_T, 0.0, tag))
        out.append(Box("band", -half, half, *band(p1, b1), -EH_DECK_T, PLATFORM_H, tag))
        out.append(Box("wall", -half, half, *band(b1, w1), f1 + EH_CEIL, sh, tag))
        out.append(Box("shed", -half, half, *band(p0 + 0.2, w1), sh, sh + SHED_T, tag))
        out.append(Box("wing", -half, half, *band(w1, wo), f1, f1 + EH_WING_H, tag))
        out.append(Box("fare", ba0, ba1, *band(b1, w1), f1, f1 + 1.1, tag))
        for a0 in (-half, half - FENCE_T):
            out.append(Box("fence", a0, a0 + FENCE_T, *band(p0, b1), PLATFORM_H, PLATFORM_H + FENCE_H, tag + "_end"))
    for i, (c0, c1, cm) in enumerate(eh_islands(st)):
        tag = "island_%d" % i
        g = 0.5 * (c1 - c0) - (EH_DECK_HALF - TRACK_HALF - PLATFORM_EDGE)       # half the gap between the decks
        out.append(Box("platform", -half, half, c0, c1, 0.0, PLATFORM_H, tag))
        out.append(Box("roof", -half, half, cm - g, cm + g, -EH_DECK_T, 0.0, tag))
        out.append(Box("shed", -half, half, c0 + 0.2, c1 - 0.2, sh, sh + SHED_T, tag))
        for a0 in (-half, half - FENCE_T):
            out.append(Box("fence", a0, a0 + FENCE_T, c0, c1, PLATFORM_H, PLATFORM_H + FENCE_H, tag + "_end"))
    for a in (ba0, ba1):
        out.append(Box("fare", a - 0.05, a + 0.05, lo - b1, hi + b1, f1, f1 + 1.1, "end"))
    for a0 in (-half, half - 0.3):
        out.append(Box("wall", a0, a0 + 0.3, lo - wo, hi + wo, f1, -EH_DECK_T, "end"))
    out.append(Box("ceiling", -half, half, lo - wo, hi + wo, f1 + EH_CEIL, f1 + EH_CEIL + 0.05, "f1"))
    mods, _sc = eh_modules(st)
    la = next(a for a, r in mods.items() if r == "lift")
    lx0, lx1 = eh_lift()
    for sg, tag, base in ((1.0, "left", hi), (-1.0, "right", lo)):
        cc = sorted((base + sg * p1, base + sg * b1))
        out.append(Box("lift", la + lx0, la + lx1, cc[0], cc[1], -EH_LIFT, PLATFORM_H + LIFT_HEAD, tag))
    for i, (_c0, _c1, cm) in enumerate(eh_islands(st)):
        out.append(Box("lift", la + lx0, la + lx1, cm - EH_ISLAND_SW / 2, cm + EH_ISLAND_SW / 2, -EH_LIFT,
                       PLATFORM_H + LIFT_HEAD, "island_%d" % i))
    for a, c, role in eh_restrooms(st):
        out.append(Box("restroom", a - WC_L / 2, a + WC_L / 2, c - WC_D / 2, c + WC_D / 2, f1, f1 + EH_CEIL - 0.02,
                       role))
    return out


def eh_entrances(st: Station):
    """[(a, c, h)] of the street 3 m outside each wing entrance (both long sides, at every 'entrance' module)."""
    mods, _ = eh_modules(st)
    wo = eh_outer(st)
    lo, hi = eh_span(st)
    return [(a, (hi + wo + 3.0) if sg > 0 else (lo - wo - 3.0), -EH_LIFT) for a, r in sorted(mods.items())
            if r == "entrance" for sg in (1.0, -1.0)]


def eh_props(st: Station):
    if abs(st.lift - EH_LIFT) > EH_LIFT_TOL:
        raise SystemExit("%s: its bed stands %.2f m over the ground; the elevated hub's pieces are built for %.2f"
                         % (st.name, st.lift, EH_LIFT))
    half = st.length / 2.0
    lo, hi = eh_span(st)
    mid = eh_mid(st)
    side_c = {"L": hi, "R": lo}                   # the side structure stands outside the outermost lane on its side
    w = PLATFORM_W.get(st.kind, PLATFORM_W["standard"])
    ws = _wname(w)
    core = eh_core(st)
    islands = eh_islands(st)
    p0, p1, b1, _w1 = eh_band(st)
    mods, stair_c = eh_modules(st)
    out = []
    for a, role in mods.items():
        gate = role.startswith("gate")
        # a gate module's fare line across the hall has its UNPAID side (+X of the piece) facing out of the box, and
        # its side gate banks in its inner half (-X): turned 180 at the low end, where the hands swap sides
        yaw = 180.0 if role == "gate_lo" else 0.0
        out += _piece_props("EH_FloorGate_" + core if gate else "EH_Floor_" + core, a, mid, 0.0, yaw)
        for hand in ("L", "R"):
            h2 = hand if yaw == 0.0 else {"L": "R", "R": "L"}[hand]
            c = side_c[hand]
            out += _piece_props("EH_%s_%s_%s" % ("SideLift" if role == "lift" else "Side", ws, h2), a, c, 0.0, yaw)
            # the wing: a six-bay ENTRANCE (its piece spans the flanks too), the machines beside each end fare line,
            # and everywhere else a SHOP facing the hall (the large hubs' shops along the side, user 2026-09-27)
            wing = {"entrance": "WingEntrance", "entrance_flank": None}.get(
                role, "WingMachines" if gate else "WingShop")
            if wing:
                out += _piece_props("EH_%s_%s_%s" % (wing, ws, h2), a, c, 0.0, yaw)
            if gate:
                out += _piece_props("EH_FareSideGate_%s_%s" % (ws, h2), a, c, 0.0, yaw)
            elif role == "lift":
                out += _piece_props("EH_FareSide_%s_%s" % (ws, h2), a, c, 0.0, yaw)
        for c0, c1, cm in islands:
            wi = _wname(round(c1 - c0, 3))
            out += _piece_props("EH_%s_%s" % ("IslandLift" if role == "lift" else "Island", wi), a, cm, 0.0, 0.0)
    for hand in ("L", "R"):
        out += _piece_props("EH_SideStair_%s_%s" % (ws, hand), stair_c, side_c[hand], 0.0, 0.0)
    for c0, c1, cm in islands:
        out += _piece_props("EH_IslandStair_" + _wname(round(c1 - c0, 3)), stair_c, cm, 0.0, 0.0)
    for k in range(int(round(EH_STAIR_LEN / MODULE))):
        ak = stair_c - EH_STAIR_LEN / 2 + MODULE * (k + 0.5)
        out += _piece_props("EH_Floor_" + core, ak, mid, 0.0, 0.0)
        for hand in ("L", "R"):
            out += _piece_props("EH_WingShop_%s_%s" % (ws, hand), ak, side_c[hand], 0.0, 0.0)
    for sg, base in ((1.0, hi), (-1.0, lo)):
        cc = base + sg * (p0 + p1) / 2.0
        yaw = 0.0 if sg > 0 else 180.0
        for k in range(int(round(st.length / MODULE))):
            out += _piece_props("EH_Platform_" + ws, -half + MODULE * (k + 0.5), cc, 0.0, yaw)
        ce = base + sg * (p0 + b1) / 2.0
        for se in (1.0, -1.0):
            out += _piece_props("EH_EndFence_" + ws, se * (half - FENCE_T / 2), ce, PLATFORM_H, 0.0)
    for c0, c1, cm in islands:
        for se in (1.0, -1.0):
            out += _piece_props("EH_IslandEndFence_" + _wname(round(c1 - c0, 3)), se * (half - FENCE_T / 2), cm,
                                PLATFORM_H, 0.0)
    out += _piece_props("EH_EndWall_" + core, half, mid, 0.0, 0.0)
    out += _piece_props("EH_EndWall_" + core, -half, mid, 0.0, 180.0)
    for a, c, _role in eh_restrooms(st):
        out += _piece_props("EH_Restroom", a, c, 0.0, 0.0)
    return out


def eh_kit(sts):
    """[(platform w, [island widths], core suffix, lane offsets from the core's centre)]: every elevated hub's piece
    set (the generator makes one per entry, `blender/tools/build_station_blends.py`)."""
    out = {}
    for st in sts.values():
        if st.form != "elevated_hub":
            continue
        mid = eh_mid(st)
        key = eh_core(st)
        out[key] = (PLATFORM_W.get(st.kind, PLATFORM_W["standard"]),
                    sorted({round(c1 - c0, 3) for c0, c1, _cm in eh_islands(st)}), key,
                    [round(ln.c - mid, 3) for ln in sorted(st.lanes, key=lambda ln: ln.c)])
    return [out[k] for k in sorted(out)]


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
    col = {k: entry[src] for k, src in (("boxes", "collide_boxes"), ("hulls", "collide_hulls")) if entry.get(src)}
    out = [{"piece": KIT + ":" + ref, "at": [x, z], "y": y, "yaw": yaw, "collide": col or "none"}]
    for g in entry.get("gates", ()):
        gx, gz = LB.rot_xz(yaw, g["pos"][0], g["pos"][2])
        ox, oz = LB.rot_xz(yaw, g["out"][0], g["out"][2])
        out.append({"at": [x + gx, z + gz], "y": y + g["pos"][1], "yaw": math.degrees(math.atan2(ox, oz)),
                    "door": {"kind": "gate", "w": g["w"], "h": g["h"]}})
    for lf in entry.get("lifts", ()):
        lx, lz = LB.rot_xz(yaw, lf["pos"][0], lf["pos"][2])
        out.append({"at": [x + lx, z + lz], "y": y + lf["pos"][1], "yaw": yaw,
                    "lift": {k: lf[k] for k in ("w", "d", "rise", "door_w", "door_h")}})
    return out


def props(st: Station):
    """The station as layout_buildings props (see `elements` for the same plan as boxes)."""
    if st.form == "ground_hub":
        return hub_props(st)
    if st.form == "elevated_hub":
        return eh_props(st)
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
        sg = 1.0 if left else -1.0
        inner = c0 if left else c1
        bc = inner + sg * BUILDING_D / 2.0
        out += _piece_props("OA_Building_%s_%s" % (ws, hand), end * (half + BUILDING_LEN / 2.0), bc, 0.0, byaw)
        risers = entry_n(st.entry_rise.get(side, PLATFORM_H))
        out += _piece_props("OA_Ramp_%d" % risers, end * (half + BUILDING_LEN), inner + sg * DOOR_OFF, PLATFORM_H,
                            byaw)
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
    if st.form == "elevated_hub":
        entr += [list(to_godot_local(*e)) for e in eh_entrances(st)]
    for c0, c1, _f in (platforms(st) if st.form == "open_air" else ()):
        side = "left" if c0 > 0 else "right"
        end = st.building_end.get(side, 1)
        a, c = entrance(st, side, end)
        entr.append(list(to_godot_local(a, c, PLATFORM_H - entry_n(st.entry_rise.get(side, PLATFORM_H)) * ENTRY_RISE)))
    for sg in (1.0, -1.0):
        for ln in st.lanes:
            bed.append(list(to_godot_local(sg * (half + BUILDING_LEN + 12.0), ln.c, 0.0)))
    out = {"id": "Station_" + st.name.replace(" ", ""), "kit": KIT, "pieces": [], "boxes": [], "doors": [],
           "station": {"form": st.form, "name": st.name, "length": st.length,
                       "lanes": [[ln.line, ln.c] for ln in st.lanes],
                       "platforms": [[-c1, -c0] for c0, c1, _f in platforms(st)],   # Godot z band of each
                       "platform_top": PLATFORM_H, "entrances": entr, "bed_points": bed,
                       # the street below the bed, and (an elevated hub) the rail's own viaduct deck the station stands
                       # in: [half width, depth] -- a stand probe builds both, since the scene holds neither
                       "street": -EH_LIFT if st.form == "elevated_hub" else 0.0,
                       "deck": [EH_DECK_HALF, EH_DECK_T] if st.form == "elevated_hub" else [],
                       # an elevated hub's F1: the paid box along the axis (Godot x) and the wings' outer face
                       "paid_box": list(eh_box(st)) if st.form == "elevated_hub" else [],
                       # its restroom blocks: [Godot x of the centre, Godot z of the door face, role]
                       "restrooms": [[a, -(c - WC_D / 2.0), r] for a, c, r in eh_restrooms(st)]
                       if st.form == "elevated_hub" else [],
                       # across the axis on the LEFT side (+c): the wing's outer face and the rail wall's two faces,
                       # measured from the axis (the outermost lane on that side carries them)
                       "outer": eh_span(st)[1] + eh_outer(st) if st.form == "elevated_hub" else 0.0,
                       "rail_wall": [eh_span(st)[1] + v for v in eh_band(st)[2:]] if st.form == "elevated_hub"
                       else []}}
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


def end_building(st: Station, side, end, kind=None):
    """(centre a, centre c, half along, half across) of `side`'s end building standing at end `end` (+1 / -1)."""
    half = st.length / 2.0
    for c0, c1, _f in platforms(st):
        if ("left" if c0 > 0 else "right") != side:
            continue
        sg = 1.0 if side == "left" else -1.0
        inner = c0 if side == "left" else c1
        # the building AND its entry ramp (straight out from the door, in line with it) and the apron at its foot --
        # the whole of what must clear the roads; the ramp is taken at a typical rise (PLATFORM_H over the street)
        n = entry_n(st.entry_rise.get(side, PLATFORM_H + 0.14))
        along = BUILDING_LEN + ramp_run(n) + FOOT_GAP
        across = BUILDING_D
        bc = sorted((inner, inner + sg * across))
        return (end * (half + along / 2.0), 0.5 * (bc[0] + bc[1]), along / 2.0, 0.5 * (bc[1] - bc[0]))
    raise KeyError(side)


def entrance(st: Station, side, end, kind=None):
    """(a, c) of the street outside `side`'s end building at end `end`: on its door's centre line, 3 m past the apron
    at the foot of its entry ramp."""
    a, _c, ha, _hc = end_building(st, side, end, kind)
    inner = next((c0 if side == "left" else c1) for c0, c1, _f in platforms(st) if ("left" if c0 > 0 else "right")
                 == side)
    return (a + end * (ha + 3.0), inner + (1.0 if side == "left" else -1.0) * DOOR_OFF)


def extent(st: Station):
    """(half along, half across) of everything the station owns, whichever ends its buildings stand at (a ground
    hub: whichever side its entrance annex stands on)."""
    if st.form == "ground_hub":
        lo, hi = hub_band(st)
        return st.length / 2.0, max(-lo, hi) + WALL_T + ANNEX_D + annex_entry_depth(st)
    if st.form == "elevated_hub":
        return st.length / 2.0, max(abs(ln.c) for ln in st.lanes) + eh_outer(st)
    hc = max(abs(end_building(st, sd, 1)[1]) + end_building(st, sd, 1)[3] for sd in ("left", "right"))
    return st.length / 2.0 + 2 * end_building(st, "left", 1)[2], hc


def choose_ends(st: Station, clear, cost, front=None):
    """{side: +1 | -1}: for each platform, the end its building stands at. `front` (the rail plan's authored front
    end, `island_rail_layout.STATION_FRONT`: the end whose ramp comes down to its street) wins when its BUILDING
    stands clear -- the ramp's foot is meant to meet the street, so it is not asked to clear it. Else, among the ends
    where `clear(cx, cy, ux, uy, half along, half across)` (record frame) says the building AND its entry ramp stand
    clear, the one whose street entrance has the lower `cost(x, y)` (the town is nearer). A side with no clear end is
    left out, and the caller reports it."""
    out = {}
    half = st.length / 2.0
    for side in ("left", "right"):
        if front:
            _a, c, _ha, hc = end_building(st, side, front)
            cx, cy = to_record(st, front * (half + BUILDING_LEN / 2.0), c)
            if clear(cx, cy, st.ux, st.uy, BUILDING_LEN / 2.0 + 0.5, hc + 0.5):
                out[side] = front
                st.entry_kind[side] = "ramp"
                continue
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
            st.entry_kind[side] = "ramp"
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
    for ln in st.lanes:
        # every lane runs the platform's whole length: a lane whose track ends inside the station (Central's Blue and
        # Harbour lines until 2026-09-27) would leave the kit's platforms beside a missing deck
        if ln.cover and (ln.cover[0] > -half + 1.0 or ln.cover[1] < half - 1.0):
            bad.append("%s: the %s's track covers only a %+.1f..%+.1f of the %.0f m platform"
                       % (st.name, ln.line, ln.cover[0], ln.cover[1], st.length))
    for line, (a_end, _c) in st.branches:
        if -half < a_end < half:
            bad.append("%s: the %s branch leaves inside the platform (a %.1f)" % (st.name, line, a_end))
    return bad


def kit_widths(sts):
    """{"side": {w}, "island": {w}}: every platform width the kit stations need (the station kit's generator makes a
    piece per width, `blender/tools/build_station_blends.py`)."""
    out = {"side": set(), "island": set()}
    for st in sts.values():
        if not st.kit:
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


def reserve_rises(path=RESERVE):
    """{station name: {side: rise}} -- how far each open-air door's sill (the platform top) stands over its street, as
    the rail reserve measured it (the entry piece's riser count comes from it)."""
    import json
    if not os.path.exists(path):
        return {}
    return {b["id"].partition(":")[2]: b["entry_rise"] for b in json.load(open(path))["boxes"]
            if b["id"].startswith("station:") and "entry_rise" in b}


def reserve_kinds(path=RESERVE):
    import json
    if not os.path.exists(path):
        return {}
    return {b["id"].partition(":")[2]: b["entry_kind"] for b in json.load(open(path))["boxes"]
            if b["id"].startswith("station:") and "entry_kind" in b}


def reserve_entrances(path=RESERVE):
    """{station name: ('left' | 'right', door step)} -- the ground hubs' entrance sides the rail reserve chose."""
    import json
    if not os.path.exists(path):
        return {}
    return {b["id"].partition(":")[2]: (b["entrance"], b.get("door_step", 0.0)) for b in json.load(open(path))["boxes"]
            if b["id"].startswith("station:") and "entrance" in b}


def stations(res, ends=None, entrances=None, rises=None):
    """{name: Station} from `island_rail_layout.analyse()`'s result; `ends` ({name: {side: end}}, the reserve's
    choice) says which end each open-air building stands at."""
    import island_rail_layout as R
    chosen = reserve_ends() if ends is None else ends
    doors = reserve_entrances() if entrances is None else entrances
    risen = reserve_rises() if rises is None else rises
    kinds = reserve_kinds() if rises is None else {}
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
            span = next(((a, b) for a, b, _k in IRR.platform_spans(res, ln) if a - 5.0 <= s2 <= b + 5.0), None)
            if span:
                # the span along THIS station's axis (the lines run parallel through a station: measured by projection)
                ends = [IRR.point_at(L2, v)[:2] for v in span]
                aa = sorted((ex - x) * tx + (ey - y) * ty for ex, ey in ends)
                lanes.append(Lane(ln, round(c, 3), (round(aa[0], 2), round(aa[1], 2))))
            else:
                # a line passing without stopping: its end nearest the station is a branch end (the turnout's side)
                ends = [(L2["pts"][0], 0), (L2["pts"][-1], -1)]
                (ex, ey), _ = min(ends, key=lambda e: math.hypot(e[0][0] - x, e[0][1] - y))
                branches.append((ln, ((ex - x) * tx + (ey - y) * ty, round(c, 3))))
        z = sd.get("z", 0.0)
        gi = min(range(len(L["cum"])), key=lambda k: abs(L["cum"][k] - sd["s"]))
        lift = (z - 0.16) - L["ground"][gi] if "ground" in L else 0.0
        out[name] = Station(name, sd["kind"], x, y, tx, ty, z - 0.16, sd["platform_m"],
                            elevated=z > 4.0, lanes=lanes, branches=branches,
                            building_end=dict(chosen.get(name, {})), entrance=doors.get(name, ("", 0.0))[0],
                            door_step=doors.get(name, ("", 0.0))[1], lift=round(lift, 3),
                            entry_rise=dict(risen.get(name, {})), entry_kind=dict(kinds.get(name, {})))
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
    st3 = Station("Frt", "standard", 0, 0, 1, 0, 0, 90.0, False, [Lane("L", 0.0)], branches=[("F", (50.0, 35.0))])
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
    # THE LARGE HUBS (step 6b): every entrance is roller-shutter bays; a large hub's is six of them in ~11.8 m, inside
    # its annex's street wall and clear of the machines; its shop rows stand beside the platforms, out of every gauge;
    # a standard station squeezed onto the hub form is not large
    bays = shutter_bays(*ANNEX_DOOR_LARGE, LARGE_BAYS)
    assert len(bays) == 6 and all(abs((b1 - b0) - LARGE_BAY_W) < 1e-9 for b0, b1 in bays), bays
    assert abs(bays[-1][1] - ANNEX_DOOR_LARGE[1]) < 1e-9 and ANNEX_DOOR_LARGE[1] <= CAP_LEN / 2 - 0.3 + 1e-9
    assert all(abs((b1 - b0) - (DOOR_W - SHUTTER_POST) / 2) < 1e-9 for b0, b1 in shutter_bays(0.0, DOOR_W, DOOR_BAYS))
    st6.entrance = "left"
    assert is_large(st6) and annex_span(st6)[1] == CAP_LEN / 2 + ANNEX_STORE and check(st6) == [], check(st6)
    shops = [e for e in hub_elements(st6) if e.kind == "store"]
    assert len(shops) == 1 and shops[0].a0 >= CAP_LEN / 2 - 1e-9, shops
    assert annex_span(st6)[1] <= st6.length / 2, "the store reaches past the platform"
    assert store_door_w(5.0) == STORE_DOOR_W2 and store_door_w(3.0) == STORE_DOOR_W1
    assert not is_large(Station("Waterpark", "standard", 0, 0, 1, 0, 0, 90.0, False, [Lane("L", 0.0)]))
    # control: a shop row pulled over the platform stands in the gauge
    els = hub_elements(st6)
    sh = next(e for e in els if e.kind == "store")
    sh.c0 -= 12.0
    assert any("store" in f and "gauge" in f for f in check(st6, els)), check(st6, els)
    st6.entrance = "left"
    # every platform is laid its whole length on both sides (a riser count once shadowed the module count, and the
    # second platform came out 8 modules long)
    st_oa = Station("OA", "standard", 0, 0, 1, 0, 0, 90.0, False, [Lane("L", 0.0)])
    st_oa.building_end = {"left": 1, "right": 1}
    real = globals()["_piece_props"]
    globals()["_piece_props"] = lambda ref, a, c, h, yaw: [{"piece": ref, "at": [a, -c]}]
    try:
        plats = [p_ for p_ in props(st_oa) if p_["piece"].startswith("OA_Platform_")]
    finally:
        globals()["_piece_props"] = real
    assert len(plats) == 2 * 18, len(plats)
    # the elevated hub: one lane on the viaduct, its contract kept; the stair fits its piece and reaches the platform
    import island_rail_layout as R
    assert abs(EH_LIFT - (R.ELEVATED_Z - 0.16)) < 1e-9, "EH_LIFT is not the rail plan's elevated bed"
    st8 = Station("Elev", "standard", 0, 0, 1, 0, EH_LIFT, 90.0, True, [Lane("M", 0.0)], lift=EH_LIFT)
    assert st8.form == "elevated_hub" and st8.kit
    assert check(st8) == [], check(st8)
    steps, x_top = eh_stairs()
    rises = [b[1] - a[1] for a, b in zip([(0, -EH_LIFT)] + steps, steps + [(x_top, PLATFORM_H)])]
    assert max(rises) <= STAIR_RISE + 1e-9 and abs(sum(rises) - (EH_LIFT + PLATFORM_H)) < 1e-9, rises
    assert x_top > -EH_STAIR_LEN / 2 + 1.0, x_top
    # the platform edge stands outside the train's gauge (since 2026-09-29 the real train's: 3.0 m, so 5 cm); the gap to
    # the car itself (0.11 m at the platform's top) is probe_train_fit.gd's
    assert eh_band(st8)[0] - GAUGE_HALF - TRACK_HALF > 0.0
    mods, sc = eh_modules(st8)
    vals = list(mods.values())
    assert vals.count("gate_lo") == 1 and vals.count("gate_hi") == 1 and vals.count("entrance") == 2, mods
    # the paid box holds the stair and the lift, roughly centred, and the four entrances are outside it, in the wings
    ba0, ba1 = eh_box(st8)
    assert ba0 < sc - EH_STAIR_LEN / 2 - EH_LIFT_MODULE and sc + EH_STAIR_LEN / 2 < ba1, (ba0, ba1, sc)
    assert abs((ba0 + ba1) / 2) <= 5.0, (ba0, ba1)
    ents = eh_entrances(st8)
    assert len(ents) == 4 and all(abs(c) > eh_outer(st8) and not ba0 <= a <= ba1 for a, c, _h in ents), ents
    # each entrance's three modules stay outside the paid box, and every other wing module is a shop or machines
    for a, r in mods.items():
        if r.startswith("entrance"):
            assert a + MODULE / 2 <= ba0 - MODULE / 2 + 1e-9 or a - MODULE / 2 >= ba1 + MODULE / 2 - 1e-9, (a, r)
    for n60 in (65.0, 75.0, 90.0, 120.0):
        eh_modules(Station("L", "standard", 0, 0, 1, 0, EH_LIFT, n60, True, [Lane("M", 0.0)], lift=EH_LIFT))
    # control: a stair band's slab pulled in over the track stands in the gauge
    els = eh_elements(st8)
    wl = next(e for e in els if e.kind == "band" and e.tag == "left")
    wl.c0 = 3.0
    assert any("gauge" in f for f in check(st8, els))
    # the LIFTS (user, 2026-09-27): beside each stair, LIFT_GAP beyond its TOP end so the doors never open into the
    # stair's queue, inside the paid area, doors wide enough for a wheelchair
    mods, sc = eh_modules(st8)
    gate_a = next(a for a, r in mods.items() if r == "gate_hi")
    lifts = [e for e in eh_elements(st8) if e.kind == "lift"]
    assert len(lifts) == 2, lifts
    stair_top_a = sc + x_top
    for e in lifts:
        assert abs((stair_top_a - e.a1) - LIFT_GAP) < 1e-6, (stair_top_a, e.a1)
        assert ba0 < e.a0 and e.a1 < gate_a and abs((e.a1 - e.a0) - EH_SW) < 1e-9 and abs((e.c1 - e.c0) - EH_SW) < 1e-9
    n, _r = stair_steps(AF - PLATFORM_H)
    for sw in (CAP_SW_SIDE, CAP_SW_ISLAND):
        x0, x1 = hub_lift(sw)
        assert abs((CAP_STAIR_X - (n - 1) * STAIR_RUN) - x1 - LIFT_GAP) < 1e-9 and x0 > -CAP_LEN / 2 + 1.0
        assert lift_door_w(sw - 2 * LIFT_WALL_T) >= 0.8, sw
    st6.entrance = "left"
    assert sum(1 for e in hub_elements(st6) if e.kind == "lift") == len(platforms(st6))
    assert check(st6) == [], check(st6)
    # CENTRAL's shape (PLAN.md step 6): three lanes 14 m apart over a 300 m F1 -- two side platforms outside the
    # outer lanes, two ISLAND platforms between them with their stair and lift in the gap between the decks; one paid
    # box holds every stair and lift; entrances beside the box as well as near the ends
    st9 = Station("C", "hub", 0, 0, 1, 0, EH_LIFT, 300.0, True, [Lane("A", -14.0), Lane("B", 0.0), Lane("H", 14.0)],
                  lift=EH_LIFT)
    assert st9.kit and st9.form == "elevated_hub"
    assert check(st9) == [], check(st9)
    isl = eh_islands(st9)
    assert len(isl) == 2 and all(abs((c1 - c0) - 6.9) < 1e-9 for c0, c1, _m in isl), isl
    assert eh_core(st9) == "345_3x14", eh_core(st9)
    els = eh_elements(st9)
    ba0, ba1 = eh_box(st9)
    lifts = [e for e in els if e.kind == "lift"]
    assert len(lifts) == 4 and all(ba0 < e.a0 and e.a1 < ba1 for e in lifts), lifts
    for c0, c1, cm in isl:             # the stairwell and the lift stand between the decks, never over a track
        assert cm - EH_ISLAND_SW / 2 > c0 - PLATFORM_EDGE + (EH_DECK_HALF - TRACK_HALF) - 1e-9
        assert (cm - EH_ISLAND_SW / 2) - c0 >= 1.5 and c1 - (cm + EH_ISLAND_SW / 2) >= 1.5   # 1.5 m beside the well
    ents = eh_entrances(st9)
    assert len(ents) == 8 and all(not ba0 <= a <= ba1 for a, _c, _h in ents), ents
    assert min(abs(a - ba0) for a, _c, _h in ents) <= 10.0 + 1e-9, "no entrance beside the paid box"
    # the AMENITIES (step 6b): a restroom block inside the paid box and one outside it, both under the middle lane
    # between its deck's column rows (faces at +-4.1 m) and clear of every stair and lift; neither widens the building
    for stx in (st8, st9):
        els = eh_elements(stx)
        ba0, ba1 = eh_box(stx)
        wcs = {e.tag: e for e in els if e.kind == "restroom"}
        assert set(wcs) == {"paid", "unpaid"}, wcs
        assert ba0 + MODULE / 2 < wcs["paid"].a0 and wcs["paid"].a1 < ba1 - MODULE / 2, (ba0, ba1, wcs["paid"])
        assert wcs["unpaid"].a1 < ba0 - MODULE / 2 and wcs["unpaid"].a0 > -stx.length / 2, wcs["unpaid"]
        mc = sorted(ln.c for ln in stx.lanes)[len(stx.lanes) // 2]
        for e in wcs.values():
            assert mc - (EH_DECK_HALF - 0.9) < e.c0 and e.c1 < mc + (EH_DECK_HALF - 0.9), e
            for o in els:
                if o.kind in ("lift", "band", "wall", "wing", "fare", "floor", "ceiling") and o is not e:
                    assert o.kind in ("floor", "ceiling") or not e.overlaps(o), (e, o)
    assert eh_outer(st8) == eh_band(st8)[3] + EH_WING
    # control: a lane whose track stops at the station's centre (the old Blue line) is refused
    st9.lanes[0].cover = (-150.0, 0.0)
    assert any("covers only" in f for f in check(st9)), check(st9)
    st9.lanes[0].cover = None
    # control: lanes too close for a stair between the decks are refused
    try:
        eh_islands(Station("X", "hub", 0, 0, 1, 0, EH_LIFT, 300.0, True, [Lane("A", 0.0), Lane("B", 12.0)]))
        raise AssertionError("an island with no room for its stair was accepted")
    except SystemExit:
        pass
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
        done = [layout(st) for st in sts.values() if (not only or st.name in only) and st.kit]
        json.dump({"buildings": done}, open(a.write, "w"), indent=1)
        print("station_layout: %d station(s) -> %s" % (len(done), a.write))
    for st in sts.values():
        lanes = ", ".join("%s c%+.1f" % (ln.line, ln.c) for ln in st.lanes)
        br = ", ".join("%s end a%+.0f c%+.0f" % (b[0], b[1][0], b[1][1]) for b in st.branches)
        print("%-18s %-12s %-9s %5.0f m  bed %5.2f  lanes [%s]%s" % (st.name, st.form, st.kind, st.length, st.bed,
                                                                   lanes, ("  branches [%s]" % br) if br else ""))
        if st.kit:
            for f in check(st):
                print("   FINDING " + f)
                bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
