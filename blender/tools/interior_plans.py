"""The SEED plans of the mission buildings (user, 2026-09-28), laid out ONCE into kits/interiors/<Id>.blend by
blender/tools/build_interior_blends.py; from then on the .blend is the artist's. Every building is a PLACEHOLDER of the
right size and room programme: an artist remodels the shell and replaces the library fittings (kits/interiors/
ARTIST_NOTES.md lists what to replace; the game only assumes the frame, the doors, the lifts and the markers).

Frame: Blender metres, Z up, origin on the ground at the PLOT centre (island_civic_sites.py's plots), the STREET -Y.

Sizes (Japanese practice; the user: "base on Japan standard measurements, but compact if needed, keep the essential
portions"; "small police / fire station is one floor, the larger two; the hospital is medium / large"):

* 交番 (Koban, the SMALL police station): 6 x 7 m, one storey 3.4 m -- a 見張所 (front office) with the public
  counter, a 休憩室 (rest room) with the pistol locker (LIGHT weapons), a toilet, a back door. Plot 8 x 10.
* 警察署 (PoliceStation, the LARGE one): 30 x 20 m, two storeys (4.2 + 3.8 m) -- public counters and waiting, two
  interrogation rooms, holding cells, the ARMOURY (long-gun racks, pistol lockers, shields: the complete one), the
  duty room; upstairs the criminal-investigation office, the chief's office, a meeting room, a locker room; two
  stairs (二方向避難) and a lift. Plot 40 x 45 (35 x 40 west).
* 消防出張所 (FireBranch, the SMALL fire station): 16 x 18 m, one storey 5.2 m -- two apparatus bays (a pumper, an
  ambulance), gear racks, the office, the crew room with kitchen, bunks, shower / WC, the equipment store. Plot 20 x 25.
* 消防署 (FireStation, the LARGE one): 32 x 21 m, two storeys (5.4 m apparatus floor + 4.0) -- four bays (a ladder
  truck, two pumpers, an ambulance), the office with the counter, lockers, the store; upstairs bunk rooms, the
  briefing room, the prevention office, the chief's office; two stairs, a roof stair house; the 訓練塔 behind.
  Plot 40 x 50.
* 病院 (Hospital, one type, medium / large, compact): 44 x 28 m, three storeys (4.5 + 4.0 + 4.0) + a roof HELIPAD --
  entrance hall, reception / pharmacy, four consulting rooms, X-ray, the 救急 (ER) with its own ambulance door and
  three bays; upstairs two operating theatres, the ICU; the ward floor (nurse station, four 4-bed rooms, private
  rooms). A bed lift to the roof and two stairs. Plots 55 x 60 and 100 x 100.
* オフィスビル (OfficeHQ): 24 x 18 m, four storeys (4.2 + 3 x 3.8): lobby with security, a lift (5 stops, the roof
  included? no: the roof is by the stair house), two stairs, 島型 open offices, meeting rooms, a server room, the
  president's office and boardroom on the top floor. Not placed on the island: a level designer's building.
* リゾートホテル (ResortHotel): 48 x 18 m, four storeys (4.5 + 3 x 3.2): the lobby, front desk, restaurant and
  kitchen on the ground floor, the pool terrace on the sea side (-Y), guest rooms along a corridor above, a lift and
  two stairs. Sits on the resort reserves (70 x 60).
* 倉庫 + ヤード (WarehouseYard): a 40 x 24 x 9 m warehouse (pallet racks, forklifts, three open loading docks, a
  two-storey office in its corner up a stair) on a fenced yard with a trailer at the dock and a guard house.
"""
import interior_kit as IK
from interior_kit import Opening

NOTE = ("A mission building (blender/tools/build_interior_blends.py, seed blender/tools/interior_plans.py): a "
        "PLACEHOLDER shell and fit-out at its real Japanese size -- remodel freely. Keep the frame (origin = plot "
        "centre on the ground, street -Y), the floor levels, and move the Empties with what they belong to: DOOR_ "
        "(interior door, arrow OUT of the room), EXIT_ (outer door, arrow out of the building), LIFT_ (a lift: shaft "
        "floor centre at the low stop; stops / faces), MARK_ (a mission marker: kind weapon / spawn / cover ...). "
        "Keep 1.2 m clear both sides of every door. After editing: tools/building_kit/build_buildings.sh.")

EXT_T = 0.2
PART_T = 0.12


# ── helpers ─────────────────────────────────────────────────────────────────────────────────────────────────────

def openings(b, axis, c, z, doors):
    """doors: [(u, out, w, style, kind, h, sill)] -> Openings. kind 'door' (a DOOR_), 'exit' (an EXIT_), 'open' (a
    plain gap: an archway, an apparatus bay), 'fire' (a stair's fire door: a DOOR_ swing). `sill` (optional) raises
    the doorway above the wall's z -- a door onto a raised floor in a wall that starts at the ground."""
    ops = []
    for d in doors:
        u, out = d[0], d[1]
        w = d[2] if len(d) > 2 else IK.DOOR_W
        style = d[3] if len(d) > 3 else "swing"
        kind = d[4] if len(d) > 4 else "door"
        h = d[5] if len(d) > 5 else IK.DOOR_H
        zd = z + (d[6] if len(d) > 6 else 0.0)
        if kind == "open":
            ops.append(Opening(u - w / 2, u + w / 2, zd, zd + h))
        else:
            ops.append(b.door(axis, c, u, zd, out, w=w, h=h, style=style, exit=(kind == "exit")))
    return ops


def ext(b, x0, y0, x1, y1, z, h, facade, sides=None, t=EXT_T, inner="MI_Plaster"):
    """The four outer walls of one storey (z .. z + h, t thick, INSIDE the footprint), facade outside, plaster inside.
    sides: {'f'|'b'|'l'|'r': (doors, windows)} -- doors as `openings`, windows as Openings."""
    sides = sides or {}
    for s, axis, c, a0, a1, sgn in (("f", "x", y0 + t / 2, x0, x1, -1), ("b", "x", y1 - t / 2, x0, x1, 1),
                                    ("l", "y", x0 + t / 2, y0 + t, y1 - t, -1), ("r", "y", x1 - t / 2, y0 + t, y1 - t, 1)):
        doors, wins = sides.get(s, ((), ()))
        ops = openings(b, axis, c, z, doors) + list(wins)
        b.wall(axis, c, a0, a1, z, h, t, inner, mat_out=facade, out_sign=sgn, ops=ops, group="Facade")


def part(b, axis, c, a0, a1, z, h, doors=(), wins=(), t=PART_T, mat="MI_Plaster", group=None):
    """An interior partition, floor to the slab above."""
    ops = openings(b, axis, c, z, doors) + list(wins)
    b.wall(axis, c, a0, a1, z, h, t, mat, ops=ops, group=group or "Walls_%g" % z)


def glass_part(b, axis, c, a0, a1, z, h, doors=()):
    """A glazed partition (an office's meeting room, a nurse station's window): a 0.9 m solid base, glass to 2.4 m."""
    ops = openings(b, axis, c, z, doors)
    glass = []
    cur = a0
    for o in sorted(ops, key=lambda o: o.u0):
        if o.u0 - cur > 0.3:
            glass.append(Opening(cur + 0.1, o.u0 - 0.1, z + 0.9, z + 2.4, glass="MI_GlassClear", frame="MI_PaintedMetal"))
        cur = o.u1
    if a1 - cur > 0.3:
        glass.append(Opening(cur + 0.1, a1 - 0.1, z + 0.9, z + 2.4, glass="MI_GlassClear", frame="MI_PaintedMetal"))
    b.wall(axis, c, a0, a1, z, h, PART_T, "MI_Plaster", ops=ops + glass, group="Walls_%g" % z)


def band_windows(b, a0, a1, z, h, every=3.6, w=2.0, skip=(), sill=0.9, head=None, glass="MI_GlassClear"):
    return b.windows(a0, a1, z, every=every, w=w, sill=sill, head=head if head is not None else min(h - 0.5, 2.4),
                     skip=skip, glass=glass)


def roof(b, x0, y0, x1, y1, z, holes=(), parapet=1.1, mat="MI_ConcreteSmooth", units=0):
    b.slab(x0, y0, x1, y1, z, mat, holes=holes, group="Roof")
    b.parapet(x0, y0, x1, y1, z, parapet, mat=mat)
    for i in range(units):
        cx = x0 + 2.5 + i * 2.6
        b.box("Roof", (cx, y1 - 3.5, z), (cx + 1.8, y1 - 2.3, z + 1.3), "MI_PlasticWhite")


def stair_house(b, x0, y0, x1, y1, z, door_side="s", h=2.8):
    """塔屋: the stair's roof house over its well (x0..x1, y0..y1) with a door onto the roof on `door_side`'s near
    strip. The roof slab keeps its hole over the well; the house has its own roof."""
    t = EXT_T
    doors = {"s": ((x0 + x1) / 2, -1)}
    for s, axis, c, a0, a1, sgn in (("f", "x", y0 - t / 2, x0 - t, x1 + t, -1), ("b", "x", y1 + t / 2, x0 - t, x1 + t, 1),
                                    ("l", "y", x0 - t / 2, y0, y1, -1), ("r", "y", x1 + t / 2, y0, y1, 1)):
        ops = []
        if (s == "f" and door_side == "s"):
            ops = openings(b, axis, c, z, [((x0 + x1) / 2, -1, 0.9, "swing", "door")])
        b.wall(axis, c, a0, a1, z, h, t, "MI_Plaster", mat_out="MI_ConcreteSmooth", out_sign=sgn, ops=ops, group="Roof")
    b.box("Roof", (x0 - t, y0 - t, z + h), (x1 + t, y1 + t, z + h + 0.2), "MI_ConcreteSmooth")


def paint_bays(b, x0, n, pitch, y0, y1, mat="MI_PaintWhite"):
    """Parking bays painted on the lot (2.5 x 5.0 m, Japan's 駐車場 standard)."""
    for k in range(n + 1):
        x = x0 + k * pitch
        b.box("Site", (x - 0.05, y0, 0.0), (x + 0.05, y1, 0.012), mat)


def apron(b, x0, y0, x1, y1, mat="MI_ConcreteSmooth"):
    b.box("Site", (x0, y0, -0.03), (x1, y1, 0.01), mat)


def sign(b, x0, x1, y, z0, z1, mat="MI_Sign"):
    b.box("Facade", (x0, y - 0.15, z0), (x1, y, z1), mat)


def chairs_around(b, x, y, n_side=2, dx=0.6, gap=0.85, piece="Office_Chair", z=0.0):
    """Chairs on both long sides of a table / desk island at (x, y) running along X, on the floor at z."""
    for i in range(n_side):
        cx = x + (i - (n_side - 1) / 2) * dx * 2
        b.put(piece, cx, y - gap, 0.0, z=z)
        b.put(piece, cx, y + gap, 180.0, z=z)


# ── 交番: the SMALL police station, one storey, LIGHT weapons only ────────────────────────────────────────────────

def koban(b):
    x0, y0, x1, y1 = -3.0, -4.0, 3.0, 3.0
    H = 3.4
    apron(b, -3.5, -5.0, 3.5, 3.4)                          # the front of the plot only: the neighbours stand close
    b.slab(x0, y0, x1, y1, 0.0, "MI_Terrazzo")
    ext(b, x0, y0, x1, y1, 0.0, H + 0.2, "MI_TileWhite", {
        "f": ([(-1.2, -1, 1.8, "slide", "exit")], [b.window(1.6, 0.0, 1.6, 0.9, 2.4)]),
        "r": ([(0.15, 1, 0.9, "swing", "exit")], []),
        "l": ((), [b.window(-2.2, 0.0, 1.2, 0.9, 2.2)]),
    })
    roof(b, x0, y0, x1, y1, H + 0.2)
    # the red lamp (赤色灯) over the door and the KOBAN board
    b.box("Facade", (-1.45, y0 - 0.45, 2.75), (-0.95, y0, 3.15), "MI_SignRed")
    sign(b, 0.3, 2.8, y0, 2.6, 3.2)
    b.box("Facade", (x0, y0 - 1.0, 2.55), (x1, y0, 2.7), "MI_PaintedMetal")         # the door canopy
    # 見張所 (front office) y -3.8 .. -0.6
    part(b, "x", -0.6, x0 + EXT_T, x1 - EXT_T, 0.0, H,
         doors=[(1.8, -1, 0.9, "swing", "door")])
    b.put("Office_Desk", 0.0, -2.3, 0.0)
    b.put("Office_Chair", 0.0, -1.65, 180.0)
    b.put("Station_Bench", -2.5, -2.3, 90.0)
    b.put("Office_Cabinet", 2.5, -1.4, 270.0)
    # 休憩室 (rest room) x -2.8 .. 0.8, y -0.6 .. 2.8, with the PISTOL LOCKER (the light armoury)
    part(b, "y", 0.8, -0.6, y1 - EXT_T, 0.0, H, doors=[(0.15, 1, 0.9, "swing", "door")])
    b.put("Police_GunLocker", -1.8, 2.5, 0.0)
    b.put("Office_Locker", 0.2, 2.5, 0.0)
    b.put("Rest_Table", -1.3, 0.6, 0.0)
    b.put("Rest_Chair", -1.65, -0.15, 0.0)
    b.put("Rest_Chair", -0.95, -0.15, 0.0)
    b.mark("weapon", -2.0, 1.9, 0.0, 180.0, weapon="PIS1", note="the koban's pistol locker: light weapons only")
    b.mark("weapon", -1.6, 1.9, 0.0, 180.0, weapon="PIS1")
    b.mark("spawn", 0.0, -1.2, 0.0, 180.0, team="police")
    b.mark("spawn", -1.0, 1.5, 0.0, 0.0, team="police")
    # toilet x 0.8 .. 2.8, y 0.9 .. 2.8
    part(b, "x", 0.9, 0.8, x1 - EXT_T, 0.0, H, doors=[(1.8, -1, 0.8, "swing", "door")])
    b.put("WC_Toilet", 1.8, 2.43, 0.0)
    b.put("WC_Basin", 2.5, 1.3, 270.0)
    return {"note": "交番: the small police station, one storey; its armoury is one pistol locker (MARK_weapon x2)."}


# ── 消防出張所: the SMALL fire station, one storey ──────────────────────────────────────────────────────────────────

def fire_branch(b):
    x0, y0, x1, y1 = -8.0, -10.0, 8.0, 8.0
    H = 5.2
    apron(b, -10.0, -12.5, 10.0, 12.5)
    b.slab(x0, y0, x1, y1, 0.0, "MI_ConcreteSmooth")
    bays = [(-5.9, -1, 3.6, "", "open", 4.2), (-2.0, -1, 3.6, "", "open", 4.2)]
    ext(b, x0, y0, x1, y1, 0.0, H + 0.2, "MI_TileWhite", {
        "f": (bays + [(4.5, -1, 1.8, "slide", "exit")], [b.window(1.6, 0.0, 1.6, 0.9, 2.4)]),
        "b": ([(-3.8, 1, 0.9, "swing", "exit")], []),
        "r": ((), band_windows(b, y0 + 1.0, y1 - 1.0, 0.0, H, every=3.4, skip=())),
    })
    roof(b, x0, y0, x1, y1, H + 0.2, units=2)
    for u in (-5.9, -2.0):                                               # the raised shutters' housings
        b.box("Facade", (u - 1.9, y0 - 0.35, 4.25), (u + 1.9, y0, 4.8), "MI_CraneRed")
    b.box("Facade", (x0, y0 - 0.2, 4.9), (x1, y0, 5.3), "MI_CraneRed")     # the red band
    sign(b, 2.5, 7.0, y0 - 0.2, 3.0, 3.6, "MI_SignRed")
    # apparatus bays x -7.8 .. 0, y -9.8 .. 1.0
    b.mark("vehicle", -5.9, -4.0, 0.0, 180.0, vehicle="FIE1")
    b.mark("vehicle", -2.2, -4.9, 0.0, 180.0, vehicle="AMB1")
    part(b, "x", 1.0, x0 + EXT_T, 0.0, 0.0, H, doors=[(-4.0, 1, 2.0, "", "open", 2.4)])
    b.put("Fire_GearRack", -7.0, 0.6, 0.0)
    b.put("Fire_GearRack", -1.3, 0.6, 0.0)
    b.mark("spawn", -4.0, -8.5, 0.0, 180.0, team="fire")
    # equipment store behind the bays, the back door
    b.put("Shop_StockShelf", -6.2, 7.4, 0.0)
    b.put("Shop_StockShelf", -1.6, 7.4, 0.0)
    b.put("Warehouse_Pallet", -6.9, 3.2, 0.0)
    # the dividing wall bays | office side, x = 0
    part(b, "y", 0.0, y0 + EXT_T, y1 - EXT_T, 0.0, H,
         doors=[(-7.0, -1, 0.9, "swing", "door"), (-1.0, -1, 0.9, "swing", "door")])
    # 事務室 (office) x 0 .. 7.8, y -9.8 .. -3.5
    part(b, "x", -3.5, 0.0, x1 - EXT_T, 0.0, H, doors=[(6.0, 1, 0.9, "swing", "door")])
    b.put("Office_Reception", 4.5, -7.8, 0.0)
    b.put("Office_Desk", 2.2, -5.0, 0.0)
    b.put("Office_Desk", 7.0, -5.0, 0.0)
    b.put("Office_Chair", 2.2, -4.35, 180.0)
    b.put("Office_Chair", 7.0, -4.35, 180.0)
    b.put("Office_Cabinet", 0.45, -5.0, 90.0)
    b.mark("spawn", 3.4, -6.5, 0.0, 0.0, team="fire")
    # 待機室 (crew room, kitchen) x 0 .. 7.8, y -3.5 .. 2.0
    part(b, "x", 2.0, 0.0, x1 - EXT_T, 0.0, H,
         doors=[(2.2, -1, 0.9, "swing", "door"), (6.5, -1, 0.8, "swing", "door")])
    b.put("Rest_Table", 3.8, -0.8, 0.0)
    for dx in (-0.35, 0.35):
        b.put("Rest_Chair", 3.8 + dx, -1.55, 0.0)
        b.put("Rest_Chair", 3.8 + dx, -0.05, 180.0)
    b.put("Kitchen_Sink", 7.35, -0.6, 270.0)
    b.put("Kitchen_Fridge", 7.2, -2.6, 270.0)
    b.put("Office_Sofa", 1.0, 0.4, 90.0)
    # 仮眠室 (bunks) x 0 .. 5, y 2 .. 7.8 ; shower / WC x 5 .. 7.8
    part(b, "y", 5.0, 2.0, y1 - EXT_T, 0.0, H)
    b.put("Fire_Bunk", 1.4, 5.0, 90.0)
    b.put("Fire_Bunk", 3.6, 5.0, 90.0)
    b.put("Office_Locker", 2.5, 7.5, 0.0)
    b.put("WC_Toilet", 6.3, 7.43, 0.0)
    b.put("WC_Basin", 7.55, 4.0, 90.0)
    return {"note": "消防出張所: the small fire station, one storey, two bays (a pumper and an ambulance)."}


