package com.character;

import com.character.ai.AIState;
import com.character.ai.PatrolState;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.*;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

@RegisterClass(className = "AICharacter")
public class AICharacter extends Character {

    /** Y-offset of the SightRay and AimRay above the character's feet. */
    public static final float EYE_HEIGHT = 1.4f;

    /**
     * Y-offset from a character's CharacterBody3D origin (feet) to upper body.
     * Used for aim targeting and LoS checks.
     */
    public static final float TARGET_BODY_HEIGHT = 0.9f;

    // ── Inspector-tunable properties ──────────────────────────────────────────
    @Export @RegisterProperty public float detectionRange       = 120.0f;
    @Export @RegisterProperty public float aimPitchMin          = -55.0f;
    @Export @RegisterProperty public float aimPitchMax          =  75.0f;
    @Export @RegisterProperty public float attackRange          = 150.0f;
    @Export @RegisterProperty public float patrolRadius         =  80.0f;
    @Export @RegisterProperty public Area3D ammoRefill;

    /** Per-shot probability of hitting the target (0 = always miss, 1 = always hit). */
    @Export @RegisterProperty public float hitChance            = 0.9f;
    /** Seconds from first LoS contact before firing begins. */
    @Export @RegisterProperty public float reactionTime         = 0.1f;
    /** Maximum aim scatter radius (world units) for a miss at 10 m, scales with distance. */
    @Export @RegisterProperty public float aimScatterRadius     = 1.5f;
    /** Seconds between lateral strafe direction changes in attack stance. */
    @Export @RegisterProperty public float strafeChangeDuration = 1f;
    /** Seconds of suppression fire after losing LoS before switching to SearchState. */
    @Export @RegisterProperty public float suppressionDuration  = 1.5f;

    // ── Constants ─────────────────────────────────────────────────────────────
    private static final float  AMMO_REFILL_ARRIVAL_THRESHOLD = 1.5f;
    private static final double LOST_TARGET_TIMEOUT           = 3.0;
    private static final double UNDER_ATTACK_DURATION         = 2.5;

    // ── AI node refs ──────────────────────────────────────────────────────────
    private NavigationAgent3D navAgent;
    private RayCast3D sightRay;

    // ── AI FSM state ──────────────────────────────────────────────────────────
    private AIState  currentState;
    private Vector3  spawnPosition;
    private boolean  isDead = false;

    /** Runtime target; discovered via discoverTarget(). Not exported — determined by faction. */
    private Character currentTarget;

    // ── Per-tick timers (package-private so state singletons can access them) ─
    double attackTimer      = 0.0;
    double lostTargetTimer  = 0.0;
    double reactionTimer    = 0.0;
    double underAttackTimer = 0.0;
    double strafeTimer      = 0.0;
    double searchTimer      = 0.0;

    float strafeX = 0f;
    float strafeZ = 0f;

    Vector3 lastKnownTargetPosition = null;
    Vector3 currentAimTarget        = null;

    // ── Lifecycle ─────────────────────────────────────────────────────────────
    @RegisterFunction
    @Override
    public void _ready() {
        useWeaponSpread = false;
        super._ready();
        navAgent = (NavigationAgent3D) getNode("NavigationAgent3D");
        sightRay = (RayCast3D) getNode("CameraRoot/Yaw/Pitch/Pivot/SpringArm/Camera/SightRay");

        for (int i = 0; i < physicalBoneSimulator.getChildCount(); i++) {
            Node child = physicalBoneSimulator.getChild(i);
            if (child instanceof PhysicalBone3D bone) sightRay.addException(bone);
        }
        spawnPosition = new Vector3(getGlobalPosition());
        transitionTo(PatrolState.INSTANCE);
    }

    // ── Input gathering (AI FSM → CharacterInput) ─────────────────────────────
    @Override
    protected CharacterInput gatherInput(double delta) {
        CharacterInput input = new CharacterInput();
        if (isDead) return input;

        if (underAttackTimer > 0) underAttackTimer = Math.max(0.0, underAttackTimer - delta);

        AIState next = currentState.update(this, input, delta);
        if (next != currentState) transitionTo(next);
        return input;
    }

    private void transitionTo(AIState next) {
        if (currentState != null) currentState.exit(this);
        currentState = next;
        currentState.enter(this);
    }

    // ── Target discovery ──────────────────────────────────────────────────────

