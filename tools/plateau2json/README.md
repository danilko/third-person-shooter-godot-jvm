# plateau2json — PLATEAU CityGML → 3D JSON → compressed world

Pulls roads (with lane surfaces), the railway network (including the Shinkansen),
buildings, terrain, land use, water and bridges out of Project PLATEAU CityGML into a
plain JSON intermediate, then squeezes that real-world extract into a fixed square (a
6 km × 6 km world by default) without thinning the roads.

Nothing here depends on Blender. The JSON is meant to be read by your own generator.

**Attribution — required in any public build:** `Data: Project PLATEAU (MLIT)`.
PLATEAU is published by Japan's Ministry of Land, Infrastructure, Transport and Tourism
and distributed via the G-Spatial Information Center under **CC BY 4.0**. Raw CityGML
zips are multi-GB and are kept **outside** the repo, in `/data/danilko/plateau_model/`.

---

## Pipeline

```
fetch.py       catalogue lookup + download        (optional; datasets may already be local)
    ↓
extract.py     CityGML tiles  → per-layer 3D JSON in real metres
    ↓
compress.py    real world     → 6144 m × 6144 m, cross-sections preserved
    ↓
verify_compression.py          the five checks that catch a bad squeeze
preview_png.py                 top-down PNG + Blender scale sidecar (debug view)
```

### 1. `fetch.py`

```bash
python3 fetch.py --wards 13101 13102 13103 13108 13109 13111 13113 --year 2025 --extract
python3 fetch.py --wards 13103 --list-only     # just show what is published
```

Resolves download URLs **live through the CKAN API** — PLATEAU asset URLs contain opaque
hashes that change between publications, so a hardcoded list rots. After each download it
prints the archive's real `udx/` module list and tile counts, so `wtr` (waterbody) and
`tran` LOD presence is verified rather than assumed. It also grabs the small
`*_related.zip`, which is where the railway data lives (see below).

Wards covering the Tokyo bay/airport area: 13101 千代田, 13102 中央, 13103 港, 13108 江東,
13109 品川, 13111 大田 (Haneda), 13113 渋谷.

### 2. `extract.py`

```bash
python3 extract.py \
  --input /data/danilko/plateau_model/13111_ota-ku_city_2023_citygml_1_op \
  --out   build/plateau_json \
  --layers road,rail,building,terrain,landuse,water,bridge \
  --related /data/danilko/plateau_model/13103_minato-ku_2025_related.zip \
  --bbox 139.69 35.540 139.81 35.700 \
  --origin 139.77 35.62
```

`--census-only` parses and prints counts + code histograms without writing geometry —
the fastest way to see what a dataset actually contains.

Writes one file per layer plus `manifest.json`:

| file | what's in it |
|:--|:--|
| `road.json` | `tran:Road` + nested `traffic_areas` (real lane / sidewalk / intersection surfaces), `function`, `width_type`, `section_type`, `usage`, `lanes_per_direction_hint` |
| `rail.json` | railway lines with `route_name`, `operator`, `railway_class`, `is_shinkansen` |
| `building.json` | `measured_height`, `storeys`, `usage`, LOD0 roof edge + LOD1/2 solids with wall/roof/ground semantics |
| `terrain.json` | DEM TIN triangles — the real ground surface |
| `landuse.json` | zoning polygons + `land_use_type`, `is_water` |
| `water.json` | `wtr:WaterBody` surfaces (2025 v5 datasets only) |
| `bridge.json` | LOD2 bridge solids |
| `station.json`, `landmark.json` | from the related GeoJSON, when `--related` is given |
| `tunnel/furniture/vegetation/underground/area/cityplan.json` | the smaller v5 modules (`tun`, `frn`, `veg`, `ubld`, `area`, `urf`) — generic records keeping all raw attributes |

`--layers all` pulls every module a dataset ships. Geometry harvesting is **LOD-agnostic**:
each shape carries its own `lod` string (`lod1MultiSurface`, `lod2Solid`, `lod3MultiSurface`…),
so LOD3/LOD4 geometry flows through with no code change the moment a dataset authors it.
Buildings additionally get a `lods` list, which is the quickest way to see whether you got
LOD1 boxes or real LOD2/3 detail.

Every numeric code is emitted resolved: `{"code": "5", "label": "都市高速道路"}`, read from
the dataset's own `codelists/*.xml`, so downstream tools need no lookup tables.

### 3. `compress.py`

```bash
python3 compress.py --in build/plateau_json --out build/plateau_json_6km --size 6144
python3 verify_compression.py --raw build/plateau_json --compressed build/plateau_json_6km
```

> **Compress the distance *between* things. Never compress the things themselves.**

A uniform scale would fit the box and make a 3.25 m lane 1.1 m wide. Instead:

* a **monotonic piecewise-linear warp per axis** moves things closer together, with band
  scales solved from feature density — dense bands (a downtown core, a waterfront, the
  airport) stay near 1:1 while empty bands (open water, gaps) collapse hard, until the
  total fits. The same warp is applied to every layer, so nothing tears or de-registers.
* **elongated network geometry** (road and rail slabs) takes its *along-axis* coordinate
  from the warp — so a road spanning bands of different scale still shortens
  non-uniformly — while its *across-axis* coordinate is copied verbatim from the
  original. A 15 m carriageway stays 15 m. There is no gain factor and nothing to clamp.
* **authored 3D models** (buildings, bridges) and **compact blobs** (junction plazas,
  `sectionType=4` intersection polygons) are translated rigidly and never deformed.
* **Z is never touched** — viaduct clearances, terrain slope and building heights stay
  real against the shortened plan.
* the warp is inset by a **margin** auto-sized from the half-widths of features that
  actually land near an edge, so preserved cross-sections still fit inside the box.

