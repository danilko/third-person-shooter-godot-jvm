#!/usr/bin/env python3
"""Derive a world's ambient-traffic ZoneMarkers from its Road Kit lanes (PLAN.md 3.4).

A traffic zone is not authored by dragging markers around: where a car may be SET DOWN is a fact
about the lane graph, not about taste.  ``ZoneManager.spawnTrafficCar`` only ever places a car in
the first few queue slots of a lane (``placementOn``), so every spawn point in the world is a lane
ENTRY -- and on a Road Kit network the entries cluster at junctions and road ends, because that is
where lanes begin.  So the markers ARE those clusters, and this tool derives them:

  1. read the piece's ``.lanekit.json`` and take every ``spawnable`` lane's first point;
  2. single-linkage cluster them at ``--cluster`` metres (order-independent; a junction's 2-25
     lane entries collapse to one centroid);
  3. write one geometry-less ``Zone`` + ``ZoneMarker`` per cluster into the scene, each carrying a
     ``VehicleSpawnConfig`` whose ``route_name`` is the lanes' own ``zone_id`` -- which is
     ``ZoneManager.spawnLanes``' zone-id pass, so a marker offers exactly the lanes of that network
     whose entry is within its ``unload_radius``.

The radii are not free either.  ``spawnTrafficCar``'s player gate is ``unload_radius * 0.9`` from a
lane ENTRY, so a player driving mid-arterial sees traffic only if ``0.9 * unload_radius`` covers the
worst distance from a lane sample to the nearest cluster; the tool MEASURES that distance and
refuses radii that do not (``--unload``), rather than letting a quiet stretch of road pass as a
tuning preference.  ``--load`` must leave hysteresis below it and cover the network too.

The block it writes is identified by NAME (``Zone_traffic_*``, ``VehicleSpawn_traffic``, the
``TrafficZones`` node), never by a comment, so re-running it after an editor re-save replaces the
previous block instead of duplicating it.

    tools/island_traffic_zones.py assets/world_source/pieces/Roads_IslandRoads_island_*.lanekit.json \
        src/main/resources/com/openworld/world/World.tscn
    tools/island_traffic_zones.py ... --check     # exit 1 if the scene is stale (CI)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

ZONE_SCRIPT = "res://src/main/java/com/openworld/world/Zone.java"
MARKER_SCRIPT = "res://src/main/java/com/openworld/world/ZoneMarker.java"
VSPAWN_SCRIPT = "res://src/main/java/com/openworld/world/VehicleSpawnConfig.java"

# Godot writes a uid= on every ext_resource; a path alone still loads, and the editor fills the uid
# back in on its next save.
SCRIPT_UIDS = {
    ZONE_SCRIPT: "uid://oxf3ybti5sgy",
    MARKER_SCRIPT: "uid://dd6fa8v7fiv47",
    VSPAWN_SCRIPT: "uid://4hm6pt3jr6fb",
}

NODE_ID_BASE = 910012000       # a free block; IslandZone/IslandRoads sit at 9100110xx
ZONE_PREFIX = "Zone_traffic_"
VSPAWN_ID = "VehicleSpawn_traffic"
HOLDER = "TrafficZones"


# ---------------------------------------------------------------------------- lanes -> clusters

def spawn_entries(lanekits: list[dict]) -> tuple[list[list[float]], list[list[list[float]]], str]:
    """(entry point per spawnable lane, every spawnable lane's polyline, the ROUTE they share).

    One piece: the route is its lanes' zone_id. A network cut into a grid of zones (PLAN.md 3.10,
    `island_road_zones.py`) streams as many pieces, one zone id each (`island_<gx>_<gz>`); the route
    is then their common prefix up to its last `_` (`island_`), which `ZoneManager.spawnLanes`'
    zone-id pass reads as "any zone whose id starts with this" -- one route over the whole network,
    however it streams."""
    every = [l for doc in lanekits for l in doc.get("lanes", [])]
    kind = {l["id"]: l.get("kind", "") for l in every}
    preds: dict[str, list[str]] = {}
    for l in every:
        for n in l.get("next", ()):
            preds.setdefault(n, []).append(l["id"])
    # A lane whose only predecessors are plain lanes starts at a JOINT, mid-road (a road split at a
    # zone cell boundary, `island_road_zones.py`): it is not where traffic clusters, and counting it
    # would scatter markers along every arterial. The clusters stay junctions and road ends.
    lanes = [l for l in every if l.get("spawnable")
             and not (preds.get(l["id"]) and all(kind.get(p) != "connector" for p in preds[l["id"]]))]
    if not lanes:
        raise SystemExit("no spawnable lanes in the lanekit(s) — nothing to build traffic zones from")
    zone_ids = sorted({l.get("zone_id", "") for l in lanes})
    if "" in zone_ids:
        raise SystemExit("a spawnable lane has no zone_id")
    if len(zone_ids) == 1:
        route = zone_ids[0]
    else:
        common = os.path.commonprefix(zone_ids)
        route = common[:common.rfind("_") + 1] if "_" in common else ""
        if not route:
            raise SystemExit(f"the lanes' zone ids share no '<prefix>_': {zone_ids[:5]}...")
    # Coverage is measured over EVERY spawnable lane: a joint lane is still road a player drives.
    return ([l["points"][0] for l in lanes],
            [l["points"] for l in every if l.get("spawnable")], route)


def cluster(points: list[list[float]], radius: float) -> list[tuple[float, float, float, int]]:
    """Single-linkage clusters (XZ) at `radius`, as (x, y, z, member count), biggest first.

    Single linkage rather than a greedy "cover the most" pass: the greedy one is order-dependent,
    so a lane reordering in the record would move markers that nothing about the road changed.
    """
    parent = list(range(len(points)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            if math.dist((points[i][0], points[i][2]), (points[j][0], points[j][2])) <= radius:
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(len(points)):
        groups.setdefault(find(i), []).append(i)
    out = []
    for members in groups.values():
        n = len(members)
        out.append((sum(points[j][0] for j in members) / n,
                    sum(points[j][1] for j in members) / n,
                    sum(points[j][2] for j in members) / n, n))
    # Biggest first, then by position, so the order is a fact about the road and not about dict order.
    out.sort(key=lambda c: (-c[3], round(c[0], 3), round(c[2], 3)))
    return out


def worst_coverage(polylines: list[list[list[float]]], centres, step: float = 50.0) -> tuple[float, int]:
    """Farthest any point ON a lane is from the nearest cluster centre (XZ), and how many samples."""
    worst, n = 0.0, 0
    for pts in polylines:
        acc, samples = 0.0, [pts[0]]
        for a, b in zip(pts, pts[1:]):
            acc += math.dist(a, b)
            if acc >= step:
                samples.append(b)
                acc = 0.0
        for s in samples:
            n += 1
            worst = max(worst, min(math.dist((s[0], s[2]), (c[0], c[2])) for c in centres))
    return worst, n


# ---------------------------------------------------------------------------- .tscn patching

SECTION = re.compile(r"^\[(\w+)\s*(.*)\]\s*$")


def split_sections(text: str) -> list[tuple[str, str]]:
    """[(header line or '' for the preamble, body including the header)] in file order."""
    out, header, buf = [], "", []
    for line in text.splitlines(keepends=True):
        if SECTION.match(line):
            out.append((header, "".join(buf)))
            header, buf = line, [line]
        else:
            buf.append(line)
    out.append((header, "".join(buf)))
    return out


def attr(header: str, key: str) -> str | None:
    # (?<![\w]) so key="id" does not match the `uid="..."` sitting beside it.
    m = re.search(rf'(?<![\w]){key}="([^"]*)"', header)
    return m.group(1) if m else None


def ext_resource_id(sections, path: str) -> str | None:
    for header, _ in sections:
        if header.startswith("[ext_resource") and attr(header, "path") == path:
            return attr(header, "id")
    return None


def network_offset(sections, node_name: str) -> tuple[float, float, float]:
    """The network node's own translation — the lanekit's points are in ITS frame, the markers are
    written in the scene root's."""
    for header, body in sections:
        if header.startswith("[node") and attr(header, "name") == node_name:
            m = re.search(r"transform = Transform3D\(([^)]*)\)", body)
            if not m:
                return (0.0, 0.0, 0.0)
            v = [float(x) for x in m.group(1).split(",")]
            if len(v) != 12:
                raise SystemExit(f"node '{node_name}' has a malformed transform")
            if any(abs(v[i] - e) > 1e-6 for i, e in enumerate([1, 0, 0, 0, 1, 0, 0, 0, 1])):
                raise SystemExit(f"node '{node_name}' is rotated/scaled — the marker generator "
                                 "only composes a translation")
            return (v[9], v[10], v[11])
    raise SystemExit(f"no node named '{node_name}' in the scene")


