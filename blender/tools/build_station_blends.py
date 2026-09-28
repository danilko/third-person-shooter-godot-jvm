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
                 the lane's centre, its local +X pointing to the UNPAID (street) side, custom props `w` and `h`;
    - `LIFT_<n>` a lift (world.Elevator builds the car, its doors and the landing doors, never modelled): at the centre
                 of the shaft's floor at the LOW stop, custom props `w` / `d` (the shaft's inside along X / Y), `rise`
                 (to the top stop), `door_w` / `door_h` (each door's clear opening). Its doors are on the +X and -X
                 faces (along the track), a two-leaf centre-opening slide each. The SHAFT around it is the piece's
                 own mesh and COL_ boxes: keep a door opening in each X face at each stop.
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
        self.gates = []         # [(pos, w, h)] or [(pos, w, h, yaw)]: yaw (deg about Z) turns the unpaid side off +X
        self.lifts = []         # [(pos, w, d, rise, door_w, door_h)]
        self.hulls = []         # [[(x, y, z), ...]]: convex colliders (a ramp's smooth slope)
        self.doors = []         # [(pos, (dx, dy) out of the room, w, h, style, slide_dir)]: DOOR_ Empties
        self.props = []         # [(library piece, pos, yaw deg, collide)]: PROP_ Empties -- a LIBRARY fixture (the
                                # konbini's restroom kit: washlet toilet, basin, mirror, ...) placed by the game
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


class Frame:
    """A right-angle frame in a piece's plan: local (u, v, z) -> piece (x, y, z), u along (ux, uy), v along (vx, vy),
    each a unit axis vector. Boxes stay axis-aligned, so a block authored once stands in any of the four turns."""
    def __init__(self, ox, oy, ux, uy, vx, vy, oz=0.0):
        self.o, self.u, self.v, self.oz = (ox, oy), (ux, uy), (vx, vy), oz

    def pt(self, u, v, z):
        return (self.o[0] + u * self.u[0] + v * self.v[0], self.o[1] + u * self.u[1] + v * self.v[1], self.oz + z)

    def prop(self, p, piece, u, v, z, face, collide="none"):
        """A LIBRARY fixture at (u, v, z) whose front faces `face` = (du, dv) in this frame (a library piece's front
        is its -Y, so its back goes to the wall behind it)."""
        fx = face[0] * self.u[0] + face[1] * self.v[0]
        fy = face[0] * self.u[1] + face[1] * self.v[1]
        yaw = round(math.degrees(math.atan2(fy, fx)) + 90.0, 4) % 360.0
        p.props.append((piece, self.pt(u, v, z), yaw, collide))

    def box(self, p, lo, hi, mat, collide=True):
        a, b = self.pt(*lo), self.pt(*hi)
        lo_, hi_ = tuple(min(a[i], b[i]) for i in range(3)), tuple(max(a[i], b[i]) for i in range(3))
        if collide:
            p.solid(lo_, hi_, mat)
        else:
            p.b.box(lo_, hi_, mat)


def restroom_block(p, f, top):
    """THE RESTROOM BLOCK (駅のトイレ, the standard set of a modern Japanese station) in frame `f`: u 0..WC_L along its
    OPEN face (v 0, the hall), v 0..WC_D back from it, floor at z 0, walls to `top`. Men (u 0..3.0): one stall, two
    urinals, three sinks; women (u 3.0..6.4): three stalls, three sinks; the accessible room (多機能, u 6.4..WC_L). Each
    room's door is in the hall face behind a privacy screen; a pictogram sign over each."""
    L, D, t = SL.WC_L, SL.WC_D, 0.15
    f.box(p, (0, 0, 0), (L, D, 0.01), "MI_TileWhite", collide=False)
    # outer walls: the back, the two ends, and the hall face with the three doors
    f.box(p, (0, D - t, 0), (L, D, top), "MI_Plaster")
    f.box(p, (0, 0, 0), (t, D, top), "MI_Plaster")
    f.box(p, (L - t, 0, 0), (L, D, top), "MI_Plaster")
    doors = [(2.0, 2.9), (3.2, 4.1), (6.7, 7.9)]          # men / women / accessible (1.2 m: a wheelchair)
    u = 0.0
    for d0, d1 in doors:
        f.box(p, (u, 0, 0), (d0, t, top), "MI_Plaster")
        f.box(p, (d0, 0, 2.2), (d1, t, top), "MI_Plaster")
        u = d1
    f.box(p, (u, 0, 0), (L, t, top), "MI_Plaster")
    for u in (3.0, 6.4):                                  # the partitions between the rooms
        f.box(p, (u - t / 2, 0, 0), (u + t / 2, D, top), "MI_Plaster")
    # the privacy screens inside the men's and women's doors (the entry turns behind them)
    f.box(p, (1.7, 1.05, 0), (3.0 - t / 2, 1.15, 2.1), "MI_PaintedMetalDark")
    f.box(p, (3.0 + t / 2, 1.05, 0), (4.4, 1.15, 2.1), "MI_PaintedMetalDark")

    # THE FIXTURES are the konbini's LIBRARY restroom kit (user, 2026-09-28): the washlet toilet (WC_Toilet), the square
    # basin with a mirror over it (WC_Basin, WC_Mirror), the stall partitions (WC_Partition), the grab rail and the baby
    # table -- PROP_ markers the game places as library pieces, so an edit to the library reaches every station
    def stall(u0, u1):
        f.box(p, (u0, 3.35, 0), (u1, 3.4, 2.0), "MI_PaintedMetalDark")        # the door (shut; a placeholder)
        f.prop(p, "WC_Partition", u1 - 0.015, 3.35 + 0.75, 0.0, (0.0, -1.0), "box")
        f.prop(p, "WC_Toilet", (u0 + u1) / 2, D - t - 0.375, 0.0, (0.0, -1.0), "box")

    def basins(u_wall, face, vs):
        for v in vs:
            f.prop(p, "WC_Basin", u_wall + face * 0.283, v, 0.0, (face, 0.0))
            f.prop(p, "WC_Mirror", u_wall + face * 0.025, v, 0.0, (face, 0.0))
    # men: one stall at the back of the far end, two urinals on the back wall, three basins along the end wall
    stall(t, 1.15)
    for uc in (1.7, 2.45):
        f.box(p, (uc - 0.2, D - t - 0.35, 0.35), (uc + 0.2, D - t, 1.05), "MI_PlasticWhite")
        f.box(p, (uc + 0.33, D - t - 0.45, 0.5), (uc + 0.36, D - t, 1.5), "MI_PaintedMetalDark", collide=False)
    basins(t, 1.0, (1.55, 2.25, 2.95))
    # women: three stalls along the back, three basins along the accessible room's wall
    for k in range(3):
        stall(3.0 + t / 2 + k * 1.07, 3.0 + t / 2 + (k + 1) * 1.07)
    basins(6.4 - t / 2, -1.0, (1.3, 2.0, 2.7))
    # accessible (多機能トイレ): the toilet in the back corner, the grab rail on the end wall beside it, a basin and
    # mirror on the partition wall, the baby table on the back wall; its doorway a SOLID SLIDING door (引き戸, the
    # konbini's), hung on the hall face and running over the wall toward the women's room
    f.prop(p, "WC_Toilet", 7.9, D - t - 0.375, 0.0, (0.0, -1.0), "box")
    f.prop(p, "WC_GrabRail", L - t, D - t - 0.45, 0.0, (-1.0, 0.0))
    basins(6.4 + t / 2, 1.0, (2.85,))
    f.prop(p, "WC_BabyTable", 6.95, D - t, 0.0, (0.0, -1.0))
    out = (-f.v[0], -f.v[1])
    run = (-f.u[0], -f.u[1])
    left = (-out[1], out[0])
    p.doors.append((f.pt(7.3, t / 2, 0.0), out, 1.2, 2.2, "slide",
                    1.0 if run[0] * left[0] + run[1] * left[1] > 0 else -1.0))
    # pictogram signs over the doors: men blue, women red, accessible blue with a white panel
    for (d0, d1), mat in zip(doors, ("MI_Sign", "MI_FabricRed", "MI_Sign")):
        f.box(p, (d0, -0.06, 2.3), (d1, 0.0, 2.7), mat, collide=False)
        f.box(p, ((d0 + d1) / 2 - 0.12, -0.07, 2.4), ((d0 + d1) / 2 + 0.12, -0.06, 2.6), "MI_PaintWhite",
              collide=False)


def service_counter(p, f, top):
    """The station staff's SERVICE COUNTER (有人改札 / 駅務室) in frame `f`: a glazed box u 0..COUNTER_L, v 0..D, standing on
    the fare line, a window and a counter to each side of it; staff only, so solid to a walker."""
    L, D = SL.COUNTER_L, SL.WC_D
    f.box(p, (0, 0, 0), (L, D, 1.0), "MI_PlasticWhite")                        # the counter body (collides whole)
    f.box(p, (0, 0, 1.0), (L, D, 2.4), "MI_GlassClear")
    f.box(p, (0, 0, 2.4), (L, D, top), "MI_Plaster")
    for uu in (-0.35, L):                                                       # the counters out each side
        f.box(p, (uu, 0.4, 0.95), (uu + 0.35, D - 0.4, 1.0), "MI_Wood", collide=False)
    f.box(p, (0.2, -0.06, 2.45), (L - 0.2, 0.0, 2.75), "MI_Sign", collide=False)


def shutter(p, f, u0, u1, n, h, t, posts=True):
    """A ROLLER-SHUTTER OPENING (every station entrance, user 2026-09-27) in a wall of frame `f`: the wall is v 0..t,
    its OUTSIDE toward -v, the opening u0..u1 (the caller leaves it open), h clear, with a guide rail down each side
    and over the opening, in the header, the housing the shutter rolls up into, its bottom bar showing under it.
    `posts` True (a shop front): n bays (`SL.shutter_bays`), a post between two (a collider), a rail and a bottom bar
    per bay. False (every station ENTRANCE, user 2026-09-28: "no support in between, only each side of the opening"):
    one shutter across the whole opening, framed only at its two sides. Open all day: nothing in the opening collides."""
    bays = SL.shutter_bays(u0, u1, n) if posts else [(u0, u1)]
    for (_a0, a1), (b0, _b1) in zip(bays, bays[1:]):
        f.box(p, (a1, 0.0, 0.0), (b0, t, h), "MI_PaintedMetal")
    for b0, b1 in bays:
        for ue in (b0, b1):
            f.box(p, (ue - 0.035, -0.07, 0.0), (ue + 0.035, 0.0, h), "MI_PaintedMetalDark", collide=False)
        f.box(p, (b0, -0.3, h - 0.06), (b1, -0.22, h), "MI_Steel", collide=False)          # the bottom bar
    f.box(p, (u0 - 0.1, -0.4, h), (u1 + 0.1, 0.0, h + 0.45), "MI_PaintedMetal", collide=False)   # the housing
    f.box(p, (u0 - 0.1, -0.42, h + 0.02), (u1 + 0.1, -0.4, h + 0.43), "MI_Corrugated", collide=False)


def store_front(p, f, u0, u1, top, t=0.15):
    """A STATION STORE's glazed front (user, 2026-09-28) in frame `f`, u0..u1 along the wall (v 0..t, the outside --
    the hall -- toward -v), floor z 0: fixed glass either side of a SLIDING GLASS door in its middle (two leaves
    parting from the middle where the front is wide enough, else one: `SL.store_door_w`), a transom over the door, a
    solid band to `top`. The leaves are the game's (the DOOR_ Empty, style `slide_glass`, automatic); they slide
    behind the fixed glass, which stands on the wall's outer face."""
    w = u1 - u0
    dw, dh = SL.store_door_w(w), SL.STORE_DOOR_H
    h = min(SL.SHUTTER_H, top - 0.3)
    uc = (u0 + u1) / 2.0
    d0, d1 = uc - dw / 2, uc + dw / 2
    f.box(p, (u0, 0.0, h), (u1, t, top), "MI_Plaster")                                   # the band over the glass
    for a0, a1 in ((u0, d0), (d1, u1)):                                                  # the fixed glass
        f.box(p, (a0, 0.0, 0.0), (a1, 0.04, h), "MI_GlassClear")
        f.box(p, (a0, 0.04, 0.0), (a1, t, 0.12), "MI_PaintedMetalDark")                  # its kick rail
    for ue in (u0, d0, d1, u1):                                                          # the mullions
        f.box(p, (ue - 0.03, 0.0, 0.0), (ue + 0.03, 0.06, h), "MI_PaintedMetalDark", collide=False)
    f.box(p, (d0, 0.0, dh), (d1, 0.04, h), "MI_GlassClear", collide=False)                # the transom
    f.box(p, (d0, 0.0, dh - 0.06), (d1, 0.08, dh), "MI_PaintedMetalDark", collide=False)  # the head rail
    q = f.pt(uc, 0.1, 0.0)
    out = (-f.v[0], -f.v[1])
    p.doors.append((q, out, dw, dh, "slide_glass", 1.0))
    return h


def shop_unit(p, f, w, d, top, back=True):
    """One SHOP (the large hubs' shops, user 2026-09-27) in frame `f`: u 0..w along its FRONT (v 0, the front's outer
    face; outside toward -v), v 0..d back from it, floor at z 0, walls to `top`. Its front is glazed with a SLIDING
    GLASS door (`store_front`, user 2026-09-28), a fascia sign over it; inside, shelving on the back and side walls and
    a counter by the front. `back` False: the wall behind it is someone else's (an outer wall)."""
    t, pier = 0.15, 0.35
    f.box(p, (0, 0, 0), (w, d, 0.01), "MI_Terrazzo", collide=False)
    f.box(p, (0, 0, 0), (pier, t, top), "MI_Plaster")
    f.box(p, (w - pier, 0, 0), (w, t, top), "MI_Plaster")
    h = store_front(p, f, pier, w - pier, top, t)
    f.box(p, (pier, -0.1, h + 0.1), (w - pier, -0.02, min(top, h + 0.55)), "MI_Sign", collide=False)
    for u in (0.0, w - 0.1):                                                   # the side walls (shared with a neighbour)
        f.box(p, (u, t, 0), (u + 0.1, d, top), "MI_Plaster")
    if back:
        f.box(p, (0, d - t, 0), (w, d, top), "MI_Plaster")
    vb = d - (t if back else 0.0)
    f.box(p, (0.3, vb - 0.45, 0), (w - 0.3, vb, 1.9), "MI_Wood")                   # shelving on the back wall
    f.box(p, (0.35, vb - 0.44, 0.9), (w - 0.35, vb - 0.02, 1.6), "MI_Goods", collide=False)
    if d > 4.0:
        for u in (0.1, w - 0.55):                                              # and down each side of a deep shop
            f.box(p, (u, t + 1.8, 0), (u + 0.45, vb - 0.6, 1.9), "MI_Wood")
    f.box(p, (w - pier - 1.0, t + 0.5, 0), (w - pier - 0.1, t + 1.1, 1.0), "MI_PlasticWhite")   # the counter
    f.box(p, (w / 2 - 1.0, d / 2 - 0.2, top - 0.05), (w / 2 + 1.0, d / 2 + 0.2, top), "MI_Light", collide=False)


def machines(p, f):
    """The ticket machines (2), an ATM and two vending machines (券売機 / ATM / 自販機) against a wall in frame `f`: u along
    the wall, v 0..0.75 out from it (v 0 = the wall), outside the paid area."""
    u = 0.0
    for w, mat, h in ((0.75, "MI_PlasticDark", 1.8), (0.75, "MI_PlasticDark", 1.8), (0.9, "MI_Steel", 1.9),
                      (1.0, "MI_FabricRed", 1.83), (1.0, "MI_Sign", 1.83)):
        f.box(p, (u, 0, 0), (u + w, 0.75, h), mat)
        f.box(p, (u + 0.1, 0.75, 0.9), (u + w - 0.1, 0.76, 1.5), "MI_GlassClear", collide=False)
        u += w + 0.1
    return u


def building(w, hand):
    """An open-air station's END BUILDING, in line with its platform (the user's 2026-09-27 plan): its whole floor is
    at PLATFORM level (the platform comes straight in through the -X face); the street door is in the +X face, where
    the entry piece (`OA_Entry_*`) brings a stair and a slope down to the street. Inside, from the platform: the paid
    hall with its restroom block against the far wall, the FARE LINE across the hall (GATE_LANES lanes by the
    track-side wall, the SERVICE COUNTER on the line), the unpaid hall with the other restroom block and the ticket /
    ATM / vending machines, the entrance (two roller-shutter bays, open all day). Origin: footprint centre at BED level.
    `hand` 'L' has the track on -Y."""
    p = Piece("OA_Building_%s_%s" % (wname(w), hand), "open_air")
    L, D, t = SL.BUILDING_LEN, SL.BUILDING_D, SL.BUILDING_T
    hp, H = SL.PLATFORM_H, SL.BUILDING_H
    top = hp + H
    y0, y1 = -D / 2, D / 2                      # y0 = the track side (the platform edge line)
    yp = y0 + w                                 # the platform's outer edge
    x0, x1 = -L / 2, L / 2
    xg = x0 + SL.GATE_X
    # the floor: solid down into the ground, its top the platform's
    p.solid((x0, y0, -SL.PLINTH), (x1, y1, hp), "MI_ConcreteSmooth")
    p.b.box((x0, y0 + t, hp), (x1, y1 - t, hp + 0.01), "MI_Terrazzo")
    # walls: track side, far side, the -X face beside the platform opening (a header over it), the street face with
    # the door (DOOR_W, centred DOOR_OFF off the track wall), the roof
    p.solid((x0, y0, hp), (x1, y0 + t, top), "MI_Plaster")
    p.solid((x0, y1 - t, hp), (x1, y1, top), "MI_Plaster")
    p.solid((x0, yp, hp), (x0 + t, y1, top), "MI_Plaster")
    p.solid((x0, y0, hp + 2.6), (x0 + t, yp, top), "MI_Plaster")
    yd0, yd1 = y0 + SL.DOOR_OFF - SL.DOOR_W / 2, y0 + SL.DOOR_OFF + SL.DOOR_W / 2
    p.solid((x1 - t, y0, hp), (x1, yd0, top), "MI_Plaster")
    p.solid((x1 - t, yd1, hp), (x1, y1, top), "MI_Plaster")
    p.solid((x1 - t, yd0, hp + 2.6), (x1, yd1, top), "MI_Plaster")
    shutter(p, Frame(x1, yd0, 0.0, 1.0, -1.0, 0.0, hp), 0.0, SL.DOOR_W, SL.DOOR_BAYS, 2.6, t, posts=False)
    p.solid((x0, y0, top), (x1, y1, top + 0.25), "MI_ConcreteSmooth")
    p.b.box((x1, (yd0 + yd1) / 2 - 2.5, hp + 3.07), (x1 + 0.08, (yd0 + yd1) / 2 + 2.5, hp + 3.4), "MI_Sign")
    for xl in (x0 + 3.0, xg - 2.5, xg + 3.0, x1 - 3.0):                        # ceiling lights
        p.b.box((xl - 1.0, (y0 + yd1) / 2 - 0.2, top - 0.05), (xl + 1.0, (y0 + yd1) / 2 + 0.2, top), "MI_Light")
    # the restroom blocks against the far wall, open to the hall (their hall face at y1 - WC_D): paid, then unpaid
    for u0 in (x0 + t, xg + SL.COUNTER_L / 2):
        restroom_block(p, Frame(u0, y1 - SL.WC_D, 1.0, 0.0, 0.0, 1.0, hp), SL.BUILDING_H - 0.02)
    # the fare line: cabinets 0.25 wide with GATE_W lanes, from the track wall; a railing to the service counter
    lane, cab = SL.GATE_W, 0.25
    cabs = [y0 + t + 0.8 + i * (lane + cab) - cab / 2 for i in range(SL.GATE_LANES + 1)]
    for cy in cabs:
        p.solid((xg - 0.6, cy - cab / 2, hp), (xg + 0.6, cy + cab / 2, hp + 1.0), "MI_PlasticWhite")
    for a_, b_ in zip(cabs, cabs[1:]):
        p.gates.append(((xg, (a_ + b_) / 2, hp), lane, 1.0))
    railing(p, (xg - 0.03, y0 + t, hp), (xg + 0.03, cabs[0] - cab / 2, hp))
    yc0 = y1 - SL.WC_D
    railing(p, (xg - 0.03, cabs[-1] + cab / 2, hp), (xg + 0.03, yc0, hp))
    service_counter(p, Frame(xg - SL.COUNTER_L / 2, yc0, 1.0, 0.0, 0.0, 1.0, hp), SL.BUILDING_H - 0.02)
    # the machines outside the paid area, against the track-side wall (v out from it, +Y)
    machines(p, Frame(xg + 1.5, y0 + t, 1.0, 0.0, 0.0, 1.0, hp))
    if hand == "R":
        mirror_y(p)
    p.note = ("An open-air station's end building (hand %s): the whole floor is at the platform top; the -X face is where "
              "the platform comes in, the +X face the street door (the OA_Entry_* piece brings the stair and slope down "
              "to the street). The track-side wall stands ON the platform edge line (the gauge is 0.2 m beyond it) -- "
              "never move it toward the track. The GATE_ Empties are the ticket-gate lanes: keep one between each pair "
              "of cabinets, and keep the fare line closed from the track wall to the service counter. The other hand "
              "(_L/_R) is a mirror: make the same change there." % hand)
    return p


def wedge_y(p, x0, x1, y0, y1, z0, z_at_y0, z_at_y1, mat):
    """A solid from z0 up to a top sloping along Y (a ramp leg); its collider is the same wedge (a convex hull), so the
    slope is smooth underfoot (user, 2026-09-27: "a smooth triangular slope, not built off a staircase")."""
    bm = p.b.bm
    mi = p.b._mi(mat)
    q = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z_at_y0), (x1, y0, z_at_y0), (x1, y1, z_at_y1), (x0, y1, z_at_y1)]
    vs = [bm.verts.new(v) for v in q]
    for fc in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        face = bm.faces.new([vs[i] for i in fc])
        face.material_index = mi
    p.hulls.append(q)                           # the collider IS the wedge: a smooth slope, not steps