# ── 警察署: the LARGE police station, two storeys, the complete ARMOURY ───────────────────────────────────────────

def police_station(b):
    X0, X1, Y0, Y1 = -15.0, 15.0, -10.0, 7.4
    F1, F2, TOP = 0.0, 4.2, 8.0
    CF, CB = -1.0, 0.8                      # the corridor's two walls (a 1.8 m double-loaded corridor)
    xi0, xi1 = X0 + EXT_T, X1 - EXT_T
    yf, yb = Y0 + EXT_T, Y1 - EXT_T
    apron(b, -17.5, -20.0, 17.5, 20.0)
    paint_bays(b, -12.5, 10, 2.5, 10.0, 15.0)                 # the rear car park (patrol cars, staff)
    # THE COMPOUND (user, 2026-09-29: a large station stands inside a fence, its entrances watched): a steel fence
    # on a concrete upstand round the plot; the PUBLIC gate in front of the entrance with the 立番 booth (the
    # standing guard's post) beside it; the VEHICLE gate on the west side to the rear car park, under a barrier,
    # with its own guard booth. Suspects are brought in through the west side door (護送口), under its canopy,
    # straight to the holding cells (留置場) behind the duty desk.
    import interior_plans_jp as JP
    JP.fence(b, -17.3, -19.8, 17.3, 19.8, [("f", -9.0, 5.0), ("l", 12.5, 5.0)])
    JP.guard_post(b, -14.4, -19.5, -11.9, -16.5, door_side="b")
    b.mark("spawn", -12.8, -18.2, 0.0, 180.0, team="police", note="立番: the standing guard at the public gate")
    JP.guard_post(b, -17.0, 15.6, -14.0, 18.2, door_side="r")
    b.mark("spawn", -16.0, 13.0, 0.0, 270.0, team="police", note="the vehicle gate's guard")
    b.box("Site", (-17.1, 9.6, 0.0), (-16.8, 9.9, 1.1), "MI_PaintYellow")               # the barrier's post
    b.box("Site", (-17.05, 9.65, 1.1), (-16.85, 9.85, 5.2), "MI_PaintWhite")            # its arm, raised
    b.box("Site", (-17.3, 15.2, 0.0), (-17.15, 19.6, 2.0), "MI_Steel")                   # the sliding gate, open
    b.box("Site", (-17.5, -2.0, 3.0), (-15.0, 1.8, 3.2), "MI_PaintedMetal")             # the 護送口 canopy
    b.mark("vehicle", -13.75, 17.5, 0.0, 90.0, vehicle="CRT1", faction="police", note="the prisoner-transport bay")
    for (x, y) in ((-17.0, -19.5), (17.0, -19.5), (-17.0, 19.5), (17.0, 19.5), (-6.2, -19.5)):
        JP.camera(b, x, y, 2.0)
    for x, vid in ((-11.25, "POC1"), (-8.75, "POC1"), (-6.25, "MPC1")):
        b.mark("vehicle", x, 12.5, 0.0, 180.0, vehicle=vid, faction="police")
    # stairs (B at the west end, A in the middle, which goes on to the roof) and the lift
    wellB = (xi0, CB + 0.06, -12.06, yb)
    wellA = (3.66, CB + 0.06, 6.34, yb)
    holeB = b.ustair(*wellB, F1, F2 - F1, near="s")
    holeA = b.ustair(*wellA, F1, F2 - F1, near="s")
    b.ustair(*wellB, F2, TOP - F2, near="s", cap=True)
    holeA2 = b.ustair(*wellA, F2, TOP - F2, near="s")
    shaft = b.lift(7.55, 1.92, 1.8, 1.8, [F1, F2], faces=1, turned=True)
    b.slab(X0, Y0, X1, Y1, F1, "MI_Terrazzo")
    b.slab(X0, Y0, X1, Y1, F2, "MI_Terrazzo", holes=[holeB, holeA, shaft])
    roof(b, X0, Y0, X1, Y1, TOP, holes=[holeA2], units=5)
    stair_house(b, wellA[0], wellA[1], wellA[2], wellA[3], TOP)
    b.box("Roof", (11.0, 4.0, TOP), (11.3, 4.3, TOP + 12.0), "MI_Steel")                  # the radio mast
    # ── the shell
    hall_skip = (-9.0,)
    ext(b, X0, Y0, X1, Y1, F1, F2 - F1, "MI_TileBrown", {
        "f": ([(-9.0, -1, 1.8, "slide", "exit")],
              band_windows(b, xi0 + 0.5, 6.0, F1, 4.0, every=3.0, w=1.8, skip=hall_skip, head=2.6)),
        "l": ([(-0.1, -1, 1.2, "swing", "exit")], []),
        "r": ([(-0.1, 1, 1.2, "swing", "exit")], []),
        "b": ((), band_windows(b, -3.0, 3.0, F1, 4.0, every=3.6, w=1.6, head=2.4)),
    })
    ext(b, X0, Y0, X1, Y1, F2, TOP - F2, "MI_TileBeige", {
        "f": ((), band_windows(b, xi0 + 0.5, xi1 - 0.5, F2, 3.6, every=3.0, w=2.0)),
        "b": ((), band_windows(b, -12.0, 3.0, F2, 3.6, every=3.0, w=1.6) +
              band_windows(b, 6.5, 14.5, F2, 3.6, every=3.0, w=1.6)),
    })
    b.box("Facade", (-12.0, Y0 - 3.0, 3.4), (-6.0, Y0, 3.6), "MI_PaintedMetal")          # the entrance canopy
    sign(b, -11.0, -7.0, Y0 - 3.0, 3.6, 4.1)
    b.box("Facade", (-9.6, Y0 - 0.2, 4.6), (-8.4, Y0, 5.8), "MI_Gold")                 # the emblem (旭日章)
    for x in (-11.8, -6.2):
        b.box("Facade", (x - 0.15, Y0 - 0.35, 2.6), (x + 0.15, Y0 - 0.05, 3.1), "MI_SignRed")   # 赤色灯

    # ── F1 corridor walls
    part(b, "x", CF, xi0, xi1, F1, 4.0, doors=[(-3.6, 1), (1.5, 1), (8.2, 1), (12.6, 1)])
    part(b, "x", CB, xi0, xi1, F1, 4.0, doors=[(-13.4, -1, 1.0, "swing", "door"), (-7.8, -1), (-2.8, -1),
                                             (0.8, -1), (5.0, -1, 1.0, "swing", "door"),
                                             (7.55, -1, 1.0, "", "open", 2.1), (10.5, -1), (13.4, -1, 1.0)])
    # front row: the public hall and counters | the duty office | the ARMOURY | the equipment room
    part(b, "y", -3.0, yf, CF, F1, 4.0)
    part(b, "y", 6.0, yf, CF, F1, 4.0)
    part(b, "y", 10.4, yf, CF, F1, 4.0)
    b.put("Shop_Counter", -12.0, -5.2, 0.0)
    b.put("Shop_Counter", -6.9, -5.2, 0.0)
    b.put("Hosp_WaitingBench", -12.6, -8.3, 180.0)
    b.put("Hosp_WaitingBench", -5.4, -8.3, 180.0)
    b.put("Office_DeskIsland", -9.5, -3.0, 0.0)
    chairs_around(b, -9.5, -3.0, 2, 0.6, 0.85)
    b.put("Office_Cabinet", -14.5, -2.0, 90.0)
    b.mark("spawn", -9.0, -7.5, F1, 0.0, team="civilian")
    b.put("Office_DeskIsland", -0.2, -6.5, 0.0)
    chairs_around(b, -0.2, -6.5, 2, 0.6, 0.85)
    b.put("Office_DeskIsland", 3.3, -6.5, 0.0)
    chairs_around(b, 3.3, -6.5, 2, 0.6, 0.85)
    b.put("Office_Locker", -2.4, -9.5, 0.0, repeat=(4, 0.95, 0.0))
    b.put("Office_Cabinet", 5.6, -3.5, 270.0)
    b.mark("spawn", 1.5, -4.0, F1, 0.0, team="police")
    # the ARMOURY (武器庫): long-gun racks, riot shields, pistol lockers, ammunition shelves -- the complete one
    b.put("Police_GunRack", 7.25, -9.45, 0.0)
    b.put("Police_GunRack", 9.2, -9.45, 0.0)
    b.put("Police_ShieldRack", 6.4 + 0.3, -5.4, 90.0)
    b.put("Police_GunLocker", 10.0, -6.8, 270.0)
    b.put("Police_GunLocker", 10.0, -5.6, 270.0)
    b.put("Shop_StockShelf", 10.0, -3.2, 270.0)
    for i, w in enumerate(("ASR1", "ASR2", "SHG1", "SMG1")):
        b.mark("weapon", 6.8 + i * 0.95, -8.7, F1, 180.0, weapon=w)
    for i, w in enumerate(("SNR1", "SHG1", "SMG1", "PIS1")):
        b.mark("weapon", 6.8 + i * 0.95, -7.9, F1, 180.0, weapon=w)
    for i, w in enumerate(("PIS1", "PIS2", "REV1")):
        b.mark("weapon", 9.2, -7.2 + i * 0.7, F1, 90.0, weapon=w)
    for i, w in enumerate(("FLA1", "FLA1", "SMO1")):
        b.mark("weapon", 9.2, -3.9 + i * 0.5, F1, 90.0, weapon=w)
    b.mark("spawn", 8.2, -2.2, F1, 0.0, team="police", note="the armourer")
    # the equipment / locker room
    b.put("Office_Locker", 11.2, -9.5, 0.0, repeat=(4, 0.95, 0.0))
    b.put("Rest_Table", 12.6, -5.0, 0.0)
    # back row: holding cells (留置場) behind a guard room
    part(b, "y", -12.0, CB, yb, F1, 4.0)
    part(b, "y", -3.6, CB, yb, F1, 4.0)
    cells_y = 4.2
    for i, cx in enumerate((-12.0, -9.27, -6.54)):
        b.put("Police_CellFront", cx + 0.91, cells_y, 0.0)
        b.door("x", cells_y, cx + 1.82 + 0.45, F1, -1, w=0.8, h=2.2, label="cell")
        part(b, "x", cells_y, cx + 1.82 + 0.85, cx + 2.73, F1, 4.0, mat="MI_PaintedMetalDark")
        part(b, "x", cells_y, cx + 1.82, cx + 1.82 + 0.05, F1, 2.4, mat="MI_PaintedMetalDark")
        b.box("Walls_0", (cx + 1.82, cells_y - 0.06, 2.4), (cx + 2.73, cells_y + 0.06, 4.0), "MI_PaintedMetalDark")
        b.box("Walls_0", (cx, cells_y - 0.06, 2.4), (cx + 1.82, cells_y + 0.06, 4.0), "MI_PaintedMetalDark")
        if i:
            part(b, "y", cx, cells_y, yb, F1, 4.0)
        b.put("Police_CellBunk", cx + 1.2, yb - 0.45, 0.0)
        b.mark("spawn", cx + 1.3, 5.6, F1, 180.0, team="prisoner")
    part(b, "y", -3.81, cells_y, yb, F1, 4.0)
    part(b, "x", cells_y, -3.81, -3.6, F1, 4.0)
    b.put("Office_Desk", -10.0, 1.8, 180.0)
    b.put("Office_Chair", -10.0, 2.5, 0.0)
    # 取調室 x2 (interrogation, a glass wall onto the observation room behind)
    part(b, "y", 0.0, CB, yb, F1, 4.0)
    for cx in (-1.8, 1.8):
        glass_part(b, "x", 3.8, cx - 1.74, cx + 1.74, F1, 4.0, doors=[(cx - 1.0, 1, 0.8, "swing", "door")])
        b.put("Rest_Table", cx + 0.6, 2.8, 0.0)
        b.put("Rest_Chair", cx + 0.6, 2.05, 0.0)
        b.put("Rest_Chair", cx + 0.6, 3.55, 180.0)
        b.put("Office_Desk", cx + 0.6, 6.7, 0.0)
        b.mark("spawn", cx + 0.6, 3.55, F1, 180.0, team="suspect")
    # the locker room round the lift, the WCs
    part(b, "y", 12.0, CB, yb, F1, 4.0, doors=[(5.5, -1, 0.8, "swing", "door")])
    part(b, "x", 3.8, 12.0, xi1, F1, 4.0)
    b.put("Office_Locker", 9.0, yb - 0.3, 0.0, repeat=(3, 0.95, 0.0))
    b.put("Office_Locker", 11.7, 3.4, 270.0, repeat=(2, 0.0, 0.95))
    b.put("WC_Toilet", 14.4, 2.3, 270.0)
    b.put("WC_GrabRail", 14.75, 1.4, 270.0)
    b.put("WC_Basin", 12.4, 3.4, 90.0)
    b.put("WC_Toilet", 14.4, 6.8, 270.0)

    # ── F2
    part(b, "x", CF, xi0, xi1, F2, 3.6, doors=[(-3.6, 1), (1.5, 1), (10.4, 1)])
    part(b, "x", CB, xi0, xi1, F2, 3.6, doors=[(-13.4, -1, 1.0, "swing", "door"), (-7.8, -1), (0.0, -1),
                                             (5.0, -1, 1.0, "swing", "door"), (7.55, -1, 1.0, "", "open", 2.1),
                                             (10.5, -1), (13.4, -1)])
    part(b, "y", -3.0, yf, CF, F2, 3.6)
    part(b, "y", 6.0, yf, CF, F2, 3.6)
    # 刑事課 (criminal investigation) -- the open office
    for x in (-12.0, -7.5):
        for y in (-7.4, -3.8):
            b.put("Office_DeskIsland", x, y, 0.0, z=F2)
            chairs_around(b, x, y, 2, 0.6, 0.85, z=F2)
    for (piece, x, y, r) in (("Office_Whiteboard", -4.2, -8.8, 0.0), ("Office_Cabinet", -14.5, -2.4, 90.0)):
        b.put(piece, x, y, r, z=F2)
    b.put("Office_Chair", -12.0, -7.4 - 0.85, 0.0, z=F2)
    b.mark("spawn", -9.8, -5.6, F2, 0.0, team="police")
    b.mark("cover", -5.5, -5.6, F2, 90.0)
    # 署長室 (the chief's office)
    b.put("Office_Desk", 1.5, -8.2, 180.0, z=F2)
    b.put("Office_Chair", 1.5, -8.9, 0.0, z=F2)
    b.put("Office_Sofa", -1.3, -4.6, 90.0, z=F2)
    b.put("Office_Sofa", 4.3, -4.6, 270.0, z=F2)
    b.put("Rest_Table", 1.5, -4.6, 90.0, z=F2)
    b.put("Office_Safe", 5.4, -9.3, 0.0, z=F2)
    b.mark("spawn", 1.5, -7.2, F2, 180.0, team="police", note="the chief")
    # 会議室 / 捜査本部 (the meeting room / incident room)
    b.put("Office_MeetingTable", 10.4, -6.9, 0.0, z=F2)
    b.put("Office_MeetingTable", 10.4, -4.1, 0.0, z=F2)
    for y in (-6.9, -4.1):
        for dx in (-1.0, 0.0, 1.0):
            b.put("Office_Chair", 10.4 + dx, y - 0.95, 0.0, z=F2)
            b.put("Office_Chair", 10.4 + dx, y + 0.95, 180.0, z=F2)
    b.put("Office_Whiteboard", 14.2, -8.5, 270.0, z=F2)
    # back row: 生活安全課 office | 仮眠室 | the locker room round the lift | WC
    part(b, "y", -12.0, CB, yb, F2, 3.6)
    part(b, "y", -3.6, CB, yb, F2, 3.6)
    part(b, "y", 3.6, CB, yb, F2, 3.6)
    b.put("Office_DeskIsland", -9.5, 4.8, 0.0, z=F2)
    chairs_around(b, -9.5, 4.8, 2, 0.6, 0.85, z=F2)
    b.put("Office_Cabinet", -4.1, 6.7, 270.0, z=F2)
    for x in (-2.4, 0.0, 2.4):
        b.put("Fire_Bunk", x, 5.4, 0.0, z=F2)
    part(b, "y", 12.0, CB, yb, F2, 3.6)
    b.put("Office_Locker", 9.0, yb - 0.3, 0.0, repeat=(3, 0.95, 0.0), z=F2)
    b.put("WC_Toilet", 14.4, 5.8, 270.0, z=F2)
    b.put("WC_Basin", 12.4, 3.2, 90.0, z=F2)
    return {"note": "警察署: the large police station, two storeys, inside a FENCED COMPOUND: the public gate with "
                    "the 立番 booth, the vehicle gate to the rear car park under a barrier with its own booth, "
                    "cameras; the ARMOURY on the ground floor (front right, MARK_weapon for every rack slot) -- the "
                    "complete one; the 留置場 (three holding cells behind the duty desk) reached from the west "
                    "護送口 door under its canopy, two interrogation rooms with observation rooms; the chief's "
                    "office and the incident room upstairs; two stairs and a lift."}


# ── 消防署: the LARGE fire station, two storeys ──────────────────────────────────────────────────────────────────

