# rail-and-stations

Moved out of `CLAUDE.md` verbatim on 2026-10-09 (PLAN.md 0.5 / F12). Sections:

- The rail is RESERVED before it is built: elevated in the core, 踏切 outside (PLAN.md B10, 2026-09-25)
- The rail is a MODE of the Road Kit, built against the roads (PLAN.md 3.25 R1/R2, 2026-09-26)
- Stations, 踏切 signals, working traffic lights and real street names (rail batch, 2026-09-26)
- The paid area: ticket gates (2026-09-27; the interim yards and footbridges retired by step 7)
- Station lifts: a through car beside every hub stair, and balustrades on every stair (2026-09-27, user-asked)
- Central is the elevated hub over three lanes; every station is a kit station (PLAN.md step 6, 2026-09-27)
- The open-air station building: restrooms both sides, a service counter, and a straight entry ramp (2026-09-27/28)
- EMU1: the measuring train, and what it says about the platforms (2026-09-29, user-asked)
- Trains you can board: doors, an interior, hits, a wreck and a respawn, and the line on the map (2026-10-02)
- The large hubs: six-bay roller-shutter entrances and shops along the side (PLAN.md step 6b, 2026-09-28)

---

## The rail is RESERVED before it is built: elevated in the core, 踏切 outside (PLAN.md B10, 2026-09-25)

**User decision: the city core (C1's interior) is ELEVATED (連続立体交差), outside it the rail is AT GRADE with level
crossings (踏切).** A road UNDERPASS cannot be built anywhere on this island: the world has ONE water box whose top
is y 0 over the whole world, and the city plain is at 0.6 m, so a road dipped under the rail floods. The plan of
record is `tools/island_rail_layout.py --layout tokyo_straight` (its `crossing: "level"` mode). Each line passes
UNDER C1 at grade (C1's deck leaves no room for a viaduct) and climbs onto the viaduct ~250 m inside the ring at
3.5 %: the profile lays a ramp on the LOWER form's side, so an "elev" breakpoint is set back from C1 by the ramp's
length. An ARTERIAL is never closed: it passes under the viaduct in the core and takes a 踏切 outside (a WIDE one
where two or three lines run side by side at the approach to Central). An oblique or near-junction arterial 踏切
is a NOTE for the rail build, not a blocker.

**The rail geometry is a later piece; what exists now is the RESERVE the derive reads.**
`island_rail_layout.py --layout tokyo_straight --reserve` writes `assets/world_source/buildings/IslandRailReserve.json`
(record frame), and `island_world.sh` runs it at the start of the `layout` stage, because the rail's profile follows
the LAND.
- `corridors`: each line sampled every 10 m with what a street may do there: `level` (a 踏切), `under` (the viaduct),
  or `no`. `no` means a ramp too high to cross and too low to pass under, OR an at-grade sample with another line's
  at-grade sample within 25 m (a multi-track 踏切 is down almost all day, 開かずの踏切). The multi-line test is taken
  against the flags as they were BEFORE any is re-marked, or only one line of each pair is marked.
- `boxes`: each station's platform box and its car park. An ELEVATED station (`street_under`: Central, Suburb,
  Airport) keeps buildings off but lets a street pass under it.
- `island_buildings.rail_reserve` keeps every building off all of it (0.18 km2).
- `island_streets` treats car parks, non-elevated stations and `no` stretches as SITES (a street there is nudged or
  cut), and refuses a street running ALONG a corridor for more than `RAIL_ALONG` (40 m). A street may cross a
  single at-grade line (a 踏切) and pass under the viaduct. Nothing names a closure: the two block streets under the
  core's ramps end at the corridor because the rule says so.

**Three street-planner rules came with it, each a measured defect on the first rebuild** (the core's block streets
went 14 -> 5 and the gate then failed with 10 orphaned points):
- **A line whose OWN course hits a site and that no nudge rescues is CUT, not dropped**, even when a nudge failed
  for another reason (crowding a junction). It used to need EVERY nudge to fail on a site.
- **A nudge is taken over that cut only when it keeps at least as many crossings.** `y=-11` across the core had
  become a 67 m stub of 2 crossings, where the cut kept 9. A nudge that only moves a street off a site's face keeps all
  its crossings and still wins, which is what the nudge is for. The control (no reserve) is unchanged: city 14, SW 103.
- **Segments are numbered per NAME, not per piece** (`build_region`'s `segs_of`). Two pieces of one cut line share a
  base name, so a counter restarting per piece made the second piece's first road overwrite the first's. Its
  points stayed in the record with no road (`point_orphan`). The flow report then came back empty, and
  `island_layout` crashed on `None["open_end"]`.

**EVERY EXPRESSWAY STOOD ON PLAIN BOXES: the preset named a pier the kit does not have** (found by
`probe_road_ground` on the same rebuild). `point_presets`' expressway wrote `pillar_asset: "hammerhead"`, but the kit's
pier is `RKA_PIER_hammerhead`, the name every other record uses. So `point_kit.resolve` found nothing and each of
the island's 30 expressway roads (and both interchange templates) fell back to the plain `rka_pillar_w` box. The
only report was a `missing_style` line in the build output that nothing read. It became visible on the Wangan's
new west-end sea viaduct: a box is sized from the ground at the deck CENTRELINE only, so over a seabed falling 20 m
in 8 m two boxes stopped 19 m short of it, where an asset pier founds each shaft vertex on the ground under itself.
- The preset now names `RKA_PIER_hammerhead`, and **`point_presets`' self-test asserts that every style a preset
  names resolves in the kit** (control: the old name fails, naming the pier).
- The three records were rewritten through `point_model.save_network`. That is equivalent to regenerating them:
  a template regeneration differs from the committed one only in freshly drawn point uids.
- `shuto_wangan_w` is born a RAMP (`branch_ramp`) and takes no preset at all, so `island_expressway.wangan_east`
  gives it its partner's pier explicitly. The diamond ramps keep box pillars; they stand on land.

Measured: the core keeps 13 of its 14 block streets, the south-west residential 100 of 103, and 0 building centres
stand on a corridor or in a station or car-park box.

## The rail is a MODE of the Road Kit, built against the roads (PLAN.md 3.25 R1/R2, 2026-09-26)

A rail line is a Road Kit road whose `road_class` is **`rail`** (the `rail` preset: 1 + 1 lanes whose centres are the
track centres, 4.0 m apart, 1 m ballast shoulders, fenced, `RKA_PIER_hammerhead` when elevated, 80 km/h). So the
carrier, the grades, the zone cut, the piers and the lanekit are the kit's own; only what is SWEPT differs
(`point_mesh` "RAIL"): a ballast bed (`M_Ballast`, a `road_kit/materials` name) instead of asphalt, no markings, and
two rails a track (1067 mm, 16 cm tall, `M_Rail`). `road_class` and not a network flag, because a road's class
already decides everything per road.
- **A level crossing is where the rail meets ANOTHER network's paved band at its own height** (`build(foreign=)`,
  `roadkit_cli.py gltf --avoid <record>`, `CROSSING_DZ` 1 m): the road owns the ground there, so the rail's bed, fence,
  car wall and their collision are cut out and the rails lie FLUSH in the road surface (a car must not meet a 16 cm
  step); each crossing is reported (`crossings`) for the barrier props and the runtime. The cut is asked of the RAIL's
  height at that plan point, never the triangle's (a 3 m car wall's top face is not "at road level"). Piers keep off
  the foreign network's carriageways too (`pier_on_road` over both sets of bands).
