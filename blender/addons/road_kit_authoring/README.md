# road_kit_authoring — Blender addon

Interactive placement/authoring addon for the mesh-first road kit (`kit/lane_kit.blend`). See
`road_blender_godot.md` at the repo root for the full plan and phase tracker.

## Dev install (symlink, not copy — edits here take effect immediately, no addon reinstall)

From the repo root:

```bash
blender/tools/install_blender_addon.sh
```

This symlinks this directory into **every** installed Blender version's addons folder
(`~/.config/blender/<version>/scripts/addons/`) and enables it headlessly. **Re-run it after
every Blender upgrade** — Blender's addon config is per-version, so a fresh version directory
(e.g. after 5.1 → 5.2) does not inherit the symlink from the old one and the panel silently
disappears until this is re-run. See the top-level `README.md` "World Authoring Setup" section.

Manual fallback (if you only want one specific Blender version wired up):

```bash
ln -s "$(pwd)/blender/addons/road_kit_authoring" \
    ~/.config/blender/<version>/scripts/addons/road_kit_authoring
```

then enable it in Edit > Preferences > Add-ons, search "Road Kit Authoring".

## Panel — "Road Graph" (the current model: one mesh, vertices are junctions)

3D Viewport > Sidebar (`N`) > "Road Kit" tab > **Road Graph**. A whole network is ONE edge-only
mesh: **vertex = junction, edge = road segment, the cross-section lives on the edge domain** as
Blender attributes. Everything else — asphalt, kerbs, footways, junction pads, pillars, lane
routes — is *generated from it*.

**What is editable and what is output.** Exactly one object is input: the graph mesh (the island's
is `IslandRoads`). Every object carrying the `rka_generated_for` custom property
(`<graph>_Carrier`, `_Corners`, `_Nodes`) and everything in the `RKA_LANE_PREVIEW*` collections is
rebuilt from scratch on the next Build — **edits to them are silently thrown away.** That is the
usual reason "editing the road did nothing": the road you can click in the viewport *is* the
carrier, because the graph is a wireframe underneath it.

- *Build / Solve / Validate / Weld / Auto Aux / Preview / Export* resolve a generated object back
  to its graph, so clicking the road and pressing them works.
- *Assign To Selected Edges* / *Assign To Selected Nodes* cannot — a stamp writes to the edges you
  selected, and those are swept output. They refuse with the name of the object to edit instead.
- **Press *Edit Road Graph* (top of the panel) and it does the finding for you**: from a click on
  the road, on a corner, on a node pad or on the graph itself, it selects the graph, enters Edit
  Mode and switches to edge select. The panel shows the same button wherever the brush is hidden,
  so "I clicked the road and there is nothing to edit" has a button on it rather than a rule to
  remember.

**Why Assign can look like it does nothing** (three separate causes, each with its own message):

1. *"No fields enabled — nothing to assign"* — every field in the brush has a **checkbox beside
   it**, and Assign only writes the ticked ones. An untouched panel writes nothing.
2. *"No edges selected"* — Assign works on the Edit-Mode selection, not on the active object.
3. The stamp landed but geometry did not move: the **refresh toggle beside Assign** (`auto_build`)
   was off. Press *Build Road Graph* — the attributes are already written.

The panel prints the exact list of fields a stamp will write (`writes: lanes_fwd, median_width,
…`) directly above the button, because the reverse mistake is just as costly: **eight fields are
ticked by default**, so an Assign meant to change the lane count also rewrites the median, the
footways and the lane width with whatever the brush holds. Either untick what you do not mean to
touch, or press the eyedropper (*Pick From Active Edge*) first so the brush already holds that
road's own values.

**Lane counts have their own +/- buttons** (*Lanes on selected edges*), which read each edge's
value and add or subtract one. They touch nothing else, they work across a mixed selection (a
2-lane and a 3-lane stretch selected together each gain a lane rather than both being flattened),
and they are the right tool for "one more lane here" — the brush is for stamping a whole
cross-section.

