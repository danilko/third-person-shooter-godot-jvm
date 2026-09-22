# Japan art review — every block, building and material to re-author

**Who this is for:** the artist(s) who will review and redo the city by hand. Every row below names the file you
open, what is wrong with it *as a Japanese street*, the target measured from real data, and where to look.
Tick a row off when it has been reviewed, and write the decision next to it — "keep", "redo", or "redo later".

**Written 2026-09-21** (PLAN.md 3.6b / 3.17 / 3.18). Numbers are measured, not guessed; each says how to
re-measure it. When a number here and a number in a tool disagree, the tool is the owner and this file is stale.

---

## 0. The three reference sources, and what each may be used for

| source | what it is good for | licence rule |
|---|---|---|
| **PLATEAU `japan_city.blend`** — `/data/danilko/concept_arts/japan_city.blend` (outside the repo) | MASSING: footprints, heights, gaps between buildings, roof shapes, how a block is filled. Also facade TONE. 1 851 buildings of central Tokyo (third mesh 5339-35-85/86/95/96), LOD2 with textures. | CC BY 4.0. Use freely **with attribution** (CREDITS.md "Real-world data"). Do not copy its meshes or textures into the repo; take numbers and look. |
| **pakutaso** — <https://www.pakutaso.com/en/> | EYE-LEVEL detail PLATEAU cannot show: shop fronts, sashes, shutters, signage, konbini interiors, alleys, stations, textures. | Free incl. commercial, no registration. **Forbidden: selling the photo as-is; redistribution only under conditions** (terms: <https://www.pakutaso.com/userpolicy.html>, read them again before each use — they change). So: **never commit a pakutaso file**, and do not ship a texture that is a pakutaso photo lightly edited. Look, measure, author our own. Blur/avoid logos and trademarks. |
| **The user's own photographs** — `/data/danilko/references/japan/` (1 144 JPEGs) | Same subjects as pakutaso, and ours: a texture MAY be made from these (rectified, tiling, de-lit). | Ours. Record the source photo name beside any texture made from it. |

**Finding things on pakutaso.** Search is `https://www.pakutaso.com/search.html?search=<keyword>` and Japanese
keywords work far better than English (each keyword below was checked to return 20–30 photos). The useful
categories:

| subject | category page |
|---|---|
| city skyline / offices | <https://www.pakutaso.com/town/office/> |
| shopping streets, 繁華街 | <https://www.pakutaso.com/town/shopping/> |
| residential streets | <https://www.pakutaso.com/town/scenery/> |
| countryside | <https://www.pakutaso.com/town/rural/> |
| stations | <https://www.pakutaso.com/facility/terminal/> |
| restaurants, shops | <https://www.pakutaso.com/facility/shop/> |
| buildings / structures | <https://www.pakutaso.com/facility/spot/> |
| shrines, temples | <https://www.pakutaso.com/facility/shrine/> |
| street objects | <https://www.pakutaso.com/facility/installation/> |
| factories, construction | <https://www.pakutaso.com/mono/factory/> |
| textures: concrete / metal / brick / wood | <https://www.pakutaso.com/texture/concrete/>, <https://www.pakutaso.com/texture/metal/>, <https://www.pakutaso.com/texture/bricks/>, <https://www.pakutaso.com/texture/woodgrain/> |

**Re-measuring PLATEAU:**

    blender -b /data/danilko/concept_arts/japan_city.blend --python blender/tools/measure_plateau_blocks.py -- --json out.json
    blender -b /data/danilko/concept_arts/japan_city.blend --python blender/tools/measure_plateau_facades.py

Our own side of every comparison: `python3 tools/island_buildings.py` (placement), `probe_buildings.gd` (types),
`tools/godot/shot_city.gd` / `shot_buildings.gd` (pictures; need a display).

---

## 1. Lighting and the facade palette — DONE 2026-09-21 (PLAN.md 3.19(e)+(a))

