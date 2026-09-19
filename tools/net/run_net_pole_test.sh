#!/usr/bin/env bash
# PLAN.md 3.11b two-instance gate: street poles are knocked down LOCALLY on every peer, with no world event.
# The host drives its car through one pole, the client drives its own car through another; each car is a
# puppet on the other peer. Both poles must be down on BOTH peers, the side poles up, and 0 world events.
# Exit 0 = pass.
set -u
cd "$(dirname "$0")/../.."
G="${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}"
OUT="${OUT:-$(mktemp -d)}"
SCENE=res://src/main/resources/com/openworld/debug/NetPoleTest.tscn

timeout -k 5 100 stdbuf -oL "$G" --headless --path . "$SCENE" -- --role=host > "$OUT/host.log" 2>&1 &
host=$!
sleep 4
timeout -k 5 95 stdbuf -oL "$G" --headless --path . "$SCENE" -- --role=client > "$OUT/client.log" 2>&1 &
client=$!
wait $client $host

grep -h "\[netpole\]" "$OUT"/*.log
python3 - "$OUT" <<'PY'
import re, sys
out = sys.argv[1]
def summary(n):
    m = re.search(r"\[netpole\] SUMMARY (.*)", open(f"{out}/{n}.log", errors="replace").read())
    return dict(kv.split("=", 1) for kv in m.group(1).split() if "=" in kv) if m else {}
h, c = summary("host"), summary("client")
fails = 0
def check(label, ok, detail):
    global fails
    fails += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<58} {detail}")
check("both peers finished", bool(h) and bool(c), f"host {'ok' if h else 'no summary'}, client {'ok' if c else 'no summary'}")
check("host car (simulated on host) knocked its pole down on the host", h.get("pole0") == "down", f"host pole0={h.get('pole0')}")
check("... and on the client, from its puppet", c.get("pole0") == "down", f"client pole0={c.get('pole0')}")
check("client car (simulated on client) knocked its pole down on the client", c.get("pole1") == "down", f"client pole1={c.get('pole1')}")
check("... and on the host, from its puppet", h.get("pole1") == "down", f"host pole1={h.get('pole1')}")
check("the side poles stand on both peers", all(d.get(k) == "up" for d in (h, c) for k in ("pole2", "pole3")),
      f"host {h.get('pole2')}/{h.get('pole3')}, client {c.get('pole2')}/{c.get('pole3')}")
check("no world event while the cars knock poles down", h.get("world_events_during_drives") == "0" and c.get("world_events_during_drives") == "0",
      f"host sent {h.get('world_events_during_drives')}, client received {c.get('world_events_during_drives')} "
      f"(totals incl. join baseline: sent {h.get('world_event_sent')}, received {c.get('world_event_received')})")
print("3.11b local pole knock-downs:", "PASS" if fails == 0 else f"FAIL ({fails})", "— logs in", out)
sys.exit(1 if fails else 0)
PY
