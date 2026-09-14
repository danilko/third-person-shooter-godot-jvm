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
    python3 blender/tools/roadkit_cli.py centrelines <record> [--step 4.0]
    python3 blender/tools/roadkit_cli.py lanekit     <record> <out.lanekit.json>
    python3 blender/tools/roadkit_cli.py ramp        <record> <uid_a> <uid_b> [--lanes 1]   (rewrites the record)
    python3 blender/tools/roadkit_cli.py pieces      <record> <zones.json> <out_dir> <prefix> [--dry-run]

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
    net = pm.load_network(a.record)
    runs = pp.centreline_runs(net, step=a.step)
    return {"runs": [{"road": name, "points": [pe.godot(p) for p in pts]} for name, pts in runs]}


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


def _declares_aux(p):
    return int(p.aux_fwd) + int(p.aux_bwd) > 0


def resolve_aux_pair(net, a, b):
    """`(mainline_uid, ramp_uid)` -- `point_ops.resolve_aux_pair`'s scoring over record points, so
    which point is the mainline is a fact about the two points, never click order."""
    pa, pb = net.points[a], net.points[b]

    def score(main, ramp):
        s = 0
        if _declares_aux(main):
            s += 3
        if pm.is_ramp_role(ramp.role):
            s += 2
        if pm.is_ramp_role(main.role):
            s -= 2
        if _declares_aux(ramp):
            s -= 1
        if ramp.lanes_bwd == 0 or ramp.lanes_fwd == 0:
            s += 1
        if main.lanes_bwd == 0 or main.lanes_fwd == 0:
            s -= 1
        return s
    return (a, b) if score(pa, pb) >= score(pb, pa) else (b, a)


def open_aux_slot(net, main_uid, lanes, field, entrance):
    """`point_ops.open_aux_slot` over the record: open the slot back along the run to the first span
    long enough for the taper the gate asks for (`point_validate.taper_min_length`), so a one-click
    ramp does not leave the gate red. Returns `(stations, span, want)`."""
    road = net.road_of(main_uid)
    res = net.resolved(main_uid)
    width = lanes * res.lane_width
    want = pv.taper_min_length(width, res.design_speed, getattr(road, "taper_factor", 1.0))
    run = pm.run_of(net, main_uid)
    step = -1 if (field == "aux_fwd") != bool(entrance) else 1
    j, chain, span = run.index(main_uid), [main_uid], 0.0
    while True:
        p = net.points[chain[-1]]
        setattr(p, field, max(getattr(p, field), lanes))
        k = j + step
        if not (0 <= k < len(run)):
            span = 0.0
            break
        a, b = net.points[run[j]].pos, net.points[run[k]].pos
        span = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5
        if span >= want:
            break
        chain.append(run[k])
        j = k
    return len(chain), span, want


def cmd_ramp(a):
    """`Make Ramp` + `Align Ramp To Aux` (point_ops) on the record: AUX link mainline -> ramp, the
    ramp one-way and typed RAMP, the aux slot opened on the carriageway the mouth is on and back to a
    taper-length span, and the mouth placed on the gore line facing down the mainline."""
    net = pm.load_network(a.record)
    main_uid, ramp_uid = resolve_aux_pair(net, a.uid_a, a.uid_b)
    main, ramp = net.points[main_uid], net.points[ramp_uid]
    ramp.role = pm.RAMP
    if not ramp.lanes_fwd and not ramp.lanes_bwd:
        ramp.lanes_fwd = a.lanes
    elif ramp.lanes_fwd and ramp.lanes_bwd:
        ramp.lanes_bwd = 0
    ramp.profile_mode = pm.OVERRIDE
    field = "aux_fwd" if ps.ramp_carriageway(net, main_uid, ramp.pos) == lp.FWD else "aux_bwd"
    net.unlink(main_uid, ramp_uid)
    net.link(main_uid, ramp_uid, pm.LINK_AUX)
    entrance = pm.ramp_is_entrance(net, ramp_uid)
    stations, span, want = open_aux_slot(net, main_uid, a.lanes, field, entrance)
    got = ps.ramp_target(net, main_uid, ramp_uid)
    aligned = got is not None
    if aligned:
        pos, ax, _side = got
        ax = ps.ramp_facing(net, main_uid, ramp_uid) or ax
        ramp.pos = tuple(pos)
        ramp.tangent_mode = pm.MANUAL
        ramp.tangent = (ax[0], ax[1], 0.0)
    pm.save_network(net, a.record)
    out = _findings(net)
    out.update({"mainline": main_uid, "ramp": ramp_uid, "field": field, "entrance": entrance,
                "slot_stations": stations, "taper_span": span, "taper_want": want, "aligned": aligned})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="roadkit_cli.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("validate"); s.add_argument("record"); s.set_defaults(fn=cmd_validate)
    s = sub.add_parser("setback"); s.add_argument("record")
    s.add_argument("--margin", type=float, default=2.0); s.set_defaults(fn=cmd_setback)
    s = sub.add_parser("centrelines"); s.add_argument("record")
    s.add_argument("--step", type=float, default=None); s.set_defaults(fn=cmd_centrelines)
    s = sub.add_parser("lanekit"); s.add_argument("record"); s.add_argument("out")
    s.set_defaults(fn=cmd_lanekit)
    s = sub.add_parser("ramp"); s.add_argument("record"); s.add_argument("uid_a"); s.add_argument("uid_b")
    s.add_argument("--lanes", type=int, default=1); s.set_defaults(fn=cmd_ramp)
    s = sub.add_parser("pieces"); s.add_argument("record"); s.add_argument("zones")
    s.add_argument("out_dir"); s.add_argument("prefix"); s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_pieces)
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
