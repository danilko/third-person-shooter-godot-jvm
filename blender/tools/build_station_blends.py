"""Build the STATION KIT's Blender files: one .blend per station FORM (PLAN.md "NEXT STEP 2026-09-27").

    blender -b --python-exit-code 1 --python blender/tools/build_station_blends.py -- [--form=open_air]
            [--force=Piece,Piece]

Every station on the island is ONE of three forms (tools/station_layout.py, the one owner of which station is which
and of every number a piece must keep). A form's .blend is `assets/world_source/kits/stations/Station_<Form>.blend`
and it OWNS its pieces, exactly like a building kit's .blend (CLAUDE.md "The kit .blend OWNS the pieces"): after
this has run, an artist edits a piece there and `tools/building_kit/build_stations.sh` exports it.

* Every piece is a collection named after it (`bk_piece_path`, `bk_category` = the form) at a grid spot
  (`instance_offset`, which the export moves back). Piece frame: Z up, X ALONG the track, the TRACK SIDE facing -Y,
  origin at the footprint centre on the piece's own floor (a shed's floor is the platform top).
* What the game reads besides the mesh is EMPTIES in the piece's collection, so it is edited where it is seen:
    - `COL_<n>`  a collision box: an Empty drawn as a CUBE (display size 1) whose location is the box's centre and
                 whose SCALE is the box's half size -- scale it in Blender to change the collider;
    - `GATE_<n>` a ticket-gate lane (world.TicketGate's two flaps are built from it, never modelled): on the floor at
                 the lane's centre, its local +X pointing to the UNPAID (street) side, custom props `w` and `h`.
* A generated piece stores a fingerprint of its meshes, Empties and materials (`st_generated`). A regenerate
  KEEPS a piece an artist has changed and names it; `--force=<Piece>` regenerates that one on purpose. A run that
  kept something it would have changed exits 3, so a pipeline notices.
* A `Preview` collection lays out a whole default station from linked instances of the pieces, for the eye only (the
  export reads piece collections alone).

Materials are the central library's palette (library_palette.py); the station kit's kit.json says
`materials_from: library`, so the game wears `kits/library/materials/MI_*.tres`.
"""
import json
import math
import os
import sys

import bpy
import mathutils

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from library_palette import material          # noqa: E402
from library_procedural import Builder        # noqa: E402

KIT = os.path.join(ROOT, "assets", "world_source", "kits", "stations")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
FORMS = [a.split("=", 1)[1] for a in argv if a.startswith("--form=")] or ["open_air"]
FORCE = {n for a in argv if a.startswith("--force=") for n in a.split("=", 1)[1].split(",") if n}
GRID = 14.0
ROW = 6

# the contract, from the one owner (plain python: tools/station_layout.py imports nothing Blender-side)
import station_layout as SL   # noqa: E402

MODULE = 5.0                    # a platform / shed / fence module, along the track
WIDTHS = sorted({SL.PLATFORM_W["small"], SL.PLATFORM_W["standard"], SL.PLATFORM_W["large"]})


def wname(w):
    return ("%g" % w).replace(".", "")


# ── the pieces of the OPEN-AIR form ─────────────────────────────────────────────────────────────────────────────
class Piece:
    def __init__(self, name, cat):
        self.b = Builder(name, material)
        self.name, self.cat = name, cat
        self.cols = []          # [(centre, half)]
        self.gates = []         # [(pos, w, h)]
        self.note = ""

    def solid(self, lo, hi, mat, collide=True):
        self.b.box(lo, hi, mat)
        if collide:
            self.col(lo, hi)

    def col(self, lo, hi):
        c = [(lo[i] + hi[i]) / 2 for i in range(3)]
        h = [(hi[i] - lo[i]) / 2 for i in range(3)]
        self.cols.append((c, h))


def platform(w, pre="OA", cat="open_air"):
    """A platform module: MODULE long, `w` wide, PLATFORM_H over the bed, the edge (white line, yellow coping face,
    tactile strip 0.8 m in) on the track side (-Y)."""
    p = Piece("%s_Platform_%s" % (pre, wname(w)), cat)
    L, h = MODULE, SL.PLATFORM_H
    y0, y1 = -w / 2, w / 2
    p.solid((-L / 2, y0, 0), (L / 2, y1, h), "MI_ConcreteSmooth")
    p.b.box((-L / 2, y0, h), (L / 2, y0 + 0.08, h + 0.004), "MI_PaintWhite")
    p.b.box((-L / 2, y0 + 0.8, h), (L / 2, y0 + 1.1, h + 0.006), "MI_Tactile")
    p.b.box((-L / 2, y0, h - 0.12), (L / 2, y0 + 0.02, h), "MI_PaintYellow")
    p.note = ("A platform module. The TRACK EDGE is the -Y face and must stay exactly there: the layout puts it "
              "%.2f m from the track centre (station_layout.PLATFORM_EDGE) and the train's gauge is 1.35 m. Top "
              "%.2f m over the bed. Length %.1f m tiles along X." % (SL.PLATFORM_EDGE, h, L))
    return p


