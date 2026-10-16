#!/usr/bin/env bash
# PLAN.md 3.1b: a motorcycle on TWO peers. DebugWorld, host + client (DebugHarness --bike-test=<rider>): the host parks
# a bike on the west ring road; the rider's player gets on, rides, SLIDES (throttle + full left + Space) and brakes.
# Both peers print the bike every 0.1 s. The lean, the counter-steered front wheel and the rear-wheel dust are read from
# the bike's MOTION, and the helmet / rider pose from the seat occupancy, so the observing peer must draw the same with
# no message of its own. Samples are paired by the bike's PLACE (the puppet runs a snapshot behind). Asserted:
#   * the observer sees the bike, the rider seated and the rider's gear (helmet + pose) built;
#   * the bike really slides on the simulating peer (slip past 15 deg);
#   * the observer's lean is within 6 deg of the simulator's at the same place on >= 90 % of the ride + slide;
#   * the peak lean in the slide agrees within 6 deg; the front wheel within 10 deg where the slip is past 14 deg;
#   * the observer raises dust on >= 50 % of the samples where the simulator does; no JVM exception on either peer.
#   tools/net/run_net_bike.sh [--control] [host|guest ...] [--bike=TRB1]     default: both riders
# --control: the OBSERVER draws the old yaw-rate lean, the bars' front wheel and no dust (Motorcycle.slideLean false).
set -u
cd "$(dirname "$0")/../.."
G="${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}"
OUT="${OUT:-$(mktemp -d)}"
SECS="${SECS:-40}"
SCENE=res://src/main/resources/com/openworld/world/DebugWorld.tscn
EXTRA=""
BIKE=TRB1
CASES=()
for a in "$@"; do
  case "$a" in
    --control) EXTRA="--bike-test-control" ;;
    --bike=*) BIKE="${a#--bike=}" ;;
    *) CASES+=("$a") ;;
  esac
