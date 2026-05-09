# Architecture Roadmap — Brain/Body Split + Network + Vehicle
Branch: `issue-21`

---

## Phase 3 — Controller/UserCommand refactor  ✅ COMPLETE
Build: clean. All tasks done.

### What was done
- `CharacterInput` → `UserCommand` (≈ Source `CUserCmd`). Added `sequenceNumber`,
  `lastServerAck` (network reconciliation), `throttle`/`steering`/`handbrake`/`enterExit`
  (vehicle Phase 5 stubs).
- `Controller` (abstract Node) — `isAuthority()` delegates to `isMultiplayerAuthority()`.
- `PlayerController` — keyboard/mouse, child of `Player`. Extracted from `Player.gatherInput()`.
- `AIController` (abstract) — owns all FSM timers + memory: `lastKnownTargetPosition`,
  `currentAimTarget`, strafe state, `computeSuppressTarget`, `refreshStrafe`, all
  reset/advance/check helpers. Read body config via `getBody().suppressionDuration` etc.
- `CharacterController` — concrete, caches `AICharacter` owner, starts `PatrolState`.
- `NetworkController` — skeleton, `isAuthority()=false`, ready for Phase 4.
- `AIState` interface: `enter/exit/update(AICharacter body, AIController ctrl, UserCommand cmd, delta)`.
  All 5 FSM states updated — body calls = hardware, ctrl calls = memory/state.
- `Character._physicsProcess`: checks `controller.isAuthority()`, early-returns for
  non-authority peers (state arrives via `MultiplayerSynchronizer`).
- `Player`: removed `gatherInput()`. Added `isCombat()` getter.
- `AICharacter`: removed FSM/timers/memory. Kept hardware (NavAgent, SightRay, sensing).
  Added `isDead()` getter, `getCharacterController()`.
- `Player.tscn`: `PlayerController` child node added.
- `AICharacter.tscn`: `CharacterController` child node added.
- `CharacterInput.java` deleted.

### Key files created
```
src/main/java/com/character/
  UserCommand.java
  Controller.java
  PlayerController.java
  AIController.java
  CharacterController.java
  NetworkController.java
```

---

## Phase 4 — Network foundation  ✅ COMPLETE
Build: clean. All tasks done.

### What was done
- `Character.java`: `combat` promoted to `@RegisterProperty @Export public boolean`;
  new `@RegisterProperty @Export public int stanceOrdinal` mirrors
  `currentStanceName.ordinal()` — updated every `setStance()` call.
- `Health.java`: new `@RegisterProperty @Export public float syncHealth` mirrors
  `currentHealth` — updated in `_ready()`, `takeDamage()`, and `heal()`.
- `Character.tscn`: Added `MultiplayerSynchronizer` child node with a
  `SceneReplicationConfig` sub-resource syncing:
  - `global_position` (spawn=true, ALWAYS)
  - `velocity` (spawn=false, ALWAYS)
  - `combat` (spawn=true, ON_CHANGE)
  - `stance_ordinal` (spawn=true, ON_CHANGE)
  - `Health:sync_health` (spawn=true, ON_CHANGE)
- `NetworkController.java`: BUFFER_SIZE=64 ring buffer; `receiveCommand(cmd)` stores
  by tick; `getBufferedCommand(tick)` retrieves for replay. Non-authority peers still
  return an empty `UserCommand` from `gatherInput()`.
- `PlayerController.java`: `localSequence` counter; `predictionBuffer[64]` ring buffer;
  `gatherInput()` stamps `cmd.sequenceNumber = ++localSequence` and stores a copy;
  `reconcile(serverAck)` discards entries ≤ serverAck (replay wired in TODO comment).
- `GameManager.java`: `onPlayerLeft(Player body)` swaps in `CharacterController` (bot);
  `onPlayerJoined(Player body)` swaps in `PlayerController` (human) — L4D-style
  controller hot-swap without touching the body.
- Step 6 (AIController authority): no change needed — inherits
  `getOwner().isMultiplayerAuthority()` which is true only on server for AI nodes.

### Phase 4 TODOs (actual transport, not yet wired)
- Serialize `UserCommand` and call `rpc_id(1, "server_receive_cmd", ...)` in
  `PlayerController.gatherInput()` after stamping `sequenceNumber`.
- Server-side handler: run `applyInput()` authoritatively, echo `lastServerAck` back.
- Wire `PlayerController.reconcile()` to MultiplayerSynchronizer sync signal or a
  custom RPC so it triggers on state correction from the server.
- Animation tree parameter sync: add blend positions / state machine current state
  to the `SceneReplicationConfig` once property paths are confirmed in the editor.

---

## Phase 5 — Vehicle support  ✅ COMPLETE
Build: clean. All tasks done.

### Design

```
Controllable (interface)
  void applyCommand(UserCommand cmd, double delta)
  CharacterInfo getCharacterInfo()

Character implements Controllable   ← applyCommand() delegates to applyInput()
VehicleBody implements Controllable ← new (VehicleBody3D base)
```

