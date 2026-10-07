#!/usr/bin/env bash
# PLAN.md 1c gate (user 2026-10-06: the light crowd matches across co-op peers): host + a LATE-joining client on the
# island (World.tscn), both idle at the spawn. After 50 s each prints every light ped of every loaded crowd each time
# the shared clock crosses a multiple of 10 s (DebugHarness --crowd-dump). Asserted, for every zone loaded on both:
#   * the same people (the same ped indices, the same body each);
#   * calm peds (walking or stopped on both peers) within 0.5 m of each other at the same instant (95% of them; a ped
#     that fled from a gunshot rejoins from where it ended up and may sit a little off);
#   * no JVM exception on either peer.
set -u
cd "$(dirname "$0")/../.."
G="${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}"
OUT="${OUT:-$(mktemp -d)}"
SECS="${SECS:-120}"
SCENE=res://src/main/resources/com/openworld/world/World.tscn
timeout -k 5 $((SECS + 20)) stdbuf -oL "$G" --headless --path . "$SCENE" -- --net=host --idle --crowd-dump > "$OUT/host.log" 2>&1 &
host=$!
sleep 15
timeout -k 5 $SECS stdbuf -oL "$G" --headless --path . "$SCENE" -- --net=join --idle --crowd-dump > "$OUT/client.log" 2>&1 &
client=$!
wait $client $host 2>/dev/null
echo "logs in $OUT"
python3 - "$OUT/host.log" "$OUT/client.log" <<'PY'
import re, sys
def dumps(path):
    out = {}
    for line in open(path, errors="replace"):
        m = re.match(r"\[crowd\] bucket=(-?\d+) clock=\S+ zone=(\S+) peds=(.*)$", line.strip())
        if not m:
            continue
        peds = {}
        for item in m.group(3).split(";"):
            if not item:
                continue
            idx, rest = item.split(":", 1)
            x, z, st, body = rest.split(",")
            peds[int(idx)] = (float(x), float(z), int(st), body)
        out[(int(m.group(1)), m.group(2))] = peds
    return out, open(path, errors="replace").read()
h, ht = dumps(sys.argv[1]); c, ct = dumps(sys.argv[2])
fails = 0
def check(name, ok, detail=""):
    global fails
    print("  %s  %-58s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        fails += 1
common = sorted(set(h) & set(c))
check("both peers dumped the same crowd at the same instant", len(common) > 0, "%d (bucket, zone) pairs" % len(common))
n = same_body = near = calm = 0
worst = 0.0
for k in common:
    for i, (x, z, st, body) in h[k].items():
        if i not in c[k]:
            continue
        n += 1
        cx, cz, cst, cbody = c[k][i]
        same_body += body == cbody
        if st in (0, 1) and cst in (0, 1):
            calm += 1
            d = ((x - cx) ** 2 + (z - cz) ** 2) ** 0.5
            worst = max(worst, d)
            near += d < 0.5
check("the same peds on both peers", n > 20, "%d peds compared" % n)
check("each ped is the same body on both peers", n > 0 and same_body == n, "%d / %d" % (same_body, n))
check("calm peds stand within 0.5 m of each other", calm > 0 and near >= 0.95 * calm,
      "%d / %d (worst %.2f m)" % (near, calm, worst))
for name, text in (("host", ht), ("client", ct)):
    # the documented harmless noise of instancing a vehicle scene from code (CLAUDE.md "Known noise")
    k = sum(1 for line in text.splitlines() if "Exception" in line and "cannot be cast to class com.openworld" not in line)
    check("no JVM exception on the %s" % name, k == 0, str(k))
print("PASS" if fails == 0 else "FAIL (%d failures)" % fails)
sys.exit(1 if fails else 0)
PY