def is_generated(header: str) -> bool:
    if header.startswith("[sub_resource"):
        rid = attr(header, "id") or ""
        return rid.startswith(ZONE_PREFIX) or rid == VSPAWN_ID
    if header.startswith("[node"):
        return attr(header, "name") == HOLDER or attr(header, "parent") == HOLDER
    return False


def build_block(centres, offset, args, route: str, zone_ext: str, marker_ext: str, vspawn_ext: str):
    sub, nodes = [], []
    sub.append(f'[sub_resource type="Resource" id="{VSPAWN_ID}"]\n'
               f'script = ExtResource("{vspawn_ext}")\n'
               f'count = {args.count}\n'
               f'cruise_throttle = {args.throttle}\n'
               f'route_name = "{route}"\n\n')
    nodes.append(f'[node name="{HOLDER}" type="Node" parent="." unique_id={NODE_ID_BASE}]\n\n')
    for i, (x, y, z, n) in enumerate(centres):
        zid = f"{route.rstrip('_')}_traffic_{i:02d}"
        sub.append(f'[sub_resource type="Resource" id="{ZONE_PREFIX}{i:02d}"]\n'
                   f'script = ExtResource("{zone_ext}")\n'
                   f'zone_id = "{zid}"\n'
                   f'size = Vector3({args.box}, 10, {args.box})\n'
                   f'load_radius = {args.load:.1f}\n'
                   f'unload_radius = {args.unload:.1f}\n'
                   f'vehicle_spawn_configs = Array[ExtResource("{vspawn_ext}")]'
                   f'([SubResource("{VSPAWN_ID}")])\n\n')
        wx, wy, wz = x + offset[0], y + offset[1], z + offset[2]
        nodes.append(f'[node name="Traffic{i:02d}" type="Node3D" parent="{HOLDER}" '
                     f'unique_id={NODE_ID_BASE + 1 + i}]\n'
                     f'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, '
                     f'{wx:.3f}, {wy:.3f}, {wz:.3f})\n'
                     f'script = ExtResource("{marker_ext}")\n'
                     f'zone = SubResource("{ZONE_PREFIX}{i:02d}")\n'
                     f'show_debug_volume = false\n\n')
    return sub, nodes


