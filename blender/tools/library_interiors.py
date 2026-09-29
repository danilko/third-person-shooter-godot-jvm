"""Interior fittings for the mission buildings (user, 2026-09-28): PLACEHOLDERS an artist replaces by hand in
library.blend. Imported by library_procedural.build_all. Ours, CC0.

Frame as every library piece: Z up, origin at the footprint centre on the floor, the side a person USES facing -Y.
Real Japanese sizes, stated where chosen. Every one is a labelled block to be modelled properly (kits/library/
ARTIST_NOTES.md "Interior placeholders" and kits/interiors/ARTIST_NOTES.md list them).

Used by: the supermarket (kits/shops, tools/building_kit/shop_interiors.py) and the mission buildings
(kits/interiors, blender/tools/interior_plans.py): the police station's ARMOURY (a light pistol locker in the 交番, a
full armoury in the 警察署), the fire stations' apparatus, the hospital's wards and theatres, the office, the hotel,
the warehouse.
"""
import math

NOTE = ("Interior PLACEHOLDER (blender/tools/library_interiors.py), ours (CC0): replace by hand, keeping the frame "
        "(Z up, origin at the footprint centre on the floor, the side a person uses facing -Y) and the size, which "
        "the buildings' layouts assume. Copies of this mesh live in kits/shops/*.blend and kits/interiors/*.blend: "
        "re-run blender/tools/build_interior_blends.py / build_shop_blends.py only for a building nobody edited.")


def _legs(b, x0, x1, y0, y1, z, w=0.04, mat="MI_Steel"):
    for x in (x0 + w, x1 - w):
        for y in (y0 + w, y1 - w):
            b.box((x - w, y - w, 0.0), (x + w, y + w, z), mat)


# ── supermarket (食品スーパー) ───────────────────────────────────────────────────────────────────────────────────

def checkout(material, Builder):
    """A checkout lane (レジ): a 0.8 x 2.4 m counter 0.9 m high, the register and card reader at the -Y end facing
    the cashier's side (+X), a basket shelf at the +Y end. Lanes stand 2.2 m apart (a 1.4 m aisle)."""
    b = Builder("Shop_Checkout", material)
    b.box((-0.4, -1.2, 0.0), (0.4, 1.2, 0.9), "MI_PlasticWhite")
    b.box((-0.42, -1.22, 0.86), (0.42, 1.22, 0.9), "MI_Steel")
    b.box((-0.1, -0.9, 0.9), (0.3, -0.5, 1.25), "MI_PlasticDark")              # register
    b.box((0.05, -1.0, 1.25), (0.3, -0.6, 1.45), "MI_Light")                   # its screen
    b.box((-0.3, 0.6, 0.9), (0.3, 1.1, 0.94), "MI_PlasticDark")                # basket shelf
    b.box((-0.05, -1.2, 1.9), (0.05, -1.1, 2.4), "MI_Steel")                   # the lane-number pole
    b.box((-0.2, -1.2, 2.2), (0.2, -1.12, 2.45), "MI_Sign")
    return "Shop_Checkout", "interior", b.mesh()


def bagging_table(material, Builder):
    """サッカー台: the packing table after the checkouts, 1.8 x 0.6 m, 0.85 m high, a bag-roll rail above."""
    b = Builder("Shop_BaggingTable", material)
    b.box((-0.9, -0.3, 0.8), (0.9, 0.3, 0.85), "MI_PlasticWhite")
    _legs(b, -0.9, 0.9, -0.3, 0.3, 0.8)
    b.box((-0.8, 0.26, 0.85), (0.8, 0.3, 1.3), "MI_Steel")
    b.box((-0.7, 0.2, 1.2), (0.7, 0.26, 1.28), "MI_PlasticWhite")              # the bag roll
    return "Shop_BaggingTable", "interior", b.mesh()


def produce_table(material, Builder):
    """青果台: a produce table, 1.8 x 1.2 m, 0.9 m at the front rising to 1.3 m at the back, stepped crates."""
    b = Builder("Shop_ProduceTable", material)
    b.box((-0.9, -0.6, 0.0), (0.9, 0.6, 0.6), "MI_Wood")
    for k, (y0, y1, z) in enumerate(((-0.6, -0.2, 0.9), (-0.2, 0.2, 1.1), (0.2, 0.6, 1.3))):
        b.box((-0.9, y0, 0.6), (0.9, y1, z), "MI_Wood")
        b.box((-0.85, y0 + 0.03, z), (0.85, y1 - 0.03, z + 0.12), "MI_Goods")
    return "Shop_ProduceTable", "interior", b.mesh()


