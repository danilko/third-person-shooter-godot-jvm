package com.openworld.character;

import com.openworld.util.CollisionLayers;
import com.openworld.carrier.vehicle.VehicleWeaponMode;
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
import com.openworld.camera.ControlRotation;
import com.openworld.camera.FPSCameraController;
import com.openworld.camera.TPSCameraController;
import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.control.Controllable;
import com.openworld.control.Controller;
import com.openworld.control.ModalInput;
import com.openworld.control.PlayerController;
import com.openworld.control.UserCommand;
import com.openworld.game.EventBus;
import com.openworld.game.GameManager;
import com.openworld.movement.character.CombatState;
import com.openworld.movement.character.JumpState;
import com.openworld.movement.character.MovementController;
import com.openworld.movement.character.MovementState;
import com.openworld.movement.character.MovementType;
import com.openworld.movement.character.Stance;
import com.openworld.movement.character.StanceName;
import com.openworld.net.NetworkController;
import com.openworld.net.NetworkManager;
import com.openworld.ui.HUDManager;
import com.openworld.weapon.WeaponController;
import com.openworld.weapon.WeaponItem;
import com.openworld.weapon.WeaponType;
import com.openworld.world.SpatialEntityGrid;
import com.openworld.world.manager.ExplosionManager;
import com.openworld.world.manager.ImpactManager;

@RegisterClass
public class Character extends CharacterBody3D implements Controllable, NameplateTarget {

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

    /**
     * Generic {@link NameplateTarget} refresh: emitted whenever name, faction colour, or active
     * weapon changes (faction swap, weapon switch). The nameplate re-reads the getters; health/ammo
     * refresh via the Health/WeaponController node signals.
     */
    @RegisterSignal
    public final Signal0 nameplateChanged = new Signal0(this, new StringName("nameplate_changed"));

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
    // public (not protected): read cross-package by weapon/movement/control collaborators.
    public boolean useWeaponSpread = true;

    // ── Vehicle / drive state ─────────────────────────────────────────────────
    // The outward-visible flags stay here (NetworkController/NetworkManager read them); the
    // transition logic + pre-drive snapshot live in CharacterDriveState (WS5 god-class split).
    public VehicleWeaponMode vehicleWeaponMode = VehicleWeaponMode.NONE;
    /** The Vehicle RigidBody3D this character is currently riding, or null when on foot. */
    public Node currentVehicleNode = null;
    final CharacterDriveState driveState = new CharacterDriveState(this);

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

    public Health healthNode;
    protected Marker3D aimTarget;
    public RayCast3D aimRay;

    protected Node3D cameraRoot;
    protected FPSCameraController fpsCameraController;
    public boolean isFpsMode = false;
    public final ControlRotation controlRotation = new ControlRotation();
    public Camera3D activeCamera;
    protected PhysicalBoneSimulator3D physicalBoneSimulator;

    // ── Visuals scene (B2: mesh-swap foundation) ──────────────────────────────
    protected CharacterVisuals visualsInstance;
    protected MeshConfig meshConfig;

    // ── Ragdoll + death visuals (extracted to CharacterRagdoll — WS5 god-class split) ──
    // The settle-timer state lives in the collaborator; _process pumps it via tickFreeze.
    final CharacterRagdoll ragdoll = new CharacterRagdoll(this);
    // Guards the death visuals (anim-tree off + ragdoll) so they run exactly once, whether the
    // body died authoritatively (onDied) or via a replicated zero-health snapshot (applyReplicatedDeath).
    // Protected: Player.applyReplicatedDeath keys its once-only playerDied emission off it;
    // CharacterRagdoll (same package) reads/sets it from enableDeathVisuals.
    protected boolean deathVisualsApplied  = false;

    // ── Stance cache — populated once in _ready() to avoid repeated NodePath traversals ──
    // Package-private: CharacterRagdoll reads it to drop the active stance collider on death.
    final Map<StanceName, Stance> stanceCache = new EnumMap<>(StanceName.class);

    // ── Tick counter (stamped onto every UserCommand for network ordering) ─────
    protected long currentTick = 0;

