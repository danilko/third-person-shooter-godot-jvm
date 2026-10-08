package com.openworld.character;

import com.openworld.util.MiniJson;

import java.util.HashMap;
import java.util.Map;

/** The engine-free half of {@link Outfits} (unit-tested in DispatchRulesTest): which part a material dresses and
 *  what an outfit puts on it. */
public final class OutfitTable {

    private OutfitTable() {}

    /** The part a material name dresses ("Tops", "Bottoms", ...; "cloth" for an unknown one), or null = not cloth. */
    public static String partOf(String materialName) {
        if (materialName == null || !materialName.endsWith("_CLOTH")) return null;
        String[] bits = materialName.split("_");
        // <body>_<nnn>_<nn>_<Part>_<nn>_CLOTH: the part is the word before the trailing number
        return bits.length >= 3 ? bits[bits.length - 3] : "cloth";
    }

    /** Parse the table's text: outfit -> part -> colour list or material path. */
    @SuppressWarnings("unchecked")
    public static Map<String, Map<String, Object>> parse(String json) {
        Map<String, Map<String, Object>> out = new HashMap<>();
        if (!(MiniJson.parse(json) instanceof Map<?, ?> doc) || !(doc.get("outfits") instanceof Map<?, ?> o)) return out;
        for (var e : ((Map<String, Object>) o).entrySet())
            if (e.getValue() instanceof Map<?, ?> parts) out.put(e.getKey(), (Map<String, Object>) parts);
        return out;
    }

    /** What an outfit puts on a part: a colour list, a material path, or null (the part keeps its own). */
    public static Object valueFor(Map<String, Object> outfit, String part) {
        if (outfit == null || part == null) return null;
        Object v = outfit.get(part);
        return v != null ? v : outfit.get("cloth");
    }

}
