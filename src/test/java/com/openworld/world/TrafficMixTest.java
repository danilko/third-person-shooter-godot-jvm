package com.openworld.world;

import com.openworld.carrier.vehicle.VehicleModels;
import com.openworld.util.DataReader;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TrafficMixTest {

    private static TrafficMix shipped() throws Exception {
        return TrafficMix.parse(Files.readString(Path.of("src/main/resources/com/openworld/game/traffic.json")));
    }

    private static Map<String, Integer> draw(TrafficMix m, String region) {
        Map<String, Integer> n = new HashMap<>();
        for (int i = 0; i < 1000; i++) n.merge(m.pick(region, (i + 0.5) / 1000.0), 1, Integer::sum);
        return n;
    }

    private static int trucks(Map<String, Integer> n) {
        int t = 0;
        for (String id : List.of("BOT1", "CRT1", "POT1", "COT1", "KET1")) t += n.getOrDefault(id, 0);
        return t;
    }

    /** The user's ask, as numbers: industry mostly trucks, the farm mostly kei trucks, downtown mostly cars. */
    @Test
    void eachDistrictDrawsItsOwnStreet() throws Exception {
        TrafficMix m = shipped();
        assertTrue(trucks(draw(m, "industry")) > 700, "industry: " + draw(m, "industry"));
        assertTrue(trucks(draw(m, "harbour")) > 700, "harbour: " + draw(m, "harbour"));
        Map<String, Integer> farm = draw(m, "farm");
        assertTrue(farm.getOrDefault("KET1", 0) > 500 && farm.getOrDefault("KEC1", 0) > 200, "farm: " + farm);
        Map<String, Integer> downtown = draw(m, "downtown_core");
        assertTrue(trucks(downtown) < 200 && trucks(downtown) > 0, "downtown: " + downtown);
        assertTrue(draw(m, "nightlife").getOrDefault("TAX1", 0) > 300, "nightlife is taxis");
    }

    @Test
    void aRegionTakesTheRowOfItsLongestPrefix() throws Exception {
        TrafficMix m = shipped();
        assertEquals(m.regions.get("residential"), m.rowOf("residential_north"));
        assertEquals(m.regions.get("light_industry"), m.rowOf("light_industry_w"));
        assertEquals(m.regions.get("downtown"), m.rowOf("downtown_core"));
        assertEquals(m.regions.get("west_"), m.rowOf("west_centre"));
        assertEquals(m.fallback, m.rowOf(""));
        assertEquals(m.fallback, m.rowOf("the_sea"));
        assertEquals(0.6, m.scale("farm"));
        assertEquals(1.0, m.scale("downtown"));
    }

    @Test
    void theRollWalksTheWeights() {
        TrafficMix m = TrafficMix.parse("{\"default\":{\"mix\":{\"A\":1,\"B\":3}},\"regions\":{}}");
        assertEquals("A", m.pick("x", 0.0));
        assertEquals("A", m.pick("x", 0.249));
        assertEquals("B", m.pick("x", 0.251));
        assertEquals("B", m.pick("x", 1.0));
        assertEquals(0.75, m.fallback.share("B"));
    }

    /** Every id in the shipped table is a vehicle the game has, and every weight is positive. */
    @Test
    void theShippedTableNamesOnlyRealVehicles() throws Exception {
        DataReader d = DataReader.of(Files.readString(Path.of("src/main/resources/com/openworld/game/traffic.json")));
        TrafficMix.read(d, id -> VehicleModels.sceneOfId(id) != null);
        assertEquals(List.of(), d.finish());
    }

    @Test
    void anUnknownModelOrABadWeightIsAProblem() {
        DataReader d = DataReader.of("{\"default\":{\"mix\":{\"KEC1\":1,\"NOPE\":2,\"SPC1\":0}},\"regions\":{\"x\":{\"scale\":1}}}");
        TrafficMix m = TrafficMix.read(d, id -> VehicleModels.sceneOfId(id) != null);
        assertEquals(List.of("default.mix.NOPE: not a vehicle model", "default.mix.SPC1: a weight must be positive",
                "regions.x.mix: missing"), d.finish());
        assertEquals("KEC1", m.pick("x", 0.9), "a region with no usable mix draws the default");
    }
}
