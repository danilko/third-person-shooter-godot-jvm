"""The INTERIOR PLANS of the shops (user, 2026-09-27): the small and large konbini and the family restaurant, as
library props in the building's frame. They are the SEED of blender/tools/build_shop_blends.py, which lays them out
ONCE into `assets/world_source/kits/shops/Shop_<Id>.blend`; from then on the .blend is the artist's and owns the
interior (its piece `<Id>_Interior`, exported by export_building_kit.py). A piece an artist has edited is kept on a
regenerate. Edit THIS file only to change the seed of a store nobody has touched.

Frame: the footprint centre on the floor, front (the street) +Z, right +X, Godot axes. Yaw: 0 -> the piece's used
face +Z, 90 -> +X, 180 -> -Z, 270 -> -X. A wall piece runs along its own X (yaw 90/270 runs it along Z).

* Restrooms: every store has at least one ACCESSIBLE restroom (多機能トイレ: a 1.0 m doorway with a SOLID SLIDING
  door, toilet, L grab rail, basin, baby table). The small konbini has one (the customers' and the staff's); the large
  one has two (a customer one at the back-left, a staff one opening behind the counter); the restaurant has a staff one
  and TWO customer accessible rooms (user, 2026-09-28: the space is small, so two, not three).
* Store rooms, staff rooms, offices and the cooler room have HINGED doors; the street entrance stays the 自動ドア.
* Staff never leave straight out of a room: the staff exit opens into the STAFF AISLE, which is itself behind a
  hinged door (user, 2026-09-28).
* Konbini (user, 2026-09-28, from a review of the hand edits): the walk-in cooler is a ROOM whose front wall is the
  drink doors (open backs, restocked from inside) with shelves and a freezer for stock; open bento cases (no door);
  an upright freezer case (the chest ice freezer is gone); a half-glass cigarette wall behind the counter; at least
  TWO coffee machines and TWO hot cases; a sorted bin station; a wall-mounted eat-in counter (1 stool small, 3 large);
  vending machines OUTSIDE on the forecourt (2 small, 3 large). The restaurant adds the bin station, meal-ticket
  machines (食券機) and an ATM by the entrance.
"""
DOOR_BOXES = [[-0.6675, 1.35, 0, 0.485, 2.7, 0.12], [0.6675, 1.35, 0, 0.485, 2.7, 0.12], [0, 2.35, 0, 0.85, 0.7, 0.12]]
WIDE_BOXES = [[-0.705, 1.35, 0, 0.41, 2.7, 0.12], [0.705, 1.35, 0, 0.41, 2.7, 0.12], [0, 2.35, 0, 1.0, 0.7, 0.12]]
PASS_BOXES = [[0, 0.475, 0, 1.82, 0.95, 0.12], [0, 2.075, 0, 1.82, 1.25, 0.12]]


def r(v):
    return round(v, 4)


def P(piece, x, z, yaw=0.0, **kw):
    d = {"piece": "library:" + piece, "at": [r(x), r(z)]}
    if yaw:
        d["yaw"] = float(yaw)
    d.update(kw)
    return d


def wall(x, z, yaw=0.0):
    return P("Wall_Partition", x, z, yaw)


def half(x, z, yaw=0.0):
    return P("Wall_PartitionHalf", x, z, yaw)


def swing(x, z, yaw=0.0):
    """a hinged interior door (store room, staff room, office); the leaf swings away from whoever opens it"""
    return P("Wall_PartitionDoor", x, z, yaw, door={"w": 0.85, "h": 2.0}, collide={"boxes": DOOR_BOXES})


def slide(x, z, yaw, sdir, wide=False):
    """a SOLID sliding door hung on the piece's +Z face (a restroom's 引き戸); `sdir` along the piece's own X"""
    if wide:
        return P("Wall_PartitionDoorWide", x, z, yaw, door={"w": 1.0, "h": 2.0, "style": "slide", "slide_dir": sdir},
                 collide={"boxes": WIDE_BOXES})
    return P("Wall_PartitionDoor", x, z, yaw, door={"w": 0.85, "h": 2.0, "style": "slide", "slide_dir": sdir},
             collide={"boxes": DOOR_BOXES})


