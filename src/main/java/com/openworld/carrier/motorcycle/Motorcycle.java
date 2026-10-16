package com.openworld.carrier.motorcycle;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.carrier.vehicle.VehicleConfig;
import com.openworld.carrier.vehicle.VehicleWheel;
import com.openworld.character.Character;
import com.openworld.character.Health;
import com.openworld.movement.character.MovementController;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.CollisionShape3D;
import godot.api.MeshInstance3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.SphereShape3D;
import godot.core.Basis;
import godot.core.Transform3D;
import godot.core.Vector3;
import godot.global.GD;

/**
 * A motorcycle (PLAN.md 3.1b / 2c.7): the component car with a bike's model, and the three things a bike does that a
 * car does not.
 *
 * <p><b>It leans, and the lean is VISUAL.</b> The body is the car's: FOUR suspension rays in a narrow track under the
 * two wheels (tools/build_vehicle_scenes.py, BIKE_TRACK), with the car's upright assist holding it level, so a bike is
 * built, damaged, lit and seated by the component-car pipeline unchanged, and its rays stay vertical whatever the lean.
 * The stub this replaces drove two rays and leaned the BODY through the upright assist; measured, that also stands
 * and crosses a 0.15 m kerb at 12 m/s (probe_motorcycle_ride --stub), so this is a choice of pipeline and of a lean
 * that cannot feed back into the handling, not a fix of a stub that fell over. GTA V leans its bikes with the physics;
 * nothing a player meets here needs the body itself to roll. The MODEL
 * (wheels included -- they stay in it, unlike a car's, so they lean with it) rolls about its own origin, which is the
 * ground contact line, by {@code atan(v * yawRate / g)}: the angle a real bike holds through that turn, capped at
 * {@link VehicleConfig#motorcycleLeanDegrees} and eased. The riders roll with it ({@link #seatRollRadians}). Both
 * are read from the body's MOTION (heading and position change per tick), so a network puppet, which is moved
 * kinematically and has no velocity, leans the same with no message. A parked bike with nobody on it stands on its
 * side stand, a few degrees to the left.
 *
 * <p><b>A hard crash THROWS the riders</b> (a car keeps its occupants). A step whose velocity change passes
 * {@link VehicleConfig#motorcycleEjectDv} (a wall at ~25 km/h, a car broadside) or that leaves the bike past 60
 * degrees of tilt unseats everyone, gives them the bike's speed from before the hit plus a hop, and hurts them by
 * how hard it was; a death in the air is the ordinary ragdoll death, carrying that speed. Host / simulating peer
 * only: the unseat is a seat exit, which already replicates.
 */
@Script(className = "Motorcycle")
public class Motorcycle extends Vehicle {

    private static final double G = 9.81;
    /** Lean eases toward its target at this rate (1/s): a bike rolls into a turn in ~0.3 s. */
    private static final double LEAN_RATE = 6.0;
    /** The side stand: a parked, empty bike rests this far over to its left (deg). */
    private static final double KICKSTAND_DEG = 7.0;
    /** A tilt past this (deg) is a fall: the riders come off. */
    private static final double FALL_TILT_DEG = 60.0;
    /** The upward hop a thrown rider leaves with (m/s). */
    private static final double THROW_UP = 2.5;
    /** A thrown rider keeps this share of the bike's speed. */
    private static final double THROW_KEEP = 0.85;

    private Node3D model;
    private Transform3D modelRest;
    private MeshInstance3D wheelFront, wheelBack;
    private Transform3D wheelFrontRest, wheelBackRest;
    private double spinFront, spinBack;
    private double lean;
    private double lastHeading = Double.NaN;
    private Vector3 lastPos;
    private Vector3 lastVel = Vector3.Companion.getZERO();
    private boolean haveLastVel = false;
    private double motionSpeed, motionYawRate;
    private int throwCount;

