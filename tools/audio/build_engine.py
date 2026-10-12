#!/usr/bin/env python3
"""Builds the car engine's sounds (audio.Sound.ENGINE_*; played by carrier.vehicle.EngineAudio):

    assets/audio/engine/start.wav   one shot: the starter's last second and the engine catching
    assets/audio/engine/idle.wav    loop, a steady idle
    assets/audio/engine/low.wav     loop, FIRING[low] Hz   (~2 850 rpm on a four)
    assets/audio/engine/mid.wav     loop, FIRING[mid] Hz   (~4 500 rpm)
    assets/audio/engine/high.wav    loop, FIRING[high] Hz  (~6 600 rpm)

    python3 tools/audio/build_engine.py [--src /data/danilko/game_assets/audio]

Sources (CC0, CREDITS.md): START and IDLE are a parked Toyota Camry, Freesound vacuumfan7072 322552 (a phone
recording: starter from ~9 s, idle from ~12.5 s, thumps at 2 s and 17 s that are not used). LOW / MID / HIGH are cut
from ONE dyno pull of a Scion FR-S, Freesound dezoris 183654: the engine runs from ~2 500 rpm to the redline between
6 s and 22 s, so no part of it is steady. Each loop is therefore RE-TIMED: the firing frequency is tracked through
the pull (a harmonic comb, then a quadratic fit), a second of sound round the moment it passes the band's frequency
is resampled sample by sample so that the pitch stands still at exactly FIRING[band], the pull's rising level is
divided out, and the loop is closed on a whole number of engine cycles (4 firings), the end moved up to 3 ms to
where it matches the start, with a 20 ms cross-fade. The loop points go into each WAV's `smpl` chunk (Godot loops
it with no .import edit, as the siren).

FIRING is the contract with EngineAudio.java (its BAND_HZ): the game plays a band at pitch = wanted Hz / FIRING, so
the two tables must agree -- `--check` compares them and measures each built loop again.

NOTHING HERE WAS AUDITIONED BY EAR (2026-10-12): the cuts are by spectrum. Listen in game.
"""
import argparse
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_weapon_sfx import SR, load, normalise, loudness, write_wav  # noqa: E402
from build_siren import write_loop_wav, level  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, "assets", "audio", "engine")
JAVA = os.path.join(REPO, "src/main/java/com/openworld/carrier/vehicle/EngineAudio.java")
DYNO = "freesound_cc0/dynojet_scion_frs_dezoris_183654.mp3"
CAMRY = "freesound_cc0/toyota_camry_startup_vacuumfan7072_322552.mp3"

FIRING = {"low": 95.0, "mid": 150.0, "high": 220.0}   # Hz; idle's is measured (IDLE_HZ is printed, and checked)
PULL = (6.5, 21.5)        # s, the part of the dyno take where the engine is under load and rising
LOOP_SECONDS = 0.9
FADE = 0.02
TARGET = -24.0            # LUFS, every loop alike: EngineAudio sets the levels
START = (10.35, 12.75)    # s of the Camry take: ~1.2 s of starter, the catch, the first of the idle
IDLE = (13.0, 16.4)       # s, steady idle


def comb(seg, lo, hi, step=0.25):
    """The firing frequency of `seg` in [lo, hi] Hz: the f whose half, whole, 1.5x, double and triple together carry
    the most energy (an engine's loudest partial moves between these from one rpm to the next)."""
    n = 1 << int(np.ceil(np.log2(len(seg) * 4)))
    X = np.abs(np.fft.rfft((seg - seg.mean()) * np.hanning(len(seg)), n))
    hz = SR / n
    best, best_f = -1.0, lo
    for f in np.arange(lo, hi, step):
        s = sum(w * X[int(round(k * f / hz))] for k, w in ((0.5, 0.6), (1.0, 1.0), (1.5, 0.8), (2.0, 1.0), (3.0, 0.7)))
        if s > best:
            best, best_f = s, f
    return best_f


def track(x):
    """Firing frequency through the pull as a quadratic f(t), following the comb from one 0.25 s step to the next
    (so it cannot jump an octave), and the worst distance of a tracked point from the fit (Hz)."""
    ts, fs = [], []
    f = comb(x[int(PULL[0] * SR):int((PULL[0] + 0.5) * SR)], 70.0, 110.0)
    for t in np.arange(PULL[0], PULL[1], 0.25):
        f = comb(x[int(t * SR):int((t + 0.4) * SR)], f * 0.96, f * 1.10)
        ts.append(t + 0.2)
        fs.append(f)
    p = np.polyfit(ts, fs, 2)
    return p, float(np.abs(np.polyval(p, ts) - fs).max())


def steady(x, p, hz):
    """About 1.6 s of the pull round the moment it passes `hz`, resampled so the firing frequency is `hz`
    throughout: output time u maps to source time t with dt/du = hz / f(t)."""
    roots = [r.real for r in np.roots(p - np.array([0, 0, hz])) if abs(r.imag) < 1e-6 and PULL[0] - 1 < r.real < PULL[1] + 1]
    assert roots, f"the pull never passes {hz} Hz"
    t0 = roots[0]
    n = int(1.6 * SR)
    t = np.empty(n)
    cur = t0 - 0.8 * hz / np.polyval(p, t0)
    for i in range(n):                                   # forward Euler at 48 kHz: the map is nearly linear
        t[i] = cur
        cur += hz / np.polyval(p, cur) / SR
    return np.interp(t * SR, np.arange(len(x)), x), t0


