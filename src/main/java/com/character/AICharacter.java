package com.character;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.*;
import com.vehicle.Vehicle;
import godot.core.Callable;
import godot.core.NodePath;
import godot.core.StringName;
import godot.core.StringNames;
import godot.core.Vector3;

/**
 * AI-controlled character body — hardware and sensing only.
 *
 * The brain (AIController) generates a UserCommand each physics tick; this class
 * owns the body capabilities it needs: navigation, line-of-sight raycasting, aim
 * hardware, weapon selection, and patrol geometry.
 *
 * All per-AI tuning lives in AIBehaviorConfig. Swap a different .tres preset in the
 * inspector to change archetype (soldier, guard, civilian…) without touching code.
 */
@RegisterClass(className = "AICharacter")
public class AICharacter extends Character {

    public static final float EYE_HEIGHT        = 1.4f;
    public static final float TARGET_BODY_HEIGHT = 0.9f;

    // ── Behaviour configuration ───────────────────────────────────────────────

    /** Per-AI tuning resource. If null, shared DEFAULTS are used. */
    @Export @RegisterProperty public AIBehaviorConfig behaviorConfig;

    /** Shared defaults — allocated once; never mutated. */
    private static final AIBehaviorConfig DEFAULTS = new AIBehaviorConfig();

    public AIBehaviorConfig getBehaviorConfig() {
        return behaviorConfig != null ? behaviorConfig : DEFAULTS;
    }

    /**
     * World-space Area3D that refills all weapons on entry.
     * Scene-specific node reference — lives here rather than in AIBehaviorConfig.
     */
    @Export @RegisterProperty public Area3D ammoRefill;

    /**
     * NodePath (from scene root) of the Character to escort in EscortState.
     * Resolved to escortTarget in _ready(). Leave empty for non-escort AIs.
     */
    @Export @RegisterProperty public NodePath escortTargetPath = new NodePath();

    /**
     * Runtime escort target — populated from escortTargetPath in _ready() or set
     * directly via setEscortTarget() from mission code (e.g. MissionDirector).
     */
    public Character escortTarget;

    // ── Sensor throttle constants ─────────────────────────────────────────────
    private static final StringName CHARACTERS_GROUP     = new StringName("characters");
    private static final double     TARGET_SCAN_INTERVAL = 0.4;
    private static final double     LOS_CACHE_INTERVAL   = 0.05;

    // ── Lightweight LOD ───────────────────────────────────────────────────────
    // AIs beyond LOD_FREEZE_DIST from all players skip their entire FSM + animation
    // tick (Character._physicsProcess is not called). MovementController still runs
    // as a separate node, decelerating the AI to rest and holding its last pose.
    private static final float LOD_FREEZE_DIST = 200.0f;
    private double  lodTimer  = 0.0;
    private boolean lodFrozen = false;

    public boolean isLodFrozen() { return lodFrozen; }

    // ── Movement-state dedup (Perf 3) ─────────────────────────────────────────
    // Prevents Character.setMovementState emitting changedMovementState every frame
    // when the (type, stance) pair is unchanged. Not applied to the base class
    // because the player relies on the signal firing even without type changes
    // (combat-speed-factor updates from changedCombatState need a fresh speed apply).
    private MovementType lastEmittedMoveType  = null;
    private StanceName   lastEmittedMoveStance = null;

    @Override
    public void setMovementState(MovementType type) {
        if (type == lastEmittedMoveType && currentStanceName == lastEmittedMoveStance) return;
        lastEmittedMoveType   = type;
        lastEmittedMoveStance = currentStanceName;
        super.setMovementState(type);
    }

    // ── AI hardware ───────────────────────────────────────────────────────────
    private NavigationAgent3D  navAgent;
    private AICameraController aiCamera;

    // ── Body state ────────────────────────────────────────────────────────────
    private boolean   isDead        = false;
    private Character currentTarget;
    private Vector3   spawnPosition;

    // ── Sensor cache ─────────────────────────────────────────────────────────
    private double    targetScanTimer     = 0.0;
    private double    losCacheTimer       = 0.0;
    private boolean   cachedLoS           = false;
    private Character cachedTargetForBone = null;
    private Node3D[]  cachedBoneNodes     = null;
    private Node3D    cachedVisibleBone   = null;

    // ── Best-weapon cache (-1 = stale) ────────────────────────────────────────
    private int cachedBestWeapon = -1;

