#!/usr/bin/env python3
"""roadkit_cli.py -- the road kit's SOLVER as a plain-python3 service for the Godot editor plugin.

PLAN.md 3.1 option B: roads are AUTHORED in Godot (`addons/road_kit/`), the kit's data model, gate,
junction solve and lane export run HERE with no Blender, and Blender is only the headless mesh sweep
(`roadkit_build_mesh.py`). Everything this imports already ran under plain python3 -- it is what
`check_roads.sh` stage 1 tests -- so this file adds no logic, only a door.

Every command reads a `.roads.json` record (the kit's own schema, `point_model.network_to_dict`, in
the kit's Z-up frame) and prints ONE JSON object on stdout. Coordinates it hands back for DRAWING
are already in Godot's frame (`point_export.godot`, the one conversion site) so the plugin never
converts a preview; the record itself stays in the kit's frame, converted once by the plugin's IO.

    python3 blender/tools/roadkit_cli.py validate    <record>
    python3 blender/tools/roadkit_cli.py setback     <record> [--margin 2.0]   (rewrites the record)
    python3 blender/tools/roadkit_cli.py centrelines <record> [--step 4.0] [--zones <zones.json>]
    python3 blender/tools/roadkit_cli.py lanekit     <record> <out.lanekit.json>
    python3 blender/tools/roadkit_cli.py corridors   <record> [--ground <stem>.ground.json]
    python3 blender/tools/roadkit_cli.py ramp        <record> <uid_a> <uid_b> [--lanes 1]   (rewrites the record)
    python3 blender/tools/roadkit_cli.py pieces      <record> <zones.json> <out_dir> <prefix> [--dry-run]
    python3 blender/tools/roadkit_cli.py merge|split <record> <uid,uid,...> [--keep uid --at-keep | --name n]
    python3 blender/tools/roadkit_cli.py renumber|repair|tidy <record>           (rewrite the record)
    python3 blender/tools/roadkit_cli.py cross_section <record> <src> <uid,...> <LANES,WIDTH,...>
    python3 blender/tools/roadkit_cli.py branch_ramp <record> <uid> [--lanes 1 --carriageway FWD --entrance ...]
    python3 blender/tools/roadkit_cli.py facings|flow <record>

Exit code 0 unless the command itself failed (a red gate is a RESULT, reported in the JSON).
"""
import argparse
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
    moved = []
    for uids in net.junction_cliques():
        for uid, old, new in ps.auto_setback(net, uids, a.margin):
            moved.append({"uid": uid, "old": old, "new": new})
    pm.save_network(net, a.record)
    # Every mouth's solved distance and position, moved or not, so the plugin can write back the
    # derived `setback_solved` too -- it is shown on the point and must not go stale.
    mouths = {u: {"pos": list(net.points[u].pos), "setback_solved": net.points[u].setback_solved}
              for c in net.junction_cliques() for u in c}
    return {"moved": moved, "mouths": mouths, "cliques": len(net.junction_cliques())}


def cmd_centrelines(a):
    """The overlay's picture. With `--zones` (B6c) each run also says which zone `point_zones` cuts
    it into and whether it reaches past that zone's load radius (`beyond`), and `cross` lists every
    successor edge that leaves its lane's zone, with the lane's points -- the hand-overs that only
    resolve while both pieces are loaded. Everything here is asked of `point_zones`, never derived."""
    net = pm.load_network(a.record)
    zones = pz.load_zones(a.zones) if a.zones and os.path.exists(a.zones) else []
    part = pz.partition(net, zones) if zones else None
    beyond = {f["obj"] for f in part.findings if f["code"] == "zone_beyond_load"} if part else set()
    out = []
    for name, pts, uids in pp.centreline_runs(net, step=a.step, with_uids=True):
        row = {"road": name, "points": [pe.godot(p) for p in pts]}
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
        cross = []
        if not _findings(net)["errors"]:
            doc = pe.export_network(net)
            pz.stamp_lanes(doc, part, net)
            by_id = {l["id"]: l for l in doc.get("lanes", ())}
            for lane, nxt in pz.cross_zone_report(doc)[0]:
                cross.append({"lane": lane, "next": nxt, "zone": by_id[lane].get("zone_id", pz.RESIDENT),
                              "next_zone": by_id[nxt].get("zone_id", pz.RESIDENT),
                              "points": by_id[lane].get("points", [])})
        res["cross"] = cross
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
    pieces = []
    for zone in sorted(counts):
        sub = pz.split_doc(doc, zone) if zones else doc
        piece = pz.piece_name(a.prefix, zone)
        path = os.path.join(a.out_dir, piece + ".lanekit.json")
        row = dict(counts[zone], zone=zone, piece=piece, lanes=len(sub.get("lanes", ())),
                   junctions=len(sub.get("junctions", ())), lanekit=path)
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
    for line, _half, owner in ped.band_corridors(bands, owners=True):
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
    s = sub.add_parser("corridors"); s.add_argument("record"); s.add_argument("--ground", default="")
    s.set_defaults(fn=cmd_corridors)
    s = sub.add_parser("lanekit"); s.add_argument("record"); s.add_argument("out")
    s.set_defaults(fn=cmd_lanekit)
    s = sub.add_parser("ramp"); s.add_argument("record"); s.add_argument("uid_a"); s.add_argument("uid_b")
    s.add_argument("--lanes", type=int, default=1); s.set_defaults(fn=cmd_ramp)
    s = sub.add_parser("pieces"); s.add_argument("record"); s.add_argument("zones")
    s.add_argument("out_dir"); s.add_argument("prefix"); s.add_argument("--dry-run", action="store_true")
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
