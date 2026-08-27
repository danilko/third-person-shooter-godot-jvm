"""Step 2's acceptance test: build the step-1 testbed scene PURELY through operators, headless.

    blender --background --python-exit-code 1 \
            --python blender/addons/road_kit_authoring/smoketest_point_ops.py

`--python-exit-code 1` MUST come before `--python`, or a crash in here exits 0 and the test
silently "passes" -- a trap this repo has already paid for once.

Every assertion is on an INVARIANT, never on an object name, except where the name IS the thing
being tested (chain order is name order).
"""

import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "blender", "lib"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "lib"))

from road_kit_authoring import point_model as pm         # noqa: E402
from road_kit_authoring import point_ops as po           # noqa: E402
from road_kit_authoring import point_validate as pv      # noqa: E402


def _wipe():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


def _sel(*objs):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[-1]


def _coll(name):
    return pm._local(bpy.data.collections, name)


def _pts(name):
    return po.points_in(_coll(name))


def build_through_operators():
    """The same scene as `point_validate.build_testbed()`, but every edit is an operator call."""
    _wipe()

    # -- the 6-point mainline, by New Road + Extend Road -----------------------------------------
    bpy.ops.rka.new_road(name="road_main", x=0.0, y=0.0, lanes_fwd=2, lanes_bwd=2,
                         median_width=1.0, road_class="arterial", design_speed=50.0)
    for dx in (120.0, 116.0, 28.0, 216.0, 120.0):
        bpy.ops.rka.extend_road(use_delta=True, dx=dx)
    mp = _pts("road_main")
    assert len(mp) == 6, mp

    # -- the cross street --------------------------------------------------------------------
    bpy.ops.rka.new_road(name="road_cross", x=250.0, y=-150.0, lanes_fwd=1, lanes_bwd=1,
                         median_width=0.0, road_class="street")
    for dy in (136.0, 28.0, 136.0):
        bpy.ops.rka.extend_road(use_delta=True, dy=dy)
    cp = _pts("road_cross")
    assert len(cp) == 4, cp

    # -- the 4-arm pad. The two mainline mouths are ADJACENT members of one 6-point chain: a
    #    crossing does not split the street.
    _sel(mp[2], mp[3])
    bpy.ops.rka.disconnect_selected()
    _sel(cp[1], cp[2])
    bpy.ops.rka.disconnect_selected()
    _sel(mp[2], mp[3], cp[1], cp[2])
    bpy.ops.rka.make_intersection(fillet_radius=6.0)

    # -- the ramp ------------------------------------------------------------------------------
    bpy.ops.rka.new_road(name="ramp_e", x=480.0, y=40.0, lanes_fwd=1, lanes_bwd=0,
                         median_width=0.0, road_class="ramp")
    bpy.ops.rka.extend_road(use_delta=True, dx=140.0, dy=29.0)
    rr = _pts("ramp_e")
    _sel(rr[0], mp[4])                      # active = the MAINLINE point
    bpy.ops.rka.make_ramp(role=pm.RAMP_EXIT, aux_lanes=1, align=True)
    return mp, cp, rr


