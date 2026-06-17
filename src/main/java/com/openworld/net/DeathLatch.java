package com.openworld.net;

import com.openworld.ui.Feed;

/**
 * Edge-triggered latch that fires exactly once when a replicated health value first reaches
 * zero. Used by {@code NetworkController} to drive the non-authority death/ragdoll path from
 * the continuously-replicated {@code currentHealth} field without re-triggering on every
 * subsequent zero-health snapshot (the snapshot stream keeps carrying health == 0 after the
 * body is dead).
 *
 * <p>Engine-free on purpose (plain float/boolean, no Godot types) so the one-shot semantics
 * are unit-testable headless, mirroring {@link SnapshotInterpolator}.
 */
public final class DeathLatch {

    private boolean dead;

    /**
     * Feed the latest replicated health. Returns {@code true} exactly once — on the first call
     * where {@code currentHealth <= 0} — and {@code false} every call thereafter (and while the
     * body is still alive). The caller plays the death visuals on that single {@code true}.
     */
    public boolean update(float currentHealth) {
        if (dead) return false;
        if (currentHealth <= 0f) {
            dead = true;
            return true;
        }
        return false;
    }

    /** True once the latch has fired — the body is dead and its transform must no longer be driven. */
    public boolean isDead() {
        return dead;
    }
}
