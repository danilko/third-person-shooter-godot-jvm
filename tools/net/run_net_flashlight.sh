#!/usr/bin/env bash
# PLAN.md 3.2: the flashlight on TWO peers (snapshot flags bit 14). DebugWorld, host + client (DebugHarness
# --flash-test): each peer owns one; the host's goes on at 4 s and off at 12 s, the guest's at 6 s and 14 s (each on its
# own clock from both players being in); the host holds an ASR1 (the gun mount), the guest is empty-handed (the body
# mount). Every peer prints each player's light every 0.25 s. Asserted, both ways:
#   * while an owner's light is on (1.5 s after the switch, to 0.5 s before the next), the OTHER peer shows it on, with
#     a visible beam on the SAME mount the owner drew (gun / body: each peer picks it from the weapon it sees);
#   * a puppet's beam casts no shadow (cost), the owner's does;
#   * after it goes off, 1.5 s later the other peer shows it off; no JVM exception on either peer.
#   tools/net/run_net_flashlight.sh
set -u
cd "$(dirname "$0")/../.."
G="${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}"
OUT="${OUT:-$(mktemp -d)}"
mkdir -p "$OUT"
SECS="${SECS:-36}"
SCENE=res://src/main/resources/com/openworld/world/DebugWorld.tscn
timeout -k 5 $((SECS + 8)) stdbuf -oL "$G" --headless --path . "$SCENE" -- --net=host --flash-test > "$OUT/host.log" 2>&1 &
host=$!
sleep 6
timeout -k 5 $SECS stdbuf -oL "$G" --headless --path . "$SCENE" -- --net=join --flash-test > "$OUT/client.log" 2>&1 &
client=$!
wait $client $host 2>/dev/null
echo "logs in $OUT"
python3 - "$OUT/host.log" "$OUT/client.log" <<'PY'
import re, sys
logs = {"host": open(sys.argv[1], errors="replace").read(), "guest": open(sys.argv[2], errors="replace").read()}
def rows(text):
    out = []
    for m in re.finditer(r"\[flash\] role=\w+ t=([\d.]+)((?: \w+=\d,\w+,\d,\d)+)", text):
        r = {"t": float(m.group(1))}
        for k, on, mount, vis, sh in re.findall(r"(\w+)=(\d),(\w+),(\d),(\d)", m.group(2)):
            r[k] = (int(on), mount, int(vis), int(sh))
        out.append(r)
    return out
R = {k: rows(v) for k, v in logs.items()}
fails = 0
def check(name, ok, detail=""):
    global fails
    print("  %s  %-66s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        fails += 1
for owner, window in (("host", (4.0, 12.0)), ("guest", (6.0, 14.0))):
    other = "guest" if owner == "host" else "host"
    key = owner + "p"
    own = [r for r in R[owner] if key in r and window[0] + 1.5 <= r["t"] <= window[1] - 0.5]
    obs = [r for r in R[other] if key in r and window[0] + 1.5 <= r["t"] <= window[1] - 0.5]
    check("%s's light is on at home" % owner, len(own) > 10 and all(r[key][0] == 1 and r[key][2] == 1 for r in own), "%d samples" % len(own))
    mounts = {r[key][1] for r in own}
    check("... the %s shows it on, beam visible" % other, len(obs) > 10 and sum(r[key][0] == 1 and r[key][2] == 1 for r in obs) >= 0.9 * len(obs),
          "%d / %d" % (sum(r[key][0] == 1 and r[key][2] == 1 for r in obs), len(obs)))
    want = "gun" if owner == "host" else "body"      # the host holds an ASR1, the guest is empty-handed
    check("... the owner draws it on the %s" % want, mounts == {want}, str(sorted(mounts)))
    check("... and the %s on the same mount" % other, obs and all(r[key][1] == want for r in obs),
          str(sorted({r[key][1] for r in obs})))
    check("... the owner's beam casts shadows, the puppet's does not", own and all(r[key][3] == 1 for r in own) and obs and all(r[key][3] == 0 for r in obs))
    after = [r for r in R[other] if key in r and r["t"] >= window[1] + 2.5]
    check("... and goes off on the %s after the switch" % other, len(after) > 3 and all(r[key][0] == 0 and r[key][2] == 0 for r in after), "%d samples" % len(after))
for name, text in logs.items():
    k = sum(1 for line in text.splitlines() if "Exception" in line and "cannot be cast to class com.openworld" not in line)
    check("no JVM exception on the %s" % name, k == 0, str(k))
print("RESULT PASS" if fails == 0 else "RESULT FAIL (%d failures)" % fails)
sys.exit(1 if fails else 0)
PY
