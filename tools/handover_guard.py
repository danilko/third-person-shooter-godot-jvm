#!/usr/bin/env python3
"""handover_guard.py -- the ONE rule for "may a generator overwrite the island" (PLAN.md item 3, 2026-10-08).

After the handover the island is hand-authored (assets/world_source/HAND_AUTHORING.md): a designer moves a road in
the Road Kit dock or a building in its record, and a generator re-run would silently throw that work away. So once
`assets/world_source/HANDOVER` exists, every tool that REGENERATES a record asks `refuse(what, argv)` first, and
refuses unless the caller says `--regenerate` (or OW_REGENERATE=1 in the environment, which is how island_world.sh
passes its own --regenerate down to the tools it runs).

Who asks: island_layout.py (the road record), island_buildings.py derive / anchors / lots / retone (the building
record), island_world.sh (the whole order). What does NOT ask: anything that only RENDERS a record into scenes or
checks it (island_buildings.py write, the road build, every probe and --check) -- those are exactly what a hand edit
needs re-run.

    python3 tools/handover_guard.py            print whether the island is frozen
    python3 tools/handover_freeze.py           freeze it (writes HANDOVER, unticks the records' `generated`)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKER = os.path.join(ROOT, "assets", "world_source", "HANDOVER")


def frozen():
    return os.path.exists(MARKER)


def allowed(argv=None):
    argv = sys.argv if argv is None else argv
    return "--regenerate" in argv or os.environ.get("OW_REGENERATE") == "1"


def refuse(what, argv=None):
    """Exit 3 with a message when the island is frozen and the caller did not ask to regenerate."""
    if frozen() and not allowed(argv):
        with open(MARKER) as f:
            note = f.read().strip()
        sys.stderr.write(
            "REFUSED: %s would regenerate the hand-authored island (%s exists: %s).\n"
            "  Edit by hand (assets/world_source/HAND_AUTHORING.md), or pass --regenerate to throw the hand work away.\n"
            % (what, os.path.relpath(MARKER, ROOT), note or "frozen"))
        sys.exit(3)


if __name__ == "__main__":
    print("island frozen (%s)" % os.path.relpath(MARKER, ROOT) if frozen() else "island not frozen: generators may run")