    // ── Controller (generates UserCommand each tick) ──────────────────────────
    protected Controller controller;

    // ── Non-authority replication writes (extracted to CharacterReplication — WS5 god-class split) ──
    final CharacterReplication replication = new CharacterReplication(this);

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
        // Register in the spatial grid so AI target discovery can query neighbours in O(k)
        // instead of scanning the whole "characters" group (PLAN.md Part D / D1). Stagger the
        // first re-bucket so bodies spawned together don't all update on the same frame.
        SpatialEntityGrid grid = SpatialEntityGrid.get();
        if (grid != null) grid.register(this, getGlobalPosition());
        gridUpdateTimer = GD.randfRange(0f, (float) GRID_UPDATE_INTERVAL);
        if (hasNode(aimTargetPath)) {
            aimTarget = (Marker3D) getNode(aimTargetPath);
        }
        if (hasNode(aimRayPath)) {
            aimRay = (RayCast3D) getNode(aimRayPath);
            // Exclude our own body from the AimRay. The bone exceptions (addPhysicalBoneExceptions)
            // only cover the ragdoll PhysicalBone3D nodes, not the live stance capsule. Firearms
            // never hit self (spread < 0.5deg), but MeleeItem casts this ray through a +/-25deg cone
            // that can tilt onto the character's own capsule and deal self-damage. Excepting the body
            // here is rotation-independent, so it covers every cone ray (and hardens firearm hitscan).
            aimRay.addException(this);
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

        // Decide our own-nameplate hide by ownership, not the camera — deferred so ownerPeerId is
        // resolved. No-ops for AI and other peers' bodies (they keep their visible nameplate).
        callDeferred(StringNames.toGodotName("applyNameplateVisibility"));
    }

    @RegisterFunction
    public void emitCharacterSpawned() {
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof com.openworld.game.EventBus bus) bus.characterSpawned.emit(this, characterInfo);
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

    /** Current movement direction — read by AIController to build a PASSIVE-tier hold-heading command. */
    public Vector3 getMovementDirection() { return movementDirection; }

    /** Current movement type — read by AIController to build a PASSIVE-tier hold-heading command. */
    public MovementType getCurrentMovementType() { return currentMovementType; }

    // ── Spatial grid bookkeeping (PLAN.md Part D / D1) ───────────────────────
    private static final double GRID_UPDATE_INTERVAL = 0.25;
    private double gridUpdateTimer = 0.0;

    /**
     * Throttled spatial-grid re-bucket. Cheap (a map lookup) while the body stays in its cell;
     * only an actual cell crossing re-hashes. Called from {@link #_physicsProcess} BEFORE the
     * non-authority early return so puppet bodies (NetworkController, e.g. remote players on the
     * host) keep their grid cell current too — host AI must be able to find them.
     */
    protected void updateSpatialCell(double delta) {
        gridUpdateTimer -= delta;
        if (gridUpdateTimer > 0.0) return;
        gridUpdateTimer = GRID_UPDATE_INTERVAL;
        SpatialEntityGrid grid = SpatialEntityGrid.get();
        if (grid != null) grid.move(this, getGlobalPosition());
    }

    // ── Physics loop: gather → apply ─────────────────────────────────────────
    @RegisterFunction
    @Override
    public void _physicsProcess(double delta) {
        updateSpatialCell(delta);
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
        ragdoll.tickFreeze(delta);
    }