def fire_station(b):
    X0, X1, Y0, Y1 = -16.0, 16.0, -13.0, 8.4
    F1, F2, TOP = 0.0, 5.4, 9.4
    CF, CB = -1.2, 0.6
    xi0, xi1, yf, yb = X0 + EXT_T, X1 - EXT_T, Y0 + EXT_T, Y1 - EXT_T
    apron(b, -20.0, -25.0, 20.0, 14.0)                      # the apparatus apron in front; the plot's back is left open
    # the 訓練塔 (training / hose tower) right behind, not enterable
    b.box("Site", (9.0, 8.6, 0.0), (14.0, 13.6, 16.0), "MI_ConcreteSmooth")
    for z in range(3, 16, 3):
        b.box("Site", (8.97, 9.4, z), (9.0, 12.8, z + 1.2), "MI_Window")
    b.box("Site", (8.6, 8.4, 16.0), (14.4, 13.8, 16.6), "MI_CraneRed")
    wellB = (xi0, CB + 0.06, -13.06, yb)
    wellA = (10.06, CB + 0.06, 12.74, yb)
    holeB = b.ustair(*wellB, F1, F2 - F1, near="s")
    holeA = b.ustair(*wellA, F1, F2 - F1, near="s")
    b.ustair(*wellB, F2, TOP - F2, near="s", cap=True)
    holeA2 = b.ustair(*wellA, F2, TOP - F2, near="s")
    shaft = b.lift(14.3, CB + 0.875, 1.6, 1.6, [F1, F2], faces=1, turned=True)      # beside stair A (user, 2026-09-29)
    b.slab(X0, Y0, X1, Y1, F1, "MI_ConcreteSmooth")
    b.slab(X0, Y0, X1, Y1, F2, "MI_Terrazzo", holes=[holeB, holeA, shaft])
    roof(b, X0, Y0, X1, Y1, TOP, holes=[holeA2], units=5)
    stair_house(b, wellA[0], wellA[1], wellA[2], wellA[3], TOP)
    bays = [(u, -1, 4.0, "", "open", 4.4) for u in (-13.3, -8.3, -3.3, 1.7)]
    ext(b, X0, Y0, X1, Y1, F1, F2 - F1, "MI_TileWhite", {
        "f": (bays + [(12.5, -1, 1.8, "slide", "exit")], [b.window(8.0, F1, 2.4, 0.9, 2.6)]),
        "b": ([(-3.0, 1, 0.9, "swing", "exit")], []),
        "r": ([(-0.3, 1, 1.0, "swing", "exit")], band_windows(b, yf + 1.0, -2.0, F1, 5.0, every=3.6)),
    })
    ext(b, X0, Y0, X1, Y1, F2, TOP - F2, "MI_TileWhite", {
        "f": ((), band_windows(b, xi0 + 0.5, xi1 - 0.5, F2, 3.8, every=3.2, w=2.0)),
        "b": ((), band_windows(b, -12.0, 9.5, F2, 3.8, every=3.2, w=1.6)),
    })
    for u in (-13.3, -8.3, -3.3, 1.7):
        b.box("Facade", (u - 2.1, Y0 - 0.35, 4.5), (u + 2.1, Y0, 5.1), "MI_CraneRed")
    b.box("Facade", (X0, Y0 - 0.2, TOP - 1.3), (X1, Y0, TOP - 0.6), "MI_CraneRed")
    sign(b, 9.5, 15.5, Y0 - 0.2, 3.0, 3.7, "MI_SignRed")
    # ── F1: apparatus bays x -15.8 .. 4.2, the office x 4.4 .. 15.8
    part(b, "y", 4.3, yf, CF, F1, 5.2, doors=[(-9.0, -1)])
    part(b, "x", CF, xi0, xi1, F1, 5.2, doors=[(-11.0, 1), (0.0, 1), (6.0, 1)])
    b.mark("vehicle", -13.3, -6.9, 0.0, 180.0, vehicle="LAT1")
    b.mark("vehicle", -8.3, -8.3, 0.0, 180.0, vehicle="FIE1")
    b.mark("vehicle", -3.3, -8.3, 0.0, 180.0, vehicle="FIE1")
    b.mark("vehicle", 1.7, -9.0, 0.0, 180.0, vehicle="AMB1")
    for x in (-8.5, -6.4, -3.3, 2.3):
        b.put("Fire_GearRack", x, -1.55, 0.0)
    b.mark("spawn", -5.8, -3.0, F1, 180.0, team="fire")
    b.put("Office_Reception", 12.5, -9.8, 0.0)
    b.put("Office_DeskIsland", 8.2, -6.4, 0.0)
    chairs_around(b, 8.2, -6.4, 2, 0.6, 0.85)
    b.put("Office_DeskIsland", 12.6, -5.2, 0.0)
    chairs_around(b, 12.6, -5.2, 2, 0.6, 0.85)
    b.put("Office_ServerRack", 15.3, -2.3, 270.0)
    b.put("Office_Cabinet", 4.75, -4.0, 90.0)
    b.mark("spawn", 10.5, -8.0, F1, 0.0, team="fire")
    # back row
    part(b, "x", CB, xi0, xi1, F1, 5.2, doors=[(-14.4, -1, 1.0), (-9.5, -1), (-3.0, -1), (1.05, -1, 0.8),
                                             (3.2, -1, 0.8), (7.0, -1), (11.4, -1, 1.0), (14.3, -1, 1.0, "", "open", 2.1)])
    for x in (-13.0, -6.0, 0.0, 2.1, 4.3, 10.0, 12.8):
        part(b, "y", x, CB, yb, F1, 5.2)
    b.put("Office_Locker", -11.5, yb - 0.3, 0.0, repeat=(5, 0.95, 0.0))
    b.put("Station_Bench", -9.5, 4.0, 0.0)
    b.put("Shop_StockShelf", -4.0, 2.3, 90.0)
    b.put("Warehouse_Pallet", -1.2, 6.3, 0.0)
    b.put("WC_Toilet", 1.05, yb - 0.38, 0.0)
    b.put("WC_Basin", 3.95, 4.5, 270.0)
    b.put("Rest_Table", 7.0, 4.6, 0.0)
    for dx in (-0.35, 0.35):
        b.put("Rest_Chair", 7.0 + dx, 3.85, 0.0)
        b.put("Rest_Chair", 7.0 + dx, 5.35, 180.0)
    b.put("Kitchen_Sink", 5.5, yb - 0.4, 0.0)
    b.put("Kitchen_Fridge", 9.4, yb - 0.45, 0.0)
    b.put("Office_ServerRack", 15.3, 5.0, 270.0)
    # ── F2
    part(b, "x", CF, xi0, xi1, F2, 3.8, doors=[(-13.4, 1), (-8.6, 1), (-3.1, 1), (4.0, 1), (11.9, 1)])
    for x in (-11.0, -6.2, 0.0, 8.0):
        part(b, "y", x, yf, CF, F2, 3.8)
    for x0_ in (-15.8, -11.0):
        for k in range(2):
            b.put("Fire_Bunk", x0_ + 1.2 + k * 2.4, -9.8, 90.0, z=F2)
        b.put("Office_Locker", x0_ + 2.4, yf + 0.3, 180.0, z=F2)
    b.mark("spawn", -13.4, -5.0, F2, 0.0, team="fire")
    b.put("Office_MeetingTable", -3.1, -6.8, 0.0, z=F2)
    for dx in (-1.0, 0.0, 1.0):
        b.put("Office_Chair", -3.1 + dx, -7.75, 0.0, z=F2)
        b.put("Office_Chair", -3.1 + dx, -5.85, 180.0, z=F2)
    b.put("Office_Whiteboard", -3.1, -11.2, 0.0, z=F2)
    b.put("Office_DeskIsland", 4.0, -7.5, 0.0, z=F2)
    chairs_around(b, 4.0, -7.5, 2, 0.6, 0.85, z=F2)
    b.put("Office_Desk", 11.9, -9.6, 180.0, z=F2)
    b.put("Office_Chair", 11.9, -10.3, 0.0, z=F2)
    b.put("Office_Sofa", 14.9, -5.5, 270.0, z=F2)
    b.put("Office_Safe", 9.0, -12.2, 0.0, z=F2)
    part(b, "x", CB, xi0, xi1, F2, 3.8, doors=[(-14.4, -1, 1.0), (-9.5, -1), (-3.0, -1), (2.1, -1),
                                             (7.0, -1), (11.4, -1, 1.0), (14.3, -1, 1.0, "", "open", 2.1)])
    for x in (-13.0, -6.0, 4.3, 10.0, 12.8):
        part(b, "y", x, CB, yb, F2, 3.8)
    b.put("Office_Locker", -11.5, yb - 0.3, 0.0, repeat=(5, 0.95, 0.0), z=F2)
    b.put("Office_Whiteboard", -3.0, yb - 0.4, 0.0, z=F2)
    b.put("WC_Toilet", 0.5, yb - 0.38, 0.0, z=F2)
    b.put("WC_Toilet", 3.6, yb - 0.38, 0.0, z=F2)
    b.put("Office_Sofa", 7.0, 6.5, 0.0, z=F2)
    b.put("Shop_StockShelf", 15.3, 4.5, 270.0, z=F2)
    return {"note": "消防署: the large fire station, two storeys; four open bays (ladder truck, two pumpers, an "
                    "ambulance), bunk rooms and the briefing room upstairs, the 訓練塔 behind; a lift beside stair A."}


# ── 病院: ONE hospital type, medium / large, compacted to its essentials ─────────────────────────────────────────

def hospital(b):
    X0, X1, Y0, Y1 = -22.0, 22.0, -12.0, 8.0
    F1, F2, F3, TOP = 0.0, 4.5, 8.5, 12.5
    CF, CB = -3.4, -0.7                     # a 2.7 m corridor (a double-loaded hospital corridor)
    xi0, xi1, yf, yb = X0 + EXT_T, X1 - EXT_T, Y0 + EXT_T, Y1 - EXT_T
    SL = "slide"
    apron(b, -27.5, -30.0, 27.5, 30.0)
    paint_bays(b, -25.0, 20, 2.5, 14.0, 19.0)
    paint_bays(b, -25.0, 20, 2.5, 24.0, 29.0)
    b.box("Site", (-20.0, -19.0, 3.8), (-8.0, Y0, 4.1), "MI_PaintedMetal")        # the entrance canopy
    for x in (-19.7, -8.3):
        b.box("Site", (x - 0.15, -18.85, 0.0), (x + 0.15, -18.55, 3.8), "MI_PaintedMetal")
    b.box("Site", (X1, -11.0, 4.0), (27.0, -4.0, 4.3), "MI_PaintedMetal")       # the 救急 ambulance canopy
    wellB = (xi0, CB + 0.06, -19.06, yb)
    wellA = (2.56, CB + 0.06, 5.24, yb)
    holes, holesA = [], []
    for z0, z1 in ((F1, F2), (F2, F3)):
        holes.append(b.ustair(*wellB, z0, z1 - z0, near="s"))
        holes.append(b.ustair(*wellA, z0, z1 - z0, near="s"))
    b.ustair(*wellB, F3, TOP - F3, near="s", cap=True)
    holeA3 = b.ustair(*wellA, F3, TOP - F3, near="s")
    shaft = b.lift(1.0, 0.95, 2.8, 1.9, [F1, F2, F3, TOP], faces=1, turned=True, door_w=1.2, head=3.0)
    b.slab(X0, Y0, X1, Y1, F1, "MI_TileWhite")
    b.slab(X0, Y0, X1, Y1, F2, "MI_TileWhite", holes=[holes[0], holes[1], shaft])
    b.slab(X0, Y0, X1, Y1, F3, "MI_TileWhite", holes=[holes[2], holes[3], shaft])
    roof(b, X0, Y0, X1, Y1, TOP, holes=[holeA3, shaft], units=0)
    stair_house(b, wellA[0], wellA[1], wellA[2], wellA[3], TOP)
    # the roof HELIPAD (H in a circle's square) and the lift's roof lobby
    b.box("Roof", (-18.0, -11.0, TOP), (-4.0, 3.0, TOP + 0.05), "MI_ConcreteSmooth")
    for lo, hi in (((-13.0, -6.0), (-12.2, 0.0)), ((-9.8, -6.0), (-9.0, 0.0)), ((-12.2, -3.4), (-9.8, -2.6))):
        b.box("Roof", (lo[0], lo[1], TOP + 0.05), (hi[0], hi[1], TOP + 0.07), "MI_PaintWhite")
    b.mark("vehicle", -11.0, -4.0, TOP, 0.0, note="helipad: a helicopter lands here")
    lob = (-0.8, -3.2, 2.8, CB - 0.1)
    for s_, axis, c, a0, a1, sgn in (("f", "x", lob[1] - 0.1, lob[0] - 0.2, lob[2] + 0.2, -1),
                                     ("l", "y", lob[0] - 0.1, lob[1], lob[3], -1), ("r", "y", lob[2] + 0.1, lob[1], lob[3], 1)):
        ops = openings(b, axis, c, TOP, [(1.0, -1, 1.2, "swing", "door")]) if s_ == "f" else []
        b.wall(axis, c, a0, a1, TOP, 3.0, 0.2, "MI_Plaster", mat_out="MI_ConcreteSmooth", out_sign=sgn, ops=ops,
               group="Roof")
    b.box("Roof", (lob[0] - 0.2, lob[1] - 0.2, TOP + 3.0), (lob[2] + 0.2, lob[3], TOP + 3.2), "MI_ConcreteSmooth")
    # ── the shell
    ext(b, X0, Y0, X1, Y1, F1, F2 - F1, "MI_TileWhite", {
        "f": ([(-14.0, -1, 2.4, SL, "exit")], band_windows(b, -8.0, 13.5, F1, 4.3, every=5.0, w=2.2) +
              [b.window(-19.0, F1, 2.4, 0.6, 3.0), b.window(-9.5, F1, 2.4, 0.6, 3.0)]),
        "r": ([(-7.6, 1, 2.4, SL, "exit"), (-2.05, 1, 1.2, SL, "exit")], []),
        "l": ([(-2.05, -1, 1.2, "swing", "exit")], []),
    })
    for z0, z1 in ((F2, F3), (F3, TOP)):
        ext(b, X0, Y0, X1, Y1, z0, z1 - z0, "MI_TileWhite", {
            "f": ((), band_windows(b, xi0 + 0.5, xi1 - 0.5, z0, 3.8, every=3.2, w=2.0)),
            "b": ((), band_windows(b, -18.5, -1.0, z0, 3.8, every=3.4, w=1.6) +
                  band_windows(b, 5.5, 21.5, z0, 3.8, every=3.4, w=1.6)),
        })
    sign(b, -18.0, -10.0, Y0 - 0.2, TOP - 2.2, TOP - 0.8, "MI_SignGreen")
    sign(b, X1 - 0.2 + 0.2, X1 + 0.05, -9.5, 4.4, 5.0, "MI_SignRed")
    # TWO ENTRANCES, told apart (user, 2026-09-29): the MAIN entrance (正面玄関) on the street with its 風除室 and
    # the drop-off under the canopy; the EMERGENCY side on the right -- the ambulance lane (救急車専用) from the
    # street to its own canopy and the 救急搬入口 (the stretcher door, a vestibule into the ER), and beside it the
    # walk-in 救急外来 door for patients who come on foot. Red for the emergency side, green for the main.
    b.box("Site", (-20.0, -19.2, 0.01), (-8.0, -16.4, 0.02), "MI_PaintWhite")         # the drop-off bay
    b.box("Site", (-19.8, -19.0, 0.02), (-8.2, -16.6, 0.03), "MI_AsphaltLot")
    b.box("Facade", (-17.5, -19.05, 3.3), (-10.5, -18.85, 3.8), "MI_SignGreen")       # 正面玄関 over the canopy
    for y0_, y1_ in ((-30.0, -27.0), (-25.0, -22.0), (-20.0, -17.0), (-15.0, -12.0)):
        b.box("Site", (X1 + 1.5, y0_, 0.01), (X1 + 4.5, y1_, 0.02), "MI_SignRed")      # the ambulance lane
    b.box("Site", (X1 + 1.3, -30.0, 0.01), (X1 + 1.45, -4.0, 0.02), "MI_PaintYellow")
    b.box("Site", (X1 + 4.55, -30.0, 0.01), (X1 + 4.7, -4.0, 0.02), "MI_PaintYellow")
    for y in (-10.8, -4.2):
        b.box("Site", (26.6, y - 0.2, 0.0), (27.0, y + 0.2, 4.0), "MI_PaintedMetal")   # the ER canopy's columns
    b.box("Site", (27.1, -29.8, 0.0), (27.25, -29.65, 2.4), "MI_Steel")               # 救急車専用 sign post
    b.box("Site", (26.8, -29.8, 1.8), (27.4, -29.65, 2.4), "MI_SignRed")
    b.box("Facade", (X1, -8.9, 2.7), (X1 + 0.2, -6.3, 3.3), "MI_SignRed")              # 救急搬入口
    b.box("Facade", (X1, -2.8, 2.6), (X1 + 0.2, -1.3, 3.1), "MI_SignRed")              # 救急外来
    b.box("Facade", (X1, -3.0, 3.3), (X1 + 1.6, -1.1, 3.45), "MI_PaintedMetal")        # its small canopy
    # ── F1
    # front row: entrance hall | four consulting rooms | the ER (救急)
    part(b, "x", CF, -6.0, xi1, F1, 4.3, doors=[(-3.5, 1, 1.2, SL), (1.5, 1, 1.2, SL), (6.5, 1, 1.2, SL),
                                                 (11.5, 1, 1.2, SL), (17.9, 1, 1.6, SL)])
    part(b, "x", CF, xi0, -15.5, F1, 4.3)
    for x in (-6.0, -1.0, 4.0, 9.0, 14.0):
        part(b, "y", x, yf, CF, F1, 4.3)
    for x in (-16.0, -12.0):                                   # the 風除室 at the main entrance
        b.wall("y", x, yf, -9.3, F1, 4.3, 0.1, "MI_GlassClear", group="Walls_0")
    b.wall("x", -9.3, -16.0, -12.0, F1, 4.3, 0.1, "MI_GlassClear", group="Walls_0",
           ops=[b.door("x", -9.3, -14.0, F1, -1, w=2.0, h=2.3, style=SL, label="the main 風除室")])
    for y in (-9.2, -6.0):                                     # 救急搬入口: the stretcher vestibule into the ER
        b.wall("x", y, 19.6, xi1, F1, 4.3, 0.12, "MI_Plaster", group="Walls_0")
    b.wall("y", 19.6, -9.2, -6.0, F1, 4.3, 0.12, "MI_Plaster", group="Walls_0",
           ops=[b.door("y", 19.6, -7.6, F1, 1, w=2.0, h=2.3, style=SL, label="the ER vestibule")])
    b.put("Shop_Counter", -18.0, -5.0, 0.0)
    b.put("Shop_Counter", -9.0, -5.0, 0.0)
    b.put("Office_Chair", -18.5, -4.2, 180.0)
    b.put("Office_Chair", -9.0, -4.2, 180.0)
    for x in (-19.0, -9.2):
        b.put("Hosp_WaitingBench", x, -8.2, 180.0)
    b.put("Hosp_WaitingBench", -9.2, -10.6, 180.0)
    b.put("Shop_ATM", -21.5, -10.0, 90.0)
    b.mark("spawn", -14.0, -7.0, F1, 0.0, team="civilian")
    for cx in (-3.5, 1.5, 6.5, 11.5):
        b.put("Office_Desk", cx - 1.2, -10.8, 0.0)
        b.put("Office_Chair", cx - 1.2, -10.15, 180.0)
        b.put("Hosp_ExamTable", cx + 1.5, -9.3, 0.0)
        b.put("Hosp_Curtain", cx + 1.5, -7.6, 0.0)
    b.mark("spawn", -3.5, -8.0, F1, 0.0, team="doctor")
    # the ER: three bays behind curtains, the stretcher, the monitor, from the ambulance door
    for i, y in enumerate((-10.6, -7.6)):
        b.put("Hosp_Bed", 15.2, y, 90.0)
        b.put("Hosp_Monitor", 14.6, y + 1.1, 90.0)
    b.put("Hosp_Curtain", 16.8, -9.1, 0.0)
    b.put("Hosp_Stretcher", 20.6, -10.8, 90.0)
    b.mark("vehicle", 24.8, -7.5, 0.0, 180.0, vehicle="AMB1")   # under the 救急 canopy
    b.put("Hosp_NurseStation", 17.9, -5.0, 180.0)
    b.mark("spawn", 18.0, -8.0, F1, 90.0, team="doctor", note="the ER team, met at the 搬入口")
    # back row: stair B | pharmacy store | X-ray | two WCs | the bed lift | stair A | the doctors' office | treatment
    part(b, "x", CB, xi0, xi1, F1, 4.3, doors=[(-20.4, -1, 1.2), (-15.5, -1), (-9.0, -1, 1.2, SL),
                                             (-4.65, -1, 1.0, SL), (-1.95, -1, 1.0, SL),
                                             (1.0, -1, 1.3, "", "open", 2.1), (3.9, -1, 1.2), (9.5, -1),
                                             (17.9, -1, 1.6, SL)])
    for x in (-19.0, -12.0, -6.0, -3.3, -0.6, 2.5, 5.3, 14.0):
        part(b, "y", x, CB, yb, F1, 4.3)
    part(b, "x", 3.3, -6.0, -0.6, F1, 4.3)
    b.put("Shop_StockShelf", -15.5, yb - 0.4, 0.0)
    b.put("Kitchen_Shelf", -18.4, 3.5, 90.0)
    b.put("Hosp_XRay", -9.0, 4.2, 0.0)
    for x in (-4.65, -1.95):
        b.put("WC_Toilet", x, 2.9, 0.0)
        b.put("WC_GrabRail", x + 0.7, 3.2, 0.0)
        b.put("WC_Basin", x - 1.0, 1.0, 90.0)
    b.put("Office_DeskIsland", 9.6, 4.8, 0.0)
    chairs_around(b, 9.6, 4.8, 2, 0.6, 0.85)
    b.put("Office_Cabinet", 13.6, 2.5, 270.0)
    b.put("Hosp_Bed", 17.9, 5.8, 0.0)
    b.put("Kitchen_Sink", 21.2, 3.0, 270.0)
    # ── F2: the operating suite and the ICU
    part(b, "x", CF, xi0, xi1, F2, 3.8, doors=[(-18.0, 1, 1.2, SL), (-10.5, 1, 1.6, SL), (-3.5, 1, 1.6, SL),
                                             (5.0, 1, 1.6, SL), (16.0, 1, 1.2, SL)])
    for x in (-14.0, -7.0, 0.0, 10.0):
        part(b, "y", x, yf, CF, F2, 3.8)
    b.put("Kitchen_Sink", -18.0, -11.2, 0.0, z=F2)
    b.put("Kitchen_Sink", -15.8, -11.2, 0.0, z=F2)
    b.put("Office_Locker", -21.4, -8.0, 90.0, repeat=(3, 0.0, 0.95), z=F2)
    for cx in (-10.5, -3.5):
        b.put("Hosp_ORTable", cx, -8.2, 0.0, z=F2)
        b.put("Hosp_Monitor", cx + 1.5, -8.2, 270.0, z=F2)
        b.put("Hosp_Stretcher", cx - 2.4, -9.0, 0.0, z=F2)
    b.mark("spawn", -10.5, -6.5, F2, 180.0, team="doctor")
    b.mark("objective", -3.5, -8.2, F2, 0.0, note="an operating table (a VIP patient)")
    for x in (1.6, 4.0, 6.4, 8.8):
        b.put("Hosp_Bed", x, -10.2, 0.0, z=F2)
        b.put("Hosp_Monitor", x + 0.85, -11.2, 0.0, z=F2)
    b.put("Hosp_NurseStation", 5.0, -5.8, 0.0, z=F2)
    b.put("Office_DeskIsland", 16.0, -8.0, 0.0, z=F2)
    chairs_around(b, 16.0, -8.0, 2, 0.6, 0.85, z=F2)
    part(b, "x", CB, xi0, xi1, F2, 3.8, doors=[(-20.4, -1, 1.2), (-15.5, -1), (-9.0, -1, 1.2, SL),
                                             (-4.65, -1, 1.0, SL), (-1.95, -1, 1.0, SL),
                                             (1.0, -1, 1.3, "", "open", 2.1), (3.9, -1, 1.2), (9.5, -1), (17.9, -1)])
    for x in (-19.0, -12.0, -6.0, -3.3, -0.6, 2.5, 5.3, 14.0):
        part(b, "y", x, CB, yb, F2, 3.8)
    part(b, "x", 3.3, -6.0, -0.6, F2, 3.8)
    b.put("Shop_StockShelf", -15.5, yb - 0.4, 0.0, z=F2)
    b.put("Hosp_XRay", -9.0, 4.2, 0.0, z=F2)
    for x in (-4.65, -1.95):
        b.put("WC_Toilet", x, 2.9, 0.0, z=F2)
    b.put("Office_DeskIsland", 9.6, 4.8, 0.0, z=F2)
    chairs_around(b, 9.6, 4.8, 2, 0.6, 0.85, z=F2)
    b.put("Office_Locker", 16.0, yb - 0.3, 0.0, repeat=(5, 0.95, 0.0), z=F2)
    # ── F3: the ward (four 4-bed rooms, three private rooms, the day room), the nurse station opposite
    wards = [(-21.8, -15.4), (-15.4, -9.0), (-9.0, -2.6), (-2.6, 3.8)]
    privs = [(3.8, 7.4), (7.4, 11.0), (11.0, 14.6)]
    doors = [((a + c) / 2, 1, 1.2, SL) for a, c in wards + privs]
    part(b, "x", CF, xi0, xi1, F3, 3.8, doors=doors + [(18.2, 1, 3.0, "", "open", 2.4)])
    for a, c in wards + privs:
        part(b, "y", c, yf, CF, F3, 3.8)
    for a, c in wards:
        for y in (-10.4, -6.9):
            b.put("Hosp_Bed", a + 1.2, y, 270.0, z=F3)
            b.put("Hosp_Bed", c - 1.2, y, 90.0, z=F3)
    for a, c in privs:
        b.put("Hosp_Bed", a + 1.2, -9.5, 270.0, z=F3)
        b.put("Hosp_Monitor", c - 0.5, -10.8, 270.0, z=F3)
    b.mark("objective", 5.0, -9.5, F3, 0.0, note="a private room: the protected / wanted patient")
    b.put("Office_Sofa", 18.2, -10.8, 0.0, z=F3)
    b.put("Rest_Table", 18.2, -8.0, 0.0, z=F3)
    part(b, "x", CB, xi0, xi1, F3, 3.8, doors=[(-20.4, -1, 1.2), (-15.5, -1, 4.0, "", "open", 2.4),
                                             (-9.0, -1), (-4.65, -1, 1.0, SL), (-1.95, -1, 1.0, SL),
                                             (1.0, -1, 1.3, "", "open", 2.1), (3.9, -1, 1.2), (9.5, -1), (17.9, -1)])
    for x in (-19.0, -12.0, -6.0, -3.3, -0.6, 2.5, 5.3, 14.0):
        part(b, "y", x, CB, yb, F3, 3.8)
    part(b, "x", 3.3, -6.0, -0.6, F3, 3.8)
    b.put("Hosp_NurseStation", -15.5, 1.5, 180.0, z=F3)
    b.put("Office_Cabinet", -15.5, yb - 0.3, 0.0, z=F3)
    b.mark("spawn", -15.5, 2.6, F3, 180.0, team="nurse")
    b.put("Rest_Table", -9.0, 4.5, 0.0, z=F3)
    for x in (-4.65, -1.95):
        b.put("WC_Toilet", x, 2.9, 0.0, z=F3)
    b.put("Shop_StockShelf", 9.6, yb - 0.4, 0.0, z=F3)
    b.put("Hosp_Stretcher", 17.9, 5.0, 0.0, z=F3)
    return {"note": "病院: one hospital type (medium / large, compact): 3 storeys + a roof helipad; the bed lift "
                    "stops at every floor and the roof. TWO entrances: the MAIN one on the street (a 風除室, the "
                    "drop-off under the canopy, green signs) and the EMERGENCY side on the right (the ambulance lane "
                    "to its canopy, the 救急搬入口 vestibule into the ER, the walk-in 救急外来 door; red signs)."}


