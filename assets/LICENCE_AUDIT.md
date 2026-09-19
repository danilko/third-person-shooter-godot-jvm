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
| `assets/weapons` ASR1 ASR2 PIS1 SHG1 SNR1 FRG1 PIB1 FLA1 SMO1 REC1 + `textures/<id>_base_color.png` | models | 3DModelsCC0 Free CC0 Guns & Explosives Pack, CC0, credited (2026-09-19: re-imported by `import_guns_pack.py`; the download was removed from the repo after import) | ok |
| `assets/weapons` MEW1-7 + `textures/` | models, 28 textures | 3DModelsCC0 melee pack, CC0, credited | ok |
| `assets/weapons` ATL1, FRG1, ATL1_Rocket, SHI1 | primitives | this project | ok |
| `assets/weapons/SNR1` (was `SR3`, added e9ede64) | sniper rifle model | was Quaternius 50 Low-poly Guns (CC0, owner confirmed 2026-09-18); replaced 2026-09-19 by the Guns & Explosives pack model (row above) | ok (resolved) |
| `assets/vfx` | effects, water shader | Binbun3D, CC0, credited | ok |
| `assets/terrain3d` | ambientCG CC0 + generated | credited | ok |
| `assets/ui` | Aldrich font (OFL 1.1), generated icons, `white.png` | credited / ours | ok |
| `assets/world_source/kits/quaternius_*` | kits | Quaternius, CC0, credited | ok |
| `assets/world_source/kits/road_kit`, `pieces/`, road glTFs in `src/.../pieces/` | ours | this project | ok |
| `assets/world_source/kits/library` | 24 re-textured base meshes (elbolilloduro models, CC0), our modelled pieces, ambientCG CC0 textures, generated textures | credited; the packs' own textures are NOT used and the downloads are not in the repo | ok (resolved 2026-09-18) |
| `assets/vehicles` | SPC1 (project author's model); PIT1, POC1 (elbolilloduro "Vegetation" pack models, CC0), all flat materials of our own | credited; the Vegetation pack's textures (`Car_ex`, `Car_in`, `Car_sheriff*`, `Tire`) are NOT used: its page licenses only "the models" | ok (2026-09-19) |
| elbolilloduro downloads | 7 packs (incl. Vegetation, 2026-09-19) | models CC0, textures partly Textures.com/Pexels | **removed** from the repo folder; `.gitignore` refuses `kits/elbolilloduro*/` |
| all PLATEAU-derived files: `assets/world_source/plateau/` (42 precincts), `PLATEAU_RainbowBridge/HanedaTerminal/TokyoTower.blend`, `RecycledBuildingKit.blend`, `plateau_reference/`, `archive/world_6x6/` | PLATEAU CC BY (Tokyo Tower was ours) | **deleted** (owner, 2026-09-18) after the landmarks were rebuilt as our own base models (`kits/library/`, `TokyoStation`, `AirportTerminal` and the rest) from PLATEAU measurements; nothing used them |
| `archive/retired_road_model`, `assets/world_source/island_v3*.blend` | ours | this project | ok |
| `images/screenshot*.png`, `assets/world_source/reference/map_plan_*.png` | ours | this project | ok |
| PLATEAU-derived files in **git history** (precincts, districts, baked district glTF/scn, `PLATEAU_*.blend`) | CC BY 4.0 | not at HEAD, but still in every pushed branch's history; attribution kept in CREDITS.md. Removing it needs a history rewrite + force push (backup of `.git` taken 2026-09-19 in `../third-person-shooter.git-backup-2026-09-19`) | open (owner decision) |

## Cleanup 2026-09-19

Removed from the tree (still in history): the Guns & Explosives download `assets/weapons/free-cc0-melee-weapons-pack/`
(86 MB; one-shot input to `import_guns_pack.py`, the melee-pack precedent), `demo/` (Terrain3D's demo, unused),
`merged_animation*.pre-A24.blend` (local backups), the UAL `*_RM.glb` root-motion variants (unused by
`retarget_ual.py`), `quaternius_downtown_city/source/` (raw download, the kit `.blend` owns the pieces) and a stray
PLATEAU extractor log. The UAL folders got `.gdignore` (Blender-only sources). The `.bin` buffers of every committed
glTF are now committed through LFS (they were caught by `*.bin` in `.gitignore`).
