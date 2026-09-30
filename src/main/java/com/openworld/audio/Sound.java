package com.openworld.audio;

/**
 * Every non-weapon sound the game plays, by name. The file is {@code res://assets/audio/<file>.ogg} (or {@code .wav});
 * a missing file is silence, reported once. No sound is generated in code: a new sound is a file dropped into
 * {@code assets/audio/} under the name listed here. {@code assets/audio/README.md} is the list of what exists and
 * what is still missing; {@code SoundTest} checks the two agree.
 *
 * <p>Weapon fire/reload sounds are not here: each weapon names its own files in its scene ({@code fire_audio},
 * {@code reload_audio}).
 */
public enum Sound {
    /** A car window shattering (a crash, a bullet, a blast, a melee blow). 3D, at the pane. */
    GLASS_SHATTER("glass_shatter"),
    /** The local player's damage was confirmed (HitMarker). 2D. */
    HIT_MARKER("hit_marker");

    /** File extensions tried in order (engine-free, so a unit test can read it). */
    public static final String[] EXTENSIONS = {".ogg", ".wav"};

    /** The file's name in {@code assets/audio/}, without extension. */
    public final String file;

    Sound(String file) { this.file = file; }
}
