package com.openworld.world;

import com.openworld.character.Character;
import com.openworld.util.CollisionLayers;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.AnimatableBody3D;
import godot.api.Area3D;
import godot.api.BoxMesh;
import godot.api.BoxShape3D;
import godot.api.CollisionShape3D;
import godot.api.Material;
import godot.api.MeshInstance3D;
import godot.api.Node3D;
import godot.api.StandardMaterial3D;
import godot.api.StaticBody3D;
import godot.core.Color;
import godot.core.MethodCallable;
import godot.core.StringName;
import godot.core.Vector3;

import java.util.ArrayList;
import java.util.List;

/**
 * A station LIFT (エレベーター; user, 2026-09-27: one beside every hub platform stair, "big as the stair case for
 * accessibility / large luggage", doors "slide doors open horizontally to both sides", along the track, never the
 * rail side). What it does is {@link ElevatorRules}; this node feeds it its sensors and draws the answer.
 *
 * <p>The SHAFT is the station kit piece's own mesh and colliders (`blender/tools/build_station_blends.py
 * lift_shaft`: glass walls, a door opening in both X faces at every stop). This node builds, at {@code _ready}, what
 * moves: the CAR (an {@link AnimatableBody3D}, so a character standing in it rides it), a two-leaf CENTRE-OPENING
 * sliding door on each of its X faces, the same pair in each landing opening, and three kinds of sensor -- a CALL
 * zone in front of each landing door, a DOORWAY band across each opening (the doors never shut on anybody in it) and
 * the car's own RIDE volume. A leaf's collider is off only while its doors stand open at the car's stop, so nobody
 * walks into the shaft or out of a moving car.
 *
 * <p>Frame: the origin is the shaft floor's centre at the LOW stop; +X is along the track (the door faces), +Z across.
 * {@link #rise} is the top stop over the low one. Placed by the scene builder from the piece's {@code LIFT_} Empty.
 *
 * <p><b>Networking:</b> local per peer, the {@link Door} rule: each peer runs its own lift for its own bodies. A
 * remote player's puppet rides the snapshot, so on another peer they may be seen standing in a shaft whose car is
 * elsewhere -- cosmetic, and cleared when they step out.
 */
@Script(className = "Elevator")
public class Elevator extends Node3D {
    /** The shaft's inside along X (between the door faces) and along Z. */
    @Export public double shaftWidth = 2.26;
    @Export public double shaftDepth = 2.26;
    /** The top stop over the low one. */
    @Export public double rise = 4.94;
    /** Each door's clear opening. */
    @Export public double doorWidth = 1.1;
    @Export public double doorHeight = 2.1;
    @Export public double speed = 1.5;
    @Export public double doorSeconds = 1.2;
    @Export public double dwellSeconds = 3.0;
    @Export public Material frameMaterial;
    @Export public Material glassMaterial;
    @Export public Material floorMaterial;
    /** An out-of-service lift neither opens nor moves (a story beat, a blackout; the probe's control). */
    @Export public boolean inService = true;

    private static final double CAR_CLEAR = 0.05;       // each side between the car and the shaft wall
    private static final double CAR_H = 2.35;
    private static final double LEAF_T = 0.05;
    private static final double CALL_DEPTH = 1.2;

    private ElevatorRules rules;
    private AnimatableBody3D car;
    private final List<Node3D> carLeaves = new ArrayList<>();            // [face * 2 + leaf]
    private final List<CollisionShape3D> carLeafShapes = new ArrayList<>();
    private final List<List<Node3D>> landingLeaves = new ArrayList<>();  // per stop
    private final List<List<CollisionShape3D>> landingShapes = new ArrayList<>();
    private int[] doorway;
    private int riders;