def accessible_wc(tx, tz, tyaw, rail, basin, baby):
    """the fittings of an accessible toilet (多機能トイレ): toilet, L grab rail, basin + mirror, baby table"""
    out = [P("WC_Toilet", tx, tz, tyaw), P("WC_GrabRail", *rail, collide="none")]
    bx, bz, byaw, mx, mz = basin
    out += [P("WC_Basin", bx, bz, byaw, collide="none"), P("WC_Mirror", mx, mz, byaw, collide="none")]
    out.append(P("WC_BabyTable", *baby, collide="none"))
    return out


def outside(piece, x, z, yaw=0.0, **kw):
    """a piece standing OUTSIDE the front wall, on the forecourt (the frontage keeps 1.5 m, island_buildings.KERB_GAP):
    a vending machine, the bins. Sunk 3 cm, because outside the plinth the ground is lower than the shop floor."""
    return P(piece, x, z, yaw, y=-0.03, **kw)


def cooler_room(fridge, stock):
    """the WALK-IN COOLER as a ROOM (user, 2026-09-28): the reach-in doors ARE its front wall (open at the back, so
    staff restock them all from inside), shelves and a freezer for stacked stock inside, entered by a hinged door"""
    return fridge + stock


def konbini_s():
    # 12.74 x 18.2 m, interior +-6.19 x +-8.92. Entrance front module 5 (x 3.64); the staff exit is back module 0
    # (x 5.46), into the STAFF AISLE (x 4.96..6.19), never straight out of the staff room.
    p = []
    # the ONE accessible restroom (a small store: customers and staff), back-left x -6.19..-2.73, z -8.92..-5.46
    p += [slide(-5.46, -5.46, 0, 1, wide=True), wall(-3.64, -5.46), wall(-2.73, -6.37, 90), wall(-2.73, -8.19, 90)]
    p += accessible_wc(-5.805, -8.3, 90, (-5.2, -8.92, 0), (-3.6, -8.6, 0, -3.6, -8.9), (-2.79, -6.5, 270))
    # the walk-in cooler room across the back middle (x -2.73..2.73, z -8.92..-6.25): six drink doors are its front,
    # a hinged door from the staff room, a stock shelf and a freezer for frozen stock inside
    p += cooler_room([P("Shop_FridgeDoor", -2.275, -5.85, repeat=[6, 0.91, 0])],
                     [P("Shop_StockShelf", -0.7, -8.55), P("Kitchen_Fridge", -2.24, -7.3, 90)])
    p += [swing(2.73, -8.19, 90), wall(2.73, -6.37, 90), half(2.73, -5.005, 90)]
    # the staff room (x 2.73..4.9): lockers, desk, safe; its door opens onto the staff aisle
    p += [wall(4.9, -8.01, 90), swing(4.9, -6.19, 90), half(4.9, -4.915, 90), wall(3.64, -4.55)]
    p += [P("Office_Locker", 4.585, -8.3, 270), P("Office_Desk", 3.6, -4.97, 180), P("Office_Safe", 3.1, -6.6)]
    # the staff aisle is itself behind a hinged door, onto the floor behind the counter
    p += [swing(5.46, -4.55)]
    # the counter: two registers, TWO coffee machines, TWO hot cases at its front end; the cigarette wall behind it
    p += [P("Shop_Counter", 3.59, -0.64, 90),
          P("Shop_Register", 3.64, -1.74, 90, y=1.0, collide="none"),
          P("Shop_Register", 3.64, -0.04, 90, y=1.0, collide="none"),
          P("Shop_CoffeeMachine", 3.64, 0.99, 90, y=1.0, collide="none"),
          P("Shop_CoffeeMachine", 3.64, 1.46, 90, y=1.0, collide="none"),
          P("Shop_HotCase", 3.63, 2.36, 90), P("Shop_HotCase", 3.63, 3.29, 90),
          P("Shop_CigaretteCase", 5.965, -2.1, 270, repeat=[2, 0, 1.82])]
    p += [P("Shop_ATM", 5.7, 6.52, 270), P("Shop_Copier", 5.75, 8.22, 270)]
    # the sales floor: open bento cases down the left wall, the upright freezer, gondolas, magazines along the glass,
    # a one-seat eat-in counter in the front corner
    p += [P("Shop_OpenCase", -5.765, -3.39, 90, repeat=[2, 0, 1.82]), P("Shop_FreezerCase", -5.715, 0.5, 90)]
    p += [P("Shop_Gondola", x, -2.09, 90, repeat=[3, 0, 2.88]) for x in (-2.63, -0.13)]
    p += [P("Shop_MagazineRack", -2.57, 8.65, 180, repeat=[3, 1.815, 0])]
    p += [P("Shop_EatInCounter", -5.2, 8.695, 180), P("Shop_Stool", -5.2, 8.1)]
    # outside: the sorted bins by the door and two vending machines
    p += [outside("Shop_BinStation", 1.5, 9.375), outside("Station_VendingMachine", -2.9, 9.48, repeat=[2, 1.1, 0])]
    return p


