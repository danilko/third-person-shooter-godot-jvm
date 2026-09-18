#!/usr/bin/env python3
"""roadkit_cli.py -- the road kit's SOLVER as a plain-python3 service for the Godot editor plugin.

PLAN.md 3.1 option B: roads are AUTHORED in Godot (`addons/road_kit/`), the kit's data model, gate,
junction solve, lane export AND (since B11) the mesh sweep and the piece glTF run HERE with no Blender
(`gltf`: `point_mesh` + `point_gltf`). Everything this imports already ran under plain python3 -- it is what
`check_roads.sh` stage 1 tests -- so this file adds no logic, only a door.

Every command reads a `.roads.json` record (the kit's own schema, `point_model.network_to_dict`, in
the kit's Z-up frame) and prints ONE JSON object on stdout. Coordinates it hands back for DRAWING
are already in Godot's frame (`point_export.godot`, the one conversion site) so the plugin never
converts a preview; the record itself stays in the kit's frame, converted once by the plugin's IO.

    python3 blender/tools/roadkit_cli.py validate    <record>
    python3 blender/tools/roadkit_cli.py setback     <record> [--margin 2.0]   (rewrites the record)
    python3 blender/tools/roadkit_cli.py centrelines <record> [--step 4.0] [--zones <zones.json>]
    python3 blender/tools/roadkit_cli.py lanekit     <record> <out.lanekit.json>
    python3 blender/tools/roadkit_cli.py bands       <record> [--ground <stem>.ground.json]
    python3 blender/tools/roadkit_cli.py corridors   <record> [--ground <stem>.ground.json]
    python3 blender/tools/roadkit_cli.py ramp        <record> <uid_a> <uid_b> [--lanes 1]   (rewrites the record)
    python3 blender/tools/roadkit_cli.py pieces      <record> <zones.json> <out_dir> <prefix> [--dry-run] [--ground <g.json>]
    python3 blender/tools/roadkit_cli.py merge|split <record> <uid,uid,...> [--keep uid --at-keep | --name n]
    python3 blender/tools/roadkit_cli.py renumber|repair|tidy <record>           (rewrite the record)
    python3 blender/tools/roadkit_cli.py cross_section <record> <src> <uid,...> <LANES,WIDTH,...>
    python3 blender/tools/roadkit_cli.py branch_ramp <record> <uid> [--lanes 1 --carriageway FWD --entrance ...]
    python3 blender/tools/roadkit_cli.py facings|flow <record>
    python3 blender/tools/roadkit_cli.py live        <record> [--zones z.json] [--draft] [--cross]

Exit code 0 unless the command itself failed (a red gate is a RESULT, reported in the JSON).
"""
import argparse
import math
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BP = os.path.dirname(HERE)
for p in (os.path.join(BP, "lib"), os.path.join(BP, "addons", "road_kit_authoring")):
    if p not in sys.path:
        sys.path.insert(0, p)

import point_model as pm          # noqa: E402
import point_validate as pv       # noqa: E402
import point_solve as ps          # noqa: E402
import point_profile as pp        # noqa: E402
import point_export as pe         # noqa: E402
import point_zones as pz          # noqa: E402
import lane_profile as lp         # noqa: E402
import point_edges as ped         # noqa: E402
import point_ground as pg         # noqa: E402
import road_support as rs         # noqa: E402
import point_record_ops as ro     # noqa: E402
import point_flow as pf           # noqa: E402
import point_digest as pdg        # noqa: E402
import point_mesh as pmsh         # noqa: E402
import point_gltf as pgl          # noqa: E402
import point_kit as pk            # noqa: E402
import point_furniture as pfu     # noqa: E402


def _findings(net):
    fs = pv.validate(net)
    errs = pv.errors(fs)
    return {"errors": len(errs), "warnings": len(fs) - len(errs),
            "findings": [{"code": f.code, "severity": f.severity, "obj": f.obj,
                          "message": f.message} for f in fs]}


def cmd_validate(a):
    return _findings(pm.load_network(a.record))