- **The game keeps a track out of traffic and the GPS**: a rail `PathLaneRoute` joins group `rail_track` and never
  `ZoneManager.registerRoute` (so no car spawns on it and `LaneGraph` never hands a car onto a track at a crossing);
  `RoadGraph` skips `road_class` "rail" lanes.
- **`point_validate.check_rail`**: plan radius >= 160 m (WARN below, ERROR under 100 = a station throat's floor) and
  grade 3.5 % (ERROR over 4 %), the radius read as heading change per length -- a circumradius under-reads at every
  tangent point (a 200 m fillet read 128 m).
- **`tools/island_rail_record.py`** writes `IslandRail.roads.json` from the rail PLAN (`island_rail_layout.py`):
  stations ON the true arcs every <= 20 m (the plan's own polyline samples an arc coarsely: station to station it read
  a 200 m curve as ~32 m), bed = rail head - 0.16, held at the road's surface +-12 m round every level crossing and
  eased at 3.5 %, `pillar_skip` where the Rainbow Bridge's lower deck carries it; it adds World.tscn's `IslandRail`
  network node (same frame as `IslandRoads`).
- **Pipeline order** (`island_rebuild.sh`): the rail is grounded, zoned (`island_road_zones.py --network IslandRail
  --prefix rail --holder RailZones --zone-prefix Zone_rail_ --marker-prefix Rail_ --node-id-base 910020000`), built
  (against the road record) and STAMPED **before** the roads sample their ground, so to the roads the rail's embankment
  is land and a road re-stamp never undoes it. **Trap:** a rail re-stamp after the roads WOULD fight the road stamp --
  re-run from `terrain`. `island_ground` keeps the block fill off the rail reserve (a kerb-level fill would bury an
  at-grade track), painting under an elevated stretch like under a deck.
- **The ring road bridges a harbour line** (the 臨港線 pattern): the rail plan asks the ground WITHOUT the dike crest
  (`island_roadgen.Ground(dike=False)`), `island_dike.rail_lifts` lifts the ring 7.5 m over every rail head that passes
  UNDER it (never where the rail is elevated over the ring), eased at 5 %, and `sculpt` leaves the embankment open over
  the corridor.
- **The reserve closes streets by rule**: a generated street crossing at grade < 30 m from a junction or < 60 deg is
  written `no` in `IslandRailReserve.json`, which `island_streets` and the dike's side road (`island_dike._rail_no`)
  both obey; a site's ACCESS road is never closed (it stays a finding the route must answer).

## Stations, 踏切 signals, working traffic lights and real street names (rail batch, 2026-09-26)

Authored for the ONE rail rebuild (PLAN.md "the rail rebuild batch"); every piece below has its own check.

- **RETIRED by PLAN.md step 7 (2026-09-28): the rail record's own platforms, station buildings and platform exits.**
  Every station is one kit scene now (`Station_<Name>_Shop`, see "Step 7" below); the record keeps the TRACK only over
  a station span. What survives from here is `island_rail_record`'s platform CONTRACT (`PLATFORM_EDGE` 1.55 m from a
  track centre, `PLATFORM_H` 1.26 m over the bed, `PLATFORM_W` by kind), which `station_layout` reads.
- **踏切 signals (R4)**: `library` piece `Rail_CrossingSignal` (警報機 + raised 遮断機, `library_procedural.
  crossing_signal`); `point_mesh`'s crossing report now carries the rail and road directions and the road's paved half
  widths, and `point_furniture.crossing_signals` stands one on the LEFT of each approach, `crossing_track_clear` 4.5 m
  before the track (square to it). The rail build runs furniture now (`island_rebuild.sh` dropped `--no-furniture`);
  `point_furniture.place` gives a RAIL road none of the street's furniture (a platform is a footway to the kit).
