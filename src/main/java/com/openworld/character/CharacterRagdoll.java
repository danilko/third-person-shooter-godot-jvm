package com.openworld.character;

import com.openworld.util.CollisionLayers;
import godot.api.AnimationTree;
import godot.api.CollisionShape3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.PhysicalBone3D;
import godot.api.PhysicalBoneSimulator3D;
import godot.api.PhysicsServer3D;
import godot.api.Skeleton3D;
import godot.api.SkeletonModifier3D;
import godot.core.Basis;
import godot.core.NodePath;
import godot.core.Quaternion;
import godot.core.Vector3;
import com.openworld.movement.character.MovementController;
import com.openworld.movement.character.Stance;
import com.openworld.world.manager.ImpactManager;

/**
 * Ragdoll + death-visuals behaviour extracted from {@link Character} (WS5 god-class split).
 *
 * Plain collaborator — deliberately NOT a {@code @Script} Node — owned by a single
 * {@link Character} and operating on its node tree. Keeping it un-registered is what makes the
 * extraction scene-safe: no new {@code .gdj} is generated and no scene {@code ext_resource}
 * reference changes. {@code Character} keeps the public-facing method signatures (and their Godot
 * annotations) and delegates the bodies here.
 *
 * The ragdoll-settle timer state ({@link #ragdollFreezeCountdown}/{@link #ragdollFrozen}) lives
 * here; {@code Character._process} pumps it via {@link #tickFreeze(double)}. The once-only
 * {@code deathVisualsApplied} guard stays on {@code Character} because {@code Player} reads it.
 */
final class CharacterRagdoll {

    // Velocity change per damage point applied to an alive character (m/s per dmg).
    private static final float ALIVE_HIT_VELOCITY_SCALE = 0.05f;
    // Impulse magnitude per damage point applied to the hit ragdoll bone (N·s per dmg).
    private static final float DEATH_BONE_IMPULSE_SCALE = 0.3f;

    private final Character owner;

    private double  ragdollFreezeCountdown = -1.0;
    private boolean ragdollFrozen          = false;

    /**
     * True while this body is a corpse held in a vehicle seat (PLAN.md 0.2). A seated occupant who
     * dies stays where they died -- GTA's model: the driver slumps over the wheel, the car rolls on,
     * and the body only drops out when someone opens the door -- so the ragdoll is NOT started
     * (bones simulating inside a moving car's hull would tumble through it and out). The body is
     * frozen in a slumped pose instead, and {@link #releaseSeatedCorpse()} starts the ordinary
     * ragdoll the moment the seat lets it go.
     */
    private boolean seatedCorpse = false;

    /**
     * The slump: each bone pitched FORWARD about the body's own lateral axis, degrees, spine to head.
     * Procedural and deliberately modest -- a placeholder until an authored seated-death clip exists
     * (P6). The chest folds ~38 degrees further than the seated clip and the neck and head another
     * ~55: measured on DebugWorld, the chest leans about 25 degrees more than the living, aiming driver,
     * whose shoulder modifier had been holding it up.
     */
    private static final String[] SLUMP_BONES   = {"spine_01", "spine_02", "spine_03", "neck_01", "head_2"};
    private static final double[]  SLUMP_DEGREES = {8.0, 10.0, 20.0, 30.0, 25.0};

    CharacterRagdoll(Character owner) {
        this.owner = owner;
    }

    /**
     * Counts down the ragdoll-settle timer and freezes physics when it expires. Pumped from
     * {@code Character._process(delta)} — a no-op until {@link #enableRagdoll()} arms the countdown.
     */
    void tickFreeze(double delta) {
        if (ragdollFreezeCountdown <= 0) return;
        ragdollFreezeCountdown -= delta;
        if (ragdollFreezeCountdown <= 0) freezeRagdoll();
    }

    /**
     * The visual half of death — disable the AnimationTree, start the ragdoll, and drop the
     * active stance collider so the corpse settles. Shared by the authoritative {@code onDied()}
     * path and the non-authority {@code applyReplicatedDeath()} path so a replicated corpse looks
     * identical without re-running authority-only side effects. Idempotent via {@code deathVisualsApplied}.
     */
    void enableDeathVisuals() {
        if (owner.deathVisualsApplied) return;
        owner.deathVisualsApplied = true;

        // Disable animation tree — prefer meshConfig path, fall back to legacy position.
        AnimationTree animationTree = null;
        if (owner.visualsInstance != null && owner.meshConfig != null
                && !owner.meshConfig.animationTreePath.isEmpty()) {
            Node atNode = owner.visualsInstance.getNodeOrNull(owner.meshConfig.animationTreePath);
            if (atNode instanceof AnimationTree at) animationTree = at;
        }
        if (animationTree == null) animationTree = (AnimationTree) owner.getNodeOrNull("AnimationTree");
        if (animationTree != null) animationTree.setActive(false);

        if (owner.currentVehicleNode != null) {
            enableSeatedDeath();
            return;
        }

        enableRagdoll();

        // Disabled current stance to let ragdoll take over
        Stance s = owner.stanceCache.get(owner.currentStanceName);
        if (s != null && s.getCollider() != null) s.getCollider().setDisabled(true);
    }

