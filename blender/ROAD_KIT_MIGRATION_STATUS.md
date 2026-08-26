# Road Kit migration — status & continuation plan

Handoff written 2026-08-13. Read `ROAD_KIT_REDESIGN.md` first — it is the design of record and
carries the 13 measured defects that shape all of this. This file is the *working state*: what is
done, how to verify it in one command, and exactly what to do next.

---

## 0. The one-paragraph situation

The road kit is mid-migration from a **sibling-object model** (a piece = a swept Curve plus
Python-owned `curb_*`/`sidewalk_*`/`median_*` mesh objects, lifetimes managed by hand) to a
**modifier-stack model** (a piece = ONE mesh carrier whose whole road is its modifier stack, driven
by a per-station `ProfileSet`). **The switch is flipped** (2026-08-14): every new segment is a
carrier + stack, and the sibling BUILD path is deleted. What remains of the old model is the
*rebuild* path for pieces already authored as Curve spines — see Step 3, which is blocked on Step 7
converting those files.

Running two cross-section models at once was itself a defect source — it produced the
"two-direction carriageway swept entirely onto one side of its spine" bug (the profile owned the
width, the scalars owned the left/right ratio), and the single-vs-double centreline that changed
the first time a road was dragged. Both are fixed.

The known-bad ramp geometry in §5 is still deliberately left alone.

---

## 1. Verify the current state (run these first)

```bash
cd blender

# 1. addon suite — expect PASS=60 FAIL=0. USE THE SCRIPT, not a hand-written loop:
#    `--python-exit-code` must come BEFORE `--python` or it never fires and every test
#    "passes" (see §6). The loop that used to be printed here did exactly that.
tools/run_smoketests.sh                 # all; add name filters to narrow: `… median curb`

# 2. pure-python self-tests — all print ALL SELF-TESTS PASSED
python3 lib/lane_profile.py && python3 lib/intersection_kit.py && \
  python3 lib/lane_kit.py && python3 lib/lane_joints.py

# 3. rebuild the island road network (~2 min)
blender --background --python tools/island_v3_to_roadkit.py -- \
  --build --splits --intersections --support --out island_v3_roads_test.blend

# 4. export the sidecar, then run THE GATE — expect exactly 1 failure (see §3)
cd ..
blender assets/world_source/island_v3_roads_test.blend --background \
  --python blender/tools/save_lane_kit.py
python3 blender/tools/check_road_network.py \
  assets/world_source/island_v3_roads_test.lanekit.json
```

`assets/world_source/island_v3_roads.blend` (the real one) is **untouched**. Everything so far is in
`island_v3_roads_test.blend`. Nothing done in this migration is destructive yet.

---

## 2. What is done

- **`lib/lane_profile.py`** — Slot / Profile / ProfileSet, stable slot ids, `slot_offset` as the
  single owner of lateral position, `lane_runs`, `lane_neighbors`, `marking_runs`. Self-tested.
- **`lib/road_stack.py` + `addons/road_kit_authoring/segment_stack.py`** — the layer stack, plus
  curb/sidewalk/median profile-object builders.
- **The stack is a working build path.** Verified on a full T2 street:
  carrier `MESH`, layers `[Spine, Pavement, CurbL, CurbR, Median, SidewalkL, SidewalkR, Finish]`,
  242v/210p, lateral −12.12..12.12 (= 1.5 + 6.5 + 0.125 + 2.0, exact), **zero sibling objects**.
- **Two-direction carriageway** (`ops_split.two_way_carriageway_*`) — ONE piece carrying
  `[REV aux+gore][R1 R0][MED][F0 F1][FWD gore+aux]`. `LOOP_A`/`LOOP_B` retired. Built:
  `LOOP_carriageway_001`, 3275.7 m, 313 pts, 42 stations, 21 slots, support sharing the spine.
- **Ramps are two pieces with an uncut mainline**, seeded by *transforming* the authored alignment
  (`ops_split.seed_ramp`), never rebuilding it.
- **Connectivity is authored, not inferred** — `lane_export._carriageway_links` emits EXIT/ENTRY
  refs; `lane_kit.combine_pieces` resolves them. Gate reports all 8 ramp lanes reachable.
- **`tools/check_road_network.py` is a truthful standing gate** (§3).
- **Connection preview** — "Preview Lane Curves" also draws the resolved movement graph as
  `link_<KIND>_<src>__<dst>` tubes, so flow direction at a junction is visible.

---

## 3. The gate, and its one remaining failure

`tools/check_road_network.py` is the standing connectivity gate. **A build that fails it is a failed
build.** Current output ends:

```
4. ramps usable from their carriageway:
     LOOP   OK  all 8 ramp lane(s) reachable (6 exit / 2 entry)
5. LOOP   OK  reaches 239 lane(s) outside itself
FAIL: 709 drivable lane(s) unreachable by authored data alone
network gate FAILED (1 problem(s))
```

**Step 4 is done, and re-exporting moved this failure rather than fixing it — for a reason worth
recording.** Links are now emitted for both joint shapes (segment↔segment `THROUGH`, segment↔arm
with the junction fan) and every link is checked **edge-to-edge** rather than for proximity
(check `2b`), plus an authored joint that no lane crosses is reported (`2c`). The re-exported
sidecar reads:

```
lanes: 739
2. authored graph: 26 successor link(s), 40 lane(s) with lane-change adjacency
   691 drivable lane(s) with NO authored edge in or out
2b. 11 link(s) are not edge-aligned      (gores 3.6-4.7m out; one trunk pair DISJOINT by 18.2m)
2c. authored joints all crossed by a lane        OK (0 joint(s))
```

The island file contains **zero authored joints** (`rka_linked_to` markers: 0, across 124 pieces).
Its 691 orphans were never a link-emission gap: that file's connectivity was **never authored**,
only placed adjacent and left to the runtime's proximity guess. No amount of emission quality
changes a file that claims nothing — **Step 5's regeneration has to author the joints**. Check `2c`
reporting `OK (0 joints)` is the honest answer, not a pass to lean on.

Check `2b` did become measurable, and immediately named 11 real defects in the interchange group
refs that were invisible before (see Step 4). Before the re-export it reported `(0 of 8 measurable)`
— a check that quietly measures nothing is exactly the failure mode this gate exists to prevent, so
it said so out loud rather than passing.

---

## 4. Continuation plan, in order

### Step 1 — Port the sibling-object smoketests to invariants  ✅ DONE (2026-08-13)

The tests no longer name a segment's generated sibling objects; they assert properties of the road,
per `ROAD_KIT_REDESIGN.md` §7. **Suite: PASS=58 FAIL=0, run twice, on a runner that can actually
fail** (it could not before — see §6).

