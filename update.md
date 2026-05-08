# Character Identity & Faction System — Implementation Plan

Branch: `issue-21`

---

## Phase 1 — CharacterInfo / Faction / weaponPickedUp filter  ✅ COMPLETE

All steps done. Build successful. Notes:
- `CharacterHUD` is NOT owned by Player — lives under HUDManager (CanvasLayer) in
  World.tscn. Player characterId is injected via `HUDManager.wirePlayer()` →
  `CharacterHUD.setPlayerCharacterId()`.
- Faction guard placed in `Enemy.canSeePlayer()` — single LoS gate for all AI states.
- Both Player.tscn and Enemy.tscn already have CharacterInfo resources configured
  (character_id = "player"/"enemy", faction = "player"/"enemy").

---

## Phase 2 — Rename Enemy → AICharacter; dynamic target discovery

### Motivation

- `Enemy` implies faction: any AI character could be neutral or friendly.
- The hardcoded `@Export Character player` field is redundant now that
  `Faction.areHostile()` determines targeting — the AI should discover hostile
  characters dynamically from the scene instead of requiring inspector wiring.

### Design decisions

- **`Enemy` → `AICharacter`**: class, file, Godot class name, scene file.
- **`EnemyAIState` → `AIState`**: the interface is generic to any AI character.
- **`EnemyCameraController`**: keep name — camera-concern only, not faction-related.
- **`EventBus.enemyKilled`**: keep name for now — changing signal names also requires
  updating scene signal connections; defer to a dedicated cleanup pass.
- **Target discovery**: `Character` nodes self-register into the Godot group
  `"characters"` in `_ready()`. `AICharacter.discoverTarget()` scans that group,
  filters by `Faction.areHostile()` and distance, returns the nearest hostile.
- **`currentTarget`** replaces `player`: runtime field, not exported. Set lazily
  by `canSeeTarget()` → `discoverTarget()`. Cleared in `PatrolState.enter()`.
- All AI state method signatures change from `Enemy` to `AICharacter`.

### Files to create

#### `src/main/java/com/character/ai/AIState.java`
Rename of `EnemyAIState.java`:
- Interface name: `AIState`
- Method signatures: `enter/exit/update` take `AICharacter` instead of `Enemy`
- Return type of `update`: `AIState`

#### `src/main/java/com/character/AICharacter.java`
Rename + refactor of `Enemy.java`:
- `@RegisterClass(className = "AICharacter")`
- Remove `@Export Character player`
- Add `private Character currentTarget`
- Add private `discoverTarget()` scanning `"characters"` group
- `getPlayer()` → `getTarget()` returns `currentTarget`
- `canSeePlayer()` → `canSeeTarget()`: calls `discoverTarget()` if null,
  then checks detectionRange + `hasLineOfSight()`
- `hasLineOfSight()`: replace all `player` refs with `currentTarget`
- `computeAimTarget()`, `computeSuppressTarget()`: replace `player` refs
- `clearCameraAimTarget()` → unchanged (camera concern)
- Field `private EnemyAIState currentState` → `private AIState currentState`
- `transitionTo(EnemyAIState)` → `transitionTo(AIState)`
- `gatherInput` → unchanged logic, just type references updated
- `onEnemyDamaged` → keep name (connected by scene signal)

#### `src/main/resources/com/character/AICharacter.tscn`
Copy of `Enemy.tscn` with:
- Script ext_resource path: `gdj/com/character/AICharacter.gdj`
- Node name: `"AICharacter"` (was `"Enemy"`)
- Signal connection: `damaged → on_enemy_damaged` (method name stays — signal connection)
- No other structural changes needed

### Files to modify

#### `src/main/java/com/character/Character.java`
In `_ready()`, after existing setup, add:
```java
addToGroup(new StringName("characters"), false);
```

#### `src/main/java/com/character/ai/PatrolState.java`
- Import `AICharacter` instead of `Enemy`, `AIState` instead of `EnemyAIState`
- All method signatures: `Enemy enemy` → `AICharacter c`
- `enemy.canSeePlayer()` → `c.canSeeTarget()`
- `enemy.getPlayer()` → `c.getTarget()`
- Implement `enter(AICharacter c)`: call `c.clearTarget()` then `c.setNextPatrolTarget()`

#### `src/main/java/com/character/ai/ChaseState.java`
- Same import/type/method rename pattern
- `enemy.getPlayer()` → `c.getTarget()`
- `enemy.canSeePlayer()` → `c.canSeeTarget()`

#### `src/main/java/com/character/ai/AttackState.java`
- Same import/type/method rename pattern
- `enemy.getPlayer()` → `c.getTarget()`

#### `src/main/java/com/character/ai/SearchState.java`
- Same import/type/method rename pattern
- `enemy.canSeePlayer()` → `c.canSeeTarget()`
- `enemy.getPlayer()` → `c.getTarget()`

#### `src/main/java/com/character/ai/RefillAmmoState.java`
- Same import/type/method rename pattern

#### `src/main/resources/com/world/World.tscn`
- Update ext_resource path: `Enemy.tscn` → `AICharacter.tscn`  
- Node name: `"Enemy"` → `"AICharacter"`
- Remove `node_paths=PackedStringArray("player", "ammo_refill")` → `PackedStringArray("ammo_refill")`
- Remove `player = NodePath("../Player")`
- Keep `ammo_refill = NodePath(...)` unchanged

### Files to delete
- `src/main/java/com/character/Enemy.java`
- `src/main/java/com/character/ai/EnemyAIState.java`
- `src/main/resources/com/character/Enemy.tscn`

---

## Execution checklist

- [ ] Step 1: Update `Character.java` — addToGroup("characters")
- [ ] Step 2: Create `AIState.java` (rename of EnemyAIState)
- [ ] Step 3: Create `AICharacter.java` (rename + refactor of Enemy)
- [ ] Step 4: Create `AICharacter.tscn` (copy + update of Enemy.tscn)
- [ ] Step 5: Update all 5 AI state files (PatrolState, ChaseState, AttackState, SearchState, RefillAmmoState)
- [ ] Step 6: Update `World.tscn` — new scene path, remove player export, rename node
- [ ] Step 7: Delete `Enemy.java`, `EnemyAIState.java`, `Enemy.tscn`
- [ ] Step 8: `./gradlew build` — confirm clean compile
