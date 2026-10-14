"""Civic, leisure, military and airside buildings for kits/library (user, 2026-09-28): PLACEHOLDER massings an artist
replaces by hand in library.blend. Imported by library_procedural.build_all. Ours, CC0.

Frame as every library piece: Z up, origin at the footprint (or plot) centre on the ground, the STREET side facing -Y
(Godot +Z). Each building is its real Japanese size: numbers measured from PLATEAU named buildings
(tools/plateau2json/measure_named_buildings.py, CC BY 4.0 measurement reference, credited) where PLATEAU has the class,
public record otherwise (a fighter's and an airliner's dimensions). What the game assumes about each is its EDIT_NOTE
(shown on the piece in Blender); the list of what to replace is kits/library/ARTIST_NOTES.md "Civic placeholders".

The Japanese look these aim for, in massing terms: flat roofs with parapets and rooftop plant, 塔屋 stair houses,
horizontal ribbon windows on public buildings (tile or concrete spandrels), a building's name on a board, emergency
buildings in their colours (fire: red bay shutters and a 訓練塔; police: a 赤色灯 lamp and the emblem).
"""
import math

ST = 3.8          # a public building's storey (m): PLATEAU h/storey p50 for offices and civic buildings is 3.7-4.0


def ribbon_block(b, x0, x1, y0, y1, z0, storeys, h=ST, wall="MI_TileBeige", glass="MI_Window", sides="fblr",
                 sill=1.0, ground=None):
    """A block of `storeys` storeys from z0 with RIBBON windows: a solid core, and on each named side a window band per
    storey (sill `sill` m of spandrel, a band to 0.4 m under the next floor) standing 0.03 m proud, stopping 0.8 m
    short of each corner. `ground` = a material for a glazed ground storey (a lobby), else it is ribboned too.
    Returns the roof height."""
    top = z0 + storeys * h
    b.box((x0, y0, z0), (x1, y1, top), wall)
    for k in range(storeys):
        zb = z0 + k * h
        g = ground if (k == 0 and ground) else glass
        lo, hi = (zb + 0.3, zb + h - 0.5) if (k == 0 and ground) else (zb + sill, zb + h - 0.4)
        for s in sides:
            if s == "f":
                b.box((x0 + 0.8, y0 - 0.03, lo), (x1 - 0.8, y0, hi), g)
            elif s == "b":
                b.box((x0 + 0.8, y1, lo), (x1 - 0.8, y1 + 0.03, hi), g)
            elif s == "l":
                b.box((x0 - 0.03, y0 + 0.8, lo), (x0, y1 - 0.8, hi), g)
            elif s == "r":
                b.box((x1, y0 + 0.8, lo), (x1 + 0.03, y1 - 0.8, hi), g)
    return top


def punched_block(b, x0, x1, y0, y1, z0, storeys, h=3.0, wall="MI_TileWhite", glass="MI_Window", bay=3.6, win=1.8,
                  sides="fb", balcony=None):
    """A block with PUNCHED windows every `bay` m (a hotel, a barracks, flats); `balcony` = a material for a slab
    and rail along each storey of the front (a resort hotel's balconies)."""
    top = z0 + storeys * h
    b.box((x0, y0, z0), (x1, y1, top), wall)
    for k in range(storeys):
        zb = z0 + k * h
        for s in sides:
            n = max(1, int((x1 - x0) / bay)) if s in "fb" else max(1, int((y1 - y0) / bay))
            for i in range(n):
                if s in "fb":
                    c = x0 + (x1 - x0) * (i + 0.5) / n
                    y = y0 - 0.03 if s == "f" else y1
                    b.box((c - win / 2, y, zb + 0.9), (c + win / 2, y + 0.03, zb + h - 0.5), glass)
                else:
                    c = y0 + (y1 - y0) * (i + 0.5) / n
                    x = x0 - 0.03 if s == "l" else x1
                    b.box((x, c - win / 2, zb + 0.9), (x + 0.03, c + win / 2, zb + h - 0.5), glass)
        if balcony and k > 0:
            b.box((x0 + 0.5, y0 - 1.4, zb - 0.15), (x1 - 0.5, y0, zb + 0.05), balcony)
            b.box((x0 + 0.5, y0 - 1.45, zb + 0.05), (x1 - 0.5, y0 - 1.35, zb + 1.1), balcony)
    return top


def roof(b, x0, x1, y0, y1, z, parapet=1.1, units=0, stair=True, mat="MI_ConcreteSmooth"):
    """A flat roof: a parapet round the edge, `units` rooftop AC units in a row, and a 塔屋 stair house."""
    t = 0.25
    for (a0, b0, a1, b1) in ((x0, y0, x1, y0 + t), (x0, y1 - t, x1, y1), (x0, y0, x0 + t, y1), (x1 - t, y0, x1, y1)):
        b.box((a0, b0, z), (a1, b1, z + parapet), mat)
    for i in range(units):
        cx = x0 + 3.0 + i * 2.6
        if cx + 1.0 > x1 - 5.0:
            break
        b.box((cx, y1 - 4.0, z), (cx + 1.8, y1 - 2.8, z + 1.3), "MI_PlasticWhite")
    if stair:
        b.box((x1 - 6.5, y1 - 6.0, z), (x1 - 2.0, y1 - 1.5, z + 3.2), mat)


def sign(b, x0, x1, y, z0, z1, mat="MI_Sign"):
    """A name board on a front face (-Y), 0.15 m proud."""
    b.box((x0, y - 0.15, z0), (x1, y, z1), mat)


def canopy(b, x0, x1, y0, y1, z, mat="MI_PaintedMetal", posts=True):
    b.box((x0, y0, z), (x1, y1, z + 0.35), mat)
    if posts:
        for x in (x0 + 0.3, x1 - 0.3):
            b.box((x - 0.15, y0 + 0.15, 0.0), (x + 0.15, y0 + 0.45, z), mat)


def fence(b, x0, x1, y0, y1, h=1.8, gaps=(), mat="MI_PaintedMetalDark", post=3.0):
    """A plot fence (a rail at the top and bottom, posts every `post` m); `gaps` = [(side, centre, width)] openings,
    sides f(-Y) b(+Y) l(-X) r(+X)."""
    runs = {"f": (x0, x1, y0, True), "b": (x0, x1, y1, True), "l": (y0, y1, x0, False), "r": (y0, y1, x1, False)}
    for s, (a0, a1, c, along_x) in runs.items():
        cuts = sorted((cc - w / 2, cc + w / 2) for ss, cc, w in gaps if ss == s)
        pieces, cur = [], a0
        for g0, g1 in cuts:
            pieces.append((cur, g0))
            cur = g1
        pieces.append((cur, a1))
        for p0, p1 in pieces:
            if p1 - p0 < 0.2:
                continue
            for zb, zt in ((0.1, 0.2), (h - 0.1, h)):
                if along_x:
                    b.box((p0, c - 0.03, zb), (p1, c + 0.03, zt), mat)
                else:
                    b.box((c - 0.03, p0, zb), (c + 0.03, p1, zt), mat)
            n = max(1, int((p1 - p0) / post))
            for i in range(n + 1):
                p = p0 + (p1 - p0) * i / n
                if along_x:
                    b.box((p - 0.04, c - 0.04, 0.0), (p + 0.04, c + 0.04, h), mat)
                else:
                    b.box((c - 0.04, p - 0.04, 0.0), (c + 0.04, p + 0.04, h), mat)
            # the mesh between the rails, as one thin panel
            if along_x:
                b.box((p0, c - 0.01, 0.2), (p1, c + 0.01, h - 0.1), "MI_Steel")
            else:
                b.box((c - 0.01, p0, 0.2), (c + 0.01, p1, h - 0.1), "MI_Steel")


def ground(b, x0, x1, y0, y1, mat, z=0.02):
    """A surface on the plot, its top `z` above the ground (paint on the lot)."""
    b.box((x0, y0, z - 0.04), (x1, y1, z), mat)


def gable(b, cx, cy, z, hx, hy, rise, mat, along="x"):
    """A gabled roof (two sloping planes, a ridge along `along`) over a hx x hy half footprint from height z."""
    if along == "x":
        b.frustum(cx, cy, z, z + rise, hx, hy, hx, 0.15, mat)
    else:
        b.frustum(cx, cy, z, z + rise, hx, hy, 0.15, hy, mat)


def hip(b, cx, cy, z, hx, hy, rise, mat, eave=1.2):
    """A hipped roof with eaves (a Japanese temple / shrine roof's massing)."""
    b.box((cx - hx - eave, cy - hy - eave, z), (cx + hx + eave, cy + hy + eave, z + 0.3), mat)
    b.frustum(cx, cy, z + 0.3, z + rise, hx + eave, hy + eave, max(0.2, hx - hy + 0.5), 0.3, mat)


# ── emergency and public services ──────────────────────────────────────────────────────────────────────────────
# PLATEAU (7 central wards, measure_named_buildings.py, 2026-09-28), p50: 警察署 30 x 45 m, 7 storeys, 38 m;
# 交番 4.9 x 7.3 m, 2 storeys, 6.8 m; 消防署 23 x 42 m, 5 storeys, 23 m, 4.5 m a storey (the tall apparatus floor);
# 消防出張所 15.5 x 23 m, 3 storeys; 郵便局 9.3 x 14.4 m, 4 storeys; 区役所 48 x 85 m, 14 storeys, 55 m. The island's
# town is smaller than central Tokyo, so the big ones are the p25 end, sized to fit their plot (island_civic_sites.py).

def police_station(material, Builder):
    """警察署: 36 x 24 m, 6 storeys (a 4.6 m ground floor + 5 x 4.0), on a 40 x 45 plot, parking behind. The emblem (旭日章,
    gold) and the name board over the entrance canopy, a 赤色灯 each side of it, a radio mast on the roof."""
    b = Builder("Civic_PoliceStation", material)
    x0, x1, y0, y1 = -18.0, 18.0, -20.0, 4.0
    b.box((x0, y0, 0.0), (x1, y1, 4.6), "MI_TileBrown")
    b.box((-8.0, y0 - 0.03, 0.3), (8.0, y0, 3.8), "MI_GlassClear")               # the glazed entrance hall
    top = ribbon_block(b, x0, x1, y0, y1, 4.6, 5, 4.0, wall="MI_TileBeige")
    roof(b, x0, x1, y0, y1, top, units=6)
    canopy(b, -6.0, 6.0, y0 - 3.0, y0, 3.6)
    sign(b, -6.0, 6.0, y0 - 3.0, 4.0, 4.5, "MI_Sign")
    b.box((-0.6, y0 - 0.2, 4.8), (0.6, y0, 6.0), "MI_Gold")                       # the emblem
    for x in (-7.0, 7.0):
        b.box((x - 0.15, y0 - 0.35, 3.0), (x + 0.15, y0 - 0.05, 3.5), "MI_SignRed")
    b.beam((x1 - 4.0, y1 - 4.0, top), (x1 - 4.0, y1 - 4.0, top + 14.0), 0.3, "MI_Steel")
    for k in range(6):                                                           # the rear parking bays
        b.box((x0 + 2.0 + k * 5.5, 12.0, 0.0), (x0 + 2.1 + k * 5.5, 20.0, 0.01), "MI_PaintWhite")
    return "Civic_PoliceStation", "civic", b.mesh()


def koban(material, Builder):
    """交番: 5 x 7 m, two storeys (6.8 m), a gabled roof over the entrance corner, the red 赤色灯 lamp over the door,
    the KOBAN board, glass front. Its whole plot is 8 x 10."""
    b = Builder("Civic_Koban", material)
    b.box((-2.5, -3.5, 0.0), (2.5, 3.5, 6.2), "MI_TileWhite")
    b.box((-2.0, -3.53, 0.2), (2.0, -3.5, 2.6), "MI_GlassClear")
    b.box((-2.0, -3.53, 3.6), (2.0, -3.5, 5.2), "MI_Window")
    gable(b, 0.0, 0.0, 6.2, 2.9, 3.9, 1.6, "MI_RoofSlate", along="y")
    sign(b, -1.6, 1.6, -3.5, 2.75, 3.3, "MI_Sign")
    b.box((-0.25, -3.9, 3.35), (0.25, -3.5, 3.85), "MI_SignRed")                  # 赤色灯
    b.box((-2.6, -4.6, 2.7), (2.6, -3.5, 2.85), "MI_PaintedMetal")               # the door canopy
    return "Civic_Koban", "civic", b.mesh()


def _bays(b, x0, n, w, y, h, gap=1.2):
    """`n` apparatus bays with RED roll-up shutters (fire engines out to the street, -Y)."""
    x = x0
    for _ in range(n):
        b.box((x, y - 0.05, 0.0), (x + w, y, h), "MI_CraneRed")
        for z in range(1, int(h / 0.5)):                                           # the shutter's slats
            b.box((x, y - 0.07, z * 0.5), (x + w, y - 0.05, z * 0.5 + 0.04), "MI_PaintedMetalDark")
        x += w + gap
    return x


def fire_station(material, Builder):
    """消防署 (main station): 38 x 22 m, a 5.5 m apparatus floor with FOUR red bay shutters + 3 x 4.2 m offices, and
    the 訓練塔 (hose-drying / training tower, 6 x 6 x 24 m) at the back right; the name board and a red lamp."""
    b = Builder("Civic_FireStation", material)
    x0, x1, y0, y1 = -19.0, 19.0, -22.0, 0.0
    b.box((x0, y0, 0.0), (x1, y1, 5.5), "MI_ConcreteSmooth")
    _bays(b, x0 + 3.0, 4, 4.2, y0, 4.2)
    b.box((x1 - 6.0, y0 - 0.03, 0.3), (x1 - 1.5, y0, 3.8), "MI_GlassClear")       # the office door
    top = ribbon_block(b, x0, x1, y0, y1, 5.5, 3, 4.2, wall="MI_TileWhite")
    roof(b, x0, x1, y0, y1, top, units=5)
    b.box((x0, y0 - 0.2, top - 1.4), (x1, y0, top - 0.6), "MI_CraneRed")          # the red band under the roof
    sign(b, -8.0, 8.0, y0, 5.6, 6.5, "MI_SignRed")
    b.box((x1 - 9.0, 6.0, 0.0), (x1 - 3.0, 12.0, 24.0), "MI_ConcreteSmooth")      # the 訓練塔
    for z in range(3, 24, 3):
        b.box((x1 - 9.03, 6.8, z), (x1 - 9.0, 11.2, z + 1.2), "MI_Window")
    b.box((x1 - 9.5, 5.5, 24.0), (x1 - 2.5, 12.5, 24.8), "MI_CraneRed")
    ground(b, x0, x1, -25.0, y0, "MI_AsphaltLot")                             # the apron in front of the bays
    return "Civic_FireStation", "civic", b.mesh()


def fire_branch(material, Builder):
    """消防出張所: 18 x 14 m, a 5 m apparatus floor with two red bay shutters + two 4.0 m storeys, and a 4 x 4 x 15 m
    hose tower at the back."""
    b = Builder("Civic_FireBranch", material)
    x0, x1, y0, y1 = -9.0, 9.0, -11.0, 3.0
    b.box((x0, y0, 0.0), (x1, y1, 5.0), "MI_ConcreteSmooth")
    _bays(b, x0 + 1.5, 2, 4.0, y0, 4.0)
    b.box((x1 - 4.0, y0 - 0.03, 0.3), (x1 - 1.0, y0, 3.6), "MI_GlassClear")
    top = ribbon_block(b, x0, x1, y0, y1, 5.0, 2, 4.0, wall="MI_TileWhite")
    roof(b, x0, x1, y0, y1, top, units=2, stair=False)
    b.box((x0, y0 - 0.2, top - 1.2), (x1, y0, top - 0.5), "MI_CraneRed")
    sign(b, -4.0, 4.0, y0, 5.1, 5.9, "MI_SignRed")
    b.box((x0 + 1.0, 4.0, 0.0), (x0 + 5.0, 8.0, 15.0), "MI_ConcreteSmooth")
    b.box((x0 + 0.6, 3.6, 15.0), (x0 + 5.4, 8.4, 15.6), "MI_CraneRed")
    ground(b, x0, x1, -12.5, y0, "MI_AsphaltLot")
    return "Civic_FireBranch", "civic", b.mesh()


def post_office(material, Builder):
    """郵便局 (a main office): 30 x 20 m, 5 storeys, the red JP band and the 〒 board, a red post box by the door, the
    loading bay for the red vans at the side."""
    b = Builder("Civic_PostOffice", material)
    x0, x1, y0, y1 = -15.0, 15.0, -12.0, 8.0
    b.box((x0, y0, 0.0), (x1, y1, 4.5), "MI_TileBeige")
    b.box((-12.0, y0 - 0.03, 0.3), (6.0, y0, 3.8), "MI_GlassClear")
    top = ribbon_block(b, x0, x1, y0, y1, 4.5, 4, 3.8, wall="MI_TileBeige")
    roof(b, x0, x1, y0, y1, top, units=4)
    b.box((x0, y0 - 0.15, 3.9), (x1, y0, 4.4), "MI_PostRed")
    sign(b, -2.0, 2.0, y0 - 0.15, 4.6, 6.0, "MI_PostRed")
    b.box((-10.5, y0 - 2.0, 0.0), (-9.9, y0 - 1.4, 1.3), "MI_PostRed")            # the post box
    b.box((x1 - 7.0, y0 - 0.03, 0.0), (x1 - 1.0, y0, 3.6), "MI_PaintedMetal")     # the loading shutter
    return "Civic_PostOffice", "civic", b.mesh()


def post_office_small(material, Builder):
    """A branch 郵便局: 10 x 14 m, 2 storeys, the red band, 〒 board and post box."""
    b = Builder("Civic_PostOfficeSmall", material)
    x0, x1, y0, y1 = -5.0, 5.0, -8.0, 6.0
    b.box((x0, y0, 0.0), (x1, y1, 3.8), "MI_TileBeige")
    b.box((-4.0, y0 - 0.03, 0.3), (3.0, y0, 3.2), "MI_GlassClear")
    top = punched_block(b, x0, x1, y0, y1, 3.8, 1, 3.2, wall="MI_TileBeige", sides="f")
    roof(b, x0, x1, y0, y1, top, stair=False, units=1)
    b.box((x0, y0 - 0.15, 3.3), (x1, y0, 3.75), "MI_PostRed")
    sign(b, 3.3, 4.6, y0 - 0.15, 3.9, 5.2, "MI_PostRed")
    b.box((-4.5, y0 - 1.6, 0.0), (-3.9, y0 - 1.0, 1.3), "MI_PostRed")
    return "Civic_PostOfficeSmall", "civic", b.mesh()


