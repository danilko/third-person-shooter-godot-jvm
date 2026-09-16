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
import java.awt.image.BufferedImage;
import javax.imageio.ImageIO;
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

    private static int iconSpec(String text, String key) {
        Matcher m = Pattern.compile("\"icon\"\\s*:\\s*\\{.*?\"" + key + "\"\\s*:\\s*(\\d+)", Pattern.DOTALL).matcher(text);
        assertTrue(m.find(), "icon." + key);
        return Integer.parseInt(m.group(1));
    }

    /** A weapon's declared length: weapon_models.json `length_m`, or a primitive's `size` z. 0 if unknown. */
    private static double declaredLength(String models, String id) {
        Matcher m = Pattern.compile("\"id\":\\s*\"" + id + "\",\\s*\"length_m\":\\s*([0-9.]+)").matcher(models);
        if (m.find()) return Double.parseDouble(m.group(1));
        Matcher p = Pattern.compile("\"" + id + "\":\\s*\\{\\s*\"size\":\\s*\\[[0-9.]+,\\s*[0-9.]+,\\s*([0-9.]+)\\]").matcher(models);
        return p.find() ? Double.parseDouble(p.group(1)) : 0;
    }

    /**
     * Every weapon with a model or a primitive has a generated icon (blender/tools/render_weapon_icons.py) that
     * its scene uses, at the catalog's frame size, white, centred, inside the padding, and at the catalog's
     * scale: with `scale` "uniform" each silhouette is as wide as its weapon's declared length x pixels_per_metre.
     */
    @Test
    void everyIconIsInTheFrameWhiteCentredAndFitted() throws IOException {
        String cat = Files.readString(CATALOG);
        int w = iconSpec(cat, "width"), h = iconSpec(cat, "height"), pad = iconSpec(cat, "padding");
        boolean uniform = cat.matches("(?s).*\"scale\"\\s*:\\s*\"uniform\".*");
        int ppm = uniform ? iconSpec(cat, "pixels_per_metre") : 0;
        String models = Files.readString(MODELS);
        for (Row r : catalog()) {
            boolean modelled = Files.exists(ROOT.resolve("assets/weapons/" + r.id() + ".blend"))
                    || declaredLength(models, r.id()) > 0;
            if (!modelled) continue;
            Path png = ROOT.resolve("assets/ui/weapons/" + r.id() + ".png");
            assertTrue(Files.exists(png), r.id() + ": no icon, run render_weapon_icons.py");
            assertTrue(Files.readString(ROOT.resolve(r.scene())).contains("path=\"res://assets/ui/weapons/" + r.id() + ".png\""),
                    r.id() + ": the scene does not use its generated icon");
            BufferedImage img = ImageIO.read(png.toFile());
            assertEquals(w, img.getWidth(), r.id() + " width");
            assertEquals(h, img.getHeight(), r.id() + " height");
            int minX = w, minY = h, maxX = -1, maxY = -1;
            for (int y = 0; y < h; y++) {
                for (int x = 0; x < w; x++) {
                    int argb = img.getRGB(x, y);
                    int a = argb >>> 24;
                    if (a < 128) continue;
                    assertEquals(0xFFFFFF, argb & 0xFFFFFF, r.id() + ": opaque pixel is not white at " + x + "," + y);
                    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
                    minY = Math.min(minY, y); maxY = Math.max(maxY, y);
                }
            }
            assertTrue(maxX >= 0, r.id() + ": empty icon");
            assertTrue(minX >= pad - 1 && minY >= pad - 1 && maxX <= w - pad && maxY <= h - pad, r.id() + ": content enters the padding");
            assertTrue(Math.abs((minX + maxX) - (w - 1)) <= 2 && Math.abs((minY + maxY) - (h - 1)) <= 2,
                    r.id() + ": not centred (" + minX + ".." + maxX + ", " + minY + ".." + maxY + ")");
            if (uniform) {
                // One scale for every weapon: the silhouette is as wide as the weapon is long at pixels_per_metre.
                double length = declaredLength(models, r.id());
                if (length > 0) {
                    int want = (int) Math.round(length * ppm);
                    assertTrue(Math.abs((maxX - minX + 1) - want) <= 3,
                            r.id() + ": " + (maxX - minX + 1) + " px wide, " + length + " m at " + ppm + " px/m is " + want);
                }
            } else {
                boolean fitsX = minX <= pad + 1 && maxX >= w - pad - 2;
                boolean fitsY = minY <= pad + 1 && maxY >= h - pad - 2;
                assertTrue(fitsX || fitsY, r.id() + ": not fitted to the frame");
            }
        }
    }

    /**
     * An id is a KEY (file names, catalog rows, the inventory manifest, stack merging) and stays plain — "AR4",
     * "PI52". The NAME a player reads is the id with a hyphen between the letters and the number — "AR-4",
     * "PI-52" — the way real designations are written (AK-47, M4A1-S) and the way CS keeps `weapon_ak47` apart
     * from its display string. Fist, which has no designation, is exempt.
     */
    @Test
    void idsArePlainAndDisplayNamesAreHyphenated() throws IOException {
        for (Row r : catalog()) {
            if (r.id().equals("Fist")) continue;
            String text = Files.readString(ROOT.resolve(r.scene()));
            Matcher id = Pattern.compile("\nweapon_id = \"([^\"]*)\"").matcher(text);
            Matcher name = Pattern.compile("\nweapon_name = \"([^\"]*)\"").matcher(text);
            assertTrue(id.find(), r.id() + ": no weapon_id");
            assertEquals(r.id(), id.group(1), r.scene() + ": weapon_id must equal the catalog id");
            assertTrue(r.id().matches("[A-Z]+[0-9]+"), r.id() + ": an id is letters then digits, no punctuation");
            assertTrue(name.find(), r.id() + ": no weapon_name");
            assertEquals(r.id().replaceFirst("^([A-Z]+)([0-9]+)$", "$1-$2"), name.group(1), r.id() + ": display name");
        }
    }
}