def shed(w, pre="OA", cat="open_air"):
    """A platform shed module (上屋): a roof SHED_CLEAR over the platform top on one row of columns in the back half,
    so the edge side is clear. Floor (origin) = the platform top."""
    p = Piece("%s_Shed_%s" % (pre, wname(w)), cat)
    L = MODULE
    z0 = SL.SHED_CLEAR
    yc = w / 2 - min(1.0, w / 3)
    p.solid((-0.14, yc - 0.14, 0), (0.14, yc + 0.14, z0), "MI_PaintedMetal")
    p.b.box((-L / 2, -w / 2 + 0.2, z0), (L / 2, w / 2, z0 + SL.SHED_T), "MI_Corrugated")
    p.b.box((-L / 2, -w / 2 + 0.2, z0 - 0.08), (L / 2, -w / 2 + 0.28, z0 + SL.SHED_T), "MI_PaintedMetal")
    p.b.box((-L / 2, yc - 0.6, z0 - 0.3), (L / 2, yc + 0.6, z0), "MI_PaintedMetal")    # the beam on the columns
    p.b.box((-1.0, -w / 2 + 0.8, z0 - 0.05), (1.0, -w / 2 + 1.0, z0), "MI_Light")
    p.note = "A shed module on the platform. Keep the roof inside the platform's width (the gauge is beside it)."
    return p


def fence(pre="OA", cat="open_air"):
    """The back fence (駅の柵) along a platform's outer edge: MODULE long, FENCE_H tall, centred on y 0."""
    p = Piece("%s_Fence" % pre, cat)
    L, H, t = MODULE, SL.FENCE_H, SL.FENCE_T
    for x in (-L / 2 + 0.04, 0.0):
        p.b.box((x - 0.04, -0.04, 0), (x + 0.04, 0.04, H), "MI_PaintedMetal")
    for z in (0.1, H / 2, H - 0.05):
        p.b.box((-L / 2, -0.025, z - 0.025), (L / 2, 0.025, z + 0.025), "MI_PaintedMetal")
    for i in range(int(L / 0.25)):
        x = -L / 2 + 0.125 + i * 0.25
        p.b.box((x - 0.008, -0.008, 0.1), (x + 0.008, 0.008, H - 0.05), "MI_PaintedMetal")
    p.col((-L / 2, -t / 2, 0), (L / 2, t / 2, H))
    p.note = "The platform's back fence. Its collider is the whole panel: nobody climbs off the platform here."
    return p


def end_fence(w, name=None, cat="open_air"):
    p = Piece(name or "OA_EndFence_%s" % wname(w), cat)
    H, t = SL.FENCE_H, SL.FENCE_T
    for y in (-w / 2 + 0.04, w / 2 - 0.04):
        p.b.box((-0.04, y - 0.04, 0), (0.04, y + 0.04, H), "MI_PaintedMetal")
    for z in (0.1, H / 2, H - 0.05):
        p.b.box((-0.025, -w / 2, z - 0.025), (0.025, w / 2, z + 0.025), "MI_PaintedMetal")
    for i in range(int(w / 0.25)):
        y = -w / 2 + 0.125 + i * 0.25
        p.b.box((-0.008, y - 0.008, 0.1), (0.008, y + 0.008, H - 0.05), "MI_PaintedMetal")
    p.col((-t / 2, -w / 2, 0), (t / 2, w / 2, H))
    p.note = "The fence across a platform's far end (ホーム端の柵): the end without a building."
    return p


