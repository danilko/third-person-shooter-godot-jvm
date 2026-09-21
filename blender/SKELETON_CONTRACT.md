# The skeleton contract — one clip library, many bodies (PLAN.md 6.9, 2026-09-20)

**A clip is a fact about the SKELETON, not about a body.** So there is ONE animation library in this
game, every body plays it, and a new body ships with no clips at all. This file is what a body has
to present to get that for free, why each rule is there, and what was measured to decide it.

It is the same answer GTA reaches: every ped shares one skeleton, clips live in shared dictionaries,
and a *specific* character gets extra clips of its own rather than a private copy of the walk cycle.
The part worth stating, because it is what makes it work at all, is that **the shared thing is the
RIG, not the proportions** — bodies here differ from 1.49 m to 1.91 m and share every clip.

---

## 1. What a body must present

| the contract | why it is the contract |
|---|---|
| the **53 bone NAMES** (`Root`, `pelvis`, `spine_01..03`, `clavicle_*`, `upperarm_*`, `lowerarm_*`, `hand_*`, 15 finger bones a side, `neck_01`, `head_2`, `thigh_*`, `calf_*`, `foot_*`, `ball_*`) | a track, an AnimationTree filter, a `PhysicalBone3D`, `ShoulderAimModifier.drivenBones` and the bone-damage table all address a bone by name |
| the **rest ORIENTATIONS**, within 1° | a rotation key says "this bone is rotated by *q* **from its rest**". Two rigs whose rests differ interpret the same key as different poses |
| **facing −Y in Blender, left arm at +X** | the same fact stated as a whole-body rotation |

| deliberately NOT the contract | why |
|---|---|
| bone **LENGTHS**, and therefore height, reach, hip height | this is the whole point of a second body. Shino's arm is 0.433 m against Godot-chan's 0.416, her hips sit 0.935 m up against 0.767 — and both play every clip |
| bones the contract does not name — hair, skirt, spring-bone chains, eyes, tongue | a VRoid body keeps its own (158 bones on Shino, 117 on Fumiriya); the mesh is skinned to them and nothing animates them |
| meshes, materials, textures | a body's appearance is the body's |

**Gate: `tools/godot/probe_body_contract.gd -- --body=res://assets/characters/<body>/<body>.glb`.**
It plays every clip in the shared library on the body and on the reference rig and compares every
bone's world orientation. Measured: **Shino 0.06°, Fumiriya 0.06°** over 171 clips × 4 samples,
while bone POSITIONS differ by up to 0.37 m — which is exactly the split above. `--control` puts
20° into one bone's rest and the gate fails, because that error is otherwise silent: every clip
still plays, and the body just stands slightly wrong.

---

## 2. Why position tracks are the thing that had to go

**A position key is an absolute bone-local offset in METRES.** Play a clip that pins `pelvis` at
Godot-chan's 0.767 m on a 1.91 m body and its hips sit 0.37 m too low for the whole clip — not a
subtle error, and not one any name check can see.

Measured on the source export: of **8550** position tracks, only **136** carry motion.

| bone | biggest move |
|---|---:|
| `pelvis` | 0.766 m |
| `Root` | 0.643 m |
| `clavicle_l` / `clavicle_r` | 0.0097 m |
| **every other bone** | **≤ 0.000036 m** |

The two populations are **270×** apart, so `tools/godot/build_character_anims.gd` drops every
position track that never leaves the rest pose and keeps the four that move. That is what makes a
clip portable; it also takes the library from 8550 position tracks to 136.

`Root` and `pelvis` still carry metres, and a taller body therefore under-travels on a roll or a
crawl-to-stand in proportion to its legs. It is not corrected, on purpose: nothing in the game reads
root motion (`MovementController` moves the body), so it is a look, not a mechanic, and a per-body
correction would be per-body data — the thing this whole design exists to avoid. Measure it before
fixing it.

---

## 3. Why the rest pose is CONFORMED rather than the clips retargeted

A VRoid `.vrm` rests with **every bone's rotation at identity** — the VRM spec's T-pose, where a
bone is distinguished only by where it is. Blender's stock importer preserves that, so an imported
VRoid bone's local +Y points at the world's up, not along the bone. Against Godot-chan's Blender-style
rig, that is a wholly different rest, and the same clip on both is two different poses.

Two ways out, and the cheap one is right:

- **retarget the clips** per body (`retarget_ual.py`'s world-space delta, W34) — a derived copy of
  all 171 clips per skeleton, re-run on every clip edit, and the runtime no longer has one library;
- **conform the body's rest** — and this is FREE, because a Blender bone's deformation is
  `pose · rest⁻¹`, which at rest is the identity *whatever the rest orientation is*. Re-orienting a
  bone in edit mode does not move one vertex of the mesh. It only changes what a pose rotation
  means, which is precisely the thing that has to agree.

So `blender/tools/import_vrm_body.py` does three things and nothing else: **turns the body round**
(measured: one 180° about Z, not a mirror — VRoid faces +Y with its left arm at −X, we face −Y with
left at +X), **renames** the 54 humanoid bones from the file's own `VRM.humanoid.humanBones` map
rather than by matching `J_Bip_*` strings, and **re-orients** each contract bone's rest to the
reference's, keeping the VRoid head position. Measured on Shino: after the turn her limb directions
already agreed with the contract to a few degrees (both rigs are T-posed), so what the re-orient
actually supplies is the ROLL — biggest change 251.7°, on a thumb.

`blender/tools/dump_skeleton_rest.py` writes the reference's rest to
`assets/characters/skeleton_rest.json`, so the target is derived from the rig and not a table typed
into a script.

**Auto-Rig Pro and Rigify stay the ARTIST's control rig** for authoring new clips, never a build
step: ARP still throws draw-handler errors in headless Blender 5.2 (seen on every run here, as W34
measured). Whatever rig authors a clip, what ships is a clip on these named deform bones.

---

## 4. Where the shared things live

```
assets/characters/
  skeleton_rest.json                 the contract's rest, DERIVED from the reference rig
  godot_chan/merged_animation.blend  the CLIP SOURCE (and, for now, the reference body)
  shino/shino.{blend,glb}            body: mesh + conformed skeleton, no clips     (F, 1.645 m)
  fumiriya/fumiriya.{blend,glb}      body: mesh + conformed skeleton, no clips     (M, 1.909 m)
src/main/resources/com/openworld/character/anim/
  character_anims.res                THE library: 171 clips, 2.1 MB, every body plays it
  character_anims.json               its manifest (clip names, bones, which bones translate)
```

Two rules make one library bind to any body:

- **a track path names the SKELETON, not the armature**: `Skeleton3D:spine_03`, never
  `Godot_Chan_Stealth/Skeleton3D:spine_03`. The `AnimationTree`'s `root_node` is the body's own
  armature node, so a body may name that node anything;
- **the AnimationTree carries the library itself** (`libraries = {&"": …}`) instead of pointing at
  an `AnimationPlayer` inside the body's imported `.glb`. Its filters are body-independent for the
  same reason.

**Gate: `tools/godot/probe_shared_anims.gd`** plays every clip from the body `.glb`'s own player and
from the shared library on two real skeletons and compares every bone: **0.000001 m / 0.056°**
(that last is float32 key noise on a fingertip four bones down the chain). `--control` shifts one
bone's rest by 5 cm — less than Shino's arm differs from Godot-chan's — and the constant position
tracks then override it, failing by exactly **0.050 m**.

---

## 5. The boss case: a character with clips of its own

The shared library is `AnimationTree.libraries[""]`. A named character that needs moves nobody else
has gets a **second library beside it** under its own key — `libraries = {&"": <shared>,
&"boss_a": <boss_a_anims.res>}` — and plays them as `boss_a/<clip>`. It is additive: the boss still
walks, aims, reloads and dies on the shared clips, and only the beats that are genuinely its own are
its own. That is the split GTA makes between a movement dictionary and a cutscene dictionary, and it
is why "one library" costs nothing in expressiveness.

Nothing ships one yet. Build the first one when a boss needs it, not before.

---

## 6. Known warts, both worth fixing when Godot-chan retires

- **The head bone is `head_2`.** The reference `.glb` carries a MESH node called `head` as well as
  the bone, so Godot's glTF importer renamed the BONE out of the way — and the library's tracks, the
  AnimationTree's filters, `Physical Bone head_2` and the Java bone-multiplier table all say
  `head_2`. `import_vrm_body.py` therefore names it `head_2` on every new body. The clean fix is to
  rename the reference's mesh.
- **Godot-chan is still the reference, and now for a second reason.** `skeleton_rest.json` and
  `probe_body_contract.gd`'s comparison come from it, the clips are authored on it, and it owns the
  AnimationTree that `build_character_visuals.gd` copies into every other body. Both VRoid bodies now
  have full `CharacterVisuals` scenes (§8), so what keeps it is that it is the CONTROL every derived
  rule is read against — and two things the gates say about it are true and unflattering: its
  first-person mount sits 8.2 cm behind the head bone rather than at the eye, and its hands are 0.9 cm
  across (the editor's `0.1 x bone length` rule). See CLAUDE.md "W41".

---

## 7. What a new body costs, end to end

```bash
G=/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64
blender -b --python-exit-code 1 --python blender/tools/import_vrm_body.py -- \
    --vrm "/path/to/body.vrm" --name <body>
$G --headless --path . --import                     # NOT optional
$G --headless --path . --script tools/godot/probe_body_contract.gd -- \
    --body=res://assets/characters/<body>/<body>.glb
```

Then the body's own numbers and its scene, both of which are MEASURED and GENERATED rather than
authored (CLAUDE.md "W41" is the record; §8 below is the command):

```bash
$G --headless --path . --script tools/godot/measure_body.gd -- --body=<body>
$G --headless --path . --script tools/godot/build_character_visuals.gd -- --body=<body>
# the shoulder pocket's owner is the gate, so one round-trip settles it
$G --headless --fixed-fps 60 --path . --script tools/godot/probe_weapon_fit.gd -- \
    --visuals=res://src/main/resources/com/openworld/character/CharacterVisuals_<Body>.tscn \
    --emit-pocket=res://assets/characters/<body>/<body>.pocket.json
$G --headless --path . --script tools/godot/measure_body.gd -- --body=<body>
$G --headless --path . --script tools/godot/build_character_visuals.gd -- --body=<body>
$G --headless --fixed-fps 60 --path . --script tools/godot/probe_character_visuals.gd -- \
    --visuals=res://src/main/resources/com/openworld/character/CharacterVisuals_<Body>.tscn
```

`--check` on either tool re-derives into memory and fails if what is on disk is stale, so a clip-tree
edit that never reached the other bodies is caught.

If the clip library itself is re-authored:

```bash
blender -b assets/characters/godot_chan/merged_animation.blend --python-exit-code 1 \
    --python blender/tools/export_character.py
$G --headless --path . --import
python3 blender/tools/check_character_anim.py
blender -b assets/characters/godot_chan/merged_animation.blend --python-exit-code 1 \
    --python blender/tools/dump_skeleton_rest.py       # only if the RIG changed
$G --headless --path . --script tools/godot/build_character_anims.gd
$G --headless --path . --script tools/godot/probe_shared_anims.gd
```

---

## 8. The per-body half, and what it does NOT give you

`assets/characters/<body>/<body>.body.json` is the derived record — reviewed like the road record, a
re-run reproduces it, and a diff is readable. `CharacterVisuals_<Body>.tscn` is written from it and
from the reference's AnimationTree. What a body still owes a human:

- **its materials.** A VRoid body arrives with 17 MToon-derived materials; merging them toward one
  toon material per region is 6.10. The regions are already in the record (`surface_regions`, from the
  `_SKIN`/`_CLOTH`/`_FACE`/`_EYE`/`_HAIR` suffix VRoid stamps on every material name), so the merge has
  its list.
- **a hold pose, if its proportions need one.** Measured, Shino's support hand misses the longest two
  handguards by 7.8 and 8.6 cm — her shoulders are 7.8 cm narrower than the reference's, which moves
  her left hand that much further from a gun held on the right. That is W25's `adopt` path, not a
  number a tool should invent.
- **a decision about which body ships as the player**, which is an art call and deliberately not made
  here.

And one thing nobody owes, which is the point: **no clips.**

---

## 9. Authoring a shared clip: judge on every body, edit in one

One library means the clips live in Godot-chan's `.blend` and **no other body has any**, so a pose is
authored while looking at the body it suits LEAST — 1.49 m, the biggest head and the longest hands of
the three, serving bodies of 1.65 m and 1.91 m. `assets/characters/animation_review.blend` is the fix
(`blender/tools/build_animation_review.py`, re-run it rather than editing it):

```bash
blender -b --python-exit-code 1 --python blender/tools/build_animation_review.py
blender assets/characters/animation_review.blend
```

It is a **VIEW, not a copy**. Every body is library-LINKED from its own `.blend` and then
`override_hierarchy_create`d, and the 171 actions are library-LINKED from `merged_animation.blend`
and are therefore **read-only here**. That is the design and not a limitation: a clip has one owner,
Blender cannot merge two edits of one action, so it must not be possible to make two. **Judge here,
edit there, `File > External Data > Reload`.**

**Judge it on SHINO**, who stands at the origin. Her reach is the shortest of the three and not
because of her arm — her shoulders are 0.218 m against the reference's 0.296, which is what puts an
off hand furthest from a weapon held on the right. A hold that works on her works on the others, and
the reverse is measurably false (§8, and CLAUDE.md "W41": ASR1's support hand missed by 7.8 cm on
Shino and 0.000 on the two wider bodies).

Two traps, both of which read as "this body has no animation":

- **Since Blender 4.4 an action is SLOTTED.** Its channels belong to a slot naming the ID it was
  authored on (`OBGodot_Chan_Stealth`); assign that action to any other rig and `action_slot` comes
  up None — **no error, no warning**, the rig simply stands in its rest pose while the timeline runs.
  Binding `animation_data.action_slot = action.slots[0]` is what makes one clip play on every body,
  and it is the reason the review file could not have been a hand-assembled scene.
- **A LINKED object cannot be given `animation_data` at all**, so linking alone cannot play anything;
  the override is what makes it local enough to take an action. Building local objects around the
  linked mesh DATA instead does not work either — vertex groups live on the OBJECT, so the meshes
  arrive unweighted and the armature moves nothing.

What the file then shows, and what it is worth opening for: once bound, `upright_walk_forward`'s same
rotation keys travel **0.53 m on Shino, 0.47 m on Godot-chan and 0.65 m on Fumiriya** — longer legs,
longer stride, one clip. That is the contract working. What it also shows is §6's wart, which is NOT
a pose problem and must not be "fixed" by moving keys: `Root`/`pelvis` position keys are absolute
metres, so a crouch or a crawl authored here sits too high on a taller body (Fumiriya's feet 5.8 cm
off the ground in `crouch_idle`). That is runtime foot grounding.

---

## 10. Posing with IK: a control layer, added, never generated

`blender/tools/add_control_rig.py` gives a body's `.blend` hand and foot IK so a pose is made by
moving a hand, not by turning four bones. **A ONE-SHOT** — it runs when a body needs the layer, the
result is committed inside the `.blend`, and nothing depends on it running again: no gate calls it,
no build step, no export path. The clips are already protected by gates that exist, so it needs none
of its own.

```bash
blender -b assets/characters/<b>/<b>.blend --python-exit-code 1 \
    --python blender/tools/add_control_rig.py -- --armature=<name> --save
```

It adds 9 bones (`CTRL_root`, `CTRL_hand_l/r`, `CTRL_foot_l/r`, `CTRL_elbow_l/r`, `CTRL_knee_l/r`),
an IK constraint on `lowerarm_l/r` (**chain 3 — the CLAVICLE is in it**) and `calf_l/r` (chain 2), a hideable `CTRL` bone collection, wire widgets,
and an `IK CONTROLS` text block carrying the workflow and both snap helpers — **inside the `.blend`,
so they travel with the file and do not depend on the repo script surviving.**

**Why not Rigify / Auto-Rig Pro / Rigodotify.** All three were tested, not dismissed
(CLAUDE.md "W42"). Rigodotify is a genuinely good fit on the one axis people reach for it — its
skeleton is **51 of our 53 bones by exact name**, the only gaps being `Root` vs `root` and our own
`head_2`. But those tools GENERATE a rig, and a generated rig brings **its own bone rolls**: measured
against ours, the roll differs by a median of **24.4°**, with only 6 of 52 bones within 1° and 10
past 45° (`ball_l/r` 175°, `clavicle_l/r` 87.8°). Rest orientations are half this contract and both
VRoid bodies were CONFORMED to them, so adopting a generated rest would re-mean all 171 clips, force
a re-conform of every body, and move every bone-frame constant in the game. Adding bones and
constraints touches none of it. (The generated route also needs the GUI — Rigodotify's converter
drives the Drivers *editor* and dies headless.)

**The interop argument is already satisfied and does not need a new rig.** What a retargeter reads
is the DEFORM skeleton's bone names, and ours are the UE-mannequin convention every engine
auto-detects. The two exceptions are recorded here rather than renamed: `Root` (standard is `root`)
and `head_2` (standard is `Head`, and ours exists only because the reference `.glb` carries a *mesh*
called `head`, so Godot's importer renamed the bone — §1). Renaming costs 75 hits across 26 files
plus a library re-bake; a retargeter needs a mapping table anyway, so the cheap fix is two rows in
that table at the seam.

### The rules that make it safe

- **The IK influence is 0, and that is the whole safety argument.** A constraint at full influence
  OVERRIDES the chain's own rotation channels, so leaving it on would silently replace the arms of
  all 171 shared clips. At 0 the rig evaluates exactly as before — the script asserts it and refuses
  to save otherwise (measured: **0.000000 m** over 477 samples on the reference).
- **GRAB before you pose.** A control you have not grabbed sits where it was left, and raising
  influence drags the limb to it — measured **0.83 m** on an arm from the rest position. The
  `IK CONTROLS` helper in `GRAB` mode puts both handles where the clip already has them and switches
  IK on, disturbing **0.0007–0.0019 m**.
- **The pole angle is POSE-DEPENDENT and must be re-solved at grab time.** One stored value cannot
  preserve every pose: an angle solved on a crouch moved an aim pose's forearm **0.231 m**. `GRAB`
  places the pole in the limb's current bend plane and re-solves (~80 evaluations).
- **Prefer `BAKE` to keying the controls.** `BAKE` writes the IK result into the FK bones
  (measured **0.000000 m**) and drops influence to 0, so the action keys only the 53 contract bones,
  exactly as today — `animation_review.blend`, every other body and the shared library are all
  unaffected. Keying the controls instead also works (the export samples the evaluated pose) but
  then every body needs the layer and `export_def_bones` must be on.
- **`export_def_bones = True` is now required** in `export_character.py`. A `CTRL_` bone is not a
  deform bone, but `use_deform = False` does **not** keep it out of a glTF export — measured, it
  comes through as a 54th joint with its own animation track, which breaks the 53-bone contract
  silently. With the flag on: **53 joints, no `CTRL_` node, no `CTRL_` track, all 171 clips**, and an
  IK result still fully baked. It is not bit-identical (up to **0.065°**, against the 0.056° of
  float32 key noise `probe_shared_anims` already tolerates), so the shipped `.glb` was deliberately
  NOT re-baked when it was flipped.
- **Re-importing a `.vrm` overwrites the `.blend` and takes the control layer with it.** Re-run this
  script after `import_vrm_body.py`; it is idempotent, so running it on a body that already has the
  layer repositions rather than duplicates.

### 10a. The shoulder is in the arm chain (2026-09-20, CLAUDE.md "W45")

Move the hand and the **shoulder follows**. A support hand that cannot reach its grip is short
because of the SHOULDER, not the arm — Shino's shoulders measure 0.2174 m against the other two
bodies' 0.2955, and it is that 7.8 cm, not her arm length, that misses a long handguard — so the
gesture the artist wants is one where the collarbone protracts to help, exactly as a person does
and as the runtime `SupportHandIKModifier` already does in game.

Two rules keep it safe, and both are measured by the tool on every run:

* **It goes up only as far as it must.** `ik_stiffness` 0.9 on the collarbone, so the solver spends
  the elbow and the shoulder joint first.
* **It cannot over-rotate.** A symmetric envelope on all three axes,
  `character_anim_naming.json` → `limits.shoulder_channel_deg` (**60**), which is the ONE owner of
  that number — the control rig, `fix_shoulder_overbend.py` and `check_character_anim.py`'s
  `shoulder_overbend` all read it. Symmetric and per-axis-identical on purpose: which local axis is
  protraction is a fact about bone ROLL, and an envelope written per axis would be a second place
  that fact lives, wrong on the first body whose roll differs.

Measured on the reference: the hand pulled 4 cm past the arm's own reach recruits **23.1 deg** of
collarbone and ARRIVES (0.002 m); pulled 60 cm past, the collarbone stops at **60.1 deg** and the
hand is honestly 0.53 m short rather than the shoulder dislocating. Influence stays 0, so the rig
still evaluates identically (**0.000000 m over 477 samples**).

**BAKE writes the collarbone too.** The `IK CONTROLS` snap helper's chains are
`clavicle → upperarm → lowerarm`; a BAKE that left the collarbone out would let the shoulder spring
back to the clip's pose the moment influence dropped.

**Two traps this cost, both silent:** an IK constraint's result never reaches `matrix_basis` (a
shoulder the solver had swung 0.12 m read 0.9 deg — read the EVALUATED pose), and a limb's reach is
the two JOINT-TO-JOINT distances, not the two bone lengths (a bone's tail need not sit on its
child's head; the lengths under-measured this arm by 4 cm).
