# Godot Kotlin/JVM Third Person Experiment

A technical exploration of 3D game mechanics in **Godot 4.x** using the **Kotlin/JVM** binding. This project adapts and refactors traditional GDScript-based third-person controllers into a Java/Kotlin-compatible architecture.

## 🎮 Play the Game
A prebuilt binary is available on **itch.io**: [third-person-shooter-godot-jvm](https://danil-ko.itch.io/third-person-shooter-godot-jvm)

## 📺 Gameplay Video
Watch the gameplay demo on **YouTube**: [third-person-shooter-godot-jvm](https://youtu.be/CiJGKLYyk9Q)

## 🛠 Tech Stack
* **Engine:** Godot 4.6 (Custom [Utopia-Rise](https://github.com/utopia-rise/godot-kotlin-jvm) build required)
* **Plugin:** godot-kotlin-jvm `0.15.0-4.6`
* **Language:** Java / Kotlin
* **JDK:** 17 (configured via Gradle JVM toolchain)

## ✨ Features & Modifications
This project is based on:
 - Johnny Rouddro's Third Person Controller tutorial ([YouTube](https://www.youtube.com/watch?v=3AD2z2mx3sY)) with several architectural changes and gameplay tweaks.
 - octodemy's Custom Raycast Vehicle Physics in Godot ([YouTube](https://www.youtube.com/@octodemy)) with several architectural changes and gameplay tweaks.

* **Input-Driven Character Architecture:** `Character` (base) → `Player` / `AICharacter`. Each body delegates its "brain" to a `Controller` (`PlayerController` for keyboard/mouse, `AIController` for the FSM) via the `Controllable` interface. All state transitions go through a `UserCommand` snapshot, making human input, AI, and future network input interchangeable.
* **Movement Mechanics:**
	* Added **Double Jump** capability.
	* **Crawl-to-Shoot** mechanics (Experimental/Beta animation).
	* Dynamic **Physics Body transformation** during dodge rolls.
* **Combat & Ballistics:**
	* Arcade-style shooting: recoil-only challenge by default; optional bloom accumulation and movement/stance spread modifiers for each weapon.
	* Dynamic crosshair that tracks live spread from `WeaponController` via a configurable pixel-per-degree scale.
	* Toggleable over-the-shoulder camera (Left/Right swap).
* **AI (7-state FSM):**
	* Configurable hit chance, reaction delay, aim scatter, and suppression fire.
	* Navigation via `NavigationAgent3D`; separate SightRay (LoS) and AimRay (fire direction).
	* Ammo management with a dedicated `RefillAmmoState`.
	* Faction-aware targeting (`AICharacter.discoverTarget()`) — same-faction AI ignore each other and neutral factions are never targeted, enabling friendly escorts and non-hostile NPCs.
	* `EscortState` (follow + defend a designated character) and `FleeState` (sprint away from an attacker, then return to patrol).
* **Drivable Vehicle:**
	* Player able to enter and exit vehicle
	* Arcade driving vehicle
* **Game Systems:**
	* `EventBus` AutoLoad singleton for decoupled kill/death events.
	* `GameManager` AutoLoad singleton (PLAYING / PAUSED / GAME_OVER).
	* `AmmoRefill` environment trigger that replenishes all weapons on contact.

---

## 🏗 Architecture

### Character Input Pattern

```
Character._physicsProcess()
	│
	├── controller.gatherInput(delta) → UserCommand   ← per-body Controller
	│       PlayerController : polls Input singleton (keyboard/mouse)
	│       AIController     : runs the AI FSM, writes decisions into the snapshot
	│       (Network)        : future — inject a deserialized snapshot here
	│
	└── applyInput(command, delta)                    ← shared in base class
			all signal emissions and state transitions live here
```

`UserCommand` carries a monotonically-increasing `tick`/`sequenceNumber` so inputs are totally ordered and can be replayed for client-side prediction in the future.

### Scene Inheritance

```
CharacterBody3D (Character.tscn)   ← shared ragdoll, health, weapon controller
	├── Player.tscn                 ← PlayerController, HUD wiring, keyboard/mouse input
	└── AICharacter.tscn            ← AIController (FSM), NavigationAgent3D, SightRay
```

---

## 🤖 AI

AI characters run on a **7-state singleton FSM** owned by `AIController`. States are stateless objects; all mutable data (timers, last-known position, faction, escort/flee targets) lives on the `AICharacter` node.

| State | Description |
|:------|:------------|
| **PatrolState** | Wanders within `patrolRadius` of spawn using NavAgent. Transitions to Chase/Attack on sight, Search on hit. |
| **ChaseState** | Sprints toward the player. Navigates to last known position when LoS is broken. Falls back to Patrol after `LOST_PLAYER_TIMEOUT`. |
| **AttackState** | Strafes laterally, waits for `reactionTime`, then fires per-shot accuracy rolls. Fires suppression shots at last known position for up to `suppressionDuration` after losing LoS. |
| **SearchState** | Moves to last known position and strafes to peek cover. Re-engages on sight; gives up after 5 s and returns to Patrol. |
| **RefillAmmoState** | Sprints to the `ammoRefill` Area3D. Fills all weapons on arrival, then returns to Patrol. |
| **EscortState** | Follows a designated `Character` at a configurable distance; switches to Attack if the escort target is attacked. |
| **FleeState** | Sprints away from an attacker for a configured distance, then returns to Patrol. |

Targeting is faction-aware (`AICharacter.discoverTarget()`): same-faction AI never target each other and neutral factions are skipped entirely, which is what makes friendly escorts and non-hostile NPCs possible.

### State Transitions

```
Patrol ──(sees hostile, in range)──► Attack ──(out of range)──► Chase
	   ──(sees hostile, out of range)► Chase  ──(in range + LoS)► Attack
	   ──(hit without LoS)──────────► Search  ──(sees hostile)──► Attack/Chase
											  ──(timeout 5 s)───► Patrol
	   ──(assigned escort target)───► Escort  ──(target attacked)► Attack
	   ──(low health / overwhelmed)─► Flee    ──(reached flee distance)► Patrol
Attack ──(no ammo)──────────────────► RefillAmmo ───────────────────► Patrol
```

### Accuracy Knobs

| Property | Default | Description |
|:---------|:-------:|:------------|
| `hitChance` | 0.9 | Per-shot probability of actually hitting (0 = always miss, 1 = always hit) |
| `reactionTime` | 0.1 s | Seconds from first LoS contact before firing starts |
| `aimScatterRadius` | 1.5 | Max scatter radius (world units) at 10 m; scales linearly with distance |
| `suppressionDuration` | 1.5 s | How long the enemy fires blind after losing LoS |
| `strafeChangeDuration` | 1.0 s | Seconds between lateral strafe direction changes |
| `detectionRange` | 120 | Max range for LoS detection |
| `attackRange` | 150 | Max range to stay in AttackState |

LoS is detected via a dedicated **SightRay** that is completely independent of the AimRay. This means accurate LoS detection never implies accurate aim — the two systems are decoupled.

---

## 🎯 Combat System

### Weapon Ballistics (Spread & Bloom)

`FirearmItem` computes a live spread value each frame:

```
totalSpreadDeg = (spread + currentBloom + speed_m_s × 0.03) × stanceMultiplier
```

The stance multiplier scales the **entire** expression — crouching and crawling reduce both the base accuracy penalty and the movement penalty at the same time.

| Stance / Condition | Multiplier |
|:-------------------|:----------:|
| Upright (default) | 1.0× |
| Crouch | 0.7× |
| Crawl | 0.5× |
| Airborne | 2.0× |

**Bloom** (`currentBloom`) accumulates per shot and decays continuously. The key tuning relationship: if `bloomDecaySpeed < bloomPerShot × fireRate` bloom builds during sustained fire (full-auto); if greater, each shot clears before the next (semi-auto tap-fire).

| Weapon | Base spread | Bloom/shot | Bloom decay | Bloom cap | Recoil/shot |
|:-------|:-----------:|:----------:|:-----------:|:---------:|:-----------:|
| Rifle  | 0.01°       | 0.05°      | 0.3°/s      | 0.25°     | 1.0°        |
| Pistol | 0.05°       | 0.05°      | 2.0°/s      | 0.2°      | 0.5°        |

**Crosshair** (`Crosshair.java`) reads `getCurrentSpreadDeg() × spreadPixelsPerDeg` (default **100 px/deg**) every frame and lerps the four reticle arms: instant snap outward on each shot, fast contract during recovery. At scale 100 the pistol's 0.05° base spread produces a 5 px arm gap from the moment it is drawn — giving an immediate visual "this is less precise than the rifle" signal without any shots fired.

**Camera recoil** is routed through `CameraController.applyRecoil()`: each shot subtracts from `recoilPitch` (negative = look up in Godot's convention) and adds a small random `recoilYaw`. Both decay via exponential lerp at `recoilRecoverySpeed = 8.0`, clearing in ~0.3 s — producing a snappy per-shot kick and a learnable upward drift during sustained spray, independent of spread.

### Skeleton Hitbox & Damage Zones

Damage is resolved against the character's **physical ragdoll skeleton** (`PhysicalBoneSimulator3D`). Each `PhysicalBone3D` acts as an independent collider, so the hit location on the body determines the damage multiplier applied to the base weapon damage.

| Body Zone | Bones | Damage Multiplier |
|:----------|:------|:-----------------:|
| **Head / Neck** | `head_2` | **4.0×** |
| **Upper Torso** | `spine_03`, `clavicle_l`, `clavicle_r` | 1.0× |
| **Mid / Lower Torso** | `spine_02`, `spine_01`, `pelvis` | 0.75× |
| **Arms** | `upperarm_l/r`, `lowerarm_l/r`, `hand_l/r` | 0.75× |
| **Legs** | `thigh_l/r`, `calf_l/r`, `foot_l/r` | 0.5× |

The hitbox colliders are the same bones that drive the ragdoll on death — no separate invisible hit-mesh is needed.

### Headshot Detection

A hit is classified as a **headshot** when the colliding bone is `Physical Bone head_2`. This single bone covers both the neck capsule and the head sphere in the ragdoll setup.

```
hit bone == "Physical Bone head_2"  →  headshot = true  →  4× damage
```

Headshot detection lives in `Health.takeDamage()` and is bone-name driven, so it works identically for both player and enemy characters.

### Kill Notifications (EventBus)

When any character's health reaches zero, `Health` emits a unified payload to the **EventBus** singleton:

```
EventBus.characterEliminated(attackerName, victimName, weaponName, headshot)
```

The player HUD (`CharacterHUD`) subscribes to this signal in `_ready()` and displays a 3-second notification:

| Situation | Example message |
|:----------|:----------------|
| Body shot kill | `Enemy Eliminated [Pistol] - Eliminated` |
| Headshot kill | `Enemy Eliminated [Pistol] - Headshot` |
| Player killed | `Player Eliminated [Rifle] - Eliminated` |

Character display names are configured via the `displayName` export property on each `Health` node. If left blank, the owning node's scene name is used as a fallback.

> **Note:** This is an experimental codebase. You may encounter "crunch-time" bugs or unstable animations. It is provided as-is for educational purposes.

---

## 🚀 Getting Started

### Prerequisites
You **cannot** use the standard Godot editor. You must download the specific Kotlin-JVM enabled editor from [Utopia-Rise Releases](https://github.com/utopia-rise/godot-kotlin-jvm).

### Build Instructions
1. Clone the repository.
2. Run the Gradle build task to generate the necessary JVM wrappers:
   ```bash
   ./gradlew build
   ```
3. Open the `project.godot` file using the **Godot Kotlin/JVM Editor**.

---

## 🎮 Controls

### On Foot

| Action                                  | Input                        |
|:----------------------------------------|:-----------------------------|
| **Move**                                | `W` `A` `S` `D`              |
| **Jump / Double Jump**                  | `Space`                      |
| **Roll (Third Person)**                 | `C` + Direction              |
| **Crouch (Hold) / Crawl (Hold)**        | `Ctrl` / `Shift`             |
| **Aim (Third Person) / Fire**           | `Mouse Right` / `Mouse Left` |
| **Reload**                              | `R`                          |
| **Switch Weapon (cycle)**               | `G`                          |
| **Select Weapon Slot (quick-switch)**   | `0` – `6` (see table below)  |
| **Drop Weapon**                         | `F`                          |
| **Equip/Use/Enter**                     | `E`                          |
| **Swap Camera Shoulder (Third Person)** | `Q`                          |
| **View Change to FPS/TPS**              | `Q`                          |
| **Menu**                                | `Esc`                        |

#### Weapon Slot Quick-Switch

| Key | Slot | Type | Example |
|:---:|:----:|:-----|:--------|
| `0` | 0 | Fist (permanent, always available) | — |
| `1` | 1 | Primary weapon A | Assault Rifle (AR4 / AR212) |
| `2` | 2 | Primary weapon B | Shotgun (SG1) / Rocket Launcher (ATL4) |
| `3` | 3 | Secondary (sidearm) | Pistol (PI52) |
| `4` | 4 | Melee | Knife |
| `5` | 5 | Throwable | Grenade (T1) |
| `6` | 6 | Consumable | — |

### On Vehicle

| Action                                  | Input                        |
|:----------------------------------------|:-----------------------------|
| **Accelerate/Back**                     | `W` `S`                      |
| **Steer**                               | `A` `D`                      |
| **Handbreak**                           | `Space`                      |
| **Ctrl**                                | `Break`                      |
| **Aim (Hold to change angle) / Fire**   | `Mouse Right` / `Mouse Left` |
| **Reload**                              | `R`                          |
| **Switch Weapon (cycle)**               | `G`                          |
| **Select Weapon Slot (quick-switch)**   | `0` – `6` (passenger weapon mode — see table above) |
| **Drop Weapon**                         | `F`                          |
| **Exit**                                | `E`                          |
| **Swap Camera Shoulder (Third Person)** | `Q`                          |
| **Menu**                                | `Esc`                        |
---

## 📚 Credits & Assets

### Code & Logic
* Base Third Person Controller by **Johnny Rouddro**: [YouTube](https://www.youtube.com/watch?v=3AD2z2mx3sY) | [GitHub](https://github.com/JohnnyRouddro/Godot_Third_Person_Controller) | [Itch.io](https://johnnyrouddro.itch.io/godot-4-third-person-controller)

### Models & External Assets
* **Weapon Models:** [50 Low-poly Guns](https://quaternius.itch.io/50-lowpoly-guns) by Quaternius.
* **Additional Assets:** [Godot Asset Library](https://godotengine.org/asset-library/asset/781).


Note:
Did use Gemini/Claude AI during debugging/documentation.

---

## 🎮 Screenshots
![screenshot1.png](images/screenshot1.png)
![screenshot2.png](images/screenshot2.png)
![screenshot3.png](images/screenshot3.png)
