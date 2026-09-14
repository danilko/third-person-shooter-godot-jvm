#!/usr/bin/env bash
# PLAN.md N2 two-instance check: a client's knife swing is ONE MSG_MELEE the host resolves on its own copy,
# landing the knife's damage, and forged damage requests / swings are refused and counted. Exit 0 = pass.
set -u
cd "$(dirname "$0")/../.."
G="${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}"
OUT="${OUT:-$(mktemp -d)}"
SCENE=res://src/main/resources/com/openworld/debug/NetMeleeTest.tscn

timeout 100 stdbuf -oL "$G" --headless --path . "$SCENE" -- --role=host > "$OUT/host.log" 2>&1 &
HOST=$!
sleep 4
timeout 95 stdbuf -oL "$G" --headless --path . "$SCENE" -- --role=client > "$OUT/client.log" 2>&1 &
CLIENT=$!
wait $CLIENT $HOST

grep -h "\[netmelee\] SUMMARY" "$OUT/host.log" "$OUT/client.log"
python3 - "$OUT/host.log" "$OUT/client.log" <<'PY'
import re, sys
host, client = (open(p, errors="replace").read() for p in sys.argv[1:3])
def summary(text):
    m = re.search(r"\[netmelee\] SUMMARY (.*)", text)
    return dict(kv.split("=", 1) for kv in m.group(1).split() if "=" in kv) if m else {}
hs, cs = summary(host), summary(client)
fails = 0
def check(label, ok, detail):
    global fails
    fails += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<58} {detail}")
def h(k): return float(hs.get(k, 0))
def c(k): return float(cs.get(k, 0))
taps = int(c("taps"))
resolved = [(int(n), [x for x in re.split(r",\s*", hits.strip()) if x]) for n, hits in re.findall(r"\[melee\] host resolved #(\d+) -> \[([^\]]*)\]", host)]
check("client tapped the knife", taps == 6, f"taps={taps}")
check("ONE MSG_MELEE per tap (+3 forged swings)", c("melee_sent") == taps + 3, f"melee_sent={cs.get('melee_sent')}")
check("every honest swing accepted by the host", h("melee_accepted") == taps, f"melee_accepted={hs.get('melee_accepted')}")
check("every host-resolved swing landed on the target", len(resolved) == taps and all(len(r[1]) == 1 for r in resolved),
      f"{sum(1 for r in resolved if len(r[1]) == 1)} of {len(resolved)} resolved swings hit it")
check("client prediction and host agree on hits", c("melee_predicted_hits") == h("melee_resolved_hits") == taps,
      f"predicted={cs.get('melee_predicted_hits')} resolved={hs.get('melee_resolved_hits')}")
dmg = h("target_damage")
per = dmg / taps if taps else 0
# The knife's stab is 40; the host applies it through the bone the sweep met (Health.getDamageMultiplier).
check("the host landed the knife's stab per swing (and no forged damage)", taps > 0 and any(abs(per - 40 * m) < 0.05 for m in (0.5, 0.75, 1.0, 4.0)),
      f"target_damage={dmg} = {per:.2f} per swing (stab 40 x bone multiplier)")
check("CONTROL: damage naming an attacker the sender does not own", h("damage_request_rejected_not_owner") == 1, f"not_owner={hs.get('damage_request_rejected_not_owner')}")
check("CONTROL: 'self' damage on someone else's body", h("damage_request_rejected_self_mismatch") == 1, f"self_mismatch={hs.get('damage_request_rejected_self_mismatch')}")
check("CONTROL: unattributed damage is malformed", h("drop_invalid_damage_request") == 1, f"drop_invalid_damage_request={hs.get('drop_invalid_damage_request')}")
check("CONTROL: absurd damage", h("damage_request_rejected_damage_too_high") == 1, f"damage_too_high={hs.get('damage_request_rejected_damage_too_high')}")
check("CONTROL: area damage is refused outright (N4)", h("damage_request_rejected_kind_refused") == 1, f"kind_refused={hs.get('damage_request_rejected_kind_refused')}")
check("an honest self-damage request is still accepted", h("damage_request_accepted") == 1, f"accepted={hs.get('damage_request_accepted')}")
check("CONTROL: a replayed swing", h("melee_rejected_stale_seq") == 1, f"stale_seq={hs.get('melee_rejected_stale_seq')}")
check("CONTROL: a swing from 10 m away", h("melee_rejected_origin_too_far") == 1, f"origin_too_far={hs.get('melee_rejected_origin_too_far')}")
check("CONTROL: a swing for a body the sender does not own", h("melee_rejected_not_owner") == 1, f"not_owner={hs.get('melee_rejected_not_owner')}")
check("nothing rate-limited", h("drop_rate_limited") == 0, f"drop_rate_limited={hs.get('drop_rate_limited')}")
print("RESULT:", "PASS" if fails == 0 else "FAIL", f"({fails} failures)  logs in {sys.argv[1].rsplit('/',1)[0]}")
sys.exit(1 if fails else 0)
PY