# ── オフィスビル: a four-storey office building ────────────────────────────────────────────────────────────────

def office_hq(b):
    X0, X1, Y0, Y1 = -12.0, 12.0, -9.0, 9.0
    LV = [0.0, 4.2, 8.0, 11.8]
    TOP = 15.6
    CF, CB = -1.5, 0.3
    xi0, xi1, yf, yb = X0 + EXT_T, X1 - EXT_T, Y0 + EXT_T, Y1 - EXT_T
    apron(b, -14.0, -15.0, 14.0, 11.0, "MI_TileWhite")                            # the entrance plaza
    for x in (-10.0, -6.0, 6.0, 10.0):
        b.box("Site", (x - 0.6, -13.5, 0.0), (x + 0.6, -12.3, 0.5), "MI_ConcreteSmooth")   # planters
    wellB = (xi0, CB + 0.06, -9.06, yb)
    wellA = (-0.44, CB + 0.06, 2.24, yb)
    shaft = b.lift(-1.75, 1.41, 1.8, 1.8, LV, faces=1, turned=True)
    holes = {LV[0]: []}
    for i, z0 in enumerate(LV):
        z1 = LV[i + 1] if i + 1 < len(LV) else TOP
        hB = b.ustair(*wellB, z0, z1 - z0, near="s", cap=(z1 == TOP))
        hA = b.ustair(*wellA, z0, z1 - z0, near="s")
        holes[z1] = [hA] if z1 == TOP else [hA, hB, shaft]
    for z in LV:
        b.slab(X0, Y0, X1, Y1, z, "MI_Terrazzo" if z == 0 else "MI_Fabric", holes=holes.get(z, []))
    roof(b, X0, Y0, X1, Y1, TOP, holes=holes[TOP], units=6)
    stair_house(b, wellA[0], wellA[1], wellA[2], wellA[3], TOP)
    # the shell: a glazed lobby, ribbon windows above
    lobby_glass = [Opening(xi0 + 0.3, -1.2, 0.2, 3.6, glass="MI_GlassClear", frame="MI_PaintedMetal"),
                   Opening(1.2, xi1 - 0.3, 0.2, 3.6, glass="MI_GlassClear", frame="MI_PaintedMetal")]
    ext(b, X0, Y0, X1, Y1, LV[0], LV[1], "MI_ConcreteSmooth", {
        "f": ([(0.0, -1, 1.8, "slide", "exit")], lobby_glass),
        "l": ([(-0.6, -1, 1.0, "swing", "exit")], []),
    })
    for i, z0 in enumerate(LV[1:]):
        z1 = LV[i + 2] if i + 2 < len(LV) else TOP
        rib = [Opening(xi0 + 0.4, xi1 - 0.4, z0 + 0.8, z0 + 2.9, glass="MI_GlassClear", frame="MI_PaintedMetal")]
        ext(b, X0, Y0, X1, Y1, z0, z1 - z0, "MI_TileBeige", {
            "f": ((), rib), "b": ((), band_windows(b, 3.0, 11.0, z0, 3.6, every=3.0, w=2.0)),
            "l": ((), band_windows(b, yf + 1.0, -2.5, z0, 3.6, every=3.0, w=1.8)),
            "r": ((), band_windows(b, yf + 1.0, yb - 1.0, z0, 3.6, every=3.0, w=1.8)),
        })
    b.box("Facade", (-3.0, Y0 - 3.0, 3.7), (3.0, Y0, 3.9), "MI_PaintedMetal")       # the entrance canopy
    sign(b, -2.5, 2.5, Y0 - 3.0, 3.9, 4.4)

    def core(z, h, room_doors):
        part(b, "x", CB, xi0, xi1, z, h, doors=[(-10.4, -1, 1.0), (-7.5, -1), (-4.5, -1),
                                             (-1.75, -1, 1.0, "", "open", 2.1), (0.9, -1, 1.0)] + room_doors)
        for x in (-9.0, -6.0, -3.0, -0.5, 2.3):
            part(b, "y", x, CB, yb, z, h)
        b.put("WC_Toilet", -8.2, yb - 0.38, 0.0, z=z)
        b.put("WC_Toilet", -6.8, yb - 0.38, 0.0, z=z)
        b.put("WC_Basin", -8.65, 1.6, 90.0, z=z)
        b.put("WC_Toilet", -5.2, yb - 0.38, 0.0, z=z)
        b.put("WC_Toilet", -3.8, yb - 0.38, 0.0, z=z)
        b.put("WC_Basin", -5.65, 1.6, 90.0, z=z)

    # ── F1: the lobby (open to the corridor), security, mail room
    z, h = LV[0], LV[1] - LV[0] - 0.2
    core(z, h, [(4.65, -1), (9.4, -1)])
    part(b, "y", 7.0, CB, yb, z, h)
    b.put("Office_Reception", 4.5, -4.2, 0.0)
    b.put("Office_Chair", 4.5, -3.4, 180.0)
    for x, y, r in ((-7.0, -6.5, 90.0), (-4.5, -7.6, 0.0), (-9.8, -4.0, 90.0)):
        b.put("Office_Sofa", x, y, r)
    b.put("Rest_Table", -5.6, -5.5, 0.0)
    b.mark("spawn", 4.5, -2.8, z, 180.0, team="guard")
    b.mark("spawn", -2.0, -3.0, z, 0.0, team="guard")
    b.put("Office_ServerRack", 2.9, yb - 0.6, 0.0)
    b.put("Office_Desk", 4.6, 5.0, 0.0)
    b.put("Office_Chair", 4.6, 4.35, 180.0)
    b.put("Shop_StockShelf", 9.4, yb - 0.4, 0.0)
    b.put("Shop_Copier", 11.1, 3.0, 270.0)
    # ── F2 and F3: 島型 open offices, meeting rooms (F3: the server room)
    for fi in (1, 2):
        z, h = LV[fi], LV[fi + 1] - LV[fi] - 0.2
        glass_part(b, "x", CF, xi0, xi1, z, h, doors=[(-6.2, 1), (7.2, 1)])
        for x in (-8.5, -4.0, 0.5, 5.0, 9.5):
            for y in (-6.9, -3.6):
                b.put("Office_DeskIsland", x, y, 0.0, z=z)
                chairs_around(b, x, y, 2, 0.6, 0.85, z=z)
        b.mark("spawn", -1.8, -5.2, z, 0.0, team="worker")
        b.mark("cover", 2.8, -5.2, z, 90.0)
        core(z, h, [(4.65, -1), (9.4, -1)])
        part(b, "y", 7.0, CB, yb, z, h)
        if fi == 1:
            for cx in (4.65, 9.4):
                b.put("Office_MeetingTable", cx, 5.0, 90.0, z=z)
                for dy in (-1.0, 0.0, 1.0):
                    b.put("Office_Chair", cx - 0.9, 5.0 + dy, 270.0, z=z)
                    b.put("Office_Chair", cx + 0.9, 5.0 + dy, 90.0, z=z)
        else:
            b.put("Office_ServerRack", 3.3, 4.5, 90.0, repeat=(4, 0.0, 1.05), z=z)
            b.put("Office_ServerRack", 6.0, 4.5, 270.0, repeat=(4, 0.0, 1.05), z=z)
            b.mark("objective", 4.65, 6.0, z, 0.0, note="the server room")
            b.put("Office_MeetingTable", 9.4, 5.0, 90.0, z=z)
    # ── F4: the boardroom, the secretaries, the president's office, the strong room
    z, h = LV[3], TOP - LV[3] - 0.2
    part(b, "x", CF, xi0, xi1, z, h, doors=[(-7.4, 1), (0.0, 1), (7.4, 1)])
    part(b, "y", -3.0, yf, CF, z, h, doors=[(-5.0, 1)])
    part(b, "y", 3.0, yf, CF, z, h, doors=[(-5.0, -1)])
    for x in (-8.9, -5.9):
        b.put("Office_MeetingTable", x, -5.4, 0.0, z=z)
        for dx in (-1.0, 0.0, 1.0):
            b.put("Office_Chair", x + dx, -6.35, 0.0, z=z)
            b.put("Office_Chair", x + dx, -4.45, 180.0, z=z)
    b.put("Office_Desk", -1.0, -7.2, 180.0, z=z)
    b.put("Office_Chair", -1.0, -7.9, 0.0, z=z)
    b.put("Office_Cabinet", -2.5, -8.4, 0.0, z=z)
    b.put("Office_Desk", 8.4, -7.6, 180.0, z=z)
    b.put("Office_Chair", 8.4, -8.3, 0.0, z=z)
    b.put("Office_Sofa", 6.6, -4.4, 90.0, z=z)
    b.put("Office_Sofa", 10.6, -4.4, 270.0, z=z)
    b.put("Rest_Table", 8.6, -4.4, 90.0, z=z)
    b.mark("spawn", 8.4, -6.8, z, 180.0, team="vip", note="the president")
    core(z, h, [(4.65, -1, 1.0, "swing", "door"), (9.4, -1)])
    part(b, "y", 7.0, CB, yb, z, h)
    b.put("Office_Safe", 3.0, yb - 0.4, 0.0, z=z)
    b.put("Office_Safe", 4.0, yb - 0.4, 0.0, z=z)
    b.put("Office_Cabinet", 6.4, 4.5, 270.0, repeat=(3, 0.0, 0.95), z=z)
    b.mark("objective", 3.5, 7.0, z, 0.0, note="the strong room (金庫室)")
    b.put("Shop_StockShelf", 9.4, yb - 0.4, 0.0, z=z)
    return {"note": "オフィスビル: four storeys; a lift (every floor), two stairs (A to the roof), open offices on "
                    "F2-F3, the server room (F3), the president, the boardroom and the strong room on F4."}


# ── リゾートホテル: a four-storey resort hotel, 24 sea-view rooms ────────────────────────────────────────────────

