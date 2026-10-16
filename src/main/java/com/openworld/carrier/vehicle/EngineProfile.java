package com.openworld.carrier.vehicle;

import java.util.List;
import java.util.Map;

/**
 * Which ENGINE a vehicle sounds like (user, 2026-10-16: "add sound as different engine sound options, so it can be
 * replaced later if needed, or GTA-like use the same sound"). A vehicle names a profile in
 * {@link VehicleConfig#engineSound} ("" = {@link #CAR}); {@link EngineAudio} plays it.
 *
 * <p><b>Replacing a sound is dropping files in a folder.</b> A profile's loops live in
 * {@code assets/audio/engine/<folder>/} as {@code idle / low / mid / high / start} (.wav or .ogg), cut to the SAME
 * steady firing frequencies as the car's ({@link EngineAudio#BAND_HZ}: run them through
 * {@code tools/audio/build_engine.py}). A band whose file is missing falls back to the shared car take, played at
 * {@link #fallbackPitch} -- that is the GTA way (one recording, pitched per class), and it is what every profile but
 * {@code car} does today. A profile's own file always plays at pitch 1 relative to the band.
 *
 * <p>The GEARING is the profile's too: a scooter's CVT is one long gear (the revs rise with the speed and never drop),
 * a Cub has four, a sport bike six close ones; a truck lugs low. Engine-free ({@code EngineProfileTest}).
 *
 * @param id            the name a VehicleConfig uses
 * @param folder        under {@code assets/audio/engine/} ("" = the car's own files, the root)
 * @param fallbackPitch the car take's pitch when this profile has no file for a band (1 = the car)
 * @param gearTops      each gear's top as a share of top speed (the last one past 1 = it never changes up)
 * @param levelDb       loudness against the car
 */
public record EngineProfile(String id, String folder, double fallbackPitch, double[] gearTops, float levelDb) {

    public static final String CAR = "car";

    /** The profiles, MY PICKS (2026-10-16, unheard): pitches from the classes' firing rates, gears from their boxes. */
    public static final Map<String, EngineProfile> ALL = Map.of(
            CAR, new EngineProfile(CAR, "", 1.0, new double[] {0.20, 0.38, 0.58, 0.80, 1.25}, 0f),
            "kei", new EngineProfile("kei", "kei", 1.18, new double[] {0.22, 0.42, 0.65, 0.88, 1.25}, -2f),
            "truck", new EngineProfile("truck", "truck", 0.72, new double[] {0.12, 0.25, 0.40, 0.58, 0.78, 1.25}, 2f),
            // 原付 / 125 scooter: a CVT -- one gear, the revs climb with the speed; a buzzy single
            "scooter", new EngineProfile("scooter", "scooter", 1.45, new double[] {1.25}, -5f),
            // Cub / trail single: four short gears
            "bike_small", new EngineProfile("bike_small", "bike_small", 1.32, new double[] {0.18, 0.36, 0.60, 1.25}, -3f),
            // 白バイ class big four: five gears, deeper than the sport bike
            "bike_big", new EngineProfile("bike_big", "bike_big", 1.12, new double[] {0.16, 0.32, 0.50, 0.72, 1.25}, 0f),
            // supersport four: six close gears, high-revving
            "sport", new EngineProfile("sport", "sport", 1.52, new double[] {0.13, 0.25, 0.38, 0.52, 0.70, 1.25}, 1f));

    /** The profile of a config's {@code engineSound}; unknown or blank = the car. */
    public static EngineProfile of(String id) {
        if (id == null || id.isBlank()) return ALL.get(CAR);
        EngineProfile p = ALL.get(id.trim());
        return p != null ? p : ALL.get(CAR);
    }

    /** Every profile name, sorted (the console, probes). */
    public static List<String> ids() { return ALL.keySet().stream().sorted().toList(); }

    /** The file stem of a band for this profile ("engine/scooter/low"), or the car's ("engine/low"). */
    public String stem(String band) { return folder.isEmpty() ? "engine/" + band : "engine/" + folder + "/" + band; }

    /**
     * Engine speed 0..1 for a road speed (as a share of top speed) and a throttle: climbs through each gear to 0.95,
     * drops to 0.42 at a change, held up by the throttle when standing. One gear (a CVT) climbs 0.3 -> 0.95 with no drop.
     */
    public double targetRpm(double speedShare, double throttle) {
        double lo = 0.0;
        for (int g = 0; g < gearTops.length; g++) {
            if (speedShare <= gearTops[g] || g == gearTops.length - 1) {
                double f = Math.max(0.0, Math.min(1.0, (speedShare - lo) / (gearTops[g] - lo)));
                // a CVT holds the revs up the moment the throttle opens (the belt slips), then rises with the speed
                if (gearTops.length == 1) return Math.max(0.3 * throttle + (0.95 - 0.3 * throttle) * f, throttle * 0.55);
                double bottom = g == 0 ? 0.0 : 0.42;
                return Math.max(bottom + (0.95 - bottom) * f, g == 0 ? throttle * 0.3 : 0.0);
            }
            lo = gearTops[g];
        }
        return 0.0;
    }
}
