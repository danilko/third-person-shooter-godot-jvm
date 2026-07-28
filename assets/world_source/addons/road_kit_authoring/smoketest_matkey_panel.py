#!/usr/bin/env python3
"""
smoketest_matkey_panel.py -- headless verification for RKA_OT_set_pavement_matkey/
RKA_OT_set_curb_matkey (2026-07-28, user-reported: "is there a way to change mesh/material for
segment/intersection road/curb etc, seem only allow in F9, but any edit afterward not allow" --
`matkey` was actually a hardcoded Python literal at every build call site, not exposed as an
operator property at all, so there was no way to change it after the fact, full stop). Confirms
the change actually reaches the real material slot on the piece's own visual object(s) -- not just
a stored custom property nobody reads -- for an intersection (pad + curb) and a GN segment
(pavement spine + curb), including the segment's special case: `rebuild_segment_gn_in_place`
deliberately never deletes/recreates the spine object, so its material can't just be picked up by
a normal rebuild the way curb regeneration does.

RUN: blender --background --python addons/road_kit_authoring/smoketest_matkey_panel.py
"""
import bpy
import os
import sys

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


def _gn_mat_name(obj, mod_name, ng_getter):
    """Pad/curb/spine material lives in their GN modifier's Material input (a Set Material node
    inside the node group), not `obj.data.materials` -- these are GN-modifier-backed Curve objects,
    the material only reaches a real mesh material slot once glTF export bakes the modifier."""
    mod = obj.modifiers.get(mod_name)
    if mod is None:
        return None
    _ng, ids = ng_getter()
    mat_id = ids[0]   # every relevant group returns (mat_id, ...) with mat_id first
    return mod[mat_id].name


def _pad_mat_name(obj):
    return _gn_mat_name(obj, "Pad", kc.make_junction_pad_group)


def _curb_mat_name(obj):
    return _gn_mat_name(obj, "Curb", kc.make_curb_loop_group)


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    scene_coll = bpy.context.scene.collection
    context = bpy.context

    # --- Intersection: pad + curb material.
    result = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    coll = result["coll"]
    pad = coll.objects["pad_%s" % coll.name]
    _assert(_pad_mat_name(pad) == "M_Asphalt", "fresh pad should default to asphalt, got %s"
            % _pad_mat_name(pad))

    context.view_layer.objects.active = pad
    ret = bpy.ops.rka.set_pavement_matkey(matkey='concrete')
    _assert(ret == {'FINISHED'}, "set_pavement_matkey did not finish: %s" % (ret,))
    _assert(coll.get("rka_pad_matkey") == 'concrete', "rka_pad_matkey should now be 'concrete'")
    pad_after = coll.objects["pad_%s" % coll.name]   # regenerated object, re-fetch
    _assert(_pad_mat_name(pad_after) == "M_Concrete",
            "pad's real material slot should now be M_Concrete, got %s" % _pad_mat_name(pad_after))
    print("smoketest_matkey_panel: intersection pad material persisted through a rebuild "
          "(asphalt -> concrete), not just stored and ignored")

    curb0 = next(o for o in coll.objects if o.name.startswith("curb_%s_" % coll.name))
    context.view_layer.objects.active = curb0
    ret = bpy.ops.rka.set_curb_matkey(matkey='red')
    _assert(ret == {'FINISHED'}, "set_curb_matkey did not finish: %s" % (ret,))
    curb0_after = next(o for o in coll.objects if o.name.startswith("curb_%s_" % coll.name))
    _assert(_curb_mat_name(curb0_after) == "M_Red",
            "curb's real material slot should now be M_Red, got %s" % _curb_mat_name(curb0_after))
    print("smoketest_matkey_panel: intersection curb material persisted through a rebuild")

    # --- GN segment: pavement (spine) material -- the special case, since rebuild never
    # deletes/recreates the spine object itself.
    seg_result = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 100.0, 0.0), (40.0, 100.0, 0.0)], 5.0, 1, 1,
        'BOX', 'BOX', 0.15, 0.25, False, "", "")
    seg_coll = seg_result["coll"]
    spine = seg_coll.objects["spine_%s" % seg_coll.name]

    def _spine_mat_name(coll_):
        sp = coll_.objects["spine_%s" % coll_.name]
        mod = sp.modifiers.get("Road")
        _ng, (mat_id, _tid) = kc.make_road_profile_group()
        return mod[mat_id].name

    _assert(_spine_mat_name(seg_coll) == "M_Asphalt",
            "fresh segment spine should default to asphalt, got %s" % _spine_mat_name(seg_coll))

    context.view_layer.objects.active = spine
    ret = bpy.ops.rka.set_pavement_matkey(matkey='dirt')
    _assert(ret == {'FINISHED'}, "set_pavement_matkey on a segment did not finish: %s" % (ret,))
    _assert(seg_coll.get("rka_pave_matkey") == 'dirt', "rka_pave_matkey should now be 'dirt'")
    _assert(_spine_mat_name(seg_coll) == "M_Dirt",
            "segment spine's GN modifier material should now be M_Dirt (direct update, since "
            "rebuild never recreates the spine object), got %s" % _spine_mat_name(seg_coll))
    print("smoketest_matkey_panel: GN segment pavement material updated directly on the live "
          "spine modifier (the special case rebuild alone can't handle)")

    seg_curb = next(o for o in seg_coll.objects if o.name.startswith("curb_%s_" % seg_coll.name))
    context.view_layer.objects.active = seg_curb
    ret = bpy.ops.rka.set_curb_matkey(matkey='trim')
    _assert(ret == {'FINISHED'}, "set_curb_matkey on a segment did not finish: %s" % (ret,))
    seg_curb_after = next(o for o in seg_coll.objects
                           if o.name.startswith("curb_%s_" % seg_coll.name))
    _assert(_curb_mat_name(seg_curb_after) == "M_Trim",
            "segment curb material should now be M_Trim, got %s" % _curb_mat_name(seg_curb_after))
    print("smoketest_matkey_panel: GN segment curb material persisted through a rebuild")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