def ward_office(material, Builder):
    """区役所: a 44 x 26 m tower of 10 storeys (42 m) on a 56 x 40 m two-storey podium (the citizens' counters), the
    name board, a plaza canopy and three flag poles."""
    b = Builder("Civic_WardOffice", material)
    b.box((-28.0, -20.0, 0.0), (28.0, 20.0, 9.0), "MI_TileBeige")
    b.box((-20.0, -20.03, 0.3), (20.0, -20.0, 8.0), "MI_GlassClear")
    top = ribbon_block(b, -22.0, 22.0, -13.0, 13.0, 9.0, 9, 3.9, wall="MI_TileBeige")
    roof(b, -22.0, 22.0, -13.0, 13.0, top, units=8)
    roof(b, -28.0, 28.0, -20.0, 20.0, 9.0, stair=False)
    canopy(b, -10.0, 10.0, -26.0, -20.0, 5.0)
    sign(b, -8.0, 8.0, -20.0, 7.2, 8.4)
    for x in (-24.0, -21.0, -18.0):
        b.box((x - 0.08, -27.0, 0.0), (x + 0.08, -26.84, 12.0), "MI_Steel")
    ground(b, -28.0, 28.0, -30.0, -20.0, "MI_AsphaltLot")
    return "Civic_WardOffice", "civic", b.mesh()


# ── health and schools ─────────────────────────────────────────────────────────────────────────────────────────
# PLATEAU p50: 総合病院 52 x 83 m, 8 storeys, 41 m; 小学校 (the school building) 46 x 80 m, 4 storeys, 18 m (4.4-4.9 m a
# storey); 中学校 42 x 84 m, 4 storeys, 18.5 m. A school's plot adds the 校庭 (sports ground), the 体育館 and a pool.

def hospital(material, Builder):
    """総合病院 on a 100 x 100 plot: a 80 x 40 m, 2-storey outpatient podium at the street, an 8-storey (4.5 + 7 x 4.0 m)
    64 x 18 m ward tower on it with a rooftop helipad, the 救急 (emergency) entrance with its red sign and canopy at the
    right end, the main entrance canopy centre, and the car park behind."""
    b = Builder("Civic_Hospital", material)
    px0, px1, py0, py1 = -40.0, 40.0, -45.0, -5.0
    b.box((px0, py0, 0.0), (px1, py1, 9.0), "MI_TileWhite")
    b.box((-20.0, py0 - 0.03, 0.3), (20.0, py0, 4.0), "MI_GlassClear")
    b.box((-36.0, py0 - 0.03, 5.5), (36.0, py0, 8.0), "MI_Window")
    roof(b, px0, px1, py0, py1, 9.0, stair=False, units=10)
    canopy(b, -10.0, 10.0, py0 - 6.0, py0, 4.0)
    sign(b, -9.0, 9.0, py0, 4.4, 5.3, "MI_SignGreen")
    b.box((26.0, py0 - 0.03, 0.3), (34.0, py0, 3.8), "MI_GlassClear")            # 救急入口
    canopy(b, 24.0, 36.0, py0 - 8.0, py0, 4.4)
    sign(b, 27.0, 33.0, py0 - 8.0, 4.8, 5.6, "MI_SignRed")
    top = ribbon_block(b, -32.0, 32.0, -34.0, -16.0, 9.0, 8, 4.0, wall="MI_TileWhite")
    roof(b, -32.0, 32.0, -34.0, -16.0, top, units=6)
    b.box((-8.0, -33.0, top), (8.0, -17.0, top + 0.3), "MI_ConcreteSmooth")     # the helipad
    b.box((-3.0, -26.0, top + 0.3), (-1.8, -24.0, top + 0.32), "MI_PaintWhite")
    b.box((1.8, -26.0, top + 0.3), (3.0, -24.0, top + 0.32), "MI_PaintWhite")
    b.box((-1.8, -25.3, top + 0.3), (1.8, -24.7, top + 0.32), "MI_PaintWhite")
    for k in range(14):
        b.box((-38.0 + k * 5.5, 20.0, 0.0), (-37.9 + k * 5.5, 25.0, 0.01), "MI_PaintWhite")
        b.box((-38.0 + k * 5.5, 32.0, 0.0), (-37.9 + k * 5.5, 37.0, 0.01), "MI_PaintWhite")
    return "Civic_Hospital", "civic", b.mesh()


def hospital_small(material, Builder):
    """病院 (a district hospital, 55 x 60 plot): 44 x 22 m, 5 storeys (4.2 + 4 x 3.8), a green name board, the
    entrance canopy and a small 救急 door at the side."""
    b = Builder("Civic_HospitalSmall", material)
    x0, x1, y0, y1 = -22.0, 22.0, -24.0, -2.0
    b.box((x0, y0, 0.0), (x1, y1, 4.2), "MI_TileWhite")
    b.box((-10.0, y0 - 0.03, 0.3), (10.0, y0, 3.6), "MI_GlassClear")
    top = ribbon_block(b, x0, x1, y0, y1, 4.2, 4, 3.8, wall="MI_TileWhite")
    roof(b, x0, x1, y0, y1, top, units=6)
    canopy(b, -6.0, 6.0, y0 - 4.0, y0, 3.4)
    sign(b, -7.0, 7.0, y0, top - 2.0, top - 0.6, "MI_SignGreen")
    b.box((x1 - 0.03, -8.0, 0.3), (x1, -4.0, 3.2), "MI_GlassClear")
    sign(b, x1 - 0.2, x1, -9.0, 3.4, 3.9, "MI_SignRed")
    for k in range(8):
        b.box((-20.0 + k * 5.5, 12.0, 0.0), (-19.9 + k * 5.5, 17.0, 0.01), "MI_PaintWhite")
    return "Civic_HospitalSmall", "civic", b.mesh()


def clinic(material, Builder):
    """診療所 (a street clinic, 14 x 18 plot): 12 x 13 m, 3 storeys, the clinic behind a glass front on the ground
    floor and the doctor's family above; the green cross-free name board (a Japanese clinic's is a plain board)."""
    b = Builder("Civic_Clinic", material)
    x0, x1, y0, y1 = -6.0, 6.0, -8.0, 5.0
    b.box((x0, y0, 0.0), (x1, y1, 3.6), "MI_TileWhite")
    b.box((-5.0, y0 - 0.03, 0.3), (2.0, y0, 3.0), "MI_GlassClear")
    top = punched_block(b, x0, x1, y0, y1, 3.6, 2, 3.0, wall="MI_TileBeige", sides="fblr", bay=3.0, win=1.6)
    roof(b, x0, x1, y0, y1, top, units=1, stair=False)
    sign(b, -5.0, 5.0, y0, 3.65, 4.3, "MI_SignGreen")
    return "Civic_Clinic", "civic", b.mesh()


def _school(b, pw, pd, blk, gym, pool):
    """A school on a pw x pd plot (street at -Y): the 校舎 (classroom block, `blk` = (length, depth, storeys)) along the
    BACK of the plot facing the 校庭 (sports ground) in front of it, the 体育館 (gym, `gym` = (w, d)) at one side, the
    pool (25 m) beside it, a fence round the plot with the 校門 gate at the street, a clock on the block."""
    hx, hy = pw / 2.0, pd / 2.0
    L, D, n = blk
    by1 = hy - 3.0
    by0 = by1 - D
    bx0 = -hx + 4.0
    top = ribbon_block(b, bx0, bx0 + L, by0, by1, 0.0, n, 4.4, wall="MI_ConcreteSmooth", sides="fb", sill=1.0)
    roof(b, bx0, bx0 + L, by0, by1, top, units=0)
    b.box((bx0 + L / 2 - 1.2, by0 - 0.12, top - 3.0), (bx0 + L / 2 + 1.2, by0, top - 0.6), "MI_PaintWhite")  # clock
    b.box((bx0 + L / 2 - 0.8, by0 - 0.14, top - 2.6), (bx0 + L / 2 + 0.8, by0 - 0.12, top - 1.0), "MI_PlasticDark")
    gw, gd = gym
    gx1 = hx - 4.0
    gx0 = gx1 - gw
    gy1 = by1
    gy0 = gy1 - gd
    b.box((gx0, gy0, 0.0), (gx1, gy1, 9.0), "MI_Corrugated")
    b.frustum((gx0 + gx1) / 2, (gy0 + gy1) / 2, 9.0, 12.5, gw / 2 + 0.5, gd / 2 + 0.5, gw / 2 + 0.5, 1.0,
              "MI_RoofCopper")
    for x in range(int(gx0) + 2, int(gx1) - 1, 4):
        b.box((x, gy0 - 0.03, 5.5), (x + 2.2, gy0, 8.0), "MI_Window")
    if pool:
        px1 = gx0 - 4.0
        b.box((px1 - 29.0, gy1 - 17.0, 0.0), (px1, gy1, 0.3), "MI_ConcreteSmooth")
        b.box((px1 - 27.0, gy1 - 15.0, 0.3), (px1 - 2.0, gy1 - 2.0, 0.32), "MI_PoolWater")
        fence(b, px1 - 29.0, px1, gy1 - 17.0, gy1, h=2.0)
    ground(b, -hx + 3.0, hx - 3.0, -hy + 3.0, min(by0, gy0) - 3.0, "MI_Dirt")   # the 校庭
    # a 200 m track's straights, white, on the ground
    tx0, tx1, ty = -hx + 12.0, hx - 12.0, (-hy + min(by0, gy0)) / 2.0
    for y in (ty - 10.0, ty + 10.0):
        b.box((tx0, y - 0.05, 0.02), (tx1, y + 0.05, 0.03), "MI_PaintWhite")
    fence(b, -hx + 0.5, hx - 0.5, -hy + 0.5, hy - 0.5, h=2.2, gaps=[("f", 0.0, 6.0)])
    for x in (-3.4, 3.4):                                                       # 校門 posts
        b.box((x - 0.4, -hy + 0.1, 0.0), (x + 0.4, -hy + 0.9, 2.4), "MI_ConcreteSmooth")


def school_elementary(material, Builder):
    """小学校 on a 100 x 110 plot: a 76 x 14 m, 4-storey 校舎 (4.4 m storeys: 17.6 m, PLATEAU p50 17.8), a 34 x 24 m 体育館,
    a 25 m pool, the 校庭 with a 200 m track, the plot fence and the gate at the street."""
    b = Builder("Civic_SchoolElementary", material)
    _school(b, 100.0, 110.0, (54.0, 14.0, 4), (34.0, 24.0), True)
    return "Civic_SchoolElementary", "civic", b.mesh()


def school_junior_high(material, Builder):
    """中学校 on a 110 x 130 plot: a 64 x 16 m, 4-storey 校舎, a 38 x 28 m 体育館, a 25 m pool, the larger 校庭."""
    b = Builder("Civic_SchoolJuniorHigh", material)
    _school(b, 110.0, 130.0, (60.0, 16.0, 4), (38.0, 28.0), True)
    return "Civic_SchoolJuniorHigh", "civic", b.mesh()


# ── worship, leisure and the shore ─────────────────────────────────────────────────────────────────────────────
# PLATEAU p50: a named 寺 hall 24 x 32 m, 16 m to the ridge (shrines are rarely named buildings in PLATEAU; a town 神社's
# 拝殿 is ~8-12 m wide). Resort hotels: public record for an Okinawa resort (a 12-16 storey slab, 3.2 m storeys, sea
# view balconies); PLATEAU's named Tokyo hotels are city towers (39 storeys, 150 m), not this type.

def shrine(material, Builder):
    """神社 on a 50 x 60 plot: the vermilion 鳥居 at the street, a stone 参道 to the 拝殿 (worship hall, 12 x 9 m, a
    copper gabled roof with its entrance under a 向拝), the 本殿 behind it on a raised base, a 手水舎 beside the path and
    a low stone 玉垣 round the precinct."""
    b = Builder("Shrine", material)
    ground(b, -24.0, 24.0, -29.0, 29.0, "MI_Dirt")
    b.box((-1.8, -30.0, 0.0), (1.8, 14.0, 0.06), "MI_Limestone")                 # the 参道
    for x in (-2.6, 2.6):                                                        # the 鳥居
        b.box((x - 0.3, -26.3, 0.0), (x + 0.3, -25.7, 6.0), "MI_LacquerRed")
    b.box((-4.6, -26.4, 6.0), (4.6, -25.6, 6.6), "MI_PlasticDark")               # 笠木
    b.box((-3.6, -26.2, 5.0), (3.6, -25.8, 5.35), "MI_LacquerRed")              # 貫
    b.box((-8.0, 12.0, 0.0), (8.0, 22.0, 0.8), "MI_StoneWall")                   # the stone base
    b.box((-6.0, 13.0, 0.8), (6.0, 21.0, 5.0), "MI_Wood")                        # 拝殿
    gable(b, 0.0, 17.0, 5.0, 7.5, 5.5, 3.6, "MI_RoofCopper", along="x")
    b.box((-3.0, 10.0, 3.4), (3.0, 13.0, 3.7), "MI_RoofCopper")                   # 向拝
    for x in (-2.8, 2.8):
        b.box((x - 0.15, 10.2, 0.8), (x + 0.15, 10.5, 3.4), "MI_Wood")
    b.box((-3.5, 23.0, 0.0), (3.5, 28.0, 1.6), "MI_StoneWall")                   # 本殿
    b.box((-2.5, 23.8, 1.6), (2.5, 27.2, 4.6), "MI_Wood")
    gable(b, 0.0, 25.5, 4.6, 3.6, 2.8, 2.6, "MI_RoofCopper", along="x")
    b.box((6.0, -8.0, 0.0), (9.0, -5.0, 0.8), "MI_StoneWall")                    # 手水舎
    for (x, y) in ((6.2, -7.8), (8.8, -7.8), (6.2, -5.2), (8.8, -5.2)):
        b.box((x - 0.1, y - 0.1, 0.0), (x + 0.1, y + 0.1, 2.6), "MI_Wood")
    gable(b, 7.5, -6.5, 2.6, 2.2, 2.2, 1.2, "MI_RoofCopper", along="x")
    for (a0, b0, a1, b1) in ((-25, -29.5, -3, -29.0), (3, -29.5, 25, -29.0), (-25, 29.0, 25, 29.5),
                             (-25, -29.5, -24.5, 29.5), (24.5, -29.5, 25, 29.5)):
        b.box((a0, b0, 0.0), (a1, b1, 0.9), "MI_StoneWall")                        # 玉垣
    return "Shrine", "civic", b.mesh()


def temple(material, Builder):
    """寺 on a 50 x 50 plot: the 山門 gate at the street, the 本堂 (main hall, 20 x 16 m, a dark-tiled hipped roof to 15 m,
    PLATEAU p50 16 m), a 鐘楼 (bell tower) to the side, a gravel precinct and a plastered 塀 round it."""
    b = Builder("Temple", material)
    ground(b, -24.0, 24.0, -24.0, 24.0, "MI_Limestone")
    b.box((-10.0, 0.0, 0.0), (10.0, 16.0, 1.0), "MI_StoneWall")
    b.box((-8.5, 1.5, 1.0), (8.5, 14.5, 7.0), "MI_Wood")
    b.box((-8.5, 1.47, 1.0), (8.5, 1.5, 6.0), "MI_Plaster")
    hip(b, 0.0, 8.0, 7.0, 8.5, 6.5, 8.0, "MI_RoofSlate", eave=2.2)
    for x in (-3.5, 3.5):                                                       # 山門
        b.box((x - 0.4, -24.4, 0.0), (x + 0.4, -23.6, 5.0), "MI_Wood")
    hip(b, 0.0, -24.0, 5.0, 3.9, 1.0, 2.2, "MI_RoofSlate", eave=1.0)
    for (x, y) in ((13.0, -8.0), (17.0, -8.0), (13.0, -4.0), (17.0, -4.0)):      # 鐘楼
        b.box((x - 0.2, y - 0.2, 0.0), (x + 0.2, y + 0.2, 5.0), "MI_Wood")
    b.box((14.3, -6.7, 2.6), (15.7, -5.3, 4.6), "MI_RoofCopper")
    hip(b, 15.0, -6.0, 5.0, 2.2, 2.2, 2.0, "MI_RoofSlate", eave=0.8)
    for (a0, b0, a1, b1) in ((-25, -25, -4.5, -24.4), (4.5, -25, 25, -24.4), (-25, 24.4, 25, 25),
                             (-25, -25, -24.4, 25), (24.4, -25, 25, 25)):
        b.box((a0, b0, 0.0), (a1, b1, 2.2), "MI_Plaster")                            # 塀
        b.box((a0 - 0.15, b0 - 0.15, 2.2), (a1 + 0.15, b1 + 0.15, 2.45), "MI_RoofSlate")
    return "Temple", "civic", b.mesh()


def park(material, Builder):
    """A neighbourhood 公園 on a 60 x 60 plot: a dirt open space, a paved path, a playground (slide, swings, a
    climbing frame, a sandpit), a toilet block, benches, a low fence with openings on all four sides. Trees are the
    nature kit's, placed with the composite (Park in building_types.json)."""
    b = Builder("Park", material)
    ground(b, -29.0, 29.0, -29.0, 29.0, "MI_Dirt")
    b.box((-1.5, -30.0, 0.0), (1.5, 30.0, 0.04), "MI_ConcreteSmooth")
    b.box((-30.0, -1.5, 0.0), (30.0, 1.5, 0.04), "MI_ConcreteSmooth")
    b.box((6.0, 6.0, 0.0), (26.0, 26.0, 0.03), "MI_Grass")
    b.box((-24.0, 6.0, 0.0), (-6.0, 24.0, 0.05), "MI_Limestone")                # the playground's sand
    b.wedge_x(-22.0, -16.0, 20.0, 21.0, 2.4, 0.3, "MI_PaintYellow")              # slide
    b.box((-23.5, 19.8, 0.0), (-22.0, 21.2, 2.4), "MI_CraneRed")
    for x in (-13.0, -8.0):                                                    # swings frame
        b.beam((x, 10.0, 0.0), (x, 11.0, 2.4), 0.12, "MI_PaintedMetal")
        b.beam((x, 12.0, 0.0), (x, 11.0, 2.4), 0.12, "MI_PaintedMetal")
    b.beam((-13.0, 11.0, 2.4), (-8.0, 11.0, 2.4), 0.12, "MI_PaintedMetal")
    for x in (-11.8, -9.2):
        b.box((x - 0.3, 10.8, 0.4), (x + 0.3, 11.2, 0.5), "MI_Wood")
    b.box((-20.0, 8.0, 0.0), (-17.0, 11.0, 0.3), "MI_Wood")                      # sandpit rim
    b.box((18.0, -26.0, 0.0), (26.0, -20.0, 3.2), "MI_TileWhite")                 # toilet block
    b.box((17.5, -26.5, 3.2), (26.5, -19.5, 3.5), "MI_PaintedMetalDark")
    for (x, y) in ((-10.0, -6.0), (-4.0, -6.0), (8.0, -6.0), (14.0, -6.0)):
        b.box((x - 0.9, y - 0.25, 0.4), (x + 0.9, y + 0.25, 0.5), "MI_Wood")        # benches
        b.box((x - 0.8, y - 0.2, 0.0), (x - 0.6, y + 0.2, 0.4), "MI_PaintedMetal")
        b.box((x + 0.6, y - 0.2, 0.0), (x + 0.8, y + 0.2, 0.4), "MI_PaintedMetal")
    fence(b, -29.8, 29.8, -29.8, 29.8, h=0.9, gaps=[(s, 0.0, 4.0) for s in "fblr"])
    return "Park", "civic", b.mesh()


