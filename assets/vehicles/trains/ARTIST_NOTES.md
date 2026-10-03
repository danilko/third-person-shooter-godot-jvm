# EMU1 — artist notes (placeholders to replace)

`EMU1.blend` is the owner of the train. `blender/tools/make_train.py` built it once; it never overwrites the file again
without `--force`. Re-running it with no flag only EXPORTS what is in the file (`EMU1_Tc.glb`, `EMU1_M.glb`) and
re-measures `EMU1.train.json`, which the game and the gauge checks read. After an edit:

    blender -b --python-exit-code 1 --python blender/tools/make_train.py
    godot --headless --path . --import

then `tools/godot/probe_train_board.gd` (doors, boarding, riding) and `tools/godot/probe_train_fit.gd -- --stations`
(it still fits every platform).

The car is a generic 20 m, 4-door Japanese commuter car on the 1067 mm gauge (the E231/E233 envelope). Copy no line's
livery, logo or name. Frame: the car faces Blender +Y, X across, Z up, origin on the rail head at the car's centre.
Two collections, `EMU1_Tc` (cab car) and `EMU1_M` (middle car, pantograph). Every object name starts with its car's
prefix (`Tc_` / `M_`), because object names are global in a .blend.

## What the game reads by NAME — keep these names

| object | what it is | rule |
|---|---|---|
| `<car>_Door_<P\|N><i><a\|b>` | one door leaf | P = the +X side, N = −X. `i` counts along +Y. `a` is the leaf toward −Y (it slides −Y), `b` slides +Y, by 0.62 m (`DOOR_OPEN`). Its ORIGIN is the leaf's centre when shut; the game slides it from there. |
| `<car>_COL_*` (empty, cube) | a collision box | scale = half size. The game builds the car's collider from these: floor, roof, walls with the doorways open, end walls with the gangway open, benches. Move or resize them with the geometry. |
| `<car>_DOORCOL_<P\|N><i>` | the collider that closes doorway `<i>` | it is switched off while that door is open. |
| `<car>_LIGHT_*` (empty, sphere) | where an interior light hangs | each becomes a small shadowless light in game. |

The outer envelope (`PROFILE`, 1.491 m half width with the door frames, 4.05 m to the folded pantograph) is what every
station, platform gap and track spacing was measured against. Keep the car inside it, or re-run the gauge probes.

## Placeholders to replace (all in `<car>_Interior` unless noted)

- **Long bench seats (ロングシート)**: blue cushions per seat (0.46 m), backrest, base. Shape, the seat dividers, and the
  moquette pattern are art.
- **Priority seats (優先席)**: the bench at each car's −Y end is red/orange, with yellow poles and yellow straps over it.
  The priority-seat stickers and the floor marking are missing.
- **Partitions at the doors (袖仕切り)** and **vertical poles** (one per long bench, one at each partition).
- **Luggage racks (網棚)** over every bench: a flat slab; the real one is a mesh or bar rack.
- **Grab rails and hanging straps (吊り革)**: two longitudinal rails, straps every 0.32 m, ring handles. Triangle
  handles, ads on the straps and the cross-car rails at the doors are missing.
- **Lighting**: two LED lines in the ceiling plus an air-conditioning diffuser down the middle.
- **Door-top screens (ドア上LCD)**: a dark emissive box over every door inside. No content.
- **Floor**: grey vinyl with a yellow line at each doorway.
- **Wheelchair space**: on a middle car's +Y end, one side has no bench, only a padded wall and a handrail. The
  wheelchair sign is missing.
- **Cab (Tc only)**: a partition with a window and a shut door, the driving desk, the one-handle controller and the
  driver's seat on the left. All are boxes.
- **Gangway (貫通路, in `<car>_Body`)**: an open opening with bellows and a footplate, so a player can walk the whole
  train. Real cars often have a gangway door; adding one needs a matching `COL_`.
- **Outside (`<car>_Body`)**: the colour band is a generic green; the destination sign is black. Glass is one
  see-through material.

## Not modelled yet

Hanging adverts (中吊り), the route map over the doors, the emergency intercom, door-open lamps over each door
(outside), a working destination display, and car numbers.
