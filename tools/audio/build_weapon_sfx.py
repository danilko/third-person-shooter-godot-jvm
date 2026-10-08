#!/usr/bin/env python3
"""Build the game's weapon sounds from the CC0 source libraries, at one consistent loudness.

    python3 tools/audio/build_weapon_sfx.py [--src /data/danilko/game_assets/audio] [--only ASR1,PIS1] [--check]

Sources (downloaded once, with LICENSE.txt + SOUNDS.csv each, outside the repo):
  still_north_firearms_cc0/Prepared SFX Library   gunshots (EQ'd + limited by the authors)
  still_north_firearms_cc0/Raw Master Tracks      handling: mag out/in, slide, bolt, pump, cylinder
  still_north_medieval_cc0/Weapon Textures         melee swings
  kenney_cc0/interface-sounds                      hit-marker tick
All CC0; see assets/audio/README.md and CREDITS.md.

What it does, per output (the RECIPES table is the whole design):
  fire   - the gun's NEAR take from Prepared, from its onset, cut to `tail` seconds with a fade.
  reload - handling takes from Raw, each cut to its main transient, laid out on a timeline as long as the weapon's
           reload (1 / reload_speed from weapon/stats/<id>.tres), so the sound ends when the reload does.
  swing  - one take from a melee swing recording.
Then every file is loudness-normalised (max momentary loudness, BS.1770) to its category target plus a per-weapon
offset, and peak-limited at -1 dBFS: the same steps as Audacity's Loudness Normalization + Limiter, but repeatable.
Output: 48 kHz mono 16-bit WAV in assets/audio/weapons/ (mono, because every weapon sound is 3D).
"""
import argparse, json, os, re, subprocess, sys, tempfile
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, "assets", "audio", "weapons")
STATS = os.path.join(REPO, "src", "main", "resources", "com", "openworld", "weapon", "stats")
SR = 48000

# Loudness = MAX MOMENTARY (BS.1770 K-weighted, 400 ms window): the loudest moment, the measure that suits short
# effects (integrated LUFS gates out anything under 0.4 s). Targets before each item's own offset:
TARGET = {"fire": -13.0, "reload": -24.0, "swing": -20.0}   # fire = the shipped Rifle_fire.wav level
PEAK = 10 ** (-1.0 / 20)                                                    # -1 dBFS limiter ceiling

PREP = "still_north_firearms_cc0/Prepared SFX Library"
RAW = "still_north_firearms_cc0/Raw Master Tracks"
MED = "still_north_medieval_cc0/Weapon Textures"