def konbini_l():
    # 21.84 m square, interior +-10.74. Entrance front module 7 (x 2.73); the staff exit is back module 2 (x 6.37) at
    # the end of the STAFF AISLE; the delivery door is left module 8 (z 4.55), into the store room.
    p = []
    # ── staff side (right): locker room / manager's office / staff accessible restroom off the staff aisle
    p += [wall(7.28, -10.01, 270), swing(7.28, -8.19, 270), wall(7.28, -6.37, 270), swing(7.28, -4.55, 270),
          slide(7.28, -2.73, 270, 1, wide=True), wall(7.28, -0.91, 270)]
    for z in (-6.37, -3.64):
        p += [wall(8.19, z), wall(10.01, z)]
    p += [wall(8.19, 0.0), wall(10.01, 0.0)]
    p += [P("Office_Locker", 8.4, -10.48, repeat=[3, 0.9, 0])]                           # locker room
    p += [P("Office_Desk", 10.3, -5.0, 270), P("Office_Safe", 8.2, -5.9)]                 # manager
    p += accessible_wc(10.355, -2.9, 270, (9.6, -3.58, 0), (9.0, -0.343, 180, 9.0, -0.07), (10.68, -1.3, 270))
    # the staff aisle x 5.46..7.28 runs the whole staff block (z -10.74..0), closed from the store: every staff room,
    # the staff restroom included, opens into it, and it is itself behind a hinged door onto the counter floor
    # (user, 2026-09-28: the restroom within the aisle, the counter down to two registers to make room)
    p += [wall(5.46, z, 90) for z in (-10.01, -8.19, -6.37, -4.55, -2.73, -0.91)] + [swing(6.37, 0.0)]
    # the counter: TWO registers, a coffee machine and TWO hot cases; the cigarette wall behind it
    p += [P("Shop_Counter", 5.0, 2.57, 90),
          P("Shop_Register", 5.05, 1.2, 90, y=1.0, collide="none"),
          P("Shop_Register", 5.05, 2.8, 90, y=1.0, collide="none"),
          P("Shop_CoffeeMachine", 5.05, 3.9, 90, y=1.0, collide="none"),
          P("Shop_HotCase", 5.0, 5.56, 90), P("Shop_HotCase", 5.0, 6.46, 90),
          P("Shop_CigaretteCase", 10.515, 1.2, 270, repeat=[2, 0, 1.82])]
    # the self-serve row facing the front: a hot case, the coffee station (two machines), a hot case
    p += [P("Shop_HotCase", 5.9, 5.35), P("Shop_CoffeeStation", 7.3, 5.35), P("Shop_HotCase", 8.66, 5.35)]
    p += [P("Shop_ATM", 10.34, 7.4, 270), P("Shop_Copier", 10.39, 9.0, 270), P("Shop_BinStation", 8.0, 10.465, 180)]
    # ── back-left: the customer accessible restroom
    p += [half(-7.28, -10.465, 90), slide(-7.28, -9.1, 90, -1, wide=True), half(-7.28, -7.735, 90),
          wall(-10.01, -7.28), wall(-8.19, -7.28)]
    p += accessible_wc(-10.355, -10.2, 90, (-9.7, -10.74, 0), (-10.45, -8.1, 90, -10.71, -8.1), (-8.3, -10.74, 0))
    # ...the walk-in cooler ROOM (x -10.74..-7.28, z -7.28..1.82): ten drink doors are its front wall, shelves and a
    # freezer inside, a hinged door from the store room
    p += cooler_room([P("Shop_FridgeDoor", -6.88, -6.825, 90, repeat=[10, 0, 0.91])],
                     [P("Shop_StockShelf", -10.37, -5.3, 90), P("Shop_StockShelf", -10.37, -1.48, 90),
                      P("Kitchen_Fridge", -10.29, 0.9, 90)])
    p += [wall(-10.01, 1.82), swing(-8.19, 1.82)]
    # ...and the store room (delivery in the left wall), its door onto the sales floor
    p += [swing(-7.28, 2.73, 90), wall(-7.28, 4.55, 90), half(-7.28, 5.915, 90),
          wall(-10.01, 6.37), wall(-8.19, 6.37)]
    p += [P("Shop_StockShelf", -9.2, 5.9, 180)]
    # ── the sales floor: open bento cases along the back and the aisle wall, the upright freezer, gondolas,
    # magazines, a three-seat eat-in counter in the front-left corner
    p += [P("Shop_OpenCase", -5.29, -10.325, repeat=[6, 1.82, 0]),
          P("Shop_OpenCase", 4.975, -7.28, 270, repeat=[3, 0, 1.82]),
          P("Shop_FreezerCase", -6.805, 4.3, 90)]
    p += [P("Shop_Gondola", x, -5.0, 90, repeat=[3, 0, 2.9]) for x in (-4.2, -1.4, 1.4)]
    p += [P("Shop_Gondola", -4.5, 5.8, repeat=[2, 2.84, 0]),
          P("Shop_MagazineRack", -3.54, 10.47, 180, repeat=[3, 1.82, 0])]
    p += [P("Shop_EatInCounter", -9.83, 10.515, 180, repeat=[3, 0.91, 0]),
          P("Shop_Stool", -9.83, 9.9, repeat=[3, 0.91, 0])]
    # outside: three vending machines along the front
    p += [outside("Station_VendingMachine", -7.6, 11.3, repeat=[3, 1.1, 0])]
    return p