    @Register
    @Override
    public void _ready() {
        super._ready();
        if (getNodeOrNull("Model") instanceof Node3D m) {
            model = m;
            modelRest = m.getTransform();
            if (m.getNodeOrNull("wheel_f") instanceof MeshInstance3D f) { wheelFront = f; wheelFrontRest = f.getTransform(); }
            if (m.getNodeOrNull("wheel_b") instanceof MeshInstance3D b) { wheelBack = b; wheelBackRest = b.getTransform(); }
        }
        // the four rays draw nothing: the bike's own two wheels, in the model, are the wheels you see. Their tyre hit
        // spheres take the real tyre's size so a shot at a tyre still flattens one.
        float r = getConfig().wheelRadius;
        for (VehicleWheel w : getWheels()) {
            if (w.getNodeOrNull("Wheel") instanceof MeshInstance3D mi) mi.setMesh(null);
            if (w.getNodeOrNull("Wheel/TireHit/TireHitShape") instanceof CollisionShape3D cs) {
                SphereShape3D sphere = new SphereShape3D();
                sphere.setRadius(r);
                cs.setShape(sphere);
            }
        }
    }

    @Register
    @Override
    public void _physicsProcess(double delta) {
        measureMotion(delta);
        expireClearOf(delta);
        if (isLocallySimulated() && !isDummy()) watchForThrow();
        updateLean(delta);              // before the seat pin (super), so the rider rolls with THIS tick's lean
        super._physicsProcess(delta);
        animateWheels(delta);
        updateRiders();
        lastVel = getLinearVelocity();
        haveLastVel = true;
    }

    // ── Lean ─────────────────────────────────────────────────────────────────

    /** Speed along the ground and yaw rate, from this tick's MOTION (a kinematic puppet has no velocity). */
    private void measureMotion(double delta) {
        Vector3 pos = getGlobalPosition();
        Vector3 back = getGlobalBasis().getColumn(2);
        double heading = Math.atan2(back.getX(), back.getZ());
        if (lastPos != null && delta > 0.0 && !Double.isNaN(lastHeading)) {
            Vector3 d = pos.minus(lastPos);
            double speed = Math.hypot(d.getX(), d.getZ()) / delta;
            double dh = heading - lastHeading;
            while (dh > Math.PI) dh -= 2 * Math.PI;
            while (dh < -Math.PI) dh += 2 * Math.PI;
            // a teleport (spawn, reset) is not a 300 km/h turn
            if (speed < 120.0) {
                motionSpeed = speed;
                motionYawRate = dh / delta;
            }
        }
        lastPos = pos;
        lastHeading = heading;
    }

    /** The lean this bike should hold now (radians, + = left). */
    public static double targetLean(double speed, double yawRate, double maxDeg) {
        double max = Math.toRadians(maxDeg);
        double a = Math.atan(speed * yawRate / G);
        return Math.max(-max, Math.min(max, a));
    }

    private void updateLean(double delta) {
        VehicleConfig cfg = getConfig();
        double target;
        if (isEmptyOfRiders() && motionSpeed < 0.3) target = Math.toRadians(Math.min(KICKSTAND_DEG, cfg.motorcycleLeanDegrees));
        else if (footDown()) target = Math.toRadians(FOOT_LEAN_DEG);     // resting on the rider's left foot
        else target = targetLean(motionSpeed, motionYawRate, cfg.motorcycleLeanDegrees);
        lean += (target - lean) * Math.min(1.0, LEAN_RATE * delta);
        if (model != null && modelRest != null) {
            // the model's origin is the ground under mid-wheelbase: rolling about its own Z is rolling on the tyres
            Basis b = new Basis(Vector3.Companion.getBACK(), lean).times(modelRest.getBasis());
            model.setTransform(new Transform3D(b, modelRest.getOrigin()));
        }
    }

    @Override
    protected double seatRollRadians() { return lean; }

    @Override
    protected double rollPivotHeight() { return modelRest != null ? modelRest.getOrigin().getY() : -0.8; }

    @Override
    protected double exitSideOffset() { return 0.75; }

    /** The rider steers with one hand and shoots with the other; the pillion has both free. */
    @Override
    public boolean oneHandedOnly(int seat) { return seat == 0; }

    /** The upright assist pulls the BODY level: the lean is the model's (see the class comment). */
    @Override
    protected Vector3 desiredUpAxis() { return Vector3.Companion.getUP(); }