def resort_hotel(b):
    X0, X1, Y0, Y1 = -24.0, 24.0, -8.0, 8.0
    LV = [0.0, 4.5, 7.7, 10.9]
    TOP = 14.1
    CF, CB = 1.2, 3.0                          # rooms on the sea side (-Y), the corridor, the core on the land side
    xi0, xi1, yf, yb = X0 + EXT_T, X1 - EXT_T, Y0 + EXT_T, Y1 - EXT_T
    # the pool terrace (sea side) and the porte-cochère (land side)
    apron(b, -24.0, -24.0, 16.0, Y0, "MI_Limestone")
    b.box("Site", (-16.4, -20.4, -0.25), (4.4, -11.6, 0.03), "MI_Limestone")      # the pool's coping
    b.box("Site", (-16.0, -20.0, -1.0), (4.0, -12.0, -0.2), "MI_PoolWater")
    for i in range(6):
        b.put("Hotel_Lounger", -14.0 + i * 3.2, -22.6, 180.0)
    b.put("Hotel_Lounger", 8.0, -14.0, 90.0, repeat=(3, 0.0, -2.6))
    b.mark("spawn", 10.0, -20.0, 0.0, 0.0, team="guest")
    apron(b, -6.0, Y1, 6.0, 15.0, "MI_ConcreteSmooth")
    b.box("Site", (-5.0, Y1, 4.2), (5.0, 14.0, 4.5), "MI_PaintWhite")
    for x in (-4.6, 4.6):
        b.box("Site", (x - 0.15, 13.4, 0.0), (x + 0.15, 13.7, 4.2), "MI_PaintWhite")
    wellB = (xi0, CB + 0.06, -17.46, 5.86)
    wellA = (17.46, CB + 0.06, xi1, 5.86)
    shaft = b.lift(-1.0, 4.11, 1.8, 1.8, LV, faces=1, turned=True)
    holes = {}
    for i, z0 in enumerate(LV):
        z1 = LV[i + 1] if i + 1 < len(LV) else TOP
        hB = b.ustair(*wellB, z0, z1 - z0, near="e", cap=(z1 == TOP))
        hA = b.ustair(*wellA, z0, z1 - z0, near="w")
        holes[z1] = [hA] if z1 == TOP else [hA, hB, shaft]
    for z in LV:
        b.slab(X0, Y0, X1, Y1, z, "MI_Terrazzo" if z == 0 else "MI_Fabric", holes=holes.get(z, []))
    roof(b, X0, Y0, X1, Y1, TOP, holes=holes[TOP], units=8)
    stair_house(b, wellA[0], wellA[1], wellA[2], wellA[3], TOP)
    sign(b, -8.0, 8.0, Y1 + 0.2, TOP - 2.2, TOP - 0.6, "MI_SignCyan")
    # ── the shell
    sea = [Opening(u - 3.0, u + 3.0, 0.2, 3.8, glass="MI_GlassClear", frame="MI_PaintedMetal")
           for u in (-20.5, -3.5, 12.5, 19.0)]
    ext(b, X0, Y0, X1, Y1, LV[0], LV[1], "MI_PaintWhite", {
        "f": ([(-18.0 + 3.5, -1, 1.8, "slide", "exit"), (0.0, -1, 1.8, "slide", "exit"),
               (-10.0, -1, 1.8, "slide", "exit")], []),
        "b": ([(3.0, 1, 2.4, "slide", "exit")], band_windows(b, 7.0, 16.5, LV[0], 4.3, every=3.2, w=1.8)),
    })
    for i, z0 in enumerate(LV[1:]):
        z1 = LV[i + 2] if i + 2 < len(LV) else TOP
        rooms = [Opening(-24.0 + 6 * k + 1.2, -24.0 + 6 * k + 4.8, z0 + 0.1, z0 + 2.5, glass="MI_GlassClear",
                         frame="MI_PaintedMetal") for k in range(8)]
        ext(b, X0, Y0, X1, Y1, z0, z1 - z0, "MI_PaintWhite", {"f": ((), rooms)})
        for k in range(8):
            a = -24.0 + 6 * k
            b.box("Facade", (a + 0.3, -9.4, z0 - 0.15), (a + 5.7, Y0, z0 + 0.05), "MI_PaintWhite")      # balcony
            b.box("Facade", (a + 0.3, -9.4, z0 + 0.05), (a + 5.7, -9.3, z0 + 1.1), "MI_GlassClear")
    b.box("Facade", (-17.0, Y0 - 2.5, 3.2), (-4.0, Y0, 3.4), "MI_PaintWhite")             # the terrace awning
    # ── F1: restaurant | lobby | lounge-bar on the sea side; kitchen | vestibule | office on the land side
    z, h = LV[0], LV[1] - 0.2
    part(b, "x", CF, xi0, -6.0, z, h, doors=[(-12.0, 1, 2.0, "", "open", 2.4)])
    part(b, "x", CF, 6.0, xi1, z, h, doors=[(14.0, 1, 2.0, "", "open", 2.4)])
    part(b, "y", -6.0, yf, CF, z, h, doors=[(-3.0, -1, 2.0, "", "open", 2.4)])
    part(b, "y", 6.0, yf, CF, z, h)
    for x in (-21.0, -17.5, -14.0):
        for y in (-5.8, -2.4):
            b.put("Rest_Table", x, y, 0.0)
            for dx in (-0.35, 0.35):
                b.put("Rest_Chair", x + dx, y - 0.75, 0.0)
                b.put("Rest_Chair", x + dx, y + 0.75, 180.0)
    b.put("Rest_Table", -8.2, -2.4, 0.0)
    b.put("Office_Reception", -2.5, -4.8, 180.0)
    b.put("Office_Chair", -2.5, -5.6, 0.0)
    b.put("Office_Sofa", 3.0, -5.8, 0.0)
    b.put("Office_Sofa", 4.6, -3.0, 270.0)
    b.mark("spawn", -2.5, -5.9, z, 180.0, team="staff")
    b.put("Shop_Counter", 15.0, -6.9, 0.0)
    b.put("Shop_Stool", 13.0, -6.0, 0.0, repeat=(5, 1.0, 0.0))
    for x in (9.0, 20.5):
        b.put("Office_Sofa", x, -3.2, 180.0)
    part(b, "x", CB, xi0, xi1, z, h, doors=[(-18.16, -1, 1.0), (-10.0, -1), (-1.0, -1, 1.0, "", "open", 2.1),
                                          (3.0, -1, 3.0, "", "open", 2.4), (11.7, -1), (18.16, -1, 1.0)])
    for x in (-17.4, -2.1, 0.1, 6.0, 17.4):
        part(b, "y", x, CB, yb, z, h)
    part(b, "x", 5.92, xi0, -17.4, z, h)
    part(b, "x", 5.92, 17.4, xi1, z, h)
    for x in (-15.6, -13.6):
        b.put("Kitchen_Grill", x, yb - 0.4, 0.0)
    b.put("Kitchen_Fryer", -11.9, yb - 0.4, 0.0)
    b.put("Kitchen_Sink", -5.0, yb - 0.4, 0.0)
    b.put("Kitchen_PrepTable", -12.0, 5.6, 0.0)
    b.put("Kitchen_Fridge", -2.8, 4.6, 270.0)
    b.put("Office_Desk", 9.0, 6.4, 0.0)
    b.put("Office_Chair", 9.0, 5.75, 180.0)
    b.put("Shop_StockShelf", 14.5, yb - 0.4, 0.0)
    b.put("Office_Safe", 16.8, 5.0, 270.0)
    # ── F2-F4: eight rooms a floor on the sea side
    for fi, z in enumerate(LV[1:]):
        z1 = LV[fi + 2] if fi + 2 < len(LV) else TOP
        h = z1 - z - 0.2
        part(b, "x", CF, xi0, xi1, z, h, doors=[(-24.0 + 6 * k + 4.6, 1) for k in range(8)])
        for k in range(8):
            a = -24.0 + 6 * k
            if k:
                part(b, "y", a, yf, CF, z, h)
            part(b, "y", a + 2.4, -1.3, CF, z, h, doors=[(-0.05, 1, 0.8)])
            part(b, "x", -1.3, a + (0.2 if k == 0 else 0.06), a + 2.4, z, h)
            b.put("Hotel_Tub", a + 1.3, 0.75, 0.0, z=z)
            b.put("WC_Toilet", a + 0.62, -0.75, 90.0, z=z)
            b.put("WC_Basin", a + 1.6, -0.95, 180.0, z=z)
            for y in (-3.4, -5.4):
                b.put("Hotel_Bed", a + 1.3, y, 90.0, z=z)
            b.put("Office_Desk", a + 5.5, -3.5, 90.0, z=z)
            b.put("Office_Chair", a + 4.85, -3.5, 90.0, z=z)
            b.put("Office_Sofa", a + 4.0, -6.9, 0.0, z=z)
        part(b, "x", CB, xi0, xi1, z, h, doors=[(-18.16, -1, 1.0), (-10.0, -1), (-1.0, -1, 1.0, "", "open", 2.1),
                                              (11.7, -1), (18.16, -1, 1.0)])
        for x in (-17.4, -2.1, 0.1, 17.4):
            part(b, "y", x, CB, yb, z, h)
        part(b, "x", 5.92, xi0, -17.4, z, h)
        part(b, "x", 5.92, 17.4, xi1, z, h)
        b.put("Shop_StockShelf", -9.8, yb - 0.4, 0.0, z=z)
        b.put("Station_VendingMachine", 1.2, 3.5, 0.0, z=z)
        b.put("Shop_StockShelf", 11.7, yb - 0.4, 0.0, z=z)
        b.mark("spawn", -6.0, 2.1, z, 90.0, team="guest")
    b.mark("objective", -24.0 + 6 * 3 + 3.0, -4.4, LV[3], 0.0, note="the top-floor room (a target / a witness)")
    return {"note": "リゾートホテル: four storeys, 24 sea-view rooms (-Y) with balconies, the pool terrace on the sea "
                    "side, the lobby entrance under the porte-cochère on the land side (+Y)."}


# ── 倉庫 + ヤード: a warehouse on its fenced yard ──────────────────────────────────────────────────────────────────

def warehouse_yard(b):
    X0, X1, Y0, Y1 = -20.0, 20.0, 0.0, 24.0            # the warehouse; the yard is in front (-Y) of it
    H = 9.0
    OF = 4.0                                            # the office's upper floor
    xi0, xi1, yf, yb = X0 + EXT_T, X1 - EXT_T, Y0 + EXT_T, Y1 - EXT_T
    apron(b, -22.0, -26.0, 22.0, 24.0)
    # the yard's fence, gate and guard booth
    for x0_, x1_ in ((-22.0, -4.0), (4.0, 22.0)):
        b.box("Site", (x0_, -26.0, 0.0), (x1_, -25.9, 2.0), "MI_Steel")
    for x in (-22.0, 21.9):
        b.box("Site", (x, -26.0, 0.0), (x + 0.1, Y0, 2.0), "MI_Steel")
    b.box("Site", (5.0, -24.8, 0.0), (7.0, -22.8, 2.6), "MI_PaintWhite")             # the guard booth
    b.box("Site", (4.97, -24.4, 1.0), (5.0, -23.2, 2.0), "MI_Window")
    b.mark("spawn", 4.2, -23.8, 0.0, 180.0, team="guard")
    # two container trucks backed onto docks (COT1: the terminal's 20 ft ISO box on a tractor + chassis), drivable
    for u in (-12.0, -4.0):
        b.mark("vehicle", u, -6.3, 0.0, 180.0, vehicle="COT1", note="a container truck at the dock")
    b.mark("vehicle", 4.0, -7.5, 0.0, 180.0, vehicle="CRT1")
    b.mark("vehicle", 15.0, -18.0, 0.0, 0.0, vehicle="KET1")
    b.put("Warehouse_Pallet", 12.0, -4.0, 0.0, repeat=(4, 1.4, 0.0))
    b.put("Warehouse_Pallet", 12.0, -6.0, 0.0, repeat=(3, 1.4, 0.0))
    b.mark("cover", 13.0, -8.0, 0.0, 0.0)
    # the warehouse shell: three open loading docks (shutters raised), a personnel door
    docks = [(u, -1, 3.6, "", "open", 4.2) for u in (-12.0, -4.0, 4.0)]
    ext(b, X0, Y0, X1, Y1, 0.0, H, "MI_Corrugated", {
        "f": (docks + [(13.0, -1, 0.9, "swing", "exit")], [b.window(17.0, 0.0, 1.8, 1.0, 2.2)]),
        "b": ([(-15.0, 1, 0.9, "swing", "exit")], []),
        "l": ((), [Opening(3.0, 21.0, 6.0, 7.6, glass="MI_GlassClear", frame="MI_PaintedMetal")]),
        "r": ((), [Opening(3.0, 14.0, 6.0, 7.6, glass="MI_GlassClear", frame="MI_PaintedMetal")]),
    }, inner="MI_Corrugated")
    for u in (-12.0, -4.0, 4.0):
        b.box("Facade", (u - 1.9, Y0 - 0.45, 4.25), (u + 1.9, Y0, 4.85), "MI_PaintedMetalDark")
        b.box("Facade", (u - 2.4, Y0 - 3.0, 5.2), (u + 2.4, Y0, 5.35), "MI_PaintedMetal")        # dock canopy
    b.slab(X0, Y0, X1, Y1, 0.0, "MI_ConcreteSmooth")
    roof(b, X0, Y0, X1, Y1, H, parapet=0.6, units=0)
    sign(b, -6.0, 6.0, Y0 - 0.2, 6.3, 7.4)
    # pallet racks (aisles 3.5 m for the forklifts), forklifts, roll cages at the docks
    for y in (9.0, 14.0, 19.0):
        for x in (-17.2, -14.5, -11.8, -9.1, -6.4, -3.7, -1.0, 1.7):
            b.put("Warehouse_Rack", x, y - 0.55, 0.0)
            if y != 19.0:
                b.put("Warehouse_Rack", x, y + 0.55, 0.0)
    b.put("Warehouse_Forklift", -8.0, 4.0, 180.0)
    b.put("Warehouse_Forklift", 6.5, 12.0, 90.0)
    b.put("Warehouse_RollCage", 6.8, 2.2, 0.0, repeat=(5, 0.9, 0.0))
    b.put("Warehouse_Pallet", -15.5, 3.0, 0.0, repeat=(3, 1.4, 0.0))
    for x in (-8.0, 0.35):
        b.mark("cover", x, 11.5, 0.0, 90.0)
    b.mark("spawn", -10.0, 16.5, 0.0, 0.0, team="worker")
    # the two-storey office in the back-right corner (x 11 .. 19.8, y 16 .. 23.8), its stair in the hall
    ox0, oy0 = 11.0, 16.0
    part(b, "x", oy0, ox0, xi1, 0.0, OF - 0.2, doors=[(15.4, -1)], group="Walls_0")
    part(b, "y", ox0, oy0, yb, 0.0, OF - 0.2, group="Walls_0")
    part(b, "x", oy0, ox0, xi1, OF, 3.0, doors=[(13.6, -1)], group="Walls_4",
         wins=[Opening(15.0, 19.4, OF + 0.9, OF + 2.2, glass="MI_GlassClear", frame="MI_PaintedMetal")])
    part(b, "y", ox0, oy0, yb, OF, 3.0, group="Walls_4",
         wins=[Opening(17.0, 23.2, OF + 0.9, OF + 2.2, glass="MI_GlassClear", frame="MI_PaintedMetal")])
    b.slab(ox0, oy0, xi1, yb, OF, "MI_Fabric")
    b.slab(ox0, oy0, xi1, yb, OF + 3.2, "MI_ConcreteSmooth")
    well = (12.2, 8.6, 15.0, 14.4)
    b.ustair(*well, 0.0, OF, near="n", cap=False)
    b.slab(12.2, 14.4, 15.0, oy0, OF, "MI_Fabric")                                 # the upper landing
    b.box("Walls_4", (12.2, 14.4, OF), (12.26, oy0, OF + 1.1), "MI_Steel")
    b.put("Office_Desk", 13.5, 21.5, 0.0)
    b.put("Office_Chair", 13.5, 22.15, 180.0)
    b.put("Office_Locker", 19.4, 20.0, 270.0, repeat=(3, 0.0, 0.95))
    b.put("Rest_Table", 16.5, 18.6, 0.0)
    b.put("Office_DeskIsland", 16.0, 21.2, 0.0, z=OF)
    chairs_around(b, 16.0, 21.2, 2, 0.6, 0.85, z=OF)
    b.put("Office_Safe", 12.0, 23.3, 0.0, z=OF)
    b.put("Office_Cabinet", 19.4, 17.5, 270.0, z=OF)
    b.mark("objective", 12.0, 22.6, OF, 180.0, note="the yard office's safe")
    b.mark("spawn", 17.0, 19.0, OF, 0.0, team="worker")
    return {"note": "倉庫 + ヤード: a 40 x 24 x 9 m warehouse (racks, forklifts, three open docks) with a two-storey "
                    "office in its back-right corner, on a fenced yard (two container trucks and a crate truck at the docks, a guard booth)."}


# ── the military base's buildings (user, 2026-09-28): parts of the MilitaryBase site composite ─────────────────────

