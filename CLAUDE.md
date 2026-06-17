# CLAUDE.md — Codebase Reference

Third-person shooter experiment using **Godot 4.6** with the **godot-kotlin-jvm** plugin.
All game logic is written in **Java** (a few stubs in Kotlin). GDScript is not used.

---

## Build & Run

```bash
./gradlew build          # compile + generate .gdj registration files into gdj/
```

Open `project.godot` with the **Godot Kotlin/JVM editor** (not the standard editor).
Plugin version: `0.15.0-4.6`. JVM toolchain: **JDK 17**.

Generated `.gdj` files land in `gdj/` and are what Godot actually loads.
Source of truth is always `src/main/java/` — never edit generated files.

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
                  #   CharacterVisuals, CharacterNameplate, MeshConfig, CharacterRagdoll,
                  #   CharacterDriveState, CharacterReplication, Faction
  ai/             # AI brain + FSM: AIController, AIState (base), AIBehaviorConfig
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
  world/          # world types: HitInfo, HittableBody, SurfaceType
    manager/      #   world-level singleton systems: Impact/Particle/Decal/Explosion/BulletTracer
  item/           # Pickup (RigidBody3D base for world pickups), AmmoRefill station
  carrier/vehicle/ # Vehicle, VehicleWheel, VehicleConfig, VehicleWeaponMode
  game/           # EventBus (AutoLoad signals), GameManager (PLAYING/PAUSED/GAME_OVER FSM)
    mission/      #   MissionInfo, MissionManager, MissionObjectiveType
  net/            # NetworkManager (AutoLoad RPC), NetMessageCodec, NetworkController,
                  #   VehicleNetworkController, snapshot interpolators, policies, NetStats, Vec3/Quat
    session/      #   PlayerSession, PersistentPlayerId
  ui/             # CharacterHUD, Crosshair, HUDManager, PauseMenu, RadialMenu, Feed, …
  util/           # ObjectPool, generic helpers
  debug/          # DebugHarness (temporary test-spawn harness)

src/main/resources/com/openworld/  # .tscn/.tres (internal layout NOT yet remapped to new java pkgs)
  character/Character.tscn, Player.tscn, AICharacter.tscn
  weapon/AR4.tscn, PI52.tscn, …    world/World.tscn, WorldSystems.tscn    ui/…
src/test/java/com/openworld/net/   # headless unit tests for the engine-free net logic
```

> AutoLoads (`project.godot`): `EventBus`, `GameManager` (`game`), `MissionManager`
> (`game.mission`), `NetworkManager` (`net`).

---

## Core Architecture Pattern

### CharacterInput loop

Every character (player or enemy) runs the same two-step cycle each physics frame:

```
Character._physicsProcess(delta)
    1. input = gatherInput(delta)     ← subclass provides the source
    2. applyInput(input, delta)       ← base class applies to shared state
```

`CharacterInput` is a plain struct holding all per-tick intent:
`movementDirection`, `movementType`, `wantCombat`, `fire`, `reload`, `jump`,
`roll`, `desiredStance`, `desiredWeapon`, `aimTargetPosition`, `tick`.

- **Player** overrides `gatherInput`: polls `Input` singleton (keyboard/mouse).
- **Enemy** overrides `gatherInput`: runs AI FSM, writes decisions into the struct.
- **Network** (future): inject a deserialized snapshot — no other code changes needed.

The `tick` counter makes inputs totally ordered for future replay/reconciliation.

### Scene Inheritance

```
CharacterBody3D (Character.tscn)
    shared subtree: Health, WeaponController, AnimationController,
                    MovementController, ragdoll skeleton, stances
    ├── Player.tscn  — adds: PlayerCameraController, CharacterHUD, AimStayTimer
    └── Enemy.tscn   — adds: EnemyCameraController, NavigationAgent3D, SightRay
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
                                └── SightRay (RayCast3D) ← LoS only (Enemy)