**A vertex with two edges is a shape point, not a junction.** Drawing a road by extruding a vertex
leaves every interior vertex on `AUTO`, and `AUTO` at valency 2 now means "the road runs straight
through": one continuous ribbon, no trim, no pad. (Before, each of those vertices ended the chain,
so a hand-drawn six-vertex expressway came out as five separate two-point ribbons and every
chain-level feature — the auxiliary-lane taper, the lane-count transition — was confined to one
segment. The island generator sidestepped it by stamping `NODE_NONE` on all 1543 of its shape
points, which is why the generated network looked right and hand authoring did not.) Force a real
junction at valency 2 with `node_type = INTERSECTION`; a lane-count or median change does **not**
need one — that is a taper, see `lane_transition_length`.

**Making a ramp merge INTO a new lane instead of taking over an existing one.** Press
***Auto Aux Lanes At Ramps***. It finds every place a one-way arm joins or leaves a wider road —
a motorway gore *and* a slip road touching down on a street — and stamps the acceleration /
deceleration lane on the correct lane group of the receiving road, tapering it away from the
junction. The ramp's traffic then merges into the lane that opened for it; without it the ramp
merges into the street's existing kerb lane, on top of the cars already there.

**What closes the gap between a ramp and the lane is the node's own patch** — the same
Python-solved, GN-swept patch every intersection uses, not a separate mechanism. At a gore it is a
WEDGE rather than a pad: it reaches from the road's kerb out to the ramp's ribbon, and a ramp
corner that would fall inside the carriageway is clamped back onto the kerb line rather than
dropped. Both halves of that matter — reaching too far paves over the lanes the ramp is merging
into, not reaching far enough leaves ramp and lane visibly unjoined.

**A "gore" whose ramp cannot merge is solved as a JUNCTION.** A gore means nothing has to stop; a
ramp that is refused a lane has nowhere to merge into, so its traffic turns here like any other
arm. Shown to the solver as an intersection it gets the ordinary corner setbacks and a full pad,
which is what connects it. (A ramp refused because the road is no wider than itself is a different
thing — a fork, where both halves carry on — and stays a gore.)

**The barrier wraps the merge; it is never deleted by it.** An expressway's edge is a wall, not a
footway — the kit builds one from the same kerb band, just at a wall's height (`curb_height`, 1.0 m
on the island's `T1`/`T1C`/`RAMP` tiers). The kerb LINE is already a function of the point's lane
count (`offsets_for_counts`), so where an auxiliary lane opens, the wall rides out with it and
comes back in as it tapers — no switch needed:

```
|| o2 | o1 ||| i1 | i2 ||   // ramp //   two roads, each fully walled
|| o2 | o1 ||| i1 | i2 ||// ramp //      the corridor narrows to ONE LANE  <- || stops here
|| o2 | o1 ||| i1 | i2   // ramp //      only the ramp's wall, on the ramp's own edge
|| o2 | o1 ||| i1 | i2      ramp    ||   the nose: the ramp's inner wall opens
|| o2 | o1 ||| i1 | i2   i3         ||   ONE wall, outboard of the auxiliary lane
|| o2 | o1 ||| i1 | i2   i3         ||   ...held there for `aux_buffer_length`
|| o2 | o1 ||| i1 | i2 ||                after the taper, back where it was
```

Three rules, and between them they close every case:

1. **The outer barrier is never removed.** The kerb LINE is already a function of the point's lane
   count (`offsets_for_counts`), so where an auxiliary lane opens the wall rides out with it and
   comes back in as it tapers — no switch needed.
