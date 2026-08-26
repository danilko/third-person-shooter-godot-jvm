# road_kit_authoring — the point/port road graph

Design of record: **`blender/ROAD_POINT_GRAPH.md`**. This file is the map.

## The model in four lines

| Concept | Is | Blender |
|---|---|---|
| **Road** | an ordered corridor — a chain of points | a Collection under `ROAD_MANAGER` |
| **Point** | a **station** *and* a **port**: position, cross-section, connections | an Empty (`obj.rka_pt`) |
| **Link** | an authored connection, typed `SEGMENT` / `JUNCTION` / `AUX` | an entry in `point.rka_pt.links` |
| **Junction** | a clique over `JUNCTION` links; the members **are** the stop lines | derived; owns a `JCT_*` parent |

Every along-the-length change — lane drop, lane opening, one-way, an acceleration lane with its
taper and buffer — is just *"two stations that differ"*. That is what deletes the ~900 lines of
special-case inference the previous (mesh-graph) model needed for the same roads.

## Modules

| Module | Owns | bpy? | Self-test |
|---|---|---|---|
| `point_model` | the schema + the git-diffable `.roads.json`; the Empties are a **view** of it | optional | `python3` |
| `point_profile` | station → `lane_profile.Profile`; the slot ids `F0.. R0.. AF0.. MED` | no | `python3` |
| `point_solve` | chain → carrier numbers; clique → pad, fillets, turn paths; `Auto Setback` | no | `python3` |
| `point_edges` | the road **edge**: where kerbs open, from the paved footprints | no | `python3` |
| `point_validate` | **the gate** — a build that fails it is a failed build | no | `python3` |
| `point_export` | `.lanekit.json` **v2** — real bezier handles, `junctions[]`, explicit `spawnable` | no | `python3` |
| `point_nodes` | the Geometry Nodes vocabulary: spine / band / deck / pillars / assets / finish | yes | — |
| `point_build` | carrier + stack + pads + ground cut + collision; `ROAD_MANAGER_GEN` lifetime | yes | smoketest |
| `point_ops` | the authoring gestures (§4.1) | yes | smoketest |
| `point_panel` | the point **inspector** + the **Connections** list (deliberately not a stamping brush) | yes | smoketest |
| `point_overlay` | the GPU overlay — what makes hundreds of points legible, and what follows a drag | yes | smoketest |
| `point_preview` | the **traffic-flow preview** — the EXPORTED lane graph, its defects, and cars walking it | yes | smoketest |
| `point_live` | depsgraph dirty set + debounced rebuild; geometry on **settle** only | yes | smoketest |

## Verify

```bash
blender/tools/check_roads.sh          # 17 checks — self-tests, the lanekit gate, the smoketests
blender/tools/check_roads.sh --quick  # pure-Python only, no Blender, ~2 s
```

`smoketest_point_coverage.py` is the whole-plugin one: it drives **every registered operator** and
**executes every panel's `draw()`**, and it fails if you add an operator or a sidebar button without
a test behind it.

## Building your first road (View3D ▸ N-panel ▸ **Road Kit**)

**Fastest:** `Author ▸ Learn ▸ Add Sample Network`, then `Build ▸ Build Roads`. That gives you two
streets crossing, an elevated highway on piers, and an exit ramp — a worked example of all four
link types to pull apart. Everything below is what it did, by hand.

Seven panels: **Author** (the gestures), **Road Point** (the active station), **Connections**
(what it is joined to), **Junction**, **Road** (the corridor's base profile), **Preview** (the
exported traffic graph), **Build**.

### 1. A straight road

1. `Author ▸ Corridor ▸ New Road` — creates a `ROAD_MANAGER/road_new` collection and its first
   point. Open the redo panel (bottom-left) to set the name, lane counts and width up front.
2. With that point active, press `Extend Road` repeatedly. Each press adds a point along the chain
   tangent and links it `SEGMENT`. Drag points with **G** like any Empty; the overlay follows.
