package com.openworld.game.mission;

import com.openworld.character.AICharacter;
import com.openworld.character.Faction;
import com.openworld.character.Health;
import com.openworld.character.Player;
import com.openworld.game.PlayerRegistry;
import com.openworld.net.NetworkManager;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.Node;
import godot.api.Node3D;
import godot.core.VariantArray;
import godot.global.GD;

/**
 * The first piece of story CONTENT on the shipped F1-F3 code (PLAN.md 4.8): "the konbini job", one mission with two
 * outcome variants, played in the streamed downtown.
 *
 * <ul>
 *   <li>A crew of named characters ({@code storyCharacter}, streamed by a Zone beside this node) loiters outside a
 *       konbini as {@code neutral}: nobody fights them until the job starts.</li>
 *   <li>A {@code ZoneTrigger} in front of the shop fires {@link #startBeat}. The handler starts the mission THROUGH
 *       the director (so its unlock rule still decides) and turns the crew {@code gang_a}, which is hostile to the
 *       player by the inherent rule.</li>
 *   <li>With the crew down and the boss under {@link #surrenderHealthFraction}, the boss SURRENDERS: turned
 *       {@code neutral} and sent running (FLEE). That is the choice. Shoot him anyway and the mission completes
 *       {@code BOSS_KILLED}; let him get {@link #spareDistance} away or {@link #spareSeconds} pass and it completes
 *       {@code BOSS_SPARED}. Killing the boss before he surrenders is also {@code BOSS_KILLED}.</li>
 *   <li>{@code m02_informant} is declared unlocked ONLY by {@code m01_konbini:BOSS_SPARED} -- the branch in the
 *       unlock graph a spared boss opens (the informant mission itself is not authored yet).</li>
 *   <li>Fails when every player is down, or when the boss's zone unloads mid-fight (the player left).</li>
 * </ul>
 *
 * The mission's objective is {@link MissionObjectiveType#SCRIPTED}: this node, not MissionManager's counter,
 * decides the outcome. Outcome decisions run on the host only (the director's rule: a beat runs on every peer and
 * gates its own authoritative effect); completion reaches clients through MissionManager's world events.
 */
@Script(className = "KonbiniMission")
public class KonbiniMission extends Node3D {

    public static final String VARIANT_KILLED = "BOSS_KILLED";
    public static final String VARIANT_SPARED = "BOSS_SPARED";

    @Export public String missionPath = "res://src/main/resources/com/openworld/game/mission/M01_Konbini.tres";
    @Export public String missionId = "m01_konbini";
    @Export public String startBeat = "m01_start";
    @Export public String bossId = "m01_boss";
    @Export public VariantArray<String> crewIds = new VariantArray<>(String.class);
    @Export public String hostileFaction = Faction.GANG_A;
    @Export public float surrenderHealthFraction = 0.5f;
    @Export public float spareDistance = 45f;
    @Export public float spareSeconds = 15f;
    @Export public String unlocksOnSpare = "m02_informant";
    /**
     * While the job runs, every {@code world.Door} within this of the node is UNLOCKED, so the player may open the
     * shop (its building is placed as the `_Open` variant, whose doors ship locked -- every other building in the
     * city is shut for good). Re-locked when the mission ends: a shop is open for the job, not for ever.
     */
    @Export public float doorUnlockRadius = 25f;

    /** IDLE, FIGHT, SURRENDER, DONE -- probe readout. */
    @Visible public String phase = "IDLE";
    @Visible public String outcome = "";

    private float surrenderTimer = 0f;
    private final java.util.List<com.openworld.world.Door> unlockedDoors = new java.util.ArrayList<>();

    @Register
    @Override
    public void _ready() {
        MissionDirector dir = MissionDirector.get();
        if (dir == null) {
            GD.printErr("[KonbiniMission] no MissionDirector autoload -- the mission cannot run");
            return;
        }
        dir.registerBeat(startBeat, this::onStart);
        if (!unlocksOnSpare.isEmpty()) {
            dir.declareUnlockOn(unlocksOnSpare, MissionDirector.variantKey(missionId, VARIANT_SPARED));
        }
    }

    private boolean isHost() {
        Node n = getNodeOrNull("/root/NetworkManager");
        return !(n instanceof NetworkManager net) || !net.isNetworked() || net.isServer();
    }

    private MissionManager manager() {
        Node n = getNodeOrNull("/root/MissionManager");
        return n instanceof MissionManager mm ? mm : null;
    }

    private boolean missionRunning() {
        MissionManager mm = manager();
        return mm != null && mm.isActive() && mm.getActiveMission() != null
                && missionId.equals(mm.getActiveMission().missionId);
    }

    /** The start beat: every peer runs it, the host starts the job. */
    private void onStart() {
        if (!isHost() || !"IDLE".equals(phase)) return;
        MissionDirector dir = MissionDirector.get();
        if (dir == null || !dir.startMissionFromPath(missionPath)) return;
        for (String id : allIds()) {
            AICharacter ai = dir.getNamedCharacter(id);
            if (ai != null) ai.setFaction(hostileFaction);
        }
        setDoorsLocked(false);
        phase = "FIGHT";
        GD.print("[KonbiniMission] '" + missionId + "' started: the crew turns " + hostileFaction
                + ", " + unlockedDoors.size() + " door(s) unlocked");
    }