    @Register
    @Override
    public void _ready() {
        rules = new ElevatorRules(new double[]{0.0, rise});
        rules.speed = speed;
        rules.doorSeconds = doorSeconds;
        rules.dwellSeconds = dwellSeconds;
        doorway = new int[2];
        if (frameMaterial == null) frameMaterial = plain(new Color(0.55, 0.57, 0.6, 1.0));
        if (glassMaterial == null) glassMaterial = plain(new Color(0.7, 0.85, 0.9, 0.35));
        if (floorMaterial == null) floorMaterial = plain(new Color(0.35, 0.35, 0.36, 1.0));
        buildCar();
        for (int s = 0; s < 2; s++) buildLanding(s);
        apply();
        setPhysicsProcess(true);
    }

    private static Material plain(Color c) {
        StandardMaterial3D m = new StandardMaterial3D();
        m.setAlbedo(c);
        if (c.getA() < 1.0) m.setTransparency(StandardMaterial3D.Transparency.ALPHA);
        return m;
    }

    private double dw() { return Math.min(doorWidth, shaftDepth - 0.1); }

    // ── construction ────────────────────────────────────────────────────────────────────────────────────────
    private static MeshInstance3D box(Node3D parent, Vector3 size, Vector3 at, Material mat) {
        MeshInstance3D mi = new MeshInstance3D();
        BoxMesh m = new BoxMesh();
        m.setSize(size);
        mi.setMesh(m);
        mi.setMaterialOverride(mat);
        mi.setPosition(at);
        parent.addChild(mi);
        return mi;
    }

    private static CollisionShape3D shape(Node3D body, Vector3 size, Vector3 at) {
        CollisionShape3D cs = new CollisionShape3D();
        BoxShape3D b = new BoxShape3D();
        b.setSize(size);
        cs.setShape(b);
        cs.setPosition(at);
        body.addChild(cs);
        return cs;
    }

    private void buildCar() {
        car = new AnimatableBody3D();
        car.setName(new StringName("Car"));
        car.setSyncToPhysics(true);
        car.setCollisionLayer(CollisionLayers.WORLD);
        car.setCollisionMask(0);
        double cw = shaftWidth - 2 * CAR_CLEAR, cd = shaftDepth - 2 * CAR_CLEAR, dw = dw();
        // filled OFF-TREE and entered once (BreakableProps' rule: a shape added to a body in the tree rebuilds it)
        shape(car, new Vector3(cw, 0.1, cd), new Vector3(0, -0.05, 0));
        shape(car, new Vector3(cw, 0.1, cd), new Vector3(0, CAR_H + 0.05, 0));
        box(car, new Vector3(cw, 0.1, cd), new Vector3(0, -0.05, 0), floorMaterial);
        box(car, new Vector3(cw, 0.08, cd), new Vector3(0, CAR_H + 0.04, 0), frameMaterial);
        box(car, new Vector3(cw * 0.6, 0.02, cd * 0.6), new Vector3(0, CAR_H - 0.01, 0), glassMaterial);
        for (double sz : new double[]{-1, 1}) {                 // the two side walls (toward the track and the wall)
            Vector3 at = new Vector3(0, CAR_H / 2, sz * (cd / 2 - 0.025));
            shape(car, new Vector3(cw, CAR_H, 0.05), at);
            box(car, new Vector3(cw, CAR_H, 0.03), at, glassMaterial);
            box(car, new Vector3(cw, 0.06, 0.06), new Vector3(0, 0.9, sz * (cd / 2 - 0.08)), frameMaterial); // handrail
        }
        double jamb = (cd - dw) / 2;
        for (int f = 0; f < 2; f++) {                            // the two door faces, -X then +X
            double sx = f == 0 ? -1 : 1;
            double x = sx * (cw / 2 - 0.025);
            for (double sz : new double[]{-1, 1}) {
                Vector3 at = new Vector3(x, CAR_H / 2, sz * (dw / 2 + jamb / 2));
                shape(car, new Vector3(0.05, CAR_H, jamb), at);
                box(car, new Vector3(0.05, CAR_H, jamb), at, frameMaterial);
            }
            Vector3 head = new Vector3(x, doorHeight + (CAR_H - doorHeight) / 2, 0);
            shape(car, new Vector3(0.05, CAR_H - doorHeight, dw), head);
            box(car, new Vector3(0.05, CAR_H - doorHeight, dw), head, frameMaterial);
            carLeafShapes.add(shape(car, new Vector3(LEAF_T, doorHeight, dw), new Vector3(x, doorHeight / 2, 0)));
            for (int l = 0; l < 2; l++) carLeaves.add(leaf(car, x, 0.0));
        }
        Area3D ride = sensor(car, new Vector3(cw - 0.2, 1.6, cd - 0.2), new Vector3(0, 0.9, 0));
        ride.setName(new StringName("Ride"));
        ride.connect(new StringName("body_entered"), MethodCallable.createUnsafe(this, "on_ride_entered"));
        ride.connect(new StringName("body_exited"), MethodCallable.createUnsafe(this, "on_ride_exited"));
        addChild(car);
    }