    // ── Vehicle-target tracking ───────────────────────────────────────────────
    private Node cachedTargetVehicle = null;

    // ── Lifecycle ─────────────────────────────────────────────────────────────
    @RegisterFunction
    @Override
    public void _ready() {
        useWeaponSpread = false;
        super._ready();
        navAgent = (NavigationAgent3D) getNode("NavigationAgent3D");
        if (cameraRoot instanceof AICameraController ac) aiCamera = ac;

        spawnPosition = new Vector3(getGlobalPosition());

        // Stagger scan timers so all AIs don't expire on the same frame.
        targetScanTimer = godot.global.GD.randfRange(0f, (float) TARGET_SCAN_INTERVAL);
        losCacheTimer   = godot.global.GD.randfRange(0f, (float) LOS_CACHE_INTERVAL);
        // Stagger LOD checks too.
        lodTimer = godot.global.GD.randfRange(0f, 2.0f);

        if (weaponController != null) {
            weaponController.ammoChanged.connectUnsafe(
                    Callable.createUnsafe(this, StringNames.toGodotName("onAmmoChanged")),
                    godot.api.Object.ConnectFlags.DEFAULT);
        }

        // Resolve escort target from NodePath if provided.
        if (escortTargetPath != null && !escortTargetPath.getPath().isEmpty()) {
            Node owner = getOwner();
            if (owner != null) {
                Node n = owner.getNodeOrNull(escortTargetPath.getPath());
                if (n instanceof Character c) setEscortTarget(c);
            }
        }

        if (controller instanceof AIController aiCtrl) aiCtrl.start();
    }

    /**
     * Assigns the escort target and connects to its Health.hit signal so
     * EscortState can react immediately when the target takes a hit.
     * Safe to call at runtime from mission code.
     */
    public void setEscortTarget(Character target) {
        escortTarget = target;
        if (target == null) return;
        Node h = target.getNodeOrNull("Health");
        if (h instanceof Health health) {
            health.hit.connectUnsafe(
                    Callable.createUnsafe(this, StringNames.toGodotName("onEscortTargetDamaged")),
                    godot.api.Object.ConnectFlags.DEFAULT);
        }
    }

    /** Called when the escort target's Health emits the hit signal. */
    @RegisterFunction
    public void onEscortTargetDamaged(float amount) {
        if (controller instanceof AIController aiCtrl) aiCtrl.setEscortTargetAttacked();
    }

    /**
     * Lightweight LOD gate. Checks distance to nearest player every 2 s; freezes
     * the AI when all players are beyond LOD_FREEZE_DIST. When frozen, the FSM,
     * all signal emissions, and all AnimationTree writes are skipped entirely.
     * MovementController (_physicsProcess is a separate node) still runs and
     * decelerates the character to rest.
     */
    @RegisterFunction
    @Override
    public void _physicsProcess(double delta) {
        lodTimer -= delta;
        if (lodTimer <= 0.0) {
            lodTimer = 2.0;
            boolean shouldFreeze = nearestPlayerDist() > LOD_FREEZE_DIST;
            if (shouldFreeze != lodFrozen) {
                lodFrozen = shouldFreeze;
                if (!lodFrozen && controller instanceof AIController ai) {
                    // Unfreeze: clear stale nav/search state so AI doesn't resume mid-lunge.
                    ai.clearNavTarget();
                    ai.resetSearchTimer();
                }
            }
        }
        if (lodFrozen) return;  // skip entire FSM + animation tick
        super._physicsProcess(delta);
    }

    private float nearestPlayerDist() {
        float min = Float.MAX_VALUE;
        for (Node n : getTree().getNodesInGroup(CHARACTERS_GROUP)) {
            if (n instanceof Player p) {
                float d = (float) getGlobalPosition().distanceTo(p.getGlobalPosition());
                if (d < min) min = d;
            }
        }
        return min;  // Float.MAX_VALUE if no players in scene → freeze
    }

    // ── Controller access ─────────────────────────────────────────────────────
    public boolean isDead() { return isDead; }

    public CharacterController getCharacterController() {
        return (controller instanceof CharacterController c) ? c : null;
    }

    // ── Sensing / target discovery ────────────────────────────────────────────

    public Character          getTarget()   { return currentTarget; }
    public void               clearTarget() { currentTarget = null; }
    public NavigationAgent3D  getNavAgent() { return navAgent; }

