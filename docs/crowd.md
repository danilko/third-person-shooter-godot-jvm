# crowd

Moved out of `CLAUDE.md` verbatim on 2026-10-09 (PLAN.md 0.5 / F12). Sections:

- The ambient crowd has two tiers, and the far one has no scripts at all (PLAN.md 3.6d, 2026-09-19)
- The island is populated: the crowd is DERIVED from the same footways the buildings front (PLAN.md 3.6d, 2026-09-20)
- A LIGHT PED IS ONE SURFACE: the crowd's LOD body (2026-09-22)
- Kerb damage was street-tree planters; crowd shots land like AI shots (2026-10-06, user-reported)
- The crowd: a GPU-animated far tier, promotion on need, six bodies, a holster, a female walk (2026-09-27, user-asked)
- The crowd makes room for a fight: combat load, walker shedding, panic thinning (PLAN.md 2.3 step 8, 2026-10-16)

---

## The ambient crowd has two tiers, and the far one has no scripts at all (PLAN.md 3.6d, 2026-09-19)

`world.PedCrowd` is the GTA pedestrian LOD. A `SpawnConfig` with `behavior = "sidewalk"` no longer spawns its
count as bodies: ZoneManager fills ONE `PedCrowd` node with that many **script-free** peds (the imported
character scene -- skeleton, meshes, an `AnimationPlayer`, and nothing else), the crowd writes their transforms,
and a ped that walks within reach of a player is **promoted** into the ordinary pooled `AICharacter` this class
has always spawned. `ZoneManager.lightCrowd` (`@Export`, on) turns the whole thing off, which is the old
behaviour and the gate's control.

- **Why a tier and not another flag on the body.** D2 already skips a distant AI's FSM and its AnimationTree
  writes, and W-era work made a far sidewalk walker GLIDE (its controller moves it directly, MovementController
  stands down). Measured, a glided walker STILL cost ~0.06 ms per physics tick, because what is left is not its
  behaviour: a `Character` is ~10 JVM-scripted nodes and the engine calls into the JVM for each of them every
  tick. No flag on those nodes removes that. **Only having no scripted nodes does.**
- **What it measures** (`probe_city_perf.gd --crowd --light-crowd=0|1`, display, downtown street level, this dev
  PC; the zone is centred on the player, so the full tier is the share genuinely within 80 m):

  | pedestrians asked | with the far tier | control (every one a full body) |
  |---|---|---|
  | 150 | **p50 12.72 / p95 15.97 ms**, 31 full + 119 light | p50 50.04 / p95 61.71 ms, 150 full |
  | 300 | **p50 33.07 / p95 44.16 ms**, 62 full + 238 light | p50 201.21 / p95 210.62 ms, 300 full |

  **The frame improves far more than the tick does** (150 peds: physics-process 13.01 -> 9.53 ms, frame
  50.0 -> 12.7) and that is the point: past ~16.7 ms per tick Godot runs up to 8 catch-up ticks in one frame, so
  crossing the threshold multiplies the frame. The far tier keeps the tick under it and the spiral never starts.
- **It removes the SCRIPT cost, not the draw cost.** Draw calls at 150 peds were 1079 with the tier and 1093
  without -- a light ped still draws its nine meshes. Cutting that is a mesh-LOD or impostor job, which is where
  the remaining 300-ped cost lives, along with the ~80 bodies that are legitimately near the player.
- **Promotion is ZoneManager's, always.** The crowd only asks (`promoteSidewalkPed`), so there is still exactly
  ONE place an interactive body is pooled, armed, positioned and announced. A refusal (the zone unloaded
  mid-walk, the pool empty) is not an error -- the ped keeps walking. `demoteDistance` (100 m against the 80 m
  promote) is the Zone load/unload hysteresis rule: with one threshold a body standing on it promotes and demotes
  every tick, and without demotion at all, walking the length of a district promotes the whole crowd and keeps it.
- **The boundary is D2's own ACTIVE distance (80 m)**, not a new number: "is a player near" already had one owner.
- **It is LOCAL to each peer and never replicated**, the rule 3.11b set for the knocked-down poles. Each peer
  walks its own crowd; nothing 100 m away can be interacted with, and what IS interactive is a host-authoritative
  `AICharacter` already on the wire. **Accepted divergence:** a client may not spawn AI, so it does not promote --
  inside `promoteDistance` it HIDES its own light peds and shows the host's replicated walkers instead, and at the
  boundary the two populations are not the same people.