2. **The two barriers in the merge corridor stop where they would collide, and are joined there
   by an angled piece.** The corridor is bounded by the approaching carriageway's barrier and the
   ramp's inner one; they converge on the wedge between the two roads, and where they meet, both
   stop and a short diagonal ties them together — so the fence turns the corner instead of leaving
   two loose ends and a gap in the road's edge.

   The station is **derived per merge, never authored** (`graph_build.merge_corridor_ends`): it is
   `gap / sin(convergence angle)`, and across the island's served ramps that angle runs 1.8°–65°,
   so the distance runs from a couple of metres to a hundred. No constant can serve a 30× spread —
   which is what "the wall knob doesn't seem to do anything" looked like from the outside. Capped
   at half the approach chain (`MERGE_WALL_MAX_FRACTION`), and the build prints the range it chose
   plus any node that hit the cap.

   **`MERGE_WALL_GAP` is a collision margin, not a clearance.** The *lane* keeps its full width —
   that is what "the merge lane always has one lane of space" means — but the *wall* only has to
   stay out of that lane and off the ramp's own wall. Demanding a full lane's gap between the two
   barriers pulled the approach wall back 37 m on the testbed and left 36 m of the mainline's own
   edge with no barrier on it: a hole in the road's fence, opened while closing one in the ramp's.

   **The joint is a carrier chain, not a special case.** It is emitted the way
   `graph_solve.build_corner_mesh` emits a junction's kerb corner — a short polyline carrying the
   same `rka_*` attribute names with every band it does not want written as zero — so the one
   layer stack sweeps it and there is no second implementation of "what a wall looks like".
3. **The ramp's own inner wall keeps running** — it sits on the ramp's own edge and blocks nothing,
   and it is what keeps the wedge between the two roads closed — and stops at the SAME derived
   station as the approach's, because both bound the same wedge. `RAMP_WALL_OPEN` (12 m, measured
   from the junction vertex, never from the overshot tip) remains only as the fallback for a ramp
   with no identifiable approach arm to measure against. Past the vertex
   *both* of its walls stop: the overshoot exists to overlap the two surfaces, and a ramp still
   angling in at a few degrees walks its outer wall a metre and a half onto the asphalt over those
   8 m. From the vertex on, the carriageway's own barrier is the outer wall.

**The ramp arrives at the width of the lane it becomes.** A ramp is wider than a lane (it has
shoulders — 4.5 m against 3.5 m on the testbed), so swept at its authored width to the very nose
its edges finish half a metre proud of the carriageway's and the outer wall hands over with a
sideways step. The ribbon is therefore narrowed onto the lane over the same `ALIGN_BLEND_LENGTH`
smoothstep that slides it sideways — one gentle movement, about a metre over 120 m — so the two
walls meet exactly in line. `rka_shift` is untouched, so the lane centre does not move and the
exported route is unaffected.

Two earlier versions of this are worth knowing about, because both looked plausible. The first
switched the carriageway's barrier off wherever the auxiliary lane was more than 85 % open: on a
weaving section, where the lane is held open from one gore to the next, that removed the wall for
the *whole chain*. The second built the carriageway's barrier unconditionally — which is rule 1,
and right — but had nothing at all to say about the approaching arm, so its wall ran to the
junction and 2 m past it, straight through the ramp's entrance.

### The outline path — "Outline Edges" (EXPERIMENTAL, off by default)

Everything above is the **centreline** model: each band outboard of the asphalt is a lateral offset
from ONE chain's centreline. That is correct only where that chain's ribbon is the outermost thing
at that station, which is why a merge, a gore or a parallel flyover each needed a rule of its own —
and why there is always another one. Measured on the island: **257 of 3,736 kerb samples stand on
another road's asphalt**, and only about a third of those are near a merge. No merge rule can reach
the rest.

The **Outline Edges** toggle (beside *Build Road Graph*; `stage_edge_furniture`) stages the build
instead:

```
STAGE 1  surface        <graph>_Carrier   carriageway + median + deck
                        <graph>_Nodes     junction pads
STAGE 1.5  outline      <graph>_Edges     the road surface's outer boundary
STAGE 2  edge furniture swept on _Edges   kerb, railing   (footway + props: phase B)
```

`graph_edges.outline()` walks each chain's kerb line and drops the parts that lie inside another
chain's paved band, then emits the survivors as polylines carrying the same `rka_*` attributes,
in `build_corner_mesh`'s convention — **the polyline IS the kerb line, so the kerb sits at offset 0
and everything else rides outboard.** The very same layer stack sweeps it (`edge_spec()`), so there
is still exactly one description of what a kerb looks like. On the island that gives **0 of 3,441
boundary vertices on any road's asphalt.**