def restaurant():
    # 20.02 x 29.12 m, interior +-9.83 x +-14.38. Entrance front module 5 (x 0), staff exit back module 0 (x 9.1).
    p = []
    # ── back of house: the kitchen (x -9.83..5.46), store room / staff room / staff restroom (x 5.46..10.01)
    p += [wall(5.46, -13.65, 270), swing(5.46, -11.83, 270), wall(5.46, -10.01, 270), swing(5.46, -8.19, 270),
          slide(5.46, -6.37, 270, 1, wide=True), half(5.46, -5.005, 270)]
    for z in (-10.92, -7.28):
        p += [wall(6.37, z), wall(8.19, z), half(9.555, z)]
    # the serving wall: a pass window (lower wall, pass shelf, glass) over the service counter; the kitchen door
    p += [wall(-9.1, -4.55)]
    p += [P("Wall_PassWindow", x, -4.55, collide={"boxes": PASS_BOXES}) for x in (-7.28, -5.46, -3.64, -1.82)]
    p += [wall(0.0, -4.55), wall(1.82, -4.55), swing(3.64, -4.55), wall(5.46, -4.55), wall(7.28, -4.55),
          half(9.555, -4.55)]
    # store room
    p += [P("Shop_StockShelf", 7.15, -14.0), P("Station_Bin", 8.6, -12.0)]
    # staff room: lockers, a table
    p += [P("Office_Locker", 9.57, -10.2, 270, repeat=[2, 0, 0.9]), P("Rest_Table", 7.6, -8.8),
          P("Rest_Chair", 7.25, -9.55), P("Rest_Chair", 7.95, -9.55), P("Rest_Chair", 7.6, -8.05, 180)]
    # staff accessible restroom
    p += accessible_wc(9.445, -6.4, 270, (8.9, -7.22, 0), (7.6, -4.89, 180, 7.6, -4.63), (9.77, -5.3, 270))
    # the kitchen: cold store and shelves on the back wall, the cooking line down the left wall, prep in the middle,
    # the sinks by the back door side
    p += [P("Kitchen_Fridge", -8.9, -13.93), P("Kitchen_Fridge", -7.6, -13.93),
          P("Kitchen_Shelf", -5.5, -14.04), P("Kitchen_Sink", -2.5, -14.0), P("Kitchen_Sink", -0.6, -14.0),
          P("Kitchen_PrepTable", 2.0, -14.0)]
    p += [P("Kitchen_Grill", -9.46, z, 90) for z in (-11.0, -9.76)]
    p += [P("Kitchen_Fryer", -9.45, z, 90) for z in (-8.9, -8.3)]
    p += [P("Kitchen_PrepTable", x, -9.4) for x in (-5.4, -3.6)]
    p += [P("Kitchen_PrepTable", x, -10.15, 180) for x in (-5.4, -3.6)]
    p += [P("Kitchen_PrepTable", -5.46, -5.4, 180)]            # plating, behind the pass
    # the service counter in front of the pass, staff between them
    p += [P("Shop_Counter", -5.0, -2.5, 180), P("Shop_RegisterSmall", -3.0, -2.5, 180, y=1.0, collide="none")]
    # ── customer restrooms (user, 2026-09-28: TWO accessible rooms, not three -- the space is small):
    # x 3.64..7.28 and 7.28..10.01, z -1.82..2.73, SOLID sliding doors on the dining-room face
    p += [wall(x, -1.82) for x in (4.55, 6.37, 8.19)] + [half(9.555, -1.82)]
    p += [slide(4.55, 2.73, 0, 1, wide=True), wall(6.37, 2.73), slide(8.19, 2.73, 0, 1, wide=True), half(9.555, 2.73)]
    for x in (3.64, 7.28):
        p += [wall(x, -0.91, 90), wall(x, 0.91, 90), half(x, 2.275, 90)]
    p += accessible_wc(4.2, -1.375, 0, (4.9, -1.76, 0), (6.93, 0.6, 270, 7.2, 0.6), (3.7, 0.9, 90))
    p += accessible_wc(9.4, -1.375, 0, (8.7, -1.76, 0), (7.63, 0.6, 90, 7.36, 0.6), (9.77, 0.9, 270))
    # the sorted bins (tray return) beside the restrooms; meal-ticket machines (食券機) and an ATM by the entrance
    p += [P("Shop_BinStation", 3.3, 1.0, 270)]
    p += [P("Station_TicketMachine", 1.6, 14.105, 180, repeat=[2, 0.9, 0]), P("Shop_ATM", 3.6, 13.98, 180)]
    # ── the dining room: booths down both walls, tables in the middle
    for x, z0, n in ((-8.4, 0.0, 6), (8.4, 5.0, 4)):
        p += [P("Rest_BoothSofa", x, z0, repeat=[n, 0, 2.4]), P("Rest_Table", x, z0 + 0.8, repeat=[n, 0, 2.4]),
              P("Rest_BoothSofa", x, z0 + 1.6, 180, repeat=[n, 0, 2.4])]
    for x, z0, n in ((-3.2, 0.8, 5), (3.6, 5.5, 3)):
        p += [P("Rest_Table", x, z0, repeat=[n, 0, 3.0])]
        for dx in (-0.35, 0.35):
            p += [P("Rest_Chair", x + dx, z0 - 0.75, repeat=[n, 0, 3.0]),
                  P("Rest_Chair", x + dx, z0 + 0.75, 180, repeat=[n, 0, 3.0])]
    return p


