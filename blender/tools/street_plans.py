"""Street structures built like the mission buildings (build_interior_blends.py -> kits/interiors/<Id>.blend, one
.blend per piece, the artist's after that): the 横断歩道橋 (pedestrian footbridge; user, 2026-10-10: "Japan equips
air bridges on some intersections ... a way for peds to pass, and more tightness on the larger multi-lane streets").

THE MEASUREMENTS are Japan's 立体横断施設技術基準 (the footbridge standard), stated where used:
* clearance under the girder 4.7 m (the 4.5 m 建築限界 of a road + 0.2 m for resurfacing);
* a walkway at least 1.5 m clear, 2.0 m where two wheelchairs / a pram pass -- 2.0 here;
* stairs at 50 %: riser 0.15 m, tread 0.30 m, at least 1.5 m wide, a landing at least 1.2 m deep every 3 m of rise;
* a railing 1.1 m over the walkway, a solid lower panel over the carriageway (nothing dropped onto traffic).
Steel plate girders painted one pale colour (MI_BridgePaint), a pier on each footway behind the kerb and, on a span
over a median, one in the median; non-slip yellow nosings.

Frame: metres, Z up, the origin on the ROAD SURFACE at the road's centreline; the road runs along Y and the deck
spans it along X. The junction is toward -Y, both stairs come down toward +Y (away from it), each on the KERB half of
its footway so the building half stays open. tools/island_footbridges.py places the piece from the lane records.
"""
import interior_kit as IK
from interior_plans_jp import _hexa

CLEAR = 4.7            # under the girder (4.5 m 建築限界 + 0.2)
GIRDER = 0.8           # plate girder depth
DECK = CLEAR + GIRDER  # the walkway's top
WALK = 2.0             # clear walkway width
RISER, TREAD = 0.15, 0.30
STAIR_W = 1.6          # clear stair width (>= 1.5)
LANDING = 1.5          # the mid landing's depth (>= 1.2)
RAIL = 1.1
FOOTWAY_Z = 0.15       # the footway's top over the carriageway (the road kit's kerb)
KERB_BACK = 0.45       # the stair's and the pier's clear distance behind the kerb face
PAINT, TREAD_MAT, NOSE = "MI_BridgePaint", "MI_AsphaltLot", "MI_PaintYellow"


def _flight(b, x0, x1, y0, z0, n, r, toe=0):
    """n risers of r climbing toward -Y from y0 (the first riser's face) at floor z0; treads, yellow nosings, a solid
    side panel each side whose top is the handrail, and the ramp collider along the nosings (interior_kit)."""
    for i in range(n):
        top = z0 + (i + 1) * r
        hi = y0 - i * TREAD
        lo = hi - TREAD
        b.box("Stairs", (x0, lo, top - r - 0.14), (x1, hi, top), TREAD_MAT)
        b.box("Stairs", (x0, hi - 0.05, top - 0.02), (x1, hi, top + 0.005), NOSE)
    ya, yb = y0, y0 - n * TREAD                     # the flight's plan, bottom to top
    za, zb = z0, z0 + n * r
    for xa, xb in ((x0 - 0.06, x0), (x1, x1 + 0.06)):
        lo = [(xa, yb, zb - 0.45), (xb, yb, zb - 0.45), (xb, ya, za - 0.3), (xa, ya, za - 0.3)]
        hi = [(xa, yb, zb + RAIL), (xb, yb, zb + RAIL), (xb, ya, za + RAIL), (xa, ya, za + RAIL)]
        _hexa(b, "Stairs", lo + hi, PAINT)
    # `toe` more treads of the same slope below the floor: the foot stands on a footway whose kerb height the piece
    # does not own, and a ramp that began exactly at 0.15 m was a 0.15 m wall wherever the paving is lower
    lo_y, lo_z = y0 + (1 + toe) * TREAD, z0 - toe * r
    b.stair_ramp((x0, lo_y, lo_z), (x0, y0 - (n - 1) * TREAD, zb), (x1, lo_y, lo_z), (x1, y0 - (n - 1) * TREAD, zb))
    return yb


def _pier(b, x, y, z_top, w=0.6, head=None):
    b.box("Structure", (x - w / 2, y - w / 2, 0.0), (x + w / 2, y + w / 2, z_top), PAINT)
    b.box("Structure", (x - w / 2 - 0.1, y - w / 2 - 0.1, 0.0), (x + w / 2 + 0.1, y + w / 2 + 0.1, FOOTWAY_Z + 0.35),
          "MI_ConcreteSmooth")                                   # the concrete footing a car meets first
    if head:
        b.box("Structure", (x - 0.45, -head, z_top - 0.35), (x + 0.45, head, z_top), PAINT)


def _rail(b, x0, x1, y, z):
    """The deck railing along X at y: a solid lower panel, posts and a top rail, 1.1 m in all."""
    if x1 - x0 < 0.05:
        return
    b.box("Facade", (x0, y - 0.025, z), (x1, y + 0.025, z + 0.7), PAINT)
    b.box("Facade", (x0, y - 0.04, z + RAIL - 0.07), (x1, y + 0.04, z + RAIL), PAINT)
    n = max(1, int(round((x1 - x0) / 2.0)))
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / n
        b.box("Facade", (x - 0.03, y - 0.03, z + 0.7), (x + 0.03, y + 0.03, z + RAIL - 0.07), PAINT)