`UserCommand` already had vehicle fields (`throttle`, `steering`, `handbrake`, `enterExit`).
`Character.applyInput()` ignores them; `VehicleBody.applyCommand()` reads them.

**Control transfer (enter/exit vehicle):**
```java
// Player walks to vehicle, presses interact (enterExit = true):
Controller ctrl = playerBody.detachController();
ctrl.setTarget(vehicle);       // Brain now generates vehicle-field UserCommands
vehicle.attachController(ctrl);
playerBody.attachController(new IdleController());

// Player exits:
Controller ctrl = vehicle.detachController();
ctrl.setTarget(playerBody);
playerBody.attachController(ctrl);
vehicle.attachController(new VehicleAIController());
```

**Faction / targeting:**
`VehicleBody.characterInfo` has a faction. `AICharacter.discoverTarget()` scans
the `"characters"` group — vehicles are added to the same group on `_ready()`.

### What was done
- `Controllable.java` interface: `applyCommand(UserCommand, double)` +
  `getCharacterInfo()` — the universal possession protocol for any body type.
- `Character` now implements `Controllable`: `applyCommand()` delegates to
  `applyInput()`; `detachController()` / `attachController()` enable hot-swap.
- `Controller`: `setTarget(Controllable)` + `getControllable()` — explicit target
  override for the transition window between detach and reparent.
- `PlayerController` refactored: no longer caches `body` at `_ready()` time.
  `gatherInput()` calls `gatherCharacterInput()` or `gatherVehicleInput()` based
  on what `getControllable()` returns. Vehicle input maps existing directional
  actions to `throttle`/`steering`/`handbrake` (`jump` = handbrake, `use` = enterExit).
- `VehicleBody.java` (`com/vehicle`): extends Godot `VehicleBody3D`, implements
  `Controllable`. Exports `engineForce`, `brakeStrength`, `maxSteerAngle`,
  `idleBrake`. Adds to `"characters"` group. Owns `Controller` child +
  `Health` node. `applyCommand()` drives Godot's built-in wheel physics.
  `detachController()` / `attachController()` mirror Character's hot-swap API.
- `GroundVehicle.java` (`com/vehicle`): extends `VehicleBody`. Exports `maxSpeed`
  and `reverseSpeedFactor`; zeros `throttle` once the speed cap is exceeded.
- `VehicleAIController.java` (`com/vehicle`): extends `Controller`. Uses
  `NavigationAgent3D` to steer toward a waypoint set via `setNavigationTarget()`.
  Proportional steering: dot-product of next-path vector against vehicle right axis.
- `VehicleBody.tscn` (`src/main/resources/com/vehicle/`): base scene — `VehicleBody3D`
  root + `Health` node + blank `CollisionShape3D`. Add `VehicleWheel3D` children
  and mesh in the editor per vehicle type.

### Key files created
```
src/main/java/com/character/
  Controllable.java

src/main/java/com/vehicle/
  VehicleBody.java
  GroundVehicle.java
  VehicleAIController.java

src/main/resources/com/vehicle/
  VehicleBody.tscn

gdj/com/vehicle/              ← auto-generated by ./gradlew build
  VehicleBody.gdj
  GroundVehicle.gdj
  VehicleAIController.gdj
```

### Phase 5 TODOs (editor setup, not yet wired)
- In editor: open `VehicleBody.tscn`, add 4 `VehicleWheel3D` children at wheel
  positions; set `use_as_traction = true` on rear wheels, `use_as_steering = true`
  on front wheels. Add a `CollisionShape3D` with a `BoxShape3D` fitting the chassis.
- Add `"use"` input action to the Godot project input map (for enter/exit).
- `GroundVehicle.tscn`: inherit from `VehicleBody.tscn`, add mesh + tuned wheels.
- Wire enter/exit: in `Player.gatherInput` or a dedicated `InteractionController`,
  detect `cmd.enterExit` near a vehicle and call `playerBody.detachController()` /
  `vehicle.attachController(ctrl)` sequence.

---

## Terminology reference
| Term | Equivalent | Notes |
|---|---|---|
| `UserCommand` | Source `CUserCmd` | Per-tick command struct |
| `Controller` | Unreal `AController` / Source `CBotController` | Generates UserCommand |
| `PlayerController` | Unreal `APlayerController` | Keyboard/mouse |
| `AIController` | Unreal `AAIController` / Source `CAI_BaseNPC` | FSM + memory |
| `CharacterController` | L4D `SurvivorBot` | On-foot AI concrete controller |
| `NetworkController` | — | Non-authority placeholder |
| `Character` | Unreal `APawn` / Source `CBaseCombatCharacter` | Body |
| `Player` | Unreal `ACharacter` | Human-controlled body |
| `AICharacter` | L4D `CTerrorPlayer` (NPC) | AI-controlled body |
| `Faction` | — | String-based; `areHostile()` for targeting |
| `CharacterInfo` | — | id + displayName + faction per character |
