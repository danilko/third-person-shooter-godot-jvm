"""Japanese city types the 2026-10-03 review found missing (user: "do all, so less vacancy"): PLACEHOLDER massings an
artist replaces by hand in library.blend, chained into library_civic.build_all. Ours, CC0.

Frame as every library piece: Z up, origin at the PLOT centre on the ground (the civic types, `plot_origin`) or the
footprint centre (the small shops placed by the district mixes), the STREET side facing -Y (Godot +Z). Sizes are
ordinary Japanese ones (public record / PLATEAU class medians where it has the class); each piece's EDIT_NOTE says
what the game assumes about it.
"""
import math

from library_civic import ribbon_block, punched_block, roof, sign, canopy, fence, ground, gable, hip

NOTES = {}


def _note(name, text):
    NOTES[name] = text


def _parking(b, x0, x1, y0, y1, bay=2.5, depth=5.0, rows=1):
    """Asphalt with white bay lines along X; `rows` rows of bays from y0 upward, aisles between."""
    ground(b, x0, x1, y0, y1, "MI_AsphaltLot")
    y = y0
    for _ in range(rows):
        x = x0 + 1.0
        while x + bay <= x1 - 1.0:
            b.box((x, y, 0.02), (x + 0.1, y + depth, 0.04), "MI_PaintWhite")
            x += bay
        y += depth + 6.0


def _cars(b, pts, mat="MI_PaintedMetalDark"):
    """Parked car blocks (placeholders): (x, y, yaw 0 = along Y)."""
    for x, y, along_x in pts:
        hx, hy = (2.2, 0.85) if along_x else (0.85, 2.2)
        b.box((x - hx, y - hy, 0.2), (x + hx, y + hy, 1.0), mat)
        b.box((x - hx * 0.6, y - hy * 0.8, 1.0), (x + hx * 0.6, y + hy * 0.8, 1.45), "MI_Window")


# ── the gangs (gangs.json): 黒鉄会 Kurogane-kai (old-school, downtown / nightlife) and 青木場組 Aokiba-gumi (younger,
# the harbour / industry). Each has an HQ, a street office (事務所) and a front. Kurogane's HQ is the existing
# SecureMansion on the hill; its fronts are AdultServices and the pachinko parlour.

def jimusho(material, Builder):
    """組事務所: a 4-storey 雑居ビル 9 x 15 m on a 12 x 20 plot -- black film over every window, a steel door, cameras
    at each corner, the 代紋 (gold crest) plaque over the door, a roller shutter for the car, a roof fence."""
    b = Builder("Gang_Jimusho", material)
    x0, x1, y0, y1 = -4.5, 4.5, -8.5, 6.5
    top = punched_block(b, x0, x1, y0, y1, 0.0, 4, 3.2, wall="MI_TileBrown", glass="MI_PlasticDark", bay=3.0,
                        win=1.6, sides="fblr")
    roof(b, x0, x1, y0, y1, top, parapet=1.4, units=2)
    b.box((-4.0, y0 - 0.06, 0.0), (-0.6, y0, 2.6), "MI_PaintedMetalDark")       # the shutter (the car's)
    b.box((0.6, y0 - 0.08, 0.0), (2.0, y0, 2.2), "MI_Steel")                     # the steel door
    b.box((0.9, y0 - 0.2, 2.5), (1.7, y0, 3.1), "MI_Gold")                       # 代紋
    for x in (x0 + 0.2, x1 - 0.2):
        b.box((x - 0.15, y0 - 0.35, 2.9), (x + 0.15, y0, 3.2), "MI_PlasticWhite")  # cameras
    ground(b, -6.0, 6.0, -10.0, y0, "MI_ConcreteSmooth")
    return "Gang_Jimusho", "civic", b.mesh()


_note("Gang_Jimusho", "Placeholder 組事務所, 12 x 20 plot, the street at -Y: 4 storeys, black film windows, steel door "
      "(+X of centre) and a car shutter (-X). The game assumes: shut for now (no interior); a mission re-dress of "
      "SafeHouseCityLarge's interior is the planned enterable version; each gang's office is the SAME piece.")


def port_compound(material, Builder):
    """青木場組 HQ: a walled port yard 70 x 55 -- a 3 m concrete wall with a sliding steel gate at the street, a
    2-storey office (20 x 12), a warehouse (30 x 20), stacked containers, a watchtower at the back corner."""
    b = Builder("Gang_PortCompound", material)
    hx, hy = 35.0, 27.5
    ground(b, -hx, hx, -hy, hy, "MI_ConcreteSmooth")
    for (a0, b0, a1, b1) in ((-hx, hy - 0.4, hx, hy), (-hx, -hy, -hx + 0.4, hy), (hx - 0.4, -hy, hx, hy),
                             (-hx, -hy, -6.0, -hy + 0.4), (6.0, -hy, hx, -hy + 0.4)):
        b.box((a0, b0, 0.0), (a1, b1, 3.0), "MI_ConcreteSmooth")
    b.box((-6.0, -hy - 0.1, 0.0), (6.0, -hy + 0.1, 2.6), "MI_PaintedMetalDark")  # the gate (shut)
    top = ribbon_block(b, -hx + 3.0, -hx + 23.0, -hy + 6.0, -hy + 18.0, 0.0, 2, 3.4, wall="MI_Corrugated",
                       glass="MI_PlasticDark")
    roof(b, -hx + 3.0, -hx + 23.0, -hy + 6.0, -hy + 18.0, top, units=2, stair=False)
    b.box((-2.0, 4.0, 0.0), (28.0, 24.0, 9.0), "MI_Corrugated")                    # the warehouse
    b.frustum(13.0, 14.0, 9.0, 10.5, 15.0, 10.0, 15.0, 0.5, "MI_PaintedMetal")
    b.box((4.0, 3.94, 0.0), (10.0, 4.0, 5.0), "MI_PaintedMetalDark")               # its door
    for i, (x, y) in enumerate(((-30.0, 8.0), (-30.0, 11.0), (-18.0, 8.0))):
        for k in range(2 if i < 2 else 1):
            b.box((x, y - 1.22, k * 2.6), (x + 6.06, y + 1.22, k * 2.6 + 2.59),
                  ("MI_CraneRed", "MI_SignCyan", "MI_Olive")[(i + k) % 3])
    b.box((hx - 6.0, hy - 6.0, 0.0), (hx - 2.0, hy - 2.0, 7.0), "MI_Steel")       # the watchtower
    b.box((hx - 6.5, hy - 6.5, 7.0), (hx - 1.5, hy - 1.5, 9.4), "MI_PaintedMetalDark")
    _cars(b, ((-10.0, -12.0, False), (-6.0, -12.0, False), (14.0, -14.0, True)))
    return "Gang_PortCompound", "civic", b.mesh()


_note("Gang_PortCompound", "Placeholder 青木場組 HQ, 70 x 55 walled port yard, the street at -Y: the gate (12 m, shut) "
      "mid-front, office front-left, warehouse back-right, containers, a watchtower. The game assumes: the yard is "
      "walkable inside a closed wall; a mission opens the gate (later).")


