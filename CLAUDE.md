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

```
src/main/java/
  com/character/          # all character logic
    ai/                   # enemy FSM states (5 files)
    Character.java        # base CharacterBody3D — gatherInput / applyInput loop
    Player.java           # samples keyboard/mouse → CharacterInput
    Enemy.java            # AI FSM owner — all mutable AI state lives here
    CharacterInput.java   # per-tick input snapshot (shared by player, AI, network)
    Health.java           # damage, bone multipliers, headshot, death signal
    WeaponController.java # firing, reload, bloom/spread, recoil; calls ParticleController for VFX
    WeaponStats.java      # Resource: per-weapon stats (spread, bloom, fire rate…)
    AnimationController.java  # AnimationTree parameter writes
    MovementController.java   # physics: velocity, gravity, mesh rotation, crosshair
    CameraController.java     # base camera: recoil, shoulder swap, FoV tween
    PlayerCameraController.java  # mouse input → CameraController
    EnemyCameraController.java   # AI aim target → CameraController
    MovementState.java    # Resource: speed, acceleration, FoV, animation speed
    MovementType.java     # enum: IDLE / WALK / SPRINT
    StanceName.java       # enum: UPRIGHT / CROUCH / CRAWL
    Stance.java           # Resource: collider ref, movement states, camera height
    CombatState.java      # Resource: speed factor, FoV, shoulder offset, distance
    JumpState.java        # Resource: jump height, apex duration, animation name
    RollState.java        # Resource: roll speed, duration, animation name
  com/environment/
    AmmoRefill.java       # Area3D: fills all weapons when Player enters
    SurfaceType.java      # enum: FLESH / METAL / STONE / WOOD / DEFAULT
    HittableBody.java     # StaticBody3D subclass: attach to world geometry needing non-default particles
    HitInfo.java          # immutable hit snapshot (node, point, normal) — network-serializable
    ParticleManager.java  # world-level pool — fire-and-forget GPUParticles3D per SurfaceType
    DecalManager.java     # world-level pool — held Decal nodes recycled after decalLifetime seconds
    ImpactManager.java    # world-level singleton: resolves every HitInfo → particles + decal + damage
  com/game/
    EventBus.java         # AutoLoad singleton — global signals
    GameManager.java      # AutoLoad singleton — PLAYING / PAUSED / GAME_OVER FSM
  com/ui/
    CharacterHUD.java     # health label, ammo label, kill notification (3 s)
    Crosshair.java        # reticle arms track live spread from WeaponController
    PauseMenu.java
    RadialMenu.java / RadialMenuItem.java
  com/util/
    ObjectPool.java       # generic fixed-size pool (used for splatter particles)

src/main/resources/com/  # .tscn scene files mirroring the Java package structure
  character/Character.tscn, Player.tscn, Enemy.tscn
  weapon/pistol.tscn, rifile.tscn
  world/World.tscn
  ui/PauseMenu.tscn
```

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

`PlayerCameraController.gatherLookInput` → mouse velocity.
`EnemyCameraController.gatherLookInput` → derives yaw/pitch delta from `aimTarget` world position.

Recoil is stored as `recoilPitch / recoilYaw` on `CameraController` and decays via
`GD.lerp(…, 0, recoilRecoverySpeed * delta)` each frame — fully separate from the
mouse-intent `pitch/yaw` so recovery never fights aim.

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

### Spread formula (WeaponController)

```
totalSpreadDeg = (baseSpread + velocity_m_s × 0.12 + currentBloom) × stanceMultiplier
```

Stance multipliers: UPRIGHT 1.0×, CROUCH 0.7×, CRAWL 0.5×, airborne 2.0×.

Bloom: `currentBloom += bloomPerShot` per shot; decays by `bloomDecaySpeed` deg/s when not firing.

Enemy bypasses spread entirely (`useWeaponSpread = false`); accuracy is controlled
by `hitChance` + `aimScatterRadius` in `AttackState`.

### Crosshair

`MovementController._physicsProcess` sets `crosshair.setPositionX(weaponController.getCurrentSpreadDeg() × 8.0f)`.
`Crosshair._process` lerps the four reticle line arms toward that position
(fast expand: `crosshairExpandSpeed = 60`, slow contract: `crosshairContractSpeed = 1`).

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
- `Physical Bone neck_01` → 4.0× (headshot)
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
  `WeaponAttachment` at `_ready()` — add a new weapon by adding a `WeaponStats` child node.