The city used to render blue: the Sky3D sky light coloured every wall (a white car read navy at noon), and every
facade texture had been stripped to zero colour. Both are fixed: the facade tones are now **8 wall colours measured
from PLATEAU** (`plateau_wall_palette.json`, drawn in their measured shares), and the sky light is less blue with a
warm fill (`Sky3D.sky_contribution` 0.35). Evidence: `reference/true_colour_2026-09-21_*`.

What this means for review:
- [ ] **Judge colour now.** The colours on screen are the measured Tokyo palette under daylight. PLATEAU's walls
  are genuinely low-saturation (chroma p50 3.3): if a district should read MORE colourful than central Tokyo
  (residential beige/brown tile, the toon look), that is a style decision — a chroma gain on the palette — not a
  measurement. Say so and it is one number.
- [ ] **The glass towers still read deep blue**: that is the glass material reflecting the sky (see §4 `MI_Glass`,
  `MI_FakeInterior`).

---

## 2. Blocks and lots — how the city is laid out (tools, then art)

Measured against central Tokyo (PLATEAU, 1 851 buildings) and our island (3 592 buildings, `IslandBuildings.json`):

| | central Tokyo (PLATEAU) | our downtown | our whole island |
|---|---:|---:|---:|
| gap to nearest neighbour, median | **0.2 m** | 4.4 m | 4.4 m |
| gap, 90th percentile | 1.5 m | 10.7 m | 9.0 m |
| buildings TOUCHING a neighbour (< 0.3 m) | **59%** | 0% | 0% |
| buildings within 1 m of a neighbour | **85%** | 0% | 0% |
| plan angle vs. the 8 nearest neighbours, median / p90 | 1.1° / 12.3° | (all aligned to the street) | |

(PLATEAU hulls slightly over-report touching where eaves overlap; the order of magnitude is the point.)

- [ ] **B1. Buildings stand too far apart — the #1 reason a street does not read as Japanese.** A Japanese street
  is a near-continuous wall of narrow buildings; ours has a 3–4 m gap between every pair because every building
  keeps `ALLEY` = 1.5 m free on each side (`tools/island_buildings.py`). Target: in `downtown`, `city`,
  `nightlife` the side gap should be **0–0.5 m** (民法 art. 234 asks 50 cm from the boundary; in the core buildings
  touch), keeping the 1.5 m only in `residential`/`suburb`/`farm`. This is a TOOL change (a per-region side gap),
  then a re-derive. The 路地 (3.2 m every ~46 m) stays — it is what makes the inner lots reachable.
  Reference: pakutaso `雑居ビル`, `商店街`, `ビル群`; PLATEAU: any street in the file.
- [ ] **B2. Blank side walls must be authored once B1 lands.** When buildings touch, their SIDE walls show above
  the lower neighbour. In Tokyo those are plain, often streaked concrete or panel with no windows (a party wall
  may not have openings). Today only `PencilBuilding` has blank sides (`attached`). Needed: a stained blank
  party-wall row for every type (`party_wall_row` in the downtown kit), weathered at the top edge.
  Reference: pakutaso `ビルの側面`, `外壁`, `コンクリート壁`.
- [ ] **B3. One footprint per type — no variation.** Every one of the 582 pencil buildings is 7.6 × 13.3 m and
  23.8 m tall; PLATEAU's pencil class runs **4.6–8.5 m** wide (p10–p90), 8–20 m deep and **11–36 m** tall. Same
  for every type. Needed: 2–3 widths and 2–3 heights per type (a width/height set in `building_types.json`, the
  layout already scales by modules). Tool + data, then art review of each variant's facade.
- [ ] **B4. The lot slab reads as a bright white carpet.** Every lot is one white tile slab
  (`road_kit/materials/M_TileWhite.tres`, `LOT_MATERIAL`). In Japan the 民地 strip in front of a building is
  varied: dark granite pavers at an office, coloured interlocking block at a shop, bare concrete at a house, a
  gravel or concrete parking apron at a konbini. Needed: 3–4 lot materials chosen per type, darker than today's
  white. Reference: pakutaso `歩道 タイル`, `インターロッキング`, `駐車場`; `/texture/concrete/`.
