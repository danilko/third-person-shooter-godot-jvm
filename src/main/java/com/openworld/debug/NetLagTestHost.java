package com.openworld.debug;

import com.openworld.character.AICharacter;
import com.openworld.character.Character;
import com.openworld.character.CharacterInfo;
import com.openworld.character.Health;
import com.openworld.character.Player;
import com.openworld.movement.character.MovementType;
import com.openworld.net.NetStats;
import com.openworld.net.NetworkManager;
import com.openworld.weapon.FirearmItem;
import com.openworld.weapon.WeaponController;
import com.openworld.world.manager.ImpactManager;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.BoxShape3D;
import godot.api.CollisionShape3D;
import godot.api.Input;
import godot.api.Node;
import godot.api.OS;
import godot.api.PackedScene;
import godot.api.StaticBody3D;
import godot.core.NodePath;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

/**
 * Two-instance headless gate for PLAN.md N5 — host lag compensation for hitscan
 * ({@code tools/net/run_net_lag_test.sh}). Both processes hold every outgoing message {@code --lag-ms}
 * (the round trip is twice that plus a snapshot interval). The HOST runs a target that strafes left and
 * right at a constant speed; the CLIENT collects the scene's ASR1, aims its own view at where its screen
 * DRAWS the target's chest, and taps the trigger through {@code Input} only mid-sweep (never near a
 * turn, where the client's dead-reckoning is wrong by design). The host resolves each tap and prints
 * what it hit and how far it rewound. {@code --no-rewind} on the host is the control.
 */
@Script(className = "NetLagTestHost")
public class NetLagTestHost extends Node {

    private static final int PORT = 7793;
    private static final String TARGET_ID = "netlag-target";
    private static final String AI_SCENE = "res://src/main/resources/com/openworld/character/AICharacter.tscn";
    private static final Vector3 PICKUP_AT = new Vector3(0, 1.0, 6);
    private static final double TARGET_Z = -15.0;
    /** The strafe turns round past this |x|. */
    private static final double SWEEP_X = 6.0;
    /** The client only fires while the drawn target is inside this |x| — a steady strafe, not a turn. */
    private static final double FIRE_X = 3.0;
    private static final int PULLS = 24;
    private static final double TIMEOUT_S = 100.0;

    private boolean host;
    private int lagMs;
    private double clock;
    private NetworkManager net;

    // host
    private AICharacter target;
    private ScriptedInputController targetBrain;
    private double strafeSign = 1.0;
    private boolean sawClient;
    private double clientGoneAt = -1;
    private double speedSum;
    private int speedSamples;

    // client
    private int pullsDone;
    private double nextPullAt = -1;
    private int releaseInFrames = -1;
    private boolean finished;
    private java.util.List<String> lastSeenHits;

    @Register
    @Override
    public void _ready() {
        boolean noRewind = false;
        for (String a : OS.INSTANCE.getCmdlineUserArgs()) {
            if (a.equals("--role=host")) host = true;
            if (a.equals("--no-rewind")) noRewind = true;
            if (a.startsWith("--lag-ms=")) lagMs = Integer.parseInt(a.substring(9));
        }
        net = (NetworkManager) getNode("/root/NetworkManager");
        net.debugShots = true;
        net.debugSendDelayMs = lagMs;
        net.lagCompensation = !noRewind;

        box("Ground", new Vector3(200, 1, 200), new Vector3(0, -0.5, 0));
        box("Backstop", new Vector3(40, 12, 1), new Vector3(0, 6, -40));
        if (getTree().getFirstNodeInGroup("impact_manager") == null) addChild(new ImpactManager());

        if (host) {
            spawnTarget();
            net.hostServer(PORT);
        } else {
            net.joinServer("127.0.0.1", PORT);
        }
        GD.print("[netlag] role=" + (host ? "host" : "client") + " lag_ms=" + lagMs + " rewind=" + !noRewind);
    }

    private void box(String name, Vector3 size, Vector3 pos) {
        StaticBody3D b = new StaticBody3D();
        b.setName(name);
        CollisionShape3D cs = new CollisionShape3D();
        BoxShape3D shape = new BoxShape3D();
        shape.setSize(size);
        cs.setShape(shape);
        b.addChild(cs);
        addChild(b);
        b.setGlobalPosition(pos);
    }

    private void spawnTarget() {
        if (!(GD.INSTANCE.load(AI_SCENE) instanceof PackedScene ps)) return;
        if (!(ps.instantiate() instanceof AICharacter ai)) return;
        CharacterInfo info = new CharacterInfo();
        info.characterId = TARGET_ID;
        info.displayName = "Target";
        info.faction = "neutral";
        ai.characterInfo = info;
        ai.setPosition(new Vector3(0, 0.1, TARGET_Z));
        getNode("Characters").addChild(ai);
        targetBrain = new ScriptedInputController();
        targetBrain.setName("StrafeController");
        targetBrain.movementType = MovementType.WALK;
        ai.attachController(targetBrain);
        if (ai.getNodeOrNull(new NodePath("Health")) instanceof Health h) {
            h.maxHealth = 1_000_000f;
            h.resetFull();
        }
        target = ai;
    }

    @Register
    @Override
    public void _physicsProcess(double delta) {
        clock += delta;
        if (clock > TIMEOUT_S) finish("TIMEOUT");
        if (host) hostStep(); else clientStep();
    }

