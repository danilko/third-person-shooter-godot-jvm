#!/usr/bin/env python3
"""migrate_district_5_1_lanekit.py -- ONE-SHOT migration script (road_blender_godot.md P6.7):
rebuilds District_industry_5_1's internal streets as road_kit_authoring pieces from the data
already captured in its `.roads.json` sidecar (4 hand-drawn `road_*` curves: `road_spine`
arterial, `road_north_st` local -- these two share an exact point, a real 3-way junction --
`road_se_st` and `road_sw_ave`, two standalone local streets with no junction), then clears the
OLD road_graph.py-generated `lane_*`/`intersection_*` Empties (206 objects in `MARKERS`) so the
next export/bake doesn't carry both traffic networks at once.

Per the user's explicit instruction ("try 5_1 with automatic setup first, will then try to
handcraft update later"), this is a first-pass AUTOMATIC reconstruction, not a pixel-perfect
recreation -- lane widths/curb style use the addon's own operator defaults (this district's
`.roads.json` never captured that visual detail in the first place, only lane COUNT/class/
oneway/median), and the new pieces are meant to be hand-tuned afterward, not treated as final.

New pieces are built into a `MANUAL` collection (survives a future `build_district.py` config-
name regen, unlike `STREET`/`MARKERS`/`ROADS_SRC` -- though the intent going forward is the
STEM-FORM bake-only workflow, `tools/build_piece.sh District_industry_5_1`, same as any other
hand-edited district). `ROADS_SRC`'s original curves are left untouched (reference/backup,
already excluded from export by convention).

RUN (from a fresh Blender session, saves the .blend in place):
    blender assets/world_source/districts/District_industry_5_1.blend --background \
        --python-exit-code 1 --python assets/world_source/tools/migrate_district_5_1_lanekit.py
"""
import json
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
BP = os.path.dirname(HERE)                        # assets/world_source
sys.path.insert(0, os.path.join(BP, "lib"))
sys.path.insert(0, os.path.join(BP, "addons"))

import road_kit_authoring as rka                              # noqa: E402
from road_kit_authoring import ops_intersection as opint       # noqa: E402
from road_kit_authoring import ops_segment as opseg            # noqa: E402
import kit_common as kc                                        # noqa: E402

LANE_SURFACE_Z = 0.15   # matches RKA_SceneSettings.lane_surface_z default
LANE_WIDTH = 5.0        # matches RKA_OT_build_intersection/RKA_OT_build_straight_segment defaults
KERB_RADIUS = 6.0       # smaller than the 9.0 default -- this district's points are close together
TAIL_LENGTH = 8.0       # starting value; auto-grows via recommended_tail_length if geometry needs it
ARM_LANES = 2           # both road_spine and road_north_st are 2 lanes/direction


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _lift(pt):
    """(x, y, z) -> (x, y, z + LANE_SURFACE_Z) -- puts a raw .roads.json point on the same
    driving-surface baseline road_kit_authoring's own geometry sits on (its `cursor` convention
    always adds `lane_surface_z` on top of a raw position -- see build_intersection_geometry's
    and build_segment_geometry's docstrings)."""
    return (pt[0], pt[1], pt[2] + LANE_SURFACE_Z)


