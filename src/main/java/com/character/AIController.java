package com.character;

import com.character.ai.AIState;
import com.character.ai.PatrolState;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.core.Vector3;
import godot.global.GD;

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
        if (getBody().isDead()) return cmd;
        if (underAttackTimer > 0) underAttackTimer = Math.max(0.0, underAttackTimer - delta);
        AIState next = currentState.update(getBody(), this, cmd, delta);
        if (next != currentState) transitionTo(next);
        return cmd;
    }

    protected final void transitionTo(AIState next) {
        if (currentState != null) currentState.exit(getBody(), this);
        currentState = next;
        currentState.enter(getBody(), this);
    }

    // ── Memory / timers ───────────────────────────────────────────────────────
    // (moved from AICharacter — these are "what the AI remembers", not body capability)

    private static final double LOST_TARGET_TIMEOUT = 3.0;
    private static final double UNDER_ATTACK_DURATION = 2.5;

    double attackTimer      = 0.0;
    double lostTargetTimer  = 0.0;
    double reactionTimer    = 0.0;
    double underAttackTimer = 0.0;
    double strafeTimer      = 0.0;
    double searchTimer      = 0.0;
    double stillTimer       = 0.0;

    float   strafeX        = 0f;
    float   strafeZ        = 0f;
    float   strafeFlipSide = 1f;   // alternates ±1 each refresh — no random flips

    double stanceHoldTimer = 0.0;  // minimum time to hold a stance before switching

    Vector3 lastKnownTargetPosition = null;
    Vector3 currentAimTarget        = null;

    StanceName intendedAttackStance = StanceName.UPRIGHT;

    // ── Attack-timer helpers ──────────────────────────────────────────────────
    public void    resetAttackTimer()             { attackTimer = 0.0; }
    public void    resetAttackTimer(double value) { attackTimer = value; }
    public void    advanceAttackTimer(double d)   { attackTimer = Math.max(0.0, attackTimer + d); }
    public boolean isAttackReady()                { return attackTimer <= 0.0; }

    // ── Lost-target / suppression helpers ─────────────────────────────────────
    public void    resetLostTargetTimer()             { lostTargetTimer = 0.0; }
    public void    advanceLostTargetTimer(double d)   { lostTargetTimer += d; }
    public boolean isTargetLost()                     { return lostTargetTimer >= LOST_TARGET_TIMEOUT; }
    public boolean isSuppressExpired()                { return lostTargetTimer >= getBody().suppressionDuration; }

    // ── Reaction-timer helpers ────────────────────────────────────────────────
    public void    advanceReactionTimer(double d) { reactionTimer += d; }
    public boolean isReactionReady()              { return reactionTimer >= getBody().reactionTime; }
    public void    resetReactionTimer()           { reactionTimer = 0.0; }

    // ── Under-attack helpers ──────────────────────────────────────────────────
    public boolean isUnderAttack() { return underAttackTimer > 0.0; }

    /** Called by AICharacter.onEnemyDamaged() when the body takes a hit. */
    public void onDamagedByAttacker(Character attacker) {
        underAttackTimer = UNDER_ATTACK_DURATION;
        if (attacker != null && lastKnownTargetPosition == null)
            lastKnownTargetPosition = new Vector3(attacker.getGlobalPosition());
    }

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
                strafeTimer = getBody().strafeChangeDuration;
                return;
            }
        }
        // Fallback: no known position yet — use current flip side along world X
        strafeX = strafeFlipSide;
        strafeZ = 0f;
        strafeTimer = getBody().strafeChangeDuration;
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

    // ── Suppression fire ──────────────────────────────────────────────────────
    public Vector3 computeSuppressTarget(float hDist) {
        if (lastKnownTargetPosition == null) return null;
        float maxOffset = getBody().aimScatterRadius * 2f * (hDist / 10f);
        float offset    = GD.randf() * maxOffset;
        float angle     = GD.randf() * (float) (Math.PI * 2.0);
        return lastKnownTargetPosition.plus(new Vector3(
                offset * (float) Math.cos(angle),
                offset * (float) Math.sin(angle),
                0f));
    }
}