def cart_row(material, Builder):
    """A row of nested shopping carts (カート), 0.6 x 2.4 m, 1.0 m high."""
    b = Builder("Shop_CartRow", material)
    for k in range(6):
        y = -1.1 + k * 0.4
        b.box((-0.28, y, 0.25), (0.28, y + 0.55, 0.8), "MI_Steel")
        b.box((-0.3, y + 0.5, 0.8), (0.3, y + 0.55, 1.0), "MI_PlasticDark")
    b.box((-0.3, -1.2, 0.0), (0.3, 1.2, 0.08), "MI_PaintedMetalDark")
    return "Shop_CartRow", "interior", b.mesh()


def deli_counter(material, Builder):
    """惣菜ケース: a refrigerated deli counter, 1.8 x 0.9 m, 1.2 m high with a sloped glass front toward -Y."""
    b = Builder("Shop_DeliCounter", material)
    b.box((-0.9, -0.45, 0.0), (0.9, 0.45, 0.8), "MI_PaintedMetal")
    b.box((-0.88, -0.35, 0.8), (0.88, 0.4, 0.85), "MI_Steel")
    b.box((-0.85, -0.3, 0.85), (0.85, 0.35, 0.98), "MI_Goods")
    b.box((-0.9, -0.45, 0.8), (0.9, -0.4, 1.2), "MI_GlassClear")
    b.box((-0.9, 0.35, 1.15), (0.9, 0.45, 1.2), "MI_PaintedMetal")
    return "Shop_DeliCounter", "interior", b.mesh()


# ── office (オフィス) ─────────────────────────────────────────────────────────────────────────────────────────────

def desk_island(material, Builder):
    """島型: the Japanese office's desk island, 4 desks facing each other in pairs (2 x 1.2 m wide, 2 x 0.7 deep: 2.4 x
    1.4 m), 0.72 m high, a monitor on each, a low screen down the middle. Chairs are separate (Office_Chair)."""
    b = Builder("Office_DeskIsland", material)
    b.box((-1.2, -0.7, 0.68), (1.2, 0.7, 0.72), "MI_Wood")
    for x in (-1.17, 0.0, 1.17):
        b.box((x - 0.03, -0.67, 0.0), (x + 0.03, 0.67, 0.68), "MI_PaintedMetal")
    b.box((-1.2, -0.02, 0.72), (1.2, 0.02, 1.1), "MI_Fabric")                   # the middle screen
    for x in (-0.6, 0.6):
        for s in (-1, 1):
            b.box((x - 0.25, s * 0.18 - 0.015, 0.72), (x + 0.25, s * 0.18 + 0.015, 1.05), "MI_PlasticDark")
    return "Office_DeskIsland", "interior", b.mesh()


def office_chair(material, Builder):
    """A task chair, 0.6 x 0.6 m, seat 0.45, back to 1.0 m (the back toward +Y)."""
    b = Builder("Office_Chair", material)
    b.box((-0.03, -0.03, 0.0), (0.03, 0.03, 0.42), "MI_Steel")
    b.box((-0.3, -0.3, 0.0), (0.3, 0.3, 0.05), "MI_PlasticDark")
    b.box((-0.25, -0.25, 0.42), (0.25, 0.25, 0.5), "MI_Fabric")
    b.box((-0.23, 0.22, 0.5), (0.23, 0.28, 1.0), "MI_Fabric")
    return "Office_Chair", "interior", b.mesh()


def meeting_table(material, Builder):
    """A meeting table for 8, 3.0 x 1.2 m, 0.72 m high."""
    b = Builder("Office_MeetingTable", material)
    b.box((-1.5, -0.6, 0.68), (1.5, 0.6, 0.72), "MI_Wood")
    for x in (-1.2, 1.2):
        b.box((x - 0.05, -0.4, 0.0), (x + 0.05, 0.4, 0.68), "MI_PaintedMetalDark")
    return "Office_MeetingTable", "interior", b.mesh()


