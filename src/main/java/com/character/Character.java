package com.character;

import com.util.CollisionLayers;
import com.vehicle.VehicleWeaponMode;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.annotation.RegisterSignal;
import godot.api.*;
import godot.core.*;
import godot.global.GD;

import java.util.ArrayList;
import java.util.EnumMap;
import java.util.Map;
import java.util.UUID;

@RegisterClass
public class Character extends CharacterBody3D implements Controllable {

    // ── Signals ──────────────────────────────────────────────────────────────
    @RegisterSignal
    public final Signal1<JumpState> pressedJump = new Signal1<>(this, new StringName("pressed_jump"));

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
    @Export
    @RegisterProperty
    public Dictionary<String, JumpState> jumpStates = new Dictionary<>(String.class, JumpState.class);

    @Export
    @RegisterProperty
    public Dictionary<String, NodePath> stances = new Dictionary<>(String.class, NodePath.class);

    @Export
    @RegisterProperty
    public Dictionary<String, CombatState> combatStates = new Dictionary<>(String.class, CombatState.class);

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
    public NodePath cameraRootPath = new NodePath("TPSCameraController");

    @RegisterProperty
    @Export
    public NodePath fpsCameraRootPath = new NodePath("FPSCameraController");

    @RegisterProperty
    @Export
    public NodePath aimTargetPath = new NodePath("ActiveCamera/AimRay/AimTarget");

    @RegisterProperty
    @Export
    public NodePath aimRayPath = new NodePath("ActiveCamera/AimRay");

    @RegisterProperty
    @Export
    public NodePath activeCameraPath = new NodePath("ActiveCamera");

    @RegisterProperty
    @Export
    public NodePath physicalBoneSimulatorPath = new NodePath("MeshRoot/Model/Godot_Chan_Stealth/Skeleton3D/PhysicalBoneSimulator3D");

    /**
     * Packed scene whose root is a {@link CharacterVisuals} node containing the mesh,
     * AnimationTree, and PhysicalBoneSimulator3D.  Instantiated in {@code _ready()} and
     * attached to the {@code VisualsMount} Marker3D.  Swapping this one field swaps the
     * entire character appearance; the embedded {@link MeshConfig} wires all dependent
     * component references automatically.
     */
    @RegisterProperty
    @Export
    public PackedScene characterVisuals;

    // ── Protected state ───────────────────────────────────────────────────────
    protected Vector3 movementDirection = new Vector3();
    protected StanceName currentStanceName = StanceName.UPRIGHT;
    protected MovementType currentMovementType = MovementType.IDLE;

    // False for AI-controlled characters whose accuracy is managed by their own system.
    protected boolean useWeaponSpread = true;

    // ── Vehicle / drive state ─────────────────────────────────────────────────
    public VehicleWeaponMode vehicleWeaponMode = VehicleWeaponMode.NONE;
    /** The Vehicle RigidBody3D this character is currently riding, or null when on foot. */
    public Node currentVehicleNode = null;
    private StanceName preDriveStance    = StanceName.UPRIGHT;
    private boolean    preDriveCombat    = false;
    private Vector3    preDriveRotation  = Vector3.Companion.getZERO();

    // ── Combat/stance state (read by NetworkManager._physicsProcess for MSG_SNAPSHOT gather,
    // applied on remote peers via applyReplicatedCombatAndStance — see NetworkController) ──
    @RegisterProperty
    @Export
    public boolean combat = false;

    @RegisterProperty
    @Export
    public int stanceOrdinal = StanceName.UPRIGHT.ordinal();

    @Export
    @RegisterProperty
    public VariantArray<NodePath> headMeshPaths = new VariantArray<>(NodePath.class);

    protected ArrayList<Node3D> headMeshes = new ArrayList<>();

    protected Health healthNode;
    protected Marker3D aimTarget;
    protected RayCast3D aimRay;

    protected Node3D cameraRoot;
    protected FPSCameraController fpsCameraController;
    public boolean isFpsMode = false;
    public final ControlRotation controlRotation = new ControlRotation();
    public Camera3D activeCamera;
    protected PhysicalBoneSimulator3D physicalBoneSimulator;

    // ── Visuals scene (B2: mesh-swap foundation) ──────────────────────────────
    protected CharacterVisuals visualsInstance;
    protected MeshConfig meshConfig;

    // ── Ragdoll freeze state ──────────────────────────────────────────────────
    private double  ragdollFreezeCountdown = -1.0;
    private boolean ragdollFrozen          = false;
    // Guards the death visuals (anim-tree off + ragdoll) so they run exactly once, whether the
    // body died authoritatively (onDied) or via a replicated zero-health snapshot (applyReplicatedDeath).
    // Protected: Player.applyReplicatedDeath keys its once-only playerDied emission off it.
    protected boolean deathVisualsApplied  = false;

