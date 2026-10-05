"""Give every road of a record its class's 路肩 (shoulder) and 側帯 (median strip): the Japanese edge line with a
shoulder between it and the kerb (PLAN.md "edge lines", user 2026-10-05).

    python3 tools/island_shoulders.py <out> [--from <record>]      # in place when --from is omitted

(The output first, like every layout step: `island_layout.run`'s cache takes a step's first .json as its output.)

The presets carry shoulders (`point_presets.PRESETS`), so a road a generator makes from a preset has them already;
this is for the roads whose section was written before shoulders existed -- the island's arterials INPUT, written
once by island_network.py, and any road a generator copies a section into by hand. The rule is
`point_presets.add_shoulders`: by road class, never on an expressway, a ramp or the rail, and a road that already
has a shoulder keeps it. Idempotent.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import island_roadgen  # noqa: E402,F401  (puts the Road Kit on sys.path)
import point_model as pm  # noqa: E402
import point_presets as pr  # noqa: E402


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    out = argv[0]
    src = argv[argv.index("--from") + 1] if "--from" in argv else out
    net = pm.load_network(src)
    changed = [n for n in sorted(net.roads) if pr.add_shoulders(net, n)]
    pm.save_network(net, out)
    print("island_shoulders: %d road(s) given shoulders%s" % (len(changed), "" if not changed else
                                                              " (%s%s)" % (", ".join(changed[:6]),
                                                                           ", ..." if len(changed) > 6 else "")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
