#!/usr/bin/env bash
# PLAN.md P0 0.5 gate: co-op on the REAL DebugWorld scene (not a test host). Host + client headless, each
# started through DebugHarness (`-- --net=host|join`, the F6/F7 path), each holding a movement action
# (`--hold-action=`), with the per-peer character dump on (`--net-diag`). Exit 0 = pass.
# Two phases (walk, tour). Asserted: no packet dropped by the rate limiter on either peer, no JVM exception, the joiner spawns
# at DebugWorld's PlayerSpawn (on the ground, not in the sea at the origin), and each player's walk
# shows up on the other peer.
set -u
cd "$(dirname "$0")/../.."
G="${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}"
OUT="${OUT:-$(mktemp -d)}"
SECS="${SECS:-30}"
SCENE=res://src/main/resources/com/openworld/world/DebugWorld.tscn
run_pair() {   # <dir> <host args> <client args>
  mkdir -p "$1"
  timeout -k 5 $((SECS + 12)) stdbuf -oL "$G" --headless --path . "$SCENE" -- --net=host --net-diag $2 > "$1/host.log" 2>&1 &
  local host=$!
  sleep 6
  timeout -k 5 $SECS stdbuf -oL "$G" --headless --path . "$SCENE" -- --net=join --net-diag $3 > "$1/client.log" 2>&1 &
  local client=$!
  wait $client $host 2>/dev/null
}
# Phase A: both walk on foot (spawn + replication both ways).
run_pair "$OUT/walk" --hold-action=left --hold-action=forward
# Phase B: the client tours every zone (DebugHarness auto-walk) so the host streams BOTH zones' AI and
# its snapshots split into more MTU frames — the load that made the client's limiter drop ~20 packets/s.
run_pair "$OUT/tour" --idle --auto-walk
# Phase C (2026-10-06): the client buys at a real shop counter, then dies; the host must respawn it; both print the clock.
SECS_SAVE=$SECS; SECS=62
run_pair "$OUT/coop" --coop-test --coop-test
SECS=$SECS_SAVE
echo "logs in $OUT"
python3 - "$OUT/walk/host.log" "$OUT/walk/client.log" "$OUT/tour/host.log" "$OUT/tour/client.log" \
    "$OUT/coop/host.log" "$OUT/coop/client.log" <<'PY'
import re, sys
host, client, thost, tclient, chost, cclient = (open(p, errors="replace").read() for p in sys.argv[1:7])
SPAWN = (-330.0, 6.1, 10.0)   # DebugWorld.tscn PlayerSpawn (re-derived 2026-09-28)
# CLAUDE.md "Known noise": instancing Vehicle.tscn from code logs this cast (the embedded CharacterInfo binds late).
KNOWN_NOISE = r"java\.lang\.ClassCastException: class godot\.api\.Resource cannot be cast to class com\.openworld\.character\.CharacterInfo"
fails = 0
def check(label, ok, detail):
    global fails
    fails += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<52} {detail}")
def chars(text):
    out = {}
    for cid, own, ctrl, x, y, z in re.findall(r"CHR (\S+) own=(\d+) auth=\S+ vis=\S+ ctrl=(\S+)\s+seat=\S+ pos=\(([-\d.]+),([-\d.]+),([-\d.]+)\)", text):
        out.setdefault(cid, []).append((int(own), ctrl, float(x), float(y), float(z)))
    return out
hc, cc = chars(host), chars(client)
check("client connected", "NetworkManager: assigned local peer id 2" in client, "")
check("no rate-limited packet on the host", "rate limit exceeded" not in host, f"{host.count('rate limit exceeded')} drops")
check("no rate-limited packet on the client", "rate limit exceeded" not in client, f"{client.count('rate limit exceeded')} drops")
for name, text in (("host", host), ("client", client)):
    n = len(re.findall(r"java\.lang\.\w+Exception", text)) - len(re.findall(KNOWN_NOISE, text))
    check(f"no JVM exception on the {name}", n == 0, f"{n}")
cli = [k for k, v in cc.items() if v[0][0] == 2 and v[0][1] == "PlayerController"]
check("client owns one player body", len(cli) == 1, str(cli))
if cli:
    cid = cli[0]
    first = cc[cid][0]
    d = ((first[2] - SPAWN[0]) ** 2 + (first[4] - SPAWN[2]) ** 2) ** 0.5
    check("  ... spawned at PlayerSpawn, on the ground", d < 25.0 and abs(first[3] - 5.6) < 3.0,
          f"first seen at ({first[2]:.1f},{first[3]:.1f},{first[4]:.1f}), {d:.1f} m from the marker in XZ")
    hp = [p for p in hc.get(cid, []) if p[1] == "NetworkController"]
    moved = max((abs(p[4] - hp[0][4]) + abs(p[2] - hp[0][2]) for p in hp), default=0.0)
    check("client's walk is seen on the host", len(hp) > 2 and moved > 8.0, f"host copy moved {moved:.1f} m over {len(hp)} dumps")
