# Segment/joint alignment + multi-lane-transition architecture study

> Durable copy of an architecture study (2026-08), kept here so it can be picked back up across
> sessions.

## Status: Option B implemented (2026-08)

User chose **Option B** (fix + chain, not the full per-point-profile rewrite) and confirmed the
current median-widens-the-road resize behavior should stay as-is. All five root causes below are
fixed:

- Finding #1 (`_sync_linked_width` always wrote start-side props) -- fixed, now end-aware
  (`live_edit._sync_linked_width`'s `end` parameter).
- Finding #2 (no live end-side lane/median control) -- fixed: `RKA_OT_adjust_segment_lanes_end`,
  `RKA_OT_adjust_median_width_end` (`ops_segment.py`), wired into the panel next to the existing
  start-side rows. Also fixed the coupled bug where the OLD start-side operators flattened any
  existing taper to one uniform value on every click (`ops_segment._refresh_pavement_radius`, now
  shared by all four adjust operators).
- Finding #3 (no dual-end link/solve) -- fixed: `port_A`/`port_B` can now be link dependents
  (`ops_intersection._is_link_dependent_marker`), and `live_edit.move_dependent_marker` detects a
  dual-linked segment and reshapes the whole spine via `_blend_spine_endpoints` (an arc-length-
  blended per-point displacement, not a rigid single-anchor transform) instead.
- Finding #4 (yellow line through median) -- fixed: `intersection_kit.build_segment_lane_markings`
  takes `median_half_start`/`median_half_end`, suppresses the yellow line and shifts the internal
  white boundary lines outward wherever a median is active.
- Finding #5 (asymmetric arm vs. symmetric pavement) -- left as documented, lower-priority/cosmetic
  (not implemented this pass).

Covered by smoketests: `smoketest_end_side_adjust.py`, `smoketest_median_marking.py`,
`smoketest_dual_end_link.py`, plus the existing `smoketest_joint_sync.py`/`smoketest_ports.py`/
`smoketest_link_propagation.py` re-verified with no regressions.

Option A (single continuous spine, per-point lane/separator profile, pavement generation moved
off Geometry Nodes) remains explicitly deferred -- revisit only if chained segments still visibly
read as "seamed" in practice after living with Option B.

## Follow-up fix: arm angle decoupled from marker position (2026-08)

After the above shipped, the user reported the gap/rotation problem persisting, and confirmed
directly via a read-only headless load of `world_session.blend`: a linked segment sat EXACTLY on
its arm (0.0000m position gap) with a permanent ~12deg TANGENT mismatch.

Root cause: an arm's angle was recomputed FRESH from its marker's POSITION (`atan2` against the
intersection origin) on every rebuild AND every live joint sync (`ops_intersection.
rebuild_intersection_in_place`, `live_edit._arm_joint_state`) -- oversensitive to ordinary
hand-drag imprecision, since a drag meant only to nudge an arm's distance almost never lands
perfectly radially by hand, so it always changed the angle at least slightly too. That unintended
angle delta then rigidly rotated the WHOLE linked segment (`move_dependent_marker`/
`_rotate_spine_points`) -- including its already-correctly-placed FAR end -- on every drag. Worse,
the OLD incremental angle-delta tracking (`rka_joint_last_angle`) could only ever correct for
CHANGES since it was last seeded -- `RKA_OT_connect_markers`'s one-time initial link syncs
position only (no previous angle exists yet to diff against), so any tangent mismatch already
present at connect time was baked in FOREVER.

Fixed:
- Angle is now read directly from the arm Empty's own `rotation_euler.z`, decoupled from
  position -- a pure Grab/translate (G key) never touches the rotation channel, so it can no
  longer change the angle at all; only an explicit Rotate (R key) or `RKA_OT_set_arm_angle` does.
  Position only ever supplies DISTANCE (`hypot`, not oversensitive).
- The old incremental `rka_joint_last_angle` tracking (`live_edit.move_dependent_marker`'s single-
  anchor rotation) was replaced with an ABSOLUTE, self-correcting measurement
  (`live_edit._spine_tangent_angle`): every sync measures the spine's actual current tangent and
  rotates by however much it differs from the target's angle RIGHT NOW -- immune to any
  stale/never-seeded baseline, fixes `RKA_OT_connect_markers`'s "no rotation on first link" gap
  too.
- `ops_intersection.ensure_arm_angle_migrated` -- a one-time per-arm migration seeding
  `rotation_euler.z` from the OLD position-derived angle, so already-existing content (e.g.
  `world_session.blend`) preserves its CURRENT visual state exactly instead of snapping back to a
  stale creation-time rotation, then becomes decoupled from then on.

Covered by `smoketest_arm_angle_decoupled.py` (translate-only leaves angle/far-end untouched
beyond a pure carry; migration preserves current angle, then decouples) and updated
`smoketest_joint_sync.py`/`smoketest_move_intersection.py`/`smoketest_dual_end_link.py`/
`smoketest_connect_markers_tangent.py` (all now simulate an explicit Rotate, not just a Translate,
when the test intends to change an arm's angle -- matching what the new model actually requires).

## Follow-up fix: "Aim At"/"Snap To" + the hard geometric limit (2026-08)

Decoupling angle from position (previous section) made an arm's angle *stable*, but didn't make it
*easy to set correctly by hand* -- the user reported a screenshot where a road stub ran off
diagonally but the arm/pad edge cut straight across it, asked whether a plain horizontal Grab could
also steer the angle (no -- see previous section, that's deliberate), and separately asked for an
easier way to visualize/adjust a port's edge than typing a raw angle.

Added `RKA_OT_aim_arm_at` (two panel buttons, "Aim At Selected" / "Snap To Selected") and
`RKA_OT_nudge_arm_angle` (+-1/+-5 deg buttons) so an arm can be pointed at any other object --
another arm, a port, a plain Empty -- without computing bearings by hand. Selection order: select
the TARGET first, Shift-click the ARM LAST so it's the active object (the one that moves) -- the
same "active = the one being changed" convention `RKA_OT_connect_markers` already uses, and what
the panel row/operator poll both require (the row only appears when the *active* object is an
`arm_*`). An earlier confusion here was over which object should end up active; both the panel
label and the operator docstring now spell out target-first/arm-last explicitly.

Re-verifying against `world_session.blend` (read-only headless load, never saved) surfaced a
second, more fundamental issue: **aiming an arm at a target's position and matching its tangent
direction are two different numbers, and only one can be exact at a time.** An arm's tail is always
`origin + distance * direction(angle)` -- one ray from the intersection's single shared origin
(`intersection_kit.Arm`). A real external edge (a segment's port) generally does NOT sit exactly on
the ray implied by its own correct tangent -- the two only coincide when the connecting road happens
to run exactly radially through that origin, which isn't generally true. Measured directly:
arm_E's bearing-to-`Segment_001.port_A` is 236.30 deg, while the segment's own tangent there is
241.17 deg -- a real ~4.9 deg gap baked into the geometry, not a bug in any angle calculation.

So `_resolve_target_angle_deg` (used by "Aim At Selected") prefers the TARGET's own tangent (via
its owning segment, for a port/origin target) over the raw bearing whenever available -- that's the
"orientation exact" choice, and it's what the arm's cap edge visually needs to align with. Since
that alone still leaves the position gap the user was asking to eliminate, `match_distance=True`
("Snap To Selected") does the opposite trade: use the raw bearing instead (the only angle for which
"distance along it" reaches the target's exact point), landing the arm's tail EXACTLY on the
target -- verified against `world_session.blend`, arm_E snapped onto `port_A` closes the position
gap to 0.0000m, leaving an honestly-reported 4.88 deg residual tangent mismatch (the report message
always states the size of whichever residual remains, so it's never a silent surprise). There is no
button that can zero out both at once when the target isn't already on the correct ray -- doing
that would require letting an arm's tail sit at an independent 2D position instead of one
shared-origin ray, a bigger data-model change not undertaken here (flagged in the operator's own
docstring as the only real further fix, if a residual ever proves unacceptable in practice).

Covered by `smoketest_aim_arm.py`: plain aim (tangent-exact, may leave a position gap), three nudges
landing at an exact expected angle, aiming cascading through a linked segment's tangent, and
`match_distance=True` landing exactly on a target not on the arm's original ray while leaving every
OTHER arm in the intersection completely untouched. Full suite (`smoketest_*.py`, all ~35 files) re-run
clean with no regressions.

## Follow-up fix: pin the far end -- don't rotate the whole spine (2026-08)

After the above, the user pushed back further: aiming/snapping only ever gets ONE of position or
tangent exact for the ARM (a hard limit of the single-ray arm model -- see previous section), and
asked to study whether the arm's model itself could be changed (decouple tail position from angle)
to get both at once. Investigation found that would only solve the FLAT (2D) case --
`intersection_kit.py` is explicitly flat-2D-plus-one-constant-Z per intersection, so it has no
concept of slope at all, while segments already ARE fully 3D/bendable (`segbend`) -- so decoupling
the arm doesn't reach a real fix once elevation matters, and pushes toward the much bigger,
previously-deferred "merge intersection+segment into one curve" rewrite for no real gain.

The actual fix stays on the SEGMENT side, which was already correctly identified as the flexible
element: the segment linked to an arm should adopt the arm's exact position AND tangent (a free
curve endpoint can always match an arbitrary position+tangent pair -- no ray-coupling problem, at
ANY angle), while its FAR end (e.g. `port_B`, not itself linked to anything) must NOT move as a
side effect. The old code didn't do this -- `move_dependent_marker`'s single-end branch corrected
the near end's tangent with `_rotate_spine_points`, a RIGID rotation of the WHOLE spine around the
joint, which necessarily swings the far end too (confirmed directly against `world_session.blend`:
linking `Segment_001`'s `port_A` to `arm_E` the correct way -- select `arm_E` first, shift-click
`port_A` last -- needs a ~169 deg tangent correction (72.35 deg vs the segment's original 241.17
deg), which under the old rigid-rotate behavior would have thrown `port_B` wildly out of position).

Also surfaced: a plain 2-point straight segment (confirmed the common case -- `Segment_001` itself
is exactly this) has no interior control point at all, so "exact tangent at the near end" AND
"far end completely pinned" is mathematically impossible without inserting one -- there's nothing
to bend at.

Fixed in `live_edit.py`, `move_dependent_marker`'s single-end branch:
- `_translate_spine` (rigid whole-spine carry) is UNCHANGED -- a plain position move legitimately
  carries the whole piece, including the far end (needed for `smoketest_link_propagation.py`'s
  multi-hop cascade, e.g. moving a whole intersection and everything chained off it).
- The TANGENT correction changed from `_rotate_spine_points` (rigid, removed -- no callers left)
  to `_bend_near_end_to_angle`, done in two EXACT stages instead of one rigid rotation:
  1. `_ensure_bend_room` inserts one interior control point near the joint end if the spine is a
     plain 2-point line (radius/pavement-width linearly interpolated to match the existing taper).
  2. That bend point is placed EXACTLY `joint_position + (its own original distance) *
     direction(joint_angle)` -- exact tangent at the joint by direct construction, no residual --
     then `_blend_endpoints_range` (a new generalization of `_blend_spine_endpoints`, scoped to a
     sub-range of the point array instead of always the whole spline) reshapes everything from
     that bend point through the far end so the far end lands back EXACTLY where the plain
     translate already put it.

Verified directly against `world_session.blend`: linking `arm_E` -> `Segment_001.port_A` the
correct way now lands the near end at an EXACT 0.0m gap with an EXACT tangent match (72.35 deg,
off by 0.00003 deg) despite the ~169 deg correction, while `port_B` moves by EXACTLY 33.15m -- the
SAME magnitude as the near end's own necessary reposition (the plain translate-carry, unavoidable
and correct any time a near end relocates) -- with zero additional rotational swing. Covered by the
new `smoketest_pinned_far_end.py`: a 100m segment, 25 deg tangent correction, asserts the far end
moves by EXACTLY the arm's own translate-carry delta and no more (the old behavior would add
~42m of unwanted swing on top). Full suite re-run clean.

## Follow-up fix: the ARM adapts, not the segment -- Arm.tail_pos (2026-08)

Direct testing of the above against `world_session.blend` surfaced that `arm_W` (not `arm_E` --
the piece actually near `Segment_001`'s `port_A`, confirmed by measured distance) still had a
0.41m residual gap even after using the operators. The user then gave an explicit, different
requirement than everything built so far: `Segment_001` must NOT move at all (it's already
correctly authored/positioned), the intersection's OTHER arms and its own center must NOT move,
and ONLY `arm_W`'s own position/edge should adjust to match the segment -- the reverse of the
"segment bends to the arm" direction the previous two sections built.

This re-runs into the original hard limit (arm position ALWAYS `origin + distance *
direction(angle)`, one ray, so position-exact and tangent-exact were two different angles) --
but this time it's solvable without the earlier-rejected full merge-into-one-curve rewrite,
because the actual coupling is narrower than it first looked: `curb_edges`/`_junction_corner_
vertex` (the ROUNDED CORNER between two adjacent arms) never read an arm's tail-CENTER point at
all -- confirmed by inspection, a corner fillet only needs a LINE (point + direction) for each
arm's edge, and `angle_deg` + lane width alone already fully determine that line; ANY point on it
works as the anchor. Only `build_junction_boundary`/`build_junction_curb_segments` (an arm's OWN
tail-CAP, the literal edge that must align with a connecting piece) actually use the tail-center
POSITION. So decoupling the cap's position from `angle_deg` cannot distort a NEIGHBORING arm's
corner geometry, however far off-ray the match is -- the earlier "3D/slope" objection to this
approach also doesn't block it here, since `Segment_001`'s own near/far/origin Z values are all
within ~0.1m of each other (confirmed measured) -- a non-issue for this concrete case.

Added `intersection_kit.Arm.tail_pos` (optional explicit local (x,y), None = old ray-derived
point, byte-identical default -- self-tests confirm) and `Arm.tail_center()`, used by
`build_junction_boundary`/`build_junction_curb_segments` only. `build_lane_movements`/
`build_ports` (AI driving-lane paths/connectivity) deliberately still use the plain ray point even
when `tail_pos` is set -- an intentional scope limit keeping this change out of the AI-navigation-
critical turn-arc math entirely.

`ops_intersection.rebuild_intersection_in_place` now passes each arm's REAL current local
position as `tail_pos` unconditionally (for an untouched arm this already equals the ray point, so
nothing changes for the common case). The one real wrinkle: the rebuild's own "re-snap onto the
clean ray" step (float-drift correction + wide-arm clearance growth) would otherwise silently pull
a matched arm straight back onto its ray on the VERY NEXT rebuild, undoing the match every time --
fixed by a new `rka_arm_tail_pos_locked` stamp: an arm matched via `RKA_OT_aim_arm_at` is excluded
from the re-snap; `RKA_OT_set_arm_angle`/`RKA_OT_nudge_arm_angle` (the classic ray-based numeric
tools) both clear the lock, an explicit, discoverable way back to ray-based positioning.

`RKA_OT_aim_arm_at` collapsed from two modes (Aim/Snap, each only ever exact on ONE of position or
tangent) into ONE operator/button ("Match Arm To Selected") that sets both simultaneously -- the
original "remove two buttons to one" ask, now actually achievable. Panel updated to the single
button.

Verified directly against `world_session.blend`, matching every one of the user's explicit
requirements exactly:
- `arm_W` <-> `port_A` gap: **0.000000 m**.
- Edge alignment: spine tangent 245.5862 deg == arm angle 245.5862 deg (diff 0.000002 deg).
- `Segment_001`'s spine: **0.000000 m** movement on every point (confirmed NOT moved).
- `arm_N`/`arm_E`/`arm_S`: **0.0 m** movement each (confirmed untouched).
- Intersection origin/center: **0.000000 m** movement (confirmed untouched).
- The match survives an UNRELATED later rebuild (adjusting a different arm's lane count) --
  gap stays exactly 0.000000 m, confirming the lock actually prevents the regression.

Covered by rewritten `smoketest_aim_arm.py` (exact position+tangent match, lock persists across a
separate rebuild, nudge clears the lock, cascades to a linked segment). Full suite + the pure-Python
`intersection_kit.py` self-tests both re-run clean.

## Follow-up: vertical (Z) joint fit + an extend_from_arm regression (2026-08)

Two more issues surfaced from further testing of the above:

**1. Z was still manual.** `RKA_OT_aim_arm_at` matches an arm's XY position + tangent exactly, but
always places it at the INTERSECTION's own flat Z (`intersection_kit.py` is explicitly "all
geometry is 2D, callers add one constant world Z" -- an arm literally has no Z of its own to give).
So a real elevation difference between the arm and the segment's port survived even after a
perfect XY+tangent match. Fix: `move_dependent_marker`'s single-end branch now only ever
XY-translates rigidly; Z is corrected the SAME LOCAL way as tangent
(`_bend_near_end_to_angle`, extended to take an optional `angle_rad=None` for "fix Z only, keep
the current tangent") -- so linking the segment to the arm (`Connect Markers`, AFTER matching the
arm's XY+tangent) now closes the vertical gap too, as a local grade fit near the joint, while a far
port that's already correctly connected/graded elsewhere is never dragged up or down. This is the
answer to "is it possible to do both, segment align to arm and arm align to segment" -- literally
both, each handling the axis it actually can: the arm supplies exact XY+tangent (its whole domain,
since it can't tilt a flat pad), the segment supplies the Z fit (something only a bendable spine can
do). Verified directly against `world_session.blend`: `arm_W` matched to `Segment_001.port_A`, then
linked -- near end lands at an exact 3D gap of 0.0m (X, Y, AND Z), `port_B` (a genuine ~0.4m lower,
confirming this segment really is sloped) does not move AT ALL. Covered by new
`smoketest_vertical_joint_fit.py`.

**2. `RKA_OT_extend_from_arm` regression.** User-reported: "extend from arm/intersection... no
longer create from exact port/arm location with align tangent." Root cause: this operator predates
`Arm.tail_pos` and always re-derived the new segment's start point from `origin + tail_length *
direction(angle_deg)` instead of reading the arm marker's own `.location` -- exactly right while
every arm was forced onto that ray every rebuild, but wrong the instant an arm can be
`tail_pos_locked` (off-ray). Fixed to read `arm_obj.location` directly (byte-identical for an
ordinary/unlocked arm, correct for a locked one). Verified against `world_session.blend`: extending
from the now-matched `arm_W` starts the new segment at an exact 0.0m gap. Covered by an added case
in `smoketest_aim_arm.py`.

Full suite + `intersection_kit.py` self-tests re-run clean after both fixes.

## Follow-up: segment-to-segment alignment (2026-08)

User-reported: "support segment to segment alignment, at least for the port point (if the segment
now has like 6 points, only the last point port is force move to align) for both arm/[segment]".
Root cause: every tangent/Z/width sync in `move_dependent_marker` was gated on `"rka_arm_name" in
target_obj.keys()` -- linking one segment's port to ANOTHER segment's port/origin (instead of to
an arm) got a rigid horizontal position carry but NEVER a tangent match, regardless of how many
control points either spine had. Fixed with `_segment_joint_state` (the segment-port counterpart
to `_arm_joint_state` -- same `(angle_rad, lane_width, lanes_forward, lanes_backward)` shape, but
`angle_rad` comes from the OTHER segment's own `_spine_tangent_angle` at that port, and lane
width/counts from its end-aware `rka_lanes[_backward][_end]` properties, the same pair
`_sync_linked_width` itself writes) and a unified `_joint_state(target_obj)` dispatcher (arm ->
`_arm_joint_state`, segment port/origin -> `_segment_joint_state`) used everywhere the arm-only
check used to be, including `_propagate_links`'s early-exit (a segment's tangent can drift even
when its port's raw position hasn't moved -- `_bend_near_end_to_angle`'s far-end pin keeps the
port's ABSOLUTE position fixed while still reshaping the interior point right before it, which is
exactly what that port's own tangent is measured from -- so position-match alone can no longer
mean "nothing to cascade" for a segment target either).

`_bend_near_end_to_angle`/`_ensure_bend_room`/`_blend_endpoints_range` needed NO changes -- they
were already generic (pure spine-point math, no arm-specific logic), so a 6+ point (already-bent)
dependent segment reshapes smoothly from the point right after the joint through the far end, the
same as a plain 2-point one gets a bend point inserted.

Verified with a new `smoketest_segment_to_segment_joint.py`: a 2-lane, 6-point BENT segment (off
one intersection) linked to a 1-lane straight segment's port (off a second, unrelated,
~300m-away intersection) -- near end lands at an exact 3D gap of 0.0m AND an exact tangent match;
far end moves by EXACTLY the horizontal translate-carry and no more (no extra tangent swing, no
vertical shift); width/lane-count correctly syncs to the target's own END-side values (not its
START values, and not a stale carry of the dependent's old config). Full suite + `intersection_kit.py`
self-tests re-run clean.

## Follow-up: median transitions, including a per-arm median (2026-08)

User-reported: "add a transition logic segment that allow[s] [the] median from high number to low
number act like transition." `intersection_kit.build_segment_from_spine`'s tapered path already
supported `median_width` != `median_width_end` within one segment (Option B, finding #2) -- no new
piece type was needed. What was missing: the JOINT SYNC (`_arm_joint_state`/`_segment_joint_state`/
`_sync_linked_width`) never read or wrote median width at all, so a segment's median stayed
whatever it was independently authored as even when linked to a joint with a very different one.
Fixed by threading `median_width` through the existing `(angle, lane_width, lanes_forward,
lanes_backward, ...)` joint-state tuple and `_sync_linked_width`, exactly like lane count/width
already worked -- linking a wide-median segment's end to a narrow/median-less one's port now tapers
the median across the link the same way a lane-count mismatch already tapers lanes.

User follow-up: "each intersection arm [should]... have idea of median... one arm can use as
transition to ease out the median from high count to low count." Until this point `intersection_kit.
Arm` had no median concept at all -- linking to an arm always tapered a segment's median down to 0.
Added `Arm.median_width` (PER-ARM, default 0.0, fully back-compatible) + `Arm.median_half()` (the
same "genuine two-way" gate a segment's own median uses), and rewired `in_width`/`out_width`/
`in_offset`/`out_offset` -- the ONLY 4 methods every other arm-geometry function
(`build_junction_boundary`, `curb_edges`, `build_lane_movements`, `build_ports`) goes through -- to
read it, so a per-arm median cascades through the ENTIRE intersection pipeline (pad cap, curb
corners, AND driving-lane centerlines, which must also shift outward in step or they'd disagree
with a linked segment's own median-shifted lanes) with no other code needing to know about it.
Wired into `ops_intersection.py`: `rebuild_intersection_in_place` reads/passes each arm's own
`rka_arm_median_width`; new `RKA_OT_adjust_arm_median_width` (+ panel row, mirrors
`RKA_OT_adjust_arm_lanes`) sets it live. `_arm_joint_state` now returns the arm's REAL median
(gated by the same two-way rule) instead of a hardcoded 0.0, so a segment linked to a median-
carrying arm tapers against that real value.

Note: `RKA_OT_extend_from_arm` does NOT auto-continue an arm's median into a freshly-built segment
(unlike lane count, which already auto-continues) -- a fresh extension still defaults to 0 median;
only the LIVE joint sync (Connect Markers, or a later drag/rebuild cascade) picks up the arm's real
value. Verified with `smoketest_median_joint_transition.py` (3 cases: arm->segment high-to-low,
segment->segment low-to-high, and a per-arm median confirmed isolated to one arm + picked up by a
live-linked segment). Also added the missing `median_width_end` property to `RKA_OT_extend_from_arm`
(it already existed on `RKA_OT_build_straight_segment`/`RKA_OT_build_lane_transition`, but was
absent here -- an oversight, not by design). Full suite + `intersection_kit.py` self-tests re-run
clean.

## Follow-up: ONE continuous median WALL mesh across a linked chain (2026-08)

User-reported: "change the current median to [a] single mesh of curb instead of curb on each way,"
explicitly chosen as fully-automatic/always-live-synced (not a manual button) after being told the
tradeoff (a genuinely new cross-piece dependency, unlike everything else this session which only
ever synced ONE piece's own end to a joint). This is a deliberate, narrow exception to the addon's
otherwise-universal "each piece owns its own small generated objects" convention -- justified because
a median WALL specifically shows a visible seam at every joint (each piece's own wall has a flat end
cap) that position/tangent/Z sync alone cannot fix; a flush/NONE-style median has no such object at
all (just painted stripes, already continuous for free via the median-width joint sync above), and
ASSET-style repeated-instance curbs are left as a known, unimplemented follow-up.

New `median_merge.py`: discovers every mergeable chain (2+ segments, 'BOX'-style median active on
both sides of each link) by walking the existing `RKA_LINKED_TO_KEY` graph, orders each chain end-
to-end (tracking which members' own natural point order runs backward relative to the chain, i.e.
need reversing), extracts each member's own median-edge polylines via
`intersection_kit.build_segment_from_spine` (reused, not re-derived), concatenates them into ONE
continuous curve per side, and builds it as a `curb_loop` object in a dedicated `RKA_MedianChains`
collection -- deleting each member's own individual median wall object once merged. Runs from
`live_edit._flush_rebuilds`'s tail, AFTER the normal per-piece dispatch, fully recomputing from
scratch every call; delete+recreate is safe here specifically because this only ever runs in the
already-deferred (post-drag, outside the depsgraph callback) context the rest of `_flush_rebuilds`
already relies on.

**Three real, previously-latent bugs surfaced building this**, none of them new -- all pre-existing,
just never exercised by any single-piece-focused smoketest before a MULTI-piece merge needed both
ends' geometry to agree exactly:

1. **`_sync_linked_width`'s end-side fallback could silently drift.** `_effective_end_lanes`/
   `_effective_end_median` fall back to the START value when no independent END value was ever set
   ("an untapered piece's end IS its start"). Writing the START side (a joint sync) used to write
   straight through that fallback, silently changing the FAR end's EFFECTIVE value too for any
   never-independently-tapered piece -- exactly the failure mode every other joint-sync fix this
   session avoided. Fixed by materializing the END side's current resolved value into an explicit
   property FIRST, before the START write, so the fallback can never again inherit a start-side
   change after that point.
2. **`_bend_near_end_to_angle`'s `_blend_endpoints_range` call had swapped arguments for the 'end'
   case.** `sub`'s first/last index order is OPPOSITE between 'start' (bend_idx first, far end
   last) and 'end' (far end first, bend_idx last) -- the `(start_new, end_new)` arguments passed
   were never flipped to match, so an 'end'-side correction pinned the far point to the bend
   value and vice versa, producing an inserted "overshoot and double back" zigzag instead of a
   clean local bend. This is the first-ever exercise of a single-end TANGENT correction at a
   piece's 'end' in any smoketest this session -- every earlier one used 'end' only for the
   dual-end position-only blend, or as an unmoved TARGET read by a 'start'-side dependent.
3. **A median-edge polyline's `edge_0`/`edge_1` identity is not a fixed physical label.**
   `lane_perp`/`offset_line_tapered` derive each point's offset DIRECTION from that spine's own
   local, array-order tangent -- reversing which end is index 0 (a chain member walked backward)
   flips that local tangent, and therefore flips which physical side `edge_0` lands on. Confirmed
   concretely: an aligned member's `edge_0` sat on the +Y side; a reversed member's `edge_0` (its
   own natural array running the opposite way) sat on -Y -- concatenating `edge_0`-to-`edge_0`
   would have joined two DIFFERENT physical sides. Fixed in `_oriented_edges`: a reversed member
   swaps `edge_0`<->`edge_1` in addition to reversing each array's point order.

(A fourth suspected bug -- `_spine_tangent_angle`'s 'end'-case sign -- was investigated, "fixed,"
then reverted after re-deriving the desired geometry from first principles: the ORIGINAL `(pts[-2],
pts[-1])` formula was already correct, matching `_arm_joint_state`'s "direction of travel as the
road continues through this point" convention for both ends symmetrically; the actual bug was
#2 above.)

Verified with a new `smoketest_median_chain_merge.py`, deliberately constructed with a
"meet in the middle" topology (two segments from two separate intersections, linked far-end-to-
far-end) specifically because it's the one arrangement that exercises a reversed chain member --
the ordinary "keep extending forward" authoring pattern never produces one. Confirms: correct
chain ordering/alignment detection, exactly 2 merged objects with the right total point count (no
duplicate joint point), strictly monotonic/single-sided geometry (no mis-ordering, no side
mismatch), correct endpoints, and each member's own individual median wall removed. Full suite +
`intersection_kit.py` self-tests re-run clean (twice), and the real `world_session.blend` arm-match
scenario re-verified unaffected (it only ever exercised the 'start' case, never touched by bug #2).

## What was asked

Three reports, bundled together in one message:

1. Intersection arm / segment port edges don't fully align when moved, and there's "no friendly
   way" to adjust the edge angle -- it "reflects the generated lane data" and looks wrong.
2. A segment with a different lane count intended at each end (grow on one port, shrink on the
   other) doesn't visibly taper -- "the overall mesh seems not to change."
3. Bigger ask: can the median/yellow-line separator become a real, swappable MESH piece that can
   shrink to 0 (not just grow), and can one segment carry MULTIPLE lane/separator transitions along
   its length (not just one taper from start to end) -- versus just chaining multiple segments,
   each of which still needs correct per-port grow/shrink.

This is a study of root causes and options, not an implementation. Findings below are each backed
by a specific file:line in the current addon.

## Root causes found (all confirmed by reading the current code, not guessed)

### 1. `_sync_linked_width` always writes the START-side properties, regardless of which end it's syncing

`live_edit._sync_linked_width` (`live_edit.py:383`) is called from `move_dependent_marker`
whenever a segment's linked end tracks an arm's width/lane-count change:

```python
coll["rka_lane_width"] = lane_width
coll["rka_lanes"] = lanes_forward
coll["rka_lanes_backward"] = lanes_backward
```

This is **unconditional** -- it never checks whether the joint it's syncing is the spine's start
(`rka_lanes`/`rka_lanes_backward`, correct) or its end (`rka_lanes_end`/`rka_lanes_backward_end`,
never touched). Only the point **radius** (the visual pavement width) is correctly written to
whichever endpoint control point matches `joint_loc` -- the **custom properties** driving the
actual taper math always land on the start-side keys. So a segment whose *far* end is linked to a
joint gets its `rka_lanes`/`rka_lane_width` silently overwritten with the far joint's values
instead of `rka_lanes_end`/`rka_lanes_backward_end` -- the segment's start and end settle on
whichever joint synced *last*, and a genuine taper never gets recorded at all.

### 2. There is no live way to adjust a segment's END-side lane count, median width, or sidewalk width at all

`RKA_OT_adjust_segment_lanes` (`ops_segment.py:1041`) only ever touches `rka_lanes`/
`rka_lanes_backward`. `RKA_OT_adjust_median_width` (`ops_segment.py:1119`) only touches
`rka_median_width`. **Neither has an `_end` counterpart, and none is exposed in the panel.** The
only way to set `lanes_end`/`lanes_backward_end`/`median_width_end`/`sidewalk_*_width_end` on an
already-built segment is hand-editing the Custom Property in the N-panel, then manually triggering
a rebuild (no button does both) -- there is no discoverable "grow/shrink the far port" workflow at
all today.

**This, combined with #1, is almost certainly the exact bug in report #2**: there's no live control
that could have made "one port grow, one port shrink" happen in the first place, so of course the
mesh didn't change.

### 3. A segment can only ever have ONE end genuinely linked/auto-following -- the far end has no smoothing

`_is_link_dependent_marker` (`ops_intersection.py:1436`) explicitly restricts a valid link
*dependent* to an intersection's `arm_*` or a segment's own **origin marker** (always the spine's
**first** point, stamped in `_build_segment_from_points`). A `port_*` marker -- the segment's other,
far end -- is explicitly excluded from ever being a dependent ("purely derived/cosmetic... making
it the dependent would have no lasting effect"). So:

- A segment's start can auto-follow an arm/port (rigid translate + rotate, `move_dependent_marker`,
  `live_edit.py:411`).
- A segment's **far** end can only ever be dragged freely, or moved to *exactly* match a target's
  position via a one-time `Connect Markers` snap -- never rotated/kept tangent-continuous with
  whatever it's near, and never automatically re-synced again after that snap.

This is the actual mechanism behind report #1. A 2-point (or bent) POLY spine between two
independently-moved endpoints, where only ONE end's *direction* is ever actively kept in sync, is
geometrically going to look "off" / kinked whenever the two ends' natural directions disagree --
that's not really a bug so much as a documented, deliberate scope limit (see the original redesign
plan's Stage 1, "when bridging two intersections... interior control points re-fit... rather than
a naive rigid translate" -- **never implemented**, only the one-end case shipped).

### 4. A segment's pavement/curb cross-section is forced SYMMETRIC even against an asymmetric arm

`Arm.in_width()`/`out_width()` (`intersection_kit.py:167`) are independent (an arm with
`lanes=1, lanes_out=2` has a genuinely lopsided footprint) and the intersection's own pad/curb
already render that correctly (`curb_edges`, `intersection_kit.py:245`, uses both independently).
But `_sync_linked_width`'s pavement radius formula (`live_edit.py:403`) is
`half_w = median_half + max(lanes_forward, lanes_backward, 1) * lane_width` -- **one shared scalar**
-- because `road_spine`'s `GN_RoadProfile` (`kit_common.py:1211`) sweeps a profile `Line` from
`(-1,0,0)` to `(1,0,0)` scaled by ONE per-point `Radius`. That GN node graph is *inherently*
symmetric about the spine -- there is no way to make one side wider than the other without
replacing the node graph. So a segment linked to a lopsided arm always gets a same-width-both-sides
pavement, which can show as a visible step/mismatch right at the joint, independent of angle.

### 5. The yellow center line is painted straight through a raised median

`build_segment_lane_markings` (`intersection_kit.py:899`) always emits a solid "yellow" line at
offset 0 -- it has **no idea a median exists** (`_populate_lane_markings`, `ops_segment.py:1512`,
never passes `median_width` in at all). So a segment with `median_width > 0` gets a real median
curb/wall AND a yellow paint stripe drawn straight through/under it -- physically nonsensical, and
presumably part of what reads as "wrong" about the current median. The actual median-as-mesh
feature (raised BOX/GUTTER wall, or an ASSET row of barrier meshes, shrinkable to 0 via
`RKA_OT_adjust_median_width`) **already exists** (`ops_segment.py:1341` docstring, `curb_loop`-built
`curb_<name>_median_A/B` objects) -- it's just never told to suppress the redundant/wrong paint
line.

## What the GN layer can and can't do here

`GN_RoadProfile` (pavement), `GN_CurbLoop` (curb/median/sidewalk walls), `GN_JunctionPad` (pad) are
all "sweep or fill a boundary the whole width of which is ONE number (or two symmetric numbers) per
spine point." That's sufficient for everything currently built (constant width, one start->end
taper, symmetric cross-section) but is a hard ceiling for:

- A genuinely **asymmetric** cross-section (finding #4).
- A cross-section with an **arbitrary number of independently-sized channels** (N forward lanes +
  a separator channel + M backward lanes, where N/M can vary per point) -- Geometry Nodes has no
  native "list of channels with a per-point-varying count" data type; you'd have to fix a MAX
  channel count and mask unused ones, which is exactly the kind of blind, hard-to-verify node
  graph that's very risky to build without a GUI to look at (all verification in this environment
  is headless -- vertex-position assertions on the evaluated mesh, which *can* catch bugs, but is a
  slow, indirect way to debug new node wiring compared to actually looking at the viewport).
- **Multiple transitions along one spine** (report #3's core ask) -- `road_spine`'s per-point
  `radius` already supports an arbitrary-length taper curve in principle (nothing stops a point in
  the *middle* of a spline from having a different radius than its neighbors), but the *lane
  identity* data (which lane is which, where a lane is born/dies, where the median starts/stops)
  is only ever computed for a start value and an end value (`build_segment_from_spine`'s
  `_transition_lane_pairs`) -- there's no data model for "at t=0.3 along this spine, insert a new
  lane" today, in GN or otherwise.

None of this is a Geometry Nodes bug -- it's that GN was adopted for exactly one reason (live
Edit-Mode point drags updating pavement shape with zero Python involvement, `road_spine`'s own
docstring), and that reason **already doesn't hold** for anything else in this addon: curbs,
median walls, sidewalks, markings, and now the export-time collision proxies are ALL plain Python
mesh generation, re-run on every rebuild via the SAME depsgraph hook that would also need to fire
for a "recompute pavement in Python" step. Editing a spine's control points in Edit Mode already
triggers a full `rebuild_segment_gn_in_place` (`dirty_curve_names` -> `_pending_curve_seg`,
`live_edit.py:265`) -- the pavement is the *only* piece still leaning on GN's own live recompute,
and it's a ~0.2s-debounced Python rebuild away from not needing to.

## Two ways to give report #3 what it's asking for

### Option A -- one continuous spine, N transitions, richer per-point profile data

Replace the single per-point `radius` (pavement) + the handful of independently-computed offset
lines (curbs/median/sidewalks, always start/end only) with **one explicit per-point cross-section
profile**: a list of "channels" (each a lane or a separator, with a width and, for a separator, a
style) attached to EVERY control point (or to specific control points, with the addon interpolating
between the nearest two "profile keyframes" along the spine the same way `offset_spine_line_tapered`
already blends two numbers by arc length -- just generalized from 2 keyframes to N). Rendering
would move OFF Geometry Nodes and onto the exact same Python quad-strip / update-in-place technique
`flat_ribbon`/`swept_wall`/`marking_ribbon` already use (proven safe this session) -- computing each
channel's own left/right rail via `offset_spine_line_tapered` per channel, joining them into one
mesh (or leaving them separate per-channel objects, if per-lane materials/markings are wanted).

**What this buys:** a single object can genuinely narrow from 3 lanes to 1 and back to 2, with a
median that appears/disappears partway along, with no visible seam -- because there IS no seam,
it's one continuous piece.

**What this costs:** this is a real rewrite of the segment data model (`rka_lanes`/`rka_lanes_end`
becomes a profile list; `build_segment_from_spine` gets rewritten around N keyframes instead of 2;
every consumer of the current shape -- `_populate_segment_mesh_gn`, the marking builder, the
`.lanekit.json` export, `WorldBaker`'s Godot-side reader -- needs updating for the new shape).
Multi-session-sized work, and the riskiest part (whatever replaces `GN_RoadProfile`) is exactly the
part hardest to verify without a GUI.

### Option B -- keep segments as the taper unit, fix the four concrete bugs above, chain segments for multiple transitions

A segment already supports ONE clean start->end taper (lane count, median, sidewalk, all
independently) via the existing TAPERED PATH in `build_segment_from_spine`
(`intersection_kit.py:1037`) -- that code looks correct on inspection; it's simply never being fed
real end-side values (bugs #1/#2) and never solving both ends' geometry at once (bug #3). Fixing
those turns "chain three segments end to end" into a fully working way to get 2+ transitions along
one logical road, using machinery that already exists:

- Fix #1 (`_sync_linked_width` writes the wrong end) -- a scoped, mechanical fix: know which end
  (start vs. end) `joint_loc` matched and write the corresponding property pair.
- Fix #2 (no live end-side adjust) -- add `RKA_OT_adjust_segment_lanes`/`RKA_OT_adjust_median_width`
  `_end` siblings (or an `end: BoolProperty` on the existing ones) and wire them into the panel next
  to the existing start-side rows. Small, additive, same pattern as everything already there.
- Fix #3 (no dual-end solve) -- the real design work: let a segment's **far** port also become a
  genuine link dependent (lift `_is_link_dependent_marker`'s restriction), and when a piece has
  BOTH ends linked, solve position+tangent+width at both ends at once instead of one rigid
  translate-from-one-anchor -- e.g. re-fit the interior control points by blending each one's
  offset-from-the-original-chord by its own arc-length fraction (the same interpolation primitive,
  `_arc_length_fractions`, already used everywhere else in this module) rather than a single rigid
  transform. This is the one piece of Option B that's still genuinely new design, but it's scoped
  to "one function," not a whole data-model rewrite.
- Fix #4 (yellow line through median) -- pass median half-width (start/end) into
  `build_segment_lane_markings` and skip the offset-0 yellow line whenever the median is nonzero at
  that point; only emit it where there's no physical median to draw it through.
- Fix #5 (asymmetric arm -> symmetric pavement) -- lower priority / cosmetic-only (the mismatch is
  usually hidden by the curb walls sitting on top of the pavement); can be addressed later by
  widening the pavement's radius to `max(in, out)` at a linked joint (a small over-generation
  hidden under whichever side's curb sits further out) without touching GN at all.

**What this buys:** every one of the four/five concrete, reported problems gets fixed by something
scoped and independently testable (matching this session's existing headless-smoketest discipline),
reusing 100% of the current architecture. "Multiple transitions" becomes "place another `Build
Straight Segment`/`Extend From Port` and taper it too" -- more objects, but each joint is now
correct, and the object-count concern already has an answer in the existing `join_visual_mesh`
flag if a chain needs to end up as one mesh for Godot's sake.

**What this costs:** a long road with many transitions is visibly a chain of separate pieces during
authoring (though not necessarily in the final baked/joined mesh) -- and per-segment collision/port
markers add UI clutter for a very granular chain. No new node graphs, no export-format changes,
much smaller and much more verifiable.

## Recommendation

**Do Option B.** It fixes every concretely-reported symptom (all five root causes trace to real,
scoped bugs/gaps, not to a fundamental GN limitation) with low-risk, independently-testable
changes matching the pattern already validated repeatedly this session, and it does not touch the
`.lanekit.json` export contract or `WorldBaker` at all. Option A is a legitimate longer-term
upgrade *specifically* for "one continuous object with no interior seams," but nothing reported so
far actually requires that -- it should be revisited only if, after Option B ships, a chained-
segment road still visibly reads as "chained" in a way that matters (e.g., for a very long road
with frequent lane changes where per-piece port markers/join seams are themselves the complaint).

## Decisions made (2026-08)

1. **Option A vs. B**: B, with A explicitly deferred (see "Status" above).
2. **Median resize semantics**: keep the current behavior (growing `median_width` widens the total
   road footprint; shrinking back to 0 already worked via `RKA_OT_adjust_median_width`'s negative
   delta). No change made here.
