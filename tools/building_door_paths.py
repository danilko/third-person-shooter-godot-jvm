"""The way round a building to each of its doors, BAKED (PLAN.md 1g f, 2026-10-07).

game.EnforcementDispatch sends breaching units to a building's cheapest door. Its live route goes round the
building's OWN corners, which runs into a neighbour that touches the building (measured: probe_breach's officers gave
up a konbini's back door 26 times out of 28). The walk is a fact about the layout, so it is baked here, once, from the
same footprints `tools/island_door_access.py` measures: from 1.2 m outside the FRONT door to 1.2 m outside every other
door, on a 0.5 m grid, round every neighbour's plinth grown by a body's radius, inside a 70 m window. A door no walk
reaches is recorded as null (the dispatch never sends anyone there).

    door_paths(i, B, polys, tree, idx, layout) -> {"Door_<side>_<module>": [[x, z], ...] | None}   (Godot frame)

Used by island_buildings.write_places (the places record's `door_paths`) and by island_door_access.py's report.
"""
import math
from collections import deque

import numpy as np
import shapely
from shapely.geometry import box as sbox

WALK = ("Parking", "PocketPark", "Park")
RES, WIN, R, OUT = 0.5, 70.0, 0.4, 1.2


def _door_name(d):
    return "Door_%s_%d" % (d["side"], int(d.get("module", 0)))


def _grid(b, i, B, polys, tree, idx, paved):
    x0, z0 = b["pos"][0] - WIN / 2, b["pos"][2] - WIN / 2
    n = int(WIN / RES)
    occ = np.zeros((n, n), bool)
    gx = x0 + (np.arange(n) + 0.5) * RES
    X, Z = np.meshgrid(gx, z0 + (np.arange(n) + 0.5) * RES, indexing="ij")
    for k in tree.query(sbox(x0, z0, x0 + WIN, z0 + WIN)):
        j = idx[int(k)]
        if B[j]["type"].startswith(WALK):
            continue
        if j == i:
            if paved(B[j]["type"]):
                continue                     # a compound's own yard is walkable; its doors open into it
            P = polys[j]
        else:
            P = polys[j].buffer(R)
        minx, minz, maxx, maxz = P.bounds
        a0, a1 = max(0, int((minx - x0) / RES)), min(n, int((maxx - x0) / RES) + 1)
        c0, c1 = max(0, int((minz - z0) / RES)), min(n, int((maxz - z0) / RES) + 1)
        if a0 >= a1 or c0 >= c1:
            continue
        occ[a0:a1, c0:c1] |= shapely.contains_xy(P, X[a0:a1, c0:c1], Z[a0:a1, c0:c1])
    return occ, x0, z0, n


def _clear(occ, a, b):
    """Every cell on the segment between grid cells a and b is free (a sampled walk, half a cell apart)."""
    (ax, ay), (bx, by) = a, b
    steps = int(max(abs(bx - ax), abs(by - ay)) * 2) + 1
    for t in range(steps + 1):
        u = ax + (bx - ax) * t / steps
        v = ay + (by - ay) * t / steps
        if occ[int(round(u)), int(round(v))]:
            return False
    return True


def walk_grid(i, B, polys, tree, idx, paved):
    """The building's 70 m walk window as data the game can search from wherever a unit stands:
    {x0, z0, n, res, bits} with bits = base64 of the occupancy, one bit per cell, cell (gx, gz) at bit gx * n + gz,
    most significant bit first (numpy.packbits)."""
    import base64
    occ, x0, z0, n = _grid(B[i], i, B, polys, tree, idx, paved)
    return {"x0": round(x0, 2), "z0": round(z0, 2), "n": n, "res": RES,
            "bits": base64.b64encode(np.packbits(occ.flatten(order="C")).tobytes()).decode("ascii")}


def door_paths(i, B, polys, tree, idx, layout, paved):
    b = B[i]
    L = layout.get(b["type"])
    if not L or len(L["doors"]) < 2:
        return {}
    a = math.radians(b["yaw"])
    c, s = math.cos(a), math.sin(a)

    def w(x, z):
        return (b["pos"][0] + x * c + z * s, b["pos"][2] - x * s + z * c)

    occ, x0, z0, n = _grid(b, i, B, polys, tree, idx, paved)

    def cell(p):
        return int((p[0] - x0) / RES), int((p[1] - z0) / RES)

    doors = []
    for d in L["doors"]:
        cx, _, cz = d["center"]
        ox, _, oz = d.get("outward", [0, 0, 1])
        doors.append((d, w(cx + ox * OUT, cz + oz * OUT)))
    fronts = [p for d, p in doors if d["side"] == "front"] or [doors[0][1]]
    start = cell(fronts[0])
    if not (0 <= start[0] < n and 0 <= start[1] < n):
        return {}
    occ[start] = False
    parent = {start: None}
    dq = deque([start])
    while dq:
        x, y = dq.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            u, v = x + dx, y + dy
            if 0 <= u < n and 0 <= v < n and (u, v) not in parent and not occ[u, v]:
                parent[(u, v)] = (x, y)
                dq.append((u, v))
    out = {}
    for d, p in doors:
        if d["side"] == "front":
            continue
        g = cell(p)
        if g not in parent:
            # the door's outside cell itself may sit in a neighbour's grown plinth: the nearest reached cell within 1 m
            near = [(gx_, gy_) for gx_ in range(g[0] - 2, g[0] + 3) for gy_ in range(g[1] - 2, g[1] + 3)
                    if (gx_, gy_) in parent]
            if not near:
                out[_door_name(d)] = None
                continue
            g = min(near, key=lambda q: (q[0] - g[0]) ** 2 + (q[1] - g[1]) ** 2)
        chain = []
        q = g
        while q is not None:
            chain.append(q)
            q = parent[q]
        chain.reverse()
        # string-pull: keep only the cells the straight walk needs
        keep = [chain[0]]
        k = 0
        while k < len(chain) - 1:
            far = len(chain) - 1
            while far > k + 1 and not _clear(occ, chain[k], chain[far]):
                far -= 1
            keep.append(chain[far])
            k = far
        pts = [[round(x0 + (cx_ + 0.5) * RES, 2), round(z0 + (cy_ + 0.5) * RES, 2)] for cx_, cy_ in keep]
        pts[0] = [round(fronts[0][0], 2), round(fronts[0][1], 2)]
        pts.append([round(p[0], 2), round(p[1], 2)])
        out[_door_name(d)] = pts
    return out
