package com.openworld.control;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class BindingTableTest {
    private static BindingTable defaults() {
        BindingTable t = new BindingTable();
        t.set("interact", "key:69");   // E
        t.set("reload", "key:82");     // R
        t.set("fire", "mouse:1");
        return t;
    }

    @Test
    void rebindToAFreeKeyMovesOnlyThatRow() {
        BindingTable t = defaults();
        List<BindingTable.Change> c = t.rebind("interact", "key:84");   // T
        assertEquals(List.of(new BindingTable.Change("interact", "key:69", "key:84")), c);
        assertEquals("key:84", t.keyOf("interact"));
        assertEquals("key:82", t.keyOf("reload"));
    }

    @Test
    void aTakenKeyIsSwappedNotDoubleBound() {
        BindingTable t = defaults();
        List<BindingTable.Change> c = t.rebind("interact", "key:82");   // R, held by reload
        assertEquals(2, c.size());
        assertEquals("key:82", t.keyOf("interact"));
        assertEquals("key:69", t.keyOf("reload"));
        assertEquals(new BindingTable.Change("reload", "key:82", "key:69"), c.get(1));
    }

    @Test
    void escAndTheSameKeyChangeNothing() {
        BindingTable t = defaults();
        assertTrue(t.rebind("interact", "key:4194305").isEmpty());
        assertTrue(t.rebind("interact", "key:69").isEmpty());
        assertTrue(t.rebind("nope", "key:70").isEmpty());
    }

    @Test
    void sharedKeysLiveInOneRow() {
        // W drives the body AND the car: one row, so a rebind can never split them
        BindingTable.Row fwd = BindingTable.row("forward");
        assertNotNull(fwd);
        assertTrue(fwd.actions().containsAll(List.of("forward", "throttle")));
        assertTrue(BindingTable.row("jump").actions().containsAll(List.of("jump", "handbrake", "drift", "upright")));
        Set<String> ids = new HashSet<>();
        for (BindingTable.Row r : BindingTable.ROWS) assertTrue(ids.add(r.id()), "duplicate row " + r.id());
    }

    @Test
    void labels() {
        assertEquals("RMB", BindingTable.label("mouse:2", k -> "x"));
        assertEquals("T", BindingTable.label("key:84", k -> k == 84 ? "T" : "?"));
    }

    @Test
    void thePadTableSwapsLikeTheKeyboardAndKeepsStartForPause() {
        BindingTable t = new BindingTable(BindingTable.PAD_ROWS);
        t.set("jump", "pad:0");
        t.set("fire", "trig:5");
        t.set("reload", "pad:2");
        assertEquals(2, t.rebind("jump", "pad:2").size());            // X was reload's: swapped
        assertEquals("pad:0", t.keyOf("reload"));
        assertEquals(1, t.rebind("fire", "pad:10").size());           // a trigger row may take a button
        assertTrue(t.rebind("jump", "pad:6").isEmpty());              // Start is pause
        assertTrue(t.rebind("forward", "pad:1").isEmpty());           // a keyboard-only row is not a pad row
        Set<String> seen = new HashSet<>();
        for (BindingTable.Row r : BindingTable.PAD_ROWS)
            for (String a : r.actions()) assertTrue(seen.add(a), "action in two pad rows: " + a);
        assertEquals("RT", BindingTable.label("trig:5", k -> "x"));
        assertEquals("button_r1", BindingTable.padGlyph("pad:10"));
    }
}
