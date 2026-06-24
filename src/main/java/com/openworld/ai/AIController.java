package com.openworld.ai;

import com.openworld.ai.AIState;
import com.openworld.ai.character.PatrolState;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.core.Vector3;
import godot.global.GD;
import com.openworld.ai.character.ChaseState;
import com.openworld.ai.character.EscortState;
import com.openworld.ai.character.FleeState;
import com.openworld.character.AICharacter;
import com.openworld.character.Character;
import com.openworld.character.Health;
import com.openworld.control.Controller;
import com.openworld.control.UserCommand;
import com.openworld.movement.character.StanceName;

/**
 * Abstract AI controller — owns all FSM machinery, timers, and memory state.
 *
 * Equivalent to Unreal's AAIController / Source Engine's CAI_BaseNPC scheduling.
 * Lives as a child node of an AICharacter body. Subclasses supply the body
 * reference and initial FSM state.
 *
 * Hardware / sensing methods (NavAgent, SightRay, LoS) stay on the AICharacter
 * body. Memory / state (timers, last-known positions, aim targets) lives here.
 * FSM states receive both body and controller explicitly, making their
 * data sources unambiguous.
 */
@RegisterClass(className = "AIController")
public class AIController extends Controller {

    // ── FSM ───────────────────────────────────────────────────────────────────
    private AIState currentState;

    /** Override in subclasses to return the AICharacter body this controller drives. */
    protected AICharacter getBody() { return null; }

    /** Override in subclasses to supply the initial FSM state. */
    protected AIState initialState() { return PatrolState.INSTANCE; }

    @RegisterFunction
    @Override
    public void _ready() {
        // FSM is started by the owning body's _ready() via start() once
        // body hardware (NavAgent, spawnPosition, etc.) is fully initialized.
        // Children fire _ready() before parents, so body is not ready yet here.
    }

    /** Called by AICharacter._ready() after body initialization is complete. */
    public void start() {
        if (currentState == null) transitionTo(initialState());
    }

    @Override
    public UserCommand gatherInput(double delta) {
        UserCommand cmd = new UserCommand();
        AICharacter body = getBody();
        if (body.isDead()) return cmd;
        // PASSIVE LOD tier (PLAN.md Part D / D2): mid-range AIs skip the FSM entirely — no
        // NavAgent pathfinding, no state transitions, no aim/target work — and just hold their
        // last heading. AnimationController separately skips its AnimationTree writes at this tier.
        if (body.getLodLevel() == AILodLevel.PASSIVE) {
            cmd.movementDirection = body.getMovementDirection();
            cmd.movementType      = body.getCurrentMovementType();
            return cmd;
        }
        if (underAttackTimer > 0) underAttackTimer = Math.max(0.0, underAttackTimer - delta);
        AIState next = currentState.update(body, this, cmd, delta);
        if (next != currentState) transitionTo(next);
        return cmd;
    }

    protected final void transitionTo(AIState next) {
        if (currentState != null) currentState.exit(getBody(), this);
        currentState = next;
        currentState.enter(getBody(), this);
    }

    /**
     * Wipe all FSM memory and return to the initial state. Called when a pooled body is recycled
     * into a fresh spawn (PLAN.md Part E / E1 SpawnPool) so a reused AI does not resume a stale
     * chase/search/flee from its previous life.
     */
    public void resetState() {
        attackTimer = 0.0;
        lostTargetTimer = 0.0;
        reactionTimer = 0.0;
        underAttackTimer = 0.0;
        strafeTimer = 0.0;
        searchTimer = 0.0;
        stillTimer = 0.0;
        stanceHoldTimer = 0.0;
        lastKnownTargetPosition = null;
        currentAimTarget = null;
        lastNavTarget = null;
        escortTargetUnderAttack = false;
        fleeStartPosition = null;
        intendedAttackStance = StanceName.UPRIGHT;
        transitionTo(initialState());
    }

    /**
     * Force the FSM straight into {@link FleeState}, running from a threat at {@code threatPos}
     * (PLAN.md I3c — an evicted civilian driver panicking away from the carjacker). FleeState reads
     * the last-known position for its flee direction, so we seed it here.
     */
    public void forceFlee(Vector3 threatPos) {
        if (threatPos != null) lastKnownTargetPosition = new Vector3(threatPos);
        transitionTo(FleeState.INSTANCE);
    }

