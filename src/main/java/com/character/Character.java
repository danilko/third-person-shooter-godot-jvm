package com.character;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.annotation.RegisterSignal;
import godot.api.*;
import godot.core.*;
import godot.global.GD;

import java.lang.Math;
import java.util.UUID;

@RegisterClass
public class Character extends CharacterBody3D implements Controllable {

    // ── Signals ──────────────────────────────────────────────────────────────
    @RegisterSignal
    public final Signal1<JumpState> pressedJump = new Signal1<>(this, new StringName("pressed_jump"));

    @RegisterSignal
    public final Signal1<RollState> pressedRoll = new Signal1<>(this, new StringName("pressed_roll"));

    @RegisterSignal
    public final Signal1<Stance> changedStance = new Signal1<>(this, new StringName("changed_stance"));

    @RegisterSignal
    public final Signal0 fireWeapon = new Signal0(this, new StringName("fire_weapon"));

    @RegisterSignal
    public final Signal0 notFireWeapon = new Signal0(this, new StringName("not_fire_weapon"));

    @RegisterSignal
    public final Signal1<MovementState> changedMovementState = new Signal1<>(this, new StringName("changed_movement_state"));

    @RegisterSignal
    public final Signal1<Vector3> changedMovementDirection = new Signal1<>(this, new StringName("changed_movement_direction"));

    @RegisterSignal
    public final Signal1<CombatState> changedCombatState = new Signal1<>(this, new StringName("changed_combat_state"));

    @RegisterSignal
    public final Signal1<Integer> changedWeapon = new Signal1<>(this, new StringName("changed_weapon"));

    @RegisterSignal
    public final Signal0 reloadWeapon = new Signal0(this, new StringName("reload_weapon"));

    @RegisterSignal
    public final Signal0 dropWeapon = new Signal0(this, new StringName("drop_weapon"));

    // ── Exports ───────────────────────────────────────────────────────────────
    @RegisterProperty
    public int maxAirJump = 1;

    @Export
    @RegisterProperty
    public Dictionary<String, JumpState> jumpStates = new Dictionary<>(String.class, JumpState.class);

    @Export
    @RegisterProperty
    public Dictionary<String, NodePath> stances = new Dictionary<>(String.class, NodePath.class);

    @Export
    @RegisterProperty
    public Dictionary<String, CombatState> combatStates = new Dictionary<>(String.class, CombatState.class);

    @Export
    @RegisterProperty
    public RollState rollState = null;

    @RegisterProperty
    @Export
    public CharacterInfo characterInfo;

    /**
     * How long (seconds) the ragdoll simulates before all physics are frozen.
     * 0 or less skips the ragdoll entirely and freezes the mesh at the last
     * animation pose — cheapest option for large crowd scenes.
     */
    @RegisterProperty
    @Export
    public float ragdollDuration = 3.0f;

    @RegisterProperty
    @Export
    public WeaponController weaponController;

    @RegisterProperty
    @Export
    public NodePath cameraRootPath = new NodePath("CameraRoot");

    @RegisterProperty
    @Export
    public NodePath aimTargetPath = new NodePath("CameraRoot/Yaw/Pitch/Pivot/SpringArm/Camera/AimTarget");

    @RegisterProperty
    @Export
    public NodePath aimRayPath = new NodePath("CameraRoot/Yaw/Pitch/Pivot/SpringArm/Camera/AimRay");

    @RegisterProperty
    @Export
    public NodePath physicalBoneSimulatorPath = new NodePath("MeshRoot/Model/Godot_Chan_Stealth/Skeleton3D/PhysicalBoneSimulator3D");

    // ── Protected state ───────────────────────────────────────────────────────
    protected int airJumpCounter = 0;
    protected Vector3 movementDirection = new Vector3();
    protected StanceName currentStanceName = StanceName.UPRIGHT;
    protected MovementType currentMovementType = MovementType.IDLE;
    protected boolean isRolling = false;

    // False for AI-controlled characters whose accuracy is managed by their own system.
    protected boolean useWeaponSpread = true;

    // ── Network-synced state (MultiplayerSynchronizer reads these) ────────────
    @RegisterProperty
    @Export
    public boolean combat = false;

