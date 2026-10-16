#!/usr/bin/env python3
"""Builds the car's held / sliding sounds (audio.Sound.CAR_HORN / CAR_SKID; PLAN.md F11), both LOOPS:

    assets/audio/vehicle/horn.wav   loop, the horn held (a short tap still plays a short beep: Vehicle stops it)
    assets/audio/vehicle/skid.wav   loop, tyres squealing while they slide (handbrake drift, a locked brake, a spin)

    python3 tools/audio/build_vehicle_sfx.py [--src /data/danilko/game_assets/audio] [--check]

Sources (CC0, own recordings, CREDITS.md; Freesound HQ PREVIEWS until the originals are downloaded with a login):
HORN = misperpodcast 733553 "Beeping car horn from inside car, engine off" (a 2008 Fiat Panda: a small-car horn,
right for kei cars and hatchbacks); two ~0.3 s beeps at ~410 Hz, at 0.55 s and 2.45 s. SKID = audible-edge 71737
"Chrysler LHS tire squeal 02" (Rode NTG2 into a Zoom H4); the loudest squeal is 4.10-4.60 s at ~1.07-1.24 kHz, with
the engine under it.

Each loop is the steady middle of one event: the horn's closed on whole cycles of its measured tone (the end moved
up to 3 ms to where it matches the start), the squeal's (not periodic: its pitch drifts) with a 60 ms equal-power
cross-fade. Loop points go in the WAV's `smpl` chunk (Godot loops it with no .import edit, as the siren / engine).

NOTHING HERE WAS AUDITIONED BY EAR (2026-10-16): the cuts are by spectrum. Listen in game.
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_weapon_sfx import SR, load, normalise, loudness  # noqa: E402
from build_siren import write_loop_wav  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, "assets", "audio", "vehicle")
HORN = "freesound_cc0/fiat_panda_horn_misperpodcast_733553.mp3"
SKID = "freesound_cc0/chrysler_tire_squeal_audible_edge_71737.mp3"
HORN_AT = (2.50, 2.68)     # s: the steady part of the second (cleaner, louder) beep
SKID_AT = (4.10, 4.55)     # s: the loudest squeal
TARGET = {"horn": -16.0, "skid": -20.0}   # LUFS (max momentary)


def tone_hz(x, lo, hi):
    """The strongest partial between lo and hi Hz (a zero-padded FFT: fine to ~0.5 Hz)."""
    n = 1 << 18
    sp = np.abs(np.fft.rfft(x * np.hanning(len(x)), n))
    f = np.fft.rfftfreq(n, 1.0 / SR)
    m = (f > lo) & (f < hi)
    return float(f[m][np.argmax(sp[m])])


def periodic_loop(x, hz):
    """Whole cycles of `hz` from `x`, the end moved up to 3 ms to where it best matches the start, 10 ms cross-fade."""
    cycle = SR / hz
    nominal = int(round(int(len(x) * 0.8 / cycle) * cycle))
    w = int(0.01 * SR)
    a = x[:w]
    best, lag = -2.0, nominal
    for d in range(nominal - int(0.003 * SR), min(len(x) - w, nominal + int(0.003 * SR))):
        b = x[d:d + w]
        c = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
        if c > best:
            best, lag = c, d
    seg = x[:lag].copy()
    fade = int(0.01 * SR)
    k = np.linspace(0.0, 1.0, fade)
    seg[:fade] = seg[:fade] * np.sqrt(k) + x[lag:lag + fade] * np.sqrt(1.0 - k)
    return seg, best


def crossfade_loop(x, fade_s=0.06):
    """A loop of a non-periodic sound: the last fade_s is folded over the start (equal power)."""
    fade = int(fade_s * SR)
    seg = x[:-fade].copy()
    k = np.linspace(0.0, 1.0, fade)
    seg[:fade] = seg[:fade] * np.sqrt(k) + x[-fade:] * np.sqrt(1.0 - k)
    return seg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/data/danilko/game_assets/audio")
    ap.add_argument("--check", action="store_true", help="build nothing: are the files there")
    a = ap.parse_args()
    if a.check:
        missing = [n for n in ("horn", "skid") if not os.path.exists(os.path.join(OUT, n + ".wav"))]
        for n in missing:
            print(f"FAIL: assets/audio/vehicle/{n}.wav is missing")
        print("RESULT", "FAIL" if missing else "PASS")
        return 1 if missing else 0
    horn_src = load(os.path.join(a.src, HORN))
    h = horn_src[int(HORN_AT[0] * SR):int(HORN_AT[1] * SR)]
    hz = tone_hz(h, 300, 500)
    horn, corr = periodic_loop(h, hz)
    horn = normalise(horn, TARGET["horn"])
    skid_src = load(os.path.join(a.src, SKID))
    s = skid_src[int(SKID_AT[0] * SR):int(SKID_AT[1] * SR)]
    shz = tone_hz(s, 800, 1600)
    skid = normalise(crossfade_loop(s), TARGET["skid"])
    os.makedirs(OUT, exist_ok=True)
    write_loop_wav(os.path.join(OUT, "horn.wav"), horn)
    write_loop_wav(os.path.join(OUT, "skid.wav"), skid)
    print(f"  horn: {len(horn) / SR:.3f} s loop, tone {hz:.1f} Hz, self-match {corr:.2f}, {loudness(horn):.1f} LUFS")
    print(f"  skid: {len(skid) / SR:.3f} s loop, squeal {shz:.0f} Hz, {loudness(skid):.1f} LUFS")
    print("RESULT PASS -- then: godot --headless --path . --import")
    return 0


if __name__ == "__main__":
    sys.exit(main())