def reception_desk(material, Builder):
    """A reception / security desk (受付), 2.4 x 0.8 m, 1.1 m at the visitor's side (-Y) over a 0.72 m work top."""
    b = Builder("Office_Reception", material)
    b.box((-1.2, -0.4, 0.0), (1.2, -0.25, 1.1), "MI_Wood")
    b.box((-1.25, -0.45, 1.05), (1.25, -0.2, 1.1), "MI_Steel")
    b.box((-1.2, -0.25, 0.68), (1.2, 0.4, 0.72), "MI_Wood")
    for x in (-1.15, 1.15):
        b.box((x - 0.05, -0.25, 0.0), (x + 0.05, 0.4, 0.68), "MI_Wood")
    b.box((-0.5, 0.05, 0.72), (-0.05, 0.1, 1.05), "MI_PlasticDark")
    b.box((0.2, 0.05, 0.72), (0.65, 0.1, 1.05), "MI_PlasticDark")
    return "Office_Reception", "interior", b.mesh()


def sofa(material, Builder):
    """A lobby / lounge sofa, 1.8 x 0.85 m, seat 0.42, back 0.8 m (the back toward +Y)."""
    b = Builder("Office_Sofa", material)
    b.box((-0.9, -0.42, 0.0), (0.9, 0.42, 0.42), "MI_Fabric")
    b.box((-0.9, 0.22, 0.42), (0.9, 0.42, 0.8), "MI_Fabric")
    for x in (-0.9, 0.78):
        b.box((x, -0.42, 0.42), (x + 0.12, 0.42, 0.6), "MI_Fabric")
    return "Office_Sofa", "interior", b.mesh()


def filing_cabinet(material, Builder):
    """A steel filing cabinet (書庫), 0.9 x 0.45 x 1.8 m, glass-fronted upper half."""
    b = Builder("Office_Cabinet", material)
    b.box((-0.45, -0.225, 0.0), (0.45, 0.225, 1.8), "MI_PaintedMetal")
    b.box((-0.42, -0.235, 0.95), (0.42, -0.225, 1.75), "MI_GlassClear")
    b.box((-0.4, -0.2, 1.0), (0.4, 0.15, 1.7), "MI_Goods")
    return "Office_Cabinet", "interior", b.mesh()


def server_rack(material, Builder):
    """A 42U server rack, 0.6 x 1.0 x 2.0 m, the lit front toward -Y."""
    b = Builder("Office_ServerRack", material)
    b.box((-0.3, -0.5, 0.0), (0.3, 0.5, 2.0), "MI_PlasticDark")
    for k in range(10):
        b.box((-0.25, -0.51, 0.15 + k * 0.17), (0.25, -0.5, 0.2 + k * 0.17), "MI_Light")
    return "Office_ServerRack", "interior", b.mesh()


def whiteboard(material, Builder):
    """A mobile whiteboard, 1.8 x 0.5 m base, the board 1.2 m tall from 0.8 m (the board faces -Y)."""
    b = Builder("Office_Whiteboard", material)
    b.box((-0.9, -0.03, 0.8), (0.9, 0.03, 2.0), "MI_PaintWhite")
    for x in (-0.85, 0.85):
        b.box((x - 0.02, -0.02, 0.0), (x + 0.02, 0.02, 0.8), "MI_Steel")
        b.box((x - 0.03, -0.25, 0.0), (x + 0.03, 0.25, 0.05), "MI_Steel")
    return "Office_Whiteboard", "interior", b.mesh()


# ── police (交番 / 警察署) ─────────────────────────────────────────────────────────────────────────────────────────
# The ARMOURY is a gameplay room (user, 2026-09-28: "police station can prepare for weapon room with weapons, the
# small station only light"): the koban carries one pistol locker; the station an armoury of racks. What is actually
# picked up is placed by the level designer at the building's `MARK_weapon_*` markers (kits/interiors/ARTIST_NOTES.md).

def gun_locker(material, Builder):
    """拳銃保管庫: a steel pistol locker, 1.0 x 0.5 x 1.8 m, two doors, the pistols' silhouettes on pegs inside
    (shown through a slot window so it reads)."""
    b = Builder("Police_GunLocker", material)
    b.box((-0.5, -0.25, 0.0), (0.5, 0.25, 1.8), "MI_PaintedMetalDark")
    b.box((-0.48, -0.26, 0.1), (-0.01, -0.25, 1.7), "MI_PaintedMetal")
    b.box((0.01, -0.26, 0.1), (0.48, -0.25, 1.7), "MI_PaintedMetal")
    b.box((-0.4, -0.27, 1.2), (0.4, -0.26, 1.45), "MI_GlassClear")
    for k in range(6):
        b.box((-0.36 + k * 0.13, -0.2, 1.25), (-0.28 + k * 0.13, -0.1, 1.4), "MI_PlasticDark")   # pistols
    b.box((0.06, -0.3, 0.85), (0.1, -0.26, 1.0), "MI_Steel")                    # handle
    return "Police_GunLocker", "police", b.mesh()


