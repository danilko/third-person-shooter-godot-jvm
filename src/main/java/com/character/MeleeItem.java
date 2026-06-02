package com.character;

import com.environment.HitInfo;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Node;
import godot.api.RayCast3D;
import godot.api.Timer;
import godot.api.Object;
import godot.core.Vector3;

/**
 * Base class for all melee weapons (fist, knife, sword).
 *
 * Hit detection uses the character's existing AimRay with a distance cap (meleeRange).
 * This hits exactly what the player/AI is looking at within arm's reach — no Area3D
 * signal timing issues, no animation-dependent hitbox positioning. When proper swing
 * animations exist, an Area3D hitbox pass can be layered on top without changing
 * this instant-check foundation.
 *
 * Scene setup — every MeleeItem scene must include:
 *   HitTimer (Timer)   one_shot=true  ← controls attack window / rate-limiting
 *
 * Signal connection in .tscn:
 *   HitTimer.timeout → . on_hit_timer_timeout   (optional visual feedback hook)
 */
@RegisterClass(className = "MeleeItem")
public class MeleeItem extends WeaponItem {

    private static final Vector3 TORSO_OFFSET = new Vector3(0, 0.8f, 0);

    /** Maximum reach in metres, measured from the character's torso (not the camera). */
    @Export @RegisterProperty
    public float meleeRange = 1.5f;

    /**
     * Half-angle of the hit-detection cone in degrees.
     * Each swing casts 5 rays — centre plus ±coneAngleDeg in pitch and yaw — so a
     * target anywhere inside this cone registers even if the crosshair isn't dead-on.
     * 25° gives ~0.7 m of forgiveness at 1.5 m range; tune up for slow heavy weapons,
     * down for precise weapons like a knife.
     */
    @Export @RegisterProperty
    public float coneAngleDeg = 25f;

    /**
     * How long the hit window stays open after a swing starts (seconds).
     * Hit is checked every physics frame during this window; stops on first contact.
     * This gives the grace period needed so the player doesn't have to be pixel-perfect
     * at the exact frame they press the attack button.
     */
    @Export @RegisterProperty
    public float swingDuration = 0.3f;

    protected Timer hitTimer;

    private float     swingTimeLeft      = 0f;
    private boolean   swingHitRegistered = false;
    // Built once in _ready() from the constant coneAngleDeg export; reused every swing.
    private float[][] swingOffsets;

    @RegisterFunction
    @Override
    public void _ready() {
        Node ht = getNodeOrNull("HitTimer");
        if (ht instanceof Timer t) hitTimer = t;
        buildSwingOffsets();
    }

    private void buildSwingOffsets() {
        float a = coneAngleDeg;
        swingOffsets = new float[][]{{0, 0}, {a, 0}, {-a, 0}, {0, a}, {0, -a}};
    }

    @RegisterFunction
    @Override
    public void _physicsProcess(double delta) {
        if (swingTimeLeft <= 0) return;
        swingTimeLeft -= (float) delta;
        if (!swingHitRegistered && performMeleeHit()) {
            swingHitRegistered = true;
        }
    }

    // ── WeaponAction ─────────────────────────────────────────────────────────

    @Override
    public void useWeapon() {
        if (hitTimer != null) {
            hitTimer.setWaitTime(1.0 / fireRate);
            hitTimer.start();
        }
        if (weaponAudio != null && fireAudio != null) {
            weaponAudio.stop();
            weaponAudio.setStream(fireAudio);
            weaponAudio.play();
        }
        swingTimeLeft      = swingDuration;
        swingHitRegistered = false;
    }

    @Override
    public boolean canUse() {
        return hitTimer == null || hitTimer.getTimeLeft() <= 0;
    }

    @Override public void stopUseWeapon() {}
    @Override public WeaponType getWeaponType() { return WeaponType.MELEE; }

    // ── Signal handler ────────────────────────────────────────────────────────

    @RegisterFunction
    public void onHitTimerTimeout() {
        // Hook for subclasses or future animation feedback; no hitbox to disable.
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    /**
     * Casts 5 rays in a cone (centre + ±coneAngleDeg pitch and yaw) from the camera
     * AimRay and returns true on the first hit within meleeRange of the character's
     * torso. Stops at first contact so only one hit registers per swing-window frame.
     *
     * Uses the same temp-rotate + forceRaycastUpdate() + restore pattern as
     * FirearmItem.performHitscan() — no new node types needed.
     *
     * Range is measured from the character's torso (≈0.8 m above feet) so the check
     * is consistent in both FPS and TPS regardless of where the camera sits.
     */
    private boolean performMeleeHit() {
        if (weaponController == null || owningCharacter == null || swingOffsets == null) return false;
        RayCast3D ray = weaponController.getAimRay();
        if (ray == null) return false;

        var im = getImpactManager();
        if (im == null) return false;

        Vector3 torso    = owningCharacter.getGlobalPosition().plus(TORSO_OFFSET);
        Vector3 savedRot = ray.getRotationDegrees();
        try {
            for (float[] off : swingOffsets) {
                ray.setRotationDegrees(new Vector3(savedRot.getX() + off[0],
                                                   savedRot.getY() + off[1], 0f));
                ray.forceRaycastUpdate();
                if (hitInRange(ray, torso, im)) return true;
            }
            return false;
        } finally {
            ray.setRotationDegrees(savedRot);
        }
    }

    /** Checks one ray direction; processes the hit via ImpactManager and returns true if in range. */
    private boolean hitInRange(RayCast3D ray, Vector3 torso, com.environment.ImpactManager im) {
        if (!ray.isColliding()) return false;
        // Reject floor/ground surfaces (normal pointing mostly upward) to prevent the
        // TPS camera's natural downward tilt from registering ground hits.
        if (ray.getCollisionNormal().getY() > 0.7f) return false;
        Vector3 hitPoint = ray.getCollisionPoint();
        if ((float) hitPoint.minus(torso).length() > meleeRange) return false;
        Object collider = ray.getCollider();
        Node hitNode = (collider instanceof Node n) ? n : null;
        im.processHit(new HitInfo(hitNode, hitPoint, ray.getCollisionNormal()),
                      damage, getDisplayName(), weaponIcon, resolveAttackerName(), resolveAttackerFaction());
        return true;
    }
}
