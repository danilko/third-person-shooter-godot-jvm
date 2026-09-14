package com.openworld.weapon;

import godot.api.Node;
import godot.global.GD;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HashMap;
import java.util.Map;

/**
 * Per attacker, the cosmetic projectiles this peer is flying, oldest first (PLAN.md N4). A host detonation
 * names only its attacker: launches and detonations of one attacker arrive in order on reliable ordered
 * channels, so the host's k-th detonation is this peer's k-th live copy. Process-local static state holding
 * NODES, so {@link #clear} runs when the network session ends and a copy removes itself when it leaves the tree.
 */
public final class ProjectileLedger {

    private static final Map<String, Deque<Node>> LIVE = new HashMap<>();

    private ProjectileLedger() { }

    public static void register(String attackerId, Node projectile) {
        if (attackerId == null || attackerId.isEmpty() || projectile == null) return;
        LIVE.computeIfAbsent(attackerId, k -> new ArrayDeque<>()).addLast(projectile);
    }

    public static void forget(Node projectile) {
        for (Deque<Node> q : LIVE.values()) q.remove(projectile);
    }

    /** The oldest live copy for {@code attackerId}, removed from the ledger; null when there is none. */
    public static CosmeticProjectile takeOldest(String attackerId) {
        Deque<Node> q = LIVE.get(attackerId);
        while (q != null && !q.isEmpty()) {
            Node n = q.pollFirst();
            if (GD.INSTANCE.isInstanceValid(n) && n instanceof CosmeticProjectile cp) return cp;
        }
        return null;
    }

    public static void clear() {
        LIVE.clear();
    }
}
