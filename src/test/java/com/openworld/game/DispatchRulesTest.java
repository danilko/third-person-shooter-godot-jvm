package com.openworld.game;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class DispatchRulesTest {

    private static String read(String name) throws Exception {
        return Files.readString(Path.of("src/main/resources/com/openworld/game/" + name));
    }

    @Test
    void policeUnitsGrowWithStarsAndShootFromTheThreshold() throws Exception {
        DispatchRules r = DispatchRules.parse(read("crimes.json"), "dispatch");
        assertNotNull(r);
        assertEquals(0, r.footFor(0));
        assertEquals(0, r.carsFor(0));
        for (int s = 1; s < 5; s++) {
            assertTrue(r.footFor(s + 1) >= r.footFor(s), "foot units never shrink with stars");
            assertTrue(r.carsFor(s + 1) >= r.carsFor(s), "cars never shrink with stars");
        }
        assertTrue(r.footFor(1) > 0, "one star sends someone");
        assertTrue(r.shoots(1, false), "one star already hunts the player down (no arrest by proximity)");
        assertTrue(r.shoots(1, true), "lethal-wanted is shot at any stars");
        assertTrue(r.shoots(r.shootAt, false));
        assertEquals(r.footFor(5), r.footFor(9), "past the table the last row holds");
    }

    @Test
    void gangHuntersAlwaysShootAndOnlyFromChaseAt() throws Exception {
        DispatchRules g = DispatchRules.parse(read("gangs.json"), "hunters");
        assertNotNull(g);
        assertTrue(g.shoots(1, false));
        assertEquals(0, g.footFor(2), "below chase_at nobody hunts");
        assertTrue(g.footFor(3) > 0);
        assertFalse(g.weapons.isEmpty());
    }

    @Test
    void spawningFillsTheGapAFewAtATime() {
        assertEquals(2, DispatchRules.toSpawn(8, 0, 2));
        assertEquals(1, DispatchRules.toSpawn(8, 7, 2));
        assertEquals(0, DispatchRules.toSpawn(3, 5, 2));
    }

    @org.junit.jupiter.api.Test
    void policeEscalateWithTheStars() throws Exception {
        DispatchRules r = DispatchRules.parse(read("crimes.json"), "dispatch");
        org.junit.jupiter.api.Assertions.assertEquals(java.util.List.of("BAT1"), r.weaponsFor(1), "a baton at one star");
        org.junit.jupiter.api.Assertions.assertTrue(r.weaponsFor(2).contains("PIS1"), "firearms from two stars");
        org.junit.jupiter.api.Assertions.assertTrue(r.weaponsFor(5).contains("ATL1"), "rockets at the top");
        org.junit.jupiter.api.Assertions.assertTrue(r.vehiclesFor(5).contains("TNK1"), "a tank at 5 stars");
        org.junit.jupiter.api.Assertions.assertTrue(r.vehiclesFor(5).contains("LTK1"), "a light tank at 5 stars");
        org.junit.jupiter.api.Assertions.assertFalse(r.vehiclesFor(3).contains("ARV1"), "no armour at 3 stars");
        org.junit.jupiter.api.Assertions.assertFalse(r.rams(3));
        org.junit.jupiter.api.Assertions.assertTrue(r.rams(4));
        org.junit.jupiter.api.Assertions.assertEquals(0, r.snipersFor(3));
        org.junit.jupiter.api.Assertions.assertTrue(r.snipersFor(5) > 0);
        org.junit.jupiter.api.Assertions.assertTrue(r.helisFor(5) > 0);
        org.junit.jupiter.api.Assertions.assertTrue(r.hasGun("TNK1") && !r.hasGun("POC1"));
        // past the table's end the last row holds
        org.junit.jupiter.api.Assertions.assertEquals(r.vehiclesFor(5), r.vehiclesFor(9));
    }

    @org.junit.jupiter.api.Test
    void gangsEscalateToo() throws Exception {
        DispatchRules r = DispatchRules.parse(read("gangs.json"), "hunters");
        org.junit.jupiter.api.Assertions.assertTrue(r.rams(4));
        org.junit.jupiter.api.Assertions.assertTrue(r.vehiclesFor(5).isEmpty(), "gangs drive civilian cars");
    }

    @org.junit.jupiter.api.Test
    void attackTokensGoToTheNearestAndRotate() {
        double[] dist = {30, 10, 20, 5};
        double[] none = {-1, -1, -1, -1}, rest = {0, 0, 0, 0};
        boolean[] g = DispatchRules.tokenHolders(dist, none, rest, 2, 4.0);
        org.junit.jupiter.api.Assertions.assertArrayEquals(new boolean[] {false, true, false, true}, g, "the two nearest");
        // a holder keeps its token though someone is nearer; a resting unit is skipped
        double[] held = {1.0, -1, -1, -1}, rest2 = {0, 0, 0, 1.0};
        g = DispatchRules.tokenHolders(dist, held, rest2, 2, 4.0);
        org.junit.jupiter.api.Assertions.assertArrayEquals(new boolean[] {true, true, false, false}, g);
        // no limit: everyone attacks
        g = DispatchRules.tokenHolders(dist, none, rest, 0, 4.0);
        org.junit.jupiter.api.Assertions.assertArrayEquals(new boolean[] {true, true, true, true}, g);
    }

    @org.junit.jupiter.api.Test
    void tokensAndRegroupAreData() throws Exception {
        DispatchRules r = DispatchRules.parse(read("crimes.json"), "dispatch");
        org.junit.jupiter.api.Assertions.assertTrue(r.tokensFor(5) > r.tokensFor(1) && r.tokensFor(1) > 0);
        org.junit.jupiter.api.Assertions.assertTrue(r.regroupFor(2) > 0 && r.regroupFor(5) < r.regroupFor(2),
                "a shorter lull at the top: relief is already on its way");
        DispatchRules h = DispatchRules.parse(read("gangs.json"), "hunters");
        org.junit.jupiter.api.Assertions.assertTrue(h.tokensFor(5) > 0);
    }

    @Test
    void bodiesAreChosenPerForceAndStars() throws Exception {
        DispatchRules r = DispatchRules.parse(read("crimes.json"), "dispatch");
        assertFalse(r.bodies.isEmpty(), "police name their bodies");
        java.util.Set<String> low = new java.util.HashSet<>(), high = new java.util.HashSet<>();
        for (int i = 0; i < 100; i++) {
            low.add(DispatchRules.pickBody(r.bodies, 2, i / 100.0).outfit());
            high.add(DispatchRules.pickBody(r.bodies, 5, i / 100.0).outfit());
        }
        assertEquals(java.util.Set.of("police"), low, "below five stars ordinary uniforms");
        assertEquals(java.util.Set.of("special_force"), high, "special forces from five stars");
        assertEquals(java.util.List.of("MEW1"), DispatchRules.pickBody(r.bodies, 5, 0.5).extraWeapons(),
                "special forces carry a knife besides their firearm");
        assertTrue(DispatchRules.pickBody(r.bodies, 2, 0.5).extraWeapons().isEmpty(), "ordinary officers do not");
        assertEquals("fumiriya", DispatchRules.pickBody(r.bodies, 2, 0.0).body(), "weights in table order");
        var gangs = DispatchRules.parseGangBodies(read("gangs.json"));
        assertEquals("gang_a", DispatchRules.pickBody(gangs.get("gang_a"), 3, 0.5).outfit());
        assertEquals("gang_b", DispatchRules.pickBody(gangs.get("gang_b"), 3, 0.99).outfit());
        assertNull(DispatchRules.pickBody(java.util.List.of(), 3, 0.5), "no table = the scene's own body");
        assertEquals("Tops", com.openworld.character.OutfitTable.partOf("F00_001_01_Tops_01_CLOTH"));
        assertEquals("Onepice", com.openworld.character.OutfitTable.partOf("F00_002_01_Onepice_01_CLOTH"));
        assertNull(com.openworld.character.OutfitTable.partOf("F00_001_01_Body_00_SKIN"), "skin is never dressed");
        var outfits = com.openworld.character.OutfitTable.parse(Files.readString(
                Path.of("src/main/resources/com/openworld/character/outfits.json")));
        for (var b : r.bodies) assertTrue(outfits.containsKey(b.outfit()), b.outfit() + " is in outfits.json");
        for (var l : gangs.values()) for (var b : l) assertTrue(outfits.containsKey(b.outfit()), b.outfit());
        for (var b : r.bodies) assertTrue(Files.exists(Path.of("src/main/resources/com/openworld/character/CharacterVisuals_"
                + Character.toUpperCase(b.body().charAt(0)) + b.body().substring(1) + ".tscn")), b.body());
    }
}