hst = [k for k, v in hc.items() if v[0][0] == 1 and v[0][1] == "PlayerController"]
if hst:
    cp = [p for p in cc.get(hst[0], []) if p[1] == "NetworkController"]
    moved = max((abs(p[4] - cp[0][4]) + abs(p[2] - cp[0][2]) for p in cp), default=0.0)
    check("host's walk is seen on the client", len(cp) > 2 and moved > 8.0, f"client copy moved {moved:.1f} m over {len(cp)} dumps")
else:
    check("host has a local player", False, "")
print("  -- tour: the client streams both zones")
check("tour: client connected", "NetworkManager: assigned local peer id 2" in tclient, "")
check("tour: host streamed a second zone", len(set(re.findall(r"LOADED zone '(\S+)'", thost))) >= 2,
      str(sorted(set(re.findall(r"LOADED zone '(\S+)'", thost)))))
for name, text in (("host", thost), ("client", tclient)):
    check(f"tour: no rate-limited packet on the {name}", "rate limit exceeded" not in text, f"{text.count('rate limit exceeded')} drops")
    n = len(re.findall(r"java\.lang\.\w+Exception", text)) - len(re.findall(KNOWN_NOISE, text))
    check(f"tour: no JVM exception on the {name}", n == 0, f"{n}")
print("  -- coop: purchase, respawn, clock")
m = re.search(r"\[coop\] at counter \S+ item=(\S*)", cclient)
check("coop: client stood at a shop counter", m is not None and m.group(1) != "", m.group(0) if m else "no counter line")
check("coop: the host accepted the client's purchase", "NetworkManager: shop sale" in chost, "")
m = re.search(r"\[coop\] carries (\S+)=(true|false)", cclient)
check("coop: the client's own body carries what it bought", m is not None and m.group(2) == "true", m.group(0) if m else "")
mb = re.search(r"\[coop\] host buy \S+ unix_ms=(\d+)", chost)
ms = re.search(r"\[coop\] host puppet carries .* unix_ms=(\d+)", cclient)
lag = (int(ms.group(1)) - int(mb.group(1))) / 1000.0 if mb and ms else None
check("coop: a HOST purchase reaches the client within 1 s", lag is not None and lag < 1.0,
      ("%.2f s" % lag) if lag is not None else ("host bought: %s, client saw: %s" % (bool(mb), bool(ms))))
m = re.search(r"\[coop\] client hud stars=(-?\d+)", cclient)
check("coop: the host's wanted stars reach the client's HUD", m is not None and m.group(1) == "2", m.group(0) if m else "no line")
m = re.search(r"\[coop\] respawn alive=(\w+) owned=(\w+) pos=(.*?) respawns=(-?\d+)", cclient)
check("coop: the client is respawned, alive and owned", m is not None and m.group(1) == "true" and m.group(2) == "true"
      and int(m.group(4)) >= 1, m.group(0) if m else "")
check("coop: the host ran the respawn", "RespawnSystem: HOSPITALIZED -> respawned" in chost, "")
check("coop: no game over on either peer", "GAME_OVER" not in chost and "GAME_OVER" not in cclient, "")
def clock(text):
    m = re.search(r"\[coop\] clock hours=([-\d.eE]+) unix_ms=(\d+) hps=([-\d.eE]+)", text)
    return (float(m.group(1)), int(m.group(2)), float(m.group(3))) if m else None
hc_, cc_ = clock(chost), clock(cclient)
if hc_ and cc_:
    host_then = hc_[0] + (cc_[1] - hc_[1]) / 1000.0 * hc_[2]
    diff = abs(((cc_[0] - host_then) + 12.0) % 24.0 - 12.0) * 60.0
    check("coop: the client's clock matches the host's", diff < 2.0, f"{diff:.2f} game min apart")
else:
    check("coop: both peers printed the clock", False, f"host={hc_} client={cc_}")
print("  -- coop: die seated, then the respawn")
m = re.search(r"\[coop\] seated=(\w+) hud=(\S*)", cclient)
check("coop: the client took a seat in the parked car", m is not None and m.group(1) == "true", m.group(0) if m else "no line")
m = re.search(r"\[coop\] seated respawn alive=(\w+) owned=(\w+) inCar=(\w+) riders=(\d+) hud=(\S*)", cclient)
check("coop: after a seated death the client is respawned on foot", m is not None and m.group(1) == "true"
      and m.group(2) == "true" and m.group(3) == "false" and m.group(5) == "ON_FOOT", m.group(0) if m else "no line")
check("coop: no car on the client holds a player", m is not None and m.group(4) == "0", m.group(0) if m else "")
m = re.search(r"\[coop\] host car riders=(\d+)", chost)
check("coop: no car on the host holds a player", m is not None and m.group(1) == "0", m.group(0) if m else "no line")
check("coop: the host ran two respawns", chost.count("RespawnSystem: HOSPITALIZED -> respawned") >= 2,
      str(chost.count("RespawnSystem: HOSPITALIZED -> respawned")))
for name, text in (("host", chost), ("client", cclient)):
    n = len(re.findall(r"java\.lang\.\w+Exception", text)) - len(re.findall(KNOWN_NOISE, text))
    check(f"coop: no JVM exception on the {name}", n == 0, f"{n}")
print("PASS (0 failures)" if fails == 0 else f"FAIL ({fails} failures)")
sys.exit(1 if fails else 0)
PY
