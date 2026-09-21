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
                  #   WaterVolume (swim/float Area3D), WorldBounds (the logic wall),
                  #   ZoneTrigger (fires one story beat, F3), RaceCheckpoint (a race gate, R2)
    manager/      #   world-level singleton systems: Impact/Particle/Decal/Explosion/BulletTracer
  item/           # Pickup (Node3D item base) + PickupBody (the RigidBody3D it rides in the
                  #   world — W15), AmmoRefill station
  carrier/vehicle/ # Vehicle, VehicleWheel, VehicleConfig, VehicleWeaponMode
  game/           # EventBus (AutoLoad signals), GameManager (PLAYING/PAUSED/GAME_OVER FSM),
                  #   PlayerRegistry (AutoLoad — live Player list for AI LOD)
    mission/      #   MissionInfo, MissionManager, MissionObjectiveType, MissionDirector
                  #   (story, F1), ScriptCommand, RaceDirector (R2 street races)
  net/            # NetworkManager (AutoLoad RPC), NetMessageCodec, NetworkController,
                  #   VehicleNetworkController, snapshot interpolators, policies, NetStats, Vec3/Quat
    session/      #   PlayerSession, PersistentPlayerId
  ui/             # CharacterHUD, Crosshair, HUDManager, PauseMenu, RadialMenu, Feed,
                  #   Nameplate (generic billboard, any NameplateTarget), WeaponSlotsUI/Item,
                  #   ScopeOverlay, HitMarker, AreaWarning, GpsArrow, RaceHUD (all self-gated), …
  vfx/            # Binbun3D effect controllers (Java ports of the packs' GDScript): VfxEffect (one-shot,
                  #   plays "main"), MuzzleFlashVfx, SmokeVfx, VfxLight — assets in assets/vfx/
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
> (`game.mission`), `MissionDirector` (`game.mission`), `RaceDirector` (`game.mission`), `SaveSystem`
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

#### Presets, wildcard rows and the mission layer (F2, 2026-09-17)

- **The rule has one engine-free owner: `character.FactionRules`** (`FactionRulesTest`, 7 cases).
  `FactionManager.areHostile` and `FactionTable.relationship` both call it. The order is: `neutral`
  is never hostile, then an exact pair (either direction), then a **wildcard row**, then the default.
- **Wildcard row.** `"civilian>*"` (or `"*>civilian"`) means "toward every OTHER faction". It is how
  a preset says "civilians are neutral to everyone" without listing each faction and going stale when
  one is added. It never applies to a faction and itself. If both sides carry wildcards that disagree,
  the LESS hostile one wins, so a civilian stays out of a hostile-to-all faction's fight.
  `FactionTable.row` checks `containsKey` before `get`, because godot-jvm's `Dictionary.get` on a
  missing key is not guaranteed to return null.
- **Presets** in `character/`, beside `DefaultFactions.tres`:
  - `OpenWorldFactions.tres`: player, police, gang_a, gang_b, civilian. Civilians are neutral to all,
    police are neutral to the player and hostile to both gangs.
  - `GangA_vs_Police.tres`: gang_a DESPISES police, the player sides with police, gang_b sits it out
    (`gang_b>*` NEUTRAL).
  - `Faction` gained `POLICE`/`GANG_A`/`GANG_B`/`CIVILIAN` constants and nameplate colours.
- **Three layers, one live table.** The live table is a `duplicate(true)` of the highest layer
  present: mission (`applyMissionTable`), then region (`applyTable`, from `RegionConfig`), then
  `DefaultFactions.tres`. A region change while a mission runs is remembered but does not replace the
  mission's table.
  - Rebuilding the table discards runtime flips. That is the per-mission scope the flips want.
  - `reset()` clears both layers.
- **Missions.** `MissionInfo.factionTable` (`@Export`, nullable) is applied by
  `MissionManager.startMission` BEFORE the ELIMINATE_ALL count and removed on complete and on fail.
  - Clients get it as a resource path in `WORLD_EVENT_MISSION_STARTED`'s second argument
    (`GameManager.applyMissionStarted`). A table built in code or embedded as a sub-resource has no
    loadable path and is not mirrored. That loses nothing today: hostility is only decided on the host.
  - Worked example: `game/mission/GangA_vs_Police_Mission.tres`.
  - `MissionManager.startMissionFromPath` / `completeMissionNow` and `FactionManager.activeLayerNow` /
    `hostileNow` are registered for probes. So is `AICharacter.targetIdNow`.
- **Gate `tools/godot/probe_faction_presets.gd`** (21/21, stable over 3 runs). It uses real AI that
  stand still and think, plus a Player.
  - Control, shipped defaults: the policeman targets the nearest body, the civilian.
  - `OpenWorldFactions` as the region layer: police target a gang, and nobody targets or is targeted
    by the civilian.
  - The mission layer: police and gang_a target each other, gang_b and the civilian are left out, and
    a region change does not replace the layer.
  - Armed with ASR1s through real pickups, police and gang_a damage each other and nobody else.
  - Completing the mission restores the defaults.
  - Probe trap: with `MovementController` off, a target 90° to the side stays past the aim reach and
    W21's fire gate holds every shot. The policeman targeted gang_a for 20 s with a full magazine.

---

### The story layer — MissionDirector (`com.openworld.game.mission`, AutoLoad, F1, 2026-09-17)

The one owner of story logic, beside `MissionManager`, which keeps objective TRACKING. The split is
the whole design: **"may this mission run" is campaign state; "is it won yet" is not.** Four jobs.

- **NamedCharacterRegistry** — `characterId → live AICharacter`. **Registration has ONE owner,
  `AICharacter._ready()`**, gated on `@Export storyCharacter`; `ZoneManager.spawnNamed` sets that flag
  before `addChild` so a streamed `NamedCharacterConfig` and a hand-placed story AI take the identical
  path. **The flag exists because the ID cannot answer the question** — an ambient AI's id is a random
  UUID and a named one's is authored, and those are the same type of string. A second body claiming a
  live id is refused and reported (which boss you commanded must not depend on streaming order); one
  replacing a FREED node is the ordinary zone reload. `_exitTree` drops the entry, so the map is
  authoritative about "is the boss loaded right now" with no tree scan.
- **`commandCharacter(id, ScriptCommand)`.** `ScriptCommand` is a `Resource` whose every field is a
  command with an explicit **do-nothing sentinel** (`targetState = ""`, `move = false`,
  `invincible = KEEP`), never a mirror of the AI's state — so a partly-filled order cannot quietly
  reset the rest of the body. `move` is a separate flag from `moveTo` because **(0,0,0) is a legal
  destination** (it is the spec's own verify case), so "is the vector set" is not derivable.
  `assignSquad` is code-set rather than exported: a `.tres` cannot hold a node.
- **`triggerBeat(beatId)`** — runs the Java handler registered under that id (beats are methods, not a
  scripting language) and emits `EventBus.missionBeatTriggered` either way, so a beat with no logic yet
  is still an event dialogue/HUD can hang off. `ZoneTrigger` (F3) is the caller that is still missing.
- **The mission-output graph.** A completion folds `(missionId, outcomeVariant)` into an accumulated
  set and re-evaluates an append-only unlock table. **Idempotent on variant** (a replay adds no branch,
  so the tree is bounded by `missions × variants`, not by replay count), **sticky** (a branch once open
  never closes), and unique items granted exactly once via `grantUniqueOnce`'s membership check.
  **Ordinary rewards have no code here on purpose** — there is nothing to gate, and a field nothing
  reads is wrong the day something reads it. It listens to **`EventBus.missionCompleted`**, which fires
  on *every* peer (a client gets it mirrored by `GameManager.applyMissionCompleted`), so every peer's
  graph advances with no new message — and the idempotency is what makes that safe.

**Commands are host-side, and that needs no gate:** only the host runs an `AIController`; a client's
copy of the same body is a puppet, so `commandCharacter` returns false there and the motion it causes
on the host replicates the ordinary way. A beat script may therefore run on both peers without knowing
which it is.

**`ScriptedMoveState` — an order is not a mood.** Nothing in the world cancels it: not sight of an
enemy, not being shot, not gunfire. The autonomous states are the opposite by design, and mixing the
two gives a cutscene walk a passing civilian can derail. The director cancels it (`releaseCharacter`,
or the next command). **A NavAgent off the navmesh does not go silent — it lies:** with no navigation
map under the body it reports `isNavigationFinished() == false` forever and hands back the body's own
position, one tick stale, so the steering vector points exactly BACKWARD along its own travel and
feeds itself — measured on the bare probe stand, the AI ran from 20 m off the origin to **110 m in
30 s**. The agent is believed only while its next point is a real step ahead (`NAV_MIN_STEP` 0.5 m);
otherwise the destination answers. Arrival is likewise asked of the DESTINATION, never of
`isNavigationFinished()` alone — an arrival that is a lie fires the next beat in the wrong place.

**Invulnerability is one flag in one place**, `Health.invulnerable`, checked at the top of
`applyDamage` — the single site every source funnels through (bullet, blast, fall, a relayed client
request), so it can never mean "immune to some damage". `@Visible`, not `@Export`: live mission state,
not something a scene authors. Not replicated — the host is the only peer that applies damage.
`releaseCharacter` clears it with the order, so a beat cannot leave someone immortal.

**A mission vehicle is not ambient traffic** (the `TERRAIN3D_TRANSITION.md` note, now enforced).
`registerMissionEntity(key, node, failOnLoss)` is the declaration; `ZoneManager` asks
`isMissionProtected` in ONE place — before the reclaim, not inside each of the seven reclaim reasons —
and `freeTrafficCar` leaves a protected car and its driver exactly as they are, dropping only the
pairing. From there the MISSION owns them: registering an entity is taking responsibility for it.
Losing one registered `failOnLoss` calls **`MissionManager.failMission`** — the mission system's rule,
never the streamer's. Loss is detected as a FREED node rather than a `Health.died` connection, because
a wreck replaced by a wreck scene emits nothing a mission could hear.

**The debug console** (`debug.DebugConsole`, **backtick** via `DebugHarness`) is F1's stated
prerequisite: iterating a beat in one session instead of one restart per edit. Built in code like
`PerfDebugOverlay`, so no scene wiring; opening it sets `inputBlocked` on every registered local player
and frees the mouse (otherwise typing "state" walks the player and shoots). Its command table is
hand-written, not reflective — a typo in a reflective console is a silent no-op — and everything it
drives is already a `@Register`ed method, the same surface a probe uses, so it can never reach further
into the game than the gates can. `named / move / state / invincible / release / beat / mission
start|complete|fail / unlock / close`, and the weapon commands (the CS `give` / Unreal `summon` idiom, host or
single player only): `weapons`, `give <id>` (straight into the inventory through `requestEquip`), `drop <id>|all`
(a row of pickups 3 m ahead) and `ammo`. They read `weapon.WeaponCatalog`, the one runtime reader of
`weapon_catalog.json` (the aim bench uses it too), so a new catalog weapon is spawnable with no other edit; the
built-in fist is excluded. Gate `tools/godot/probe_debug_weapons.gd` 6/6. The debug HUD (`PerfDebugOverlay`, **Shift+F3** cycles, console
`hud 0-3`) is levelled like CS's `net_graph`: 1 a corner FPS counter, 2 the engine monitors + JVM heap + streaming
+ a `FrameTimeGraph` (240 frames, 60/30 fps lines, avg / 1%-low / max), 3 adds the local player's live state
(position, speed, stance, view, health, vehicle, weapon + ammo + `WeaponState` + spread, what the aim ray is on)
and `NetworkManager.debugNetLine` (rtt, loss, kbit/s from ENet's own statistics). Gate
`tools/godot/probe_debug_hud.gd` 10/10 (`-- --shot=<png>` with a display).

**Gate `tools/godot/probe_mission_director.gd`** (34/34; `-- --control` turns the boss's
`story_character` flag off and fails 11). Real AI bodies on a bare stand, with a **Player in the scene
because an AICharacter with no player within 80 m is LOD-FROZEN and never thinks** — it is also the
hostile the scripted walk must ignore. Cases: the registry (an ambient AI is not in it; a duplicate id
refused; a freed body leaves it), the spec's own verify (`command_move_to` origin → SCRIPTED_MOVE,
20.44 m → **1.20 m in 6.8 s**), the order held for the whole walk past a hostile, an invincible boss
taking **0 hits from a 1e6-damage kill** and dying the moment it is released, beats, the graph (locked
→ wrong variant does not open it → the declared one does → replay adds no branch → sticky), the
director refusing to start a locked mission and starting it once unlocked, a mission entity freed
failing the ACTIVE mission by name, and the console reaching the director. **Not covered, on purpose:**
`ZoneManager`'s half of the vehicle rule needs a streamed zone with live traffic
(`probe_traffic_spawn.gd`'s stand), so what this asserts is the ANSWER the streamer reads.

### The caller the story layer was missing — `world.ZoneTrigger` (F3, 2026-09-17)

F1 built `triggerBeat` and nothing in the world called it. `ZoneTrigger` is an `Area3D` an artist
drops in a scene: the right body enters, it fires one beat, and **that is the whole of it** — mission
start zones, objective markers, ambush triggers and cutscene entries are all the same volume with a
different beat id. What the beat DOES stays a Java handler registered by id on the director, so a
trigger can never become a second place story logic lives; a beat with no handler still emits
`EventBus.missionBeatTriggered`, so an authored volume is useful to dialogue and HUD before any Java
exists for it.

- **"Has this already fired" is the DIRECTOR's answer, not a flag on the node.** `oneShot` asks
  `MissionDirector.beatFireCount(beatId)`, and that is load-bearing rather than tidy: a trigger
  authored inside a streamed zone's geometry is **freed and re-instanced every time the player walks
  away and back**, so a local flag re-arms the ambush on every pass with nothing to see. The
  director's fired-beat log is campaign state and outlives the node — and `resetCampaign()` re-arms
  every trigger with it, which is the same answer for the same reason. `campaignOneShot` is the
  control knob (`@Visible`, always on) that puts the local flag back, and the gate measures it.
- **The mask is not authored.** `_ready` states `CHARACTER | VEHICLE` itself. A seated occupant is on
  collision layer **0** (`CharacterDriveState.enter`), so without the VEHICLE half a player who
  DRIVES to the mission marker trips nothing — and an area whose mask silently excludes the thing it
  watches for looks exactly like a trigger that was never wired. A carrier hands the trigger whichever
  seated occupant qualifies. `carrierAware` is that half's control knob.
- **Every peer fires its own.** The volume is symmetric — a client's copy fires as the client's copy
  of the body arrives — which is the director's own rule that a beat script runs on both peers without
  knowing which it is. A beat whose EFFECT is host-authoritative is gated inside its handler, exactly
  as `commandCharacter` already is. A `hostOnly` flag on the volume would move that decision into the
  scene, away from the only thing that knows the answer.
- **Gates that need no code**, each one export and each one a real authoring case:
  `requiredMissionId` (an ambush does not fire before its mission), `requiresBeat` (objective markers
  in sequence — otherwise marker 2 fires as you walk past it on the way to marker 1), and
  `requiredCharacterId` (the escortee's drop-off, not the player's). `showDebugVolume` draws the box
  or sphere (armed yellow, spent green), off by default — unlike a zone marker there are many.
- **The escort order the verify needed did not exist.** `commandCharacter` could enter `ESCORT` but
  not say WHOM to escort, so `ScriptCommand.escortTarget` (a live node, therefore code-set like
  `assignSquad`) and `MissionDirector.commandEscortPlayer(id)` are new. The target is resolved through
  `PlayerRegistry` rather than passed in, because a beat fires from a volume that knows nothing about
  which player tripped it and in co-op "the player" is whichever one is there.

**Gate `tools/godot/probe_zone_trigger.gd`** (16/16; `-- --control` turns both knobs off and fails
exactly 2). The spec's own verify is case 1 and is a REAL walk — the player's own `PlayerController`
reading the `forward` action — into the volume, which fires the beat, whose listener orders the boss
to escort; the rest teleport, which crosses the boundary the same way. Also: an ambient AI does not
trip a player trigger, a re-streamed trigger node stays silent for a spent beat, the three gates each
refuse and then admit, a player who DRIVES in trips it (mask 18), and a trigger with no beat id is
inert. **What is NOT asserted, on purpose: metres walked while escorting.** The escort MOTION is
`EscortState`'s and is nav-driven, and this bare stand has no `NavigationRegion3D`, where a NavAgent
reports "not finished" forever and hands back the body's own position — so the gate asserts the ORDER
the trigger delivered (the state, and who is being escorted).

**Probe trap, and it is the shared-sub-resource rule from the other side:** a `.tscn`-embedded
`CharacterInfo` is SHARED by every instantiation, and `Character._ready` only privatizes one whose id
is still **empty** — so a probe that stamps the scene's own resource *renames every AI it spawned
before*. Spawning `ambient_01` silently renamed the boss, and the case keyed on `requiredCharacterId`
failed with "not boss_01" while the registry (keyed by the string handed in at registration) still
said the boss was loaded. Both this probe and `probe_mission_director.gd` now build a fresh
`CharacterInfo` per body, which is the codebase's own "own identity in code, not the scene" rule.

### The campaign save — `game.SaveSystem` (I7, AutoLoad, 2026-09-17)

One JSON document per slot under `user://saves/`, written and read with Godot's own `FileAccess`.
It carries the campaign graph, the faction flips, which mission was running, and each player's
position / facing / health / slot manifest. **Which pieces are in it is the whole design**, and four
rules decide it:

- **Progress is saved; AUTHORING is not.** `MissionDirector.declareUnlock` rows say which variants
  open which mission — that is content, re-declared by the same Java every launch. A saved copy would
  be a second owner that goes stale the day the campaign is edited, with the stale copy winning. What
  is saved is only what the player's play produced: the achieved `(missionId, variant)` set, the
  completed missions, the sticky `unlocked` set, the granted unique items.
- **The fired-beat log is campaign state, not a debug counter.** F3's `ZoneTrigger` decides "has this
  already fired" by asking `MissionDirector.beatFireCount`, precisely so a trigger inside a streamed
  zone cannot re-arm when the zone reloads. A save that left the log out would re-arm **every
  one-shot trigger in the world** on load — the ambush you already sprang, waiting for you again —
  with nothing on screen to say why. `SaveSystem.saveFiredBeats` (`@Visible`, always on) is the
  control knob the gate measures that with, and it is 3 of the probe's checks.
- **An interrupted mission RESTARTS; it does not resume mid-flight.** AI bodies are not saved (a
  streamed world respawns its crowds), so a restored "3 of 7 left" counter would be counted against a
  fresh crowd of 7 — a number that is simply untrue. The slot records the mission's id and its `.tres`
  path and `loadSlot` starts it again **through the director**, so the unlock predicate still decides
  whether it may run and a save cannot smuggle a locked mission back in. That is also what GTA does
  with a save taken during a mission. A mission built in code or embedded as a sub-resource has no
  loadable path (the limit `MissionManager` already documents for its client mirror), so it is
  recorded by id and reported as unresumable rather than half-restored.
- **Only what RUNTIME changed is saved of the factions.** `getActiveRelationships()` — the late-join
  net baseline — returns the whole live table, which is a copy of the shipped/authored `.tres` with
  the flips written into it, so saving that would freeze the shipped defaults into the slot and let an
  old save silently win over an edited preset. `FactionManager.runtimeFlips` records exactly the
  `setRelationship` calls that are still live (cleared by `rebuildLiveTable`, which IS the documented
  "a layer change discards runtime flips" rule) and `getRuntimeOverrides()` is what the slot carries.
  The region and mission LAYERS are not saved either: each is re-applied when its region streams in or
  its mission restarts.
- **The host's save is canonical and needs NO new message.** `saveSlot` refuses on a client
  (`save_refused_client`). A load on the host reaches every client through seams that already exist:
  the faction flips ride `FactionManager.setRelationship`'s world event, the mission restart rides
  `WORLD_EVENT_MISSION_STARTED`, and inventory converges through the periodic `MSG_INVENTORY`
  manifest. An RPC here would be a second way to say what the wire already says.

**The player key is the id that is stable ACROSS LAUNCHES, and that is not the same field in both
cases.** A remote player's `characterId` IS their `PersistentPlayerId` (`GameManager.onPeerIdentified`
makes it so on first join), while a locally-owned body carries a per-launch UUID — so the local body
is keyed by `PersistentPlayerId.getOrCreate()`, the id this install would identify as if it were the
client. One rule, both cases, and the key survives a host/client role swap. A record whose body is not
live yet is **held** (`pendingPlayerCount()`) and applied as that body appears, so loading before or
during a scene coming up works, and a client that joins after the load still gets its own record.

**Nothing new was written to read or apply state.** Inventory is `WeaponController.buildInventoryEntries`
/ `applyReplicatedInventory(entries, addOnly=false)` — the N2 manifest path, with `addOnly` false
because the owned-body guard exists to stop a *lag-stale* manifest fighting live input, and a document
read off disk has nothing to race. Health is `Health.applyReplicatedHealth`, which is already the "set
the number, fire no damage event" path; a save taken while dead is not resurrected into a corpse (a
non-positive value is left alone). `MissionDirector.restoreCampaign` is a REPLACE, then
`reevaluateUnlocks()`, so a requirement declared by this launch's code that the restored achievements
already satisfy opens with everything else.

**Autosave** (`autosaveEnabled`, slot 0) fires on `EventBus.missionBeatTriggered` and
`missionCompleted` — the F3 hook I7 asked for, now that a beat has a caller. The debug console gained
`save [slot]` / `load [slot]`.

**Registration shapes that had to be worked around**, all the same quirk: godot-jvm merges a JavaBean
accessor with its field into one property, so a registered `setX` with no getter does not compile and
a registered `getX` with no setter registers READ_ONLY. The probe needed four things GDScript could
not reach, and each is a question-named reader or a differently-named action beside the original:
`FactionManager.flipRelationship` (beside `setRelationship`), `Health.healthNow` (beside
`getCurrentHealth`), `WeaponController.activeSlotNow` (beside `getReplicatedActiveSlot`) and
`MissionManager.missionActiveNow` / `activeMissionIdNow` (beside `isActive`). `FactionManager.reset`
and `Health.applyReplicatedHealth` are not accessor-shaped and were annotated in place.

**Gate `tools/godot/probe_save_system.gd`** (36/36; `-- --control` turns `saveFiredBeats` off and
fails exactly 3). Its method is the spec's own verify, and the middle step is the part that matters:
reach a state, save, **LOSE that state in the same session** (the stand-in for quitting), load, and
find it back — a probe that only saves and loads cannot tell a working restore from a state that never
went away. Cases: the graph (a declared unlock, an achieved variant, a granted unique item), a faction
flip, a real ASR1 taken through the ordinary pickup path with a hand-set magazine, position and
health; the file itself (schema, the four blocks, one player); everything wiped; everything restored,
onto the SAME weapon node rather than a duplicate; a real one-shot `ZoneTrigger` dropped on the player
after the load staying silent; the running mission recorded with a loadable path and restarted; and a
missing slot refused rather than half-applied. **The faction flip has to DIFFER from the shipped
default or it is unobservable** — two different factions are hostile by the inherent rule, so a flip
to HOSTILE proves nothing and the case uses FRIENDLY (it cost one false pass first).