# fire: (file, tail seconds, gain offset dB, pitch factor)
# reload: list of (file, max segment seconds, position as fraction of the reload time, take index, gain dB)
RECIPES = {
    "PIS1": {"fire": (f"{PREP}/Bersa/F_47P.wav", 0.9, -2.0, 1.0),
             "reload": [(f"{RAW}/Bersa/F_3.wav", 0.6, 0.05, 0, 0), (f"{RAW}/Bersa/F_4.wav", 0.6, 0.45, 0, 0),
                        (f"{RAW}/Bersa/F_17.wav", 0.5, 0.78, 0, 2)]},
    "PIS2": {"fire": (f"{PREP}/1911/A_42P.wav", 1.1, 0.0, 1.0),
             "reload": [(f"{RAW}/1911/A_5.wav", 0.6, 0.05, 0, 0), (f"{RAW}/1911/A_4.wav", 0.6, 0.45, 0, 0),
                        (f"{RAW}/1911/A_17.wav", 0.5, 0.78, 0, 2)]},
    "DUP1": {"fire": (f"{PREP}/Walther PPQ/X_39P.wav", 0.9, -1.0, 1.0),
             "reload": [(f"{RAW}/Walther PPQ/X_3.wav", 0.5, 0.04, 0, 0), (f"{RAW}/Walther PPQ/X_3.wav", 0.5, 0.18, 0, -2),
                        (f"{RAW}/Walther PPQ/X_2.wav", 0.5, 0.45, 0, 0), (f"{RAW}/Walther PPQ/X_2.wav", 0.5, 0.6, 0, -2),
                        (f"{RAW}/Walther PPQ/X_17.wav", 0.5, 0.82, 0, 2)]},
    # a .38 snub pitched down ~12 % reads as a heavier revolver
    "REV1": {"fire": (f"{PREP}/Smith & Wesson 642/V_27P.wav", 1.6, 1.0, 0.88),
             "reload": [(f"{RAW}/Smith & Wesson 642/V_0.wav", 0.6, 0.03, 0, 0),
                        (f"{RAW}/Smith & Wesson 642/V_3.wav", 0.7, 0.2, 0, 0),
                        (f"{RAW}/Smith & Wesson 642/V_18.wav", 0.9, 0.45, 0, 0),
                        (f"{RAW}/Smith & Wesson 642/V_1.wav", 0.6, 0.8, 0, 1)]},
    "SMG1": {"fire": (f"{PREP}/Carl Gustav M45/G_31P.wav", 0.7, -1.0, 1.0),
             "reload": [(f"{RAW}/Carl Gustav M45:Swedish K/G_9.wav", 0.6, 0.05, 0, 0),
                        (f"{RAW}/Carl Gustav M45:Swedish K/G_8.wav", 0.6, 0.45, 0, 0),
                        (f"{RAW}/Carl Gustav M45:Swedish K/G_10.wav", 0.6, 0.76, 0, 2)]},
    "ASR1": {"fire": (f"{PREP}/AK-47/C_28P.wav", 0.8, 0.0, 1.0),
             "reload": [(f"{RAW}/AK-47/C_11.wav", 0.6, 0.05, 0, 0), (f"{RAW}/AK-47/C_10.wav", 0.6, 0.45, 0, 0),
                        (f"{RAW}/AK-47/C_14.wav", 0.8, 0.72, 0, 2)]},
    "ASR2": {"fire": (f"{PREP}/AR-15/D_32P.wav", 0.8, 0.0, 1.0),
             "reload": [(f"{RAW}/AR-15/D_5.wav", 0.6, 0.05, 0, 0), (f"{RAW}/AR-15/D_4.wav", 0.6, 0.45, 0, 0),
                        (f"{RAW}/AR-15/D_13.wav", 0.6, 0.76, 0, 2)]},
    "SHG1": {"fire": (f"{PREP}/Nova/O_21P.wav", 1.4, 1.0, 1.0),
             "reload": [(f"{RAW}/Nova/O_7.wav", 0.5, 0.05, 0, 0), (f"{RAW}/Nova/O_7.wav", 0.5, 0.25, 0, -1),
                        (f"{RAW}/Nova/O_7.wav", 0.5, 0.45, 0, 0), (f"{RAW}/Nova/O_6.wav", 0.9, 0.68, 0, 2)]},
    "SNR1": {"fire": (f"{PREP}/Mosin Nagant/M_21P.wav", 2.0, 2.0, 1.0),
             "reload": [(f"{RAW}/Mosin Nagant/M_2.wav", 0.5, 0.03, 0, 0), (f"{RAW}/Mosin Nagant/M_3.wav", 0.6, 0.15, 0, 0),
                        (f"{RAW}/Mosin Nagant/M_18.wav", 0.8, 0.4, 0, 0), (f"{RAW}/Mosin Nagant/M_6.wav", 0.6, 0.7, 0, 0),
                        (f"{RAW}/Mosin Nagant/M_7.wav", 0.5, 0.86, 0, 1)]},
    # melee: the swing whoosh played on each attack (MeleeItem plays fire_audio)
    "MEW1": {"swing": (f"{MED}/Dagger Swing.wav", 0.5, 0.0, 1.0, 0)},
    "MEW2": {"swing": (f"{MED}/Axe Swing.wav", 0.8, 1.0, 1.0, 0)},
    "BAT1": {"swing": (f"{MED}/Spear Swing.wav", 0.55, 0.0, 1.0, 0)},   # 0.7 ran into a second swing in the take
    "Fist": {"swing": (f"{MED}/Dagger Swing.wav", 0.4, -4.0, 1.12, 1)},
}
UI = {"hit_marker": ("kenney_cc0/interface-sounds/Audio/tick_002.ogg", 0.08, -6.0)}   # (file, length, peak dBFS)


def load(path, pitch=1.0):
    af = ["aformat=channel_layouts=mono"]
    if pitch != 1.0:
        af = [f"asetrate={int(96000 * pitch)}", "aresample=96000"] + af
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-af", ",".join(af), "-ar", str(SR), "-f", "f32le", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64)


def envelope(x, ms=5):
    n = max(1, int(SR * ms / 1000))
    return np.convolve(np.abs(x), np.ones(n) / n, "same")


def takes(x, gap=0.25, on=0.25, off=0.03):
    """Onsets/ends of the distinct events in a recording (a raw take often holds several)."""
    env = envelope(x); pk = env.max()
    if pk <= 0:
        return []
    loud = env > on * pk; quiet_len = int(gap * SR)
    out, i, n = [], 0, len(x)
    while i < n:
        idx = np.flatnonzero(loud[i:])
        if not len(idx):
            break
        s = i + idx[0]; e = s
        while e < n:
            nxt = np.flatnonzero(env[e:min(n, e + quiet_len)] > off * pk)
            if not len(nxt):
                break
            e += nxt[-1] + 1
            if e >= n or not (env[e:min(n, e + quiet_len)] > off * pk).any():
                break
        out.append((max(0, s - int(0.008 * SR)), e))
        i = e + quiet_len
    return out


