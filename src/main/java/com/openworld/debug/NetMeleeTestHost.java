package com.openworld.debug;

import com.openworld.character.AICharacter;
import com.openworld.character.Character;
import com.openworld.character.CharacterInfo;
import com.openworld.character.Health;
import com.openworld.character.Player;
import com.openworld.net.DamageRequestPolicy;
import com.openworld.net.NetStats;
import com.openworld.net.NetworkManager;
import com.openworld.weapon.KnifeItem;
import com.openworld.weapon.WeaponController;
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
 * Two-instance headless check for PLAN.md N2 — melee resolved on the host, and the damage-request hole closed.
 * Run as two processes of {@code NetMeleeTest.tscn} ({@code tools/net/run_net_melee_test.sh}):
 *
 * <p>The HOST spawns a still target (an AICharacter driven by a {@link ScriptedInputController}). The CLIENT
 * walks onto the scene's MEW1 knife (the host-arbitrated pickup), stands in reach of the target and taps fire
 * through the {@code Input} singleton, so the shipped {@code PlayerController → WeaponController → KnifeItem}
 * path runs: each tap is a stab the client PREDICTS (impact, hitstop) and the host RESOLVES from the
 * swing's inputs ({@code MSG_MELEE}). Then it sends what a forged client would: damage requests naming an
 * attacker it does not own, "self" damage on someone else, an unattributed request, absurd damage, and swings
 * replayed, from 10 m away and for a body it does not own. Both sides print a SUMMARY the script compares.
 */
@Script(className = "NetMeleeTestHost")
public class NetMeleeTestHost extends Node3D {

    private static final int PORT = 7793;
    private static final String TARGET_ID = "netmelee-target";
    private static final String AI_SCENE = "res://src/main/resources/com/openworld/character/AICharacter.tscn";
    private static final Vector3 PICKUP_AT = new Vector3(0, 1.0, 6);
    private static final Vector3 TARGET_AT = new Vector3(0, 0.1, -12);
    /** How far in front of the target the client stands: in reach of its chest. */
    private static final double STAND_GAP_M = 1.1;
    private static final int TAPS = 6;
    private static final double TIMEOUT_S = 90.0;

    private boolean host;
    private double clock;
    private NetworkManager net;

    // host
    private boolean sawClient;
    private double clientGoneAt = -1;
    private Health targetHealth;
    private float targetHpStart;

    // client
    private int tapsDone;
    private double nextTapAt = -1;
    private int releaseInFrames = -1;
    private double doneAt = -1;
    private int forgeStepDone = -1;

    @Register
    @Override
    public void _ready() {
        for (String a : OS.INSTANCE.getCmdlineUserArgs()) if (a.equals("--role=host")) host = true;
        Node n = getNodeOrNull("/root/NetworkManager");
        net = n instanceof NetworkManager nm ? nm : null;
        net.debugShots = true;
        box("Ground", new Vector3(200, 1, 200), new Vector3(0, -0.5, 0));
        if (getTree().getFirstNodeInGroup("impact_manager") == null) addChild(new ImpactManager());
        if (host) {
            spawnTarget();
            net.hostServer(PORT);
        } else {
            net.joinServer("127.0.0.1", PORT);
        }
        GD.print("[netmelee] role=" + (host ? "host" : "client"));
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
        if (host) hostStep(); else clientStep();
    }

    private void hostStep() {
        boolean client = false;
        for (Node node : getTree().getNodesInGroup(new StringName("characters"))) {
            if (node instanceof Player p && p.characterInfo != null && p.characterInfo.ownerPeerId != 1) client = true;
        }
        if (client) sawClient = true;
        else if (sawClient && clientGoneAt < 0) clientGoneAt = clock;
        if (clientGoneAt >= 0 && clock - clientGoneAt > 1.0) finish("client left");
        // The last forgery (a swing for a body the client does not own) has arrived: give stragglers a moment.
        if (NetStats.get("melee_rejected_not_owner") >= 1) {
            if (lastForgeryAt < 0) lastForgeryAt = clock;
            if (clock - lastForgeryAt > 2.0) finish("client done");
        }
    }

    private double lastForgeryAt = -1;

