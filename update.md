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

## Phase 4 — Network foundation  🔜 NEXT

### Goal
Source Engine-style feel: owning client predicts locally, server is authoritative,
non-authority peers receive replicated state. L4D bot-fill via controller swap.

### Steps

**Step 1 — MultiplayerSynchronizer in Character.tscn**
Add `MultiplayerSynchronizer` node to `Character.tscn`. Sync properties:
- `global_position`, `velocity`
- `currentStanceName` (int), `combat` (bool)
- Animation tree parameters (blend positions, state names)
- `Health.currentHealth`

**Step 2 — NetworkController implementation**
Fill `NetworkController.java` (currently skeleton):
```java
// Ring buffer (size = max RTT ticks, e.g. 64)
private final UserCommand[] buffer = new UserCommand[64];

// Called by network layer when server broadcasts a corrected state
public void receiveCommand(UserCommand cmd) {
    buffer[(int)(cmd.tick % buffer.length)] = cmd.copy();
}
```

**Step 3 — PlayerController: send commands to server**
In `PlayerController.gatherInput()`, after building the `UserCommand`:
```java
cmd.sequenceNumber = ++localSequence;
// RPC to server: sendCommand(cmd)  — serialize UserCommand fields
```
Server receives, runs `applyInput()` authoritatively, echoes `lastServerAck` back.

**Step 4 — Client-side prediction reconciliation**
`PlayerController` maintains a ring buffer of recent `UserCommand` copies.
On receiving server correction (position/state diverges from prediction):
1. Snap to server state.
2. Replay buffered commands from `lastServerAck + 1` forward.
`UserCommand.copy()` and `Character.applyInput()` are already deterministic — no
changes needed there.

**Step 5 — Bot-fill / L4D controller swap**
```java
// Player disconnects → attach CharacterController
void onPlayerLeft(Player body) {
    body.controller.queueFree();
    CharacterController bot = new CharacterController();
    body.addChild(bot);
}
// Player reconnects → swap back
void onPlayerJoined(Player body) {
    body.controller.queueFree();
    PlayerController human = new PlayerController();
    body.addChild(human);
}
```
`Character._ready()` already scans children for a `Controller` — no other wiring needed.

**Step 6 — AIController authority**
`AIController.isAuthority()` inherits `getOwner().isMultiplayerAuthority()`.
In multiplayer, AI nodes are owned by the server — this returns true only on server.
No code change needed; the authority model already works.

---

## Phase 5 — Vehicle support  📋 PLANNED

### Design

```
Controllable (interface)
  void applyCommand(UserCommand cmd, double delta)
  CharacterInfo getCharacterInfo()

Character implements Controllable   ← already effectively does this
VehicleBody implements Controllable ← new (RigidBody3D base)
```

`UserCommand` already has vehicle fields (`throttle`, `steering`, `handbrake`, `enterExit`).
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
vehicle.attachController(new VehicleAIController()); // or leave empty
```

**Faction / targeting:**
`VehicleBody.characterInfo` has a faction. `AICharacter.discoverTarget()` scans
the `"characters"` group — add vehicles to the same group so AI can target them.

### Steps (implement when ready)
- [ ] `Controllable.java` interface
- [ ] `VehicleBody.java` (RigidBody3D, implements Controllable)
- [ ] `GroundVehicle.java` (car/tank — physics tuning)
- [ ] `VehicleAIController.java` (route/waypoint FSM)
- [ ] `HumanBrain`→`PlayerController`: generate vehicle fields when target is Vehicle
- [ ] `VehicleBody.tscn` base scene
- [ ] Add vehicles to `"characters"` group for faction targeting

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
