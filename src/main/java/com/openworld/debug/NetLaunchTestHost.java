package com.openworld.debug;

import com.openworld.character.AICharacter;
import com.openworld.character.Character;
import com.openworld.character.CharacterInfo;
import com.openworld.character.Health;
import com.openworld.character.Player;
import com.openworld.net.NetStats;
import com.openworld.net.NetworkManager;
import com.openworld.weapon.ProjectileItem;
import com.openworld.weapon.ThrowableItem;
import com.openworld.weapon.WeaponController;
import com.openworld.weapon.WeaponItem;
import com.openworld.world.manager.ExplosionManager;
import com.openworld.world.manager.ImpactManager;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.BoxShape3D;
import godot.api.CollisionShape3D;
import godot.api.Input;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.OS;
import godot.api.PackedScene;
import godot.api.StaticBody3D;
import godot.core.NodePath;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

/**
 * Three-instance headless check for PLAN.md N4 — projectiles flown by the host ({@code tools/net/run_net_launch_test.sh}).
 *
 * <p>The HOST spawns a still target and a backstop. The CLIENT collects the scene's ATL1 launcher and FRG1 grenades,
 * fires 3 rockets and throws 2 grenades at the target through the {@code Input} singleton — each a cosmetic
 * copy it predicts plus ONE {@code MSG_LAUNCH} the host validates and flies — then sends forged launches. An
 * OBSERVER watches from the side and sees every launch only as its puppet's fire cue. Every peer must draw
 * exactly one explosion per blast, where the host's projectile went off, and only the host deals damage.
 */
@Script(className = "NetLaunchTestHost")
public class NetLaunchTestHost extends Node3D {

    private static final int PORT = 7795;
    private static final String TARGET_ID = "netlaunch-target";
    private static final String AI_SCENE = "res://src/main/resources/com/openworld/character/AICharacter.tscn";
    private static final Vector3 ATL1_AT = new Vector3(0, 1.0, 6);
    private static final Vector3 FRG1_AT = new Vector3(4, 1.0, 6);
    private static final Vector3 TARGET_AT = new Vector3(0, 0.1, -12);
    private static final Vector3 FIRE_FROM = new Vector3(0, 0.1, 0);
    private static final int ROCKETS = 3;
    private static final int GRENADES = 2;
    private static final double TIMEOUT_S = 110.0;

    private String role = "client";
    private boolean dropDetonations;
    private double clock;
    private NetworkManager net;

    private boolean sawPeer;
    private double peerGoneAt = -1;
    private Health targetHealth;
    private float targetHpStart;

    private int rocketsDone, grenadesDone;
    private double nextAt = -1;
    private int releaseInFrames = -1;
    private double doneAt = -1;
    private int forgeStepDone = -1;

    @Register
    @Override
    public void _ready() {
        for (String a : OS.INSTANCE.getCmdlineUserArgs()) {
            if (a.equals("--role=host")) role = "host";
            if (a.equals("--role=observer")) role = "observer";
            if (a.equals("--drop-detonations")) dropDetonations = true;
        }
        net = getNodeOrNull("/root/NetworkManager") instanceof NetworkManager nm ? nm : null;
        net.debugShots = true;
        net.debugDropDetonations = dropDetonations;
        box("Ground", new Vector3(200, 1, 200), new Vector3(0, -0.5, 0));
        box("Backstop", new Vector3(30, 12, 1), new Vector3(0, 6, -16));
        if (getTree().getFirstNodeInGroup("impact_manager") == null) addChild(new ImpactManager());
        if (getTree().getFirstNodeInGroup("explosion_manager") == null) addChild(new ExplosionManager());
        if (role.equals("host")) {
            spawnTarget();
            net.hostServer(PORT);
        } else {
            net.joinServer("127.0.0.1", PORT);
        }
        GD.print("[netlaunch] role=" + role);
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
        if (!(GD.INSTANCE.load(AI_SCENE) instanceof PackedScene ps) || !(ps.instantiate() instanceof AICharacter ai)) return;
        CharacterInfo info = new CharacterInfo();
        info.characterId = TARGET_ID;
        info.displayName = "Target";
        info.faction = "neutral";
        ai.characterInfo = info;
        ai.setPosition(TARGET_AT);
        getNodeOrNull("Characters").addChild(ai);
        ScriptedInputController still = new ScriptedInputController();
        still.setName("StillController");
        ai.attachController(still);
        if (ai.getNodeOrNull(new NodePath("Health")) instanceof Health h) {
            h.maxHealth = 100000f;
            h.resetFull();
            targetHealth = h;
            targetHpStart = h.getCurrentHealth();
        }
    }