    @RegisterProperty
    @Export
    public int stanceOrdinal = StanceName.UPRIGHT.ordinal();

    protected Timer stanceAntispamTimer;
    protected Timer rollTimer;
    protected Health healthNode;
    protected Marker3D aimTarget;
    protected RayCast3D aimRay;

    protected Node3D cameraRoot;
    protected PhysicalBoneSimulator3D physicalBoneSimulator;

    // ── Ragdoll freeze state ──────────────────────────────────────────────────
    private double  ragdollFreezeCountdown = -1.0;
    private boolean ragdollFrozen          = false;

    // ── Tick counter (stamped onto every UserCommand for network ordering) ─────
    protected long currentTick = 0;

    // ── Controller (generates UserCommand each tick) ──────────────────────────
    protected Controller controller;

    // ── Lifecycle ─────────────────────────────────────────────────────────────
    @RegisterFunction
    @Override
    public void _ready() {
        if (hasNode("StanceAntispamTimer")) {
            stanceAntispamTimer = (Timer) getNode("StanceAntispamTimer");
        }
        if (hasNode("RollTimer")) {
            rollTimer = (Timer) getNode("RollTimer");
            if (rollTimer != null && rollState != null) {
                rollTimer.setWaitTime(rollState.getRollDuration());
            }
        }
        healthNode = (Health) getNode("Health");
        if (characterInfo == null) characterInfo = new CharacterInfo();
        if (characterInfo.characterId.isEmpty())
            characterInfo.characterId = UUID.randomUUID().toString();
        addToGroup(new StringName("characters"), false);
        if (hasNode(aimTargetPath)) {
            aimTarget = (Marker3D)  getNode(aimTargetPath);
        }
        if (hasNode(aimRayPath)) {
            aimRay = (RayCast3D) getNode(aimRayPath);

        }

        if (hasNode(cameraRootPath)) {
            cameraRoot = (Node3D) getNode(cameraRootPath);
        }
        if (physicalBoneSimulatorPath != null && !physicalBoneSimulatorPath.isEmpty() && hasNode(physicalBoneSimulatorPath)) {
            physicalBoneSimulator = (PhysicalBoneSimulator3D) getNode(physicalBoneSimulatorPath);

            if (aimRay != null) for (int i = 0; i < physicalBoneSimulator.getChildCount(); i++) {
                Node child = physicalBoneSimulator.getChild(i);
                if (child instanceof PhysicalBone3D bone) {
                   aimRay.addException(bone);
                }
            }
        }

        for (Node child : getChildren()) {
            if (child instanceof Controller c) { controller = c; break; }
        }

        changedMovementDirection.emit(Vector3.Companion.getBACK());
        setMovementState(MovementType.IDLE);
        setStance(currentStanceName);
        setCombatState();
        setWeapon(0);
    }

    public boolean isCombat() { return combat; }

    // ── Physics loop: gather → apply ─────────────────────────────────────────
    @RegisterFunction
    @Override
    public void _physicsProcess(double delta) {
        UserCommand cmd;
        if (controller != null) {
            if (!controller.isAuthority()) return; // non-authority: state via MultiplayerSynchronizer
            cmd = controller.gatherInput(delta);
        } else {
            cmd = gatherInput(delta); // fallback: subclass override
        }
        cmd.tick = currentTick++;
        applyInput(cmd, delta);
    }

    /** Counts down the ragdoll-settle timer and freezes physics when it expires. */
    @RegisterFunction
    @Override
    public void _process(double delta) {
        if (ragdollFreezeCountdown <= 0) return;
        ragdollFreezeCountdown -= delta;
        if (ragdollFreezeCountdown <= 0) freezeRagdoll();
    }

    /** Fallback input path when no Controller child is present. Returns empty command. */
    protected UserCommand gatherInput(double delta) {
        return new UserCommand();
    }

