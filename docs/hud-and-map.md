# hud-and-map

Moved out of `CLAUDE.md` verbatim on 2026-10-09 (PLAN.md 0.5 / F12). Sections:

- HUD system (`com.openworld.ui`)
- The rear-view mirror while driving (user, 2026-10-07)
- The map says where you are (PLAN.md 3.18n, 2026-09-21)
- The minimap turns with you, and the route is drawn on the road (user, 2026-09-20)
- The map shows the city: buildings, typed places, every grid code, north; one ground fill; square turnarounds (2026-09-22)

---

## HUD system (`com.openworld.ui`)

`HUDManager` (CanvasLayer in `HUDManager.tscn`) owns the on-screen HUD. Two pieces worth knowing:

### The layout: one panel per corner, one background, one palette (2026-09-18)

GTA V's corners with CS2's information, and nothing overlaps (gate **`tools/godot/probe_hud_layout.gd`** 21/21;
pictures `tools/godot/shot_hud.gd`, needs a display):

| where | on foot | in a vehicle |
|---|---|---|
| bottom-left | `Minimap` (150 px) over `FootHUD` health number + bar (and the air bar while swimming) | same |
| bottom-right | `WeaponHUD` (icon cropped to its silhouette and drawn at one common height, `ui.IconFit`; name; magazine large / reserve small; no count for fist or melee); `WeaponSlotsUI` above it is ALWAYS visible at `idle_alpha` 0.6 (PUBG / Valorant / Apex: six slots and a growing loadout should be readable at a glance) and comes up to full for 2.5 s on a switch or an inventory change; `idle_alpha = 0` is the CS behaviour | the DRIVER gets the vehicle cluster: speed (km/h; `imperial` for mph) beside `VehicleStatus`, a top-down damage diagram (body coloured by health, a square per wheel where the wheels really are: white, amber when the tire is damaged, red when flat, pulsing while sliding), and beside it the car's health as a PERCENTAGE in the same colour ramp (user, 2026-09-22: colour alone did not say how close the car was to burning); the car smokes and burns as well. In a drive-by car the compact `WeaponHUD` stacks ABOVE the cluster (always, no swap on aim); the inventory column stays hidden (the weapon wheel shows the loadout). A PASSENGER with a gun gets the weapon panel and column. While a race runs (`RaceDirector.raceActiveNow`) the weapon HUD and column step aside for `RaceHUD`; missions hide anything via `setWidgetEnabled` |
| top-right | the clock, the wanted stars (police row, gang row) and under them ONE feed (`Feed`): kill lines and pickup / mission / radio notices in one column (2026-10-08; `StatusFeed` is gone, `HUDManager.feedTop`) | same |
| centre | crosshair, `WeaponProgress` ring, hit marker, damage direction, interact prompt just under the crosshair | same |

