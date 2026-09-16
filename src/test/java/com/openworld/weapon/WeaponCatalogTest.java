package com.openworld.weapon;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;

/**
 * Holds every weapon list to the ONE catalog (PLAN.md 2.8 items 7-8): the catalog's scenes exist and store
 * the archetype NAME the catalog says, no weapon scene is missing from it, GripArchetype mirrors
 * weapon_archetypes.json's append-only order, and weapon_models.json / the holds only name catalog weapons
 * and known archetypes. Plain text parsing — no JSON dependency and no engine.
 */
class WeaponCatalogTest {

    private static final Path ROOT = Path.of("").toAbsolutePath();
    private static final Path CATALOG = ROOT.resolve("src/main/resources/com/openworld/weapon/weapon_catalog.json");
    private static final Path ARCHETYPES = ROOT.resolve("blender/tools/weapon_archetypes.json");
    private static final Path MODELS = ROOT.resolve("blender/tools/weapon_models.json");
    private static final Path WEAPON_DIR = ROOT.resolve("src/main/resources/com/openworld/weapon");

    record Row(String id, String scene, String archetype) {}

    private static List<Row> catalog() throws IOException {
        String text = Files.readString(CATALOG);
        Matcher m = Pattern.compile("\\{\"id\": \"([^\"]+)\",\\s*\"scene\": \"res://([^\"]+)\",\\s*\"archetype\": \"([^\"]+)\"").matcher(text);
        List<Row> rows = new ArrayList<>();
        while (m.find()) rows.add(new Row(m.group(1), m.group(2), m.group(3)));
        return rows;
    }

    @Test
    void gripArchetypeMirrorsTheAppendOnlyTable() throws IOException {
        String text = Files.readString(ARCHETYPES);
        Matcher m = Pattern.compile("\"index\":\\s*(\\d+),\\s*\"name\":\\s*\"([^\"]+)\"").matcher(text);
        int n = 0;
        while (m.find()) {
            int index = Integer.parseInt(m.group(1));
            GripArchetype a = GripArchetype.fromKey(m.group(2));
            assertNotNull(a, "GripArchetype has no '" + m.group(2) + "'");
            assertEquals(index, a.index(), m.group(2));
            n++;
        }
        assertEquals(GripArchetype.values().length, n, "archetype count");
    }

    @Test
    void everyCatalogSceneExistsAndStoresItsArchetypeByName() throws IOException {
        List<Row> rows = catalog();
        assertTrue(rows.size() >= 10, "catalog rows " + rows.size());
        for (Row r : rows) {
            Path scene = ROOT.resolve(r.scene());
            assertTrue(Files.exists(scene), r.scene());
            assertNotNull(GripArchetype.fromKey(r.archetype()), r.id() + ": " + r.archetype());
            String text = Files.readString(scene);
            assertTrue(!text.contains("weapon_pose_index"), r.id() + " still stores a bare weapon_pose_index");
            Matcher m = Pattern.compile("weapon_archetype = \"([^\"]+)\"").matcher(text);
            String stored = m.find() ? m.group(1) : "pistol";   // the WeaponItem default
            if (r.id().equals("Fist")) continue;              // FistItem's constructor names it; the scene may too
            assertEquals(r.archetype(), stored, r.id());
        }
    }

    @Test
    void noWeaponSceneIsMissingFromTheCatalog() throws IOException {
        Set<String> listed = new HashSet<>();
        for (Row r : catalog()) listed.add(ROOT.resolve(r.scene()).normalize().toString());
        try (var files = Files.list(WEAPON_DIR)) {
            for (Path p : (Iterable<Path>) files::iterator) {
                String name = p.getFileName().toString();
                if (!name.endsWith(".tscn")) continue;
                String text = Files.readString(p);
                boolean isWeapon = text.contains("weapon_id = ") || text.contains("FistItem.java");
                if (isWeapon) assertTrue(listed.contains(p.normalize().toString()), name + " is not in weapon_catalog.json");
            }
        }
    }

    @Test
    void modelsAndHoldsNameOnlyCatalogWeaponsAndKnownArchetypes() throws IOException {
        Set<String> ids = new HashSet<>();
        for (Row r : catalog()) ids.add(r.id());
        Matcher m = Pattern.compile("\\{\\s*\"id\":\\s*\"([^\"]+)\"").matcher(Files.readString(MODELS));
        while (m.find()) assertTrue(ids.contains(m.group(1)), "weapon_models.json names " + m.group(1));
        String arch = Files.readString(ARCHETYPES);
        int holds = arch.indexOf("\"holds\"");
        Matcher h = Pattern.compile("\n    \"([a-z_]+)\": \\{").matcher(arch.substring(holds));
        while (h.find()) assertNotNull(GripArchetype.fromKey(h.group(1)), "holds row " + h.group(1));
        assertTrue(!arch.contains("weapon_assignments"), "weapon_assignments is derived from the catalog now");
    }
}