    private void hostStep() {
        if (target != null) {
            Vector3 p = target.getGlobalPosition();
            if (p.getX() > SWEEP_X) strafeSign = -1.0;
            if (p.getX() < -SWEEP_X) strafeSign = 1.0;
            // Hold the lane: a body that drifts in depth would change the shot's geometry between runs.
            targetBrain.move = new Vector3(strafeSign, 0, (TARGET_Z - p.getZ()) * 0.5).normalized();
            if (Math.abs(p.getX()) < FIRE_X) {
                speedSum += Math.hypot(target.getVelocity().getX(), target.getVelocity().getZ());
                speedSamples++;
            }
        }
        boolean client = false;
        for (Node node : getTree().getNodesInGroup(new StringName("characters"))) {
            if (node instanceof Player pl && pl.characterInfo != null && pl.characterInfo.ownerPeerId != 1) client = true;
        }
        if (client) sawClient = true;
        else if (sawClient && clientGoneAt < 0) clientGoneAt = clock;
        if (clientGoneAt >= 0 && clock - clientGoneAt > 1.0) finish("client left");
        // A disconnected client's body stays as a bot, so also stop once the shots have ended.
        long seen = NetStats.get("shot_accepted");
        if (seen != lastSeenShots) { lastSeenShots = seen; lastShotAt = clock; }
        if (seen >= PULLS - 2 && clock - lastShotAt > 4.0) finish("shots done");
    }

    private long lastSeenShots;
    private double lastShotAt;

    private void clientStep() {
        Player me = null;
        Character tgt = null;
        for (Node node : getTree().getNodesInGroup(new StringName("characters"))) {
            if (node instanceof Player p && p.characterInfo != null && net.isAuthorityFor(p.characterInfo)) me = p;
            if (node instanceof Character c && c.characterInfo != null && TARGET_ID.equals(c.characterInfo.characterId)) tgt = c;
        }
        if (me == null || tgt == null || !(me.getNodeOrNull(new NodePath("WeaponController")) instanceof WeaponController wc)) return;

        // The view goes onto where THIS screen draws the target's chest — the puppet's position.
        // From the camera actually drawing the frame (the TPS boom is above and beside the shoulder): the
        // shot converges on the point under the crosshair, so that point must be on the drawn chest.
        godot.api.Camera3D cam = getViewport().getCamera3d();
        Vector3 eye = cam != null ? cam.getGlobalPosition() : me.getGlobalPosition().plus(new Vector3(0, 1.5, 0));
        Vector3 to = tgt.getGlobalPosition().plus(new Vector3(0, 1.0, 0)).minus(eye);
        me.controlRotation.yaw = Math.toDegrees(Math.atan2(-to.getX(), -to.getZ()));
        me.controlRotation.pitch = Math.toDegrees(Math.atan2(to.getY(), Math.hypot(to.getX(), to.getZ())));

        FirearmItem gun = null;
        int slot = -1;
        for (int i = 0; i < wc.getSlotCount(); i++) {
            if (wc.getWeaponItem(i) instanceof FirearmItem f && f.pelletCount == 1) { gun = f; slot = i; }
        }
        if (gun == null) {
            if (me.getGlobalPosition().distanceTo(PICKUP_AT) > 0.6) me.setGlobalPosition(PICKUP_AT);
            return;
        }
        if (me.getGlobalPosition().distanceTo(new Vector3(0, 1, 0)) > 0.6 && nextPullAt < 0) {
            me.setGlobalPosition(new Vector3(0, 1, 0));   // back off the pickup to the firing spot
        }
        if (wc.getCurrentWeaponItem() != gun) {
            if (!wc.isWeaponTransitioning()) wc.onSetWeapon(slot);
            return;
        }
        if (nextPullAt < 0) nextPullAt = clock + 3.0;   // let the draw and the aim settle

        if (gun.lastShotPelletHits != lastSeenHits && !gun.lastShotPelletHits.isEmpty()) {
            lastSeenHits = gun.lastShotPelletHits;
            GD.print("[shot] client predicted #" + (pullsDone - 1) + " -> " + lastSeenHits
                    + String.format(" (drawn target x %.2f)", tgt.getGlobalPosition().getX()));
        }
        if (releaseInFrames >= 0 && --releaseInFrames < 0) Input.INSTANCE.actionRelease(new StringName("fire"));
        boolean steady = Math.abs(tgt.getGlobalPosition().getX()) < FIRE_X;
        if (pullsDone < PULLS && clock >= nextPullAt && releaseInFrames < 0 && steady) {
            gun.setMagazine(Math.max(gun.getMagazine(), 5));
            Input.INSTANCE.actionPress(new StringName("fire"), 1.0f);
            releaseInFrames = 2;
            pullsDone++;
            nextPullAt = clock + 0.7;   // lets bloom decay between taps
        }
        if (pullsDone >= PULLS && clock > nextPullAt + 2.0) finish("pulls done");
    }

    private void finish(String why) {
        if (finished) return;
        finished = true;
        StringBuilder sb = new StringBuilder("[netlag] SUMMARY role=" + (host ? "host" : "client") + " (" + why + ")");
        for (String k : new String[] {"shot_sent", "shot_accepted", "shot_rewound", "drop_rate_limited"}) {
            sb.append(' ').append(k).append('=').append(NetStats.get(k));
        }
        if (host) sb.append(String.format(" target_speed=%.2f", speedSamples > 0 ? speedSum / speedSamples : 0.0));
        else sb.append(" pulls=").append(pullsDone);
        GD.print(sb.toString());
        getTree().quit();
    }
}