def main():
    context = bpy.context
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    roads_json = os.path.join(BP, "districts", "District_industry_5_1.roads.json")
    with open(roads_json) as f:
        data = json.load(f)
    curves = {c["name"]: c for c in data["curves"]}
    _assert(set(curves) == {"road_spine", "road_north_st", "road_se_st", "road_sw_ave"},
            "unexpected curve set in %s: %r" % (roads_json, sorted(curves)))

    spine_pts = curves["road_spine"]["points"]
    north_pts = curves["road_north_st"]["points"]
    se_pts = curves["road_se_st"]["points"]
    sw_pts = curves["road_sw_ave"]["points"]

    # The shared junction point -- confirmed exact (not just close) in road_blender_godot.md's own
    # inspection of this sidecar: road_north_st's LAST point equals road_spine's INTERIOR point 5.
    junction = tuple(north_pts[-1])
    spine_junction_idx = next(i for i, p in enumerate(spine_pts) if tuple(p) == junction)
    _assert(spine_junction_idx not in (0, len(spine_pts) - 1),
            "expected the junction to be an INTERIOR point of road_spine, got index %d of %d"
            % (spine_junction_idx, len(spine_pts)))
    print("MIGRATE: junction at %s (road_spine index %d, road_north_st's last point)"
          % (junction, spine_junction_idx))

    spine_west_remaining = spine_pts[:spine_junction_idx][::-1]   # near-to-far from junction
    spine_east_remaining = spine_pts[spine_junction_idx + 1:]     # already near-to-far
    north_remaining = north_pts[:-1][::-1]                        # near-to-far from junction

    def bearing(to_pt):
        dx, dy = to_pt[0] - junction[0], to_pt[1] - junction[1]
        return math.degrees(math.atan2(dy, dx)) % 360.0

    angle_west = bearing(spine_west_remaining[0])
    angle_east = bearing(spine_east_remaining[0])
    angle_north = bearing(north_remaining[0])
    print("MIGRATE: arm bearings -- west=%.1f east=%.1f north=%.1f"
          % (angle_west, angle_east, angle_north))

    manual = kc.get_coll("MANUAL")

    # ── 1. The one real junction (road_spine <-> road_north_st) ─────────────────────────────
    result = opint.build_intersection_geometry(
        context, manual, cursor=junction, preset='NWAY', rotation_deg=0.0, side_angle=90.0,
        arm_angles_str="%.4f,%.4f,%.4f" % (angle_west, angle_east, angle_north),
        lane_width=LANE_WIDTH, lanes=ARM_LANES, lane_arm_overrides="", kerb_radius=KERB_RADIUS,
        tail_length=TAIL_LENGTH, segments=8, curb_style='BOX', curb_height=0.15,
        curb_thickness=0.25, lane_map=None, join_visual_mesh=False, export_path="",
        gltf_export_path="", traffic_side='LEFT')
    eff_tail = result["tail_length"]
    print("MIGRATE: built intersection '%s' (%d arms, effective tail_length=%.2f)"
          % (result["coll"].name, len(result["arms"]), eff_tail))
    if eff_tail > TAIL_LENGTH + 1e-3:
        print("MIGRATE: NOTE tail_length auto-grew %.2f -> %.2f for wide arms"
              % (TAIL_LENGTH, eff_tail))

    # Arm A/B/C == west/east/north IN THAT ORDER -- preset_nway names arms alphabetically in the
    # same order as the angles string, which we built as (west, east, north) above.
    arm_names = {"west": "A", "east": "B", "north": "C"}
    arm_ports = {}
    for label, letter in arm_names.items():
        marker = result["coll"].objects.get("arm_%s" % letter)
        _assert(marker is not None, "missing arm marker for %s (%s)" % (label, letter))
        arm_ports[label] = tuple(marker.location)
    print("MIGRATE: arm ports -- %s" % arm_ports)

    # ── 2. Segments extending from each arm, following the ORIGINAL curve's remaining points ──
    def build_arm_segment(label, remaining_pts, lanes, base_name):
        spine = [arm_ports[label]] + [_lift(p) for p in remaining_pts]
        seg = opseg._build_segment_from_points(
            context, manual, spine, LANE_WIDTH, lanes, lanes, 'BOX', 'BOX', 0.15, 0.25,
            False, "", "", base_name=base_name, traffic_side='LEFT')
        print("MIGRATE: built segment '%s' (%d pts) for %s arm"
              % (seg["coll"].name, len(spine), label))
        return seg

    build_arm_segment("west", spine_west_remaining, curves["road_spine"]["lanes"], "Segment_spine_W")
    build_arm_segment("east", spine_east_remaining, curves["road_spine"]["lanes"], "Segment_spine_E")
    build_arm_segment("north", north_remaining, curves["road_north_st"]["lanes"], "Segment_north_st")

    # ── 3. Standalone streets (no junction involved) ─────────────────────────────────────────
    def build_standalone(name, pts, lanes, base_name):
        spine = [_lift(p) for p in pts]
        seg = opseg._build_segment_from_points(
            context, manual, spine, LANE_WIDTH, lanes, lanes, 'BOX', 'BOX', 0.15, 0.25,
            False, "", "", base_name=base_name, traffic_side='LEFT')
        print("MIGRATE: built standalone segment '%s' (%d pts) for %s" % (seg["coll"].name, len(spine), name))

    build_standalone("road_se_st", se_pts, curves["road_se_st"]["lanes"], "Segment_se_st")
    build_standalone("road_sw_ave", sw_pts, curves["road_sw_ave"]["lanes"], "Segment_sw_ave")

    # ── 4. Clear the OLD road_graph.py-generated markers so export doesn't double up ─────────
    markers = bpy.data.collections.get("MARKERS")
    if markers is not None:
        old_count = len(markers.objects)
        removed = 0
        for o in list(markers.objects):
            if o.name.startswith("lane_") or o.name.startswith("intersection_"):
                bpy.data.objects.remove(o, do_unlink=True)
                removed += 1
        print("MIGRATE: cleared %d/%d old road_graph.py marker(s) from MARKERS" % (removed, old_count))

    bpy.ops.wm.save_mainfile()
    print("MIGRATE: saved. Next: tools/save_lane_kit.py, then rebake via "
          "tools/build_piece.sh District_industry_5_1.")


if __name__ == "__main__":
    main()
