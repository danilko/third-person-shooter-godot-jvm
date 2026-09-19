#!/usr/bin/env bash
# PLAN.md N5 two-instance gate: host lag compensation for hitscan. A client taps a single-pellet rifle
# at a target strafing at constant speed, with LAG_MS held on every message both ways. Run once with
# the host rewinding and once without (the control). Exit 0 = pass.
set -u
cd "$(dirname "$0")/../.."
G="${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}"
OUT="${OUT:-$(mktemp -d)}"
LAG_MS="${LAG_MS:-80}"
SCENE=res://src/main/resources/com/openworld/debug/NetLagTest.tscn

run_pair() {  # $1 = label, $2 = extra host arg
    timeout -k 5 110 stdbuf -oL "$G" --headless --path . "$SCENE" -- --role=host --lag-ms=$LAG_MS $2 > "$OUT/$1-host.log" 2>&1 &
    local host=$!
    sleep 4
    timeout -k 5 100 stdbuf -oL "$G" --headless --path . "$SCENE" -- --role=client --lag-ms=$LAG_MS > "$OUT/$1-client.log" 2>&1 &
    local client=$!
    wait $client $host
}
run_pair rewind ""
run_pair norewind "--no-rewind"

grep -h "\[netlag\] SUMMARY" "$OUT"/*.log
python3 - "$OUT" "$LAG_MS" <<'PY'
import re, sys
out, lag = sys.argv[1], int(sys.argv[2])
def read(n): return open(f"{out}/{n}.log", errors="replace").read()
def summary(t):
    m = re.search(r"\[netlag\] SUMMARY (.*)", t)
    return dict(kv.split("=", 1) for kv in m.group(1).split() if "=" in kv) if m else {}
def hits(t):
    shots = re.findall(r"\[shot\] host resolved #(\d+) dirs \S+ hits \d+ -> \[(.*)\]", t)
    return len(shots), sum(1 for _, h in shots if h.startswith("Physical Bone"))
def rewinds(t): return [int(ms) for ms in re.findall(r"\[shot\] host rewind #\d+ (\d+) ms", t)]
fails = 0
def check(label, ok, detail):
    global fails
    fails += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<52} {detail}")
rh, nh = read("rewind-host"), read("norewind-host")
rs, ns = hits(rh), hits(nh)
speed = float(summary(rh).get("target_speed", 0))
check("target strafes at a steady walk", speed > 1.8, f"{speed:.2f} m/s mid-sweep")
check("client fired and the host resolved its pulls", rs[0] >= 20 and ns[0] >= 20, f"rewind {rs[0]}, control {ns[0]} resolved")
rw = rewinds(rh)
med = sorted(rw)[len(rw) // 2] if rw else -1
check("host rewound by about the round trip", rw and 2 * lag <= med <= 2 * lag + 120, f"median {med} ms (lag {lag} ms each way)")
check("CONTROL: no rewind without lag compensation", rewinds(nh) and max(rewinds(nh)) == 0, f"max {max(rewinds(nh) or [-1])} ms")
rr, nr = rs[1] / max(1, rs[0]), ns[1] / max(1, ns[0])
check("with rewind: the shots the client saw land", rr >= 0.85, f"{rs[1]}/{rs[0]} = {rr:.0%}")
check("CONTROL: without rewind they mostly miss", nr <= 0.35, f"{ns[1]}/{ns[0]} = {nr:.0%}")
check("nothing rate-limited", summary(rh).get("drop_rate_limited") == "0", f"drop_rate_limited={summary(rh).get('drop_rate_limited')}")
print("N5 lag compensation:", "PASS" if fails == 0 else f"FAIL ({fails})", "— logs in", out)
sys.exit(1 if fails else 0)
PY
