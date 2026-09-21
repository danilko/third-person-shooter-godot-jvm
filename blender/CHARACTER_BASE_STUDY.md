# Replacing Godot-chan with a VRoid base body — the decision (PLAN.md 6.8, 2026-09-19)

The study the plan asked for, and the decision it reached. Measured, not guessed: every number below comes
from reading the files (`.vrm` is a GLB, so its JSON chunk answers most of it with no Blender at all) or from
a headless Blender import. Nothing has entered the repo yet.

Source: `/data/danilko/game_assets/cc0 vrm/` — 12 `.vrm` VRoid avatars (11 distinct; one is a duplicate), one
already opened in Blender, and six VRoid FAQ pages as PDFs.

---

## 1. Licence — per model, from the FILE and from the FAQ

**The file is the primary record.** Every one of these `.vrm` files carries its own `VRM.meta`, and VRoid Hub
publishes the permission set in the `otherLicenseUrl` query string. All eleven carry the **same fully permissive
set**:

```
allowed_to_use_user=everyone   modification=allow      redistribution=allow
personal_commercial_use=profit corporate_commercial_use=allow   credit=unnecessary
```

That is CC0-equivalent in effect: modify, redistribute, sell, no credit required. `licenseName` is the string
`"Other"` in all of them — which is VRoid's way of saying "see the URL", **not** a restriction.

The FAQ PDFs corroborate it for the models they name, and say plainly that *not every* VRoid sample is CC0:
`AvatarSample_A/B/C` have "particular conditions of use", while the **base models** and **β Ver AvatarSample_1–4**
are CC0. None of the A/B/C models is in this folder.

| file | title | PDF says | file says | height |
|---|---|---|---|---|
| `4537789756845150029.vrm` | 千駄ヶ谷篠 Sendagaya Shino | **CC0** (own PDF) | permissive | 1.645 m |
| `1889117373041382244.vrm` (+ `.blend`) | 千駄ヶ谷篠_WSU (Shino, school uniform) | Shino's PDF | permissive | 1.645 m |
| `2233030527144754025.vrm` | 桜田 史利矢 Sakurada Fumiriya | **CC0** (own PDF) | permissive | 1.909 m |
| `8801565727279527051.vrm` | 千駄ヶ谷渋 Sendagaya Shibu | — | permissive | 1.616 m |
| `2818922592115760586.vrm` | 千駄ヶ谷渋_WSU | — | permissive | 1.616 m |
| `3658448283550216100.vrm` | ダークネス渋 Darkness Shibu | — | permissive | 1.733 m |
| `4821756309702791141.vrm` (×2, identical) | ヴィクトリア・ルービン Victoria Rubin | — | permissive | 1.737 m |
| `6795810513740058493.vrm` | ビビ Bibi | — | permissive | 1.412 m |
| `7151938431140058353.vrm` | ヴィータ Vita | — | permissive | 1.713 m |
| `6806103343691492736.vrm` | さくらだ ふみりや | — | permissive, **author `しげぽんしげぽん`** | 1.580 m |

**Two cautions, and they decide which files we take.**

- The last row is **not by pixiv/VRoid Project** — it is a third-party VRoid Hub user's re-make of Fumiriya. Its
  own metadata permits redistribution, but no FAQ page covers it and the chain of rights behind a user upload is
  not something this project should rely on. **Do not import it.**
- Only two models have a PDF of their own in the folder confirming CC0 in prose: **Sendagaya Shino** and
  **Sakurada Fumiriya**. Those two are the female and male base bodies this study recommends. The rest are
  permissive by their own metadata and may be used later, but the two with both records are the ones to start
  from.

**Action taken:** a row in `assets/LICENCE_AUDIT.md` records this before any file enters the repo, per the rule
in that file. Nothing is committed yet.

---

## 2. Pipeline — VRM → **Blender** → our glTF export

**Decided (user, 2026-09-19): convert to Blender.** The alternative — V-Sekai's `godot-vrm` addon importing
`.vrm` straight into Godot — buys spring bones and MToon for free and costs everything the W-series is built on:
one character export path (`blender/tools/export_character.py`), one gate (`check_character_anim.py`), one place
a clip is named, one place a socket is measured. A second import path into Godot would be a second owner of the
character, and this file's whole history is one-owner rules.

**The import needs no VRM addon at all.** Measured: a `.vrm` renamed `.glb` and opened with Blender's *stock*
glTF importer gives **1 armature / 158 bones / 4 meshes / 19 materials / 42 shape keys / 1 UV layer per mesh /
19 images** — the whole body, skeleton, weights and textures. The `io_scene_vrm` addon (saturday06) is needed
only for the three things the VRM *extensions* carry: the humanoid bone map, the spring-bone chains, and MToon.

