package com.openworld.game;

import com.openworld.character.AICharacter;
import com.openworld.character.Character;
import com.openworld.character.Player;
import com.openworld.game.mission.MissionDirector;
import com.openworld.item.Pickup;
import com.openworld.net.NetworkManager;
import com.openworld.weapon.WeaponItem;
import com.openworld.world.ZoneManager;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.Time;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * Takes away what a fight leaves on the ground (user 2026-10-07: "after an arrest or a hospital the bodies and the
 * weapons are still lying all over the konbini, and the next engagement feels slower"). Before this nothing removed a
 * corpse but its zone unloading, and nothing ever removed a dropped weapon: each corpse is a full ~125-node body with
 * its skeleton still evaluated, each dropped weapon a rigid body.
 *
 * <p>Two kinds, the GTA rule for both -- gone once it has lain long enough AND nobody is looking:
 * <ul>
 *   <li><b>corpses</b>: a dead non-player {@link Character} ({@link Character#diedAtMs}) after {@link #corpseSeconds},
 *       out of this peer's view within {@link #viewDistance}; at most {@link #maxCorpses} (the oldest out of view go
 *       first); and every one past {@link #corpseMaxSeconds} whatever. A story character and a seated corpse (its car
 *       owns it) are left alone; a player's own body is {@link RespawnSystem}'s.</li>
 *   <li><b>dropped weapons</b>: a {@link WeaponItem} lying in the world that a character DROPPED (the
 *       {@link #DROPPED_META} meta {@code WeaponController} stamps; never a scene-placed pickup), on the same rules
 *       with {@link #pickupSeconds} / {@link #maxPickups} / {@link #pickupMaxSeconds}.</li>
 * </ul>
 * A respawn sweeps everything out of view at once ({@link #sweepSoon}).
 *
 * <p>Authority only: the host (or single player) decides. A corpse goes to every peer through the ordinary
 * {@code announceDespawn}; a dropped weapon through {@link GameManager#WORLD_EVENT_PICKUP_CLEARED}. Built in code by
 * {@link GameManager}; {@link #enabled} off is the control.
 */
@Script(className = "WorldJanitor")
public class WorldJanitor extends Node {

    /** Engine msec a weapon was dropped into the world: set by {@code WeaponController.returnWeaponToWorld}. */
    public static final String DROPPED_META = "dropped_at_ms";

    private static WorldJanitor instance;

    public static WorldJanitor get() { return instance != null && GD.isInstanceValid(instance) ? instance : null; }

    @Visible public boolean enabled = true;
    public boolean getEnabled() { return enabled; }
    public void setEnabled(boolean v) { enabled = v; }

    public double corpseSeconds = 30.0, corpseMaxSeconds = 180.0;
    public int maxCorpses = 12;
    public double pickupSeconds = 60.0, pickupMaxSeconds = 300.0;
    public int maxPickups = 24;
    /** Something is "being looked at" when it is in this peer's camera frustum within this distance (m). */
    public double viewDistance = 90.0;

    private static final double TICK = 1.0;
    private double clock;
    private double sweepIn = -1.0;
    private int corpsesFreed, pickupsFreed;

    @Override
    public void _ready() { instance = this; }

    @Override
    public void _exitTree() { if (instance == this) instance = null; }

    /** Sweep everything out of view in {@code seconds} (after a respawn: once the camera is at the new body). */
    public void sweepSoon(double seconds) { sweepIn = Math.max(0.0, seconds); }

    @Override
    public void _process(double delta) {
        if (!enabled || !authority()) return;
        if (sweepIn >= 0) {
            sweepIn -= delta;
            if (sweepIn < 0) { sweep(true); clock = 0; return; }
        }
        clock += delta;
        if (clock < TICK) return;
        clock = 0;
        sweep(false);
    }

    /** One pass. {@code all}: every corpse and dropped weapon out of view goes, whatever its age (a respawn). */
    private void sweep(boolean all) {
        if (getTree() == null) return;
        long now = Time.getTicksMsec();
        NetworkManager net = net();

        List<Character> corpses = new ArrayList<>();
        for (Node n : getTree().getNodesInGroup(new StringName("characters"))) {
            if (!(n instanceof Character c) || c instanceof Player || !GD.isInstanceValid(c) || c.isQueuedForDeletion()) continue;
            if (c.isAlive() || c.diedAtMs < 0 || c.currentVehicleNode != null) continue;
            if (c instanceof AICharacter ai && ai.storyCharacter) continue;
            MissionDirector md = MissionDirector.get();
            if (md != null && md.isMissionProtected(c)) continue;
            corpses.add(c);
        }
        corpses.sort(Comparator.comparingLong(c -> c.diedAtMs));
        int over = corpses.size() - maxCorpses;
        for (Character c : corpses) {
            double age = (now - c.diedAtMs) / 1000.0;
            boolean seen = inView(c.getGlobalPosition());
            boolean go = age >= corpseMaxSeconds
                    || (!seen && (all ? age >= 1.0 : (age >= corpseSeconds || over > 0)));
            if (!go) continue;
            over--;
            if (net != null && c.characterInfo != null) net.announceDespawn(c.characterInfo.characterId);
            c.queueFree();
            corpsesFreed++;
        }

        List<WeaponItem> drops = new ArrayList<>();
        for (Node n : getTree().getNodesInGroup(new StringName(Pickup.PICKUPS_GROUP))) {
            if (n instanceof WeaponItem w && GD.isInstanceValid(w) && !w.isQueuedForDeletion() && !w.isTaken()
                    && w.hasMeta(new StringName(DROPPED_META))) drops.add(w);
        }
        drops.sort(Comparator.comparingLong(this::droppedAt));
        over = drops.size() - maxPickups;
        for (WeaponItem w : drops) {
            double age = (now - droppedAt(w)) / 1000.0;
            boolean seen = inView(w.getGlobalPosition());
            boolean go = age >= pickupMaxSeconds
                    || (!seen && (all ? age >= 1.0 : (age >= pickupSeconds || over > 0)));
            if (!go) continue;
            over--;
            if (net != null && net.isNetworked() && w.pickupId != null && !w.pickupId.isEmpty())
                net.broadcastWorldEvent(GameManager.WORLD_EVENT_PICKUP_CLEARED, w.pickupId, 0f);
            freePickup(w);
            pickupsFreed++;
        }
    }

    /** Free a world pickup and the body it rides in (the body would free itself once empty; this is sooner). */
    public static void freePickup(Pickup p) {
        Node parent = p.getParent();
        if (parent instanceof com.openworld.item.PickupBody body) body.queueFree();
        else p.queueFree();
    }

    private long droppedAt(WeaponItem w) {
        Object v = w.getMeta(new StringName(DROPPED_META), 0L);
        return v instanceof Number num ? num.longValue() : 0L;
    }

    private boolean inView(Vector3 at) {
        ZoneManager z = ZoneManager.get();
        return z != null && z.inLocalView(at, viewDistance);
    }

    private NetworkManager net() {
        return getNodeOrNull("/root/NetworkManager") instanceof NetworkManager n && n.isNetworked() ? n : null;
    }

    private boolean authority() {
        NetworkManager n = net();
        return n == null || n.isServer();
    }

    /** "corpses freed,dropped weapons freed" for probes. */
    @Register
    public String freedNow() { return corpsesFreed + "," + pickupsFreed; }

    /** Run one pass now (probes); {@code all} as {@link #sweep}. */
    @Register
    public void sweepNow(boolean all) { sweep(all); }
}