    @Register
    @Override
    public void _physicsProcess(double delta) {
        clock += delta;
        if (clock > TIMEOUT_S) finish("TIMEOUT");
        switch (role) {
            case "host" -> hostStep();
            case "observer" -> observerStep();
            default -> clientStep();
        }
    }

    private Player me() {
        for (Node node : getTree().getNodesInGroup(new StringName("characters"))) {
            if (node instanceof Player p && p.characterInfo != null && net.isAuthorityFor(p.characterInfo)) return p;
        }
        return null;
    }

    private int players() {
        int n = 0;
        for (Node node : getTree().getNodesInGroup(new StringName("characters"))) if (node instanceof Player) n++;
        return n;
    }

    private void hostStep() {
        boolean peers = players() > 1;
        if (peers) sawPeer = true;
        else if (sawPeer && peerGoneAt < 0) peerGoneAt = clock;
        if (peerGoneAt >= 0 && clock - peerGoneAt > 1.0) finish("peers left");
    }

    private void observerStep() {
        Player p = me();
        if (p != null) {
            Vector3 spot = new Vector3(dropDetonations ? -15 : 15, 0.1, 10);
            if (p.getGlobalPosition().distanceTo(spot) > 1.0) p.setGlobalPosition(spot);
        }
        if (net.isNetworked() && clock > 1.0) sawPeer = true;
        if (sawPeer && !net.isNetworked()) finish("host left");
    }

    private void clientStep() {
        Player me = me();
        Character target = null;
        for (Node node : getTree().getNodesInGroup(new StringName("characters"))) {
            if (node instanceof Character c && c.characterInfo != null && TARGET_ID.equals(c.characterInfo.characterId)) target = c;
        }
        if (me == null || target == null || !(me.getNodeOrNull(new NodePath("WeaponController")) instanceof WeaponController wc)) return;

        int launcherSlot = -1, grenadeSlot = -1;
        for (int i = 0; i < wc.getSlotCount(); i++) {
            WeaponItem w = wc.getWeaponItem(i);
            if (w instanceof ProjectileItem) launcherSlot = i;
            if (w instanceof ThrowableItem) grenadeSlot = i;
        }
        if (launcherSlot < 0) { if (me.getGlobalPosition().distanceTo(ATL1_AT) > 0.6) me.setGlobalPosition(ATL1_AT); return; }
        if (grenadeSlot < 0) { if (me.getGlobalPosition().distanceTo(FRG1_AT) > 0.6) me.setGlobalPosition(FRG1_AT); return; }
        if (nextAt < 0) {
            if (players() < 3) return;   // both observers (the host has no player) must be watching first
            nextAt = clock + 2.0;
        }
        if (me.getGlobalPosition().distanceTo(FIRE_FROM) > 0.3) me.setGlobalPosition(FIRE_FROM);
        Vector3 eye = me.getGlobalPosition().plus(new Vector3(0, 1.5, 0));
        Vector3 to = target.getGlobalPosition().plus(new Vector3(0, 1.1, 0)).minus(eye);
        me.controlRotation.yaw = Math.toDegrees(Math.atan2(-to.getX(), -to.getZ()));
        me.controlRotation.pitch = Math.toDegrees(Math.atan2(to.getY(), Math.hypot(to.getX(), to.getZ())));

        if (releaseInFrames >= 0 && --releaseInFrames < 0) Input.INSTANCE.actionRelease(new StringName("fire"));
        boolean rockets = rocketsDone < ROCKETS;
        int want = rockets ? launcherSlot : grenadeSlot;
        if (rocketsDone + grenadesDone < ROCKETS + GRENADES) {
            // Never switch while the last press may still be held back by the aim gate (one frame, W21):
            // switching then drops it. Measured: rocket 3 lost exactly that way.
            if (wc.getWeapon() != want) {
                if (releaseInFrames < 0 && clock >= nextAt - 1.0 && !wc.isWeaponTransitioning()) {
                    wc.onSetWeapon(want);
                    nextAt = Math.max(nextAt, clock + 1.0);
                }
                return;
            }
            if (clock >= nextAt && releaseInFrames < 0) {
                WeaponItem w = wc.getWeaponItem(want);
                w.setMagazine(Math.max(w.getMagazine(), rockets ? 1 : 2));
                Input.INSTANCE.actionPress(new StringName("fire"), 1.0f);
                releaseInFrames = 3;
                if (rockets) rocketsDone++; else grenadesDone++;
                GD.print("[launch] client fired " + (rockets ? "rocket " + rocketsDone : "grenade " + grenadesDone)
                        + " | holding " + (wc.getCurrentWeaponItem() != null ? wc.getCurrentWeaponItem().getClass().getSimpleName() : "-")
                        + " mag " + w.getMagazine() + " canUse " + w.canUse() + " | " + wc.fireGateReport());
                nextAt = clock + 2.0;
            }
            return;
        }
        if (doneAt < 0) doneAt = clock;
        if (clock - doneAt > 6.0) forgeStep(me, target, wc, launcherSlot);   // grenades (3 s fuse) have gone off
    }