- Two implementation rules that are easy to get wrong: promotions are collected and applied AFTER the walk loop
  (removing mid-loop shifts every later ped into a different update group, so the stagger quietly stops being a
  partition), and the AI scene is **warmed at zone-build time** -- otherwise the first promotion runs a blocking
  `GD.load` inside a physics tick while the zone's own geometry is still parsing on a worker thread.
- Peds are advanced in `updateGroups` (4) round-robin groups, one group per frame moved by the whole group's
  worth of time, and each writes ONE transform; beyond `animateDistance` (60 m) its `AnimationPlayer` is paused.
  Each starts its walk clip at its own random offset, or a crowd marches in step.
- Gate **`tools/godot/probe_ped_crowd.gd`** 12/12 on World.tscn with the real ZoneManager and sidewalk data: the
  zone fills its crowd and adds nothing to the `characters` group, 120 of 120 peds walk (683 m in 4 s) at footway
  height, a player standing in them promotes 10 into real bodies carrying a `SidewalkWalkerController` with
  nobody lost in the swap, walking away hands every one back, and the crowd goes with its marker.
  `-- --control` fails exactly 7: 120 full bodies spawned out of reach and never handed back.
- **Not done: the island has no pedestrians yet.** Nothing in `World.tscn` carries a sidewalk `SpawnConfig`; the
  population belongs in `tools/island_buildings.py`'s derived `BuildingZones` block, beside the buildings whose
  footways the crowd walks.

## The island is populated: the crowd is DERIVED from the same footways the buildings front (PLAN.md 3.6d, 2026-09-20)

3.6d built the two-tier crowd and nothing in `World.tscn` carried a sidewalk `SpawnConfig`, so the island's
streets were empty. The population is now derived by **`tools/island_buildings.py`** — the tool that already owns
the footway record (`IslandSidewalks.json`) and the 252 m cell grid the buildings stream on — and written as a
**`PedZones`** block of geometry-less `ZoneMarker`s beside `BuildingZones`, by the same `write` step, with the
same `--check`.

- **A crowd's size is a MEASUREMENT of its cell, not a number typed per zone**: the footway metres inside the
  cell times `PED_DENSITY` for its region (peds per 100 m: downtown 2.0, city 1.2, residential 0.8, suburb 0.6,
  harbour 0.4, farm 0.3, outside every region 0.5), capped at `PED_MAX` 40. The length is measured over the
  cell's **inscribed circle**, because that is the footway `ZoneManager.buildPedCrowd` can actually pick from
  (`Sidewalks.randomNear(centre, size/2)`) — measuring the square would ask for peds the placement cannot seat,
  and the zone would quietly come up short of its count.
- **The radii are the thing the crowd's cost is actually paid on.** `PED_LOAD` 300 m is just over the 252 m cell
  pitch, so the four orthogonal neighbours stream too and a crowd is already walking before it comes into view;
  `PED_UNLOAD` 420 keeps the Zone rule (unload > load > halfExtent). Measured: **511 pedestrians over 79 zones,
  104 in range at once at worst (downtown), 22 typically** — inside the 150 that `probe_city_perf.gd --crowd`
  measured at p50 12.7 ms. `island_buildings.py peds` prints that table; raise the density against the perf
  probe, never by eye.
- **The faction is `neutral`, not `civilian`.** `neutral` is never hostile whatever faction table is live
  (`FactionRules`), which is what an ambient pedestrian must be; `civilian` is hostile to `player` by the
  INHERENT default unless a preset table is applied, and `World.tscn` applies none.
