# Road Kit — ground-up redesign

Written 2026-08-13, after a session that measured (not guessed) why the current pipeline has
holes. This is the design of record for the rebuild; `AUTHORING_GUIDE.md` stays the guide for
using whatever exists today.

---

## 1. What actually went wrong, and what each defect teaches

Every item here was measured against `assets/world_source/island_v3_roads.blend` or a build from
it. They are listed because the new design is shaped by them, not by taste.

| # | Defect (measured) | Root cause | Rule it forces |
|---|---|---|---|
| 1 | One-way roads swept double width; gore seeded 3.25 m into empty air | Three consumers each re-derived the cross-section with their own convention | **One owner of "where is slot *i*"** |
| 2 | An exit lane could not be expressed at all; `trunk_before`/`trunk_taper`/`trunk_aux` existed only to change a lane *count* | A piece carried one scalar lane count | **Cross-section is per-station, not per-piece** |
| 3 | `LOOP_A` — a 3278 m ring with **zero** crossing cuts — was built as 12 pieces | Same as 2, at road scale | **A road is one piece unless something real divides it** |
| 4 | Half the addon is `clear_generated_mesh_objects` / `_rka_touched` / `sweep_untouched_boundaries` | Python owns the lifetime of sibling objects | **One object per piece; layers are modifiers** |
| 5 | A taper/ramp could not vary along the piece | A `Curve` datablock cannot hold custom per-point attributes | **Mesh carrier** |
| 6 | Support duplicated: 94 objects over 26,227 m for a 23,902 m network; the same ramp built twice | Support derived per *segment* | **Understructure belongs to the road, and shares its spine** |
| 7 | Deck vanished, leaving bare columns | `GN_RoadSupport` does not pass input geometry through | **Every layer is pass-through; a layer that replaces is a bug** |
| 8 | Embankment 16.5 m wide under a 4.5 m ramp, and `Half Width` fed the full width | Fill drawn as a prism of *toe* width; unit confusion | **Name units in the socket; a layer never exceeds the road it serves without saying so** |
| 9 | Ramp opened with a 47.9 m segment and a −55.3° kink | Endpoint *replaced* rather than the alignment moved | **Never rebuild an authored alignment; transform it** |
| 10 | **717 lanes, 0 with successors, no typed movements, 6 with lane-change edges** | The lane graph was never emitted — only endpoint proximity | **Connectivity is authored data, not inferred from distance** |
| 11 | `check_road_network.py` failed every group by construction | Checker hardcoded the old roles | **A gate that cannot pass is worse than no gate** |
| 12 | Expressway laterally correct but topologically detached: ramp tip 3.24 m from an arterial *lane* yet 14.19 m from any lane *head* | Proximity joins tail→head only; a ramp lands mid-lane | **A touchdown is a junction and must cut the road it lands on** |
| 13 | `LOOP_B` reachable *into* but never *out of* | All exits were put on carriageway A, all entries on B | **Each direction needs its own exits AND entries** — see 2.3 |

Defects 12 and 13 were both found by the gate once it was made truthful, which is the argument
for building the gate first.

Defect 10 is the one that matters most. The gore geometry is *fine* — every auxiliary lane ends
0.85–3.49 m from its ramp's lane, inside the 4.5 m junction radius — yet the exits are unusable,
because an exit lane has no way in except a lane change and no lane-change edge exists. Geometry
that looks connected and a graph that isn't is exactly the "hole" this rebuild has to close.

---

## 2. The model

Five concepts. Nothing else is a first-class thing.

### 2.1 Slot / Profile / ProfileSet  *(exists: `lib/lane_profile.py`, self-tested)*

A **Slot** is one lateral band: stable `id`, `kind` (TRAVEL/AUX/SHOULDER/MEDIAN/SIDEWALK/PARKING),
`width`, `dir` (FWD/REV/NONE), `mark_left`. A **Profile** is an ordered list of slots plus an
`anchor` fixing where `s = 0` sits. A **ProfileSet** is N profiles at N stations along the piece.

The stable `id` is the whole trick: a lane that tapers in is the same id at width 0 then width w,
so `interpolate()` subsumes every `_end` scalar, and "this lane becomes that ramp" is expressible.
`slot_offset()` is the single owner of lateral position — defect 1 cannot recur because there is
no second formula.