    /** One sliding leaf (glass in a steel frame), hung at plane x, its closed centre set by {@link #slideLeaves}. */
    private Node3D leaf(Node3D parent, double x, double y0) {
        double lw = dw() / 2, h = doorHeight;
        Node3D n = new Node3D();
        n.setPosition(new Vector3(x, y0, 0));
        box(n, new Vector3(LEAF_T * 0.6, h - 0.3, lw - 0.1), new Vector3(0, h / 2, 0), glassMaterial);
        box(n, new Vector3(LEAF_T, 0.15, lw), new Vector3(0, 0.075, 0), frameMaterial);
        box(n, new Vector3(LEAF_T, 0.15, lw), new Vector3(0, h - 0.075, 0), frameMaterial);
        for (double sz : new double[]{-1, 1})
            box(n, new Vector3(LEAF_T, h, 0.05), new Vector3(0, h / 2, sz * (lw / 2 - 0.025)), frameMaterial);
        parent.addChild(n);
        return n;
    }

    private Area3D sensor(Node3D parent, Vector3 size, Vector3 at) {
        Area3D a = new Area3D();
        a.setCollisionLayer(0);
        a.setCollisionMask(CollisionLayers.CHARACTER);
        a.setMonitorable(false);
        CollisionShape3D cs = new CollisionShape3D();
        BoxShape3D b = new BoxShape3D();
        b.setSize(size);
        cs.setShape(b);
        a.addChild(cs);
        a.setPosition(at);
        parent.addChild(a);
        return a;
    }

    private void buildLanding(int s) {
        double y = s == 0 ? 0.0 : rise;
        double x = shaftWidth / 2 + 0.03, dw = dw();
        StaticBody3D body = new StaticBody3D();
        body.setName(new StringName("Landing" + s));
        body.setCollisionLayer(CollisionLayers.WORLD);
        body.setCollisionMask(0);
        List<Node3D> leaves = new ArrayList<>();
        List<CollisionShape3D> shapes = new ArrayList<>();
        for (int f = 0; f < 2; f++) {
            double sx = f == 0 ? -1 : 1;
            shapes.add(shape(body, new Vector3(LEAF_T, doorHeight, dw), new Vector3(sx * x, y + doorHeight / 2, 0)));
            for (int l = 0; l < 2; l++) leaves.add(leaf(body, sx * x, y));
            Area3D call = sensor(this, new Vector3(CALL_DEPTH, 1.8, dw + 0.8),
                    new Vector3(sx * (x + 0.1 + CALL_DEPTH / 2), y + 1.0, 0));
            call.setName(new StringName("Call" + s + (f == 0 ? "W" : "E")));
            call.connect(new StringName("body_entered"), MethodCallable.createUnsafe(this, "on_call_" + (s == 0 ? "low" : "high")));
            Area3D way = sensor(this, new Vector3(0.7, 1.8, dw), new Vector3(sx * x, y + 1.0, 0));
            way.setName(new StringName("Doorway" + s + (f == 0 ? "W" : "E")));
            way.connect(new StringName("body_entered"), MethodCallable.createUnsafe(this, "on_way_entered_" + (s == 0 ? "low" : "high")));
            way.connect(new StringName("body_exited"), MethodCallable.createUnsafe(this, "on_way_exited_" + (s == 0 ? "low" : "high")));
        }
        addChild(body);
        landingLeaves.add(leaves);
        landingShapes.add(shapes);
    }

