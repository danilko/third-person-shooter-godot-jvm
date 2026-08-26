# CLAUDE.md — Codebase Reference

Third-person shooter experiment using **Godot 4.6** with the **godot-kotlin-jvm** plugin.
All game logic is written in **Java** (a few stubs in Kotlin). GDScript is not used.

---

## Build & Run

```bash
./gradlew build          # compile + regenerate .gdj registration files into gdj/
```

Open `project.godot` with the **Godot Kotlin/JVM editor** (not the standard editor).
Plugin version: `0.15.0-4.6`. JVM toolchain: **JDK 17**.

Scenes/resources now reference scripts by their **source `.java` path**
(`res://src/main/java/com/openworld/.../X.java`), not the generated `.gdj` — see the
`.gdj`→`.java` migration in PLAN.md. `.gdj` generation into `gdj/` is still ON as a
safety net but is no longer what scenes load. Source of truth is always `src/main/java/`
— never edit generated files.

---

## Source Layout

All code lives under the **`com.openworld`** root, organized **by domain/concern** (not layer-first).
Scripts are referenced from scenes by `.java` path (`res://src/main/java/com/openworld/.../X.java`),
not via generated `.gdj`. The two reorg scripts (`tools/reorg_stage1.py`, `tools/reorg_stage2.py`)
and `tools/REORG_PROGRESS.md` document the move; reuse their pattern for future moves.

```
src/main/java/com/openworld/
  character/      # character bodies + visuals + data: Character (gatherInput/applyInput loop),
                  #   Player, AICharacter, Health, AnimationController, CharacterInfo,
                  #   CharacterVisuals, MeshConfig, CharacterRagdoll, NameplateTarget (interface),
                  #   CharacterDriveState, CharacterReplication, Faction, FactionManager (AutoLoad),
                  #   FactionTable (relationship matrix Resource)
  ai/             # AI brain + FSM: AIController, AIState (base), AIBehaviorConfig, AILodLevel
    character/    #   7 behaviour states: Patrol/Chase/Attack/Search/RefillAmmo/Escort/Flee
    vehicle/      #   VehicleAIController (reserved for future vehicle AI states)
  control/        # controller framework + input: Controllable, Controller, CharacterController,
                  #   PlayerController, UserCommand (per-tick input snapshot), ModalInput
  camera/         # AI/Player/FPS/TPS/Vehicle CameraControllers, CameraMode, ControlRotation
  movement/character/  # MovementController, MovementState, MovementType, Stance, StanceName,
                  #   CombatState, JumpState, RollState
  weapon/         # WeaponController (slot inventory), WeaponItem (extends item.Pickup),
                  #   WeaponAction, WeaponType, WeaponSlotType, FirearmItem, Melee/Knife/Axe/Fist,
                  #   ThrowableItem, ProjectileItem, RocketProjectile, T1Projectile, Detonatable,
                  #   IconRegistry
  world/          # world types: HitInfo, HittableBody, SurfaceType, SpatialEntityGrid (AutoLoad)
    manager/      #   world-level singleton systems: Impact/Particle/Decal/Explosion/BulletTracer
  item/           # Pickup (RigidBody3D base for world pickups), AmmoRefill station
  carrier/vehicle/ # Vehicle, VehicleWheel, VehicleConfig, VehicleWeaponMode
  game/           # EventBus (AutoLoad signals), GameManager (PLAYING/PAUSED/GAME_OVER FSM),
                  #   PlayerRegistry (AutoLoad — live Player list for AI LOD)
    mission/      #   MissionInfo, MissionManager, MissionObjectiveType
  net/            # NetworkManager (AutoLoad RPC), NetMessageCodec, NetworkController,
                  #   VehicleNetworkController, snapshot interpolators, policies, NetStats, Vec3/Quat
    session/      #   PlayerSession, PersistentPlayerId
  ui/             # CharacterHUD, Crosshair, HUDManager, PauseMenu, RadialMenu, Feed,
                  #   Nameplate (generic billboard, any NameplateTarget), WeaponSlotsUI/Item, …
  util/           # ObjectPool, generic helpers
  debug/          # DebugHarness (temporary test-spawn harness)

src/main/resources/com/openworld/  # .tscn/.tres (internal layout NOT yet remapped to new java pkgs)
  character/Character.tscn, Player.tscn, AICharacter.tscn
  weapon/AR4.tscn, PI52.tscn, …    world/World.tscn, WorldSystems.tscn    ui/…
src/test/java/com/openworld/net/   # headless unit tests for the engine-free net logic
```

> AutoLoads (`project.godot`): `EventBus`, `GameManager` (`game`), `MissionManager`
> (`game.mission`), `NetworkManager` (`net`), `PlayerRegistry` (`game`), `SpatialEntityGrid`
> (`world`), `FactionManager` (`character`), `WorldZoneManager` (`world`),
> `StimulusManager` (`world`).

---

## Core Architecture Pattern

### UserCommand loop

Every character (player or AI) runs the same two-step cycle each physics frame. The "brain"
is a separate `Controller` (`com.openworld.control`) attached to the body via the `Controllable`
interface — not a `Character` subclass override:

```
Character._physicsProcess(delta)
    1. command = controller.gatherInput(delta)   ← per-body Controller provides the source
    2. applyInput(command, delta)                ← base class applies to shared state
```

`UserCommand` (`com.openworld.control`) is a plain struct holding all per-tick intent:
`movementDirection`, `movementType`, `wantCombat`, `fire`, `reload`, `jump`,
`desiredStance`, `desiredWeapon`, `aimTargetPosition`, `tick`/`sequenceNumber`.

- **`PlayerController`** polls the `Input` singleton (keyboard/mouse).
- **`AIController`** runs the AI FSM and writes decisions into the command.
- **`NetworkController`** (`com.openworld.net`) injects the host-broadcast snapshot on
  non-authority peers — the interchangeable third source the pattern was built for.

The `tick`/`sequenceNumber` counter makes commands totally ordered for replay/reconciliation.

### Scene Inheritance

```
CharacterBody3D (Character.tscn)
    shared subtree: Health, WeaponController, AnimationController,
                    MovementController, ragdoll skeleton, stances
    ├── Player.tscn       — adds: PlayerController, camera, HUD wiring, AimStayTimer
    └── AICharacter.tscn  — adds: AIController, AICameraController, NavigationAgent3D, SightRay
```

### Camera Hierarchy (both characters)

```
CameraController (Node3D, top-level)
  └── Yaw (Node3D)
        └── Pitch (Node3D)
              └── Pivot (Node3D)
                    └── SpringArm3D
                          └── Camera3D
                                ├── AimRay (RayCast3D)   ← fire direction
                                └── SightRay (RayCast3D) ← LoS only (AICharacter)
```

`PlayerCameraController._input` accumulates `InputEventMouseMotion.getRelative()` deltas into
`pendingYaw / pendingPitch` on every mouse event; `gatherLookInput` consumes and resets them
each physics tick. This captures every mouse event between physics steps rather than sampling
only the last velocity (`getLastMouseVelocity`), which dropped intermediate events.
`AICameraController.gatherLookInput` → derives yaw/pitch delta from `aimTarget` world position.
(`PlayerCameraController` is the on-foot TPS/FPS controller; `TPSCameraController` /
`FPSCameraController` are its view sub-types. All live in `com.openworld.camera`.)

Recoil is stored as `recoilPitch / recoilYaw` on `CameraController` and decays via
`GD.lerp(…, 0, recoilRecoverySpeed * delta)` each frame — fully separate from the
mouse-intent `pitch/yaw` so recovery never fights aim. `recoilPitch` is **subtracted** per shot
(`recoilPitch -= pitchKick`) because negative pitch = look up in Godot's convention.
`recoilRecoverySpeed = 8.0` gives a snappy per-shot kick that clears in ~0.3 s; sustained fire
builds a learnable upward drift (~1.7° at full spray) rather than a persistent offset.

---

## Performance Foundation (Part D)

Drop-in accelerators that change nothing visually. Each degrades gracefully if its AutoLoad is
absent (test scenes), so they are safe to rely on but never required for correctness.

### Spatial partitioning — SpatialEntityGrid (`com.openworld.world`, AutoLoad, D1)

Uniform XZ spatial hash (`cellSize` exported, 50 m). `Character` and `Vehicle` (both in the
"characters" group) `register()` in `_ready()`, re-bucket via a throttled `updateSpatialCell()`
(0.25 s) called at the **top of `_physicsProcess`, before the non-authority early return** — so
puppet bodies (e.g. remote players on the host) keep their cell current too — and `unregister()`
in `_exitTree()`. `AICharacter.discoverTarget()` calls `queryRadius(pos, detectionRange)` instead of
`getNodesInGroup("characters")`, falling back to the group scan when `SpatialEntityGrid.get()` is
null. Reached via a JVM-static `get()`; all maps + the static are cleared in `_exitTree()`
(leak discipline).

### AI level-of-detail — AILodLevel (`com.openworld.ai`, D2)

`AICharacter` carries an `AILodLevel { ACTIVE, PASSIVE, FROZEN }` set every 2 s from
`nearestPlayerDist()` (which now iterates `PlayerRegistry`, not the group): `< 80 m ACTIVE`,
`80–200 m PASSIVE`, `> 200 m FROZEN`.
- **FROZEN** — `AICharacter._physicsProcess` returns before `super` (whole FSM + animation tick
  skipped). MovementController, a separate node, still decelerates the body to rest.
- **PASSIVE** — `AIController.gatherInput` returns a hold-heading command (no NavAgent / FSM /
  aim), and `AnimationController._physicsProcess` skips **all AnimationTree writes** when
  `getLodLevel() != ACTIVE` — those JVM-bridge calls are the dominant per-AI cost, so this is the
  real mid-range win.
- Returning to ACTIVE from any non-ACTIVE tier clears stale nav/search state.
`isLodFrozen()` is kept as a back-compat shorthand for `lodLevel == FROZEN`.

### Faction relationships — FactionManager / FactionTable (`com.openworld.character`, D3)

`Faction.areHostile()` is a **thin delegate** to the `FactionManager` AutoLoad (registered via
`Faction.setRegistry`), so **all call-sites stay unchanged** and there is no duplicated rule.
`FactionManager.areHostile()` is the single owner of the logic: NEUTRAL is never hostile → an
explicit `FactionTable` entry wins (`HOSTILE/DESPISE` → hostile) → otherwise the inherent default
(same faction allied, different factions hostile). The table (`DefaultFactions.tres`, a flat
`Dictionary<String,String>` keyed `"a>b"`) only needs **overrides** of that default — it ships just
the editable `player↔enemy = HOSTILE` rows. `setRelationship(a,b,rel)` flips a relationship at
runtime (mission betrayals; required before Part F). With no registry loaded (engine-free tests)
`Faction.areHostile()` returns false.

