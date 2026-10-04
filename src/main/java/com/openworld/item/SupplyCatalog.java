package com.openworld.item;

import com.openworld.util.MiniJson;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * The healing supplies table ({@code item/supplies.json}): food, medical and "strange" medical items a shop counter
 * sells and a character carries and uses. Engine-free parsing and the "which one do I use" rule, so they are
 * unit-tested ({@code SupplyCatalogTest}); {@link #load()} reads the shipped file through Godot.
 */
public final class SupplyCatalog {

    public static final String PATH = "res://src/main/resources/com/openworld/item/supplies.json";

    public record Supply(String id, String name, String kind, float heal, int max) {}

    private static Map<String, Supply> rows;

    private SupplyCatalog() {}

    @SuppressWarnings("unchecked")
    public static Map<String, Supply> parse(String json) {
        Map<String, Supply> out = new LinkedHashMap<>();
        Map<String, Object> doc = (Map<String, Object>) MiniJson.parse(json);
        Map<String, Object> list = (Map<String, Object>) doc.get("supplies");
        for (Map.Entry<String, Object> e : list.entrySet()) {
            Map<String, Object> r = (Map<String, Object>) e.getValue();
            out.put(e.getKey(), new Supply(e.getKey(), String.valueOf(r.getOrDefault("name", e.getKey())),
                    String.valueOf(r.getOrDefault("kind", "food")), ((Number) r.get("heal")).floatValue(),
                    ((Number) r.getOrDefault("max", 3)).intValue()));
        }
        return out;
    }

    public static synchronized Map<String, Supply> load() {
        if (rows != null) return rows;
        rows = godot.api.FileAccess.fileExists(PATH)
                ? parse(godot.api.FileAccess.getFileAsString(PATH)) : new LinkedHashMap<>();
        return rows;
    }

    public static Supply find(String id) { return load().get(id); }

    /**
     * Which carried supply to use for {@code missing} health: the smallest one that heals it all, else the
     * biggest (so a scratch does not waste a medical kit). Null when nothing is carried.
     */
    public static String best(Map<String, Integer> carried, Map<String, Supply> table, float missing) {
        String fit = null, big = null;
        for (Map.Entry<String, Integer> e : carried.entrySet()) {
            Supply s = table.get(e.getKey());
            if (s == null || e.getValue() <= 0) continue;
            if (s.heal() >= missing && (fit == null || s.heal() < table.get(fit).heal())) fit = s.id();
            if (big == null || s.heal() > table.get(big).heal()) big = s.id();
        }
        return fit != null ? fit : big;
    }
}