    @Register public double leanDegreesNow() { return Math.toDegrees(lean); }
    @Register public double motionYawRateNow() { return motionYawRate; }
    @Register public int throwsNow() { return throwCount; }

    // ── The bike's own wheels: spin, steer, suspension ───────────────────────

    private void animateWheels(double delta) {
        float r = Math.max(0.05f, getConfig().wheelRadius);
        Vector3 fwd = getGlobalBasis().getColumn(2).times(-1);
        double vf = fwd.dot(getLinearVelocity());
        if (isFreezeEnabled()) vf = motionSpeed;              // a puppet: its motion, not its (zero) velocity
        spinFront -= vf * delta / r;
        spinBack -= vf * delta / r;
        double frontLift = 0.0, backLift = 0.0;
        int nf = 0, nb = 0;
        for (VehicleWheel w : getWheels()) {
            if (!(w.getNodeOrNull("Wheel") instanceof Node3D holder)) continue;
            double y = w.getPosition().getY() + holder.getPosition().getY();
            if (w.getPosition().getZ() < 0) { frontLift += y; nf++; } else { backLift += y; nb++; }
        }
        if (wheelFront != null) {
            Basis b = new Basis(Vector3.Companion.getUP(), getCurrentSteerAngle())
                    .times(new Basis(Vector3.Companion.getRIGHT(), spinFront)).times(wheelFrontRest.getBasis());
            wheelFront.setTransform(new Transform3D(b, wheelOrigin(wheelFrontRest, nf > 0 ? frontLift / nf : Double.NaN)));
        }
        if (wheelBack != null) {
            Basis b = new Basis(Vector3.Companion.getRIGHT(), spinBack).times(wheelBackRest.getBasis());
            wheelBack.setTransform(new Transform3D(b, wheelOrigin(wheelBackRest, nb > 0 ? backLift / nb : Double.NaN)));
        }
    }

    /** The model wheel's centre, at the height the rays' wheels are at (body space -> model space). */
    private Vector3 wheelOrigin(Transform3D rest, double bodyY) {
        Vector3 o = rest.getOrigin();
        if (Double.isNaN(bodyY) || modelRest == null) return o;
        return new Vector3(o.getX(), bodyY - modelRest.getOrigin().getY(), o.getZ());
    }

    // ── The rider: a pose per bike, a foot down at a stop, a helmet ─────────

    /** Below this speed (m/s) the rider puts the left foot down and the bike rests on it. */
    static final double FOOT_DOWN_SPEED = 1.0;
    /** The lean (deg, to the left) of a bike held up by its rider's foot. */
    private static final double FOOT_LEAN_DEG = 4.0;
    /** The foot goes down this far left of the bike's centre line (m). */
    private static final double FOOT_OUT = 0.32;
    /** Helmet shells: a 白バイ's is white, a civilian's one of these, by the rider. */
    private static final godot.core.Color[] HELMETS = {
            new godot.core.Color(0.08, 0.08, 0.09, 1), new godot.core.Color(0.85, 0.85, 0.82, 1),
            new godot.core.Color(0.62, 0.10, 0.10, 1), new godot.core.Color(0.12, 0.22, 0.48, 1),
            new godot.core.Color(0.75, 0.62, 0.12, 1)};

    private static final class Gear {
        com.openworld.character.RiderPoseModifier pose;
        Node3D helmet;
        godot.api.Skeleton3D skel;
    }

    private final java.util.Map<Character, Gear> gear = new java.util.HashMap<>();

    private boolean footDown() {
        Character drv = getSeatOccupant(0);
        return drv != null && motionSpeed < FOOT_DOWN_SPEED && getConfig() != null;
    }

    /** The rider pose + helmet on (probe_rider_pose's control turns it off: the car's clip, bare-headed). */
    public static boolean riderGear = true;
    @Register public void setRiderGearNow(boolean on) { riderGear = on; }