    /**
     * Scans all nodes in the "characters" group for the nearest one that is
     * hostile to this character's faction. Returns null if none found.
     */
    private Character discoverTarget() {
        String myFaction = characterInfo != null ? characterInfo.faction : Faction.ENEMY;
        float closestDist = Float.MAX_VALUE;
        Character closest = null;
        for (Node node : getTree().getNodesInGroup(new StringName("characters"))) {
            if (!(node instanceof Character c) || c == this) continue;
            String targetFaction = c.characterInfo != null ? c.characterInfo.faction : Faction.NEUTRAL;
            if (!Faction.areHostile(myFaction, targetFaction)) continue;
            float dist = (float) getGlobalPosition().distanceTo(c.getGlobalPosition());
            if (dist < closestDist) { closestDist = dist; closest = c; }
        }
        return closest;
    }

    // ── Methods used by state objects ─────────────────────────────────────────

    public Character getTarget()           { return currentTarget; }
    public void      clearTarget()         { currentTarget = null; }
    public NavigationAgent3D getNavAgent() { return navAgent; }

    /**
     * Discovers a hostile target if none is set, then checks detectionRange and LoS.
     * Returns true when a valid target is visible this frame.
     */
    public boolean canSeeTarget() {
        if (currentTarget == null) currentTarget = discoverTarget();
        if (currentTarget == null) return false;
        float dist = (float) getGlobalPosition().distanceTo(currentTarget.getGlobalPosition());
        if (dist > detectionRange) return false;
        return hasLineOfSight();
    }

    /**
     * Pure LoS check using the dedicated SightRay — never moves the camera.
     * Decoupled from fire direction so LoS accuracy never implies aim accuracy.
     */
    public boolean hasLineOfSight() {
        if (currentTarget == null || sightRay == null) return false;
        Vector3 targetBodyPos = ((Node3D) currentTarget.getNode(
                "MeshRoot/Model/Godot_Chan_Stealth/Skeleton3D/PhysicalBoneSimulator3D/Physical Bone neck_01"))
                .getGlobalPosition();
        sightRay.setTargetPosition(sightRay.toLocal(targetBodyPos));
        sightRay.forceRaycastUpdate();
        if (!sightRay.isColliding()) return false;
        return sightRay.getCollider() instanceof Node3D
                && ((Node3D) sightRay.getCollider()).getOwner() == currentTarget;
    }

    /** Tells the AICameraController to smoothly track {@code target} this frame. */
    public void aimAtPosition(Vector3 target, double delta) {
        if (!(cameraRoot instanceof AICameraController cam) || target == null) return;
        cam.setAimTarget(target);
    }

    /** Clears the camera aim override so it reverts to body-facing direction. */
    public void clearCameraAimTarget() {
        if (cameraRoot instanceof AICameraController cam) cam.clearAimTarget();
    }

    /**
     * Forces AimRay to point at {@code worldTarget} and updates collision immediately.
     * Call just before setting {@code input.fire = true}.
     */
    public void snapAimRay(Vector3 worldTarget) {
        if (aimRay == null || worldTarget == null) return;
        aimRay.setTargetPosition(aimRay.toLocal(worldTarget));
        aimRay.forceRaycastUpdate();
    }

    /**
     * World-space aim position for a single shot toward the current target.
     * Hit: aims at the target's neck. Miss: random offset scaling with distance.
     */
    public Vector3 computeAimTarget(boolean isHit, float hDist) {
        Vector3 base = ((Node3D) currentTarget.getNode(
                "MeshRoot/Model/Godot_Chan_Stealth/Skeleton3D/PhysicalBoneSimulator3D/Physical Bone neck_01"))
                .getGlobalPosition();
        if (isHit) return base;
        float maxOffset = aimScatterRadius * (hDist / 10f);
        float offset    = GD.randf() * maxOffset;
        float angle     = GD.randf() * (float) (Math.PI * 2.0);
        return base.plus(new Vector3(
                offset * (float) Math.cos(angle),
                offset * (float) Math.sin(angle),
                0f));
    }

    /**
     * Picks a new lateral strafe direction perpendicular to the last known target
     * position and resets the strafe timer.
     */
    public void refreshStrafe() {
        if (lastKnownTargetPosition != null) {
            Vector3 toTarget = lastKnownTargetPosition.minus(getGlobalPosition());
            double len = toTarget.length();
            if (len > 0.1) {
                float side = GD.randf() > 0.5f ? 1f : -1f;
                strafeX = side * (float) (toTarget.getZ() / len);
                strafeZ = side * (float) (-toTarget.getX() / len);
                strafeTimer = strafeChangeDuration;
                return;
            }
        }
        float angle = GD.randf() * (float) (Math.PI * 2.0);
        strafeX = (float) Math.cos(angle);
        strafeZ = (float) Math.sin(angle);
        strafeTimer = strafeChangeDuration;
    }

