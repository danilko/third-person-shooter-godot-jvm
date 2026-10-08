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
}