- **`lib/piece_probe.py`** (new) is the measurement vocabulary: it reads a piece's EVALUATED
  geometry and reports it against the piece's own spine as `(s, lat, dz)` — distance along, signed
  lateral offset, height above. `raised_span` / `raised_gaps` / `raised_centroid` /
  `clusters_along` / `span` / `length` / `geometry_summary`. It is carrier-agnostic by
  construction, so the same assertion holds for a curb that is a sibling Curve and a curb that is a
  `CurbL` modifier.
- **Ported:** `boundary_sweep` (median removal now asserts the carriageway gap CLOSES by exactly
  the median width; curb NONE→PROFILE→NONE asserts raised geometry appears at the paved edge and
  leaves, and that re-applying does not stack a second copy — the invariant form of "no `.001`
  duplicate"), `gn_boundary_persist` (segment half: carrier identity + curb carried outward by two
  lane widths), `collision` (segment/transition: proxies must COVER the piece's span and taper with
  it, not number 3), `asset_curb_sidewalk_gap` (the raised surface must run unbroken outward — a
  stronger statement than the old two-object subtraction), `curb_style_panel`, `asset_default_fill`,
  `move_segment`, `sidewalk_props_panel`, `transition_and_spine`, `matkey_panel`.
- **`smoketest_rebuild_guard` needed no change** — it already asserted invariants
  (`live_edit._pending_*` empty), never object names.
- **Deliberately left on object names:** `legacy_segment_persist` (its whole subject is that legacy
  sibling pieces keep working), everything asserting an INTERSECTION's pad/corner-curb objects
  (real objects on every path), and the median-object tests `median_single` / `median_chain_merge` /
  `turn_lane_widen` — those belong with `median_merge.py` in Step 2.
- **Found and fixed en route:** 4 smoketests that had been failing invisibly, and a
  build-vs-rebuild divergence in lane markings (see below).

Modules that still reach into sibling objects directly, and move in Step 2:

```
median_merge.py   live_edit.py   ops_segment.py   ops_intersection.py
```

**Known divergence surfaced by this work — FIXED in Step 2:** a fresh build gave a 2+1 road a
single solid yellow centreline; a *rebuild* of the same piece gave it a DOUBLE yellow.
`_populate_lane_markings` branches on `profile_set` — absent on the fresh build (markings from
`intersection_kit.build_segment_lane_markings`), present on the rebuild (markings from
`_profile_lane_markings`, where `DOUBLE_Y` is two ribbons). That is defect 1 again, two owners of
one cross-section question, and the fix is the ProfileSet becoming the only owner — not teaching
one path to imitate the other. `smoketest_markings` documents it and asserts non-accumulation
instead of a literal count.

### Step 2 — Move `live_edit` / `median_merge` / intersection joints onto the carrier  ✅ DONE (2026-08-14)

**Suite: PASS=59 FAIL=0 with the stack as the build path.** The joints — the part flagged as
delicate — needed no new machinery: `spine_io` already adapted the point maths, and once ports
existed everything from `joint_sync` to `median_chain_merge` passed unchanged.

What was actually broken, and is now fixed:

- **Every cross-section edit was a silent no-op on a stack piece.** `rebuild_segment_gn_in_place`
  opened with `if spine_obj.type != 'CURVE': return`, so add-a-lane / taper / median / sidewalk
  wrote their custom property, reported `{'FINISHED'}` and changed nothing. It hid well because
  *dragging* the spine always worked — the stack is driven off the carrier's own vertices, so a
  drag needs no Python at all.
- **`apply_segment_stack` is now the single owner** of "what layers does this piece have", called
  by both the build and every rebuild. A build path and a rebuild path deriving the cross-section
  separately is defect 1, and it had already bitten twice in this file.
- **Tapers reached the stack.** It read only the START scalars, so a piece asked for 2→4 lanes came
  out constant-width. `segment_profile_set` emits a second station whenever any `_end` scalar
  differs — `interpolate()` doing what §2.1 said it would.
- **Ports.** `_place_segment_ports` only ever ran inside `_populate_segment_mesh_gn`, so a stack
  piece had no `port_A`/`port_B` and was **unlinkable** — this alone was 8 of the failures.
- **`_refresh_pavement_radius`** had a fifth, unguarded caller (`live_edit._sync_linked_width`);
  it now no-ops on a stack carrier, where `rka_halfw` carries that quantity instead.
- **`median_merge`** suppressed a member's own median by deleting an object; on a stack piece the
  median is a `Median` layer, so a chain drew the merged row on top of every member's still-live
  median. It now removes the layer.
- **`bake_colonly_proxies`** only looked at Curves, so a stack piece got no collision at all. It
  now emits one `pave_<piece>` proxy covering the whole carrier.
- **`spine_io` was not the drop-in it claimed.** `.co` returned a tuple (so `.x` raised) and then a
  fresh `Vector` (so `pt.co.x += 5` silently wrote to a temporary). It is now a write-through
  4-component proxy.
- **The build↔rebuild marking divergence from Step 1 is fixed at the root.** `read_profile`
  *synthesizes* a ProfileSet from the scalars, so every rebuild took the profile path while the
  build took the scalar one. The build now uses the same ProfileSet the piece was built from.
- **A yellow centreline was painted through the median.** `profile_from_scalars` gave the MEDIAN
  slot `MARK_SOLID_Y`; a median with real width *is* the separator, so it is `MARK_NONE` now —
  the profile model reintroducing a bug the scalar path had already fixed.

New standing test: **`smoketest_stack_live_edit`** — drag, add a lane, taper an end, widen the
median, grow a sidewalk, all asserted through `piece_probe`, with the carrier surviving by identity
and owning zero sibling objects throughout.

### Step 3 — Flip the default and delete the old path  ◐ BUILD PATH DELETED, REBUILD PATH BLOCKED ON STEP 7

**`use_stack=True` is now the default** (2026-08-14). It was flipped as part of finishing Step 2
because the alternative was leaving the suite red: with the sibling path selected, two tests fail
on **defects the sibling path has and the stack path does not**, and both were invisible until
Step 1's assertions got stronger:

- `markings` — a fresh build draws a single solid yellow centreline and the very first rebuild
  replaces it with a double yellow (defect 1: two derivations of one cross-section).
- `turn_lane_widen` — a piece authored `median_width 6.0 → 2.0` measures −13.000 at the start and
  −13.500 at the end. The declared median taper never reaches the geometry at all, and it narrows
  in the wrong direction.

Fixing those in code that is scheduled for deletion is wasted work, so the flip came first. Both
paths were measured before flipping: **stack 59/59, siblings 57/59.**

**Done (2026-08-14):** the `use_stack` parameter is gone, the sibling BUILD branch is deleted --
every new segment is a carrier + stack -- and `lane_profile.scalars_from_profile` (the migration
bridge) is removed.