def mil_hq(b):
    """司令部庁舎: 44 x 18 m, two storeys (4.2 + 3.8)."""
    X0, X1, Y0, Y1 = -22.0, 22.0, -9.0, 9.0
    F1, F2, TOP = 0.0, 4.2, 8.0
    CF, CB = -1.0, 0.8
    xi0, xi1, yf, yb = X0 + EXT_T, X1 - EXT_T, Y0 + EXT_T, Y1 - EXT_T
    wellB = (xi0, CB + 0.06, -19.06, yb)
    wellA = (-3.94, CB + 0.06, -1.26, yb)
    hB = b.ustair(*wellB, F1, F2 - F1, near="s")
    hA = b.ustair(*wellA, F1, F2 - F1, near="s")
    b.ustair(*wellB, F2, TOP - F2, near="s", cap=True)
    hA2 = b.ustair(*wellA, F2, TOP - F2, near="s")
    shaft = b.lift(-5.0, CB + 0.875, 1.6, 1.6, [F1, F2], faces=1, turned=True)      # beside stair A (user, 2026-09-29)
    b.slab(X0, Y0, X1, Y1, F1, "MI_Terrazzo")
    b.slab(X0, Y0, X1, Y1, F2, "MI_Terrazzo", holes=[hB, hA, shaft])
    roof(b, X0, Y0, X1, Y1, TOP, holes=[hA2], units=4)
    stair_house(b, wellA[0], wellA[1], wellA[2], wellA[3], TOP)
    b.box("Roof", (15.0, 4.0, TOP), (15.3, 4.3, TOP + 10.0), "MI_Steel")                  # the radio mast
    ext(b, X0, Y0, X1, Y1, F1, F2 - F1, "MI_Olive", {
        "f": ([(-16.0, -1, 1.8, "slide", "exit")], band_windows(b, -10.0, 21.0, F1, 4.0, every=3.2, w=1.8)),
        "l": ([(-0.1, -1, 1.2, "swing", "exit")], []), "r": ([(-0.1, 1, 1.2, "swing", "exit")], [])})
    ext(b, X0, Y0, X1, Y1, F2, TOP - F2, "MI_Olive", {
        "f": ((), band_windows(b, xi0 + 0.5, xi1 - 0.5, F2, 3.6, every=3.2, w=1.8)),
        "b": ((), band_windows(b, 6.0, 21.0, F2, 3.6, every=3.2, w=1.6))})
    sign(b, -19.0, -13.0, Y0 - 0.2, 3.2, 3.8)
    # F1: entrance hall | operations room | offices | comms room ; back: WC | records | locker-armoury | break | store
    part(b, "x", CF, xi0, xi1, F1, 4.0, doors=[(-16.0, 1, 1.8, "", "open", 2.4), (-3.0, 1), (9.0, 1), (18.0, 1)])
    for x in (-10.0, 4.0, 14.0):
        part(b, "y", x, yf, CF, F1, 4.0)
    b.put("Office_Reception", -16.0, -4.2, 0.0)
    b.put("Office_Chair", -16.0, -3.4, 180.0)
    b.put("Station_Bench", -20.8, -6.0, 90.0)
    b.mark("spawn", -16.0, -3.0, F1, 180.0, team="soldier", note="the duty guard")
    for x in (-6.5, -2.0):
        b.put("Office_MeetingTable", x, -5.0, 0.0)
        for dx in (-1.0, 0.0, 1.0):
            b.put("Office_Chair", x + dx, -5.95, 0.0)
            b.put("Office_Chair", x + dx, -4.05, 180.0)
    b.put("Office_Whiteboard", -4.2, -8.4, 0.0)
    b.put("Office_ServerRack", 3.5, -7.5, 270.0, repeat=(2, 0.0, 1.1))
    b.mark("objective", -4.2, -5.0, F1, 0.0, note="the operations room (作戦室)")
    for x in (6.5, 11.5):
        b.put("Office_DeskIsland", x, -5.5, 0.0)
        chairs_around(b, x, -5.5, 2, 0.6, 0.85)
    b.put("Office_ServerRack", 15.0, -8.2, 0.0, repeat=(6, 1.1, 0.0))
    b.put("Office_Desk", 18.0, -4.2, 180.0)
    b.put("Office_Chair", 18.0, -4.9, 0.0)
    part(b, "x", CB, xi0, xi1, F1, 4.0, doors=[(-20.4, -1, 1.0), (-15.5, -1), (-8.0, -1), (-2.6, -1, 1.0),
                                             (-5.0, -1, 1.0, "", "open", 2.1), (2.5, -1), (10.0, -1), (18.0, -1)])
    for x in (-19.0, -12.0, -4.0, -1.2, 6.0, 14.0):
        part(b, "y", x, CB, yb, F1, 4.0)
    b.put("WC_Toilet", -17.0, yb - 0.38, 0.0)
    b.put("WC_Toilet", -14.0, yb - 0.38, 0.0)
    b.put("WC_Basin", -18.6, 3.0, 90.0)
    b.put("Office_Cabinet", -11.5, 5.0, 270.0, repeat=(3, 0.0, 0.95))
    b.put("Office_Cabinet", -4.5, 5.2, 270.0, repeat=(3, 0.0, 0.95))
    b.put("Police_GunLocker", 0.0, yb - 0.3, 0.0)
    b.put("Police_GunRack", 3.0, yb - 0.3, 0.0)
    b.mark("weapon", 0.0, 7.2, F1, 180.0, weapon="PIS1")
    b.mark("weapon", 3.0, 7.2, F1, 180.0, weapon="ASR1")
    b.put("Rest_Table", 10.0, 5.0, 0.0)
    b.put("Kitchen_Sink", 13.3, 5.0, 270.0)
    b.put("Shop_StockShelf", 18.0, yb - 0.4, 0.0)
    # F2: the commander's office | briefing room | staff offices ; back: WC | offices
    part(b, "x", CF, xi0, xi1, F2, 3.6, doors=[(-12.0, 1), (-3.0, 1), (12.0, 1)])
    for x in (-8.0, 6.0):
        part(b, "y", x, yf, CF, F2, 3.6)
    b.put("Office_Desk", -15.0, -7.8, 180.0, z=F2)
    b.put("Office_Chair", -15.0, -8.5, 0.0, z=F2)
    b.put("Office_Sofa", -19.8, -4.5, 90.0, z=F2)
    b.put("Rest_Table", -17.8, -4.5, 90.0, z=F2)
    b.put("Office_Safe", -9.0, -8.3, 0.0, z=F2)
    b.mark("spawn", -15.0, -6.8, F2, 180.0, team="vip", note="the base commander")
    b.mark("objective", -9.0, -7.6, F2, 180.0, note="the commander's safe")
    b.put("Office_MeetingTable", -1.0, -5.0, 0.0, z=F2)
    for dx in (-1.0, 0.0, 1.0):
        b.put("Office_Chair", -1.0 + dx, -5.95, 0.0, z=F2)
        b.put("Office_Chair", -1.0 + dx, -4.05, 180.0, z=F2)
    b.put("Office_Whiteboard", -1.0, -8.4, 0.0, z=F2)
    for x in (9.5, 15.5):
        b.put("Office_DeskIsland", x, -5.5, 0.0, z=F2)
        chairs_around(b, x, -5.5, 2, 0.6, 0.85, z=F2)
    b.mark("spawn", 12.0, -3.0, F2, 0.0, team="soldier")
    part(b, "x", CB, xi0, xi1, F2, 3.6, doors=[(-20.4, -1, 1.0), (-15.5, -1), (-8.0, -1), (-2.6, -1, 1.0),
                                             (-5.0, -1, 1.0, "", "open", 2.1), (2.5, -1), (10.0, -1), (18.0, -1)])
    for x in (-19.0, -12.0, -4.0, -1.2, 6.0, 14.0):
        part(b, "y", x, CB, yb, F2, 3.6)
    b.put("WC_Toilet", -17.0, yb - 0.38, 0.0, z=F2)
    b.put("Office_Desk", -8.0, 6.5, 0.0, z=F2)
    b.put("Office_DeskIsland", 10.0, 4.8, 0.0, z=F2)
    b.put("Office_Cabinet", 18.0, yb - 0.3, 0.0, z=F2)
    return {"note": "司令部庁舎 (base HQ): operations room, comms room, a small ready-arms locker on the ground floor; "
                    "the commander's office (safe), the briefing room upstairs."}


def mil_barracks(b):
    """隊舎: 48 x 16 m, two storeys (4.0 + 4.0): the mess hall and kitchen below, four bunk rooms above."""
    X0, X1, Y0, Y1 = -24.0, 24.0, -8.0, 8.0
    F1, F2, TOP = 0.0, 4.0, 8.0
    CF, CB = 0.2, 1.8
    xi0, xi1, yf, yb = X0 + EXT_T, X1 - EXT_T, Y0 + EXT_T, Y1 - EXT_T
    wellB = (xi0, CB + 0.06, -21.06, yb)
    wellA = (21.06, CB + 0.06, xi1, yb)
    hB = b.ustair(*wellB, F1, F2 - F1, near="s")
    hA = b.ustair(*wellA, F1, F2 - F1, near="s")
    b.ustair(*wellB, F2, TOP - F2, near="s", cap=True)
    b.ustair(*wellA, F2, TOP - F2, near="s", cap=True)
    shaft = b.lift(19.9, CB + 0.875, 1.6, 1.6, [F1, F2], faces=1, turned=True)      # beside the east stair
    b.slab(X0, Y0, X1, Y1, F1, "MI_Terrazzo")
    b.slab(X0, Y0, X1, Y1, F2, "MI_Terrazzo", holes=[hB, hA, shaft])
    roof(b, X0, Y0, X1, Y1, TOP, units=6)
    ext(b, X0, Y0, X1, Y1, F1, F2 - F1, "MI_TileBeige", {
        "f": ([(-12.0, -1, 1.8, "swing", "exit")], band_windows(b, xi0 + 0.5, xi1 - 0.5, F1, 3.8, every=3.0,
                                                                w=1.6, skip=(-12.0,))),
        "l": ([(1.0, -1, 1.2, "swing", "exit")], []), "r": ([(1.0, 1, 1.2, "swing", "exit")], [])})
    ext(b, X0, Y0, X1, Y1, F2, TOP - F2, "MI_TileBeige", {
        "f": ((), band_windows(b, xi0 + 0.5, xi1 - 0.5, F2, 3.8, every=3.0, w=1.6))})
    back = [(-22.4, -1, 1.0), (-17.0, -1), (-9.0, -1), (-2.0, -1), (6.0, -1), (15.0, -1),
            (19.9, -1, 1.0, "", "open", 2.1), (22.4, -1, 1.0)]
    backx = (-21.0, -13.0, -5.0, 1.0, 11.0, 21.0)
    # F1: mess hall | kitchen | recreation room ; back: showers | WC | store | lockers | laundry
    part(b, "x", CF, xi0, xi1, F1, 3.8, doors=[(-12.0, 1, 2.0, "", "open", 2.4), (5.0, 1), (17.0, 1)])
    part(b, "y", 0.0, yf, CF, F1, 3.8, doors=[(-3.0, -1)])
    part(b, "y", 10.0, yf, CF, F1, 3.8)
    for x in (-21.0, -17.0, -13.0, -9.0, -5.0):
        for y in (-5.6, -2.4):
            b.put("Rest_Table", x, y, 0.0)
            for dx in (-0.35, 0.35):
                b.put("Rest_Chair", x + dx, y - 0.75, 0.0)
                b.put("Rest_Chair", x + dx, y + 0.75, 180.0)
    b.mark("spawn", -12.0, -1.0, F1, 0.0, team="soldier")
    for x in (1.5, 3.2):
        b.put("Kitchen_Grill", x, yf + 0.4, 0.0)
    b.put("Kitchen_Fryer", 4.7, yf + 0.4, 0.0)
    b.put("Kitchen_Sink", 7.8, yf + 0.45, 0.0)
    b.put("Kitchen_PrepTable", 5.0, -3.8, 0.0)
    b.put("Kitchen_Fridge", 9.4, -3.6, 270.0)
    for x, r in ((13.0, 90.0), (21.0, 270.0)):
        b.put("Office_Sofa", x, -3.5, r)
    b.put("Rest_Table", 17.0, -3.5, 0.0)
    part(b, "x", CB, xi0, xi1, F1, 3.8, doors=back)
    for x in backx:
        part(b, "y", x, CB, yb, F1, 3.8)
    for x in (-19.0, -15.0):
        b.put("WC_Basin", x, yb - 0.3, 0.0)
    b.put("WC_Toilet", -11.0, yb - 0.38, 0.0)
    b.put("WC_Toilet", -7.0, yb - 0.38, 0.0)
    b.put("Shop_StockShelf", -2.0, yb - 0.4, 0.0)
    b.put("Office_Locker", 3.5, yb - 0.3, 0.0, repeat=(5, 0.95, 0.0))
    b.put("Shop_StockShelf", 14.0, yb - 0.4, 0.0)
    # F2: four bunk rooms ; back: showers, WC, store, lockers
    rooms = [(xi0, -12.0), (-12.0, 0.0), (0.0, 12.0), (12.0, xi1)]
    part(b, "x", CF, xi0, xi1, F2, 3.8, doors=[((a + c) / 2, 1) for a, c in rooms])
    for a, c in rooms[:-1]:
        part(b, "y", c, yf, CF, F2, 3.8)
    for a, c in rooms:
        for k in range(4):
            b.put("Fire_Bunk", a + 1.6 + k * 2.4, -6.3, 0.0, z=F2)
        b.put("Office_Locker", (a + c) / 2 + 2.6, -2.0, 180.0, repeat=(2, 0.95, 0.0), z=F2)
        b.mark("spawn", (a + c) / 2 - 2.0, -3.4, F2, 0.0, team="soldier")
    part(b, "x", CB, xi0, xi1, F2, 3.8, doors=back)
    for x in backx:
        part(b, "y", x, CB, yb, F2, 3.8)
    b.put("WC_Toilet", -11.0, yb - 0.38, 0.0, z=F2)
    b.put("Shop_StockShelf", -2.0, yb - 0.4, 0.0, z=F2)
    return {"note": "隊舎 (barracks): the mess hall, kitchen and recreation room below; four 8-bunk rooms above."}