    /** True while a seated corpse is waiting for its seat to release it. */
    boolean isSeatedCorpse() { return seatedCorpse; }

    /**
     * Death in a seat: no simulation, a frozen slumped pose. The aim/IK modifiers are switched off
     * (they would keep turning a dead body's shoulders toward its last aim point) and the bones leave
     * the hitbox layer for the same reason {@link #enableRagdoll()} takes them off it -- a corpse must
     * not block line of sight or soak up a shot meant for whoever is behind it.
     */
    private void enableSeatedDeath() {
        seatedCorpse = true;
        Skeleton3D skel = skeleton();
        if (skel != null) {
            for (int i = 0; i < skel.getChildCount(); i++) {
                Node child = skel.getChild(i);
                if (child instanceof SkeletonModifier3D m && !(child instanceof PhysicalBoneSimulator3D)) {
                    m.setActive(false);
                }
            }
            slump(skel);
        }
        if (owner.physicalBoneSimulator != null) {
            for (int i = 0; i < owner.physicalBoneSimulator.getChildCount(); i++) {
                if (owner.physicalBoneSimulator.getChild(i) instanceof PhysicalBone3D bone) {
                    bone.setCollisionLayerValue(CollisionLayers.LAYER_HITBOX, false);
                }
            }
        }
    }

    /**
     * The seat has let the corpse go (a carjack pulled it out, the car was freed): start the ordinary
     * ragdoll from the slumped pose. Called from {@code CharacterDriveState.exit}, after the body has
     * been placed beside the car. {@code _process} is switched back on because it is what pumps the
     * ragdoll's settle-and-freeze timer, and a driver's processing was turned off when they sat down.
     */
    void releaseSeatedCorpse() {
        if (!seatedCorpse) return;
        seatedCorpse = false;
        owner.setProcess(true);
        enableRagdoll();
        Stance s = owner.stanceCache.get(owner.currentStanceName);
        if (s != null && s.getCollider() != null) s.getCollider().setDisabled(true);
    }

    private Skeleton3D skeleton() {
        return owner.physicalBoneSimulator != null && owner.physicalBoneSimulator.getParent() instanceof Skeleton3D sk
                ? sk : null;
    }

    /**
     * Pitch the slump chain forward about the BODY's lateral axis. The axis is taken from
     * {@code MeshRoot} (-Z forward, +X right) and expressed in each bone's own frame, so the result
     * does not depend on how the importer oriented the bones -- W1's lesson (a bone's local axes are
     * whatever the rig says, and `spine_03`'s +X is the body's LEFT on this one). Rotating every bone
     * about ONE world axis also keeps a child's axis fixed while its parent turns, so the chain
     * composes with no re-read of the pose.
     */
    private void slump(Skeleton3D skel) {
        Node meshRoot = owner.visualsInstance != null && owner.meshConfig != null
                ? owner.visualsInstance.getNodeOrNull(owner.meshConfig.meshRootPath) : null;
        if (!(meshRoot instanceof Node3D mr)) return;
        Vector3 rightWorld = mr.getGlobalTransform().getBasis().getColumn(0).normalized();
        Vector3 axisSkel = skel.getGlobalTransform().getBasis().inverse().times(rightWorld).normalized();
        for (int i = 0; i < SLUMP_BONES.length; i++) {
            int idx = skel.findBone(SLUMP_BONES[i]);
            if (idx < 0) continue;
            Basis boneGlobal = skel.getBoneGlobalPose(idx).getBasis();
            Vector3 axisLocal = boneGlobal.inverse().times(axisSkel).normalized();
            // About the body's RIGHT axis a positive angle tips +Y (up the spine) toward +Z, which is
            // the body's BACK on a -Z-forward mesh -- so forward is negative.
            Quaternion bend = new Quaternion(axisLocal, -Math.toRadians(SLUMP_DEGREES[i]));
            skel.setBonePoseRotation(idx, skel.getBonePoseRotation(idx).times(bend));
        }
    }