**Blocked, and the plan had the order wrong.** The rest of the deletion list
(`_populate_segment_mesh_gn`, `clear_generated_mesh_objects`, `_rka_touched`,
`sweep_untouched_boundaries`) is still reachable from `rebuild_segment_gn_in_place`'s **legacy
carrier branch**, which rebuilds pieces whose spine is still a POLY Curve. Every segment already
authored in `island_v3_roads.blend`, `world_session.blend` and `District_industry_5_1`'s `MANUAL`
collection is one of those, so deleting it makes all of them uneditable. **Step 7 must run before
the rest of Step 3.** The branch is marked in the source with the same note. (Some of those
functions are also still used by intersections, transitions and marking objects, which are not
part of this migration at all -- they do not go away with the carrier.)

The remaining deletion list, for after Step 7:

```
_populate_segment_mesh_gn          clear_generated_mesh_objects
_rka_touched tagging               sweep_untouched_boundaries
rebuild_segment_gn_in_place's object reconciliation
the scalar _end twins              scalars_from_profile (migration bridge)
```

### Step 4 — Close the gate: segment↔segment and segment↔intersection links

See §3. After this the gate should pass, and the network is fully authored rather than
proximity-guessed.

#### Edge-to-edge alignment  ✅ DONE (2026-08-14)

**Touching is not connecting**, and it is now measured rather than eyeballed. A link is a promise
that a car can cross the seam; two lanes whose centrelines coincide *to the millimetre* can still
be a full lane width apart at their edges. `lib/lane_joints.py` (pure Python, self-tested) tests
the thing the promise is about -- the lane's ribbon EDGES, left on left and right on right -- which
is deliberately **one** check rather than three, because it subsumes all of them:

| what is wrong | how the edge test sees it |
|---|---|
| centrelines offset | both edges move together — a 2 cm offset reads as 0.020 m |
| widths differ | each edge out by half the difference, with the centres exactly coincident |
| heading break | edges splay apart; a 30° kink on a 3.5 m lane reads as 0.906 m |
| head-on pairing | left meets right — a full lane width, with the centres exactly coincident |

`MISALIGNED` (the seam is sloppy) and `DISJOINT` (the link names the wrong lanes) are reported
separately, because they want different fixes. A lane with no width is `UNMEASURABLE`, never
assumed-aligned.

Three consumers, one implementation:

- **`tools/check_road_network.py`** — check 2b, on the exported sidecar. A build whose links are
  not edge-aligned is a failed build.
- **`Check Joint Alignment`** (`ops_joint_check.py`, panel button) — the same numbers on the live
  scene, worst seam first, in metres, selecting the offending piece. Authoring-time, while there
  is still something to drag.
- **`smoketest_joint_links.py`** / **`smoketest_junction_links.py`** — standing tests that an
  authored joint yields real per-lane links (segment↔segment, and segment↔intersection with its
  fan), that nudging a joined piece 0.4 m sideways is *visible* (a proximity join accepts it
  silently), and that a seam broken past the point where links form is still reported.

Lanes now export `width_start`/`width_end` so edges are **derived**, not stored: a stored edge can
drift out of agreement with the centreline it belongs to, and the sidecar does not grow by two
polylines per lane.

#### Links: authored pieces, measured lanes  ✅ DONE (2026-08-14)

`lane_export.emit_joint_links` turns each authored piece-to-piece link into real per-lane
connections. The split is the point:

> **Which two pieces connect is AUTHORED** — the user said so by linking a port. **Which lane
> continues into which is MEASURED** — `lane_joints.pair_lanes` pairs the ribbons that actually
> meet edge-to-edge.

Deriving the pairing instead (same slot id, unless the pieces meet end-to-end, in which case the
frames mirror and forward pairs with reverse and the slot order flips) is correct reasoning and
four chances to get a sign wrong in a case nobody tests. Measuring asks the question the connection
is about, and a mirrored joint needs no special case.

**This is also the ramp answer, with no ramp rule.** A ramp pairs with the auxiliary lane when one
was opened for the exit and with the outermost lane when none was — because those are the edges it
meets. And a ramp that *kinks* off the mainline instead of departing tangentially pairs with
nothing, so the known bad-gore-angle defect (§5) surfaces as a missing link rather than as a link
that lies about the geometry.

Verified: two segments joined by `Extend From Port` produce **4 per-lane links (2 each way), 0
misalignments**, each naming one specific target lane, typed `THROUGH`.

##### A junction FANS — the one place the segment rule is wrong

A junction is a different *shape* of joint, not a bigger one, and this is the trap the intersection
half turned on. Between two segments a lane continues into exactly one lane, so pairing is
one-to-one and a tie means one of the candidates is wrong. At a junction the approach lane feeds
**every** movement that starts on it — left, straight and right all begin on that same ribbon at the
same stop line, so all three are exactly, equally aligned and *a tie is the correct answer*. Run the
segment rule there and the closest movement wins: **a junction cars can only drive straight
through**, built out of geometry that is perfectly correct and impossible to spot in the viewport.

So `pair_lanes` takes `exclusive`, and `_pair_across` sets it from the joint (`lane_joints`'s
measurement is identical either way — only which lanes may fan differs). Same on the way out: every
movement arriving at a departure arm hands over to the single lane leaving on the road.

A movement's `kind` comes from **the movement's own `turn`** (`intersection_kit` already decides
L/S/R from the two arm angles), not from "a junction is involved" — which would label a straight
crossing as a `TURN` and make the runtime's straight-bias weighting meaningless at exactly the
junctions that have one. A lane *leaving* a junction is a plain continuation: the turn already
happened.

Verified (`smoketest_junction_links.py`): a road extended off a 4-way arm produces **6 edge-aligned
connections** — the approach lane reaching all three movements (L/S/R, kinds `TURN`/`THROUGH`/`TURN`)
and all three movements handing back out onto the road's single departure lane.

##### `UNJOINED` — the failure that hides behind the fix

Breaking a seam badly enough makes the links **stop forming**, so a checker that only measures links
goes quiet and the file reads as clean. That is a worse failure than the one it replaced. An
authored joint that no lane crosses is invisible in the lane data — indistinguishable from two
pieces that were never linked — so only the authored side can tell the difference:
`lane_export.authored_joints` / `unjoined_joints`, reported as `lane_joints.unjoined`. Live in the
`Check Joint Alignment` button (ranked above any merely-bad gap), written into the sidecar as
`joints` by `save_lane_kit.py`, and checked as **2c** by `check_road_network.py` so CI can make the
call with no Blender. Confirmed by test: widening a junction's lanes 1 m kills every link across the
seam and is reported as `UNJOINED` rather than as a clean scene.

##### What re-exporting the island revealed

`island_v3_roads.lanekit.json` re-exported (739 lanes, 124 pieces). Two findings, neither fixable in
Step 4:

