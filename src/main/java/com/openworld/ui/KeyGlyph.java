package com.openworld.ui;

/**
 * A HUD prompt's key hint, read out of its text so a keycap glyph can be drawn instead of the letter
 * (Kenney Input Prompts, {@code assets/ui/prompts/keyboard_<key>.png}). Prompts reach the HUD as plain strings in
 * three spellings, all understood: {@code "[ F ]  Enter vehicle"}, {@code "[E] pay"} and {@code "Door (E)"}; a
 * prompt with no hint is the {@code interact} key, E. Engine-free ({@code KeyGlyphTest}).
 */
public final class KeyGlyph {
    private KeyGlyph() {}

    /** The key (one upper-case letter) and the prompt text without the hint. */
    public record Prompt(String key, String text) {}

    public static Prompt parse(String label) {
        String s = label == null ? "" : label.trim();
        java.util.regex.Matcher m = java.util.regex.Pattern.compile("^\\[\\s*([A-Za-z0-9])\\s*\\]\\s*(.*)$").matcher(s);
        if (m.matches()) return new Prompt(m.group(1).toUpperCase(), m.group(2).trim());
        m = java.util.regex.Pattern.compile("^(.*?)\\s*\\(\\s*([A-Za-z0-9])\\s*\\)\\s*$").matcher(s);
        if (m.matches()) return new Prompt(m.group(2).toUpperCase(), m.group(1).trim());
        return new Prompt("E", s);
    }

    /** The glyph's texture path for {@code key}; the caller falls back to the "[ X ]" text when it does not exist. */
    public static String texturePath(String key) {
        return "res://assets/ui/prompts/keyboard_" + key.toLowerCase() + ".png";
    }

    /**
     * The same prompt for a pad player (PLAN.md 1.1 / F1): the key's ACTION, then that action's pad input as laid out
     * by {@code tools/input/joypad_bindings.py} (Kenney's Steam Deck glyphs, {@code steamdeck_<name>.png}). Null when
     * the key has no pad twin -- the caller then shows the key as text.
     */
    public static String padGlyph(String key) {
        return switch (key == null ? "" : key.toUpperCase()) {
            case "E" -> "dpad_right";     // interact
            case "F" -> "button_y";       // use_carrier
            case "H" -> "dpad_left";      // holster
            case "R" -> "button_x";       // reload
            case "B" -> "button_r1";      // detonate
            case "G" -> "button_l1";      // radialmenu
            case "M" -> "dpad_up";        // map
            default -> null;
        };
    }

    /** The input action a prompt's DEFAULT letter stands for (the table padGlyph follows), or null. */
    public static String actionOf(String key) {
        return switch (key == null ? "" : key.toUpperCase()) {
            case "E" -> "interact";
            case "F" -> "use_carrier";
            case "H" -> "holster";
            case "R" -> "reload";
            case "B" -> "detonate";
            case "G" -> "radialmenu";
            case "M" -> "map";
            default -> null;
        };
    }

    public static String texturePath(String key, boolean pad) {
        if (!pad) return texturePath(key);
        String g = padGlyph(key);
        return g == null ? texturePath(key) : "res://assets/ui/prompts/steamdeck_" + g + ".png";
    }
}
