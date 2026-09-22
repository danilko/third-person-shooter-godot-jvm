package com.openworld.world;

import com.openworld.character.Player;
import com.openworld.game.PlayerRegistry;
import com.openworld.util.CollisionLayers;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.BoxShape3D;
import godot.api.Camera3D;
import godot.api.CollisionShape3D;
import godot.api.Mesh;
import godot.api.MeshInstance3D;
import godot.api.MultiMesh;
import godot.api.MultiMeshInstance3D;
import godot.api.Node;
import godot.api.RigidBody3D;
import godot.api.StaticBody3D;
import godot.api.Time;
import godot.core.Basis;
import godot.core.PackedFloat32Array;
import godot.core.PackedVector3Array;
import godot.core.StringName;
import godot.core.Transform3D;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Knock-down street poles (PLAN.md 3.11): one node per breakable ASSET per road piece — every lamp of a piece, or
 * every signal — built by {@code WorldBaker} from the piece's {@code mmesh_*} markers whose asset
 * {@code furniture.json} flags {@code breakable}. It IS the asset's {@link MultiMeshInstance3D} (the visual batch
 * 3.10 made per zone), and it owns what a static proxy cannot do:
 * <ul>
 *   <li><b>A collider per pole</b>, built at {@code _ready} from {@link #positions}/{@link #yaws} (a box round the
 *       shaft, on the WORLD layer, so a slow car and a walking character stop against it exactly as they did
 *       against the old {@code FURN_props-prop-colonly} box, which no longer carries these poles).</li>
 *   <li><b>The break.</b> A vehicle asks {@link #sweepVehicle} before each physics step; a pole the car will reach
 *       this step at or above {@link #breakSpeed} loses its collider NOW (so the contact never happens), its
 *       MultiMesh instance is hidden, a {@link RigidBody3D} with the pole's own mesh takes the car's lost momentum
 *       and falls, and the car keeps {@code m_car / (m_car + m_pole)} of its speed. The rules are
 *       {@link PropBreakRules}'.</li>
 *   <li><b>The return.</b> After {@link #respawnSeconds}, only where no viewer sees the spot (farther than
 *       {@link #hideDistance} from every remote player, and not in this peer's camera frustum within that
 *       distance) and nothing stands on it, the debris goes and the instance and collider come back.</li>
 * </ul>
 *
 * <p><b>Why the transforms are stored twice.</b> The MultiMesh carries them for drawing, but the {@code --headless}
 * dummy renderer drops a MultiMesh's transform buffer (reads come back identity), so a collider built from it would
 * sit every pole at the piece origin in every headless run and probe. {@link #positions}/{@link #yaws} are the
 * copy the logic reads.
 *
 * <p><b>Local, not replicated (PLAN.md 3.11b).</b> A knocked-down pole is cosmetic, so it costs no bandwidth: every
 * peer runs {@link #sweepVehicle} for every car it sees move (a car it simulates, or a puppet whose velocity comes
 * from its motion), knocks the pole down itself, and runs its own respawn timer and "unseen" rule. Only the peer
 * that SIMULATES the car takes the speed loss, and that reaches every other peer through the car's own snapshot.
 * Two peers may therefore disagree about a pole for up to {@link #respawnSeconds} (a puppet's interpolated path can
 * graze a pole the real car missed); a late joiner sees every pole standing. The pole is not cover or a gameplay
 * object, so that is accepted rather than paid for with messages. {@code world.Breakable} (glass, walls) changes
 * line of sight and stays host-authoritative.
 */
@Script(className = "BreakableProps")
public class BreakableProps extends MultiMeshInstance3D {

    /** The road piece this batch belongs to (the baked scene's stem) — the first part of each pole's key. */
    @Export public String pieceId = "";
    /** The furniture asset (e.g. {@code lamp}) — the second part of the key. */
    @Export public String assetName = "";
    /** Each pole's base, in this node's frame (the piece's). */
    @Export public PackedVector3Array positions = new PackedVector3Array();
    /** Each pole's yaw (radians about +Y), index-parallel to {@link #positions}. */
    @Export public PackedFloat32Array yaws = new PackedFloat32Array();
    /** The asset's scale in its own axes (one for every instance). */
    @Export public Vector3 instanceScale = new Vector3(1, 1, 1);
    /** Half width of the shaft's collider (m) and its height (m). */
    @Export public float poleHalfWidth = 0.2f;
    @Export public float poleHeight = 6.0f;
    /** Effective mass of the pole (kg): what it costs a car to knock it down, and the falling body's mass. */
    @Export public float mass = 250.0f;
    /** A vehicle at or above this speed (m/s) knocks the pole down; below it the pole is a solid post. */
    @Export public float breakSpeed = 5.0f;
    /** Seconds a knocked-down pole stays down before it may come back (unseen). */
    @Export public float respawnSeconds = 60.0f;
    /** A viewer farther than this (m) cannot see a pole come back. */
    @Export public float hideDistance = 80.0f;

    /** The control knob: off, every pole is a solid post at any speed (the pre-3.11 world). */
    @Visible public boolean breakingEnabled = true;

    /** Physics layer of a falling pole: nothing collides with it (it must never stop a car), and it lands on WORLD. */
    private static final int DEBRIS_LAYER = 0;
    /** Falling poles alive at once, over the whole world; the oldest is freed first (its pole stays down). */
    private static final int MAX_DEBRIS = 12;
    /** Height above the pole's base where a bumper hits it (m). */
    private static final float CONTACT_HEIGHT = 0.7f;
    /** Plan cell of the per-node pole lookup (m). */
    private static final float CELL = 16.0f;
    /** Seconds between respawn checks. */
    private static final double RESPAWN_TICK = 0.5;
    /** Metres round a pole that must be clear of characters and vehicles for it to come back. */
    private static final float OCCUPIED_RADIUS = 2.5f;

    private static final List<BreakableProps> LIVE = new ArrayList<>();
    private static final ArrayDeque<RigidBody3D> DEBRIS = new ArrayDeque<>();

    private final List<CollisionShape3D> shapes = new ArrayList<>();
    private final Map<Long, List<Integer>> cells = new HashMap<>();
    private boolean[] broken = new boolean[0];
    private double[] brokenAt = new double[0];
    private final Map<Integer, RigidBody3D> debris = new HashMap<>();
    private Vector3[] worldPos = new Vector3[0];
    private float minX, maxX, minZ, maxZ;
    private boolean built;
    private double tickTimer;
    private int brokenCount;
    private int breaksTotal;
    private final List<Node> scratch = new ArrayList<>();

    // ── Lifetime ──────────────────────────────────────────────────────────────

    @Register
    @Override
    public void _enterTree() {
        if (!LIVE.contains(this)) LIVE.add(this);
    }

    @Register
    @Override
    public void _exitTree() {
        LIVE.remove(this);
        for (RigidBody3D d : debris.values()) freeDebris(d);
        debris.clear();
    }

    @Register
    @Override
    public void _ready() {
        if (built) return;
        built = true;
        int n = count();
        broken = new boolean[n];
        brokenAt = new double[n];
        worldPos = new Vector3[n];
        StaticBody3D body = new StaticBody3D();
        body.setName(new StringName("Poles"));
        body.setCollisionLayer(CollisionLayers.WORLD);
        body.setCollisionMask(0);
        // The body is filled OFF-TREE and entered once. Adding each shape to a body already in the tree makes the
        // physics server rebuild the body's compound shape per shape -- quadratic in the pole count, and a piece's
        // bollard batch has hundreds: measured 3.27 s in ONE frame entering island_3_3 (probe_start_hitch.gd).
        BoxShape3D box = new BoxShape3D();
        box.setSize(new Vector3(2 * poleHalfWidth, poleHeight, 2 * poleHalfWidth));
        Transform3D frame = getGlobalTransform();
        minX = minZ = Float.MAX_VALUE;
        maxX = maxZ = -Float.MAX_VALUE;
        for (int i = 0; i < n; i++) {
            CollisionShape3D cs = new CollisionShape3D();
            cs.setShape(box);
            Vector3 p = positions.get(i);
            cs.setTransform(new Transform3D(new Basis(Vector3.Companion.getUP(), yaws.get(i)),
                    p.plus(new Vector3(0, poleHeight * 0.5, 0))));
            body.addChild(cs);
            shapes.add(cs);
            Vector3 w = frame.times(p);
            worldPos[i] = w;
            minX = Math.min(minX, (float) w.getX()); maxX = Math.max(maxX, (float) w.getX());
            minZ = Math.min(minZ, (float) w.getZ()); maxZ = Math.max(maxZ, (float) w.getZ());
            cells.computeIfAbsent(cellKey(w.getX(), w.getZ()), k -> new ArrayList<>()).add(i);
        }
        addChild(body);
        setProcess(false);   // ticks only while a pole is down
    }

    /**
     * Undo {@code _ready}'s runtime build: WorldBaker adds this node to a live tree while it bakes, so its colliders
     * would otherwise be packed into the piece and built a second time on load.
     */
    public void removeRuntimeParts() {
        for (Node c : getChildren()) { removeChild(c); c.queueFree(); }
        shapes.clear();
        cells.clear();
        built = false;
    }

    private int count() {
        return Math.min(positions.getSize(), yaws.getSize());
    }

    private String keyPrefix() {
        return pieceId + "|" + assetName;
    }

    private static long cellKey(double x, double z) {
        long cx = (long) Math.floor(x / CELL), cz = (long) Math.floor(z / CELL);
        return (cx << 32) | (cz & 0xFFFFFFFFL);
    }

    // ── The vehicle's question ────────────────────────────────────────────────

    /**
     * Knock down every pole a car is about to reach fast enough, and return the fraction of its speed it keeps
     * (1 when it reaches none). Called by the vehicle before its physics step on EVERY peer, for a simulated car
     * and a puppet alike; the caller applies the returned fraction only where it simulates the car. Nothing is
     * sent over the network.
     *
     * @param pos       the car's centre (world)
     * @param basis     the car's world basis (its plan rectangle is aligned to X and Z)
     * @param velocity  the car's velocity (world)
     * @param halfWidth half the car's footprint across (m); {@code halfLength} along
     * @param carMass   the car's mass (kg)
     * @param dt        the physics step (s)
     */
    public static double sweepVehicle(Vector3 pos, Basis basis, Vector3 velocity, double halfWidth,
                                      double halfLength, double carMass, double dt) {
        if (LIVE.isEmpty()) return 1.0;
        double speed = Math.hypot(velocity.getX(), velocity.getZ());
        if (speed < 1.0) return 1.0;
        Vector3 ax = basis.getX(), az = basis.getZ();
        double vx = velocity.dot(ax), vz = velocity.dot(az);
        double reach = halfLength + halfWidth + speed * dt * PropBreakRules.LOOKAHEAD_STEPS + 2.0;
        double keep = 1.0;
        for (int li = 0; li < LIVE.size(); li++) {
            BreakableProps p = LIVE.get(li);
            if (!p.breakingEnabled || !p.built || speed < p.breakSpeed) continue;
            if (pos.getX() < p.minX - reach || pos.getX() > p.maxX + reach
                    || pos.getZ() < p.minZ - reach || pos.getZ() > p.maxZ + reach) continue;
            long c0x = (long) Math.floor((pos.getX() - reach) / CELL), c1x = (long) Math.floor((pos.getX() + reach) / CELL);
            long c0z = (long) Math.floor((pos.getZ() - reach) / CELL), c1z = (long) Math.floor((pos.getZ() + reach) / CELL);
            for (long cx = c0x; cx <= c1x; cx++) {
                for (long cz = c0z; cz <= c1z; cz++) {
                    List<Integer> bucket = p.cells.get((cx << 32) | (cz & 0xFFFFFFFFL));
                    if (bucket == null) continue;
                    for (int i : bucket) {
                        if (p.broken[i]) continue;
                        Vector3 d = p.worldPos[i].minus(pos);
                        if (d.getY() > 2.5 || d.getY() + p.poleHeight < -1.0) continue;   // not at the car's height
                        if (!PropBreakRules.reachesPole(d.dot(ax), d.dot(az), halfWidth, halfLength,
                                p.poleHalfWidth, vx, vz, dt)) continue;
                        if (!PropBreakRules.breaks(speed, p.breakSpeed)) continue;
                        p.knockDown(i, velocity, carMass);
                        keep *= PropBreakRules.keepFraction(carMass, p.mass);
                    }
                }
            }
        }
        return keep;
    }

    // ── Down and back ─────────────────────────────────────────────────────────

    private void knockDown(int i, Vector3 velocity, double carMass) {
        if (broken[i]) return;
        broken[i] = true;
        brokenAt[i] = now();
        brokenCount++;
        breaksTotal++;
        shapes.get(i).setDisabled(true);
        MultiMesh mm = getMultimesh();
        if (mm != null && i < mm.getInstanceCount()) {
            mm.setInstanceTransform(i, new Transform3D(new Basis(Vector3.Companion.getZERO(),
                    Vector3.Companion.getZERO(), Vector3.Companion.getZERO()), positions.get(i)));
        }
        spawnDebris(i, velocity.times(PropBreakRules.poleImpulseScale(carMass, mass)));
        setProcess(true);
    }

    private void restore(int i) {
        if (!broken[i]) return;
        broken[i] = false;
        brokenCount--;
        shapes.get(i).setDisabled(false);
        MultiMesh mm = getMultimesh();
        if (mm != null && i < mm.getInstanceCount()) mm.setInstanceTransform(i, instanceTransform(i));
        RigidBody3D d = debris.remove(i);
        if (d != null) freeDebris(d);
        if (brokenCount <= 0) setProcess(false);
    }

    private Transform3D instanceTransform(int i) {
        // rotation then the piece's own-axis scale (R * S), as the marker's basis was
        Basis scale = new Basis(instanceScale.getX(), 0, 0, 0, instanceScale.getY(), 0, 0, 0, instanceScale.getZ());
        return new Transform3D(new Basis(Vector3.Companion.getUP(), yaws.get(i)).times(scale), positions.get(i));
    }

    private void spawnDebris(int i, Vector3 impulse) {
        MultiMesh mm = getMultimesh();
        Mesh mesh = mm != null ? mm.getMesh() : null;
        RigidBody3D body = new RigidBody3D();
        body.setName(new StringName("FallingPole_" + i));
        body.setCollisionLayer(DEBRIS_LAYER);
        body.setCollisionMask(CollisionLayers.WORLD);
        body.setMass(Math.max(1.0f, mass));
        if (mesh != null) {
            MeshInstance3D mi = new MeshInstance3D();
            mi.setMesh(mesh);
            mi.setScale(instanceScale);
            body.addChild(mi);
        }
        CollisionShape3D cs = new CollisionShape3D();
        BoxShape3D box = new BoxShape3D();
        box.setSize(new Vector3(2 * poleHalfWidth, poleHeight, 2 * poleHalfWidth));
        cs.setShape(box);
        cs.setPosition(new Vector3(0, poleHeight * 0.5, 0));
        body.addChild(cs);
        addChild(body);
        body.setGlobalTransform(getGlobalTransform().times(
                new Transform3D(new Basis(Vector3.Companion.getUP(), yaws.get(i)), positions.get(i))));
        // the bumper hits low on the shaft; a little lift so the base does not dig into the ground as it kicks out
        Vector3 up = new Vector3(0, impulse.length() * 0.15, 0);
        body.applyImpulse(impulse.plus(up), new Vector3(0, CONTACT_HEIGHT, 0));
        RigidBody3D old = debris.put(i, body);
        if (old != null) freeDebris(old);
        DEBRIS.addLast(body);
        while (DEBRIS.size() > MAX_DEBRIS) freeDebris(DEBRIS.pollFirst());
    }

    private static void freeDebris(RigidBody3D d) {
        if (d == null) return;
        DEBRIS.remove(d);
        if (GD.isInstanceValid(d)) d.queueFree();
    }

    @Register
    @Override
    public void _process(double delta) {
        tickTimer -= delta;
        if (tickTimer > 0.0) return;
        tickTimer = RESPAWN_TICK;
        double t = now();
        for (int i = 0; i < broken.length; i++) {
            if (!broken[i]) continue;
            if (!PropBreakRules.mayRestore(t - brokenAt[i], respawnSeconds, seen(worldPos[i]), occupied(worldPos[i])))
                continue;
            restore(i);
        }
    }

    private boolean seen(Vector3 p) {
        double[] pt = {p.getX(), p.getY() + poleHeight * 0.5, p.getZ()};
        Vector3 top = new Vector3(pt[0], pt[1], pt[2]);
        Camera3D cam = getViewport() != null ? getViewport().getCamera3d() : null;
        if (cam != null && GD.isInstanceValid(cam)) {
            Vector3 c = cam.getGlobalPosition();
            if (PropBreakRules.sees(new double[]{c.getX(), c.getY(), c.getZ()}, null, 0, pt, hideDistance)
                    && cam.isPositionInFrustum(top)) return true;
        }
        for (Player pl : PlayerRegistry.getPlayers()) {
            if (pl == null || !GD.isInstanceValid(pl) || pl.isLocallyOwnedPlayer()) continue;
            Vector3 v = pl.getGlobalPosition();
            if (PropBreakRules.sees(new double[]{v.getX(), v.getY(), v.getZ()}, null, 0, pt, hideDistance)) return true;
        }
        return false;
    }

    private boolean occupied(Vector3 p) {
        SpatialEntityGrid grid = SpatialEntityGrid.get();
        if (grid == null) return false;
        grid.queryRadius(p, OCCUPIED_RADIUS + 3.0f, scratch);
        for (Node n : scratch) {
            if (n instanceof godot.api.Node3D n3 && GD.isInstanceValid(n3)
                    && n3.getGlobalPosition().distanceTo(p) < OCCUPIED_RADIUS + 1.5) return true;
        }
        return false;
    }

    private static double now() {
        return Time.INSTANCE.getTicksMsec() / 1000.0;
    }

    private String key(int i) {
        return keyPrefix() + "|" + i;
    }

    // ── What a lamp light needs (StreetLights) ────────────────────────────────

    /** Every batch currently in the tree. The list is the live one; read it, do not keep it. */
    public static List<BreakableProps> live() { return LIVE; }

    /** This batch's kit piece ({@code StreetLight_JP}, …) — which bulb offsets apply. */
    public String asset() { return assetName; }

    /** Poles in this batch, once {@code _ready} has built its index. */
    public int poles() { return built ? worldPos.length : 0; }

    /** True while this pole is lying on the ground: its bulb is out. */
    public boolean poleBroken(int i) { return i >= 0 && i < broken.length && broken[i]; }

    /** This pole's base, in world space. */
    public Vector3 poleBase(int i) { return worldPos[i]; }

    /** This pole's yaw about +Y (radians), as the MultiMesh instance carries it. */
    public float poleYaw(int i) { return yaws.get(i); }

    /** The piece's own-axis scale, which a bulb offset rides too. */
    public Vector3 poleScale() { return instanceScale; }

    /** Cheap reject: could any pole of this batch be within {@code r} of (x, z)? */
    public boolean nearBounds(double x, double z, double r) {
        return built && x >= minX - r && x <= maxX + r && z >= minZ - r && z <= maxZ + r;
    }

    // ── Probe readouts (question-named, so godot-jvm does not merge them into properties) ─────

    /** Poles in this batch. */
    @Register public int poleCountNow() { return count(); }
    /** True when pole {@code i} is down. */
    @Register public boolean poleBrokenNow(int i) { return i >= 0 && i < broken.length && broken[i]; }
    /** True when pole {@code i}'s collider is live. */
    @Register public boolean poleSolidNow(int i) { return i >= 0 && i < shapes.size() && !shapes.get(i).isDisabled(); }
    /** Pole {@code i}'s base in world space. */
    @Register public Vector3 poleWorldPositionNow(int i) {
        return i >= 0 && i < worldPos.length ? worldPos[i] : Vector3.Companion.getZERO();
    }
    /** Pole {@code i}'s falling body, or null. */
    @Register public RigidBody3D poleDebrisNow(int i) { return debris.get(i); }
    /** Poles knocked down on this node since it loaded. */
    @Register public int breaksTotalNow() { return breaksTotal; }
    /** Seconds pole {@code i} has been down (0 when standing) — a probe shortens the wait with {@link #ageBreakNow}. */
    @Register public double brokenForNow(int i) { return poleBrokenNow(i) ? now() - brokenAt[i] : 0.0; }
    /** Probe support: pretend pole {@code i} went down {@code seconds} earlier than it did. */
    @Register public void ageBreakNow(int i, double seconds) { if (poleBrokenNow(i)) brokenAt[i] -= seconds; }
    /** Pole {@code i}'s identity ({@code piece|asset|index}), for probes and logs. */
    @Register public String poleKeyNow(int i) { return key(i); }
}
