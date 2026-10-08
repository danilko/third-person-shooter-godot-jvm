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
    /** The local player's damage was confirmed (HitMarker). 2D. */
    HIT_MARKER("hit_marker"),
    /** An emergency vehicle on a call (Vehicle.refreshEmergency): a LOOPING Japanese siren (police: the wailing
     *  ウーウー; an ambulance's ピーポー can be a second file later). 3D, on the car. */
    SIREN("siren"),

    // a bullet meeting a surface (ImpactManager, by SurfaceType)
    IMPACT_FLESH("sfx/impact_flesh", 5),
    IMPACT_METAL("sfx/impact_metal", 5),
    IMPACT_STONE("sfx/impact_stone", 5),
    IMPACT_WOOD("sfx/impact_wood", 5),
    IMPACT_GLASS("sfx/impact_glass", 5),

    // water (world.Splash): a body or a car entering, a swim stroke, a wading step or a bullet into the water
    SPLASH("sfx/splash", 3),
    SPLASH_SMALL("sfx/splash_small"),
    SWIM_STROKE("sfx/swim_stroke", 4),

    // a melee blow landing (MeleeItem): on a body, on anything else
    MELEE_HIT_FLESH("sfx/melee_hit_flesh", 5),
    MELEE_HIT_HARD("sfx/melee_hit_hard", 3),

    /** Every explosion (ExplosionManager.playBlast). 3D, heard far. */
    EXPLOSION("sfx/explosion", 4),

    // doors (world.Door): a hinged leaf opening / shutting, an automatic sliding door
    DOOR_OPEN("sfx/door_open", 2),
    DOOR_CLOSE("sfx/door_close", 4),
    DOOR_SLIDE("sfx/door_slide", 3),

    // weapons (WeaponController): the trigger on an empty gun, raising a weapon
    DRY_FIRE("sfx/dry_fire", 3),
    WEAPON_DRAW("sfx/weapon_draw", 3),

    // UI (2D)
    UI_CLICK("ui/click", 3),
    UI_BACK("ui/back"),
    UI_CONFIRM("ui/confirm"),
    UI_ERROR("ui/error"),
    UI_WAYPOINT("ui/waypoint"),
    MISSION_START("ui/mission_start"),
    MISSION_COMPLETE("ui/mission_complete"),
    MISSION_FAIL("ui/mission_fail");

    /** File extensions tried in order (engine-free, so a unit test can read it). */
    public static final String[] EXTENSIONS = {".ogg", ".wav"};

    /** The file's path under {@code assets/audio/}, without extension (and without the variant suffix). */
    public final String file;
    /** How many takes: 1 = {@code <file>.ext}; N = {@code <file>_1.ext} .. {@code <file>_N.ext}, one picked per play. */
    public final int variants;

    Sound(String file) { this(file, 1); }
    Sound(String file, int variants) { this.file = file; this.variants = variants; }

    /** The file name (no extension) of take {@code i} (1-based). */
    public String variantFile(int i) { return variants <= 1 ? file : file + "_" + i; }
}