def next_ext_id(sections) -> int:
    used = set()
    for header, _ in sections:
        if header.startswith("[ext_resource"):
            rid = attr(header, "id") or ""
            m = re.match(r"gen_(\d+)$", rid)
            if m:
                used.add(int(m.group(1)))
    return max(used, default=0) + 1


def patch(text: str, centres, offset, args, route: str) -> str:
    sections = split_sections(text)
    added_ext = []
    ids = {}
    counter = next_ext_id(sections)
    for path in (ZONE_SCRIPT, MARKER_SCRIPT, VSPAWN_SCRIPT):
        rid = ext_resource_id(sections, path)
        if rid is None:
            rid = f"gen_{counter}"
            counter += 1
            added_ext.append(f'[ext_resource type="Script" uid="{SCRIPT_UIDS[path]}" '
                             f'path="{path}" id="{rid}"]\n\n')
        ids[path] = rid

    sub, nodes = build_block(centres, offset, args, route,
                             ids[ZONE_SCRIPT], ids[MARKER_SCRIPT], ids[VSPAWN_SCRIPT])

    return splice(sections, is_generated, sub, nodes, added_ext)


def splice(sections, generated, sub, nodes, ext=()) -> str:
    """The scene with every `generated` section replaced by `sub` / `nodes`, each put back WHERE ITS
    PREVIOUS COPY WAS (else before the first node / first connection). Two tools own blocks in one
    scene (this one and `island_road_zones.py`); inserting "before the first node" each time made
    whichever ran last move in front of the other, so neither could ever read "up to date"."""
    has_sub = any(generated(h) and h.startswith("[sub_resource") for h, _ in sections)
    has_node = any(generated(h) and h.startswith("[node") for h, _ in sections)
    out, sub_done, nodes_done, ext_done = [], False, False, False
    for header, body in sections:
        if ext and not ext_done and header and not header.startswith(("[ext_resource", "[gd_scene")):
            out.extend(ext)
            ext_done = True
        if generated(header):
            if header.startswith("[sub_resource") and not sub_done:
                out.extend(sub)
                sub_done = True
            elif header.startswith("[node") and not nodes_done:
                out.extend(nodes)
                nodes_done = True
            continue
        if not sub_done and not has_sub and header.startswith("[node"):
            out.extend(sub)
            sub_done = True
        if not nodes_done and not has_node and header.startswith("[connection"):
            out.extend(nodes)
            nodes_done = True
        out.append(body)
    if ext and not ext_done:
        out.extend(ext)
    if not sub_done:
        out.extend(sub)
    if not nodes_done:
        out.extend(nodes)
    # Sections are emitted with exactly one blank line between them.
    return re.sub(r"\n{3,}(\[)", r"\n\n\1", "".join(out))


