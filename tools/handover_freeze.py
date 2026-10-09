#!/usr/bin/env python3
"""handover_freeze.py -- hand the generated island over to hand-authoring (PLAN.md item 3). Run ONCE, by decision.

    python3 tools/handover_freeze.py [--note "<why / who>"] [--undo]

Freezing is two facts written together, so they cannot disagree:
  1. `assets/world_source/HANDOVER` exists (tools/handover_guard.py): island_layout.py, island_buildings.py derive /
     anchors / lots / retone and island_world.sh then refuse unless given --regenerate;
  2. the island's Road Kit networks in World.tscn (IslandRoads, IslandRail) lose `generated = true`, so the Road Kit
     dock lets a designer edit and save their records (a `generated` record refuses a hand edit).
`--undo` reverses both (the records go back to `generated`, the marker is removed). Commit the result.
"""
import datetime
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import handover_guard  # noqa: E402

WORLD = os.path.join(ROOT, "src", "main", "resources", "com", "openworld", "world", "World.tscn")
NETWORKS = ("IslandRoads", "IslandRail")


def set_generated(text, on):
    out = text
    for name in NETWORKS:
        m = re.search(r'\[node name="%s"[^\]]*\]\n(?:(?!\n\[).)*' % name, out, re.S)
        if m is None:
            sys.exit("no %s node in World.tscn" % name)
        block = m.group(0)
        if on:
            nb = block if "generated = true" in block else re.sub(
                r'(record_path = "[^"]*"\n)', r'\1generated = true\n', block, count=1)
        else:
            nb = block.replace("generated = true\n", "")
        out = out[:m.start()] + nb + out[m.end():]
    return out


def main(argv):
    undo = "--undo" in argv
    note = argv[argv.index("--note") + 1] if "--note" in argv else ""
    with open(WORLD) as f:
        text = f.read()
    new = set_generated(text, on=undo)
    if new != text:
        with open(WORLD, "w") as f:
            f.write(new)
    if undo:
        if os.path.exists(handover_guard.MARKER):
            os.remove(handover_guard.MARKER)
        print("handover_freeze: island back to generated (records `generated`, %s removed)"
              % os.path.relpath(handover_guard.MARKER, ROOT))
        return 0
    with open(handover_guard.MARKER, "w") as f:
        f.write("frozen %s%s\n" % (datetime.date.today().isoformat(), (" -- " + note) if note else ""))
    print("handover_freeze: island handed over (%s written; %s editable in the Road Kit dock)"
          % (os.path.relpath(handover_guard.MARKER, ROOT), ", ".join(NETWORKS)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