def building(w, hand):
    """An open-air station's END BUILDING, in line with its platform (the sketch's 'station' box): the platform comes
    in through the -X face at platform level; the street entrance is the +X face, at street level. Inside, from the
    street: the unpaid hall, the fare line (gate cabinets with GATE lanes between them, a railing across the rest), a
    flight of steps up to the platform level, and the paid landing the platform continues into.
    `hand` 'L' has the track on -Y (the platform on the LEFT of the line, seen along +a); 'R' is its mirror."""
    p = Piece("OA_Building_%s_%s" % (wname(w), hand), "open_air")
    L, D, H = SL.BUILDING_LEN, w + SL.BUILDING_OUT, SL.BUILDING_H
    hp, t = SL.PLATFORM_H, 0.2
    y0, y1 = -D / 2, D / 2                      # y0 = the track side (the platform edge line)
    yp = y0 + w                                 # the platform's outer edge
    x0, x1 = -L / 2, L / 2
    land = x0 + 2.9                             # the paid landing's end (platform level)
    steps = 7
    rise, run = hp / steps, 0.30
    stair0 = land + 0.0
    gate_x = stair0 + steps * run + 0.8
    # floor slabs: the street-level floor, and the paid landing at platform level
    p.solid((x0, y0, -0.2), (x1, y1, 0), "MI_Terrazzo")
    p.solid((x0, y0, 0), (land, y1 - t, hp), "MI_ConcreteSmooth")
    for k in range(steps - 1):
        # each step's box reaches back to the landing: a solid stair, no seam between two treads for a ray (or a
        # foot) to fall through, and nothing hollow under it
        p.solid((stair0, y0 + t, 0), (stair0 + (k + 1) * run, y1 - t, hp - (k + 1) * rise), "MI_ConcreteSmooth")
    # walls: track side (-Y) full height, the far side (+Y), the -X face beyond the platform, the street face (+X)
    # with a 3 m entrance, and a header over the platform opening
    p.solid((x0, y0, 0), (x1, y0 + t, H), "MI_Plaster")
    p.solid((x0, y1 - t, 0), (x1, y1, H), "MI_Plaster")
    p.solid((x0, yp, 0), (x0 + t, y1, H), "MI_Plaster")
    p.solid((x0, y0, hp + 2.6), (x0 + t, yp, H), "MI_Plaster")
    ent = 3.0
    ymid = (y0 + y1) / 2
    p.solid((x1 - t, y0, 0), (x1, ymid - ent / 2, H), "MI_Plaster")
    p.solid((x1 - t, ymid + ent / 2, 0), (x1, y1, H), "MI_Plaster")
    p.solid((x1 - t, ymid - ent / 2, 2.6), (x1, ymid + ent / 2, H), "MI_Plaster")
    p.solid((x0, y0, H), (x1, y1, H + 0.2), "MI_ConcreteSmooth")
    p.b.box((x1, ymid - 2.2, 2.7), (x1 + 0.08, ymid + 2.2, 3.3), "MI_Sign")               # the station sign
    # the fare line: cabinets 0.25 wide, lanes GATE_W between the middle ones, a railing to the walls
    yc = (y0 + t + y1 - t) / 2
    lane = SL.GATE_W
    cab = 0.25
    centres = [yc - (lane + cab) / 2, yc + (lane + cab) / 2]
    cabs = [yc - lane - cab, yc, yc + lane + cab]
    for cy in cabs:
        p.solid((gate_x - 0.6, cy - cab / 2, 0), (gate_x + 0.6, cy + cab / 2, 1.0), "MI_PlasticWhite")
    lo_edge, hi_edge = cabs[0] - cab / 2, cabs[-1] + cab / 2
    p.solid((gate_x - 0.03, y0 + t, 0), (gate_x + 0.03, lo_edge, 1.1), "MI_PaintedMetal")
    p.solid((gate_x - 0.03, hi_edge, 0), (gate_x + 0.03, y1 - t, 1.1), "MI_PaintedMetal")
    for cy in centres:
        p.gates.append(((gate_x, cy, 0.0), lane, 1.0))
    # the ticket machines on the unpaid side, against the far wall
    for k in range(2):
        xm = x1 - 1.2 - k * 0.8
        p.solid((xm - 0.3, y1 - t - 0.6, 0), (xm + 0.3, y1 - t, 1.8), "MI_PlasticDark")
    if hand == "R":
        mirror_y(p)
    p.note = ("An open-air station's end building (hand %s). The -X face is where the platform comes in at "
              "platform level; the +X face is the street entrance. The track-side wall stands ON the platform edge "
              "line (the gauge is 0.2 m beyond it) -- never move it toward the track. The GATE_ Empties are the "
              "ticket-gate lanes: keep one between each pair of cabinets. The other hand (_L/_R) is a mirror: "
              "make the same change there." % hand)
    return p


def mirror_y(p):
    """Mirror a piece across y = 0 (the other hand), fixing the face winding the mirror turns inside out."""
    import bmesh
    for v in p.b.bm.verts:
        v.co.y = -v.co.y
    bmesh.ops.reverse_faces(p.b.bm, faces=list(p.b.bm.faces))
    p.cols = [((c[0], -c[1], c[2]), h) for c, h in p.cols]
    p.gates = [((q[0], -q[1], q[2]), w_, h_) for q, w_, h_ in p.gates]


def open_air_pieces():
    out = [fence()]
    for w in WIDTHS:
        out += [platform(w), shed(w), end_fence(w), building(w, "L"), building(w, "R")]
    return out


# ── the pieces of the GROUND HUB (橋上駅) ────────────────────────────────────────────────────────────────────────────
# Every cap piece's origin is at BED level (the track's own height) at the centre of what it spans across; X along the
# track, CAP_LEN long; the airbridge concourse floor's top at AF.
CAP_SW_SIDE = 2.2               # a side platform's stair down from the concourse, against the cap wall
CAP_SW_ISLAND = 3.0             # an island platform's stair, on its centre line
RAIL_H = 1.1                    # a railing's height


def stair(p, x_top, x_bot, y0, y1, z0, z1, mat="MI_ConcreteSmooth"):
    """A solid flight rising from z0 at x_bot to z1 at x_top (x_top < x_bot): n risers, each step's box reaching back
    to the top so there is no seam for a foot (or a probe's ray) to fall through."""
    n, r = SL.stair_steps(z1 - z0)
    assert abs((x_bot - x_top) - (n - 1) * SL.STAIR_RUN) < 1e-6, (x_bot - x_top, n)
    for k in range(1, n):
        p.solid((x_top, y0, z0), (x_bot - (k - 1) * SL.STAIR_RUN, y1, z0 + k * r), mat)
        p.b.box((x_bot - (k - 1) * SL.STAIR_RUN - 0.04, y0, z0 + k * r), (x_bot - (k - 1) * SL.STAIR_RUN, y1,
                                                                          z0 + k * r + 0.004), "MI_PaintYellow")


