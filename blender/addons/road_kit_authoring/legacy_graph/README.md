# legacy_graph — the mesh-graph road model, archived

**Not imported. Not registered. Kept for reference only.**

This is the second of the three road-authoring models this addon has had:

| | model | cross-section lives on | fate |
|---|---|---|---|
| 1 | per-piece generators (`ops_intersection`, `ops_segment`, …) | the piece | **deleted** at step 7 |
| 2 | mesh graph — vertex = node, edge = segment (`graph_*.py`, here) | the **edge domain** | archived here |
| 3 | point/port graph (`point_*.py`) | the **station** | current |

## Why it was replaced

The edge domain stores ONE constant cross-section per segment. A real road changes along its
length, so every such change had to be bought back as a special case bolted onto that constant —
`lane_transition_length`, `aux_taper_length`, `aux_buffer_length`, `derived_offsets`,
`taper_breakpoints`, `aux_scale_keys`, `align_ramp_ends`, `merge_corridor_ends` (192 lines,
59 branches), `ramp_candidates` (277 lines), `auto_aux_lanes`, `ramp_plan`, `ramp_services`, and
the constants `AUX_WEAVE_HOLD`, `AUX_TAPER_MIN_LENGTH`, `AUX_MERGE_BUFFER`, `RAMP_WALL_OPEN`,
`MERGE_WALL_GAP`, `MERGE_WALL_MAX_FRACTION`, `MERGE_JOINT_MAX`, `RAMP_OVERSHOOT`,
`JOIN_OVERSHOOT`, `ALIGN_BLEND_LENGTH`, `NOSE_MAX_CHAIN_FRACTION`, `RAMP_SIDE_WINDOW`.

Every one of them expresses *"the cross-section is different here than it is there"* — which is
free once the cross-section lives on a **station**. Two further consequences: ramp connectivity was
*inferred* from distance rather than authored, and the network presented as 1619 identical grey
edges you could not select or read.

See `blender/ROAD_POINT_GRAPH.md` for the model that replaced it.

## What survived, and where it went

- **`graph_nodes.py` → `point_nodes.py`.** The one part of this model that never knew anything
  about it: every node group reads named per-point attributes off a polyline carrier. Ported, not
  rewritten, so three measured facts survive — `Curve to Mesh`'s `Scale` being the only real
  per-point width, the profile-orientation rotation that keeps kerbs from building inside-out, and
  the interface-version stamp that stops a cached group swallowing a new socket.
- **`graph_build.stack_spec` → `point_build.surface_spec` / `edge_spec`**, split in two because
  the kerb now rides the outline rather than the centreline.
- **`graph_edges.outline` → `point_edges`**, with the boundary walk replaced (see that module's
  docstring for the decision and why a polygon clipper turned out not to be needed).
- **`legacy/ops_ground.py`'s boolean cut → `point_build.cut_ground`**, now part of `Build All`
  rather than a panel button the bake pipeline never called — the confirmed root cause of the
  "mesh holes" reports.

`blender/lib/` is untouched. `lane_profile.py` still owns the cross-section, `intersection_kit.py`
still owns junction geometry, and `road_graph_solve.py` is still here as pure Python.

## tools/

`island_v3_to_graph.py` and `ramp_merge_testbed.py` drove this model and moved with it. They are
the record of how the island was generated on the mesh graph; the point/port replacement is
`island_v3_to_points.py`, which does not exist yet.