def gun_rack(material, Builder):
    """An armoury long-gun rack (武器庫), 1.8 x 0.5 x 1.9 m, open front (-Y): eight rifles/shotguns standing in a
    butt rail, a steel mesh back, a shelf of ammunition cans at the top."""
    b = Builder("Police_GunRack", material)
    b.box((-0.9, 0.2, 0.0), (0.9, 0.25, 1.9), "MI_Steel")                       # the mesh back
    for x in (-0.9, 0.86):
        b.box((x, -0.25, 0.0), (x + 0.04, 0.25, 1.9), "MI_PaintedMetalDark")
    b.box((-0.9, -0.25, 0.0), (0.9, 0.25, 0.1), "MI_PaintedMetalDark")          # the butt rail
    b.box((-0.9, -0.1, 1.2), (0.9, 0.2, 1.24), "MI_PaintedMetalDark")           # the barrel rail
    for k in range(8):
        x = -0.75 + k * 0.21
        b.box((x - 0.03, -0.05, 0.1), (x + 0.03, 0.05, 1.3), "MI_PlasticDark")  # a long gun, muzzle up
    b.box((-0.9, -0.25, 1.55), (0.9, 0.25, 1.59), "MI_PaintedMetalDark")        # top shelf
    for k in range(5):
        x = -0.8 + k * 0.35
        b.box((x, -0.15, 1.59), (x + 0.28, 0.1, 1.8), "MI_Olive")                # ammunition cans
    return "Police_GunRack", "police", b.mesh()


def shield_rack(material, Builder):
    """A riot-shield and helmet rack, 1.8 x 0.5 x 1.9 m: four shields (0.55 x 1.0) leaning in slots, helmets above."""
    b = Builder("Police_ShieldRack", material)
    b.box((-0.9, 0.2, 0.0), (0.9, 0.25, 1.9), "MI_PaintedMetalDark")
    b.box((-0.9, -0.25, 0.0), (0.9, 0.25, 0.08), "MI_PaintedMetalDark")
    for k in range(4):
        x = -0.65 + k * 0.43
        b.box((x - 0.27, 0.05, 0.08), (x + 0.27, 0.1, 1.1), "MI_GlassClear")
    b.box((-0.9, -0.2, 1.4), (0.9, 0.25, 1.44), "MI_PaintedMetalDark")
    for k in range(4):
        x = -0.65 + k * 0.43
        b.box((x - 0.14, -0.1, 1.44), (x + 0.14, 0.15, 1.66), "MI_PlasticDark")
    return "Police_ShieldRack", "police", b.mesh()


def cell_front(material, Builder):
    """留置場: a holding cell's front, one ken (1.82 m) of steel bars 2.4 m tall with a 0.8 m barred door opening
    at the +X end (the game's DOOR_ hangs the leaf there). Runs along X, faces -Y."""
    b = Builder("Police_CellFront", material)
    b.box((-0.91, -0.06, 2.3), (0.91, 0.06, 2.4), "MI_PaintedMetalDark")        # head rail
    b.box((-0.91, -0.06, 0.0), (0.0, 0.06, 0.08), "MI_PaintedMetalDark")
    for k in range(9):
        x = -0.86 + k * 0.1
        b.box((x - 0.015, -0.015, 0.0), (x + 0.015, 0.015, 2.3), "MI_Steel")
    for x in (0.0, 0.85):                                                        # the door jambs
        b.box((x - 0.03, -0.06, 0.0), (x + 0.03, 0.06, 2.3), "MI_PaintedMetalDark")
    return "Police_CellFront", "police", b.mesh()


def cell_bunk(material, Builder):
    """A cell's fixed bench-bed, 2.0 x 0.8 m, 0.45 m high, a folded mattress."""
    b = Builder("Police_CellBunk", material)
    b.box((-1.0, -0.4, 0.0), (1.0, 0.4, 0.4), "MI_ConcreteSmooth")
    b.box((-0.95, -0.35, 0.4), (0.95, 0.35, 0.48), "MI_Fabric")
    return "Police_CellBunk", "police", b.mesh()


# ── fire (消防署 / 出張所) ─────────────────────────────────────────────────────────────────────────────────────────

