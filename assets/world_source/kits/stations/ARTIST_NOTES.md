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
* **LIFT_ Empties** (small cubes) are the station LIFTS: `world.Elevator` builds the moving car, its two-leaf
  centre-opening sliding doors and the landing doors from one, never modelled. It sits at the centre of the shaft's
  floor at the LOW stop; custom props `w` / `d` (the shaft's inside along X / Y), `rise` (to the top stop), `door_w` /
  `door_h`. The SHAFT around it is the piece's own mesh and `COL_` boxes (glass walls, metal posts): keep a door
  opening, `door_w` wide and `door_h` tall, centred in BOTH X faces at EVERY stop, and nothing else open -- the doors
  face along the track, never the rail side. Leave a pocket each side of an opening at least half the door wide (the
  leaves slide into it). Keep the lift at least 3 m (`station_layout.LIFT_GAP`) beyond the stair's TOP end, so its
  doors never open into the stair's queue.
* **Stair balustrades** (glass panel + handrail, stepped with the flight) stand on both long sides of every stair; the
  `COL_` box along an open side is what keeps anyone from stepping off it. On a side against a wall only the handrail
  is drawn.

* **Every station entrance is a ROLLER-SHUTTER opening** (user, 2026-09-27): no swing or slide door, open all day.
  No post in between: the opening is framed only at its two sides, with a guide rail down each and, over it in the
  header, the housing the shutter rolls up into (its bottom bar showing). Keep it clear -- it is the way in. An
  ordinary entrance is 4 m; a LARGE hub's is 11.8 m (`station_layout.LARGE_ENTRANCE_W`). A shutter that comes down at night is a later runtime item.
* **The large hubs** (every hub but Fish Market, a standard-size station on the hub form) also have STORES. Every station
  store's front is glazed with a SLIDING GLASS door (user, 2026-09-28): a `DOOR_` arrow (style `slide_glass`, `w` 1.6
  = two leaves, 0.9 = one) at the doorway's centre, just inside the fixed glass, pointing out into the hall; the game
  hangs the glass leaves, which slide behind the fixed glass either side -- keep that glass clear of anything solid.

* **Restroom fixtures are LIBRARY pieces** (the konbini's kit: washlet toilet, square basin, mirror, stall partitions,
  grab rail, baby table). Each is a `PROP_` Empty showing the linked library piece: MOVE or TURN the Empty to move the
  fixture; its custom prop `piece` says which library piece it is (`library:WC_Toilet`), `collide` whether it blocks
  (`box`) or not (`none`). To change what a toilet LOOKS like, edit it in `kits/library/library.blend` -- every station
  and konbini picks it up. The accessible room's door is a `DOOR_` arrow (style `slide`): a solid sliding leaf the game
  hangs on the hall face; keep the wall beside the doorway clear for it to run over.

## Ground hub (`Station_GroundHub.blend`)
* Cap pieces (`GH_Cap*`, `GH_Annex_*`) have their origin at the BED (track) level. The concourse
  floor's top is 6.2 m over the bed and its underside 5.9 m: nothing in `GH_CapLane` may come lower -- the train and
  its overhead line pass under it.
* `GH_CapWall_Door`'s opening (along X -8..-2, at the concourse level) must meet the annex's landing; the annex's
  stair must arrive on that landing at 6.2 m.
* The annex's street door is in its outer face (along X 9..13); the `GATE_` Empties sit on the fare line between the
  gate cabinets, arrows to the street side. The SERVICE COUNTER stands on the fare line beyond the gates, out to the
  end wall: keep the line closed from end wall to end wall (railing, cabinets, counter).
* The annex's amenities: a RESTROOM BLOCK on each side of the fare line (the paid one under the mezzanine landing,
  against the cap wall; the unpaid one against the street wall) and the ticket / ATM / vending machines beside the
  unpaid one. Keep a walkway in front of each (the paid walkway runs from the gates to the stair foot and the lift).
* `GH_Entry_<n>_<L|R>` is the stair + smooth 1:15 slope outside an annex door whose street is lower (the open-air
  entry, n risers of 0.165 m); its origin is the door's centre at the floor, and the layout turns it out to the street.
  `GH_EntryWide_<n>_<L|R>` is the same across a large hub's whole 11.8 m opening (a middle handrail on the stair).
* A LARGE hub uses `GH_AnnexLarge_*` (the 11.8 m opening, along X 2.6..14.4) and ONE store, `GH_AnnexStore_*`, past the
  annex's +X end (10 m, the annex's depth, its floor the hall's). The store opens ONLY into the unpaid hall: its glass
  front and door are `GH_AnnexLarge_*`'s +X end wall (the part beside the paid strip and the service counter stays
  solid), so the store piece has no wall on its -X side. Its street side is display glass, no door. Its back wall
  faces the platform, whose fence is 0.3 m behind it: keep that wall.
* Every platform's lift is in its cap bay (`GH_CapPlatform_*`, `GH_CapIsland_*`: platform -> concourse, the stair's
  width square, in line with the stair), and the annex has one in its PAID strip (street -> concourse, behind the
  gates): so the whole way from the street to a platform has a lift.