def close_loop(x, hz, seconds=LOOP_SECONDS):
    """A loop of whole engine cycles (4 firings each) from the middle of `x`, its end moved up to 3 ms to where it
    matches its start, cross-faded over FADE. Returns (loop, self-match)."""
    cycle = 4.0 * SR / hz
    nominal = int(round(round(seconds * SR / cycle) * cycle))
    start = (len(x) - nominal) // 2 - int(FADE * SR)
    w = int(0.04 * SR)
    a = x[start:start + w]
    best, lag = -2.0, nominal
    for d in range(nominal - int(0.003 * SR), nominal + int(0.003 * SR)):
        b = x[start + d:start + d + w]
        c = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
        if c > best:
            best, lag = c, d
    fade = int(FADE * SR)
    seg = x[start:start + lag].copy()
    k = np.linspace(0.0, 1.0, fade)
    seg[:fade] = seg[:fade] * np.sqrt(k) + x[start + lag:start + lag + fade] * np.sqrt(1.0 - k)
    return seg, best


def idle_hz(x):
    """An idling four fires at 20-35 Hz: the strongest autocorrelation lag in that range."""
    x = x - x.mean()
    n = len(x)
    X = np.fft.rfft(x, 2 * n)
    ac = np.fft.irfft(X * np.conj(X))[:n]
    lo, hi = int(SR / 35.0), int(SR / 20.0)
    return SR / (lo + int(np.argmax(ac[lo:hi])))


def java_table():
    """EngineAudio.java's BAND_HZ = {idle, low, mid, high}."""
    if not os.path.exists(JAVA):
        return None
    m = re.search(r"BAND_HZ\s*=\s*\{([^}]*)\}", open(JAVA).read())
    return [float(v.strip().rstrip("f")) for v in m.group(1).split(",")] if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/data/danilko/game_assets/audio")
    ap.add_argument("--check", action="store_true", help="build nothing: compare with EngineAudio.java and the files")
    a = ap.parse_args()
    dyno = load(os.path.join(a.src, DYNO))
    camry = load(os.path.join(a.src, CAMRY))
    p, err = track(dyno)
    print(f"dyno pull: firing {np.polyval(p, PULL[0]):.1f} -> {np.polyval(p, PULL[1]):.1f} Hz over "
          f"{PULL[0]}-{PULL[1]} s, worst tracked point {err:.1f} Hz off the fit")
    fails = 0
    built = {}
    for band, hz in FIRING.items():
        y, t0 = steady(dyno, p, hz)
        y = level(y)
        seg, corr = close_loop(y, hz)
        seg = normalise(seg, TARGET)
        got = comb(np.tile(seg, 3)[:int(1.0 * SR)], hz * 0.9, hz * 1.1, 0.1)
        built[band] = (seg, hz)
        ok = abs(got - hz) / hz < 0.02      # self-match is reported only: under the dyno room's roar it reads 0.3-0.4
        fails += not ok
        print(f"  {band}: from {t0:.2f} s, {len(seg) / SR:.3f} s loop, measured {got:.1f} Hz (wanted {hz:.0f}), "
              f"self-match {corr:.2f}, {loudness(seg):.1f} LUFS {'ok' if ok else 'FAIL'}")
    idle_src = level(camry[int(IDLE[0] * SR):int(IDLE[1] * SR)])
    ihz = idle_hz(idle_src)
    idle, corr = close_loop(idle_src, ihz, 1.6)
    idle = normalise(idle, TARGET)
    print(f"  idle: {len(idle) / SR:.3f} s loop, firing {ihz:.1f} Hz, self-match {corr:.2f}, {loudness(idle):.1f} LUFS")
    start = camry[int(START[0] * SR):int(START[1] * SR)].copy()
    fo = int(0.5 * SR)
    start[:int(0.01 * SR)] *= np.linspace(0, 1, int(0.01 * SR))
    start[-fo:] *= np.linspace(1, 0, fo) ** 2                 # out under the idle loop that EngineAudio fades in
    start = normalise(start, -22.0)
    print(f"  start: {len(start) / SR:.2f} s, {loudness(start):.1f} LUFS")

    table = java_table()
    want = [round(ihz, 1)] + list(FIRING.values())
    if table is None or any(abs(x - y) > 0.25 for x, y in zip(table, want)) or len(table) != 4:
        print(f"FAIL: EngineAudio.BAND_HZ is {table}, these files are {want}")
        fails += 1
    if a.check:
        for band in ["idle", *FIRING, "start"]:
            if not os.path.exists(os.path.join(OUT, band + ".wav")):
                print(f"FAIL: assets/audio/engine/{band}.wav is missing")
                fails += 1
        print("RESULT", "FAIL" if fails else "PASS")
        return 1 if fails else 0
    os.makedirs(OUT, exist_ok=True)
    for band, (seg, _) in built.items():
        write_loop_wav(os.path.join(OUT, band + ".wav"), seg)
    write_loop_wav(os.path.join(OUT, "idle.wav"), idle)
    write_wav(os.path.join(OUT, "start.wav"), start)
    print("RESULT", "FAIL" if fails else "PASS", "-- then: godot --headless --path . --import")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