3. `Build ▸ Build Roads`.

The chain order **is** the object-name order (`road_new_p000`, `_p001`, …), and **FWD is increasing
index** — that is what fixes which side is left.

### 2. Change the cross-section along it

Select a point and edit **Road Point ▸ Cross-section**. A lane count that differs from its
neighbour *is* the taper — there is no taper length to set, because **the taper length is the
distance you put between the two points**. If it is too short for the road's `design_speed` the
gate says so and the link draws **red** in the viewport.

The length it asks for is the real merge-taper standard (`L = W·S²/155` up to 70 km/h, `0.6·W·S`
above it) — 3.5 m at 80 km/h wants 168 m. **The world is not 1:1**, so if that eats a district,
lower **`taper_factor`** on the **Road** panel rather than fighting the gate: it scales the demand,
`1.0` is the book, and it is a visible authored decision on the road it applies to. Two things are
already exempt and need no factor: a lane **departing onto a ramp** (nobody merges at a gore), and
a width change at the station that owns the `AUX` link.

- `lanes_fwd` / `lanes_bwd` — `0` on one side gives a one-way street.
- `drop_side` — *which* lane a decrease removes (kerb-side by default; `MEDIAN` for an offside exit).
- `aux_fwd` — an auxiliary lane, always outboard (`aux_side = MEDIAN` for an offside exit).
  `0 → 1 → 1 → 0` across four points is an acceleration lane, its taper, its buffer run and
  its close. It **counts as a lane**: `lanes_fwd = 3, aux_fwd = 1` is a four-lane carriageway,
  and both the panel and the overlay (`3+1|3`) say so.

Editing many points at once: select them, make the one you want to copy **from** active, then
`Author ▸ Cross-section brush ▸ Apply Cross-Section` and tick **only** the group you mean.

### 3. Connect two points

Two ways, and **the active point is always the source** in both:

**By selection** — select two points and press `Author ▸ Connect`. Whatever you clicked *last* is
the source.

**By name** — select one point and use `Connections ▸ Connect To`: pick the other from the object
field, then press a type button. No two-object selection to wrangle, which is the better path in a
dense network.

| Button | Means |
|---|---|
| **Segment** | the carriageway continues from one into the other |
| **Junction** | both become intersection mouths of one pad |
| **Aux** | mainline → ramp — **directed**, so the source matters (the target must be a `RAMP_ENTRY`/`RAMP_EXIT` point) |

### 3a. Seeing what a point is connected to

The **Connections** panel lists every link on the active point, one row each:

    [type ▾]  demo_main_p004  [X]
              216.0 m -- straight

- the **type** dropdown retypes the link in place;
- the **name** is a button — press it to jump to the other end and walk the graph;
- **X** cuts that one link;
- underneath, the span, and whether that stretch runs **straight** or **bends N°**;
- a **taper too short** warning when the width change is too abrupt for the design speed — the
  same rule the gate uses, so the panel and the gate cannot disagree.

Everything on the row is **derived**. There is no stored "straight or curved" flag to keep in sync;
the geometry already knows.

### 3b. Bending a road

**Select the point and rotate it with `R`. That is the whole gesture.** The point's rotation *is*
the road's direction there, so the road bends to follow it — live in the overlay, before any
rebuild, with no mode to set first. Points are drawn as `ARROWS` so you can see which axis is
which: **local +Y is travel**.

Two things make that work, and both are automatic:

- **A point is born facing its road.** `New Road`, `Extend Road` and `Insert Point` set the
  Empty's rotation to the chain direction, and `Build` re-faces every point the tool still owns.
  So the arrow you are looking at is the direction the solver actually uses — it is never the
  world +Y of a fresh Empty pretending to be a road heading east.
