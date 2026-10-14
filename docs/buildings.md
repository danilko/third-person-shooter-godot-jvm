# buildings

Moved out of `CLAUDE.md` verbatim on 2026-10-09 (PLAN.md 0.5 / F12). Sections:

- Stairs are walked on an invisible ramp; bullets still meet the steps (user, 2026-10-07)
- `assets/` is organised by domain; every modular kit is under `world_source/kits/` (PLAN.md 3.9, 2026-09-17)
- Building kits — a downloaded kit, Japanese types, one scene per type (2026-09-17)
- The project's own library kit, composite sites, and Japanese sizes from PLATEAU (PLAN.md 3.12, 2026-09-18)
- One tone per building, and a Japanese shop window you can see through (2026-09-21)
- The vegetation kit: a family is one baked scale, and a recolour is one material (PLAN.md 3.16 steps 1-2, 2026-09-19)
- The island's buildings, streamed per 252 m cell, and what a city costs (PLAN.md 3.6, 2026-09-19)
- The pavement is for walking on, and the city is not yellow (user's walk-test, 2026-09-20)
- Lots never overlap, arterials have a grade gate, the light crowd flees (2026-09-22, forty-eighth session)
- One row of street-facing buildings a side, tight blocks, weapons in every konbini (user, 2026-09-26)
- Shop counters are in the shop's model; a car runs a person over; car-park entrances stay clear (2026-10-04)
- Shop interiors are a kit of .blend files, one per store (2026-09-27, user-asked)
- Civic plots and placeholder public buildings (2026-09-28, user-asked)
- Sliding doors: one leaf for a restroom, a sensor that stays on the doorway, and a probe that stands in front (2026-09-28)
- The logistics hub, resort hotels in the suburb loop, and five gate findings fixed (2026-09-28)
- Central's 駅前広場 replaces the Tokyo Station placeholder; one facing per joint; stage timings (2026-09-28)
- Mission buildings with interiors, parked vehicles, flyable/sailable craft, and the offshore military runway (2026-09-28/29, user-asked)
- Civic compounds leave room for a truck to drive round them (2026-10-04, user-asked)
- More enterable buildings, Japanese convention (2026-09-29, user-asked)

---

## Stairs are walked on an invisible ramp; bullets still meet the steps (user, 2026-10-07)

"Characters get stuck on stairs." Every stair flight the kits generate carries a RAMP collider along its NOSINGS: a
0.3 m convex slab from one tread in front of the first riser (at the floor) to the front of the top tread (at the top),
so every step sits under it and keeps its own collision. It is on collision layer 7 (`CollisionLayers.STAIR_RAMP`, 64,
named `stair_ramp`), which only CHARACTER bodies collide with (`Character.tscn` mask 19 -> 83; `testMove`, the
step-up, inherits it): bullets, projectiles, blasts and vehicles meet the real steps (user: "other weapons / collision
deal with stairs like stairs"). A navmesh bake parses every layer, so a path walks the slope too.
- Made by the generators: `interior_kit.Bld.stair_ramp` (both flights of `ustair`; `interior_plans_jp.sstair`) and
  `build_station_blends.stair` (`p.stair_hulls`), written as `HULL_stair_<n>` Empties (a kept, hand-edited interior
  piece gets missing ones added, like its shop MARKs). `export_building_kit.py` puts them in a piece's `stair_ramps`;
  `layout_buildings.py` carries them for props, custom (interiors) types and composite parts; `build_building_scenes.gd`
  builds a `StairRamps` StaticBody3D (layer 64, mask 0) of `Ramp<n>` ConvexPolygonShape3Ds.
- Gate **`tools/godot/probe_stairs.gd [-- --scenes=...] [--control]`**: a real Player holds `forward` up every ramp
  of each scene. Steps only (`--control`): stuck on 14 of 24 flights; with the ramps 2 of 24, and both are BUILDING
  defects that fail with steps only too: the police station's roof-level flight has 1.64 m of headroom at its foot
  (the roof slab is not cut over it), and the large city safe house's top flight has a slab edge at head height.
- Not covered: stairs inside `library.blend` pieces (landmarks, civic placeholders, apartment external stairs).
  Since S13 (2026-10-13) a library piece CAN carry them (`library_procedural.Builder.stair_ramp`; the FishMarket's
  7 flights); see `docs/island-world.md` "The fish market rebuilt for cars".
- **A hull must lie ON the nosings, not one riser under them** (2026-10-14): from one tread before the first riser at
  the lower floor to the top nosing, i.e. both ends one tread toward the low side of the flight. The FishMarket's
  first `flight()` ran it from the first riser's foot to the top floor's edge: `probe_stairs` still passed (a walker
  hops the 0.16 m noses), but a SWIMMER stalled at the first riser. A flight down into the sea must also reach ~1.2 m+
  under the surface (a floating body reaches ~0.45 m under its origin).

## `assets/` is organised by domain; every modular kit is under `world_source/kits/` (PLAN.md 3.9, 2026-09-17)

```
assets/characters/godot_chan/   the character: merged_animation{,_f}.{blend,glb,tscn} + extracted textures, textures/
assets/weapons/                 catalog, per-weapon .blend, WeaponLibrary.blend
assets/world_source/kits/       one folder per kit SOURCE (a licence + module boundary):
    quaternius_downtown_city/     the CC0 download (buildings, road textures, decals, props)
    quaternius_zombie_apocalypse/ CC0: blends/ (the download's models the tools build from; the download itself is
                                  deleted), TrafficLight_2_Japan.blend (the owner's
                                  Japanese signal), pieces/props/ generated by build_street_poles.py
    road_kit/                     ours: road_kit.{blend,json}, materials/M_*.tres, furniture.json
assets/world_source/buildings/  building types, BuildingLibrary.blend, PLATEAU landmark blends
assets/world_source/pieces/     road records + sidecars (*.roads.json, lanekits, ground, zones, build manifests)
```
The move was one path map (`tools/reorg_assets.py`: `git mv` with each `.import` beside its source, so every
uid survives, then a text rewrite). A `.blend`'s relative library links are binary and were re-pointed with
`tools/relink_blends.py` (WeaponLibrary → the character, Island_base / Island_base_manual_modified / RoadKitGodot
→ road_kit.blend). Rebuilt road pieces came out with byte-identical glTFs; only the `.tscn`/`.scn` material paths
changed. `pieces/` was deliberately NOT renamed to `roads/`: `build_piece.sh`, the probes and the zone wiring all
expect it (~35 files) and nothing but the name would improve. Trap met on the way: the island piece must be built
with **`NAV_FIT=1`** (each zone piece's navmesh clipped to its own content; it was `NAV_HALF=2016` while the
island was one piece), or its navmesh silently bakes only the default ±252 m about the origin.

## Building kits — a downloaded kit, Japanese types, one scene per type (2026-09-17)

`assets/world_source/buildings/README.md` is the how-to (kits in `assets/world_source/kits/<kit>/`, the type
table and `BuildingLibrary.blend` in `assets/world_source/buildings/`); `tools/building_kit/build_buildings.sh` rebuilds and gates it all
(9 s). The first kit is Quaternius' Downtown City MegaKit (Standard, CC0, credited).
- **Three owners.** `<kit>/kit.json` is the kit's facts, written by hand: licence, the MEASURED module (2 m) and
  storey (3 m), `module_scale`, category rules and facade ROWS (which pieces make one storey of one side).
  `building_types.json` is the Japanese types in modules and rows. `tools/building_kit/layout_buildings.py`
  (pure python, `--self-test`) derives placements, collision boxes and doors. `tools/godot/build_building_scenes.gd`
  only writes what the layout says.
- **The model is the size (W19's rule).** `normalize_kit.py --init` bakes `module_scale` 0.91 into every piece's
  vertices ONCE, for a newly downloaded kit (`source/` -> `pieces/<category>/`, `.gdignore` on source). The module
  becomes the ken 1.82 m, a storey 2.73 m, a banded storey 3.64 m and a door 0.91 × 2.00 m. A piece instance never
  carries a scale.
- **The kit `.blend` OWNS the pieces (3.6b step 1, 2026-09-18), the weapon precedent.** `blender/tools/export_building_kit.py`
  writes `pieces/` + `pieces.json` from `<kit>/<kit>.blend` (each piece collection moved back by its
  `instance_offset`, every UV map and colour attribute kept, textures referenced in `../../textures/`, never
  copied), and `build_buildings.sh` runs it (2.4 s, idempotent: a second run writes 0 files). `pieces.json` is
  measured by `normalize_kit.measure`, the one measure both tools use. **The bounds are the kit's contract with the
  layout**: an export whose piece bounds move more than 1 mm from the committed `pieces.json` (or adds, removes or
  re-categorises a piece) is REFUSED and writes nothing (it stages in a temp dir); `ACCEPT_BOUNDS=1` for a
  deliberate change. Control: `Brick_Plain_3` moved 10 cm in the .blend -> refused, naming the 0.1000 m.
  `normalize_kit.py --init` and `build_building_kit_blend.py` both refuse to overwrite an existing kit .blend
  (`--force`). Measured on the switch-over: all 153 pieces' bounds within 0.1 mm of the downloaded ones, identical
  attributes and materials, up to 12% more vertices where Blender splits on seams; `probe_buildings.gd` 59/59.
- **Proportion rules (3.6b step 6, 2026-09-18)**, in `layout_buildings.py`, each refused when it cannot be honoured:
  - `attached: [sides]` — a side against a neighbour is `kit.party_wall_row` (plain, or banded to match a banded
    storey) all the way up; a door or AC unit there is refused. PencilBuilding: left + right.
  - `setback: {storeys, modules}` — the top storeys stand that many modules back from the front (道路斜線), the strip
    is a terrace slab at the setback level edged with the parapet piece, and collision follows (lower walls full
    length to the terrace, upper walls set back, terrace floor and edge boxes). Under half the depth, and at least
    one full storey below. PencilBuilding 1/1, Mansion 1/1, OfficeMid 2/1.
  - `stair_house` (塔屋) — default on for a flat roof over three storeys: a `kit.stair_house` block (2×2 modules,
    banded metal, door facing the roof) one module in from the back-left parapet. `jp.height_m` is checked against
    the ROOFLINE (`roofline_m`), which excludes it, as Japanese height rules exclude a small roof structure;
    `height_m` (the mesh) includes it. Roof units move clear of it and of the roof centre the probe looks at.
  Not built, and why: a 2.9–3.0 m storey needs a 0.2–0.3 m spacer piece (step 4, `jp_street`); per-instance
  variation needs step 2's material decision.
- **A building is ONE merged mesh**, one surface per material (OfficeMid: 1109 pieces -> 9 surfaces), plus box
  collision split round each door, `Door_<side>_<module>` markers and a `building` meta. Front +Z, origin at the
  footprint centre on the ground (BLENDER_CONVENTIONS.md "Asset"). Only the ground storey is enterable.
- **Materials are the kit's `materials/MI_*.tres`**, written once and then hand-owned, never overwritten.
- **Trap: the Standard glTF's COLOR_0 is a wear MASK, not a colour.** Godot's importer turns on
  `vertex_color_use_as_albedo` for every material on a piece that has it (81 pieces). That rendered MetalConcrete
  near-black and put red blotches on the example buildings. The build writes the `.tres` with it off.
  `MI_Trim_MetalConcrete` is hand-tinted light grey for Japanese panel facades.
- **Blender: one `.blend` per KIT plus one library VIEW.** `<kit>/<kit>.blend` (`blender/tools/build_building_kit_blend.py`)
  puts each piece in a collection whose `instance_offset` is its grid spot, keeps textures external (3 MB) and one
  copy of each material. `buildings/BuildingLibrary.blend` (`build_building_library.py`, like WeaponLibrary)
  assembles every type from the same layout, with LINKED instances. The kit file is the owner (above); after an
  edit there, `build_buildings.sh` then File > External Data > Reload in the library. The glTF importer PACKS images
  unless `import_pack_images=False` (85 MB -> 3 MB).
- Gate **`tools/godot/probe_buildings.gd`** 59/59 over 10 scenes: size, every surface on a kit material, roof at
  the wall top, ground slab, the character's own capsule (r 0.35, h 1.75) fits every door and a ray walks in,
  and the same capsule and ray are blocked at a solid module of that side. Control: a 0.55 m door opening fails
  the capsule check on both Konbini doors while the ray still passes (so the capsule is the load-bearing check).
  `tools/godot/shot_buildings.gd` renders every type with a 1.49 m stand-in (needs a display). Judge the look
  there: no probe can tell a Boston facade from a Tokyo one.

## The project's own library kit, composite sites, and Japanese sizes from PLATEAU (PLAN.md 3.12, 2026-09-18)

`assets/world_source/kits/library/` is the project's own central library of Japanese building parts, interior
furniture and street/station props (CC0, ours). No `jp_` prefix anywhere: the whole game is Japanese.
- **`library.blend` owns the pieces** (the building-kit rule). `blender/tools/build_library.py` built it:
  `--procedural` (re)models `blender/tools/library_procedural.py`'s pieces in place (fridge bay, coffee machine,
  fascia, WC partition, gas canopy/column/island, platform module/ramp/fence/shelter, name board, 1067 mm track,
  apron, parking line and wheel stop); `--reframe` applies `extract.json`'s `fit_box` (a non-uniform resize to a real
  Japanese size) and writes each piece's Japan-likeness review into its `lib_review` property; `--extract` was the
  one-time cut of 24 base meshes from the elbolilloduro packs and refuses to run without the downloads.
- **NEVER commit or import an elbolilloduro download** (or any pack whose page licenses only "the models"): their
  textures mix Textures.com and Pexels images that may not be redistributed. The base meshes were cut out once,
  resized, re-textured with our palette, credited (CREDITS.md), and the downloads deleted; `.gitignore` refuses
  `kits/elbolilloduro*/`. Pexels/Unsplash are NOT CC0; ambientCG and Poly Haven are.
- **FLAT TOON MATERIALS (user, 2026-09-28).** `retone_downtown_kit.FLAT`: every downtown-kit building material
(the PLATEAU facade tones, trims, doors, interiors, concrete) drops its photo albedo and ORM and wears ONE flat
colour, keeping only its normal map; brick, asphalt, dirt, decals and glass keep their textures. The library's photo
sets (plaster, tiles, steel, wood, fabric, corrugated, smooth concrete) are `albedo_tex: false` at their measured
mean. `FLAT = False` restores the textured look.
- **`palette.json` owns every library material's look.** `tools/building_kit/build_library_palette.py` writes
  `materials/MI_*.tres` (world-space triplanar, so a foreign mesh needs no UVs) and our generated textures
  (`T_Goods`, two brand-neutral fascia bands); `--check` runs first in `build_buildings.sh`. ambientCG CC0 sets
  are listed in `textures/SOURCES.md`.
- **2026-09-28: every elbolilloduro-derived piece is GONE** (owner: keep only sources we can confirm). The 21 base
  meshes (and their copies in `kits/shops/Shop_*.blend`) are same-size PLACEHOLDER BOXES
  (`blender/tools/replace_removed_meshes.py`, one-shot), listed with a modelling brief in
  `kits/library/placeholders.json`; `extract.json` and `build_library.py --extract/--reframe` are deleted. A file-level
  audit found no elbolilloduro texture anywhere (`assets/LICENCE_AUDIT.md`, "Audit 2026-09-28"). The toon/anime look the game is heading for (PLAN.md 6.x) will change these
  to flat colours + a shared palette atlas; the palette file is where that change lands.
- **Generic names** where the piece is not specific: `Shop_Counter`, `Shop_Register`, `Shop_Gondola`,
  `Shop_FridgeDoor`, `Shop_IceFreezer`, `Fascia_Shop`; `Rest_*`, `Kitchen_*`, `WC_*`, `Gas_*`, `Station_*`,
  `Platform_*`, `BusStop_*`.
- **Japan review** (`extract.json` `jp`): 16 base meshes read as Japanese, 2 were re-framed to Japanese sizes
  (ticket machine 0.8 x 0.55 x 1.8, vending machine 1.0 x 0.72 x 1.83), 7 need a modeller: counter (hot-snack case,
  cigarette wall), register (Japanese POS), toilet (washlet panel), fuel pump (Japanese ground/overhead unit),
  ticket gate (IC-card gate), bin (three sorted openings), bus-stop sign (round-top plate on a concrete base).
  Listed in PLAN.md 3.12b and `assets/world_source/buildings/README.md`.

**The layout grew props and composite sites** (`tools/building_kit/layout_buildings.py`):
- a type's `props`: library pieces by name (`library:Shop_Counter`), `at` [x, z] in the footprint frame, `y`, `yaw`,
  `repeat` [n, dx, dz], `collide` `box` (turned bounds, the default) / `hull` (a convex hull of the mesh, for a
  ramp; `build_building_scenes.gd` makes a `ConvexPolygonShape3D`) / `none`.
- `check_doors_clear`: nothing a prop adds may stand in the 1.2 m inside any door, across its width, at knee and
  chest height (self-test control: a gondola moved in front of the konbini door is refused). The back side numbers
  its modules from +X, so back door 0 is at the RIGHT end seen from the front.
- `composites` in `building_types.json`: a SITE of whole building types (`parts`, turned and moved, with their
  doors, walls and collision) plus props on a paved `apron` (tiles skipped under a part), on one footprint
  centred on the origin. `probe_xz` names a clear spot for the roof/floor probe (a canopy, not a pump island);
  `probe_buildings.gd` reads it.
- New types: `GasKiosk`, `StationBuilding`, `FamilyRestaurant`; `Konbini` re-sized to 10 x 6 ken with a full
  interior. Composites: `GasStation` (canopy on three columns over three islands, six pumps, the kiosk),
  `KonbiniLot` (the konbini behind seven 2.5 x 5.0 m bays), `StationRural` (a one-platform country station: the
  station building with ticket gates, a 21.8 m platform 0.94 m above the rail with a ramp at each end, shelters,
  benches, a name board, 1067 mm track). Gate `probe_buildings.gd` **103/103** over 16 scenes; renders
  `tools/godot/shot_buildings.gd`.

**Sizes come from PLATEAU as MEASUREMENTS** (`tools/plateau2json/measure_building_types.py`, run locally on the raw
CityGML outside the repo; only rounded numbers enter the repo; credited in CREDITS.md "Real-world data"):

| class (use + size window) | Ota-ku 2023 | Tama + Higashiyamato 2023 |
|---|---|---|
| konbini (1-storey commercial 120-350 m2) | 11.0 x 18.4 m, 184 m2, 5.1 m | 11.3 x 18.8 m, 193 m2, 4.8 m |
| family restaurant (1-storey commercial 350-900 m2) | 21.2 x 29.5 m, 6.0-7.5 m | 19.0 x 27.5 m |
| small station building (1-2 storey transport 30-400 m2) | 7.4 x 13.4 m, 6.7 m | 6.9 x 12.6 m, 5.6 m |
| shop + house, 2-3 storeys | 6.4 x 10.8 m, 3.7 m / storey | 7.1 x 10.9 m, 3.55 m / storey |
| detached house, 2 storeys | 7.1 x 10.4 m, 7.4 m | 7.5 x 10.2 m, 7.5 m |

(p50 short side x long side, area, height.) PLATEAU records use, not brand, so each class is a use + size window,
and it does not record gas-station canopies (their sizes are design choices, stated in the type).

**Landmarks are our own base models, and no PLATEAU data is left in the repo** (owner, 2026-09-18). In
`library_landmarks.py` (numbers measured from PLATEAU or public record, written in the code, toon-flat palette):
- `RainbowBridge`: towers 575 m apart, 127.8 m tops, 115 m side spans, cables sagging to 69 m. **Structure
  only: its two decks are Road Kit roads** laid through a clear corridor |y| < 15 m (a 29 m T2 fits) at 52.5 m (upper)
  and 44.5 m (lower), stations with `pillar_skip`; a vertex check confirms nothing of the structure is in the corridor.
- `TokyoTower` (splayed legs, bands, decks, antenna; replaces `PLATEAU_TokyoTower.blend`, which was ours).
- `TokyoStation`: 320 m red-brick block with its two domed halls HOLLOW, ticket-gate concourses furnished
  from the library (gates, machines, benches), street and platform doors.
- `OsakaCastle`: stone bases 40.6 x 69.3 m, five tiers, 55 m.
- `AirportTerminal`: GTA-style scale (user: one terminal, one or two runways): a hollow 150 m departure
  hall (check-in islands, benches, shop) and concourse, two piers, the elevated drive, a small control tower.
  `Airport_Runway` (60 m section) and `Airport_RunwayEnd` lay the runways.
- **Landmarks are managed as ordinary buildings** (user, 2026-09-18): they are the `custom` list in
  `building_types.json` (a building made from ONE library piece plus `props` and `doors` in the piece's frame, through
  `layout_example`), scenes `<Name>.tscn` beside the konbini, gated by the same probe; `landmark: true` is only a tag
  (unique, placed once, labelled on the map). No `Landmark_` prefix. `shell()` builds their hollow rooms.
- **Their outer layer uses the downtown kit's own wall modules where the kit has them** (user): Tokyo Station's main
  block is clad with `Brick_Window_Square_Single` / `Brick_Plain_3` (three window storeys over six kit rows, 310- and
  12-vertex modules: the ornate 623-vertex window took the station to 495k vertices, now 141k); the airport's hall
  sides and concourse apron face with `Metal_Plain_3` / `Metal_Window_Half` / `Metal_FullWindow`. The airport's hall
  FRONT stays clear library glass: the kit's glass carries a fake lit interior that would hide the real furnished
  hall. The castle, bridge and tower have no kit equivalent and stay modelled. The collider is the core piece alone
  (`trimesh_pieces: 1` -> `build_building_scenes.gd` builds a ConcavePolygonShape3D from those surfaces), never the
  cladding or furniture.
- Deleted: `assets/world_source/plateau/` (42 precincts), `PLATEAU_*.blend`, `RecycledBuildingKit.blend`,
  `plateau_reference/`, `archive/world_6x6/`, `build_tokyo_tower.py`. Gate `probe_buildings.gd` **130/130**.

**Licence audit** (`assets/LICENCE_AUDIT.md`): everything traced (`SNR1` is Quaternius 50 Low-poly Guns, CC0,
owner-confirmed); every PLATEAU-derived file deleted after the landmarks were rebuilt (above).

## One tone per building, and a Japanese shop window you can see through (2026-09-21)

**A city of ONE grey is the same defect as a city of one yellow.** The retone gave `MI_Trim` a single target and
the merged mesh is per TYPE, so every building of a type wore it. The mixture is now per BUILDING, and it costs
no new mesh: the tone is an **instance override** (`surface_material_override/<i>`) on the shared mesh, so 3852
buildings wear 4 greys out of 6 materials.

- **A FACADE IS TWO MATERIAL FAMILIES HERE, NOT ONE.** `Trim_*` pieces wear `MI_Trim` (the 磁器タイル of a
  mansion, a shop-house, a pencil building); `Metal_*` pieces wear `MI_Trim_MetalConcrete` (an office, a
  warehouse, a konbini — and the SIDES of nearly every other type). Measured after a first pass that named only
  the tile: **4 of 19 types had a tile surface at all**, so downtown's offices and the harbour's warehouses
  would have kept one grey between them. Both families get the same four levels.
- **PLATEAU was RE-MEASURED, and that is itself a finding.** The percentiles this repo carried (p10 113 /
  median 146 / p90 168) had no way to be re-derived. `blender/tools/measure_plateau_facades.py` now exists and
  states its method (a facade material here is TEXTURED, so its tone is the mean of its own base-colour image,
  converted linear → sRGB before averaging), and over the SAME 3048 materials it reads **p10 100.0, median
  135.6, p90 160.6, mean 132.6, R-B +0.9**. Two consequences: Tokyo is GREY, so every tone is a LUMINANCE on one
  neutral texture and never a hue; and the shipped single target of 150 sat at this distribution's **p75** — the
  whole city was lit a quarter brighter than its reference — so `MI_Trim` moved onto the measured median.
  Three of the four tones are measured percentiles outright (100 / 136 / 161); the fourth (185) is a stated
  extension, because aerial photogrammetry compresses both tails and a white porcelain-tile facade is ordinary.
- **One owner each, and neither fact is written twice.** `retone_downtown_kit.py` writes the variants FROM each
  base `.tres` (so a change to the facade's textures reaches all four) plus `facade_tones.json`, the one record
  of which materials are facades. `build_building_scenes.gd` writes `facade_surfaces` into each type's own meta,
  because only the merge knows its surface order. `island_buildings.py` picks the tone from the slot's OWN key
  with its own salt — never by drawing from the `rng` that decides which TYPE stands there, which would silently
  re-roll the whole city.
- **A region may bias its tones**, which is what makes a working district read greyer: `REGIONS`' 7th field is a
  weight per level, and `harbour`/`industry`/`nightlife` draw from the dark end (measured: industry places 202
  Slate and 168 base and **no** Pale at all).
- Gates: `island_buildings.py tones` (the materials are distinct greys, every override addresses the surface its
  type's meta records, the mixture is a mixture) and `probe_buildings.gd`'s own runtime pass — it LOADS every
  cell and reads the overrides back off the live `MeshInstance3D`, which is the half a text check cannot make,
  because a `.tscn` whose override syntax Godot silently drops reads exactly like a city that was never given a
  mixture. Control: one scrambled override fails BOTH gates.

**A JAPANESE SHOP WINDOW IS CLEAR GLASS WITH A STRIP ACROSS THE MIDDLE** (user, twice: "the konbini window is
still not visible ... in Japan the store window glass CAN see internal folks, just in the middle of the glass
there is a strip along the whole window panel, white gloss with store colour strips; top and bottom stay
transparent"). **The glass was never the cause.** Measured on the kit's `Metal_FirstFloor_Window`: behind the
2.21 m pane (y 0.470–2.677 at z −0.061) sits an opaque `MI_FakeInterior` quad (y 0.184–2.714 at z −0.067). That
card is what you were looking at.
- **A shopfront on a building with a ROOM loses the card**, and the test is derived, not authored:
  `layout_buildings` writes `has_interior` (true exactly for the four types that place interior fittings), and
  `kit.json` names `shopfront_rows`, so the same glazed piece on a tower's curtain wall keeps its card — which
  is what makes an unenterable building read as occupied. That is the gate's control, and it passes on
  `OfficeMid` and `Mansion`.
- **The layout now records each piece's ROW**, which only it can know: a glazed panel on a shopfront is a window
  you look into, the same piece on a floor 8 of a tower is not, and recovering that from the geometry afterwards
  is guesswork.
- **A shopfront gets its own clearer glass** (`MI_GlassShopfront`, alpha 0.14 against the tower glazing's 0.28),
  which closes the follow-up `MI_Glass`'s own comment recorded — it said the ground storey wants its own
  material and that "the row table knows which rows are shopfronts, the MERGED mesh no longer does". It does now.
- **The 目隠しシート** is built from the panel's OWN glass (width, plane and floor), so a narrower pane gets a
  strip that fits it: a white gloss band with two livery stripes, **1.25–1.70 m above the panel's floor**. That
  height is measured from the FLOOR and not from the pane's bottom edge — adding it to the glass's own bottom
  (0.47) put the strip at 1.72–2.17 m, over a head rather than across a face, which is what the first render
  showed. Liveries are brand-neutral (blue/green/red/amber per type) and a type's own fascia picks which.
- Gate: `probe_buildings.gd` **1043/1043**, asserting both halves — a shop window has no card and wears the
  strip, glazing that is not a shop window keeps its card and gets no strip.

## The vegetation kit: a family is one baked scale, and a recolour is one material (PLAN.md 3.16 steps 1-2, 2026-09-19)

`assets/world_source/kits/quaternius_stylized_nature/` is Quaternius' Stylized Nature MegaKit (Standard, CC0, 68
of its 116 models; credited) in the project's kit shape. `STUDY.md` in it is the measured record, regenerated by
`tools/building_kit/study_nature_kit.py --md`; `tools/godot/shot_nature_kit.gd` (needs a display) is the picture
beside it, one per family with the character's 1.49 m capsule for scale, plus `--variants` (the leaf colours) and `--before` (the download's own sizes, each piece scaled back by the inverse of its baked family scale).
- **It is a kit of UNRELATED PROPS, so `module_scale` is the wrong shape for it.** A modular kit has one number;
  trees, grass and stones were modelled at unrelated sizes. `kit.json` carries **`category_scale`** instead —
  ONE scale per family, never one per model (so a family keeps its own variation), BAKED into the vertices by
  `normalize_kit.py`, so nothing downstream holds the number (W19: the model IS the size). `material_prefix`
  ("MI_") renames the download's materials on the way in, because the game resolves a surface to
  `<kit>/materials/<glTF material name>.tres` and every other kit names them `MI_*`.
- **Every scale is a MEASUREMENT against what a Japanese example really is**, per family, on the axis that
  family is judged on (a tree by height, a stepping stone across). **The trees came out right** (every tree
  family inside its band, baked 1.0: a broadleaf 7.0–9.4 m is a pruned street keyaki, a pine 7.3–10.2 m a
  coastal kuromatsu) **and everything at ground level did not** — a clover leaf stood **1.26 m**, a flower
  2.42 m, a grass tuft 1.33 m, a stepping stone 1.48 m across, a cobble 0.45 m. Those are baked down (lawn
  x0.10, flowers x0.21, grass x0.41, mushrooms x0.22, cobbles x0.44, stepping stones x0.30, spreading plants
  x0.37).
- **A DECLARED glTF box is a hint, not the truth.** `Fern_1` and `Plant_1_Big` declare a POSITION box **3.18 m**
  and **1.39 m** larger than their own vertices, which is exactly what glTF asks a reader to trust — so the fern
  measured 2.69 m when it is 0.84 m and nearly took a x0.28 rescale it did not need. `normalize_kit.measure`
  reads the VERTICES wherever the buffer is at hand (`measure(gltf, blob)`), `declared_bounds_error` is the
  check the bake prints, and `scale_gltf` writes each accessor's min/max **from the scaled data** rather than
  scaling the declaration, so the lie stops here. The downtown and library kits re-measure **0.000000 m**
  different, so the change is free where the declarations were honest.
- **A RECOLOUR IS ONE MATERIAL, NOT A NEW TEXTURE.** Each leaf shape ships twice: `X.png` is a pure WHITE mask
  (measured mean 253,253,253 over its opaque texels) and `X_C.png` is the same shape already tinted. So sakura,
  a fresh-green keyaki, an autumn ginkgo and a momiji are one `albedo_color` each over the white one, with no
  new texture and no new mesh — `shot_nature_kit.gd --variants` renders the five candidates side by side. It
  also explains what the pictures show: `Leaves_TwistedTree_C` is RED, so the gnarled trees and `Bush_Common`
  ship as autumn momiji, and their green partners are one material away.
- **`Bark_NormalTree` is declared alpha MASK and its texture is opaque at every texel**, so the ten trees using
  it alpha-tested their trunks for nothing; ours is opaque. `Grass.png` is opaque too — the grass is modelled
  blades, not cards. The six genuine leaf/flower cards (56–76% of their texels under the 0.2 cutoff) are
  ALPHA_SCISSOR, never blend: a tree is one surface and a blended one sorts as a whole.
- **A piece's base is BURIED below its origin** (0.02–0.34 m, scaled with it) and that is KEPT: it is the
  download's own convention and it hides the join with uneven ground. A building kit's origin sits ON the
  ground, so `pieces.json` `min` y is negative here and zero there. A tree is not centred in plan either
  (`TwistedTree_1`'s canopy reaches 11.3 m one way, 2.2 m the other): the origin is the trunk, which is what a
  placement wants, and the bounds are not a footprint.
- **Nothing new was written to USE it.** The pieces resolve through `layout_buildings.lib_piece`
  (`quaternius_stylized_nature:CommonTree_3` in a type's `props`) and their materials through
  `build_building_scenes.gd`'s per-kit lookup, both unchanged — verified by resolving four pieces through the
  real path. Placing vegetation in the WORLD (street trees derived from the road facts, per-region scatter,
  MultiMesh per zone) is PLAN.md 3.16 step 4 and is deliberately not built: a kit with no user is the cheapest
  thing to get wrong.
- Gates: the kit round-trips through its own `.blend` inside `export_building_kit.py`'s bounds contract;
  `probe_buildings.gd` 563/563 and `layout_buildings.py --self-test` are unchanged by the shared-measure change.

## The island's buildings, streamed per 252 m cell, and what a city costs (PLAN.md 3.6, 2026-09-19)

**`tools/island_buildings.py`** places the city. `derive <heights.f32>` (a dump of World's STAMPED terrain:
`dump_height_grid.gd -- <out> -2304 -2304 2305 2305 2`) writes `assets/world_source/buildings/IslandBuildings.json`
(reviewed like the record) and `src/main/resources/com/openworld/world/IslandSidewalks.json`; `write [--check]` turns
the placements into `world/buildings/cells/Bld_island_<gx>_<gz>.tscn` (instances of the type scenes at world
transforms) and World.tscn's `BuildingZones` block. Nothing is a typed coordinate:
- **Blocked** = every solved road surface (`point_edges.band_corridors`, at ANY height, so nothing stands under the
  expressway) + that road's footway + 1.5 m, the sea + 16 m, every `SiteZones` site and landmark.
- **Frontage rows**: each at-grade road side offset by (paved half + footway + gap); a building's FRONT stands on the
  line facing the road; `rows` more lines behind at the region's `pitch`. Region = the first of `REGIONS`' boxes
  (downtown inside C1 / city / harbour / residential / suburb / farm), each a weighted mix; lots, gas stations and
  restaurants only on arterials (>= 2 lanes a side) with a spacing per kind. Choice hashed from (road, side, row,
  slot): an unchanged record rebuilds byte-identically.
- **Every building stands on a concrete LOT at sidewalk height** (user): road surface + 0.15 m kerb, never the
  heightmap. Refused where the ground stands above the slab or falls more than 1.2 m below it. The frontage lot
  reaches the footway edge; then `grow_lots` pushes every side out a metre at a time (30 m along the street, 10 m
  back/front) until it meets a footway (`field.road`) or another lot (`field.owner`: lots never overlap, coplanar
  slabs would z-fight). Per cell the slabs are ONE `MultiMeshInstance3D` of a scaled unit box in the footway's own
  world-triplanar `M_ConcreteTile` (one draw call) + one `StaticBody3D` of box shapes. Left: a ~10 m bare strip at a
  junction pad's own corner footway.
- A cell is a QUARTER road cell (252 m): ZoneManager instantiates one cell's buildings in one frame
  (GEO_INSTANTIATE), and a 504 m downtown cell (~250 buildings) was a 20-26 ms frame; 252 m gives 15.5 ms worst.
  Load 800 / unload 1100 m from the cell centre. The Road Kit dock skips these zones (`/world/buildings/` path).

**Building scenes** (`build_building_scenes.gd`): meshes are indexed with `ImporterMesh.generate_lods` and carry a
`visibility_range_end` by height (350-900 m, dithered fade); the solid types also get a box `OccluderInstance3D`
inside their walls (`rendering/occlusion_culling/use_occlusion_culling` is on), while glass-fronted and hollow types
get none -- a body inside must stay visible.

**EVERY building ships SHUT, and a type has three variants** (user, 2026-09-19). A city of open doorways into hollow
shells reads worse than a city you cannot walk into, and an interior is authored content:
- **`<Id>.tscn`** -- shut. The kit's own `Door_1` leaf is merged into every door frame (a plain leaf of the declared
  opening where the doorway is modelled into a library piece, e.g. a terminal's glass front) with a collider. No
  nodes, no cost. `metadata/building.doors_closed`.
- **`<Id>_Open.tscn`** -- what a MISSION places: a `world.Door` per doorway (hinge at the opening's edge, the kit
  leaf, a sensor band), **MANUAL and LOCKED**. `doors_locked`.
- **`<Id>_Shop.tscn`** -- a shop or the player's home base: the same Doors, **unlocked and AUTOMATIC** (GTA's
  always-open store; Japanese shop doors are automatic). `doors_shop`. It reuses `_Open`'s mesh and collider.
`island_buildings.py` places `SHOP_TYPES` (konbini, konbini lot, family restaurant, gas station and kiosk, the two
stations -- 127 of them) as `_Shop`, one `PUBLIC_BUILDINGS` anchor as the player's home base, and `OPEN_BUILDINGS`
anchors (the konbini job's shop) as `_Open`, which wins. `probe_buildings.gd` asserts: a shipped door blocks the
capsule and a ray; a `_Open` door starts locked and manual and still blocks; a `_Shop` door starts unlocked and
automatic; and either variant's leaf CLEARS the doorway once opened (the door is driven directly there -- who may
open it is `world.Door`'s own sensor rule, which counts only `Character` bodies).
**`Door.unlockMissionId` blank now means NEVER** (it meant "any mission completes"): with every building locked, the
first mission completed would have unlocked every door in the world, and it silently undid `KonbiniMission`'s own
re-lock at the end of the job. `"*"` is the any-mission wildcard. A mission unlocks only doors that are LOCKED
within its radius, so a shop it stands next to stays open and is not shut when the job ends.

**Measured** (`tools/godot/probe_city_perf.gd`, NEEDS A DISPLAY, vsync off, noon pinned; street level downtown, this
dev PC): roads alone 2.0 ms p50 / 0.27 M tris; buildings as first placed 5.8 ms / 12.0 M tris / 1160 draws; with
LOD + occlusion + 252 m cells 4.3 ms / 4.6 M / 714. LOD barely engages (meshoptimizer's error on the kit's disjoint
pieces is ~1.9 m, so LOD1 appears past ~1 km); OCCLUSION is what worked. Sun shadows at 600 m are 18-24 M shadow
tris; 200 m makes it 5.7 M (not changed: a look decision). Flags: `--legs=`, `--no-buildings`, `--no-lod`,
`--shadow-distance=`, `--shots=<dir>`, `--crowd` (below).

**The crowd costs more than the city.** `--crowd` streams pedestrians and traffic through the REAL ZoneManager at
one street view (runtime Zones: `SpawnConfig.behavior`, `VehicleSpawnConfig`) and reports per scenario the frame,
the per-physics-tick script time, draws, AI LOD tiers and walker readouts. Per agent per physics tick: sidewalk
walker ~0.12 ms (0.06 ms gliding), navmesh wanderer ~0.12, armed fighting AI ~0.13, traffic car + driver
~0.16-0.18. Past ~16.7 ms per tick Godot runs up to 8 catch-up ticks per frame (a physics SPIRAL): 150 walkers took
a frame from 5 to 177 ms. How the cost was found, for next time: disabling a body's scripts, children, rays,
modifiers, AnimationTree, nameplate or hitbox bones changed nothing; `process_mode = DISABLED` on the WHOLE body
did; bisecting its direct children (cumulatively, with the spiral in mind: read the per-tick column, not the frame)
put ~12 of the ~18 ms in `MovementController` (move_and_slide + step-up shape tests against the city's colliders).
`asprof` (async-profiler, in the JDK's bin/) attaches to the Godot process and showed 83% in the engine binary,
i.e. engine work driven through the bridge. Jolt reports 0 for every Performance physics monitor.
- **Ambient pedestrians** exist now: `SpawnConfig.behavior = "sidewalk"` makes ZoneManager set the AI down on a
  footway inside the zone's box (`world.Sidewalks`, a 50 m bucket index over `IslandSidewalks.json`) with
  `ai.SidewalkWalkerController` (walks the footway, turns at its ends, no navmesh, no perception); an empty
  `weaponScenePath` spawns unarmed. Beyond the ACTIVE tier (> 80 m) a walker GLIDES: the controller moves it along
  the footway directly and `MovementController` skips it (150 walkers: 22.4 -> 13.0 ms per tick). What remains is
  the per-node JVM callback cost of a full `Character` body; a real crowd needs a lightweight ped (PLAN.md 3.6d).

**The first mission: "the konbini job"** (PLAN.md 4.8). `game.mission.KonbiniMission` on
`game/mission/M01_Konbini.tscn` (instanced in World.tscn under `Missions`, at a downtown konbini): a Zone streams
three NEUTRAL named story characters; a `ZoneTrigger` fires `m01_start`, whose handler (host only) starts
`M01_Konbini.tres` through the director and turns the crew `gang_a`. Crew down + boss under half health -> he
surrenders (`neutral`, FLEE) and the player chooses: kill him (`BOSS_KILLED`) or let him get 45 m / 15 s away
(`BOSS_SPARED`, the only way to unlock the declared `m02_informant`). Objective type **`SCRIPTED`** (new): the
content decides the outcome, because ELIMINATE_ALL counts every non-player character in the tree, which in a
populated world is every traffic driver. Fails when every player is down or the boss's zone unloads. Gate
`tools/godot/probe_konbini_mission.gd -- --case=kill|spare` (15/15 each; `--control` never surrenders, fails 5).
Probe trap: a node added in `SceneTree._initialize` is not in the tree until the next frame (`global_position` reads
0 and `get_node` of an AutoLoad fails) -- await a frame first.

## The pavement is for walking on, and the city is not yellow (user's walk-test, 2026-09-20)

A batch of walk-test reports, each measured before it was touched. PLAN.md 3.18 carries the ones still open.

**The crowd got stuck on street furniture, and the cause was the WALK LINE, not the brain.** The footway
centreline the ambient crowd follows (`IslandSidewalks.json`, derived by `island_buildings.py`) was the footway's
MIDDLE, while every street prop stands in the KERB-SIDE strip — so the two were laid on top of each other.
Measured over the island, every solid prop against the walk line for a 0.35 m capsule: **1081 of 1139 planters
blocked it (worst −0.92 m), 483 of 1061 lamps (−0.13), 108 of 333 signals (−0.55), 2 of 401 trees**; bollards were
clear. A blocked walker is stuck FOR EVER, not briefly, because `SidewalkWalkerController` advances `along` by the
step the body actually took: no step, no progress, so it never reaches the end of its path and never turns round.
- **`island_buildings.ped_walk_offset` puts the line in the middle of the CLEAR band** — outboard of the furniture
  strip, inboard of the footway's outer edge. The strip is DERIVED from `furniture.json` (`furniture_strip`): each
  kerb-side asset's own offset plus its own half width across the footway, and only the assets a footway that wide
  can carry (`*_min_footway`). It reads the SAME table the placer reads, so the two cannot come to disagree about
  where a planter is. On a 4 m footway the line moves 2.00 → 3.05 m from the kerb; on a 2 m footway 1.00 → 1.55.
- **Measured after: 1676 → 88 blocking, and planters 1081 → 0.** What is left is 82 signals grazing at −0.00 m on
  2 m footways (a 1.2 m signal strip plus a 0.7 m capsule does not fit in 2.0 m — the remedy is a narrower
  `signal_kerb_offset` on a narrow footway, not a different walk line) and 6 outliers where the line curves at a
  pad. The gate is **`island_buildings.py clearance`**, which measures from the OTHER side of the pipeline — the
  placer's own output against the derived record — so it cannot agree with `furniture_strip` by construction.
- **`SidewalkWalkerController` gained an unstick rule**, because the derivation cannot see a parked car, a player
  in a doorway or another walker: under `STALL_PROGRESS_M` (0.25) of progress in `STALL_SECONDS` (1.5) reverses
  `dir` and counts a `stalls`. Turning round rather than stepping around is deliberate — it is what a pedestrian
  meeting a blocked passage does, it costs two doubles and a compare, and stepping around wants the navmesh this
  whole tier exists to avoid.
- **`island_buildings.py sidewalks`** re-derives ONLY that record, with no terrain dump and no building moved: the
  walk line is a fact about the ROAD, which the road solve already has. `walk_lines` is the one owner, shared with
  `derive`.

**The city was yellow because three materials share one texture and none of them was tinted.** Measured, the mean
of each base-colour texture: `T_Trim` **146/135/102, R−B +44** (the tile facade — every `tile_*` row, and the sides
of nearly every type), `T_MarbleFloor` +49, `T_RedBrick` +44 (correct: brick IS red), `T_Ornaments` +27, against a
neutral `T_Concrete` (+5). Two defects that no screenshot separates: **`MI_Trim`, `MI_Trim_Dark` and
`MI_Trim_Green` are the same texture with no tint on any of them**, so the kit's three trim variants render
identically and a "dark" shopfront frame is the same tan as the wall behind it; and **`MI_InteriorWall` is on
`T_RedBrick`**, so every interior wall in the game is brick brown. `tools/building_kit/retone_downtown_kit.py` is
the owner: each row is "this surface should read as a <target> grey", and the tint is `target / measured mean` per
channel, so the numbers are arguable rather than picked by eye. Shipped: the tile facade 178 (light off-white
porcelain), dark panel 52, balcony guard 140, exposed concrete 168, interior wall 214 and ceiling 226 (both moved
onto the neutral concrete texture), interior floor 212 (white tile). Brick, asphalt, ground and the lit-window
fake are left alone, each with its reason in the table.

**What a Japanese facade MEASURES, from the two sources the user named** (2026-09-20). The photograph
(`/data/danilko/references/japan/20240317_133825.jpg`) reads **strongly COOL** — built mean R−B **−13.8**, every
cluster cool, sunlit facades 195/201/202. `japan_city.blend` (PLATEAU, textured, **3048 real Tokyo facade
materials**) reads **NEUTRAL and mid-light** — mean 143.8/142.4/142.0, R−B **+1.7**, luminance p10 113 /
**median 146** / p90 168, R−B spread only −4.0 to +7.2. **The disagreement is the finding:** the photograph is lit
by a blue sky, so its cool cast is LIGHTING, which our own sky light applies again at run time — tinting the
albedo cool would count it twice. PLATEAU is averaged over a city and largely de-lit, so it is the albedo source,
and what it says is that Tokyo is a **neutral grey at ~146**, not white and not warm. The facade targets sit at
150 because of it, not at the 178 the first pass carried.

**A TINT CANNOT REACH A PER-TEXEL HUE, AND RUST IS PER-TEXEL** (user, 2026-09-20: "the grey still has a reddish
cast … can the material be changed?"). `albedo_color` MULTIPLIES, so it moves a texture's MEAN onto a neutral
target while every rust-streaked texel stays rust — which is exactly what a render of the retoned kit showed.
`retone_downtown_kit.neutralise` writes `<stem>_Neutral.png` beside each kit texture, and it separates the two
things by SCALE rather than by judgement: a rust run is hundreds of texels across, a tile joint is a few, so the
copy keeps **only what survives a high pass** (`lum − blur(lum, 48 texels on a 2048 px map)`) laid back on a flat
field. Measured, large-scale blotching against detail kept: `T_Trim` **35.1 → 4.4** (detail sd 15.3),
`T_MetalConcrete` **30.9 → 1.6** (7.5), `T_Ornaments` 19.0 → 2.4 (13.3). The NORMAL and ORM maps are untouched,
so all the relief and roughness variation stays — the user's own framing, "keep the normal, remove the rust".
`T_RedBrick` is not in the list: brick is red.

**A door's STYLE is a fact about the door, not about the site it stands on.** `layout_composite` took
`door_style` from the COMPOSITE's row, so the gas station's kiosk had a hinged swing door while the same kiosk
standing alone had the konbini's 自動ドア. The part's own type row already says which it is, so the door carries
it (`d["style"]`), `_openings` hands it to `_panels` and to the door loop, and `probe_buildings.gd` asks the
doorway NEAREST each leaf instead of the building. 979 checks PASS.

**A hinged door swings AWAY from whoever opens it** (`Door.swingBothWays`, on). The sensor is a volume around the
doorway, so it fires while the body is still walking up — which is what makes an automatic door feel automatic,
and is exactly why a leaf that always swings one way meets somebody half the time. The leaf spans the node's local
−X, so its normal is local +Z and the opener's own local Z IS the side; the sign is taken ONCE, at the moment the
door starts to open, so it cannot flip mid-swing. Off, the leaf always swings by `+openAngleDeg` — the old
behaviour, and the control.

**THREE heights, one rule** (and the second half came from the user's Shibuya photograph: the public footway in
dark asphalt with its yellow 点字ブロック, each building's OWN frontage paving in a different material, slightly
PROUD of it). In Japan the footway belongs to the ROAD and the strip in front of a building belongs to the LOT
(民地), so they are two surfaces at two heights, never one: footway top = carriageway + `KERB_H`; lot slab top =
footway + `LOT_RAISE` (6 cm); building floor and a composite's apron = lot + `FLOOR_LIFT` (2 cm). `FLOOR_LIFT` is
the z-fighting fix and it fixes it by CONSTRUCTION — a composite draws its apron at its own origin height, so
while that was the slab's height too the two were exactly coplanar, which is what z-fighting IS and what no depth
bias answers honestly. 8 cm from footway to floor: visible, the shallow end of the 10–15 cm a Japanese shop really
stands up, and far under `stepHeight`. Both are applied in `write`, so changing them needs no terrain dump and no
re-derive. HISTORIC first attempt: **A lot is white tile, and it sits 2 cm below the floor it meets.** The forecourt a player crosses to a shop door
is the same surface family as the floor inside it (`M_TileWhite`, the footway's own triplanar concrete tinted
near-white at a 0.6 m tile), and `island_buildings.LOT_DROP` is the z-fighting answer: a composite draws its own
apron at its origin height and the lot slab was exactly coplanar with it, which is what z-fighting IS and what no
depth bias fixes honestly. A Japanese shop floor stands 10–15 cm above its forecourt anyway, so the drop is both
the fix and the look, and it is far under `MovementController.stepHeight`.

**A manhole belongs in the gutter, not down the lane** (user). `manhole_spacing` is 0, and `_lane_props` returns
on it — the placement is kept because a service cover down the lane IS correct on an older trunk road or in a
tunnel, and data, not code, should decide. The kerb-side `drain` run is untouched.

**Street trees: a pit, and two Japanese species.** `point_furniture._tree_pit` lays a 1.4 m square of `M_Dirt`
(植樹枡) at each tree's foot — paint, not a piece, because a pit is a hole in the paving and two triangles per tree
merge into the piece's one paint object, against a modelled kerb ring that would be a second asset and a second
batch. `tree_assets` is now **sakura** (`CommonTree_3`, with `MI_Leaves_NormalTree` retinted over the kit's white
leaf mask) and **黒松** (`Pine_3`), two species instead of three interchangeable broadleaves. A GREEN CommonTree
beside the pink one needs a per-asset material override, which is PLAN.md 3.16 step 3's own next step.

## Lots never overlap, arterials have a grade gate, the light crowd flees (2026-09-22, forty-eighth session)

- **Two lot slabs never share plan area** (`island_buildings.separate_lots`, run by `derive` after `grow_lots`, and on
  its own as `island_buildings.py lots [--check]`, no terrain dump). `grow_lots` claims whole 1 m cells by their
  CENTRES, so two lots never claim one cell, but a rectangle's continuous edge runs up to a cell past the last centre
  it covers: neighbours grown toward each other shared a strip up to 0.9 m wide along their whole side. Measured
  **1453 overlapping pairs, 5 995 m2, 1421 of them coplanar** (z-fighting). The pass trims, per pair, the one side
  of either lot that clears it with the least cut, never into the building's own footprint (its type AABB).
  After: 0 pairs (checked independently with shapely), 1137 lots trimmed (median 0.25 m, max 1.0), no building moved.
  The ground under a trimmed strip is the block ground at footway level, 6 cm below the slab, already paved.
- **An arterial has a grade gate** (`island_layout.arterial_grades`, asserted by `island_layout.py` and by its new
  `--check`, which runs the asserts on the committed output without deriving). An arterial is pure drape, so a
  terrain edit could tilt one silently (v16's junction on a 42 % slope). `ARTERIAL_GRADE` 6 % over at least
  `ARTERIAL_SPAN` 20 m, on every road of the arterials INPUT (its `__n` zone splits included). Measured: 127
  arterial roads, steepest 2.4 % (`chuo_dori`). The gate's `pad_grade` WARNs on pads with an arterial mouth are
  printed beside it, not asserted (a pad slope is a stop-line placement): today 3, worst 19.9 % where the touge's
  east foot meets `nishi_dori__6` (its mouth 2.26 m above the arterial's).
- **The light crowd REACTS, with no promotion** (`world.PedCrowd`, PLAN.md 3.32): a light ped that hears a GUNSHOT or
  EXPLOSION within `panicRange` 120 m (capped by the stimulus's own radius), or that a player in combat is aiming at
  (within `aimedAtRadius` 2 m of that player's aim marker -- beyond the promote ring that means a scope), runs AWAY
  along its footway at `fleeSpeed` 4.5 m/s on `upright_sprint_forward` for `panicSeconds` 8 s, then walks again.
  Stimuli are read once per frame (each newer than the last seen), so the cost is one list walk plus a distance per
  ped. `reactions` off is the control. `StimulusManager.postNoise(type, origin, radius)` is the registered form of
  `post` for probes. Gate **`tools/godot/probe_ped_panic.gd`** 7/7 (bare stand: 5 peds 20-40 m from a shot run away
  at 4.50 m/s, 5 at 200 m keep walking at 1.40, all walk again after the panic); `--control` fails the flee case.
  Not gated: the aimed-at half (it needs a Player's aim marker in a scope).
- `probe_ped_crowd.gd`'s "the crowd added nothing to the characters group" had been failing on World.tscn since the
  traffic ring (3.32) streams 9 cars and their drivers round the stand; it now counts bodies on foot only.

## One row of street-facing buildings a side, tight blocks, weapons in every konbini (user, 2026-09-26)

- **A block holds ONE row per street side, every building facing its street** (user: "no several rows within a
  block ... all building should face street, not face another building"). Every `island_buildings.REGIONS` row
  count is 1. The block's middle is the back lane (`through_lanes`, 4 m, the fire / delivery access) and the 路地
  (`PASSAGE_*`) reach it from the street. A back-row building would need 接道 (`BACK_ACCESS`: a 路地, lane or street
  within 3 m -- the 旗竿地 strip); the rule stays in `try_place(back_row=)` for the day a region asks for rows again.
- **Tight blocks instead of deep ones** (`island_plan.STREET_REGIONS`): city / suburb / koba 64 m
  deep, the housing 44 m, so two frontage rows plus the back lane fill a block. **Open:** the band between C1's north
  side and `nishi_dori` (record y ~570-760, x 280-990) has no block streets and the grid planner cannot make any --
  C1 is elevated, so a line there meets only one ground road (measured: every line "meets one road"); it needs
  authored streets (a trunk-grid style line). A lot grows up to `LOT_GROW_MAX` 20 m
  back, so the building's own yard reaches the lane. A few large blocks remain for warehouses (industry 200 m,
  logistics 220 m), which one building may take whole.
- **Gaps**: outside the 防火地域 core a building keeps ~1 m to its neighbour (`REGION_ALLEY` 0.5 per side in city /
  west_centre; housing 0.6-0.8); the core (downtown, nightlife, west_ekimae) stays 0.2-0.25.
- **Anchored buildings front a street**: `apply_anchors` takes only a frontage-row slot (key row 0, not a car park).
  The `armoury` role is only how the safe house finds its street: the nearest `KonbiniL` to the centre
  (`ARMOURY_REACH` 1200 m, resolved first); the safe house is the nearest street-front ShopHouse to it that has a
  plain neighbour wide enough to become its OWN car park (`HOME_PARK` = ParkingLot4, role `home_park`; a second
  `anchors` run keeps it), and the starting car stands in a bay there, nose in. If none, the nearest ParkingLot8,
  then the mouth of the nearest 路地.
- **Every konbini sells weapons, free for now** (`KONBINI_PADS`): a KonbiniL the whole catalog (3 x 4 grid between
  its gondolas and the counter), a KonbiniS pistols + SMG + knife + grenade. There is NO separate weapon counter
  (user, 2026-09-26): every store's pads are in its streamed building cell (`Pads_NNN`), the one beside the safe
  house included, and the map lists it as a Convenience Store. `WeaponPad` fades out past `drawDistance` (40 m),
  turns its model only while on screen, and times its cooldown on the engine clock (a `_process` accumulator
  stopped with the processing and the pad never re-armed).
- **Doors**: only a shop's STREET entrance slides (`slide_sides`, default front); back / side exits are hinged, and a
  `Wall_PartitionDoor` prop with a `door` entry gets a hinged, automatic, never-locked interior leaf (`inner_doors`;
  the konbini staff room and toilets). How-to: `assets/world_source/buildings/README.md` "Doors".
- **Map blips**: `RoadOverlay.worthABlip` is the one rule for both maps -- another player, anyone hostile to the local
  player, and a car driven by either. Neutral pedestrians and ambient traffic get none (GTA). The full map draws the
  player as the minimap's heading triangle (`RoadOverlay.drawHeading`).
- **The full map prints no place names** (`WorldMapManager.showPlaceNames`, off): the typed squares and the legend
  key say what each place is. The minimap is unchanged.

## Shop counters are in the shop's model; a car runs a person over; car-park entrances stay clear (2026-10-04)

- **A shop's counter and clerk are `MARK_` Empties in its own .blend** (PLAN.md W3/W7): `MARK_shop_counter_<n>`
  (props `stock`, `title`, `w`/`d`/`h` = the sensor box; the marker at the box's floor centre, its X along the counter)
  and `MARK_clerk_<n>` (props `surrender`, `weapons`, `till`, `responders`; -Z = facing). `build_building_scenes.gd`
  turns them into `item.ShopCounter` / `world.ShopClerkSpot`, **only in a `_Shop`/`_Open` variant** (a clerk is an AI
  body; nobody can reach one in a shut building), and takes the kind from the NAME when the `kind` property is
  missing. Seeds: `tools/building_kit/shop_interiors.py` `MARKS` (konbini S/L, family restaurant, supermarket;
  `build_shop_blends.py` ADDS a missing mark even to a hand-edited, KEPT piece and never moves one) and
  `interior_plans*.py` `b.mark("shop_counter"|"clerk", ...)` (hospital pharmacy, izakaya, the adult shop as gang_a's
  gray-area front; `build_interior_blends.py` adds them to a kept piece the same way). The floor `WeaponPad`s,
  `KONBINI_PADS`, the cells' `Pads_NNN` and DebugWorld's `KonbiniPads` are DELETED. A DEEP-pocket building of a type
  `CIVIC_SCENE` opens (a supermarket, a 立体駐車場) now stands as that open variant too (`island_buildings.scene_of`).
  Gates: `probe_weapon_counter.gd` (island 13 checks, `--world=debug` 9; it counts its checks so an aborted coroutine
  cannot print PASS), `probe_shop_clerk`, `probe_wanted_respawn`, `probe_underground` (each with `--control`).
- **A car hitting a person** (user-reported: "the character is like a wall; the car takes damage, the person none").
  A character is a kinematic body, infinite mass to the solver: measured 14.7 -> 1.8 m/s, 75 HP of crash damage to
  the car, 0 to the person -- and the contact damage read the speed AFTER the solver stopped the car. `Vehicle
  .sweepPeople` (the pole sweep's shape, before the step, simulating peer only): anyone the car reaches this step at
  >= `vehicleCollisionMinSpeed` takes the hit damage and the throw; one it kills is excepted from the car's collision
  for 1.5 s, so the car drives on (keeps 1300/(1300+80) of its speed); a living one (a slow nudge) is met by physics.
  A PLAYER's car also promotes the light crowd peds 0.5 s ahead (`PedCrowd.promoteNear`) so they are bodies to hit.
  `knockPeople` (`@Visible`) is the control. Gate `tools/godot/probe_car_hits_ped.gd` (bare stand; 15 and 8 m/s
  PASS; `--control` fails 3).
- **Car-park entrances keep clear of street furniture** (user: "a tree in front of a parking exit"; measured 17 trees,
  25 lamps, 17 planters and 3 bollards in 70 of 158 entrances). `island_buildings.py write` writes
  `pieces/IslandRoads.keepout.json` (every `Parking*` lot's front, every `drive`'s mouth at the kerb), `roadkit_cli
  pieces|gltf --keep-out` reads it, `point_furniture.Furniture.blocked` refuses any standing prop inside (signals, signs,
  drains and manholes excepted), and each road piece's digest includes the boxes near it. The boxes come from the
  PREVIOUS buildings derive (roads are built before buildings): after a layout change run the road build once more.
- **Crowd density: the city reads busier than the port** (user). Measured in play (`tools/godot/probe_crowd_by_region.gd`)
  the city was already denser (130 people within 150 m in the nightlife quarter, 7 at the harbour), but a city
  street is boxed in by buildings while an open quay shows its few people across hundreds of metres, so
  `PED_DENSITY` widens the contrast (city districts ~+50 %, working districts halved).
- **Dynamic content exists only near a player** (measured on the ground with `probe_walk_perf.gd`, downtown / station
  p50): a shop's CLERK (`ShopClerkSpot`, spawned within 60 m, returned past 100 m while calm; one that surrendered,
  fought or died is `spent` while the shop stays loaded) took 47 -> 19 / 49 -> 26 ms -- every open shop in range had
  spawned a full AI body at load; a PARKED VEHICLE (`ParkedVehicle`, spawned within 150 m, returned past 230 m while
  untouched: nobody in it, within 1.5 m of its spot, undamaged) took another 4.2 / 6.6 ms off (74 in range). A world
  with no registered player (a bare stand) spawns both at once. End state: 14 / 18 ms p50, p95 24 / 27 (over 16.7;
  next lever the <= 12 promoted crowd bodies). `--no-parked` is the probe's control for the vehicles. The same rule for
  any future dynamic content of a building: geometry streams with the cell (and draws through HLOD / visibility
  ranges), bodies and vehicles spawn on proximity, and a mission that needs them earlier calls the spawn itself.
- **A deep-pocket lot faces SQUARE to its street** (user: "some parking lots are at a slope angle, aligned to neither
  street nor neighbours"): `deep_fill` took the facing from the direction to the nearest footway sample, oblique near a
  corner or a bend; it now takes the street's normal there (the frontage line's own tangent) and measures the
  driveway square to it. Lands at the next buildings derive (needs `--from terrain`).
- **Perf and crowd probes stand ON the ground**: `probe_walk_perf.gd`'s legs had heights typed before the land raise
  (y 1.65 on a 5.6 m plain): the player walked UNDER the terrain. Each placement now takes the walkable surface under
  it (a downward ray bounded by `WorldBounds.terrain_height`; an elevated leg takes the deck) and the run FAILS if any
  frame has the player under the terrain. `probe_city_perf.gd` and `probe_ped_crowd.gd` ground the same way.

## Shop interiors are a kit of .blend files, one per store (2026-09-27, user-asked)

The konbini (small, large) and the family restaurant were re-planned from the user's sketches and moved to the
station's Blender -> Godot shape so an artist can adjust them. `assets/world_source/kits/shops/` (`ARTIST_NOTES.md`)
holds `Shop_<Id>.blend`, each ONE piece `<Id>_Interior`: every fitting a separate object (a copy of the library mesh),
`COL_` Empties the colliders, `DOOR_` Empties the interior doors (arrow OUT of the room; `w`, `h`, `style` swing |
slide, `slide_dir` +1/-1 = right/left seen from the arrow's side), and a `Reference (not exported)` collection drawing
the shell's walls. The shell (outer walls, shopfront, roof, street entrance, outer doors) is still the downtown kit laid
by `building_types.json`; the type's props are the fascia plus `{"piece": "shops:<Id>_Interior", "collide": "piece"}`.
- **Seed**: `tools/building_kit/shop_interiors.py` (the plans as library props) -> `blender/tools/build_shop_blends.py`
  lays them out ONCE; a regenerate keeps a hand-edited piece (`sh_generated` fingerprint; `--force=<Id>_Interior`).
- **Export**: `export_building_kit.py` gained `DOOR_` -> `doors`; `build_buildings.sh` now exports a kit's `blends`
  list too (the station kit opts out with `own_build`: it has build_stations.sh). `place_props`' `collide: "piece"`
  takes the piece's own boxes/hulls, and a piece's `doors` become `inner_doors`.
- **Doors**: store/staff rooms and offices are hinged; every restroom has a SOLID SLIDING leaf
  (`build_building_scenes.gd`: an inner door with `style: slide` is one opaque leaf hung 0.11 m proud of the wall on
  its outward face, running `slide_dir` along the wall). `layout_buildings.check_inner_doors_clear` refuses a store
  whose interior door has something within 1.1 m on either side, or on a sliding leaf's run.
- **Plans**: every store has at least one ACCESSIBLE restroom (1.0 m `Wall_PartitionDoorWide`, toilet, `WC_GrabRail`,
  basin + mirror, `WC_BabyTable`). Small konbini: one (customers + staff); large: two (customer back-left, staff in the
  back-of-house row off a closed staff aisle behind the counter), plus a store room with a delivery door behind the
  walk-in's fulfilment corridor; restaurant: kitchen across the back (`Kitchen_Fridge/Sink/PrepTable/Fryer`, grills),
  `Wall_PassWindow` over the service counter, store/staff/staff-WC column, customer accessible/women/men block.
  New library placeholders in `library_procedural.py`: those above plus `Wall_PartitionHalf`.
- **Second round (2026-09-28, from a review of the user's hand edits, which were folded into the seed and then
  regenerated with `--force`):** the cooler is a ROOM (drink doors = its front wall,
  `Shop_FridgeDoor` has no back panel now), `Shop_OpenCase` (bento, no door), `Shop_FreezerCase` (replaces the ice
  freezer), `Shop_CigaretteCase`, `Shop_CoffeeStation` (2 machines), `Shop_BinStation` (3 sorted bins),
  `Shop_EatInCounter` (wall-mounted, one seat per 0.91 m unit) + `Shop_Stool`; staff exit only through the staff
  aisle (KonbiniS back [0], KonbiniL back [2]; the aisle behind a hinged door); vending machines OUTSIDE (2 small,
  3 large); the restaurant has TWO accessible customer restrooms + bins, ticket machines and an ATM. A type records
  `forecourt_m` (props past the front wall) and probe_buildings lets the mesh be that much deeper. The generator
  reloads library meshes on a regenerate and folds `MI_x.001` material copies; the scene builder also strips `.NNN`.
- **Third round (2026-09-28):** `WC_Toilet` is a code-built Japanese WASHLET (rounded one-piece bowl, tank/washlet
  housing, seat + lid, control panel on the right of the seat; 0.75 m deep, so every toilet sits 0.385 m off its wall)
  and `WC_Basin` a plain square wall-hung basin; both left `extract.json` (one owner). The large konbini's staff aisle
  now runs the whole staff block to z 0 with its hinged door there, the staff restroom opens INTO it, and the counter
  moved forward with two registers.
- Weapon pads (`island_buildings.KONBINI_PADS`) moved onto free sales floor. Gates: `probe_buildings.gd` (an interior
  door may be `inner_slide`, asserted by movement) 310/310 on the three types; `probe_weapon_counter.gd` PASS.

## Civic plots and placeholder public buildings (2026-09-28, user-asked)

**Ground is held BEFORE the streets are planned** (user: "leave enough space for fire / police stations, hospital,
clinics, a water resort, the fish market ... so later updates need less rebuild"). `tools/island_civic_sites.py`
searches once and FREEZES 33 plots into `assets/world_source/buildings/IslandCivicSites.json` (the IslandSites rule:
an ordinary run never moves one; `--resite[=id]` searches again; `--check` asserts every plot still fronts a road and
has no road through it, and runs in `island_world.sh`'s layout stage). A plot fronts a road that exists before the
street planner (arterial, trunk, ring, dike side road -- never a generated block street, an expressway, the touge or
the cliff road), at grade, `FRONT_GAP` 1.5 m past its paved edge, flat within 1.5 m, clear of every other road's paved
edge (4 m, exact segment distance -- `IS.road_index` is a square box test), the rail corridor and stations, the frozen
sites, `island_plan.RESERVES`, the dike and other plots; the nearest to its target wins. `island_streets._sites` treats
a plot as a site (SITE_CLEAR 10 m); `island_buildings.civic_plots` blocks it and places the plot's BUILDING on it
(`CIVIC_TYPES`, facing its road), which is then a map place even though it is shut (`CIVIC_LABELS`); `island_ground`
paves it like a lot. Sizes (PLATEAU p50, 7 central wards): 警察署 30 x 45 m / 7 st; 交番 5 x 7 / 2; 消防署 23 x 42 / 5;
出張所 15 x 23 / 3; 総合病院 52 x 83 / 8; 小学校 46 x 80 / 4 (18 m); 区役所 48 x 85 / 14; 寺 24 x 32 / 16 m.

**A street could run through a site** (found on the first run): `_line_ok` checks a line against sites only between
its crossings with EXISTING roads, and a crossing with another NEW street could then extend it past that span. Such a
crossing is refused now when the extension runs through a site (`plan_region`, where `cross` is built) -- for every
site, not only the plots.

**The placeholders** are `blender/tools/library_civic.py` (Builder massings in `library.blend`, flat palette
materials; `kits/library/ARTIST_NOTES.md` "Civic placeholders" is the replace-by-hand list, and each piece carries its
`edit_note`): Civic_PoliceStation / Koban / FireStation (red bay shutters, 訓練塔) / FireBranch / PostOffice(Small) /
WardOffice / Hospital (podium + ward tower + helipad + 救急) / HospitalSmall / Clinic / SchoolElementary /
SchoolJuniorHigh (校舎, 体育館, pool, 校庭, fence), Shrine, Temple, Park (+ nature-kit trees), WaterResort,
ResortHotel, FishMarket; the air base (Mil_HQ, Mil_Barracks, Mil_Hangar, Mil_ControlTower, Mil_FighterJet, Mil_Fence,
Mil_Gate); airside (Airport_Hangar, Airport_Airliner, Airport_Taxiway, Airport_Apron); signage (Sign_AkibaVertical,
Sign_AkibaBillboard, Sign_Sodekanban, Sign_ShopVertical, Prop_Chochin, Prop_Noren); the 一戸建て (House_Detached, _B).
A civic piece's origin is its PLOT centre (`plot_origin` on the custom row keeps it; a custom is otherwise re-centred on
its bounds). Types: the civic `custom` rows; composites `MilitaryBase` (320 x 300: gate north, apron + hangars with jets
south), `MilitaryAirfield` (1 200 m runway + taxiway + a link to the base), `AirportAirside` (540 m runway, taxiway,
apron with three airliners, a hangar holding a fourth); kit types `AkibaElectric` (glass front, two 袖看板 stacks,
rooftop billboard) and `YokochoRow` (2-module izakaya: 赤提灯, 暖簾, sign); `PencilBuilding` now wears a 袖看板;
`DetachedHouse(B)`. Reserves become streamed sites through `island_sites.RESERVE_SITES`.
- **The military base is COMPACT** (user, 2026-09-28: "so the player does not need to wander around, but every
  component for missions"; one runway + one pier is the standard for a small base -- a finger pier berths a ship each
  side, one runway serves a squadron). Land stage: the 1 210 m reclaimed runway strip off the south-west coast and the
  second pier are GONE (`island_reshape.MILITARY_PIERS` is one pier). `MilitaryBase` (reserve x -760..-475, z
  1250..1480, yaw 90: the gate faces the gate road `kichi_mon_michi` at x -460) holds the gate, HQ, barracks, parade
  ground, motor pool + trucks, fuel depot, armoury bunker, helipad, control tower, one hangar (two jets) and an apron
  row (two jets) on its south side; `MilitaryAirfield` is a ~780 m runway on the platform's own south band
  (z 1480..1535) abutting that apron; `MilitaryPier` (reserve centred on z 1336, yaw 270) is the terminal, bollards,
  masts and a berthed Mil_PatrolShip (its waterline 9.6 m under the deck). The west fence has a gap onto the pier;
  everything is within ~300 m. The military reserves are street SITES too (`island_streets._sites`).
  `ground_box` may be a rectangle `[x0, z0, x1, z1]` (the pier's deck, not the water where the ship lies).
- **The container terminal already fronts the bay**: its quay (+X) drops straight to the -24 m seabed with open water
  > 700 m out, so it needs no harbour of its own. Two things it lacks: a ship at berth, and a believable quay height
  (the quay top is 9.6 m above the water, the land stage's raised plain; a real one stands ~3-5 m).
- A plot re-sited AFTER the streets were planned uses `island_civic_sites.py --resite=<id> --avoid-streets` (it keeps
  off the finished block streets too, so no layout pass is needed); the water resort was re-sited that way when the
  dike side road it fronted moved.
- **New layout rules**: a type prop may be `"y": "roof"`, and `front` / `right: d` / `left: d` place it against the
  type's (or its variant's) own size; `"facade": true` marks street dressing (it does not make the building "have an
  interior", and it counts toward the forecourt depth); a custom or composite may state `height_m`; a composite may ask
  for `ground_box` (the paved ground's collider without an apron).
- **A lot never GROWS into held ground** (found by `lots --check` after the civic plots): `grow_lots` stopped only at
  roads, passages and other lots, so a neighbour's lot grew into civic plots, sites and reserves. `Field.block_box(...,
  hold=True)` also marks the cells owner -1 (nobody's lot), for sites, reserves and civic plots.
- `probe_station_paid.gd`'s island mode freezes the WHOLE player (`process_mode` DISABLED): MovementController is its
  own node and kept moving the teleported body, which fell through unstreamed ground and died, and every station after
  that never streamed. 13/13 on the island since.
- **A building's fade distance covers its own plan** (`build_building_scenes.gd`: at least half its diagonal past the
  minimum): a 1.2 km runway faded out by height while you stood on its end.
- New palette materials: MI_Window (opaque dark glazing for closed placeholders), MI_Dirt, MI_PoolWater, MI_Grass,
  MI_JetGrey, MI_Olive, MI_TileBeige, MI_TileBrown, MI_PostRed, MI_NorenNavy, MI_Sign{Red,Green,Yellow,Pink,Cyan}.

## Sliding doors: one leaf for a restroom, a sensor that stays on the doorway, and a probe that stands in front (2026-09-28)

User-reported on the station's accessible restroom: "keeps trying to open but immediately slides back", "the sliding
logic seems wrong (should be one door)", "should be a white block like the restroom wall". Three defects, all in
`build_building_scenes.gd`:
- **A 1.2 m interior slide was split into TWO leaves** (`_panels` split any slide >= 1.2 m). With the mirrored hand's
  `slide_dir` -1 both leaves slid ACROSS each other and the doorway stayed shut. An interior solid slide (`style:
  slide`, inner) is one leaf now, and `slide_dir` only steers a SINGLE leaf (a pair always parts from the middle).
- **A sliding leaf carried its own sensor**, so a long leaf slid the sensor off the person who opened it, shut, came
  back and found them again: the chatter. A slide's sensor is a sibling on the DOORWAY (`Doors/Sensor<n>`,
  `sensor_path = ../Sensor<n>`): the ticket gate's rule.
- The interior solid leaf wears the restroom wall's `MI_Plaster` (`_plaster_material`).
Gates: **`tools/godot/probe_slide_doors.gd`** stands a real AICharacter 0.8 m in front of every automatic sliding door
and asserts it opens its full slide within 1.5 s and STAYS open for 1 s (all stations, both konbini). A disabled
CollisionObject leaves the physics space, so the probe body keeps `disable_mode = KEEP_ACTIVE`. `probe_buildings.gd`
now also probes a station's doors (it stopped at the station's missing `wall_top_m`, so no station door had ever been
driven), classifies `slide_glass` as sliding, and asserts every interior sliding doorway takes the capsule once open.
A station's declared footprint is its reserve, so the size rule is skipped for it (the 39 "size" failures).

## The logistics hub, resort hotels in the suburb loop, and five gate findings fixed (2026-09-28)

User: "fill the empty middle with a logistics park ... restrict to 1, or 2 if it makes sense, for level design ...
compact, not repeated, but have all industry / military / other services".
- **ONE logistics hub** on the port platform's middle (`island_plan.RESERVES` `logistics_*`, street sites): a
  トラックターミナル west of `butsuryu_michi` (x -445..-295, composite `LogisticsTruckTerminal` 225 x 150, yaw 90) and a
  物流センター east of it (x -265..-25, `LogisticsDistributionCentre` 225 x 240, yaw 270), both gated onto that road,
  south of the port road, beside the container terminal. Pieces `Logi_*` in `library_civic.py` (cross-dock shed with
  docks both sides, DC with 16 docks, box truck, tractor-trailer, gate house, fence bay, yard slabs); the two big
  buildings collide by explicit boxes (their bounds would wall off the dock bays). Generic `Warehouse` is now a
  MINORITY in every district mix (the harbour region places port offices, a konbini and lorry parks instead).
- **Resort hotels**: three `ResortHotel` sites INSIDE the suburb loop (`kogai_loop`), fronting its bottom leg (they
  had been laid across that leg and across the Main line). Resort and logistics reserves are street sites.
- **A station stands on a straight**: `island_rail_layout`'s check reports a station whose platform + 15 m
  (`STATION_STRAIGHT_PAD`, the kit building's overhang) bows > 5 cm; Castle Town moved -560 -> -540 (its wall stood
  in the Blue line's curve gauge). `ACCEPT_CURVES` names Central on the Main line (its pad only).
- **Streets keep off station boxes**: the farm frame's station-front leg moved x 1080 -> 1045
  (`island_core_streets`), and the dike side road skips a station box or car park (+7 m, `island_dike._in_station`).
- **Two mouths' caps may not overlap** (`check_mouth_sides`): a minor mouth whose cap (paved half, footway included)
  touches another mouth's moves out; a road that changes its NAME through a pad (ring_kita -> kaigan_dori) now counts
  as a through road (two free mouths leaving it within 35 deg of head-on). The one finding was rinkai_dori's mouth
  inside the ring's cap.
- **`probe_road_ground` judges a column foot by the build's founding rule** (lowest ground within
  `point_mesh.FOOT_REACH` 1.5 m): a Wangan column at a vertical quay face stands on the seabed at the wall's toe.
- **Plinths never overlap** (`island_buildings.fit_plinths`): the plinth is what renders since the lot slab went; each
  overlapping pair shrinks the margins of the sides facing each other (a per-building `plinth` in the record), a
  corner clash of two frontage rows drops the smaller building, and the safe house's car park slides along the row to
  clear the house. `lots --check` fails on plinths; lot rectangles are record data (the few rotated pairs no rectangle
  can separate are reported). Civic lots are separated too (the pass runs after they join).
- DebugWorld's road tests follow the redesigned DebugRoads (12 runs, 6 pads, footways, 7 cross-zone successors, no
  open end) and pick the DebugRoads network by record path (DebugWorld also carries `DebugRail`).

## Central's 駅前広場 replaces the Tokyo Station placeholder; one facing per joint; stage timings (2026-09-28)

- **The Tokyo Station placeholder is RETIRED** (user): Central is the rail kit's elevated hub, and the old site stood a
  second station building in front of it. Gone: the `tokyo_station` frozen site and its search
  (`island_sites.station_site`), the `TokyoStation` custom type and its three scenes, the map label (Central's own
  station scene is "Central Station"). The library model `TokyoStation` stays in `library.blend`, unplaced.
- **The forecourt is a Road Kit loop plus a composite.** `ekimae_rotary` (`island_core_streets.STREETS`, now with
  `one_way` / `lanes` / `walks` / `spacing` keys): ONE-WAY, 2 lanes, clockwise (Japan keeps left), in from ekimae_dori at
  x 690, along y 150 in front of the station, out at x 880; a one-way road lays its lanes LEFT of its stations, so the
  stations are the loop's inner edge and the 4 m outer footway is the kerb buses and taxis stop at. The ground between
  ekimae_dori and the station is the `central_forecourt` RESERVE (`island_plan.RESERVES`): a street site, a LEVELLED
  site (`island_sites.LEVELLED_RESERVES`: level = the rotary's highest station + 0.15, so `island_ground` fills it to
  footway height like a lot, never over the road cells), and it carries `CentralForecourt`
  (`tools/building_kit/site_central_forecourt.py`, DERIVED from the reserve and the rotary's corners; `--check` runs in
  the layout stage): four bus berths with shelters + signs on the station-side kerb under a covered walk, the taxi rank
  on the east leg, a 立体駐車場 in the west zone with its mouth on the west leg (a left turn in), the 交番 and two 駐輪場
  in the east zone, the clock and benches on the plaza, trees on the inner island. Every prop is refused if it touches
  the rotary's paved bands. A composite `reserve: true` skips probe_buildings' size rule (its footprint is ground it
  dresses, not a slab). New library placeholders (`library_civic.py`): `Parking_Multistorey`, `Plaza_Clock`,
  `Plaza_BikeRack`, `Taxi_Sign`, `Plaza_Canopy`. Central's `multistorey` rail car-park box is gone (it stood on
  yamate_dori and nothing was placed in it). Map: "Central Bus Terminal".
- **A joint's two stations share ONE FACING** (`island_layout.weld_joints`, run last): two AUTO halves meeting at a bend
  cut their sections on different planes and hand each lane over sideways. Both are frozen on the bisector of their
  chords, each facing its own road's forward direction; a joint a generator already froze is left alone. It took every
  cross-road hand-over under 0.25 m, including the old `kaigan_machi -> ring_kita` 3.42 m.
- **The dike's side roads detour round a station box** (`island_dike.round_stations`: a run that enters a station or
  car-park box, grown 7 m, is shifted 3 m past its nearest edge with a 40 m cosine ease), instead of the whole piece
  being dropped -- which had cost 9 civic plots their frontage.
- **Stand probe (`probe_station_paid.gd`)**: the stand's ground is TILTED between an open-air station's entrances'
  street heights (a flat stand read the slope as a step), the flood's bound includes every collision shape, and a
  surface ray that grazes a cell edge asks a second ray 3 cm over.
- **A road corridor is centred on its BAND, not its spine** (`point_edges.band_corridors`): half = half the distance
  between the two paved edges, centre = their midpoint. A one-way road's spine is its inner EDGE, so the old
  `max(left, right)` about the spine claimed a carriageway's width of ground on the side with none -- the stamp, the
  building placer and the block fill (`island_ground.road_mask`) all saw the rotary 9 m wider inside, and the island
  kept an unfilled grass strip. Two-way roads are unchanged (their midpoint is the spine).
- **The castle's approach ends WEST of Castle Town station** (`island_site_access` jokamachi_sando end (-628, -208)):
  the station moved east and its car park (placed at the approach's end) stood on the station's front, the approach's
  lane in its entrance (probe_road_clear).
- **Where a rebuild's time goes** (island_world.sh prints each stage's seconds, island_rebuild.sh each step's,
  island_layout each generator's): `--from layout` 60 min = layout 24 min + roads 31 min (16 rail + 40 road pieces
  baked) + sites 4 + buildings 0.5 + ground 0.6. A layout run re-derives the whole island, so every road zone's
  digest changes and `DIRTY_ONLY` skips nothing.
- **What skips now (2026-09-28, user: "build only the affected region")** -- four of the five measured proposals:
  * **Cross-network context in the piece digest** (`point_digest.context_of`, `CONTEXT_REACH` 40 m): a piece's digest
    also hashes the FOREIGN bands (`--avoid`) and keep-clear lanes (`--keep-clear-lanekits`) within reach of its own
    box, added only when there are any, so a piece nothing foreign touches keeps its old digest. `roadkit_cli.py
    pieces` takes those flags (`build_roads_piece.sh` passes `GLTF_EXTRA`), so the RAIL build is `DIRTY_ONLY=1` in
    `island_rebuild.sh` too, and a road piece no longer needs a full rebuild after a rail change. Self-test: a foreign
    band / keep-clear lane dirties only the piece it touches, and moving it re-dirties.
  * **Stations skip when unchanged** (`tools/building_kit/station_digest.py`, manifest
    `assets/world_source/kits/stations/build.json` -- commit with the scenes): per station, its layout entry + a salt
    of the station kit, the library, the scene builder, the layout, the probe and the door/gate/lift classes. Only
    dirty stations are built and stand-probed, and only a stand PASS is recorded; `FORCE=1` does all. 4m21 -> 39 s.
  * **`island_layout.py` caches each generator step** (`tools/layout_cache.py`, `$XDG_CACHE_HOME/openworld_island_layout`,
    last 400; `--no-cache` / `LAYOUT_CACHE=0`): key = the argv with every input file's bytes, the step's Python import
    closure, the `DATA` files and the `VOLATILE` state; a hit replays the output and stdout. Editing `island_streets.py`
    re-runs streets onward only. Also: `tidy` ran the WHOLE gate for one finding (291 s); it runs
    `check_mouth_clearance` alone now (0.1 s). Derive 347 s -> 58 s cold, 2 s warm (verified identical modulo point
    uids, which are random per run); the checks after it (~190 s: flow 99, validate 50) still run on a changed output.
  * **Incremental stamp** (`road_kit_stamp.dirty_corridors`): a re-stamp re-derives only vertices reachable from
    corridors that changed (old and new), when the stamp record's rule md5 / clearance / verge match; else full
    (`stamp_roadkit_terrain.gd --full`). Verified: a station raised 1 m re-stamps 312 vertices, 0 different from a
    full stamp.
  * Not built: `--region` for `island_streets` -- it runs in ~1 s, so a region option buys nothing.
  * **The first build after this rebuilds every road and rail piece once** (the builder salt includes
    `point_digest.py` and `roadkit_cli.py`).

## Mission buildings with interiors, parked vehicles, flyable/sailable craft, and the offshore military runway (2026-09-28/29, user-asked)

**`assets/world_source/kits/interiors/`** holds one `.blend` per mission building, each ONE piece `<Id>` (shell, floors,
stairs, lift shafts, rooms, fittings) at its real Japanese size: `Koban` (1 storey, light arms), `PoliceStation` (2,
the complete armoury, cells, interrogation), `FireBranch` (1) / `FireStation` (2), `Hospital` (3 + helipad, ER, ORs,
wards), `OfficeHQ` (4, open offices, server room, strong room), `ResortHotel`, `WarehouseYard`; the military base's
`MilHQ`, `MilBarracks`, `MilArmoury` (the complete military armoury), `MilHangar` (two FIJ1), `MilControlTower` (cab at
20 m); `AirportTerminal` (F1 arrivals, F2 departures, security, four gates on boarding bridges), `AirportHangar` (one
airliner + a LIP1); `CargoShip` (a static walkable feeder, origin on the waterline, not placed). Plus shops
(`kits/shops/Shop_Supermarket.blend` + `SupermarketSite`, the re-planned `Shop_FamilyRestaurant.blend`).
- **Seed**: `blender/tools/interior_plans.py` (plans in a small DSL, `interior_kit.py`: slab / wall / door / ustair /
  lift / mark) -> `blender/tools/build_interior_blends.py` lays each out ONCE; a hand-edited piece is KEPT
  (`ib_generated` fingerprint, `--force=<Id>`). The generator refuses a plan with a fitting within 1.1 m of a door.
- **Empties the game reads** (`export_building_kit.py`): `DOOR_` interior doors, `EXIT_` outer doors, `LIFT_` a lift
  (`stops` "0,4.2,8", `faces`), `MARK_<kind>_` mission markers (weapon / spawn / cover / objective / vehicle ->
  `Markers` node, group `mission_marker`), `COL_`, `PROP_`. A new piece needs `ACCEPT_BOUNDS=1` on its first export.
- **Rows**: `building_types.json` `custom` rows (kit `interiors`); a composite may take a custom row as a PART (its
  trimesh goes into the site's collider, `trimesh_idx`); the MilitaryBase / AirportAirside library blocks were replaced
  this way. Artist list: `kits/interiors/ARTIST_NOTES.md`.
- **Multi-stop lifts**: `world.Elevator` takes `stopHeights` / `faces`; `ElevatorRules` sweeps (a boarded rider goes on
  in the car's direction). Gate `probe_building_lift.gd`.
- **Parked vehicles**: a `MARK_vehicle` (or a composite `{"vehicle": id, "faction"}` prop) becomes a
  `world.ParkedVehicle`: host-only, spawns ONE drivable vehicle from `VehicleModels.sceneOfId` into the current scene
  (not the streamed building), remembered by position so a cell streaming back in spawns no second one. New models
  AMB1 (ambulance), FIE1 (pumper), LAT1 (ladder) (`make_placeholder_cars.py`), index 12-14. Gate
  `probe_parked_vehicles.gd`.
- **Craft**: FIJ1 fighter, LIP1 light plane, WOB1 work boat, FIB1 fishing boat (`blender/tools/make_placeholder_craft.py`
  -> `tools/build_craft_scenes.py`, inherited Airplane / Boat scenes, VehicleModels 15-18). Lift is sized so it reaches
  its 1.3 x weight cap just past take-off (FIJ1 60 m/s, ~130 m roll; LIP1 37 m/s). Gate `probe_craft.gd` (a pilot's
  rotation: stick back to ~15 deg nose-up, then neutral -- holding it loops the plane); `--control` fails 4. Placed:
  jets and trucks at the base, a LIP1 in the airport hangar, a WOB1 at the military pier, two FIB1 at the fish market.
- **The military runway is OFFSHORE** (user, 2026-09-29): it had run 820 m along the port platform's south band to the
  container terminal's corner. Now a 540 m runway (the civilian airport's length; FIJ1 needs ~130 m) on a reclaimed
  strip running WEST from the base into the sea (`island_reshape.MILITARY_PIERS`' second rectangle, `island_plan`
  `military_airfield` x -1260..-720). The airport island needs no widening.
- `probe_buildings.gd` now tests a door at its own floor height (`center[1]`), so an upper-floor exit (a gate, a ship's
  deck door) is probed where it is.

## Civic compounds leave room for a truck to drive round them (2026-10-04, user-asked)

User: the fence stood too close to the building for a large truck to pass, and side entrances were blocked by the
neighbouring building. The rule now (the site ring only; every interior is unchanged):
- **A drive lane down each side of the building**, measured from the wall to the fence or site edge: police
  station 10 m, hospital 9.5 m, fire station 9 m (+ 8 m behind, the 訓練塔 behind that lane), fire branch 7 m, warehouse
  yard 9 m (+ 8 m behind, fenced all round), main post office 8 m, branch post office 6 m. A truck lane is 6 m; the rest
  is its turn.
- **Vehicles enter from the FRONT, never through the plot's side**: a neighbour may stand against a plot's side edge.
  The police station's single 5 m side gate became two 10 m gates in the front fence, one at the head of each side
  lane (in left, out right), with the 6 m public gate between them. The warehouse gate is 16 m (was 8), the impound
  lot's and scrapyard's 14 m (were 8).
- **Deeper front and back**: the police car park is one row against the back fence across an 11 m aisle; the fire
  branch has a 10 m apparatus apron (was 2.5); the post offices' van yards are 8 m (branch) and 18 m (main) deep.
- **Plots grew to match** (`island_civic_sites.PLOTS`): police 52 x 50, fire HQ 52 x 56, fire branch 32 x 42, hospital
  (west) 65 x 65, main post office 54 x 64, branch 25 x 28, warehouse yard 60 x 66; re-sited with `--resite=<ids>
  --avoid-streets`. **`--check` now also compares a plot with an INTERIORS building** (`piece_extents` read only the
  library before, which is how a 34.6 m police fence sat on a 35 m plot unnoticed). It found four plots already smaller
  than their buildings (both multi-storey car parks, the civic centre, the onsen ryokan), now sized.

## More enterable buildings, Japanese convention (2026-09-29, user-asked)

`blender/tools/interior_plans_jp.py` (seed plans; `build_interior_blends.py` now merges its `PLANS` with
`interior_plans.py`'s) adds 18 kits/interiors buildings, each a `custom` row in `building_types.json` with the usual
three variants (shut / `_Open` locked / `_Shop` open) and `probe_buildings.gd` PASS: `SafeHouseSmall` /
`SafeHouseLarge` (residential houses), `SafeHouseCitySmall` (3-storey 狭小住宅) / `SafeHouseCityLarge` (5-storey
雑居ビル with a penthouse over a front company) for downtown, `Izakaya`, `MaidCafe`, `AdultServices` (non-explicit
風俗ビル), `BankSmall` / `BankLarge` (ATM corner, 風除室, counters, back office, vault), `ParkingGarage` (自走式,
stacked 15 % ramps: up west, down east), `AirportControlTower` (civil, lift to a 36 m cab), `FashionBuilding` /
`DepartmentStore` (one `mall()` generator: escalator atriums, lift banks, 4 stairs, a floor programme),
`CivicCenter` (downtown 区民センター), `OnsenRyokan` (snow, 男湯 / 女湯 + 露天風呂), `SecureMansion` (walled estate,
詰所 checkpoint, panic room). `Hospital` gained a 風除室 main entrance and a separate, signed emergency side
(ambulance lane, 救急搬入口 vestibule, walk-in 救急外来); `PoliceStation` stands in a fenced compound (public gate +
立番 booth, barrier vehicle gate + booth, cameras, the 護送口 to the 留置場). None is placed on the island yet.
- **Japanese conventions baked in:** a house's raised 0.45 m floor over a 基礎, the genkan doma one step up from the
  street and the 0.30 agarikamachi, 下足箱; the WC its own room apart from the 洗面所 / unit bath; tatami (flush,
  1.2 cm -- a 和室 floor is sunk for it), 押入れ, 床の間; 風除室 at busy entrances; car ramps <= 17 %, bays 2.5 x 5.0.
- **Helpers** (`interior_plans_jp.py`): `zakkyo()` (a narrow multi-tenant core: back stair to the roof, a lift, a
  lobby strip, a WC per floor; `core_y()` gives the side fire exit's position), `mall()`, `gable()`, `sstair()`
  (a straight flight; tread 0.4 = an escalator placeholder), `ramp()`, `perimeter()` / `fence()`, `guard_post()`,
  `vault()`, `vestibule()`, `genkan()`, `tatami()`. `interior_plans.openings` takes an optional 7th element, the
  doorway's sill above the wall's z (a door onto a raised floor in a wall that starts at the ground).
- **Rules the probe taught** (each a failure first): the character capsule (r 0.35) must fit at the door's own
  floor -- an exit into a raised floor needs its sill, a garage door off a raised hall needs a doma pocket; interior
  doors are >= 0.8 m; nothing (a kitchen run, tatami thicker than 2 cm, a slab edge) may stand within 0.35 m of a
  doorway at floor height; a slab's edge flush with the facade z-fights (slabs stop 2 cm inside); `probe_xz` must be
  a spot whose top-down ray hits the roof at `wall_top_m` and whose floor ray hits 0 -- under a porch or hood for a
  pitched roof.
- **Fast loop:** `tools/building_kit/build_interiors_only.sh <Id> ...` (export those .blends, import, layout, build
  ONLY those scenes, probe ONLY them + their variants; `ACCEPT_BOUNDS=1` for a new piece). `probe_buildings.gd
  --only=` no longer demands 10 scenes, and names a blocked interior sliding door's centre.
  `shot_buildings.gd --plan-z=<m>` sets the plan camera height (the default 3.2 m sits inside a house's F2 slab).
- **Not verified:** a car actually driving the car park's ramps (only the geometry is gated), the escalators as
  moving walkways (they are static steps).
- **Follow-ups (same day):** every bank floor has restrooms -- `wc_block()` (男子 / 女子 / 多目的, sliding doors,
  toilets facing their doors) on each of BankLarge's floors, a customer 多目的トイレ off BankSmall's lobby. **A lift
  beside a stair in every multi-floor public building**: added to FireStation, MilHQ, MilBarracks, MilControlTower
  (in the tower shaft, to the cab) and ParkingGarage (beside the stair tower, a bridge to each deck); houses and the
  izakaya stay stair-only. **Water is a marker, not geometry:** a `MARK_water_` Empty (props `w`, `d`, `material`)
  becomes a non-colliding quad in `build_building_scenes.gd` (`WATER_MATERIALS`: `onsen` ->
  `assets/vfx/water/material/water_onsen.tres`, on `assets/vfx/water/onsen.gdshader` -- the Binbun3D water body with
  no displacement, pale jade, a short depth fade so the stone floor shows); the ryokan's tubs and outdoor pools are
  SUNK (bottom at the ground under a 0.2 m rim, a 0.25 m seat ledge) so a body wades in. **COT1, the container
  truck** (`VehicleModels` index 19, APPEND-ONLY): `make_placeholder_cars.py` shape `tractor` -- a cab-over tractor
  and a 20 ft skeletal chassis made ONE rigid 4-wheel body (wb 7.8 m) carrying the container terminal's own 20 ft ISO
  box (6.058 x 2.438 x 2.591, top 3.79 m); a rigid 40 ft rig would have a 13 m wheelbase and could not turn at a
  junction. `probe_component_car.gd --car=COT1` PASS. Parked (MARK_vehicle / composite `vehicle` props) at the
  WarehouseYard's docks and in the ContainerTerminal's truck lanes. **Nothing may span a lift shaft above the bottom stop** -- a
  thin tatami layer over the ryokan's shaft and the airport tower cab's solid underside each scraped the rider off
  the rising car (`probe_building_lift.gd` read it as "the rider N m off the top stop" while the car's own run
  passed); `slab()`'s holes are not enough, every box laid over a room must miss the shaft too.
- **Findings the island probes surfaced on this rebuild, fixed** (each first seen now: the island had not been
  rebuilt since the previous session's station slides):
  - `probe_station_paid`'s island mode bounded its flood 40 m past the platform ends, and an open-air entry ramp puts
    the street ~48 m out: every open-air station "failed" at a start outside the flood's own box. The bound now reaches
    past every entrance; `--` failures print what blocks the start (`_blockers`) and the floors round it. 13/13.
  - `probe_rail_track`'s gauge is the EMU1's PROFILE in two bands (below the platform line the car is 1.44 m a side,
    above it 1.49 m over the doors), margin 0.001: one box at the door width touched every island platform at Central
    (the real train clears them by 0.11 m). A hit now names its SHAPE and where it stands.
  - The castle approach `jokamachi_sando` ramped straight from its junction to a car park against the castle wall
    and crossed the Blue line 1.5 m ABOVE it (the rail plan read "street closed" while the road was built anyway). It
    now follows the ground (a level 踏切 beside Castle Town station) and ends 10 m past the track with no lot of its
    own; drivers use the station's car park south of the track. `island_site_access.rail_crossings` keeps any access
    road with a lot level over an at-grade track (`LX_HOLD` past it) before it climbs.
  - The dike's opening under the ring where it bridges the Main line was a straight strip along the track's tangent;
    on the curved approach to the bridge the embankment stood in the viaduct 30 m along. It now follows the corridor's
    own samples (`island_dike.RAIL_OPEN`, a disc per 10 m sample).
  - **A road stamp never raises ground over a rail corridor** (`road_kit_stamp.guard_corridors` / `guard_cap`). With
    the natural ground open, the RING's own 1:1.5 fill batter (it is lifted 7 m over the Main line there) still spilled
    8 m up onto the elevated track (`probe_rail_track`: Terrain3D in the gauge at (1171, 449)). A road stamp reads every
    sibling network whose record's roads are all `road_class` "rail" (their stamp record: the rail is stamped first)
    and caps its result, never below the natural ground, at the rail surface - CLEARANCE out to the rail band's edge +
    `GUARD_MARGIN` (0.5 m), rising 1:1 beyond. After: gauge 10 064 samples clean, `probe_road_stamp` PASS (idempotent,
    restore exact).
- **Open, not from this change**: `ring_kita__6_F1` meets a junction footway on the dike where `kogai_loop` leaves the
  ring nearly parallel to its southbound arm (probe_road_clear); 18 of 13 007 PIER samples on the Wangan's west sea
  viaduct (-899, 1131) have no column foot within 25 m (probe_road_ground). Final gate state on this rebuild:
  `probe_rail_track` PASS, `probe_station_paid` 13/13, `probe_road_stamp` PASS, and those two.
- **Civic plots and streets are planned round each other**, so a re-site can move the streets under another plot:
  after the re-sites here `water_resort` went 746 m away (its old plot cut by the dike side road `teibo_sokudo_3`),
  and one more layout + `--resite=water_resort --avoid-streets` found it a plot 117 m from Waterpark station on
  wangan_dori. Re-run `island_civic_sites.py --check` after every layout and re-site what it names.


## Shop fronts and the kerb zone: awnings, signs, bicycles, 置き看板 (PLAN.md T2 + T5, 2026-10-12, s10)

**T2 -- what a frontage wears.** Data, in `building_types.json` `props`:

- `ShopHouse` (372 placed, every variant and `_BB` twin): a テント awning over one bay (`Prop_Awning_Navy`, 3.4 m
  wide, 0.9 m out, valance foot 2.28 m up; `left: 1.9` so it follows each width) and the small projecting shop sign
  (`Sign_ShopVertical`, `right: 0.35`, from 3.3 m).
- `OfficeMid` (79): a name board over the lobby (`Sign_OfficeName`, 6.0 x 0.7 m at 4.3 m).
- New library pieces (`blender/tools/library_civic.py`, in `library.blend`): `Prop_Awning_Navy / _Red / _Olive`,
  `Sign_OfficeName`. Only Navy is used; the other two are there for an artist or a per-street choice.

**`"overhang": true` -- a prop that is drawn but claims no ground.** A building is PLACED by its scene's
`metadata/building.aabb`, which was the merged mesh's bounds: anything standing out of the front wall made the
footprint deeper and pushed the building back from its frontage line on the next derive (PencilBuilding's 袖看板
already does, by 0.8 m). An awning is over head height and over the lot's own strip, so:
`layout_buildings.place_props` marks the piece, leaves it out of `forecourt_m` and reports `overhang_m` (how far it
stands out); `build_building_scenes.gd` takes the aabb's x / z from the pieces that stand on the ground only (y from
everything drawn); `probe_buildings` allows the mesh to be up to `overhang_m` deeper than the declared footprint.
Measured: ShopHouse's aabb is byte-identical before and after (z -5.498 .. 5.719), so the shop fronts were added
with `island_buildings.py write` alone -- no derive. `probe_buildings` 18 163 of 18 163 (it failed 24 on the size rule
before the allowance: the control).

**T5 -- the kerb-zone scatter** (`island_buildings.kerb_scatter`, written by `write`). Between the footway's outer
edge and a building's front there is `KERB_GAP` (1.5 m) of the lot's own ground. Each frontage building gets, by a
hash of its record key (an unchanged record rebuilds byte-identically):

| stands in front of | what | chance, count |
|---|---|---|
| shops (ShopHouse, PencilBuilding, YokochoRow, AkibaElectric, the six `Shop*`) | a pair of vending machines | 12 %, 1-2 |
| | parked bicycles (`Prop_Bicycle`, along the wall, +-7 deg) | 50 %, 1-2 |
| | a 置き看板 (`Prop_AFrameSign`) | 45 % |
| | planters (`Prop_PlanterBox`) | 35 %, 1-2 |
| flats (Apartment, ApartRC3F, Apato2F4 / 6, MansionPencil) | bicycles | 85 %, 1-4 |
| | planters | 25 %, 1-2 |

Nothing within 0.9 m of a front door's opening, nothing on a lot with a driveway across its front, nothing behind
the frontage row (`deep`) or on a hand-placed building. 1 234 on the island (bicycles 551, signs 318, planters 274,
vending machines 91). **One MultiMesh per piece per cell** (at most four draws a cell, `visibility_range_end` 110 m,
no shadows); only the vending machines collide (a box each). The MultiMesh draws a mesh resource, not a glTF scene:
`tools/godot/extract_piece_meshes.gd` merges a kit piece into `world/buildings/scatter/<Piece>.res` -- re-run it
when one of the four pieces changes in `library.blend`. `SCATTER_ON = False` is the control.

**A trap found on the way:** `export_building_kit.py` removes every file in a kit's `pieces/` its `.blend` does not
own, which includes the right-hand twins `tools/mirror_piece.py` writes (`Sign_ExpwyCantilever_R.*` was deleted by a
library export). `build_buildings.sh` now runs `mirror_piece.py` after the export.

**Not done:** a rolled-down shutter (a closed shop) -- props are per type, and a shutter on every ShopHouse reads as
a dead street; the awning's colour is one per type; more `_BB` roof billboards in nightlife / ekimae (the pick is
made in `derive`: `SIGN_REGIONS`); 止まれ / speed numbers painted on the road (T4: which language? the signs switch
at run time, paint baked into a road piece cannot).

**A second trap, found by a picture** (a standing sign 6 m from the camera was not drawn; the bicycle beside it
was): `visibility_range_end` is measured to the instance's AABB CENTRE, and one MultiMesh per piece spans its whole
252 m cell. Each scatter set's range is `SCATTER_RANGE` (110 m) plus the set's own reach from its centre. Any other
cell-wide MultiMesh that gets a range needs the same sum (the lot plinths and aprons carry none).

**Looked at** (`shot_city.gd`, noon): a shop street (awnings, projecting signs, vending machines), a bicycle and a
置き看板 close up, the three scatter meshes alone. **Not looked at:** the office name board (two pictures landed inside
a building; `probe_buildings` passes it), anything at night, the flats' bicycles.

## Interior lighting, measured (PLAN.md L1, 2026-10-12) -- a first reading, not a decision

User, 2026-10-11: "stores such as the konbini have room light meshes, but no actual light on ... not sure if baked
light will be cheaper for interiors -- do a performance test and suggest."

`tools/godot/measure_interior_light.gd` (needs a display): one interior standing ALONE (its `_Shop` scene, no city),
two cameras (standing inside; on the street 14 m from the front), day and night, and per variant the draw calls,
the GPU's own frame time over 240 frames and a picture. Variants: **control** (as shipped), **omni N** (an
`OmniLight3D`, no shadow, range 7 m, at the N ceiling points nearest the camera: 12 and 4), **fill** (no light node;
the environment's ambient raised to a flat warm colour, what a per-interior ambient would do).

**What the pictures show (KonbiniL, the clear result).** Control at night is BLACK inside: the emissive strips light
nothing. Omni gives the room pools of light and shaded walls, and from the street at night the shop front glows
through its glass, which is the konbini's whole look. Fill makes every surface the same flat white: it reads as
unlit, only brighter, and as built here it changes the ambient of the whole scene, not the room.

**What the timings show: less than they should.** GPU ms, control -> omni 12 / omni 4 / fill:

| | KonbiniL inside | KonbiniL street | Hospital inside | Hospital street |
|---|---|---|---|---|
| day | 0.38 -> 2.39 / 0.61 / 1.34 | 0.81 -> 1.28 / 1.12 / 0.81 | 2.35 -> 2.53 / 2.49 / 2.41 | 1.39 -> 1.69 / 1.72 / 1.79 |
| night | 0.92 -> 1.97 / 1.40 / 0.97 | 0.71 -> 1.11 / 1.04 / 0.60 | 1.11 -> 1.36 / 1.16 / 0.92 | 0.72 -> 0.97 / 0.85 / 0.60 |

Draw calls are unchanged in every cell (lights without shadows add none). The times are NOISY at this scale: the
same control scene reads 0.38 and 0.92 ms, and "fill" (no light at all) reads from -0.19 to +0.97 against its
control -- so the noise is about +-0.5 ms, as large as most of the differences. What can be said: 4 lights cost
somewhere between nothing and 0.5 ms, 12 lights between 0.2 and 2.0 ms, in a frame that is otherwise almost empty.
One run; an isolated room, not a frame of the game.

**Not built, so not measured:** (c) a LightmapGI per building scene and (d) vertex-baked light. Both are free at
run time by construction; (c) needs UV2 on the merged mesh and a bake step, (d) needs the scene build to write a
colour attribute.

**Suggestion, to confirm with a proper measurement:** real lights, pooled like `world.StreetLights` -- an unshadowed
OmniLight3D at the ceiling points of the interior the player is in or looking into, capped at 4-6 -- because it is
the only variant here that gives the room form and the lit shop front, it adds no draws, and its cost is at the
noise floor of this test. Before building it: repeat the timing INSIDE the game at a busy site (the perf gate's
cameras), several runs, so the number is real. Two traps found on the way: the konbini's `MI_Light` surfaces are
shelf and fridge strips under 2 m, not ceiling panels (the script falls back to a 4.5 m grid under a 2.85 m
ceiling), and a `_Shop` scene already uses the `_Open` mesh -- instancing both doubles the building.
