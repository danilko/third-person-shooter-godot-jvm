package com.openworld.character;

import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.*;
import com.openworld.carrier.vehicle.Vehicle;
import godot.core.Callable;
import godot.core.MethodCallable;
import godot.core.NodePath;
import godot.core.StringName;
import godot.core.StringNames;
import godot.core.Vector3;
import com.openworld.ai.AIBehaviorConfig;
import com.openworld.ai.AIController;
import com.openworld.ai.AILodLevel;
import com.openworld.ai.character.AttackState;
import com.openworld.ai.character.EscortState;
import com.openworld.ai.character.FleeState;
import com.openworld.ai.character.RefillAmmoState;
import com.openworld.camera.AICameraController;
import com.openworld.control.CharacterController;
import com.openworld.game.mission.MissionDirector;
import com.openworld.control.Controller;
import com.openworld.control.UserCommand;
import com.openworld.game.PlayerRegistry;
import com.openworld.movement.character.MovementController;
import com.openworld.movement.character.MovementType;
import com.openworld.movement.character.StanceName;
import com.openworld.weapon.WeaponItem;
import com.openworld.weapon.WeaponType;
import com.openworld.world.SpatialEntityGrid;
import com.openworld.world.StimulusManager;

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
@Script(className = "AICharacter")
public class AICharacter extends Character {

    public static final float EYE_HEIGHT        = 1.63f;
    public static final float TARGET_BODY_HEIGHT = 1.05f;

    // ── Behaviour configuration ───────────────────────────────────────────────

    /** Per-AI tuning resource. If null, shared DEFAULTS are used. */
    @Export public AIBehaviorConfig behaviorConfig;

    /** Shared defaults — allocated once; never mutated. */
    private static final AIBehaviorConfig DEFAULTS = new AIBehaviorConfig();

    /**
     * The tuning config, falling back to the shared defaults when none is assigned.
     * Deliberately NOT named {@code getBehaviorConfig} — a JavaBean-shaped getter is merged
     * with the exported {@code behaviorConfig} field into one accessor-bound property, which
     * would make Godot read (and save) DEFAULTS whenever the field is unset.
     */
    public AIBehaviorConfig behaviorConfigOrDefaults() {
        return behaviorConfig != null ? behaviorConfig : DEFAULTS;
    }

    /**
     * World-space Area3D that refills all weapons on entry.
     * Scene-specific node reference — lives here rather than in AIBehaviorConfig.
     */
    @Export public Area3D ammoRefill;

    /**
     * NodePath (from scene root) of the Character to escort in EscortState.
     * Resolved to escortTarget in _ready(). Leave empty for non-escort AIs.
     */
    @Export public NodePath escortTargetPath = new NodePath();

    /**
     * NodePath to this AI's {@link AISquad} for editor-placed squads (PLAN.md E3). Resolved in
     * {@code _ready()}. Zone-spawned AI are assigned a squad programmatically via {@link #setSquad}
     * instead. Leave empty for a solo AI.
     */
    @Export public NodePath squadPath = new NodePath();

    /**
     * True when this AI is a <b>story character</b> — one a mission addresses by
     * {@code characterInfo.characterId} through {@code MissionDirector} (PLAN.md F1). Ticked in the
     * editor for a hand-placed named AI; set by {@code ZoneManager} before {@code addChild} for one
     * spawned from a {@link com.openworld.world.NamedCharacterConfig}.
     *
     * <p>The flag exists because the ID alone cannot answer the question: an ambient AI's id is a
     * random UUID and a named one's is authored, and those are the same type of string. Registration
     * itself has ONE owner either way — {@code _ready()} below — so neither path can forget it.
     */
    @Export public boolean storyCharacter = false;

    /** A mission character, or a hostile that is fighting, always has a plate; otherwise Character's rule. */
    @Override
    public boolean isNameplateRelevant() {
        if (storyCharacter) return true;
        if (isCombat() && characterInfo != null && Faction.areHostile(characterInfo.faction, Faction.PLAYER)) return true;
        return super.isNameplateRelevant();
    }

    /** Runtime squad — shared group awareness (E3). Null = solo. Accessed via {@link #activeSquad()}. */
    private AISquad squad;

    /**
     * Runtime escort target — populated from escortTargetPath in _ready() or set
     * directly via setEscortTarget() from mission code (e.g. MissionDirector).
     */
    public Character escortTarget;

    // ── Sensor throttle constants ─────────────────────────────────────────────
    private static final StringName CHARACTERS_GROUP     = new StringName("characters");
    private static final double     TARGET_SCAN_INTERVAL = 0.4;
    private static final double     LOS_CACHE_INTERVAL   = 0.05;