    /**
     * Full O(n) group scan for the nearest live hostile. Scans both on-foot
     * Characters and Vehicle occupants.
     *
     * Null-faction characters (characterInfo == null or faction == null) are treated
     * as opponents so AI always attacks unknown combatants.
     */
    private Character discoverTarget() {
        String myFaction = characterInfo != null ? characterInfo.faction : Faction.ENEMY;
        float closestDist = Float.MAX_VALUE;
        Character closest = null;

        for (Node node : getTree().getNodesInGroup(CHARACTERS_GROUP)) {
            Character candidate = null;
            float dist = Float.MAX_VALUE;

            if (node instanceof Character c) {
                if (c == this || !c.isAlive()) continue;
                // Unknown faction → treated as opponent (empty string is hostile to all named factions).
                String tf = (c.characterInfo != null && c.characterInfo.faction != null)
                        ? c.characterInfo.faction : "";
                if (!Faction.areHostile(myFaction, tf)) continue;
                if (c.currentVehicleNode != null) continue;   // vehicle entry handles this
                dist      = (float) getGlobalPosition().distanceTo(c.getGlobalPosition());
                candidate = c;

            } else if (node instanceof Vehicle v) {
                Character occ = v.getOccupant();
                if (occ == null || !occ.isAlive() || !v.isAlive()) continue;
                String tf = (occ.characterInfo != null && occ.characterInfo.faction != null)
                        ? occ.characterInfo.faction : "";
                if (!Faction.areHostile(myFaction, tf)) continue;
                dist      = (float) getGlobalPosition().distanceTo(v.getGlobalPosition());
                candidate = occ;
            }

            if (candidate != null && dist < closestDist) {
                closestDist = dist;
                closest     = candidate;
            }
        }
        return closest;
    }

    /**
     * Throttled target scan — runs discoverTarget() at most once per TARGET_SCAN_INTERVAL.
     * Always runs the full scan when the timer fires so the AI switches to the nearest
     * threat (e.g. a player walking past a lower-priority target).
     */
    private void tickTargetScan(double delta) {
        targetScanTimer -= delta;
        if (targetScanTimer > 0) return;
        targetScanTimer = TARGET_SCAN_INTERVAL;

        Character previous = currentTarget;
        currentTarget = discoverTarget();
        if (currentTarget != previous) {
            cachedTargetForBone = null;
            cachedBoneNodes     = null;
            cachedVisibleBone   = null;
            cachedTargetVehicle = null;
            cachedLoS           = false;
            losCacheTimer       = 0;
        }
    }

    /** Throttled target refresh. Call from states that need an up-to-date target. */
    public void refreshTarget(double delta) { tickTargetScan(delta); }

    /**
     * Throttled visibility check for patrol/search detection.
     * Includes distance pre-filter and optional FOV cone (detectionFovDeg).
     */
    public boolean canSeeTarget(double delta) {
        tickTargetScan(delta);
        if (currentTarget == null) return false;
        Vector3 myPos = getGlobalPosition();
        float dist = (float) myPos.distanceTo(currentTarget.getGlobalPosition());
        if (dist > getBehaviorConfig().detectionRange) return false;

        float fovDeg = getBehaviorConfig().detectionFovDeg;
        if (fovDeg < 360.0f && movementDirection.lengthSquared() > 0.001f) {
            Vector3 forward  = movementDirection.normalized();
            Vector3 toTarget = currentTarget.getGlobalPosition().minus(myPos).normalized();
            double dotXZ = forward.getX() * toTarget.getX()
                         + forward.getZ() * toTarget.getZ();
            if (dotXZ < Math.cos(Math.toRadians(fovDeg * 0.5))) return false;
        }

        return hasLineOfSight(delta);
    }

    /**
     * Builds the priority-ordered bone list for the current target.
     * Called once per target; result is cached in cachedBoneNodes.
     */
    private void resolveTargetBones() {
        cachedTargetForBone = currentTarget;
        cachedVisibleBone   = null;
        String[] names;
        switch (getBehaviorConfig().aimBodyPart.toUpperCase()) {
            case "HEAD":  names = new String[]{"head_2",   "spine_03", "spine_01"}; break;
            case "BODY":  names = new String[]{"spine_01", "spine_03", "thigh_l" }; break;
            case "LEGS":  names = new String[]{"thigh_l",  "thigh_r",  "spine_01"}; break;
            default:      names = new String[]{"spine_03", "spine_01", "head_2"  }; break; // CHEST
        }
        cachedBoneNodes = new Node3D[names.length];
        for (int i = 0; i < names.length; i++)
            cachedBoneNodes[i] = currentTarget.getPhysicalBoneNode(names[i]);
    }

