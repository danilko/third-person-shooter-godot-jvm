#!/usr/bin/env python3
"""compare_roads_records.py A B [--tol 1e-3] -- are two `.roads.json` records the same network?

Semantic, through `point_model` (so key order, defaults written or omitted, and float formatting do
not matter), with a position/tangent tolerance for the Godot side's single-precision Vector3.
Exit 0 when equal; prints every difference otherwise."""
import json
import math
import os
import sys

BP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BP, "lib"))
sys.path.insert(0, os.path.join(BP, "addons", "road_kit_authoring"))
import point_model as pm  # noqa: E402


def diff(a, b, tol, path=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append("%s/%s only in %s" % (path, k, "A" if k in a else "B"))
            else:
                out += diff(a[k], b[k], tol, path + "/" + str(k))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append("%s length %d vs %d" % (path, len(a), len(b)))
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                out += diff(x, y, tol, "%s[%d]" % (path, i))
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if not math.isclose(float(a), float(b), abs_tol=tol):
            out.append("%s %r vs %r" % (path, a, b))
    elif a != b:
        out.append("%s %r vs %r" % (path, a, b))
    return out


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    tol = float(sys.argv[sys.argv.index("--tol") + 1]) if "--tol" in sys.argv else 1e-3
    if "--tol" in sys.argv:
        args = [x for x in args if x != sys.argv[sys.argv.index("--tol") + 1]]
    a = pm.network_to_dict(pm.load_network(args[0]))
    b = pm.network_to_dict(pm.load_network(args[1]))
    d = diff(a, b, tol)
    for line in d[:40]:
        print("  DIFF", line)
    print("records %s (%d roads, %d points; %d difference(s), tol %g)"
          % ("EQUAL" if not d else "DIFFER", len(a["roads"]), len(a["points"]), len(d), tol))
    return 0 if not d else 1


if __name__ == "__main__":
    sys.exit(main())
