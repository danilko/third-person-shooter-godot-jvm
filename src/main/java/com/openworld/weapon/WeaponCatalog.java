package com.openworld.weapon;

import godot.api.FileAccess;
import godot.api.JSON;
import godot.api.PackedScene;
import godot.core.Dictionary;
import godot.core.VariantArray;
import godot.global.GD;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * THE weapon list at runtime: {@code weapon/weapon_catalog.json} (PLAN.md 2.8 item 7), read once. What the
 * debug tools offer — the console's {@code weapons}/{@code give}/{@code drop}, the aim bench's weapon cycle — comes
 * from here, so a weapon added to the catalog is spawnable everywhere with no other edit. {@code WeaponCatalogTest}
 * holds the file itself together (every row has a scene, every weapon scene has a row).
 */
public final class WeaponCatalog {
    private WeaponCatalog() {}

    public static final String PATH = "res://src/main/resources/com/openworld/weapon/weapon_catalog.json";

    /** One catalog row. */
    public record Row(String id, String scene, String archetype, boolean bench) {}

    private static Map<String, Row> rows;

    /** Every row, in catalog order. */
    public static synchronized Map<String, Row> rows() {
        if (rows != null) return rows;
        rows = new LinkedHashMap<>();
        if (FileAccess.fileExists(PATH)
                && JSON.parseString(FileAccess.getFileAsString(PATH)) instanceof Dictionary<?, ?> d
                && d.get("weapons") instanceof VariantArray<?> list) {
            for (Object o : list) {
                if (o instanceof Dictionary<?, ?> r && r.get("id") instanceof String id && r.get("scene") instanceof String scene) {
                    rows.put(id, new Row(id, scene, r.get("archetype") instanceof String arch ? arch : "",
                            Boolean.TRUE.equals(r.get("bench"))));
                }
            }
        }
        return rows;
    }

    public static List<String> ids() { return new ArrayList<>(rows().keySet()); }

    /**
     * The weapons a debug tool may hand out or drop: every row but the built-in fist, which every character is
     * born with in slot 0 and which has no world body (it would fall through the floor).
     */
    public static List<String> spawnableIds() {
        List<String> out = new ArrayList<>();
        for (Row r : rows().values()) if (!"fist".equals(r.archetype())) out.add(r.id());
        return out;
    }

    public static List<String> benchIds() {
        List<String> out = new ArrayList<>();
        for (Row r : rows().values()) if (r.bench()) out.add(r.id());
        return out;
    }

    /** A spawnable catalog id, case-insensitive ("snr1" finds SNR1); null if there is none. */
    public static String find(String id) {
        for (String k : spawnableIds()) if (k.equalsIgnoreCase(id)) return k;
        return null;
    }

    /** A fresh, un-parented instance of weapon {@code id}; null if it has no loadable scene. */
    public static WeaponItem instantiate(String id) {
        Row r = rows().get(id);
        if (r == null) return null;
        if (!(GD.INSTANCE.load(r.scene()) instanceof PackedScene ps) || !(ps.instantiate() instanceof WeaponItem item)) {
            GD.INSTANCE.printErr("WeaponCatalog: " + r.scene() + " is not a WeaponItem scene");
            return null;
        }
        return item;
    }
}