    /**
     * LoS check with a short result cache (~3 frames at 60 Hz).
     * On-foot targets: walk the priority bone list, stop at first exposed bone.
     * Vehicle targets: cast to vehicle cabin centre.
     */
    public boolean hasLineOfSight(double delta) {
        if (currentTarget == null || aimRay == null) return false;

        Node currentVehicle = currentTarget.currentVehicleNode;
        if (currentVehicle != cachedTargetVehicle) {
            cachedTargetVehicle = currentVehicle;
            cachedVisibleBone   = null;
            losCacheTimer       = 0;
        }

        losCacheTimer -= delta;
        if (losCacheTimer > 0) return cachedLoS;
        losCacheTimer = LOS_CACHE_INTERVAL;

        if (currentVehicle instanceof Node3D vehicleNode) {
            Vector3 cabin = vehicleNode.getGlobalPosition().plus(new Vector3(0f, 0.5f, 0f));
            aimRay.setTargetPosition(aimRay.toLocal(cabin));
            aimRay.forceRaycastUpdate();
            cachedLoS = !aimRay.isColliding()
                    || (aimRay.getCollider() instanceof Node n
                        && (n == vehicleNode || vehicleNode.isAncestorOf(n)));
            return cachedLoS;
        }

        if (currentTarget != cachedTargetForBone) resolveTargetBones();
        if (cachedBoneNodes == null) { cachedLoS = false; return false; }
        cachedVisibleBone = null;
        for (Node3D bone : cachedBoneNodes) {
            if (bone == null) continue;
            aimRay.setTargetPosition(aimRay.toLocal(bone.getGlobalPosition()));
            aimRay.forceRaycastUpdate();
            if (aimRay.isColliding()
                    && aimRay.getCollider() instanceof Node3D n
                    && currentTarget.isAncestorOf(n)) {
                cachedVisibleBone = bone;
                cachedLoS = true;
                return true;
            }
        }
        cachedLoS = false;
        return false;
    }

    // ── Aim hardware ──────────────────────────────────────────────────────────

    public void aimAtPosition(Vector3 target, double delta) {
        if (aiCamera == null || target == null) return;
        aiCamera.setAimTarget(target);
    }

    public void clearCameraAimTarget() {
        if (aiCamera != null) aiCamera.clearAimTarget();
    }

    /** Bypasses the anti-spam timer; used by AttackState for direct stance control. */
    public void forceSetStance(StanceName stanceName) {
        if (isStanceBlocked(stanceName)) return;
        super.forceSetStance(stanceName);
        setMovementState(currentMovementType);
    }

    public void snapAimRay(Vector3 worldTarget) {
        if (aimRay == null || worldTarget == null) return;
        aimRay.setTargetPosition(aimRay.toLocal(worldTarget));
        aimRay.forceRaycastUpdate();
    }

    /**
     * World position to aim at on the current target.
     * Vehicle occupant: vehicle cabin centre. On foot: last confirmed visible bone.
     */
    public Vector3 getAimBonePosition() {
        if (currentTarget.currentVehicleNode instanceof Node3D vn)
            return vn.getGlobalPosition().plus(new Vector3(0f, 0.5f, 0f));
        if (cachedVisibleBone != null) return cachedVisibleBone.getGlobalPosition();
        if (cachedBoneNodes != null && cachedBoneNodes.length > 0 && cachedBoneNodes[0] != null)
            return cachedBoneNodes[0].getGlobalPosition();
        Node3D headBone = currentTarget.getPhysicalBoneNode("head_2");
        return headBone != null ? headBone.getGlobalPosition() : currentTarget.getGlobalPosition();
    }

    /**
     * hitChance reduced proportionally by current speed.
     * Stationary = full hitChance; at 4 m/s = hitChance × (1 − moveAccuracyPenalty).
     */
    public float computeEffectiveHitChance() {
        float moveFactor = Math.min(1.0f, (float) getVelocity().length() / 4.0f);
        return getBehaviorConfig().hitChance * (1.0f - moveFactor * getBehaviorConfig().moveAccuracyPenalty);
    }

