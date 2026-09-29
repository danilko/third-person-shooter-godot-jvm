# library.blend -- notes for the artist

`library.blend` is the project's own model library (CC0, ours). Every piece is a COLLECTION named after it, holding
one object, laid out on a grid (the collection's `instance_offset` is its grid spot; the export moves it back).

## Edit a piece

1. Open `assets/world_source/kits/library/library.blend`, find the collection, edit the object.
2. Keep the FRAME: Z up, origin at the footprint centre on the ground, the side a person uses facing **-Y**
   (the game's +Z, the building convention). Real size, in metres.
3. Read the piece's `edit_note` (Object or Collection Properties > Custom Properties): what else in the project
   assumes something about this model, and has to move with it.
4. Run `tools/building_kit/build_buildings.sh` (exports the pieces, rebuilds the building scenes, runs the probe).
   A piece whose bounds changed is refused until you re-run with `ACCEPT_BOUNDS=1` -- on purpose.
5. Materials: use the palette's names (`MI_*`); their look is `palette.json` -> `materials/MI_*.tres`
   (`tools/building_kit/build_library_palette.py`), not the Blender node values.

## Your edits are safe

Some pieces are GENERATED from code (`blender/tools/library_procedural.py`, `library_landmarks.py`, flagged
`lib_procedural`). Each remembers a fingerprint of its mesh and materials (`lib_generated`). Once you edit one, the
fingerprint no longer matches and `build_library.py --procedural` KEEPS your version (it says so). Only
`--force` or `--only=<Name>` regenerates a piece on purpose.

## Pieces that other files depend on

| piece | what depends on it |
|---|---|
| `Harbour_Crane` | its COLLIDER is `CRANE_BOXES` in `tools/building_kit/site_container_terminal.py` (bogies, legs, portal and girder beams), not its mesh: update the boxes with the model. Rails 30.48 m apart along Y (sea -Y), portal clear 18 m; nothing may overhang -Y past the seaside rail + 2 m. |
| `Harbour_LightMast` | collider `MAST_BOXES` in the same file. |
| `Harbour_Apron` | tiled 10 x 6 by the terminal: must stay 36.4 m square, top at Z 0. |
| `ShuriCastle` | the platform (25 m) is sized to the measured site (`tools/island_sites.py`): its top must clear the uphill ground. Faces -Y towards downtown. Collider = its mesh. |
| landmarks (`RainbowBridge`, `TokyoStation`, ...) | see `blender/tools/library_landmarks.py`; the Rainbow Bridge's two road levels are Road Kit roads (`RB_ROAD_LOWER`/`RB_ROAD_UPPER`). |

Containers, pallets, drums, cones and the expressway's median panel are NOT here: they are Quaternius' (CC0), owned by
`assets/world_source/kits/quaternius_zombie_apocalypse/blends/` (see its README).

## Civic placeholders (2026-09-28) -- REPLACE BY HAND

Every piece below is a PLACEHOLDER massing written by `blender/tools/library_civic.py` (flat palette materials, boxes,
ribbon or punched windows). Edit it in `library.blend` (the generator never overwrites a hand-edited piece), then run
`tools/building_kit/build_buildings.sh`. Sizes are real Japanese sizes -- keep them. Measured from PLATEAU named
buildings (`tools/plateau2json/measure_named_buildings.py`, p50 over 7 central wards): 警察署 30 x 45 m / 7 storeys;
交番 5 x 7 m / 2 storeys; 消防署 23 x 42 m / 5 storeys (4.5 m a storey); 出張所 15 x 23 m / 3 storeys; 総合病院
52 x 83 m / 8 storeys / 41 m; 小学校 building 46 x 80 m / 4 storeys / 18 m; 区役所 48 x 85 m / 14 storeys; 寺 hall
24 x 32 m / 16 m. The island's are the p25 end, fitted to their plots.

| piece | is | frame / what the game assumes | what the real model wants |
|---|---|---|---|
| Civic_PoliceStation | 警察署 | origin = PLOT centre (40 x 45), street -Y | tile facade, 旭日章 emblem, 赤色灯, parking at the back |
| Civic_Koban | 交番 | 8 x 10 plot, street -Y | the corner koban: gabled or modern roof, red lamp, KOBAN sign, a bench |
| Civic_FireStation | 消防署 | 40 x 50 plot, bays face the street | red roll-up bays, 訓練塔 (hose / training tower), a fire engine prop |
| Civic_FireBranch | 消防出張所 | 20 x 25 plot | two bays, small hose tower |
| Civic_PostOffice / _Small | 郵便局 | 40 x 40 / 15 x 20 plots | 〒 sign, red band, post box, van bay |
| Civic_WardOffice | 区役所 | 60 x 60 plot | tower on a counter podium, plaza, flags |
| Civic_Hospital / _Small | 総合病院 / 病院 | 100 x 100 / 55 x 60 plots | ward tower, 救急 entrance + canopy, rooftop helipad (H) |
| Civic_Clinic | 診療所 | 14 x 18 plot | clinic below, home above, plain name board |
| Civic_SchoolElementary / _JuniorHigh | 小学校 / 中学校 | 100 x 110 / 110 x 130 plots | 校舎 with a clock, 体育館, 25 m pool, 校庭, fence + 校門 |
| Shrine | 神社 | 50 x 60 plot, 鳥居 on the street | real 拝殿 / 本殿 roofs (copper), 狛犬, 灯籠, 手水舎 |
| Temple | 寺 | 50 x 50 plot, 山門 on the street | tiled hip roof 本堂, 鐘楼, gravel, 塀 |
| Park | 公園 | 60 x 60 plot, trees from the nature kit | playground, toilet, benches |
| WaterResort | 温浴・プールリゾート | 150 x 120 plot | spa / pool hall, wave pool, lazy river, slide tower |
| ResortHotel | リゾートホテル | a 70 x 60 reserve, balconies to -Y (the sea) | an Okinawa resort slab: balconies, pool deck, porte-cochère |
| FishMarket | 魚市場 | the 416 x 99 quay reserve, quay at -Y | sawtooth auction hall, ice plant, office, boats |
| Mil_HQ / Mil_Barracks / Mil_Hangar / Mil_ControlTower / Mil_Gate / Mil_Fence | 航空自衛隊 基地 | composite MilitaryBase (320 x 300), gate on the north | plain concrete blocks, arched hangars, tower cab, perimeter fence |
| Mil_FighterJet | F-15J class | nose -Y; collider = boxes in building_types.json | a real fighter model (19.4 m, 13 m span) |
| Airport_Hangar / Airport_Airliner | maintenance hangar + 737 class | composite AirportAirside | a real hangar and narrow-body; the hangar doorway stays >= 32 x 16.5 m |
| Airport_Taxiway / Airport_Apron | airside paving | 60 x 23 / 30 x 30 tiles, top at 0 | markings |
| Sign_AkibaVertical / Sign_AkibaBillboard | 秋葉原 signage | on the AkibaElectric type's facade / roof | stacked 袖看板 with real shop names, an LED screen |
| Prop_Chochin / Prop_Noren / Sign_ShopVertical | 横丁 dressing | on the YokochoRow type's front | 赤提灯, 暖簾, a small lit sign |
| Logi_TruckTerminal | トラックターミナル (cross-dock) | composite LogisticsTruckTerminal (225 x 150), 180 x 30 m shed, dock floor 1.2 m, doors on both long faces, office at +X; collider = the boxes in building_types.json | dock shelters and levellers, numbered doors, the carrier's sign, rooftop plant |
| Logi_DistributionCentre | 物流センター | composite LogisticsDistributionCentre (225 x 240), 120 x 70 x 14 m, dock face -Y (16 doors), office at the -X front corner | a real DC facade (metal panel bands, a glazed office corner), dock shelters, rooftop solar |
| Logi_Truck / Logi_Trailer | 10 t box truck, tractor + 40 ft trailer | cab / tractor -Y, static props | real vehicle models |
| Logi_GateHouse / Logi_Fence / Logi_YardTruckTerminal / Logi_YardDistribution | 守衛所, yard fence, yard slabs | gate house road -Y; yards have no collider (the site's ground box is it) | yard markings, lamp masts, wheel stops |

## Interior placeholders (2026-09-28) -- REPLACE BY HAND

Written by `blender/tools/library_interiors.py` for the supermarket (`kits/shops`) and the mission buildings
(`kits/interiors`): each is a labelled block at its real size, the side a person uses facing -Y. Replace the mesh
here, keeping the frame and the size; the buildings hold COPIES, so regenerate a building nobody edited (or edit the
copy there). `PIECES.md` lists each one's state.

| group | pieces | what the real model wants |
|---|---|---|
| supermarket | Shop_Checkout, Shop_BaggingTable, Shop_ProduceTable, Shop_CartRow, Shop_DeliCounter | a Japanese レジ lane with the self-pay machine, サッカー台, stepped produce crates, nested carts, a sloped-glass 惣菜 case |
| office | Office_DeskIsland, Office_Chair, Office_MeetingTable, Office_Reception, Office_Sofa, Office_Cabinet, Office_ServerRack, Office_Whiteboard | 島型 desks with monitors and cable trays, task chairs, a 受付 counter with the company sign |
| police | Police_GunLocker, Police_GunRack, Police_ShieldRack, Police_CellFront, Police_CellBunk | a steel 拳銃保管庫, long guns in a rack with a locking bar, riot shields (透明盾), a barred cell front |
| fire | Fire_PumpTruck, Fire_LadderTruck, Fire_Ambulance, Fire_GearRack, Fire_Bunk | the real vehicles (red, with the white band; the ambulance white with red), 防火衣 on hooks |
| hospital | Hosp_Bed, Hosp_ExamTable, Hosp_ORTable, Hosp_Curtain, Hosp_Monitor, Hosp_NurseStation, Hosp_XRay, Hosp_Stretcher, Hosp_WaitingBench | ward beds with rails, the OR light, curtain tracks, a nurse station counter |
| hotel | Hotel_Bed, Hotel_Tub, Hotel_Lounger | beds with throws, the unit bath, pool loungers |
| warehouse | Warehouse_Rack, Warehouse_Forklift, Warehouse_Pallet, Warehouse_RollCage | pallet racks, a counterbalance forklift, カゴ台車 |
