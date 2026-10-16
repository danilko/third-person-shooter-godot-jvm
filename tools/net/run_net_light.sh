#!/usr/bin/env bash
# PLAN.md 2.3 follow-up: the light combatant tier on TWO peers (MSG_LIGHT_BATCH, tag 37). DebugWorld, host + client
# (DebugHarness -- --net=host|join --light-test): both players invulnerable; at 25 s the host spawns 24 light hunters
# round its player, who converge on the players (some are promoted to full bodies inside 15 m). From 28 s to 88 s
# each peer prints its tier on every wall-clock second. Asserted:
#   * the client received batches and drew the tier (the same ids as the host's unpromoted bodies);
#   * a body the host has NOT promoted stands within 1.5 m on the client at the same second (90 % of them);
#   * a body the host HAS promoted is not drawn by the client (its full body replicates instead: the client sees
#     "light:" characters whenever the host has promoted ones);
#   * no JVM exception on either peer.
set -u
cd "$(dirname "$0")/../.."
G="${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}"
OUT="${OUT:-$(mktemp -d)}"
SECS="${SECS:-100}"
SCENE=res://src/main/resources/com/openworld/world/DebugWorld.tscn
timeout -k 5 $((SECS + 12)) stdbuf -oL "$G" --headless --path . "$SCENE" -- --net=host --light-test > "$OUT/host.log" 2>&1 &
host=$!
sleep 6
timeout -k 5 $SECS stdbuf -oL "$G" --headless --path . "$SCENE" -- --net=join --light-test > "$OUT/client.log" 2>&1 &
client=$!
wait $client $host 2>/dev/null
echo "logs in $OUT"
python3 - "$OUT/host.log" "$OUT/client.log" <<'PY'
import re, sys
def dumps(path):
    out = {}
    text = open(path, errors="replace").read()
    for m in re.finditer(r"\[light\] role=(\w+) unix_ms=(\d+) full=(\d+) sent=(\d+) applied=(\d+) dump=(.*)", text):
        bodies = {}
        for item in filter(None, m.group(6).strip().split("|")):
            f = item.split(";")
            bodies[int(f[0])] = (int(f[1]), float(f[2]), float(f[4]), f[6] == "1")
        out[int(m.group(2)) // 1000] = (int(m.group(3)), int(m.group(4)), int(m.group(5)), bodies)
    return out, text
h, ht = dumps(sys.argv[1]); c, ct = dumps(sys.argv[2])
fails = 0
def check(name, ok, detail=""):
    global fails
    print("  %s  %-62s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        fails += 1
check("client connected", "assigned local peer id 2" in ct)
check("host spawned the horde", re.search(r"\[light\] host spawned (\d+)", ht) is not None,
      (re.search(r"\[light\] host spawned (\d+)", ht) or [None, "-"])[1])
secs = sorted(set(h) & set(c))
check("both peers dumped on the same seconds", len(secs) >= 30, "%d seconds" % len(secs))
sent = max((v[1] for v in h.values()), default=0); applied = max((v[2] for v in c.values()), default=0)
check("host sent batches, client applied them", sent > 100 and applied > 0.5 * sent, "sent %d applied %d" % (sent, applied))
n = near = shown_promoted = promoted = missing = 0
worst = 0.0
full_seen = 0; full_needed = 0
for s in secs:
    hf, _, _, hb = h[s]; cf, _, _, cb = c[s]
    hp = [i for i, b in hb.items() if b[3]]
    if hp:
        full_needed += 1
        full_seen += cf > 0
    for i, (st, x, z, prom) in hb.items():
        if prom:
            promoted += 1
            shown_promoted += i in cb
            continue
        if st >= 4:      # DEAD / GONE (LightSim states past HOLD): may be swept on one peer first
            continue
        if i not in cb:
            missing += 1
            continue
        n += 1
        d = ((x - cb[i][1]) ** 2 + (z - cb[i][2]) ** 2) ** 0.5
        worst = max(worst, d)
        near += d < 1.5
check("the client draws the host's light bodies", n > 200 and missing <= 0.05 * (n + missing), "%d compared, %d missing" % (n, missing))
check("a light body stands within 1.5 m on the client", n > 0 and near >= 0.9 * n, "%d / %d (worst %.2f m)" % (near, n, worst))
check("a promoted body is not drawn light on the client", promoted > 0 and shown_promoted <= 0.05 * promoted,
      "%d of %d promoted samples still light" % (shown_promoted, promoted))
check("the client sees the promoted ones as full bodies", full_needed > 0 and full_seen >= 0.8 * full_needed,
      "%d / %d seconds" % (full_seen, full_needed))
# the horn (snapshot flag bit 7): the host holds it 12-18 s of ITS clock; the client joined 6 s later, so its 8-24 s
# window sees the hold from about t 8 to t 12
hh = [l for l in re.findall(r"\[horn\] role=host t=(\d+) heard=(\w+)", ht)]
ch = [l for l in re.findall(r"\[horn\] role=client t=(\d+) heard=(\w+)", ct)]
check("the host hears its own horn while it holds it", any(h2 == "true" for t, h2 in hh if 13 <= int(t) <= 17), str(hh))
check("the client hears the host's horn (snapshot bit 7)", any(h2 == "true" for t, h2 in ch), str([t for t, h2 in ch if h2 == "true"]))
check("...and it stops when released", ch and ch[-1][1] == "false", "")
for name, text in (("host", ht), ("client", ct)):
    k = sum(1 for line in text.splitlines() if "Exception" in line and "cannot be cast to class com.openworld" not in line)
    check("no JVM exception on the %s" % name, k == 0, str(k))
print("PASS" if fails == 0 else "FAIL (%d failures)" % fails)
sys.exit(1 if fails else 0)
PY
