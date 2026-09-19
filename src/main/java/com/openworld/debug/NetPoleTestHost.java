package com.openworld.debug;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.character.CharacterInfo;
import com.openworld.character.Player;
import com.openworld.net.NetStats;
import com.openworld.net.NetworkManager;
import com.openworld.world.BreakableProps;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.BoxShape3D;
import godot.api.CollisionShape3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.OS;
import godot.api.PackedScene;
import godot.api.StaticBody3D;
import godot.core.PackedFloat32Array;
import godot.core.PackedVector3Array;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

/**
 * Two-instance headless check for PLAN.md 3.11b — street poles are knocked down LOCALLY on every peer, with no
 * network message ({@code tools/net/run_net_pole_test.sh}).
 *
 * <p>Both peers build the same {@link BreakableProps} batch in code: pole H on the host car's path, pole C on the
 * client car's path, and a SIDE pole 6 m beside each path that nothing touches. The HOST spawns two cars and drives
 * the first (driverless, host-simulated) through pole H at 15 m/s; the client sees it only as a puppet. The CLIENT
 * takes the driver's seat of the second car through the ordinary host-arbitrated request and drives it through
 * pole C; the host sees that car only as a puppet. Each peer prints which poles it has down and how many world
 * events it sent and received: both poles must be down on both peers, the side poles standing, and 0 world events.
 */
@Script(className = "NetPoleTestHost")
public class NetPoleTestHost extends Node3D {

    private static final int PORT = 7797;
    private static final String VEHICLE_SCENE = "res://src/main/resources/com/openworld/vehicle/SPC1.tscn";
    private static final String HOST_CAR = "netpole-host-car";
    private static final String CLIENT_CAR = "netpole-client-car";
    /** Pole index: 0 = on the host car's path, 1 = on the client car's path, 2 and 3 = beside each path. */
    private static final Vector3[] POLES = {
            new Vector3(-20, 0, 0), new Vector3(20, 0, 0), new Vector3(-26, 0, 0), new Vector3(26, 0, 0)};
    private static final double SPEED = 15.0;
    private static final double CAR_Z = 40.0;
    private static final double STOP_Z = -25.0;
    private static final double TIMEOUT_S = 90.0;

    private String role = "client";
    private NetworkManager net;
    private BreakableProps poles;
    private double clock;
    private boolean sawPeer;
    private double joinedAt = -1;
    private double seatAskedAt = -1;
    private double seatedAt = -1;
    private boolean hostDriveDone, clientDriveDone;
    private double doneAt = -1;
    private boolean finished;
    /** World-event counters when both cars were ready to drive — the join baselines (faction rows) come before. */
    private long eventsAtDrive = -1;

