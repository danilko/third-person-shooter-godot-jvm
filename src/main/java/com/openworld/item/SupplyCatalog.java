package com.openworld.item;

import com.openworld.util.DataReader;

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

    private SupplyCatalog() {}

    public static Map<String, Supply> parse(String json) { return read(DataReader.of(json)); }

    public static Map<String, Supply> read(DataReader doc) {
        Map<String, Supply> out = new LinkedHashMap<>();
        for (Map.Entry<String, DataReader> e : doc.rows("supplies").entrySet()) {
            DataReader r = e.getValue();
            out.put(e.getKey(), new Supply(e.getKey(), r.str("name", e.getKey()), r.str("kind", "food"),
                    (float) r.reqNum("heal", 0.0), r.integer("max", 3)));
        }
        return out;
    }

    public static Map<String, Supply> load() { return com.openworld.game.data.Tables.SUPPLIES.get(); }

    public static Supply find(String id) { return load().get(id); }
}
