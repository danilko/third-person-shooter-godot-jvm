#!/usr/bin/env python3
"""
build_roads.py -> roads_kit.blend

Granular, game-aligned road kit on a 7 m grid (3.5 m lane). Two authoring paths:

  1. GRANULAR manual pieces  — one lane / shoulder / sidewalk / curb + separate
     raised decoration meshes (lines, crosswalk). Stack lanes on X to widen a
     road (2-lane, 4-lane, highway) and drop decoration on top.
  2. AUTO-TILER intersection tiles — Road_Straight/Corner/Tee/Cross/End_7, each a
     7x7 asphalt tile with its lane markings baked in, consumed by the cell
     classifier in lib/road_network.py.

Plus Road_Ground_7 (fills every non-road cell -> no void), and future-extension
scaffolds for highway / bridge / railroad so the same solver/grid extends later.

All road/grid tiles are CENTRED on origin, asphalt top at z=0, so 90deg rotation
snaps and neighbours abut. Each solid (walk-on / blocking) piece gets a
`<Name>-colonly` box proxy; pure decoration carries none.

RUN: blender --background --python kit/build_roads.py
"""
import bpy, os, sys, math
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import kit_common as kc

COLL = "ROADS"
H = kc.CELL / 2.0          # 3.5  half cell
LH = kc.LANE / 2.0         # 1.75 half lane
AZ0, AZ1 = -0.12, 0.0      # asphalt body (top at ground)
ZM0, ZM1 = 0.0, 0.02       # lane-marking deco (raised just above asphalt)
SZ = 0.15                  # sidewalk top height
CZ = 0.30                  # curb height
GZ0, GZ1 = -0.05, 0.0      # ground fill


def asphalt_full():
    return ((-H, H, -H, H, AZ0, AZ1), "asphalt")


def center_line_y():
    return ((-0.075, 0.075, -H, H, ZM0, ZM1), "line_y")     # yellow centre, along Y


def edge_lines_w():
    return [((-3.35, -3.2, -H, H, ZM0, ZM1), "line_w"),
            ((3.2, 3.35, -H, H, ZM0, ZM1), "line_w")]


def crosswalk(edge):
    """Zebra bars near one edge. edge in {'N','S','E','W'} (N=+Y, E=+X)."""
    bars = []
    for k in range(-3, 4):                      # 7 bars across the carriageway
        c = k * 0.45
        if edge in ("N", "S"):                  # bars run along X, banded in Y
            yb = (H - 0.9) if edge == "N" else (-H)
            bars.append(((c-0.16, c+0.16, yb, yb+0.9, ZM0, ZM1), "line_w"))
        else:                                    # bars run along Y, banded in X
            xb = (H - 0.9) if edge == "E" else (-H)
            bars.append(((xb, xb+0.9, c-0.16, c+0.16, ZM0, ZM1), "line_w"))
    return bars


def build_granular(c):
    """Compose-it-yourself lane / shoulder / sidewalk / curb + separate deco."""
    kc.box("Road_Lane_3p5", -LH, LH, -H, H, AZ0, AZ1, c, "asphalt")          # 1 lane
    kc.box("Road_Shoulder_1p75", -0.875, 0.875, -H, H, AZ0, AZ1, c, "asphalt")  # side strip
    kc.box("Road_Sidewalk_2", -1.0, 1.0, -H, H, 0, SZ, c, "trim")            # raised walk
    kc.box("Road_Curb", -0.075, 0.075, -H, H, 0, CZ, c, "trim")              # kerb edge
    kc.box("Road_Ground_7", -H, H, -H, H, GZ0, GZ1, c, "dirt")               # fills any cell

    # decoration (separate, raised, NO collision)
    kc.combine("Deco_Line_Center", [center_line_y()], c)
    kc.combine("Deco_Line_Edge", [((-0.075, 0.075, -H, H, ZM0, ZM1), "line_w")], c)
    kc.combine("Deco_Line_Dash",
               [((-0.075, 0.075, y, y+0.9, ZM0, ZM1), "line_w") for y in (-3.0, -1.2, 0.6, 2.4)], c)
    kc.combine("Deco_Crosswalk", crosswalk("S"), c)
    kc.combine("Deco_StopBar", [((-H, 0, H-0.6, H-0.2, ZM0, ZM1), "line_w")], c)