def stair_top(x_bot, rise):
    n, _r = SL.stair_steps(rise)
    return x_bot - (n - 1) * SL.STAIR_RUN


def railing(p, lo, hi):
    """A railing (collider included) between two plan corners at height lo[2]: posts, a top rail, a mid rail."""
    x0, y0, z = lo
    x1, y1, _ = hi
    p.b.box((x0, y0, z + RAIL_H - 0.05), (x1, y1, z + RAIL_H), "MI_PaintedMetal")
    p.b.box((x0, y0, z + 0.5), (x1, y1, z + 0.54), "MI_PaintedMetal")
    along_x = (x1 - x0) >= (y1 - y0)
    length = (x1 - x0) if along_x else (y1 - y0)
    for i in range(int(length / 1.5) + 2):
        t = min(length, i * 1.5)
        if along_x:
            p.b.box((x0 + t - 0.03, y0, z), (x0 + t + 0.03, y1, z + RAIL_H), "MI_PaintedMetal")
        else:
            p.b.box((x0, y0 + t - 0.03, z), (x1, y0 + t + 0.03, z + RAIL_H), "MI_PaintedMetal")
    p.col((x0, y0, z), (x1, y1, z + RAIL_H))


def cap_top(p, w, opening=None):
    """The cap's upper storey over a band `w` wide: the concourse floor (with `opening` (x0, x1, y0, y1) cut out for a
    stair), the roof, the two end walls (glazed) from the concourse's soffit up, and a light strip under the soffit."""
    L = SL.CAP_LEN
    z0, z1 = SL.AF - SL.AF_T, SL.AF
    y0, y1 = -w / 2, w / 2
    if opening is None:
        p.solid((-L / 2, y0, z0), (L / 2, y1, z1), "MI_ConcreteSmooth")
    else:
        ox0, ox1, oy0, oy1 = opening
        p.solid((-L / 2, y0, z0), (ox0, y1, z1), "MI_ConcreteSmooth")
        p.solid((ox1, y0, z0), (L / 2, y1, z1), "MI_ConcreteSmooth")
        if oy0 > y0 + 1e-6:
            p.solid((ox0, y0, z0), (ox1, oy0, z1), "MI_ConcreteSmooth")
        if oy1 < y1 - 1e-6:
            p.solid((ox0, oy1, z0), (ox1, y1, z1), "MI_ConcreteSmooth")
    p.b.box((-L / 2, y0, z1), (L / 2, y1, z1 + 0.01), "MI_Terrazzo")
    p.solid((-L / 2, y0, SL.ROOF), (L / 2, y1, SL.ROOF + SL.ROOF_T), "MI_Corrugated")
    for sx in (-1.0, 1.0):
        xa, xb = sorted((sx * L / 2, sx * (L / 2 - 0.2)))
        p.b.box((xa, y0, z0), (xb, y1, z1 + 0.9), "MI_Plaster")
        p.b.box((xa + 0.05, y0, z1 + 0.9), (xb - 0.05, y1, z1 + 2.6), "MI_GlassClear")
        p.b.box((xa, y0, z1 + 2.6), (xb, y1, SL.ROOF), "MI_Plaster")
        p.col((xa, y0, z0), (xb, y1, SL.ROOF))
    p.b.box((-L / 2 + 1.0, -0.15, z0 - 0.05), (L / 2 - 1.0, 0.15, z0), "MI_Light")


def island_platform(w):
    """An ISLAND platform module: both long faces are track edges (white line, yellow coping, tactile strip)."""
    p = Piece("GH_IslandPlatform_%s" % wname(w), "ground_hub")
    L, h = MODULE, SL.PLATFORM_H
    p.solid((-L / 2, -w / 2, 0), (L / 2, w / 2, h), "MI_ConcreteSmooth")
    for sg in (-1.0, 1.0):
        ye = sg * w / 2
        a, b = sorted((ye, ye - sg * 0.08))
        p.b.box((-L / 2, a, h), (L / 2, b, h + 0.004), "MI_PaintWhite")
        a, b = sorted((ye - sg * 0.8, ye - sg * 1.1))
        p.b.box((-L / 2, a, h), (L / 2, b, h + 0.006), "MI_Tactile")
        a, b = sorted((ye, ye - sg * 0.02))
        p.b.box((-L / 2, a, h - 0.12), (L / 2, b, h), "MI_PaintYellow")
    p.note = ("An island platform module (both faces are track edges, each %.2f m from its track centre). Top %.2f m "
              "over the bed; %.1f m long, tiled along X." % (SL.PLATFORM_EDGE, h, L))
    return p


