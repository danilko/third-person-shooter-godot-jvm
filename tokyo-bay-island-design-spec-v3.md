# Tokyo-Bay Island v3 — Design & Modeling Spec

> **This is the active plan.** v1 (`tokyo-bay-island-design-spec.md`) is the source of the
> rules; v2 (`-v2.md`) was the real-Tokyo-topology experiment and is superseded — kept only
> because its PLATEAU-decimation method (§1 there) still applies verbatim.
>
> Plates: `tokyo-bay-island-overview-v3.svg` (read first) · `tokyo-bay-island-modeling-plate-v3.svg`
> Regenerate both: `python3 tools/island_v3_plates.py` · geometry lives in `tools/island_v3_geom.py`

---

## 0. What v3 is

v1's **fictional island**, condensed back to its original size, and re-planned as a clean
south-to-north transect with the neon core split into three centres:

```
HARBOUR / BAY  ->  NEON x3  ->  RESIDENTIAL  ->  FARMLAND  ->  MOUNTAIN
   (south)        A / B / C      danchi +      valley +      massif +
                  split by       detached      paddy-to-      spur ridge
                  the river                    the-sea arm
```

v2's real-Tokyo layout is dropped. What survives from it is the *method*: PLATEAU used as a
decimated road skeleton + a massing histogram + a handful of landmark meshes, never as
shipped building geometry.

### Measured, not estimated

| | v1 proposed | **v3 actual** | GTA III |
|:--|--:|--:|--:|
| world box | 1.9 × 1.9 km | **2016 × 2016 m** | — |
| land | 2.4 km² | **2.49 km²** | 4.38 km² |
| districts | n/a | **14 built of 16** | — |
| building instances | ~3,000 | **2,060** | ~3,000–4,000 |
| flagship lap | 3.4 km | **3,331 m** | — |

`2016 m = 4 × 4 districts of 504 m`, so `world_grid.GRID_N` goes **6 → 4** — one constant.
`CELL`, `DISTRICT`, `to_world()`, seam naming and `piece_id_for_cell()` are all
`GRID_N`-parametric and unchanged.

---

## 1. Reference: 新潟市 / the Echigo plain, not Tokyo

Tokyo was the wrong reference for what this island actually is — a mid-size coastal city with
farmland running to the sea and a mountain standing beside it. **Niigata is that city**, and
five of its patterns are now load-bearing here. Each is cheap to build and unmistakably
Japanese, which is exactly the combination this budget needs.

| Niigata pattern | how v3 uses it | why it earns its place |
|:--|:--|:--|
| **信濃川 splits the city** — Furumachi (old town, west bank) vs Bandai (new centre, east bank), joined by 萬代橋 | the river runs **through** the core, dividing **Neon A** (old town) from **Neon B** (electric town); one **91 m multi-arch stone bridge** is the hero crossing | gives the city an internal landmark and a chokepoint, and makes the three-centre split *structural* instead of arbitrary |
| **砂丘列 dune ridges + drained back-swamp** — the built land is linear ridges parallel to the shore, the paddy is the troughs between them | the eastern farmland is **striped**: farmhouse rows on the ridges, paddy in the troughs, all parallel to the coast | replaces uniform scatter with a real land-use grain — and the stripes read instantly from a car |
| **海岸松林** — a continuous black-pine windbreak on the seaward dune | a pine belt inside the whole ocean-facing coast | the cheapest "Sea of Japan" signal there is, and a continuous occluder wall along the map's most open edge |
| **潟 lagoons** stranded inland when the swamp was drained | one **lagoon** among the paddies | free landmark, free reflection, free scenic pull-off |
| **弥彦山** — an isolated 634 m peak rising straight off the plain by the sea, with the shrine at its foot and the *okumiya* on the summit | the **spur ridge** that comes down beside Neon C, with **a shrine at the foot and a second on the summit** | this is exactly your "mountain on the neon side" and "shrine on top" in one real precedent |