def build_intersections(c):
    """7x7 asphalt tiles with markings baked in, for the classifier."""
    a = asphalt_full()
    # Straight: open N/S -> centre line + white edges
    kc.combine("Road_Straight_7", [a, center_line_y()] + edge_lines_w(), c)
    # Corner: open N + E (curve) -> plain asphalt + short edge hints
    kc.combine("Road_Corner_7", [a,
               ((-0.075, 0.075, 0, H, ZM0, ZM1), "line_y"),
               ((0, H, -0.075, 0.075, ZM0, ZM1), "line_y")], c)
    # Tee: open N/S/E (closed W) -> centre line + crosswalk on the closed-side approach
    kc.combine("Road_Tee_7", [a, center_line_y()] + crosswalk("W"), c)
    # Cross: open all -> crosswalks on all four approaches
    kc.combine("Road_Cross_7", [a] + crosswalk("N") + crosswalk("S")
               + crosswalk("E") + crosswalk("W"), c)
    # End / cul-de-sac: open one side (N) -> stop bar across the closed end
    kc.combine("Road_End_7", [a, center_line_y(),
               ((-H, H, -H, -H+0.5, ZM0, ZM1), "line_w")], c)


def build_scramble(c):
    """Road_Scramble: a 2x2-cell (14 m) plaza junction with orthogonal + diagonal
    crosswalks — the Shibuya 'scramble'. One placed piece; pedestrians cross every
    way, vehicles hold. A foundation primitive; the Shibuya district places it later."""
    Q = kc.CELL                              # 7.0  half of the 14 m plaza
    bars = [((-Q, Q, -Q, Q, AZ0, AZ1), "asphalt")]
    # orthogonal zebra crossings just inside each edge (bars across the approach)
    for k in range(-6, 7):
        c0 = k * 0.5
        bars.append(((c0-0.16, c0+0.16, Q-1.0, Q-0.1, ZM0, ZM1), "line_w"))   # N
        bars.append(((c0-0.16, c0+0.16, -Q+0.1, -Q+1.0, ZM0, ZM1), "line_w")) # S
        bars.append(((Q-1.0, Q-0.1, c0-0.16, c0+0.16, ZM0, ZM1), "line_w"))   # E
        bars.append(((-Q+1.0, -Q+0.1, c0-0.16, c0+0.16, ZM0, ZM1), "line_w")) # W
    # two diagonal crossings corner-to-corner (the scramble's signature)
    for t in range(-12, 13):
        d = t * 0.5
        bars.append(((d-0.18, d+0.18, d-0.9, d-0.5, ZM0, ZM1), "line_w"))     # SW->NE
        bars.append(((d-0.18, d+0.18, -d+0.5, -d+0.9, ZM0, ZM1), "line_w"))   # NW->SE
    kc.combine("Road_Scramble", bars, c)


def build_arterial(c):
    """Pieces specific to a wide divided arterial: a raised central median (kerb +
    planting strip, 7 m long on the grid) and a one-way direction arrow."""
    # raised median divider — centred on x=0, full cell long, top above the asphalt
    kc.combine("SM_Road_Median_7", [
        ((-0.45, 0.45, -H, H, 0.0, 0.18), "trim"),               # kerb body
        ((-0.30, 0.30, -H, H, 0.18, 0.24), "leaf"),              # planting strip
    ], c)
    # one-way arrow (raised deco, no collision) — points +Y along the lane
    head = [((-0.50 + 0.18*k, 0.50 - 0.18*k, 0.8 + 0.2*k, 1.0 + 0.2*k, ZM0, ZM1), "line_w")
            for k in range(4)]                                   # stepped triangular head
    kc.combine("Deco_Oneway", [((-0.10, 0.10, -1.6, 0.85, ZM0, ZM1), "line_w")] + head, c)


# ---- JP intersection library (multi-cell, lane-config-aware) ------------------------------
# Modular intersection PIECES keyed by the Japanese road system, so the cell solver can stamp a
# real intersection like a tile (road_network.intersection_for / assemble.lay_intersections):
#   * Int_Cross_Arterial / Int_Tee_Arterial / Int_Corner_Arterial — 3x3 (21 m) signalised
#     junctions: each approach has 2 through lanes + a dedicated left + right turn lane around a
#     raised median, with stop bars, zebra crosswalks and channelizing islands (douryuutou).
#   * Int_Cross_1 / Int_Tee_1 — 1-cell local junctions (1 lane each way + crosswalks/stop bar).
#   * Int_Oneway_Feed — a one-way feeder merge.  * Int_Roundabout (+ _Island) — a circular junction.
#   * Deco_Island / Road_TurnPocket — reusable sub-pieces.  * SM_Road_Grade_7 — a sloped grade tile
#     for the simple overpass (assemble.place_overpass).
HALF3 = 1.5 * kc.CELL          # 10.5  half of a 3x3 arterial-intersection footprint (21 m)