    // ── Memory / timers ───────────────────────────────────────────────────────
    // (moved from AICharacter — these are "what the AI remembers", not body capability)

    private static final double LOST_TARGET_TIMEOUT  = 3.0;
    private static final double UNDER_ATTACK_DURATION = 2.5;

    private double attackTimer      = 0.0;
    private double lostTargetTimer  = 0.0;
    private double reactionTimer    = 0.0;
    private double underAttackTimer = 0.0;
    private double strafeTimer      = 0.0;
    private double searchTimer      = 0.0;
    private double stillTimer       = 0.0;

    private float   strafeX        = 0f;
    private float   strafeZ        = 0f;
    private float   strafeFlipSide = 1f;   // alternates ±1 each refresh — no random flips

    private double stanceHoldTimer = 0.0;  // minimum time to hold a stance before switching

    private Vector3 lastKnownTargetPosition = null;
    private Vector3 currentAimTarget        = null;

    private StanceName intendedAttackStance = StanceName.UPRIGHT;

    // ── Attack-timer helpers ──────────────────────────────────────────────────
    public void    resetAttackTimer()             { attackTimer = 0.0; }
    public void    resetAttackTimer(double value) { attackTimer = value; }
    public void    advanceAttackTimer(double d)   { attackTimer = Math.max(0.0, attackTimer + d); }
    public boolean isAttackReady()                { return attackTimer <= 0.0; }

    // ── Lost-target / suppression helpers ─────────────────────────────────────
    public void    resetLostTargetTimer()             { lostTargetTimer = 0.0; }
    public void    advanceLostTargetTimer(double d)   { lostTargetTimer += d; }
    public boolean isTargetLost()                     { return lostTargetTimer >= LOST_TARGET_TIMEOUT; }
    public boolean isSuppressExpired()                { return lostTargetTimer >= getBody().getBehaviorConfig().suppressionDuration; }

    // ── Reaction-timer helpers ────────────────────────────────────────────────
    public void    advanceReactionTimer(double d) { reactionTimer += d; }
    public boolean isReactionReady()              { return reactionTimer >= getBody().getBehaviorConfig().reactionTime; }
    public void    resetReactionTimer()           { reactionTimer = 0.0; }

    // ── Under-attack helpers ──────────────────────────────────────────────────
    public boolean isUnderAttack() { return underAttackTimer > 0.0; }

    /** Called by AICharacter.onEnemyDamaged() when the body takes a hit. */
    public void onDamagedByAttacker(Character attacker) {
        underAttackTimer = UNDER_ATTACK_DURATION;
        if (attacker != null && lastKnownTargetPosition == null)
            lastKnownTargetPosition = new Vector3(attacker.getGlobalPosition());
    }

    // ── Nav-target throttle (Perf 4) ─────────────────────────────────────────
    // Prevents setTargetPosition() from being called 60×/s in ChaseState.
    // Path recompute is only requested when the target moves > 1.5 m.
    private Vector3 lastNavTarget = null;

    public boolean shouldUpdateNav(Vector3 pos) {
        return lastNavTarget == null || (float) lastNavTarget.distanceTo(pos) > 1.5f;
    }
    public void recordNavTarget(Vector3 pos) { lastNavTarget = pos; }
    public void clearNavTarget()             { lastNavTarget = null; }

    // ── Strafe helpers ────────────────────────────────────────────────────────
    public boolean needsStrafeUpdate()           { return strafeTimer <= 0.0; }
    public void    tickStrafeTimer(double delta) { if (strafeTimer > 0) strafeTimer -= delta; }
    public float   getStrafeX()                  { return strafeX; }
    public float   getStrafeZ()                  { return strafeZ; }