#### Multi-faction & runtime changes (high-level — details will firm up with Part F mission state)

Factions are arbitrary strings on `CharacterInfo.faction`, resolved fresh every target scan, so any
number of parties works with **no code change** — author a `FactionTable` (`.tres`) with only the
pairs that *differ* from the default (different faction ⇒ hostile, same ⇒ allied, `"neutral"` ⇒
never fights). Two runtime levers, both **host-authoritative and replicated** over the world-event
seam (`WORLD_EVENT_FACTION_*`):
- `FactionManager.setRelationship(a, b, rel)` — flip a whole party relationship (the betrayal beat).
- `Character.setFaction(s)` — swap one character's allegiance (e.g. a cornered NPC turning hostile).

Use these setters, **not** a raw `characterInfo.faction = …` write, so the change syncs to clients
(and rides the late-join baseline). **Lifetime:** the live table is a `duplicate()` of the shipped
`.tres`, and `FactionManager` is an AutoLoad, so a flip persists across scenes/missions until
`FactionManager.reset()` restores defaults (already called on full restart in
`GameManager.restartLevel`; call it at mission end for per-mission scope — auto-scoping belongs with
Part F). Behaviours that *react* to factions (a bystander fleeing when a fight erupts, corner
detection that triggers a swap) are AI-perception features not built yet — they'll land with Part E2
`StimulusManager` / the AI FSM.

---

## Open World Simulation (Part E)

### Zone streaming — WorldZoneManager / WorldZone / SpawnPool (`com.openworld.world`, E1)

As a player walks toward a populated area an AI group streams in; walking away streams it back
out — no scene stutter, no O(n) tree scans, host-authoritative + replicated spawns. Five pieces:

- **`WorldZone`** (`@RegisterClass extends Resource`) — placeholder-AABB zone data: `zoneId`,
  `size` (full XZ extents of the spawn box; *center is the marker's world position*),
  `loadRadius`/`unloadRadius` (hysteresis — unload **>** load avoids boundary flicker), nullable
  `geometry` (PackedScene, cosmetic), and two collections built with class tokens —
  `VariantArray<SpawnConfig> spawnConfigs` (ambient groups) and
  `VariantArray<NamedCharacterConfig> namedCharacters` (story AI with stable ids for Part F).
- **`SpawnConfig`** — `faction`, nullable `behaviorConfig` (else AICharacter `DEFAULTS`), `count`,
  `weaponScenePath` (AR4 default). Ambient AI share the `AICharacter.tscn` archetype.
- **`NamedCharacterConfig`** — stable `characterId`, `displayName`, `faction`, nullable `scene`
  (else AICharacter.tscn), `behaviorConfig`, `weaponScenePath`, `offset` (relative to marker).
- **`WorldZoneMarker`** (`@RegisterClass extends Node3D`) — the inspector-friendly in-scene anchor
  (a `Resource` AutoLoad can't take an inspector-assigned `.tres`, and a marker is positioned by
  dragging). Holds `@Export WorldZone zone`; **its global position is the zone center**. Registers
  with the manager in `_ready()`, deregisters in `_exitTree()` (the same register-with-AutoLoad
  idiom `Character` uses with `SpatialEntityGrid`).
- **`SpawnPool`** — plain Java helper (not an AutoLoad, not `util/ObjectPool` which throws on
  exhaustion and isn't tree-aware), owned by the manager. `acquire()` polls a `Deque<AICharacter>`
  (recycling a detached body, validated by `isInstanceValid`) or instantiates fresh;
  `wasLastAcquireRecycled()` lets load skip re-equipping an already-armed recycled body;
  `release(ai)` removes from tree + enqueues up to `poolCapacity`, else `queueFree`. **Only healthy
  bodies are pooled** — dead AI follow the normal death/ragdoll→free flow, so a recycled body never
  needs un-ragdolling.
- **`WorldZoneManager`** (`@RegisterClass extends Node`, AutoLoad) — mirrors `SpatialEntityGrid`'s
  shape (JVM-static `instance`/`get()`, `_exitTree()` frees geometry + clears maps + `pool.clear()`
  for leak discipline). Throttled tick (`evalInterval`, 0.5 s) over registered markers computes
  nearest-player XZ distance via `PlayerRegistry.getPlayers()` (O(playerCount)); `< loadRadius` →
  `load`, `> unloadRadius` → `unload`.

**Sizing a zone (radii are center-relative, NOT edge-relative).** Both `loadRadius` and
`unloadRadius` are measured from the **marker (zone center)** and are **fully independent of
`size`** (the spawn box). So the unload trigger can and *should* be much larger than the box — a
player stepping a few metres past the box edge does **not** unload (you'd have to reach
`unloadRadius` from the center). Defaults: `size = (60,10,60)` (30 m half-extent),
`loadRadius = 200`, `unloadRadius = 350` — unload only fires 350 m from center. Recommended
relationship (`halfExtent = max(size.x, size.z)/2`):
`unloadRadius > loadRadius > halfExtent`, e.g. `loadRadius ≈ halfExtent + pre-spawn lead (~150 m)`
and `unloadRadius ≈ loadRadius + hysteresis margin (~150 m)`. `WorldZoneManager.warnIfMisSized`
(debug-gated) logs once at registration when a `.tres` violates this (the cause of "everything
unloads the moment I step out" — a too-small `unloadRadius`).

**Authority:** AI spawn/despawn is host-only — geometry is instanced on every peer but the spawn
work is skipped on a non-server client (`net.isNetworked() && !net.isServer()`); clients receive
the bodies through the existing `announceSpawn → MSG_SPAWN → GameManager.spawnReplicatedCharacter`
path, and late-joiners via `sendBaselineSpawns`. Unload calls `announceDespawn(characterId)`
before pooling/freeing.

**Incremental streaming pipeline (the district-border anti-freeze rework):** a zone crossing used
to be one synchronous `load()` — `GD.load`-parse a 7–19 MB district `.tscn` on the main thread,
instantiate ~1600 nodes, tree-enter 500+ static bodies + a `NavigationRegion3D`, then spawn every
AI/vehicle, all in a single physics frame. Streaming is now a per-marker **task state machine**
(`StreamTask` in `WorldZoneManager`), processed every physics frame under a time budget
(`streamBudgetMs`, exported, 4 ms, ≥1 step of progress per frame so tasks can't stall):
`GEO_REQUEST → GEO_WAIT` (PackedScene parsed on **engine worker threads** via
`ResourceLoader.loadThreadedRequest`; main thread only polls) `→ GEO_INSTANTIATE` (one frame:
instantiate off-tree — node construction only — then strip children) `→ GEO_ENTER` (children
re-enter the tree a budget-slice per frame — tree entry is where physics/render registration
happens; a `NavigationRegion3D` gets a frame alone for its nav-map sync spike) `→ SPAWN`
(AI/named/vehicle spawns drained as work items — the formerly-deferred "frame-spread spawning",
now done). Unload is likewise batched: `FREE_BODIES → FREE_GEO` (per-child detach+free instead of
one ~1600-node `queueFree`). Rules that fall out of this: a marker with an in-flight task is in
neither `loaded` nor eligible for a second task; the LOD-low placeholder stays up until full
detail is **completely** entered (no visual hole) and returns only when the last child is freed;
a load whose player retreats past `unloadRadius` mid-stream is **cancelled** (partial content
torn down synchronously; off-tree staged children are explicitly freed — they'd leak otherwise,
same in `detectSceneReload`/`_exitTree`). Synchronous teardown still exists for marker-exit /
scene-reload / AutoLoad-exit (`unloadImmediate`/`teardownZone`). `maxLoadsPerTick` (now 2) only
caps how many *threaded parses* start per eval tick — main-thread work is always serialized to
one zone per frame. The remaining single-frame cost is `instantiate()` of the whole district
(~1600 node constructions, no registration); if that ever reads as a hitch on Steam Deck the next
lever is baking districts as sub-chunk scenes, not shrinking the budget.

**Binary district scenes:** `resolveGeometryPath` prefers a sibling `.scn` over the wired
`geometry_path` `.tscn` when it exists — the baked districts are multi-MB *text* scenes whose
parse dominates stream-in time even on a worker thread. `DistrictBinaryConverter`
(`hosts/ConvertDistricts.tscn`, one-shot batch job in the `WorldBaker` idiom, mtime-skips
unchanged files) resaves them all; `blender/tools/build_piece.sh` runs it automatically as its final step
(so a fresh bake is never shadowed by a stale `.scn`) — re-run it manually only after baking a
district by hand. `.scn` files are derived artifacts (delete-and-regenerate safe); the `.tscn`
stays the source of truth. No master re-bake or `geometry_path` edit is needed for the preference
to kick in.

**District authoring seam (see `blender/AUTHORING_GUIDE.md`):** a district rebuild
regenerates the `.blend` **in place** — only the procedural collections (`STREET`, `MARKERS`,
`STREET_LOD_LOW`, `ROADS_SRC`) are wiped; `MANUAL` (hand-authored content, exported + baked) and
`NEIGHBOR_REF` (read-only library-linked neighbour/master context from `tools/link_neighbors.py`,
dropped by every export) survive. `build_piece.sh District_<theme>_<gx>_<gy>` (stem form) is the
bake-only loop for hand-edited blends — it skips the regen entirely. Because linked libraries can
carry same-named collections (several linked `STREET`s), every collection lookup in the Blender
pipeline is local-only (`library is None`) — keep new lookups that way.

**What streams vs. what's static (a common confusion):** only two things are added on load and
removed on unload — the **AI bodies** and the zone's **`geometry` PackedScene** (instanced as a
marker child, `queueFree`d on unload). Anything authored directly into the `WorldZoneMarker` *scene*
(the debug box from `showDebugVolume`, or any mesh you drop under the marker node) is **static scene
content — it never streams**; it is the persistent zone *footprint/outline*. To make a mesh stream
in/out, assign it to the WorldZone's **`geometry`** field, not as a marker child (a Blender-exported
zone-chunk `.tscn`, same convention every district piece's `geometry_path` already uses). Zones also
do **not** carry their own navigation — AI use the level's `NavigationRegion3D`; nav is a
parent/world concern.

**Body recycling is OFF by default (`recycleBodies`, EXPERIMENTAL).** Reusing a full character body
subtree (detach via `removeChild`, re-attach via `addChild`) is **unsafe** in godot-kotlin-jvm: the
body carries a `top_level` camera (`TPSCameraController.setAsTopLevel`), a muzzle-flash
`GPUParticles3D`, and a nameplate `SubViewport`, and re-attaching that subtree leaves them
half-initialised — `get_global_transform "not inside tree"` / `particles is null` errors, then a
native use-after-free **segfault on zone enter** (no AI death required). So unload frees and
load instantiates fresh — correct, and no longer a stutter concern: spawns are frame-spread by the
streaming pipeline's SPAWN phase (see above), which was always the proper perf answer, not body
reuse. The `SpawnPool` + `activateForSpawn` reset path is kept
behind the flag for future hardening only. When recycling *is* on, only `isAlive() && !isDead()`
bodies are pooled (a dead body is ragdolled and `activateForSpawn` does not un-ragdoll it).

**The manager is an AutoLoad, so it survives `reloadCurrentScene()`/restart** — and pooled bodies are
parentless (held only by the deque, not in the scene tree), so a scene reload does **not** free them.
`detectSceneReload()` (top of `_physicsProcess`, compares the current-scene instance id) drops
`loaded` + frees the pool on any scene swap, so a restart never resurrects a body from the old scene
into the new one (this was a reproducible restart crash).

**Despawn safety — dangling references:** streaming despawns bodies that other systems may still
reference between target scans. `AICharacter.validateCurrentTarget()` (run every active frame, before
`super._physicsProcess`) drops `currentTarget` + its bone caches the moment the target is freed or
pulled out of the tree — without it, the FSM dereferences an out-of-tree node (`get_global_transform`
/ `look_at` "Node not inside tree") and segfaults once it is freed. `activateForSpawn` also clears the
recycled body's carried-over camera aim target and escort reference for the same reason.

**Pooled-reuse reset constraint (critical):** a pooled body's `_ready()` does **not** re-run on
tree re-entry, so reuse must re-initialize explicitly. `load()` calls
`AICharacter.activateForSpawn(worldPos)` **after `addChild`**, which sets global position,
**re-captures `spawnPosition`** (the patrol anchor, otherwise only set in `_ready()`), clears
`isDead` + all sensor caches, resets LOD + staggered timers, `Health.resetFull()`, re-registers the
`SpatialEntityGrid`, and calls `AIController.resetState()` (FSM back to `initialState()`, all timers
+ last-known targets cleared). Without the re-anchor a recycled AI would patrol around its *previous*
spawn point.

**Debug visualization + walk-test setup:** `WorldZoneManager.debugLog` (exported, on) prints each
load/unload decision, an approach-distance line while a player is near, and per-load recycled-vs-fresh
+ pool-idle counts. `WorldZoneMarker.showDebugVolume` (exported, on) builds at runtime a translucent
box (the spawn volume, `zone.size`) plus flat rings at `loadRadius`/`unloadRadius`; the box tints
**green while streamed in, cyan while idle** (driven by `setLoadedVisual` from the manager) — so you
can see a zone and walk into it. Both are pure debug aids, off via their export flags for shipping.
The `DebugHarness` **F12** key drops a code-built `WorldZone`/`WorldZoneMarker` in front of the
nearest player (`spawnDebugZone()`, no `.tscn`/`.tres` needed) if you want a quick zone to walk-test
without editing a scene — the standalone example zone scene this used to point at (`zones/DebugZone
.tscn`/`.tres`, `zones/DebugZoneGeometry.tscn`) was retired once the real 36-district open world
(`assets/world_source/`, `hosts/WorldMaster.tscn`) existed to walk-test against instead.

### Ambient traffic & the road graph (roads-v2)

**Generated data, not runtime inference.** `assets/world_source/lib/road_graph.py` (pure Python,
`python3 lib/road_graph.py` self-tests) turns an abstract centerline graph — junction nodes +
polyline edges with `lanes`/`oneway`/`class` — into everything the runtime consumes: per-direction
per-lane offset routes (`<edge>_<F|R><lane>`, keep-left, trimmed at junction stop lines), bezier
**turn connectors** (`c<node>_<in>_<turn>`, short names — Blender's 63-char object-name cap) carrying
`turn` (L/S/R) + `approach` (N/E/S/W) metas, and `intersection_` markers. Turning is a **data
lookup**: each chained lane's `_0` empty stamps `next_routes` (its connectors) + straight-biased
`next_weights` (0.6/0.2/0.2); `LaneGraph` endpoint clustering is only the legacy fallback (now
straightness-biased via `VehicleRoute.start/endTangentXZ`). Weighted choice = `util/WeightedPick`
(engine-free, unit-tested; malformed weights degrade to uniform, never throw). Keep-left legality:
1-lane approach → L/S/R; ≥2 lanes → curb lane (idx 0) L+S, median (n−1) R+S, middle S only; target
lane clamps by index — that clamp is the whole mixed-lane-count answer. `assemble.lay_road_graph()`
emits it all (raises on any name collision/overflow — Blender auto-rename would corrupt the baker's
name grouping).

**Graph sources:** master backbone — `build_world.backbone_graph()` (junction-split, 2 lanes per
direction, 336 lanes + 568 connectors + 49 junctions; `radius_fn` forces stop lines to the 21 m
paved footprint) + `backbone_deck()`, an always-resident **collision-only deck** under every
arterial (without it, cars outside streamed districts fall into the void — PLATEAU districts have
no always-resident ground) in the same exported `ARTDECK` collection. Authored in the master
blend (debuggable there), NOT runtime Java. **There is deliberately no world-spanning safety
floor** (`build_world.safety_floor()`/`--with-floor` and the per-district
`add_ground_safety_plane()` were both removed outright) — a collision-only floor a
meter-plus below visual ground silently trapped `Character`/`Player` bodies with no recovery
path, since neither has any fall-out-of-world safety net (unlike vehicles, which
`WorldZoneManager.maintainTraffic` reclaims below `Y = -30`). Falling off a road or off the
ArtDeck now falls through, same as any other gap in authored ground — see
`AUTHORING_GUIDE.md` for the districts/void-cell design this replaced it with. The *accurate*
per-district ground is PLATEAU terrain: originally imported via `extract_plateau.py --dem`
(CityGML `dem:TINRelief`) → `plateau_import.import_terrain`, which built a real sloped ground mesh
(visual + collision) and draped roads onto it — districts extracted without `--dem` have no
continuous ground and fall through in the gaps (no safety-floor catch anymore, see above). **That
extraction/import tooling was removed** once every PLATEAU-derived district/overlay/building asset
had already produced its permanent output `.blend` — see `AUTHORING_GUIDE.md` §2/§6. Terrain is
now hand-owned exactly like everything else; road authoring specifically is the
`road_kit_authoring` addon's point/port graph + `.lanekit.json` v2 sidecar (see "Ambient traffic &
the road graph" below), not the old `road_<name>` centerline/`.roads.json` pipeline that predates
it.

**Spawning:** region markers carry `traffic_count`/`traffic_route` → `WorldBaker.buildZone` builds a
`VehicleSpawnConfig`. `traffic_route` is a route-name **prefix** (`"art_"`, or `"<piece>__"` once a
sidecar exists — the master build flips the meta by checking for the sidecar, so re-run it after
authoring): `WorldZoneManager.findRoute(name, center, maxDist, index)` matches exact first, else
prefix-collects plain lanes (never turn connectors) whose entry is within `unloadRadius`,
round-robin by spawn index in name order — that spread IS the multi-lane spawn distribution.
**All lane lookups are registry reads, never scene-tree walks:** `VehicleRoute._ready/_exitTree`
register/deregister with a `TreeMap` on `WorldZoneManager` (the Character↔SpatialEntityGrid
idiom; sorted names make the prefix query ordered for free), and `entryPoint()` caches the first
marker position per tree entry. The old recursive whole-tree scans (two per spawn, tens of
thousands of JVM-bridge calls with a district streamed in) ran inside the 0.5 s `maintainTraffic`
tick and were the "periodic hitch in all movement" regression; `VehicleRoute.resolveRoute`/
`pickNextRoute` (every lane end) go through the same registry.
`maintainTraffic` reclaims: dead / route-finished / **fell-out** (Y < −30 — an off-road car
free-falls with unchanged XZ, so the range check alone never catches it) / out-of-range, then tops
back up (GTA disposable traffic). `debugLog` prints spawn/reclaim/status lines — "N cars, M moving,
K routed" is the headless-smoke signal (routed-but-0-moving = falling through missing ground;
route-finished churn = broken junction wiring).

**Junction discipline:** `CruiseState`'s curvature probe cannot see past the current route, so
`VehicleAIController` clamps throttle (`junctionThrottleScale`, 0.45) within `junctionSlowdown`
(18 m) of any chained lane end and while riding an L/R connector — without this cars enter 90°
turns at full cruise speed and fly off. Phase 2 (JunctionArbiter FCFS grant sets + timed signals
keyed on the baked `approach`/`turn`) and Phase 3 (highway ring + ramps + `speedLimit`) are next —
see PLAN.md "Roads & Traffic v2".

**Known noise:** instancing `Vehicle.tscn` from code logs a `CharacterInfo` ClassCastException
(the scene-embedded sub-resource's JVM script binds late, so the setter receives a plain
`Resource`) — harmless: every spawn path immediately overwrites `characterInfo` with a fresh
instance per the shared-sub-resource identity rule.

### Terrain & seam alignment (ground is NOT a flat plane)

Each district's real ground is a **DEM-derived heightfield** — originally imported via
`extract_plateau.py --dem` → `lib/plateau_import.py: import_terrain` (one continuous sloped mesh
per district, visual + collision in one; that extraction/import code has since been removed, see
`AUTHORING_GUIDE.md` §2/§6 — every district's terrain is now a permanent, hand-owned part of its
`.blend`, this just describes how it originally got its shape) — genuinely non-flat wherever DEM
data was extracted, not a flat square. What makes adjacent districts agree at their shared edge is
a **theme-elevation-step + taper system**, not literal shared/welded geometry:

- `lib/world_grid.py`'s `THEMES` dict assigns each of the 7 region themes a flat **baseline**
  elevation (harbor 0, city 2, resid 4, rural 10, mtn 40, snow 90, industry 0) — a coarse
  staircase across the whole map.
- The original import blended the real (sloped) terrain height toward that baseline within a
  border margin of every district edge (`plateau_import.seam_taper()`, no longer present but
  baked into every existing district's terrain), so the interior keeps real terrain shape but
  every edge lands at a known, neighbor-predictable value.
- A `.seam.json` sidecar per district (36 of the 39 district files have one) records each edge's world
  position, elevation, the neighbor's expected elevation, and route-name chaining;
  `tools/check_seams.py` (pure Python, no Blender needed) verifies two adjacent `.seam.json` files
  agree — this is the existing, already-automated seam-alignment QA step, run whenever
  neighboring districts change.

So cross-district alignment for elevation is a **solved, working system** — districts don't need
literal vertex-welded ground, they need matching boundary *values* (elevation, route endpoints),
which the taper + `.seam.json` + `check_seams.py` trio already enforces.

**Road authoring is now the POINT/PORT GRAPH** (`blender/ROAD_POINT_GRAPH.md`, the design of
record; `blender/addons/road_kit_authoring/point_*.py`). A road is an ordered chain of **road
points** — an Empty that is simultaneously a *station* (its own cross-section: lanes per direction,
median, kerbs, footways, structure) and a *port* (its typed `SEGMENT` / `JUNCTION` / `AUX` links).
A junction is a clique over `JUNCTION` links whose member points **are** the stop lines; a ramp is
an aux slot plus an `AUX` link. Every along-the-length change — lane drop, lane opening, one-way,
an acceleration lane with its taper — is just *"two stations that differ"*. The authored record is
a git-diffable `<stem>.roads.json`; the Empties are a **view** of it. Build emits per road run a
swept `__surface` carrier (a GN layer stack), `__edges` kerb/footway runs placed against the paved
**outline** so gores open by themselves, `__edges` kerb/footway/**barrier** runs per junction
corner too, a pad per junction, a paved **gore strip** per ramp, the terrain cut, and split
`-colonly` road/footway collision proxies. `blender/tools/check_roads.sh` is the one command
that runs the gate (17 checks, including a full-plugin pass that drives every operator, draws every panel, and asserts every operator is reachable from a button). `Author ▸ Learn ▸ Add Sample Network` builds a worked example of all four link types; the step-by-step guide is in the addon's `README.md`.
**The Empty's transform IS the road frame** — position is the station, **local +Y is travel
direction** (points draw as `ARROWS` so that axis is visible; `SINGLE_ARROW` draws along +Z and
showed the wrong one), roll is banking, and `tangent_mode = MANUAL` makes the rotation drive the
curve, with `handle_in`/`handle_out` in metres (0 = the chord). **Rotating a point IS the bend
gesture — there is no mode to set first.** Points are *born facing their road* (`new_point` takes a
`facing`; `Extend Road`/`Insert Point` pass the chain direction — never via `face_matrix`, which
reads a `matrix_world` still identity on a just-created object and would move the station to the
world origin), and the tool stamps the facing it gave each one in `RKA_Point.auto_tangent` (derived
state, **not** in `.roads.json`). `read_point` then promotes an AUTO point whose facing has left
that baseline to MANUAL — a *read-side* derivation, so it takes effect in the overlay, the gate,
Build and the export at once with no write and no handler. The baseline is what separates a
rotation from a **drag** (a translate changes the chain tangent while leaving the rotation alone,
so recomputing-and-comparing would falsely promote every dragged point). `point_ops.sync_facings()`
is the write half — promotion first, *then* re-face what the tool still owns — run by Build, by the
live rebuild, and by the `Follow Road (Auto)` button; `point_profile.chain_facings()` is the one
owner of "which way does this station face". The overlay draws the **resolved centreline**
(`point_profile.centreline_runs()`, resample-only so it is cheap enough for a per-frame draw
handler), so a rotation reshapes the road live without any rebuild — `rka_live_rebuild` (off by
default) is only about the *mesh*. **Straightness is measured, never authored** (`road_points.segment_bend_deg`) — there is no straight/curved flag to keep in sync. The
`Connections` panel lists the active point's links with derived span / straight-vs-bend / taper
verdict (the taper number comes from the gate's own `taper_min_length`, so the two cannot
disagree), and `Connect Selected` is anchored on the **active** point — `AUX` is directed
(mainline → ramp), so `selected_objects` order was a coin flip. The two previous models are gone: the mesh-graph `graph_*.py` is
archived under `legacy_graph/` (not imported) and the per-piece generators (`ops_placement.py`,
`ops_intersection.py`, `ops_segment.py`, …) were **deleted** — see `legacy_graph/README.md`.
District_industry_5_1's hand-authored `MANUAL` collection predates this and is still valid baked
geometry; it is no longer the authoring reference.

**One owner per derived fact — the four rules the 2026-08-25 fixes added** (`ROAD_POINT_GRAPH.md`
§8f has the full write-up; each of these was a user report):

- **Direction has ONE owner: `point_model.station_axis`.** The carriageway honoured a MANUAL
  tangent while `point_solve.mouth_axis` and `point_validate._axis` each re-derived the direction
  from the *neighbour's position* — so rotating an intersection mouth bent its street and left the
  pad exactly where it was. Both now delegate. Rotating a mouth turns its cap, its two fillets and
  its turn paths.
- **A pad always tessellates.** `point_solve.pad_triangles` fans from the ring's **kernel point**
  (`fan_origin`, found by pushing the apex inside the edges it is outside of) and `ear_clip`s when
  no kernel exists; `build_pad` sweeps exactly that. `pad_not_star_shaped` is a **WARN**, not an
  ERROR — a 2 cm fold from a hand-drag used to refuse the whole build and name as its remedy an
  `Auto Setback` that then reported "moved 0". Never let a hand-drag be a build failure.
- **A ramp is the aux slot's CONTINUATION, not a lane beyond it.** `point_profile.aux_edge_offset`
  returns the aux slot's **through-lane-side** edge (the gore line), so `lanes_fwd = 3,
  aux_fwd = 1` is a four-lane carriageway whose outermost lane leaves. `point_solve.ramp_target`
  is the single owner of where the mouth belongs — and `Align Ramp To Aux` also **faces** it down
  the mainline (`MANUAL`), because two bands cut on different planes touch at one vertex and open
  from the next. Divergence is authored at the ramp's *next* point. `solve_gore` paves the wedge
  between the two roads' own paved edges, from where the signed gap changes sign to a 4 m nose.
  `check_tapers` exempts the station that owns the `AUX` link: a **departing** lane is not a
  **merging** lane and needs no merge taper.
- **Reachability is not geometry, and had no eye.** An `AUX` link exported as *nothing*: the ramp
  lane had no predecessor, so no ambient car could ever reach a ramp anywhere in the world, with a
  green gate and perfect geometry. `point_export.wire_ramps` emits the edge (directed by the ramp
  point's role) and `_aux_handoffs` **ends the exit lane at its gore** so the successor is within
  `CHAIN_TOL`. `point_preview` (the **Preview** panel) draws the *exported* lane graph — directed
  lanes, `next` edges, agents walking it on the exported weights — and reports `broken` /
  `open_end` / `unreached` / `ramp_orphans`. When adding anything to the lane graph, check it
  there: a build being green says nothing about whether traffic can get to it.

**Five more owners, from the 2026-08-26 follow-up** (`ROAD_POINT_GRAPH.md` §8g; same shape as §8f
— a rule right for the case in front of you, applied to one nobody had looked at):

- **An exit is a BLOCK of aux slots, not one slot.** `point_profile.aux_block` returns the whole
  run of same-direction aux slots and the edge facing the through lanes; `aux_edge_offset` is that
  edge. Anchoring on the *outermost* slot was right at `aux_fwd = 1` and put a two-lane ramp half
  on the carriageway at `aux_fwd = 2`.
- **The merge taper is the metric standard × the road's `taper_factor`.** `TAPER_LINEAR_ABOVE` is
  70 km/h (it was 60, which over-demanded by half across the whole 60–70 band). `taper_factor`
  (`ROAD_FIELDS`, default 1.0) exists because **the world is not 1:1** — shortening a taper for a
  compressed map is a visible authored decision on the road, never a constant bent in the checker.
- **A barrier's HEIGHT is authored, its PLACEMENT is derived.** `RoadData.barrier_height` (0 =
  none) × the rule in `solve_road`: fenced along the whole length when `ped_access` is off, and
  only where `delta >= BARRIER_MIN_DELTA` when it is on. It is a layer in `edge_spec()` on the same
  `deck` node group as the kerb, so it rides the **outline** — which is why it opens across a gore
  and closes past the nose with no ramp-specific code at all.
- **A junction corner IS an edge run.** `point_solve.junction_corners` emits one `Corner` per real
  corner from `intersection_kit.build_junction_curb_segments` (the same curve the pad boundary is
  rounded with) and `point_build.build_junction_edges` sweeps it with the ordinary `edge_spec()`.
  Before this, every crossing in the world had four missing pavement corners.
- **`point_edges.Band.carries_edge` — a pad hands the furniture on, a gore does not.** A run must
  not suppress its kerb against a footprint that continues it (that gap was the missing corner
  pavement), but it MUST open across one that does not. A run is a member of both, so membership
  alone cannot tell them apart; keying on it left a barrier stub standing across the gore paint.
- **`intersection_kit.curb_edges(..., tail_length=)` anchors each arm's kerb ray on that arm's own
  `tail_center`, not the origin** (§8h). The origin-anchored ray passes through the cap only
  because a plain arm's tail centre is a multiple of its direction — an off-ray `tail_pos` (which
  is what `_PadArm` sets from the AUTHORED mouth) does not satisfy that, so a **rotated** mouth's
  corner left the cap ~50° out and its footway met the street in a notch. Opt-in by parameter, and
  byte-identical for any arm without `tail_pos`; `Arm.tail_center`'s docstring records the opposite
  scope limit, which was right for the model that wrote it and wrong for this one.
- **`point_edges.covered(..., outward=)` is DIRECTIONAL: "does the pavement continue past this
  line", not "is there asphalt within 0.6 m".** Where a ramp leaves along the mainline's outer
  edge, both edges are the outer boundary of the same pavement, and the undirected `NEAR_PAD` slop
  had each band suppress the OTHER's parapet — 11 m of unwalled edge at the top of a 14 m drop.
  The probe is taken `NEAR_PAD` **outboard** and must land strictly inside another band.
  `measure_on_asphalt` uses the same tolerance for the same reason: it measures standing ON asphalt.
- **A directional `covered` asks TWO questions, and a run's END is CLIPPED, not rounded (§8h.4).**
  Two user reports, opposite ends of one ramp, one root cause — start/end decided per 4 m sample
  about features metres across. (a) The outboard probe can step clean OVER a band narrower than
  `NEAR_PAD`: at a mouth the mainline's outer edge lies 0.5 m inside the ramp's band, the probe
  landed 3 cm past it, and both parallel edges kept a wall — "one extra wall at the ramp
  connection". So `covered` now also suppresses when the point ITSELF is `BURIED_TOL` (5 cm) inside
  another band. That is a tolerance for *exactly on*, not a margin — an edge on another band's
  boundary is the shared outer boundary and keeps its wall, which is §8h.2's case. (b)
  `point_edges.open_runs` returns `Run(i0, i1, head, tail)` — still `(i0, i1)` when indexed — whose
  `head`/`tail` are **bisected onto the covering band's boundary** (`_clip_end`), so a run ends at
  the mouth it hands over at and starts at the gore nose it must meet, instead of a sample either
  side. `sub_polyline` + `pe.run_values` emit points and attributes from one place so they cannot
  come out different lengths. Together these let the gore cap sit FLUSH on the strip's last pair
  (`GoreSolve.nose`) with both flank walls meeting it — three walls, one closed corner.
- **A GORE OWNS ITS OWN NOSE — neither flanking road can (§8h.3).** A gore is bare paint
  (`Band.carries_edge` False), so both flanking walls open across it: right along the join, where a
  wall would stand in the exit lane, and wrong at the wide end, where the two roads have parted and
  their walls restart `GORE_NOSE_WIDTH` apart with an open V between them at the tip of a viaduct.
  Neither road can fill it — the stretch is the other one's asphalt — so `point_solve._gore_nose`
  emits an ordinary `Corner` and `point_build.build_gore_edges` sweeps it with the ordinary
  `edge_spec()` (`GORE_*__edges_nose`). **What** it carries is still the roads': each end reads that
  road's own solved `rka_wall_h`/`rka_curb_h*`/`rka_walk_h*` and the run blends between them, so a
  fenced highway meeting a fenced ramp is a wall, an approach declaring a footway gets a kerbed
  island, and a pair declaring neither builds nothing. `GoreSolve.ped_access` is both flanks'
  answer, so the proxy is `-noped` between an expressway and its ramp and walkable between two
  streets. **Where** it sits is derived: one `GORE_STEP` past the nose on each road's own edge — the
  first sample outside the gore's polygon, i.e. exactly where `open_runs` lets that flank's wall
  resume. `point_build.edge_run_values`/`build_edge_run` are now the one owner of the per-vertex
  furniture arithmetic, shared by a road flank, a junction corner and this.

**Road/geometry alignment across a shared seam is a separate, still-manual concern.** Because Blender's Library Override
system can move/rotate a linked object as a whole but can never edit linked mesh/curve vertex
data, aligning road geometry that genuinely spans two districts' seam needs either (a) read-only
whole-world context while editing one district locally (`tools/link_neighbors.py`, extendable to
every built district, not just immediate neighbors), or (b) a temporary scoped multi-district
edit session — append (not link) just the districts that need reconciling into one scratch file,
edit their `MANUAL` content together with full Edit Mode access, then write each district's
result back into its own file. See `AUTHORING_GUIDE.md` for the current tooling around this.

### AI spatial perception — StimulusManager (`com.openworld.world`, AutoLoad, E2)

Poll-based, spatial channel for AI-perceptible world events — the AI counterpart to `SpatialEntityGrid`
(events instead of bodies). **Not EventBus:** EventBus fans every signal to every listener (right for
UI, wrong for AI at open-world scale); a stimulus is instead *dropped at a world position with an
audible `radius`*, and AI **poll** their own neighbourhood. EventBus is unchanged and keeps all UI
signals — only AI-perception events live here.

- **`StimulusManager`** mirrors the AutoLoad shape (JVM-static `get()`, `_exitTree()` clears). Holds a
  `List<Stimulus>` aged out after `stimulusLifetime` (5 s) in `_process`. `post(type, origin, radius,
  source, sourceFaction)` drops one; `getStimuli()` exposes the live list read-only (same backing-list
  convention as `PlayerRegistry`). `Stimulus` is an immutable plain object; `Type` =
  `GUNSHOT, EXPLOSION, VEHICLE_CRASH, DEAD_BODY, PLAYER_SPOTTED` (last two reserved for later).
- **Emit (authority side-effect paths only**, so the host that simulates the AI sees them):
  `FirearmItem.useWeapon` → `GUNSHOT` at the muzzle (`gunshotHearingRadius`, exported, 150 m — *not* the
  puppet `playRemoteFireCue`); `ExplosionManager.triggerExplosion` → `EXPLOSION` at the blast center
  (heard past the blast); `Vehicle._integrateForces` → `VEHICLE_CRASH` on a fast impact (throttled
  ~1×/s).
- **Poll:** `AICharacter.hearAlarm()` returns the nearest investigate-worthy origin within
  `behaviorConfig.hearingRadius` (capped by each stimulus's own radius), ignoring its own events and
  *allied* gunfire (`Faction.areHostile` for `GUNSHOT`; explosions/crashes alert everyone).
  `PatrolState` calls it after the visual-target check and, on a hit, sets the controller's
  last-known-position and transitions to `SearchState` (which already navigates there). `DebugHarness`
  **F8** drops a synthetic enemy `GUNSHOT` at the player for a vision-free walk-test.

**Networked propagation:** stimuli are a local per-peer list (puppet AI don't think). A remote
*client's* gunshot is delivered to host AI **for free via the existing fire replication** — when the
client's `fireSeq` bumps, the host runs `FirearmItem.playRemoteFireCue` on that puppet and (gated to
`isServerPeer()`) posts the same GUNSHOT stimulus there, where the AI poll. No new network message;
other clients run the cue but don't post (their AI are puppets). Non-gunshot stimuli
(explosion/crash) still post only where their authoritative side-effect runs.

### Squad awareness — AISquad (`com.openworld.character`, E3)

Shared group targeting so shooting one AI turns the whole nearby band toward the shooter within a
frame, instead of each AI waking on its own ~0.4 s scan.

- **`AISquad`** is a `Node` (editor-placed, or one created per `SpawnConfig` by `WorldZoneManager`).
  Members `register`/`unregister`; it holds a `sharedTarget` + `sharedLastKnownPosition`.
  `getSharedTarget()` self-clears a dead/freed/out-of-tree target (the "lose track" path);
  `clearThreat()` drops a still-alive one.
- **Spot → broadcast:** `broadcastSpotted(spotter, target, pos)` records the target and pushes it to
  every member within `alertBroadcastRadius` (60 m of the spotter) via `AICharacter.adoptSquadTarget`
  — which sets `currentTarget` + last-known immediately (skipping the scan interval). Triggers:
  `AttackState` on confirmed LoS, and `AICharacter.onEnemyDamaged` (being shot is a sighting too — uses
  `currentTarget`, the believed attacker). Squad-mates are one faction and the spotter already verified
  hostility, so adopters skip a redundant faction check.
- **Converge:** `AICharacter.discoverTarget()` consults `getSharedTarget()` **before** its own scan, so
  a mate keeps the shared target across rescans; `PatrolState` chases a squad-adopted target even
  without personal LoS yet. `AICharacter` holds the squad via `activeSquad()` (nulls a stale ref to a
  freed squad node — pooling/reuse safe); `setSquad` moves registration; `WorldZoneManager` frees each
  per-group squad on unload.

`AISquad._process` also implements **lose-track**: if no member has spotted the shared target for
`forgetDuration` (8 s) it `clearThreat()`s and members fall back to their own scans (death is handled
sooner by `getSharedTarget`'s self-clear).

> **Part E (E1–E3) complete.** Only deferred item left: body-recycling (E1, off by default — subtree
> reuse unsafe; frame-spread spawning is the real perf fix, TODO).

---

## AI (7-state singleton FSM)

The AI body is `AICharacter`; its brain is `AIController` (`com.openworld.ai`), which runs the
FSM in `gatherInput`. States are **stateless** singleton objects under `com.openworld.ai.character`.
All mutable data lives on `AICharacter`. `AIState.update()` returns the next state; a different
reference triggers a transition.

| State | Key behaviour |
|:------|:--------------|
| `PatrolState` | NavAgent random walk within `patrolRadius` of spawn. → Chase/Attack on sight. → Search on hit. |
| `ChaseState` | Sprint to target (or last known pos). → Attack when in range + LoS. → Patrol after `LOST_PLAYER_TIMEOUT` (3 s). |
| `AttackState` | Strafe laterally. Reaction delay before first shot. Per-shot `hitChance` roll. Suppression fire for `suppressionDuration` after losing LoS. → Search when suppression expires. → RefillAmmo when dry. |
| `SearchState` | Sprint to last known position, strafe to peek. Re-engage on sight. → Patrol after 5 s. |
| `RefillAmmoState` | Sprint to `ammoRefill` Area3D. Fill all weapons on arrival. → Patrol. |
| `EscortState` | Follow + defend a designated `Character`. → Attack if the escort target is attacked. |
| `FleeState` | Sprint away from an attacker for a set distance. → Patrol on arrival. |

Targeting is faction-aware (`AICharacter.discoverTarget()`): same-faction AI ignore each other
and neutral factions are never targeted (friendly escorts / non-hostile NPCs).

### Key AICharacter fields (timers all on AICharacter, not states)

```java
double attackTimer         // counts down per-shot cooldown
double lostPlayerTimer     // time since last LoS in Attack/Chase
double reactionTimer       // counts up from AttackState.enter; fires when >= reactionTime
double underAttackTimer    // set to UNDER_ATTACK_DURATION (2.5 s) on damage
double strafeTimer         // counts down; refresh strafe direction on <= 0
double searchTimer         // counts up in SearchState
Vector3 lastKnownPlayerPosition
Vector3 currentAimTarget   // where AimRay is tracking this frame
```

### SightRay vs AimRay separation

- **SightRay**: pure LoS check — `hasLineOfSight()`. Never moves the camera.
- **AimRay**: fire direction — `AICharacter.snapAimRay(target)` forces it to point at the
  computed aim target just before `command.fire = true`.
- These are independent so accurate LoS never implies accurate aim.

---

## Combat / Weapon System

All weapon classes live in `com.openworld.weapon`; `WeaponItem extends item.Pickup`
(weapon items *are* the world pickup nodes).

### Semi-auto / full-auto lock (WeaponItem)

The "one use per trigger pull" lock lives in the base `WeaponItem`, not per-subclass:
`isWeaponFired` is set in `useWeapon()` and cleared in `stopUseWeapon()` (trigger release);
`isSemiAutoReady()` returns `!isWeaponFired || auto`. Every weapon gates `canUse()` on it, so a
non-`auto` weapon fires exactly once per pull regardless of `fireRate`. `FirearmItem`,
`ProjectileItem`, and `ThrowableItem` all share this — previously the lock was copy-pasted into
the firearm/projectile only and **missing from `ThrowableItem`**, which let a held throw key
spawn multiple grenades back-to-back (the double-throw bug). `MeleeItem` keeps its own
timer-based model (overrides `stopUseWeapon()` to a no-op).

### Spread formula (FirearmItem)

```
totalSpreadDeg = (spread + currentBloom + speed_m_s × 0.03) × stanceMultiplier
```

Stance multipliers: UPRIGHT 1.0×, CROUCH 0.7×, CRAWL 0.5×, airborne 2.0×.
The multiplier applies to the **entire** expression — crouching reduces both the base
accuracy penalty and the movement penalty proportionally.

Bloom accumulation: `currentBloom += bloomPerShot` on each shot; decays at `bloomDecaySpeed`
deg/s every physics frame. Key relationship: if `bloomDecaySpeed < bloomPerShot × fireRate`
bloom accumulates during sustained fire; if greater, each shot clears before the next (semi-auto).

Current weapon values:

| Weapon | `spread` | `bloomPerShot` | `bloomDecaySpeed` | `bloomMax` | `recoil` |
|:-------|:--------:|:--------------:|:-----------------:|:----------:|:--------:|
| Rifle  | 0.01°    | 0.05°          | 0.3°/s            | 0.25°      | 1.0°     |
| Pistol | 0.05°    | 0.05°          | 2.0°/s            | 0.2°       | 0.5°     |

- Rifle: first shot 0.01° (~1 cm at 50 m); full spray 0.26°; bloom accumulates over ~1.25 s of fire.
- Pistol: first shot 0.05° (5 px crosshair gap from draw — visibly less precise than rifle); bloom
  clears between taps so sustained semi-auto accuracy stays near base spread.

Spread is applied as a **circular cone** in `performHitscan`: random angle + `sqrt(rand) ×
halfSpread` radius → uniform disk distribution (no diagonal bulge from independent pitch/yaw
sampling). The block is skipped entirely when `spread == 0` (no wasted raycast work).

AI bypasses spread entirely (`useWeaponSpread = false` on the AICharacter); accuracy is controlled
by `hitChance` + `aimScatterRadius` in `AttackState`.

### Crosshair (weapon-normalized spread)

`Crosshair._process` maps `weaponController.getCrosshairSpreadFraction()` (a 0..1 value) to a fixed
pixel range `[minSpreadPixels, maxSpreadPixels]` (default `3..90 px`, exported). It does **not** use the
raw degrees directly — that was the old `getCurrentSpreadDeg() × spreadPixelsPerDeg` model, which ran a
wide-cone weapon (shotgun: up to ~8°) off-screen and made small-spread weapons barely move.

**The fraction is normalized per weapon** (`FirearmItem.getCrosshairFraction`): `currentSpread /
worstCase`, where `worstCase = spread + bloomMax + CROSSHAIR_REF_SPEED(6 m/s) × MOVEMENT_SPREAD_PER_MPS`
— this weapon's realistic on-ground max. So **every weapon shares one reticle scale with no per-weapon
crosshair tuning** (the gun's existing `spread`/`bloomMax` drive it), the opening is **capped** (never
off-screen — airborne spread just clamps to 1), and movement/bloom/stance always move the reticle a
visible fraction of the range. The reticle therefore reliably means "current inaccuracy with this
weapon": a rifle reads ~2% at rest and opens dramatically when moving/spraying; a shotgun rests wider
(~37%) and tops out under bloom without exploding off-screen. `getCurrentSpreadDeg()` is unchanged and
still drives the **actual** bullet cone — the crosshair fraction is purely cosmetic.
Arms snap outward at `crosshairExpandSpeed = 60` (near-instant on shot) and contract at
`crosshairContractSpeed = 8` (tracks bloom recovery — a clear "accurate again" signal).

### Hit detection, damage, and impact VFX

`WeaponController.onWeaponFire()` collects hit data into a `HitInfo` and delegates entirely:

```
WeaponController
  → HitInfo(hitNode, collisionPoint, collisionNormal)
  → ImpactManager.processHit(info, damage, weapon, attacker)
        │
        ├─ spawnImpactParticles()   resolveSurfaceType → ParticleManager.spawn(type, point)
        ├─ spawnDecal()             DecalManager.spawn(point, normal)
        └─ applyDamage()            owner.getNode("Health").takeDamage(...)
```

**`HitInfo`** bundles `(hitNode, hitPoint, hitNormal)`. Adding future effects never
changes the `processHit` signature — just add a private method in `ImpactManager`.

**`resolveSurfaceType`** priority (two `instanceof` checks, no node-tree scan):
1. `owner instanceof Character`       → `FLESH`  (automatic)
2. `owner instanceof HittableBody hb` → reads `hb.surfaceType` directly
3. fallback                           → `DEFAULT`

**`ParticleManager`** — fire-and-forget pool. Acquire → position → emit → release immediately.
  Scene setup: one `GPUParticles3D` template per type container; `_ready()` duplicates it
  to `poolSizePerType` (default 16) automatically — only the template needs editor config.

**`DecalManager`** — held pool. Acquire → show → age in `_process` → release after `decalLifetime`.
  Scene setup: one `Decal` template as direct child; `_ready()` duplicates it to `poolSize`
  (default 16) automatically — only the template needs texture + size set in the editor.
  Decal oriented by building `Basis(right, normal, fwd)` so local +Y = surface normal
  (Decal projects along local -Y, so +Y = outward normal shoots the projection into the surface).

All three world managers (`ImpactManager`, `ParticleManager`, `DecalManager`) live in
`World.tscn` and are discovered via Godot groups — `WeaponController` and `ImpactManager`
lazily cache references on first use to avoid `_ready()` ordering issues.

Damage multipliers are resolved by bone name in `Health.getDamageMultiplier()`:
- `Physical Bone head_2` → 4.0× (headshot)
- Upper torso → 1.0×, mid torso / arms → 0.75×, legs → 0.5×

On death, `Health` emits to `EventBus.characterEliminated(attacker, victim, weapon, headshot)`.

### Networked combat cosmetics — fire / reload / melee replay (puppets)

Combat is replicated as **state, not events**: `WeaponController` carries two rolling u8 counters
sampled into every snapshot — `fireSeq` (bumped in `onWeaponFire`, all weapon types) and `reloadSeq`
(bumped at the end of `onWeaponReload`). `NetworkController.applyDiscreteState` change-detects each:
when a counter differs from the last seen value it calls `wc.playRemoteFireCue()` /
`wc.playRemoteReloadCue()` and mirrors the value forward (so a re-broadcasting host carries the right
counter to other clients). No separate droppable fire/reload message exists. `SNAPSHOT_ENTRY_FIXED_BYTES`
in `NetworkManager` must equal the per-entry byte count in `NetMessageCodec.putSnapshotEntry`
(currently 65 = …+ fireSeq u8 + activeMagazine u16 + reloadSeq u8) or MTU chunking mis-sizes frames.

**The core rule — a puppet replays cosmetics only, never re-derives damage, and derives the shot
identically to the authority:**
- Every weapon's `playRemoteFireCue()` reconstructs the shot from the **replicated logical state**
  shared by all peers: the weapon's **own `Muzzle` marker** for the origin and the replicated
  **`getAimTargetPosition()`** point (which also drives spine IK and rides in every snapshot) for the
  direction — *never* the local `aimRay`/crosshair (puppets have none) and *never* the animating pose.
  Authority and puppet run the **same** origin/direction derivation; only damage differs.
- Damage is **authority-only**, gated by the `cosmetic` flag: `RocketProjectile`/`T1Projectile` spawned
  with `cosmetic = true` play VFX (`ExplosionManager.spawnExplosion`) but skip
  `triggerExplosion`/attacker injection; `FirearmItem` puppet draws a tracer but runs no hitscan;
  `MeleeItem.playRemoteFireCue` plays swing audio only and must **not** call `startSwing()` (its hit
  window applies damage). `WeaponItem.playRemoteFireCue()` is an empty default — every concrete weapon
  type that can fire must override it or it is silent/invisible on other peers (this was the melee bug).
- Spawned projectiles add `addCollisionExceptionWith(owningCharacter)` — a secondary guard so a
  weapon never collides with / detonates on its own shooter (the rocket's `collision_mask` includes
  the character layer); it is not the consistency fix, the unified muzzle+`aimTarget` spawn is.

**Switch timing (CS/PUBG-snappy):** the deploy is `transitionTimer = 1/switchSpeed` (~0.45 s at
`switchSpeed = 2.2`); the post-deploy fire lockout `onWeaponTransitionComplete` starts is a small fixed
`WeaponController.DRAW_SETTLE_SECONDS` (0.08 s), **not** a second full `1/switchSpeed`. So total
switch ≈ deploy time (was ~2/switchSpeed — the old double-duration that felt sluggish). The
draw-settle still exists only to stop a held fire button launching on the first mid-draw frame; its
duration is intentionally tiny. (The `WeaponProgress` HUD ring reads `getSwitchProgress` /
`getReloadProgress` off these timers — see HUD system.)

**Weapon switch — ordered equip event (so a remote switch is neither late nor early, and fire can't
render before draw):** the owner's switch is two-phase — `onSetWeapon` starts `transitionTimer`
(holster, old weapon still shown) and only `onWeaponTransitionComplete` raises the new weapon
(`onWeaponEquip`) — so the new weapon comes up at `switchStart + transitionTime`. Both `onSetWeapon`
and the puppet path share `beginWeaponTransition(slot)`, so **a puppet runs the same transition and
raises the weapon at the same offset from switch-start** — timing-identical, off only by latency.
This requires delivering the switch at switch-*start*: `onSetWeapon` emits a reliable, ordered
`MSG_WEAPON_SWITCH(charId, targetSlot)` the instant the owner begins (gated on `isAuthorityFor`; host
validates owner + re-broadcasts excluding the originator), and the per-tick snapshot replicates
`getReplicatedActiveSlot()` (the **target** during a transition, not the post-animation
`activeSlotIndex`) as the drop-heal backstop. (Pitfall: an earlier version *snapped* the puppet's
weapon up instantly — fine while delivery was *late* via the post-transition slot, but once delivery
became prompt it drew a full `transitionTime` too early.) The puppet gates its cue with the **same**
condition as the owner's `onWeaponFire` — `isWeaponTransitioning() || fireTimer.getTimeLeft() > 0`
(`fireTimer` = draw-settle started by `onWeaponTransitionComplete`) — dropping any cue inside the
draw window (`fire_cue_predraw_suppressed`). The replicated path only ever runs on puppets (the owner
uses `onWeaponFire`/`onSetWeapon`), so these timers never carry two meanings on one body. Host-side
fire-timing *validation* is deferred (H3).

### Ragdoll on death (Character.enableRagdoll)

1. `setPhysicsProcess(false)` on both `Character` and `MovementController`.
2. Disable all `CollisionShape3D` stance capsules.
3. Set `collisionMask` layer 1 on each `PhysicalBone3D` so bones rest on the floor.
4. `physicalBoneSimulator.physicalBonesStartSimulation()`.

### Nameplate (`ui.Nameplate`) — generic, reusable across entity types

`ui.Nameplate` (scene `ui/Nameplate.tscn`) is a **generic** floating plate: a single `SubViewport`
rendered to a billboard `Sprite3D`, holding two UI sub-scenes — `CharacterHealthUI.tscn` (`HealthUI`,
name + health, top) and `CharacterWeaponUI.tscn` (`WeaponUI`, bottom strip). `Nameplate.refreshWeapon`
lists **every** carried weapon (one line per occupied slot, `<slot> <name> <mag>/<reserve>`, active slot
marked with a leading `>`) — a full-inventory readout for cross-network debugging, not just the active
weapon. The weapon block is for cross-network debugging (shown for all factions now; gameplay
faction-visibility filtering is later).

**It carries no entity-specific logic** — it binds to its parent purely through the
`character.NameplateTarget` interface (`getNameplateText()`, `getNameplateColor()`,
`getNameplateChangedSignal()`) plus two conventionally-named sibling nodes it discovers itself
(`Health`, `WeaponController` — same names on `Character` and `Vehicle`). So **any type reuses the same
scene/script** by implementing `NameplateTarget` and supplying its own rules. `NameplateTarget` lives
in the `character` package (not `ui`) only to avoid a package cycle — `ui` already depends on
`character`. It's instanced in **`Character.tscn`** (base, node named `Nameplate`), so
AI *and* every networked player gets one. `Character.applyNameplateVisibility` looks this node up by
that exact name (`getNodeOrNull("Nameplate")`) to hide the locally-owned body's own plate — keep the
node name and the lookup string in sync.

`Character implements NameplateTarget`: colour = own faction. `Vehicle implements NameplateTarget`:
colour = its *driver's* faction (neutral when empty/defeated), health + weapon = the *carrier's* own
(found via the shared sibling-node lookup) — see "Carrier nameplate".

**Visibility is decided at runtime by ownership, not per scene and not by the camera:** the plate
defaults visible, and `Character.applyNameplateVisibility` (deferred from `_ready`) hides it **only on
the body we locally own** — `isLocallyOwnedPlayer()` = single-player, or networked + `isAuthorityFor`,
gated to `Player` so AI is never affected. Ownership is the real signal (the camera being current is a
consequence of it); keying on it also stays correct while spectating / viewing another camera. This
replaced both the old `visible = false` override on `Player.tscn` (which also hid *remote* players'
plates) and a camera-coupled hide inside `activateCameraIfOwned`. AI and other peers' players keep the
default, so networked peers see each other's.

**It reflects replicated state with no extra net message** by reacting to signals that already fire on
the puppet apply paths:
- weapon/ammo ← `WeaponController.ammoChanged` (emitted in `applyReplicated*` on puppets).
- name/color/weapon ← `NameplateTarget.getNameplateChangedSignal()`. For `Character` that's the
  registered `nameplateChanged` (Signal0), emitted in `setFaction` (so a replicated
  `WORLD_EVENT_FACTION_SWAP` recolours on every peer, not just at spawn) and alongside `changedWeapon`.
  A carrier would emit it on driver enter/exit (replicated for free via `MSG_VEHICLE_OCCUPANCY`).

#### Carrier nameplate (implemented)

`Vehicle` reuses `ui/Nameplate.tscn` unchanged (instanced as a `Nameplate` node in `Vehicle.tscn`) and
implements `NameplateTarget`:
- `getNameplateColor()` = driver present & alive ? `Faction.color(driver.faction)` : `NEUTRAL` — the
  **driver seat occupant determines the colour; neutral when not ridden or driver exits/defeated**.
- health + weapon/ammo are the **carrier's own** `Health` / `WeaponController` — no code change in
  `Nameplate`; its `../Health` + `../WeaponController` sibling lookup resolves to the vehicle's nodes
  (same node names as on `Character`).
- emits `nameplateChanged` in `tryEnter`/`tryExit`; both run on **every peer** (host-arbitrated seat
  change), so the tint re-derives everywhere with no new message — occupancy already replicates.
- **Auto-exit when the seated occupant is defeated** ("shot through the open vehicle") is still a
  separate *Vehicle gameplay* concern, not nameplate (not built): on the occupant's `Health.died` the
  host would run `Vehicle.tryExit()` + broadcast occupancy; the plate then goes neutral *because* the
  seat emptied — `tryExit` already emits `nameplateChanged`. Damage reaching a seated occupant is
  hit/collision routing on the occupant's `Health`.

> A base `Carrier` class above `Vehicle` was considered and **deferred**: reuse is achieved through
> the `NameplateTarget` / `Controllable` interfaces (the codebase idiom), so a class hierarchy buys
> nothing while `Vehicle` is the only concrete carrier. Extract `Carrier` when a second carrier type
> (boat/aircraft/mount) actually exists and shows what is genuinely shared.

---

## Event System (EventBus AutoLoad)

`EventBus` is a global `Node` registered as AutoLoad. Any node reaches it via
`getNodeOrNull("/root/EventBus")`.

Key signals (not exhaustive — see `EventBus.java` for the full set, which also includes
`all_players_died`, `player_spawned`, `pickup_interact_changed`, `player_ammo_changed`,
`weapon_picked_up`, and the multi-character spawn/health/ammo signals used by `HUDManager`):

| Signal | Emitter | Payload |
|:-------|:--------|:--------|
| `player_died` | `Player.onDied()` | — |
| `enemy_killed` | (future use) | score: `int` |
| `player_health_changed` | (future use) | currentHealth: `float` |
| `ammo_picked_up` | (future use) | weapon index: `int` |
| `character_eliminated` | `Health.takeDamage()` | `Signal7`: victimId, victimName, victimFaction, attackerName, attackerFaction, icon, headshot |

`GameManager` connects `playerDied → onPlayerDied()` in `_ready()`.
The HUD (`HUDManager`/`CharacterHUD`) connects `characterEliminated` for the kill feed.

---

## HUD system (`com.openworld.ui`)

`HUDManager` (CanvasLayer in `HUDManager.tscn`) owns the on-screen HUD. Two pieces worth knowing:

### Situational widget visibility (declarative table + runtime overrides)

Instead of scattered `show()/hide()`, visibility is driven by a `Situation` enum — `ON_FOOT`,
`VEHICLE_DRIVE`, `VEHICLE_PASSENGER_WEAPON`, `VEHICLE_MOUNTED_WEAPON` (the in-vehicle case is derived
from `Vehicle.getWeaponMode()` in `situationForVehicle`). A code table `BASE_LAYOUT`
(`EnumMap<Situation, Set<String>>`) lists which **table-managed widgets** are visible per situation.
Widgets are direct `Control` children discovered by **node name** in `_ready` (`FootHUD`, `VehicleHUD`,
`WeaponSlotsUI`, `DamageIndicator`, future `Minimap`); `Feed`/`StatusFeed`/`Crosshair`/`WeaponRadialMenu`
are intentionally excluded (feeds are always-on; the crosshair self-gates in `refreshCrosshair`; the
radial menu is a self-managed input overlay). **Player health (`FootHUD`) is in every vehicle situation**
so it stays visible while riding (the seated occupant is exposed). Add a widget = drop the node in
`HUDManager.tscn` + add its name to the relevant `BASE_LAYOUT` sets — no new code.
Runtime flexibility: `setWidgetEnabled(id, bool)` / `clearWidgetOverride(id)` (a `widgetOverrides` map
that wins over the table) force a widget on/off regardless of situation (per-carrier/gameplay tweaks).
The table is **code, not an exported `Dictionary`** — a nested generic `Dictionary` export crashes the
godot-kotlin-jvm registration scanner (see Known Quirks).

### Weapon switch/reload progress ring (`WeaponProgress`)

`WeaponProgress` (`ui/WeaponProgress.tscn`, a radial `TextureProgressBar` centered on the crosshair —
renamed from the old unused `WeaponReloadProgression`) polls the active player's `WeaponController` each
frame: it shows + fills 0→100% during a weapon switch (`getSwitchProgress`) or reload
(`getReloadProgress`), hidden otherwise (switch tints cyan, reload amber). The ring texture is generated
procedurally in `_ready` (a transparent annulus), so no ring asset is needed. Not table-managed (it
self-hides); wired in `HUDManager.wirePlayer` like `WeaponSlotsUI`. The progress getters return -1 when
their timer is idle. The ring texture is generated by default, but assign an `@Export ringTexture` (a
baked PNG) to use an asset instead (cheaper load, exact look). **Centering:** with
`nine_patch_stretch = false` a `TextureProgressBar` draws its texture at **native size, top-left aligned**
(it does NOT stretch to or centre within the control rect). So the control rect must be **symmetric AND
exactly the texture size** — `WeaponProgress.tscn` uses offsets `-32/-32/32/32` (a 64 px rect) to match
`RING_PX = 64`; the radial fill pivot (`radial_center_offset` 0,0 = rect centre) then coincides with the
texture centre on the screen centre, lining up with the crosshair dot. A rect *larger* than the texture
(e.g. the earlier `±34` → 68 px) leaves the 64 px ring pinned top-left, ~2 px off-centre — the bug. Keep
the scene offsets and `RING_PX` in sync, and don't override the offsets in `HUDManager.tscn` (use the
scene defaults). Same rule for a baked `ringTexture`: make its pixel size equal the rect.

### Damage-direction indicator (`DamageIndicator`)

Industry-standard directional hit cue: on local-player damage a red arc appears around the crosshair
**rotated to the attacker's bearing** (top=front, sides=left/right, bottom=behind), fading over
`fadeSeconds`; repeated hits from one bearing stack opacity up to `maxAlpha` (a small pooled set of arcs
handles multi-source hits). Bearing is computed relative to the player camera's facing, so it stays
correct as the camera turns.

**Data path:** `EventBus.characterDamagedFrom(CharacterInfo victim, Vector3 sourceWorldPos)` — emitted in
`Health.applyDamage` (single-player/host, attacker world pos threaded through
`ImpactManager.processHit` → `Health.takeDamage`; weapons supply it via `WeaponItem.resolveAttackerPosition`,
explosions via the blast center). `HUDManager.onCharacterDamagedFrom` filters to the local player and
calls `DamageIndicator.onDamagedFrom`. **Networked:** the host is the single broadcast site —
`Health.applyDamage` calls `NetworkManager.broadcastDamage(victimId, damage, hasSource, source)` for every
server-applied hit (host-originated AND client-relayed), and `MSG_DAMAGE_BROADCAST` now carries the
attacker world position (`hasSource` u8 + Vec3 — cheaper than a UUID and exact); the victim's client
re-emits `characterDamagedFrom` in `handleDamageBroadcastMessage`. The per-hit broadcast moved **out** of
`handleDamageRequestMessage` into `applyDamage` (the relay path flows through `applyDamage` on the host
anyway), so it is now the one place the hit cue + direction are sent.

---

## MovementController flags (Player vs AICharacter)

| Export flag | Player | AICharacter |
|:------------|:------:|:-----------:|
| `worldSpaceMovement` | `false` | `true` |
| `faceCameraInCombat` | `true` | `false` |

Player input is camera-relative (rotated by `camRotation`).
AI input is world-space (set directly by the AI FSM).

---

## Godot-Kotlin-JVM Specifics

- Every class exposed to Godot needs `@RegisterClass`, methods need `@RegisterFunction`,
  properties need `@RegisterProperty` + `@Export`.
- Signal declarations: `Signal0 / Signal1<T> / … / Signal7<…>` declared as `public final` fields.
- Class registration is byte-compatible across package moves: `@RegisterClass(className=…)` is
  an explicit string (and the default is the simple class name), both package-independent — so the
  `com.openworld.*` reorg did not change any registered type name.
- Always run `./gradlew build` before opening the editor so registration is up to date.
- `GD.lerp`, `GD.lerpAngle`, `GD.clamp`, `GD.randf`, `GD.randfRange` are the GDScript global equivalents.
- `StringName` is used for signal names and node lookups; `NodePath` for node paths.

---

## Known Quirks / Gotchas

- `AICharacter.onDied()` must set `isDead = true` **before** calling `super.onDied()` (which stops
  physics processing). If `isDead` is not set first, `gatherInput` can still run on the
  same frame via a pending physics callback.
- **Do not export a nested/raw generic `Dictionary` from a `@RegisterClass`** (e.g.
  `@Export Dictionary<String, Dictionary>`). The godot-kotlin-jvm `classGraphSymbolsProcess`
  registration scanner chokes on the raw nested type parameter and dies with `Java heap space` /
  `Requested array size exceeds VM limit` (NOT a real memory shortage — bumping `org.gradle.jvmargs`
  does not help). Use a flat `Dictionary<String, String>` (compose keys, e.g. `"a>b"`) — the shape
  the codebase already uses (`MeshConfig.boneHitMultipliers`). This bit `FactionTable` (D3).
- **A `.tscn`-embedded sub-resource is SHARED across every instantiation of that scene** (Godot
  reference semantics), so an *identity/mutable* Resource embedded in a scene (e.g. the
  `CharacterInfo` on `Character.tscn`/`AICharacter.tscn`/`Player.tscn`/`Vehicle.tscn`) is the **same
  object** on every instance — mutating one (stamping a per-instance `characterId`) rewrites them all.
  This collapsed all streamed traffic onto one id (stuck/can't-exit/ownership-migrates — I3b). **Own
  identity in code, not the scene:** spawn code builds a fresh `new CharacterInfo()` before `addChild`,
  and `Character._ready`/`Vehicle._ready` **privatize** a scene-supplied (empty-`characterId`) one via
  `CharacterInfo.copyOf` before stamping the UUID. **Do NOT use `resource_local_to_scene = true` on a
  JVM-scripted Resource** to force per-instance copies — its instantiate-time `duplicate()` reenters the
  godot-kotlin-jvm `TransferContext` shared buffer and throws `Shared Buffer Error: JVM expected a LONG
  but received a BOOL` (the int `ownerPeerId` read colliding with the bool `resource_local_to_scene`
  write). Copy fields in plain Java instead. Read-only shared configs (`VehicleConfig`,
  `AIBehaviorConfig`) are fine embedded/shared — never mutated per-instance, so leave them as-is (and
  do not add `resource_local_to_scene` to them either).
- `AimStayTimer` in `PlayerController.gatherInput`: uses `isActionJustReleased` (not `isActionPressed`)
  to start the timer so it starts exactly once and doesn't restart every frame after it ends.
- `WeaponController.onWeaponFire` saves and restores `aimRay3D` rotation when applying spread;
  `AICharacter.snapAimRay` pre-positions the ray before firing so the spread rotation must be
  skipped for AI (`useWeaponSpread = false`).
- `ParticleManager` pool containers must be named exactly after the `SurfaceType` constant
  (e.g. node named `"FLESH"`, not `"Flesh"`). A missing container is silently skipped in `_ready()`.
- To add a new surface type: (1) add constant to `SurfaceType.java`, (2) add a child container
  under `ParticleManager` in the editor with `GPUParticles3D` children, (3) for world geometry
  attach `HittableBody` script and set `surfaceType` in the inspector.
- `ImpactManager.processHit()` is the single place to add new hit effects (decals, sounds,
  physics impulse). `WeaponController` does not need to change for any of those additions.
- `PhysicalBoneSimulator3D` children must be added to `aimRay.addException()` in both
  `Character._ready()` and `AICharacter._ready()` (for SightRay) to prevent self-hits.
- Process-global static state that holds Godot **resources** (e.g. `IconRegistry.ICONS`, a static
  `Map<String,Texture2D>`) outlives the engine and surfaces as `1 resource still in use at exit` /
  `ObjectDB instances leaked at exit`. Clear such caches on shutdown: `IconRegistry.clear()` is
  called from `GameManager._exitTree()` (the AutoLoad leaving the tree at engine teardown). Add the
  same release for any future static Godot-object cache. (`Color`/`Vector3`/`Quat` statics are value
  types — they don't leak.)
- **Swapping a node must free the outgoing one.** `Character.attachController` /
  `Vehicle.attachController` replace the controller with `removeChild(old); old.queueFree();` — a
  `removeChild` *without* the free leaves a parentless, never-freed node (Godot reports it at exit as
  `Leaked instance: Node … - removed with remove_child() but not freed`, and any resource it holds —
  e.g. its `.java` script — as `resources still in use`). This bites every controller swap: puppet
  spawn (→ `NetworkController`), player-disconnect (→ bot `CharacterController`), scene
  `PlayerController` → `NetworkController`. The retain-and-reuse path is the separate
  `detachController()` (removes, returns, does **not** free — used by vehicle enter/exit hot-swap).
  Same rule for any other `removeChild` that isn't handing the node to a new parent.
- **A 3D audio playback still running when its node is freed mid-session leaks at exit.** Freeing an
  `AudioStreamPlayer3D` while it is playing leaves the `AudioStreamPlaybackWAV` + its stream held by
  the audio server (`Leaked instance: AudioStreamPlaybackWAV` / `Resource still in use:
  Rifle_reload.wav`). This is **networked-only** in practice: the client frees its pre-placed `Player`
  on connect (`NetworkManager.removeLocalPrePlacedPlayer` → `queueFree`) while the spawn-time
  equip/reload SFX (`WeaponController` plays `getReloadAudio()` on equip) is still sounding — in
  single-player no body is freed mid-session, so the cue always finishes. Fix: `WeaponController._exitTree`
  calls `weaponAudio.stop()` (guarded by `GD.isInstanceValid`), releasing the playback on every
  teardown path. **But `stop()` from a *different* node's `_exitTree` is unreliable when a whole body
  subtree is freed at once** (E1 zone-unload frees armed AI mid-session; the player's gun audio leaked
  the same way at app exit — fire SFX `Rifle_fire.wav`): the sibling `WeaponAudio` `AudioStreamPlayer3D`
  can exit the tree *before* `WeaponController._exitTree` runs, orphaning its in-flight playback first.
  **Mid-session fix: the audio node stops *itself* on its own `tree_exiting`** — `WeaponController._ready`
  connects `weaponAudio`'s `tree_exiting` → `weaponAudio.stop`; that signal fires while the node is still
  valid and in-tree, so the playback is released no matter who frees the body or in what order (despawn,
  disconnect, zone-unload). Belt-and-suspenders: `WeaponController.silenceAudio()` (public) is also called by
  `WorldZoneManager.unload` before it frees/recycles a body (stop a touch earlier, while fully in-tree).
  For any other node that plays audio and can be freed while playing, prefer the **self-stop on
  `tree_exiting`** pattern over a parent/sibling `_exitTree` stop.
  **App-exit does NOT go through `tree_exiting`** (this was the residual leak): at real quit the
  godot-kotlin-jvm runtime is torn down ("Cleaning JVM Memory…") *before* the final SceneTree node teardown,
  so a JVM-registered `tree_exiting` → stop never runs for any body still alive at quit — the local player's
  (or any still-loaded AI's) in-flight reload/fire playback leaks (`Resource still in use: Rifle_reload.wav`).
  The reliable hook is the **root `Window.close_requested` signal**, which fires while every node and the JVM
  are still alive: `GameManager._ready` connects it to `onCloseRequested`, which does **one generic
  depth-first sweep from the root, calling `stop()` on every `AudioStreamPlayer{,2D,3D}`**. This is
  deliberately *not* weapon-specific — any future audio (footsteps, engine, ambient, UI) is covered with **no
  per-entity wiring**, so a new sound-emitting node never needs its own quit handler. (`_notification`/
  `NOTIFICATION_WM_CLOSE_REQUEST` is *not* overridable in this binding — use the Window signal. AutoLoad
  `_exitTree` is too late: AutoLoads are freed *after* the main scene, so the player's `weaponAudio` is
  already gone — that's why static caches like `IconRegistry` clear fine there but live-node audio can't.)
  **Division of labour:** app-exit = this one global sweep; **mid-session** frees (zone unload, despawn,
  disconnect — app keeps running, so `close_requested` has not fired) = each audio node self-stops on its own
  `tree_exiting` (a one-liner, only needed on nodes that can be freed *while playing*). The two are
  complementary; neither replaces the other.
- Weapon scenes are discovered dynamically: `WeaponController` iterates children of
  `WeaponAttachment` at `_ready()` — add a new weapon by adding a `Marker3D` wrapper with a
  `WeaponItem` subclass scene (e.g. `FirearmItem`) as its only child.
- `WeaponPickup` finds its `WeaponItem` child lazily in `onCharacterEntered` (not `_ready()`)
  because `WeaponController.spawnPickup()` reparents the weapon after `addChild()`, so `_ready()`
  fires before the weapon is attached.
- `Pickup.pause()` calls `setFreezeEnabled(true)` (not `setFreeze`) — the Kotlin/JVM binding
  exposes the Godot 4 `freeze` property as `setFreezeEnabled / isFreezeEnabled`.
- `ENetConnection.createHost/createHostBound` take `(… maxPeers, maxChannels, inBandwidth,
  outBandwidth)` — all-int positional args. Putting the channel count one slot too far right
  silently caps outgoing bandwidth at N bytes/s (ENet then throttle-drops unreliable packets
  into multi-second bursts). `connectToHost` differs: its 3rd param IS `channel_count`.
- `NodePath.toString()` returns `"NodePath(<subnames>)"` — the `:property` subname part only,
  which is **empty for plain node paths** — NOT the path string. Use `nodePath.getPath()`
  (the Kotlin `path` property) whenever a path string is needed, e.g. `getPath().getPath()`
  on a Node. `StringName.toString()` is unaffected (it calls the native string operator).
