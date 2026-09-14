"""PIPELINE COVERAGE: every registered operator driven, end to end, headless.

    blender --background --python-exit-code 1 \
            --python blender/addons/road_kit_authoring/smoketest_point_coverage.py

Since B9 (PLAN.md 3.1, 2026-09-14) the Blender addon is the headless MODEL half of the Godot Road Kit:
no panel, no overlay, no preview drawing, no live rebuild, and the interactive gestures live in the
Godot plugin and `point_record_ops` (their tests: `point_record_ops.py`'s self-test and
`tools/godot/test_roadkit_b8.gd`). What stays here is what a TOOL drives -- the seeder's New Road,
Extend Road, Connect and Make Intersection, Auto Setback, the build, the record, the lanekit export
and the style kit -- and the coverage assertion at the bottom FAILS if an operator is registered
without being driven, because an operator nothing calls is an operator that does not work (the
previous addon shipped a `Cut Ground Under Road` button the bake never called).
"""

import json
import math
import os
import sys
import tempfile

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "blender", "lib"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "lib"))

import lane_profile as lp                                                    # noqa: E402
from road_kit_authoring import point_build as pb                             # noqa: E402
from road_kit_authoring import point_model as pm                             # noqa: E402
from road_kit_authoring import point_ops as po                               # noqa: E402
from road_kit_authoring import point_flow as pflow                           # noqa: E402
from road_kit_authoring import point_record_ops as ro                        # noqa: E402
from road_kit_authoring import point_export as pe3                           # noqa: E402
from road_kit_authoring import point_style as pstyle                         # noqa: E402
from road_kit_authoring import point_solve as ps                             # noqa: E402
from road_kit_authoring import point_validate as pv                          # noqa: E402

#: Every operator this file drives. Compared against what is actually registered, at the end.
DRIVEN = set()
#: The sample network, as committed. It was authored by the gestures `Add Sample Network` drove, and
#: the record is what survives them (B9).
SAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))),
                      "assets", "world_source", "pieces", "RoadKitSample.roads.json")

def check(msg):
    print("OK:", msg)


def run(idname, **kw):
    """Call an operator by id and record that it was driven."""
    DRIVEN.add(idname)
    op = bpy.ops
    for part in idname.split("."):
        op = getattr(op, part)
    return op(**kw)


def _wipe():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


def _sel(*objs, active=None):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or (objs[0] if objs else None)


def _pts(name):
    return po.points_in(pm._local(bpy.data.collections, name))


class _Ctx(object):
    """The two attributes `resolve_pair` reads. A real selection would do, but naming the active
    object explicitly is what the assertion is ABOUT -- so it is passed, not inferred."""

    def __init__(self, sel, active):
        self.selected_objects = list(sel)
        self.active_object = active


def _ctx_sel(*objs, active=None):
    return _Ctx(objs, active)



def _unlink(a, b):
    """Both rows of a pair -- what the retired Disconnect Selected wrote."""
    for x, y in ((a, b), (b, a)):
        for i in range(len(x.rka_pt.links) - 1, -1, -1):
            if x.rka_pt.links[i].target is y:
                x.rka_pt.links.remove(i)


def _flow():
    """The flow report over what the scene exports (`point_flow`, the one owner)."""
    return pflow.flow_report(pe3.export_network(pm.read_network()))


# ---------------------------------------------------------------------------------- the test

def _all_objects(coll, acc=None):
    """Every object under a collection, recursively -- generated geometry is nested per road."""
    acc = [] if acc is None else acc
    if coll is None:
        return acc
    acc += list(coll.objects)
    for child in coll.children:
        _all_objects(child, acc)
    return acc



