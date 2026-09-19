package com.openworld.weapon;

import godot.api.Node;
import godot.global.GD;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HashMap;
import java.util.Map;

/**
 * Per attacker AND KIND (the weapon id that threw or fired it), the cosmetic projectiles this peer is flying,
 * oldest first (PLAN.md N4). Launches and detonations of one attacker arrive in order on reliable ordered channels,
 * and projectiles of ONE kind go off in the order they were thrown (one fuse length; the remote charges all at once,
 * in order), so the host's k-th detonation of a kind is this peer's k-th live copy of it. Across kinds that does not
 * hold -- a 1.5 s flashbang thrown after a 3 s frag goes off first, and a remote charge waits for its detonator --
 * which is why the kind is part of the key. Process-local static state holding
 * NODES, so {@link #clear} runs when the network session ends and a copy removes itself when it leaves the tree.
 */
public final class ProjectileLedger {

    private static final Map<String, Deque<Node>> LIVE = new HashMap<>();

    private ProjectileLedger() { }

    public static void register(String attackerId, String kind, Node projectile) {
        if (attackerId == null || attackerId.isEmpty() || projectile == null) return;
        LIVE.computeIfAbsent(key(attackerId, kind), k -> new ArrayDeque<>()).addLast(projectile);
    }

    public static void forget(Node projectile) {
        for (Deque<Node> q : LIVE.values()) q.remove(projectile);
    }

    private static String key(String attackerId, String kind) {
        return attackerId + "|" + (kind == null ? "" : kind);
    }

    /** The oldest live copy of {@code kind} for {@code attackerId}, removed from the ledger; null when there is none. */
    public static CosmeticProjectile takeOldest(String attackerId, String kind) {
        Deque<Node> q = LIVE.get(key(attackerId, kind));
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