    private void clientStep() {
        Player me = null;
        Character target = null;
        for (Node node : getTree().getNodesInGroup(new StringName("characters"))) {
            if (node instanceof Player p && p.characterInfo != null && net.isAuthorityFor(p.characterInfo)) me = p;
            if (node instanceof Character c && c.characterInfo != null && TARGET_ID.equals(c.characterInfo.characterId)) target = c;
        }
        if (me == null || target == null || !(me.getNodeOrNull(new NodePath("WeaponController")) instanceof WeaponController wc)) return;

        KnifeItem knife = null;
        int knifeSlot = -1;
        for (int i = 0; i < wc.getSlotCount(); i++) {
            if (wc.getWeaponItem(i) instanceof KnifeItem k) { knife = k; knifeSlot = i; }
        }
        if (knife == null) {
            if (me.getGlobalPosition().distanceTo(PICKUP_AT) > 0.6) me.setGlobalPosition(PICKUP_AT);
            return;
        }
        if (wc.getCurrentWeaponItem() != knife) {
            if (!wc.isWeaponTransitioning()) wc.onSetWeapon(knifeSlot);
            return;
        }
        // Stand in reach and look at the target's chest (world yaw, positive pitch up). Each stab knocks the
        // target back (measured 1.10 -> 1.93 m over three hits), so follow it the way a player closes in.
        Vector3 stand = target.getGlobalPosition().plus(new Vector3(0, 0, STAND_GAP_M));
        if (me.getGlobalPosition().distanceTo(stand) > 0.15) me.setGlobalPosition(stand);
        Vector3 eye = me.getGlobalPosition().plus(new Vector3(0, 1.5, 0));
        Vector3 to = target.getGlobalPosition().plus(new Vector3(0, 1.2, 0)).minus(eye);
        me.controlRotation.yaw = Math.toDegrees(Math.atan2(-to.getX(), -to.getZ()));
        me.controlRotation.pitch = Math.toDegrees(Math.atan2(to.getY(), Math.hypot(to.getX(), to.getZ())));
        if (nextTapAt < 0) nextTapAt = clock + 2.0;   // the draw and the host's copy of the stand settle

        if (releaseInFrames >= 0 && --releaseInFrames < 0) Input.INSTANCE.actionRelease(new StringName("fire"));
        if (tapsDone < TAPS && clock >= nextTapAt && releaseInFrames < 0) {
            GD.print(String.format("[tap] #%d me %s target %s dist %.2f", tapsDone, me.getGlobalPosition(), target.getGlobalPosition(),
                    me.getGlobalPosition().distanceTo(target.getGlobalPosition())));
            Input.INSTANCE.actionPress(new StringName("fire"), 1.0f);
            releaseInFrames = 3;                          // a tap: the knife stabs (step 0)
            tapsDone++;
            nextTapAt = clock + 1.5;                      // past the swing and the combo reset
        }
        if (tapsDone >= TAPS && doneAt < 0 && clock >= nextTapAt) doneAt = clock;
        if (doneAt >= 0) forgeStep(me, target, wc, knifeSlot);
    }

    /** What a forged client sends, one per 0.5 s, each refused for its own reason. */
    private void forgeStep(Player me, Character target, WeaponController wc, int slot) {
        int step = (int) Math.floor((clock - doneAt) / 0.5);
        if (step <= forgeStepDone) return;
        forgeStepDone = step;
        String myId = me.characterInfo.characterId;
        Vector3 chest = me.getGlobalPosition().plus(new Vector3(0, 1.2, 0));
        Vector3 aim = target.getGlobalPosition().plus(new Vector3(0, 1.2, 0)).minus(chest).normalized();
        switch (step) {
            case 0 -> { net.requestDamage(TARGET_ID, TARGET_ID, DamageRequestPolicy.Kind.SELF, 5000f, false, "forged", "x", "x");
                        GD.print("[forge] damage naming an attacker I do not own"); }
            case 1 -> { net.requestDamage(TARGET_ID, myId, DamageRequestPolicy.Kind.SELF, 5000f, false, "forged", "x", "x");
                        GD.print("[forge] 'self' damage on someone else"); }
            case 2 -> { net.requestDamage(TARGET_ID, "", DamageRequestPolicy.Kind.AREA, 5000f, false, "forged", "x", "x");
                        GD.print("[forge] unattributed damage"); }
            case 3 -> { net.requestDamage(myId, myId, DamageRequestPolicy.Kind.SELF, 100000f, false, "forged", "x", "x");
                        GD.print("[forge] absurd self damage"); }
            case 4 -> { net.requestDamage(myId, myId, DamageRequestPolicy.Kind.SELF, 1f, false, "Fall", "", "");
                        GD.print("[honest] one point of fall damage on my own body"); }
            case 5 -> { long last = wc.nextShotSeq() - 1;   // the counter the last honest swing used
                        net.sendMelee(myId, slot, last, 0, chest, aim); GD.print("[forge] replayed swing #" + last); }
            case 6 -> { net.sendMelee(myId, slot, wc.nextShotSeq(), 0, chest.plus(new Vector3(10, 0, 0)), aim);
                        GD.print("[forge] swing from 10 m away"); }
            case 7 -> { net.sendMelee(TARGET_ID, slot, wc.nextShotSeq(), 0, target.getGlobalPosition().plus(new Vector3(0, 1.2, 0)), aim.times(-1f));
                        GD.print("[forge] swing for a body I do not own"); }
            case 8 -> { net.requestDamage(TARGET_ID, myId, DamageRequestPolicy.Kind.AREA, 50f, false, "forged", "x", "x");
                        GD.print("[forge] area damage (refused since N4)"); }
            case 10 -> finish("taps + forgeries done");
            default -> { }
        }
    }

    private boolean finished;

    private void finish(String why) {
        if (finished) return;
        finished = true;
        StringBuilder sb = new StringBuilder("[netmelee] SUMMARY role=" + (host ? "host" : "client") + " (" + why + ")");
        for (String k : new String[] {"melee_sent", "melee_accepted", "melee_invalid", "melee_resolved_hits",
                "melee_predicted_hits", "melee_rejected_stale_seq", "melee_rejected_origin_too_far",
                "melee_rejected_not_owner", "melee_rejected_too_fast", "melee_rejected_aim_diverged",
                "damage_request_sent", "damage_request_accepted", "damage_request_rejected_not_owner",
                "damage_request_rejected_self_mismatch", "damage_request_rejected_damage_too_high",
                "damage_request_rejected_kind_refused",
                "drop_invalid_damage_request", "drop_rate_limited"}) {
            sb.append(' ').append(k).append('=').append(NetStats.get(k));
        }
        if (host && targetHealth != null) {
            sb.append(String.format(" target_damage=%.2f", targetHpStart - targetHealth.getCurrentHealth()));
        }
        if (!host) sb.append(" taps=").append(tapsDone);
        GD.print(sb.toString());
        getTree().quit();
    }
}