- **Measured cost on the island's own streaming gate: none.** `probe_island_zones.gd` gained `--no-peds` /
  `--no-buildings`, which free those derived blocks so a drive's frame time can be ATTRIBUTED rather than
  guessed at. Its 30 m/s drive over the whole 47-cell tour reads **p50 13.83 ms / p99 20.84 ms with the crowd
  and p50 13.83 / p99 20.84 without it** — identical. (The first attempt at that control measured nothing,
  because the flag name was DERIVED from the node name and came out `--no-ped`; a flag table beats a clever
  derivation, and a control that silently does not apply reads exactly like a change that costs nothing.)
  **That p50 is itself a pre-existing regression against the 1.54 ms CLAUDE.md records for 3.10**, from before
  the island had a city; `--no-buildings` is the one command that attributes it.
- Gate **`tools/godot/probe_island_peds.gd`** 12/12 on the real World.tscn and the real ZoneManager (it asserts
  the SHIPPED placement; `probe_ped_crowd.gd` still asserts the mechanism on a zone it builds itself): the block
  exists and every crowd is one unarmed group inside the cap; standing in the busiest cell there are 98 light
  peds and 6 promoted, 28 within 150 m and 60 more between 150 and 300 m, 104 in range against the 150 budget;
  **every ped stands on a derived footway (0 off, worst 0.02 m of height)**; all 98 walk; every promoted body is
  neutral; and the crowd left behind is unloaded with its zone. `-- --control` puts the load radius back under
  the cell pitch (only the cell you stand in ever streams) and fails exactly the "the streets ahead are already
  populated" check, 60 -> 0.

## A LIGHT PED IS ONE SURFACE: the crowd's LOD body (2026-09-22)

3.6d built the two-tier crowd and pointed its far tier at the PLAYABLE body, which is **3
`MeshInstance3D` but 17 surfaces with 17 materials** -- ~17 draws per light ped, with ~100 in range
downtown, i.e. ~1 100 of the station quarter's ~4 000 draws. `blender/tools/build_ped_body.py` writes
`assets/characters/<body>/<body>_ped.glb`: **one skinned mesh, one material, one atlas, two clips**
(48.8 MB -> 2.0 MB), and `PedCrowd.PED_SCENE` points at `shino_ped.tscn`.

- **Measured, the whole reason it exists** (`probe_walk_perf.gd --legs=walk_station`, display, this dev
  PC): the station walk went **p50 15.4 / p95 20.8 ms -> p50 10.84 / p95 15.72**, and the run's own
  verdict flipped to `RESULT PASS worst leg p95 15.72 ms (budget 16.7)`. That quarter was the ONLY
  place on the island over 16.7 ms p95.
- **It is built FROM THE SHIPPED `.glb`, not the `.blend`.** The game plays the export, so the LOD is
  derived from the same artefact the full body is and can never disagree with what is on screen; it
  also needs to know nothing about the authoring file (Auto-Rig Pro, the control rig, the linked weapon
  libraries, the 173 authored actions). One tool serves every body, the way `export_character.py`
  derives its output from the file it was handed.
- **THE PED'S MATERIAL IS THE BODY'S MATERIAL WITH THE ATLAS IN IT**, cloned, never a fresh Principled
  one. Every shino surface is `KHR_materials_unlit` -- a VRoid/VRM import artefact that survives the
  export, so **the shipped character body is shadeless and ignores the sun, the night and every street
  lamp** (worth knowing on its own; it is the body export's business, P6 / 3.14, not the crowd's). A LIT
  ped beside an UNLIT player would change brightness at the moment it promotes, 80 m from the camera.
  Cloning makes the ped match whatever that body is, with nothing here to keep in step.
- **What it drops, and the measurement that allows it.** The eight sub-pixel face surfaces (iris, white,
  highlight, extra, eyelash, eyeline, brow, mouth -- 1 808 tris and 8 of the 17 textures) cannot be
  resolved at the nearest distance this tier is ever drawn: at `promoteDistance` (80 m) a 1.65 m body is
  **~14 px tall** on a 1080p screen and a head is ~2 px. A client, which may not promote, HIDES its light
  peds inside that ring rather than drawing them close, so no path puts this body in front of a camera
  at conversational range. Everything carrying the SILHOUETTE is kept, all three hair surfaces included
  -- hair is 53 % of the triangles and is alpha cut-out, so dropping its alpha would make it a block.