### 2.2 Piece

**One carrier object, one ProfileSet, one modifier stack.** The carrier is a mesh polyline: one
vertex per control point, per-vertex attributes carrying the cross-section (defect 5). The piece
*is* that object — there are no generated siblings, so there is no lifetime problem (defect 4).

A piece is divided only by something real: an intersection, or an authored break. Not by a lane
count changing (defect 3).

### 2.3 A highway is ONE piece carrying BOTH directions

This is a change from what exists, and it is the requirement that shaped the rest.

Today the expressway is two one-way roads, `LOOP_A` and `LOOP_B`. That was a workaround for the
scalar model: two directions with independently varying lane counts could not live in one piece.
With a ProfileSet they can — FWD slots, a MEDIAN slot, REV slots, and each direction's auxiliary
lanes opening and closing on their own stations:

```
REV side                    median                    FWD side
[ IC_X_EN_A0 ][ R1 ][ R0 ] [ MED ] [ F0 ][ F1 ][ IC_Y_A0 ][ IC_Y_GORE ]
   entry, opens                                  exit, opens
   around IC_X only                              around IC_Y only
```

So **a segment can have different enter/exit on each side**, which is what makes ramps work
without splitting the road. `anchor = DIVIDE` puts `s = 0` on the median — the driving datum —
which is also why the one-way anchor question stops mattering: a real highway piece has two
directions and a genuine divide.

Consequences that fall out for free: one spine to drag, one continuous understructure, one place
the road's identity lives, and no seam every time a ramp happens.

### 2.4 Ramp

A ramp is **its own piece** (one-way, usually one lane), joined to a segment by an explicit
connection — never by being carved out of it. Its authored alignment is *transformed* onto the
gore, never rebuilt (defect 9): slide it so the gore end lands on its slot, decaying to zero at
the far end so the touchdown stays where authored.

The mainline's side of the exit is purely a cross-section change: an AUX slot opening flush, a
SHOULDER (gore) slot opening only over the final nose run, then both dropping. That is the
"segment prepares for enter/exit" half, and it is data, not geometry code.

### 2.5 Connection  *(new — this is the hole)*

An explicit, exported record:

```
Connection(from_piece, from_slot, to_piece, to_slot, kind)
kind ∈ { THROUGH, EXIT, ENTRY, TURN, LANE_CHANGE }
```

- **THROUGH** — a slot continues into the next piece's slot across a shared boundary.
- **EXIT / ENTRY** — a mainline AUX slot hands off to / receives from a ramp piece's slot.
- **TURN** — a movement through an intersection, one per (in-slot, out-slot) pair.
- **LANE_CHANGE** — adjacency *within* a piece, from `lane_profile.lane_neighbors`.

Proximity may **seed** these at build time, but the exported graph is explicit. Nothing downstream
infers connectivity from distance. This is what closes defect 10 and what makes "ramp connects to
one of the segment's lanes" a statement the data can carry.

---

## 3. Layers

An ordered modifier stack on the carrier *(exists: `lib/road_stack.py` + `addons/…/segment_stack.py`)*:

```
[Spine]      mesh -> curve; computes the lateral frame ONCE as a point attribute
[Pavement]   asymmetric swept carriageway
[Median]
[Curb L] [Curb R]
[Sidewalk L] [Sidewalk R]
[Props L/R] [Streetlights]        asset rows
[Support]    piers / embankment, from deck height over terrain
[Finish]
```

Two rules, both bought with defects:

1. **Every lateral offset is computed in Python from `lane_profile` and handed to the layer as a
   per-point attribute. Nodes never derive where a slot is** (defect 1 would otherwise recur
   somewhere far harder to see).
2. **Every layer passes its input geometry through.** `GN_RoadSupport` does not, which is how the
   deck disappeared and left bare columns (defect 7). A layer that replaces its input is a bug,
   and the stack builder should assert it.

Support therefore becomes an ordinary layer on the same carrier — which is what "one thing to
move" means: drag the spine, the road and its piers follow, because they are the same object.

---

## 4. Export to Godot

- One **Path3D per lane run** — start/end station included, so a lane that exists for part of the
  piece exports as a lane for that part (defect 2).
- The **connection graph** alongside it, typed as in §2.5.
- Markings as trim-sheet UV columns driven by `Slot.mark_left`, not generated ribbons.
- Sidecar stays `.lanekit.json`; the runtime reads explicit links first and only falls back to
  proximity where a link is absent.