    /** Forged launches, one per 1.2 s, each refused for its own reason (the budget refills in between). */
    private void forgeStep(Player me, Character target, WeaponController wc, int slot) {
        int step = (int) Math.floor((clock - doneAt - 6.0) / 1.2);
        if (step <= forgeStepDone) return;
        forgeStepDone = step;
        String id = me.characterInfo.characterId;
        Vector3 origin = me.getGlobalPosition().plus(new Vector3(0, 1.4, 0));
        Vector3 aim = target.getGlobalPosition().plus(new Vector3(0, 1.1, 0)).minus(origin).normalized();
        switch (step) {
            case 0 -> { long last = wc.nextShotSeq() - 1; net.sendLaunch(id, slot, last, origin, aim); GD.print("[forge] replayed launch #" + last); }
            case 1 -> { net.sendLaunch(id, slot, wc.nextShotSeq(), origin.plus(new Vector3(10, 0, 0)), aim); GD.print("[forge] launch from 10 m away"); }
            case 2 -> { net.sendLaunch(TARGET_ID, slot, wc.nextShotSeq(), target.getGlobalPosition().plus(new Vector3(0, 1.4, 0)), aim.times(-1f)); GD.print("[forge] launch for a body I do not own"); }
            case 3 -> { net.sendLaunch(id, slot, wc.nextShotSeq(), origin, aim.times(-1f)); GD.print("[forge] launch aimed backwards"); }
            case 7 -> finish("launches + forgeries done");
            default -> { }
        }
    }

    private boolean finished;

    private void finish(String why) {
        if (finished) return;
        finished = true;
        StringBuilder sb = new StringBuilder("[netlaunch] SUMMARY role=" + role + (dropDetonations ? "-drop" : "") + " (" + why + ")");
        for (String k : new String[] {"launch_sent", "launch_accepted", "launch_invalid", "launch_no_launcher",
                "launch_rejected_stale_seq", "launch_rejected_origin_too_far", "launch_rejected_not_owner",
                "launch_rejected_aim_diverged", "launch_rejected_too_fast", "launch_cue_host_skipped",
                "detonation_broadcast", "detonation_received", "detonation_snapped", "detonation_no_local_copy",
                "detonation_local_timeout", "detonation_dropped_debug", "explosion_vfx", "damage_request_sent", "damage_relay_suppressed",
                "drop_rate_limited"}) {
            sb.append(' ').append(k).append('=').append(NetStats.get(k));
        }
        if (targetHealth != null) sb.append(String.format(" target_damage=%.1f", targetHpStart - targetHealth.getCurrentHealth()));
        if (role.equals("client")) sb.append(" rockets=").append(rocketsDone).append(" grenades=").append(grenadesDone);
        GD.print(sb.toString());
        getTree().quit();
    }
}