- **The island has ZERO authored joints** — `rka_linked_to` markers: 0, across all 124 pieces. Its
  691 orphan lanes are therefore *not* a link-emission gap; that file's connectivity was **never
  authored at all**, only placed adjacent and left to runtime proximity. Step 5's regeneration has
  to author the joints, or the file keeps relying on the proximity guess no matter how good the
  emission is. (Check 2c says `OK (0 joints)` — truthfully: nothing was claimed, so nothing is
  broken.)
- **Check 2b went from unmeasurable to loud.** With widths now exported it immediately named 11
  real defects in the existing interchange group refs: the gores are **3.6–4.7 m out at the edges**
  (the known §5 bad-gore-angle defect, now in metres), and one trunk pair is **18.2 m apart** —
  `DISJOINT`, i.e. that link names the wrong lanes.

**A ramp link names a LANE, not a piece** (requirement added 2026-08-14). `Connection` already
carries `from_slot`/`to_slot`; these are the cases that have to fill them in honestly:

| Case | Mainline side of the link |
|---|---|
| ramp ↔ segment, aux lane present | the AUX slot opened for that enter/exit — the ramp's own lane continues into it |
| ramp ↔ segment, no aux lane | the **outermost** lane on the exit side (curb side on keep-left), or the innermost, depending on the direction the ramp leaves/joins — chosen explicitly and recorded, never inferred downstream |
| ramp ↔ intersection | an intersection opening may expose a **single** lane output; the ramp links to that one lane |

The rule that makes this tractable is already in the model: `slot_offset` owns lateral position and
slot ids are stable, so "which lane" is a slot id, and the same statement serves the exported graph,
the gate, and Step 7's per-slot ports. Nothing here needs a new concept — only that EXIT/ENTRY stop
being piece-to-piece and start being slot-to-slot.

### Step 5 — Regenerate for real  ◐ REDRAWN FROM THE 2D PLAN (2026-08-15)

`island_v3_roads.blend` has been rebuilt from the plan by `island_v3_to_roadkit.py`. The previous
file is kept as `island_v3_roads.pre_regen.blend` (**it was untracked in git — the only copy**).
`island_v3_assemble.py` for the combined view is still to do.

| | before | after |
|---|---|---|
| segment model | 102 legacy Curve spines, **0** stack carriers | **76 stack carriers, 0 Curve spines** |
| authored joints (`rka_linked_to`) | **0** | **98**, every one measuring 0.00 m |
| segment ports landing on an arm tip | **0** of 204 | **77** |
| successor links in the sidecar | 26 | **637** |
| orphan lanes | 691 | **128** |
| movement kinds | THROUGH only | THROUGH 406, **TURN 223**, EXIT 6, ENTRY 2 |

Because the segment builder now only builds stack carriers, this regeneration **also completed
Step 7 for this file** — there is no mixed profile/mesh content left in it.

#### Four defects found and fixed, all in the generator or the overlay

