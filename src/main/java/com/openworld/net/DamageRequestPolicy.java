package com.openworld.net;

/**
 * Pure host-side acceptance rules for a client's MSG_DAMAGE_REQUEST (PLAN.md N2) — engine-free, unit-tested.
 *
 * <p>A client used to relay the FINAL damage number for any victim, naming nobody as responsible, and the
 * host checked only that the fields were well-formed: one forged packet could kill anyone. Firearms resolve
 * on the host (MSG_SHOT, N1) and melee does too (MSG_MELEE, N2), so what a client may still relay is:
 * <p><b>After N4</b> projectiles fly on the host too, so AREA is refused outright and only SELF remains.
 * <ul>
 *   <li><b>SELF</b> — damage its OWN simulation dealt to an entity it owns (a fall, drowning, its vehicle's
 *       collision). The victim must be the sender's and the named attacker must BE the victim.</li>
 *   <li><b>AREA</b> — damage from an explosive the sender's own character fired or threw (until N4 moves
 *       projectiles to the host). The named attacker must exist and be the sender's.</li>
 * </ul>
 * Everything else is refused and counted by the caller. The damage itself is bounded as a sanity cap, and
 * AREA requests draw on a per-sender budget (one blast legitimately damages several victims at once).
 */
public final class DamageRequestPolicy {

    public enum Kind { SELF, AREA }

    public enum Verdict { ACCEPT, UNKNOWN_KIND, KIND_REFUSED, UNKNOWN_VICTIM, UNKNOWN_ATTACKER, NOT_OWNER, SELF_MISMATCH, TOO_MANY, DAMAGE_TOO_HIGH }

    /**
     * Whether AREA damage may still be relayed. N2 allowed it while a client flew its own explosives; N4 moved
     * projectiles to the host, so no honest client produces it and it is refused ({@link Verdict#KIND_REFUSED}).
     */
    public static final boolean AREA_ALLOWED = false;

    /** Highest single relayed hit accepted — well above any explosive's max damage, far below "kill anything". */
    public static final double MAX_DAMAGE = 500.0;
    /** AREA requests one sender may land back to back (a grenade into a group), and the sustained refill. */
    public static final double AREA_BURST = 12.0;
    public static final double AREA_PER_SECOND = 6.0;

    private DamageRequestPolicy() { }

    /** The wire value of a kind, or null for one this host does not know. */
    public static Kind kindOf(int wire) {
        return wire >= 0 && wire < Kind.values().length ? Kind.values()[wire] : null;
    }

    /**
     * @param senderPeerId       the peer the request came from
     * @param kind               the declared kind (null = unknown value)
     * @param victimOwnerPeerId  owner of the victim entity, or {@link Integer#MIN_VALUE} when there is no victim
     * @param attackerOwnerPeerId owner of the named attacker, or {@link Integer#MIN_VALUE} when unknown
     * @param attackerIsVictim   the named attacker IS the victim
     * @param areaBudgetOk       whether the sender's AREA budget had a token (ignored for SELF)
     * @param finalDamage        the relayed damage
     */
    public static Verdict evaluate(int senderPeerId, Kind kind, int victimOwnerPeerId, int attackerOwnerPeerId,
                                   boolean attackerIsVictim, boolean areaBudgetOk, double finalDamage) {
        if (kind == null) return Verdict.UNKNOWN_KIND;
        if (kind == Kind.AREA && !AREA_ALLOWED) return Verdict.KIND_REFUSED;
        if (victimOwnerPeerId == Integer.MIN_VALUE) return Verdict.UNKNOWN_VICTIM;
        if (attackerOwnerPeerId == Integer.MIN_VALUE) return Verdict.UNKNOWN_ATTACKER;
        if (attackerOwnerPeerId != senderPeerId) return Verdict.NOT_OWNER;
        if (kind == Kind.SELF && (!attackerIsVictim || victimOwnerPeerId != senderPeerId)) return Verdict.SELF_MISMATCH;
        if (!(finalDamage <= MAX_DAMAGE)) return Verdict.DAMAGE_TOO_HIGH;   // NaN-safe
        if (kind == Kind.AREA && !areaBudgetOk) return Verdict.TOO_MANY;
        return Verdict.ACCEPT;
    }
}