* `_L` / `_R` are mirror images: change both.

## Elevated hub (`Station_ElevatedHub.blend`)
* Every piece's origin is on the LANE's centre line at BED level (the viaduct's own height); hand `_L` builds the +Y
  (left) side, `_R` is its mirror. The F1 floor's top is the street, 7.84 m BELOW the origin (the rail plan's viaduct:
  every elevated station stands on it at that height).
* The rail's own deck (+-5.0 m from the lane, 0.8 m deep) is NOT a piece -- the rail record builds it. The side pieces'
  roof slab starts at its edge; nothing a piece owns may enter the track band (+-3.55 m) between 0.5 and 4.2 m over the
  bed. Over the station the rail puts no pier: the `EH_Floor_*` columns carry the deck.
* **F1 is a PAID BOX ringed by the unpaid hall** (user, 2026-09-27): both stairs and both lifts are inside the box; the
  unpaid hall is the two WINGS along the long sides (5 m past the rail wall, a single-storey roof 4.6 m over the
  street) and the two ends of the hall. A wing module is one of: `EH_WingEntrance_*` (THREE modules long, a six-bay
  roller-shutter entrance -- one near each end of each side, and on a long station also one beside each end of the
  paid box), `EH_WingMachines_*` (beside each end fare line) or `EH_WingShop_*` (every other module: a shop 2.4 m deep
  against the outer wall, its glass front and sliding door on the hall -- keep the 2.3 m walkway before it).
  The box is closed on all FOUR sides: across the hall at each end (`EH_FloorGate_*`, its railing reaching the rail
  wall's outer face), and along each long side in the rail wall's line (`EH_FareSide_*` a railing, `EH_FareSideGate_*`
  a gate bank in the module's -X half, arrows toward the wing). Keep every fare line closed end to end, and keep them
  meeting at the corners, or the paid area leaks round the gates.
* At F1 the rail wall's line is open: a column at each module's +X end (`EH_Side_*`) under a beam at the ceiling. Along
  the stair (`EH_SideStair_*`) the rail wall comes down to the floor -- the stair's own wall.
* The hall has a lowered CEILING 3.8 m over the street (visual only), open over the stairs; a bulkhead closes the
  stair's open side from the ceiling up to the platform slab. The raw viaduct soffit is hidden above it.
* `EH_SideStair_*` (20 m long) holds the stair from F1 up to the platform: three flights, two landings, rising toward
  -X. Its top must arrive on the stair band's slab at the platform level (1.26 m); the railing along the platform edge
  over the stair well keeps anyone from stepping off the platform into it.
* `EH_SideLift_*` (5 m) holds each side's lift, F1 -> platform, in the stair band just beyond the stair's top end.
* **More than one lane (Central: three lanes 14 m apart).** The side pieces (`EH_Side_*`, `EH_Wing*`, `EH_FareSide*`,
  `EH_Platform_*`, `EH_EndFence_*`) stand outside the two OUTERMOST lanes, exactly as on a one-lane station. Between
  two lanes the platform is an ISLAND: `EH_Island_<w>` (5 m), `EH_IslandStair_<w>` (20 m) and `EH_IslandLift_<w>`
  (5 m), origin on the island's centre line at bed level. Each carries the platform (both long faces are track edges),
  the slab filling the 4 m gap between the two lanes' viaduct decks, the F1 ceiling under that gap and the shed on a
  row of columns on the centre line. The island's stair and lift stand in that gap, on the centre line, 2.5 m wide:
  keep them inside it (the decks are the rail record's) and keep 1.5 m of platform beside the stairwell.
  `EH_IslandEndFence_<w>` closes each island's ends. The whole-building pieces are named for the lane set:
  `EH_Floor_345_3x14`, `EH_FloorGate_345_3x14` (a bank of four gate lanes under each lane) and `EH_EndWall_345_3x14`.
* **Amenities (step 6b).** `EH_Restroom` (men / women / accessible, doors facing -Y) stands free on F1 under the
  middle lane, between its deck's two column rows (their faces 4.1 m either side of the lane): one inside the paid box
  over the stair span, one in the unpaid end hall just outside the low fare line. Keep it within 2.5 m of its centre
  across and under the 3.8 m ceiling. Each end fare line (`EH_FloorGate_*`) ends at +Y in the SERVICE COUNTER
  (有人改札, staff only, solid), 0.6 m short of the long side's gate bank, with a railing each side of it. The wing
  beside each end fare line is `EH_WingMachines_*`: the ticket machines, an ATM and two vending machines against a
  blank outer wall, facing the long side's gate bank. The amenities fit in the F1 as it is: the building is not wider.

## After an edit
Run `tools/building_kit/build_stations.sh` (exports every station piece, rebuilds the station scenes). If a piece's
bounds changed on purpose, it will ask for `ACCEPT_BOUNDS=1`.

A regenerate by `blender/tools/build_station_blends.py` never overwrites a piece you edited: it reports it as KEPT.