def scrapyard(material, Builder):
    """解体屋 / 中古車屋 (青木場組's front): a 50 x 40 yard -- a corrugated fence, a used-car row at the street with
    price boards, a site cabin, stacks of crushed hulks and a grab crane at the back."""
    b = Builder("Gang_Scrapyard", material)
    hx, hy = 25.0, 20.0
    ground(b, -hx, hx, -hy, hy, "MI_Dirt")
    ground(b, -hx, hx, -hy, -hy + 8.0, "MI_AsphaltLot", z=0.03)
    for (a0, b0, a1, b1) in ((-hx, -hy + 8.0, -hx + 0.2, hy), (hx - 0.2, -hy + 8.0, hx, hy), (-hx, hy - 0.2, hx, hy),
                             (-hx, -hy + 8.0, -7.0, -hy + 8.2), (7.0, -hy + 8.0, hx, -hy + 8.2)):   # a 14 m opening (2026-10-04)
        b.box((a0, b0, 0.0), (a1, b1, 2.4), "MI_Corrugated")
    _cars(b, [(-20.0 + 5.0 * i, -hy + 4.0, False) for i in range(9)], "MI_PlasticWhite")
    for i in range(9):
        b.box((-21.0 + 5.0 * i, -hy + 1.4, 1.5), (-19.0 + 5.0 * i, -hy + 1.5, 2.1), "MI_SignYellow")
    b.box((-hx + 2.0, -hy + 10.0, 0.0), (-hx + 10.0, -hy + 14.0, 2.7), "MI_PlasticWhite")   # the cabin
    for k in range(12):
        x, y = -14.0 + (k % 6) * 6.0, 8.0 + (k // 6) * 6.0
        for s in range(3):
            b.box((x - 2.0, y - 0.9, s * 0.9), (x + 2.0, y + 0.9, s * 0.9 + 0.85),
                  ("MI_PaintedMetalDark", "MI_CraneRed", "MI_SignCyan")[(k + s) % 3])
    b.beam((18.0, 12.0, 0.0), (18.0, 12.0, 8.0), 0.8, "MI_PaintYellow")
    b.beam((18.0, 12.0, 8.0), (8.0, 12.0, 6.0), 0.5, "MI_PaintYellow")
    return "Gang_Scrapyard", "civic", b.mesh()


_note("Gang_Scrapyard", "Placeholder 解体屋 / used-car lot (青木場組's front), 50 x 40, the street at -Y: the used-car "
      "row on asphalt at the front, the yard behind a corrugated fence with a 14 m opening. The game assumes: the "
      "gang's clerk/contact stands by the cabin (front-left); the cars are mesh, not vehicles.")


def pachinko(material, Builder):
    """パチンコ店 on a 60 x 45 plot: a 34 x 22 hall, two storeys (10 m) with a lit glazed entrance and the facade's
    neon band, a 22 m sign tower, the 景品交換所 (prize-exchange kiosk) apart at the side, the car park in front."""
    b = Builder("Pachinko", material)
    hx, hy = 30.0, 22.5
    _parking(b, -hx, hx, -hy, -hy + 18.0, rows=1)
    x0, x1, y0, y1 = -20.0, 14.0, 0.0, 22.0
    b.box((x0, y0, 0.0), (x1, y1, 10.0), "MI_TileWhite")
    b.box((x0 - 0.5, y0 - 0.5, 10.0), (x1 + 0.5, y1 + 0.5, 10.4), "MI_PaintedMetal")
    b.box((-6.0, y0 - 0.05, 0.0), (6.0, y0, 3.2), "MI_GlassClear")                 # the entrance
    b.box((x0, y0 - 0.25, 4.0), (x1, y0, 9.0), "MI_SignPink")                      # the neon facade band
    b.box((-12.0, y0 - 0.35, 5.0), (6.0, y0 - 0.25, 8.0), "MI_SignYellow")
    canopy(b, -7.0, 7.0, y0 - 3.0, y0, 3.4, "MI_PaintedMetal")
    b.box((x1 + 2.0, -4.0, 0.0), (x1 + 3.2, -2.8, 22.0), "MI_Steel")               # the sign tower
    b.box((x1 + 0.6, -4.6, 14.0), (x1 + 4.6, -2.2, 22.0), "MI_SignRed")
    b.box((x1 + 9.0, 14.0, 0.0), (x1 + 12.0, 17.0, 2.6), "MI_TileBrown")           # 景品交換所
    b.box((x1 + 9.0, 13.95, 1.0), (x1 + 10.0, 14.0, 1.6), "MI_PlasticDark")
    _cars(b, ((-24.0, -18.0, False), (-16.5, -18.0, False), (8.5, -18.0, False)))
    return "Pachinko", "civic", b.mesh()


_note("Pachinko", "Placeholder パチンコ店, 60 x 45 plot, the street at -Y: the car park in front, the hall behind, a "
      "sign tower, the 景品交換所 kiosk at the back-right corner (a robbery target). Shut for now; an enterable hall "
      "floor (rows of machines) is the planned interior. 黒鉄会's front.")


# ── the street's small shops (the district mixes place these between the shop-houses) ───────────────────────────
def _small_shop(name, w, d, storeys, wall, band, noren=None, glass=True, sign_mat="MI_Sign"):
    def make(material, Builder):
        b = Builder(name, material)
        x0, x1, y0, y1 = -w / 2, w / 2, -d / 2, d / 2
        top = punched_block(b, x0, x1, y0, y1, 3.6, storeys - 1, 3.0, wall=wall, bay=3.0, win=1.4, sides="f") \
            if storeys > 1 else 3.6
        b.box((x0, y0, 0.0), (x1, y1, 3.6), wall)
        if glass:
            b.box((x0 + 0.5, y0 - 0.04, 0.2), (x1 - 0.5, y0, 2.6), "MI_GlassClear")
        b.box((x0, y0 - 0.2, 2.8), (x1, y0, 3.5), band)                            # the shop's fascia band
        if noren:
            b.box((-1.2, y0 - 0.3, 1.8), (1.2, y0 - 0.25, 2.7), noren)
        b.box((x1 - 1.0, y0 - 0.9, 3.8), (x1 - 0.8, y0 - 0.1, top - 0.5), sign_mat)   # a 袖看板
        roof(b, x0, x1, y0, y1, top, parapet=0.9, units=1, stair=False)
        return name, "civic", b.mesh()
    return make


SMALL_SHOPS = (
    ("Shop_Ramen", 7.0, 14.0, 2, "MI_TileBeige", "MI_SignRed", "MI_NorenNavy", "ラーメン屋: a counter shop, a red "
     "band, a navy 暖簾"),
    ("Shop_Gyudon", 9.0, 14.0, 2, "MI_TileWhite", "MI_SignYellow", None, "牛丼チェーン: a yellow/orange band, "
     "glass front, open all night"),
    ("Shop_Drugstore", 16.0, 20.0, 2, "MI_TileWhite", "MI_SignGreen", None, "ドラッグストア: a wide glass front "
     "with goods out on the pavement (placeholder band only)"),
    ("Shop_HundredYen", 14.0, 18.0, 1, "MI_TileWhite", "MI_SignPink", None, "100円ショップ: one storey, a pink band"),
    ("Shop_CoinLaundry", 6.0, 12.0, 2, "MI_TileBeige", "MI_SignCyan", None, "コインランドリー: a narrow glass front, "
     "machines along the walls (later)"),
    ("Shop_Bookstore", 9.0, 14.0, 2, "MI_TileBrown", "MI_SignGreen", None, "町の本屋 (neighbourhood bookstore): a "
     "glass front, the magazine rack under the canopy (later)"),
)


def small_shops(material, Builder):
    out = []
    for name, w, d, n, wall, band, noren, note in SMALL_SHOPS:
        out.append(_small_shop(name, w, d, n, wall, band, noren)(material, Builder))
    return out


for _n, _w, _d, _s, _wall, _band, _nor, _txt in SMALL_SHOPS:
    _note(_n, "Placeholder " + _txt + " -- %.0f x %.0f m, %d storey(s), the street at -Y. Placed by the district "
          "mixes (island_buildings.REGIONS); shut." % (_w, _d, _s))


# ── 商店街: the covered shopping street ─────────────────────────────────────────────────────────────────────────
def shotengai(material, Builder):
    """アーケード商店街 on a 24 x 110 plot running BACK from the street (-Y): a 6 m walkway down the middle under an
    arched glazed roof on steel frames (8 m to the crown), 8 m-deep two-storey shop fronts both sides (shutters,
    signs, a few open glass fronts), the arcade gate with its name board at the street end, open at the back."""
    b = Builder("Shotengai", material)
    hy = 55.0
    ground(b, -3.0, 3.0, -hy, hy, "MI_Terrazzo", z=0.05)
    cols = ("MI_SignRed", "MI_SignYellow", "MI_SignGreen", "MI_SignCyan", "MI_SignPink", "MI_NorenNavy")
    for side in (-1, 1):
        x0, x1 = (-12.0, -3.0) if side < 0 else (3.0, 12.0)
        face = -3.0 if side < 0 else 3.0
        n = 0
        y = -hy + 2.0
        while y + 5.5 <= hy - 1.0:
            w = 5.5 + (n % 3)
            b.box((x0, y, 0.0), (x1, y + w - 0.2, 7.0 + (n % 2)), ("MI_TileBeige", "MI_TileWhite", "MI_TileBrown")[n % 3])
            fx = face if side < 0 else face - 0.05
            gl = "MI_GlassClear" if n % 2 == 0 else "MI_PaintedMetal"            # an open front or a shutter
            b.box((fx - 0.05 * side, y + 0.4, 0.1), (fx, y + w - 0.6, 2.8), gl) if side < 0 else \
                b.box((fx, y + 0.4, 0.1), (fx + 0.05, y + w - 0.6, 2.8), gl)
            sx = face - 0.25 if side < 0 else face
            b.box((sx, y + 0.3, 3.0), (sx + 0.25, y + w - 0.5, 3.8), cols[n % len(cols)])
            y += w
            n += 1
    # the arcade roof: frames every 6 m, a glazed vault (two sloping planes + a crown) over the walkway
    for k in range(int(2 * hy / 6) + 1):
        y = -hy + k * 6.0
        b.beam((-3.2, y, 0.0), (-3.2, y, 6.0), 0.25, "MI_Steel")
        b.beam((3.2, y, 0.0), (3.2, y, 6.0), 0.25, "MI_Steel")
        b.beam((-3.2, y, 6.0), (0.0, y, 8.0), 0.25, "MI_Steel")
        b.beam((3.2, y, 6.0), (0.0, y, 8.0), 0.25, "MI_Steel")
    b.convex([(-3.4, -hy, 6.0), (-3.4, hy, 6.0), (0.0, -hy, 8.0), (0.0, hy, 8.0),
              (-3.4, -hy, 6.1), (-3.4, hy, 6.1), (0.0, -hy, 8.1), (0.0, hy, 8.1)], "MI_GlassClear")
    b.convex([(3.4, -hy, 6.0), (3.4, hy, 6.0), (0.0, -hy, 8.0), (0.0, hy, 8.0),
              (3.4, -hy, 6.1), (3.4, hy, 6.1), (0.0, -hy, 8.1), (0.0, hy, 8.1)], "MI_GlassClear")
    b.box((-4.5, -hy - 0.4, 0.0), (-3.6, -hy + 0.4, 9.5), "MI_PaintedMetal")       # the gate at the street
    b.box((3.6, -hy - 0.4, 0.0), (4.5, -hy + 0.4, 9.5), "MI_PaintedMetal")
    b.box((-4.5, -hy - 0.5, 8.2), (4.5, -hy + 0.5, 9.8), "MI_SignRed")             # its name board
    return "Shotengai", "civic", b.mesh()


_note("Shotengai", "Placeholder アーケード商店街, 24 x 110 plot running back from the street (-Y): the 6 m walkway "
      "under a glazed arcade roof, shop fronts both sides, the gate + name board at the street end, open at the back. "
      "The game assumes: the walkway is walkable end to end (the collider is the mesh); 2-3 shops get interiors later.")


# ── 団地: the public housing estate ───────────────────────────────────────────────────────────────────────────
def danchi(material, Builder):
    """公団の団地 on a 130 x 110 plot: four 5-storey slabs (60 x 10 m, 2.8 m storeys, open-gallery corridors on the
    north face, balconies with laundry rails on the south), each with its block number painted on the gable, a
    playground and a bicycle shed between them, a car park at the street."""
    b = Builder("Danchi", material)
    hx, hy = 65.0, 55.0
    ground(b, -hx, hx, -hy, hy, "MI_Grass")
    _parking(b, -hx, hx, -hy, -hy + 14.0)
    slabs = ((-35.0, -28.0), (35.0, -28.0), (-35.0, 12.0), (35.0, 12.0))
    for i, (cx, cy) in enumerate(slabs):
        x0, x1, y0, y1 = cx - 28.0, cx + 28.0, cy, cy + 10.0
        top = punched_block(b, x0, x1, y0, y1, 0.0, 5, 2.8, wall="MI_PaintWhite", bay=3.5, win=1.8, sides="fb",
                            balcony="MI_ConcreteSmooth")
        roof(b, x0, x1, y0, y1, top, parapet=0.8, units=0)
        for k in range(1, 5):                                                     # the open galleries (north)
            b.box((x0 + 1.0, y1, k * 2.8 - 0.1), (x1 - 1.0, y1 + 1.4, k * 2.8 + 0.1), "MI_ConcreteSmooth")
            b.box((x0 + 1.0, y1 + 1.3, k * 2.8 + 0.1), (x1 - 1.0, y1 + 1.4, k * 2.8 + 1.1), "MI_ConcreteSmooth")
        for sx in (x0 + 18.0, x1 - 18.0):                                         # stair cores
            b.box((sx - 1.5, y1, 0.0), (sx + 1.5, y1 + 3.0, top + 2.5), "MI_ConcreteSmooth")
        b.box((x1, cy + 2.0, top - 4.0), (x1 + 0.05, cy + 8.0, top - 1.0), "MI_SignGreen")   # the block number
    b.box((-12.0, -6.0, 0.0), (12.0, 8.0, 0.04), "MI_Dirt")                         # the playground
    b.wedge_x(-8.0, -3.0, 2.0, 3.0, 2.2, 0.3, "MI_PaintYellow")
    b.box((4.0, -4.0, 0.0), (10.0, -3.6, 2.4), "MI_PaintedMetal")
    b.box((-12.0, 32.0, 0.0), (12.0, 38.0, 2.4), "MI_PaintedMetal")                 # the bicycle shed
    b.box((-12.0, 32.0, 2.4), (12.0, 38.0, 2.6), "MI_Corrugated")
    fence(b, -hx + 0.5, hx - 0.5, -hy + 0.5, hy - 0.5, h=1.2, gaps=[("f", -20.0, 8.0), ("f", 20.0, 8.0)])
    return "Danchi", "civic", b.mesh()


_note("Danchi", "Placeholder 団地, 130 x 110 plot, the street at -Y: four 5-storey slabs (stair cores and open "
      "galleries on +Y, balconies on -Y), a playground and bicycle shed between, a car park at the street. Shut for "
      "now; the stairwells are the planned enterable part (stakeouts, a rooftop chase).")


# ── hotels ─────────────────────────────────────────────────────────────────────────────────────────────────────
def hotel_business(material, Builder):
    """ビジネスホテル on a 22 x 20 plot: a 20 x 14 m, 11-storey slab (a 4.5 m lobby + 10 x 3.0), small punched
    windows, the vertical name sign, a glazed lobby with a canopy. (A capsule hotel is the same block re-dressed.)"""
    b = Builder("HotelBusiness", material)
    x0, x1, y0, y1 = -10.0, 10.0, -8.0, 6.0
    b.box((x0, y0, 0.0), (x1, y1, 4.5), "MI_TileBrown")
    b.box((-6.0, y0 - 0.04, 0.2), (6.0, y0, 3.8), "MI_GlassClear")
    top = punched_block(b, x0, x1, y0, y1, 4.5, 10, 3.0, wall="MI_TileBeige", bay=2.6, win=1.1, sides="fblr")
    roof(b, x0, x1, y0, y1, top, units=3)
    canopy(b, -4.0, 4.0, y0 - 2.5, y0, 3.4)
    b.box((x1 - 0.2, y0 - 1.2, 6.0), (x1, y0 - 0.2, top - 2.0), "MI_SignCyan")
    return "HotelBusiness", "civic", b.mesh()


_note("HotelBusiness", "Placeholder ビジネスホテル (and, re-dressed, the capsule hotel), 22 x 20 plot, the street at -Y: "
      "11 storeys. Shut for now; the planned interior is one room floor (an assassination from the room opposite).")


def hotel_love(material, Builder):
    """ラブホテル on a 22 x 24 plot: a 6-storey block with a mock-castle turret and battlements, pink and purple
    neon, NO street windows, the price board, and the screened drive-in garage entrance (vinyl strip curtain) at the
    side -- the anonymous arrival is the type."""
    b = Builder("HotelLove", material)
    x0, x1, y0, y1 = -9.0, 9.0, -10.0, 10.0
    b.box((x0, y0, 0.0), (x1, y1, 19.0), "MI_Plaster")
    for k in range(6):
        b.box((x0 - 0.05, y0 - 0.05, 3.0 + k * 3.0), (x1 + 0.05, y1 + 0.05, 3.15 + k * 3.0), "MI_SignPink")
    b.box((x1 - 6.0, y0 - 0.05, 0.0), (x1 - 1.0, y0, 2.6), "MI_FabricRed")          # the garage curtain
    b.box((x0 + 1.0, y0 - 0.05, 0.0), (x0 + 3.0, y0, 2.3), "MI_PlasticDark")        # the hidden door
    b.box((x0 + 3.5, y0 - 0.15, 1.0), (x0 + 6.5, y0, 2.6), "MI_SignYellow")         # the price board
    b.frustum(x0 + 3.0, y0 + 3.0, 19.0, 26.0, 2.6, 2.6, 2.2, 2.2, "MI_Plaster")     # the turret
    b.frustum(x0 + 3.0, y0 + 3.0, 26.0, 29.0, 3.0, 3.0, 0.2, 0.2, "MI_SignPink")
    for i in range(7):                                                           # battlements
        x = x0 + 0.5 + i * 2.6
        b.box((x, y0, 19.0), (x + 1.3, y0 + 0.6, 20.2), "MI_Plaster")
    b.box((x1 - 0.3, y0 + 2.0, 8.0), (x1, y0 + 8.0, 16.0), "MI_SignPink")
    return "HotelLove", "civic", b.mesh()


_note("HotelLove", "Placeholder ラブホテル, 22 x 24 plot, the street at -Y: no street windows, a screened garage at "
      "the front-right, the walk-in door front-left. Shut for now. Nothing explicit, ever.")


# ── the construction site ──────────────────────────────────────────────────────────────────────────────────────
def construction_site(material, Builder):
    """工事現場 on a 40 x 40 plot: the 仮囲い hoarding (3 m white panels, a sliding gate), a steel frame half up (6
    storeys of columns and beams on a 24 x 18 grid, the top two bare), scaffold with mesh sheeting on the street
    face, a 45 m tower crane with its jib over the site, site-office cabins stacked two high."""
    b = Builder("ConstructionSite", material)
    hx = 20.0
    ground(b, -hx, hx, -hx, hx, "MI_Dirt")
    for (a0, b0, a1, b1) in ((-hx, hx - 0.15, hx, hx), (-hx, -hx, -hx + 0.15, hx), (hx - 0.15, -hx, hx, hx),
                             (-hx, -hx, -4.0, -hx + 0.15), (4.0, -hx, hx, -hx + 0.15)):
        b.box((a0, b0, 0.0), (a1, b1, 3.0), "MI_PaintWhite")
    b.box((-4.0, -hx - 0.2, 0.0), (4.0, -hx - 0.05, 2.8), "MI_PaintedMetal")        # the gate
    for i in range(5):
        for j in range(4):
            x, y = -12.0 + i * 6.0, -8.0 + j * 6.0
            b.box((x - 0.25, y - 0.25, 0.0), (x + 0.25, y + 0.25, 24.0), "MI_CraneRed")
    for k in range(1, 7):
        z = k * 4.0
        for j in range(4):
            y = -8.0 + j * 6.0
            b.box((-12.0, y - 0.2, z - 0.5), (12.0, y + 0.2, z), "MI_CraneRed")
        for i in range(5):
            x = -12.0 + i * 6.0
            b.box((x - 0.2, -8.0, z - 0.5), (x + 0.2, 10.0, z), "MI_CraneRed")
        if k <= 4:
            b.box((-12.0, -8.0, z - 0.15), (12.0, 10.0, z), "MI_ConcreteSmooth")    # decks poured to 4
    b.box((-13.5, -10.0, 0.0), (13.5, -9.9, 20.0), "MI_Fabric")                      # sheeted scaffold
    b.box((14.0, 12.0, 0.0), (16.0, 14.0, 45.0), "MI_PaintYellow")                  # the tower crane
    b.box((-20.0, 12.4, 45.0), (30.0, 13.6, 46.4), "MI_PaintYellow")
    b.box((22.0, 11.0, 44.0), (28.0, 15.0, 46.0), "MI_ConcreteSmooth")              # counterweight
    b.beam((15.0, 13.0, 46.4), (15.0, 13.0, 52.0), 0.5, "MI_PaintYellow")
    for k in range(2):
        b.box((-18.0, 13.0, k * 2.7), (-12.0, 18.0, k * 2.7 + 2.6), "MI_PlasticWhite")  # site office
    return "ConstructionSite", "civic", b.mesh()


_note("ConstructionSite", "Placeholder 工事現場, 40 x 40 plot, the street at -Y: hoarding with an 8 m gate, a 6-storey "
      "steel frame (decks poured to the 4th), a 45 m tower crane at the back-right. The game assumes: the frame and "
      "decks are climbable / sniping positions (the collider is the mesh); reusable on several plots.")


# ── nightlife / akiba ──────────────────────────────────────────────────────────────────────────────────────────
def game_centre(material, Builder):
    """ゲームセンター on an 18 x 22 plot: a 4-storey box, the whole ground floor glazed (crane machines behind it), a
    bright sign band per floor, a vertical sign."""
    b = Builder("GameCentre", material)
    x0, x1, y0, y1 = -8.0, 8.0, -10.0, 10.0
    b.box((x0, y0, 0.0), (x1, y1, 16.0), "MI_TileWhite")
    b.box((x0 + 0.5, y0 - 0.05, 0.1), (x1 - 0.5, y0, 3.6), "MI_GlassClear")
    for k, m in enumerate(("MI_SignCyan", "MI_SignPink", "MI_SignYellow")):
        b.box((x0, y0 - 0.2, 4.5 + k * 4.0), (x1, y0, 7.5 + k * 4.0), m)
    b.box((x1 - 0.4, y0 - 1.4, 4.0), (x1 - 0.1, y0 - 0.1, 15.0), "MI_SignRed")
    roof(b, x0, x1, y0, y1, 16.0, units=3)
    return "GameCentre", "civic", b.mesh()


def karaoke(material, Builder):
    """カラオケボックス on a 14 x 20 plot: a 7-storey slim block, small windows (one per booth), the big vertical
    sign down the front corner, a glass entrance with a lit canopy."""
    b = Builder("Karaoke", material)
    x0, x1, y0, y1 = -6.0, 6.0, -9.0, 9.0
    b.box((x0, y0, 0.0), (x1, y1, 4.0), "MI_TileWhite")
    b.box((-4.0, y0 - 0.05, 0.2), (4.0, y0, 3.4), "MI_GlassClear")
    top = punched_block(b, x0, x1, y0, y1, 4.0, 6, 3.0, wall="MI_TileBeige", bay=2.4, win=0.9, sides="flr")
    roof(b, x0, x1, y0, y1, top, units=2)
    b.box((x0 + 0.1, y0 - 1.6, 4.5), (x0 + 0.5, y0 - 0.1, top - 1.0), "MI_SignPink")
    canopy(b, -4.0, 4.0, y0 - 2.0, y0, 3.2, "MI_SignYellow")
    return "Karaoke", "civic", b.mesh()


_note("GameCentre", "Placeholder ゲームセンター, 18 x 22 plot, the street at -Y: 4 storeys, a glazed ground floor. "
      "Shut for now; one enterable floor (crane machines, lockers) is planned.")
_note("Karaoke", "Placeholder カラオケボックス, 14 x 20 plot, the street at -Y: 7 storeys of booths. Shut for now; one "
      "enterable booth corridor is planned (a meet in a booth).")


# ── big leisure: the arena and the suburban mall ───────────────────────────────────────────────────────────────
def arena(material, Builder):
    """アリーナ on a 150 x 120 plot: a 110 x 80 hall, 22 m to the eaves, a shallow dome over it (to 32 m), a glazed
    concourse band, a raised entrance plaza (a 3 m deck reached by broad steps at the street), the name board."""
    b = Builder("Arena", material)
    hx, hy = 75.0, 60.0
    ground(b, -hx, hx, -hy, hy, "MI_Terrazzo")
    x0, x1, y0, y1 = -55.0, 55.0, -30.0, 50.0
    b.frustum(0.0, 10.0, 0.0, 22.0, 56.0, 41.0, 55.0, 40.0, "MI_PaintedMetal")
    b.box((x0 - 1.0, y0 - 1.05, 4.0), (x1 + 1.0, y0, 9.0), "MI_GlassClear")          # the concourse band
    b.frustum(0.0, 10.0, 22.0, 26.0, 57.0, 42.0, 45.0, 30.0, "MI_Steel")             # the dome, in two tiers
    b.frustum(0.0, 10.0, 26.0, 32.0, 45.0, 30.0, 20.0, 10.0, "MI_Steel")
    b.box((-40.0, -48.0, 0.0), (40.0, -31.0, 3.0), "MI_ConcreteSmooth")               # the entrance deck
    for k in range(12):                                                            # its steps at the street side
        b.box((-30.0, -48.0 - 0.4 * (k + 1), 0.0), (30.0, -48.0 - 0.4 * k, 3.0 - 0.25 * (k + 1)), "MI_ConcreteSmooth")
    b.box((-18.0, y0 - 1.3, 12.0), (18.0, y0 - 1.05, 16.0), "MI_SignCyan")
    return "Arena", "civic", b.mesh()


_note("Arena", "Placeholder アリーナ, 150 x 120 plot, the street at -Y: a 110 x 80 hall under a stepped dome, a 3 m "
      "entrance deck with steps down to the street. Shut for now; a crowd-event mission (a target in the stands) "
      "wants the bowl modelled inside.")


def suburban_mall(material, Builder):
    """郊外型ショッピングモール on a 160 x 130 plot: a 120 x 70 mall, three 5.5 m storeys, glazed entrances front and
    side, the CINEMA (シネコン) as the box on its roof (40 x 50, 12 m, the sign on its face), rooftop parking with
    the spiral ramp at the side, surface parking in front."""
    b = Builder("SuburbanMall", material)
    hx, hy = 80.0, 65.0
    _parking(b, -hx, hx, -hy, -hy + 40.0, rows=2)
    x0, x1, y0, y1 = -60.0, 60.0, -15.0, 55.0
    top = ribbon_block(b, x0, x1, y0, y1, 0.0, 3, 5.5, wall="MI_TileWhite", sides="flr", sill=2.5)
    for x in (-30.0, 30.0):
        b.box((x - 6.0, y0 - 0.05, 0.2), (x + 6.0, y0, 4.8), "MI_GlassClear")
        canopy(b, x - 7.0, x + 7.0, y0 - 4.0, y0, 4.6)
    b.box((x0 - 0.05, y0 + 25.0, 0.2), (x0, y0 + 37.0, 4.8), "MI_GlassClear")
    ground(b, x0 + 2.0, x0 + 70.0, y0 + 2.0, y1 - 2.0, "MI_AsphaltLot", z=top + 0.02)   # the roof car park
    b.box((x1 - 50.0, y1 - 52.0, top), (x1 - 2.0, y1 - 2.0, top + 12.0), "MI_PaintedMetalDark")   # the cinema
    b.box((x1 - 44.0, y1 - 52.05, top + 4.0), (x1 - 8.0, y1 - 52.0, top + 10.0), "MI_SignRed")
    b.box((-20.0, y0 - 0.25, top - 4.5), (20.0, y0, top - 1.0), "MI_SignYellow")         # the mall's name
    b.frustum(x1 + 9.0, y1 - 12.0, 0.0, top, 8.0, 8.0, 8.0, 8.0, "MI_ConcreteSmooth")  # the ramp drum
    return "SuburbanMall", "civic", b.mesh()


_note("SuburbanMall", "Placeholder 郊外型モール, 160 x 130 plot, the street at -Y: 3 storeys, the cinema box on the "
      "roof's +X +Y corner, a roof car park (west half) reached by the ramp drum at +X, surface parking in front. "
      "Shut for now; the cinema (a dark theatre with a projection booth) is the planned mission interior.")


# ── the island's one school: kindergarten to university on one campus ──────────────────────────────────────────
def campus(material, Builder):
    """学園 (幼稚園から高校まで一貫教育, user 2026-10-03: "one big building, with park land for baseball"; the
    Tamagawa / Seijo Gakuen shape; the university is its own urban campus, `university`) on a 260 x 220 plot, the
    street at -Y:
      * ONE main building, an L of linked wings along the back and the west side (6 storeys, 4.2 m): the kindergarten
        in the low west end (2 storeys, its own fenced garden), the elementary, junior high and high schools above and along, an
        auditorium/gym block joined at the east end of the back wing, the clock on the back wing's centre;
      * the 校庭 / athletics ground (a 300 m track) between the wings;
      * a baseball field in the east (home plate at the front-west corner of its square, 90 m lines, a backstop,
        dugouts, four light towers, a stand behind home);
      * a public park strip along the street front (grass, paths, benches), open to the street, the campus fence
        behind it with the 校門 gate."""
    b = Builder("Campus", material)
    hx, hy = 130.0, 110.0
    ground(b, -hx, hx, -hy, hy, "MI_Grass")
    # the park strip at the street (25 m deep), its paths, benches
    b.box((-hx, -hy, 0.0), (hx, -hy + 3.0, 0.05), "MI_ConcreteSmooth")
    b.box((-hx, -hy + 12.0, 0.0), (hx, -hy + 14.5, 0.05), "MI_ConcreteSmooth")
    for x in range(-110, 120, 22):
        b.box((x - 0.9, -hy + 9.0, 0.4), (x + 0.9, -hy + 9.5, 0.5), "MI_Wood")
        b.box((x - 0.8, -hy + 9.0, 0.0), (x - 0.6, -hy + 9.5, 0.4), "MI_PaintedMetal")
        b.box((x + 0.6, -hy + 9.0, 0.0), (x + 0.8, -hy + 9.5, 0.4), "MI_PaintedMetal")
    fy = -hy + 25.0                                                                 # the campus fence line
    fence(b, -hx + 1.0, hx - 1.0, fy, hy - 1.0, h=2.2, gaps=[("f", -60.0, 10.0)])
    for x in (-66.0, -54.0):
        b.box((x - 0.6, fy - 0.6, 0.0), (x + 0.6, fy + 0.6, 3.0), "MI_StoneWall")      # 校門
    # the main building: back wing (y 70..95), west wing (x -125..-100), the kindergarten at the west wing's front end
    top = ribbon_block(b, -125.0, 60.0, 70.0, 95.0, 0.0, 6, 4.2, wall="MI_TileBeige", sides="fb", ground="MI_GlassClear")
    roof(b, -125.0, 60.0, 70.0, 95.0, top, units=8)
    b.box((-35.0, 69.85, top - 4.0), (-29.0, 70.0, top - 0.8), "MI_PaintWhite")      # the clock
    b.box((-34.0, 69.8, top - 3.6), (-30.0, 69.85, top - 1.2), "MI_PlasticDark")
    topw = ribbon_block(b, -125.0, -100.0, -45.0, 70.0, 0.0, 5, 4.2, wall="MI_TileBeige", sides="lr")
    roof(b, -125.0, -100.0, -45.0, 70.0, topw, units=4)
    ribbon_block(b, -125.0, -100.0, -80.0, -45.0, 0.0, 2, 3.6, wall="MI_PaintYellow", sides="flr")   # 幼稚園
    roof(b, -125.0, -100.0, -80.0, -45.0, 7.2, units=0, stair=False)
    fence(b, -99.0, -80.0, -80.0, -50.0, h=1.2, gaps=[("f", -90.0, 3.0)])            # its garden
    b.box((-95.0, -70.0, 0.0), (-85.0, -60.0, 0.05), "MI_Limestone")                 # sandpit
    b.box((60.0, 60.0, 0.0), (110.0, 100.0, 14.0), "MI_Corrugated")                  # auditorium / gym
    b.frustum(85.0, 80.0, 14.0, 17.0, 26.0, 21.0, 26.0, 1.0, "MI_RoofCopper")
    # the athletics ground: x -95..0, y -75..62, a 300 m track's straights, white
    ground(b, -95.0, 0.0, -75.0, 62.0, "MI_Dirt", z=0.03)
    for x in (-80.0, -15.0):
        b.box((x - 0.06, -55.0, 0.03), (x + 0.06, 42.0, 0.04), "MI_PaintWhite")
    # the baseball field: home plate at (8, -78), lines along +X and +Y, 90 m
    hp = (8.0, -78.0)
    ground(b, hp[0], hp[0] + 120.0, hp[1], hp[1] + 130.0, "MI_Grass", z=0.03)
    b.convex([(hp[0], hp[1], 0.0), (hp[0] + 40.0, hp[1], 0.0), (hp[0], hp[1] + 40.0, 0.0),
              (hp[0] + 32.0, hp[1] + 32.0, 0.0), (hp[0], hp[1], 0.05), (hp[0] + 40.0, hp[1], 0.05),
              (hp[0], hp[1] + 40.0, 0.05), (hp[0] + 32.0, hp[1] + 32.0, 0.05)], "MI_Dirt")   # the infield
    for (dx, dy) in ((90.0, 0.0), (0.0, 90.0)):
        b.box((hp[0] + min(0, dx) - 0.05, hp[1] + min(0, dy) - 0.05, 0.05),
              (hp[0] + max(dx, 0.1), hp[1] + max(dy, 0.1), 0.06), "MI_PaintWhite")
    for k in range(9):                                                             # the outfield fence, an arc
        a0, a1 = math.pi / 2 * k / 9, math.pi / 2 * (k + 1) / 9
        p0 = (hp[0] + 95 * math.cos(a0), hp[1] + 95 * math.sin(a0))
        p1 = (hp[0] + 95 * math.cos(a1), hp[1] + 95 * math.sin(a1))
        b.beam((p0[0], p0[1], 1.0), (p1[0], p1[1], 1.0), 2.0, "MI_SignGreen")
    b.box((hp[0] - 8.0, hp[1] - 6.0, 0.0), (hp[0] - 7.8, hp[1] + 6.0, 8.0), "MI_Steel")   # backstop
    b.box((hp[0] - 6.0, hp[1] - 8.0, 0.0), (hp[0] + 6.0, hp[1] - 7.8, 8.0), "MI_Steel")
    b.box((hp[0] + 18.0, hp[1] - 6.0, 0.0), (hp[0] + 30.0, hp[1] - 3.0, 2.4), "MI_ConcreteSmooth")   # dugouts
    b.box((hp[0] - 6.0, hp[1] + 18.0, 0.0), (hp[0] - 3.0, hp[1] + 30.0, 2.4), "MI_ConcreteSmooth")
    for k in range(4):                                                             # the stand behind home
        b.box((hp[0] - 22.0 + k * 0.9, hp[1] - 24.0 + k * 0.9, 0.0), (hp[0] - 12.0, hp[1] - 12.0, 0.5 * (k + 1)),
              "MI_ConcreteSmooth")
    for (x, y) in ((hp[0] - 5.0, hp[1] + 60.0), (hp[0] + 60.0, hp[1] - 5.0), (hp[0] + 90.0, hp[1] + 70.0),
                   (hp[0] + 70.0, hp[1] + 90.0)):
        b.box((x - 0.5, y - 0.5, 0.0), (x + 0.5, y + 0.5, 25.0), "MI_Steel")      # light towers
        b.box((x - 2.5, y - 0.4, 25.0), (x + 2.5, y + 0.4, 28.0), "MI_Light")
    return "Campus", "civic", b.mesh()


_note("Campus", "Placeholder 学園 (kindergarten to high school on one campus), 260 x 220 plot, the street at -Y: the park "
      "strip open to the street (25 m), the fence + 校門 at x -60; ONE main building (an L along the back and the "
      "west side, the yellow kindergarten at its front end with its own garden), the gym/auditorium at the back-east, "
      "the athletics ground in the middle, the baseball field in the east (home plate at the front-west corner). "
      "Shut for now; the main building's interior is a later mission piece.")


# ── the broadcast centre (replaces the Tokyo Tower model: user 2026-10-03, no copyright / trademark exposure) ──────
def broadcast_centre(material, Builder):
    """海都放送センター (Kaito Broadcasting Centre), an ORIGINAL design on the old tower's ~100 m site: a 90 x 60
    studio podium (3 tall storeys, 18 m) with a glazed atrium at the front, a 34 x 26 office tower rising 120 m from
    its back half, a rooftop helipad, a 60 m steel transmission mast with red/white aviation bands on the tower, and a
    row of satellite dishes on the podium roof -- the skyline marker the tower used to be, ~185 m to the mast tip."""
    b = Builder("BroadcastCentre", material)
    x0, x1, y0, y1 = -45.0, 45.0, -30.0, 30.0
    ground(b, -50.0, 50.0, -48.0, 48.0, "MI_Terrazzo")
    pod = ribbon_block(b, x0, x1, y0, y1, 0.0, 3, 6.0, wall="MI_PaintedMetal", sides="fblr", sill=2.0)
    b.box((-20.0, y0 - 6.0, 0.0), (20.0, y0, pod - 2.0), "MI_GlassClear")              # the atrium
    b.box((-20.5, y0 - 6.5, pod - 2.0), (20.5, y0 + 0.5, pod - 1.2), "MI_PaintedMetal")
    b.box((-14.0, y0 - 6.3, pod - 5.0), (14.0, y0 - 6.0, pod - 3.0), "MI_SignCyan")     # the station's mark
    roof(b, x0, x1, y0, y1, pod, units=6, stair=False)
    for i in range(5):                                                              # dishes
        cx = x0 + 8.0 + i * 7.0
        b.box((cx - 0.4, y0 + 6.0, pod), (cx + 0.4, y0 + 6.8, pod + 2.5), "MI_Steel")
        b.frustum(cx, y0 + 5.4, pod + 2.0, pod + 2.6, 2.4, 0.2, 2.6, 0.3, "MI_PlasticWhite")
    tx0, tx1, ty0, ty1 = -17.0, 17.0, 2.0, 28.0
    top = ribbon_block(b, tx0, tx1, ty0, ty1, pod, 25, 4.08, wall="MI_TileWhite", sides="fblr", sill=0.6)
    b.box((tx0 - 0.4, ty0 - 0.4, top), (tx1 + 0.4, ty1 + 0.4, top + 1.2), "MI_PaintedMetal")
    b.box((-12.0, ty0 + 1.0, top + 1.2), (12.0, ty1 - 1.0, top + 1.4), "MI_ConcreteSmooth")   # the helipad deck
    b.box((-1.5, (ty0 + ty1) / 2 - 5.0, top + 1.4), (1.5, (ty0 + ty1) / 2 + 5.0, top + 1.45), "MI_PaintWhite")
    mx, my = tx1 - 4.0, ty1 - 4.0                                                   # the mast at the back corner
    for k in range(6):
        z0, z1 = top + 1.4 + k * 10.0, top + 1.4 + (k + 1) * 10.0
        h0, h1 = 2.0 - k * 0.28, 2.0 - (k + 1) * 0.28
        b.frustum(mx, my, z0, z1, h0, h0, h1, h1, "MI_AviationOrange" if k % 2 == 0 else "MI_PaintWhite")
    return "BroadcastCentre", "structure", b.mesh()


_note("BroadcastCentre", "Placeholder 海都放送センター (an original broadcast centre that REPLACES the old Tokyo Tower "
      "model): 90 x 60 podium (18 m), a 34 x 26 tower to 120 m on its back half, a helipad and a 60 m banded mast. "
      "The game assumes: a landmark seen from across the city (it streams at 3 km), the collider is the mesh, the "
      "front (-Y) faces the street; the helipad is the planned rooftop mission set piece.")


def university(material, Builder):
    """大学 (an URBAN campus, the Waseda / Keio Mita shape) on a 110 x 100 plot, the street at -Y: two linked
    buildings round a quad -- a 9-storey teaching tower (40 x 20) on the west, a 5-storey block on the east whose
    ground floor is the LIBRARY (glazed full height, 図書館), a glass bridge between them at the 3rd floor, the quad
    paved with trees' places, a stone 正門 gate with the name plaque at the street."""
    b = Builder("University", material)
    hx, hy = 55.0, 50.0
    ground(b, -hx, hx, -hy, hy, "MI_Terrazzo")
    top = ribbon_block(b, -50.0, -10.0, -20.0, 0.0, 0.0, 9, 4.0, wall="MI_BrickRed", sides="fblr")
    roof(b, -50.0, -10.0, -20.0, 0.0, top, units=6)
    b.box((10.0, -10.0, 0.0), (50.0, 40.0, 7.0), "MI_BrickRed")                      # the library's hall
    b.box((9.95, -9.0, 0.3), (10.0, 39.0, 6.6), "MI_GlassClear")
    top2 = ribbon_block(b, 10.0, 50.0, -10.0, 40.0, 7.0, 4, 4.0, wall="MI_BrickRed", sides="flr")
    roof(b, 10.0, 50.0, -10.0, 40.0, top2, units=4)
    b.box((-10.0, -14.0, 9.0), (10.0, -6.0, 12.5), "MI_GlassClear")                  # the bridge
    b.box((-12.0, 20.0, 0.0), (8.0, 45.0, 14.0), "MI_TileBeige")                     # the lecture hall at the back
    for x in (-6.0, 6.0):
        b.box((x - 1.0, -hy, 0.0), (x + 1.0, -hy + 1.5, 4.0), "MI_StoneWall")        # 正門
    b.box((-5.0, -hy - 0.1, 2.6), (5.0, -hy, 3.4), "MI_Gold")
    fence(b, -hx + 0.5, hx - 0.5, -hy + 0.5, hy - 0.5, h=1.6, gaps=[("f", 0.0, 10.0)])
    return "University", "civic", b.mesh()


_note("University", "Placeholder 大学 urban campus, 110 x 100 plot, the street at -Y: a 9-storey teaching tower (west), "
      "the LIBRARY + 5-storey block (east, the library its glazed ground floor), a glass bridge, a lecture hall at the "
      "back, the 正門 at the street. Shut for now.")


def public_library(material, Builder):
    """区立図書館 on a 40 x 36 plot: a 3-storey 34 x 24 block, a full-height glazed reading room on the street front,
    a book-return box by the door, bicycle racks."""
    b = Builder("PublicLibrary", material)
    x0, x1, y0, y1 = -17.0, 17.0, -10.0, 14.0
    top = ribbon_block(b, x0, x1, y0, y1, 0.0, 3, 4.5, wall="MI_TileBrown", sides="blr")
    b.box((x0 + 1.0, y0 - 0.05, 0.2), (x1 - 1.0, y0, top - 1.0), "MI_GlassClear")
    roof(b, x0, x1, y0, y1, top, units=3)
    sign(b, -6.0, 6.0, y0, top - 0.9, top - 0.2, "MI_Sign")
    b.box((7.0, y0 - 2.0, 0.0), (8.0, y0 - 1.2, 1.2), "MI_PostRed")                  # the book return
    for i in range(6):
        b.box((x0 + 2.0 + i * 1.0, y0 - 5.0, 0.0), (x0 + 2.05 + i * 1.0, y0 - 3.5, 0.9), "MI_Steel")
    ground(b, -20.0, 20.0, -18.0, y0, "MI_ConcreteSmooth")
    return "PublicLibrary", "civic", b.mesh()


_note("PublicLibrary", "Placeholder 区立図書館, 40 x 36 plot, the street at -Y: 3 storeys, a glazed reading room on the "
      "front. Placed beside the Civic Centre. Shut for now (a quiet-meeting / dead-drop interior is planned).")


# ── the roadside (沿道) and the neighbourhood: the second review's types (2026-10-03) ─────────────────────────────
def repair_shop(material, Builder):
    """整備工場 / 車検 on a 30 x 30 plot: a 2-bay workshop (18 x 14, 6 m, two roll-up doors, a lift inside each bay),
    a small office with the 車検 sign, a forecourt with three cars waiting. In the game this is the garage that
    repairs, resprays and clears the wanted level (the Pay'n'Spray role)."""
    b = Builder("RepairShop", material)
    ground(b, -15.0, 15.0, -15.0, 15.0, "MI_ConcreteSmooth")
    x0, x1, y0, y1 = -13.0, 5.0, 0.0, 14.0
    b.box((x0, y0, 0.0), (x1, y1, 6.0), "MI_Corrugated")
    b.frustum((x0 + x1) / 2, (y0 + y1) / 2, 6.0, 7.2, 9.5, 7.5, 9.5, 0.5, "MI_PaintedMetal")
    for xa in (x0 + 1.0, x0 + 9.5):                                             # the two bays (open)
        b.box((xa, y0 - 0.05, 4.2), (xa + 7.5, y0, 6.0), "MI_Corrugated")
        b.box((xa + 2.0, y0 + 2.0, 0.0), (xa + 5.5, y0 + 2.4, 0.3), "MI_PaintYellow")   # the lift's arms
        b.box((xa + 2.0, y0 + 8.0, 0.0), (xa + 5.5, y0 + 8.4, 0.3), "MI_PaintYellow")
    b.box((x0, y0 + 13.8, 0.0), (x1, y1, 6.0), "MI_Corrugated")
    b.box((7.0, 2.0, 0.0), (14.0, 10.0, 3.2), "MI_TileWhite")                     # the office
    b.box((7.5, 1.95, 0.4), (13.5, 2.0, 2.6), "MI_GlassClear")
    b.box((x0, y0 - 0.25, 6.2), (x1, y0 - 0.05, 7.4), "MI_SignCyan")               # 車検 / 整備 sign
    _cars(b, ((-8.0, -9.0, False), (-2.0, -9.0, False), (6.0, -9.0, False)), "MI_PlasticWhite")
    return "RepairShop", "civic", b.mesh()


_note("RepairShop", "Placeholder 整備工場 / 車検, 30 x 30 plot, the street at -Y: two OPEN workshop bays (4.2 m "
      "clear, a car drives in), an office at +X, a forecourt. The game assumes: a car driven into a bay is the "
      "repair / respray / wanted-clear trigger (later, WantedSystem); keep the bays open and 4 m+ high.")


def car_dealer(material, Builder):
    """ディーラー (a car dealer) on a 40 x 36 plot: a glazed showroom (24 x 16, 6 m, three cars inside), the brand-
    neutral sign pylon, an outdoor display lot with bunting, a service bay behind."""
    b = Builder("CarDealer", material)
    ground(b, -20.0, 20.0, -18.0, 18.0, "MI_AsphaltLot")
    x0, x1, y0, y1 = -12.0, 12.0, -2.0, 14.0
    b.box((x0, y0, 0.0), (x1, y1, 0.15), "MI_Terrazzo")
    b.box((x0, y0, 0.15), (x1, y0 + 0.05, 5.6), "MI_GlassClear")
    b.box((x0, y0, 0.15), (x0 + 0.05, y1, 5.6), "MI_GlassClear")
    b.box((x1 - 0.05, y0, 0.15), (x1, y1, 5.6), "MI_GlassClear")
    b.box((x0, y1 - 0.3, 0.0), (x1, y1, 6.0), "MI_PaintWhite")
    b.box((x0 - 0.5, y0 - 0.5, 5.6), (x1 + 0.5, y1 + 0.5, 6.4), "MI_PaintWhite")
    _cars(b, ((-7.0, 6.0, True), (0.0, 6.0, True), (7.0, 6.0, True)), "MI_CraneRed")
    _cars(b, [(-16.0 + 4.0 * i, -12.0, False) for i in range(9)], "MI_PaintWhite")
    b.box((16.0, -16.0, 0.0), (17.0, -15.0, 9.0), "MI_Steel")                       # the pylon
    b.box((15.0, -16.2, 6.0), (18.0, -14.8, 9.0), "MI_SignCyan")
    b.box((x0, 14.0, 0.0), (x1, 18.0, 5.0), "MI_Corrugated")                        # service bay
    return "CarDealer", "civic", b.mesh()


_note("CarDealer", "Placeholder ディーラー, 40 x 36 plot, the street at -Y: a glazed showroom with three cars, a "
      "display lot at the street, a sign pylon (brand-neutral, keep it so), a service bay behind. Placed on arterials "
      "by the district mixes; the cars are mesh, not vehicles. Shut for now; one frozen 'import dealer' with an "
      "interior is the planned heist location.")


def home_centre(material, Builder):
    """ホームセンター + カー用品店 on a 120 x 90 plot: the big-box home centre (60 x 40, 9 m, a garden centre under a
    canopy at its side), the auto-parts shop (30 x 24, a pit / tyre-fitting bay), one car park in front of both."""
    b = Builder("HomeCentre", material)
    hx, hy = 60.0, 45.0
    _parking(b, -hx, hx, -hy, -hy + 32.0, rows=2)
    b.box((-58.0, -8.0, 0.0), (2.0, 32.0, 9.0), "MI_Corrugated")
    b.box((-40.0, -8.05, 0.2), (-20.0, -8.0, 4.0), "MI_GlassClear")
    b.box((-56.0, -8.25, 6.0), (0.0, -8.05, 8.6), "MI_SignYellow")
    b.box((2.0, 0.0, 0.0), (18.0, 30.0, 0.05), "MI_ConcreteSmooth")                  # the garden centre
    b.box((2.0, 0.0, 5.0), (18.0, 30.0, 5.3), "MI_GlassClear")
    b.box((26.0, -2.0, 0.0), (56.0, 22.0, 7.0), "MI_TileWhite")                      # the auto-parts shop
    b.box((28.0, -2.05, 0.2), (40.0, -2.0, 4.0), "MI_GlassClear")
    b.box((44.0, -2.05, 0.0), (54.0, -2.0, 4.5), "MI_Corrugated")                     # the pit bay (open)
    b.box((26.0, -2.25, 4.8), (56.0, -2.05, 6.6), "MI_SignRed")
    return "HomeCentre", "civic", b.mesh()


_note("HomeCentre", "Placeholder ホームセンター + カー用品店 roadside pair, 120 x 90 plot, the street at -Y: the big box "
      "(west), garden centre, the auto-parts shop with an open pit bay (east), one car park in front. Shut for now; "
      "their counters (ShopCounter) are planned supply / mod shops.")


def shrine_small(material, Builder):
    """町の小さな神社 (a neighbourhood shrine) on a 12 x 16 lot: a red 鳥居 at the street, a stone path, a small
    祠 / 拝殿 (3 x 3) under a copper roof, a stone fence, a pair of 狛犬 and one tree's place."""
    b = Builder("ShrineSmall", material)
    ground(b, -6.0, 6.0, -8.0, 8.0, "MI_Dirt")
    b.box((-0.8, -8.0, 0.0), (0.8, 4.0, 0.06), "MI_StoneWall")
    for x in (-1.8, 1.8):
        b.box((x - 0.18, -7.0, 0.0), (x + 0.18, -6.64, 3.4), "MI_LacquerRed")
    b.box((-2.6, -7.1, 3.4), (2.6, -6.54, 3.7), "MI_LacquerRed")                    # 笠木
    b.box((-2.2, -6.95, 2.8), (2.2, -6.69, 3.0), "MI_LacquerRed")                   # 貫
    b.box((-1.5, 4.0, 0.0), (1.5, 7.0, 0.5), "MI_StoneWall")
    b.box((-1.2, 4.3, 0.5), (1.2, 6.7, 2.6), "MI_Hinoki")
    hip(b, 0.0, 5.5, 2.6, 1.3, 1.3, 1.4, "MI_RoofCopper", eave=0.6)
    for x in (-1.6, 1.6):
        b.box((x - 0.3, 1.5, 0.0), (x + 0.3, 2.1, 1.0), "MI_StoneWall")              # 狛犬
    for (a0, b0, a1, b1) in ((-6.0, -8.0, -5.8, 8.0), (5.8, -8.0, 6.0, 8.0), (-6.0, 7.8, 6.0, 8.0)):
        b.box((a0, b0, 0.0), (a1, b1, 0.9), "MI_StoneWall")
    return "ShrineSmall", "civic", b.mesh()


_note("ShrineSmall", "Placeholder neighbourhood 神社, 12 x 16, the street at -Y: 鳥居 at the street, a 祠 at the back. "
      "Placed by the district mixes (Japan has more shrines than konbini).")


def temple_cemetery(material, Builder):
    """寺と墓地 on a 70 x 60 plot: the 本堂 (20 x 16) under a big tiled hip roof at the back-west, a 山門 gate at
    the street, a bell house, and the 墓地 east -- rows of grave stones on stepped plinths with narrow paths."""
    b = Builder("TempleCemetery", material)
    hx, hy = 35.0, 30.0
    ground(b, -hx, hx, -hy, hy, "MI_Dirt")
    b.box((-30.0, 6.0, 0.0), (-10.0, 22.0, 6.5), "MI_Wood")
    hip(b, -20.0, 14.0, 6.5, 10.0, 8.0, 6.0, "MI_RoofSlate", eave=2.0)
    b.box((-24.0, -hy, 0.0), (-16.0, -hy + 5.0, 5.0), "MI_Wood")                     # 山門
    b.box((-22.0, -hy - 0.1, 0.0), (-18.0, -hy + 5.1, 3.4), "MI_PlasticDark")
    hip(b, -20.0, -hy + 2.5, 5.0, 4.0, 2.5, 2.0, "MI_RoofSlate", eave=1.0)
    b.box((-8.0, -6.0, 0.0), (-4.0, -2.0, 4.5), "MI_Wood")                            # 鐘楼
    hip(b, -6.0, -4.0, 4.5, 2.0, 2.0, 1.6, "MI_RoofSlate", eave=0.8)
    b.box((-20.5, -hy + 5.0, 0.0), (-19.5, 6.0, 0.06), "MI_StoneWall")
    for i in range(6):                                                           # 墓地: graves in rows
        y = -22.0 + i * 8.0
        b.box((2.0, y - 0.3, 0.0), (32.0, y + 0.3, 0.05), "MI_StoneWall")
        for k in range(9):
            x = 4.0 + k * 3.2
            b.box((x - 1.0, y + 0.6, 0.0), (x + 1.0, y + 2.4, 0.35), "MI_StoneWall")
            b.box((x - 0.35, y + 1.2, 0.35), (x + 0.35, y + 1.7, 1.6), "MI_Limestone")
    fence(b, -hx + 0.5, hx - 0.5, -hy + 0.5, hy - 0.5, h=1.6, gaps=[("f", -20.0, 8.0)], mat="MI_StoneWall")
    return "TempleCemetery", "civic", b.mesh()


_note("TempleCemetery", "Placeholder 寺と墓地, 70 x 60 plot, the street at -Y: 本堂 back-west, 山門 at the street, a "
      "鐘楼, the cemetery east (6 rows of graves). Night meetings and chases; the graves are cover (mesh collider).")


def factory_small(material, Builder):
    """町工場 (a small works) 12 x 18 m: a shuttered workshop floor (5 m, two roll-up doors, one half open), the
    family's flat above (one storey, a balcony), a vent stack, a yard strip at the side."""
    b = Builder("FactorySmall", material)
    x0, x1, y0, y1 = -6.0, 6.0, -9.0, 9.0
    b.box((x0, y0, 0.0), (x1, y1, 5.0), "MI_Corrugated")
    b.box((x0 + 0.5, y0 - 0.06, 0.0), (-0.3, y0, 4.2), "MI_PaintedMetal")
    b.box((0.3, y0 - 0.06, 2.4), (x1 - 0.5, y0, 4.2), "MI_PaintedMetal")               # half open
    top = punched_block(b, x0, x1, y0, y1, 5.0, 1, 2.9, wall="MI_TileBeige", bay=3.0, win=1.6, sides="f",
                        balcony="MI_PaintedMetal")
    roof(b, x0, x1, y0, y1, top, parapet=0.8, units=1, stair=False)
    b.beam((x1 - 1.0, y1 - 1.0, 0.0), (x1 - 1.0, y1 - 1.0, top + 3.0), 0.5, "MI_Steel")
    b.box((x0 + 0.3, y0 - 0.2, 4.3), (x0 + 5.0, y0 - 0.06, 4.9), "MI_Sign")
    return "FactorySmall", "civic", b.mesh()


_note("FactorySmall", "Placeholder 町工場, 12 x 18 m, the street at -Y: a shuttered works with a flat above. Placed by "
      "the industry / 準工業 mixes (replaces the shop-house stand-in there).")


def house_traditional(material, Builder):
    """古い日本家屋 (an older, larger family house -- the grandparents' generation) on its own 18 x 20 lot: a
    single-storey 14 x 10 m house under a big grey 瓦 hip roof (deep eaves), a 縁側 veranda along the garden side, a
    block 塀 wall round the lot with a roofed 門 gate at the street, a garden with stepping stones and a small 蔵
    (storehouse) in the back corner."""
    b = Builder("HouseTraditional", material)
    hx, hy = 9.0, 10.0
    ground(b, -hx, hx, -hy, hy, "MI_Dirt")
    for (a0, b0, a1, b1) in ((-hx, hy - 0.2, hx, hy), (-hx, -hy, -hx + 0.2, hy), (hx - 0.2, -hy, hx, hy),
                             (-hx, -hy, -1.6, -hy + 0.2), (1.6, -hy, hx, -hy + 0.2)):
        b.box((a0, b0, 0.0), (a1, b1, 1.8), "MI_Plaster")
        b.box((a0 - 0.1, b0 - 0.1, 1.8), (a1 + 0.1, b1 + 0.1, 2.0), "MI_RoofSlate")
    for x in (-1.6, 1.4):                                                         # the 門
        b.box((x, -hy - 0.1, 0.0), (x + 0.2, -hy + 0.3, 2.6), "MI_Wood")
    hip(b, 0.0, -hy + 0.1, 2.6, 1.6, 0.6, 0.9, "MI_RoofSlate", eave=0.4)
    b.box((-1.0, -hy, 0.0), (1.0, -1.0, 0.04), "MI_StoneWall")                      # stepping stones (one strip)
    x0, x1, y0, y1 = -7.0, 7.0, -2.0, 8.0
    b.box((x0, y0, 0.0), (x1, y1, 0.5), "MI_StoneWall")                             # the raised floor's base
    b.box((x0, y0, 0.5), (x1, y1, 3.3), "MI_Wood")
    b.box((x0 + 0.5, y0 - 0.04, 0.9), (x1 - 0.5, y0, 2.9), "MI_Shoji")
    b.box((x0, y0 - 1.0, 0.45), (x1, y0, 0.55), "MI_Wood")                          # 縁側
    hip(b, 0.0, (y0 + y1) / 2, 3.3, 7.0, 5.0, 2.8, "MI_RoofSlate", eave=1.3)
    b.box((4.5, 5.0, 0.0), (8.5, 9.5, 4.2), "MI_Plaster")                           # 蔵
    hip(b, 6.5, 7.25, 4.2, 2.0, 2.25, 1.4, "MI_RoofSlate", eave=0.4)
    b.box((-8.0, -8.0, 0.0), (-4.0, -4.0, 0.02), "MI_Grass")
    return "HouseTraditional", "civic", b.mesh()


_note("HouseTraditional", "Placeholder 古い日本家屋 (an older, larger single-family house), 18 x 20 lot, the street at "
      "-Y: one storey under a deep 瓦 hip roof, a 縁側 to the garden, a 塀 wall with a roofed gate, a 蔵 at the back. "
      "Placed by the housing mixes beside the modern DetachedHouse(B); shut.")


# ── housing: the apartment ladder (user, 2026-10-03: "larger and smaller apartments, modern ones with one unit line
# horizontal or vertical over several floors, and the outdated 2-floor one-unit-line apartment that is cheaper") ──
# Measurements are the ordinary Japanese ones: a 1K unit of a wooden アパート is 2 ken (3.64 m) wide by 4 ken
# (7.28 m) deep (~26 m2, 6 畳 + kitchen + unit bath); a マンション unit is 6-7 m of frontage by 10-12 m deep
# (65-75 m2, 3LDK); storeys 2.8 m (wooden) and 3.0 m (RC); open-air corridors (外廊下) 1.2-1.5 m; balconies 1.5-1.8 m.

def _apato(name, units, material, Builder):
    """木造2階建てアパート (the cheap 1980s-90s wooden two-storey block, 1K units in ONE line): `units` x 3.64 m by
    7.28 m, 2 x 2.8 m storeys, the open corridor and the external steel stair on the street side (-Y), a door + a
    small window + an electric meter box per unit, sliding windows and narrow balconies (laundry rails) at the back, a
    low slate gable, the bicycle rack at the street."""
    b = Builder(name, material)
    w = units * 3.64
    x0, x1, y0, y1 = -w / 2, w / 2, -3.64 + 0.9, 3.64 + 0.9            # the block; the corridor in front of y0
    h = 2.8
    b.box((x0, y0, 0.0), (x1, y1, 0.4), "MI_ConcreteSmooth")                       # the 基礎
    b.box((x0, y0, 0.4), (x1, y1, 0.4 + 2 * h), "MI_Plaster")                      # siding
    for k in range(2):
        zb = 0.4 + k * h
        for i in range(units):
            cx = x0 + 3.64 * (i + 0.5)
            b.box((cx - 0.9, y0 - 0.03, zb + 0.05), (cx - 0.1, y0, zb + 2.05), "MI_PaintedMetal")    # the door
            b.box((cx + 0.3, y0 - 0.03, zb + 1.1), (cx + 1.2, y0, zb + 1.9), "MI_Window")
            b.box((cx + 1.3, y0 - 0.12, zb + 1.2), (cx + 1.6, y0, zb + 1.6), "MI_PlasticWhite")      # meter box
            b.box((cx - 1.4, y1, zb + 0.35), (cx + 1.4, y1 + 0.03, zb + 2.25), "MI_Window")          # back sash
            if k == 1:
                b.box((cx - 1.6, y1, zb - 0.1), (cx + 1.6, y1 + 0.9, zb + 0.05), "MI_PaintedMetal")  # balcony
                b.box((cx - 1.6, y1 + 0.85, zb + 0.05), (cx + 1.6, y1 + 0.9, zb + 1.0), "MI_PaintedMetal")
        if k == 1:                                                                  # the 2F open corridor
            b.box((x0, y0 - 1.2, zb - 0.15), (x1, y0, zb), "MI_PaintedMetal")
            b.box((x0, y0 - 1.2, zb), (x1, y0 - 1.15, zb + 1.05), "MI_PaintedMetal")
            for xx in (x0 + 0.1, x1 - 1.0):
                b.box((xx, y0 - 1.2, 0.0), (xx + 0.1, y0 - 1.1, zb), "MI_Steel")    # its posts
    # the external steel stair: off the +X end, rising along the front to the 2F corridor (16 x 0.2 m risers)
    zc = 0.4 + h
    for k in range(16):
        xh = x1 + 4.1 - k * 0.25
        b.box((xh - 0.25, y0 - 1.2, 0.0), (xh, y0 - 0.1, zc * (k + 1) / 16.0), "MI_Steel")
    b.box((x1, y0 - 1.2, zc - 0.15), (x1 + 0.1, y0, zc), "MI_Steel")
    gable(b, 0.0, (y0 + y1) / 2, 0.4 + 2 * h, w / 2 + 0.4, (y1 - y0) / 2 + 0.4, 1.3, "MI_RoofSlate")
    b.box((x0 + 0.5, y0 - 2.6, 0.0), (x0 + 3.5, y0 - 1.6, 1.0), "MI_PaintedMetal")  # the bicycle rack
    return name, "civic", b.mesh()


def _mansion_line(name, units, storeys, material, Builder):
    """片廊下型マンション (the modern mid-rise, units in ONE horizontal line): `units` x 6.5 m by 11 m (3LDK), `storeys`
    x 3.0 m over a 3.6 m ground floor (the entrance hall, the auto-lock lobby, the bicycle and refuse rooms), balconies
    with frosted glass panels on the street side (-Y), the open corridor + the lift / stair core at the back (+Y), the
    core rising past the parapet."""
    b = Builder(name, material)
    w = units * 6.5
    x0, x1, y0, y1 = -w / 2, w / 2, -5.5, 5.5
    b.box((x0, y0, 0.0), (x1, y1, 3.6), "MI_TileBrown")
    b.box((-3.0, y0 - 0.04, 0.2), (3.0, y0, 3.2), "MI_GlassClear")                      # the entrance hall
    canopy(b, -3.5, 3.5, y0 - 2.0, y0, 3.2, posts=False)
    top = ribbon_block(b, x0, x1, y0, y1, 3.6, storeys, h=3.0, wall="MI_TileBeige", sides="fb")
    for k in range(storeys):
        zb = 3.6 + k * 3.0
        b.box((x0 + 0.3, y0 - 1.8, zb - 0.15), (x1 - 0.3, y0, zb + 0.05), "MI_ConcreteSmooth")      # balcony slab
        b.box((x0 + 0.3, y0 - 1.8, zb + 0.05), (x1 - 0.3, y0 - 1.7, zb + 1.1), "MI_GlassClear")     # glass panel
        for i in range(1, units):                                                    # the partition boards
            xx = x0 + 6.5 * i
            b.box((xx - 0.05, y0 - 1.8, zb + 0.05), (xx + 0.05, y0, zb + 2.4), "MI_PlasticWhite")
        b.box((x0 + 0.3, y1, zb - 0.15), (x1 - 0.3, y1 + 1.4, zb + 0.05), "MI_ConcreteSmooth")     # back corridor
        b.box((x0 + 0.3, y1 + 1.3, zb + 0.05), (x1 - 0.3, y1 + 1.4, zb + 1.1), "MI_ConcreteSmooth")
    b.box((x1 - 6.0, y1 + 1.4, 0.0), (x1 - 1.0, y1 + 6.0, top + 3.0), "MI_ConcreteSmooth")         # lift + stair
    roof(b, x0, x1, y0, y1, top, parapet=1.0, units=max(1, units // 2), stair=False)
    return name, "civic", b.mesh()


def _mansion_tower(name, storeys, material, Builder):
    """1フロア1住戸のペンシルマンション (the modern narrow block, ONE unit per floor stacked vertically): 8 x 14 m,
    a 3.6 m ground floor (the entrance + a tenant shop or parking), `storeys` x 3.0 m flats with a full-width balcony
    to the street (-Y), a lift + stair core along the +X side, a mechanical car stacker beside the entrance."""
    b = Builder(name, material)
    x0, x1, y0, y1 = -4.0, 4.0, -7.0, 7.0
    b.box((x0, y0, 0.0), (x1, y1, 3.6), "MI_ConcreteSmooth")
    b.box((x0 + 0.5, y0 - 0.04, 0.2), (0.5, y0, 3.2), "MI_GlassClear")
    b.box((1.0, y0 - 0.04, 0.0), (x1 - 0.3, y0, 3.2), "MI_PaintedMetalDark")               # the car stacker door
    top = punched_block(b, x0, x1 - 2.4, y0, y1, 3.6, storeys, 3.0, wall="MI_TileWhite", bay=5.0, win=4.0,
                        sides="fb", balcony="MI_GlassClear")
    b.box((x1 - 2.4, y0 + 1.0, 3.6), (x1, y1, top + 3.0), "MI_TileBrown")                  # the core
    roof(b, x0, x1 - 2.4, y0, y1, top, parapet=0.9, units=1, stair=False)
    return name, "civic", b.mesh()


def _apart_rc(name, material, Builder):
    """RC / 重量鉄骨 3階建てアパート (the newer small block, cheaper than a マンション): 12 x 10 m, 2 units a floor
    (1LDK, ~50 m2), 3 x 3.0 m, an internal stair behind a glass-block slot at the centre front, balconies to the
    street (-Y), a flat roof."""
    b = Builder(name, material)
    x0, x1, y0, y1 = -6.0, 6.0, -5.0, 5.0
    top = punched_block(b, x0, x1, y0, y1, 0.0, 3, 3.0, wall="MI_PaintWhite", bay=6.0, win=3.0, sides="fbl",
                        balcony="MI_PaintedMetal")
    b.box((-0.9, y0 - 0.05, 0.0), (0.9, y0, top - 0.3), "MI_GlassClear")                   # the stair slot
    b.box((-0.9, y0 - 0.06, 0.0), (0.9, y0 - 0.02, 2.2), "MI_PaintedMetalDark")           # the entrance door
    roof(b, x0, x1, y0, y1, top, parapet=0.8, units=2, stair=False)
    return name, "civic", b.mesh()


def _tower_mansion(name, storeys, material, Builder):
    """タワーマンション (タワマン): a 36 x 36 m tower of `storeys` x 3.1 m over a 2-storey podium (48 x 44 m: the
    two-storey glazed entrance hall with a porte-cochere, the concierge lounge, the residents' facilities), deep
    wrap-around balconies with glass rails on every floor, the sky lounge glazing at the top, a helipad / H mark on the
    roof (a 100 m+ building has one), the multi-storey car park entrance at the +X side."""
    b = Builder(name, material)
    px0, px1, py0, py1 = -24.0, 24.0, -22.0, 22.0
    b.box((px0, py0, 0.0), (px1, py1, 8.0), "MI_StoneWall")
    b.box((-14.0, py0 - 0.05, 0.3), (14.0, py0, 7.2), "MI_GlassClear")                     # the double-height hall
    canopy(b, -10.0, 10.0, py0 - 7.0, py0, 4.5, mat="MI_Steel")                           # porte-cochere
    b.box((px1 - 0.05, -6.0, 0.0), (px1, 6.0, 4.2), "MI_PaintedMetalDark")                 # car park entrance
    x0, x1, y0, y1 = -18.0, 18.0, -18.0, 18.0
    z0 = 8.0
    top = z0 + storeys * 3.1
    b.box((x0, y0, z0), (x1, y1, top), "MI_TileWhite")
    for k in range(storeys):
        zb = z0 + k * 3.1
        b.box((x0 - 2.0, y0 - 2.0, zb - 0.2), (x1 + 2.0, y1 + 2.0, zb), "MI_ConcreteSmooth")   # wrap balcony
        for (a0, b0, a1, b1) in ((x0 - 2.0, y0 - 2.0, x1 + 2.0, y0 - 1.95), (x0 - 2.0, y1 + 1.95, x1 + 2.0, y1 + 2.0),
                                 (x0 - 2.0, y0 - 2.0, x0 - 1.95, y1 + 2.0), (x1 + 1.95, y0 - 2.0, x1 + 2.0, y1 + 2.0)):
            b.box((a0, b0, zb), (a1, b1, zb + 1.1), "MI_GlassClear")
        for (a0, b0, a1, b1) in ((x0 + 1.0, y0 - 0.03, x1 - 1.0, y0), (x0 + 1.0, y1, x1 - 1.0, y1 + 0.03),
                                 (x0 - 0.03, y0 + 1.0, x0, y1 - 1.0), (x1, y0 + 1.0, x1 + 0.03, y1 - 1.0)):
            b.box((a0, b0, zb + 0.3), (a1, b1, zb + 2.8), "MI_Window")                        # floor-height glazing
    b.box((x0, y0, top), (x1, y1, top + 4.0), "MI_GlassClear")                            # the sky lounge
    roof(b, x0, x1, y0, y1, top + 4.0, parapet=1.2, units=4, stair=False)
    b.box((-6.0, -6.0, top + 4.05), (6.0, 6.0, top + 4.1), "MI_PaintYellow")               # the H pad
    return name, "civic", b.mesh()


def _luxury_lowrise(name, material, Builder):
    """低層高級レジデンス (the Hiroo / Shirokane low-rise luxury block): 36 x 20 m, 4 storeys of 3.4 m (100-150 m2
    units, two to four a floor), a stone base and stone-clad facade, deep balconies with planters and glass rails to
    the street (-Y), a recessed gated entrance with a 3 m stone wall and a planted forecourt, the ramp down to the
    underground car park at the +X corner, a roof terrace with a pergola."""
    b = Builder(name, material)
    x0, x1, y0, y1 = -18.0, 18.0, -8.0, 12.0
    b.box((x0 - 1.0, y0 - 4.0, 0.0), (x1 + 1.0, y0 - 3.6, 1.2), "MI_StoneWall")            # the low wall at the street
    ground(b, x0, x1, y0 - 3.6, y0, "MI_Grass")
    b.box((-2.5, y0 - 4.05, 0.0), (2.5, y0 - 3.55, 2.6), "MI_PaintedMetalDark")            # the gate
    h = 3.4
    b.box((x0, y0, 0.0), (x1, y1, 4 * h), "MI_Limestone")
    for k in range(4):
        zb = k * h
        b.box((x0 + 0.5, y0 - 0.03, zb + 0.4), (x1 - 0.5, y0, zb + h - 0.3), "MI_Window")
        if k > 0:
            b.box((x0 + 0.5, y0 - 2.5, zb - 0.2), (x1 - 0.5, y0, zb), "MI_StoneWall")         # deep balcony
            b.box((x0 + 0.5, y0 - 2.5, zb), (x1 - 0.5, y0 - 2.45, zb + 1.1), "MI_GlassClear")
            b.box((x0 + 0.5, y0 - 2.4, zb), (x1 - 0.5, y0 - 1.9, zb + 0.6), "MI_Grass")      # planters
    b.box((-3.0, y0 - 0.04, 0.2), (3.0, y0, 3.0), "MI_GlassClear")                       # the entrance
    b.box((x1 - 6.0, y0 - 3.6, -0.2), (x1 - 1.0, y0, 0.05), "MI_ConcreteSmooth")           # car park ramp mouth
    top = 4 * h
    roof(b, x0, x1, y0, y1, top, parapet=1.1, units=2, stair=False)
    for xx in (-10.0, -4.0, 2.0, 8.0):                                                    # roof-terrace pergola
        b.box((xx - 0.1, y0 + 2.0, top), (xx + 0.1, y0 + 2.2, top + 2.6), "MI_Wood")
    b.box((-10.5, y0 + 2.0, top + 2.6), (8.5, y0 + 6.0, top + 2.8), "MI_Wood")
    return name, "civic", b.mesh()


def _terrace_house(name, units, material, Builder):
    """メゾネット / テラスハウス (family units in a row, each on two storeys with its own front door): `units` x 6.0 m by
    11 m, 2 x 3.0 m storeys, each with a small front garden, a 1F entrance porch and a 2F balcony to the street (-Y), a
    parking space beside its door, a low hip roof."""
    b = Builder(name, material)
    w = units * 6.0
    x0, x1, y0, y1 = -w / 2, w / 2, -3.5, 7.5
    b.box((x0, y0, 0.0), (x1, y1, 6.0), "MI_TileBeige")
    for i in range(units):
        cx = x0 + 6.0 * (i + 0.5)
        b.box((cx - 2.6, y0 - 0.04, 0.0), (cx - 1.6, y0, 2.2), "MI_Wood")                  # the front door
        b.box((cx - 1.2, y0 - 0.03, 0.9), (cx + 2.6, y0, 2.4), "MI_Window")
        b.box((cx - 2.8, y0 - 1.5, 0.0), (cx - 1.4, y0, 0.05), "MI_StoneWall")              # the porch path
        ground(b, cx - 1.2, cx + 2.9, y0 - 3.5, y0, "MI_Grass")                            # the garden
        b.box((cx - 2.9, y0 - 1.6, 3.0), (cx + 2.9, y0, 3.2), "MI_ConcreteSmooth")          # 2F balcony
        b.box((cx - 2.9, y0 - 1.6, 3.2), (cx + 2.9, y0 - 1.5, 4.2), "MI_PaintedMetal")
        b.box((cx - 2.6, y0 - 0.03, 3.4), (cx + 2.6, y0, 5.6), "MI_Window")
        if i > 0:
            b.box((x0 + 6.0 * i - 0.1, y0 - 3.5, 0.0), (x0 + 6.0 * i + 0.1, y0, 1.0), "MI_Wood")   # garden fences
    hip(b, 0.0, (y0 + y1) / 2, 6.0, w / 2, (y1 - y0) / 2, 1.6, "MI_RoofSlate", eave=0.5)
    return name, "civic", b.mesh()


def apartments(material, Builder):
    return [_apato("Apato2F4", 4, material, Builder), _apato("Apato2F6", 6, material, Builder),
            _apart_rc("ApartRC3F", material, Builder),
            _mansion_line("MansionLine4", 4, 6, material, Builder), _mansion_line("MansionLine6", 6, 8, material, Builder),
            _mansion_tower("MansionPencil", 9, material, Builder),
            _tower_mansion("TowerMansion", 32, material, Builder), _luxury_lowrise("LuxuryLowRise", material, Builder),
            _terrace_house("TerraceHouse4", 4, material, Builder)]


for _n, _t in (("Apato2F4", "木造2階建てアパート, 4 x 1K units in one line a floor (14.6 x 7.3 m + corridor and the "
                             "external stair at the street side), 2 storeys under a slate gable"),
               ("Apato2F6", "木造2階建てアパート, 6 x 1K units in one line (21.8 x 7.3 m)"),
               ("ApartRC3F", "3階建てアパート (RC / heavy steel), 12 x 10 m, 2 units a floor, balconies to the street"),
               ("MansionLine4", "片廊下型マンション, 4 x 3LDK in one line, 6 storeys over a lobby floor (26 x 11 m + "
                                "balconies at the street, the corridor and the lift core at the back)"),
               ("MansionLine6", "片廊下型マンション, 6 x 3LDK in one line, 8 storeys (39 x 11 m)"),
               ("MansionPencil", "1フロア1住戸 pencil マンション, 8 x 14 m, 9 storeys over a lobby + car stacker"),
               ("TowerMansion", "タワーマンション, a 36 x 36 m tower of 32 x 3.1 m over a 48 x 44 m two-storey podium "
                                "(porte-cochere, concierge hall), wrap-around glass balconies, a sky lounge, ~111 m"),
               ("LuxuryLowRise", "低層高級レジデンス, 36 x 20 m, 4 x 3.4 m storeys of large units, stone facade, deep planted "
                                 "balconies, a gated forecourt, the underground car park ramp"),
               ("TerraceHouse4", "メゾネット / テラスハウス, 4 family units of 6 x 11 m on two storeys in a row, each with "
                                 "its own door, garden and balcony")):
    _note(_n, "Placeholder " + _t + ". The street at -Y, the origin at the footprint centre. Placed by the housing and "
              "city mixes (island_buildings.REGIONS); shut.")


def supply_build_all(material, Builder):
    return [repair_shop(material, Builder), car_dealer(material, Builder), home_centre(material, Builder),
            shrine_small(material, Builder), temple_cemetery(material, Builder), factory_small(material, Builder),
            house_traditional(material, Builder)] + apartments(material, Builder)


# ── the third review (2026-10-03): player services, district mission buildings, the bathhouses, the PA, Okinawa ──
def clothing_store(material, Builder):
    """衣料品店 (a clothing store, the disguise service) on a 30 x 28 plot: a 2-storey glass-fronted box (24 x 18,
    9 m), mannequins in the window, a big band sign, the entrance on the corner."""
    b = Builder("ClothingStore", material)
    x0, x1, y0, y1 = -12.0, 12.0, -6.0, 12.0
    b.box((x0, y0, 0.0), (x1, y1, 9.0), "MI_PaintWhite")
    b.box((x0 + 0.5, y0 - 0.05, 0.2), (x1 - 0.5, y0, 8.4), "MI_GlassClear")
    b.box((x0, y0 - 0.25, 7.0), (x1, y0 - 0.05, 8.6), "MI_SignRed")
    for x in range(-9, 10, 3):                                                   # mannequins
        b.box((x - 0.2, y0 + 0.4, 0.0), (x + 0.2, y0 + 0.8, 1.8), "MI_PlasticWhite")
    roof(b, x0, x1, y0, y1, 9.0, units=3)
    ground(b, -15.0, 15.0, -14.0, y0, "MI_ConcreteSmooth")
    return "ClothingStore", "civic", b.mesh()


def shooting_range(material, Builder):
    """射撃場 (a shooting range) on a 30 x 60 plot: a front office (the counter, 12 x 8) and a long covered range
    behind (14 lanes' width, 50 m, baffles overhead, the backstop berm), the whole lot fenced."""
    b = Builder("ShootingRange", material)
    ground(b, -15.0, 15.0, -30.0, 30.0, "MI_Dirt")
    b.box((-6.0, -28.0, 0.0), (6.0, -20.0, 4.0), "MI_TileBeige")                   # the office
    b.box((-4.0, -28.05, 0.2), (4.0, -28.0, 2.6), "MI_GlassClear")
    b.box((-6.0, -28.25, 3.0), (6.0, -28.05, 3.8), "MI_SignGreen")
    b.box((-14.0, -20.0, 0.0), (14.0, -16.0, 3.0), "MI_ConcreteSmooth")              # the firing line's booth
    for k in range(5):                                                         # the overhead baffles
        y = -14.0 + k * 9.0
        b.box((-14.0, y, 3.2), (14.0, y + 1.0, 4.4), "MI_Wood")
    for x in (-14.0, 13.6):
        b.box((x, -20.0, 0.0), (x + 0.4, 28.0, 3.2), "MI_ConcreteSmooth")             # the side walls
    b.wedge_x(-14.0, 14.0, 24.0, 30.0, 6.0, 6.0, "MI_Dirt")                          # the backstop berm
    for k in range(7):
        b.box((-12.0 + k * 4.0, 12.0, 0.0), (-11.2 + k * 4.0, 12.1, 1.8), "MI_PaintWhite")   # targets
    fence(b, -14.8, 14.8, -29.8, 29.8, h=2.4, gaps=[("f", 0.0, 6.0)])
    return "ShootingRange", "civic", b.mesh()


def impound_lot(material, Builder):
    """レッカー移動保管場所 (the police impound lot) on a 50 x 40 plot: a fenced asphalt yard with rows of bays, a
    gate with a barrier, a cabin, a tow truck's place."""
    b = Builder("ImpoundLot", material)
    _parking(b, -25.0, 25.0, -20.0, 20.0, rows=3)
    fence(b, -24.8, 24.8, -19.8, 19.8, h=2.4, gaps=[("f", -15.0, 14.0)])            # a 14 m gate (2026-10-04)
    b.box((-6.0, -19.0, 0.0), (-1.0, -14.0, 2.7), "MI_PlasticWhite")
    b.box((-22.0, -20.3, 1.0), (-8.0, -20.1, 1.15), "MI_SignRed")                  # the barrier arm
    _cars(b, [(-18.0 + 4.0 * i, -6.0, False) for i in range(8)], "MI_PaintedMetalDark")
    return "ImpoundLot", "civic", b.mesh()


def farm_barn(material, Builder):
    """農家 (a farmhouse and its barn) on a 60 x 50 yard -- the farm district's mission building (a gang's hidden
    lab in the barn): a tiled 2-storey farmhouse, a big corrugated barn (20 x 14, 8 m, a sliding door), a tractor
    shed, a 軽トラ's place, a hedge round the yard."""
    b = Builder("FarmBarn", material)
    ground(b, -30.0, 30.0, -25.0, 25.0, "MI_Dirt")
    b.box((-26.0, 4.0, 0.0), (-10.0, 16.0, 6.0), "MI_Wood")
    hip(b, -18.0, 10.0, 6.0, 8.0, 6.0, 3.0, "MI_RoofSlate", eave=1.0)
    b.box((2.0, 0.0, 0.0), (22.0, 14.0, 8.0), "MI_Corrugated")
    b.frustum(12.0, 7.0, 8.0, 10.0, 10.5, 7.5, 10.5, 0.4, "MI_PaintedMetal")
    b.box((8.0, -0.05, 0.0), (16.0, 0.0, 5.5), "MI_PaintedMetalDark")
    b.box((22.0, 2.0, 0.0), (28.0, 12.0, 3.5), "MI_Corrugated")
    for (a0, b0, a1, b1) in ((-30.0, 24.0, 30.0, 25.0), (-30.0, -25.0, -29.0, 25.0), (29.0, -25.0, 30.0, 25.0)):
        b.box((a0, b0, 0.0), (a1, b1, 1.6), "MI_Grass")
    return "FarmBarn", "civic", b.mesh()


def _bath_chimney(b, x, y, h):
    b.frustum(x, y, 0.0, h, 1.4, 1.4, 0.9, 0.9, "MI_BrickRed")


def sento(material, Builder):
    """町の銭湯 (a neighbourhood bathhouse) 14 x 20: a 宮造り temple-style front (a curved gable over the door), a
    のれん, the tall brick chimney behind -- the old residential district's landmark."""
    b = Builder("Sento", material)
    x0, x1, y0, y1 = -7.0, 7.0, -10.0, 10.0
    b.box((x0, y0, 0.0), (x1, y1, 6.0), "MI_Plaster")
    gable(b, 0.0, 0.0, 6.0, 7.5, 10.5, 3.5, "MI_RoofSlate", along="y")
    b.convex([(-4.0, y0 - 1.2, 4.0), (4.0, y0 - 1.2, 4.0), (-4.0, y0 + 1.0, 4.0), (4.0, y0 + 1.0, 4.0),
              (0.0, y0 - 1.6, 6.5), (0.0, y0 + 1.0, 6.5)], "MI_RoofSlate")                  # 唐破風 over the door
    b.box((-1.6, y0 - 0.3, 1.2), (1.6, y0 - 0.25, 2.4), "MI_NorenNavy")
    b.box((-2.0, y0 - 0.05, 0.0), (2.0, y0, 2.6), "MI_Wood")
    _bath_chimney(b, 4.0, 8.0, 18.0)
    return "Sento", "civic", b.mesh()


def super_sento(material, Builder):
    """スーパー銭湯 / 大浴場 on a 90 x 70 plot (the suburb's mission building): a long 2-storey bath hall (50 x 28)
    with a lit glazed front, an outdoor 露天風呂 courtyard behind a bamboo screen, the big sign tower, the car park."""
    b = Builder("SuperSento", material)
    hx, hy = 45.0, 35.0
    _parking(b, -hx, hx, -hy, -hy + 22.0)
    x0, x1, y0, y1 = -30.0, 20.0, -8.0, 20.0
    b.box((x0, y0, 0.0), (x1, y1, 9.0), "MI_Wood")
    b.box((x0 + 4.0, y0 - 0.05, 0.2), (x0 + 24.0, y0, 3.6), "MI_GlassClear")
    hip(b, (x0 + x1) / 2, (y0 + y1) / 2, 9.0, 25.0, 14.0, 4.0, "MI_RoofSlate", eave=1.5)
    b.box((20.0, 0.0, 0.0), (42.0, 30.0, 0.05), "MI_StoneWall")                      # 露天風呂 court
    b.box((24.0, 6.0, 0.05), (38.0, 24.0, 0.07), "MI_PoolWater")
    b.box((42.0, 0.0, 0.0), (42.3, 30.0, 2.6), "MI_Hinoki")                          # the screen
    b.box((20.0, 30.0, 0.0), (42.0, 30.3, 2.6), "MI_Hinoki")
    b.box((25.0, -8.0, 0.0), (26.0, -7.0, 14.0), "MI_Steel")
    b.box((22.0, -8.6, 9.0), (29.0, -6.4, 14.0), "MI_SignRed")
    return "SuperSento", "civic", b.mesh()


def cargo_shed(material, Builder):
    """航空貨物上屋 (an air-cargo shed) on a 70 x 50 plot (the airport's mission building): a 50 x 30 m shed, 10 m, a
    row of truck docks on the landside, ULD containers stacked on the apron side, a fenced yard."""
    b = Builder("CargoShed", material)
    ground(b, -35.0, 35.0, -25.0, 25.0, "MI_ConcreteSmooth")
    b.box((-25.0, -5.0, 0.0), (25.0, 25.0, 10.0), "MI_Corrugated")
    for k in range(8):
        x = -22.0 + k * 6.0
        b.box((x, -5.05, 0.0), (x + 4.0, -5.0, 4.0), "MI_PaintedMetalDark")
    b.box((-25.0, -5.25, 8.0), (25.0, -5.05, 9.6), "MI_SignCyan")
    for k in range(6):                                                        # ULD containers
        b.convex([(-30.0 + k * 3.5, 22.0, 0.0), (-27.2 + k * 3.5, 22.0, 0.0), (-30.0 + k * 3.5, 24.4, 0.0),
                  (-27.2 + k * 3.5, 24.4, 0.0), (-30.0 + k * 3.5, 22.0, 1.6), (-27.2 + k * 3.5, 22.0, 1.6),
                  (-29.4 + k * 3.5, 24.4, 1.6), (-27.8 + k * 3.5, 24.4, 1.6)], "MI_Steel")
    fence(b, -34.8, 34.8, -24.8, 24.8, h=2.4, gaps=[("f", 20.0, 10.0)])
    return "CargoShed", "civic", b.mesh()


def expressway_pa(material, Builder):
    """パーキングエリア (an expressway parking area, the Daikoku shape: inside a loop junction) on a 100 x 50 lot: a
    big car park (car meets, race starts, a police checkpoint), a rest building (food court, toilets, a konbini, 18 x
    40, 6 m), vending machines, the PA sign. 100 x 50: the Wangan terminal loop's interior is ~104 x 54."""
    b = Builder("ExpresswayPA", material)
    hx, hy = 50.0, 25.0
    _parking(b, -hx, hx - 25.0, -hy, hy, rows=3)
    b.box((hx - 22.0, -20.0, 0.0), (hx - 4.0, 20.0, 6.0), "MI_TileBeige")
    b.box((hx - 22.05, -16.0, 0.2), (hx - 22.0, 16.0, 3.6), "MI_GlassClear")
    b.box((hx - 22.5, -20.5, 6.0), (hx - 3.5, 20.5, 6.5), "MI_PaintedMetal")
    b.box((hx - 22.3, -8.0, 4.0), (hx - 22.05, 8.0, 5.6), "MI_ExpwyGreen")
    for k in range(6):
        b.box((hx - 26.0, -12.0 + k * 1.1, 0.0), (hx - 25.0, -11.0 + k * 1.1, 1.8), "MI_SignCyan")   # vending
    return "ExpresswayPA", "civic", b.mesh()


def public_market(material, Builder):
    """公設市場 (an Okinawan public market, the Makishi shape) on a 50 x 40 plot: a 2-storey hall, the ground floor
    open on three sides under a deep canopy (fish, pork and produce stalls), the eating floor above, red-tile awning
    roofs and a シーサー pair at the entrance."""
    b = Builder("PublicMarket", material)
    x0, x1, y0, y1 = -22.0, 22.0, -14.0, 16.0
    for x in range(-20, 21, 8):                                                 # the open ground floor's columns
        for y in (y0, y1):
            b.box((x - 0.3, y - 0.3, 0.0), (x + 0.3, y + 0.3, 4.5), "MI_ConcreteSmooth")
    b.box((x0, y0, 4.5), (x1, y1, 9.0), "MI_Plaster")
    b.box((x0 - 3.0, y0 - 3.0, 4.2), (x1 + 3.0, y0, 4.5), "MI_RoofTileRed")             # the canopy
    for i in range(4):                                                          # stalls
        for j in range(3):
            b.box((-16.0 + i * 9.0, -9.0 + j * 9.0, 0.0), (-10.0 + i * 9.0, -6.0 + j * 9.0, 0.9), "MI_Wood")
    roof(b, x0, x1, y0, y1, 9.0, units=4)
    for x in (-3.0, 3.0):
        b.box((x - 0.4, y0 - 4.0, 0.0), (x + 0.4, y0 - 3.2, 1.4), "MI_RoofTileRed")       # シーサー
    b.box((-8.0, y0 - 0.2, 5.0), (8.0, y0, 7.0), "MI_SignRed")
    return "PublicMarket", "civic", b.mesh()


for _n, _t in (("ClothingStore", "衣料品店 (disguise service), 30 x 28 plot, the street at -Y; shut for now"),
               ("ShootingRange", "射撃場, 30 x 60 plot, the range running back from the street; shut for now"),
               ("ImpoundLot", "police impound lot, 50 x 40, fenced, gate front-left"),
               ("FarmBarn", "farmhouse + barn, 60 x 50 yard (the farm district's mission building: the gang's lab)"),
               ("Sento", "neighbourhood 銭湯 14 x 20 with its chimney; placed by the older housing mixes; shut"),
               ("SuperSento", "スーパー銭湯 / 大浴場, 90 x 70 plot (the suburb's mission building); shut for now"),
               ("CargoShed", "air-cargo shed, 70 x 50 plot (the airport's mission building: cargo theft); shut"),
               ("ExpresswayPA", "expressway parking area inside the Wangan terminal loop (100 x 50): car meets, race "
                "starts, a checkpoint; reached from the loop road like any car park"),
               ("PublicMarket", "Okinawan 公設市場, 50 x 40 plot by Castle Town; shut for now")):
    _note(_n, "Placeholder " + _t + ". (library_jp_city.py)")


def services_build_all(material, Builder):
    return [clothing_store(material, Builder), shooting_range(material, Builder), impound_lot(material, Builder),
            farm_barn(material, Builder), sento(material, Builder), super_sento(material, Builder),
            cargo_shed(material, Builder), expressway_pa(material, Builder), public_market(material, Builder)]


def build_all(material, Builder):
    return services_build_all(material, Builder) + supply_build_all(material, Builder) + ([university(material, Builder), public_library(material, Builder), jimusho(material, Builder), port_compound(material, Builder), scrapyard(material, Builder),
             pachinko(material, Builder)] + small_shops(material, Builder)
            + [shotengai(material, Builder), danchi(material, Builder), hotel_business(material, Builder),
               hotel_love(material, Builder), construction_site(material, Builder), game_centre(material, Builder),
               karaoke(material, Builder), arena(material, Builder), suburban_mall(material, Builder),
               campus(material, Builder), broadcast_centre(material, Builder)])
