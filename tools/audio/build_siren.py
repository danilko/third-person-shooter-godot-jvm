#!/usr/bin/env python3
"""Builds the looping sirens: assets/audio/siren.wav (audio.Sound.SIREN, the ambulance's ピーポー and the fallback for
the other two), siren_police.wav and siren_fire.wav (WAILS below). What follows describes the ambulance's.

Source: a street recording of a Japanese ambulance passing (the two-tone ピーポー, ~960 / 770 Hz, one cycle every
~1.3 s) -- Freesound thabigm 758375, CC0 (CREDITS.md). It is a pass-by, so this cuts whole cycles out of the loud,
clean part, flattens the pass-by's level swing, and closes the loop:

  * the loop runs from one ピー -> ポー tone change to the same change CYCLES later (a seam there is where the siren
    is discontinuous anyway), the end nudged up to 3 ms so the tone is in phase where it meets the start;
  * the first FADE seconds are cross-faded with what FOLLOWS the cut, so the last sample runs into the first with
    no click;
  * the loop points go into the WAV's `smpl` chunk: Godot's WAV importer (edit/loop_mode=0, "detect from WAV")
    loops it with no .import edit.

    python3 tools/audio/build_siren.py [--src /data/danilko/game_assets/audio] [--at 3.8] [--cycles 2]
"""
import argparse
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_weapon_sfx import SR, load, normalise, loudness  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, "assets", "audio", "siren.wav")
SOURCE = "freesound_cc0/japan_nara_medic_siren_thabigm_758375.mp3"
FADE = 0.02          # s, the loop's cross-fade
TARGET = -20.0       # LUFS (max momentary), as build_sfx's louder world sounds


