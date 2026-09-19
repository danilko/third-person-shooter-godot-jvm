package com.openworld.net;

import com.openworld.character.Character;
import godot.api.Node;
import godot.api.PhysicalBone3D;
import godot.api.PhysicsServer3D;
import godot.api.SceneTree;
import godot.core.RID;
import godot.core.StringName;
import godot.core.Transform3D;
import godot.core.Vector3;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Host-side lag compensation for hitscan (PLAN.md N5), the engine half of {@link LagCompensation}.
 *
 * <p>Every physics tick the host records each character's ROOT position, keyed by its own clock — the
 * same clock and the same moment its snapshots are stamped with, so "the host time the client saw" and
 * "the history" are one timeline. To resolve a client's shot it moves the hitbox bones of every body
 * near the shot line by (root then − root now), straight in the physics server, runs the trace, and
 * puts them back. The bones are KINEMATIC, and Jolt applies a kinematic body's new transform only at
 * the next step (a query in between still sees the old place: measured, every rewound shot went
 * through the target to the wall). So each moved bone is made STATIC for the trace, which Jolt moves
 * at once, and given its mode back afterwards. Nothing in the scene tree moves: the skeleton, the camera rig and the body's own
 * collider are untouched, and the next physics step would overwrite the bones anyway.
 *
 * <p>What is rewound is POSITION only, not the animated pose or the facing. Within the 200 ms cap a
 * pose changes centimetres, while a 5 m/s strafe is a metre — the translation is the error worth
 * correcting (Source rewinds the pose as well; it is the next step if a measurement ever asks for it).
 */
public final class LagCompensator {

    private static final StringName CHARACTERS_GROUP = new StringName("characters");
    /** A body whose rewound chest is further than this from the shot line (plus the cone's spread there) is left alone. */
    private static final double REACH_M = 3.0;
    /** Chest height over the root, for the proximity test. */
    private static final double CHEST_Y = 1.0;
    /** Rewinds smaller than this are not worth two physics-server calls per bone. */
    private static final double MIN_SHIFT_M = 0.01;
    /** Records between sweeps that drop the history of bodies that left. */
    private static final int PRUNE_EVERY = 120;

    private final Map<String, LagCompensation.History> histories = new HashMap<>();
    private final Map<String, Integer> lastSeenPass = new HashMap<>();
    private int pass;

    /** Host, every physics tick while a client is connected: append each live character's root. */
    public void record(SceneTree tree, int nowMs) {
        pass++;
        for (Node node : tree.getNodesInGroup(CHARACTERS_GROUP)) {
            if (!(node instanceof Character c) || c.characterInfo == null || c.characterInfo.characterId.isEmpty()) continue;
            String id = c.characterInfo.characterId;
            Vector3 p = c.getGlobalPosition();
            histories.computeIfAbsent(id, k -> new LagCompensation.History()).record(nowMs, p.getX(), p.getY(), p.getZ());
            lastSeenPass.put(id, pass);
        }
        if (pass % PRUNE_EVERY == 0) {
            lastSeenPass.entrySet().removeIf(e -> {
                boolean gone = pass - e.getValue() > PRUNE_EVERY;
                if (gone) histories.remove(e.getKey());
                return gone;
            });
        }
    }

    public void clear() {
        histories.clear();
        lastSeenPass.clear();
    }

    /** Bones moved by one rewind, and where they were — {@link #restore()} puts them back. */
    public static final class Rewind {
        private final List<RID> rids = new ArrayList<>();
        private final List<Transform3D> saved = new ArrayList<>();
        private final List<PhysicsServer3D.BodyMode> modes = new ArrayList<>();
        /** Bodies moved, and the largest shift applied — read by the N5 gate and the debug log. */
        public int bodies;
        public double maxShiftM;
        /** Nearest rewound chest to the shot line, metres (debug). */
        public double nearestLineM = Double.POSITIVE_INFINITY;

        public void restore() {
            for (int i = 0; i < rids.size(); i++) {
                PhysicsServer3D.bodySetState(rids.get(i), PhysicsServer3D.BodyState.TRANSFORM, saved.get(i));
                PhysicsServer3D.bodySetMode(rids.get(i), modes.get(i));
            }
            rids.clear();
            saved.clear();
            modes.clear();
        }
    }

    /**
     * Move the hitboxes of every live body near the shot (except the shooter) to where they were
     * {@code rewindMs} before {@code nowMs}. Always returns a {@link Rewind}; restore it after the trace.
     */
    public Rewind rewind(Character shooter, Vector3 from, Vector3 aim, double range, double spreadDeg,
            int nowMs, int rewindMs) {
        Rewind r = new Rewind();
        if (rewindMs <= 0 || aim.lengthSquared() < 1e-6) return r;
        int then = nowMs - rewindMs;
        Vec3 f = new Vec3(from.getX(), from.getY(), from.getZ());
        Vector3 a = aim.normalized();
        Vec3 dir = new Vec3(a.getX(), a.getY(), a.getZ());
        double coneSlope = Math.tan(Math.toRadians(Math.max(0.0, spreadDeg) * 0.5));
        for (Node node : shooter.getTree().getNodesInGroup(CHARACTERS_GROUP)) {
            if (!(node instanceof Character c) || c == shooter || c.characterInfo == null || !c.isAlive()) continue;
            LagCompensation.History h = histories.get(c.characterInfo.characterId);
            Vec3 past = h == null ? null : h.at(then);
            if (past == null) continue;
            Vector3 now = c.getGlobalPosition();
            double dx = past.x() - now.getX(), dy = past.y() - now.getY(), dz = past.z() - now.getZ();
            double shift = Math.sqrt(dx * dx + dy * dy + dz * dz);
            if (shift < MIN_SHIFT_M) continue;
            Vec3 chest = new Vec3(past.x(), past.y() + CHEST_Y, past.z());
            double along = Math.max(0.0, (chest.x() - f.x()) * dir.x() + (chest.y() - f.y()) * dir.y()
                    + (chest.z() - f.z()) * dir.z());
            double lineDist = LagCompensation.distanceToSegment(chest, f, dir, range);
            if (lineDist > REACH_M + along * coneSlope) continue;
            r.nearestLineM = Math.min(r.nearestLineM, lineDist);
            Vector3 delta = new Vector3(dx, dy, dz);
            for (PhysicalBone3D bone : c.hitboxBones()) {
                RID rid = bone.getRid();
                if (!(PhysicsServer3D.bodyGetState(rid, PhysicsServer3D.BodyState.TRANSFORM) instanceof Transform3D t)) continue;
                r.rids.add(rid);
                r.saved.add(t);
                r.modes.add(PhysicsServer3D.bodyGetMode(rid));
                PhysicsServer3D.bodySetMode(rid, PhysicsServer3D.BodyMode.STATIC);
                PhysicsServer3D.bodySetState(rid, PhysicsServer3D.BodyState.TRANSFORM,
                        new Transform3D(t.getBasis(), t.getOrigin().plus(delta)));
            }
            r.bodies++;
            r.maxShiftM = Math.max(r.maxShiftM, shift);
        }
        return r;
    }
}
