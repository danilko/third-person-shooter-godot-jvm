package com.openworld.world;

import com.openworld.net.NetworkManager;
import com.openworld.world.manager.ParticleManager;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.CollisionShape3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.BitSet;

/**
 * Every breakable window of ONE building (PLAN.md 1g g; build_building_scenes.gd `_add_panes`): this node is the
 * building's {@code Panes} holder, and each child {@code Pane<n>} is a PLAIN StaticBody3D (WORLD layer, an
 * {@code IntactVisual} mesh and a {@code Glass} box) -- no script per pane, because a department store has over a
 * thousand windows and a JVM-scripted node each would make streaming the building in a hitch. A pane obeys the car's
 * glass rule (world.GlassPanes): any hit breaks it. Breaks are host-authoritative and replicated through the existing
 * {@code GameManager.WORLD_EVENT_BREAKABLE} keyed {@code <this node's path>#<pane index>}, with a late-join baseline
 * (NetworkManager.sendBaselineBreakables). A broken pane comes back after {@link #restoreDelay}.
 */
@Script(className = "PaneSet")
public class PaneSet extends Node3D {

    public static final String GROUP = "pane_set";

    /** Seconds before a broken pane is whole again (host-authoritative; 0 = never). */
    @Export public float restoreDelay = 180.0f;

    private final BitSet broken = new BitSet();
    private double[] restoreAt = new double[0];
    private double clock;
    private ParticleManager particles;

    @Register
    @Override
    public void _ready() {
        addToGroup(new StringName(GROUP));
        restoreAt = new double[getChildCount()];
        setPhysicsProcess(false);
    }

    /** The index of {@code pane} (a direct child of this set), or -1. */
    public int indexOf(Node pane) {
        return pane != null && pane.getParent() == this ? pane.getIndex() : -1;
    }

    public boolean isBroken(int i) { return i >= 0 && broken.get(i); }

    @Register public boolean paneBrokenNow(int i) { return isBroken(i); }

    @Register public int brokenCountNow() { return broken.cardinality(); }

    /** Authority: a hit of any strength breaks a whole pane (a client ignores it; the host's break replicates). */
    public void hit(int i, Vector3 at) {
        if (isBroken(i) || i < 0 || i >= getChildCount()) return;
        NetworkManager net = getNodeOrNull("/root/NetworkManager") instanceof NetworkManager n ? n : null;
        if (net != null && net.isNetworked() && !net.isServer()) return;
        breakNow(i, true);
    }

    /** Break pane {@code i} now; {@code broadcast} on the authority. Idempotent. */
    public void breakNow(int i, boolean broadcast) {
        if (isBroken(i) || i < 0 || i >= getChildCount()) return;
        broken.set(i);
        Node pane = getChild(i);
        setIntact(pane, false);
        if (pane instanceof Node3D p3) {
            Vector3 at = p3.getGlobalPosition();
            if (pane.getNodeOrNull("Glass") instanceof Node3D g) at = g.getGlobalPosition();
            ParticleManager pm = particles();
            if (pm != null) pm.spawn(SurfaceType.GLASS, at);
            // no shatter sound for now (user, 2026-10-08: the layered placeholder read as awkward)
        }
        if (broadcast) {
            if (restoreDelay > 0f) {
                if (restoreAt.length < getChildCount()) restoreAt = java.util.Arrays.copyOf(restoreAt, getChildCount());
                restoreAt[i] = clock + restoreDelay;
                setPhysicsProcess(true);
            }
            send(i, 1f);
        }
    }

    /** Make pane {@code i} whole again; {@code broadcast} on the authority. Idempotent. */
    public void restore(int i, boolean broadcast) {
        if (!isBroken(i)) return;
        broken.clear(i);
        setIntact(getChild(i), true);
        if (broadcast) send(i, 0f);
    }

    @Register public void restoreNow(int i) { restore(i, true); }

    @Register
    @Override
    public void _physicsProcess(double delta) {
        clock += delta;
        boolean pending = false;
        for (int i = broken.nextSetBit(0); i >= 0; i = broken.nextSetBit(i + 1)) {
            if (i < restoreAt.length && restoreAt[i] > 0.0) {
                if (clock >= restoreAt[i]) { restoreAt[i] = 0.0; restore(i, true); }
                else pending = true;
            }
        }
        if (!pending) setPhysicsProcess(false);
    }

    /** Every broken pane's replication key (the late-join baseline). */
    public java.util.List<String> brokenKeys() {
        java.util.List<String> out = new java.util.ArrayList<>();
        for (int i = broken.nextSetBit(0); i >= 0; i = broken.nextSetBit(i + 1)) out.add(keyOf(i));
        return out;
    }

    public String keyOf(int i) { return getPath().getPath() + "#" + i; }

    private void send(int i, float value) {
        if (getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net)
            net.broadcastWorldEvent(com.openworld.game.GameManager.WORLD_EVENT_BREAKABLE, keyOf(i), value);
    }

    private static void setIntact(Node pane, boolean intact) {
        for (Node c : pane.getChildren()) {
            if (c instanceof CollisionShape3D cs) cs.setDeferred(new StringName("disabled"), !intact);
            else if (c instanceof Node3D v) v.setVisible(intact);
        }
    }

    private ParticleManager particles() {
        if (particles == null && getTree() != null
                && getTree().getFirstNodeInGroup(new StringName("particle_manager")) instanceof ParticleManager pm)
            particles = pm;
        return particles;
    }

    /** The set and pane a replication key names, applied on a client (GameManager.applyBreakableState). */
    public static boolean applyRemote(Node any, String key, float value) {
        int hash = key.lastIndexOf('#');
        if (hash < 0 || any == null || any.getTree() == null) return false;
        Node n = any.getTree().getRoot().getNodeOrNull(key.substring(0, hash));
        if (!(n instanceof PaneSet set)) return true;     // a pane key whose building is not streamed here: nothing to do
        int i;
        try { i = Integer.parseInt(key.substring(hash + 1)); } catch (NumberFormatException e) { return true; }
        if (value >= 0.5f) set.breakNow(i, false); else set.restore(i, false);
        return true;
    }

    static boolean valid(Node n) { return n != null && GD.isInstanceValid(n); }
}
