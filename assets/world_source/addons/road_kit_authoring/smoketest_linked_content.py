#!/usr/bin/env python3
"""
smoketest_linked_content.py -- headless verification for P6.3 (road_blender_godot.md): the addon's
own by-name resolution now skips read-only LINKED library content (mirrors kit_common.get_coll()'s
own `.library is None` filter, already relied on elsewhere in the pipeline -- tools/link_neighbors.py
in particular). Without this, road_kit_authoring's deterministic auto-naming (`Segment_%03d`,
`Intersection_<preset>_%03d`) makes a cross-file name collision likely the moment ANOTHER
road_kit_authoring-authored file is linked in read-only (exactly what the P6.5 cross-district
arterial-authoring workflow requires) -- a rebuild could then silently misfire onto the wrong
(linked) object instead of the local one being edited.

Builds a small piece in a throwaway "neighbor" .blend, saves it, then in a FRESH session builds a
LOCAL piece that intentionally collides on name, links the neighbor file's collection in, and
confirms every local-only operation still resolves to -- and only ever mutates -- the local object.

RUN: blender --background --python addons/road_kit_authoring/smoketest_linked_content.py
"""
import bpy
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import road_kit_authoring as rka                          # noqa: E402
from road_kit_authoring import ops_intersection as opint  # noqa: E402
from road_kit_authoring import ops_segment as opseg        # noqa: E402
import kit_common as kc                                     # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    neighbor_path = os.path.join(tempfile.gettempdir(), "rka_smoketest_neighbor.blend")

    # ---- Build the "neighbor" file: a straight segment that will auto-name to "Segment_001",
    # exactly the same name a fresh local file's own first segment would also auto-generate.
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()
    scene_coll = bpy.context.scene.collection
    context = bpy.context
    neighbor_result = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0)], 5.0, 1, 1,
        'BOX', 'BOX', 0.15, 0.25, False, "", "")
    _assert(neighbor_result["coll"].name == "Segment_001",
            "neighbor file's first segment should auto-name to 'Segment_001', got %r"
            % neighbor_result["coll"].name)
    bpy.ops.wm.save_as_mainfile(filepath=neighbor_path)
    print("linked_content smoketest: built neighbor file with 'Segment_001' at %s" % neighbor_path)

    # ---- Fresh session: build a LOCAL segment (also auto-names to "Segment_001" -- this file has
    # never built one before either), THEN link the neighbor's "Segment_001" in read-only.
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()
    scene_coll = bpy.context.scene.collection
    context = bpy.context
    local_result = opseg._build_segment_from_points(
        context, scene_coll, [(100.0, 0.0, 0.0), (140.0, 0.0, 0.0)], 5.0, 1, 1,
        'BOX', 'BOX', 0.15, 0.25, False, "", "")
    local_coll = local_result["coll"]
    _assert(local_coll.name == "Segment_001",
            "local file's first segment should ALSO auto-name to 'Segment_001' (fresh file, no "
            "linked content yet), got %r" % local_coll.name)

    with bpy.data.libraries.load(neighbor_path, link=True) as (data_from, data_to):
        data_to.collections = [c for c in data_from.collections if c == "Segment_001"]
    linked_coll = next(c for c in bpy.data.collections if c.name == "Segment_001" and c.library is not None)
    # Instance it into the scene the way link_neighbors.py/kit_common.instance_collection do, so
    # it's genuinely present (not just an orphaned library datablock).
    inst = bpy.data.objects.new("NeighborRef_Segment_001", None)
    inst.instance_type = 'COLLECTION'
    inst.instance_collection = linked_coll
    scene_coll.objects.link(inst)

    _assert(sum(1 for c in bpy.data.collections if c.name == "Segment_001") == 2,
            "should now have exactly 2 'Segment_001' collections: one local, one linked")
    print("linked_content smoketest: local + linked 'Segment_001' now coexist by exact name")

    # ---- local_collection()/local_object() must resolve to the LOCAL one specifically.
    resolved = opint.local_collection("Segment_001")
    _assert(resolved is local_coll,
            "local_collection('Segment_001') must resolve to the LOCAL collection, not the linked "
            "one -- got %r (library=%r)" % (resolved, resolved.library if resolved else None))
    print("linked_content smoketest: local_collection() correctly resolves to the local collection")

    local_spine = local_coll.objects.get(local_coll["rka_curve_object"])
    resolved_obj = opint.local_object(local_coll["rka_curve_object"])
    _assert(resolved_obj is local_spine,
            "local_object() must resolve the local spine, not a same-named linked one")
    print("linked_content smoketest: local_object() correctly resolves to the local spine")

    # ---- A rebuild/adjust operation on the LOCAL piece must succeed and touch ONLY local data --
    # this would previously have had a real chance of resolving onto the linked collection instead
    # (Python dict-like bpy.data.collections.get() has no defined tie-break between same-named
    # local/linked entries) and either raising (mutating read-only library data) or silently
    # rebuilding the wrong object.
    for o in bpy.data.objects:
        o.select_set(False)
    local_spine.select_set(True)
    context.view_layer.objects.active = local_spine
    ret = bpy.ops.rka.adjust_segment_lanes(delta=1)
    _assert(ret == {'FINISHED'}, "adjust_segment_lanes on the local piece should succeed: %s" % (ret,))
    _assert(local_coll.get("rka_lanes") == 2, "the LOCAL collection's lane count should have "
            "changed, got %s" % local_coll.get("rka_lanes"))
    _assert(linked_coll.get("rka_lanes") == 1, "the LINKED (read-only) collection must be "
            "completely untouched, got %s" % linked_coll.get("rka_lanes"))
    print("linked_content smoketest: adjust_segment_lanes mutated only the local piece; the "
          "linked, read-only neighbor was untouched")

    # ---- A THIRD local segment must auto-name to 'Segment_002', not be perturbed by (or collide
    # with) the linked 'Segment_001' -- proves the auto-naming loop is also local-only.
    third_result = opseg._build_segment_from_points(
        context, scene_coll, [(200.0, 0.0, 0.0), (240.0, 0.0, 0.0)], 5.0, 1, 1,
        'BOX', 'BOX', 0.15, 0.25, False, "", "")
    _assert(third_result["coll"].name == "Segment_002",
            "a third local segment should auto-name to 'Segment_002', got %r"
            % third_result["coll"].name)
    print("linked_content smoketest: auto-naming continues correctly (Segment_002) alongside the "
          "linked 'Segment_001'")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