The main massif keeps the touge and the pass shrine (v1's brief). So the island carries
**three shrines from one kit**, dressed three ways: urban forest at the foot, exposed summit
*okumiya*, and snowy mountain pass.

---

## 2. Zones — south to north

| zone | Z | content | unique meshes | instances |
|:--|--:|:--|--:|--:|
| **Harbour / port** (reclaimed peninsula, straight seawalls) | +2 | sheds, tanks, container stacks; fused to the mainland by a wide land neck — drive straight in | 12 | 51 |
| **Airport island** (offshore SE) | +4 | terminal, hangars, **520 × 45 m runway = drag strip** | 8 | 20 |
| **Neon A** — main core, old town, **west bank** | +3…6 | zakkyo 6 × 12, zero setback, interior solid, 4–6 m *roji*; central station | 16 | 644 |
| **Neon B** — electric town, **east bank** | +3…6 | same kit, taller signage, under the rail viaduct | reuses A | 373 |
| **Neon C** — hillside strip, under the spur | +6…20 | low-rise entertainment climbing the slope, hairpin streets | reuses A | 273 |
| **Residential** | +10…30 | danchi slabs on **one sun-angle bearing that ignores the street grid** + detached 7 × 9; farmhouses thin out northward into the paddies | 12 | 719 |
| **Farmland** — valley, flank terraces, and the **ocean arm** | +45 (valley) | dune-ridge/trough striping, lagoon, pine belt, coastal station | 8 | 55 |
| **Mountain + spur** | +80…380 | 1:1 slope, touge to the **pass +220**, peak +380 scenery only, tunnel portal | 8 | — |

**Farmland and residential interlock rather than abut** (your note). There is no hard line:
danchi give way to detached, detached to farmhouse-and-outbuilding, farmhouses to paddy, over
about 300 m. The only sharp edge in the whole transect is the seawall.

**The dense zakkyo envelope totals ~0.29 km²** across the three centres. Small on purpose —
v1's rule holds that 0.5 km² of real density reads as a huge city, and three separated 0.1 km²
centres read bigger than one 0.3 km² blob because you cross open ground between them.

---

## 2b. Coastline, the bay, and block size

### The coast is fractal, the skeleton is not

The island is drawn from **two** polygons. A smooth 28-vertex skeleton is what the design is
authored against — the ring road offsets from it, zones are laid out on it — and a
**224-vertex fractal coastline** (three rounds of midpoint displacement, ±30 m decaying by
0.55) is what gets drawn and collided. That split matters practically: coastal detail can be
retuned to taste without moving a single road. Three **offshore islets** are scenery only,
deliberately outside `LAND`, so they carry no roads, no buildings and no streaming cost.

The **reclaimed edges stay dead straight** — port peninsula and airport island. That contrast
between a ragged natural coast and a ruled artificial one is most of what reads as "reclaimed"
in a Japanese port city, and it costs nothing.

### The bay cuts in — and that is the point

The bay is now a **drowned river mouth (ria)** running ~850 m north into the city, 130 m wide
at the head and 260 m at the sea. It does four jobs with one piece of water: it is the river's
outlet, the city divider, the harbour, and the reason the main arterial needs a real bridge.

It also **removes ~0.17 km² of land** (2.53 → 2.49 km²) while *adding* coastline, which is the
trade you were reaching for: less to build, more to look at, more edge to drive along.

**Yes, this is a real Japanese city pattern — several of them.** The closest are:

| city | pattern |
|:--|:--|
| **長崎** | a deep harbour biting into the city with mountains rising immediately behind — the single best match, since v3 also has the spur ridge standing directly over Neon C |
| **尾道** | a narrow channel through the middle of town, crossed by one large bridge; small old crossings upstream, the big span downstream |
| **神戸** | reclaimed port islands off a city pinned between water and hills |
| **横浜** | Bay Bridge across the harbour mouth as the arterial crossing |

v3 uses the **Onomichi arrangement of two crossings on the same water**: a small
**94 m arch bridge** upstream between the old-town banks, and a **243 m bay bridge** downstream
carrying `Hama-dori`, the main arterial. Cutting either one forces a genuine detour around the
bay head — which is v1's racing fork, arriving for free.

### Block size is a theme property, not a constant

> **Neon buildings are not bigger than houses. They are the same size and much taller.**

This is the most counterintuitive fact in the kit and it drives the whole build. A zakkyo
shop-office is **6 × 12 m = 72 m²**. A detached suburban house is **7 × 9 m = 63 m²**. Nearly
identical footprints. What separates them is:

- **height** — 3–8 floors × 3.2 m against 2 floors;
- **setback** — zero, buildings touching on both sides, against 0.5–1 m side gaps;
- **frontage rhythm** — a 60 m block face carries 10 shopfronts in the core and 7 houses in the
  suburbs.

Japanese lots are *unagi no nedoko*, eel beds: 4–7 m wide, 12–15 m deep. Density comes from
**narrow frontage and no gaps**, never from big buildings. The genuinely large footprints on
this map are the exceptions: danchi slabs (12 × 55), harbour sheds (40 × 70), and the anchors
below.

What *does* change per theme is the **block**, which earlier passes got wrong by using one
168 m block everywhere — that is exactly why the neon read like the suburbs in a different
colour:

| theme | block | real-world basis |
|:--|--:|:--|
| Neon A / B / C | **84 m** | dense centre, 50–90 m, cross-streets every block |
| Residential | **168 m** | suburb, 100–170 m |
| Port | **252 m** | industry needs turning room for trucks |
| Airport | **252 m** | apron scale |
| Farmland | **336 m** | field parcels, not blocks |

And because a real neon district is *not* uniformly eel-beds, one block in seven now carries a
single **24 × 34 m anchor** — department store, office, station building. Nine of them across
the three centres. They are the landmarks you navigate by inside the density.

---

## 3. The castle (what replaced the Imperial Palace)

v2 put a 520 × 440 m Imperial Palace at the map centre. At 2016 m that is a quarter of the
world, so it is now a **260 × 210 m castle with a moat and stone walls** — a *tenshu*, gate,
and pine ground, sitting between Neon A and the residential band.

It keeps the entire reason the palace was there: **it is a hole every road must bend around**,
so the grid can never read as an American lattice. It costs almost nothing (walls, water,
trees, one keep) and it gives the flagship lap its start/finish straight along the moat.

`assets/world_source/plateau/data/osakacastle.json` (30 buildings) becomes usable reference
here — on a *fictional* island a castle is right, where on v2's Tokyo map it was out of place.

---

## 4. Water, bridges, connectivity

- **Sea rings everything** — the map boundary on all sides, no air walls. The massif is the
  impassable north wall by shape.
- **The river** is one spine: snowmelt → paddies → through the city between Neon A and B →
  widens into the **harbour inlet** → sea. Its mouth is what separates the port from the
  eastern shore.
- **Arch bridge, 94 m** — the Bandai-bashi analogue over the river between the two neon
  centres. Multi-arch stone, hand-modelled, the city's signature image.
- **Bay bridge, 243 m** — the main arterial crossing, carrying `Hama-dori` over the bay.
  Also the early-game **gate** (v1's role for it).
- **Airport bridge, 550 m, double-deck road + rail** — the single most expensive asset on the
  map, and the only link to the airport island. Reached by **one 335 m ramp off the expressway
  loop beside S3** — not by a separate surface route. An expressway that sheds a ramp straight
  onto a bridge is both how Japanese bay crossings actually work and one road fewer to build,
  light and populate.
  > **Why it runs *along* the bay, not across it.** At a 2 km world there is nowhere a 550 m
  > span can cross open water — the widest gap is ~250 m. Routing it parallel to the coast,
  > out over the bay from the eastern headland to the island's north-east corner, buys the
  > full length honestly and reads better: you drive out over water with the city receding on
  > your right. This is the one dimension v1 asked for (620 m) that the condensed size cannot
  > give; 550 m is the most it can.
- **Redundancy:** the port also connects by land (the neck) and the eastern shore by the
  arterial ring, so no timed mission can be softlocked by one crash. Only the airport spur
  dead-ends — deliberately, per v1.

---

## 5. Roads

Four tiers, unchanged dimensions from v1/v2 (they are real Japanese figures):
**T1** 22 m elevated deck +12 m · **T2** 27 m arterial · **T3** 14 m local @168 m ·
**T4** 4.5 m *roji* @45–60 m, core only.

### The white lanes are authored, not a clipped lattice

Earlier passes generated T2 as district-seam lines with random doglegs and then clipped them
to the coast. That produced stubs — arterials that dead-ended in mid-air wherever the clip cut
them. **The rule now: every arterial is end-to-end and terminates on the ring or on another
arterial.** Nothing dead-ends except the two spurs that are supposed to.

| arterial | length | runs |
|:--|--:|:--|
| **`RING`** — coastal ring, **closed** | **4,987 m** | the whole coastline at a 62 m inset. Every radial ends on it; it is also v1's scenic coast drive. North arc doubles as the 7 m mountain-foot road. |
| `Chuo-dori` | 1,409 m | port → Neon A → castle → residential → farmland → mountain foot |
| `Rinkai-dori` | 1,641 m | west coast → Neon C → Neon A → **arch bridge** → Neon B → east coast |
| `Yamate-dori` | 1,615 m | residential cross-street, coast to coast |
| `Nogyo-michi` | 1,390 m | farmland cross-street, bends around the lagoon |
| `Hama-dori` | 1,392 m | coastal station → Neon B → **bay bridge** → port |
| `Nishi-dori` | 826 m | ring → Neon C → shrine → tunnel approach |
| `Port road` | 368 m | distributor on the reclaimed peninsula |

Two things fall out of this that are worth naming. **Both hero bridges now carry a trunk
arterial** — `Rinkai-dori` crosses the arch bridge, `Hama-dori` crosses the bay bridge — so
neither is decorative; cutting one genuinely re-routes traffic. And the **ring is the answer
to "is it end-to-end on each edge"**: yes, and it is the thing that makes it true, because
every other road can terminate on it instead of on the shoreline.

Spacing in the dense band lands near 250 m — the low end of the real 300–600 m range, which is
correct for a city centre and the one dimension the smaller world forces.

| T1 route | length | role |
|:--|--:|:--|
| `LOOP` — closed, wraps the castle + Neon A | **3,331 m** | flagship circuit |
| `AIRPORT_RAMP` → airport bridge | 335 m + bridge | a **ramp off the loop beside S3**, not a second route |
| `WESTRAD` → tunnel portal | ~470 m | mountain approach |
| `PORTSPUR` | ~370 m | dead-ends at the container port |
| `TOUGE` (T2, at grade) | 795 m | **+220 m of climb**, 4 hairpin pairs, 11 m minimum radius, guardrail on the valley side only |

The touge stops at the pass. The +380 peak is scenery — driving it would force an 18 % wall.

### Flagship lap — 3,331 m, ~90 s

| sector | asks for |
|:--|:--|
| **S1** moat straight | start/finish, flat out along the castle water |
| **S2** electric-town esses | rhythm, walls close, river on the right |
| **S3** port hairpin | hardest braking point — natural checkpoint |
| **S4** bayshore sweep | one long committed left, tower on the left |
| **S5** hillside climb | blind crest onto the spur |
| **S6** spur descent | downhill commitment back into the moat straight |

Also free from the same network: a **long lap** out over the airport bridge and back, the
**520 m drag strip**, and a **hillclimb** from the port to the pass (0 → +220 m).

---

## 6. Budget

### Building population (measured off the plate, not estimated)

| type | footprint | floors | instances | notes |
|:--|:--|:--|--:|:--|
| Zakkyo shop-office | 6 × 12 m | 3–8 | **1,174** | one kit, three centres, 84 m blocks |
| Anchor: store / office / station | 24 × 34 m | 6–12 | **9** | one per seven blocks — the things you navigate by |
| Danchi slab | 12 × 55 m | 5 | **27** | all on **one 18° bearing** that ignores the street grid |
| Detached house | 7 × 9 m | 2 | **692** | 0.5–1 m side gaps, one car slot |
| Farmhouse + barn | 12 × 8 m | 1–2 | **77** | on the dune ridges, never mid-paddy |
| Shed / tank | 40 × 70 m · r9 | 1 | **47** | reclaimed port |
| Hangar / terminal | 26 × 34 m | 1–2 | **34** | airport island |
| | | | **2,060** | |

27 danchi slabs looks small next to 692 houses until you scale it: a 5-floor 12 × 55 m slab is
roughly **50 dwellings**, so the estates hold ~1,350 homes against the detached band's ~700.
The slabs are the population; the houses are the texture. That ratio is correct for a Japanese
regional city, and it is why the danchi bearing matters so much visually — a handful of very
large objects, all pointing the same wrong way relative to the streets.

| family | unique meshes | instances |
|:--|--:|--:|
| Zakkyo shop-office (all three neon centres share it) | 14 | 1,290 |
| Detached house + danchi slab | 12 | 719 |
| Farmhouse + outbuilding + barn | 6 | 55 |
| Warehouse / shed / tank / hangar | 12 | 71 |
| **recycled kit total** | **44** | **2,135** |
| Hero: arch bridge, bay bridge, airport bridge, castle+keep, tower, temple, 3× shrine kit, terminal, stations, tunnel portal, torii, lanterns | **~52** | ~40 |

**~96 unique meshes, 2,060 building instances** — under GTA III on both axes, and the three
hero assets already in the repo (`PLATEAU_TokyoTower`, `PLATEAU_RainbowBridge`,
`PLATEAU_HanedaTerminal` .blend) cover the tower, the long bridge and the terminal.

Everything repeated is MultiMesh and not counted here: vending machines, poles, guardrails,
signage quads, pine trees, paddy props, containers, and **crowd** — which remains the single
best place to spend surplus, per v1 §2.

---

## 7. Build order

1. `world_grid.GRID_N` **6 → 4**; replace `MAP` with the 4 rows below.
2. Terrain and coastline first — the massif and spur at 1:1 slope, the dune ridges as gentle
   linear rises, sea at Z 0.
3. Roads before blocks; blocks are the leftover polygons. Feed the node/edge graph to
   `road_kit_authoring` (`ops_placement` / `ops_segment` / `ops_intersection`).
4. Extrude footprints by floor count from the kit; never model a block by hand.
5. One collection per zone so collections match streaming districts from day one; hand work
   lives in `MANUAL`, which survives district regeneration.
6. The **airport bridge** and the **arch bridge** are the two hero assets. Everything else repeats.

```
        gx0        gx1        gx2        gx3
gy3 |   void[27]   mtn[87]    rural[82]  rural[26]
gy2 |   mtn[72]    resid[100] resid[100] rural[72]
gy1 |   city[58]   CITY[100]  city[88]   rural[47]
gy0 |   void[1]    harbor[61] harbor[32] harbor[53]

[n] = measured land fraction of that 504 m cell.  14 BUILT of 16.
```

---

## 8. Open decisions

- **Era.** Still unpicked, still halves the asset list. The Niigata reference points at
  **1990s–2000s regional-city Japan** rather than neon-future Tokyo — cheaper and more
  distinctive. Lock it before the signage atlas.
- ~~Danchi bearing~~ — **decided: 18°**, locked in `island_v3_geom.DANCHI_BEARING` and drawn
  on the plate. Change it there if it reads wrong on site; do not vary it per estate.
- **Dune-ridge count.** The plate draws 9 ridges; 5–6 wider ones may read better at driving
  speed. Decide by walking one district, not on paper.
- **Whether Neon C earns its own kit.** It currently reuses A's. A distinct low-rise
  hillside kit (4–5 meshes) would make the three centres unmistakable — the cheapest
  available upgrade if the budget has room.
- **Archive v1 and v2** once this is accepted, so the repo has exactly one live island plan.

*Plates generated by `tools/island_v3_plates.py` from `tools/island_v3_geom.py` — edit the
geometry module, not the SVG. Landmark mesh sources: Project PLATEAU (MLIT), CC BY 4.0.*