def _rot90(b):
    """Rotate a ((x0,x1,y0,y1,z0,z1), mat) box 90deg CCW about Z: (x,y)->(-y,x)."""
    (x0, x1, y0, y1, z0, z1), m = b
    return ((-y1, -y0, x0, x1, z0, z1), m)


def _rotn(b, steps):
    for _ in range(steps % 4):
        b = _rot90(b)
    return b


def _ring(boxes, steps_list=(0, 1, 2, 3)):
    """Replicate boxes authored on the +Y (N) arm to each orientation (90deg CCW steps ->
    N,W,S,E). Tee = (0,2,3) keeps N,S,E (closed W); corner = (0,3) keeps N,E."""
    out = []
    for s in steps_list:
        out += [_rotn(b, s) for b in boxes]
    return out


def _zebra_arm(y_in, y_out, span, pitch=0.7):
    """Zebra crosswalk bars (along X, banded in Y) for the +Y arm, between y_in..y_out across
    x in [-span, span]."""
    n = int(span / pitch)
    return [((k*pitch - 0.16, k*pitch + 0.16, y_in, y_out, ZM0, ZM1), "line_w")
            for k in range(-n, n + 1)]


def _arterial_arm():
    """Markings for ONE arm (+Y / N) of a 3x3 arterial junction: raised central median, white
    lane lines (2 through + a turn lane per direction), stop bar + zebra crosswalk at the conflict
    zone, and a channelizing island separating the left-turn pocket. _ring replicates it."""
    CORE = kc.CELL * 0.75                       # 5.25  half-extent of the central conflict zone
    out = [((-0.45, 0.45, CORE + 1.4, HALF3, 0.0, 0.18), "trim"),        # median kerb
           ((-0.30, 0.30, CORE + 1.4, HALF3, 0.18, 0.24), "leaf")]       # median planting
    for x in (-7.0, -3.5, 3.5, 7.0):                                     # lane boundary lines
        out.append(((x - 0.075, x + 0.075, CORE + 1.4, HALF3, ZM0, ZM1), "line_w"))
    out.append(((0.6, HALF3, CORE + 0.95, CORE + 1.25, ZM0, ZM1), "line_w"))   # stop bar (one dir)
    out += _zebra_arm(CORE - 0.1, CORE + 0.9, 9.0)                       # crosswalk
    for sgn in (-1, 1):                                                  # corner islands
        out.append(((sgn * 6.6, sgn * 9.4, CORE + 1.6, CORE + 4.4, 0.0, 0.16), "trim"))
    return out


def build_jp_intersections(c):
    a3 = ((-HALF3, HALF3, -HALF3, HALF3, AZ0, AZ1), "asphalt")           # 3x3 asphalt base
    kc.combine("Int_Cross_Arterial", [a3] + _ring(_arterial_arm(), (0, 1, 2, 3)), c)
    kc.combine("Int_Tee_Arterial", [a3] + _ring(_arterial_arm(), (0, 2, 3))
               + [((-HALF3, -HALF3 + 0.3, -HALF3, HALF3, 0.0, 0.2), "trim")], c)   # closed-W kerb
    kc.combine("Int_Corner_Arterial", [a3] + _ring(_arterial_arm(), (0, 3)), c)
    # 1-cell local junctions — richer than the plain Road_* tiles (stop bar hints)
    a1 = asphalt_full()
    kc.combine("Int_Cross_1", [a1] + crosswalk("N") + crosswalk("S") + crosswalk("E")
               + crosswalk("W") + [((0.4, H, H - 1.05, H - 0.8, ZM0, ZM1), "line_w")], c)
    kc.combine("Int_Tee_1", [a1, center_line_y()] + crosswalk("W") + crosswalk("N") + crosswalk("S"), c)
    # one-way feeder merge (1 cell): centre line + a stepped merge arrow
    kc.combine("Int_Oneway_Feed", [a1, ((-0.075, 0.075, -H, H, ZM0, ZM1), "line_w")]
               + [((-0.50 + 0.18*k, 0.50 - 0.18*k, 0.8 + 0.2*k, 1.0 + 0.2*k, ZM0, ZM1), "line_w")
                  for k in range(4)], c)
    # reusable sub-pieces
    kc.combine("Deco_Island", [((-1.4, 1.4, -2.6, 2.6, 0.0, 0.16), "trim"),
               ((-1.0, 1.0, -2.2, 2.2, 0.16, 0.20), "leaf")], c)
    kc.box("Road_TurnPocket", -LH, LH, -H, H, AZ0, AZ1, c, "asphalt")
    # simple-overpass grade tile: a 3.5x7 lane that climbs CELL*8% over its length (assemble.place_overpass)
    kc.wedge("SM_Road_Grade_7", [((-LH, LH, -H, H, 0.0, kc.CELL * 0.08, 0.12), "asphalt")], c)


