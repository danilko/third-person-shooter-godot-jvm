#!/usr/bin/env python3
"""layout_cache.py -- a content-addressed cache for the island layout's generator steps (island_layout.run).

The layout is a chain of generators, each rewriting the road record: coast road -> touge -> dike -> expressway ->
core streets -> streets -> site access -> turnarounds -> setback rounds -> grades -> weld. Edit one generator (or its
data) and every step BEFORE it gets the same input, the same code and the same data as last time -- so its output is
the same, and replaying it from here costs a file copy instead of minutes. The chain re-runs from the first step whose
key changed; everything after it misses naturally, because its input record differs.

A step's KEY hashes:
  * its argv, with each argument that names an existing file replaced by that file's bytes (the record it reads);
  * the SOURCE of its script and every repo module it imports, transitively (`closure`), so an edit to
    island_streets.py re-runs streets onward and nothing before;
  * the DATA the generators read that is not on their command line (`DATA`): the land grid, the plan's JSON inputs,
    the rail reserve, the frozen sites, the kit tables -- hashed once per layout run;
  * the current bytes of the VOLATILE files (`VOLATILE`): read AND written by steps inside the chain (the dike
    corridor), so they are part of the input at the moment the step runs, and their after-state is part of its output.
A hit restores the step's output record, the volatile files' after-state and its stdout. The cache lives outside the
repo (`$XDG_CACHE_HOME/openworld_island_layout`, the newest `KEEP` entries). `island_layout.py --no-cache` or
LAYOUT_CACHE=0 turns it off; a data file a generator reads and `DATA` does not name would make a hit stale, so add it
there when a generator starts reading a new file.
"""
import ast
import hashlib
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
SEARCH = [os.path.join(ROOT, d) for d in ("tools", "blender/addons/road_kit_authoring", "blender/tools",
                                          "assets/world_source/lib", "blender/lib")]
W = os.path.join(ROOT, "assets", "world_source")
DATA = ["terrain/island_land.f32", "island_dike.json", "island_coast.json",
        "buildings/IslandRailReserve.json", "buildings/IslandSites.json", "buildings/IslandCivicSites.json",
        "buildings/building_types.json",
        "pieces/IslandRoads.arterials.roads.json", "pieces/IslandCoastRoad.json", "pieces/IslandTouge.json",
        "pieces/IslandRail.roads.json",
        "kits/road_kit/road_kit.json", "kits/road_kit/furniture.json"]
VOLATILE = ["island_dike_line.json"]
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "openworld_island_layout")
KEEP = 400


def _sha_file(path, h):
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)


def _module(name):
    for d in SEARCH:
        for cand in (os.path.join(d, name + ".py"), os.path.join(d, name, "__init__.py")):
            if os.path.exists(cand):
                return cand
    return None


_CLOSURE = {}


def closure(script):
    """Every repo source file `script` imports, transitively (by module name against `SEARCH`)."""
    if script in _CLOSURE:
        return _CLOSURE[script]
    seen, todo = set(), [os.path.abspath(script)]
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        try:
            tree = ast.parse(open(f).read())
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    names = [node.module.split(".")[0]]
                if node.level or not node.module:          # `from . import x`: x is a sibling module
                    names += [a.name for a in node.names]
            for n in names:
                p = _module(n)
                if p and p not in seen:
                    todo.append(p)
    _CLOSURE[script] = sorted(seen)
    return _CLOSURE[script]


_DATA_SALT = None


def data_salt():
    global _DATA_SALT
    if _DATA_SALT is None:
        h = hashlib.sha1()
        for rel in DATA:
            p = os.path.join(W, rel)
            h.update(rel.encode())
            if os.path.exists(p):
                _sha_file(p, h)
        _DATA_SALT = h.hexdigest()
    return _DATA_SALT


def key(cmd, out):
    h = hashlib.sha1()
    h.update(data_salt().encode())
    for rel in VOLATILE:
        p = os.path.join(W, rel)
        h.update(("volatile:" + rel).encode())
        if os.path.exists(p):
            _sha_file(p, h)
        else:
            h.update(b"<absent>")
    for f in closure(cmd[0]):
        h.update(os.path.relpath(f, ROOT).encode())
        _sha_file(f, h)
    for a in cmd[1:]:
        if out and os.path.abspath(a) == os.path.abspath(out):
            h.update(b"<out>")
            if os.path.exists(a):
                _sha_file(a, h)
        elif os.path.isfile(a):
            h.update(b"<file>")
            _sha_file(a, h)
        else:
            h.update(("arg:" + a).encode())
    return h.hexdigest()


def get(k, out):
    """Replay entry `k`: restore `out` and the volatile files, return its stdout -- or None on a miss."""
    d = os.path.join(CACHE, k)
    meta = os.path.join(d, "meta.json")
    if not os.path.exists(meta):
        return None
    m = json.load(open(meta))
    if out:
        shutil.copyfile(os.path.join(d, "out"), out)
    for rel, present in m["volatile"].items():
        p = os.path.join(W, rel)
        if present:
            shutil.copyfile(os.path.join(d, "v_" + rel.replace("/", "_")), p)
        elif os.path.exists(p):
            os.remove(p)
    os.utime(meta)                                   # recently used: kept by the trim
    return m["stdout"]


def put(k, out, stdout):
    d = os.path.join(CACHE, k)
    tmp = d + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    if out:
        shutil.copyfile(out, os.path.join(tmp, "out"))
    vol = {}
    for rel in VOLATILE:
        p = os.path.join(W, rel)
        vol[rel] = os.path.exists(p)
        if vol[rel]:
            shutil.copyfile(p, os.path.join(tmp, "v_" + rel.replace("/", "_")))
    json.dump({"stdout": stdout, "volatile": vol}, open(os.path.join(tmp, "meta.json"), "w"))
    shutil.rmtree(d, ignore_errors=True)
    os.replace(tmp, d)
    trim()


def trim():
    try:
        ents = [os.path.join(CACHE, e) for e in os.listdir(CACHE) if not e.endswith(".tmp")]
    except FileNotFoundError:
        return
    if len(ents) <= KEEP:
        return
    ents.sort(key=lambda e: os.path.getmtime(os.path.join(e, "meta.json")) if os.path.exists(os.path.join(e, "meta.json")) else 0)
    for e in ents[:len(ents) - KEEP]:
        shutil.rmtree(e, ignore_errors=True)


if __name__ == "__main__":
    import sys
    for s in sys.argv[1:]:
        print(s, "->", [os.path.relpath(f, ROOT) for f in closure(s)])