1. **`use_stack=True` was still being passed** to `_build_segment_from_points` after Step 3 removed
   the argument, so `--splits` raised — and **Blender exited 0 anyway** because the invocation
   omitted `--python-exit-code` (§6's trap, hit again from outside the test runner). No file was
   ever written; the run just looked like it worked.

2. **Chunks were never trimmed back to the junction.** A road was cut *at* each crossing and the
   intersection was then built *centred* on that same crossing with arms reaching `tail_length`
   (14–31 m, auto-grown) outward — so every chunk ran through the pad and out past its own arm.
   The road was authored twice over every junction, and *zero* of 204 ports were within 5 m of any
   of the 83 arm tips. That is why the file had no joints: there was no seam to author, only an
   overlap. Fixed by ordering (intersections first — an arm's tail length is not knowable until it
   exists) plus `trim_chunk_to_arms`.

3. **Arms had no median while the roads did.** T2 carries a 3 m median; the arms came out flush, so
   at a seam whose ports coincided *to the millimetre* not one lane lined up — the textbook
   "touching is not connecting" case. Each arm now takes its road's own `rka_arm_median_width`.

4. **`stamp_joint` on the piece could only hold one link.** `ops_segment._stamp_link` writes
   `rka_linked_to` on the *origin* marker, which is right for "this piece was extended from there"
   but cannot express a chunk meeting a different junction at each end: 153 stamps collapsed to 69.
   Now stamped on `port_A`/`port_B`, which `_is_link_dependent_marker` already supports.
   (Also: port positions are read from the **spine**, not the port Empty — the Empty is not placed
   yet during a batch build, and reading it welded 15 interchange ramp ports to each other at
   distances up to 1340 m.)

#### The measurement was running in the wrong plane — Step 4 correction

`emit_joint_links` runs inside `collect_pieces`, which the **real export** calls with
`godot_space=True`. A `.lanekit.json` is written `(x, height, -northing)`, so `lane_joints` — which
read `p[0], p[1]` — was measuring **x against elevation** on the export path. On flat road that
collapses both lane edges onto the centreline, so nothing is ever far from anything: it pairs lanes
that do not touch, refuses lanes that do, and every number it prints is plausible. The in-Blender
preview path (`godot_space=False`) was correct, which is why all 61 smoketests passed over it.

Ground-plane axes are now an explicit parameter (`BLENDER_AXES` / `GODOT_AXES`) threaded through
`lane_edges` / `joint_alignment` / `check_links` / `pair_lanes`, and each caller states its frame.
**This invalidates the gore figures reported for Step 4** (“3.6–4.7 m out”, “18.2 m DISJOINT”) —
those were measured in the wrong plane. The current honest count is **8 misaligned links**.

#### The overlay was dead, and it was one piece that killed it

`traffic_viz` took each segment's direction from its two-endpoint **chord**. `SegmentCurve_062` is
a descending hairpin (22 points, start and end at one XY, z 12→4), so that chord has zero length and
`vnorm` raised — and since `_gather` builds the whole overlay in one pass, that single piece produced
**zero gizmos for all 126 pieces**. That is the reported "lost the ability to show in/out at each
port". The chord was also just the wrong quantity: on a Catmull-Rom-resampled road it can be tens of
degrees from the road's actual direction where the arrow is drawn. Now per-end tangents from the last
two *distinct* points, with a degenerate piece skipping itself. Pinned by
`smoketest_viz_degenerate.py`. The regenerated file draws **1248** gizmos.

#### Check 6 — is the lane actually DRIVABLE at its speed? (2026-08-15)

`lib/road_geometry.py` (pure Python, self-tested) answers grade, curvature and superelevation from
the one AASHTO equation `e + f = V²/(127 R)`, and check 6 runs it **per lane** — the same points
`Preview Lane Curves` draws as `lanepreview_<piece>_<slot>`, not the piece centreline, because a car
drives a lane and on a curve the inner lane is tighter than the centreline it was offset from.

Three verdicts, kept apart because they have three different fixes:

| | meaning | fix | fails the build? |
|---|---|---|---|
| `GRADE` | too steep over a real distance | the climb needs more length | no |
| `SUPERELEV` | needs more bank than the 6% norm | bank it — it is achievable | no |
| `RADIUS` | needs more bank than the 10% ceiling | open the curve, or sign it slower | **yes** |

`RADIUS` alone is fatal because it is the one no amount of banking rescues. The report says what
radius *would* work and what speed the curve honestly carries, so it leads somewhere:

```
IC_RINKAI_E_ramp_001_A0: RADIUS -- R=25 m needs 42% bank at 45 km/h -- past the 10% ceiling,
  so NO amount of banking fixes it. Either open the curve to R>=59 m or sign it at 32 km/h
```

Design speed is authored (`rka_design_speed` on the piece, carried to every lane by
`collect_pieces`); a sidecar without it makes check 6 **skip and say so** rather than invent a speed.

**Two measurement traps, both hit and both fixed** — a checked number that is wrong is worse than no
check:

- **Grade is measured over a 20 m window, not per span.** A polyline draped on terrain wobbles; one
  12 m span read 10% on a road that climbs 0.2 m end to end.
- **Curvature is measured over a 25 m arc window, never between adjacent points.** The
  adjacent-triple Menger radius measures the *sampling*, not the curve — this project had already
  learned that (`island_v3_plan.min_radius_windowed`: one 140 m arc reads 140.9 / 77.1 / 38.8 at
  20 / 12 / 6 m resample) and `road_geometry` shipped with the bug anyway. Its first run "found"
  **R = 3 m kinks in an 80 km/h expressway** — two nearly-coincident points at a ramp taper, nothing
  on the ground. Corrected count: RADIUS 36 → **22**.

**`TIERS` min_radius is now derived, not asserted.** The table claimed its radii were "a DESIGN-SPEED
figure, 6% superelevation at the tier's speed" and every one of them was more permissive than that:
T3 declared 25 m at 40 km/h where the equation gives 43 m, RAMP 30 m at 40, T2 60 m at 50 (needs 79),
T1 140 m at 80 (needs 252). So `tight=0` on a full run meant nothing. Now computed from `speed`.
`TOUGE` keeps its deliberate 11 m hairpin override — that IS the design.

**Ramps are now 45 km/h** (`RAMP` tier), i.e. a 59 m minimum radius, nearly double what the tier
used to claim.

#### What the gate still fails on, honestly

```
FAIL: 140 drivable lane(s) unreachable by authored data alone
FAIL: 8 link(s) are not edge-aligned
FAIL: 28 authored joint(s) have NO lane crossing them
FAIL: 22 lane(s) are too tight to bank into compliance at their design speed
```

Concentrated in the **interchange** pieces (`build_carriageways`), which chunk trimming does not
touch — the §5 ramp-geometry defect, Step 6's job. Now quantified rather than described: the
expressway mainline pinches to **R = 108–113 m at every interchange** where an 80 km/h road needs
252 m, and `IC_RINKAI_E_ramp_001` runs at **R = 25 m** against the 59 m a 45 km/h ramp needs.

Two entries are worth a design decision rather than a fix: `SegmentCurve_055`/`_056` are **touge
hairpins** at R = 14–15 m, reported against a tier declaring 30 km/h. The check is right — a 14 m
hairpin is honestly a 26 km/h corner — so either the tier's speed or the check's verdict is the
thing to change, and that is the author's call, not the tool's.

#### Arm bearings: fixed at source, after two dead ends

`arms_at` bearinged each arm from a **30 m chord** out of the junction centre, but the arm cap is
built at the **tail** distance (~18 m) and the segment leaves along the road's tangent *there*. On a
curving approach the two disagree by the curvature between them. On `Intersection_NWAY_013` — the
file's own reference junction — all four arm tips sat on their segment's first spine point to
**0.0000 m** and `SegmentCurve_004` still left at 247.32° against an arm facing 256.22°: an **8.9°
heading break** worth 0.5 m of edge gap on a 3.25 m lane, invisible unless measured. `reach` now
matches the tail. NWAY_013 is clean; the worst remaining break is ~11° where the tail auto-grew past
the nominal.

Two post-hoc corrections were tried first and both are dead ends worth recording:
writing `rka_arm_angles` directly is **silently undone** by the rebuild that is supposed to apply it
(it re-derives the angle from the marker), and `rka.aim_arm_at` — the operator built for exactly
this — **core-dumps under `--background`** (an unengaged `PointerRNA`; it needs UI context).
Interactively it remains the right tool for a one-off manual fit.

Also fixed in trimming: a chunk could bind to the arm on the **far side** of a junction it ran
through (distance alone cannot say which side), producing exact 180° heading breaks and one arm
claimed by three segments at once. Arms are now side-checked and claimed once each.

#### The expressway serves each interchange in ONE direction only (2026-08-15)

Reported as "the expressway is only one way traffic". The deck itself is **not** one-way — it
exports four travel lanes, `R1 R0 F0 F1`, a genuine 2+2. What is one-way is the **interchanges**:

| ramp aux lane attaches to | interchanges |
|---|---|
| `F1` (forward, outermost) | IC_CHUO, IC_CHUO_EN, IC_YAMATE, IC_PORT, JCT_AIRPORT |
| `R1` (reverse, outermost) | IC_RINKAI_E, IC_RINKAI_W |
| another **aux** lane (defect) | IC_RINKAI_E_EN → `IC_RINKAI_E_A0` |

So **no interchange has a pair on the other side**: you can leave the ring at Chuo going forward
and there is no matching exit — or re-entry — going the other way. Driving it, most exits only work
in one direction, which is exactly what it feels like.

The cause is a design that half-collapsed. The `T1C` tier still documents the intent — "TWO one-way
carriageways, not one two-way road", emitted as `LOOP_A`/`LOOP_B`, every interchange exiting A and a
"pair" also entering B. But `collect_roads` does `add("LOOP", "T1", ...)` — **one** ring on the
two-way `T1` tier — and `build_carriageways` does `plan = {"LOOP": ics}` with `cwA = cwB =
roads["LOOP"]["pts"]`. `interchange_side(rid)` survived as the A/B selector, so it now silently means
"which EDGE of the single two-way deck this aux lane opens on" — forward or reverse — and nothing
ever pairs them.

**This is a design decision, not a bug to quietly pick a side on.** Two coherent answers:
restore two one-way carriageways (`LOOP_A`/`LOOP_B` on `T1C`, which the code already half-describes),
or keep the 2+2 deck and give every interchange a mirrored ramp pair. They differ in width, in
interchange count, and in how the ring reads from the ground. Left for the author.

Separately, `IC_RINKAI_E_EN_A0`'s inner neighbour is `IC_RINKAI_E_A0` — an **entry ramp feeding an
exit ramp's auxiliary lane** rather than a travel lane. That one is a defect either way.

#### Ramps had no panel at all

Reported as "from panel, seem not able to control how the exit ramp is created". Correct, and the
cause is narrower than it looks: `rka.build_line_split` and `rka.build_line_merge` have been
registered since `ops_split.py` landed and were reachable **only from F3 operator search** — never
drawn in the panel. So were their four shaping dials: `Trunk Lanes` (one below the branch total is
what tapers the auxiliary lane in — *that* is the off-ramp), `Auxiliary Length`, `Taper Length` and
`Gore Nose`. The operators were never missing; the buttons were. Added under **Ramps: Split /
Merge**, enabled once three curves are selected.

**"Rebuild From Handles resets it back to a segment" does NOT reproduce.** Measured on the
carriageway and on two ramp pieces, before and after `_rebuild_piece_in_place` (which is literally
all that operator calls): profile present, **42 stations / 21 slots / 8 aux lanes unchanged**, and
the evaluated mesh identical to the vertex — 624 verts, 13.95 m half-width, 3252 m long.

What is true, and is probably what was seen: **a ramp piece genuinely IS a plain one-lane road.**
`IC_CHUO_ramp_001` is one station, one slot, `A0`, no aux, no gore. All the ramp *shape* — the
auxiliary lane opening, the taper, the gore — lives on the **carriageway's** profile
(`IC_CHUO_A0`, `IC_CHUO_GORE`), not on the ramp. Select a ramp and rebuild it and you correctly get
a plain segment back, because that is what that piece is. Editing the ramp's shape means editing the
mainline it leaves, which is the un-built half of Step 6.

#### Seed curves are dropped

`rc_*` polylines are sampled **once** to seed each piece's spine and never referred to again, so
keeping them left a second, dead copy of every road that looks like road, exports nothing, and is the
obvious thing to grab by mistake. 67 removed per build; `--keep-seed-curves` retains them for
debugging the smoothing/splitting passes.

### Step 6 — *Only now* fix ramp geometry  ◐ THE PIPELINE IS FIXED; FOUR RAMPS NEED AUTHORING

See §5 for the first four defects. Three more were found on 2026-08-15, each by measuring the
polyline at a stage boundary rather than by reading the code — the plan, the seed, and the
landing were each quietly reshaping what the previous stage had proved.

**1. `ops_split.seed_ramp` was shearing the ramp, not moving it.** The gore seed sits on the
carriageway's auxiliary-lane slot, ~10.6 m off the alignment the ramp was authored on, and the
shift used to decay *linearly across the whole length*. A weight that varies along the curve is a
**shear**, and a shear across a curving path rescales its radius — the exact thing the function's
own docstring claimed to preserve. Measured against `road_geometry.min_radius_along`, at a 15 m
seed offset:

| ramp | authored | linear decay | rigid + bounded release |
|---|---|---|---|
| IC_RINKAI_W | 74.2 m | **27.5 m** | 74.2 m |
| IC_PORT | 48.4 m | **23.5 m** | 48.4 m |
| IC_RINKAI_E | 61.7 m | **39.9 m** | 76.7 m |

At a 22 m offset it took IC_PORT to 18.1 m. It is now a **rigid translation**, released by a
smoothstep in the run-out (`RAMP_SEED_BLEND`, 150 m) and kept clear of the touchdown
(`RAMP_SEED_TAIL_CLEAR`, 120 m) so it does not stack with the landing correction — two smoothsteps
in one 120 m stretch cost IC_RINKAI_E 14 m of radius on their own. Guarded by
`smoketest_ramp_seed_radius.py`.

**2. `land_ramp_on_kerb` was inventing junctions.** It snapped a ramp's touchdown to the nearest
arterial with no distance check. `JCT_AIRPORT` is an expressway-to-expressway ramp with no
arterial to land on: its touchdown sat 32.8 m from the nearest street and was dragged 26.4 m onto
it, taking the ramp from **120.9 m to 62.7 m**. `MAX_LANDING_SNAP` (20 m) now leaves such a ramp
on its authored alignment and says so; `JCT_AIRPORT` is back to 120.9 m exactly.

**3. `IC_YAMATE`'s gore was not on the expressway** — 30.4 m off the LOOP polyline, the only one
of six. Everything downstream inherited it: `seed_ramp` then had to slide the ramp **46.8 m** onto
its slot against 10.6 m for every well-placed interchange. `island_v3_plan.gore_on_loop` now
projects an authored gore onto the mainline (a gore is where a ramp *leaves* the mainline, so it
is on it by definition) and prints the distance when it is more than authoring slack.

#### The finding that mattered most: a windowed radius cannot see a hairpin

`min_radius_along` samples two points a fixed **arc length** either side of each point, which is
what makes it immune to sampling density (§5 defect 2) — and at a **hairpin** that same property
is a blind spot. 25 m of arc back and 25 m forward land on the two *legs* of the U, metres apart
in space, and the circle through three nearly-collinear points is enormous. A built ramp spine
that visibly doubles back — `(151.2, 499.7) → (145.3, 505.2) → (148.5, 502.2)` — measured
**70.2 m**, comfortably inside the 59.1 m minimum.

`fit_ramp` optimises against that measure, so it had been **buying its radius by folding the ramp
back on itself**: IC_RINKAI_E's "61.7 m on a 300 m parallel run" and IC_RINKAI_W's "74.2 m on
320 m" were both U-turns. Those numbers were real arithmetic on a shape no car can drive, and they
were reported as successes here on 2026-08-15 — **disregard them**.

`island_v3_plan.turns_back` rejects a candidate whose cumulative heading excursion exceeds 135°
(an S-curve returns toward zero and passes; a U-turn does not), applied *before* scoring. With
folds rejected every parallel run collapses to 0 m and the honest geometry appears:

| ramp | reported before | real |
|---|---|---|
| IC_RINKAI_E | 61.7 m | **25.4 m** |
| IC_RINKAI_W | 74.2 m | **34.0 m** |
| IC_YAMATE | 66.6 m | 66.4 m |

A gore and a touchdown ~180 m apart cannot absorb a 12 m descent (200 m at 6%) *and* a turn. The
distance between the two authored points is the constraint and no search can fix it — so
`NEEDS_AUTHORING` now names four ramps (`IC_CHUO`, `IC_PORT`, `IC_RINKAI_E`, `IC_RINKAI_W`), the
self-test still fails on a fifth, and the decision is real: **move the touchdowns further along
their arterials, add loop ramps, or sign these at 30–35 km/h.**

**Built vs planned radius, after all of the above** (`min(window 25, window 12)`, and now
fold-free, so the numbers mean what they say):

```
IC_CHUO         plan  46.6   built  46.6      IC_RINKAI_E     plan  25.4   built  24.8
IC_CHUO_EN      plan  76.2   built  68.6      IC_RINKAI_E_EN  plan 983.2   built 363.4
IC_YAMATE       plan  66.4   built  61.4      IC_RINKAI_W     plan  34.0   built  34.7
IC_PORT         plan  47.4   built  46.7      JCT_AIRPORT     plan 120.9   built 120.9
```

Remaining pipeline loss is the touchdown landing's own ~6.3 m smoothstep; `RAMP_FIT_TARGET`
(70 m) budgets for it so a ramp planned to the standard is not built below it.

### Step 7 — Per-slot ports  ✅ DONE (2026-08-15)

`lib/lane_ports.py` (pure Python, self-tested) + `addons/road_kit_authoring/ops_lane_ports.py` +
`smoketest_lane_ports.py`. One marker per **lane end**, on that lane's own centreline, arrow along
its direction of travel:

- **`lp_IN_*` / `lp_OUT_*`** — traffic enters / leaves the piece here. A two-way road end shows
  both, so *which way traffic goes through a connection* is visible rather than guessed. Joining
  OUT-to-OUT (two streams head-on) or IN-to-IN (a seam nothing feeds) is refused **by name**
  (`flow_conflict`) instead of quietly producing a link the gate later calls DISJOINT.
- **The port IS the exported lane's endpoint.** Ports are derived from the very lane dicts
  `lane_export.export_piece_dict` produces — not re-derived from the profile with a second
  convention. A port computed independently could disagree with the lane it names, and then
  snapping to the port would not align the lane. Because they are the same data, a snapped seam
  necessarily measures aligned under `lane_joints`' edge test; the self-test asserts exactly that.
- **`Snap Lane To Lane`** rigidly rotates + translates the *active* port's piece so the two lane
  ends coincide and flow the same way, rebuilds through the normal dispatcher, stamps the joint
  (`rka_linked_to`), and reports the resulting worst edge gap in metres. Alignment is geometry;
  connectivity stays authored.
- **Opt-in per piece.** `Show Lane Ports` materialises them for the selection; once a piece has
  them every rebuild refreshes them (`refresh_if_present`, wired into
  `ops_intersection._rebuild_piece_in_place` and `live_edit._flush_rebuilds`). A piece nobody asked
  about stays clean — the island would otherwise carry a couple of thousand Empties.
- **Tagged `rka_lane_port`, deliberately NOT `rka_port`.** `live_edit._flush_port_drags` treats any
  `rka_port` Empty as a drag handle for its piece's spine endpoint (`"A"` → first point, anything
  else → last), so a lane port carrying that key would yank the far end of the road onto a lane
  centreline the moment it was nudged. Same trap `_place_segment_ports` documents for `rka_segend`;
  the smoketest pins it.

