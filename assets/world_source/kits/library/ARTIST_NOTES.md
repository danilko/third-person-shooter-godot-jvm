# library.blend -- notes for the artist

`library.blend` is the project's own model library (CC0, ours). Every piece is a COLLECTION named after it, holding
one object, laid out on a grid (the collection's `instance_offset` is its grid spot; the export moves it back).

## Edit a piece

1. Open `assets/world_source/kits/library/library.blend`, find the collection, edit the object.
2. Keep the FRAME: Z up, origin at the footprint centre on the ground, the side a person uses facing **-Y**
   (the game's +Z, the building convention). Real size, in metres.
3. Read the piece's `edit_note` (Object or Collection Properties > Custom Properties): what else in the project
   assumes something about this model, and has to move with it.
4. Run `tools/building_kit/build_buildings.sh` (exports the pieces, rebuilds the building scenes, runs the probe).
   A piece whose bounds changed is refused until you re-run with `ACCEPT_BOUNDS=1` -- on purpose.
5. Materials: use the palette's names (`MI_*`); their look is `palette.json` -> `materials/MI_*.tres`
   (`tools/building_kit/build_library_palette.py`), not the Blender node values.

## Your edits are safe

Some pieces are GENERATED from code (`blender/tools/library_procedural.py`, `library_landmarks.py`, flagged
`lib_procedural`). Each remembers a fingerprint of its mesh and materials (`lib_generated`). Once you edit one, the
fingerprint no longer matches and `build_library.py --procedural` KEEPS your version (it says so). Only
`--force` or `--only=<Name>` regenerates a piece on purpose.

## Pieces that other files depend on

| piece | what depends on it |
|---|---|
| `Harbour_Crane` | its COLLIDER is `CRANE_BOXES` in `tools/building_kit/site_container_terminal.py` (bogies, legs, portal and girder beams), not its mesh: update the boxes with the model. Rails 30.48 m apart along Y (sea -Y), portal clear 18 m; nothing may overhang -Y past the seaside rail + 2 m. |
| `Harbour_LightMast` | collider `MAST_BOXES` in the same file. |
| `Harbour_Apron` | tiled 10 x 6 by the terminal: must stay 36.4 m square, top at Z 0. |
| `ShuriCastle` | the platform (25 m) is sized to the measured site (`tools/island_sites.py`): its top must clear the uphill ground. Faces -Y towards downtown. Collider = its mesh. |
| landmarks (`RainbowBridge`, `TokyoStation`, ...) | see `blender/tools/library_landmarks.py`; the Rainbow Bridge's two road levels are Road Kit roads (`RB_ROAD_LOWER`/`RB_ROAD_UPPER`). |

Containers, pallets, drums, cones and the expressway's median panel are NOT here: they are Quaternius' (CC0), owned by
`assets/world_source/kits/quaternius_zombie_apocalypse/blends/` (see its README).