    /**
     * Apply a CharacterInput snapshot to this character's state.
     *
     * All signal emissions and state transitions live here so that any
     * input source (local, AI, network) produces identical results.
     */
    protected void applyInput(UserCommand input, double delta) {

        // ── Movement direction ─────────────────────────────────────────────
        if (input.movementDirection.lengthSquared() > 0.001) {
            movementDirection = input.movementDirection;
            changedMovementDirection.emit(movementDirection);
        }
        setMovementState(input.movementType);

        // ── Floor / jump counter ───────────────────────────────────────────
        if (isOnFloor()) {
            airJumpCounter = 0;
        } else if (airJumpCounter == 0) {
            airJumpCounter = 1;
        }

        // ── Combat state ───────────────────────────────────────────────────
        if (input.wantCombat != combat) {
            combat = input.wantCombat;
            setCombatState();
        }

        // ── Aim target ─────────────────────────────────────────────────────
        if (input.aimTargetPosition != null && aimTarget != null) {
            aimTarget.setGlobalPosition(input.aimTargetPosition);
        }
        
        // ── Fire / not-fire ────────────────────────────────────────────────
        if (!isRolling) {
            if (input.fire) {
                fireWeapon.emit();
            } else {
                notFireWeapon.emit();
            }
        } else {
            notFireWeapon.emit();
        }

        // ── Reload ─────────────────────────────────────────────────────────
        if (input.reload) {
            reloadWeapon.emit();
        }

        // ── Drop ────────────────────────────────────────────────────────────
        if (input.drop) {
            dropWeapon.emit();
        }

        // ── Jump ───────────────────────────────────────────────────────────
        if (input.jump && !isRolling && airJumpCounter <= maxAirJump) {
            if (!isStanceBlocked(StanceName.UPRIGHT)) {
                if (currentStanceName != StanceName.UPRIGHT) {
                    setStance(StanceName.UPRIGHT);
                } else {
                    String jumpName = (airJumpCounter > 0) ? "AirJump" : "GroundJump";
                    JumpState js = jumpStates.get(jumpName);
                    if (js != null) {
                        pressedJump.emit(js);
                    }
                    airJumpCounter++;
                }
            }
        }

        // ── Roll ───────────────────────────────────────────────────────────
        if (input.roll && !isRolling && isOnFloor() &&
                movementDirection.lengthSquared() > 0.001 &&
                (weaponController == null || !weaponController.isWeaponReloading())) {
            if (rollTimer == null || rollTimer.getTimeLeft() <= 0) {
                roll(true);
            }
        }

        // ── Stance ─────────────────────────────────────────────────────────
        if (input.desiredStance != null && isOnFloor() &&
                (rollTimer == null || rollTimer.getTimeLeft() <= 0)) {
            setStance(input.desiredStance);
        }

        // ── Weapon switch ──────────────────────────────────────────────────
        if (input.desiredWeapon >= 0) {
            setWeapon(input.desiredWeapon);
        }
    }

    // ── Shared helpers ────────────────────────────────────────────────────────
    protected void setCombatState() {
        changedCombatState.emit(combatStates.get(combat ? "Combat" : "NoCombat"));
    }

    @RegisterFunction
    public void completedRoll() {
        roll(false);
    }

    protected void roll(boolean isRoll) {
        isRolling = isRoll;

        if (currentStanceName != StanceName.CROUCH) {
            StanceName disabledStanceName = isRoll ? currentStanceName : StanceName.CROUCH;
            StanceName enabledStanceName  = isRoll ? StanceName.CROUCH  : currentStanceName;

            NodePath disabledPath = stances.get(disabledStanceName.getKey());
            if (disabledPath != null) {
                Stance s = (Stance) getNode(disabledPath);
                if (s != null && s.getCollider() != null) s.getCollider().setDisabled(true);
            }

            NodePath enabledPath = stances.get(enabledStanceName.getKey());
            if (enabledPath != null) {
                Stance s = (Stance) getNode(enabledPath);
                if (s != null && s.getCollider() != null) s.getCollider().setDisabled(false);
            }
        }

        if (isRoll) {
            if (rollTimer != null) {
                rollTimer.start();
            }
            pressedRoll.emit(rollState);
        }
    }

