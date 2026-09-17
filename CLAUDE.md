# CLAUDE.md — Codebase Reference

Third-person shooter experiment using **Godot 4.7** with the **[godot-jvm](https://github.com/utopia-rise/godot-jvm)** binding
(`1.0.0-rc1`, shipped as the in-project `addons/jvm/` GDExtension; docs: https://godot-jvm.dev/en/1.0/).
All game logic is written in **Java** (a few stubs in Kotlin). **GDScript is used for EDITOR TOOLING
ONLY** (decided 2026-09-13): godot-jvm rc1 ships `@Tool` but no editor API (0 `godot/api/Editor*`
classes), so editor plugins, docks and gizmos are GDScript — `addons/road_kit/` is the first — and
they call into Java or external tools for logic. Never GDScript for runtime gameplay.

---

## Build & Run

```bash
./gradlew build          # compile + generate the registrars Godot loads
```

Open `project.godot` with the **stock Godot 4.7.2 editor** —
`/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64`, which is also every tool script's `GODOT`
default (`blender/tools/env.sh`) and what every headless check must run under. JVM toolchain:
**JDK 17**.

godot-jvm **`1.0.0-rc1`** is a **GDExtension add-on** that ships with the project in `addons/jvm/`,
so the **standard Godot editor** is all that is needed — no custom engine build. Keep the Gradle
plugin (`build.gradle.kts`: `com.utopia-rise.godot-jvm`) and the `addons/jvm/` add-on on the same
version (both `1.0.0-rc1`) and upgrade them together.

Scenes/resources reference scripts by their **source `.java` path**
(`res://src/main/java/com/openworld/.../X.java`). Under godot-jvm `1.0.0-rc1` that is the *only* way for a
project class: `.gdj` registration files are now emitted **only for registered classes coming
from external dependencies**, of which this project has none — so `gdj/` stays empty and is not
a fallback. Source of truth is always `src/main/java/` — never edit generated files.

---

## Vocabulary — there are TWO world concepts, not four (2026-09-05)

`district` is **retired as a mechanism**. It described a 504 m grid tile with neighbours, shared
edges, a `.seam.json` and a registry position, and the world is one continuous island now
(`WORLD_REBUILD_PLAN.md` step 3: *author one continuous world, let the export cut it* — with the
ground authored once there is no seam to verify). It survives only as a **place name**, the thing it
always meant to a player: `zone_id = "harbour"`.

| concept | what it is | where |
|---|---|---|
| **zone** | the ONE streaming unit, at any scale — a neighbourhood, a car park, a building interior. Scale-free and grid-free: it has a centre, load/unload radii, spawn configs and optional geometry. "A cell inside a cell" is just *a zone inside a zone*; it needs no new type. | `world.Zone`, `world.ZoneMarker`, `world.ZoneManager` (AutoLoad), and the Blender-side `region_` marker that bakes into one |
| **piece** | the authoring/bake unit: one `.blend` -> one baked `.tscn`. A build-pipeline word, not a gameplay one, and it collides with nothing. | `piece_registry`, `build_piece.sh`, `world/pieces/`, `PieceBinaryConverter` |

Renamed with it, so nothing keeps the old spelling: `WorldZone*` -> `Zone*` (213 references),
`DistrictBinaryConverter` -> `PieceBinaryConverter` (its `districtsDir` export is `piecesDir`),
`MultiDistrictStreamTestHost` -> `MultiZoneStreamTestHost`, `hosts/ConvertDistricts.tscn` ->
`hosts/ConvertPieces.tscn`, and the baked-output folder `world/districts/` -> `world/pieces/`.
**`IntersectionZone` is a different thing** (an `Area3D` marking a junction, `GROUP =
"intersection"`) and was deliberately left alone.

Prose below and in `blender/*.md` still says "district" where it is describing **history** — the
archived 6x6 grid world, `District_*.blend`, `check_seams.py`. That is left standing on purpose:
rewriting it would make the record lie about what was actually built. New writing uses **zone** and
**piece**.

## Source Layout

All code lives under the **`com.openworld`** root, organized **by domain/concern** (not layer-first).
Scripts are referenced from scenes by `.java` path (`res://src/main/java/com/openworld/.../X.java`);
`.gdj` is dependency-only under godot-jvm `1.0.0-rc1` and unused here. The two reorg scripts (`tools/reorg_stage1.py`, `tools/reorg_stage2.py`)
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
  world/          # world types: HitInfo, HittableBody, SurfaceType, SpatialEntityGrid (AutoLoad),
                  #   WaterVolume (swim/float Area3D), WorldBounds (the logic wall)
    manager/      #   world-level singleton systems: Impact/Particle/Decal/Explosion/BulletTracer
  item/           # Pickup (Node3D item base) + PickupBody (the RigidBody3D it rides in the
                  #   world — W15), AmmoRefill station
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
  debug/          # DebugHarness (temporary test-spawn harness); headless test stands —
                  #   DriveTestHost (vehicle physics soak, fixed timeline) and
                  #   HandlingTestHost + ScriptedInputController (step-by-step handling
                  #   cases, each with its control — hosts/HandlingTest.tscn)

src/main/resources/com/openworld/  # .tscn/.tres (internal layout NOT yet remapped to new java pkgs)
  character/Character.tscn, Player.tscn, AICharacter.tscn
  weapon/AR4.tscn, PI52.tscn, …    world/World.tscn, WorldSystems.tscn    ui/…
src/test/java/com/openworld/net/   # headless unit tests for the engine-free net logic
```

> AutoLoads (`project.godot`): `EventBus`, `GameManager` (`game`), `MissionManager`
> (`game.mission`), `NetworkManager` (`net`), `PlayerRegistry` (`game`), `SpatialEntityGrid`
> (`world`), `FactionManager` (`character`), `ZoneManager` (`world`),
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

**`controlRotation` is a WORLD rotation in degrees and positive pitch means LOOK UP** — since
`AIM_PLAN.md` W3, and both halves used to be false. The rig node's world basis is stated outright
every frame (`setGlobalRotation(ZERO)`), so `setAsTopLevel`'s frozen frame no longer makes the yaw
a local one, and the two cancelling 180° Y flips are gone from `Character.tscn`, so nothing negates
the pitch downstream. See the W3 section under "Animation" for the whole change and its
measurements.

Recoil here is the AIM layer only — the VISIBLE weapon kick is a separate spring on the firing arm
(`character.WeaponRecoilModifier`, W27), and the weapon's own moving parts are a third layer.
Recoil is stored as `recoilPitch / recoilYaw` on `CameraController` and decays via
`GD.lerp(…, 0, recoilRecoverySpeed * delta)` each frame — fully separate from the
mouse-intent `pitch/yaw` so recovery never fights aim. `recoilPitch` is **added** per shot
(`recoilPitch += pitchKick`), because a kick is upward and positive pitch is up; it was subtracted
while `Pivot`'s flip negated pitch. `recoilRecoverySpeed = 8.0` gives a snappy per-shot kick that
clears in ~0.3 s; sustained fire builds a learnable upward drift (~1.7° at full spray) rather than a
persistent offset. **`VehicleCameraController` is the exception and still subtracts** — its rig is
the vehicle's own, keeps the `Pivot` flip, and shares no state with `ControlRotation`.

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

### Zone streaming — ZoneManager / Zone / SpawnPool (`com.openworld.world`, E1)

As a player walks toward a populated area an AI group streams in; walking away streams it back
out — no scene stutter, no O(n) tree scans, host-authoritative + replicated spawns. Five pieces:

- **`Zone`** (`@Script extends Resource`) — placeholder-AABB zone data: `zoneId`,
  `size` (full XZ extents of the spawn box; *center is the marker's world position*),
  `loadRadius`/`unloadRadius` (hysteresis — unload **>** load avoids boundary flicker), nullable
  `geometry` (PackedScene, cosmetic), and two collections built with class tokens —
  `VariantArray<SpawnConfig> spawnConfigs` (ambient groups) and
  `VariantArray<NamedCharacterConfig> namedCharacters` (story AI with stable ids for Part F).
- **`SpawnConfig`** — `faction`, nullable `behaviorConfig` (else AICharacter `DEFAULTS`), `count`,
  `weaponScenePath` (AR4 default). Ambient AI share the `AICharacter.tscn` archetype.
- **`NamedCharacterConfig`** — stable `characterId`, `displayName`, `faction`, nullable `scene`
  (else AICharacter.tscn), `behaviorConfig`, `weaponScenePath`, `offset` (relative to marker).
- **`ZoneMarker`** (`@Script extends Node3D`) — the inspector-friendly in-scene anchor
  (a `Resource` AutoLoad can't take an inspector-assigned `.tres`, and a marker is positioned by
  dragging). Holds `@Export Zone zone`; **its global position is the zone center**. Registers
  with the manager in `_ready()`, deregisters in `_exitTree()` (the same register-with-AutoLoad
  idiom `Character` uses with `SpatialEntityGrid`).
- **`SpawnPool`** — plain Java helper (not an AutoLoad, not `util/ObjectPool` which throws on
  exhaustion and isn't tree-aware), owned by the manager. `acquire()` polls a `Deque<AICharacter>`
  (recycling a detached body, validated by `isInstanceValid`) or instantiates fresh;
  `wasLastAcquireRecycled()` lets load skip re-equipping an already-armed recycled body;
  `release(ai)` removes from tree + enqueues up to `poolCapacity`, else `queueFree`. **Only healthy
  bodies are pooled** — dead AI follow the normal death/ragdoll→free flow, so a recycled body never
  needs un-ragdolling.
- **`ZoneManager`** (`@Script extends Node`, AutoLoad) — mirrors `SpatialEntityGrid`'s
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
and `unloadRadius ≈ loadRadius + hysteresis margin (~150 m)`. `ZoneManager.warnIfMisSized`
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
(`StreamTask` in `ZoneManager`), processed every physics frame under a time budget
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
parse dominates stream-in time even on a worker thread. `PieceBinaryConverter`
(`hosts/ConvertPieces.tscn`, one-shot batch job in the `WorldBaker` idiom, mtime-skips
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
marker child, `queueFree`d on unload). Anything authored directly into the `ZoneMarker` *scene*
(the debug box from `showDebugVolume`, or any mesh you drop under the marker node) is **static scene
content — it never streams**; it is the persistent zone *footprint/outline*. To make a mesh stream
in/out, assign it to the Zone's **`geometry`** field, not as a marker child (a Blender-exported
zone-chunk `.tscn`, same convention every district piece's `geometry_path` already uses). Zones also
do **not** carry their own navigation — AI use the level's `NavigationRegion3D`; nav is a
parent/world concern.

**Body recycling is OFF by default (`recycleBodies`, EXPERIMENTAL).** Reusing a full character body
subtree (detach via `removeChild`, re-attach via `addChild`) is **unsafe** in godot-jvm: the
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

**Debug visualization + walk-test setup:** `ZoneManager.debugLog` (exported, on) prints each
load/unload decision, an approach-distance line while a player is near, and per-load recycled-vs-fresh
+ pool-idle counts. `ZoneMarker.showDebugVolume` (exported, on) builds at runtime a translucent
box (the spawn volume, `zone.size`) plus flat rings at `loadRadius`/`unloadRadius`; the box tints
**green while streamed in, cyan while idle** (driven by `setLoadedVisual` from the manager) — so you
can see a zone and walk into it. Both are pure debug aids, off via their export flags for shipping.
The `DebugHarness` **F12** key drops a code-built `Zone`/`ZoneMarker` in front of the
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
`ZoneManager.maintainTraffic` reclaims below `Y = -30`). Falling off a road or off the
ArtDeck now falls through, same as any other gap in authored ground — see
`AUTHORING_GUIDE.md` for the districts/void-cell design this replaced it with.

> **A SEABED IS NOT A SAFETY FLOOR** (island v3, 2026-08-30 — `blender/WORLD_REBUILD_PLAN.md`).
> `Island_base` has a `Seabed` sheet under the whole sea and it does not reopen the above. A safety
> floor is *invisible*, *collision-only* and sits a metre under the **visible ground**, so a body
> that falls through a hole lands somewhere it cannot see with no way back — which is why it was
> removed. A seabed is the terrain **continuing past the waterline**: visible, sloped, walkable in
> both directions, and it does not exist under the island at all (`island_v3_terrain.Terrain
> .surface` returns the land wherever there is land). Falling off a cliff onto land still falls.
> Two rules came with it, both cheap to get wrong: a ground sheet must be forced to **face up**
> (`recalc_face_normals` infers "out" from the shape, and an open sheet with no skirt came out
> entirely inverted — invisible from above AND unwalkable to Recast, while its collision proxy
> worked perfectly), and a solid-but-unwalkable surface takes the `-noped` marker (below) so it
> does not bake a 4 km walkable sheet under the sea.
>
> **The beach is the part that is easy to get wrong while fixing the fall-through.** The land stops
> 0.60 m above the water, so a sea floor starting at the waterline rings the island with a 0.80 m
> wall — swimmable *to*, impossible to climb (`MovementController.stepHeight` is 0.35 m), i.e.
> falling out of the world replaced by being locked out of it. `SHORE_Z` starts the floor 0.20 m
> **under the land**: one step down onto ~27 m of dry sand before the water. Measured on 16 shore
> rays: worst natural-coast step **0.206 m**, 0 samples with no surface.
> `blender/tools/check_island_water.py` is that layer's gate (sea-below-land, continuity, the beach
> step, cliff/quay classification, and the markers).
>
> **The water shader fades its detail with distance** (2026-09-16, user-reported "repeated small squares far
> away"). `world/water.gdshader` samples 256 px seamless noise in WORLD space (a tile every 5 m in DebugWorld,
> 40 m in World; foam every 2 m) and read the waves at one fixed mip level, so far water aliased into a speckled
> grid of repeated pixel squares — measured on a Vulkan screenshot, not guessed. Now fragment samples use
> automatic mipmaps with anisotropic filtering, a second layer at `far_scale_ratio` (0.125 = 8x bigger features)
> fades in between `detail_fade_start` and `detail_fade_end` (40-320 m from the camera), the foam shape does
> the same, and the normal map flattens toward `far_normal_strength` far out. Near water is unchanged
> (before/after screenshots compared). Vertex displacement still uses the fixed LOD (no derivatives there).
>
> **All water is ONE swim volume** (`water_sea`, baked to a `WaterVolume`), and one box can cover
> the sea, the bay and the lagoon because the land is above every part of it: a box whose TOP is the
> water line cannot touch a character standing on land. `Character` decides wade-vs-swim from the
> true depth under the body, so the beach wades and only real depth swims. **`WorldBaker.buildWater`
> used to build a bare `Area3D` on the default collision mask** — no script, so `setInWater` was
> never called, and mask 1 never sees a character body (they are on `CollisionLayers.CHARACTER`).
> Either half alone was fatal, and together they looked exactly like a swim feature that was never
> written; `SwimState` and the buoyancy spring had been complete since I1.
>
> **The world edge is a LOGIC WALL, not an invisible collider** — `world.WorldBounds`, baked from a
> `bounds_<id>` marker. A warning band inside `warnMargin` (no physics), hard position clamp past the edge with
> only the OUTWARD velocity component cancelled (so swimming home is unresisted), and a `floorY`
> kill-Z that puts a body back at `PlayerSpawn`. A collider would also stop bullets, ragdolls and
> vehicles, would give a body sliding along it no "leaving the area" moment, and — the deciding one —
> could never recover a body that is ALREADY outside. **The wall stands inside the sea floor's own
> edge, not at the world square**: `SEABED_MARGIN` 288 m puts the floor at ±2304 and
> `BOUNDS_INSET` 144 m puts the wall at ±2160 — a 4.6 km sea with 202 m of water at the
> tightest heading and 498 m at the median, over 1 km only on the diagonals. Both extremes were
> walk-tested: the wall AT the world square read as a fence 700 m offshore, and a floor out at
> the ±3800 m budget read as 2.0 km of empty ocean. 3.5 km is not available — the land's own
> bounding box is 3.72 × 3.94 km, because the offshore airport reaches y = −1976 m.
> **ONE physical rule, the hard wall; the band only WARNS** (2026-09-16, PLAN.md P0 0.3 then 0.6).
> User-reported as "an invisible collision block on DebugWorld's loop_p005 corner": `confine` used to
> cancel the outward velocity whenever ANY correction was non-zero, so the soft band's INNER edge was
> a wall with no shape for debug drawing to show (a player stalled at z -363.8, a driven car at
> -356.8). 0.3 made the band a nudge; 0.6 (user decision: "remove the soft push entirely, only warn")
> DELETED it — `softMargin`/`pushSpeed` and the RigidBody3D velocity bias are gone, because a physical
> push nobody can see is indistinguishable from a bug. Past `halfExtent` the position is clamped and
> only the outward velocity cancelled; nothing inside the wall is ever moved. `warnMargin` (80 m;
> DebugWorld 40) raises `EventBus.leavingArea(distanceToWall)` / `returnedToArea` on the EDGE for each
> locally-owned player, and `ui.AreaWarning` (self-gated, not in `BASE_LAYOUT`) shows "LEAVING THE
> AREA" with the distance and a red vignette deepening toward the wall. Local per peer, no message.
> `WorldBounds.showDebugVolume` (on in DebugWorld; DebugHarness **Shift+F2** toggles it) draws the wall
> red and the band's inner edge yellow; `debugLog` prints each hard correction (throttled per body)
> and the warning edges. `WorldBounds.get()` + `distanceToWall(pos)` are the one owner of "how far is
> the edge". `tools/godot/check_world_envelope.gd` asserts every Road Kit station + 18 m of paving
> clears the warning band. Gate **`tools/godot/probe_world_bounds.gd`** 16/16: a Player, an
> engine-driven RigidBody3D and a swept CharacterBody3D keep their FULL speed right up to the wall and
> are turned back at it, `leaving_area` fires once (for the player only) and `returned_to_area` once
> on walking back, and the HUD warning shows and hides; `-- --control` (a velocity cancel in the band)
> fails 5. `HandlingTest.tscn`'s three wall cases unchanged.
> The *accurate*
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
authoring): `ZoneManager.spawnLanes(name, center, maxDist)` matches exact first, else
prefix-collects plain lanes (never turn connectors) whose entry is within `unloadRadius`, then keeps
only those a car can drive at least `unloadRadius` from (`util.LaneReach`, over the same
`LaneGraph.successorsOf` the AI follows — name order put cars on lanes with no successor).
`spawnTrafficCar` is the ONE placement owner (zone load and top-up alike): a per-zone rotating
cursor over those lanes, a slot with nothing within `TRAFFIC_SPAWN_CLEARANCE` (10 m, the obstacle
ray's reach), the car **faced along its lane**, and no spawn at all while a named route matches no
lane yet. See "Ambient spawn placement" under Terrain3D below.
**All lane lookups are registry reads, never scene-tree walks:** `VehicleRoute._ready/_exitTree`
register/deregister with a `TreeMap` on `ZoneManager` (the Character↔SpatialEntityGrid
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
that runs the gate (31 checks since B9: the pure self-tests, the headless pipeline smoketests and every Godot plugin test; the Blender panels it used to draw are retired). The worked example of all four link types is `assets/world_source/pieces/RoadKitSample.roads.json`; the editing how-to is `addons/road_kit/README.md`.
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

**Style, markings and the Path3D preview (2026-08-27, `blender/ROAD_STYLE_AND_PATH_PREVIEW.md`).**
Three things landed together; the doc is the design of record and its §7 is what actually shipped.

- **The exported Path3D IS the lane, now.** `WorldBaker` builds every `Curve3D` an ambient car
  drives from the `.lanekit.json` `curve` block, and `point_export` used to refit those handles
  from the chord through the neighbouring stations — discarding the authored tangents
  (`station_axis`, the R-key bend) the road is actually swept from. At an open end that chord sat
  **70°** off the true heading: measured **22.57 m** of error on the addon's own sample network,
  with a green gate and perfect geometry. Handles now come from the lane's own sampled tangent,
  length least-squares-fitted, subdividing only where a cubic cannot follow to 0.05 m → **0.09 m**
  worst, with *fewer* control points. Two rules fell out and both are load-bearing: the fit error
  must be measured **curve-to-lane**, not lane-to-curve (a cubic that bulges wide and comes back
  passes near every sample while sitting a lane's width off the road), and the split must
  **bisect** (splitting at the worst sample slivers a span whose real problem is a bad handle).
- **`Preview ▸ Geometry` draws the Path3D by default**, not the lane polyline — the two are
  different objects, and drawing the wrong one is how the above survived. `Both` overlays them with
  orange rungs where they part; `path_deviation` is the matching gate finding, from the same
  function, so picture and finding cannot disagree.
- **One material registry.** `point_build`'s parallel `rka_*` materials are gone; roads now use
  `kit_common.MATS` like every other builder — which had carried `M_LineW`/`M_LineY`, described in
  its own source as lane lines, with **no user at all**. `RoadData` gained a style slot per layer
  (a datablock NAME, so `.roads.json` round-trips; blank = default; a missing name falls back AND
  warns), `median_style` moved from the point to the road as an enum
  (`NONE`/`PAINT_DOUBLE_Y`/`RAISED`/`WALL`), and **lane markings are built at last** from
  `lane_profile.marking_runs`, which had computed every painted boundary since the profile model
  landed and which nothing had ever swept. Dashes are cut in Python (the addon's own rule: Python
  owns the curve, GN only sweeps); paint is lifted `PAINT_Z_BIAS` and is deliberately **not** in
  the collision proxies.
- **A profile asset replaces a layer's parametric band with a swept section the artist modelled**
  (`GN_PointProfile`, `point_style`, `assets/world_source/kit/road_kit.blend` via
  `tools/build_road_kit.py`, library-linked). SWEPT, never tiled — rigid pieces round a 9 m corner
  sit ~12.7° apart and open a real ~7.8 cm gap at every joint, which is what retired the previous
  model's asset style; tiling is for lamp posts, and that is `GN_PointAssets`. Three measured
  gotchas: `Curve to Mesh` **drops the profile's materials** (zero slots, even from a two-material
  section — so the addon reads it off the asset), `obj.bound_box` is **stale on a freshly linked
  object** (reported a 0.32 m kerb as 2.32 m — read the curve data), and an asset layer has no
  `WidthAttr` so it **bypassed `layer_has_content`** until `ASSET_REQUIRE` gave it the same gate
  (a named barrier was building along an at-grade pedestrian street).
- **The `JCT_*` Empty is a handle and now sits where the junction is.** It was written once at
  `Make Intersection` and never re-derived, while `JunctionSolve.centre` recomputes the same
  centroid every solve — two owners, one frozen: dragging one mouth 42 m left the grip **10.44 m**
  off, so G and R pivoted on a point with nothing there (and `Auto Setback`, which moves every
  unlocked mouth, caused it immediately). It now follows the centre at Build, at Auto Setback and
  on live settle, moving no mouth. Z rotation is **unlocked** (scale and out-of-plane rotation stay
  locked, which is what the original lock was actually right about) so a whole crossing can be
  turned; `stamp_baseline` moved to the point's **parent frame** so that gesture promotes **0**
  arms to MANUAL instead of all of them, while a hand rotation of one arm still promotes exactly
  that one.

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

**And the gesture round, 2026-08-26** (`ROAD_POINT_GRAPH.md` §8i; six user reports). §8f–§8h were
all *one fact with two owners*; §8i is the other face — **a fact the artist was made to declare
that the model already knew**, or **an ordering the tool imposed because nobody had asked the
question from the other side**:

- **`Extend Road` works from EITHER end.** `_next_point_name` only ever hands out the next free
  index, so a new point was always born at the *tail* of the names however the artist got there:
  extending `..._p000` misfiled it at the far end of a road it starts, and (the head has no `prev`
  to take a chord from, so it fell back to its own `+Y` = the way the road already runs) placed it
  *forward*, back down the road. `chain_unlinked` on an untouched pair, on the next Build. Now the
  head grows away from the chain and `_renumber(..., at=0)` prepends; an interior point is refused
  by name.
- **Which point is the MAINLINE is a fact, not click order** (`point_ops.resolve_aux_pair`). `AUX`
  stays directed (mainline → ramp) but the gesture works from either end — an entrance ramp reads
  "ramp joins road", and insisting the mainline be active made every merge unauthorable with the
  button the panel offers. `Make Ramp` shares the resolution.
- **ONE ramp role.** `RAMP_ENTRY`/`RAMP_EXIT` fed exactly one decision (which way
  `point_export.wire_ramps` points the lane edge) while `point_solve` derived the same thing from
  the chain — and when the two disagreed the geometry was perfect, the gate green, and the traffic
  wired backwards. `point_model.ramp_is_entrance` is the one owner: the mouth's position in its own
  **run** plus which way the ramp's lanes run (`lanes_bwd = 1, lanes_fwd = 0` is ordinary, and its
  head is where cars come *out*). `road_runs` moved to `point_model` for this (a run is a fact about
  the chain and its links); `point_solve.road_runs` is an alias. The ramp edge is now **added to**
  the junction connectors rather than dropped when a lane has both — §8f.4's orphan again.
- **The taper is PER CARRIAGEWAY and only WITHIN a run.** Summing both sides doubled the demand
  (336 m where the standard asks 168) on the theory that two opposite lane drops compound; they do
  not — a merge is one driver on one side of the divide, so the demand is the *wider* of the two
  changes. And walking the chain pairwise measured a taper straight across a junction gap, where the
  pad joins the mouths and no carriageway exists. `taper_factor` is unchanged (1.0 is the book) but
  the finding now names the factor that would pass.
- **A gore's nose carries the RAMP's section, uniformly** — not a blend of the two flanks (§8h.3's
  blend was right only while both roads declared the same *kind* of furniture; a fenced ramp leaving
  a kerbed street gave a wall of falling height standing in a widening footway). The mainline's kerb
  and footway run on past it unbroken. The mainline's values are the fallback only when the ramp
  declares nothing at all.
- **A Blender `EnumProperty` is stored by ORDINAL, not identifier** — introduced and caught in this
  same round. Inserting `RAMP` into the middle of `ROLES` re-read every saved role in every `.blend`
  (`RAMP_EXIT` → `RAMP_ENTRY`) with nothing to see in any diff. **The enum tuples in `point_model`
  are append-only**; `_enum_items` emits the 5-tuple form so the numbers are written down.
- **`Author ▸ Corridor ▸ Split To New Road`** is the repair when a stretch lands in the wrong road
  (a ramp grown with `Extend Road` off its mainline). Links are object pointers, so the `AUX` link
  survives the move. `chain_unlinked` is a **WARN** now, not an ERROR: `road_runs` already builds a
  split chain correctly. The real defect — a point joined to nothing — arrives under its own name,
  `point_stranded`.
- **`Author ▸ Repair ▸ Tidy Roads`** does the same filing with **no selection**, from the links
  alone: a point whose `SEGMENT` links all land in one *other* collection moves there (placed next
  to the neighbour it joins — appending would repeat §8i.1's defect), and a collection holding more
  than one **corridor** splits. A *corridor* is not a *run*: `point_model.road_corridors` breaks
  only where two chain-adjacent points carry neither a `SEGMENT` nor a `JUNCTION` link, because a
  crossing does not split a street — `road_runs` breaks at the junction gap too, since a lane must
  not be swept across a pad. One owner, shared with `check_chains`. A split-out corridor something
  `AUX`-links into is named `<road>_ramp`.
- **`Author ▸ Repair ▸ Repair Links` now exists.** The gate had named it as the remedy since step 1
  (`uid_duplicate`: "run Repair Links") and it had never been built. It **drops** what cannot be
  honoured (a `None`/self/non-point/no-road target, a duplicate row — a pair carries at most ONE
  link) and the ramp's half of an `AUX` pair; **restores** the missing half of a `SEGMENT`/
  `JUNCTION` link and completes a junction component into its clique; and **writes back** the uid
  `read_network`'s `dedupe_uids` re-allocates, which nothing had ever persisted (so the warning
  could not be cleared). Type conflict between the two rows of a pair: `AUX` > `JUNCTION` >
  `SEGMENT`.
- **A finding must name an object in the MESSAGE, not just the subject.** Rule 5 was half-kept:
  `Validate` translated `Finding.obj` but not the body, where most uids are ("is chain-adjacent to
  `p_862c8815`", "move `p_5dd247b1` further away"), and `Build`/`Export` translated neither.
  `point_validate.describe(finding, labels)` is the one owner (regex over `p_` + 8 hex);
  `point_model.point_labels()` supplies `{uid: "<road>/<object>"}`.
- **`Add Sample Network` is authored BY THE GESTURES now**, not by the internal helpers. As a
  data-model fixture it could be perfect while `Extend Road` grew roads backwards and `Make Ramp`
  refused half the ramps in the world — the smoketest pressed the button and covered neither. It
  now contains the arrangements that were broken (a head extension, aux lanes on *both*
  carriageways over one span, one ramp that is an exit at one end and an entrance at the other,
  and a fenced-ramp-to-kerbed-street gore), so it is evidence rather than illustration; under the
  old taper rule it would be red. `is_loop` is the one shape it does not carry yet.
- **A junction arm offers only the lanes that exist AT THE STOP LINE** (`point_export._arm_lanes`)
  — a pre-existing bug the new sample surfaced. `lane_movements.target_lane` preserves distance
  from the **kerb**, and an arm was offering every lane of its run including one that opens 200 m
  past the stop line and is zero width there: both approach lanes shifted one outboard, the
  straight-ahead movement fed a lane that is not there yet, and the exit's **median** lane came
  out with no predecessor — at every junction whose exit arm has an aux lane in the same run.
  Which end is zero decides it, so it is asked per end; `spawnable` is the same fact from one side
  and is NOT the test. Found by `Preview ▸ Flow Report`, which the smoketest now asserts is clean
  on the sample.
- **Object names are GLOBAL — renumber the DESTINATION first when points move between
  collections.** `_renumber`'s two passes only protect against collisions *within* one collection;
  a point that has left but not yet been renamed still holds `<src>_pNNN`, so renumbering the
  source first gets `main_p000.001` back from Blender — a point whose name sorts outside its own
  chain, which is the one thing the name order has to guarantee. Asserted in the coverage
  smoketest (no `.` in any point name).

**And the duplicate-and-branch round, 2026-08-27** (`ROAD_POINT_GRAPH.md` §8j; four user reports
about authoring a *second* ramp). Every one was a derived fact resolved through a proxy that is
usually right — a **uid** where the ground truth is an **object**, or the **walk direction** where
the ground truth is the **road** — and every one failed by returning a plausible number rather than
an error:

- **Membership is read off the OBJECT; links resolve by OBJECT IDENTITY.** Duplicating a road
  collection gave every copy the original's uid, so `dedupe_uids` dropped the copy's own internal
  wiring (right for Shift+D on one Empty, wrong for a whole road) and `read_network`'s
  `{old_uid: new_uid}` remap — only a function while uids are unique, which is exactly what they
  are not at that moment — rewrote **both** roads' point lists, leaving the ORIGINAL orphaned.
  `point_model.relink_from_objects` keeps a link row that stays inside the re-allocated set (the
  copy's own wiring) and drops one that leaves it (a clone's inherited connectivity); a link to an
  object in no road collection is dropped, not resolved by uid onto whoever shares it. `net.labels`
  comes from the same read so §8i.10's rule survives the dedupe.
- **`Author ▸ Ramp ▸ Branch Ramp Here`** is the gesture for a ramp that starts mid-corridor.
  `Extend Road` refuses an interior station and is right to, but the thing the artist was doing had
  no gesture at all. It opens the aux slot back to the first span long enough to hold the taper
  `check_tapers` asks for (an aux count is an integer, so the slot goes zero-to-full across exactly
  ONE span — opening it on more stations moves which span the change lands on, never lengthens it),
  places and faces the mouth via `Align Ramp To Aux`, bends the second station **outboard**, and
  leaves the far end active.
- **Outboard is a fact about the road, not about the walk.** `point_solve._signed_gap` took its
  normal off the chord it was walking, so the upstream reading was the downstream one sign-flipped:
  "which way do the bands part" picked upstream unconditionally, the two edges were paired running
  opposite ways in world space, and the gore's nose cap came out **22 m long, laid across the
  merge** — with a green gate, zero residual and zero angle. It now takes a `sense`. The same fix
  ended the arterial footway that was built across the ramp mouth: `open_runs` opens a kerb across
  whatever the gore actually covers.
- **A ramp that bends back ACROSS the road it leaves had no eye on it.** Both ramp checks measure
  the mouth, and `Align Ramp To Aux` sets both, so a ramp that leaves correctly and then drives
  through the carriageway passed the whole gate with no gore built and nothing said.
  `ramp_divergence` measures the station *after* the mouth; `ramp_wrong_side` (ERROR) /
  `ramp_parallel` (WARN). The sample network's own exit ramp was authored that way.
- **`ramp_frame_sign` is the product of TWO signs**: which carriageway the aux slot is on
  (`aux_fwd` vs `aux_bwd` — traffic through a reverse slot runs against the station axis) and which
  way the ramp's own lanes run. Three places derived it and all three assumed +1, so a
  reverse-carriageway ramp was faced, placed and edged as a forward one — a two-lane entrance came
  out as a 600 m hairpin with a 38 m wall down the middle. `Make Ramp` also stopped writing
  `aux_fwd` unconditionally: `ramp_carriageway` reads it off which side the mouth is on.
- **One aux slot, one ramp, per run.** `point_profile.aux_slot_ids` is the one owner of which lanes
  leave (`_aux_handoffs` was still handing over the outermost slot only, so a 2-lane ramp's inner
  lane had no predecessor — §8g.1 one level up). The structural half is reported, not fixed: a run
  exports ONE lane per slot, so two ramps on one run — or one station wired to two ramps, where a
  duplicated ramp collection lands — both claim `AF0` and one is reachable by no car.
  `check_aux_slots` (ERROR) names both and the two ways out: the other carriageway, or a run break.

**The diverge/merge round, 2026-08-27** (`ROAD_POINT_GRAPH.md` §8k). Two ramps hanging off ONE
mainline station — a two-lane exit that splits, two ramps merging back into one two-lane slot — is
the ordinary shape of an interchange, and §8j.6 had just declared it an error. That was right about
the *run* and wrong about the *station*: a station's aux block is several slots, and what was
missing was which of them is THIS ramp's.

- **`point_solve.aux_allocation` divides a station's aux block among its ramps**, each taking as
  many slots as it declares lanes. Order is derived from where the artist put the mouths (nearest
  the through lanes takes the innermost slot) — not click order (§8i.2) and not uid order, which is
  invisible and would reshuffle a network on a rename. `aux_gore_offset` replaces "the block's gore
  line" everywhere, and `wire_ramps` hands each ramp only its own aux lanes. `aux_slot_shared` is
  narrowed to the same slot claimed twice IN ONE RUN; over-subscription is its own finding.
- **A gore is against the neighbour on the INBOARD side, which is not always the mainline.** The
  outer ramp's is the INNER RAMP; measured against the mainline its wedge is struck across the
  inner ramp's asphalt. `inboard_neighbour` chooses it and reads that road's outboard edge with its
  own `ramp_frame_sign`.
- **Two boundaries pair by PROJECTION, never by index** (`_project_signed`). Equal-arclength walks
  assume both advance together; two sibling ramps do not, so by 90 m the samples lag six metres and
  the perpendicular offset was measured against a point that is not opposite. Two ramps with a real
  5 m hole between them read as a gap of zero and no gore was paved.
- **Which carriageway a ramp is on is a fact about where its mouth is** (`ramp_carriageway`).
  `Make Ramp` wrote `aux_fwd` unconditionally, putting a westbound ramp's slot on the eastbound
  carriageway.
- **"Does this lane exist at the stop line" is asked of the WIDTHS, not of the receiver.**
  `merge_into`/`opens_from` are both None when `lane_taper_route` cannot resolve a receiver —
  indistinguishable from a full-length lane. Declaring `aux_bwd` on the arterial was enough to make
  the junction arm offer the forward aux lane, shift every straight movement one lane outboard, and
  leave an ordinary through lane reachable by nothing (§8i.13 again, from the other side).
  `LaneRoute.i0`/`i1` are the question actually being asked.

**One ramp out and one ramp in at one station, 2026-08-27** (`ROAD_POINT_GRAPH.md` §8l) — the
ordinary half-interchange, and what `Add Sample Network` now carries (the westbound ramp two lanes
wide, plus a spur branched mid-corridor). Four things were in the way:

- **`aux_block` answered "forward" for a reverse ramp.** A station handing a ramp to each
  carriageway declares `aux_fwd` AND `aux_bwd`, and the case-free "most slots, ties to FWD" reading
  then put the reverse ramp's mouth on the forward gore line. `aux_block(profile, direction)` takes
  the side when the caller knows it, and `point_solve.ramp_side_of` knows it — §8j.4's rule asked
  per RAMP instead of per station. `aux_allocation` allocates each carriageway separately,
  `inboard_neighbour` only pairs same-side siblings, and `check_aux_slots` no longer reads one ramp
  on each side as a collision (`AF*`/`AR*` ids keep them apart by construction).
- **An entrance's lane was cut off the wrong end.** `_aux_handoffs` ends an aux lane at its gore
  because *an exit lane has left with the ramp*; applied to an entrance it handed the merging ramp
  the stretch of slot UPSTREAM of the merge — a successor whose head was 600 m back down the road.
  An entrance's lane is the acceleration lane and BEGINS at the gore.
- **Nothing could see that, because every check asked whether an edge EXISTS.** `broken` is no
  successor, `unreached` no predecessor, `ramp_orphans` nothing leads to a ramp — a successor
  pointing the wrong way is healthy by all three. `flow_report` now also reports **`misjoined`**: a
  successor whose head is not where this lane's tail is (`merge` edges exempt — a taper hand-over is
  lateral and its target spans the run).
- **`unreached` stopped reporting non-`spawnable` lanes.** A deceleration lane that opens after a
  junction is supposed to have no predecessor: it is entered by a lane change, and a lane-change
  edge is `inner_lane`/`outer_lane`, not `next`. It keeps its bite where it matters — a full-width
  through lane is spawnable, which is §8k.5's case.

**NAME ORDER IS CHAIN ORDER, AND A HAND EDIT CAN BREAK IT** (2026-08-31, `ROAD_POINT_GRAPH.md`
§8m). `point_model.read_network` sorts a road's point objects **by name** and that order IS the
chain; the links are the separate, authored fact. A rename, a `Shift+D` or a point dragged between
collections therefore reorders the road silently — the build follows the links and is correct,
while the file no longer reads the way it behaves. `point_model.link_order` is the one owner of
"what order do the links put these in" (idempotent on a correct road, and it leaves a **branching**
stretch alone rather than inventing an order for it); `Author ▸ Repair ▸ Renumber Roads` renames to
match — links are authored, a name is derived, so the name is what is wrong — and
`chain_out_of_order` / `chain_branched` are the WARNs that say so. Two gestures came with it:
**`Merge Points`** (a contiguous run of ONE road collapses to one station; the first survives with
its uid and section, outward links carried over — points in *different* roads are a junction, not a
merge) and **`Insert Point` from a single selection** (splits the span after it; `_next_in_chain`
derives the neighbour from the link AND the order, since either alone is ambiguous).

**A RUN'S END IS NOT A ROAD'S END, AND A PAD IS SIZED BY THE WHOLE SECTION** (2026-09-04,
`ROAD_POINT_GRAPH.md` §8o, `WORLD_REBUILD_PLAN.md` `W16`). Two junction defects, both of them the
footway reaching a solve that had never been asked for it. (1) `road_points.chain_tangents` is
handed a RUN, and a run stops at a junction mouth, so its end tangent falls back to the one
available chord — right for a road that ends, wrong for a mouth, where the road carries on across
the pad and the cap is cut on `point_model.station_axis`. They agree only while a road runs
straight through a crossing: at a 12.2 deg bend the street's kerb line finished **2.23 m** off the
pad corner it must meet. `point_profile.run_end_axes` gives the two end stations the chain's
direction (keeping their own Z slope, so a graded approach does not kink) and the sweep, the export
and the overlay all take it. (2) `point_solve.corner_setback` passed the CARRIAGEWAY half-width to
`corner_clearance`, whose own docstring quotes the DECK half — indistinguishable while every
footway was 0 m wide, and the day one was not, every pad was sized for a 21 m road that is 29 m
wide, leaving corners whose cap points are 3.31 m apart for a kerb that has to turn 95 deg through
them. **A number derived from a section must be derived from the whole section:** while a layer is
optional and zero everywhere, every consumer standing for "the road's width" holds a value that
merely happens to be right.

**A CONSISTENCY CHECK CANNOT SEE A FACT THAT WAS NEVER WRITTEN DOWN** (2026-09-04,
`ROAD_POINT_GRAPH.md` §8n, `WORLD_REBUILD_PLAN.md` `W14`). Every gate check reads the authored
graph and asks whether it is consistent, which is blind to a junction that was never authored at
all: two roads whose end stations sit at the identical position with no link between them have no
link to be asymmetric, no chain with a hole and no clique to be incomplete, so an 839 m road can
be an unreachable component of the island with the gate reading 0/0. The cause was
`seed_district_roads.seg_intersect` testing `0.0 <= t <= 1.0` on a crossing that lands on a shared
VERTEX — the plan's own rule is that an arterial terminates on another arterial, and `resample`'s
float drift put `t` at `1.0000000006`, so **four of the island's sixteen crossings were dropped at
the ninth decimal place**. Bounds belong in **metres** (`TOUCH`, 5 cm), never in parameter space:
`t` and `u` are fractions of two segments of different lengths and one number cannot mean the same
thing to both. `point_validate.check_meetings` / `road_end_unjoined` is the eye — open ends only
(a ramp mouth stands beside its mainline by construction) and in **3D** (a street under a deck is
not a meeting).

**A STATION'S CROSS-SECTION COMES FROM THE ROAD, NOT THE STATION** (2026-09-04,
`WORLD_REBUILD_PLAN.md` `W3`). `point_model.resolve_point` gives an `INHERIT` station its road's
`base` and takes only the four `DELTA_FIELDS` (`lanes_fwd/bwd`, `aux_fwd/bwd`) from the point —
lane width, median, footway widths, kerb heights and design speed all come from `RoadData.base`.
So writing a footway width onto every point of a seeded road is writing it where nothing reads it:
`seed_district_roads` did exactly that, and **the island had no pavement at all** — `rka_walk_hl`
was 0.0 on every sample of every road, for as long as the point-graph seeder had existed, with a
green gate. A field being *per-point in the schema* does not make the point its owner; only
`profile_mode = OVERRIDE` does. The barrier needed nothing: `point_solve.solve_road` derives it
(fenced end to end where `ped_access` is off, and where `delta >= BARRIER_MIN_DELTA` or on piers
where it is on) and the missing footway had only left it standing on the kerb line instead of at
the pavement's outboard edge.

**A MOUTH SLIDES ALONG ITS OWN ROAD, AND THE SEEDER MUST NOT GUESS HOW FAR** (2026-09-04,
`ROAD_POINT_GRAPH.md` §8p, `WORLD_REBUILD_PLAN.md` `W18`). Two owners of "where is the stop line":
`seed_district_roads` placed every junction mouth at a provisional **14 m** and pruned the stations
inside `14 + MIN_SPAN` of the crossing; `bpy.ops.rka.auto_setback()` then solved the real distance
(**17.9–35.5 m** over the island's ten pads) and walked the mouth out over the top of a station
that had survived a window computed from the wrong number. `point_solve.solved_setback` is the one
owner now — a function of the ARMS alone, so `seed_district_roads.place_setbacks` can ask it with
planned arms before an Empty exists. Nothing could see the result: two stations with the same
profile make `check_tapers` return on `dw == 0` and `station_coincident` only fires at 1e-6, so the
island shipped an ordinary station **0.19 m** past a mouth with a green gate —
`point_validate.check_mouth_clearance` / `station_crowds_mouth` is that eye. And `auto_setback`
placed each mouth on a ray from the pad CENTROID, which is on none of the roads: identical to the
crossing on a symmetric X (which is why it was invisible), **12 m** off it on a 5-arm pad, enough
to leave one approach 40° from its own alignment and 3.54° from the next arm — two carriageways
leaving on top of each other. The centre is projected onto each mouth's own axis first, so a mouth
can only slide along its road. **Still open (`W17`): `Auto Setback` is not idempotent** — pressing
it twice moved 17 of 35 mouths by up to 30 m and a fourth press by 58, because
`recommended_tail_length` only searches upward from the widest mouth while the mouths move the
centroid it measures from. The build presses it once; do not press it twice by hand.

**A GESTURE THAT HANDS OUT A `JUNCTION` LINK OWES THE WHOLE PAD** (2026-09-04,
`ROAD_POINT_GRAPH.md` §8q, `WORLD_REBUILD_PLAN.md` `W19`). A pad is three facts written together —
the members form a **clique**, each is typed `INTERSECTION`, each hangs off the `JCT_*` handle — and
`point_ops.make_pad` was the only thing that had ever written them. `Merge Points` correctly carried
"every link that left the collapsed run" onto the survivor and stopped there, so merging a plain
station into a crossing (the plain station is `doomed[0]`, so it survives) left the pad a
**component, not a clique**, with mouths still typed `SEGMENT` and unparented — 8 gate errors from
one gesture, and `Auto Setback` then solving a clique that is not one.
`point_ops.complete_junction_cliques` is the shared owner; `Repair Links` recovers a file already
broken by it. A merge smoketest that only merges **interior** stations cannot see this.

**`resample` NEEDS AN OPPOSITE NUMBER** (same round). It lays a station every `spacing` metres so a
road has stations where it needs them; on the straight legs between two authored plan vertices those
are exactly collinear and cost geometry, build time and a lane control point each for nothing.
`seed_district_roads.simplify` is **Douglas-Peucker** over the 3D polyline — never a pairwise
"is this station between its neighbours" walk, which measures each candidate against a line that
already reflects previous removals and lets a shallow curve walk off by many times the tolerance one
legal step at a time. Run twice and unioned: against the ROAD at `STATION_MERGE_TOL` (0.25 m) and
against the GROUND at `GROUND_MERGE_TOL` (1.0 m, looser because a station's `ground_z` is what
`road_support` sizes its piers from — a straight deck over a bay must not collapse to its two shore
stations). Junction mouths are protected outright: a stop line is not a shape. Measured on the
island: **433 → 184 stations** for **+0.02 m** of drape error (worst at-grade road-to-ground gap
0.32 → 0.34 m, against a 0.35 m `MovementController.stepUpLedge`).

**A CORNER IS A BEND STATION, AND ONLY THE JOINT HAS TO MOVE** (2026-09-04,
`ROAD_POINT_GRAPH.md` §8r, `WORLD_REBUILD_PLAN.md` `W15`). **A run never spans two road
collections** (`point_solve.road_runs` walks one road's own points), so two plan arterials meeting
end-to-end each sweep their own carriageway to the joint at their OWN heading — sections cut on
planes 98–124° apart agree nowhere, and the island's three corners ended **24–28 m apart** with a
SEGMENT link across the hole. Rounding the corner and using a bend station are the same answer:
`seed_district_roads.fillet_corner` trims both chains by the tangent length, lays an arc of
`CORNER_RADIUS_FACTOR` (3.0) × the **deck** half-width (43.5 m on a T2 — derived from the section
per `W16`, clamped by `CORNER_MAX_CHAIN_FRACTION` when the road is too short), and **splits it at
its midpoint** so each road carries half the turn and they meet **tangentially** — the
straight-through joint the seeder already built correctly, with each street keeping its name and
every lane id. A 2-arm pad is refused by the model; merging the two roads costs a street its
identity. Measured: gap **25.6 → 0.00 m**, deflection **106/124/98° → ~7°** (one arc step).
**The geometry meeting is not the graph chaining:** the fix moved the flow verdict from `open_end`
to **`broken`** (a tail on a head with no edge), and `point_export.wire_joints` emits the
hand-over — matched by geometry, not lane index — taking `broken` to 0. The runtime's
`LaneGraph` proximity fallback would have hidden it, which is exactly why it is exported.

**A PAD IS A PLANE AND THE GROUND UNDER IT IS NOT** (2026-09-05, `ROAD_POINT_GRAPH.md` §8s,
`WORLD_REBUILD_PLAN.md` `W20`/`W21`). `point_solve._idw_z` interpolates a junction's surface from
its mouths so a pad meets every approach at that approach's own elevation — right, and it stops a
junction on a grade from stepping — but between the mouths the ground goes on doing whatever it
does, and where it rises inside the footprint the pad is **under** it. **The collider is why that
matters:** `point_build.cut_ground` punches a vertical prism through the terrain over every band
including the pad, so the burial is invisible, but `Ground-colonly` is deliberately in a collection
the cut does **not** recognise (continuous collision under the island is the base layer's whole
job), so the player walks on ground the eye says is not there. Measured at the port crossing, four
arterials on ground falling 2.09 m across the pad: **0.924 m** of ground proud of the pad, against
a 0.35 m `stepUpLedge`. `seed_district_roads.pad_lifts` probes the footprint on a 2 m grid and
raises **every mouth by one uniform offset** (`_idw_z` is linear in the mouth heights, so one pass
is exact and the pad keeps its tilt), applied as a **floor before the grade cone**
(`height_profile(..., floors=)`) so the approaches ramp instead of stepping and `road_support`
grows the embankment for free. `PAD_BURY_TOL` (5 cm — `point_edges.BURIED_TOL`'s "exactly on"
idea, not a margin) keeps it off flat pads, whose raw burial measures 0.000000–0.000122 m against
the slope's 0.924. **Still open (`W21`): the terrain collider is never cut**, so ANY road surface
below the ground is unreachable — `W20` fixed the one place it happened, not the class.

**THE ROAD DEFORMS THE GROUND; IT DOES NOT CUT IT** (2026-09-06, `ROAD_POINT_GRAPH.md` §8v,
`WORLD_REBUILD_PLAN.md` `W13`/`W21` — both closed). The boolean cut is **deleted**
(`point_build.cut_ground`, `clear_cuts`, `_cut_tube`, `_cut_section`, `_outward_offsets`,
`_self_intersects`, the `Cut Ground` build option and the exporter's cutter-hiding workaround).
Four rounds of fixing it each found a real defect — a zero-thickness cutter that had never cut
anything (`W22`); a sampler reading the terrain the PREVIOUS build had cut, so 29 of the touge's 66
stations found no ground and were never cut again; a switchback's cutter passing through itself,
which an exact solver answers by leaving the ground standing, silently — and the measurement that
settled it is that **from identical inputs (same network, same terrain, same sampled `ground_z`
byte for byte) a second Build took the touge from 2 buried stations to 9.** That is the tool, not
the road. It was also never the industry approach: terrain is a **heightfield**, a heightfield has
no topology to cut, and from Unreal's `Deform Landscape to Splines` to a Houdini road HDA the
operation is to write the road's elevation INTO the field — where the collision IS that field, so
visual and collider cannot disagree. (Manual cut-and-stitch is real but narrow: terrain holes plus
a hand-modelled piece, for what a 2.5D field cannot express — tunnels, overhangs, an abutment into
a cliff.)

`island_v3_terrain.Carve` is the rule — `z = min(z, road_corridor_z)`, and **carve-only is
load-bearing**: `road_support` already owns FILL (NONE/FILL/PIER/CUT from `surface_z − ground_z`),
so rising ground would build the same embankment twice, and a rule that raises ground would **fill
the bay** under `W1`'s 18.20 m bridge. `min` needs no bridge case because it cannot raise ground.
Terrain owns the cut and its batter; `road_support` owns the fill and the piers — opposite signs of
one number. **One direction of derivation:** a road's profile is derived FROM the ground
(`bench_profile`/`grade_cone`/`height_profile`), so a `Carve` is a separate VIEW (`carved_field`)
handed only to the ground-MESH builder — `build_island_base` emits the ground **twice** (natural →
seed + solve → carved), alignment against the original terrain and terrain deformed to the finished
alignment, never back. **The verge is what makes a 12 m grid exact:** the flat shelf runs one full
`GROUND_CELL` past the pavement, so no triangle spanning the road can have a raised corner —
measured 1 185 377 samples, **0 proud / 0.000 m**, against 450 at 3.508 m with no verge; subdivision
was measured and rejected as the lever (12 m → 3 m moved the worst intrusion only 3.508 → 0.647 m,
still past the 0.35 m `stepUpLedge`, for 16× the vertices). **A hairpin needs no case** — the lower
leg wins where two legs overlap and each leg clears itself, which is the geometry that defeated the
boolean four times. Measured on the built island, 28 295 samples: ground proud of the road **2 of
225 at 3.20 m → 0 at 0.00 m** on the visual and **0 at 0.00 m on the collider**, `Ground` 30 577 →
**21 547** verts, **collider identical to the visual** (that is `W21` closed by construction), and
repeated Build stable. One trap it introduced, with an eye on it: a carved ground is not the
natural ground, and a second Build stamped "the ground meets the road here" onto **195 of 225**
stations (biggest 9.46 m) — `point_build.CARVED_FLAG` refuses that with a message, re-measured 0 of
225. `point_build.road_corridors` / `band_corridors` is the addon's whole remaining contribution:
the centreline and half-width of what it just built, the width read off the swept band.

**THE GROUND CUT HAD NEVER CUT ANYTHING** (2026-09-05, `ROAD_POINT_GRAPH.md` §8t,
`WORLD_REBUILD_PLAN.md` `W22`). `point_build.cut_ground` built its cutters with
`bmesh.ops.solidify(bm, geom=[face], thickness=…)` and got **no thickness at all** — measured across
all 32, `z_min == z_max == -40.00`, so every boolean was a no-op and the evaluated terrain came back
with exactly its base vertex count. It stayed invisible for as long as every road was draped ON the
ground (a road 0.16 m proud needs no cut to look right) and surfaced only where a road went *below*
it: the buried junction pad (`W20`) and the touge's slot (`W13`) are the same defect seen twice.
The solid is built explicitly now. Three rules came with it: **a road is cut as a TUBE, not one
lofted outline** (`band_of` walks left-edge-out/right-edge-back, so a switchback's outline
self-intersects and its single n-gon cap is geometry the exact boolean will not arrange — a tube has
only two small end caps); **coincident rings are welded, not emitted** (at grade the cut depth is 0
and the middle rings coincide, and a solid of degenerate quads is non-manifold, which the boolean
also answers by doing nothing, silently); and **the reach is asymmetric** — full depth downward, but
upward only to each section's own daylight point, because ground above that is hillside the batter
has run out to meet (a local downward reach was measured too: holes 57% → 21% for no gain).
`road_support.cut_footprint`/`CUT_SLOPE` give a CUT the batter only a FILL had — steeper than the
fill (1:1 vs 1:1.5) because a cut face is undisturbed ground while a fill is placed earth on its
angle of repose. And **`CUT_MAX` had two owners that disagreed 8×**: it said a trench deeper than
3 m is a TUNNEL while `island_v3_terrain.MAX_BENCH` said 25, so the touge's 8.1 m bench was
classified as a tunnel nothing builds; `MAX_BENCH` reads `CUT_MAX` now. Measured: samples cut
**6% → 57%**, ground standing proud on eleven of twelve roads **up to +0.42 m → +0.00 m**.
**Still open (`W13`): the shrine touge is the twelfth** — still 0% cut and 8.71 m under its
hillside — and it is a SAMPLER problem, not a geometry one. The hairpin theory was tested twice and
reverted (chunking the cutter every 150° of turn, and a local skirt instead of the full depth:
neither moved the touge, and the second cost 57% → 21% of through-holes elsewhere). At the deepest
station `ground_sampler` returns ground 3 m **below** the road while the station's stored `ground_z`
says the road is 8 m **below** the ground — an 11 m disagreement — so `_cut_section` gets a daylight
height of 0 and correctly removes nothing. `scene.ray_cast` respects modifiers and punches through
whatever `is_terrain` rejects; that is where the 11 m comes from.

**A MATERIAL IS AN ASSET, NOT A CONSTANT IN A BUILDER** (2026-09-05, user-asked: default the
plugin's materials to the ones in `assets/`). `kit_common.mat()` used to get-or-**create** every
material from its own Python table, in whichever `.blend` was building — so the look of the world
lived in code, and it was not even one datablock: `road_kit.blend`'s profile sections carry their
own `M_Concrete` (built by that same function, in that file), so a district linking a kerb section
got the kit's concrete on the kerb and a locally-created one on the deck beside it. Identical, and
two materials in the exported scene. **The kit file is the material library now** —
`blender/tools/build_road_kit.py` writes every `MATS`/`TILED_MATS` entry into
`assets/world_source/kit/road_kit.blend` with a **fake user** (a `.blend` drops any zero-user
datablock on save, so without the flag the kit shipped only the 3 of 25 its sections happened to
use). `mat()` is still the ONE resolver and grew one lookup, not a second registry: a datablock of
that name already in the file wins (`bpy.data.materials.get` prefers a LOCAL one over a linked one
— measured — so a hand-edit survives a rebuild), else it is **linked** from the kit, else built
from the table as the BOOTSTRAP (`build_road_kit.py` sets `kc.USE_MATERIAL_LIBRARY = False`: the
tool that writes the library must not read it). Linked, not appended — an appended copy drifts —
and a linked material *is* writable from Python in a background process, so the base-colour
flattening below is unaffected. `point_build.material()`/`MATERIAL_KEYS` and `point_style.resolve`
are **untouched**: the addon had one default-material lookup and still has one; adding a second
there would have been the very defect this closes. Measured on `Island_base`: the same 11
materials with the same user counts, every one now `lib=//../kit/road_kit.blend`, all 11 baked
with an `albedo_color`, `check_roads.sh` PASS=18.

**A PROCEDURAL BASE COLOUR CANNOT CROSS glTF, AND IT LEAVES NO TRACE WHEN IT FAILS**
(2026-09-05, user-reported "materials seem lost"). glTF carries a base colour as either a CONSTANT
factor or an IMAGE texture. Blender's exporter reads the Principled BSDF's Base Color: unlinked it
writes the constant, linked to an image it writes the texture, and **linked to anything else — a
Checker, a Noise, a Mix — it writes nothing**, so Godot renders the surface pure white with no
warning on either side. `kit_common.get_tiled_mat` builds exactly that shape, for a good reason (a
world-position checker survives a curved corner without the UV pinch a tangent-frame pattern gets,
which is what a footway wrapping a junction fillet needs) — so **`M_ConcreteTile`, the PAVEMENT,
had been white in-game ever since**, while looking right in every Blender render. The authoring
intent belongs in Blender and the constraint belongs to the seam, so the fix is at the seam:
`export_world.py` temporarily replaces any Base Color driven by a non-image node with a
representative constant (a Checker's is the mean of its two colours; anything else falls back to
the material's viewport `diffuse_color`) and restores it after export. **Verified by reading the
baked `.tscn`:** every named material now carries an `albedo_color` (the one remaining blank is an
unused glTF default with 0 users). When a surface looks white in Godot and right in Blender, check
this before suspecting the mesh.

**A GROUND CUTTER IS A MODIFIER INPUT, NOT CONTENT — AND IT MUST BE UNLINKED, NEVER REMOVED**
(2026-09-05, user-reported "one white ground cover the main pave segment, like an open box over the
road"). `point_build.cut_ground` builds one solid per road/pad and hands it to the terrain as a
BOOLEAN target; they are scene objects in `ROAD_MANAGER_GEN/CUTTERS`, and the glTF exporter takes
the whole scene — so all 32 baked into the game as raw white boxes straddling every road. It went
unseen for as long as `bmesh.ops.solidify` was silently producing zero-thickness sheets at z = −40
(the `W22` defect): invisible cutters that cut nothing. Giving them real volume made them real
geometry in Godot. **Removing the objects is not the fix** — the boolean would lose its target and
the terrain would export UNCUT, undoing `W22` where it matters. `export_world.py` UNLINKS them from
every collection instead: verified, the evaluated terrain reads 30577 vertices linked, unlinked and
relinked alike, because the modifier's own reference keeps the datablock alive while the exporter,
which walks the scene rather than `bpy.data`, no longer sees it. Baked scene: 32 cutter nodes → 0,
Ground still 38153 vertices against 19477 uncut.

**The Blender→Godot axis mapping is (x, y, z) → (x, z, −y), and it is correct** — verified to three
decimals on a baked road (`export_yup=True`). A piece that "looks flipped" in Godot is far more
likely a lost material than a transform; measure a known object's bounds on both sides before
chasing the export.

**A HILL ROAD IS DERIVED, NOT DRAWN** (island v3, 2026-08-31 — `blender/WORLD_REBUILD_PLAN.md`
`W2`). `island_v3_terrain.hill_road` walks the height field to produce a switchback alignment:
write a heading as `cos φ · uphill + sin φ · contour` and the height gained per metre is
`|∇z| cos φ`, so asking for the road's grade fixes `φ = acos(grade / |∇z|)` — on a 92% flank an 8%
road runs 85° off the fall line, and flipping the contour term's sign IS the hairpin. It is not a
grid search on purpose: the legal headings lie within ~5° of the contour, a grid offers 8 or 16 of
them, so A* returns nothing and that reads as "there is no route up this hill" (which the plan had
recorded as a measured fact). Three rules came with it and each was a defect first — **the hairpins
are part of the climb** (a half-turn moves the road `2R` across the slope, so it gains `2R·m` in
`πR`; legs walked at the limit average 10.1% on an 8.1% road, and the grade cone "corrects" that by
lifting the foot of the mountain, giving a 57 m sky-road that every per-sample check passes);
**a benched road is judged over its whole alignment**, not sample by sample
(`island_v3_terrain.BENCHED_CLASSES`, `alignment_grade`, `bench_depth`, `MAX_BENCH`) — its hairpins
are cut-and-fill platforms and the ground across a turn swings far more steeply than the road does;
and **the station rule has one owner** (`island_v3_terrain.stations`), because a resample that only
lays even arc-length stations steps clean over a 38 m hairpin at 70 m spacing and the cone then
fills the cut corner (25.6 m of pier where the model said 14.7). `grade_cone` is likewise one
function shared by the seeder that builds the road and the gate that predicts it.

**A MOUNTAIN ROAD IS A BENCH, NOT A VIADUCT** (2026-08-31). `seed_district_roads.height_profile`
raises a draped profile with a grade cone, which is right for a bay crossing (you do not cut a
bridge into water) and wrong for a hill — it answered every hairpin with a pier and left 71 of the
shrine touge's 90 stations elevated, up to 16.3 m, over a hillside the ground cut had already
punched a road-shaped slot through. `island_v3_terrain.bench_profile` takes the MIDPOINT of the two
envelopes (least legal profile above the ground, greatest below); it is grade-legal for free because
`|dz| <= limit*span` is convex, and it turns +16.3/−0.0 into a symmetric ±8.1 at an unchanged 8.10%.
Applied only to `BENCHED_CLASSES`. **The ground cut itself was never the problem** — measured at the
centreline stations it leaves ground standing proud at 1 of 419, by 0.18 m (`cut_ground` is a
vertical prism from −40 to +40 m over each band's footprint). What is still missing is a CUT BATTER:
`road_support` builds an embankment toe for FILL and columns for PIER and nothing at all for CUT, so
a benched stretch comes out in a vertical-walled slot.

**A SHALLOW CROSSING NEEDS A BIG PAD** (2026-08-31). `point_solve.auto_setback` searched only for a
tail that fits every turn MOVEMENT and never asked whether the arms' own CAPS stay in ring order —
so `pad_not_star_shaped` named `Auto Setback` as its remedy and `Auto Setback` answered "moved 0".
The ring stays in order while `atan(half_a/d) + atan(half_b/d) <= theta`, i.e. `h/tan(theta/2)` at
equal widths: 14.5 m at a square crossing, **27.2 m at 56°**. `corner_clearance`/`corner_setback`
add that term. It is the CAP-ORDER test, not "where the outer edges cross" (30.8 m at 56°), which
over-demands by half — a fillet may bulge past that point, and asking for it grows every square
junction for a fold that is not there.

**LANES ARE 4.5 m, WHICH IS AN ARCADE NUMBER** (`seed_district_roads.LANE_WIDTH`, and
`point_model`'s own default, 2026-08-31). The car's hull is 2.00 m with wheels at ±1.1 m, so its
footprint is ~2.4 m: in a book-correct 3.25 m lane that is 74% of the lane and it drives like a
lorry in a tunnel. 4.5 m leaves 1.05 m either side. `island_v3_plan.ROAD_HALF` carries the same
arithmetic (T2 = 4 lanes + 3 m median + two 4 m footways = 29.0 m).

**THE VEHICLE SPEED-FEEL OVERLAY IS DELETED** (2026-08-31, walk-test: "too much… hard to see
road"). `SpeedFX`/`SpeedLines` and `SpeedLines.gdshader` are gone from `Vehicle.tscn`, not hidden.
`VehicleCameraController`'s FOV/accel/NOS/spring-arm terms are kept as exported knobs and ship at
**0**, with their previous values recorded on each field — a camera that cannot react to speed at
all is a decision to take deliberately, not by deletion. The planned replacement is world-space (a
trail or wheel effect on the car), never a screen overlay.

**`-noped` HAS A READER ON THE GODOT SIDE NOW** (2026-08-30). `point_build.collision_name` had
stamped the marker into every carriageway `-colonly` proxy since the point graph landed,
*specifically* so the navmesh would skip them, and nothing in Java had ever looked at it —
`NavBaker` parsed the whole root, so every carriageway baked into the navmesh the marker exists to
keep it out of. `NavBaker.NO_PED_TOKEN` is that reader: it clears each matching body's
`collision_layer` for the duration of `parseSourceGeometryData` (Godot's `STATIC_COLLIDERS` parser
tests the layer against the navmesh's geometry mask) and restores it before `pack()` — reversible,
and it cannot drop geometry from the SAVED scene the way detaching nodes could. What the marker
means on this side is "solid, but not walkable ground", so it is **not road-only**: the island's
`Seabed-noped-colonly` is its second user. Note the honest limit measured on `Island_base`:
excluding the carriageway removed only 11 of 1232 navmesh vertices, because the road stands 0.16 m
proud of ground that is continuous underneath it — a street stays crossable (correctly), and the
case the marker really decides is an on-ramp on piers, where there is no ground under the deck.

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

- **`AISquad`** is a `Node` (editor-placed, or one created per `SpawnConfig` by `ZoneManager`).
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
  freed squad node — pooling/reuse safe); `setSquad` moves registration; `ZoneManager` frees each
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

All weapon classes live in `com.openworld.weapon`; `WeaponItem extends item.Pickup`, which is a
**`Node3D`** — a weapon is not a physics body. Lying in the world it rides inside an
`item.PickupBody` (a `RigidBody3D`); held, it hangs off a bone socket with no physics at all. See
"W15 — A WEAPON HAS TWO STATES" under Animation for why, and for the rules that came with it.

### Semi-auto / full-auto lock (WeaponItem)

The "one use per trigger pull" lock lives in the base `WeaponItem`, not per-subclass:
`isWeaponFired` is set in `useWeapon()` and cleared in `stopUseWeapon()` (trigger release);
`isSemiAutoReady()` returns `!isWeaponFired || auto`. Every weapon gates `canUse()` on it, so a
non-`auto` weapon fires exactly once per pull regardless of `fireRate`. `FirearmItem`,
`ProjectileItem`, and `ThrowableItem` all share this — previously the lock was copy-pasted into
the firearm/projectile only and **missing from `ThrowableItem`**, which let a held throw key
spawn multiple grenades back-to-back (the double-throw bug). `MeleeItem` keeps its own
timer-based model (overrides `stopUseWeapon()` to a no-op).

### Auto-reload on empty — and why it cannot loop (2026-09-16, user-asked)

The shot that empties the magazine STARTS THE RELOAD ITSELF, which is the default in every modern
shooter (CS, PUBG, COD): a player who has just fired their last round should not have to press a dead
trigger to find out, and on a slow weapon — a bolt rifle, a launcher — that discovery costs a whole
reload. `WeaponController.onWeaponFire` calls `onWeaponReload()` when `magazine == 0` and the weapon
answers `WeaponItem.autoReloadsOnEmpty()`.

**The infinite-reload worry is answered structurally, not with a flag.** `onWeaponReload` already
returns immediately when `getReserve() == 0` or a reload is already running, so the GATE IS THE
RELOAD, not the caller: a weapon that is empty AND dry does nothing however often the hook fires.
There is no timer, no retry and no state to get stuck in — the only thing that can start a reload is
ammo actually being there. The pre-existing dry-PRESS path (pressing fire on an empty magazine
reloads) is unchanged and is the fallback for a reserve that arrives later, from a pickup.

Two ordering rules, both load-bearing:
- **The auto-reload runs BEFORE the weapon's own `onMagazineEmpty()` hook**, because a throwable's
  hook CLEARS THE SLOT — after it, `w` is no longer the current weapon and the reload would refill
  whatever replaced it.
- **`ThrowableItem.autoReloadsOnEmpty()` is false.** An emptied grenade stack clears its slot by
  design (so another throwable type can be picked up without an interact-to-swap); reloading into
  itself instead would strand the slot. `isInfiniteAmmo` weapons (fist, melee) are excluded by the
  same derived reader, so the flag is only ever asked of a weapon that has a magazine.

`WeaponItem.autoReloadOnEmpty` (`@Export`, default **true**) turns it off per weapon, and with it off
manual reloading is untouched. Gate: **`tools/godot/probe_auto_reload.gd`** — SR3's last round starts
a reload with no further input and the ammo moves; with a dry reserve nothing starts through 3 s of
idle AND twenty more trigger presses (the loop check), then a press after the reserve is refilled
reloads; the flag off is the control; and a throwable never auto-reloads.
`WeaponController.reloadingNow()` / `reloadsStarted()` are the two registered readouts it needs —
question-named so godot-jvm does not merge them into getter-only properties, and `reloadsStarted` is
a LOCAL count of reloads begun, deliberately not the replicated `reloadSeq` (which a puppet
overwrites from the wire).

### A BOLT ACTION IS THE FIRE RATE, NOT A RELOAD (2026-09-16, user-asked)

The question was whether a bolt cycle is a new behaviour or the reload path overloaded. It is
**neither** — it is what `auto = false` plus `fireRate` already do: `isSemiAutoReady()` gives exactly
one shot per trigger pull (the trigger must be released before the next), and
`fireTimer.setWaitTime(w.fireInterval())` — `1 / fireRate` — is the hard cooldown in between. So a
bolt gun is DATA: SR3 ships `auto = false`, `fire_rate = 0.685` (**1.46 s**, the CS:GO AWP's cycle),
measured at 1.467 s by the gate.

**Overloading the reload path would have been wrong in five concrete ways**, each of which is a system
that already means something else:
- `onWeaponReload` → `onReloadComplete` MOVES AMMO from the reserve into the magazine. A bolt cycle
  must not, so reuse would need a "don't actually reload" flag — one function with two meanings, the
  defect this file's W-series keeps closing.
- `reloadSeq` is replicated as state and drives `playRemoteReloadCue` on every puppet, so every peer
  would play a reload animation AND the reload audio once per shot.
- `isWeaponReloading()` feeds the HUD's `WeaponProgress` ring, which would read "reloading" (amber)
  after every shot.
- the reload timer already blocks firing, so the lockout would exist twice, with two owners and two
  durations to keep in step.
- an interrupted reload and an interrupted bolt cycle are different things, and a shared timer cannot
  be cancelled for one without cancelling the other.

What a bolt gun still wants is **cosmetic and per-view**, and each piece has an existing owner:
the weapon's own moving parts (`WeaponItem.fireAnimation` on its own `AnimationPlayer` — W13, exactly
"a shotgun pump, a bolt, a revolver cylinder"; SR3's model has no separate bolt object yet, so this is
authoring, not code), a character-side bolt one-shot if the arm should visibly work it (the `Attack`
one-shot's shape, W16), and the unscope/re-scope around the cycle (the scope work, PLAN.md 2.7).

Gate: `tools/godot/probe_auto_reload.gd` case 5 asserts BOTH halves — the interval between two shots
is `1 / fire_rate`, and nothing reloads while the magazine still has rounds.

### Spread formula (FirearmItem)

**One owner: engine-free `weapon.Accuracy`** (PLAN.md 2.8 item 3, `AccuracyTest` 10 cases). The live
cone, the host's N1 floor (`minimum`), the crosshair fraction and bloom decay/add all come from it, so
none of them can drift from the shot.

```
coneDeg = (spread + bloom + movementPenalty(horizontalSpeed, maxSpeed)) × posture × (aimed ? 1 : hipfire)
movementPenalty = 0                                       below standingSpeedFraction × maxSpeed (0.34, CS)
                = 0.03 × maxSpeed × (v − thr)/(max − thr)  ramping to the full term at max speed
                = 0.03 × v                                 at or past max (a slide, a fall)
```

Posture multipliers: UPRIGHT 1.0×, CROUCH 0.7×, CRAWL 0.5×, SWIM 1.8×, AIRBORNE 2.0×, applied to the
**entire** expression. `maxSpeed` is `Character.maxMoveSpeed()` — the stance's sprint speed × the combat
speed factor × a raised scope's `moveSpeedFactor` — so a scoped slowdown lowers the threshold with it.
Speed is HORIZONTAL: a body standing on a slope carries floor-snap vertical velocity that is not
movement. `hipfireSpreadMultiplier` (FirearmItem, default 1; SR3 8) widens only the LIVE cone — the host
floor cannot see the client's aim state. The threshold is `FirearmItem.standingSpeedFraction`.

Bloom accumulation: `currentBloom += bloomPerShot` on each shot, **added AFTER the shot resolves**
(it is what this shot does to the next one; added first, it put every weapon's per-shot bloom on its
own first round — W31); decays at `bloomDecaySpeed`
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

Spread is a **circular cone** from `weapon.SpreadPattern` (engine-free, unit-tested): random
perpendicular axis + `sqrt(u) × halfSpread` angle → uniform disk distribution (no diagonal bulge from
independent pitch/yaw sampling), rotating the shot **direction** around the muzzle→target line (see
"Two-stage hit resolution" below). Skipped entirely at zero spread. **It is deterministic** (PLAN.md N1):
every pellet is a pure function of `(aim, halfSpread, seed(shooterId, shotSeq), pelletIndex)` with its
own SplitMix64 PRNG — never `GD.randf` — so the host regenerates a client's exact pellets. See
"Networked shots — one seeded message per pull" below.

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

### Two-stage hit resolution — sight → muzzle (the cover fix)

A bullet is resolved in **two legs**, not one, because in third person the camera is not where the
gun is. `FirearmItem.fireShot`:

1. **Sight leg** (`resolveSightPoint`) — the camera `AimRay` (player) or the ray `AttackState`
   already snapped onto its scatter point (`AICharacter.snapAimRay`, AI) answers *where this shot is
   aimed*: its collision point, else its far end. This is the same point the crosshair sits on and
   the point `UserCommand.aimTargetPosition` feeds to the spine IK — so what the character visibly
   aims at is what the bullet is sent toward.
2. **Muzzle leg** (`resolveShot` → `trace`) — the bullet is traced **from the weapon's own `Muzzle`
   marker** to that point, with the spread cone sampled around *that* line. Whatever it hits first
   is the hit, the tracer end, and the impact VFX.

Leg 2 is the fix for *"my character is fully behind a wall and I still killed someone."* A single
camera-origin trace started above/beside the shoulder, on the free side of the cover the character
was visibly hiding behind. The muzzle leg starts at the gun, so that cover blocks the shot — while
the bullet still converges exactly on the crosshair, so aiming is unchanged.

Details that matter:

- **A SCOPED shot is one leg, from the scope** (W31, user decision). A raised scope
  (`Character.isScopeRaised()`) is behind the shooter's own eye, so the reason for the second leg is
  gone; `FirearmItem.useMuzzleTrace` is false and the shot is the camera ray itself.
- **The hug-the-wall bypass is closed.** `resolveShotOrigin` first traces the shooter's chest → its
  own muzzle; if *that* is blocked the barrel has clipped through geometry and the shot origin falls
  back to the chest, so the wall is still hit. Without it, pressing against cover puts the muzzle on
  the far side and the trace starts past the very wall that should stop it.
- **On-foot only** (`useMuzzleTrace`). A seated occupant's gun and a vehicle's own mounted weapon sit
  inside/against the carrier's collision, where a muzzle-origin trace is blocked by the carrier
  itself — and a drive-by is not the exploit this guards. Those keep the camera-origin trace.
  `@Export muzzleTrace` (default true) disables the whole thing per weapon.
- **`trace` borrows the character's AimRay** (`setPosition`/`setTargetPosition` +
  `forceRaycastUpdate`, then restores the **local** values — restoring globals would drift), the
  same idiom `resolveServerShot` uses. So a trace inherits the ray's collision mask and its
  self-exceptions (own body + ragdoll bones) with no query setup, and can never self-hit.
- **Networked:** the origin a client reports in `MSG_SHOT` is the **muzzle**, and the host's
  `resolveServerShot` re-runs the chest→origin cover test on its own copy, so a reported muzzle on the
  far side of a wall is pulled back to the chest exactly as a local shot would be.
- Shotguns resolve the sight leg + origin **once** per trigger pull and only re-sample the cone per
  pellet.

### Networked shots — one seeded message per pull (PLAN.md N1, 2026-09-13)

A client used to send **one reliable `MSG_SHOT` per pellet** (8 per SG1 pull) carrying a post-spread
ray the host traced as given — trusted origin, trusted direction, no rate/cone check, on channel 0
with damage, pickups and spawns. Now a pull is ONE message on its own reliable **channel 1**:
`shooterId, slot, shotSeq u32, origin, aim (PRE-spread), spreadDeg`. The client generates its pellets
from exactly those values **after rounding origin and aim to float32** — generating from the doubles
first made 1 pull in 10 differ in the fifth decimal from the host's regeneration. The host
(`NetworkManager.validateShot` → engine-free `net.ShotValidationPolicy`) refuses, each counted as
`shot_rejected_<verdict>`: a counter that does not advance (`STALE_SEQ`; per sender+shooter, cleared
on disconnect so a rejoin's fresh counter works), an empty per-weapon token bucket refilled at the
weapon's fire rate with a burst of 3 (`TOO_FAST` — a plain minimum interval would refuse honest pulls
that a reliable resend delivers together), an origin more than 1 m outside the shooter's **body
volume** (`ORIGIN_TOO_FAR`), an aim > 35° from the host copy's replicated aim point (`AIM_DIVERGED`),
and a cone under half the weapon's `minimumSpreadDeg()` for the host-known stance
(`SPREAD_TOO_NARROW`). Two measured traps shaped those rules:
- **A host puppet does not animate the owner's pose.** Its muzzle is cosmetic: a standing client
  firing from the shoulder had its host copy holding the same SG1 at the hip, 1.17 m away, on every
  shot. So the origin is judged against the replicated BODY, never the puppet's muzzle bone.
- **A host puppet is never on the floor**, so its live `getCurrentSpreadDeg()` carries the airborne ×2
  (6.0° vs the client's 4.0°) and would refuse an honest crouched shot. The floor is the weapon's
  minimum for the stance (no movement, no bloom, no air) × 0.5 — the widest stance ratio, so a stance
  change the host has not seen yet never refuses a shot.
The "any held firearm" slot fallback is gone (a sibling weapon's damage/pellets would be a different
shot); the current item is still used, counted as `shot_slot_fallback`.

Gate: **`tools/net/run_net_shot_test.sh`** — two headless processes of `debug/NetShotTest.tscn`
(`NetShotTestHost`, `--role=host|client`); the client collects a scene SG1 pickup, aims with its real
`PlayerController` and pulls 10 times through `Input`, then sends 10 forged shots. Asserts 20 messages
for 10 pulls + 10 forgeries, 10/10 honest pulls resolved, **10/10 pulls with identical pellet rays**
(a direction digest), each forgery refused for its own reason, the burst cut, and damage landed.
Pellet HITS agree ~90%, not 100%, by design: the target's hitboxes are animated and the client's
puppet of it is centimetres off the host's.

**Other peers see the real pellets (N1b).** The host queues a `ShotResult` for every pull it resolves —
a relayed client pull (excluding that client, who predicted it) and its own shooters' pulls (host
player, AI) — and flushes them once per frame as one `MSG_SHOT_RESULT_BATCH` per peer on **unreliable
channel 3**: per pellet an end point, plus the `SurfaceType` and normal for a hit. A peer draws a tracer
per pellet from its puppet's muzzle and `ImpactManager.processVisualImpact`. The fire cue that rides
the snapshot's `fireSeq` keeps flash + audio, but its single aim-point tracer is now a FALLBACK: drawn
only if no result arrives within 150 ms, skipped if one arrived in the last **300** ms. The windows are
asymmetric on purpose — the cue travels client → host → peer on the 30 Hz snapshot relay and was
measured arriving over 150 ms after its own result under load, which drew a second tracer. The host
draws a relayed pull's real tracers itself and suppresses the cue's the same way. Gated by the same
script, now with two watching peers: one must receive a result per resolved pull with the host's
pellet count and hits and draw 8 tracers each with 0 fallbacks; the other drops results and must draw
exactly one fallback per pull (the control). **Not exercised by the gate:** results for the HOST's own
shooters (no host-side shooter in the harness) — same queue, exclusion -1.

**Two game instances on one install share a `PersistentPlayerId`** (`user://player_id.cfg`), which is
exactly how LAN co-op is tested on one PC. The host used to spawn the second instance's body with the
FIRST peer's characterId — three bodies, one identity, and a client that could not tell which it owned
(the harness's observers took over the shooter's body). `GameManager.onPeerIdentified` now gives a peer
whose id a CONNECTED session already holds `id#peerId` (counted `identify_duplicate_player_id`); a
disconnected session still matches first, so a real rejoin is unchanged.
- Melee (`MeleeItem`) runs the SAME two legs — see "W16 — MELEE IS A SWEPT REACH FROM THE CHEST".

### Melee resolved on the host; the damage-request hole closed (PLAN.md N2, 2026-09-14)

Before N2 a client resolved its own swing, and `Health.takeDamage` relayed the FINAL number in
`MSG_DAMAGE_REQUEST`, naming nobody. The host checked only that the fields were well-formed, so one
forged packet could kill anyone.
- **`MSG_MELEE` (tag 27, reliable channel 1 beside `MSG_SHOT`)**: `attackerId, slot, swingSeq u32 (the
  weapon controller's shot counter), stepIndex, origin (chest), aim`, sent by the owner client when the
  swing's ACTIVE window opens. The host (`handleMeleeMessage` → engine-free `net.MeleeValidationPolicy`)
  refuses a non-owner, a counter that does not advance, a step the weapon lacks, a burst past the swing
  budget (a `RateBudget` refilled at one per the weapon's SHORTEST step), a chest outside the body volume
  (`originOutsideBody`, now shared with shots) and an aim more than 35° off the replicated one. It counts
  `melee_accepted` / `melee_rejected_<verdict>`, then `MeleeItem.resolveServerSwing` runs the SAME sweep
  (`sweepFrom`, the one owner of the capsule / group-by-target / LoS-from-chest logic) over the same active
  window. The chest rides the host copy's body as it moves, and damage is authoritative. The client's own
  sweep only PREDICTS: impacts, hitstop, kick, no damage (`melee_predicted_hits`).
- **`MSG_DAMAGE_REQUEST` names the responsible entity and a kind**, judged by `net.DamageRequestPolicy`.
  SELF (a fall, drowning, the sender's own vehicle) must be to an entity the sender owns and name it as the
  attacker. AREA (the sender's own explosive, until N4) must name an attacker the sender owns and draws on a
  per-sender budget (burst 12, 6/s). Damage above 500 is refused, an empty attacker id is malformed, and
  every refusal is counted `damage_request_rejected_<verdict>`. `Health.relayDamageToAuthority` picks the
  kind from ownership of the victim, and `NetworkManager.localAttackerId` supplies the sender's player.
- **An input-buffer bug found on the way**, pre-existing and not N2's: `onWeaponFire` runs every frame fire is
  HELD, and a blocked frame buffered itself as a new tap. So one 2-frame tap on the fist played jab AND cross
  whenever the swing was shorter than the 0.2 s buffer, and `probe_melee` had been failing 4 checks
  (reproduced on HEAD's Java). `WeaponController.rememberBlockedPress` now buffers only a press that STARTS
  while the weapon is busy (a physics-frame edge); the mid-recovery tap check still passes.
- Gates: `tools/net/run_net_melee_test.sh` (`debug/NetMeleeTest.tscn`, `NetMeleeTestHost`), 15/15 in 22 s.
  A client knife taps 6 times through `Input`: 6 `MSG_MELEE`, 6 accepted, 6 resolved hits = 6 predicted,
  target damage exactly 6 × 30 (stab 40 × 0.75). Each forgery is refused for its own reason: an attacker it
  does not own, "self" damage on someone else, unattributed, 100 000 damage, a replayed swing, a swing from
  10 m, a swing for a body it does not own. One honest self-damage request is accepted. `probe_melee` PASS,
  `run_net_shot_test.sh` 18/18, `probe_self_hit` PASS, unit tests `MeleeValidationPolicyTest` /
  `DamageRequestPolicyTest`. Test trap: each stab's knockback pushes the target 0.3 m back (1.10 → 1.93 m
  over three hits, out of a knife's reach), so a stand that does not follow its target reads as half the
  swings missing on BOTH sides.

**A remote fire cue per shot, not per changed counter (PLAN.md N3, 2026-09-14).** A puppet played ONE cue
whenever the replicated u8 `fireSeq` changed, so a dropped snapshot — or the host re-broadcasting two
client snapshots in one interval — collapsed a full-auto burst into one sound and tracer. The counter
already says how many shots happened: `net.FireCuePolicy.cuesFor(haveLast, last, now, cap)` is the
wrapping delta, capped at `MAX_CUES` (4 — past that a gap is a stall or a rejoin, not a burst), and 0 on the
first snapshot. `NetworkController` and `VehicleNetworkController` hand it to
`WeaponController.playRemoteFireCues`, which plays the first cue now and the rest at the held weapon's fire
interval (kept between two frames and 0.12 s, in `_process`) and counts `fire_cue_burst_replayed`. A melee
weapon replays only its latest swing: a swing restarts the one before it, and the step on the snapshot is
the latest. The draw-window gate inside `playRemoteFireCue` applies to every replayed cue. Gates:
`FireCuePolicyTest` (one shot, a collapsed burst, wrap at 255, cap, first snapshot, the melee cap of 1);
`probe_melee`'s puppet replay still passes; `run_net_shot_test.sh` still one fallback per pull.

**Rockets and grenades are flown by the host; clients relay no damage but their own (PLAN.md N4,
2026-09-14).** A client simulated its own rocket or grenade and relayed the blast's damage per victim, while
every other peer flew a cosmetic copy from the fire cue that could explode somewhere else. The blast players
saw and the damage applied could disagree.
- **`MSG_LAUNCH` (tag 28, channel 1)**: `attackerId, slot, launchSeq, origin, aim` (a grenade's aim BEFORE
  its arc). The owner client sends it and flies a COSMETIC predicted copy. The host judges it with
  `ShotValidationPolicy` at a cone of 0 (owner, advancing counter, the weapon's fire-rate budget, origin in the
  body volume, aim within 35°, a launcher in the slot) and flies the only projectile that damages
  (`ProjectileItem.launchFrom` / `ThrowableItem.launchFrom`). Counted `launch_accepted` /
  `launch_rejected_<verdict>`. **On the host a puppet's fire cue no longer spawns a copy**
  (`launch_cue_host_skipped`), because its real projectile arrives as the message.
- **`MSG_DETONATION` (tag 29, reliable channel 0)**: `attackerId, point`, broadcast when a host projectile
  explodes. A peer's cosmetic copies are filed per attacker, oldest first (`weapon.ProjectileLedger`;
  launches and detonations of one attacker arrive in order), and the host's k-th detonation explodes the
  k-th live copy AT THE HOST'S POINT (`CosmeticProjectile.snapDetonate`). A copy that reaches its own
  detonation first hides and waits 0.5 s for that point, then explodes where it is
  (`detonation_local_timeout`). A detonation with no copy draws the explosion at the point. The ledger is
  cleared with the session.
- **Damage requests**: `DamageRequestPolicy.AREA_ALLOWED = false` (`KIND_REFUSED`), and
  `Health.relayDamageToAuthority` sends only SELF damage (fall, drowning, the peer's own vehicle). Damage
  predicted on an entity the peer does not own is never relayed (`damage_relay_suppressed`).
  `NetworkManager.localAttackerId` is gone.
- **A grenade could never be thrown** (found by this check, single-player included). W21's `pointsAtAim` gate
  compares the HELD ITEM's model forward with the aim, which is a barrel's direction and nothing a grenade in
  the hand has. `ThrowableItem.launchesTowardAim()` is now false: a throw's direction is body → aim point, it
  leaves in front of the chest and ignores its thrower, so the gate's self-hit reason does not apply.
- Gate `tools/net/run_net_launch_test.sh` (`debug/NetLaunchTest.tscn`, `NetLaunchTestHost`; host, client, an
  observer and a CONTROL observer that drops detonations), 22/22. The client fires 3 rockets and throws 2
  grenades through `Input`: 9 launches sent (5 + 4 forged), 5 accepted, 5 host cue copies skipped, 5
  detonations broadcast, one explosion drawn per blast on host, client and observer, each copy snapped to the
  host's point (prediction 0.00–0.18 m off), no damage from any predicted blast. Refused forgeries: replayed,
  from 10 m, for a body the sender does not own, aimed backwards. The control observer times out and explodes
  every copy exactly once. `run_net_melee_test.sh` 16/16 (its AREA forgery now `KIND_REFUSED`),
  `run_net_shot_test.sh` 18/18, unit tests green. Harness trap: switching weapon on the frame after a press
  drops the press W21's aim gate is holding for one frame, so a stand that switches straight after its last
  rocket loses that rocket.
  `resolveSightPoint` and `trace` live on `WeaponItem` for that reason: a firearm and a melee weapon
  must not come to disagree about where an attack is aimed or what may block it.

### Co-op in DebugWorld — the client's limiter and the joiner's spawn (PLAN.md P0 0.5, 2026-09-16)

User: "co-op stopped working in debug world". Two defects, both reproduced on the REAL scene and each
with a control:
- **The client rate-limited the HOST.** `onPacketReceived`'s token bucket (70/s, burst 60) is a guard
  against a flooding CLIENT, but it ran on every peer, so a client throttled the authoritative stream
  it joined. The host's frame count grows with the world: once both DebugWorld zones stream (~20
  characters) every snapshot splits into several MTU frames (`snapshot_batch_split`), and the client
  dropped **~20 packets a second** (400 in 30 s) — snapshots, spawns and damage alike. The limiter is
  now host-side only (`amServer`). The test hosts never streamed enough characters to cross it.
- **A joiner spawned in the sea.** DebugWorld had no `PlayerSpawn` marker, so
  `GameManager.jitteredSpawnPosition` fell back to a box around the world origin, which in DebugWorld
  is the water gap between the islands (the client appeared at y −0.7, 250 m from the host). DebugWorld
  has a `PlayerSpawn` now, and the fallback with no marker is 3–5 m beside the host's own player (which
  stands somewhere playable by construction), with the origin box only as the last resort.
- Also: `WeaponProgress` threw "previously freed instance" for the frames between a client freeing its
  pre-placed Player and the HUD re-wiring (guarded), and `DebugHarness`'s auto-walk dragged the first
  registered Player, which on a client is the host's puppet (now the locally owned one).

`DebugHarness` gained headless co-op flags: `-- --net=host|join` (F6/F7 two seconds after ready),
`--net-diag` (`NetworkManager.NET_DEBUG_VEHICLES`, the per-peer character/vehicle dump every 2 s) and
`--hold-action=<action>` (holds a real input action from 6 s, a walk rather than the auto-walk drag).
Gate **`tools/net/run_net_debugworld.sh`** 15/15: phase *walk* (both players hold a movement action —
no drops, no JVM exception, the joiner at `PlayerSpawn` on the ground, each walk seen on the other peer)
and phase *tour* (the client auto-walks both zones — the host streams `debug_a` + `debug_b`, no drops).
Controls: the limiter back on the client → *tour* 400 drops; no marker and no host-relative fallback →
the joiner 247 m away at y −0.7. Trap: a `SceneTree` `--script` that `change_scene_to_file`s DebugWorld
and presses F6/F7 through `push_input` hosted and "connected" but no ENet event ever arrived on either
side (not explained); run the scene as the main scene with the harness flags instead.

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
- **A defeated driver stays in the seat, GTA-style, and the car coasts (PLAN.md 0.2, 2026-09-14; user
  decision: "stay seated", not eject).** An ambient car's brain is on the VEHICLE (Design B), so killing the
  AI at the wheel used to change nothing. `Vehicle.watchDriverDefeat` (top of `_physicsProcess`, an EDGE on
  every peer so the plate re-tints everywhere; `Health.died` fires only where damage is applied) emits
  `nameplateChanged` and, where a `VehicleAIController` is present (the simulating peer), frees it: no
  throttle, brake or steer, so the car coasts until it stops or hits something, then parks. No new message.
  A PLAYER driver is deliberately not touched. The body is a SEATED CORPSE
  (`CharacterRagdoll.enableSeatedDeath`): AnimationTree off, every aim/IK modifier off, bones off the hitbox
  layer, NO simulation (bones in a moving hull tumble out of it), and a procedural slump. The slump pitches
  `spine_01..head_2` forward about MeshRoot's lateral axis, expressed in each bone's own frame, so it does not
  depend on how the importer oriented the bones. It is a placeholder for an authored clip (P6). The car is
  still `isAiOccupied`, so a player takes it by the carjack path; `CharacterDriveState.exit` sees the corpse
  and `releaseSeatedCorpse` starts the ordinary ragdoll beside the car. `reactToCarjack` ignores a dead AI.
  `ZoneManager` reclaims such a car as **`abandoned`** once it is below 1 m/s and beyond
  `stallReclaimMinDist` of every player (no brain means neither `unrouted` nor `stalled` could fire).
  `Vehicle.updateSeatPosture` skips a dead rider. Gate **`tools/godot/probe_dead_driver.gd`** (20/20, uses
  `debug/VehicleProbeHelper` for the unregistered seat/kill/carjack calls): brain dropped, plate neutral,
  car at rest (4.0 s from 22.7 m/s on east_R1 — it runs off the curving lane into the verge), corpse within
  1 cm (plus one tick of travel) of `Seat0`, not simulating, chest leaning 30.7° → 49.9°; the control car
  still driving at 22.8 m/s; a carjack seats the player and ragdolls the corpse; an ambient car reclaimed as
  `abandoned` 9 s after its driver dies. With the hook disabled: the three car checks fail. Probe trap: a
  carjacked player is PINNED to the seat, so moving them does nothing, and the car 250 m east unloads zone
  `debug_a` and every ambient car in it. Exit first.

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
godot-jvm registration scanner (see Known Quirks).

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

Player input is camera-relative (rotated by `camRotation` at the source, in `PlayerController`).
AI input is world-space (set directly by the AI FSM).

**Combat facing is the AIM yaw, not the camera yaw.** `MovementController.aimYaw()` yaws `meshRoot`
toward `Character.getAimTargetPosition()` — the same world point the spine IK (`SpineAimModifier`,
a `LookAtModifier3D` tracking the `AimTarget` marker) and the bullet converge on. The TPS camera
sits off the shoulder, so its yaw and the body→aim-point yaw differ by several degrees at close
range: keying the body off the camera left the visible body/gun square to a wall while the shot
went past it. It falls back to the raw `camRotation` for a non-`Character` body or an aim point
within 0.5 m horizontally (directly overhead/underfoot). Together with the muzzle leg of the
two-stage trace this makes the three agree — body, bone-driven gun, and bullet.

---

## Animation — the export pipeline, the Root-bone rule, and how to MEASURE it (2026-09-07)

The AnimationTree, `AnimationController`, `PlayerController` and the stances are **as committed** —
a session of changes to them was reverted after making things worse (`PLAN.archive.md`, "Reverted: the aim /
rotation changes"). What survives below is only what was measured. The player-facing rotation
complaint (lower body ~90° off the aim while the AI is correct) is **still unexplained** — see the
end of this section for what was ruled out, so the next attempt does not re-tread it.

### Export pipeline

Source of truth is `assets/merged_animation.blend`, exported by
`blender/tools/export_character.py` to `assets/merged_animation.glb`, which
`assets/merged_animation.tscn` instances and `CharacterVisuals_GodotChan.tscn` drives.
**The glTF animation name is the ACTION name**, and Godot's importer strips a trailing `-loop`
(that suffix is what sets loop mode) — action `crouch_idle-loop` arrives as `crouch_idle`. Two traps
that both shipped: an action that is both the *active* action and stashed exports **twice**, merged
into one animation with doubled channels (the 318-channel clips), and the object's active action
exports even when it is on no NLA track. Keep one named NLA track per clip and leave
`animation_data.action` at `None`. `blender/tools/check_character_anim.py` fails on either.

### The Root bone is a shared origin, not a per-clip pose

**Every clip in one blendspace ring must agree on `Root`.** `Root` sits above `pelvis`, so a
translation on it moves the whole skeleton, feet and all — and with it `WeaponAttachment` (a
`BoneAttachment3D` on `hand_r`, carrying the gun and its `Muzzle`, which is
`FirearmItem.resolveShotOrigin`'s shot origin) and every `PhysicalBone3D` hitbox. A ring whose
points disagree on `Root` therefore translates the body, the gun and the hitboxes together, which
reads as a lurch. Upright obeys this (Root.y spread ≤ 0.028 m). Crouch did not, in three ways, all
repaired in the `.blend` and verified:

- the four **diagonal** crouch_idle_deep clips had a crouch_idle_deep→walk stand-up baked into their first 7 frames and
  looped it forever — 23 cm of vertical pumping per cycle. The pose at frame 7 was bit-identical to
  frame 31 (max error 0.00000), so `[7..31]` was the real loop;
- `crouch_walk_forward/back` carried a constant 18.3 cm `Root.location[1]` offset no sibling had;
- `crouch_idle_deep` (the ring centre) is a far deeper squat than its own eight corners — hips 0.292 vs 0.486.
  A `crouch_idle` clip built from `crouch_walk_forward` frame 1 exists in the `.blend` for this and
  is currently **unused**: wiring it as the blendspace centre is a one-line scene change that takes
  the idle→walk gun step from 0.13 m to 0.00 m.

Measured after the repairs: diagonal in-loop gun bob 0.14 m → 0.05 m (equal to the cardinals), gun Z
spread across the crouch_idle_deep cardinals 0.22 m → 0.00 m, feet still planted. When adding a locomotion
clip, measure `Root` against its ring first — a per-clip offset is invisible previewing one clip at
a time and only appears when two are blended.

### How to measure this rig without fooling yourself

Three traps, each of which cost a wrong conclusion this session:

- **`get_bone_global_pose()` / `get_bone_pose_rotation()` return the PRE-modifier pose.** Skeleton
  modifiers (`SpineAimModifier`, a `LookAtModifier3D` on `spine_03`) write into the final pose only,
  so a perfectly working modifier reads as completely inert through those accessors — identical
  before and after toggling `active`, under every `forward_axis`, in both callback modes, and after
  `Skeleton3D.advance()`. Read the final transform through a **`BoneAttachment3D`**, which is what
  skinning and `WeaponAttachment` use.
- **Derive a YAW "forward" from a PAIR of bones**, never from one bone's own `+Z`. A thigh's local
  axes run down the bone, so comparing raw bone bases across the body compares nothing. Use the hip
  axis (`thigh_l`−`thigh_r`), the shoulder axis (`clavicle_l`−`clavicle_r`), or heel→toe.
  **But do not carry that rule into ELEVATION**, which is how W1 hid: the obvious chest pair,
  `spine_03 → head_2`, runs UP the neck, and elevation is a useless coordinate for a near-vertical
  vector — it read a chest tracking the aim 1:1 as FOLLOW 0.15. For pitch, use the bone's own
  forward, having first MEASURED which axis that is (`spine_03`'s `+Z` lands on the mesh forward and
  its `+X` on the clavicle axis, so its basis is genuinely the chest frame) — and mind the sign: a
  camera looks down −Z, a bone here does not.
- **The mesh is −Z FORWARD** (`MovementController.aimYaw`'s `atan2(-dx, -dz)` is the same fact). An
  aim target at +Z is *behind* the character and makes the spine modifier twist the chest ~180°.

`tools/godot/probe_character_aim.gd` does all three correctly and is the tool to reach for.

### Measured content facts (not code — these need authored clips)

Shoulders-minus-hips yaw with the chest held on an aim target, per blendspace corner:

| corner | Upright | Crouch | Crawl |
|---|---|---|---|
| idle / fwd / back | 0° | −3° … +12° | chest **−114°** |
| left / right | **−62.9° / +57.0°** | −3.0° | — |
| fwd-left / fwd-right | −42.1° / +45.6° | **−46.1° / +39.8°** | −67.7° / −44.3° |

The **upright** `walk_left`/`walk_right` are turn-and-walk clips, not true strafes, and the
diagonals in both stances turn too — while the crouch_idle_deep cardinals are proper strafes. With the upper
body on the aim, a 40–63° pelvis swing reads as the legs facing the wrong way. **Crawl's chest sits
−114° off its own hips in the clip itself**, and a spine look-at cannot fix that: the modifier
*overwrites* `spine_03`, so its result is a function of the parent chain, and a prone `spine_02` is
~86° pitched (solving a corrected `spine_03` into the clip changed the rendered result by exactly
zero). Prone aiming needs an authored prone aim set.

### SOLVED: the player's ~90° body rotation while the AI is correct (2026-09-08)

**One engine object, TWO JVM wrappers.** A node reference exported through a scene
(`node_paths=PackedStringArray("player")`, i.e. `@Export CharacterBody3D player`) is resolved when
the scene is instantiated, and godot-jvm can hand back a **second JVM instance** for
that engine object — identical `get_instance_id()`, different Java object, and **none of the state
the body's own `_ready()` wrote**. Engine calls (`isOnFloor`, `getGlobalPosition`, `moveAndSlide`)
go through the bridge and are correct on either wrapper, which is exactly why this hid for so long;
**Java fields are not**.

So `MovementController.aimYaw()` called `getAimTargetPosition()` on a `Character` whose `aimTarget`
marker was **null**, got the BODY's own position back, failed its own "too close to yaw toward"
guard (`AIM_FACING_MIN_DIST_SQ`), and returned `camRotation` — the camera rig's **local** yaw under
a `setAsTopLevel` frame, which is not a world direction at all. Measured on
`world/hosts/AimDebugAuto.tscn`: **the mesh 90° off the aim point in every stance**, the aim marker
sitting 1998 m out while the same call inside `_physicsProcess` returned the body position
(`charInstanceId` identical, `identityHashCode` different — that print is what finally named it).

**And that is why the AI looked right.** The fallback is `camRotation`, and
`AICameraController.gatherLookInput` drives `controlRotation.yaw` to `atan2(-dx, -dz)` toward the
AI's own aim target — so for an AI the fallback happens to BE the correct aim yaw. The player's
`camRotation` is mouse intent under a frozen parent frame, and is not.

Whether a given export is stale **depends on resolution order and can only be measured, not reasoned
about**: on the same body, `AnimationController.player` measured stale (so `getLodLevel()` always
read a fresh field and the PASSIVE/FROZEN AnimationTree skip — the dominant per-AI saving, Part D/D2
— had **never once fired**) while `TPSCameraController.player` measured live. The rule is therefore
unconditional: **never read Java-side state through a scene-exported node reference; re-resolve the
path at runtime** (`getNodeOrNull(player.getPath())`, cached). `MovementController.body()` and
`AnimationController.lodBody()` are that, and `MovementController`'s authority gate, swim settle
depth and fall-damage attribution were all silently reading defaults too.

### The other half: the movement frame no longer rebuilds the camera's yaw

`TPSCameraController` is `setAsTopLevel(true)`, so its world yaw is whatever the body's was at the
instant its `_ready()` ran, and `PlayerController` added `body.getRotation().getY()` back to
compensate — right only while the body's yaw has not changed since. It takes the frame off
**`ActiveCamera`'s own world basis** now, which is one owner, needs no compensation term, and covers
FPS and the vehicle seat for free (every camera mode writes that node's global transform).
`getCurrentYaw()` is deleted so there is nothing left to reach for. Likewise
`MovementController.playerInitRotation` (the body's yaw cached in `_ready()`) is gone: the body's
**current** yaw is read every frame.

Both were latent until a body was rotated after `add_child()` — which is what every code spawn path
does, and what `AimDebugHost` did. Measured before/after with `tools/godot/probe_camera_frame.gd`,
which runs one Player both ways: rotate-after went from **−90° of movement error and +88° of facing
error** to 0.00 and 0.00, rotate-before (the world scenes) was and stays clean.

### The stands: `AimDebugAuto.tscn` (asserts) and `AimWorkbench.tscn` (shows)

`world/hosts/AimWorkbench.tscn` is the same host with `workbench = true`: a **mannequin** (a real
`AICharacter` with its `AIController` swapped for a `ScriptedInputController`, so it holds a pose
instead of wandering), a movable **aim ball**, and a **free-fly camera** (`G`, which freezes the
Player because both want WASD). Keys: `1/2/3` stance, `4` combat, `Q/E` weapon slot, `F` fire (through `UserCommand.fire`, so the
real trace/recoil/bloom/stimulus path runs), `I/J/K/L`+`U/O` the ball, `H` to drop the Player and
fly with no character. It also spawns a **car and a pool**, the only way to reach DriveCarrier and
Swim, and prints a setup line per body (controller, stance, aim mechanism, yaw cap, held weapon). **Driving an AI's aim needs BOTH halves** — the command's `aimTargetPosition` (which moves
the `AimTarget` marker) AND `AICameraController.setAimTarget` (which swings the rig that owns the
`AimRay` the marker hangs off); with the command alone the gun sat 91.6° off. Two more traps it
surfaced: the first `Muzzle` in a subtree is **not** the held weapon (ask
`WeaponController.getCurrentWeaponItem()`; a stowed gun read 91.6° while the chest was 4.6° off),
and a weapon switch must finish before a gun angle means anything (63.0° mid-transition, 3.3°
settled). Artist-facing guide: **`blender/CHARACTER_AIM_AUTHORING.md`** — aiming is procedural, so
a new model needs **one aim pose per weapon type**, not one per stance.

**`Stance.aimYawLimit` caps the aim's YAW only** (upright 80, crouch_idle_deep 75, crawl/drive/swim 45) so
the spine and neck cannot twist to an inhuman angle. Elevation is deliberately uncapped — the
camera already bounds it to -55..+75 and a cap tight enough to matter there took upright's chest
FOLLOW from 0.94 to 0.47. `SpineAimModifier` takes it as `primary_limit_angle` (secondary left at
179); `ShoulderAimModifier` clamps it itself, **about WORLD UP and against `MeshRoot`'s forward**.
Three wrong frames were measured first, and each is a trap worth knowing: the reference BONE's own
frame (a prone `spine_03` is pitched 88 deg, so its "yaw" is world PITCH — crawl's head FOLLOW fell
0.93 -> 0.32), the `Skeleton3D` node's basis (it carries the glTF import's orientation, gun 42.8
deg off), and the bone's own flattened forward (a prone chest points at the FLOOR, so its
horizontal projection is noise, 21.2 deg off). Left without a body frame the clamp is SKIPPED, not
applied against a bad one.

### The gate: `world/hosts/AimDebugAuto.tscn`

`AimDebugHost` presses its own keys and moves its own mouse through the real `Input` singleton — so
the shipped `PlayerController → Character → MovementController` path is what runs — and asserts 12
cases: walk forward/back/left/right at two view headings, and aim-standing in upright/crouch_idle_deep/crawl.
**12/12 at 0.0° error.** Run it with
`godot --headless --path . res://src/main/resources/com/openworld/world/hosts/AimDebugAuto.tscn`;
`AimDebug.tscn` is the same stand for walking around by hand.

Two rules are built into what it asserts. It measures **`meshRoot`**, which is what the code owns,
and prints the clip's own hip yaw (`hips − mesh`) beside it rather than folding them into one
number — the crawl aim pose carries **8.2°** of its own and the upright `walk_left`/`walk_right`
clips up to 63° (the table above), so a single combined number lets an authored pose fail a frame
check or mask one. And every assertion is a **difference of two world yaws**, never an absolute one,
so it does not care where the stand puts the body or which way the camera starts.

**W1, elevation — CLOSED 2026-09-08. The gate now reports `yaw 12/12, pitch 3/3` and exits 0.**
Three things, and only the middle one was the defect the plan had named:
- **The instrument was measuring the wrong axis.** The pitch cases took the chest as
  `spine_03 → head_2` — a bone PAIR, the right instinct for YAW, carried over without re-deriving
  it. That vector runs UP the neck, and elevation is a useless coordinate for a near-vertical
  vector: **upright was never at 0.15**, it tracked the aim at 0.94 the whole time while the
  up-axis metric reported 0.14 for the same motion. The gate measures `spine_03`'s own local **+Z**
  now — measured, not assumed: in the rest pose that axis lands on the mesh forward (world −Z) and
  `+X` lands exactly on the `clavicle_l − clavicle_r` axis, so the basis IS the chest frame here.
  **The sign is the opposite of a camera's** (a camera looks down −Z); copying that convention onto
  a bone read a perfect track as FOLLOW −0.94.
- **Crouch and crawl really were inert**, because `Character.tscn` set `spine_aim_max_angle = 0.0`
  and `updateAimModifiers` read it as an on/off flag. Fixed: crouch_idle_deep **0.00 → 0.94** and crawl
  **0.00 → 0.96**, both with the chest within 0.0°/7.5° of the view, matching upright.
- **`Stance.spineAimMaxAngle` is now `spineAimEnabled`, a boolean — after being made a real angle
  and measured.** W1a did push it into the modifier's `use_angle_limitation`/`primary_limit_angle`/
  `secondary_limit_angle`, and that works; the measurement is what retired it. **The limit is taken
  from the bone's REST pose**, so it must cover the camera's range PLUS however far the stance's
  clip already holds the chest from the aim. Upright FOLLOW by limit: 60 → **0.47**, 90 → 0.70,
  135 → 0.92, off → 0.94; crawl needs **300** to reach 0.89, against an engine default of **360**
  (uncapped — read off the node, with damp thresholds at 1.0, so no damping is involved). **A cap
  loose enough not to hurt is indistinguishable from no cap, and it bites hardest exactly where the
  aim needs the most help.** Nothing is lost: the modifier runs only in combat, and in combat
  `MovementController.aimYaw()` turns the whole mesh to the aim point, so the twist a cap would
  prevent cannot arise. A stance that ever needs limiting wants PER-AXIS limits — one symmetric
  number cannot serve a yaw cap and an elevation range at once. `false` (DriveCarrier, Swim) still
  means "this stance does not aim".

`AnimationController.aimIk`/`weaponIKTarget`/`weaponIKBasePosition` and `Stance.weaponIKOffset` are
**deleted**: wired in no scene, read by nothing, and with the spine tracking the view to within 0.0°
there is no residual elevation for arms to take. The spine modifier is the whole aim mechanism.
**A stance whose BODY must not move aims with `ShoulderAimModifier`, not the spine** (2026-09-08).
`SpineAimModifier` is a `LookAtModifier3D` on `spine_03` with one strategy — rotate that bone until
the chest points at the target — so in crawl it hit the target by standing the torso up (measured:
`aim up, crawl` gave chest **+55.0°**, on a body lying on the ground), and switching it off is why
crawl, DriveCarrier and Swim did not aim at all. **`clavicle_l`, `clavicle_r` and `neck_01` are all
direct children of `spine_03`**, so `character.ShoulderAimModifier` (a custom `SkeletonModifier3D`
— a `LookAtModifier3D` aims a bone's OWN forward, and a clavicle's runs sideways along the
collarbone) applies the very same delta one level down: the arms, the weapon and the head swing to
the aim while the spine, pelvis and legs do not move at all. It must sit AFTER the spine modifier
in the skeleton's children (modifiers run in tree order), and `Stance.shoulderAimEnabled` is
mutually exclusive with `spineAimEnabled` — both would apply the rotation twice. Measured on
`AimDebugAuto`: crawl's chest swing **0.00°** across a 130° view swing, head FOLLOW **0.93**, gun
**1.5°/6.1°** off the aim against upright's 1.5°/5.9°. DriveCarrier and Swim are wired the same way
but have no case in the stand.

**Historic — the reading that hid it:** The
pitch cases measure where the chest points, so crawl passes at 0.96 — but read the absolute value
beside it: aiming up, `view 55.0 / chest +55.0` means the chest is 55 deg above horizontal **on a
body lying on the ground**. The look-at hits the target by standing the torso up. That is inherent
to the instrument: a `LookAtModifier3D` has one strategy, rotate this bone until it points at the
target, and cannot know prone should spend the aim in the arms and neck instead. **A procedural
look-at is the wrong instrument for a pose that differs in KIND, not degree** — prone wants an
authored aim offset (top/normal/bottom), with the modifier off for that stance. `AIM_PLAN.md` W4
carries the three options and the recommendation.

**Crawl's other gap is the YAW** — its chest now tracks 0.96 and sits within
5.8° of the view, but the clip holds it −114° off its own hips, and a spine look-at provably cannot
repair that (the modifier overwrites `spine_03` only, so its result stays a function of a prone
`spine_02`). That needs an authored prone aim set — for which `aim_pistol_crawl-loop` is the
starting point, and the reason the orphan aim clips are kept rather than deleted.

**The crouch_idle_deep aim CLIP was not the problem.** `merged_animation.blend` carries
`aim_pistol_crouch-loop` and three siblings, and they are real stance poses — but `WeaponBlend` is a
**filtered** `Blend2` taking only clavicles/arms/hands/fingers from the aim branch, and over those
**38 filtered bones they are bit-identical to the upright clip** (worst rotation 0.0000°). The
author changed only the lower body, which the filter discards, so a per-stance aim branch would
change the render by exactly zero. Two eyes came out of that: `check_character_anim.py`'s new
**`orphan_clips`** WARN (a clip that exports but is named by no AnimationTree node is unreachable —
13 today, including `crouch_idle`), and a fix to `tools/godot/probe_character_aim.gd`, which was
setting `AimStanceTransition`/`WeaponAimCrouch`/`WeaponAimCrawl` — **none of which exist**, and
`AnimationTree.set()` on an unknown parameter is silently ignored.

### W2 — A LEG ANIMATION'S FRAME IS THE MESH'S OWN FACING (CLOSED 2026-09-08)

The combat strafe blend picked its corner in a frame that was wrong for both bodies, in two
different ways, and the pair was inverted on top. The Player's direction is converted to world space
by `PlayerController` **at the source**, and `AnimationController.worldSpaceMovement` was `false`, so
the corner was read off the WORLD COMPASS — walking north played the same clip whichever way the
character faced, and at a view heading of 0 pressing forward selected `walk_right` (measured). The
AI rotated by `-camRotation`, the camera rig's LOCAL yaw under a `setAsTopLevel` frame, which reads
as plausible only because `AICameraController` drives that yaw toward the AI's aim yaw. And
`updateAnimationBlend` negated X to reach the blendspace's frame (`+X = walk_right,
+Y = walk_forward`), which with a correct frame is a 180° error.

`AnimationController.meshRoot` is the one owner now — wired from `MeshConfig.meshRootPath` in
`Character.wireFromMeshConfig`, beside the `ShoulderAimModifier` wiring that needs the same node for
the same reason. The direction is projected onto the mesh's **global** basis (`+X` right, `-Z`
forward), so the body's yaw and the mesh's local yaw are both accounted for with no compensation
term, and player, AI and puppet share it. Both `worldSpaceMovement` flags are deleted — the
`AnimationController` one is replaced by this and the `MovementController` one was declared and
never read. `AnimationController.onSetCamRotation` went with them (nothing read it), along with the
`set_cam_rotation → AnimationController` connection in `Character.tscn` and the yaw argument of
`Character.applyReplicatedLocomotion` — a puppet is if anything better off, because
`applyReplicatedFacing` writes `MeshRoot` from the same snapshot **before** the locomotion apply.

**A SIGN TEST IS NOT ENOUGH, and that is the part the plan did not anticipate.** In combat the mesh
faces the AIM point while the camera sits off the shoulder, so walking straight forward leaves a few
degrees of lateral component whose SIGN is perfectly definite — enough to pick a diagonal clip for a
straight-ahead walk and flip it left/right as the parallax changes sides.
`AnimationController.AXIS_DEADZONE` is `sin(22.5°)`, the eight-way quantisation the blendspace's own
`snap = (1, 1)` already implies, so each corner owns a 45° wedge.

Gated by `AimDebugAuto`: **`strafe 10/10`** (four directions at two view headings plus two in
crouch_idle_deep) and **`ai 4/4`**, both verified to go to **0** when the old frame is put back. They assert
the blend INPUT, read off `parameters/<Stance>MovementBlend/blend_position`, never the hips — the
upright `walk_left`/`walk_right` clips carry up to 63° of hip yaw of their own, so a hips reading
cannot separate "the wrong clip was chosen" from "the right clip is authored that way".

### W3 — ONE CAMERA CONVENTION: `controlRotation` IS A WORLD ROTATION (CLOSED 2026-09-08)

The camera rig produced this file's other two aim bugs and was the shape behind both.
`TPSCameraController` is `setAsTopLevel(true)`, which detaches the rig from the body but
**preserves its global transform at the instant it is called** — so `controlRotation.yaw` was a
LOCAL yaw under a frame frozen at the body's `_ready()`-time rotation, which is why
`PlayerController` had to add the body's yaw back (and broke the moment a body was rotated after
`add_child()`) and why `MovementController.aimYaw()`'s fallback put the player 90° off. On top of
that the chain carried **two cancelling 180° Y flips** (the rig node's own transform and `Pivot`'s)
and `AICharacter.tscn` overrode `Pivot` back to identity — so player and AI rigs were literally
different shapes, and the second flip also turned `Rot_x(pitch)` into `Rot_x(-pitch)`, making
positive pitch mean look DOWN.

**The rig states its world basis every frame** (`setGlobalRotation(ZERO)` in
`TPSCameraController._physicsProcess`, before the positioning block that reads `yawNode`'s global
basis, and the same in `FPSCameraController`), and all four flips are out of `Character.tscn` —
so `AICharacter.tscn`'s `Pivot` override is deleted as redundant. **Positive pitch now means LOOK
UP**, written on `ControlRotation`, with every owner of that sign moved together: `pitchMin`/
`pitchMax` are −75/+55 (the same view range, said the right way round), both `applyRecoil`s add
instead of subtract, `PlayerCameraController._input` subtracts the mouse's downward-growing Y, and
`AICameraController` loses its negated pitch and its negated-body-yaw fallback (it tracks
`getFacingYaw()`, where the MESH points, which is what a facing actually is).

Measured: the AI camera's error against its own aim point **90.1° → 0.8°** (now asserted by the
gate, and 179.3° with the `Pivot` flip put back); TPS vs FPS forward **dot = 1.0000**;
`probe_camera_frame.gd` reports a rig root world yaw of **0.00** whether the body is rotated before
or after `add_child()`.

**THE CAMERA SWAPPED SHOULDERS, AND THE FIX BELONGS IN THE DATA.** The shoulder offset is applied
along the `Yaw` node's X; under the old rig that axis pointed *opposite* the camera's own right, so
a POSITIVE `cameraShoulderOffset` produced a LEFT-shoulder camera. Removing the flip makes the axis
honest and mirrors the framing — measured `yawRight · camRight` **−1.000 before, +1.000 after** — so
the authored values in `combatstates/*.tres` were negated to keep the side the game ships with.
The sign now MEANS something (positive = right shoulder) instead of being absorbed by a flip.

**The VEHICLE rig is deliberately untouched.** `VehicleCameraController` has its own
`yaw`/`pitch`/`pitchMin`/`pitchMax`, its own scene under `Vehicle.tscn`, and still carries the
`Pivot` flip — positive pitch is still DOWN there and its `applyRecoil` still subtracts. It shares
no state with `ControlRotation`, so it is self-consistent as it stands; a note at its `applyRecoil`
says so, because matching one half of it to the character convention is how a sign bug is born.

**One thing the driven gate still cannot see** and that was checked with a throwaway probe instead
— add a case before trusting it again: which **shoulder** the boom sits over. One probe trap came
out of it: a body with no floor under it FALLS, and the camera's follow-lerp then lags into a
reading that looks like "above and behind" but is just late. (`is_fps_mode` was the other, and it
is fixed — see W5 below.)

Still content, not code: the per-corner hip swings in the table above.

### W5 — THE THREE VIEWS: registration, a filtered eye point, and a stance-owned elevation limit (2026-09-08)

Four user reports, one area. `tools/godot/probe_fps_camera.gd` is the gate for the first three and
`AimDebugAuto`'s new `limit` axis for the fourth; both are green (`PASS (0 failures)`, and
`yaw 12/12, pitch 3/3, strafe 10/10, ai 8/8, limit 6/6`).

**`is_fps_mode` is a registered property now** (`@Visible` on `Character.isFpsMode`; `Node
currentVehicleNode` went with it, for the same reason). It was a plain public field, which reads
exactly like a registered one from Java and like *nothing at all* from GDScript — `get()` returned
`<null>` and `set()` silently did nothing, so a probe that switched to FPS measured the TPS camera
and reported it with a straight face. `@Visible` rather than `@Export`: it is live view state, not
something to author into a scene.

**There are THREE views and only ONE of them is inside the character's skull.** The head was hidden
by a latch — `setCameraMode` called `setHeadVisible(!fps)` once, at the toggle — so a player who
entered a vehicle while in FPS drove a headless character: nothing on the way into the seat had any
reason to put it back. `Character.refreshHeadVisibility()` DERIVES it instead, from
`isFpsMode && currentVehicleNode == null`, and is called from the toggle, from
`CharacterDriveState.enter`/`exit`, and every frame from `TPSCameraController` (which processes in
every mode — the Character's own `_physicsProcess` is switched off in the driver's seat, so it is
not a candidate). It touches the meshes only when the answer changes. The carrier case is not a
special case: `Vehicle.tscn`'s `FPSCameraMount` sits at (0, 0.34, −0.80), over the bonnet, so the
carrier's "first person" is not behind anyone's eyes and the head belongs on.

**A bone-mounted FPS camera must FILTER the bone, not copy it.** `MarkerFPSCamera` hangs off a
`BoneAttachment3D` on `neck_01`, so its world position carries the locomotion clip's head bob, the
`WeaponChange`/`Reload` one-shots, and — because `neck_01` is one of `ShoulderAimModifier`'s driven
bones — **the aim swing itself**, which is the largest of the three. Copied straight through that
is a camera that jitters at footstep frequency and lurches sideways every time you turn your head.
The industry answer (Arma, Tarkov, Star Citizen; Cyberpunk 2077 shipped a head-bob toggle for
exactly this) is to treat the bone as a *signal*, and `FPSCameraController` now does, in four
stages: work in **`MeshRoot`'s frame**, so sprinting and turning are not motion to filter at all (a
world-space filter would instead make the camera trail the body); split the signal with a slow
single-pole average (`baselineFollow`) that IS the resting eye point — it carries the mount's true
height and forward offset for free, per stance, with nothing authored; **scale and clamp** what is
left over (`boneMotionScale` 0.25, `maxBoneOffset` 0.08 m, and scale 0 is the "head bob off"
accessibility setting); then smooth (`positionSmoothing`). Orientation never comes from the bone —
it is `ControlRotation`, the same world rotation the TPS rig uses. Measured while walking with the
view swinging: the raw mount travels **0.150 m with jerk 0.081**, the camera **0.055 m with jerk
0.0055** — **14.7x less jerk** — and the eye sits **0.028 m** off the centre line, i.e. on it.
**The shoulder is not a concern here**: the over-the-shoulder offset is the TPS boom's framing
device (`CombatState.cameraShoulderOffset`, applied along the TPS `Yaw` node's X) and this rig has
no boom to hang it on; `PlayerCameraController` refuses the shoulder-swap key while in FPS.
`fpsCameraMount == null` no longer early-returns — it falls back to `fallbackEyeHeight` above the
body, because a camera frozen in the world is worse than an approximate one.

**THE VIEW LIMIT AND THE BONE LIMIT ARE DIFFERENT NUMBERS, AND THE MEASUREMENT IS WHAT SEPARATED
THEM.** They started as one — `Stance.viewPitchMax`/`viewPitchMin`, published into `ControlRotation`
by `TPSCameraController.onSetStance` and read by both rigs — on the reasoning that the bones do not
choose where they point (the aim target is where the view ray lands, so whatever the view reaches is
what the spine or the shoulders must follow). That reasoning is still right and is why the view
limit exists at all. What it missed is the response: swept per stance,
**the chest tracks the view 1:1** — view +51 gives chest +51.1, view +80 gives chest **+80.0**, a
body arched 80 deg backwards — so a view range wide enough to look at a rooftop *is* a limit that
lets the trunk fold to a pose no trunk reaches. One number could not serve both.

So there are two, and the gate asserts both:

| stance | view up | view down | **bone up** | **bone down** | measured chest at the cap |
|---|---:|---:|---:|---:|---|
| Upright | +60 | −75 | **+45** | **−65** | chest +45.0 / head +22.5 ; chest −65.0 / head −87.5 |
| Crouch | +55 | −70 | **+40** | **−60** | chest +40.0 / head +17.5 ; chest −60.0 / head −82.5 |
| Crawl | +40 | −35 | **+30** | **−30** | chest **−88.1 (unmoved)** / head +7.5 ; −88.1 / −49.1 |
| Swim | +50 | −50 | +40 | −40 | (no case — no stand covers it) |
| DriveCarrier | +45 | −45 | +35 | −35 | (no case) |

**The asymmetry runs the opposite way to the obvious guess.** A trunk bends FORWARD far more
easily than backward, and the sweep says so: upward the chest is 1:1, downward it saturates at
roughly `view + 8` (view −80 gave chest −72.4, which is just bending over to look at the ground).
So the UP cap is the one that bites and the DOWN cap can stay generous — which is also why both
`Stance.aimPitchMax/Min` and `ShoulderAimModifier.pitchLimitMax/Min` are asymmetric pairs rather
than one symmetric number.

**Past the bone limit the body HOLDS and starts tracking again when the target comes back down** —
that is the whole behaviour being bought. Nothing is lost from shooting: the bullet is traced from
the muzzle to the point the CAMERA ray found (`FirearmItem`'s two-stage resolution), so it still
converges on the crosshair while the gun is visibly held lower. **Keep the gap small** — it is
visible disagreement between the gun and the reticle, and it is reported per case as
`gun-off-aim`: 15 deg at the top of upright's range, and crouch_idle_deep's view was trimmed 60 → 55
precisely because 60 made it 20.

**One implementation, because one limit implemented twice is a limit that disagrees with itself.**
`SpineAimModifier` is no longer a stock `LookAtModifier3D`; it is a `ShoulderAimModifier` with
`drivenBones = ["spine_03"]` — the reference bone itself, which rotates that bone until its `+Z`
points at the target with the clavicles and neck following as its children, i.e. exactly what the
look-at did (measured identical). The stock modifier could not carry these limits anyway: its
`use_angle_limitation` pair is symmetric, is measured from the bone's REST pose, and mixes the two
axes — W1a measured a 60 deg cap taking upright's chest FOLLOW from 0.94 to 0.47 while still
allowing the pose it was meant to stop. `AnimationController.applyAimLimits` is the one writer.

**A TARGET STRAIGHT OVERHEAD HAS NO BEARING, AND `atan2` ON IT IS NOISE.** The elevation clamp is
rebuilt from a horizontal direction plus an angle rather than rotated, and at the extreme the
horizontal part of the wanted direction is exactly what has gone — so it falls back to the BODY's
own forward (`bodyForwardNode`, `MeshRoot`). That is the heading the character already has, so the
aim rises straight up in front of it and comes back down onto the target the moment the target has
a bearing again, instead of the bones twisting to a heading that means nothing. `MovementController
.aimYaw()`'s own guard (`AIM_FACING_MIN_DIST_SQ`) covers the same degeneracy for the mesh yaw and
was measured clean at the new limits (mesh yaw 0.06 deg off the camera at view 80, aim 347 m out).

`TPSCameraController` also re-resolves its `@Export player` at runtime before reading any Java
state off it (`getNodeOrNull(player.getPath())`), and `PlayerCameraController` reads `character`
rather than `player` throughout. That export was measured LIVE on this body — but the rule is
unconditional for a reason, and what hangs off it here is `controlRotation` (an object identity
shared with the FPS rig), `isFpsMode`, and whether the character has a face.

**THE CLAVICLE SPLIT IS BUILT, MEASURED, AND SHIPS AT 1.0 — THE SWEEP IS WHY.**
`ShoulderAimModifier.drivenWeights` is an index-parallel 0..1 weight per driven bone (empty = all
1.0), applied by scaling the delta's ANGLE about its own axis — the slerp from identity on the
shortest arc, which is why `rotationBetween` was split into `rotationAxis` + `angleBetween`. It
exists because prone the delta is **not** the aim elevation: it is measured from a reference bone
pointing at the FLOOR, so the rotation handed to the collarbones is ~130 deg, and *that* is what
reads as a dislocated shoulder. The obvious fix is to give the neck its full share and the
clavicles less. Measured on `AimDebugAuto` at a saturated prone aim:

| clavicle weight | shoulder-vs-chest | gun-off-aim | head pitch |
|---:|---:|---:|---:|
| 1.0 (shipped) | 121.1° | **9.1°** | +7.5° |
| 0.7 | 85.6° | 45.1° | +7.5° |
| 0.5 | 61.6° | 69.2° | +7.5° |
| 0.0 | 2.5° | 132.0° | +7.5° |

**The trade is worse than 1:1 and has no knee** — 1.0 → 0.7 buys 39 deg of shoulder for 36 deg of
gun — so there is no setting where dialling it down is worth taking, and at 0.7 the gun is already
45 deg off the reticle. The gun rides `hand_r` under `clavicle_r` and nothing else in the chain can
absorb the difference: the elbow and wrist are not driven. Note also that the head column does not
move: the neck keeps its full share at every weight, so the dial does exactly what it claims — the
answer is that what it claims is not worth having. **The large clavicle-vs-chest angle is therefore
not a defect to tune out; it is what makes prone aiming work at all** while the arms are posed for a
standing aim on a prone chest (the `WeaponBlend` filter takes clavicles/arms/hands from the aim
branch, and those are bit-identical to the upright clip — see "The crouch_idle_deep aim CLIP was not the
problem"). The real fix is an authored prone aim pose, where the arms START where a prone shooter's
arms are and the delta is small again (`AIM_PLAN.md` W4). The knob stays for that day, and for a
skeleton whose arms are posed differently.

The gate keeps the sweep as the evidence and asserts the one number that must not regress: at the
shipped weight the prone gun sits within `PRONE_GUN_TOLERANCE_DEG` (15) of the aim — measured 9.1.
The rows run **ascending** so the sweep ends on the shipped value and cannot leave the rig dialled
down for anything after it. Full gate: `yaw 12/12, pitch 3/3, strafe 10/10, ai 8/8, limit 6/6,
clav 1/1`.

Two things this cost that are worth not repeating. A standalone `SceneTree` probe that builds its
own world in `_initialize()` had **both** aim modifiers read `active = true` and apply nothing —
`combat` true, stance CRAWL, target path resolved, and the head still sat at the clip's −64 deg
through a full view sweep; the same measurement inside `AimDebugHost` works. Reach for the driven
stand for anything involving skeleton modifiers rather than re-deriving a rig in a bare tree. And
`WeaponController.getCurrentWeaponItem()` is **not** a registered method, so GDScript cannot ask
which weapon is held; `CharacterVisuals_GodotChan` instances only `Fist` (a `MeleeItem`, no muzzle)
under `WeaponAttachment`, so a probe measuring a gun angle must arm the body itself the way
`AimDebugHost.armStandOn` does.

### W6 — THREE DRIVING VIEWS, AND THE VIEW PREFERENCE FOLLOWS THE PLAYER INTO THE SEAT (2026-09-09)

Getting into a car threw away the view the player had just chosen, and there was no view from
behind the driver's eyes at all. Both fall out of the same shape: the on-foot rig and the carrier
rig were **two independent latches** — `Character.isFpsMode` and `VehicleCameraController
.cameraMode`, the second defaulting to TPS and remembering whatever *that particular car* was last
left in — so `tryEnter` simply called `makeCurrent()` on the carrier camera and the choice was
gone (and a different one came back on the way out).

**One fact is shared and one is local, and the split is the whole design.** `CameraMode` (TPS/FPS —
*am I in first person*) is MIRRORED across the enter/exit seam: `tryEnter` pushes
`c.isFpsMode` into the carrier rig, `tryExit` writes it back. `camera.VehicleEyeMount`
(COCKPIT/BONNET — *which* first person) is carrier-local and remembered per vehicle, because it is
a fact about the car, not about the player. `VehicleCameraController.cycleView()` is the one writer
of both, so "which view am I in" can never be assembled from two independently-toggled halves; one
press of `view` walks TPS -> cockpit -> bonnet -> TPS, and the cockpit step is skipped on a carrier
scene that has no cockpit mount, so a press always changes the picture.

**The cockpit mount is a child of the SEAT** (`Seats/Seat0/CockpitCameraMount`), which keeps the
seat the one owner of where the driver is — move `Seat0` and the view moves with it. Its height is
the one number here that cannot be derived, so it was **measured, not guessed**
(`tools/godot/probe_cockpit_eye.gd`, which drives the AnimationTree's `StanceTransition` directly
and needs no vehicle): a seated driver's eye sits **+0.809 m** above the character origin the
vehicle pins to the seat, and **0.153 m behind** it — against upright's +1.359 and crouch_idle_deep's +0.791,
which is also the check that the `DriveCarrier` state is real and not a fallback. The old
`FPSCameraMount` (0, 0.34, −0.80) is kept as the **bonnet** view: it is 0.85 m from the cockpit eye
and is a genuinely different camera (the car's own front view), not a worse cockpit.

**Head visibility gets no new rule — it gets a better question.** `Character.refreshHeadVisibility`
used to ask "am I in FPS *and not in a vehicle*", which was right only while every carrier view was
outside the skull. It now asks the one thing that was always meant: *is the camera on screen behind
THIS character's eyes* — `isFpsMode` on foot, `Vehicle.isViewInsideOccupantHead` for a driver (the
carrier is the only one that knows which of its three views is up), and `isFpsMode` again for a
**passenger**, who keeps their own camera when they sit down. That last case was a live bug: a
passenger in FPS was looking at the inside of their own head, and it closed here for free.

Gated by `tools/godot/probe_vehicle_views.gd`, which walks a real Player into a real Vehicle's
`EntranceArea` and presses `use_carrier` and `view` through the `Input` singleton — 12/12, camera
0.000 m from the mount it claims in each view. Two probe traps came out of it, both cheap to hit
again: a Player spawned inside the car's hull launches it, and **a parked car climbs at ~50 m/s
the moment any Player exists in a bare probe tree** (suspension, not this feature) — so the probe
freezes the body, which leaves every seat, mount and Area3D exactly where a parked car has them.
`probe_fps_camera.gd`'s carrier case was re-pointed rather than deleted: its fake carrier (a
`current_vehicle_node` with no `vehicleDriver`) is precisely the passenger case now, so it asserts
the passenger rule and defers the driver's three views to the probe that has a real vehicle.

### W7 — DRIVE-BY: ONE CLAMPED AIM POINT, AND A POSTURE WHERE THE BONES RUN OUT (2026-09-09)

Shooting from a car put the gun 45 degrees off the car's nose while the bullet went 180 — a driver
could shoot through their own vehicle, and the reticle said nothing. **The aim direction had two
owners and neither was the whole truth.** `ShoulderAimModifier` clamped the BONES to
`Stance.aimYawLimit` (45 for DriveCarrier), while the shot's sight leg read the carrier camera's
own ray, unclamped through 360 (`FirearmItem.resolveSightPoint`), and the crosshair sat at screen
centre on that same ray. On foot the two agree because `MovementController.aimYaw()` turns the whole
mesh to the aim point so the bone limit never binds; **a body belted into a seat cannot yaw, so the
limit binds constantly** and the disagreement is the normal case rather than the edge one.

**One clamp, on the POINT, before anything reads it.** `Character.applySeatedAimTarget` is now the
only place a seated occupant's aim target is written — for the driver (fed by the carrier camera
through `CharacterDriveState`) and for a passenger (fed by their own, through
`applySeatedPassengerInput`); both used to write the marker directly, which is how the clamp came to
have no owner. It asks the carrier (`Vehicle.clampSeatAim`) and everything downstream reads that one
result: the aim modifiers, `FirearmItem.resolveSightPoint`, the snapshot, and the reticle. There is
no second value left to disagree. `DriveCarrier`'s `aimYawLimit` therefore stops being a permission
and becomes only the RIG's reach — **two clamps on one fact is worse than either alone, because the
tighter one is invisible and the looser one is a lie.**

**The clamp is DISTANCE-PRESERVING and takes no raycast.** That makes it the identity whenever the
target is legal, so an ordinary drive-by is bit-for-bit what it was; and where it bites, the point
is still at a plausible depth, which is what lets the reticle sit on it. The shot's own stage-2
trace already runs from the muzzle along this direction to full range and hits whatever is really
there, so a query here would only produce a second answer. Clamped about WORLD UP, so elevation
survives — the same reason `ShoulderAimModifier` clamps about that axis and not the reference bone's.

**The camera is NOT clamped, and that was the deciding measurement of the design.** Clamping the
carrier camera's yaw was tried on paper first and is wrong in third person: the chase camera is an
orbiting boom a player expects to swing freely round the car (it is also the only good chase/race
view), so freezing it reads as broken input rather than as a limit. In first person the same clamp
reads as "my neck does not turn that far". One number cannot mean both, so the camera stays free —
**non-aiming driving is untouched: yaw still lerps to the vehicle heading at `yawRecoverySpeed`,
mouse input is still ignored outside aim.** What tells the player instead is the reticle:
`Crosshair.aimCharacter` anchors the whole reticle on the world point via `unprojectPosition`, so it
sticks at the sector edge and drags along it, dimming (`clampedAlpha`) while held. Two rules there:
a point BEHIND the camera has no projection and `unprojectPosition` mirrors it, so that case is
handled explicitly; and the offset is pinned at `maxAnchorOffsetFraction` rather than allowed off
screen, which in third person is the ordinary case.

**Past the rig's reach the answer is a different POSTURE, not a further twist** (the user's call,
and it is what makes a car able to cover its own back). `VehicleConfig.rearAimEnterDeg` /
`rearAimBodyYaw` / `rearAimSeatShift`: the occupant turns round in the seat and slides toward the far
side, so the bones are only ever asked for the RESIDUAL between the aim and whichever way the body
now faces — the rear sector costs the arms no more than a forward one. It rides the pin that already
existed in `Vehicle._physicsProcess` (yaw offset on the rotation it writes every tick, slide on the
position), so there is still one place that decides where a seated occupant is. **Hysteretic**
(enter 100, return 80 — a single threshold where a player's aim rests flips the body every few
frames, the same reason `Zone` has separate load/unload radii) and **eased** at `postureTurnSpeed`.
The aim modifiers need to know nothing about it: they clamp against `MeshRoot`'s forward, and
`MeshRoot` follows the body, so "the residual" is already what they measure.

**The two aim modifiers COMPOSE, so a stance can spend the aim in stages.** `ShoulderAimModifier`
measures its delta from `spine_03`'s CURRENT forward and runs after the spine modifier in tree
order, so whatever the torso covered is not there to cover again — run the spine uncapped and it
reaches the target while the shoulders then add ~0. So `Stance.spineAimYawLimit` is the torso's share
of `aimYawLimit` (the total), and DriveCarrier ships 45 of 100 with BOTH modifiers on. The
"mutually exclusive" rule in the W5 notes was right about running both UNCAPPED and wrong about
running both at all. Single-modifier stances are untouched, and `AimDebugAuto` is unchanged at
`yaw 12/12, pitch 3/3, strafe 10/10, ai 8/8, limit 6/6, clav 1/1`.

**The sector and the reach are independently authored and must relate**, so
`Vehicle.warnIfAimSectorUnreachable` says so on entry when they do not (the band between them is
where the gun visibly lags the reticle) — the `ZoneManager.warnIfMisSized` pattern, for the same
reason: neither can own the other, one is the car's and one is the rig's.

Gated by `tools/godot/probe_driveby_aim.gd`, 4/4. The sweep is produced by **rotating the car under
a held `aim`** — in FPS aim mode the camera keeps its own world yaw, so turning the car by theta puts
the aim at heading -theta exactly. Faking mouse motion with `Input.parse_input_event` was tried
first and does not arrive reliably in a bare `--script` tree; the camera's own end of the chain is
covered by `probe_vehicle_views.gd` instead. Measured across a half-turn: the aim tracks the camera
to **-179.5** and never leaves the sector, the posture engages at -110 and returns to **0.0** coming
forward, and the worst residual left for spine + collarbones is **68.3 deg against a reach of 100**.

**THE DRIVE CLIPS ARE NAMED AND THE DRIVE RING IS WIRED — the placeholder is in the data, not in
prose.** `DriveCarrier`'s blendspace played `crouch_idle_deep` at all five points, so the stance had no clip
of its own to author and nothing in the file said one was wanted. `assets/merged_animation.blend`
now carries the drive set, named on the same pattern as every other stance
(`<pose>_idle-loop`, `aim_<weapon>_<stance>-loop`):

| clip | what it is | copied from |
|---|---|---|
| `drive_idle-loop` | the seated pose — **wired** as all five points of `DriveCarrierMovementBlend` | `crouch_idle_deep-loop` |
| `aim_rifle_drive-loop`, `aim_pistol_drive-loop` | seated forward aim | the crouch_idle_deep aim pair |
| `aim_rifle_drive_back-loop`, `aim_pistol_drive_back-loop` | seated REAR aim, for the posture above | the crouch_idle_deep aim pair |

`drive_idle` is copied from `crouch_idle_deep-loop` deliberately — that is the clip the ring played — so
wiring the new name changed the seated pose by **nothing**, which is the point of an alignment
change. Re-measured: the seated eye is +0.791 m (`probe_cockpit_eye.gd`), and the cockpit mount
carries that number. The four aim clips stay **orphan** on purpose: giving them a home needs a
stance-driven branch inside `WeaponAim` that should land with the authored poses, not before them —
`WeaponBlend` is a filtered `Blend2` taking only clavicles/arms/hands from the aim branch, and the
existing per-stance aim clips are bit-identical to upright over those bones, so building the
structure now would change the render by exactly zero. Replacing any of them is a pose edit on an
existing action: no rename, no pipeline change, no scene change.

**Two names were out of line and are now one convention.** Every clip separates words with `_` and
keeps the hyphen for the `-loop` suffix Godot's importer strips — except `crawl-idle-loop`, which
spelled its own exception in the .blend, the scene AND `check_character_anim.py`; it is
`crawl_idle-loop` now. And the Crouch ring's CENTRE was `crouch_idle_deep` while the .blend carried an unused
`crouch_idle` and the checker had always *measured* `crouch_idle` — three owners, one of them wrong,
which is the 0.126 m idle→walk gun step recorded above. The scene plays `crouch_idle` now, so blend,
scene and checker finally agree; `crouch_idle_deep` becomes an orphan, and measurably nothing moved
(`AimDebugAuto` unchanged, seated and crouch_idle_deep eyes identical at +0.791). `check_character_anim.py`
gained the `drive` ring — one clip, which is the ring's true shape rather than an omission, since a
seated occupant does not locomote — and PASSes at 51 clips / 5 rings / 0 errors.

Elevation is deliberately left as W5 had it: `aimPitchMax/Min` (35) sits inside the view range (45),
a small documented gap between gun and reticle, which is a different thing from the 135 degrees of
yaw this section closes.

### W8 — THREE SIGN/SEAM DEFECTS THE DRIVE-BY SHIPPED WITH (2026-09-09, all user-reported)

W7's design was right and three of its seams were not. All three were reported from one walk-test —
"can shoot 180 on the right, forced into a small area on the left" and "FPS into a vehicle tangles
the animations" — and each is a distinct lesson.

**1. THE HEADING SIGN WAS INVERTED, AND THE PROBE AGREED WITH IT.** `Vehicle.headingDegrees` built
its answer as a difference of two world-space `atan2`s and returned **-90 for a direction pointing
RIGHT** while every comment on it said +90. So a left-hand-drive seat's sweep `[-180, +20]` opened
the whole RIGHT side of the car and shut the driver's own window — exactly as reported. It is
projected onto the carrier's own axes now (`dot(dir, basis.x)`, `dot(dir, -basis.z)`), which cannot
express the mistake: column 0 IS right and -column 2 IS forward by definition of the transform.
`Vehicle.yawForHeading` is the single owner of the other half of it — **a positive Godot Y rotation
turns LEFT while a positive heading is to the RIGHT** — and the posture is stored in HEADING space
so the two conventions meet in exactly one place.

**The probe was worthless on this because I wrote its `_heading` to mirror the implementation line
for line.** It reported 4/4 on a car whose driver could shoot out of the passenger window and not
his own. *A check that reproduces the implementation's reasoning cannot test that reasoning* — it
derives the heading from the car's basis independently now, and the reported case is its own
assertion: a left seat's own window is open (-150) and across the car is clamped (+20).

**2. A CARRIER'S AIM RAY MUST BE BLIND TO ITS OWN OCCUPANT.** `Vehicle.tscn`'s
`ActiveCamera/AimRay` has `collision_mask = 25`, which includes the HITBOX layer, and nothing
excepted the person in the seat. The cockpit camera sits *inside the driver's head*, so the ray
reported a hit on their own ragdoll bone ~0.3 m out: the aim point landed **0.8 m** from the driver
instead of 200 m, its heading read **64-118 degrees** off where the camera pointed, and because
`FirearmItem.resolveSightPoint` reads that same point for a seated shooter, **the shot was aimed
into the shooter**. It also reads exactly like the reported symptom, because the aim kept snapping
back onto the body whichever way you looked. `Character.addAimExceptionsTo` /
`removeAimExceptionsFrom` offer the set `_ready()` already excepts from the body's own ray — one
owner of "what must not be hit of mine" — and `Vehicle` applies it on every enter and undoes it on
every exit, driver and passenger alike. `VehicleCameraController.getAimTarget()`'s fallbacks now all
point FORWARD too; returning the carrier's own origin was never usable.

**Found by adding ONE column to the probe's table.** The failing sample said "camera at -40, aim at
-104" and three explanations fit; `aim-dist` separated them in a single run — 0.8 m where the healthy
rows read 200 m. When a diagnostic table has an unexplained row, add the column that discriminates
rather than reasoning about which candidate feels likeliest.

**3. THE FPS DRIVE VIEW WAS A FEEDBACK LOOP.** `AimTarget` hangs off `ActiveCamera/AimRay`,
`FPSCameraController` writes `ActiveCamera` from the filtered **neck bone**, and
`ShoulderAimModifier` drives `neck_01` *from that target*: bone -> camera -> aim target -> bone, once
per frame. On foot the loop exists and is tame — that is what W5's filtering is for (14.7x less jerk
than the raw mount). **Seated it is not:** a belted body cannot yaw, so the entire aim goes through
the driven bones, plus a posture swinging the body 150 degrees, and the loop gain goes with it. That
is the animation tangle. `Character.carrierOwnsView()` (driver only — a passenger keeps their own
camera, the same asymmetry `refreshHeadVisibility` turns on) makes both character rigs stand down
while the carrier's camera is the one on screen; for the driver the camera they were writing was not
even rendered, so the loop was pure cost. The FPS rig drops `primed` so the eye re-primes on the
frame the driver steps out instead of lerping in from a stale baseline.

Gates after all three: `probe_driveby_aim.gd` **6/6** (aim tracks the camera to -178.9 at 200 m,
posture engages at -110 and returns to 0.0, worst residual 80.0 against a reach of 100),
`probe_vehicle_views.gd` 12/12, `probe_fps_camera.gd` PASS, `AimDebugAuto` unchanged.

### W9 — THE POSTURE IS CONTINUOUS, AND A SEAT COVERS BOTH SIDES (2026-09-09, user-reported)

"On the right side it has a kind of lag, hard to track all directions, different from the GTA feel."
Two separate causes, and the GTA comparison is the interesting part of the answer.

**GTA is on the side of the restriction and against the feel.** Rockstar really does stop a
left-hand-drive driver from firing across the car — that is why passenger drive-bys exist — so W7's
sector rule was faithful. But *the restriction only reads as a rule when the player can see it*, and
here it read as a dead zone plus a body swing every time the aim crossed it. Two things made it feel
like lag rather than like a wall, and neither is a tuning problem:

**1. THE POSTURE COULD ONLY TURN ONE WAY.** The side came from whichever end of the sweep was wider,
so a left seat always turned LEFT: the entire right half of the world was reachable by no posture at
all, the aim clamped at the sweep's near bound, and the body swung back to forward whenever the
player crossed it. It turns toward the target now, whichever side that is, and
`VehicleConfig.drivebyAimMin/Max` defaults to the full circle — **a deliberate departure from GTA**,
available because the posture makes the far side reachable by a BODY rather than only by a clamp.
Restricting a seat is still authored in the sweep (`-180 / +20` for a GTA-style left seat, mirrored
automatically), which is checked and reported; a posture that silently refuses one side is not the
place for it.

**2. THE POSTURE WAS A STEP FUNCTION.** It snapped to a fixed `rearAimBodyYaw` (150) past an
enter threshold and latched there until an exit threshold — so between 80 and 180 degrees of aim the
body sat pinned at 150 while the aim was somewhere else entirely, and the bones absorbed a residual
that sawtoothed from 0 to 70 and back. **`VehicleConfig.postureHoldDeg` replaces both thresholds
with one continuous rule:** the bones carry that much of the aim and the body turns by exactly the
excess, capped at `rearAimBodyYaw`. Measured on `probe_driveby_aim.gd`, aim -179 through +179: the
residual is **flat at 80.0** at every sample (against a sawtooth of 0/9.9/29.1/31.1/70/70 before),
and the body tracks the aim — 0 at ±80, 60 at ±140, 99 at ±179, mirrored either side.

**A continuous rule needs no hysteresis** — there is no step to chatter across — which retired the
enter/exit pair. **One latch survives, for the one unavoidable discontinuity:** directly behind,
+179 and -179 are a degree apart in the world and opposite in the number, so "turn toward the target"
would flip the body ~200 degrees for a degree of aim movement. Past `postureSideLatchDeg` the body
keeps the side it already holds — stable, and nearly free, because the two poses are almost the same
one (measured: 82.1 vs 80.0 of residual at the crossing).

Gate `probe_driveby_aim.gd` **8/8**, and two of its assertions are new and only meaningful against
this rule: **the residual is flat past the hold** (a fixed-angle posture cannot produce that) and
**the postures mirror** (`+70` left vs `-70` right at ±150 — a one-sided posture reads as +150/+150
or +150/0). `probe_vehicle_views.gd` 12/12, `probe_fps_camera.gd` PASS, `AimDebugAuto` unchanged.

**One process note worth keeping.** A slice-and-replace of `updateSeatPosture` bounded by "the next
method's doc comment" would have silently deleted three unrelated methods between them — the ordering
had changed since the region was written. It was caught only because the edit asserted on text it
expected to find AFTERWARDS and refused to write. Bound a whole-method replacement by that method's
own closing brace, and assert the slice contains no other signature.

### W10 — ONE CLIP NAMING SCHEME, AND THE STALE-IMPORT TRAP (2026-09-09)

**The scheme is `<stance>_<action>[_<direction>][_<weapon>]-loop`, stance FIRST.** Sorting the clip
list then groups by stance, and a new stance is authored by copying a ring's names. Stance-agnostic
one-shots stay bare (`jump`, `air_jump`, `reload`, `roll`, `roll_rifle`, `weapon_switch_*`,
`falling`, `tpose`) — prefixing them would claim a stance they do not have. 26 clips were renamed to
reach it, the biggest group being upright locomotion, which had been the implicit default
(`idle`, `walk_forward`) while every other stance carried its prefix; the aim clips were reordered
from `aim_<weapon>_<stance>` to `<stance>_aim_<weapon>` so one rule covers both families. Also
folded in: `walk_backward` -> `upright_walk_back` (crouch_idle_deep already said `back`), `roll-rifle` ->
`roll_rifle` (hyphen is for `-loop` only, the same defect `crawl-idle` had), `T` -> `tpose`, and
`falling-loop-Godot_Chan_Stealth` — an import artefact duplicating `falling` — deleted.

**The blend, the scene and the checker are driven from ONE map.** The rename table lives in a JSON
the Blender script and the scene patcher both read, so they cannot spell a clip differently. The
safety net that makes this kind of pass survivable is `check_character_anim.py`'s **`tree_refs`**,
which ERRORS when the scene names a clip the export does not have — a missed reference cannot pass
silently.

**Placeholders, so a stance's ring exists before its art does.** The CRAWL ring played ONE clip at
four of its five points, so a crawl strafe was a crawl forward played sideways and there was nowhere
to author the difference: `crawl_back` / `crawl_left` / `crawl_right` are copies of the real forward
crawl, **wired**, so the ring looks exactly as it did and each direction is now an editable slot.
SWIM has no AnimationTree state at all (the stance ships `animationStanceKey = "Crawl"` and borrows
that ring), so its five locomotion clips and its aim pair are added as **orphans** — wiring a Swim
blendspace is the change that makes them reachable, and it is a scene edit that should land with the
authored poses. `check_character_anim.py` gained `crawl`'s four directions and a `swim` family, and
reads 60 clips / 6 rings / 0 errors.

**GODOT DOES NOT RESCAN IMPORTS ON A `--headless --script` RUN, AND A STALE IMPORT LOOKS LIKE A
BEHAVIOURAL BUG.** After the export the cached `.scn` was six hours older than the `.glb` and still
held the OLD 51 clip names, so the AnimationTree asked for `upright_idle` from a library that only
had `idle`, nothing resolved, and the skeleton fell back to its REST pose. What that produced was
not an error — it was a plausible-looking regression: `AimDebugAuto`'s crawl case reported the chest
at 44.3 deg instead of 129.8, and the eye probe reported all three stances at an identical 1.349.
**`check_character_anim.py` cannot catch it** — it reads the `.glb`, not Godot's cache — so it
happily said PASS. Run `godot --headless --path . --import` after every export;
`export_character.py` now prints that as step 1 of 2 with the reason.

**It also cost a measurement, which is the part worth remembering.** The cockpit mount was
"corrected" from 0.809 to 0.791 on a reading taken while the import was mid-staleness. Re-measured
on a fresh import and AVERAGED over a full second rather than sampled on one frame, the seated eye is
**0.808 (0.807..0.809)** — the original number — while CROUCH is 0.787 (0.767..0.802), i.e. it moves
±1.5 cm within its own loop, which is more than the difference being argued about. `probe_cockpit_eye
.gd` averages and prints the spread now, so the noise is visible instead of implied: **a single-frame
sample of a 57-frame clip is not a measurement.**

Gates after the pass: `check_character_anim` PASS (60 clips, 6 rings), `AimDebugAuto`
`yaw 12/12, pitch 3/3, strafe 10/10, ai 8/8, limit 6/6, clav 1/1`, `probe_vehicle_views` 12/12,
`probe_driveby_aim` 8/8, `probe_fps_camera` PASS.

### W11 — THE COCKPIT EYE MUST BE MEASURED IN THE SEAT, IN COMBAT (2026-09-09, user-reported)

"In vehicle FPS the camera is behind the character's neck." It was: measured against the driver's
own eye marker, **0.100 m behind and 0.062 m below** it, so the view sat inside the back of the neck
with the head hidden and nothing on screen to explain why.

The offset was right for the pose it was measured in and wrong for the pose that ships. The standing
probe drove `StanceTransition` directly with **combat off**; taking a seat sets `combat = true`,
which switches on the `NeckFront` blend AND the aim modifier — and both move `neck_01`, which is the
bone `MarkerFPSCamera` hangs off. So the seated-and-armed head is 6 cm higher and 10 cm further
forward than the seated-and-idle one. **A pose measured in the wrong state is not a measurement of
that pose**, and the tell was available all along: the same probe reported crouch_idle_deep's eye moving
±1.5 cm within its own loop, which should have prompted asking what else moves it.

`probe_vehicle_views.gd` measures the real thing now — the cockpit camera against the driver's eye
marker, decomposed in the car's frame — and asserts it (0.000 fwd / 0.000 up after the fix, 13/13).
That assertion is the durable part: the mount is authored per carrier, so every new carrier can get
this wrong in exactly the same way.

**The mount stays a fixed seat-relative Marker3D, deliberately.** Following the head bone would be
more faithful and is wrong here twice over: the carrier camera's ray feeds
`Character.applySeatedAimTarget`, which drives the aim modifier, which drives `neck_01` — closing the
very feedback loop that made first-person driving tangle (W8.3) — and a driving view wants to be
steady regardless.

### W12 — WEAPON GRIP ARCHETYPES, NOT PER-WEAPON ANIMATIONS (2026-09-09)

**The answer to "does every weapon need its own hold animation" is no, and the code already assumed
no** — it just shipped with two archetypes. `WeaponItem.weaponPoseIndex` is a blend position on three
`BlendSpace1D` nodes (`WeaponAim`, `WeaponHold`, `WeaponChangeAnimation`) and every weapon already
has its own `Marker<Weapon>` under `WeaponAttachment`. That IS the industry split: the *class* of
grip is animated, the *fit* of a particular gun is a socket transform.

Nine archetypes now, `blender/tools/weapon_archetypes.json` the table of record:

| idx | archetype | idx | archetype | idx | archetype |
|---|---|---|---|---|---|
| 0 | pistol | 3 | dual_pistol | 6 | shield |
| 1 | rifle | 4 | melee | 7 | shield_melee |
| 2 | launcher | 5 | fist | 8 | throwable |

**The index list is APPEND-ONLY.** It is stored in every weapon `.tscn`, so inserting in the middle
silently re-poses every weapon above the insertion — the same hazard the Blender addon's
`EnumProperty` ordinals have (`ROAD_POINT_GRAPH.md` §8i), and just as invisible in a diff.

21 placeholder clips (`upright_aim_<arch>`, `upright_idle_<arch>`, `weapon_switch_<arch>`), each a
copy of the pistol or rifle base, all **wired** — orphan count is unchanged at 23, so editing any of
them changes the game immediately. Five weapons moved off a pose that was merely the nearest
available: `ATL4` rifle→launcher, `MW1`/`MW2` (knife and axe) rifle→**melee**, `Fist` pistol→fist,
`T1` pistol→throwable. Only the melee pair changes visibly today, from a two-handed rifle hold to a
one-handed one, which is the less wrong of the two.

**Only the UPPER BODY needs authoring.** `WeaponBlend` is a *filtered* `Blend2` taking clavicles,
arms, hands and fingers from the aim branch, so an archetype pose's legs and pelvis are discarded —
which is also why the existing per-stance aim clips measured bit-identical to upright and changed
nothing.

**Fingers are not per weapon.** They are baked into the archetype's hold pose; the per-weapon
variation that matters is where the *support hand* sits, and that wants a socket on the weapon plus
a two-bone IK modifier for the left arm — the same shape as `ShoulderAimModifier`, and the change
that stops archetypes multiplying (one `rifle` pose then serves an SMG, a shotgun and a foregrip
variant). Not built yet; it is the natural next piece.

Gated by `tools/godot/probe_weapon_archetypes.gd`. **An index with no blend point raises nothing** —
the branch goes silent and the skeleton drifts to its rest pose, which by eye is indistinguishable
from a neutral authored pose. So the probe sweeps all nine indices and measures the RIGHT HAND
through a `BoneAttachment3D` (never `get_bone_global_pose`, which reads the pre-modifier pose), and
asserts **exactly two clusters** — every placeholder is a copy of pistol or rifle, so a third cluster
is an index that resolved to nothing. Measured: pistol and rifle 0.165 m apart, launcher with rifle,
the other six with pistol. Raise that expected count deliberately as real poses land.

### W13 — THE WEAPON OWNS HOW IT SITS, AND ITS OWN MOVING PARTS (2026-09-09, user-asked)

Two facts about a weapon had nowhere to live, so both had ended up somewhere worse.

**1. WHERE A WEAPON SITS IN THE HAND IS A FACT ABOUT THE WEAPON.**
`WeaponController.reparentWeapon` zeroed the item's local transform, so the socket carried the
entire placement — which forced a per-weapon marker onto the CHARACTER rig for every weapon in the
game (`MarkerAR4`, `MarkerATL4`, `MarkerSG1`, …). Three costs: adding a weapon meant editing the
character, the fit could not travel with the weapon to a second rig, and a weapon's own anatomy —
where its grip is — was written down nowhere. `WeaponItem.gripPoint` (a child `Marker3D`, default
name `GripPoint`) inverts it: `alignmentFor()` returns that marker's inverse transform, so the GRIP
lands on the socket instead of the ORIGIN. The character then needs one socket per **grip
archetype** (W12), not per weapon — the same split `weaponPoseIndex` already makes for the pose.

**Backward compatible by construction**: a weapon declaring no grip point gets identity, which IS
the old zeroing. `holsterPoint` is the same idea for the stow pose, because a rifle hangs on a back
socket by a different point than the one the hand grips.

**2. A WEAPON'S MOVING PARTS ARE ITS OWN ANIMATION.** A shotgun pump, a bolt, a revolver cylinder,
a folding stock: `WeaponItem.weaponAnimatorPath` + `fireAnimation` / `reloadAnimation` play a clip on
an `AnimationPlayer` inside the weapon's own scene. Not the character's skeleton — that would tie
every weapon to one rig and one clip set, and the part must keep moving while the character is doing
something else. **What the two share is the EVENT, not the animation**, and `WeaponController` is
already the one owner of that event for both peers, so the calls sit on all four of its existing
sites: `onWeaponFire` / `onWeaponReload` (authority, after every gate, so a suppressed shot moves
nothing) and `playRemoteFireCue` / `playRemoteReloadCue` (puppet, so a remote peer sees the pump
cycle). A magazine that must follow the off hand is the case this does NOT cover; that wants the
support-hand IK below.

**The launcher is the worked example, and it is half art.** It rides on the SHOULDER, so its tube
sits high and back relative to the hand compared to a rifle — that half is now a translation of
`ATL4`'s `GripPoint` (shipped at `(0, -0.09, 0.10)`, a starting point derived from the 0.08 m tube
radius; drag it, no character edit needed). The ARM pose is genuinely authored art and its slot is
`weaponPoseIndex` 2 (`upright_aim_launcher`, currently a copy of the rifle pose).

Gated by `tools/godot/probe_weapon_sockets.gd`. **The failure mode is SILENCE** — a grip marker that
is renamed, missing, or left blank makes `alignmentFor` return identity, the weapon lands exactly
where it always did, and nothing says the feature did not run. So both halves are asserted: a weapon
WITH a grip point moves its grip onto the socket (0.0000 m) while its origin does NOT sit there
(0.135 m away, or the alignment did nothing), and one WITHOUT still puts its origin there
(0.0000 m). The socket is deliberately rotated and off-axis: the alignment is applied in SOCKET
space, so an axis-aligned socket would let a wrong-but-plausible implementation pass.

**One probe trap, and it cost a false failure first — HISTORIC, closed by W15:** a weapon *was* a
`RigidBody3D`, so the PHYSICS SERVER owned its transform — set it and gravity had moved it again by
the next frame. Both cases read 5.4 mm off, which looks exactly like a small alignment error rather
than like free fall, and the probe had to `set("freeze", true)` the way the game froze a carried
weapon in `Pickup.pause()`. That reading is what named the real defect: a held weapon should not
have been a body at all. It is a `Node3D` now and the probe asserts **0.000000 m** of drift over 60
physics frames instead of working around it.

**Still to build: support-hand IK.** A socket on the weapon (`SupportPoint`) plus a two-bone IK
modifier for the left arm — the same shape as `ShoulderAimModifier`. It is what stops archetypes
multiplying, since one `rifle` pose then serves an SMG, a shotgun and a foregrip variant, and it is
also the answer for a reload where the off hand must follow a magazine.

### W14 — SUPPORT-HAND IK, AND WHY A HELD WEAPON SHOULD NOT BE A RIGID BODY (2026-09-09)

**`character.SupportHandIKModifier` is what stops grip archetypes multiplying.** An archetype (W12)
animates the CLASS of hold; what it cannot express is that an SMG's foregrip is 12 cm from the
trigger and a long rifle's is 30, because that is a fact about the WEAPON. Two-bone IK on
`upperarm_l -> lowerarm_l -> hand_l` puts the off hand on the held weapon's `SupportPoint` marker, so
one `rifle` pose serves an SMG, a shotgun, a carbine and a foregrip variant and a new weapon costs
one marker and no animation. Law of cosines in SKELETON space, reach clamped to the arm's own length
(a target past `a+b` straightens the arm instead of stretching it), and **the bend plane comes from
the CURRENT pose** rather than a pole vector — the clip already knows where the elbow belongs, and a
pole would overrule it. It must sit AFTER `ShoulderAimModifier` in the skeleton's children: the aim
swings the whole shoulder, and the hand goes where the weapon ENDS UP.

**Self-managed on purpose** — it asks `WeaponController.getCurrentWeaponItem()` each frame, so no
equip path pushes anything and none of the four `onWeaponEquip` sites can forget it. A weapon with no
`SupportPoint` leaves the arm exactly as the clip authored it, which is the right answer for a pistol
and needs no flag.

**`getOwner()` IS NOT THE CHARACTER, and that made it silently inert.** The modifier lives inside the
`CharacterVisuals` sub-scene, so its owner is that sub-scene's root — while `WeaponController` is a
child of the CHARACTER, one level further out. `getOwner().getNodeOrNull("WeaponController")`
therefore returns null forever, `resolveTarget` returns null, and the modifier does nothing at all
with a scene that looks correctly wired. Measured: the arm moved **0.006 m**. It walks up the parent
chain now. Every existing wiring of this kind goes through `Character.wireFromMeshConfig` for exactly
this reason — reach for that idiom, or walk up, but never `getOwner()` from inside the visuals.

Gated by `tools/godot/probe_support_hand_ik.gd`: hand **0.209 m -> 0.013 m** from the support point,
having moved **0.201 m**. Both halves are asserted, because *every* failure here is silent (no
controller, no held weapon, no marker, a bad bone name, `weight = 0` — all return early leaving the
clip's arm), so "close to the target" alone would pass on a clip that happened to be near it. `hand_l`
is read through a `BoneAttachment3D`: a modifier writes into the FINAL pose only, so
`get_bone_global_pose` would report the pre-IK arm and a working solve would measure as inert.

### W15 — A WEAPON HAS TWO STATES, AND ONLY ONE OF THEM IS A PHYSICS BODY (2026-09-10)

`WeaponItem extends Pickup extends RigidBody3D` made a weapon a physics body **even in the hand**,
and every cost of that was already in the codebase as its own workaround rather than as one cause:
reparenting a `CollisionObject3D` is **forbidden in a physics callback**, so every equip was queued
and drained in `_process`; a frozen body that is moved leaves **Jolt's body position stale** and the
item later clips through the ground, so a weapon with no holster socket was left lying in the world
scene (hidden) instead of stowed; `Pickup.pause()` had to freeze a body at all; and two probes had to
set `freeze = true` before they could measure a transform, because the physics server owned it and
gravity moved the weapon **5.4 mm** between the set and the read — which reads exactly like a small
alignment error rather than like free fall.

**The split is now real.** `item.Pickup` is a **`Node3D`** — meshes, markers, logic, identity,
replication — and `item.PickupBody` is the **`RigidBody3D`**: shape, gravity, impulses. In the world
the item rides INSIDE the body as its only `Pickup` child at identity; held, it hangs off a bone
socket with **no physics anywhere in its ancestry**. `Pickup.placeInWorld` builds the body,
`Pickup.detachWorldBody` takes it away, and `onPickedUp`/`onReturnedToWorld` are the two halves of
the transition (both `@Register`ed, so a scene or a probe can state it).

Four rules came out of it, three of them measured:

- **A shape only registers with the `CollisionObject3D` it is a DIRECT child of**, so the item's
  authored `CollisionShape3D` children are **lent** to the body while it exists and taken back when
  it goes (`lendShapesTo`/`reclaimShapesFrom`). The weapon scene stays the one place a weapon's shape
  is authored — the alternative, a shape resource copied onto a generic wrapper, is a second owner.
- **A body frees ITSELF once no item is left inside it** (`PickupBody.freeIfEmpty`, off
  `child_exiting_tree`, deferred). Several paths free an item outright — a fully-absorbed throwable
  stack, a reconcile discard — and none of them can be expected to know about a parent they did not
  create. Without it those leave an empty rigid body standing in the world.
- **An item on its way into a slot is not lying in the world.** `WeaponController.requestEquip`
  calls `Pickup.claimForInventory()` (the flag only — detaching there would reparent a
  `CollisionShape3D` out of a body inside a `body_entered` signal, which the physics server refuses).
  Measured on DebugWorld: **13 bodies built per boot → 10**, the three lost being weapons spawned
  straight into an AI's inventory by `ZoneManager`, wrapped on the deferred frame and freed by the
  equip one frame later. The pickup path already had this — `WeaponItem.onCharacterEntered` sets the
  same flag before it defers, to block a re-trigger.
- **A scene-placed item wraps ITSELF; one authored inside a character does not.** The test is
  `Pickup.bornHeld()` — a `WeaponController` somewhere up the parent chain — which is the fact that
  actually decides it. Owner-is-current-scene and scene-root tests were both considered and are wrong
  for a runtime-instantiated weapon (no owner) and for a weapon placed in a sub-scene. The wrap is
  deferred out of `_ready` because `pickupId` must be read from the **authored** path: wrapping first
  changes it, and every peer has to derive the same string.

**The one regression it introduced, and the rule behind it: a body STANDS IN for its item, and the
item is now the collider's CHILD.** `ImpactManager.resolveHitContext` walks **up** the parent chain
from whatever the weapon's ray returned — which for a world item is the `PickupBody`, with the item
hanging below it. So the walk sailed straight past `ThrowableItem`'s `Detonatable` and **shooting a
dropped grenade did nothing at all**, silently, because a bullet that finds no `Detonatable` just
leaves a decal. `resolveHitContext` redirects to `PickupBody.carriedItem()` before it starts, so
everything above the body is still above the item. This is a live path, not a dead one: the
`Character.tscn` AimRay's mask is **29**, which includes the PICKUP layer — `CollisionLayers`' own
comment said 25 and is corrected. The same walk is where a `HittableBody` surface type would live,
so the redirect is not grenade-specific.

**What this buys, beyond the workarounds it deletes:** a held weapon cannot be moved by anything,
`returnWeaponToWorld` lost its case analysis entirely (where the weapon currently hangs no longer
matters — it has no body to reparent, and building one is what puts it back), and a socketless
throwable is now **stowed on the character** instead of abandoned at the spot it was collected.
`T1.tscn`'s `continuous_cd` became `world_body_continuous_cd` on the ITEM — a fact about the item,
applied to each body built for it — since a thin, fast grenade can tunnel and a dropped rifle need
not pay for it.

**Measured equivalence, which is the point of a refactor:** booting `World.tscn`, all ten
scene-placed weapons come to rest at **byte-identical y** before and after (4.66–4.90, and MW1 at
−59.05 both ways). Leak signature at headless exit is identical too (3 ObjectDB instances, the
documented `Rifle_fire.wav` audio-at-quit case).

**MW1 fell to −59.05 both before and after, and the cause written here first was WRONG** — it was
recorded as "authored over a gap in the ground" on the strength of `world_body_continuous_cd = true`
changing nothing. Measured afterwards (W16): a ray at MW1's own XZ finds ground at **y = 4.61**,
exactly where its neighbours rest. The real cause was its **collider**: a 0.05 × 0.25 × **0.04** m
box, thinner than any other pickup in the scene (MW2 0.06, PI52 0.064 — both rest), which a physics
engine will not hold on a heightfield. At 0.10 × 0.25 × 0.10 it rests at **4.64** with the rest. Its
`PickupArea` was the same blade-sized box, so it was also nearly uncollectable; it has a 0.5 m
detection volume now, the split `T1.tscn` already had (small body, generous area). **A pickup's
collider is not its silhouette** — it is what has to rest on ground and be walked into.

Gated by **`tools/godot/probe_weapon_world_body.gd`** (18/18), which drives a real `Player` through a
real auto-pickup and drop rather than calling the API in a bare tree: the item rides a falling body
in the world, has no physics body between it and the character when held, gets a rebuilt-and-thrown
body on `drop_current_weapon`, and strands nothing when freed. **Every failure here is silent** — a
body never built leaves a weapon hanging in mid-air, a body never removed leaves a rigid body riding
a hand, and neither says so — which is why both directions are asserted.
`probe_weapon_sockets.gd` lost its `freeze` workaround and gained the assertion that replaces it: a
socketed weapon drifts **0.000000 m over 60 physics frames**.

**The hit-resolution case is asserted structurally, and that is a deliberate limit worth stating.**
Driving a real bullet into a dropped grenade in a bare probe tree means fighting two things that are
not under test — the camera boom's resting orientation (with no input driving it the aim ray sits at
identity, so "1 m in front of the player" is over a metre off the ray) and the melee cone's own
range and surface-normal filters. **It is NOT a teleport problem, though it looked like one and was
nearly written down as one:** measured separately, assigning `global_position` to a settled,
sleeping pickup body moves it and the collider follows (`sleeping` clears itself, and an explicit
wake changes nothing). The body in the probe had just been thrown at 4.33 m/s and simply flew off
again. A space query is worse than useless here: every segment through a
grenade resting at a character's feet also passes through that character's ragdoll bones, which are
on the HITBOX layer the same mask includes — it returned `Physical Bone head_2`, then the floor. So
what is asserted is the redirect's premise (the shape is on the body, so the body is what a ray
returns), the hazard (walking up from the body never reaches the item), and the hand-over
(`carried_item()` is the item). The middle one is the load-bearing assertion: it fails if anyone
"simplifies" the redirect away.

**Still open: the equip deferral is now a choice, not a constraint.** `pendingEquips` no longer
exists because reparenting a body in a physics callback is illegal; it exists because the same-frame
merge and displacement guards in `equipWeapon` are written against an equip that resolves out of the
`body_entered` signal that asked for it. Collapsing it would mean re-deriving those guards.

**Still to build: support-hand IK is done (W14); what is not is a weapon's own moving parts having a
second consumer.** `WeaponItem.weaponAnimatorPath` covers a pump or a bolt; a magazine that must
follow the off hand during a reload is the case it does not, and that wants the IK target to switch
source mid-clip.

### W16 — MELEE IS A SWEPT REACH FROM THE CHEST, AND AN ATTACK IS A DATA TABLE (2026-09-11)

**The target feel is Left 4 Dead, not Dark Souls, and that decides the architecture.** L4D's melee
is reliable because of a generous hull resolved from the view at a fixed early moment with total
feedback — the animation is decorative and decides nothing. GTA's is less reliable *because* of its
extra machinery: target snapping picks someone you did not mean, root-motion commitment delays
contact, and a staggering NPC leaves "did that connect?" ambiguous. So the Souls/DMC toolkit —
animation-notify hit windows, target selection, motion warping — is **deliberately not built**; at
this degree it would subtract feel, not add it.

**What was there:** five rays cast from the **camera** (`weaponController.getAimRay()`), first hit
only, re-cast every frame for the whole 0.3 s swing. Both of its patches were the camera origin
showing through — a range measured from the torso rather than from the ray, and a filter rejecting
upward normals so a downward-tilted camera did not "hit" the floor. It is the melee half of the
defect the firearm's two-stage resolution closed.

**The two legs are now ONE owner, shared.** `resolveSightPoint` and `trace` (with `TraceHit`) moved
from `FirearmItem` up to `WeaponItem` — a pure move. Stage 1, the camera says what is aimed at;
stage 2, the attack is resolved **from the character**: a firearm from its `Muzzle`, a melee weapon
from its **chest** (`spine_03`'s ragdoll bone, so a crouched swing starts at a crouched chest). The
answer to "is the hitscan always from the character, whatever the view" is **yes, by construction,
and in FPS too** — the FPS camera is a filtered neck bone, not the chest, so even there the two are
not the same point.

**Cleave, and each target once.** The sweep is a capsule spanning `[chest, chest + dir*range]`,
queried with `intersect_shape` (a static overlap of the WHOLE reach volume, not a `ShapeCast3D`,
which reports only what is touching at its FIRST contact and so cannot cleave). Results are grouped
by **`ImpactManager.resolveTarget`** — the same walk that applies the damage — so ten ragdoll bones
of one character are ONE target, and a per-swing hit set means a multi-frame window cannot hit twice.
Each target must then trace clear from the chest, so cover blocks a swing exactly as it blocks a
bullet; a blocked target stays live and may connect later in the window.

**One direction rule, judged along the VIEW.** The swing runs chest → sight point, unless that point
is not ahead of the chest along the view — which is the camera ray stopping on something BETWEEN the
camera and the character, i.e. behind them in third person — in which case it runs along the view
itself. Judged against the view rather than the body's facing, so it needs no knowledge of how far
the mesh has turned toward the aim yet.

**An attack is DATA: `MeleeAttackStep`** (`animation`, `damage`, `range`, `radius`, `windup`,
`active`, `recovery`, `hitstop`, `cameraKick`), and a weapon declares an ordered list. The default
chain walks it while swings keep coming inside `comboResetSeconds` and starts over after a pause —
so the axe is `[light, heavy]`, "light first, big second", and the fist is `[jab, cross]`. **A
subclass changes only how a step is CHOSEN:** `KnifeItem` is now just tap → step 0, hold → the heavy
index, and its parallel heavy damage/range/cone fields and second cone table are gone. Adding a
melee weapon is a scene with a step table; adding a moveset is rows.

**The code owns the timing and the clip is time-warped to fit it** (`AnimationController
.playMeleeAttack` scales the clip so its whole length spans `windup + active + recovery`). That is
L4D's split, and it is what lets feel be tuned without re-authoring and a placeholder of the wrong
length still play correctly. When real swing clips land, set the step to the clip's own contact
frames and the scale comes out at 1.

**The attack one-shot is selected BY CLIP NAME, not by weapon index.** `Attack` (a OneShot with
`WeaponChange`'s upper-body filter) ← `AttackScale` (TimeScale) ← `AttackClip`, an
`AnimationNodeTransition` whose inputs are named after their clips. The existing one-shots are fed by
a `BlendSpace1D` on `weaponPoseIndex`; keying attacks the same way would have meant a second index
table to hold in step with `weapon_archetypes.json`, and W12's rule that an index with no blend point
is **silent**. A step names its clip, so a new weapon or step is one Transition input and one action.

**Placeholder clips exist per melee weapon** (user-asked), minted through `character_anim_naming
.json`'s `placeholders` map — the same one-owner mechanism W10 used: `attack_stab_mw1`,
`attack_slash_mw1`, `attack_swing_mw2`, `attack_chop_mw2`, `attack_jab_fist`,
`attack_cross_fist`, each a copy of that archetype's `weapon_switch_*`. Per WEAPON rather than per
grip archetype because a knife's stab and an axe's chop are different art even though the grip is
one; two weapons may still point at one clip, since the step names it. Replacing any of them is a
pose edit on an existing action — no rename, no scene change. Measured: 81 → **87 clips**, orphans
23 → 29 (unwired) → **23** once the tree was wired, `check_character_anim` PASS.

**Feel, which is mostly not detection.** Hitstop freezes the attack one-shot on the pose that
connected and holds the swing's own clock with it — **local and cosmetic, never `Engine.time_scale`**,
which in multiplayer would stall every peer for one player's hit. Plus a camera kick on contact, and
a per-weapon **input buffer** (`WeaponController`, opt-in via `WeaponItem.fireBufferSeconds`, 0 for
guns because a buffered shot is a shot the player did not ask for): a tap landing during recovery
fires the moment the weapon frees up, through the ordinary `onWeaponFire` so every gate, cue and
`fireSeq` bump still runs. Draining checks every gate WITHOUT firing (`readyToFire`), or the drain
would re-buffer itself and extend the window forever.

Gated by **`tools/godot/probe_melee.gd`** (28/28), which presses the real `fire` action through
`PlayerController` and measures damage through each target's own `Health.hit`. Cases that can each
fail for one reason: reach (3.5 m out is on the camera's line and must take nothing), **behind** (a
wall between camera and character, on a layer the spring arm ignores — a camera-origin swing strikes
it and whiffs), cover, cleave, hit-once, chain order and restart, buffer, hitstop, FPS parity, the
axe at exactly **120/60** and the knife at exactly **100/40**.

**An AI is the other half of the path and shares none of the player's rig** — no `PlayerController`,
no FPS mode, an `AICameraController` instead of a boom — so the last case arms one by walking it over
a pickup and fires it the way `AttackState` does: **one frame** of `fire` (which is also why an AI
knife always taps and never charges). It lands 60 × 0.75 = **45.0**. Getting there needed the thing
`AttackState` does on that same frame and a probe would not think to: **`snapAimRay(target)`**. A
frozen AI's camera rig had not converged on its own facing and rested 90° off, pointing −X, so the
swing went nowhere — the aim ray is aimed AT the victim before the swing, not merely resting.

Three probe lessons, each of which cost a wrong reading first:
- **A target that walks is not a target.** With no `PlayerRegistry` autoload these AI run their full
  FSM: the far target strolled into reach and the near one turned, so three jabs read
  `10x0.75, 14x0.75, 10x4.0` — the last a **headshot** — and the chain looked broken when it was not.
- **Freezing the body is not freezing the POSE.** The AnimationTree is its own node and kept playing,
  so the bone under the capsule still drifted (an arm, then a torso). Both must stand still.
- **The bone multiplier is inside the number `hit` reports**, so every chain assertion is a RATIO of
  two swings into the same target from the same place. It is exact only while both steps meet the
  same bone — which is why the fist's jab and cross now share a reach (they come off the same
  shoulder; the cross differs in damage and recovery), and why the axe and knife ratios come out at
  exactly 2.00 and 2.50.

**Known limits, on purpose.** A puppet replays the chain from its OWN position (`fireSeq` carries no
step), so a knife's tap/hold is not knowable remotely and replays as the light swing; and the knife
bumps `fireSeq` on the PRESS while its swing starts on RELEASE, so a remote knife swing leads by the
charge time — both pre-existing shapes of "fire is replicated as state". The next step up, if a
weapon ever needs blade-accurate contact, is socket sweeps between frames driven by animation notify
tracks — additive, and the trace code does not change.

### W17 — A CLIP NAME SAYS THE MOTION; THE TABLE SAYS THE ROLE (2026-09-11, user-asked)

`attack_light_b_fist` was the name that prompted this, and it is wrong in a way worth naming: `light`
and `b` are the step's JOB in the chain, which `MeleeAttackStep` already owns (its damage, its
recovery, its place in the order). Putting that in the clip too gives the fact two owners, and the
second one cannot be edited — re-ordering a chain would rename art. **The clip says what the body
DOES; the table says what the swing is FOR.** So: `attack_jab_fist`, `attack_cross_fist`,
`attack_stab_mw1`, `attack_slash_mw1` (the two `KnifeItem`'s own doc has always called them),
`attack_swing_mw2`, `attack_chop_mw2`. Re-rolling the axe's chain to heavy-first is now a data edit
with no clip touched.

Three more renames, each a name that described something the clip is not:

- **`upright_idle_<arch>` → `upright_hold_<arch>`** (9). It is the weapon HOLD pose fed to the
  filtered `WeaponBlend`, and it sat one underscore away from `upright_idle`, the locomotion idle of
  the upright ring — two unrelated things reading as one family.
- **`on_air_<weapon>` → `air_aim_<weapon>`**. These are aim poses; under their own name they join the
  `<stance>_aim_<weapon>` family they belong to and sort with it.
- **`crawl_high` → `crawl_idle_high`, `crouch` → `crouch_idle_deep`** — orphan pose variants whose
  names read like a stance rather than a variant of one.

**What was deliberately NOT flattened:** `<stance>_aim_<arch>` keeps its stance prefix even though
the aim branch is archetype-only today, because the family is genuinely two-dimensional — its
`crouch_`/`crawl_`/`drive_`/`swim_` siblings already exist as orphans and a stance-driven branch
inside `WeaponAim` is the change that reaches them (W7, W10). Renaming them to `<arch>_aim` would
read better today and fight the direction of travel. `weapon_switch_<arch>` stays for the same reason
it always had: a stance-agnostic one-shot stays bare.

**The safety net is what makes a 19-clip rename survivable**, and it is the same one W10 relied on:
one map (`character_anim_naming.json`) drives the `.blend`, and `check_character_anim.py`'s
**`tree_refs`** ERRORS when the AnimationTree names a clip the export does not have — so a missed
reference cannot pass quietly. Two traps specific to renaming clips that are also PLACEHOLDERS:
the placeholder map is keyed by NAME, so its keys must be re-keyed in the same pass or the old names
are minted straight back on the next run; and a historical `renames` entry whose TARGET is being
renamed must be re-pointed at the final name, or the map stops being old→current for a fresh import.
Measured after: 87 clips, `tree_refs` 64, orphans 23, 0 errors — every number unchanged but the names.

### W18 — A SECOND BODY IS A SECOND `CharacterVisuals`, AND CLIP NAMES ARE THE CONTRACT (2026-09-11)

**What actually differs between a male and a female character is the LOWER BODY, and the tree already
says so.** `WeaponBlend` is a *filtered* `Blend2` taking only clavicles, arms, hands and fingers from
the aim branch, and the `Attack`, `WeaponChange` and `Reload` one-shots carry that same upper-body
filter. So every weapon-owned clip — 9 aim poses, 9 hold poses, 9 switch one-shots, 6 attacks — is
**upper body only** and is dictated by the WEAPON, not by the body holding it. They are shared. What
reads as male/female is posture and gait: the locomotion rings, **~29 clips** (upright 9, crouch 9,
crawl 5, swim 5, drive 1). A second body costs those, **not** 29 + 33 — there is no per-weapon
full-body set, and the combinatorial explosion people fear (archetypes × genders × stances) does not
exist here. It is the line the industry draws too: GTA V and Cyberpunk author gendered idle/walk/run
and share the weapon poses; Elden Ring shares combat movesets outright because the weapon defines
them.

**The swap unit already existed:** `Character.characterVisuals` is one exported `PackedScene`, and
the `MeshConfig` embedded in that scene rewires every dependent path (mesh root, sockets, modifiers,
stance colliders, bone multipliers). So the scaffold is
`CharacterVisuals_GodotChanF.tscn` → `assets/merged_animation_f.tscn` → `assets/merged_animation_f.glb`,
built from `assets/merged_animation_f.blend`.

**Identical clip NAMES are what make it free.** All the Java addresses clips by name
(`playMeleeAttack("attack_chop_mw2")`, `parameters/<Stance>MovementBlend/blend_position`), so a second
body with the same names needs **no code, no rewiring and no second probe suite** — which is exactly
why W17's naming pass was worth doing first. Divergent proportions do not force duplicated poses
either: `SupportHandIKModifier` solves the off hand to the weapon's own `SupportPoint` (W14) and
`GripPoint` carries the weapon's fit (W13), so those absorb a different skeleton instead of
multiplying art.

Two tools stopped being single-body, and both were one line from silently breaking a second:
`export_character.py`'s output is **derived from the .blend being exported** (it was hardcoded to
`merged_animation.glb`, so building a second body would have overwritten the first), and
`check_character_anim.py` takes an optional second argument for the visuals scene, so the same gate
can be pointed at either body. The variant passes it identically: **87 clips, 6 rings, 0 errors**,
the same 23 orphans.

**The placeholder is a byte-identical copy on purpose**, and LFS makes that nearly free — the copy
shares the original's object id until it is actually edited, so the repo pays only when there is real
content to pay for. Author the ~29 locomotion clips one at a time; everything else already works.

Gated by **`tools/godot/probe_character_variant.gd`** (8/8): the swap took (each body loads its own
export), the **clip-name sets are identical both ways** (87 = 87, nothing missing, nothing extra —
the contract itself, asserted because the failure is silent: a renamed clip does not error, the
branch goes quiet and the skeleton drifts to REST, which by eye looks like a neutral authored pose),
the melee path runs unchanged on the second body (its fist lands and plays `attack_jab_fist`), and
the **eye offset matches the base body to 0.0003 m**. That last one is the live tripwire: the variant
is a copy today, so it must measure identically; the day its locomotion is genuinely authored, that
case failing is the gate telling you to re-measure the FPS and cockpit mounts (W11 — a pose measured
in the wrong state is not a measurement of that pose).

**One probe lesson worth keeping:** measured one after the other, two byte-identical bodies read
**5 mm apart**. Each 60-frame window caught the shared idle loop at a different phase, and the neck
the eye mount rides was simply somewhere else. Averaging is not enough — **two bodies must be
sampled on the SAME frames**, or a looping clip's phase becomes the difference between them.

### W19 — A WEAPON IS ITS REAL SIZE, AND A CONFORMING MODEL NEEDS NO TRANSFORM (2026-09-11, user-asked)

**The standard is in `blender/WEAPON_AUTHORING.md`; the table is `blender/tools/weapon_models.json`;
the build is `blender/tools/build_weapon.py`; the gate is `tools/godot/probe_weapon_scale.gd`.**
Four rules: 1 unit = 1 **metre** at real-world length, **−Z** is the muzzle/blade direction, **+Y**
up, and the model **origin is the grip**. The last one is what makes `WeaponItem.alignmentFor`
identity, so the character's socket carries no per-weapon fudge — and together they mean **a
conforming model needs no transform on its scene instance at all**, which is the rule the gate
actually asserts.

**The origin rule was STATED here and never MEASURED, and it was false for every model — W20.**

**What was there:** every source mesh was authored 10× too large and yawed 90°, and every weapon
scene undid it by hand with `scale 0.1` and a rotated basis — measured, all nine identically. Two
costs, and the second is the one that bit: the correction lived in nine scenes instead of one, and
because each `0.1` was a **guess rather than a conversion**, nothing agreed with life.

| weapon | was | real | ratio |
|---|---|---|---|
| AR4 / AR212 | 0.549 / 0.517 m | 0.90 | 61% / 57% |
| SG1 | 0.521 | 1.00 | 52% |
| PI52 | 0.182 | 0.22 | 83% |
| MW1 (bayonet) | 0.117 | 0.30 | **39%** |
| T1 (grenade) | 0.300 | 0.09 | **333%** |

A 0.55 m "assault rifle" on a 1.49 m character reads as an SMG and a 0.30 m grenade is a melon. None
of those sizes was chosen; they fell out of a per-weapon fudge factor. All eight now measure their
declared length to **0.0%**.

**On the arcade question, which is a real one here:** the world is deliberately not 1:1 — road lanes
are 4.5 m rather than the book's 3.25 (`seed_district_roads.LANE_WIDTH`) because a 2.0 m car in a
3.25 m lane drives like a lorry in a tunnel. That is a **vehicle-scale** decision and it does not
reach hand props: a weapon is measured against the hand holding it, and the hand is metric. So
weapons are life-size and the two scales do not have to be reconciled.

**The correction is GONE, not relocated — and that took a second pass (user-asked).** The first
version computed it at build time: read the raw art, apply `scale 0.1 x k`, a yaw and a grip offset,
every run. That beats nine scenes each carrying the fudge, but it keeps the same defect one level up:
**the asset is still wrong and something has to keep fixing it**, the real size lives in a JSON field
rather than in the model, and an artist opening the source still sees a 10x weapon. So the model is
simply RIGHT now. `build_weapon.py --init` bakes the convention undo, the scale-to-life and the grip
offset into `assets/weapons/<id>.blend` **once** and then APPLIES every transform, so each object
sits at location 0 / rotation 0 / **scale 1** with metre-correct mesh data (PI52 even had a
non-uniform 0.889 object scale, now baked out). The ordinary build opens that `.blend`, verifies, and
exports applying **nothing**; the raw art in `assets/` is never modified and never ships. A new
weapon is simply modelled at its real size — there is no scale factor to work out because there is
no scale factor anywhere. Markers and colliders scaled with their models. The primitives (ATL4's
cylinder, MW2's box, T1's box) took the same metre rule directly, and ATL4 shows why a uniform scale
is not always the answer: its tube was authored 0.16 m across where an AT4 is 0.084, so length and
bore had to be set independently rather than multiplied by one factor.

**Two collider rules came out of it**, both from defects already paid for:
- **No axis thinner than 0.05 m.** MW1 shipped a 0.04 m box and fell to y = −59 in `World.tscn`,
  which was misread as a hole in the ground for a whole session (W15/W16). **A pickup's collider is
  not its silhouette** — it is what has to rest on ground, so it may be fatter than the art.
- **A `PickupArea` is a DETECTION volume, not the body shape.** Several weapons shared one box for
  both, which made them nearly uncollectable; MW1 and MW2 now follow `T1.tscn`'s split — small body,
  roomy area.

**`length_m` flipped from an input to an ASSERTION**, which is the whole point of the second pass:
the build measures the `.blend` and refuses to export one that has drifted, naming the rule that
broke. Verified by scuffing a model on purpose — an un-applied `scale 1.5` on AR4 is refused with
*"still carries a transform … Apply it (Object ▸ Apply ▸ All Transforms) — the model IS the weapon"*
and exit 1. A guard that has never been seen to fire is not a guard.

Gated by **`probe_weapon_scale.gd`** (37/37), reading the same JSON the build reads so the gate and
the build cannot disagree about what a weapon is supposed to be: declared length to within 2%, **the
instance transform is identity**, the muzzle is on −Z, and the two collider rules. One trap it hit
while being written and that will catch the next person: a weapon added to a bare scene **wraps
itself in a `PickupBody`** (W15) and LENDS it the authored `CollisionShape3D` children, so the item's
own shapes vanish and the collider checks silently measure nothing at all — call `on_picked_up()`
first, the same thing `WeaponController` does before reparenting onto a socket.

### W20 — THE ORIGIN IS THE GRIP, MEASURED; ONE SOCKET PER ARCHETYPE; A LIBRARY FILE (2026-09-13, user-asked)

Prompted by "the shotgun pokes over the shoulder — is the character too short or the weapon too
large?" **Neither.** GodotChan measures **1.49 m** to the crown (the docs had said ~1.7 m — never
measured; corrected everywhere), SG1 is a real 0.98 m, and a 1.0 m gun on a 1.49 m body is simply the
proportion of a 1.17 m gun on a 1.75 m man. What was wrong was **where the gun sat in the hand**, and
it was wrong in a way W19 had written down as solved.

**W19 said "the origin is the grip" and nothing checked it.** Side renders with the origin marked
showed every raw model's origin wherever a centring offset had left it: SG1's on the RECEIVER, ahead
of the trigger (0.48 m from the butt, against ~0.27 for a hand on the stock wrist); AR4's above the
magazine; the bayonet's on the BLADE. The stocks themselves were correctly proportioned (SG1
trigger-to-butt 0.36 m = a Remington 870's 14 in length of pull). **The per-weapon markers on the
character were compensating**, weapon by weapon — measured in hand space, the grips landed 4 cm (AR4),
7 cm (AR212), 10 cm (MW1) and **15 cm (SG1)** from the palm. W19's `grip_offset` had copied each scene
instance's old translation, which was a centring offset, not a grip.

**Fixed in the models, then asserted.** Each `.blend`'s origin was moved to the centre of the firing
hand's fist on the grip (placed on zoomed renders with a 1 cm grid), and three lengths that W19 had
guessed were taken from a named reference instead (`reference` in `weapon_models.json`): AR4 0.90 ->
**0.88** (AKMS), AR212 0.90 -> **0.84** (M4), SG1 1.00 -> **0.98** (870, 18.5 in). `build_weapon.py`
now refuses a model whose origin has moved: `grip_to_rear_m` (origin to rearmost point, 1 cm) is
asserted beside `length_m`, and each weapon's meshes must sit in a collection named `<id>`. The
long guns now read 0.281 / 0.259 / 0.272 m grip-to-butt — consistent, which is the point. Also
found and fixed on the way: `Muzzle` markers floated **8-16 cm past the barrel** (now the measured
bore tip), and only AR4 had a `SupportPoint` (AR212 and SG1 now have measured ones on the handguard
and pump). Scene colliders are the mesh AABB (thin axes clamped to 0.08 m), pickup areas ≥ 0.5 m.

**One socket per GRIP ARCHETYPE** — what W13 said the character should need and never got:
`MarkerAR4/AR212/SG1/PI52/ATL4/Fist` became `SocketRifle`, `SocketPistol`, `SocketLauncher`,
`SocketMelee`, `SocketFist` (both body variants, and `MeshConfig.socketPaths`). The rifle and pistol
sockets are **the grip positions AR4 and PI52 already had** (`MarkerX * T(grip)`), because those two
were the weapons the aim stand and the support-hand probe had been tuned against — so they look
exactly as before, and every other weapon moves ONTO the tuned fit. The finger bones put the palm's
fist centre about 4 cm from the socket, within the resolution of the estimate. Measured after, in
the aim pose: all three long guns grip-to-palm **0.042 m**, stock end **0.08-0.10 m behind the
shoulder joint** (SG1 was 0.24). That remaining 10 cm is the ARM POSE, not the weapon: the rifle aim
clip holds the hand only 0.17 m in front of the shoulder, where a shouldered stock needs ~0.26-0.28.
That is authored animation, and the next step.

**No shipped weapon has a `GripPoint` now** (ATL4's primitive was re-origined; MW2's axe box now
extends down −Z from its grip like the knife). The mechanism stays as the escape hatch for an asset
whose origin cannot be moved; `probe_weapon_sockets.gd` asserts every weapon in the table conforms
AND that the hatch still lands a runtime-added marker on the socket. Holstered long guns hang by the
grip now, so they sit differently on the back sockets than before — `holsterPoint` exists if that
needs tuning.

**`assets/weapons/WeaponLibrary.blend` is the "zoo"** (`blender/tools/build_weapon_library.py`):
every weapon LINKED from its own `.blend` (one owner — an edit there shows up on reload), all grips
on one vertical line, a red bar under each at the reference's real length with a blue tick where
the real trigger is, the primitives as boxes, and the character with a 1.49 m stick. It is a view:
nothing reads it and nothing exports it. It is what would have shown every defect above at a glance.

**Legacy removed:** the raw source art (`assets/{AssaultRifle_4,AssaultRifle2_1,Pistol_5,Shotgun_1,
Bayonet}.glb`), `build_weapon.py --init` and its `source_convention`/`grip_offset`,
`assets/ui/AssaultRifle_5.blend` (a 5.4 m icon-render leftover) and `assets/merged_animation_bak.blend`.
Weapon scenes instance their model as a node named `Model`.

### W21 — THE GUN FACES ITS SHOT BEFORE IT FIRES (2026-09-13, PLAN.md 0.2)

"Flick behind and the bullet hits me." **The cause had already gone** (W15): a held weapon was a
`RigidBody3D` on the PICKUP layer, which the AimRay's mask includes, so a backward shot traced from
the muzzle through the gun's own box and `ImpactManager` walked up from the gun to the shooter's
`Health` — reproduced by putting that collider back (20 damage to the shooter). **What was still
live is the precondition:** the body turns toward the aim by a `rotationSpeed` lerp while the spine
and shoulders stop at `Stance.aimYawLimit`, so for several frames after a 135–180° flick the shot
left a gun pointing **84–102°** away from it, back across the body, in both views.

**Both views keep the two-stage trace from the animated gun** (it is what closes "behind a wall
but still killed someone"); what changed is that the gun is on target when it fires:
- `MovementController.keepAimWithinReach` — while in combat the body never lags the aim point by
  more than `aimYawLimit − 10°`, so the aim modifiers can always carry the gun the rest of the way.
  Small turns keep the smooth lerp. It is the split Source's player models and Lyra's
  "orient to controller while aiming" make.
- `WeaponItem.pointsAtAim` (15°, yaw only — the W5 elevation gap is by design) gates
  `WeaponController.onWeaponFire` for weapons that `launchesTowardAim()` (firearm muzzle trace,
  rocket, grenade). The press is **held, not dropped** (`AIM_HOLD_SECONDS` 0.15, independent of
  `fireBufferSeconds`), because the body lands one frame late: the camera moves at the end of a
  frame and the shot fires at the start of the next, before `MovementController` has run.

Measured by `tools/godot/probe_self_hit.gd` (real input, AR4, TPS+FPS, 56 flicks): worst
gun-off-shot **102.0° → 13.9°**, 0 presses lost, the gate adds **exactly 1 frame** in 11 cases
and nothing in the rest. `AimDebugAuto`, `probe_melee`, `probe_driveby_aim`, `probe_fps_camera`,
`probe_vehicle_views`, `probe_weapon_world_body` unchanged. Probe trap: an AR4 left at 2 rounds
reloads on the next press, which reads exactly like the gate eating it — refill between cases.

**The AI half, and the bench that found it.** An AI aims a shot by pointing its ray at the chosen
point on the frame it presses fire (`AttackState` → `AICharacter.snapAimRay`), in the ray's LOCAL
space. When the gate holds that press, the camera rig has carried the ray elsewhere by the time the
shot resolves: a shot held 2 frames after the target swung behind the AI hit **nothing**.
`WeaponItem.resolveSightPoint` re-snaps onto the aim point the command still carries (identical when
not held), for `launchesTowardAim()` weapons only — melee is never held, and re-snapping it broke
`probe_melee`'s AI case, which aims with the ray alone.

`AimWorkbench.tscn` is now also a **shooting bench**: `[`/`]` arm the AI with any weapon (for real,
through `requestEquip`), `T` aims it at the Player instead of the ball, `Y` fires one shot the way
`AttackState` does (`ScriptedInputController.pressFire`), `C` turns it 180° and fires on the same
frame, `N` spawns a stock `AICharacter` with its own brain, `B` drops cover between the shooter and
the Player, `P` makes the Player invulnerable. Every shot is logged in the overlay (and stdout,
`[AimBench]`): shooter, weapon, frames the gate held it, gun-off-aim, what the muzzle trace hit, and
gun-off-hit, with the damage it did grouped under it. The stand had no `ImpactManager`, so until now
nothing in it could take damage. `tools/godot/probe_aim_bench.gd` drives those keys headless.

**Open work is in `PLAN.md`'s Work queue** (P1–P2 and 5.1): seeded one-message shot + host validation, host-resolved
melee, per-shot remote cues, the stock-to-shoulder gate and rifle pose re-author, procedural recoil kick,
holster placement, projectile authority, lag compensation.

### W22 — THE STOCK BELONGS IN THE SHOULDER POCKET, AND THE POCKET IS MEASURED OFF THE SKIN (2026-09-14, PLAN.md A1)

W20 put every long gun's grip on the palm and left the butt wherever the arm pose happened to put it.
A1 is the gate for that, written BEFORE the pose re-author (A2) so the re-author has a target, and it
**fails on the poses that ship today — 6 of 6, on purpose.**

- **`StockPoint`** (a `Marker3D` on AR4 / AR212 / SG1) is the centre of the butt pad, read off a side
  silhouette of each model's `.blend` on a 1 cm grid: AR4 (0, 0.033, 0.281), AR212 (0, 0.046, 0.259),
  SG1 (0, −0.037, 0.265). SG1's pad is slanted and its stock drops well below the bore. ATL4 has no stock,
  so it has no marker.
- **The shoulder pocket is a fixed offset from `upperarm_r` in `clavicle_r`'s orthonormalised frame**
  (`probe_weapon_fit.POCKET_IN_CLAVICLE`), so it rolls with the shoulder when the aim modifier moves it.
  It was DERIVED from the character's own skinned `armor` mesh: in the hold pose, the frontmost skin
  vertex in a column 2–7 cm inboard of the joint and 0–4 cm below it, which is 4.3 cm inboard, 3.3 cm
  below and 8.6 cm in front of the joint centre. The probe re-derives it every run and fails on
  more than 1.5 cm of drift, because a second body (W18) would make the constant quietly wrong.
- **Two measurement traps.** `MeshInstance3D.bake_mesh_from_current_skeleton_pose` is refused headless
  ("The source mesh must have its skin registered with a valid skeleton"), so the probe skins the
  vertices by hand from `get_bone_global_pose`, which is the PRE-modifier pose. That is only valid in
  the hold pose, where no aim modifier runs. Every other bone read goes through a `BoneAttachment3D`.
  And an aimed arm sits in front of the chest, so the same skin column taken in the aim pose finds the
  FOREARM (0.45 m out) rather than the chest.

Measured on today's poses (MeshRoot frame):

| weapon | aim: stock vs pocket (right / up / fwd) | aim miss | hold: stock vs joint (up) |
|---|---|---:|---:|
| AR4 | −0.002 / −0.016 / −0.188 | 0.189 m | **+0.073** |
| AR212 | −0.002 / −0.003 / −0.166 | 0.166 m | **+0.067** |
| SG1 | −0.001 / −0.086 / −0.171 | 0.191 m | **+0.014** |

**Laterally the fit is already exact. The whole miss is fore-aft**, plus SG1's dropped stock. The palm
sits 0.205 m in front of the joint, and a shouldered stock needs it at pocket depth plus grip-to-butt,
about **0.37–0.39 m**. PLAN.md's earlier "0.27" was measured from the pocket, not from the joint. In
the hold pose all three stocks sit ABOVE the shoulder (muzzle down, butt high), where a low ready puts
them below it. Gate: `tools/godot/probe_weapon_fit.gd` (equips through a real pickup and
`on_set_weapon`, holds `aim` through `Input`). `-- --visuals=res://…/CharacterVisuals_X.tscn` measures
another body or a scratch export of an unexported pose, without touching the shipped `.glb`. That is how
the user's bladed `upright_aim_rifle` edit was studied: it blades the shoulders +34.8° through the
collarbones, but carries the firing arm 27.9° off the aim, which the W21 fire gate would refuse. Its
numbers are in PLAN.md "combat §A2".

### W23 — THE AIM MODIFIERS AIM THE GUN; THE STOCK IS IK'D INTO THE POCKET; THE AIM CLIP OWNS THE UPPER SPINE (2026-09-14, PLAN.md A2.0–A2.3)

**A2.0 — study a pose by its CLIP, not only through the rig.** `tools/godot/study_character_pose.sh [<blend>]`
exports a scratch copy to `assets/_study/`, re-points uid-stripped copies of `merged_animation.tscn` and the
visuals scene at it (a copied `uid=` wins over the path and silently loads the SHIPPED clip), runs `--import`,
then `probe_pose_clip.gd` (the clip on a bare `AnimationPlayer`, tree and modifiers off, so
`get_bone_global_pose` IS the final pose) and `probe_weapon_fit.gd`, and deletes the folder (`KEEP=1` keeps it).
`probe_pose_clip.gd -- --compare=res://assets/merged_animation.tscn --all` diffs every clip against the shipped
export. The user's saved `upright_aim_rifle` (17:26:44) was the 2026-09-14 snapshot exactly; its clip truth is a
**40.1° blade = 5.2° spine + 34.8° collarbones with the gun 33.2° right of the aim** (the rig showed 27.9°
because `WeaponBlend` drops the spine twist). Trap: a "spine share" from the clavicle ORIGINS read 32° — they
sit a few cm apart; use `spine_03`'s own +X (flipped to agree with the hip axis — the import's 180° puts it on
the body's left).

**A2.1 — `ShoulderAimModifier.aimHeldWeapon`: the reference is the held weapon's BORE** whenever
`WeaponItem.aimsAlongBore()` (firearms, launcher) and the weapon hangs from `weaponBone` (`hand_r`); else the
chest as before (melee, fist, throwable, a holstered weapon mid-switch). A chest reference throws away any
authored chest-to-gun relationship — a bladed rifle hold is exactly that — and the gun then points wherever
the clip left it. The weapon's skeleton-space transform comes from `HeldWeaponPose`: the weapon RELATIVE to its
`BoneAttachment3D` (exact, both nodes update together) composed onto the bone pose AS THIS PASS SEES IT — the
weapon's own global transform is last frame's. The carrier bone moves the gun as it turns it, so the delta is
solved twice ("turn, see where the gun went, aim again"). Measured: study pose gun-off-aim **27.9° → 0.0°**
(control 27.9°); AI gun-off-aim 2.0 → 0.2°; crawl down 5.0 → 1.5°. **The stance limits now bind the GUN**:
at every cap the gun sits exactly on `aimPitchMax/Min` (upright 45.0/−65.0, crouch 40.0/−60.0, crawl 30.0) and
the view-vs-gun gap is exactly W5's designed 15°; AimDebugAuto's limit bands assert the gun (crawl gained a real
band). **Consequence:** the torso spends the clip's gun offset — the study pose's blade collapsed 34.8° → 6.9°.
An authored blade survives only if the clip's bore is already on the body's forward line.

**A2.2 — `StockMountIKModifier` (firing arm):** while `engaged` (combat in a stance with
`Stance.stockMountEnabled` — Upright/Crouch; off for Crawl, DriveCarrier, Swim until A2.5) and the held weapon
has a `StockPoint`, the hand is TRANSLATED by stock→pocket (never turned — the aim already pointed the bore) and
`upperarm_r`/`lowerarm_r` are solved by `TwoBoneIK` (shared with `SupportHandIKModifier` now; clip elbow plane,
reach clamped). Pocket = `pocketOffset` (the W22 constant, owned here; the probe reads it) in `clavicle_r`'s
orthonormalised frame. Eases over `blendSeconds` (0.1). Skeleton order: spine aim, shoulder aim, stock mount,
(recoil A3), support hand. `lastHandMove()`/`lastShortfall()` are registered for probes. Measured: aim stock-to-
pocket **0.001–0.002 m** on AR4/AR212/SG1 on BOTH bodies (hand moved 0.17–0.19 m, palm now 0.37–0.39 m in front
of the joint), gun still on the line; `--stock-weight=0` puts the A1 failures back. **Not solvable in code: the
support hand.** The left arm is **0.416 m**; SupportPoint sits 0.50–0.62 m from the left shoulder with the clip's
arm (so the pre-A2 0.08–0.20 m misses were already pure reach) and 0.64–0.77 m once shouldered (misses
0.23–0.36 m). `SupportHandIKModifier` also now places its target from this pass's pose (after the stock mount)
instead of the marker's stale global.

**A2.3 — `WeaponTorsoBlend`, a stance-gated layer, NOT more bones in `WeaponBlend`.** `WeaponBlend` feeds every
stance, combat or not, and the archetype clips are standing poses: their spine on a crouched or prone body would
stand it up. The layer (filter `spine_03`, `neck_01`, `head_2`) is eased to 1 only in combat with
`Stance.weaponTorsoLayer` (Upright). **A blend-tree node's output can feed ONE input** — connecting
`CombatTransition` to a second node made Godot refuse the connection (`Condition "output == p_output_node"`)
and the WHOLE tree stopped evaluating: every stance read the rest pose (cockpit eye 1.348 m in all three). So
the layer has its own copy of the aim blendspace, `WeaponAimTorso`, indexed in `onWeaponEquip`. Filter width was
measured on AimDebugAuto's combat strafe cases (chest vs mesh; the strafe lines now print hips/chest/gun):
layer off −2.3/+5.7°, spine_01..03 −21.2/+13.2°, **shipped spine_03+neck+head −5.8/+14.4°** — spine_01/02 carry
the turn-and-walk clips' counter-rotation of a 55–63° hip swing (spine_01 alone sways 14.5° walking and 20–22°
strafing). The remaining left-strafe cost is `upright_walk_left` counter-rotating `spine_03` itself. Also fixed on
the way: `AnimationController.setHolster` wrote `WeaponBlend/blend_position`, which a Blend2 does not have, so the
story hook had never done anything.

Gates after all three: `probe_weapon_fit` aim 3/3 seated + on line on both bodies (hold 3/3 FAIL — A2.4 content);
AimDebugAuto `yaw 12/12, pitch 3/3, strafe 10/10, ai 8/8, limit 6/6, clav 1/1`; `probe_self_hit` worst 13.0°;
`probe_driveby_aim`, `probe_fps_camera`, `probe_vehicle_views`, `probe_support_hand_ik`, `probe_melee`,
`probe_weapon_{sockets,archetypes,scale,world_body}`, `probe_character_variant` PASS; cockpit eyes unchanged
(1.359/0.787/0.808); `check_character_anim` PASS on both bodies; `World.tscn` boots clean; `./gradlew test` green.

### W24 — THE RIFLE POSES ARE SOLVED, NOT NUDGED; THE SUPPORT HAND GRIPS WHERE THE ARM REACHES (2026-09-14, PLAN.md A2.4–A2.5)

**`blender/tools/pose_weapon_hold.py` (then `pose_long_gun.py`) authors `upright_aim_rifle` and `upright_hold_rifle` from the constants the
game reads** (`SocketRifle`, the weapon markers, `StockMountIKModifier`'s anchors, all parsed out of their
files). A pose nudged by eye passes some facts and silently fails the others; the user's 22:48 save was the third
such pose (blade 43.3° but 36° of it in the collarbones, gun 9° off the line, stock 10–13 cm behind the pocket).
Frames, verified to reproduce `probe_pose_clip.gd` to the millimetre: the glTF exporter changes axes on the ROOT
joint only, so a Godot bone-local transform applies unchanged to the Blender pose bone; body = `(-x, z, y)` of
armature space; a `.tscn` `Transform3D(...)` is ROW-major. `measure` prints blade (spine vs collarbone share),
gun yaw/pitch, stock vs pocket, support grip vs `SupportPoint`, right eye vs the bore (and clearance over the
gun's top), elbow flare, and POKE — how deep the gun's surface sits inside the skinned body. `--render <dir>`
writes Workbench contact sheets (front, both sides, top, 3/4, TPS). Poke-test traps: keep the hands IN the BVH
and skip samples whose nearest face is a hand's (removing hand faces leaves a hole at the wrist, and every
sample inside the fist read 15 cm deep in the forearm); leave hair out (open cards); exclude the last 4 cm of
the stock (the butt pad is meant to press into the pocket).

Solve order, each step reading the previous: blade (spine_03 twist, then the LEFT collarbone reaching), a 12°
shrug of the right collarbone (lifts the pocket toward the cheek), gun (bore on the forward line, level, butt
pad on the pocket), firing arm two-bone to the grip (elbow flared 40°), support arm to the grip point with the
clip's hand-to-gun orientation, fingers curled absolutely (45/60/40°), then the head by a 3-angle minimise
(nod, tilt toward the stock, turn) inside a neck's comfortable range. Shipped: `--spine 26 --collarbones 18
--shrug 12` → blade **44.5° (spine 26 / collarbones 18.5)**, gun 0.00°, AR4 stock 0.000 m, support grip 0.012 m,
right eye 3.9 cm left of the bore and 5.8 cm over the gun's top (head tilt at its 18° cap — a closer weld
needs a laid-over head), poke ≤ 1.1 cm on AR4/AR212, 2.4 cm on SG1 (its dropped stock). The hold is a
PATROL CARRY, not a low ready: grip 12 cm inboard / 22 cm below / 22 cm ahead of the shoulder, muzzle 35° down
and 55° across the body. A forward low ready was tried first and cannot work with this arm: the support hand
fell 12–22 cm short, and pulling the stock to the chest to help poked 3–4.5 cm into it. Across the body the
support grip is 0.000–0.021 m off, poke ≤ 2.1 cm (the stock pinched under the forearm), stock 3.4 cm below the
joint; the clip's breathing is kept (a constant local delta per key). Both clips are copied into
`merged_animation_f.blend` (`copy-from`): weapon clips are shared (W18).

**The support hand's REACH decided where it grips.** GodotChan's arm is 0.416 m shoulder→wrist (28% of height;
a human's is ~33%), which reaches ~0.235 m ahead of the pistol grip with the blade above — the rear of a
handguard, not its middle and not a pump. So:
- **`SupportPoint` means the GRIP now, not the wrist.** `SupportHandIKModifier.gripFraction` (0.75 of the way to
  `middle_01_l`, from the skeleton rest) is where a hand closes round a handguard; the wrist target is the marker
  pulled back through the hand. And `keepHandRotation`: TwoBoneIK turns the hand with its parents, so a hand that
  reached the marker still did not wrap the handguard (the control turns it 17.6°). `lastGripMiss()` is registered.
- Markers moved to where the arm reaches: **AR4 (0, 0.08, −0.25)**, **AR212 (0, 0.085, −0.23)**, **SG1
  (0, 0.015, −0.30)** — SG1's is the pump's rear edge and still 4.0 cm short (a pump is further than this arm
  reaches with the stock shouldered; the user allowed the shotgun to be the compromise). A longer-armed body
  is the real fix and is the user's call. `WEAPON_AUTHORING.md` carries the rule.

**Crouch takes the torso layer too** (`Stance.weaponTorsoLayer` on Crouch). With only `spine_03`, neck and head
in the layer, spine_01/02 keep the crouch lean and the gun-referenced aim re-levels the chest, so the crouched
upper body measures IDENTICAL to upright (blade 44.5°, head over the stock). Without it the head keeps the
crouch clip's orientation 8 cm off the stock while the spine aim still twists the chest (blade 46.7°). Crawl,
DriveCarrier and Swim do not mount the stock; crawl measures gun on the line and AR4's stock on the pocket from
the clip alone, but the arms are still standing arms on a prone chest (W4's authored prone set is still needed).

Gates: `probe_weapon_fit.gd` **PASS on both bodies and `--stance=crouch`** (new `--stance=`, `--torso-layer-on=`;
now asserts the support grip, 5 cm), with the StockMount hand move **0.000 m** on AR4 (the clip is right, the IK
has nothing to do); control `--stock-weight=0 --aim-reference=chest --torso-layer=off` → gun 26° off, 4 FAIL.
`probe_support_hand_ik.gd` grip 0.002 m, hand turned 0.27° (control `--control`: 0.052 m, 17.6°, 2 FAIL).
`probe_weapon_archetypes.gd` now expects 3 clusters (the launcher is still the pre-A2.4 rifle copy). AimDebugAuto
`yaw 12/12, pitch 3/3, strafe 10/10, ai 8/8, limit 6/6, clav 1/1`; `probe_self_hit` worst 12.8°;
`probe_driveby_aim` 8/8 (worst residual 82.1°); `probe_character_variant`, `probe_melee`, `probe_fps_camera`,
`probe_vehicle_views`, `probe_weapon_{sockets,scale,world_body}` PASS; cockpit eyes unchanged; `check_character_anim`
PASS on both bodies; `World.tscn` boots clean; `./gradlew test` green.

### W25 — ONE HOLD MODEL FOR EVERY WEAPON: SOCKET + ARCHETYPE CLIP + AIM + MOUNT IK + SUPPORT IK (2026-09-15)

**The rifle's base is now the artist's own placement.** The user placed an `AR4` model in `merged_animation.blend`
level on the forward line, stock high on the shoulder, and posed both hands round it by eye. It sat 5 cm ahead of and
21° off the clip hand's socket fit, so re-solving the arms to the old socket (tried, rendered) put the fist low on the
grip and the left hand over the handguard, where the user had it cupped under. The pose is therefore ADOPTED, not
re-solved: `pose_weapon_hold.py adopt --placed AR4 --apply` derives the three pieces of data that reproduce it in
game and writes them where the game reads them. `SocketRifle` (both bodies: 5.0 cm / 21.1° from the W20 fit),
the `StockPoint` anchor (−0.0221, −0.0284, 0.0775), and AR4's `SupportPoint` (0.0116, 0.0206, −0.2368), 3 cm under
the handguard at its rear. AR212 and SG1 take the same relation to their own handguard/pump. The clip's bones are
untouched, and in game the stock IK now moves the hand **0.000 m** on AR4 and the grip is 0.000 m off. The rifle
hold was re-solved for the new socket. The placed `AR4` was then removed from the `.blend` (`remove-object`).
With the authored head that low, the headphones sit 4.6 cm into AR4's receiver; left as authored.

**The model is the CS / Left 4 Dead / GTA one, and it is now one row per archetype**
(`weapon_archetypes.json` `holds`):
1. The weapon hangs from the firing hand at ONE socket per archetype (`SocketRifle`, `SocketPistol`,
   `SocketLauncher`, …).
2. ONE upper-body clip pair per archetype (`upright_aim_<arch>`, `upright_hold_<arch>`) supplies the class of hold.
3. The aim modifiers point the BORE (W23).
4. **Mount IK** puts a marker on the weapon at a body anchor.
5. **Support IK** puts the off hand's grip on `SupportPoint` (W24).

A new weapon of an existing archetype is markers only. A new archetype is a row, a socket, a clip pair and a solve.

- **`StockMountIKModifier` is a general mount IK now.** `mount_markers` / `mount_offsets` are index-parallel. A held
  weapon mounts with the FIRST marker it declares (`current_mount()` is registered). A weapon declaring none, like a
  pistol, is left alone. The anchors are facts about the body's skin, so each visuals scene owns them. The Java
  `DEFAULT_MOUNT_*` arrays are the fallback and are parsed by the tool, so keep their literal shape. `pocketOffset` /
  `stockPointName` are gone.
- **`pose_weapon_hold.py`** (was `pose_long_gun.py`) takes `--hold <archetype>`. Commands:
  - `measure [--placed OBJ] [--render DIR]`
  - `solve-aim` with placement `mount` (marker on anchor, bore level) or `eye_line` (the bore `sight_drop` under
    the right eye, the grip `reach` ahead of the shoulder — for a stockless weapon)
  - `adopt [--placed OBJ] --apply` (derive socket/anchor/SupportPoint from a pose the artist made)
  - `solve-hold`, `body-anchor r u f`, `skin-anchor`, `remove-object`, `copy-from`

  Row arguments are the shipped defaults, and the command line overrides them. Primitive weapons (ATL4) are
  sampled/rendered as their box. Scene weapon models are hidden in renders unless `--show-placed`.
- **Pistol:** the authored two-handed isosceles clip was already sound (gun on the line, no poke), so it is kept.
  PI52 gained a `SupportPoint` ADOPTED from it (0.0105, −0.0473, 0.0193: the left hand cupping under and behind the
  grip), so the support IK now holds that grip through aim and stance changes.
- **Launcher (first pass):** ATL4 gained `ShoulderRestPoint` (0, 0.01, 0.25 — the tube's underside 25 cm behind the
  grip) and a `SupportPoint` under the tube. Its anchor is on the deltoid 2 cm outboard of / 6 cm above the joint
  (0.0582, 0.0246, −0.0002). A skin-derived "top of the shoulder" is INBOARD of the joint and put the tube through
  this character's head and headphones. `SocketLauncher` was stale (it held the grip 17 cm from the wrist) and now
  equals the rifle's hand fit. Aim: blade 34°, tube on the anchor, grip 0.000 m, eye 10 cm left of the bore, 3.3 cm
  of tube inside the right headphone cup (the head is kept as authored: an AT4 sight is beside the tube, not above
  it). Hold: carried low across the body, support grip 5.8 cm short.

Gates: `probe_weapon_fit.gd` now covers **AR4, AR212, SG1, PI52, ATL4** through each weapon's own mount (PASS on
both bodies and `--stance=crouch`). SG1 grip 3.3 cm, every other grip and mount 0.000–0.002 m. The pocket-vs-skin
check is "within 2 cm" (the pocket is authored now; 1.5 cm measured). Also passing: `probe_support_hand_ik`,
`probe_weapon_{archetypes,sockets,scale,world_body}`, `probe_character_variant`, `probe_melee`, `probe_self_hit`
(worst 12.7°), `probe_fps_camera`, `probe_vehicle_views`, `probe_driveby_aim` (82.1°); AimDebugAuto 40/40;
`check_character_anim` PASS on both bodies; `World.tscn` 0 errors; `./gradlew test` green.

### W26 — A BORE IS ONLY AIMED WHILE THE WEAPON IS POSED; THE PRONE BODY IS SYMMETRIC (2026-09-15, user-reported)

**"An AI's upper body spins nearly 360° when it switches to a rifle."** At the end of a switch the rifle becomes the
held weapon and the `WeaponChange` draw one-shot starts. `ShoulderAimModifier` aims the held weapon's BORE (W23),
and for the length of that clip the bore is being swung up from the holster, so the spine chased it. An AI is in
combat while it switches, and a player usually is not. Reproduced on a player holding `aim`
(`tools/godot/probe_switch_spin.gd`): chest overshoot **120°**, travel **309°** per switch to AR4; pistol switches
were fine.
- `AnimationController` sets `weaponPosed` (no `WeaponChange` / `Reload` / `Attack` one-shot active, read only in
  combat) on both aim modifiers and gates `StockMountIKModifier.engaged` with it.
- The modifier always solves the CHEST reference, and eases the BORE reference in and out over `boreBlendSeconds`
  (0.15 s, a quaternion slerp of the two deltas).
- During a draw or reload the chest squares to the target, then re-blades once the gun is up.
- A trap this introduced, with an eye on it: the delta solve returned null for "already on target", and the blend
  read that as "no bore" (a one-frame un-blade whenever the bore settled exactly). It returns a zero rotation now.
- Result: overshoot **6°**, travel **89°** (the chest squaring and re-blading, 26° each way). `-- --control`
  (`bore_during_one_shots`) puts the spin back.

**"Crawl always leans left and rocks left/right while moving."** Yaw about world up barely sees a prone body. The lean
was in the LEGS: `crawl_idle` had the hips yawed 8.2° and the left knee 38 cm out against the right knee's 13 cm.
The rocking was the crawl cycle swinging the hips 29° peak-to-peak; the chest was already steady (1.2°).
`crawl_left/right/back` are still copies of `crawl_forward` (W10 placeholders). Fixed in the clips with
`pose_weapon_hold.py`, both bodies:
- `symmetrize --action crawl_idle-loop`: each side is averaged with the other's mirror, centre bones with their own.
  The rig is X-symmetric to 0.0002 and the mirror is a reflection conjugate of each bone's rest frame.
- `damp-hip-yaw --factor 0.8` on the four moving crawls: the pelvis turns about world up by −0.8 × its hip yaw,
  then `spine_03` gets its world orientation back, so the chest and aim do not move while the legs still alternate.

Measured in game: idle hip yaw **+0.0°**, knee asymmetry **0.000 m**; moving hip sway **5.7°** (was 29).
`tools/godot/probe_crawl_balance.gd` asserts those and compares crawl's chest and head against upright. Its
`--dump=` writes the FINAL in-game bone pose (after every modifier), and `pose_weapon_hold.py render-dump` renders
it headless. The glTF axis change sits on the root joint only, so a Godot skeleton-space bone transform is
`G2B @ G` with no right-hand conversion.

**What a balanced prone set looks like, still to author:** a symmetric prone idle is what `symmetrize` produced.
The moving crawl should keep hip yaw within about ±3° with the chest on the aim line, as PUBG and Arma prone do, and
their characters lower the weapon while crawling. Strafing and backing need their OWN clips: an elbow-and-knee
sideways shuffle and a push back, not the forward crawl played sideways. The prone AIM set is still W4.

Gates: `probe_switch_spin` and `probe_crawl_balance` PASS; `probe_weapon_fit` PASS (default, female, crouch, crawl);
`probe_support_hand_ik`, `probe_weapon_{archetypes,sockets,world_body}`, `probe_character_variant`, `probe_melee`,
`probe_self_hit`, `probe_fps_camera`, `probe_vehicle_views`, `probe_driveby_aim`; AimDebugAuto 40/40;
`check_character_anim` PASS on both bodies; `World.tscn` 0 errors; `./gradlew test` green.

### W27 — THE WEAPON KICK IS A SPRING ON THE FIRING ARM, AND IT IS A DIFFERENT LAYER FROM THE AIM (2026-09-15, PLAN.md A3)

Recoil is three layers and only the middle one was missing. **The aim** — the camera kick and the
spread bloom — has always existed (`Character.applyRecoil` -> `ControlRotation.recoilPitch/Yaw`,
`FirearmItem`'s bloom), is owner-only and is correctly not replicated. **Large discrete motion** — a
pump, a bolt, a launcher rocking the shoulder — is animation, on the weapon's own `AnimationPlayer`
(`WeaponItem.fireAnimation`, W13). Between them sits the **visible weapon kick**, which nothing did:
the gun sat perfectly still in the hands while the camera jumped.

**It is code, not a clip, and the reason is full auto.** A per-shot animation restarted every 0.1 s
plays its first frames forever and can never settle; a spring takes any number of impulses at any
spacing and always comes back to rest. `character.WeaponRecoilModifier` is two scalar springs —
push-back (m) along the bore and muzzle pitch (deg) — each taking a STEP per shot, because a shot IS
instantaneous, with the spring as the return. The firing hand is rotated about the SHOULDER JOINT by
the pitch (a shouldered rifle pivots at the butt pad, a few centimetres from that joint), translated
back along the bore, and `TwoBoneIK` swings the arm after it; the hand keeps the kick's rotation, so
the gun turns with it instead of sliding through the grip.

**IK is not a recoil source — it is what keeps the hands on the gun while the kick moves it.** The
modifier sits between `StockMountIKModifier` (which decides where the gun sits) and
`SupportHandIKModifier` (which puts the off hand where the gun ENDS UP) in the skeleton's children,
so the support hand follows the kick for free: both read the weapon through `HeldWeaponPose`, which
composes it onto the firing hand's pose as this pass sees it. Measured: the off hand's grip miss
never left 0.022 m through a burst.

**Pitch only, with no yaw term, and that is a hard constraint rather than a simplification.** The
horizontal half of recoil is already the camera's (`FirearmItem.applyRecoil` randomises a yaw kick on
`ControlRotation`). A yaw kick HERE would turn the bore off the aim line in the one axis
`WeaponItem.pointsAtAim` gates firing on (W21, 15 deg of yaw), so a burst would start eating its own
trigger presses — the gate asserts 0.26 deg of yaw drift and that every press still fired.

**The numbers are per weapon** (`WeaponItem.kickBack`/`kickPitch`/`kickSpring`/`kickDamping`, and the
spring is part of how heavy a gun feels): AR4 0.020 m / 2.5 deg / 22 / 1.0, AR212 0.018 / 2.2 / 24,
SG1 0.050 / 6.0 / 14, PI52 0.012 / 3.0 / 26, ATL4 0.060 / 5.0 / 10. They are **zero by default**, so a
weapon that authors no kick does not kick — the right answer for a fist, a knife and a thrown
grenade, and it makes an unauthored firearm visible rather than silently inheriting a rifle's feel.
`WeaponController` delivers the impulse at the two sites W13 already uses for the weapon's own moving
parts — `onWeaponFire` on the owner and `playRemoteFireCue` on a puppet — so **a remote peer sees the
kick with no new message**, and an AI kicks because it fires through the same path.

**MEASURING IT NEEDED TWO CORRECTIONS, AND BOTH WERE THE PROBE AGREEING WITH SOMETHING THAT WAS
ALREADY TRUE.** (1) *The clip moves the hand by itself* — the aim pose breathes 0.0028 m, so "the hand
moved 5 mm" is evidence of nothing; every case measures a quiet window of the same length first and
the kick has to beat it by 3x. (2) *The muzzle rises whether or not this layer exists*: the camera
recoil lifts the aim point and the aim modifiers follow it, so with the kick switched off the world
-frame muzzle still rose **+1.27 deg (AR4) / +2.17 deg (SG1)** and the whole arm still moved 0.008–0.011
m. Measured **against the aim line** the camera layer cancels — both the gun and the target move with
it — and the control reads **+0.00 deg** on both weapons. That is the number the gate asserts, and the
hand-displacement threshold is 0.020 m rather than "more than nothing" for the same reason.

"Back to rest" is likewise asked of the SPRING, not of the hand: the hand never returns to an exact
position because the clip has carried on, so rest is `< 1 mm / < 0.05 deg` on the modifier's own state
and the hand only has to come back inside the clip's own wobble.

Gate `tools/godot/probe_recoil_kick.gd` **14/14** (AR4, a 6-shot burst: hand peak 0.0320 m, bore
+2.72 deg off the aim, one kick per shot, spring at 0.00000 m after 0.75 s; SG1, one shot: 0.0665 m and
+5.68 deg, settled). `-- --control` sets `weight = 0` and fails 4. Everything else unchanged:
`probe_self_hit` worst 12.7 deg with 0 presses lost, `probe_weapon_fit` PASS (default, female, crouch),
`probe_support_hand_ik`, `probe_melee`, `probe_switch_spin`, `probe_crawl_balance`,
`probe_weapon_{sockets,scale,world_body,archetypes}`, `probe_character_variant`, `probe_fps_camera`,
`probe_vehicle_views`, `probe_driveby_aim` PASS; AimDebugAuto 40/40; `World.tscn` 0 errors;
`./gradlew test` green.

### W28 — THE SLING IS THE CHARACTER'S, THE HANG POINT IS THE WEAPON'S (2026-09-16, PLAN.md A4)

W20 moved every model's ORIGIN onto its grip and replaced the per-weapon markers on the character
with one socket per grip archetype. `WeaponController.reparentWeapon` asks the weapon how it sits
(`WeaponItem.alignmentFor(holstered)`), so a HOLSTERED weapon started putting its GRIP on the
back/hip socket where it used to put its old arbitrary origin — and the holster sockets, authored
against those origins, were never re-checked. Measured (`tools/godot/probe_weapon_holster.gd`, the
gate written first): the back sockets hang a long gun **straight down** (86 deg from vertical), so on
a 1.49 m body with 0.43 m of back between shoulder and hip, both ends leave the torso — AR4's butt
CORNER 0.133 m from `head_2` (beside the ear), ATL4's tube **1.460 m, above the 1.435 m crown**, SG1's
muzzle at 0.378 m, below `calf_l`. Worse, **two holstered long guns occupied each other**: the pair
is 0.163 m apart laterally while a slung gun's tall axis (0.18-0.29 m) lies ACROSS the back, so they
overlapped by **0.153 m**. And the right-hip socket was authored pointing nearly FORWARD (75 deg from
vertical), which drove a holstered knife into the hip: **17.3%** of its volume inside the spine and
thigh bones.

**Which owner fixes what is the whole of A4.** PLAN.md said to prefer a per-weapon `holsterPoint`
over touching the shared sockets, and that is right for a FIT — but "how the strap crosses this
character's back" is one fact shared by every long weapon, and writing it into four weapons would be
four copies of it. So:

- **The SLING is the character's**, solved in the body's frame by
  **`tools/godot/solve_holster_sockets.gd`** and applied to both `CharacterVisuals_*.tscn`: 22 deg
  from vertical (muzzle down-left, butt up-right), the gun FLAT against the back (its local X out of
  the back), the pair separated in **DEPTH** (0.20 m and 0.32 m behind the spine) because laterally
  they cannot be. The right hip is now defined as the **MIRROR** of the left (a conjugation by a
  body-frame reflection, which keeps the frame right-handed and only decides which face looks
  outward); the left hip measured clean as authored and is the reference. A socket is never nudged by
  eye — its authored transform is in a BONE's frame and says nothing legible about where the weapon
  ends up.
- **The HANG POINT is the weapon's.** `ATL4`'s grip is 0.397 m from the rear of its tube, so even
  slung it stood above the crown: it gets `holsterPoint = "HolsterPoint"` 0.20 m behind the grip
  (1.460 -> 1.295 m). That is what the escape hatch is for.
- **A 0.81 m axe is a LONG weapon, whatever slot it occupies.** `MW2`'s hip list could not hold it in
  any pose — by the grip its head reached 0.154 m off the ground, by mid-haft the head was inside the
  character's own head (0.112 m from `head_2`, 20% buried). Its `holsterSockets` are the two solved
  back slings now (its MELEE slot is unchanged); with both taken by primaries it falls back to the
  documented stow-hidden, which is what GTA does with a weapon it has no visible slot for.

Measured after, every weapon on its socket: poke into the character's own hitbox bones
**0.165 -> 0.002-0.032 m** (0-2.7% of the weapon's volume, which is a weapon RESTING on the back),
nothing above the crown, nothing below 0.30 m, and **0.000 m** between any two weapons of a loadout.

**How it is measured, and the two traps.** The poke test is a shape query against the character's own
`PhysicalBone3D` bones (layer 4 — the bodies a bullet hits, so they track the live pose), plus a grid
of points inside the weapon's own collision box; weapon-vs-weapon uses a temporary `StaticBody3D`
proxy on an unused layer so the engine's own OBB test answers it. The crown is **measured** off the
skinned `head` mesh every run (1.435 m; hair and headphones reach 1.458/1.469 and are deliberately not
the line — W25 already accepted a held launcher inside the headphone cup), because a written constant
would be silently wrong on a second body. And **a `.tscn` `Transform3D` literal's 9 basis floats are
ROWS, not the three axis vectors**: printing `basis.x/y/z` in order transposed it, the position stayed
exactly right, and the rifle came out lying HORIZONTALLY across the back (89 deg from vertical instead
of 22). The solver serializes with `var_to_str` now, which is the engine's own form.

Gate `tools/godot/probe_weapon_holster.gd` **PASS on both bodies** (7 weapons alone + two loadouts:
two slings and both hips, then the axe on the second sling). `LongWeaponHolsterMaker3/4` and
`ShortWeaponHolsterMaker3/4` are left as authored and unsolved — with two PRIMARY, one SECONDARY and
one MELEE slot nothing can reach them, and a weapon there hangs horizontally by its grip (~0.6 m out
to the left). Solve them as third/fourth poses the day a loadout needs them.

### SR3 — a sniper rifle (2026-09-16, user-asked; the sniper mechanic itself is later)

`assets/weapons/SR3.blend` was raw art: one mesh, ~7.24 units long down **+X**, bolt handle toward
−Y. Normalised in place to the standard (`blender/WEAPON_AUTHORING.md`) — scaled to metres, turned so
the muzzle is **+Y** in Blender, origin moved onto the grip, every transform applied, meshes in a
collection named `SR3`. **The user replaced the model once mid-session** (a Remington 700-pattern gun
became an AWP/L96-pattern one: thumbhole stock, heavy barrel, muzzle brake, 908 verts), and that is
the useful record: re-deriving took one measurement pass, because everything downstream is derived
from the model rather than hand-tuned.

**The reference follows the MODEL, and the model's own proportions pick it.** The shipped one is an
**Accuracy International AWP / L96A1 (24 in barrel, muzzle brake), 1.124 m** — trigger-to-butt
measures 2.281 raw units, which is **0.354 m** at that scale against the AWP's 0.356 m length of
pull, where the earlier 1.003 m Remington reference would have made it 0.316 m. So the size is a fact
about the weapon, not a proportion knob. At 1.124 m it is the longest weapon in the game (75% of this
1.49 m character's height, which is what an AWP looks like on a small shooter) and the tightest fit on
the W28 back sling: slung, its muzzle corner sits **0.284 m** off the ground against the gate's 0.25 m
limit, and its butt corner 1.395 m under the 1.488 m crown.

**A THUMBHOLE STOCK PUTS THE FIST CLOSER TO THE TRIGGER than the standard's rule of thumb.** The
"origin is the centre of the firing fist" rule is a *position*, and the usual ~6 cm behind the trigger
comes from an AR-style pistol grip; here the hand wraps the column in front of the hole with the thumb
through it, which measures **4 cm** behind the trigger and level with the hole's centre. Placing it at
6 cm would have put the origin inside the hole. Measured after: grip->rear **0.306 m** (AR4 0.281,
SG1 0.272, and an AWP's long stock is why it is the largest).

It is a plain `FirearmItem` of the **rifle** grip archetype, so it needed no character edit: `Muzzle`
on the bore tip of the brake, `SupportPoint` 0.24 m ahead of the grip (where this body's 0.416 m arm
reaches), `StockPoint` on the butt pad — all three read off the conformed mesh's own cross-sections,
never off the render. Stats are sniper-shaped and provisional: bolt/semi (`auto = false`,
`fire_rate 0.9`), `damage 110` (a torso hit kills a 100 HP target, a leg does not), `spread 0.005`
with heavy bloom, 5+20 rounds, a 3.0 s reload, and a hard W27 kick (0.045 m / 5.0 deg). **No scope, no
zoom, no sway** — that is the mechanic still to come, and no icon asset exists yet (SG1, ATL4, MW1,
MW2 and T1 already ship without one). Registered in `weapon_models.json`, `weapon_archetypes.json`
(`holds.rifle.weapons`), `AimDebugHost.BENCH_WEAPONS`, `probe_weapon_fit`, `probe_weapon_holster`, the
weapon library and `DebugWorld.tscn`'s pickup row.

Gates: `probe_weapon_scale` (1.124 m, 0.0% out, instanced at identity, muzzle on −Z, collider rules),
`probe_weapon_sockets` (no `GripPoint` — the origin IS the grip), `probe_weapon_fit` (stock on the
pocket **0.000 m**, support grip **0.012 m**, gun on the aim line) and `probe_weapon_holster` (poke
**0.000 m**, the only weapon with no hitbox contact at all) all PASS, on both bodies.

**Superseded by W32: `SniperItem` is folded into `FirearmItem` + a `ScopeConfig`.** The argument
against a new `WeaponType` value below still stands; the subclass itself turned out to be only data.
**`weapon.SniperItem` WAS the type, and a new `WeaponType` VALUE would have been the wrong way to get
one** (user-asked). `WeaponType` is a coarse behaviour category — RANGED / THROWN / MELEE — and the
code tests it with `== WeaponType.MELEE` / `== RANGED` in `AICharacter` and in `Character`'s combat
entry, so a fourth value would make every one of those tests silently miss a sniper rifle. A sniper
IS ranged; what differs is behaviour, and behaviour is a subclass — the split the weapon set already
makes (`ProjectileItem`, `ThrowableItem`, `MeleeItem`, `KnifeItem`, `AxeItem` are all classes).

What the class owns today is the **CS:GO AWP rule**: `hipfireSpreadMultiplier` (8.0) multiplies the
cone while the holder is not in combat, so the rifle is pinpoint through the sights and near-useless
from the hip — which is what makes a one-shot weapon fair. Only `getCurrentSpreadDeg` widens:
`minimumSpreadDeg` is the FLOOR the host validates a client's reported cone against (N1), and a floor
that grew with the hipfire multiplier would refuse an honest scoped shot from a client whose aim state
the host has not seen yet. **Widening a cone is always safe there; narrowing never is.** The scope
itself (an ADS FOV plus an overlay or a render-to-texture scope), hold-breath sway and the bolt-cycle
view punch are NOT stubbed as fields — a field nothing reads is a field that is wrong the day
something reads it.

**The aim POSE is a grip archetype, and index 9 is `sniper`** (user-asked). A scoped shooter's head
comes down to the scope and the support hand goes further out, which is a pose, and a pose is exactly
what `weaponPoseIndex` selects (W12). So: `weapon_archetypes.json` gains index **9** (the list is
APPEND-ONLY — an index is stored in every weapon `.tscn`, so inserting in the middle silently re-poses
existing weapons), a `holds.sniper` row, and three clips minted by the one-owner placeholder mechanism
in `character_anim_naming.json` — `upright_aim_sniper`, `upright_hold_sniper`, `weapon_switch_sniper`,
copies of the rifle's, **wired** into all four weapon-index blendspaces (`WeaponAim`,
`WeaponAimTorso`, `WeaponHold`, `WeaponChangeAnimation`, `max_space` 8 → 9) in BOTH bodies. It shares
`SocketRifle` and the `StockPoint` mount because a sniper's grip IS a rifle grip — W20's rule is one
socket per grip CLASS, and the fit gate proves this hand works (stock 0.000 m, support grip 0.012 m).
Because the clips are copies, the render is unchanged until they are authored: 90 clips (was 87),
tree_refs 67 (was 64), orphans still 23, and `probe_weapon_archetypes` sweeps 10 indices and still
finds **3** hand-pose clusters, with sniper landing in the rifle one. Authoring the scoped pose is a
pose edit on an existing action — no rename, no scene change, no code.

**`damage 150` is the CS ONE-SHOT BODY feel, and the number comes from the bone table, not from
taste** (user decision, 2026-09-16). `Health.getBuiltInMultiplier` against a 100 HP character gives
upper torso (`spine_03`, clavicles) ×1.0, **mid and lower torso (`spine_02`, `spine_01`, `pelvis`)
×0.75**, arms ×0.75, legs ×0.5, head ×4.0 — so "any torso hit kills" is decided by the WORST torso
multiplier: `100 / 0.75 = 133.3` is the floor, and 150 clears it with the same margin CS's AWP has
(112.5 at the worst torso against its 115 chest). Result: upper torso 150, mid/lower torso 112.5,
legs 75 (survivable, as in CS), head 600. **The one thing that does not match CS: arms share the
mid-torso ×0.75**, so an arm hit kills here where CS leaves 15 HP. That is a fact about the
CHARACTER's bone table, not the weapon, so the fix if it matters is a per-bone
`MeshConfig.boneHitMultipliers` entry (arms ≤ 0.66), never a lower weapon damage — lowering the
damage would take the torso one-shot away with it. 5 + 20 rounds, and it auto-reloads on empty like
every other magazine weapon (see "Auto-reload on empty").

### W29 — THE SCOPE IS A DERIVED VIEW, NOT A SECOND COPY OF THE PREFERENCE (2026-09-16, PLAN.md 2.7 piece 1)

**Decided by the user: a scoped shot is FIRST PERSON, and both view modes converge on it** — a TPS
player scoping sees exactly what an FPS player sees. That is the industry default (CS, PUBG), it
means there is only ONE scoped view to build and gate, and it avoids the disagreement W7/W21 spent
two rounds closing: a zoomed third person puts the reticle and the bore in different places. The
codebase already had the hard part — W5's filtered bone-mounted FPS rig and
`Character.refreshHeadVisibility`'s derived "is the camera behind THIS character's eyes", which a
scope answers yes to.

**The trap the decision creates is W6's, and it is the whole of this change.** The obvious
implementation writes `Character.isFpsMode` when the scope goes up and writes it back when it comes
down. That cannot survive an interruption BETWEEN the two writes — a death, a weapon switch, a
dropped gun, a car door — and the player is left stuck in first person with no way out. So:

- **`UserCommand.wantScope`** is the raw intent (the aim button HELD), deliberately not `wantCombat`,
  which is also set by firing, by the aim-stay timer, and **unconditionally in first person** — a
  scoped rifle merely carried in FPS would otherwise be permanently scoped.
- **`WeaponController.scopedNow()`** decides whether that intent means anything: the button, no
  weapon transition in flight, and a held weapon that declares a scope at all.
  **`Character.isScoped()`** adds the two conditions the weapon cannot see — dead, or in a seat.
  Nothing is latched, so every way out of the scope is a CONSEQUENCE: the button released, the draw
  animation of a switch, a weapon with no scope, no weapon, no pulse, a carrier.
- **`Character.isFirstPersonView()` (`isFpsMode || isScoped()`) is the one question both rigs ask.**
  `isFpsMode` stays the player's PREFERENCE and is never written by the scope, so releasing the
  button returns the player to exactly the view they chose, with no second write to get wrong.
  `TPSCameraController` and `FPSCameraController` read it in place of the preference, and
  `refreshHeadVisibility` takes one more condition rather than a fourth latch.

**A weapon has no scope unless it declares one.** `WeaponItem.scopedFovDegrees()` returns 0 by
default and **0 IS "no scope"** — one fact, one owner, no separate flag to disagree with it;
`scopeZoomSeconds()` is its transition. `SniperItem` supplies both (`scopedFov` 20°, ~3.75× against
the ~75° hip FOV — the AWP's scope; `scopeZoomTime` 0.12 s). **The camera owns the view and the
weapon owns the data**, the same split W13 makes for the weapon's own animation and W27 for its
kick: `TPSCameraController.setCameraFov` stays the SINGLE writer of the shared `ActiveCamera`'s FOV
and simply has a new highest-priority source. Only the TRANSITION is edge-driven (a tween is a
one-shot), from `_physicsProcess`, which is the node that gets a frame in every mode.

**The scoped eye admits NO bone motion.** `FPSCameraController` scales its filtered deviation to 0
while scoped and keeps the slow baseline: through a 3.75× optic the leftover bob that reads as "a
walk" unscoped reads as an unusable picture, and this rig sits inside a loop (bone → camera → aim
target → `ShoulderAimModifier` → bone) whose gain rises with the zoom — W8.3 is what that looks like
when it gets away. W11's cockpit mount took the same decision for the same reason: a view you AIM
from comes off a steady point.

**The optic is drawn, not authored.** `ui.ScopeOverlay` (a `Control` in `HUDManager.tscn`) draws the
black surround as an **annulus of quads** — a filled polygon cannot have a hole — plus the glass rim,
a mil-dot reticle and a centre dot, scaling to any resolution. A full-screen overlay rather than a
`SubViewport` scope is exactly what the first-person decision buys: the camera is already behind the
eye and already zoomed, so the glass shows what it renders and a render-to-texture scope would draw
the world a second time for the same picture. It is **self-gated** (it polls `scopedNow()` like
`WeaponProgress` polls the reload timer) and so is **not** in `HUDManager`'s `BASE_LAYOUT` table: a
scope is not a SITUATION — it comes and goes on the aim button and on every interruption — so the
table could only hold a stale answer. `Crosshair` hides itself on the same condition, for the same
reason (`HUDManager.refreshCrosshair` is edge-driven off the combat state, which is not an edge
that sees this).

Gate **`tools/godot/probe_sniper_scope.gd`**, 25/25, six cases: TPS → scope → release (camera on the
FPS rig and back, FOV **75.0 → 20.04 → 74.93** against a declared 20, head hidden and back, optic
shown and gone, `is_fps_mode` FALSE throughout); FPS → scope → release (first person throughout,
preference still TRUE, FOV back to its combat value); AR4 as the control (aiming moves the FOV to the
ordinary combat 59.0 and scopes nothing); and **three interruptions with the aim button still HELD** —
a weapon switch, sitting in a carrier, and death — each of which must leave the camera on the TPS
boom with the preference intact. `-- --control` reproduces the refused preference-writing
implementation: cases 1–3 still pass, and it **fails exactly the six interruption checks**, which is
the argument for the derivation stated as a measurement.

Two probe notes. The rig a frame is drawn from is **measured, not asked** — `ActiveCamera` is
compared with the TPS boom's `Proxy` and the FPS rig's `Pivot`, ~3 m apart, so there is no ambiguity.
And **the FOV baseline has to be taken after the camera has settled**: the aim-stay timer holds
combat for 0.5 s past the button and the combat/movement tween is another 0.5 s, so a short settle
reads the ordinary combat FOV and calls it a scope that did not zoom back (it cost two false
failures before the settle was lengthened). The optic itself was verified by rendering it on a real
display and looking at it — headless has no renderer, so a probe can only assert that it is on
screen.

**SR3's bolt and icon (2.7 pieces 6-7, 2026-09-16).** The bolt handle was island 3 of the one SR3 mesh
(36 verts at the receiver, 5 cm out to the right); it is its own `Bolt` object in `SR3.blend` now (transforms
applied, so `build_weapon.py` still accepts it) and `Model/Bolt` in the scene. `fire_animation = "bolt_cycle"`
(since W33: `bolt_work`, authored in the .blend, see below) (W13 — plays on the owner and every puppet) lifts it 60° about the bore,
draws it back 4 cm, runs it home and lowers it inside 0.9 s of the 1.46 s cycle. The throw is 4 cm, not an
AWP's ~10: with only the handle split out (no bolt body), a longer throw floats it over the stock wrist —
measured by rendering both poses. Gate `tools/godot/probe_sniper_bolt.gd` (60.0°, 0.039 m, home before the
next shot; `--control` no motion) — replaced by `probe_weapon_motion.gd` in W33.

### W33 — PART MOTION IS AUTHORED IN BLENDER; A SCOPE HAS ZOOM LEVELS; SNR1'S GRIP SITS LOWER (2026-09-16, user-asked)

**A weapon's moving parts are Blender actions on their own pivots.** SNR1's bolt used to be keyed in
`SNR1.tscn`, and because the part's origin was the weapon's grip, every key of a 60° lift about the bore
carried a hand-computed compensating translation. Now each part's origin IS its pivot (build rule: a part
not named `<id>` may carry its pivot as location; rotation 0 / scale 1), its motion is one action on an NLA
track, and the glTF import puts the clips on the model's own `AnimationPlayer`.
`WeaponItem.weaponAnimatorPath` now defaults to `Model/AnimationPlayer`, and `SNR1.tscn`'s `WeaponAnimator` is
gone. A per-shot index was also considered in CODE (a tween adding 60° a shot): rejected, because it is a new
mechanism for one weapon where W13's clip path already exists, and a 6-fold symmetric cylinder can use a plain
0 → 60° clip that restarts invisibly. The artist-facing rules are in `blender/WEAPON_AUTHORING.md` "Moving
parts". Five traps, each hit here and each now refused by `build_weapon.py`:
- **Godot strips a `loop`/`cycle` prefix or suffix from an imported clip name and loops it**, so
  `bolt_cycle` arrived as a looping `bolt`. The glTF was right and the scene named nothing. Renamed `bolt_work`;
  the build refuses a hinted name AND a clip the scene's `fire_animation`/`reload_animation` names that is
  missing from the export (`playMotion` is silent about it).
- **Keys on fractional frames are cut short**: glTF samples at the scene rate, and a 0.16 s cylinder key
  (frame 10.6) stopped at 58.8°. Weapon `.blend`s run at 60 fps with keys on whole frames.
- **NLA strip extrapolation `Nothing` resets the animated channels to 0 outside the strip**, so the part
  exported at the weapon origin. Use `Hold` (the first key is rest); the build reads the rest at frame 0.
- **`Hold` after the end leaves the file reading the LAST key** (the cylinder at −60°) if saved past the clip,
  which the transform check then refuses. The build reads the rest at frame 0.
- **Blender 5.2 actions are layered**: `action.fcurves` is gone, and a script that shifts keys through it
  silently changes nothing.

REV1: the split `CYLINDER` is `Cylinder` now, its two stray loose vertices (a leftover edge 5 cm behind it) are
removed, and its origin is on its axis (6-fold symmetric: 0.15 mm mean error under 60°). **A per-shot turn was
built and then REMOVED (user decision), because it could not be seen.** A 60° `cylinder_index` over frames 2–10
landed entirely under the muzzle flash and the 10° kick. Re-timed to 0.1–0.4 s it read only in 3x crops. From
the player's own FIRST-PERSON camera (`tools/godot/shot_fps_part.gd`, 1920x1080, aim held) the cylinder is
70–90 px across. It is seen from behind, where its rear face is a featureless hexagon, and a rim point moves
1–9 px a frame while the whole gun kicks. That matches industry practice: shooters with a separate first-person
viewmodel animate such parts there, and third-person world models mostly skip them. Here the character's own
body is the first-person view, and sound (a cylinder click) sells a revolver shot better. The split object and
its pivot stay, at no runtime cost, because a swing-out reload needs exactly that. Also keep the lesson: a
Blender session left open on the OLD `REV1.blend` saved over the authored file (22:27, back to `CYLINDER` on
the grip, no action) while the exported glb stayed correct. Close or revert a weapon `.blend` in Blender before
a tool rewrites it.
`pose_weapon_hold.py render` puts parts at rest before placing a weapon (a part otherwise follows the body clip's
frame) and gained `--closeup` (the firing hand from four sides, ~35 cm).
Gate **`tools/godot/probe_weapon_motion.gd`**: SNR1 lifts 60.0°, the knob rises 0.042 m, draws back 0.039 m and
is home by 1.46 s. `--control` (no clip): nothing moves. **Is a part motion worth shipping? Measure it from the
game camera first**: `tools/godot/shot_fps_part.gd -- --weapon=<id> --part=Model/<Part>` (needs a display) prints
the part's size on screen and pixels moved per frame and saves the frames. Under ~2 px a frame or ~20 px across,
it reads as still.

**A scope has two zoom levels, and the wheel or middle click TOGGLES it with nothing held (CS AWP / Left 4 Dead),
beside the held right-click scope (GTA).** `ScopeConfig.closeFov` (0 = one level; SNR1 7.5, CS's second zoom in
vertical degrees against a ~74 hip view; the first level stays 20, tighter than CS's ~31). The controls, by user
decision:
- **wheel up** (`scope_zoom_in`) steps IN from off: off → first → closer, stopping at the closer level;
- **wheel down** (`scope_zoom_out`) steps OUT: closer → first → off;
- **middle click** (`scope_zoom`) cycles first → closer → off, CS's AWP right click;
- **right-click hold** (`aim`) is still a scope for as long as it is held. Toggling while holding latches the next
  level, so letting go keeps it, and a toggle step to OFF while aim is still held wins until aim is released.

How the three references differ: CS's AWP right click cycles zoom1 → zoom2 → off and stays put. The bolt drops the
zoom and `resume_zoom` brings it back; a reload or a switch ends it. Left 4 Dead's snipers zoom on a middle-mouse
TOGGLE, because M2 is the shove. GTA V's sniper is HOLD to aim, with the wheel zooming continuously and a hold/toggle
option in settings. Here a toggled scope comes back after the bolt AND the reload (the user asked that it never exit
by itself, which is one step past CS). **The toggle is state that has to be remembered**
(`WeaponController.scopeLatched`, plus `holdSuppressed`), so every end is a CLEAR, not a hide. A switch, a drop or an
unscoped weapon clears it in `applyScopeZoom`. A seat or death clears it in `Character.tickScopeSway`, which the
camera calls every frame in every mode, because `applyInput` does not run in the driver's seat. Otherwise the scope
would pop back up on leaving the car or re-drawing the rifle. `PlayerController` counts a latched scope as aiming, so
combat stays on (the body faces the aim), and the aim-stay beat starts on the tick the toggle ends. `UserCommand.scopeZoom`
is a one-tick edge (`SCOPE_ZOOM_IN/OUT/CYCLE`). `scopeZoomLevel` resets whenever the scope is not raised. The bolt
cycle and the reload keep the scope RAISED (only the zoom drops), so it resumes at its level. `scopedFovDegrees()`
returns the level's FOV, and `TPSCameraController` re-tweens when that changes.
**Look input scales with the zoom** (`TPSCameraController.scopedSensitivityRatio`, CS's `zoom_sensitivity_ratio`,
default 1, 0 = off): mouse deltas × `min(1, ratio × camera fov / unscoped fov)` while raised, read off the live FOV.
This also slows the FIRST level (100 px: 7.00° raw → 2.55° at 20°). Without it the 7.5° level turns 1 px into
~6 screen px.
Gate `probe_sniper_scope.gd`, 77 checks: middle click scopes at level 1 with nothing held and stays up 3 s in combat;
click → closer; wheel up clamps; wheel down → first → OFF (back on the boom, FOV restored); wheel down while off
does nothing; wheel up from off scopes; the look scale (raw 7.000° control / 2.545° / 0.955°, ratio 0.375 = the FOV
ratio); the bolt and a reload each drop the zoom and it resumes at the closer level; the third click is off; hold +
click latches and survives letting go; with aim held the off step wins until aim is pressed again. The switch, seat
and death interruptions run for the HELD scope and again for the TOGGLED one. For the toggle the switch and the seat
are then undone, and the scope must stay down, with the latch cleared rather than hidden. `-- --control` still fails
exactly the 6 held-scope interruption checks. Probe trap: `ScopeConfig` is a SHARED sub-resource, and the bolt case's
`unscope_to_cycle = false` control leaked into every later SNR1 until it was restored.

**The "sinking" hand the user still saw was the SUPPORT hand**, found only with real-renderer screenshots
(`tools/godot/shot_weapon_hold.gd`, run WITH a display: a real Player armed through the pickup path, a camera
riding the weapon in its own frame, hold and aim poses plus frames of a part clip). SNR1's `SupportPoint` sat
**2.0 cm inside** the forend (y 0.055 against an underside at 0.035), so the left hand closed through the stock.
ASR1, ASR2 and SHG1 sit 3.4–5.1 cm UNDER theirs. It is 3.5 cm under now (y 0.0), and the grip miss went
0.012 → 0.010 m. No probe could see it, because they all measure the hand against the MARKER, never against the
mesh, so `build_weapon.py` now refuses a `support_grip: "under"` weapon (ASR1, ASR2, SHG1, SNR1 in
`weapon_models.json`) whose marker is not 2.5–6 cm below the gun's underside (control: y 0.055 → "−0.020 m",
exit 1). SMG1 (vertical foregrip) and the pistols are not "under" grips and are not checked. Lowering the
rifle's arm POSE was considered and rejected: the gun hangs from the hand, so a lower pose moves both together
and changes nothing between them.

**SNR1's grip sits 2 cm lower on the gun: the model moved UP in its .blend** (every mesh +0.02 m in Blender Z,
the bolt pivot 0.061 → 0.081, and every `SNR1.tscn` marker/collider +0.02 in Y). "Move the grip" and "move the
weapon up in Blender" are the same change, and the standard says to make it in the model, not with a
`GripPoint`. The thumbhole stock is thin, so the fist centred on the hole put the stock's lower edge through the
palm and the fingers through the stock. Close-ups swept +0 / +1.5 / +2.5 cm: at +2 the fingers wrap the grip's
underside with the trigger finger in the guard. Hand vertices inside the gun went 299 → 116, levelling off past
+2 (108 at +3). The non-closed low-poly meshes make those counts approximate, and ASR1 measures 323 at +0.
`grip_to_rear_m` is unchanged (a vertical move). In game the stock mount IK re-seats the butt pad on the pocket,
so the gun stays where it was and the HAND drops: the IK now moves the hand 0.026 m (ASR2's figure).
`probe_weapon_fit` PASS on both bodies and crouched (stock 0.000 m, support grip 0.012 m), `probe_weapon_holster`
PASS on both (slung muzzle corner 0.276 m off the ground, limit 0.25), and these pass too:
`probe_weapon_{scale,sockets,world_body,motion}`, `probe_sniper_{scope,hits,live}`, `probe_scope_sway`,
`probe_recoil_kick`, `probe_self_hit`, `probe_auto_reload`, `probe_support_hand_ik`, `probe_fps_camera` and
`./gradlew test`. Icons are byte-identical (fitted), and `WeaponLibrary.blend` was rebuilt.

**Weapon icons are GENERATED, one PNG per weapon, FITTED, barrel LEFT (2026-09-16, user decisions).**
`blender/tools/render_weapon_icons.py` renders every catalog weapon with a model (or a primitive, reported as a
PLACEHOLDER rectangle — ATL4, T1, MW2 today) to `assets/ui/weapons/<id>.png`, and the weapon scenes use those.
The spec is `weapon_catalog.json` `icon` (one owner for the tool and the test): an orthographic view of the
weapon's LEFT side with no tilt, so the barrel points LEFT (`side`/`muzzle`; the image is mirrored only if the
two disagree), flat white on transparent (the UI tints it), rendered at 4x and box-filtered, centred in a
**384x128** frame and FITTED to it with 6 px padding (`scale` "fit"). Fit, not true relative size, is the HUD
convention — kill feeds, weapon wheels and slot bars all size icons for legibility at ~20-44 px, and true
scale is for size-as-gameplay inventory grids; at one 330 px/m scale a grenade was ~10x8 px in the radial
slot. `scale` "uniform" + `pixels_per_metre` remain in the tool. The frame is 3:1 because the largest slot is
the radial menu's 133x44 and a TextureRect keeps aspect. Per-weapon files, not a sheet; the generated
`review/sheet.png` (.gdignore'd) is the contact sheet. `WeaponCatalogTest` asserts each icon: frame size,
white, centred, inside the padding, fitted (or, uniform, as wide as length x px/m), used by its scene. Try
variants: `-- --scale=uniform --side=right --muzzle=right --width=512 --out=<dir>`.

**The weapon wheel is UPRIGHT CARDS, selected by ANGLE (2026-09-16, user-asked).** `WeaponRadialMenu` places one
`WeaponRadialCard.tscn` per slot on a `ringRadiusX` x `ringRadiusY` ellipse (260x180 canvas units; slot 0 at the
top, clockwise), each card a 150x84 panel: the icon, its name pinned to the icon's bottom-right (CS-style), the
slot key on the left and the ammo on the right beneath, a `Highlight` panel for the selection. It replaced
textured pie wedges rotated into place with per-wedge click masks: a slot's content is rectangular, the wedges
squeezed it toward the centre, and the masks left dead spots. Selection is the pointer's ANGLE from the centre
past `deadZone` (48), each slot owning 360/N degrees — independent of the drawn shapes, which is the
weapon-wheel convention and what a stick would use too; opening warps the mouse to the centre and highlights the
weapon in hand, moving selects (and switches, as the wedge hover did), a click or releasing the key closes.
The wedge scene `RadiaMenuItem.tscn`, its unused copy and the wedge textures (`radial_menu*.png`, the click mask)
are deleted. The wheel used to label every slot one key too high (`weapon_slot_(N+1)`); the card now uses
WeaponSlotsUI's rule (slot 0 = `weapon_unequip`, slot N = `weapon_slot_N`).

**Text: one outline for the whole game, one size for the weapon menus.** `ui/game_theme.tres` is the project
theme (`gui/theme/custom`): a dark outline (size 3, black 85%) on every text-bearing control type — Label,
RichTextLabel, buttons, fields, lists, progress bars — in the HUD, menus and nameplate SubViewports alike; the
existing LabelSettings already carry their own outlines, and `AreaWarning`, the one hand-drawn string, calls
`drawStringOutline` first. `ui/weapon_menu_theme.tres` (10 pt for Label and RichTextLabel) is set on the wheel card
and the slot-bar row, replacing per-node size and outline overrides: 10 pt in the 1152x648 canvas is ~11 px on a
Steam Deck and ~17 px at 1080p, just above Valve's ~9 px readability floor. The slot icon is 36 px tall, and
WeaponSlotsUI moved up 56 px in HUDManager so its taller column clears the health box. Gate
**`tools/godot/probe_weapon_wheel.gd`** (runs with a display; `-- --shot=<png>` saves the open wheel and the closed
HUD): one card per slot, no overlaps, all on screen, pointing at every card selects its slot through the angle
function AND a real mouse-motion event, keys match the slot bar, the dead zone holds, all 42 wheel and slot-bar
texts are 10 pt with an outline, and a plain Label anywhere gets the theme outline.

**Weapon names: a 3-letter TYPE code + a series number (2026-09-16, user decision).** The code says what the
item IS: two words -> first two letters of the first + first letter of the second (SNiper Rifle = SNR, SHot
Gun = SHG, ASsault Rifle = ASR, MElee Weapon = MEW, FRag Grenade = FRG); one word -> its first three letters
(PIStol = PIS); three or more words -> initials (Anti-Tank Launcher = ATL). The number is a SERIES within the
type starting at 1 — never a real-world model number (those are exactly the designations that carry trademark
and association risk). `weapon_id`, file names, catalog rows and `.blend` collection names use the plain id
(`SNR1`); `weapon_name`, what players read, is hyphenated (`SNR-1`), the way CS separates `weapon_ak47` from the
"AK-47" it displays. `WeaponCatalogTest` enforces id == catalog id, id = letters+digits, name = hyphenated id.

| old | new | weapon |  | old | new | weapon |
|---|---|---|---|---|---|---|
| AR4 | **ASR1** | AK-pattern rifle |  | ATL4 | **ATL1** | launcher tube |
| AR212 | **ASR2** | AR-pattern carbine |  | T1 | **FRG1** | frag grenade |
| SG1 | **SHG1** | pump shotgun |  | MW1 (id was `MK1`) | **MEW1** | knife / bayonet |
| SR3 | **SNR1** | bolt sniper rifle |  | MW2 | **MEW2** | axe |
| PI52 | **PIS1** | pistol |  | (new) | **REV1** | revolver (hand cannon) |
| (new) | **SMG1** | submachine gun |  | | | |

Renamed everywhere live: scenes, stats, models (`.blend` collections/objects, re-exported `.glb`), icons,
projectile scenes and the class (`T1Projectile` -> `FRG1Projectile`, `ATL4Projectile.tscn` -> `ATL1Projectile.tscn`),
the catalog, `weapon_models.json`/`weapon_archetypes.json`, tools, probes, tests, README/CREDITS and the
weapon/aim authoring guides. **Sections of this file written before the rename keep the old ids** as the record
of what was built then, the district->zone precedent. Deliberately NOT renamed: the four melee attack CLIPS
(`attack_stab_mw1`, `attack_slash_mw1`, `attack_swing_mw2`, `attack_chop_mw2`) — renaming them means
re-exporting both character animation `.blend`s — and "T1" in the island/road planning tools, where it is a road tier.

**SR3 rendered WHITE in Godot — two Material Output nodes (2026-09-16, user-reported).** Every SR3 material
had an EEVEE-target output (Principled, right colour) and a Cycles-target output (Diffuse BSDF); the glTF
export carried no `baseColorFactor` for any of them, so Godot drew them white. Fixed in `SR3.blend` (one
output, target All, Principled only), and `build_weapon.py` now REFUSES an export in which any material has
neither a base colour factor nor a texture (control: the old .blend fails with the five names).

**REV-1 and SMG-1 (2026-09-16, user-asked).** Two raw Quaternius models (`Revolver_3`, `SubmachineGun_3`) were
normalised the way ASR-1 was: transforms applied, scaled to a reference length, muzzle turned to +Y, origin on the
firing fist (placed on a grid render), one output node per material. **SMG, not SUG:** written "sub-machine gun" it
is three words, so the initials rule gives SMG, which is also the abbreviation players already read (CS's buy-menu
category). A revolver gets its own type code (REV, one word) and shares the **pistol** grip archetype, the way SNR and
ASR both hold like a rifle.
- **REV1**: a Smith & Wesson Model 500 with an 8 3/8 in barrel, **0.381 m**, grip to rear 0.041 m. `Muzzle` (0, 0.085,
  −0.338); `SupportPoint` is PIS1's, the cupped support hand. Stats: a "hand cannon", 6 + 24 rounds, semi-auto at
  2 shots/s, damage 70 (two body hits, one head hit), recoil 3.0, a hard kick (0.03 m / 10°), bloom 0.9 per shot,
  2.5 s reload. Secondary slot, hip holster.
- **SMG1**: a B&T MP9 with the stock extended, **0.523 m**, grip to rear 0.244 m, rifle archetype. `StockPoint`
  (0, 0.0445, 0.244) on the rod stock's butt pad, `SupportPoint` (0, −0.01, −0.194) on the vertical foregrip, and
  `Muzzle` (0, 0.0615, −0.279). Stats modelled on the MP9's role: 14 shots/s full auto, 30 + 90 rounds, damage 14,
  low recoil (0.6), a 2.1 s reload, a fast 2.8 switch and `standing_speed_fraction` 0.5, so it stays accurate while
  moving more than a rifle does. Primary slot, back sling.

Measured: `probe_weapon_scale` (0.0% out on both), `probe_weapon_fit` on both bodies and crouched (REV1: gun on
the line, support grip 0.000 m; SMG1: stock on the anchor 0.000 m, grip 0.001 m, hand moved 0.039 m) and
`probe_weapon_holster` on both bodies (REV1 on the hip, 0.4% poke; SMG1 on the back sling, 3.1%). Also passing:
`probe_weapon_{sockets,world_body,archetypes}`, `probe_self_hit`, `probe_recoil_kick` and `./gradlew test`. Both
are in the catalog, the weapon library, the icon set and DebugWorld's pickup row.

**ASR-1's model was replaced (2026-09-16, user request: closer in style to ASR-2).** The AKMS with a folding
stock became a fixed-stock AKM (`AssaultRifle_5` from the same Quaternius pack), normalised the way SR3 was.
It was 5.422 raw units along +X, so it was scaled ×0.16230 to the AKM's **0.88 m**, turned so the muzzle is
+Y, and moved so the origin sits at the centre of the firing hand on the slanted pistol grip (raw x 0.02,
z 0.09, placed on a 0.1-unit grid render). Its materials had the same two Material Output nodes and were
fixed the same way; the new build check caught it. The grip-to-rear distance is now **0.263 m** (was 0.281
on the AKMS). Markers were read off ray casts through the mesh:
- `Muzzle` (0, 0.0826, −0.617)
- `StockPoint` (0, 0.020, 0.256): the pad is 1.3 cm lower and 2.5 cm shorter than the AKMS's
- `SupportPoint` unchanged: the magazine and the start of the handguard sit where the old model's did, to within 2 cm

The collider is the mesh's bounding box. The adopted rifle pose was built on the old stock, so the stock IK
now moves the hand **0.028 m** (ASR-2's is 0.026). Stock and support grip are 0.000 m off. Gates:
`probe_weapon_{scale,sockets,fit (both bodies, crouch),holster,world_body,archetypes}`, `probe_self_hit`,
`probe_recoil_kick`, `probe_switch_spin`, `probe_support_hand_ik`, `probe_character_variant` and
`./gradlew test` pass. The icon and `WeaponLibrary.blend` were regenerated.

### W30 — THE SCOPE DRIFTS, A HELD BREATH STEADIES IT, AND HOLDING TOO LONG COSTS MORE (2026-09-16, PLAN.md 2.7 piece 2)

**The drift is an OFFSET on the view, the same kind of thing as recoil.** `ControlRotation` gained
`swayPitch`/`swayYaw`, added by both rigs beside `recoilPitch`/`recoilYaw` and, like them, never
written into `yaw`/`pitch` — the mouse intent. So the player never fights the drift through the
mouse, letting go of the scope leaves the aim exactly where they put it, and because the offset
moves the camera it moves the `AimRay` that hangs off it: **the shot goes where the scope's centre
is**. A drift drawn over a still aim would be a picture that lies about the bullet.

**Engine-free `camera.ScopeSway` owns the rules** (unit-tested, `ScopeSwayTest` 11 cases):
- **Shape:** two incommensurate sines per axis — a slow figure-eight with a faster, smaller wander on
  top, so it cannot be timed by counting. Peak yaw is the weapon's amplitude, peak pitch 70% of it.
- **A LEVEL eased toward a target, never switched** (`FOLLOW_RATE` 5/s): 0 unscoped, 1 scoped,
  `HELD_LEVEL` 0.1 holding, `WINDED_LEVEL` 1.8 winded. The scope coming up starts the drift from rest
  and going down lets it settle, so nothing steps.
- **Breath is a 0..1 reserve.** Holding spends it over `holdSeconds`; running out winds the shooter
  until it is back to `WINDED_CLEARS_AT` (0.5), otherwise it refills over `recoverSeconds`. Winded is
  WORSE than never holding, which is what makes the breath a resource rather than a key you keep down.
- **A hold needs a fresh PRESS.** The key kept down through a winded spell does not silently start a
  second hold the moment it ends, and a key already down when the scope comes up is not a press.
  (That second case is `observeInput`: the at-rest ticks are skipped, and they must still record the
  key, or the first scoped tick reads a held Shift as a new press.)

**Who owns what.** The weapon says how far it wanders (`WeaponItem.scopeSwayDegrees()`, 0 = does not
sway; `SniperItem.scopeSway` 0.5 deg — 2.5% of a 20 deg picture). The breath is the BODY's
(`Character.breathHoldSeconds` 4.0, `breathRecoverSeconds` 5.0, and the `ScopeSway` state) — the
lungs are not the rifle's. So is the steadiness, a multiplier from the stance (upright 1.0, crouch
0.6, crawl 0.35, airborne or swimming 2.0; the same ordering as `FirearmItem`'s stance spread with
prone further apart). `Character.tickScopeSway` is called by `TPSCameraController._physicsProcess`
beside the recoil decay, because that node gets a frame in every mode and the Character's own
`_physicsProcess` does not (the driver's seat switches it off). Nothing is latched: every way out of
the scope eases the level to 0. An unscoped body at rest returns before the steadiness read, which is
an engine call (`isOnFloor`) not worth paying on every AI rig every frame.

**SR3 ships with `scopeSway = 0`** (W31, user decision: a still, CS-style scope; 0.5 deg read as an idle
bob that moved the shot). The mechanism stays opt-in per weapon, and its gate sets 0.5 on the pair.

**Input:** `UserCommand.holdBreath` from a new `hold_breath` action, bound to Shift. That is the
stealth-walk key too, which is CoD's binding and harmless: a shooter steadying a scope is not running.
It is its own action so it can be rebound. No HUD for the breath yet — CoD and PUBG signal it with
audio, and a breath sound is the natural next addition.

**THE GATE IS PAIRED, because the drift is a wave.** Measured one window after another, "the drift was
smaller while the breath was held" compares two different stretches of the same wave, and a quiet
stretch reads as a working breath. `tools/godot/probe_scope_sway.gd` drives TWO Players from the same
`Input` on the same frames, both scoping on the same frame, so their phase clocks are identical. They
differ in one thing: A cannot hold its breath (`breath_hold_seconds` ~0 winds it for one tick and it
recovers the next). Every breath assertion is a ratio B/A over the same frames, so the wave cancels.
The first window, where neither holds, must read 1.00, which checks that the pairing is real. The
drift is read off the CAMERA against a rest direction recorded before scoping (both in first person,
so the rig does not change), never off the helper's numbers. **17/17:**
- open peak yaw 0.491 / pitch 0.333 against 0.50 / 0.35, pair ratio **1.000**;
- the aim target on the view line (0.0000 deg) AND on the wall 40 m out, **0.353 m** off the rest
  line. The first alone is a tautology of `AimTarget` hanging off the camera;
- held B/A **0.102**, breath 0.81 -> 0.31;
- winded at **4.02 s** (declared 4.0), then B/A **1.793**;
- no second hold with the key still down, a fresh press holds;
- both views back on rest (0.0000 deg) after letting go of aim.

`-- --control` (both rifles `scope_sway = 0`) fails 5.

Unchanged: `probe_sniper_scope` 25/25, `probe_fps_camera`, `probe_self_hit`, `probe_vehicle_views`,
`probe_driveby_aim`, `probe_recoil_kick`, `probe_auto_reload` PASS; AimDebugAuto 40/40; `World.tscn`
0 errors; `./gradlew test` green.

### W31 — A SNIPER SHOT GOES WHERE THE SCOPE IS; THE BOLT AND THE RELOAD LEAVE THE EYE (2026-09-16, user-reported)

"Hit the enemy but it seems not hit, it dies later, or needs several shots — distance?" Measured with a
new gate, **`tools/godot/probe_sniper_hits.gd`**: still AI at 30/60/120/260 m, the level scope line on
the head, chest or belly, on the body or 0.40 m beside it, one shot each through real Input. Before:
**12 of 24** on-body shots registered, several on the WRONG bone (scope on the head -> 112.5, on the
chest -> 75, beside the head -> 600). Two causes, separated by controls:

- **Bloom was added BEFORE the shot** (`FirearmItem.useWeapon`), so each round carried its own
  per-shot bloom. SR3's is 0.6 deg, so every "0.005 deg" shot left a **0.605 deg** cone, ~0.6 m of
  scatter at 120 m. AR4's is 0.05 deg, which is why no other gun showed it. It is added after
  `fireShot()` now. Control (bloom first, everything else fixed): **4/24**.
- **The muzzle leg at long range.** With bloom fixed and the two-stage trace kept for scoped shots:
  **22/24**, both misses at 260 m landing a bone low. A scoped shot is now ONE leg from the scope
  (`FirearmItem.useMuzzleTrace` refuses while `Character.isScopeRaised()`; user decision, CS/PUBG).
  The eye is inside the head, so cover still blocks it, and the host re-runs its chest-to-origin cover
  test on the reported eye.

After both: **24/24 on the right bone, 12/12 beside the body clean misses**, stable across runs. The
gate zeroes SR3's base spread so a scope line on a bone boundary is not a coin toss on the 1 cm cone at
260 m, and leaves bloom as shipped so the bloom defect would still fail it. "Dies much later by itself"
was not reproduced separately: a shot whose damage lands on no bone, or on a leg, reads exactly like it.

**The scope is still** (`SniperItem.scopeSway` ships 0; W30's mechanism is opt-in).

**The bolt and the reload leave the eye, and aim held brings it back** (PLAN.md 2.7 piece 4, user
decision: CS AWP with resume-zoom, the balance lever for a one-shot rifle). Two derived facts now,
because two different things ask:
- **raised** — `WeaponController.scopeRaisedNow()` / `Character.isScopeRaised()`: aim held on a scoped
  weapon, no switch, alive, on foot. The FIRST-PERSON VIEW and the SHOT ORIGIN follow it. A TPS player
  stays behind the eye through the cycle instead of flicking to the boom and back each shot. The shot
  that starts the cycle is still a scoped one, which matters because `onWeaponFire` starts the fire
  timer BEFORE `useWeapon` resolves the shot.
- **scoped** — `scopedNow()` / `isScoped()`: raised, and not (a weapon that `unscopesToCycle()` with
  its fire timer or reload timer running). The ZOOM, the OPTIC and the hidden crosshair follow it.

The fire timer IS the bolt cycle (a bolt action is `auto = false` + `fireRate`) and the reload timer
IS the reload, so there is no re-scope bookkeeping. `SniperItem.unscopeToCycle` (default true) is the
per-weapon switch. The timer is also started by a pickup's equip block and the draw settle, so the zoom
waits those out too. That is the overloading PLAN.md 2.8 names.

`ScopeOverlay` and `Crosshair` now ask `Character.isScoped()` (the answer the camera and the head use),
not the weapon controller, which does not know the body died or sat down.

Gates: `probe_sniper_hits` 24/24 + 12/12. `probe_sniper_scope` gains the bolt/reload case: zoom and
optic drop on the shot with the view still first person, back at 20 deg after the 1.46 s bolt and
after the reload, third person if aim is let go mid-cycle; control `unscope_to_cycle = false` stays
zoomed. Also PASS: `probe_scope_sway` 17/17, `probe_self_hit`, `probe_auto_reload`,
`probe_recoil_kick`, `probe_fps_camera`, `probe_vehicle_views`, `probe_driveby_aim`, `probe_melee`,
`probe_weapon_fit`, `tools/net/run_net_shot_test.sh`, AimDebugAuto 40/40, `./gradlew test`,
`World.tscn` 0 errors.

### W32 — ONE ACCURACY OWNER, A SCOPE BY COMPOSITION, SCOPED MOVEMENT, AND A CONFIRMED HIT MARKER (2026-09-16, PLAN.md 2.8 items 3, 4, 9, 10)

The study behind W31 found every remaining miss was a MOVING or JUST-STOPPED shot: the scope did not
slow the player (7.98 m/s), the cone grew 0.03°/m/s from zero with no standing dead zone, and the body
slid ~0.5 s after the key was released. Four changes, each on the owner that the architecture review
asked for first.

- **`weapon.Accuracy` (item 3)** — see "Spread formula". The standing threshold is the CS rule (fully
  accurate below 34% of max speed), expressed as a FRACTION so a scoped slowdown lowers it too.
- **`weapon.ScopeConfig` (item 4)** — a read-only Resource on `FirearmItem.scope` (fov, zoomSeconds,
  sway, unscopeToCycle, moveSpeedFactor, stopAccelerationFactor). `WeaponItem.scopeConfig()` replaces
  the four base-class hooks that returned 0/false, so any firearm with a config is scoped and
  `SniperItem` is DELETED: SR3 is a `FirearmItem` with `hipfire_spread_multiplier = 8` and an embedded
  config. `WeaponController.heldScope()` is the one reader (a config with fov 0 is no scope); the
  camera, the sway and `scopedNow` read through it. Probes that tuned the old exports now set
  `gun.get("scope").set(...)` — the config is a SHARED sub-resource, so a probe that changes it changes
  every SR3.
- **Scoped movement (item 4)** — `MovementController` multiplies the target speed by
  `Character.scopeMoveSpeedFactor()` and, with no wish direction, the acceleration by
  `scopeStopAccelerationFactor()`, every frame (the scope comes and goes without a movement-state
  change). SR3 ships **0.4** (CS: AWP scoped 100 u/s = 40% of the 250 u/s knife speed; this game's
  weapons do not slow the runner) and **3.0** (the counter-strafe stop: ~0.1 s to accurate instead of
  ~0.5 s). Both numbers were the user's call and are recorded on the config for them to retune.
- **Hit marker (item 9)** — `EventBus.damageDealt(attackerId, damage, headshot, killed)`, emitted by
  `Health.applyDamage` where damage is APPLIED, and re-emitted on a client from `MSG_DAMAGE_BROADCAST`,
  which now carries the attacker id and a headshot/killed flag byte. So the marker is CONFIRMED, never
  predicted. The attacker id is threaded `WeaponItem.resolveAttackerId()` → `ImpactManager.processHit`
  → `Health.takeDamage` (new overloads; the old ones pass ""). Explosions still pass no id (no marker
  for a rocket kill yet). `ui.HitMarker` (self-gated, not in `BASE_LAYOUT`) draws an X at screen centre,
  red and held twice as long on a kill, larger on a headshot, with a generated 45 ms tick (no asset).

- **`weapon.WeaponState` (item 2)** — `fireTimer` meant four things (fire interval, draw settle, pickup
  equip block, merge-pickup block) and the scope keyed off all of them. `startFireLock(seconds, reason)`
  is now its only writer, `state()` resolves SWITCHING > RELOADING > the lock's reason > IDLE
  (`WeaponStateTest`), and `scopedNow` drops the zoom only for CYCLING or RELOADING — a draw settle no
  longer blinks the scope. `weaponStateNow()` is the registered readout.

- **`WeaponStats` (item 1)** — every weapon's tuning (spread, bloom, reload/switch/fire rates, auto, magazine
  size, reserve max, recoil, damage, the W27 kick, range, pellets, hipfire, standing threshold) lives in
  `weapon/stats/<id>.tres`, generated from each weapon's effective values (field defaults + constructor +
  scene lines) so nothing changed. `WeaponItem.setStats` copies it onto the fields, which are `@Visible`
  now: registered, so probes still read and nudge them, but no longer stored in the scene. Live STATE
  (`magazine`, `reserve`) stays on the scene.
- **`WeaponController` split (item 5)** — `WeaponSockets` (hand/holster/stow placement),
  `WeaponInventorySync` (MSG_INVENTORY build + reconcile) and `RemoteWeaponCues` (a puppet's replayed
  fire/reload cosmetics) are plain-Java collaborators now, 1592 → 1311 lines, behaviour unchanged (net
  shot/melee/launch gates green). The fire/reload/switch state machine stays: it is the controller's job.
- **Stateless traces (item 6)** — `WeaponItem.trace` is an `intersect_ray` with the AimRay's mask, flags
  and exclusions, and no longer moves the ray node (or the `AimTarget` under it). `RayCast3D` cannot list
  its exceptions, so `util.RayExclusions` is the one place they are added/removed (every former
  `aimRay.addException` site) and read back; it is cleared from `GameManager._exitTree`.
- **One weapon catalog (item 7)** — `weapon/weapon_catalog.json` is THE list (id, scene, archetype,
  bench). `AimDebugHost`'s bench, `probe_weapon_fit` / `probe_weapon_holster` and
  `pose_weapon_hold.py` read it; `weapon_archetypes.json` lost `weapon_assignments` and every
  `holds.*.weapons` (a hold covers the catalog rows of its archetype).
- **Archetype by name (item 8)** — scenes store `weapon_archetype = "rifle"`; `WeaponItem.weaponPoseIndex()`
  derives the blend index from `weapon.GripArchetype` (still append-only; an unknown name warns once and
  poses as a pistol). `WeaponCatalogTest` (4) holds all of it together: the enum mirrors
  `weapon_archetypes.json`, every catalog scene exists and stores its archetype by name, no weapon scene
  is missing from the catalog, and `weapon_models.json` / the holds name only catalog weapons.

`probe_weapon_fit.gd -- --stance=swim` (A2.5) builds a 3.5 m pool under the stands: every body swims and
every held weapon sits on the aim line (0.0° on all six); the stock is not mounted while swimming, by design.

**Gates.** `AccuracyTest` 10/10, `WeaponStateTest` 2/2, `WeaponCatalogTest` 4/4; `probe_sniper_scope.gd` asserts the named
CYCLING/RELOADING states and that the 5-frame draw settle keeps the zoom. `tools/godot/probe_hit_marker.gd` 6/6 (a hit shows it, a miss and
another attacker's damage do not, a kill is flagged). `tools/net/run_net_shot_test.sh` gained
`hit_confirmed_local` (the client's hits are confirmed by the host; an observer gets none).
**`tools/godot/probe_sniper_live.gd` is now a gate (item 10)**: every stationary and just-stopped HEAD
and CHEST shot on the aimed bone (48/48), limbs ≥ 90% (69/72), scoped move speed **3.20 m/s**, a moving
scoped cone **0.101°** (20× base), hitboxes on the drawn body (0.000 m); `-- --control` (threshold 0, no scoped slowdown, the ordinary stop) fails 3 — stopped chest shots 3/6, limbs 63/72, speed 8.00. Three probe defects it had to
lose first, each of which read as a game bug: the moving case fired on the first frame of acceleration
(0.21 m/s), the run-ups walked the player ~180 m sideways so later shots met the target's own arm in
front of its chest, and a teleport back left the camera rigs settling for a second. **Limbs are held to
90%, not 100%, on purpose:** a 3 cm-radius arm capsule at 260 m against the cone's own 1.1 cm radius
plus ~1 cm of steering error is a genuine graze (the capsules were measured colliding where drawn, hit
centroids within 2 cm) — the old 90/90 was a lucky seed.

## Godot-JVM Specifics

- **Annotations (godot-jvm `1.0.0-rc1` API — the older `@Register*` family is gone).** The plugin runs in the
  default `Inferred` mode, where an annotation implies what it needs:

  | intent | annotation | replaced |
  |:--|:--|:--|
  | expose a class as a Godot script | `@Script` / `@Script(className = "X")` | `@RegisterClass` |
  | let Godot call an ordinary method | `@Register` | `@RegisterFunction` |
  | show/edit a property in the Inspector | `@Export` (alone — it implies registration) | `@RegisterProperty` + `@Export` |
  | register a property without exporting it | `@Visible` | bare `@RegisterProperty` |
  | name a signal's arguments | `@Emit(parameters = {…})` (optional) | `@RegisterSignal` |

  In **Java** `@Script`'s element is `className` — `@Script("X")` does not compile (Java has no
  positional annotation arguments), it must be `@Script(className = "X")`. Do not use
  `import godot.annotation.*;` alongside `import godot.api.*;`: **`godot.api.Script` exists**, and
  two on-demand imports make `@Script` ambiguous. Import the annotations explicitly.
- Signal declarations: `Signal0 / Signal1<T> / … / Signal7<…>` declared as `public final` fields —
  **registered automatically**, no annotation. The registrar names the signal after the *field*
  (`playerDied` → `player_died`, via `convertToSnakeCase`), which is why the field name and the
  `new StringName("player_died")` handed to the constructor must stay in sync.
- **A Java field and its JavaBean accessors are ONE property.** godot-jvm's language adapter merges
  `public T x` with `getX`/`isX`/`setX` into a single logical property and then binds it *through
  the accessors*. Consequences, each of which bit this codebase during the 4.7 upgrade:
  - A **getter-only** exported property is registered `READ_ONLY` (and its generated registrar does
    not even compile) — the scene/`.tres` value would never reach the object. Every `@Export` field
    with an accessor must have **both** halves; `Crosshair.showCrosshair` and `Door.locked` gained a
    getter, and ~50 tuning fields (`MovementState`, `SwimState`, `VehicleRoute`, …) gained a setter.
  - A **convenience method that merely looks like a getter** silently hijacks the property. Three
    were renamed rather than completed, because their return value is not the field's:
    `AICharacter.behaviorConfigOrDefaults()` (falls back to shared DEFAULTS),
    `WeaponItem.resolveSlotType()` and `HittableBody.resolveSurfaceType()` (enum views of an
    `int`/`String` field). Name a derived reader `resolveX()`/`xOrDefaults()`, never `getX()`.
  - A **registered method must not be overloaded** — the registrar emits a bare `Class::method`
    reference, which is ambiguous in Kotlin. `WorldBaker.bake()` / `WorldPreviewBuilder.buildPreview()`
    keep the no-arg registered form; their static helpers are `bakeScene(…)` / `buildPreviewScene(…)`.
- Class registration is byte-compatible across package moves: `@Script(className=…)` is
  an explicit string (and the default is the simple class name), both package-independent — so the
  `com.openworld.*` reorg did not change any registered type name.
- Always run `./gradlew build` before opening the editor so registration is up to date.
- `GD.lerp`, `GD.lerpAngle`, `GD.clamp`, `GD.randf`, `GD.randfRange` are the GDScript global equivalents.
- `StringName` is used for signal names and node lookups; `NodePath` for node paths.

---

## Road Kit — option B: author in Godot, solve and mesh in python3 (2026-09-13; no Blender since B11, 2026-09-16)

Supersedes road-generator, which is now removed (PLAN.md 3.1; see the section below). The Blender road kit's
solver was kept and its authoring moved into the Godot editor, where zones, Terrain3D and building
scenes live. **Three owners, one contract (`.roads.json`, the kit's `point_model` schema, Z-up):**

| layer | where | what |
|---|---|---|
| authoring | `addons/road_kit/` (GDScript editor plugin) | `RoadKitNetwork` → `RoadKitRoad` → `RoadKitPoint` nodes; a road's CHILD ORDER is its chain; links by uid; the dock's gestures (`road_kit_gestures.gd`, pure functions, headless-testable); overlay of the solver's resolved centrelines; undo = restore the record |
| rules | `blender/tools/roadkit_cli.py` (plain python3) | `validate`, `setback`, `centrelines`, `lanekit`, `ramp` over the record, using the kit's existing pure modules — no Blender |
| meshes | `blender/tools/roadkit_cli.py gltf` (plain python3, B11) | `point_mesh` sweeps, `point_gltf` writes the piece `.gltf`, then `GLTF_READY=1 build_piece.sh` bakes it (WorldBaker, NavBaker); `build_roads_piece.sh <record> <Piece>` runs every step. Until B11 this was headless Blender (`roadkit_build_mesh.py` + `point_build`, deleted) |

Rules that came with it, each measured:
- **The field table is GENERATED** into `road_kit_fields.gd` (`blender/tools/gen_roadkit_godot_fields.py`,
  `--check` fails when stale). A second hand-copied table is the drift the kit's own field-table rule
  exists to prevent.
- **Coordinates convert in ONE GDScript place** (`road_kit_frame.gd`, kit `(x,y,z)` → Godot
  `(x,z,-y)`, mirroring `point_export.godot`). Record positions are in the NETWORK node's frame,
  composed from local transforms, so import/export works outside the scene tree. Gate:
  `test_roadkit_record.gd` + `compare_roads_records.py` — 0 differences on the sample network, and
  the lanekit from the Godot-written record equals Blender's export (worst delta 0.0).
- **Solver facts are never re-derived in GDScript.** A ramp's mouth position, carriageway and taper
  opening are `roadkit_cli.py ramp` (a port of `Make Ramp` + `open_aux_slot` + `Align Ramp To Aux`
  over the record); the GDScript `make_ramp` that guessed them was deleted.
- **Sibling scripts are referenced by PRELOAD, never by `class_name`.** A headless `--script` run
  and a fresh checkout have no global class cache; a `class_name` type hint then fails to parse and
  the script is dead (read as a hang, since the error aborts before `quit()`). Parse-check addon files
  with `godot --headless --check-only --script res://<file>` — verified to catch a strict-typing error.
- **Ground heights come from Terrain3D** (`Gestures.sample_ground`, before every service call), and
  must be the NATURAL ground: stamping road corridors into the height map comes after sampling, or
  the kit's CARVED_FLAG trap returns. Blender keeps a record height when its scene has no terrain.
- Gates: `test_roadkit_record.gd`, `test_roadkit_gestures.gd` (16/16 — a gesture-authored network
  passes the kit's gate with 0 errors and exports 34 lanes), `test_roadkit_ground.gd` (3/3).
  Still to build (PLAN.md 3.1): corridor stamp into Terrain3D (B7), the remaining gestures and
  gizmos (B8), retiring the Blender authoring UI (B9).

**Zones (B6, 2026-09-13): author ONE network, let the build cut it.** The dock's Build writes the
scene's ZoneMarkers to `<stem>.zones.json` (`road_kit_zones.gd`: each centre in the NETWORK's frame,
kit axes, `Zone.size`'s XZ footprint as the box) and `build_roads_piece.sh <record> Roads_<net>
<zones.json>` builds one piece per zone. `point_zones.py` is the ONE owner of the cut, asked by both
the lane export (`roadkit_cli.py pieces`) and the mesh build (`point_build.build_network(part=,
zone=)`), so tarmac and lanes cannot land in different pieces. Rules: a station is in the SMALLEST
box containing it, else the nearest centre within `load_radius`; a **RUN** (not a road — a long
arterial is cut at its own crossings, never mid-carriageway) takes its road's authored `zone_id` if
that names a marker (else reported `zone_id_unknown` and derived), else its stations' majority; a
pad goes with its clique centre; a gore with its ramp's run; anything in no zone goes to the
resident piece `Roads_<net>`, which is exactly the old single-piece build. The **whole** network is
still solved per piece — a kerb beside a ramp is a fact about both roads — and only emission is
filtered: measured on the sample, 81 objects = 52 + 29, every one byte-identical in vertex count and
position sum to the unzoned build, and the unzoned lanekit is unchanged byte for byte. A lane's
`zone_id` is its zone, so a `VehicleSpawnConfig.route_name` of the zone id spawns on exactly that
zone's lanes (`ZoneManager.spawnLanes`' zone-id pass). Successor names cross pieces untouched; the
lane registry is global, so they resolve whenever both pieces are loaded.
- **A cut piece is placed in the NETWORK's frame, not its marker's.** `ZoneManager` parents a zone's
  geometry under the marker, which is right for a district authored about its own centre and put the
  sample's pieces **1403.6 m** off (the probe's control). `Zone.geometryWorldPlaced` +
  `geometryWorldTransform` (written by the dock from the network's global transform) and
  `Zone.placeGeometry` — the one placement rule, used by the streamed tier, the LOD-low tier and
  `WorldPreviewBuilder` — so dragging a marker never drags the road. Moving the NETWORK needs a Build.
- **Wiring** (`plan_wiring`, one undo step): a Zone takes its piece's scene path and the placement; a
  Zone already streaming something that is not one of this network's pieces keeps it and is reported
  (one geometry per zone); a Zone whose road piece this build did not produce is CLEARED, so a stale
  piece file cannot stream roads that are gone; the resident piece is reported, never silently lost.
- Gates: `point_zones.py` self-test (in `check_roads.sh`, now 19), `test_roadkit_zones.gd` (17/17 with
  a build log: the committed `hosts/RoadKitZones.tscn` needs ZERO wiring changes), and
  **`probe_road_zones.gd`** (12/12): both pieces stream and sit at the network's transform, every lane
  starts where its lanekit says (0.0000 m), every successor resolves with both loaded, a car hands
  over from the west pad's connector onto an east lane, walking away unloads west and leaves exactly
  the 6 east→west successors unresolved, and walking back resolves them all. `-- --control` (marker
  frame) fails 4 of them.

**Ground (B6b, 2026-09-14): a support stands on the ground under EACH SAMPLE, and the ground is
Terrain3D's.** The kit decides NONE/FILL/PIER every 4 m from `surface_z − ground_z`
(`point_solve.solve_road`) with `ground_fn` as the sampler — a raycast into the Blender scene. A road
authored in Godot is built in a Blender session with NO terrain, so every sample missed and fell back
to a lerp of its stations' `ground_z`: DebugRoads' `link` (3 stations, 20.9 m over the gap the user
dug between the islands) had **no support at all** — its stations were draped to the old ground, so
the lerp read 0.1 m everywhere. Now the dock's Build (and `tools/godot/write_roadkit_ground.gd`)
samples Terrain3D on a 2 m grid over the network's footprint + 60 m (`road_kit_ground.gd`, network
frame, kit axes, float32 `<stem>.ground.bin` + `<stem>.ground.json`; 424×180 in 58 ms), and
`point_ground.GroundGrid` — bilinear, a NaN cell or the outside is a MISS (None), never 0 — is passed
as `build_network(ground=)` (`rka.point_build(ground_path=)`, then `roadkit_build_mesh.py --ground`; since B11 `point_mesh.build(ground=)` / `roadkit_cli.py gltf --ground`,
`build_roads_piece.sh`'s 4th argument). The road's own heights are NOT re-draped: the support is
derived from the gap, which is the point. Rules:
- **The kit sweeps no embankment.** `road_support` sizes a FILL toe and nothing builds it, so a road
  0.4–4 m over the ground floats until the terrain carries it (B7's stamp). The gate reports FILL
  (120 samples on DebugRoads, mostly `spur`) and does not assert it.
- **A span over a cliff edge is carried by the edge.** Pillars are laid at `PIER_SPACING` along the
  carrier, so the first column can be 30 m in from where the ground falls away; the gate accepts a
  PIER sample within 18 m of a column foot on the terrain OR of ground rising to within `FILL_MAX` of
  the deck.
- `write_roadkit_ground.gd` also re-samples each station's `ground_z` into the record, as every dock
  service call does (a pad reads its mouths' station ground); on DebugRoads that moved exactly one
  station, link's middle one, 10.36 → −10.40.
- `<stem>.ground.bin` is un-ignored (`.gitignore` ignores `*.bin`) and LFS-tracked: once B7 has
  stamped a network it is the ONLY record of the natural ground under its roads.
- The grid is snapped to multiples of its step in the network frame, so on an unrotated network every
  sample IS a Terrain3D vertex (2 m) and B7's restore is exact.
- Gate **`tools/godot/probe_road_ground.gd`** (instances every ZoneMarker's road piece where
  `Zone.placeGeometry` puts it, walks every lane every 4 m against Terrain3D, reads column feet off the
  baked `__surface` meshes): **213/213** pier samples supported, no column stopping short of the
  ground; the same pieces built without the sidecar: **111/213**. `probe_traffic_spawn.gd` 6/6
  (a car still drives `link`), `probe_road_zones.gd` 12/12, `check_roads.sh` PASS=20.

**Seeing it while editing (B6c, 2026-09-14).** A built road is instanced by `ZoneManager` at runtime
and a `ZoneMarker`'s box is runtime-only too, so the editor showed neither. The dock's **Preview
Pieces** (`road_kit_preview.gd`) instances every Zone's `geometry_path` (plus a resident
`Roads_<network>` piece) under ONE `top_level`, UNOWNED node, placed by `Zone.placeGeometry`'s rule
re-stated in GDScript (the Java is not `@Tool`); an unowned node is not written by `PackedScene.pack`,
and the gate proves it with a control that gives the node an owner. It re-reads the scenes
(`CACHE_MODE_REPLACE`) after each Build. **Refresh Preview** now passes `--zones` (written to
`user://`, never over the build's own sidecar) and `roadkit_cli.py centrelines` answers per run
`zone`/`beyond` and the `cross` successor lanes from `point_zones` — the overlay colours, never
decides. Gate `test_roadkit_preview.gd` 12/12; how-to in `addons/road_kit/README.md`.

**The roads are written into Terrain3D (B7, 2026-09-14): carve AND fill, derived from the natural
ground.** `road_kit_stamp.gd` (dock **Stamp Terrain / Restore Terrain**, headless
`tools/godot/stamp_roadkit_terrain.gd`) sets every terrain vertex near a road from the network's
natural-ground sidecar and `roadkit_cli.py corridors` — `point_edges.band_corridors` (moved out of
`point_build` with `solve_all`, which alias them, so the CLI needs no bpy), each point carrying the
natural ground and `road_support.support_kind`. Inside a corridor's paved half-width + `VERGE` (6 m:
a 4 m footway + one 2 m cell) the ground is the road surface − 5 cm; outside, a 1:1 cut batter and a
1:1.5 fill batter. Rules, each a measured defect first:
- **FILL, where the island's `Carve` is carve-only.** Its reason — "`road_support` owns FILL and builds
  the embankment" — is false in the kit: `rka_fill_w` is computed and nothing sweeps it. A Terrain3D
  world's height field is the only thing that can carry a road 0.4–4 m up. The bay-fill hazard is kept
  away by classification: a corridor point may fill only if it is not PIER/TUNNEL (the nearer end of
  a segment decides).
- **A fill batter runs until it meets the ground**, never to a fixed toe (a toe cut-off stood a
  20.8 m wall beside DebugRoads), and **only the NEAREST corridor fills** (the max of every corridor's
  floor spilled the last fill before a bridge 30 m under the deck: 116 of 199 clear-span samples
  buried → 2).
- **Each corridor is its nearest segment.** Every segment in reach measured a graded road's further
  segments from their end caps and capped the ground at the lowest (0.75 m of air under `loop`).
- **On a road the road decides; off every road the batters do.** In a band the ground is the nearest
  corridor's surface, capped by any corridor within one terrain CELL of standing on it or more than
  `UNDERPASS` (3 m) below (a street under a deck) — a hairpin's lower leg must not cut under the
  upper leg, a junction's lower approach not under the pad.
- **`band_corridors` had never included a pad**, though its docstring said so: a pad band is a ring
  plus mouths, so `len(poly) == 2 * len(spine)` skipped every one. `_pad_corridors` fans spokes from
  the centre to a ring resampled at 3 m (spokes to the raw ring let a 18 m cap edge claim 9 m of the
  approach road), heights by `point_solve._idw_z` along each spoke. This also changes the island
  carve's input (`build_island_base`), which has not been rebuilt since.
- **Idempotent by construction and reversible:** heights derive from the natural sidecar, the vertices
  the previous stamp reached (`<stem>.stamp.json`) are re-derived too, and a stamp record makes
  `road_kit_ground` read the sidecar as the ground where it covers (the CARVED_FLAG trap), and refuse
  to sample at all if the record exists and the sidecar does not. Restore puts the natural ground back
  and deletes the record.
- Gate **`tools/godot/probe_road_stamp.gd`** on the saved DebugWorld terrain: no ground proud of any
  lane (0.05 m) or pad mesh vertex (0.15 m) — 0; every lane the kit calls FILL at grade on the stamped
  ground 132/132 (natural ground, the control: 0/132); clear-PIER samples still over the natural ground
  190/192; stamping again changes 0 vertices; restore worst 0.0000 m. 14 103 vertices touched (raise
  histogram ≤4 m 3369, 4–8 m 1384, 8–16 m 322, >16 m 56 — the abutment spill cones). B6b's
  `probe_road_ground.gd` still passes on the stamped terrain (202/202). `check_world_envelope.gd`'s
  "mesh box matches the collision box" FAIL on DebugWorld is pre-existing (same on the unstamped terrain).

**The remaining gestures (B8, 2026-09-14).** Every rule that is not a plain node edit lives once, in
`blender/addons/road_kit_authoring/point_record_ops.py` over `NetworkData` (pure python3, self-tested,
in `check_roads.sh`), reached through `roadkit_cli.py merge|split|renumber|repair|tidy|cross_section|
branch_ramp|facings|flow`; the dock runs each as `Service.record_gesture` — save (promoting rotated
points), run, reload, face — in ONE undo step. B9 retires the Blender operators these restate, so this
module is the owner. The Preview panel's flow report moved to pure `point_flow.py` (`point_preview`
imports it back). Rules that came with it:
- **Rotation is the bend gesture in Godot too.** `RoadKitPoint.auto_facing` is the facing the tool gave
  (stamped by `face()` from `roadkit_cli.py facings` = `point_profile.chain_facings`, and at birth);
  `to_record` promotes an AUTO point turned more than `ROTATED_TOL_DEG` (0.5°, now generated into
  `road_kit_fields.gd` with `MASK_GROUPS`) from it to MANUAL. A drag leaves the basis alone, so it can
  never read as a rotation — the gate's control. A point loaded from the record has no facing until the
  plugin faces it, which every refresh does.
- **A record gesture reloads the network, so node references do not survive it** — carry uids.
- **`point_model.link_order` reversed a road whose HEAD was dragged to the tail**: it started at the end
  that sorts first, which is then the old tail, so Renumber handed the chain back backwards and swapped
  what `lanes_fwd`/`lanes_bwd` mean on every station. The orientation agreeing with more of the current
  order now wins (a 3-point road is genuinely ambiguous). This fixes the Blender operator as well.
- **Branch Ramp Here re-aligns once the ramp has two stations**: aligned with only its mouth, a
  reverse-carriageway exit sat one lane (4.50 m) off the gore line (`ramp_edge_residual`).
- **There is no junction handle node in Godot** — a road's CHILD ORDER is its chain, so a mouth cannot
  be re-parented under one. **Select Junction** selects the clique and the editor's multi-selection
  pivot is the handle. Turning a crossing that way promotes its mouths to MANUAL (the kit's parent-frame
  baseline has no equivalent without a parent).
- `road_kit_gizmo.gd` draws each point's travel arrow and `handle_in`/`handle_out` handles on its own
  axis; a drag is a LENGTH (`handle_length` projects the mouse ray onto the axis, clamped at 0) and makes
  the point MANUAL.
- Gate `test_roadkit_b8.gd` 15/15. `check_roads.sh` now also runs the field-table check and every Godot
  plugin test (section 4, PASS=31 in 1m46s); `timeout -k` because a hung Godot ignores SIGTERM.

**The Blender authoring UI is retired (B9, 2026-09-14).** Deleted: `point_panel`, `point_overlay`,
`point_preview` (its report lives on in pure `point_flow`), `point_live`, `smoketest_point_live`, and 20
interactive operators (Insert/Merge/Split/Tidy/Renumber/Repair/Disconnect/Delete/Select/Jump/Align
Tangent/Sync Facings/Recentre/Validate/Make Ramp/Align Ramp/Branch Ramp/Apply Cross-Section/Add Sample
Network) — their rules are `point_record_ops`'s. `point_ops` keeps what a TOOL drives: New Road, Extend
Road, Connect, Make Intersection (`seed_district_roads.py`), Auto Setback, Load/Save Record, Export
Lanekit, Link Road Kit, plus the helpers `point_build` calls. `make_ramp`/`resolve_aux_pair` moved into
`point_record_ops` (the CLI's `ramp` calls them). The smoketests now drive that pipeline
(`smoketest_point_coverage` 34 checks, the sample network loaded from `RoadKitSample.roads.json`;
`smoketest_point_addon` asserts no `RKA_PT_*` is registered). `build_intersection_prototype.py`, which
called an operator that no longer existed, is in `archive/dead_tools/`. The addon README is now a module
map; the old Blender how-to is in git history.

**Two editor defects, found by running the plugin INSIDE the editor** (`ROADKIT_EDITOR_SELFTEST=<scene>
godot --headless --editor`, the `_selftest` hook in `plugin.gd`, in `check_roads.sh`) — in the editor a
non-@tool JVM script is a placeholder, which no SceneTree test sees:
- **The road did not "show up" because nothing showed it.** Preview Pieces instanced both DebugRoads
  pieces correctly in the real editor — it just had to be ticked, per scene. It is now ON by default
  (EditorSettings `road_kit/preview_pieces`) and rebuilt on every `scene_changed`.
- **A refresh on an UNLOADED network wiped the record.** A saved scene holds `RoadKitNetwork` without its
  points until Load Record; the preview-on-open path called `_refresh` → `_save_for_service` →
  `save_record` and wrote an empty network over `DebugRoads.roads.json` (restored from git, ground
  re-sampled). `RoadKitNetwork.save_record` now refuses to write an empty network over a record that has
  points (`force` to clear on purpose), `_refresh` skips an unloaded network, and the self-test asserts the
  record survives opening the scene.

**The draft surface: the road you are editing, not the last build (B10.1, 2026-09-14).** Until now the
editor showed a thin centreline until a ~30 s Blender build. `roadkit_cli.py bands` returns the paved
footprint Build sweeps, from the solve Build runs (`point_edges.solve_all`): a road run's strip between
`RoadSolve.edges_left/right`, a pad's `JunctionSolve.fan`, a gore's `GoreSolve.tris`, and the kerb /
footway lines of `point_edges.road_edge_runs` / `junction_edge_runs` / `gore_edge_runs`. Those three
are new and are the ONE enumeration of edge runs: `point_build.build_edges` / `build_junction_edges` /
`build_gore_edges` became thin loops over them, so the draft and the build cannot disagree about where a
kerb stops. The overlay uploads it (`road_kit_overlay.gd draft()`, an `ArrayMesh` child of the unowned
overlay, never saved) on every refresh; dock checkbox **Draft Surface**, EditorSettings
`road_kit/draft_surface`, ON by default. Each `bands[i]` names its owner and triangle range, for the
viewport's click-select (B10.3).
- **Materials come off the base meshes, never built in code** (user request): `materials_from(node)`
  collects surface materials by `resource_name` from the Preview Pieces holder, the same `M_Asphalt` /
  `M_ConcreteTile` / `M_LineW` every baked piece carries from `road_kit.blend`. Nothing built yet →
  engine default material. The overlay's line material is a `.tres` too (`road_kit_overlay_lines.tres`).
- **Measured on DebugRoads:** 60 ms wall for the CLI (budget 300; solve 22 ms). RoadKitSample is
  ~400 ms, 260 of it `kerb_runs` — the caching lever if a big network drags.
- **The draft IS the build, within the sweep's own frame:** every one of 2370 draft tarmac/pad vertices
  lies on a built tarmac triangle, worst **0.067 m** — the GN sweep lays each cross-section in the
  curve's frame, which drifts from the per-sample normal on a grade. Control: one station moved 10 m →
  2055/2382.
- **Finding (the build, not the draft): a run's END is cut on its last CHORD by the sweep**, while the
  solver's edges and the pad ring cut it on the mouth's axis (`point_profile.run_end_axes`, §8o). 24
  run-end vertices, worst **0.328 m** at DebugRoads junction 1 (loop mouth); the built road surface ends
  up to 1.5 m short of the draft's cap corner and the pad ring meets it with a step. B10.7 (mesh from the
  Python edges) removes it by construction.
- **Finding: 85 of 1781 lane samples stand on no paving in draft OR build** — turn connectors at
  junction 2 swinging up to 9 m outside the pad, and junction 1's turn paths riding 0.3–0.8 m off its
  planar pad. Draft and build agree on all of them; the lanes are what is wrong.
- Gate trap: a degenerate built triangle makes the closest-point test NaN, and `minf(0.0, NaN)` is NaN —
  it threw away an exact hit and read as a 4.8 m parity failure. Compare with `if d < best`.
- Gate `test_roadkit_draft.gd` 13/13, in `check_roads.sh`; the editor self-test now also refreshes a
  scratch copy of the record and asserts the draft wears `M_Asphalt` inside the real editor.

**Points are editable the moment a scene opens, and the record is their ONLY saved copy (B10.0,
2026-09-14).** The user could not hand-fix DebugRoads' junctions: a saved scene held only the
`RoadKitNetwork` node, its points appeared only after the dock's Load Record (which nothing prompted),
Preview Pieces showed a baked mesh that looked editable and was not, and a point had no click target in
the viewport. Worse, **the committed `DebugRoads.roads.json` had been overwritten by a 2-point `road_0`**
— `New Road` pressed on that unloaded view, which the empty-network guard did not catch because the
network was no longer empty. Restored from `f8b7859`. What changed, each asserted in the editor self-test:
- **`RoadKitNetwork.needs_load`**: an editor-instanced network with no roads and a record with points
  (set in `_ready`, editor only — a `--script` tool or the game builds its own). `save_record` refuses it
  like an empty network; the plugin's `_adopt` loads it on `scene_changed` and before any dock action.
  Loading is not an undo action, so the scene is not marked modified; the record stays byte-identical.
- **The scene never stores a road.** On `NOTIFICATION_EDITOR_PRE_SAVE` the network writes its record
  (only if the text changed) and clears its roads' and points' owners — `PackedScene.pack` skips an
  unowned node's whole subtree, measured, even an owned child under it — and restores them on
  `POST_SAVE` (and deferred, in case a failed save never sends it). So a scene save IS a record save, and
  there is no second copy to disagree with.
- **`from_record` reconciles instead of rebuilding**: a road keeps its node by name and a point by uid
  (moved between roads, re-ordered, renamed through temporary names). Selection and the editor's own undo
  entries (a Move, an inspector edit) keep pointing at live nodes across gestures and undo.
- **Clickable points.** `road_kit_gizmo.gd` adds collision segments (a 1.5 m cross + post and the travel
  arrow); junction mouths are drawn yellow, ramps cyan, termini red. **Preview piece internals are
  un-owned now**: owned by their piece root, each got a gizmo, and a click on the tarmac under a point
  resolved to its nearest editable ancestor — the SCENE ROOT. Control: no collision → the click selects
  the Terrain3D `Surface` mesh.
- A selected point is labelled in the viewport (road, chain index, role, uid, MANUAL / setback locked).
- **Edits refresh themselves.** Points and roads `set_notify_transform` in the editor and report
  transform and `rk_*` changes to the network (`edited`); the plugin debounces 0.25 s (`SETTLE_SECONDS`)
  and refreshes only when `record_text()` differs from the last refresh (so its own re-facing cannot
  loop). While the mouse is held it only redraws.
- **On release a sideways-moved point is DRAPED**: one that sat at grade (height − ground within
  `DRAPE_BAND` −0.5..1.5 m) keeps that height above the NATURAL ground at its new place; a deck or pier
  station keeps the artist's height. A moved junction mouth gets `setback_locked`. One undo step, and
  none at all when nothing changed. **An undo or redo is not a drag**: `version_changed` with a history
  that did not grow suppresses the drape, or undoing a Move would re-drape, commit, and destroy the redo
  history (measured: history 3 → 1 before the guard).
- `_get_property_list` returns `Array[Dictionary]` (the editor logged the compat ERROR on every open).
- Gate: the editor self-test (`plugin.gd _selftest`, `check_roads.sh` greps `RESULT PASS`) edits and
  saves the REAL DebugWorld scene and record and restores both byte for byte. It picks the at-grade mouth
  and move crossing the most ground (loop_p000, 3.17 m), clicks it through the 3D viewport's input
  surface after framing it with F, and asserts: 21/21 points loaded, all owned, scene unmodified, record
  byte-identical, click selects the point, drape to 0.01 m, setback locked, save writes no point into the
  `.tscn` and exactly `pos`/`setback_locked`/`fillet_radius` of that one point into the record, Ctrl+Z ×3
  commits nothing and returns the point to 0.0000 m with redo intact. Controls (no collision, no drape, no
  owner strip) fail 5 checks. Two self-test traps: undo through `get_history_undo_redo(id).undo()`
  bypasses the manager ("Inconsistent redo history", no `version_changed`) — push Ctrl+Z instead; and a
  point created by `add_child` gets its owner afterwards, so it needs `update_gizmos()` for the 3D editor
  to request its gizmo.

**A JUNCTION'S KERB FOLLOWS THE VEHICLE, AND A CAR CROSSING A PAD RIDES ITS SURFACE (B10.0b,
2026-09-14).** B10.1's two findings, both fixed in the rules rather than by hand, measured on DebugRoads
(built pieces, `test_roadkit_draft.gd`): lane samples off paving **85 → 0**, run-end vertices off the
draft **0.328 → 0.004 m**; RoadKitSample 20 → 0.
- **Swept-path sizing: `point_solve.contain_turns`.** The pad ring was sized by `fillet_radius` alone and
  `bezier_through` owned the turn shape, so junction 2's `east` — bending ~95° through its own crossing,
  mouths 40 m out — sent every movement between its two mouths across the unpaved corner notch, 7–23 m
  off the tarmac with a green gate. Each ring corner's radius now grows (×1.25 + 1 m per pass) until every
  legal turn path is `TURN_CLEARANCE` (1.0 m, half the car's hull) inside the ring; the kerb corners take
  the same solved radii (`junction_corners(ring=)`), so pad and kerb agree. Growth is monotonic, so it
  stops when nothing escapes or the ring stops changing. An escaping sample grows the corner whose KERB
  EDGE it is nearest to (`_round_ring(owners=)`), never the nearest corner VERTEX — a corner between arms
  40° apart has its vertex on the far side of the pad, 53 m from the notch it rounds, and growing by
  vertex distance grew the wrong (already clamped) corner and stopped. A corner may now take 98% of an
  edge that runs to a CAP point (`CAP_EDGE_REACH`); half an edge is kept only between two rounded corners.
  A path's first and last samples lie ON its cap, so a point within 5 cm of a cap counts as inside —
  without that, boundary parity grew three corners for nothing.
- **A turn is driven as a kerb return is built: `point_solve.turn_shape`** — straight along the longer
  approach, the largest circular arc through the point where the two lane lines meet (tangent length =
  the shorter leg), straight out; a movement turning < `TURN_ARC_MIN_DEG` (20°) or whose lane lines do not
  meet ahead of both mouths (straight-through, lane shift) stays a cubic, now with circular-arc handles
  (`arc_handle`, chord/3 only when straight). This is what makes a corner containable at all: the kerb arc
  sits concentric inside it. A single cubic between the mouths could not be contained whatever its handles
  (one leg 13 m longer than the other), and chord/3 handles bowed a sharp turn toward its chord, into the
  corner. Two sign errors cost a round each and are worth a unit check next time: the fillet radius is
  `t · tan(interior / 2)` (dividing drew a zig-zag), and `u` from `d0·s + d1·u = p1 − p0` is Cramer over
  `cross(d0, d1)` (over −cross the arc branch only ran in the wrong cases).
- **A turn path's HEIGHT is the pad's: `turn_path` reads each sample off the pad's own triangles
  (`pad_z`).** The cubic's Z ran straight between mouths while the pad is IDW-from-mouths, triangulated;
  with 1.1 m between junction 1's mouths they parted by up to 0.81 m. `point_export` now builds each
  connector from the solved pad and fits its `curve` with `curve_points` (control points at the arc's
  breaks, and wherever else 0.05 m needs one) — `JunctionSolve.turns`, the export and the preview share it.
- **The pad meets its stop line at the road's height: `_idw_z` weights by distance to each mouth's CAP
  SEGMENT (`Mouth.cap`)**, not its centre point. A cap corner 9 m out took 0.31 m of the neighbours'
  heights and the pad stepped against the road along `link`'s mouth. A stand-in with only `.pos`
  (`seed_district_roads`) keeps the point rule; the weights are geometry either way, so `_idw_z` stays
  linear in the mouth heights (the pad-lift property `W20` relies on).
- **A run's END is cut on the mouth axis in the BUILD too: `point_build.END_LEAD`.** `Curve to Mesh` (and
  `GN_PointSpine`'s stored lateral) take a poly curve's end frame from its last CHORD, while the solver and
  the pad ring use `run_end_axes`; `carrier_points` inserts a vertex 2 cm inside each open end along that
  end sample's own tangent, with the end's values.
- **What is left is layout, and the gate names it: `turn_off_pad` (WARN, `point_solve.turns_off_pad`)**,
  on the mouth nearest the worst sample other than the movement's own two. DebugRoads has one: `link →
  east` straight crosses the end of `spur`'s carriageway, 2.22 m past the pad, because the `spur` mouth
  (2-point road) faces 79° off its pad centre. Pulling it out 6/10/15 m along its road does not clear it
  (2.00/2.00/1.21 m) — the remedy is turning the mouth, a hand edit.
- Self-tests (`point_solve.py`, 20): turn_shape's arc/line/cubic cases; a 3-arm pad bending 90° through
  30 m mouths contains every movement, with the CONTROL `solve_junction(contain=False)` failing; the pad
  meets every cap at the road height; every turn sample rides `pad_z`. `test_roadkit_draft.gd` asserts
  both former findings.

**The intersection tweak is handles on the point (B10.4, 2026-09-14).** `road_kit_gizmo.gd` draws and
`road_kit_handles.gd` (a `RefCounted` — an `EditorNode3DGizmoPlugin` "can only be instantiated by
editor", so logic kept in the gizmo is untestable headless) owns what each does, through pure
`road_kit_gestures.gd` operations: every point has two LANE-COUNT handles at the outer edge of each
carriageway (`lane_edge_offset` / `lanes_for_offset`; FWD is `+s`, the point's local −X), and a junction
mouth adds a SETBACK handle (`slide_along_axis`: along the mouth's own flattened axis, locks the setback),
a FILLET handle (the radius the pad starts from — `contain_turns` may grow it) and the whole junction's
MOVE and ROTATE handles at the mouths' centroid (`junction_translate` / `junction_rotate`). There is no
junction node to parent the mouths under, so the kit's "turning a crossing promotes nothing" is kept by
rotating each mouth's `auto_facing` baseline with it; a hand turn of one mouth still promotes (the
control). Drags project onto the horizontal plane through the point or pad centre, and each is ONE
record-restoring undo step (`Handles.end` → `{before, after}`); cancel restores the record exactly. Gates:
`test_roadkit_handles.gd` 13/13 (rotate promotes none, move touches only the clique, setback 5e-6 m off
its axis, lane counts ±half a lane, fillet, a rotate drag through `drag_to` passes the kit's gate, cancel
restores); the editor self-test drags the ROTATE handle through the real gizmo plugin with the viewport's
camera, checks all 3 mouths turned and the action is "Road Kit: rotate junction", and Ctrl+Z restores it.
Self-test trap: after the undo checks there is redo history, which a new commit truncates — identify the
action by `get_current_action_name()`, never by history count.

**A viewport tool mode, road-generator style (B10.3, 2026-09-14).** A toolbar in
`CONTAINER_SPATIAL_EDITOR_MENU` (Off / Select / Draw Road / Insert / Delete / Connect) and
`set_input_event_forwarding_always_enabled()`, so a click anywhere reaches `plugin._forward_3d_gui_input`
— not only while a road node is selected. `road_kit_tool.gd` (a `RefCounted`, so testable) owns what a
click does, over the existing gestures: picking is screen-space (a point within 14 px, a centreline within
12 px of the overlay's last `centrelines` runs, which now carry each run's `uids` so a click names its
span); DRAW lands each station on Terrain3D's surface in plan (`get_intersection(..., gpu_mode=false)`,
miss = `z > 3.4e38` or NaN) at the NATURAL ground's height + 0.10 m drape (`road_kit_ground.natural_height`,
so a stamped terrain cannot lift a new road onto the old one), else on the network's y = 0 plane; CONNECT
joins two ends of one road by SEGMENT, makes or grows a junction across roads, and hands off to
`roadkit_cli.py ramp` (the solver places a ramp) when one pick is an interior station with aux lanes. The
plugin wraps every click that changes the network in one record-restoring undo step named after the mode,
and Esc / right-click finishes an open sequence. Gates: `test_roadkit_tool.gd` 12/12 (a real Camera3D over
the sample network: pick, select road, Alt-select junction, insert at the click with the gate still 0
errors, delete, draw 3 stations at the clicks, Esc then a NEW road, connect SEGMENT and junction, and on
DebugWorld a drawn station at natural ground + drape rather than the stamped surface) and the editor
self-test sends a left click through `_forward_3d_gui_input` in Insert mode and undoes it. Two traps: in a
`SceneTree._initialize` a node added to `root` is not `is_inside_tree()` until the first `await
process_frame` (every `global_position` errors); and a GDScript parse error in `plugin.gd` makes the editor
self-test HANG to its timeout — always `--check-only` the plugin first.

**Dragging a road is a move, baked on release (B10.5, 2026-09-14).** A `RoadKitRoad` node dragged with the
stock gizmo already moves its points (a point's record position composes its road's transform), but it
left the road node carrying an offset every later edit had to compose. On release (`_drape_moved`) each
road with a non-identity transform is baked into its points (`Gestures.bake_road_transform`: road back at
identity, every network transform unchanged, the facing baseline turned with it so nothing is promoted to
MANUAL), and — dock option "Dragging a road moves its junctions", on by default — every OTHER road's mouth
at its junctions moves by that junction's mean mouth displacement (`move_junction_partners`), so a pad
travels with the road instead of stretching across the gap. The bake, the partners and the drape are ONE
undo step ("Road Kit: Move Road") back to the last refreshed record; an undo/redo is never baked (the
road's transform may then keep an offset until the next edit, which is harmless — the record composes it).
Gates: `test_roadkit_handles.gd` (bake keeps every network transform, a 10° turn promotes none, partners
follow, bystanders do not) and the editor self-test drags road `east` with a real Move action (4 partner
mouths follow, one step, Ctrl+Z restores the record).

**Build rebuilds only the zones whose output changed (B10.6, 2026-09-14).** Which zones an edit touched is
NOT a record diff — the whole network is solved for every piece (a kerb opens against a neighbour's asphalt,
a pad corner grows for another road's turn, a gore goes with its ramp's zone). `point_digest.piece_digests`
asks the OUTPUT instead: per piece, a SHA-1 of what it emits from the same solve and cut the build runs —
its runs' carrier samples and values, edge runs, marking runs, pads (ring, fan, corners), gores, its own
`split_doc` lanekit and its roads' authored fields — rounded to 0.1 mm, salted with the builder's source
(`point_build`, `point_nodes`, `point_solve`, `point_edges`, `kit_common`, …) and `road_kit.blend`'s size
and mtime, so a builder change dirties everything. `roadkit_cli.py pieces` reports a `digest` per piece
(now with `--ground`, the same ground the mesh build uses); `build_roads_piece.sh` with `DIRTY_ONLY=1`
skips a piece whose digest equals the one in `<stem>.build.json` and whose scene exists, builds only
the dirty ones (`roadkit_cli.py gltf --only`; Blender's `--only` until B11) — and nothing at all when none is — and writes a piece's
digest into the manifest only after it has BAKED, so a failed bake stays dirty. The manifest belongs to the
committed pieces; commit it with them. Dock: **Build Piece (changed zones)** is the default, **Rebuild All
Pieces** forces it, and a build that rebuilt something on a stamped network says to press Stamp Terrain.
Measured on DebugRoads (2 zones): cold 40.7 s, nothing changed **5.2 s** (no Blender), one interior station
of `east` moved **23.4 s** — `debug_b` rebuilt, `debug_a` reported clean. Gate: `point_digest.py`
self-test (in `check_roads.sh`): re-solving reproduces every digest, a station moved in one zone of the
testbed dirties that piece only, moving it back restores the digests.

**Does the road mesh need Blender? Measured, then decided (B10.7, 2026-09-14).** `point_mesh.py` re-sweeps
every layer `point_build` hands Geometry Nodes — carriageway, median, deck, pillars, kerb, footway,
barrier, markings, pads, gores — in pure Python from the same solve and the same layer table, and
`blender/tools/roadkit_mesh_parity.py` compares it with the baked glTF object by object, material by
material (area, triangle count, sampled surface distance both ways) plus the drivable surface under every
lane sample. `roadkit_cli.py mesh` hands the result to Godot (`gltf_tris.py` is the reader).
- **Parity.** DebugRoads: carriageway, pads, markings exact (p95 0.000 m both ways); road surface under
  2 255 lane samples max **2.6 mm** apart. RoadKitSample (ramps, gores, footways, median): footway, gore,
  median, pad, markings exact; 6 046 lane samples max **8.4 mm**; no object in only one build. Kerbs and
  decks exact after the GN fix below, barriers within 0.4% area (Blender evaluates an extrusion's
  thickness per FACE, so a wall's end segment steps where the solver's per-vertex value ramps).
- **Speed.** Python sweep 65–90 ms (DebugRoads) / 526–605 ms (RoadKitSample); **177 ms end to end** into
  Godot `ArrayMesh`es with trimesh collision for DebugRoads, 848 ms for RoadKitSample — against ~40 s for
  the Blender build of DebugRoads before export and bake.
- **What the spike found in the SHIPPED build, and fixed in `GN_PointDeck` (GROUP_VERSION 5):** `Extrude
  Mesh` MOVES the faces it extrudes, and with `Individual` at its default every face got its own four walls.
  So every kerb was hollow (its only horizontal face at road level, 10.46 m, walls to 10.61 m), every bridge
  deck had no underside from below (the soffit still faced up), side walls faced inward (a kerb's signed
  volume −1.8 m³ against +5.46 once fixed), and every segment carried hidden internal walls. Now: one
  region, the moved copy flipped (bottom down, walls out), the swept band joined back on as the top.
  Measured after: kerb 492/492 triangles and deck 556/556 equal to the Python sweep, volumes equal (deck
  2355.2 vs 2355.9 m³). DebugRoads and RoadKitZones pieces rebuilt (the digest salt caught the builder
  change and dirtied every piece by itself).
- **Not ported at the time (all ported in B11, below):** profile ASSETS (artist-modelled sections from `road_kit.blend`
  — neither sample network uses one), style slots (material by name), vertex normals (Blender's glTF
  carries NORMAL; neither carries UVs, the kit's materials are world-position procedural), the `-colonly`
  road/walk/`-noped` collision split, and the piece SCENE (today glTF → `WorldBaker` → `NavBaker`).
- **Decision:** the pure-Python sweep becomes the ONE owner of road geometry (PLAN.md 3.1 **B11**): port the
  five items above, write the piece scene from Godot, gate it with `roadkit_mesh_parity.py` +
  `probe_road_ground`/`probe_road_stamp`/`probe_traffic_spawn`/`probe_road_zones`, then make it the Build
  and retire the Blender road build like B9 (`build_island_base.py` keeps Blender until the island is
  rebuilt on Terrain3D). Until then Blender is the build, and `check_roads.sh` runs
  `roadkit_mesh_parity.py --assert` on DebugRoads so the two cannot drift (control: Python's deck moved
  10 cm → `surface/M_Concrete: surface distance p95 0.100`, exit 1).

**Editing is live, Godot's Delete is a road gesture, and a name says what a point is (B10.8, 2026-09-14,
user-reported: "dragging freezes the editor", "delete like a Godot node", "everything has the same name").**
- **THE FREEZE WAS ONE COMMAND.** With ZoneMarkers in the scene every refresh ran `centrelines --zones`,
  which drew the cross-zone successor edges by running the whole gate and a whole lane export —
  **3.1 s blocking on DebugRoads** (6 s of it `check_path_fidelity`, fitting every lane twice) — on every
  pause of a drag and every release. `roadkit_cli.py live` answers centrelines + draft bands + facings +
  junction centres in ONE process (**0.09 s**, cross edges only with `--cross`, 3.4 s). The plugin runs it on
  worker threads in two LATEST-WINS slots (FAST, and CROSS for the edges), from scratch copies under
  `user://road_kit_live/` — never the real record mid-drag — and sends a drag every `LIVE_TICK` (50 ms)
  while the button is held, so the road follows the mouse. Nothing is saved, draped or faced mid-drag; a
  result is faced only if the record still matches the one sent. Main-thread cost per tick is asserted by
  the editor self-test (`LIVE_TICK_BUDGET_MS`). Validate and Flow Report (2–6 s) run on a thread too
  (`_service_async`); Build already did.
- **Facing the point under the gizmo quietly made it MANUAL.** A settle mid-drag re-faced every AUTO point,
  the gizmo then wrote its pre-drag basis back on the next mouse move, and `was_rotated()` read the
  difference as a hand rotation. Facings now land only after release.
- **SELECT took the PRESS**, so a move-gizmo arrow lying along a road (over its centreline) selected the road
  instead of starting the drag — "dragging does not work". The press and release now pass through; a click
  (release within 4 px of the press) selects the road, deferred after the editor's own click-select.
- **Links in the record are DERIVED from the live tree** (`RoadKitNetwork.record_links`), so the Scene dock's
  Delete needs no hook and its undo (which just re-adds the node) restores the record exactly: a link to a
  point no longer in the tree is not written; SEGMENT/JUNCTION links are written on both ends; two points
  left chain-adjacent by deleted stations are joined (through remembered links, `_known_links`); a
  SEGMENT that skips exactly one live station linking both ends is dropped; an INTERSECTION with no
  JUNCTION left is written as SEGMENT. `Gestures.delete_point` joins the neighbours the same way (it used to
  cut the road). `child_order_changed` on roads and the network is the edit signal; names renumber on settle.
- **Names carry a tag** (`RoadKitNetwork.name_tag`): `_jct` junction mouth, `_ramp` ramp mouth, `_aux` the
  mainline station a ramp leaves, `_end` a road end joining nothing, none for a plain station; each point's
  `editor_description` (the Scene-dock tooltip) lists its role and links, and the overlay floats a
  `JUNCTION (n)` label listing the mouths over every pad. Nothing reads a point by name.
- **The record cannot be lost by a crash or a commit.** `save_record` writes `<record>.tmp` and renames it over
  the record (atomic), skips an unchanged write, and tracks the text it last read or wrote: a record changed
  on disk (a git checkout) is RELOADED as an undo step (`_reload_if_changed_on_disk`), never saved over —
  also on scene save.
- **DebugRoads' west junction is one clean T** (user request). `loop_p010` had been deleted in the editor,
  leaving `link_p000` + `loop_p000` a 2-arm pad; the committed version had that mouth 74° off its pad
  centre because `loop_p009` jogged 25 m north. Rebuilt as a T — loop's tail and `link` the through road,
  loop's head the stem — dropping that station, mouths on their approach lines, AUTO facings, one
  `auto_setback` (a second pass grew it, W17): 0 errors, no finding on the pad, 0 of 465 nearby lane samples
  off paving. The tail mouth is `loop_p009_jct` now.
- Gates: `test_roadkit_native_delete.gd` (in `check_roads.sh`), and the editor self-test's new steps — SELECT
  click pass-through, a Scene-dock delete + Ctrl+Z, a record changed on disk reloaded both ways, the junction
  labels, the live-tick cost.

**A BARRIER IS ON OR OFF, NEVER A WEDGE — the "car launched at speed" bug (PLAN.md 0.1, 2026-09-14,
user-reported: "randomly spikes upward at high speed, worse near the bridge and close to a wall").** The
solver decides `rka_wall_h` per 4 m sample (full `barrier_height` where the road is ≥ `BARRIER_MIN_DELTA`
off the ground, 0 elsewhere) and the sweep interpolates every attribute between samples, so the span where
a parapet BEGINS was swept as a 4 m wedge rising from the kerb to 1 m, collision included. On DebugRoads'
`link`, where the bridge leaves the island, that is a jump ramp standing on the road edge: a car at 37 m/s
with its outer wheels on the edge line climbed it and left the ground at up to 23.6 m/s of vertical speed.
(Real highways retired the "ramped end" barrier terminal for the same reason.) `point_edges.step_walls` is
now applied inside all three edge-run enumerations (`road_edge_runs` / `junction_edge_runs` /
`gore_edge_runs`), so the Blender build, the pure-Python sweep, the draft and the digest all see it: where
one vertex has a barrier and its neighbour none, a vertex goes in `WALL_END_STEP` (2 cm) from the bare one at
full height, so the wall covers the whole span and ends in a face. It errs toward more fence. Two non-zero
heights still blend. `point_solve.junction_corners` had the same wedge along a whole corner arc when one arm
is fenced and the other not; it now steps at the corner's middle. Found with two new tools:
- **`tools/godot/probe_road_launch.gd`** — the gate. `debug/LaneDriveProbeController` (the ordinary traffic
  brain, aimed at a lane by name, blind to other cars, optionally riding `lateral_offset` m beside the lane)
  drives Vehicle.tscn through DebugWorld's streamed pieces. A LAUNCH is the body's vertical speed RELATIVE
  TO THE LANE'S OWN RISE RATE going up by more than 3 m/s within 0.25 s while on the road. Measured against
  the road, not the world: a sag at 32 m/s is legitimately a 3.8 m/s change, and the first detector read
  grades as launches. A per-tick threshold was the first detector too, and it missed launches that build
  over several ticks (31 m/s with no flag). Each launch prints every body contact and every wheel ray.
  GATE_CASES: 0 on-road launches over 6 cases; control (the pieces built before `step_walls`): 6 launches
  on the two edge-line cases, worst 23.6 m/s.
- **`tools/godot/probe_road_section.gd`** — a collision cross-section of a streamed lane (`--half`), or a
  lengthwise one at a lateral offset (`--along --lat`): every collider a vertical ray passes through, top
  first. It is what showed the wedge (10.61 → 11.61 m over 4.25 m), which no visual shows.

**A SLOPED PAD IS A GRID OVER A THIN PLATE CLAMPED TO ITS ROADS (B12, 2026-09-16).** Found by the same
probe: DebugRoads' west T has mouths at 10.46 / 12.97 / 11.02 m, and two of its stop lines have cap corners
6 m apart with 1.95 m between them. `point_solve.PadField` is now the ONE owner of a pad's height, and
`pad_triangles` builds a sloped pad as `grid_pad_triangles` (the ring cut by a world-aligned 1.5 m grid,
Sutherland-Hodgman plus ear-clip per edge cell, watertight by area) instead of a one-apex fan. A pad whose
mouths are level and whose roads are level keeps its fan, its triangle count and its digest. The field is the
minimum-curvature surface (squared second differences in x, y and the cross term). Each approach band,
`PAD_APPROACH` 4 m along its road, is fixed to that road's plane: its height at the stop line, rising at
`Mouth.grade` (`mouth_grade`, the run's own end tangent). It is solved in pure Python by conjugate gradients on
a 2 m grid, started from IDW, in 0.07 s on the west T. It is linear in the mouth heights, like IDW.
- **Measure a pad ROAD TO ROAD, never on the pad alone.** The first attempt was a membrane (harmonic,
  fixed at the caps). On the pad it looked better than IDW, 17.9% steepest and 5.9% grade change per 2 m.
  In a car it was worse: it met the `loop` stop line climbing 18% against a +4% road, and `link_R1` at
  20 m/s launched there, where the old fan had not. `point_solve.turn_grades` now follows each movement
  `PAD_GRADE_APPROACH` (10 m) along both roads. Drive profile of the straight `link` → `loop` outer lane
  (crest per 2 m / steepest): old fan 9.3 / 21.2%, IDW 9.9 / 16.3%, membrane 13.2 / 17.3%, thin plate
  8.4 / 12.6%. Worst movement: 41.5 / 17.5 / 18.0 / 12.8%.
- **`pad_grade` (WARN)**: the steepest movement past `PAD_GRADE_MAX` (8%, the kit's hill-road grade),
  naming the two stop lines and the floor no surface can go below (end-to-end rise over plan length). On
  the west T: 18.3% on the left turn from the `loop` head to its tail, whose floor is 15.7% (1.95 m over
  12.4 m). That is layout.
- **The rest was layout, and DebugRoads' west T was re-graded (user decision).** On the new surface
  `probe_road_launch.gd -- --lane=link_R1 --speed=S` still rose 3.65 m/s at 25 m/s and 4.50 at 30. At
  35 m/s the launches were 20-50 m PAST the pad, on `loop` itself, which fell from −2% to −18% within 11 m of
  its head station: B12's original "a car leaves the pad at 5 m/s" was that crest. `loop`'s head mouth
  `p_ffcedf9d` went 11.02 → 12.2 m, and its next two stations 10.63 → 11.5 and 8.06 → 10.8, so the 4 m
  descent runs over 106 m (fill up to 2.8 m, re-stamped). Pad steepest 18.3 → 10.4%, `loop` worst grade
  change per sample 7.2 → 1.6%. `link_R1 +0`: 0 on-road launches at 20/25/30/35 m/s, worst rise 1.62-2.29
  m/s. `pad_grade` still WARNs at 10.4%: `link` (10.46) to `loop`'s tail (12.97) is 6.9% at best. At 30 m/s
  the car also runs wide on a `loop` curve ~250 m on and bounces on terrain, which is unrelated.
- **After a pad change on a stamped network, stamp again.** The terrain was stamped from the old surface,
  and at 20 m/s a rear wheel hit Terrain3D standing 0.18 m proud of the new pad.
- **Terrain3D `get_height` a hair inside a cell edge returns the FAR vertex's height**: (-150.0006, 72.0)
  read 11.09, the (-152, 72) vertex, where (-150, 72) is 10.97. The 1.5 m pad grid shares a vertex with
  the 2 m terrain grid every 6 m, which turned that into 6 false "proud" pad vertices in
  `probe_road_stamp.gd`. The probe queries pad vertices on a 1 cm grid now.
- `blender/tools/measure_pad_grades.py <record>` prints the built pad, its field, IDW and the old fan side
  by side, with the floor.
- Not changed: `seed_district_roads.pad_lifts` still predicts burial with `_idw_z` over stand-in mouths (no
  ring exists yet). Both rules are linear in the mouth heights, so its uniform lift is still exact in kind.

**THE ROAD BUILD HAS NO BLENDER (B11, 2026-09-16).** B10.7's five missing pieces are ported, the Build runs them,
and the Blender road build is deleted. `build_roads_piece.sh`: (1) `roadkit_cli.py pieces` (gate, zone cut, lanekits,
digests), (2) `roadkit_cli.py gltf --gated --only <dirty>` writes `src/.../world/pieces/<piece>.gltf`, (3)
`GLTF_READY=1 build_piece.sh <piece>` bakes it (WorldBaker + lanekit Path3Ds, NavBaker, `.scn`) with no `.blend`.
DebugRoads end to end **28 s**, of which the mesh write is **0.4 s** — the rest is the Godot bake.
- **The kit is DATA** (`point_kit.py`): `blender/tools/export_road_kit_data.py` reads `road_kit.blend` into
  `assets/world_source/kit/road_kit.json` — every material as the glTF entry Blender's exporter produced
  (`export_world.py`'s base-colour flattening restated: M_ConcreteTile's checker is its mean, 0.815/0.795/0.755) and
  every `ROAD_KIT` profile's points — plus the `.blend`'s sha1, which `point_kit.self_test` checks, so an edited kit
  with a stale JSON fails the gate. `build_road_kit.py` runs the export at the end of every kit build. Styles resolve
  as `point_style.resolve` did (one slot table, `point_style.SLOTS`): a name the kit lacks falls back to the layer
  default and is reported (`missing_style`, printed by the build).
- **A profile asset is swept in the Z-up curve frame**: section +X is `cross(N, T)` (the curve's left), +Y the Z-up
  normal `N` (perpendicular to the tangent), mirrored for the right flank, open (no caps), origin on
  `point_build.ASSET_Z_ATTR`'s line. Derived from `GN_PointProfile`'s measured correction, then measured: triangle
  counts equal to Blender's on every asset layer (granite kerb 300/300, parapet 816/816, jersey 1400/1400), p95
  0.000 m. **The Blender road build had never swept one from a Godot record**: `roadkit_build_mesh.py` never linked
  the kit, so every named asset resolved to "missing" and the report line was filtered out of the build output.
- **`-colonly` proxies** are `point_mesh._collision` (`point_build.collision_name`'s rule): one road proxy (the
  `__surface`/pad/gore, every material), one walk proxy (the run's edge objects), `-noped` from `ped_access`.
  Godot's importer still makes the `StaticBody3D`s from the name. Navmesh vertex counts and collision shape counts
  of the rebuilt pieces equal the Blender-built ones (RoadKitZones west 32/18, RoadKitSample 32/28).
- **Normals are auto-smooth at 30°, computed** (`point_gltf.indexed`), not matched: Blender's export shaded smooth
  across hard edges and carried inverted normals (88 on one DebugRoads deck). Gate: none inverted, none past the
  angle (worst 28.6°). Quads split on the SHORTER diagonal (`point_mesh._strip`): areas now equal Blender's to
  0.1 m² (they differed by up to 0.7% on the ramps), at p95 0.003 m.
- **The pieces no longer carry the station Empties** (`east_p000` Node3Ds with the record in their extras): nothing
  read them, and the record is the one copy. 38 nodes fewer on RoadKitSample (235 -> 197).
- **Parity before retirement**, Blender references built from the same records with the kit linked, `--assert`
  green on all four: DebugRoads (both zones, with ground) every layer and both proxy kinds p95 0.000 m except the
  known barrier per-face step, lane surface max 0.9 mm over 2 214 samples; RoadKitZones west+east and RoadKitSample
  p95 ≤ 0.003 m, lane surface max 8.4 mm over 6 046 samples; `RoadKitStyled.roads.json` (the sample with material
  slots, three profile assets and one missing name) every layer p95 0.000–0.003 m, the 13 materials identical.
- **The editor shows the full mesh on release**: `roadkit_cli.py live --mesh [--ground]` returns
  `point_mesh.build`'s visible triangles by material; the plugin requests it only when the mouse is up (a drag still
  gets the fast bands), prepares the arrays on the worker thread (`OverlayScript.prepare_mesh`, re-wound for Godot's
  clockwise front face) and uploads them as the draft (`full_mesh`), in the base meshes' materials. DebugRoads
  18 280 triangles in 0.34 s of CLI.
- **Retired:** `blender/tools/roadkit_build_mesh.py`, `build_roadkit_sample_piece.py` and the piece `.blend`s they
  wrote (`Roads_DebugRoads_*`, `Roads_RoadKitZones_*`, `RoadKitSample`). `point_build`/`point_nodes` stay for
  `build_island_base.py` only. The digest salt is now the Python builder's sources and `road_kit.json`'s bytes.
- Gates: `point_kit.py`, `point_gltf.py` self-tests and **`blender/tools/check_roadkit_build.py`** (in
  `check_roads.sh`, now PASS=40): DebugRoads and RoadKitZones rebuilt into a temp dir must equal the committed
  glTFs under `roadkit_mesh_parity --built --assert` (control: one station of `east` moved 3 m in the record →
  `edges/M_Concrete p95 1.584`, FAIL), and RoadKitStyled's styles, assets and normals build. Runtime, on the
  rebuilt pieces: `probe_road_zones` 12/12, `probe_road_ground` 201/201, `probe_road_stamp` PASS,
  `probe_traffic_spawn` 6/6, `probe_road_launch` 0 launches over 6 cases, `probe_road_traffic --scene=roadkit`
  50 cars / 0 stuck; editor self-test PASS including "after a release the draft is the full mesh".
- **Also fixed on the way: a close camera could not click a road** (`road_kit_tool.gd`). `pick_centreline` skipped
  every segment with an end behind the camera, so framed a few metres from a mouth (F) nothing was clickable, which
  is what failed the editor self-test on a clean HEAD. Segments are clipped to the near plane (`visible_part`), and
  the click's screen fraction is mapped back to the segment perspective-correctly (`world_param`): the insert point
  had been up to 0.585 m from the cursor on a close view. Gate `test_roadkit_tool.gd` "close camera" (controls: the
  old skip → no pick; a linear lerp → 0.585 m).

## Ground is Terrain3D; road-generator was tried and REMOVED (2026-09-06 → 2026-09-13)

`TERRAIN3D_TRANSITION.md` is the history of record. Ground moved from the Blender bake to in-engine
**Terrain3D** and stays there. Roads moved to **road-generator** for a week and were then replaced by
the Godot-authored Road Kit (option B, above); the addon, its `road_demos/`, `world.RoadNetworkBridge`
and `tools/godot/bake_road_terrain.gd` are **deleted** (user decision, 2026-09-13). `world/World.tscn`
is the real world; `world/DebugWorld.tscn` is a small-scale version of the *entire* world for fast
iteration. Both are gated by `tools/godot/check_world_envelope.gd`.

**DebugWorld's road is a Road Kit network now** — `DebugRoads` (`assets/world_source/pieces/
DebugRoads.roads.json`), cut by its two zones into `Roads_DebugRoads_debug_a` / `_debug_b`, and
debug_a's traffic route is its zone id. It was converted once from the road-generator points
(position, and the authored basis at each junction mouth faced along its chain; interior stations
take the kit's own facing, because road-generator's 5 m default handles made near-polyline corners
that folded the inner lanes back on themselves, 177° measured). Three decisions in that conversion,
each measured: road-generator's fork at `RP_008` (two roads claiming one point, no junction — the
source of 3.2's duplicated lanes and self-successor) is DROPPED, not turned into a Y junction (an
invented one hooked two lanes 170° at its mouths), leaving `spur` a dead end; **Auto Setback was not
pressed** — it grew junction 2 to a ~190 m pad over terrain that was only ever flattened along
road-generator's corridor, while the authored mouths keep it at 15–43 m with 0 gate errors; and every
station is draped 0.10 m onto the sampled Terrain3D ground (they sat up to 1.44 m off it; before draping two
ambient cars spawned at junction-1 mouths fell out of the world within 3 s, after it none did in 240 s). The terrain keeps the
road-generator flattening baked into its height map; the Road Kit's own corridor stamp is B7.

The seam into traffic is unchanged in shape: every lane is a `PathLaneRoute` over a native
`Curve3D`. `PathLaneRoute.sourcePath` (an externally owned `Path3D`) outlived the bridge it was
added for; it costs one branch and nothing uses it today. Rules from the road-generator week that
still hold:

- **The lane registry is not guaranteed complete at spawn time.** Baked `VehicleRoute`s registered in
  `_ready`; road-generator built through `call_deferred` and the bridge published a few frames
  later — measured, a zone LOADED one log line before the bridge published and spawned its whole
  fleet unrouted. `ZoneManager.maintainTraffic`'s cull gained an **`unrouted`** reason beside dead /
  route-finished / fell-out / out-of-range, and the existing top-up respawns the car. Re-routing it
  in place was tried and reverted: that is a SECOND placement path, and the two disagreed — it left
  two cars on one lane nose to tail, the front one stuck in `BrakeState`. Since 0.4 the fleet is
  not spawned at all until a lane matches (`spawnTrafficCar` holds it and logs once), so `unrouted`
  now only covers a road rebuild stranding a car.
- **Ambient spawn placement had three defects, and one caused the other two to look like physics**
  (2026-09-13, PLAN.md 0.4, gate `tools/godot/probe_traffic_spawn.gd`). (1) Lanes were taken in
  NAME order (`_1, _10, _11, _2`), not chain order, so a car could land on a lane with no successor.
  (2) The top-up index was `vehicles.size()`, which repeats — two respawns in a row were set down on
  the same point, and on HEAD 19 of 21 spawns went to one lane. (3) A car spawned at its default
  heading (−Z) whatever way its lane ran; one set across a west-running lane crept 6 m north on full
  steer and stopped for good, 54 m from the player — inside the 60 m `stallReclaimMinDist`, so it
  was never reclaimed, and the respawns stacked on it until the fleet read **0 moving**. That is
  the "car at ~0 m/s" shape recorded as unexplained. **Ordering alone did not fix (1)**: once the
  cursor rotates, a short lane merely waits its turn (9 of 22 cars ran out within 160 m), so
  `LaneReach.orderForSpawn` FILTERS to lanes that reach far enough. Measured after, 240 s on
  DebugWorld with the plain `Lane_` prefix (the `Lane_pR` workaround is gone): 15 cars over 7
  lanes, each driving 393–528 m, nearest car at spawn ≥ 13 m, heading within 6° of the lane,
  longest idle 0.1 s; HEAD fails clearance (7.6 m), heading (164°) and rotation (19/21).

- **A car can be alive, routed, in range and still not drive**, and every reclaim reason missed it:
  dead / route-finished / fell-out / out-of-range are all false for a stuck car, so it was immortal
  and held a slot the top-up would have filled with a working one. Distance never covered it — the
  stall happens near the spawn, i.e. near the player, which is where out-of-range is furthest from
  firing. `stalled` (`ZoneManager.vehicleStallTimeout`, 12 s) is that eye, measured on
  **`routeProgress`, not speed** (`VehicleAIController.stalledFor()`): the speed version missed a car
  oscillating across 6 m of plateau at 0.3-1.0 m/s indefinitely — moving the whole time, advancing
  along its lane not at all. Gated by `stallReclaimMinDist` (60 m) so nothing pops in view. Measured:
  `1 moving` -> `3 cars, 3 moving, 3 routed`, steady, after 3 `unrouted` + 2 `stalled` reclaims.
- **A mission vehicle must never be ambient traffic.** There is no mission-vehicle concept yet, and
  when one lands the hazard is the opposite of the obvious: a mission car in a zone's `lz.vehicles`
  is *already* reclaimable by out-of-range and `stalled`, so the mission breaks silently. It belongs
  outside the disposable list, the way `NamedCharacterConfig` sits beside `SpawnConfig`. "Vehicle
  gone -> mission failed" is the mission system's rule (`MissionManager.failMission` +
  `EventBus.missionFailed`, the pattern `Door` already uses), never `ZoneManager`'s — that would put
  reclaim policy and mission policy in two places.

---

## Known Quirks / Gotchas

- **A scene-exported node reference can be a DIFFERENT JVM object than the one Godot bound the
  script to.** `@Export CharacterBody3D player` serialized as `node_paths=PackedStringArray("player")`
  is resolved at instantiate time and may hand back a second JVM wrapper for the same engine object
  (same `get_instance_id()`, different `identityHashCode`, all Java fields at their defaults). Engine
  calls work on either wrapper; **Java state does not**, and which exports are affected depends on
  resolution order — measured on one body, `AnimationController.player` was stale and
  `TPSCameraController.player` was not. So: use the export to say *which* node, then re-resolve it
  at runtime (`getNodeOrNull(player.getPath())`, cached) before reading any Java field or calling any
  non-engine method on it. This produced the 90° aim-facing bug and silently disabled AI animation
  LOD — see "SOLVED: the player's ~90° body rotation" above.
- **An exported *Node* reference needs `node_paths=PackedStringArray("a","b")` in the `.tscn` node
  header.** Serialize the NodePath without it and the property stays **silently null** — the
  Terrain3D road connector read as configured and did nothing. Godot writes this itself when a scene
  is saved from the editor; it is only a trap when authoring `.tscn` text by hand.
- **A godot-jvm registered method is snake_cased** (`publishedCount()` → `published_count`), and a
  GDScript error inside `SceneTree._initialize` aborts before `quit()` — so a wrong name reads as a
  **hang**, not an error. Same shape as `ClassDB.instantiate("<a JVM class>")` returning null: a
  godot-jvm class is a **script**, so `load("res://…/X.java").new()`.
- **Godot's stdout is block-buffered when piped**, so a `timeout`-killed headless run prints
  **nothing at all** — including lines that already executed. Run headless checks under `stdbuf -oL`
  or a hang will be attributed to the wrong statement.
- `AICharacter.onDied()` must set `isDead = true` **before** calling `super.onDied()` (which stops
  physics processing). If `isDead` is not set first, `gatherInput` can still run on the
  same frame via a pending physics callback.
- **godot-jvm 1.0.0-rc1: `Dictionary.put(k, v)` throws on a typed non-nullable value** (e.g.
  `Dictionary<String, String>`) — `put` calls `get(key, null)` to return the old value, and the `null`
  default fails the STRING converter's `require(any is String)` (`IllegalArgumentException: Failed
  requirement`). Use `set(k, v)`. It broke every runtime faction flip, and a joining client dropped the
  faction baseline as "malformed" (found by `tools/net/run_net_shot_test.sh`; `FactionTable` fixed).
  `NetworkManager`'s malformed-packet log now names the tag and the top stack frames — it named neither.
- **Do not export a nested/raw generic `Dictionary` from a `@Script` class** (e.g.
  `@Export Dictionary<String, Dictionary>`). The godot-jvm `classGraphSymbolsProcess`
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
  godot-jvm `TransferContext` shared buffer and throws `Shared Buffer Error: JVM expected a LONG
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
  `ZoneManager.unload` before it frees/recycles a body (stop a touch earlier, while fully in-tree).
  For any other node that plays audio and can be freed while playing, prefer the **self-stop on
  `tree_exiting`** pattern over a parent/sibling `_exitTree` stop.
  **App-exit does NOT go through `tree_exiting`** (this was the residual leak): at real quit the
  godot-jvm runtime is torn down ("Cleaning JVM Memory…") *before* the final SceneTree node teardown,
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
- A weapon BORN HELD (authored inside the character, like `Fist`) is discovered by
  `WeaponController.discoverPrePlacedWeapons`: it takes the first child of each `WeaponAttachment`
  child that is a `WeaponItem`. The sockets are per GRIP ARCHETYPE (`SocketRifle`, `SocketPistol`,
  `SocketLauncher`, `SocketMelee`, `SocketFist` — W20), never per weapon; a weapon names its own in
  `holdSocket`.
- The godot-jvm binding exposes a `RigidBody3D`'s Godot 4 `freeze` property as
  `setFreezeEnabled / isFreezeEnabled`, not `setFreeze` (`Vehicle` uses it). A weapon is no longer a
  body at all (W15), so `Pickup.pause()` detaches its world body instead of freezing anything.
- `ENetConnection.createHost/createHostBound` take `(… maxPeers, maxChannels, inBandwidth,
  outBandwidth)` — all-int positional args. Putting the channel count one slot too far right
  silently caps outgoing bandwidth at N bytes/s (ENet then throttle-drops unreliable packets
  into multi-second bursts). `connectToHost` differs: its 3rd param IS `channel_count`.
- `NodePath.toString()` returns `"NodePath(<subnames>)"` — the `:property` subname part only,
  which is **empty for plain node paths** — NOT the path string. Use `nodePath.getPath()`
  (the Kotlin `path` property) whenever a path string is needed, e.g. `getPath().getPath()`
  on a Node. `StringName.toString()` is unaffected (it calls the native string operator).