- **The atlas's one known limit, stated rather than hidden:** each cell is grown by a gutter of its own
  EDGE pixels (16 px), so the first four mip levels cannot sample a neighbour; past that -- once the whole
  ped is a few tens of pixels -- cells do average into each other, a slight colour shift on a body that is
  already a smudge. A per-cell mip chain cannot cross glTF, and the alternative is the 17 draws this
  removes.

**Four traps, each of which cost a build:**
- **A `baseColorFactor` is not in the texture.** VRoid tints a GREYSCALE hair texture with a constant
  (shino's is a dark blue 0.098/0.141/0.220 over a white mask), so the first atlas -- which copied the
  textures alone -- would have put a **white-haired** ped in the crowd. Each cell now bakes its own
  material's factor in, sRGB texel x linear factor, the way a renderer multiplies them.
- **Blender's glTF IMPORTER builds an `Icosphere`** as the display shape for all 158 bones and leaves it
  in the scene (in a `glTF_not_exported` collection), so a filter on `type == 'MESH'` silently joins a
  bone widget into the body. Only what the armature DEFORMS may enter -- `export_character
  .deform_armature`'s rule from the other side.
- **Since Blender 4.2 the glTF exporter derives `alphaMode` from the NODE TREE, not from
  `blend_method`** (`search_node_tree.gather_alpha_info` / `detect_alpha_clip`). Setting
  `blend_method = 'CLIP'` exports as **BLEND** and says nothing; what it looks for is a compare node on
  the alpha (`GREATER_THAN` -> MASK with that cutoff). A MASK donor already carries such a chain and a
  BLEND one wires the alpha straight through, so the chain is cut back to the image and re-made.
- **Blender hands back a FRESH Python wrapper for an RNA socket on every access**, so `l.from_socket is
  sock` is False even for one socket -- match the node and the socket NAME instead. This read as "the
  donor material does not route its alpha anywhere".

Gate **`tools/godot/probe_ped_body.gd`** (19/19; `-- --control` measures the FULL body and fails exactly
the 4 surface/material checks). Every failure here is silent in game -- a scene that quietly kept 17
surfaces looks identical and costs 17x, one whose clips were renamed stands still (`AnimationPlayer.play`
of a missing clip is a no-op), one whose skeleton lost a bone plays the walk on a body that does not move
-- so each is asserted, clip LOOPING included. `probe_ped_crowd` 12/12 and `probe_island_peds` 12/12 are
unchanged on the new body.

**An atlas is a PICTURE question and no structural check can see it** -- a cell mapped to the wrong face, or
flipped, passes every assertion above. `tools/godot/shot_ped_body.gd` (NEEDS A DISPLAY) puts the full body
and the LOD side by side in one frame at each distance. Looked at: at **2.5 m**, 32x nearer than this tier
is ever drawn, the two are the same body -- hair colour, uniform, ribbon, socks, shoes and skin all match --
and the ONLY difference is the face, which is the eight surfaces that were deliberately dropped (the eyes
read as flat ovals, no brows or mouth). At **80 m**, the nearest a light ped is drawn, they are
indistinguishable and the mip bleeding is not visible.


## Kerb damage was street-tree planters; crowd shots land like AI shots (2026-10-06, user-reported)

- **"The kerb damages my car sometimes, not other times."** Measured (`probe_road_launch.gd` with `OW_CRASH_TRACE=1`):
  the kerb never scored a crash; every damaging contact was `FURN_props-prop`, the PLANTER every street tree stands in
  (3.18m). The tree stood `tree_kerb_gap` 0.90 m in and the planter is 0.898 m across-half, so its face was 2 mm from
  the kerb line: a car with its tyre on the kerb scraped a 0.6 m concrete box every 18 m. `point_furniture
  .tree_kerb_offset` is the one owner now (planter face `planter_kerb_gap` 0.3 m behind the kerb, tree centre 1.20 m),
  and `island_buildings.furniture_strip` reads it (the walk line moves on 3 m footways). DebugWorld, kerb line at 12 and
  22 m/s: 17.6 / 72.4 hp -> 0. Driving fully onto the pavement into a tree is still a crash, on purpose. A raised median
  measured 0 damage with the wheels on it (naka_hondori, 244 m).
- **The rest of the "kerb damage" was the SUSPENSION: a bump stop was missing** (user, same day: "near a kerb or a
  median, at any speed, occasionally huge damage"; their trace: `[crash] ... hit nishi_dori__5_road-road-noped: dv
  53.28 m/s`). Reproduced on the island (`probe_road_launch.gd` on `nishi_dori__4__x1_F0` at 55 m/s: 311, 141+249 and
  295 hp): the contact is the vertical 0.15 m face of a RAISED MEDIAN's cap at a junction mouth, struck by the HULL
  (normal `(-0.09, 0.09, 0.99)`, at kerb-top height, all four wheels on the pad). SPC1's springs (14 000 N/m a wheel)
  already sag ~0.23 m of their 0.35 m at rest and had no end of travel, so ~2 g of load (a hard turn, a dip) pushed the
  hull floor from 0.32 m to ~0.09 m -- under kerb height -- and its vertical edge stopped the car dead. Which speed and
  which kerb is a matter of the load on that corner at that instant, so it never repeated on demand.
  `VehicleConfig.bumpStopTravel` (0.06 m past the static sag) / `bumpStopRate` (12 x the spring rate) add a
  progressive bump stop in `VehicleWheel.bumpStopForce`, both suspension paths. After: the same three cases 0 damage;
  `--bump-stop=0` (new probe flag) is the control and crashes again (205 hp). `probe_component_car` (SPC1, CRT1, KEC1),
  `probe_vehicle_views`, `probe_car_push`, `probe_dead_driver`, `probe_driveby_aim`, the launch gate PASS. The gate's
  `w_ring__x2__x1_F1` case moved -3 -> -2 m and the probe now reports a bounce off street furniture
  (`FURN_props-prop`) as a FURNITURE CRASH, not a launch: since DebugRoads has footways, -3 m is ON the pavement.
- **`OW_CRASH_TRACE=1`** in the environment prints `[crash] <car> hit <collider path>: dv ...` for every scored crash of
  a PLAYER-driven car (`Vehicle.CRASH_TRACE`, `VehicleDamageModel.flushCrash`). Ask for that line before guessing.
- **Shooting the light crowd** (user: "even a shotgun or a powerful handgun after 3-4 shots cannot knock one down").
  Three defects, each measured:
  * **The sight leg passed through the ped.** In third person the shot is aimed at what the CAMERA ray hits and
    traced from the muzzle; a light ped has no collider, so the camera ray ended on the wall behind it and the muzzle
    leg converged there, passing up to ~0.3 m beside the person under the crosshair. `WeaponItem.resolveSightPoint`
    now stops the sight at a crowd ped (`PedCrowd.shoot`).
  * **The promoting shot landed at x1 on the capsule** (no headshot ever killed a crowd ped outright). It now lands on
    the hitbox at the height it struck (`PedCrowd.hitPart` / `hitHeightFraction`): REV1 to the head kills in one.
  * **A shotgun counted one pellet**: the first pellet promoted the ped and the other seven found nobody.
    `FirearmItem.resolvePellets` traces every pellet first, promotes each ped once, then lands every pellet that
    reached it. One SHG1 pull at 5.6 m: 8 pellets on the body, a kill.
  * The hit cylinder is each body's own height (`<body>.body.json` crown + 4 cm, `PedCrowd.Variant.height`), not one
    1.62 m for bodies 1.41-1.91 m tall. `ped_heights_now` is its readout.
  * **Confirmed in play by the user** (same day): every crowd member near them now takes damage. A crowded street
    can still put a passer-by between the gun and the crosshair (the muzzle sits beside the camera), which is the
    ordinary third-person rule. **`OW_SHOT_TRACE=1`** prints `[shot] <collider path> at <point> -> <body> (hp N)` for
    every bullet a player lands (`ImpactManager.SHOT_TRACE`); `tools/godot/probe_crowd_scene.gd` is the diagnosis stand
    (the island crowd, shooting the promoted walkers near the player).
  Gate **`tools/godot/probe_crowd_hits.gd`** (World.tscn, light peds frozen in place, a real Player firing through
  Input): head kill, chest hit alive, SHG1 multi-pellet -- PASS. Unchanged: `probe_hit_marker`, `probe_self_hit`,
  `probe_sniper_hits`, `probe_ped_crowd`, `probe_auto_reload`, `./gradlew test`.

## The crowd: a GPU-animated far tier, promotion on need, six bodies, a holster, a female walk (2026-09-27, user-asked)

Supersedes the section above on how the far tier is DRAWN (its LOD-body rules still apply: the bake reads that body).

**What was measured first** (bare stand, this PC): a skinned light ped cost ~26 us of CPU a frame for its
AnimationPlayer + skinning, even hidden (600 walking: 18.9 ms, the GPU under 1 ms). The old tier was also FROZEN:
`animateDistance` (60 m) < `promoteDistance` (80 m), so a light ped never animated. And a promotion to a full
`AICharacter` (125 nodes) costs 3-4 ms on the main thread with no per-frame cap -- driving into downtown crossed
dozens of 80 m rings in a few frames. Navigation was NOT the crowd's cost: the walkers follow the footway polyline
and their `NavigationAgent3D` is idle.

**The far tier is a vertex-animation texture.** `tools/godot/bake_ped_vat.gd -- --body=<b>` bakes a body's light-ped
mesh (`<b>_ped.tscn`, simplified by Godot's own LOD generator to ~5k vertices; `BODY_VERTS` overrides -- Fumiriya's
trousers tore below 8k) under the SHARED library clips of its GAIT (idle / walk / run / cower / phone / talk, 15 fps)
into `<b>_vat_mesh.res` + `<b>_vat_pos.res` (RGBAH, one texel per vertex, one row per frame) + `<b>_vat.json`.
`assets/characters/crowd/ped_vat.gdshader` plays it by `VERTEX_ID` (unshaded, alpha scissor, like the VRoid body).
`world.PedCrowd` is now plain Java state per ped and ONE `MultiMesh` per body type, one `setBuffer` a frame.
`tools/godot/bench_crowd.gd` (display): 150 / 600 / 2000 peds = 4.76 / 18.44 / 61.2 ms skinned against
**0.45 / 0.57 / 1.48 ms**, one draw call. Island walk (`probe_walk_perf.gd`): the crowd now costs ~0.6 ms downtown
and ~1.2 ms at the station (`--no-peds` the control). A ped stops now and then (idle/phone/talk), keeps its own pace
(+-10%, stride matched) and height (+-4%).

**Promotion is a decision** (PLAN.md 3.32): a ped becomes a real body only within `promoteDistance` 15 m, when aimed
at, when a FIGHTER is scared, or when SHOT (`PedCrowd.shoot` -- an upright cylinder per ped, engine-free
`world.CrowdShot` + `PedCrowdShotTest`; `FirearmItem.resolvePellets` asks the crowds on the authoritative path and the
hit ped is promoted at once, budget ignored, damage through `ImpactManager.processHit`). One promotion a frame,
nearest first; `ZoneManager.walkerBudget` 8, `fighterBudget` 6 (budget 12 / ring 25 m until 2026-10-09: measured with
`probe_walk_perf --walker-budget= --promote-ring=`, 8 + 15 m took downtown GPU p95 5.2-5.9 -> 3.7 ms and station
4.8 -> 4.6; budget 6 bought nothing over 8; a shadow LOD on promoted bodies bought nothing once the ring was 15 m); a body is held 10 s after promotion and while hurt
in the last 20 s. The promoted character wears the SAME body (`characterVisuals` = `CharacterVisuals_<Body>.tscn`).
**Temperament** from each ped's roll: ~83% flee, 12% cower (`crouch_idle`), 5% fight -- a fighter keeps the ordinary
AIController brain, is armed from PIS1 / MEW1 / fists, and turns to `ZoneManager.FIGHTER_FACTION` "vigilante".
Accepted divergence: a client hides its peds inside 15 m and cannot promote; the crowd stays local per peer.

**Six bodies**: Shino, Fumiriya, and the imported Shibu, Victoria, Bibi, Vita (all female; the only male body is
Fumiriya, weighted 3 in `character_gaits.json` `crowd_weights`). Each went `import_vrm_body.py` ->
`measure_body.gd` (BODIES) -> `build_character_visuals.gd` -> `build_ped_body.py --no-clips --keep-face` ->
`bake_ped_vat.gd`. Licence in CREDITS.md.

**A HOLSTER, not a raised state** (user decision). Hands EMPTY (`WeaponController.isHolstered`, the fist slot's second
state; a body starts holstered): the walk's own arms (WeaponBlend eased to 0 over 0.15 s), no shoulder aim / stock
mount / torso layer / aim branch, and fire does nothing -- the same in FPS and TPS. **Controls (2026-10-06):** H
(`holster`) toggles it -- a weapon in hand is put away and remembered, empty hands bring that weapon back (the fists if
none); any slot key draws that slot at once (0 = the fists). Holstered, `PlayerController` keeps combat and the scope
OFF whatever aim / fire are doing, so nothing aims and nothing alarms a bystander; the weapon panel shows NO weapon
(not the fist) and no inventory row is lit. An AI holsters its fists when not fighting. The CHEST look-at and `NeckFront` still follow combat (the FPS camera rides the neck: keyed on the hands,
the view lagged a crouch 0.161 m against `probe_fps_camera`'s 0.12). Replicated as bit 12 of the snapshot flags word.
Drawing posts `StimulusManager.Type.WEAPON_DRAWN` (10 m fists, 30 m a weapon): the crowd and the promoted walkers
(`SidewalkWalkerController` now runs from gunshots, blasts and drawn weapons) react. Both listen by IDENTITY, not by
timestamp (the stimulus clock advances in _process, so two physics ticks can repeat a timestamp).

**One walk, two gaits** (user, 2026-09-27/28). The walks are ORDINARY CLIPS on the rig in `shino.blend`: `male_upright_walk` / `female_upright_walk` (the NORMAL walk, hands empty; the tree's clip is `upright_walk`, formerly `upright_walk_relaxed`) and `male_/female_upright_walk_forward/_forward_left/_forward_right/_back` (the ring with a weapon up). `derive_gait.py` SEEDED them once from the source walk and never overwrites one (`--force=<clip>` re-seeds); edit them on the rig like any clip. Neither sex plays the source `upright_walk_forward` ring (it drops the hips 20.5 deg with no pelvic turn and carries the elbows bent 41 deg, arms swinging only behind: it read feminine on Fumiriya). Male: drop -> 9.2 deg, 1 deg pelvic turn, feet 9.3 -> 12.6 cm (each pushed out on its OWN side: pushing away from the midline flipped when a diagonal's planted foot crossed it), arms nearly straight, 13 deg out, swinging from the shoulder with the collarbone following. Female: as below, plus softer arms in the normal walk. The chest is held exactly in every weapon-up clip, so aim is identical. How an artist makes a body male or female: `blender/SKELETON_CONTRACT.md` section 11. HISTORIC (the first version): `blender/tools/derive_gait.py` writes the FEMALE copies into `shino.blend` as
`f_<clip>` (forward, the two forward diagonals, back): planted feet 46% narrower (9.3 -> 5.0 cm), a weight shift over
the standing foot (4.4 cm), hip drop x1.15, and `spine_03`'s world transform held exactly (0.00 deg, <= 2 mm), so aim
is untouched. Plus `f_upright_walk_relaxed` (chest counter-roll 2.5 deg, a wider arm swing) that only the RELAXED
branch plays: `RelaxedTransition` on the Upright stance input (`tools/patch_tree_relaxed.py`), Relaxed out of combat
(idle / `upright_walk_relaxed` / run by movement id), Raised otherwise. `character_gaits.json` maps base names to the
gait's clips; `build_character_anims.gd` writes `character_anims.res` (male, with `upright_walk_relaxed` aliased to
the walk) and `character_anims_f.res`; a body's gait picks its library in `build_character_visuals.gd`.
`upright_walk_casual` / `_formal` / `_carry` are deleted (naming table `delete`, retarget rows removed).

**Plates by relevance** (`NameplateTarget.isNameplateRelevant`): another Player, a story character, a hostile in
combat, anyone hurt in the last 10 s, a car whose driver is relevant or that was hit. A hidden plate's SubViewport
is set to DISABLED. Gate `tools/godot/probe_nameplate_relevance.gd` 6/6 (`--control` fails 2).

**The Blender clip preview** (`game_export_ui.py`): shino.blend opens with the ARP rig driving the body, and the rig
had been saved on `ARP_upright_aim_rifle-loop` -- so every clip showed the aim in the upper body. Picking a clip now
loads it on the rig, the panel says what the rig shows, and "Preview as the game plays it" switches the rig off and
plays the GAME clip (never saved or exported that way).

**No tint** (user): clothing / car colour variety is dropped -- no extra materials or masks; the shader's COLOR tint
stays at strength 0. **Open bugs** (PLAN.md zb1/zb2): a pedestrian under attack sometimes not promoted or seemingly
duplicated; promoted walkers stuck face to face.

**Gates**: `probe_ped_crowd` 15/15 (fighters = budget, a shot at 70 m promotes, the 10 s hold), `probe_ped_panic`,
`probe_melee` (holster: starts holstered, 0 draws), `probe_fps_camera`, `probe_nameplate_relevance`, `SnapshotFlagsTest`
(bit 12), `PedCrowdShotTest`, `derive_gait.py --check`-style asserts on every run, AimDebugAuto 40/40,
`probe_weapon_fit`, `check_character_anim` (gait aliases understood). **Not green, not this work:**
`probe_island_peds` segfaults on World after a teleport, with the light crowd switched OFF too (headless streaming,
the world mid-rebuild); `probe_recoil_kick`'s ASR1 checks fail by a hair per body (rifle path, untouched here).



## The crowd makes room for a fight: combat load, walker shedding, panic thinning (PLAN.md 2.3 step 8, 2026-10-16)

User, 2026-10-16: "can it automatically reduce the peds when more engagement comes? the crowd seems to run around in
big chunks ... in GTA they just disappear by themselves, but not fully". Three parts, each with its own switch:

- **One combat load.** `ZoneManager.setCombatLoad(source, bodies)` beside the dispatch's `setEnforcementLoad`: the
  light combatant tier reports its promoted bodies (`"light"`), each `Encounter` its live full members
  (`"encounter:<path>"`), each 0 when it goes. `combatBodies()` (dispatch + every source) is what the existing
  balancing subtracts: walkers `8 - n/2` (floor 2), fighters `6 - n/3` (floor 1), traffic `budget - 2 x cars - n/2`.
  Before, a horde or a placed fight did not thin the street at all. `combatLoadNow()` reads it.
- **Shedding** (`ZoneManager.shedWalkers`, on). The reduced budget used to stop only NEW promotions; walkers promoted
  before the fight kept their bodies until they walked out of reach. Now `maintainPedestrians` hands back the walkers
  over the budget: farthest first, at most 2 a pass, only ones not hurt in 20 s, past `shedMinDistance` (20 m) from
  every player and out of this peer's camera view. Fighters are never shed.
- **Panic thinning** (`PedCrowd.panicThinning`, on). A FLEEING light ped that is out of this peer's camera view and
  more than `thinMinDistance` (30 m) from what scared it goes INSIDE: hidden, not promotable, deaf, for
  `insideSeconds` (20 s), then walks back onto its shared schedule -- and only when it is out of view (in view it
  waits 2 s more), so nobody pops in or out in front of the camera. Never more than `thinMaxShare` (70 %) of a crowd
  is inside at once: the street keeps people. A fighter never goes inside (it turns to fight; probe_ped_crowd's
  "exactly the fighter budget" failed 5 of 6 until it was excluded). The crowd is local per peer, so each peer thins
  by its own camera (accepted: the scare itself already was local).

Gate **`tools/godot/probe_crowd_thinning.gd`** (World.tscn, a 120-ped zone downtown; 10/10, 3 runs): a gunshot sends
the out-of-view fleeing peds inside (10-30), never past 70 %, the ones in view keep running, they come back after
`insideSeconds` and none comes out in view; the light tier's promoted bodies raise the combat load one for one and
the walker budget drops; walkers over a budget a 16-body fight leaves are shed. `-- --control` (both switches off)
fails exactly the 3 thinning / shedding checks. The island's own fights scare a probe crowd while it streams in, so
the probe calms it (`calmNow`) before each case. probe_ped_crowd 16/16 (x2), probe_light_tier, probe_encounter
unchanged.
