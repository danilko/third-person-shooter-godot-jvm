package com.openworld.world;

import com.openworld.util.MiniJson;
import godot.api.FileAccess;
import godot.api.FontFile;
import godot.api.ResourceLoader;
import godot.global.GD;

import java.util.HashMap;
import java.util.Map;

/**
 * Every road's REAL street name (user, 2026-09-26: "update street with real street name"), written by
 * {@code tools/island_street_names.py} into {@link #PATH}: a road's BASE name (its record name without the
 * {@code __n} zone / joint suffixes, so every piece of one street carries one name) -> its name in kanji and in
 * romaji. Read by the signal name plates ({@link TrafficSignals}) and the minimap's street line.
 *
 * <p>{@link #font()} is the font that can draw them: a subset of Noto Sans CJK JP (SIL OFL 1.1) holding only the
 * characters the names use, {@code tools/make_jp_font.py}.
 */
public final class StreetNames {

    public static final String PATH = "res://src/main/resources/com/openworld/world/IslandStreetNames.json";
    public static final String FONT = "res://src/main/resources/com/openworld/ui/fonts/NotoSansJP-Signs.otf";

    /** {ja, en} */
    private static Map<String, String[]> names;
    private static FontFile font;

    private StreetNames() {}

    /** A road's base name: `chuo_dori__3__x1` -> `chuo_dori`. */
    public static String base(String road) {
        if (road == null) return "";
        int k = road.indexOf("__");
        return k < 0 ? road : road.substring(0, k);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, String[]> table() {
        if (names != null) return names;
        names = new HashMap<>();
        if (!FileAccess.fileExists(PATH)) return names;
        try {
            Map<String, Object> doc = (Map<String, Object>) MiniJson.parse(FileAccess.getFileAsString(PATH));
            Map<String, Object> roads = (Map<String, Object>) doc.get("roads");
            for (Map.Entry<String, Object> e : roads.entrySet()) {
                Map<String, Object> v = (Map<String, Object>) e.getValue();
                names.put(e.getKey(), new String[]{String.valueOf(v.get("ja")), String.valueOf(v.get("en"))});
            }
        } catch (IllegalArgumentException | ClassCastException e) {
            GD.printErr("StreetNames: " + PATH + ": " + e.getMessage());
        }
        return names;
    }

    /** The kanji name of `road` (any piece of it), or null when it has none. */
    public static String ja(String road) {
        String[] n = table().get(base(road));
        return n == null ? null : n[0];
    }

    /** The romaji name of `road`, or null. */
    public static String en(String road) {
        String[] n = table().get(base(road));
        return n == null ? null : n[1];
    }

    /** The Japanese sign font, or null when the subset is not built. */
    public static FontFile font() {
        if (font == null && ResourceLoader.INSTANCE.exists(FONT))
            font = (FontFile) ResourceLoader.INSTANCE.load(FONT);
        return font;
    }
}