Three things fall out of the model rather than being arranged:

- **Union and clip are the same computation.** `_profile_offsets` gives `curb_off_left = ppos`
  while `paved_shift + paved_half = ppos` as well, so the kerb line and the paved edge are one
  curve. Clipping the kerb line against other roads' bands *is* taking the boundary of the union,
  and the thing being clipped can never disagree with the thing clipping it.
- **The corner closes with no joint.** Where chain A's kerb enters chain B's band, refining that
  transition onto the band edge lands exactly ON B's kerb line — because B's band edge is B's kerb
  line. A's run ends where B's run passes. That is the whole of `merge_corridor_ends`'
  `gap / sin(theta)`, its cap and its refusal, arrived at by construction instead of by estimate.
- **There is no left and right on a boundary**, only inboard and outboard — so the six `_mirror`
  pairs and the `CurbL`/`CurbR` duplication stop applying to edge furniture, and the long-standing
  absence of a `PropsR`/`RailR` (street furniture could only ever appear on one side) disappears
  rather than needing a fix.

What it still cannot do, and says so rather than hiding: where two ribbons run **parallel and
overlapping** without ever converging, a run stops against a road it never crosses and there is
nothing to hand the fence over to. Those ends are reported with their coordinates (60 of them on the
island — the pre-existing parallel overlaps). A polygon clipper would resolve them; walking curve
pieces cannot. That is the one deliberate deviation from the industry shape of this pipeline, and
it is the escalation to take if the report ever gets long, rather than adding another special case.

**Turning the flag off removes `_Edges` again** and gives the kerb back to the carrier — otherwise
the leftover object keeps its stack and keeps sweeping, and the flag looks inert while the kerb is
built twice.

**A merge follows the direction of travel, both ways.** An arriving ramp attaches to the auxiliary
lane of the carriageway going ITS way, and that lane opens at that carriageway's kerb; a departing
ramp leaves from the same lane. Where no such lane can serve it — the ramp is offside, the road is
no wider than the ramp, or the arm is turning rather than merging — the ramp is simply **one more
arm of the junction**, and its traffic turns there like any other road. The build prints how many
arms ended up that way and why (`N ramp arm(s) connect as ordinary junction arms rather than
merges: ...`), so the difference is never silent.

**When it declines, it says so on the edge.** Select the ramp's edge in Edit Mode and the
*Active edge* block at the bottom of the panel prints what the kit thinks it is — either

    ramp: merges at node 398 into road g12, forward group (63 deg)

or the reason it was passed over, with the number behind it:

    ramp: meets the road at 84 deg, past the 70 deg merge limit -- read as a turn, not a merge

**To override it, select that edge and press *Merge Selected Ramp Via Aux Lane*.** Pointing at the
edge is the answer to "is this a ramp?", so that operator skips the angle test entirely: the road
grows its lane and the merge goes into it. Everything downstream is identical to the automatic
path. The readout then adds *"but the road it joins already carries an aux lane, so the merge uses
it"*, so the panel never reports the rule while the file says otherwise.

Two things decide whether an arm qualifies automatically, both deliberately conservative:

- **it must be one-way** — an acceleration lane is for traffic that joins without stopping, and a
  two-way side street is a junction with a stop line, not a merge;