def island_shed(w):
    p = Piece("GH_IslandShed_%s" % wname(w), "ground_hub")
    L, z0 = MODULE, SL.SHED_CLEAR
    p.solid((-0.15, -0.15, 0), (0.15, 0.15, z0), "MI_PaintedMetal")
    p.b.box((-L / 2, -w / 2 + 0.2, z0), (L / 2, w / 2 - 0.2, z0 + SL.SHED_T), "MI_Corrugated")
    p.b.box((-L / 2, -0.8, z0 - 0.3), (L / 2, 0.8, z0), "MI_PaintedMetal")
    for sg in (-1.0, 1.0):
        a, b = sorted((sg * (w / 2 - 1.0), sg * (w / 2 - 0.8)))
        p.b.box((-1.0, a, z0 - 0.05), (1.0, b, z0), "MI_Light")
    p.note = "An island platform's shed module: one row of columns on the centre line; keep the roof inside the platform."
    return p


def cap_platform(w, hand):
    """The cap's bay over a SIDE platform: the concourse over it with a stair down onto the platform against the cap
    wall (hand L: the track on -Y, the wall on +Y), and two columns carrying the concourse."""
    p = Piece("GH_CapPlatform_%s_%s" % (wname(w), hand), "ground_hub")
    sw = CAP_SW_SIDE
    xb = SL.CAP_STAIR_X
    xt = stair_top(xb, SL.AF - SL.PLATFORM_H)
    y0, y1 = w / 2 - sw, w / 2
    stair(p, xt, xb, y0, y1, SL.PLATFORM_H, SL.AF)
    cap_top(p, w, (xt, xb + 0.3, y0, y1))
    railing(p, (xt, y0 - 0.05, SL.AF), (xb + 0.3, y0, SL.AF))
    railing(p, (xb + 0.3, y0 - 0.05, SL.AF), (xb + 0.35, y1, SL.AF))
    for x in (-11.0, 11.0):
        p.solid((x - 0.25, w / 2 - 0.85, SL.PLATFORM_H), (x + 0.25, w / 2 - 0.35, SL.AF - SL.AF_T), "MI_PaintedMetal")
    if hand == "R":
        mirror_y(p)
    p.note = ("The cap's bay over a side platform (hand %s): the concourse (top %.2f m over the bed) with the stair "
              "down to the platform against the cap wall. Nothing below %.2f m may reach past the platform's track "
              "edge (-Y face for L): the train passes under the concourse." % (hand, SL.AF, SL.AF - SL.AF_T))
    return p


def cap_island(w):
    p = Piece("GH_CapIsland_%s" % wname(w), "ground_hub")
    sw = CAP_SW_ISLAND
    xb = SL.CAP_STAIR_X
    xt = stair_top(xb, SL.AF - SL.PLATFORM_H)
    stair(p, xt, xb, -sw / 2, sw / 2, SL.PLATFORM_H, SL.AF)
    cap_top(p, w, (xt, xb + 0.3, -sw / 2, sw / 2))
    for sg in (-1.0, 1.0):
        a, b = sorted((sg * sw / 2, sg * (sw / 2 + 0.05)))
        railing(p, (xt, a, SL.AF), (xb + 0.3, b, SL.AF))
    railing(p, (xb + 0.3, -sw / 2, SL.AF), (xb + 0.35, sw / 2, SL.AF))
    for x in (-11.0, 11.0):
        p.solid((x - 0.3, -0.3, SL.PLATFORM_H), (x + 0.3, 0.3, SL.AF - SL.AF_T), "MI_PaintedMetal")
    p.note = "The cap's bay over an island platform: the stair down on the platform's centre line, columns beside it."
    return p


def cap_lane():
    """The cap's bay over one two-way lane (its two tracks): the concourse spans it, nothing below its soffit."""
    w = 2 * (SL.TRACK_HALF + SL.PLATFORM_EDGE)
    p = Piece("GH_CapLane", "ground_hub")
    cap_top(p, w)
    p.note = ("The cap over a lane's two tracks, %.2f m between the platform edges. NOTHING may come below %.2f m "
              "over the bed here: the train (4.2 m gauge, overhead line) passes under it." % (w, SL.AF - SL.AF_T))
    return p


def cap_wall(door):
    p = Piece("GH_CapWall" + ("_Door" if door else ""), "ground_hub")
    L, t, top = SL.CAP_LEN, SL.WALL_T, SL.ROOF + SL.ROOF_T
    if door:
        d0, d1 = SL.WALL_DOOR
        p.solid((-L / 2, -t / 2, -SL.PLINTH), (d0, t / 2, top), "MI_Plaster")
        p.solid((d1, -t / 2, -SL.PLINTH), (L / 2, t / 2, top), "MI_Plaster")
        p.solid((d0, -t / 2, -SL.PLINTH), (d1, t / 2, SL.AF), "MI_Plaster")
        p.solid((d0, -t / 2, SL.AF + 2.6), (d1, t / 2, top), "MI_Plaster")
    else:
        p.solid((-L / 2, -t / 2, -SL.PLINTH), (L / 2, t / 2, top), "MI_Plaster")
    p.note = ("The cap's outer side wall, standing on the ground beside the outermost platform. The _Door one has the "
              "opening from the entrance annex's landing onto the concourse (along X %.1f..%.1f)." % SL.WALL_DOOR)
    return p