- **A rotation is adopted, a drag is not.** The tool remembers the facing it last gave each point;
  turn the Empty away from that and the point becomes `MANUAL` on the spot, everywhere — overlay,
  gate, build and export all read it through the same function. *Moving* a point changes the chain
  direction without touching the rotation, so a drag is never mistaken for a bend.

`Shape ▸ tangent_mode` shows what happened and lets you take it back: set it to `AUTO` and the
point rejoins the chain (the arrow re-straightens at the next `Follow Road (Auto)` or `Build`).
`Face Road (Manual)` straightens the facing *and* pins the point to `MANUAL` — useful to
re-straighten a bend you no longer want while keeping hand control of it.

- **Straight is detected, never authored.** Two facings that agree with the chord give a dead
  straight run; the Connections row says `straight`.
- **`Leaves` / `Arrives`** are handle lengths in metres (`0` = automatic). They change how *hard*
  the curve leaves and arrives, never which way.
- **If two points cannot express the shape, add a third.** That is the model's answer to a
  compound curve — not a curve-type setting on the link.

`Disconnect` removes a link; the `Author ▸ Connect` buttons grey out until exactly two points are
selected, and the `Connections` ones until you have named a target.

### 4. An intersection

A crossing does **not** split either street. Give each street a point where the stop line should
be — four points for a four-way — select them all, and press `Author ▸ Junction ▸ Make
Intersection`. That writes the full clique and parents every mouth to a `JCT_*` Empty.

- **The points are the stop lines.** Drag one to move that arm's stop line; drag the `JCT_*` parent
  to move the whole junction.
- **Rotate a mouth and the pad turns with it.** A mouth's arm direction is its authored facing
  (`point_model.station_axis`), the same source the carriageway uses — so the cap, the fillets
  either side, that arm's turn paths and its two corner footways all follow the arrow. There is no
  mode to set first and no separate re-solve.
- A pad **always tessellates**: the fan's apex is the ring's kernel point, not the centroid, and a
  ring with no kernel is ear-clipped. Pulling a mouth in too far is a warning about tidiness, not
  a refused build.
- **The pad grows its own kerb and footway.** One run per real corner, on the same corner curve
  the pad boundary is rounded with, built with the two adjoining arms' own footway widths — so
  the pavement wraps the crossing instead of every street's footway stopping dead at its mouth.
  A through-pair contributes none: the road runs straight on and its own edge run owns that
  stretch already.
- Rough placement is fine: `Junction ▸ Auto Setback` solves the whole clique and moves every
  unlocked mouth. Tick **Setback Locked** on a mouth you have placed by hand.
- A through street contributes **two** mouths, and they are joined by the pad, not by carriageway
  — so do **not** put a `SEGMENT` link between them.

### 5. A ramp

1. `New Road` for the ramp, `lanes_bwd = 0`.
2. On the mainline point where the exit lane opens, set `aux_fwd = 1`, and on the point at the
   gore as well — so the lane runs at full width for the deceleration length.
3. Select the ramp's first point, then the **mainline** point **last** so it is active, and press
   `Author ▸ Ramp ▸ Make Ramp`.
4. On the *next* mainline point past the gore, set `aux_fwd` back to `0`.

**The aux BLOCK is the exit lane, and the ramp is its continuation.** `lanes_fwd = 3` with
`aux_fwd = 1` is a **four-lane** carriageway whose outermost lane leaves — the panel and the
overlay both say so (`3+1|3`, and a `carriageway: 4 fwd` read-out), because counting it as three
and treating the ramp as a fifth lane beyond it is the one thing that makes an exit look wrong.

`aux_fwd = 2` is a **two-lane exit**, and the ramp continues **both**: the gore line is the
*innermost* aux slot's inner edge, not the outermost's, so widening the exit widens it outward and
never moves the join. Give the ramp `lanes_fwd = 2` to take the whole block.


`Make Ramp` calls `Align Ramp To Aux`, which does **two** things:

- puts the ramp's mouth on the **gore line** — the aux slot's edge on the through-lane side —
  at the mainline station's own cross-section, so the two bands are cut on the same plane;