def wedge_x_col(p, x0, x1, y0, y1, z0, z_at_x0, z_at_x1, mat):
    """A ramp leg sloping along X from z0, its collider the same wedge (a convex hull)."""
    bm = p.b.bm
    mi = p.b._mi(mat)
    q = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z_at_x0), (x1, y0, z_at_x1), (x1, y1, z_at_x1), (x0, y1, z_at_x0)]
    vs = [bm.verts.new(v) for v in q]
    for fc in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        face = bm.faces.new([vs[i] for i in fc])
        face.material_index = mi
    p.hulls.append(q)


def entry_out(n, hand):
    """The OTHER entrance (the user's 'stair ^ | slope ^'): the slope runs straight OUT beside the stair instead of
    along the front -- for a front with no room beside the door (the reserve tries the along-the-front one first).
    Same origin and landing as `entry`; the slope starts at the landing's +Y side (away from the rail for hand L)."""
    p = Piece("OA_EntryOut_%d_%s" % (n, hand), "open_air")
    rise, r = n * SL.ENTRY_RISE, SL.ENTRY_RISE
    dw, land, run = SL.DOOR_W, SL.ENTRY_LAND, SL.STAIR_RUN
    zb = -rise - SL.PLINTH
    ya, yb = dw / 2 + 0.2, dw / 2 + 0.2 + SL.RAMP_W
    p.solid((0.0, -dw / 2, zb), (land, yb, 0.0), "MI_Terrazzo")
    for k in range(1, n):
        x = land + (k - 1) * run
        p.solid((land, -dw / 2, zb), (x + run, dw / 2, -k * r), "MI_ConcreteSmooth")
        p.b.box((x + run - 0.04, -dw / 2, -k * r), (x + run, dw / 2, -k * r + 0.004), "MI_PaintYellow")
    xs = land + (n - 1) * run
    p.b.beam((land, -dw / 2, 0.9), (xs, -dw / 2, -rise + r + 0.9), 0.05, "MI_Steel")
    p.solid((land, dw / 2, zb), (max(xs, land + 0.3), ya, 0.9 - rise), "MI_ConcreteSmooth")   # stair | slope wall
    x, z = land, 0.0
    segs = SL.ramp_segments(n)
    for i, (sr, sh) in enumerate(segs):
        wedge_x_col(p, x, x + sr, ya, yb, zb, z, z - sh, "MI_ConcreteSmooth")
        p.b.beam((x, yb + 0.05, z + 0.85), (x + sr, yb + 0.05, z - sh + 0.85), 0.05, "MI_Steel")
        p.col((x, yb, z - sh), (x + sr, yb + 0.1, z + 0.9))
        x, z = x + sr, z - sh
        if i < len(segs) - 1:
            p.solid((x, ya, zb), (x + SL.RAMP_LAND, yb, z), "MI_ConcreteSmooth")
            x += SL.RAMP_LAND
    if hand == "R":
        mirror_y(p)
    p.note = ("The entrance stair + slope (hand %s, %d risers, %.2f m), the slope running STRAIGHT OUT beside the "
              "stair. Keep it 1:%g with a landing every %.2f m of rise." % (hand, n, rise, SL.RAMP_SLOPE,
                                                                        SL.RAMP_SEG_RISE))
    return p


