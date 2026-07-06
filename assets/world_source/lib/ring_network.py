#!/usr/bin/env python3
"""
ring_network.py -- the C1 Loop / Shuto-Expressway-style RING, built the same way every other
elevated corridor in this codebase is: `road_network.py`'s Corridor/RampCurve primitives
(swept spline decks, `ramp_between()` merges), not one-off hand-placed boxes. PURE PYTHON
(no bpy) for the geometry math; building into Blender objects happens via `assemble.py` calls
from the caller (build_world.py), same division of labour as everywhere else in this pipeline.

Design (see PLAN.md's condensed-Tokyo-landmarks plan, section 4):
  - The ring's 4 legs run along the k=1 / k=4 backbone-arterial grid lines (world_grid.DCELLS
    multiples), enclosing the real-precinct cluster (gx,gy in [1,3]) with a 1-district margin,
    at z=road_network.LAYER_EXPS.
  - Each leg is a `Corridor` (2 lanes/direction), swept as ONE continuous spline
    (`assemble.lay_corridor(..., swept=True)`) -- no tile faceting.
  - The 4 corners are real `ramp_between()` quarter-turns (flat, z0==z1), not hard-angle boxes --
    the SAME primitive used for merge ramps elsewhere, so a corner reads as one continuous curve.
  - A SMALL number of interchange ramps (`INTERCHANGES` below) connect the ring down to the
    ground-level arterial backbone at chosen points near the real-precinct cluster, via
    `ramp_between()` (climbing/descending) + `assemble.lay_curve_road()` -- exactly the same
    primitive pair `road_network.py`'s own self-test proves out (radius=MIN_RAMP_R, turns=1.0
    reliably clears a LAYER_EXPS climb within MAX_GRADE).

This is intentionally the SAME "small parametric solver, not hand-modeled junctions" pattern
`TownGrid`/`intersection_for` already uses for local roads (classify a topology, stamp/derive the
piece) -- extended here to ring-scale interchanges: adding a future 5th/6th interchange means
adding one entry to `INTERCHANGES`, not hand-authoring new geometry.
"""
import math
import road_network as rn
import assemble as asm
import kit_common as kc
import world_grid as wg

RING_K_LO = 1                    # ring legs run along the k=1 backbone arterial line...
RING_K_HI = 4                    # ...to the k=4 line (encloses gx,gy in [1,3] w/ 1-district margin)
RING_LANES = 2                   # lanes per direction on the ring itself
RING_DECK = "SM_Exps_Deck_2L"
RING_PIER = "SM_Exps_Pillar"
CORNER_RADIUS = rn.MIN_RAMP_R + 5.0     # a touch above the minimum for a comfortable ring corner

# (leg, cell_frac, side) -> where an interchange ramp descends to the ground arterial. `leg` is
# 'S'/'N'/'E'/'W' (which ring leg); `cell_frac` is 0..1 along that leg (0 = the RING_K_LO corner);
# `side` picks which lateral side the ramp descends on ('L'/'R', matching ramp_between). Chosen
# near the real-precinct cluster's two busiest edges (Kabukicho/Shibuya on the south, Akihabara/
# Tokyo Tower on the east) -- see PLAN.md section 4.
INTERCHANGES = [
    dict(leg='S', frac=0.5, side='R', tag="C1_IC_South"),   # near Kabukicho/Shibuya
    dict(leg='E', frac=0.5, side='R', tag="C1_IC_East"),    # near Akihabara/Tokyo Tower
]


def _leg_cells(k_lo, k_hi, leg):
    lo, hi = k_lo * wg.DCELLS, k_hi * wg.DCELLS
    if leg == 'S':
        return [(x, lo) for x in range(lo, hi + 1)], 'EW'
    if leg == 'N':
        return [(x, hi) for x in range(lo, hi + 1)], 'EW'
    if leg == 'W':
        return [(lo, y) for y in range(lo, hi + 1)], 'NS'
    if leg == 'E':
        return [(hi, y) for y in range(lo, hi + 1)], 'NS'
    raise ValueError(leg)