```

`PlayerCameraController._input` accumulates `InputEventMouseMotion.getRelative()` deltas into
`pendingYaw / pendingPitch` on every mouse event; `gatherLookInput` consumes and resets them
each physics tick. This captures every mouse event between physics steps rather than sampling
only the last velocity (`getLastMouseVelocity`), which dropped intermediate events.
`EnemyCameraController.gatherLookInput` → derives yaw/pitch delta from `aimTarget` world position.

Recoil is stored as `recoilPitch / recoilYaw` on `CameraController` and decays via
`GD.lerp(…, 0, recoilRecoverySpeed * delta)` each frame — fully separate from the
mouse-intent `pitch/yaw` so recovery never fights aim. `recoilPitch` is **subtracted** per shot
(`recoilPitch -= pitchKick`) because negative pitch = look up in Godot's convention.
`recoilRecoverySpeed = 8.0` gives a snappy per-shot kick that clears in ~0.3 s; sustained fire
builds a learnable upward drift (~1.7° at full spray) rather than a persistent offset.

---

## Enemy AI (5-state singleton FSM)

States are **stateless** singleton objects. All mutable data lives on `Enemy`.
`EnemyAIState.update()` returns the next state; a different reference triggers transition.

| State | Key behaviour |
|:------|:--------------|
| `PatrolState` | NavAgent random walk within `patrolRadius` of spawn. → Chase/Attack on sight. → Search on hit. |
| `ChaseState` | Sprint to player (or last known pos). → Attack when in range + LoS. → Patrol after `LOST_PLAYER_TIMEOUT` (3 s). |
| `AttackState` | Strafe laterally. Reaction delay before first shot. Per-shot `hitChance` roll. Suppression fire for `suppressionDuration` after losing LoS. → Search when suppression expires. → RefillAmmo when dry. |
| `SearchState` | Sprint to last known position, strafe to peek. Re-engage on sight. → Patrol after 5 s. |
| `RefillAmmoState` | Sprint to `ammoRefill` Area3D. Fill all weapons on arrival. → Patrol. |

### Key Enemy fields (timers all on Enemy, not states)

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
- **AimRay**: fire direction — `Enemy.snapAimRay(target)` forces it to point at the
  computed aim target just before `input.fire = true`.
- These are independent so accurate LoS never implies accurate aim.

---

## Combat / Weapon System

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

Enemy bypasses spread entirely (`useWeaponSpread = false`); accuracy is controlled
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

### Ragdoll on death (Character.enableRagdoll)

1. `setPhysicsProcess(false)` on both `Character` and `MovementController`.
2. Disable all `CollisionShape3D` stance capsules.
3. Set `collisionMask` layer 1 on each `PhysicalBone3D` so bones rest on the floor.
4. `physicalBoneSimulator.physicalBonesStartSimulation()`.

---

## Event System (EventBus AutoLoad)

`EventBus` is a global `Node` registered as AutoLoad. Any node reaches it via
`getNodeOrNull("/root/EventBus")`.

| Signal | Emitter | Payload |
|:-------|:--------|:--------|
| `player_died` | `Player.onDied()` | — |
| `enemy_killed` | (future use) | score: `int` |
| `player_health_changed` | (future use) | currentHealth: `float` |
| `ammo_picked_up` | (future use) | weapon index: `int` |
| `character_eliminated` | `Health.takeDamage()` | attacker, victim, weapon, headshot |

`GameManager` connects `playerDied → onPlayerDied()` in `_ready()`.
`CharacterHUD` connects `characterEliminated → onCharacterEliminated()` in `_ready()`.

---

## MovementController flags (Player vs Enemy)

| Export flag | Player | Enemy |
|:------------|:------:|:-----:|
| `worldSpaceMovement` | `false` | `true` |
| `faceCameraInCombat` | `true` | `false` |

Player input is camera-relative (rotated by `camRotation`).
Enemy input is world-space (set directly by AI FSM).

---

## Godot-Kotlin-JVM Specifics

- Every class exposed to Godot needs `@RegisterClass`, methods need `@RegisterFunction`,
  properties need `@RegisterProperty` + `@Export`.
- Signal declarations: `Signal0 / Signal1<T> / Signal2<T,U> / Signal4<A,B,C,D>` declared as
  `public final` fields.
- Scene nodes not in `.tscn` but loaded via `.gdj` registration files in `gdj/` —
  always run `./gradlew build` before opening the editor.
- `GD.lerp`, `GD.lerpAngle`, `GD.clamp`, `GD.randf`, `GD.randfRange` are the GDScript global equivalents.
- `StringName` is used for signal names and node lookups; `NodePath` for node paths.

---

## Known Quirks / Gotchas

- Enemy `onDied()` must set `isDead = true` **before** calling `super.onDied()` (which stops
  physics processing). If `isDead` is not set first, `gatherInput` can still run on the
  same frame via a pending physics callback.
- `AimStayTimer` in `Player.gatherInput`: uses `isActionJustReleased` (not `isActionPressed`)
  to start the timer so it starts exactly once and doesn't restart every frame after it ends.
- `WeaponController.onWeaponFire` saves and restores `aimRay3D` rotation when applying spread;
  Enemy's `snapAimRay` pre-positions the ray before firing so the spread rotation must be
  skipped for enemies (`useWeaponSpread = false`).
- `ParticleManager` pool containers must be named exactly after the `SurfaceType` constant
  (e.g. node named `"FLESH"`, not `"Flesh"`). A missing container is silently skipped in `_ready()`.
- To add a new surface type: (1) add constant to `SurfaceType.java`, (2) add a child container
  under `ParticleManager` in the editor with `GPUParticles3D` children, (3) for world geometry
  attach `HittableBody` script and set `surfaceType` in the inspector.
- `ImpactManager.processHit()` is the single place to add new hit effects (decals, sounds,
  physics impulse). `WeaponController` does not need to change for any of those additions.
- `PhysicalBoneSimulator3D` children must be added to `aimRay.addException()` in both
  `Character._ready()` and `Enemy._ready()` (for SightRay) to prevent self-hits.
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