def water_resort(material, Builder):
    """温浴・プールリゾート on a 150 x 70 plot (an Oedo-Onsen / Summerland type; 2026-10-03: 120 -> 70 deep, so it fits
    inside the suburb loop beside the beach hotels, on the flat ground south of the dike's slope): a 70 x 24 m indoor
    pool and spa hall (glazed, 14 m, a barrel roof) at the street with the entrance canopy, outdoor pools behind it (a
    wave pool, a lazy river loop, a kids' pool) on a deck, a 16 m slide tower with two chutes, changing blocks, a
    fence."""
    b = Builder("WaterResort", material)
    ground(b, -74.0, 74.0, -34.0, 34.0, "MI_ConcreteSmooth")
    b.box((-35.0, -33.0, 0.0), (35.0, -9.0, 10.0), "MI_TileWhite")
    b.box((-33.0, -33.03, 0.3), (33.0, -33.0, 9.0), "MI_GlassClear")
    b.frustum(0.0, -21.0, 10.0, 14.0, 35.0, 12.0, 35.0, 4.8, "MI_GlassClear")
    b.box((-35.0, -33.3, 9.5), (35.0, -32.8, 10.3), "MI_PoolWater")
    canopy(b, -10.0, 10.0, -34.5, -33.0, 5.0, posts=False)
    sign(b, -12.0, 12.0, -33.3, 10.4, 12.4, "MI_SignCyan")
    b.box((-60.0, -4.0, 0.0), (-10.0, 16.0, 0.35), "MI_Limestone")               # wave pool deck
    b.box((-58.0, -2.0, 0.35), (-12.0, 14.0, 0.37), "MI_PoolWater")
    for (x0, y0, x1, y1) in ((0.0, -5.0, 60.0, -1.0), (0.0, 26.0, 60.0, 30.0), (0.0, -1.0, 5.0, 26.0),
                             (55.0, -1.0, 60.0, 26.0)):                              # lazy river
        b.box((x0, y0, 0.0), (x1, y1, 0.35), "MI_Limestone")
        b.box((x0 + 0.8, y0 + 0.8, 0.35), (x1 - 0.8, y1 - 0.8, 0.37), "MI_PoolWater")
    b.box((18.0, 6.0, 0.0), (38.0, 18.0, 0.37), "MI_PoolWater")                    # kids' pool
    b.box((-66.0, 20.0, 0.0), (-58.0, 27.0, 16.0), "MI_PaintYellow")              # slide tower
    for dx, mat in ((0.0, "MI_CraneRed"), (4.0, "MI_PoolWater")):
        b.beam((-62.0 + dx, 20.0, 15.5), (-40.0 + dx, 2.0, 0.8), 1.2, mat)
    for x in (-70.0, 62.0):
        b.box((x, -6.0, 0.0), (x + 8.0, 14.0, 3.5), "MI_TileWhite")                # changing blocks
    fence(b, -74.5, 74.5, -34.5, 34.5, h=2.4, gaps=[("f", 0.0, 22.0)])
    return "WaterResort", "civic", b.mesh()


def resort_hotel(material, Builder):
    """A resort hotel for a 70 x 60 reserve: a 56 x 18 m slab of 15 guest storeys (3.2 m) with sea-view balconies on
    the -Y face over a 64 x 36 m two-storey lobby podium (glass, a porte-cochère at the +Y land side), a rooftop
    restaurant box and the hotel's name board at the top. The balconies face -Y: site it with -Y to the sea."""
    b = Builder("ResortHotel", material)
    b.box((-32.0, -18.0, 0.0), (32.0, 18.0, 8.0), "MI_TileWhite")
    b.box((-30.0, 17.97, 0.3), (30.0, 18.0, 7.2), "MI_GlassClear")
    b.box((-30.0, -18.03, 0.3), (30.0, -18.0, 7.2), "MI_GlassClear")
    canopy(b, -12.0, 12.0, 18.0, 24.0, 5.0)
    roof(b, -32.0, 32.0, -18.0, 18.0, 8.0, stair=False)
    top = punched_block(b, -28.0, 28.0, -9.0, 9.0, 8.0, 15, 3.2, wall="MI_PaintWhite", sides="fblr", bay=4.0,
                        win=2.6, balcony="MI_PaintWhite")
    roof(b, -28.0, 28.0, -9.0, 9.0, top, units=6)
    b.box((-10.0, -6.0, top), (10.0, 6.0, top + 4.0), "MI_GlassClear")
    sign(b, -12.0, 12.0, -9.0, top - 2.6, top - 0.4, "MI_SignCyan")
    b.box((-30.0, -30.0, 0.0), (10.0, -19.0, 0.35), "MI_Limestone")              # the pool deck toward the sea
    b.box((-28.0, -28.5, 0.35), (8.0, -20.5, 0.37), "MI_PoolWater")
    return "ResortHotel", "civic", b.mesh()


FM_C = (455.0, 746.0)     # the fish market reserve's centre, GODOT (x, z): island_plan RESERVES "fish_market"
FM_QUAY_Z = 780.0         # island_reshape.MARKET_QUAY's sea edge
FM_YARD_X = (262.0, 610.0)   # island_reshape.MARKET_YARD: the low yard's west and east ends
FM_WATER = -2.0           # the water under the yard (island_reshape.MARKET_YARD_Z = 2.0 over the sea)
FM_STRIP_H = 3.6          # the strip under the viaduct east of the yard: the plain, 5.6 - 2.0 over the yard


def fish_market(material, Builder):
    """魚市場 on a fishing port's quay, 2 m over the water (user, 2026-10-13 late: "the boat quay should be same level as
    the pontoon in most images ... go down, about 2 m above the water ... a more reasonable arrangement to a Japanese
    fish market with quay"), as three fresh reviewers (Japanese port planner, level designer, developer) then changed
    it. The first build of the day stood on the island's raised plain, 5.6 m up, with a pontoon far below it.

    Laid out in WORLD (Godot x, z) numbers through `B`, because every part answers to something the generators own:
    the low yard (island_reshape.MARKET_YARD), the quay line z 780, the truck ramp `ichiba_michi` coming down the
    dike's face to its foot at (383, 728) (island_site_access), the Wangan's viaduct east of x 610. Origin = the
    reserve's centre on the yard's ground; the quay at -Y.

    West to east (the planner's order: the PUBLIC at the ramp's foot and fenced off, so no visitor's car passes the
    truck berths; trucks run foot -> berths -> the turning ground at the east end and back):
      * the public car park and, by the quay, the 3-storey office over a 直売所 / 食堂 floor -- its roof is the
        津波避難 deck, a solid stair up its land side; a fence with one gate between it and the working yard;
      * the 90 x 20 m auction hall (a 荷さばき所 is 15-25 m deep; at 27 m the trucks had 7 m to back in), sawtooth
        roof, open to the quay under a 4.5 m eave, a wall to the land, 13 truck berths 15-18 m deep on its land side;
      * the cold store and ice plant, the 給氷塔 on the quay with its chute (the 準備岸壁: ice straight into the boats);
      * the trucks' turning and waiting ground, net / float store; a 3.6 m retaining wall up to the strip under the
        viaduct with a stair through it.
    THE QUAY: a wall down past the water (the terrain's own edge is a 2 m slope), 車止め kerb, bollards, tyre fenders;
    at the west end a 船揚場 slipway down into the water, and three landing stairs along the wall -- the only ways OUT
    of the water for a swimmer (the swim jump clears ~1 m, the quay is 2 m). Three 避難階段 climb the dike's face to
    the crest (the dike IS the refuge: 10 m up, a minute away)."""
    b = Builder("FishMarket", material)
    cx, cz = FM_C

    def B(x0, x1, z0, z1, h0, h1, mat):
        """A box over Godot x0..x1, z0..z1, from height h0 to h1 above the yard."""
        b.box((x0 - cx, cz - z1, h0), (x1 - cx, cz - z0, h1), mat)

    def ramp_x(x0, x1, z0, z1, h_at_x0, h_at_x1, mat, base=None):
        """A solid stair / ramp whose top slopes along Godot x (from the yard's ground, or a box under it to `base`)."""
        b.wedge_x(x0 - cx, x1 - cx, cz - z1, cz - z0, h_at_x0, h_at_x1, mat)
        if base is not None:
            B(x0, x1, z0, z1, base, 0.0, mat)
    q = FM_QUAY_Z
    yx0, yx1 = FM_YARD_X
    sh = FM_STRIP_H
    # ── the yard's paving: all of it south of the ramp's fill (the ramp comes down inside the north edge from x 545
    # to its foot at x 383; its seaward slope ends by z ~736), and the public forecourt west of the foot
    # (measured by the developer review: the coast road's own embankment covers x 262..288, and the terrain stamp's
    # verge carries the ramp's fill toe to z 736..738 over x 394..480)
    wx = 290.0
    B(wx, 376.0, 722.0, q, -0.02, 0.02, "MI_AsphaltLot")
    B(376.0, yx1, 738.0, q, -0.02, 0.02, "MI_AsphaltLot")
    B(wx, yx1, q - 8.0, q, 0.02, 0.03, "MI_ConcreteSmooth")                  # the quay apron
    # ── the quay: a wall down past the water along the yard, a 車止め kerb (open at the slipway and the stairs),
    # bollards and tyre fenders; east of the yard the strip's higher sea wall, its coping and a 1.1 m pipe railing
    B(yx0, yx1, q - 0.4, q + 1.6, -6.0, 0.0, "MI_ConcreteSmooth")
    B(yx1, 720.0, q - 0.4, q + 1.6, -6.0, sh, "MI_ConcreteSmooth")
    slip = (294.0, 324.0)                     # the 船揚場: its head at x 300, falling west into the water
    stairs = (352.0, 468.0, 598.0)            # landing stairs: each head at this x, falling west
    gaps = [(slip[1] - 7.0, slip[1] + 0.5)] + [(x - 0.5, x + 2.5) for x in stairs]
    x = wx
    for g0, g1 in sorted(gaps) + [(yx1, yx1)]:
        if g0 > x:
            B(x, g0, q - 0.5, q - 0.2, 0.0, 0.25, "MI_PaintYellow")
        x = max(x, g1)
    for x in range(340, 606, 15):
        if any(g0 - 2.0 < x < g1 + 2.0 for g0, g1 in gaps):
            continue
        B(x - 0.3, x + 0.3, q - 1.6, q - 1.0, 0.0, 0.6, "MI_PaintedMetalDark")
        B(x + 6.9, x + 8.1, q + 1.6, q + 2.0, -1.9, -0.3, "MI_PaintedMetalDark")
    B(yx1, 720.0, q - 0.5, q, sh, sh + 0.4, "MI_ConcreteSmooth")
    for h in (0.7, 1.04):
        B(yx1, 720.0, q - 0.3, q - 0.24, sh + h, sh + h + 0.06, "MI_PaintedMetal")
    for x in range(int(yx1), 721, 5):
        B(x - 0.04, x + 0.04, q - 0.31, q - 0.23, sh + 0.4, sh + 1.1, "MI_PaintedMetal")
    # the slipway (1:11, 6.5 m wide, outside the wall: a car or a trailer can reach the water, a swimmer the yard)
    # and the landing stairs (1:2, 2 m wide), each from the quay's level to 0.6 m under the water
    wz0 = q + 1.6
    ramp_x(slip[0], slip[1], wz0, wz0 + 6.5, FM_WATER - 0.7, 0.0, "MI_ConcreteSmooth", base=-6.0)
    B(slip[1], slip[1] + 0.5, wz0, wz0 + 6.5, -6.0, 0.0, "MI_ConcreteSmooth")
    B(slip[1] - 7.0, slip[1] + 0.5, q - 0.4, wz0, 0.0, 0.02, "MI_ConcreteSmooth")
    for sx in stairs:
        drop = -FM_WATER + 0.6
        ramp_x(sx - 2.0 * drop, sx, wz0, wz0 + 2.0, -drop, 0.0, "MI_ConcreteSmooth", base=-6.0)
        B(sx, sx + 2.0, wz0, wz0 + 2.0, -6.0, 0.0, "MI_ConcreteSmooth")             # its head landing
    # ── the retaining wall up to the strip (the land grid's own edge is a 2 m slope: the wall stands over it), a
    # low wall on top (a chain-link panel would be a see-through bullet stop), and a stair through it
    w = 2.2
    for z0, z1 in ((712.0, 742.0), (745.0, q + 1.6)):
        B(yx1 - w, yx1, z0, z1, -0.5, sh, "MI_ConcreteSmooth")
        B(yx1 - 0.3, yx1, z0, z1, sh, sh + 1.1, "MI_ConcreteSmooth")
    B(yx1 - w, yx1 + 1.0, 742.0, 745.0, -0.5, sh, "MI_ConcreteSmooth")              # the stair's head, at the strip
    ramp_x(yx1 - w - 2.0 * sh, yx1 - w, 742.0, 745.0, 0.0, sh, "MI_ConcreteSmooth")
    # ── the PUBLIC end, at the ramp's foot: a car park (two double rows, a 6 m aisle between and either side) and
    # the office over a 直売所 / 食堂; a fence with one gate keeps the public off the 荷さばき floor
    for z in (735.0, 757.0):
        B(293.0, 338.0, z - 0.06, z + 0.06, 0.02, 0.03, "MI_PaintWhite")
        for k in range(19):
            xx = 293.0 + k * 2.5
            B(xx - 0.05, xx + 0.05, z - 5.0, z + 5.0, 0.02, 0.03, "MI_PaintWhite")
    ox0, ox1, oz0, oz1 = 345.0, 368.5, 746.0, 770.0
    top = ribbon_block(b, ox0 - cx, ox1 - cx, cz - oz1, cz - oz0, 0.0, 3, ST, wall="MI_TileBeige",
                       ground="MI_GlassClear")
    t = 0.25
    B(ox0, ox1, oz1 - t, oz1, top, top + 1.1, "MI_ConcreteSmooth")                  # the deck's parapet: south,
    B(ox0, ox0 + t, oz0, oz1, top, top + 1.1, "MI_ConcreteSmooth")                  # west,
    B(ox1 - t, ox1, oz0, oz1, top, top + 1.1, "MI_ConcreteSmooth")                  # east,
    B(ox0, ox1 - 2.6, oz0, oz0 + t, top, top + 1.1, "MI_ConcreteSmooth")            # north, open at the stair's head
    B(350.0, 354.0, 762.0, 766.0, top, top + 3.0, "MI_ConcreteSmooth")              # the 塔屋
    B(ox0 + 2.0, ox1 - 2.0, oz1, oz1 + 0.15, top - 2.4, top - 0.6, "MI_Sign")       # 魚市場, on the quay face
    B(ox0 + 2.0, ox1 - 2.0, oz0 - 2.75, oz0 - 2.6, top - 2.4, top - 0.6, "MI_Sign")  # ...and to the ramp
    sz0, sz1 = oz0 - 2.6, oz0                                                        # the stair: 1:2, 2.6 m wide
    ramp_x(ox1 - 2.0 * top, ox1 - 0.6, sz0, sz1, 0.0, top, "MI_ConcreteSmooth")
    B(ox1 - 0.6, ox1, sz0, sz1, 0.0, top, "MI_ConcreteSmooth")
    B(ox1 - 2.0 * top, ox1, sz0 - 0.1, sz0, 0.0, top + 1.1, "MI_PaintedMetal")
    for z0, z1 in ((736.0, oz0 - 2.7), (oz1, q - 8.5)):                               # the fence at x 371
        B(370.9, 371.1, z0, z1, 0.0, 1.2, "MI_ConcreteSmooth")
    # ── the auction hall: 90 x 20 m, a sawtooth-roofed shed open to the quay on columns, an eave over the apron
    hx0, hx1, hz0, hz1 = 374.0, 464.0, 751.0, 771.0
    B(hx0, hx1, hz0, hz0 + 1.0, 0.0, 8.0, "MI_Corrugated")
    B(hx0, hx0 + 0.6, hz0, hz1 - 6.0, 0.0, 8.0, "MI_Corrugated")                    # the west gable; the east is open
    for x in range(int(hx0), int(hx1) + 1, 10):
        B(x - 0.4, x + 0.4, hz1 - 0.4, hz1 + 0.4, 0.0, 8.0, "MI_PaintedMetal")
        B(x - 0.4, x + 0.4, hz0 + 9.6, hz0 + 10.4, 0.0, 8.0, "MI_PaintedMetal")     # the mid row
    B(hx0, hx1, hz0, hz1 + 4.5, 8.0, 8.6, "MI_PaintedMetal")                        # the roof slab and its 庇
    x = hx0
    while x < hx1 - 1e-6:
        b.wedge_x(x - cx, x + 10.0 - cx, cz - hz1, cz - hz0, 11.0, 8.6, "MI_Corrugated")
        B(x, x + 0.3, hz0, hz1, 8.6, 11.0, "MI_GlassClear")
        x += 10.0
    B(hx0, hx1, hz0, hz1, 0.0, 0.05, "MI_TileWhite")                                # the washable floor
    B(hx0 + 25.0, hx1 - 25.0, hz0 - 0.15, hz0, 5.4, 7.4, "MI_Sign")                 # the name, to the ramp and the dike
    for k in range(13):                                                              # the truck berths, land side
        xx = 398.0 + k * 5.0
        B(xx, xx + 0.12, hz0 - 11.0, hz0 - 1.0, 0.02, 0.03, "MI_PaintWhite")
    for k in range(8):                                                               # fish-box rows: cover in the hall
        xx = 380.0 + k * 10.0
        B(xx, xx + 6.0, 756.0, 757.2, 0.05, 1.25, "MI_PlasticWhite")
        B(xx + 3.0, xx + 9.0, 763.0, 764.2, 0.05, 1.25, "MI_PlasticWhite")
    # ── the cold store and ice plant east of the hall, the 給氷塔 on the quay with its chute to the boats
    B(470.0, 504.0, 747.0, 771.0, 0.0, 9.0, "MI_Corrugated")
    B(470.0, 504.0, 747.0, 771.0, 9.0, 9.4, "MI_PaintedMetal")
    B(474.0, 478.0, 746.85, 747.0, 0.0, 4.2, "MI_PaintedMetalDark")                 # its two dock doors, land side
    B(486.0, 490.0, 746.85, 747.0, 0.0, 4.2, "MI_PaintedMetalDark")
    B(506.0, 512.0, 764.0, 770.0, 0.0, 18.0, "MI_PaintedMetal")                     # the ice tower: the tall mark
    B(506.0, 512.0, 763.85, 764.0, 14.0, 17.0, "MI_Sign")
    b.beam((509.0 - cx, cz - 770.0, 9.0), (509.0 - cx, cz - (q + 3.0), 1.5), 0.8, "MI_Steel")
    # ── the trucks' turning and waiting ground at the east end: a net / float store, stacked reefer boxes as cover
    B(576.0, 600.0, 760.0, 771.0, 0.0, 5.0, "MI_Corrugated")                        # 漁具倉庫
    for x0 in (520.0, 548.0):
        B(x0, x0 + 12.2, 737.0, 739.5, 0.0, 5.2, "MI_PaintedMetal")                 # two-high container rows
    # ── 避難階段 up the dike's sea face to the crest (1:2, 2 m wide, lying on the slope), clear of the ramp
    rise = 9.9
    for x in (300.0, 350.0, 590.0):
        b.beam((x - cx, cz - 718.5, -0.9), (x - cx, cz - (718.5 - 2.0 * rise), rise - 0.9), 2.0, "MI_ConcreteSmooth")
        for dx in (-1.0, 1.0):
            b.beam((x + dx - cx, cz - 718.5, 1.0), (x + dx - cx, cz - (718.5 - 2.0 * rise), rise + 1.0), 0.06,
                   "MI_PaintedMetal")
    return "FishMarket", "civic", b.mesh()