# ---------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lanekit", type=Path, nargs="+", help="every piece lanekit of the network")
    ap.add_argument("scene", type=Path)
    ap.add_argument("--network", default="IslandRoads",
                    help="the scene node the lanekit's frame belongs to (default IslandRoads)")
    ap.add_argument("--cluster", type=float, default=250.0, help="single-linkage radius, m")
    ap.add_argument("--load", type=float, default=1000.0)
    ap.add_argument("--unload", type=float, default=1400.0)
    ap.add_argument("--count", type=int, default=3, help="cars per zone")
    ap.add_argument("--throttle", type=float, default=0.4)
    ap.add_argument("--box", type=float, default=60.0, help="Zone.size XZ (no AI here; debug only)")
    ap.add_argument("--check", action="store_true", help="exit 1 if the scene would change")
    args = ap.parse_args()

    entries, polylines, route = spawn_entries([json.loads(p.read_text()) for p in args.lanekit])
    centres = cluster(entries, args.cluster)
    worst, samples = worst_coverage(polylines, centres)

    text = args.scene.read_text()
    offset = network_offset(split_sections(text), args.network)

    gate = args.unload * 0.9      # ZoneManager.spawnTrafficCar's player gate
    print(f"{len(entries)} spawnable lane entries -> {len(centres)} clusters at {args.cluster:.0f} m")
    for i, (x, y, z, n) in enumerate(centres):
        print(f"  Traffic{i:02d}  ({x + offset[0]:8.1f}, {y + offset[1]:6.1f}, "
              f"{z + offset[2]:8.1f})  {n:2d} lane entries")
    print(f"worst lane sample -> nearest cluster: {worst:.0f} m over {samples} samples; "
          f"spawn gate = 0.9 x unload = {gate:.0f} m")
    if gate < worst:
        print(f"REFUSED: --unload {args.unload:.0f} leaves {worst - gate:.0f} m of road with no "
              f"spawn source. Raise it to at least {worst / 0.9:.0f}.", file=sys.stderr)
        return 1
    if args.load <= args.cluster or args.load >= args.unload:
        print("REFUSED: need --cluster < --load < --unload.", file=sys.stderr)
        return 1
    if args.load < worst:
        print(f"REFUSED: --load {args.load:.0f} < {worst:.0f} m — a stretch of road has no zone "
              f"LOADED to spawn from.", file=sys.stderr)
        return 1

    patched = patch(text, centres, offset, args, route)
    if args.check:
        if patched != text:
            print(f"STALE: {args.scene} does not match the lanekit — re-run without --check.",
                  file=sys.stderr)
            return 1
        print("up to date")
        return 0
    if patched == text:
        print(f"{args.scene}: unchanged")
        return 0
    args.scene.write_text(patched)
    print(f"{args.scene}: wrote {len(centres)} traffic zones "
          f"({args.count} cars each, route '{route}')")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