def main():
    ok = 0
    _wipe()
    if not hasattr(bpy.types, "RKA_OT_point_build"):
        import addon_utils
        addon_utils.enable("road_kit_authoring", default_set=False, persistent=False)

    # ================================================================= A. corridor authoring
    run("rka.new_road", name="main", x=0.0, y=0.0, lanes_fwd=2, lanes_bwd=2,
        lane_width=3.5, median_width=1.0, road_class="arterial", design_speed=60.0)
    main = pm._local(bpy.data.collections, "main")
    assert main is not None and main.rka_road.is_road
    for _ in range(4):
        _sel(_pts("main")[-1])
        run("rka.extend_road", use_delta=True, dx=140.0, dy=0.0, dz=0.0)
    mp = _pts("main")
    assert len(mp) == 5, [o.name for o in mp]
    assert all(o.name.startswith("main_p") for o in mp), [o.name for o in mp]
    check("New Road + Extend Road: a 5-point chain, road-prefixed so name order IS chain order")
    ok += 1


    # -- Extend Road works from the HEAD too, and prepends ----------------------------------------
    # It used to append unconditionally: the new point took the name at the FAR end of a road it
    # sits at the start of, and (with no `prev` to take a chord from) grew forward, back down the
    # road. Both halves showed up as `chain_unlinked` on an untouched pair the next time you built.
    head_before = _pts("main")[0]
    x0 = head_before.matrix_world.translation.x
    _sel(head_before)
    run("rka.extend_road", distance=120.0)
    mp = _pts("main")
    assert len(mp) == 6, [o.name for o in mp]
    assert mp[1] is head_before, "the new point must sort BEFORE the old head"
    assert mp[0].matrix_world.translation.x < x0 - 100.0, mp[0].matrix_world.translation.x
    assert mp[0].rka_pt.links[0].target is head_before
    net = pm.read_network()
    assert not [f for f in pv.errors(pv.validate(net)) if f.code in ("chain_unlinked",
                                                                     "point_stranded")], \
        "extending the head must leave the chain in order, buildable with no repair"
    # ...and an INTERIOR point is refused by name rather than silently picking an end.
    _sel(mp[3])
    try:                       # bpy.ops raises on an ERROR report, which is the refusal
        run("rka.extend_road", distance=50.0)
        raise AssertionError("extending an interior point must be refused")
    except RuntimeError as exc:
        assert "middle of" in str(exc), exc
    assert len(_pts("main")) == 6
    check("Extend Road grows from EITHER end -- prepends at the head, appends at the tail")
    ok += 1

    # A second road, crossing the first.
    run("rka.new_road", name="cross", x=300.0, y=-200.0, lanes_fwd=1, lanes_bwd=1,
        lane_width=3.5, median_width=0.0, road_class="street")
    for dy in (170.0, 60.0, 170.0):
        _sel(_pts("cross")[-1])
        run("rka.extend_road", use_delta=True, dx=0.0, dy=dy, dz=0.0)
    cp = _pts("cross")
    assert len(cp) == 4

    # ================================================================= D. ramp (the record gesture)
    # Make Ramp is `point_record_ops.make_ramp` now; a tool applies it to the read network and
    # projects the record back. Done BEFORE the junction, because the projection rebuilds the Empties.
    run("rka.new_road", name="ramp", x=760.0, y=40.0, lanes_fwd=1, lanes_bwd=0,
        lane_width=3.5, median_width=0.0, road_class="ramp")
    _sel(_pts("ramp")[-1])
    run("rka.extend_road", use_delta=True, dx=160.0, dy=90.0, dz=0.0)
    net = pm.read_network()
    res = ro.make_ramp(net, _pts("main")[-1].rka_pt.uid, _pts("ramp")[0].rka_pt.uid)
    po.apply_network(net)
    bpy.context.view_layer.update()
    net = pm.read_network()
    pairs = net.aux_pairs()
    assert len(pairs) == 1, pairs
    assert net.points[pairs[0][0]].aux_fwd >= 1, "the mainline never opened its aux slot"
    assert res["aligned"] and not [f for f in pv.errors(pv.validate(net)) if f.code.startswith("ramp_")]
    check("Make Ramp (record gesture): an AUX link plus the aux slot, the mouth on the gore line")
    ok += 1

    # ================================================================= B. junction
    mp, cp = _pts("main"), _pts("cross")
    _sel(mp[3], mp[4], cp[1], cp[2], active=mp[3])
    run("rka.make_intersection")
    net = pm.read_network()
    cliques = net.junction_cliques()
    assert len(cliques) == 1 and len(cliques[0]) == 4, cliques
    jct = mp[3].parent
    assert jct is not None and jct.name.startswith("JCT_")
    # The JCT parent owns position. SCALE is locked -- a stray S would restate every mouth's lane
    # count at once. Rotation is locked out of plane only: turning the crossing about Z is a real
    # gesture, and the handle sits on the live centre so it turns about the intersection.
    assert all(jct.lock_scale), jct.lock_scale
    assert tuple(jct.lock_rotation) == (True, True, False), tuple(jct.lock_rotation)
    assert po.junction_drift(jct) < 1e-6, "the handle is the centre, from creation onwards"
    check("Make Intersection: one clique of 4, a JCT_* handle on the centre with scale locked "
          "and Z free, chain unsplit")
    ok += 1

    # ================================================================= C. Auto Setback
    before = [tuple(o.matrix_world.translation) for o in _pts("main")]
    _sel(mp[3])
    res = run("rka.auto_setback", margin=2.0)
    net = pm.read_network()
    assert all(net.points[u].setback_solved > 0.0 for u in cliques[0]), "no setback recorded"
    check("Auto Setback runs whole-clique and records the solved distance on every mouth (%s)"
          % ("moved" if res == {'FINISHED'} else "already solved"))
    ok += 1

    # ...and a LOCKED mouth is never touched, however far off it is.
    lock = mp[3]
    lock.rka_pt.setback_locked = True
    here = tuple(lock.matrix_world.translation)
    lock.matrix_world.translation = (here[0] - 25.0, here[1], here[2])
    moved_to = tuple(lock.matrix_world.translation)
    bpy.context.view_layer.update()
    _sel(mp[4])
    run("rka.auto_setback", margin=2.0)
    assert tuple(lock.matrix_world.translation) == moved_to, "a locked mouth was moved"
    lock.rka_pt.setback_locked = False
    check("a setback_locked mouth survives Auto Setback -- the lock is explicit, never inferred")
    ok += 1

    # ================================================================= F. connect
    mp = _pts("main")
    _sel(mp[0], mp[2], active=mp[0])
    run("rka.connect_selected", type=pm.LINK_SEGMENT)
    assert pm.read_network().points[mp[0].rka_pt.uid].has_link(mp[2].rka_pt.uid, pm.LINK_SEGMENT)
    _unlink(mp[0], mp[2])
    assert not pm.read_network().points[mp[0].rka_pt.uid].has_link(mp[2].rka_pt.uid)
    check("Connect Selected writes a typed link symmetrically")
    ok += 1

    # -- the ACTIVE point is the source, not `selected_objects` order --------------------------
    # AUX is DIRECTED (mainline -> ramp) and the ordering used to be arbitrary, so the Aux button
    # agreed with the panel's own "active = mainline" hint only about half the time.
    a, b = po.resolve_pair(_ctx_sel(mp[2], mp[0], active=mp[2]))
    assert (a, b) == (mp[2], mp[0]), (a.name, b.name)
    a, b = po.resolve_pair(_ctx_sel(mp[2], mp[0], active=mp[0]))
    assert (a, b) == (mp[0], mp[2]), (a.name, b.name)
    check("Connect is anchored on the ACTIVE point, so a directed AUX link cannot come out backwards")
    ok += 1

    # -- ...but AUX resolves its OWN direction, so the gesture works from either end -------------
    # An entrance ramp reads "ramp joins road", so the ramp is the natural point to have active --
    # and that used to be refused outright ("the AUX target must be a RAMP point"), which made half
    # the ramps in a network unauthorable with the button the panel offers.
    ramp0, main0 = _pts("ramp")[0], _pts("main")[-1]
    assert po.resolve_aux_pair(main0, ramp0) == (main0, ramp0)
    assert po.resolve_aux_pair(ramp0, main0) == (main0, ramp0), "the mainline is the one with aux"
    _sel(ramp0, main0, active=ramp0)                  # the RAMP is active: the old refusal case
    run("rka.connect_selected", type=pm.LINK_AUX)
    net = pm.read_network()
    assert net.points[main0.rka_pt.uid].has_link(ramp0.rka_pt.uid, pm.LINK_AUX), \
        "AUX must be written mainline -> ramp however the two were picked"
    assert not net.points[ramp0.rka_pt.uid].has_link(main0.rka_pt.uid), "AUX stays directed"
    check("Aux connects either way round -- which point is the mainline is a fact, not click order")
    ok += 1

    # -- and it can be driven by NAME, which is the answer to "selecting two points is fiddly" --
    _sel(mp[0], active=mp[0])
    run("rka.connect_selected", type=pm.LINK_SEGMENT, target=mp[2].name)
    assert pm.read_network().points[mp[0].rka_pt.uid].has_link(mp[2].rka_pt.uid, pm.LINK_SEGMENT)
    _unlink(mp[0], mp[2])
    assert not pm.read_network().points[mp[0].rka_pt.uid].has_link(mp[2].rka_pt.uid)
    check("Connect works from a NAMED target, with one point selected")
    ok += 1
    # ================================================================= F3. ROTATION (the helper Build runs)
    def _bow(name):
        n = pm.read_network()
        r = n.roads[name]
        sol = ps.solve_road(n, r)
        p0, p1 = sol.samples[0].pos, sol.samples[-1].pos
        d = (p1[0] - p0[0], p1[1] - p0[1])
        L = (d[0] ** 2 + d[1] ** 2) ** 0.5 or 1.0
        return max(abs(((sm.pos[0] - p0[0]) * d[1] - (sm.pos[1] - p0[1]) * d[0]) / L)
                   for sm in sol.samples)

    # ============================================== F3. ROTATION IS THE GESTURE (the second report)
    # "connect to another point through extend road ... if rotate 75 degree around z axis, the
    # previous connection seem connect to old angle of the target point". Both halves were real:
    # a point born by Extend Road had IDENTITY rotation (so its arrow pointed at world +Y whatever
    # the road did) and it was AUTO (so its rotation was ignored outright). Rotating it therefore
    # did nothing at all, and the only way to make it count was a button nothing told you about.
    import math as _math
    run("rka.new_road", name="road_rot", lanes_fwd=1, lanes_bwd=1, design_speed=40.0)
    rp0 = _pts("road_rot")[0]
    _sel(rp0, active=rp0)
    run("rka.extend_road", use_delta=True, dx=140.0)
    _sel(bpy.context.active_object, active=bpy.context.active_object)
    run("rka.extend_road", use_delta=True, dx=140.0)
    rpts = _pts("road_rot")
    bpy.context.view_layer.update()
    # THE ARROW MUST NOT LIE. An east-west road's points face EAST the moment they are made.
    for o in rpts:
        f = pm.facing_of(o)
        assert abs(f[0] - 1.0) < 1e-4, (o.name, f)
    assert all(o.rka_pt.tangent_mode == pm.AUTO for o in rpts)
    assert _bow("road_rot") < 1e-6

    # A pure DRAG changes the chain tangent while leaving the rotation alone. It must NOT read as
    # a rotation -- which is exactly why the baseline is stamped rather than recomputed.
    rpts[1].location = (140.0, 40.0, 0.0)
    bpy.context.view_layer.update()
    assert all(pm.read_network().points[o.rka_pt.uid].tangent_mode == pm.AUTO for o in rpts)
    promoted, refaced = po.sync_facings(bpy.context.scene)
    assert not promoted and refaced, (promoted, refaced)
    check("a point is BORN facing its road, and dragging one is never mistaken for rotating it")
    ok += 1

    # Now the gesture itself: rotate, and the road bends. No mode switch, no button, no rebuild --
    # the promotion is derived in `read_point`, so the overlay and the gate see it immediately.
    rpts[2].rotation_euler = (0.0, 0.0, _math.radians(75.0))
    bpy.context.view_layer.update()
    assert pm.read_network().points[rpts[2].rka_pt.uid].tangent_mode == pm.MANUAL
    rot_bow = _bow("road_rot")
    assert rot_bow > 3.0, rot_bow
    po.sync_facings(bpy.context.scene)
    assert rpts[2].rka_pt.tangent_mode == pm.MANUAL, "the enum catches up so the panel is honest"
    assert all(o.rka_pt.tangent_mode == pm.AUTO for o in rpts[:2])
    check("rotating an AUTO point bends the road with no mode switch (%.1f m of bow), and the "
          "flag catches up" % rot_bow)
    ok += 1

    # ...and the way back. Setting AUTO must not instantly re-promote off the stale baseline, and
    # the next sync re-straightens the arrow to the chain. Leaves the scene flat for the gate.
    rpts[2].rka_pt.tangent_mode = pm.AUTO
    assert pm.read_network().points[rpts[2].rka_pt.uid].tangent_mode == pm.AUTO
    rpts[1].location = (140.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    po.sync_facings(bpy.context.scene)
    bpy.context.view_layer.update()
    assert abs(pm.facing_of(rpts[2])[0] - 1.0) < 1e-4, pm.facing_of(rpts[2])
    assert _bow("road_rot") < 1e-6, _bow("road_rot")
    check("back to AUTO re-straightens instead of re-adopting the rotation it was just given")
    ok += 1

    # ================================================================= G. the gate
    net = pm.read_network()
    assert not pv.errors(pv.validate(net)), pv.errors(pv.validate(net))
    check("Validate: the whole authored scene is gate-GREEN")
    ok += 1

    # ================================================================= H. build / clear
    run("rka.point_build")
    surfaces = [o for o in bpy.data.objects if o.name.endswith(pb.SUFFIX_CARRIER)]
    pads = [o for o in bpy.data.objects if o.name.endswith(pb.SUFFIX_PAD)]
    cols = [o for o in bpy.data.objects if o.name.endswith(pb.SUFFIX_COL)]
    assert surfaces and pads and cols, (len(surfaces), len(pads), len(cols))
    authored = {o.name for o in bpy.data.objects if getattr(o, "rka_pt", None) is not None
                and o.rka_pt.is_point}
    run("rka.point_clear")
    assert not [o for o in bpy.data.objects if o.name.endswith(pb.SUFFIX_CARRIER)]
    still = {o.name for o in bpy.data.objects if getattr(o, "rka_pt", None) is not None
             and o.rka_pt.is_point}
    # RULE 1: a build only ever clears inside ROAD_MANAGER_GEN.
    assert still == authored, authored ^ still
    check("Build then Clear Generated: %d surfaces, %d pads, %d proxies -- and every authored "
          "point survives" % (len(surfaces), len(pads), len(cols)))
    ok += 1

    # ================================= H2. THE GROUND SAMPLE REACHES THE AUTHORED POINTS
    # 3.3 rule 1: Build samples the terrain UNCONDITIONALLY -- there is no button to forget. The
    # thing to check is not that it samples, but that the number ARRIVES: on the Empty, in the
    # panel readout, in `.roads.json`, and in the gate's warning clearing.
    warns = {f.code for f in pv.validate(pm.read_network())}
    assert "ground_unsampled" in warns, "premise: nothing has been sampled yet"
    terrain = bpy.data.collections.new("TERRAIN")
    bpy.context.scene.collection.children.link(terrain)
    bpy.ops.mesh.primitive_plane_add(size=4000.0, location=(400.0, 0.0, -7.0))
    plane = bpy.context.active_object
    for c in list(plane.users_collection):
        c.objects.unlink(plane)
    terrain.objects.link(plane)
    bpy.context.view_layer.update()

    run("rka.point_build")
    sampled = [o for o in _pts("main") if o.rka_pt.has_ground_z]
    assert sampled, "Build sampled the terrain but the number never reached the Empties"
    assert all(abs(o.rka_pt.ground_z + 7.0) < 1e-4 for o in sampled), \
        [o.rka_pt.ground_z for o in sampled]
    net = pm.read_network()
    assert all(abs(net.points[o.rka_pt.uid].ground_z + 7.0) < 1e-4 for o in sampled)
    # ...and the road is now 7 m up on fill, derived from that one number and nothing else.
    sol = ps.solve_road(net, net.roads["main"], ps.road_runs(net, net.roads["main"])[0])
    kinds = {sol.values[i]["rka_support"] for i in range(len(sol))}
    assert ps.SUPPORT_CODE["PIER"] in kinds, kinds
    check("Build's ground sample reaches the Empties, the record and the support solve "
          "(%d station(s) at -7.0 m -> PIER)" % len(sampled))
    ok += 1

    # THE ROAD MUST NOT WALK UP ITS OWN OUTPUT. The raycast runs against the live scene, which by
    # now contains the surface the last build swept. If generated geometry is not excluded, the
    # second build samples the ROAD instead of the ground, `ground_z` climbs to the road's own
    # height, the support flips PIER -> NONE, and every rebuild lifts it further. Two builds and a
    # comparison is the whole test, and it fails loudly.
    first = {o.name: o.rka_pt.ground_z for o in _pts("main") if o.rka_pt.has_ground_z}
    run("rka.point_build")
    run("rka.point_build")
    third = {o.name: o.rka_pt.ground_z for o in _pts("main") if o.rka_pt.has_ground_z}
    assert first == third, ("ground drifted across rebuilds",
                            {k: (first[k], third.get(k)) for k in first
                             if first[k] != third.get(k)})
    net = pm.read_network()
    sol = ps.solve_road(net, net.roads["main"], ps.road_runs(net, net.roads["main"])[0])
    assert ps.SUPPORT_CODE["PIER"] in {sol.values[i]["rka_support"] for i in range(len(sol))}, \
        "the viaduct lost its supports on rebuild -- it sampled its own deck"
    check("three builds, identical ground: the raycast never samples the road's own output")
    ok += 1

    # A MISS IS NOT A SAMPLE. With the terrain gone the flag must not be re-asserted, and the
    # last real value must survive rather than being overwritten with 0.
    bpy.data.objects.remove(plane, do_unlink=True)
    bpy.data.collections.remove(terrain)
    bpy.context.view_layer.update()
    probe = _pts("cross")[0]
    probe.rka_pt.has_ground_z = False
    probe.rka_pt.ground_z = 0.0
    keeper = sampled[0]
    run("rka.point_build")
    assert not probe.rka_pt.has_ground_z, "a raycast MISS was recorded as a sample"
    assert keeper.rka_pt.has_ground_z and abs(keeper.rka_pt.ground_z + 7.0) < 1e-4, \
        "a miss overwrote a station's last real ground sample"
    check("a raycast miss is not recorded as a sample -- no invented ground under a road "
          "over water")
    ok += 1

    # ================================================================= I. the record + export
    tmp = tempfile.mkdtemp()
    rec = os.path.join(tmp, "coverage.roads.json")
    run("rka.save_record", filepath=rec)
    first = open(rec).read()
    assert len(first) > 500
    n_before = len(pm.read_network().points)
    run("rka.load_record", filepath=rec)
    assert len(pm.read_network().points) == n_before
    run("rka.save_record", filepath=rec)
    assert open(rec).read() == first, "the record did not round-trip byte-stable"
    check("Save / Load Road Record round-trips the Empties byte-stable (%d bytes)" % len(first))
    ok += 1

    lk = os.path.join(tmp, "coverage.lanekit.json")
    run("rka.export_lanekit", filepath=lk)
    doc = json.load(open(lk))
    assert doc["schema_ver"] == 2, doc.get("schema_ver")
    assert doc["lanes"] and doc["junctions"] and doc["arms"] and doc["roads"]
    through = [l for l in doc["lanes"] if l["kind"] == "through"]
    conn = [l for l in doc["lanes"] if l["kind"] != "through"]
    assert any(l["spawnable"] for l in through), "no through lane is spawnable"
    assert not any(l["spawnable"] for l in conn), "a connector is spawnable"
    assert all(len(l["curve"]) >= 2 for l in through)
    check("Export .lanekit v2: %d through + %d connectors, junctions[]/arms[]/roads[] present, "
          "spawnable explicit" % (len(through), len(conn)))
    ok += 1

    # ...and the gate GUARDS the export: break the scene, the export must refuse.
    mp = _pts("main")
    victim = mp[1]
    hold = tuple(victim.matrix_world.translation)
    victim.matrix_world.translation = tuple(mp[2].matrix_world.translation)
    bpy.context.view_layer.update()
    bad = os.path.join(tmp, "bad.lanekit.json")
    try:
        run("rka.export_lanekit", filepath=bad)
        exported = True
    except RuntimeError:
        exported = False
    assert not exported and not os.path.exists(bad), "a failing gate still exported"
    victim.matrix_world.translation = hold
    bpy.context.view_layer.update()
    check("a failing gate REFUSES to export -- a bad build is a failed build, not a warning")
    ok += 1

    # ================================================================= L. THE SAMPLE NETWORK
    # The sample network, loaded from its committed record. It is tested end to end because a worked
    # example that does not survive the gate teaches the wrong thing.
    _wipe()
    run("rka.load_record", filepath=SAMPLE)
    net = pm.read_network()
    assert len(net.roads) == 6, sorted(net.roads)
    errs = pv.errors(pv.validate(net))
    assert not errs, ["%s: %s" % (f.code, f.message) for f in errs]
    assert len(net.junction_cliques()) == 1
    # ONE RAMP OUT AND ONE RAMP IN, AT EACH OF TWO SHARED STATIONS (8l). `demo_hwy_p002` and
    # `demo_main_p007` each carry an EXIT and an ENTRANCE: eastbound traffic leaves the expressway
    # and joins the arterial, westbound traffic does the reverse. A single `aux_fwd` integer
    # cannot say that -- the two are different pavement on different carriageways, and which one a
    # ramp is on is read off which side its mouth sits (`point_solve.ramp_side_of`), which is what
    # `aux_block`'s "most slots, ties to FWD" reading used to get wrong for the reverse one.
    pairs = net.aux_pairs()
    assert len(pairs) == 5, pairs
    for road, station in (("demo_hwy", "demo_hwy_p002"), ("demo_main", "demo_main_p007")):
        uid = next(u for u, lab in net.labels.items() if lab == "%s/%s" % (road, station))
        here = [r for m, r in pairs if m == uid]
        assert len(here) == 2, (station, [net.labels[r] for r in here])
        assert sorted(pm.ramp_is_entrance(net, r) for r in here) == [False, True], \
            "%s must accept one ramp OUT and one ramp IN" % station
        sides = {net.road_of(r).name: ps.ramp_side_of(net, uid, r) for r in here}
        assert sides == {"demo_ramp": lp.FWD, "demo_ramp_b": lp.REV}, (station, sides)
        res = net.resolved(uid)
        assert res.aux_fwd >= 1 and res.aux_bwd >= 1, (station, res.aux_fwd, res.aux_bwd)
        # ...and the two blocks are disjoint by construction -- different slot ids entirely.
        alloc = ps.aux_allocation(net, uid)
        got = {net.road_of(r).name: alloc[r] for r in here}
        assert got == {"demo_ramp": ["AF0"], "demo_ramp_b": ["AR0", "AR1"]}, (station, got)

    # MULTI-LANE, which nothing else exercises: two aux slots is 8g.1's case, where a ramp
    # anchored on the outermost slot instead of the whole BLOCK lands half on the carriageway.
    rb = net.roads["demo_ramp_b"]
    assert all(net.resolved(u).lanes_fwd == 2 for u in rb.points), \
        [net.resolved(u).lanes_fwd for u in rb.points]

    # A RAMP MUST LEAVE OUTBOARD. The sample's own exit used to dive straight back across the
    # carriageway it was leaving: no gore could be paved, and nothing said so (8j).
    for m, r in pairs:
        outboard, _along = ps.ramp_divergence(net, m, r)
        assert outboard > 1.0, "%s bends %.1f m inboard" % (net.labels[r], outboard)
    # All four link types are present, which is the point of the example.
    kinds = {l.type for p in net.points.values() for l in p.links}
    assert kinds == {pm.LINK_SEGMENT, pm.LINK_JUNCTION, pm.LINK_AUX}, kinds
    # It is authored THROUGH THE GESTURES, so the sample is evidence they work -- these are the
    # ones that were broken and that a helper-written fixture could not have caught (8i.1, 8i.4).
    mx = [round(o.location.x) for o in _pts("demo_main")]
    assert mx[0] < mx[1], "the head extension grew the wrong way: %s" % mx
    hx = _pts("demo_hwy")
    assert hx[2].rka_pt.aux_fwd and hx[2].rka_pt.aux_bwd, \
        "both carriageways must open an aux lane over one span"
    check("the sample network (its committed record): 6 roads, a crossing, a ramp OUT and a ramp IN at each of two "
          "shared stations (the westbound one two lanes wide), and a spur branched from the "
          "middle of a corridor -- gate-GREEN")
    ok += 1

    run("rka.point_build")
    surf = [o for o in bpy.data.objects if o.name.endswith(pb.SUFFIX_CARRIER)]
    pads = [o for o in bpy.data.objects if o.name.endswith(pb.SUFFIX_PAD)]
    assert len(surf) >= 5 and len(pads) == 1, (len(surf), len(pads))
    # The highway is 14 m up, so it must be on piers -- the sample exists to SHOW that.
    hwy = next(o for o in surf if o.name.startswith("demo_hwy"))
    assert "Pillars" in {m.name for m in hwy.modifiers}, [m.name for m in hwy.modifiers]
    assert "Deck" in {m.name for m in hwy.modifiers}
    lk = os.path.join(tempfile.mkdtemp(), "demo.lanekit.json")
    run("rka.export_lanekit", filepath=lk)
    doc = json.load(open(lk))
    assert doc["lanes"] and doc["junctions"]
    check("...and it builds: %d surfaces (the 14 m highway on piers), %d pad, %d lanes exported"
          % (len(surf), len(pads), len(doc["lanes"])))
    ok += 1

    # ================================================================= L2. THE TWO GORES
    # The sample's ramp LEAVES the highway and MERGES into the arterial, so it makes two gores of
    # deliberately different kinds -- and each is asserted at the level it is actually fixed at.
    net = pm.read_network()
    pairs = net.aux_pairs()
    gore = [o for o in bpy.data.objects if o.name.endswith(pb.SUFFIX_GORE)]
    assert len(gore) == 5, [o.name for o in gore]
    by_ramp = {}
    for main_uid, ramp_uid in pairs:
        g = next((o for o in gore if o.name.startswith("GORE_" + ramp_uid[:8])), None)
        assert g is not None, (ramp_uid, [o.name for o in gore])
        assert len(g.data.polygons) >= 2, "%s is a strip, not an empty mesh" % g.name
        resid, angle = ps.ramp_residual(net, main_uid, ramp_uid)
        assert resid < 0.01, "%s: the mouth sits ON the gore line, %.3f m off" % (g.name, resid)
        assert angle < 0.5, "%s: ...and leaves PARALLEL, %.1f deg off" % (g.name, angle)
        by_ramp[ramp_uid] = g
    assert any(o.name.startswith("GORE_") and o.name.endswith(pb.SUFFIX_COL)
               for o in bpy.data.objects), "a gore needs collision or a car drops through it"
    check("all %d gores are paved wedges whose mouths sit on the gore line and face down their "
          "mainline, and the outer of two ramps at one station opens against the INNER RAMP "
          "(%s)" % (len(gore), ", ".join("%d faces" % len(g.data.polygons) for g in gore)))
    ok += 1

    # ================================================================= L2a. THE GORE'S NOSE CAP
    # A gore is bare paint, so BOTH flanking walls open across it -- right along the join, where a
    # wall would stand in the exit lane, and wrong at the wide end, where the two roads have parted
    # and their walls restarted metres apart with an open V between them, on a viaduct, over the
    # drop. The cap is an ordinary edge run on the ordinary `edge_spec()` stack.
    noses = [o for o in bpy.data.objects
             if o.name.startswith("GORE_") and o.name.endswith(pb.SUFFIX_EDGE + "_nose")]
    assert len(noses) == 5, [o.name for o in noses]
    # A NOSE CLOSES A V; IT DOES NOT BLOCK THE RAMP (8j). Every cap must be about as wide as the
    # gap the gore ends at -- a few metres. The one that got reported was 22 m of 1 m wall laid
    # straight across a merge, and the mesh was the only place it showed: the gate was green, the
    # residual was zero, and only the sign of one normal was wrong.
    solves = [x for v in ps.solve_network(net).values() for x in v]
    by_solve = {}
    for x in solves:
        for u in x.uids:
            by_solve[u] = x
    # A GORE IS AGAINST THE NEIGHBOUR ON THE INBOARD SIDE (8k), and a ramp on the OTHER
    # carriageway is not that: the two share a station and nothing else, so neither is beside the
    # other anywhere and both open against the mainline.
    assert all(ps.inboard_neighbour(net, m, r, by_solve) is None for m, r in pairs), \
        [net.labels[r] for m, r in pairs if ps.inboard_neighbour(net, m, r, by_solve)]
    for g in ps.solve_gores(net, solves):
        assert g.nose is not None, net.labels[g.ramp_uid]
        cap = math.dist(g.nose.points[0][:2], g.nose.points[-1][:2])
        assert cap <= ps.GORE_NOSE_WIDTH + 2.0, \
            "%s: a %.1f m nose cap is a wall across the ramp, not a cap on the gore" % (
                net.labels[g.ramp_uid], cap)
        assert g.length > 1.0, "%s: the gore is a %.2f m splinter" % (net.labels[g.ramp_uid],
                                                                     g.length)
    # WHAT a cap carries is the RAMP's own section, so a fenced ramp gives a wall and a walkable
    # one gives a kerbed island -- the sample has both, and the empty case is a third (8i.5). What
    # every cap must do is carry SOMETHING, or the V it exists to close is still open.
    walled = 0
    for n in noses:
        mods = {m.name for m in n.modifiers}
        assert mods & {"Barrier", "Curb", "Sidewalk"}, (n.name, sorted(mods))
        walled += "Barrier" in mods
    assert walled >= 3, walled
    # THE MISMATCHED PAIR, which is what 8i.5 is about and what the sample now contains: the
    # arterial declares a footway, a kerb and NO wall (it is at grade and walkable); the ramp is
    # fenced. The nose is the RAMP's section along its whole length -- a single uniform wall --
    # not a blend that falls from the ramp's height to nothing across a widening footway, which is
    # a shape neither road has anywhere else.
    entry_uid = next(r for _m, r in pairs
                     if pm.ramp_is_entrance(net, r) and net.road_of(r).name == "demo_ramp")
    street_nose = next(n for n in noses if n.name.startswith("GORE_" + entry_uid[:8]))
    wall = [d.value for d in street_nose.data.attributes["rka_wall_h"].data]
    assert wall and max(wall) - min(wall) < 1e-6 and wall[0] > 0.5, wall
    ramp_wall = pm._local(bpy.data.collections, "demo_ramp").rka_road.barrier_height
    assert abs(wall[0] - ramp_wall) < 1e-6, (wall[0], ramp_wall)
    # ...and it must reach the collision proxy, or it is a wall you can drive straight through.
    walk_proxy = [o for o in bpy.data.objects
                  if o.name.startswith("GORE_") and pb.COL_WALK in o.name
                  and o.name.endswith(pb.SUFFIX_COL)]
    assert walk_proxy and len(walk_proxy[0].data.polygons) > 0, [o.name for o in walk_proxy]
    # An island between a road and a ramp nobody may walk on is NOT a refuge: -noped, or the
    # navmesh bakes a walkable strip in the middle of an exit. BOTH flanks must allow pedestrians
    # for a gore to be walkable -- so every gore touching the fenced expressway or one of its
    # ramps is closed, and the one between the walkable arterial and the walkable spur is not.
    # Both cases are in the sample deliberately: an all-`-noped` answer would also be produced by
    # a constant, and this is the rule being `ped_access`-driven.
    noped = [o for o in walk_proxy if pb.NO_PED_SUFFIX in o.name]
    walkable = [o for o in walk_proxy if pb.NO_PED_SUFFIX not in o.name]
    assert len(noped) == 4 and len(walkable) == 1, [o.name for o in walk_proxy]
    assert walkable[0].name.startswith("GORE_" + next(
        r for m, r in pairs if net.road_of(r).name == "demo_spur")[:8]), walkable[0].name
    check("all %d nose caps close their V and carry the RAMP's own section -- a %.2f m wall where "
          "the ramp is fenced, a kerbed island where it is not -- and each reaches collision with "
          "the -noped marker its two flanks earn" % (len(noses), wall[0]))
    ok += 1

    # ================================================================= L2b. THE PAD'S FOOTWAY
    # A crossing was bare asphalt to its own boundary, with every street's footway stopping dead at
    # its mouth -- four missing pavement corners at every junction in the world.
    jct_edges = [o for o in bpy.data.objects
                 if o.name.startswith("JCT_") and pb.SUFFIX_EDGE in o.name]
    assert len(jct_edges) == 4, [o.name for o in jct_edges]
    assert all({"Curb", "Sidewalk"} <= {m.name for m in o.modifiers} for o in jct_edges)
    # ...and the wall: the demo highway has no pedestrian access, so it is fenced; the arterial
    # under it is at grade and walkable, so it is not.
    def _mods(road):
        return {m.name for o in bpy.data.objects
                if o.name.startswith(road) and pb.SUFFIX_EDGE in o.name
                for m in o.modifiers}
    assert "Barrier" in _mods("demo_hwy") and "Barrier" in _mods("demo_ramp"), _mods("demo_hwy")
    assert "Barrier" not in _mods("demo_main"), _mods("demo_main")
    assert "Sidewalk" in _mods("demo_main")
    check("the pad grows kerb + footway on all 4 corners, and the barrier follows ped_access")
    ok += 1

    # ================================================================= L2c. THE TWO ROAD KNOBS
    hwy = pm._local(bpy.data.collections, "demo_hwy")
    assert abs(hwy.rka_road.taper_factor - 1.0) < 1e-6, "the default IS the real standard"
    assert hwy.rka_road.barrier_height > 0.0
    # `taper_factor` really relaxes the gate, and it is the ROAD's, not a constant in the checker.
    hwy_pts = _pts("demo_hwy")
    hwy_pts[1].rka_pt.aux_fwd = 1          # open the aux one station earlier: too abrupt at 80
    hwy_pts[0].rka_pt.aux_fwd = 0
    hwy.rka_road.base.design_speed = 120.0
    for o in hwy_pts:
        o.rka_pt.design_speed = 120.0
    net_t = pm.read_network()
    assert [f for f in pv.errors(pv.validate(net_t)) if f.code == "taper_too_short"], \
        "a 120 km/h aux opening over 200 m is short of the standard"
    hwy.rka_road.taper_factor = 0.4
    net_t = pm.read_network()
    assert not [f for f in pv.errors(pv.validate(net_t)) if f.code == "taper_too_short"], \
        "taper_factor must actually relax it -- the compressed-world knob"
    hwy.rka_road.taper_factor = 1.0
    check("taper_factor scales the gate's merge-taper rule; 1.0 is the real standard")
    ok += 1

    # ================================================================= L3. THE FLOW REPORT
    # The defect this exists to catch, reproduced: cut the AUX link and the ramp becomes a lane
    # nothing can reach. Geometry stays perfect and the gate stays green -- which is exactly why
    # reachability needed its own eye. (`point_flow` is the owner; the Godot dock's Flow Report asks it.)
    rep = _flow()
    assert rep["lanes"] > 20 and rep["ramp_orphans"] == [], rep
    assert not rep["broken"] and not rep["unreached"] and not rep["misjoined"], rep
    # AN AUX LANE ON ONE CARRIAGEWAY MUST NOT UNHOOK THE OTHER'S (8k): asked of the widths, not the
    # receiver.
    mid = _pts("demo_main")[5]
    mid.rka_pt.aux_bwd = 1
    both = _flow()
    assert not both["unreached"] and not both["broken"] and not both["misjoined"], both
    mid.rka_pt.aux_bwd = 0
    doc = pe3.export_network(pm.read_network())
    ramp_lanes = [l for l in doc["lanes"] if l["road_name"] == "demo_ramp"]
    assert ramp_lanes and any(l["id"] in {n for x in doc["lanes"] for n in (x.get("next") or ())}
                              for l in ramp_lanes), \
        "the aux lane must hand off to the ramp -- without that edge no car ever exits"
    hold = []
    for pt in _pts("demo_hwy"):
        for i in range(len(pt.rka_pt.links) - 1, -1, -1):
            if pt.rka_pt.links[i].type == pm.LINK_AUX:
                hold.append((pt, pt.rka_pt.links[i].target))
                pt.rka_pt.links.remove(i)
    broke = _flow()
    assert broke["ramp_orphans"], "cutting the AUX link must orphan the ramp in the report"
    check("the flow report reads the EXPORT: %d lanes, and cutting the AUX link is reported as an "
          "orphaned ramp (%s)" % (rep["lanes"], broke["ramp_orphans"][0]))
    ok += 1

    # -- a Path3D pushed off its lane is named by the report and the gate's measure ------------------
    doc = pe3.export_network(pm.read_network())
    victim = next(l for l in doc["lanes"] if l["id"] == "demo_ramp_F0")
    h = victim["curve"][1]["out"]
    victim["curve"][1]["out"] = [-h[2] * 8.0, h[1], h[0] * 8.0]
    assert pe3.path_deviation(victim) > pe3.PATH_DEVIATION_ERROR, \
        "the sabotage must actually move the curve off the road"
    assert any(i == "demo_ramp_F0" for i, _d in pe3.deviating_lanes(doc))
    assert any(i == "demo_ramp_F0" for i, _d in pflow.flow_report(doc)["path_off_road"]), \
        "Flow Report must list a path that has left its lane"
    check("a curve pushed off its lane is reported by name")
    ok += 1

    # -- STYLE: markings, one material registry, and a profile asset --------------------------------
    # The road kit used to build kerbs, footways, walls, pads and gores and not one lane line --
    # while `lane_profile.marking_runs` had computed every painted boundary since the profile model
    # landed and `kit_common.MATS` had carried `M_LineW`/`M_LineY`, described in its own source as
    # lane lines, with no user at all.
    #
    # A FRESH sample first: the preview block above deliberately cut demo_hwy's AUX links to
    # orphan a ramp, which leaves the aux slot opening over a span far too short for its taper --
    # a red gate, and correctly so. Style is a different subject and starts from a green network.
    # `_wipe()` and not `replace=True`: the cut links left `demo_spur` an EMPTY collection, and
    # `Add Sample Network` extends roads by selecting their last point.
    _wipe()
    run("rka.load_record", filepath=SAMPLE)
    bpy.ops.rka.point_build()
    gen = bpy.data.collections.get(pm.ROAD_MANAGER_GEN)
    built = _all_objects(gen)
    marks = [o for o in built if "__marks" in o.name]
    assert marks, "a multi-lane network must paint lane lines"
    dg = bpy.context.evaluated_depsgraph_get()
    painted = set()
    for o in marks:
        me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), depsgraph=dg)
        painted.update(m.name for m in me.materials if m)
        zs = [v.co.z for v in me.vertices]
        base = min(zs) if zs else 0.0
        assert len(me.polygons) > 0, "%s painted nothing" % o.name
        bpy.data.meshes.remove(me)
    assert {"M_LineW", "M_LineY"} <= painted, painted
    # ...and paint is NOT collidable: a proxy per stripe is a paper-thin StaticBody under every
    # dashed line in the world, for something no bullet, wheel or navmesh agent wants.
    assert not [o for o in built if "__marks" in o.name and pb.SUFFIX_COL in o.name], \
        "lane markings must not reach collision"
    # ONE material registry: everything the road builds is now a `kit_common` `M_*` datablock, not
    # the parallel `rka_*` set that had no lane lines in it.
    road_mats = {m.name for o in built for m in (o.data.materials if o.data else ()) if m}
    assert not [m for m in road_mats if m.startswith("rka_")], sorted(road_mats)
    check("markings paint %d object(s) in M_LineW/M_LineY, out of collision, from ONE registry"
          % len(marks))
    ok += 1

    # -- a PROFILE ASSET replaces its layer, at its own size, gated the same way ---------------------
    run("rka.link_road_kit")
    kit = pstyle.kit_assets()
    if kit:
        road = next(c for c in pm.road_collections() if c.name == "demo_main")
        road.rka_road.kerb_asset = "RKA_PROFILE_kerb_granite"
        st = pstyle.resolve(road.rka_road, material_fn=pb.material)
        got = pstyle.asset_width(st.asset("kerb"))
        # MEASURED OFF THE CURVE DATA, never `bound_box`: on a freshly linked object in background
        # Blender the cached box is stale and reported this 0.32 m kerb as 2.32 m.
        assert abs(got - 0.32) < 1e-3, "asset width must be the section's own: %.3f" % got
        assert abs(pstyle.asset_height(st.asset("kerb")) - 0.17) < 1e-3
        bpy.ops.rka.point_build()
        edges = [o for o in _all_objects(bpy.data.collections.get(pm.ROAD_MANAGER_GEN))
                 if o.name.startswith("demo_main") and pb.SUFFIX_EDGE in o.name
                 and pb.SUFFIX_COL not in o.name]
        dg = bpy.context.evaluated_depsgraph_get()
        tops = []
        for o in edges:
            me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), depsgraph=dg)
            if me.vertices:
                tops.append(max(v.co.z for v in me.vertices))
            bpy.data.meshes.remove(me)
        # The granite section is 0.17 m tall where the parametric default is 0.15 -- so the height
        # of the built kerb IS the proof the asset drove the geometry.
        assert tops and abs(max(tops) - 0.17) < 1e-3, \
            "the swept kerb must be the ASSET's own height, got %r" % (tops,)
        # ...and an asset layer is still gated: `demo_main` is at grade with ped access, so
        # `solve_road` says no barrier, and naming one must not build one anyway. (An asset layer
        # has no WidthAttr, which is what `layer_has_content` used to gate on.)
        road.rka_road.barrier_asset = "RKA_PROFILE_wall_jersey"
        bpy.ops.rka.point_build()
        edges = [o for o in _all_objects(bpy.data.collections.get(pm.ROAD_MANAGER_GEN))
                 if o.name.startswith("demo_main") and pb.SUFFIX_EDGE in o.name
                 and pb.SUFFIX_COL not in o.name]
        assert not [o for o in edges if any(m.name == "Barrier" for m in o.modifiers)], \
            "an asset barrier must obey the same rule the parametric one does"
        road.rka_road.kerb_asset = ""
        road.rka_road.barrier_asset = ""
        check("a profile asset sweeps at its OWN measured size (0.32 x 0.17 m) and is gated by "
              "the same attribute the parametric layer is")
        ok += 1

    # -- a style slot naming nothing FALLS BACK, and the gate says so ---------------------------------
    road = next(c for c in pm.road_collections() if c.name == "demo_main")
    road.rka_road.kerb_mat = "M_ThisDoesNotExist"
    st = pstyle.resolve(road.rka_road, material_fn=pb.material)
    assert st.material("kerb") is pb.material("concrete"), "a missing name must fall back"
    assert ("kerb", "material", "M_ThisDoesNotExist") in st.missing()
    findings = pv.validate(pm.read_network(), (pv.check_style,))
    assert any(f.code == "style_missing" for f in findings), \
        "a silently-wrong look must still be reported"
    assert not pv.errors(findings), "...as a WARNING: falling back is a working build"
    road.rka_road.kerb_mat = ""
    check("a style slot naming a missing datablock falls back AND is reported by the gate")
    ok += 1

    # -- ...and the GATE says so too, from the same function ----------------------------------------
    # A preview only helps the artist who looks. `check_path_fidelity` measures with
    # `point_export.path_deviation`, the same one the picture is drawn with.
    net_ok = pm.read_network()
    assert not [f for f in pv.validate(net_ok, (pv.check_path_fidelity,))], \
        "a healthy network must not report a path deviation"
    check("check_path_fidelity is green on the sample network and shares the preview's measure")
    ok += 1

    # ================================================================= coverage
    registered = set()
    for mod in (po, pb):
        for cls in mod.CLASSES:
            if hasattr(cls, "bl_idname") and "." in cls.bl_idname:
                registered.add(cls.bl_idname)
    missing = sorted(registered - DRIVEN)
    assert not missing, "registered but never driven by any test: %s" % missing
    check("COVERAGE: all %d registered operators driven" % len(registered))
    ok += 1

    print("\nALL SMOKETESTS PASSED (%d)" % ok)
    print("operators driven: %s" % ", ".join(sorted(DRIVEN)))


main()