def highpass(x, hz=350.0):
    """Street rumble out (the siren's lowest tone is ~770 Hz): a brick-wall in the frequency domain."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / SR)
    X *= np.clip((f - hz * 0.7) / (hz * 0.3), 0.0, 1.0)
    return np.fft.irfft(X, len(x))


def level(x, win=0.35):
    """Divides out the slow level swing of the pass-by (RMS over `win` s), so every cycle is as loud as the next."""
    n = int(win * SR)
    rms = np.sqrt(np.convolve(x * x, np.ones(n) / n, "same") + 1e-9)
    return x / np.maximum(rms, rms.max() * 0.15)


def tone_starts(x):
    """Sample indices where the LOW tone (ポー, ~770 Hz) takes over from the high one (ピー, ~960 Hz)."""
    hop, w = int(0.005 * SR), int(0.03 * SR)
    f = np.fft.rfftfreq(w, 1.0 / SR)
    lo, hi = (f > 720) & (f < 830), (f > 900) & (f < 1020)
    win = np.hanning(w)
    d = []
    for i in range(0, len(x) - w, hop):
        X = np.abs(np.fft.rfft(x[i:i + w] * win)) ** 2
        d.append(X[lo].sum() - X[hi].sum())
    d = np.convolve(np.sign(d), np.ones(9) / 9, "same")          # 45 ms majority: one flip per tone change
    return [i * hop + w // 2 for i in range(1, len(d)) if d[i - 1] <= 0 < d[i]]


def loop_cut(x, at, cycles):
    """(start, length, self-match): from the tone change nearest `at` to the same change `cycles` later -- a seam on
    a tone change is where the siren itself is discontinuous -- the end then moved up to 3 ms to match the phase."""
    starts = tone_starts(x)
    i = int(np.argmin([abs(s - at) for s in starts]))
    start, nominal = starts[i], starts[i + cycles] - starts[i]
    w = int(0.03 * SR)
    a = x[start:start + w]
    best, best_lag = -2.0, nominal
    for lag in range(nominal - int(0.003 * SR), nominal + int(0.003 * SR)):
        b = x[start + lag:start + lag + w]
        c = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
        if c > best:
            best, best_lag = c, lag
    return start, best_lag, best


def write_loop_wav(path, x):
    """16-bit mono PCM with a `smpl` chunk looping the whole file (forward)."""
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    fmt = struct.pack("<HHIIHH", 1, 1, SR, SR * 2, 2, 16)
    smpl = struct.pack("<9I", 0, 0, int(1e9 / SR), 60, 0, 0, 0, 1, 0) \
        + struct.pack("<6I", 0, 0, 0, len(x) - 1, 0, 0)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt \
        + b"data" + struct.pack("<I", len(pcm)) + pcm \
        + b"smpl" + struct.pack("<I", len(smpl)) + smpl
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", len(body)) + body)


#: The WAILS (user, 2026-10-12, after hearing the one siren on every vehicle: "quite different, so may still need to
#: split"). No CC0 recording of a JAPANESE patrol car (ウー) or fire engine (ウー + カンカン) was found on Freesound
#: (the Tokyo / Kyoto ones are NonCommercial), so these are the nearest CC0 own-recordings: file -> (source, search
#: from s, search to s, shortest cycle s). One whole sweep, from one LOW point of the tone to the next.
WAILS = {
    "siren_police": ("freesound_cc0/police_siren_nyc_multimax2121_156869.mp3", 4.2, 11.0, 4.5),   # the first slow wail; it yelps from 11 s
    "siren_fire": ("freesound_cc0/firetruck_siren_toronto_trp_717906.mp3", 14.6, 20.7, 3.5),   # after 21 s it has stopped: engine only
}


def pitch_track(x, lo=450.0, hi=1900.0):
    """(times s, dominant tone Hz) every 10 ms over 60 ms windows, median-smoothed over 90 ms."""
    hop, w = int(0.01 * SR), int(0.06 * SR)
    f = np.fft.rfftfreq(w, 1.0 / SR)
    m = (f > lo) & (f < hi)
    win = np.hanning(w)
    hz = np.array([f[m][np.argmax(np.abs(np.fft.rfft(x[i:i + w] * win))[m])] for i in range(0, len(x) - w, hop)])
    k = 9
    pad = np.pad(hz, k // 2, mode="edge")
    hz = np.array([np.median(pad[i:i + k]) for i in range(len(hz))])
    return np.arange(len(hz)) * hop / SR + w / (2.0 * SR), hz


def build_wail(src, name, source, t0, t1, min_cycle):
    """Cuts one sweep of a wailing siren: from the lowest tone in the first part of [t0, t1] to the lowest tone at
    least `min_cycle` later, the end moved up to 3 ms to match the start's phase, cross-faded, levelled."""
    x = level(highpass(load(os.path.join(src, source))))
    t, hz = pitch_track(x)
    sel = (t >= t0) & (t <= t1)
    ts, hs = t[sel], hz[sel]
    first = ts <= ts[0] + (t1 - t0 - min_cycle) * 0.6
    a = ts[first][np.argmin(hs[first])]
    later = ts >= a + min_cycle
    b = ts[later][np.argmin(hs[later])]
    start, nominal = int(a * SR), int((b - a) * SR)
    w = int(0.03 * SR)
    ref = x[start:start + w]
    best, lag = -2.0, nominal
    for d in range(nominal - int(0.003 * SR), nominal + int(0.003 * SR)):
        c = x[start + d:start + d + w]
        v = float(np.dot(ref, c) / (np.linalg.norm(ref) * np.linalg.norm(c) + 1e-12))
        if v > best:
            best, lag = v, d
    fade = int(FADE * SR)
    seg = x[start:start + lag].copy()
    k = np.linspace(0.0, 1.0, fade)
    seg[:fade] = seg[:fade] * np.sqrt(k) + x[start + lag:start + lag + fade] * np.sqrt(1.0 - k)
    seg = normalise(seg, TARGET)
    out = os.path.join(REPO, "assets", "audio", name + ".wav")
    write_loop_wav(out, seg)
    inside = (t >= a) & (t <= b)
    print(f"{os.path.relpath(out, REPO)}: {lag / SR:.3f} s loop from {a:.2f} s, tone {hz[inside].min():.0f}-"
          f"{hz[inside].max():.0f} Hz ({hs[np.argmin(np.abs(ts - a))]:.0f} Hz at the seam's start, "
          f"{hs[np.argmin(np.abs(ts - b))]:.0f} at its end), self-match {best:.3f}, {loudness(seg):.1f} LUFS")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/data/danilko/game_assets/audio")
    ap.add_argument("--at", type=float, default=3.8, help="the loop starts at the tone change nearest this (s)")
    ap.add_argument("--cycles", type=int, default=2)
    ap.add_argument("--only", default="", help="siren | siren_police | siren_fire (default: all three)")
    a = ap.parse_args()
    for name, (source, t0, t1, min_cycle) in WAILS.items():
        if a.only in ("", name):
            build_wail(a.src, name, source, t0, t1, min_cycle)
    if a.only not in ("", "siren"):
        return
    x = level(highpass(load(os.path.join(a.src, SOURCE))))
    start, n, corr = loop_cut(x, int(a.at * SR), a.cycles)
    fade = int(FADE * SR)
    seg = x[start:start + n].copy()
    t = np.linspace(0.0, 1.0, fade)
    seg[:fade] = seg[:fade] * np.sqrt(t) + x[start + n:start + n + fade] * np.sqrt(1.0 - t)
    seg = normalise(seg, TARGET)
    write_loop_wav(OUT, seg)
    print(f"{os.path.relpath(OUT, REPO)}: {n / SR:.3f} s loop ({a.cycles} cycles from {start / SR:.2f} s), "
          f"self-match {corr:.3f}, {loudness(seg):.1f} LUFS, peak {20 * np.log10(np.abs(seg).max()):.1f} dBFS")


if __name__ == "__main__":
    main()