    // ── Stance cache — populated once in _ready() to avoid repeated NodePath traversals ──
    private final Map<StanceName, Stance> stanceCache = new EnumMap<>(StanceName.class);

    // ── Tick counter (stamped onto every UserCommand for network ordering) ─────
    protected long currentTick = 0;

    // ── Controller (generates UserCommand each tick) ──────────────────────────
    protected Controller controller;

    // ── UI input lock (set by radial menu / pause / any overlay that must own the mouse) ──
    public boolean inputBlocked = false;

    // ── Lifecycle ─────────────────────────────────────────────────────────────
    @RegisterFunction
    @Override
    public void _ready() {
        healthNode = (Health) getNode("Health");
        if (characterInfo == null) characterInfo = new CharacterInfo();
        if (characterInfo.characterId.isEmpty())
            characterInfo.characterId = UUID.randomUUID().toString();
        addToGroup(new StringName("characters"), false);
        if (hasNode(aimTargetPath)) {
            aimTarget = (Marker3D) getNode(aimTargetPath);
        }
        if (hasNode(aimRayPath)) {
            aimRay = (RayCast3D) getNode(aimRayPath);
        }
        if (hasNode(cameraRootPath)) {
            cameraRoot = (Node3D) getNode(cameraRootPath);
        }
        if (fpsCameraRootPath != null && !fpsCameraRootPath.isEmpty() && hasNode(fpsCameraRootPath)) {
            Node fpsNode = getNode(fpsCameraRootPath);
            if (fpsNode instanceof FPSCameraController fpsCtrl) {
                fpsCameraController = fpsCtrl;
            }
        }
        if (activeCameraPath != null && !activeCameraPath.isEmpty() && hasNode(activeCameraPath)) {
            activeCamera = (Camera3D) getNode(activeCameraPath);
            // Deferred: camera controllers' _ready() runs bottom-up — BEFORE this
            // method assigns activeCamera (see TPSCameraController.setCameraFov's
            // comment) — so any makeCurrent()/clearCurrent() ownership-gating done
            // there sees a null activeCamera and is a silent no-op. Decide and act
            // here instead, once activeCamera AND characterInfo are both resolved,
            // deferred so every sibling _ready() (NetworkManager spawn wiring, etc.)
            // has finished too — same pattern as emitCharacterSpawned below.
            callDeferred(StringNames.toGodotName("activateCameraIfOwned"));
        }

        // ── Visuals instantiation (B2) ─────────────────────────────────────
        if (characterVisuals != null && hasNode("VisualsMount")) {
            Node mount = getNode("VisualsMount");
            Node vis = characterVisuals.instantiate();
            mount.addChild(vis);
            if (vis instanceof CharacterVisuals cv) {
                visualsInstance = cv;
                meshConfig = cv.meshConfig;
            }
            wireFromMeshConfig();
        } else {
            // Legacy fallback: visuals embedded directly in Character scene.
            for (NodePath headMeshPath : headMeshPaths) {
                if (headMeshPath != null && !headMeshPath.isEmpty() && hasNode(headMeshPath)) {
                    headMeshes.add((Node3D) getNode(headMeshPath));
                }
            }
            if (physicalBoneSimulatorPath != null && !physicalBoneSimulatorPath.isEmpty()
                    && hasNode(physicalBoneSimulatorPath)) {
                physicalBoneSimulator = (PhysicalBoneSimulator3D) getNode(physicalBoneSimulatorPath);
                addPhysicalBoneExceptions(physicalBoneSimulator);
            }
        }

        for (Node child : getChildren()) {
            if (child instanceof Controller c) { controller = c; break; }
        }

        for (StanceName sn : StanceName.values()) {
            NodePath sp = stances.get(sn.getKey());
            if (sp == null) continue;
            Node sn2 = getNodeOrNull(sp);
            if (sn2 instanceof Stance s) stanceCache.put(sn, s);
        }

        changedMovementDirection.emit(Vector3.Companion.getBACK());
        setMovementState(MovementType.IDLE);
        // Init: force-emit the starting stance. setStance is now idempotent (no-ops on
        // same stance), so the initial wiring of colliders/animation goes through
        // forceSetStance which always emits changed_stance.
        forceSetStance(currentStanceName);
        setCombatState();
        setWeapon(0);

        // Deferred so all sibling _ready() calls (e.g. HUDManager, GameManager)
        // finish connecting to characterSpawned before this fires. Fires for every
        // character — player and AI — so multi-character systems (C2) can build
        // characterId-keyed registries instead of assuming a single local player.
        callDeferred(StringNames.toGodotName("emitCharacterSpawned"));
    }