done
[ ${#CASES[@]} -eq 0 ] && CASES=(host guest)
fails=0
for c in "${CASES[@]}"; do
  d="$OUT/$c"
  mkdir -p "$d"
  timeout -k 5 $((SECS + 8)) stdbuf -oL "$G" --headless --path . "$SCENE" -- --net=host --bike-test=$c --bike-id=$BIKE $EXTRA > "$d/host.log" 2>&1 &
  host=$!
  sleep 6
  timeout -k 5 $SECS stdbuf -oL "$G" --headless --path . "$SCENE" -- --net=join --bike-test=$c --bike-id=$BIKE $EXTRA > "$d/client.log" 2>&1 &
  client=$!
  wait $client $host 2>/dev/null
  echo "== rider: $c ($BIKE)  logs in $d"
  python3 - "$c" "$d/host.log" "$d/client.log" <<'PY' || fails=$((fails + 1))
import re, sys
rider = sys.argv[1]
logs = {"host": open(sys.argv[2], errors="replace").read(), "guest": open(sys.argv[3], errors="replace").read()}
obs_role = "guest" if rider == "host" else "host"
LINE = re.compile(r"\[biketest\] role=(\w+) unix_ms=(\d+) pos=([-\d.]+),([-\d.]+),([-\d.]+) lean=([-\d.]+) wheel=([-\d.]+) "
                  r"slip=([-\d.]+) dust=(\d) gear=(\d+) seated=(\d) sim=(\d)")
def samples(text):
    out = []
    for m in LINE.finditer(text):
        out.append(dict(ms=int(m.group(2)), x=float(m.group(3)), z=float(m.group(5)), lean=float(m.group(6)),
                        wheel=float(m.group(7)), slip=float(m.group(8)), dust=int(m.group(9)), gear=int(m.group(10)),
                        seated=int(m.group(11)), sim=int(m.group(12))))
    return out
sim = samples(logs[rider]); obs = samples(logs[obs_role])
def phase(name):
    m = re.search(r"\[biketest\] phase %s unix_ms=(\d+)" % name, logs[rider])
    return int(m.group(1)) if m else None
ride, slide, brake, done = phase("ride"), phase("slide"), phase("brake"), phase("done")
fails = 0
def check(name, ok, detail=""):
    global fails
    print("  %s  %-64s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        fails += 1
check("the rider rode the whole script", None not in (ride, slide, brake, done), str((ride, slide, brake, done)))
if None in (ride, slide, brake, done):
    print("FAIL"); sys.exit(1)
check("the simulating peer simulates the bike", any(s["sim"] for s in sim if ride <= s["ms"] <= done))
seated = [s for s in obs if ride <= s["ms"] <= brake]
check("the observer sees the bike and the rider seated", len(seated) > 20 and all(s["seated"] for s in seated), "%d samples" % len(seated))
check("... and builds the rider's gear (helmet + pose)", seated and all(s["gear"] >= 1 for s in seated))
sl = [s for s in sim if slide <= s["ms"] <= brake + 500]
check("the bike slides on the simulating peer", sl and max(abs(s["slip"]) for s in sl) > 15.0,
      "slip max %.0f deg" % max([abs(s["slip"]) for s in sl] or [0]))
def nearest(o):
    """the simulator at the observer's PLACE: the closest point on its path (samples 0.1 s apart, i.e. ~1.5 m at speed,
    interpolated linearly), within 1.5 s before the observer's time -- it draws a snapshot behind -- and 0.5 m"""
    best, bd = None, 1e9
    for a, b in zip(sim, sim[1:]):
        if not (o["ms"] - 1500 <= b["ms"] and a["ms"] <= o["ms"] + 100):
            continue
        dx, dz = b["x"] - a["x"], b["z"] - a["z"]
        L = dx * dx + dz * dz
        t = 0.0 if L < 1e-9 else max(0.0, min(1.0, ((o["x"] - a["x"]) * dx + (o["z"] - a["z"]) * dz) / L))
        px, pz = a["x"] + t * dx, a["z"] + t * dz
        d = (px - o["x"]) ** 2 + (pz - o["z"]) ** 2
        if d < bd:
            bd = d
            best = {k: a[k] + t * (b[k] - a[k]) for k in ("lean", "wheel", "slip")}
            best["dust"] = a["dust"] or b["dust"]
    return best if best is not None and bd < 0.5 ** 2 else None
pairs = [(o, nearest(o)) for o in obs if ride + 500 <= o["ms"] <= brake + 500]
pairs = [(o, s) for o, s in pairs if s is not None]
lean_ok = sum(1 for o, s in pairs if abs(o["lean"] - s["lean"]) <= 6.0)
worst = max([abs(o["lean"] - s["lean"]) for o, s in pairs] or [0])
check("the observer's lean matches at the same place", len(pairs) > 20 and lean_ok >= 0.9 * len(pairs),
      "%d / %d within 6 deg (worst %.1f)" % (lean_ok, len(pairs), worst))
po = max([abs(o["lean"]) for o in obs if slide <= o["ms"] <= brake + 800] or [0])
ps = max([abs(s["lean"]) for s in sl] or [0])
check("the peak lean in the slide agrees", abs(po - ps) <= 6.0, "observer %.1f, simulator %.1f deg" % (po, ps))
wp = [(o, s) for o, s in pairs if abs(s["slip"]) > 14.0]
wheel_ok = sum(1 for o, s in wp if abs(o["wheel"] - s["wheel"]) <= 10.0)
check("the front wheel is counter-steered on the observer too", len(wp) >= 3 and wheel_ok >= 0.85 * len(wp),
      "%d / %d within 10 deg" % (wheel_ok, len(wp)))
dp = [(o, s) for o, s in pairs if s["dust"]]
dust_ok = sum(1 for o, s in dp if o["dust"])
check("the observer raises the dust where the simulator does", len(dp) >= 3 and dust_ok >= 0.5 * len(dp),
      "%d / %d samples" % (dust_ok, len(dp)))
for name, text in logs.items():
    k = sum(1 for line in text.splitlines() if "Exception" in line and "cannot be cast to class com.openworld" not in line)
    check("no JVM exception on the %s" % name, k == 0, str(k))
print("PASS" if fails == 0 else "FAIL (%d failures)" % fails)
sys.exit(1 if fails else 0)
PY
done
[ $fails -eq 0 ] && echo "RESULT PASS" || echo "RESULT FAIL ($fails case(s))"
exit $fails