- **One background**: `ui/hud_panel.tres`, the minimap's translucent black, behind every panel (a `Background`
  Panel in each scene, `WeaponSlotsUI`'s panel style, and `FeedEntry._draw` for feed rows), SQUARE (no corner radius
  anywhere in the HUD; the minimap is a square, `RoadOverlay.CORNER` 0). Text-only (alpha 0) was tried on 2026-10-05
  and measured on a bright ground: the white weapon silhouettes and the inventory list vanished, so the boxes stay.
  What made the HUD look "not aligned" was each widget drawing its background 6-8 px OUTSIDE its content, so the
  visible edges sat 12-20 px from the screen. Now every VISIBLE edge sits on one 20 px margin (content inset by its
  background's padding) and the boxes stacked in a corner are one width (health = minimap, weapon = inventory
  column); `probe_hud_layout` asserts both ("the visible edges share one margin", "each corner's stacked boxes are
  one width"; the old offsets fail them). A MENU has its own backing (`ui/menu_panel.tres`, the store list).
- **The store menu** (`ShopMenu`): Enter / click takes a row; `E` (the key that opened it) or `Esc` closes it, and
  `MenuManager` hands Esc to an open store first, so it does not go on to open the pause menu. A footer lists the keys.
- **Supplies** are a weapon stack in slot 6 (CLAUDE.md "Wanted level ..." -> "Healing supplies are a WEAPON stack"): the
  weapon panel and the inventory column show them; there is no separate supplies line.
- **One palette**: `ui.HudPalette`. Colour means state, never selection: white → amber (health under 50%, a
  quarter magazine) → red (health under 25%, empty); red is reserved for danger. Selection is carried by SHAPE and
  brightness: a white ▶ in the inventory panel's left gutter before the active row, which is full white while the
  others are 70% — readable for colour-blind players. (An inverted white chip was tried first and dropped: the
  outline around black text on white read as bold, smeared lettering.)
- **One outline**: 2 px of 55% black at every size (`HudPalette.OUTLINE` / `OUTLINE_PX`, `ui/game_theme.tres`, every
  HUD `LabelSettings`, the drawn race and area warnings). An outline's width is in pixels, so a constant size gives
  big and small text the same thin edge; the old 3–5 px at 85% made large numbers look heavy.
- **Draw order**: `UnderwaterOverlay` and `ScopeOverlay` are HUDManager's FIRST children, so every panel draws over
  the scope's black surround and the water tint (the health bar was hidden under the scope before). The minimap
  has a thin light rim (`rimColor`) so its translucent disc still reads over black.
- **Underwater tint** (`ui.UnderwaterOverlay`) follows the camera ON SCREEN (`WaterVolume.isUnderwater` of the
  viewport's camera): on foot, first person, a car's chase or cockpit view. It replaced a tint the Character drew
  from its own tick and camera, which is off in a driver's seat, so a car driven into the sea left the screen clear.
- **UI scale**: `display/window/stretch/scale = 0.8` over the canvas_items stretch — everything 20% smaller, still
  scaling with the screen height (the weapon list's text is ~10 px on a Steam Deck, just over Valve's ~9 px floor).
  One number for a future "UI scale" setting (`Window.content_scale_factor`).
- Numbers are Aldrich (`assets/ui/Aldrich-Regular.ttf`); the DSEG7 seven-segment font is gone.
- The local player's own vehicle nameplate is hidden while they are in it, by the plate's own relevance rule
  (`Nameplate.carriesLocalPlayer`: the local player's body, or a car any seat of which holds them). HUDManager used to
  hide it once on entry and the 0.25 s relevance check put it back, since the driver is a Player.

The visibility machinery is unchanged: a `Situation` enum (`ON_FOOT`, `VEHICLE_DRIVE`, `VEHICLE_PASSENGER_WEAPON`,
`VEHICLE_MOUNTED_WEAPON`, derived from `Vehicle.getWeaponMode()` in `situationForVehicle`) and a code table
`BASE_LAYOUT` of table-managed widgets per situation (`FootHUD`, `WeaponHUD`, `VehicleHUD`, `WeaponSlotsUI`,
`DamageIndicator`), with `setWidgetEnabled` / `clearWidgetOverride` runtime overrides that win over the table.
Feeds, crosshair, radial menu, scope, area warning, hit marker, race HUD and the map widgets are self-managed. The
table is **code, not an exported `Dictionary`** — a nested generic `Dictionary` export crashes the godot-jvm
registration scanner (see Known Quirks).

### Weapon switch/reload progress ring (`WeaponProgress`)

`WeaponProgress` (`ui/WeaponProgress.tscn`, a radial `TextureProgressBar` centered on the crosshair —
renamed from the old unused `WeaponReloadProgression`) polls the active player's `WeaponController` each
frame: it shows + fills 0→100% during a weapon switch (`getSwitchProgress`) or reload
(`getReloadProgress`), hidden otherwise (switch tints cyan, reload amber). The ring texture is generated
procedurally in `_ready` (a transparent annulus), so no ring asset is needed. Not table-managed (it
self-hides); wired in `HUDManager.wirePlayer` like `WeaponSlotsUI`. The progress getters return -1 when
their timer is idle. The ring texture is generated by default, but assign an `@Export ringTexture` (a
baked PNG) to use an asset instead (cheaper load, exact look). **Centering:** with
`nine_patch_stretch = false` a `TextureProgressBar` draws its texture at **native size, top-left aligned**
(it does NOT stretch to or centre within the control rect). So the control rect must be **symmetric AND
exactly the texture size** — `WeaponProgress.tscn` uses offsets `-32/-32/32/32` (a 64 px rect) to match
`RING_PX = 64`; the radial fill pivot (`radial_center_offset` 0,0 = rect centre) then coincides with the
texture centre on the screen centre, lining up with the crosshair dot. A rect *larger* than the texture
(e.g. the earlier `±34` → 68 px) leaves the 64 px ring pinned top-left, ~2 px off-centre — the bug. Keep
the scene offsets and `RING_PX` in sync, and don't override the offsets in `HUDManager.tscn` (use the
scene defaults). Same rule for a baked `ringTexture`: make its pixel size equal the rect.

### Damage-direction indicator (`DamageIndicator`)

Industry-standard directional hit cue: on local-player damage a red arc appears around the crosshair
**rotated to the attacker's bearing** (top=front, sides=left/right, bottom=behind), fading over
`fadeSeconds`; repeated hits from one bearing stack opacity up to `maxAlpha` (a small pooled set of arcs
handles multi-source hits). Bearing is computed relative to the player camera's facing, so it stays
correct as the camera turns.

**Data path:** `EventBus.characterDamagedFrom(CharacterInfo victim, Vector3 sourceWorldPos)` — emitted in
`Health.applyDamage` (single-player/host, attacker world pos threaded through
`ImpactManager.processHit` → `Health.takeDamage`; weapons supply it via `WeaponItem.resolveAttackerPosition`,
explosions via the blast center). `HUDManager.onCharacterDamagedFrom` filters to the local player and
calls `DamageIndicator.onDamagedFrom`. **Networked:** the host is the single broadcast site —
`Health.applyDamage` calls `NetworkManager.broadcastDamage(victimId, damage, hasSource, source)` for every
server-applied hit (host-originated AND client-relayed), and `MSG_DAMAGE_BROADCAST` now carries the
attacker world position (`hasSource` u8 + Vec3 — cheaper than a UUID and exact); the victim's client
re-emits `characterDamagedFrom` in `handleDamageBroadcastMessage`. The per-hit broadcast moved **out** of
`handleDamageRequestMessage` into `applyDamage` (the relay path flows through `applyDamage` on the host
anyway), so it is now the one place the hit cue + direction are sent.

---

### Roads on the map, and a GPS route along them (`world.RoadMap` / `world.RoadGraph`, PLAN.md 4.7, 2026-09-17)

The minimap and the full map draw the road network, and the GPS arrow follows a ROUTE along the lanes
instead of pointing at the waypoint as the crow flies.

- **The network is read from the lanekit sidecars, never from the scene.** The `Lane` nodes a zone
  instances exist only while that zone is streamed, so a route to a waypoint in an unloaded zone would
  have nothing to walk (and `LaneGraph` is built from exactly those nodes). `RoadMap.graph()` takes every
  `ZoneMarker` whose zone streams `.../pieces/<stem>.tscn`, reads `res://assets/world_source/pieces/<stem>
  .lanekit.json` (the convention `build_piece.sh` already uses), and places it with
  `Zone.geometryFrame(marker)` — new, beside `placeGeometry`, so a sidecar lands where its piece does.
  No second road record. Rebuilt when the scene or the set of road zones changes; 16 ms for DebugRoads,
  55 ms for the island (218 lanes, 2.4 MB). The sidecars are in `export_presets.cfg`'s include filter,
  since `assets/` is otherwise not exported.
- **`util.MiniJson`** reads them in plain Java: through Godot's `JSON` every number is a bridge call, and
  a unit test could not run it at all.
- **`RoadGraph` is engine-free** and the successor rule is the runtime's (`LaneGraph.successorsOf`): the
  authored `next` list, else every lane starting within `JUNCTION_RADIUS` of the end minus the direct
  reverse. So a route only makes movements a car could make. Dijkstra over lanes (cost = metres to a
  lane's START) plus `inner_lane`/`outer_lane` lane changes at `LANE_CHANGE_COST` 15 m — without the
  lateral edge a left turn owned by the other lane is unreachable. Start and goal are projections; both
  take every lane within `CANDIDATE_SLACK` 10 m of the nearest, so a player on a two-way street is not
  sent to the end of the wrong carriageway to turn round. The start is snapped in 3D (a body on a
  bridge), the goal in plan (a map click carries the player's height).
- **Re-routing is GTA's "recalculating"**, never a per-frame search: per character, on a new waypoint, a
  rebuilt network, or the body more than `OFF_ROUTE_METERS` 25 m from the route (at most once per
  `REROUTE_SECONDS` 1 s).
- **`RoadMap.gpsTarget` is the arrow's one rule:** the route's point `LOOKAHEAD_METERS` 30 m past the
  body's place on it (which leads a body that is off the road ONTO it first), and straight at the
  waypoint within `DIRECT_METERS` 40 m, past the route's end, or with no route. A race still points at
  the next checkpoint directly. `GpsArrow.followRoads` (`@Visible`, on) is the control knob.
- **Drawing is one owner, `ui.RoadOverlay`**, shared by `MinimapController` and `WorldMapManager`. The
  roads are the BAKED picture (4.7b, below) drawn as one textured polygon; the route is drawn on top in the
  player's colour, simplified at 0.5 m (`Route.drawXZ`, cached), then a thin line from where it leaves the
  road to the waypoint.

Gates: **`RoadGraphTest`** (6, on the real sidecars — a route across DebugRoads' junction into the other
zone's lanes, ending on the nearest lane; 500 random island pairs, every route legal and every
BFS-reachable goal routed) and **`tools/godot/probe_gps_route.gd`** (13/13 on DebugWorld, 12/12 with
`-- --world=island`): the real HUD, the waypoint set by opening the map with `map`, zooming with the
wheel and left-clicking; roads drawn on both maps; the route a legal chain (checked independently from
the same sidecars) that crosses `link -> connector -> spur` and ends on the lane nearest the click; the
arrow's target on the route 30 m ahead; off the road it points at the road (57 deg off the straight
bearing); straight at the waypoint within 40 m; right-click clears. `-- --control` (`follow_roads` off)
fails exactly 2. Not covered: the co-op half (a teammate's waypoint is drawn but routed only for the
local player, by design — each peer routes for itself).

### The road map is BAKED — nothing about the roads is derived per frame (PLAN.md 4.7b, 2026-09-17)

The user asked for the GTA model: a pre-rendered map, a pre-built path graph, and only the route drawn live.
Before this the minimap redrew all 218 island lane polylines every frame (each a list of `Vector2`s and a
bridge call), and every snap measured every lane.
- **`tools/godot/bake_road_map.gd`** (`-- --world=debugworld|island`, `-- --check` writes nothing and exits 1
  on a stale bake) writes `src/main/resources/com/openworld/world/roadmap/<Scene>.roadmap.bin` and `.res`.
  Re-run it after a road build, a zone move or a `WorldBounds` change.
- **The picture (`world.RoadRaster`, engine-free)** covers the map square to the `WorldBounds` wall (without
  a wall, the roads plus 100 m). It is a power-of-two `FORMAT_LA8` image, alpha = road, finest 0.5 m/px and
  at most 4096 px: the island is 4096 px at 1.05 m/px, DebugWorld 2048 px at 0.42 m/px.
  - It paints ROADS, not lanes: each lane is swept at its width and the result is CLOSED by `GAP_FILL`
    2.5 m (grown, then shrunk back with a chamfer distance transform). So the 3 m median of a divided road
    fills in and the outer edges stay put. Without the closing every arterial read as two parallel lines.
  - Mips are the MAX of each 2x2 block, so a 20 m road is still at least a pixel on the whole-island view,
    where an averaged mip chain fades it out.
  - It is saved as a compressed `Image` resource (`ResourceSaver.FLAG_COMPRESS`): island 574 KB, loads in
    ~19 ms with the mips as written. A `PortableCompressedTexture2D` also saved, but headless cannot read a
    texture back to verify it, and a PNG import would regenerate AVERAGED mips.
- **The graph file (`world.RoadMapBake`)** holds the lanes already in world space with their AUTHORED ids.
  `RoadGraph.finish` resolves successors on load by the live rule, so a bake cannot carry a different rule.
  Island 1.0 MB, loads in 12 ms (live: 393 ms parse and index + 87 ms paint).
- **The lookup (`world.RoadIndex`)**: a 32 m cell grid over the whole square, sea included. For each cell,
  with centre c and half-diagonal h: `U = min d(c, lane) + h`, and the cell lists every lane with
  `d(c) <= U + h + CANDIDATE_SLACK`.
  - `RoadGraph.snaps` over the cell list is exactly a full scan for a plan snap. For a 3D snap it is exact
    whenever the nearest found is `<= U`; otherwise it scans, which only happens for a body far above every
    road.
  - A map click 600 m offshore is one array read plus a few lanes; the island's largest cell holds fewer
    than half the network.
- **A stale bake is never drawn.** The bake's signature covers every sidecar's path, placement frame and md5,
  plus the square. On a mismatch `RoadMap` builds live with the same code, prints the reason once, and
  `RoadMap.source()` reads `"live"`. The GPS probe asserts `"bake"`.
- **The full map is the GTA pause map.** It opens FITTED to the whole world (the square), the wheel zooms
  about the cursor, a left drag (past `dragThresholdPx`) pans, a left CLICK (press and release without a
  drag) sets the waypoint, and a right click clears it.
  - Blips are limited to `blipRangeMeters` (400) around the player.
  - The zone load rings are off on both maps (`showZoneRings`): with 14 island traffic zones of 1 km they
    covered the map.
  - Probe readouts: `world_to_screen_now` / `screen_to_world_now` / `road_map_drawn_now` on the map;
    `road_map_source_now` / `road_coverage_now` on the minimap.
- Gates: **`RoadMapBakeTest`** (3):
  - the index agrees with a full scan at 4000 random island points, plan and 3D;
  - every lane sample is on a fully painted pixel, nothing is painted 60 m from a road, the chuo_dori median
    is painted, and 1.5 px past its outer edge is not;
  - a bake read back routes exactly like the live graph on 150 random pairs.

  **`probe_gps_route.gd`**, now 18/18 on DebugWorld and 17/17 on the island. New: the source is the bake,
  the picture is road under the route's ends and empty off the road, the map opens fitted with both wall
  corners on screen, the wheel zoom moves the point under the cursor 0.00 m, and a drag pans without
  dropping a waypoint. `-- --control` still fails exactly 2.

  `tools/godot/shot_road_map.gd` (needs a display) saves the minimap, the fitted map and a zoomed map.
- **Limit:** a junction pad is not in the lane data, so a pad's interior gap wider than 5 m can show as a
  small hole (one on DebugRoads' east junction). The fix is painting pads from the record, not a bigger
  `GAP_FILL`, which would start merging a ramp into its mainline.

## The rear-view mirror while driving (user, 2026-10-07)

`ui.RearViewMirror` (built in code by HUDManager, self-managed): a strip at the top centre while the LOCAL player
drives with the carrier's own camera on screen (`Vehicle.isDrivenViewOf`), the racing-game convention (Forza, GT, NFS),
drawn mirror-flipped, ON every time the player takes the wheel (C hides it for that drive). The chase view looks back from `roofLift` over the roof; the first-person views from the
driver's eye HEIGHT but just past the back of the hull (from the eye itself the headrests filled it). `rear_view` (C)
toggles it. Cost control: its own SubViewport SUPERSAMPLED at `renderScale` 1.5x a strip `widthFraction` 22% of the
screen wide (user: smaller and crisper; about the old strip's pixel count), refreshed every `updateEvery` (2) frames, `farPlane`
150 m, mesh LOD threshold 2, FXAA only, no positional shadows, a copy of the world Environment with SSAO / SSIL / SSR /
glow / SDFGI / volumetric fog off, and nothing rendered while hidden. **A blurred mirror is resolution, not meshes**:
at `renderScale` 0.6 (an upscaled target, which also samples blurrier mips) it was visibly soft; 1.0 costs nothing
measurable, because draws, not pixels, are the cost here. Measured in the city (island safe house, parked, chase
view, ON/OFF alternated): +1.5 ms p50, +2.4 ms p95, +1 500 draws (~16%); DebugWorld +0.45 ms. Gate
**`tools/godot/probe_rear_view.gd [-- --world=island] [--shot=<dir>]`** (display): hidden on foot, shown driving,
looks back (dot -0.998) in chase and first person, renders every other frame, C hides it and it renders nothing.

## The map says where you are (PLAN.md 3.18n, 2026-09-21)

The map drew roads and a route and nothing that NAMED a place, so a player could not say where they were and a
developer could not tell which zone a bug was in. Both halves are DERIVED from records that already exist.

- **`world.Places`** reads `world/places/<Scene>.places.json`, written by `island_buildings.py` from the same
  placement that writes the buildings: a building is a place because the placement made it enterable (its scene
  is a `_Shop` or `_Open` variant), and a region is a box that placement already uses. So a new shop reaches the
  map by re-running `derive`, and **the map can never name a building that is not there** — the failure a
  hand-kept marker list has.
- **PER SCENE, like `RoadMap`'s bake.** One fixed path drew the island's shops on DebugWorld's map at island
  coordinates. The world is found by walking the OWNER chain to its outermost root, not from
  `getCurrentScene()`, which is null for a world a probe `add_child`ed rather than `change_scene_to_file`d —
  keying on it would make every gate measure a different code path from the game.
- **Two positions per place and they mean different things:** `at` is where the blip sits, `go` is the front
  face, which is where the door is. A click within `placePickPx` of a blip takes that PLACE and sets the
  waypoint to `go`; `RoadMap` then snaps the goal to the nearest lane, so `go` decides which side of the block
  you are routed to. Blips are SQUARES so they never read as a character or a vehicle (both are discs), and
  ordinary shops appear only under `placeDetailRange` so a whole-island view is landmarks, not 94 konbini.
- **The region underlay was REMOVED from the map (2026-09-22: overlapping boxes, hard to read); the postal grid is the
  background now** (see "The safe-house start" below). The HUD still announces a region on entry — DERIVED every frame from the player's position against the same boxes, never latched on a
  trigger volume, so it is right after a teleport or a scene load, with a 1 s settle because the boxes touch.
- **`showZoneIds`** is the debug half: each streaming zone's id over its marker, off by default.
- Gate: `probe_gps_route.gd` **29/29 island** (every place is an enterable building or a site in the scene; the
  region the map reads is the record's own box, 0 of 109 disagree; a click on a blip takes that place and its
  waypoint is the door; a click away from every blip is an ordinary waypoint) and **23/23 DebugWorld**, where
  the first check is that a world with no record draws no places.
- **Two probe defects fixed here, both of which made a gate measure nothing.** The heading-up minimap case set
  `look_at` on `ActiveCamera`, which the TPS rig rewrites every frame (the trap `probe_night_lights` records) —
  it turns the PLAYER now, and derives the view yaw from the game's own `atan2(-dx, -dz)` rather than writing a
  sign down. And **a GDScript error inside an awaited coroutine aborts THAT coroutine and lets the caller reach
  its RESULT line**, so a probe that skipped half its cases printed PASS; the probe counts its checks now.
- **Matching a record to a record by a FORMATTED coordinate is a trap**: the places record rounds to 2 dp and
  two printf implementations disagree on a .x5 boundary, which read as 4 shops that do not exist. Matched by
  DISTANCE.

## The minimap turns with you, and the route is drawn on the road (user, 2026-09-20)

Two asks, one answer each.

- **Heading-up minimap.** `MinimapController.rotateWithHeading` (`@Export`, on) turns the map so the way the
  player is FACING is up, with the arrow FIXED pointing up — GTA's radar, and what makes "the line goes left, so
  turn left" readable without reading a compass first. The **full map stays north-up**: a paper map you are
  reading is a different job from a radar you are steering by. It is one angle, applied in one place:
  `RoadOverlay.project` is now the single world→screen mapping for the blips, the route AND the baked road
  picture, so they cannot come to disagree about which way the map faces. The picture's polygon does not move —
  its **UVs** do, carrying the INVERSE rotation, because a UV is the inverse of that mapping.
- **The route on the tarmac.** `world.RouteRibbon` (AutoLoad) draws the GPS route as a band on the road ahead.
  GTA IV/V draw one (San Andreas only drew it on the radar), and here it is nearly free because the hard part
  exists: `RoadMap.routeFor` already returns the route as lane samples **in 3D** and re-routes at most once a
  second, so the band is one `ImmediateMesh` rebuilt only when the route or 5 m of progress has changed — one
  draw call of a few hundred triangles, never a per-frame search. It takes **the lane's own Y** (`Route.points`
  is {x, y, z} triples), so it rides a bridge deck correctly; a ray down from above would have found whatever
  deck is overhead, which on this island is a real case. It is DERIVED, never latched: it shows what the routing
  already says and goes with the waypoint. Nothing is saved or sent — a teammate's waypoint is drawn on the MAP,
  but each peer routes for itself.
- Gate: `tools/godot/probe_gps_route.gd` (now 22/22 on DebugWorld). Heading-up is asserted **by measurement**,
  not by reading the angle back: a point 20 m dead ahead must land straight up on the radar at three different
  headings, and with `rotate_with_heading` off NORTH must land up instead. The band draws 97 quads over the
  route and the control knob removes it.

## The map shows the city: buildings, typed places, every grid code, north; one ground fill; square turnarounds (2026-09-22)

- **Every building is on both maps** (`world.BuildingMap`): `island_buildings.py write` puts each building's
  footprint (its type AABB, placed) into the places record as `footprints` ([kind, 4 corners]), and the map paints
  them ONCE into one LA8 picture over the road picture's own square (2048 px max, averaged mips so a zoomed-out city
  reads as block density), drawn UNDER the roads with the same view mapping (`RoadOverlay.drawBuildings`, the road
  picture's `drawPicture`). Painted at load rather than baked: the buildings are re-derived more often than the
  roads. `buildings_drawn_now` is the probe readout.
- **Every place at every zoom, typed** (`RoadOverlay.PlaceKind`, the one table): a coloured square with a type code
  in it -- H safe house, W weapon counter, 1 konbini, 2 gas station, 3 restaurant, 4 station, 5 landmark, 6 other --
  and a legend on the full map. Names wait for `placeDetailRange` (landmarks always), so a zoomed-out map is squares,
  not text; the code is the stand-in for a label later.
- **Every postal cell prints its code** (user: "so the user does not need to guess"): `postalCellLabelPx` 20 on the
  full map, the font shrinking to the cell (`RoadOverlay.labelFontSize`, >= 7 px), white at 85 % with a dark
  outline. A click on a code sets the waypoint to that cell's centre (`pickPostalLabel`, sharing the label's own
  position rule `postalLabelPoint`; `picked_postal_now`), after a place blip and before a bare waypoint.
- **North marker** (`RoadOverlay.drawNorth`): on the minimap RIM in north's on-screen direction (it travels round a
  heading-up radar; `north_at_now`), top-right on the north-up full map.
- **One ground fill.** The terrain's "Urban" layer (the block ground `island_ground.py` paints) is the footway's own
  concrete (`tools/make_urban_texture.py --from-footway`: `T_Concrete` albedo + a luminance height, normal + the
  ORM's roughness), with `M_ConcreteTile`'s tint (0.92, 0.90, 0.86) and tile (`uv_scale` 0.3663 = 2.73 m) on the
  texture asset. The generated aggregate is still the script's default mode.
- **`island_world.sh --only ground` is NOT safe on its own** (measured 2026-09-22): the stage derives the block
  surface from a dump of the CURRENT terrain, which already carries the previous block layer, so the layer it
  writes no longer agrees with the road stamp -- `probe_road_stamp` then fails "stamping again changes nothing"
  (22 337 vertices) and "restore puts the natural ground back" (0.09 m). Re-run from `--from terrain`, which lays
  the natural ground down first. (The block heights themselves are absolute and unchanged; it is the layer and
  the restore that break.)
- **The land under an elevated road is painted with the block** (`island_ground.UNDER_REACH` 40 m): a deck's
  footprint is kept out of the FILL on purpose (nothing may raise ground under a viaduct), so the strip under C1
  between two paved blocks kept the elevation-based BEACH paint. It now takes the block's paint wherever it adjoins
  paved ground; open country under a viaduct is untouched. Island paint 3.132 -> 3.317 km2.
- **`ZoneManager.maxLoadsPerTick` caps PARSES, and the main thread goes NEAREST FIRST.** A zone with no geometry
  (a crowd, a traffic zone) parses nothing and now starts at once instead of queueing behind every building cell --
  measured, the four crowd zones next to the player were still queued when its own had settled
  (`probe_island_peds` "the streets ahead are already populated" failed, 0 in the 150-300 m ring; after, 5 crowds
  and 74 light peds). And `processStreamTasks` steps the NEAREST ready task (distance / load radius; an unload
  ranks at `UNLOAD_RANK` 0.5) rather than the first in map order, so a crowd's spawn queue cannot hold the one
  main-thread slot while the road piece under the player waits.
- **A turnaround is a rounded SQUARE** (user: Japan rarely has a circular approach; a square is a block to build
  round): `island_turnarounds.loop_line` puts a T junction in the middle of the square's near side, the arms leave at
  90 deg, and four 90 deg corners are filleted to `CORNER_R` 15 m; `SIDES` 90/110/130 m are searched, smallest
  first. The airport end became 90 x 90 m (was a 43 x 59 m teardrop).

## The map key, redone: what a player DOES something at; the police search disc (user, 2026-10-11)

User: "update the map to include mission areas / all enterable buildings, police stations / gang / mission area
instead of landmark; there is no longer a weapon store, so re-do the keys; mark konbini small and big", and "add the
circle area of the police search in the minimap".

`ui.RoadOverlay.PlaceKind` is still the ONE table the blips and the full map's legend read. The kinds, in legend
order: **H** Safe house, **M** Mission, **P** Police (station, koban, impound), **G** Gang ground (any place the
record gives a `gang`, and the Gang* kinds), **+** Hospital / clinic / fire, **T** Station -- these six are `major`:
named at every zoom -- then **K** Konbini large and **k** Konbini small (both sell weapons; `KonbiniL` / `KonbiniS`),
**2** Gas / repair / car dealer, **3** Bank, **4** Food and nightlife, **5** Shops and services, **6** Other
enterable / site. "Weapon counter" and "Landmark" are gone (a name used to decide the first, a tier the second);
the old `k.contains("Station")` also made a police station, a fire station and the station mall a rail station --
a station is `Station_*` only now. Every place is still drawn at every zoom (all 237 are enterable buildings or
sites: the record lists nothing else).

**Mission places are not in the places record** (they are not buildings): `RoadOverlay.withMissions` appends one
`Mission` place per `ActivityRuntime.missionSpots()` -- a placed mission the local player can start now, or one
that is running -- at its placement node, named by the mission's title. A finished mission leaves the map.

**The search disc** (`MinimapController`): while the police have LOST the local player, a blue ring and faint fill
at `EnforcementDispatch.searchArea(playerId)` = the last known place and the radius their units are searching (8 m
growing 1 m/s to 45 m). It is the host's knowledge read directly: a co-op guest does not see it yet (it would ride
`WORLD_EVENT_WANTED`). `probe_lose_police` checks the readout (`search_area_now`).
