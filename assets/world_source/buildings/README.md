# Buildings and building kits

Modular building kits (`assets/world_source/kits/`), and the Japanese building types built from them (this
folder). One scene per type in `src/main/resources/com/openworld/world/buildings/`. Rebuild and gate everything with:

    tools/building_kit/build_buildings.sh

## Layout

```
assets/world_source/buildings/
  building_types.json          the building TYPES (kit-independent): footprint in modules, storeys, rows, doors
  BuildingLibrary.blend        VIEW: every type assembled from LINKED kit pieces (blender/tools/build_building_library.py)
  README.md                    this file
  (landmarks are library pieces now: kits/library/ the landmark pieces; the PLATEAU files were deleted 2026-09-18)
assets/world_source/kits/
  <kit_id>/                    one folder per kit = one licence and one module grid
    kit.json                   AUTHORED: licence, source, module, module_scale, category rules, facade rows
    <kit_id>.blend             THE OWNER of the pieces: every piece on a grid, one collection per piece
    source/                    the download's glTF, untouched (.gdignore: Godot never imports it); used once, by --init
    textures/                  the download's images, shared by every piece (and by the .blend, not packed)
    pieces/<category>/         EXPORTED from the .blend by blender/tools/export_building_kit.py
    pieces.json                EXPORTED: category and measured bounds of every piece (the layout's contract)
    materials/MI_*.tres        written once by the scene build, then HAND-OWNED (never overwritten)
```

A new kit is a new `<kit_id>/` folder: put the download in `source/` and `textures/`, write its `kit.json`
(copy `quaternius_downtown_city/kit.json`, measure its module and storey, write its category rules and rows), run
`python3 tools/building_kit/normalize_kit.py <kit> --init` (the first `pieces/`, `module_scale` baked in) and
`blender -b --python blender/tools/build_building_kit_blend.py -- <kit>` (the kit `.blend`). From then on the
`.blend` owns the pieces and `tools/building_kit/build_buildings.sh` exports them; both one-time tools refuse to
run again over an existing `.blend`. Then name the kit as a type's `kit`. Credit it in `CREDITS.md`. Map data is CC0/MIT only. A download is never split
across kits: roads and street furniture take their categories from the same folder (PLAN.md 3.6c).

## Blender: one file per kit, one view of every building

- **`<kit_id>.blend`**: one file per KIT, not per piece and not one for every kit. The pieces share ~20 materials and
  one grid, and a facade change touches several pieces at once. A kit is also a licence boundary: Quaternius' CC0
  pieces and our own Japanese pieces stay apart. Each piece is a collection named after it. Its objects sit at a
  grid spot, and the collection's `instance_offset` is that spot, so an instance still lands on the module. A wall's
  exterior faces -Y.
- **`BuildingLibrary.blend`**: open this to see or debug every building at once. It is built from the same layout as
  the game's scenes, with collision wireframes, door arrows and a 1.49 m stick. Edit a piece in the kit file, then
  File > External Data > Reload here.
- **Editing a piece:** change it in its collection in the kit `.blend`, save, run `build_buildings.sh`. A piece whose
  BOUNDS move more than 1 mm (or a piece added, removed or re-categorised) is refused, because the layout places every
  piece from its bounds; re-run with `ACCEPT_BOUNDS=1` when the change is deliberate. PLAN.md 3.6b step 2 still has to
  decide who owns a material's look. The Blender files show `MI_Trim_MetalConcrete` dark because its grey
  tint lives only in the Godot `.tres`.

## Japanese sizing

The Downtown City MegaKit is authored on a 2 m plan module and a 3 m storey. `module_scale` 0.91 puts it on
the Japanese construction grid, and each value below comes from that one number:

| | kit | ×0.91 | Japanese reference |
|---|---|---|---|
| plan module | 2.00 m | **1.82 m** | 1 ken (半間 0.91 m × 2) |
| storey | 3.00 m | **2.73 m** | house / apartment floor-to-floor 2.7–2.9 m |
| storey + band | 4.00 m | **3.64 m** | office / shop floor 3.5–4.0 m |
| door opening | 1.10 × 2.20 m | **1.00 × 2.00 m** (walkable 0.91 m) | door 0.8–0.9 × 2.0 m |

Sizing is metric, measured against the character (1.49 m, capsule r 0.35 × 1.75), like the weapons, not
arcade-scaled like the road lanes. To change it, edit `module_scale` and rerun `build_buildings.sh`. Nothing
else holds the number, and the types are written in modules so they follow.

What makes a building read as Japanese is mostly its proportions, not the scale: narrow, deep plots (a pencil
building is 4 × 7 modules), blank party walls, a shop on the ground floor, light tile or grey panel, and air
conditioner units on the facade. The type table is where that lives.

## Types (`building_types.json`)