def _truck(b, L, W, H, cab, body_mat, stripe="MI_PaintWhite"):
    """A truck along -Y (the cab at -Y, where the apparatus bay opens)."""
    b.box((-W / 2, -L / 2, 0.45), (W / 2, -L / 2 + cab, H * 0.95), body_mat)      # cab
    b.box((-W / 2 + 0.05, -L / 2 - 0.01, H * 0.55), (W / 2 - 0.05, -L / 2, H * 0.9), "MI_GlassClear")
    b.box((-W / 2, -L / 2 + cab, 0.45), (W / 2, L / 2, H), body_mat)             # body
    b.box((-W / 2 - 0.01, -L / 2, 1.0), (W / 2 + 0.01, L / 2, 1.12), stripe)     # the white band
    for y in (-L / 2 + 1.2, L / 2 - 1.4, L / 2 - 2.6):
        for x in (-W / 2 + 0.2, W / 2 - 0.2):
            b.box((x - 0.18 if x < 0 else x - 0.18, y - 0.5, 0.0), (x + 0.18, y + 0.5, 0.95), "MI_PlasticDark")
    b.box((-0.4, -L / 2 + 0.4, H * 0.95), (0.4, -L / 2 + 0.8, H * 0.95 + 0.18), "MI_SignRed")   # light bar


def pump_truck(material, Builder):
    """消防ポンプ車 (a CD-I pumper): 7.0 x 2.3 x 2.9 m, red, the white band, the hose bed, a light bar on the cab.
    Faces -Y (backed into its bay, nose to the street)."""
    b = Builder("Fire_PumpTruck", material)
    _truck(b, 7.0, 2.3, 2.9, 2.2, "MI_CraneRed")
    b.box((-1.0, 0.0, 2.9), (1.0, 3.3, 3.1), "MI_Steel")                         # ladder on top
    return "Fire_PumpTruck", "fire", b.mesh()


def ladder_truck(material, Builder):
    """はしご車: 10.0 x 2.5 x 3.5 m, the turntable and nested ladder over the body."""
    b = Builder("Fire_LadderTruck", material)
    _truck(b, 10.0, 2.5, 3.0, 2.4, "MI_CraneRed")
    b.box((-0.8, 1.5, 3.0), (0.8, 3.1, 3.3), "MI_PaintedMetalDark")              # turntable
    b.box((-0.6, -4.2, 3.2), (0.6, 4.0, 3.5), "MI_Steel")                        # the ladder
    return "Fire_LadderTruck", "fire", b.mesh()


def ambulance(material, Builder):
    """救急車 (高規格救急車): 5.6 x 1.9 x 2.5 m, white with the red band and the rear box."""
    b = Builder("Fire_Ambulance", material)
    _truck(b, 5.6, 1.9, 2.5, 1.8, "MI_PaintWhite", stripe="MI_SignRed")
    return "Fire_Ambulance", "fire", b.mesh()


def gear_rack(material, Builder):
    """防火衣 rack: turnout gear on hooks over boots, 1.8 x 0.6 x 1.9 m, four positions, open front (-Y)."""
    b = Builder("Fire_GearRack", material)
    b.box((-0.9, 0.25, 0.0), (0.9, 0.3, 1.9), "MI_Steel")
    b.box((-0.9, -0.3, 0.0), (0.9, 0.3, 0.05), "MI_PaintedMetalDark")
    for k in range(4):
        x = -0.68 + k * 0.45
        b.box((x - 0.2, -0.05, 0.9), (x + 0.2, 0.25, 1.6), "MI_Olive")          # the coat
        b.box((x - 0.15, -0.1, 1.62), (x + 0.15, 0.2, 1.85), "MI_PaintYellow")   # the helmet
        b.box((x - 0.18, -0.2, 0.05), (x + 0.18, 0.2, 0.45), "MI_PlasticDark")   # the boots and trousers
    return "Fire_GearRack", "fire", b.mesh()


def bunk_bed(material, Builder):
    """A crew bunk (仮眠室), 2.0 x 0.9 x 1.7 m, two berths."""
    b = Builder("Fire_Bunk", material)
    for x in (-0.95, 0.95):
        for y in (-0.42, 0.42):
            b.box((x - 0.04, y - 0.04, 0.0), (x + 0.04, y + 0.04, 1.7), "MI_PaintedMetal")
    for z in (0.3, 1.2):
        b.box((-1.0, -0.45, z), (1.0, 0.45, z + 0.08), "MI_PaintedMetal")
        b.box((-0.95, -0.4, z + 0.08), (0.95, 0.4, z + 0.2), "MI_Fabric")
    return "Fire_Bunk", "fire", b.mesh()