---

## 5. What survives, what goes

**Keep (already the new design, already tested, never wired in):**
`lib/lane_profile.py` · `lib/road_stack.py` · `addons/road_kit_authoring/segment_stack.py` ·
`addons/road_kit_authoring/spine_io.py` · the split/ramp/carriageway primitives in `ops_split.py`

**Delete once the stack is the build path:**
`clear_generated_mesh_objects` · `_rka_touched` tagging · `sweep_untouched_boundaries` ·
`rebuild_segment_gn_in_place`'s object reconciliation · the sibling-object builders in
`_populate_segment_mesh_gn` · the scalar `_end` twins · `scalars_from_profile` (a migration bridge)

**Rewrite:** `check_road_network.py` against the new roles, and make it a gate that runs on every
build (defect 11).

---

## 5a. The connectivity gate (standing requirement)

**Every build runs a network connectivity check, and a build that fails it is a failed build.**

This is not a diagnostic to run when something looks wrong. The whole class of defect this rebuild
exists to remove — geometry that *looks* joined while the graph is not (defect 10) — is invisible
in the viewport and cheap to detect in the data. Without a standing gate we shipped 717 lanes with
zero successors and nobody noticed; with a *broken* gate (defect 11) we had worse than nothing,
because its failures were structural and so carried no information.

What the gate asserts, on the exported sidecar:

1. **No dangling references** — every `next` / `inner_lane` / `outer_lane` names a lane that exists.
2. **Every drivable lane is reachable** from at least one other lane by *explicit links only*,
   with proximity disabled. Proximity is a runtime convenience, never a substitute for data.
3. **Every ramp is usable** — an EXIT ramp's lane is reachable from the mainline, an ENTRY ramp's
   lane reaches the mainline, and the exit case is reachable *only* via a LANE_CHANGE edge (which
   is the property that was silently missing).
4. **Every piece joins the wider network** — no island of internally-perfect lanes.
5. **Movement kinds are present** where the topology implies them (an exit group has an EXIT, a
   merge group an ENTRY, every group a THROUGH).

It must be runnable two ways: standalone on a `.lanekit.json` for a quick answer, and as a
smoketest in the suite so it cannot rot unnoticed. When it fails it names the piece, the lane and
the missing edge — a gate that only says "FAIL" trains people to ignore it.

---

## 6. Build order

Each step ends green and useful on its own.

1. **Truthful gate.** Fix `check_road_network.py`; add a connectivity smoketest. *Without this we
   are flying blind — it has been failing structurally, so it could have been masking real breaks.*
2. **Connection graph.** Emit THROUGH / EXIT / ENTRY / LANE_CHANGE from the profile
   (`lane_neighbors` already computes the last). Ramps become drivable. Gate from step 1 proves it.
3. **Two-direction highway piece.** One piece carrying FWD + MEDIAN + REV, per-direction aux
   slots. Retire `LOOP_A`/`LOOP_B`.
4. **Stack as the build path.** Swap the carrier and the layers; port the 19 smoketests that
   currently assert sibling objects by name to assert *invariants* instead. This is the big one —
   `live_edit.py`, `median_merge.py` and the intersection joints all move with it.
5. **Intersections on the same footing.** Arms as slots, turns as TURN connections.
6. **Export.** Path3D per lane run + the connection graph.
7. **Regenerate `island_v3`** and delete the old path.

Ordering rationale: 1–2 make the road *work* and are small; 3 is the requirement that reshapes the
data; 4 is the largest change and is cosmetic-but-deep, so it goes after correctness; 6 depends on
2 and 3 being settled.

---

## 7. Invariants the tests should assert

Assert *properties*, not object names — coupling tests to `curb_*` / `sidewalk_*` siblings is why
19 of them block the stack migration.

- A piece is as long as the alignment it was given (nothing silently cut).
- Slots that persist across stations do not move laterally.
- A profile's paved width never exceeds the sum of its slot widths.
- Every layer's output contains its input.
- Every drivable slot reaches the wider network through explicit links alone (no proximity).
- An exit lane is reachable from the mainline, and only via a LANE_CHANGE edge.
- Support geometry exists exactly where `support_kind(delta)` says, and nowhere else.
