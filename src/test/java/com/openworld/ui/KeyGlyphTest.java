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
}