- [x] **B5. DONE 2026-09-22: the block's ground IS the footway's paving.** Terrain3D's "Urban" layer is now packed
  from the footway's own `T_Concrete` maps (`tools/make_urban_texture.py --from-footway`) with the material's tint
  and 2.73 m tile on the texture asset, so kerb-back to door is one surface. ORIGINAL: **The block's own ground
  should be the SAME paving as the footway** (user, 2026-09-21; PLAN.md
  3.19(d)). Today the footway mesh is the kit's `T_Concrete` (2.73 m tile, warm light grey) and the block's
  ground is Terrain3D's generated "Urban" aggregate (`tools/make_urban_texture.py`, cool dark grey), so every
  kerb-back is a visible material line. In Japan the public footway and a block's paved back land are usually
  one asphalt/concrete surface; only the 民地 strip in front of a building differs (B4). Plan: rebuild the
  terrain's Urban asset from `T_Concrete` at the footway's scale and tint (or the other way round), judged on a
  seam picture after §1. Reference: pakutaso `歩道`, `路地`, `アスファルト`, `/texture/concrete/`.
- [ ] **B6. The 路地 (alley) has no surface of its own** — decided 2026-09-21 by looking
  (`reference/alley_slab_2026-09-21_before_top_after_bottom*.jpg`): the block's grey ground running between the
  white lots already reads as a way through. If a stronger cue is wanted later, it is a second terrain paint id,
  not a mesh. A real 路地 has: a drain gutter (側溝) with a steel grate down one side, potted plants, bicycles,
  a gas/water meter box, a narrow concrete strip. Those are PROPS, which is where the look would come from.
  Reference: pakutaso `路地`, `路地裏`, `下町`.
- [ ] **B7. The lot edge against open land has no boundary** (~12 km of edge). A Japanese lot ends in a
  ブロック塀 (concrete block wall, 1.2–1.6 m, often with a decorative top row), a hedge, or a low 擁壁 (retaining
  wall) where the ground falls. Needed: a wall piece set (straight, end, corner, gate gap) in `kits/library/`.
  Reference: pakutaso `ブロック塀`, `生垣`, `擁壁`.
- [ ] **B8. Roofscape is too clean.** PLATEAU's tall buildings almost never have a clean flat roof: only 6% of
  8–15-storey and 4% of taller buildings have ≥ 50% of their plan within 1 m of the top — the rest carry 塔屋
  (stair/lift houses), plant rooms, water tanks, sign frames and parapet steps. Ours have one stair house and a
  few AC boxes. Needed: roof clutter pieces (water tank 受水槽 on a steel stand, cooling tower, plant-room box,
  rooftop billboard frame, lightning rod, 手すり). Reference: pakutaso `屋上`, `給水塔`, `ビル 屋上`.
- [ ] **B9. Setbacks are too rare.** PLATEAU: a third of 3–15-storey buildings are tiered (the top third of the
  building covers under 80% of the footprint — 道路斜線 setbacks and podiums), half of towers. Ours: `Mansion`,
  `OfficeMid`, `PencilBuilding` have one setback. Target: most mid/tall variants get a 1–2 storey setback, some a
  two-step one.

**Tall / mid / low mix by class** (for zoning and the variant sets in B3; PLATEAU central Tokyo, p10 / median / p90):