def run_x(z, x0, x1, doors=None, yaw=0.0):
    """A partition along X at z from x0 to x1 in 1.82 m pieces (a half piece for the rest, the last one overlapping
    back to x1). `doors` = {x: prop}: a door prop (built by `swing` / `slide`) replaces the piece centred there."""
    out, x = [], x0
    doors = dict(doors or {})
    while x1 - x > 0.05:
        d = next((k for k in doors if x - 0.01 <= k - 0.91 <= x + 0.01), None)
        if d is not None:
            out.append(doors.pop(d))
            x += 1.82
        elif x1 - x >= 1.82:
            out.append(wall(x + 0.91, z, yaw))
            x += 1.82
        else:
            out.append(half(max(x + 0.455, x1 - 0.455), z, yaw))
            x += 0.91
    if doors:
        raise SystemExit("run_x: door(s) at %s are off the 1.82 m grid of the run %.2f .. %.2f" % (sorted(doors), x0, x1))
    return out


def run_z(x, z0, z1, doors=None):
    """A partition along Z at x from z0 to z1 (see run_x)."""
    out, z = [], z0
    doors = dict(doors or {})
    while z1 - z > 0.05:
        d = next((k for k in doors if z - 0.01 <= k - 0.91 <= z + 0.01), None)
        if d is not None:
            out.append(doors.pop(d))
            z += 1.82
        elif z1 - z >= 1.82:
            out.append(wall(x, z + 0.91, 90))
            z += 1.82
        else:
            out.append(half(x, max(z + 0.455, z1 - 0.455), 90))
            z += 0.91
    if doors:
        raise SystemExit("run_z: door(s) at %s are off the 1.82 m grid of the run %.2f .. %.2f" % (sorted(doors), z0, z1))
    return out