# ── hospital (病院) ──────────────────────────────────────────────────────────────────────────────────────────────

def hospital_bed(material, Builder):
    """A ward bed, 2.1 x 1.0 m, 0.6 m high, side rails, the head (+Y) raised, a monitor pole at the head."""
    b = Builder("Hosp_Bed", material)
    b.box((-0.5, -1.05, 0.0), (0.5, 1.05, 0.5), "MI_PaintedMetal")
    b.box((-0.47, -1.0, 0.5), (0.47, 1.0, 0.62), "MI_PaintWhite")
    b.box((-0.5, 0.95, 0.0), (0.5, 1.05, 1.0), "MI_PaintedMetal")               # headboard
    for x in (-0.52, 0.5):
        b.box((x, -0.3, 0.62), (x + 0.02, 0.6, 0.85), "MI_Steel")               # side rails
    b.box((0.55, 0.95, 0.0), (0.6, 1.0, 1.9), "MI_Steel")                      # the drip pole
    return "Hosp_Bed", "hospital", b.mesh()


def exam_table(material, Builder):
    """An examination couch (診察台), 1.9 x 0.7 m, 0.6 m high."""
    b = Builder("Hosp_ExamTable", material)
    b.box((-0.35, -0.95, 0.0), (0.35, 0.95, 0.5), "MI_PaintedMetal")
    b.box((-0.35, -0.95, 0.5), (0.35, 0.95, 0.6), "MI_Fabric")
    return "Hosp_ExamTable", "hospital", b.mesh()


def or_table(material, Builder):
    """An operating table under its theatre light: the table 2.0 x 0.6 m at 0.9 m, the light on a boom at 2.4 m."""
    b = Builder("Hosp_ORTable", material)
    b.box((-0.2, -0.3, 0.0), (0.2, 0.3, 0.8), "MI_Steel")
    b.box((-0.3, -1.0, 0.8), (0.3, 1.0, 0.92), "MI_PlasticDark")
    b.box((-0.05, -0.05, 0.92), (0.05, 0.05, 2.6), "MI_Steel")
    b.box((-0.45, -0.45, 2.3), (0.45, 0.45, 2.42), "MI_Light")
    return "Hosp_ORTable", "hospital", b.mesh()


def curtain(material, Builder):
    """A cubicle curtain (カーテン) on its ceiling track: 2.4 m long, 0.02 m thick, from 0.3 m to 2.5 m. No collider
    by design (a walker pushes through)."""
    b = Builder("Hosp_Curtain", material)
    b.box((-1.2, -0.01, 0.3), (1.2, 0.01, 2.4), "MI_Fabric")
    b.box((-1.2, -0.02, 2.4), (1.2, 0.02, 2.45), "MI_Steel")
    return "Hosp_Curtain", "hospital", b.mesh()


def monitor_cart(material, Builder):
    """A patient monitor / medical cart, 0.6 x 0.5 x 1.5 m, the screen toward -Y."""
    b = Builder("Hosp_Monitor", material)
    b.box((-0.3, -0.25, 0.0), (0.3, 0.25, 0.9), "MI_PlasticWhite")
    b.box((-0.25, -0.1, 0.9), (0.25, 0.1, 1.5), "MI_PlasticDark")
    b.box((-0.2, -0.11, 1.0), (0.2, -0.1, 1.4), "MI_Light")
    return "Hosp_Monitor", "hospital", b.mesh()


def nurse_station(material, Builder):
    """ナースステーション: a 3.6 x 0.8 m counter, 1.05 m at the corridor side (-Y), a 0.72 m work top behind, two
    screens."""
    b = Builder("Hosp_NurseStation", material)
    b.box((-1.8, -0.4, 0.0), (1.8, -0.25, 1.05), "MI_PlasticWhite")
    b.box((-1.85, -0.45, 1.0), (1.85, -0.2, 1.05), "MI_Wood")
    b.box((-1.8, -0.25, 0.68), (1.8, 0.4, 0.72), "MI_Wood")
    for x in (-1.75, 1.75):
        b.box((x - 0.05, -0.25, 0.0), (x + 0.05, 0.4, 0.68), "MI_PlasticWhite")
    for x in (-0.9, 0.9):
        b.box((x - 0.25, 0.1, 0.72), (x + 0.25, 0.14, 1.05), "MI_PlasticDark")
    return "Hosp_NurseStation", "hospital", b.mesh()


