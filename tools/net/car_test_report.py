#!/usr/bin/env python3
"""Reads run_net_car_test.sh's logs: what each peer saw of both cars and both players over the 4 s of throttle."""
import math, re, sys
out, cases = sys.argv[1], sys.argv[2:]
V = r"\(([-\d.]+),([-\d.]+),([-\d.]+)\)"
LINE = re.compile(r"\[cartest\] unix_ms=(\d+) ket=" + V + r" yaw=([-\d.]+) spc=" + V + r" yaw=([-\d.]+) poc=" + V + r" yaw=([-\d.]+)(.*)")
PL = re.compile(r" (hostp|guestp)=" + V + r" hp=([-\d.]+) car=(\w+)")
def rows(path):
    r = []
    for m in LINE.finditer(open(path, errors="replace").read()):
        g = m.groups()
        d = {"t": int(g[0]), "ket": tuple(map(float, g[1:4])), "ket_yaw": float(g[4]),
             "spc": tuple(map(float, g[5:8])), "spc_yaw": float(g[8]),
             "poc": tuple(map(float, g[9:12])), "poc_yaw": float(g[12])}
        for who, x, y, z, hp, car in PL.findall(g[13]):
            d[who] = (float(x), float(y), float(z)); d[who + "_hp"] = float(hp)
        r.append(d)
    return r
def at(r, t):
    return min(r, key=lambda d: abs(d["t"] - t)) if r else None
def dist(a, b): return math.hypot(a[0] - b[0], a[2] - b[2])
fails = 0
def check(label, ok, detail=""):
    global fails
    fails += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<58} {detail}")
for c in cases:
    drv, obs = c.split(":")
    d = f"{out}/{c.replace(':', '_')}"
    logs = {"host": open(f"{d}/host.log", errors="replace").read(), "guest": open(f"{d}/client.log", errors="replace").read()}
    R = {"host": rows(f"{d}/host.log"), "guest": rows(f"{d}/client.log")}
    other = "host" if drv == "guest" else "guest"
    print(f"-- {c}: the {drv} drives, the {other} is the obstacle's side")
    m0 = re.search(r"drive start unix_ms=(\d+)", logs[drv]); m1 = re.search(r"drive end unix_ms=(\d+)", logs[drv])
    if not (m0 and m1 and R["host"] and R["guest"]):
        check("the drive ran on both peers", False, f"start={bool(m0)} end={bool(m1)} host_rows={len(R['host'])} guest_rows={len(R['guest'])}")
        continue
    t0, t1 = int(m0.group(1)), int(m1.group(1)) + 1500
    car = "spc" if obs == "ped" else "poc"
    a, b = at(R[drv], t0), at(R[drv], t1)          # the driver's own view of its car
    oa, ob = at(R[other], t0), at(R[other], t1)    # the other peer's view
    run = dist(a[car], b[car]); drift = abs(b[car][0] - a[car][0])
    turn = abs((b[car + "_yaw"] - a[car + "_yaw"] + 180) % 360 - 180)
    for name, text in logs.items():
        n = len(re.findall(r"java\.lang\.\w+Exception", text)) - len(re.findall(r"ClassCastException: class godot\.api\.Resource", text))
        check(f"no JVM exception on the {name}", n == 0, str(n))
    if obs == "ped":
        who = "hostp" if other == "host" else "guestp"
        check("the car drives on", run > 10.0, f"{run:.1f} m in 5.5 s")
        n = at(R[drv], t0 + 2000)                  # its line while it passes the person (it leaves the pad later)
        drift = abs(n[car][0] - a[car][0]); turn = abs((n[car + "_yaw"] - a[car + "_yaw"] + 180) % 360 - 180)
        check("the car keeps its line past the person", drift < 0.5 and turn < 5.0, f"drift {drift:.2f} m, turned {turn:.1f} deg")
        for peer, r0, r1 in ((other, oa, ob), (drv, a, b)):
            if who not in r1: check(f"the person exists on the {peer}", False); continue
            side = abs(r1[who][0] - a[car][0]); moved = dist(r0[who], r1[who])
            check(f"on the {peer}: the person is out of the car's path", side > 1.2 and moved < 8.0,
                  f"{side:.2f} m off the line, moved {moved:.2f} m, hp {r1[who + '_hp']:.0f}")
        check("the person is unhurt (own peer)", ob.get(who + "_hp", 0) >= oa.get(who + "_hp", 1e9),
              f"hp {oa.get(who + '_hp', -1):.0f} -> {ob.get(who + '_hp', -1):.0f}")
    else:
        simpeer = "host" if (obs == "parked" or other == "host") else "guest"   # who simulates the truck that is hit
        s0, s1 = at(R[simpeer], t0), at(R[simpeer], t1)
        pushed = dist(s0["ket"], s1["ket"])
        rose_k = max(r["ket"][1] for r in R[simpeer] if r["t"] >= t0) - s0["ket"][1]
        rose_p = max(r["poc"][1] for r in R[drv] if r["t"] >= t0) - a["poc"][1]
        check("the police car reaches the truck and goes on", run > 7.0, f"ran {run:.1f} m")
        check(f"the truck is moved where it is simulated ({simpeer})", 0.5 < pushed < 40.0, f"{pushed:.2f} m")
        check("neither car is thrown", rose_k < 1.5 and rose_p < 1.5, f"truck rose {rose_k:.2f} m, police car rose {rose_p:.2f} m")
        tl = min(R["host"][-1]["t"], R["guest"][-1]["t"])          # the last instant both peers printed: at rest
        eh, eg = at(R["host"], tl), at(R["guest"], tl)
        for peer, e in (("host", eh), ("guest", eg)):
            gap = math.dist(e["poc"], e["ket"])
            check(f"on the {peer}: the cars do not end inside each other", gap > 2.5, f"centres {gap:.2f} m apart")
        check("both peers agree where the cars ended", dist(eh["ket"], eg["ket"]) < 1.0 and dist(eh["poc"], eg["poc"]) < 1.0,
              f"truck {dist(eh['ket'], eg['ket']):.2f} m, police car {dist(eh['poc'], eg['poc']):.2f} m apart")
print(f"{'PASS' if fails == 0 else 'FAIL'}: {fails} failed")
sys.exit(1 if fails else 0)