def mil_hq(material, Builder):
    """本部庁舎 (base headquarters): 44 x 16 m, 4 storeys (4.0 m), plain beige concrete, a flag pole and name board."""
    b = Builder("Mil_HQ", material)
    top = ribbon_block(b, -22.0, 22.0, -8.0, 8.0, 0.0, 4, 4.0, wall="MI_Limestone", sill=1.1)
    roof(b, -22.0, 22.0, -8.0, 8.0, top, units=4)
    canopy(b, -5.0, 5.0, -12.0, -8.0, 3.4)
    sign(b, -6.0, 6.0, -8.0, 3.6, 4.0, "MI_PlasticDark")
    b.box((-9.08, -14.08, 0.0), (-8.92, -13.92, 14.0), "MI_Steel")
    return "Mil_HQ", "military", b.mesh()


def mil_barracks(material, Builder):
    """隊舎 (barracks): 60 x 14 m, 5 storeys (3.2 m), punched windows, stairwells at both ends."""
    b = Builder("Mil_Barracks", material)
    top = punched_block(b, -30.0, 30.0, -7.0, 7.0, 0.0, 5, 3.2, wall="MI_Limestone", bay=3.6, win=1.6)
    roof(b, -30.0, 30.0, -7.0, 7.0, top, units=6)
    for x in (-31.5, 28.5):
        b.box((x, -3.0, 0.0), (x + 3.0, 3.0, top + 1.0), "MI_ConcreteSmooth")
    return "Mil_Barracks", "military", b.mesh()


def mil_hangar(material, Builder):
    """A fighter hangar (格納庫): 48 x 40 m, a barrel roof to 14 m, the whole front (-Y) open (door leaves slid to the
    sides), a concrete floor. Two F-15-class fighters fit side by side."""
    b = Builder("Mil_Hangar", material)
    b.box((-24.0, -20.0, -0.05), (24.0, 20.0, 0.0), "MI_ConcreteSmooth")
    b.box((-24.0, 19.0, 0.0), (24.0, 20.0, 10.0), "MI_Corrugated")                 # back wall
    for x in (-24.0, 23.0):
        b.box((x, -20.0, 0.0), (x + 1.0, 20.0, 10.0), "MI_Corrugated")               # side walls
    for x in (-27.5, 24.5):
        b.box((x, -20.5, 0.0), (x + 3.0, -19.5, 10.0), "MI_Olive")                   # door leaves, slid open
    n = 12
    for k in range(n):                                                                 # the barrel roof, faceted
        a0, a1 = math.pi * k / n, math.pi * (k + 1) / n
        xa, za = -24.0 * math.cos(a0), 10.0 + 4.0 * math.sin(a0)
        xb, zb = -24.0 * math.cos(a1), 10.0 + 4.0 * math.sin(a1)
        b.beam((xa, 0.0, za), (xb, 0.0, zb), 0.5, "MI_Corrugated")
        b.box((min(xa, xb), -20.0, min(za, zb)), (max(xa, xb), 20.0, max(za, zb) + 0.3), "MI_Corrugated")
    b.box((-24.0, -20.5, 9.2), (24.0, -20.0, 10.2), "MI_Olive")                       # door head
    return "Mil_Hangar", "military", b.mesh()


def mil_control_tower(material, Builder):
    """管制塔: a 7 x 7 m shaft to 22 m, a 10 x 10 m glazed cab (4 m), antennas, a two-storey base building (operations)."""
    b = Builder("Mil_ControlTower", material)
    b.box((-10.0, -6.0, 0.0), (10.0, 6.0, 7.6), "MI_Limestone")
    ribbon_block(b, -10.0, 10.0, -6.0, 6.0, 0.0, 2, 3.8, wall="MI_Limestone")
    b.box((-3.5, -3.5, 7.6), (3.5, 3.5, 22.0), "MI_Limestone")
    b.frustum(0.0, 0.0, 22.0, 26.0, 4.6, 4.6, 5.2, 5.2, "MI_GlassClear")
    b.box((-5.5, -5.5, 26.0), (5.5, 5.5, 26.8), "MI_PaintedMetalDark")
    b.box((-3.5, -5.5, 21.6), (3.5, 5.5, 22.0), "MI_AviationOrange")
    b.beam((2.0, 2.0, 26.8), (2.0, 2.0, 32.0), 0.15, "MI_Steel")
    return "Mil_ControlTower", "military", b.mesh()


def fighter_jet(material, Builder):
    """An F-15J-class fighter, parked: 19.4 m nose (-Y) to tail, 13.0 m span, twin fins to 5.6 m, air-superiority
    grey, on its gear (the fuselage's belly 1.2 m up). A static prop; its collider is its own box (MIL_JET_BOXES)."""
    b = Builder("Mil_FighterJet", material)
    g = "MI_JetGrey"
    b.frustum(0.0, -8.0, 1.2, 3.0, 0.9, 1.7, 0.6, 1.4, g)                             # forward fuselage
    b.box((-1.6, -6.4, 1.2), (1.6, 9.7, 3.0), g)                                     # centre / engines
    b.beam((0.0, -9.7, 2.2), (0.0, -6.4, 2.2), 1.4, g)                               # nose
    b.box((-0.55, -7.2, 3.0), (0.55, -4.8, 3.6), "MI_GlassClear")                   # canopy
    for s in (-1.0, 1.0):
        # the wing: a tapered slab, root 9 m at the fuselage to the tip 2.5 m at 6.5 m out
        b.frustum(s * 3.9, 2.5, 2.2, 2.4, 2.3, 4.5, 2.3, 4.5, g)
        b.box((s * 6.5 - 0.5, 1.5, 2.2), (s * 6.5 + 0.5, 4.0, 2.4), g)
        b.box((s * 1.8 - 0.15, 6.5, 3.0), (s * 1.8 + 0.15, 9.5, 5.6), g)             # twin fins
        b.box((s * 3.4 - 1.4, 7.8, 2.1), (s * 3.4 + 1.4, 9.6, 2.25), g)              # stabilators
        b.box((s * 1.4 - 0.12, 1.5, 0.0), (s * 1.4 + 0.12, 2.3, 1.2), "MI_PlasticDark")  # main gear
    b.box((-0.1, -6.8, 0.0), (0.1, -6.2, 1.2), "MI_PlasticDark")                        # nose gear
    b.box((-0.2, -2.6, 2.45), (0.2, -2.2, 2.46), "MI_CraneRed")                         # the roundel's place
    return "Mil_FighterJet", "military", b.mesh()


def mil_fence(material, Builder):
    """One 10 m bay of the base's perimeter fence: 2.4 m chain-link on posts with a barbed-wire outrigger, along X."""
    b = Builder("Mil_Fence", material)
    for x in (-5.0, 5.0):
        b.box((x - 0.05, -0.05, 0.0), (x + 0.05, 0.05, 2.4), "MI_Steel")
        b.beam((x, 0.0, 2.4), (x, -0.45, 2.85), 0.05, "MI_Steel")
    b.box((-5.0, -0.01, 0.1), (5.0, 0.01, 2.35), "MI_Steel")
    for z in (2.55, 2.7, 2.85):
        b.box((-5.0, -0.3 - (z - 2.55), z - 0.01), (5.0, -0.28 - (z - 2.55), z + 0.01), "MI_Steel")
    return "Mil_Fence", "military", b.mesh()


def mil_gate(material, Builder):
    """The base's main gate: a guard house (4 x 3 m) between the in and out lanes, a canopy over both, barrier arms,
    the name board. 16 m across (two 6 m lanes), the street at -Y."""
    b = Builder("Mil_Gate", material)
    b.box((-2.0, -1.5, 0.0), (2.0, 1.5, 3.0), "MI_Limestone")
    b.box((-2.03, -1.0, 0.9), (-2.0, 1.0, 2.2), "MI_Window")
    b.box((2.0, -1.0, 0.9), (2.03, 1.0, 2.2), "MI_Window")
    b.box((-8.0, -3.0, 5.0), (8.0, 3.0, 5.4), "MI_PaintedMetal")
    for x in (-7.8, 7.4):
        b.box((x, -0.2, 0.0), (x + 0.4, 0.2, 5.0), "MI_PaintedMetal")
    for s in (-1.0, 1.0):          # the barrier arms, RAISED (2026-10-05: the two lanes are open; a mission lowers them)
        b.box((s * 2.25 - 0.05, -2.5, 0.9), (s * 2.25 + 0.05, -2.4, 4.8), "MI_PaintYellow")
    sign(b, -7.0, 7.0, -3.0, 5.4, 6.4, "MI_PlasticDark")
    return "Mil_Gate", "military", b.mesh()


def airport_service_gate(material, Builder):
    """The airport's landside SERVICE GATE (user, 2026-09-29: "a vehicle service gate, locked"): an 8 m sliding
    chain-link gate, CLOSED, between two 0.3 m posts, 2.4 m tall with the perimeter fence's barbed outrigger, a small
    guard booth beside it on the landside (+Y is the airside; the street at -Y). The gate is part of the fence line:
    its collider (the piece's bounds) keeps everyone out; a mission opens it later."""
    b = Builder("Airport_ServiceGate", material)
    for x in (-4.3, 4.0):
        b.box((x, -0.15, 0.0), (x + 0.3, 0.15, 2.8), "MI_PaintedMetal")
    b.box((-4.0, -0.03, 0.1), (4.0, 0.03, 2.35), "MI_Steel")                  # the leaf (chain-link)
    for z in (0.15, 1.2, 2.3):
        b.box((-4.0, -0.05, z), (4.0, 0.05, z + 0.08), "MI_PaintedMetal")    # its rails
    for z in (2.55, 2.7, 2.85):
        b.box((-4.3, -0.3 - (z - 2.55), z - 0.01), (4.3, -0.28 - (z - 2.55), z + 0.01), "MI_Steel")
    b.box((-1.0, -0.06, 1.2), (1.0, -0.04, 1.8), "MI_SignRed")                 # 関係者以外立入禁止 plate
    b.box((7.5, -3.2, 0.0), (9.5, -1.2, 2.6), "MI_TileWhite")                 # the guard booth, landside, clear of
    b.box((7.48, -2.8, 1.0), (7.5, -1.6, 2.0), "MI_Window")                   # the service road's footway
    b.box((7.3, -3.4, 2.6), (9.7, -1.0, 2.8), "MI_PaintedMetal")
    return "Airport_ServiceGate", "airport", b.mesh()


def taxiway(material, Builder):
    """A 60 m taxiway section along X: 23 m of asphalt, yellow centreline, edge lines (runways: Airport_Runway)."""
    b = Builder("Airport_Taxiway", material)
    b.box((-30.0, -11.5, -0.05), (30.0, 11.5, 0.0), "MI_AsphaltLot")
    b.box((-30.0, -0.1, 0.0), (30.0, 0.1, 0.01), "MI_PaintYellow")
    for y in (-11.0, 11.0):
        b.box((-30.0, y - 0.15, 0.0), (30.0, y + 0.15, 0.01), "MI_PaintYellow")
    return "Airport_Taxiway", "airport", b.mesh()


def apron_slab(material, Builder):
    """One 30 m square of concrete apron (エプロン), its top flush with the ground, joints every 7.5 m."""
    b = Builder("Airport_Apron", material)
    b.box((-15.0, -15.0, -0.05), (15.0, 15.0, 0.0), "MI_ConcreteSmooth")
    for k in range(1, 4):
        v = -15.0 + 7.5 * k
        b.box((v - 0.03, -15.0, 0.0), (v + 0.03, 15.0, 0.002), "MI_PaintedMetalDark")
        b.box((-15.0, v - 0.03, 0.0), (15.0, v + 0.03, 0.002), "MI_PaintedMetalDark")
    return "Airport_Apron", "airport", b.mesh()


def airliner(material, Builder):
    """A narrow-body airliner (737-800 class): 39.5 m nose (-Y) to tail, 35.8 m span, fin to 12.5 m, white with a
    blue cheatline; on its gear, belly at 1.5 m. Static; its collider is a few boxes (AIRLINER_BOXES)."""
    b = Builder("Airport_Airliner", material)
    w = "MI_PaintWhite"
    b.box((-1.9, -15.0, 1.5), (1.9, 16.0, 5.3), w)                                       # fuselage
    b.frustum(0.0, -17.5, 1.9, 4.9, 1.2, 2.5, 1.7, 2.5, w)                                # nose section
    b.beam((0.0, -19.75, 3.3), (0.0, -17.0, 3.3), 2.6, w)
    b.frustum(0.0, 18.0, 2.4, 5.3, 1.9, 2.0, 0.6, 2.0, w)                                 # tail cone
    b.box((-1.93, -15.0, 3.6), (1.93, 16.0, 3.9), "MI_Sign")                              # cheatline
    for y in range(-13, 15, 1):
        for s in (-1.0, 1.0):
            b.box((s * 1.9 - (0.02 if s > 0 else 0.0), y, 4.1), (s * 1.9 + (0.0 if s > 0 else 0.02), y + 0.3, 4.5),
                  "MI_Window")
    for s in (-1.0, 1.0):
        b.frustum(s * 9.8, 1.5, 2.4, 2.8, 7.9, 3.5, 7.9, 2.0, w)                          # wings
        b.box((s * 5.5 - 1.0, -3.5, 1.0), (s * 5.5 + 1.0, 0.5, 3.0), "MI_Steel")          # engines
        b.box((s * 4.5 - 2.0, 16.5, 5.0), (s * 4.5 + 2.0, 19.5, 5.2), w)                   # tailplane
        b.box((s * 2.0 - 0.15, 1.0, 0.0), (s * 2.0 + 0.15, 2.5, 1.6), "MI_PlasticDark")    # main gear
    b.box((-0.15, 17.0, 5.3), (0.15, 20.5, 12.5), "MI_Sign")                             # fin
    b.box((-0.12, -15.5, 0.0), (0.12, -14.8, 1.6), "MI_PlasticDark")                       # nose gear
    return "Airport_Airliner", "airport", b.mesh()


def airliner_hangar(material, Builder):
    """A maintenance hangar for one narrow-body: 70 x 60 m, 22 m to the roof truss, the front (-Y) open (doors slid
    aside), the airliner parked inside as its own prop (AirportAirside). Offices along the back."""
    b = Builder("Airport_Hangar", material)
    b.box((-35.0, -30.0, -0.05), (35.0, 30.0, 0.0), "MI_ConcreteSmooth")
    b.box((-35.0, 29.0, 0.0), (35.0, 30.0, 20.0), "MI_Corrugated")
    for x in (-35.0, 34.0):
        b.box((x, -30.0, 0.0), (x + 1.0, 30.0, 20.0), "MI_Corrugated")
    b.box((-35.0, -30.0, 20.0), (35.0, 30.0, 22.0), "MI_PaintedMetal")                    # roof + truss depth
    b.box((-35.0, -30.3, 16.5), (35.0, -30.0, 20.0), "MI_Corrugated")                     # door head
    for x in (-40.0, 35.5):
        b.box((x, -31.0, 0.0), (x + 4.5, -30.2, 16.5), "MI_Corrugated")                    # door leaves, open
    b.box((-33.0, 22.0, 0.0), (33.0, 28.8, 7.6), "MI_TileWhite")                          # back offices
    ribbon_block(b, -33.0, 33.0, 22.0, 28.8, 0.0, 2, 3.8, wall="MI_TileWhite", sides="f")
    sign(b, -15.0, 15.0, -30.3, 20.2, 21.8, "MI_Sign")
    return "Airport_Hangar", "airport", b.mesh()


# ── street signage: 秋葉原 electric town and the 横丁 ──────────────────────────────────────────────────────────────

def akiba_vertical_sign(material, Builder):
    """An 秋葉原 electric-town VERTICAL sign (袖看板) for the corner of a building's front: 1.8 m wide, 0.4 m deep,
    18 m of stacked lit panels (the shops floor by floor), hung off the facade from 5 m up. Origin: its foot on the
    facade line, the panels facing -Y and to both sides."""
    b = Builder("Sign_AkibaVertical", material)
    mats = ("MI_SignYellow", "MI_SignRed", "MI_SignCyan", "MI_SignPink", "MI_Sign", "MI_SignGreen")
    b.box((-0.1, -0.1, 4.8), (0.1, 0.1, 23.2), "MI_Steel")
    for k in range(9):
        z = 5.0 + k * 2.0
        b.box((-0.9, -0.6, z), (0.9, -0.2, z + 1.85), mats[k % len(mats)])
    return "Sign_AkibaVertical", "street", b.mesh()


def akiba_billboard(material, Builder):
    """An 秋葉原 rooftop / facade BILLBOARD: a 10 x 6 m lit screen (a game or anime ad) in a dark frame on a steel
    stand, its face -Y. Origin: the stand's foot centre."""
    b = Builder("Sign_AkibaBillboard", material)
    for x in (-3.5, 3.5):
        b.box((x - 0.2, 0.5, 0.0), (x + 0.2, 0.9, 6.5), "MI_Steel")
    b.box((-5.3, 0.0, 6.0), (5.3, 0.5, 12.3), "MI_PlasticDark")
    b.box((-5.0, -0.03, 6.3), (5.0, 0.0, 12.0), "MI_SignPink")
    return "Sign_AkibaBillboard", "street", b.mesh()


ROOF_SIGN_COLOURS = (("Red", "MI_SignRed"), ("Cyan", "MI_SignCyan"), ("Yellow", "MI_SignYellow"),
                     ("Green", "MI_SignGreen"))
ROOF_SIGN_SIZES = {"S": (4.4, 2.6, 3.0), "L": (9.0, 4.4, 4.0)}    # face width, face height, stand height (m)