def mil_armoury(b):
    """武器庫: a 24 x 16 m single-storey bunker, 0.5 m walls, a vault door, an issue cage, the COMPLETE armoury."""
    X0, X1, Y0, Y1 = -12.0, 12.0, -8.0, 8.0
    H = 4.2
    T = 0.5
    b.slab(X0, Y0, X1, Y1, 0.0, "MI_ConcreteSmooth")
    ext(b, X0, Y0, X1, Y1, 0.0, H + 0.4, "MI_ConcreteSmooth", {"f": ([(0.0, -1, 1.6, "swing", "exit", 2.4)], [])},
        t=T, inner="MI_ConcreteSmooth")
    b.slab(X0 - 0.5, Y0 - 0.5, X1 + 0.5, Y1 + 0.5, H + 1.0, "MI_ConcreteSmooth", t=1.0, group="Roof")
    b.box("Facade", (-2.0, Y0 - 0.25, 2.6), (2.0, Y0, 3.2), "MI_PaintYellow")                  # the hazard band
    # the issue cage across the front: a counter window and the cage door
    part(b, "x", -4.0, X0 + T, X1 - T, 0.0, H, doors=[(-6.0, 1, 0.9, "swing", "door")],
         wins=[Opening(-2.0, 6.0, 1.0, 2.4, glass=None)], mat="MI_Steel")
    b.put("Shop_Counter", 2.0, -4.5, 180.0)
    b.put("Office_Desk", -9.5, -6.3, 90.0)
    b.mark("spawn", 2.0, -3.3, 0.0, 180.0, team="soldier", note="the armourer, behind the cage")
    # the vault: long-gun racks along both side walls, pistol lockers and shields on the back wall, ammunition shelves
    for y in (-2.4, -0.3, 1.8, 3.9, 6.0):
        b.put("Police_GunRack", X0 + T + 0.3, y, 90.0)
        b.put("Police_GunRack", X1 - T - 0.3, y, 270.0)
    b.put("Police_GunLocker", -4.0, Y1 - T - 0.3, 0.0, repeat=(3, 1.1, 0.0))
    b.put("Police_ShieldRack", 3.0, Y1 - T - 0.3, 0.0)
    b.put("Police_ShieldRack", 5.0, Y1 - T - 0.3, 0.0)
    for y in (0.5, 3.6):
        b.put("Shop_StockShelf", 0.0, y, 90.0)
    b.put("Warehouse_Pallet", -7.5, 5.5, 0.0)
    b.put("Warehouse_Pallet", 7.5, 5.5, 0.0)
    left = ("ASR1", "ASR1", "ASR2", "SMG1", "SMG1")
    right = ("SHG1", "SNR1", "ATL1", "ATL1", "SHG1")
    for i, y in enumerate((-2.4, -0.3, 1.8, 3.9, 6.0)):
        b.mark("weapon", X0 + T + 1.1, y, 0.0, 90.0, weapon=left[i])
        b.mark("weapon", X1 - T - 1.1, y, 0.0, 270.0, weapon=right[i])
    for i, w in enumerate(("PIS1", "PIS2", "REV1", "DUP1")):
        b.mark("weapon", -4.4 + i * 0.9, 6.3, 0.0, 180.0, weapon=w)
    for i, w in enumerate(("FRG1", "FRG1", "PIB1", "FLA1", "SMO1", "REC1", "MEW1")):
        b.mark("weapon", -1.2 + (i % 2) * 2.4, -1.4 + (i // 2) * 1.3, 0.0, 0.0, weapon=w)
    return {"note": "武器庫 (armoury bunker): the COMPLETE military armoury -- rifles, SMGs, shotguns, a sniper rifle, "
                    "launchers, pistols, grenades, flash / smoke, the remote charge, a knife (MARK_weapon each)."}


def mil_hangar(b):
    """格納庫: 44 x 36 x 12 m, an open 30 m door at the front (-Y), two flyable FIJ1 jets, workshops along the back
    and a mezzanine office above them up an open stair."""
    X0, X1, Y0, Y1 = -22.0, 22.0, -18.0, 18.0
    H = 12.0
    xi0, xi1, yf, yb = X0 + EXT_T, X1 - EXT_T, Y0 + EXT_T, Y1 - EXT_T
    b.slab(X0, Y0, X1, Y1, 0.0, "MI_ConcreteSmooth")
    ext(b, X0, Y0, X1, Y1, 0.0, H, "MI_Corrugated", {
        "f": ([(0.0, -1, 30.0, "", "open", 9.0)], []),
        "l": ([(12.0, -1, 0.9, "swing", "exit")], [Opening(-14.0, 8.0, 8.0, 10.5, glass="MI_GlassClear")]),
        "r": ([(12.0, 1, 0.9, "swing", "exit")], [Opening(-14.0, 8.0, 8.0, 10.5, glass="MI_GlassClear")]),
    }, inner="MI_Corrugated")
    roof(b, X0, Y0, X1, Y1, H, parapet=0.5)
    for x0, x1 in ((-21.8, -15.0), (15.0, 21.8)):          # the hangar door leaves, slid open to both sides
        b.box("Facade", (x0, Y0 - 0.5, 0.0), (x1, Y0 - 0.3, 9.4), "MI_PaintedMetal")
    b.box("Facade", (-15.5, Y0 - 0.6, 9.0), (15.5, Y0, 9.6), "MI_PaintedMetalDark")
    for x in (-9.5, 9.5):
        b.mark("vehicle", x, -3.0, 0.0, 180.0, vehicle="FIJ1", faction="military")
    b.mark("cover", 0.0, -6.0, 0.0, 180.0)
    b.put("Warehouse_Forklift", -18.0, -12.0, 90.0)
    b.put("Shop_StockShelf", xi0 + 0.4, 0.0, 90.0, repeat=(2, 0.0, 3.3))
    b.put("Warehouse_Pallet", 18.5, -8.0, 0.0, repeat=(2, 0.0, 1.4))
    # workshops along the back (y 11.5 .. 17.8), the mezzanine office above them
    WY = 11.5
    part(b, "x", WY, xi0, xi1, 0.0, 4.0 - 0.2, doors=[(-15.0, -1), (-3.0, -1), (9.0, -1)])
    for x in (-8.0, 4.0):
        part(b, "y", x, WY, yb, 0.0, 4.0 - 0.2)
    b.put("Kitchen_PrepTable", -15.0, 16.8, 0.0)
    b.put("Shop_StockShelf", -2.0, 17.3, 0.0)
    b.put("Office_Locker", 9.0, yb - 0.3, 0.0, repeat=(4, 0.95, 0.0))
    b.mark("spawn", -3.0, 10.0, 0.0, 180.0, team="soldier", note="ground crew")
    b.slab(xi0, WY - 0.06, xi1, yb, 4.0, "MI_Fabric")
    part(b, "x", WY, xi0, xi1, 4.0, 3.2, doors=[(18.5, -1)],
         wins=[Opening(-19.0, 14.0, 4.9, 6.4, glass="MI_GlassClear", frame="MI_PaintedMetal")])
    well = (16.8, 5.1, 19.6, WY - 0.06)
    b.ustair(*well, 0.0, 4.0, near="n")
    b.slab(16.8, WY - 1.46, 19.6, WY - 0.06, 4.0, "MI_Fabric")                    # the upper landing's floor
    b.put("Office_DeskIsland", -6.0, 14.5, 0.0, z=4.0)
    chairs_around(b, -6.0, 14.5, 2, 0.6, 0.85, z=4.0)
    b.put("Office_Desk", 6.0, 15.0, 0.0, z=4.0)
    b.put("Office_Chair", 6.0, 14.35, 180.0, z=4.0)
    b.mark("spawn", 0.0, 13.0, 4.0, 180.0, team="soldier", note="the flight office")
    return {"note": "格納庫 (fighter hangar): two flyable FIJ1 jets on MARK_vehicle, workshops, the flight office "
                    "on the mezzanine."}


def mil_control_tower(b):
    """管制塔: a 20 x 12 m operations building with an 8 x 8 m tower rising to a glass cab at 20 m."""
    X0, X1, Y0, Y1 = -10.0, 10.0, -6.0, 6.0
    TX0, TX1, TY0, TY1 = 2.0, 10.0, -2.0, 6.0                    # the tower (the building's back-right corner)
    LV = [0.0, 4.0, 8.0, 12.0, 16.0, 20.0]
    b.slab(X0, Y0, X1, Y1, 0.0, "MI_Terrazzo")
    ext(b, X0, Y0, X1, Y1, 0.0, 4.2, "MI_PaintWhite", {
        "f": ([(-6.0, -1, 1.8, "slide", "exit")], band_windows(b, -3.0, 9.0, 0.0, 3.8, every=3.0, w=2.0)),
        "l": ((), band_windows(b, -4.0, 4.0, 0.0, 3.8, every=3.0, w=1.6))})
    b.slab(X0, Y0, TX0 + 0.2, Y1, 4.2, "MI_ConcreteSmooth", group="Roof")
    b.slab(TX0, Y0, X1, TY0 + 0.2, 4.2, "MI_ConcreteSmooth", group="Roof")
    b.parapet(X0, Y0, X1, Y1, 4.2, 0.8)
    part(b, "y", TX0, TY0, Y1 - EXT_T, 0.0, 4.0, doors=[(-1.0, -1, 1.0)])
    part(b, "x", TY0, TX0, X1 - EXT_T, 0.0, 4.0)
    b.put("Office_DeskIsland", -4.0, 1.0, 0.0)
    chairs_around(b, -4.0, 1.0, 2, 0.6, 0.85)
    b.put("Office_ServerRack", -9.4, 4.0, 90.0)
    b.mark("spawn", -4.0, -2.5, 0.0, 180.0, team="soldier")
    # the tower shaft: walls from the building roof up to the cab, a U-stair inside, landings at each level
    well = (TX0 + 0.3, TY0 + 0.3, TX0 + 3.1, TY1 - 0.3)
    holes = []
    for i in range(len(LV) - 1):
        holes.append(b.ustair(*well, LV[i], LV[i + 1] - LV[i], near="s", cap=(i == len(LV) - 2)))
    shaft = b.lift(TX0 + 5.9, TY0 + 2.3, 1.6, 1.6, LV, faces=1, turned=True)      # beside the stair, to the cab
    for i, z in enumerate(LV[1:-1]):
        b.slab(TX0, TY0, TX1, TY1, z, "MI_ConcreteSmooth", holes=[holes[i], shaft])
    for s, axis, c, a0, a1, sgn in (("f", "x", TY0 + 0.1, TX0, TX1, -1), ("b", "x", TY1 - 0.1, TX0, TX1, 1),
                                    ("l", "y", TX0 + 0.1, TY0 + 0.2, TY1 - 0.2, -1), ("r", "y", TX1 - 0.1, TY0 + 0.2, TY1 - 0.2, 1)):
        ops = [Opening(((a0 + a1) / 2) - 0.4, ((a0 + a1) / 2) + 0.4, z + 1.4, z + 2.4, glass="MI_GlassClear")
               for z in LV[1:-1]] if s in "fr" else []
        b.wall(axis, c, a0, a1, 4.2, LV[-1] - 4.2, 0.2, "MI_Plaster", mat_out="MI_PaintWhite", out_sign=sgn, ops=ops,
               group="Facade")
    # the CAB: a 10 x 10 m glass room overhanging the shaft, consoles round its windows, a roof
    CX0, CX1, CY0, CY1 = TX0 - 1.0, TX1 + 1.0, TY0 - 1.0, TY1 + 1.0
    b.slab(CX0, CY0, CX1, CY1, LV[-1], "MI_Fabric", holes=[holes[-1], shaft])
    for s, axis, c, a0, a1 in (("f", "x", CY0 + 0.1, CX0, CX1), ("b", "x", CY1 - 0.1, CX0, CX1),
                               ("l", "y", CX0 + 0.1, CY0 + 0.2, CY1 - 0.2), ("r", "y", CX1 - 0.1, CY0 + 0.2, CY1 - 0.2)):
        b.wall(axis, c, a0, a1, LV[-1], 3.2, 0.2, "MI_PaintWhite",
               ops=[Opening(a0 + 0.3, a1 - 0.3, LV[-1] + 1.0, LV[-1] + 3.0, glass="MI_GlassClear",
                            frame="MI_PaintedMetal")], group="Facade")
    b.box("Roof", (CX0 - 0.6, CY0 - 0.6, LV[-1] + 3.2), (CX1 + 0.6, CY1 + 0.6, LV[-1] + 3.5), "MI_PaintWhite")
    b.box("Roof", (5.8, 1.8, LV[-1] + 3.5), (6.2, 2.2, LV[-1] + 6.0), "MI_Steel")                 # the radar mast
    for x in (7.0, 9.3):
        b.put("Office_Desk", x, CY0 + 0.6, 180.0, z=LV[-1])
    b.put("Office_Desk", CX1 - 0.6, 3.0, 270.0, z=LV[-1])
    b.put("Office_Chair", 7.0, CY0 + 1.3, 0.0, z=LV[-1])
    b.mark("spawn", 7.5, 2.0, LV[-1], 180.0, team="soldier", note="the controller in the cab")
    b.mark("cover", 9.0, CY1 - 1.0, LV[-1], 0.0, note="a sniper's view over the airfield")
    return {"note": "管制塔 (control tower): an operations room below, a stair and a lift up five levels, the glass cab "
                    "at 20 m (a sniper spot)."}


# ── the airport (user, 2026-09-28: "detailed airplane terminal / airplane hangar ... in the same fashion") ────────

def _enclose_well(b, well, near, z, h):
    """Walls round a stair well on the three sides away from its `near` landing strip (the landing stays open)."""
    x0, y0, x1, y1 = well
    t = PART_T
    if near == "s":
        part(b, "y", x0 - t / 2, y0 + IK.STAIR_NEAR, y1, z, h)
        part(b, "y", x1 + t / 2, y0 + IK.STAIR_NEAR, y1, z, h)
        part(b, "x", y1 + t / 2, x0 - t, x1 + t, z, h)
    else:
        part(b, "y", x0 - t / 2, y0, y1 - IK.STAIR_NEAR, z, h)
        part(b, "y", x1 + t / 2, y0, y1 - IK.STAIR_NEAR, z, h)
        part(b, "x", y0 - t / 2, x0 - t, x1 + t, z, h)


def airport_terminal(b):
    """空港ターミナル: a regional terminal (地方空港 class), 150 x 50 m, two storeys of 6 m. Landside (-Y) the curb and
    its canopy; F1 arrivals (arrivals hall, car hire, konbini, the baggage hall with two carousels, the airport police
    box, operations); F2 departures (check-in islands, self check-in, the security line, the airside lounge with gate
    seating, a shop and a cafe, four gates onto boarding bridges with a service stair down to the apron)."""
    X0, X1, Y0, Y1 = -75.0, 75.0, -25.0, 25.0
    F1, F2, TOP = 0.0, 6.0, 12.0
    xi0, xi1, yf, yb = X0 + EXT_T, X1 - EXT_T, Y0 + EXT_T, Y1 - EXT_T
    GATES = (-52.0, -17.0, 17.0, 52.0)
    wellW = (xi0, yf, xi0 + 2.8, yf + 7.4)
    wellE = (xi1 - 2.8, yf, xi1, yf + 7.4)
    wellC = (69.0, yb - 7.4, 71.8, yb)                      # airside: the lounge down to the arrivals corridor
    hW = b.ustair(*wellW, F1, F2 - F1, near="s", cap=True)
    hE = b.ustair(*wellE, F1, F2 - F1, near="s", cap=True)
    hC = b.ustair(*wellC, F1, F2 - F1, near="n", cap=True)
    lL = b.lift(0.0, -21.0, 2.0, 2.0, [F1, F2], faces=1)
    lA = b.lift(0.0, 20.0, 2.0, 2.0, [F1, F2], faces=1)
    b.slab(X0, Y0, X1, Y1, F1, "MI_Terrazzo")
    b.slab(X0, Y0, X1, Y1, F2, "MI_Terrazzo", holes=[hW, hE, hC, lL, lA])
    roof(b, X0, Y0, X1, Y1, TOP, parapet=0.8, units=8)
    for well, near in ((wellW, "s"), (wellE, "s"), (wellC, "n")):
        for z in (F1, F2):
            _enclose_well(b, well, near, z, F2 - F1 - 0.2)
    # the shell: glass landside and airside, the curb canopy on its columns
    gaps = [(-74.3, -46.5), (-43.5, -16.5), (-13.5, 13.5), (16.5, 43.5), (46.5, 74.3)]
    ext(b, X0, Y0, X1, Y1, F1, F2 - F1, "MI_PaintedMetal", {
        "f": ([(x, -1, 2.4, "slide", "exit") for x in (-45.0, -15.0, 15.0, 45.0)],
              [Opening(a, c, 0.3, 4.8, glass="MI_GlassClear", frame="MI_PaintedMetal") for a, c in gaps]),
        "b": ([(-55.0, 1, 3.0, "swing", "exit"), (50.0, 1, 1.2, "swing", "exit")], []),
        "l": ((), band_windows(b, yf + 9.0, yb - 2.0, F1, 5.8, every=4.0, w=2.4)),
        "r": ((), band_windows(b, yf + 9.0, yb - 9.0, F1, 5.8, every=4.0, w=2.4))})
    ribbon = [Opening(xi0 + 0.4, xi1 - 0.4, F2 + 0.3, F2 + 5.2, glass="MI_GlassClear", frame="MI_PaintedMetal")]
    airside = []
    cur = xi0 + 0.4
    for g in GATES:
        airside.append(Opening(cur, g - 1.4, F2 + 0.3, F2 + 5.2, glass="MI_GlassClear", frame="MI_PaintedMetal"))
        cur = g + 1.4
    airside.append(Opening(cur, xi1 - 0.4, F2 + 0.3, F2 + 5.2, glass="MI_GlassClear", frame="MI_PaintedMetal"))
    ext(b, X0, Y0, X1, Y1, F2, TOP - F2, "MI_PaintedMetal", {
        "f": ((), ribbon), "b": ([(g, 1, 1.8, "swing", "exit") for g in GATES], airside)})
    b.box("Facade", (X0 + 4.0, Y0 - 9.0, 5.2), (X1 - 4.0, Y0, 5.5), "MI_PaintWhite")          # the curb canopy
    for x in range(-66, 67, 12):
        b.box("Facade", (x - 0.25, Y0 - 8.5, 0.0), (x + 0.25, Y0 - 8.0, 5.2), "MI_PaintedMetal")
    sign(b, -20.0, 20.0, Y0 - 0.2, 10.4, 11.6)
    # ── F1 arrivals: the hall (landside), the baggage hall behind glass, the airside corridor and back rooms
    h1 = F2 - F1 - 0.2
    glass_part(b, "x", -5.0, xi0 + 3.0, xi1 - 3.0, F1, h1, doors=[(-20.0, -1, 3.0, "", "open", 2.6),
                                                                (20.0, -1, 3.0, "", "open", 2.6)])
    part(b, "x", 15.0, xi0, xi1, F1, h1, doors=[(-45.0, -1, 3.0, "", "open", 2.6), (45.0, -1, 3.0, "", "open", 2.6)])
    for x, y in ((-36.0, -8.0), (36.0, -8.0)):
        pass
    b.put("Shop_Counter", -60.0, -7.3, 180.0, repeat=(4, 2.2, 0.0))                  # car hire desks
    b.put("Office_Reception", -8.0, -7.6, 180.0)                                      # the information desk
    b.put("Office_Chair", -8.0, -6.9, 0.0)
    for x in (-36.0, 28.0):
        b.put("Station_Bench", x, -15.0, 0.0, repeat=(4, 2.2, 0.0))
        b.put("Station_Bench", x, -12.5, 180.0, repeat=(4, 2.2, 0.0))
    b.put("Station_TicketMachine", -30.0, -7.2, 180.0, repeat=(3, 1.2, 0.0))            # bus tickets
    b.put("Station_VendingMachine", 8.0, -7.2, 180.0, repeat=(3, 1.1, 0.0))
    for y in (-16.0, -12.0):                                                            # the konbini corner
        b.put("Shop_Gondola", 58.0, y, 90.0)
    b.put("Shop_FridgeDoor", 64.0, -7.3, 180.0, repeat=(4, 0.91, 0.0))
    b.put("Shop_Register", 52.0, -18.0, 0.0)
    b.mark("spawn", -8.0, -10.0, F1, 180.0, team="civilian", note="arrivals hall")
    for cx in (-30.0, 30.0):                                                            # the two carousels
        b.box("Fittings", (cx - 10.0, 3.0, 0.0), (cx + 10.0, 6.0, 0.55), "MI_Steel")
        b.box("Fittings", (cx - 10.3, 2.7, 0.55), (cx + 10.3, 6.3, 0.72), "MI_PaintedMetalDark")
        b.box("Fittings", (cx - 1.0, 6.0, 0.0), (cx + 1.0, 14.9, 1.4), "MI_Steel")          # the feed belt
        b.put("Shop_CartRow", cx, 12.0, 90.0)
    b.mark("cover", 0.0, 4.5, F1, 0.0, note="between the carousels")
    # the airside strip (y 15..25): operations (the apron door), the airport police box, the corridor to the stair
    part(b, "y", -40.0, 15.0, yb, F1, h1, doors=[(20.0, -1)])
    part(b, "y", -26.0, 15.0, yb, F1, h1, doors=[(20.0, 1)])
    b.put("Office_Desk", -65.0, 21.0, 0.0)
    b.put("Office_Chair", -65.0, 20.35, 180.0)
    b.put("Warehouse_Pallet", -48.0, 23.0, 0.0)
    b.mark("spawn", -60.0, 18.0, F1, 0.0, team="worker", note="baggage handlers")
    b.put("Office_Desk", -33.0, 23.2, 0.0)
    b.put("Office_Chair", -33.0, 22.55, 180.0)
    b.put("Police_GunLocker", -28.0, yb - 0.3, 0.0)
    b.put("Police_ShieldRack", -37.8, 17.5, 90.0)
    b.mark("spawn", -33.0, 19.0, F1, 0.0, team="police", note="the airport police box")
    b.mark("weapon", -28.0, 23.6, F1, 180.0, weapon="PIS1")
    b.mark("weapon", -29.0, 23.6, F1, 180.0, weapon="SMG1")
    # ── F2 departures: check-in (landside), the security line, the airside lounge and the gates
    h2 = TOP - F2 - 0.2
    glass_part(b, "x", 0.0, xi0 + 3.0, xi1 - 3.0, F2, h2, doors=[(x, 1, 1.2, "", "open", 2.2)
                                                             for x in (-9.0, -3.0, 3.0, 9.0)])
    for x in (-9.0, -3.0, 3.0, 9.0):                                                   # the walk-through arches
        b.box("Fittings", (x - 0.8, -0.3, F2), (x - 0.62, 0.3, F2 + 2.3), "MI_PlasticWhite")
        b.box("Fittings", (x + 0.62, -0.3, F2), (x + 0.8, 0.3, F2 + 2.3), "MI_PlasticWhite")
        b.box("Fittings", (x - 0.8, -0.3, F2 + 2.2), (x + 0.8, 0.3, F2 + 2.4), "MI_PlasticWhite")
        b.box("Fittings", (x + 1.2, -4.5, F2), (x + 2.0, -0.2, F2 + 0.8), "MI_Steel")      # the X-ray belt
    b.mark("spawn", 0.0, 2.0, F2, 180.0, team="police", note="the security line")
    for x0 in (-55.0, -30.0, 18.0, 43.0):                                              # four check-in islands
        b.put("Shop_Counter", x0, -12.0, 180.0, z=F2, repeat=(5, 2.4, 0.0))
        b.box("Fittings", (x0 - 1.0, -10.8, F2), (x0 + 10.6, -10.2, F2 + 0.6), "MI_Steel")  # the bag belt
    b.put("Station_TicketMachine", -20.0, -20.0, 0.0, z=F2, repeat=(6, 1.2, 0.0))       # self check-in
    b.put("Station_TicketMachine", 12.0, -20.0, 0.0, z=F2, repeat=(4, 1.2, 0.0))
    b.mark("spawn", 20.0, -16.0, F2, 180.0, team="civilian", note="check-in hall")
    # the lounge: gate seating, a shop (west) and a cafe (east)
    part(b, "y", -62.0, 0.1, yb, F2, h2, doors=[(12.0, 1, 3.0, "", "open", 2.6)])
    for y in (5.0, 9.0):
        b.put("Shop_Gondola", -68.0, y, 90.0, z=F2)
    b.put("Shop_Register", -64.0, 3.0, 90.0, z=F2)
    for g in GATES:
        for y in (12.0, 15.5):
            b.put("Station_Bench", g - 6.6, y, 0.0, z=F2, repeat=(4, 2.2, 0.0))
        b.put("Office_Reception", g, 21.5, 0.0, z=F2)                                   # the gate podium
        b.mark("spawn", g + 3.0, 18.0, F2, 0.0, team="civilian")
    for x, y in ((60.0, 5.0), (60.0, 9.0), (64.0, 5.0), (64.0, 9.0)):
        b.put("Rest_Table", x, y, 0.0, z=F2)
        b.put("Rest_Chair", x, y - 0.75, 0.0, z=F2)
        b.put("Rest_Chair", x, y + 0.75, 180.0, z=F2)
    b.put("Shop_Counter", 66.0, 13.0, 90.0, z=F2)
    b.mark("objective", -17.0, 20.0, F2, 0.0, note="gate 2")
    # the boarding bridges: a 3.2 m enclosed walkway at F2 out 18 m, a service stair down to the apron at its end
    for g in GATES:
        b.slab(g - 1.6, Y1, g + 1.6, Y1 + 18.0, F2, "MI_Fabric", group="Bridges")
        for sx in (-1, 1):
            b.wall("y", g + sx * 1.525, Y1, Y1 + 18.0, F2, 2.6, 0.15, "MI_PaintedMetal", group="Bridges",
                   ops=[Opening(Y1 + 1.0, Y1 + 17.0, F2 + 1.0, F2 + 2.1, glass="MI_GlassClear")])
        b.box("Bridges", (g - 1.6, Y1, F2 + 2.6), (g + 1.6, Y1 + 18.0, F2 + 2.8), "MI_PaintedMetal")
        b.box("Bridges", (g - 0.3, Y1 + 12.0, 0.0), (g + 0.3, Y1 + 12.6, F2 - 0.2), "MI_Steel")   # the rotunda leg
        tower = (g - 1.4, Y1 + 18.0, g + 1.4, Y1 + 25.4)
        b.ustair(*tower, F1, F2 - F1, near="s", cap=True)
        b.slab(g - 1.6, Y1 + 18.0, g + 1.6, Y1 + 18.0 + IK.STAIR_NEAR, F2, "MI_Steel", group="Bridges")
        b.box("Bridges", (g - 1.6, Y1 + 25.4, F2 - 0.2), (g + 1.6, Y1 + 25.6, F2 + 1.1), "MI_Steel")  # the guard
    return {"note": "空港ターミナル (airport terminal): F1 arrivals (baggage hall, car hire, konbini, the airport police "
                    "box with light arms); F2 departures (check-in, security, the lounge, four gates on boarding "
                    "bridges with a stair down to the apron). Two lifts, three stairs."}


def airport_hangar(b):
    """整備格納庫: a 70 x 60 x 22 m hangar for one narrow-body airliner (the airliner is the site's own prop), its
    front (-Y) open 56 m wide; a LIP1 light plane parked beside it; workshops, a parts store and the crew room along
    the back, the engineering office above them up a stair."""
    X0, X1, Y0, Y1 = -35.0, 35.0, -30.0, 30.0
    H = 22.0
    OY = 23.0
    xi0, xi1, yf, yb = X0 + EXT_T, X1 - EXT_T, Y0 + EXT_T, Y1 - EXT_T
    b.slab(X0, Y0, X1, Y1, 0.0, "MI_ConcreteSmooth")
    ext(b, X0, Y0, X1, Y1, 0.0, H, "MI_Corrugated", {
        "f": ([(0.0, -1, 56.0, "", "open", 18.0)], []),
        "l": ([(12.0, -1, 0.9, "swing", "exit")], [Opening(-25.0, 8.0, 14.0, 20.0, glass="MI_GlassClear")]),
        "r": ([(12.0, 1, 0.9, "swing", "exit")], [Opening(-25.0, 8.0, 14.0, 20.0, glass="MI_GlassClear")]),
    }, inner="MI_Corrugated")
    roof(b, X0, Y0, X1, Y1, H, parapet=0.6)
    for x0, x1 in ((-34.8, -28.2), (28.2, 34.8)):                  # the door leaves, slid aside
        b.box("Facade", (x0, Y0 - 0.5, 0.0), (x1, Y0 - 0.3, 18.4), "MI_PaintedMetal")
    b.box("Facade", (-28.5, Y0 - 0.6, 18.0), (28.5, Y0, 18.8), "MI_PaintedMetalDark")
    for x in (-16.0, 16.0):                                        # engine work stands under the wings
        b.box("Fittings", (x - 2.0, -3.0, 0.0), (x + 2.0, 1.0, 0.15), "MI_PaintYellow")
        for dx in (-1.9, 1.7):
            b.box("Fittings", (x + dx, -3.0, 0.0), (x + dx + 0.2, 1.0, 1.1), "MI_PaintYellow")
    b.mark("vehicle", 27.5, -14.0, 0.0, 180.0, vehicle="LIP1")
    b.put("Warehouse_Forklift", -30.0, -18.0, 90.0)
    b.put("Shop_StockShelf", xi0 + 0.4, -10.0, 90.0, repeat=(3, 0.0, 3.3))
    b.put("Warehouse_Pallet", -30.0, -24.0, 0.0, repeat=(2, 2.0, 0.0))
    b.mark("spawn", 0.0, -24.0, 0.0, 0.0, team="worker", note="mechanics")
    b.mark("cover", -24.0, 8.0, 0.0, 0.0)
    # the back block: stair | workshop | parts store | crew room ; above, the engineering office
    well = (xi0, OY + 0.06, xi0 + 2.8, yb)
    b.ustair(*well, 0.0, 4.0, near="s", cap=True)
    part(b, "x", OY, xi0, xi1, 0.0, 3.8, doors=[(xi0 + 1.4, -1, 1.0), (-20.0, -1, 2.0, "", "open", 2.4),
                                              (0.0, -1, 2.0, "", "open", 2.4), (20.0, -1)])
    for x in (xi0 + 2.86, -10.0, 10.0):
        part(b, "y", x, OY, yb, 0.0, 3.8)
    b.put("Kitchen_PrepTable", -20.0, 28.8, 0.0)
    b.put("Shop_StockShelf", -14.0, 29.2, 0.0)
    b.put("Shop_StockShelf", -4.0, 29.2, 0.0, repeat=(3, 3.5, 0.0))
    b.put("Rest_Table", 22.0, 27.0, 0.0)
    b.put("Office_Locker", 28.0, yb - 0.3, 0.0, repeat=(4, 0.95, 0.0))
    b.slab(xi0, OY - 0.06, xi1, yb, 4.0, "MI_Fabric", holes=[(well[0], well[1] + IK.STAIR_NEAR, well[2], well[3])])
    part(b, "x", OY, xi0, xi1, 4.0, 3.8, wins=[Opening(-28.0, 30.0, 4.9, 6.9, glass="MI_GlassClear",
                                                      frame="MI_PaintedMetal")])
    part(b, "y", xi0 + 2.86, OY + IK.STAIR_NEAR, yb, 4.0, 3.8)
    part(b, "x", OY + IK.STAIR_NEAR + 0.06, xi0, xi0 + 2.8, 4.0, 1.1)       # a guard at the landing's edge
    b.slab(xi0, OY - 0.06, xi1, yb, 8.0, "MI_ConcreteSmooth")
    for x in (-18.0, -6.0, 6.0):
        b.put("Office_DeskIsland", x, 27.0, 0.0, z=4.0)
        chairs_around(b, x, 27.0, 2, 0.6, 0.85, z=4.0)
    b.put("Office_Desk", 26.0, 28.6, 0.0, z=4.0)
    b.put("Office_Chair", 26.0, 27.95, 180.0, z=4.0)
    b.mark("spawn", 0.0, 25.0, 4.0, 180.0, team="worker", note="the engineering office")
    return {"note": "整備格納庫 (maintenance hangar): one narrow-body airliner inside (the site's prop), a flyable LIP1 "
                    "light plane (MARK_vehicle), workshops, parts, crew room, the engineering office upstairs."}


# ── a CARGO SHIP (user, 2026-09-28): a static walkable level, not controllable ──────────────────────────────────

def cargo_ship(b):
    """コンテナ船 (a coastal feeder, 内航コンテナ船 class): 150 x 24 m, the origin on the WATERLINE (z 0) at midships,
    the bow -Y. Hull from the keel (-7 m) to the main deck (+8 m) with a 1.2 m bulwark; four holds under hatch covers
    stacked with containers; two deck cranes; the forecastle with its winches and mast; the aft accommodation house
    (A-deck mess, two cabin decks, the captain's deck, the wheelhouse with its wings) over the ENGINE ROOM, reached by
    a stair from the deck. A placeholder LEVEL: nothing moves it."""
    DECK = 8.0
    KEEL = -7.0
    HW = 12.0
    red, dark = "MI_CraneRed", "MI_PaintedMetalDark"

    def hull_seg(y0, y1, hw):
        """One stepped length of hull: two sides and the deck (the bow is stepped, a placeholder)."""
        for s in (-1, 1):
            xa, xb = (s * hw - 0.3, s * hw) if s > 0 else (s * hw, s * hw + 0.3)
            b.box("Hull", (xa, y0, KEEL), (xb, y1, 0.0), red)
            b.box("Hull", (xa, y0, 0.0), (xb, y1, DECK + 1.2), dark)
        b.box("Hull", (-hw, y0, KEEL - 0.2), (hw, y1, KEEL), red)

    # the engine stair's hole is cut in the midbody's deck
    eng_well = (-9.8, 49.0, -7.0, 58.5)
    eng_hole = b.ustair(*eng_well, 0.0, DECK, near="s", cap=False)
    hull_seg(-50.0, 75.0, HW)
    b.slab(-HW, -50.0, HW, 75.0, DECK, "MI_PaintedMetal", holes=[eng_hole], group="Hull")
    b.box("Hull", (-HW, 74.7, KEEL), (HW, 75.0, DECK + 1.2), dark)                           # the transom
    for y0, y1, hw in ((-55.0, -50.0, 11.2), (-60.0, -55.0, 10.0), (-65.0, -60.0, 8.0), (-70.0, -65.0, 5.5),
                       (-75.0, -70.0, 2.5)):
        hull_seg(y0, y1, hw)
        b.slab(-hw, y0, hw, y1, DECK, "MI_PaintedMetal", group="Hull")
        b.box("Hull", (-hw, y0, KEEL), (hw, y0 + 0.3, DECK + 1.2), dark) if y0 == -75.0 else None
    for y in (-55.0, -60.0, -65.0, -70.0):                     # close the steps between bow segments
        pass
    # the engine room: its floor (the tank top) at the waterline, the forward bulkhead, the engine, generators
    b.box("Hull", (-11.7, 42.0, -0.3), (11.7, 74.7, 0.0), "MI_Steel")
    b.box("Hull", (-11.7, 41.85, 0.0), (11.7, 42.0, DECK), dark)
    b.box("Engine", (-2.0, 50.0, 0.0), (2.0, 62.0, 4.5), "MI_Olive")
    b.box("Engine", (-1.2, 51.0, 4.5), (1.2, 61.0, 5.4), "MI_Olive")
    for y in (46.0, 51.0, 56.0):
        b.box("Engine", (6.0, y, 0.0), (9.5, y + 3.0, 2.2), "MI_Olive")
    part(b, "y", -7.0, 64.0, 74.6, 0.0, 3.0, wins=[Opening(66.0, 72.0, 1.0, 2.2, glass="MI_GlassClear")])
    part(b, "x", 64.0, -11.7, -7.0, 0.0, 3.0, doors=[(-9.3, -1)])
    b.put("Office_Desk", -9.3, 72.8, 0.0)
    b.put("Office_Chair", -9.3, 72.15, 180.0)
    b.put("Office_ServerRack", -11.2, 67.0, 90.0)
    b.mark("spawn", 4.0, 64.0, 0.0, 180.0, team="crew", note="the engine room")
    b.mark("objective", -9.3, 71.5, 0.0, 180.0, note="the engine control room")
    # the holds' hatch covers, stacked with containers (20 ft: 6.06 x 2.44 x 2.59), gaps to walk between
    cols = ("MI_CraneRed", "MI_SignGreen", "MI_SignCyan", "MI_PaintedMetal", "MI_SignYellow", "MI_PostRed",
            "MI_Olive", "MI_PaintWhite")
    k = 0
    for hy in (-46.0, -24.0, -2.0, 20.0):
        b.box("Cargo", (-9.5, hy, DECK), (9.5, hy + 18.2, DECK + 1.4), "MI_PaintedMetal")
        for bay in range(3):
            for row in range(7):
                tiers = 3 if (row + bay) % 4 else 2
                if hy == -46.0 and row in (0, 6):
                    tiers = 1
                for tier in range(tiers):
                    x0 = -8.54 + row * 2.44
                    y0 = hy + bay * 6.07
                    z0 = DECK + 1.4 + tier * 2.59
                    b.box("Cargo", (x0 + 0.02, y0 + 0.03, z0), (x0 + 2.42, y0 + 6.03, z0 + 2.57), cols[k % len(cols)])
                    k += 1
        b.mark("cover", 10.8, hy + 9.0, DECK, 0.0)
        b.mark("cover", -10.8, hy + 9.0, DECK, 180.0)
    for cy in (-26.0, 18.0):                                   # the deck cranes, between the holds
        b.box("Cranes", (-1.4, cy - 1.4, DECK), (1.4, cy + 1.4, DECK + 8.0), "MI_PaintYellow")
        b.box("Cranes", (-1.8, cy - 1.8, DECK + 8.0), (1.8, cy + 1.8, DECK + 11.0), "MI_PaintYellow")
        b.box("Cranes", (-0.5, cy - 20.0, DECK + 10.0), (0.5, cy - 1.8, DECK + 10.8), "MI_PaintYellow")
    # the forecastle: winches, bollards, the foremast
    for x in (-5.0, 5.0):
        b.box("Deck", (x - 1.2, -62.0, DECK), (x + 1.2, -59.0, DECK + 1.3), "MI_Olive")
    b.put("Harbour_Bollard", -6.5, -66.0, 0.0, z=DECK)
    b.put("Harbour_Bollard", 6.5, -66.0, 0.0, z=DECK)
    b.put("Harbour_Bollard", -10.5, 70.0, 0.0, z=DECK)
    b.put("Harbour_Bollard", 10.5, 70.0, 0.0, z=DECK)
    b.box("Deck", (-0.3, -56.3, DECK), (0.3, -55.7, DECK + 14.0), "MI_PaintWhite")
    # ── the accommodation house (x -10..10, y 48..63) aft, five decks of 2.8 m, the wheelhouse on top
    X0, X1, Y0, Y1 = -10.0, 10.0, 48.0, 63.0
    LV = [DECK, DECK + 2.8, DECK + 5.6, DECK + 8.4, DECK + 11.2]
    TOP = LV[-1] + 3.0
    xi0, xi1, yf, yb = X0 + EXT_T, X1 - EXT_T, Y0 + EXT_T, Y1 - EXT_T
    acc = (7.0, 49.0, 9.8, 55.9)
    holes = []
    for i in range(len(LV) - 1):
        holes.append(b.ustair(*acc, LV[i], LV[i + 1] - LV[i], near="s", cap=(i == len(LV) - 2)))
    for i, z in enumerate(LV[1:]):
        b.slab(X0 - (2.0 if z == LV[-1] else 0.0), Y0, X1 + (2.0 if z == LV[-1] else 0.0),
               Y1 if z != LV[-1] else Y0 + 6.0, z, "MI_Terrazzo", holes=[holes[i]])
        if z == LV[-1]:
            b.slab(X0, Y0 + 6.0, X1, Y1, z, "MI_Terrazzo")
    b.box("Roof", (X0 - 0.3, Y0 - 0.3, TOP - 0.2), (X1 + 0.3, Y1 + 0.3, TOP), "MI_PaintWhite")
    for i, z in enumerate(LV):
        h = (LV[i + 1] - z) if i + 1 < len(LV) else TOP - z
        if i == 0:
            sides = {"f": ([(3.0, -1, 0.9, "swing", "exit")], band_windows(b, -8.0, 0.0, z, h, every=2.5, w=1.0)),
                     "l": ([(55.0, -1, 0.9, "swing", "exit")], []), "r": ([(58.5, 1, 0.9, "swing", "exit")], [])}
        elif i < len(LV) - 1:
            sides = {"f": ((), band_windows(b, xi0, xi1, z, h, every=2.5, w=1.0, sill=1.0, head=1.9)),
                     "l": ((), band_windows(b, yf + 1.0, yb - 1.0, z, h, every=3.0, w=0.8, sill=1.0, head=1.8)),
                     "r": ((), band_windows(b, 57.0, yb - 1.0, z, h, every=3.0, w=0.8, sill=1.0, head=1.8))}
        else:
            wall = [Opening(xi0 + 0.3, xi1 - 0.3, z + 1.1, z + 2.6, glass="MI_GlassClear", frame="MI_PaintedMetal")]
            sides = {"f": ((), wall), "l": ([(50.5, -1, 0.9, "swing", "exit")], []),
                     "r": ([(50.5, 1, 0.9, "swing", "exit")], [])}
        ext(b, X0, Y0, X1, Y1, z, h - (0.2 if i + 1 < len(LV) else 0.2), "MI_PaintWhite", sides, inner="MI_PaintWhite")
        if i < len(LV) - 1:
            _enclose_well(b, acc, "s", z, h - 0.2)
    # the bridge wings, a 1.1 m guard round each
    for s in (-1, 1):
        xa, xb = (X1, X1 + 2.0) if s > 0 else (X0 - 2.0, X0)
        edge = xb - 0.15 if s > 0 else xa
        b.box("Roof", (edge, Y0, LV[-1]), (edge + 0.15, Y0 + 6.0, LV[-1] + 1.1), "MI_PaintWhite")
        b.box("Roof", (xa, Y0, LV[-1]), (xb, Y0 + 0.15, LV[-1] + 1.1), "MI_PaintWhite")
        b.box("Roof", (xa, Y0 + 5.85, LV[-1]), (xb, Y0 + 6.0, LV[-1] + 1.1), "MI_PaintWhite")
    b.box("Roof", (-3.0, 63.0, DECK), (3.0, 67.0, DECK + 18.0), "MI_PaintWhite")               # the funnel
    b.box("Roof", (-3.05, 62.95, DECK + 15.5), (3.05, 67.05, DECK + 17.0), "MI_CraneRed")
    b.box("Roof", (-0.2, 55.0, TOP), (0.2, 55.4, TOP + 5.0), "MI_Steel")                      # the radar mast
    # A deck: the engine stair enclosed, the mess aft, the galley
    z = LV[0]
    _enclose_well(b, eng_well, "s", z, 2.6)
    part(b, "x", 59.5, -6.94, 6.94, z, 2.6, doors=[(5.5, -1)])
    for x in (-5.0, -1.5, 2.0):
        b.put("Rest_Table", x, 61.2, 0.0, z=z)
        b.put("Rest_Chair", x, 60.45, 0.0, z=z)
    b.put("Kitchen_Fridge", 8.8, 61.5, 270.0, z=z)
    b.put("Kitchen_PrepTable", 8.0, 58.0, 270.0, z=z)
    b.mark("spawn", 0.0, 61.2, z, 0.0, team="crew", note="the mess")
    # B and C decks: four cabins aft each side of the stair
    for z in LV[1:3]:
        part(b, "x", 56.0, xi0, 6.94, z, 2.6, doors=[(-7.4, 1), (-2.5, 1), (2.5, 1)])
        for x in (-5.0, 0.0, 5.0):
            part(b, "y", x, 56.0, yb, z, 2.6)
        for x in (-7.4, -2.5, 2.5):
            b.put("Fire_Bunk", x, 61.8, 0.0, z=z)
            b.put("Office_Locker", x + 1.4, 57.0, 180.0, z=z)
        b.mark("spawn", -2.0, 52.0, z, 0.0, team="crew")
    # D deck: the captain's cabin (the safe) and the chief engineer's
    z = LV[3]
    part(b, "x", 56.0, xi0, 6.94, z, 2.6, doors=[(-5.0, 1), (4.0, 1)])
    part(b, "y", 0.0, 56.0, yb, z, 2.6)
    b.put("Office_Desk", -5.0, 61.8, 0.0, z=z)
    b.put("Office_Chair", -5.0, 61.15, 180.0, z=z)
    b.put("Office_Safe", -9.2, 61.8, 90.0, z=z)
    b.put("Fire_Bunk", 4.0, 61.8, 0.0, z=z)
    b.mark("objective", -8.6, 61.8, z, 90.0, note="the captain's safe")
    b.mark("weapon", -3.0, 62.0, z, 180.0, weapon="SMG1", note="the smuggler's cache")
    # the wheelhouse: consoles along the front glass, the chart table, the captain's chair
    z = LV[-1]
    b.put("Office_Desk", -4.0, 48.8, 180.0, z=z, repeat=(5, 2.0, 0.0))
    b.put("Office_Chair", 0.0, 50.2, 0.0, z=z)
    b.put("Office_MeetingTable", -6.0, 58.0, 0.0, z=z)
    b.mark("spawn", 0.0, 51.0, z, 180.0, team="crew", note="the officer of the watch")
    b.mark("objective", 0.0, 49.5, z, 180.0, note="the wheelhouse")
    return {"note": "コンテナ船 (a coastal container feeder, 150 m): a STATIC walkable level (not controllable) -- "
                    "container stacks to fight through, the accommodation house (mess, cabins, the captain's safe, "
                    "the wheelhouse) and the engine room. Origin on the waterline at midships, bow -Y."}


PLANS = {"Koban": koban, "FireBranch": fire_branch, "PoliceStation": police_station,
         "FireStation": fire_station, "Hospital": hospital,
         "OfficeHQ": office_hq, "ResortHotel": resort_hotel,
         "WarehouseYard": warehouse_yard, "MilHQ": mil_hq, "MilBarracks": mil_barracks,
         "MilArmoury": mil_armoury, "MilHangar": mil_hangar, "MilControlTower": mil_control_tower,
         "AirportTerminal": airport_terminal, "AirportHangar": airport_hangar, "CargoShip": cargo_ship}
