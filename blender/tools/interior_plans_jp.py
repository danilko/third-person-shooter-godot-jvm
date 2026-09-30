"""More mission / enterable buildings (user, 2026-09-29), seeded like interior_plans.py and built by
build_interior_blends.py into kits/interiors/<Id>.blend. Japanese convention throughout:

* a house has a 玄関 (genkan): a DOMA (土間, shoes on) one step up from the street, then the 上がり框 (agarikamachi)
  up onto the raised house floor (0.45 m over the ground, 建築基準法 >= 0.45 for a wooden floor), a 下駄箱 (shoe
  cabinet) beside it; the TOILET is its own small room, apart from the 洗面所 (wash room) and the 浴室 (bathroom,
  a unit bath);  和室 (tatami rooms) with 押入れ (futon closets); an LDK;
* a shop / public building has a 風除室 (windbreak vestibule: two sets of automatic doors) at a busy entrance;
* baths (onsen) are split 男湯 / 女湯 behind 暖簾 with a 脱衣所 (changing room) in front, a 洗い場 (wash row of
  stools and taps) before the tub;
* stairs obey interior_kit (riser <= 0.19, tread 0.27) even in a house: comfortable, not the steep house stair a
  real one might have (the game's step-height rule wins);
* car ramps <= 1/6 (駐車場法施行令: a ramp is at most 17 %), a parking bay 2.5 x 5.0 m, an aisle 6 m.

Frame as interior_plans: metres, Z up, origin on the ground at the plot centre, the STREET toward -Y.
"""
import math

import interior_kit as IK
from interior_kit import Opening
from interior_plans import (EXT_T, PART_T, apron, band_windows, chairs_around, ext, glass_part, openings,
                            paint_bays, part, roof, sign, stair_house)

HOUSE_FLOOR = 0.45          # a Japanese wooden house's raised floor
DOMA = 0.15                 # the genkan's 土間 top: one step up from the ground


# ── helpers ─────────────────────────────────────────────────────────────────────────────────────────────────────

def _hexa(b, group, pts, mat):
    """A solid from 8 corners in box order (bottom ring x0y0, x1y0, x1y1, x0y1, then the top ring)."""
    g = b.g(group)
    mi = g._mi(mat)
    vs = [g.bm.verts.new(p) for p in pts]
    for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        g.bm.faces.new([vs[i] for i in f]).material_index = mi


def ramp(b, x0, y0, x1, y1, za, zb, axis, t=0.25, group="Structure", mat="MI_ConcreteSmooth"):
    """A sloped slab `t` thick: top at `za` at the low end (x0 / y0) rising to `zb` at x1 / y1."""
    if axis == "x":
        top = [(x0, y0, za), (x1, y0, zb), (x1, y1, zb), (x0, y1, za)]
    else:
        top = [(x0, y0, za), (x1, y0, za), (x1, y1, zb), (x0, y1, zb)]
    _hexa(b, group, [(x, y, z - t) for x, y, z in top] + top, mat)


def gable(b, x0, y0, x1, y1, z, rise, ridge="x", over=0.6, t=0.2, mat="MI_RoofSlate", group="Roof", gable_mat=None):
    """A gable roof (切妻) over x0..x1 / y0..y1 from eave height z, the ridge along `ridge`, `over` eaves; the gable
    ends are filled with `gable_mat` (the wall's facade)."""
    X0, Y0, X1, Y1 = x0 - over, y0 - over, x1 + over, y1 + over
    if ridge == "x":
        ym = (Y0 + Y1) / 2
        for ya, yb in ((Y0, ym), (Y1, ym)):
            lo = [(X0, ya, z), (X1, ya, z), (X1, yb, z + rise), (X0, yb, z + rise)]
            _hexa(b, group, lo + [(p[0], p[1], p[2] + t) for p in lo], mat)
        if gable_mat:
            g = b.g(group)
            mi = g._mi(gable_mat)
            for x in (x0, x1):
                vs = [g.bm.verts.new(p) for p in ((x, y0, z), (x, y1, z), (x, (y0 + y1) / 2, z + rise * (1 - over / ((Y1 - Y0) / 2))))]
                g.bm.faces.new(vs).material_index = mi
                vs2 = [g.bm.verts.new(v.co) for v in vs]
                g.bm.faces.new(vs2[::-1]).material_index = mi
    else:
        xm = (X0 + X1) / 2
        for xa, xb in ((X0, xm), (X1, xm)):
            lo = [(xa, Y0, z), (xa, Y1, z), (xb, Y1, z + rise), (xb, Y0, z + rise)]
            _hexa(b, group, lo + [(p[0], p[1], p[2] + t) for p in lo], mat)
        if gable_mat:
            g = b.g(group)
            mi = g._mi(gable_mat)
            for y in (y0, y1):
                vs = [g.bm.verts.new(p) for p in ((x0, y, z), (x1, y, z), ((x0 + x1) / 2, y, z + rise * (1 - over / ((X1 - X0) / 2))))]
                g.bm.faces.new(vs).material_index = mi
                vs2 = [g.bm.verts.new(v.co) for v in vs]
                g.bm.faces.new(vs2[::-1]).material_index = mi


def sstair(b, x0, x1, y0, z0, rise, sign_=1, tread=IK.TREAD, mat="MI_ConcreteSmooth", nosing="MI_PaintedMetalDark",
           rails=True, group="Stairs"):
    """A STRAIGHT flight x0..x1 wide starting at y0 and climbing toward +Y (sign_ +1) or -Y, from floor z0 up
    `rise`. Used for an escalator's walkable placeholder (tread 0.4: ~25 deg) and a stair in a void. Returns the
    hole (the flight's plan) to cut in the slab above."""
    n = int(math.ceil(rise / IK.RISER_MAX))
    r = rise / n
    for i in range(n):
        top = z0 + (i + 1) * r
        ya = y0 + sign_ * i * tread
        yb = ya + sign_ * tread
        lo, hi = min(ya, yb), max(ya, yb)
        b.box(group, (x0, lo, max(z0, top - r - 0.3)), (x1, hi, top), mat)
        nl, nh = (hi - 0.04, hi) if sign_ > 0 else (lo, lo + 0.04)
        b.box(group, (x0, nl, top - 0.02), (x1, nh, top + 0.005), nosing)
    L = n * tread
    if rails:
        for x in (x0 - 0.08, x1):
            for i in range(n):
                ya = y0 + sign_ * i * tread
                yb = ya + sign_ * tread
                b.box(group, (x, min(ya, yb), z0 + (i + 1) * r), (x + 0.08, max(ya, yb), z0 + (i + 1) * r + 1.0),
                      "MI_GlassClear" if tread > 0.3 else mat)
    ya, yb = sorted((y0, y0 + sign_ * L))
    return (x0 - 0.1, ya, x1 + 0.1, yb)


def perimeter(b, x0, y0, x1, y1, h, gaps, t=0.2, mat="MI_ConcreteSmooth", cap=None, group="Site"):
    """A boundary wall (塀) round x0..x1 / y0..y1, `h` tall, with gaps [(side 'f'|'b'|'l'|'r', u, width)]."""
    for s, axis, c, a0, a1 in (("f", "x", y0, x0, x1), ("b", "x", y1, x0, x1),
                               ("l", "y", x0, y0, y1), ("r", "y", x1, y0, y1)):
        cuts = sorted((u - w / 2, u + w / 2) for side, u, w in gaps if side == s)
        cur = a0
        for u0, u1 in cuts + [(a1, a1)]:
            if u0 - cur > 0.05:
                if axis == "x":
                    b.box(group, (cur, c - t / 2, 0.0), (u0, c + t / 2, h), mat)
                    if cap:
                        b.box(group, (cur, c - t / 2 - 0.03, h), (u0, c + t / 2 + 0.03, h + 0.08), cap)
                else:
                    b.box(group, (c - t / 2, cur, 0.0), (c + t / 2, u0, h), mat)
                    if cap:
                        b.box(group, (c - t / 2 - 0.03, cur, h), (c + t / 2 + 0.03, u0, h + 0.08), cap)
            cur = max(cur, u1)


def genkan(b, x0, y0, x1, step_y, shoe_x=None):
    """The genkan's 土間 (x0..x1, y0..step_y) at DOMA, the 上がり框 edge at step_y (a wood nosing), a 下駄箱 on the
    x = shoe_x wall. The house floor (HOUSE_FLOOR) starts past step_y; call b.slab for it with this doma as a hole."""
    b.box("Structure", (x0, y0, 0.0), (x1, step_y, DOMA), "MI_TileBrown")
    b.box("Structure", (x0, step_y - 0.1, DOMA), (x1, step_y, HOUSE_FLOOR), "MI_Wood")      # the agarikamachi
    if shoe_x is not None:
        sx = 1 if shoe_x > (x0 + x1) / 2 else -1
        b.box("Furniture", (shoe_x - (0.38 if sx > 0 else 0), y0 + 0.15, DOMA),
              (shoe_x + (0 if sx > 0 else 0.38), step_y - 0.25, DOMA + 0.95), "MI_Wood")


def tatami(b, x0, y0, x1, y1, z):
    """Tatami mats laid over a floor at z (0.9 x 1.8 m mats, 5.5 cm)."""
    b.box("Furniture", (x0, y0, z), (x1, y1, z + 0.012), "MI_Tatami")     # flush: a 和室's floor is sunk for it
    x = x0 + 0.91
    while x < x1 - 0.1:
        b.box("Furniture", (x - 0.012, y0, z + 0.012), (x + 0.012, y1, z + 0.015), "MI_Wood")
        x += 0.91


def oshiire(b, x0, y0, x1, y1, z, h=2.3):
    """押入れ: a futon closet, fusuma front (a box the size of the closet)."""
    b.box("Furniture", (x0, y0, z), (x1, y1, z + h), "MI_Shoji")


def kitchen_run(b, x0, x1, y, z, face=1):
    """A system kitchen along a wall at y (worktop 0.85, 0.65 deep), face +1 = the cook stands on +Y."""
    d = 0.65 * face
    ya, yb = sorted((y, y + d))
    b.box("Furniture", (x0, ya, z), (x1, yb, z + 0.85), "MI_PlasticWhite")
    b.box("Furniture", (x0, ya, z + 0.85), (x1, yb, z + 0.88), "MI_Steel")


def bath_unit(b, x0, y0, x1, y1, z):
    """浴室: a unit bath's tub and wash space: the tub along the far (+Y) wall, a raised door sill."""
    b.put("Hotel_Tub", (x0 + x1) / 2, y1 - 0.45, 0.0, z=z)
    b.box("Furniture", (x0 + 0.1, y0 + 0.1, z), (x0 + 0.5, y0 + 0.5, z + 0.35), "MI_PlasticWhite")   # the bath stool


def low_table(b, x, y, z, w=1.8, d=0.9, cushions=True):
    """座卓: a low table 0.33 m high, with 座布団 cushions."""
    b.box("Furniture", (x - w / 2, y - d / 2, z + 0.3), (x + w / 2, y + d / 2, z + 0.33), "MI_Wood")
    for sx in (-1, 1):
        for sy in (-1, 1):
            b.box("Furniture", (x + sx * (w / 2 - 0.1) - 0.04, y + sy * (d / 2 - 0.1) - 0.04, z),
                  (x + sx * (w / 2 - 0.1) + 0.04, y + sy * (d / 2 - 0.1) + 0.04, z + 0.3), "MI_Wood")
    if cushions:
        n = max(1, int(w / 0.75))
        for i in range(n):
            cx = x - w / 2 + (i + 0.5) * w / n
            for cy in (y - d / 2 - 0.35, y + d / 2 + 0.35):
                b.box("Furniture", (cx - 0.27, cy - 0.27, z), (cx + 0.27, cy + 0.27, z + 0.06), "MI_FabricRed")


def counter(b, x0, y0, x1, y1, z=0.0, h=1.05, mat="MI_Wood", top="MI_Hinoki"):
    b.box("Furniture", (x0, y0, z), (x1, y1, z + h - 0.05), mat)
    b.box("Furniture", (x0 - 0.05, y0 - 0.05, z + h - 0.05), (x1 + 0.05, y1 + 0.05, z + h), top)


def stools(b, x0, x1, y, z=0.0, every=0.6, h=0.7):
    x = x0
    while x <= x1 + 1e-6:
        b.box("Furniture", (x - 0.03, y - 0.03, z), (x + 0.03, y + 0.03, z + h - 0.06), "MI_Steel")
        b.box("Furniture", (x - 0.18, y - 0.18, z + h - 0.06), (x + 0.18, y + 0.18, z + h), "MI_FabricRed")
        x += every


def chochin(b, x, y, z, mat="MI_SignRed"):
    """赤提灯: a red paper lantern hanging at the door."""
    b.box("Facade", (x - 0.2, y - 0.2, z), (x + 0.2, y + 0.2, z + 0.6), mat)
    b.box("Facade", (x - 0.12, y - 0.12, z + 0.6), (x + 0.12, y + 0.12, z + 0.66), "MI_PlasticDark")


def noren(b, x0, x1, y, z_top, mat="MI_NorenNavy", drop=0.9):
    """暖簾: the split cloth over a doorway (split in strips; a body passes between them). Non-solid in spirit:
    a thin panel above head height (the strips stop at z_top - drop >= 2.0)."""
    lo = max(z_top - drop, 1.95)
    n = max(2, int((x1 - x0) / 0.35))
    for i in range(n):
        a = x0 + (x1 - x0) * i / n + 0.01
        c = x0 + (x1 - x0) * (i + 1) / n - 0.01
        b.box("Facade", (a, y - 0.01, lo), (c, y + 0.01, z_top), mat)


def fence(b, x0, y0, x1, y1, gaps, h=1.8, base=0.5, pitch=0.3, group="Site"):
    """A security fence (a steel palisade on a concrete upstand) round x0..x1 / y0..y1, with gaps
    [(side, u, width)] -- the gates."""
    for s_, axis, c, a0, a1 in (("f", "x", y0, x0, x1), ("b", "x", y1, x0, x1),
                                ("l", "y", x0, y0, y1), ("r", "y", x1, y0, y1)):
        cuts = sorted((u - w / 2, u + w / 2) for side, u, w in gaps if side == s_)
        cur = a0
        for u0, u1 in cuts + [(a1, a1)]:
            if u0 - cur > 0.05:
                def bx(ua, ub, za, zb, t, m):
                    if axis == "x":
                        b.box(group, (ua, c - t / 2, za), (ub, c + t / 2, zb), m)
                    else:
                        b.box(group, (c - t / 2, ua, za), (c + t / 2, ub, zb), m)
                bx(cur, u0, 0.0, base, 0.25, "MI_ConcreteSmooth")
                bx(cur, u0, h - 0.06, h, 0.06, "MI_PaintedMetalDark")
                bx(cur, u0, base + 0.1, base + 0.14, 0.05, "MI_PaintedMetalDark")
                n = max(1, int((u0 - cur) / pitch))
                for k in range(n + 1):
                    u = cur + (u0 - cur) * k / n
                    bx(u - 0.015, u + 0.015, base, h, 0.03, "MI_PaintedMetalDark")
            cur = max(cur, u1)


# ── 隠れ家 (small): a two-storey 3.5 x 5 間 wooden house (木造2階建て), the player's first safe house ──────────────

def safehouse_small(b):
    x0, y0, x1, y1 = -3.2, -4.55, 3.2, 4.55
    F1, F2, TOP = HOUSE_FLOOR, HOUSE_FLOOR + 2.8, HOUSE_FLOOR + 5.5
    xi0, xi1, yf, yb = x0 + EXT_T, x1 - EXT_T, y0 + EXT_T, y1 - EXT_T
    apron(b, -4.0, -7.5, 4.0, 5.2)
    b.box("Site", (2.2, -7.5, 0.0), (4.0, -4.6, 0.02), "MI_ConcreteSmooth")         # a bike / scooter spot
    perimeter(b, -4.0, -7.5, 4.0, 5.2, 1.2, [("f", -2.1, 1.6), ("f", 3.0, 2.2)], mat="MI_StoneWall", cap="MI_ConcreteSmooth")
    b.box("Site", (-2.9, -5.15, 0.0), (-1.3, -4.55, DOMA), "MI_TileBrown")            # the porch step
    # the genkan (front-left) and the stair behind it
    step_y = -3.1
    genkan(b, xi0, yf, -1.2, step_y, shoe_x=-1.2)
    b.box("Site", (x0 - 0.6, -4.15, 0.0), (x0, -3.35, DOMA), "MI_TileBrown")         # the side door's step
    well = (xi0, step_y, -1.2, step_y + 5.0)
    hole = b.ustair(*well, F1, F2 - F1, near="s", cap=True)
    b.slab(xi0, yf, xi1, yb, F1, "MI_Wood", holes=[(xi0, yf, -1.2, step_y)], t=HOUSE_FLOOR)
    b.slab(xi0, yf, xi1, yb, F2, "MI_Wood", holes=[hole])
    for lo, hi in (((x0, y0), (x1, y0 + EXT_T)), ((x0, y1 - EXT_T), (x1, y1)), ((x0, y0), (x0 + EXT_T, y1)),
                   ((x1 - EXT_T, y0), (x1, y1))):
        b.box("Facade", (lo[0], lo[1], 0.0), (hi[0], hi[1], DOMA), "MI_ConcreteSmooth")     # 基礎, the foundation
    ext(b, x0, y0, x1, y1, DOMA, F2 - DOMA, "MI_TileBeige", {
        "f": ([(-2.1, -1, 0.9, "slide", "exit", 2.0)], [b.window(1.2, F1, 2.2, 0.8, 2.0)]),
        "l": ([(-3.75, -1, 0.9, "swing", "exit", 2.0)], []),
        "r": ((), [b.window(3.3, F1, 0.8, 1.2, 1.9), b.window(-1.0, F1, 0.9, 1.1, 2.0)]),
    })
    ext(b, x0, y0, x1, y1, F2, TOP - F2, "MI_TileBeige", {
        "f": ((), [b.window(-0.5, F2, 1.6, 0.9, 2.0), b.window(1.9, F2, 1.6, 0.9, 2.0)]),
        "b": ((), [b.window(0.9, F2, 1.6, 0.9, 2.0)]),
        "r": ((), [b.window(2.5, F2, 1.2, 0.9, 1.9)]),
    })
    gable(b, x0, y0, x1, y1, TOP, 1.8, ridge="y", over=0.5, gable_mat="MI_TileBeige")
    b.box("Facade", (-3.0, y0 - 0.9, 2.4), (-1.2, y0, 2.5), "MI_PaintedMetalDark")    # the door hood
    b.box("Facade", (1.2 - 1.0, y0 - 0.9, F1 + 2.2), (1.2 + 1.0, y0, F1 + 2.3), "MI_PaintedMetalDark")
    # F1: the hall (the stair's landing) -> LDK (right, front) ; 洗面所 + 浴室 (right, back) ; WC (left, back)
    H = F2 - F1 - 0.2
    part(b, "y", -1.15, yf, 1.95, F1, H, doors=[(step_y + 0.75, 1, 0.8, "swing", "door", 2.0)])
    part(b, "x", 0.9, -1.1, xi1, F1, H, doors=[(-0.2, 1, 0.8, "slide", "door", 2.0)])
    part(b, "y", 0.95, 0.9, yb, F1, H, doors=[(2.1, 1, 0.7, "swing", "door", 2.0)])   # 洗面所 | 浴室 (a door)
    part(b, "x", 1.95, xi0, -1.15, F1, H)                                             # the stair's back wall
    part(b, "y", -1.15, 1.95, yb, F1, H, doors=[(3.2, 1, 0.7, "swing", "door", 2.0)])  # the WC off the wash room
    kitchen_run(b, 0.35, 2.3, 0.84, F1, face=-1)
    b.put("Kitchen_Fridge", 2.62, 0.45, 0.0, z=F1)
    b.put("Rest_Table", 1.3, -1.6, 90.0, z=F1)
    for dy in (-0.35, 0.35):
        b.put("Rest_Chair", 0.55, -1.6 + dy, 270.0, z=F1)
    b.put("Office_Sofa", 1.9, -3.7, 0.0, z=F1)
    b.mark("spawn", 0.4, -2.8, F1, 0.0, team="player", note="the safe house: save / rest here")
    b.put("WC_Basin", 0.0, yb - 0.3, 180.0, z=F1)
    bath_unit(b, 1.0, 1.0, xi1, yb, F1)
    b.put("WC_Toilet", -2.1, yb - 0.38, 180.0, z=F1)
    # F2: 洋室 (front) and 和室 (back, a 続き間 behind a fusuma), the 納戸 with the stash over the WC
    H2 = TOP - F2 - 0.2
    part(b, "y", -1.15, yf, 1.95, F2, H2, doors=[(step_y + 0.7, 1, 0.8, "swing", "door", 2.0)])
    part(b, "x", 0.2, -1.15, xi1, F2, H2, doors=[(1.0, 1, 1.6, "slide", "door", 2.0)])
    part(b, "x", 1.95, xi0, -1.15, F2, H2)
    b.put("Hotel_Bed", 2.0, -3.2, 90.0, z=F2)
    b.put("Office_Desk", -0.3, -3.9, 180.0, z=F2)
    tatami(b, -1.1, 0.25, xi1, yb, F2)
    oshiire(b, 2.1, 0.3, xi1, 1.9, F2)
    low_table(b, 0.6, 2.8, F2 + 0.055, 1.2, 0.8)
    part(b, "y", -1.15, 1.95, yb, F2, H2, doors=[(3.2, -1, 0.8, "slide", "door", 2.0)])
    b.put("Shop_StockShelf", -2.1, yb - 0.4, 0.0, z=F2)
    for i, w in enumerate(("PIS1", "SMG1", "SHG1")):
        b.mark("weapon", -2.6 + i * 0.5, 3.2, F2, 180.0, weapon=w, note="the safe house's stash (納戸)")
    return {"note": "隠れ家 (small safe house): a two-storey 3.5 x 5 間 wooden house -- genkan with the shoe step, "
                    "LDK, 洗面所 + unit bath, a separate WC; upstairs a 洋室 and a 和室 (続き間) and the 納戸 with the "
                    "stash; a stone boundary wall with a scooter spot."}