And **we are dropping two of those three on purpose** (§4): MToon is replaced by our own toon shader, and spring
bones are a per-frame cost a crowd cannot afford. The humanoid map is a 54-row table that the GLB's JSON already
hands us (this study read it with 40 lines of Python). So:

> **The build step is plain glTF. `io_scene_vrm` is an optional artist convenience for opening a `.vrm` to look
> at it, never a dependency of the pipeline.** One fewer addon whose Blender-version support we have to track —
> which matters, because this project runs Blender 5.2 and the road kit already learned what a UI-driven addon
> costs in a headless build (W34).

Shape: `<name>.vrm` → (once) `assets/characters/<name>/<name>.blend` → `export_character.py` →
`<name>.glb` → `<name>.tscn` → `CharacterVisuals_<name>.tscn` + a `MeshConfig`. That is exactly W18's
second-body path, which already exists and is already gated.

---

## 3. Rigging — **rename the bones; do not retarget**. Rigify/ARP is an artist tool, not a build step

The W-series contract is **bone names and clip names** (W18). A VRM humanoid skeleton is a fixed, published
54-bone map with names like `J_Bip_C_Hips`, `J_Bip_C_Spine`, `J_Bip_L_UpperArm`; Godot-chan's are
`pelvis`, `spine_01..03`, `clavicle_*`, `upperarm_*`, `hand_r`. **That is a rename table, not a retarget.**