- **faces the mouth down the mainline**, and pins it `MANUAL`. A parallel-type exit leaves
  *parallel*; you author the divergence by rotating the ramp's **next** point.

You never author the gore. Build emits it: a paved strip between the mainline's outer edge and the
ramp's inboard edge, running from the theoretical gore (where the two edges actually part) to the
nose (where the gap reaches ~4 m and kerb takes over). It lands in `ROAD_MANAGER_GEN/GORES` with
its own `-noped-colonly` proxy.

**And Build caps the nose.** Past the nose the two roads have parted and each carries its own wall
again — but the V between them belongs to neither: both are silent there for the same correct
reason, that the stretch is the other one's asphalt. So the gore closes it, with a short
`GORE_*__edges_nose` run swept from the ordinary kerb/footway/barrier stack. The cap IS the gore
strip's last pair, flush with the paint, and both flanking walls resume on that same line — three
pieces of wall meeting at a point, with nothing to line up by hand.

You do not author that either, and there is no gore-specific knob for it. **Each end reads what its
own road declares** and the cap blends between them:

| The two roads declare | The nose becomes |
|---|---|
| a barrier on both (highway + ramp) | a wall closing the V, at each road's own height |
| a barrier on one, none on the other | a wall that fades out across the cap, no step |
| footways | a kerbed pedestrian island, walkable proxy |
| nothing (`barrier_height = 0`, no kerb, no footway) | nothing built |

The collision proxy follows the same source: `-noped` unless **both** roads allow pedestrians, so a
gore between an expressway and its ramp never bakes as a navmesh strip in the middle of an exit,
while a gore between two ordinary streets does.

The gate reports both numbers rather than hiding them: the station residual in metres
(`ramp_edge_residual`, an error) and the divergence angle in degrees (`ramp_diverge_angle`, a
warning past 8°). A lane *departing* onto a ramp is exempt from the merge-taper rule — it is
not merging into traffic, so the mainline's edge may come back at gore rates rather than tapering
a lane to nowhere for the next 200 m.

### 6. A highway, and what holds it up

An expressway is an ordinary road with more lanes, a higher `design_speed`, no footways, and
**`ped_access` off** on the **Road** panel (without that, AI walk onto it).

You never author its supports. Give the points a **Z** and Build derives everything from
`delta = surface_z − ground_z`: at grade it cuts the terrain, a little up is an earth embankment
with a real 1:1.5 batter, well up is a deck on piers, down is a trench or a bore. The terrain is
raycast on **every** Build — there is no "sample ground" button to forget.

### 6a. Kerbs, footways and walls

Everything outboard of the asphalt rides the road's **outline**, never its centreline — which is
what makes it open by itself at a gore, a merge or a junction mouth, with no special case anywhere.
Three layers, in order outward:

| Layer | From | Where |
|---|---|---|
| kerb | `left_kerb_height` / `right_kerb_height` | every open stretch |
| footway | `left_walk_width` / `right_walk_width` | wherever the width is non-zero |
| **barrier** | the road's `barrier_height` | **derived** — see below |

**You author how tall a barrier is; Build decides where it stands.** A road with **`ped_access`
off** (an expressway, a ramp) is fenced along its whole length; a road people may walk on is fenced
only where it is genuinely off the ground — a viaduct's parapet — and not where it merely rides
a low kerb. Set `barrier_height = 0` on the **Road** panel for none at all.

Because it rides the outline like the kerb, the wall **opens across a gore and closes again past
the nose**, and runs on into the next segment of the same road without you joining anything up.
That is the same mechanism, not a second one.

What decides it, exactly, is *"does the pavement continue past this line?"* — probed **outboard**
from the edge, not "is there asphalt somewhere within half a metre". The difference shows where a
ramp leaves along the mainline's own outer edge: both edges are the outer boundary of the same
pavement there, and an undirected test had each road suppress the other's parapet, leaving a hole
in the wall at the top of the drop. Directional, the mainline's wall runs up to the mouth and the
ramp's takes over from it.