    @RegisterFunction
    public void emitCharacterSpawned() {
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof com.game.EventBus bus) bus.characterSpawned.emit(this, characterInfo);
    }

    /**
     * Resolves all mesh-dependent node references from the newly instantiated
     * {@link CharacterVisuals} scene and wires them into sibling components.
     * Called in _ready() immediately after addChild(visualsInstance).
     */
    private void wireFromMeshConfig() {
        if (meshConfig == null || visualsInstance == null) return;

        // ── Physical bone simulator ────────────────────────────────────────
        if (!meshConfig.physicalBoneSimulatorPath.isEmpty()) {
            Node n = visualsInstance.getNodeOrNull(meshConfig.physicalBoneSimulatorPath);
            if (n instanceof PhysicalBoneSimulator3D sim) {
                physicalBoneSimulator = sim;
                addPhysicalBoneExceptions(sim);
            }
        }

        // ── Head meshes (FPS mode visibility) ─────────────────────────────
        headMeshes.clear();
        for (NodePath p : meshConfig.headMeshPaths) {
            if (p == null || p.isEmpty()) continue;
            Node n = visualsInstance.getNodeOrNull(p);
            if (n instanceof Node3D n3d) headMeshes.add(n3d);
        }

        // ── AnimationController ────────────────────────────────────────────
        Node acNode = getNodeOrNull("AnimationController");
        if (acNode instanceof AnimationController ac) {
            if (!meshConfig.animationTreePath.isEmpty()) {
                Node atNode = visualsInstance.getNodeOrNull(meshConfig.animationTreePath);
                if (atNode instanceof AnimationTree at) ac.animationTree = at;
            }
            if (!meshConfig.aimSpineModifierPath.isEmpty()) {
                Node asmNode = visualsInstance.getNodeOrNull(meshConfig.aimSpineModifierPath);
                if (asmNode instanceof LookAtModifier3D asm) {
                    ac.aimSpineModifier = asm;
                    if (aimTarget != null) asm.setTargetNode(aimTarget.getPath());
                }
            }
        }

        // ── WeaponController ──────────────────────────────────────────────
        if (weaponController != null) {
            weaponController.postInitFromVisuals(visualsInstance, meshConfig);
        }

        // ── FPSCameraController ────────────────────────────────────────────
        if (fpsCameraController != null && !meshConfig.fpsCameraMarkerPath.isEmpty()) {
            Node fpsMountNode = visualsInstance.getNodeOrNull(meshConfig.fpsCameraMarkerPath);
            if (fpsMountNode instanceof Node3D fpsMark) fpsCameraController.fpsCameraMount = fpsMark;
        }

        // ── MovementController ─────────────────────────────────────────────
        Node mcNode = getNodeOrNull("MovementController");
        if (mcNode instanceof MovementController mc && !meshConfig.meshRootPath.isEmpty()) {
            Node mr = visualsInstance.getNodeOrNull(meshConfig.meshRootPath);
            if (mr instanceof Node3D mrN) mc.meshRoot = mrN;
        }

        // ── Stance colliders ──────────────────────────────────────────────
        // CharacterVisuals owns the authoring shapes (so sizes can be edited in
        // mesh context). Character.tscn owns the live physics shapes (direct
        // children of CharacterBody3D, required until godot#77937 lands).
        // We copy the Shape3D resource + transform from the visual into the
        // existing character-level collider so both stay in sync.
        if (!meshConfig.stanceColliderPaths.isEmpty()) {
            for (StanceName sn : StanceName.values()) {
                String key = sn.getKey();
                NodePath stancePath = stances.get(key);
                if (stancePath == null || stancePath.isEmpty()) continue;
                Node stanceNode = getNodeOrNull(stancePath);
                if (!(stanceNode instanceof Stance stance)) continue;
                NodePath cp = (NodePath) meshConfig.stanceColliderPaths.get(key);
                if (cp != null && !cp.isEmpty()) {
                    Node cn = visualsInstance.getNodeOrNull(cp);
                    CollisionShape3D charShape = stance.getCollider();
                    if (cn instanceof CollisionShape3D visShape && charShape != null) {
                        if (visShape.getShape() != null) charShape.setShape(visShape.getShape());
                        charShape.setTransform(visShape.getTransform());
                    }
                }
                NodePath rp = (NodePath) meshConfig.stanceRaycastPaths.get(key);
                if (rp != null && !rp.isEmpty()) {
                    Node rn = visualsInstance.getNodeOrNull(rp);
                    RayCast3D charRay = stance.getColRaycast();
                    if (rn instanceof RayCast3D visRay && charRay != null) {
                        charRay.setTransform(visRay.getTransform());
                        charRay.setTargetPosition(visRay.getTargetPosition());
                    }
                }
            }
        }

        // ── Health ────────────────────────────────────────────────────────
        if (healthNode != null) healthNode.meshConfig = meshConfig;
    }

    private void addPhysicalBoneExceptions(PhysicalBoneSimulator3D sim) {
        if (aimRay == null) return;
        for (int i = 0; i < sim.getChildCount(); i++) {
            Node child = sim.getChild(i);
            if (child instanceof PhysicalBone3D bone) aimRay.addException(bone);
        }
    }

    public boolean isCombat() { return combat; }

    /** Current physics-tick counter — read by NetworkManager when gathering MSG_SNAPSHOT. */
    public long getCurrentTick() { return currentTick; }

    /** Current stance ordinal — read by NetworkManager when gathering MSG_SNAPSHOT (mirrors the exported `stanceOrdinal` field). */
    public int getStanceOrdinal() { return stanceOrdinal; }

    /**
     * Visual facing — read by NetworkManager when gathering MSG_SNAPSHOT. Facing lives
     * on MovementController.meshRoot's Y rotation (radians), NOT on this body's own
     * transform: MovementController rotates the mesh independently of movement velocity
     * (e.g. strafing keeps the mesh facing the aim target while the body slides
     * sideways), so the body's rotation alone is never enough to reproduce "which way
     * this character is visually facing" on a remote peer (Round 5 "wrong direction" bug).
     */
    public float getFacingYaw() {
        Node mcNode = getNodeOrNull("MovementController");
        if (mcNode instanceof MovementController mc && mc.meshRoot != null) {
            return (float) (mc.meshRoot.getRotation().getY() + getRotation().getY());
        }
        return 0f;
    }

    /**
     * World-space spine-IK look point — read by NetworkManager when gathering MSG_SNAPSHOT so a
     * remote puppet can reproduce where this character is looking (drives its aimTarget node, which
     * the LookAtModifier3D spine tracks). Falls back to the body origin if no aimTarget marker exists.
     */
    public Vector3 getAimTargetPosition() {
        return aimTarget != null ? aimTarget.getGlobalPosition() : getGlobalPosition();
    }

    /** Current movement type ordinal (IDLE/WALK/SPRINT) — replicated in the snapshot flag bits so a puppet's locomotion blend matches exactly. */
    public int getMovementTypeOrdinal() {
        return currentMovementType != null ? currentMovementType.ordinal() : 0;
    }

    // ── Physics loop: gather → apply ─────────────────────────────────────────
    @RegisterFunction
    @Override
    public void _physicsProcess(double delta) {
        UserCommand cmd;
        if (controller != null) {
            if (!controller.isAuthority()) return; // non-authority: state arrives via MSG_SNAPSHOT — see NetworkController
            // inputBlocked is set by UI overlays (radial menu, pause) that own the mouse.
            // _physicsProcess still runs while blocked — we return an empty command so the
            // character stays still without interrupting physics (gravity, collision).
            cmd = inputBlocked ? new UserCommand() : controller.gatherInput(delta);
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
        if (input.movementDirection.lengthSquared() > 0.001
                || movementDirection.lengthSquared() > 0.001) {
            movementDirection = input.movementDirection;
            changedMovementDirection.emit(movementDirection);
        }
        setMovementState(input.movementType);

        // ── Combat state ───────────────────────────────────────────────────
        // Pressing fire with a melee weapon automatically enters combat stance so
        // the character raises fists without requiring a separate aim button press.
        boolean effectiveCombat = input.wantCombat;
        if (input.fire && weaponController != null) {
            WeaponItem w = weaponController.getCurrentWeaponItem();
            if (w != null && w.getWeaponType() == WeaponType.MELEE) effectiveCombat = true;
        }
        if (effectiveCombat != combat) {
            combat = effectiveCombat;
            setCombatState();
        }

        // ── Aim target ─────────────────────────────────────────────────────
        // Set directly so the spine IK always matches the actual bullet direction.
        // Lerping caused the weapon to visually lag behind the crosshair when
        // strafing: the bullet hit the new point while the weapon still pointed
        // at the previous lerped target.
        if (input.aimTargetPosition != null && aimTarget != null) {
            aimTarget.setGlobalPosition(input.aimTargetPosition);
        }
        
        // ── Fire / not-fire ────────────────────────────────────────────────
        if (input.fire) {
            fireWeapon.emit();
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

        // ── Jump (single ground jump only) ─────────────────────────────────
        // First stand up if crouched/crawling, otherwise launch a ground jump.
        if (input.jump && isOnFloor()) {
            if (!isStanceBlocked(StanceName.UPRIGHT)) {
                if (currentStanceName != StanceName.UPRIGHT) {
                    setStance(StanceName.UPRIGHT);
                } else {
                    JumpState js = jumpStates.get("GroundJump");
                    if (js != null) {
                        pressedJump.emit(js);
                    }
                }
            }
        }

        // ── Stance ─────────────────────────────────────────────────────────
        if (input.desiredStance != null && isOnFloor()) {
            setStance(input.desiredStance);
        }

        // ── Weapon switch / unequip ────────────────────────────────────────
        if (input.wantUnequip) {
            setWeapon(-1);
        } else if (input.desiredWeapon >= 0) {
            setWeapon(input.desiredWeapon);
        }
    }

    // ── Shared helpers ────────────────────────────────────────────────────────
    protected void setCombatState() {
        changedCombatState.emit(combatStates.get(resolveCombatKey(null)));
    }

    // ── Replication apply (non-authority — driven by NetworkController from MSG_SNAPSHOT) ──
    //
    // Non-authority bodies never run gatherInput/applyInput/physics (see the early
    // return in _physicsProcess above), so these are the only writes their transform/
    // combat/stance state ever receive. Position/velocity are written every frame by
    // the interpolator; combat/stance are discrete and applied once per snapshot.

    /** Direct transform write — safe outside _physicsProcess because non-authority bodies never run move_and_slide. */
    public void applyReplicatedTransform(Vector3 position, Vector3 velocity) {
        setGlobalPosition(position);
        setVelocity(velocity);
    }

    /**
     * Direct mesh-facing write — counterpart to {@link #getFacingYaw()}. Sets only
     * meshRoot's Y rotation, preserving whatever X/Z it already has (mirrors how
     * MovementController itself only ever rewrites Y — see MovementController's
     * `setRotation(new Vector3(currentRot.getX(), newY, currentRot.getZ()))`).
     */
    public void applyReplicatedFacing(float yaw) {
        Node mcNode = getNodeOrNull("MovementController");
        if (!(mcNode instanceof MovementController mc) || mc.meshRoot == null) return;
        Vector3 rot = mc.meshRoot.getRotation();
        float localY = yaw - (float) getRotation().getY();
        mc.meshRoot.setRotation(new Vector3(rot.getX(), localY, rot.getZ()));
    }

    /** Direct spine-IK look write — moves the aimTarget marker the LookAtModifier3D tracks, so a puppet's upper body aims where the owner looks (counterpart to {@link #getAimTargetPosition()}). */
    public void applyReplicatedAim(Vector3 aimPosition) {
        if (aimTarget != null && aimPosition != null) aimTarget.setGlobalPosition(aimPosition);
    }

    /**
     * Drives the locomotion blend on a non-authority body from replicated motion. applyInput never
     * runs on a puppet, so {@code changed_movement_direction} / {@code set_cam_rotation} never fire
     * for it — without this the AnimationController's walk/strafe blend stays frozen (the "AI
     * animation not synced" bug). Movement direction is derived from the interpolated horizontal
     * velocity (the same world-space convention the owner's own signal carries); facing yaw is pushed
     * in as camRotation so the combat strafe blend rotates correctly. Movement *type* (walk vs sprint)
     * is applied separately and discretely via {@link #applyReplicatedMovementType(int)}.
     */
    public void applyReplicatedLocomotion(Vector3 velocity, double yaw) {
        Vector3 flat = new Vector3(velocity.getX(), 0, velocity.getZ());
        if (flat.lengthSquared() > 0.01) {
            movementDirection = flat.normalized();
            changedMovementDirection.emit(movementDirection);
        } else if (movementDirection.lengthSquared() > 0.0) {
            // Velocity has settled to ~0: collapse the strafe direction to idle exactly once,
            // instead of holding the last non-zero lean (the "stuck mid-stride" look after a
            // remote body stops). The walk/idle blend itself is driven by the discrete
            // movementType (applyReplicatedMovementType); this clears the combat strafe lean.
            movementDirection = Vector3.Companion.getZERO();
            changedMovementDirection.emit(movementDirection);
        }
        Node acNode = getNodeOrNull("AnimationController");
        if (acNode instanceof AnimationController ac) ac.onSetCamRotation(yaw);
    }

    /** Applies a replicated movement type (IDLE/WALK/SPRINT) on a puppet — emits changed_movement_state so the blend speed/pose updates exactly like the local path. */
    public void applyReplicatedMovementType(int ordinal) {
        MovementType[] types = MovementType.values();
        if (ordinal >= 0 && ordinal < types.length) setMovementState(types[ordinal]);
    }

    /**
     * Replays the same change-detection + signal cascade applyInput uses for combat/
     * stance (see the `effectiveCombat != combat` and `setStance` calls below) so the
     * local-input and replication paths share one "transition into this state" routine
     * rather than drifting apart over time.
     */
    public void applyReplicatedCombatAndStance(boolean combat, int stanceOrdinal) {
        if (combat != this.combat) {
            this.combat = combat;
            setCombatState();
        }
        StanceName[] stances = StanceName.values();
        if (stanceOrdinal >= 0 && stanceOrdinal < stances.length && stanceOrdinal != currentStanceName.ordinal()) {
            setStance(stances[stanceOrdinal]);
        }
    }

    /**
     * Picks the combat-state dictionary key for the given weapon slot.
     * Pass null to use the currently equipped weapon (for state refreshes).
     * Pass a slot index to preview the camera state for a weapon being switched to.
     *
     * Returns "MeleeCombat" when the target weapon is MELEE type and that key exists,
     * otherwise falls back to "Combat" / "NoCombat" as before.
     */
    private String resolveCombatKey(Integer targetSlot) {
        if (!combat) return "NoCombat";
        WeaponItem w = null;
        if (weaponController != null) {
            w = (targetSlot != null) ? weaponController.getWeaponItem(targetSlot)
                                     : weaponController.getCurrentWeaponItem();
        }
        boolean isMelee = w != null && w.getWeaponType() == WeaponType.MELEE;
        return (isMelee && combatStates.get("MeleeCombat") != null) ? "MeleeCombat" : "Combat";
    }


    public void setMovementState(MovementType type) {
        Stance stanceNode = stanceCache.get(currentStanceName);
        if (stanceNode == null) return;
        currentMovementType = type;
        changedMovementState.emit(stanceNode.getMovementState(type));
    }

    /**
     * Pure idempotent stance setter — sets the character to exactly {@code stanceName}.
     * No toggle, no anti-spam timer: the hold-vs-toggle decision lives in the input
     * layer ({@link ModalInput} in {@link PlayerController}) and AI uses its own hold
     * timer. This is also the replication apply path, so it must be idempotent.
     */
    protected void setStance(StanceName stanceName) {
        if (stanceName == currentStanceName) return;
        if (isStanceBlocked(stanceName)) return;

        Stance current = stanceCache.get(currentStanceName);
        if (current != null && current.getCollider() != null) current.getCollider().setDisabled(true);

        currentStanceName = stanceName;
        stanceOrdinal = currentStanceName.ordinal();
        Stance nextStance = stanceCache.get(currentStanceName);
        if (nextStance != null) {
            if (nextStance.getCollider() != null) nextStance.getCollider().setDisabled(false);
            changedStance.emit(nextStance);
        }

        setMovementState(currentMovementType);
    }

    protected boolean isStanceBlocked(StanceName stanceName) {
        Stance s = stanceCache.get(stanceName);
        return (s != null) && s.isBlocked();
    }

    /**
     * Immediately transitions to {@code next} stance, bypassing the anti-spam timer
     * and toggle logic.  Used for forced transitions (vehicle enter/exit) that must
     * happen the same frame regardless of how recently the last stance changed.
     */
    protected void forceSetStance(StanceName next) {
        Stance current = stanceCache.get(currentStanceName);
        if (current != null && current.getCollider() != null) current.getCollider().setDisabled(true);
        currentStanceName = next;
        stanceOrdinal     = next.ordinal();
        Stance nextStance = stanceCache.get(next);
        if (nextStance != null) {
            if (nextStance.getCollider() != null) nextStance.getCollider().setDisabled(false);
            changedStance.emit(nextStance);
        }
    }

    /**
     * Puts the character into the DRIVE_CARRIER state for the given weapon mode.
     * Called by {@code Vehicle.tryEnter}.  Handles collision, stance, combat state,
     * and physics processing — Vehicle only needs to hot-swap the controller after
     * this returns.
     */
    public void enterDriveState(VehicleWeaponMode mode, Node vehicleNode) {
        preDriveStance    = currentStanceName;
        preDriveCombat    = combat;
        preDriveRotation  = getGlobalRotation();
        vehicleWeaponMode = mode;
        currentVehicleNode = vehicleNode;
        setCollisionLayer(0);  // remove from all layers while in vehicle
        forceSetStance(StanceName.DRIVE_CARRIER);
        // Reset the MeshRoot local rotation so the mesh aligns with the body.
        // MovementController normally controls this; since it is disabled the mesh
        // would otherwise stay at whatever facing angle it had when the player stopped.
        Node meshRoot = null;
        if (visualsInstance != null && meshConfig != null && !meshConfig.meshRootPath.isEmpty()) {
            meshRoot = visualsInstance.getNodeOrNull(meshConfig.meshRootPath);
        }
        if (meshRoot == null) meshRoot = getNodeOrNull("MeshRoot");
        if (meshRoot instanceof Node3D mr) mr.setRotation(Vector3.Companion.getZERO());
        // Show character weapon for any mode where the vehicle has no weapon of its own.
        // PASSENGER_WEAPON: character fires their weapon via vehicle camera → must be in combat.
        // NONE: vehicle has no weapon; character still holds their weapon visually while riding.
        // VEHICLE_WEAPON: vehicle fires its own weapon; leave the character's combat state as-is.
        if (mode != VehicleWeaponMode.VEHICLE_WEAPON) {
            combat = true;
            setCombatState();
        }
        setProcess(false);
        setPhysicsProcess(false);
        Node mc = getNodeOrNull("MovementController");
        if (mc != null) mc.setPhysicsProcess(false);
    }

    /**
     * Restores the character's pre-drive state.
     * Called by {@code Vehicle.tryExit} before the controller is returned.
     */
    public void exitDriveState() {
        currentVehicleNode = null;
        // Restore body rotation so MovementController's playerInitRotation stays valid.
        setGlobalRotation(preDriveRotation);
        setCollisionLayer(CollisionLayers.CHARACTER);
        setProcess(true);
        setPhysicsProcess(true);
        Node mc = getNodeOrNull("MovementController");
        if (mc != null) mc.setPhysicsProcess(true);
        forceSetStance(preDriveStance);
        combat = preDriveCombat;
        setCombatState();
        vehicleWeaponMode = VehicleWeaponMode.NONE;
    }

    /**
     * Relays fire/reload commands from the vehicle controller to this character's
     * weapon system each physics frame.  Only called when
     * {@code vehicleWeaponMode == PASSENGER_WEAPON}.
     *
     * @param fire      true while the fire button is held
     * @param reload    true on the frame the reload button is just-pressed
     * @param aimTarget world-space point the vehicle camera is aimed at (unused here;
     *                  the vehicle already injected its AimRay into WeaponController)
     */
    public void applyPassengerWeaponInput(boolean fire, boolean reload, int desiredWeapon, Vector3 aimTargetPos) {
        if (aimTargetPos != null && aimTarget != null) {
            aimTarget.setGlobalPosition(aimTargetPos);
        }
        if (fire) fireWeapon.emit();
        else      notFireWeapon.emit();
        if (reload) reloadWeapon.emit();
        if (desiredWeapon >= 0) setWeapon(desiredWeapon);
    }

    public void setMovementDirection(Vector3 movementDirection) {
        this.movementDirection = movementDirection;
    }

    public void setWeapon(int weapon) {
        changedWeapon.emit(weapon);
        // Preview camera state for the target weapon type immediately so the camera
        // starts lerping to melee/ranged position during the weapon-switch animation.
        if (combat && weapon >= 0) {
            CombatState state = combatStates.get(resolveCombatKey(weapon));
            if (state != null) changedCombatState.emit(state);
        }
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

    /** The controller currently driving this body — null only before _ready() resolves it. */
    public Controller getController() {
        return controller;
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
                    // Remove dead bones from the hitbox layer so living characters' AimRay
                    // and LoS rays pass through corpses. Fixes dead bodies blocking
                    // hasLineOfSight() and performHitscan().
                    bone.setCollisionLayerValue(CollisionLayers.LAYER_HITBOX, false);
                    // Add world to mask so ragdoll bones rest on floor geometry.
                    bone.setCollisionMaskValue(CollisionLayers.LAYER_WORLD, true);
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
        if (activeCamera != null) activeCamera.makeCurrent();
    }

    /**
     * Claims the viewport for this body's camera if — and only if — this body is
     * the one the local peer should be looking through: single-player (no
     * NetworkManager, or not networked) always claims; networked, only the body
     * this peer owns (isAuthorityFor) does. A ServerProxyController-driven body
     * reports isAuthority()=true (the server simulates it) but is NOT locally
     * owned, so gating on ownership — not on the attached controller — is what
     * keeps the host's own view from being stolen by remote bodies it simulates.
     * Deferred from _ready() (see the activeCamera resolution above) so this runs
     * once activeCamera/characterInfo are populated and every other _ready() that
     * might also touch the viewport (e.g. vehicle occupancy) has settled.
     */
    @RegisterFunction
    public void activateCameraIfOwned() {
        if (activeCamera == null) return;
        // isAuthorityFor answers "do I simulate this body" — right for the physics
        // gate, wrong for "is this MY viewpoint": AI characters default ownerPeerId
        // to SERVER_PEER_ID, so on the host (localPeerId == SERVER_PEER_ID) every
        // AI reports isAuthorityFor() == true and would otherwise steal the
        // viewport the instant it spawns. Only a human-driven body (Player) is ever
        // a valid local viewpoint — AICharacter is a sibling type, never a Player.
        if (!(this instanceof Player)) return;
        Node netNode = getNodeOrNull("/root/NetworkManager");
        boolean isLocalView = characterInfo == null
                || !(netNode instanceof com.game.NetworkManager net) || !net.isNetworked()
                || net.isAuthorityFor(characterInfo);
        if (isLocalView) {
            activeCamera.makeCurrent();
        } else if (netNode instanceof com.game.NetworkManager net && net.isNetworked()
                   && controller instanceof PlayerController) {
            // Ghost Player body: World.tscn's pre-placed Player on the client machine.
            // removeLocalPrePlacedPlayer() queues it free on connect, but a physics frame
            // can still run before queueFree resolves. Disable physics and collision here
            // so the body cannot block the local player's movement or occupy physics space.
            setPhysicsProcess(false);
            Node mc = getNodeOrNull("MovementController");
            if (mc != null) mc.setPhysicsProcess(false);
            setCollisionLayer(0);
            setCollisionMask(0);
        }
    }

    public boolean isAlive() {
        return healthNode == null || !healthNode.isDead();
    }

    public void setHeadVisible(boolean visible) {
        for (Node3D headMesh : headMeshes) headMesh.setVisible(visible);
    }

    /**
     * Looks up a physical bone node by bone name within this character's
     * physicalBoneSimulator.  Works with both B2 (bones inside CharacterVisuals)
     * and any legacy embedded setup where physicalBoneSimulator was resolved in _ready().
     */
    public Node3D getPhysicalBoneNode(String boneName) {
        if (physicalBoneSimulator == null) return null;
        Node n = physicalBoneSimulator.getNodeOrNull(new NodePath("Physical Bone " + boneName));
        return (n instanceof Node3D nd) ? nd : null;
    }

    public void applyRecoil(double pitchKick, double yawKick) {
        controlRotation.recoilPitch -= pitchKick;
        controlRotation.recoilYaw   += yawKick;
    }

    public void setCameraMode(boolean fps) {
        isFpsMode = fps;
        // ActiveCamera is the single rendering camera — no makeCurrent() switching needed.
        // Controllers write their proxy transform to it each frame based on isFpsMode.
        setHeadVisible(!fps);
    }

    // ── Override in subclasses ────────────────────────────────────────────────
    @RegisterFunction
    public void onDied() {
        GD.print(getName() + " died");
        enableDeathVisuals();
        // Authority-only side effect: the dropped weapons are the host's authoritative world
        // state. A non-authority puppet (applyReplicatedDeath) must NOT drop, or it would spawn
        // orphan, unsynced pickups on the client.
        if (weaponController != null) weaponController.dropAllWeapons();
    }

    /**
     * The visual half of death — disable the AnimationTree, start the ragdoll, and drop the
     * active stance collider so the corpse settles. Shared by the authoritative {@link #onDied()}
     * path and the non-authority {@link #applyReplicatedDeath()} path so a replicated corpse looks
     * identical without re-running authority-only side effects. Idempotent via {@code deathVisualsApplied}.
     */
    protected void enableDeathVisuals() {
        if (deathVisualsApplied) return;
        deathVisualsApplied = true;

        // Disable animation tree — prefer meshConfig path, fall back to legacy position.
        AnimationTree animationTree = null;
        if (visualsInstance != null && meshConfig != null && !meshConfig.animationTreePath.isEmpty()) {
            Node atNode = visualsInstance.getNodeOrNull(meshConfig.animationTreePath);
            if (atNode instanceof AnimationTree at) animationTree = at;
        }
        if (animationTree == null) animationTree = (AnimationTree) getNodeOrNull("AnimationTree");
        if (animationTree != null) animationTree.setActive(false);

        enableRagdoll();

        // Disabled current stance to let ragdoll take over
        Stance s = stanceCache.get(currentStanceName);
        if (s != null && s.getCollider() != null) s.getCollider().setDisabled(true);
    }

    /**
     * Non-authority death: a replicated {@code currentHealth} reached zero on a puppet
     * (NetworkController-driven body). Plays the ragdoll visuals only — no weapon drops,
     * no playerDied/game-over, no EventBus kill notification (all emitted once, on the
     * authority, inside {@code Health.applyDamage}). NetworkController stops driving this
     * body's transform after calling it, so the ragdoll isn't dragged by further snapshots.
     */
    public void applyReplicatedDeath() {
        enableDeathVisuals();
    }
}