def entry(n, hand, pre="OA", cat="open_air", dw=None, kind="Entry"):
    """The ENTRANCE STAIR + SLOPE outside an open-air building's street door (user, 2026-09-27: "in addition to the
    stair, a slope for accessibility"), for a sill n risers of ENTRY_RISE over the street. Origin: the door's centre on
    the street face, at FLOOR level (the platform top); +X out to the street. A landing ENTRY_LAND deep across the
    door; a stair of n risers straight out; and from the landing's side a smooth 1:15 SLOPE running along the building's
    front AWAY from the rail (+Y for hand L), a landing every 0.75 m of rise, handrails both sides. Solid down to the
    street and PLINTH past it, so it stands in the ground however it lies."""
    p = Piece("%s_%s_%d_%s" % (pre, kind, n, hand), cat)
    rise, r = n * SL.ENTRY_RISE, SL.ENTRY_RISE
    dw, land, run = dw or SL.DOOR_W, SL.ENTRY_LAND, SL.STAIR_RUN
    zb = -rise - SL.PLINTH
    p.solid((0.0, -dw / 2, zb), (land, dw / 2, 0.0), "MI_Terrazzo")
    for k in range(1, n):
        x = land + (k - 1) * run
        p.solid((land, -dw / 2, zb), (x + run, dw / 2, -k * r), "MI_ConcreteSmooth")
        p.b.box((x + run - 0.04, -dw / 2, -k * r), (x + run, dw / 2, -k * r + 0.004), "MI_PaintYellow")
    xs = land + (n - 1) * run
    for yy in (-dw / 2, dw / 2) + ((0.0,) if dw > 6.0 else ()):   # handrails (a middle one on a wide stair)
        p.b.beam((land, yy, 0.9), (xs, yy, -rise + r + 0.9), 0.05, "MI_Steel")
    # the slope: from the landing's +Y edge along the front (x 0.1 .. 0.1 + RAMP_W), down to the street
    xa, xb = 0.1, 0.1 + SL.RAMP_W
    y, z = dw / 2, 0.0
    p.solid((0.0, dw / 2, zb), (land, dw / 2 + 0.01, 0.0), "MI_Terrazzo", collide=False)
    for i, (sr, sh) in enumerate(SL.ramp_segments(n)):
        wedge_y(p, xa, xb, y, y + sr, zb, z, z - sh, "MI_ConcreteSmooth")
        p.b.beam((xb + 0.05, y, z + 0.85), (xb + 0.05, y + sr, z - sh + 0.85), 0.05, "MI_Steel")
        p.col((xb, y, z - sh), (xb + 0.1, y + sr, z + 0.9))                    # the kerb + rail: nobody steps off
        y, z = y + sr, z - sh
        if i < len(SL.ramp_segments(n)) - 1:
            p.solid((xa, y, zb), (xb, y + SL.RAMP_LAND, z), "MI_ConcreteSmooth")
            y += SL.RAMP_LAND
    if hand == "R":
        mirror_y(p)
    p.note = ("The entrance stair + slope outside an open-air building (hand %s), %d risers (%.2f m) down from the door "
              "sill to the street. Keep the slope 1:%g with a landing every %.2f m of rise: it is the step-free route "
              "in. The layout picks the riser count nearest each station's street." % (hand, n, rise, SL.RAMP_SLOPE,
                                                                                   SL.RAMP_SEG_RISE))
    return p


def mirror_y(p):
    """Mirror a piece across y = 0 (the other hand), fixing the face winding the mirror turns inside out."""
    import bmesh
    for v in p.b.bm.verts:
        v.co.y = -v.co.y
    bmesh.ops.reverse_faces(p.b.bm, faces=list(p.b.bm.faces))
    p.cols = [((c[0], -c[1], c[2]), h) for c, h in p.cols]
    p.gates = [((g[0][0], -g[0][1], g[0][2]), g[1], g[2], -(g[3] if len(g) > 3 else 0.0)) for g in p.gates]
    p.lifts = [((q[0], -q[1], q[2]),) + tuple(rest) for q, *rest in p.lifts]
    p.hulls = [[(q[0], -q[1], q[2]) for q in h] for h in p.hulls]
    # a door's arrow flips with the piece, and so does which way a single leaf runs (right and left swap in a mirror)
    p.doors = [((q[0], -q[1], q[2]), (d[0], -d[1]), w, h, st, -sd) for q, d, w, h, st, sd in p.doors]
    # a fixture turned by yaw is reflected by 180 - yaw (its own mirror image is not available: it keeps its hand)
    p.props = [(n, (q[0], -q[1], q[2]), (180.0 - yaw) % 360.0, c) for n, q, yaw, c in p.props]


def open_air_pieces():
    out = [fence()]
    for w in WIDTHS:
        out += [platform(w), shed(w), end_fence(w), building(w, "L"), building(w, "R")]
    out += [f(n, h) for f in (entry, entry_out) for n in range(SL.ENTRY_N[0], SL.ENTRY_N[1] + 1) for h in ("L", "R")]
    return out


# ── the pieces of the GROUND HUB (橋上駅) ────────────────────────────────────────────────────────────────────────────
# Every cap piece's origin is at BED level (the track's own height) at the centre of what it spans across; X along the
# track, CAP_LEN long; the airbridge concourse floor's top at AF.
CAP_SW_SIDE = SL.CAP_SW_SIDE    # a side platform's stair (and lift) down from the concourse, against the cap wall
CAP_SW_ISLAND = SL.CAP_SW_ISLAND  # an island platform's stair (and lift), on its centre line
RAIL_H = 1.1                    # a railing's height