def _roof_billboard(material, Builder, size, colour, mat):
    """A brand-neutral ROOFTOP BILLBOARD (屋上看板, user 2026-09-29: "rooftop billboards across downtown, not only the
    electric street"): a lit panel in a dark frame on a two-leg steel stand, its face -Y (the street). `S` (a 4.4 m face)
    fits a pencil building or a shop-house, `L` (9 m) an office or a mansion. Origin: the stand's foot centre on the
    roof, 0.6 m BEHIND the face so the frame's front is at y -0.35. A panel colour per piece; the face is plain colour
    (a real ad replaces the material)."""
    fw, fh, sh = ROOF_SIGN_SIZES[size]
    name = "Sign_RoofBillboard_%s_%s" % (size, colour)
    b = Builder(name, material)
    for x in (-fw * 0.32, fw * 0.32):
        b.box((x - 0.12, 0.25, 0.0), (x + 0.12, 0.55, sh + fh * 0.5), "MI_Steel")      # the legs
        b.box((x - 0.08, 0.3, 0.0), (x + 0.08, 1.6, 0.2), "MI_Steel")                    # the back strut foot
    b.box((-fw / 2.0 - 0.2, -0.3, sh - 0.2), (fw / 2.0 + 0.2, 0.25, sh + fh + 0.2), "MI_PlasticDark")
    b.box((-fw / 2.0, -0.33, sh), (fw / 2.0, -0.3, sh + fh), mat)
    b.box((-fw / 2.0, -0.62, sh + fh + 0.15), (fw / 2.0, -0.3, sh + fh + 0.25), "MI_Steel")  # the lamp rail
    return name, "street", b.mesh()


def roof_billboards(material, Builder):
    return [_roof_billboard(material, Builder, sz, c, m) for sz in ROOF_SIGN_SIZES for c, m in ROOF_SIGN_COLOURS]


def chochin(material, Builder):
    """A red paper lantern (赤提灯) on a bracket: 0.45 m across, 0.75 m tall, lit, hanging 0.6 m out from a facade at
    -Y. Origin: the bracket on the facade."""
    b = Builder("Prop_Chochin", material)
    b.box((-0.03, -0.6, -0.03), (0.03, 0.0, 0.03), "MI_PlasticDark")
    b.frustum(0.0, -0.6, -0.9, -0.55, 0.16, 0.16, 0.22, 0.22, "MI_SignRed")
    b.frustum(0.0, -0.6, -0.55, -0.2, 0.22, 0.22, 0.16, 0.16, "MI_SignRed")
    b.box((-0.18, -0.78, -0.95), (0.18, -0.42, -0.9), "MI_PlasticDark")
    b.box((-0.18, -0.78, -0.2), (0.18, -0.42, -0.15), "MI_PlasticDark")
    return "Prop_Chochin", "street", b.mesh()


def noren(material, Builder):
    """A 暖簾 (shop curtain) across a doorway: 1.7 m wide, 1.0 m deep of navy cloth in four panels on a rod, its top at
    the origin (hang it at the door head), 0.1 m out from the facade at -Y."""
    b = Builder("Prop_Noren", material)
    b.box((-0.95, -0.14, -0.03), (0.95, -0.1, 0.03), "MI_Wood")
    for k in range(4):
        x = -0.85 + k * 0.43
        b.box((x, -0.13, -1.0), (x + 0.4, -0.12, -0.02), "MI_NorenNavy")
    return "Prop_Noren", "street", b.mesh()


def shop_vertical_sign(material, Builder):
    """A small izakaya / snack VERTICAL sign on a bracket: 0.5 x 0.18 x 2.4 m, lit, standing out 0.6 m from a facade
    at -Y; origin at the bracket, its bottom 0.2 m below."""
    b = Builder("Sign_ShopVertical", material)
    b.box((-0.03, -0.6, 0.0), (0.03, 0.0, 0.06), "MI_Steel")
    b.box((-0.09, -0.85, -0.2), (0.09, -0.35, 2.2), "MI_SignYellow")
    return "Sign_ShopVertical", "street", b.mesh()


# ── expressway guide signs (PLAN.md item 1g, user 2026-09-30): Japanese convention, white letters on green ──────────
#: The PANEL of each sign in the GODOT piece frame (x across, y up, z toward the drivers), read by
#: `point_furniture.expressway_signs` to tell the runtime where to draw the text. Keep these in step with the boxes.
EXPWY_SIGN_PANELS = {
    "Sign_ExpwyCantilever": {"centre": [3.9, 6.25, 0.07], "size": [5.0, 2.5]},
    "Sign_ExpwyEntrance": {"centre": [0.0, 3.3, 0.07], "size": [3.2, 1.8]},
}


def _green_panel(b, x0, x1, z0, z1):
    """A green sign face at y -0.05 (its face toward -Y = the drivers) with a white inset border, on a grey backing."""
    b.box((x0, -0.05, z0), (x1, 0.08, z1), "MI_ExpwyGreen")
    t, e = 0.06, 0.1
    for (a0, a1, c0, c1) in ((x0 + e, x1 - e, z1 - e - t, z1 - e), (x0 + e, x1 - e, z0 + e, z0 + e + t),
                             (x0 + e, x0 + e + t, z0 + e, z1 - e), (x1 - e - t, x1 - e, z0 + e, z1 - e)):
        b.box((a0, -0.065, c0), (a1, -0.05, c1), "MI_PaintWhite")


def expwy_cantilever_sign(material, Builder):
    """A Japanese expressway GUIDE sign on an F-type cantilever (片持ち式): a grey steel post at the carriageway's LEFT
    edge (keep-left: exits leave on the left), two arms reaching +X over the lanes, and a 5.0 x 2.5 m green panel with
    its bottom 5.0 m up (the clearance a Japanese road sign keeps over a carriageway). Its face is -Y (Godot +Z): the
    furniture pass turns the piece so it faces oncoming traffic. The TEXT (出口 EXIT, the destination) is drawn at run
    time (world.TrafficSignals), so one piece serves every sign. Origin: the post's foot."""
    b = Builder("Sign_ExpwyCantilever", material)
    b.box((-0.18, 0.1, 0.0), (0.18, 0.46, 7.6), "MI_PaintedMetal")
    b.box((-0.35, -0.07, 0.0), (0.35, 0.63, 0.3), "MI_ConcreteSmooth")          # the foot
    for z in (5.55, 6.95):
        b.box((0.0, 0.12, z), (6.6, 0.32, z + 0.2), "MI_PaintedMetal")
    _green_panel(b, 1.4, 6.4, 5.0, 7.5)
    return "Sign_ExpwyCantilever", "street", b.mesh()


def expwy_entrance_sign(material, Builder):
    """The ENTRANCE sign on the surface street at an on-ramp (入口): a 3.2 x 1.8 m green panel on two posts, its bottom
    2.4 m up, face -Y. Text (海都高速 入口 + the route) drawn at run time. Origin: between the two posts' feet."""
    b = Builder("Sign_ExpwyEntrance", material)
    for x in (-1.2, 1.2):
        b.box((x - 0.07, 0.1, 0.0), (x + 0.07, 0.24, 4.3), "MI_PaintedMetal")
    _green_panel(b, -1.6, 1.6, 2.4, 4.2)
    return "Sign_ExpwyEntrance", "street", b.mesh()


# ── 電柱 (PLAN.md T1, user 2026-10-11: "use japanese measure ... pole / electric pole placed in blender") ─────────────
# The Japanese distribution pole, to its real numbers:
#   * a 14 m prestressed-concrete pole (コンクリート柱), 根入れ 1/6 of its length = 2.33 m in the ground, so 11.67 m
#     stands; 末口 (top) 19 cm, taper 1/75, so ~34.6 cm at the ground and 37.7 cm at the butt;
#   * 高圧 (6.6 kV, three wires) on pin insulators on a 75 mm 腕金 (1.8 m) near the top -- 片出し, reaching toward the
#     ROAD so the conductors keep off the buildings; an 架空地線 on a cap bracket above it;
#   * 低圧 (100 / 200 V) on a vertical rack ~2 m below; the 柱上変圧器 (a grey can, ~0.55 m across) between them;
#   * 通信線 lowest, over 5 m (the clearance a cable keeps over a road), with a splice closure hung on it;
#   * 足場ボルト up the shaft from 2.7 m, yellow 反射 bands at bumper height, and (the _Lamp pieces) a 防犯灯 at 5 m.
# WHERE each wire meets the pole is `furniture.json` rules `denchu_wires` (the one owner: `point_furniture` strings
# the wires from it), so the insulators are built from that table. Frame: origin = the pole's axis AT THE GROUND,
# +X = the road side, +Y = along the road. Three materials (four with the lamp), because a MultiMesh draws once per
# surface.
DENCHU_LENGTH = 14.0
DENCHU_BURIED = DENCHU_LENGTH / 6.0
DENCHU_UP = DENCHU_LENGTH - DENCHU_BURIED          # 11.67 m above the ground
DENCHU_TOP_R = 0.095
DENCHU_TAPER = 1.0 / 75.0                          # on the diameter
DENCHU_LAMP_Z = 5.0                                # a 防犯灯's mounting height
DENCHU_PIECES = (("Pole_Denchu", False, False), ("Pole_DenchuTr", True, False),
                 ("Pole_DenchuLamp", False, True), ("Pole_DenchuTrLamp", True, True))


def denchu_radius(z):
    """The shaft's radius `z` m above the ground."""
    return DENCHU_TOP_R + 0.5 * DENCHU_TAPER * (DENCHU_UP - z)


def denchu_wires():
    import json
    import os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(root, "assets", "world_source", "kits", "road_kit", "furniture.json")) as fh:
        return json.load(fh)["rules"]["denchu_wires"]


def _denchu(material, Builder, name, transformer, lamp):
    b = Builder(name, material)
    conc, steel = "MI_ConcreteSmooth", "MI_Steel"
    b.cyl(0.0, 0.0, -DENCHU_BURIED, DENCHU_UP, denchu_radius(-DENCHU_BURIED), DENCHU_TOP_R, conc, segs=12)
    for k in range(3):                                           # 反射 bands, bumper to chest height
        z = 0.75 + 0.4 * k
        b.cyl(0.0, 0.0, z, z + 0.2, denchu_radius(z) + 0.012, denchu_radius(z + 0.2) + 0.012, "MI_PaintYellow", segs=12)
    z, side = 2.7, 1.0
    while z < DENCHU_UP - 1.2:                                   # 足場ボルト, alternating sides, 45 cm apart
        r = denchu_radius(z)
        b.box((-0.012, side * r - (0.0 if side > 0 else 0.13), z), (0.012, side * r + (0.13 if side > 0 else 0.0), z + 0.024),
              steel)
        z, side = z + 0.45, -side
    wires = denchu_wires()
    hv = [w for w in wires if w["kind"] == "hv"]
    if hv:                                                       # the 腕金, bolted to the shaft's +Y face
        az = min(w["z"] for w in hv) - 0.22
        ay = denchu_radius(az) + 0.04
        b.box((min(w["x"] for w in hv) - 0.2, ay - 0.0375, az - 0.075), (max(w["x"] for w in hv) + 0.2, ay + 0.0375, az),
              steel)
        b.box((-0.05, -ay, az - 0.06), (0.05, ay, az - 0.02), steel)                     # the band round the shaft
        x1 = max(w["x"] for w in hv)
        b.beam((0.0, ay, az - 0.75), (0.75 * x1, ay, az - 0.04), 0.04, steel)             # the arm's brace
        for w in hv:                                             # pin insulators, the wire on top
            b.cyl(w["x"], ay, az, w["z"] - 0.1, 0.022, 0.022, steel, segs=6)
            b.cyl(w["x"], ay, w["z"] - 0.13, w["z"], 0.065, 0.04, steel, segs=8)
    for w in (w for w in wires if w["kind"] == "gw"):            # 架空地線 on its cap bracket
        b.box((w["x"] - 0.025, -0.025, DENCHU_UP - 0.3), (w["x"] + 0.025, 0.025, w["z"]), steel)
    lv = [w for w in wires if w["kind"] == "lv"]
    if lv:                                                       # the low-voltage rack: a strip with spool insulators
        z0, z1 = min(w["z"] for w in lv) - 0.15, max(w["z"] for w in lv) + 0.15
        x = lv[0]["x"]
        b.box((x - 0.06, -0.02, z0), (x - 0.03, 0.02, z1), steel)
        for zz in (z0 + 0.03, z1 - 0.07):
            b.box((0.0, -0.02, zz), (x - 0.03, 0.02, zz + 0.04), steel)
        for w in lv:
            b.cyl(w["x"], 0.0, w["z"] - 0.05, w["z"] + 0.05, 0.045, 0.045, steel, segs=8)
    for w in (w for w in wires if w["kind"] == "comm"):          # the cable's clamp and a splice closure on the span
        r = denchu_radius(w["z"])
        sx = -1.0 if w["x"] < 0 else 1.0
        b.box((min(sx * r, w["x"]) - 0.02, -0.03, w["z"] - 0.05), (max(sx * r, w["x"]) + 0.02, 0.03, w["z"] + 0.03), steel)
        b.box((w["x"] - 0.07, 0.5, w["z"] - 0.19), (w["x"] + 0.07, 1.05, w["z"] - 0.04), steel)
    if transformer:                                              # 柱上変圧器, hung in line with the wires
        ty, tz0, tz1 = -(denchu_radius(8.2) + 0.34), 7.75, 8.65
        b.cyl(0.0, ty, tz0, tz1, 0.27, 0.27, steel, segs=12)
        b.cyl(0.0, ty, tz1, tz1 + 0.05, 0.29, 0.29, steel, segs=12)                       # the lid
        for x in (-0.11, 0.11):                                  # the high-voltage bushings
            b.cyl(x, ty, tz1 + 0.05, tz1 + 0.3, 0.035, 0.02, steel, segs=6)
        for zz in (tz0 + 0.15, tz1 - 0.2):                       # the hanger bands
            b.box((-0.05, ty, zz), (0.05, 0.0, zz + 0.06), steel)
        b.box((-0.3, ty - 0.3, tz0 - 0.07), (0.3, 0.0, tz0), steel)                       # the platform arm under it
    if lamp:                                                     # 防犯灯: a short arm toward the road, an LED head
        r = denchu_radius(DENCHU_LAMP_Z)
        b.beam((r - 0.02, 0.0, DENCHU_LAMP_Z - 0.35), (0.75, 0.0, DENCHU_LAMP_Z + 0.02), 0.045, steel)
        b.box((0.6, -0.11, DENCHU_LAMP_Z - 0.03), (1.2, 0.11, DENCHU_LAMP_Z + 0.06), steel)
        b.box((0.66, -0.08, DENCHU_LAMP_Z - 0.045), (1.16, 0.08, DENCHU_LAMP_Z - 0.03), "MI_Light")
    return name, "street", b.mesh()


def denchu_poles(material, Builder):
    return [_denchu(material, Builder, n, tr, lamp) for n, tr, lamp in DENCHU_PIECES]


# ── ガードレール (user 2026-10-11: "white guardrails along some mountain roads ... larger city roads + coastline roads") ──
# The Japanese standard guardrail (防護柵 Gr, 土中建込 type): a white W-section beam 350 mm deep whose CENTRE is 0.6 m
# above the road, on φ114 mm posts every 4 m, the post's top just over the beam. ONE 4 m module with its post in the
# middle, so modules laid end to end put a post every 4 m; the post runs 0.5 m into the ground so a rail on a falling
# verge still stands in it. Frame: origin = the post's axis at the ground, +X = the ROAD side (the beam is bolted to
# the traffic face), +Y along the road. One material (white), so a chunk of rail is one draw.
GUARDRAIL_MODULE = 4.0
GUARDRAIL_BEAM = (0.425, 0.775)      # the beam's lower and upper edge above the road (centre 0.6, 350 mm deep)


def guardrail(material, Builder):
    b = Builder("Guardrail_JP", material)
    white = "MI_PaintWhite"
    h = GUARDRAIL_MODULE / 2.0
    b.cyl(0.0, 0.0, -0.5, 0.8, 0.057, 0.057, white, segs=8)
    x0 = 0.057 + 0.012                                           # the block-out bracket between post and beam
    b.box((0.0, -0.05, 0.5), (x0, 0.05, 0.7), white)
    z0, z1 = GUARDRAIL_BEAM
    half = 0.5 * (z1 - z0)
    b.box((x0, -h, z0), (x0 + 0.012, h, z1), white)              # the web
    for zc in (z0 + 0.5 * half, z0 + 1.5 * half):                # the two corrugations of the W
        lo, hi = zc - 0.5 * half + 0.012, zc + 0.5 * half - 0.012
        sec = ((x0 + 0.012, lo), (x0 + 0.075, lo + 0.04), (x0 + 0.075, hi - 0.04), (x0 + 0.012, hi))
        b.convex([(x, y, z) for y in (-h, h) for x, z in sec], white)
    return "Guardrail_JP", "street", b.mesh()


