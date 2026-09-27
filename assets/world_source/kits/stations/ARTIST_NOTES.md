# Station kit -- notes for the artist

Every station on the island is one of three FORMS, drawn in
`assets/world_source/reference/stations_layout_*_2026-09-27.png`:

* **Open-air** (`Station_OpenAir.blend`): a side platform each side of one double track, each with a shed and a back
  fence, and its own building in line with the platform's END (street -> gates -> steps up -> platform).
* **Ground hub** (`Station_GroundHub.blend`): the tracks at grade, a walled building capping them with an airbridge
  over the tracks (street -> gates -> up into the airbridge -> down to a platform).
* **Elevated hub** (`Station_ElevatedHub.blend`): the platforms up on the viaduct, the F1 building under them
  (street -> gates -> up to a platform).

## What you may change freely
Shape, detail, materials (any name in the library palette), the shed's and building's look, extra props inside.

## What the game assumes -- keep these or the train and the gates break
* **The piece frame:** Z up, X along the track, the TRACK SIDE facing -Y, origin at the footprint centre on the
  piece's own floor. The platform's -Y face is its TRACK EDGE: it stands 1.55 m from the track centre, 1.26 m over the
  bed (1.1 m over the rail head). Nothing may come closer to the track than that edge line: a train is 2.7 m wide.
* **COL_ Empties** (drawn as cubes) are the colliders: the Empty's location is the box centre and its SCALE is the
  half size. Move or scale them when you change a wall; add one for a new solid part (name it COL_<anything>).
* **GATE_ Empties** (arrows) are the ticket-gate lanes: the flaps are built by the game at each one. The arrow points
  to the UNPAID (street) side. Keep one in each gap between two gate cabinets; custom props `w` (lane width) and `h`.
* **Hands:** a building comes as `_L` and `_R` (mirror images, for a platform on either side of the line). A change to
  one should be made to the other.
* **Module length** of platform / shed / fence pieces is 5 m (they are tiled along the platform).

## Ground hub (`Station_GroundHub.blend`)
* Cap pieces (`GH_Cap*`, `GH_Annex_*`, `GH_DoorSteps_*`) have their origin at the BED (track) level. The concourse
  floor's top is 6.2 m over the bed and its underside 5.9 m: nothing in `GH_CapLane` may come lower -- the train and
  its overhead line pass under it.
* `GH_CapWall_Door`'s opening (along X -8..-2, at the concourse level) must meet the annex's landing; the annex's
  stair must arrive on that landing at 6.2 m.
* The annex's street door is in its outer face (along X 9..13); the `GATE_` Empties sit on the fare line between the
  gate cabinets, arrows to the street side.
* `_L` / `_R` are mirror images: change both.

## After an edit
Run `tools/building_kit/build_stations.sh` (exports every station piece, rebuilds the station scenes). If a piece's
bounds changed on purpose, it will ask for `ACCEPT_BOUNDS=1`.

A regenerate by `blender/tools/build_station_blends.py` never overwrites a piece you edited: it reports it as KEPT.