def annex(hand):
    """The ground hub's ENTRANCE ANNEX, against the cap wall (hand L: the cap on -Y, the street on +Y). The street door
    in the +Y face, the fare line along X between the unpaid strip (+Y) and the paid strip (-Y, next to the cap), and
    in the paid strip a stair up to a landing at the concourse level that meets the cap wall's opening."""
    p = Piece("GH_Annex_%s" % hand, "ground_hub")
    L, D, top, t = SL.CAP_LEN, SL.ANNEX_D, SL.ROOF + SL.ROOF_T, 0.3
    y0, y1 = -D / 2, D / 2
    yg = y0 + SL.ANNEX_PAID
    p.solid((-L / 2, y0, -SL.PLINTH), (L / 2, y1, 0), "MI_ConcreteSmooth")
    p.b.box((-L / 2, y0, 0), (L / 2, y1, 0.01), "MI_Terrazzo")
    d0, d1 = SL.ANNEX_DOOR
    p.solid((-L / 2, y1 - t, 0), (d0, y1, top), "MI_Plaster")
    p.solid((d1, y1 - t, 0), (L / 2, y1, top), "MI_Plaster")
    p.solid((d0, y1 - t, 2.6), (d1, y1, top), "MI_Plaster")
    p.b.box((d0 - 1.0, y1, 3.0), (d1 + 1.0, y1 + 0.08, 3.6), "MI_Sign")
    for sx in (-1.0, 1.0):
        xa, xb = sorted((sx * L / 2, sx * (L / 2 - t)))
        p.solid((xa, y0, 0), (xb, y1, top), "MI_Plaster")
    p.solid((-L / 2, y0, SL.ROOF), (L / 2, y1, top), "MI_Corrugated")
    # the stair up and the landing it arrives on (paid strip, against the cap wall)
    xb = SL.ANNEX_STAIR_X
    xt = stair_top(xb, SL.AF)
    sw = 2.4
    stair(p, xt, xb, y0, y0 + sw, 0.0, SL.AF)
    p.solid((-L / 2, y0, SL.AF - SL.AF_T), (xt, yg, SL.AF), "MI_ConcreteSmooth")
    p.b.box((-L / 2, y0, SL.AF), (xt, yg, SL.AF + 0.01), "MI_Terrazzo")
    railing(p, (-L / 2 + t, yg - 0.05, SL.AF), (xt, yg, SL.AF))
    railing(p, (xt, y0 + sw, SL.AF), (xt + 0.05, yg, SL.AF))
    # the fare line: a railing along X with the gate cabinets and lanes by the door
    lane, cab = SL.GATE_W, 0.25
    xg = 0.5 * (d0 + d1)
    cabs = [xg - lane - cab, xg, xg + lane + cab]
    for cx in cabs:
        p.solid((cx - cab / 2, yg - 0.6, 0), (cx + cab / 2, yg + 0.6, 1.0), "MI_PlasticWhite")
    lo_e, hi_e = cabs[0] - cab / 2, cabs[-1] + cab / 2
    railing(p, (-L / 2 + t, yg - 0.03, 0.0), (lo_e, yg + 0.03, 0.0))
    railing(p, (hi_e, yg - 0.03, 0.0), (L / 2 - t, yg + 0.03, 0.0))
    for cx in (xg - (lane + cab) / 2, xg + (lane + cab) / 2):
        p.gates.append(((cx, yg, 0.0), lane, 1.0))
    for k in range(3):                                    # ticket machines on the unpaid side, on the outer wall
        xm = d0 - 1.5 - k * 0.9
        p.solid((xm - 0.35, y1 - t - 0.6, 0), (xm + 0.35, y1 - t, 1.8), "MI_PlasticDark")
    p.b.box((-L / 2 + 1.0, yg + 1.8, SL.ROOF - 0.05), (L / 2 - 1.0, yg + 2.2, SL.ROOF), "MI_Light")
    if hand == "R":
        mirror_y(p)
    p.note = ("A ground hub's entrance annex (hand %s: the cap wall on %s). The street door is in the outer face; the "
              "GATE_ Empties are the ticket-gate lanes on the fare line (their arrows point to the street side). The "
              "stair up and the landing must meet the cap wall's opening at the concourse level (%.2f m)."
              % (hand, "-Y" if hand == "L" else "+Y", SL.AF))
    return p


def door_steps(n):
    """The flight outside an annex door down to the street: n risers of the most common size (the layout picks the
    count from the measured step, so a riser is within half a riser of the real one), from the sill (origin, floor
    level) outward along +Y; solid down to PLINTH below the sill so it stands in the ground however low it lies."""
    p = Piece("GH_DoorSteps_%d" % n, "ground_hub")
    r, run = SL.STAIR_RISE * 0.98, SL.STAIR_RUN
    w = SL.ANNEX_DOOR[1] - SL.ANNEX_DOOR[0] + 1.0
    for k in range(1, n):
        p.solid((-w / 2, 0.0, -SL.PLINTH), (w / 2, k * run, -k * r), "MI_ConcreteSmooth")
    p.note = ("Steps from an entrance annex's door down to the street, %d risers. The layout places the count that "
              "matches the street's height." % n)
    return p