CIVIC_NOTES = {
    "Civic_PoliceStation": "Placeholder 警察署, origin = its PLOT centre (40 x 45 m plot, tools/island_civic_sites.py), "
                           "the street at -Y. Keep the building inside the plot and the street face at -Y.",
    "Civic_Koban": "Placeholder 交番, origin = its 8 x 10 m plot centre, street at -Y; the red lamp is MI_SignRed.",
    "Civic_FireStation": "Placeholder 消防署 on a 40 x 50 plot (origin = plot centre, street -Y): the red bay shutters "
                         "face the street; the training tower at the back right.",
    "Civic_FireBranch": "Placeholder 消防出張所 on a 20 x 25 plot, origin = plot centre, street -Y.",
    "Civic_PostOffice": "Placeholder 郵便局 on a 40 x 40 plot. Civic_PostOfficeSmall: a branch on a 15 x 20 plot.",
    "Civic_PostOfficeSmall": "Placeholder branch 郵便局 on a 15 x 20 plot, origin = plot centre, street -Y.",
    "Civic_WardOffice": "Placeholder 区役所 on a 60 x 60 plot, origin = plot centre, street -Y.",
    "Civic_Hospital": "Placeholder 総合病院 on a 100 x 100 plot, origin = plot centre, street -Y; the rooftop helipad.",
    "Civic_HospitalSmall": "Placeholder 病院 on a 55 x 60 plot, origin = plot centre, street -Y.",
    "Civic_Clinic": "Placeholder 診療所 on a 14 x 18 plot, origin = plot centre, street -Y.",
    "Civic_SchoolElementary": "Placeholder 小学校 on a 100 x 110 plot: 校舎, 体育館, pool, 校庭, fence; origin = plot "
                              "centre, the gate on the street at -Y. Everything must stay inside the plot.",
    "Civic_SchoolJuniorHigh": "Placeholder 中学校 on a 110 x 130 plot; as the elementary school.",
    "Shrine": "Placeholder 神社 on a 50 x 60 plot, the 鳥居 on the street at -Y. A modeller: real 拝殿 / 本殿 roofs.",
    "Temple": "Placeholder 寺 on a 50 x 50 plot, the 山門 on the street at -Y.",
    "Park": "Placeholder 公園 on a 60 x 60 plot, openings on all four sides; trees come from the nature kit (composite).",
    "WaterResort": "Placeholder 温浴・プールリゾート on a 150 x 120 plot, entrance on the street at -Y.",
    "ResortHotel": "Placeholder resort hotel for a 70 x 60 reserve, the balconies and pool deck to -Y (the sea).",
    "FishMarket": "Placeholder 魚市場 on a quay 2 m over the water (the 310 x 68 m reserve), laid out in WORLD numbers: "
                  "the quay wall matches island_reshape.MARKET_QUAY's z 780 edge, the east retaining wall MARKET_YARD's "
                  "x 610 and the strip's 3.6 m. Origin = the reserve's centre on the yard; the quay at -Y. The whole "
                  "mesh is the collider (the stairs are solid ramps): keep every stair a slope a character can walk.",
    "Mil_FighterJet": "Placeholder F-15J-class fighter, nose -Y. Static prop; its collider is the boxes in "
                      "building_types.json (MilitaryBase props), not its mesh.",
    "Airport_Airliner": "Placeholder narrow-body airliner (737-800 class), nose -Y. Static prop; collider = boxes in "
                        "building_types.json (AirportAirside).",
    "Airport_Hangar": "Placeholder maintenance hangar, 70 x 60 m, open front -Y; the airliner stands inside it as a "
                      "separate prop (AirportAirside). Keep the doorway clear (32 m wide x 16.5 m high at least).",
    "House_Detached": "Placeholder 一戸建て (9.1 x 7.28 m house, 平入り: its long side and ridge along the street, a 玄関 bay, "
                      "one parking bay under a cantilever carport, a low wall with the gate pillar) -- a placed building "
                      "(type DetachedHouse): front (-Y) to the street; the carport's gap in the wall at the front.",
    "House_DetachedB": "Placeholder 一戸建て, the hipped (寄棟) variant: brown roof, white siding, parking and 玄関 on the left "
                       "(type DetachedHouseB).",
    "Prop_Awning_Navy": "Shop-front テント over one bay (3.4 m wide, 0.9 m out, valance foot 0.62 m below the origin); "
                        "ShopHouse mounts it at 2.9 m. Keep it above 2.2 m and within 0.9 m of the facade (it claims no "
                        "ground). _Red and _Olive are the same piece in another cloth.",
    "Sign_OfficeName": "Office name board over the lobby (6.0 x 0.7 m, 0.12 m proud). Plain face.",
    "Sign_Sodekanban": "Placeholder 袖看板 for the PencilBuilding front corner: stacked lit tenant panels 4-12.5 m.",
    "Mil_PatrolShip": "Placeholder patrol ship, 90 x 12 m, bow -Y, origin AT THE WATERLINE (the MilitaryPier composite "
                      "sets it 9.6 m below the pier deck: the pier's land height). Static prop, collider = its box.",
    "Mil_Armoury": "Placeholder earth-covered armoury bunker (mission target), blast door at -Y.",
    "Mil_MotorPool": "Placeholder open vehicle shed, 40 x 14 m, open front -Y; trucks are Mil_Truck props.",
    "Mil_PierTerminal": "Placeholder military harbour terminal (36 x 16 m, 2 storeys) at the north pier's root; pier "
                        "side -Y. Composite MilitaryPier.",
    "Sign_ExpwyCantilever": "Placeholder expressway guide sign (F-type cantilever). The panel's place is "
                            "EXPWY_SIGN_PANELS in library_civic.py (the runtime draws the text there): move the panel "
                            "and that table together.",
    "Sign_ExpwyEntrance": "Placeholder expressway ENTRANCE sign (two posts); panel in EXPWY_SIGN_PANELS.",
    **{n: "電柱 (PLAN.md T1): a 14 m concrete distribution pole, 11.67 m above the ground (the rest is its 根入れ, "
          "modelled below z 0 so a pole on a falling verge still reaches the ground). Origin = the axis at the ground, "
          "+X = the ROAD side, +Y along the road. Where the wires arrive is furniture.json `denchu_wires`: move an "
          "insulator and that table together. The lamp's bulb place is world.StreetLights HEAD_OFFSETS. Keep to "
          "MI_ConcreteSmooth / MI_Steel / MI_PaintYellow (+ MI_Light): one draw per material per chunk."
       for n in ("Pole_Denchu", "Pole_DenchuTr", "Pole_DenchuLamp", "Pole_DenchuTrLamp")},
    "Guardrail_JP": "ガードレール: one 4 m module of the Japanese W-beam guardrail (beam centre 0.6 m, 350 mm deep, a "
                    "φ114 post in the MIDDLE), white. Origin = the post's axis at the ground, +X = the road side, +Y "
                    "along the road; point_furniture tiles it by its own length (keep it exactly as long as the post "
                    "pitch) and BreakableProps knocks a module down under a car. One material.",
    "Mil_Hangar": "Placeholder fighter hangar, 48 x 40 m, open front -Y; two jets stand inside as props (MilitaryBase).",
}


def build_all(material, Builder):
    fns = (police_station, koban, fire_station, fire_branch, post_office, post_office_small, ward_office,
           hospital, hospital_small, clinic, school_elementary, school_junior_high,
           shrine, temple, park, water_resort, resort_hotel, fish_market,
           mil_hq, mil_barracks, mil_hangar, mil_control_tower, fighter_jet, mil_fence, mil_gate, airport_service_gate,
           taxiway, apron_slab, airliner, airliner_hangar,
           akiba_vertical_sign, akiba_billboard, chochin, noren, shop_vertical_sign,
           detached_house, detached_house_b, sode_kanban, mil_pier_terminal,
           mil_armoury, mil_motor_pool, mil_truck, mil_parade_ground, mil_helipad, mil_fuel_depot, mil_patrol_ship,
           expwy_cantilever_sign, expwy_entrance_sign)
    return [f(material, Builder) for f in fns] + roof_billboards(material, Builder) + denchu_poles(material, Builder) + [
        guardrail(material, Builder), office_name_board(material, Builder), parked_bicycle(material, Builder),
        a_frame_sign(material, Builder), planter_box(material, Builder)] + awnings(material, Builder)


# ── the Japanese house and the 雑居ビル's sign (JAPAN_ART_REVIEW.md §3: "the whole residential texture of Japan is
# missing"; "袖看板 ... the single strongest Tokyo read") ────────────────────────────────────────────────────────────
# PLATEAU (measure_building_types.py, Ota + Tama): a 2-storey 一戸建て is 7.1-7.5 x 10.2-10.4 m, 7.4-7.5 m tall.

def _gable_slabs(b, x0, x1, y0, y1, z, rise, roof, wall, over=0.6, t=0.18):
    """A 切妻 roof with its ridge along X: two sloping slabs with real thickness and EAVES `over` past the walls (an
    eave line and a fascia, not a solid wedge), and the two gable ends filled in the WALL material."""
    yc = (y0 + y1) / 2.0
    hy = (y1 - y0) / 2.0
    k = rise / hy                                                  # the pitch
    ze = z - over * k                                              # the eave line, `over` out and down the slope
    for sg in (-1.0, 1.0):
        ye = yc + sg * (hy + over)
        b.convex([(x0 - over, ye, ze), (x1 + over, ye, ze), (x0 - over, yc, z + rise), (x1 + over, yc, z + rise),
                  (x0 - over, ye, ze + t), (x1 + over, ye, ze + t), (x0 - over, yc, z + rise + t),
                  (x1 + over, yc, z + rise + t)], roof)
    for x in (x0, x1):                                              # the gable ends, in the wall
        b.convex([(x - 0.01, y0, z), (x + 0.01, y0, z), (x - 0.01, y1, z), (x + 0.01, y1, z),
                  (x - 0.01, yc, z + rise), (x + 0.01, yc, z + rise)], wall)


def _house(b, roof, wall, side, hipped=False):
    """一戸建て, a Japanese two-storey detached house as it faces the street (user, 2026-09-30, item 11b): 平入り -- its
    LONG side (9.1 m, 5 ken) along the street (-Y) and the ridge parallel to it, 7.28 m (4 ken) deep; the entry bay
    (玄関) projecting toward the street at the parking side under a small canopy, one step up; ONE parking bay beside
    it under a polycarbonate carport on a one-sided cantilever (片側支持); a 1.6 m front garden behind a low wall with
    the gate pillar (門柱: 表札 + letterbox) and a 門扉. The front: a 1F 掃き出し窓 onto the garden and a 2F one onto a
    ベランダ (a slab, rails on three sides and a 物干し pole); 腰窓 and frosted side windows. `side` +1 puts the parking
    on the right (+X), -1 on the left. A 4-寸 pitch to a 7.5 m ridge (PLATEAU p50 7.4-7.5 m); the foundation (基礎)
    stands 2 cm proud of the wall (no z-fighting)."""
    W, D, PW = 9.1, 7.28, 3.0                     # house width (along the street), depth, parking bay width
    X0 = -(W + PW + 0.4) / 2.0                     # the plot runs X0 .. -X0 (12.5 m)
    if side > 0:
        hx0, hx1 = X0, X0 + W
        px0, px1 = hx1 + 0.4, -X0
    else:
        hx0, hx1 = -X0 - W, -X0
        px0, px1 = X0, hx0 - 0.4
    hy0, hy1 = -3.8, 3.48                          # the house's front (street side) and back
    fy = -5.6                                      # the front wall's line (the plot's street edge is fy - 0.2)
    base, eave = 0.5, 6.1                          # 1F floor (the 基礎's top) and the wall top
    b.box((hx0 - 0.02, hy0 - 0.02, 0.0), (hx1 + 0.02, hy1 + 0.02, base), "MI_ConcreteSmooth")   # the 基礎
    b.box((hx0, hy0, base), (hx1, hy1, eave), wall)
    # the entry bay (玄関), projecting 1.2 m toward the street at the parking end, one storey, with its own canopy
    ex0, ex1 = (hx1 - 2.73, hx1) if side > 0 else (hx0, hx0 + 2.73)
    b.box((ex0 - 0.02, hy0 - 1.22, 0.0), (ex1 + 0.02, hy0, base), "MI_ConcreteSmooth")
    b.box((ex0, hy0 - 1.2, base), (ex1, hy0, 3.0), wall)
    b.box((ex0 - 0.3, hy0 - 1.7, 3.0), (ex1 + 0.3, hy0, 3.15), roof)
    dx = (ex0 + ex1) / 2.0
    b.box((dx - 0.45, hy0 - 1.23, base), (dx + 0.45, hy0 - 1.2, base + 2.1), "MI_Wood")      # the 玄関 door
    b.box((dx - 0.9, hy0 - 2.2, 0.0), (dx + 0.9, hy0 - 1.2, 0.25), "MI_ConcreteSmooth")      # the porch step
    # the front windows: a 1F 掃き出し窓 onto the garden and a 腰窓, and a 2F 掃き出し窓 onto the ベランダ
    wx0, wx1 = (hx0 + 0.6, hx0 + 3.2) if side > 0 else (hx1 - 3.2, hx1 - 0.6)
    b.box((wx0, hy0 - 0.03, base + 0.05), (wx1, hy0, base + 2.05), "MI_Window")
    kx = (wx1 + 0.9, wx1 + 2.5) if side > 0 else (wx0 - 2.5, wx0 - 0.9)
    b.box((kx[0], hy0 - 0.03, base + 0.9), (kx[1], hy0, base + 2.0), "MI_Window")
    f2 = base + 2.8
    b.box((wx0, hy0 - 0.03, f2 + 0.05), (wx1, hy0, f2 + 1.95), "MI_Window")
    b.box((kx[0], hy0 - 0.03, f2 + 0.9), (kx[1], hy0, f2 + 2.0), "MI_Window")
    vx0, vx1 = wx0 - 0.4, wx1 + 0.4                                          # the ベランダ
    b.box((vx0, hy0 - 1.0, f2 - 0.15), (vx1, hy0, f2), "MI_ConcreteSmooth")
    b.box((vx0, hy0 - 1.0, f2), (vx1, hy0 - 0.9, f2 + 1.1), "MI_PaintedMetal")
    for x in (vx0, vx1 - 0.1):
        b.box((x, hy0 - 1.0, f2), (x + 0.1, hy0, f2 + 1.1), "MI_PaintedMetal")
    b.beam((vx0 + 0.3, hy0 - 0.6, f2 + 1.7), (vx1 - 0.3, hy0 - 0.6, f2 + 1.7), 0.04, "MI_Steel")   # 物干し
    for x in (vx0 + 0.3, vx1 - 0.3):
        b.beam((x, hy0 - 0.6, f2 + 1.1), (x, hy0 - 0.6, f2 + 1.7), 0.04, "MI_Steel")
    for z0 in (base, f2):                                                       # frosted side windows
        b.box((hx0 - 0.03, -1.0, z0 + 1.0), (hx0, 0.2, z0 + 1.8), "MI_Window")
        b.box((hx1, 0.6, z0 + 1.0), (hx1 + 0.03, 1.8, z0 + 1.8), "MI_Window")
    # the roof
    rise = (hy1 - hy0) / 2.0 * 0.38
    if hipped:
        over = 0.6
        b.frustum((hx0 + hx1) / 2.0, (hy0 + hy1) / 2.0, eave, eave + rise, (hx1 - hx0) / 2.0 + over,
                  (hy1 - hy0) / 2.0 + over, max(0.3, (hx1 - hx0 - (hy1 - hy0)) / 2.0), 0.12, roof)
        b.box((hx0 - over, hy0 - over, eave - 0.18), (hx1 + over, hy1 + over, eave), roof)   # the eave's fascia
    else:
        _gable_slabs(b, hx0, hx1, hy0, hy1, eave, rise, roof, wall)
    # the parking bay and its carport: a polycarbonate sheet on a one-sided cantilever (posts on the outer side)
    b.box((px0, fy + 0.2, 0.0), (px1, hy1, 0.03), "MI_ConcreteSmooth")
    post_x = px1 - 0.15 if side > 0 else px0 + 0.15
    for y in (fy + 1.4, hy1 - 1.0):
        b.box((post_x - 0.07, y - 0.07, 0.0), (post_x + 0.07, y + 0.07, 2.5), "MI_Steel")
        b.beam((post_x, y, 2.45), ((px0 if side > 0 else px1), y, 2.3), 0.1, "MI_Steel")
    b.box((px0, fy + 0.6, 2.35), (px1, hy1 - 0.4, 2.4), "MI_GlassClear")
    # the front garden: a low block wall with the gate pillar and the 門扉 at the path to the porch
    gx0, gx1 = dx - 0.6, dx + 0.6
    lo, hi = (X0, gx0) if side > 0 else (gx1, -X0)
    if side > 0:
        b.box((hx0, fy, 0.0), (gx0, fy + 0.15, 0.8), "MI_ConcreteSmooth")
    else:
        b.box((gx1, fy, 0.0), (hx1, fy + 0.15, 0.8), "MI_ConcreteSmooth")
    px = gx0 - 0.45 if side > 0 else gx1 + 0.05
    b.box((px, fy - 0.05, 0.0), (px + 0.4, fy + 0.35, 1.25), "MI_TileBrown")        # 門柱
    b.box((px + 0.05, fy - 0.07, 0.95), (px + 0.35, fy - 0.05, 1.1), "MI_PaintWhite")   # 表札
    b.box((px + 0.08, fy - 0.07, 0.55), (px + 0.32, fy - 0.05, 0.8), "MI_PaintedMetalDark")  # letterbox
    b.box((gx0, fy + 0.05, 0.0), (gx1, fy + 0.1, 1.0), "MI_PaintedMetalDark")            # 門扉
    b.box((gx0, fy + 0.1, 0.0), (gx1, hy0 - 2.2, 0.03), "MI_ConcreteSmooth")             # the path to the porch
    del lo, hi


def detached_house(material, Builder):
    """一戸建て (a detached house): 切妻, a slate roof, beige siding, the parking on the right."""
    b = Builder("House_Detached", material)
    _house(b, "MI_RoofSlate", "MI_TileBeige", 1.0)
    return "House_Detached", "civic", b.mesh()


def detached_house_b(material, Builder):
    """一戸建て, variant: 寄棟 (hipped), a brown roof, white siding, the parking and the 玄関 on the left."""
    b = Builder("House_DetachedB", material)
    _house(b, "MI_TileBrown", "MI_PaintWhite", -1.0, hipped=True)
    return "House_DetachedB", "civic", b.mesh()


def parked_bicycle(material, Builder):
    """A parked ママチャリ, low-poly: 1.7 m long (along X), 0.5 m wide, saddle 0.85 m, bars 1.05 m; two wheels as flat
    discs, a step-through frame, a front basket. Origin: on the ground under its middle. Kerb-zone scatter (T5)."""
    b = Builder("Prop_Bicycle", material)
    for x in (-0.55, 0.55):                                                               # the wheels: 12-sided discs
        b.convex([(x + 0.33 * math.cos(math.pi * k / 6.0), y, 0.33 + 0.33 * math.sin(math.pi * k / 6.0))
                  for k in range(12) for y in (-0.02, 0.02)], "MI_PlasticDark")
    b.beam((-0.55, 0.0, 0.33), (0.1, 0.0, 0.3), 0.04, "MI_PaintedMetal")                  # chain stay
    b.beam((0.1, 0.0, 0.3), (0.45, 0.0, 0.8), 0.04, "MI_PaintedMetal")                    # the step-through tube
    b.beam((-0.2, 0.0, 0.32), (-0.3, 0.0, 0.82), 0.04, "MI_PaintedMetal")                 # seat tube
    b.beam((0.55, 0.0, 0.33), (0.42, 0.0, 1.0), 0.035, "MI_Steel")                        # the fork and head tube
    b.box((-0.42, -0.09, 0.82), (-0.18, 0.09, 0.88), "MI_PlasticDark")                    # saddle
    b.box((0.38, -0.25, 1.0), (0.44, 0.25, 1.04), "MI_Steel")                             # handlebar
    b.box((0.5, -0.17, 0.72), (0.82, 0.17, 0.95), "MI_Steel")                             # basket
    b.box((-0.75, -0.08, 0.68), (-0.4, 0.08, 0.7), "MI_Steel")                            # rear carrier
    return "Prop_Bicycle", "street", b.mesh()


def a_frame_sign(material, Builder):
    """A 置き看板 (A-frame standing sign): 0.5 m wide, 0.95 m tall, its two faces along +-Y. Origin: on the ground."""
    b = Builder("Prop_AFrameSign", material)
    b.convex([(-0.25, -0.22, 0.0), (0.25, -0.22, 0.0), (-0.25, -0.18, 0.0), (0.25, -0.18, 0.0),
              (-0.25, -0.03, 0.95), (0.25, -0.03, 0.95), (-0.25, 0.01, 0.95), (0.25, 0.01, 0.95)], "MI_SignYellow")
    b.convex([(-0.25, 0.22, 0.0), (0.25, 0.22, 0.0), (-0.25, 0.18, 0.0), (0.25, 0.18, 0.0),
              (-0.25, 0.03, 0.95), (0.25, 0.03, 0.95), (-0.25, -0.01, 0.95), (0.25, -0.01, 0.95)], "MI_PlasticDark")
    return "Prop_AFrameSign", "street", b.mesh()


def planter_box(material, Builder):
    """A shop's own プランター: a 0.9 x 0.32 m trough 0.3 m tall with a clipped green block to 0.62 m. Origin: ground."""
    b = Builder("Prop_PlanterBox", material)
    b.box((-0.45, -0.16, 0.0), (0.45, 0.16, 0.3), "MI_TileBrown")
    b.box((-0.41, -0.13, 0.3), (0.41, 0.13, 0.62), "MI_Grass")
    return "Prop_PlanterBox", "street", b.mesh()