**Not covered, on purpose:** the client refusal and the co-op mirror need two processes
(`tools/net/run_net_*.sh`'s shape), so what this asserts is the ANSWER each seam reads. World entity
state — which AI are dead, which pickups are gone, where the traffic is — is **not** saved at all, and
that is the boundary the mission-restart rule above is drawn around.

### Street races — `game.mission.RaceDirector` + `world.RaceCheckpoint` (R2, AutoLoad, 2026-09-17)

GTA SA/VC-style checkpoint races over the existing road network, and the **first objective type
beyond ELIMINATE_ALL with real logic**. `MissionObjectiveType.RACE` had been schema only since C1.

**Where it sits is the F1 split, applied again.** "May this mission run" is `MissionDirector`'s;
"is it won yet" is `MissionManager`'s — and a race is the second kind, so `MissionManager.startMission`
hands a `RACE` mission to `RaceDirector` and the director hands the answer back through
`completeMission` / `failMission`, exactly as the ELIMINATE_ALL counter does. It is a separate class
rather than another branch in `MissionManager` because a race carries live per-racer state (progress,
laps, placings, a clock) and a per-frame tick that no counter-shaped objective has.

- **The route is checkpoints in index order, and they register themselves.** `RaceCheckpoint` calls
  `registerCheckpoint` in `_ready` and `unregisterCheckpoint` in `_exitTree` — the
  `Character`↔`SpatialEntityGrid` idiom — keyed by `raceId`, so a circuit authored inside a streamed
  zone assembles and disassembles itself with no tree scan, and a world holds as many circuits as it
  has names. Two gates claiming one index is refused and reported (`MissionDirector`'s duplicate-id
  rule, same reason: which gate is #2 must not depend on streaming order).
- **A checkpoint reports; it does not adjudicate.** It tells the director "this body touched index N"
  and nothing else. **Only the racer's OWN next index counts** — so driving back through a gate you
  already took is not progress and cutting the course cannot skip one — and that rule lives in one
  place because it is the same rule for every gate in the world. `orderedCheckpoints` is the control
  knob (`@Visible`, always on) that puts the naive "any untaken gate counts" implementation back, and
  the gate measures the difference rather than asserting it in prose.
- **The racer is the CHARACTER, never the vehicle**, keyed by `characterId` — the id the whole net
  layer already uses. A racer who wrecks their car, steals another and drives on is the same racer;
  one who bails out and runs the last 50 m finishes on foot, which is what GTA does and what falls
  out of keying on the driver. A carrier hands the gate **every** seated occupant, because who is
  enrolled is the director's answer and a passenger who is a racer has as much claim to the gate they
  were carried through as the driver.
- **The mask is not authored**: `CHARACTER | VEHICLE`, stated by the node, for `ZoneTrigger`'s reason
  — a seated occupant is on collision layer **0** (`CharacterDriveState.enter`), so a gate watching
  only CHARACTER is invisible to every car in the race, which looks exactly like a gate that was never
  wired. Likewise a gate with no authored `CollisionShape3D` states a default cylinder: an `Area3D`
  with no shape detects nothing and says nothing about it.
- **Enrolment needs no authoring.** Every live `Player` races (in co-op that is the whole session,
  the only default a mission cannot get wrong); AI racers and anyone else come from `addRacer`, which
  works mid-race so a late joiner is not a special case.
- **The MISSION ends when every HUMAN has finished**, not when the first one does — a co-op partner
  two corners behind would otherwise be cut off mid-race. The variant is `WON` if any human took place
  1, else `FINISHED`. AI racers keep their places and can end nothing: the mission is the players'.
  `MissionInfo.timeLimit` — declared since C1 and never implemented — is the time trial's clock here,
  and running it out calls `failMission`. Only the host may fail on the clock: two peers failing one
  mission is two events for one fact.
- **`endRace` FREEZES rather than wipes.** The placings, the clock and the roster stay readable until
  the next `startRace`, because the moment a race ends is exactly when the results are wanted — by the
  finish panel, by a beat that reads who won, and by a probe. Only `raceActiveNow()` changes.
- **Standings** are checkpoints cleared, then distance to the next gate, recomputed at 4 Hz. Cheap and
  exact enough for a HUD list; the only authoritative place is a FINISHED one, fixed when it is set.
- **A race that cannot be finished is refused, loudly.** Fewer than two gates under that `raceId` and
  `startRace` says so and does not start: a race silently running with no route is a mission the
  player can never complete, and the cause (a mis-typed name, or a zone that has not streamed) is
  invisible from the HUD.

**Authoring costs one field and one marker prefix.** `MissionInfo.raceId` (empty = the circuit named
after the mission — the case that needs no second name) and `raceLaps`; `WorldBaker` bakes
`race_<raceId>_<idx>` empties into gates, the same `<name>_<n>` convention `lane_`/`spawn_` already
use, with `radius`/`height` metas. **Shift+F4** on `DebugHarness` drops a four-gate circuit around the
nearest player and starts a one-lap RACE mission over it — through `MissionManager.startMission`, so
it exercises the shipped path rather than a shortcut.

**AI racers are the shipped traffic brain plus ONE behavioural exception.**
`VehicleAIController.racing` makes `shouldYield()` false: a race runs on a closed course, and
first-come-first-served right of way at every junction is exactly what makes an AI racer finish last.
Everything else a racer wants — a higher `cruiseThrottle`/`cruiseSpeed`, a bolder `cornerLateralAccel`
(3.2d's corner-speed governor) — is already an exported number, so a racer is TUNING plus that one
flag rather than a second controller.

**The HUD polls, and a race is not a SITUATION.** `ui.RaceHUD` (countdown, clock, position, lap and
checkpoint count, and the boost meter `Vehicle.getBoostFraction()` has exposed since the vehicle
overhaul with no gauge) is self-gated like `WeaponProgress`/`ScopeOverlay` and deliberately **not** in
`HUDManager`'s `BASE_LAYOUT`: a race is orthogonal to ON_FOOT/VEHICLE — you can finish one on foot —
so the table could only hold a stale answer. **A race therefore needs no `EventBus` signal of its
own**: the HUD polls, and the one event anything else cares about is the mission completing, which
already exists. `ui.GpsArrow` points at the racer's next checkpoint while a race runs and at the
player's own waypoint otherwise — DERIVED, never latched, because a race that WROTE the waypoint would
clobber the destination the player set before it and not give it back (W29's rule for the view
preference, applied to the waypoint).

**Replication is three constants and no new message.** `WORLD_EVENT_RACE_START` (key = raceId,
value = the countdown still to run, args = missionId, laps, then a `characterId` + `"0"/"1"` human
flag per racer — the ROSTER rides in the event because a client cannot re-derive which AI the host
enrolled), `_CHECKPOINT` (the RESULT — nextIndex and lap — not a delta, so a dropped grant is healed
by the next one) and `_FINISH`. **The race ENDING needs no event of its own**: it is the mission
completing or failing, which already replicates, and `RaceDirector` listens to those two signals on
every peer. Only the host grants a checkpoint (`onCheckpointTouched` returns immediately off the host)
and only the host decides a finish. Late join replays the start plus each racer's progress as *the
same events* a live race sends (`NetworkManager.sendBaselineRace` → `sendWorldEventTo`, new, and now
the shape every baseline can use), so a joiner runs the path a live event already exercises.
**The payload's shape has one owner**: `RaceDirector.startArgs` builds it and
`RaceDirector.applyRemoteStart` parses it, next to each other on purpose — an off-by-one between a
builder here and a parser in `GameManager` shows up as "the client thinks the AI is a human and waits
for it to finish", with nothing on either peer to say so. `GameManager`'s three `applyRace*` are pure
routing.

**Gate `tools/godot/probe_race.gd`** (42/42; `-- --control` turns `orderedCheckpoints` off and fails
exactly 4, with no cascade — each later case restarts the race, and the knob's only effect is whether
an out-of-order touch counts). Real Player, Vehicle and AICharacter bodies against the real AutoLoads,
started the shipped way (a `MissionInfo` written as a `.tres` and handed to
`MissionManager.startMissionFromPath`), never by calling `startRace`. Cases: a mission naming a
circuit that is not there does not start a race; the countdown holds the clock AND refuses a gate
cleared during it; the ordering rule (out of order, in order, and back through the one just taken);
the GPS target and the self-gated HUD; the lap closing into a finish and the mission completing as
`WON`, with the results still readable afterwards; two laps of the same four gates; the time trial
failing the mission; a **car** carrying the racer clearing a gate (mask 18); an AI racer enrolled
mid-race and scored by the same rules; standings; the `racing` exception measured on two real cars in
a real `IntersectionZone` (ambient yields, the SAME brain with the flag on does not); the co-op mirror
(the host's own wire payload fed back through `applyRemoteEventCsv` rebuilds its roster, and a
mirrored checkpoint/finish lands); and a duplicate index refused / a freed gate leaving the route.

**Not covered, on purpose:** the AI racer's LANE-FOLLOWING — a bare stand has no road network, and
driving a lane is `probe_road_traffic`'s and `probe_traffic_spawn`'s gate, not this one's; and the
two-process co-op run (`tools/net/run_net_*.sh`'s shape), for which what is asserted is the ANSWER each
seam reads. Race state is also **not saved** (I7's boundary): an interrupted race restarts with its
mission, which is the rule a fresh crowd already forced on every other objective.

**Probe traps.** The junction arbiter registers a car on `body_entered` and skips one with no
`VehicleAIController`, so a brain attached AFTER the car is already inside the volume is never
registered and reads as "not yielding" for the wrong reason; and re-attaching a brain to flip `racing`
loses that membership the same way (`VehicleProbeHelper.setRacing` flips the flag on the brain already
in the junction). Two helpers were added there rather than registering `attachController`/`shouldYield`
on the gameplay classes: a probe-support node exists precisely so a test does not add engine-visible
surface to `Vehicle` and `VehicleAIController`.

---

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
> away"). The water shader (now `assets/vfx/water/water_common.gdshaderinc`, Binbun3D CC0) samples 256 px seamless noise in WORLD space (a tile every 5 m in DebugWorld,
> 40 m in World; foam every 2 m) and read the waves at one fixed mip level, so far water aliased into a speckled
> grid of repeated pixel squares — measured on a Vulkan screenshot, not guessed. Now fragment samples use
> automatic mipmaps with anisotropic filtering, a second layer at `far_scale_ratio` (0.125 = 8x bigger features)
> fades in between `detail_fade_start` and `detail_fade_end` (40-320 m from the camera), the foam shape does
> the same, and the normal map flattens toward `far_normal_strength` far out. Near water is unchanged
> (before/after screenshots compared). Vertex displacement still uses the fixed LOD (no derivatives there).
>
> **The dark band under the horizon was the SKY, past the edge of a finite sea** (PLAN.md 3.7, 2026-09-18). Sky3D
> paints every direction below 0° elevation as `ground_color × scatter` (a dark grey), and the sea box ends 8 km
> out, so from any altitude its edge sits a few degrees under the horizontal line and the sky's "ground" filled
> the gap: measured with `tools/godot/shot_horizon.gd` (needs a display; `--mark-sky-ground` paints that colour
> magenta), the band turned magenta, 0.19/0.26/0.32 against a 0.78/0.86/0.92 sea, from 400 m and 1500 m. The fix
> is an ocean that reaches the horizon, not a repainted sky: `WaterVolume.farOceanExtent` (100 km in both worlds,
> the camera's far plane) lays four flat quads round the surface box in the same water material, no collision.
> What is left is under 1° past 100 km (6 px at 1500 m), and **`SkyDome.ground_color`** (the owner: the Sky3D
> script writes it into the material at startup, so editing the material's `shader_parameter/ground_color` alone
> does nothing) is (0.75, 0.85, 0.95), measured to within 0.03 of the far sea. From 400 m nothing is left.
> DebugWorld looks the same before and after: from altitude it renders as haze with no horizon line.
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
Since 3.2d cars also hold a CORNER SPEED, `sqrt(cornerLateralAccel·R)` braked for ahead of every bend on the
lane (`VehicleAIController.cornerSpeedLimit`, 4 m/s²; see "The touge, driven and fixed").

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
  (`GN_PointProfile`, `point_style`, `assets/world_source/kits/road_kit/road_kit.blend` via
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
can only slide along its road.

**`Auto Setback` IS IDEMPOTENT NOW, AND THE DISTANCE COMES FROM THE ARMS ALONE** (2026-09-17,
`W17` closed). It moved 17 of 35 island mouths on a second press, and on DebugRoads 52, 34, 43, 84
and 69 m on five presses, the fifth turning an AUTO arm round. Three inputs moved with the mouths:
- **The search start.** `recommended_tail_length` grows ×1.3 from `start`, and its overshoot is not
  monotone, so the start is part of the answer (DebugRoads' east pad: 42.4 m from 5, 57.9 from 12,
  50.7 from 30). `auto_setback` passed the widest mouth, so each press fed the next. And
  `solved_setback`'s default was `start=0.0`, and `0 × 1.3` never grows, so the seeder only ever got the
  corner term and never ran the turn search. The default is `None` now, the search's own 12 m, for
  every caller. **Consequence: an unlocked mouth further out than the solve comes IN**
  (RoadKitSample's provisional 14 m mouths go to 12). The override is `setback_locked`, which the
  setback handle and a mouth drag already set.
- **The centre.** The mouths' centroid moves when a mouth slides. `point_solve.axis_crossing` is the
  least-squares point nearest every mouth's axis LINE, which a slide along that line does not move.
- **An AUTO axis is a chord through the opposite mouth across the pad**, so the passes repeat to a
  fixed point (`SETBACK_SETTLE_TOL` 1e-5 m; DebugRoads settles in 3 passes).

A mouth is never slid over the station beyond it: it stops `point_validate.MIN_MOUTH_CLEAR` (10 m)
short along its axis. `auto_setback(clamped=)`, the CLI's `clamped` list and the dock message name it,
with the gate's remedy (delete the station or lock the mouth). Measured: DebugRoads settles on press 1
(58.6 m) and moves 0 on presses 2–4, and RoadKitSample the same (2.0 m, then 0). `point_solve`
self-test (21) builds a crossing whose two roads bend through it, with four AUTO mouths whose axes
pass metres from their centroid. On it, presses 2–4 move nothing, the seeder's number equals the
solved one, and a station 22 m out holds its mouth 10 m short. Controls: HEAD's `auto_setback` fails
"press 2 moved mouths", and the old single pass drifts 1.79, 0.99, 0.68 m on successive presses.
DebugRoads' committed record was not re-pressed: its authored east pad is still the shallow 4-arm one
that a press grows to 58 m.

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
`assets/world_source/kits/road_kit/road_kit.blend` with a **fake user** (a `.blend` drops any zero-user
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
materials with the same user counts, every one now `lib=//../kits/road_kit/road_kit.blend`, all 11 baked
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

### A long ray steps over a small, far hitbox: short windows near each body (PLAN.md P0 0.4, 2026-09-17)

User report: "standing, a still enemy, the first scoped shot does not hit". The cause is in the physics engine,
not the aim. **Jolt's ray test against a small capsule fails when the ray STARTS far from it.** A ray aimed
exactly at a capsule's centre reports nothing once the radius is under about **2.4e-4 × the start distance**.
`tools/godot/probe_ray_capsule.gd` measures it on bare capsules:
- a thigh-sized capsule from 250 m: 28 misses in 400 rays;
- the same from 5 m: 0;
- from 5 m with the ray carried 500 m PAST it: 0.

So the start distance matters, not the ray length. A float32 discriminant cancelling in the analytic
ray-capsule solve fits every case. For this character's hitboxes the unsafe distance starts at 60 m (hand_l,
r 1.4 cm), 127 m (hand_r), 200 m (arms, feet), 232 m (thighs, r 5.6 cm) and 540 m (spine_03).

In DebugWorld (`probe_sniper_world.gd`, thigh at 250 m, still target, player standing) the probe's scope
line hit the thigh, while the shot's own report ended on Terrain3D **490 m out**. The bullet had gone
straight through the hitbox. A per-frame monitor measured the physics server's bone transform equal to the
node's (≤ 4 mm), and a ray at the drawn thigh centre hit NOTHING on ~8% of frames.

**The fix is the Source/CS split** (`WeaponItem.trace` → `nearerSmallShape`):
- The long query still answers the WORLD.
- Every character or vehicle near the line is then asked again with a short ray that starts a few metres
  before it. Engine-free `util.RayWindows` (+ `RayWindowsTest`) decides the windows:
  - only bodies whose root is within `REACH` 3.5 m of the line, between `SAFE_START` 20 m and what the long
    ray reached;
  - each window runs `LEAD` 4.5 m either side of the root, so it never starts more than 8 m from its shape
    (safe for r > 6 mm);
  - overlapping windows coalesce only up to 12 m, so a crowd does not become one long query again.
- The bodies come from `SpatialEntityGrid.querySegment` (new; cells along the segment's XZ, radius REACH
  + 12 m for grid staleness), or the "characters" group where the AutoLoad is absent. A seated occupant is
  covered by the vehicle's own window.
- `resolveSightPoint` runs the same pass on the RayCast3D's result. Otherwise the sight point landed on the
  ground BEHIND the target, and a third-person muzzle leg converging there passes beside it.

Both the local shot and the host's `resolveServerShot` go through `trace`, and the queries honour the AimRay's
mask and exclusions. No cost is added under 20 m. `WeaponItem.smallShapeWindows` (`@Visible`, always on)
exists only for the control.

Gate `probe_sniper_world.gd -- --from=-150,60 --only-dirs=67.5,90 --dists=250 --bones=thigh_l --repeat=20`:
**40/40**; `--control` 3 true misses (earlier runs of the unfixed code: 5/40, 6/36). The probe gained
`--repeat`, `--only-dirs`, `--bones`, `--monitor=N` (a per-frame ray at the drawn bone with the server
transform) and `--verbose`. A miss prints the shot's `last_shot_report` (now with pellet end points) and a
retrace of it. **If the engine is upgraded, rerun `probe_ray_capsule.gd`**: 0 misses on its far cases
means Jolt was fixed and this pass could go.

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

**Lag compensation for hitscan (PLAN.md N5, 2026-09-18).** A client draws a remote body at its newest host
snapshot dead-reckoned forward (`SnapshotInterpolator`), so what it aims at is where the body was a round trip
ago. The host now resolves a client's shot against THAT moment:
- **`MSG_SHOT` carries `viewTimeMs`** (i32, the host's clock): the newest host snapshot's timestamp plus the time
  since it arrived, capped like the interpolator's projection (`NetworkManager.hostViewTimeMs`,
  `SnapshotInterpolator.DEFAULT_MAX_PROJECTION_SECONDS`).
- **The host keeps ~1 s of every character's ROOT position** (`net.LagCompensator.record`, every physics tick
  while a client is connected, in `NetworkManager._physicsProcess` at the moment and on the clock snapshots are
  stamped with, so the view time and the history are one timeline). Engine-free `net.LagCompensation`
  (`LagCompensationTest`, 6) owns the ring buffer, the wrap-safe age and `MAX_REWIND_MS` 200 (Source's
  `sv_maxunlag` idea: the view time is the client's word, so the cap is all a forged one buys).
- **Rewind = move the hitbox bones, trace, restore.** Every live body whose rewound chest is within 3 m (+ the
  cone) of the shot line has each `PhysicalBone3D` (`Character.hitboxBones()`) shifted by root-then minus
  root-now straight in `PhysicsServer3D`; `FirearmItem.resolveServerShot` runs; the bones go back. Nothing in the
  scene tree moves. **The bones are KINEMATIC, and Jolt applies a kinematic body's new transform only at the next
  step**, so a query in between still sees the old place (measured: every rewound shot went through the target to
  the wall). Each moved bone is made STATIC for the trace, which Jolt moves at once, and given its mode back.
- Position only, not pose or facing: within 200 ms a pose moves centimetres and a strafe a metre.
- `NetworkManager.lagCompensation` (on) is the control knob; `debugSendDelayMs` holds every outgoing message
  (test latency, 0 in the game). Counted `shot_rewound`; `debugShots` prints each rewind.

Gate **`tools/net/run_net_lag_test.sh`** (`debug/NetLagTest.tscn`, `NetLagTestHost`; 80 ms held each way): a
client taps an ASR1 through `Input` at a target walking 2.3–3 m/s side to side 15 m out, aiming from its real
camera at the chest it DRAWS, only mid-sweep. Rewind **23/23** hits (median rewind 175 ms = the round trip);
control (`--no-rewind`) **0/23**. Measured on the way: at the reported view time the host history matched where
the client drew the target to 0.004–0.07 m. **Probe traps**, both of which read as a rewind defect: aiming from a
guessed eye instead of the TPS camera put the line 0.3 m high; and a SPRINTING target does not agree with itself —
the host AI's sprint leans `spine_03` 10–20 cm lower and further forward than the client's puppet of it, which at
15 m decides hit or miss (PLAN.md 5.1b). `run_net_shot_test.sh` still passes (all checks).

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

### Effects are Binbun3D packs driven from Java (`assets/vfx/`, `com.openworld.vfx`, 2026-09-18)

Explosions, muzzle flashes, smoke and the sea shader come from four CC0 Binbun3D packs, re-organised into
`assets/vfx/{explosion,muzzle_flash,smoke,water}/` with their GDScript rewritten in Java;
`assets/vfx/README.md` is the record (who plays what, what changed from the packs), `LICENSE.txt` the licence.
- **The caller decides when.** Nothing autoplays or loops: `ExplosionManager` pools `poolSize` instances of
  `explosion_scene` (a `VfxEffect`) and `spawnExplosion` plays the next idle one, else the oldest;
  `WeaponItem.playMuzzleFlash()` plays `Muzzle/MuzzleVFX` on each shot (owner and puppet), sped up to fit one
  shot interval; `Vehicle` toggles `DamageVfx/Smoke` (`SmokeVfx`) from its damage tier.
- **The packs' `@tool` root setters never ran in a game** (the children do not exist when the root's
  properties load), so what renders is what the materials hold. Explosion and smoke roots were checked equal
  to their materials and dropped. Muzzle variants SHARE `.tres` materials with different colours and animate
  the glow's alpha on them, so `MuzzleFlashVfx` duplicates its materials per instance and writes its colours.
- A flash points down −Z (the pack's +X was rotated into the scenes), so its instance carries no transform.
- **A blast is sized from its damage radius, by MEASUREMENT** (2026-09-18). Each explosion scene stores
  `blast_radius` (how far its shockwave, the `Rings` layer, clearly-visibly reaches at scale 1) and
  `fireball_radius` (the `Core` layer), written by `tools/godot/measure_explosion_radii.gd` (display; `-- --check`
  re-measures, 15% tolerance — the particles are random and a re-measure varies ~10%). `ExplosionManager.playBlast`
  scales the effect so the fireball covers HALF the damage radius (the zone taking at least 25% of the maximum under
  the quadratic falloff) and scales the `Rings` child on its own so the shockwave expands to exactly the damage
  radius. `explosion_vfx_scale` on a source is now only an extra multiplier (1).
  Two traps it took to get there: world-space particles IGNORE their node's scale (measured: a 3x-scaled blast
  reached 2.42 -> 2.59 m), so every explosion layer is `local_coords = true` (an explosion does not move while it
  plays) and now scales linearly (2.32 -> 7.78 m); and counting every non-transparent pixel overstated the
  shockwave ~3x (a quad's near-zero-alpha corners), so the reach is the furthest pixel over an alpha x brightness
  threshold. Gate: `probe_vfx.gd` (a 7 m blast draws a 3.5 m fireball and a 7 m shockwave; every effect measured);
  pictures: `shot_vfx.gd` draws each shipped blast beside a red ring at its damage radius.
- **The car's damage smoke is half size** (`Vehicle.tscn`, `DamageVfx/Smoke` scale 0.5). The pack's thin smoke is
  6 m quads; trailing a moving car they piled into one flat grey sheet in front of the chase camera. The wreck keeps
  the full-size plume.
- Gates: `tools/godot/probe_vfx.gd` (headless, 33 checks), `tools/godot/shot_vfx.gd` (display, pictures).

### Throwables beyond the frag: pipe bomb, flashbang, smoke, remote charge (2026-09-19)

ONE projectile class flies every throwable, `weapon.GrenadeProjectile` (was `FRG1Projectile`); its scene's
`effect` (`weapon.GrenadeEffect`, ordinal on the wire, APPEND-ONLY) says what happens when it goes off, so a new
throwable is a scene, not a class. Each is an ordinary `ThrowableItem` weapon (`<id>.tscn` + `<id>Projectile.tscn` +
`stats/<id>.tres` + a catalog row), thrown by the CS 1.6 arc with its preview.
- **PIB1 pipe bomb**: `frag`, like FRG1 (user decision: grenade type).
- **FLA1 flashbang**: `flash`, 1.5 s fuse. `world.FlashBang`: anyone with a clear WORLD-layer line from the flash to
  their head is blinded by engine-free `world.FlashRules` (`FlashRulesTest`): full inside 30% of `flash_radius`
  (20 m), linear to 0 at it, times 0.25..1 by facing; `flash_max_seconds` 5. An AI is blinded for real
  (`AICharacter.blind`: `hasLineOfSight` false until it wears off); the local player gets `ui.FlashOverlay` (white,
  fading over the last 1.5 s, built in code). A wall protects completely. `detonates_when_shot = false` on the pickup.
- **SMO1 smoke**: `smoke`, 1.5 s fuse. `world.SmokeCloud`: the Binbun3D big-smoke emitter reshaped into a 5 m dome,
  tinted near-white on its own material copy (the pack's is fire smoke), 18 s; `world.SmokeRules` (`SmokeRulesTest`)
  is its size over time and the sight test. `AICharacter.hasLineOfSight` skips any bone whose line passes through a
  cloud's core (85% of its radius). The id is SMO, not SMG (taken by SMG1).
- **REC1 remote charge** (the pack's C4): `remote`. No fuse; it STICKS to the first surface it touches (GTA's sticky
  bomb) and registers in `weapon.RemoteCharges` on the authoritative peer. The `detonate` action (**B**,
  `UserCommand.detonate`, whatever is held) calls `Character.pressDetonator`: the host / single player sets off every
  charge that character has out, in throw order; a client sends `MSG_DETONATE_REQUEST` (tag 30, channel 1), which the
  host accepts only from the character's owner.
- **Network.** Every effect runs LOCALLY on each peer from the one detonation point, so a flash or smoke needs no
  message of its own: the host blinds AI (only it simulates them), every peer blinds its own player and draws the
  cloud. `MSG_DETONATION` gained the KIND (the weapon id) and the effect byte, and `ProjectileLedger` is keyed per
  attacker AND kind: ordering only holds within one kind (a 1.5 s flash thrown after a 3 s frag goes off first, and
  a remote charge waits indefinitely). A peer with no copy draws the effect from the byte.
- Models from the CC0 Guns & Explosives pack via `blender/tools/import_guns_pack.py` (with PIS1 = Makarov, FRG1 = an
  M67-pattern grenade): one 1024 px colour map each, no normal/metal/rough maps (measured: the pack's normal maps
  change a first-person frame by 0.35/255), full triangle counts (Godot's LODs cover distance).
- Gate **`tools/godot/probe_grenade_types.gd`** 21/21, each thrown the real way (pickup, `fire` through Input): the pipe
  bomb hurts an AI where it lands; the flash blinds an AI in the open (2.9 s) but not one behind a wall (0.0, the
  control) and whites out the local screen; the smoke cloud grows to 4.5+ m and blocks a line through it but not
  one 8 m beside; two charges stick, stay armed 5 s, and go off together on `detonate`, hurting an AI next to them.
  `run_net_launch_test.sh` 22/22 after the wire change. **Not gated:** a flash/smoke/charge across two processes.

### Damage kinds: the target decides how hard a bullet or a blast hits it (2026-09-18)

`Health.hitDamageMultiplier` (every weapon hit: bullet, pellet, melee, applied in `ImpactManager.processHit`) and
`Health.explosionDamageMultiplier` (applied in `ExplosionManager`), the GTA model: one weapon number stays right
for a person and a car at once. Characters 1/1; every vehicle scene (car, motorcycle, boat, plane) 0.4 / 2.5, so a
car soaks gunfire and folds to a rocket. Blast distance is to the target's nearest SURFACE (its collision
shapes' boxes, engine-free `world.BlastFalloff`, `BlastFalloffTest`), not its origin: a rocket on a 4 m car's
bumper used to be a 2 m, 64%-damage hit. Tuning: ATL1 rocket 320 over 7 m (`ATL1.tscn`, injected into the
rocket), FRG1 grenade 220 over 8 m (`FRG1Projectile.tscn`; `FRG1.tscn` for a shot pickup). Result: one rocket
within ~1 m or one grenade under it destroys a 500 HP car, SNR1 needs 9 rounds (was 4), and people die within
~3 m of a rocket / ~2.5 m of a grenade while one SNR1 round still kills. Each explosive also names its own blast
VFX (`explosion_vfx` / `explosion_vfx_scale`, see `assets/vfx/README.md`). Gate
**`tools/godot/probe_explosive_damage.gd`** 15/15 (`-- --control` puts the car back to 1/1 and fails the 8 car
cases); it hits and blasts through `debug/VehicleProbeHelper.weaponHit` / `blast`. The grenade (a
cylinder, 56 x 112 mm), the rocket (84 mm, 0.46 m) and a ballistic shield (SHI1, 0.50 x 0.90 m, not an
in-game item yet) are real-size placeholder models (`blender/tools/make_placeholder_models.py`), in
`weapon_models.json` (the `FRG1` row, `projectiles` for `ATL1_Rocket`, `equipment` for `SHI1`; `build_weapon.py`
checks and exports all of them).

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
| `character_eliminated` | `Health.takeDamage()` | `Signal7`: attackerName, attackerFaction, victimName, victimFaction, weaponName, weaponIcon, headshot |

`GameManager` connects `playerDied → onPlayerDied()` in `_ready()`.
The HUD (`HUDManager`/`CharacterHUD`) connects `characterEliminated` for the kill feed.

---

## HUD system (`com.openworld.ui`)

`HUDManager` (CanvasLayer in `HUDManager.tscn`) owns the on-screen HUD. Two pieces worth knowing:

### The layout: one panel per corner, one background, one palette (2026-09-18)

GTA V's corners with CS2's information, and nothing overlaps (gate **`tools/godot/probe_hud_layout.gd`** 21/21;
pictures `tools/godot/shot_hud.gd`, needs a display):

| where | on foot | in a vehicle |
|---|---|---|
| bottom-left | `Minimap` (150 px) over `FootHUD` health number + bar (and the air bar while swimming) | same |
| bottom-right | `WeaponHUD` (icon cropped to its silhouette and drawn at one common height, `ui.IconFit`; name; magazine large / reserve small; no count for fist or melee); `WeaponSlotsUI` above it is ALWAYS visible at `idle_alpha` 0.6 (PUBG / Valorant / Apex: six slots and a growing loadout should be readable at a glance) and comes up to full for 2.5 s on a switch or an inventory change; `idle_alpha = 0` is the CS behaviour | the DRIVER gets the vehicle cluster: speed (km/h; `imperial` for mph) beside `VehicleStatus`, a top-down damage diagram (body coloured by health, a square per wheel where the wheels really are: white, amber when the tire is damaged, red when flat, pulsing while sliding). No health NUMBER; the car smokes and burns as well. In a drive-by car the compact `WeaponHUD` stacks ABOVE the cluster (always, no swap on aim); the inventory column stays hidden (the weapon wheel shows the loadout). A PASSENGER with a gun gets the weapon panel and column. While a race runs (`RaceDirector.raceActiveNow`) the weapon HUD and column step aside for `RaceHUD`; missions hide anything via `setWidgetEnabled` |
| top-right | kill feed (`Feed`) | same |
| top-left | pickup / mission notices (`StatusFeed`) | same |
| centre | crosshair, `WeaponProgress` ring, hit marker, damage direction, interact prompt just under the crosshair | same |

- **One background**: `ui/hud_panel.tres`, the minimap's translucent black, behind every panel (a `Background`
  Panel in each scene, `WeaponSlotsUI`'s panel style, and `FeedEntry._draw` for feed rows).
- **One palette**: `ui.HudPalette`. Colour means state, never selection: white → amber (health under 50%, a
  quarter magazine) → red (health under 25%, empty); red is reserved for danger. Selection is carried by SHAPE and
  brightness: a white ▶ in the inventory panel's left gutter before the active row, which is full white while the
  others are 70% — readable for colour-blind players. (An inverted white chip was tried first and dropped: the
  outline around black text on white read as bold, smeared lettering.)
- **One outline**: 2 px of 55% black at every size (`HudPalette.OUTLINE` / `OUTLINE_PX`, `ui/game_theme.tres`, every
  HUD `LabelSettings`, the drawn race and area warnings). An outline's width is in pixels, so a constant size gives
  big and small text the same thin edge; the old 3–5 px at 85% made large numbers look heavy.
- **Draw order**: `UnderwaterOverlay` and `ScopeOverlay` are HUDManager's FIRST children, so every panel draws over
  the scope's black surround and the water tint (the health bar was hidden under the scope before). The minimap
  has a thin light rim (`rimColor`) so its translucent disc still reads over black.
- **Underwater tint** (`ui.UnderwaterOverlay`) follows the camera ON SCREEN (`WaterVolume.isUnderwater` of the
  viewport's camera): on foot, first person, a car's chase or cockpit view. It replaced a tint the Character drew
  from its own tick and camera, which is off in a driver's seat, so a car driven into the sea left the screen clear.
- **UI scale**: `display/window/stretch/scale = 0.8` over the canvas_items stretch — everything 20% smaller, still
  scaling with the screen height (the weapon list's text is ~10 px on a Steam Deck, just over Valve's ~9 px floor).
  One number for a future "UI scale" setting (`Window.content_scale_factor`).
- Numbers are Aldrich (`assets/ui/Aldrich-Regular.ttf`); the DSEG7 seven-segment font is gone.
- The local player's own vehicle nameplate is hidden while they are in it (`HUDManager.setVehicleNameplateVisible`,
  the vehicle twin of `Character.applyNameplateVisibility`).

The visibility machinery is unchanged: a `Situation` enum (`ON_FOOT`, `VEHICLE_DRIVE`, `VEHICLE_PASSENGER_WEAPON`,
`VEHICLE_MOUNTED_WEAPON`, derived from `Vehicle.getWeaponMode()` in `situationForVehicle`) and a code table
`BASE_LAYOUT` of table-managed widgets per situation (`FootHUD`, `WeaponHUD`, `VehicleHUD`, `WeaponSlotsUI`,
`DamageIndicator`), with `setWidgetEnabled` / `clearWidgetOverride` runtime overrides that win over the table.
Feeds, crosshair, radial menu, scope, area warning, hit marker, race HUD and the map widgets are self-managed. The
table is **code, not an exported `Dictionary`** — a nested generic `Dictionary` export crashes the godot-jvm
registration scanner (see Known Quirks).

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

### Roads on the map, and a GPS route along them (`world.RoadMap` / `world.RoadGraph`, PLAN.md 4.7, 2026-09-17)

The minimap and the full map draw the road network, and the GPS arrow follows a ROUTE along the lanes
instead of pointing at the waypoint as the crow flies.

- **The network is read from the lanekit sidecars, never from the scene.** The `Lane` nodes a zone
  instances exist only while that zone is streamed, so a route to a waypoint in an unloaded zone would
  have nothing to walk (and `LaneGraph` is built from exactly those nodes). `RoadMap.graph()` takes every
  `ZoneMarker` whose zone streams `.../pieces/<stem>.tscn`, reads `res://assets/world_source/pieces/<stem>
  .lanekit.json` (the convention `build_piece.sh` already uses), and places it with
  `Zone.geometryFrame(marker)` — new, beside `placeGeometry`, so a sidecar lands where its piece does.
  No second road record. Rebuilt when the scene or the set of road zones changes; 16 ms for DebugRoads,
  55 ms for the island (218 lanes, 2.4 MB). The sidecars are in `export_presets.cfg`'s include filter,
  since `assets/` is otherwise not exported.
- **`util.MiniJson`** reads them in plain Java: through Godot's `JSON` every number is a bridge call, and
  a unit test could not run it at all.
- **`RoadGraph` is engine-free** and the successor rule is the runtime's (`LaneGraph.successorsOf`): the
  authored `next` list, else every lane starting within `JUNCTION_RADIUS` of the end minus the direct
  reverse. So a route only makes movements a car could make. Dijkstra over lanes (cost = metres to a
  lane's START) plus `inner_lane`/`outer_lane` lane changes at `LANE_CHANGE_COST` 15 m — without the
  lateral edge a left turn owned by the other lane is unreachable. Start and goal are projections; both
  take every lane within `CANDIDATE_SLACK` 10 m of the nearest, so a player on a two-way street is not
  sent to the end of the wrong carriageway to turn round. The start is snapped in 3D (a body on a
  bridge), the goal in plan (a map click carries the player's height).
- **Re-routing is GTA's "recalculating"**, never a per-frame search: per character, on a new waypoint, a
  rebuilt network, or the body more than `OFF_ROUTE_METERS` 25 m from the route (at most once per
  `REROUTE_SECONDS` 1 s).
- **`RoadMap.gpsTarget` is the arrow's one rule:** the route's point `LOOKAHEAD_METERS` 30 m past the
  body's place on it (which leads a body that is off the road ONTO it first), and straight at the
  waypoint within `DIRECT_METERS` 40 m, past the route's end, or with no route. A race still points at
  the next checkpoint directly. `GpsArrow.followRoads` (`@Visible`, on) is the control knob.
- **Drawing is one owner, `ui.RoadOverlay`**, shared by `MinimapController` and `WorldMapManager`. The
  roads are the BAKED picture (4.7b, below) drawn as one textured polygon; the route is drawn on top in the
  player's colour, simplified at 0.5 m (`Route.drawXZ`, cached), then a thin line from where it leaves the
  road to the waypoint.

Gates: **`RoadGraphTest`** (6, on the real sidecars — a route across DebugRoads' junction into the other
zone's lanes, ending on the nearest lane; 500 random island pairs, every route legal and every
BFS-reachable goal routed) and **`tools/godot/probe_gps_route.gd`** (13/13 on DebugWorld, 12/12 with
`-- --world=island`): the real HUD, the waypoint set by opening the map with `map`, zooming with the
wheel and left-clicking; roads drawn on both maps; the route a legal chain (checked independently from
the same sidecars) that crosses `link -> connector -> spur` and ends on the lane nearest the click; the
arrow's target on the route 30 m ahead; off the road it points at the road (57 deg off the straight
bearing); straight at the waypoint within 40 m; right-click clears. `-- --control` (`follow_roads` off)
fails exactly 2. Not covered: the co-op half (a teammate's waypoint is drawn but routed only for the
local player, by design — each peer routes for itself).

### The road map is BAKED — nothing about the roads is derived per frame (PLAN.md 4.7b, 2026-09-17)

The user asked for the GTA model: a pre-rendered map, a pre-built path graph, and only the route drawn live.
Before this the minimap redrew all 218 island lane polylines every frame (each a list of `Vector2`s and a
bridge call), and every snap measured every lane.
- **`tools/godot/bake_road_map.gd`** (`-- --world=debugworld|island`, `-- --check` writes nothing and exits 1
  on a stale bake) writes `src/main/resources/com/openworld/world/roadmap/<Scene>.roadmap.bin` and `.res`.
  Re-run it after a road build, a zone move or a `WorldBounds` change.
- **The picture (`world.RoadRaster`, engine-free)** covers the map square to the `WorldBounds` wall (without
  a wall, the roads plus 100 m). It is a power-of-two `FORMAT_LA8` image, alpha = road, finest 0.5 m/px and
  at most 4096 px: the island is 4096 px at 1.05 m/px, DebugWorld 2048 px at 0.42 m/px.
  - It paints ROADS, not lanes: each lane is swept at its width and the result is CLOSED by `GAP_FILL`
    2.5 m (grown, then shrunk back with a chamfer distance transform). So the 3 m median of a divided road
    fills in and the outer edges stay put. Without the closing every arterial read as two parallel lines.
  - Mips are the MAX of each 2x2 block, so a 20 m road is still at least a pixel on the whole-island view,
    where an averaged mip chain fades it out.
  - It is saved as a compressed `Image` resource (`ResourceSaver.FLAG_COMPRESS`): island 574 KB, loads in
    ~19 ms with the mips as written. A `PortableCompressedTexture2D` also saved, but headless cannot read a
    texture back to verify it, and a PNG import would regenerate AVERAGED mips.
- **The graph file (`world.RoadMapBake`)** holds the lanes already in world space with their AUTHORED ids.
  `RoadGraph.finish` resolves successors on load by the live rule, so a bake cannot carry a different rule.
  Island 1.0 MB, loads in 12 ms (live: 393 ms parse and index + 87 ms paint).
- **The lookup (`world.RoadIndex`)**: a 32 m cell grid over the whole square, sea included. For each cell,
  with centre c and half-diagonal h: `U = min d(c, lane) + h`, and the cell lists every lane with
  `d(c) <= U + h + CANDIDATE_SLACK`.
  - `RoadGraph.snaps` over the cell list is exactly a full scan for a plan snap. For a 3D snap it is exact
    whenever the nearest found is `<= U`; otherwise it scans, which only happens for a body far above every
    road.
  - A map click 600 m offshore is one array read plus a few lanes; the island's largest cell holds fewer
    than half the network.
- **A stale bake is never drawn.** The bake's signature covers every sidecar's path, placement frame and md5,
  plus the square. On a mismatch `RoadMap` builds live with the same code, prints the reason once, and
  `RoadMap.source()` reads `"live"`. The GPS probe asserts `"bake"`.
- **The full map is the GTA pause map.** It opens FITTED to the whole world (the square), the wheel zooms
  about the cursor, a left drag (past `dragThresholdPx`) pans, a left CLICK (press and release without a
  drag) sets the waypoint, and a right click clears it.
  - Blips are limited to `blipRangeMeters` (400) around the player.
  - The zone load rings are off on both maps (`showZoneRings`): with 14 island traffic zones of 1 km they
    covered the map.
  - Probe readouts: `world_to_screen_now` / `screen_to_world_now` / `road_map_drawn_now` on the map;
    `road_map_source_now` / `road_coverage_now` on the minimap.
- Gates: **`RoadMapBakeTest`** (3):
  - the index agrees with a full scan at 4000 random island points, plan and 3D;
  - every lane sample is on a fully painted pixel, nothing is painted 60 m from a road, the chuo_dori median
    is painted, and 1.5 px past its outer edge is not;
  - a bake read back routes exactly like the live graph on 150 random pairs.

  **`probe_gps_route.gd`**, now 18/18 on DebugWorld and 17/17 on the island. New: the source is the bake,
  the picture is road under the route's ends and empty off the road, the map opens fitted with both wall
  corners on screen, the wheel zoom moves the point under the cursor 0.00 m, and a drag pans without
  dropping a waypoint. `-- --control` still fails exactly 2.

  `tools/godot/shot_road_map.gd` (needs a display) saves the minimap, the fitted map and a zoomed map.
- **Limit:** a junction pad is not in the lane data, so a pad's interior gap wider than 5 m can show as a
  small hole (one on DebugRoads' east junction). The fix is painting pads from the record, not a bigger
  `GAP_FILL`, which would start merging a ramp into its mainline.

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

Source of truth is `assets/characters/godot_chan/merged_animation.blend`, exported by
`blender/tools/export_character.py` to `assets/characters/godot_chan/merged_animation.glb`, which
`assets/characters/godot_chan/merged_animation.tscn` instances and `CharacterVisuals_GodotChan.tscn` drives.
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
of its own to author and nothing in the file said one was wanted. `assets/characters/godot_chan/merged_animation.blend`
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
`CharacterVisuals_GodotChanF.tscn` → `assets/characters/godot_chan/merged_animation_f.tscn` → `assets/characters/godot_chan/merged_animation_f.glb`,
built from `assets/characters/godot_chan/merged_animation_f.blend`.

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
`assets/ui/AssaultRifle_5.blend` (a 5.4 m icon-render leftover) and `assets/characters/godot_chan/merged_animation_bak.blend`.
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

**The workbench shows the fit, per weapon and per body** (2026-09-20, user-asked). Three numbers a line, the
same three `probe_weapon_fit.gd` asserts, where they can be watched instead of read out of a gate's log:
the **stock** against its shoulder anchor, the **support** hand's grip miss beside the REACH it was asked
for against the reach that arm HAS (`reach 0.55 / arm 0.43, +0.12` = the support point is 12 cm past where
this arm straightens, so no solver closes it), and the **gun** against what the body is aiming at. **V**
cycles the mannequin's BODY — discovered, every `CharacterVisuals_*.tscn` beside the reference, so a body
added later needs no edit — and **M** sweeps every bench weapon on it and logs one line each. Read `gun`
first: the bench spawns the mannequin facing +X with the ball 8 m down -Z, so until the ball is moved round
in front (I/J/K/L) the stance's yaw limit clamps the aim and the arms are wherever the clamp left them.
Turning the mannequin's body instead was tried and measurably changes nothing — its MovementController is
not what drives this stand, so the mesh keeps its own yaw.

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
`probe_pose_clip.gd -- --compare=res://assets/characters/godot_chan/merged_animation.tscn --all` diffs every clip against the shipped
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
option in settings. Here, as in CS, a toggled scope comes back after the bolt, and **a reload ENDS the scope, held or
toggled** (user decision, which reversed the first version where it resumed). `WeaponController.onWeaponReload` calls
`endScope()`: it clears the toggle and ignores a held aim button until it is released, so the player re-scopes on
purpose. That also covers the auto-reload after the last round. **The toggle is state that has to be remembered**
(`WeaponController.scopeLatched`, plus `holdSuppressed`), so every end is a CLEAR, not a hide. A switch, a drop or an
unscoped weapon clears it in `applyScopeZoom`. A seat or death clears it in `Character.tickScopeSway`, which the
camera calls every frame in every mode, because `applyInput` does not run in the driver's seat. Otherwise the scope
would pop back up on leaving the car or re-drawing the rifle. `PlayerController` counts a latched scope as aiming, so
combat stays on (the body faces the aim), and the aim-stay beat starts on the tick the toggle ends. `UserCommand.scopeZoom`
is a one-tick edge (`SCOPE_ZOOM_IN/OUT/CYCLE`). `scopeZoomLevel` resets whenever the scope is not raised. The bolt
cycle keeps the scope RAISED (only the zoom drops), so it resumes at its level; a reload does not. `scopedFovDegrees()`
returns the level's FOV, and `TPSCameraController` re-tweens when that changes.
**Look input scales with the zoom** (`TPSCameraController.scopedSensitivityRatio`, CS's `zoom_sensitivity_ratio`,
default 1, 0 = off): mouse deltas × `min(1, ratio × camera fov / unscoped fov)` while raised, read off the live FOV.
This also slows the FIRST level (100 px: 7.00° raw → 2.55° at 20°). Without it the 7.5° level turns 1 px into
~6 screen px.
Gate `probe_sniper_scope.gd`, 80 checks: middle click scopes at level 1 with nothing held and stays up 3 s in combat;
click → closer; wheel up clamps; wheel down → first → OFF (back on the boom, FOV restored); wheel down while off
does nothing; wheel up from off scopes; the look scale (raw 7.000° control / 2.545° / 0.955°, ratio 0.375 = the FOV
ratio); the bolt drops the zoom and it resumes at the closer level; the third click is off; a reload ends a
toggled scope and it stays down after, re-scoping starts at level 1; a reload ends a HELD scope too (back on the boom),
it stays down with aim still held, and pressing aim again scopes; hold +
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

**The melee models come from a CC0 pack (2026-09-18, user-asked).** MEW1 (combat knife, replacing the low-poly
bayonet) and MEW2 (fire axe, replacing its primitive box, scaled 0.60 -> 0.81 m) plus five models that are not game
items yet, MEW3 crowbar, MEW4 spade, MEW5 dagger, MEW6 katana, MEW7 machete (`weapon_models.json` `equipment`),
all from the "Free CC0 Melee Weapons Pack" (3DModelsCC0, credited). `blender/tools/import_melee_pack.py` is the
one-shot record of what was done to each (the pack itself was deleted after import): tip/head forward, edge
DOWN, origin on the grip, textures baked to 1024 px in `assets/weapons/textures/` (`.gdignore`d: each `.glb`
embeds its own), DirectX normal maps green-flipped, height maps dropped. Grips and edges were placed from
per-slice measurements (the handle is the narrow uniform run, the edge the side that thins to ~0), then
checked on a render. The ids follow the series rule; the original generic names live in each row's `real`.

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
decision: CS AWP with resume-zoom, the balance lever for a one-shot rifle; since W33 a reload ENDS the scope
instead, and only the bolt resumes). Two derived facts now,
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
and CHEST shot on the aimed bone (48/48), every limb/edge shot (72/72; was held to 90% at 69/72), scoped move speed **3.20 m/s**, a moving
scoped cone **0.101°** (20× base), hitboxes on the drawn body (0.000 m); `-- --control` (threshold 0, no scoped slowdown, the ordinary stop) fails 3 — stopped chest shots 3/6, limbs 63/72, speed 8.00. Three probe defects it had to
lose first, each of which read as a game bug: the moving case fired on the first frame of acceleration
(0.21 m/s), the run-ups walked the player ~180 m sideways so later shots met the target's own arm in
front of its chest, and a teleport back left the camera rigs settling for a second. **Limbs were held to
90% as "a genuine graze" — wrong:** the 3 misses were Jolt stepping over a small far capsule (see "A long ray
steps over a small, far hitbox", 2026-09-17), and since that fix the gate asserts all 72.

### W34 — THE UNIVERSAL ANIMATION LIBRARY, RETARGETED BY A WORLD-SPACE DELTA (2026-09-18, user-asked)

Quaternius' Universal Animation Library 1 + 2 (CC0, `assets/Universal Animation Library_1/`,
`assets/Universal_Animation_Library_2/`, credited in `CREDITS.md`) is merged into both bodies' `.blend`
and `.glb`: 81 new clips and 16 placeholders replaced, 90 -> 171 clips, `.glb` 13.5 -> 23.4 MB.
`blender/tools/retarget_ual.py` is the tool and `blender/tools/ual_retarget.json` the table (`clips`:
source -> new name; `replace`: an existing action -> a source clip or `A+B`, written INTO that action so
the AnimationTree needs no edit). Re-running is idempotent; `--only a,b` rebuilds some. Then
`export_character.py`, `godot --headless --import`, `check_character_anim.py` (both bodies).

- **Why not a name copy.** The library is a UE-mannequin rig whose bone NAMES match Godot-chan's (bar
  `root`/`Root`, `Head`/`head`, the `*_leaf` bones), but rolls and lengths do not. Both rigs rest in a
  T-pose facing -Y (measured), so each bone takes the source's world rotation relative to its own rest:
  `R_t = R_s @ R_s_rest^-1 @ R_t_rest`. Positions come down the TARGET's chain; the pelvis takes the
  source pelvis scaled by the rest pelvis heights (0.839). Root is held at the pose it has in the clip
  being replaced (else `upright_idle`), so a ring's Root baseline does not move.
- **Auto-Rig Pro was not used.** Its Remap would do the same job interactively, but in headless Blender
  5.2 it fails to register (draw-handler errors) and it is driven by scene/UI state, so it is not a
  reproducible build step. Converting the rig to ARP/Rigify would rename the bones every modifier and
  the Java address — the deform skeleton is already a game skeleton; keep it.
- **Replaced:** `drive_idle` <- `Driving_Loop` (a real seated, hands-on-wheel pose); `attack_jab_fist` /
  `attack_cross_fist` <- `Punch_Jab` / `Punch_Cross`; `attack_stab_mw1` <- `Punch_Cross` (a right-hand
  thrust); `attack_slash_mw1` <- `Sword_Regular_A+…_A_Rec`; `attack_swing_mw2` <- `Sword_Regular_B+…_B_Rec`;
  `attack_chop_mw2` <- `Sword_Attack`; `swim_idle`/`swim_back`/`swim_left`/`swim_right` <-
  `Swim_Idle_Loop`, `swim_forward` <- `Swim_Fwd_Loop`. No crawl exists in the library (crawl stays
  placeholder); `LayToIdle` arrives as `crawl_stand_up`.
- **A clip the tree plays through an ARMS filter is baked arms-only** (`{"src", "arms_over"}` in the
  table). The Attack one-shot takes `spine_03`, neck and the arms from its clip, but the shoulder-aim
  modifier squares the chest to the aim during a swing, so what survives is the arms relative to a
  square chest. Retargeted whole-body, a sword clip's arms were solved inside a torso twisted 60-90 deg
  into the lunge, and on the game's square torso the axe swept BEHIND the body (user-reported, seen in
  real-renderer shots). Now every bone but the clavicles-down holds `upright_idle`'s first frame and the
  arms keep the source's WORLD directions: the swing arcs in front. The lunge and torso twist are lost;
  getting them back means letting the aim modifier stand down during an Attack one-shot (code).
- **Fist, melee and throwable all hold the FIST's guard** (user decisions, settled in W36): `Punch_Jab@0`,
  arms-only. For melee and throwable the right WRIST alone is turned so the held handle stands up, 20 deg
  forward (`fist_axis` in the table). The draw clips are that pose too (`weapon_switch_*` were pistol copies).
  `Sword_Regular_B` is the SECOND hit of the library's combo -- it starts with the arm already raised --
  so no one-off swing may use it; the axe's light swing is `Sword_Regular_A` + its recovery.
  `probe_weapon_archetypes` expects **5** hand-pose clusters.
- **Swim is two postures, and the gate says so.** Treading water is UPRIGHT (chest at the water line),
  the stroke HORIZONTAL; one blendspace between them moved the gun centre 0.41 m. `check_character_anim`
  now has `swim_tread` and `swim_stroke` rings (7 rings, bob 0.15 for a stroke). Swim is still unwired
  (the stance borrows `Crawl`); wiring it is a Transition tread <-> stroke, the GTA shape.
- **The seated eye moved**, so `Vehicle.tscn`'s `Seats/Seat0/CockpitCameraMount` is re-measured in the
  seat, in combat (W11's rule): (0, 0.870, 0.057) -> **(0, 1.031, 0.367)**, `probe_vehicle_views` 0.006 m
  from the driver's eye. `probe_cockpit_eye` (combat off) now reads DriveCarrier +1.028 up / +0.337 fwd.

Gates: `check_character_anim` PASS on both bodies (171 clips, 104 orphans WARN), `probe_vehicle_views`,
`probe_driveby_aim`, `probe_melee`, `probe_character_variant` PASS. Study renders: import the retargeted
action in a scratch copy of the `.blend` and render with Workbench before wiring a clip.

### W35 — HIT FLINCH, RAGDOLL DEATH, PASSENGER SEAT, GRENADE THROW, LEDGE CLIMB, AND THE MELEE GRIP (2026-09-18, user-asked)

The W34 clips wired in. Tree edits are `tools/patch_tree_w35.py` (idempotent, both bodies). Gate
**`tools/godot/probe_w35_anims.gd`** 13/13; `-- --control` (climbing off) fails exactly the 2 climb checks.

- **Hit reaction = a torso flinch, never the arms.** `HitReact` is a OneShot filtered to `spine_01..03`,
  `neck_01`, `head_2` near the end of the chain, fed by `HitReactClip` (`hit_chest` | `hit_head` on a
  headshot). L4D plays gesture-layer flinches; CS plays none and punches the view. The arms stay with the
  aim modifiers, because the shot leaves from the muzzle and a flinching arm would move it.
  `Health.playHitReaction` runs where damage is applied and, from `handleDamageBroadcastMessage`, on every
  other peer (no new message). A killing hit plays none. Skipped for a non-ACTIVE LOD AI.
- **Death stays the ragdoll.** It already pushed the struck bone along the bullet (CS's model) and is
  directional; a death clip falls one way whatever hit it. So `death_fall_back` is DROPPED
  (`ual_retarget.json` `drop`). Two fixes: a blast pushed only LIVING bodies (`ExplosionManager`), and a
  push with no struck bone fell through both branches of `CharacterRagdoll.applyHitImpulse`. Now a blast
  kill is pushed too, shared across every bone and lifted 0.6: +0.76 m vs -0.09 m without.
  Seated death is unchanged (the procedural slump over the new drive pose; `probe_dead_driver` passes).
- **Passenger:** `StanceTransition` input `Passenger` -> `PassengerMovementBlend` (`sit_idle` x5).
  `AnimationController.onSetStance` swaps `DriveCarrier` for it when the live body `isSeatedPassenger()`,
  so aim limits and drive-by rules stay the DriveCarrier stance's. `check_character_anim` has a `passenger` ring.
- **Throw:** `attack_throw` (`OverhandThrow@6:32`, arms-only) on `AttackClip`, played by
  `ThrowableItem.useWeapon` and `playRemoteFireCue` (`throwAnimation`, `throwAnimationSeconds` 0.8). The
  grenade leaves on the PRESS, so the clip starts with the arm cocked (the windup is frames 0-6, the
  release ~8): the release lands ~80 ms after the press. FRG1 is now visible in the hand (`SocketThrowable`).
- **Climb: REMOVED in W39** (user decision: CS keeps movement to walk / step / jump, and a climb added a
  kinematic override of the body and an animation the network did not carry). `climb_up_1m` stays in the
  clip library, unwired.
- **The melee grip is the SOCKET's, derived from the hand** (user-reported: the axe poked forward out of
  the fingers). A handle runs through the curled fingers, pinky knuckle -> index knuckle, and the edge
  faces the knuckles. `SocketMelee` (and the new `SocketThrowable`) are that frame, computed from the
  rest skeleton in `hand_r`'s space, not guessed: a 90-degree rotation about the old socket's X was tried
  first and put the axe sideways. The library agrees: its own mannequin with a stick through the fist
  holds `Sword_Idle`'s blade low and OUT TO THE SIDE, and the boxing guard stands it up over the shoulder.
  So the models keep the W19/W20 convention, and whether a weapon stands up at rest is the HOLD POSE's
  wrist, not the socket's.
- **Found:** `GroundJump` was 4.0 m high (fixed in W36). And `probe_auto_reload`'s bolt cadence
  (1.667 s vs 1.460) fails at HEAD too.

### W36 — A 1 m JUMP, A 2.5 s FUSE WITH A TRAJECTORY PREVIEW, NO COLLAR IN FIRST PERSON, AND WEAPONS STOOD UP (2026-09-18, user-asked)

- **Ground jump 4.0 m -> 1.0 m** (`GroundJump.tres` now overrides `jump_height = 1.0`, `apex_duration = 0.4`;
  the 4 m was `JumpState`'s default, never overridden). About two-thirds of this 1.49 m body; GTA's is
  ~1 m. `AirJump.tres` (2.5 m) is untouched. Measured rise 0.99 m.
- **The grenade burst in the air because its fuse was 1.0 s** (`FRG1Projectile.tscn` overriding the
  script's 3 s). At 12 m/s and 25 deg up from shoulder height it needs ~1.26 s to come down on flat
  ground ~14 m out. 2.5 s at first, then **3.0 s** with W37's longer throws (CS ~1.6 s, GTA/PUBG 3-5 s).
- **Trajectory preview** (`ThrowableItem`, `showTrajectory`): while the LOCAL player aims a throwable,
  its path is drawn as a translucent blue RIBBON (camera-facing, 4 cm and at least 0.6 cm per metre from
  the camera, so it keeps its on-screen thickness) ending in a filled 0.6 m disc where it goes off.
  Red-orange if the fuse runs out before it touches anything. Since W38 the preview is the grenade's own
  `GrenadeFlight` stepped ahead, bounces included. No message: it is a local drawing. Probe readouts
  `preview_end_now` / `preview_lands_now` / `preview_shown_now`.
- **The dark wedge at the bottom of the first-person view was the COLLAR**, part of the whole-body `armor`
  mesh, so hiding the head meshes never removed it. `blender/tools/split_fps_neck.py` moves the faces
  mostly driven by `neck_01`/`head` (511 faces) into `armor_neck` (same material, armature and weights),
  listed in `head_mesh_paths`. Hiding the whole torso (arms only) was not needed. Scaling `neck_01` to
  zero was rejected because the FPS camera mount hangs off that bone.
- **Weapons stand up in the hand.** The grip is the socket, derived from the hand (W35). Where the weapon
  POINTS at rest is the pose's wrist, so the fist's guard is used with only the right wrist turned
  (`fist_axis`). In first person the axe now stands in view at the bottom right, and so does the grenade.
- **Why the axe was invisible in first-person swings:** L4D/CS draw a separate VIEWMODEL, arms and weapon
  authored for the camera, with their own FOV. This game's first person is the real body with the head
  hidden (Arma/Tarkov style), so a whole-body swing leaves the view. Not built; the rest pose is now in view.
- The ledge climb was kept here, then removed in W39.

### W37 — THE GRENADE THROWS LIKE CS 1.6: HARDER AND HIGHER THE HIGHER YOU AIM (2026-09-18, user-asked)

The fixed throw (12 m/s at aim + 25 deg, ~14 m) became CS 1.6's `CHEGrenade::ThrowGrenade`, owned by
engine-free **`weapon.ThrowArc`** (`ThrowArcTest`, 5). The view pitch gets a 10 deg upward bias, compressed
above the horizon and stretched below it, and the speed is `(90 - biasedPitch) * 6` u/s capped at 750 u/s,
at 1 u = 2.54 cm. Level aim is a 10 deg lob at 15.2 m/s, and the 19.05 m/s cap is reached aiming ~30 deg up.
`ThrowableItem.throwVelocity` is the one place the real throw and the preview get it from. The old fixed
throw (`throwSpeed`, `arcAngleDeg`) and its `cs16Throw` switch were removed in W38. The host derives the same velocity from the aim MSG_LAUNCH already carries, so
there is no wire change (`run_net_launch_test.sh` 22/22). CS's "add the runner's velocity" is deliberately
left out, because a host's copy of a remote player does not carry that velocity exactly.
- Measured (`probe_w35_anims.gd`, view pitch 0 / 20 / 40): **12.6 / 26.7 / 32.5 m**, each within 0.15 m of
  its preview. The drag-free maximum is 38.4 m at 45 deg of elevation.
- The fuse went 2.5 -> **3.0 s**: at a 40 deg aim the flight is ~2.8 s and 2.5 s burst it in the air.
  A near-vertical lob still bursts, and the preview draws it red.
- (Its first bounce was a rigid-body `PhysicsMaterial`; W38 replaced it with CS's own bounce rule.)
- `VehicleProbeHelper.setViewPitch` lets a probe throw at a chosen angle.

### W38 — THE GRENADE FLIES THE PREVIEW'S PATH: CS 1.6's BOUNCE, NOT RIGID-BODY PHYSICS (2026-09-18, user-reported)

"The throw is sometimes in front of the arc, sometimes past it." Measured on DebugWorld
(`tools/godot/probe_grenade_world.gd`, 8 directions x 2 pitches): the FIRST impact was within 0.26 m of the
ring every time, but a rigid-body grenade (a 0.37 m box for a 112 mm grenade, bounce 0.45) then rolled
**3-6 m** past it. A tumbling rigid body cannot be predicted. CS never used rigid bodies for grenades.
- **`weapon.GrenadeFlight` is the ONE owner of how a grenade moves.** Each step: gravity, then a 6 cm sphere
  swept along the motion on the world layer (`castMotion`), and on contact the velocity is bounced by
  **`ThrowArc.bounce`**. That is CS 1.6's MOVETYPE_BOUNCE: overbounce 1.2 (restitution 0.2), a ground hit
  keeps 0.8 of the speed, and it rests below 20 u/s. It is engine-free, in `ThrowArcTest` (8).
- **The grenade is a KINEMATIC body** stepping that flight (`FRG1Projectile.launchVelocity` / `ignoreRid`
  replace the rigid velocity and the collision exception). The preview steps a copy of the same flight to
  the fuse or to rest, so the disc is the DETONATION point, bounces included. No drag anywhere (CS has none).
  Collider: a 6 cm sphere (the box was ~3x the grenade).
- **Removed:** `throwSpeed`, `arcAngleDeg`, `cs16Throw`, the ray-and-damping preview, the bounce
  `PhysicsMaterial` and CCD on the projectile.
- **Measured.** Flat stand: detonation **0.00 m** from the disc at view pitch 0 / 20 / 40 (15.2 / 34.1 /
  39.9 m with the roll). DebugWorld: **15 of 16 within 0.5 m (median 0.06 m)**, worst 2.06 m. The launch
  inputs agree to ~1e-7 m, so the worst case is chaos, not a mismatch: a long throw touching bumpy ground
  10-18 times can cross the rest threshold on a different bump. It is inherent in multiplayer too, because the
  host flies the real grenade from the float32 aim in MSG_LAUNCH. Gates: `probe_grenade_world.gd` (75%
  within 0.5 m and none past 6 m), `probe_w35_anims.gd`, `run_net_launch_test.sh` 22/22,
  `probe_explosive_damage.gd` PASS. `VehicleProbeHelper.setView(c, yaw, pitch)` aims a probe.

### W39 — THE LEDGE CLIMB IS REMOVED (2026-09-18, user decision)

For simpler movement and play, the CS model: walk, a free 0.35 m step (`stepHeight`), and a 1 m jump.
Removed: `MovementController.tryClimb`/`tickClimb`/`climbingNow` and their exports, the climb branch in
`Character`'s jump, `AnimationController.playClimb`, and the `Climb`/`ClimbScale`/`climb_up_1m` nodes in
both visuals scenes (the chain ends `output <- HitReact` again; `tools/patch_tree_w35.py` no longer adds them).
The `climb_up_1m` clip stays in the library, unwired. `probe_w35_anims.gd` 17/17. Its climb cases and
`--control` went with the feature.

### W40 — ONE ANIMATION LIBRARY, MANY BODIES: THE SKELETON CONTRACT (2026-09-20, PLAN.md 6.9)

`blender/SKELETON_CONTRACT.md` is the design record. **A clip is a fact about the SKELETON, not about a
body**, so there is ONE library in the game, every body plays it, and a new body ships with **no clips at
all**. That is GTA's model — one ped skeleton, shared clip dictionaries, extra dictionaries for a named
character — and the part that makes it work is that the shared thing is the RIG, not the proportions:
bodies here run 1.49 m to 1.91 m and share every clip.

- **What a body owes**: the 53 bone NAMES, the rest ORIENTATIONS within 1 deg, and facing −Y in Blender
  with the left arm at +X. What it does NOT owe: bone LENGTHS (that is the whole point of a second body),
  its non-contract bones (hair, skirt, spring chains — Shino keeps 158 bones, Fumiriya 117), or anything
  about its meshes and materials.
- **A POSITION KEY IS AN ABSOLUTE OFFSET IN METRES, and that is what stopped clips being portable.** Play a
  clip that pins `pelvis` at Godot-chan's 0.767 m on a 1.91 m body and its hips sit 0.37 m low for the whole
  clip — silent, and no name check can see it. Measured on the source export: of **8550** position tracks
  only **136** carry motion (`pelvis` 0.766 m, `Root` 0.643, both clavicles 0.0097); every other bone's
  deviates by at most **0.000036 m**, i.e. exporter noise, **270x** below the real motion.
  `tools/godot/build_character_anims.gd` drops the constant ones and rewrites each path from
  `Godot_Chan_Stealth/Skeleton3D:x` to **`Skeleton3D:x`**, so the library binds to whatever the
  `AnimationTree`'s `root_node` is. The tree carries the library itself (`libraries = {&"": ...}`) rather
  than pointing at an `AnimationPlayer` inside a body's `.glb`, and its filters are body-independent for the
  same reason. `Root`/`pelvis` still carry metres, so a taller body under-travels a roll in proportion to
  its legs: NOT corrected, because nothing reads root motion (`MovementController` moves the body), so it is
  a look and a per-body correction would be the per-body data this design exists to avoid.
- **A VRoid rig is CONFORMED, not retargeted.** A `.vrm` rests with every bone's rotation at **identity**
  (the VRM T-pose), and Blender's stock importer preserves that — so against Godot-chan's Blender-style rig
  the same clip is two different poses. Retargeting would mean a derived copy of all 171 clips per body,
  re-run on every clip edit. Conforming is FREE: a Blender bone deforms by `pose · rest⁻¹`, which at rest is
  the identity **whatever the rest orientation is**, so re-orienting a bone in edit mode moves no vertex of
  the mesh — it only changes what a pose rotation means, which is the thing that has to agree.
  `blender/tools/import_vrm_body.py` does exactly three things: **turns the body round** (measured, one 180
  deg about Z — VRoid faces +Y with left at −X, we face −Y with left at +X, NOT a mirror), **renames** the 54
  humanoid bones from the file's OWN `VRM.humanoid.humanBones` map (not by matching `J_Bip_*` strings), and
  **re-orients** each contract bone's rest to the reference's, keeping the VRoid head position. After the
  turn the limb directions already agreed to a few degrees (both rigs are T-posed), so what the re-orient
  supplies is the ROLL — biggest change 251.7 deg, on a thumb.
  `blender/tools/dump_skeleton_rest.py` writes the target to `assets/characters/skeleton_rest.json`, derived
  from the rig rather than typed into a script.
- **Two traps, both measured.** A VRoid file ALREADY HAS a bone called `Root`, so a branch written as
  "create it if missing" never ran and the imported root's own frame survived 120 deg out on every body (and
  a newly created EditBone is zero-length, which has no direction for `matrix` to preserve — that was the
  second half of the same bug). And **the head bone is `head_2`**: the reference `.glb` carries a MESH node
  called `head` beside the bone, so Godot's importer renamed the BONE, and the library's tracks, the tree's
  filters, `Physical Bone head_2` and the Java bone-multiplier table all say `head_2`. A new body has no
  such collision and would import as `head`, resolving to nothing and simply never animating.
- **A BOSS GETS A SECOND LIBRARY BESIDE THE SHARED ONE**, never a private copy of the walk cycle:
  `libraries = {&"": <shared>, &"boss_a": <boss_a_anims.res>}`, played as `boss_a/<clip>`. Additive, so the
  boss still walks, aims, reloads and dies on the shared clips. None ships yet.
- **Retired**: `merged_animation_f.{blend,glb,tscn}` + its textures and `CharacterVisuals_GodotChanF.tscn` —
  a byte-identical placeholder whose animation data hashed the same as the base body's (171 clips duplicated
  for nothing). `probe_character_variant.gd` went with it, superseded by `probe_body_contract.gd`.
- **Gates.** `tools/godot/probe_shared_anims.gd` 2/2 — every clip poses every bone within **0.000001 m /
  0.056 deg** of the body `.glb`'s own player (that last is float32 key noise on a fingertip four bones down
  the chain); `--control` shifts one bone's rest by 5 cm, less than Shino's arm differs from Godot-chan's,
  and the constant position tracks override it, failing by exactly **0.050 m**.
  `tools/godot/probe_body_contract.gd -- --body=res://assets/characters/<body>/<body>.glb` **3/3 on both
  bodies** — every contract bone present, rest orientations within **0.04 deg**, and all 171 shared clips
  posing the body within **0.06 deg** of the reference while bone POSITIONS differ by up to 0.37 m, which is
  the split the contract is drawn around; `--control` injects 20 deg into one rest and fails 2.
  Unchanged by the whole change: AimDebugAuto 40/40, `check_character_anim` PASS, `probe_weapon_fit` /
  `_holster` / `_sockets` / `_archetypes` / `probe_melee` / `probe_support_hand_ik` PASS, World.tscn 0 errors.
- **Not done, and it is the per-BODY half**: `CharacterVisuals_Shino.tscn` / `_Fumiriya.tscn` + `MeshConfig`,
  then every number in `CHARACTER_BASE_STUDY.md` section 5 re-measured on each body (the FPS and cockpit
  eyes, the six weapon sockets, the stock anchors, the holster slings, the stance capsules, the ragdoll bone
  shapes) — those are facts about a BODY and do not come free. Godot-chan stays until then: it is the clip
  source, the rest reference and the control.

### W41 — A BODY'S OWN NUMBERS ARE MEASURED, AND ITS SCENE IS GENERATED (2026-09-20, PLAN.md 6.9)

W40 made the RIG shared. Everything else a character needs is a fact about THAT BODY and does not come
free: where the eye is, where a grip sits in the fist, where a stock meets the shoulder, how a rifle hangs
on the back, how wide it is for a stance capsule, how thick each limb is for its hitbox. Godot-chan's were
measured and hand-tuned across the whole W series. A second body must not inherit them and must not have
them guessed, so there are two tools and one file between them:

```
tools/godot/measure_body.gd        --body=<b> [--check]  ->  assets/characters/<b>/<b>.body.json
tools/godot/build_character_visuals.gd --body=<b> [--check] -> character/CharacterVisuals_<Body>.tscn
```

`CharacterVisuals_Shino.tscn` and `_Fumiriya.tscn` are generated; **the reference's scene is not.** It owns
the AnimationTree the generator copies, and it is the control every rule below is read against.

- **The reference reproduces itself, which is what says a rule is a rule.** Run the deriver on Godot-chan
  and it lands on the numbers the shipped scene was hand-tuned to: the six weapon sockets **exactly**, the
  stock anchor **exactly**, `body_radius` **0.350** and the crouch capsule **0.35 / 0.94** exactly, upright
  1.508 against an authored 1.5, the back's skin surface **0.128 m** against the 0.13 the W28 solver
  recorded, and its two solved back slings within **1.2 cm** of the authored ones.
- **What is DERIVED and what is TRANSFERRED is a deliberate split.** A rule the body answers is derived:
  the crown and the eye (the EYE surfaces' centroid), the back's surface, the shoulder pocket, the stance
  capsules, every hitbox radius. A number that is an ARTIST's choice with no rule behind it — which way a
  pistol sits in a fist — is not invented: it is transferred through a frame built from the body's OWN
  bones (wrist -> knuckle line, index knuckle -> pinky knuckle, normalised by the hand's own length), so
  the reference reproduces itself exactly and another body gets the same grip in its own hand. **The hand
  is not proportional to the body**, which is why it carries its own scale: Godot-chan's is 0.083 m on a
  1.49 m body and Fumiriya's 0.072 m on a 1.91 m one.
- **THE ARMATURE'S FRAME IS NOT THE GAME'S, and getting it backwards is silent.** `merged_animation.tscn`
  turns the armature 180 deg about Y, so `get_bone_global_rest` hands back a frame whose **+Z is the FACE**
  while every rule in this codebase is written in MeshRoot's, where forward is -Z. Measured on the
  reference: the backpack sits at bone z -0.22..-0.10, the eyes at +0.05..+0.07, the toe in front of the
  ankle at +0.08. Read the wrong way the back sling is solved onto the CHEST and the shoulder pocket lands
  behind the shoulder — both happened here, and both survive every sanity check because the numbers stay
  plausible. The generator states the same turn on the body it instances.
- **The shoulder pocket has ONE owner and it is the GATE.** `probe_weapon_fit.gd` already re-derived it
  every run and failed on 2 cm of drift; two implementations of one rule disagreed by 3.5 cm on one body,
  so `--emit-pocket=<file>` makes the probe write what it measures and the deriver reads it. The deriver's
  own reading is the bootstrap that lets a body's scene be built at all (within 2 cm on two of three
  bodies, 4.9 cm on the third). A new body is therefore measure -> build -> probe `--emit-pocket` ->
  measure -> build.
- **A hitbox's radius comes from the SKIN, not from the bone's length.** The editor's "create physical
  skeleton" sizes a capsule at `0.1 x bone length`, which is where Godot-chan's **0.9 cm** hands come from
  — and a capsule that small is exactly what Jolt's ray test steps over at range (see "A long ray steps
  over a small, far hitbox"). Measured off each body's own skin: hand **0.009 -> 0.027 m**, forearm 0.035,
  thigh 0.080, pelvis 0.137, head 0.090. Unhittable past 38 m becomes unhittable past 112 m. The LAYOUT
  still follows the editor's rule, so the joints behave as they always have.
- **A stance capsule is not the body's bounding radius.** One radius serves every capsule stance and is a
  fact about the body: taking the widest thing in `crouch_idle` instead gives a **1.17 m** wide collider,
  because a crouch leans the torso half a metre off the body's own axis. Every shooter walks a crouched
  character on the cylinder it stands on and lets the knees clip.

**Measured on the two VRoid bodies** (`probe_character_visuals.gd`, the new gate, **10/10 each**;
`--control` undoes the armature turn and fails exactly the 2 facing checks). `probe_weapon_fit.gd` PASSes
on Fumiriya and on the reference; `probe_weapon_holster.gd` PASSes on Fumiriya and on the reference.
Unchanged by all of it: AimDebugAuto 40/40, `probe_shared_anims` 2/2, `probe_body_contract` 3/3 on each
body, `probe_weapon_sockets` / `_archetypes` / `_world_body` / `probe_melee` / `probe_support_hand_ik` /
`probe_self_hit` / `probe_recoil_kick` / `probe_switch_spin` / `probe_crawl_balance` PASS,
`check_character_anim` PASS, World.tscn 0 errors, `./gradlew test` green.

**Three things the gates now say about the REFERENCE, and each is true.** Its first-person mount is
**8.2 cm BEHIND** the head bone — at the back of the skull, not at the eye (the generated bodies put it on
their measured eye, 7.0 and 8.5 cm in front); its hands are 0.9 cm across; and both are consequences of
hand-authoring that predate the rules. `probe_character_visuals.gd` reports 8/10 on it for exactly those
two, which is the argument for retiring it rather than a defect to fix in it.

**Three open items, measured rather than papered over:**
- **A taller body crouches less deep, because a position key is metres.** The shared library expresses a
  crouch and a crawl as `Root`'s own drop, and W40's known wart has a consequence: measured, Fumiriya's
  feet leave the ground by **5.8 cm** in `crouch_idle` and his head sits **28 cm** higher than proportional
  in `crawl_idle`. Scaling the drop by leg length was tried on paper and is wrong — the leg ROTATIONS fold
  a longer leg further by themselves, so the correction Shino needs is ~1.0x and Fumiriya's ~1.2x, not
  their 1.22 and 1.48 hip ratios. The real answer is foot grounding (an IK pass that puts the soles on the
  floor), which is its own feature and which Godot-chan does not need. The stance capsules are derived from
  the pose the body is ACTUALLY in, so they are right either way.
- **The support hand's reach is set by SHOULDER WIDTH as much as by arm length, and the lever is the
  WEAPON's `SupportPoint`.** Shino missed ASR1's and SHG1's by 7.8 and 8.6 cm where Godot-chan reaches
  both. Decomposed: her stock seats 9.8 cm in front of her shoulder against Godot-chan's 6.9 (+2.9 cm, a
  deeper chest), and her shoulders are 0.218 m wide against 0.2955 (+3.9 cm, so her left hand starts
  further from a gun held on the right). Together 6.8 cm, which is the whole miss.
  **Pulling the firing arm back in the CLIP does not move the gun** — for a stocked weapon
  `StockMountIKModifier` puts the butt on the shoulder anchor and the weapon's whole position follows from
  that anchor, its own geometry and the aim, so the clip's right arm is overridden (it is still the lever
  for a pistol, and for the non-combat hold where the mount stands down). What DOES move is the support
  point, and it is free because a shorter hold helps every body: measured, moving **ASR1's `SupportPoint`
  6 cm back** (z -0.285 -> -0.225, W24's own rule applied to a shorter arm) takes Godot-chan 0.014 ->
  **0.000**, Shino 0.078 -> **0.021** and Fumiriya 0.019 -> **0.000**. Applied.
  **SHG1 is not, and it is a look decision.** The same 6 cm (-0.29 -> -0.23) takes Shino to 0.030 and the
  other two to 0.000 — but its marker is already the PUMP's rear edge (W24), so 6 cm back puts the support
  hand behind the pump on the receiver, which is not a hold a shotgun has. The alternatives are an
  authored hold pose for her (W25's `adopt`) or a shorter shotgun.
- **A long weapon on a short neck.** Shino's axe slung on her back comes **0.093 m** from `head_2` against
  the holster gate's 0.10 m limit — a 7 mm miss on one weapon in one slot, with the poke check still clean.

**Four traps this cost, all of them silent:**
- **`Skeleton3D.get_bone_global_pose()` returns the REST pose in a headless `--script` run** and
  `force_update_all_bone_transforms()` does not clear it. Measured: with `crawl_idle` applied, the local
  poses put the head at 0.322 m while that call still answered 1.357. Walk the parent chain from
  `get_bone_pose()` instead. It reads as "this body measures the same in every stance", which is how it was
  found.
- **`ap.play(clip)` then `ap.seek(0.0, true, true)` applies NOTHING** — it seeks to where the player
  already is — and leaves the rest pose standing. `advance()` is what applies a pose.
- **A `PackedVector3Array` read out of a Dictionary is a COPY**, so `out[b].append(v)` appends to it and
  throws it away. Every hitbox came out with zero samples and its radius on the floor. Use `Array`, which
  is a reference. (The same shape as godot-jvm's mutating `Transform3D.times`.)
- **`PackedScene.pack()` needs BOTH `instantiate(GEN_EDIT_STATE_INSTANCE)` and `set_editable_instance`**,
  and each is silent the other way: without the edit state the saved scene carries the whole body (measured,
  **2.0 MB** of ArrayMesh against 70 KB), and without the editable flag the nodes added inside the instance
  are not stored at all. `ResourceSaver.save` also picks its format from the EXTENSION and writes nothing
  for an unknown one.

**The pose a skin reading is taken in is part of the reading.** The shoulder is read in the weapon HOLD,
which the tree assembles from two clips — legs and spine from the locomotion idle, clavicles/arms/hands
from the hold clip through `WeaponBlend`'s filter — so the deriver assembles the same pose rather than
playing the hold clip whole. Everything else is read standing. Reading the shoulder in the idle instead
puts the anchor 2.6 cm from where the probe then finds it.

**AUTHORING a shared clip needs every body in front of you, and that is a VIEW, not a copy**
(2026-09-20). One library means the 171 clips live in Godot-chan's `.blend` and no other body has
any, so a pose is authored while looking at the body it suits LEAST — 1.49 m, the biggest head and
the longest hands, serving 1.65 m and 1.91 m. `blender/tools/build_animation_review.py` writes
`assets/characters/animation_review.blend`: every body library-LINKED from its own file and then
`override_hierarchy_create`d, the actions library-LINKED from `merged_animation.blend` and therefore
**read-only there**. That is the design — a clip has ONE owner, Blender cannot merge two edits of one
action, so it must not be possible to make two. **Judge there, edit in `merged_animation.blend`,
`File > External Data > Reload`.** Judged on SHINO, at the origin (user's call): her reach is the
shortest of the three and not because of her arm — her shoulders are 0.218 m against the reference's
0.296, which is what puts an off hand furthest from a weapon held on the right, and W41's own ASR1
measurement is the evidence (7.8 cm on Shino, 0.000 on the two wider bodies).
**The trap it exists to make visible is the one that makes a body look like it "has no animation":
since Blender 4.4 an action is SLOTTED** — its channels belong to a slot naming the ID it was
authored on (`OBGodot_Chan_Stealth`), and assigning that action to any other rig leaves `action_slot`
None with **no error and no warning**, so the rig stands in its rest pose while the timeline runs.
Binding `action_slot = action.slots[0]` is what plays one clip on every body. (A LINKED object cannot
be given `animation_data` at all, which is why the override is needed; building local objects around
the linked mesh DATA fails differently — vertex groups live on the OBJECT, so the meshes arrive
unweighted and the armature moves nothing.) Measured once bound, `upright_walk_forward`'s same
rotation keys travel **0.53 m on Shino, 0.47 m on Godot-chan and 0.65 m on Fumiriya** — one clip,
longer legs, longer stride. `blender/SKELETON_CONTRACT.md` §9 is the record.

### W42 — POSING IS IK NOW, AND THE CONTROL LAYER IS ADDED RATHER THAN GENERATED (2026-09-20, user-asked)

Authoring a pose meant turning four bones by hand. `blender/tools/add_control_rig.py` adds hand and
foot IK to a body's `.blend`: 9 `CTRL_` bones, an IK constraint on `lowerarm_l/r` and `calf_l/r`, a
hideable `CTRL` bone collection, widgets, and an `IK CONTROLS` text block holding the workflow and
both snap helpers. Applied to all three bodies. `blender/SKELETON_CONTRACT.md` §10 is the record.

**A ONE-SHOT, the `import_melee_pack.py` pattern** (user's ask: a long-term maintenance answer, not
legacy code). It runs when a body needs the layer, the result lives in the `.blend`, and **nothing
depends on it running again** — no gate, no build step, no export path. A tool every export depends
on is how a repo grows legacy. The clips are already covered by `probe_shared_anims` /
`probe_body_contract` / `check_character_anim`, so it needs no gate of its own, and the workflow doc
and snap helpers live INSIDE the `.blend` so they do not depend on the script surviving.

**Rigify / Auto-Rig Pro / Rigodotify were TESTED, not waved away.** Rigodotify (felesmachina, itch.io;
MIT in its LICENSE, GPL-3.0-or-later in its manifest) is a real fit on the axis people reach for it:
its skeleton is **51 of our 53 bones by exact name**, and its convert keeps the whole Rigify control
rig (220 widgets, IK on `MCH-*_ik.L/R`) while renaming the DEF bones to ours and driving them by
`COPY_ROTATION`. What kills it is the **rest**: a generated rig brings its own rolls, and measured
against ours the roll differs by a median of **24.4°** — only 6 of 52 bones within 1°, 10 past 45°
(`ball_l/r` **175°**, `clavicle_l/r` **87.8°**). Rest orientations are half the W40 contract and both
VRoid bodies were CONFORMED to them, so a generated rest would re-mean all 171 clips, force a
re-conform of every body and move every bone-frame constant. It also needs the GUI (its converter
drives the Drivers *editor* and dies headless on `bpy.context.area`). **Licence was NOT the reason** —
GPL does not claim a tool's output, the add-on source never enters the repo, and a CREDITS line would
cover the generated data; that point was raised and correctly withdrawn.

**Interop needs no new rig, and that is the measurement that settles it.** A retargeter reads the
DEFORM skeleton's bone names, and ours already ARE the UE-mannequin convention Rigodotify targets.
The two exceptions are RECORDED rather than renamed: `Root` (standard `root`) and `head_2` (standard
`Head`, ours only because the reference `.glb` carries a *mesh* called `head` so Godot's importer
renamed the bone — W40). Renaming is 75 hits across 26 files plus a library re-bake, and a retargeter
needs a mapping table anyway, so two rows at the seam is the cheap fix.

**Four rules, each a measured defect first:**
- **The IK influence is 0, and that is the whole safety argument.** A constraint at full influence
  OVERRIDES the chain's rotation channels, so leaving it on would silently replace the arms of all
  171 shared clips. The script asserts the rig is unmoved and refuses to save otherwise — measured
  **0.000000 m over 477 samples**.
- **GRAB before posing.** An ungrabbed control sits where it was left and raising influence drags the
  limb to it — **0.83 m** on an arm from rest. `GRAB` puts both handles where the clip already has
  them, disturbing **0.0007–0.0019 m** across three different poses.
- **The pole angle is POSE-DEPENDENT.** One stored value cannot preserve every pose: an angle solved
  on a crouch moved an aim pose's forearm **0.231 m**. `GRAB` places the pole in the limb's current
  bend plane and re-solves it (~80 evaluations), which is also why the script's initial solve is only
  a convenience — a body with no clips at all (a fresh `.vrm`) legitimately gets none.
- **`export_def_bones = True` is now required.** `use_deform = False` does **not** keep a control bone
  out of a glTF export — measured, it arrives as a 54th joint with its own track, breaking the
  53-bone contract silently. With the flag on: 53 joints, no `CTRL_` node, no `CTRL_` track, 171
  clips, IK still baked. Not bit-identical (up to **0.065°** against the 0.056° of float32 key noise
  `probe_shared_anims` tolerates), so the shipped `.glb` was deliberately NOT re-baked on the flip.

**`BAKE` is the preferred half of the workflow**: it writes the IK result into the FK bones
(**0.000000 m**) and drops influence to 0, so an action keys only the 53 contract bones exactly as
today and `animation_review.blend`, every other body and the shared library are untouched. Keying the
controls instead also works — the export samples the evaluated pose — but then every body needs the
layer. **Re-importing a `.vrm` overwrites the `.blend` and takes the control layer with it**: re-run
the script, which is idempotent.

### W43 — A CLAVICLE POSITION KEY LIFTED EVERY VROID BODY'S SHOULDER 9-13 cm (2026-09-20, user-reported)

User, on a visual review: "the shoulder is held up, worse on Fumiriya, worst on Shino, and the gun is
held up, and the skeleton turns in an ugly way." All of it was right, and it was one defect.

**`upright_aim_rifle` carried POSITION tracks on the two CLAVICLES**, at the reference's absolute
offset `y = 0.2132`. A position key is an absolute offset in metres (W40), so on another body it
overrides that body's own clavicle rest:

| body | own `clavicle_r` rest y | forced to | shoulder girdle lifted |
|---|---:|---:|---:|
| Godot-chan | 0.2134 | 0.2132 | **0.000 m** |
| Fumiriya | 0.1208 | 0.2132 | **+0.092 m** |
| Shino | 0.0868 | 0.2132 | **+0.126 m** |

Measured lifts matched the arithmetic to the millimetre (0.0924 / 0.1261). The reference's clavicle
sits 21 cm above `spine_03` and Shino's 8.7 cm, so the same key is invisible on one body and a
violent shrug on the other — which is why it survived: **every gate was green.**
`probe_shared_anims` compares the library against the REFERENCE's own `.glb`, where the key is
0.0002 m from rest, and `probe_body_contract` checks rest ORIENTATIONS, not positions.

**Two causes, and the user named both.** The proportions differ enormously; and the pose was authored
BY EYE WITH NO IK (W25 adopted it from a hand-placed ASR1), so the artist got the shoulder where they
wanted by **translating** the clavicle instead of rotating it. A rotation is portable; a translation
is not. The `.blend` has IK now (W42), so the next pose need not be made that way.

**The fix is a RULE, not an epsilon: `build_character_anims.TRANSLATING_BONES = ["Root", "pelvis"]`.**
Only those two may carry a position track; every other bone's position is a fact about the BODY.
The old test kept any track deviating more than `POS_EPS` (1e-3) from the reference's rest, and the
clavicles wobble **0.0097 m** with breathing, so they cleared it — **1 cm of authored motion bought
at 13 cm of error, and no epsilon can separate those, because the VALUE is wrong rather than the
movement.** 8208 tracks are now dropped by rule; the build reports the most authored motion given up
(0.009742 m, `clavicle_r`) so the cost is visible rather than silent. Its own noise-floor test counts
only ELIGIBLE bones now, or it fails on a rule it is not testing.

**Measured after**, and this is the shape a portable clip should have — the same pose on every body,
scaled by each body's own proportions:

| body | clavicle lift | upperarm_r lift | as %% of its own clavicle |
|---|---:|---:|---:|
| Godot-chan | 0.000 (unchanged) | +0.016 (unchanged) | 12.6%% |
| Shino | 0.126 -> **0.000** | 0.138 -> **0.012** | 13.6%% |
| Fumiriya | 0.092 -> **0.000** | 0.109 -> **0.017** | 13.5%% |

**It is free on the reference**: `probe_shared_anims` still 2/2 at 0.000001 m, AimDebugAuto 40/40,
`probe_body_contract` 3/3 on both VRoid bodies, `probe_weapon_fit` PASS on Godot-chan and Fumiriya.

**What it EXPOSED, which is the honest part.** Shino's SHG1 went 0.086 -> **0.105 m** and SNR1 newly
fails at **0.065 m** — the bogus shrug had been lifting her girdle toward the gun and masking a real
reach deficit. The two failures are the two LONGEST weapons: SHG1's `SupportPoint` is 0.29 m ahead of
the grip and SNR1's 0.24, against ASR1's 0.225 and SMG1's 0.194. That is PLAN.md 6.12's case, and the
user's framing of it is the right one: **a pump shotgun is not a rifle** — its support grip is far
forward of the trigger, so it wants its OWN hold authored around that distance rather than the rifle
hold overridden.

### W44 — THE SUPPORT HAND REACHES ON EVERY BODY: A PROTRACTING SHOULDER, +8 deg OF BLADE, 7 mm OF MARKER (2026-09-20)

After W43 removed the bogus shrug, Shino failed three weapons on reach — ASR1 0.040 (against a 0.050
tolerance), SNR1 0.065, SHG1 0.105 — because reach is set by SHOULDER WIDTH, not arm length: hers is
0.2174 m against the other two bodies' 0.2955, and her shoulder pocket sits 0.098 m forward of her
joint against the reference's 0.069. **All three now PASS on all three bodies**, from three changes
that each fix a different half of the problem and none of which is a per-body number.

- **`SupportHandIKModifier` protracts the support shoulder** (`shoulderBone`, `maxClavicleDeg` 40,
  **0 is the exact control**). Two-bone IK solved from a RIGID clavicle, but protraction is how a
  human extends reach. It is FREE here because **the weapon hangs off `clavicle_r`** — swinging
  `clavicle_l` moves the support shoulder toward a gun that does not move, so there is no re-aim and
  no loop with `ShoulderAimModifier` or `StockMountIKModifier`. It engages only past the arm's own
  reach and the angle is solved to close exactly the deficit, so a body that already fits gets 0 and
  is bit-identical. Worth **0.026 m** on Shino; 0 on the other two.
- **+8 deg of blade in the shared aim clip** (`blender/tools/blade_delta.py`, a DELTA not a re-solve —
  `pose_weapon_hold.py solve-aim` would discard W25's adopted pose). Measured **3.5 mm of reach per
  degree**, matching the geometric 3.6. **The counter-rotation must be BELOW the shoulder.** Restoring
  the CLAVICLES' world orientation cancels the whole effect — a clavicle origin sits ~2 cm off the
  spine axis, so rotating the chest barely moves it, and the shoulder's position comes from the
  clavicle's own direction; measured, a +15 deg chest delta then moved reach only **9 mm**. Restoring
  the HANDS' orientation instead leaves the arm to absorb the twist, keeps the bore on the forward
  line (W23's condition for an authored blade to survive) and yields the full 3.5 mm/deg.
- **SHG1's `SupportPoint` back 7 mm** (z -0.290 -> -0.283). The pump is the uniform run from bore
  z -0.42 to -0.27 (measured off the mesh), so 7 mm keeps the hand ON it; the -0.25 an earlier
  single-lever fix would have needed is 2 cm behind it, on the receiver.

**Why a blade and not more of either single lever**, which is the user's constraint and the reason the
answer is three small changes: blade costs CHEEK WELD (the right eye drifts 0.9 cm further off the
bore at +8 deg, 1.6 cm at +15) and past +8 it costs POKE (SHG1 goes 24 -> 60 skin samples inside the
body). Protraction past ~40 deg reads as a shrug rather than a reach. So each lever is taken to where
its own cost starts and no further — and +15 deg of blade, which a single-lever fix would have needed,
is measurably worse on both counts.

**The shotgun archetype (PLAN.md 6.12) was NOT needed and is not built.** It remains right for the
LOOK of a pump hold, but it is no longer load-bearing for reach — which is the healthier split, since
a clip should not encode "Shino's arms".

**A WALK-TEST FOUND WHAT THE GATES DID NOT, and the blade is the cause (PLAN.md 6.14).** In CRAWL the
weapon yaws RIGHT by about the blade angle. The counter-rotation lives on `hand_r`/`hand_l`, which
`WeaponBlend`'s filter carries in EVERY stance, while the spine blade arrives through
`WeaponTorsoBlend`, gated on `Stance.weaponTorsoLayer` — **true on Upright and Crouch only**. So in
crawl the hands get the compensation and the spine never gets the thing it compensates for. **The
verification gap that let it ship: `probe_weapon_fit` takes `--stance=crouch|crawl|swim` and only the
default upright was run.** Run all four stances x three bodies before touching the shared aim clip.

Measured after, all three bodies (UPRIGHT only — see above): `probe_weapon_fit` **PASS** (Shino's worst is SHG1 at 0.046),
AimDebugAuto **40/40**, `probe_shared_anims` 2/2, `probe_support_hand_ik` PASS, `probe_self_hit` PASS
(worst 12.5 deg, 1 frame), `check_character_anim` PASS.

**Open, and found on the way: the cheek weld is poor on the VRoid bodies.** In combat the head sits
+0.096 m (Shino) and +0.157 m (Fumiriya) above the stock, against the reference's +0.058. The suspect
is `NeckFront` — a `Blend2` filtered to `head_2` and `neck_01` that replaces them **100% with the
TPOSE** whenever combat is on (`AnimationController:366`). It exists so a walk cycle's head bob does
not shake the neck-mounted FPS camera — but W5 already filters that at the camera (14.7x less jerk)
and W30 scales it to zero while scoped, and `NeckFront` runs ONLY in combat, so the filter is
evidently sufficient by itself out of combat. One fact, two owners. Removing it is its own measured
change: it alters the third-person head in combat on every body.
**And it is COUPLED to the blade, so the order is fixed:** the T-pose is currently MASKING W44's
-8 deg of `spine_03` blade at the head. Remove it while the blade is still carried as a clip rotation
and the head inherits the bladed torso — user-reported, the head/eye stops facing the target and
slides RIGHT by about the blade angle. Fix the blade's stance leakage (PLAN.md 6.14a) BEFORE touching
`NeckFront`. It also cannot be judged in the `.blend`: the preview does not run `ShoulderAimModifier`,
which is what drives `neck_01` toward the aim in game.

### W45 — THE HEAD LOOKS AT THE TARGET, THE SHOULDER IS IN THE AUTHORING CHAIN, AND THE BLADE IS THE ARTIST'S (2026-09-20, user-asked)

The ask was to "fix/simplify the entire aim" and to build a control IK in the central animation so
the hand's grip pushes the adjustment up into the shoulder, with the artist owning the blade. Four
changes, each measured, and the first is the one that was doing the damage.

**1. THE BORE IS AIMED BY THE SHOULDERS; THE HEAD LOOKS AT THE TARGET.** One delta was solved — from
the held weapon's bore (W23), else the chest — and applied to `clavicle_l`, `clavicle_r` AND
`neck_01` alike, so the head inherited whatever correction the ARMS happened to need. That is wrong
in KIND, and the authored pose is why: a shouldered rifle is held BLADED (the shipped clips turn the
chest 42–57 deg off the line while the bore stays on it) and `neck_01` is a CHILD of `spine_03`, so
the head rode the blade. Measured across **three bodies x four stances, the head sat 28–34 deg off
the aim while the gun was on it to 0.0** — upright included, not just crawl.
`ShoulderAimModifier.headBone` / `headForwardBone` now solve the NECK's own delta, from the HEAD's
own forward onto the target, clamped by the same stance limits and applied AFTER the shoulders (the
neck is a child of the reference bone in the chest-aim case). Measured after: **0.0 deg in every one
of the twelve cases**, and the head is on the body centre line (0.000–0.016 m, against +0.076 m in
crawl). `headBone = ""` is the control. The head's forward AXIS is derived from the rest pose
against `referenceBone` rather than assumed — W1 records what assuming an axis on this rig costs.
- This is 6.14(a) ("the whole upper body / weapon yaws RIGHT in FPS, in crawl") and 6.14(d) ("the
  head/eye stops facing the target and slides right"): **they were one defect**, and neither was
  really about the stance or about `NeckFront`.
- **`NeckFront` STAYS** (user decision, 2026-09-20): the T-pose secures the neck and the aim IK
  turns the face onto the target from there. Measured with it off, the head still lands on the aim
  (0.0 deg) but keeps the clip's own ROLL — 10.6 deg on the new rifle pose, and 34.1 deg on the
  sniper placeholder before it was refreshed — because a look-at fixes a direction and says nothing
  about the twist about it. `probe_weapon_fit --neck-front=off` is that measurement, kept.

**2. THE BLADE IS OUT OF THE CLIP, so the artist owns it.** W44's +8 deg carried a −8 deg
counter-rotation on `hand_r`/`hand_l`, and the two halves reach the pose by DIFFERENT paths: the
spine arrives through `WeaponTorsoBlend`, gated on `Stance.weaponTorsoLayer` (true on Upright and
Crouch only), while `WeaponBlend` carries the hands in EVERY stance. Reverted by copying HEAD's own
action back (`pose_weapon_hold.py copy-from`) rather than `git checkout`, so W42's control rig
survived — and a channel-by-channel diff of every action against HEAD confirmed
`upright_aim_rifle-loop` was the ONLY clip that differed, which is also how the sniper placeholder
was found to have silently diverged. `blade_delta.py` is deleted.

**3. THE CONTROL RIG'S ARM CHAIN REACHES THE CLAVICLE** (`add_control_rig.py`, chain 2 -> **3**).
A support hand that cannot reach its grip is short because of the SHOULDER, not the arm — Shino's
shoulders are 0.2174 m against the other two bodies' 0.2955, and it is that 7.8 cm that misses — so
the gesture the artist wants is "move the hand and let the shoulder follow". Two rules make it safe:
- **It goes up only as far as it must.** `ik_stiffness` 0.9 on the collarbone, so the solver spends
  the elbow and the shoulder joint first. That is the same rule the runtime `SupportHandIKModifier`
  already follows (it protracts ONLY past the arm's own reach), so authoring and runtime now agree.
- **It cannot over-rotate.** A symmetric 60 deg envelope on all three axes — measured against the
  library, where every aim, hold, idle, locomotion and reload pose turns a clavicle at most 35 deg
  on its own channel. Symmetric and per-axis-identical on purpose: which local axis is protraction
  is a fact about bone ROLL, and an envelope written per axis would be a second place that fact
  lives.
- Measured by the tool itself, every run: the hand pulled 4 cm past the arm's own reach recruits
  **23.1 deg** of collarbone and ARRIVES (0.002 m); pulled 60 cm past, the collarbone stops at
  **60.1 deg** and the hand is honestly 0.53 m short instead of dislocating. Influence stays 0 and
  the pose is unchanged at **0.000000 m over 477 samples**.
- Two traps it cost: **an IK constraint's result never reaches `matrix_basis`** (a shoulder the
  solver had swung 0.12 m read 0.9 deg, and the check passed a limit it was not testing — read the
  EVALUATED pose), and **the reach is the two JOINT-TO-JOINT distances, not the two bone lengths**
  (a bone's tail need not sit on its child's head; taking the lengths under-measured this arm by
  4 cm, enough that the "past its reach" case was still reachable and tested nothing).

**4. FIVE CLIPS TURNED A COLLARBONE 73–171 deg, AND IT SHIPPED.** `blender/tools/fix_shoulder_overbend.py`
(a one-shot, the `add_control_rig.py` contract). It is one defect six times: W34 retargeted the melee
and throw attacks ARMS-ONLY — every bone below the clavicles holds `upright_idle`'s first frame while
the arms keep the source's WORLD directions — which leaves the COLLARBONE to absorb the whole
difference between the source's torso and our held one.

| clip | clavicle_l | clavicle_r | after |
|---|---:|---:|---|
| `attack_slash_mw1`, `attack_swing_mw2` | 159.1 | 170.6 | 60.0 |
| `attack_chop_mw2` | 128.1 | 124.8 | 60.0 |
| `attack_throw` | 110.5 | 110.3 | 60.0 |
| `attack_jab_fist` | 73.8 | 63.4 | 60.0 |
| `attack_cross_fist`, `attack_stab_mw1` | 43.5 | 51.9 | (under the limit, untouched) |

**It is not a preview problem:** both clavicles are in the `Attack` one-shot's filter, so every melee
swing in the game played it. **Measure the CHANNEL, not the bone's world direction** — a clip that
rolls or dashes turns every bone in the body, and by direction an ordinary sword clip reads 160 deg
at the collarbone while its own channel moves 10. The fix keeps the hand and moves only the shoulder:
the channel is scaled back along its own axis to the limit (a continuous function of the input, so
the clip does not step where the fix starts, and frames already inside are not touched at all) and
the arm is re-solved with two-bone IK to put the WRIST back, with the hand's own world orientation
restored on top. Measured: **the wrist stayed within 0.012 m (jab), 0.058 m (throw) and 0.115–0.120 m
(slash/swing/chop)** of where the swing had it — the worst case being where a 60 deg shoulder simply
cannot reach the original point and the arm straightens instead.
- **`check_character_anim.py`'s `shoulder_overbend` reports it**, reading the .glb so it also sees a
  hand edit. It is a **WARN, and the number is DESCRIPTIVE** (user, 2026-09-20): 60 deg is what the
  AIM AND HOLD poses measure, i.e. a description of how those are built, not a budget every clip
  owes — an attack, a throw or a prone reach legitimately swings a collarbone further. It says when
  a clip has gone somewhere unusual; it does not decide what a pose may be.
- **The limit has ONE owner**, `character_anim_naming.json` `limits.shoulder_channel_deg` (60), read
  by the control rig, the reset and the report. The one place it is a HARD limit is the control
  rig's IK solve, where it is what stops the solver answering "I cannot reach" with a dislocated
  shoulder.
- **The reset is separable from the report and is reversible**: the five clips are clamped in the
  `.blend`, and the artist's own pose file still carries the originals, so
  `pose_weapon_hold.py copy-from <pose>.blend --actions attack_throw,... --save` puts any of them
  back. What the clamp cost each one is measured above (worst wrist 0.012 m on the jab, 0.058 on the
  throw, 0.115-0.120 on slash/swing/chop).

**5. THE USER'S NEW UPRIGHT AIM POSE — more blade, a relaxed head, and ROOM FOR THE IK** (authored in
`merged_animation_new_upright_aim_pose.blend`, brought in as the one action). The idea is to author
the pose comfortably INSIDE every body's reach so the support-hand and stock-mount IK have slack to
pull IN rather than being asked to stretch, which is what makes a short-shouldered body fail. It
works, and the numbers say by how much:

| | reverted pose | user's pose |
|---|---:|---:|
| support grip miss — Godot-chan / Fumiriya | 0.011 / 0.009 m | **0.002 / 0.001 m** |
| — Shino | **0.072 m (FAIL)** | **0.038 m (PASS)** |
| support shoulder protraction — Godot-chan / Fumiriya | 16.4 / 17.9 deg | **2.0 / 3.4 deg** |
| stock-mount hand move (the IK's own work) | 0.085–0.098 m | 0.139–0.163 m |
| blade, in game | 48–50 deg | 54–70 deg |

The clip itself measures blade **+58.0 deg** (spine 39.3 + collarbones 18.6, against the previous
26/18.5), the palm **0.144 m** in front of the shoulder joint (was 0.205 — this is the room), and the
right eye **0.093–0.170 m** over the gun's top (was 0.058 — the relaxed head). Two things to watch,
both cheap to fix in the pose: the clip's bore is **7.3 deg off level**, which the aim modifiers
correct every frame but which costs the shoulders a permanent 7 deg of it; and **Shino is still
pinned at the runtime 40 deg protraction cap**, so she passes with no headroom.

**6. THE STANCE AGAINST THE REFERENCES: WE ARE IN THE TRADITIONAL BLADED BAND, NOT A MODERN CQC ONE**
(user-asked, 2026-09-20). Shooting-stance practice puts a traditional/target bladed stance at 40-60
deg off the target, a modern tactical/CQC carbine stance at 0-15 (squared, so armour faces the
threat and recoil goes into both legs), and a prone/precision one at 15-30; the rigging advice for
ONE base pose driving every long gun through IK is **15-25 deg**, because past ~45 the off-hand
shoulder is pulled so far back that the IK straightens the support arm to reach a forward handguard
and the elbow locks. **Measured, this pose is at 58 deg in the clip and 54-70 deg in game**, i.e.
traditional-bladed — and our own numbers show the predicted cost rather than merely the theory:
Shino (shoulders 0.2174 m) sits **pinned at the runtime 40 deg protraction cap** with her support
arm effectively straight, which is exactly the failure the 15-25 recommendation exists to avoid.
- **Measured, not argued.** `blender/tools/aim_pose_delta.py --blade` takes the blade off by turning
  BOTH CLAVICLES (see its docstring for why that is the only lever that survives the aim modifiers),
  and at **31.5 deg of clip blade** the same three bodies measure: Shino's support shoulder
  **40.0 -> 15.7 deg** (off the cap) and her grip miss **0.038 -> 0.013 m**; Godot-chan and Fumiriya
  protract **2.0/3.4 -> 0.0** (their arms reach unaided). Everything still passes.
- **Not shipped, because the silhouette is the artist's call and it did not move the way the theory
  says:** the IN-GAME shoulder line went the other way on two of the three bodies (Godot-chan
  61.5 -> 66.0, Fumiriya 54.1 -> 59.0, Shino 69.8 -> 66.1), since the aim modifiers re-square the
  chest by whatever the clip's chest-to-bore angle leaves them. So the reach improves and the
  silhouette does not: one command applies it if that trade is wanted
  (`--lean 8 --blade -30 --save`, then export/import/rebuild).

**THE SPINE LEANS 8 DEG FORWARD** (user-asked, shipped): `--lean` shares the bend equally over
`spine_01/02/03`, with nothing counter-rotated anywhere — the arms and the weapon ride the chest,
the aim modifiers re-point the bore in game, and what SURVIVES that is the POSITION. Measured:
chest lean **+0.4 -> +8.4 deg**, the head **+0.030 m further forward** over the firing hand.
- **What a lean CANNOT do, and it is worth knowing before authoring another one: it does not close
  the head-to-weapon gap.** The head and the arms are both children of the chest, so leaning moves
  them together — measured, head-to-gun-hand stayed **0.239 m** and its vertical component moved
  0.211 -> 0.210. The gap is `NeckFront`'s: in combat the neck and head are replaced 100% by the
  T-POSE, so no authored cheek weld can show. That is now a deliberate decision (user, 2026-09-20 —
  the T-pose secures the head and the aim IK turns the face onto the target), and closing the gap
  means letting the clip's head through, which is the one thing that layer exists to prevent.

**A PLACEHOLDER IS A COPY THAT NOTHING REFRESHED.** `upright_aim_sniper` was minted from
`upright_aim_rifle` and then sat frozen while the rifle pose was re-authored twice — it was the only
clip still laying the head 34 deg over. `rename_character_anims.py --refresh-placeholders
[--refresh-only=<names>]` re-copies one, opt-in and naming what it overwrites, because once the
sniper pose IS authored, refreshing it is exactly the wrong thing.

**7. THE BLADE SWEPT, AND THE ANSWER IS THE OPPOSITE OF THE WORRY** (user-asked: "if we follow CQC,
does Shino stop working?"). Squaring the pose up is the thing that FIXES her. Measured on the
shipped path, three bodies, upright, the clip's blade taken down with `aim_pose_delta.py --blade`:

| clip blade | Shino shoulder | Shino grip | Godot-chan / Fumiriya shoulder | in-game blade (GC / Sh / Fu) |
|---:|---:|---:|---:|---|
| **58.0** (shipped) | **40.0 deg, PINNED at the cap** | 0.038 m | 2.0 / 3.4 | 61.5 / 70.1 / 54.2 |
| 31.5 | 15.7 | 0.013 | 0.0 / 0.0 | 66.0 / 66.1 / 59.0 |
| 24.5 | 12.7 | 0.011 | 0.0 / 0.0 | 67.2 / 66.5 / 60.4 |
| **13.8** (CQC-squared) | **9.9** | **0.008** | 0.0 / 0.0 | 69.0 / 67.8 / 62.3 |

Every body passes at every setting, and the improvement is monotonic — which is exactly what the
rigging guidance predicts (past ~45 deg the off-hand shoulder is pulled so far back that the IK
straightens the support arm to reach a forward handguard). **So the narrowest-shouldered body is the
one that gains most from squaring up, not the one that breaks.**

**AND THE CLIP'S BLADE IS A REACH KNOB, NOT A LOOK KNOB — in THIS rig.** The on-screen shoulder line
moved by at most 7.7 deg across a 44 deg change in the clip, because the aim modifiers re-square the
chest by whatever the clip's chest-to-bore angle leaves them: the silhouette is mostly the SOLVER's,
the clip mostly decides how hard the IK has to work. That is why the reference-stance question
("traditional 40-60, modern CQC 0-15, one-IK-pose 15-25") does not settle it on its own here, and
why the pose can be chosen for reach at almost no cost to the look.
- **Not shipped: this is the artist's call, and one command applies any row**
  (`aim_pose_delta.py -- --lean 8 --blade -30 --save`, then export / `--import` / rebuild the library).
- **The sniper is NOT a CQC question.** A precision rifle standing is a traditional bladed stance and
  prone is 15-30 deg, so it wants its own pose — and the slot already exists: `sniper` is grip
  archetype **9** with its own `upright_aim_sniper` clip, blendspace point and switch clip (W: SR3).
  What it does not have is an AUTHORED pose; it is a placeholder copy of the rifle's, so today it
  inherits whatever the rifle does. Author it there and the two part company with no code change.

**8. THE WORKBENCH CAN SHOW IT: `V` AND `M` EXIST NOW.** Both were described in this file and in
PLAN.md 6.14(c) and **neither was ever bound** — `AimDebugHost` had no `V`, no `M` and no
body-switching code at all, so "AimWorkbench can no longer switch the body" was never a regression,
it was a feature that had only ever been written down. (`tools/godot/probe_aim_bench.gd` had been
pressing both keys into the void.) Now:
- **`V`** (shift-`V` backwards) cycles the mannequin's body through every
  `CharacterVisuals_*.tscn` beside the reference, DISCOVERED with `DirAccess` so a body the
  generator adds appears with no edit, plus "the scene's own" as one of the stops. The body is
  chosen BEFORE `add_child`, because `Character._ready` is what instances the visuals.
- **`M`** sweeps every catalog bench weapon on the current body and logs one measured line each:
  what is held, how far the stock mount dragged the firing hand and whether it fell short, the
  support grip miss with the reach it was asked for against the reach that arm HAS and the shoulder
  it cost, and the gun's angle off the aim. Same quantities `probe_weapon_fit` asserts — a gate says
  PASS, this says whether the hold looks like a hold while you watch it.
- **The sweep is frame-driven, not a loop.** Arming frees and rebuilds the mannequin and the numbers
  come from skeleton MODIFIERS that have not run on the frame the body is built: a loop printed "no
  mount, no SupportPoint, NaN" for all fifteen weapons, and 40 frames of settle still read the FIST
  (the deferred equip, the slot sync and the ~0.45 s draw have to land first). 110 frames is the
  shipped settle.
- Read `gun` last, not first: the stand spawns the mannequin facing away from the aim ball, so until
  the ball is moved round in front (I/J/K/L) the stance's yaw limit is what that number measures.

**9. CRAWL HAS ITS OWN AIM POSES AT LAST — the aim branch is stance-driven** (user-authored,
2026-09-20). `crawl_aim_pistol` and `crawl_aim_rifle` had been exported, ORPHANED and unreachable
since W10: the aim branch (`WeaponAim`) is indexed by grip ARCHETYPE only, so there was nowhere for
a prone pose to go, and crawl aimed with the STANDING arms on a prone chest — AIM_PLAN.md's W4, open
since the beginning. The tree now has the stance dimension:

```
CombatTransition 0 <- AimStanceTransition  { Default <- WeaponAim ; Crawl <- WeaponAimCrawl }
```

`WeaponAimCrawl` is its own copy of the 10-point archetype blendspace (a node's output feeds ONE
input — the reason `WeaponAimTorso` already has one), and `AnimationController` drives the
transition from the stance's own ANIMATION KEY, so Swim borrows Crawl's aim exactly as it already
borrows Crawl's ring, with no second table. Every archetype got a `crawl_aim_<arch>` slot minted
as a copy of its UPRIGHT twin (the W12 bootstrap), so wiring the branch changed nothing for the
eight nobody has authored yet, and each is now a named, wired slot whose edit reaches the game.

**Measured in game, crawl, against the standing arms it replaced:**

| | before (standing arms, prone chest) | after (authored prone poses) |
|---|---:|---:|
| blade, Godot-chan | 46.8–53.8 deg | **8.2–32.5 deg** |
| support grip miss | 0.012–0.026 m | **0.000–0.004 m** |
| support shoulder protraction, Godot-chan | 17.4–31.2 deg | **0.0–5.8 deg** |
| — Shino | **40.0 deg (PINNED at the cap)** | **0.0 deg on every weapon** |

The clips themselves measure square and sighted: the pistol pose blade **+1.8 deg**, support grip
**0.000 m**, eye 0.010 m over the bore, **poke 0.000 m**; the rifle pose blade +0.5 deg, gun +5.7 deg
of pitch, firing elbow 66 deg (against the old placeholder's **-80.7 deg of gun pitch and a 157 deg
hyperextended elbow**, which is what "the strange crawl animation" was).

**How the prone pose is built** (the artist's description of it, 2026-09-20, recorded so the next
person reading these numbers knows what they are looking at rather than inferring a rule from them):
prone, the shoulder is turned roughly 180 deg from its rest position — the same thing an upright
body does holding the weapon straight up — so an IK driving that joint would be taking the hand up
past the top of the head. Measured on the authored crawl rifle pose, that is where the rotation
sits: `upperarm_l` **134.5 deg** and `neck_01` 66.9, while the collarbones stay small
(`clavicle_l` **39.7**, `clavicle_r` **34.9**).

**ONE OPEN ITEM, and the gate found it rather than a walk-test: `gun_travel` on the crawl ring is
now 0.110 m against its 0.08 limit** (`crawl_forward/back/left/right`; `crawl_idle` is clean). It is
a true consequence, not a false alarm: a prone aim holds the palm **0.376 m** in front of the
shoulder, so the same body motion in the crawl cycle is amplified at the hand — the aim modifiers
re-point the bore but they do not translate, so the weapon really does slide. The four moving crawl
clips are still W10 PLACEHOLDER copies of the forward crawl, so the fix is in them (damp the cycle,
or author real prone locomotion), **not in the limit** — bending a checker to fit is the defect this
file keeps recording.

**Crawl's aim pitch band is already the tightest of any stance** and the new pose is its level
baseline: `aim_pitch_max/min` **+30 / -30** against upright's +45/-65 and crouch's +40/-60, with the
view at +40/-35. A prone chest genuinely cannot look far up, so if it still reads as too much the
number to move is `Stances/Crawl.aim_pitch_max` — one field, no code.

**10. ONE PLACE TO LOOK: body x weapon x stance, on the shipped path** (`shift+M` in AimWorkbench,
headless `tools/godot/probe_aim_review.gd`). The gap was real and it was not a missing gate:
`probe_weapon_fit` measures weapon x stance for ONE body per run, `V`+`M` measure body x weapon at
ONE stance, and the Blender side measures the CLIP before any modifier runs — so judging a shared
pose meant stitching two tools together and nothing showed the matrix at once. The review walks
**4 bodies x 15 weapons x 3 stances = 180 cells**, logging per cell what is held, how far the stock
mount dragged the firing hand and whether it still fell short, the support grip miss with the reach
asked for against the reach that arm HAS and the shoulder it cost, and the gun's angle off the aim.
**It asserts nothing, deliberately** — the gates answer "did this regress", this answers "show me".

Three things it took to make its numbers mean anything, each of which had produced a full, plausible,
wrong table first:
- **Combat ON explicitly, never by pressing the toggle.** `4` FLIPS combat and the mannequin spawns
  already in it, so "turn combat on" turned it off: every cell then read a believable stock and
  support while the gun sat **55-123 deg** off the target, because with combat off the aim branch
  never runs at all. Now 0.1-1.0 deg.
- **Turn the BODY at the target, not the ball at the body.** The stand parks the mannequin facing
  away (it is a shooting bench too), and a fit read facing away is a reading of the stance's YAW
  CLAMP with the arms wrapped round the body — the same body and weapon read grip 0.037 m /
  shoulder 38.8 deg facing away and 0.000 / 0.0 facing the target. Turning the body is also what
  survives the per-cell respawn, which restores the yaw.
- **Print the stance the BODY is in, not the one that was asked for.** Three identical rows is
  indistinguishable from "this pose does not vary by stance"; the live readout is what showed the
  stance was fine and combat was not.

What it says today, and both are findings rather than failures: crawl's SHG1 needs **29.8 deg**
(Godot-chan) / **25.4** (Fumiriya) of support shoulder, because a pump sits further forward than a
prone arm reaches — every other long gun is 0.0-7.0; and melee, fists and throwables report nothing,
because they declare neither a mount nor a support point, which is the honest answer rather than a
number.

**11. EVERY LONG GUN IS ONE GRIP ARCHETYPE NOW** (user decision, 2026-09-20). ASR1, ASR2, SHG1, SMG1
were already `rifle`; SNR1 moved onto it too, because splitting it only ever meant copying the
rifle's clips across and keeping four more placeholders in sync — the `sniper` set had ALREADY
silently diverged twice (it missed W44's blade, and its crawl slot was minted from the UPRIGHT pose,
so a crawling sniper would have played a standing hold while a crawling rifle played the authored
prone one). Archetype **9 and its clips stay as a reserved slot**, unplayed: the index list is
append-only (W12) and removing it would touch the enum, four blendspaces in three scenes and the
catalog, where the split now costs one field in `SNR1.tscn` plus an authored pose. Measured after:
all five long guns identical upright (blade 61.5 deg, grip 0.000-0.002 m) and in crawl SNR1 matches
ASR1 exactly; `probe_weapon_archetypes` reads **4** hand-pose clusters.

**12. CRAWL'S AIM BAND IS ASYMMETRIC AND TIGHT UPWARD** (user-reported: the new prone pose reads as
an idle aim near the top of what a prone body can reach). It was the BAND, not the pose. Upright and
crouch are deliberately asymmetric — a trunk bends forward far more easily than backward (W5) — and
crawl was **symmetric at +-30**, on the one posture with the least left: the authored prone pose
already spends **66.9 deg of `neck_01`** just to look level forward, the largest neck rotation in the
library. Crawl is now **view +15 / -35, bone +10 / -30**. Measured on AimDebugAuto: looking up, the
view caps at 15.0 and the gun holds at 10.0 with the head at -15.0; looking down, view -35 and gun
-26.4. Shooting upward is what standing up is for.

**13. "THE ARM MOVES IN AND OUT CONSTANTLY IN CRAWL" — AN AIM CLIP HELD TWO POSES** (user-reported,
2026-09-20, in game and in the workbench; not in the .blend, and crouch was clean). Measured with
`tools/godot/probe_crawl_jitter.gd`, which holds a STATIONARY aim and logs the support hand frame by
frame — a still target means anything that moves is a per-frame loop, and the PERIOD separates the
suspects (1-2 frames is an IK solve fighting itself, ~9 is the 0.15 s bore blend).

| crawl, stationary target | hand travel | support reach spread | reversals |
|---|---:|---:|---:|
| as reported | **0.1145 m** (0.0896 in ONE frame) | **0.0784 m** | 142 in 180 (~2.5 frames/cycle) |
| crouch, same test | 0.0107 m | 0.0000 | 2 (steady) |
| after the fix | **0.0146 m** | **0.0000** | **0 (steady)** |

**It was not the aim solver.** The reach being ASKED for changed every frame on a still target, and
the support clavicle never moved (0.00 spread), so the WEAPON was moving. Forcing the aim branch back
to `Default` in crawl (`--aim-branch=`) was steady and `Crawl` was not, which put it in the clip —
and the clip is **two frames whose hands are 0.49 m apart**: frame 0 the authored prone pose, frame 1
the old placeholder it replaced (gun pitched **-80.7 deg**, elbow flared **157 deg**, the very pose
measured as unusable). A blendspace point PLAYS its clip, so the game alternated between them.

**AN AIM OR HOLD CLIP IS ONE POSE**, and nothing was watching because every upright aim clip happens
to be a single frame. `check_character_anim.py`'s **`pose_clip_moves`** is that eye now: a hand may
travel at most 0.05 m across a pose clip's own range (breathing, not a second pose), checked only on
clips the AnimationTree actually PLAYS — an orphan cannot alternate in game, and failing an export
over one would report a fact about the `.blend` as a defect in the game. It fired on the two crawl
clips and on the sniper copy taken from one of them.

**Probe traps this cost, all three already written down in this file:** `request_equip` is not a
registered method, so calling it aborts the script — which in a `--script` run reads as a HANG
(`probe_weapon_fit`'s pickup path is how a probe arms a body); Godot's stdout is block-buffered when
piped, so a killed run prints nothing at all; and the stance keys are EDGE-driven, so a probe that
releases the key measures UPRIGHT while reporting "crawl" — print the body's own stance ordinal, not
the key that was pressed.

**Gates, all on the final state:** `probe_weapon_fit` **12/12** (three bodies x upright/crouch/crawl/
swim — the four-stance matrix 6.14 named as the verification gap that let W44 ship); AimDebugAuto
**40/40**; `check_character_anim` PASS (171 clips, 0 errors); `probe_shared_anims` 2/2;
`probe_body_contract` 3/3 on both VRoid bodies; `probe_self_hit`, `probe_support_hand_ik`,
`probe_switch_spin`, `probe_crawl_balance`, `probe_melee`, `probe_recoil_kick`, `probe_fps_camera`,
`probe_weapon_{sockets,holster,archetypes}` PASS; `./gradlew build test` green.

## Vehicles — the component car: GTA III / SA damage, three models (2026-09-19)

`blender/VEHICLE_AUTHORING.md` is the how-to. Three cars ship in the component standard: **SPC-1** (sports coupe, the
project author's model), **PIT-1** (pickup) and **POC-1** (police car, Japanese black-and-white), the last two
cut out of elbolilloduro's "Vegetation" pack (models CC0; its textures are NOT used; credited). Ids follow the weapon
rule (3-letter type code + series). DebugWorld parks all three behind `VehicleRoot`.

- **Pipeline**: `<ID>.blend` → `blender/tools/build_vehicle.py` → `<ID>.glb` + MEASURED `<ID>.vehicle.json` →
  `tools/build_vehicle_scenes.py` → `vehicle/<ID>.tscn` (INHERITED from `Vehicle.tscn`) + `<ID>Config.tres`. Nothing
  in a car scene is hand-placed. SPC1's .blend is the artist's authoring layout and the build NEVER writes it: it is
  split in memory (`SOURCE_GROUPS`); its honeycomb grilles ship as placeholder planes. PIT1/POC1 are already in
  component form (`blender/tools/import_pack_vehicles.py`, one-time).
- **The model** hangs 0.8 m under the body origin (the COM Vehicle pins 0.3 m under the origin lands ~0.5 m up).
  Wheel mounts = modelled centre + the spring's EQUILIBRIUM length, `rest − m g / 4k`: each tyre then sits in its own
  arch to the millimetre. `VehicleWheel.modelMesh` names the glb's wheel, which `Vehicle._ready` moves under the
  wheel's `Wheel` node (`adoptModelMesh`) — spin, steer, suspension and flat squash unchanged.
- **`carrier/vehicle/VehicleDamageModel`** (child `DamageModel`; a vehicle without one is unchanged) finds parts BY
  NAME and walks each OK → DENTED → LOOSE → OFF (`VehicleDamageRules`, engine-free, `VehicleDamageRulesTest` 8).
  DENTED blends the part's `dam` shape key (generated by the build); LOOSE swings it on its hinge (the origin) from
  the specific force of the car's OWN motion, read from its position so a frozen puppet flaps its doors too
  (`hingeAccel`/`stepHinge`; gravity hangs a bumper and shuts a bonnet, air lifts a loose bonnet); OFF drops it as a
  cosmetic RigidBody (layer 0, mask WORLD, capped at 32, 25 s). The chassis `dam` follows health.
  - **Crashes**: `Vehicle._integrateForces` → `feedCrash`: this step's contact impulses / mass (skipping a contact that
    pushes UP — resting or landing) at the impulse-weighted point, summed over a crash's steps into ONE impact and
    shared among the parts near it. `VehicleConfig.crashHealthPerDv` makes crashes cost health (0 in the prototype).
  - **Bullets**: `ImpactManager.processHit` → `applyHit` on the part under the hit point (not a tyre hit).
  - **The net**: a 2-bit-per-part mask (`VehicleDamageRules.SLOTS`, APPEND-ONLY) rides the vehicle snapshot
    (`partMask` i32, `VEHICLE_SNAPSHOT_ENTRY_FIXED_BYTES` +4). States only rise, so every peer MAX-merges any report
    (the simulating peer's crashes, the host's bullets) and the result needs no authority. Swing, dents and debris
    are local. `MSG_VEHICLE_SPAWN` gained a `model` byte indexing `VehicleModels.SCENES` (APPEND-ONLY) — before it,
    a client instanced `Vehicle.tscn` for every host car; a snapshot-lazy-spawned prototype is replaced when the
    real spawn names another model.
  - **Wreck**: on destruction the panels blow off and `dressWreck` puts a burnt copy of the car (dents, wheels, the
    parts already gone) in the wreck scene with the car's own hull.
  - **Paint**: a surface on material `car` is repainted per car from a hash of its id (every peer agrees).
- **Doors on enter/exit** (Godot, not Blender: a clip would fight the damage states): `tryEnter`/`tryExit` (every peer)
  → `openDoorFor(seat)` opens the nearest door on the seat's side to 65°, holds, slams. The open door is solid through
  its OWN `AnimatableBody3D` (layer VEHICLE, excepted from its car) — never a shape on the car's RigidBody: the driver
  steps out where the door opens, and a car shape overlapping them was resolved by throwing the CAR, 100 m/s in one
  frame. A kinematic door stops a character walking into it, takes bullets (they dent that door) and pushes nothing.
- **Gate `tools/godot/probe_component_car.gd -- --car=SPC1|PIT1|POC1`** 40/40 each: scene vs facts, rest height and
  wheels in their arches (0.000 m), a car set down 0.3 m high settling to 2 mm, front crash dents / removes the
  bumper, crash health, bullets loosen one door, a loose door swinging to 70° under a kinematic (puppet) move, the
  mask reproducing a car, hips on the cushion (0.079 m) and the eye under the roof, the enter/exit door with its
  collider and the car staying still, the burnt wreck. `--control` (damage off) fails exactly the 7 damage checks.
- **The box prototype is retired as a car** (user decision). `Vehicle.tscn` is now only the shared BASE the cars
  inherit (seats, cameras, weapons, nameplate, net wiring): its placeholder body mesh and debug camera cube are
  deleted (41 KB -> 10 KB), `WheelPlaceholder.tscn` is deleted, and nothing spawns it. The placed `VehicleRoot` in
  World / DebugWorld / WorldMaster is an SPC-1 on its own config; DebugHarness spawns SPC-1; the network fallback
  (`VehicleModels.DEFAULT`) is SPC-1; every test stand and probe that used the prototype drives SPC-1.
  `VehicleWheel.tscn`'s cylinder and `VehicleWreck.tscn`'s boxes stay: the motorcycle, boat and airplane use them.
- **Traffic draws from a pool**: `VehicleSpawnConfig.vehicleScenePath` empty (the default) = `VehicleModels
  .trafficScene(faction)` — police drive POC-1, everyone else SPC-1 / PIT-1 (60/40), chosen on the host; clients get
  the model index. An explicit path still forces one model.
- **The collision hull is a GAME body**: `build_vehicle.py` raises its floor to `HULL_FLOOR` (0.32 m) and pulls points
  past the body's width (the side mirrors) in to it. The visual sill height (0.18 m on SPC-1) hit a 0.15 m kerb at
  35 m/s and climbed it (`probe_road_launch`, 4.3 m/s); with the game hull 0 launches, worst rise 0.74 m/s.
  `probe_road_launch`'s edge cases now mean "outer WHEELS on the kerb line" for any track (the -3 m was written for
  the prototype's +-1.1 m wheels). Its flat-out cases leave the road in the same 3 places with SPC-1 as with the
  prototype (governor off by design).
- **Two pre-existing defects the real cars exposed, both fixed:**
  - A character seated before it ever LANDED (traffic spawns a driver and seats it the same frame, in the air)
    kept `OnFloorBlend` at "airborne" for good — seating switches its physics off, so `isOnFloor()` never changed —
    and sat bolt upright, head through the roof. `AnimationController` counts a seated body as on the floor, and
    lands it on the seat edge BEFORE the LOD gate (a PASSIVE/FROZEN driver beyond 80 m got no tree writes at all).
  - The parking lock froze an unoccupied car MID-SETTLE (velocity zeroed below 0.5 m/s while the overdamped
    suspension was still easing down): set down 0.3 m high it hovered 0.32 m. `Vehicle.suspensionSettled()` (no
    spring faster than 0.01 m/s) now gates both the lock and parking into sleep.
- **The wheel-sensor review** (`tools/godot/bench_wheel_sensor.gd` behaviour, `.sh` cost: one mode per fresh process,
  median of 5 — in one process the step time climbed round over round, 2.7 → 11 ms, so single-process numbers are
  noise). `VehicleConfig.wheelSensor`: 0 rays (shipped), 1 sphere, 2 tyre cylinder. Measured on SPC1:
  cost for 40 cars 5.15 / 5.40 / 4.59 ms per step (1 ray / 3 rays / sphere): equal within noise, so the choice is
  not a performance one. A 0.15 m kerb at 15 m/s: rays lift the body at 0.47 m/s and pitch it 0.17 rad/s, sphere and
  cylinder 0.03 / 0.02 — 15x smoother, the tyre rolls onto the edge instead of the axle snapping up. 1 ray and 3 rays
  are IDENTICAL on a kerb (the fore/aft rays only matter over gaps narrower than their spread). A wall scrape at
  20 m/s: no mode launches (rise ≤ 0.01 m/s); roll 8.4° rays vs ~12° sphere/cylinder (the cylinder cannot reach the
  wall, so it is the car's response, not the sensor reading the wall). Drift and high-speed feel are the tyre force
  model's (grip curves, drift grip, yaw torque), not the ground sensor's. The extra fore/aft rays were cast twice a
  step (enabled AND forced); they are forced only now.

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
  `auto_setback` (before W17 was closed, a second pass grew it): 0 errors, no finding on the pad, 0 of 465 nearby lane samples
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
  `assets/world_source/kits/road_kit/road_kit.json` — every material as the glTF entry Blender's exporter produced
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
  wrote (`Roads_DebugRoads_*`, `Roads_RoadKitZones_*`, `RoadKitSample`). `point_build`/`point_nodes` stayed for
  `build_island_base.py` until 2026-09-18, when both were deleted (PLAN.md 3.10, "The island's roads stream as a
  504 m grid"). The digest salt is now the Python builder's sources and `road_kit.json`'s bytes.
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

**A PIER IS A MODELLED ASSET: RIGID CAP, STRETCHED SHAFT (PLAN.md 3.5, 2026-09-17, user decision: a modelled
asset slot, not a procedural enum).** A road names `RoadData.pillar_asset` (blank = the plain `rka_pillar_w` box,
byte-identical to before), and `point_mesh.pillars` stands that mesh at every placement the solve already makes
(`pier_placements`: the deck-centre curve resampled every `rka_sp_pillar`, kept where `rka_pillar_param`).
- **The asset** is a `RKA_PIER_<variant>` MESH in `road_kit.blend`'s `ROAD_KIT` collection: Z-up, origin at the TOP
  centre (the soffit), +Y along the road, +X across, at its REAL size (never scaled to the deck, like a profile).
  Its `rka_stretch_z` custom property splits it: every vertex above is rigid (cap, crossbeam), every vertex below
  stretches linearly so the lowest point lands exactly `rka_pillar_h` under the soffit, i.e. on the ground. A pier
  shorter than its cap + `PIER_MIN_SHAFT` (0.3 m) is squashed whole instead. **Each shaft vertex stretches to the
  ground under ITSELF** (the build's ground grid, `place_pier(ground=)`), not under the centreline: stretched to the
  centreline's ground, the portal's side columns (5.5 m off the road's line) stopped 5.09 m over the sloping seabed
  at hama_dori (`probe_road_ground.gd -- World.tscn`, 3 columns); now 0. Any number of materials, each face its
  own. `export_road_kit_data.py` writes each as `piers[name] = {stretch_z, tris: {material: [9 floats]}}` into
  `road_kit.json` (rotation/scale applied, location not, so a pier can stand anywhere in the kit file).
- **Shipped placeholders** (`build_road_kit.py PIERS`; `-- --add-piers` re-makes only these in the existing kit file,
  so hand edits survive): `round` (r 0.9 m column), `hammerhead` (the Shuto T-pier: 12 m tapered cap on a 2.6 x 2.0 m
  column, `stretch_z` -1.8), `portal` (a 16 m crossbeam on two round columns, -1.5). Model a real one in the kit
  file, then run `export_road_kit_data.py`.
- **Wired:** DebugRoads' `link` and `east` (9 m deck half-width) stand `hammerhead`; the island's two sea crossings
  `hama_dori` and `kuko_dori` (29 m decks, columns 3-48 m) stand `portal`.
- A name the kit lacks falls back to the box and is reported (`missing_style` row `(road, "pillar", "asset",
  name)`); a pier reaching past the deck edge is reported as `pier_overhang` (the build prints both).
- Gates: `point_kit.py` (resolve + missing), `point_mesh.py` self-test (cap rigid, foot exactly `height` down,
  turned onto the heading, short pier squashed whole), `check_roadkit_build.py` on `RoadKitStyled` (demo_hwy's
  hammerhead: a whole number of the pier's triangles and the full 12.4 m; the 16 m portal on a 7 m ramp deck is the
  only overhang; control: blank demo_hwy's pier -> 2 FAIL). On the rebuilt DebugRoads pieces
  `probe_road_ground.gd` 201/201 column feet on the terrain, `probe_road_zones.gd` 12/12, `probe_road_launch.gd`
  0 launches; on the island `probe_road_ground.gd -- World.tscn` 2408/2408 and 0 short columns,
  `probe_traffic_spawn --world=island` PASS, `check_roads.sh` PASS=40. Rebuilding the island piece also landed
  3.4b's fix in its lanekit (28 connectors lose a duplicate control point), so the island road map was re-baked. The Blender road build (`point_build`, island base only) does NOT read `pillar_asset`.
- **Still art, not code:** real pier models, and the named hero bridge (Rainbow Bridge), which is authored
  content fitted to a road with `pillar_skip` on its stations.

**A road's texture is a material library, resolved by NAME at bake (PLAN.md 3.6c, 2026-09-17).** glTF carries
the kit's procedural materials only as a flat base colour and the swept mesh has no UVs, so the textured look
lives in Godot: `assets/world_source/kits/road_kit/materials/<M_name>.tres` — `M_Asphalt` (`T_Concrete_Asphalt`),
`M_ConcreteTile` / `M_Concrete` / `M_Barrier` (`T_Concrete`, tinted), with the kit's ORM + normal maps, all
**world-space triplanar** at the Quaternius tile (3 m x `module_scale` 0.91 = **2.73 m**, measured off the kit's
own `Street_*` UVs). `WorldBaker.applyMaterialLibrary` (every bake, after conversion) replaces any mesh surface
whose material is named like a file there; the baked scene REFERENCES the `.tres`, so editing one restyles every
piece with no rebake, while adding or removing a name needs one — `point_digest.builder_salt` hashes the directory
for that reason, so the next `DIRTY_ONLY` build rebakes everything. The names keep `resource_name`, so the editor
draft (`materials_from`) wears them too. Markings (`M_LineW/Y`) and `M_Median` stay flat. Gate:
`tools/godot/shot_road_surface.gd -- <out> [--piece=] [--flat]` (needs a display; `--flat` is the control).
The decals and props are the next paragraph.

**Road decals and street furniture are PLACED by the Road Kit, from facts the build already owns (PLAN.md 3.6c,
2026-09-17).** `blender/addons/road_kit_authoring/point_furniture.py` (pure python, self-tested) runs inside
`roadkit_cli.py gltf`; `assets/world_source/kits/road_kit/furniture.json` is its table (which kit piece, lift, scale, `collide`,
`exclude_roads` globs, and every spacing).
- **At each junction arm, on the APPROACH road** (the Japanese order a driver meets them): a turn arrow on each arriving
  lane 14 m back, chosen from the turns of that lane's connectors (S, L, R, S+L, S+R; L+R and all three get none);
  a stop line 7 m back across the ARRIVING lanes only; a zebra 1-5 m back across the whole carriageway, 45 cm bars and
  gaps with no side bars. The lanes come from the lanekits `pieces` wrote in step 1, ALL of the network's, because a
  mouth's connectors stream with the pad's piece.
- **Along the kerbs:** a drain in the gutter every 20 m, a planter (collides) on a footway at least 3 m wide every
  30 m, and bollards (collide) round every junction corner that has a footway. Manholes every 90 m per through lane,
  at a phase hashed from the lane id, so an unchanged record rebuilds byte-identically. Nothing where a barrier
  stands, or where a ground grid says the lane is more than 2 m up (a bridge). Planters and manholes skip
  `shrine_touge*`.
- **The arrows are the kit's decals; the stop line and zebra are PAINT** (triangles in the road's `mark_w`
  material, object `FURN__marks_w`), because the kit's crosswalk has side bars and it has no stop line.
- **Kit pieces leave as `mmesh_<asset>` glTF nodes** carrying `asset_path` in their extras (`point_gltf.marker_node`,
  piece -Z along `fwd`). `WorldBaker.buildMultiMeshes` already collapses those into one MultiMesh per asset;
  `withKitMaterials` now gives each a DUPLICATED mesh wearing `<kit>/materials/<name>.tres` (the imported material
  turns on vertex-colour-as-albedo from the kit's COLOR_0 wear mask, the buildings' trap). `MI_StreetDecals.tres`
  (alpha scissor) and `MI_Dirt.tres` were added, and their textures set to the 3D import (mipmaps, VRAM) the other
  kit textures already had. Collision is one `FURN_props-prop-colonly` proxy of oriented boxes.
- **The digest** salts `point_furniture.py`, the table and every piece it names, and hashes each lane's successor turns
  into the lane's own piece (an arrow depends on a connector in another piece).
- Measured: DebugRoads (no footways) 159 placements, 7 crossings, 14 stop lines; the island 4659 (1059 planters,
  417 bollards, 2435 drains, 682 manholes, 66 arrows, 36 crossings, 68 stop lines). Picture gate
  `tools/godot/shot_road_furniture.gd` (needs a display; frames `--per` instances of every MultiMesh from behind
  along its own forward). Two traps: a MultiMesh reads identity transforms under `--headless` (the dummy renderer),
  and an unfocused window saves the SAME frame every shot unless `RenderingServer.force_draw()` runs first.
- **Lines stop at the stop line and the zebra (2026-09-18), the Japanese layout.** A lane line on the arriving side
  and the centre line end at the stop line's upstream edge, nothing is painted across the zebra, and a departing
  lane's line starts past it. `point_furniture.clear_zones` derives the keep-clear rectangles from the SAME arm
  frames (`_arms`) and the same placement tests (`_has_zebra`, `_has_stop`) the marks are placed with, so a line
  only stops where a stop line or zebra was actually painted; `point_mesh.build(clear=)` clips every mark polyline
  against them (`clip_outside`, Liang-Barsky per segment, dashes cut at the edge, heights interpolated). Measured,
  mark vertices inside a zone: DebugRoads 423 -> **0** (of ~7.4 k), island 438 -> **0** (of ~74 k); the control is
  `clear=None`. The editor's draft (`roadkit_cli.py live --mesh`) has no lanekits and still draws lines through.
- **Signals and street lighting (2026-09-18, user-asked).** Three pole pieces from Quaternius' CC0 Zombie Apocalypse
  kit, made by `blender/tools/build_street_poles.py` (Blender, from `TrafficLight_2_Japan.blend` — the owner's
  Japanese re-make of `TrafficLight_2` — and the download's `StreetLights.blend`):
  - `TrafficLight_JP`: scaled ×1.099 so the vehicle head's lower edge is **4.7 m** (Japan: ≥ 4.5 m over a
    carriageway; the download's was 4.28), the pedestrian head lifted to a **2.5 m** lower edge. 5.84 m pole,
    5.5 m arm. Still carries the download's "E 12 St" name plate (atlas texture) — replace in the .blend.
  - `StreetLight_JP`: shaft stretched (base, collar, arm, luminaire rigid) to a **10 m** luminaire, the usual
    Japanese arterial mounting height (the download's 6.4 m is residential). `StreetLight_JP_Twin` mirrors the
    arm for a raised median.
  - Placement (`point_furniture._signals` / `_lamps`): a junction is signalised when any mouth is authored
    `traffic_light` or (`signal_all_junctions`) ≥ `signal_min_arms` (3) arms carry arriving traffic. One signal
    per arm on the **FAR side** (the Japanese position): 6 m past the end of the kerb lane's STRAIGHT connector,
    1 m outside that lane's kerb edge, facing the approach, arm over the arriving lanes; with no straight movement
    (a T stem, a Y) the pole is NEAR-side, on the arm's own kerb 0.5 m back from its mouth (junction-side of its zebra). The piece's arm reaches right of forward, so
    a right-hand-traffic arm is refused and counted (`signal_skipped_right_hand`). Lamps: twin-arm down a raised
    median ≥ 1.2 m wide every 36 m (then no kerb lamps), else kerb lamps every 36 m staggered side to side, 0.6 m
    behind the kerb, never over a barrier or `max_above_ground`, none on `shrine_touge*`. Signals are placed
    before every other solid prop, and planters, bollards and lamps keep `pole_clearance` (2 m) from a pole.
    Collision is the SHAFT only (`collide_pole`), never the arm's footprint. An asset may name its own `kit`.
  - The digest now hashes each successor connector's END point (it places the far-side signal).
  - Measured: DebugRoads 7 signals (2 junctions), 56 lamps; `point_furniture.py` self-test covers keep-left
    straight and T-stem placement, the right-hand refusal, the unsignalised 2-arm junction and the pole-only
    collider. The signals are static props: no signal phase logic exists yet.
- Not done: the Japanese-only marks (止まれ, the diamond, speed numbers) belong to our own `jp_street` kit
  (3.6b step 4).

**A car knocks a street pole down and keeps most of its speed; the pole comes back unseen (PLAN.md 3.11,
2026-09-18, user: "like arcade/GTA").** GTA's shape: static until hit, a physics body only while falling, restored
out of view.
- **Data.** `furniture.json` gives `signal` (450 kg), `lamp` and `lamp_twin` (250 kg) a
  `breakable {mass, break_speed 5, respawn 60}`. `point_furniture.put` then leaves the pole OUT of
  `FURN_props-prop-colonly` (planters and bollards stay in it) and puts the pole size and those numbers on the
  placement. `point_gltf.marker_node` writes them as flat `break_*` extras. Flat keys, because the importer
  keeps extras as one Dictionary meta.
- **Bake.** `WorldBaker.buildMultiMeshes` turns such an asset's batch into a `world.BreakableProps` (a
  `MultiMeshInstance3D`, named `Breakable_<asset>`). The node also stores each pole's base and yaw
  (`positions`/`yaws`), because a headless run reads a MultiMesh's transforms back as identity.
  - Its `pieceId` is the baked scene's stem (`WorldBaker.bakingPieceId`), so a key is the same on every peer.
  - Its runtime colliders are stripped before `pack()` (`removeRuntimeParts`, beside `stripEagerLodLow`). The
    baker adds the node to a live tree, so `_ready` would otherwise pack them into the piece.
- **Runtime.**
  - `_ready` builds one `StaticBody3D` "Poles" (WORLD layer) with a box per shaft, so a slow car and a
    walking character stop against it as before.
  - `Vehicle._physicsProcess` → `sweepStreetPoles` → static `BreakableProps.sweepVehicle` runs BEFORE the
    physics step. It checks, in the car's frame, every standing pole the car will reach this step
    (`PropBreakRules.reachesPole`: hull ±1.1 × ±2.0 m, read off its own convex shape, grown by the pole radius
    + 2 steps of travel + 0.35 m, ahead of the motion only). For each one at or above `breakSpeed`:
    - the collider goes off NOW, so the contact never happens. Giving the speed back after a contact would be
      a guess at what the solver took;
    - the MultiMesh instance gets a zero basis;
    - a `RigidBody3D` with the pole's own mesh falls (layer 0, mask WORLD, so it never stops a car; at most 12
      alive worldwide), kicked with the car's lost momentum at bumper height;
    - the car keeps `m_car / (m_car + m_pole)` of its velocity: 0.83 past a lamp, 0.73 past a signal.
  - The engine-free rules are `world.PropBreakRules` (`PropBreakRulesTest`, 8).
  - **The return** (`_process`, 2 Hz, only while a pole is down) needs all of these (`mayRestore`):
    `respawnSeconds` have passed; no remote player is within `hideDistance` (80 m); this peer's camera does not
    have the pole in its frustum within that distance; nothing stands within ~4 m (`SpatialEntityGrid`).
- **Network: NOTHING, on purpose (PLAN.md 3.11b, user decision: cosmetic state costs no bandwidth).** Every peer
  runs `sweepStreetPoles` for every car it sees move — a car it simulates (its velocity) or a puppet (its motion
  per step; a FROZEN body is the puppet mechanism and reports no velocity, so frozen always reads motion, and a
  park flag counts only while simulating) — knocks its own poles down and runs its own return rule. Only the
  simulating peer takes the speed loss, which then reaches every peer in the car's own snapshot.
  - Retired: `WORLD_EVENT_PROP_BROKEN` (number 12 is left unused, commented in `GameManager`),
    `sendBaselineBreakableProps`, `BreakableProps.applyRemote`/`brokenKeys` and the predicted/confirmed bookkeeping.
  - **Accepted divergence:** two peers can disagree about a pole for up to `respawnSeconds` (a puppet's
    interpolated path can graze a pole the real car missed), and a late joiner sees every pole standing. The worst
    visible case is a car stopping against a pole the other peer shows down, re-synced by the next vehicle
    snapshot. If a walk-test ever shows that matters, the fallback is making a pole non-solid to puppet contacts,
    or ONE unreliable rate-limited "pole down" hint from the simulating peer: no return event, no baseline.
  - Same rule for future cosmetic breakables (bollards, bins, trees). `world.Breakable` (glass, walls) changes
    line of sight and stays host-authoritative.
  - A zone that unloads forgets its broken poles: it reloads with them standing, which is out of view by
    definition.
  - `NetStats` now counts `world_event_sent` (every world event goes through `broadcastWorldEvent` /
    `sendWorldEventTo`, the two baselines that called `sendMessage` directly included) and `world_event_received`.
- **A CAR DOES NOT GET WIDER WITH SPEED (PLAN.md 0.8, 2026-09-19, user-reported: "a car driving down the middle of
  the road hits street poles").** `PropBreakRules.reachesPole` grew the car's plan rectangle by the step's travel
  on BOTH axes, so the knock-down sweep's LATERAL reach rose with speed: at 31 m/s it reached 1.05 m past the car's
  own body on each side. Measured on the island's expressway, driving **dead centre** (`-0.00 m right of it`) down
  `shuto_c1_F0` at 31 m/s: **16 poles knocked down over 2.7 km, one every ~36 m, with 0 contacts** — nothing was
  touched, poles simply fell and the car lost 17 % of its speed each time, which is exactly what "it hits poles"
  looks like from the driver's seat. The travel is now swept **along the motion only**: the rectangle is grown by
  the pole radius + `REACH_MARGIN` (the "about to touch" slack, legitimately isotropic) and then translated along
  the velocity by `LOOKAHEAD_STEPS` of travel, tested by slab intersection — exact for a rectangle swept along a
  line, and the "ahead of the motion" dot test is kept so a pole the car is driving AWAY from is still refused.
  Forward behaviour is unchanged. After: **0 poles, 0 contacts** over 2 738 m of the same drive, and the same on a
  city street, the coast road and a trunk road. **The geometry was measured and left alone** — over the island's
  1 962 poles the nearest same-deck lane centre is 2.85 m for a kerb lamp (0.60 m outside a 4.5 m lane's edge),
  2.40 m for a barrier lamp (0.15 m outside, on a barrier that is already there behind a 3 m car wall) and ≥ 2.75 m
  for a signal or median lamp, so a 1.10 m half-width car centred in its lane has at worst 1.30 m of room. No
  `furniture.json` change, no road rebuild. `PropBreakRulesTest` gained
  `theReachGrowsWithSpeedALONGtheMotionOnly` (a pole 2.40 m to the side at 10/20/31/45/80 m/s; it fails on the old
  rule), and `probe_road_launch.gd` now counts **poles knocked down** (`BreakableProps.breaksTotalNow` summed over
  the scene) and **pole contacts** — at speed a pole goes down BEFORE the contact, so the knock-down is what a fast
  drive shows and the contact what a slow one shows.
- **Two defects the wide reach was MASKING, both found by the DebugWorld launch gate the moment it was removed**
  (it went from PASS to 3 launches/falls), and both fixed:
  - **A barrier lamp stood 3 cm INSIDE the car wall.** `point_mesh` puts a barrier's centre — and the 3 m
    vehicle-only CAR WALL on its line — `2·walk + BARRIER_THICKNESS/2` outboard of the paved edge, so the wall's
    INBOARD face is at `2·walk`. `barrier_lamp_inset` was a flat 0.15 m from the edge line, which was right only
    for a road with no footway and no car wall; a 0.18 m shaft there spans −0.03…+0.33, i.e. a post 3 cm inside
    the carriageway that the wall does not protect. Measured on DebugRoads' `link` at 35 m/s with the outer wheels
    on the kerb line: **5 pole contacts and the car flipped off the bridge twice**. The offset is now DERIVED —
    `2·walk + poleHalf + barrier_lamp_clear` (0.05) — so the shaft always starts outboard of that face and, on a
    0.32 m parapet, still stands on the barrier. `_barrier_samples` returns the footway width for it.
  - **The "ahead of the motion" test refused a pole the car's FLANK was sliding into.** Scraping a kerb, the pole
    is nearly abeam and the dot product is nearly zero, so the sweep refused it and the physical collider was hit
    instead. It is now asked ONLY of a pole already inside the grown rectangle (one the car has passed, not one it
    has yet to reach): `|localX| <= hw && |localZ| <= hl && dot <= 0`. After both, the gate is back to **0 launches,
    0 falls**, and `link_F1@-3` knocks its 4 poles down cleanly instead of going off the bridge.
- **Gate `tools/godot/probe_breakable_poles.gd`** (18/18, real DebugWorld lamps):
  - 15 m/s: the lamp goes down, and a ray down the shaft then finds nothing (no static box left in the piece).
    The car keeps **79 %** and drives on.
  - 3 m/s: the lamp stands and the car stops 2.11 m short (its bumper).
  - Aged past its respawn with a camera looking at it: it stays down. Camera turned away: back, solid, the
    falling body gone.
  - A frozen car moved kinematically (a puppet) at 15 m/s knocks a lamp down by itself, and its motion is not
    touched.
  - `-- --control` (`breaking_enabled` off) fails 8: the car stops dead 2.0 m short.
  - Probe trap: holding a car's velocity INTO a contact is an infinite force that slides it round a thin pole,
    and a slow car walks 1.5 m sideways on the crossfall over 22 m. The probe re-aims every tick and lets the car
    coast the last metre.
- **Gate `tools/net/run_net_pole_test.sh`** (7/7; `debug/NetPoleTest.tscn`, `NetPoleTestHost`): the host drives a
  driverless car through one pole, the client takes the seat of another through the ordinary seat request and
  drives it through a second pole; each car is a puppet on the other peer. Both poles go down on BOTH peers, the
  side poles 6 m beside each path stand, and **0** world events are sent or received while the cars drive (2 are
  sent at join: the faction baseline). Bollards, bins and trees are the same mechanism, but none is flagged
  breakable yet.

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

**The island's arterials are a Road Kit network in `World.tscn` now** (2026-09-17). Before this,
World.tscn had Terrain3D and NO roads: the 12 arterials existed only in the Blender `Island_base.blend`
bake.
- **Porting.**
  - `IslandRoads.roads.json` (12 roads, 233 stations, 9 junctions) was read out of `Island_base.blend`
    once, with `point_model.read_network` + `save_network` (what `rka.save_record` does). It was not
    re-seeded, so every setback, fillet and pad lift the seeder solved is kept.
  - The `IslandRoads` network node sits at **Y +0.60**, because `island_to_terrain3d.py` moved sea
    level to Y = 0. The median station-vs-terrain difference is 0.00 m.
  - Station `ground_z` was then re-sampled from Terrain3D (`write_roadkit_ground.gd`).
- **Streaming** (superseded 2026-09-18 by the 504 m grid, below). One always-loaded `ZoneMarker` `IslandZone`
  (`zone_id` "island", box 4608 m, load 6000 / unload 9000, `geometry_world_placed` at the network's transform)
  streamed `Roads_IslandRoads_island`. That piece was built with the matching `IslandRoads.zones.json`, so a
  later dock Build produces the same piece name and needs no rewiring. `NAV_HALF=2016` for the navmesh.
  - `ZoneManager`'s approach log now prints only when the distance moves 10 m, because an island-wide
    zone is always "near".
- **Measured.**
  - Validate: 0 errors, 2 `mouth_angle` warnings. Flow: 209 lanes, 0 broken, 0 misjoined, 1 unreached
    (`nishi_dori_1_R0`). The 13 open ends are arterials that really end.
  - `island_v3_reach.py --record` (new flag): **70.8%**, the same as the plan's network.
  - The roads were stamped into World's Terrain3D. `probe_road_stamp.gd -- World.tscn IslandRoads`:
    no ground proud of any lane or pad, stamping again changes 0 vertices, restore is exact, and 590 of
    602 FILL samples are carried.
  - `probe_road_ground.gd -- World.tscn` (now also places a network's resident piece): 2783 of 2833
    PIER samples have a foot on the terrain.
  - World.tscn boots with 0 errors and the zone loads.
- **Two findings from the port, both closed the same day (next section):** the bay bridges stood over a
  −88 m seabed (columns up to 113 m), and the shrine touge rode piers up to 27 m because its switchback was
  fitted to the Python field's slope.

**The seabed is −24 m, the plateau has a 1:3 east face, and the shrine touge climbs in two phases**
(2026-09-17, user decisions). All three are edits to World's Terrain3D data plus the island record, made by
repo tools so they can be re-run and reviewed.
- **Seabed.** `tools/godot/set_world_depths.gd`'s `TERRAIN_FLOOR` is the seabed now: −24 m, where it was a
  −190 m guard. A dredged harbour depth (Tokyo Bay's inner bay averages ~15 m; berths and channels run
  ~15–24 m), and the Python island's own floor. 3.26 M texels raised, from as deep as −138 m. The shelf above
  the floor is untouched. `shape_terrain.gd`'s `HARBOUR_MAX_DEPTH` is 24 to agree.
- **The first mountain's east face** (`tools/island_widen_first_mountain.py`).
  - The shrine plateau (~281 m, centre plan (−1250, 770)) fell east at ~62% on average, and up to 200% on
    the ridges `shape_terrain.gd` laid over it. It now falls at 1:3 from its own measured edge, easing onto
    the 0.6 m city floor. The toe moved ~400 m east, to x ≈ −130.
  - Only the east sector is touched (−35°…0° full, 25° fade), never the sea, and west of a safety line
    before chuo_dori.
  - Ridges are cut only on the plateau's own face. Cutting the massif's foot (north of east) steepened what
    was left: 2989 new >100% cells.
  - It REFUSES a second run. A soft blend is not idempotent, and the check reads the full-strength cells.
    Two defects surfaced through that guard: the face started above the edge threshold it is measured with,
    and the mask used the smoothed edge instead of the raw one. Either way the edit moved its own reference.
  - I/O: `tools/godot/dump_height_grid.gd` / `apply_height_grid.gd` write a float32 grid into a Terrain3D
    data dir; read-back is within 1 mm.
- **Arterials re-routed onto the new toe** (`tools/island_shrine_touge.py`, same uids so links survive).
  - nishi_dori now leaves rinkai_dori at 71°. A first route ran out at 15°, almost along rinkai, and the kit
    correctly solved that shallow crossing to a **102 m** setback. Every centreline sample, and 22 m either
    side, is on ground ≤ 0.48 m.
  - yamate_dori's and nogyo_michi's west ends lost their short first spans.
  - A chuo_dori station 10 m past the chuo × yamate mouth was dropped: that junction now solves 1.5 m wider
    (`station_crowds_mouth`).
  - `roadkit_cli.py setback` re-solved all 9 junctions. It moves every unlocked mouth (W17), so other
    junctions shifted a few metres; rinkai × nishi went 26.5 → 23.8 m.
- **The touge, two phases, both ≤ 10%** (user: watch the driving in two stages).
  - **Phase 1, `shrine_touge`:** from the nishi/nogyo junction, a 40 m level lead-in, then up the widened
    face to a level stop on the plateau. The stop ARCS (45 m radius) round to face the massif, so phase 2 leaves
    straight. Aimed at the plateau centre instead, the hand-off was a 120° bend over a 10 m span, and its inner
    lane had ground 0.17 m proud of it. 2.98 km, 3 hairpins (18 m radius), z 1 → 276 m.
  - **Phase 2, `shrine_touge_2`:** starts ON phase 1's last station (a joint: two coincident points, a
    SEGMENT link). It runs level north along the plateau to the massif's foot, switchbacks up the massif's
    south face, and ends at a stop by the 793 m summit. 5.28 km, 6 hairpins, z 276 → 752 m. The summit end was
    a dead end; since 3.2d it is a turnaround loop (below).
  - Alignments come from `island_v3_terrain.hill_road` on the dumped heights, smoothed (20 m phase 1, 40 m
    phase 2) so the walk does not chase ridge noise. Phase 2 is confined to a south-face band, with "on
    land" asked of the RAW ground 120 m out: the smoothed field blurred the NW sea cliff into 250 m of land.
  - `hill_road`/`switchback` gained `lookahead` (default 0, existing callers unchanged). A walk in a bounded
    band otherwise turns only once its next step leaves the band, and its hairpin is then itself outside and
    ends the road.
  - Profile = `bench_profile`, then fixed stations, then the DOWNWARD cone, then the upward one. Raise-only
    lifted the level lead-in 12 m off its pad (a 21–27% `pad_grade`).
  - The fixed stop stations are counted BACK FROM THE END. Taken as "any station near the arrival point",
    it caught a switchback leg 76 m below the summit and lifted all of phase 2 ~50 m off its mountain.
  - Phase 1's walk grade steps down from 10% until the whole road fits, level lead-in included (it had
    come out 36.7%).
- **The mountain carries its road** (`island_shrine_touge.sculpt`). The kit puts a road more than 4 m over
  its ground on PIERS and the stamp never fills under one, so the ground is shaped to the touge first:
  - within road + verge (14 m) it is the road less 0.10 m;
  - a fill batter (1:1.5) or cut batter (1:1) runs only as wide as the fill or cut at the road's own
    centreline (it daylights), then blends back over 8 m;
  - the sea is never filled; the nearest segment decides.
  - Two wrong versions came first. An unbounded batter "filled" every slope steeper than itself (+633 m
    over a cliff). A batter capped at a height stood 300%+ walls.
  - Result: raised ≤ 63.5 m, lowered ≤ 89 m (rock-cut benches on the ~120% massif face); both roads 0.07–0.15 m
    above the ground on every centreline sample.
- **Measured on the rebuilt island** (pipeline order matters: restore the stamp → sculpt → setback → sample
  the ground → build → stamp; with a stamp record present, sampling reads the OLD sidecar):
  - validate 0 errors (2 `mouth_angle` WARNs, as before); flow 210 lanes, 0 broken, 0 misjoined, 1 unreached
    (`nishi_dori_1_R0`, as before);
  - reach **70.8% → 80.7%** (the massif is served now);
  - `probe_road_stamp -- World.tscn IslandRoads` 6/7: no ground above any lane or pad (highest 0.069 m UNDER a
    lane), idempotent, exact restore. FILL 360/363: the 3 misses are hama_dori's bridge abutments, where the
    lane stands at ~3.9 m, just under `FILL_MAX` (the island had these before);
  - `probe_road_ground -- World.tscn` PASS: 2408/2408 bridge samples have a column foot on the −24 m seabed,
    and both touge phases are all at grade (1494 + 2650 samples, 0 fill, 0 pier);
  - World.tscn boots with 0 errors.
- **Driving it, first build** (`probe_road_launch.gd -- --world=…World.tscn --lane=shrine_touge_F0|shrine_touge_2_F0
  --speed=11`; the probe gained `--world=` and prints each launch's position): phase 1 had 9 launches and a worst
  lateral of 5.8 m, phase 2 had 4 and ran off the summit dead end, and at 15 m/s the car left the road. Fixed in 3.2d:
- **The touge, driven and fixed (PLAN.md 3.2d, 2026-09-17).** Measured first, along the kit's own resampled
  centreline (plan radius over ±6 m, vertical K), which showed that most launches were not where the plan had
  guessed:
  - **Two "grade breaks" were unrounded PLAN corners**: the level lead-in meets the walk at 110° in one station
    (swept at R 18 m), and the walk top meets the plateau ramp at 100° (R **7.7 m**). `fillet` rounds every corner
    nobody drew with a circular arc (40 m, or what the spans leave; sharpest corner served first; collinear
    vertices merged so a straight run counts as one span).
  - **The hairpins were built at 11–14 m, not 18.** `island_v3_terrain.stations` drops the later of two marks
    closer than 10 m, and an even mark landing just before an arc point dropped every other point of the arc
    (chord 9.3 m). `stations(vertices_first=True)` keeps every vertex (default off, so the seeder and
    `bench_depth` are unchanged). The touge's stations are also 20 m apart now, not 70, so the kit can follow a
    vertical curve.
  - **A hairpin arc is not tangent to its own legs.** The walk picks its next heading at the moment it turns,
    so measured 50° into an arc and 32–36° out of it, and Douglas-Peucker had dropped the arc's start point.
    The start is protected, the arc's two boundary points are filleted like any corner, and a vertex that
    cannot be rounded to 18 m is dropped (walk wobble on ridge noise), except beside a hairpin. Result: every
    non-hairpin corner ≥ 23 m, hairpins 12.7–17 m (the worst had been 7.0).
  - **Vertical curves**: `vertical_curves` is the profile's 80 m moving average over arc length. That IS a
    parabolic vertical curve (K = 8 m/% on a 10% break), and it cannot break the grade limit, because the average's
    slope is the average of the slopes. `P2_LEAD` (45 m) keeps the phase joint level through it.
  - **Summit turnaround**: `summit_loop` adds road `shrine_touge_loop`, a level teardrop joined to the stem
    by a 3-arm junction (the kit refuses a 2-arm pad). Its axis and reach are searched (±60°, 70/90/110 m) for
    the flattest summit: straight on, the loop hung 54 m over a slope; chosen −55° / 70 m, ground within 16.6 m.
    A car drives up, round and back down both phases.
  - **The traffic brain had no corner speed.** `CruiseState` cut throttle by a fraction and never braked, so
    uphill at full throttle it held 13 m/s into 18 m hairpins (9.4 m/s² sideways). `VehicleAIController
    .cornerSpeedLimit` is `min over the bends ahead of sqrt(a·R + 2·b·d)`: R is the XZ circumradius of lane
    points 8 m apart, out to the braking distance, re-planned every 0.1 s. `CruiseState` lifts off across
    the first 1 m/s over that limit and brakes past it. `cornerLateralAccel` 4 m/s² (0 = off), `cornerBrakeDecel`
    4 m/s². It is ON for all traffic. `probe_road_launch.gd --corner-accel=` sets it; `GATE_CASES` pass 0, since
    they exist to reach DebugWorld's parapets at 35 m/s.
  - **The generator's input is rebuilt, not stored**: `tools/island_touge_presculpt.sh` (terrain at a389d61,
    seabed clamp, widening) reproduces the pre-sculpt grid byte for byte. Generator + setback on it reproduces the
    record to 0.06 mm. The terrain was swapped as a DELTA over the restored natural ground
    (`nat + sculpt(new) − sculpt(old)`, 115 151 vertices), so nothing else in the window moved. The arterial
    re-route runs only once (`REROUTED_MARK`).
  - **Measured.** At 11 m/s phase 1 goes from 9 launches to **0** (worst rise 2.48 m/s, lateral 1.1 m). Phase 2
    goes from 4 plus the dead end to **0**, driven up, round the loop and down both phases, 14.6 km. At 15 m/s both
    phases have 0.
    Controls on the new road with the governor off: 3 launches at 11 m/s, and 6 plus 5 off-road at 15 m/s.
    Geometry and governor are both needed.
  - Gates: validate 0 errors (3 `mouth_angle` WARNs, one new at a loop mouth); flow 218 lanes, 0 broken/misjoined,
    1 unreached (as before), open ends 13 → 12; reach 80.8%; `probe_road_stamp -- World.tscn IslandRoads` 6/7
    (only the 3 pre-existing hama_dori FILL samples); `probe_road_ground -- World.tscn` PASS; DebugWorld
    `probe_road_stamp` 7/7, launch `GATE_CASES` 0; `probe_traffic_spawn` 6/6, `probe_road_traffic` roadkit and
    debugworld 0 stuck, `probe_dead_driver`, `probe_road_zones` 12/12; World boots with 0 errors; `./gradlew test`.
  - **Probe trap, fixed**: `probe_road_stamp` now also queries LANE samples on the 1 cm grid, the pads' rule. Two
    samples a few mm off an exact terrain vertex read the far vertex, 0.20 m up the 10% grade, which looked like
    "0.09 m proud"; snapped, they are 0.097/0.100 m UNDER the lane.
- **Stamp clearance is 0.10 m** (`road_kit_stamp.gd CLEARANCE`, was 0.05; user: "the road always 0.1 m above
  ground"). `probe_road_stamp.gd` now asserts ground is never above a lane (tolerance 0, was 0.05) and at most
  0.05 m above a pad vertex (was 0.15). DebugWorld re-stamped: 7/7, highest ground 0.078 m UNDER a lane.
- **City ground was already flat** (measured, so no edit): 73% of land under 40 m is exactly 0.60 m, the
  4–16 m bands are flat terraces, and only 0.013 km² of low land deviates more than 0.15 m from its 5×5
  median, nearly all at mountain toes.

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

### Ambient traffic on the island — the zones are DERIVED from the lane entries (2026-09-17, PLAN.md 3.4)

`World.tscn` had exactly one `ZoneMarker` (`IslandZone`, which streams the road piece) and no traffic
at all: cars appeared only through `DebugHarness` F4. What was missing is a set of markers carrying a
`VehicleSpawnConfig` — and **where those go is a fact about the lane graph, not a matter of taste.**
`ZoneManager.placementOn` only ever sets a car down in the first few queue slots of a lane, so every
spawn point in the world is a lane **entry**; on a Road Kit network entries cluster at junctions and
road ends, because that is where lanes begin. So the markers ARE those clusters.

**`tools/island_traffic_zones.py`** derives them from the piece's `.lanekit.json`: 94 spawnable lane
entries → **14 clusters** by single-linkage at 250 m (single linkage, not a greedy "cover the most"
pass, which is order-dependent — a lane reordering in the record would then move markers that nothing
about the road changed). Each cluster becomes a geometry-less `Zone` + `ZoneMarker` whose
`VehicleSpawnConfig.route_name` is the lanes' own `zone_id` (`"island"`), which is
`ZoneManager.spawnLanes`' **zone-id pass** — so a marker offers exactly that network's lanes whose
entry is within its `unload_radius`, with no per-zone route naming to keep in step.

**The radii are measured, not chosen.** `spawnTrafficCar`'s player gate is `unload_radius × 0.9` from
a lane ENTRY, so a player driving mid-arterial sees traffic only if that covers the worst distance
from any point ON a lane to the nearest cluster. The tool measures it (**945 m** over 1852 samples,
on `hama_dori_2`) and **refuses** radii that do not, naming the number that would pass — a quiet
stretch of road is a measurement, not a tuning preference. Shipped: `load 1000`, `unload 1400`
(gate 1260 m), 3 cars per zone; ~2.3 zones loaded at a typical point on the network, 8 gaps in 1852
samples at `load 900` and 0 at 1000.

The generated block is identified by NAME (`Zone_traffic_*`, `VehicleSpawn_traffic`, the
`TrafficZones` node), never by a `;` comment — a comment does not survive the editor re-saving the
scene, and the next run would then duplicate the block instead of replacing it. The tool is
idempotent and takes `--check` for CI.

**Gate: `tools/godot/probe_traffic_spawn.gd -- --world=island`** (the probe gained `--world=`;
`debugworld` is still the default and unchanged). 6/6 over 240 s: 29 cars spawned across 15 lanes,
spawn clearance 10.5 m, worst facing 3°, longest idle 0.1 s, one car drove **2.5 km**. Control —
`World.tscn` without the block — fails 2 (0 cars, 0 lanes).

One rule came out of running it on a big world: **a reclaim past `0.95 × unload_radius` is "left
range" and is exempt from the `MIN_DRIVE_M` check.** The gate exists to catch a car that cannot
drive; on a 1.4 km zone the 0.9 gate legitimately sets a car down with only the last tenth of the
radius ahead of it, so an out-of-range reclaim after 130 m is the design working, not a defect. The
probe reads the reclaim radius off the scene (the widest `unload_radius` among markers that actually
spawn traffic) rather than carrying a per-world constant.

**A TURN PATH'S ZERO-LENGTH LEG MADE FIVE LANES UN-QUERYABLE** (found by that gate). A lead or tail
of 1e-5 m — every corner whose approach leg is the shorter one, so the arc starts at the mouth —
still rounded to `k = 1` in `point_solve.turn_shape`, emitting two samples that distance apart AND a
`break` between them; `point_export.curve_points` then put two **coincident control points** on the
exported `Curve3D`, whose zero-length first baked segment makes `Curve3D.get_closest_offset` return
**NaN**. Nothing in the game asks a lane that question (a car walks its own arc length), which is why
it survived — but every probe that attributes a position to a lane does, and `sample_baked(NaN)`
errors and then measures the wrong lane, silently. Measured on the island: **5 of 218 lanes**, all
turn connectors, first chord 0.0000–0.0001 m. `point_solve.TURN_LEG_MIN` (**0.05 m**) is the floor —
a bound on a LENGTH belongs in metres, never in the parameter it is a fraction of — swept in the
`point_solve.py` self-test across an approach offset so the lead passes *through* zero rather than
being aimed at it, with the old 1e-6 floor as the control. The three lane-scanning probes
(`probe_traffic_spawn`, `probe_road_zones`, `probe_road_traffic`) also **skip** a non-finite offset
rather than guess, because every piece baked before this still carries the duplicates until its next
zoned build.

### The island's roads stream as a 504 m grid (PLAN.md 3.10, 2026-09-18)

Before this the whole island network was ONE zone (`IslandZone`, a 4608 m box) streaming ONE piece. So
every prop type was one island-wide MultiMesh that was never culled or unloaded (2435 drains, 1059 planters,
508 lamps in single draws), and the navmesh needed a world-sized bake at ~2 m cells.
**`tools/island_road_zones.py`** derives the zones instead (the `island_traffic_zones.py` idiom: derived,
idempotent, blocks found by node name, `--check`, both checks in `check_roads.sh`):
- **The grid** is the world square cut 8 x 8 (`island_v3_geom`: 504 m about the origin, the old district
  size). Zone ids are `island_<gx>_<gz>` in GODOT axes (`gx` along +X, `gz` along +Z, so `island_0_0` is the
  north-west cell). A cell becomes a zone only if the cut (`point_zones`, B6, unchanged) hands it something,
  found as a fixed point: a cell that owns nothing is dropped and the cut re-run.
- **The cut is still a RUN cut, so long runs had to be split.** A run goes junction to junction, never
  mid-carriageway, and on the unsplit record the zones reached up to **1.76 km** from their cell centre (the
  touge's phase 2 is one 5 km run). `--split` (an AUTHORED change to the record, review the diff) turns a
  station near each cell boundary into a **joint** with the new
  `point_record_ops.split_at_joint`: the station ends its road, an exact copy starts a new road
  (`<road>__<n>`), and the two are SEGMENT-linked. That is the shape the seeder's corner fillets already
  built, so `wire_joints` hands the lanes over. Rules:
  - **The facing is frozen first.** Both halves take the unsplit chain's facing, MANUAL. A road end takes its
    own last chord as its axis, so on a curve the halves would otherwise cut their sections on different
    planes. The self-test's control (facing left free) moves the lane 1 cm.
  - The joint is the station within one of the boundary with the smallest bend (`--max-bend` 15°), never a
    mouth or a ramp. It is placed only if both pieces stay at least `--min-piece` (300 m) long. That same
    rule makes a second run a no-op.
- **Radii are measured.** `load = max(700, reach + 200)` where `reach` is the farthest station or mouth the
  zone owns from its centre, rounded up to 50 m; `unload = load + 300`. A zone left with a stretch past its
  load radius is refused (`zone_beyond_load`).
- **Measured on the island.**
  - 33 joints → 721 stations in 47 roads, cut into **31 zones**. 27 of them load at ≤ 900 m. The widest
    is `island_0_4` (the touge, 1450 m): its hairpins leave no station a joint may take.
  - Lanes 218 → 318. Connectors are unchanged (124), and every sample of the new lanes lies on an old one
    within 0.1 mm (24 308 samples).
  - Validate is unchanged (0 errors, the same 3 `mouth_angle`). Flow is identical: 0 broken, 0 misjoined,
    the same 12 open ends and 1 unreached lane.
- **Traffic follows a zone-id PREFIX.** `ZoneManager.spawnLanes`' zone-id pass matches `routeName` exactly,
  or, when it ends in `_`, as a prefix (`zoneMatches`). So `route_name = "island_"` is one route over the
  whole network, however it streams. `island_traffic_zones.py` takes every piece lanekit and routes by their
  common prefix. It clusters only lane entries at junctions and road ends: a lane whose only predecessors
  are plain lanes starts at a joint, and counting those scattered 35 markers along the arterials. Coverage is
  still measured over every spawnable lane. 11 traffic zones; the worst lane sample is 933 m from a cluster
  (gate 1260 m).
- **A joint is one road to the terrain stamp too.** The stamp represents each corridor by its NEAREST
  segment. Split into separate corridors, a switchback's other leg started capping the hillside between the
  legs as if it were a second road: re-stamping the split touge changed **6088** vertices.
  `roadkit_cli.py corridors` now joins corridors across every joint (`_join_at_joints`), and that took it
  to 15. Those 15, in one region, are the pre-existing joints now judged as one road; World's terrain was
  re-stamped once for them, and the stamp is idempotent again (0).
- **Navmesh: `NavBaker.clipToContent`** (`build_piece.sh`'s `NAV_FIT=1`). A cut piece sits in the
  NETWORK's frame, wherever its cell is, and its runs can pass the cell edge, so neither the origin box nor
  the cell box fits. The clip is the piece's own mesh AABB + 1 m. Pieces share no geometry, so their
  navmeshes meet only where the asphalt does. Every piece bakes at 0.5 m cells.
- **The dock skips traffic-only markers** (`road_kit_zones.is_traffic_only`: vehicle configs, no geometry,
  no AI). Their 60 m boxes would otherwise be the SMALLEST box around a junction and take its pad.
- **Gate `tools/godot/probe_island_zones.gd`** (World.tscn, the real ZoneManager): the player is set down
  at each of the 31 cell centres in a snake. PASS on all of these:
  - every zone inside its load radius is loaded, and none past its unload radius;
  - every piece sits at the network (Y +0.6);
  - every lane starts where its lanekit says (0.0000 m);
  - a successor dangles only into an unloaded zone;
  - every lane within 150 m of the player is streamed.

  Then a 30 m/s drive along the tour (43 648 frames, headless): p50 1.54 ms, p99 3.05 ms, worst 14.98 ms;
  65 pieces entered, the worst frame in which one finished entering 7.07 ms. `-- --control` (load 150 m)
  fails the coverage check. Also: `probe_traffic_spawn --world=island` 6/6 (24 cars on 11 lanes),
  `probe_road_ground -- World.tscn` 2417/2417 PIER samples with a foot, `RoadGraphTest` / `RoadMapBakeTest`
  on all 31 lanekits (`RoadGraphTest.addIsland`), the road map re-baked, `probe_gps_route --world=island`
  17/17 (a 5.2 km route across the pieces). That probe now picks its goal among lanes the start can REACH:
  with the lanes renamed by the split it had picked the inbound carriageway of the `kitahama_dori` dead end,
  which only the dead end feeds (3.3b's missing turnarounds), and reported "no route".
- **Probe finding, not from this change:** `probe_road_stamp -- World.tscn IslandRoads` reads 329/331
  FILL samples carried, identically on the unsplit record. The misses are `kuko_dori`'s bridge abutment
  (0.99 m over the stamped ground), the class the 3 `hama_dori` misses were before.
- **The Blender half of the Road Kit is deleted** (user: "remove unused old blender plugin"). Removed:
  - `point_ops`, `point_build`, `point_nodes`, `paths`, the addon registration, the four
    `smoketest_point_*` and `legacy_graph/`;
  - `build_island_base.py` (the pre-Terrain3D island bake) and `seed_district_roads.py` (the Blender
    district seeder), their only consumers;
  - `run_smoketests.sh`, and `check_roads.sh`'s Blender section.

  `road_kit_authoring/` is now the pure-python rules and build (its README is the module map). The
  `Island_base` piece files and its Blender check tools are data and history, and were left alone.

---

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
- **`palette.json` owns every library material's look.** `tools/building_kit/build_library_palette.py` writes
  `materials/MI_*.tres` (world-space triplanar, so a foreign mesh needs no UVs) and our generated textures
  (`T_Goods`, two brand-neutral fascia bands); `--check` runs first in `build_buildings.sh`. ambientCG CC0 sets
  are listed in `textures/SOURCES.md`. The toon/anime look the game is heading for (PLAN.md 6.x) will change these
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

## Street trees are ROAD FURNITURE, one species per street (PLAN.md 3.16 step 4, 2026-09-20)

The first half of 3.16 step 4. A 街路樹 is placed by **`point_furniture._street_trees`**, beside the planters,
bollards, drains, signals and lamps — not by a second placer — because "what stands on this footway" is one
question, and it is `Furniture.clear_of` that stops a tree growing through a lamp post.

- **One species per STREET**, chosen by a hash of the ROAD's name (`tree_assets`: `CommonTree_1/3/5` from the
  Stylized Nature kit). A Japanese street is planted with one tree; a per-spot choice reads as scrub.
- **Only on a footway at least `tree_min_footway` (3 m) wide**, which on this island is the trunk/arterial
  network — block streets have 2 m and get none. The trunk stands **AT THE KERB** (`tree_kerb_gap` 0.9 m), the
  Japanese 植樹帯 position and the same side every other prop already keeps to (`planter_kerb_gap` 0.3,
  `lamp_inset` 0.6): so the canopy overhangs the CARRIAGEWAY rather than the lot (the canopies start 2.35–2.58 m
  up, which is the clearance a pruned street tree is kept at), **and the trunk is off the footway's own walk
  line**. That second half is load-bearing and was a measured near-miss: `island_buildings.py` puts the
  sidewalk centreline at half the footway's width from the kerb (2.0 m on the island's 4 m footways), so at the
  1.3 m first tried the trunk's face and a walking body's capsule touched exactly — every promoted pedestrian
  would have rubbed past every tree. At 0.9 there is 0.4 m of clear.
- **The run starts half a tree spacing past where the LAMPS start.** A tree whose station lands on a lamp's is
  simply dropped by the clearance rule, which leaves the avenue with a hole every other tree; offsetting
  interleaves them instead.
- **A footway is a fact about ONE road, so the placer also asks the LANES.** `_LaneIndex` (a 20 m grid over
  every exported lane's plan segments) refuses a spot within that lane's half width plus `tree_lane_clear`
  (0.6 m) — measured on the sample network, a tree on `demo_main`'s footway stood **0.23 m off
  `demo_ramp_b_F0`'s centreline**, because a ramp runs alongside its mainline. A lamp post there is bad; a 9 m
  tree is worse.
- **The collider is the TRUNK** (`collide_pole` 0.35 m x 2.3 m), never the canopy: a box of the piece's
  footprint would stand 4 m across the pavement.
- **A per-asset visibility range was BUILT, MEASURED AND REMOVED, and the measurement is the point.** A tree is
  ~4 k triangles and a piece holds dozens, so a `visibility_range_end` on the batch looks like the obvious lever.
  It is not: **a MultiMesh is ONE instance to the renderer**, so the range is whole-batch, and a range shorter
  than the batch's own extent culls **every instance at any camera distance**. Measured on the island's
  `MM_CommonTree_5` batch (AABB 803.7 m across), camera 12 m from a tree, green pixels in the frame:
  **20285 at no range, 0 at 350 m, 20285 at 700 m, 20285 at 1200 m.** So the only ranges that render are the ones
  that cull nothing. It reads exactly like a bug in the placement — the trees vanish while still casting correct
  leafy shadows, which is how it was found (the picture, not a probe). The lever that WOULD work is cutting a
  piece's trees into several smaller batches; until then the piece's own streaming (700–1450 m) is the bound.
  The plumbing (`furniture.json` `fade`, the glTF `fade_end` extra, the `WorldBaker` branch) is gone rather than
  left unused: a mechanism that does the opposite of what it claims is a trap, not a spare part.
- Measured: **1215 trees on the island**, 44 on `RoadKitSample`, none on DebugRoads (no footway is 3 m there).
- Gate **`blender/tools/check_street_trees.py`** (in `check_roads.sh`, on the island and on the sample), which
  measures the RESULT from the other side of the pipeline — the EXPORTED LANES and the record's authored
  cross-section, never the edge runs the placer read: no tree within half a lane's width of any lane centreline
  plus the trunk's radius, every tree's road authoring a footway at least `tree_min_footway` wide, and no tree
  further from the nearest lane than that lane's half plus the footway plus 2.5 m. `--control` puts the kerb gap
  inside the kerb AND turns the placer's own lane guard off: **109 of 111 trees then stand in a lane**.
  - **Probe trap:** every network's `.lanekit.json` sidecars share `assets/world_source/pieces/`, and another
    world's lanes overlap these coordinates — loading them all reported 13 trees in a lane where one was.
    `--prefix` is the fix.

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

## Road types, the interchange templates, one sea bridge (PLAN.md 3.13 step 1, 3.8 steps 3-4, 2026-09-18)

- **Road types are presets** (`blender/addons/road_kit_authoring/point_presets.py`, the one owner; self-test 9, in
  `check_roads.sh`): `expressway` (2+2, wall median, no footway, barriers, `hammerhead` piers, 80 km/h,
  `taper_factor` 0.5: the world is compressed, a visible authored choice), `trunk` (3+3, raised median, 4 m
  footways, 60), `block` (1+1, 2 m footways, 30), `lane` (1+1, no footway or kerb, a painted 路側帯 edge, 30),
  `farm` (1+1 at 3.5 m, no kerb, 40). `apply_preset` writes the road's fields, its base section and every INHERIT
  station's lane counts; an OVERRIDE station keeps its own section and is reported. `roadkit_cli.py preset <record>
  <road> <type>`; the Godot dock's **Apply Road Type** picker (road or station selected).
- **Two interchange templates** (`tools/roadkit_interchange.py`, `--check` = gate 0 errors + flow 0 broken/misjoined/
  unreached/orphans + every crossing >= 5.5 m surface to surface, measured on the BUILT mesh's upward-facing asphalt;
  both in `check_roads.sh`):
  - `InterchangeTemplate.roads.json`: a DIAMOND, expressway to street (the sketch's dark-blue exits): expressway at
    10 m over a trunk road; keep-left, so eastbound ramps land on a signalised junction north of the overpass,
    westbound south; the expressway split at the overpass. 56 lanes.
  - `LoopJctTemplate.roads.json` (`--kind loop`): an EXPRESSWAY-TO-EXPRESSWAY junction, the Shibaura-JCT shape that
    takes C1 onto the Rainbow Bridge (user): no ground junction; four ramps incl. the 270-degree loop that climbs over
    its own entry (10.4 m) and over C1; the spur to the bridge as two one-way roads side by side climbing to 32 m.
  - Rules they taught, each hit as a gate error first: an exit and an entrance on the SAME carriageway of one run
    share an aux slot (`aux_slot_shared`) -- split the run (`split_at_joint`) or use the other carriageway; two ramps
    on ONE station confuse which carriageway's slot each takes -- one ramp per station; a 2-lane aux lane needs 432 m
    of taper at 80 km/h (hence the preset's 0.5); keep-left decides every merge (a ramp joins from the road's LEFT);
    a JOINT needs coincident end stations AND a tangential approach, or its lanes land beside each other (`broken`).
- **One sea bridge** (user, 3.8): `tools/island_remove_gulf_crossing.py` deleted `hama_dori__2/3/4` (the gulf span;
  the harbour junction is three-arm, setback re-solved); `hama_dori` ends at the inlet's east shore (the future
  military harbour's access). Pipeline re-run: zones 31 -> 29 pieces (stale `island_4_5`, `island_5_5` removed),
  terrain re-stamp (2636 vertices back to natural ground), 12 traffic zones, road map re-baked; reach 80.8% -> 79.0%.
- **The Rainbow Bridge is on the airport crossing** (`tools/island_rainbow_bridge.py`, `--check`): centre and heading
  DERIVED from the record (the two shore stations of `kuko_dori`), `Landmarks/RainbowBridge` in World.tscn at the road
  network's Y, `pillar_skip` on the 8 deck stations inside the span, and an alignment check over the lanekit lanes
  (32 samples, every lane >= 4.5 m inside the corridor, height error 0.00 m). The model's two road levels are
  parameters (`RB_ROAD_LOWER` 24 = the airport road, `RB_ROAD_UPPER` 32 = reserved for the expressway spur from the
  loop JCT); towers and anchorages stand on the seabed (`RB_BASE_Z` -30); `keep_origin` keeps its scene origin at the
  water line. `pillar_skip` holds from its station to the NEXT (`point_solve._bool_field`), so a station skips its
  piers only when the whole span it starts is inside the structure; `probe_road_ground.gd` counts a PIER sample inside
  a `Landmarks/*` building's footprint as carried by it (reported as its own INFO line, 802 on the island).
- **The coast is zoned, and the beaches have a shelf** (`tools/island_coast.py`, PLAN.md 3.8 steps 1-2):
  `island_coast.json` holds the coast types as rectangles (beach, cliff, industrial harbour, gulf, military harbour,
  airport island, fishing port), written from the tool's table. Every coast used to drop from +0.5 m to the -24 m
  seabed within one cell; `shelf` raises only sea cells whose nearest land is BEACH land (in a beach zone and under
  3 m, so cliffs never qualify) to -0.3 m at the waterline -> -3 m 150 m out -> the seabed by 350 m (cosine). Quays
  and cliffs keep their drop. The water shader colours by depth (turquoise + caustics over 12 m), so the shelf reads
  as a lagoon with no shader change. Applied: 391 765 sea cells (1.57 km2).
  - **The shelf never enters a hard zone** (cliff, harbours, gulf), and its target FADES to the -24 m seabed over
    `HARD_FADE` (150 m) approaching any water it does not take, so it adds no underwater wall (steepest step it adds:
    0.50 m per 2 m cell). The result is `max(h, faded target)` and the target depends on the land mask only, so the
    shelf of a shelved grid is itself: `shelf` is idempotent (a fade toward `h` was not -- a second pass raised again).
  - **`check <new> <orig>` asserts three things:** 95.5% of beach water (outside that fade) is under 2.5 m deep,
    0 quay/cliff/harbour/land cells changed, and the added step is at most 1 m per cell. It is not a quay DEPTH test:
    measured, 13% of harbour/gulf water within 20 m of a quay was SHALLOWER than 10 m before any shelf (the inlet's
    sloping ends), so "unchanged" is the rule.
  - **A stamped network's natural-ground sidecar must take the same edit** (`island_coast.py sidecar <orig> <new>`
    re-runs the shelf on the NATURAL ground -- the terrain with the sidecar's values where it covers -- so a stamp-owned
    fill toe in the sea gets the shelf too; then `stamp_roadkit_terrain.gd`), or a re-stamp or restore puts the old
    seabed back under every stamped corridor (the probe measured 191 388 vertices "re-stamped", 23.3 m off on restore). The same holds for ANY terrain edit
    under a stamped network.

## The island's road layout is DERIVED: arterials in, expressway, trunk grid, streets and turnarounds out (PLAN.md 3.13 steps 2-5, 3.3, 3.3b, 2026-09-19)

**Two layers, one command.** `IslandRoads.arterials.roads.json` is the INPUT (the arterials, the touge and the airport
road as seeded and hand-fixed); `IslandRoads.roads.json` is the OUTPUT, made by **`tools/island_layout.py`**: trunk
grid -> streets -> expressway -> turnarounds -> setback, then it asserts the gate (0 errors), a clean flow (0 broken /
misjoined / unreached / orphaned / open ends) and every grade separation >= `roadkit_interchange.CLEARANCE` on the
built surface. A hand edit to the OUTPUT is lost on the next run: edit the input, or the generator that owns the road.
**`tools/island_rebuild.sh [--no-layout]`** runs the whole island after it: ground, zones (`--split`), build
(`NAV_FIT=1 DIRTY_ONLY=1`), a prune of pieces whose zone is gone (every later step globs the lanekits), stamp, traffic
zones, road map. Shared helpers: `tools/island_roadgen.py` (natural ground, filleted plans, a chain road, a station
inserted into a chain, `cut_road` to land a junction on a ground road, `make_junction`, the pier pass).

- **Expressway** (`tools/island_expressway.py`, roads `shuto_*`):
  - **C1**, a rounded rectangle inside the arterial frame (x 150-1300, y 40-720 record frame), deck 11 m, cut into four
    roads at joints (the JCT, both sides, the diamond's overpass) so no run carries two ramps on one aux slot.
  - **The airport JCT** on C1's south side is the loop template (`roadkit_interchange.build_loop`) with three of its four
    movements (the long flyover does not fit a compact ring). The **spur** is two one-way carriageways 8 m off one
    centreline: south, east at y -396, tangent onto the Rainbow Bridge's UPPER deck at the north anchorage (32 m, the
    bridge's `pillar_skip` span), south past it, and down onto the airport. The carriageways PART at the airport: each
    meets the airport road at its own T, because a pad cannot take two parallel one-way arms 16 m apart (the setback
    solver pushed such mouths 145 m out).
  - **A diamond** on C1's north side down to `naka_hondori` (junctions at y 615 inside the ring and 815 outside), its
    four ramps 260-380 m from the overpass, each a single cubic from its gore to its mouth.
  - **3 m sound walls only where C1 is central to the city** (防音壁, `SOUND_WALL`, user): its south half
    (`SOUND_WALL_ROADS`: the JCT road and the south-west road) faces downtown; the north half faces the farmland and
    the mountains and keeps the preset's 1.1 m barrier for the view, as do the ramps, the spur and the bridge. The median wall stays 1.1 m whatever the side barriers are (`MEDIAN_WALL_HEIGHT`).
  - **Every ramp is two lanes** (user: wider for racing): `RAMP_LANES`, and `make_ramp(..., lanes=2)` where a ramp
    merges (the default is ONE lane, and a two-lane ramp into a one-lane slot left its second lane `broken`).
  - Decks are DERIVED: the highest natural ground across the deck + `CLEAR` (11 m), a 4% grade cone. **No pier stands
    on another road**, decided per COLUMN by the build (`point_mesh.pier_on_road`: a column whose footprint is on, or
    within `PIER_ROAD_CLEAR` 3 m of, another road's paved band more than `PIER_ROAD_DZ` 4 m below is dropped; the build
    reports `pier_on_road`). It replaced a station-span pass (`island_roadgen.clear_piers`, retired: it raises) that
    could only switch a whole span off and could not split a taper span, so C1 flew 120 m and `shuto_eb_loop__2`
    250 m over the city with no column -- found by `probe_road_ground.gd`, which had not been run on 3.13. The spur's
    stations inside the Rainbow Bridge take `island_rainbow_bridge`'s own `pillar_skip` rule
    (`island_expressway.bridge_skip`). `taper_factor` 0.25 on every `shuto_*` road (the compressed world; a ring's
    corners leave no 216 m straight), and no station within `MARK_CLEAR` (112 m) of a ramp or joint station.
  - **Not built, and why:** the sketch's OUTER ring closes over the 700 m massif and the touge; the Road Kit has no
    tunnels. The coastal horseshoe that remains is not built either (the lowland is already framed by coastal arterials
    and it needs a second JCT); the E-W link through the city likewise.
- **Trunk grid** (`tools/island_trunk_grid.py`, `trunk` preset 3+3): `nishi_hondori` (x 400), `naka_hondori` (725),
  `higashi_hondori` (1100) from rinkai_dori to nogyo_michi, `ekimae_dori` (y 250) from chuo_dori to hama_dori, and
  `yamate_dori` upgraded. Every crossing a signalised junction; an existing road is CUT for one.
- **Streets** (`tools/island_streets.py`): regions of N-S and E-W lines, each clipped to between its first and last
  crossing, so every street ends on a road. City (block preset, one street down each trunk cell, south of y 560 where
  the diamond ramps come down: they passed 3.1 m over two streets before), the south-west residential lowland (3.3's
  reach gap 2) and the north-east farm grid (farm preset). A line is nudged up to 60 m before it is dropped; a crossing
  of two new lines is kept only where one of them runs THROUGH it (never a two-armed pad); water is judged only once
  the crossings have settled (a partner dropped in the same pass shortens a line).
- **Turnarounds** (`tools/island_turnarounds.py`, 3.3b): every road end that joins nothing becomes a mouth of a 3-arm
  junction with a teardrop loop (the summit loop, generalised), its axis and reach searched for flat land clear of
  every other road; an end with no room is shortened a station at a time. 7 ends, `open_end` 15 -> 0.
- **Measured:** gate 0 errors; flow 1811 lanes, 0 broken / misjoined / unreached / orphans / open ends; 31 grade
  separations, tightest 7.7 m (the airport loop over the westbound exit).

**Five kit defects this surfaced, fixed in the kit:**
- **A T has no straight ahead** (`lane_movements.allowed_turns(available=)`): a middle lane restricted to S led
  nowhere, `broken` at every T with a 3-lane stem (and at the harbour T the gulf removal left, 2 lanes since 3.8). With
  no S on offer the approach splits kerb half -> nearside, median half -> offside.
- **A right turn lands in the median lane** (`target_lane(turn=)`, the road rule; left turns keep the kerb lane).
- **A lane beside a reached lane is reached** (`point_flow.flow_report`): a lane change (`inner_lane`/`outer_lane`)
  reaches it, which is how an aux lane was already entered; a 3-lane trunk off a T is fed into two lanes.
- **Lane-change edges come from EVERY station** (`point_export._adjacency`, widest first): a run with one carriageway's
  aux block at one station and the other's at another has no station holding both, and the lane missing from the widest
  got no edge.
- **A `WALL` median builds its wall** (`point_mesh.median_wall`): `point_solve` had always
  said "RAISED, and a barrier stands on it" and nothing built it -- the expressway's divide was a 0.16 m island. A 0.6 m
  prism, `point_solve.MEDIAN_WALL_HEIGHT` (1.1 m) tall, as its own `<road>_median-road-noped-colonly` COLLIDER; what is
  SEEN is the kit's median panel (user: Quaternius' `TrafficHighwayMidWall`, fitted to 1.1 m by `build_zombie_yard.py`)
  tiled end to end by its own length (`point_furniture._median_walls`, furniture asset `median_wall`; 1028 panels on
  the template's 1.6 km). A fence panel is no collider to scrape at speed, a continuous prism is.
`point_digest` now salts `lib/lane_movements.py` too (it decides every connector).

**Lamps on barriers** (`point_furniture._lamps`, user): where an edge carries a barrier (a deck, a ramp, a bridge
parapet) the kerb lamp is skipped, so an expressway was unlit; now a single `lamp` (the base StreetLight, 10 m
luminaire) stands ON the barrier every `barrier_lamp_spacing` (45 m), staggered. A WALL median takes the median lamp
(`lamp_twin` slot, on the wall's top at `MEDIAN_WALL_HEIGHT`) when that asset exists (`median_wall_lamp_min_half`
0.45); remove the slot (the user is replacing the twin with a simpler Japanese lamp) and the barrier lamps light the
expressway from the sides.

**Sites** (`tools/island_sites.py`, 3.8 steps 5 and 8), each STREAMED as a `SiteZones/<Name>` ZoneMarker whose Zone
places the building scene in world space (`geometry_world_placed`; the dock's road cut skips a zone streaming a
building, `road_kit_zones.is_traffic_only`):
- `ContainerTerminal` (composite, `tools/building_kit/site_container_terminal.py`): 364 x 218 m on `Harbour_Apron`
  slabs, four ship-to-shore cranes (30.48 m gauge, booms raised to 88 deg so nothing overhangs the quay), bollards,
  light masts, ~800 stacked containers; its front laid on the industrial harbour's east quay, a line least-squares
  fitted through 33 edge samples of the natural ground (worst 2.5 m off). 624 k vertices merged, so it streams (900 m).
- `ShuriCastle` (`library_landmarks.shuri_castle`): the Seiden (29 x 17 m, red lacquer, two red-tile roof tiers, a
  karahafu, gold dragon pillars) on a striped Una with the Hokuden, Nanden and Houshinmon, all on a 25 m Ryukyu-limestone
  platform the hill slopes into. Sited by search: a ~140 m patch at 3-27 m, no road within 85 m, the massif behind:
  (-580, -40), facing downtown.
- **The yard pieces are Quaternius'** (Zombie Apocalypse kit, CC0, credited): `blender/tools/build_zombie_yard.py`
  writes containers fitted to ISO 668 (the 40 ft box is the 20 ft model stretched; decimated to 25% of its faces --
  ~800 in one terminal were 1.3 M vertices), pallet, drum, cone, plastic barrier and tyre stack into
  `kits/quaternius_zombie_apocalypse/pieces/yard/` + its `pieces.json`, so a composite names
  `quaternius_zombie_apocalypse:<Piece>`. **A third-party kit stays its own folder** (the licence and credit
  boundary); the `.blend` files the tools build from are copied into its `blends/`, and the download (`source/`) is
  deleted (2026-09-19). New library pieces: `Harbour_Crane/Bollard/Fender/LightMast/Apron`, `ShuriCastle`; palette `MI_CraneRed`,
  `MI_LacquerRed`, `MI_RoofTileRed`, `MI_Limestone`.

- **The crane's collider is BOXES, not its hull** (user: a character or car must pass under a crane). A composite prop
  may say `collide: {"boxes": [[cx, cy, cz, sx, sy, sz], ...]}` in its own frame (`layout_buildings.place_props`), and
  `site_container_terminal.CRANE_BOXES` / `MAST_BOXES` are the bogies, legs, sill and side beams and girders. A
  composite also carries `clear_probes` (points that must stay open), and `probe_buildings.gd` fits the character's
  capsule at each: one under every crane's portal. Control: the crane back on its bounding box fails all four.
- **Generated pieces are safe to hand-edit** (`blender/tools/build_library.py`): each procedural or landmark piece
  stores a fingerprint of its mesh and materials (`lib_generated`), and `--procedural` KEEPS a piece whose fingerprint
  no longer matches ("KEPT Harbour_Bollard"); only `--force` / `--only=<Name>` regenerate. Every piece carries an
  `edit_note` (what else assumes something about it), and the `.blend` a `README_artist` text from
  `kits/library/ARTIST_NOTES.md`; the Zombie kit's owner blends have `kits/quaternius_zombie_apocalypse/blends/README.md`.

**Headless streaming loads synchronously** (`ZoneManager.threadedLoadMode`, `-1` = auto). Under `--headless` the dummy
renderer's mesh storage is not safe against meshes created on the loader thread while the main thread creates others:
it logs "Attempting to initialize the wrong RID" / `mesh_add_surface: Parameter "m" is null`, then segfaults, and the
island's larger pieces made two loads overlap often enough to crash `probe_island_zones.gd` most runs. Auto = threaded
unless `DisplayServer.getName()` is `headless`; a real renderer queues cross-thread calls. `warmDependencies` loads a
piece's non-scene dependencies on the main thread first (not enough alone: 1 of 3 runs still crashed). `ZM_TRACE=1`
prints every streaming step. Cost, headless only: the worst frame of the island drive is 134 ms (a whole piece parsed
in one frame); p99 5.6 ms.

## Every grade break is rounded, and what is left is named (PLAN.md 0.7, 2026-09-20)

**A car at speed was thrown into the air on roads with no hole and no bad collider.** Measured, ruled out
first: not a hole (80 m sectioned, continuous), not the physics rate (same at 60 and 120 Hz), not the wheel
sensor (same with rays, sphere and tyre cylinder). What was left is a **GRADE BREAK** — a profile is built span
by span (`bench_profile`, a grade cone, a deck's `CLEAR` over the ground) and **every one of those holds a LIMIT
per span and says nothing about the CHANGE from one span to the next**, so a road can meet its 5 % limit at
every station and still step from −3.13 % to +3.12 % across one of them. At 45 m/s a 6 % break hands the wheels
~2.8 m/s of vertical velocity in one tick and the suspension throws the car.

**`tools/island_grades.py` is the one owner of that change**, and it is 3.2d's rule (`vertical_curves`, built
for the touge) applied to every road instead of one: `smooth` replaces each profile with its own **moving
average over `LENGTH` (80 m) of arc length**, which IS a vertical curve (K = 8 m/% on a 10 % break) and — because
the derivative of an average is the average of the derivative — **can never make a span steeper than the
steepest it was built from**, so it is safe to run over a whole network with no per-road re-check. `rank` is the
measurement, over the BUILT lanekits rather than the record, because what a car drives is the exported Path3D.
It is step 6 of `island_layout.py`, after the setback solve.

**What is HELD, each for a measured reason:** a junction mouth (a pad is solved FROM its mouths); a ramp mouth
**and the station after it** (that span is the gore, where the ramp and the carriageway still share paving —
dropping the far station tilts it, which is a past defect, not a worry); every station of a `pillar_skip` deck
**and the one either side** (the deck is fitted to a structure — the Rainbow Bridge's road is gated to 0.5 m over
its span — and the span boundary falls BETWEEN two stations); and the first and last station of every CORRIDOR,
where a corridor joins roads across a `split_at_joint` JOINT and smooths them as ONE profile, exactly as the
terrain stamp already joins them.

**A held station is a BOUNDARY, not a pin.** Each stretch between two anchors is averaged separately, extended
past its own ends by its end SLOPE, so a stretch that is straight where it meets an anchor comes back untouched
there. Averaging the whole corridor and pinning the anchors afterwards is what does NOT work: it took a diamond
ramp's 6.15 % break to 6.40 %, because the station 36 m past the anchor moved and the anchor did not.

**Measured on the island**, rebuilt end to end (`tools/island_rebuild.sh`: record → ground → zones → pieces →
stamp → traffic → map), 299 stations moved in 164 corridors, biggest move 0.70 m:

| grade breaks over | 2 % | 3 % | 4 % | 6 % | worst |
|---|---|---|---|---|---|
| before | 508 | 202 | 39 | 3 | **6.25 %** (`kaigan_dori__8`, a −3.13 → +3.12 sag) |
| after | **114** | **34** | **8** | **0** | **4.68 %** (`shuto_d_bwd_on`, a ramp CREST) |

over the same 49 970 through-lane samples. The gate, flow and crossing asserts are unchanged by it (0 errors,
0 broken/misjoined/unreached/orphans/open ends, 31 crossings, tightest 7.7 m).

**A vertical curve needs stations to be followed**, so `smooth` NAMES every break it could not take below 3 %
rather than passing silently — 17 roads before, **7** after, and all 7 are span-limited (their spans are longer
than the curve): the two bridge approaches, the four diamond ramp crests and the spur's deck approach. Those
want stations or a re-graded alignment, not a different constant; densifying the diamond ramps was tried and
bought 0.06 pp.

**Re-driven at 45 m/s with the corner governor off** (`probe_road_launch.gd`, a player's speed, not traffic's),
9.9 km over six cases, **every remaining launch is attributable and none of them is a grade break**:

| case | launches | worst rise | what produced it |
|---|---|---|---|
| `kaigan_dori_R1` | **0** | 0.84 m/s | — (the road that held the 6.25 % worst break) |
| `shuto_d_bwd_on_R1` | **0** | 2.98 m/s | — (the worst break LEFT, 4.68 %: a crest unloads, it does not throw) |
| `shuto_d_fwd_on_R1` | **0** | 2.88 m/s | — |
| `kaigan_dori__8_R1` | 1 | 7.05 m/s | **an ambient car** (`Characters/PIT1`) at 47 → 24 m/s |
| `kuko_dori__2_F1` | 2 | 11.39 m/s | ran 25 m wide onto the footway and the car wall; one at the bridge approach |
| `kuko_dori__3_F1` | 2 | 4.00 m/s | ran 25 m wide |

**Cause 1 is the probe's own brain, and it is now provable rather than inferred.** `LaneDriveProbeController` is
deliberately blind to other cars so a launch run is not spoiled by traffic, which means it rear-ends them at
45 m/s; `probe_road_launch.gd --see-obstacles=1` gives it the shipped sensing back. Same lane, same speed:
**1 launch at 7.05 m/s blind → 0 launches, worst rise 0.57 m/s** over 1793 m.

**What is genuinely left is the Rainbow Bridge approach**, and `island_grades` named it before the drive did.
`kuko_dori` climbs +0.89 → +3.10 → +7.62 → +8.00 % and then steps **+8.00 % → 0.00 % in one station** at the
first `pillar_skip` (deck) station, with the mirror step at the far end (0.00 → −8.00 %) easing to −6.16 % and
then **−6.16 → −0.79 % across an 88.9 m span** — the sag that threw the car at (1711, 10, 1543), 0.93 m from the
lane centre, not running wide. The deck may not tilt and its approach stations are 64–139 m apart, so the 80 m
curve has nowhere to work: that approach needs stations (or a re-grade), which is authored geometry.

## The north-west coast road: a bench cut into the cliff, with rock sheds (PLAN.md 3.15, 2026-09-19)

`kaigan_dori` closes the sketch's outer ring where the expressway cannot go: 4.0 km round the massif's north-west
cliffs, from `kitahama_dori__3`'s end (a JOINT: the coast road continues it westward) to a new T at the
`nishihama_dori__2` / `rinkai_dori` corner (the corner's fillet dropped; nishihama -> coast road is the through road).
**User decisions:** a shelf CUT INTO THE CLIFF FOOT, never a viaduct or fill in the sea (the island stays compact);
2 + 2 lanes; rock sheds (洞門 / ロックシェッド) first, one true tunnel later.

- **The alignment is derived once, then authored** (`tools/island_coast_road.py derive <dump>`, the touge's shape):
  from a Terrain3D height dump (`dump_height_grid.gd -- <out> -2304 -2304 1153 1153 4`) it walks the coast with the sea
  on its left, `D_TARGET` 17 m inland of the water line (paved half 10 + the stamp's 6 m verge = the flat ends at the
  cliff edge, the sea in view past the barrier), smooths, pushes back inland anything under `D_MIN` (a chord across a
  cove cuts toward the water), and resamples at 30 m. Height: no higher than the ground at the band's SEA-side edge
  (+0.3, at least `Z_MIN` 1 m, at most `Z_BENCH` 12 m) nor the ground under the centreline, lowered by a 5% cone, so the
  road only ever CUTS. The first version held a 12 m bench everywhere, and the pictures (`tools/godot/shot_coast_road.gd`,
  needs a display) showed why that is wrong here: this coast has a strip of sand at the cliff foot the whole way round,
  so the road stood on a vertical rock wall 12 m over the beach (the stamp does not fill a cut deeper than `CUT_MAX`, and
  filling it would push an embankment into the sea). It now runs at 1-3 m on the flat strip with the cliff cut beside it. Written to `assets/world_source/pieces/IslandCoastRoad.json` (stations with
  z, shed spans), reviewed like the record. `add` puts it into a record, terrain-free; `island_layout.py` runs it first.
  Measured: 4012 m, nearest the water 12.5 m (the paved edge stays on land), steepest 5.0%, four 300 m sheds.
- **`coast` road type** (`point_presets`, and the dock's picker): 2 + 2 at 4.5 m, a painted median, 0.75 m shoulders, no
  footway, barriers both sides (`ped_access` off), 60 km/h, `cut_batter` 10.
- **`RoadData.cut_batter`** (new road field): the UPHILL side's cut face in metres of rise per metre across; 0 = the
  stamp's ordinary 1:1 batter. A 1:1 face on a 150 m cliff would slice 150 m back into the mountain. Which side is
  uphill is DERIVED per corridor point (`roadkit_cli._steep_side`: the natural ground `STEEP_PROBE` 16 m past each paved
  edge) and handed to the stamp as a 7th corridor-point value, signed in GODOT axes (the kit's sign flipped: Godot z is
  -kit y); `road_kit_stamp.height_at` uses it on that side only.
- **`PointData.shed`** (new station enum, append-only: `NONE`/`OPEN_LEFT`/`OPEN_RIGHT`, which side is open against the
  chain direction), held to the next station like `pillar_skip`, solved into `rka_shed`. `point_mesh.sheds` builds per
  span: a roof slab whose soffit is `point_solve.SHED_CLEAR` (5.5 m) over the road, `SHED_ROOF` (1 m) thick, from past
  the open-side columns to `SHED_BACK` (5 m) past the closed-side wall -- over the stamp's flat verge to the cut face, so
  no daylight shows between roof and rock; the wall against the rock; a 0.8 m column every `SHED_COL_SPACING` (8 m) on
  the open side; two rows of lamp panels under the soffit in `M_TunnelLamp` (sodium orange, emissive,
  `road_kit/materials/M_TunnelLamp.tres`, applied by name at bake). The concrete is also its own
  `<road>_shed-road-noped-colonly` collider.
- **A bench road fills over LAND only** (corridor kind `BENCH`, `road_kit_stamp.LAND_ONLY`): the CLI reports every
  point of a `cut_batter` road as `BENCH` (a centreline cut deeper than `CUT_MAX` would otherwise be `TUNNEL`, which
  never fills, and the road's sea half stood 1-2 m over the sand on its own side face), and the stamp fills such a
  point only where the natural ground is at or above the water line (`LAND_Z`). Measured on a terrain diff against a
  dump taken before the road: the first stamp raised 67 sea cells by up to 28 m where the flat verge overhangs a cove;
  with `BENCH`, 0 on the coast.
- **A turnaround's verge must be on land too** (`island_turnarounds.SHORE`, 13 m round every probe point): the same
  diff found `futo_dori_loop` (3.3b) on the quay with its verge over the harbour, 175 cells filled up to 28 m.
  `futo_dori_loop` and `rinkai_dori_loop` moved.
- Self-tests: `point_mesh.py` (the shed: soffit, columns on the open side, wall + roof to the rock, mirrored),
  `point_presets.py` (coast passes the gate), `tools/godot/test_roadkit_stamp_rules.gd` (the steep face on the named side
  only, and the control with none; in `check_roads.sh`).

**A traffic car can run off the edge of the streamed road, and that has its own reclaim reason** (`stream-edge`). Since
3.10 road pieces stream at 700-1450 m while traffic spawns up to 0.9 x 1550 m from a player, so a car heading away can
reach a lane whose named successors are in a piece that is not loaded; `advanceToNextRoute` finds none and the car is
`isFinished`, which read exactly like a dead end in the network. `VehicleAIController.finishedAtStreamEdge()` marks it
(the lane NAMES successors and none resolve), `ZoneManager.cullFinishedVehicles` logs and records the reason
(`reclaimReasonOf(instanceId)`, registered, the last 256), and `probe_traffic_spawn.gd` exempts only that reason, as it
already exempted leaving range. Measured before: a car set down 640 m from the player vanished after 82 m at 720 m,
just past a road piece's 700 m load radius.

**`LaneGraph` follows the lanes that are streamed** (found driving the coast road, 2026-09-19). Its proximity graph was
built ONCE per scene by a scene-tree walk, so after 3.10's zone streaming it held freed lanes as successors (1086
"Cannot call a method on a previously freed instance" in one 4 km drive) and never saw a piece that streamed in later.
`LaneGraph.invalidate()` is called by `ZoneManager.registerRoute` / `unregisterRoute`, the graph is rebuilt lazily from
the registry (`ZoneManager.registeredLanes()`, never a tree walk; the walk remains only for a scene with no ZoneManager),
and a car whose own lane was freed under it (its piece unloaded) finishes as `stream-edge` instead of querying it
(`VehicleAIController.gatherInput` / `advanceToNextRoute`). Measured after: 0 freed-instance calls over the same drive.

**A barrier has an invisible CAR WALL behind it** (2026-09-19; the user's "ramp walls' collision is not right at speed").
Measured on the diamond's exit ramp (`probe_road_launch.gd -- --lane=shuto_d_fwd_off_F1 --offset=-2`, 25 m/s): a car
pressed into the 1.15 m parapet caught the wall's TOP edge with its hull and was thrown up it -- 4 launches, 7.7 m/s of
rise, contacts on the barrier's top face. The parapet is a proper closed 0.32 m prism; a wall that low simply has an
edge to climb. `point_mesh._edge_run` now adds, wherever a barrier stands (road flanks, junction corners, gore noses),
a collision-only wall on the barrier's line `CAR_WALL_HEIGHT` (3 m) tall, as a `<edge>_carwall-carwall-noped-colonly`
proxy. `WorldBaker.applyCarWalls` puts those bodies on `CollisionLayers.CAR_WALL` (layer 6, 32) with mask 0, and only
`Vehicle.tscn` and `Motorcycle.tscn` bodies have it in their mask (19 -> 51): bullets, characters, wheel rays and the
navmesh never see it. `point_mesh.py` self-test asserts the wall's line and height, and none without a barrier.

**The natural-ground sidecar is kept only where a stamp reached** (`road_kit_ground.stamp_reach` / `natural_height`,
2026-09-19). Once a network is stamped, re-sampling its ground took the old sidecar as the natural ground wherever the
sidecar covered, i.e. over the whole footprint + 60 m -- so a terrain edit made after the first stamp (the harbour
dredged to -24 m) never reached it, and the spur's portal columns stretched to the old seabed stood 3.3 m above the new
one (`probe_road_ground.gd`). Now the old value is kept only where the previous stamp's corridors reach
(`road_kit_stamp.height_at` over the recorded corridors is not NaN); everywhere else the terrain was never stamped and is
sampled. The documented rule still holds for the corridors themselves: re-sculpt under a road only after Restore.

**Probe notes.** `probe_road_stamp.gd`'s support-kind lookup is a 32 m bucket index (it scanned every corridor point
per lane sample: 58 k x 70 k on the island, past 50 minutes; DebugWorld now 7 s). `probe_road_ground.gd` counts a PIER
sample on a span over another road (a lane more than 4 m below within `SPAN_REACH` 60 m) as carried and reports it,
skips the hanging-column check inside a landmark's footprint and where a cell's lowest vertex is a deck SOFFIT (a
lane 0-3 m above it within 8 m): two stacked decks -- the Rainbow Bridge's, a JCT loop over its exit -- read as a column,
and prints its phase timings. **Do not pass `--fixed-fps` to the static probes** (`probe_road_ground`,
`probe_road_stamp`, `probe_gps_route`): under it `probe_road_ground` on World.tscn ran 50 minutes to its timeout, and
about a minute without it.

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

## Night is lit: a moon, street lamps and headlights (user, 2026-09-20)

User-reported: "night time is barely able to see in game". Measured, and the cause was not a setting to tune —
**there was not one `OmniLight3D` or `SpotLight3D` in the whole project**, `MoonLight.light_energy` was 0, and the
lamps and signals placed by `point_furniture` were props with no light. A clear night was lit by sky ambient
alone. Also `TimeOfDay.minutes_per_day` was the Sky3D default **15**, so a whole day passed every 15 real minutes
(GTA V uses 48; it is 48 here now).

- **"How dark is it" has ONE owner: `world.DayNight`** (AutoLoad). It is **measured off the key light, not read
  off a clock**: Sky3D's clock can be driven by a system time, a scripted beat or an editor scrub, and its own
  `sun_altitude` is stored in a frame this code would have to guess at, while the one thing always true is where
  the sun light points. A `DirectionalLight3D` shines along its own −Z, so the elevation is `asin(-forward.y)`,
  and `nightFactor` ramps 0 → 1 between `dayElevation` (+2°) and `nightElevation` (−8°, the end of civil
  twilight) — so dusk fades the lamps up instead of switching them. The sun is found by the group
  **`sun_light`** (both world scenes put Sky3D's `SunLight` in it), else the brightest directional light. With no
  directional light at all — a bare probe stand — `nightFactor` is 0 and every consumer behaves as before.
- **`world.StreetLights` (AutoLoad) is a POOL that follows the camera.** The island stands **1 962 poles**; they
  are MultiMesh instances precisely so a district costs one draw call, and a light per instance would undo that
  and light half the island. So the nearest standing lamp HEADS within `radius` (75 m) get one of `maxLights`
  (24) shadowless omni lights, re-assigned every 0.25 s. A lamp beyond the pool still reads, because its glass
  (`MI_LampGlass`) is emissive, which costs nothing; what the pool adds is the pool of light on the road.
  **A knocked-down lamp is dark** — `BreakableProps` already knows which poles are lying down (3.11), so the pool
  skips them and there is no second record of what is broken.
  Where the bulb is comes from the PIECE and is MEASURED (`StreetLights.HEAD_OFFSETS`): `StreetLight_JP`'s
  luminaire mesh spans y 10.00–10.15, z −2.69…−2.08, so its bulb is (0, 10.07, −2.39); the twin's two heads are
  (±2.39, 10.07, 0). They are a table in Java rather than in `furniture.json` for one reason: the piece data
  reaches the game through a BAKE, so putting them there would rebuild all 52 road pieces to move a light 10 cm.
- **Headlights are built in code from the config's measured lamp offsets** (`Vehicle.refreshLights`), so every
  carrier gets them and a new car needs no scene edit: two low-beam `SpotLight3D` and two red tail `OmniLight3D`,
  **no shadows** (one shadow map per lamp per frame, on a street holding a dozen cars, to light the car's own
  shadow in its own beam), built on first need and shown only when `DayNight` says it is dark AND the car is
  within `LIGHT_VIEW_DISTANCE` (140 m) of the camera. The offsets are DERIVED by
  `tools/build_vehicle_scenes.py` from the model's measured bounds — the front/rear face, `LAMP_OUT` (0.62) of
  the way out to the flank, `LAMP_UP` (0.42) of the body's height — never hand-placed.
- **The moon is Sky3D's, and the scene line for it is a trap.** `SkyDome._update_moon_light_energy` writes
  `MoonLight.light_energy` every frame from its own `moon_light_energy` × the moon's altitude, so a value set on
  the light node never wins — the same trap `SkyDome.ground_color` already cost us (the horizon band). The moon
  is turned up at its real owner (`SkyDome.moon_light_energy` 0.6) and `TimeOfDay.celestials_calculations` is
  **SIMPLE**, which puts the moon opposite the sun — a full moon every night, instead of wherever the real
  ephemeris happens to put it. That is what makes open ground away from a road readable at all.
- Gate **`tools/godot/probe_night_lights.gd`** (18/18; `-- --control` turns the pool off and clears the shared
  `SPC1Config`'s lamp offsets, and fails exactly 6): noon reads day and midnight night off the sun light
  (elevation +87.0° / −85.5°); beside a lamp 5 heads are lit, the nearest 11.2 m away, its light exactly
  10.07 m above the pole's base; a camera 400 m from every lamp lights none; a car driven into a lamp puts its
  light out with it; a car 4 m from the camera has its headlights on at night and off by day; and the moon casts
  0.598 at midnight. Pictures: `tools/godot/shot_night.gd` (needs a display) saves a frame per hour with each
  one's **mean luminance**, which is the number the complaint is about.
- **Probe trap:** the Player's TPS rig keeps writing the current camera even with the Player's `process_mode`
  DISABLED, so "move the current camera" silently moved nothing and every lamp reading was of somewhere else
  (the camera stayed 150 m from where the probe asked). A probe that needs a viewpoint owns its own `Camera3D`.

## The minimap turns with you, and the route is drawn on the road (user, 2026-09-20)

Two asks, one answer each.

- **Heading-up minimap.** `MinimapController.rotateWithHeading` (`@Export`, on) turns the map so the way the
  player is FACING is up, with the arrow FIXED pointing up — GTA's radar, and what makes "the line goes left, so
  turn left" readable without reading a compass first. The **full map stays north-up**: a paper map you are
  reading is a different job from a radar you are steering by. It is one angle, applied in one place:
  `RoadOverlay.project` is now the single world→screen mapping for the blips, the route AND the baked road
  picture, so they cannot come to disagree about which way the map faces. The picture's polygon does not move —
  its **UVs** do, carrying the INVERSE rotation, because a UV is the inverse of that mapping.
- **The route on the tarmac.** `world.RouteRibbon` (AutoLoad) draws the GPS route as a band on the road ahead.
  GTA IV/V draw one (San Andreas only drew it on the radar), and here it is nearly free because the hard part
  exists: `RoadMap.routeFor` already returns the route as lane samples **in 3D** and re-routes at most once a
  second, so the band is one `ImmediateMesh` rebuilt only when the route or 5 m of progress has changed — one
  draw call of a few hundred triangles, never a per-frame search. It takes **the lane's own Y** (`Route.points`
  is {x, y, z} triples), so it rides a bridge deck correctly; a ray down from above would have found whatever
  deck is overhead, which on this island is a real case. It is DERIVED, never latched: it shows what the routing
  already says and goes with the waypoint. Nothing is saved or sent — a teammate's waypoint is drawn on the MAP,
  but each peer routes for itself.
- Gate: `tools/godot/probe_gps_route.gd` (now 22/22 on DebugWorld). Heading-up is asserted **by measurement**,
  not by reading the angle back: a point 20 m dead ahead must land straight up on the radar at three different
  headings, and with `rotate_with_heading` off NORTH must land up instead. The band draws 97 quads over the
  route and the control knob removes it.

## A car stops for a person in the road (user, 2026-09-20)

Reported as "the AI driver will not stop in front of player/character to block". It was never that the car could
not see people — the scene's `ObstacleRay` mask is **18** (CHARACTER | VEHICLE) — it was that the ray reached a
fixed **7 m**, which is 0.3 s at 22 m/s where stopping takes 40–60 m, and was a single line down the centreline,
so anyone not dead ahead was invisible. Both halves are fixed in `VehicleAIController`:

- **The look-ahead is the STOPPING DISTANCE**, `v²/(2·obstacleBrakeDecel) + v·0.4`, clamped to
  `obstacleLookMin`/`obstacleLookMax` (7–30 m).
- **It is three rays, not one**: the two flanking rays sit at the car's own hull half-width, built in code so
  every carrier gets them, and they take the scene ray's own mask — what counts as an obstacle still has one
  owner.
- **They are aimed ALONG THE LANE**, at `route.pointAtLength(progress + look)` — the same point the steering
  already follows. Aiming straight ahead is what a 7 m ray could afford; a 30 m one cannot, because on any bend
  it leaves the carriageway and the thing it then finds is the ONCOMING traffic, i.e. a car that brakes for
  every vehicle across a curve.
- Gate **`tools/godot/probe_ai_stops.gd`**: a person on the lane centre and a person at the edge of the car's
  own width both stop it short, and a clear lane is driven without braking (so the fix is not "always brake");
  `-- --control` puts the fixed 7 m single ray back. `probe_traffic_spawn.gd` still passes with 0 idle, which is
  the check that the longer look did not gridlock traffic.

## Sliding shop doors, and the cars' top speed (user, 2026-09-20)

- **A Japanese store, office, terminal or konbini has a sliding automatic entrance (自動ドア), not a swing door.**
  Nothing new was needed in `world.Door` — `openMode = "SLIDE"` and `slideOffset` have been there since I2; what
  was missing is that the type table never said which buildings have one. `building_types.json` gains
  **`door_style`** (`"slide"` on Konbini, ShopHouse, PencilBuilding, OfficeMid, GasKiosk, StationBuilding,
  FamilyRestaurant, TokyoStation and AirportTerminal; `"swing"` — the default — on houses and flats, whose
  玄関ドア is hinged), `layout_buildings.py` carries it into the layout, and `build_building_scenes.gd` builds
  **two leaves parting from the middle** on an opening 1.6 m or wider and a single 片引き戸 below that. Each leaf
  is its own `Door` with its own sensor covering the WHOLE doorway, so both open together. `slideOffset` is in
  the door's PARENT frame (Door adds it to its own position), so the direction is the opening's own ±X.
- **A SHOP ENTRANCE IS THE WHOLE MODULE, GLAZED, AND ITS DOOR IS TWO PANELS OF GLASS** (user, 2026-09-20:
  "two door panel, and open on both side … should use glass material, but full glass similar to japan
  konbini/store"). What shipped first was a single opaque leaf, because the entrance was the kit's
  `DoorFrame_Metal_Single`, whose hole is **0.91 × 2.00 m** inside a 1.82 m wall module — a single-leaf doorway,
  under the two-leaf threshold. A Japanese 自動ドア is not a door punched in a wall: the module is glass, and the
  leaves slide behind the fixed sidelights beside them. So:
  - `layout_buildings.py` gives a `door_style: slide` type's entrance **no kit wall piece at all** and an opening
    of `SLIDE_OPENING_W` × `SLIDE_OPENING_H` = **1.70 × 2.10 m** (two 0.85 m leaves, 6 cm of mullion each side of
    a 1.82 m module), and the collision split leaves exactly that gap. The door meta carries `shopfront`
    (the module width and the storey height), so the builder need not re-derive the type's style.
  - `build_building_scenes.gd` glazes the rest of the module — a header pane from the door head to the storey
    top, a mullion each side, and the head rail the leaves hang from (`_shopfront_glazing`) — into the merged
    mesh of **both** variants, because fixed glazing is not a door. Each leaf is `_glass_leaf_mesh`: a pane of
    `MI_GlassClear` in a slim `MI_PaintedMetal` frame (`FRAME_T` 4 cm), built at the kit leaf's own convention
    (it spans its node's local −X and stands on y = 0), so a Door node needs no offset and the collider, the
    slide offset and the sensor are unchanged.
  - **`_panels` is the one owner of "how many leaves"**, asked by the shut mesh and by the Door nodes alike, so
    the two cannot disagree about what the door is.
  - **Two leaves that meet exactly at the doorway centre share a face, and a ray straight down that seam passes
    between them** — measured, by the probe's own shut-door ray, which is also what a bullet would do. A real
    pair overlaps at the meeting stile, so each leaf's COLLIDER is `LEAF_MEET` (2 cm) wider each way; the pane is
    not, so nothing changes to look at.
  - Assumed, and one line to change if wrong: 1.70 m of opening, a 2.10 m head, a 4 cm frame. The reference
    photographs (`/data/danilko/references/japan/`) are a general travel set, not shopfront studies, so these are
    the standard proportions rather than measurements off a picture. The glazed SHOPFRONT beside the entrance
    (the rest of the ground storey as glass) is 3.17 facade work and is deliberately not done here.
  Gate: `probe_buildings.gd` (783 checks) asserts it **by movement** — a slide leaf must translate and not turn,
  a hinged one turn and not translate — because a leaf that reads "SLIDE" and swings is the failure worth
  catching. Measured: the airport's doors slide 2.00 m and turn 0.0°.
- **Top speed: 200 km/h** (user decision). SPC-1 67 → **55 m/s**, POC-1 62 → **50**, PIT-1 50 → **40**, in
  `build_vehicle_scenes.py`'s `TUNING`. 241 km/h is realistic for an unrestricted sports coupe (JDM cars ship
  180 km/h-limited), but the island is 3.7 km across and its roads are authored at 80/60/30 km/h, so the old
  number crossed the world in 55 s and ran at 3× the traffic; every launch measured in PLAN.md 0.7 was at 45 m/s.

## Known Quirks / Gotchas

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
