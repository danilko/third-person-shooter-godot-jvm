#!/usr/bin/env python3
"""Build the game's non-weapon sounds (com.openworld.audio.Sound) from the CC0 source libraries.

    python3 tools/audio/build_sfx.py [--src /data/danilko/game_assets/audio] [--only door_slide,ui_click]

Every Sound with variants is <file>_<n>.wav, n = 1..variants (Sounds picks one at random each play). Each output is
cut from one take (or LAYERED from several, `layers`), loudness-normalised to its row's target (max momentary LUFS,
BS.1770, the scale build_weapon_sfx.py uses) and peak-limited at -1 dBFS. Output: 48 kHz mono 16-bit WAV (mono:
the 3D ones need it, and a mono UI click costs nothing). Then `godot --headless --path . --import`.

The SPECS table is the whole design: (Sound file, target LUFS, max seconds, pitch, list of variants), a variant
being one source path, or a list of (path, offset seconds, gain dB) layered into one sound. Sources (each folder has
LICENSE.txt + SOUNDS.csv): kenney_cc0 (impact-sounds, interface-sounds, rpg-audio, sci-fi-sounds, music-jingles),
still_north_firearms_cc0 (Raw: dry fire, safety), still_north_medieval_cc0 (weapon impacts, draws). All CC0.

NOTHING HERE WAS AUDITIONED BY EAR (2026-10-08): the picks are by name and waveform. Listen in game and change the
row (PLAN.md P2b "Listen and tune").
"""
import argparse, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_weapon_sfx import SR, load, cut, normalise, loudness, write_wav  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, "assets", "audio")

K = "kenney_cc0"
IMP = f"{K}/impact-sounds/Audio"
UI = f"{K}/interface-sounds/Audio"
RPG = f"{K}/rpg-audio/Audio"
SCI = f"{K}/sci-fi-sounds/Audio"
FS = "freesound_cc0"   # Freesound CC0 sounds (one file each; URL, author and licence in CREDITS.md)
JIN = f"{K}/music-jingles/Audio/Steel jingles"
RAW = "still_north_firearms_cc0/Raw Master Tracks"
MED = "still_north_medieval_cc0"


def k5(prefix, n=5, ext="ogg"):
    """Kenney's numbered takes prefix_000 .. prefix_004."""
    return [f"{prefix}_{i:03d}.{ext}" for i in range(n)]


# file -> (target LUFS, max seconds, pitch, [variants]). A variant: a path, or [(path, offset s, gain dB), ...].
SPECS = {
    # characters
    # bullet impacts per SurfaceType (FLESH, METAL, STONE, WOOD, DEFAULT -> STONE, GLASS)
    "sfx/impact_flesh": (-24, 0.35, 1.0, k5(f"{IMP}/impactPunch_medium")),
    "sfx/impact_metal": (-22, 0.6, 1.0, k5(f"{IMP}/impactMetal_light")),
    "sfx/impact_stone": (-23, 0.4, 1.0, k5(f"{IMP}/impactPlate_light")),
    "sfx/impact_wood": (-23, 0.4, 1.0, k5(f"{IMP}/impactWood_light")),
    "sfx/impact_glass": (-24, 0.5, 1.0, k5(f"{IMP}/impactGlass_light")),
    # melee contact
    "sfx/melee_hit_flesh": (-17, 0.45, 1.0, k5(f"{IMP}/impactPunch_heavy")),
    "sfx/melee_hit_hard": (-18, 0.6, 1.0, [f"{MED}/Weapon Impacts/Mace Spear Haft.wav",
                                            f"{MED}/Weapon Impacts/Axe Spear Haft on Haft.wav",
                                            f"{MED}/Weapon Impacts/Mace Axe Blade and Haft.wav"]),
    # explosions: a crunch over a sub-bass boom
    "sfx/explosion": (-9, 2.0, 1.0, [[(f"{SCI}/explosionCrunch_00{i}.ogg", 0.0, 0),
                                      (f"{SCI}/lowFrequency_explosion_00{i % 2}.ogg", 0.0, 2)] for i in range(4)]),
    # doors
    # water (world.Splash). Freesound HQ PREVIEWS (CC0, checked on each sound's page 2026-10-08) -- placeholders until
    # the originals are downloaded (needs a login); swap the path, the rows stay.
    "sfx/splash": (-20, 1.4, 1.0, [f"{FS}/water_jump_mono_nox_sound_585744.mp3",
                                   f"{FS}/water_jump_mono_nox_sound_585744.mp3@5.15",
                                   f"{FS}/water_jump_mono_nox_sound_585744.mp3@9.70"]),
    "sfx/splash_small": (-24, 0.4, 1.0, [f"{FS}/small_puddle_splash_robo9418_841834.mp3"]),
    "sfx/swim_stroke": (-27, 0.8, 1.0, [f"{FS}/person_swimming_craigsmith_438845.mp3@{t}"
                                        for t in (3.75, 8.90, 18.05, 22.10)]),   # not 0.40: a voice (155 Hz + harmonics) at 0.54-0.80 s
    "sfx/door_open": (-25, 1.0, 1.0, [f"{RPG}/doorOpen_1.ogg", f"{RPG}/doorOpen_2.ogg"]),
    "sfx/door_close": (-23, 1.0, 1.0, [f"{RPG}/doorClose_{i}.ogg" for i in range(1, 5)]),
    "sfx/door_slide": (-22,   # a 0.29 s take: the 400 ms window under-reads it, so +3 dB to sit at door_open's level
                        0.8, 0.85, k5(f"{SCI}/doorOpen", 3)),
    # weapons
    "sfx/dry_fire": (-26, 0.25, 1.0, [f"{RAW}/Walther PPQ/X_18.wav", f"{RAW}/Tikka/W_13.wav",
                                      f"{RAW}/Ruger 10.22/Q_13.wav"]),
    "sfx/weapon_draw": (-27, 0.45, 1.0, [f"{RAW}/Tikka/W_18.wav", f"{RAW}/Arisaka/E_11.wav",
                                         f"{RAW}/PPSh/P_3.wav"]),
    # UI (2D)
    "ui/click": (-26, 0.25, 1.0, [f"{K}/ui-audio/Audio/click{i}.ogg" for i in (1, 2, 3)]),
    "ui/back": (-26, 0.3, 1.0, [f"{UI}/back_001.ogg"]),
    "ui/confirm": (-24, 0.6, 1.0, [f"{UI}/confirmation_001.ogg"]),
    "ui/error": (-24, 0.5, 1.0, [f"{UI}/error_001.ogg"]),
    "ui/waypoint": (-24, 0.4, 1.0, [f"{UI}/select_001.ogg"]),
    # mission stingers (2D)
    "ui/mission_start": (-20, 2.0, 1.0, [f"{JIN}/jingles_STEEL00.ogg"]),
    "ui/mission_complete": (-19, 2.0, 1.0, [f"{JIN}/jingles_STEEL07.ogg"]),
    "ui/mission_fail": (-20, 2.0, 1.0, [f"{JIN}/jingles_STEEL09.ogg"]),
}