def cut(x, max_len, take=0, fixed=False):
    """One event: from its onset to its end (reload clicks), or to onset + max_len (fixed: shots, swings)."""
    t = takes(x)
    if not t:
        raise SystemExit("no event found")
    s, e = t[min(take, len(t) - 1)]
    i = min(take, len(t) - 1)
    nxt = t[i + 1][0] - int(0.02 * SR) if i + 1 < len(t) else len(x)       # never run into the next take
    end = min(s + int(max_len * SR), nxt) if fixed else min(max(e, s + int(0.12 * SR)), s + int(max_len * SR), nxt)
    seg = x[s:min(end, len(x))].copy()
    fade = min(len(seg) // 3, int(0.04 * SR))
    if fade:
        seg[-fade:] *= np.linspace(1, 0, fade)
    return seg / (np.abs(seg).max() or 1)


def _biquad(x, b, a):
    y = np.zeros_like(x); x1 = x2 = y1 = y2 = 0.0
    b0, b1, b2 = b; _, a1, a2 = a
    for i, v in enumerate(x):
        o = b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, v, y1, o
        y[i] = o
    return y


try:
    from scipy.signal import lfilter as _lfilter
except ImportError:
    _lfilter = None
K1 = ([1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585])
K2 = ([1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621])     # BS.1770 K-weighting at 48 kHz


def loudness(x):
    """Max momentary loudness (LUFS): K-weighted mean square over 400 ms windows, 10 ms hop, x zero-padded."""
    x = np.concatenate([np.zeros(int(0.4 * SR)), x, np.zeros(int(0.4 * SR))])
    f = (lambda v, b, a: _lfilter(b, a, v)) if _lfilter else _biquad
    y = f(f(x, *K1), *K2) ** 2
    w = int(0.4 * SR); c = np.concatenate([[0.0], np.cumsum(y)])
    ms = (c[w:] - c[:-w])[:: int(0.01 * SR)] / w
    return -0.691 + 10 * np.log10(ms.max() + 1e-12)


def limit(x, ceiling=PEAK, knee=0.8):
    """Soft-knee peak limiter: transparent below knee*ceiling, tanh above it (no hard clip)."""
    knee = ceiling * knee
    y = x.copy(); a = np.abs(x); over = a > knee
    y[over] = np.sign(x[over]) * (knee + (ceiling - knee) * np.tanh((a[over] - knee) / (ceiling - knee)))
    return y


def normalise(x, target, knee=0.8):
    """Gain to the target, then limit; repeat, because limiting lowers the loudness it was aimed at.
    Gunshots use a lower knee (knee=0.5): they are nearly all peak, and a gentle limiter cannot bring them up."""
    for _ in range(6):
        x = limit(x * 10 ** ((target - loudness(x)) / 20), knee=knee)
        if abs(loudness(x) - target) < 0.2:
            break
    return x


def write_wav(path, x):
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "-",
                    "-c:a", "pcm_s16le", path], input=pcm, check=True)


def reload_seconds(wid):
    p = os.path.join(STATS, f"{wid}.tres")
    m = re.search(r"^reload_speed\s*=\s*([\d.]+)", open(p).read(), re.M)
    return 1.0 / float(m.group(1))


def build(src, wid, recipe, report):
    for kind, spec in recipe.items():
        if kind == "fire":
            f, tail, gain, pitch = spec
            x = cut(load(os.path.join(src, f), pitch), tail, fixed=True)
            x = normalise(x, TARGET["fire"] + gain, knee=0.5)
            name = f"{wid}_fire.wav"
        elif kind == "swing":
            f, length, gain, pitch, take = spec
            x = normalise(cut(load(os.path.join(src, f), pitch), length, take, fixed=True), TARGET["swing"] + gain)
            name = f"{wid}_swing.wav"
        else:
            total = reload_seconds(wid)
            x = np.zeros(int(total * SR))
            for f, max_len, at, take, gain in spec:
                seg = cut(load(os.path.join(src, f)), max_len, take) * 10 ** (gain / 20)
                s = int(at * total * SR); e = min(len(x), s + len(seg))
                x[s:e] += seg[:e - s]
            x = normalise(x, TARGET["reload"])
            name = f"{wid}_reload.wav"
        write_wav(os.path.join(OUT, name), x)
        report.append((name, len(x) / SR, loudness(x), 20 * np.log10(np.abs(x).max() or 1e-9)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/data/danilko/game_assets/audio")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    only = set(filter(None, a.only.split(",")))
    report = []
    for wid, recipe in RECIPES.items():
        if not only or wid in only:
            build(a.src, wid, recipe, report)
    for name, (f, length, peak_db) in UI.items():
        if only and name not in only:
            continue
        x = load(os.path.join(a.src, f))[: int(length * SR)]
        x = x / (np.abs(x).max() or 1) * 10 ** (peak_db / 20)
        dest = os.path.join(REPO, "assets", "audio", f"{name}.wav")
        write_wav(dest, x)
        report.append((os.path.basename(dest), len(x) / SR, loudness(x), peak_db))
    print(f"{'file':<22}{'sec':>6}{'LUFS(Mmax)':>11}{'peak dBFS':>11}")
    for name, sec, lufs, pk in report:
        print(f"{name:<22}{sec:6.2f}{lufs:11.1f}{pk:11.1f}")


if __name__ == "__main__":
    main()