def lift_shaft(p, x0, x1, y0, y1, stops, cut_y=None):
    """A lift shaft over the square (x0..x1, y0..y1): glass walls between metal corner posts from the low stop to
    LIFT_HEAD over the top one, a DOOR OPENING in both X faces (along the track, never the rail side) at every stop,
    and the `LIFT_` Empty world.Elevator builds the car from. Solid everywhere but the openings, so nobody walks or
    falls into the shaft; the landing doors in the openings are the runtime's."""
    t, dh = SL.LIFT_WALL_T, SL.LIFT_DOOR_H
    dw = SL.lift_door_w(y1 - y0 - 2 * t)
    zb, zt = stops[0] - 0.05, stops[-1] + SL.LIFT_HEAD
    yc = (y0 + y1) / 2
    for ya, yb in ((y0, y0 + t), (y1 - t, y1)):                      # the two faces toward the track / the wall
        p.solid((x0, ya, zb), (x1, yb, zt), "MI_GlassClear")
    for xa, xb in ((x0, x0 + t), (x1 - t, x1)):                      # the two DOOR faces
        p.solid((xa, y0, zb), (xb, yc - dw / 2, zt), "MI_PaintedMetal")
        p.solid((xa, yc + dw / 2, zb), (xb, y1, zt), "MI_PaintedMetal")
        z = zb
        for sz in stops:
            if sz > z + 1e-6:
                p.solid((xa, yc - dw / 2, z), (xb, yc + dw / 2, sz), "MI_GlassClear")
            z = sz + dh
        p.solid((xa, yc - dw / 2, z), (xb, yc + dw / 2, zt), "MI_GlassClear")
        for sz in stops:                                             # the door surround and the call panel
            p.b.box((xa - 0.02, yc - dw / 2 - 0.12, sz), (xb + 0.02, yc - dw / 2, sz + dh + 0.12), "MI_PlasticDark")
            p.b.box((xa - 0.02, yc + dw / 2, sz), (xb + 0.02, yc + dw / 2 + 0.12, sz + dh + 0.12), "MI_PlasticDark")
            p.b.box((xa - 0.02, yc - dw / 2, sz + dh), (xb + 0.02, yc + dw / 2, sz + dh + 0.12), "MI_PlasticDark")
            p.b.box((xa - 0.03, yc + dw / 2 + 0.2, sz + 1.0), (xb + 0.03, yc + dw / 2 + 0.32, sz + 1.25), "MI_Sign")
    for cx in (x0, x1 - 0.08):
        for cy in (y0, y1 - 0.08):
            p.b.box((cx, cy, zb), (cx + 0.08, cy + 0.08, zt), "MI_PaintedMetal")
    p.solid((x0, y0, zt), (x1, y1, zt + 0.2), "MI_PaintedMetal")
    p.lifts.append((((x0 + x1) / 2, yc, stops[0]), x1 - x0 - 2 * t, y1 - y0 - 2 * t, stops[-1] - stops[0], dw, dh))


def stair_rail(p, runs, y, collide=True):
    """A BALUSTRADE along one long side of a stair (user, 2026-09-27: a fence on both sides of every stair), in the
    plane y: a glass lower panel and a handrail RAIL_H over the treads, stepped with the flight, and one collider per
    run so nobody steps off the side. `runs` = [(xa, za, xb, zb)], xa < xb: a flight's or a landing's two ends and
    the tread height at each."""
    for xa, za, xb, zb in runs:
        n = max(1, int(round((xb - xa) / SL.STAIR_RUN)))
        for k in range(n):
            x0 = xa + (xb - xa) * k / n
            x1 = xa + (xb - xa) * (k + 1) / n
            z = za + (zb - za) * (k + 0.5) / n
            p.b.box((x0, y - 0.02, z), (x1, y + 0.02, z + 0.85), "MI_GlassClear")
            p.b.box((x0, y - 0.03, z + RAIL_H - 0.05), (x1, y + 0.03, z + RAIL_H), "MI_PaintedMetal")
        for x, z in ((xa, za), (xb, zb)):
            p.b.box((x - 0.03, y - 0.03, z), (x + 0.03, y + 0.03, z + RAIL_H), "MI_PaintedMetal")
        if collide:
            p.col((xa, y - 0.03, min(za, zb)), (xb, y + 0.03, max(za, zb) + RAIL_H))


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


def slab_with_holes(p, x0, x1, y0, y1, z0, z1, holes, mat="MI_ConcreteSmooth", collide=True):
    """A slab over (x0..x1, y0..y1) with every hole (hx0, hx1, hy0, hy1) cut out: sliced along x at the holes' ends,
    each slice solid across y except where a hole covers it."""
    xs = sorted({x0, x1} | {v for h in holes for v in (h[0], h[1]) if x0 < v < x1})
    for xa, xb in zip(xs, xs[1:]):
        xm = (xa + xb) / 2
        cuts = sorted((max(h[2], y0), min(h[3], y1)) for h in holes if h[0] <= xm <= h[1])
        y = y0
        for ca, cb in cuts:
            if ca > y + 1e-6:
                p.solid((xa, y, z0), (xb, ca, z1), mat, collide)
            y = max(y, cb)
        if y1 > y + 1e-6:
            p.solid((xa, y, z0), (xb, y1, z1), mat, collide)


