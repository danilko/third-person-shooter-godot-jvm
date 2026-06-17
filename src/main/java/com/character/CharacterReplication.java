package com.character;

import godot.api.Node;
import godot.core.Vector3;

/**
 * Non-authority replication-apply writes extracted from {@link Character} (WS5 god-class split).
 *
 * Plain collaborator — NOT a {@code @RegisterClass} Node — owned by a single {@link Character},
 * so the extraction is scene-safe (no {@code .gdj}, no scene {@code ext_resource} change).
 * {@code Character} keeps the public {@code applyReplicated*} surface that
 * {@link NetworkController} calls each frame and delegates the bodies here.
 *
 * These writes are the only state a non-authority (puppet) body ever receives: it never runs
 * gatherInput/applyInput/physics (see {@code Character._physicsProcess}'s early return), so the
 * interpolator drives transform/facing/aim every frame and combat/stance/movement-type are
 * applied discretely once per snapshot.
 */
final class CharacterReplication {

    private final Character owner;

    CharacterReplication(Character owner) {
        this.owner = owner;
    }

    /** Direct transform write — safe outside _physicsProcess because non-authority bodies never run move_and_slide. */
    void applyTransform(Vector3 position, Vector3 velocity) {
        owner.setGlobalPosition(position);
        owner.setVelocity(velocity);
    }

    /**
     * Direct mesh-facing write — counterpart to {@code Character.getFacingYaw()}. Sets only
     * meshRoot's Y rotation, preserving whatever X/Z it already has (mirrors how
     * MovementController itself only ever rewrites Y).
     */
    void applyFacing(float yaw) {
        Node mcNode = owner.getNodeOrNull("MovementController");
        if (!(mcNode instanceof MovementController mc) || mc.meshRoot == null) return;
        Vector3 rot = mc.meshRoot.getRotation();
        float localY = yaw - (float) owner.getRotation().getY();
        mc.meshRoot.setRotation(new Vector3(rot.getX(), localY, rot.getZ()));
    }

    /** Direct spine-IK look write — moves the aimTarget marker the LookAtModifier3D tracks, so a puppet's upper body aims where the owner looks. */
    void applyAim(Vector3 aimPosition) {
        if (owner.aimTarget != null && aimPosition != null) owner.aimTarget.setGlobalPosition(aimPosition);
    }

    /**
     * Drives the locomotion blend on a non-authority body from replicated motion. applyInput never
     * runs on a puppet, so {@code changed_movement_direction} / {@code set_cam_rotation} never fire
     * for it — without this the AnimationController's walk/strafe blend stays frozen (the "AI
     * animation not synced" bug). Movement direction is derived from the interpolated horizontal
     * velocity (the same world-space convention the owner's own signal carries); facing yaw is pushed
     * in as camRotation so the combat strafe blend rotates correctly. Movement *type* (walk vs sprint)
     * is applied separately and discretely via {@link #applyMovementType(int)}.
     */
    void applyLocomotion(Vector3 velocity, double yaw) {
        Vector3 flat = new Vector3(velocity.getX(), 0, velocity.getZ());
        if (flat.lengthSquared() > 0.01) {
            owner.movementDirection = flat.normalized();
            owner.changedMovementDirection.emit(owner.movementDirection);
        } else if (owner.movementDirection.lengthSquared() > 0.0) {
            // Velocity has settled to ~0: collapse the strafe direction to idle exactly once,
            // instead of holding the last non-zero lean (the "stuck mid-stride" look after a
            // remote body stops). The walk/idle blend itself is driven by the discrete
            // movementType (applyMovementType); this clears the combat strafe lean.
            owner.movementDirection = Vector3.Companion.getZERO();
            owner.changedMovementDirection.emit(owner.movementDirection);
        }
        Node acNode = owner.getNodeOrNull("AnimationController");
        if (acNode instanceof AnimationController ac) ac.onSetCamRotation(yaw);
    }

    /** Applies a replicated movement type (IDLE/WALK/SPRINT) on a puppet — emits changed_movement_state so the blend speed/pose updates exactly like the local path. */
    void applyMovementType(int ordinal) {
        MovementType[] types = MovementType.values();
        if (ordinal >= 0 && ordinal < types.length) owner.setMovementState(types[ordinal]);
    }

    /**
     * Replays the same change-detection + signal cascade applyInput uses for combat/stance so the
     * local-input and replication paths share one "transition into this state" routine rather than
     * drifting apart over time.
     */
    void applyCombatAndStance(boolean combat, int stanceOrdinal) {
        if (combat != owner.combat) {
            owner.combat = combat;
            owner.setCombatState();
        }
        StanceName[] stances = StanceName.values();
        if (stanceOrdinal >= 0 && stanceOrdinal < stances.length && stanceOrdinal != owner.currentStanceName.ordinal()) {
            owner.setStance(stances[stanceOrdinal]);
        }
    }
}