| class | share | short side (m) | long side (m) | height (m) | storeys (÷3.3) |
|---|---:|---|---|---|---|
| 1–2 storeys, < 150 m² | 12% | 2.7 / 4.7 / 8.4 | 4.9 / 9.1 / 14.9 | 2.9 / 5.9 / 7.9 | 1–2 |
| 1–2 storeys, ≥ 150 m² | 2% | 8.7 / 12.7 / 20.5 | 14.9 / 21.8 / 39.1 | 3.4 / 6.1 / 7.7 | 1–2 |
| pencil (short side < 9 m, 3+ storeys) | **31%** | 4.6 / 6.7 / 8.5 | 8.0 / 12.3 / 20.1 | 11.3 / 16.8 / 35.5 | 3–11 |
| mid 3–7 storeys | 24% | 6.3 / 11.3 / 18.0 | 10.1 / 16.8 / 29.4 | 9.2 / 15.7 / 23.4 | 3–7 |
| tall 8–15 storeys | 27% | 10.3 / 14.9 / 27.6 | 14.2 / 22.9 / 41.7 | 26.9 / 35.7 / 44.4 | 8–13 |
| tower > 15 storeys | 5% | 18.9 / 32.8 / 52.1 | 24.4 / 43.8 / 88.8 | 52.0 / 60.9 / 110.5 | 16–33 |

This is the CORE of Tokyo; residential districts are much lower (CLAUDE.md "Sizes come from PLATEAU":
Ota-ku 2-storey houses 7.1 × 10.4 m, 7.4 m tall).

---

## 3. Building types — one row per scene

Files: `assets/world_source/buildings/building_types.json` (the type), `src/main/resources/com/openworld/world/buildings/<Type>.tscn`
(generated — do not hand-edit, edit the kit or the JSON and rebuild with `tools/building_kit/build_buildings.sh`).
The pieces live in `kits/quaternius_downtown_city/quaternius_downtown_city.blend` — a Boston/New York kit, which is
the root of most of what follows. Counts are how many the island places.

| ✓ | type | placed | what it is built from today | what reads wrong | target / what to author | pakutaso keywords |
|---|---|---:|---|---|---|---|
| [ ] | **ShopHouse** 店舗併用住宅 | 1 354 | shopfront + `residential_windows` (US window + tile) | Western sash windows; flat parapet; no balcony; shop front all glass | 2–3 storeys, 5.5–8 m wide; ground floor a shop with a **シャッター** (roll-up shutter) and a fabric awning テント; upper floors aluminium 引き違い sashes with 面格子 grilles, a small balcony with laundry pole; often a pitched or mono-pitch roof. Needs jp_street pieces 2, 3, 5 (PLAN 3.6b step 4) | `商店街`, `下町 商店`, `シャッター 商店` |
| [ ] | **Apartment** アパート | 763 | tile ground + residential windows, 2 storeys | reads as a small US motel | the 木造/軽量鉄骨アパート: 2 storeys, **external steel corridor + stair** (外廊下・外階段) on the front, a row of steel doors, a meter box and a small window per unit, siding panels, a slate or metal roof | `アパート 外階段`, `木造アパート`, `二階建て アパート` |
| [ ] | **PencilBuilding** ペンシルビル/雑居ビル | 582 | shopfront + `glass_floor` (full glazing) | an all-glass narrow tower is rare; no signs | 雑居ビル: tile or panel front with **one window band per floor**, **袖看板 vertical projecting signs** stacked up the front (the single strongest Tokyo read), a narrow entrance and a stair/lift core at the side, AC units on a rear/side | `雑居ビル`, `袖看板`, `歌舞伎町`, `ペンシルビル` |
| [ ] | **Mansion** マンション | 469 | tile balcony row with a 0.58 m rail strip | the balconies are a rail on a flat wall | RC 集合住宅: a **deep continuous balcony slab with a solid or frosted-glass parapet** on every floor (the mansion signature), sliding doors behind, partition boards (隔て板) between units, AC outdoor units on the balconies, external corridor at the back | `マンション ベランダ`, `集合住宅`, `分譲マンション` |
| [ ] | **OfficeMid** 中規模オフィスビル | 138 | glass lobby + US curtain wall | US glass box | Japanese mid-rise office: horizontal **window bands** in a tiled or panelled frame (not full glazing), a ground-floor lobby with a 自動ドア, company signs on the parapet | `オフィスビル`, `ビル 外観`, `丸の内` |
| [ ] | **Warehouse** 倉庫 | 183 | metal banded + windows | brick-era US warehouse | **折板 corrugated steel roof, ALC panel walls**, large roll-up shutter doors on the quay side, a painted company name, an office corner with a steel stair | `倉庫`, `物流倉庫`, `港 倉庫` |
| [ ] | **Konbini** コンビニ | 87 (+6 with a car park) | shopfront, fascia band, full interior | fascia is a plain band; interior layout (PLAN 3.18(y)) | fascia with the **three brand-neutral colour stripes** carried round the corner, a lit 袖看板 pole sign, the glass front with the 目隠し strip (shipped), a bin station and a bicycle rack at the front, back-of-house door | `コンビニ`, `コンビニ 店内`, `コンビニ 駐車場` |
| [ ] | **FamilyRestaurant** ファミレス | 5 | shopfront all round | flat box | a raised pitched or mansard roof edge, a tall pole sign, a car park; windows all round with booths (shipped) | `ファミレス`, `ファミリーレストラン` |
| [ ] | **GasKiosk / GasStation** | 5 | kiosk + canopy + pumps | US pumps; canopy edge plain | a thick lit canopy fascia, Japanese pumps (ground unit with big price panel, or overhead 懸垂式), a price tower | `ガソリンスタンド`, `給油所` |
| [ ] | **StationBuilding / StationRural** 駅舎 | (sites) | shopfront box | a shop, not a station | a station name board on the roof edge, a canopy over the entrance, ticket machines under the canopy, a bicycle parking lot | `駅舎`, `無人駅`, `地方 駅` |
| [ ] | **(missing) 一戸建て** detached house | 0 | — | the whole residential texture of Japan is missing | 2 storeys, ~7 × 10 m, 7.4 m tall, **pitched roof** (slate/kawara), siding walls, a carport, a block wall and gate — PLAN 3.6b step 4 item 7 and step 5 | `住宅街`, `一戸建て`, `建売住宅` |

