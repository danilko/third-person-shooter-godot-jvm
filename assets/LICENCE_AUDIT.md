# Asset licence audit (2026-09-18)

The project rule: every model, texture, sound and font must be CC0, MIT or public domain, or listed with its
licence in `CREDITS.md`. Map data is CC0/MIT/public domain only; no PLATEAU data remains (2026-09-18: PLATEAU is used
only to MEASURE sizes, locally, and credited as thanks). **Never add** anything whose page only licenses "the models" (its textures may
not be redistributable), anything from Pexels, Unsplash or Textures.com, or anything "free for personal use".
CC0 texture sources that are fine: ambientCG, Poly Haven.

Method: every tracked or new model/texture/audio/font file (`git ls-files` + untracked, not ignored) grouped by
folder and matched to a CREDITS.md row; a folder with no row was opened and traced.

| group | files | source / licence | status |
|---|---|---|---|
| `addons/jvm`, `addons/terrain_3d` (+ `demo/`), `addons/sky_3d` | icons, brushes, noise, demo meshes | MIT, each with its LICENSE file | ok |
| `addons/sky_3d/.../milkyway/` | Milkyway.jpg, StarField.jpg | ESO, **CC BY 4.0**, credited | ok (attribution required). Could be swapped for a public-domain NASA star map if we want no CC BY at all |
| `addons/kenney_prototype_textures` | grids | CC0 | ok |
| `assets/characters/godot_chan`, `assets/audio` | model, textures, 4 wavs | Johnny Rouddro, MIT, credited | ok |
| `assets/Universal*Animation*Library*` | clips | Quaternius, CC0, credited | ok |
| `assets/weapons` REV1 SMG1 | models | Quaternius 50 Low-poly Guns, CC0, credited | ok |
| `assets/weapons` ASR1 ASR2 SHG1 FRG1 PIB1 FLA1 SMO1 REC1 + `textures/<id>_base_color.png` | models | 3DModelsCC0 Free CC0 Guns & Explosives Pack, CC0, credited (2026-09-19: re-imported by `import_guns_pack.py`; the download was removed from the repo after import) | ok |
| `assets/weapons` MEW1-7 + `textures/` | models, 28 textures | 3DModelsCC0 melee pack, CC0, credited | ok |
| `assets/weapons` ATL1, FRG1, ATL1_Rocket, SHI1 | primitives | this project | ok |
| `assets/weapons/SNR1` (was `SR3`, added e9ede64) | sniper rifle model | was Quaternius 50 Low-poly Guns (CC0, owner confirmed 2026-09-18); replaced 2026-09-19 by the Guns & Explosives pack model, and back to Quaternius `SniperRifle_3` on 2026-09-21 (50 Low-poly Guns, CC0, `license_link.txt`); PIS1 / PIS2 / DUP1 are Quaternius `Pistol_5` / `Pistol_6` / `Pistol_1` from the same pack | ok |
| `assets/vfx` | effects, water shader | Binbun3D, CC0, credited | ok |
| `assets/terrain3d` | ambientCG CC0 + generated | credited | ok |
| `assets/ui` | Aldrich font (OFL 1.1), generated icons, `white.png` | credited / ours | ok |
| `assets/world_source/kits/quaternius_*` | kits | Quaternius, CC0, credited | ok |
| `assets/world_source/kits/quaternius_stylized_nature` | vegetation kit | Quaternius Stylized Nature MegaKit (Standard), CC0 1.0 (`License.txt` kept at the kit root), credited | ok |
| `assets/world_source/kits/road_kit`, `pieces/`, road glTFs in `src/.../pieces/` | ours | this project | ok |
| `assets/world_source/kits/library` | our modelled pieces, 21 placeholder boxes, ambientCG CC0 textures, generated textures | ours / ambientCG CC0 (`textures/SOURCES.md`) | ok. **2026-09-28: the 21 elbolilloduro-derived base meshes were REMOVED** (provenance not confirmable) and are same-size placeholders listed in `placeholders.json` |
| `assets/vehicles` | SPC1 (project author's model); PIT1, POC1 placeholder blocks (ours) | ours | ok. **2026-09-28: the PIT1/POC1 geometry from elbolilloduro's "Vegetation" pack was REMOVED** and replaced by placeholders of the same size and component split |
| elbolilloduro downloads | 7 packs (incl. Vegetation, 2026-09-19) | models CC0, textures partly Textures.com/Pexels | **removed** from the repo folder; `.gitignore` refuses `kits/elbolilloduro*/` |
| all PLATEAU-derived files: `assets/world_source/plateau/` (42 precincts), `PLATEAU_RainbowBridge/HanedaTerminal/TokyoTower.blend`, `RecycledBuildingKit.blend`, `plateau_reference/`, `archive/world_6x6/` | PLATEAU CC BY (Tokyo Tower was ours) | **deleted** (owner, 2026-09-18) after the landmarks were rebuilt as our own base models (`kits/library/`, `TokyoStation`, `AirportTerminal` and the rest) from PLATEAU measurements; nothing used them |
| `archive/retired_road_model`, `assets/world_source/island_v3*.blend` | ours | this project | ok |
| `images/screenshot*.png`, `assets/world_source/reference/map_plan_*.png` | ours | this project | ok |
| VRoid `.vrm` sample avatars (`/data/danilko/game_assets/cc0 vrm/`, **outside the repo**) | 11 models + 6 FAQ PDFs | pixiv / VRoid Project. Each file's own `VRM.meta` carries a fully permissive VRoid Hub licence (`modification=allow`, `redistribution=allow`, `corporate_commercial_use=allow`, `credit=unnecessary`); the FAQ PDFs confirm **CC0** in prose for **Sendagaya Shino** and **Sakurada Fumiriya**, and warn that `AvatarSample_A/B/C` (none present) have their own conditions | ok. **Two are now in the repo** (PLAN.md 6.9): `assets/characters/shino/` (Sendagaya Shino, `4537789756845150029.vrm`) and `assets/characters/fumiriya/` (Sakurada Fumiriya, `2233030527144754025.vrm`) — the two with a CC0 FAQ page of their own, converted by `blender/tools/import_vrm_body.py` (geometry, skeleton and textures; MToon materials, spring bones and expression morphs dropped). The source `.vrm` files are read and never modified. **`6806103343691492736.vrm` is by a third-party VRoid Hub user (`しげぽんしげぽん`), not pixiv, and no FAQ page covers it — do not import** |
| Toon character shaders (godotshaders.com) | 2 shaders, not yet in the tree | Evident — face shader **MIT**, contact shadows **CC0 1.0**; licences read on each shader's page and credited | ok (PLAN.md 6.8 §4). **Shader CODE only — never a model from those pages** |
| PLATEAU-derived files in **git history** (precincts, districts, baked district glTF/scn, `PLATEAU_*.blend`) | CC BY 4.0 | not at HEAD, but still in every pushed branch's history; attribution kept in CREDITS.md. Removing it needs a history rewrite + force push (backup of `.git` taken 2026-09-19 in `../third-person-shooter.git-backup-2026-09-19`) | open (owner decision) |

## Cleanup 2026-09-19

Removed from the tree (still in history): the Guns & Explosives download `assets/weapons/free-cc0-melee-weapons-pack/`
(86 MB; one-shot input to `import_guns_pack.py`, the melee-pack precedent), `demo/` (Terrain3D's demo, unused),
`merged_animation*.pre-A24.blend` (local backups), the UAL `*_RM.glb` root-motion variants (unused by
`retarget_ual.py`), `quaternius_downtown_city/source/` (raw download, the kit `.blend` owns the pieces) and a stray
PLATEAU extractor log. The UAL folders got `.gdignore` (Blender-only sources). The `.bin` buffers of every committed
glTF are now committed through LFS (they were caught by `*.bin` in `.gitignore`).

## Audit 2026-09-28 (owner: "remove anything from elbolilloduro; keep only sources we can confirm")

File-level, not folder-level. Checked: every image file on disk under `assets/`, `src/`, `addons/`; every image
referenced by a Godot `.tres`/`.tscn`; every image embedded in or referenced by all 664 `.glb`/`.gltf`; and every
image datablock (packed or external) in all 62 `.blend` files. **No elbolilloduro texture was found anywhere**; each
image traces to a row above. What remained from elbolilloduro was GEOMETRY: 21 library base meshes (and their copies
inside `kits/shops/Shop_*.blend`) and the PIT1/POC1 car models. All were replaced by same-size placeholders.

Left for the owner to decide: `assets/world_source/store/6a8fbe75-...jpeg` is a floor-plan brief with no metadata
(it appears generated); it is design input, not shipped. Several weapon `.blend`s still carry DANGLING image paths
to the deleted download folders (`//free-cc0-melee-weapons-pack/...`, a `/Blender/DavidThorn/Library/Large/Texture.png`
in REV1/SMG1/SNR1): the files are not in the repo and nothing uses them (each weapon's material uses
`weapons/textures/<id>_base_color.png`), so they are harmless leftovers of the imports.
