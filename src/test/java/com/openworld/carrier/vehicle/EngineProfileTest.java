package com.openworld.carrier.vehicle;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** EngineProfile: the names, the folders, the gearing, and every config naming a profile that exists. */
class EngineProfileTest {

    @Test
    void blankOrUnknownIsTheCar() {
        assertEquals("car", EngineProfile.of("").id());
        assertEquals("car", EngineProfile.of(null).id());
        assertEquals("car", EngineProfile.of("jet_turbine").id());
        assertEquals("scooter", EngineProfile.of(" scooter ").id());
    }

    @Test
    void stemsPointIntoTheProfilesFolder() {
        assertEquals("engine/low", EngineProfile.of("car").stem("low"));
        assertEquals("engine/sport/start", EngineProfile.of("sport").stem("start"));
    }

    @Test
    void theCarsGearingIsUnchanged() {
        // the numbers EngineAudio had before profiles: standing on the throttle 0.3, the top of first gear 0.95,
        // just past the change 0.42
        EngineProfile car = EngineProfile.of("car");
        assertEquals(0.3, car.targetRpm(0.0, 1.0), 1e-9);
        assertEquals(0.95, car.targetRpm(0.20, 0.0), 1e-9);
        assertEquals(0.42, car.targetRpm(0.2000001, 0.0), 1e-3);
    }

    @Test
    void aScooterNeverDropsItsRevs() {
        EngineProfile cvt = EngineProfile.of("scooter");
        double last = -1;
        for (int i = 0; i <= 100; i++) {
            double r = cvt.targetRpm(i / 100.0, 1.0);
            assertTrue(r >= last - 1e-9, "a CVT's revs fell at " + i + "%");
            last = r;
        }
        assertTrue(cvt.targetRpm(0.0, 1.0) >= 0.5, "the belt slips: the revs rise as the throttle opens");
    }

    @Test
    void pitchesAreOrderedLikeTheEngines() {
        assertTrue(EngineProfile.of("truck").fallbackPitch() < EngineProfile.of("car").fallbackPitch());
        assertTrue(EngineProfile.of("car").fallbackPitch() < EngineProfile.of("kei").fallbackPitch());
        assertTrue(EngineProfile.of("bike_big").fallbackPitch() < EngineProfile.of("sport").fallbackPitch());
    }

    /** Every generated config that names an engine names one that exists (a typo would silently be the car). */
    @Test
    void everyConfigNamesARealProfile() throws Exception {
        Pattern p = Pattern.compile("engine_sound = \"([^\"]*)\"");
        int named = 0;
        try (var files = Files.list(Path.of("src/main/resources/com/openworld/vehicle"))) {
            for (Path f : (Iterable<Path>) files.filter(x -> x.toString().endsWith("Config.tres"))::iterator) {
                Matcher m = p.matcher(Files.readString(f));
                if (!m.find()) continue;
                named++;
                assertTrue(EngineProfile.ALL.containsKey(m.group(1)), f + " names engine '" + m.group(1) + "'");
            }
        }
        assertTrue(named >= 5, "the bikes at least name their engines (" + named + ")");
    }
}