    /** Console / probe entry: start the job as if the trigger had fired. */
    @Register
    public boolean startNow() {
        MissionDirector dir = MissionDirector.get();
        if (dir == null) return false;
        dir.triggerBeat(startBeat);
        return "FIGHT".equals(phase);
    }

    private java.util.List<String> allIds() {
        java.util.List<String> ids = new java.util.ArrayList<>();
        ids.add(bossId);
        for (int i = 0; i < crewIds.size(); i++) ids.add(crewIds.get(i));
        return ids;
    }

    private static boolean alive(AICharacter ai) {
        return ai != null && GD.isInstanceValid(ai) && !ai.isDead() && ai.isAlive();
    }

    @Register
    @Override
    public void _physicsProcess(double delta) {
        if (!isHost() || !("FIGHT".equals(phase) || "SURRENDER".equals(phase))) return;
        if (!missionRunning()) {           // failed or completed elsewhere (console, save load)
            phase = "DONE";
            return;
        }
        MissionDirector dir = MissionDirector.get();
        if (dir == null) return;
        if (allPlayersDown()) {
            finish(null, "every player is down");
            return;
        }
        AICharacter boss = dir.getNamedCharacter(bossId);
        boolean bossLoaded = boss != null && GD.isInstanceValid(boss);
        if (bossLoaded && (boss.isDead() || !boss.isAlive())) {
            finish(VARIANT_KILLED, null);
            return;
        }
        if (!bossLoaded) {
            finish(null, "left the area");
            return;
        }
        if ("FIGHT".equals(phase)) {
            int crewUp = 0;
            for (int i = 0; i < crewIds.size(); i++) {
                if (alive(dir.getNamedCharacter(crewIds.get(i)))) crewUp++;
            }
            Node hn = boss.getNodeOrNull("Health");
            if (crewUp == 0 && hn instanceof Health h && h.getCurrentHealth() < surrenderHealthFraction * h.maxHealth) {
                boss.setFaction(Faction.NEUTRAL);
                dir.commandState(bossId, ScriptCommand.STATE_FLEE);
                surrenderTimer = 0f;
                phase = "SURRENDER";
                GD.print("[KonbiniMission] the boss surrenders and runs -- shoot him or let him go");
            }
        } else {
            surrenderTimer += (float) delta;
            if (surrenderTimer >= spareSeconds || nearestPlayerDistance(boss) >= spareDistance) {
                dir.releaseCharacter(bossId);
                finish(VARIANT_SPARED, null);
            }
        }
    }

    private void finish(String variant, String failReason) {
        MissionManager mm = manager();
        setDoorsLocked(true);
        phase = "DONE";
        if (mm == null) return;
        if (variant != null) {
            outcome = variant;
            mm.completeMission("player", variant);
        } else {
            outcome = "FAILED: " + failReason;
            mm.failMission(failReason);
        }
    }

    /**
     * Unlock (or re-lock) the doors of the mission's own building. Doors are in {@code Breakable.BREAKABLE_GROUP},
     * so this is a group read, not a tree walk; a door that has streamed out since is simply gone from the list.
     */
    private void setDoorsLocked(boolean locked) {
        if (!locked) {
            unlockedDoors.clear();
            if (getTree() == null) return;
            for (Node n : getTree().getNodesInGroup(new godot.core.StringName(
                    com.openworld.world.Breakable.BREAKABLE_GROUP))) {
                // only a LOCKED door: a shop (or the player's home base) that is already open stays open -- it is
                // not the mission's to shut when the job ends
                if (n instanceof com.openworld.world.Door door && door.isLocked()
                        && door.getGlobalPosition().distanceTo(getGlobalPosition()) <= doorUnlockRadius) {
                    door.setLocked(false);
                    unlockedDoors.add(door);
                }
            }
            return;
        }
        for (com.openworld.world.Door door : unlockedDoors) {
            if (GD.isInstanceValid(door)) door.setLocked(true);
        }
        unlockedDoors.clear();
    }

    /** How many doors this job has unlocked -- probe readout. */
    @Register
    public int unlockedDoorsNow() { return unlockedDoors.size(); }

    private static boolean allPlayersDown() {
        boolean any = false;
        for (Player p : PlayerRegistry.getPlayers()) {
            if (p == null || !GD.isInstanceValid(p)) continue;
            any = true;
            if (p.isAlive()) return false;
        }
        return any;
    }

    private static double nearestPlayerDistance(AICharacter ai) {
        double best = Double.MAX_VALUE;
        for (Player p : PlayerRegistry.getPlayers()) {
            if (p == null || !GD.isInstanceValid(p) || !p.isAlive()) continue;
            best = Math.min(best, p.getGlobalPosition().distanceTo(ai.getGlobalPosition()));
        }
        return best;
    }
}