    private void enableRagdoll() {
        // Stop Character's own input/apply cycle
        owner.setPhysicsProcess(false);

        // Stop MovementController — it is a separate Node with its own
        // _physicsProcess that applies gravity and calls moveAndSlide().
        // Without this, the CharacterBody3D keeps falling even after death.
        if (owner.hasNode("MovementController")) {
            owner.getNode("MovementController").setPhysicsProcess(false);
        }

        // Disable all CharacterBody3D stance capsules so the frozen corpse
        // shell doesn't block navigation or other characters.
        for (int i = 0; i < owner.getChildCount(); i++) {
            Node child = owner.getChild(i);
            if (child instanceof CollisionShape3D shape) {
                shape.setDisabled(true);
            }
        }

        if (owner.physicalBoneSimulator == null) {
            ragdollFrozen = true; // nothing to freeze later
            return;
        }

        if (owner.ragdollDuration > 0) {
            // Simulate ragdoll briefly so the body tumbles naturally, then freeze.
            for (int i = 0; i < owner.physicalBoneSimulator.getChildCount(); i++) {
                Node child = owner.physicalBoneSimulator.getChild(i);
                if (child instanceof PhysicalBone3D bone) {
                    // Remove dead bones from the hitbox layer so living characters' AimRay
                    // and LoS rays pass through corpses. Fixes dead bodies blocking
                    // hasLineOfSight() and performHitscan().
                    bone.setCollisionLayerValue(CollisionLayers.LAYER_HITBOX, false);
                    // Add world to mask so ragdoll bones rest on floor geometry.
                    bone.setCollisionMaskValue(CollisionLayers.LAYER_WORLD, true);
                }
            }
            owner.physicalBoneSimulator.physicalBonesStartSimulation();
            ragdollFreezeCountdown = owner.ragdollDuration;
        } else {
            // ragdollDuration == 0: skip simulation, freeze at animation pose immediately.
            freezeRagdoll();
        }
    }

    /**
     * Freezes all ragdoll physics and stops the bone simulator.
     *
     * Called automatically after ragdollDuration seconds (via {@link #tickFreeze}), or
     * immediately when ragdollDuration <= 0. After this:
     *   - PhysicalBone3D rigid bodies are frozen in place (no gravity, no collision)
     *   - PhysicalBoneSimulator3D modifier is deactivated
     *   - Skeleton retains the last bone transforms → mesh stays at the frozen pose
     *   - No ongoing physics or modifier processing cost
     */
    private void freezeRagdoll() {
        if (ragdollFrozen) return;
        ragdollFrozen = true;
        owner.setProcess(false);

        if (owner.physicalBoneSimulator == null) return;

        for (int i = 0; i < owner.physicalBoneSimulator.getChildCount(); i++) {
            Node child = owner.physicalBoneSimulator.getChild(i);
            if (child instanceof PhysicalBone3D bone) {
                // Switch from DYNAMIC → STATIC in the physics server.
                // STATIC bodies are not simulated (no gravity, no velocity integration)
                // but stay exactly at their current world transform and remain solid
                // so the corpse rests on the floor rather than falling through it.
                // This is the same technique used by CS-style engines for settled ragdolls.
                PhysicsServer3D.bodySetMode(bone.getRid(), PhysicsServer3D.BodyMode.STATIC);
                // Static bodies don't move so they don't need a collision mask
                // (they never query what they're touching). Keep the layer so
                // bullets and characters can still physically interact with the corpse.
                bone.setCollisionMask(0);
            }
        }
        // Leave the simulator active — it copies the now-static bone world transforms
        // to the skeleton each frame, keeping the mesh at the frozen ragdoll pose.
        // Cost is a handful of matrix copies, not physics simulation.
    }

    /**
     * Applies a physics response to a bullet hit.
     *
     * While alive: adds a small velocity kick in the bullet direction — simulates the
     * stagger seen in CS/L4D where shots push the target back from the shooter.
     *
     * On death: pushes the specific PhysicalBone3D that was struck so the ragdoll
     * falls away from the shooter. Requires the ragdoll to already be started —
     * ImpactManager calls this after applyDamage(), by which point the synchronous
     * died-signal chain has already called enableRagdoll().
     *
     * @param hitNode    the node returned by AimRay (typically a PhysicalBone3D)
     * @param bulletDir  world-space bullet travel direction (hitNormal negated)
     * @param damage     base damage value used to scale the impulse magnitude
     */
    void applyHitImpulse(Node hitNode, Vector3 bulletDir, float damage) {
        Vector3 dir = bulletDir.normalized();
        if (owner.isAlive()) {
            owner.setVelocity(owner.getVelocity().plus(dir.times(damage * ALIVE_HIT_VELOCITY_SCALE)));
        } else if (hitNode instanceof PhysicalBone3D bone) {
            bone.applyCentralImpulse(dir.times(damage * DEATH_BONE_IMPULSE_SCALE));
        }
    }

    /**
     * Apply a physics impulse to a named bone during ragdoll.
     * Only has effect when the ragdoll is active (call after enableRagdoll or on death).
     */
    void applyBoneImpulse(String boneName, Vector3 impulse) {
        if (owner.physicalBoneSimulator == null) return;
        for (int i = 0; i < owner.physicalBoneSimulator.getChildCount(); i++) {
            Node child = owner.physicalBoneSimulator.getChild(i);
            if (child instanceof PhysicalBone3D bone && boneName.equalsIgnoreCase(String.valueOf(bone.getName()))) {
                bone.applyCentralImpulse(impulse);
                return;
            }
        }
    }
}