def whole(x, max_len):
    """The whole file from its onset (UI sounds and jingles are already one clean event; cut() would split a
    click at its first micro-gap), at most max_len, with a short fade."""
    on = np.flatnonzero(np.abs(x) > 0.02 * (np.abs(x).max() or 1))
    seg = x[max(0, (on[0] if len(on) else 0) - int(0.002 * SR)):][: int(max_len * SR)].copy()
    fade = min(len(seg) // 4, int(0.02 * SR))
    if fade:
        seg[-fade:] *= np.linspace(1, 0, fade)
    return seg / (np.abs(seg).max() or 1)


def one(src, variant, max_len, pitch, name=""):
    if isinstance(variant, str) and "@" in variant:
        # "path@seconds": a window of max_len cut from a long take at that time (a swim stroke in a 42 s recording)
        path, at = variant.rsplit("@", 1)
        x = load(os.path.join(src, path), pitch)
        s = int(float(at) * SR)
        seg = x[s:s + int(max_len * SR)].copy()
        fi, fo = min(len(seg) // 4, int(0.01 * SR)), min(len(seg) // 3, int(0.12 * SR))
        if fi: seg[:fi] *= np.linspace(0, 1, fi)
        if fo: seg[-fo:] *= np.linspace(1, 0, fo)
        return seg / (np.abs(seg).max() or 1)
    if isinstance(variant, str):
        x = load(os.path.join(src, variant), pitch)
        return whole(x, max_len) if name.startswith("ui/") else cut(x, max_len, fixed=True)
    x = np.zeros(int(max_len * SR))
    for path, at, gain in variant:
        seg = cut(load(os.path.join(src, path), pitch), max_len, fixed=True) * 10 ** (gain / 20)
        s = int(at * SR); e = min(len(x), s + len(seg))
        x[s:e] += seg[:e - s]
    return x[: max(np.flatnonzero(np.abs(x) > 1e-4).max(initial=0) + 1, int(0.05 * SR))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/data/danilko/game_assets/audio")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    only = set(filter(None, a.only.split(",")))
    print(f"{'file':<34}{'sec':>6}{'LUFS(Mmax)':>11}{'peak dBFS':>11}")
    for name, (target, max_len, pitch, variants) in SPECS.items():
        if only and os.path.basename(name) not in only and name not in only:
            continue
        os.makedirs(os.path.dirname(os.path.join(OUT, name)), exist_ok=True)
        for i, v in enumerate(variants, 1):
            x = normalise(one(a.src, v, max_len, pitch, name), target)
            dest = os.path.join(OUT, f"{name}_{i}.wav" if len(variants) > 1 else f"{name}.wav")
            write_wav(dest, x)
            print(f"{os.path.relpath(dest, OUT):<34}{len(x) / SR:6.2f}{loudness(x):11.1f}"
                  f"{20 * np.log10(np.abs(x).max() or 1e-9):11.1f}")


if __name__ == "__main__":
    main()
