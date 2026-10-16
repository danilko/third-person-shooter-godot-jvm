# CLAUDE.md — Codebase Reference

Third-person shooter experiment using **Godot 4.7** with the **[godot-jvm](https://github.com/utopia-rise/godot-jvm)** binding
(shipped as the in-project `addons/jvm/` GDExtension; the version in use is stated ONCE, under "Build & Run";
docs: https://godot-jvm.dev/en/1.0/).
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

**godot-jvm version in use: `1.0.0-rc3`** (since 2026-10-14; rc2 from 2026-10-10, rc1 before). This is the ONE
place the current version is written -- elsewhere "rc1" / "rc2" only says when something changed or was measured;
on an upgrade, change this line, `build.gradle.kts` and `addons/jvm/`, nothing else. It is a **GDExtension add-on**
that ships with the project in `addons/jvm/`, so the **standard Godot editor** is all that is needed — no custom
engine build. Keep the Gradle plugin (`build.gradle.kts`: `com.utopia-rise.godot-jvm`) and the `addons/jvm/` add-on
on the same version and upgrade them together -- then `./gradlew build` and one headless probe before anything else
(the rc1 -> rc2 step broke ~100 call sites; see "rc2" under Godot-JVM Specifics; rc2 -> rc3 built with no source change).

Scenes/resources reference scripts by their **source `.java` path**
(`res://src/main/java/com/openworld/.../X.java`). Under godot-jvm `1.0.0-rc1` and later that is the *only* way for a
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
`.gdj` is dependency-only under godot-jvm `1.0.0-rc1`+ and unused here. The two reorg scripts (`tools/reorg_stage1.py`, `tools/reorg_stage2.py`)
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
    light/        #   the LIGHT COMBATANT tier (2.3/F8): LightSim (engine-free brain), LightCombatants (node: VAT
                  #   draw, promote/demote under a budget, shots/blasts), LightLooks, LightBatch (MSG_LIGHT_BATCH);
                  #   AIBlackboard (ai/) = the orders both tiers share
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
                  #   MarkerRegistry (every MARK_ level-design marker by kind / distance / building),
                  #   WaterVolume (swim/float Area3D), WorldBounds (the logic wall),
                  #   ZoneTrigger (fires one story beat, F3), RaceCheckpoint (a race gate, R2)
    manager/      #   world-level singleton systems: Impact/Particle/Decal/Explosion/BulletTracer
  item/           # Pickup (Node3D item base) + PickupBody (the RigidBody3D it rides in the
                  #   world — W15), AmmoRefill station
  carrier/vehicle/ # Vehicle, VehicleWheel, VehicleConfig, VehicleWeaponMode
  game/           # EventBus (AutoLoad signals), GameManager (PLAYING/PAUSED/GAME_OVER FSM),
                  #   PlayerRegistry (AutoLoad — live Player list for AI LOD)
                  #   WorldLedger (world flags, dead story characters, place overrides — the host's)
    event/        #   GameplayEvents (the typed action -> consequence stream, authority only),
                  #   GameplayEvent records, Actor/Spot, CrimeMap — a seam PUBLISHES, systems subscribe
    data/         #   Tables: THE list of data tables (util.DataTable + DataReader: unknown keys are errors)
    profile/      #   PlayerProfile, Economy.transfer, EconomyTable, SafeSave, SaveMigrations
    mission/      #   MissionInfo, MissionManager, MissionObjectiveType, MissionDirector
                  #   (story, F1), ScriptCommand, RaceDirector (R2 street races)
    campaign/     #   the campaign GRAPH: FlagKey, Requirement, Effect, ActivityDef, CampaignLint, GameOverRule;
                  #   content/ = the content packs (Act1) and their mission classes (KonbiniActivity)
    activity/     #   the Activity runtime (typed Java missions): Activity, Plan, Stage, RuleSet,
                  #   ActivityDirector, ActivityHost + FakeActivityHost, ActivityRuntime (AutoLoad)
    encounter/    #   placed fights + guarded buildings (2.2): Encounter (a node a designer drops in), EncounterWaves,
                  #   SiteGuards (guards from the buildings' baked MARK_spawn), Loadouts (character/loadouts.json)
  net/            # NetworkManager (AutoLoad RPC), NetMessageCodec, NetworkController,
                  #   VehicleNetworkController, snapshot interpolators, policies, NetStats, Vec3/Quat
    session/      #   PlayerSession, PersistentPlayerId
  ui/             # CharacterHUD, Crosshair, HUDManager, PauseMenu, RadialMenu, Feed,
                  #   Nameplate (generic billboard, any NameplateTarget), WeaponSlotsUI/Item,
                  #   ScopeOverlay, HitMarker, AreaWarning, GpsArrow, RaceHUD (all self-gated), …
  vfx/            # Binbun3D effect controllers (Java ports of the packs' GDScript): VfxEffect (one-shot,
                  #   plays "main"), MuzzleFlashVfx, SmokeVfx, VfxLight — assets in assets/vfx/
  util/           # ObjectPool, generic helpers
  debug/          # DebugHarness (temporary test-spawn harness; DebugWorld / hosts only, NOT World.tscn -- user
                  #   2026-10-09: no F-key debug in the main world); DebugConsole (backtick) IS in the real game
                  #   too, opened by GameManager (user 2026-10-10: `traffic`, `activity`, `hud 0-3`); test stands —
                  #   DriveTestHost (vehicle physics soak, fixed timeline) and
                  #   HandlingTestHost + ScriptedInputController (step-by-step handling
                  #   cases, each with its control — hosts/HandlingTest.tscn)

src/main/resources/com/openworld/  # .tscn/.tres (internal layout NOT yet remapped to new java pkgs)
  character/Character.tscn, Player.tscn, AICharacter.tscn
  weapon/AR4.tscn, PI52.tscn, …    world/World.tscn, WorldSystems.tscn    ui/…
src/test/java/com/openworld/net/   # headless unit tests for the engine-free net logic
```

> AutoLoads (`project.godot`): `EventBus`, `GameManager` (`game`), `MissionManager`
> (`game.mission`), `MissionDirector` (`game.mission`), `RaceDirector` (`game.mission`), `ActivityRuntime`
> (`game.activity`), `SaveSystem`
> (`game`), `NetworkManager` (`net`), `PlayerRegistry` (`game`), `SpatialEntityGrid` (`world`),
> `FactionManager` (`character`), `ZoneManager` (`world`), `StimulusManager` (`world`).

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

## The system write-ups live in `docs/` (split 2026-10-09, PLAN.md 0.5 / F12)

This file holds only what every session needs. Each system's design record -- what was measured, the traps, the
gates -- is in `docs/<system>.md`, moved verbatim (each file lists its sections at the top). **Read the doc for a
system before changing it, and write new findings THERE, not here.** A reference elsewhere to `CLAUDE.md "<title>"`
means that section title in one of these files (`grep -l "<title>" docs/*.md`).

| doc | what is in it |
|---|---|
| `docs/game-systems.md` | Part D: spatial grid, AI LOD, factions (presets, campaign layer), MissionDirector + ZoneTrigger, SaveSystem, the profile / economy / save v2, the garage, the authoring foundations (GameplayEvents, DataTable, MarkerRegistry, WorldLedger), the campaign graph, the Activity runtime (how a mission is written and tested), placed encounters + site guards (game.encounter), RaceDirector; the AI FSM; EventBus; audio |
| `docs/open-world-simulation.md` | Part E: zone streaming, ambient traffic + the lane graph, traffic by region (traffic.json) + the idle-car recycle + the three car tiers, the old terrain/seam notes, StimulusManager, AISquad |
| `docs/combat.md` | weapons (spread, two-stage trace, the long-ray fix, networked shots/melee/projectiles, damage, VFX, throwables, the blocked-muzzle hint), glass, ladders |
| `docs/enforcement.md` | wanted level, dispatch, gang hangouts, escalation, recovery outcomes, co-op correctness batch |
| `docs/hud-and-map.md` | HUD layout, progress ring, damage indicator, GPS route + baked road map, rear-view mirror, the map's places and grid |
| `docs/animation.md` | the W-series: export pipeline, aim/camera conventions, grip archetypes, IK, holsters, scopes, recoil, shared library, bodies, control rigs |
| `docs/vehicles.md` | the component car (damage, doors, lamps, hull), stopping for people, top speed, armour + helicopter |
| `docs/roads.md` | Road Kit (authoring, rules, mesh build, furniture, signals), road presets, the derived island layout, grades, coast road, expressway, 踏切 rules, signs, dropped kerbs, streaming quiet + clearance gates |
| `docs/island-world.md` | Terrain3D, the land redo, districts, land planning, block ground, safe-house start, the rebuild review batch, the airport, night lighting |
| `docs/buildings.md` | building kits, the library, tones + shop windows, streamed cells, lots, civic plots, logistics, forecourts, interiors (mission + shops), sliding doors, stair ramps, vegetation, shop counters |
| `docs/crowd.md` | the two-tier crowd, island population, the LOD ped body, the VAT tier, holster, gaits, crowd hits |
| `docs/front-end.md` | the title screen (main scene), FrontEnd's after-load actions, QualitySettings (settings.cfg, presets, H3's client-local rule + fairness floors), the settings page, World density (the host's simulation load), the loading screen + warm-up tour |
| `docs/input.md` | the gamepad (F1): the one binding table, the device tracker, analog walk / look rate / aim assist, triggers as pedals, pause vs back, pad glyphs |
| `docs/rail-and-stations.md` | rail reserve + rail mode, stations, signals, street names, paid areas, lifts, station forms, EMU1, boardable trains |

## Godot-JVM Specifics

- **Annotations (godot-jvm `1.0.0-rc1`+ API — the older `@Register*` family is gone).** The plugin runs in the
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
- **rc2 (2026-10-10) moved two things every `connect` touches.** `ConnectFlags` is `godot.core.ConnectFlags` (it was
  the nested `godot.api.Object.ConnectFlags`), and `Object.connect(StringName, Callable)` is gone: the two-argument
  form takes a **`String`** (`connect("body_entered", callable)`); the `StringName` overload needs the flags too.
  `signal.connectUnsafe(callable, flags)` is unchanged apart from the flags' package. The quirks below that are
  labelled rc1 (`Transform3D.times`, `Dictionary.put`, the stale `@Export` wrapper, bound Callables) were NOT
  re-measured on rc2 or later: keep obeying them until one is.
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

## Hand-authoring the island after generation (2026-09-30)

`assets/world_source/HAND_AUTHORING.md` is the how-to for level designers and artists: which record owns each thing,
the Road Kit workflow for roads, lanes and ramps, placing and moving buildings, terrain, and what to re-run after each
edit. The handover itself (freezing the generated records, a stamp that cooperates with the block ground, a Downstream
button, an editor building placer) is PLAN.md NEXT item 12, the last piece of that batch. Until then the generators still own the island's roads and
buildings.

## Known Quirks / Gotchas

- **Godot re-imports a glTF only when the `.gltf` FILE changes; it never hashes the `.bin`** (2026-09-29). A
  geometry change that leaves every accessor's count, offset and bounds identical rewrites the `.bin`, and the
  next bake silently uses the OLD import. Measured: 27 of the island's road and rail pieces had been baked from
  stale imports, some for 8 days. The visible symptom was a rail pier standing in a street that `pier_on_road`
  had dropped from the current glTF. `point_gltf.write` now puts the buffer's sha1 in `asset.extras.bin_sha1`,
  so the JSON changes whenever the geometry does. The same risk applies to any other glTF writer (the Blender
  exports of kit pieces and bodies); to check one, compare `.godot/imported/<name>*.scn`'s mtime against its
  `.bin`.
- **A character's FALL SPEED is `MovementController`'s own field, not the body's velocity.** Moving a body by hand
  and zeroing `CharacterBody3D.velocity` still lands it at the speed it was falling, with fall damage. Call
  `MovementController.clearMotion()` after any hand teleport (WorldBounds' rescues do; `run_net_melee_test.sh`'s 1-in-3
  flake was its harness snapping the client back to the pickup every 0.6 m of fall until it landed at 12 m/s).
- **godot-jvm rc1: `Transform3D.times(Transform3D)` MUTATES its receiver** (`val t = this`, then writes into it) and
  returns it. `a.times(b)` in a loop accumulates every product into `a` (every car part's box sat ~1 m above the
  last). Always call it on a fresh getter result (`getGlobalTransform().affineInverse().times(x)`); `times(Vector3)`
  is a pure `xform`, and `Basis.times` is pure.
- **A godot-jvm `@Export` resource reads as NULL while its node is OFF-TREE.** `car.get("config")` on a freshly
  `instantiate()`d `Vehicle` returns null; it binds when the node enters the tree, which is too late to change
  something `_ready` consumes (`VehicleWheel` builds its ground probe there). Reach the shared `.tres` through the
  resource cache instead — `load("res://.../SPC1Config.tres").set(...)` before any car is built. Found writing
  `probe_road_launch.gd --wheel-sensor`: the `.set` on null aborted `_spawn`, and the probe reported it as
  **"lane never streamed in"**, which is a different failure entirely.
- **An int literal in a `.tscn`/`.tres` for a JVM float property is silently DROPPED** ("Shared Buffer Error: JVM
  expected a DOUBLE but received a LONG") and the default stays: `spring_strength = 14000` did nothing,
  `14000.0` works. Generated scene text must always write the decimal point (`tools/build_vehicle_scenes.py f()`).
- **A long Jolt ray misses a small shape it starts far from** (radius < ~2.4e-4 × start distance: a 5.6 cm
  thigh hitbox from ~230 m). Never trust one long `intersect_ray`/`RayCast3D` to find a hitbox at range —
  weapons go through `WeaponItem.trace`, which re-asks the bodies near the line with short windows
  (`util.RayWindows`); see "A long ray steps over a small, far hitbox".

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
- **godot-jvm rc3: a registered method's Object argument is cast NON-NULL** (`args[0] as FactionTable` in the
  generated registrar; `@Nullable` on the parameter is not read). A `null` from GDScript, or from a signal emit
  (`Signal.emit(..., null, ...)` into a connected `@Register` handler), throws `NullPointerException: null cannot be
  cast to non-null type` and the method never runs. It cost the kill feed and ELIMINATE_ALL missions every kill
  with an icon-less weapon (`characterEliminated` carried a `Texture2D` that was null; it now carries none and
  listeners read `IconRegistry.get(weaponName)`). Never pass a possibly-null Object through a registered method or
  a signal: give GDScript a no-argument entry (`FactionManager.clearRegionTable()`), or send an id/name instead.
- **A fully-qualified annotation is silently NOT registered**: `@godot.annotation.Visible public boolean x`
  compiles and produces no property at all (GDScript `set` does nothing, `get` returns null). Import the
  annotation and write `@Visible`. Found by `probe_gps_route.gd`'s control reading as a pass.
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