def cmd_setback(a):
    net = pm.load_network(a.record)
    moved, clamped = [], {}
    for uids in net.junction_cliques():
        for uid, old, new in ps.auto_setback(net, uids, a.margin, clamped=clamped):
            moved.append({"uid": uid, "old": old, "new": new})
    pm.save_network(net, a.record)
    # Every mouth's solved distance and position, moved or not, so the plugin can write back the
    # derived `setback_solved` too -- it is shown on the point and must not go stale.
    mouths = {u: {"pos": list(net.points[u].pos), "setback_solved": net.points[u].setback_solved}
              for c in net.junction_cliques() for u in c}
    # A mouth the solve wanted further out than the station beyond it allows (W17): it stopped
    # `MIN_MOUTH_CLEAR` short. The remedy is the gate's -- delete that station, or lock the mouth.
    held = [{"uid": u, "solved": s, "placed": p, "station": st}
            for u, (s, p, st) in sorted(clamped.items())]
    return {"moved": moved, "clamped": held, "mouths": mouths, "cliques": len(net.junction_cliques())}


def cmd_centrelines(a):
    """The overlay's picture. With `--zones` (B6c) each run also says which zone `point_zones` cuts
    it into and whether it reaches past that zone's load radius (`beyond`), and `cross` lists every
    successor edge that leaves its lane's zone, with the lane's points -- the hand-overs that only
    resolve while both pieces are loaded. Everything here is asked of `point_zones`, never derived."""
    return _centrelines(pm.load_network(a.record), a.step, a.zones, cross=True)


def _centrelines(net, step, zones_path, cross=True):
    """`cross` costs a gate run and a whole lane export (~3 s on DebugRoads, `path_deviation` fitting
    every lane twice) -- `live` asks for it only once a drag has ended."""
    zones = pz.load_zones(zones_path) if zones_path and os.path.exists(zones_path) else []
    part = pz.partition(net, zones) if zones else None
    beyond = {f["obj"] for f in part.findings if f["code"] == "zone_beyond_load"} if part else set()
    out = []
    for name, pts, uids in pp.centreline_runs(net, step=step, with_uids=True):
        row = {"road": name, "points": [pe.godot(p) for p in pts], "uids": list(uids)}
        if part is not None:
            first = part.run_of_uid.get(uids[0], uids[0])
            row.update({"first": first, "zone": part.runs.get(first, pz.RESIDENT), "beyond": first in beyond})
        out.append(row)
    res = {"runs": out}
    if part is not None:
        res["pads"] = [{"uid": u, "zone": z, "beyond": u in beyond,
                        "centre": pe.godot((sum(net.points[m].pos[0] for m in c) / len(c),
                                            sum(net.points[m].pos[1] for m in c) / len(c),
                                            sum(net.points[m].pos[2] for m in c) / len(c)))}
                       for c in net.junction_cliques() for u, z in [(min(c), part.pad_zone(c))]]
    if part is not None and cross:
        edges = []
        if not pv.errors(pv.validate(net)):
            doc = pe.export_network(net)
            pz.stamp_lanes(doc, part, net)
            by_id = {l["id"]: l for l in doc.get("lanes", ())}
            for lane, nxt in pz.cross_zone_report(doc)[0]:
                edges.append({"lane": lane, "next": nxt, "zone": by_id[lane].get("zone_id", pz.RESIDENT),
                              "next_zone": by_id[nxt].get("zone_id", pz.RESIDENT),
                              "points": by_id[lane].get("points", [])})
        res["cross"] = edges
    return res


def cmd_lanekit(a):
    net = pm.load_network(a.record)
    gate = _findings(net)
    if gate["errors"]:
        gate["written"] = False
        return gate
    doc = pe.write(net, a.out)
    gate.update({"written": True, "lanes": len(doc.get("lanes", ())),
                 "junctions": len(doc.get("junctions", ()))})
    return gate


