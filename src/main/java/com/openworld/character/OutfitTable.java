package com.openworld.character;

import com.openworld.util.DataReader;

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
    public static Map<String, Map<String, Object>> parse(String json) { return read(DataReader.of(json)); }

    /** An outfit's parts are free-form (the part names come from each body's material names), so they are not
     *  checked key by key; a value must be a colour list or a material path. */
    public static Map<String, Map<String, Object>> read(DataReader doc) {
        Map<String, Map<String, Object>> out = new HashMap<>();
        for (Map.Entry<String, DataReader> e : doc.rows("outfits").entrySet()) {
            Map<String, Object> parts = new HashMap<>();
            for (String part : e.getValue().keys()) parts.put(part, e.getValue().raw(part));
            out.put(e.getKey(), parts);
        }
        return out;
    }

    /** What an outfit puts on a part: a colour list, a material path, or null (the part keeps its own). */
    public static Object valueFor(Map<String, Object> outfit, String part) {
        if (outfit == null || part == null) return null;
        Object v = outfit.get(part);
        return v != null ? v : outfit.get("cloth");
    }

}
