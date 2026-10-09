# combat

Moved out of `CLAUDE.md` verbatim on 2026-10-09 (PLAN.md 0.5 / F12). Sections:

- Combat / Weapon System
- Glass breaks like a car's: shops, stations, mission and gang buildings, trains (PLAN.md 1g g, 2026-10-07)
- Platform ladders, CS 1.6 style (user 2026-10-07)

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

### First person shoots from the eye; third person keeps both legs, no forgiveness (2026-10-09, user decision)

`FirearmItem.eyeTraceInFirstPerson` (on): in first person (`Character.isFirstPersonView()`, FPS or scoped) a shot is
ONE leg from the camera, the CS / L4D rule -- the camera is the eye, so a wall in front of the gun is in front of the
eye too, and the muzzle leg there only stopped shots on corners and shelf edges the player could plainly see past.
Third person keeps the two-stage trace with NO near-muzzle forgiveness (user: forgiveness would let a player hide the
character behind a wall and shoot from the camera). Gate `probe_muzzle_blocked.gd` (`--fps-control` fails the FPS
case); probe_self_hit, probe_fps_camera, probe_sniper_hits, probe_hit_marker, run_net_shot_test PASS.

**Moving the TPS aim camera closer was measured, not done** (`tools/godot/shot_aim_camera.gd`, display): the aim
camera (Combat.tres: distance 1.0, shoulder 0.35, height -0.3) already sits 0.13 m above and 0.23 m beside the muzzle
on Shino, 1.75 m behind it. Shoulder 0.35 / 0.25 / 0.15 / 0.05 gives a 0.23 / 0.16 / 0.12 / 0.13 m gap between the
camera's line and the gun's line 1 m past the muzzle -- diminishing, because the distance behind does not change --
and at 0.15 the character's back covers the gun and the target in the middle of the screen. The remaining TPS levers
are a pose lift over low cover (GTA / TLOU) and a cover system that pops the gun clear of the lip (Gears).

### The crosshair says when the muzzle line is blocked (PLAN.md 1d, 2026-10-09)

The two-stage trace is right that cover the camera sees over or past still stops the round at the gun -- but with
no feedback "I shot over the shelf and nothing happened" read as a bug. `FirearmItem.muzzleBlockedPoint()` re-asks
the shot's own two legs (sight point, then `resolveShotOrigin` -> sight with `trace`) and returns where the round
would stop when that is more than `BLOCK_SLACK` 0.6 m short of the sight point (null when clear, scoped or seated).
`Crosshair` asks it once a frame for the local player's held firearm: the reticle dims to `blockedAlpha` (0.35) and a
small × is drawn where the round will land (Arma / The Division / Gears) -- the one HUD hint the minimal-HUD rule
allows here. `showBlocked` off is the control. Gate `tools/godot/probe_muzzle_blocked.gd` 6/6 (`--control` fails 3);
on Shino the combat camera is only ~5 cm above the muzzle, so the gate uses a post ON the muzzle's line that the
over-the-shoulder camera sees past (the same code path as a shelf).

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

**Firearm damage is CS 1.6's** (user 2026-10-08: "an assault rifle kills in 1-2 headshots in CS, here half a
magazine"). It had been ~half (ASR1 20: two headshots, five chest hits). Now ASR1 36 (AK), ASR2 33 (M4A1), SMG1 22,
PIS1 25, DUP1 28, SHG1 20 x 8 (M3), PIS2 55, REV1 70, SNR1 150, in `weapon/stats/<id>.tres`; the bone multipliers
are unchanged, so chest 3 hits, legs 6. **Headshots (user, same day): two for most guns, ONE for the AK, the hand
cannons and the sniper** -- `WeaponStats.headshot_scale` scales a head hit before the x4 (FirearmItem.resolvePellets):
ASR1 144 (one-tap; the AK's identity), ASR2 0.7 -> 92 (CS's M4 against a helmet), SMG1 88, PIS1 0.9 -> 90, DUP1 0.85
-> 95, a SHG1 pellet 80; PIS2 220, REV1 280, SNR1 600 one-tap. Gate `tools/godot/probe_headshots.gd` 14/14
(`--control` = every scale 1, fails 3). The player has 1000 HP, so AI
fire on the player rose with it. Glass `PANE_PIERCE_AT` went 20 -> 30 so pistols, SMGs and buckshot pellets still
stop in a window and rifles still carry on.

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
**A puppet is never on the floor by its own test** (it never runs `move_and_slide`), so the owner's floor state rides
the flags word as bit 13 (`SNAPSHOT_FLAG_AIRBORNE`, `Character.isAirborneNow()` / `replicatedAirborne`), and
`AnimationController` asks that. Without it every remote body stood in the airborne blend (arms 0.2 m wider and
0.15 m higher than on the host), and `run_net_shot_test`'s pellet agreement read 63/80; with it 78/80. The same rule
holds for anything else a puppet would read off its own physics.

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
- **A defeated driver stays in the seat, GTA-style, and the car BRAKES to a stop (PLAN.md 0.2, 2026-09-14; user
  decision: "stay seated", not eject — confirmed again 2026-09-28, after a fall-out-of-the-door version was built and
  dropped as more to replicate and test for no gain). Since 2026-09-28 `Vehicle.hasDefeatedDriver` holds the brake
  (no throttle or steer) until 0.3 m/s, then lets the car park: 22.7 m/s to rest in 2.3 s over 25 m, where coasting
  took far longer.** An ambient car's brain is on the VEHICLE (Design B), so killing the
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

