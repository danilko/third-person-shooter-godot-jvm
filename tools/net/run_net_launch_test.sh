#!/usr/bin/env bash
# PLAN.md N4 three-instance check: a client's rockets and grenades are flown by the HOST (one MSG_LAUNCH each),
# every peer draws exactly one explosion per blast at the host's point, only the host damages, and forged
# launches are refused. Exit 0 = pass.
set -u
cd "$(dirname "$0")/../.."
G="${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}"
OUT="${OUT:-$(mktemp -d)}"
SCENE=res://src/main/resources/com/openworld/debug/NetLaunchTest.tscn

timeout 120 stdbuf -oL "$G" --headless --path . "$SCENE" -- --role=host > "$OUT/host.log" 2>&1 &
HOST=$!
sleep 4
timeout 115 stdbuf -oL "$G" --headless --path . "$SCENE" -- --role=client > "$OUT/client.log" 2>&1 &
CLIENT=$!
# The observer joins once the client holds both weapons, so it cannot spawn onto a pickup.
sleep 12
timeout 105 stdbuf -oL "$G" --headless --path . "$SCENE" -- --role=observer > "$OUT/observer.log" 2>&1 &
OBS=$!
timeout 105 stdbuf -oL "$G" --headless --path . "$SCENE" -- --role=observer --drop-detonations > "$OUT/observer-drop.log" 2>&1 &
DROP=$!
wait $CLIENT $OBS $DROP $HOST

grep -h "\[netlaunch\] SUMMARY" "$OUT/host.log" "$OUT/client.log" "$OUT/observer.log" "$OUT/observer-drop.log"
python3 - "$OUT/host.log" "$OUT/client.log" "$OUT/observer.log" "$OUT/observer-drop.log" <<'PY'
import re, sys
host, client, obs, dropped = (open(p, errors="replace").read() for p in sys.argv[1:5])
def summary(text):
    m = re.search(r"\[netlaunch\] SUMMARY (.*)", text)
    return dict(kv.split("=", 1) for kv in m.group(1).split() if "=" in kv) if m else {}
hs, cs, os_, ds = summary(host), summary(client), summary(obs), summary(dropped)
fails = 0
def check(label, ok, detail):
    global fails
    fails += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<62} {detail}")
g = lambda d, k: float(d.get(k, 0))
honest = int(g(cs, "rockets") + g(cs, "grenades"))
check("client fired 3 rockets and threw 2 grenades", honest == 5, f"rockets={cs.get('rockets')} grenades={cs.get('grenades')}")
check("ONE MSG_LAUNCH per launch (+4 forged)", g(cs, "launch_sent") == honest + 4, f"launch_sent={cs.get('launch_sent')}")
check("every honest launch flown by the host", g(hs, "launch_accepted") == honest, f"launch_accepted={hs.get('launch_accepted')}")
check("the host's puppet cue spawned no second projectile", g(hs, "launch_cue_host_skipped") == honest, f"skipped={hs.get('launch_cue_host_skipped')}")
check("the host broadcast every detonation", g(hs, "detonation_broadcast") == honest, f"broadcast={hs.get('detonation_broadcast')}")
check("the host drew one explosion per blast", g(hs, "explosion_vfx") == honest, f"explosion_vfx={hs.get('explosion_vfx')}")
check("the host's blasts damaged the target", g(hs, "target_damage") > 0, f"target_damage={hs.get('target_damage')}")
# A cosmetic copy never reaches Health: had one tried to damage the target, the client would have counted a
# suppressed relay. (Its damage_request_sent is SELF fall damage from the harness teleporting its body.)
check("the client's predicted blasts tried to damage no one", g(cs, "damage_relay_suppressed") == 0,
      f"suppressed={cs.get('damage_relay_suppressed')} (self damage requests sent: {cs.get('damage_request_sent')})")
for name, d in (("client", cs), ("observer", os_)):
    check(f"{name}: received every detonation", g(d, "detonation_received") == honest, f"received={d.get('detonation_received')}")
    check(f"{name}: its own copy exploded at the host's point, each one", g(d, "detonation_snapped") == honest,
          f"snapped={d.get('detonation_snapped')} no_copy={d.get('detonation_no_local_copy')} timeout={d.get('detonation_local_timeout')}")
    check(f"{name}: exactly one explosion drawn per blast", g(d, "explosion_vfx") == honest, f"explosion_vfx={d.get('explosion_vfx')}")
    check(f"{name}: dealt no damage", g(d, "target_damage") == 0, f"target_damage={d.get('target_damage')}")
snaps = [float(x) for x in re.findall(r"\[launch\] snapped \S+ by ([\d.]+) m", client)]
print(f"        client prediction vs host blast: {', '.join('%.2f' % x for x in snaps)} m")
check("CONTROL: a replayed launch", g(hs, "launch_rejected_stale_seq") == 1, f"stale_seq={hs.get('launch_rejected_stale_seq')}")
check("CONTROL: a launch from 10 m away", g(hs, "launch_rejected_origin_too_far") == 1, f"origin_too_far={hs.get('launch_rejected_origin_too_far')}")
check("CONTROL: a launch for a body the sender does not own", g(hs, "launch_rejected_not_owner") == 1, f"not_owner={hs.get('launch_rejected_not_owner')}")
check("CONTROL: a launch aimed backwards", g(hs, "launch_rejected_aim_diverged") == 1, f"aim_diverged={hs.get('launch_rejected_aim_diverged')}")
check("CONTROL: detonations lost -> every copy explodes on its own, once", g(ds, "detonation_dropped_debug") == honest
      and g(ds, "detonation_local_timeout") == honest and g(ds, "explosion_vfx") == honest,
      f"dropped={ds.get('detonation_dropped_debug')} timeout={ds.get('detonation_local_timeout')} explosion_vfx={ds.get('explosion_vfx')}")
check("nothing rate-limited", g(hs, "drop_rate_limited") == 0, f"drop_rate_limited={hs.get('drop_rate_limited')}")
print("RESULT:", "PASS" if fails == 0 else "FAIL", f"({fails} failures)  logs in {sys.argv[1].rsplit('/',1)[0]}")
sys.exit(1 if fails else 0)
PY