def footbridge(b, kerb_half, median_pier):
    """One span over a road whose kerbs are `kerb_half` either side of the centreline."""
    K = kerb_half
    half = WALK / 2 + 0.1                       # the walkway + the girder flange each side
    end = K + KERB_BACK + STAIR_W + 0.15        # the deck's end: over the stair's outer panel
    sx0, sx1 = K + KERB_BACK, K + KERB_BACK + STAIR_W
    # the two plate girders, the walkway between them, the name plate both ways
    for y0, y1 in ((-half, -half + 0.2), (half - 0.2, half)):
        b.box("Structure", (-end, y0, CLEAR), (end, y1, DECK), PAINT)
    b.box("Structure", (-end, -half + 0.2, DECK - 0.2), (end, half - 0.2, DECK), TREAD_MAT)
    for x in [-end + 0.1] + [-end + (2 * end) * i / 8 for i in range(1, 8)] + [end - 0.1]:   # cross beams under the slab
        b.box("Structure", (x - 0.08, -half + 0.2, CLEAR + 0.25), (x + 0.08, half - 0.2, DECK - 0.2), PAINT)
    for sgn in (-1, 1):
        y = sgn * (half + 0.03)
        b.box("Facade", (-1.6, min(y, y - sgn * 0.03), CLEAR + 0.17), (1.6, max(y, y - sgn * 0.03), CLEAR + 0.63), "MI_PaintWhite")
        b.mark("name_plate", 0.0, y, CLEAR + 0.4, 0.0 if sgn < 0 else 180.0, w=3.2, h=0.46)
    # railings: the junction side whole; the far side open at the two stair heads; the two ends closed
    _rail(b, -end, end, -half + 0.1, DECK)
    _rail(b, -sx0, sx0, half - 0.1, DECK)
    for s in (-1, 1):
        _rail(b, min(s * sx1, s * end), max(s * sx1, s * end), half - 0.1, DECK)
        x = s * (end - 0.05)
        b.box("Facade", (x - 0.025, -half + 0.1, DECK), (x + 0.025, half - 0.1, DECK + 0.7), PAINT)
        b.box("Facade", (x - 0.04, -half + 0.1, DECK + RAIL - 0.07), (x + 0.04, half - 0.1, DECK + RAIL), PAINT)
    # piers: one behind each kerb under the girders, one in the median when the road has it
    for s in (-1, 1):
        _pier(b, s * (K + KERB_BACK + 0.3), 0.0, CLEAR, head=half)
    if median_pier:
        _pier(b, 0.0, 0.0, CLEAR, head=half)
    # the stairs: two flights of equal rise with a landing between (a landing every <= 3 m of rise)
    rise = DECK - FOOTWAY_Z
    n = int(round(rise / RISER))
    n += n % 2
    r = rise / n
    k = n // 2
    zm = FOOTWAY_Z + k * r
    y_top = half                                 # the deck's far edge: the upper flight's top riser
    y_mid_hi = y_top + k * TREAD                 # the landing's deck-side edge
    y_mid_lo = y_mid_hi + LANDING
    y_foot = y_mid_lo + k * TREAD
    for s in (-1, 1):
        x0, x1 = (sx0, sx1) if s > 0 else (-sx1, -sx0)
        _flight(b, x0, x1, y_foot, FOOTWAY_Z, k, r, toe=1)
        b.box("Stairs", (x0, y_mid_hi, zm - 0.2), (x1, y_mid_lo, zm), TREAD_MAT)
        for xa, xb in ((x0 - 0.06, x0), (x1, x1 + 0.06)):
            b.box("Stairs", (xa, y_mid_hi, zm - 0.45), (xb, y_mid_lo, zm + RAIL), PAINT)
        _flight(b, x0, x1, y_mid_hi, zm, k, r)
        _pier(b, (x0 + x1) / 2, (y_mid_hi + y_mid_lo) / 2, zm - 0.2, w=0.4)
        # where a walker steps on and off (the crowd and the navmesh read these)
        b.mark("footbridge_foot", (x0 + x1) / 2, y_foot + 1.0, FOOTWAY_Z, 0.0, side=float(s))
    return {"note": "横断歩道橋 over a road %.1f m kerb to kerb: deck %.2f m up (%.1f m clear under the girder), walkway "
                    "%.1f m, stairs %d risers of %.3f m on %.2f m treads with a %.1f m landing. Remodel freely INSIDE "
                    "this envelope: the piers' plan, the stair foot and the clearance are what the placement relies on."
                    % (2 * K, DECK, CLEAR, WALK, n, r, TREAD, LANDING),
            "stair_foot_y": y_foot, "end": end}


# kerb half-widths are MEASURED from the island's junction arms (tools/island_footbridges.py --list): every 3+3 arm
# is 15.25 m from the centreline to the kerb (30.5 m kerb to kerb, a 2.5 m median); the 2+2 arms with a median are
# 11.25 or 11.5 m (99 of 142; the piece is drawn for 11.35 so its piers stand 0.3-0.55 m behind either kerb)
PLANS = {"Footbridge30": lambda b: footbridge(b, 15.25, True),
         "Footbridge23": lambda b: footbridge(b, 11.35, True)}