**Building-level items shared by every type:**

- [ ] **Storey height.** Ours: 2.73 m (plain) / 3.64 m (banded); PLATEAU averages ~3.3 m. A residential floor is
  2.8–3.0 m, an office 3.6–4.0 m. Needs the 0.2–0.3 m spacer band piece (PLAN 3.6b step 6).
- [ ] **Windows.** Every window is a US double-hung shape. Japan: aluminium 引き違い (2-panel sliding), silver or
  dark bronze frame, 面格子 grille on ground-floor and bathroom windows, frosted glass in bathrooms.
  Reference: `アルミサッシ`, `面格子`, `窓 外観`.
- [ ] **Signs are the Tokyo street.** No type carries text/signage beyond a fascia stripe. Needed: 袖看板
  (vertical projecting), 置き看板 (A-frame on the pavement), rooftop sign frames, のぼり banners. Brand-neutral,
  our own text. Reference: `看板`, `袖看板`, `ネオン 繁華街`, `のぼり`.
- [ ] **Utility poles and wires** (電柱・電線) — the most Japanese thing on a residential street, and missing.
  Road furniture, placed per footway (like lamps). Reference: `電柱`, `電線`.
- [ ] **AC outdoor units**: the kit's is a Western box; Japanese units are the white horizontal fan box with a
  pipe run and a duct cover up the wall. Reference: `室外機`.

---

## 4. Materials — the downtown kit (`kits/quaternius_downtown_city/materials/`)

Owner: `tools/building_kit/retone_downtown_kit.py` writes the tone variants; the `.tres` are hand-owned otherwise.
Tone targets come from PLATEAU (facade luminance p10 100 / median 136 / p90 161, R−B +0.9 — **Tokyo is grey,
the variety is in lightness, never hue**).

