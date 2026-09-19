package com.openworld.weapon;

import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * The armed remote charges (REC1) on THIS peer's authority, per thrower, oldest first. A charge registers when the
 * authoritative copy is thrown and leaves when it goes off or leaves the tree. {@link #detonateAll} is the detonator:
 * GTA's sticky bomb, every charge the thrower has out goes off at once, in the order they were thrown (so each
 * peer's cosmetic copies, filed the same way, are snapped in the same order).
 *
 * <p>Process-local static state holding NODES, so {@link #clear} runs when a session ends and a charge removes itself
 * in {@code _exitTree}.
 */
public final class RemoteCharges {

    private static final Map<String, List<GrenadeProjectile>> ARMED = new HashMap<>();

    private RemoteCharges() { }

    static void arm(String attackerId, GrenadeProjectile charge) {
        if (attackerId == null || attackerId.isEmpty() || charge == null) return;
        ARMED.computeIfAbsent(attackerId, k -> new ArrayList<>()).add(charge);
    }

    static void forget(GrenadeProjectile charge) {
        for (List<GrenadeProjectile> l : ARMED.values()) l.remove(charge);
    }

    /** Set off every charge {@code attackerId} has armed. Returns how many went off. */
    public static int detonateAll(String attackerId) {
        List<GrenadeProjectile> l = ARMED.remove(attackerId);
        if (l == null) return 0;
        int n = 0;
        for (GrenadeProjectile g : l) {
            if (GD.INSTANCE.isInstanceValid(g) && g.isInsideTree()) { g.detonate(); n++; }
        }
        return n;
    }

    public static int armedCount(String attackerId) {
        List<GrenadeProjectile> l = ARMED.get(attackerId);
        if (l == null) return 0;
        int n = 0;
        for (GrenadeProjectile g : l) if (GD.INSTANCE.isInstanceValid(g)) n++;
        return n;
    }

    public static void clear() { ARMED.clear(); }
}