def supermarket():
    """食品スーパー (user, 2026-09-28: "a larger market that combines kitchen and konbini features, the food made in
    the kitchen, larger supplies, a larger backyard for fulfilment"): 32.76 x 40.04 m, interior +-16.2 x +-19.84. The
    front is the SALES floor, the back 10.7 m the バックヤード (backyard). Entrances front modules 4 and 13 (x -+8.19);
    receiving doors back modules 13-14 (x -8.19, -10.01) into the 荷受け (receiving) area; the staff exit back module 0
    (x 15.47) at the end of the STAFF AISLE. The loading yard (荷捌き場) is outside, the SupermarketSite composite."""
    p = []
    ZB = -9.1                       # the backyard's front wall
    ZC = -17.84                     # the back corridor's wall (supplies: receiving -> the corridor -> every room)
    # ── the backyard: rooms between the corridor and the sales floor
    p += run_x(ZC, -7.28, 14.56, {-4.55: swing(-4.55, ZC, 180), -0.91: swing(-0.91, ZC, 180),
                                  2.73: swing(2.73, ZC, 180), 8.19: swing(8.19, ZC, 180)}, 180)
    for x in (-7.28, -3.64, 0.0, 5.46, 10.92):
        p += run_z(x, ZC, ZB)
    p += [swing(14.56, -16.93, 90), wall(14.56, -15.11, 90), swing(14.56, -13.29, 90), half(14.56, -11.925, 90),
          slide(14.56, -10.56, 90, 1, wide=True), half(14.56, -9.555, 90)]
    # the backyard's front wall onto the sales floor: receiving (a wide swing door) | the cooler's drink doors |
    # freezer | meat & fish behind its open cases | the deli kitchen's pass windows and door | the staff block
    p += run_x(ZB, -16.2, -7.28, {-11.65: P("Wall_PartitionDoorWide", -11.65, ZB, 0, door={"w": 1.0, "h": 2.0},
                                            collide={"boxes": WIDE_BOXES})})
    p += [P("Shop_FridgeDoor", -6.825, ZB + 0.4, 180, repeat=[4, 0.91, 0])]
    p += run_x(ZB, -3.64, 5.46)
    p += [P("Wall_PassWindow", x, ZB, collide={"boxes": PASS_BOXES}) for x in (6.37, 8.19)]
    p += [swing(10.01, ZB)]
    p += run_x(ZB, 10.92, 14.56)
    p += [swing(15.38, ZB)]                                                     # the staff aisle onto the floor
    # receiving (荷受け・検品): roll cages, pallets, the check-in desk, shelves
    p += [P("Warehouse_RollCage", -15.6, -18.8, 0, repeat=[4, 0.95, 0]),
          P("Warehouse_Pallet", -15.4, -13.2, 0, repeat=[2, 0, 1.5]),
          P("Shop_StockShelf", -15.85, -16.2, 90), P("Office_Desk", -9.5, -12.6, 90)]
    # the walk-in cooler (its front is the drink doors) and freezer
    p += [P("Shop_StockShelf", -6.85, -13.5, 90), P("Kitchen_Fridge", -3.95, -12.5, 270),
          P("Shop_FreezerCase", -2.2, -17.3, 180), P("Shop_StockShelf", -1.82, -10.55, 0)]
    # 精肉・鮮魚 (meat and fish): prep, sinks, a fridge; the open cases on the floor side
    p += [P("Kitchen_PrepTable", 1.3, -13.5, 90), P("Kitchen_PrepTable", 4.1, -13.5, 90),
          P("Kitchen_Sink", 4.3, -17.2, 180), P("Kitchen_Fridge", 0.7, -17.35, 180)]
    p += [P("Shop_OpenCase", x, ZB + 0.5, 0) for x in (0.91, 2.73, 4.55)]
    # 惣菜 (the deli kitchen: the food is made here, handed through the pass windows to the deli counters)
    p += [P("Kitchen_Grill", x, -17.45, 180) for x in (5.95, 7.15)]
    p += [P("Kitchen_Fryer", x, -17.45, 180) for x in (9.6, 10.25)]
    p += [P("Kitchen_PrepTable", 7.3, -13.3, 0), P("Kitchen_PrepTable", 7.3, -12.4, 180),
          P("Kitchen_Sink", 10.5, -13.3, 270), P("Kitchen_Fridge", 5.95, -13.0, 90)]
    p += [P("Shop_DeliCounter", x, ZB + 0.55, 0) for x in (6.37, 8.19)]
    # the staff block off the staff aisle: office (safe), lockers, the staff accessible restroom
    p += run_x(-14.8, 10.92, 14.56) + run_x(-11.95, 10.92, 14.56)
    p += [P("Office_Desk", 12.5, -17.3, 180), P("Office_Safe", 11.3, -15.2, 0), P("Office_Cabinet", 13.9, -17.5, 180)]
    p += [P("Office_Locker", 11.4, -12.35, 180, repeat=[3, 0.95, 0])]
    p += accessible_wc(11.3, -10.0, 90, (11.0, -11.85, 0), (13.9, -9.6, 0, 13.9, -9.25), (11.0, -9.25, 180))
    # ── the sales floor
    # produce (青果) along the left wall and two islands
    p += [P("Shop_ProduceTable", -15.6, z, 90) for z in (-6.5, -4.6, -2.7, -0.8, 1.1, 3.0)]
    p += [P("Shop_ProduceTable", -12.0, z, 0) for z in (-3.5, -0.5)]
    # gondola runs (a 2.5 m aisle), the frozen island, open cases (dairy, drinks) along the right wall
    p += [P("Shop_Gondola", x, -5.5, 90, repeat=[3, 0, 2.88]) for x in (-8.5, -5.3, -2.1, 1.1, 4.3, 7.5)]
    p += [P("Shop_FreezerCase", 11.2, 0.0, 90), P("Shop_FreezerCase", 12.12, 0.0, 270)]
    p += [P("Shop_OpenCase", 15.77, z, 270) for z in (-5.3, -3.48, -1.66, 0.16, 1.98)]
    # the konbini corner (front right): the service counter with two registers, hot snacks, coffee, ATM, copier,
    # an eat-in counter along the glass
    p += [P("Shop_Counter", 14.0, 7.5, 270),
          P("Shop_Register", 14.05, 6.2, 270, y=1.0, collide="none"),
          P("Shop_Register", 14.05, 8.8, 270, y=1.0, collide="none"),
          P("Shop_HotCase", 11.4, 5.3, 0), P("Shop_HotCase", 12.3, 5.3, 0),
          P("Shop_CoffeeStation", 12.0, 12.0, 90),
          P("Shop_ATM", 15.7, 12.8, 270), P("Shop_Copier", 15.75, 14.5, 270)]
    p += [P("Shop_EatInCounter", 10.9 + 0.91 * k, 19.4, 180) for k in range(4)]
    p += [P("Shop_Stool", 10.9 + 0.91 * k, 18.8) for k in range(4)]
    # the checkouts (six lanes), the bagging tables after them, the carts by the left entrance
    p += [P("Shop_Checkout", -5.5 + 2.2 * k, 11.5) for k in range(6)]
    p += [P("Shop_BaggingTable", x, 14.9) for x in (-4.4, -1.1, 2.2)]
    p += [P("Shop_CartRow", -9.95, 16.9)]
    # the customer restrooms (two accessible rooms) in the front-left corner, behind solid front modules
    # (two rooms 2.73 wide; each sliding leaf runs over the solid half between the two doors)
    p += [slide(-15.29, 15.2, 180, -1, wide=True), half(-13.925, 15.2, 180), half(-13.015, 15.2, 180),
          slide(-11.65, 15.2, 180, 1, wide=True)]
    p += run_z(-13.47, 15.2, 19.84) + run_z(-10.74, 15.2, 19.84)
    p += accessible_wc(-15.84, 19.2, 90, (-15.3, 19.84, 0), (-14.6, 19.56, 180, -14.6, 19.8), (-13.53, 17.3, 270))
    p += accessible_wc(-11.1, 19.2, 270, (-11.7, 19.84, 0), (-12.4, 19.56, 180, -12.4, 19.8), (-13.41, 17.3, 90))
    # outside: two vending machines and the sorted bins by the right entrance
    p += [outside("Station_VendingMachine", 12.0, 20.4, repeat=[2, 1.1, 0]), outside("Shop_BinStation", 4.0, 20.3)]
    return p



PLANS = {"KonbiniS": konbini_s, "KonbiniL": konbini_l, "FamilyRestaurant": restaurant, "Supermarket": supermarket}
#: the exterior doors each plan was drawn for (building_types.json `doors`): a door moved there must stay clear of
#: the rooms, which the layout's door check asserts
DOORS = {"KonbiniS": {"front": [5], "back": [0]},
         "KonbiniL": {"front": [7], "back": [2], "left": [8]},
         "FamilyRestaurant": {"front": [5], "back": [0]},
         "Supermarket": {"front": [4, 13], "back": [0, 13, 14]}}