`warp.json` records the band tables and both axis mappings, so the transform is auditable
and a compressed point can be traced back to its real position.

Knobs: `--min-scale` / `--max-scale` (how hard empty vs. dense bands squeeze),
`--min-elongation` (rigid vs. shortened threshold), `--cross-section-scale` (drop below
1.0 if a hard-collapsed region leaves neighbouring roads overlapping), `--margin`.

### 4. `preview_png.py`

```bash
python3 preview_png.py --in build/plateau_json_6km --out build/preview.png --size 4096
```

Black background, roads white (stroke weight from the real road class), rail green, water
blue, buildings grey; `--plain` for strictly white/green/black. Writes a sidecar with
`metres_per_pixel` and `extent_m` — add a plane of that size in Blender and the image
lines up 1:1 with real-world scale.

---

## Things that will bite you (all verified against the real data)

**Coordinates are `lat lon height`, not lon/lat.** PLATEAU posLists are EPSG:6697
(JGD2011 geographic 3D). `citygml.parse_poslist` swaps them exactly once; nothing else in
the pipeline reorders coordinates.

**Projection.** Horizontal goes to **EPSG:6677** (JGD2011 / Japan Plane Rectangular CS IX,
the Tokyo zone) via pyproj, transforming from the *2D* CRS 6668 rather than the compound
6697 so no vertical datum shift is applied — PLATEAU heights are already T.P. elevations
in metres and are carried straight through. pyproj returns 6677 as (northing, easting);
`always_xy=True` is used throughout. Output axes are **X=east, Y=north, Z=up**, relative
to a declared origin recorded in every file header.

**Namespaces drift; local tag names don't.** The 2020/2022 tiles are CityGML 2.0 + i-UR
1.5, 2023 is i-UR 3.0, 2025 is spec v5. Every match in `citygml.py` is on the local tag
name, which is why the same extractor runs over all of them with no changes.

**Tiles live in `udx/<module>/`.** `discover_tiles` also accepts `udm/`, a bare directory
of tiles, or a single `.gml`.

**Road elevation depends on the dataset generation.** `tran` **LOD1** is a flat footprint —
every Z is 0, so those roads need draping onto `terrain.json`. The **2025 v5** datasets author
`tran` at LOD2 **and LOD3** with **real elevation**: Chiyoda's traffic areas span Z −6.33 →
29.61 m, so no draping is needed there. Bridges and buildings always carry real 3D.

**Carriageway / sidewalk / intersection are in v5, but not individual lanes.** Chiyoda v5
yields 33 745 `TrafficArea` records across 15 375 roads:

| code | meaning | count |
|:--|:--|--:|
| 1000 | 車道部 carriageway | 11 854 |
| 2000 | 歩道部 sidewalk | 13 651 |
| 1020 | 車道交差部 intersection | 6 639 |
| 3000 | 島 median island | 1 601 |

with 417 144 LOD3 shapes. Code **`1010`=車線 (an individual lane) is defined in the codelist
but not authored** — carriageways are not subdivided per lane in any dataset checked. Split
lanes from the 車道部 polygon width downstream; `lanes_per_direction_hint` gives the count.

**Rail is not in `tran` for the Tokyo wards.** There are **zero** `tran:Railway` features
across all 751 local `tran` tiles, and no `rwy` module. The railway network is published
instead as an official GeoJSON sidecar inside each ward's `*_related.zip` — pass it with
`--related`. Minato-ku alone yields 150 line features across 16 routes including
**東海道新幹線** (5 segments, operator 東海旅客鉄道), 山手線, 東京モノレール羽田線,
東京臨海新交通臨海線 and 臨海副都心線 — i.e. the whole bay/airport rail complex. These
lines are **2D**, so their Z is 0 and they need draping too.

**Land use `class` is not always present.** The 2023 tiles carry `luse:class`; the 2022
tiles only carry `uro:orgLandUse`. Both are emitted (`land_use_type` / `org_land_use`).

---

## The codelists that matter

`Road_function` — drives `lanes_per_direction_hint` and the preview stroke weight:

| code | meaning | hint |
|:--|:--|:--:|
| 1 | 高速自動車国道 national expressway | 4 |
| **5** | **都市高速道路 urban expressway (Shuto)** | 4 |
| 2 | 一般国道 national highway | 3 |
| 3 | 都道府県道 prefectural road | 3 |
| 4 | 市町村道 municipal road | 2 |
| 10–15 | 建築基準法42条 narrow streets | 1 |

`RoadStructureAttribute_widthType`: `1`=≥15 m, `2`=6–15 m, `3`=4–6 m, `4`=<4 m — the
fallback when `function` is unsurveyed (`9000/9010/9020`).

`RoadStructureAttribute_sectionType`: `1`=at grade, **`2`=高架橋 elevated viaduct**,
`3`=橋梁 bridge, **`4`=交差部 intersection**, `5`=underpass, `6`=tunnel.

`TrafficArea_function`: `1000`=車道部, **`1010`=車線 (one lane)**, `1020`=車道交差部,
`2000`=歩道部, `2020`=歩道, `2030`=自転車道; rail codes `1040`=踏切道, `1050`=軌道敷,
`8000`=軌道中心線, `8100`=軌道, `8112`=レール (flagged as `is_rail` / `is_lane`).

`Common_landUseType`: **`204`=水面** (river/canal/moat), `205`=beach/riverbed/shore,
`211`=residential, `212`=commercial, `213`=industrial, `216`=transport facilities.

---

## Requirements

Python 3.9+, `pyproj` (projection) and `Pillow` (preview only). Everything else is stdlib;
CityGML is parsed with `iterparse` so a 400 MB tile streams in bounded memory.