## Glass breaks like a car's: shops, stations, mission and gang buildings, trains (PLAN.md 1g g, 2026-10-07)

**One rule for every window** (user: "update the glass behaviour like car"), the car's own
(`VehicleDamageRules.PANE_PIERCE_AT` 30): ordinary glass gives ONE hit of protection -- a light round, a melee blow, a
crash (a car above 3 m/s, `Vehicle.crashedPanes`) or a blast (`GlassPanes.blast`, from `ExplosionManager`) breaks it and
stops there; a round of 30+ breaks it and carries on at full damage; a broken window lets everything through. The bullet
half is `WeaponItem.throughGlass` (cars, then building panes up to three deep, then train windows); AI sight passes an
intact window (`AICharacter.seenPastGlass`).
- **Buildings** (`build_building_scenes.gd`, ENTERABLE variants only -- `_Shop` / `_Open`; a shut building keeps its
  glass solid, user decision): every connected island of `MI_GlassClear` in a library / interiors / stations / shops
  piece is its own pane, INTERIOR glass included, one piece per window (user: "each glass a separate piece"; an artist
  separating glass in Blender keeps it separate here for free), plus the downtown kit's shop windows with their 目隠し
  strip. A pane is a PLAIN StaticBody3D (WORLD layer, `IntactVisual` mesh embedded in the scene, `Glass` box) under ONE
  `world.PaneSet` script per building (`Panes` node) -- the DepartmentStore has 1266 windows and a JVM-scripted node
  each would hitch its cell. The wall's collision box is cut through its whole depth at each pane (`_aabb_minus`), the
  trimesh collider skips the glass. Islands under 0.05 m2 stay in the shell. Breaks are host-authoritative, replicated
  by `WORLD_EVENT_BREAKABLE` keyed `<PaneSet path>#<index>` (`PaneSet.applyRemote`) with a late-join baseline; a pane
  is whole again after 180 s. Cost: DepartmentStore_Shop is a 3 MB text scene (164 ms parse on the loader thread, 15 ms
  instantiate). Counts: konbini S/L 17/28, family restaurant 30, supermarket 26, police station 42, Central 480.
  Gang places with see-through glass: AdultServices, SecureMansion, WarehouseYard; GangOffice / PortCompound /
  Scrapyard placeholders have only opaque `MI_Window` (art), Pachinko is shut.
- **Trains** (`world.TrainWindows`): each EMU1 car's `M_Train_glass` surface is split ONCE per model into its
  window islands (11 per car), the surface hidden and every window its own `Win<n>` node; the car keeps its box
  collider and `TrainSystem.windowAt` says whether a hit point is on a window. Past a window the round crosses the car's
  inside (3.2 m) and stops in the far wall unless it meets someone. Broken windows are kept per set (cars are rebuilt
  with the camera) and are cosmetic, local per peer. Door-leaf glass is not split.
- Gates: `tools/godot/probe_shop_glass.gd` (DebugWorld konbini: a pane stops a ray, a hit opens it, restore closes it,
  heavy round carries on / light stops, a hostile shoots the window out; `OW_NO_GLASS_SIGHT=1 ... -- --control`),
  `tools/godot/probe_train_glass.gd` (heavy/light/open window on a real car), `probe_station_paid` per station.
  `WeaponItem.probe_shot` is the probe readout (one round through the real trace + glass rule).

## Platform ladders, CS 1.6 style (user 2026-10-07)

Somebody on the track bed climbs back onto the platform by a vertical ladder: `world.Ladder` (an Area3D, mask
CHARACTER, `top` = the ledge over its origin, its -Z INTO the face) on every TRACK-FACING edge of every platform,
`LADDER_INSET` 2 m in from both ends (`tools/station_layout.py ladders` -> layout `ladders` -> `build_building_scenes.gd
_add_ladders`, a yellow rung mesh 2-5 cm off the face, inside the ~6 cm the train's gauge leaves). Inside its volume
`MovementController`'s ladder branch replaces gravity. **Grabbing is on INTENT, never on contact** (2026-10-08; the
volume reaches 0.2 m onto the platform, so contact grabbed a body walking the edge and held it with no gravity): walking
INTO the face within `LADDER_GRAB_DEG` 40 deg from below the ledge grabs it (Source / L4D / Apex / Fortnite), and the
interact key grabs it from anywhere in the volume, from the ledge too (the body is set on the face just under the top,
ready to climb down -- the only way down that is not a jump). `ladderAutoGrab` (`@Export`, on) off = the interact key
only (Battlefield / Tarkov). On it (user, 2026-10-07): FORWARD climbs UP, BACK climbs DOWN, no input hangs, the view's
pitch plays no part, sideways slides, at `LADDER_SPEED` 2.5 m/s; over the top forward carries the body onto the ledge
and lets go; at the foot back steps off; jump (`ladderJump`) or interact (`ladderUse`, `UserCommand.useLadder`) lets go,
no re-grab for 0.5 s. No animation. AI uses the same branch (it grabs by walking into the face; its nav does not path to
ladders yet). A ladder also lets a fare-dodger onto the platform, as in life. Gate `tools/godot/probe_ladder.gd
[-- --control]` 16/16 (DebugWorld station A: up onto the platform, forward climbs while looking down, no input hangs,
back climbs down and steps off, jump lets go, walking along the bed or the platform edge grabs nothing, interact grabs
from the top and back climbs down, interact lets go, auto-grab off; control: no ladder, stays on the bed).