def _lane_arm(L):
    """Markings for ONE arm (+Y / N) of a 3x3 junction carrying `L` lanes-per-direction (so the
    arm is 2*L lanes wide): raised central median, white lane-boundary lines at ±k*LANE, a stop
    bar + zebra crosswalk at the conflict zone, and (for L>=2) channelizing turn islands. Drive it
    per-arm so an ASYMMETRIC crossing (2-lane major x 1-lane minor) bakes correctly. _rotn places
    it on each open side."""
    CORE = kc.CELL * 0.75                        # 5.25  half-extent of the central conflict zone
    W = L * kc.LANE                              # half carriageway width of this arm (one dir = L lanes)
    out = [((-0.45, 0.45, CORE + 1.4, HALF3, 0.0, 0.18), "trim"),        # median kerb
           ((-0.30, 0.30, CORE + 1.4, HALF3, 0.18, 0.24), "leaf")]       # median planting
    for k in range(1, L + 1):                                            # lane boundary lines both dirs
        for x in (k * kc.LANE, -k * kc.LANE):
            out.append(((x - 0.075, x + 0.075, CORE + 1.4, HALF3, ZM0, ZM1), "line_w"))
    out.append(((0.6, W, CORE + 0.95, CORE + 1.25, ZM0, ZM1), "line_w"))   # stop bar (one dir)
    out += _zebra_arm(CORE - 0.1, CORE + 0.9, W + 1.5)                     # crosswalk across the arm
    if L >= 2:                                                            # channelizing corner islands
        for sgn in (-1, 1):
            out.append(((sgn * (W - 0.4), sgn * (W + 2.8), CORE + 1.6, CORE + 4.4, 0.0, 0.16), "trim"))
    return out


# _rotn steps (CCW, RING=N,W,S,E) that rotate the authored +Y (N) arm onto each side
_ARM_STEPS = {'N': 0, 'W': 1, 'S': 2, 'E': 3}


def build_jp_intersection(name, arms, c):
    """Bake a 3x3 (21 m) JP intersection PIECE from a per-arm lane config `arms`={'N':L,'E':L,
    'S':L,'W':L} (L = lanes-per-direction, 0 = closed side -> solid kerb). Composes `_lane_arm(L)`
    on each open side (rotated), so ONE generator makes the symmetric (equal all four) AND the
    asymmetric (2-lane major x 1-lane minor) crossings the JP set needs. Selected by
    road_network.intersection_for via the cell's arm_config."""
    boxes = [((-HALF3, HALF3, -HALF3, HALF3, AZ0, AZ1), "asphalt")]      # 3x3 asphalt base
    for d, L in arms.items():
        if L <= 0:                                                       # closed side -> kerb
            boxes.append(_rotn(((-HALF3, HALF3, HALF3 - 0.3, HALF3, 0.0, 0.2), "trim"), _ARM_STEPS[d]))
        else:
            boxes += [_rotn(b, _ARM_STEPS[d]) for b in _lane_arm(L)]
    kc.combine(name, boxes, c)


def build_lane_config_intersections(c):
    """The lane-config JP crossing set (keyed by per-arm lane count): a symmetric 2-lane cross and
    the asymmetric 2-lane-major x 1-lane-minor cross (major on E/W as authored; the solver rotates
    it 90 deg when the major axis runs N/S). The all-1-lane cross stays the 1-cell Int_Cross_1."""
    build_jp_intersection("Int_Cross_2", {'N': 2, 'E': 2, 'S': 2, 'W': 2}, c)
    build_jp_intersection("Int_Cross_Major2_Minor1", {'E': 2, 'W': 2, 'N': 1, 'S': 1}, c)