def cmd_pieces(a):
    """B6: cut ONE network into a piece per zone (`point_zones`). Writes `<out_dir>/<piece>.lanekit.json`
    per piece and reports the table the build script and the plugin's marker wiring both read -- so
    neither of them computes a piece name or a zone for itself."""
    net = pm.load_network(a.record)
    zones = pz.load_zones(a.zones) if a.zones and os.path.exists(a.zones) else []
    gate = _findings(net)
    part = pz.partition(net, zones)
    gate["findings"] += part.findings
    gate["warnings"] += len(part.findings)
    doc = pe.export_network(net) if not gate["errors"] else {"lanes": [], "junctions": []}
    if zones:
        pz.stamp_lanes(doc, part, net)
    cross, dangling = pz.cross_zone_report(doc)
    if not zones:
        cross = []   # an unzoned doc's zone_id is the legacy per-road tag, not a cut
    counts = part.pieces()
    # B10.6: what each piece EMITS, hashed -- a build skips a piece whose digest is the one it last baked.
    digests = pdg.piece_digests(net, zones, pg.load_ground(a.ground) if a.ground else None) if not gate["errors"] else {}
    pieces = []
    for zone in sorted(counts):
        sub = pz.split_doc(doc, zone) if zones else doc
        piece = pz.piece_name(a.prefix, zone)
        path = os.path.join(a.out_dir, piece + ".lanekit.json")
        row = dict(counts[zone], zone=zone, piece=piece, lanes=len(sub.get("lanes", ())),
                   junctions=len(sub.get("junctions", ())), lanekit=path, digest=digests.get(zone, ""))
        if not gate["errors"] and not dangling and not a.dry_run:
            os.makedirs(a.out_dir, exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(sub, fh, indent=1, sort_keys=True)
                fh.write("\n")
            os.replace(tmp, path)
        pieces.append(row)
    gate.update({"written": bool(not gate["errors"] and not dangling and not a.dry_run),
                 "zones": len(zones), "pieces": pieces, "lanes": len(doc.get("lanes", ())),
                 "cross_zone": len(cross), "dangling": [list(d) for d in dangling],
                 "runs": [{"road": part.run_road[f], "first": f, "zone": z}
                          for f, z in sorted(part.runs.items(), key=lambda kv: (part.run_road[kv[0]], kv[0]))]})
    return gate


def cmd_corridors(a):
    """B7: every built surface as a corridor the Godot terrain stamp deforms Terrain3D to -- the SAME
    corridors `point_build.road_corridors` hands the island's ground carve (`point_edges.band_corridors`,
    widths read off the solved bands, pads and gores included), solved over the same ground sidecar the
    mesh build used. Each point is `[x, y, z, half, ground, kind]` in GODOT axes and the network's frame:
    `ground` is the NATURAL ground under it (null off the grid) and `kind` is `road_support.support_kind`
    of the two -- the stamp may FILL only where the kit did not put the road on piers."""
    net = pm.load_network(a.record)
    gate = _findings(net)
    if gate["errors"]:
        gate["corridors"] = []
        return gate
    grid = pg.load_ground(a.ground) if a.ground else None
    bands = ped.solve_all(net, grid)[3]
    out = []
    kinds = {}
    for line, owner in _join_at_joints(net, [(list(line), str(owner))
                                            for line, _h, owner in ped.band_corridors(bands, owners=True)]):
        pts = []
        for (x, y, z, half) in line:
            g = grid(x, y) if grid is not None else None
            kind = rs.support_kind(z, g) if g is not None else "UNKNOWN"
            kinds[kind] = kinds.get(kind, 0) + 1
            gx, gy, gz = pe.godot((x, y, z))
            pts.append([gx, gy, gz, round(float(half), 4), None if g is None else round(float(g), 4), kind])
        out.append({"owner": str(owner), "points": pts})
    gate.update({"corridors": out, "kinds": kinds, "ground": bool(grid),
                 # The batter rules, from their one owner, so the stamp copies no constant.
                 "cut_slope": rs.CUT_SLOPE, "fill_slope": rs.FILL_SLOPE, "fill_max": rs.FILL_MAX,
                 "cut_max": rs.CUT_MAX})
    return gate


def _join_at_joints(net, lines, tol=0.05):
    """`[(line, owner)]` with the corridors of two roads that meet at a JOINT (two coincident stations
    of different roads, SEGMENT-linked -- `point_record_ops.split_at_joint`, the seeder's corner
    fillets) joined into ONE line. A joint is one road running on, and the stamp represents each
    corridor by its NEAREST segment: split into two corridors, a switchback's other leg stops being
    the same road and starts capping the hillside between the legs as if it were a second road
    (PLAN.md 3.10 measured it: the touge cut at its zone boundaries re-stamped 6088 vertices). The
    owner of a joined line is its first part's."""
    joints = []
    for p in net.points.values():
        for t in p.targets(pm.LINK_SEGMENT):
            q = net.points.get(t)
            if (q is not None and p.uid < q.uid and net.road_of(p.uid) is not net.road_of(q.uid)
                    and math.dist(p.pos[:2], q.pos[:2]) < tol):
                joints.append(p.pos)
    lines = [(list(l), o) for l, o in lines]

    def at(pt, j):
        return math.hypot(pt[0] - j[0], pt[1] - j[1]) < tol and abs(pt[2] - j[2]) < 0.5

    for j in joints:
        ends = [i for i, (l, _o) in enumerate(lines) if l and (at(l[0], j) or at(l[-1], j))]
        if len(ends) != 2 or lines[ends[0]][1] == lines[ends[1]][1]:
            continue
        (la, oa), (lb, _ob) = lines[ends[0]], lines[ends[1]]
        if at(la[0], j):
            la = la[::-1]
        if not at(lb[0], j):
            lb = lb[::-1]
        lines[ends[0]] = (la + lb[1:], oa)
        lines[ends[1]] = ([], "")
    return [(l, o) for l, o in lines if l]


def _left_offset(pts, dist):
    """`pts` pushed `dist[i]` metres to each vertex's LEFT in plan (Z-up), the tangent averaged over
    the two neighbouring chords. A DRAWING helper only: the footway's outer line in the draft."""
    out = []
    n = len(pts)
    for i, p in enumerate(pts):
        a, b = pts[max(i - 1, 0)], pts[min(i + 1, n - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ln = (dx * dx + dy * dy) ** 0.5 or 1.0
        out.append((p[0] - dy / ln * dist[i], p[1] + dx / ln * dist[i], p[2]))
    return out


def _flat(tris):
    return [c for t in tris for v in t for c in pe.godot(v)]


def cmd_bands(a):
    """B10.1: the DRAFT SURFACE -- exactly the footprints Build sweeps, from the solve Build runs
    (`point_edges.solve_all`), so the editor can show a junction's pad, setbacks, fillets and gores
    while it is being tweaked without a Blender round trip. Nothing here is geometry of its own: road
    triangles are the strip between `RoadSolve.edges_left/right`, a pad is `JunctionSolve.fan`, a gore
    is `GoreSolve.tris`, and the kerb/footway lines are `point_edges.*_edge_runs` -- the same runs the
    `__edges` carriers are swept on. Godot axes, the network's frame, flat `[x,y,z, ...]` arrays of
    whole triangles (`surface`, `walk`) and polylines (`kerbs`). `bands[i]` names the owner of
    triangles `tri_start .. tri_start + tri_count` of `surface[kind]` -- a road run's strip is
    `(L[i], R[i], R[i+1]), (L[i], R[i+1], L[i+1])`, so its end cross-sections are the first and last pair."""
    return _bands(pm.load_network(a.record), pg.load_ground(a.ground) if a.ground else None)


def _bands(net, grid):
    import time
    t0 = time.time()
    solves, jsolves, gsolves, bands = ped.solve_all(net, grid)
    surface, walk, kerbs, owners = {"road": [], "pad": [], "gore": []}, [], [], []
    runs = []
    for s in solves:
        L, R = s.edges_left, s.edges_right
        tris = []
        for i in range(len(L) - 1):
            tris += [(L[i], R[i], R[i + 1]), (L[i], R[i + 1], L[i + 1])]
        owners.append({"kind": "road", "owner": s.road.name, "uids": list(s.uids),
                       "tri_start": len(surface["road"]) // 9, "tri_count": len(tris)})
        surface["road"] += _flat(tris)
        runs += ped.road_edge_runs(s, bands)
    for j in jsolves:
        owners.append({"kind": "pad", "owner": "JCT:" + j.uids[0][:8], "uids": list(j.uids),
                       "tri_start": len(surface["pad"]) // 9, "tri_count": len(j.fan)})
        surface["pad"] += _flat(j.fan)
        runs += ped.junction_edge_runs(j)
    for g in gsolves:
        owners.append({"kind": "gore", "owner": "GORE:" + g.ramp_uid[:8], "uids": [g.main_uid, g.ramp_uid],
                       "tri_start": len(surface["gore"]) // 9, "tri_count": len(g.tris)})
        surface["gore"] += _flat(g.tris)
        runs += ped.gore_edge_runs(g)
    for _sfx, pts, w, k, _wall, sgn in runs:
        top = [(p[0], p[1], p[2] + float(k[i])) for i, p in enumerate(pts)]
        kerbs.append([c for p in top for c in pe.godot(p)])
        if any(float(x) > 1e-6 for x in w):
            outer = _left_offset(top, [sgn * 2.0 * float(x) for x in w])
            kerbs.append([c for p in outer for c in pe.godot(p)])
            for i in range(len(top) - 1):
                walk += _flat([(top[i], outer[i], outer[i + 1]), (top[i], outer[i + 1], top[i + 1])])
    return {"surface": surface, "walk": walk, "kerbs": kerbs, "bands": owners,
            "counts": {"roads": len(solves), "pads": len(jsolves), "gores": len(gsolves),
                       "edge_runs": len(runs)},
            "ms": round((time.time() - t0) * 1000.0, 1)}


def _mesh_by_material(net, grid):
    """B11: what Build will sweep, for the editor to SHOW -- every visible triangle of the whole network from the
    same `point_mesh.build` the piece glTF is written from (collision proxies left out), grouped by material
    name, Godot axes, flat `[x, y, z, ...]` rounded to the millimetre."""
    import time
    t0 = time.time()
    by_mat, tris = {}, 0
    for name, mats in pmsh.build(net, grid).items():
        if pmsh.SUFFIX_COL in name:
            continue
        for mat, ts in mats.items():
            flat = by_mat.setdefault(mat, [])
            flat += [round(c, 3) for t in ts for p in t for c in pe.godot(p)]
            tris += len(ts)
    return {"materials": by_mat, "tris": tris, "ms": round((time.time() - t0) * 1000.0, 1)}


def cmd_mesh(a):
    """B10.7 SPIKE: the whole network's meshes from the pure-Python sweep (`point_mesh`), Godot axes, the
    network's frame: `{"objects": {name: {material: [x,y,z, ...] (whole triangles)}}, "ms", "tris"}`.
    What a Godot-side build would upload; measured against the Blender build by `roadkit_mesh_parity.py`."""
    import time
    t0 = time.time()
    net = pm.load_network(a.record)
    objs = pmsh.build(net, pg.load_ground(a.ground) if a.ground else None)
    out, tris = {}, 0
    for name, mats in objs.items():
        out[name] = {}
        for mat, ts in mats.items():
            out[name][mat] = [round(c, 4) for t in ts for p in t for c in pe.godot(p)]
            tris += len(ts)
    return {"objects": out, "tris": tris, "ms": round((time.time() - t0) * 1000.0, 1)}


def cmd_gltf(a):
    """B11: the road build without Blender. Cuts the network by zone (`point_zones`, the same cut `pieces` writes
    the lanekits by), sweeps each piece in pure Python (`point_mesh`, styles and profile assets from
    `road_kit.json`) and writes `<out_dir>/<piece>.gltf` (`point_gltf`) -- the file `build_piece.sh` bakes.
    `--only` names the pieces to write (the dirty ones); a red gate writes nothing."""
    import time
    t0 = time.time()
    net = pm.load_network(a.record)
    zones = pz.load_zones(a.zones) if a.zones and os.path.exists(a.zones) else []
    # `--gated`: the caller ran the gate on this record already (`build_roads_piece.sh` runs `pieces` first, which
    # refuses a red one) -- it is most of this command's time, and the same answer twice.
    gate = {"errors": 0, "warnings": 0, "findings": []} if a.gated else _findings(net)
    if gate["errors"]:
        gate.update({"written": False, "pieces": []})
        return gate
    part = pz.partition(net, zones)
    grid = pg.load_ground(a.ground) if a.ground else None
    kit = pk.load()
    solved = ped.solve_all(net, grid)
    only = {n for n in a.only.split(",") if n}
    report, pieces = {}, []
    # PLAN.md 3.6c: decals and street furniture. The lane-based marks read the lanekits `pieces` wrote (step 1 of
    # build_roads_piece.sh) -- ALL of this network's, because a mouth's connectors stream with the pad's piece.
    table = None if a.no_furniture else pfu.load()
    lanekit_dir = a.lanekits or os.path.dirname(os.path.abspath(a.record))
    lanes_doc, missing_lanekits = {"lanes": [], "junctions": []}, []
    if table is not None:
        for zone in sorted(part.pieces()):
            lk = os.path.join(lanekit_dir, pz.piece_name(a.prefix, zone) + ".lanekit.json")
            if not os.path.exists(lk):
                missing_lanekits.append(lk)
                continue
            with open(lk) as fh:
                d = json.load(fh)
            lanes_doc["lanes"] += d.get("lanes", [])
            lanes_doc["junctions"] += d.get("junctions", [])
    styles = {n: pk.resolve(r, kit) for n, r in net.roads.items()}
    default_mark = pk.resolve(object(), kit).material("mark_w")

    def mark_mat(lane):
        st = styles.get(lane.get("road_name"))
        return st.material("mark_w") if st is not None else default_mark

    # the lines stop at the stop line and the zebra: the same arm frames the marks below are placed from
    clear = pfu.clear_zones(table, lanes_doc)
    for zone in sorted(part.pieces()):
        piece = pz.piece_name(a.prefix, zone)
        if only and piece not in only:
            continue
        objs = pmsh.build(net, grid, part if zones else None, zone, kit, report, solved, clear)
        fur = pfu.place(table, solved, lanes_doc,
                        (lambda l, z=zone: l.get("zone_id", pz.RESIDENT) == z) if zones else (lambda l: True),
                        (lambda s, z=zone: part.run_zone(s.uids) == z) if zones else (lambda s: True),
                        (lambda j, z=zone: part.pad_zone(j.uids) == z) if zones else (lambda j: True),
                        mark_mat, grid)
        for mat, tris in fur.paint.items():
            objs.setdefault(pfu.PAINT_OBJECT, {}).setdefault(mat, []).extend(tris)
        if fur.collision:
            objs.setdefault(pfu.COLLISION_OBJECT, {}).setdefault(pfu.NO_MATERIAL, []).extend(fur.collision)
        path = os.path.join(a.out_dir, piece + ".gltf")
        row = dict(pgl.write(objs, kit, path, markers=fur.placements), zone=zone, piece=piece, gltf=path,
                   furniture=dict(sorted(fur.counts.items())))
        pieces.append(row)
    gate.update({"written": True, "pieces": pieces, "kit_stale": kit.stale(), "kit": kit.path,
                 "missing_style": sorted(set(tuple(m) for m in report.get("missing_style", []))),
                 "pier_overhang": sorted(set(tuple(m) for m in report.get("pier_overhang", []))),
                 "missing_lanekits": missing_lanekits,
                 "ms": round((time.time() - t0) * 1000.0, 1)})
    return gate


def cmd_ramp(a):
    """`Make Ramp` + `Align Ramp To Aux` on the record (`point_record_ops.make_ramp`)."""
    net = pm.load_network(a.record)
    res = ro.make_ramp(net, a.uid_a, a.uid_b, a.lanes)
    pm.save_network(net, a.record)
    out = _findings(net)
    out.update(res)
    return out


def _record_op(fn):
    """B8: a gesture from `point_record_ops` over the record -- load, apply, save, report. A refused
    gesture (`GestureError`) is a result, not a crash, and writes nothing."""
    def run(a):
        net = pm.load_network(a.record)
        try:
            msg, extra = fn(net, a)
        except ro.GestureError as e:
            return {"failed": True, "error": str(e)}
        pm.save_network(net, a.record)
        out = _findings(net)
        out.update(extra)
        out["message"] = msg
        return out
    return run


def _uids(s):
    return [u for u in s.split(",") if u]


cmd_merge = _record_op(lambda net, a: ro.merge_points(net, _uids(a.uids), a.keep or None, a.at_keep))
cmd_split = _record_op(lambda net, a: ro.split_road(net, _uids(a.uids), a.name))
cmd_renumber = _record_op(lambda net, a: ro.renumber_roads(net))
cmd_repair = _record_op(lambda net, a: ro.repair_links(net))
cmd_tidy = _record_op(lambda net, a: ro.tidy_roads(net))
cmd_cross_section = _record_op(lambda net, a: ro.apply_cross_section(net, a.src, _uids(a.uids), _uids(a.groups)))
cmd_branch_ramp = _record_op(lambda net, a: ro.branch_ramp(
    net, a.uid, a.name, a.lanes, a.carriageway, a.entrance, a.length, a.spread, a.drop))


def cmd_facings(a):
    """`{uid: [x, y, z]}` in GODOT axes -- the facing the tool gives every point it owns."""
    net = pm.load_network(a.record)
    return {"facings": {u: pe.godot(v) for u, v in ro.facings(net).items()}}


def cmd_live(a):
    """THE EDITOR'S LIVE REFRESH, in one process: `centrelines` (with `--zones`), `bands` (with
    `--draft`) and `facings`, each over its own fresh read of the record. Without `--cross` the
    cross-zone successor edges are skipped -- they need the gate and a full lane export, seconds on a
    real network, which is what froze the editor on every pause of a drag. `--mesh` (B11, sent once a drag is
    RELEASED) adds the full swept mesh Build will write (`_mesh_by_material`). `junctions` names every pad:
    its centre (Godot axes) and its mouths, for the viewport's junction labels."""
    import time
    t0 = time.time()
    out = {"centrelines": _centrelines(pm.load_network(a.record), a.step, a.zones, cross=a.cross)}
    if a.draft:
        out["bands"] = _bands(pm.load_network(a.record), None)
    if a.mesh:
        out["mesh"] = _mesh_by_material(pm.load_network(a.record), pg.load_ground(a.ground) if a.ground else None)
    net = pm.load_network(a.record)
    out["facings"] = {u: pe.godot(v) for u, v in ro.facings(net).items()}
    out["junctions"] = [{"uids": list(c), "centre": pe.godot(
        (sum(net.points[m].pos[0] for m in c) / len(c), sum(net.points[m].pos[1] for m in c) / len(c),
         sum(net.points[m].pos[2] for m in c) / len(c)))} for c in net.junction_cliques()]
    out["ms"] = round((time.time() - t0) * 1000.0, 1)
    return out


def cmd_flow(a):
    """Preview > Flow Report over the exported lane graph (`point_flow.flow_report`), uids resolved."""
    net = pm.load_network(a.record)
    gate = _findings(net)
    if gate["errors"]:
        gate["report"] = None
        return gate
    rep = pf.flow_report(pe.export_network(net))
    gate["report"] = rep
    return gate


def main(argv=None):
    ap = argparse.ArgumentParser(prog="roadkit_cli.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("validate"); s.add_argument("record"); s.set_defaults(fn=cmd_validate)
    s = sub.add_parser("setback"); s.add_argument("record")
    s.add_argument("--margin", type=float, default=2.0); s.set_defaults(fn=cmd_setback)
    s = sub.add_parser("centrelines"); s.add_argument("record")
    s.add_argument("--step", type=float, default=None); s.add_argument("--zones", default="")
    s.set_defaults(fn=cmd_centrelines)
    s = sub.add_parser("live"); s.add_argument("record")
    s.add_argument("--step", type=float, default=None); s.add_argument("--zones", default="")
    s.add_argument("--draft", action="store_true"); s.add_argument("--cross", action="store_true")
    s.add_argument("--mesh", action="store_true"); s.add_argument("--ground", default="")
    s.set_defaults(fn=cmd_live)
    s = sub.add_parser("corridors"); s.add_argument("record"); s.add_argument("--ground", default="")
    s.set_defaults(fn=cmd_corridors)
    s = sub.add_parser("mesh"); s.add_argument("record"); s.add_argument("--ground", default=""); s.set_defaults(fn=cmd_mesh)
    s = sub.add_parser("gltf"); s.add_argument("record"); s.add_argument("zones"); s.add_argument("out_dir")
    s.add_argument("prefix"); s.add_argument("--ground", default=""); s.add_argument("--only", default="")
    s.add_argument("--gated", action="store_true"); s.add_argument("--lanekits", default="")
    s.add_argument("--no-furniture", action="store_true"); s.set_defaults(fn=cmd_gltf)
    s = sub.add_parser("bands"); s.add_argument("record"); s.add_argument("--ground", default="")
    s.set_defaults(fn=cmd_bands)
    s = sub.add_parser("lanekit"); s.add_argument("record"); s.add_argument("out")
    s.set_defaults(fn=cmd_lanekit)
    s = sub.add_parser("ramp"); s.add_argument("record"); s.add_argument("uid_a"); s.add_argument("uid_b")
    s.add_argument("--lanes", type=int, default=1); s.set_defaults(fn=cmd_ramp)
    s = sub.add_parser("pieces"); s.add_argument("record"); s.add_argument("zones")
    s.add_argument("out_dir"); s.add_argument("prefix"); s.add_argument("--dry-run", action="store_true")
    s.add_argument("--ground", default="")
    s.set_defaults(fn=cmd_pieces)
    s = sub.add_parser("merge"); s.add_argument("record"); s.add_argument("uids")
    s.add_argument("--keep", default=""); s.add_argument("--at-keep", action="store_true")
    s.set_defaults(fn=cmd_merge)
    s = sub.add_parser("split"); s.add_argument("record"); s.add_argument("uids")
    s.add_argument("--name", default=""); s.set_defaults(fn=cmd_split)
    for n, fn in (("renumber", cmd_renumber), ("repair", cmd_repair), ("tidy", cmd_tidy),
                  ("facings", cmd_facings), ("flow", cmd_flow)):
        s = sub.add_parser(n); s.add_argument("record"); s.set_defaults(fn=fn)
    s = sub.add_parser("cross_section"); s.add_argument("record"); s.add_argument("src")
    s.add_argument("uids"); s.add_argument("groups"); s.set_defaults(fn=cmd_cross_section)
    s = sub.add_parser("branch_ramp"); s.add_argument("record"); s.add_argument("uid")
    s.add_argument("--name", default=""); s.add_argument("--lanes", type=int, default=1)
    s.add_argument("--carriageway", default="FWD", choices=("FWD", "BWD"))
    s.add_argument("--entrance", action="store_true")
    s.add_argument("--length", type=float, default=80.0); s.add_argument("--spread", type=float, default=25.0)
    s.add_argument("--drop", type=float, default=0.0); s.set_defaults(fn=cmd_branch_ramp)
    a = ap.parse_args(argv)
    try:
        out = a.fn(a)
    except Exception as e:                                           # a broken record is a result too
        json.dump({"failed": True, "error": "%s: %s" % (type(e).__name__, e)}, sys.stdout)
        sys.stdout.write("\n")
        return 2
    json.dump(out, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
