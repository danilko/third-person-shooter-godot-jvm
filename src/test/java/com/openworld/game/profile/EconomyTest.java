package com.openworld.game.profile;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import org.junit.jupiter.api.Test;

class EconomyTest {
    @Test
    void aPurchaseIsRefusedWhenShortAndChangesNothing() {
        PlayerProfile p = new PlayerProfile("p");
        p.balance = 500;
        assertFalse(Economy.transfer(p, null, 800, Economy.Reason.PURCHASE));
        assertEquals(500, p.balance);
        assertTrue(Economy.transfer(p, null, 500, Economy.Reason.PURCHASE));
        assertEquals(0, p.balance);
    }

    @Test
    void aBillMayGoIntoDebt() {
        PlayerProfile p = new PlayerProfile("p");
        p.balance = 300;
        assertEquals(1000, Economy.bill(p, 1000, Economy.Reason.BILL_HOSPITAL));
        assertEquals(-700, p.balance);
        assertEquals(700, p.totalDebt());
        // the next income pays it back first
        assertTrue(Economy.transfer(null, p, 1000, Economy.Reason.REWARD));
        assertEquals(300, p.balance);
    }

    @Test
    void playerToPlayerAndListeners() {
        PlayerProfile a = new PlayerProfile("a"), b = new PlayerProfile("b");
        a.balance = 100;
        List<Economy.Transfer> seen = new ArrayList<>();
        Consumer<Economy.Transfer> l = seen::add;
        Economy.listen(l);
        try {
            assertTrue(Economy.transfer(a, b, 60, Economy.Reason.SALE));
            assertFalse(Economy.transfer(a, b, 0, Economy.Reason.SALE));
            assertFalse(Economy.transfer(null, null, 5, Economy.Reason.GRANT));
            assertFalse(Economy.transfer(a, a, 5, Economy.Reason.GRANT));
        } finally {
            Economy.unlisten(l);
        }
        assertEquals(40, a.balance);
        assertEquals(60, b.balance);
        assertEquals(1, seen.size());
        assertEquals(Economy.Reason.SALE, seen.get(0).reason());
    }
}
