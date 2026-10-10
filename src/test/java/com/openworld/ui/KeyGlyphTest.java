package com.openworld.ui;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class KeyGlyphTest {
    @Test
    void readsEveryPromptSpelling() {
        assertEquals(new KeyGlyph.Prompt("F", "Enter vehicle"), KeyGlyph.parse("[ F ]  Enter vehicle"));
        assertEquals(new KeyGlyph.Prompt("E", "pay"), KeyGlyph.parse("[E] pay"));
        assertEquals(new KeyGlyph.Prompt("E", "Door"), KeyGlyph.parse("Door (E)"));
        assertEquals(new KeyGlyph.Prompt("E", "RESTOCK AMMO x3"), KeyGlyph.parse("RESTOCK AMMO x3 (E)"));
        assertEquals(new KeyGlyph.Prompt("E", "Locked"), KeyGlyph.parse("Locked"));
        assertEquals(new KeyGlyph.Prompt("E", "Konbini (open 24h)"), KeyGlyph.parse("Konbini (open 24h)"));
    }

    @Test
    void padPromptsFollowTheBindingTable() {
        assertEquals("res://assets/ui/prompts/steamdeck_dpad_right.png", KeyGlyph.texturePath("E", true));
        assertEquals("res://assets/ui/prompts/steamdeck_button_y.png", KeyGlyph.texturePath("F", true));
        assertEquals("res://assets/ui/prompts/keyboard_q.png", KeyGlyph.texturePath("Q", true));   // no pad twin
        assertEquals("res://assets/ui/prompts/keyboard_e.png", KeyGlyph.texturePath("E", false));
    }
}
