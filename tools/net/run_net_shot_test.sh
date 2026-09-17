#!/usr/bin/env bash
# PLAN.md N1 two-instance check: a client shotgun pull is ONE MSG_SHOT, accepted by the host, and the
# host's regenerated pellets hit what the client predicted. Exit 0 = pass.
set -u
cd "$(dirname "$0")/../.."
G="${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}"
OUT="${OUT:-$(mktemp -d)}"
SCENE=res://src/main/resources/com/openworld/debug/NetShotTest.tscn

timeout 140 stdbuf -oL "$G" --headless --path . "$SCENE" -- --role=host > "$OUT/host.log" 2>&1 &
HOST=$!
sleep 4
timeout 130 stdbuf -oL "$G" --headless --path . "$SCENE" -- --role=client > "$OUT/client.log" 2>&1 &
CLIENT=$!
# Two watching peers (N1b), started once the client holds the gun so neither spawns onto the pickup:
# one plays the host's shot results, one drops them to exercise the fallback. The client waits for both.
sleep 10
timeout 120 stdbuf -oL "$G" --headless --path . "$SCENE" -- --role=observer > "$OUT/observer.log" 2>&1 &
OBS=$!
timeout 120 stdbuf -oL "$G" --headless --path . "$SCENE" -- --role=observer --drop-results > "$OUT/observer-drop.log" 2>&1 &
DROP=$!
wait $CLIENT $HOST $OBS $DROP

grep -h "\[netshot\] SUMMARY" "$OUT/host.log" "$OUT/client.log" "$OUT/observer.log" "$OUT/observer-drop.log"
python3 - "$OUT/host.log" "$OUT/client.log" "$OUT/observer.log" "$OUT/observer-drop.log" <<'PY'
import re, sys
host, client, obs, drop = (open(p, errors="replace").read() for p in sys.argv[1:5])
def summary(text):
    m = re.search(r"\[netshot\] SUMMARY (.*)", text)
    return dict(kv.split("=", 1) for kv in m.group(1).split() if "=" in kv) if m else {}
def shots(text, who):
    return {int(k): (d, h.split(", ")) for k, d, h in re.findall(r"\[shot\] %s #(\d+) dirs (\S+) (?:hits \d+ )?-> \[(.*)\]" % who, text)}
hs, cs = summary(host), summary(client)
hp, cp = shots(host, "host resolved"), shots(client, "client predicted")
fails = 0
def check(label, ok, detail):
    global fails
    fails += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<46} {detail}")
pulls = int(cs.get("pulls", 0))
check("client pulled the trigger", pulls >= 10, f"pulls={pulls}")
check("ONE message per pull (not per pellet)", pulls > 0 and int(cs.get("shot_sent", -1)) == pulls + 10,
      f"shot_sent={cs.get('shot_sent')} ({pulls} pulls + 10 forged; SHG1 has 8 pellets)")
resolved_honest = [k for k in shots(host, "host resolved") if k < pulls]
check("every honest pull accepted by the host", pulls > 0 and len(resolved_honest) == pulls,
      f"{len(resolved_honest)} of {pulls} resolved")
def stat(k): return int(hs.get(k, 0))
check("CONTROL: a replayed counter is refused", stat("shot_rejected_stale_seq") == 1, f"stale_seq={stat('shot_rejected_stale_seq')}")
check("CONTROL: an origin 10 m off is refused", stat("shot_rejected_origin_too_far") == 1, f"origin_too_far={stat('shot_rejected_origin_too_far')}")
check("CONTROL: a zero cone is refused", stat("shot_rejected_spread_too_narrow") == 1, f"spread_too_narrow={stat('shot_rejected_spread_too_narrow')}")
check("CONTROL: a reversed aim is refused", stat("shot_rejected_aim_diverged") == 1, f"aim_diverged={stat('shot_rejected_aim_diverged')}")
check("CONTROL: a burst of 6 is cut by the fire budget", 3 <= stat("shot_rejected_too_fast") <= 5,
      f"too_fast={stat('shot_rejected_too_fast')}, accepted={stat('shot_accepted')} (= {pulls} honest + burst survivors)")
