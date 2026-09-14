package com.openworld.weapon;

import godot.core.Vector3;

/**
 * A projectile a peer flies for LOOKS only (PLAN.md N4): the owner's prediction of its own launch, or a copy
 * replayed from a remote fire cue. It deals no damage. When the host's projectile explodes the host says where
 * ({@code MSG_DETONATION}) and the copy explodes there ({@link #snapDetonate}); a copy that reaches its own
 * detonation first waits a moment for that point before exploding where it is.
 */
public interface CosmeticProjectile {

    /** Explode at the host's {@code point} now, whatever this copy was doing. */
    void snapDetonate(Vector3 point);
}
