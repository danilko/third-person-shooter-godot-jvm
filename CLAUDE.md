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

**Authority:** AI spawn/despawn is host-only — `load()` instances cosmetic geometry on every peer
but returns early on a non-server client (`net.isNetworked() && !net.isServer()`); clients receive
the bodies through the existing `announceSpawn → MSG_SPAWN → GameManager.spawnReplicatedCharacter`
path, and late-joiners via `sendBaselineSpawns`. `unload()` calls `announceDespawn(characterId)`
before pooling/freeing.

**What streams vs. what's static (a common confusion):** only two things are added on load and
removed on unload — the **AI bodies** and the zone's **`geometry` PackedScene** (instanced as a
marker child, `queueFree`d on unload). Anything authored directly into the `WorldZoneMarker` *scene*
(the debug box from `showDebugVolume`, or any mesh you drop under the marker node) is **static scene
content — it never streams**; it is the persistent zone *footprint/outline*. To make a mesh stream
in/out, assign it to the WorldZone's **`geometry`** field, not as a marker child
(`zones/DebugZoneGeometry.tscn` is an example to drop into that slot). Zones also do **not** carry
their own navigation — AI use the level's `NavigationRegion3D`; nav is a parent/world concern.

**Body recycling is OFF by default (`recycleBodies`, EXPERIMENTAL).** Reusing a full character body
subtree (detach via `removeChild`, re-attach via `addChild`) is **unsafe** in godot-kotlin-jvm: the
body carries a `top_level` camera (`TPSCameraController.setAsTopLevel`), a muzzle-flash
`GPUParticles3D`, and a nameplate `SubViewport`, and re-attaching that subtree leaves them
half-initialised — `get_global_transform "not inside tree"` / `particles is null` errors, then a
native use-after-free **segfault on zone enter** (no AI death required). So `unload()` frees and
`load()` instantiates fresh; correct and stutter-tolerable. Spreading spawns across frames is the
proper perf answer (TODO), not body reuse. The `SpawnPool` + `activateForSpawn` reset path is kept
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
`resources/com/openworld/world/zones/DebugZone.tscn` is a reusable **zone scene** (a `WorldZoneMarker`
with `DebugZone.tres` assigned) — the authoring template / "what a zone looks like" demo (duplicate it
and swap the `.tres` for a real zone; a Blender-exported zone-chunk mesh becomes the optional
`geometry`). One instance is placed in `World.tscn` (`DebugZone` node, ~20 m left of spawn) for an
in-editor walk-test. The `DebugHarness` **F12** key also drops a code-built zone in front of the
nearest player if you want one without editing the scene.

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

### Crosshair

`Crosshair._process` reads `weaponController.getCurrentSpreadDeg() × spreadPixelsPerDeg` every
frame (default `spreadPixelsPerDeg = 100 px/deg`, exported so it can be tuned per scene).
Arms snap outward at `crosshairExpandSpeed = 60` (near-instant on shot) and contract at
`crosshairContractSpeed = 8` (fast enough to track bloom recovery, giving a clear "you can shoot
accurately again" signal). Example pixel values at scale 100:

| Situation | Spread° | Arm offset |
|:----------|:-------:|:----------:|
| Rifle still, no bloom | 0.01° | 1 px |
| Pistol still, no bloom | 0.05° | 5 px |
| Rifle full spray, standing | 0.26° | 26 px |
| Rifle sprinting (6 m/s) | 0.195° | 19.5 px |
| Rifle full spray + sprint | 0.44° | 44 px |

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
- name/colour/weapon ← `NameplateTarget.getNameplateChangedSignal()`. For `Character` that's the
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
their timer is idle.

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
  **Primary, universal fix: the audio node stops *itself* on its own `tree_exiting`** — `WeaponController._ready`
  connects `weaponAudio`'s `tree_exiting` → `weaponAudio.stop`; that signal fires while the node is still
  valid and in-tree, so the playback is released no matter who frees the body or in what order (covers app
  exit too). Belt-and-suspenders: `WeaponController.silenceAudio()` (public) is also called by
  `WorldZoneManager.unload` before it frees/recycles a body (stop a touch earlier, while fully in-tree).
  For any other node that plays audio and can be freed while playing, prefer the **self-stop on
  `tree_exiting`** pattern over a parent/sibling `_exitTree` stop.
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