- **it must point roughly the way the traffic it joins is going** — `graph_solve.MERGE_ANGLE_DEG`
  (70°, and the operator's *Merge Angle*) is the cut between "a slip road merging" and "an arm
  turning at a junction". The same number decides the GEOMETRY: below it, the corner between a
  one-way arm and the road it joins is built as a nose, not as a junction pad sized to the
  corner's apex. That one change halved several of the island's touchdown pads (1,042 → 527 m²,
  1,105 → 549 m²) — a shallow arm's apex always ran into the size cap, which is what "the ramp
  occupies the whole road" looked like. A junction cannot be a merge for the lanes and a corner
  for the mesh, so both read this constant.

Doing it by hand instead is a trap worth knowing about: `aux_lanes_left` / `aux_lanes_right` are
the **forward / backward lane groups of the edge's own direction**, not geometric sides. Stamping
the wrong one is not a near miss — measured, the widened lane opens on the carriageway going the
other way, and the ramp ends up with **no successor at all**. Use the operator, or check the
active-edge readout at the bottom of the panel (`2F/2B (+1/0 aux)`) after stamping.

**A ramp is MOVED onto the lane, never cut short of it.** A ramp's polyline ends at the junction
vertex, which is on the mainline's centreline — so swept as authored, its last stretch would drive
diagonally across the road it is joining. The kit eases that stretch sideways onto the auxiliary
lane instead (`graph_build.align_ramp_ends`, blended over `ALIGN_BLEND_LENGTH` = 120 m), so the
ramp's edges line up with the lane's edges and the mesh runs all the way in. Everything further
back is exactly as authored, so the approach stays yours to adjust.

The thing this replaced was a nose setback derived from the angle the ramp came in at: at a
6° entry that works out to 46 m, so 46 m of ramp was never built and the mesh stopped in mid-air
short of the junction. Any setback computed from the entry angle has that failure built into it —
the shallower and more realistic the merge, the bigger the hole. What remains is a metre or two of
the ramp's own half-width, closed by the gore's nose wedge.

**Changing a ramp / express-lane exit by hand.** The auxiliary lane is normally derived by that
operator, which is the path the island generator uses. To override one:

- Select the trunk chain's edges (Edit Mode; *Select Whole Road* follows a chain through its shape
  points), then in **Carriageway** tick and set:
  - `aux_lanes_left` / `aux_lanes_right` — how many extra lanes, on the **forward / backward lane
    group**. These are travel-direction groups, *not* geometric sides; putting the lane on the
    wrong group builds it on the carriageway going the other way, where nothing can reach it.
  - `aux_taper_length` — how far the lane takes to open from nothing.
  - `aux_buffer_length` — the **extra segment after the merge**: how far past the gore the lane is
    held at *full* width before that taper starts, so a merge reads `gore → buffer → taper`
    rather than `gore → taper`. A joining driver gets a full-width lane to settle into instead of
    merging straight into a closing wedge, and the barrier gets a stretch at full auxiliary width
    instead of diving back inboard at the nose. (Meeting the ramp's outer wall *exactly* in line is
    the ramp's width taper, above — the buffer gives that handoff somewhere to land.)
    Default 40 m (`graph_build.AUX_MERGE_BUFFER`); *Auto Aux Lanes At Ramps* and *Merge Selected
    Ramp Via Aux Lane* both stamp it, and both expose it as **Buffer After Merge** in the operator
    panel. Set it to 0 for the old behaviour. Where a chain is too short for buffer *and* taper the
    buffer yields first — a lane that steps shut is worse than one with no settling length.
    Both distances are measured from the gore the lane serves.
    There is no "which end of the group" switch: an auxiliary lane **always** opens at the kerb —
    which under keep-left is the **left** of the stream's own direction of travel. An eastbound
    carriageway therefore has its kerb on the NORTH, and a ramp merging into it must approach from
    the north; one arriving from the south is *offside* and gets **no lane at all** (the panel
    readout says so on the edge). That refusal is the point: served anyway, the lane opens on the
    far side of the road from the ramp and the ramp's own mesh is aligned onto a lane it cannot
    reach. `allow_cross` does not license it — that flag is about whether a MOVEMENT may cross the
    opposing stream, and an offside ramp at a surface junction still connects, as an ordinary
    turning arm rather than as a merge.
    A ramp measured on the median side of the stream it serves is reported as a layout error
    (`Auto Aux Lanes` names the node) rather than built, because its traffic would have to cross
    the opposing carriageway to reach it — the layout is what needs fixing.
  - `lane_transition_length` — how far the road takes to gain or lose **one through lane** where
    this edge meets one with a different count. Stamp 2 lanes on one edge and 4 on the next and the
    ribbon steps `2 → 3 → 4`, one transition each, centred on the shared vertex. The vertex between
    them can be an ordinary `AUTO` one; a straight vertex where only the width changes is treated
    as a taper, not a junction, so the road stays one continuous ribbon through it.
- **The two carriageways taper independently, and each opens at ITS OWN gore.** A stretch between
  an exit and an entry carries an auxiliary lane on each side, each full width at the ramp it
  serves. Where the **same** side is served at both ends and the gap is under
  `graph_build.AUX_WEAVE_HOLD` (400 m), the lane is carried straight through as one continuous
  auxiliary lane — the ordinary weaving section, a genuine third lane between the two ramps.
  Beyond that it tapers shut after the first ramp and reopens before the second, as a real
  motorway does.
- **`allow_cross` on the vertex is what keeps an exit off the wrong carriageway.** It means "may a
  movement here cross the opposing stream?", and it must be **0 on every node of a limited-access
  road** — an exit ramp hangs off one carriageway, and traffic on the other cannot reach it without
  driving over the middle of the motorway. Left at its default of 1, an exit that leaves too
  steeply to read as a tangential diverge is classified as an ordinary intersection and the far
  carriageway gets a right turn straight into it. Keep it at 1 at a surface junction: a diamond's
  on-ramp genuinely *is* entered from both directions of the cross street, because that junction
  does break its median.
- A junction's own behaviour is on the **vertex**: `node_type` = `GORE` forces a tangential split
  (nose, no stop line), `NONE` makes it a shape point (the road runs straight through, no junction
  at all), `allow_cross` gates turns across the opposing stream. Stamp with *Assign To Selected
  Nodes*.
- **Run *Validate Road Graph* after any ramp edit.** Besides the graph checks it now audits the
  **movements** — what the routes mean rather than how the mesh looks — and reports the two ways a
  ramp goes wrong while the geometry stays perfectly well formed: a one-way arm fed from more than
  one carriageway where crossing is forbidden, and a ramp fed from a through lane instead of the
  auxiliary lane that opens for it. Both are invisible in the viewport.
- **`?` (Explain Node)** next to *Preview Lanes* prints every candidate movement at a junction and
  the rule that accepted or rejected it — the tool for "why is there no turn from here to there?".
  If it says *nothing arrives or departs here*, the junction was **merged**: two junctions with
  less than a car-length of road between them become one, and only the surviving root has lanes.
- *Preview Lanes* draws the routes as curves, coloured by movement, with flow chevrons
  (`RKA_LANE_FLOW`), so a ramp connection can be read directly in the viewport.

> **The island's graph is generated, so hand edits to `island_v3_roads.blend` do not survive.**
> `blender/tools/island_v3_to_graph.py` opens an *empty* file and writes the whole blend, so
> re-running it discards anything authored there. Edit `tools/island_v3_plan.py` (the source
> layout) for a change that must persist, and treat the blend as somewhere to try things out and
> to inspect what the rules produced.

## Panel — piece placement (the earlier per-piece kit)

3D Viewport > Sidebar (`N`) > "Road Kit" tab. This is the addon's real current feature set —
it's grown well past initial placement into a full mesh-first hand-authoring workflow
(this is the same tool used to hand-author Piece_5_1's (industry) `MANUAL` road content, the
reference example for how every other district's roads are meant to be authored going forward):

- **Godot Export** — one-click button that regenerates the district's `.lanekit.json` sidecar and
  runs the export/bake/navmesh pipeline (`tools/save_lane_kit.py` + `tools/build_piece.sh`) for
  the currently-open district. Watch the System Console for progress (~20-40s). Requires the file
  to be saved as `District_<theme>_<gx>_<gy>.blend` first.
- **Multi-District Group** — panel front-end for the multi-district combined edit session
  (`tools/open_district_group.py`/`writeback_district_group.py`, see `AUTHORING_GUIDE.md` §4):
  from a district file, check off which built neighbours to include (or type any other district
  stem(s), comma-separated, into "Other Districts" — not just adjacent ones), *Open Group* to
  append them all into one disposable scratch file at their true offsets and open it directly.
  While in that scratch session, *Add District(s)* pulls in more districts on the fly (typed the
  same way) without restarting — for when a fix turns out to reach further than where you
  started. *Write Back Group* saves everything back to each district's own file, rebuilds each,
  and checks the seam — all as background subprocesses (same modal-timer pattern as "Godot
  Export"), watch the System Console.
- **Kit Library / Curb Kit Library** — link every Collection from `kit/lane_kit.blend` /
  the curb-asset kit blend into the current file (true library link, not append — editing a
  piece in the library blend and reopening the district file picks up the change with no
  re-export step). A curb style can be set to "Asset" on any build operator's F9 panel, then
  pointed at a linked curb collection.
- **Placement** — search/pick a linked catalog piece, then *Place Piece* (modal click-to-drop,
  grid-snapped), *Duplicate* (offsets along the piece's own local placement direction, so a run
  continues correctly after a 90° rotation), *Rotate CW/CCW*.
- **Live Edit** — drag an `arm_*` Empty to rotate/reshape its intersection live, or a segment's
  `segend_A/B` to resize/redirect it (or `segbend` to bend/hill it) — all live, no rebuild
  needed. Includes a manual "force update" fallback for when a drag doesn't auto-refresh.
- **Select Piece** — lists every piece in the file by name for one-click whole-piece selection
  (no Outliner click needed first); *Freeze For Move* / *Freeze ALL* suspend live-edit
  regeneration before a Grab/Rotate on one piece or the whole file (required for a whole-file
  move — doing that with live-edit on will crash Blender); *Unfreeze & Rebuild* / *Unfreeze ALL
  & Rebuild* bring geometry back in sync afterward.
- **Multi-lane (seam marking)** — visual lane-direction/count readout per arm/segment end
  (incoming vs. outgoing lanes), plus a lane-map override field for asymmetric arm lane counts.
- **Intersection (prototype)** — `Build Intersection` at the active `arm_*`/`segend_*`/
  `segbend_*` marker or the 3D cursor; F9 to tweak preset/radius/lanes/traffic side right after
  building.
- **Straight Segment / Segment From Curve** — curve-backed pavement (`spine_*` Curve object,
  editable live in Edit Mode); Lanes Backward = 0 makes it one-way. `Segment From Curve` seeds a
  new self-contained spine by sampling an existing Curve object once.
- **Lane Transition** — tapers Lanes A -> Lanes B over its length (pavement + curb together),
  e.g. a 2-lane street narrowing into a 1-lane arm.
- **Extend / Insert** — context-sensitive continuation from whatever's active: a `port_*` Empty,
  an `arm_*` Empty, an Intersection collection, or a Segment collection.
- **Centerline** — builds a centerline from a lane mesh's `lanedata` vertex group.
- **Connectivity (Phase 3, not wired yet)** — `connect_eps` is exported for `lib/lane_kit.py`'s
  endpoint-clustering pass; still not wired to any operator.

Requires `kit/lane_kit.blend` to exist first — build it with
`blender --background --python tools/build_lane_kit.py` (see that script's docstring).

Roughly 20 `smoketest_*.py` scripts (`smoketest_collision.py`, `smoketest_freeze_all.py`,
`smoketest_curb_style_panel.py`, `smoketest_lane_map_panel.py`, `smoketest_open_ended_deck.py`,
`smoketest_transition_and_spine.py`, etc.) cover this feature set headlessly — run one with
`blender --background --python <script>` when touching the corresponding operator.

## Status

Well past the original Phase 1 skeleton — placement, live-edit, freeze/select, intersections,
segments, lane transitions, extend/insert, centerline extraction, and one-click Godot export
(`ops_export.py`, wired into `__init__.py`'s `MODULES`) are all present and in active use.
Still not present: dedicated `ops_connect.py`/`ops_validate.py`/`overlay_draw.py` modules and the
Phase 3 `connect_eps` wiring described above.