def build_ring(coll, mk, grid, z=None):
    """Build the full ring (4 legs + 4 corners + interchange ramps) into `coll` (visual +
    collision) / `mk` (lane markers, via the Corridor/RampCurve route= mechanism already wired
    into assemble.lay_corridor/lay_curve_road). `grid` = the master TownGrid (for pier
    lower-structure avoidance against the backbone arterial cells). Coordinates are in the same
    GRID-SPACE (0..WORLD, corner-origin) every other build_world.py function computes in --
    the caller applies world_grid.to_world() by re-centring this collection's objects the same
    way build_district.recenter() does, AFTER this returns (see build_world.py's call site).
    Returns a stats dict for the caller's summary print."""
    z = rn.LAYER_EXPS if z is None else z
    legs = {leg: _leg_cells(RING_K_LO, RING_K_HI, leg) for leg in ('S', 'N', 'W', 'E')}

    corridors = {}
    for leg, (cells, axis) in legs.items():
        cor = rn.Corridor(cells, z, RING_DECK, RING_PIER,
                          lines=[(-rn.LANE / 2, f"c1_{leg}_a", False, None),
                                 (rn.LANE / 2, f"c1_{leg}_b", True, None)])
        corridors[leg] = cor
        asm.lay_corridor(cor, coll, grid=grid, swept=True, base_lanes=RING_LANES, grip="asphalt")

    # 4 corners: a flat (z0==z1) ramp_between() quarter-turn from one leg's outer-lane end to the
    # next leg's outer-lane start -- one continuous curved corner, not a hard right angle.
    # `_leg_cells` always orders each leg's cell list lo->hi along its axis, which does NOT match
    # a single consistent clockwise travel direction (S/E legs happen to run lo->hi clockwise;
    # N/W legs run clockwise hi->lo, i.e. REVERSED relative to their own cell list) -- so exit/
    # entry index + travel sign is looked up explicitly per leg below, not derived from a generic
    # rule (that was the bug caught reviewing this before running it).
    LEG_EXIT  = {'S': (-1, 1), 'E': (-1, 1), 'N': (0, -1), 'W': (0, -1)}   # (cell_index, travel)
    LEG_ENTRY = {'S': (0, 1),  'E': (0, 1),  'N': (-1, -1), 'W': (-1, -1)}
    corner_specs = [('S', 'E'), ('E', 'N'), ('N', 'W'), ('W', 'S')]
    n_corners = 0
    for (leg_a, leg_b) in corner_specs:
        cor_a, cor_b = corridors[leg_a], corridors[leg_b]
        ia, ta = LEG_EXIT[leg_a]
        ib, tb = LEG_ENTRY[leg_b]
        start = rn.deck_lane_anchor(cor_a, cor_a.cells[ia], 'R', travel=ta, base_lanes=RING_LANES)
        end = rn.deck_lane_anchor(cor_b, cor_b.cells[ib], 'R', travel=tb, base_lanes=RING_LANES)
        rc = rn.ramp_between(start[:2] + (start[3],), end[:2] + (end[3],), z0=z, z1=z,
                             radius=CORNER_RADIUS, side='L', turns=0.0,
                             route=f"c1_corner_{leg_a}{leg_b}", tag=f"C1_Corner_{leg_a}{leg_b}")
        asm.lay_curve_road(rc, coll, grid=grid)
        n_corners += 1

    # interchange ramps: ring outer lane -> ground-level arterial, climbing/descending LAYER_EXPS.
    n_ic = 0
    for spec in INTERCHANGES:
        cor = corridors[spec['leg']]
        idx = max(0, min(len(cor.cells) - 1, round(spec['frac'] * (len(cor.cells) - 1))))
        deck_anchor = rn.deck_lane_anchor(cor, cor.cells[idx], spec['side'], travel=1,
                                          base_lanes=RING_LANES)
        ground_cell = cor.cells[idx]
        ground_gx, ground_gy = ground_cell[0] // wg.DCELLS, ground_cell[1] // wg.DCELLS
        ground_elev = wg.elev_at(ground_gx, ground_gy)
        ground_anchor = rn.ramp_socket(ground_cell, 'S' if spec['leg'] in ('S', 'N') else 'E')
        rc = rn.ramp_between(deck_anchor[:2] + (deck_anchor[3],), ground_anchor,
                             z0=z, z1=ground_elev, radius=rn.MIN_RAMP_R, side=spec['side'],
                             turns=1.0, route=f"lane_{spec['tag']}", tag=spec['tag'])
        asm.lay_curve_road(rc, coll, grid=grid)
        n_ic += 1

    return dict(legs=len(corridors), corners=n_corners, interchanges=n_ic)