Intersections get ports too, via the same path: a junction's fan of movements off one approach
lane **merges into one port** naming all of them (measured against the real sidecar: 158 of 160
same-arm groups agree to within 5°, and the 2 that differ by 180° are genuinely opposite flows and
stay separate).

Still to do from Step 7's table: **slot-level edit ops** (add/drop/taper a slot at a station), the
one pain point that was never about ports.

### Step 7 (original problem statement) — the authoring pain points

Recorded 2026-08-13 from use as a level editor. Three of the four complaints are **one root
cause**: *a port is a single point at the road CENTRE*, so nothing downstream can name a lane.

| Pain point | Why it happens | What fixes it |
|---|---|---|
| Adjusting lanes for a ramp exit/enter is fiddly | the aux/gore lanes are a `ProfileSet` edited through scalar operators, with no direct "open an AUX slot here" gesture | slot-level edit ops on the piece (add/drop/taper a slot at a station), which the ProfileSet already models |
| Lane cannot be snapped to lane | a port is the road centre — there is no per-lane anchor to snap TO | **per-slot ports**: one port per drivable slot, positioned by `slot_offset` |
| Segment↔intersection / intersection↔segment snapping is unreliable | same — an arm port is one centre point, so the match is a proximity guess about whole roads | arm ports become per-slot too; snapping becomes "connect slot A to slot B" |