def xray(material, Builder):
    """An X-ray unit: the table 2.0 x 0.8 m and the ceiling tube stand; 2.2 m tall."""
    b = Builder("Hosp_XRay", material)
    b.box((-0.4, -1.0, 0.0), (0.4, 1.0, 0.75), "MI_PlasticWhite")
    b.box((0.6, -0.2, 0.0), (0.8, 0.2, 2.2), "MI_PlasticWhite")
    b.box((-0.3, -0.25, 1.6), (0.8, 0.25, 1.9), "MI_PlasticWhite")
    return "Hosp_XRay", "hospital", b.mesh()


def stretcher(material, Builder):
    """An ambulance stretcher (ストレッチャー), 2.0 x 0.6 m, 0.9 m high."""
    b = Builder("Hosp_Stretcher", material)
    _legs(b, -0.3, 0.3, -0.9, 0.9, 0.8)
    b.box((-0.3, -1.0, 0.8), (0.3, 1.0, 0.9), "MI_PaintWhite")
    return "Hosp_Stretcher", "hospital", b.mesh()


def waiting_bench(material, Builder):
    """A waiting-room bench of four linked seats, 2.2 x 0.6 m (the back toward +Y)."""
    b = Builder("Hosp_WaitingBench", material)
    b.box((-1.1, -0.05, 0.0), (1.1, 0.05, 0.4), "MI_Steel")
    for k in range(4):
        x = -0.825 + k * 0.55
        b.box((x - 0.25, -0.28, 0.4), (x + 0.25, 0.22, 0.46), "MI_Fabric")
        b.box((x - 0.25, 0.22, 0.46), (x + 0.25, 0.28, 0.85), "MI_Fabric")
    return "Hosp_WaitingBench", "hospital", b.mesh()


# ── hotel (リゾートホテル) ───────────────────────────────────────────────────────────────────────────────────────

def hotel_bed(material, Builder):
    """A hotel twin/double bed, 2.0 x 1.6 m, 0.55 m high, the headboard at +Y."""
    b = Builder("Hotel_Bed", material)
    b.box((-0.8, -1.0, 0.0), (0.8, 1.0, 0.35), "MI_Wood")
    b.box((-0.78, -0.98, 0.35), (0.78, 0.98, 0.55), "MI_PaintWhite")
    b.box((-0.8, 0.95, 0.0), (0.8, 1.05, 1.1), "MI_Wood")
    b.box((-0.7, 0.55, 0.55), (0.7, 0.9, 0.68), "MI_PaintWhite")                 # pillows
    return "Hotel_Bed", "hotel", b.mesh()


def unit_bath(material, Builder):
    """ユニットバス: the bath unit's tub, 1.6 x 0.75 x 0.55 m, white."""
    b = Builder("Hotel_Tub", material)
    b.box((-0.8, -0.375, 0.0), (0.8, 0.375, 0.55), "MI_PlasticWhite")
    b.box((-0.7, -0.3, 0.2), (0.7, 0.3, 0.56), "MI_PoolWater")
    return "Hotel_Tub", "hotel", b.mesh()


def lounger(material, Builder):
    """A pool lounger, 1.9 x 0.7 m, the back raised at +Y."""
    b = Builder("Hotel_Lounger", material)
    _legs(b, -0.35, 0.35, -0.95, 0.95, 0.3)
    b.box((-0.35, -0.95, 0.3), (0.35, 0.4, 0.36), "MI_PaintWhite")
    b.beam((0.0, 0.4, 0.33), (0.0, 0.95, 0.8), 0.7, "MI_PaintWhite")
    return "Hotel_Lounger", "hotel", b.mesh()


# ── warehouse (倉庫) ─────────────────────────────────────────────────────────────────────────────────────────────