check("2.8 item 9: the client's hits are confirmed to it by the host", int(cs.get("hit_confirmed_local", 0)) > 0,
      f"hit_confirmed_local={cs.get('hit_confirmed_local')} (host target_damage={hs.get('target_damage')})")
check("  ... and an observer gets none credited to itself", int(summary(obs).get("hit_confirmed_local", 1)) == 0,
      f"observer hit_confirmed_local={summary(obs).get('hit_confirmed_local')}")
check("nothing rate-limited", hs.get("drop_rate_limited") == "0", f"drop_rate_limited={hs.get('drop_rate_limited')}")
both = [n for n in cp if n in hp]
dirs_same = [n for n in both if hp[n][0] == cp[n][0]]
for n in both:
    if hp[n][0] != cp[n][0]:
        print(f"        #{n} pellet directions differ: client {cp[n][0]} host {hp[n][0]}")
check("host regenerated the client's exact pellet rays", pulls > 0 and len(both) >= pulls and len(dirs_same) == len(both),
      f"{len(dirs_same)} of {len(both)} pulls identical")
pellets = sum(len(cp[n][1]) for n in both)
agree = sum(1 for n in both for a, b in zip(cp[n][1], hp[n][1]) if a == b)
# Not exact by design: the target's hitboxes are animated, and the client's puppet of it is a few
# centimetres off the host's, so a pellet grazing an edge can land either side.
check("pellet hits mostly agree (animated hitboxes)", pellets > 0 and agree >= 0.8 * pellets,
      f"{agree} of {pellets} pellets hit the same thing")
os_, ds = summary(obs), summary(drop)
def ostat(d, k): return int(d.get(k, 0))
resolved_all = shots(host, "host resolved")
got = {int(k): (int(p), int(h)) for k, p, h in re.findall(r"\[shot\] peer got result #(\d+) pellets (\d+) hits (\d+)", obs)}
host_hits = {k: sum(1 for x in v[1] if x != "-") for k, v in resolved_all.items()}
check("N1b: observer received a result for every resolved pull", pulls > 0 and len(got) == len(resolved_all) and len(got) >= pulls,
      f"{len(got)} results for {len(resolved_all)} resolved pulls")
check("N1b: ...with the host's pellet count and hits", pulls > 0 and all(got.get(k) == (8, host_hits[k]) for k in resolved_all),
      f"mismatched: {[k for k in resolved_all if got.get(k) != (8, host_hits[k])]}")
check("N1b: observer drew 8 real tracers per result", len(got) > 0 and ostat(os_, "shot_result_tracer") == 8 * len(got),
      f"tracers={ostat(os_, 'shot_result_tracer')}")
check("N1b: ...and no aim-tracer fallback on top", pulls > 0 and ostat(os_, "cue_fallback_tracer") == 0,
      f"fallback={ostat(os_, 'cue_fallback_tracer')} superseded={ostat(os_, 'cue_tracer_superseded')} waited={ostat(os_, 'cue_tracer_waited_for_result')}")
check("N1b: host drew no fallback for the relayed shots", pulls > 0 and ostat(hs, "cue_fallback_tracer") == 0,
      f"fallback={ostat(hs, 'cue_fallback_tracer')}")
check("N1b CONTROL: results dropped -> one fallback per fire cue", pulls > 0 and ostat(ds, "shot_result_tracer") == 0 and ostat(ds, "cue_fallback_tracer") == pulls,
      f"result tracers={ostat(ds, 'shot_result_tracer')} fallback={ostat(ds, 'cue_fallback_tracer')} (pulls={pulls})")
check("the target took damage", float(hs.get("target_damage", 0)) > 0, f"target_damage={hs.get('target_damage')}")
print("RESULT:", "PASS" if fails == 0 else "FAIL", f"({fails} failures)  logs in {sys.argv[1].rsplit('/',1)[0]}")
sys.exit(1 if fails else 0)
PY