This is **not a new subsystem** — it is the same statement Step 4's connection graph has to emit
anyway (`Connection(from_piece, from_slot, to_piece, to_slot, kind)`). Once `slot_offset` owns
lateral position and links are explicit, a port *is* a slot with a world transform, and snapping,
the exported graph, and the gate all read the same data. Doing it before Step 4 would mean building
it twice, which is why it sits here and not earlier.

### Step 8 — Unify what is already in the map

The live blends currently hold pieces from **both** cross-section models (the migration's whole
point, and the user-visible "profile/mesh in the current map" complaint). After Step 3 the build
path is single, but existing pieces are not: `island_v3_roads.blend`, `world_session.blend` (6
pieces still carrying stale BOX/ASSET values) and `District_industry_5_1`'s `MANUAL` collection all
need converting to carrier + `ProfileSet`, so exactly one model exists in the file. Conversion is
mechanical — `custom_props.read_profile` already prefers a written profile, and
`scalars_from_profile` inverts the bridge — but it is destructive to authored files, so it runs
last and per-file with the gate as the check.

---

## 5. Known-bad, deliberately not fixed yet

**Ramp exit alignment.** ✅ **FIXED (2026-08-15) — Step 6.** Four separate defects, each hiding the
next; every one was found by measuring rather than by reading the code.

1. **Arrival tangent followed the chord, not the road.** `ramp_polyline`'s departure handle used
   the mainline tangent but its arrival handle used the straight line from the end of the parallel
   run to the touchdown — a direction no road runs in. When `fit_ramp` chose the departure
   direction pointing away from the touchdown, the curve had to U-turn to arrive (`IC_CHUO`'s
   teardrop). Now it arrives along `arterial_tangent(touchdown)`, oriented to the approach so a
   reversal is unrepresentable.
2. **The polyline was wildly non-uniform**: `[gore] + 19 bezier samples`, so the FIRST span was the
   entire parallel run — up to 260 m — against ~20 m elsewhere. Every arc-length-windowed
   measurement then depended on where its window landed: `IC_RINKAI_E` measured **159.1 m at an
   18 m window and 19.6 m at 25 m from the same points**. Resampled uniformly at 8 m.
3. **The two checks used different windows** (18 m here, 25 m in `road_geometry`), so this module
   passed ramps the export gate then failed. Unified, and a second short window
   (`RAMP_KINK_WINDOW`) now catches local cusps — which the handle-scale search was otherwise free
   to fold into the middle of a curve to buy a better sustained radius.
4. **`land_ramp_on_kerb` sheared the whole ramp.** It spread the ~6 m centreline→kerb-lane
   correction linearly over the ENTIRE ramp in a fixed direction, which bends a curve wherever it
   turns relative to that direction. Measured: it roughly **halved every ramp's radius between the
   plan and the built spine**, point count unchanged — `IC_RINKAI_E` 61.7 → 29.3 m, `IC_RINKAI_W`
   74.2 → 41.6 m — silently undoing the geometry `fit_ramp` had just searched for. A touchdown
   correction is local, so it is now a smoothstep over the last 120 m.