    /** Every rider aboard wears its gear; one who got off loses it. Visual, every peer, from the seat occupancy. */
    private void updateRiders() {
        java.util.Set<Character> aboard = new java.util.HashSet<>();
        if (!riderGear) {
            for (Gear g : gear.values()) undress(g);
            gear.clear();
            return;
        }
        for (int seat = 0; seat < getSeatCount(); seat++) {
            Character c = getSeatOccupant(seat);
            if (c == null || !GD.isInstanceValid(c)) continue;
            aboard.add(c);
            Gear g = gear.get(c);
            if (g == null || !GD.isInstanceValid(g.pose)) {
                g = dress(c);
                if (g == null) continue;
                gear.put(c, g);
            }
            VehicleConfig cfg = getConfig();
            // the pillion sits up (half the tuck) with its feet on the same pegs
            g.pose.setPose(seat == 0 ? cfg.riderLeanForward : cfg.riderLeanForward * 0.5, cfg.riderThighRaise, cfg.riderKneeBend);
            g.pose.setFootTarget(seat == 0 && footDown() ? footSpot(g.skel) : null);
        }
        if (gear.size() > aboard.size()) {
            java.util.Iterator<java.util.Map.Entry<Character, Gear>> it = gear.entrySet().iterator();
            while (it.hasNext()) {
                java.util.Map.Entry<Character, Gear> e = it.next();
                if (aboard.contains(e.getKey())) continue;
                undress(e.getValue());
                it.remove();
            }
        }
    }

    /** The ground beside the bike under the rider's left hip (world). */
    private Vector3 footSpot(godot.api.Skeleton3D skel) {
        if (skel == null || modelRest == null) return null;
        int hip = skel.findBone("thigh_l");
        if (hip < 0) return null;
        Vector3 hipWorld = skel.getGlobalTransform().times(skel.getBoneGlobalPose(hip).getOrigin());
        Vector3 hipLocal = getGlobalTransform().affineInverse().times(hipWorld);
        // the model's origin is the ground under the bike: the foot stands on that plane, out to the left
        Vector3 local = new Vector3(-FOOT_OUT, modelRest.getOrigin().getY() + 0.02, hipLocal.getZ());
        return getGlobalTransform().times(local);
    }

    private Gear dress(Character c) {
        if (!(c.findChild("Skeleton3D", true, false) instanceof godot.api.Skeleton3D skel)) return null;
        Gear g = new Gear();
        g.skel = skel;
        g.pose = new com.openworld.character.RiderPoseModifier();
        g.pose.setName(new godot.core.StringName(com.openworld.character.RiderPoseModifier.NAME));
        skel.addChild(g.pose);
        // after the clip, BEFORE the aim modifiers: the drive-by aim corrects the bent spine, not the other way
        Node first = skel.getNodeOrNull("SpineAimModifier");
        if (first != null) skel.moveChild(g.pose, first.getIndex());
        String head = skel.findBone("head") >= 0 ? "head" : skel.findBone("head_2") >= 0 ? "head_2" : null;
        if (head != null) {
            godot.api.BoneAttachment3D at = new godot.api.BoneAttachment3D();
            at.setName(new godot.core.StringName("RiderHelmet"));
            at.setBoneName(head);
            skel.addChild(at);
            MeshInstance3D shell = new MeshInstance3D();
            godot.api.SphereMesh m = new godot.api.SphereMesh();
            m.setRadius(HELMET_RADIUS);
            m.setHeight(HELMET_RADIUS * 2.0f);
            godot.api.StandardMaterial3D mat = new godot.api.StandardMaterial3D();
            mat.setAlbedo(helmetColour(c));
            mat.setRoughness(0.35f);
            m.setMaterial(mat);
            shell.setMesh(m);
            shell.setPosition(HELMET_OFFSET);
            shell.setCastShadowsSetting(godot.api.GeometryInstance3D.ShadowCastingSetting.OFF);
            at.addChild(shell);
            g.helmet = at;
        }
        return g;
    }

    /** A helmet shell's radius (m) and its centre from the head bone (bone space, m): the MY PICKS of 3.1b. */
    static final float HELMET_RADIUS = 0.155f;
    static final Vector3 HELMET_OFFSET = new Vector3(0.0, 0.10, 0.01);