def _awning(material, Builder, colour, mat):
    """A shop-front テント (fixed canvas awning) over ONE shop bay: 3.4 m wide, standing 0.9 m out from a facade at -Y,
    its canvas falling 0.3 m to the front edge, a 0.32 m valance hanging there (where a shop's name goes). Origin: on
    the facade line at the awning's TOP (mount it at 2.9 m: the valance's foot is then 2.28 m up, over a walker's
    head and over the door). It overhangs the lot's own strip and claims no ground (`overhang` in building_types)."""
    name = "Prop_Awning_%s" % colour
    b = Builder(name, material)
    hw = 1.7
    b.convex([(-hw, 0.0, -0.06), (hw, 0.0, -0.06), (-hw, 0.0, 0.0), (hw, 0.0, 0.0),
              (-hw, -0.9, -0.36), (hw, -0.9, -0.36), (-hw, -0.9, -0.3), (hw, -0.9, -0.3)], mat)
    b.box((-hw, -0.9, -0.62), (hw, -0.87, -0.3), mat)                                     # the valance
    for x in (-hw + 0.02, hw - 0.06):                                                     # the two arms under it
        b.box((x, -0.88, -0.4), (x + 0.04, 0.0, -0.36), "MI_Steel")
    return name, "street", b.mesh()


AWNING_COLOURS = (("Navy", "MI_NorenNavy"), ("Red", "MI_LacquerRed"), ("Olive", "MI_Olive"))


def awnings(material, Builder):
    return [_awning(material, Builder, c, m) for c, m in AWNING_COLOURS]


def office_name_board(material, Builder):
    """An office building's name board (ビル名板) over its lobby: a lit band 6.0 x 0.7 m in a dark frame, 0.12 m proud of
    a facade at -Y. Origin: on the facade line at the board's centre foot. The face is plain (a fictional name is
    drawn by whoever dresses the building)."""
    b = Builder("Sign_OfficeName", material)
    b.box((-3.1, -0.1, -0.05), (3.1, 0.0, 0.75), "MI_PlasticDark")
    b.box((-3.0, -0.12, 0.0), (3.0, -0.1, 0.7), "MI_Sign")
    return "Sign_OfficeName", "street", b.mesh()


def sode_kanban(material, Builder):
    """A 雑居ビル's 袖看板 (vertical projecting sign): 0.8 m wide, 0.3 m deep, the tenants' lit panels stacked from 4 m to
    12.5 m, standing 0.5 m out from the facade at -Y on two brackets. Origin: on the facade line at the ground."""
    b = Builder("Sign_Sodekanban", material)
    mats = ("MI_SignYellow", "MI_Sign", "MI_SignRed", "MI_SignPink", "MI_SignGreen", "MI_SignCyan")
    for z in (4.2, 11.8):
        b.box((-0.04, -0.5, z), (0.04, 0.0, z + 0.08), "MI_Steel")
    for k in range(6):
        z = 4.0 + k * 1.42
        b.box((-0.15, -0.8, z), (0.15, -0.5, z + 1.36), mats[k % len(mats)])
    return "Sign_Sodekanban", "street", b.mesh()


def mil_pier_terminal(material, Builder):
    """The base's HARBOUR TERMINAL (user, 2026-09-28: "just one air lane and one harbour terminal"): a two-storey
    36 x 16 m terminal / store building (plain concrete, ribbon windows, a canopy over the pier-side doors at -Y) with
    a small signal mast. Placed at the root of the north finger pier by the MilitaryPier composite."""
    b = Builder("Mil_PierTerminal", material)
    top = ribbon_block(b, -18.0, 18.0, -8.0, 8.0, 0.0, 2, 4.2, wall="MI_Limestone")
    roof(b, -18.0, 18.0, -8.0, 8.0, top, units=3)
    for x in (-10.0, 0.0, 10.0):
        b.box((x - 2.0, -8.03, 0.0), (x + 2.0, -8.0, 3.6), "MI_PaintedMetal")          # pier-side shutters
    canopy(b, -16.0, 16.0, -12.0, -8.0, 4.0)
    b.beam((14.0, 4.0, top), (14.0, 4.0, top + 12.0), 0.25, "MI_Steel")
    sign(b, -6.0, 6.0, -8.0, 4.4, 5.2, "MI_PlasticDark")
    return "Mil_PierTerminal", "military", b.mesh()


# ── the rest of a COMPACT base (user, 2026-09-28: every component a mission needs, in a walkable area) ─────────────

def mil_armoury(material, Builder):
    """弾薬庫 / armoury: an earth-covered 20 x 12 m bunker (a berm sloping over a concrete box), a steel blast door at
    -Y under a concrete headwall. A mission's 'steal the weapons' / 'plant the charge' target."""
    b = Builder("Mil_Armoury", material)
    b.box((-10.0, -6.0, 0.0), (10.0, 6.0, 4.0), "MI_ConcreteSmooth")
    b.frustum(0.0, 1.0, 0.0, 5.5, 13.0, 8.5, 8.0, 3.5, "MI_Grass")                    # the earth cover
    b.box((-6.0, -7.0, 0.0), (6.0, -6.0, 5.0), "MI_ConcreteSmooth")                     # the headwall
    b.box((-2.2, -7.05, 0.0), (2.2, -7.0, 3.2), "MI_Olive")                              # the blast door
    sign(b, -1.5, 1.5, -7.05, 3.5, 4.2, "MI_PaintYellow")
    return "Mil_Armoury", "military", b.mesh()


def mil_motor_pool(material, Builder):
    """車両整備場 / motor pool: a 40 x 14 m open-fronted shed (six bays, a steel roof on posts, a back wall), the
    vehicles parked in it are Mil_Truck props. Front -Y."""
    b = Builder("Mil_MotorPool", material)
    b.box((-20.0, -7.0, -0.05), (20.0, 7.0, 0.0), "MI_AsphaltLot")
    b.box((-20.0, 6.5, 0.0), (20.0, 7.0, 5.0), "MI_Corrugated")
    for x in range(-20, 21, 8):
        b.box((x - 0.2, -7.0, 0.0), (x + 0.2, -6.6, 5.0), "MI_PaintedMetal")
    b.box((-20.5, -7.5, 5.0), (20.5, 7.5, 5.4), "MI_Corrugated")
    return "Mil_MotorPool", "military", b.mesh()


def mil_truck(material, Builder):
    """A 3 1/2 t class military truck (73式大型トラック-like), olive: 7.2 x 2.5 m, 3.1 m tall, cab at -Y, canvas cover."""
    b = Builder("Mil_Truck", material)
    b.box((-1.25, -3.6, 0.8), (1.25, -1.6, 2.7), "MI_Olive")                              # cab
    b.box((-1.2, -3.62, 1.8), (1.2, -3.6, 2.5), "MI_Window")
    b.box((-1.25, -1.5, 0.8), (1.25, 3.6, 1.3), "MI_Olive")                               # bed
    b.box((-1.2, -1.4, 1.3), (1.2, 3.5, 3.1), "MI_Fabric")                                 # canvas
    for y in (-2.8, 1.4, 2.8):
        for x in (-1.1, 1.1):
            b.box((x - 0.2, y - 0.5, 0.0), (x + 0.2, y + 0.5, 1.0), "MI_PlasticDark")
    return "Mil_Truck", "military", b.mesh()


def mil_parade_ground(material, Builder):
    """グラウンド / parade ground: a 50 x 40 m paved square with white formation lines and a flag pole at +Y."""
    b = Builder("Mil_ParadeGround", material)
    b.box((-25.0, -20.0, -0.04), (25.0, 20.0, 0.02), "MI_AsphaltLot")   # asphalt (user, 2026-10-05: not white)
    for k in range(-4, 5):
        b.box((k * 5.0 - 0.06, -15.0, 0.02), (k * 5.0 + 0.06, 15.0, 0.03), "MI_PaintWhite")
    b.box((-0.1, 18.0, 0.0), (0.1, 18.2, 12.0), "MI_Steel")
    return "Mil_ParadeGround", "military", b.mesh()


def mil_helipad(material, Builder):
    """ヘリポート: a 25 m square pad, a white H in a circle's square, edge lights (dark here)."""
    b = Builder("Mil_Helipad", material)
    b.box((-12.5, -12.5, -0.04), (12.5, 12.5, 0.03), "MI_AsphaltLot")   # asphalt (user, 2026-10-05: not white)
    for x in (-3.0, 3.0):
        b.box((x - 0.6, -5.0, 0.03), (x + 0.6, 5.0, 0.04), "MI_PaintWhite")
    b.box((-2.4, -0.6, 0.03), (2.4, 0.6, 0.04), "MI_PaintWhite")
    for k in range(4):
        a = math.pi / 2 * k
        for t in (-9.0, -3.0, 3.0, 9.0):
            x, y = 11.5 * math.cos(a) - t * math.sin(a), 11.5 * math.sin(a) + t * math.cos(a)
            b.box((x - 0.2, y - 0.2, 0.03), (x + 0.2, y + 0.2, 0.25), "MI_PaintYellow")
    return "Mil_Helipad", "military", b.mesh()


def mil_fuel_depot(material, Builder):
    """燃料タンク: two 10 m fuel tanks (faceted cylinders, 8 m) in a 1 m concrete bund, 28 x 16 m, a pump shed at -Y."""
    b = Builder("Mil_FuelDepot", material)
    for (a0, b0, a1, b1) in ((-14, -8, 14, -7.6), (-14, 7.6, 14, 8), (-14, -8, -13.6, 8), (13.6, -8, 14, 8)):
        b.box((a0, b0, 0.0), (a1, b1, 1.0), "MI_ConcreteSmooth")
    for cx in (-6.5, 6.5):
        n = 16
        for k in range(n):
            a = 2 * math.pi * k / n
            b.box((cx + 4.8 * math.cos(a) - 1.0, 4.8 * math.sin(a) - 1.0, 0.0),
                  (cx + 4.8 * math.cos(a) + 1.0, 4.8 * math.sin(a) + 1.0, 8.0), "MI_PaintWhite")
        b.box((cx - 4.5, -4.5, 0.0), (cx + 4.5, 4.5, 8.2), "MI_PaintWhite")
    b.box((-3.0, -12.0, 0.0), (3.0, -8.5, 3.0), "MI_ConcreteSmooth")
    return "Mil_FuelDepot", "military", b.mesh()


def mil_patrol_ship(material, Builder):
    """A patrol ship (a JMSDF / coastguard patrol-vessel placeholder): 90 x 12 m, bow at -Y, grey hull (4 m above the
    water, origin AT THE WATERLINE), a superstructure and bridge, a mast, a gun mount forward, a hull number."""
    b = Builder("Mil_PatrolShip", material)
    g = "MI_JetGrey"
    b.box((-6.0, -35.0, -3.0), (6.0, 40.0, 4.0), g)                                        # hull
    b.frustum(0.0, -40.0, -3.0, 4.0, 0.5, 5.0, 6.0, 5.0, g)                                # bow
    b.box((-5.0, -12.0, 4.0), (5.0, 20.0, 9.0), g)                                          # superstructure
    b.box((-4.0, -12.0, 9.0), (4.0, -2.0, 12.0), g)                                         # bridge
    b.box((-4.03, -12.03, 10.0), (4.03, -11.9, 11.3), "MI_Window")
    b.beam((0.0, 0.0, 12.0), (0.0, 0.0, 24.0), 0.6, g)                                       # mast
    b.box((-1.5, -28.0, 4.0), (1.5, -24.0, 6.0), g)                                          # gun mount
    b.beam((0.0, -28.0, 5.5), (0.0, -33.0, 5.8), 0.25, g)
    b.box((-6.03, -30.0, 1.0), (-6.0, -24.0, 3.0), "MI_PaintWhite")                          # hull number (plain)
    b.box((-6.0, -35.0, -0.2), (6.0, 40.0, 0.0), "MI_CraneRed")                               # boot topping
    return "Mil_PatrolShip", "military", b.mesh()


# ── ONE LOGISTICS HUB (user, 2026-09-28: "fill the empty middle with a logistics park, compact, 1 or 2 so a level
# designer can use them, not repeated"). Beside the container terminal on the port platform: a トラックターミナル
# (cross-dock: trucks back onto both long sides) and a 物流センター (a distribution centre, docks on one face). The
# island has these ONCE; the generic Warehouse type stands in for small depots only. Sizes: a Japanese cross-dock
# terminal bay is ~30 m deep with 4 m dock spacing; a single-storey DC slab 100-150 m long, 6-7 m storeys.

LOGI_DOCK = 1.2       # a dock floor stands this high (a truck bed's height), so a truck backs onto it level


def logi_truck_terminal(material, Builder):
    """トラックターミナル: a 180 x 30 m cross-dock shed, dock-high floor (1.2 m), a dock door every 4 m on BOTH long
    faces (-Y the gate side, +Y the back yard) under 6 m canopies, a 3-storey office at the +X end. Origin at its
    centre on the ground."""
    b = Builder("Logi_TruckTerminal", material)
    L, D, H = 90.0, 15.0, 8.0
    b.box((-L, -D, 0.0), (L - 14.0, D, LOGI_DOCK), "MI_ConcreteSmooth")                  # the dock-high floor
    b.box((-L, -D, H - 0.4), (L - 14.0, D, H), "MI_Corrugated")                           # roof
    for x in (-L, L - 14.4):                                                               # end walls
        b.box((x, -D, LOGI_DOCK), (x + 0.4, D, H), "MI_Corrugated")
    for s in (-1.0, 1.0):
        y0 = s * D
        x = -L + 2.0
        while x < L - 16.0:                                                                # dock doors and piers
            b.box((x, y0 - 0.1, LOGI_DOCK), (x + 0.6, y0 + 0.1, H - 0.4), "MI_PaintedMetal")
            b.box((x + 0.6, y0 - 0.05, LOGI_DOCK + 3.2), (x + 3.4, y0 + 0.05, H - 0.4), "MI_Corrugated")
            b.box((x + 0.6, y0 + s * 0.05, LOGI_DOCK + 0.1), (x + 3.4, y0 + s * 0.08, LOGI_DOCK + 3.2), "MI_PaintYellow")
            x += 4.0
        b.box((-L, min(y0, y0 + s * 6.0), H - 1.0), (L - 14.0, max(y0, y0 + s * 6.0), H - 0.7), "MI_PaintedMetal")
    top = ribbon_block(b, L - 14.0, L, -D, D, 0.0, 3, 3.6, wall="MI_TileWhite")          # the office block
    roof(b, L - 14.0, L, -D, D, top, units=2)
    sign(b, L - 12.0, L - 2.0, -D, top - 1.6, top - 0.6, "MI_Sign")
    return "Logi_TruckTerminal", "logistics", b.mesh()


def logi_distribution_centre(material, Builder):
    """物流センター: a 120 x 70 m single-volume distribution centre, 2 storeys of 7 m (14 m, the rack hall), metal
    panel walls, a dock-high floor with 16 dock doors on the -Y face under a canopy, a 4-storey glazed office at the
    -X front corner. Origin at its centre on the ground."""
    b = Builder("Logi_DistributionCentre", material)
    X, Y, H = 60.0, 35.0, 14.0
    b.box((-X, -Y, 0.0), (X, Y, LOGI_DOCK), "MI_ConcreteSmooth")
    for (a0, b0, a1, b1) in ((-X, Y - 0.4, X, Y), (-X, -Y, -X + 0.4, Y), (X - 0.4, -Y, X, Y)):
        b.box((a0, b0, LOGI_DOCK), (a1, b1, H), "MI_Corrugated")
    b.box((-X, -Y, H - 0.4), (X, Y, H), "MI_Corrugated")
    x = -X + 18.0
    while x < X - 4.0:                                                                     # the dock face (-Y)
        b.box((x, -Y - 0.1, LOGI_DOCK), (x + 2.0, -Y + 0.1, H - 0.4), "MI_Corrugated")
        b.box((x + 2.0, -Y - 0.1, LOGI_DOCK + 3.4), (x + 5.0, -Y + 0.1, H - 0.4), "MI_Corrugated")
        b.box((x + 2.0, -Y - 0.05, LOGI_DOCK + 0.1), (x + 5.0, -Y + 0.05, LOGI_DOCK + 3.4), "MI_PaintYellow")
        x += 6.0
    b.box((-X + 16.0, -Y - 7.0, 6.0), (X, -Y, 6.4), "MI_PaintedMetal")                    # the dock canopy
    for x in range(int(-X + 18), int(X), 18):
        b.box((x - 0.2, -Y - 6.8, 0.0), (x + 0.2, -Y - 6.4, 6.0), "MI_PaintedMetal")
    top = ribbon_block(b, -X, -X + 16.0, -Y, -Y + 20.0, 0.0, 4, 3.6, wall="MI_TileWhite")  # the office corner
    b.box((-X + 16.0, -Y, LOGI_DOCK), (-X + 18.0, -Y + 0.2, H - 0.4), "MI_Corrugated")
    sign(b, -X + 2.0, -X + 14.0, -Y, top - 1.8, top - 0.6, "MI_Sign")
    b.box((-X + 20.0, -Y + 0.4, H), (X - 10.0, Y - 10.0, H + 0.02), "MI_PaintWhite")      # roof (a white membrane)
    return "Logi_DistributionCentre", "logistics", b.mesh()


def logi_truck(material, Builder):
    """A 10 t box truck (大型トラック, ウイング車): 12 x 2.5 m, 3.8 m tall, white cab at -Y, an aluminium box."""
    b = Builder("Logi_Truck", material)
    b.box((-1.25, -6.0, 0.9), (1.25, -3.9, 3.2), "MI_PaintWhite")
    b.box((-1.2, -6.02, 2.1), (1.2, -6.0, 3.0), "MI_Window")
    b.box((-1.25, -3.7, 1.1), (1.25, 6.0, 3.8), "MI_Steel")
    for y in (-4.9, 2.6, 4.4):
        for x in (-1.05, 1.05):
            b.box((x - 0.25, y - 0.55, 0.0), (x + 0.25, y + 0.55, 1.1), "MI_PlasticDark")
    return "Logi_Truck", "logistics", b.mesh()


def logi_trailer(material, Builder):
    """A tractor and a 40 ft box semi-trailer (トレーラー): 16.5 x 2.5 m, 4.0 m tall, the tractor at -Y."""
    b = Builder("Logi_Trailer", material)
    b.box((-1.25, -8.25, 0.9), (1.25, -5.4, 3.3), "MI_PostRed")
    b.box((-1.2, -8.27, 2.2), (1.2, -8.25, 3.1), "MI_Window")
    b.box((-1.25, -5.0, 1.3), (1.25, 8.25, 4.0), "MI_PaintWhite")
    for y in (-7.2, -5.9, 5.4, 6.6, 7.8):
        for x in (-1.05, 1.05):
            b.box((x - 0.25, y - 0.5, 0.0), (x + 0.25, y + 0.5, 1.0), "MI_PlasticDark")
    return "Logi_Trailer", "logistics", b.mesh()