| scene | 日本語 | modules | size (m) | storeys |
|---|---|---|---|---|
| PencilBuilding | ペンシルビル / 雑居ビル | 4 × 7 | 7.3 × 12.7 × 21.8 | shop 3.64 + 6 × 2.73 |
| ShopHouse | 店舗併用住宅 | 4 × 6 | 7.3 × 10.9 × 10.0 | shop 3.64 + 2 × 2.73 |
| Konbini | コンビニ | 10 × 7 | 18.2 × 12.7 × 4.6 | 1 × 3.64 |
| Mansion | マンション | 10 × 5 | 18.2 × 9.1 × 17.3 | 6 × 2.73 |
| Apartment | アパート | 8 × 4 | 14.6 × 7.3 × 6.4 | 2 × 2.73 |
| OfficeMid | 中規模オフィスビル | 12 × 8 | 21.8 × 14.6 × 34.6 | 9 × 3.64 |
| Warehouse | 倉庫 | 20 × 12 | 36.4 × 21.8 × 8.2 | 2 × 3.64 |
| Konbini (re-sized) | コンビニ | 10 × 6 | 18.2 × 10.9 × 4.6 | 1 × 3.64, full interior |
| GasKiosk | 給油所の事務所・売店 | 5 × 3 | 9.1 × 5.5 × 4.6 | 1 × 3.64 |
| StationBuilding | 駅舎 (小規模) | 7 × 4 | 12.7 × 7.3 × 4.6 | 1 × 3.64, ticket gates |
| FamilyRestaurant | ファミリーレストラン | 11 × 16 | 20.0 × 29.1 × 5.5 | 1 × 3.64, booths, kitchen, WC |
| KitExample_* | (the kit's own Boston/NYC buildings, re-scaled only) | | | |

Composite SITES (`composites` in `building_types.json`: whole types + library props on a paved apron):

| scene | 日本語 | site (m) | what |
|---|---|---|---|
| GasStation | ガソリンスタンド | 30.9 × 25.5 | canopy (4.7 m clear) on 3 columns, 3 islands, 6 pumps, the kiosk |
| KonbiniLot | コンビニ (駐車場付き) | 21.8 × 21.8 | the konbini behind seven 2.5 × 5.0 m bays with wheel stops |
| StationRural | 小さな地上駅 | 32.8 × 16.4 | station building, 21.8 m platform (0.94 m above rail) with end ramps, shelters, benches, name board, 1067 mm track |

Sizes: PLATEAU MEASUREMENTS (`tools/plateau2json/measure_building_types.py`, statistics only, see CLAUDE.md), the
ken grid, and stated design choices where PLATEAU has nothing (gas canopies).

## Landmarks (the `custom` list: our own base models from `kits/library/`, managed like every building)

`landmark: true` is only a tag (unique, placed once, labelled on the map). Where the downtown kit has the right wall,
the outer layer IS kit modules (Tokyo Station's brick and windows, the airport's metal and glass); the core piece is
the collider.

| scene | what | size (m) |
|---|---|---|
| RainbowBridge | suspension structure only; the two decks are Road Kit roads (upper 52.5 m, lower 44.5 m, corridor 15 m either side) | 849 × 48 × 129 |
| TokyoTower | splayed legs, orange/white bands, two decks, antenna | 95 × 95 × 334 |
| TokyoStation | red-brick Marunouchi building; the two domed halls are hollow ticket-gate concourses | 320 × 30 × 36 |
| OsakaCastle | stone bases, five tiers, copper roofs, gold top | 41 × 69 × 55 |
| AirportTerminal | one compact terminal (GTA-style scale): hollow furnished hall and concourse, piers, drive, control tower | 242 × 170 × 47 |

Runways: `Airport_Runway` (60 m section) and `Airport_RunwayEnd`, laid one or two per airport.

## The library kit (`kits/library/`, ours) and pieces that still need a modeller

Props are placed by name (`library:Shop_Counter`) from the project's own library (see its `kit.json`). 7 of the
24 re-textured base meshes do not yet read as Japanese and are waiting for hand modelling (`extract.json` `jp`):

| piece | what to change |
|---|---|
| Shop_Counter | add the heated hot-snack case and the cigarette wall behind the clerk |
| Shop_Register | Japanese POS: customer screen, automatic change machine, IC-card pad |
| WC_Toilet | the washlet control panel |
| Gas_Pump | a Japanese ground unit with a big price panel, and an overhead (懸垂式) unit for city stations |
| Station_TicketGate | a slim IC-card gate: lit card pad, short flaps, direction light |
| Station_Bin | three sorted bins (燃えるゴミ / 缶・びん / ペットボトル) |
| BusStop_Sign | a round-top plate on a pole with a heavy round concrete base and a timetable box |

Edit a piece in `library.blend`, then `tools/building_kit/build_buildings.sh` (with `ACCEPT_BOUNDS=1` if its size
changed). `Station_TicketMachine` and `Station_VendingMachine` were re-framed to Japanese sizes and still want
their faces (fare board, drink samples).

Each scene: front faces +Z, origin at the footprint centre on the ground. It holds one merged `Mesh`
(one surface per material), a `Collision` StaticBody3D (a box per wall run, split round each door, plus the
ground and roof slabs), a `Door_<side>_<module>` Marker3D per door (its −Z points out), and a `building` meta
with the facts the probe checks. The ground storey can be entered; the upper storeys are facade only.

## Known gaps in the Standard kit (the manual Japanese pass is PLAN.md 3.6b)

- No pitched tile roof, so there are no detached houses (一戸建て) or machiya.
- No roll-up shutters (シャッター), vertical signs, external stairs or balcony slabs; a balcony is a rail strip.
- The Standard glTF has no colour variants: `MI_RedBrick` and `MI_RedBrick_Pale`, and every `MI_Trim_*`, share
  one texture each. Their vertex colours are a wear mask for the Source version's shader, so the scene build
  switches vertex-colour albedo off. `MI_Trim_MetalConcrete` is hand-tinted light grey (albedo ×1.75, metallic
  0.4) for Japanese panel facades.
- Door leaves are not placed. `world/buildings/Door.tscn` fits a `Door_*` marker when interiors land (I2).
