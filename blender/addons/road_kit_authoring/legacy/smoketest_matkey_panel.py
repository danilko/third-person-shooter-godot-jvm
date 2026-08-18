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

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_matkey_panel.py
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
    return kc.get_mod_input(mod, mat_id).name


def _pad_mat_name(obj):
    return _gn_mat_name(obj, "Pad", kc.make_junction_pad_group)


def _curb_mat_name(obj):
    return _gn_mat_name(obj, "Curb", kc.make_curb_loop_group)


def _gn_material_name(mod):
    """The material a geometry-nodes modifier is set to, found by SOCKET TYPE on its own node
    group. Type, not a hardcoded identifier: each carrier uses a different group, so an id
    borrowed from another one silently reads whatever shares that identifier there."""
    if mod is None or mod.node_group is None:
        return None
    for sock in mod.node_group.interface.items_tree:
        if getattr(sock, "in_out", None) == 'INPUT' and sock.socket_type == 'NodeSocketMaterial':
            val = kc.get_mod_input(mod, sock.identifier)
            return val.name if val is not None else None
    return None


def _curb_mat_names(coll):
    """The set of materials this piece's CURBS are made of, found by ROLE rather than by the name
    `curb_<piece>_<side>` (`ROAD_KIT_REDESIGN.md` §7 -- a name is a property of the sibling-object
    build path; on the modifier-stack path there is no curb object to name at all).

    "Carries a curb" has one spelling per carrier and this covers both: a sibling-object piece has
    objects with a `Curb` modifier, a stack piece has `CurbL`/`CurbR` LAYERS on its one carrier.

    Read off the GN modifier's Material INPUT, deliberately, not off evaluated geometry -- see the
    note at the top of `lib/piece_probe.py` for why evaluated material access is unusable here
    (dangling slots, and a hard segfault about one run in five)."""
    out = set()
    for o in coll.objects:
        if o.name.endswith("-colonly"):
            continue
        for mod in o.modifiers:
            if mod.type == 'NODES' and mod.name in ("Curb", "CurbL", "CurbR"):
                out.add(_gn_material_name(mod))
    return out - {None}


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
    # 'line_y' (not 'red' -- ROAD_MATKEY_ITEMS is now the curated 5-entry road picker, 2026-08;
    # 'red' isn't a road material and is no longer a valid choice for this operator).
    ret = bpy.ops.rka.set_curb_matkey(matkey='line_y')
    _assert(ret == {'FINISHED'}, "set_curb_matkey did not finish: %s" % (ret,))
    curb0_after = next(o for o in coll.objects if o.name.startswith("curb_%s_" % coll.name))
    _assert(_curb_mat_name(curb0_after) == "M_LineY",
            "curb's real material slot should now be M_LineY, got %s" % _curb_mat_name(curb0_after))
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
        # The PAVEMENT layer, whatever the carrier calls it: a Curve spine sweeps it in a `Road`
        # modifier, a modifier-stack carrier in a `Pavement` one. Same question, two spellings.
        mod = sp.modifiers.get("Road") or sp.modifiers.get("Pavement")
        # The Material socket is found BY TYPE on the modifier's own node group, not by an id
        # borrowed from `make_road_profile_group` -- the two carriers use different node groups,
        # so a hardcoded id reads whatever socket happens to share that identifier (observed:
        # a float, giving `'float' object has no attribute 'name'`). Asking the group itself is
        # also what made the earlier stale-arity bug impossible to reintroduce.
        name = _gn_material_name(mod)
        _assert(name is not None,
                "no Material input on %r's %r modifier" % (sp.name, mod.name))
        return name

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

    # The segment's curbs are found BY ROLE -- "the parts of this piece that carry a curb sweep" --
    # not by the name `curb_<piece>_L` (`ROAD_KIT_REDESIGN.md` §7). See `_curb_mat_names`.
    # The operator resolves the piece from any of its objects, so the spine is a valid target.
    context.view_layer.objects.active = spine
    curb_before = _curb_mat_names(seg_coll)
    _assert(curb_before == {"M_Concrete"},
            "sanity: a fresh BOX curb should be concrete, this piece's curbs use %r"
            % sorted(curb_before))
    # 'line_w' (not 'trim' -- see the 'line_y' note above; 'trim' is a building-kit-only material,
    # no longer offered by the curated ROAD_MATKEY_ITEMS picker).
    ret = bpy.ops.rka.set_curb_matkey(matkey='line_w')
    _assert(ret == {'FINISHED'}, "set_curb_matkey on a segment did not finish: %s" % (ret,))
    seg_coll = opint.local_collection(seg_coll.name)
    curb_after = _curb_mat_names(seg_coll)
    _assert(curb_after == {"M_LineW"},
            "every one of the segment's curbs should now be M_LineW, got %r" % sorted(curb_after))
    _assert(_spine_mat_name(seg_coll) == "M_Dirt",
            "changing the CURB material must not disturb the pavement, which is still 'dirt' from "
            "the step above -- the spine's material is now %s" % _spine_mat_name(seg_coll))
    print("smoketest_matkey_panel: GN segment curb material persisted through a rebuild "
          "(%s -> M_LineW) with the pavement left alone" % sorted(curb_before))

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
