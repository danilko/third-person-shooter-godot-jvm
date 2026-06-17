package com.openworld.weapon;

import com.openworld.world.HitInfo;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Node;
import godot.api.RayCast3D;
import godot.api.Timer;
import godot.api.Object;
import godot.core.Vector3;
import com.openworld.character.AICharacter;
import com.openworld.item.Pickup;
import com.openworld.world.manager.ImpactManager;

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
     * 25° gives ~0.7 m of forgiveness at 1.5 m range; tune down for precise weapons.
     */
    @Export @RegisterProperty
    public float coneAngleDeg = 25f;

    /**
     * How long the hit window stays open after a swing starts (seconds).
     * Hit is checked every physics frame during this window; stops on first contact.
     */
    @Export @RegisterProperty
    public float swingDuration = 0.3f;

    protected Timer hitTimer;

    private float   swingTimeLeft      = 0f;
    private boolean swingHitRegistered = false;
    // Built once in _ready() from coneAngleDeg; accessible to subclasses for override.
    protected float[][] swingOffsets;

    @RegisterFunction
    @Override
    public void _ready() {
        super._ready();  // Pickup._ready — group + pickupId registration for replication
        Node ht = getNodeOrNull("HitTimer");
        if (ht instanceof Timer t) hitTimer = t;
        swingOffsets = buildOffsets(coneAngleDeg);
    }

    /**
     * Builds a 5-ray cone offset table from the given half-angle.
     * Protected so subclasses can build their own offset tables (e.g. KnifeItem
     * pre-builds a heavy-attack table with a wider angle).
     */
    protected static float[][] buildOffsets(float angleDeg) {
        return new float[][]{{0, 0}, {angleDeg, 0}, {-angleDeg, 0}, {0, angleDeg}, {0, -angleDeg}};
    }

    /** Mirrors meleeRange so AI range checks (AICharacter.getEffectiveAttackRange) and
     *  actual hit detection always agree — no separate "weaponRange" to keep in sync. */
    @Override
    public float getEffectiveRange() { return meleeRange; }

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
        if (weaponAudio != null && fireAudio != null) {
            weaponAudio.stop();
            weaponAudio.setStream(fireAudio);
            weaponAudio.play();
        }
        startSwing();
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

    // ── Protected helpers (accessible to subclasses) ──────────────────────────

    /**
     * Starts the attack window: resets swing flags and arms the rate-limit timer.
     * Separated from useWeapon() audio so KnifeItem.stopUseWeapon() can start the
     * swing on button-release without double-playing audio.
     */
    protected void startSwing() {
        if (hitTimer != null) {
            hitTimer.setWaitTime(1.0 / fireRate);
            hitTimer.start();
        }
        swingTimeLeft      = swingDuration;
        swingHitRegistered = false;
    }

    /**
     * Override in subclasses to select different damage/range/offsets per attack type.
     * Default uses the instance's exported damage/meleeRange/swingOffsets.
     */
    protected boolean performMeleeHit() {
        return performMeleeHitWith(damage, meleeRange, swingOffsets);
    }

    /**
     * Casts 5 rays (center + ±pitch/yaw from {@code offsets}) and processes the first
     * hit within {@code range} via ImpactManager. Returns true on first contact.
     *
     * Explicit parameters let subclasses (KnifeItem) call this with light-attack or
     * heavy-attack stats without touching instance fields.
     */
    protected boolean performMeleeHitWith(float hitDamage, float range, float[][] offsets) {
        if (weaponController == null || owningCharacter == null || offsets == null) return false;
        RayCast3D ray = weaponController.getAimRay();
        if (ray == null) return false;
        var im = getImpactManager();
        if (im == null) return false;

        Vector3 torso    = owningCharacter.getGlobalPosition().plus(TORSO_OFFSET);
        Vector3 savedRot = ray.getRotationDegrees();
        try {
            for (float[] off : offsets) {
                ray.setRotationDegrees(new Vector3(savedRot.getX() + off[0],
                                                   savedRot.getY() + off[1], 0f));
                ray.forceRaycastUpdate();
                if (!ray.isColliding()) continue;
                // Reject upward-facing normals to prevent TPS downward-tilt camera from
                // registering floor hits.
                if (ray.getCollisionNormal().getY() > 0.7f) continue;
                Vector3 hitPoint = ray.getCollisionPoint();
                if ((float) hitPoint.minus(torso).length() > range) continue;
                Node hitNode = (ray.getCollider() instanceof Node n) ? n : null;
                im.processHit(new HitInfo(hitNode, hitPoint, ray.getCollisionNormal()),
                        hitDamage, getDisplayName(), weaponIcon,
                        resolveAttackerName(), resolveAttackerFaction());
                return true;
            }
            return false;
        } finally {
            ray.setRotationDegrees(savedRot);
        }
    }
}
