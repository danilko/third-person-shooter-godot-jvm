package com.openworld.control;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class InputContextStackTest {
    @Test
    void closingOneOverlayKeepsTheOtherInCharge() {
        int[] changes = {0};
        InputContextStack s = new InputContextStack(() -> changes[0]++);
        assertFalse(s.blocksGameplay());
        s.push("map", InputContext.MENU);
        s.push("radial", InputContext.MENU);
        s.pop("map");                       // closed out of order: the wheel is still open
        assertTrue(s.blocksGameplay());
        assertTrue(s.showsCursor());
        s.pop("radial");
        assertFalse(s.blocksGameplay());
        assertFalse(s.showsCursor());
        assertNull(s.top());
        assertEquals(4, changes[0]);
    }

    @Test
    void heldUnderAMenuStaysHeldAndCaptured() {
        InputContextStack s = new InputContextStack(null);
        s.push("arrest", InputContext.HELD);
        s.push("console", InputContext.MENU);
        assertTrue(s.showsCursor());
        s.pop("console");
        assertTrue(s.blocksGameplay());
        assertFalse(s.showsCursor());
    }

    @Test
    void rePushMovesToTopAndUnknownPopIsANoOp() {
        int[] changes = {0};
        InputContextStack s = new InputContextStack(() -> changes[0]++);
        s.push("arrest", InputContext.HELD);
        s.push("shop", InputContext.MENU);
        s.push("arrest", InputContext.HELD);
        assertEquals(InputContext.HELD, s.top());
        assertEquals("shop:MENU,arrest:HELD", s.describe());
        s.pop("nobody");
        assertEquals(3, changes[0]);
        s.set("shop", InputContext.MENU, false);
        assertFalse(s.has("shop"));
    }
}