    public void setMovementState(MovementType type) {
        NodePath path = stances.get(currentStanceName.getKey());
        if (path == null) return;
        Stance stanceNode = (Stance) getNode(path);
        if (stanceNode == null) return;
        currentMovementType = type;
        changedMovementState.emit(stanceNode.getMovementState(type));
    }

    protected void setStance(StanceName stanceName) {
        if (stanceAntispamTimer != null && stanceAntispamTimer.getTimeLeft() > 0) return;

        if (stanceAntispamTimer != null && getTree() != null) {
            stanceAntispamTimer.start();
        }

        StanceName next = (stanceName == currentStanceName) ? StanceName.UPRIGHT : stanceName;
        if (isStanceBlocked(next)) return;

        NodePath currentPath = stances.get(currentStanceName.getKey());
        if (currentPath != null) {
            Stance s = (Stance) getNode(currentPath);
            if (s != null && s.getCollider() != null) s.getCollider().setDisabled(true);
        }

        currentStanceName = next;
        stanceOrdinal = currentStanceName.ordinal();
        NodePath nextPath = stances.get(currentStanceName.getKey());
        if (nextPath != null) {
            Stance s = (Stance) getNode(nextPath);
            if (s != null) {
                if (s.getCollider() != null) s.getCollider().setDisabled(false);
                changedStance.emit(s);
            }
        }

        setMovementState(currentMovementType);
    }

    protected boolean isStanceBlocked(StanceName stanceName) {
        NodePath path = stances.get(stanceName.getKey());
        if (path == null) return false;
        Stance s = (Stance) getNode(path);
        return (s != null) && s.isBlocked();
    }

    public void setMovementDirection(Vector3 movementDirection) {
        this.movementDirection = movementDirection;
    }

    public void setWeapon(int weapon) {
        changedWeapon.emit(weapon);
    }

    // ── Controllable implementation ───────────────────────────────────────────

    @Override
    public void applyCommand(UserCommand cmd, double delta) {
        applyInput(cmd, delta);
    }

    @Override
    public CharacterInfo getCharacterInfo() {
        return characterInfo;
    }

    /**
     * Remove the current Controller child and return it so the caller can
     * reparent it to a different Controllable (vehicle hot-swap).
     * If no controller is attached, returns null.
     */
    public Controller detachController() {
        if (controller == null) return null;
        Controller ctrl = controller;
        removeChild(ctrl);
        controller = null;
        return ctrl;
    }

    /**
     * Add ctrl as a child controller, replacing any existing one.
     * The outgoing controller is freed unless the caller retains a reference.
     */
    public void attachController(Controller ctrl) {
        if (controller != null) removeChild(controller);
        controller = ctrl;
        addChild(ctrl);
    }

    // ── Ragdoll ───────────────────────────────────────────────────────────────
    protected void enableRagdoll() {
        // Stop Character's own input/apply cycle
        setPhysicsProcess(false);

        // Stop MovementController — it is a separate Node with its own
        // _physicsProcess that applies gravity and calls moveAndSlide().
        // Without this, the CharacterBody3D keeps falling even after death.
        if (hasNode("MovementController")) {
            getNode("MovementController").setPhysicsProcess(false);
        }

        // Disable all CharacterBody3D stance capsules so the frozen corpse
        // shell doesn't block navigation or other characters.
        for (int i = 0; i < getChildCount(); i++) {
            Node child = getChild(i);
            if (child instanceof CollisionShape3D shape) {
                shape.setDisabled(true);
            }
        }

        if (physicalBoneSimulator == null) {
            ragdollFrozen = true; // nothing to freeze later
            return;
        }

        if (ragdollDuration > 0) {
            // Simulate ragdoll briefly so the body tumbles naturally, then freeze.
            for (int i = 0; i < physicalBoneSimulator.getChildCount(); i++) {
                Node child = physicalBoneSimulator.getChild(i);
                if (child instanceof PhysicalBone3D bone) {
                    // Layer 4 (value 8) is the character-detection layer used by SightRay
                    // and AimRay (both collision_mask = 9 = layers 1+4). Removing dead bones
                    // from this layer makes the ragdoll transparent to raycasts from living
                    // characters — fixes dead bodies blocking hasLineOfSight() and
                    // performHitscan(), which caused the "not disappearing" and suppression-
                    // fire-into-dead-body symptoms.
                    bone.setCollisionLayerValue(4, false);
                    // Layer 1 (world) in the MASK means the bone can detect the floor so
                    // the ragdoll physically rests on world geometry.
                    bone.setCollisionMaskValue(1, true);
                }
            }
            physicalBoneSimulator.physicalBonesStartSimulation();
            ragdollFreezeCountdown = ragdollDuration;
        } else {
            // ragdollDuration == 0: skip simulation, freeze at animation pose immediately.
            freezeRagdoll();
        }
    }