def build_roundabout(c):
    """A circular junction (kanjou-kousaten): a circulating asphalt disc + a raised central
    island, placed concentrically (two modular leaves). Splitter islands = Deco_Island."""
    R = 2.5 * kc.CELL                                  # 17.5  outer radius (a 5x5 footprint)
    kc.cyl("Int_Roundabout", R, AZ0, AZ1, c, "asphalt", seg=32)          # circulating carriageway
    kc.cyl("Int_Roundabout_Island", R - 7.0, 0.0, 0.20, c, "trim", seg=32)   # central island (raised)


def build_future(c):
    """Minimal blockouts proving the 7 m grid extends to highway/bridge/rail."""
    # highway: a lane + jersey barrier
    kc.box("Highway_Lane_3p5", -LH, LH, -H, H, AZ0, AZ1, c, "asphalt")
    kc.combine("Highway_Barrier", [((-0.3, 0.3, -H, H, 0, 0.3), "concrete"),
               ((-0.15, 0.15, -H, H, 0.3, 0.9), "concrete")], c)
    # bridge: deck + side rail + pier
    kc.box("Bridge_Deck_7", -H, H, -H, H, -0.3, 0.0, c, "concrete")
    kc.combine("Bridge_Rail", [((-H, H, H-0.12, H, 0, 1.1), "metal")], c)
    kc.box("Bridge_Pier", -0.6, 0.6, -0.6, 0.6, -6.0, -0.3, c, "concrete")
    # railroad: ballast bed + two rails + a tie
    kc.box("Rail_Bed_7", -2.0, 2.0, -H, H, GZ0, 0.1, c, "dirt")
    kc.combine("Rail_Track_7", [((-0.72, -0.65, -H, H, 0.1, 0.22), "rail"),
               ((0.65, 0.72, -H, H, 0.1, 0.22), "rail")], c)
    kc.box("Rail_Tie", -1.0, 1.0, -0.13, 0.13, 0.05, 0.13, c, "wood")


# pieces that need a collision proxy (walk-on or blocking); deco/markings skip it
SOLID = {
    "Road_Lane_3p5", "Road_Shoulder_1p75", "Road_Sidewalk_2", "Road_Curb",
    "Road_Ground_7", "Road_Straight_7", "Road_Corner_7", "Road_Tee_7",
    "Road_Cross_7", "Road_End_7", "Road_Scramble", "SM_Road_Median_7",
    "Highway_Lane_3p5", "Highway_Barrier",
    "Bridge_Deck_7", "Bridge_Rail", "Bridge_Pier", "Rail_Bed_7",
    # JP intersection library + grade tile (all drivable/blocking surfaces)
    "Int_Cross_Arterial", "Int_Tee_Arterial", "Int_Corner_Arterial",
    "Int_Cross_1", "Int_Tee_1", "Int_Oneway_Feed", "Deco_Island", "Road_TurnPocket",
    "Int_Roundabout", "Int_Roundabout_Island", "SM_Road_Grade_7",
    # lane-config JP crossings (symmetric 2-lane + asymmetric 2-lane major x 1-lane minor)
    "Int_Cross_2", "Int_Cross_Major2_Minor1",
}


def main():
    kc.setup_units()
    kc.reset_scene([COLL])
    c = kc.get_coll(COLL)
    build_granular(c)
    build_intersections(c)
    build_jp_intersections(c)
    build_lane_config_intersections(c)
    build_roundabout(c)
    build_scramble(c)
    build_arterial(c)
    build_future(c)
    # collision proxies
    for name in list(SOLID):
        o = bpy.data.objects.get(name)
        if o:
            kc.colonly(o, c)

    visuals = [o for o in c.objects if not o.name.endswith("-colonly")]
    print("ROADS kit: %d visual pieces, %d -colonly proxies"
          % (len(visuals), len(c.objects) - len(visuals)))
    for o in sorted(c.objects, key=lambda o: o.name):
        bb = o.bound_box
        xs = [p[0] for p in bb]; ys = [p[1] for p in bb]; zs = [p[2] for p in bb]
        print("  %-22s X[%5.2f,%5.2f] Y[%5.2f,%5.2f] Z[%5.2f,%5.2f]"
              % (o.name, min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))

    if bpy.app.background:
        kc.save_blend(ROOT, "roads_kit.blend")


if __name__ == "__main__":
    main()