def cap_top(p, w, openings=()):
    """The cap's upper storey over a band `w` wide: the concourse floor (with each of `openings` (x0, x1, y0, y1) cut
    out, for a stair or a lift shaft), the roof, the two end walls (glazed) from the concourse's soffit up, and a
    light strip under the soffit."""
    L = SL.CAP_LEN
    z0, z1 = SL.AF - SL.AF_T, SL.AF
    y0, y1 = -w / 2, w / 2
    slab_with_holes(p, -L / 2, L / 2, y0, y1, z0, z1, list(openings))
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
    wall (hand L: the track on -Y, the wall on +Y), a balustrade along the stair's open side (a handrail on the wall's),
    the LIFT beside it (LIFT_GAP beyond the stair's top end, the stair's width square), and two columns."""
    p = Piece("GH_CapPlatform_%s_%s" % (wname(w), hand), "ground_hub")
    sw = CAP_SW_SIDE
    xb = SL.CAP_STAIR_X
    xt = stair_top(xb, SL.AF - SL.PLATFORM_H)
    y0, y1 = w / 2 - sw, w / 2
    stair(p, xt, xb, y0, y1, SL.PLATFORM_H, SL.AF)
    lx0, lx1 = SL.hub_lift(sw)
    cap_top(p, w, [(xt, xb + 0.3, y0, y1), (lx0, lx1, y0, y1)])
    lift_shaft(p, lx0, lx1, y0, y1, (SL.PLATFORM_H, SL.AF))
    stair_rail(p, [(xt, SL.AF, xb, SL.PLATFORM_H)], y0 - 0.03)
    stair_rail(p, [(xt, SL.AF, xb, SL.PLATFORM_H)], y1 - 0.05, collide=False)
    railing(p, (xt, y0 - 0.05, SL.AF), (xb + 0.3, y0, SL.AF))
    railing(p, (xb + 0.3, y0 - 0.05, SL.AF), (xb + 0.35, y1, SL.AF))
    for x in (-11.0, 11.0):
        p.solid((x - 0.25, w / 2 - 0.85, SL.PLATFORM_H), (x + 0.25, w / 2 - 0.35, SL.AF - SL.AF_T), "MI_PaintedMetal")
    if hand == "R":
        mirror_y(p)
    p.note = ("The cap's bay over a side platform (hand %s): the concourse (top %.2f m over the bed) with the stair "
              "down to the platform against the cap wall, and the LIFT beside it (LIFT_0: doors on its X faces at the "
              "platform and the concourse). Nothing below %.2f m may reach past the platform's track edge (-Y face for "
              "L): the train passes under the concourse." % (hand, SL.AF, SL.AF - SL.AF_T))
    return p


def cap_island(w):
    p = Piece("GH_CapIsland_%s" % wname(w), "ground_hub")
    sw = CAP_SW_ISLAND
    xb = SL.CAP_STAIR_X
    xt = stair_top(xb, SL.AF - SL.PLATFORM_H)
    stair(p, xt, xb, -sw / 2, sw / 2, SL.PLATFORM_H, SL.AF)
    lx0, lx1 = SL.hub_lift(sw)
    cap_top(p, w, [(xt, xb + 0.3, -sw / 2, sw / 2), (lx0, lx1, -sw / 2, sw / 2)])
    lift_shaft(p, lx0, lx1, -sw / 2, sw / 2, (SL.PLATFORM_H, SL.AF))
    for sg in (-1.0, 1.0):
        stair_rail(p, [(xt, SL.AF, xb, SL.PLATFORM_H)], sg * (sw / 2 + 0.03))
        a, b = sorted((sg * sw / 2, sg * (sw / 2 + 0.05)))
        railing(p, (xt, a, SL.AF), (xb + 0.3, b, SL.AF))
    railing(p, (xb + 0.3, -sw / 2, SL.AF), (xb + 0.35, sw / 2, SL.AF))
    for x in (-11.0, 11.0):
        p.solid((x - 0.3, -0.3, SL.PLATFORM_H), (x + 0.3, 0.3, SL.AF - SL.AF_T), "MI_PaintedMetal")
    p.note = ("The cap's bay over an island platform: the stair down on the platform's centre line (a balustrade each "
              "side), the LIFT beside it on the same line, columns beside them.")
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


def annex(hand, large=False):
    """The ground hub's ENTRANCE ANNEX, against the cap wall (hand L: the cap on -Y, the street on +Y). The street door
    in the +Y face; the FARE LINE along X between the unpaid strip (+Y) and the paid strip (-Y, next to the cap), its
    gate lanes (ANNEX_GATES) beside the SERVICE COUNTER, which stands on the line out to the +X end wall. The paid
    strip: a stair up to a MEZZANINE landing at the concourse level (it meets the cap wall's opening), the lift beside
    the stair, and under the landing a RESTROOM BLOCK facing the walkway. The unpaid strip: the other restroom block and
    the ticket / ATM / vending machines against the street wall. Origin: footprint centre at bed (floor) level."""
    p = Piece("GH_%s_%s" % ("AnnexLarge" if large else "Annex", hand), "ground_hub")
    L, D, top, t = SL.CAP_LEN, SL.ANNEX_D, SL.ROOF + SL.ROOF_T, 0.3
    y0, y1 = -D / 2, D / 2
    yg = y0 + SL.ANNEX_PAID
    x0, x1 = -L / 2, L / 2
    p.solid((x0, y0, -SL.PLINTH), (x1, y1, 0), "MI_ConcreteSmooth")
    p.b.box((x0, y0, 0), (x1, y1, 0.01), "MI_Terrazzo")
    d0, d1 = SL.ANNEX_DOOR_LARGE if large else SL.ANNEX_DOOR
    h = SL.SHUTTER_H
    p.solid((x0, y1 - t, 0), (d0, y1, top), "MI_Plaster")
    p.solid((d1, y1 - t, 0), (x1, y1, top), "MI_Plaster")
    p.solid((d0, y1 - t, h), (d1, y1, top), "MI_Plaster")
    shutter(p, Frame(d0, y1, 1.0, 0.0, 0.0, -1.0), 0.0, d1 - d0, SL.LARGE_BAYS if large else SL.DOOR_BAYS, h, t,
            posts=False)
    p.b.box((max(x0, d0 - 1.0), y1, h + 0.55), (min(x1, d1 + 1.0), y1 + 0.08, h + 1.15), "MI_Sign")
    for sx in (-1.0, 1.0):
        xa, xb = sorted((sx * L / 2, sx * (L / 2 - t)))
        if large and sx > 0:
            # a LARGE hub's +X end wall is its STORE's front (user, 2026-09-28): solid along the paid strip and the
            # service counter, glazed with a sliding glass door along the unpaid hall -- the store's ONLY opening
            ya = y0 + SL.ANNEX_PAID + SL.COUNTER_L / 2 + 0.3
            p.solid((xa, y0, 0), (xb, ya, top), "MI_Plaster")
            h = store_front(p, Frame(xa, ya, 0.0, 1.0, 1.0, 0.0), 0.0, y1 - t - ya, top, t)
            p.b.box((xa - 0.08, ya, h + 0.1), (xa, y1 - t, h + 0.55), "MI_Sign")
        else:
            p.solid((xa, y0, 0), (xb, y1, top), "MI_Plaster")
    p.solid((x0, y0, SL.ROOF), (x1, y1, top), "MI_Corrugated")
    # the stair up and the mezzanine landing it arrives on (paid strip, against the cap wall)
    xb = SL.ANNEX_STAIR_X
    xt = stair_top(xb, SL.AF)
    sw = 2.4
    stair(p, xt, xb, y0, y0 + sw, 0.0, SL.AF)
    # the lift beside it (street -> concourse, inside the paid strip), LIFT_GAP beyond the stair's top end
    lx1 = xt - SL.LIFT_GAP
    lx0 = lx1 - sw
    slab_with_holes(p, x0, xt, y0, yg, SL.AF - SL.AF_T, SL.AF, [(lx0, lx1, y0, y0 + sw)])
    lift_shaft(p, lx0, lx1, y0, y0 + sw, (0.0, SL.AF))
    stair_rail(p, [(xt, SL.AF, xb, 0.0)], y0 + sw + 0.03)
    stair_rail(p, [(xt, SL.AF, xb, 0.0)], y0 + 0.05, collide=False)
    p.b.box((x0, y0, SL.AF), (xt, yg, SL.AF + 0.01), "MI_Terrazzo")
    railing(p, (x0 + t, yg - 0.05, SL.AF), (xt, yg, SL.AF))
    railing(p, (xt, y0 + sw, SL.AF), (xt + 0.05, yg, SL.AF))
    for xl in (x0 + 4.0, x0 + 12.0):                                     # lights under the mezzanine
        p.b.box((xl - 1.0, y0 + 5.6, SL.AF - SL.AF_T - 0.05), (xl + 1.0, y0 + 6.0, SL.AF - SL.AF_T), "MI_Light")
    # the paid restroom block, at the -X end under the mezzanine, its back on the cap wall, open to the walkway (+Y)
    wc_top = SL.BUILDING_H - 0.02
    restroom_block(p, Frame(x0 + t, y0 + SL.WC_D, 1.0, 0.0, 0.0, -1.0), wc_top)
    # the fare line along X at yg: gate cabinets and lanes centred on ANNEX_GATES, a railing from the -X end wall to
    # them, and the SERVICE COUNTER straddling the line from their +X end to the +X end wall (its window each side)
    lane, cab = SL.GATE_W, 0.25
    xg = SL.ANNEX_GATES
    cabs = [xg - lane - cab, xg, xg + lane + cab]
    for cx in cabs:
        p.solid((cx - cab / 2, yg - 0.6, 0), (cx + cab / 2, yg + 0.6, 1.0), "MI_PlasticWhite")
    lo_e, hi_e = cabs[0] - cab / 2, cabs[-1] + cab / 2
    railing(p, (x0 + t, yg - 0.03, 0.0), (lo_e, yg + 0.03, 0.0))
    for cx in (xg - (lane + cab) / 2, xg + (lane + cab) / 2):
        # the fare line runs along X here, the unpaid side is +Y (the street): yaw 90 (a gate's default is +X, the
        # open-air building's). Without it the flaps stood edge-on in the lane and the probe walked through them
        p.gates.append(((cx, yg, 0.0), lane, 1.0, 90.0))
    xc0 = x1 - t - SL.WC_D
    assert xc0 >= hi_e - 1e-6, (xc0, hi_e)
    railing(p, (hi_e, yg - 0.03, 0.0), (xc0, yg + 0.03, 0.0))
    service_counter(p, Frame(xc0, yg + SL.COUNTER_L / 2, 0.0, -1.0, 1.0, 0.0), wc_top)
    # the unpaid restroom block against the street wall at the -X end, open to the hall (-Y); the machines beside it
    restroom_block(p, Frame(x0 + t, y1 - SL.WC_D, 1.0, 0.0, 0.0, 1.0), wc_top)
    machines(p, Frame(x0 + t + SL.WC_L + 0.6, y1 - t, 1.0, 0.0, 0.0, -1.0))
    p.b.box((x0 + 1.0, yg + 1.8, SL.ROOF - 0.05), (x1 - 1.0, yg + 2.2, SL.ROOF), "MI_Light")
    if hand == "R":
        mirror_y(p)
    p.note = ("A ground hub's entrance annex (hand %s: the cap wall on %s%s). The street entrance is a roller-shutter "
              "opening in the outer face (open all day: keep its bays clear); the "
              "GATE_ Empties are the ticket-gate lanes on the fare line (their arrows point to the street side); the "
              "service counter closes the line to the end wall. Paid side: the stair and lift up to the mezzanine "
              "landing (it must meet the cap wall's opening at the concourse level, %.2f m) and a restroom block under "
              "it. Unpaid side: a restroom block and the machines. The GH_Entry_* piece outside the door brings the "
              "stair + slope down where the street is lower." % (hand, "-Y" if hand == "L" else "+Y",
                                                                 "; a LARGE hub's: the six-bay entrance, and its +X end "
                                                                 "wall the store's glass front" if large else "", SL.AF))
    return p


def annex_store(hand):
    """A LARGE ground hub's ONE STORE (user, 2026-09-28), past the annex's +X end along the track: ANNEX_STORE long, the
    annex's depth, its floor the annex floor. It opens ONLY into the annex's unpaid hall -- through the sliding glass
    door in GH_AnnexLarge's +X end wall, so it has no wall of its own on that side -- and shows display glass to the
    street (no door there). Origin: footprint centre at floor level; hand L has the platform side on -Y."""
    p = Piece("GH_AnnexStore_%s" % hand, "ground_hub")
    L, D, top, t = SL.ANNEX_STORE, SL.ANNEX_D, SL.SHOP_H, 0.2
    x0, x1, y0, y1 = -L / 2, L / 2, -D / 2, D / 2
    p.solid((x0, y0, -SL.PLINTH - 1.5), (x1, y1, 0.0), "MI_ConcreteSmooth")
    p.b.box((x0, y0, 0.0), (x1, y1, 0.01), "MI_Terrazzo")
    p.solid((x0, y0, 0.0), (x1, y0 + t, top), "MI_Plaster")                     # the back, toward the platform
    p.solid((x1 - t, y0, 0.0), (x1, y1, top), "MI_Plaster")                     # the outer end
    # the street side: DISPLAY glass between piers over a kick wall, no door
    p.solid((x0, y1 - t, 0.0), (x1, y1, 0.6), "MI_Plaster")
    p.solid((x0, y1 - t, 2.8), (x1, y1, top), "MI_Plaster")
    piers = [x0, -0.1, x1 - t]
    for xp in piers:
        p.solid((xp, y1 - t, 0.6), (xp + t, y1, 2.8), "MI_Plaster")
    for a0, a1 in zip(piers, piers[1:]):
        p.solid((a0 + t, y1 - 0.06, 0.6), (a1, y1 - 0.02, 2.8), "MI_GlassClear")
    p.b.box((x0 + 0.5, y1, 2.95), (x1 - 0.5, y1 + 0.08, 3.5), "MI_Sign")
    p.solid((x0, y0, top - 0.3), (x1, y1, top), "MI_ConcreteSmooth")
    p.b.box((x0, y0, top), (x1, y1 + 0.1, top + 0.02), "MI_RoofSlate")
    # inside: shelving along the back and the outer end, two gondolas, the counter by the hall door
    p.solid((x0 + 0.3, y0 + t, 0.0), (x1 - t - 0.3, y0 + t + 0.5, 1.9), "MI_Wood")
    p.b.box((x0 + 0.35, y0 + t + 0.02, 0.9), (x1 - t - 0.35, y0 + t + 0.5, 1.6), "MI_Goods")
    p.solid((x1 - t - 0.5, y0 + 1.5, 0.0), (x1 - t, y1 - 1.5, 1.9), "MI_Wood")
    for yg in (-2.5, 1.0):
        p.solid((x0 + 2.5, yg, 0.0), (x1 - 2.5, yg + 0.9, 1.5), "MI_Wood")
        p.b.box((x0 + 2.55, yg + 0.05, 0.5), (x1 - 2.55, yg + 0.85, 1.4), "MI_Goods")
    p.solid((x0 + 0.4, y1 - 3.2, 0.0), (x0 + 1.0, y1 - 1.4, 1.0), "MI_PlasticWhite")    # the counter
    for yl in (-3.0, 3.0):
        p.b.box((-2.0, yl - 0.2, top - 0.35), (2.0, yl + 0.2, top - 0.3), "MI_Light")
    if hand == "R":
        mirror_y(p)
    p.note = ("A large ground hub's store (hand %s), past the annex's +X end. Its only way in is the sliding glass door "
              "in GH_AnnexLarge's +X end wall, from the UNPAID hall: keep this piece's -X side open to that wall, and "
              "keep the paid strip's side of it solid. The street side is display glass (no door)." % hand)
    return p


def hub_widths():
    import island_rail_layout as R
    R.use_layout("tokyo_straight")
    sts = {n: st for n, st in SL.stations(R.analyse()).items() if st.form == "ground_hub"}
    return SL.kit_widths(sts)


def ground_hub_pieces():
    ws = hub_widths()
    out = [cap_lane(), cap_wall(False), cap_wall(True)]
    out += [f(h) for h in ("L", "R") for f in (annex, lambda h_: annex(h_, True), annex_store)]
    # the entry (stair + smooth slope) outside an annex door whose street is lower: the open-air entry, this file's own
    # copy; the wide one spans a large hub's six-bay opening
    out += [entry(n, h, "GH", "ground_hub") for n in range(SL.ENTRY_N[0], SL.ENTRY_N[1] + 1) for h in ("L", "R")]
    out += [entry(n, h, "GH", "ground_hub", SL.LARGE_ENTRANCE_W, "EntryWide")
            for n in range(SL.ENTRY_N[0], SL.ENTRY_N[1] + 1) for h in ("L", "R")]
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


# ── the pieces of the ELEVATED HUB (高架駅) ───────────────────────────────────────────────────────────────────────
# Every piece's origin is on the LANE's centre line at BED level (the viaduct's own height); X along the track; hand L
# builds the +Y (left) side, R is its mirror. The F1 floor lies EH_LIFT below the origin. The rail's deck (+-EH_DECK_HALF,
# EH_DECK_T deep) is the rail record's, not a piece: the station meets it at its edges.
def eh_dims(w):
    """(p0, p1, b1, w1, wo): the platform's track edge, its outer edge, the stair band's outer edge (the rail wall's
    inner face), the wall's outer face and the F1 wing's outer face, across from the lane."""
    p0 = SL.TRACK_HALF + SL.PLATFORM_EDGE
    p1 = p0 + w
    b1 = p1 + SL.EH_SW
    w1 = b1 + SL.EH_WALL_T
    return p0, p1, b1, w1, w1 + SL.EH_WING


def ceiling(p, x0, x1, y0, y1, holes=()):
    """The F1 hall's lowered ceiling (visual only: nobody reaches it) at EH_CEIL over the street, with light panels."""
    z = -SL.EH_LIFT + SL.EH_CEIL
    slab_with_holes(p, x0, x1, y0, y1, z, z + 0.05, list(holes), "MI_Plaster", collide=False)
    if y1 - y0 > 1.5 and x1 - x0 > 2.0 and not any(h[0] - 0.5 < (x0 + x1) / 2 < h[1] + 0.5 for h in holes):
        yc = (y0 + y1) / 2
        p.b.box((x0 + 0.8, yc - 0.3, z - 0.03), (x1 - 0.8, yc + 0.3, z), "MI_Light")


def eh_side(w, hand, role):
    """One 5 m module of a side's structure: the roof slab under the platform (from the deck's edge), the stair band's
    slab at platform level, the outer rail wall, and the shed over platform and band on a column on the platform and on
    the wall. At F1 the rail wall's line is the paid box's long side: a COLUMN at the module's +X end under a beam at
    the ceiling (the fare line in it is `EH_FareSide*`), and the band's ceiling. Role 'stair': the EH_STAIR_LEN piece
    whose band has the stair up from F1 in it, the rail wall coming down to the floor (the stair's own wall); role
    'lift': the band holds the lift."""
    name = {"plain": "EH_Side_%s_%s", "stair": "EH_SideStair_%s_%s", "lift": "EH_SideLift_%s_%s"}[role] % (wname(w), hand)
    p = Piece(name, "elevated_hub")
    L = SL.EH_STAIR_LEN if role == "stair" else MODULE
    x0, x1 = -L / 2, L / 2
    p0, p1, b1, w1, _wo = eh_dims(w)
    hp, dt, lift = SL.PLATFORM_H, SL.EH_DECK_T, SL.EH_LIFT
    sh = hp + SL.SHED_CLEAR
    zc = -lift + SL.EH_CEIL
    p.solid((x0, SL.EH_DECK_HALF - 0.1, -dt), (x1, p1, 0.0), "MI_ConcreteSmooth")          # under the platform
    if role == "stair":
        steps, x_top = SL.eh_stairs()
        xb = SL.EH_STAIR_FOOT
        p.solid((x0, p1, -dt), (x_top, b1, hp), "MI_ConcreteSmooth")                        # the arrival floor
        p.solid((xb + 0.3, p1, -dt), (x1, b1, hp), "MI_ConcreteSmooth")
        p.b.box((x0, p1, hp), (x_top, b1, hp + 0.01), "MI_Terrazzo")
        p.b.box((xb + 0.3, p1, hp), (x1, b1, hp + 0.01), "MI_Terrazzo")
        for xf, zt in steps:
            p.solid((x_top, p1, -lift), (xf, b1, zt), "MI_ConcreteSmooth")
            p.b.box((xf - 0.04, p1, zt), (xf, b1, zt + 0.004), "MI_PaintYellow")
        railing(p, (x_top, p1 - 0.05, hp), (xb + 0.3, p1, hp))              # the platform's edge over the stair well
        railing(p, (xb + 0.3, p1, hp), (xb + 0.35, b1, hp))
        # the balustrades (user, 2026-09-27): on the side open to the F1 hall, up to the hall's ceiling, where a
        # BULKHEAD (to the platform's slab) takes over as the stairwell's wall; a handrail along the rail wall
        runs = eh_stair_runs(steps, x_top)
        stair_rail(p, clip_runs(runs, zc), p1 + 0.03)
        stair_rail(p, runs, b1 - 0.05, collide=False)
        p.solid((x0, p1, zc), (xb + 0.3, p1 + 0.1, -dt), "MI_Plaster")
        ceiling(p, xb + 0.3, x1, p1, b1)
        # the rail wall comes down to the floor along the stair
        p.solid((x0, b1, -lift - SL.PLINTH), (x1, w1, hp + 1.1), "MI_Plaster")
    else:
        if role == "lift":
            lx0, lx1 = SL.eh_lift()
            slab_with_holes(p, x0, x1, p1, b1, -dt, hp, [(lx0, lx1, p1, b1)])
            for xa, xb_ in ((x0, lx0), (lx1, x1)):
                p.b.box((xa, p1, hp), (xb_, b1, hp + 0.01), "MI_Terrazzo")
            lift_shaft(p, lx0, lx1, p1, b1, (-lift, hp))
            ceiling(p, x0, x1, p1, b1, [(lx0, lx1, p1, b1)])
        else:
            p.solid((x0, p1, -dt), (x1, b1, hp), "MI_ConcreteSmooth")
            p.b.box((x0, p1, hp), (x1, b1, hp + 0.01), "MI_Terrazzo")
            ceiling(p, x0, x1, p1, b1)
        # the rail wall from the ceiling's beam up; at F1 a column at the module's +X end
        p.solid((x0, b1, zc), (x1, w1, hp + 1.1), "MI_Plaster")
        p.solid((x1 - SL.EH_COL, b1, -lift), (x1, w1, zc), "MI_ConcreteSmooth")
    zg = hp + 1.1
    p.b.box((x0, b1, zg), (x1, w1, sh), "MI_GlassClear")
    p.col((x0, b1, zg), (x1, w1, sh))
    p.b.box((x0, b1, sh - 0.3), (x1, w1, sh), "MI_PaintedMetal")                              # the wall's top beam
    # the shed: roof over platform and band, a column on the platform's back half each module
    p.b.box((x0, p0 + 0.2, sh), (x1, w1, sh + SL.SHED_T), "MI_Corrugated")
    p.b.box((x0, p0 + 0.2, sh - 0.08), (x1, p0 + 0.28, sh + SL.SHED_T), "MI_PaintedMetal")
    yc = p1 - 0.6
    for k in range(int(round(L / MODULE))):
        xc = x0 + MODULE * (k + 0.5)
        p.solid((xc - 0.14, yc - 0.14, hp), (xc + 0.14, yc + 0.14, sh), "MI_PaintedMetal")
        p.b.box((xc - 1.0, p0 + 0.8, sh - 0.05), (xc + 1.0, p0 + 1.0, sh), "MI_Light")
    if hand == "R":
        mirror_y(p)
    p.note = ("An elevated hub's side structure (hand %s, %s), origin on the LANE centre at bed level. The roof slab "
              "starts at the rail deck's edge (%.1f m) and carries the platform; nothing may come nearer the track than "
              "the platform edge (%.2f m) below %.1f m (the gauge). At F1 the rail wall's line is the paid box's long "
              "side: a column at the module's +X end under a beam at the ceiling (%.1f m over the street)."
              % (hand, role, SL.EH_DECK_HALF, SL.TRACK_HALF + SL.PLATFORM_EDGE, SL.GAUGE_H[1], SL.EH_CEIL))
    return p


EH_SHOP_D = 2.4                 # an elevated hub's hall-facing shop, deep from the wing's outer wall (a 2.3 m walkway
                                # stays before it, user 2026-09-27: "hall-facing")


def eh_wing(w, hand, kind):
    """The F1 WING past the rail wall (hand L on +Y): the unpaid hall along the long side -- its floor, its outer wall,
    its roof and ceiling. Kind 'shop' (one 5 m module; the large hubs' shops along the side, user 2026-09-27): a shop
    against the outer wall, its glass front and sliding door on the hall. Kind 'machines' (the module beside each end fare
    line): the ticket machines, an ATM and vending machines against a blank outer wall, facing the long side's gate
    bank across the hall. Kind 'entrance' (THREE modules): the station's six-bay street entrance, a roller-shutter
    opening in the outer wall, open all day."""
    p = Piece("EH_%s_%s_%s" % ({"entrance": "WingEntrance", "shop": "WingShop", "machines": "WingMachines"}[kind],
                               wname(w), hand), "elevated_hub")
    L = MODULE * (SL.EH_ENTRANCE_MODULES if kind == "entrance" else 1)
    x0, x1 = -L / 2, L / 2
    _p0, _p1, _b1, w1, wo = eh_dims(w)
    z, t, top = -SL.EH_LIFT, SL.EH_WALL_T, -SL.EH_LIFT + SL.EH_WING_H
    p.solid((x0, w1, z - SL.PLINTH), (x1, wo, z), "MI_ConcreteSmooth")
    p.b.box((x0, w1, z), (x1, wo - t, z + 0.01), "MI_Terrazzo")
    if kind == "entrance":
        d = SL.LARGE_ENTRANCE_W / 2
        h = SL.SHUTTER_H
        p.solid((x0, wo - t, z - SL.PLINTH), (-d, wo, top), "MI_Plaster")
        p.solid((d, wo - t, z - SL.PLINTH), (x1, wo, top), "MI_Plaster")
        p.solid((-d, wo - t, z + h), (d, wo, top), "MI_Plaster")
        shutter(p, Frame(-d, wo, 1.0, 0.0, 0.0, -1.0, z), 0.0, 2 * d, SL.LARGE_BAYS, h, t, posts=False)
        p.b.box((-d, wo, z + h + 0.55), (d, wo + 0.08, z + h + 1.15), "MI_Sign")
    elif kind == "machines":
        p.solid((x0, wo - t, z - SL.PLINTH), (x1, wo, top), "MI_Plaster")
        run = machines(p, Frame(-2.4, wo - t, 1.0, 0.0, 0.0, -1.0, z))
        assert run - 0.1 <= L - 0.1, run
        p.b.box((-2.4, wo - t - 0.02, z + 2.1), (2.4, wo - t, z + 2.5), "MI_Sign")          # 「きっぷうりば」 board
    else:
        p.solid((x0, wo - t, z - SL.PLINTH), (x1, wo, top), "MI_Plaster")
        shop_unit(p, Frame(x0, wo - t - EH_SHOP_D, 1.0, 0.0, 0.0, 1.0, z), L, EH_SHOP_D, SL.EH_CEIL - 0.02,
                  back=False)
    p.solid((x0, w1, top - 0.3), (x1, wo, top), "MI_ConcreteSmooth")
    p.b.box((x0, w1, top), (x1, wo + 0.1, top + 0.02), "MI_RoofSlate")
    ceiling(p, x0, x1, w1, wo - t)
    if hand == "R":
        mirror_y(p)
    p.note = ("An elevated hub's F1 wing (hand %s, %s): the unpaid hall along the long side, %.1f m past the rail wall, "
              "its roof %.1f m over the street. %s" % (
                  hand, kind, SL.EH_WING, SL.EH_WING_H,
                  {"entrance": "One of the station's street entrances: one %.1f m roller-shutter opening, framed "
                               "only at its sides, three modules long. Keep it clear." % SL.LARGE_ENTRANCE_W,
                   "shop": "A shop against the outer wall, %.1f m deep, its glass front and sliding door on the hall: keep "
                           "the walkway before it (the wing's hall)." % EH_SHOP_D,
                   "machines": "Keep the machines outside the paid area (this wing is unpaid)."}[kind]))
    return p


def eh_fare_side(w, hand, gate):
    """The paid box's LONG-SIDE fare line in the rail wall's line at F1 (hand L on +Y), one 5 m module: a railing
    along it (to the column at the +X end), or in the 'gate' one a GATE BANK in the -X half (the box's side of a
    corner module), the unpaid side toward the wing (+Y)."""
    p = Piece("EH_FareSide%s_%s_%s" % ("Gate" if gate else "", wname(w), hand), "elevated_hub")
    L = MODULE
    _p0, _p1, b1, w1, _wo = eh_dims(w)
    z, yc = -SL.EH_LIFT, (b1 + w1) / 2
    if not gate:
        railing(p, (-L / 2, yc - 0.03, z), (L / 2 - SL.EH_COL, yc + 0.03, z))
    else:
        lane, cab = SL.GATE_W, SL.EH_SIDE_GATE_CAB
        cabs = [-0.05 - cab / 2 - k * (lane + cab) for k in range(SL.EH_SIDE_GATE_LANES + 1)]
        for cx in cabs:
            p.solid((cx - cab / 2, yc - 0.6, z), (cx + cab / 2, yc + 0.6, z + 1.0), "MI_PlasticWhite")
        for a, b in zip(cabs, cabs[1:]):
            p.gates.append((((a + b) / 2, yc, z), lane, 1.0, 90.0))
        if cabs[-1] - cab / 2 > -L / 2 + 0.05:
            railing(p, (-L / 2, yc - 0.03, z), (cabs[-1] - cab / 2, yc + 0.03, z))
    if hand == "R":
        mirror_y(p)
    p.note = ("The paid box's long-side fare line at F1 (hand %s)%s, in the rail wall's line (the column at the +X "
              "end is the side piece's). Keep it closed from end to end: the paid area leaks through any gap." %
              (hand, ": a gate bank in the -X half, GATE_ arrows toward the wing (the unpaid side)" if gate else ""))
    return p


def eh_stair_runs(steps, x_top):
    """The F1 -> platform stair's nosing line as balustrade runs [(xa, za, xb, zb)]: a sloped run per flight, a level
    one per landing (from `station_layout.eh_stairs`' steps, the lowest first, rising toward -x)."""
    pts = [(SL.EH_STAIR_FOOT, -SL.EH_LIFT)] + list(steps) + [(x_top, SL.PLATFORM_H)]
    runs, start = [], 0
    for i in range(1, len(pts)):
        dx = pts[i - 1][0] - pts[i][0]
        if dx > SL.STAIR_RUN + 1e-6:                    # a landing: close the flight, then a level run at its height
            if i - 1 > start:
                runs.append((pts[i - 1][0], pts[i - 1][1], pts[start][0], pts[start][1]))
            runs.append((pts[i][0], pts[i - 1][1], pts[i - 1][0], pts[i - 1][1]))
            start = i
    runs.append((pts[-1][0], pts[-1][1], pts[start][0], pts[start][1]))
    return runs


def clip_runs(runs, zmax):
    """The part of each run whose treads lie at or below zmax (a run crossing it is cut where it does)."""
    out = []
    for xa, za, xb, zb in runs:
        if min(za, zb) >= zmax:
            continue
        if max(za, zb) <= zmax:
            out.append((xa, za, xb, zb))
            continue
        t = (zmax - za) / (zb - za)
        xm = xa + (xb - xa) * t
        out.append((xm, zmax, xb, zb) if za > zmax else (xa, za, xm, zmax))
    return out


def eh_floor(w, gate, core=None, lanes=(0.0,)):
    """One 5 m module of F1: the floor across the whole building (wall to wall), columns under each deck's edges, and
    in the 'gate' module the FARE LINE across it (a bank of gate cabinets under each lane, GATE lanes between them, a
    railing to each wall; the unpaid side is +X) with ticket machines on the unpaid side. `lanes`: the lanes' centres
    across from the piece's origin (one lane at 0 for a one-lane hub; Central's three at -14, 0, +14)."""
    core = core or wname(w)
    p = Piece("EH_%s_%s" % ("FloorGate" if gate else "Floor", core), "elevated_hub")
    L = MODULE
    lo, hi = min(lanes), max(lanes)
    p1 = SL.TRACK_HALF + SL.PLATFORM_EDGE + w
    b1, w1 = p1 + SL.EH_SW, p1 + SL.EH_SW + SL.EH_WALL_T
    z = -SL.EH_LIFT
    p.solid((-L / 2, lo - w1, z - SL.PLINTH), (L / 2, hi + w1, z), "MI_ConcreteSmooth")
    p.b.box((-L / 2, lo - b1, z), (L / 2, hi + b1, z + 0.01), "MI_Terrazzo")
    # the ceiling under each lane's deck, out to the platform's outer edge on the building's two sides (the gap
    # between two decks is the island piece's)
    for c in lanes:
        ceiling(p, -L / 2, L / 2, c - (p1 if c == lo else SL.EH_DECK_HALF), c + (p1 if c == hi else SL.EH_DECK_HALF))
    if not gate:
        for c in lanes:
            for sg in (-1.0, 1.0):
                yc = c + sg * (SL.EH_DECK_HALF - 0.6)
                p.solid((-0.3, yc - 0.3, z), (0.3, yc + 0.3, -SL.EH_DECK_T), "MI_ConcreteSmooth")
    else:
        lane, cab = SL.GATE_W, 0.25
        n = SL.EH_GATE_LANES
        # the railing reaches the wing (w1) at both ends: the long-side fare lines meet it there
        edge = lo - w1
        for c in lanes:
            cabs = [c + (i - n / 2) * (lane + cab) for i in range(n + 1)]
            for cy in cabs:
                p.solid((-0.6, cy - cab / 2, z), (0.6, cy + cab / 2, z + 1.0), "MI_PlasticWhite")
            railing(p, (-0.03, edge, z), (0.03, cabs[0] - cab / 2, z))
            edge = cabs[-1] + cab / 2
            for a, b in zip(cabs, cabs[1:]):
                p.gates.append(((0.0, (a + b) / 2, z), lane, 1.0))
        # the SERVICE COUNTER (有人改札) straddles the line at its +Y end, stopping short of the long side's gate bank
        # in the rail wall's line; a railing each side of it closes the line (the machines are in the wings)
        yc1 = hi + b1 - SL.EH_COUNTER_WALL
        yc0 = yc1 - SL.WC_D
        assert yc0 > edge + 0.9, (yc0, edge)
        railing(p, (-0.03, edge, z), (0.03, yc0, z))
        service_counter(p, Frame(-SL.COUNTER_L / 2, yc0, 1.0, 0.0, 0.0, 1.0, z), SL.EH_CEIL - 0.02)
        railing(p, (-0.03, yc1, z), (0.03, hi + w1, z))
    p.note = ("An elevated hub's F1 module (%s%s). The floor's top is the street, %.2f m below the origin (the bed). "
              "%s" % ("the fare line" if gate else "plain", "" if len(lanes) == 1 else
                      ", %d lanes at %s m across" % (len(lanes), ", ".join("%g" % c for c in lanes)), SL.EH_LIFT,
                      "The GATE_ Empties are the ticket-gate lanes; +X is the unpaid (street-door) side; the service "
                      "counter closes the line at +Y." if gate else
                      "The columns carry the rail's decks over the station (the rail record puts no pier here)."))
    return p


def eh_end_wall(w, core=None, lanes=(0.0,)):
    """The F1 end wall at a platform end (the piece's +X face is the station's end), wall to wall, up to the decks'
    underside: the rail decks continue out over it."""
    core = core or wname(w)
    p = Piece("EH_EndWall_%s" % core, "elevated_hub")
    lo, hi = min(lanes), max(lanes)
    _p0, _p1, _b1, w1, wo = eh_dims(w)
    p.solid((-0.3, lo - w1, -SL.EH_LIFT - SL.PLINTH), (0.0, hi + w1, -SL.EH_DECK_T), "MI_Plaster")
    for ya, yb in ((lo - wo, lo - w1), (hi + w1, hi + wo)):          # across the wings, up to their roofs
        p.solid((-0.3, ya, -SL.EH_LIFT - SL.PLINTH), (0.0, yb, -SL.EH_LIFT + SL.EH_WING_H), "MI_Plaster")
    p.note = ("The F1 end wall, across the hall and both wings; its +X face is the station's end. It stops under the "
              "rail deck (the train runs on).")
    return p


def eh_island(wi, role):
    """One module of an ISLAND platform between two lanes (origin on its centre line at bed level, X along): the
    platform (both long faces track edges), the slab filling the gap between the two lanes' viaduct decks, the F1
    ceiling under that gap, and the shed on a row of columns on the centre line. Role 'stair' (EH_STAIR_LEN long): a
    stairwell on the centre line, the stair up from F1 in it (a balustrade on both open sides, a bulkhead above the
    F1 ceiling, a railing round the well at platform level); role 'lift': the lift on the centre line."""
    name = {"plain": "EH_Island_%s", "stair": "EH_IslandStair_%s", "lift": "EH_IslandLift_%s"}[role] % wname(wi)
    p = Piece(name, "elevated_hub")
    L = SL.EH_STAIR_LEN if role == "stair" else MODULE
    x0, x1 = -L / 2, L / 2
    hp, dt, lift = SL.PLATFORM_H, SL.EH_DECK_T, SL.EH_LIFT
    sh = hp + SL.SHED_CLEAR
    zc = -lift + SL.EH_CEIL
    g = wi / 2 - (SL.EH_DECK_HALF - SL.TRACK_HALF - SL.PLATFORM_EDGE)       # half the gap between the decks
    sw = SL.EH_ISLAND_SW
    holes, cols = [], [0.0]
    if role == "stair":
        steps, x_top = SL.eh_stairs()
        xb = SL.EH_STAIR_FOOT
        holes = [(x_top, xb + 0.3, -sw / 2, sw / 2)]
        cols = [x0 + 1.0]
        for xf, zt in steps:
            p.solid((x_top, -sw / 2, -lift), (xf, sw / 2, zt), "MI_ConcreteSmooth")
            p.b.box((xf - 0.04, -sw / 2, zt), (xf, sw / 2, zt + 0.004), "MI_PaintYellow")
        runs = eh_stair_runs(steps, x_top)
        for sg in (-1.0, 1.0):
            stair_rail(p, clip_runs(runs, zc), sg * (sw / 2 + 0.03))
            ya, yb = sorted((sg * sw / 2, sg * (sw / 2 + 0.1)))
            p.solid((x_top, ya, zc), (xb + 0.3, yb, -dt), "MI_Plaster")               # the bulkhead over the ceiling
            ya, yb = sorted((sg * sw / 2, sg * (sw / 2 + 0.05)))
            railing(p, (x_top, ya, hp), (xb + 0.3, yb, hp))                          # round the well
        railing(p, (xb + 0.3, -sw / 2, hp), (xb + 0.35, sw / 2, hp))
    elif role == "lift":
        lx0, lx1 = SL.eh_lift()
        holes = [(lx0, lx1, -sw / 2, sw / 2)]
        lift_shaft(p, lx0, lx1, -sw / 2, sw / 2, (-lift, hp))
        cols = [c for c in (x0 + 0.5, x1 - 0.5) if not lx0 - 0.3 < c < lx1 + 0.3][:1]
    slab_with_holes(p, x0, x1, -g - 0.1, g + 0.1, -dt, 0.0, holes)                   # between the decks
    slab_with_holes(p, x0, x1, -wi / 2, wi / 2, 0.0, hp, holes)                      # the platform
    for sg in (-1.0, 1.0):
        ye = sg * wi / 2
        a, b = sorted((ye, ye - sg * 0.08))
        p.b.box((x0, a, hp), (x1, b, hp + 0.004), "MI_PaintWhite")
        a, b = sorted((ye - sg * 0.8, ye - sg * 1.1))
        p.b.box((x0, a, hp), (x1, b, hp + 0.006), "MI_Tactile")
        a, b = sorted((ye, ye - sg * 0.02))
        p.b.box((x0, a, hp - 0.12), (x1, b, hp), "MI_PaintYellow")
    ceiling(p, x0, x1, -g, g, holes)
    # the shed: columns on the centre line (none over the well or the shaft), the roof inside the platform
    for xc in cols:
        p.solid((xc - 0.15, -0.15, hp), (xc + 0.15, 0.15, sh), "MI_PaintedMetal")
    p.b.box((x0, -wi / 2 + 0.2, sh), (x1, wi / 2 - 0.2, sh + SL.SHED_T), "MI_Corrugated")
    if role == "plain":
        p.b.box((x0, -0.8, sh - 0.3), (x1, 0.8, sh), "MI_PaintedMetal")
    for sg in (-1.0, 1.0):
        a, b = sorted((sg * (wi / 2 - 1.0), sg * (wi / 2 - 0.8)))
        p.b.box((-1.0, a, sh - 0.05), (1.0, b, sh), "MI_Light")
    p.note = ("An elevated hub's ISLAND platform module (%s), %.2f m wide, origin on its centre line at bed level: both "
              "long faces are track edges (%.2f m from each track centre). The slab under it fills the %.2f m gap "
              "between the two lanes' viaduct decks; nothing may come nearer a track than the platform edge below "
              "%.1f m (the gauge). %s" % (role, wi, SL.PLATFORM_EDGE, 2 * g, SL.GAUGE_H[1],
                                          "The stair and its well stay on the centre line, inside the gap." if role
                                          == "stair" else "The lift (LIFT_0) stays on the centre line." if role ==
                                          "lift" else ""))
    return p


def eh_restroom():
    """An elevated hub's RESTROOM BLOCK on F1 (PLAN.md step 6b), free-standing under a lane between its deck's column
    rows: origin at the block's footprint centre at BED level (its floor EH_LIFT below), WC_L along X, the open (door)
    face toward -Y. The station places two: one inside the paid box, one in the unpaid end hall."""
    p = Piece("EH_Restroom", "elevated_hub")
    restroom_block(p, Frame(-SL.WC_L / 2, -SL.WC_D / 2, 1.0, 0.0, 0.0, 1.0, -SL.EH_LIFT), SL.EH_CEIL - 0.02)
    p.note = ("An elevated hub's restroom block (men / women / accessible), free-standing on F1 under a lane: keep it "
              "inside %.2f m of its centre across (the deck's F1 columns stand at +-%.1f m from the lane) and no "
              "taller than the hall's ceiling (%.1f m over the floor). The doors face -Y." %
              (SL.WC_D / 2, SL.EH_DECK_HALF - 0.6, SL.EH_CEIL))
    return p


def elevated_hub_pieces():
    import island_rail_layout as R
    R.use_layout("tokyo_straight")
    kit = SL.eh_kit(SL.stations(R.analyse()))
    out, seen = [eh_restroom()], set()
    for w, islands, core, lanes in kit:
        if w not in seen:
            seen.add(w)
            out += [platform(w, "EH", "elevated_hub"), end_fence(w + SL.EH_SW, "EH_EndFence_%s" % wname(w),
                                                                  "elevated_hub")]
            for hand in ("L", "R"):
                out += [eh_side(w, hand, r) for r in ("plain", "stair", "lift")]
                out += [eh_wing(w, hand, k) for k in ("entrance", "shop", "machines")]
                out += [eh_fare_side(w, hand, g) for g in (False, True)]
        out += [eh_floor(w, False, core, lanes), eh_floor(w, True, core, lanes), eh_end_wall(w, core, lanes)]
        for wi in islands:
            if ("island", wi) in seen:
                continue
            seen.add(("island", wi))
            out += [eh_island(wi, r) for r in ("plain", "stair", "lift")]
            out.append(end_fence(wi, "EH_IslandEndFence_%s" % wname(wi), "elevated_hub"))
    return out


FORM_PIECES = {"open_air": open_air_pieces, "ground_hub": ground_hub_pieces, "elevated_hub": elevated_hub_pieces}
FORM_FILES = {"open_air": "Station_OpenAir.blend", "ground_hub": "Station_GroundHub.blend",
              "elevated_hub": "Station_ElevatedHub.blend"}


# ── the file ─────────────────────────────────────────────────────────────────────────────────────────────────────
LIBRARY_BLEND = os.path.join(ROOT, "assets", "world_source", "kits", "library", "library.blend")


def library_piece(name):
    """The library's piece collection `name`, LINKED into this file (for the PROP_ instances' display only)."""
    lc = bpy.data.collections.get(name)
    if lc is not None and lc.library is not None:
        return lc
    if not os.path.exists(LIBRARY_BLEND):
        return None
    with bpy.data.libraries.load(LIBRARY_BLEND, link=True, relative=True) as (src, dst):
        if name not in src.collections:
            return None
        dst.collections = [name]
    return next((c for c in bpy.data.collections if c.name == name and c.library is not None), None)


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
    for i, g in enumerate(p.gates):
        q, w, hh = g[0], g[1], g[2]
        e = bpy.data.objects.new("GATE_%d" % i, None)
        e.empty_display_type = "SINGLE_ARROW"
        e.empty_display_size = 0.8
        e.location = q
        # the arrow (local +Z) drawn along +X, then turned about Z by the gate's yaw
        e.rotation_euler = (0.0, math.radians(90.0), math.radians(g[3] if len(g) > 3 else 0.0))
        e["w"], e["h"] = float(w), float(hh)
        col.objects.link(e)
    for i, pts in enumerate(p.hulls):
        # a CONVEX collider (a ramp leg's wedge): drawn as a small sphere at its first point, the points (relative to
        # the Empty) in its custom property -- the export turns it into a ConvexPolygonShape3D
        e = bpy.data.objects.new("HULL_%d" % i, None)
        e.empty_display_type = "SPHERE"
        e.empty_display_size = 0.2
        e.location = pts[0]
        e["pts"] = [c - pts[0][k % 3] for q in pts for k, c in enumerate(q)]
        e.hide_render = True
        col.objects.link(e)
    for i, (q, d, w, hh, style, sd) in enumerate(p.doors):
        # an interior door (DOOR_ Empty, export_building_kit.markers): a single arrow on the floor at the doorway's
        # centre, pointing OUT of the room; the scene builder hangs the leaves (`slide_glass`: sliding glass, automatic)
        e = bpy.data.objects.new("DOOR_%d" % i, None)
        e.empty_display_type = "SINGLE_ARROW"
        e.empty_display_size = 0.8
        e.location = q
        e.rotation_euler = (0.0, math.radians(90.0), math.atan2(d[1], d[0]))
        e["w"], e["h"], e["style"], e["slide_dir"] = float(w), float(hh), style, float(sd)
        col.objects.link(e)
    for i, (piece, q, yaw, collide) in enumerate(p.props):
        # a LIBRARY fixture (export_building_kit.markers -> the manifest's `props` -> layout_buildings): shown here as
        # an instance of the linked library piece, so the artist sees it and can move it; never exported as geometry
        e = bpy.data.objects.new("PROP_%02d_%s" % (i, piece), None)
        e.empty_display_type = "ARROWS"
        e.empty_display_size = 0.3
        e.location = q
        e.rotation_euler = (0.0, 0.0, math.radians(yaw))
        e["piece"], e["collide"] = "library:" + piece, collide
        lc = library_piece(piece)
        if lc is not None:
            e.instance_type = "COLLECTION"
            e.instance_collection = lc
        col.objects.link(e)
    for i, (q, w, d, rise, dw, dh) in enumerate(p.lifts):
        e = bpy.data.objects.new("LIFT_%d" % i, None)
        e.empty_display_type = "CUBE"
        e.empty_display_size = 0.3
        e.location = q
        e["w"], e["d"], e["rise"], e["door_w"], e["door_h"] = float(w), float(d), float(rise), float(dw), float(dh)
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
        inst("OA_Building_%s_%s" % (ws, side), (length / 2 + SL.BUILDING_LEN / 2, sg * (edge + SL.BUILDING_D / 2), 0.0),
             0.0)
        inst("OA_Entry_%d_%s" % (SL.entry_n(SL.PLATFORM_H), side), (length / 2 + SL.BUILDING_LEN,
                                                                  sg * (edge + SL.DOOR_OFF), SL.PLATFORM_H), 0.0)
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


PREVIEW = {"ground_hub": "Bay", "elevated_hub": "Suburb"}


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
    # a generated piece of this form the generator no longer makes (a retired design) is REMOVED when untouched --
    # left in the file it would still export -- and reported, never deleted, when an artist has edited it
    wanted_names = {p.name for p in pieces}
    for col in list(bpy.data.collections):
        if col.get("bk_category") == form and col.get("st_generated") and col.name not in wanted_names:
            if col["st_generated"] == fingerprint(col):
                gone = col.name
                remove_piece(gone)
                print("[build_station_blends] %-24s retired (no longer part of the form)" % gone)
            else:
                kept.append(col.name)
                print("[build_station_blends] KEPT %s: retired from the form but edited by hand -- delete it in the "
                      ".blend if it is no longer wanted" % col.name)
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