    private godot.core.Color helmetColour(Character c) {
        if ("PMB1".equals(modelId())) return new godot.core.Color(0.95, 0.95, 0.95, 1);
        String id = c.getCharacterInfo() != null ? c.getCharacterInfo().characterId : c.getName().toString();
        return HELMETS[Math.floorMod(id.hashCode(), HELMETS.length)];
    }

    private static void undress(Gear g) {
        if (g.pose != null && GD.isInstanceValid(g.pose)) g.pose.queueFree();
        if (g.helmet != null && GD.isInstanceValid(g.helmet)) g.helmet.queueFree();
    }

    @Register
    @Override
    public void _exitTree() {
        for (Gear g : gear.values()) undress(g);
        gear.clear();
        super._exitTree();
    }

    @Register public int riderGearNow() { return gear.size(); }

    // ── A hard crash throws the riders ───────────────────────────────────────

    private void watchForThrow() {
        if (!haveLastVel || isEmptyOfRiders()) return;
        VehicleConfig cfg = getConfig();
        Vector3 v = getLinearVelocity();
        // gravity alone changes the velocity by g * dt a tick; a fall onto the wheels is the springs' business
        Vector3 dvv = v.minus(lastVel);
        double dv = Math.hypot(dvv.getX(), dvv.getZ()) + Math.max(0.0, dvv.getY() - 1.0);
        double tilt = Math.toDegrees(Math.acos(GD.clamp(getGlobalBasis().getColumn(1).dot(Vector3.Companion.getUP()), -1.0, 1.0)));
        // only a HIT counts: the hull touching something this step (the wheels are rays and report nothing). A speed
        // set from outside -- a traffic spawn, a probe -- is a velocity change with nothing touching.
        boolean hit = getContactCount() > 0;
        if ((hit && dv >= cfg.motorcycleEjectDv) || tilt >= FALL_TILT_DEG) {
            throwRiders(lastVel, Math.max(0.0, dv - cfg.motorcycleEjectDv));
        }
    }

    /** Unseat every rider into the air with {@code carried} (the bike's velocity before the hit), hurt by {@code over}. */
    @Register
    public void throwRidersNow() { throwRiders(getLinearVelocity(), 0.0); }

    private void throwRiders(Vector3 carried, double over) {
        VehicleConfig cfg = getConfig();
        for (int seat = getSeatCount() - 1; seat >= 0; seat--) {
            Character c = getSeatOccupant(seat);
            if (c == null || !GD.isInstanceValid(c)) continue;
            Vector3 at = c.getGlobalPosition().plus(new Vector3(0, 0.35, 0));
            tryExit(seat);
            c.setGlobalPosition(at);
            Vector3 launch = carried.times((float) THROW_KEEP).plus(new Vector3(0, THROW_UP, 0));
            MovementController mc = c.movementControllerNow();
            if (mc != null) mc.launch(launch);
            c.setVelocity(launch);
            addCollisionExceptionWith(c);              // the bike tumbling on must not swat its own rider
            clearOf.put(c, RIDER_CLEAR_SECONDS);
            throwCount++;
            Node h = c.getNodeOrNull("Health");
            if (h instanceof Health health) {
                float damage = (float) (8.0 + over * cfg.motorcycleEjectDamagePerDv);
                health.takeDamage(null, damage, DAMAGE_SOURCE_COLLISION);
            }
        }
    }

    /** A thrown rider and the bike ignore each other this long (s). */
    private static final double RIDER_CLEAR_SECONDS = 0.6;
    private final java.util.Map<Character, Double> clearOf = new java.util.HashMap<>();

    private void expireClearOf(double delta) {
        if (clearOf.isEmpty()) return;
        java.util.Iterator<java.util.Map.Entry<Character, Double>> it = clearOf.entrySet().iterator();
        while (it.hasNext()) {
            java.util.Map.Entry<Character, Double> e = it.next();
            double left = e.getValue() - delta;
            if (left > 0.0 && GD.isInstanceValid(e.getKey())) { e.setValue(left); continue; }
            if (GD.isInstanceValid(e.getKey())) removeCollisionExceptionWith(e.getKey());
            it.remove();
        }
    }
}