    /**
     * Freezes all ragdoll physics and stops the bone simulator.
     *
     * Called automatically after ragdollDuration seconds (via _process), or
     * immediately when ragdollDuration <= 0. After this:
     *   - PhysicalBone3D rigid bodies are frozen in place (no gravity, no collision)
     *   - PhysicalBoneSimulator3D modifier is deactivated
     *   - Skeleton retains the last bone transforms → mesh stays at the frozen pose
     *   - No ongoing physics or modifier processing cost
     */
    private void freezeRagdoll() {
        if (ragdollFrozen) return;
        ragdollFrozen = true;
        setProcess(false);

        if (physicalBoneSimulator == null) return;

        for (int i = 0; i < physicalBoneSimulator.getChildCount(); i++) {
            Node child = physicalBoneSimulator.getChild(i);
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

    // Velocity change per damage point applied to an alive character (m/s per dmg).
    private static final float ALIVE_HIT_VELOCITY_SCALE = 0.05f;
    // Impulse magnitude per damage point applied to the hit ragdoll bone (N·s per dmg).
    private static final float DEATH_BONE_IMPULSE_SCALE = 0.3f;

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
    public void applyHitImpulse(Node hitNode, Vector3 bulletDir, float damage) {
        Vector3 dir = bulletDir.normalized();
        if (isAlive()) {
            setVelocity(getVelocity().plus(dir.times(damage * ALIVE_HIT_VELOCITY_SCALE)));
        } else if (hitNode instanceof PhysicalBone3D bone) {
            bone.applyCentralImpulse(dir.times(damage * DEATH_BONE_IMPULSE_SCALE));
        }
    }

    /**
     * Apply a physics impulse to a named bone during ragdoll.
     * Only has effect when the ragdoll is active (call after enableRagdoll or on death).
     */
    public void applyBoneImpulse(String boneName, Vector3 impulse) {
        if (physicalBoneSimulator == null) return;
        for (int i = 0; i < physicalBoneSimulator.getChildCount(); i++) {
            Node child = physicalBoneSimulator.getChild(i);
            if (child instanceof PhysicalBone3D bone && boneName.equalsIgnoreCase(String.valueOf(bone.getName()))) {
                bone.applyCentralImpulse(impulse);
                return;
            }
        }
    }

    public Node3D getCameraRoot() { return cameraRoot; }

    /**
     * Makes this character's Camera3D the active viewport camera.
     * Called by Vehicle.tryExit() when the player leaves the vehicle.
     */
    public void makeCameraActive() {
        Node camNode = getNodeOrNull("CameraRoot/Yaw/Pitch/Pivot/SpringArm/Camera");
        if (camNode instanceof Camera3D cam) cam.makeCurrent();
    }

    public boolean isAlive() {
        return healthNode == null || !healthNode.isDead();
    }

    // ── Override in subclasses ────────────────────────────────────────────────
    @RegisterFunction
    public void onDied() {
        GD.print(getName() + " died");
        // Disable animation tree
        AnimationTree animationTree = (AnimationTree) getNode("AnimationTree");
        animationTree.setActive(false);

        if (weaponController != null) weaponController.dropAllWeapons();

        enableRagdoll();

        // Disabled current stance to let ragdoll take over
            NodePath enabledPath = stances.get(currentStanceName.getKey());
            if (enabledPath != null) {
                Stance s = (Stance) getNode(enabledPath);
                if (s != null && s.getCollider() != null) s.getCollider().setDisabled(true);
            }
    }
}
