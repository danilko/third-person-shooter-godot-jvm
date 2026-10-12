#!/bin/bash
# PLAN.md R-9: the Steam Deck proxy perf gate. Runs tools/godot/probe_walk_perf.gd --deck (NEEDS A DISPLAY) once as
# shipped, once per control (--no-peds, --no-traffic, --no-buildings) and once at PEAK enforcement load
# (--wanted=5 --gang=4, reported, not judged), then attributes each system's cost per leg
# as (shipped deck_ms p50 - control deck_ms p50) and judges it against tools/godot/perf_budget.json's
# `systems_deck_ms_p50`, and the shipped run against its frame / count budgets.
#   tools/perf_gate.sh [--legs=a,b] [--quick]     (--quick: the shipped run only, no attribution)
set -u
cd "$(dirname "$0")/.."
G=${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}
OUT=${PERF_OUT:-$(mktemp -d)}
EXTRA=(); QUICK=""
for a in "$@"; do [ "$a" = "--quick" ] && QUICK=1 || EXTRA+=("$a"); done
run() {   # name, flags...
    local n=$1; shift
    echo "── $n"
    timeout -k 5 3600 stdbuf -oL "$G" --path . --script tools/godot/probe_walk_perf.gd -- --deck "${EXTRA[@]}" "$@" \
        > "$OUT/$n.log" 2>&1
    grep -E "^DECK|^AUDIO|RESULT|OVER BUDGET|under the terrain" "$OUT/$n.log"
}
run shipped
RC=$?
grep -q "RESULT PASS" "$OUT/shipped.log"; SHIP=$?
if [ -z "$QUICK" ]; then
    run no-peds --no-peds
    run no-traffic --no-traffic
    run no-buildings --no-buildings
    run peak --wanted=5 --gang=4
fi
python3 - "$OUT" <<'PY'
import json, re, sys, os
out = sys.argv[1]
cfg = json.load(open("tools/godot/perf_budget.json"))
def legs(n):
    p = os.path.join(out, n + ".log")
    r = {}
    if os.path.exists(p):
        for l in open(p):
            m = re.match(r"DECK (\S+) p50 ([\d.]+) p95 ([\d.]+)", l)
            if m:
                r[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    return r
base = legs("shipped")
fail = 0
for sysname, ctl in (("peds", "no-peds"), ("traffic", "no-traffic"), ("buildings", "no-buildings")):
    c = legs(ctl)
    if not c:
        continue
    budget = cfg["systems_deck_ms_p50"][sysname]
    worst = max(((base[k][0] - c[k][0], k) for k in base if k in c), default=(0.0, "-"))
    ok = worst[0] <= budget
    fail += not ok
    print("SYSTEM %-10s worst leg %-18s %+6.2f deck ms p50 (budget %.1f) %s" % (sysname, worst[1], worst[0], budget,
                                                                              "ok" if ok else "OVER"))
pk = legs("peak")
for k in sorted(pk):
    if k in base:
        print("PEAK   %-18s p50 %6.1f -> %6.1f (%+.1f)  p95 %6.1f -> %6.1f (%+.1f) deck ms  (wanted 6, gang 4)" % (
            k, base[k][0], pk[k][0], pk[k][0] - base[k][0], base[k][1], pk[k][1], pk[k][1] - base[k][1]))
print("logs in", out)
sys.exit(1 if fail else 0)
PY
ATTR=$?
[ $SHIP -eq 0 ] && [ $ATTR -eq 0 ] && { echo "PERF GATE PASS"; exit 0; } || { echo "PERF GATE FAIL"; exit 1; }
