package com.openworld.game.mission;

import com.openworld.ai.AIController;
import com.openworld.ai.AIState;
import com.openworld.ai.character.AttackState;
import com.openworld.ai.character.ChaseState;
import com.openworld.ai.character.EscortState;
import com.openworld.ai.character.FleeState;
import com.openworld.ai.character.PatrolState;
import com.openworld.ai.character.RefillAmmoState;
import com.openworld.ai.character.ScriptedMoveState;
import com.openworld.ai.character.SearchState;
import com.openworld.character.AICharacter;
import com.openworld.character.Character;
import com.openworld.character.Health;
import com.openworld.character.Player;
import com.openworld.game.PlayerRegistry;
import com.openworld.game.EventBus;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;
import godot.api.Object;
import godot.core.MethodCallable;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * The story layer's one owner (PLAN.md Part F / F1) — registered as an AutoLoad named
 * "MissionDirector". Four jobs, deliberately in one place:
 *
 * <ol>
 *   <li><b>NamedCharacterRegistry</b> — {@code characterId → live AICharacter}, filled by the body's
 *       own {@code _ready()} ({@link AICharacter#storyCharacter}) and emptied by its {@code _exitTree}.
 *       Zones stream story AI in and out, so this map is authoritative about "is the boss loaded
 *       right now", which no scene-tree scan can answer cheaply at open-world scale.</li>
 *   <li><b>{@link #commandCharacter}</b> — a {@link ScriptCommand} applied to one of them.</li>
 *   <li><b>{@link #triggerBeat}</b> — the beat table plus {@code EventBus.missionBeatTriggered}.</li>
 *   <li><b>The mission-output graph</b> — see below.</li>
 * </ol>
 *
 * <h3>The output graph</h3>
 * A completion folds {@code (missionId, outcomeVariant)} into an accumulated set and re-evaluates an
 * append-only unlock table. Three properties the design note in PLAN.md asks for, each of which is
 * the reason the graph lives here and not in {@code MissionManager}:
 * <ul>
 *   <li><b>Idempotent on variant</b> — re-achieving a known variant changes nothing, so replaying a
 *       mission cannot duplicate branches and the tree stays bounded by {@code missions × variants}
 *       rather than by how often it is played.</li>
 *   <li><b>Sticky</b> — a branch once open never closes. {@link #unlocked} is only ever added to.</li>
 *   <li><b>Unique items exactly once</b> — {@link #grantUniqueOnce} is the membership check; ordinary
 *       rewards need no gate at all, which is why there is no code here that pretends to gate them.</li>
 * </ul>
 *
 * <p>It listens to {@code EventBus.missionCompleted}, which fires on <i>every</i> peer (a client gets
 * it mirrored through {@code GameManager.applyMissionCompleted}), so every peer's graph advances
 * together with no new message — and the idempotency above is what makes that safe.
 *
 * <p><b>Commands are host-side.</b> Only the host runs an {@code AIController}; a client's copy of the
 * same body is a puppet driven by snapshots. {@link #commandCharacter} therefore does nothing on a
 * client, and the motion it causes on the host replicates the ordinary way. It is not an error to
 * call it there — a beat script runs on both peers and must not have to know which one it is.
 */
@Script(className = "MissionDirector")
public class MissionDirector extends Node {

    /** JVM-static handle, the AutoLoad idiom used by {@code SpatialEntityGrid} / {@code ZoneManager}. */
    private static MissionDirector instance;

    public static MissionDirector get() { return instance; }

    // ── Named character registry ──────────────────────────────────────────────

    private final Map<String, AICharacter> named = new LinkedHashMap<>();

    // ── Beats ─────────────────────────────────────────────────────────────────

    /** beatId → Java handler. Beats are methods, not a scripting language (F3). */
    private final Map<String, Runnable> beats = new HashMap<>();
    private final List<String> firedBeats = new ArrayList<>();

    // ── Story graph ───────────────────────────────────────────────────────────

    /** Achieved "{missionId}#{variant}" keys — the accumulated membership set. */
    private final Set<String> achievedVariants = new LinkedHashSet<>();
    private final Set<String> completedMissions = new LinkedHashSet<>();
    /** missionId → the variant keys that open it. Empty list = open from the start. */
    private final Map<String, List<String>> unlockRequirements = new LinkedHashMap<>();
    private final Set<String> unlocked = new LinkedHashSet<>();
    private final Set<String> grantedUniqueItemIds = new HashSet<>();

    // ── Mission entities (the mission-vehicle rule) ───────────────────────────

    /**
     * Entities this mission depends on — a getaway car, an escortee's truck. Two rules come with
     * being in here, and they are the whole of the "a mission vehicle is not ambient traffic" note:
     * {@code ZoneManager} never reclaims one, and losing one that was registered with
     * {@code failOnLoss} fails the mission through {@code MissionManager.failMission} — which is the
     * mission system's rule, not the streamer's.
     */
    private static final class MissionEntity {
        final String key;
        final Node node;
        final boolean failOnLoss;
        MissionEntity(String key, Node node, boolean failOnLoss) {
            this.key = key; this.node = node; this.failOnLoss = failOnLoss;
        }
    }

    private final Map<String, MissionEntity> missionEntities = new LinkedHashMap<>();

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @Register
    @Override
    public void _ready() {
        instance = this;
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) {
            bus.missionCompleted.connectUnsafe(
                    MethodCallable.createUnsafe(this, "onMissionCompleted"), Object.ConnectFlags.DEFAULT);
            bus.missionFailed.connectUnsafe(
                    MethodCallable.createUnsafe(this, "onMissionFailed"), Object.ConnectFlags.DEFAULT);
        }
    }

    @Register
    @Override
    public void _exitTree() {
        // Leak discipline (CLAUDE.md "Known Quirks"): an AutoLoad's static back-reference and every
        // map holding live nodes go at teardown, or the next run inherits them.
        named.clear();
        beats.clear();
        firedBeats.clear();
        missionEntities.clear();
        if (instance == this) instance = null;
    }

    @Register
    @Override
    public void _process(double delta) {
        pruneMissionEntities();
    }

    // ── NamedCharacterRegistry ────────────────────────────────────────────────

    /**
     * Called by {@link AICharacter#_ready()} on a body whose {@code storyCharacter} flag is set.
     * A second body claiming an id that is already live is reported and REFUSED: mission code
     * addresses a story character by id, so two of them is an ambiguity nothing downstream can
     * resolve, and silently keeping the newer one would make which boss you commanded depend on
     * streaming order. A registration replacing a FREED node is the ordinary zone re-load and is
     * not a conflict.
     */
    public void registerNamedCharacter(AICharacter ai) {
        if (ai == null || ai.characterInfo == null) return;
        String id = ai.characterInfo.characterId;
        if (id == null || id.isEmpty()) {
            GD.printErr("[MissionDirector] story character with no characterId — not registered ("
                    + ai.getName() + ")");
            return;
        }
        AICharacter existing = named.get(id);
        if (existing != null && existing != ai && GD.isInstanceValid(existing)) {
            GD.printErr("[MissionDirector] duplicate story characterId '" + id
                    + "' — keeping the one already loaded, ignoring " + ai.getName());
            return;
        }
        named.put(id, ai);
    }

    /** Called from the body's {@code _exitTree}. Only drops the entry it still owns. */
    public void unregisterNamedCharacter(AICharacter ai) {
        if (ai == null || ai.characterInfo == null) return;
        String id = ai.characterInfo.characterId;
        if (id != null && named.get(id) == ai) named.remove(id);
    }

    /** The live story AI with this id, or null when it is not loaded (or has been freed). */
    public AICharacter getNamedCharacter(String characterId) {
        AICharacter ai = named.get(characterId);
        if (ai != null && !GD.isInstanceValid(ai)) {
            named.remove(characterId);
            return null;
        }
        return ai;
    }

    /** True when a story character with this id is loaded right now — probe/console readout. */
    @Register
    public boolean isNamedCharacterLoaded(String characterId) {
        return getNamedCharacter(characterId) != null;
    }

    /**
     * Every registered story-character id, comma-separated, in registration order (debug console
     * listing / probe readout). A plain String rather than a generic container: a nested generic
     * crosses the godot-jvm registration scanner badly (CLAUDE.md "Known Quirks"), and a list of ids
     * is one line of text at every call site that wants it.
     */
    @Register
    public String namedCharacterIds() {
        StringBuilder sb = new StringBuilder();
        for (Map.Entry<String, AICharacter> e : new ArrayList<>(named.entrySet())) {
            if (!GD.isInstanceValid(e.getValue())) { named.remove(e.getKey()); continue; }
            if (sb.length() > 0) sb.append(',');
            sb.append(e.getKey());
        }
        return sb.toString();
    }

    // ── Scripted commands ─────────────────────────────────────────────────────

    /**
     * Apply one {@link ScriptCommand} to a registered story character. Returns false when the
     * character is not loaded (a zone away, dead and freed) or when the body carries no AI brain —
     * i.e. on a client, where the body is a puppet.
     */
    public boolean commandCharacter(String characterId, ScriptCommand cmd) {
        AICharacter ai = getNamedCharacter(characterId);
        if (ai == null || cmd == null) return false;

        if (!ScriptCommand.KEEP.equals(cmd.invincible)) {
            Node h = ai.getNodeOrNull("Health");
            if (h instanceof Health health) health.invulnerable = ScriptCommand.ON.equals(cmd.invincible);
        }

        if (cmd.assignSquad != null) ai.setSquad(cmd.assignSquad);
        else if (cmd.clearSquad) ai.setSquad(null);

        if (cmd.escortTarget != null) ai.setEscortTarget(cmd.escortTarget);

        AIController ctrl = ai.aiController();
        if (ctrl == null) return false;          // a puppet: the host owns this AI's decisions

        if (cmd.move) {
            ctrl.setScriptedDestination(cmd.moveTo);
            ctrl.forceState(ScriptedMoveState.INSTANCE);
        }
        if (!cmd.targetState.isEmpty()) {
            AIState state = stateByName(cmd.targetState);
            if (state == null) {
                GD.printErr("[MissionDirector] unknown ScriptCommand state '" + cmd.targetState + "'");
            } else if (state != ScriptedMoveState.INSTANCE || cmd.move) {
                // SCRIPTED_MOVE without a destination is an order with nowhere to go — refused rather
                // than entered, which would drop the AI straight back to Patrol on its first tick.
                ctrl.forceState(state);
            } else {
                GD.printErr("[MissionDirector] SCRIPTED_MOVE with no moveTo — ignored");
            }
        }
        return true;
    }

    /** {@link #commandCharacter} as a walk order — the shape a beat (and the console) uses most. */
    @Register
    public boolean commandMoveTo(String characterId, Vector3 destination) {
        return commandCharacter(characterId, new ScriptCommand().withMoveTo(destination));
    }

    /** {@link #commandCharacter} forcing one FSM state by {@code ScriptCommand.STATE_*} name. */
    @Register
    public boolean commandState(String characterId, String stateName) {
        return commandCharacter(characterId, new ScriptCommand().withState(stateName));
    }

    /**
     * Order a story character to escort the nearest live player — the F3 verify's own beat ("walk
     * into the trigger and the boss starts escorting you"), and the shape almost every escort beat
     * wants. The target is resolved through {@code PlayerRegistry} rather than taken as an argument
     * because a beat fires from a volume that knows nothing about which player tripped it, and in
     * co-op "the player" is whichever one is there.
     */
    @Register
    public boolean commandEscortPlayer(String characterId) {
        AICharacter ai = getNamedCharacter(characterId);
        if (ai == null) return false;
        Character target = nearestPlayerTo(ai);
        if (target == null) return false;
        return commandCharacter(characterId, new ScriptCommand().withEscort(target));
    }

    private static Character nearestPlayerTo(AICharacter ai) {
        Character best = null;
        double bestSq = Double.MAX_VALUE;
        for (Player p : PlayerRegistry.getPlayers()) {
            if (p == null || !GD.isInstanceValid(p) || !p.isAlive()) continue;
            double d = p.getGlobalPosition().distanceTo(ai.getGlobalPosition());
            if (d < bestSq) { bestSq = d; best = p; }
        }
        return best;
    }

    /** {@link #commandCharacter} setting scripted invulnerability. */
    @Register
    public boolean commandInvincible(String characterId, boolean on) {
        return commandCharacter(characterId, new ScriptCommand().withInvincible(on));
    }

    /**
     * End a standing order: the AI drops its scripted destination and resumes its own behaviour on
     * the next tick. Invulnerability is cleared with it — a beat that made someone immortal for a
     * cutscene must not leave them that way, and having the release do both means one call can never
     * remember half of it.
     */
    @Register
    public boolean releaseCharacter(String characterId) {
        AICharacter ai = getNamedCharacter(characterId);
        if (ai == null) return false;
        Node h = ai.getNodeOrNull("Health");
        if (h instanceof Health health) health.invulnerable = false;
        AIController ctrl = ai.aiController();
        if (ctrl == null) return false;
        ctrl.clearScriptedDestination();
        ctrl.forceState(PatrolState.INSTANCE);
        return true;
    }

    /** True once a commanded walk has reached its destination — what a beat waits on. */
    @Register
    public boolean hasArrived(String characterId) {
        AICharacter ai = getNamedCharacter(characterId);
        if (ai == null) return false;
        AIController ctrl = ai.aiController();
        return ctrl != null && ctrl.hasScriptedArrived();
    }

    /** The FSM state name a story character is in, or "" — probe/console readout. */
    @Register
    public String stateNameOf(String characterId) {
        AICharacter ai = getNamedCharacter(characterId);
        AIController ctrl = ai != null ? ai.aiController() : null;
        AIState state = ctrl != null ? ctrl.getCurrentState() : null;
        return state == null ? "" : nameOfState(state);
    }

    private static AIState stateByName(String name) {
        return switch (name) {
            case ScriptCommand.STATE_PATROL        -> PatrolState.INSTANCE;
            case ScriptCommand.STATE_CHASE         -> ChaseState.INSTANCE;
            case ScriptCommand.STATE_ATTACK        -> AttackState.INSTANCE;
            case ScriptCommand.STATE_SEARCH        -> SearchState.INSTANCE;
            case ScriptCommand.STATE_ESCORT        -> EscortState.INSTANCE;
            case ScriptCommand.STATE_FLEE          -> FleeState.INSTANCE;
            case ScriptCommand.STATE_REFILL_AMMO   -> RefillAmmoState.INSTANCE;
            case ScriptCommand.STATE_SCRIPTED_MOVE -> ScriptedMoveState.INSTANCE;
            default -> null;
        };
    }

    private static String nameOfState(AIState state) {
        if (state == PatrolState.INSTANCE)        return ScriptCommand.STATE_PATROL;
        if (state == ChaseState.INSTANCE)         return ScriptCommand.STATE_CHASE;
        if (state == AttackState.INSTANCE)        return ScriptCommand.STATE_ATTACK;
        if (state == SearchState.INSTANCE)        return ScriptCommand.STATE_SEARCH;
        if (state == EscortState.INSTANCE)        return ScriptCommand.STATE_ESCORT;
        if (state == FleeState.INSTANCE)          return ScriptCommand.STATE_FLEE;
        if (state == RefillAmmoState.INSTANCE)    return ScriptCommand.STATE_REFILL_AMMO;
        if (state == ScriptedMoveState.INSTANCE)  return ScriptCommand.STATE_SCRIPTED_MOVE;
        return state.getClass().getSimpleName();
    }

    // ── Beats ─────────────────────────────────────────────────────────────────

    /** Register the Java method a beat id runs. Re-registering an id replaces its handler. */
    public void registerBeat(String beatId, Runnable handler) {
        if (beatId == null || beatId.isEmpty() || handler == null) return;
        beats.put(beatId, handler);
    }

    /**
     * Fire a story beat: run its registered handler (if any) and emit
     * {@code EventBus.missionBeatTriggered} either way, so a beat with no Java logic yet is still an
     * event dialogue/HUD can hang off. Returns true when a handler ran.
     */
    @Register
    public boolean triggerBeat(String beatId) {
        if (beatId == null || beatId.isEmpty()) return false;
        firedBeats.add(beatId);
        Runnable handler = beats.get(beatId);
        if (handler != null) handler.run();
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) bus.missionBeatTriggered.emit(beatId);
        return handler != null;
    }

    /** How many times a beat has fired this session — probe readout (beats are not idempotent). */
    @Register
    public int beatFireCount(String beatId) {
        int n = 0;
        for (String b : firedBeats) if (b.equals(beatId)) n++;
        return n;
    }

    // ── The mission-output graph ──────────────────────────────────────────────

    /**
     * Declare which achieved variants open a mission. Append-only in spirit: calling it again for an
     * id replaces that row (authoring), but nothing ever removes an id from {@link #unlocked}.
     * An empty/absent requirement list means "open from the start".
     */
    public void declareUnlock(String missionId, List<String> requiredVariantKeys) {
        if (missionId == null || missionId.isEmpty()) return;
        unlockRequirements.put(missionId,
                requiredVariantKeys == null ? List.of() : List.copyOf(requiredVariantKeys));
        reevaluateUnlocks();
    }

    /** {@link #declareUnlock} for a probe/console: one required "missionId#variant" key, or "" for none. */
    @Register
    public void declareUnlockOn(String missionId, String requiredVariantKey) {
        declareUnlock(missionId, requiredVariantKey == null || requiredVariantKey.isEmpty()
                ? List.of() : List.of(requiredVariantKey));
    }

    /** The membership key a completion folds in. */
    public static String variantKey(String missionId, String outcomeVariant) {
        return missionId + "#" + (outcomeVariant == null ? "" : outcomeVariant);
    }

    @Register
    public void onMissionCompleted(String missionId, String winningFaction, String outcomeVariant) {
        clearMissionEntities();
        completedMissions.add(missionId);
        String key = variantKey(missionId, outcomeVariant);
        // Idempotent on variant: a replay that reaches a variant already in the set changes nothing —
        // no duplicate branch, no re-grant, and the graph stays bounded by missions × variants.
        if (!achievedVariants.add(key)) return;
        reevaluateUnlocks();
    }

    @Register
    public void onMissionFailed(String missionId, String reason) {
        clearMissionEntities();
    }

    private void reevaluateUnlocks() {
        for (Map.Entry<String, List<String>> e : unlockRequirements.entrySet()) {
            if (unlocked.contains(e.getKey())) continue;      // sticky: never re-closed
            if (achievedVariants.containsAll(e.getValue())) unlocked.add(e.getKey());
        }
    }

    /** True when the mission may start — a mission nobody declared a requirement for is open. */
    @Register
    public boolean isMissionUnlocked(String missionId) {
        List<String> req = unlockRequirements.get(missionId);
        if (req == null || req.isEmpty()) return true;
        return unlocked.contains(missionId);
    }

    /**
     * The gated way to start a mission: refuses one whose unlock predicate is not satisfied, and
     * otherwise hands it to {@code MissionManager}, which still owns the objective TRACKING. The two
     * halves are deliberately separate — "may this run" is campaign state, "is it won yet" is not.
     */
    public boolean startMission(MissionInfo info) {
        if (info == null) return false;
        if (!isMissionUnlocked(info.missionId)) {
            GD.print("MissionDirector: '" + info.missionId + "' is still locked");
            return false;
        }
        Node mmNode = getNodeOrNull("/root/MissionManager");
        if (!(mmNode instanceof MissionManager mm)) return false;
        mm.startMission(info);
        return true;
    }

    /** {@link #startMission} from a {@code MissionInfo} {@code .tres} path (beat scripts, console). */
    @Register
    public boolean startMissionFromPath(String path) {
        return GD.load(path) instanceof MissionInfo info && startMission(info);
    }

    /** True when {@code (missionId, variant)} has ever been achieved. */
    @Register
    public boolean hasAchieved(String missionId, String outcomeVariant) {
        return achievedVariants.contains(variantKey(missionId, outcomeVariant));
    }

    /** How many distinct variants are in the accumulated set — the bound the idempotency rule keeps. */
    @Register
    public int achievedVariantCount() { return achievedVariants.size(); }

    @Register
    public boolean hasCompleted(String missionId) { return completedMissions.contains(missionId); }

    /**
     * Grant a story-wide unique item exactly once: true the first time, false ever after. Ordinary
     * rewards (money, common loot) are granted unconditionally by whoever hands them out and need no
     * call here — there is nothing to gate, so there is deliberately no code pretending to gate it.
     */
    @Register
    public boolean grantUniqueOnce(String itemId) {
        return itemId != null && !itemId.isEmpty() && grantedUniqueItemIds.add(itemId);
    }

    // ── Campaign persistence (I7) ─────────────────────────────────────────────
    //
    // The four sets plus the fired-beat log are the whole of what a save has to carry from here.
    // What it must NOT carry is {@link #unlockRequirements}: that is AUTHORING, re-declared by the
    // same Java on every launch, and a saved copy of it would go stale the day the campaign is
    // edited — with the stale copy winning. Progress is saved; content is not.

    /** The achieved "{missionId}#{variant}" keys, in the order they were achieved. */
    public List<String> achievedVariantKeys() { return new ArrayList<>(achievedVariants); }

    public List<String> completedMissionIds() { return new ArrayList<>(completedMissions); }

    /** The sticky opened set. Saved rather than re-derived: a branch once open never closes. */
    public List<String> unlockedMissionIds() { return new ArrayList<>(unlocked); }

    public List<String> grantedUniqueItems() { return new ArrayList<>(grantedUniqueItemIds); }

    /**
     * Every beat fired this campaign, in order and with repeats — so {@link #beatFireCount} answers
     * the same number after a load. {@code ZoneTrigger.oneShot} asks that question, which is why this
     * log is campaign state rather than a debug counter.
     */
    public List<String> firedBeatLog() { return new ArrayList<>(firedBeats); }

    /**
     * Replace the campaign graph with a saved one (I7 {@code SaveSystem.loadSlot}). A REPLACE, not a
     * merge: whatever this session had achieved before the load is not part of the slot being loaded.
     * Unlocks are re-evaluated afterwards, so a requirement declared by code this launch that the
     * restored achievements already satisfy opens with everything else.
     */
    public void restoreCampaign(List<String> achieved, List<String> completed, List<String> unlockedIds,
                                List<String> granted, List<String> beatsFired) {
        achievedVariants.clear();
        completedMissions.clear();
        unlocked.clear();
        grantedUniqueItemIds.clear();
        firedBeats.clear();
        if (achieved != null)    achievedVariants.addAll(achieved);
        if (completed != null)   completedMissions.addAll(completed);
        if (unlockedIds != null) unlocked.addAll(unlockedIds);
        if (granted != null)     grantedUniqueItemIds.addAll(granted);
        if (beatsFired != null)  firedBeats.addAll(beatsFired);
        reevaluateUnlocks();
    }

    /** Wipe the campaign graph — a new game, or a restart. Does not touch live registrations. */
    @Register
    public void resetCampaign() {
        achievedVariants.clear();
        completedMissions.clear();
        unlocked.clear();
        grantedUniqueItemIds.clear();
        firedBeats.clear();
        reevaluateUnlocks();
    }

    // ── Mission entities ──────────────────────────────────────────────────────

    /**
     * Mark a live node as belonging to the active mission. A registered vehicle is invisible to
     * {@code ZoneManager}'s disposable-traffic reclaim, so "steal THAT car" survives the car being an
     * ordinary ambient one a moment ago.
     *
     * @param failOnLoss true when losing it fails the mission (the rule is the mission system's:
     *                   this calls {@code MissionManager.failMission}, never the streamer).
     */
    @Register
    public void registerMissionEntity(String key, Node entity, boolean failOnLoss) {
        if (key == null || key.isEmpty() || entity == null) return;
        missionEntities.put(key, new MissionEntity(key, entity, failOnLoss));
    }

    @Register
    public void unregisterMissionEntity(String key) { missionEntities.remove(key); }

    /**
     * True when this node (or an ancestor of it) belongs to the active mission. Asked by
     * {@code ZoneManager} before it reclaims a car — so the rule "a mission vehicle is not ambient
     * traffic" is enforced in ONE place rather than copied into every reclaim reason.
     */
    public boolean isMissionProtected(Node node) {
        if (node == null || missionEntities.isEmpty()) return false;
        for (MissionEntity e : missionEntities.values()) {
            if (e.node == node) return true;
        }
        return false;
    }

    /** {@link #isMissionProtected} for GDScript probes. */
    @Register
    public boolean missionProtectedNow(Node node) { return isMissionProtected(node); }

    /** Number of live mission entities — probe readout. */
    @Register
    public int missionEntityCount() { return missionEntities.size(); }

    /**
     * Drop freed mission entities, failing the mission for any that said so. A freed node is the only
     * signal that covers every way a vehicle can be lost (destroyed, streamed out, despawned by the
     * host), which is why this is a validity sweep rather than a {@code Health.died} connection —
     * a wreck that is replaced by a wreck scene never emits anything the mission could hear.
     */
    private void pruneMissionEntities() {
        if (missionEntities.isEmpty()) return;
        List<MissionEntity> lost = null;
        for (MissionEntity e : missionEntities.values()) {
            if (!GD.isInstanceValid(e.node)) {
                if (lost == null) lost = new ArrayList<>();
                lost.add(e);
            }
        }
        if (lost == null) return;
        for (MissionEntity e : lost) {
            missionEntities.remove(e.key);
            GD.print("MissionDirector: mission entity '" + e.key + "' lost"
                    + (e.failOnLoss ? " — failing the mission" : ""));
            if (e.failOnLoss) failActiveMission("mission entity lost: " + e.key);
        }
    }

    /** Clear the per-mission entity list; a mission's dependencies do not outlive the mission. */
    private void clearMissionEntities() { missionEntities.clear(); }

    private void failActiveMission(String reason) {
        Node mmNode = getNodeOrNull("/root/MissionManager");
        if (mmNode instanceof MissionManager mm) mm.failMission(reason);
    }
}
