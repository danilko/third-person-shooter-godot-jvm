# Quaternius Zombie Apocalypse kit -- the models the game builds from

These `.blend` files are Quaternius' (CC0, "Zombie Apocalypse Kit"; `../License.txt`), copied here from the download
(the download itself, `../source/`, has been deleted). They are the OWNERS of these models: edit a file here, then re-run its builder.

| file | becomes | builder | notes |
|---|---|---|---|
| `Container_Red.blend`, `Container_Green.blend` | `Container_20_*`, `Container_40_*` | `blender/tools/build_zombie_yard.py` | fitted to ISO 668 (20 ft 6.058 x 2.438 x 2.591 m; the 40 ft is the same model stretched to 12.192 m), decimated to `CONTAINER_KEEP` (a terminal stands ~800). Model it 20 ft long; a real 40 ft model can replace the stretch. |
| `Pallet`, `Barrel`, `TrafficCone_1`, `PlasticBarrier`, `Wheels_Stack` | `Pallet`, `Barrel`, `TrafficCone`, `PlasticBarrier`, `TyreStack` | `build_zombie_yard.py` | kept at their own size. |
| `TrafficHighwayMidWall.blend` | `HighwayMidWall` (the expressway's median panel) | `build_zombie_yard.py` | turned to run along the road and fitted to 1.1 m (`point_solve.MEDIAN_WALL_HEIGHT`); tiled end to end by its OWN length, so keep the ends flush. The median's collider is a solid prism, not this model. |
| `StreetLights.blend` | `StreetLight_JP`, `StreetLight_JP_Twin` | `blender/tools/build_street_poles.py` | the shaft stretched to a 10 m luminaire (Japanese arterial lighting). |
| `../TrafficLight_2_Japan.blend` | `TrafficLight_JP` | `build_street_poles.py` | the project owner's Japanese re-make of TrafficLight_2; scaled to Japanese clearances. |

After an edit: run the builder (`blender -b --factory-startup --python-exit-code 1 --python <builder>`), then
`tools/building_kit/build_buildings.sh` for the yard pieces or a road-piece build for the poles and the median panel
(the Road Kit digest salts every piece it names, so the build knows).