It asks two things, and either one opens the furniture: *does the pavement continue past this line*
(probed outboard) and *is this line buried under someone else’s pavement*. The second is what stops
a mainline growing a second wall half a metre inside the ramp that has taken over from it — a band
only slightly wider than the probe would otherwise be stepped clean over. An edge sitting exactly
**on** another road’s boundary is the shared outer edge and keeps its wall.

Where a run stops is not rounded to the 4 m sampling either: the end is clipped onto the boundary
it stops against, so a wall ends **at** the mouth it hands over at and starts **at** the gore nose
it has to meet.

One thing the hand-off cannot do is close the **tip** of a gore: there both roads open, correctly,
and the gap is nobody’s — see the nose cap in §5, “A ramp”.

### 6b. Seeing the traffic before Godot does

`Preview ▸ Traffic Flow` draws **the export, not the authoring**: every lane of `.lanekit.json`,
directed, with chevrons and its successor links. Turn on **Cars** and agents walk that graph,
choosing successors by the exported weights.

That is a different object from everything else in the sidebar, and the difference is the point. A
road can be built, gate-green, and still export a lane nothing can reach — which is exactly what
the sample's exit ramp did until this landed. In game it reads only as "that ramp is always
empty".

| Drawn | Means |
|---|---|
| blue | carriageway |
| amber | junction connector |
| green | a ramp, or the lane that hands off to one |
| violet | a merging lane's successor |
| white hairline | a `next` edge, tail to head |
| **red X** | a lane with **no successor** whose tail sits on the head of a lane going the same way — it should have chained and did not |
| **magenta ring** | a lane **nothing leads to** — always flagged for a ramp |

`Flow Report` prints the whole list to the console, naming each lane. A dead end at the edge of the
network is listed separately as an "open end", because it is expected and would otherwise drown
the two lines that matter.


### 7. Build, check, export

`Build ▸ Validate` first — **a build that fails the gate is a failed build**, and every finding
names the object to go and fix. Then `Build Roads`, and `Export .lanekit (v2)` for Godot (it
refuses while the gate is red). `Live Rebuild` re-sweeps a road when its points settle; the overlay
follows the drag either way.

`Save Road Record` writes `<blend>.roads.json` — **that file is the source of truth**, and the
Empties are a view of it. Commit it.

## Six rules that hold the whole thing up

1. **One owner of "where is slot *i*".** `lane_profile.slot_offset()`. No other module computes a
   lateral offset — they ask, or they read the outline.
2. **Authored and generated never share a collection.** A build only ever clears inside
   `ROAD_MANAGER_GEN`. Nothing under `ROAD_MANAGER` is deleted by any build, ever.
3. **The record is the file.** `<stem>.roads.json` is the source of truth; the `.blend` is not.
   Both previous rewrites stored the authored state only in `.blend` IDProperties, so when the
   model changed there was nothing to migrate.
4. **The point IS the stop line.** No hidden setback solve between the artist's Empty and the pad.
   `Auto Setback` writes the points; it does not sit behind them.
5. **A build that fails the gate is a failed build**, and every finding names the **object** to
   fix, because artists fix objects, not indices.
6. **The transform is the road frame — nothing derived is stored.** Position is the station, local
   **+Y** is travel direction, roll is banking, and straightness is *measured*, not flagged. A
   stored "this bit is straight" is one more thing that can disagree with the geometry. The
   corollary the tool owes you: **a point is born facing its road and the arrow is kept honest**,
   because a frame the artist cannot trust is worse than no frame at all.

## The two models this replaced

`legacy_graph/` holds the mesh-graph model (archived, not imported); the per-piece generators were
deleted. See `legacy_graph/README.md` for what was wrong with each, and where the pieces worth
keeping went.
