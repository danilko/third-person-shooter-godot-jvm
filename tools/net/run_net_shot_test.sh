#!/usr/bin/env bash
# PLAN.md N1 two-instance check: a client shotgun pull is ONE MSG_SHOT, accepted by the host, and the
# host's regenerated pellets hit what the client predicted. Exit 0 = pass.
set -u
cd "$(dirname "$0")/../.."
G="${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}"
OUT="${OUT:-$(mktemp -d)}"
SCENE=res://src/main/resources/com/openworld/debug/NetShotTest.tscn

timeout 120 stdbuf -oL "$G" --headless --path . "$SCENE" -- --role=host > "$OUT/host.log" 2>&1 &
HOST=$!
sleep 4
timeout 110 stdbuf -oL "$G" --headless --path . "$SCENE" -- --role=client > "$OUT/client.log" 2>&1
wait $HOST

grep -h "\[netshot\]" "$OUT/host.log" "$OUT/client.log"
python3 - "$OUT/host.log" "$OUT/client.log" <<'PY'
import re, sys
host, client = (open(p, errors="replace").read() for p in sys.argv[1:3])
def summary(text):
    m = re.search(r"\[netshot\] SUMMARY (.*)", text)
    return dict(kv.split("=", 1) for kv in m.group(1).split() if "=" in kv) if m else {}
def shots(text, who):
    return {int(n): h for n, h in re.findall(r"\[shot\] %s #(\d+) (?:for \S+ )?-> \[(.*)\]" % who, text)}
hs, cs = summary(host), summary(client)
hp, cp = shots(host, "host resolved"), shots(client, "client predicted")
fails = 0
def check(label, ok, detail):
    global fails
    fails += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<46} {detail}")
pulls = int(cs.get("pulls", 0))
check("client pulled the trigger", pulls >= 10, f"pulls={pulls}")
check("ONE message per pull (not per pellet)", pulls > 0 and int(cs.get("shot_sent", -1)) == pulls, f"shot_sent={cs.get('shot_sent')}")
check("every pull accepted by the host", pulls > 0 and int(hs.get("shot_accepted", -1)) == pulls,
      f"accepted={hs.get('shot_accepted')} " + " ".join(f"{k}={v}" for k, v in hs.items() if k.startswith("shot_rejected") and v != "0"))
check("nothing rate-limited", hs.get("drop_rate_limited") == "0", f"drop_rate_limited={hs.get('drop_rate_limited')}")
same = [n for n in cp if n in hp and hp[n] == cp[n]]
diff = [n for n in cp if n in hp and hp[n] != cp[n]]
for n in diff:
    print(f"        #{n} client {cp[n]}\n        #{n} host   {hp[n]}")
check("host pellets hit what the client predicted", pulls > 0 and len(same) >= pulls - 1 and len(cp) >= pulls,
      f"{len(same)} identical, {len(diff)} differ, {len(cp)} predicted, {len(hp)} resolved")
check("the target took damage", float(hs.get("target_damage", 0)) > 0, f"target_damage={hs.get('target_damage')}")
print("RESULT:", "PASS" if fails == 0 else "FAIL", f"({fails} failures)  logs in {sys.argv[1].rsplit('/',1)[0]}")
sys.exit(1 if fails else 0)
PY