def hub_widths():
    import island_rail_layout as R
    R.use_layout("tokyo_straight")
    sts = {n: st for n, st in SL.stations(R.analyse()).items() if st.form == "ground_hub"}
    return SL.kit_widths(sts)


def ground_hub_pieces():
    ws = hub_widths()
    out = [cap_lane(), cap_wall(False), cap_wall(True), annex("L"), annex("R")]
    out += [door_steps(n) for n in range(2, SL.DOOR_STEPS_MAX + 1)]     # n >= 2: under 0.2 m there are none
    for w in sorted(ws["island"]):
        out += [island_platform(w), island_shed(w), end_fence(w, "GH_EndFence_%s" % wname(w), "ground_hub"),
                cap_island(w)]
    # the side platforms are this file's own pieces (not the open-air file's): the file shows -- and an artist styles --
    # a whole hub station
    out.append(fence("GH", "ground_hub"))
    for w in sorted(ws["side"]):
        out += [cap_platform(w, "L"), cap_platform(w, "R"), platform(w, "GH", "ground_hub"),
                shed(w, "GH", "ground_hub"), end_fence(w, "GH_EndFence_%s" % wname(w), "ground_hub")]
    return out


FORM_PIECES = {"open_air": open_air_pieces, "ground_hub": ground_hub_pieces}
FORM_FILES = {"open_air": "Station_OpenAir.blend", "ground_hub": "Station_GroundHub.blend",
              "elevated_hub": "Station_ElevatedHub.blend"}


# ── the file ─────────────────────────────────────────────────────────────────────────────────────────────────────
def fingerprint(col):
    import hashlib
    h = hashlib.sha1()
    for o in sorted(col.objects, key=lambda o: o.name):
        off = o.location - col.instance_offset
        if o.type == "EMPTY":
            h.update(("E%s:%.4f,%.4f,%.4f|%.4f,%.4f,%.4f|%.4f;" % (o.name.split(".")[0], off.x, off.y, off.z,
                                                                  o.scale.x, o.scale.y, o.scale.z,
                                                                  o.rotation_euler.z)).encode())
            continue
        if o.type != "MESH":
            continue
        me = o.data
        for v in me.vertices:
            h.update(("%.4f,%.4f,%.4f;" % (v.co.x + off.x, v.co.y + off.y, v.co.z + off.z)).encode())
        h.update(("%d|%s" % (len(me.polygons), ",".join(m.name if m else "" for m in me.materials))).encode())
        h.update(("|" + ",".join(str(p.material_index) for p in me.polygons)).encode())
    return h.hexdigest()


def remove_piece(name):
    col = bpy.data.collections.get(name)
    if col is None:
        return
    for o in list(col.all_objects):
        me = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)
    bpy.data.collections.remove(col)


def install(p, spot, name=None):
    name = name or p.name
    remove_piece(name)
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    mesh = p.b.mesh()
    obj = bpy.data.objects.new(name, mesh)
    col.objects.link(obj)
    for i, (c, h) in enumerate(p.cols):
        e = bpy.data.objects.new("COL_%02d" % i, None)
        e.empty_display_type = "CUBE"
        e.empty_display_size = 1.0
        e.location, e.scale = c, h
        e.hide_render = True
        col.objects.link(e)
    for i, (q, w, hh) in enumerate(p.gates):
        e = bpy.data.objects.new("GATE_%d" % i, None)
        e.empty_display_type = "SINGLE_ARROW"
        e.empty_display_size = 0.8
        e.location = q
        e.rotation_euler = (0.0, math.radians(90.0), 0.0)     # the arrow (local +Z) drawn along +X
        e["w"], e["h"] = float(w), float(hh)
        col.objects.link(e)
    col["bk_piece_path"] = "pieces/%s/%s.gltf" % (p.cat, p.name)
    col["bk_category"] = p.cat
    col["edit_note"] = p.note
    for o in col.objects:
        o["edit_note"] = p.note
        if o.parent is None:
            o.location = o.location + spot
    col.instance_offset = spot
    col["st_generated"] = fingerprint(col)
    return col