`min_radius` also stopped being a hand-written literal: `RAMP_MIN_RADIUS` is the 45 km/h figure
(59.1 m) and the self-test now **asserts** instead of merely printing TIGHT lines nothing ever read.

**`IC_CHUO` and `IC_PORT` still need an authoring decision** (r ≈ 47 m and 48 m against 59 m).
The search tries every parallel run and handle scale and no cusp-free curve reaches it from their
authored gore/touchdown pair — move the touchdown further from the gore, or accept those two at
~35 km/h. Named in `NEEDS_AUTHORING` so a *third* ramp regressing still fails the self-test.
(This replaces the old `IC_RINKAI_E fits=False` entry — that one now fits.)

**Embankment is a vertical-sided prism at road width**, not a battered trapezoid. A real embankment
is road-width at the top widening to the toe at the bottom; that cannot be had by affine-scaling one
instanced primitive (the top:bottom ratio varies with height), so it needs a side wedge per side or
a per-vertex offset after realizing. `fill_footprint` still reports the true toe for authoring
clearance.

**Pair-interchange ramp corridors.** `INTERCHANGE_SIDE` assigns which direction each interchange
serves; entry corridors are derived (`entry_endpoints`, 320 m along the ring, collision-aware).
`IC_RINKAI_E_EN` sits 81 m from `JCT_AIRPORT` — legal but tight, and a candidate for hand-authoring.

---

## 6. Traps that already cost time — do not re-learn these

- **Two profile-Y conventions.** `GN_CurbLoop` maps profile +Y → world **−Z** (so
  `kit_common._curb_profile_object` negates); `GN_ProfileSweep` maps +Y → **+Z**. Reusing one
  builder for both hangs every curb under the road. `segment_stack`'s builders are separate on
  purpose.
- **`GN_RoadSupport` does not pass input geometry through.** Stacking it on a spine *replaces* the
  pavement with the columns. It must ride its own object (sharing the carrier's datablock is fine
  and is what makes road+piers move together).
- **`in_reservation` takes endpoints modulo road length** so ring intervals can wrap. On an *open*
  road `(0, total)` collapses to a single point and `(0, total+1)` reserves the first metre. Use
  `(0, total - 1e-3)`.
- **Stale rule tables fail silently and look like missing features.** Both
  `lane_export._LINK_RULES` and the old `check_road_network.py` were keyed to the retired
  `trunk`/`branch_a` roles; nothing matched the new shape, so zero links were emitted and every
  group "failed". Grep for hardcoded role names when something emits nothing.
- **Proximity joins tail→head only.** A ramp landing mid-lane is unreachable however close it is —
  hence `ramp_touchdown_cuts`. Measured: 3.24 m from the lane, 14.19 m from any lane *head*.
- **Never rebuild an authored alignment; transform it.** Replacing a ramp's endpoint with the gore
  seed produced a 47.9 m opening segment and a −55.3° kink. `seed_ramp` slides it with a decaying
  offset instead. Trimming-and-re-leading along the tangent was tried and is wrong: a ramp stops
  advancing along the mainline tangent almost immediately, so "keep what is ahead" discarded 6 of 8
  ramps down to a 25 m stub.
- **`--python-exit-code 1` must come BEFORE `--python`, or the whole test suite silently reports
  success.** Blender parses arguments IN ORDER: `--python` runs the script the moment it is parsed,
  so a `--python-exit-code` to its right is read only after the exit status has been decided.
  Verified directly — `blender -b --python boom.py --python-exit-code 1` exits **0**, the same
  command with the flags swapped exits **1**. This is the twin of defect 11 (a gate that cannot
  pass): a gate that cannot *fail*, which is worse, because it reads as reassurance. It had hidden
  **4 genuinely broken smoketests** (the real baseline was PASS=54 FAIL=4, not the 58/0 this file
  used to claim): a stale `(mat_id, thick_id)` 2-tuple unpack of `make_road_profile_group` (returns
  4 ids since the asymmetric-carriageway change), marking objects renamed `_yellow_`/`_white_` →
  `_line_y_`/`_line_w_` in two tests, and `end_side_adjust` still asserting the pre-asymmetric
  `max(fwd, rev) * lane_width` sweep radius. Always run `tools/run_smoketests.sh`.
- **Measuring a piece is not free, and must not look like an edit.** Two separate hazards, both
  reproduced while writing `lib/piece_probe.py`:
  - Evaluating a piece forces a depsgraph update, which `live_edit._on_depsgraph_update` cannot
    distinguish from user dirt — it queues a rebuild, and a second rebuild landing on the same
    piece is the documented `clear_generated_mesh_objects` segfault. The probe wraps every
    evaluation in `live_edit.rebuilding()` (lazily imported, so `lib/` keeps no addon dependency).
  - Reading MATERIALS off evaluated geometry is unusable on this Blender build: a GN-backed Curve's
    evaluated slot can hold a bare `ID` whose `.name` is a dangling read, and building an evaluated
    mesh from those objects right after a rebuild operator segfaults about **one run in five**.
    Ask the GN modifier's Material input instead (`kit_common.get_mod_input`). `piece_probe`
    carries a comment where the `materials()` function used to be, so nobody re-adds it.

---

## 7. Key files

Paths are relative to `blender/` (where this file lives) unless marked otherwise.

| File | Role |
|---|---|
| `ROAD_KIT_REDESIGN.md` | design of record; 13 defects → rules; build order |
| `lib/lane_profile.py` | Slot/Profile/ProfileSet; the single owner of lateral position |
| `lib/road_stack.py` | the layer stack; carrier + `build_stack` |
| `addons/road_kit_authoring/segment_stack.py` | build params → layers; profile objects |
| `addons/road_kit_authoring/ops_split.py` | split/merge, ramps, two-way carriageway |
| `addons/road_kit_authoring/lane_export.py` | per-piece lane dicts + link refs |
| `lib/lane_kit.py` | `combine_pieces` — resolves refs into the sidecar |
| `lib/piece_probe.py` | measure a piece's geometry against its own spine, carrier-agnostic (Step 1) |
| `tools/run_smoketests.sh` | **run the suite** — never hand-roll the blender invocation, see §6 |
| `tools/check_road_network.py` | **the gate** |
| `tools/island_v3_to_roadkit.py` | builds the island network from the plan |
| **`../tools/island_v3_plan.py`** | layout source (REPO ROOT `tools/`, not `blender/tools/`): interchanges, `INTERCHANGE_SIDE`, ramp fitting, support rules |
| **`../tools/island_v3_geom.py`** | island shape: coast, terrain, arterial centrelines |

Note the addon is **symlinked** into Blender (`~/.config/blender/5.2/scripts/addons/road_kit_authoring
-> blender/addons/road_kit_authoring`), so repo edits are live with no reinstall step.
