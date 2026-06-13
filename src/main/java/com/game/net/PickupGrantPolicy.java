package com.game.net;

/**
 * Pure host-side grant decision for a client's MSG_PICKUP_REQUEST — extracted from the
 * NetworkManager/GameManager handler (which is engine-bound and untestable headless) so the
 * arbitration rules are unit-tested in {@code PickupGrantPolicyTest}, the same pattern as
 * {@link SnapshotInterpolator}/{@link DeathLatch}.
 *
 * <p>The distance check is deliberately generous: the host evaluates the requester against its
 * ~50-100 ms-stale interpolated puppet position, so exactness is impossible — the tolerance only
 * exists to reject requests for items nowhere near the body (a buggy or forged client), never to
 * adjudicate a close race. A non-finite distance (NaN from a corrupt position) is rejected.
 */
public final class PickupGrantPolicy {

    public enum Verdict { GRANT, NO_PICKUP, ALREADY_TAKEN, NO_CHARACTER, NOT_OWNER, TOO_FAR }

    private PickupGrantPolicy() { }

    public static Verdict evaluate(boolean pickupFound, boolean alreadyTaken,
            boolean characterFound, boolean senderOwnsCharacter,
            double distanceMeters, double toleranceMeters) {
        if (!pickupFound) return Verdict.NO_PICKUP;
        if (alreadyTaken) return Verdict.ALREADY_TAKEN;
        if (!characterFound) return Verdict.NO_CHARACTER;
        if (!senderOwnsCharacter) return Verdict.NOT_OWNER;
        if (!(distanceMeters <= toleranceMeters)) return Verdict.TOO_FAR;   // NaN-safe: !(NaN <= x) is true
        return Verdict.GRANT;
    }
}