| ✓ | material | used for | status / what to redo | reference |
|---|---|---|---|---|
| [ ] | `MI_Trim` (+ its 7 PLATEAU colour tones `_WhiteWarm`, `_DarkCool`, …) | the "tile" facade (`tile_*` rows, most side walls) | colour is now PLATEAU's measured wall palette (§1). The texture is the kit's rust-streaked trim, neutralised by a high-pass (`T_Trim_Neutral`), and reads as **flat plaster**, not tile. Redo as **磁器タイル 45×95 mm or 45×45 mm mosaic** (white, beige, light grey, brown) with a faint grout grid visible at ~10 m. Keep the four tone levels | `外壁タイル`, `タイル 外壁`, `/texture/bricks/` |
| [ ] | `MI_Trim_MetalConcrete` (+ the same 7 colour tones) | office/warehouse/konbini metal panels; sides of most types | colour is PLATEAU's palette (§1); 36% of its texels are metallic (ORM blue channel), × 0.4. Redo as two materials: **ALC panel** (600 mm vertical panels, sealant joints, painted light grey/beige) for warehouses, and **painted aluminium spandrel panel** for offices | `ALC 外壁`, `金属パネル 外壁`, `/texture/metal/` |
| [ ] | `MI_Trim_Dark`, `MI_Trim_Green` | shopfront frames, a dark panel | same texture as `MI_Trim`; dark is a tint only. Redo dark as **bronze anodised aluminium** (sash/frame colour) | `アルミ サッシ ブロンズ` |
| [ ] | `MI_RedBrick` (+ `_Pale`) | brick rows (few Japanese types) | Tokyo has little exposed brick outside Meiji buildings. Keep only for Tokyo Station; remove from ordinary rows | `赤レンガ 東京駅` |
| [ ] | `MI_Ornaments` | cornices, US decorative pieces | cornices and ornament are Western. Replace pieces with a plain **parapet coping (笠木)** in aluminium | `笠木 屋上` |
| [ ] | `MI_Glass`, `MI_GlassShopfront` | glazing | shopfront glass + 目隠し strip shipped 2026-09-21. Office glazing wants a darker, slightly green tint (Japanese offices use heat-reflective glass). | `ガラス張り ビル` |
| [ ] | `MI_FakeInterior_*` | fake lit rooms behind upper windows | US office interiors. Needs Japanese interiors: fluorescent-lit offices (white ceiling grid, blinds half down), flats with curtains/laundry, bars with warm light. Our own paintings | `オフィス 夜景`, `マンション 夜景` |
| [ ] | `MI_InteriorWall/Floor/Roof` | interiors (konbini, restaurant, station) | retoned to neutral; fine for now. Konbini floor = light grey terrazzo/vinyl, ceiling = white panels with fluorescent strips | `コンビニ 店内` |
| [ ] | `MI_ShopBand`, `MI_ShopStripe_*` | fascia, 目隠し strip | shipped (brand-neutral blue/green/red/amber). Review the proportions against real konbini fascias | `コンビニ 看板` |
| [ ] | `MI_DoorLeaf_White/Wood` | swing doors | Japanese apartment doors are **steel, painted**, with a lever handle and a peephole; houses have aluminium 玄関ドア. Redo | `玄関ドア`, `アパート ドア` |
| [ ] | `MI_Asphalt`, `MI_Concrete`, `MI_Dirt` | kit ground pieces | fine | — |

**Road kit** (`kits/road_kit/materials/`): `M_Asphalt` (fine), `M_ConcreteTile` (footway — Japanese footways
are usually dark asphalt or interlocking block, often with a coloured stripe; review), `M_TileWhite` (the lot —
see B4), `M_Concrete`/`M_Barrier` (fine). Markings: Japanese white/yellow lines are shipped; add 止まれ,
the diamond ◇ and speed numbers (PLAN 3.6b step 4 / `jp_street`).

