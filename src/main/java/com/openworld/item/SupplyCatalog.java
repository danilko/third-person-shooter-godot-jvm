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
}