    /** Drop out of the spatial grid when this body leaves the tree (death/despawn). */
    @RegisterFunction
    @Override
    public void _exitTree() {
        SpatialEntityGrid grid = SpatialEntityGrid.get();
        if (grid != null) grid.unregister(this);
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

    // ── Replication apply (bodies extracted to CharacterReplication — WS5 god-class split) ──
    //
    // Non-authority bodies never run gatherInput/applyInput/physics (see the early return in
    // _physicsProcess above), so these are the only writes their transform/combat/stance state
    // ever receive. NetworkController calls these each frame; the implementations live in
    // CharacterReplication. Position/velocity are written every frame by the interpolator;
    // combat/stance are discrete and applied once per snapshot.

    /** Direct transform write — safe outside _physicsProcess because non-authority bodies never run move_and_slide. */
    public void applyReplicatedTransform(Vector3 position, Vector3 velocity) {
        replication.applyTransform(position, velocity);
    }

    /** Direct mesh-facing write — counterpart to {@link #getFacingYaw()}. */
    public void applyReplicatedFacing(float yaw) {
        replication.applyFacing(yaw);
    }

    /** Direct spine-IK look write — counterpart to {@link #getAimTargetPosition()}. */
    public void applyReplicatedAim(Vector3 aimPosition) {
        replication.applyAim(aimPosition);
    }

    /** Drives the locomotion blend on a non-authority body from replicated motion. */
    public void applyReplicatedLocomotion(Vector3 velocity, double yaw) {
        replication.applyLocomotion(velocity, yaw);
    }

    /** Applies a replicated movement type (IDLE/WALK/SPRINT) on a puppet. */
    public void applyReplicatedMovementType(int ordinal) {
        replication.applyMovementType(ordinal);
    }

    /** Replays the local applyInput combat/stance transition cascade from a replicated snapshot. */
    public void applyReplicatedCombatAndStance(boolean combat, int stanceOrdinal) {
        replication.applyCombatAndStance(combat, stanceOrdinal);
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

    // ── Vehicle drive state (bodies extracted to CharacterDriveState — WS5 god-class split) ──

    /** Puts the character into the DRIVE_CARRIER state for the given weapon mode. Called by {@code Vehicle.tryEnter}. */
    public void enterDriveState(VehicleWeaponMode mode, Node vehicleNode) {
        driveState.enter(mode, vehicleNode);
    }

    /** Restores the character's pre-drive state. Called by {@code Vehicle.tryExit} before the controller is returned. */
    public void exitDriveState() {
        driveState.exit();
    }

    /**
     * Relays fire/reload commands from the vehicle controller to this character's weapon system
     * each physics frame. Only called when {@code vehicleWeaponMode == PASSENGER_WEAPON}.
     */
    public void applyPassengerWeaponInput(boolean fire, boolean reload, int desiredWeapon, Vector3 aimTargetPos) {
        driveState.applyPassengerWeaponInput(fire, reload, desiredWeapon, aimTargetPos);
    }

    public void setMovementDirection(Vector3 movementDirection) {
        this.movementDirection = movementDirection;
    }

    public void setWeapon(int weapon) {
        changedWeapon.emit(weapon);
        nameplateChanged.emit();
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

    // ── NameplateTarget ─────────────────────────────────────────────────────────
    @Override
    public String getNameplateText() {
        return characterInfo != null ? characterInfo.displayName : "";
    }

    @Override
    public Color getNameplateColor() {
        return Faction.color(characterInfo != null ? characterInfo.faction : null);
    }

    @Override
    public Signal0 getNameplateChangedSignal() {
        return nameplateChanged;
    }

    /**
     * Host-authoritative runtime faction change (D3). Updates this body's faction and, on a
     * networked host, replicates it so every client re-targets identically — target discovery reads
     * {@code characterInfo.faction} fresh each scan, so the change takes effect on the next scan.
     * A client applying an inbound swap (GameManager.applyCharacterFaction) calls this too, but the
     * {@code isServer()} gate stops it echoing back. Emits {@link #nameplateChanged} so cosmetics that
     * key off faction (e.g. the nameplate tint) re-apply on every peer, host and client alike.
     */
    public void setFaction(String faction) {
        if (characterInfo == null || faction == null) return;
        characterInfo.faction = faction;
        nameplateChanged.emit();
        Node netNode = getNodeOrNull("/root/NetworkManager");
        if (netNode instanceof com.openworld.net.NetworkManager net && net.isNetworked() && net.isServer()) {
            net.broadcastWorldEvent(com.openworld.game.GameManager.WORLD_EVENT_FACTION_SWAP,
                    characterInfo.characterId, 0f, java.util.List.of(faction));
        }
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
     * Add ctrl as a child controller, replacing any existing one. The outgoing controller is
     * removed from the tree AND freed — a swapped-out controller is owned here and has no other
     * referent. A caller that wants to keep the old controller (vehicle enter/exit hot-swap) must
     * use {@link #detachController()} instead, which removes without freeing and returns it.
     * Without the free, every swap (puppet spawn → NetworkController, player-leaves → bot
     * AIController, scene PlayerController → NetworkController) orphaned a parentless, unfreed
     * node — the "removed with remove_child() but not freed" leak reported at exit.
     */
    public void attachController(Controller ctrl) {
        if (controller != null && controller != ctrl) {
            Controller old = controller;
            removeChild(old);
            old.queueFree();
        }
        controller = ctrl;
        addChild(ctrl);
    }

    // ── Ragdoll (bodies extracted to CharacterRagdoll — WS5 god-class split) ────

    /**
     * Applies a physics response to a bullet hit — a stagger velocity kick while alive, or a
     * bone impulse on a started ragdoll. Public surface unchanged for ImpactManager /
     * ExplosionManager / Vehicle; delegates to {@link CharacterRagdoll}.
     */
    public void applyHitImpulse(Node hitNode, Vector3 bulletDir, float damage) {
        ragdoll.applyHitImpulse(hitNode, bulletDir, damage);
    }

    /** Apply a physics impulse to a named bone during ragdoll. Delegates to {@link CharacterRagdoll}. */
    public void applyBoneImpulse(String boneName, Vector3 impulse) {
        ragdoll.applyBoneImpulse(boneName, impulse);
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
        if (isLocallyOwnedPlayer()) {
            activeCamera.makeCurrent();
        } else if (netNode instanceof com.openworld.net.NetworkManager net && net.isNetworked()
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

    /**
     * True when this body is the local peer's own player — the one we drive: single-player always,
     * or, when networked, the body this peer is authoritative for ({@code ownerPeerId == localPeerId}).
     * Gated to {@link Player} so it is never true for AI (on the host the AI's ownerPeerId is
     * SERVER_PEER_ID, so it would otherwise report as "ours"). This is the ownership signal — the
     * camera being current is a consequence of it, not the source of truth.
     */
    private boolean isLocallyOwnedPlayer() {
        if (!(this instanceof Player)) return false;
        Node netNode = getNodeOrNull("/root/NetworkManager");
        if (!(netNode instanceof com.openworld.net.NetworkManager net) || !net.isNetworked()) return true;
        return net.isAuthorityFor(characterInfo);
    }

    /**
     * Hide this body's own nameplate — you never see your own. Decided purely by ownership (not by
     * the camera): a Player we locally own hides it; AI and other peers' players keep the
     * Character.tscn default (visible), so networked peers still see each other's plates. Deferred
     * from _ready (like activateCameraIfOwned) so ownerPeerId/characterInfo are resolved first.
     * Replaces the old per-scene `visible = false` override on Player.tscn (which also hid remote
     * players') and the camera-coupled hide inside activateCameraIfOwned.
     */
    @RegisterFunction
    public void applyNameplateVisibility() {
        if (!isLocallyOwnedPlayer()) return;
        Node nameplate = getNodeOrNull("Nameplate");
        if (nameplate instanceof Node3D np) np.setVisible(false);
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
        ragdoll.enableDeathVisuals();
        // Authority-only side effect: the dropped weapons are the host's authoritative world
        // state. A non-authority puppet (applyReplicatedDeath) must NOT drop, or it would spawn
        // orphan, unsynced pickups on the client.
        if (weaponController != null) weaponController.dropAllWeapons();
    }

    /**
     * Non-authority death: a replicated {@code currentHealth} reached zero on a puppet
     * (NetworkController-driven body). Plays the ragdoll visuals only — no weapon drops,
     * no playerDied/game-over, no EventBus kill notification (all emitted once, on the
     * authority, inside {@code Health.applyDamage}). NetworkController stops driving this
     * body's transform after calling it, so the ragdoll isn't dragged by further snapshots.
     */
    public void applyReplicatedDeath() {
        ragdoll.enableDeathVisuals();
    }
}