def main():
    # The repo addon is symlinked into Blender's addons dir and auto-enables, so it is normally
    # ALREADY registered by the time this runs. Register only if it is not.
    if not hasattr(bpy.types, "RKA_OT_validate"):
        po.register()
    ok = 0
    mp, cp, rr = build_through_operators()

    net = pm.read_network()
    findings = pv.validate(net)
    if pv.errors(findings):
        pv.report(findings)
    assert not pv.errors(findings), "a scene built entirely by operators must gate GREEN"
    assert len(net.roads) == 3 and len(net.points) == 12, (len(net.roads), len(net.points))
    print("OK: New Road / Extend Road / Make Intersection / Make Ramp build a green network")
    ok += 1

    # -- the crossing did NOT split the street --------------------------------------------------
    assert len(net.roads["road_main"].points) == 6, "a junction sits INSIDE a chain (defect 3)"
    cliques = net.junction_cliques()
    assert len(cliques) == 1 and len(cliques[0]) == 4, cliques
    jct = [o for o in bpy.data.objects if o.name.startswith("JCT_")]
    assert len(jct) == 1 and tuple(jct[0].lock_rotation) == (True, True, True), \
        "the JCT parent's rotation and scale must be locked, or a stray R rescales every mouth"
    arms = [o for o in bpy.data.objects if o.rka_pt.is_point and o.parent is jct[0]]
    assert len(arms) == 4
    # The parent owns position, and `matrix_parent_inverse` was set by hand -- without it every
    # mouth jumps by the parent's offset (here (250, 0)) the moment it is parented.
    want = {(236.0, 0.0), (264.0, 0.0), (250.0, -14.0), (250.0, 14.0)}
    got = {(round(o.matrix_world.translation.x, 3), round(o.matrix_world.translation.y, 3))
           for o in arms}
    assert got == want, "parenting must not move a mouth: %s" % sorted(got)
    print("OK: 4 arms parented to one locked JCT_*, positions preserved through parenting")
    ok += 1

    # -- Make Ramp aligned the ramp to the aux slot edge, with no pad ----------------------------
    ramp0 = _pts("ramp_e")[0]
    assert ramp0.rka_pt.role == pm.RAMP_EXIT and ramp0.rka_pt.lanes_bwd == 0
    main4 = _pts("road_main")[4]
    assert main4.rka_pt.aux_fwd == 1, "the MAINLINE point owns the aux slot"
    # The GORE LINE is the aux slot's THROUGH-LANE edge (y = 7.5 here: median 0.5 + F0 3.5 +
    # F1 3.5), not its outboard edge -- so the aux slot IS the exit lane and the ramp continues
    # it, rather than the ramp being a fifth lane beyond a deceleration lane that rejoins.
    assert abs(ramp0.matrix_world.translation.y - 7.5) < 1e-3, \
        "the ramp mouth lands on the gore line at y = 7.5, got %.3f" % (
            ramp0.matrix_world.translation.y,)
    # ...and it FACES DOWN THE MAINLINE, so the two cross-sections are cut on the same plane.
    facing = pm.facing_of(ramp0)
    assert facing is not None and abs(facing[0] - 1.0) < 1e-3 and abs(facing[1]) < 1e-3, \
        "Align Ramp To Aux faces the mouth down the mainline, got %r" % (facing,)
    assert ramp0.rka_pt.tangent_mode == pm.MANUAL, "that facing is pinned, not swept away by Build"
    assert not [f for f in findings if f.code.startswith("ramp_")]
    print("OK: Make Ramp opens the aux slot, writes the AUX link, and aligns mouth AND facing")
    ok += 1

    # -- Insert Point must change NOTHING ---------------------------------------------------------
    _sel(_pts("road_main")[0], _pts("road_main")[1])
    bpy.ops.rka.insert_point(t=0.5)
    after_pts = _pts("road_main")
    assert len(after_pts) == 7
    assert [o.name for o in after_pts] == [po.point_name(_coll("road_main"), i)
                                           for i in range(7)], \
        "chain order IS name order -- an inserted point must renumber, not append"
    net2 = pm.read_network()
    assert not pv.errors(pv.validate(net2)), "inserting a point must not break the gate"
    assert len(net2.roads["road_main"].points) == 7
    print("OK: Insert Point splits the link, interpolates the profile and renumbers the chain")
    ok += 1

    # -- Delete Point strips inbound links --------------------------------------------------------
    victim = _pts("road_main")[1]
    _sel(victim)
    bpy.ops.rka.delete_point()
    net3 = pm.read_network()
    codes = {f.code for f in pv.errors(pv.validate(net3))}
    assert "link_dangling" not in codes, "deletion must leave no dangling reference"
    # The hole IS reported: the point left joined to nothing is an ERROR under its own name, and
    # the seam it leaves in the chain is a WARN (a road that splits into two runs still builds).
    assert "point_stranded" in codes, codes
    assert "chain_unlinked" in {f.code for f in pv.validate(net3)}, "reported, as a warning"
    assert len(_pts("road_main")) == 6
    # Repair by re-linking across the hole, exactly as `Connect Selected` would.
    m = _pts("road_main")
    _sel(m[0], m[1])
    bpy.ops.rka.connect_selected(type=pm.LINK_SEGMENT)
    assert not pv.errors(pv.validate(pm.read_network())), "Connect Selected closes the hole"
    print("OK: Delete Point leaves no zombie and no dangling link; Connect Selected repairs")
    ok += 1

    # -- the mask defaults to NOTHING --------------------------------------------------------------
    m = _pts("road_main")
    _sel(m[5], m[0])
    m[0].rka_pt.lanes_fwd = 4
    # `bpy.ops` turns a reported ERROR into a RuntimeError, so a refusal is caught, not compared.
    try:
        bpy.ops.rka.apply_cross_section()
        raise AssertionError("an empty field mask must refuse, not silently rewrite the median")
    except RuntimeError as exc:
        assert "mask defaults to nothing" in str(exc), exc
    assert m[5].rka_pt.lanes_fwd == 2
    _sel(m[5], m[0])
    bpy.ops.rka.apply_cross_section(groups={'LANES'})
    assert m[5].rka_pt.lanes_fwd == 4 and m[5].rka_pt.profile_mode == pm.OVERRIDE
    print("OK: Apply Cross-Section refuses an empty mask and copies only the ticked group")
    ok += 1

    # -- the record round-trips, and the Empties are a VIEW of it -----------------------------------
    import tempfile
    path = os.path.join(tempfile.gettempdir(), "rka_smoketest.roads.json")
    bpy.ops.rka.save_record(filepath=path)
    a = pm.network_to_dict(pm.read_network())
    bpy.ops.rka.load_record(filepath=path)
    b = pm.network_to_dict(pm.read_network())
    assert a == b, "the Empties must rebuild from the record byte-identically"
    assert not pv.errors(pv.validate(pm.read_network()))
    os.remove(path)
    print("OK: .roads.json is the source of truth -- the Empties rebuild from it identically")
    ok += 1

    # -- Shift+D on ONE point is caught on the next read --------------------------------------------
    m = _pts("road_main")
    clone = m[2].copy()
    clone.rka_pt.is_point = True
    pm._local(bpy.data.collections, "road_main").objects.link(clone)
    assert clone.rka_pt.uid == m[2].rka_pt.uid, "Object.copy() deep-copies the uid verbatim"
    net4 = pm.read_network()
    assert net4.uid_repairs, "a duplicated uid must be repaired on read, not silently kept"
    old, new, _p = net4.uid_repairs[0]
    assert old == m[2].rka_pt.uid and new != old
    assert not net4.points[new].links, "the clone's links describe the ORIGINAL's connectivity"
    bpy.data.objects.remove(clone, do_unlink=True)
    print("OK: Shift+D on a single point is detected and repaired on the next read")
    ok += 1

    # -- ...and duplicating a WHOLE ROAD keeps its own wiring, and orphans nothing --------------
    # THE USER REPORT (8j). Copying a road collection is the obvious way to author a second ramp,
    # and it produced five `point_orphan: <the copy> -- point belongs to no road collection`
    # errors on points plainly sitting in a road collection, plus a copy with every internal link
    # gone. Two defects, one cause: uids collide, and BOTH road-membership and link resolution
    # were keyed on the uid.
    src = pm._local(bpy.data.collections, "road_main")
    dup = bpy.data.collections.new("road_main_copy")
    pm._local(bpy.data.collections, pm.ROAD_MANAGER).children.link(dup)
    dup.rka_road.is_road = True
    copies = {}
    for o in _pts("road_main"):
        c = o.copy()
        c.rka_pt.is_point = True
        dup.objects.link(c)
        copies[o] = c
    # Blender's own ID-remap does this for a real duplicate; done by hand here because
    # `bpy.ops.object.duplicate` needs a view-layer selection that `--background` will not give.
    for o, c in copies.items():
        for l in c.rka_pt.links:
            if l.target in copies:
                l.target = copies[l.target]
    net5 = pm.read_network()
    assert len(net5.uid_repairs) == len(copies), net5.uid_repairs
    codes = {f.code for f in pv.validate(net5)}
    assert "point_orphan" not in codes, sorted(codes)
    assert "point_stranded" not in codes, sorted(codes)
    # The ORIGINAL keeps every one of its points...
    assert len(net5.roads["road_main"].points) == len(copies), net5.roads["road_main"].points
    assert all(u in net5.points for u in net5.roads["road_main"].points)
    # ...and the COPY is a connected road in its own right, wired to itself and not to the
    # original: a link row inside the duplicated set follows the copies, one leaving it is the
    # clone's inherited connectivity and is dropped.
    own = set(net5.roads["road_main_copy"].points)
    assert len(own) == len(copies) and not (own & set(net5.roads["road_main"].points))
    edges = [(u, l.target) for u in own for l in net5.points[u].links]
    assert edges and all(t in own for _u, t in edges), edges
    for c in copies.values():
        bpy.data.objects.remove(c, do_unlink=True)
    bpy.data.collections.remove(dup)
    print("OK: duplicating a whole road keeps the copy's own wiring and orphans nothing")
    ok += 1

    print("\nALL OPERATOR SMOKETESTS PASSED (%d)" % ok)


if __name__ == "__main__":
    main()