    @Register
    @Override
    public void _ready() {
        for (String a : OS.INSTANCE.getCmdlineUserArgs()) if (a.equals("--role=host")) role = "host";
        net = getNodeOrNull("/root/NetworkManager") instanceof NetworkManager nm ? nm : null;
        box("Ground", new Vector3(200, 1, 200), new Vector3(0, -0.5, 0));
        buildPoles();
        if (role.equals("host")) {
            spawnCar(HOST_CAR, new Vector3(-20, 1.0, (float) CAR_Z));
            spawnCar(CLIENT_CAR, new Vector3(20, 1.0, (float) CAR_Z));
            net.hostServer(PORT);
        } else {
            net.joinServer("127.0.0.1", PORT);
        }
        GD.print("[netpole] role=" + role);
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

    private void buildPoles() {
        poles = new BreakableProps();
        poles.setName(new StringName("Breakable_lamp"));
        poles.pieceId = "netpole";
        poles.assetName = "lamp";
        PackedVector3Array ps = new PackedVector3Array();
        PackedFloat32Array ys = new PackedFloat32Array();
        for (Vector3 p : POLES) { ps.append(p); ys.append(0f); }
        poles.positions = ps;
        poles.yaws = ys;
        poles.respawnSeconds = 600f;   // nothing comes back during the run
        addChild(poles);
    }

    private void spawnCar(String id, Vector3 at) {
        if (!(GD.INSTANCE.load(VEHICLE_SCENE) instanceof PackedScene ps) || !(ps.instantiate() instanceof Vehicle v)) return;
        v.characterInfo = new CharacterInfo();
        v.characterInfo.characterId = id;
        v.characterInfo.displayName = id;
        getNodeOrNull("Characters").addChild(v);
        v.setGlobalPosition(at);
    }

    private Vehicle car(String id) {
        for (Node node : getTree().getNodesInGroup(new StringName("characters"))) {
            if (node instanceof Vehicle v && v.characterInfo != null && id.equals(v.characterInfo.characterId)) return v;
        }
        return null;
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

    @Register
    @Override
    public void _physicsProcess(double delta) {
        clock += delta;
        if (clock > TIMEOUT_S) finish("TIMEOUT");
        if (role.equals("host")) hostStep(); else clientStep();
    }

    /** Hold a car at SPEED down -Z until it is past the poles, then stop it. Returns true once done. */
    private boolean drive(Vehicle v) {
        if (v.getGlobalPosition().getZ() < STOP_Z) {
            v.setLinearVelocity(Vector3.Companion.getZERO());
            return true;
        }
        Vector3 vel = v.getLinearVelocity();
        v.setLinearVelocity(new Vector3(0, vel.getY(), -SPEED));
        return false;
    }

    private void hostStep() {
        if (joinedAt < 0 && players() > 0) joinedAt = clock;   // the host has no player of its own
        Vehicle hc = car(HOST_CAR);
        Vehicle cc = car(CLIENT_CAR);
        if (eventsAtDrive < 0 && cc != null && cc.getOccupant() != null) eventsAtDrive = NetStats.get("world_event_sent");
        if (eventsAtDrive >= 0 && joinedAt >= 0 && clock - joinedAt > 5.0 && !hostDriveDone && hc != null) {
            hostDriveDone = drive(hc);
            if (hostDriveDone) GD.print("[netpole] host car past the poles");
        }
        // the client finishes 4 s after its car is past; the host a little later, so both summaries print
        if (hostDriveDone && cc != null && cc.getGlobalPosition().getZ() < STOP_Z) {
            if (doneAt < 0) doneAt = clock;
            if (clock - doneAt > 6.0) finish("both cars past");
        }
    }

    private void clientStep() {
        if (net.isNetworked() && clock > 1.0) sawPeer = true;
        if (sawPeer && !net.isNetworked()) finish("host left");
        Player me = me();
        Vehicle cc = car(CLIENT_CAR);
        if (me == null || cc == null) return;
        if (seatedAt < 0) {
            if (cc.getOccupant() == me && cc.isLocallySimulated()) {
                seatedAt = clock;
                eventsAtDrive = NetStats.get("world_event_received");
                GD.print("[netpole] client seated in its car");
                return;
            }
            if (seatAskedAt < 0 || clock - seatAskedAt > 2.0) {
                me.setGlobalPosition(cc.getGlobalPosition().plus(new Vector3(-2.0, 0, 0)));
                cc.requestEnter(me);
                seatAskedAt = clock;
            }
            return;
        }
        if (clock - seatedAt > 2.0 && !clientDriveDone) {
            clientDriveDone = drive(cc);
            if (clientDriveDone) { GD.print("[netpole] client car past the poles"); doneAt = clock; }
        }
        // the host's car runs at join + 5 s; both have long passed by now
        if (doneAt >= 0 && clock - doneAt > 4.0) finish("both cars past");
    }

    private void finish(String why) {
        if (finished) return;
        finished = true;
        StringBuilder sb = new StringBuilder("[netpole] SUMMARY role=" + role + " (" + why + ")");
        for (int i = 0; i < POLES.length; i++) sb.append(" pole").append(i).append('=').append(poles.poleBrokenNow(i) ? "down" : "up");
        for (String k : new String[] {"world_event_sent", "world_event_received", "drop_rate_limited"}) {
            sb.append(' ').append(k).append('=').append(NetStats.get(k));
        }
        long now = NetStats.get(role.equals("host") ? "world_event_sent" : "world_event_received");
        sb.append(" world_events_during_drives=").append(eventsAtDrive < 0 ? -1 : now - eventsAtDrive);
        GD.print(sb.toString());
        getTree().quit();
    }
}