# ── 隠れ家 (large): a 7 x 5.5 間 two-storey 注文住宅 with a built-in garage, on a walled lot ───────────────────────

def safehouse_large(b):
    x0, y0, x1, y1 = -6.37, -4.8, 6.37, 5.2
    F1, F2, TOP = HOUSE_FLOOR, HOUSE_FLOOR + 2.8, HOUSE_FLOOR + 5.5
    xi0, xi1, yf, yb = x0 + EXT_T, x1 - EXT_T, y0 + EXT_T, y1 - EXT_T
    GX = 1.0                                   # the garage: x GX .. xi1, y yf .. GY (floor at the ground)
    GY = 1.0
    apron(b, -8.5, -10.0, 8.5, 7.5)
    b.box("Site", (-8.3, 1.5, 0.0), (-6.6, 7.3, 0.02), "MI_Grass")                    # the garden strip
    b.box("Site", (-8.3, -9.8, 0.0), (-3.0, -5.3, 0.02), "MI_Grass")                  # the front garden
    perimeter(b, -8.5, -10.0, 8.5, 7.5, 1.6, [("f", -0.35, 1.4), ("f", 3.6, 5.2)],
              mat="MI_StoneWall", cap="MI_ConcreteSmooth")
    for x in (-1.1, 0.4):
        b.box("Site", (x - 0.2, -10.2, 0.0), (x + 0.2, -9.8, 1.9), "MI_StoneWall")   # the gate posts
    b.box("Site", (-1.2, -9.9, 1.45), (-0.9, -9.7, 1.75), "MI_PlasticDark")          # the intercom / camera
    b.box("Site", (5.9, -9.9, 2.2), (6.2, -9.6, 2.5), "MI_PlasticDark")              # a camera on the car gate
    b.box("Site", (-1.05, -5.4, 0.0), (0.35, -4.8, DOMA), "MI_TileBrown")            # the porch step
    for lo, hi in (((x0, y0), (x1, y0 + EXT_T)), ((x0, y1 - EXT_T), (x1, y1)), ((x0, y0), (x0 + EXT_T, y1)),
                   ((x1 - EXT_T, y0), (x1, y1))):
        b.box("Facade", (lo[0], lo[1], 0.0), (hi[0], hi[1], DOMA), "MI_ConcreteSmooth")     # 基礎
    # slabs: the house floor (raised), the genkan doma, the garage at the ground
    step_y = -3.2
    genkan(b, -1.8, yf, 0.9, step_y, shoe_x=-1.8)
    well = (xi0, -0.2, -3.67, yb)
    hole = b.ustair(*well, F1, F2 - F1, near="s", cap=True)
    b.slab(xi0, yf, xi1, yb, F1, "MI_Wood", holes=[(-1.8, yf, 0.9, step_y), (GX, yf, xi1, GY), (0.2, -2.6, GX, -1.4)],
           t=HOUSE_FLOOR)
    b.slab(GX, yf, xi1, GY, 0.0, "MI_ConcreteSmooth")
    b.slab(xi0, yf, xi1, yb, F2, "MI_Wood", holes=[hole])
    ext(b, x0, y0, x1, y1, DOMA, F2 - DOMA, "MI_PaintWhite", {
        "f": ([(-0.35, -1, 0.9, "slide", "exit", 2.0), (3.6, -1, 4.6, "", "open", 2.2 - DOMA)],
              [b.window(-5.1, F1, 1.6, 1.1, 2.0), b.window(-2.8, F1, 1.8, 0.3, 2.1)]),
        "l": ((), [b.window(-2.5, F1, 1.6, 0.9, 2.0), b.window(3.0, F1, 0.8, 1.3, 2.0, "MI_Shoji")]),
        "b": ((), [b.window(-2.0, F1, 1.6, 0.9, 2.0), b.window(2.2, F1, 0.8, 1.4, 1.9)]),
    })
    b.box("Facade", (GX + 0.2, y0 - 0.02, 0.0), (xi1 - 0.2, y0, DOMA), "MI_TileBrown")    # the garage sill (open)
    ext(b, x0, y0, x1, y1, F2, TOP - F2, "MI_PaintWhite", {
        "f": ((), [b.window(-3.5, F2, 2.6, 0.2, 2.1), b.window(0.9, F2, 1.6, 0.9, 2.0), b.window(4.2, F2, 1.6, 0.9, 2.0)]),
        "b": ((), [b.window(-1.5, F2, 1.6, 0.9, 2.0), b.window(3.5, F2, 1.2, 1.2, 2.0)]),
        "r": ((), [b.window(-1.0, F2, 1.6, 0.9, 2.0)]),
    })
    b.box("Facade", (-6.2, y0 - 1.2, F2 - 0.1), (-0.8, y0, F2 + 0.05), "MI_ConcreteSmooth")  # the balcony slab
    b.box("Facade", (-6.2, y0 - 1.2, F2 + 0.05), (-0.8, y0 - 1.1, F2 + 1.15), "MI_GlassClear")
    b.box("Facade", (GX, y0 - 0.25, 2.25), (xi1, y0, 2.6), "MI_PaintedMetalDark")     # the raised shutter's box
    b.box("Facade", (-1.3, y0 - 0.9, 2.45), (0.6, y0, 2.55), "MI_PaintedMetalDark")   # the door hood
    gable(b, x0, y0, x1, y1, TOP, 1.9, ridge="x", over=0.6, gable_mat="MI_PaintWhite")
    H = F2 - F1 - 0.2
    # F1: LDK (リビング階段: the stair rises out of the living room), 和室, the corridor, WC, 洗面所 + 浴室, garage
    part(b, "y", -0.4, step_y, 3.1, F1, H, doors=[(-2.0, -1, 0.8, "swing", "door", 2.0),
                                                 (2.6, -1, 0.8, "slide", "door", 2.0)])
    part(b, "y", -1.85, yf, step_y, F1, H)                                      # the genkan's west wall
    part(b, "x", 1.3, -3.62, -0.4, F1, H, doors=[(-2.0, -1, 1.6, "slide", "door", 2.0)])   # LDK | 和室 fusuma
    part(b, "y", -3.62, 1.3, yb, F1, H)                                        # 和室 | the stair
    part(b, "x", 3.1, -0.4, GX, F1, H, doors=[(0.25, -1, 0.8, "slide", "door", 2.0)])    # the WC at the corridor's end
    part(b, "y", GX, yf, GY, 0.0, F2 - 0.2, doors=[(-2.0, -1, 0.9, "slide", "door", 2.35)])   # garage <-> hall
    part(b, "y", GX, GY, yb, F1, H, doors=[(2.0, 1, 0.8, "slide", "door", 2.0)])
    part(b, "x", GY, GX, xi1, 0.0, F2 - 0.2)                                   # the garage's back wall
    part(b, "y", 3.4, GY, yb, F1, H, doors=[(3.0, 1, 0.8, "slide", "door", 2.0)])        # 洗面所 | 浴室
    # the garage door opens off a small 土間 pocket in the hall, at the garage's level, with a half step up
    b.box("Structure", (0.2, -2.6, -0.2), (GX - 0.06, -1.4, 0.0), "MI_TileBrown")
    b.box("Structure", (0.2, -2.6, 0.0), (0.5, -1.4, 0.225), "MI_TileBrown")
    kitchen_run(b, -6.1, -4.1, -4.6, F1, face=1)
    kitchen_run(b, -6.1, -4.4, -2.2, F1, face=-1)                              # the island (対面キッチン)
    b.put("Kitchen_Fridge", -3.65, -4.35, 0.0, z=F1)
    b.put("Rest_Table", -3.3, -2.9, 0.0, z=F1)
    for dx in (-0.35, 0.35):
        b.put("Rest_Chair", -3.3 + dx, -3.65, 0.0, z=F1)
        b.put("Rest_Chair", -3.3 + dx, -2.15, 180.0, z=F1)
    b.put("Office_Sofa", -5.3, -0.9, 90.0, z=F1)
    b.box("Furniture", (-3.3, -1.3, F1), (-2.9, -0.2, F1 + 0.55), "MI_PlasticDark")      # the TV board
    tatami(b, -3.56, 1.36, -0.46, yb, F1)
    oshiire(b, -3.56, 4.1, -1.8, yb, F1)
    low_table(b, -2.0, 2.6, F1 + 0.012, 1.2, 0.8)
    b.put("WC_Toilet", 0.25, yb - 0.38, 180.0, z=F1)
    b.put("WC_Basin", 1.4, 3.0, 90.0, z=F1)
    bath_unit(b, 3.5, GY + 0.1, xi1, yb, F1)
    for x in (2.4, 4.9):
        b.mark("vehicle", x, -1.8, 0.0, 180.0, vehicle="CLC1", note="the built-in garage (ビルトインガレージ)")
    b.mark("spawn", -2.0, -0.8, F1, 180.0, team="player", note="the large safe house")
    # F2: the corridor on the landing's line; master bedroom + study (the armoury) + child room to the front
    H2 = TOP - F2 - 0.2
    part(b, "x", -0.25, -3.67, xi1, F2, H2, doors=[(-2.0, -1, 0.8, "swing", "door", 2.0),
                                                  (0.9, -1, 0.9, "swing", "door", 2.0),
                                                  (4.2, -1, 0.8, "swing", "door", 2.0)])
    part(b, "x", -0.25, xi0, -3.67, F2, H2, doors=[(-5.0, -1, 0.8, "swing", "door", 2.0)])
    part(b, "x", 1.25, -3.62, xi1, F2, H2, doors=[(-2.0, 1, 0.8, "swing", "door", 2.0),
                                                 (1.7, 1, 0.8, "slide", "door", 2.0),
                                                 (4.3, 1, 0.8, "swing", "door", 2.0)])
    part(b, "y", -3.62, 1.25, yb, F2, H2)
    part(b, "y", -0.4, yf, -0.25, F2, H2)
    part(b, "y", 2.2, yf, -0.25, F2, H2)
    part(b, "y", 1.0, 1.25, yb, F2, H2)
    part(b, "y", 2.4, 1.25, yb, F2, H2)
    b.put("Hotel_Bed", -3.0, -3.3, 90.0, z=F2)
    b.put("Office_Cabinet", -5.8, -2.0, 90.0, z=F2)
    b.put("Office_Desk", 0.9, -4.2, 180.0, z=F2)
    b.put("Office_Chair", 0.9, -3.55, 0.0, z=F2)
    b.put("Office_Safe", -0.0, -1.2, 90.0, z=F2)
    b.put("Police_GunLocker", 1.85, -2.2, 270.0, z=F2)
    for i, w in enumerate(("ASR1", "SHG1", "SNR1", "PIS2")):
        b.mark("weapon", 1.3, -3.2 + i * 0.5, F2, 90.0, weapon=w, note="the study's gun locker")
    b.mark("objective", 0.0, -1.2, F2, 0.0, note="the safe (cash, documents)")
    b.put("Hotel_Bed", 4.2, -3.6, 90.0, z=F2)
    b.put("Office_Desk", 5.5, -1.3, 270.0, z=F2)
    b.put("Hotel_Bed", -2.2, 3.8, 90.0, z=F2)
    b.put("WC_Toilet", 1.7, yb - 0.38, 180.0, z=F2)
    b.put("Shop_StockShelf", 4.3, yb - 0.4, 0.0, z=F2)
    return {"note": "隠れ家 (large safe house): a 7 x 5.5 間 two-storey house with a built-in two-car garage -- "
                    "genkan, リビング階段 LDK with a 対面 kitchen, a 6-畳 和室 with 押入れ, WC, 洗面所 + unit bath; "
                    "upstairs the master bedroom (balcony), the study with the safe and the gun locker, two more "
                    "rooms, a WC and the storeroom; a 1.6 m block wall with a car gate and a camera."}


# ── 居酒屋 (小料理屋 / 大衆酒場): a two-storey 3 x 7 間 izakaya, enterable ───────────────────────────────────────────

def izakaya(b):
    x0, y0, x1, y1 = -2.73, -6.37, 2.73, 6.37
    F1, F2, TOP = 0.0, 3.0, 5.8
    xi0, xi1, yf, yb = x0 + EXT_T, x1 - EXT_T, y0 + EXT_T, y1 - EXT_T
    apron(b, -2.9, -8.0, 2.9, 7.0)
    well = (0.6, 1.17, xi1, yb)
    hole = b.ustair(*well, F1, F2 - F1, near="s", cap=True)
    b.slab(x0, y0, x1, y1, F1, "MI_TileBrown")                                  # the shop floor (土間)
    b.slab(xi0, yf, xi1, yb, F2, "MI_Wood", holes=[hole])
    ext(b, x0, y0, x1, y1, F1, F2, "MI_Wood", {
        "f": ([(-0.6, -1, 1.8, "slide", "exit", 2.0)], [b.window(1.8, F1, 1.2, 1.0, 2.0, "MI_Shoji")]),
        "l": ([(3.3, -1, 0.9, "swing", "exit", 2.0)], []),
    })
    ext(b, x0, y0, x1, y1, F2, TOP - F2, "MI_Plaster", {
        "f": ((), [b.window(0.0, F2, 2.4, 0.8, 1.9, "MI_Shoji")]),
        "r": ((), [b.window(-3.0, F2, 1.6, 0.8, 1.9, "MI_Shoji")]),
    })
    b.box("Facade", (x0 - 0.1, y0 - 0.9, 2.45), (x1 + 0.1, y0, 2.6), "MI_RoofSlate")   # the 庇 over the front
    noren(b, -1.5, 0.3, y0 - 0.12, 2.4, "MI_NorenNavy")
    for x in (-1.9, 0.7):
        chochin(b, x, y0 - 0.45, 1.7)
    sign(b, -2.2, 2.2, y0, 2.7, 3.0 - 0.05, "MI_Wood")                         # the 看板 board
    b.box("Facade", (x1 + 0.0, -5.6, 1.2), (x1 + 0.3, -4.6, 2.6), "MI_SignRed")      # a standing sign by the door
    gable(b, x0, y0, x1, y1, TOP, 1.4, ridge="x", over=0.5, gable_mat="MI_Plaster")
    # F1: the L counter and the open kitchen on the right, stools; the 小上がり on the left; WC and the back door
    counter(b, 0.5, -4.5, 1.1, 0.9)
    b.box("Furniture", (1.2, -4.5, 0.0), (xi1, -3.6, 0.9), "MI_Steel")          # the kitchen's range
    kitchen_run(b, 1.8, xi1, 0.9, 0.0, face=-1)
    b.box("Furniture", (xi1 - 0.6, -2.5, 0.0), (xi1, 0.2, 0.9), "MI_Steel")      # the back bench (流し台)
    b.box("Furniture", (xi1 - 0.5, -2.5, 1.5), (xi1, 0.2, 1.9), "MI_Wood")       # the bottle shelf
    stools(b, 0.2, 0.2, -4.2, every=0.6)
    for y in (-3.6, -3.0, -2.4, -1.8, -1.2, -0.6, 0.0, 0.6):
        stools(b, 0.2, 0.2, y)
    b.box("Furniture", (xi0, -3.2, 0.0), (-1.0, 2.0, 0.3), "MI_Wood")           # 小上がり, 0.3 m up
    tatami(b, xi0, -3.2, -1.0, 2.0, 0.3)
    for y in (-2.0, 0.8):
        low_table(b, -1.75, y, 0.312, 0.7, 1.2, cushions=False)
        for dx in (-0.5, 0.5):
            for dy in (-0.35, 0.35):
                b.box("Furniture", (-1.75 + dx - 0.2, y + dy - 0.2, 0.312), (-1.75 + dx + 0.2, y + dy + 0.2, 0.37),
                      "MI_FabricRed")
    b.box("Furniture", (xi0, -5.9, 0.0), (-1.6, -5.4, 1.0), "MI_Wood")          # the umbrella / shoe rack
    part(b, "x", 4.2, xi0, 0.5, F1, F2 - 0.2, doors=[(-1.2, -1, 0.8, "slide", "door", 2.0)])
    part(b, "y", 0.5, 4.2, yb, F1, F2 - 0.2)
    b.put("WC_Toilet", -1.2, yb - 0.38, 180.0)
    b.put("WC_Basin", -2.3, 4.9, 90.0)
    b.mark("spawn", 1.8, -1.5, F1, 90.0, team="staff", note="the master (大将) behind the counter")
    b.mark("spawn", 0.2, -2.4, F1, 270.0, team="civilian")
    b.mark("spawn", -1.75, -2.0, 0.3, 0.0, team="civilian")
    b.mark("objective", 2.2, -0.5, F1, 90.0, note="the register / the tab")
    # F2: the 座敷 (a private tatami banquet room) and the staff room
    H2 = TOP - F2 - 0.2
    part(b, "x", 1.1, xi0, xi1, F2, H2, doors=[(1.5, -1, 0.9, "slide", "door", 2.0)])
    part(b, "y", 0.55, 1.1, yb, F2, H2, doors=[(2.0, 1, 0.8, "swing", "door", 2.0)])
    tatami(b, xi0, yf, xi1, 1.04, F2)
    low_table(b, 0.0, -2.6, F2 + 0.012, 1.0, 4.0, cushions=False)
    for dy in (-1.5, -0.5, 0.5, 1.5):
        for dx in (-0.85, 0.85):
            b.box("Furniture", (dx - 0.27, -2.6 + dy - 0.27, F2 + 0.012), (dx + 0.27, -2.6 + dy + 0.27, F2 + 0.07),
                  "MI_FabricRed")
    b.box("Furniture", (xi0, -5.5, F2), (xi0 + 0.6, -3.7, F2 + 0.9), "MI_Wood")    # the 床の間
    b.mark("objective", 0.0, -2.6, F2, 0.0, note="the 座敷: a private meeting")
    b.put("Office_Locker", -2.0, yb - 0.3, 0.0, z=F2)
    b.put("Rest_Table", -1.2, 3.0, 0.0, z=F2)
    b.put("Office_Safe", -2.2, 2.0, 90.0, z=F2)
    return {"note": "居酒屋: a 3 x 7 間 two-storey izakaya -- 暖簾, 赤提灯, a sliding front door; the L counter with 9 "
                    "stools and the open kitchen, the 0.3 m 小上がり with two low tables, a WC and the back door to the "
                    "alley; upstairs a 座敷 banquet room with its 床の間 and the staff room with the safe."}


# ── 雑居ビル: the narrow multi-tenant building of every Japanese downtown ─────────────────────────────────────────