**Library kit** (`kits/library/materials/`, palette `kits/library/palette.json`): these are ours and already
Japanese-chosen; they will flatten for the toon look (PLAN 3.14). Review only.

---

## 5. Library pieces that do not read as Japanese (`kits/library/library.blend`)

Owner list: `kits/library/extract.json` `jp` (status `hand` = needs a modeller) and `ARTIST_NOTES.md`.

| ✓ | piece | what to add |
|---|---|---|
| [ ] | `Shop_Counter` | hot-snack case (ホットスナック) at the customer end, cigarette wall behind the clerk |
| [ ] | `Shop_Register` | Japanese POS: customer screen, 自動釣銭機 change machine, IC-card pad |
| [ ] | `WC_Toilet` | washlet control panel |
| [ ] | `Gas_Pump` | slim Japanese ground unit with a big price panel, hoses both faces; or overhead 懸垂式 |
| [ ] | `Station_TicketGate` | JR/Suica gate: slim body, lit IC pad, short flaps, direction light |
| [ ] | `Station_Bin` | three sorted openings (燃えるゴミ / 缶・びん / ペットボトル) |
| [ ] | `BusStop_Sign` | round-top plate on a pole, round concrete base, timetable box |
| [ ] | `Station_TicketMachine`, `Station_VendingMachine` | faces: touch screen + fare map; sample bottles in three rows + buttons |

pakutaso: `券売機`, `自動改札`, `自動販売機`, `バス停`, `コンビニ レジ`.

---

## 6. Street furniture and nature (placed by the Road Kit, `kits/road_kit/furniture.json`)

| ✓ | item | status |
|---|---|---|
| [ ] | `TrafficLight_JP` (Zombie kit, our Japanese re-make) | still carries the download's "E 12 St" name plate. Source: `kits/quaternius_zombie_apocalypse/TrafficLight_2_Japan.blend`; the plate is removed in `build_street_poles.py` (PLAN.md 3.21), and street names come later from one generated name atlas, not a label per sign |
| [ ] | `StreetLight_JP` (+ twin) | fine in shape; the twin is to be replaced by a simpler Japanese lamp (user) |
| [ ] | `Sidewalk_Planter`, `Prop_Bollard`, `Prop_Drain`, manhole | US pieces. Japan: low concrete 植栽帯 kerbs with shrubs, yellow/white steel bollards (車止め), a steel grating drain along the kerb, a decorated municipal manhole |
| [ ] | missing | **電柱 utility poles + wires**, 点字ブロック tactile paving strips on footways, guardrails (ガードレール, white steel), カーブミラー at corners, bicycle parking, vending machine clusters |
| [ ] | trees | sakura and 黒松 are placed; review the canopy colours; add 銀杏 ginkgo (the Tokyo street tree) and ケヤキ |

pakutaso: `ガードレール`, `点字ブロック`, `カーブミラー`, `電柱`, `街路樹 銀杏`.

---

## 7. Landmarks (`kits/library/library_landmarks.py`, our own base models)

Each needs hand refinement (PLAN 3.12c). Tokyo Tower, Tokyo Station, Rainbow Bridge, Osaka Castle, Shuri Castle,
Airport Terminal. Review silhouette against photos first; detail last.
pakutaso: `東京タワー`, `東京駅 丸の内`, `レインボーブリッジ`, `首里城`, `大阪城`.

---

## 8. Suggested order

1. §1 is done — review the colours under the new lighting first.
2. B1 + B3 (spacing and variants — tool changes, the biggest read for the least art).
3. The five type redos with the most instances: ShopHouse, Apartment, PencilBuilding (signs), Mansion (balconies), plus the missing 一戸建て.
4. `MI_Trim` → real tile, `MI_Trim_MetalConcrete` → ALC / panel.
5. Street furniture: utility poles, guardrails, tactile paving.
6. Roofscape (B8), setbacks (B9), boundary walls (B7).
7. Library pieces (§5), landmarks (§7).
