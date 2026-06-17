package com.character;

import com.util.CollisionLayers;
import godot.api.AnimationTree;
import godot.api.CollisionShape3D;
import godot.api.Node;
import godot.api.PhysicalBone3D;
import godot.api.PhysicsServer3D;
import godot.core.NodePath;
import godot.core.Vector3;

/**
 * Ragdoll + death-visuals behaviour extracted from {@link Character} (WS5 god-class split).
 *
 * Plain collaborator — deliberately NOT a {@code @RegisterClass} Node — owned by a single
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

        enableRagdoll();

        // Disabled current stance to let ragdoll take over
        Stance s = owner.stanceCache.get(owner.currentStanceName);
        if (s != null && s.getCollider() != null) s.getCollider().setDisabled(true);
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