    /**
     * Hit → exact aim-bone position. Miss → random scatter:
     *   aimScatterRadius × (hDist/10) + hDist × tan(weaponSpreadDeg)
     */
    public Vector3 computeAimTarget(boolean isHit, float hDist) {
        Vector3 base = getAimBonePosition();
        if (isHit) return base;
        float weaponSpreadM = 0f;
        if (weaponController != null) {
            float spreadDeg = weaponController.getCurrentSpreadDeg();
            weaponSpreadM = hDist * (float) Math.tan(Math.toRadians(spreadDeg));
        }
        float maxOffset = getBehaviorConfig().aimScatterRadius * (hDist / 10f) + weaponSpreadM;
        float offset    = godot.global.GD.randf() * maxOffset;
        float angle     = godot.global.GD.randf() * (float) (Math.PI * 2.0);
        return base.plus(new Vector3(
                offset * (float) Math.cos(angle),
                offset * (float) Math.sin(angle), 0f));
    }

    // ── Weapon / ammo ─────────────────────────────────────────────────────────

    public int selectBestWeapon() {
        if (cachedBestWeapon >= 0) return cachedBestWeapon;
        if (weaponController == null) { cachedBestWeapon = 0; return 0; }
        int bestIndex = -1;
        float bestDamage = -1f;
        for (int i = 1; i < weaponController.getSlotCount(); i++) {
            if (!weaponController.hasAmmoForWeapon(i)) continue;
            WeaponItem s = weaponController.getWeaponItem(i);
            if (s != null && s.damage > bestDamage) { bestDamage = s.damage; bestIndex = i; }
        }
        cachedBestWeapon = bestIndex >= 0 ? bestIndex : 0;
        return cachedBestWeapon;
    }

    /**
     * True when the selected weapon can actually be fired — including the permanent
     * fist (slot 0, isInfiniteAmmo). selectBestWeapon() deliberately skips slot 0 when
     * ranking *preferred* weapons (it's the fallback, not a pick), so checking
     * `selectBestWeapon() > 0` here would wrongly mark a fist-only AI as "out of ammo"
     * and route it to RefillAmmoState/FleeState forever instead of letting it brawl.
     */
    public boolean hasAnyAmmo() {
        return weaponController != null && weaponController.hasAmmoForWeapon(selectBestWeapon());
    }

    /**
     * Engagement range to use for Attack-state transitions: the smaller of the
     * behaviour config's general attackRange and the selected weapon's effective
     * range. Without this a melee AI (weaponRange ~1.5 m) would try to fight from
     * AIBehaviorConfig.attackRange away — strafing and "shooting" at empty air
     * instead of closing the distance to where its weapon can actually connect.
     */
    /** True when the AI's selected weapon is melee/fist — used to switch off ranged-style strafing. */
    public boolean isMeleeEngagement() {
        if (weaponController == null) return false;
        WeaponItem weapon = weaponController.getWeaponItem(selectBestWeapon());
        return weapon != null && weapon.getWeaponType() == WeaponType.MELEE;
    }

    public float getEffectiveAttackRange() {
        float configRange = getBehaviorConfig().attackRange;
        if (weaponController == null) return configRange;
        WeaponItem weapon = weaponController.getWeaponItem(selectBestWeapon());
        if (weapon == null) return configRange;
        return Math.min(configRange, weapon.getEffectiveRange());
    }

    @RegisterFunction
    public void onAmmoChanged(int magazine, int reserve) { cachedBestWeapon = -1; }

    public boolean isAtAmmoRefill() {
        if (ammoRefill == null) return false;
        return (float) getGlobalPosition().distanceTo(ammoRefill.getGlobalPosition()) <= 1.5f;
    }

    // ── Navigation ────────────────────────────────────────────────────────────

    public void setNextPatrolTarget() {
        float angle = godot.global.GD.randf() * (float) Math.PI * 2.0f;
        float dist  = godot.global.GD.randf() * getBehaviorConfig().patrolRadius;
        navAgent.setTargetPosition(spawnPosition.plus(new Vector3(
                (float) Math.cos(angle) * dist, 0.0f, (float) Math.sin(angle) * dist)));
    }

    // ── Signal receivers ──────────────────────────────────────────────────────

    @RegisterFunction
    public void onEnemyDamaged(float amount) {
        CharacterController ctrl = getCharacterController();
        if (ctrl != null) ctrl.onDamagedByAttacker(currentTarget);
    }

    @RegisterFunction
    @Override
    public void onDied() {
        isDead = true;
        super.onDied();
    }
}