def logi_gate_house(material, Builder):
    """守衛所: a 4 x 3 m guard house between an in and an out lane, a barrier arm on each; 14 m across, road at -Y."""
    b = Builder("Logi_GateHouse", material)
    b.box((-2.0, -1.5, 0.0), (2.0, 1.5, 2.8), "MI_TileWhite")
    b.box((-2.2, -1.7, 2.8), (2.2, 1.7, 3.1), "MI_PaintedMetal")
    b.box((-2.03, -1.0, 0.9), (-2.0, 1.0, 2.2), "MI_Window")
    b.box((2.0, -1.0, 0.9), (2.03, 1.0, 2.2), "MI_Window")
    for s in (-1.0, 1.0):          # the barrier arms, RAISED (2026-10-05: both lanes open)
        b.box((s * 2.25 - 0.05, -1.9, 0.9), (s * 2.25 + 0.05, -1.8, 5.0), "MI_PaintYellow")
    return "Logi_GateHouse", "logistics", b.mesh()


def logi_fence(material, Builder):
    """One 10 m bay of a logistics yard's fence: 1.8 m mesh on posts, along X (no barbed wire: a yard, not a base)."""
    b = Builder("Logi_Fence", material)
    fence(b, -5.0, 5.0, 0.0, 0.0, h=1.8, gaps=(("b", 0.0, 12.0),), post=5.0)   # one run: the "b" copy cut away
    return "Logi_Fence", "logistics", b.mesh()


def _yard(b, hx, hy, bays):
    """An asphalt yard hx x hy (half sizes), white parking lines: `bays` = [(x0, x1, y, pitch, depth)]."""
    b.box((-hx, -hy, -0.05), (hx, hy, 0.0), "MI_AsphaltLot")
    for x0, x1, y, pitch, depth in bays:
        x = x0
        while x <= x1 + 1e-6:
            b.box((x - 0.07, min(y, y + depth), 0.0), (x + 0.07, max(y, y + depth), 0.01), "MI_PaintWhite")
            x += pitch


def logi_yard_tt(material, Builder):
    """The truck terminal's 225 x 150 m yard (asphalt, bay lines at both dock faces and the trailer park)."""
    b = Builder("Logi_YardTruckTerminal", material)
    _yard(b, 112.5, 75.0, [(-88.0, 62.0, -15.0, 4.0, -14.0), (-88.0, 62.0, 15.0, 4.0, 14.0),
                           (-100.0, 100.0, 50.0, 4.0, 18.0)])
    return "Logi_YardTruckTerminal", "logistics", b.mesh()


def logi_yard_dc(material, Builder):
    """The distribution centre's 225 x 240 m yard: truck bays at the dock face, a trailer park, a staff car park."""
    b = Builder("Logi_YardDistribution", material)
    _yard(b, 112.5, 120.0, [(-62.0, 34.0, 31.0, 6.0, 14.0), (40.0, 100.0, 20.0, 4.0, 18.0),
                            (-100.0, -20.0, -100.0, 2.5, 5.0), (-100.0, -20.0, -80.0, 2.5, 5.0)])
    return "Logi_YardDistribution", "logistics", b.mesh()


LOGISTICS_NOTES = {
    "Logi_TruckTerminal": "Placeholder トラックターミナル, 180 x 30 m cross-dock, dock floor 1.2 m high, doors on both long "
                          "faces (-Y gate side, +Y back yard), office at +X. Composite LogisticsTruckTerminal.",
    "Logi_DistributionCentre": "Placeholder 物流センター, 120 x 70 x 14 m, dock face -Y (16 doors), office at the -X front "
                               "corner. Composite LogisticsDistributionCentre.",
    "Logi_Truck": "Placeholder 10 t box truck, cab -Y. Static prop (collider = its bounds).",
    "Logi_Trailer": "Placeholder tractor + 40 ft box trailer, tractor -Y. Static prop.",
    "Logi_GateHouse": "Placeholder 守衛所 with two barrier arms (raised), road at -Y. The composite collides only "
                      "with the guard house, so both lanes are drivable.",
    "Logi_Fence": "One 10 m bay of the logistics yards' fence, along X.",
    "Logi_YardTruckTerminal": "The truck terminal's yard slab (225 x 150 m), no collider (the site's ground box is it).",
    "Logi_YardDistribution": "The distribution centre's yard slab (225 x 240 m), no collider.",
}
CIVIC_NOTES.update(LOGISTICS_NOTES)
_BUILD_ALL_CIVIC = build_all


def build_all(material, Builder):
    return _BUILD_ALL_CIVIC(material, Builder) + [f(material, Builder) for f in (
        logi_truck_terminal, logi_distribution_centre, logi_truck, logi_trailer, logi_gate_house, logi_fence,
        logi_yard_tt, logi_yard_dc)]


# ── the central station's 駅前広場 (user, 2026-09-28: "place parking entrance / bus stop etc like a Japanese central
# hub"). Placed by the CentralForecourt composite round the ekimae rotary (tools/island_core_streets.py). ───────────
def parking_multistorey(material, Builder):
    """立体駐車場: 30 x 40 m, the ground floor + three decks + roof parking (2.9 m storeys, 11.6 m to the roof
    parapet), open sides behind 1.1 m parapets, a column grid, the in/out ramp mouth on the street face (-Y) and the
    blue P sign. A 4-level self-park of ~220 bays is the ordinary size beside a Japanese hub station."""
    b = Builder("Parking_Multistorey", material)
    hx, hy, st = 15.0, 20.0, 2.9
    for k in range(5):                                        # the ground slab, three decks and the roof
        z = k * st
        b.box((-hx, -hy, z - (0.02 if k == 0 else 0.3)), (hx, hy, z), "MI_ConcreteSmooth" if k else "MI_AsphaltLot")
        if k:
            for s in (-1, 1):                                 # parapets on the long and short faces
                b.box((-hx, s * hy - 0.12 * (s > 0), z), (hx, s * hy + 0.12 * (s < 0), z + 1.1), "MI_ConcreteSmooth")
                b.box((s * hx - 0.12 * (s > 0), -hy, z), (s * hx + 0.12 * (s < 0), hy, z + 1.1), "MI_ConcreteSmooth")
    for x in (-hx + 0.3, -5.0, 5.0, hx - 0.3):                # the column grid (8.1 m bays: 3 cars between columns)
        for y in (-hy + 0.3, -10.0, 0.0, 10.0, hy - 0.3):
            b.box((x - 0.3, y - 0.3, 0.0), (x + 0.3, y + 0.3, 4 * st), "MI_ConcreteSmooth")
    b.box((-hx + 1.0, -hy - 0.25, 4 * st + 1.1), (-hx + 7.0, -hy - 0.15, 4 * st + 3.6), "MI_SignCyan")   # P
    b.box((-3.5, -hy - 0.4, 2.3), (3.5, -hy, 2.6), "MI_PaintYellow")                   # the height bar (2.1 m)
    b.box((-3.5, -hy + 2.0, 0.0), (3.5, -hy + 3.0, 0.02), "MI_PaintWhite")             # the gate stop line
    return "Parking_Multistorey", "station_plaza", b.mesh()


def plaza_clock(material, Builder):
    """The 駅前 clock: a 4.5 m square post with a clock box on top, faces on all four sides."""
    b = Builder("Plaza_Clock", material)
    b.box((-0.6, -0.6, 0.0), (0.6, 0.6, 0.4), "MI_StoneWall")
    b.box((-0.12, -0.12, 0.4), (0.12, 0.12, 3.6), "MI_PaintedMetalDark")
    b.box((-0.45, -0.45, 3.6), (0.45, 0.45, 4.5), "MI_PaintedMetalDark")
    for s in (-1, 1):
        b.box((-0.35, s * 0.46 - 0.01, 3.7), (0.35, s * 0.46 + 0.01, 4.4), "MI_PlasticWhite")
        b.box((s * 0.46 - 0.01, -0.35, 3.7), (s * 0.46 + 0.01, 0.35, 4.4), "MI_PlasticWhite")
    return "Plaza_Clock", "station_plaza", b.mesh()


def plaza_bike_rack(material, Builder):
    """駐輪場: a 6 m rack of ten front-wheel slots (0.6 m pitch) under a light roof, bikes nose in to +Y."""
    b = Builder("Plaza_BikeRack", material)
    b.box((-3.0, -1.0, 0.0), (3.0, 1.0, 0.02), "MI_AsphaltLot")
    for i in range(10):
        x = -2.7 + 0.6 * i
        b.box((x - 0.03, 0.2, 0.0), (x + 0.03, 1.0, 0.45), "MI_Steel")
    for x in (-2.9, 2.9):
        b.box((x - 0.05, 0.85, 0.0), (x + 0.05, 0.95, 2.2), "MI_PaintedMetal")
    b.box((-3.0, -0.6, 2.2), (3.0, 1.0, 2.25), "MI_PaintedMetal")
    return "Plaza_BikeRack", "station_plaza", b.mesh()


def taxi_sign(material, Builder):
    """タクシーのりば: a 2.8 m pole with a yellow board; the taxis queue along the kerb behind it."""
    b = Builder("Taxi_Sign", material)
    b.box((-0.2, -0.2, 0.0), (0.2, 0.2, 0.15), "MI_ConcreteSmooth")
    b.box((-0.04, -0.04, 0.15), (0.04, 0.04, 2.8), "MI_PaintedMetal")
    b.box((-0.45, -0.04, 2.0), (0.45, 0.04, 2.8), "MI_SignYellow")
    return "Taxi_Sign", "station_plaza", b.mesh()


def plaza_canopy(material, Builder):
    """屋根付き歩道: a 10 m bay of the covered walk from the bus berths to the station, 4 m wide, 3.2 m clear; posts on
    the -Y edge (the kerb side) only, so the walk under it is open. Tiled along X by the composite."""
    b = Builder("Plaza_Canopy", material)
    b.box((-5.0, -2.0, 3.2), (5.0, 2.0, 3.45), "MI_PaintedMetal")
    b.box((-5.0, -2.05, 3.45), (5.0, -1.95, 3.6), "MI_PaintedMetalDark")
    b.box((-0.1, -1.9, 0.0), (0.1, -1.7, 3.2), "MI_PaintedMetal")
    return "Plaza_Canopy", "station_plaza", b.mesh()


PLAZA_NOTES = {
    "Parking_Multistorey": "Placeholder 立体駐車場, 30 x 40 m, 4 levels + roof; the ramp mouth and height bar on the "
                           "street face (-Y). A static building to the game (its collider is its bounds): no ramp to "
                           "drive yet. Composite CentralForecourt.",
    "Plaza_Clock": "Placeholder 駅前 clock tower, 4.5 m.",
    "Plaza_BikeRack": "Placeholder 駐輪場 rack, 6 x 2 m, ten slots; bikes nose in to +Y.",
    "Taxi_Sign": "Placeholder タクシーのりば sign; the rank is the kerb behind it (a taxi queue is a runtime job).",
    "Plaza_Canopy": "One 10 m bay of the covered walk (4 m wide, 3.2 m clear), posts on the -Y kerb edge; tiled along X.",
}
CIVIC_NOTES.update(PLAZA_NOTES)
_BUILD_ALL_LOGI = build_all


def build_all(material, Builder):
    return _BUILD_ALL_LOGI(material, Builder) + [f(material, Builder) for f in (
        parking_multistorey, plaza_clock, plaza_bike_rack, taxi_sign, plaza_canopy)]


# ── the waterfront park's Ferris wheel (user, 2026-09-29: "the Ferris wheel was discussed and never placed") ─────────
# Tokyo Bay's big wheels stand in a waterfront leisure park beside the seaside hotels and a station, and read from the
# expressway: Palette Town (Odaiba, 115 m tall, 100 m across) and Kasai Rinkai Park (117 m, 111 m). This one is 100 m
# across on a 60 m hub (110 m to the top), on the gulf's east shore beside the resort hotels.

def ferris_wheel_park(material, Builder):
    """観覧車のある臨海公園 on a 110 x 160 plot (2026-10-02 night: moved south of the Suburb WB entrance onto the plain
    by the beach). X across (the gulf at -X), Y along (the beach and the open sea at -Y, the scene's front; the suburb
    loop's corner at +X +Y): grass, a 6 m promenade along the two waterfront edges (-X, -Y), an entrance plaza at the
    +X +Y corner with a path to the wheel, and the wheel in the water corner (-X -Y) -- a 100 m rim (two rings 6 m
    apart, spokes, 32 gondolas) turning in the X-Z plane, so its full circle faces the open sea (-Y) (item 4: "the full
    circle faces open water"), on two A-frame legs, with a boarding hall under its low point."""
    b = Builder("Park_FerrisWheel", material)
    hx, hy = 55.0, 80.0
    ground(b, -hx, hx, -hy, hy, "MI_Grass")
    b.box((-hx, -hy, 0.0), (-hx + 6.0, hy, 0.05), "MI_ConcreteSmooth")         # promenade, gulf side (-X)
    b.box((-hx, -hy, 0.0), (hx, -hy + 6.0, 0.05), "MI_ConcreteSmooth")         # promenade, sea side (-Y)
    b.box((-hx, -hy, 0.05), (-hx + 0.1, hy, 1.1), "MI_PaintedMetal")             # the waterfront railing
    b.box((-hx, -hy, 0.05), (hx, -hy + 0.1, 1.1), "MI_PaintedMetal")
    b.box((hx - 30.0, hy - 22.0, 0.0), (hx, hy, 0.06), "MI_ConcreteSmooth")    # entrance plaza (+X +Y corner)
    b.box((-3.0, -28.0, 0.0), (3.0, hy - 22.0, 0.05), "MI_ConcreteSmooth")     # path south to the wheel
    b.box((3.0, hy - 28.0, 0.0), (hx - 30.0, hy - 22.0, 0.05), "MI_ConcreteSmooth")
    cx, cy, hub, R = 0.0, -40.0, 60.0, 50.0                                   # the wheel: centre (x, y), hub z, radius
    n = 48
    for side in (-3.0, 3.0):                                                  # two rims, 6 m apart across Y
        y = cy + side
        pts = [(cx + R * math.cos(2 * math.pi * k / n), y, hub + R * math.sin(2 * math.pi * k / n)) for k in range(n)]
        for k in range(n):
            b.beam(pts[k], pts[(k + 1) % n], 0.9, "MI_PaintWhite")
        for k in range(0, n, 3):                                              # spokes
            b.beam((cx, y, hub), pts[k], 0.25, "MI_Steel")
    for k in range(0, n, 3):                                                  # cross ties between the rims
        a = 2 * math.pi * k / n
        x, z = cx + R * math.cos(a), hub + R * math.sin(a)
        b.beam((x, cy - 3.0, z), (x, cy + 3.0, z), 0.35, "MI_PaintWhite")
    b.beam((cx, cy - 5.0, hub), (cx, cy + 5.0, hub), 2.4, "MI_Steel")          # the axle and hub
    for k in range(32):                                                       # gondolas hang below the rim
        a = 2 * math.pi * k / 32
        x, z = cx + (R + 1.5) * math.cos(a), hub + (R + 1.5) * math.sin(a) - 2.2
        colour = ("MI_CraneRed", "MI_SignCyan", "MI_PaintYellow", "MI_SignPink")[k % 4]
        b.box((x - 1.2, cy - 1.4, z - 1.2), (x + 1.2, cy + 1.4, z + 1.2), colour)
        b.box((x - 1.25, cy - 1.45, z + 0.1), (x + 1.25, cy + 1.45, z + 0.9), "MI_GlassClear")
    for side in (-1, 1):                                                      # A-frame legs, splayed across Y
        top = (cx, cy + side * 5.0, hub)
        for dx in (-18.0, 18.0):
            b.beam((cx + dx, cy + side * 16.0, 0.0), top, 1.6, "MI_PaintWhite")
        b.box((cx - 20.0, cy + side * 16.0 - 2.0, 0.0), (cx + 20.0, cy + side * 16.0 + 2.0, 0.8), "MI_ConcreteSmooth")
    lo = hub - R - 3.7                                                        # the boarding hall under the low point
    b.box((cx - 9.0, cy - 12.0, 0.0), (cx + 9.0, cy + 12.0, 0.3), "MI_ConcreteSmooth")
    b.box((cx - 9.0, cy - 12.0, 0.3), (cx - 8.8, cy + 12.0, lo - 0.5), "MI_GlassClear")
    b.box((cx + 8.8, cy - 12.0, 0.3), (cx + 9.0, cy + 12.0, lo - 0.5), "MI_GlassClear")
    b.box((cx - 9.5, cy - 12.5, lo - 0.5), (cx + 9.5, cy + 12.5, lo - 0.2), "MI_PaintedMetal")
    b.box((cx - 9.0, cy + 12.0, 0.3), (cx + 9.0, cy + 12.2, lo - 0.5), "MI_TileWhite")
    b.box((cx - 4.0, cy + 12.1, 2.2), (cx + 4.0, cy + 12.3, 3.6), "MI_SignPink")   # the ticket-hall sign
    for (x, y) in ((-40.0, -10.0), (-40.0, 20.0), (-40.0, 50.0), (-25.0, -70.0), (10.0, -70.0), (35.0, -70.0),
                   (20.0, 0.0), (20.0, 30.0), (-20.0, 60.0), (10.0, 60.0)):
        b.box((x - 0.9, y - 0.25, 0.4), (x + 0.9, y + 0.25, 0.5), "MI_Wood")       # benches
        b.box((x - 0.8, y - 0.2, 0.0), (x - 0.6, y + 0.2, 0.4), "MI_PaintedMetal")
        b.box((x + 0.6, y - 0.2, 0.0), (x + 0.8, y + 0.2, 0.4), "MI_PaintedMetal")
    return "Park_FerrisWheel", "civic", b.mesh()


CIVIC_NOTES["Park_FerrisWheel"] = (
    "Placeholder 観覧車 waterfront park, 110 x 160 plot (the sea -Y, the gulf -X, the entrance at +X +Y): a 100 m "
    "wheel on a 60 m hub (two white rims, 32 gondolas, A-frame legs) in the water corner, a boarding hall under its low "
    "point, a promenade along both waterfront edges. The game assumes: the wheel's plane is X-Z (its circle faces "
    "+-Y, the open sea), the wheel does not "
    "turn yet (a later runtime job: rotate a separate rim + gondola object), and the collider is the mesh itself.")
_BUILD_ALL_PLAZA = build_all


def build_all(material, Builder):
    return _BUILD_ALL_PLAZA(material, Builder) + [ferris_wheel_park(material, Builder)]


# the 2026-10-03 review's Japanese city types (gangs, pachinko, shotengai, danchi, hotels, the construction site, the
# arena, the suburban mall + cinema, the campus, the small shops, the broadcast centre): blender/tools/library_jp_city.py
CIVIC_NOTES.update(__import__("library_jp_city").NOTES)
_BUILD_ALL_FERRIS = build_all


def build_all(material, Builder):
    return _BUILD_ALL_FERRIS(material, Builder) + __import__("library_jp_city").build_all(material, Builder)