    /** Index of the equipped weapon with ammo and the highest damage, or -1 if all dry. */
    public int selectBestWeapon() {
        if (weaponController == null) return -1;
        int bestIndex = -1;
        float bestDamage = -1f;
        for (int i = 0; i < weaponController.getSlotCount(); i++) {
            if (!weaponController.hasAmmoForWeapon(i)) continue;
            WeaponItem stats = weaponController.getWeaponStats(i);
            if (stats != null && stats.damage > bestDamage) {
                bestDamage = stats.damage; bestIndex = i;
            }
        }
        return bestIndex;
    }

    public boolean hasAnyAmmo() { return selectBestWeapon() >= 0; }

    public boolean isAtAmmoRefill() {
        if (ammoRefill == null) return false;
        return (float) getGlobalPosition().distanceTo(ammoRefill.getGlobalPosition())
                <= AMMO_REFILL_ARRIVAL_THRESHOLD;
    }

    /** Pick a random patrol destination within patrolRadius of spawn. */
    public void setNextPatrolTarget() {
        float angle = GD.randf() * (float) Math.PI * 2.0f;
        float dist  = GD.randf() * patrolRadius;
        navAgent.setTargetPosition(spawnPosition.plus(new Vector3(
                (float) Math.cos(angle) * dist, 0.0f, (float) Math.sin(angle) * dist)));
    }

    // ── Attack-timer helpers ──────────────────────────────────────────────────
    public void    resetAttackTimer()              { attackTimer = 0.0; }
    public void    resetAttackTimer(double value)  { attackTimer = value; }
    public void    advanceAttackTimer(double d)    { attackTimer = Math.max(0.0, attackTimer + d); }
    public boolean isAttackReady()                 { return attackTimer <= 0.0; }

    // ── Lost-target / suppression timer helpers ───────────────────────────────
    public void    resetLostTargetTimer()              { lostTargetTimer = 0.0; }
    public void    advanceLostTargetTimer(double d)    { lostTargetTimer += d; }
    public boolean isTargetLost()                      { return lostTargetTimer >= LOST_TARGET_TIMEOUT; }
    public boolean isSuppressExpired()                 { return lostTargetTimer >= suppressionDuration; }

    /** Suppression shot position — scattered around last known target position. */
    public Vector3 computeSuppressTarget(float hDist) {
        if (lastKnownTargetPosition == null) return null;
        float maxOffset = aimScatterRadius * 2f * (hDist / 10f);
        float offset    = GD.randf() * maxOffset;
        float angle     = GD.randf() * (float) (Math.PI * 2.0);
        return lastKnownTargetPosition.plus(new Vector3(
                offset * (float) Math.cos(angle),
                offset * (float) Math.sin(angle),
                0f));
    }

    // ── Under-attack helpers ──────────────────────────────────────────────────
    public boolean isUnderAttack() { return underAttackTimer > 0.0; }

    // ── Strafe helpers ────────────────────────────────────────────────────────
    public boolean needsStrafeUpdate()           { return strafeTimer <= 0.0; }
    public void    tickStrafeTimer(double delta) { if (strafeTimer > 0) strafeTimer -= delta; }
    public float   getStrafeX()                  { return strafeX; }
    public float   getStrafeZ()                  { return strafeZ; }

    // ── Reaction-timer helpers ────────────────────────────────────────────────
    public void    advanceReactionTimer(double d){ reactionTimer += d; }
    public boolean isReactionReady()             { return reactionTimer >= reactionTime; }
    public void    resetReactionTimer()          { reactionTimer = 0.0; }

    // ── Search-timer helpers ──────────────────────────────────────────────────
    public void    resetSearchTimer()                 { searchTimer = 0.0; }
    public void    advanceSearchTimer(double d)       { searchTimer += d; }
    public boolean isSearchTimedOut(double timeout)   { return searchTimer >= timeout; }

    // ── Last-known-position helpers ───────────────────────────────────────────
    public Vector3 getLastKnownTargetPosition()            { return lastKnownTargetPosition; }
    public void    setLastKnownTargetPosition(Vector3 pos) { lastKnownTargetPosition = pos; }
    public boolean hasLastKnownPosition()                  { return lastKnownTargetPosition != null; }

    // ── Aim-target helpers ────────────────────────────────────────────────────
    public Vector3 getCurrentAimTarget()              { return currentAimTarget; }
    public void    setCurrentAimTarget(Vector3 t)     { currentAimTarget = t; }

    // ── Signal receivers ──────────────────────────────────────────────────────

    /** Connected to the Health node's damaged signal in AICharacter.tscn. */
    @RegisterFunction
    public void onEnemyDamaged(float amount) {
        underAttackTimer = UNDER_ATTACK_DURATION;
        if (currentTarget != null && lastKnownTargetPosition == null)
            lastKnownTargetPosition = new Vector3(currentTarget.getGlobalPosition());
    }

    @RegisterFunction
    @Override
    public void onDied() {
        isDead = true;
        super.onDied();
    }
}
