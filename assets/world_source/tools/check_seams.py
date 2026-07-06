#!/usr/bin/env python3
"""
check_seams.py — automated cross-district seam alignment checker (PURE PYTHON, no bpy,
no Blender/Godot needed). Verifies two adjacent district pieces will actually meet
correctly, instead of loading both in an editor and eyeballing it.

Reads the `.seam.json` sidecar each piece's build_district.py writes next to its .blend
(see build_district.py's emit_seam_routes()/main()) — cheap to produce, cheap to read
back, no engine dependency.

Checks, for the shared edge between two districts:
  1. World-space crossing point matches (both sides computed the same (x,y) — they should,
     since both derive it from the same lib/world_grid.py constants, but this catches a
     stale manifest, a wrong gx/gy, or a cells/block choice that breaks the mid==n//2
     assumption build_district.py asserts at build time).
  2. Each side's recorded elevation/neighbour_elevation is mutually consistent.
  3. Each side's `expects_next` route name matches the other side's actual `entry_route`
     name — the thing that makes VehicleRoute.nextRoutes chaining resolve at runtime
     (see world_grid.py's seam_route_name docstring).

RUN: python3 tools/check_seams.py districts/District_Shibuya.seam.json districts/District_city_2_1.seam.json
     (or any two adjacent pieces' .seam.json files, in either order)
Exit code 0 = all checks passed, 1 = a mismatch was found (details printed).
"""
import json
import sys

TOL = 0.01   # metres — float-compare tolerance for world coordinates


def load(path):
    with open(path) as f:
        return json.load(f)


def opposite(edge):
    return {"N": "S", "S": "N", "E": "W", "W": "E"}[edge]


def find_shared_edge(a, b):
    """-> (edgeA, edgeB) — the edge of `a` facing `b`, and the edge of `b` facing `a`."""
    for edge, info in a["edges"].items():
        if info["neighbour"] == [b["gx"], b["gy"]]:
            edgeB = opposite(edge)
            if edgeB not in b["edges"] or b["edges"][edgeB]["neighbour"] != [a["gx"], a["gy"]]:
                return edge, None   # `a` expects `b` here, but `b` doesn't reciprocate
            return edge, edgeB
    return None, None


def check(a, b):
    failures = []
    edgeA, edgeB = find_shared_edge(a, b)
    if edgeA is None:
        return [f"{a['piece']} ({a['gx']},{a['gy']}) and {b['piece']} ({b['gx']},{b['gy']}) "
                f"are not adjacent (no edge of either names the other as its neighbour)"]
    if edgeB is None:
        return [f"{a['piece']}'s '{edgeA}' edge expects neighbour {b['piece']}, but "
                f"{b['piece']} does not reciprocate on its '{opposite(edgeA)}' edge"]

    ea, eb = a["edges"][edgeA], b["edges"][edgeB]

    if abs(ea["world_x"] - eb["world_x"]) > TOL or abs(ea["world_y"] - eb["world_y"]) > TOL:
        failures.append(
            f"world position mismatch: {a['piece']}.{edgeA}=({ea['world_x']:.3f},{ea['world_y']:.3f}) "
            f"vs {b['piece']}.{edgeB}=({eb['world_x']:.3f},{eb['world_y']:.3f})")

    if abs(ea.get("neighbour_elev", 0) - b["elev"]) > TOL:
        failures.append(f"{a['piece']}.{edgeA}.neighbour_elev claims {ea.get('neighbour_elev')} "
                         f"but {b['piece']}'s own elev is {b['elev']}")
    if abs(eb.get("neighbour_elev", 0) - a["elev"]) > TOL:
        failures.append(f"{b['piece']}.{edgeB}.neighbour_elev claims {eb.get('neighbour_elev')} "
                         f"but {a['piece']}'s own elev is {a['elev']}")

    if ea.get("expects_next") != eb.get("entry_route"):
        failures.append(f"{a['piece']}.{edgeA}.expects_next='{ea.get('expects_next')}' != "
                         f"{b['piece']}.{edgeB}.entry_route='{eb.get('entry_route')}' "
                         f"— VehicleRoute.nextRoutes chaining will NOT resolve")
    if eb.get("expects_next") != ea.get("entry_route"):
        failures.append(f"{b['piece']}.{edgeB}.expects_next='{eb.get('expects_next')}' != "
                         f"{a['piece']}.{edgeA}.entry_route='{ea.get('entry_route')}' "
                         f"— VehicleRoute.nextRoutes chaining will NOT resolve")

    return failures


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    a, b = load(sys.argv[1]), load(sys.argv[2])
    failures = check(a, b)
    if failures:
        print(f"FAIL — {a['piece']} <-> {b['piece']}:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print(f"PASS — {a['piece']} <-> {b['piece']} seam is consistent "
          f"(position, elevation, and route naming all agree)")
    sys.exit(0)


if __name__ == "__main__":
    main()