| approach | cost | risk |
|---|---|---|
| **Rename** (recommended) | one deterministic table, ~54 rows, applied in the one-shot `.blend` conversion | the spine chain differs: VRM has `spine / chest / upperChest` (3) where we have `spine_01..03` (3) — a 1:1 map exists. Bone ROLLS and rest pose differ, which is what §5's re-measurement is for |
| **Retarget the 171 clips** (`retarget_ual.py`'s world-space delta, W34) | a second copy of every clip, re-run per edit | only needed where the rest pose cannot be reconciled — a fallback, not the plan |

**On Auto-Rig Pro / Rigify (the user's note).** Both are *control-rig* tools: they build an animator-facing rig
on top of a deform skeleton. They are genuinely useful for **authoring new clips by hand** — P6's remaining
art items (6.2 prone aim, 6.3 true strafes, 6.6 real melee swings) are exactly that work — and an artist should
use whichever they prefer, in their own `.blend`, on top of the renamed deform skeleton.

They must **not** become a build step, and W34 already paid for that lesson: Auto-Rig Pro fails to register in
headless Blender 5.2 (draw-handler errors) and is driven by scene/UI state, so it is not reproducible. The rule
that falls out:

> **The control rig is the artist's; the DEFORM skeleton is the contract.** Whatever rig authors a clip, what
> ships is a clip on the 54-ish named deform bones, exported by `export_character.py` and checked by
> `check_character_anim.py`. That keeps `ShoulderAimModifier`, `StockMountIKModifier`, `SupportHandIKModifier`,
> every socket and all 171 clips working with no code change.

---

## 4. Shading — ONE toon model, two implementations, one parameter table

**Decided (user, 2026-09-19): a custom toon shader, not MToon, and it must work in BOTH Blender and Godot so an
artist can adjust in either.**

MToon is VRM's own toon shader and V-Sekai ports it to Godot — but it is a third-party material model we would
not control, it is per-material (17 materials per avatar, §5), and it has no Blender-side twin an artist can
edit. Our own is cheaper in every sense.

**The cross-DCC rule is this project's own one-owner idiom applied to shading** (`road_kit.json`, `palette.json`,
`weapon_archetypes.json` are the precedents): the *parameters* have one owner — a small JSON — and there are
**two implementations that read it**, a Blender node group and a Godot `.gdshader`. Neither is derived from the
other at build time; both are gated against the same parameter file, so they cannot silently disagree, and an
artist who changes a ramp in Blender changes the number the game reads. A picture gate (a render from each side
of the same head under the same light, compared) is what keeps them honest — the same shape as
`roadkit_mesh_parity.py`, which is what let the Blender road build be retired.

References, licences checked and recorded in `CREDITS.md`:

| reference | author | licence | what we take |
|---|---|---|---|
| [Anime-style face shader](https://godotshaders.com/shader/anime-style-face-shader/) | Evident | **MIT** | the face SHADOW MAP idea: a stylised face lit by an authored map, not by its own normals, so it never breaks up as the sun moves |
| [Toon shader contact shadows](https://godotshaders.com/shader/toon-shader-contact-shadows/) | Evident | **CC0 1.0** | screen-space contact shadows, which a directional light alone does not give a toon material |
| ["Advanced ANIME SHADER in Blender"](https://www.youtube.com/watch?v=UfFQLAtfuOo) | Aku (@AkuVisuals) | tutorial (technique, not an asset) | the Blender-side node group: the ramp/rim/specular structure the Godot shader must match |

**Only shader CODE is taken, and never a model** (the user's rule): the characters shown on those pages are not
covered by the shader's own licence. The MIT notice ships with the build, as Johnny Rouddro's does.

### 4b. What we TAKE from a VRM: the TEXTURES, never the materials (user, 2026-09-19)

**The goal is to extract the texture maps and rebuild the shading ourselves** (§4). MToon's material graph is
discarded with the addon; the images it points at are the asset, and they are already exactly the maps a toon
shader wants. Measured on Shino — **29 images, 17 materials, every material MToon**:

| MToon slot | what it is | files in Shino | take it? |
|---|---|---|---|
| `_MainTex` (glTF `baseColorTexture`) | base colour | `Face`, `Body`, `Tops`, `Bottoms`, `Shoes`, `Hair_00_01/02`, `HairBack`, `EyeIris`, `EyeWhite`, `EyeHighlight`, `FaceBrow`, `FaceEyelash`, `FaceEyeline`, `FaceMouth`, `Accessory` | **yes** — the whole look |
| `_BumpMap` (glTF `normalTexture`) | normal maps | `Face_00_nml` 379 KB, `Body_00_nml` 2 091 KB, `HairBack_00_nml` 360 KB, `Hair_00_nml` 103 KB | **yes**, then MEASURE whether they earn their keep: the weapon import already found a CC0 pack's normals changing a first-person frame by 0.35/255, and a flat toon material may not read them at all |
| `_OutlineWidthTexture` | a per-pixel mask painted on the FACE (`Face_00_out`) | 1 | **yes, and it is the interesting one** — it is the same kind of authored face mask §4's MIT face shader wants, i.e. the face's shading is already authored as a map rather than left to its normals |
| `_SphereAdd` | matcap rim (`Matcap_Rim`, `Matcap_RimHair`) | 2 | **as reference only** — a matcap bakes a light direction into the texture; our shader computes the rim, so these say what the rim should LOOK like |
| `_ShadeTexture` | MToon's shadow-side colour | 17, mostly the same image or a black placeholder | **no** — our ramp replaces it |
| `_spe` (hair) | hair specular strip | 1 | judge by eye against our shader's specular |
| `Shader_NoneNormal`, `Shader_NoneBlack` (×2) | MToon's 0 KB "no texture" stand-ins | 3 | **no** — drop |
| `Thumbnail` | the VRoid Hub card image, 2.5 MB, in no material | 1 | **no** — drop |

Blender's stock glTF import already does most of that sorting for us: it brought in **19 images** of the 29,
leaving the empty placeholders and the thumbnail behind.

So the conversion's material step is: keep every `_MainTex` and `_BumpMap` as a file, drop the rest, and rebuild
**one** toon material per body region (skin / hair / eyes / clothing) that reads them — which is also how the
17-materials-to-7 gap in §5 closes, and the whole reason the crowd can afford it.

---

## 5. Measured deltas — what a swap changes, and what must be re-measured

Godot-chan read from `merged_animation.glb`; the VRoid rows read from their `.vrm`. The arm figure reproduces
W24's independently measured 0.416 m exactly, which is what says the method is sound.

| | Godot-chan | Shino (F, CC0) | Fumiriya (M, CC0) |
|---|---:|---:|---:|
| height | **1.49 m** (crown 1.435) | 1.645 | 1.909 |
| eye (bone) | — | 1.481 | 1.732 |
| arm, shoulder → wrist | **0.416 m** | 0.434 | 0.469 |
| arm / height | 27.9 % | 26.4 % | 24.6 % |
| leg, hip → ankle | 0.704 m | 0.792 | 0.971 |
| triangles | **48 104** | 31 211 | 39 548 |
| materials | **7** | 17 | 17 |
| meshes | 9 | 3 (4 as imported) | 3 |
| morph targets | 0 | 41 | 39 |
| spring-bone groups | 0 | 17 | 13 |
| skeleton nodes | 63 (53 joints) | 163 (54 humanoid) | 122 (54 humanoid) |

**Three findings worth having before anyone starts.**

- **A VRoid avatar is CHEAPER in triangles than Godot-chan** (26.7 k–40.0 k against 48.1 k). PLAN.md's
  "~50–100 k triangles" was an estimate and is wrong — corrected. What is genuinely more expensive is
  **materials (17 vs 7)**, i.e. draw calls, plus 40-odd morph targets and 13–22 spring-bone chains that nothing
  in this game uses. That is the whole argument for §4's single toon material: the crowd cost (3.6d) is draw
  calls and per-node work, not triangles, which is exactly what `probe_city_perf.gd` already measured for
  pedestrians.
- **A taller body helps the support hand, but the PROPORTIONS are worse, not better.** W24's open compromise is
  SHG1's pump sitting 4.0 cm beyond this arm's reach. Shino's arm is 0.434 m (+4.3 %) → ~3.2 cm short;
  Fumiriya's is 0.469 m (+12.7 %) → ~0.6 cm short, i.e. effectively closed. But arm/height goes 27.9 % → 26.4 %
  → 24.6 % (a human is ~33 %), so **the gain is pure size, not better proportion** — scaling any of these bodies
  down to 1.49 m would put the reach problem straight back.
- **Weapon proportion improves.** SNR1 is 1.124 m: 75 % of Godot-chan's height, 68 % of Shino's, 59 % of
  Fumiriya's (a 1.75 m human holding an AWP is ~64 %). Shino lands closest to life; Fumiriya at 1.909 m is
  taller than a game male usually is and would want scaling — which, per the point above, costs reach.

**What must be re-measured on the new body — DONE, and every one of them is now derived rather than authored**
(`tools/godot/measure_body.gd` is the one owner; CLAUDE.md "W41" is the record):

| number | how it is decided now | gate | Shino | Fumiriya |
|---|---|---|---|---|
| FPS eye mount | the EYE surfaces' centroid | `probe_character_visuals.gd` | 1.477 m, 7.0 cm in front | 1.727 m, 8.5 cm in front |
| `SocketRifle/Pistol/Launcher/Melee/Fist/Throwable` | transferred through the body's own HAND frame | `probe_weapon_fit.gd`, `probe_character_visuals.gd` | PASS | PASS |
| `StockMountIKModifier` mount anchors | the skin's pocket, measured by the gate (`--emit-pocket`) | `probe_weapon_fit.gd` | PASS | PASS |
| holster slings | the W28 design over this body's own back surface | `probe_weapon_holster.gd` | 1 FAIL (the axe, 0.093 m vs a 0.10 m limit) | PASS |
| stance capsules | the posed, skinned body; one radius per body | `probe_character_visuals.gd` | PASS | PASS |
| ragdoll / hitbox capsules | the skin's thickness around each bone | `probe_character_visuals.gd` | thinnest 2.4 cm | thinnest 2.8 cm |
| bone hit multipliers | unchanged — the bone NAMES are the contract | the net gates | n/a | n/a |
| every aim limit | unchanged — a `Stance` fact, not a body fact | `AimDebugAuto` | n/a | n/a |
| cockpit eye `Seats/Seat0/CockpitCameraMount` | **still the reference's** — it is a fact about the SEAT and the body in it | `probe_vehicle_views.gd` | not re-measured | not re-measured |

Still failing, and each is recorded with its cause in CLAUDE.md "W41": Shino's support hand on the two longest
handguards (7.8 / 8.6 cm — her shoulders are 7.8 cm narrower, which moves her left hand that far from a gun held
on the right), her axe's 7 mm clearance miss on the back sling, and a taller body crouching less deep because a
position key is absolute metres.

---

## 6. Order of work, and what is NOT decided

1. Record the licence rows (**done**, `assets/LICENCE_AUDIT.md`), and the shader credits (**done**, `CREDITS.md`).
2. Bring the bodies in (**done** — both, `blender/tools/import_vrm_body.py`; spring bones and MToon dropped).
3. The bone rename and rest conform (**done**, and the clips are shared rather than retargeted —
   `blender/SKELETON_CONTRACT.md`).
4. `CharacterVisuals_<Body>.tscn` + `MeshConfig` (**done**, and GENERATED from measurements rather than
   authored — CLAUDE.md "W41"); the §5 gate list re-run and what fails recorded above.
5. Next: the toon shader (§4, 6.10), the 17-material merge, and a hold pose for whichever body ships.

**Not decided here, on purpose:**

- **Which body ships as the player.** Shino is the closest to this game's weapon scale; Fumiriya nearly closes
  W24. That is an art call, and both are CC0.
- **Whether Godot-chan is retired or kept as a second variant.** W18 made the character a swappable
  `CharacterVisuals_*.tscn`, so keeping it costs nothing and it is the control for every measurement above.
- **Face rig.** 40-odd VRM blend shapes are a facial-expression set this game has no system for. Dropping them
  is the cheap default; a dialogue system would be the reason to keep them.
- **Hair and skirt.** Without spring bones they are rigid. Either weight them to a few bones by hand, or model
  them short. A crowd's hair must not be a per-frame solve.
