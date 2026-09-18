package com.openworld.game.mission;

import com.openworld.character.Character;
import com.openworld.character.Player;
import com.openworld.game.EventBus;
import com.openworld.game.GameManager;
import com.openworld.game.PlayerRegistry;
import com.openworld.net.NetworkManager;
import com.openworld.world.RaceCheckpoint;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.Node;
import godot.api.Object;
import godot.core.MethodCallable;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * The one active race (PLAN.md 4.5 / R2) — registered as an AutoLoad named "RaceDirector".
 *
 * <p>A race is an OBJECTIVE TYPE, so it sits on {@code MissionManager}'s side of the F1 split —
 * "is it won yet" — and not on {@code MissionDirector}'s, which owns "may this mission run".
 * {@code MissionManager.startMission} hands a {@code RACE} mission here and this class hands the
 * answer back through {@code completeMission} / {@code failMission}, exactly as the ELIMINATE_ALL
 * counter does. It is a separate class rather than another branch in {@code MissionManager} because
 * a race carries live per-racer state (progress, laps, placings, a clock) that no other objective
 * type has, and a per-frame tick that a pure event counter does not need.
 *
 * <h3>The route is checkpoints in index order, and the checkpoints register themselves</h3>
 * {@link RaceCheckpoint} nodes call {@link #registerCheckpoint} in {@code _ready} and
 * {@link #unregisterCheckpoint} in {@code _exitTree} — the {@code Character}↔{@code SpatialEntityGrid}
 * idiom — so a circuit authored inside a streamed zone assembles and disassembles itself with no
 * tree scan. They are keyed by {@code raceId}, so a world holds as many circuits as it has names.
 *
 * <h3>A checkpoint does not adjudicate; it reports</h3>
 * {@link RaceCheckpoint} tells this class "this body touched index N" and nothing more. Only the
 * racer's OWN next index counts, so driving back through a checkpoint you already took is not
 * progress, and cutting the course cannot skip one. That rule lives here, once, because it is the
 * same rule for every checkpoint in the world.
 *
 * <h3>The racer is the CHARACTER, never the vehicle</h3>
 * Keyed by {@code characterId} — the id the whole net layer already uses. A racer who wrecks their
 * car, steals another and drives on is the same racer; one who bails out and runs the last 50 m on
 * foot still finishes, which is what GTA does and what falls out of keying on the driver.
 *
 * <h3>Host-authoritative, mirrored through the seam that already exists</h3>
 * Only the host grants a checkpoint and only the host decides a finish
 * ({@code WORLD_EVENT_RACE_START / _CHECKPOINT / _FINISH}); a client applies what it is told and
 * never adjudicates. The race ENDING needs no message of its own — it is implied by the mission
 * completing or failing, which already replicates, and this class listens to those two signals on
 * every peer.
 */
@Script(className = "RaceDirector")
public class RaceDirector extends Node {

    /** JVM-static handle — the AutoLoad idiom ({@code SpatialEntityGrid}, {@code MissionDirector}). */
    private static RaceDirector instance;

    public static RaceDirector get() { return instance; }

    // ── Phases ────────────────────────────────────────────────────────────────

    public static final String PHASE_IDLE      = "IDLE";
    public static final String PHASE_COUNTDOWN = "COUNTDOWN";
    public static final String PHASE_RUNNING   = "RUNNING";
    public static final String PHASE_FINISHED  = "FINISHED";

    /** Outcome variants a race produces. Authored missions list these in {@code possibleOutcomeVariants}. */
    public static final String VARIANT_WON      = "WON";
    public static final String VARIANT_FINISHED = "FINISHED";

    // ── Tuning (live state, not scene-authored: an AutoLoad has no scene to author it in) ─────

    /** Seconds of "3… 2… 1… GO" before the clock starts. */
    @Visible public float countdownSeconds = 3f;

    /** How often standings are recomputed. Places move slowly; a per-frame sort is waste. */
    @Visible public float standingsInterval = 0.25f;

    @Visible public boolean debugLog = false;

    /**
     * CONTROL KNOB, always on. Off, ANY gate the racer has not taken counts, in any order — the naive
     * implementation this class refuses, in which cutting a corner skips a checkpoint and a lap can be
     * finished by driving through the four gates nearest the start. It exists so the gate can MEASURE
     * the ordering rule instead of asserting it in prose.
     */
    @Visible public boolean orderedCheckpoints = true;

    // ── Checkpoint registry ───────────────────────────────────────────────────

    /** raceId → index → checkpoint. A TreeMap so "the route" IS the key order, with no sort at use. */
    private final Map<String, TreeMap<Integer, RaceCheckpoint>> circuits = new LinkedHashMap<>();

    // ── The one active race ───────────────────────────────────────────────────

    private static final class Racer {
        final String characterId;
        String displayName;
        int lap = 0;             // laps completed
        int nextIndex = 0;       // the only checkpoint index that counts for this racer
        boolean finished = false;
        float finishTime = 0f;
        int place = 0;           // 1-based, set on finishing
        boolean human = false;   // enrolled from PlayerRegistry — decides when the MISSION ends

        Racer(String characterId) { this.characterId = characterId; }
    }

    private final Map<String, Racer> racers = new LinkedHashMap<>();
    /** Enrolled before a start (AI racers a mission spawns), folded in by {@link #startRace}. */
    private final List<String> pendingRacers = new ArrayList<>();

    private String phase = PHASE_IDLE;
    private String raceId = "";
    private String missionId = "";
    private int laps = 1;
    private float timeLimit = 0f;
    private double countdownLeft = 0.0;
    private double elapsed = 0.0;
    private double standingsTimer = 0.0;
    private int finishedCount = 0;
    /** Guards the completeMission/failMission → endRace → … path from re-entering itself. */
    private boolean ending = false;

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @Register
    @Override
    public void _ready() {
        instance = this;
        if (getNodeOrNull("/root/EventBus") instanceof EventBus bus) {
            // The race ends when its mission does, on EVERY peer — a client's mirror of the mission
            // event is what ends its race, so no fourth world-event constant is needed.
            bus.missionCompleted.connectUnsafe(
                    MethodCallable.createUnsafe(this, "onMissionCompleted"), Object.ConnectFlags.DEFAULT);
            bus.missionFailed.connectUnsafe(
                    MethodCallable.createUnsafe(this, "onMissionFailed"), Object.ConnectFlags.DEFAULT);
        }
    }

    @Register
    @Override
    public void _exitTree() {
        // Leak discipline: an AutoLoad's static back-reference and every map holding live nodes.
        circuits.clear();
        racers.clear();
        pendingRacers.clear();
        if (instance == this) instance = null;
    }

    @Register
    @Override
    public void _process(double delta) {
        if (PHASE_COUNTDOWN.equals(phase)) {
            countdownLeft -= delta;
            if (countdownLeft <= 0.0) {
                countdownLeft = 0.0;
                phase = PHASE_RUNNING;
                if (debugLog) GD.print("RaceDirector: '" + raceId + "' GO");
            }
            return;
        }
        if (!PHASE_RUNNING.equals(phase)) return;

        elapsed += delta;
        standingsTimer -= delta;
        if (standingsTimer <= 0.0) {
            standingsTimer = standingsInterval;
            updateStandings();
        }
        // Only the host may end a race on the clock: the mission events it produces are the ones
        // every peer mirrors, and two peers failing the same mission is two events for one fact.
        if (timeLimit > 0f && elapsed >= timeLimit && isHost()) {
            phase = PHASE_FINISHED;
            failMission("race time limit reached");
        }
    }

    // ── Checkpoint registry ───────────────────────────────────────────────────

    public void registerCheckpoint(RaceCheckpoint cp) {
        if (cp == null || cp.raceId == null || cp.raceId.isEmpty()) return;
        TreeMap<Integer, RaceCheckpoint> circuit = circuits.computeIfAbsent(cp.raceId, k -> new TreeMap<>());
        RaceCheckpoint existing = circuit.get(cp.checkpointIndex);
        if (existing != null && existing != cp && GD.isInstanceValid(existing)) {
            // Two checkpoints claiming one index is an ambiguity nothing downstream can resolve, and
            // keeping the newer one would make the route depend on streaming order (MissionDirector's
            // duplicate-id rule, same reason).
            GD.printErr("RaceDirector: duplicate checkpoint " + cp.raceId + "#" + cp.checkpointIndex
                    + " — keeping the one already loaded, ignoring " + cp.getName());
            return;
        }
        circuit.put(cp.checkpointIndex, cp);
    }

    public void unregisterCheckpoint(RaceCheckpoint cp) {
        if (cp == null || cp.raceId == null) return;
        TreeMap<Integer, RaceCheckpoint> circuit = circuits.get(cp.raceId);
        if (circuit == null) return;
        if (circuit.get(cp.checkpointIndex) == cp) circuit.remove(cp.checkpointIndex);
        if (circuit.isEmpty()) circuits.remove(cp.raceId);
    }

    /** The checkpoints of a circuit in index order, freed ones dropped. */
    private List<RaceCheckpoint> routeOf(String id) {
        TreeMap<Integer, RaceCheckpoint> circuit = circuits.get(id);
        List<RaceCheckpoint> out = new ArrayList<>();
        if (circuit == null) return out;
        circuit.entrySet().removeIf(e -> !GD.isInstanceValid(e.getValue()));
        out.addAll(circuit.values());
        return out;
    }

    /** How many checkpoints this circuit has right now — probe/HUD readout. */
    @Register
    public int checkpointCount(String id) { return routeOf(id).size(); }

    // ── Starting ──────────────────────────────────────────────────────────────

    /**
     * Enrol a racer before (or during) a race — an AI racer a mission spawned, or a late joiner.
     * Enrolling someone who is already racing is a no-op, so a beat may call it freely.
     */
    @Register
    public void addRacer(String characterId) {
        if (characterId == null || characterId.isEmpty()) return;
        if (PHASE_IDLE.equals(phase) || PHASE_FINISHED.equals(phase)) {
            if (!pendingRacers.contains(characterId)) pendingRacers.add(characterId);
            return;
        }
        racers.computeIfAbsent(characterId, Racer::new);
    }

    /**
     * Begin the race a {@code RACE} mission describes. Called by {@code MissionManager.startMission}.
     *
     * <p>Refused, loudly, when the circuit does not exist or is shorter than two checkpoints: a race
     * that silently runs with no route is a mission the player can never finish, and the cause (a
     * mis-named {@code raceId}, or a zone that has not streamed in) is invisible from the HUD.
     */
    public boolean startRace(MissionInfo info) {
        if (info == null) return false;
        String id = info.raceId == null || info.raceId.isEmpty() ? info.missionId : info.raceId;
        List<RaceCheckpoint> route = routeOf(id);
        if (route.size() < 2) {
            GD.printErr("RaceDirector: race '" + id + "' has " + route.size()
                    + " checkpoint(s) — a route needs at least 2; not started");
            return false;
        }
        raceId = id;
        missionId = info.missionId;
        laps = Math.max(1, info.raceLaps);
        timeLimit = info.timeLimit;
        elapsed = 0.0;
        countdownLeft = countdownSeconds;
        standingsTimer = 0.0;
        finishedCount = 0;
        ending = false;
        racers.clear();

        // Every live player races. In co-op that is the whole session, which is the only default a
        // mission cannot get wrong; AI racers (and anyone else) come from addRacer.
        for (Player p : PlayerRegistry.getPlayers()) {
            if (p == null || !GD.isInstanceValid(p) || p.characterInfo == null) continue;
            Racer r = racers.computeIfAbsent(p.characterInfo.characterId, Racer::new);
            r.human = true;
            r.displayName = p.characterInfo.displayName;
        }
        for (String pending : pendingRacers) racers.computeIfAbsent(pending, Racer::new);
        pendingRacers.clear();

        phase = PHASE_COUNTDOWN;
        GD.print("RaceDirector: race '" + raceId + "' — " + route.size() + " checkpoints × "
                + laps + " lap(s), " + racers.size() + " racer(s)");
        broadcastStart(-1);
        return true;
    }

    /** How many racers have finished — probe readout. */
    @Register
    public int finishedRacerCount() { return finishedCount; }

    /**
     * The {@code WORLD_EVENT_RACE_START} payload: {@code [missionId, laps, then one characterId and
     * one "0"/"1" human flag per racer]}. The ROSTER rides in it rather than being re-derived,
     * because a client's own {@code PlayerRegistry} does not know which AI the host enrolled.
     *
     * <p>This method and {@link #applyRemoteStart} are the two halves of one fact and live next to
     * each other on purpose: an off-by-one between a builder here and a parser in
     * {@code GameManager} is exactly the bug that shows up as "the client thinks the AI is a human
     * and waits for it to finish", with nothing on either peer to say so.
     */
    public List<String> startArgs() {
        List<String> args = new ArrayList<>();
        args.add(missionId);
        args.add(String.valueOf(laps));
        for (Racer r : racers.values()) {
            args.add(r.characterId);
            args.add(r.human ? "1" : "0");
        }
        return args;
    }

    /** Client-side mirror of a host race start. Parses exactly what {@link #startArgs} built. */
    public void applyRemoteStart(String id, float countdown, List<String> args) {
        raceId = id;
        missionId = arg(args, 0);
        laps = Math.max(1, intArg(args, 1, 1));
        timeLimit = 0f;            // the clock that can FAIL the mission is the host's alone
        elapsed = 0.0;
        countdownLeft = countdown;
        finishedCount = 0;
        ending = false;
        racers.clear();
        for (int i = 2; i + 1 < args.size(); i += 2) {
            Racer r = racers.computeIfAbsent(args.get(i), Racer::new);
            r.human = "1".equals(args.get(i + 1));
        }
        phase = countdown > 0f ? PHASE_COUNTDOWN : PHASE_RUNNING;
    }

    private static String arg(List<String> args, int i) {
        return args != null && i < args.size() && args.get(i) != null ? args.get(i) : "";
    }

    private static int intArg(List<String> args, int i, int fallback) {
        try { return Integer.parseInt(arg(args, i)); } catch (NumberFormatException e) { return fallback; }
    }

    // ── Checkpoints ───────────────────────────────────────────────────────────

    /**
     * A body touched a checkpoint. Host-only adjudication: on a client this returns immediately and
     * the racer's progress arrives as {@code WORLD_EVENT_RACE_CHECKPOINT} instead.
     *
     * @return true when this counted as progress.
     */
    public boolean onCheckpointTouched(RaceCheckpoint cp, Character who) {
        if (cp == null || who == null || who.characterInfo == null) return false;
        if (!PHASE_RUNNING.equals(phase)) return false;
        if (!cp.raceId.equals(raceId)) return false;
        if (!isHost()) return false;

        Racer r = racers.get(who.characterInfo.characterId);
        if (r == null || r.finished) return false;
        // Only the racer's OWN next index counts — see the class note.
        if (orderedCheckpoints && cp.checkpointIndex != r.nextIndex) {
            if (debugLog) GD.print("RaceDirector: " + r.characterId + " touched #" + cp.checkpointIndex
                    + " but wants #" + r.nextIndex);
            return false;
        }

        int count = routeOf(raceId).size();
        r.nextIndex++;
        if (r.nextIndex >= count) {
            r.nextIndex = 0;
            r.lap++;
        }
        if (debugLog) GD.print("RaceDirector: " + r.characterId + " cleared #" + cp.checkpointIndex
                + " → lap " + r.lap + " next #" + r.nextIndex);
        broadcastCheckpoint(r);

        if (r.lap >= laps) finishRacer(r);
        return true;
    }

    /** Client-side mirror of one racer's progress. args = [raceId, nextIndex, lap]. */
    public void applyRemoteCheckpoint(String characterId, float atTime, List<String> args) {
        applyRemoteCheckpointAt(characterId, intArg(args, 1, 0), intArg(args, 2, 0), atTime);
    }

    /** Client-side mirror of one racer finishing. args = [raceId, place]. */
    public void applyRemoteFinish(String characterId, float finishTime, List<String> args) {
        applyRemoteFinishAt(characterId, finishTime, intArg(args, 1, 0));
    }

    private void applyRemoteCheckpointAt(String characterId, int nextIndex, int lap, float atTime) {
        Racer r = racers.computeIfAbsent(characterId, Racer::new);
        r.nextIndex = nextIndex;
        r.lap = lap;
        elapsed = Math.max(elapsed, atTime);
        if (PHASE_COUNTDOWN.equals(phase)) { phase = PHASE_RUNNING; countdownLeft = 0.0; }
    }

    private void applyRemoteFinishAt(String characterId, float finishTime, int place) {
        Racer r = racers.computeIfAbsent(characterId, Racer::new);
        if (!r.finished) finishedCount++;
        r.finished = true;
        r.finishTime = finishTime;
        r.place = place;
    }

    private void finishRacer(Racer r) {
        r.finished = true;
        r.finishTime = (float) elapsed;
        r.place = ++finishedCount;
        GD.print("RaceDirector: " + r.characterId + " finished #" + r.place
                + " at " + String.format("%.2f", r.finishTime) + "s");
        broadcastFinish(r, -1);

        // The MISSION ends when every human has finished — not when the first one does, or a co-op
        // partner two corners behind would be cut off mid-race. AI racers keep their places but
        // cannot end anything: the mission is the players'.
        for (Racer other : racers.values()) {
            if (other.human && !other.finished) return;
        }
        int best = Integer.MAX_VALUE;
        for (Racer other : racers.values()) {
            if (other.human && other.place > 0) best = Math.min(best, other.place);
        }
        phase = PHASE_FINISHED;
        completeMission(best == 1 ? VARIANT_WON : VARIANT_FINISHED);
    }

    // ── Standings ─────────────────────────────────────────────────────────────

    /**
     * Place = checkpoints cleared, then distance to the next one. Cheap and exact enough for a HUD
     * list; the only place that is authoritative is a FINISHED one, which is fixed when it is set.
     */
    private void updateStandings() {
        List<RaceCheckpoint> route = routeOf(raceId);
        if (route.isEmpty()) return;
        int count = route.size();
        List<Racer> running = new ArrayList<>();
        for (Racer r : racers.values()) if (!r.finished) running.add(r);
        running.sort(Comparator
                .comparingInt((Racer r) -> -(r.lap * count + r.nextIndex))
                .thenComparingDouble(r -> distanceToNext(r, route)));
        int place = finishedCount;
        for (Racer r : running) r.place = ++place;
    }

    private double distanceToNext(Racer r, List<RaceCheckpoint> route) {
        Character c = findCharacter(r.characterId);
        if (c == null || r.nextIndex >= route.size()) return Double.MAX_VALUE;
        return c.getGlobalPosition().distanceTo(route.get(r.nextIndex).getGlobalPosition());
    }

    // ── Ending ────────────────────────────────────────────────────────────────

    @Register
    public void onMissionCompleted(String id, String winningFaction, String outcomeVariant) { endRace(); }

    @Register
    public void onMissionFailed(String id, String reason) { endRace(); }

    /**
     * End the active race. Idempotent, and safe to call from the mission events it produces.
     *
     * <p>It FREEZES rather than wipes: the placings, the clock and the roster stay readable until the
     * next {@link #startRace} clears them, because the moment a race ends is exactly when the results
     * are wanted — by the HUD's finish panel, by a beat that reads who won, and by a probe. Only
     * {@link #raceActiveNow} changes.
     */
    @Register
    public void endRace() {
        if (PHASE_IDLE.equals(phase) || PHASE_FINISHED.equals(phase)) return;
        phase = PHASE_FINISHED;
    }

    private void completeMission(String variant) {
        if (ending) return;
        ending = true;
        if (getNodeOrNull("/root/MissionManager") instanceof MissionManager mm) {
            String faction = "";
            MissionInfo info = mm.getActiveMission();
            if (info != null && !info.playerFactions.isEmpty()) faction = info.playerFactions.get(0);
            mm.completeMission(faction, variant);
        }
    }

    private void failMission(String reason) {
        if (ending) return;
        ending = true;
        if (getNodeOrNull("/root/MissionManager") instanceof MissionManager mm) mm.failMission(reason);
    }

    // ── Replication ───────────────────────────────────────────────────────────

    private NetworkManager net() {
        return getNodeOrNull("/root/NetworkManager") instanceof NetworkManager n ? n : null;
    }

    /** True where the race is adjudicated: single-player, or the host. */
    private boolean isHost() {
        NetworkManager n = net();
        return n == null || !n.isNetworked() || n.isServer();
    }

    /**
     * Host → all (or one peer, for the late-join baseline). args = [missionId, laps, then one
     * {@code <characterId>} and one {@code "0"/"1"} human flag per racer]; value = the countdown
     * still to run.
     */
    private void broadcastStart(int targetPeerId) {
        NetworkManager n = net();
        if (n == null || !n.isServer() || !n.isNetworked()) return;
        List<String> args = startArgs();
        if (targetPeerId < 0) {
            n.broadcastWorldEvent(GameManager.WORLD_EVENT_RACE_START, raceId, (float) countdownLeft, args);
        } else {
            n.sendWorldEventTo(targetPeerId, GameManager.WORLD_EVENT_RACE_START, raceId,
                    (float) countdownLeft, args);
        }
    }

    private void broadcastCheckpoint(Racer r) {
        NetworkManager n = net();
        if (n == null || !n.isServer() || !n.isNetworked()) return;
        n.broadcastWorldEvent(GameManager.WORLD_EVENT_RACE_CHECKPOINT, r.characterId, (float) elapsed,
                List.of(raceId, String.valueOf(r.nextIndex), String.valueOf(r.lap)));
    }

    private void broadcastFinish(Racer r, int targetPeerId) {
        NetworkManager n = net();
        if (n == null || !n.isServer() || !n.isNetworked()) return;
        List<String> args = List.of(raceId, String.valueOf(r.place));
        if (targetPeerId < 0) {
            n.broadcastWorldEvent(GameManager.WORLD_EVENT_RACE_FINISH, r.characterId, r.finishTime, args);
        } else {
            n.sendWorldEventTo(targetPeerId, GameManager.WORLD_EVENT_RACE_FINISH, r.characterId,
                    r.finishTime, args);
        }
    }

    /**
     * Late-join baseline: the start event (with the countdown still to run and the roster) followed
     * by each racer's current progress, as the same events a live race sends — so the receiving path
     * is the one that is already exercised.
     */
    public void sendBaselineTo(int targetPeerId) {
        if (PHASE_IDLE.equals(phase) || PHASE_FINISHED.equals(phase)) return;
        NetworkManager n = net();
        if (n == null || !n.isServer()) return;
        broadcastStart(targetPeerId);
        for (Racer r : racers.values()) {
            if (r.finished) {
                broadcastFinish(r, targetPeerId);
            } else if (r.lap > 0 || r.nextIndex > 0) {
                n.sendWorldEventTo(targetPeerId, GameManager.WORLD_EVENT_RACE_CHECKPOINT, r.characterId,
                        (float) elapsed, List.of(raceId, String.valueOf(r.nextIndex), String.valueOf(r.lap)));
            }
        }
    }

    // ── Readouts (HUD, console, probes) ───────────────────────────────────────
    //
    // Question-named so godot-jvm does not merge them with a field into one bean property
    // (CLAUDE.md "Known Quirks"), and deliberately scalar: the HUD POLLS this class the way
    // WeaponProgress polls the weapon controller, so a race needs no EventBus signal of its own.

    @Register public boolean raceActiveNow() {
        return PHASE_COUNTDOWN.equals(phase) || PHASE_RUNNING.equals(phase);
    }

    @Register public String racePhaseNow()  { return phase; }
    @Register public String raceIdNow()     { return raceId; }
    @Register public String raceMissionId() { return missionId; }
    @Register public int    raceLapCount()  { return laps; }
    @Register public float  raceElapsed()   { return (float) elapsed; }
    @Register public float  raceCountdownLeft() { return (float) countdownLeft; }

    /** Seconds left on a time trial, or -1 when the mission set no limit. */
    @Register public float raceTimeRemaining() {
        return timeLimit > 0f ? (float) Math.max(0.0, timeLimit - elapsed) : -1f;
    }

    @Register public int raceCheckpointCount() { return routeOf(raceId).size(); }
    @Register public int racerCount()          { return racers.size(); }

    /** Every enrolled racer's characterId, comma-separated (a nested generic crosses the scanner badly). */
    @Register public String racerIdsNow() {
        StringBuilder sb = new StringBuilder();
        for (String id : racers.keySet()) {
            if (sb.length() > 0) sb.append(',');
            sb.append(id);
        }
        return sb.toString();
    }

    @Register public boolean isRacer(String characterId)     { return racers.containsKey(characterId); }
    @Register public int     racerLap(String characterId)    { Racer r = racers.get(characterId); return r == null ? -1 : r.lap; }
    @Register public int     racerNextIndex(String characterId) { Racer r = racers.get(characterId); return r == null ? -1 : r.nextIndex; }
    @Register public int     racerPlace(String characterId)  { Racer r = racers.get(characterId); return r == null ? 0 : r.place; }
    @Register public boolean racerFinished(String characterId) { Racer r = racers.get(characterId); return r != null && r.finished; }
    @Register public float   racerFinishTime(String characterId) { Racer r = racers.get(characterId); return r == null ? -1f : r.finishTime; }

    /**
     * Where this racer's next checkpoint is — what {@code ui.GpsArrow} points at while a race runs.
     * Returns {@link Vector3#ZERO} when there is nothing to point at, paired with
     * {@link #hasNextCheckpoint} because (0,0,0) is a legal world position (the {@code ScriptCommand}
     * rule).
     */
    @Register
    public Vector3 nextCheckpointPosition(String characterId) {
        RaceCheckpoint cp = nextCheckpointOf(characterId);
        return cp == null ? Vector3.Companion.getZERO() : cp.getGlobalPosition();
    }

    @Register
    public boolean hasNextCheckpoint(String characterId) { return nextCheckpointOf(characterId) != null; }

    private RaceCheckpoint nextCheckpointOf(String characterId) {
        if (!raceActiveNow()) return null;
        Racer r = racers.get(characterId);
        if (r == null || r.finished) return null;
        List<RaceCheckpoint> route = routeOf(raceId);
        return r.nextIndex < route.size() ? route.get(r.nextIndex) : null;
    }

    /** True when this checkpoint is the given racer's next one — what the marker tints itself by. */
    public boolean isNextFor(RaceCheckpoint cp, String characterId) {
        return cp != null && cp == nextCheckpointOf(characterId);
    }

    /**
     * Feed this peer a race world event as a CLIENT would receive it, with the args joined by
     * commas — the probe/console seam for the co-op mirror. It runs the same
     * {@code applyRemote*} methods {@code GameManager.onWorldEvent} runs, and
     * {@link #remoteStartArgsNow} hands back exactly what a host would have put on the wire, so a
     * single process can measure that the producer and the consumer of the payload agree.
     */
    @Register
    public void applyRemoteEventCsv(int eventType, String key, float value, String argsCsv) {
        List<String> args = argsCsv == null || argsCsv.isEmpty()
                ? List.of() : List.of(argsCsv.split(",", -1));
        if (eventType == GameManager.WORLD_EVENT_RACE_START) applyRemoteStart(key, value, args);
        else if (eventType == GameManager.WORLD_EVENT_RACE_CHECKPOINT) applyRemoteCheckpoint(key, value, args);
        else if (eventType == GameManager.WORLD_EVENT_RACE_FINISH) applyRemoteFinish(key, value, args);
    }

    /** {@link #startArgs} joined by commas — the other half of {@link #applyRemoteEventCsv}. */
    @Register
    public String remoteStartArgsNow() { return String.join(",", startArgs()); }

    /** One line of race state — the debug console's readout. */
    @Register
    public String statusLine() {
        if (PHASE_IDLE.equals(phase)) return "no race";
        StringBuilder sb = new StringBuilder();
        sb.append(raceId).append(" [").append(phase).append("] ")
          .append(String.format("%.1f", elapsed)).append("s");
        if (timeLimit > 0f) sb.append(" / ").append(String.format("%.0f", timeLimit)).append("s");
        sb.append(" — ").append(raceCheckpointCount()).append(" cp × ").append(laps).append(" lap(s)");
        for (Racer r : racers.values()) {
            sb.append("\n  ").append(r.place > 0 ? r.place + "." : " -").append(' ')
              .append(r.characterId).append(r.human ? " (player)" : " (ai)")
              .append(r.finished ? String.format(" FINISHED %.2fs", r.finishTime)
                                 : " lap " + (r.lap + 1) + "/" + laps + " cp " + r.nextIndex);
        }
        return sb.toString();
    }

    private Character findCharacter(String characterId) {
        if (getNodeOrNull("/root/GameManager") instanceof GameManager gm) {
            return gm.findCharacterById(characterId);
        }
        return null;
    }
}
