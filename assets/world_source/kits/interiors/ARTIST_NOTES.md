# Mission buildings -- notes for the artist and the level designer

One `.blend` per building, each holding ONE piece collection named after it: the WHOLE building (shell, floors,
stairs, lift shafts, rooms, fittings). Everything in them is a **PLACEHOLDER at its real Japanese size**: boxes in the
library palette and copies of library fittings. Remodel freely -- the game only assumes the frame, the floor levels
and the Empties listed below.

| file | building | floors | what is in it |
|---|---|---|---|
| `Koban.blend` | 交番, the SMALL police station | 1 (3.4 m) | front office with the public counter and a bench, rest room with the **pistol locker (light weapons)**, toilet, back door. Plot 8 x 10. |
| `PoliceStation.blend` | 警察署, the LARGE police station | 2 (4.2 + 3.8) | a FENCED COMPOUND (steel palisade, cameras): the public gate with the 立番 booth, the vehicle gate to the rear car park under a barrier with its own booth; suspects come in by the west 護送口 door to the 留置場; public counters and waiting, duty office, the **complete ARMOURY** (long-gun racks, pistol lockers, riot shields, ammunition shelves), 3 holding cells + guard room, 2 interrogation rooms with observation rooms, lockers, WCs; upstairs the CID open office, the chief's office (safe), the incident room, bunks, lockers. 2 stairs, a lift. Plot 40 x 45 (35 x 40). |
| `FireBranch.blend` | 消防出張所, the SMALL fire station | 1 (5.2) | 2 open apparatus bays (pumper, ambulance), gear racks, equipment store with the back door, office + counter, crew room with kitchen, bunks, WC. Plot 20 x 25. |
| `FireStation.blend` | 消防署, the LARGE fire station | 2 (5.4 + 4.0) | 4 open bays (ladder truck, 2 pumpers, ambulance), gear racks, office + counter, lockers, store, WC / shower, mess; upstairs 2 bunk rooms, briefing room, prevention office, the chief's office. 2 stairs, a roof stair house, the 訓練塔 (training tower) behind. Plot 40 x 50. |
| `Hospital.blend` | 病院, ONE type, medium / large, compacted | 3 (4.5 + 4.0 + 4.0) + roof | TWO entrances: the MAIN one on the street (風除室, drop-off under the canopy, green signs) and the EMERGENCY side (ambulance lane to its canopy, the 救急搬入口 vestibule into the ER, a walk-in 救急外来 door; red signs); entrance hall, reception and pharmacy counters, 4 consulting rooms, X-ray, the ER (救急) with its own ambulance door and canopy, pharmacy store, doctors' office; F2 two operating theatres + scrub, the ICU (4 beds), imaging, staff office; F3 the ward (four 4-bed rooms, three private rooms, day room, nurse station); the roof HELIPAD. A BED LIFT to every floor and the roof, 2 stairs. Used by both hospital plots (55 x 60 and 100 x 100). |
| `OfficeHQ.blend` | オフィスビル | 4 (4.2 + 3 x 3.8) | glazed lobby with security, a lift to every floor, 2 stairs (A to the roof), WCs per floor; F2-F3 島型 open offices, meeting rooms, the server room (F3); F4 boardroom, secretaries, the president's office, the strong room (金庫室). Not placed on the island. |
| `ResortHotel.blend` | リゾートホテル | 4 (4.5 + 3 x 3.2) | restaurant, lobby + front desk, lounge-bar on the sea side; kitchen, entrance vestibule, back office on the land side; 24 sea-view rooms (unit bath, twin beds, desk, sofa, balcony); pool terrace; porte-cochère. A lift, 2 stairs. The resort reserves. |
| `WarehouseYard.blend` | 倉庫 + ヤード | 1 (9 m hall) + a 2-storey office | pallet racks with 3.5 m forklift aisles, forklifts, three open loading docks, a two-storey corner office up an open stair; the fenced yard with a trailer, a truck and a guard booth. Not placed on the island. |
| `SafeHouseSmall.blend` | 隠れ家 (small, residential) | 2 (house floor 0.45 + 2.8) | a 3.5 x 5 間 wooden house: genkan (doma, the 0.30 agarikamachi step, 下足箱), LDK, 洗面所 + unit bath, a SEPARATE WC; upstairs 洋室 + 和室 (続き間, 押入れ) and the 納戸 stash (MARK_weapon); stone boundary wall. |
| `SafeHouseLarge.blend` | 隠れ家 (large, residential) | 2 (0.45 + 2.8) | a 7 x 5.5 間 注文住宅 with a built-in 2-car garage (entered from a small doma pocket off the hall), リビング階段 LDK with a 対面 kitchen, 6-畳 和室, WC, 洗面所 + bath; upstairs the master bedroom (balcony), the study (safe, gun locker), two rooms, WC; a 1.6 m block wall, car gate, cameras. |
| `SafeHouseCitySmall.blend` | 隠れ家 (downtown, small) | 3 (0 / 3.1 / 5.9) | a 3 x 5 間 狭小住宅: F1 built-in garage (kei car) + workroom with a gun locker + WC, genkan; F2 the LDK (a townhouse's living floor) + WC; F3 bedroom, bath, the stash. |
| `SafeHouseCityLarge.blend` | 隠れ家 (downtown, large) | 5 + roof terrace | a 4 x 8 間 雑居ビル: F1 one-car garage behind a shutter + lobby; F2-F3 the front company's office; F4 the penthouse LDK; F5 bedroom + PANIC ROOM (gun rack, lockers, safe). Lift, one stair to the roof. |
| `Izakaya.blend` | 居酒屋 (enterable) | 2 (3.0 + 2.8) | noren, red lanterns, a sliding front door; the L counter (9 stools) and open kitchen, the 0.3 m 小上がり with two low tables, WC, a side door to the alley; upstairs the 座敷 banquet room (床の間) and the staff room (safe). |
| `MaidCafe.blend` | メイドカフェ (Akihabara) | 4 | a 3.5 x 8 間 雑居ビル: F1 merch shop (capsule-toy machines, register); F2 the cafe (tables, counter, a stage at the window); F3 the event hall; F4 staff (lockers, the takings safe). Lift + stair. |
| `AdultServices.blend` | 風俗ビル (grey-zone, non-explicit) | 5 | F1 reception (lit menu board) + waiting room; F2 host-club lounge (box seats, bar); F3-F4 four private rooms a floor off a corridor; F5 back office (takings safes, camera monitors). No roof access. |
| `BankSmall.blend` | 銀行 (small branch) | 1 (4.5) | ATM corner (own door), 風除室, lobby (ticket machine), teller counter + glass screen + staff gate, back office, VAULT (0.45 m walls, steel door), staff room + WC, 通用口. |
| `BankLarge.blend` | 銀行 (main branch) | 3 (5.0 + 4.0 + 4.0) | ATM corner, 風除室, banking hall, high / low counters, back office, MAIN VAULT, 貸金庫, cash-in-transit bay (shutter); F2 consultation booths, manager (safe), meeting room; F3 offices, server room, lockers, canteen. 2 stairs + lift. |
| `ParkingGarage.blend` | 立体駐車場 (自走式) | ground + 3 decks | 23 x 40 m; UP ramps west, DOWN ramps east (20 m per 3 m storey = 15 %, 3.5 m wide, stacked), 2.5 x 5.0 bays both sides of a 6 m aisle, wheel stops, parapets, gate booth + arm, a stair tower. |
| `AirportControlTower.blend` | 空港管制塔 (civil) | block 2 + tower to 36 m | operations block (security lobby, ops office, approach-radar room, briefing) and a tower with a LIFT and stair to a 14 x 14 m glass cab at 36 m (consoles, radar on the roof). |
| `FashionBuilding.blend` | ファッションビル | 5 (4.5 each) | 30 x 24 m: cosmetics, fashion x2, electronics, the restaurant floor; an escalator atrium, 2 lifts, 4 corner stairs, WC blocks. |
| `DepartmentStore.blend` | 百貨店 / 駅ビル (Shinjuku class) | 7 | 72 x 48 m: food hall (F1 -- no basements on this island), cosmetics, fashion x2, household, books, restaurants, roof garden; two escalator atriums, two lift banks, 4 stairs, WC blocks, 5 entrances. |
| `CivicCenter.blend` | 区民センター (downtown) | 4 | 48 x 32 m: 窓口 counters + waiting rows + info desk + cafe, 2 entrances with 風除室; F2 hall (stage) + meeting rooms; F3 library; F4 offices, director, 防災センター. |
| `OnsenRyokan.blend` | 温泉旅館 (snow mountains) | 2 (floor 0.3 + 3.5) | 玄関 (shoes off), 帳場, lobby + 売店, 大浴場 男湯 / 女湯 (脱衣所, hinoki 内湯, wash row) each opening onto its fenced 露天風呂; 宴会場, kitchen; eleven 和室 guest rooms upstairs; snow on the roof. |
| `SecureMansion.blend` | 邸宅 (high security) | 2 (0.45 + 3.3) | a 64 x 50 m walled lot: 3 m wall + cameras, pedestrian gate (locked EXIT_) + barrier vehicle gate watched from the 詰所; main house (genkan under a porte-cochère, guards' room, 警備室, 応接間, 大広間 with 床の間 / 神棚, bath, kitchen); upstairs the study (safe, guns) and a PANIC ROOM; 3-car garage; garden + pond. |

## What the game assumes -- keep these
* **The frame:** Blender metres, Z up, the origin on the ground at the PLOT centre (the civic buildings) or anywhere
  (the others are re-centred on their bounds); the STREET / front toward **-Y**. Floor levels as in the table: the
  ground floor's top is at Z 0.
* **Collision is the mesh itself** (a trimesh of the whole piece): every solid thing you model is solid in game,
  every hole is walkable. Keep door and window holes open where the Empties say.
* **`DOOR_` Empties** (single arrows on the floor at a doorway's centre, pointing OUT of the room) are the interior
  doors, built by the game (`world.Door`): props `w`, `h`, `style` -- `swing` (hinged: offices, store rooms, stair fire
  doors) or `slide` (a solid sliding leaf: every restroom, hospital rooms) -- and `slide_dir` (+1 / -1).
* **`EXIT_` Empties** are the OUTER doors (same props; the arrow points out of the building). `slide` = a Japanese
  automatic glass entrance (自動ドア), two leaves when 1.2 m or wider. The building ships SHUT; `<Id>_Open` has the doors
  LOCKED until a mission unlocks them; `<Id>_Shop` has them unlocked and automatic.
* **`LIFT_` Empties** are the lifts (`world.Elevator` builds the car and the doors at runtime; the SHAFT is yours):
  the Empty is the shaft floor's centre at the lowest stop; props `w` (inside, along the door axis), `d`, `stops`
  (every stop's floor over the lowest, "0,4.2,8,11.8"), `faces` (1 = the door is on the Empty's -X side, 2 = +X, 3 =
  both), `door_w`, `door_h`. Its Z turn turns the door axis. The shaft needs a door opening at every stop on that face.
  With no buttons, a rider who stays aboard is carried up a floor at a time to the top (step out at your floor).
* **`MARK_` Empties** are MISSION MARKERS for the level designer (a `Markers` node of Marker3Ds in group
  `mission_marker`, every prop copied as metadata). Kinds used: `weapon` (prop `weapon` = a catalog id: PIS1, SMG1,
  ASR1, SHG1, SNR1, FLA1, SMO1 ...: where a pickup belongs -- the armouries), `spawn` (prop `team`: police, fire,
  doctor, nurse, guard, worker, guest, staff, prisoner, suspect, vip, civilian), `cover`, `objective` (prop `note`),
  `vehicle` (a bay, a helipad). Nothing spawns from them by itself: a mission reads them. Add your own freely.
* **Keep 1.2 m clear on both sides of every door** and in front of every lift door; the generator refuses a plan that
  does not, `probe_buildings.gd` drives every door.
* **Stairs:** risers 0.19 m or less, treads 0.27 m, flights 1.25 m+ wide (建築基準法). Keep the landings at the floor
  levels. A top floor with no flight above has a guard over the drop.

## PLACEHOLDERS -- replace by hand
Everything is placeholder. The fittings are library pieces (`kits/library/library.blend`, written by
`blender/tools/library_interiors.py`; `kits/library/PIECES.md` lists each one's state): replacing one THERE replaces it
in every building that uses it after a regenerate -- or edit the copy here. What each building most wants:
* **every building:** a real facade (the shells are flat boxes with punched / ribbon windows), window frames and
  sills, ceilings and lights, skirting, signage.
* `Koban` / `PoliceStation`: the 旭日章 emblem, the 赤色灯 lamps and the KOBAN / 警察署 boards; barred cell DOORS (the
  game hangs a plain leaf in each cell opening today); real racks with the weapons' own silhouettes; a sally-port or
  garage for patrol cars.
* `FireBranch` / `FireStation`: roll-up bay shutters (they are modelled raised; a shutter that comes down is a later
  runtime item), the fire trucks and ambulance (`Fire_*` library placeholders), a fire pole, the tower's detail.
* `Hospital`: the H of the helipad, the 救急 signs, OR lights, curtain tracks, medical gases on the wall.
* `OfficeHQ`: the curtain wall, a reception counter with the company sign, the server room's raised floor.
* `ResortHotel`: balconies with railings you can see through, the pool (it is a shallow solid basin), parasols.
* `WarehouseYard`: the corrugated shell's structure, dock levellers and shutters, the fence mesh, a proper guard booth.

* `MilHQ` / `MilBarracks` / `MilArmoury` / `MilHangar` / `MilControlTower` (parts of the `MilitaryBase` site): the
  JASDF/JMSDF look (olive and grey panels, unit boards), a real gate barrier, the armoury's vault door (it is an open
  steel door today), a hangar door that can close, the tower cab's consoles and radar. The two jets in the hangar and
  on the apron are the flyable `FIJ1` placeholder, the trucks `CRT1`.
* `AirportTerminal`: the curtain wall and the roof's structure, check-in counters with airline boards, baggage carousels
  that curve (they are straight boxes), security arches and X-ray machines, departure boards, real boarding bridges
  (a fixed 18 m box with a service stair today). `AirportHangar`: the hangar door's leaves and rails, tail and engine
  stands, the parked airliner is the site's `Airport_Airliner` prop.
* `CargoShip`: a real hull (the bow is STEPPED boxes and the hull is open under the deck except the engine room), the
  hatch covers' detail, containers with doors and corrugation (they are boxes coloured from the palette), cranes with
  jibs that can slew, the accommodation house's railings, ladders between the decks outside, a gangway. It is a
  STATIC level: its origin is the waterline, so place it with its origin on the sea surface.

* The 2026-09-29 set (safe houses, izakaya, maid cafe, adult services, banks, car park, control tower, retail, civic
  centre, ryokan, estate): a real facade and signage everywhere (the signs are flat coloured boxes); the house
  roofs are plain gables; the ryokan wants an 入母屋 roof with deep eaves, wooden lattice (格子) and real snow
  meshes; its bath water, the car park's ramps' chevrons, the escalators (they are walkable steps, not moving) and
  the bank vault doors are placeholders; the car park wants a proper ramp surface, lights and the 満空 sign; the
  estate a real 数寄屋 house, 築地塀 and a pine garden; the maid cafe and the adult building their neon.
* **Water:** a pool's water is a `MARK_water_` Empty (props `w`, `d`, `material` = onsen / pool) -- the game draws a
  non-colliding water surface there with the water shader. Model the BASIN (sunk, with a way in and out), not the
  water: a mesh called water would be solid.
* The yard's and the terminal's container trucks are the drivable `COT1` (`assets/vehicles/COT1.blend`, a placeholder
  block from `blender/tools/make_placeholder_cars.py`): model the tractor and chassis there, keeping the 20 ft ISO box
  and the part names.
* **Every placeholder here is safe to replace** -- the generator KEEPS an edited file (`--force=<Id>` overwrites).

## Flyable and sailable placeholders (not buildings)
`blender/tools/make_placeholder_craft.py` writes `assets/vehicles/FIJ1` (fighter), `LIP1` (light plane), `WOB1` (work
boat) and `FIB1` (fishing boat) `.blend` / `.glb` / `.craft.json`; `tools/build_craft_scenes.py` makes their scenes
(inherited from `Airplane.tscn` / `Boat.tscn`, tuning in its TUNING table). Remodel the `.blend` freely -- the
generator keeps an edited one -- keeping the nose / bow toward Blender +Y, the seats' Empties and the cockpit eye;
then re-run both tools. `tools/godot/probe_craft.gd` checks the boats float and make way and the aircraft take off.

## After editing
`tools/building_kit/build_buildings.sh` exports these files with the other kits, rebuilds the scenes and runs
`probe_buildings.gd`; `tools/godot/probe_building_lift.gd -- --scene=<X_Shop.tscn>` rides a lift floor by floor. A
regenerate (`blender/tools/build_interior_blends.py`) keeps your edited building (it says KEPT); `--force=<Id>`
overwrites it -- ask first.