    // ── Distance-based LOD (PLAN.md Part D / D2) ──────────────────────────────
    // Re-evaluated on the ~2 s lodTimer from nearestPlayerDist():
    //   ACTIVE  (< 80 m)   full FSM + NavAgent + AnimationTree.
    //   PASSIVE (80–200 m) simplified tick: no pathfinding / no FSM transitions (AIController
    //                      returns a hold-heading command) and no AnimationTree writes
    //                      (AnimationController holds the last pose).
    //   FROZEN  (> 200 m)  Character._physicsProcess is skipped entirely. MovementController
    //                      still runs as a separate node, decelerating the AI to rest.
    private static final float LOD_ACTIVE_DIST = 80.0f;
    private static final float LOD_FREEZE_DIST = 200.0f;
    /**
     * Process-global multiplier on the LOD distances, set by the active region (PLAN.md I4
     * {@code RegionConfig.aiLodBias}): a rural region pushes it {@code > 1} (AI stay active farther
     * out), a dense city {@code < 1} (tighter budget). 1.0 = the built-in defaults. Static because
     * the active region is a world-wide property, not per-AI.
     */
    private static float lodDistanceBias = 1.0f;
    private double      lodTimer = 0.0;
    private AILodLevel  lodLevel = AILodLevel.ACTIVE;

    /** Set the world-wide LOD-distance multiplier (ZoneManager.applyRegion). Clamped to a sane floor. */
    public static void setLodDistanceBias(float bias) {
        lodDistanceBias = bias > 0.1f ? bias : 0.1f;
    }

    /** Current LOD tier — read by AIController (FSM gating) and AnimationController (pose gating). */
    public AILodLevel getLodLevel() { return lodLevel; }

    /** {@link #getLodLevel()} ordinal (0 ACTIVE, 1 PASSIVE, 2 FROZEN) for headless checks. */
    @Register
    public int lodLevelNow() { return lodLevel.ordinal(); }

    /** The current target's characterId, "" when there is none — the faction probe's readout (PLAN.md F2). */
    @Register
    public String targetIdNow() {
        Character t = currentTarget;
        return t != null && godot.global.GD.isInstanceValid(t) && t.characterInfo != null && t.characterInfo.characterId != null
                ? t.characterInfo.characterId : "";
    }

    /** The escort target's characterId, "" when there is none — the F3 probe's readout. */
    @Register
    public String escortTargetIdNow() {
        Character t = escortTarget;
        return t != null && godot.global.GD.isInstanceValid(t) && t.characterInfo != null && t.characterInfo.characterId != null
                ? t.characterInfo.characterId : "";
    }

    /** Back-compat shorthand: kept so existing FROZEN-only callers keep working. */
    public boolean isLodFrozen() { return lodLevel == AILodLevel.FROZEN; }

    /**
     * Held ACTIVE whatever the distance (game.EnforcementDispatch's units): a dispatched officer 85 m from the player
     * is on its way TO the player, and the PASSIVE tier would hold its heading and walk it away (measured: 79 -> 165 m).
     */
    public boolean lodPinnedActive;

    // ── Placed AI (PLAN.md 2.2: game.encounter -- an Encounter's members, a building's guards) ──
    /** Hostile to every PLAYER whatever the faction table says (an engaged encounter: a gang crew that has turned on
     *  the players without the whole gang turning). Other AI are judged by the table as usual. */
    public boolean huntsPlayers;
    /** A point it fights FROM (a cover marker, a guard's post): it goes there and holds it instead of strafing, and
     *  will not chase further than {@link #holdLeash} from it. Null = fights anywhere (the default). */
    public Vector3 holdPoint;
    /** How far from {@link #holdPoint} it may chase a target (m); 0 = it never leaves the point. */
    public double holdLeash;
    /** Crouch at the hold point between shots (a low cover: a car, a crate, a wall's end). */
    public boolean holdCrouch;
    /** A patrol ROUTE walked in order and round again, instead of the random walk round the spawn point. */
    public java.util.List<Vector3> patrolRoute;
    private int patrolRouteIndex;
    /** Calm, it stands ON {@link #holdPoint} instead of strolling round its spawn point (a guard's post). */
    public boolean standsAtPost;
    /** Where a calm body stands facing when its walk is done (a guard's post looks out of its marker's -Z). */
    public Vector3 postFacePoint;

    private AILodLevel classifyLod(float nearestPlayer) {
        if (lodPinnedActive) return AILodLevel.ACTIVE;
        if (nearestPlayer > LOD_FREEZE_DIST * lodDistanceBias) return AILodLevel.FROZEN;
        if (nearestPlayer > LOD_ACTIVE_DIST * lodDistanceBias) return AILodLevel.PASSIVE;
        return AILodLevel.ACTIVE;
    }

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
    /** When a pick that weighed an explosive expires (ms; 0 = until the ammo changes): the shared explosive cooldown
     *  (P1e) is a clock, not an ammo event. */
    private long cachedBestUntilMs;

    // ── Vehicle-target tracking ───────────────────────────────────────────────
    private Node cachedTargetVehicle = null;