- **The track is built to JAPANESE practice** (user, 2026-09-27: "japan rail standard ... additional bearing for
  earthquakes"; and "Japan always uses concrete ties"). `point_mesh` "JAPANESE TRACK": a 50N-proportioned I-section
  rail (foot 127 / web 16 / head 65 mm inside the kit's 0.16 m RAIL_H, so no platform or gauge moves); AT GRADE
  ballasted track on JR 3号 PC sleepers (`M_Concrete`, 2.0 m, 39 per 25 m = 0.641 m, tops 2 cm proud of the
  ballast); ON A VIADUCT / BRIDGE (any `rka_deck_h` > 0 sample) SLAB TRACK -- precast slabs (`M_TrackSlab`,
  4.93 x 2.22 m, 70 mm joints) on roadbed concrete, a CYLINDRICAL STOPPER (円柱形突起 Ø0.40 m, the earthquake
  restraint) in every joint, no ballast or sleepers, and a DERAILMENT GUARD (脱線防止ガード) 0.12 m inside the
  curve's inner rail; and two SEISMIC SIDE STOPPERS (横変位拘束構造 / 落橋防止) on every rail pier cap flanking the
  girder (only where the cap reaches; in the road collision). None of it is in a 踏切. ~607k visible tris over the
  island's rail, streamed per zone. Licence: the measurements are the published Japanese standards, built in code,
  MIT -- nothing third-party is in the rail.
- **The signal is SPLIT in its .blend, and the runtime lights the LENS itself** (user, 2026-09-26: "split the ped
  object / ped signals / traffic pole ... use the lamp objects for the signal instead of a round object").
  `TrafficLight_2_Japan.blend` holds `Pole`, `TrafficLight` (arm + vehicle head), `PedLight` and each lens as its own
  mesh (`TrafficLight_Lamp_Green/Yellow/Red`, double-faced: the head serves both approaches of its phase group;
  `Lamp_Ped_Red/Green`), plus `NamePlateSide1/2` Empties (a plate each side of the arm). `build_street_poles.py`
  (the old `--japanize` one-shot and the `Lamp_*` marker Empties are GONE) joins two pieces from them:
  `TrafficLight_JP` (pole + arm + vehicle head) and `PedSignal_JP` (pole + pedestrian head, turned so the head faces Godot +Z) -- the
  `ped_signal` asset now, at every crosswalk end (the library's
  `Signal_Pedestrian` placeholder is no longer placed). The baked lenses wear `MI_SignalLens` (dark glass, so an OFF
  lens reads off). Each piece's `<Piece>.lamps.json` carries its lens MESHES (`tris`, Godot piece frame) and plates;
  the signal plan hands each lamp its pole, the pole's `yaw` and that file (`lamps`), and `TrafficSignals` draws the
  lit lens as that same mesh, emissive, `LENS_PROUD` 4 mm out along each face's normal. A baked lens is one instance of
  a shared MultiMesh, so its material cannot be swapped per signal -- drawing the same mesh lit over it IS the lens
  changing colour. A plan with no mesh falls back to the old ball. Probe: `lens_lamps_now`, `lit_vehicle_lamps_now`.
  **ONE pedestrian head per crosswalk end, ALWAYS on its own pole** (user, 2026-09-27: a crossing showed two ped
  lights for one direction -- "avoid 2 formats"). Japan mounts a ped head on the vehicle-signal pole (共架) only where
  that pole stands AT the crosswalk end; ours stand at the far-side corner metres past it, so the vehicle pole's own
  head doubled the crosswalk's. `TrafficLight_JP` is therefore pole + arm + vehicle head ONLY, and
  `point_furniture._ped_signals` puts a `PedSignal_JP` at every crosswalk end, stepped back from the junction if it
  would stand within `ped_signal_pole_clear` (1.2 m) of a vehicle pole. (A corner-pole variant with a second head at
  90 deg was built and retired the same day for the same reason.)
- **Japanese signalisation** (`point_furniture._signalised`, `signal_needs_major`): a crossing of two narrow streets
  has no signal (the minor approach keeps its stop line); a signal needs an arm with `signal_major_lanes` (2)
  arriving lanes or an arterial. Island (scratch): 89 of 120 junctions signalised. **Pedestrian signals**
  (`PedSignal_JP`, breakable like the poles) stand at EVERY zebra end, facing across it, on their own pole -- see "ONE
  pedestrian head per crosswalk end" above.
- **The signals WORK** (`world.TrafficSignals` AutoLoad + engine-free `world.SignalTiming`, `SignalTimingTest` 4):
  `roadkit_cli gltf` writes `<network>.signals.json` (`point_furniture.signal_plan`: arms in phase groups -- an arm
  and the one arm most head-on to it; stop distance; every lens and plate in world space with the POLE it hangs on).
  Phases: green 22 / yellow 3 / all-red 2 s per group; a crosswalk WALKs while its road is red and another green,
  flashing its last 4 s. Clock = the system clock (peers agree with no message); `game_clock` for `--fixed-fps`
  probes. The traffic brain: `VehicleAIController.signalSpeedLimit` (sqrt(2 b d), b 3.5) in `CruiseState`; racing
  cars ignore it. Lamps near the camera (160 m) are lit (the lens mesh, above), only while their pole is streamed
  in and standing (a knocked-down signal goes dark). Pedestrians do not cross streets yet: their lights are shown,
  not obeyed. `enabled` off is the control.
- **Real street names** (`tools/island_street_names.py` -> `world/IslandStreetNames.json`, `world.StreetNames`):
  every road's base name gets kanji + romaji -- the arterials by a transliteration table, generated streets from
  pools of real Japanese street names by hash (farm roads 農道, industry streets 産業道路 ...), unique on the island;
  DebugRoads' four too. Font: `tools/make_jp_font.py` subsets Noto Sans CJK JP (OFL 1.1) to the characters used
  (`ui/fonts/NotoSansJP-Signs.otf`, ~220 KB). Shown on a blue plate on each signal arm (the CROSSED street) and as
  the kanji under the player on the minimap. Both run in `island_world.sh`'s layout stage.
- **Speed by class**: a ramp exports at most 40 km/h (`point_export.RAMP_SPEED`); C1 is 60 (`island_expressway.
  C1_SPEED`, set after the build so tapers stay sized for 80). `probe_road_launch --driver=standard` drives by the
  traffic rules (lane limit, corner governor, junctions, eyes); the default stays the flat-out stress test.
- **Streets**: `island_core_streets` gained `kojo_waku` (the industry frame: the ring became the dike and the
  Harbour line took the east edge, so industry had 0 streets -> 6) and `kogai_loop` (a U off the ring through the
  suburb's land outside the dike; its legs are dike ramps, so the suburb's buildings front the loop itself).
- **Derive**: an `airport` region; the suburb box clipped to land; a `ekimae` 駅前 row (shop-houses) round every
  station of the reserve (`EKIMAE_SKIP` Central/Airport/Residential/Harbour/Industry); **footprint variants**
  (`building_types.json` `variants`, expanded by `layout_buildings.expand_variants`: `<Id>_<suffix>` with other
  `modules` / `upper` / `doors`; `island_buildings.variant_pick` draws base-or-variant by a hash of the slot);
  **parking by district** (`PARKING_BY_REGION`: none downtown / nightlife, larger further out) and **コインパーキング**
  (`ParkingLot4` in the city / housing mixes).
- Gates: `probe_rail_track.gd` (new, needs the rebuild), `probe_traffic_signals.gd` 6/6 on DebugWorld (plan
  loaded, lamps lit, plates built, a car stops with its nose 0.17 m short of the line on red and drives on at green,
  the minimap names the street in kanji; `--control` runs the red); `tools/godot/shot_signals.gd` (display) pictures.
- **What the first rebuild's gates found (2026-09-26), each fixed in the rule:**
  - **A 踏切 cut by triangle CENTROID left half a fence segment in the road.** A rail's fence, shoulder and car wall
    are swept a sample span (~4 m) at a time, so `point_mesh.cut_crossings` now drops a triangle if ANY corner (or
    its centroid) is inside the crossed road's band -- 11 road lanes had a fence post or shoulder in their outer lane.
  - **Road furniture did not know the rail was there**: a street lamp stood 1 m off a track. The road build takes
    `--keep-clear-lanekits <pieces>/Roads_IslandRail_` (a path PREFIX, so the shell never globs it) and
    `point_furniture.place(keep_clear=)` adds those lanes to the one lane index every pole asks. The road piece
    digest cannot see the rail: after a rail change, run the road build once WITHOUT `DIRTY_ONLY`.
  - **Two station buildings stood on an arterial** (Bay on rinkai_dori, Waterpark on wangan_dori): the reserve's
    side rule looked at reachability, never at the paved road right beside the platform. `island_rail_layout`
    now tries the town side first, sliding the building + car park along the platform (0, +-10 ... +-45 m), then
    the other side, and takes the first placement clear of every at-grade arterial's paved half width + 1 m. Five
    stations moved (Bay, Waterpark, Suburb, City West, Castle Town).
  - **A car waiting at a RED was reclaimed as `stalled`** (57 of 98 in-range reclaims): the 12 s stall timer predates
    working lights, and a red lasts ~27 s. `VehicleAIController.waitingForSignal` (held at the stop line, or queued
    behind a car that is -- read off the obstacle rays) resets the stall timer; `waiting_for_signal_now` is its
    readout. `probe_traffic_spawn` runs the lights on game time (`game_clock`) and does not count a waiting car as idle.
  - `probe_weapon_counter`'s refill case waits the pad's cooldown in WALL time (`WeaponPad` uses the engine clock
    so an off-screen pad's cooldown still runs out; `--fixed-fps` is faster than real time).
  - **Nothing solid in a train's gauge, and every track ends at a station** (user, 2026-09-26). `probe_rail_track`
    checks 5 and 6: a 2.7 x 3.7 m box (0.5 m over the bed) swept every 2 m along every track must touch nothing on
    WORLD / CAR_WALL -- road, rail, building-cell, site and landmark geometry all instanced -- and a track lane with
    no successor must end inside a station's platform box (+15 m). The first sweep found, each fixed in its rule:
    - **platform faces leaned 0.63 m into the track**: a kerb is swept centred on its edge line, half as thick as it
      is tall. `point_mesh._edge_run` caps the half thickness at `KERB_HALF_MAX` (0.15) and, from
      `PLATFORM_KERB_FROM` (0.2 m, flush by 0.3 m) tall, slides the prism outward so a platform face stands flush at the edge; road
      kerbs (under 0.3 m) are byte-identical.
    - **expressway piers on the tracks** (C1, the airport spur): the road build now takes `--avoid` the rail record
      too, so `pier_on_road` keeps columns off the rail's bands.
    - **a road's parapet across a 踏切**: a road built against the rail cuts its BARRIER and car wall (never its
      kerb or footway) where it crosses a track at its own height.
    - **Central's lines run 14 m apart** (Blue y 229, Main 215, Harbour 201): at 10 m the platform between two lines
      could only be one shared island, which the Road Kit builds as two OVERLAPPING footways -- their fences ended
      diagonally across the neighbour's track at the platform ends. At 14 m each line keeps its own 3 m side
      platforms and fences clear of the next line's gauge. Platform edge 1.55 m from the track centre (was 1.5:
      the kerb's mitre at a platform END stood 2-3 cm inside the gauge).
    - **A 踏切 gets a LEVEL road**: a dike ramp ran on at 5 % across the tracks at nishi_dori__9, so the two tracks
      4 m apart met the road 0.2 m apart in height and the road's footway stood in the east track's gauge.
      `island_dike._level_at_crossings` pins every ramp station within `LX_HOLD` (15 m) of an at-grade rail sample to
      the rail's height and brings the ramp down to it at up to `RAMP_STEEP` (8 %); `island_grades` holds every
      station within `LX_HOLD` of an at-grade track by the same rule, so the smoother cannot re-slope it.
    - **street trees** asked their own lane index, not the shared one with the rail's lanes (`--keep-clear`).
    - **踏切 units swung onto the track**: `crossing_signals` measured `crossing_track_clear` ALONG the road and then
      stepped the kerb-side offset sideways, which on a 45 deg road put both units 0.9 m from the rail's centreline;
      a unit is now pushed out until it stands `clear` from the rail square to it.
    - **station buildings on another line's track** (Bay, Harbour): the reserve's placement also keeps
      `OTHER_TRACK_CLEAR` (7 m) from every other line.
    - **a 踏切 through a platform** (City West on chuo_dori, Bay on rinkai_dori): the road owns the crossing's
      ground, so the platform was missing there. Both stations slid along their lines (City West x -125, Bay y -140
      with a 100 m platform between the viaduct ramp's foot and the crossing), and the layout check reports
      `踏切 IN PLATFORM` (`LX_PLATFORM_CLEAR` 5 m past the platform end).
    - **track ends**: the Main line ran 35 m past Farm and 65 m past Airport (now ~20 m buffer), the freight siding's
      north end stopped in the open (now station tracks inside Harbour), and the Blue and Harbour lines ended beside
      Central with no platform: a HUB or JUNCTION now gives a platform to every line within `HUB_SHARE` (25 m) of
      it (`island_rail_record.platform_spans`), and a hub's platforms are 3 m -- the lines run 10 m apart, so the
      platform between two of them is one shared island.
  - Probes: `probe_rail_track` hung on an unregistered `ZoneManager` method (now `registered_lane_counts_now`) and
    read crossing heights without the network node's Y; `probe_road_clear` skips `rail_track` lanes (a platform
    1.5 m off a track is right; the train's gauge is `probe_rail_track`'s); `probe_road_stamp` judges only its own
    network's pieces and reports (does not fail) a FILL-height sample that BRIDGES a rail line
    (`island_dike.rail_lifts` leaves the corridor open by design); `probe_crops` stands a camera over a chunk,
    because `CropField` builds only the chunks round the camera (headless reads every MultiMesh transform as
    identity, so its placement check is counted "unreadable", not passed).

## The paid area: ticket gates (2026-09-27; the interim yards and footbridges retired by step 7)

A station's platforms are a closed PAID AREA: street -> station building -> ticket gates -> stair / lift -> platform.
The interim version (a yard + a `StationBuilding` beside each platform, footbridges, platform-end fences swept by the
rail kit) was replaced by the three kit station forms and deleted in PLAN.md step 7 (below).

- **`world.TicketGate`** (extends `Door`): two flaps meeting mid-lane, fast (open_speed 8), swing away from the walker,
  fare-free. `Door.admits(body)` is the one fare hook (asked on sensor enter AND exit, so the count stays balanced).
  Built by `build_building_scenes.gd._add_gate` from a DOOR-ONLY prop (`{"door": {"kind": "gate", w, h}, "at"}`, no
  `piece`; `layout_buildings.place_props` records it as an inner door). **The lane's sensor is NOT a child of a flap**:
  as a child it swung away with the flap, lost the walker, shut, swung back -- the gate chattered at 36 deg.
  Gate `tools/godot/probe_ticket_gate.gd` 7/7 on `Station_Farm_Shop.tscn` (`--scene=` any station; each lane's frame is
  its sensor's: origin mid-lane, +Z the unpaid side); `--control` (manual flaps) fails the 2 lane checks.
- **The track corridor itself is NOT closed**: nothing may stand in a train's gauge, so a trespasser can walk the bed
  from a 踏切 (as in reality). The closure is the platform: its face is 1.26 m over the bed and its ends are fenced.
- Gate **`tools/godot/probe_station_paid.gd`**: streams each station in on World.tscn (or `--scene=` one station on
  a stand) and flood-fills every walkable surface (0.25 m cells, multi-level, 0.4 m steps, a 0.2 m capsule standing):
  from every street entrance and from the bed past a platform end no platform is reached with the flaps shut; with
  them open the street reaches every platform. Auto doors are treated open. `--control` opens the flaps for the
  negative cases.
- **Also in this batch** (user, 2026-09-27): at a 踏切 the rail's fence, car wall and bed are cut over the road's
  FOOTWAYS too (`Band.walk`, `crossing_band(footways=True)`), so a pedestrian crosses beside the cars; and a RAISED
  (or WALL) median is a KERBED ISLAND (`point_mesh.raised_median`: kerb stones `MEDIAN_KERB_W` 0.15 m each edge in the
  kerb material, footway fill between, both solid to the road) instead of the flat green `M_Median` band, which had no
  sides at all. The `median` style slot's material is no longer read (a median PROFILE ASSET still is).

## Station lifts: a through car beside every hub stair, and balustrades on every stair (2026-09-27, user-asked)

Every elevated-hub and ground-hub platform has a LIFT; `station_layout.py` owns where (`LIFT_GAP` 3 m beyond the stair's
TOP end, the stair's width square, in the stair's band: `eh_lift`, `hub_lift`, `lift_door_w`). The ground hub's annex
has one too (street -> concourse, in the paid strip), so the whole route is step-free.
- **The shaft is ART, the car is RUNTIME.** `build_station_blends.lift_shaft` models glass walls on metal posts with a
  door opening in both X faces (along the track, never the rail side) at each stop, and drops a `LIFT_` Empty (w, d,
  rise, door_w, door_h). It flows through `pieces.json` `lifts`, a `{lift}` prop, and the layout's `lifts`, into a
  `world.Elevator` node that `build_building_scenes.gd` puts in EVERY variant (a lift is not a door).
- **`world.Elevator`** builds an `AnimatableBody3D` car (a character standing in it rides it). Each face gets a two-leaf
  centre-opening sliding door on the car and at each landing (the leaves part to both sides), plus CALL / DOORWAY / RIDE
  sensors. A leaf's collider is off only while the doors stand open at the car's stop. Its behaviour is engine-free
  `world.ElevatorRules` (`ElevatorRulesTest` 5). There are no buttons: a call is somebody ARRIVING at a landing (an
  event, so a person waiting does not cycle the doors). Somebody boarding rides to the other stop, and the doors never
  shut on a body in the doorway. A rider who stays on does not ride back. `inService` off = neither opens nor moves.
  Local per peer (the `Door` rule).
- **Every stair has a balustrade on both long sides** (`stair_rail`: a glass panel and a handrail stepped with the
  flight, a collider on each open side, a handrail only against a wall). The elevated stair's open side is fenced
  only below the platform slab, whose face is the fence above it (`clip_runs`).
- **The elevated hub's F1 is a PAID BOX ringed by the unpaid hall** (user's larger-station plan, same day). The box is
  centred on the station (`eh_modules`: gate module | lift | the stair's four | gate module, snapped to the 5 m
  grid) and holds both stairs and both lifts. The unpaid hall is two single-storey WINGS, `EH_WING` 5 m past each
  rail wall with a roof 4.6 m up, with four street entrances second from each end, plus the hall's two ends. The
  wings take the building from 20.7 m to 30.7 m wide; `extent()` carries it into the rail reserve, which now reports
  an elevated building that does not clear. Fare lines close all four sides:
  - `EH_FloorGate` across the hall, turned 180 deg (hands swapped) at the low end so its unpaid side faces out;
  - `EH_FareSide` / `EH_FareSideGate` along each long side, in the rail wall's line, whose F1 storey is a column per
    module under a beam at the ceiling.
  
  A lowered CEILING at `EH_CEIL` 3.8 m (visual only) hides the viaduct soffit and the seam between the rail deck and
  the station's slabs; it is open over the stairs, with a bulkhead above each stair's balustrade. The layout meta
  carries `paid_box` / `outer` / `rail_wall`. The generator now RETIRES a generated piece the form no longer makes
  (removed if untouched, reported if edited), and the exporter removes a retired piece's `.import`. Pictures:
  `tools/godot/shot_station_hall.gd` (display). Central (step 6) takes the same four-sided box.
- Gates: `tools/godot/probe_elevator.gd [--scene= --lift=N] [--control]` 10/10: a real Player calls it, rides 9.1 m up
  (0.00 m off the platform), steps out, and the car stays. Control: 6 fail. `probe_station_paid` is unchanged on all
  12 stations. Pictures: `tools/godot/shot_lift.gd` (display). Trap met: a `@Register` method renamed in Java is
  invisible to Godot until `./gradlew build`, and `MethodCallable.createUnsafe` with the stale name connects to nothing,
  silently.

## Central is the elevated hub over three lanes; every station is a kit station (PLAN.md step 6, 2026-09-27)

`station_layout.Station.kit` is every form now. A multi-lane elevated hub reuses the one-lane side pieces OUTSIDE its
two outermost lanes (`eh_span`) and puts an ISLAND platform between each pair (`eh_islands`: its stair and lift on the
island's centre line, in the gap between the two lanes' viaduct decks, `EH_ISLAND_SW` 2.5 m; refused when the decks
leave no room). Whole-building pieces are named for the lane set (`eh_core`: `EH_Floor_345_3x14`); the one-lane names
are unchanged and regenerate byte-identical. A station >= `EH_LONG` (150 m) gets entrances beside its paid box too.
- **A lane must run the whole platform** (`station_layout.check`, `Lane.cover`): the Blue and Harbour lines STARTED at
  Central's centre (x 782) and the Blue line ENDED 15 m inside Light Industry's platform. Both fixed in the rail plan
  (`island_rail_layout`: `CENTRAL_END_X` 952; the Blue line to y -1017, short of the dike's back slope).
- **The reserve**: `box_clear(own_line=)` takes every lane of the station (a station's own tracks are not a foreign
  line), and a station car park keeps off every frozen site (`site_clear`) at a 10 / 5 / 2 m gap.
- `probe_station_paid.gd` stand mode now requires EVERY platform to be reached through the open gates, not just one.

## The open-air station building: restrooms both sides, a service counter, and a straight entry ramp (2026-09-27/28)

User's layout sketches, PLAN.md step 6b. The end building is 22 m along x 9.5 m deep from the platform's track edge,
its whole FLOOR AT THE PLATFORM TOP (the platform runs straight in). From the platform: the paid hall and a restroom
block; the fare line (2 gate lanes by the track wall and the SERVICE COUNTER, the staffed wide gate); the unpaid hall
with a second restroom block and the ticket / ATM / vending machines; the 4 m door. The restroom block is the
small-station set (user, 2026-09-28: men 1 stall + 1 urinal + 1 basin, women 2 stalls + 2 basins, an accessible
room; `WC_L` x `WC_D` 8.6 x 5 m; `build_station_blends.restroom_block`, reusable in any frame via `Frame`). Every stall
has a real hinged 0.65 m door (a `DOOR_`) that swings clear of the toilet inward and of every basin outward; the basins
stand away from the stall fronts.
- **The entry is ONE straight ramp, no stair** (`OA_Ramp_<n>`, user 2026-09-28): out of the door, as wide as it and in
  line with it, a 1.5 m landing at the sill, then 1:15 legs with a landing every 0.75 m of rise (`ramp_run(n)`, ~23 m
  for the usual 1.4 m). n comes from the reserve's `entry_rise`, measured at the ramp's foot. Its foot stops
  `FOOT_GAP` (1.5 m) short of the street's paved edge; the 踏切's warning unit stands in that apron. A slope's collider
  is its own wedge. **Convex colliders:** a `HULL_<n>` Empty (points in its `pts` custom property) -> `pieces.json`
  `collide_hulls` -> the layout's `hull_points` -> a `ConvexPolygonShape3D`. Axis-aligned `COL_` boxes can only make a
  slope into steps. The rail's fence stands down past the building AND the ramp (`island_rail_record.open_air_reach`).
- **Every open-air station meets its street** (`island_rail_layout.STATION_FRONT`: the end its buildings stand at,
  the street as a record polyline, the street's half width). Each station SLID along its line until the ramps' feet
  land at a street crossing the line there, the small Japanese station beside its 踏切: Farm 2 m, Residential 9,
  Light Industry 15 (the Blue line's buffer stop moved to y -1023), Castle Town 32, Residential North 46 and City
  West 46. Where no street crossed near, the street is an access road across the line (`island_site_access`):
  `ekimae_farm`, and the castle's `jokamachi_sando`, now straight north over the Blue line to the castle's car park.
  The reserve re-measures every foot against its street and reports one that lands more than 12 m short or past the
  kerb.
  - **The car park fronts the street**, beside the town-side building (or the `park` side), its entrance ON the
    street's paved edge, sized by its scene, LEVEL with the road (`island_sites.rail_stations`: a levelled site, so the
    block ground is filled to it). It used to stand in the middle of the field at the lowest ground under it, the fill
    showing through it, with no way in.
  - **Along its axis an open-air station box and a street-front car park keep NO clearance** (`island_streets._rail`,
    `island_dike._in_station`), so a street may pass right by the front. A dike side road that runs across one is
    bent out ONTO the street line point by point (`FRONT_ESCAPE`: its paved edge exactly FOOT_GAP past the feet),
    which is what makes Light Industry's street. `island_dike.keep_off_rail` keeps a side road 35 m off an at-grade
    track it runs alongside (the old wide station boxes had done that by accident; without it, Residential North's side
    road T'd into nishi_dori 27 m from the 踏切).
- **The ground hub's entrance annex** (15.5 m deep: paid 8 m, unpaid 7.5 m) carries the same set: a restroom block each
  side of its fare line (the paid one under the mezzanine landing), the machines by the street wall, the service
  counter on the line beside 2 gate lanes, and `GH_Entry_<n>` (the entry piece, stair + slope) where the street is
  below the door. **A gate lane's yaw is the unpaid side's direction** (`p.gates` 4th element, default +X): a fare line
  along X needs 90, or the flaps stand edge-on in the lane. `probe_station_paid.gd --trace` prints a leak's route.
- **The elevated hub's amenities fit its F1 as it is (the wings are NOT widened: a wider building grows the reserve).**
  `EH_Restroom` stands free under the MIDDLE lane between its deck's F1 column rows (faces +-4.1 m), one in the paid box
  over the stair span and one in the unpaid end hall 1 m outside the low fare line (`station_layout.eh_restrooms`);
  each end fare line ends in the service counter 0.6 m short of the long side's gate bank; the machines are in
  `EH_WingMachines_*`, the wing beside each gate module. `shot_station_hall.gd` has `wc_paid` / `wc_unpaid` views.
- 9.5 m deep is what fits every site. **Waterpark is a one-lane ground hub** (`station_layout.FORM_OVERRIDE`): the
  wangan_dori trunk road is ~6.5 m from its south platform.
- `probe_station_paid.gd` stand mode checks every platform from EVERY entrance. An open-air station must also have a
  STEP-FREE route (<= 6 cm per 0.25 m cell) from each entrance to each platform. That check found a variable-shadowing
  bug that laid one platform 8 modules long.

## EMU1: the measuring train, and what it says about the platforms (2026-09-29, user-asked)

User: "the platform seems narrower than the railway's wall ... a real train has some width, not sure it fits; generate
a Japan rail/metro train and use it on the rail to measure (assume the largest)". `blender/tools/make_train.py`
writes `assets/vehicles/trains/EMU1.blend` (the owner once written; `--force` to regenerate), `EMU1_Tc.glb` (cab car),
`EMU1_M.glb` (middle car, pantograph) and `EMU1.train.json`, every size MEASURED off the built mesh. It is a generic
20 m, 4-door, WIDE-BODY commuter car on the 1067 mm gauge (the JR E231/E233 envelope, no livery copied): body 2.95 m at
the waist, 2.80 m at the sill, 2.98 m over the doors, floor 1.13 m over the rail head, roof 3.62, pantograph folded
4.05, bogie centres 13.8 m -- the largest standard conventional-line car (a subway car is 2.8-2.85 m), so what fits it
fits any.
- **`tools/godot/probe_train_fit.gd`** is the gate. `--stations` (or `--scene=`): a 4-car set on every track of every
  station, touching nothing, the platform edge found by a ray at every door, the gap measured to the car at the
  platform's top, and the step up to the floor. `--world=island|debug`: the set driven along every rail lane on its
  bogie centres (so a curve's overhang is the real car's), touching nothing; it also reports the nearest thing beside
  the car. `--control` widens the car 0.3 m a side and fails.
- **Measured: every station fits, and the platforms must NOT move out.** All 13 stations: gap **0.11 m** at every
  door, step **0.03 m**, nothing touched (Japan's straight-platform gap is ~0.05-0.10 m). The platform edge stands
  1.55 m from the track centre; the rail corridor's walls stand 3.16 m out, 1.67 m past a car's side. That is why a
  platform looks "narrower than the rail's walls". Moving the platforms out to the walls would leave a 1.7 m gap
  between train and platform.
- **The gauge is the train's now**: `station_layout.GAUGE_HALF/GAUGE_H` and `probe_rail_track.gd` check 5 read
  `EMU1.train.json` (3.0 x 4.25 m over the bed, was 2.7 x 3.7). It found DebugWorld's station A's east building and
  ramp standing where the line had begun to curve; `debug_world_layout` now starts the curve at x -275 with A at -365
  (the train then runs the whole line clear, nearest object 0.06 m past its side: the station's track wall).
- Pictures: `tools/godot/shot_train_station.gd` (display) -- the set at a station's platforms from the platform, along
  the tracks and from above.

## Trains you can board: doors, an interior, hits, a wreck and a respawn, and the line on the map (2026-10-02)

PLAN.md NEXT items 10 and 11, built beside the island rebuild (runtime and the EMU1 model only, no rebuild).
`assets/vehicles/trains/ARTIST_NOTES.md` lists every placeholder and the names the game reads.
- **The model** (`blender/tools/make_train.py`, regenerated once with `--force`; the `.blend` is the owner again):
  - real door OPENINGS in the side walls, and each doorway's two leaves as their own objects
    (`<car>_Door_<P|N><i><a|b>`, origin = the leaf's centre when shut, inside the 5 cm wall, sliding 0.62 m into its pocket);
  - a lined shell with see-through windows (glass alpha 0.35; every train material is double-sided);
  - an open gangway with bellows and a footplate, so the whole train can be walked;
  - a Japanese commuter interior in `<car>_Interior`: long benches per seat with red/orange priority seats at each
    car's −Y end, door partitions, poles (yellow at priority), luggage racks, two grab rails with straps every
    0.32 m (yellow at priority), two LED light lines plus an AC diffuser, a door-top screen over every door, yellow
    doorway lines, a wheelchair space on a middle car, and on the cab car a cab behind a partition;
  - `COL_` / `DOORCOL_` cube Empties (scale = half size) and `LIGHT_` Empties, read back into `EMU1.train.json` per
    car (`colliders`, `doors` with each leaf's slide in the Godot car frame, `lights`);
  - every object carries its car's prefix (`Tc_` / `M_`), because object names are global in a .blend.

  The outer envelope is unchanged (1.491 m with the new door frames, 4.05 m), so every station check holds:
  `probe_train_fit --stations` PASS.
- **`world.TrainSystem`**:
  - **Car collision**: each car is built from those boxes. The last car is turned 180 deg, so its x and z are negated.
  - **Doors**: at each dwell a ray beside each door asks whether a platform stands there (a surface within 0.35 m under
    the floor). Those doors open over 1.4 s and shut 3.5 s before departure. Someone in the doorway holds them until
    0.5 s before departure, because the clock-driven timetable never waits. An open door's collider is off.
  - **Interior lights**: 2 shadowless OmniLights per car, within 140 m of the camera.
- **A rider rides the AnimatableBody3D floor** (measured: 342 m on DebugWorld's curved line, 0.00 m off the floor).
  The trap that broke it first: `Transform3D.times` MUTATES its receiver (godot-jvm), so `xf.times(offset)` moved the
  car frame the rider check then used.
- **Hits** (`hitAhead`): every car's own box (the lead one grown by this step's travel), on CHARACTER | VEHICLE.
  - A character standing on that car's floor (|x| < 1.45, 0.8 < y < 3.4) is a rider and is skipped, and so is a seated one.
  - A character is otherwise hit: damage 1.2 v^2 + 10, and only where damage is (host or single player). If alive it is
    set clear of the gauge; if dead it is thrown.
  - A vehicle is shoved (impulse on the peer that simulates it) and damaged 30 v.
  - Below 2 m/s a hit is a push. A 1 s cooldown applies per target.
- **Health, destruction, respawn**:
  - Each car has a code-built `Health` (3000, bullets x0.15, blasts x2.0). A set's health is the lowest of its cars,
    kept on the set, so freeing and rebuilding the cars with the camera keeps the damage.
  - `ExplosionManager.triggerExplosion` calls `TrainSystem.blast`, because cars are WORLD bodies and not "characters".
  - At 0 HP (the authority) the cars become a burnt wreck in place, each with a blast. The set is out of service
    (no cars, crossings open, off the map) until `TrainTimetable.nextDwellStart(t, 45 s)`, the first platform dwell
    45 s later, where it reappears whole with its doors opening. Every peer derives that from the destruction time,
    so `GameManager.WORLD_EVENT_TRAIN_DESTROYED` (13) carries only the track id and the time (as a string arg, since
    unix time in a float loses minutes). `EventBus.trainDestroyed(trackId)` fires on every peer.
  - Mission API (registered): `nearest_set_now`, `destroy_set_now`, `set_invulnerable_now`, `set_health_now`,
    `set_out_of_service_now`, `set_back_at_now`. Not sent to a late joiner.
- **The map**: `TrainSystem.mapLines` (one polyline per line: a track that runs 80 % within 12 m of one already drawn is
  not drawn again) and `mapTrains` (head/tail of every set in service, from the clock). `RoadOverlay.drawRail` draws
  them in JR style, a white band with black dashes, and each train as a white bar with a yellow head. This is on the
  minimap and the full map (`showRail`), and the legend gains "Rail line" and "Train".
- **The minimap is a rounded square** (`MinimapController.square`; `RoadOverlay.squareClip` and its `clip*` helpers are
  the one clip shape). North sits on the frame's edge, always drawn whole.
- Gates:
  - `tools/godot/probe_train_board.gd` 11/11. It jumps the timetable with `TrainSystem.clock_offset`, which must never
    be done while a rider is aboard (it teleports the train). `--control` = `doors_enabled` off.
  - `probe_trains` PASS on both worlds; `TrainTimetableTest` gains the respawn case; `probe_gps_route` 25/25.
- **The timetable runs on a STEP clock anchored to the wall clock** (`TrainSystem.tickClock`). On the raw wall
  clock, two physics steps run in one render frame read nearly the same time, so the train moved 0 and then double.
  A rider felt every frame as a jolt (user-reported). The clock adds each physics delta and eases toward the wall
  clock at `CLOCK_EASE` (0.2 of the difference per second), so peers still agree. It snaps only past `CLOCK_SNAP`
  (20 s), so a game too slow to keep physics at real time eases rather than jumps. Gate
  `tools/godot/probe_train_smooth.gd` (real time, `--frame-ms=` adds render-frame load): 0 of 300 steps off at
  0/25/40 ms frames. The raw wall clock is the control: 299 of 300 off at 25 ms.
- **A double-track line runs as a LOOP, not a shuttle** (user decision, 2026-10-02):
  - `TrainTimetable.circuit` runs one track end to end, then the other, and loops. Each track carries one direction,
    keep-left. A terminus stop is two half-stops (`TERMINAL_DWELL` / 2 each), and the set changes track at the
    halfway point: the cheap turn, as GTA does it.
  - `TrainSystem.partnerOf` pairs a track with the one running back along it (ends within 60 m).
  - A loop carries `2 x setsPerWay` sets (1 per way today), evenly spaced in time so they never meet. A lone track is
    still a one-set shuttle; freight sidings carry none.
  - **The swap carries riders** (`swapTrack`): the cars are rebuilt on the new track. Anyone standing in a car moves
    with it: car i becomes car 3 - i, at the same end of the platform. A middle car's frame turns 180°, so the
    rider's place in it is mirrored, and they move only the ~4 m across to the other track.
  - **Riders are held through the turn** (user-reported: a rider landed "somewhere invisible"). The way other games
    move a passenger through a teleport is to move the vehicle and its passengers in the same step and HOLD the
    passengers until the new collision is in. Here:
    - a rider is anyone inside the walls, in a doorway (to the door's outer face) or on the gangway;
    - they are pinned to their place in the new car with no velocity for `PIN_TICKS` (8) physics steps
      (`pinRiders`, off is the control);
    - the new cars' platform-side doors stand OPEN at once. Rebuilt shut, a rider in a doorway overlapped the shut
      door's collider.

    Gate `tools/godot/probe_train_turn.gd` (real time, `--frame-ms=` load; `--walk`, `--at=x,z` a place in the car,
    `--world=island --set=N`, `--from-track=K` picks which terminus): PASS standing, walking, in a doorway and at both
    car ends on DebugWorld, and on all three island lines. The reported case, the Main line's turn at Airport with a
    rider mid-car, also passes: they end on the other Airport platform, 4 m across. `TrainSystem.set_debug_now(i)`
    prints a set's tracks, ends and stops. The control (`--control`, no pin) also passes there, so the report's exact case is not
    reproduced headless yet.
  - Every crossing asks its own track (`crossingClosed(track, ...)`); boards and the map merge every set on a track.
  - Cost: ~0.1 ms per physics step per set with its cars near the camera; nothing for a far set.
  - **Trap**: a body just built with `sync_to_physics` reports its new transform only after the next physics sync.
    So the rider mapping and the door platform rays use `carPose` (the pose computed from the track), never
    `body.getGlobalTransform()`. Read back, the swap dropped the rider at the world origin and found no platform for
    the whole stop.
, owned by TrainSystem, all derived from the timetable):
  - a departure board (発車標) hung over every platform a set calls at, found by a ray beside the track at the stop,
    with both faces: 先発 / 次発, the game-time HH:MM, 普通, the destination 行, and まもなく in the last 30 s;
  - the screen over every door inside a car (ドア上LCD): 次は / Next and the arrival time, or at a stop the station
    and where the train goes;
  - the full map: clicking a station blip opens a panel with each way's next two departures
    (`TrainSystem.stationPanel`).

  Station names are fictional, in `world/StationNames.json` (Japanese + English, plus the board words), and
  `tools/make_jp_font.py` adds their glyphs to the sign font. `TrainTimetable.calls` / `nextCall` / `terminalFor`
  are the queries (in `TrainTimetableTest`). A Label3D is centred on its node, so its alignment is CENTER: LEFT
  starts the text at the node and runs it off the board.
- **Game time has ONE owner, `world.GameTime`**: Sky3D's TimeOfDay `current_time` at its `minutes_per_day` (48, so a
  real second is 30 game seconds), falling back to local time. `ui.GameClock` (built in code by HUDManager, top-right,
  sun or moon mark) shows it, and the kill feed moved down under it. HUDManager's widget registry hides any child it
  does not list as self-managed, so a new always-on widget must be added to that skip list.
  **Consequence for the boards:** one set shuttling a DebugWorld line every ~190 real s reads as trains ~95 game
  minutes apart.
- **Probe trap:** a node with `process_mode` DISABLED leaves the physics space unless its `disable_mode` is
  KEEP_ACTIVE, so a frozen dummy on the track was invisible to the hit query.

**A floor finish carries the same holes as its slab** (2026-10-02, user-reported on a ground-hub footbridge: "a mesh
over the stair, but no collision"). `build_station_blends.cap_top` and the annex mezzanine laid a 1 cm terrazzo finish
over the whole concourse (visual only) after cutting the stair and lift holes in the slab. It is
`slab_with_holes(..., collide=False)` now. Measured with a ray grid against the pieces: 2,219 samples of finish over an
opening in every `GH_Cap*` / `GH_Annex*` piece before, 0 after. A failed Preview (a rail plan mid-edit) no longer
stops the kit .blend being saved.

## The large hubs: six-bay roller-shutter entrances and shops along the side (PLAN.md step 6b, 2026-09-28)

**Every station entrance is a roller-shutter opening** (user): no door leaf, open all day, and NO post in between --
only its frame at each side (user, 2026-09-28; the generator's `shutter(..., posts=False)`: one shutter, a guide rail
each side, the housing over it). Station stores have no shutter at all (a glass front, below). Ordinary entrances are 4 m; a LARGE hub's (`is_large`: every hub form but a `FORM_OVERRIDE` station, i.e. all
but Waterpark) is 11.8 m (`LARGE_ENTRANCE_W`, sized as six 1.8 m bays). A shutter that comes down at night is a later runtime item.
- **Ground hubs** (Bay, Industry, Harbour): `GH_AnnexLarge_*` (opening at a 2.6..14.4) and ONE store,
  `GH_AnnexStore_*`, past the annex's +X end (user, 2026-09-28): it opens ONLY into the unpaid hall, through a sliding
  glass door in the annex's +X end wall (the paid strip's part of that wall stays solid), shows display glass to the
  street, and its floor is the hall's. `GH_EntryWide_*` spans the whole opening. `annex_span` is the annex with its
  store, and `choose_entrance` clears that.
- **Every station store's door is a SLIDING GLASS door** (`store_front` in the generator: fixed glass either side, a
  `DOOR_` Empty of style `slide_glass` that the scene builder hangs as automatic glass leaves in the wall's plane; two
  leaves where the front is >= 4 m, else one -- `station_layout.store_door_w`).
- **Elevated hubs**: an entrance is THREE wing modules (`EH_WingEntrance_*`; `eh_modules` roles `entrance` and
  `entrance_flank`, which gets no wing piece); every other wing module but the machines is `EH_WingShop_*`, a 2.4 m
  shop against the outer wall whose glazed front and glass door face the HALL (user's choice), leaving a 2.3 m walkway. An elevated hub needs 65 m.
- **The restroom block's fixtures are the konbini's LIBRARY restroom kit** (user, 2026-09-28): washlet `WC_Toilet`,
  square `WC_Basin` + `WC_Mirror`, `WC_Partition` stall sides, `WC_GrabRail`, `WC_BabyTable`, and the accessible room's
  SOLID SLIDING door (the konbini's 引き戸, a `DOOR_` of style `slide`). A kit piece may now carry `PROP_` Empties: a
  LIBRARY fixture (custom props `piece` = `library:<Name>`, `collide`), shown in the station .blend as an instance of
  the LINKED library collection; `export_building_kit.markers` writes them to the manifest's `props`, and
  `layout_buildings.place_props` places them with the piece, so a library edit reaches every station on the next
  build. A mirrored hand turns a fixture by `180 - yaw` (it keeps its own hand). The export skips LINKED collections
  (they carry `bk_piece_path` too, and are their own kit's). Urinals are still the generator's boxes (the library has
  none). Pictures: `shot_station_hall.gd` views `wc_in_men` / `wc_in_women` / `wc_in_acc`.
- The generator retires untouched pieces the form no longer makes (`EH_Wing_*`, `EH_WingDoor_*`, `GH_AnnexShops_*` went this way).