    // ── sensors ─────────────────────────────────────────────────────────────────────────────────────────────
    private static boolean isCharacter(Node3D b) {
        return b instanceof Character || b.getOwner() instanceof Character;
    }

    private void wake() { setPhysicsProcess(true); }

    @Register public void onCallLow(Node3D b) { if (isCharacter(b)) { rules.call(0); wake(); } }
    @Register public void onCallHigh(Node3D b) { if (isCharacter(b)) { rules.call(1); wake(); } }
    @Register public void onWayEnteredLow(Node3D b) { if (isCharacter(b)) { doorway[0]++; wake(); } }
    @Register public void onWayEnteredHigh(Node3D b) { if (isCharacter(b)) { doorway[1]++; wake(); } }
    @Register public void onWayExitedLow(Node3D b) { if (isCharacter(b)) doorway[0] = Math.max(0, doorway[0] - 1); }
    @Register public void onWayExitedHigh(Node3D b) { if (isCharacter(b)) doorway[1] = Math.max(0, doorway[1] - 1); }

    @Register
    public void onRideEntered(Node3D b) {
        if (!isCharacter(b)) return;
        riders++;
        rules.board();
        wake();
    }

    @Register
    public void onRideExited(Node3D b) {
        if (isCharacter(b)) riders = Math.max(0, riders - 1);
    }

    // ── the tick ────────────────────────────────────────────────────────────────────────────────────────────
    @Register
    @Override
    public void _physicsProcess(double delta) {
        if (!inService) {
            setPhysicsProcess(false);
            return;
        }
        boolean blocked = rules.phase != ElevatorRules.Phase.MOVING && doorway[rules.stop] > 0;
        rules.step(delta, riders, blocked);
        apply();
        if (rules.resting() && rules.door == 0.0 && doorway[0] == 0 && doorway[1] == 0) setPhysicsProcess(false);
    }

    private void apply() {
        car.setPosition(new Vector3(0, rules.y, 0));
        double open = rules.phase == ElevatorRules.Phase.MOVING ? 0.0 : rules.door;
        slideLeaves(carLeaves, open);
        for (CollisionShape3D cs : carLeafShapes) cs.setDisabled(open > 0.9);
        for (int s = 0; s < 2; s++) {
            double o = s == rules.stop ? open : 0.0;
            slideLeaves(landingLeaves.get(s), o);
            for (CollisionShape3D cs : landingShapes.get(s)) cs.setDisabled(rules.landingOpen(s));
        }
    }

    /** Each face's two leaves part from the middle, each sliding by its own width toward its side. */
    private void slideLeaves(List<Node3D> leaves, double open) {
        double lw = dw() / 2;
        for (int i = 0; i < leaves.size(); i++) {
            double sz = (i % 2 == 0) ? -1 : 1;
            Node3D n = leaves.get(i);
            Vector3 p = n.getPosition();
            n.setPosition(new Vector3(p.getX(), p.getY(), sz * (lw / 2 + lw * open)));
        }
    }

    // ── probe surface ───────────────────────────────────────────────────────────────────────────────────────
    @Register public String phaseNow() { return rules.phase.name(); }
    @Register public double carHeightNow() { return rules.y; }
    @Register public int stopNow() { return rules.stop; }
    @Register public double doorNow() { return rules.door; }
    @Register public int tripsNow() { return rules.trips; }
    @Register public int ridersNow() { return riders; }
    @Register public void callStop(int s) { rules.call(s); wake(); }
}