    public void refreshStrafe() {
        strafeFlipSide = -strafeFlipSide;  // alternate left / right — predictable, no random flips
        if (lastKnownTargetPosition != null) {
            Vector3 toTarget = lastKnownTargetPosition.minus(getBody().getGlobalPosition());
            double len = toTarget.length();
            if (len > 0.1) {
                strafeX = strafeFlipSide * (float) (toTarget.getZ() / len);
                strafeZ = strafeFlipSide * (float) (-toTarget.getX() / len);
                strafeTimer = getBody().getBehaviorConfig().strafeChangeDuration;
                return;
            }
        }
        // Fallback: no known position yet — use current flip side along world X
        strafeX = strafeFlipSide;
        strafeZ = 0f;
        strafeTimer = getBody().getBehaviorConfig().strafeChangeDuration;
    }

    // ── Still-phase helpers (stop-to-shoot) ──────────────────────────────────
    public void    startStillPhase(double duration) { stillTimer = duration; }
    public void    tickStillTimer(double delta)     { if (stillTimer > 0) stillTimer = Math.max(0.0, stillTimer - delta); }
    public boolean isStillPhase()                   { return stillTimer > 0.0; }

    // ── Search-timer helpers ──────────────────────────────────────────────────
    public void    resetSearchTimer()               { searchTimer = 0.0; }
    public void    advanceSearchTimer(double d)     { searchTimer += d; }
    public boolean isSearchTimedOut(double timeout) { return searchTimer >= timeout; }

    // ── Last-known-position helpers ───────────────────────────────────────────
    public Vector3 getLastKnownTargetPosition()            { return lastKnownTargetPosition; }
    public void    setLastKnownTargetPosition(Vector3 pos) { lastKnownTargetPosition = pos; }
    public boolean hasLastKnownPosition()                  { return lastKnownTargetPosition != null; }
    public void    clearLastKnownPosition()                { lastKnownTargetPosition = null; }

    // ── Aim-target helpers ────────────────────────────────────────────────────
    public Vector3 getCurrentAimTarget()           { return currentAimTarget; }
    public void    setCurrentAimTarget(Vector3 t)  { currentAimTarget = t; }

    // ── Combat-stance tracker + debounce ─────────────────────────────────────
    public StanceName getIntendedAttackStance()             { return intendedAttackStance; }
    public void       setIntendedAttackStance(StanceName s) { intendedAttackStance = s; }
    public boolean    canChangeStance()                     { return stanceHoldTimer <= 0.0; }
    public void       startStanceHoldTimer(double d)        { stanceHoldTimer = d; }
    public void       tickStanceHoldTimer(double delta)     { if (stanceHoldTimer > 0) stanceHoldTimer = Math.max(0.0, stanceHoldTimer - delta); }

    // ── Escort helpers ────────────────────────────────────────────────────────
    // Set when the escort target's Health emits a damage signal. EscortState reads
    // this flag to decide whether to break escort and engage the attacker.
    private boolean escortTargetUnderAttack = false;

    public void    setEscortTargetAttacked()  { escortTargetUnderAttack = true; }
    public boolean isEscortTargetUnderAttack() { return escortTargetUnderAttack; }
    public void    clearEscortTargetAttacked() { escortTargetUnderAttack = false; }

    // ── Flee helpers ──────────────────────────────────────────────────────────
    // FleeState records the position where fleeing started so it can check distance.
    private Vector3 fleeStartPosition = null;

    public void    setFleeStartPosition(Vector3 pos) { fleeStartPosition = pos; }
    public Vector3 getFleeStartPosition()            { return fleeStartPosition; }

    // ── Suppression fire ──────────────────────────────────────────────────────
    public Vector3 computeSuppressTarget(float hDist) {
        if (lastKnownTargetPosition == null) return null;
        float maxOffset = getBody().getBehaviorConfig().aimScatterRadius * 2f * (hDist / 10f);
        float offset    = GD.randf() * maxOffset;
        // Scatter in a full 3D sphere so suppression fire spreads in all directions,
        // not just the XY world plane (which produced visible axis-aligned artefacts).
        float azimuth   = GD.randf() * (float)(Math.PI * 2.0);
        float elevation = (GD.randf() - 0.5f) * (float) Math.PI;
        float cosEl     = (float) Math.cos(elevation);
        return lastKnownTargetPosition.plus(new Vector3(
                offset * cosEl * (float) Math.cos(azimuth),
                offset * (float) Math.sin(elevation),
                offset * cosEl * (float) Math.sin(azimuth)));
    }
}
