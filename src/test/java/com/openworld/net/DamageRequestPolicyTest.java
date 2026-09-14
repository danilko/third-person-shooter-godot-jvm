package com.openworld.net;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import com.openworld.net.DamageRequestPolicy.Kind;
import com.openworld.net.DamageRequestPolicy.Verdict;
import org.junit.jupiter.api.Test;

class DamageRequestPolicyTest {

    private static final int NONE = Integer.MIN_VALUE;

    @Test
    void selfDamageToYourOwnBodyIsAccepted() {
        assertEquals(Verdict.ACCEPT, DamageRequestPolicy.evaluate(2, Kind.SELF, 2, 2, true, false, 30));
    }

    @Test
    void selfDamageMustBeYoursAndNameItself() {
        assertEquals(Verdict.SELF_MISMATCH, DamageRequestPolicy.evaluate(2, Kind.SELF, 2, 2, false, true, 30));
        // Claiming "self" damage on someone else's body: the attacker is theirs, so not yours.
        assertEquals(Verdict.NOT_OWNER, DamageRequestPolicy.evaluate(2, Kind.SELF, 1, 1, true, true, 30));
    }

    @Test
    void areaDamageIsRefusedOnceProjectilesFlyOnTheHost() {
        // N4: no honest client relays explosion damage any more, from its own character or anyone's.
        assertEquals(Verdict.KIND_REFUSED, DamageRequestPolicy.evaluate(2, Kind.AREA, 1, 2, false, true, 80));
        assertEquals(Verdict.KIND_REFUSED, DamageRequestPolicy.evaluate(2, Kind.AREA, 1, 1, false, true, 80));
    }

    @Test
    void selfDamageNeedsAKnownVictimAndAttacker() {
        assertEquals(Verdict.UNKNOWN_ATTACKER, DamageRequestPolicy.evaluate(2, Kind.SELF, 2, NONE, false, true, 5));
        assertEquals(Verdict.UNKNOWN_VICTIM, DamageRequestPolicy.evaluate(2, Kind.SELF, NONE, 2, false, true, 5));
    }

    @Test
    void absurdDamageAndUnknownKindsAreRefused() {
        assertEquals(Verdict.DAMAGE_TOO_HIGH, DamageRequestPolicy.evaluate(2, Kind.SELF, 2, 2, true, true, 100000));
        assertEquals(Verdict.DAMAGE_TOO_HIGH, DamageRequestPolicy.evaluate(2, Kind.SELF, 2, 2, true, true, Double.NaN));
        assertEquals(Verdict.UNKNOWN_KIND, DamageRequestPolicy.evaluate(2, null, 1, 2, false, true, 1));
        assertNull(DamageRequestPolicy.kindOf(7));
        assertEquals(Kind.AREA, DamageRequestPolicy.kindOf(1));
    }
}