    // ── Lifecycle ─────────────────────────────────────────────────────────────
    @Register
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
                    MethodCallable.createUnsafe(this, "onAmmoChanged"),
                    godot.core.ConnectFlags.DEFAULT);
        }

        // Resolve escort target from NodePath if provided.
        if (escortTargetPath != null && !escortTargetPath.getPath().isEmpty()) {
            Node owner = getOwner();
            if (owner != null) {
                Node n = owner.getNodeOrNull(escortTargetPath.getPath());
                if (n instanceof Character c) setEscortTarget(c);
            }
        }

        // Resolve squad from NodePath (editor-placed squads); zone-spawned AI use setSquad() instead.
        if (squadPath != null && !squadPath.getPath().isEmpty()) {
            Node n = getNodeOrNull(squadPath);
            if (n instanceof AISquad s) setSquad(s);
        }

        if (controller instanceof AIController aiCtrl) aiCtrl.start();

        // Story AI announce themselves to the director (F1). Registration is here, in the body's own
        // _ready(), so an editor-placed named AI and a zone-spawned one take the identical path.
        if (storyCharacter) {
            // a HAND-PLACED story character killed in this world stays dead (PLAN.md 2.0 / CR3): the scene still
            // carries the node, the ledger says it is gone. A zone-spawned one is never built (ZoneManager.spawnNamed).
            if (characterInfo != null && com.openworld.game.WorldLedger.get().isDead(characterInfo.characterId)) {
                setVisible(false);
                queueFree();
                return;
            }
            MissionDirector director = MissionDirector.get();
            if (director != null) director.registerNamedCharacter(this);
        }
    }

    @Register
    @Override
    public void _exitTree() {
        if (squad != null && godot.global.GD.isInstanceValid(squad)) squad.unregister(this);
        if (storyCharacter) {
            MissionDirector director = MissionDirector.get();
            if (director != null) director.unregisterNamedCharacter(this);
        }
        super._exitTree();
    }

    // ── Squad (E3) ──────────────────────────────────────────────────────────────

    /** The squad if still valid, else null (also nulls a stale ref to a freed squad node). */
    private AISquad activeSquad() {
        if (squad != null && !godot.global.GD.isInstanceValid(squad)) squad = null;
        return squad;
    }

    public AISquad getSquad() { return activeSquad(); }

    /** Assign (or clear) this AI's squad, moving its registration. Safe across recycled reuse. */
    public void setSquad(AISquad s) {
        if (squad == s) return;
        if (squad != null && godot.global.GD.isInstanceValid(squad)) squad.unregister(this);
        squad = s;
        if (squad != null) squad.register(this);
    }

    /**
     * Adopt a target pushed by a squad-mate (PLAN.md E3) without waiting for the next scan: set it as
     * the current target, drop stale bone caches, and seed last-known so the FSM converges even before
     * personal LoS. Faction was already verified by the spotter.
     */
    public void adoptSquadTarget(Character target, Vector3 pos) {
        if (target == null || isDead()) return;
        if (currentTarget != target) {
            currentTarget       = target;
            cachedTargetForBone = null;
            cachedBoneNodes     = null;
            cachedVisibleBone   = null;
            cachedTargetVehicle = null;
            cachedLoS           = false;
            losCacheTimer       = 0;
        }
        if (controller instanceof AIController ai && pos != null) ai.setLastKnownTargetPosition(pos);
    }

    /** Tell squad-mates within alert range about this AI's confirmed target (LoS or being shot). */
    public void broadcastToSquad(Character target, Vector3 pos) {
        AISquad s = activeSquad();
        if (s != null && target != null) s.broadcastSpotted(this, target, pos);
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
                    MethodCallable.createUnsafe(this, "onEscortTargetDamaged"),
                    godot.core.ConnectFlags.DEFAULT);
        }
    }

    /** Called when the escort target's Health emits the hit signal. */
    @Register
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
    @Register
    @Override
    public void _physicsProcess(double delta) {
        if (blindTimer > 0.0) blindTimer = Math.max(0.0, blindTimer - delta);
        lodTimer -= delta;
        if (lodTimer <= 0.0) {
            lodTimer = 2.0;
            lastPlayerDist = nearestPlayerDist();
            AILodLevel next = classifyLod(lastPlayerDist);
            if (next != lodLevel) {
                AILodLevel prev = lodLevel;
                lodLevel = next;
                // Returning to ACTIVE from a tier that didn't run the FSM (FROZEN skips it, PASSIVE
                // holds heading without it): clear stale nav/search state so the AI re-plans from
                // its current position instead of resuming a mid-lunge nav target.
                if (next == AILodLevel.ACTIVE && prev != AILodLevel.ACTIVE
                        && controller instanceof AIController ai) {
                    ai.clearNavTarget();
                    ai.resetSearchTimer();
                }
            }
        }
        if (lodLevel == AILodLevel.FROZEN) return;  // skip entire FSM + animation tick
        // Drop any target/bone references that have been freed or pulled out of the tree (e.g. a
        // zone-streamed body despawned by ZoneManager.unload). Dereferencing such a node's
        // global transform logs "Node not inside tree" and, once it is freed, segfaults — so the
        // FSM must never see a dangling target.
        validateCurrentTarget();
        // PASSIVE: super still runs, but AIController.gatherInput returns a hold-heading command
        // (no NavAgent / FSM) and AnimationController skips its AnimationTree writes.
        super._physicsProcess(delta);
    }

    /**
     * Clears {@link #currentTarget} and all its derived bone caches if the target has been freed or
     * removed from the scene tree. Cheap (a validity + in-tree check) and runs every active frame;
     * the guard is what makes streamed/despawned bodies safe to reference between target scans.
     */
    private void validateCurrentTarget() {
        if (currentTarget == null) return;
        if (!godot.global.GD.isInstanceValid(currentTarget) || !currentTarget.isInsideTree()) {
            currentTarget       = null;
            cachedTargetForBone = null;
            cachedBoneNodes     = null;
            cachedVisibleBone   = null;
            cachedTargetVehicle = null;
            cachedLoS           = false;
        }
    }

    /** The nearest player's distance at the last LOD check (every 2 s); AIController's think budget reads it. */
    private float lastPlayerDist = 0f;

    public float lastPlayerDistance() { return lastPlayerDist; }

    private float nearestPlayerDist() {
        float min = Float.MAX_VALUE;
        Vector3 myPos = getGlobalPosition();
        // O(playerCount) via PlayerRegistry instead of an O(characterCount) group scan +
        // instanceof filter (PLAN.md Part D pre-D1 quick win).
        for (Player p : PlayerRegistry.getPlayers()) {
            if (!godot.global.GD.isInstanceValid(p)) continue;  // defensive: list holds in-tree bodies
            float d = (float) myPos.distanceTo(p.getGlobalPosition());
            if (d < min) min = d;
        }
        return min;  // Float.MAX_VALUE if no players in scene → freeze
    }

    // ── Controller access ─────────────────────────────────────────────────────
    public boolean isDead() { return isDead; }

    public CharacterController getCharacterController() {
        return (controller instanceof CharacterController c) ? c : null;
    }

    /** This body's AI brain, or null on a puppet (a client's copy runs a {@code NetworkController}). */
    public AIController aiController() {
        return (controller instanceof AIController c) ? c : null;
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
    // Scratch list reused across discoverTarget() scans so a grid query allocates nothing per call.
    private final java.util.List<Node> targetQueryScratch = new java.util.ArrayList<>();
    // Set by evaluateCandidate() as an out-param alongside its return value (single-threaded).
    private float candidateDist;

    private Character discoverTarget() {
        String myFaction = characterInfo != null ? characterInfo.faction : Faction.ENEMY;

        // Squad-shared target (E3) takes priority over a personal scan, so a mate keeps converging on
        // a threat a squad-mate spotted even before it can see the threat itself. getSharedTarget()
        // self-clears a dead/freed target, falling back to the scan below.
        AISquad s = activeSquad();
        if (s != null) {
            Character shared = s.getSharedTarget();
            if (shared != null && shared != this && shared.currentVehicleNode == null) {
                String tf = (shared.characterInfo != null && shared.characterInfo.faction != null)
                        ? shared.characterInfo.faction : "";
                if (targets(myFaction, tf, shared)) return shared;
            }
        }

        float closestDist = Float.MAX_VALUE;
        Character closest = null;
        Vector3 myPos = getGlobalPosition();

        // D1: query only the cells overlapping the detection circle instead of the whole
        // "characters" group. Falls back to the group scan when the grid AutoLoad is absent
        // (e.g. minimal test scenes) so behaviour is identical, just slower, without it.
        SpatialEntityGrid grid = SpatialEntityGrid.get();
        if (grid != null) {
            grid.queryRadius(myPos, behaviorConfigOrDefaults().detectionRange, targetQueryScratch);
            for (Node node : targetQueryScratch) {
                Character candidate = evaluateCandidate(node, myFaction, myPos);
                if (candidate != null && candidateDist < closestDist) {
                    closestDist = candidateDist;
                    closest     = candidate;
                }
            }
        } else {
            for (Node node : getTree().getNodesInGroup(CHARACTERS_GROUP)) {
                Character candidate = evaluateCandidate(node, myFaction, myPos);
                if (candidate != null && candidateDist < closestDist) {
                    closestDist = candidateDist;
                    closest     = candidate;
                }
            }
        }
        return closest;
    }

    /** May this AI target {@code c} (faction {@code tf})? The faction table narrowed per target (P1e step 4), or --
     *  for a body that {@link #huntsPlayers} -- any player. */
    private boolean targets(String myFaction, String tf, Character c) {
        if (huntsPlayers && c instanceof Player) return true;
        return Faction.areHostile(myFaction, tf) && com.openworld.game.Hostility.mayTarget(myFaction, c);
    }

    /**
     * Returns the targetable Character for a candidate node — the node itself for an on-foot
     * Character, or the occupant for a Vehicle — when it is a live hostile, else null. On a hit,
     * {@link #candidateDist} is set to the distance used for nearest-selection (vehicle distance is
     * measured to the vehicle, matching the prior behaviour).
     */
    private Character evaluateCandidate(Node node, String myFaction, Vector3 myPos) {
        if (node instanceof Character c) {
            if (c == this || !c.isAlive()) return null;
            // Unknown faction → treated as opponent (empty string is hostile to all named factions).
            String tf = (c.characterInfo != null && c.characterInfo.faction != null)
                    ? c.characterInfo.faction : "";
            if (!targets(myFaction, tf, c)) return null;
            if (c.currentVehicleNode != null) return null;   // vehicle entry handles this
            candidateDist = (float) myPos.distanceTo(c.getGlobalPosition());
            return c;
        } else if (node instanceof Vehicle v) {
            Character occ = v.getOccupant();
            if (occ == null || !occ.isAlive() || !v.isAlive()) return null;
            String tf = (occ.characterInfo != null && occ.characterInfo.faction != null)
                    ? occ.characterInfo.faction : "";
            if (!targets(myFaction, tf, occ)) return null;
            candidateDist = (float) myPos.distanceTo(v.getGlobalPosition());
            return occ;
        }
        return null;
    }

    /**
     * Nearest world position worth investigating that this AI can currently hear (PLAN.md E2): a
     * GUNSHOT from a hostile/unknown faction, or any EXPLOSION / VEHICLE_CRASH, within
     * {@code hearingRadius} (capped by each stimulus's own audible radius). Ignores its own events and
     * allied gunfire. Returns null when nothing relevant is audible — PatrolState uses it to wake into
     * SearchState toward the sound. No-op (null) without the StimulusManager AutoLoad (test scenes).
     */
    public Vector3 hearAlarm() {
        StimulusManager sm = StimulusManager.get();
        if (sm == null) return null;
        float radius = behaviorConfigOrDefaults().hearingRadius;
        Vector3 myPos = getGlobalPosition();
        String myFaction = characterInfo != null ? characterInfo.faction : Faction.ENEMY;
        Vector3 best = null;
        float bestDist = Float.MAX_VALUE;
        for (StimulusManager.Stimulus s : sm.getStimuli()) {
            if (s.source == this) continue;
            boolean investigate = switch (s.type) {
                case GUNSHOT                  -> Faction.areHostile(myFaction, s.sourceFaction);
                case EXPLOSION, VEHICLE_CRASH -> true;
                default                       -> false;
            };
            if (!investigate) continue;
            float heardWithin = Math.min(radius, s.radius);
            float d = (float) myPos.distanceTo(s.origin);
            if (d <= heardWithin && d < bestDist) { bestDist = d; best = s.origin; }
        }
        return best;
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
        if (dist > behaviorConfigOrDefaults().detectionRange) return false;

        float fovDeg = behaviorConfigOrDefaults().detectionFovDeg;
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
        switch (behaviorConfigOrDefaults().aimBodyPart.toUpperCase()) {
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
        if (isBlinded()) { cachedLoS = false; return false; }   // a flashbang: it sees nothing

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
            if (com.openworld.world.SmokeCloud.blocksSight(aimRay.getGlobalPosition(), cabin)) { cachedLoS = false; return false; }
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
            // A smoke cloud (SMO1) hides a bone the way a wall does: the ray would sail through particles.
            if (com.openworld.world.SmokeCloud.blocksSight(aimRay.getGlobalPosition(), bone.getGlobalPosition())) continue;
            aimRay.setTargetPosition(aimRay.toLocal(bone.getGlobalPosition()));
            aimRay.forceRaycastUpdate();
            Node3D seen = aimRay.isColliding() && aimRay.getCollider() instanceof Node3D c ? c : null;
            if (seen != null && isIntactGlass(seen))
                seen = seenPastGlass(aimRay.getCollisionPoint(), bone.getGlobalPosition(), (Node3D) aimRay.getCollider());
            else if (seen != null && SEE_THROUGH_GLASS && com.openworld.world.TrainSystem.get() != null
                    && com.openworld.world.TrainSystem.get().windowAt(seen, aimRay.getCollisionPoint()) != null)
                seen = seenPastGlass(aimRay.getCollisionPoint(), bone.getGlobalPosition(), seen);   // into a train car
            if (seen != null && currentTarget.isAncestorOf(seen)) {
                cachedVisibleBone = bone;
                cachedLoS = true;
                return true;
            }
        }
        cachedLoS = false;
        return false;
    }

    /** An intact shop-window pane (world.Breakable in group glass_pane, PLAN.md 1g g): sight passes, bullets do not. */
    /** Off (env OW_NO_GLASS_SIGHT) = a pane blocks sight like a wall: probe_shop_glass's control. */
    public static final boolean SEE_THROUGH_GLASS = System.getenv("OW_NO_GLASS_SIGHT") == null;

    private static boolean isIntactGlass(Node3D n) {
        if (!SEE_THROUGH_GLASS) return false;
        com.openworld.world.GlassPanes.Pane p = com.openworld.world.GlassPanes.paneOf(n);
        return p != null && !p.broken();
    }

    /**
     * What a sight line meets past a pane of glass it hit at {@code hit}: a query from just beyond the pane to
     * {@code to}, on the aim ray's own mask, excluding that pane (and one more pane behind it). Null = nothing.
     * The shooter's own body is behind the start, so it needs no exclusion.
     */
    private Node3D seenPastGlass(Vector3 hit, Vector3 to, Node3D pane) {
        if (getViewport() == null || getViewport().getWorld3d() == null || !(pane instanceof godot.api.CollisionObject3D co))
            return null;
        var sp = getViewport().getWorld3d().getDirectSpaceState();
        godot.core.VariantArray<godot.core.RID> ex = new godot.core.VariantArray<>(godot.core.RID.class);
        ex.append(co.getRid());
        Vector3 dir = to.minus(hit).normalized();
        Vector3 from = hit.plus(dir.times(0.02));
        for (int k = 0; k < 2; k++) {
            var q = godot.api.PhysicsRayQueryParameters3D.create(from, to, aimRay.getCollisionMask(), ex);
            var r = sp.intersectRay(q);
            if (r == null || r.isEmpty()) return null;
            java.lang.Object c = r.get("collider");
            if (!(c instanceof Node3D n)) return null;
            if (!isIntactGlass(n) || !(n instanceof godot.api.CollisionObject3D nco)) return n;
            ex.append(nco.getRid());
            from = ((Vector3) r.get("position")).plus(dir.times(0.02));
        }
        return null;
    }

    // ── Flashbang blindness (FLA1) ───────────────────────────────────────────

    /** Seconds of blindness left; set by world.FlashBang on the peer that simulates this AI. */
    private double blindTimer = 0.0;

    /** Blind this AI for at least {@code seconds}: it cannot see a target (hasLineOfSight is false) until then. */
    public void blind(double seconds) {
        blindTimer = Math.max(blindTimer, seconds);
        cachedLoS = false;
        losCacheTimer = 0;
    }

    public boolean isBlinded() { return blindTimer > 0.0; }

    /** Probe readout. */
    @Register
    public double blindNow() { return blindTimer; }

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

    /** Off = the control: an officer fires through a player it is not after (probe_engagement_v2 case 1b). */
    public static boolean holdFireOnBystanders = true;
    /** A body within this of the shot's line is "in the line": a capsule's radius plus the miss offset's slack. */
    private static final double LINE_CLEARANCE = 0.7;
    /** Bodies this far PAST the aim point still count: a bullet does not stop where it was aimed. */
    private static final double LINE_OVERSHOOT = 3.0;
    /** Only the line's first stretch is checked; past it the spread is wider than any body anyway. */
    private static final double LINE_REACH = 80.0;
    /** Shots this AI fired / held for a body in the line / fired THROUGH one (the control, hold off) -- probe readouts. */
    public int shotsFired, shotsHeld, shotsThrough;
    @Register public int shotsFiredNow() { return shotsFired; }
    @Register public int shotsHeldNow() { return shotsHeld; }
    @Register public int shotsThroughNow() { return shotsThrough; }

    /**
     * Would a POLICE shot from this AI's aim ray at {@code aimAt} pass a PLAYER it is not after? P1e: per-target
     * hostility kept the police from AIMING at a wanted player's co-op partner, but a miss aimed beside the wanted
     * player still took the partner from 1000 to 195 HP in a 30 s fight. The officer then holds that shot and steps
     * aside. Deliberately narrow (user, 2026-10-15, GTA-style and cheap): gangs are careless, and the police do not
     * hold for civilians or each other -- only an innocent player is protected. The players only (no grid query),
     * then a point-to-segment distance; no ray. A player in a vehicle is left out (the hull).
     */
    public boolean bystanderInLine(Vector3 aimAt) {
        if (aimAt == null || characterInfo == null || !Faction.POLICE.equals(characterInfo.faction)) return false;
        Vector3 from = aimRay != null ? aimRay.getGlobalPosition() : getGlobalPosition().plus(new Vector3(0.0, 1.5, 0.0));
        Vector3 dir = aimAt.minus(from);
        double len = dir.length();
        if (len < 0.5) return false;
        dir = dir.div(len);
        double reach = Math.min(len + LINE_OVERSHOOT, LINE_REACH);
        for (Player c : PlayerRegistry.getPlayers()) {
            if (!godot.global.GD.isInstanceValid(c) || c == currentTarget || !c.isAlive() || c.currentVehicleNode != null) continue;
            if (com.openworld.game.Hostility.mayTarget(Faction.POLICE, c)) continue;
            // the body's centre, about chest height: a standing capsule spans ~0..1.8 m above its origin
            Vector3 p = c.getGlobalPosition().plus(new Vector3(0.0, 1.0, 0.0));
            double along = p.minus(from).dot(dir);
            if (along < 0.3 || along > reach) continue;
            Vector3 closest = from.plus(dir.times(along));
            double dy = Math.abs(p.getY() - closest.getY());
            Vector3 off = p.minus(closest);
            double lateral = Math.sqrt(off.getX() * off.getX() + off.getZ() * off.getZ());
            if (lateral < LINE_CLEARANCE && dy < 1.0) return true;
        }
        return false;
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
        return behaviorConfigOrDefaults().hitChance * (1.0f - moveFactor * behaviorConfigOrDefaults().moveAccuracyPenalty);
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
        float maxOffset = behaviorConfigOrDefaults().aimScatterRadius * (hDist / 10f) + weaponSpreadM;
        float offset    = godot.global.GD.randf() * maxOffset;
        float angle     = godot.global.GD.randf() * (float) (Math.PI * 2.0);
        return base.plus(new Vector3(
                offset * (float) Math.cos(angle),
                offset * (float) Math.sin(angle), 0f));
    }

    // ── Weapon / ammo ─────────────────────────────────────────────────────────

    /** Until this time (engine ms) the unit fights with its melee weapon (or fists) instead of its best weapon:
     *  set by AttackState when a target is in arm's reach while the gun reloads (PLAN.md 1g b). */
    public long meleeFallbackUntilMs = 0;

    /** Held back from attacking: the dispatch has not given this unit an attack TOKEN (PLAN.md 1g b2). It still
     *  closes in, strafes and aims; it does not fire or swing. Always false outside the dispatch. */
    public boolean attackHeld = false;

    /** Fight hand-to-hand for {@code seconds} (the gun's reload was cancelled by the switch; it reloads again after). */
    public void startMeleeFallback(double seconds) {
        meleeFallbackUntilMs = godot.api.Time.getTicksMsec() + (long) (seconds * 1000.0);
        meleeFallbacks++;
    }

    public int meleeFallbacks;

    private int meleeSlot() {
        for (int i = 1; i < weaponController.getSlotCount(); i++) {
            WeaponItem s = weaponController.getWeaponItem(i);
            if (s != null && s.getWeaponType() == WeaponType.MELEE) return i;
        }
        return 0;
    }

    public int selectBestWeapon() {
        if (meleeFallbackUntilMs > 0 && weaponController != null) {
            if (godot.api.Time.getTicksMsec() < meleeFallbackUntilMs) return meleeSlot();
            meleeFallbackUntilMs = 0;
            cachedBestWeapon = -1;
        }
        if (cachedBestWeapon >= 0 && (cachedBestUntilMs == 0 || godot.api.Time.getTicksMsec() < cachedBestUntilMs))
            return cachedBestWeapon;
        if (weaponController == null) { cachedBestWeapon = 0; return 0; }
        int bestIndex = -1;
        float bestDamage = -1f;
        // an explosive (launcher, grenade) is passed over while its area's shared cooldown runs (PLAN.md P1e step 1,
        // weapon.ExplosiveCooldown): the unit fights with its gun meanwhile, and the pick is re-asked in 0.5 s
        boolean explosiveHeld = false;
        Vector3 here = currentTarget != null && godot.global.GD.isInstanceValid(currentTarget)
                ? currentTarget.getGlobalPosition() : getGlobalPosition();   // the incident's area: the target's
        boolean explosiveReady = com.openworld.weapon.ExplosiveCooldown.readyQuiet(here.getX(), here.getZ(), com.openworld.weapon.ExplosiveCooldown.now());
        // a ranged weapon with ammo first; a carried melee weapon (special forces' knife) only when none has any --
        // its close-quarters use is startMeleeFallback's, never the default pick
        for (int pass = 0; pass < 2 && bestIndex < 0; pass++) {
            for (int i = 1; i < weaponController.getSlotCount(); i++) {
                if (!weaponController.hasAmmoForWeapon(i)) continue;
                WeaponItem s = weaponController.getWeaponItem(i);
                if (s == null || (pass == 0 && s.getWeaponType() == WeaponType.MELEE)) continue;
                if (weaponController.firesAiExplosive(s)) {
                    explosiveHeld = true;
                    if (!explosiveReady) continue;
                }
                if (s.damage > bestDamage) { bestDamage = s.damage; bestIndex = i; }
            }
        }
        cachedBestWeapon = bestIndex >= 0 ? bestIndex : 0;
        cachedBestUntilMs = explosiveHeld ? godot.api.Time.getTicksMsec() + 500 : 0;
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
        float configRange = behaviorConfigOrDefaults().attackRange;
        if (weaponController == null) return configRange;
        WeaponItem weapon = weaponController.getWeaponItem(selectBestWeapon());
        if (weapon == null) return configRange;
        return Math.min(configRange, weapon.getEffectiveRange());
    }

    @Register
    public void onAmmoChanged(int magazine, int reserve) { cachedBestWeapon = -1; }

    public boolean isAtAmmoRefill() {
        if (ammoRefill == null) return false;
        return (float) getGlobalPosition().distanceTo(ammoRefill.getGlobalPosition()) <= 1.5f;
    }

    // ── Navigation ────────────────────────────────────────────────────────────

    /** {@code goal} kept within {@link #holdLeash} of {@link #holdPoint} (the same object when there is no hold point
     *  or it is inside the leash). */
    public Vector3 leashed(Vector3 goal) {
        if (!holds() || goal == null) return goal;
        Vector3 d = goal.minus(holdPoint);
        d.setY(0);
        double len = d.length();
        if (len <= holdLeash) return goal;
        if (holdLeash <= 0.01 || len < 1e-3) return new Vector3(holdPoint);
        return holdPoint.plus(d.times(holdLeash / len));
    }

    /** Does it fight from {@link #holdPoint} now? Only while it CARRIES a gun with ammunition, whatever is in its hands
     *  (a calm guard holds its fists; the best-weapon pick may be the baton when nobody is near): a body with only a
     *  knife or a bat has to close in (PLAN.md 2.2). */
    public boolean holds() { return holdPoint != null && carriesLoadedGun(); }

    private boolean carriesLoadedGun() {
        if (weaponController == null) return false;
        for (int i = 0; i < weaponController.slotCount(); i++) {
            WeaponItem w = weaponController.getWeaponItem(i);
            if (w != null && w.getWeaponType() == WeaponType.RANGED && weaponController.hasAmmoForWeapon(i)) return true;
        }
        return false;
    }

    /** Is {@code goal} past the leash of its hold point? */
    public boolean beyondLeash(Vector3 goal) { return goal != null && leashed(goal) != goal; }

    public void setNextPatrolTarget() {
        if (patrolRoute != null && !patrolRoute.isEmpty()) {
            patrolRouteIndex = (patrolRouteIndex + 1) % patrolRoute.size();
            navAgent.setTargetPosition(patrolRoute.get(patrolRouteIndex));
            return;
        }
        if (holdPoint != null && (standsAtPost || holdLeash <= 0)) {
            // a post: it stands on its point while calm (a guard at a gate, a desk)
            navAgent.setTargetPosition(holdPoint);
            return;
        }
        float angle = godot.global.GD.randf() * (float) Math.PI * 2.0f;
        float dist  = godot.global.GD.randf() * behaviorConfigOrDefaults().patrolRadius;
        navAgent.setTargetPosition(spawnPosition.plus(new Vector3(
                (float) Math.cos(angle) * dist, 0.0f, (float) Math.sin(angle) * dist)));
    }

    // ── Signal receivers ──────────────────────────────────────────────────────

    @Register
    public void onEnemyDamaged(float amount) {
        CharacterController ctrl = getCharacterController();
        if (ctrl != null) ctrl.onDamagedByAttacker(currentTarget);
        // Being shot is a confirmed sighting too (E3): rally the squad onto the attacker. The damage
        // signal only carries the amount, so we use currentTarget (the AI's believed attacker) — set
        // when it already sees the shooter, which is the common "shoot one, the squad turns" case.
        if (currentTarget != null) broadcastToSquad(currentTarget, currentTarget.getGlobalPosition());
    }

    /**
     * React to being carjacked (PLAN.md I3c) — called host-side on the ejected driver right after it is
     * unseated and back on foot. {@code AIBehaviorConfig.reactToCarjack} decides the response:
     * <ul>
     *   <li>{@code FLEE} (default, civilian) — panic and run from the carjacker ({@link FleeState}).
     *   <li>{@code FIGHT} (gang/hostile) — flip this body's allegiance to {@code ENEMY} (a targeted,
     *       host-authoritative faction swap replicated over {@code WORLD_EVENT_FACTION_SWAP}) and engage
     *       the carjacker via the normal Attack/Chase path; squad mates can join for free.
     * </ul>
     */
    public void reactToCarjack(Character carjacker) {
        // A dead driver pulled out of the seat has nothing to react with (PLAN.md 0.2).
        if (carjacker == null || isDead || !isAlive() || !(controller instanceof AIController ai)) return;
        if ("FIGHT".equalsIgnoreCase(behaviorConfigOrDefaults().reactToCarjack)) {
            setFaction(Faction.ENEMY);
            adoptSquadTarget(carjacker, carjacker.getGlobalPosition());
        } else {
            ai.forceFlee(carjacker.getGlobalPosition());
        }
    }

    @Register
    @Override
    public void onDied() {
        isDead = true;
        super.onDied();
    }

    /**
     * Re-initialise this body for a (re)spawn — PLAN.md Part E / E1. Called by ZoneManager
     * after the body is (re)added to the tree: repositions it, re-anchors the patrol center to the
     * new position, full-heals, clears all sensor caches + FSM memory, and re-registers in the
     * spatial grid. Safe on a fresh instance too (a harmless re-init over what {@code _ready} did).
     *
     * <p>A pooled body's {@code _ready()} does NOT run again on tree re-entry, so the work
     * {@code _ready} normally does for spawn placement (capturing {@code spawnPosition}) and the
     * grid registration must be redone here explicitly.
     */
    public void activateForSpawn(Vector3 worldPos) {
        setGlobalPosition(worldPos);
        spawnPosition = new Vector3(getGlobalPosition());
        isDead = false;

        currentTarget       = null;
        cachedTargetForBone = null;
        cachedBoneNodes     = null;
        cachedVisibleBone   = null;
        cachedTargetVehicle = null;
        cachedLoS           = false;
        cachedBestWeapon    = -1;
        lastEmittedMoveType   = null;
        lastEmittedMoveStance = null;

        lodLevel        = AILodLevel.ACTIVE;
        lodTimer        = godot.global.GD.randfRange(0f, 2.0f);
        targetScanTimer = godot.global.GD.randfRange(0f, (float) TARGET_SCAN_INTERVAL);
        losCacheTimer   = godot.global.GD.randfRange(0f, (float) LOS_CACHE_INTERVAL);

        // Drop references carried over from the previous life so a recycled body never points at a
        // freed node: the camera's aim target and any escort target (and its Health.hit connection).
        clearCameraAimTarget();
        if (escortTarget != null) setEscortTarget(null);

        if (healthNode != null) healthNode.resetFull();

        SpatialEntityGrid grid = SpatialEntityGrid.get();
        if (grid != null) grid.register(this, getGlobalPosition());

        if (controller instanceof AIController aiCtrl) aiCtrl.resetState();
    }
}