def preview(pieces_by_name, w=4.0, length=90.0):
    """A whole default open-air station from linked instances, for the eye: the Preview collection (never exported)."""
    old = bpy.data.collections.get("Preview")
    if old:
        for o in list(old.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(old)
    pv = bpy.data.collections.new("Preview")
    bpy.context.scene.collection.children.link(pv)
    base = mathutils.Vector((0.0, 30.0, 0.0))
    n = int(length / MODULE)
    edge = SL.PLATFORM_EDGE + SL.TRACK_HALF
    ws = wname(w)

    def inst(piece, loc, yaw):
        col = bpy.data.collections.get(piece)
        if col is None:
            return
        e = bpy.data.objects.new("pv_" + piece, None)
        e.instance_type = "COLLECTION"
        e.instance_collection = col
        e.location = base + mathutils.Vector(loc)
        e.rotation_euler = (0.0, 0.0, yaw)
        pv.objects.link(e)
    for side, sg in (("L", 1.0), ("R", -1.0)):
        cy = sg * (edge + w / 2)
        yaw = 0.0 if sg > 0 else math.pi
        for k in range(n):
            a = -length / 2 + MODULE * (k + 0.5)
            inst("OA_Platform_" + ws, (a, cy, 0.0), yaw)
            inst("OA_Shed_" + ws, (a, cy, SL.PLATFORM_H), yaw)
            inst("OA_Fence", (a, sg * (edge + w - SL.FENCE_T / 2), SL.PLATFORM_H), 0.0)
        inst("OA_EndFence_" + ws, (-length / 2 + SL.FENCE_T / 2, cy, SL.PLATFORM_H), 0.0)
        bd = w + SL.BUILDING_OUT
        inst("OA_Building_%s_%s" % (ws, side), (length / 2 + SL.BUILDING_LEN / 2, sg * (edge + bd / 2), 0.0), 0.0)
    for tc in (-SL.TRACK_HALF, SL.TRACK_HALF):      # the track centres, as thin rails, so the gap reads
        e = bpy.data.objects.new("pv_track", None)
        e.empty_display_type = "PLAIN_AXES"
        e.location = base + mathutils.Vector((0.0, tc, 0.0))
        pv.objects.link(e)


def preview_station(name):
    """A whole station from linked instances, laid out by tools/station_layout.py exactly as the game lays it out (the
    Preview collection, never exported): each prop's piece at its Godot local transform, turned back to Blender axes."""
    import island_rail_layout as R
    R.use_layout("tokyo_straight")
    st = SL.stations(R.analyse())[name]
    if not st.entrance:
        st.entrance = "left"
    old = bpy.data.collections.get("Preview")
    if old:
        for o in list(old.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(old)
    pv = bpy.data.collections.new("Preview")
    bpy.context.scene.collection.children.link(pv)
    base = mathutils.Vector((0.0, 60.0, 0.0))
    def bare(ref, a, c, h, yaw):          # the layout's placement without the kit's manifest (not exported yet)
        x, y, z = SL.to_godot_local(a, c, h)
        return [{"piece": SL.KIT + ":" + ref, "at": [x, z], "y": y, "yaw": yaw}]
    real, SL._piece_props = SL._piece_props, bare
    try:
        props = SL.props(st)
    finally:
        SL._piece_props = real
    for pr in props:
        ref = pr.get("piece")
        if not ref:
            continue
        col = bpy.data.collections.get(ref.split(":", 1)[1])
        if col is None:
            continue
        e = bpy.data.objects.new("pv_" + col.name, None)
        e.instance_type = "COLLECTION"
        e.instance_collection = col
        gx, gz = pr["at"]
        e.location = base + mathutils.Vector((gx, -gz, pr.get("y", 0.0)))
        e.rotation_euler = (0.0, 0.0, math.radians(pr.get("yaw", 0.0)))
        pv.objects.link(e)


PREVIEW = {"ground_hub": "Bay"}


def build_form(form):
    path = os.path.join(KIT, FORM_FILES[form])
    if os.path.exists(path):
        bpy.ops.wm.open_mainfile(filepath=path)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.context.scene.name = "Station_" + form
    pieces = FORM_PIECES[form]()
    kept, wanted = [], []
    for i, p in enumerate(sorted(pieces, key=lambda p: p.name)):
        spot = mathutils.Vector(((i % ROW) * GRID, -(i // ROW) * GRID - 60.0, 0.0))
        col = bpy.data.collections.get(p.name)
        if col is not None and col.get("st_generated") and col["st_generated"] != fingerprint(col) \
                and p.name not in FORCE:
            # hand-edited: KEEP it, and say whether the generator would have changed it (build it aside to compare)
            tmp = install(p, spot, name=p.name + "__cmp")
            if tmp["st_generated"] != col["st_generated"]:
                kept.append(p.name)
            else:
                print("[build_station_blends] KEPT %s: edited by hand; the generator has nothing new for it" % p.name)
            remove_piece(tmp.name)
            continue
        before = col.get("st_generated") if col is not None else None
        c = install(p, spot)
        if before is not None and before != c["st_generated"]:
            wanted.append(p.name)
        print("[build_station_blends] %-24s %s" % (p.name, "regenerated" if before else "new"))
    if form in PREVIEW:
        preview_station(PREVIEW[form])
    else:
        preview({p.name: p for p in pieces})
    readme = bpy.data.texts.get("README_artist") or bpy.data.texts.new("README_artist")
    readme.from_string(open(os.path.join(KIT, "ARTIST_NOTES.md")).read())
    for m in list(bpy.data.materials):
        if m.users == 0:
            bpy.data.materials.remove(m)
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    print("[build_station_blends] %s: %d pieces -> %s" % (form, len(pieces), os.path.relpath(path, ROOT)))
    for n in kept:
        print("[build_station_blends] KEPT %s: edited since it was generated, and the generator WANTS TO CHANGE IT "
              "(--force=%s overwrites the artist's edit; ask first)" % (n, n))
    return kept


def main():
    kept = []
    for form in FORMS:
        kept += build_form(form)
    if kept:
        sys.exit(3)


main()