def core_y(D, LV, TOP):
    """The y of a 雑居ビル's stair well's front (its landing); the lobby strip runs 1.3 m in front of it -- where a
    side fire exit goes (u = core_y - 0.65)."""
    rises = [(LV[i + 1] if i + 1 < len(LV) else TOP) - LV[i] for i in range(len(LV))]
    need = IK.STAIR_NEAR + (int(math.ceil(max(rises) / IK.RISER_MAX)) // 2 + 1) * IK.TREAD + 1.2
    return D / 2 - EXT_T - need


def zakkyo(b, W, D, LV, TOP, facade="MI_TileWhite", upper="MI_TileWhite", roof_house=True, lift=True,
           f1_sides=None, win_every=2.6, win_w=1.8):
    """The shell and the CORE of a 雑居ビル W x D (street -Y): one U-stair at the back-right (to the roof's 塔屋
    when roof_house), a lift beside it (every floor), a lobby strip in front of both, a WC room at the back-left
    per floor. Every floor's slab, its outer walls (f1_sides on the ground floor, windows on the front above) and
    the lobby / WC partitions. Returns the frame the caller fits out: {x0..yb, yc (the front room's back wall),
    rooms: (xi0, yf, xi1, yc), wc: (x0, y0, x1, y1), H(i), LV}."""
    x0, x1, y0, y1 = -W / 2, W / 2, -D / 2, D / 2
    xi0, xi1, yf, yb = x0 + EXT_T, x1 - EXT_T, y0 + EXT_T, y1 - EXT_T
    well = (xi1 - 2.2, core_y(D, LV, TOP), xi1, yb)
    wy0 = well[1]
    yc = wy0 - 1.3
    holes = {z: [] for z in LV + [TOP]}
    for i, z0 in enumerate(LV):
        z1 = LV[i + 1] if i + 1 < len(LV) else TOP
        last = i + 1 == len(LV)
        h = b.ustair(*well, z0, z1 - z0, near="s", cap=last and not roof_house)
        holes[z1].append(h)
    lx = well[0] - 0.15 - 0.8
    if lift:
        shaft = b.lift(lx, wy0 + 0.9, 1.6, 1.6, LV, faces=1, turned=True)
        for z in LV[1:]:
            holes[z].append(shaft)
    e = 0.02          # slabs stop 2 cm inside the facade: a slab edge flush with the wall's face z-fights
    for z in LV:
        b.slab(x0 + e, y0 + e, x1 - e, y1 - e, z, "MI_Terrazzo", holes=holes[z])
    roof(b, x0 + e, y0 + e, x1 - e, y1 - e, TOP, holes=holes[TOP] if roof_house else [], units=2)
    if roof_house:
        stair_house(b, well[0], well[1], well[2], well[3], TOP)
    else:
        b.box("Roof", (well[0], well[1], TOP - 0.2), (well[2], well[3], TOP), "MI_ConcreteSmooth")
    xw = (lx - 0.95) if lift else (well[0] - 0.2)
    for i, z0 in enumerate(LV):
        z1 = LV[i + 1] if i + 1 < len(LV) else TOP
        h = z1 - z0
        sides = f1_sides if (i == 0 and f1_sides is not None) else {
            "f": ((), band_windows(b, xi0 + 0.4, xi1 - 0.4, z0, h - 0.2, every=win_every, w=win_w))}
        ext(b, x0, y0, x1, y1, z0, h, facade if i == 0 else upper, sides)
        part(b, "y", xw, wy0, yb, z0, h - 0.2)
        part(b, "x", wy0, xi0, xw, z0, h - 0.2, doors=[((xi0 + xw) / 2, -1, 0.8, "slide", "door", 2.0)])
        b.put("WC_Toilet", (xi0 + xw) / 2, yb - 0.38, 180.0, z=z0)
        b.put("WC_Basin", xi0 + 0.3, yb - 1.9, 90.0, z=z0)
    return {"x0": x0, "x1": x1, "y0": y0, "y1": y1, "xi0": xi0, "xi1": xi1, "yf": yf, "yb": yb, "yc": yc,
            "well": well, "lx": lx, "xw": xw, "LV": LV, "TOP": TOP}


def front_wall(b, fr, z, h, doors=()):
    """The partition between the core's lobby strip and the front room(s), at yc."""
    part(b, "x", fr["yc"], fr["xi0"], fr["xi1"], z, h, doors=list(doors))


# ── 隠れ家 (city, small): a 3-storey 狭小住宅 townhouse on a 3 x 5 間 lot, with a built-in garage ────────────────────

def safehouse_city_small(b):
    x0, y0, x1, y1 = -2.73, -4.55, 2.73, 4.55
    xi0, xi1, yf, yb = x0 + EXT_T, x1 - EXT_T, y0 + EXT_T, y1 - EXT_T
    FL, F2, F3, TOP = 0.3, 3.1, 5.9, 8.5
    apron(b, -2.9, -6.5, 2.9, 4.8)
    GX = 0.5                                             # the garage x xi0..GX, the genkan + stair x GX+0.1..xi1
    step_y = -2.8
    well = (GX + 0.1, step_y, xi1, step_y + 4.8)
    h1 = b.ustair(*well, FL, F2 - FL, near="s")
    h2 = b.ustair(*well, F2, F3 - F2, near="s", cap=True)
    e = 0.02
    b.slab(x0 + e, y0 + e, x1 - e, y1 - e, 0.0, "MI_ConcreteSmooth")
    b.box("Structure", (GX + 0.1, step_y, 0.0), (xi1, step_y + 1.4, FL), "MI_Wood")        # the landing, 0.3 up
    b.box("Structure", (GX + 0.1, step_y - 0.1, 0.0), (xi1, step_y, FL), "MI_Wood")       # the agarikamachi
    b.box("Furniture", (xi1 - 0.38, yf + 0.15, 0.0), (xi1, step_y - 0.3, 0.95), "MI_Wood")  # the 下駄箱
    b.slab(x0 + e, y0 + e, x1 - e, y1 - e, F2, "MI_Wood", holes=[h1])
    b.slab(x0 + e, y0 + e, x1 - e, y1 - e, F3, "MI_Wood", holes=[h2])
    roof(b, x0 + e, y0 + e, x1 - e, y1 - e, TOP, units=1)
    ext(b, x0, y0, x1, y1, 0.0, F2, "MI_PaintedMetalDark", {
        "f": ([(-1.1, -1, 2.8, "", "open", 2.3), (1.62, -1, 0.9, "swing", "exit", 2.0)], []),
        "b": ([(-1.4, 1, 0.9, "swing", "exit", 2.0)], [])})
    ext(b, x0, y0, x1, y1, F2, F3 - F2, "MI_TileWhite", {
        "f": ((), [b.window(-1.0, F2, 3.0, 0.3, 2.3)]), "b": ((), [b.window(-1.0, F2, 1.6, 0.9, 2.0)])})
    ext(b, x0, y0, x1, y1, F3, TOP - F3, "MI_TileWhite", {
        "f": ((), [b.window(-1.0, F3, 2.4, 0.9, 2.2)]), "b": ((), [b.window(-1.0, F3, 0.8, 1.3, 2.0)])})
    b.box("Facade", (xi0, y0 - 0.25, 2.3), (0.3, y0, 2.7), "MI_PaintedMetalDark")     # the shutter box
    b.box("Facade", (1.0, y0 - 0.7, 2.3), (2.3, y0, 2.4), "MI_PaintedMetalDark")      # the door hood
    b.box("Facade", (2.4, y0 - 0.2, 1.3), (2.6, y0, 1.6), "MI_Steel")                # the mailbox
    # F1: the garage (a kei car), the workroom behind it, the WC behind the stair
    part(b, "y", GX, yf, 0.55, 0.0, F2 - 0.2)
    part(b, "x", 0.55, xi0, GX, 0.0, F2 - 0.2, doors=[(-1.1, 1, 0.9, "swing", "door", 2.0)])
    part(b, "x", step_y + 4.85, GX + 0.05, xi1, 0.0, F2 - 0.2)
    b.mark("vehicle", -1.1, -2.2, 0.0, 180.0, vehicle="KEC1", note="the built-in garage (a kei car)")
    b.put("Office_Desk", -2.35, 2.6, 90.0)
    b.put("Office_Chair", -1.7, 2.6, 270.0)
    b.put("Police_GunLocker", -2.45, 1.0, 90.0)
    for i, w in enumerate(("PIS1", "SMG1")):
        b.mark("weapon", -2.0, 0.8 + i * 0.5, 0.0, 270.0, weapon=w, note="the workroom's locker")
    part(b, "y", GX + 0.05, step_y + 4.85, yb, 0.0, F2 - 0.2, doors=[(3.3, -1, 0.8, "slide", "door", 2.0)])
    b.put("WC_Toilet", xi1 - 0.38, 3.3, 270.0)
    # F2: the LDK (the whole floor but the stair), 洗面所 + WC behind the stair
    part(b, "y", GX + 0.05, step_y + 1.4, step_y + 4.85, F2, F3 - F2 - 0.2)
    part(b, "y", GX + 0.05, yf, step_y, F2, F3 - F2 - 0.2)
    part(b, "y", GX + 0.05, step_y, step_y + 1.4, F2, F3 - F2 - 0.2, doors=[(step_y + 0.7, -1, 0.8, "slide", "door", 2.0)])
    part(b, "x", step_y + 4.85, GX + 0.05, xi1, F2, F3 - F2 - 0.2)
    part(b, "y", GX + 0.05, step_y + 4.85, yb, F2, F3 - F2 - 0.2, doors=[(2.9, -1, 0.8, "slide", "door", 2.0)])
    kitchen_run(b, xi0, -0.3, yb, F2, face=-1)
    b.put("Kitchen_Fridge", 0.05, yb - 0.4, 180.0, z=F2)
    b.put("Rest_Table", -1.2, 1.0, 0.0, z=F2)
    for dx in (-0.35, 0.35):
        b.put("Rest_Chair", -1.2 + dx, 0.25, 0.0, z=F2)
    b.put("Office_Sofa", -1.4, -3.6, 0.0, z=F2)
    b.put("WC_Toilet", xi1 - 0.38, 3.6, 270.0, z=F2)
    b.put("WC_Basin", 1.3, yb - 0.25, 180.0, z=F2)
    b.mark("spawn", -1.0, -1.5, F2, 180.0, team="player", note="the city safe house")
    # F3: the bedroom (front), the 浴室 (back); the stash behind the stair
    H3 = TOP - F3 - 0.2
    part(b, "y", GX + 0.05, yf, step_y, F3, H3)
    part(b, "y", GX + 0.05, step_y, step_y + 1.4, F3, H3, doors=[(step_y + 0.7, -1, 0.8, "swing", "door", 2.0)])
    part(b, "y", GX + 0.05, step_y + 1.4, yb, F3, H3, doors=[(3.3, -1, 0.8, "slide", "door", 2.0)])
    part(b, "x", 0.1, xi0, GX + 0.05, F3, H3, doors=[(-1.0, 1, 0.8, "slide", "door", 2.0)])
    part(b, "x", step_y + 4.85, GX + 0.05, xi1, F3, H3)
    b.put("Hotel_Bed", -1.55, -3.35, 90.0, z=F3)
    bath_unit(b, xi0, 1.8, GX - 0.8, yb, F3)
    b.put("WC_Basin", -2.3, 1.0, 90.0, z=F3)
    b.put("Shop_StockShelf", 2.2, 3.3, 270.0, z=F3)
    b.put("Office_Safe", 1.2, 4.05, 0.0, z=F3)
    b.mark("objective", 1.2, 3.6, F3, 0.0, note="the stash behind the wash room")
    return {"note": "隠れ家 (city, small): a three-storey 狭小住宅 on a 3 x 5 間 lot -- a built-in garage for a kei car "
                    "and the workroom with a gun locker on F1, genkan with the agarikamachi step; the LDK on F2 "
                    "(bathrooms go upstairs in a townhouse), the bedroom, bath and the stash on F3."}


def desk_islands(b, x0, x1, y0, y1, z, every_x=3.4, every_y=2.9):
    """島型 desk islands filling a room (x0..x1, y0..y1) at floor z, 1 m clear of its walls."""
    nx = max(1, int((x1 - x0 - 2.0) / every_x) + 1)
    ny = max(1, int((y1 - y0 - 2.4) / every_y) + 1)
    for i in range(nx):
        for j in range(ny):
            x = (x0 + x1) / 2 + (i - (nx - 1) / 2) * every_x
            y = (y0 + y1) / 2 + (j - (ny - 1) / 2) * every_y
            b.put("Office_DeskIsland", x, y, 0.0, z=z)
            chairs_around(b, x, y, 2, 0.6, 0.85, z=z)


def v_sign(b, x, y, z0, z1, mat, w=0.5, d=0.9):
    """袖看板: a vertical sign standing out from the facade (y = the wall's outer face, street -Y)."""
    b.box("Facade", (x - w / 2, y - d, z0), (x + w / 2, y, z1), mat)


# ── 隠れ家 (city, large): a 5-storey 雑居ビル; a front company below, the penthouse on the top two floors ──────────

def safehouse_city_large(b):
    LV, TOP = [0.0, 4.0, 7.3, 10.6, 13.9], 17.2
    fr = zakkyo(b, 7.28, 14.56, LV, TOP, facade="MI_PaintedMetalDark", upper="MI_TileBrown", f1_sides={
        "f": ([(-2.0, -1, 3.0, "", "open", 2.6), (2.1, -1, 1.6, "slide", "exit", 2.2)], []),
        "l": ([(core_y(14.56, LV, TOP) - 0.65, -1, 0.9, "swing", "exit", 2.0)], [])})
    xi0, xi1, yf, yc = fr["xi0"], fr["xi1"], fr["yf"], fr["yc"]
    apron(b, -3.8, -9.5, 3.8, 7.6)
    b.box("Facade", (xi0, fr["y0"] - 0.25, 2.65), (0.6, fr["y0"], 3.0), "MI_PaintedMetalDark")   # the shutter box
    sign(b, 1.0, 3.3, fr["y0"], 2.4, 2.9, "MI_Sign")                                   # the company plate
    b.box("Facade", (3.2, fr["y0"] - 0.35, 3.1), (3.5, fr["y0"] - 0.05, 3.4), "MI_PlasticDark")  # a camera
    # F1: the garage (one car) and the entrance lobby with the mailboxes
    part(b, "y", 0.3, yf, yc, 0.0, 3.8)
    front_wall(b, fr, 0.0, 3.8, [(-1.5, 1, 0.9, "swing", "door"), (2.1, 1, 2.0, "", "open", 2.3)])
    b.mark("vehicle", -2.0, -3.6, 0.0, 180.0, vehicle="SPC1", note="the garage behind the shutter")
    b.box("Furniture", (xi1 - 0.35, -5.5, 0.0), (xi1, -3.5, 1.5), "MI_Steel")          # the mailboxes
    b.mark("spawn", 2.1, -2.0, 0.0, 0.0, team="guard", note="the doorman")
    # F2 - F3: the front company (a 'trading company' office)
    for z in LV[1:3]:
        front_wall(b, fr, z, 3.1, [(1.8, 1, 0.9, "swing", "door")])
        desk_islands(b, xi0, xi1, yf, yc - 1.2, z)
        b.put("Office_Cabinet", xi0 + 0.3, yc - 1.2, 90.0, z=z)
        b.mark("spawn", -1.0, -3.0, z, 0.0, team="worker")
    # F4: the penthouse LDK
    z = LV[3]
    front_wall(b, fr, z, 3.1, [(1.8, 1, 0.9, "swing", "door")])
    kitchen_run(b, xi0, -0.6, yc, z, face=-1)
    b.put("Kitchen_Fridge", -0.2, yc - 0.4, 180.0, z=z)
    b.put("Office_MeetingTable", -1.6, -2.8, 0.0, z=z)
    for dx in (-1.0, 0.0, 1.0):
        b.put("Rest_Chair", -1.6 + dx, -3.75, 0.0, z=z)
        b.put("Rest_Chair", -1.6 + dx, -1.85, 180.0, z=z)
    b.put("Office_Sofa", 1.8, -5.9, 0.0, z=z)
    b.put("Office_Sofa", -1.8, -5.9, 0.0, z=z)
    b.put("Rest_Table", 0.0, -5.4, 90.0, z=z)
    b.mark("spawn", 0.0, -4.0, z, 180.0, team="player", note="the penthouse safe house")
    # F5: the master bedroom and the armoury / panic room behind a steel door
    z = LV[4]
    front_wall(b, fr, z, 3.1, [(-1.8, 1, 0.9, "swing", "door"), (2.3, 1, 0.9, "swing", "door")])
    part(b, "y", 0.6, yf, yc, z, 3.1)
    b.put("Hotel_Bed", -1.4, -5.6, 0.0, z=z)
    b.put("Office_Cabinet", -3.1, -3.0, 90.0, z=z)
    b.put("Police_GunRack", 2.1, yf + 0.3, 0.0, z=z)
    b.put("Police_GunLocker", xi1 - 0.3, -3.8, 270.0, z=z)
    b.put("Office_Safe", 1.0, -6.6, 0.0, z=z)
    b.put("Office_ServerRack", xi1 - 0.35, -2.1, 270.0, z=z)
    for i, w in enumerate(("ASR1", "ASR2", "SHG1", "SNR1", "SMG1", "PIS2")):
        b.mark("weapon", 1.2 + (i % 3) * 0.7, -5.9 + (i // 3) * 0.6, z, 180.0, weapon=w, note="the panic room")
    b.mark("objective", 2.0, -3.0, z, 0.0, note="the panic room: steel door, monitors, the safe")
    # the roof terrace
    b.put("Rest_Table", -1.5, -3.0, 0.0, z=TOP)
    b.put("Hotel_Lounger", 1.5, -4.5, 0.0, z=TOP)
    b.mark("cover", 0.0, -6.5, TOP, 180.0, note="the roof terrace over the street")
    return {"note": "隠れ家 (city, large): a five-storey 雑居ビル -- F1 a one-car garage behind a shutter and the "
                    "entrance lobby; F2-F3 the front company's office; F4 the penthouse LDK; F5 the bedroom and "
                    "the panic room (armoury, safe, monitors); a lift to every floor, one stair to the roof terrace."}


# ── メイドカフェ: an Akihabara 4-storey 雑居ビル -- a merch shop, two cafe floors, the staff floor ──────────────────

def maid_cafe(b):
    LV, TOP = [0.0, 4.0, 7.3, 10.6], 13.9
    fr = zakkyo(b, 6.37, 14.56, LV, TOP, facade="MI_TileWhite", upper="MI_TileWhite", f1_sides={
        "f": ([(-1.6, -1, 1.6, "slide", "exit", 2.2)],
              [Opening(-0.6, 2.8, 0.3, 3.4, glass="MI_GlassClear", frame="MI_PaintedMetal")]),
        "l": ([(core_y(14.56, LV, TOP) - 0.65, -1, 0.9, "swing", "exit", 2.0)], [])}, win_every=2.0, win_w=1.6)
    xi0, xi1, yf, yc, y0 = fr["xi0"], fr["xi1"], fr["yf"], fr["yc"], fr["y0"]
    apron(b, -3.4, -9.0, 3.4, 7.5)
    v_sign(b, 2.7, y0, 4.0, 13.0, "MI_SignPink")                                      # the tall 袖看板
    for z in (4.6, 7.9, 11.2):
        sign(b, -2.9, 1.8, y0, z + 1.9, z + 2.5, "MI_SignCyan")
    b.box("Facade", (-3.0, y0 - 1.6, 0.0), (-2.4, y0 - 1.0, 1.4), "MI_SignPink")      # the standing A-board
    b.mark("spawn", -1.5, y0 - 1.5, 0.0, 180.0, team="staff", note="the maid handing out flyers")
    # F1: the merch shop (goods, capsule-toy machines), the register
    front_wall(b, fr, 0.0, 3.8, [(0.0, 1, 1.8, "", "open", 2.3)])
    for y in (-5.0, -3.2):
        b.put("Shop_GondolaShort", 0.6, y, 0.0)
    for i in range(4):
        b.box("Furniture", (xi0 + 0.05, -6.6 + i * 0.6, 0.0), (xi0 + 0.6, -6.05 + i * 0.6, 1.6), "MI_SignPink")
    counter(b, 1.6, yc - 1.4, xi1, yc - 0.8, 0.0, 1.0)
    b.put("Shop_RegisterSmall", 2.3, yc - 1.1, 180.0, z=1.0)
    # F2: the cafe -- tables, a small stage at the window, the counter and a kitchen corner
    z = LV[1]
    front_wall(b, fr, z, 3.1, [(0.0, 1, 1.6, "", "open", 2.3)])
    b.box("Furniture", (xi0, yf, z), (xi1, yf + 1.4, z + 0.3), "MI_SignPink")          # the stage, 0.3 up
    for x in (-1.5, 1.2):
        for y in (-4.6, -2.8):
            b.put("Rest_Table", x, y, 0.0, z=z)
            b.put("Rest_Chair", x - 0.45, y, 90.0, z=z)
            b.put("Rest_Chair", x + 0.45, y, 270.0, z=z)
    counter(b, xi0, yc - 1.2, -0.9, yc - 0.6, z, 1.05)
    b.mark("spawn", -1.8, yc - 1.6, z, 180.0, team="staff", note="the maid at the counter")
    b.mark("spawn", 1.2, -2.0, z, 0.0, team="civilian")
    b.mark("objective", 0.0, yf + 0.7, z + 0.3, 180.0, note="the stage (a live song / photo spot)")
    # F3: the event hall -- a wider stage, rows of stools
    z = LV[2]
    front_wall(b, fr, z, 3.1, [(0.0, 1, 1.6, "", "open", 2.3)])
    b.box("Furniture", (xi0, yf, z), (xi1, yf + 2.0, z + 0.4), "MI_SignPink")
    b.box("Furniture", (xi0, yf, z + 0.4), (xi1, yf + 0.1, z + 2.9), "MI_SignCyan")     # the backdrop
    for y in (-3.8, -2.8):
        stools(b, -2.1, 2.1, y, z=z, every=0.7)
    # F4: the staff floor -- the changing room (lockers), the manager's desk and the takings safe
    z = LV[3]
    front_wall(b, fr, z, 3.1, [(1.5, 1, 0.9, "swing", "door")])
    part(b, "x", -3.8, xi0, xi1, z, 3.1, doors=[(1.5, 1, 0.9, "swing", "door")])
    b.put("Office_Locker", -2.6, yf + 0.3, 0.0, repeat=(5, 0.95, 0.0), z=z)
    b.put("Office_Desk", -1.0, -2.4, 180.0, z=z)
    b.put("Office_Chair", -1.0, -3.05, 0.0, z=z)
    b.put("Office_Safe", -2.7, -1.2, 90.0, z=z)
    b.mark("objective", -2.4, -1.2, z, 0.0, note="the takings safe")
    return {"note": "メイドカフェ: a four-storey Akihabara 雑居ビル -- F1 the merch shop with capsule-toy machines; F2 "
                    "the cafe (tables, the counter, a small stage at the window); F3 the event hall; F4 the staff "
                    "floor (lockers, the manager, the takings safe). A lift, one stair to the roof, a tall pink 袖看板."}


# ── 風俗ビル: a grey-zone adult-entertainment 雑居ビル in the nightlife district (歓楽街) ───────────────────────────

def adult_services(b):
    """Non-explicit by design: what a level needs is its SHAPE -- the 無料案内所-style front with the reception and a
    lit menu board, the waiting room, a host club lounge, the floors of small private rooms off a corridor, and the
    back office that keeps the takings (a heist / raid target), with a bouncer and cameras."""
    LV, TOP = [0.0, 4.0, 7.3, 10.6, 13.9], 17.2
    fr = zakkyo(b, 7.28, 16.38, LV, TOP, facade="MI_PaintedMetalDark", upper="MI_PaintedMetalDark",
                roof_house=False, f1_sides={
                    "f": ([(0.0, -1, 1.6, "slide", "exit", 2.2)], []),
                    "l": ([(core_y(16.38, LV, TOP) - 0.65, -1, 0.9, "swing", "exit", 2.0)], [])},
                win_every=3.0, win_w=1.0)
    xi0, xi1, yf, yc, y0 = fr["xi0"], fr["xi1"], fr["yf"], fr["yc"], fr["y0"]
    apron(b, -3.8, -10.0, 3.8, 8.5)
    v_sign(b, -3.2, y0, 3.2, 16.8, "MI_SignPink")
    v_sign(b, 3.2, y0, 3.2, 16.8, "MI_SignRed")
    for z in (4.2, 7.5, 10.8, 14.1):
        sign(b, -2.6, 2.6, y0, z + 2.2, z + 2.9, "MI_SignPink")
    b.box("Facade", (-3.64, y0 - 1.2, 2.9), (3.64, y0, 3.1), "MI_Gold")                # the gaudy canopy
    b.box("Facade", (-1.4, y0 - 0.25, 0.6), (-0.9, y0 - 0.05, 2.2), "MI_Light")       # the lit menu panels
    b.box("Facade", (0.9, y0 - 0.25, 0.6), (1.4, y0 - 0.05, 2.2), "MI_Light")
    b.box("Facade", (3.3, y0 - 0.35, 2.6), (3.6, y0 - 0.05, 2.9), "MI_PlasticDark")    # the camera
    b.mark("spawn", 2.0, y0 - 1.2, 0.0, 180.0, team="guard", note="the tout / bouncer at the door")
    # F1: reception (a counter with the menu board behind), the waiting room
    part(b, "x", -3.5, xi0, xi1, 0.0, 3.8, doors=[(1.8, 1, 0.9, "swing", "door")])
    counter(b, -2.6, -4.3, 0.2, -3.8, 0.0, 1.05, mat="MI_PaintedMetalDark", top="MI_Gold")
    b.box("Furniture", (-3.0, -3.64, 1.0), (0.6, -3.56, 2.4), "MI_Light")              # the menu board
    b.mark("spawn", -1.2, -3.9, 0.0, 180.0, team="staff", note="reception")
    front_wall(b, fr, 0.0, 3.8, [(1.8, 1, 0.9, "swing", "door")])
    b.put("Office_Sofa", -2.9, -1.7, 90.0)
    b.put("Office_Sofa", -1.0, -0.9, 180.0)
    b.put("Rest_Table", -1.8, -1.9, 0.0)
    # F2: the host club lounge -- box seats round low tables, the bar counter, the champagne-tower spot
    z = LV[1]
    front_wall(b, fr, z, 3.1, [(1.8, 1, 0.9, "swing", "door")])
    for x, y in ((-2.2, -5.6), (1.4, -5.6), (-2.2, -2.8)):
        b.put("Rest_BoothSofa", x, y, 0.0, z=z)
        b.put("Rest_Table", x, y + 0.9, 0.0, z=z)
    counter(b, 0.6, -2.6, xi1 - 0.5, -2.0, z, 1.1, mat="MI_PaintedMetalDark", top="MI_Gold")
    b.box("Furniture", (xi1 - 0.35, -3.5, z), (xi1, -1.2, z + 2.2), "MI_Light")        # the bottle wall
    b.mark("objective", 1.7, -3.9, z, 0.0, note="the champagne tower")
    b.mark("spawn", 2.0, -1.5, z, 180.0, team="staff")
    # F3 - F4: the private rooms (4 a floor) off a central corridor
    for z in LV[2:4]:
        front_wall(b, fr, z, 3.1, [(0.0, 1, 1.2, "", "open", 2.2)])
        ym = (yf + yc) / 2
        for c, sgn in ((-0.6, -1), (0.6, 1)):
            part(b, "y", c, yf, yc, z, 3.1, doors=[((yf + ym) / 2, sgn, 0.8, "slide", "door", 2.0),
                                                  ((ym + yc) / 2, sgn, 0.8, "slide", "door", 2.0)])
        for xa, xb in ((xi0, -0.6), (0.6, xi1)):
            part(b, "x", ym, xa, xb, z, 3.1)
            for ya, yb_ in ((yf, ym), (ym, yc)):
                bx = xa + 0.85 if xa < 0 else xb - 0.85
                b.put("Hotel_Bed", bx, (ya + yb_) / 2, 0.0, z=z)
        b.mark("spawn", 0.0, ym, z, 0.0, team="staff", note="the corridor")
    # F5: the back office -- the takings safe, security monitors, the manager
    z = LV[4]
    front_wall(b, fr, z, 3.1, [(1.8, 1, 0.9, "swing", "door")])
    b.put("Office_Desk", -1.2, -5.2, 180.0, z=z)
    b.put("Office_Chair", -1.2, -5.85, 0.0, z=z)
    for i in range(3):
        b.put("Office_ServerRack", xi0 + 0.35, -3.2 + i * 1.05, 90.0, z=z)
    b.put("Office_Safe", 2.6, yf + 0.4, 0.0, z=z)
    b.put("Office_Safe", 1.6, yf + 0.4, 0.0, z=z)
    b.put("Office_Sofa", 2.6, -2.4, 270.0, z=z)
    b.mark("objective", 2.1, yf + 1.0, z, 0.0, note="the takings safes")
    b.mark("spawn", -1.2, -4.5, z, 180.0, team="vip", note="the manager")
    b.mark("spawn", 0.5, -1.5, z, 0.0, team="guard")
    return {"note": "風俗ビル (grey-zone adult entertainment, non-explicit): a five-storey 雑居ビル -- F1 reception with "
                    "the lit menu board and the waiting room; F2 a host club lounge (box seats, the bar); F3-F4 four "
                    "private rooms a floor off a corridor; F5 the back office with the takings safes and the "
                    "camera monitors. A lift, one stair (no roof access), a bouncer at the door, pink 袖看板."}


def vestibule(b, x0, x1, y_front, y_in, z, h, door_w=1.8):
    """風除室: the windbreak vestibule between two sets of automatic doors (the outer one is the caller's EXIT)."""
    part(b, "y", x0, y_front, y_in, z, h, mat="MI_GlassClear")
    part(b, "y", x1, y_front, y_in, z, h, mat="MI_GlassClear")
    part(b, "x", y_in, x0, x1, z, h, doors=[((x0 + x1) / 2, -1, door_w, "slide", "door", 2.2)], mat="MI_GlassClear")


def wc_block(b, z, h, x0, x1, y_door, y_back, t=PART_T):
    """A restroom block: 男子 / 女子 / 多目的 (accessible) rooms side by side from x0 to x1, their doors (sliding, the
    accessible one 1.0 m) in the wall at y_door, the toilets against the far wall at y_back (either side of y_door)."""
    w = (x1 - x0) / 3.0
    sgn = 1 if y_back > y_door else -1
    doors = [(x0 + w * (i + 0.5), -sgn, 1.0 if i == 2 else 0.9, "slide", "door", 2.1) for i in range(3)]
    part(b, "x", y_door, x0, x1, z, h, doors=doors)
    for i in range(4):
        part(b, "y", x0 + w * i, min(y_door, y_back), max(y_door, y_back), z, h)
    rot = 0.0 if sgn > 0 else 180.0
    yt = y_back - sgn * 0.38
    for i in range(3):
        cx = x0 + w * (i + 0.5)
        b.put("WC_Toilet", cx, yt, rot, z=z)
        b.put("WC_Basin", x0 + w * i + 0.3, y_door + sgn * (abs(y_back - y_door) * 0.55), 90.0, z=z)
    b.put("WC_GrabRail", x0 + w * 2.5 + 0.5, yt, rot, z=z)
    b.put("WC_BabyTable", x1 - 0.3, y_door + sgn * (abs(y_back - y_door) * 0.55), 270.0, z=z)


def teller_counter(b, x0, x1, y0, y1, z=0.0, screen=True):
    """銀行の窓口: the counter (1.05 high), its glass screen above, a teller's chair behind every 1.8 m."""
    counter(b, x0, y0, x1, y1, z, 1.05, mat="MI_Wood", top="MI_Terrazzo")
    if screen:
        b.box("Furniture", (x0, (y0 + y1) / 2 - 0.01, z + 1.05), (x1, (y0 + y1) / 2 + 0.01, z + 1.65), "MI_GlassClear")
    x = x0 + 0.9
    while x < x1 - 0.5:
        b.put("Office_Chair", x, y1 + 0.55, 0.0, z=z)
        x += 1.8


def vault(b, x0, y0, x1, y1, z, h, door_u, door_side="f", t=0.45):
    """金庫室: a vault with 0.45 m walls and a 1.0 m steel door (a swing DOOR_ the game builds; the frame is steel)."""
    ops = []
    for s_, axis, c, a0, a1, sgn in (("f", "x", y0 + t / 2, x0, x1, -1), ("b", "x", y1 - t / 2, x0, x1, 1),
                                     ("l", "y", x0 + t / 2, y0 + t, y1 - t, -1), ("r", "y", x1 - t / 2, y0 + t, y1 - t, 1)):
        ops = openings(b, axis, c, z, [(door_u, sgn, 1.0, "swing", "door", 2.1)]) if s_ == door_side else []
        b.wall(axis, c, a0, a1, z, h, t, "MI_Steel", mat_out="MI_ConcreteSmooth", out_sign=sgn, ops=ops,
               group="Walls_%g" % z)


# ── 銀行 (small): a one-storey bank branch (出張所 / 小規模店舗) ─────────────────────────────────────────────────

def bank_small(b):
    x0, x1, y0, y1 = -7.0, 7.0, -6.0, 6.0
    H = 4.5
    xi0, xi1, yf, yb = x0 + EXT_T, x1 - EXT_T, y0 + EXT_T, y1 - EXT_T
    apron(b, -8.5, -9.5, 8.5, 7.5, "MI_TileWhite")
    b.slab(x0, y0, x1, y1, 0.0, "MI_Terrazzo")
    ext(b, x0, y0, x1, y1, 0.0, H, "MI_TileBrown", {
        "f": ([(-4.6, -1, 1.6, "slide", "exit", 2.2), (0.5, -1, 1.8, "slide", "exit", 2.2)],
              [Opening(3.0, 6.3, 0.6, 3.2, glass="MI_GlassClear", frame="MI_PaintedMetal")]),
        "b": ([(-1.0, 1, 0.9, "swing", "exit", 2.1)], []),
        "l": ((), band_windows(b, -1.0, 4.0, 0.0, H, every=3.0, w=1.4, head=2.2)),
    })
    roof(b, x0 + 0.02, y0 + 0.02, x1 - 0.02, y1 - 0.02, H, units=2)
    b.box("Facade", (x0, y0 - 0.2, 3.5), (x1, y0, 4.2), "MI_SignGreen")               # the bank's band sign
    b.box("Facade", (-2.2, y0 - 0.12, 0.9), (-1.8, y0, 1.3), "MI_Steel")             # the 夜間金庫 slot
    b.box("Facade", (-6.8, y0 - 1.6, 2.9), (-2.4, y0, 3.05), "MI_PaintedMetal")      # the ATM corner's canopy
    Hi = H - 0.2
    # the ATM corner (its own door, open after hours) and the door into the lobby
    part(b, "y", -2.5, yf, -2.5, 0.0, Hi, doors=[(-4.0, 1, 0.9, "slide", "door", 2.1)])
    part(b, "x", -2.5, xi0, -2.5, 0.0, Hi)
    for x in (-6.0, -4.9, -3.8):
        b.put("Shop_ATM", x, -2.95, 0.0)
    b.mark("objective", -4.9, -3.5, 0.0, 180.0, note="the ATMs (a cash-machine job)")
    # 風除室 and the lobby: the ticket machine, the waiting sofas
    vestibule(b, -0.6, 1.6, yf, -3.9, 0.0, Hi)
    b.put("Station_TicketMachine", 3.3, -1.0, 0.0)
    b.put("Hosp_WaitingBench", 3.8, -3.4, 0.0)
    b.put("Hosp_WaitingBench", 1.5, -1.3, 180.0)
    # the customer restroom: one 多目的トイレ (accessible, a baby table) behind the ATM corner
    part(b, "y", -4.6, -2.5, 0.0, 0.0, Hi, doors=[(-1.25, 1, 1.0, "slide", "door", 2.1)])
    part(b, "x", 0.0, xi0, -4.6, 0.0, Hi)
    b.put("WC_Toilet", xi0 + 0.38, -1.0, 90.0)
    b.put("WC_GrabRail", xi0 + 0.6, -0.4, 90.0)
    b.put("WC_Basin", -5.6, -2.2, 180.0)
    b.put("WC_BabyTable", -5.6, -0.25, 0.0)
    b.mark("spawn", 2.5, -2.5, 0.0, 0.0, team="civilian")
    b.mark("spawn", 5.5, -2.0, 0.0, 180.0, team="guard", note="the lobby guard")
    # the teller counter, the staff gate
    teller_counter(b, -4.4, 4.6, 0.0, 0.7)
    part(b, "x", 0.35, 4.6, xi1, 0.0, Hi, doors=[(5.7, -1, 0.9, "swing", "door", 2.1)])
    for x in (-5.9, -4.1, -2.3, -0.5):
        b.mark("spawn", x + 0.9, 1.35, 0.0, 180.0, team="staff")
    # the back office, the vault (金庫室), the manager, the staff room + WC, the 通用口 at the back
    for x in (-2.6, 0.6):
        b.put("Office_DeskIsland", x, 2.6, 0.0)
        chairs_around(b, x, 2.6, 2, 0.6, 0.85)
    vault(b, 2.5, 2.4, xi1, yb, 0.0, Hi, 5.0)
    b.put("Office_Safe", 5.9, 5.3, 0.0)
    b.put("Office_Safe", 4.9, 5.3, 0.0)
    b.put("Warehouse_RollCage", 3.4, 4.8, 0.0)
    b.mark("objective", 5.0, 4.2, 0.0, 0.0, note="the vault (金庫室): cash, the safes")
    part(b, "y", -3.5, 3.3, yb, 0.0, Hi, doors=[(4.5, -1, 0.8, "slide", "door", 2.0)])
    part(b, "x", 3.3, xi0, -3.5, 0.0, Hi, doors=[(-5.0, -1, 0.8, "swing", "door", 2.0)])
    b.put("Office_Locker", -6.3, 5.5, 0.0, repeat=(2, 0.95, 0.0))
    b.put("WC_Toilet", -4.2, yb - 0.38, 180.0)
    b.put("Office_Desk", 1.4, 5.0, 0.0)
    b.put("Office_Chair", 1.4, 4.35, 180.0)
    b.mark("spawn", 1.4, 4.3, 0.0, 180.0, team="vip", note="the branch manager (支店長)")
    return {"note": "銀行 (small): a one-storey branch -- the ATM corner with its own door, the 風除室, the lobby "
                    "(ticket machine, sofas), the teller counter with its glass screen, the back office, the vault "
                    "(0.45 m walls, a steel door), the staff room and WC, the 通用口 staff door at the back; a customer "
                    "多目的トイレ (accessible restroom) off the lobby."}


# ── 銀行 (large): a three-storey main branch (本支店) ─────────────────────────────────────────────────────────────

def bank_large(b):
    X0, X1, Y0, Y1 = -18.0, 18.0, -11.0, 11.0
    LV, TOP = [0.0, 5.0, 9.0], 13.0
    xi0, xi1, yf, yb = X0 + EXT_T, X1 - EXT_T, Y0 + EXT_T, Y1 - EXT_T
    apron(b, -20.0, -16.0, 20.0, 14.0, "MI_TileWhite")
    for x in (-15.0, -9.0, 9.0, 15.0):
        b.box("Site", (x - 1.0, -15.0, 0.0), (x + 1.0, -13.8, 0.6), "MI_StoneWall")      # planters / bollards
    wy = (4.4, yb)
    wellB = (xi0, wy[0], xi0 + 2.4, wy[1])
    wellA = (9.3, wy[0], 11.7, wy[1])
    shaft = b.lift(-14.3, 5.3, 1.8, 1.6, LV, faces=1, turned=True)
    holes = {z: [] for z in LV + [TOP]}
    for i, z0 in enumerate(LV):
        z1 = LV[i + 1] if i + 1 < len(LV) else TOP
        holes[z1].append(b.ustair(*wellB, z0, z1 - z0, near="s", cap=(z1 == TOP)))
        holes[z1].append(b.ustair(*wellA, z0, z1 - z0, near="s"))
        if z1 != TOP:
            holes[z1].append(shaft)
    e = 0.02
    for z in LV:
        b.slab(X0 + e, Y0 + e, X1 - e, Y1 - e, z, "MI_Terrazzo", holes=holes[z])
    roof(b, X0 + e, Y0 + e, X1 - e, Y1 - e, TOP, holes=holes[TOP][1:], units=6)
    stair_house(b, wellA[0], wellA[1], wellA[2], wellA[3], TOP)
    ext(b, X0, Y0, X1, Y1, 0.0, LV[1], "MI_StoneWall", {
        "f": ([(-14.4, -1, 1.8, "slide", "exit", 2.4), (0.0, -1, 2.4, "slide", "exit", 2.6)],
              [Opening(-10.5, -3.0, 0.4, 4.2, glass="MI_GlassClear", frame="MI_PaintedMetal"),
               Opening(3.0, 16.5, 0.4, 4.2, glass="MI_GlassClear", frame="MI_PaintedMetal")]),
        "b": ([(-11.6, 1, 1.0, "swing", "exit", 2.1), (14.9, 1, 3.2, "", "open", 3.2)], []),
        "l": ([(-2.0, -1, 1.0, "swing", "exit", 2.1)], []),
    })
    for i, z0 in enumerate(LV[1:]):
        z1 = LV[i + 2] if i + 2 < len(LV) else TOP
        ext(b, X0, Y0, X1, Y1, z0, z1 - z0, "MI_TileBeige", {
            "f": ((), band_windows(b, xi0 + 1.0, xi1 - 1.0, z0, 3.8, every=3.0, w=2.2)),
            "b": ((), band_windows(b, -12.0, 8.0, z0, 3.8, every=3.0, w=1.8)),
            "l": ((), band_windows(b, -9.0, 2.0, z0, 3.8, every=3.0, w=1.8)),
            "r": ((), band_windows(b, -9.0, 2.0, z0, 3.8, every=3.0, w=1.8))})
    b.box("Facade", (-6.0, Y0 - 0.25, 10.0), (6.0, Y0, 12.2), "MI_SignGreen")           # the bank's name board
    b.box("Facade", (-4.0, Y0 - 3.0, 4.2), (4.0, Y0, 4.45), "MI_PaintedMetal")         # the entrance canopy
    b.box("Facade", (-17.8, Y0 - 1.6, 3.2), (-11.0, Y0, 3.35), "MI_PaintedMetal")      # the ATM corner's canopy
    b.box("Facade", (-6.5, Y0 - 0.12, 0.9), (-6.0, Y0, 1.4), "MI_Steel")               # the 夜間金庫 slot
    b.box("Facade", (12.9, Y1, 3.2), (16.9, Y1 + 0.35, 3.6), "MI_PaintedMetalDark")    # the raised shutter
    Hi = LV[1] - 0.2
    # ── F1: the ATM corner, 風除室, the banking hall, the counters, the back office, the vault floor
    part(b, "y", -11.0, yf, -7.4, 0.0, Hi, doors=[(-9.0, 1, 1.0, "slide", "door", 2.1)])
    part(b, "x", -7.4, xi0, -11.0, 0.0, Hi)
    for x in (-16.8, -15.6, -13.2, -12.0):
        b.put("Shop_ATM", x, -7.85, 0.0)
    # the customers' restrooms (男子 / 女子 / 多目的) off a corridor that opens onto the hall
    wc_block(b, 0.0, Hi, xi0, -11.0, -2.9, -7.4)
    part(b, "y", -11.0, -7.4, -2.9, 0.0, Hi)
    b.mark("objective", -14.4, -6.2, 0.0, 180.0, note="the ATM corner")
    vestibule(b, -2.0, 2.0, yf, -8.6, 0.0, Hi, door_w=2.0)
    for x in (-6.0, 6.0):
        b.put("Hosp_WaitingBench", x, -5.5, 180.0)
        b.put("Hosp_WaitingBench", x, -3.6, 180.0)
    b.put("Station_TicketMachine", 3.2, -7.8, 0.0)
    b.mark("spawn", 0.0, -5.0, 0.0, 0.0, team="civilian")
    b.mark("spawn", 8.0, -7.5, 0.0, 180.0, team="guard", note="the hall guard")
    teller_counter(b, -10.5, 9.5, -1.6, -0.9)
    for x in (4.0, 6.0, 8.0):
        b.put("Rest_Chair", x, -2.2, 180.0)                                           # the low counters' chairs
    part(b, "x", -1.25, 9.5, xi1, 0.0, Hi, doors=[(13.0, -1, 1.0, "swing", "door", 2.1)])
    part(b, "x", -1.25, xi0, -10.5, 0.0, Hi)
    for x in range(-9, 9, 2):
        b.mark("spawn", x + 0.5, -0.4, 0.0, 180.0, team="staff") if x % 4 == 1 else None
    for x in (-7.0, -2.5, 2.0, 6.5):
        b.put("Office_DeskIsland", x, 1.7, 0.0)
        chairs_around(b, x, 1.7, 2, 0.6, 0.85)
    # the back strip (y 4.2 .. yb): stair B + lift | the vault | 貸金庫 | stair A | the cash-in-transit bay
    part(b, "x", 4.2, xi0 + 2.5, 9.2, 0.0, Hi, doors=[(-12.0, -1, 1.0, "swing", "door", 2.1)])
    part(b, "x", 4.2, 11.8, xi1, 0.0, Hi, doors=[(15.0, -1, 1.0, "swing", "door", 2.1)])
    part(b, "y", 11.8, 4.2, yb, 0.0, Hi)
    vault(b, -9.8, 4.6, 1.8, yb, 0.0, Hi, -4.0)
    for x in (-8.5, -7.0, -5.5):
        b.put("Office_Safe", x, 10.0, 0.0)
    b.put("Warehouse_RollCage", -1.5, 9.5, 0.0)
    b.put("Warehouse_RollCage", -0.5, 9.5, 0.0)
    b.mark("objective", -4.0, 7.5, 0.0, 0.0, note="the main vault (金庫室)")
    part(b, "y", 2.2, 4.6, yb, 0.0, Hi, doors=[(5.5, -1, 0.9, "swing", "door", 2.1)])
    b.put("Office_Cabinet", 8.8, 7.0, 270.0, repeat=(4, 0.0, 0.95))
    b.put("Office_Cabinet", 3.0, 8.5, 90.0, repeat=(3, 0.0, 0.95))
    b.mark("objective", 6.0, 8.0, 0.0, 0.0, note="貸金庫 (the safe-deposit boxes)")
    b.mark("vehicle", 14.9, 8.0, 0.0, 0.0, vehicle="CRT1", note="the cash-in-transit bay (現金輸送車)")
    b.mark("spawn", 14.0, 5.5, 0.0, 180.0, team="guard", note="the transit guards")
    # ── F2: consultation booths, the manager, the meeting room, staff
    z = LV[1]
    h2 = LV[2] - z - 0.2
    glass_part(b, "x", -3.0, xi0 + 2.5, xi1, z, h2, doors=[(-10.0, -1, 0.9, "swing", "door"),
                                                           (-4.0, -1, 0.9, "swing", "door"),
                                                           (2.0, -1, 0.9, "swing", "door"),
                                                           (8.0, -1, 0.9, "swing", "door"),
                                                           (14.0, -1, 0.9, "swing", "door")])
    for x in (-7.0, -1.0, 5.0, 11.0):
        part(b, "y", x, yf, -3.0, z, h2)
    for cx in (-10.0, -4.0, 2.0):
        b.put("Rest_Table", cx, -7.0, 0.0, z=z)
        b.put("Rest_Chair", cx, -7.75, 0.0, z=z)
        b.put("Rest_Chair", cx, -6.25, 180.0, z=z)
    b.put("Office_Desk", 8.0, -9.0, 180.0, z=z)
    b.put("Office_Chair", 8.0, -9.65, 0.0, z=z)
    b.put("Office_Sofa", 6.0, -5.5, 90.0, z=z)
    b.put("Office_Safe", 10.3, -9.8, 0.0, z=z)
    b.mark("spawn", 8.0, -8.3, z, 180.0, team="vip", note="the branch manager (支店長室)")
    b.put("Office_MeetingTable", 14.5, -7.0, 90.0, z=z)
    for x in (-8.0, -2.0, 4.0):
        b.put("Office_DeskIsland", x, 1.0, 0.0, z=z)
        chairs_around(b, x, 1.0, 2, 0.6, 0.85, z=z)
    part(b, "x", 4.2, xi0 + 2.5, -9.8, z, h2, doors=[(-12.0, -1, 1.0, "swing", "door", 2.1)])
    wc_block(b, z, h2, -9.8, -1.0, 4.2, yb)
    part(b, "x", 4.2, -1.0, 9.2, z, h2, doors=[(4.0, -1, 0.9, "swing", "door", 2.1)])
    b.put("Rest_Table", 4.0, 8.0, 0.0, z=z)
    # ── F3: the offices, the server room, the lockers, the staff canteen
    z = LV[2]
    h3 = TOP - z - 0.2
    part(b, "x", -3.0, xi0 + 2.5, xi1, z, h3, doors=[(-6.0, -1, 0.9, "swing", "door"),
                                                   (6.0, -1, 0.9, "swing", "door")])
    part(b, "y", 0.0, yf, -3.0, z, h3)
    for x in (-13.0, -9.0, -5.0):
        b.put("Office_DeskIsland", x, -7.0, 0.0, z=z)
        chairs_around(b, x, -7.0, 2, 0.6, 0.85, z=z)
    b.put("Office_ServerRack", 3.0, -9.5, 0.0, repeat=(6, 1.0, 0.0), z=z)
    b.mark("objective", 5.5, -6.5, z, 0.0, note="the server room")
    for x in (-8.0, -2.0, 4.0):
        b.put("Rest_Table", x, 1.0, 0.0, z=z)
    b.put("Office_Locker", 13.0, -0.5, 0.0, repeat=(4, 0.95, 0.0), z=z)
    part(b, "x", 4.2, xi0 + 2.5, -9.8, z, h3, doors=[(-12.0, -1, 1.0, "swing", "door", 2.1)])
    wc_block(b, z, h3, -9.8, -1.0, 4.2, yb)
    return {"note": "銀行 (large): a three-storey main branch -- F1 the ATM corner, the 風除室, the banking hall "
                    "(ticket machine, sofas), the high and low teller counters, the back office, the main vault, the "
                    "safe-deposit room and a cash-in-transit bay with its shutter, the customers' restrooms; every "
                    "floor a 男子 / 女子 / 多目的 restroom block; F2 consultation booths, the "
                    "manager (a safe), a meeting room; F3 offices, the server room, lockers, the canteen. Two stairs "
                    "(A to the roof), a lift."}


def bay_lines(b, x0, x1, y0, y1, z, along="y", pitch=2.5, mat="MI_PaintWhite"):
    """Parking-bay lines painted at z: bays 2.5 m wide across `along` between x0..x1 / y0..y1."""
    if along == "y":
        n = int((y1 - y0) / pitch)
        for k in range(n + 1):
            y = y0 + k * pitch
            b.box("Structure", (x0, y - 0.05, z), (x1, y + 0.05, z + 0.01), mat)
    else:
        n = int((x1 - x0) / pitch)
        for k in range(n + 1):
            x = x0 + k * pitch
            b.box("Structure", (x - 0.05, y0, z), (x + 0.05, y1, z + 0.01), mat)


# ── 立体駐車場 (自走式): a self-park multi-storey car park, ground + 3 decks (the top one open) ────────────────────

def parking_garage(b):
    """Cars drive UP the west ramps and DOWN the east ones: each ramp runs 20 m along Y for a 3.0 m storey (15 %,
    under the 17 % 駐車場法 limit), and the ramps of every storey stack in the same strip 3 m apart. Between them the
    decks: perpendicular bays (2.5 x 5.0) either side of a 6 m two-way aisle, cross aisles at both ends. A stair
    tower on the south-east corner for people (二方向: a second stair at the north-west)."""
    X0, X1, Y0, Y1 = -11.5, 11.5, -20.0, 20.0
    RW = 3.5                                   # a one-way ramp's width (Japan: >= 3.5 m)
    RY0, RY1 = -4.0, 16.0                      # every ramp's plan along Y
    LV = [0.0, 3.0, 6.0, 9.0]
    apron(b, -14.0, -26.0, 17.5, 22.0, "MI_AsphaltLot")
    strips = {"w": (X0, X0 + RW), "e": (X1 - RW, X1)}
    for z0, z1 in zip(LV[:-1], LV[1:]):
        # up (west): low end at the north, rising south; down (east): the same, so both stack
        for k, (xa, xb) in strips.items():
            ramp(b, xa, RY0, xb, RY1, z1, z0, "y", t=0.3)
            for x in (xa, xb - 0.2):
                _hexa(b, "Structure", [(x, RY0, z1), (x + 0.2, RY0, z1), (x + 0.2, RY1, z0), (x, RY1, z0),
                                       (x, RY0, z1 + 0.9), (x + 0.2, RY0, z1 + 0.9), (x + 0.2, RY1, z0 + 0.9),
                                       (x, RY1, z0 + 0.9)], "MI_ConcreteSmooth")
            b.box("Structure", (xa + 0.3, (RY0 + RY1) / 2 - 0.1, (z0 + z1) / 2 + 0.3), (xb - 0.3, (RY0 + RY1) / 2 + 0.1,
                  (z0 + z1) / 2 + 0.31), "MI_PaintYellow")            # a chevron mid-ramp (placeholder marking)
    hole = [(X0, RY0, X0 + RW, RY1), (X1 - RW, RY0, X1, RY1)]
    for i, z in enumerate(LV):
        b.slab(X0, Y0, X1, Y1, z, "MI_ConcreteSmooth", holes=hole if i else [], t=0.3)
        bay_lines(b, -8.0, -3.0, -14.0, 14.0, z + 0.001)
        bay_lines(b, 3.0, 8.0, -14.0, 14.0, z + 0.001)
        for x in (-8.0, 8.0, -3.0, 3.0):
            b.box("Structure", (x - 0.05, -14.0, z + 0.001), (x + 0.05, 14.0, z + 0.011), "MI_PaintWhite")
        for x in (-5.5, 5.5):
            b.box("Structure", (x - 0.5, -12.5, z), (x + 0.5, 12.5, z + 0.12), "MI_ConcreteSmooth")  # wheel stops
            b.box("Structure", (x - 0.1, -12.5, z + 0.12), (x + 0.1, 12.5, z + 0.13), "MI_PaintYellow")
        if i:
            for (xa, xb) in ((X0, X0 + RW), (X1 - RW, X1)):          # guard walls at the deck edge over the ramp well
                b.box("Structure", (xa + (RW if xa == X0 else -0.2), RY0, z), (xa + (RW + 0.2 if xa == X0 else 0.0),
                      RY1, z + 1.1), "MI_ConcreteSmooth")
            # the parapets round the deck (open at nothing: the stair doors cut them)
            b.box("Structure", (X0, Y0, z), (X1, Y0 + 0.2, z + 1.1), "MI_ConcreteSmooth")
            b.box("Structure", (X0, Y1 - 0.2, z), (X1, Y1, z + 1.1), "MI_ConcreteSmooth")
            b.box("Structure", (X0, Y0, z), (X0 + 0.2, Y1, z + 1.1), "MI_ConcreteSmooth")
            b.box("Structure", (X1 - 0.2, Y0, z), (X1, -19.45, z + 1.1), "MI_ConcreteSmooth")
            b.box("Structure", (X1 - 0.2, -18.25, z), (X1, -13.45, z + 1.1), "MI_ConcreteSmooth")
            b.box("Structure", (X1 - 0.2, -12.35, z), (X1, Y1, z + 1.1), "MI_ConcreteSmooth")
        # the columns (a 8 x 10 m grid) up to the next deck
        if z < LV[-1]:
            for x in (-8.0, -3.0, 3.0, 8.0):
                for y in (-19.4, -10.0, 0.0, 10.0, 19.4):
                    if abs(x) == 3.0 and abs(y) < 19:
                        continue
                    b.box("Structure", (x - 0.35, y - 0.35, z), (x + 0.35, y + 0.35, z + 2.7), "MI_ConcreteSmooth")
    # parked cars (markers), the entrance booth and barrier at the south
    for i, (x, y) in enumerate(((-5.5, -8.75), (5.5, 1.25), (-5.5, 6.25), (5.5, -11.25))):
        b.mark("vehicle", x, y, LV[i % 4], 90.0 if x < 0 else 270.0, vehicle=("KEC1", "SPC1", "TAX1", "CLC1")[i],
               note="a parked car")
    b.box("Site", (-1.2, -22.6, 0.0), (1.2, -21.2, 2.6), "MI_PaintedMetalDark")       # the gate booth
    b.box("Site", (-4.5, -21.9, 0.9), (-1.3, -21.8, 1.0), "MI_PaintYellow")          # the raised arm (placeholder)
    b.box("Site", (X0, Y0 - 0.3, 6.3), (X1, Y0, 7.6), "MI_SignYellow")                # the P sign band
    b.mark("spawn", 0.0, -22.0, 0.0, 180.0, team="staff", note="the attendant in the booth")
    # the stair tower on the south-east corner: every deck, and the roof
    TX0, TX1, TY0, TY1 = X1 + 0.35, X1 + 3.35, -19.8, -14.0
    well = (TX0 + 0.25, TY0 + 0.25, TX1 - 0.25, TY1 - 0.1)
    for z0, z1 in zip(LV[:-1], LV[1:]):
        b.ustair(*well, z0, z1 - z0, near="s", cap=(z1 == LV[-1]))
    for z in LV:
        b.box("Structure", (X1, -19.45, z - 0.3), (TX0 + 0.25, -18.25, z), "MI_ConcreteSmooth")  # the bridge to the deck
    for s_, axis, c, a0, a1, sgn in (("f", "x", TY0 + 0.1, TX0, TX1, -1), ("b", "x", TY1 - 0.1, TX0, TX1, 1),
                                     ("r", "y", TX1 - 0.1, TY0 + 0.2, TY1 - 0.2, 1)):
        ops = openings(b, axis, c, 0.0, [((TX0 + TX1) / 2, -1, 0.9, "swing", "exit", 2.1)]) if s_ == "f" else []
        b.wall(axis, c, a0, a1, 0.0, LV[-1] + 1.2, 0.2, "MI_Plaster", mat_out="MI_ConcreteSmooth", out_sign=sgn,
               ops=ops, group="Facade")
    ops = [Opening(-19.4, -18.3, z, z + 2.1) for z in LV]
    b.wall("y", TX0 + 0.1, TY0 + 0.2, TY1 - 0.2, 0.0, LV[-1] + 1.2, 0.2, "MI_Plaster", mat_out="MI_ConcreteSmooth",
           out_sign=-1, ops=ops, group="Facade")
    b.box("Roof", (TX0, TY0, LV[-1] + 1.2), (TX1, TY1, LV[-1] + 1.4), "MI_ConcreteSmooth")
    b.box("Roof", (TX0, TY0, LV[-1] + 1.4), (TX1, TY1, LV[-1] + 3.4), "MI_ConcreteSmooth")
    # a lift beside the stair tower (user, 2026-09-29), opening west onto every deck over a short bridge
    b.lift(X1 + 1.3, -12.9, 1.6, 1.6, LV, faces=1, turned=False)
    for z in LV:
        b.box("Structure", (X1, -13.4, z - 0.3), (X1 + 0.35, -12.4, z), "MI_ConcreteSmooth")
    return {"note": "立体駐車場 (自走式): a self-park car park 23 x 40 m, ground + three decks (the top one open to "
                    "the sky) -- up ramps on the west, down ramps on the east (20 m for each 3 m storey, 15 %), 2.5 x "
                    "5.0 m bays either side of a 6 m aisle, wheel stops, a gate booth and arm at the south entrance, a "
                    "stair tower on the south-east corner and a lift beside it to every deck."}


# ── 空港管制塔: the civil airport's control tower -- an operations block and a 36 m tower with a lift ─────────────

def airport_control_tower(b):
    X0, X1, Y0, Y1 = -12.0, 12.0, -7.0, 7.0
    TX0, TX1, TY0, TY1 = 3.0, 11.0, -1.0, 7.0            # the tower shaft (the block's back-right corner)
    F1, F2, BTOP = 0.0, 4.5, 9.0
    TL = [0.0, 4.5, 9.0, 13.5, 18.0, 22.5, 27.0, 31.5, 36.0]    # the tower's levels; the cab floor is the last
    CAB = TL[-1]
    apron(b, -16.0, -12.0, 16.0, 10.0)
    paint_bays(b, -12.5, 8, 2.5, -11.5, -8.0)
    # the block (the part outside the tower): two storeys, the tower's own walls run through it
    well = (TX0 + 0.3, TY0 + 0.95, TX0 + 2.9, TY1 - 0.3)
    holes = {z: [] for z in TL}
    for z0, z1 in zip(TL[:-1], TL[1:]):
        holes[z1].append(b.ustair(*well, z0, z1 - z0, near="s", cap=(z1 == CAB)))
    shaft = b.lift(TX0 + 5.3, TY0 + 2.7, 1.6, 1.6, TL, faces=1, turned=True)
    for z in TL[1:]:
        holes[z].append(shaft)
    e = 0.02
    b.slab(X0 + e, Y0 + e, X1 - e, Y1 - e, F1, "MI_Terrazzo")
    b.slab(X0 + e, Y0 + e, X1 - e, Y1 - e, F2, "MI_Terrazzo", holes=holes[F2])
    b.slab(X0 + e, Y0 + e, TX0, Y1 - e, BTOP, "MI_ConcreteSmooth", group="Roof")
    b.slab(TX0, Y0 + e, X1 - e, TY0, BTOP, "MI_ConcreteSmooth", group="Roof")
    b.parapet(X0 + e, Y0 + e, X1 - e, Y1 - e, BTOP, 0.8)
    for z in TL[2:-1]:
        b.slab(TX0 + 0.2, TY0 + 0.2, TX1 - 0.2, TY1 - 0.2, z, "MI_ConcreteSmooth", holes=holes[z])
    for z0, z1 in ((F1, F2), (F2, BTOP)):
        ext(b, X0, Y0, X1, Y1, z0, z1 - z0, "MI_PaintWhite", {
            "f": ([(-6.0, -1, 1.8, "slide", "exit", 2.2)] if z0 == F1 else (),
                  band_windows(b, -3.0, 10.0, z0, 4.0, every=3.0, w=2.0) +
                  (band_windows(b, -10.5, -8.0, z0, 4.0, every=3.0, w=2.0) if z0 == F2 else [])),
            "l": ([(3.0, -1, 1.0, "swing", "exit", 2.1)] if z0 == F1 else (),
                  band_windows(b, -4.0, 1.0, z0, 4.0, every=3.0, w=1.6))})
    # the shaft's walls above the block, slit windows at each level
    for s_, axis, c, a0, a1, sgn in (("f", "x", TY0 + 0.1, TX0, TX1, -1), ("b", "x", TY1 - 0.1, TX0, TX1, 1),
                                     ("l", "y", TX0 + 0.1, TY0 + 0.2, TY1 - 0.2, -1),
                                     ("r", "y", TX1 - 0.1, TY0 + 0.2, TY1 - 0.2, 1)):
        ops = [Opening((a0 + a1) / 2 - 0.4, (a0 + a1) / 2 + 0.4, z + 1.2, z + 2.6, glass="MI_GlassClear")
               for z in TL[2:-1]] if s_ in "fr" else []
        b.wall(axis, c, a0, a1, BTOP, CAB - BTOP, 0.2, "MI_Plaster", mat_out="MI_PaintWhite", out_sign=sgn, ops=ops,
               group="Facade")
    # inside the block the shaft's front and left walls are partitions, with a door from each floor
    for z0, z1 in ((F1, F2), (F2, BTOP)):
        part(b, "x", TY0, TX0, X1 - EXT_T, z0, z1 - z0 - 0.2, doors=[(TX0 + 1.6, -1, 1.0, "swing", "door", 2.1)])
        part(b, "y", TX0, TY0, Y1 - EXT_T, z0, z1 - z0 - 0.2)
    # F1: the lobby and its security desk, the operations office; F2: the approach radar room (dark) and briefing
    b.put("Office_Reception", -6.0, -3.5, 0.0)
    b.put("Station_TicketGate", -3.2, -2.2, 90.0)
    b.mark("spawn", -6.0, -2.8, F1, 180.0, team="guard", note="the lobby security desk")
    for x in (-9.0, -4.5):
        b.put("Office_DeskIsland", x, 3.5, 0.0)
        chairs_around(b, x, 3.5, 2, 0.6, 0.85)
    b.put("Office_ServerRack", 1.0, 6.4, 0.0, repeat=(2, 1.0, 0.0))
    for x in (-9.5, -7.0, -4.5):
        b.put("Office_Desk", x, 5.9, 0.0, z=F2)
        b.put("Office_Chair", x, 5.25, 180.0, z=F2)
    b.put("Office_MeetingTable", -4.0, -3.5, 0.0, z=F2)
    b.put("Office_Whiteboard", -10.0, -6.3, 0.0, z=F2)
    b.mark("spawn", -7.0, 4.8, F2, 0.0, team="worker", note="the approach controllers (radar room)")
    # the CAB: 14 x 14 m, glazed all round from 1.0 to 3.6 m, consoles along the glass
    CX0, CX1, CY0, CY1 = TX0 - 3.0, TX1 + 3.0, TY0 - 3.0, TY1 + 3.0
    b.slab(CX0, CY0, CX1, CY1, CAB, "MI_Fabric", holes=holes[CAB])
    for lo, hi in (((CX0, CY0), (CX1, TY0)), ((CX0, TY1), (CX1, CY1)), ((CX0, TY0), (TX0, TY1)),
                   ((TX1, TY0), (CX1, TY1))):                  # the cab's underside: a ring round the shaft
        b.box("Facade", (lo[0], lo[1], CAB - 1.2), (hi[0], hi[1], CAB - 0.2), "MI_PaintWhite")
    for s_, axis, c, a0, a1 in (("f", "x", CY0 + 0.1, CX0, CX1), ("b", "x", CY1 - 0.1, CX0, CX1),
                               ("l", "y", CX0 + 0.1, CY0 + 0.2, CY1 - 0.2), ("r", "y", CX1 - 0.1, CY0 + 0.2, CY1 - 0.2)):
        b.wall(axis, c, a0, a1, CAB, 4.0, 0.2, "MI_PaintWhite",
               ops=[Opening(a0 + 0.4, a1 - 0.4, CAB + 1.0, CAB + 3.6, glass="MI_GlassClear", frame="MI_PaintedMetal")],
               group="Facade")
    b.box("Roof", (CX0 - 0.8, CY0 - 0.8, CAB + 4.0), (CX1 + 0.8, CY1 + 0.8, CAB + 4.4), "MI_PaintWhite")
    b.box("Roof", (6.8, 2.8, CAB + 4.4), (7.2, 3.2, CAB + 9.0), "MI_Steel")             # the antenna mast
    b.box("Roof", (5.5, 1.5, CAB + 9.0), (8.5, 4.5, CAB + 9.3), "MI_Steel")             # the radar
    part(b, "x", TY0 - 0.2, TX0 - 0.3, TX1 + 0.3, CAB, 3.0, doors=[(TX0 + 1.6, -1, 1.0, "swing", "door", 2.1),
                                                               (TX0 + 5.3, -1, 1.4, "", "open", 2.2)])
    for x in (1.2, 4.2, 7.2, 10.2):
        b.put("Office_Desk", x, CY0 + 0.7, 180.0, z=CAB)
        b.put("Office_Chair", x, CY0 + 1.35, 0.0, z=CAB)
    for y in (0.5, 3.5):
        b.put("Office_Desk", CX0 + 0.7, y, 90.0, z=CAB)
        b.put("Office_Desk", CX1 - 0.7, y, 270.0, z=CAB)
    b.mark("spawn", 5.5, CY0 + 1.8, CAB, 180.0, team="worker", note="the tower controllers")
    b.mark("cover", 1.0, CY1 - 0.8, CAB, 0.0, note="a sniper's view over the runway")
    b.mark("objective", 7.0, CY0 + 0.7, CAB, 180.0, note="the tower's radio console")
    return {"note": "空港管制塔: the civil airport's control tower -- a two-storey operations block (lobby with "
                    "security, operations office, the approach-radar room, briefing) and a tower whose lift and "
                    "stair climb to a 14 x 14 m glass cab at 36 m (consoles all round, the radar on its roof)."}


# ── retail: a mall generator shared by the fashion building and the department store ───────────────────────────

def _free(rects, x0, y0, x1, y1):
    return not any(x0 < r[2] and x1 > r[0] and y0 < r[3] and y1 > r[1] for r in rects)


def clothes_rack(b, x, y, z, w=1.5, mat="MI_Fabric"):
    """A clothes rail (a hanging display), 1.5 x 0.6 x 1.5 m: two posts, the rail, the hung stock."""
    for dx in (-w / 2 + 0.03, w / 2 - 0.03):
        b.box("Furniture", (x + dx - 0.02, y - 0.02, z), (x + dx + 0.02, y + 0.02, z + 1.5), "MI_Steel")
    b.box("Furniture", (x - w / 2, y - 0.25, z + 0.55), (x + w / 2, y + 0.25, z + 1.45), mat)


def display_table(b, x, y, z, mat="MI_Wood"):
    b.box("Furniture", (x - 0.8, y - 0.5, z), (x + 0.8, y + 0.5, z + 0.8), mat)
    b.box("Furniture", (x - 0.7, y - 0.4, z + 0.8), (x + 0.7, y + 0.4, z + 0.95), "MI_Goods")


def fill_floor(b, kind, x0, y0, x1, y1, z, no, px=3.6, py=3.2):
    """Fill a sales floor rectangle with the fixtures of `kind`, skipping the `no` rectangles (cores, the atrium,
    the aisles in front of every door and escalator). One fixture per px x py cell."""
    nx = int((x1 - x0) / px)
    ny = int((y1 - y0) / py)
    for i in range(nx):
        for j in range(ny):
            cx = x0 + (i + 0.5) * (x1 - x0) / nx
            cy = y0 + (j + 0.5) * (y1 - y0) / ny
            if not _free(no, cx - 1.3, cy - 1.0, cx + 1.3, cy + 1.0):
                continue
            k = (i + j) % 3
            if kind == "fashion":
                clothes_rack(b, cx, cy, z, mat=("MI_Fabric", "MI_FabricRed", "MI_NorenNavy")[k])
            elif kind == "cosmetics":
                display_table(b, cx, cy, z, "MI_PaintWhite")
            elif kind in ("goods", "books"):
                b.put("Shop_Gondola" if kind == "goods" else "Shop_StockShelf", cx, cy, 0.0, z=z)
            elif kind == "electronics":
                display_table(b, cx, cy, z, "MI_PlasticDark")
            elif kind == "food":
                b.put(("Shop_DeliCounter", "Shop_OpenCase", "Shop_ProduceTable")[k], cx, cy, 0.0, z=z)
            elif kind == "restaurant":
                b.put("Rest_Table", cx, cy, 0.0, z=z)
                b.put("Rest_Chair", cx, cy - 0.75, 0.0, z=z)
                b.put("Rest_Chair", cx, cy + 0.75, 180.0, z=z)


def mall(b, W, D, LV, TOP, programme, facade, upper, pairs, lift_banks, name_sign, entrances):
    """A retail building W x D: an ATRIUM per escalator pair (up escalator +Y on its left, down on its right: tread
    0.4 m, a 25 deg walkable placeholder of an escalator), U-stairs in the four corners (二方向避難), lift banks
    (two cars each) at the back (and the front when two banks), a WC block beside each back stair, and the floors
    filled from `programme` (a kind per level). entrances: [(side, u, width)] on the ground floor."""
    X0, X1, Y0, Y1 = -W / 2, W / 2, -D / 2, D / 2
    xi0, xi1, yf, yb = X0 + EXT_T, X1 - EXT_T, Y0 + EXT_T, Y1 - EXT_T
    rises = [(LV[i + 1] if i + 1 < len(LV) else TOP) - LV[i] for i in range(len(LV))]
    SL = IK.STAIR_NEAR + (int(math.ceil(max(rises) / IK.RISER_MAX)) // 2 + 1) * IK.TREAD + 1.2
    wells = [((xi0, yb - SL, xi0 + 2.6, yb), "s"), ((xi1 - 2.6, yb - SL, xi1, yb), "s"),
             ((xi0, yf, xi0 + 2.6, yf + SL), "n"), ((xi1 - 2.6, yf, xi1, yf + SL), "n")]
    holes = {z: [] for z in LV + [TOP]}
    no = []                                      # where no fixture may stand
    for (w, near) in wells:
        for i, z0 in enumerate(LV):
            z1 = LV[i + 1] if i + 1 < len(LV) else TOP
            roofw = w is wells[1][0]
            holes[z1].append(b.ustair(*w, z0, z1 - z0, near=near, cap=(z1 == TOP and not roofw)))
        no.append((w[0] - 1.5, w[1] - 1.5, w[2] + 1.5, w[3] + 1.5))
    shafts = []
    for k, lb in enumerate(lift_banks):
        cx, turned_face = lb[0], lb[1]
        yc_ = lb[2] if len(lb) > 2 else (yb - 1.0 if turned_face == 1 else yf + 1.0)
        for dx in (-1.2, 1.2):
            sh = b.lift(cx + dx, yc_, 1.8, 1.6, LV, faces=turned_face, turned=True, door_w=1.0)
            shafts.append(sh)
        no.append((cx - 3.5, yc_ - 3.5, cx + 3.5, yc_ + 3.5))
    for z in LV[1:]:
        holes[z] += shafts
    esc_n = int(math.ceil(max(rises) / IK.RISER_MAX))
    EL = esc_n * 0.4
    for (ax, ay) in pairs:
        for i, z0 in enumerate(LV[:-1]):
            z1 = LV[i + 1]
            h_up = sstair(b, ax - 2.4, ax - 0.9, ay - EL / 2, z0, z1 - z0, 1, tread=0.4, mat="MI_Steel",
                          nosing="MI_PaintYellow")
            h_dn = sstair(b, ax + 0.9, ax + 2.4, ay + EL / 2, z0, z1 - z0, -1, tread=0.4, mat="MI_Steel",
                          nosing="MI_PaintYellow")
            holes[z1].append((ax - 2.7, ay - EL / 2, ax + 2.7, ay + EL / 2))
        for z in LV[1:]:                           # glass guards round the void, open at the escalators' ends
            for x in (ax - 2.8, ax + 2.7):
                b.box("Walls_%g" % z, (x, ay - EL / 2, z), (x + 0.1, ay + EL / 2, z + 1.1), "MI_GlassClear")
            b.box("Walls_%g" % z, (ax - 0.9, ay - EL / 2 - 0.1, z), (ax + 2.8, ay - EL / 2, z + 1.1), "MI_GlassClear")
            b.box("Walls_%g" % z, (ax - 2.8, ay + EL / 2, z), (ax + 0.9, ay + EL / 2 + 0.1, z + 1.1), "MI_GlassClear")
        no.append((ax - 3.0, ay - EL / 2 - 3.5, ax + 3.0, ay + EL / 2 + 3.5))
    e = 0.02
    for i, z in enumerate(LV):
        b.slab(X0 + e, Y0 + e, X1 - e, Y1 - e, z, "MI_Terrazzo", holes=holes[z])
    roof(b, X0 + e, Y0 + e, X1 - e, Y1 - e, TOP, holes=[holes[TOP][1]], units=8)
    stair_house(b, *wells[1][0], TOP)
    # the shell
    f1 = {}
    for side, u, w in entrances:
        d, wins = f1.get(side, ([], []))
        d.append((u, -1 if side in "fl" else 1, w, "slide", "exit", 2.4))
        f1[side] = (d, wins)
        n = (0.0, -1.0) if side == "f" else (0.0, 1.0) if side == "b" else (-1.0, 0.0) if side == "l" else (1.0, 0.0)
        cx = u if side in "fb" else (xi0 if side == "l" else xi1)
        cy = (yf if side == "f" else yb) if side in "fb" else u
        no.append((cx - w / 2 - 1.5, cy - 4.0, cx + w / 2 + 1.5, cy + 4.0) if side in "fb" else
                  (cx - 4.0, cy - w / 2 - 1.5, cx + 4.0, cy + w / 2 + 1.5))
    f_d, f_w = f1.get("f", ([], []))
    show = []
    cur = xi0 + 3.2
    for dd in sorted(f_d, key=lambda t: t[0]):
        if dd[0] - dd[2] / 2 - 0.4 > cur + 1.0:
            show.append(Opening(cur, dd[0] - dd[2] / 2 - 0.4, 0.4, 4.0, glass="MI_GlassShopfront" if False else "MI_GlassClear",
                                frame="MI_PaintedMetal"))
        cur = dd[0] + dd[2] / 2 + 0.4
    if xi1 - 3.2 > cur + 1.0:
        show.append(Opening(cur, xi1 - 3.2, 0.4, 4.0, glass="MI_GlassClear", frame="MI_PaintedMetal"))
    f1["f"] = (f_d, show)
    ext(b, X0, Y0, X1, Y1, 0.0, LV[1], facade, f1)
    for i, z0 in enumerate(LV[1:]):
        z1 = LV[i + 2] if i + 2 < len(LV) else TOP
        ext(b, X0, Y0, X1, Y1, z0, z1 - z0, upper, {
            "f": ((), [Opening(xi0 + 3.5, xi1 - 3.5, z0 + 0.9, z0 + 2.9, glass="MI_GlassClear", frame="MI_PaintedMetal")]
                  if i % 2 == 0 else ())})
    b.box("Facade", (-W / 4, Y0 - 0.3, TOP - 4.0), (W / 4, Y0, TOP - 0.8), name_sign)
    for x in (X0 + 1.0, X1 - 1.6):
        v_sign(b, x + 0.3, Y0, LV[1] + 0.5, TOP - 1.0, name_sign, w=0.6, d=1.0)
    # the WC blocks beside the back stairs (a men's / women's / accessible room behind one wall), every floor
    for i, z in enumerate(LV):
        h = (LV[i + 1] if i + 1 < len(LV) else TOP) - z - 0.2
        for (xa, xb) in ((xi0 + 2.8, xi0 + 9.0), (xi1 - 9.0, xi1 - 2.8)):
            if lift_banks and any(abs(((xa + xb) / 2) - lb[0]) < 5.0 for lb in lift_banks):
                continue
            ywc = yb - 4.2
            part(b, "x", ywc, xa, xb, z, h, doors=[(xa + 1.0, -1, 0.9, "slide", "door", 2.1),
                                                (xa + 3.1, -1, 1.0, "slide", "door", 2.1),
                                                (xb - 1.0, -1, 0.9, "slide", "door", 2.1)])
            part(b, "y", xa + 2.1, ywc, yb, z, h)
            part(b, "y", xb - 2.1, ywc, yb, z, h)
            part(b, "y", xa, ywc, yb, z, h)
            part(b, "y", xb, ywc, yb, z, h)
            for x in (xa + 0.6, xa + 1.5, xb - 1.5, xb - 0.6):
                b.put("WC_Toilet", x, yb - 0.38, 180.0, z=z)
            b.put("WC_Toilet", xa + 3.1, yb - 0.38, 180.0, z=z)
            b.put("WC_GrabRail", xa + 3.7, yb - 0.6, 180.0, z=z)
            no.append((xa - 1.5, ywc - 1.6, xb + 1.5, yb))
        kind = programme[i]
        fill_floor(b, kind, xi0 + 2.0, yf + 2.0, xi1 - 2.0, yb - 2.0, z, no)
        if kind == "restaurant":
            for x in (xi0 + 6.0, xi1 - 6.0):
                counter(b, x - 2.5, yf + 1.2, x + 2.5, yf + 1.8, z, 1.0)
        if i == 0:
            for x in (xi0 + 4.0, xi1 - 7.0):
                counter(b, x, yf + 7.0, x + 3.0, yf + 7.6, z, 1.0)
                b.put("Shop_Register", x + 1.5, yf + 7.3, 180.0, z=z + 1.0)
        b.mark("spawn", 0.0, yf + 3.0, z, 0.0, team="civilian")
        b.mark("spawn", xi1 - 5.0, 0.0, z, 90.0, team="staff")
    b.mark("spawn", 0.0, yf + 2.0, 0.0, 180.0, team="guard", note="the floor guard at the main entrance")
    return {"x0": X0, "y0": Y0, "xi0": xi0, "xi1": xi1, "yf": yf, "yb": yb}


def fashion_building(b):
    """駅前ファッションビル (a PARCO / マルイ class): 30 x 24 m, five storeys, one escalator atrium, two lifts."""
    mall(b, 30.0, 24.0, [0.0, 4.5, 9.0, 13.5, 18.0], 22.5,
         ["cosmetics", "fashion", "fashion", "electronics", "restaurant"], "MI_PaintedMetalDark", "MI_TileWhite",
         pairs=[(0.0, -1.5)], lift_banks=[(0.0, 1)], name_sign="MI_SignRed",
         entrances=[("f", -6.0, 2.4), ("f", 6.0, 2.4), ("l", -2.0, 1.8)])
    apron(b, -17.0, -18.0, 17.0, 14.0, "MI_TileWhite")
    return {"note": "ファッションビル: a five-storey station-front fashion building -- F1 cosmetics and goods with "
                    "the counters, F2-F3 fashion, F4 electronics / books, F5 the restaurant floor; an escalator "
                    "atrium (up and down), two lifts, four corner stairs (one to the roof), WC blocks each floor."}


def department_store(b):
    """新宿の百貨店 / 駅ビル (an Isetan / Lumine class): 72 x 48 m, seven storeys, two escalator atriums, two lift
    banks (back and front), four corner stairs, the food hall (デパ地下 -- here on the ground floor: the island has
    no basements below sea level), the restaurant floor, the roof garden."""
    LV, TOP = [0.0, 5.0, 9.5, 14.0, 18.5, 23.0, 27.5], 32.0
    mall(b, 72.0, 48.0, LV, TOP,
         ["food", "cosmetics", "fashion", "fashion", "goods", "books", "restaurant"],
         "MI_StoneWall", "MI_TileBeige", pairs=[(-14.0, -2.0), (14.0, -2.0)],
         lift_banks=[(0.0, 1), (0.0, 1, 6.0)], name_sign="MI_SignGreen",
         entrances=[("f", -24.0, 3.0), ("f", 0.0, 3.6), ("f", 24.0, 3.0), ("l", 6.0, 2.4), ("r", 6.0, 2.4)])
    apron(b, -40.0, -32.0, 40.0, 28.0, "MI_TileWhite")
    for x in (-20.0, -8.0, 8.0, 20.0):                                           # the roof garden's planters
        b.box("Roof", (x - 3.0, -12.0, TOP), (x + 3.0, -6.0, TOP + 0.6), "MI_StoneWall")
        b.box("Roof", (x - 2.8, -11.8, TOP + 0.6), (x + 2.8, -6.2, TOP + 0.62), "MI_Grass")
    b.box("Facade", (-36.0, -24.0 - 4.0, 5.2), (36.0, -24.0, 5.5), "MI_PaintedMetal")   # the long street canopy
    return {"note": "百貨店 / 駅ビル (Shinjuku class): a seven-storey 72 x 48 m department store -- the food hall on "
                    "F1, cosmetics F2, fashion F3-F4, household F5, books F6, the restaurant floor F7 and a roof "
                    "garden; two escalator atriums, two lift banks, four corner stairs (one to the roof), WC blocks "
                    "each floor, five entrances."}


# ── 区民センター (downtown civic centre): services, a hall, the library, the offices ─────────────────────────────

def civic_center(b):
    """A downtown 区民センター / 区役所出張所 (busy): 48 x 32 m, four storeys. F1 the 窓口 (住民票 / 戸籍 counters) with
    the ticket machine and rows of waiting seats, the information desk, a cafe corner, two entrances with 風除室;
    F2 the multi-purpose hall (a 0.9 m stage, rows of chairs) and meeting rooms; F3 the library; F4 the offices,
    the director and the 防災センター (disaster-control room). Four corner stairs, a lift bank, WC blocks."""
    LV, TOP = [0.0, 4.5, 8.5, 12.5], 16.5
    fr = mall(b, 48.0, 32.0, LV, TOP, ["none"] * 4, "MI_StoneWall", "MI_TileBeige", pairs=[],
              lift_banks=[(0.0, 1)], name_sign="MI_SignGreen", entrances=[("f", -10.0, 2.4), ("f", 10.0, 2.4)])
    xi0, xi1, yf, yb = fr["xi0"], fr["xi1"], fr["yf"], fr["yb"]
    apron(b, -28.0, -26.0, 28.0, 20.0, "MI_TileWhite")
    b.box("Site", (-6.0, -23.0, 0.0), (6.0, -19.0, 0.5), "MI_StoneWall")               # the plaza's planter
    b.box("Site", (-5.8, -22.8, 0.5), (5.8, -19.2, 0.52), "MI_Grass")
    b.box("Site", (-0.15, -21.2, 0.5), (0.15, -20.8, 9.0), "MI_Steel")                 # the flag pole
    b.box("Facade", (-16.0, -16.0 - 3.0, 4.0), (16.0, -16.0, 4.3), "MI_PaintedMetal")  # the canopy
    Hi = LV[1] - 0.2
    # F1
    for u in (-10.0, 10.0):
        vestibule(b, u - 2.0, u + 2.0, yf, yf + 2.6, 0.0, Hi, door_w=2.0)
    counter(b, -2.0, -9.0, 2.0, -8.3, 0.0, 1.05)
    b.mark("spawn", 0.0, -7.6, 0.0, 180.0, team="staff", note="the information desk")
    teller_counter(b, -14.0, 14.0, 2.0, 2.7, screen=False)
    for x in (-12.0, -6.0, 0.0, 6.0, 12.0):
        b.put("Station_TicketMachine" if x == 0.0 else "Hosp_WaitingBench", x, -1.2 if x else -4.8, 0.0 if x else 0.0)
        b.put("Hosp_WaitingBench", x + 1.5, -3.0, 0.0)
    for x in (-10.0, -4.0, 4.0, 10.0):
        b.put("Office_DeskIsland", x, 6.0, 0.0)
        chairs_around(b, x, 6.0, 2, 0.6, 0.85)
    for (x, y) in ((-19.5, -9.0), (-16.5, -9.0), (-19.5, -5.5)):
        b.put("Rest_Table", x, y, 0.0)
        b.put("Rest_Chair", x - 0.7, y, 90.0)
        b.put("Rest_Chair", x + 0.7, y, 270.0)
    counter(b, -21.0, -2.8, -17.0, -2.2, 0.0, 1.0)
    b.mark("spawn", -8.0, -2.0, 0.0, 0.0, team="civilian")
    b.mark("spawn", 8.0, -6.0, 0.0, 180.0, team="guard")
    # F2: the hall and the meeting rooms
    z = LV[1]
    h = LV[2] - z - 0.2
    part(b, "y", -12.2, yf + 7.0, 8.0, z, h, doors=[(-2.0, -1, 1.8, "swing", "door", 2.2)])
    part(b, "y", 12.2, yf + 7.0, 8.0, z, h, doors=[(-2.0, 1, 1.8, "swing", "door", 2.2)])
    part(b, "x", 8.0, -12.2, 12.2, z, h)
    part(b, "x", yf + 7.0, -12.2, 12.2, z, h, doors=[(0.0, -1, 1.8, "swing", "door", 2.2)])
    b.box("Furniture", (-9.0, 4.0, z), (9.0, 7.9, z + 0.9), "MI_Wood")                # the stage
    sstair(b, -11.8, -10.0, 1.4, z, 0.9, 1, rails=False, mat="MI_Wood")
    b.box("Furniture", (-10.0, 3.2, z), (-9.0, 7.9, z + 0.9), "MI_Wood")
    for y in (-6.0, -4.5, -3.0, -1.5, 0.0):
        stools(b, -8.0, 8.0, y, z=z, every=0.8, h=0.45)
    b.mark("objective", 0.0, 6.0, z + 0.9, 180.0, note="the stage (a speech, a ceremony)")
    for xa, xb in ((xi0 + 3.0, -12.3), (12.3, xi1 - 3.0)):
        part(b, "x", -2.0, xa, xb, z, h)
        for yy in (-9.0, 2.0):
            cx = (xa + xb) / 2
            b.put("Office_MeetingTable", cx, yy, 0.0, z=z)
            for dx in (-1.0, 0.0, 1.0):
                b.put("Office_Chair", cx + dx, yy - 0.95, 0.0, z=z)
                b.put("Office_Chair", cx + dx, yy + 0.95, 180.0, z=z)
    # F3: the library
    z = LV[2]
    for x in range(-18, 19, 4):
        for y in (-11.0, -7.5):
            b.put("Shop_StockShelf", float(x), y, 0.0, z=z)
    for x in (-12.0, -4.0, 4.0, 12.0):
        b.put("Office_MeetingTable", x, 2.0, 0.0, z=z)
        for dx in (-1.0, 0.0, 1.0):
            b.put("Rest_Chair", x + dx, 1.05, 0.0, z=z)
            b.put("Rest_Chair", x + dx, 2.95, 180.0, z=z)
    counter(b, -2.0, -2.8, 2.0, -2.2, z, 1.0)
    # F4: the offices, the director, the 防災センター
    z = LV[3]
    h = TOP - z - 0.2
    part(b, "y", 8.0, yf + 7.0, 6.0, z, h, doors=[(0.0, 1, 0.9, "swing", "door", 2.1)])
    part(b, "x", 6.0, 8.0, xi1 - 3.0, z, h)
    part(b, "x", -4.0, 8.0, xi1 - 3.0, z, h, doors=[(15.0, 1, 0.9, "swing", "door", 2.1)])
    for x in (-15.0, -9.0, -3.0, 3.0):
        for y in (-9.0, -4.0, 1.5):
            b.put("Office_DeskIsland", x, y, 0.0, z=z)
            chairs_around(b, x, y, 2, 0.6, 0.85, z=z)
    b.put("Office_Desk", 16.0, -12.0, 180.0, z=z)
    b.put("Office_Chair", 16.0, -12.65, 0.0, z=z)
    b.put("Office_Sofa", 13.0, -8.0, 90.0, z=z)
    b.mark("spawn", 16.0, -11.3, z, 180.0, team="vip", note="the centre's director")
    b.put("Office_ServerRack", 20.0, 1.0, 270.0, repeat=(3, 0.0, 1.05), z=z)
    b.put("Office_DeskIsland", 15.0, 1.5, 0.0, z=z)
    b.mark("objective", 15.0, 3.0, z, 0.0, note="the 防災センター (the building's cameras and PA)")
    return {"note": "区民センター (downtown civic centre, busy): four storeys 48 x 32 m -- F1 the 窓口 counters with "
                    "the ticket machine and waiting rows, the information desk, a cafe corner, two entrances with "
                    "風除室; F2 the multi-purpose hall (stage, rows of seats) and four meeting rooms; F3 the library; "
                    "F4 the offices, the director and the 防災センター. A smaller resident-area one is the library's "
                    "Civic_WardOffice placeholder."}


# ── 温泉旅館: a hot-spring inn in the snow mountains ───────────────────────────────────────────────────────────

def onsen_ryokan(b):
    """A two-storey wooden 温泉旅館, 36 x 20 m, and its 露天風呂 behind. Shoes off at the 玄関 (a big doma, the 下足箱,
    the agarikamachi up to a 0.3 m floor); the 帳場 (front desk), the lobby and the 売店; the 大浴場 split 男湯 / 女湯
    behind 暖簾 (脱衣所 -> 内湯 -> the outdoor bath in a bamboo-fenced court); the 宴会場 (a tatami banquet hall) and
    the kitchen; upstairs ten 和室 guest rooms (tatami, 床の間, 押入れ, a 広縁 by the window). Snow on the roof."""
    X0, X1, Y0, Y1 = -18.0, 18.0, -10.0, 10.0
    FL, F2, TOP = 0.3, 3.8, 7.0
    xi0, xi1, yf, yb = X0 + EXT_T, X1 - EXT_T, Y0 + EXT_T, Y1 - EXT_T
    apron(b, -21.0, -16.0, 21.0, 22.5, "MI_StoneWall")
    b.box("Site", (-21.0, -16.0, 0.0), (21.0, -13.0, 0.05), "MI_PaintWhite")          # snow along the drive
    # the stairs (front corners, landing inward), a lift by the front desk
    well_l = (xi0, yf, xi0 + 2.6, yf + 5.6)
    well_r = (xi1 - 2.6, yf, xi1, yf + 5.6)
    hl = b.ustair(*well_l, FL, F2 - FL, near="n", cap=True)
    hr = b.ustair(*well_r, FL, F2 - FL, near="n", cap=True)
    shaft = b.lift(7.5, -1.95, 1.6, 1.6, [FL, F2], faces=2, turned=True)     # opens north, onto the corridors
    e = 0.02
    tubs = []                                                    # the 内湯 tubs' pits, cut out of the floor
    for sx in (-1, 1):
        xa, xb = (xi0, -9.0) if sx < 0 else (9.0, xi1)
        ta, tb = (xa + 0.8, (xa + xb) / 2 - 0.2) if sx < 0 else ((xa + xb) / 2 + 0.2, xb - 0.8)
        tubs.append((ta + 0.3, 7.1, tb - 0.3, 9.3))
    b.slab(X0 + e, Y0 + e, X1 - e, Y1 - e, FL, "MI_Wood", holes=[(-3.0, Y0, 3.0, -7.0)] + tubs, t=FL + 0.2)
    b.box("Structure", (-3.0, Y0, -0.2), (3.0, -7.0, 0.0), "MI_StoneWall")             # the genkan doma at 0
    b.box("Site", (5.2, Y1, 0.0), (6.8, Y1 + 0.9, FL), "MI_StoneWall")                 # the kitchen door's step
    b.box("Structure", (-3.0, -7.1, 0.0), (3.0, -7.0, FL), "MI_Hinoki")                # the agarikamachi
    b.box("Furniture", (-2.9, yf + 0.3, 0.0), (-2.5, -7.3, 1.2), "MI_Wood")            # 下足箱 (shoe lockers)
    b.box("Furniture", (2.5, yf + 0.3, 0.0), (2.9, -7.3, 1.2), "MI_Wood")
    b.slab(X0 + e, Y0 + e, X1 - e, Y1 - e, F2, "MI_Wood", holes=[hl, hr, shaft])
    # the shell: dark timber below, plaster above; the roof with its snow
    ext(b, X0, Y0, X1, Y1, 0.0, F2, "MI_Wood", {
        "f": ([(0.0, -1, 2.4, "slide", "exit", 2.4)],
              band_windows(b, -15.0, -5.0, FL, 3.2, every=2.5, w=1.8, glass="MI_Shoji") +
              band_windows(b, 5.0, 15.0, FL, 3.2, every=2.5, w=1.8, glass="MI_Shoji")),
        "b": ([(-11.2, 1, 1.0, "slide", "exit", 2.1, FL), (11.2, 1, 1.0, "slide", "exit", 2.1, FL),
               (6.0, 1, 0.9, "swing", "exit", 2.1, FL)], []),
        "l": ((), band_windows(b, 0.0, 8.0, FL, 3.2, every=2.5, w=1.4, glass="MI_Shoji"))})
    ext(b, X0, Y0, X1, Y1, F2, TOP - F2, "MI_Plaster", {
        "f": ((), band_windows(b, xi0 + 1.0, xi1 - 1.0, F2, 3.0, every=3.64, w=2.6, sill=0.5, head=2.3)),
        "b": ((), band_windows(b, xi0 + 1.0, xi1 - 1.0, F2, 3.0, every=3.64, w=2.6, sill=0.5, head=2.3))})
    gable(b, X0, Y0, X1, Y1, TOP, 3.2, ridge="x", over=1.2, gable_mat="MI_Plaster")
    gable(b, X0, Y0, X1, Y1, TOP + 0.2, 3.2, ridge="x", over=1.2, t=0.15, mat="MI_PaintWhite")   # the snow on it
    b.box("Facade", (-4.0, Y0 - 3.5, 3.2), (4.0, Y0, 3.45), "MI_RoofSlate")            # the entrance porch roof
    b.box("Facade", (-4.1, Y0 - 3.6, 3.45), (4.1, Y0, 3.55), "MI_PaintWhite")
    for x in (-3.7, 3.7):
        b.box("Facade", (x - 0.15, Y0 - 3.35, 0.0), (x + 0.15, Y0 - 3.05, 3.2), "MI_Wood")
    noren(b, -1.2, 1.2, Y0 - 0.1, 2.35, "MI_NorenNavy")
    for x in (-3.3, 3.3):
        chochin(b, x, Y0 - 0.5, 2.1, "MI_PaintWhite")
    sign(b, -2.5, 2.5, Y0, 3.7, 4.4, "MI_Wood")
    Hi = F2 - FL - 0.2
    # F1: the lobby (帳場 on the right, sofas, the 売店 on the left), a corridor across, the baths, the banquet hall
    CY0, CY1 = 0.0, 1.8
    part(b, "x", CY1, xi0, xi1, FL, Hi, doors=[(-13.4, 1, 1.8, "", "open", 2.2), (13.4, 1, 1.8, "", "open", 2.2),
                                            (-4.0, 1, 1.8, "slide", "door", 2.1), (6.0, 1, 0.9, "swing", "door", 2.1)])
    counter(b, 9.5, -7.5, 13.5, -6.9, FL, 1.05, mat="MI_Wood", top="MI_Hinoki")
    b.mark("spawn", 11.5, -6.2, FL, 180.0, team="staff", note="the 女将 at the 帳場")
    for (x, y) in ((-2.0, -4.0), (2.0, -4.0)):
        b.put("Office_Sofa", x, y, 90.0 if x < 0 else 270.0, z=FL)
    b.put("Rest_Table", 0.0, -4.0, 90.0, z=FL)
    for y in (-6.5, -4.0, -1.5):
        b.put("Shop_GondolaShort", -10.5, y, 90.0, z=FL)
    counter(b, -14.5, -1.4, -12.0, -0.8, FL, 1.0)
    b.mark("spawn", 0.0, -6.0, FL, 180.0, team="civilian")
    # the 大浴場: 男湯 (west) and 女湯 (east), each 脱衣所 then 内湯; the outdoor bath through the back door
    for sx, name, nmat in ((-1, "男湯", "MI_NorenNavy"), (1, "女湯", "MI_FabricRed")):
        xa, xb = (xi0, -9.0) if sx < 0 else (9.0, xi1)
        part(b, "y", -9.0 if sx < 0 else 9.0, CY1, yb, FL, Hi)
        part(b, "x", 5.4, xa, xb, FL, Hi, doors=[(-13.4 * -sx * -1 if sx < 0 else 13.4, 1, 1.4, "slide", "door", 2.1)])
        noren(b, (-13.4 if sx < 0 else 13.4) - 0.9, (-13.4 if sx < 0 else 13.4) + 0.9, CY1 - 0.08, FL + 2.2, nmat)
        for k in range(6):                                            # the 脱衣所's basket shelves and basins
            b.box("Furniture", ((xa + 0.2) if sx < 0 else (xb - 0.6), 2.1 + k * 0.5, FL),
                  ((xa + 0.6) if sx < 0 else (xb - 0.2), 2.5 + k * 0.5, FL + 1.8), "MI_Hinoki")
        cx = (xa + xb) / 2
        b.box("Furniture", (cx - 0.3, 2.2, FL), (cx + 1.8, 2.8, FL + 0.85), "MI_Hinoki")
        # 内湯: a hinoki tub, the wash row along the dividing wall (stools, taps)
        ta, tb = (xa + 0.8, (xa + xb) / 2 - 0.2) if sx < 0 else ((xa + xb) / 2 + 0.2, xb - 0.8)   # the tub's half
        # the 内湯: a hinoki tub SUNK into the floor (its bottom at the ground, 0.3 below the floor), a 0.2 m rim, a
        # seat ledge (腰掛け) inside at 0.25 so a body steps in and out 0.2-0.25 m at a time; the water is a surface
        b.box("Furniture", (ta, 6.8, FL), (tb, 7.1, FL + 0.2), "MI_Hinoki")
        b.box("Furniture", (ta, 9.3, FL), (tb, yb, FL + 0.2), "MI_Hinoki")
        b.box("Furniture", (ta, 6.8, FL), (ta + 0.3, yb, FL + 0.2), "MI_Hinoki")
        b.box("Furniture", (tb - 0.3, 6.8, FL), (tb, yb, FL + 0.2), "MI_Hinoki")
        b.box("Furniture", (ta + 0.3, 7.1, -0.2), (tb - 0.3, 9.3, 0.0), "MI_Hinoki")         # the tub's floor
        b.box("Furniture", (ta + 0.3, 7.1, 0.0), (tb - 0.3, 7.55, 0.25), "MI_Hinoki")        # the seat ledge
        b.mark("water", (ta + tb) / 2, 8.2, FL + 0.15, 0.0, w=round(tb - ta - 0.6, 3), d=2.2, material="onsen",
               note="the 内湯's water surface (no collider)")
        wx = xb - 0.35 if sx < 0 else xa + 0.35
        for k in range(4):
            b.box("Furniture", (wx - 0.15, 5.9 + k * 0.3, FL + 0.9), (wx + 0.15, 6.0 + k * 0.3, FL + 1.0), "MI_Steel")
        b.mark("spawn", cx, 6.5, FL, 0.0, team="civilian", note=name)
    # 宴会場 (tatami banquet hall) and the kitchen
    part(b, "y", 3.0, CY1, yb, FL, Hi, doors=[(4.8, -1, 0.9, "swing", "door", 2.1)])
    tatami(b, -8.9, CY1 + 0.1, 2.9, yb, FL)
    for y in (4.0, 7.5):
        low_table(b, -3.0, y, FL + 0.012, 8.0, 0.8)
    b.box("Furniture", (-8.8, yb - 0.6, FL), (-6.8, yb, FL + 0.4), "MI_Wood")             # the 床の間
    b.mark("objective", -3.0, 6.0, FL, 0.0, note="the 宴会場 (a dinner meeting)")
    kitchen_run(b, 3.2, 5.2, yb, FL, face=-1)
    kitchen_run(b, 6.8, 8.8, yb, FL, face=-1)
    b.put("Kitchen_Fridge", 8.4, 3.0, 270.0, z=FL)
    b.put("Kitchen_PrepTable", 6.0, 5.2, 0.0, z=FL)
    # the outdoor baths (露天風呂) behind: a stone-rimmed pool each, a bamboo fence round each court
    for sx in (-1, 1):
        xa, xb = (-17.5, -8.0) if sx < 0 else (8.0, 17.5)
        for (lo, hi) in (((xa, 10.0), (xa + 0.15, 21.0)), ((xb - 0.15, 10.0), (xb, 21.0)),
                         ((xa, 20.85), (xb, 21.0))):
            b.box("Site", (lo[0], lo[1], 0.0), (hi[0], hi[1], 2.4), "MI_Wood")
        px0, px1 = (xa + 2.0, xb - 2.0)
        # the stone terrace at the floor's level round the pool; the pool SUNK to the ground inside a 0.2 m rim,
        # with a seat ledge along its house side; its water a surface marker
        for lo, hi in (((xa, 10.0), (xb, 13.0)), ((xa, 19.5), (xb, 21.0)), ((xa, 13.0), (px0, 19.5)),
                       ((px1, 13.0), (xb, 19.5))):
            b.box("Site", (lo[0], lo[1], 0.0), (hi[0], hi[1], FL), "MI_StoneWall")
        b.box("Site", (px0, 13.0, 0.0), (px1, 13.5, FL + 0.2), "MI_StoneWall")
        b.box("Site", (px0, 19.0, 0.0), (px1, 19.5, FL + 0.2), "MI_StoneWall")
        b.box("Site", (px0, 13.0, 0.0), (px0 + 0.5, 19.5, FL + 0.2), "MI_StoneWall")
        b.box("Site", (px1 - 0.5, 13.0, 0.0), (px1, 19.5, FL + 0.2), "MI_StoneWall")
        b.box("Site", (px0 + 0.5, 13.5, 0.0), (px1 - 0.5, 13.95, 0.25), "MI_StoneWall")   # the seat ledge
        b.mark("water", (px0 + px1) / 2, 16.25, FL + 0.15, 0.0, w=round(px1 - px0 - 1.0, 3), d=5.5, material="onsen",
               note="the 露天風呂's water surface (no collider)")
        for k in range(4):                                               # rocks round the rim
            rx = px0 + 1.0 + k * (px1 - px0 - 2.0) / 3
            b.box("Site", (rx - 0.5, 19.5, FL), (rx + 0.5, 20.4, FL + 0.9), "MI_StoneWall")
        b.box("Site", (xa + 0.3, 19.8, 0.0), (xb - 0.3, 20.8, 1.0), "MI_PaintWhite")    # the snow drift
        b.mark("objective", (xa + xb) / 2, 16.0, FL, 0.0, note="the 露天風呂 (outdoor bath) in the snow")
    # F2: ten 和室 guest rooms off a central corridor
    H2 = TOP - F2 - 0.2
    part(b, "x", -1.0, xi0 + 2.8, xi1 - 2.8, F2, H2, doors=[(-12.0, -1, 0.9, "slide", "door", 2.0),
                                                          (-6.0, -1, 0.9, "slide", "door", 2.0),
                                                          (0.0, -1, 0.9, "slide", "door", 2.0),
                                                          (5.4, -1, 0.9, "slide", "door", 2.0),
                                                          (7.5, -1, 1.0, "", "open", 2.1),
                                                          (12.0, -1, 0.9, "slide", "door", 2.0)])
    part(b, "x", 1.0, xi0, xi1, F2, H2, doors=[(-15.0, 1, 0.9, "slide", "door", 2.0),
                                            (-9.0, 1, 0.9, "slide", "door", 2.0),
                                            (-3.0, 1, 0.9, "slide", "door", 2.0),
                                            (3.0, 1, 0.9, "slide", "door", 2.0),
                                            (9.0, 1, 0.9, "slide", "door", 2.0),
                                            (15.0, 1, 0.9, "slide", "door", 2.0)])
    for x in (-9.0, -3.0, 3.0, 9.0):
        part(b, "y", x, yf, -1.0, F2, H2)
    for x in (-12.0, -6.0, 0.0, 6.0, 12.0):
        part(b, "y", x, 1.0, yb, F2, H2)
    part(b, "y", xi0 + 2.8, yf, -1.0, F2, H2)
    part(b, "y", xi1 - 2.8, yf, -1.0, F2, H2)
    fronts = [(-15.2 + 0.2, -9.0), (-9.0, -3.0), (-3.0, 3.0), (3.0, 9.0), (9.0, 15.2 - 0.2)]
    backs = [(xi0, -12.0), (-12.0, -6.0), (-6.0, 0.0), (0.0, 6.0), (6.0, 12.0), (12.0, xi1)]
    for (xa, xb), (ya, yb_) in [(r, (yf, -1.0)) for r in fronts] + [(r, (1.0, yb)) for r in backs]:
        cx = (xa + xb) / 2
        engawa = ya + 1.2 if ya < 0 else yb_ - 1.2                           # the 広縁 strip by the window
        if not (xa < 7.5 < xb and ya < -1.95 < yb_):   # the lift's room (the 休憩処 by the lift) has no tatami over it
            tatami(b, xa + 0.1, min(engawa, yb_ - 0.05) if ya < 0 else ya + 0.05, xb - 0.1,
                   yb_ - 0.05 if ya < 0 else engawa, F2)
        ty = (engawa + (-1.0)) / 2 if ya < 0 else (engawa + 1.0) / 2
        low_table(b, cx, ty, F2 + 0.012, 1.2, 0.9)
        b.put("Rest_Chair", cx - 0.6, (ya + 0.6) if ya < 0 else (yb_ - 0.6), 0.0, z=F2)
    b.mark("objective", 0.0, -6.0, F2, 0.0, note="a guest's room")
    return {"note": "温泉旅館 (a hot-spring inn in the snow mountains): two storeys 36 x 20 m -- the 玄関 (shoes off: "
                    "doma, 下足箱, agarikamachi), the 帳場, the lobby and the 売店; the 大浴場 split 男湯 / 女湯 behind "
                    "noren (脱衣所, a hinoki 内湯, the wash row) with doors out to two fenced 露天風呂 in the snow; the "
                    "宴会場 and the kitchen; upstairs eleven 和室 guest rooms; snow on the roof and along the drive. "
                    "The baths are sunk into the floor (a 0.2 m rim, a seat ledge) and their water is a MARK_water "
                    "surface drawn with the onsen water shader -- no collider, a body wades in."}


def camera(b, x, y, z, group="Site"):
    """A security camera on a bracket."""
    b.box(group, (x - 0.08, y - 0.08, z), (x + 0.08, y + 0.08, z + 0.35), "MI_Steel")
    b.box(group, (x - 0.12, y - 0.3, z + 0.35), (x + 0.12, y + 0.1, z + 0.55), "MI_PlasticDark")


def guard_post(b, x0, y0, x1, y1, door_side="b", door_u=None, h=2.8, facade="MI_PaintWhite"):
    """詰所 / 立番所: a small guard house with windows all round and one door (an EXIT_)."""
    b.slab(x0 + 0.02, y0 + 0.02, x1 - 0.02, y1 - 0.02, 0.0, "MI_TileBrown")
    u = door_u if door_u is not None else ((x0 + x1) / 2 if door_side in "fb" else (y0 + y1) / 2)
    out = 1 if door_side in "br" else -1
    sides = {s_: ((), [b.window((x0 + x1) / 2 if s_ in "fb" else (y0 + y1) / 2, 0.0,
                                 min(1.6, (x1 - x0 if s_ in "fb" else y1 - y0) - 1.2), 0.9, 2.1)])
             for s_ in "fblr" if s_ != door_side}
    sides[door_side] = ([(u, out, 0.9, "swing", "exit", 2.1)], [])
    ext(b, x0, y0, x1, y1, 0.0, h, facade, sides)
    b.box("Roof", (x0 - 0.4, y0 - 0.4, h), (x1 + 0.4, y1 + 0.4, h + 0.2), "MI_PaintedMetalDark")
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2                 # the desk against the wall opposite the door
    if door_side == "b":
        b.put("Office_Desk", cx, y0 + 0.6, 0.0)
        b.put("Office_Chair", cx, y0 + 1.25, 180.0)
    elif door_side == "f":
        b.put("Office_Desk", cx, y1 - 0.6, 180.0)
        b.put("Office_Chair", cx, y1 - 1.25, 0.0)
    elif door_side == "r":
        b.put("Office_Desk", x0 + 0.6, cy, 270.0)
        b.put("Office_Chair", x0 + 1.25, cy, 90.0)
    else:
        b.put("Office_Desk", x1 - 0.6, cy, 90.0)
        b.put("Office_Chair", x1 - 1.25, cy, 270.0)


# ── 邸宅 (high-security): a walled estate -- the gate checkpoint, the main house, the garage, the garden ──────

def secure_mansion(b):
    """A high-security Japanese estate (a tycoon's -- or an 組長's): a 64 x 50 m lot inside a 3 m wall with
    cameras; the pedestrian gate (a locked EXIT_) and the vehicle gate under a barrier, both watched from the 詰所
    (guard post); a 32 x 16 m two-storey main house (a raised 0.45 m floor, a grand genkan): 応接間, the guards'
    room and the 警備室 (monitors) at the front; the 大広間 (tatami hall with 床の間), the bath, the kitchen-dining
    at the back; upstairs the master's study (safe, gun locker), the PANIC ROOM, bedrooms. A three-car garage; a
    garden with a pond. Everything a raid / infiltration mission needs: two ways in, patrol routes, a vault."""
    LX0, LX1, LY0, LY1 = -32.0, 32.0, -25.0, 25.0
    apron(b, LX0, LY0, LX1, LY1, "MI_ConcreteSmooth")
    b.box("Site", (LX0 + 0.3, LY0 + 0.3, 0.0), (-4.0, -4.0, 0.02), "MI_Grass")              # the garden
    b.box("Site", (-24.0, -18.0, 0.0), (-12.0, -10.0, 0.025), "MI_PoolWater")              # the pond
    for (x, y) in ((-25.0, -9.0), (-11.0, -19.0), (-20.0, -8.5), (-8.0, -14.0)):
        b.box("Site", (x - 0.7, y - 0.5, 0.0), (x + 0.7, y + 0.5, 0.6), "MI_StoneWall")    # garden stones
    for (x, y) in ((-28.0, -21.0), (-6.0, -21.0), (-28.0, -7.0), (-15.0, -6.0)):
        b.box("Site", (x - 1.2, y - 1.2, 0.0), (x + 1.2, y + 1.2, 1.6), "MI_Grass")        # pruned shrubs
    # the wall (3 m, a tiled cap), the gates, the guard post, the cameras
    perimeter(b, LX0, LY0, LX1, LY1, 3.0, [("f", 10.0, 1.2), ("f", 18.0, 5.0)], t=0.35, mat="MI_Plaster",
              cap="MI_RoofSlate")
    b.door("x", LY0, 10.0, 0.0, -1, w=1.2, h=2.3, style="swing", exit=True, label="the pedestrian gate")
    for x in (9.2, 10.8, 15.3, 20.7):
        b.box("Site", (x - 0.25, LY0 - 0.25, 0.0), (x + 0.25, LY0 + 0.25, 3.3), "MI_StoneWall")   # gate posts
    b.box("Site", (9.0, LY0 - 0.6, 2.4), (11.0, LY0 + 0.3, 2.6), "MI_RoofSlate")         # the gate's little roof
    b.box("Site", (15.9, LY0 + 0.6, 0.0), (16.2, LY0 + 0.9, 1.1), "MI_PaintYellow")      # the barrier post
    b.box("Site", (16.0, LY0 + 0.65, 1.1), (16.1, LY0 + 0.85, 4.8), "MI_PaintWhite")      # its arm, raised
    b.box("Site", (21.0, LY0 + 0.4, 0.0), (26.0, LY0 + 0.55, 2.4), "MI_Steel")            # the sliding gate, open
    guard_post(b, 11.6, -24.4, 14.8, -21.4, door_side="b")
    b.mark("spawn", 13.2, -22.9, 0.0, 180.0, team="guard", note="the gate guard (詰所)")
    b.mark("spawn", 18.0, -22.0, 0.0, 180.0, team="guard", note="the barrier")
    for (x, y) in ((LX0 + 0.2, LY0 + 0.2), (LX1 - 0.2, LY0 + 0.2), (LX0 + 0.2, LY1 - 0.2), (LX1 - 0.2, LY1 - 0.2),
                   (8.5, LY0 + 0.2), (21.0, LY0 + 0.2)):
        camera(b, x, y, 3.08)
    for (x, y) in ((-30.0, 0.0), (30.0, 0.0), (0.0, 23.0)):
        b.mark("spawn", x, y, 0.0, 90.0, team="guard", note="a wall patrol")
    # the main house: a raised floor over a foundation, the genkan's doma at DOMA
    X0, X1, Y0, Y1 = -16.0, 16.0, -2.0, 14.0
    xi0, xi1, yf, yb = X0 + EXT_T, X1 - EXT_T, Y0 + EXT_T, Y1 - EXT_T
    F1, F2, TOP = HOUSE_FLOOR, HOUSE_FLOOR + 3.3, HOUSE_FLOOR + 6.4
    CY0, CY1 = 1.2, 3.0                             # the front corridor (the 廊下)
    well = (-3.9, CY1, -1.3, CY1 + 5.4)
    hole = b.ustair(*well, F1, F2 - F1, near="s", cap=True)
    for lo, hi in (((X0, Y0), (X1, Y0 + EXT_T)), ((X0, Y1 - EXT_T), (X1, Y1)), ((X0, Y0), (X0 + EXT_T, Y1)),
                   ((X1 - EXT_T, Y0), (X1, Y1))):
        b.box("Facade", (lo[0], lo[1], 0.0), (hi[0], hi[1], DOMA), "MI_StoneWall")
    b.slab(xi0, yf, xi1, yb, F1, "MI_Wood", holes=[(-2.0, Y0, 2.0, CY0)], t=HOUSE_FLOOR)
    b.box("Structure", (-2.0, Y0, 0.0), (2.0, CY0, DOMA), "MI_StoneWall")               # the doma
    b.box("Structure", (-2.0, CY0 - 0.12, DOMA), (2.0, CY0, F1), "MI_Hinoki")           # the 式台 step
    b.slab(xi0, yf, xi1, yb, F2, "MI_Wood", holes=[hole])
    ext(b, X0, Y0, X1, Y1, DOMA, F2 - DOMA, "MI_Plaster", {
        "f": ([(0.0, -1, 1.8, "slide", "exit", 2.2)],
              band_windows(b, -15.0, -3.0, F1, 3.0, every=3.0, w=1.8, glass="MI_Shoji") +
              band_windows(b, 3.0, 15.0, F1, 3.0, every=3.0, w=1.8)),
        "b": ([(12.0, 1, 0.9, "swing", "exit", 2.1, F1 - DOMA)],
              band_windows(b, -15.0, -5.0, F1, 3.0, every=3.6, w=2.6, sill=0.4, glass="MI_Shoji")),
    })
    ext(b, X0, Y0, X1, Y1, F2, TOP - F2, "MI_Plaster", {
        "f": ((), band_windows(b, -15.0, 15.0, F2, 2.9, every=3.4, w=1.6)),
        "b": ((), band_windows(b, -15.0, 15.0, F2, 2.9, every=3.4, w=1.6))})
    b.box("Facade", (X0 - 0.5, Y0 - 0.9, F2 - 0.3), (X1 + 0.5, Y1 + 0.9, F2 - 0.1), "MI_RoofSlate")   # the 下屋 eave
    gable(b, X0, Y0, X1, Y1, TOP, 3.0, ridge="x", over=1.0, gable_mat="MI_Plaster")
    b.box("Facade", (-3.5, Y0 - 4.5, 3.0), (3.5, Y0, 3.25), "MI_RoofSlate")             # the porte-cochère
    for x in (-3.2, 3.2):
        b.box("Facade", (x - 0.2, Y0 - 4.3, 0.0), (x + 0.2, Y0 - 3.9, 3.0), "MI_Wood")
    b.box("Site", (-2.2, Y0 - 1.0, 0.0), (2.2, Y0, DOMA), "MI_StoneWall")               # the entrance step
    camera(b, 3.4, Y0 - 4.0, 2.6)
    Hi = F2 - F1 - 0.2
    # F1 -- the front: the guards' room, the 待合, the 警備室, the 応接間; the corridor; the back: the 大広間,
    # the stair, the bath, the WC, the kitchen-dining
    part(b, "x", CY0, xi0, -2.0, F1, Hi, doors=[(-12.0, -1, 0.9, "swing", "door", 2.1),
                                             (-5.0, -1, 0.9, "slide", "door", 2.1)])
    part(b, "x", CY0, 2.0, xi1, F1, Hi, doors=[(5.0, -1, 0.9, "swing", "door", 2.1),
                                            (11.5, -1, 0.9, "swing", "door", 2.1)])
    part(b, "y", -2.0, yf, CY0, F1, Hi)
    part(b, "y", 2.0, yf, CY0, F1, Hi)
    part(b, "y", -8.0, yf, CY0, F1, Hi)
    part(b, "y", 8.0, yf, CY0, F1, Hi)
    for (x, y) in ((-14.5, -0.5), (-10.2, -0.5)):
        b.put("Fire_Bunk", x, y, 90.0, z=F1)
    b.mark("spawn", -12.0, 0.0, F1, 0.0, team="guard", note="the guards' room")
    b.put("Office_ServerRack", 2.5, -1.0, 90.0, repeat=(2, 1.0, 0.0), z=F1)
    b.put("Office_Desk", 6.9, -0.8, 180.0, z=F1)
    b.put("Office_Chair", 6.9, -0.15, 0.0, z=F1)
    b.mark("objective", 6.9, 0.4, F1, 0.0, note="the 警備室: the camera monitors and the gate control")
    b.put("Office_Sofa", 10.5, -0.8, 0.0, z=F1)
    b.put("Office_Sofa", 14.5, -0.1, 270.0, z=F1)
    b.put("Rest_Table", 13.2, -0.5, 0.0, z=F1)
    part(b, "x", CY1, xi0, xi1, F1, Hi, doors=[(-9.0, 1, 1.8, "slide", "door", 2.1), (0.6, 1, 0.8, "slide", "door", 2.1),
                                            (3.5, 1, 0.8, "slide", "door", 2.1), (9.0, 1, 1.2, "", "open", 2.2)])
    part(b, "y", -4.0, CY1, yb, F1, Hi)
    part(b, "y", -1.2, CY1, yb, F1, Hi)
    part(b, "y", 2.4, CY1, yb, F1, Hi)
    part(b, "y", 4.6, CY1, yb, F1, Hi)
    part(b, "x", 7.0, -1.2, 2.4, F1, Hi, doors=[(0.6, 1, 0.8, "slide", "door", 2.0)])
    part(b, "x", 8.6, -3.9, -1.3, F1, Hi)
    tatami(b, xi0, CY1 + 0.06, -4.06, yb, F1)
    b.box("Furniture", (xi0, yb - 0.8, F1), (xi0 + 2.6, yb, F1 + 0.5), "MI_Wood")        # the 床の間
    b.box("Furniture", (-7.0, yb - 0.4, F1 + 1.9), (-5.0, yb, F1 + 2.3), "MI_Hinoki")    # the 神棚
    low_table(b, -10.0, 8.5, F1 + 0.012, 5.0, 1.2)
    b.mark("objective", -10.0, 11.5, F1, 180.0, note="the 大広間: the boss's meeting hall")
    b.mark("spawn", -10.0, 12.2, F1, 180.0, team="vip", note="the master, in the 大広間")
    b.put("WC_Basin", -0.9, 4.6, 90.0, z=F1)
    bath_unit(b, -1.1, 7.1, 2.3, yb, F1)
    b.put("WC_Toilet", 3.5, 6.2, 180.0, z=F1)
    kitchen_run(b, 5.0, 11.0, yb, F1, face=-1)
    b.put("Kitchen_Fridge", 13.0, yb - 0.4, 180.0, z=F1)
    b.put("Office_MeetingTable", 10.0, 7.5, 0.0, z=F1)
    for dx in (-1.0, 0.0, 1.0):
        b.put("Rest_Chair", 10.0 + dx, 6.55, 0.0, z=F1)
        b.put("Rest_Chair", 10.0 + dx, 8.45, 180.0, z=F1)
    # F2 -- the master's study (the safe, the gun locker), the PANIC ROOM, the bedrooms, a bath and a WC
    H2 = TOP - F2 - 0.2
    part(b, "x", CY0, xi0, xi1, F2, H2, doors=[(-11.0, -1, 0.9, "swing", "door", 2.1),
                                            (-3.0, -1, 0.9, "swing", "door", 2.1),
                                            (11.0, -1, 0.9, "swing", "door", 2.1)])
    part(b, "y", -6.0, yf, CY0, F2, H2)
    part(b, "y", 8.0, yf, CY0, F2, H2)
    vault(b, 2.5, yf, 8.0 - 0.06, CY0 - 0.06, F2, H2, 0.9, door_side="l")                 # the panic room
    b.put("Hotel_Bed", -14.0, -0.4, 90.0, z=F2)
    b.put("Office_Desk", -3.0, -1.0, 180.0, z=F2)
    b.put("Office_Chair", -3.0, -0.35, 0.0, z=F2)
    b.put("Office_Safe", -5.4, -1.3, 90.0, z=F2)
    b.put("Police_GunLocker", 1.8, -0.4, 270.0, z=F2)
    for i, w in enumerate(("PIS2", "REV1", "SMG1", "SHG1")):
        b.mark("weapon", 1.2, -1.2 + i * 0.4, F2, 90.0, weapon=w, note="the study's gun locker")
    b.mark("objective", -5.0, -1.3, F2, 0.0, note="the study's safe (the ledger)")
    b.put("Office_ServerRack", 7.3, -0.8, 270.0, z=F2)
    b.mark("objective", 5.2, -0.2, F2, 0.0, note="the PANIC ROOM (0.45 m steel walls; its door off the study)")
    b.put("Hotel_Bed", 14.3, -0.4, 90.0, z=F2)
    part(b, "x", CY1, xi0, xi1, F2, H2, doors=[(-9.0, 1, 0.9, "swing", "door", 2.1), (0.6, 1, 0.8, "slide", "door", 2.1),
                                            (3.5, 1, 0.8, "slide", "door", 2.1), (9.0, 1, 0.9, "swing", "door", 2.1)])
    part(b, "y", -4.0, CY1, yb, F2, H2)
    part(b, "y", -1.2, CY1 + 5.4, yb, F2, H2)
    part(b, "y", -1.2, CY1, CY1 + 5.4, F2, H2)
    part(b, "y", 2.4, CY1, yb, F2, H2)
    part(b, "y", 4.6, CY1, yb, F2, H2)
    part(b, "x", 8.6, -3.9, -1.3, F2, H2)
    tatami(b, xi0, CY1 + 0.06, -4.06, yb, F2)
    b.put("Hotel_Bed", -10.0, 10.0, 90.0, z=F2)
    bath_unit(b, -1.1, CY1 + 0.1, 2.3, yb, F2)
    b.put("WC_Toilet", 3.5, yb - 0.38, 180.0, z=F2)
    b.put("Office_Sofa", 10.0, 10.0, 0.0, z=F2)
    b.put("Rest_Table", 10.0, 8.0, 0.0, z=F2)
    # the garage: three open bays under one roof, east of the house
    GX0, GX1, GY0, GY1 = 18.0, 30.0, 0.0, 10.0
    b.slab(GX0 + 0.02, GY0 + 0.02, GX1 - 0.02, GY1 - 0.02, 0.0, "MI_ConcreteSmooth")
    for x in (GX0, GX1 - 0.25):
        b.box("Facade", (x, GY0, 0.0), (x + 0.25, GY1, 3.2), "MI_Plaster")
    b.box("Facade", (GX0, GY1 - 0.25, 0.0), (GX1, GY1, 3.2), "MI_Plaster")
    b.box("Facade", (GX0 - 0.4, GY0 - 0.6, 3.2), (GX1 + 0.4, GY1 + 0.4, 3.45), "MI_RoofSlate")
    for i, v in enumerate(("CLC1", "SPC1", "CRT1")):
        b.mark("vehicle", 20.0 + i * 4.0, 5.0, 0.0, 180.0, vehicle=v, note="the estate's garage")
    return {"note": "邸宅 (high-security estate): a 64 x 50 m walled lot -- a 3 m wall with cameras, the pedestrian "
                    "gate (a locked EXIT_) and the barrier-controlled vehicle gate watched from the 詰所; the main "
                    "house (two storeys, a raised floor, the grand genkan under a porte-cochère): guards' room, 待合, "
                    "警備室, 応接間, the tatami 大広間 with 床の間 and 神棚, bath, WC, kitchen-dining and a back door; "
                    "upstairs the study (safe, gun locker), the PANIC ROOM, bedrooms; a three-car garage; a garden "
                    "with a pond and stones; wall patrol spawns."}


PLANS = {"SafeHouseSmall": safehouse_small, "SafeHouseLarge": safehouse_large, "Izakaya": izakaya, "SafeHouseCitySmall": safehouse_city_small,
         "SafeHouseCityLarge": safehouse_city_large, "MaidCafe": maid_cafe, "AdultServices": adult_services,
         "BankSmall": bank_small, "BankLarge": bank_large,
         "ParkingGarage": parking_garage, "AirportControlTower": airport_control_tower,
         "FashionBuilding": fashion_building, "DepartmentStore": department_store,
         "CivicCenter": civic_center, "OnsenRyokan": onsen_ryokan,
         "SecureMansion": secure_mansion}
