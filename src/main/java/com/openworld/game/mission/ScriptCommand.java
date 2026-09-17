package com.openworld.game.mission;

import com.openworld.character.AISquad;
import com.openworld.character.Character;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Resource;
import godot.core.Vector3;

/**
 * One scripted order for a named story AI (PLAN.md Part F / F1), handed to
 * {@link MissionDirector#commandCharacter(String, ScriptCommand)}.
 *
 * <p>Every field is a <b>command with an explicit "do nothing" sentinel</b>, never a mirror of the
 * AI's current state: an order that omits a field leaves that part of the AI alone. So one command
 * object can say "walk here" without also claiming a state, an invincibility setting and a squad —
 * which is what a beat script actually wants, and what stops a partially-filled command from quietly
 * resetting the rest of the body.
 *
 * <ul>
 *   <li>{@link #targetState} — "" leaves the FSM alone; otherwise one of the {@code STATE_*} names.</li>
 *   <li>{@link #move} / {@link #moveTo} — a separate flag because {@code (0,0,0)} is a legal
 *       destination (it is the spec's own verify case), so "is the vector set" cannot be derived.</li>
 *   <li>{@link #invincible} — {@link #KEEP} / {@link #ON} / {@link #OFF}, the String-constant idiom
 *       this codebase already uses for {@code Faction} and {@code MissionObjectiveType}.</li>
 *   <li>{@link #assignSquad} / {@link #clearSquad} — a live node, so it is code-set, not exported:
 *       a {@code .tres} cannot hold a node reference.</li>
 * </ul>
 *
 * <p>Authorable as a {@code .tres} for beats that are pure data, or built in code (or from the debug
 * console) for everything else.
 */
@Script(className = "ScriptCommand")
public class ScriptCommand extends Resource {

    // ── targetState values (AIState singletons resolved by MissionDirector) ───
    public static final String STATE_PATROL        = "PATROL";
    public static final String STATE_CHASE         = "CHASE";
    public static final String STATE_ATTACK        = "ATTACK";
    public static final String STATE_SEARCH        = "SEARCH";
    public static final String STATE_ESCORT        = "ESCORT";
    public static final String STATE_FLEE          = "FLEE";
    public static final String STATE_REFILL_AMMO   = "REFILL_AMMO";
    /** Walk to {@link #moveTo} and hold there until the director releases the order. */
    public static final String STATE_SCRIPTED_MOVE = "SCRIPTED_MOVE";

    // ── invincible values ────────────────────────────────────────────────────
    public static final String KEEP = "";
    public static final String ON   = "on";
    public static final String OFF  = "off";

    /** Force the FSM into this state ("" = leave the FSM alone). Use a {@code STATE_*} constant. */
    @Export public String targetState = "";

    /** True when {@link #moveTo} is an order — see the class note on why this is not derived. */
    @Export public boolean move = false;

    /** Where the AI should walk to, in world space. Only read when {@link #move} is true. */
    @Export public Vector3 moveTo = new Vector3();

    /** {@link #KEEP} (default), {@link #ON} or {@link #OFF} — writes {@code Health.invulnerable}. */
    @Export public String invincible = KEEP;

    /** Squad to join. Null leaves the squad alone; see {@link #clearSquad} to leave one. */
    public AISquad assignSquad = null;

    /** True to leave the current squad (ignored when {@link #assignSquad} is set). */
    @Export public boolean clearSquad = false;

    /**
     * Who to escort. Null leaves the AI's current escort target alone, so ordering
     * {@link #STATE_ESCORT} without one re-enters an escort the body already had. A live node, so —
     * like {@link #assignSquad} — it is code-set rather than exported.
     */
    public Character escortTarget = null;

    public ScriptCommand() { super(); }

    // ── Fluent builders (code-authored beats; GDScript sets the fields directly) ──

    @Register
    public ScriptCommand withMoveTo(Vector3 destination) {
        move = true;
        moveTo = destination;
        targetState = STATE_SCRIPTED_MOVE;
        return this;
    }

    @Register
    public ScriptCommand withState(String state) {
        targetState = state;
        return this;
    }

    /** Escort this character: sets the target AND the state, because one without the other is a no-op. */
    public ScriptCommand withEscort(Character target) {
        escortTarget = target;
        targetState = STATE_ESCORT;
        return this;
    }

    @Register
    public ScriptCommand withInvincible(boolean on) {
        invincible = on ? ON : OFF;
        return this;
    }
}
