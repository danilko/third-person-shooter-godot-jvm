# animation

Moved out of `CLAUDE.md` verbatim on 2026-10-09 (PLAN.md 0.5 / F12). Sections:

- Animation — the export pipeline, the Root-bone rule, and how to MEASURE it (2026-09-07)

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
Player because both want WASD). Keys: `1/2/3` stance, `4` combat, `Q/E` the WEAPON (rebuilds the mannequin armed with the next catalog gun; it carries one, so a slot change showed nothing), `F` fire (through `UserCommand.fire`, so the
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
The sign now MEANS something (positive = right shoulder) instead of being absorbed by a flip. **Since 2026-10-04 the game ships the RIGHT shoulder** (the gun side; all three states positive). The off side is measured by `tools/godot/probe_shoulder_view.gd` (display): on Shino with ASR1 the right shoulder shows 55% of the gun and the left 12%. `CombatState.cameraLeftShoulderExtra` / `cameraLeftHeightExtra` (sideways / height, left shoulder only) do not help a long-haired body: 0.2-0.5 m wider stays at 10-12%, and higher only drops her out of a level view. Both ship 0.

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
**384x128** frame (since 2026-10-08 `align` "left": the muzzle on the left padding edge, and the HUD boxes draw it top-left at a smaller height) and FITTED to it with 6 px padding (`scale` "fit"). Fit, not true relative size, is the HUD
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
  red and held twice as long on a kill, larger on a headshot, with a tick sound (`assets/audio/hit_marker`, silent until the file exists).

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
- **Auto-Rig Pro was not used.** Its Remap would do the same job interactively, but it is driven by
  scene/UI state, so it is not a reproducible build step. Converting the rig to ARP/Rigify would
  rename the bones every modifier and the Java address — the deform skeleton is already a game
  skeleton; keep it.
  **CORRECTION (W48, 2026-09-20): "it fails to register (draw-handler errors)" is no longer true and
  should not be quoted.** Re-measured under `blender -b`: `auto_rig_pro` and
  `auto_rig_pro_quick_rig` are both `enabled=True loaded=True` and register **185 operators**
  (`bpy.ops.arp`), plus `arp_export_scene.fbx`. Whether its rig GENERATION completes headless was
  not tested. The reasons not to adopt it stand on other ground — see W48.
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

### W46 — THE EYE KEEPS UP WITH A STANCE CHANGE, AND A HOLSTER IS DERIVED ON EVERY BODY (2026-09-20)

Two of the three open per-body items, and both were a measurement that had ONE owner too few.

**1. The FPS eye lagged a stance change, and the filter was working exactly as designed.** W5 splits the
neck mount's motion into a slow average (`baselineFollow`, 6/s) that IS the resting eye point and a
scaled, clamped residual that is the bob. That is right while the rest point is STILL — and a crouch
moves the rest point itself **~0.33 m in ~0.17 s**, so the filter correctly classified the whole of it
as "fast", clamped it to `maxBoneOffset` (0.08 m) and admitted a quarter, leaving the 6/s baseline as
the only thing that could travel the distance. Measured before: the camera sat **0.23 m** below the
true eye at the frame the body had already arrived, and took **0.55 s** to come within 2 cm — the head
finishes standing and the view is still crouched.

- **A rate, not a snap, and for a measured reason:** the head has not moved yet on the frame the stance
  changes (the animation blends over the frames after it), so a snap on the signal frame catches up to
  the OLD pose and then lags exactly as before. `stanceFollow` (30/s) replaces `baselineFollow` for
  `stanceCatchUpSeconds` (0.35 s) — a touch longer than the transition, no longer.
- **30 is the knee, and past it the bound is something else.** Swept: 0 (the control) settles in 34
  frames, 30 in 15, 45 in 14, 60 in 13 — because at 30 the baseline's time constant (33 ms) is already
  under `positionSmoothing`'s (40 ms), so a faster baseline buys a frame and admits more bob for it.
- **Read, never latched.** The window opens on the character's own `getStanceOrdinal()` changing, not on
  a `changed_stance` connection: "which stance am I in" already has one owner, a signal would have to be
  added to every character scene and could then be missing from one of them, and this way a body
  re-stanced by replication or by a script gets the same treatment.
- Gate: `probe_fps_camera.gd` case 5 (2 new checks) — at the frame the body has arrived the eye is
  within 0.12 m and within 2 cm by frame 20, asserted against the MOUNT rather than an expected height,
  because where the true eye is is a fact about the body (W41). Measured after: **0.07/0.09 m** and
  frame 14/15. `-- --control` sets `stance_follow` 0 and fails exactly those 2 (0.22 m, frame 33/34).

**2. Every holster socket is derived now, by ONE rule: keep at least the clearance the REFERENCE keeps,
from BOTH surfaces, AT EVERY HEIGHT of the band the weapon hangs in.** The hip pair was the last
transferred number in `measure_body.gd` (the reference's authored transform scaled by thigh-BONE
separation, which is not skin width), and the back slings were designed afresh on each body against one
band of its upper back. `probe_weapon_holster.gd` failed **5 checks on Shino and 7 on Fumiriya**.

Four things had to be true at once, and each was a wrong answer first:
- **The arms are not the waist, and they are exactly where the waist is.** Every skin reading is taken
  standing with the arms DOWN, so the widest thing in a sideways wedge at hip height is the HAND hanging
  beside the hip: measured **0.282 m** on the reference, where her waist is ~0.15, and the derived
  clearance came out NEGATIVE on three of four sockets — "the authored holster is inside the body",
  which it is not. A vertex is waist skin only if the bone that owns it is not below a collarbone.
  (W24's shoulder column finding the forearm, from the other side.)
- **There are TWO surfaces and a holster has to clear both.** The SKIN is what a player sees a pistol
  rest against; the CAPSULES are what everything at runtime treats as the body — bullets, and this
  gate — and W41 sizes each from a percentile of the skin around ONE BONE, so a round capsule
  legitimately bulges past a slim waist while a skin reading legitimately reaches past a capsule at the
  hip. Against the skin alone, Fumiriya's PIS1 came out **30.7%** inside his spine capsules; against the
  capsules alone, the reference's own two rear-hip sockets sit **3–5 cm INSIDE** them, so carrying that
  clearance put a knife deep inside a narrower body. Neither is "the surface".
- **A single number per surface is not enough either.** Fumiriya's widest point in the band is his
  THIGH, 12 cm below the socket, where a pistol is already past the body — so matching that clearance
  still left the gun 2.3 cm inside his spine capsules. The clearance is carried **per slice** (27, 1 cm
  apart), by the slice's own offset from the socket, and the slice that binds on this body decides.
- **The band is where the weapon HANGS, not where the socket is.** A holstered weapon hangs by its
  GRIP, so it reaches well below the socket and barely above it: 0.20 m down / 0.06 m up at the hip,
  0.60/0.30 for a long gun on the back.

**The back slings go through the same rule**, with the reference's own design as the thing reproduced
rather than a fresh design per body — one rule for every holster socket. Measured: Fumiriya's SMG1 was
13.8% inside his spine and shoulder capsules because a sling clear of his upper back is not clear of his
lumbar curve.

**The gate learned the same lesson it taught.** Its poke test counted the ARMS, which is the one part of
the body a belt holster is expected to be under and which no static placement can clear — measured, a
knife correctly on Shino's right hip reads **0.072 m** inside her hanging forearm while the deepest it
reaches into her torso and legs is 0.023 m. Arm hitboxes are excluded from the judgement and reported on
their own line, because a weapon buried in a SHOULDER would still be wrong.

**The reference reproduces itself exactly** — the four hip sockets to the last rounded digit, positions
identical — which is the property the whole file is built on (W41).

Gates: `probe_weapon_holster.gd` **PASS on all three bodies**; `measure_body.gd -- --control` puts the
bone-separation transfer back and fails 2 on Shino / 1 on Fumiriya. Unchanged: `probe_weapon_fit` PASS
on **3 bodies x 4 stances** (the matrix W44's regression made mandatory), `probe_character_visuals`
10/10 on each VRoid body, AimDebugAuto 40/40, `probe_shared_anims` 2/2, `probe_body_contract` 3/3 each,
`probe_melee`, `probe_support_hand_ik`, `probe_self_hit`, `probe_switch_spin`, `probe_crawl_balance`,
`probe_weapon_{sockets,archetypes}`, `probe_vehicle_views`, `probe_sniper_scope`, `probe_scope_sway`
PASS; `./gradlew build test` green.

**Measured away, not built: the `shotgun` grip archetype (PLAN.md 6.12).** W45's new upright aim pose
plus W44's clavicle protraction closed the reach on their own — Shino now measures **SHG1 0.035 m** and
**SNR1 0.002 m** against a 0.05 tolerance, where 6.12 was written against 0.105 and 0.065. What is left
is a LOOK question: SHG1 passes with her support shoulder pinned at the 40 deg protraction cap, so a
shotgun-specific bladed hold would give the headroom back — and that is an AUTHORED pose. The empty
slot was deliberately NOT created: W45 item 11 had just retired the `sniper` split because a
placeholder archetype is four more clips to keep in sync and the sniper's had silently diverged twice.

### W47 — THE CROUCH AIM POSE REACHES THE GAME, AND A STANCE DROP IS NOT ABSOLUTE METRES (2026-09-20, user-asked)

Three user reports, one session, and two of them were a pose or a key that had nowhere to go.

**1. THE CROUCH AIM BRANCH HAD NEVER BEEN WIRED, so an authored crouch pose could not show.**
`crouch_aim_pistol` / `crouch_aim_rifle` have been exported and ORPHANED since W10 — crouch aimed
from the UPRIGHT archetype clips, which is why W24 measured "the crouched upper body identical to
upright". W45 built the mechanism for crawl (`AimStanceTransition`) and only crawl used it. Now:
- `WeaponAimCrouch`, the crouch copy of the 10-point archetype blendspace, on a third
  `AimStanceTransition` input; `AnimationController` drives it from the stance's own animation key
  (`AIM_STANCE_BRANCHES`, so adding a stance is one set entry, not a new branch in an `if`).
- **The TORSO layer needed the same dimension, and crouch is the first stance where that shows.**
  `WeaponTorsoBlend` takes `spine_03`/`neck_01`/`head_2` from `WeaponAimTorso`, which is its own copy
  of the archetype blendspace (a node's output feeds ONE input — W23). Wire only the arm layer and a
  crouching body reads its ARMS from the crouch pose and its SPINE from the upright one. Crawl never
  showed it because `Stance.weaponTorsoLayer` is off there, so the layer does not run at all. So
  there is now an `AimStanceTorsoTransition` (Default / Crouch) as well. Measured: head-to-stock in
  crouch went from `right -0.179` to `-0.127`, against upright's `-0.131`.
- The 8 unauthored archetypes are minted placeholders (`crouch_aim_<arch>`, copies of their upright
  twins) so every point is a wired, editable slot; the two AUTHORED ones are deliberately NOT listed
  in `character_anim_naming.json`'s placeholder map, because a row there is a mint source and
  `--refresh-placeholders` over an authored pose overwrites it.

**Measured, the artist's pose now reaches the game and it costs the support hand.** The clip itself
differs from the shipped one by about **7 deg of `spine_03`** and nothing else. In game the blade
falls **44.5 -> 29-31 deg**, the head comes over the stock — and `probe_weapon_fit --stance=crouch`
FAILS on all three bodies: the support hand sits **0.060 m** (ASR1), **0.083** (SNR1) and **0.116**
(SHG1) off its grip, against a 0.05 tolerance. The cause is in the pose and is one number: it holds
the palm **0.312 m** in front of the shoulder joint where the upright pose holds it at 0.215, so with
the stock seated on the shoulder anchor (measured: stock-to-pocket 0.001 m, gun on the aim line) the
`SupportPoint` ends up **0.485 m** from a **0.416 m** arm, with the protraction already pinned at its
40 deg cap. **That is a kneeling shooter holding the rifle at arm's length rather than tucked**, and
it is authored work, not code: bring the firing hand in toward the chest and the support hand
follows. Shipped live rather than held back, because a gate reporting "the support hand is 6 cm off
the gun in crouch" is the gate doing its job, and the alternative is a pose that cannot be seen.

**2. "IS THE RAISED KNEE ON THE WRONG SIDE?" — YES, AND THE FIX IS TO MIRROR THE LEGS, NOT THE UPPER
BODY.** Measured on `crouch_idle`: `calf_l` sits at **0.163 m** (the knee down, near the ground) and
`calf_r` at **0.433 m** (the knee up), with the left foot forward and the right foot back. So the
body kneels on its **LEFT** knee with the **RIGHT** knee raised. For a right-handed shooter the
standard kneeling firing position is the opposite — kneel on the RIGHT knee so the LEFT (support)
elbow can rest on the raised LEFT knee — so this clip is the mirror of it, and the raised knee is
under the FIRING arm, which is what reads as wrong.
- **Mirroring the UPPER body is not the fix**: it would put the weapon in the left hand, and every
  socket, mount anchor, holster and IK target in the codebase is authored for a right-handed hold.
- **DONE, as an X-flip of the whole crouch LOCOMOTION ring** (user's call: "flip all animation in
  crouch with x-pose flip in blender"). `pose_weapon_hold.py flip` is new and is Blender's
  "paste X-flipped pose" over a whole clip: where `symmetrize` averages each bone with its partner's
  mirror to make a pose symmetric, this takes the partner's mirror OUTRIGHT, so left becomes right.
  Same `mirror_basis` reflection, so whatever W26 established about one holds for the other, and
  `Root` is excluded for the same reason (it carries the stance DROP, and mirroring a drop is a
  no-op). Measured on every clip: the hip yaw and the knee asymmetry reverse sign with the magnitude
  unchanged and the cycle's own peak-to-peak untouched -- which is what says it is a mirror and not
  a re-pose. `crouch_idle` is now `calf_l` 0.433 UP / `calf_r` 0.163 DOWN, the exact swap.
- **A DIRECTIONAL clip must be flipped AND EXCHANGED with its partner, not flipped in place.** All
  nine points of `CrouchMovementBlend` are wired, and an X-flip of `crouch_walk_left` IS a
  right-strafe -- left at the blendspace's LEFT corner it would strafe the wrong way. So
  `--action` takes `dest=src`: `left=right`, `right=left`, and the same for both diagonal pairs,
  with every source read BEFORE anything is written or the first write destroys the second's source.
  Measured: `crouch_walk_forward_left` keeps its -39.7 deg hip yaw (it still turns left) while its
  knee asymmetry takes the mirrored right clip's -0.338. `crouch_idle`, `_walk_forward`, `_walk_back`
  and the three orphans flip in place.
- **The aim poses are NOT flipped**, and that is the whole point: the legs move to the correct side
  and the authored right-handed upper body stays as it is.
- Nothing moved in any gate: AimDebugAuto 40/40 (its two crouch strafe cases included),
  `probe_character_visuals` 10/10 on each body, `probe_melee`, `probe_crawl_balance`,
  `probe_fps_camera`, `probe_shared_anims` PASS, and the crouch fit failures are unchanged at
  3 / 4 / 1 -- they are the aim pose's reach, not the legs.

**3. A STANCE DROP IS ABSOLUTE METRES, AND `Skeleton3D.motion_scale` IS GODOT'S OWN ANSWER.**
User-reported: "beside godot chan, other models float in the air when shooting in crawl". Measured,
the foot (`ball_l`) in `crawl_idle`: reference **0.163 m**, Shino **0.334**, Fumiriya **0.525** — the
taller bodies lying a third of a metre above the ground. W40 keeps position tracks only on `Root` and
`pelvis` precisely because everything else is a fact about the body, but those two are still metres
authored on a 1.49 m reference, and the biggest of them is the stance drop: `crawl_idle` takes `Root`
to -0.601 and `crouch_idle` to -0.289 whoever plays it.
- `Skeleton3D.motion_scale` multiplies exactly those animated positions — it exists to retarget
  position tracks onto a differently-sized skeleton — so the fix is **one property per body**, no
  modifier, no per-frame work and no second copy of the library. The scalar is the body's own
  **pelvis rest height over the reference's** (Shino 1.219, Fumiriya 1.4788): the drop is the pelvis
  travelling from standing to prone, so it scales with the leg. Derived by `measure_body.gd`, written
  by `build_character_visuals.gd`, 1.0 on the reference, which is therefore untouched.
- **Measured after: crawl foot 0.334 -> 0.202 and 0.525 -> 0.237**, against proportional targets of
  0.199 and 0.241 — within **4 mm**.
- **W41 was right about CROUCH and wrong about CRAWL, and now there are numbers for both.** Its note
  rejected leg-length scaling because "the leg rotations fold a longer leg further by themselves".
  That is true of a FOLD and not of lying down: crouch over-corrects, the two VRoid feet landing
  **0.022-0.030 m BELOW** the floor where they used to float 0.060-0.128 above it. A sink of 3 cm is
  hidden by the ground and a float of 13 cm is not, so the derived scalar ships as it stands rather
  than being tuned to a compromise neither stance asks for. **Foot grounding remains the exact
  answer** and is now a smaller job: it has to cover a 3 cm fold error, not a 36 cm one.
- The capsules are re-derived with it: `measure_body.gd` sets `motion_scale` on its own rig BEFORE
  any reading, or a stance capsule would be a capsule for a pose the game never holds.
- **Measured as the lowest skinned VERTEX, which is the question actually being asked** (the foot
  BONE is a proxy): upright -0.006 / +0.000 / +0.001, crouch -0.012 / **-0.064** / **-0.079**,
  `crawl_idle` **-0.078** / -0.013 / +0.030, `crawl_forward` -0.016 / -0.001 / -0.010. So in crawl
  the two VRoid bodies now sit CLOSER to the floor than the reference does -- her own `crawl_idle`
  has put her 7.8 cm through it since it was authored, which is a fact about that clip and not about
  this fix.

**Two tool defects found on the way, both silent and both fixed or recorded:**
- **`rename_character_anims.py` died on a `_comment` key** in the placeholder map ("source ...
  missing" — the value is a sentence, not a clip). W45 added that key and nothing re-ran the tool
  since, so the very first placeholder pass after it failed. It skips `_`-prefixed keys now.
- **`tools/godot/study_character_pose.sh` HAS BEEN STALE SINCE W40 and reports the SHIPPED pose.** It
  re-points a scratch scene at a scratch `.glb`, which was the whole story when the body's own export
  carried the clips — but the AnimationTree now loads `character_anims.res`, so the study measures
  the shipped library whatever is in the blend. Caught by a control: a copy with **+25 deg** of blade
  applied to `crouch_aim_rifle` measured byte-identical to the unmodified one (support 0.060 and
  0.116, to the millimetre). Anything that studies a CLIP edit must rebuild the library too
  (`tools/godot/build_character_anims.gd`) or point the study scene's tree at a scratch one.

**THE POSE WAS RE-AUTHORED THE SAME DAY AND THE STRETCH IS GONE** (user). The support arm is
0.416 m and the first pose put its target **0.459 m** away — past the point any solver can close, so
the protraction pinned at its 40 deg cap and the hand still hung short. The re-authored pose puts it
at **0.253 m**, the same as upright's, and the in-game grip miss went **0.060 -> 0.002 m** with
`--stance=crouch` PASSING on all three bodies. It keeps what a kneeling pose should differ in — gun
pitch -22.3 deg against upright's -10.9, firing elbow flare +46 against +34, the head lower over the
stock — while matching upright on the one number that was breaking it. The lesson is the number to
check first when a shared aim pose "stretches": **`SupportPoint` from the support shoulder against
the arm's own length**, which `pose_weapon_hold.py measure` prints per weapon.

**THE UNREACHABLE AIM CLIPS ARE DELETED, AND THE RESERVED INDICES PLAY THEIR BASE POSE** (user:
"remove these unused ... so at least artists know which one to fix"). Four grip archetypes have no
shipped weapon — `dual_pistol`, `shield`, `shield_melee`, `sniper` — and each carried five clips
(aim standing / kneeling / prone, hold, draw): **20 clips no weapon could reach**, every one a copy
of another pose. That is precisely the thing W45 item 11 retired the sniper split over, because a
copy nobody can reach goes stale in silence, and the sniper's had already diverged twice.
- **The INDEX LIST IS UNTOUCHED** (W12: it is append-only, and a scene stores the archetype by name
  whose ordinal is the blendspace position). What changed is what those four points PLAY: their
  `base`, which `weapon_archetypes.json` already declares (`dual_pistol`/`shield`/`shield_melee` ->
  pistol, `sniper` -> rifle) — and which is exactly what the deleted copies were. So the render is
  unchanged, measured: `probe_weapon_archetypes` still finds **4 hand-pose clusters**.
- Their placeholder rows are gone from `character_anim_naming.json` and the names are in its
  `delete` list, so a re-run cannot mint them back. 187 -> **167 clips**, tree refs 81 -> 71.
- **`check_character_anim` prints the artist's list now** (`aim_coverage`): per family, which
  archetypes have a pose of their own and which share, plus the reserved four. Today that is six
  archetypes — pistol, rifle, launcher, melee, fist, throwable — across five families, i.e. the 30
  poses an edit can actually change something with, down from 50.

Gates: `probe_weapon_fit` PASS on **3 bodies x 4 stances**; `probe_weapon_holster` PASS on all three;
`probe_character_visuals` 10/10 each; AimDebugAuto 40/40; `probe_melee`, `probe_support_hand_ik`,
`probe_crawl_balance`, `probe_switch_spin`, `probe_shared_anims`, `probe_weapon_archetypes` PASS;
`check_character_anim` 187 clips with only 6.16's four pre-existing `gun_travel` errors.

### W48 — THE CONTROL RIG WAS UNUSABLE FOR THREE REASONS, AND RIGIFY GENERATES HEADLESS (2026-09-20, user-reported)

User: "the IK shape is not visible to easily perform IK tweak of bones, mostly still through FK for
the entire body." Diagnosed rather than guessed at, and it was three separate things.

- **Turning IK on was four constraint influences on four different bones, all at 0.** W42's
  influence-0 default is right and is unchanged — an IK constraint at full influence OVERRIDES the
  chain's rotation channels, so a rig stored with it on would silently replace the arms and legs of
  all 167 shared clips. But a control that does nothing when you grab it is indistinguishable from a
  control that is broken. `CTRL_root["ik"]` is one slider in the N-panel now, 0..1, driving all four.
- **The widgets were 6–11 cm on a 1.5 m body.** Hand 0.09 -> **0.144**, foot 0.11 -> **0.176**, pole
  0.06 -> **0.10**. And `widget()` returned an existing mesh WITHOUT re-sizing it, so a change to
  those numbers reached only a body built from scratch; it re-sizes in place now, and leaves a mesh
  an artist has reshaped (anything but its own 8-vertex cube or 6-vertex diamond) alone.
  **CORRECTION (2026-09-21): those are MESH sizes and they were not the drawn sizes**, so this half
  of the fix bought almost nothing — see "The control you can see" below.
- **Only four chains exist — arms and legs.** Nothing for the spine, chest, head or fingers, which is
  the "FK for the entire body" half and is NOT fixed here. See the Rigify note below.

**Three defects the fix surfaced, and the first is this file's own recurring shape:**
- **A DRIVER TAKES OWNERSHIP OF THE INFLUENCE.** Adding the switch broke the tool's own
  shoulder-recruitment self-test instantly: it set `con.influence = 1.0`, the driver put it back to
  the property's 0, nothing solved, and the check reported "clavicle_l did not follow the hand" —
  a true statement about a rig that was not solving at all. `set_ik()` is the ONE writer now, and
  the artist-facing GRAB/BAKE text block carries its own copy, because it runs in its own scope.
- **Once the IK actually solved, the stored pole angles turned out to be garbage** — **-185 deg** on
  all four chains, the value a search produces when the thing it is searching never moves. Re-solved:
  -58 / -60 / -60 / -128, elbow residual 0.0006–0.0103 m, and `CTRL_hand_l reached -> clavicle_l
  turned 23.1 deg, hand 0.002 m short`, which is W45's own recorded figure reproduced.
- **The envelope check compared a TOTAL against a PER-AXIS bound.** `shoulder_limits` sets
  `ik_min/max_{x,y,z}` to ±`CLAV_LIMIT_DEG` — a limit on each axis independently — while the check
  tested the channel's total magnitude, which three legal axes reach **sqrt(3) x the limit** (~104
  deg at 60). It had only ever passed because the left arm happened to land at 60.1; the right
  measures **98.7** with every axis inside its envelope. An XYZ Euler decomposition is not the
  solver's parameterisation either (it put 77 deg on x for that same rotation), and Blender does not
  expose the solve's per-DoF angles — so what is asserted is what is OBSERVABLE: the envelope is
  configured (read off the bone), and the total stays under `MAX_TOTAL_DEG`. The feature itself is
  the `reached` case, which is a measurement and not a configuration.

Unchanged by all of it: **POSE UNCHANGED AT INFLUENCE 0, worst bone 0.000000 m over 477 samples**,
the export still 53 bones / 167 clips, AimDebugAuto 40/40, `probe_weapon_fit` PASS upright/crouch/
crawl, `probe_melee`, `probe_shared_anims`, `probe_weapon_archetypes` PASS.

**ONE FILE, AND THE EXPORT ENFORCES THE SEPARATION** (user: "two files confuse the artist"). A
control rig may live in the clip `.blend` beside the deform armature — an ARP or Rigify rig included
— because three things keep it out of the export and the third is now checked rather than trusted:
control BONES are filtered by `export_def_bones=True` (measured: a `CTRL_` bone comes through as a
54th joint without it), widget objects are in a hidden collection and `use_visible` drops them, and
**nothing may be DRIVING the deform bones**. That last one is the dangerous one: the glTF exporter
samples the EVALUATED pose, so an artist who left the IK switch on would ship every clip with an IK
result welded into it and nothing downstream could tell.
- `export_character.py` now mutes every constraint on the deform armature, hides every OTHER
  armature, and then **measures whether doing so changed the pose**. Unchanged -> export. Changed ->
  it names the bone and the distance and **refuses**, because a file that looks fine is worse than no
  file. Measured: a clean export reports `neutralised 4 constraint(s) ... the pose moved 0.000000 m`;
  with `CTRL_root["ik"] = 1` and a hand control dragged 0.15 m it refuses with `'pinky_01_l' moves
  0.7590 m`, and the `.glb` is left **byte-identical**.
- The deform armature is found through the MESHES (the object of an Armature modifier), not by name,
  so one exporter serves every body and a second armature in the file cannot be mistaken for it.
- Same shape as `export_world.py` unlinking the ground cutters and restoring them, and
  `NavBaker.NO_PED_TOKEN` clearing collision layers for the duration of a parse.

**TWO WORKFLOWS, AND ONLY ONE OF THEM NEEDS A PLUGIN.** Tweaking an existing clip — nudging a pose,
adjusting the blade, fixing a knee — happens on the base rig in the clip file with FK plus the limb
IK that is already there, and needs nothing new; that is what the crouch aim pose edit of 2026-09-20
actually was. Authoring a new pose full-body is the case that wants ARP or Rigify. And the migration
does NOT block the first: the `Root`-metres hazard is about moving an action BETWEEN bodies, so
editing a clip in the file it already lives in is self-consistent whatever body that file is.

**RIGIFY GENERATES HEADLESS, AND W42's OBJECTION DOES NOT APPLY TO A DRIVING RIG** (measured, since
the user asked for Rigify/ARP to be revisited). Blender's bundled Rigify builds its sample metarig
and generates a **706-bone rig with 220 controls** under `-b`; the first attempt that failed did so
under `--factory-startup --addons rigify`, which is an addon-registration artefact and not a limit.
ARP and its Quick Rig are installed and enabled here too; Rigodotify is installed and disabled.
- **W42 rejected all three on bone ROLL** (median 24.4 deg from our rests, which would re-mean all
  167 clips and force a re-conform of both VRoid bodies). That is correct **only for a rig that
  BECOMES the deform skeleton.** The standard integration does not: generate Rigify from a metarig
  fitted to our bones, constrain our 53 deform bones to its `DEF-*` outputs, animate on Rigify's
  controls, and BAKE down to our skeleton for export. Our rests never change, the contract holds,
  and the exported clips are ordinary 53-bone actions.
- That is the answer to full-body IK (spine, chest, head, fingers, IK/FK switching) and it is a
  session-sized piece: the work is fitting the metarig, which is derivable from our rests rather
  than typed, plus the bake step. NOT started.

**SHINO AS THE BASE: the premise is wrong and the conclusion is right** (user asked, on the grounds
that she is the shortest). Measured: **Godot-chan is the shortest at 1.523 m** (Shino 1.645,
Fumiriya 1.908), and height is the wrong axis anyway — a clip is rotations, which are
body-independent, and the only absolute-metre keys are handled by `motion_scale` (W47). What DOES
bind is **shoulder width**, and Shino is **0.2174 m against the other two bodies' 0.2955** — 7.8 cm
narrower. Every reach failure this project has recorded has been hers and nobody else's, so a pose
authored to reach on her reaches on everyone, which is the property a base wants.
- **The migration is cheaper than it looks, because the rests are already conformed**
  (`probe_body_contract`: every clip poses her within 0.06 deg of the reference). Re-home the 167
  actions on her armature (the rotation channels transfer unchanged), scale the `Root`/`pelvis`
  position keys by 1/1.219, flip `REFERENCE_BODY` in `measure_body.gd` and the tools that name her,
  freeze her derived sockets and anchors as authored, and Godot-chan becomes a generated body or
  leaves the repo. NOT started: it moves the foundation every derived number is expressed against.
- **What blocks Shino as the in-game body today is five things**, and only one is code. Measured by
  pointing `Character.tscn` at her and running the game path — `probe_melee`, `probe_self_hit` and
  `probe_weapon_sockets` all PASS, so she fights correctly as the player body, and `AICharacter.tscn`
  inherits the same scene so AI get her and equip weapons through the unchanged path. The five:
  `PedCrowd.PED_SCENE` is hardcoded to `godot_chan/merged_animation.tscn` (one constant, and it
  wants a mixed crowd rather than a second constant); the LOOK (17 MToon-derived materials against
  Godot-chan's 7, and no toon shader — 6.10, gated on 3.14); the 6.4 cm crouch sink (W47's
  `motion_scale` over-correction, whose exact answer is foot grounding); the face morphs and
  hair/skirt motion dropped on import (6.11, deferred by decision); and the FPS collar, which is
  W36's class of problem and **needs a render to judge, not a measurement**.

### THE CONTROL YOU CAN SEE: the drawn size is not the mesh size, and a bone in no collection cannot be hidden (2026-09-21, user-reported)

Two measured defects behind "the control circles cover the model, and hiding CTRL leaves no bones".

- **`use_custom_shape_bone_size` was ON, so Blender scaled every widget by its BONE's length — and a
  CTRL bone is a stub.** Measured on Shino, `CTRL_hand_r` is **0.0191 m** long, so a 0.1348 m mesh
  **DREW AT 2.6 mm**. The drawn sizes were hand **2.6 mm**, pole 7.4, foot 27, root 45. That is the
  whole of W48's "the IK shape is not visible", and W48's own remedy — mesh 0.09 -> 0.144 — moved the
  drawn hand control from **1.7 mm to 2.6 mm**, which is why it did not help. It is off now, so the
  mesh size IS the drawn size: hand **0.097 / 0.090 / 0.099 m** on reference / Shino / Fumiriya.
  **A number that is never compared against the thing it sizes is not a measurement** — W48 quoted
  mesh centimetres and never asked how many millimetres reached the screen.
- **The hand control is sized from the HAND, not from the body.** Every widget was
  `size * WIDGET_GROW * scale` with `scale` the pelvis height, which is right for a foot (a foot
  grows with the leg) and wrong for a hand: measured wrist -> middle fingertip, Godot-chan 0.1616,
  Shino 0.1498, Fumiriya 0.1648 m — within 10% of each other. `hand_span(arm, side)` reads it off
  the rig and `HAND_WIDGET_FACTOR` (0.6) sizes the cube, so the control sits inside the hand and the
  fingers stay visible; `--hand-widget-factor=` takes it lower still.
- **THE CLUTTER WAS NOT A CONTROL AT ALL — every DEFORM bone wore a 19 cm sphere.** The user's
  screenshot settled it in a second where three rounds of reasoning had not: the model was buried in
  spheres while the actual controls were wire cubes off to one side. Measured, `Icosphere` (a 2.0 m
  unit sphere) is the custom shape on EVERY non-CTRL bone of all three bodies — **158 / 53 / 117** —
  scaled by a flat `custom_shape_scale_xyz` 0.08–0.10 with bone-size scaling OFF, so a fingertip and
  the pelvis both drew a **0.155–0.190 m** ball against a finger bone of 0.020–0.037 m.
  `tidy_deform_shapes` turns bone-size scaling back ON and sets the scale so each sphere is
  `DEFORM_SHAPE_FRACTION` (0.5) of ITS OWN bone — **clamped to 0.006–0.060 m**, because a fraction
  alone swaps one absurdity for another: `Root`, `Global` and `Position` are 0.935–1.0 m bones, and
  the first pass gave them **0.500 / 0.567 m** balls, worse than the flat 0.19 it replaced. After:
  every body **0.007–0.060 m**. Reversible (the Icosphere is untouched, two display fields move) and
  `--deform-shape=0` clears the shapes instead, leaving each bone as its own octahedron.
- **158 of 167 bones were in NO bone collection**, so the only thing an artist could switch off was
  the controls. `sort_collections` files every bone into **CTRL** (9), **Body** (the 53 contract
  bones, read from `skeleton_rest.json` rather than a second list) and **Extras** (the rest, which
  on a VRoid body is ~100 hair and skirt spring bones): reference 9/53/0, Shino 9/53/105, Fumiriya
  9/53/64. Hide Extras and the springs go; hide CTRL and the body bones are still there.
- **`head` vs `head_2` is the one recorded name asymmetry across the seam** (W40) and it showed up
  here as one contract bone filed under Extras: the reference `.blend` calls the bone `head` and the
  contract record, dumped from the Godot side, says `head_2`. Both spellings are accepted.
- Re-run on all three bodies with the script's own guard reporting **`POSE UNCHANGED AT INFLUENCE 0:
  worst bone moved 0.000000 m`** (477 / 1422 samples; Fumiriya has no clips to check against, which
  the script says rather than passing silently). No `.glb` was re-exported, so nothing in the game
  moved and no gate could have shifted.

### W49 — SHINO IS THE BODY THE GAME SHIPS, AND THE CLIP LIBRARY LIVES ON HER (2026-09-21, user-asked)

W48 measured the migration and stopped short of it. This is it, and the honest part is which of
Godot-chan's three jobs actually moved.

- **The CLIP OWNER moved.** `blender/tools/rehome_clips.py` (a one-shot, the `import_melee_pack.py`
  contract) imported all 167 actions onto Shino's armature, scaled the `Root`/`pelvis` position keys
  by the pelvis-rest ratio and dropped every other position fcurve — W43's `TRANSLATING_BONES` rule,
  applied at the import rather than at the library build. `shino.blend` is the one file that owns the
  actions now: `build_character_anims.gd`, `probe_shared_anims.gd`, `check_character_anim.py`,
  `build_animation_review.py` and every clip tool's usage line name it. Verified where it matters:
  `probe_shared_anims` 2/2 at **0.000000 m / 0.056 deg** — the shared library poses her own export
  bit-for-bit, which is the only thing a re-home can get wrong.
- **The SHIPPING BODY moved.** `Character.tscn` instances `CharacterVisuals_Shino.tscn`, so the
  player, every AI and every replicated puppet are her, and `PedCrowd.PED_SCENE` is a new
  `assets/characters/shino/shino.tscn` — a scripts-free instance of her export that exists only to
  state the armature's 180 deg turn (W41: a VRoid export faces +Z, the game faces −Z, and a crowd
  written onto an unturned body walks backwards). Gates on her body: **AimDebugAuto 40/40**,
  `probe_weapon_fit` upright/crouch/crawl, `probe_weapon_holster`, `probe_melee`, `probe_self_hit`,
  `probe_support_hand_ik`, `probe_weapon_sockets`, `probe_weapon_archetypes` all PASS.
- **The GEOMETRY REFERENCE did NOT move, and that is a measurement, not an omission.** Every other
  body's sockets, mount anchors, holster slings and clearance profiles are DERIVED from Godot-chan's
  hand-authored ones (W20–W46). Making Shino the reference means deriving from a derivation, and it
  compounds: measured, Fumiriya's rear-hip socket went 0.211 -> **0.329 m** and `probe_weapon_holster`
  failed **17** checks on him. So `measure_body.gd` keeps `REFERENCE_BODY = "godot_chan"` beside the
  new `CLIP_BASE = "shino"` (the only thing `motion_scale` is measured against) and the AUTHORING
  body, which is Shino. Three roles, one constant each, stated at the top of that file.
  **What would let her files go is FREEZING those readings into data** — the per-slice skin and
  hitbox profiles are a function of the query, not a fixed list, so it is a real piece of work with
  its own gate, and it is the named next step rather than something to do quietly.
- **What did leave the repo**: the three adopted pose deliveries
  (`merged_animation_new_{upright,crawl,crouch}_aim_pose.blend`, 29 MB each). Each had been adopted
  into the library, so each was a second owner of a pose that already ships; git holds them.
  `assets/characters/godot_chan/` went **237 MB -> 65 MB** (the rest was untracked `.blend1`).
- **`probe_fps_camera.gd` looked for a node called `head`**, which is a fact about ONE body: Shino's
  head meshes are `Face` and `Hair001`, so the lookup returned null and the probe died on
  `head.visible` — and a GDScript error inside `_initialize` aborts before `quit()`, so it read as a
  HANG, not a failure (13 orphaned Godot processes before it was noticed). It asks
  `MeshConfig.head_mesh_paths` now, which is the list `Character.refreshHeadVisibility` actually
  hides, so the probe tests the thing under test and any body works. **PASS on Shino** (head shown in
  TPS, hidden in FPS and while riding; eye 0.021 m off centre, steadier than the bone).
  Note what this exposes: Shino declares no split neck mesh, so **W36's FPS collar is unjudged on
  her** — it needs a render, not a measurement.
- **`study_character_pose.sh` was stale since W40 and is rewritten.** It assumed a visuals scene
  instances an intermediate body `.tscn`; a generated one ext_resources its body's `.glb` directly.
  It now FINDS the scene by what it instances rather than from a table, so adding a body needs no
  edit, and its default blend is Shino's.

**A PASS BY 2 mm IS NOT EVIDENCE, AND IT IS HOW THIS GATE WENT QUIET.** Every limit in
`check_character_anim.py` is a distance in metres measured on the clip source's own body, so the
same keys measure differently on two bodies. Moving the library to Shino took crawl's placeholder
ring (6.16) from **0.110 m** of gun bob to **0.078** against a limit of 0.08 — four real ERRORs
became silence, with nothing on either run to say the defect was still there. The limit is NOT bent:
`gauge(check, value, limit, msg)` reports a measurement inside `NEAR_FRACTION` (0.85) of its own
limit as a WARN that names the margin. On Shino the crawl ring now says 98%, and the reference export
still FAILs with all four ERRORs, which is the control.

### W52 — SHINO'S CONTROL RIG IS AUTO-RIG PRO (PRESERVE) BEHIND ONE SWITCH (2026-09-21, user decision)

W51's own layer was replaced on `shino` after the user found the arm twisting when the hand control was
dragged back ("with a Rigify / Auto-Rig Pro IK the arm and shoulder resolve correctly"). PLAN.md 6.17 has
the pipeline and numbers. The three rules that make ARP safe in the CLIP-SOURCE file:
- **PRESERVE, never CONVERT:** our 53 bones, rests, names and clips are untouched; ARP's `rig` drives them
  through 312 `COPY_TRANSFORMS`/`COPY_SCALE` from `<bone>_qr_offset`.
- **One switch at 0:** `rig.pose.bones["c_pos"]["drive_game_rig"]` drives every one of those influences
  (`blender/tools/arp/wire_switch.py`). At 0 the clips play and export byte-identically; at 1 ARP poses.
- **Export with the button, N-panel > Game > "Export to Game"** (`blender/tools/game_export_ui.py`): it
  turns every rig switch off, runs `export_character.py`, puts the switches back, and updates Godot.
  `export_character.py` exports from a constraint-free COPY of the armature, because Blender's glTF
  exporter resamples any bone that has a constraint, muted or not (652 channels STEP -> LINEAR, measured).
- **A clip lives on ARP as `ARP_<clip>`** (`blender/tools/arp_clips.py`: move / bake), and the button bakes
  it into the game clip `<clip>` before exporting; an unchanged channel keeps its original keys bit for bit.
  The exporter leaves `ARP_*` actions out and writes no scene extras.
- **The file opens in ARP; the EXPORTER switches it off and back** (`export_character.py` bakes `ARP_*`
  clips, zeroes every rig switch, exports, restores). The bake takes each limb segment's DIRECTION from the
  rig and its TWIST from the clip (on the joint-to-joint line), so an IK conversion no longer wrings a limb
  (70 -> 1.2 deg, measured; unfixed, it re-folded the skirt in game).
- **A clip moves onto ARP's controls exactly only in FK** (0.00 deg; IK retarget guesses the pole: 70 deg).
- **Quick Rig is scriptable only with a window:** `xvfb-run blender` + a timer, and EXEC with invoke's
  class attributes pre-set (`blender/tools/arp/build_limb_map.py`). ARP's source never enters the repo.
- **Five traps the first real edits hit, each fixed in the tools:** an artist keyed the switch itself with
  "key everything", which undid the exporter's switch-off (`arp_clips.strip_switch_keys`, run by move, bake,
  export and a `save_pre` handler); an `ARP_*` action with no user was dropped on save (the handler gives
  them a fake user -- the lost shotgun clip was recovered from `.blend1`); a placed reference gun exported as
  part of the character (the exporter hides every mesh the armature does not deform and every empty that is
  not its parent); and a switch change did not re-evaluate until `update_tag` + a depsgraph update.
- **SHOTGUN is grip archetype 10** (base rifle, append-only): `SocketShotgun`, its own aim clip
  `upright_aim_shotgun` at point 10 of WeaponAim/WeaponAimTorso (`tools/patch_tree_shotgun.py`); every other
  family plays the rifle's clip there. SHG1 uses it.
- **The Blender file shows where the GAME holds each weapon** (`blender/tools/game_weapon_preview.py`,
  collection `GAME_WEAPON_PREVIEW`): a `SOCKET_<X>` empty on `hand_r` at the body's socket with the linked
  weapon models and their SupportPoint/StockPoint/Muzzle. **Moving a socket empty IS the edit:** the export
  writes any socket that differs from the measured one into `<body>.sockets.json`, and
  `build_character_visuals.gd` applies it. Shino's rifle and shotgun sockets are the user's placed guns,
  adopted that way (`probe_weapon_fit` PASS: ASR1 grip 0.000 m, SHG1 0.038 m, stocks seated).
- **An aim clip is authored WITH the butt on the game's shoulder anchor, or the game moves the gun.** The
  preview shows `ANCHOR_StockPoint` (on `clavicle_r`, from the visuals scene's `mount_offsets`). The first
  rifle/shotgun edits held the butt 17 cm behind / 7 cm below (rifle) and 10 cm behind / 31 cm below (shotgun)
  it, so in game `StockMountIKModifier` dragged hand + gun 0.19 / 0.21 m and "Blender and game differ". Both
  clips were fitted by ONE rigid move of both ARP hand controls and poles (bore level on -Y, butt onto the
  anchor), then the left hand onto `SupportPoint`: in-game mount move 0.000 m on both, rifle grip 0.000, shotgun
  grip 0.029 (a pump is past Shino's reach; the shoulder push closes the rest). ARP's `fingers_grasp` does not
  drive Quick Rig fingers: the support hand's finger wrap is still a pose job.
- **Pistols (2026-09-21, user):** the Makarov is gone. PIS1 is Quaternius `Pistol_5` again (the 8eeacbf
  conform, 0.22 m), PIS2 is `Pistol_6` as the large pistol, sized by a Desert Eagle's 0.149 m HEIGHT (0.314 m
  long; by length its grip came out smaller than PIS1's). `blender/tools/import_quaternius_pistols.py` is the
  record. For dual pistols (the reserved `dual_pistol` archetype) `Pistol_1`/`Pistol_2` are the pick: one frame,
  two finishes, the classic 1911 / Beretta shape of CS's Dual Berettas and L4D's dual pistols.
- **Dual pistols are DUP1** (grip archetype 3, `dual_pistol`, now with its own poses; model Pistol_1).
  `weapon.DualPistolItem`: while the item hangs from its hold socket it makes a `BoneAttachment3D` on `hand_l` and
  moves its `ModelLeft` subtree there, at the right grip MIRRORED in rest frames (the relation to `hand_r` is read
  from the node chain up to the hand's BoneAttachment, never `getBoneGlobalPose`, which is pre-modifier). Two
  traps: `reparent()` fires `_exitTree` on every equip/holster, so cleanup runs only `isQueuedForDeletion()`; and
  the collider stays ONE gun wide (a pair-wide box read 12% inside the body when holstered). The muzzle flash
  alternates; shots come from the right gun. The poses are the pistol poses with the right arm chain X-flipped
  onto the left (`blender/tools/make_dual_pistol_clips.py`; the carry swings the arms out 31 deg first), wired at
  point 3 by `tools/patch_tree_dual_pistol.py`. `probe_weapon_archetypes` now expects 5 hand clusters.
  **The left barrel is aligned every frame, not left to the mirror** (`alignLeftBore`, on): the aim modifiers
  turn both shoulders by the RIGHT gun's correction and the mirror doubles it on the left, so the left barrel sat
  **9.7 deg outward**. It is now turned about its own grip PARALLEL to the right one (0.00 deg);
  `toeInDeg` (default 0) turns it inward to converge. Gate `tools/godot/probe_dual_pistol.gd` (`--control` =
  align off, fails at -9.69; `--toe-in=2.5` reads +2.50 inward).
- **THE DUAL PAIR IS SYMMETRIC IN THE WORLD, NOT IN THE CHEST (2026-10-10, user: "in first person the dup sits toward
  one side, though the copied animation should balance them").** The first clips mirrored the right arm's LOCAL
  rotations under the pistol pose's BLADED spine, so the pair was symmetric about a turned chest. Measured in the
  player's own camera (`tools/godot/measure_gun_screen.gd`, `--no-mods` = the clip alone): both barrels 4.8 deg right
  and the guns 11.8 cm apart; the aim layer turned the upper body 4.8 deg back, which swung that narrow pair 5.6 cm
  left -- in first person the right gun sat on the crosshair (+1.5 deg) and the left 12 cm out (-10.3 deg).
  `make_dual_pistol_clips.py` now symmetrizes the BODY (every bone outside the two arm chains averaged with its
  partner's mirror -- a square, isosceles stance), puts the right hand `HALF_SPAN` = 0.12 m to its side with the
  bore turned straight ahead (read through Shino's `SocketPistol`), solves the arm to it, and only then X-flips the
  arm (on a symmetric body the local mirror IS the world mirror); the carry gets the same minus the bore turn. Each
  clip is then moved back onto the rig in FK (`arp_clips.move_to_arp`) so the rig and the export agree. Before the
  re-run the four clips' body bones were checked byte-equal to their pistol sources, i.e. never hand-edited.
  Result: clip alone 0.04 deg, first person right +9.5 / left -10.0 deg of the crosshair, 0.194 m apart, bores on the
  aim. `alignLeftBore` no longer has anything to correct (the left barrel is parallel without it, even at a 3 m aim
  point); it stays on as a safety net. `probe_dual_pistol` gains "the pair straddles the centre line" (centre within
  2.5 cm, span >= 0.15 m) with `--pistol-clip-control` (the pistol clip under the pair: centre +0.063, fails), and
  its `--control` is now a hidden 5 deg left toe-in (fails at +5.02) -- the old one passed once the clip was fixed.
- **SNR1 is Quaternius `SniperRifle_3` again** (user, 2026-09-21): the conformed `SNR1.blend` / `.glb` / icon
  and scene markers of 686f4c0 are restored (1.124 m AWP / L96A1, grip -> rear 0.306 m, grip lifted 2 cm, the
  `Bolt` part and its `bolt_work` clip, SupportPoint 3.5 cm under the forend), keeping the `rifle` archetype.
  The 3DModelsCC0 M24 row is gone from `import_guns_pack.py` so a re-run cannot bring it back. Credit for SNR1
  and the pistols (PIS1, PIS2, DUP1) is Quaternius' 50 Low-poly Guns, per the download's `license_link.txt` (CC0).
- **Every rifle/shotgun aim shares one finger set:** right hand = the upright rifle's, left hand = the single
  pistol aim's support hand (set on ARP's same-named finger bones in the two ARP clips, copied in the crouch and
  crawl clips). It is a gentle cup (35-57 deg at the middle joints), so a handguard grip still reads nearly flat.
- **Open: SHG1 in crouch** misses the left grip by 5.4 cm (tolerance 5): crouch still plays the rifle's crouch
  aim, never fitted to the shotgun's adopted socket (the mount drags the hand 0.27 m there).
- **2026-10-07: the pistols (PIS1, PIS2, DUP1, REV1) are back on their CONFORMED grip** (user: "the grip is too low,
  the gun blocks the crosshair"): models -1.5 cm (REV1 -3 cm), so the fist sits high under the slide / frame and REV1's
  front sight, which sat ON the crosshair in first person, is clear below it. SMG1 keeps its +3 cm. Pictures:
  `tools/godot/shot_pistol_sight.gd` (display). The note below is the history.
- **The revolver and SMG1 sit 3 cm higher in the hand, the pistols (PIS1, PIS2, DUP1) 1.5 cm** (user asked ~5 cm, then
  pulled the pistols back 1.5 cm so the fist lines up near the trigger; `blender/tools/shift_weapon_grip.py`
  moves the model up in its .blend and every Marker3D/CollisionShape3D with it). 5 cm was measured and rejected: the
  grips reach only 5.3-6.4 cm below the old fist centre. A PISTOL's SupportPoint is the support hand cupped round
  the FIST, so it stays put (PIS1/PIS2/REV1); SMG1's foregrip moves with the gun, and its stock mount now drops the
  hand 4.2 cm on the grip instead of raising the gun (the butt stays in the shoulder).
- **EVERY clip lives on the rig, and `ARP_` is internal** (2026-09-22, user: "remove the need to remember ARP vs
  non-ARP"). `arp_clips.py move-all` moved every game clip onto the ARP controls in FK, each PROVED by an unedited
  bake that must write 0 keys; the sidebar (N-panel > Game) lists clips by plain name with **Edit on Rig** / **New
  Clip** / **Limbs to IK**, and the game action `<clip>` is derived at export, never edited by hand. A clip made on
  the rig gets its game action and NLA track CREATED by the bake. The export skips a clip whose rig action AND
  game action are both unchanged since its last bake (digests on the `ARP_` action), so it stays fast.
  **Three bake defects the batch found** (105 of 170 clips first failed the proof, every one a false alarm):
  - the limb swing was measured from the rig's joint POSITIONS, and ARP's connected leg puts the knee 3-6 mm
    off a disconnected VRoid knee (every rotation exact) -- it is now the clip's own joint offset carried by the
    rig's ROTATION, and a bone's position is the clip's own offset from its parent except `Root`/`pelvis`;
  - a linearly interpolated quaternion is not unit length, so components differed for the SAME rotation -- a
    quaternion is compared as a rotation, in the chord form `4 asin(|q-v|/2)` (`2 acos(dot)` is float noise
    near 1 and flagged a 0.0001 finger wobble);
  - a clip keyed at fractional frames (`jump`, every 0.48 frame, ends at 33.6) has a rig copy ending at 33
    (ARP's retarget stops at the last whole frame): the bake samples to the last WHOLE frame.
  ARP's FK knee and elbow are hinge-LOCKED (X/Y), which looked like the cause and was not: the retarget does
  not go through the locks. Probe trap: the FIRST switch-off after a file load read a stale pose (0.9 m off on
  whichever clip was measured first), while the exporter's own guard read 0.000 m.

### Swim has its own branch: tread and stroke (PLAN.md 6.4, 2026-09-21)

`StanceTransition["Swim"] <- SwimTransition { Tread <- SwimMovementBlend ; Stroke <- swim_forward }`
(`tools/patch_tree_swim.py` on the reference tree, then `build_character_visuals.gd` for each generated body);
the Swim stance no longer borrows Crawl's ring. `AnimationController.updateSwimPosture` is the one rule: moving
forward OUT of combat strokes; at rest, sideways, back and ANY movement in combat treads -- a swimmer aims with
head and chest out of the water, and treading is upright, so Swim aims from the Default (upright) branch.
Gate `tools/godot/probe_swim_anims.gd` 6/6 (trunk 1.1 deg off vertical treading, 73.2 stroking, 2.4 aiming
while swimming forward); `-- --control` puts `animation_stance_key = "Crawl"` back and fails 5.

### A seat plays every body at the reference's scale; a low car sits deeper; the cockpit view finds the eye (2026-09-22, user-reported)

"Seated in a car, the character goes above the roof." Measured: Shino's pelvis 0.178 m above the cushion.
Since W49 the clips' `Root`/`pelvis` keys are in SHINO's metres (the re-home scaled them by her leg ratio),
which is right standing and wrong seated: the hips rest on the cushion whatever the legs, and every car seat
was measured with the reference body.
- **`AnimationController.applySeatedMotionScale`**: while the stance key is DriveCarrier or Passenger the
  skeleton plays at `seated_motion_scale` (skeleton metadata = the reference body's motion_scale, written by
  `build_character_visuals.gd` from `godot_chan.body.json`); the body's own comes back on leaving.
  Measured: hips 0.080 m above the cushion for all three bodies in all three cars.
- **`VehicleConfig.seatDrop`** (SPC-1 0.07 m, `build_vehicle_scenes.py` TUNING `seat_drop`): a low coupe's
  bucket seat. NOT a recline -- the seated clip leans the torso ~25 deg toward the wheel, so tilting the
  body back brings it UPRIGHT first and RAISES the head (measured, a 24 deg recline lifted the crown 6 cm).
- **The probe had checked the CAMERA MOUNT, not the head.** `probe_component_car.gd` now measures the crown
  (the body's own `crown_m` over its head bone) against the roof, and takes `--visuals=` for any body:
  9/9 body x car, tightest Fumiriya in SPC-1 at 0.064 m below the roof top.
- **The cockpit view is at THIS driver's eye**: 0.6 s after a driver sits, `Vehicle.calibrateCockpitMount`
  reads the driver's own eye marker ONCE, in the seat's frame, and moves `CockpitCameraMount` there (once,
  not per frame: W8.3's loop). Was 0.186 m off for Shino in SPC-1; now 0.001 m (`probe_vehicle_views`,
  whose head lookup now uses `MeshConfig.head_mesh_paths` -- it had died on Godot-chan's `head` node name).

### P6 code items closed (2026-09-22): seated aim branch, melee timings, the toon shader

- **6.5** `AimStanceTransition["Drive"] <- WeaponAimDrive` for driver AND passenger; each archetype plays its
  base's seated pose except dual pistols / fist / melee / throwable (they keep their upright pose).
- **6.6** The hit lands on the clip's strike: `tools/godot/measure_attack_clips.gd` finds each attack clip's
  contact frame (the striking hand's peak speed), and each step's windup is moved so that frame lands mid
  active window, KEEPING the tuned total duration. Before, four attacks hit up to ~0.1 s after the strike.
- **6.10** `assets/vfx/toon/` (its README is the record): one JSON owns the look, generated into Godot
  uniforms and a Blender node group; `tools/check_toon_parity.sh` renders one lit sphere in each and both
  put the edge at N.L 0.0796 (want 0.08). `Character.toonLook` is OFF by default until 3.14 decides.
  Trap it cost: `LIGHT_COLOR` in `light()` carries a factor of pi; a white specular band at that scale drew
  bright streaks across dark cloth -- the highlight is now the surface's own tone, divided by pi.

### W51 — OUR OWN FULL-BODY CONTROL RIG ON `shino` (2026-09-21, PLAN.md 6.17)

`blender/tools/add_control_rig.py` is now the full-body layer (W50's ARP route is superseded; the file
held no ARP when this ran). Measured on `shino.blend`, and every number is re-asserted each run:
- **FK controls ARE the deform bones, wearing typed shapes** -- hips square (COG), rings (spine, neck,
  limbs), a head ring with a forward tick, 30 finger rings (own `Fingers` collection), a floor square on
  the stance `Root`; sized from the skin each bone dominates (`skin_radii`, hair excluded), Rigify colours,
  armature drawn in front. A `CTRL_` copy per FK bone would be a second owner of every rotation and a
  switch the library must keep at 0; rotating a ring keys exactly the bone the export writes.
- **IK solves on a hidden joint-to-joint MCH chain.** A VRoid deform bone is disconnected and short
  (Shino's lowerarm 0.066 m against 0.214 m elbow-to-wrist), so an IK on it reached the forearm's TAIL
  and left the hand **0.15 m** from the cube; `use_tail = False` on the hand does not solve at all. Followers
  (`MCH_F_*`) carry each deform bone's own rest frame and the deform bone COPY_TRANSFORMS them, so no rest,
  roll or length changes. Hands/feet also COPY their control's rotation; the foot control is a sole outline.
- **The arm is a plain 2-bone IK hanging from the FK collarbone -- Rigify / ARP's shape -- and that was a
  user report, measured.** The first build recruited the collarbone (a pole-less 3-bone "reach" stage),
  and dragging the hand control in 1 cm steps showed why it felt wrong: the shoulder did not move at all
  short of full reach (1-4 mm), then slammed from 10 to its 60 deg limit within 10 cm, pulling DOWN as
  well as forward. Now the clavicle ring poses the shoulder in IK mode too and a hand past its reach
  stops short. Measured on all four limbs: to IK moves nothing (0.0000 m), the tip stays on its control
  wherever reachable, the shoulder moves 0, no bone turns more than 10.6 deg per cm of drag (the elbow
  straightening near full reach), to FK leaves the limb where it was.
- **Per-limb IK, switched from a sidebar** (N-panel > Rig): `CTRL_root["ik_arm_l"]` etc., stored 0, and
  "to IK" / "to FK" snaps (auto-keying keys the limb on "to FK"). `blender/tools/control_rig_ui.py` is the
  one owner: written into the .blend as a registered text block (Rigify's `rig_ui.py` idiom -- Blender
  asks to allow the file's scripts) AND imported by `verify_drag`, which drives those same snaps.
  It replaced the text-block GRAB/BAKE, which had been broken since W48's single master switch.
- `export_character.py`'s guard measures DEFORM bones only; it still refuses a live rig (0.865 m).
- Headless picture of the shapes (the overlay does not render): turn each custom shape into a curve at
  `pose matrix @ T(translation) @ R(euler) @ S(scale)` and Workbench-render it. Trap: `object.convert`
  converts EVERY selected object, the body included -- deselect first.

### W50 — THE CONTROL RIG IS AUTO-RIG PRO'S, AND OURS IS REMOVED (2026-09-21, user-asked)

> **SUPERSEDED THE SAME DAY — read PLAN.md 6.17 before acting on this section.** The user's direction is
> our OWN full-body control layer on `shino` (control shapes + IK), not a vendor rig. Measured after this
> was written: merging ARP into `shino` hits **143 bone-name collisions**, 196 drivers and 216 constraints
> and loses ARP's own picker/snap (it identifies its rig by `arp_rig_type`/`rig_id`); and exporting through
> ARP would re-mean **~1400 bone-name references across ~40 files**, both VRoid bodies' conformance, and
> every bone-frame constant, since its rests differ by up to **176.6°**. A later Quick Rig run in PRESERVE
> mode DID drive our 53 bones correctly (334 `COPY_TRANSFORMS` via `<bone>_qr_offset`, clips byte-identical)
> — so the shape below is sound; what changed is that it is not the shipping path. The `--remove` recorded
> here was also undone by a file rollback, so the 9 `CTRL_` bones are back in `shino.blend`.


W48 measured Rigify/ARP/Rigodotify and rejected them on bone ROLL — correct **only for a rig that
BECOMES the deform skeleton**. ARP's Quick Rig in **`PRESERVE`** mode does not: it leaves our 53
bones as they are and builds a 381-bone control rig that DRIVES them. The rolls never change, the
contract holds, every clip stays an ordinary 53-bone action, and `export_character.py` already
refuses an export in which anything drives the deform bones — which is the safety net for
forgetting to bake down.

**The limb map is DERIVED from our contract and is stored IN `shino.blend`**, so Quick Rig opens
ready (`blender/tools/arp/build_limb_map.py`, a one-shot in the `import_melee_pack.py` contract;
`blender/tools/arp/shino_quick_rig_mapping.py` is ARP's own exported form, loadable with
Quick Rig ▸ Import Mapping). Six limbs: ARM `clavicle/upperarm/lowerarm/hand` in slots 1/2/4/6,
LEG `thigh/calf/foot/ball` in 1/3/5/6, SPINE `pelvis` + the three spines, HEAD `neck_01` + `head_2`.
**ARP is commercial: its source never enters the repo.** What lives here is our own table.

**The blocker was never a missing bone — it was a COUNT.** Every per-limb count has to be stated,
not left at its default: `neck_bones_amount` defaults to **2** against our single `neck_01`, and
Quick Rig died on `KeyError: 'neck_ref'`. Set to 1, the same map takes the generated rig from
**223 bones / 32 deform to 381 / 173**. Three more traps, all script-only: `rig_presets` is
`rig_preset`; `arp_ver_int` is computed in a DRAW-TIME helper so it stays None under `-b`; and ARP
reaches for `bpy.context.space_data.overlay`, so it needs a VIEW_3D `temp_override` and **cannot run
headless — it is an artist one-shot, never a build step**. `restore_base_arm_loc` reads state set in
`invoke()`, which a `bpy.ops` call from Python skips, so a script dies on `None.location` AFTER
building the rig; **pressing the button in the UI runs `invoke()` and never had this problem.**

**TWO CONTROL RIGS IN ONE FILE IS WORSE THAN NONE, and our own layer is what caused the next
report** ("the hand control ... when move them, nothing happen ... rest seem work pretty well"). Our
`CTRL_hand_l` and ARP's `c_hand_ik.l` are drawn at the same place on the same hand, and ours is
stored at **influence 0 by design** (`master_switch`, W42) — so the artist grabs whichever is on top
and half the time nothing happens, which is *the very report the CTRL layer was built to answer*,
now produced by it. Both reported-inert controls are ours: the hand and the foot, the two we drew
solid widgets for (`WGT_CTRL_hand_*`, `WGT_CTRL_foot_*`).

**`add_control_rig.py --remove`** (W48's open item) takes back every piece that script added and
nothing else: the 9 `CTRL_` bones, the 4 `CTRL_IK` constraints **and their drivers first** (a driver
whose target bone is gone is a broken driver), the `CTRL` bone collection, the six `WGT_*` widget
objects and the `IK CONTROLS` text block. Widgets go **by NAME, not by user count** — a datablock's
users are not re-counted until the depsgraph runs, so "unused now" is not yet true on the line after
the bones went. It asserts the same thing the builder does and refuses to save otherwise:
**the pose moved 0.000000 m over 1422 samples**. Applied to `shino.blend` only (167 → 158 bones,
167 actions, `Body`/`Extras` collections and the limb map intact); Godot-chan and Fumiriya keep
theirs, since only the authoring body has ARP.

**The game is unchanged, and that is measured rather than assumed**: a scratch re-export reads
164 nodes / 158 joints / 168 animations, identical to the shipped `.glb`, because
`export_def_bones=True` had always filtered the CTRL bones out — so the shipped export was never
rewritten.

