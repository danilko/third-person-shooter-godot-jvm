"""point_digest.py -- WHICH PIECES A BUILD MUST REDO (PLAN.md 3.1 B10.6).

A zoned build sweeps one piece per zone in Blender and bakes each in Godot, ~20 s a piece. Editing one
junction should not rebuild the island. But "which zones did the edit touch" is NOT a record diff: the
whole network is solved for every piece -- a kerb opens against a neighbour's asphalt, a pad corner grows
for another road's turn (`point_solve.contain_turns`), a ramp's gore belongs to the ramp's zone -- so a
point moved in one zone can change geometry in the next.

So the question is asked of the OUTPUT. `piece_digests` hashes, per piece, everything that piece EMITS,
taken from the same solve the build runs (`point_edges.solve_all`) and the same cut
(`point_zones.partition`): each of its runs' carrier samples and per-sample values, its kerb/footway edge
runs, its marking runs, its pads (ring, triangles, corners) and gores, its own lanekit (`split_doc`), and
the authored fields of every road it draws from (style slots live there). Plus a SALT: the source of the
modules that turn those numbers into meshes, so changing the builder dirties everything. A piece whose
digest matches the one recorded when it was last baked is not rebuilt. Floats are rounded to 0.1 mm, so
re-solving an unchanged record reproduces every digest exactly.
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "lib"))

try:
    from . import point_model as pm, point_solve as ps, point_edges as ped, point_export as pe, point_zones as pz
except ImportError:
    import point_model as pm                                                 # noqa: E402
    import point_solve as ps                                                 # noqa: E402
    import point_edges as ped                                                # noqa: E402
    import point_export as pe                                                # noqa: E402
    import point_zones as pz                                                 # noqa: E402

#: The modules whose source decides what a piece LOOKS like once its numbers are fixed -- since B11 the pure-Python
#: build (`point_mesh` sweeps, `point_gltf` writes, `point_kit` resolves styles), not `point_build`'s node groups.
BUILDER_SOURCES = ("point_mesh.py", "point_gltf.py", "point_kit.py", "point_style.py", "point_solve.py",
                   "point_edges.py", "point_export.py", "point_zones.py", "point_profile.py",
                   os.path.join("..", "..", "lib", "lane_profile.py"), os.path.join("..", "..", "lib", "road_support.py"),
                   os.path.join("..", "..", "lib", "lane_movements.py"),
                   os.path.join("..", "..", "tools", "roadkit_cli.py"), "point_furniture.py")

#: The kit as the build reads it: its materials and profile sections (`road_kit.json`, written from road_kit.blend).
BUILDER_ASSETS = (os.path.join("..", "..", "..", "assets", "world_source", "kits", "road_kit", "road_kit.json"),)

#: The Godot material library the bake resolves road materials from by name (WorldBaker.MATERIAL_LIBRARY_DIR).
MATERIAL_LIBRARY = os.path.join("..", "..", "..", "assets", "world_source", "kits", "road_kit", "materials")


def _canon(v):
    """JSON-ready, floats rounded to 0.1 mm, so the same solve always hashes the same."""
    if isinstance(v, float):
        return round(v, 4) + 0.0
    if isinstance(v, dict):
        return {str(k): _canon(x) for k, x in sorted(v.items(), key=lambda kv: str(kv[0]))}
    if isinstance(v, (list, tuple)):
        return [_canon(x) for x in v]
    if hasattr(v, "__slots__"):
        return {s: _canon(getattr(v, s, None)) for s in v.__slots__}
    return v


def builder_salt():
    h = hashlib.sha1()
    for rel in BUILDER_SOURCES:
        path = os.path.normpath(os.path.join(HERE, rel))
        h.update(rel.encode())
        if os.path.exists(path):
            with open(path, "rb") as fh:
                h.update(fh.read())
    for rel in BUILDER_ASSETS:
        path = os.path.normpath(os.path.join(HERE, rel))
        if os.path.exists(path):
            h.update(rel.encode())
            with open(path, "rb") as fh:
                h.update(fh.read())
    # The bake's material library (WorldBaker.MATERIAL_LIBRARY_DIR, PLAN.md 3.6c): which names it covers
    # decides what a baked piece references, so adding or removing a file must rebake.
    lib = os.path.normpath(os.path.join(HERE, MATERIAL_LIBRARY))
    if os.path.isdir(lib):
        for name in sorted(os.listdir(lib)):
            if name.endswith(".tres"):
                h.update(name.encode())
                with open(os.path.join(lib, name), "rb") as fh:
                    h.update(fh.read())
    # PLAN.md 3.6c: the furniture table and every kit piece it places (their bounds decide where a piece stands).
    try:
        from . import point_furniture as pfu
    except ImportError:
        import point_furniture as pfu                                        # noqa: E402
    table = pfu.load()
    for path in (table.files() if table is not None else ()):
        if os.path.exists(path):
            h.update(os.path.relpath(path, pfu.REPO).encode())
            with open(path, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


def piece_digests(net, zones, ground=None):
    """`{zone_id: sha1}` for every piece `point_zones.partition(net, zones)` cuts (the resident piece is
    `point_zones.RESIDENT`). Without zones the network is one piece, keyed `point_zones.RESIDENT`."""
    part = pz.partition(net, zones)
    solves, jsolves, gsolves, bands = ped.solve_all(net, ground)
    doc = pe.export_network(net)
    if zones:
        pz.stamp_lanes(doc, part, net)
    roads = {r["name"]: r for r in pm.network_to_dict(net)["roads"]}
    salt = builder_salt()
    per = {z: {"runs": [], "pads": [], "gores": [], "roads": set()} for z in part.pieces()}
    for s in solves:
        z = part.run_zone(s.uids)
        if z not in per:
            continue
        per[z]["roads"].add(s.road.name)
        per[z]["runs"].append({
            "road": s.road.name, "uids": list(s.uids),
            "samples": [tuple(sm.pos) for sm in s.samples], "values": s.values,
            "edges": ped.road_edge_runs(s, bands), "marks": ps.solve_marks(s)})
    for j in jsolves:
        z = part.pad_zone(j.uids)
        if z in per:
            per[z]["pads"].append({"uids": list(j.uids), "boundary": j.boundary, "fan": j.fan,
                                   "edges": ped.junction_edge_runs(j)})
            per[z]["roads"].update(r.name for r in (net.road_of(u) for u in j.uids) if r is not None)
    for g in gsolves:
        z = part.gore_zone(g.ramp_uid)
        if z in per:
            per[z]["gores"].append({"ramp": g.ramp_uid, "tris": g.tris, "edges": ped.gore_edge_runs(g)})
    # a successor's turn picks the arrow, and a straight connector's END places the far-side signal (PLAN.md 3.6c)
    turns = {l["id"]: [l.get("turn", ""), [round(float(x), 3) for x in (l.get("points") or [[0, 0, 0]])[-1]]]
             for l in doc.get("lanes", ())}
    out = {}
    for z, content in per.items():
        sub = pz.split_doc(doc, z) if zones else doc
        # a lane's turn arrow is chosen by its successors' turns, and a successor connector may stream with
        # another piece (the pad's) -- so each lane's successor turns are part of THIS piece too (PLAN.md 3.6c)
        succ = [[l["id"], sorted((n, turns.get(n, "")) for n in l.get("next", ()))] for l in sub.get("lanes", ())]
        body = {"salt": salt, "runs": content["runs"], "pads": content["pads"], "gores": content["gores"],
                "roads": [roads[n] for n in sorted(content["roads"]) if n in roads], "lanekit": sub,
                "successor_turns": succ}
        out[z] = hashlib.sha1(json.dumps(_canon(body), sort_keys=True).encode()).hexdigest()
    return out


def self_test():
    try:
        from . import point_validate as pv
    except ImportError:
        import point_validate as pv                                          # noqa: E402
    net, mp, cp, rr = pv.build_testbed()
    a = piece_digests(net, [])
    b = piece_digests(net, [])
    assert a == b and len(a) == 1, (a, b)
    print("OK: re-solving an unchanged network reproduces every digest")
    # Two zones cutting the testbed's main road at its crossing; a station moved far out in the EAST
    # piece changes that piece and leaves the WEST one alone.
    zones = [pz.ZoneBox("west", (60.0, 0.0), (130.0, 200.0), 400.0, 600.0),
             pz.ZoneBox("east", (440.0, 0.0), (250.0, 200.0), 400.0, 600.0)]
    before = piece_digests(net, zones)
    assert "west" in before and "east" in before, before
    far = mp[5]
    far.pos = (far.pos[0], far.pos[1] + 3.0, far.pos[2])
    after = piece_digests(net, zones)
    assert after["east"] != before["east"], "the edited piece is dirty"
    assert after["west"] == before["west"], "a piece the edit cannot reach stays clean"
    print("OK: a station moved in one zone dirties that piece only (%d pieces)" % len(after))
    far.pos = (far.pos[0], far.pos[1] - 3.0, far.pos[2])
    assert piece_digests(net, zones) == before, "moving it back restores every digest"
    print("OK: undoing the edit restores the digests")
    return 3


if __name__ == "__main__":
    n = self_test()
    print("point_digest.py: %d checks PASS" % n)