def pallet_rack(material, Builder):
    """A pallet rack bay (パレットラック): 2.7 m wide, 1.1 m deep, 4.5 m tall, three beam levels of loaded pallets,
    open both sides (a forklift works from -Y)."""
    b = Builder("Warehouse_Rack", material)
    for x in (-1.35, 1.29):
        for y in (-0.55, 0.49):
            b.box((x, y, 0.0), (x + 0.06, y + 0.06, 4.5), "MI_CraneRed")
    for z in (0.0, 1.5, 3.0):
        if z > 0:
            for y in (-0.55, 0.49):
                b.box((-1.35, y, z - 0.1), (1.35, y + 0.06, z), "MI_PaintYellow")
        for x in (-0.65, 0.65):
            b.box((x - 0.55, -0.5, z + 0.02), (x + 0.55, 0.5, z + 0.15), "MI_Wood")
            b.box((x - 0.5, -0.45, z + 0.15), (x + 0.5, 0.45, z + 1.2), "MI_Corrugated")
    return "Warehouse_Rack", "warehouse", b.mesh()


def forklift(material, Builder):
    """A counterbalance forklift (フォークリフト), 2.3 x 1.2 x 2.1 m, the forks toward -Y."""
    b = Builder("Warehouse_Forklift", material)
    b.box((-0.6, -0.4, 0.3), (0.6, 1.15, 1.1), "MI_PaintYellow")
    b.box((-0.6, 0.7, 1.1), (0.6, 1.15, 1.5), "MI_PaintedMetalDark")             # counterweight
    for x in (-0.55, 0.51):
        b.box((x, -0.4, 1.1), (x + 0.04, 0.6, 2.1), "MI_PaintedMetalDark")       # the overhead guard
    b.box((-0.6, -0.4, 2.05), (0.6, 0.6, 2.1), "MI_PaintedMetalDark")
    b.box((-0.45, -0.55, 0.0), (0.45, -0.45, 2.0), "MI_PaintedMetalDark")        # mast
    for x in (-0.3, 0.3):
        b.box((x - 0.05, -1.15, 0.05), (x + 0.05, -0.55, 0.1), "MI_Steel")      # forks
    for y in (-0.2, 0.9):
        for x in (-0.62, 0.5):
            b.box((x, y - 0.25, 0.0), (x + 0.12, y + 0.25, 0.5), "MI_PlasticDark")
    return "Warehouse_Forklift", "warehouse", b.mesh()


def pallet_load(material, Builder):
    """A loaded pallet on the floor, 1.1 x 1.1 m, 1.35 m high (boxes on a wooden pallet)."""
    b = Builder("Warehouse_Pallet", material)
    b.box((-0.55, -0.55, 0.0), (0.55, 0.55, 0.15), "MI_Wood")
    b.box((-0.5, -0.5, 0.15), (0.5, 0.5, 1.35), "MI_Corrugated")
    return "Warehouse_Pallet", "warehouse", b.mesh()


def roll_cage(material, Builder):
    """カゴ台車: a roll cage, 0.8 x 0.6 x 1.7 m, mesh sides, cartons inside (supermarket deliveries)."""
    b = Builder("Warehouse_RollCage", material)
    b.box((-0.4, -0.3, 0.1), (0.4, 0.3, 0.15), "MI_Steel")
    for x in (-0.4, 0.38):
        b.box((x, -0.3, 0.1), (x + 0.02, 0.3, 1.7), "MI_Steel")
    b.box((-0.4, 0.28, 0.1), (0.4, 0.3, 1.7), "MI_Steel")
    b.box((-0.36, -0.26, 0.15), (0.36, 0.26, 1.2), "MI_Corrugated")
    for x in (-0.3, 0.3):
        for y in (-0.22, 0.22):
            b.box((x - 0.04, y - 0.04, 0.0), (x + 0.04, y + 0.04, 0.1), "MI_PlasticDark")
    return "Warehouse_RollCage", "warehouse", b.mesh()


FNS = (checkout, bagging_table, produce_table, cart_row, deli_counter,
       desk_island, office_chair, meeting_table, reception_desk, sofa, filing_cabinet, server_rack, whiteboard,
       gun_locker, gun_rack, shield_rack, cell_front, cell_bunk,
       pump_truck, ladder_truck, ambulance, gear_rack, bunk_bed,
       hospital_bed, exam_table, or_table, curtain, monitor_cart, nurse_station, xray, stretcher, waiting_bench,
       hotel_bed, unit_bath, lounger,
       pallet_rack, forklift, pallet_load, roll_cage)


def build_all(material, Builder):
    return [f(material, Builder) for f in FNS]


def notes():
    """{piece: edit note}: every placeholder here carries the same note."""
    import inspect
    out = {}
    for f in FNS:
        src = inspect.getsource(f)
        name = src.split('Builder("', 1)[1].split('"', 1)[0]
        out[name] = NOTE
    return out
