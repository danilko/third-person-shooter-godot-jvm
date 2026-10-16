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
    /** The bars' grip markers, from the model (the bike .blend's grip_l / grip_r Empties); null on a model without them. */
    private Node3D gripLeft, gripRight;
    private Transform3D wheelFrontRest, wheelBackRest;
    private double spinFront, spinBack;
    private double lean;
    private double lastHeading = Double.NaN;
    private Vector3 lastPos;
    private Vector3 lastVel = Vector3.Companion.getZERO();
    private boolean haveLastVel = false;
    private double motionSpeed, motionYawRate;
    /** This tick's ground velocity from MOTION (m/s, world), the last one, and the acceleration along the bike's left (m/s^2, eased). */
    private Vector3 motionVel = Vector3.Companion.getZERO();
    private Vector3 lastMotionVel;
    private double lateralAccel;
    /** The slip angle (rad, + = the nose LEFT of where it is going, folded into -90..90: see slipAngle), eased; 0 below SLIP_FROM_SPEED. */
    private double slip;
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
            if (m.getNodeOrNull("grip_l") instanceof Node3D gl) gripLeft = gl;
            if (m.getNodeOrNull("grip_r") instanceof Node3D gr) gripRight = gr;
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
        updateDust(delta);
        updateRiders(delta);
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
                measureSlide(heading, delta);
            } else {
                posTrail.clear();
                velTrail.clear();
            }
        }
        lastPos = pos;
        lastHeading = heading;
    }

    /** Below this speed (m/s) there is no slip angle worth the name: the direction of travel is noise. */
    static final double SLIP_FROM_SPEED = 2.0;
    /** The acceleration and slip ease over ~1/this s (a position's second difference is noisy at 60 Hz). */
    private static final double SLIDE_EASE = 14.0;

    /** Velocity and acceleration are differences over this window (s), not frame to frame: a puppet moves in snapshot
     *  steps (a frame standing still, then a double one), whose raw second difference is +-900 m/s^2 of noise --
     *  measured on two peers, it leaned the observer's bike 20 deg the WRONG way into a slide, and an eased (EMA)
     *  velocity still dipped it 12 deg. A window spans several steps, so it sees the true motion. Both peers measure
     *  alike, so they agree; the cost is ~0.1 s of lag, inside the lean's own easing. */
    static final double MOTION_WINDOW = 0.1;
    private final java.util.ArrayDeque<double[]> posTrail = new java.util.ArrayDeque<>();   // {t, x, z}
    private final java.util.ArrayDeque<double[]> velTrail = new java.util.ArrayDeque<>();   // {t, vx, vz}
    private double motionClock;

    /** The difference of the newest entry over the oldest one at least MOTION_WINDOW back, per second; null if too short. */
    private static double[] windowRate(java.util.ArrayDeque<double[]> trail, double now) {
        while (trail.size() > 2) {
            java.util.Iterator<double[]> it = trail.iterator();
            it.next();
            if (now - it.next()[0] >= MOTION_WINDOW) trail.removeFirst(); else break;
        }
        double[] a = trail.peekFirst(), b = trail.peekLast();
        if (a == null || b == null || b[0] - a[0] < 0.5 * MOTION_WINDOW) return null;
        double dt = b[0] - a[0];
        return new double[] {(b[1] - a[1]) / dt, (b[2] - a[2]) / dt};
    }

    /** The body-frame lateral acceleration (dv_lat/dt + v_long x yaw rate, read as one vector derivative) and the slip angle. */
    private void measureSlide(double heading, double delta) {
        motionClock += delta;
        Vector3 p = getGlobalPosition();
        posTrail.addLast(new double[] {motionClock, p.getX(), p.getZ()});
        double[] v = windowRate(posTrail, motionClock);
        if (v == null) return;
        Vector3 vel = new Vector3(v[0], 0.0, v[1]);
        motionVel = vel;
        double k = Math.min(1.0, SLIDE_EASE * delta);
        velTrail.addLast(new double[] {motionClock, v[0], v[1]});
        double[] acc = windowRate(velTrail, motionClock);
        if (acc != null) {
            Vector3 left = getGlobalBasis().getColumn(0).times(-1.0);
            double a = acc[0] * left.getX() + acc[1] * left.getZ();
            if (Math.abs(a) < 60.0) lateralAccel += (a - lateralAccel) * k;      // a hit or a reset is not a lean
        }
        lastMotionVel = vel;
        double sp = Math.hypot(vel.getX(), vel.getZ());
        double target = sp >= SLIP_FROM_SPEED ? slipAngle(heading, Math.atan2(-vel.getX(), -vel.getZ())) : 0.0;
        slip += (target - slip) * k;
    }

    /**
     * The nose's angle left of the direction of travel (rad), both as headings atan2(back.x, back.z), FOLDED about 90 deg
     * into -90..90: a slide that swings past sideways keeps its sign and comes back down continuously (100 deg reads 80),
     * and a bike rolling straight backwards reads 0, not 180 -- so nothing snaps when a spin passes sideways.
     */
    static double slipAngle(double heading, double travelHeading) {
        double b = heading - travelHeading;
        while (b > Math.PI) b -= 2 * Math.PI;
        while (b < -Math.PI) b += 2 * Math.PI;
        if (b > Math.PI / 2) b = Math.PI - b;
        else if (b < -Math.PI / 2) b = -Math.PI - b;
        return b;
    }

    /** The lean this bike should hold now from its yaw rate alone (radians, + = left): right in a turn that grips, wrong
     *  in a slide -- a spin leans it to the cap while nothing pushes it sideways. The control of {@link #slideLean}. */
    public static double targetLean(double speed, double yawRate, double maxDeg) {
        double max = Math.toRadians(maxDeg);
        double a = Math.atan(speed * yawRate / G);
        return Math.max(-max, Math.min(max, a));
    }

    /** In a slide the rider leans this much further into it per radian of slip (the dirt-track look, past what the force
     *  alone asks for): 30 deg of slip adds 10 deg. */
    static final double SLIP_LEAN = 1.0 / 3.0;

    /**
     * The lean from what really pushes the bike sideways (radians, + = left): the tyres' force balances gravity at
     * atan(a_lat / g), a_lat the acceleration along the bike's own left -- in a turn that grips that is v x yaw rate,
     * in a slide it is the sliding tyres' drag, so a spin with the bike still going straight leans it hardly at all --
     * plus {@link #SLIP_LEAN} of the slip angle, so a powerslide leans INTO the turn with the rear stepping out.
     */
    public static double slideLeanTarget(double lateralAccel, double slip, double speed, double maxDeg) {
        double max = Math.toRadians(maxDeg);
        double a = Math.atan(lateralAccel / G) + SLIP_LEAN * slip * Math.min(1.0, speed / 6.0);
        return Math.max(-max, Math.min(max, a));
    }

    /** false = the lean from the yaw rate and the front wheel from the bars, as before the slide lean (probe control). */
    public static boolean slideLean = true;
    @Register public void setSlideLeanNow(boolean on) { slideLean = on; }
    @Register public double slipDegreesNow() { return Math.toDegrees(slip); }
    @Register public double lateralAccelNow() { return lateralAccel; }
    @Register public double frontWheelSteerDegreesNow() { return Math.toDegrees(frontSteer); }

    private void updateLean(double delta) {
        VehicleConfig cfg = getConfig();
        double target;
        if (isEmptyOfRiders() && motionSpeed < 0.3) target = Math.toRadians(Math.min(KICKSTAND_DEG, cfg.motorcycleLeanDegrees));
        else if (footDown()) target = Math.toRadians(FOOT_LEAN_DEG);     // resting on the rider's left foot
        else if (slideLean) target = slideLeanTarget(lateralAccel, slip, motionSpeed, cfg.motorcycleLeanDegrees);
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
        frontSteer = frontWheelSteer(getCurrentSteerAngle(), slideLean ? slip : 0.0);
        if (wheelFront != null) {
            Basis b = new Basis(Vector3.Companion.getUP(), frontSteer)
                    .times(new Basis(Vector3.Companion.getRIGHT(), spinFront)).times(wheelFrontRest.getBasis());
            wheelFront.setTransform(new Transform3D(b, wheelOrigin(wheelFrontRest, nf > 0 ? frontLift / nf : Double.NaN)));
        }
        if (wheelBack != null) {
            Basis b = new Basis(Vector3.Companion.getRIGHT(), spinBack).times(wheelBackRest.getBasis());
            wheelBack.setTransform(new Transform3D(b, wheelOrigin(wheelBackRest, nb > 0 ? backLift / nb : Double.NaN)));
        }
    }

    /** The slip (deg) past which the front wheel stops following the bars and points along the slide, fully by SLIDE_STEER_FULL. */
    static final double SLIDE_STEER_FROM = 6.0, SLIDE_STEER_FULL = 14.0;
    /** The front wheel's own turn is capped here (deg): past it the rider has lost it. */
    static final double FRONT_STEER_MAX = 45.0;
    private double frontSteer;

    /**
     * The model front wheel's steer (rad, + = left): the bars' angle while the tyres grip; in a slide it turns to point
     * where the bike is GOING (-slip, the counter-steer of a dirt-track powerslide), blended in over SLIDE_STEER_FROM ..
     * SLIDE_STEER_FULL deg of slip. Visual only: the handling's steer is the rays'.
     */
    static double frontWheelSteer(double bars, double slip) {
        double s = Math.abs(Math.toDegrees(slip));
        double w = Math.max(0.0, Math.min(1.0, (s - SLIDE_STEER_FROM) / (SLIDE_STEER_FULL - SLIDE_STEER_FROM)));
        w = w * w * (3.0 - 2.0 * w);
        double max = Math.toRadians(FRONT_STEER_MAX);
        return Math.max(-max, Math.min(max, bars + (-slip - bars) * w));
    }

    // ── Dust at the rear wheel while it slides ─────────────────────────────

    /** The rear tyre's dust (a thin Binbun3D smoke at tyre scale, assets/vfx/smoke/effects/tyre_dust/). */
    static final String DUST_VFX = "res://assets/vfx/smoke/effects/tyre_dust/tyre_dust_vfx.tscn";
    /** It kicks up past this slip (deg) and this speed (m/s), and keeps going this long (s) after, so a wobble is one puff. */
    static final double DUST_SLIP_DEG = 10.0, DUST_SPEED = 3.0, DUST_KEEP = 0.25;
    private com.openworld.vfx.SmokeVfx dust;
    private double dustLeft;

    /** Read off the MOTION, like the lean: a puppet raises the same dust with no message. Built on the first slide. */
    private void updateDust(double delta) {
        boolean sliding = slideLean && isAlive() && !isDummy() && motionSpeed > DUST_SPEED
                && Math.abs(Math.toDegrees(slip)) > DUST_SLIP_DEG && onTheGround();
        dustLeft = sliding ? DUST_KEEP : Math.max(0.0, dustLeft - delta);
        boolean on = dustLeft > 0.0;
        if (on && dust == null) dust = buildDust();
        if (dust != null && dust.emittingNow() != on) dust.setEmitting(on);
    }

    private boolean onTheGround() {
        if (isFreezeEnabled()) return lastMotionVel != null;            // a puppet: its rays do not run
        for (VehicleWheel w : getWheels()) if (w.grounded()) return true;
        return false;
    }

    private com.openworld.vfx.SmokeVfx buildDust() {
        if (!(GD.load(DUST_VFX) instanceof godot.api.PackedScene ps)
                || !(ps.instantiate() instanceof com.openworld.vfx.SmokeVfx d)) return null;
        // on the ground under the rear wheel: the model's origin is the ground under mid-wheelbase
        Vector3 at = new Vector3(0.0, 0.05, 0.6);
        if (modelRest != null && wheelBackRest != null) {
            Vector3 o = wheelBackRest.getOrigin();
            at = modelRest.times(new Vector3(o.getX(), 0.05, o.getZ()));      // times(Vector3) is a pure xform
        }
        d.setPosition(at);
        d.setName("TyreDust");
        addChild(d);
        return d;
    }

    @Register public boolean dustNow() { return dust != null && dust.emittingNow(); }

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
        com.openworld.character.RiderHandsModifier hands;
        Node3D helmet;                  // the BoneAttachment3D on the head bone
        Node3D model;                   // the helmet itself under it: moves from the hand onto the head and back
        Node3D grab;                    // the helmet's `grab` Empty: the right hand holds it while it goes on / off
        Transform3D fit;                // the model's own place under the head bone (the .glb's root: identity)
        godot.api.Skeleton3D skel;
        double donning;                 // s into the put-on; >= HELMET_ON_SECONDS = on
        double doffing = -1.0;          // s into the take-off once the rider got off; -1 = still riding
    }

    private final java.util.Map<Character, Gear> gear = new java.util.HashMap<>();
    /** Riders who got off and are taking the helmet off (their gear goes when it is off). */
    private final java.util.Map<Character, Gear> leaving = new java.util.HashMap<>();

    /** The helmet goes on (and comes off) over this long (s): the right hand carries it from beside the chin up over the
     *  head and down onto it. A placeholder for an artist's clip (no helmet clip in the library, searched 2026-10-16). */
    static final double HELMET_ON_SECONDS = 0.5;
    /** Where the put-on starts / the take-off ends, in the head bone's frame (m): low at the right, in front of the chin
     *  -- the hand's reach from the bars -- and the path's top, over the forehead. */
    private static final Vector3 HELMET_FROM = new Vector3(-0.16, -0.10, 0.26);
    private static final Vector3 HELMET_OVER = new Vector3(-0.04, 0.34, 0.16);
    /** The helmet tips back this far (deg, about the head's x) at the start, as a hand holds one by the rim. */
    private static final double HELMET_FROM_TILT = 70.0;

    private boolean footDown() {
        Character drv = getSeatOccupant(0);
        return drv != null && motionSpeed < FOOT_DOWN_SPEED && getConfig() != null;
    }

    /** The rider pose + helmet on (probe_rider_pose's control turns it off: the car's clip, bare-headed). */
    public static boolean riderGear = true;
    @Register public void setRiderGearNow(boolean on) { riderGear = on; }

    /** Every rider aboard wears its gear; one who got off takes the helmet off and loses it. Visual, every peer, from
     *  the seat occupancy. */
    private void updateRiders(double delta) {
        java.util.Set<Character> aboard = new java.util.HashSet<>();
        if (!riderGear) {
            for (Gear g : gear.values()) undress(g);
            for (Gear g : leaving.values()) undress(g);
            gear.clear();
            leaving.clear();
            return;
        }
        for (int seat = 0; seat < getSeatCount(); seat++) {
            Character c = getSeatOccupant(seat);
            if (c == null || !GD.isInstanceValid(c)) continue;
            aboard.add(c);
            Gear g = gear.get(c);
            if (g == null || !GD.isInstanceValid(g.pose) || !GD.isInstanceValid(g.hands)) {
                Gear off = leaving.remove(c);      // back on before the helmet was off: start again
                if (off != null) undress(off);
                g = dress(c);
                if (g == null) continue;
                gear.put(c, g);
            }
            VehicleConfig cfg = getConfig();
            // the pillion sits up (half the tuck) with its feet on the same pegs
            g.pose.setPose(seat == 0 ? cfg.riderLeanForward : cfg.riderLeanForward * 0.5, cfg.riderThighRaise, cfg.riderKneeBend);
            g.pose.setFootTarget(seat == 0 && footDown() ? footSpot(g.skel) : null);
            // the rider's hands on the bars (the pillion keeps the clip's); the right lets go to hold a weapon
            g.hands.setGrips(seat == 0 ? gripLeft : null, seat == 0 ? gripRight : null);
            g.hands.setRightHandOnBar(!holdsWeapon(c));
            g.donning += delta;
            placeHelmet(g, g.donning / HELMET_ON_SECONDS);
            g.hands.setRightHold(g.donning < HELMET_ON_SECONDS ? g.grab : null);
            showHelmet(g, c);
        }
        if (gear.size() > aboard.size()) {
            java.util.Iterator<java.util.Map.Entry<Character, Gear>> it = gear.entrySet().iterator();
            while (it.hasNext()) {
                java.util.Map.Entry<Character, Gear> e = it.next();
                if (aboard.contains(e.getKey())) continue;
                Character c = e.getKey();
                Gear g = e.getValue();
                it.remove();
                // got off: the pose goes now; the helmet comes off by the right hand. A THROWN rider, a dead one, or
                // one whose helmet never went on loses it at once (there is no clip for a helmet flying off).
                if (g.pose != null && GD.isInstanceValid(g.pose)) g.pose.queueFree();
                g.pose = null;
                boolean calm = GD.isInstanceValid(c) && !clearOf.containsKey(c) && c.isAlive()
                        && g.model != null && g.donning >= HELMET_ON_SECONDS;
                if (!calm) { undress(g); continue; }
                g.hands.setGrips(null, null);
                g.doffing = 0.0;
                leaving.put(c, g);
            }
        }
        if (!leaving.isEmpty()) {
            java.util.Iterator<java.util.Map.Entry<Character, Gear>> it = leaving.entrySet().iterator();
            while (it.hasNext()) {
                java.util.Map.Entry<Character, Gear> e = it.next();
                Gear g = e.getValue();
                g.doffing += delta;
                boolean done = g.doffing >= HELMET_ON_SECONDS || !GD.isInstanceValid(e.getKey())
                        || g.model == null || !GD.isInstanceValid(g.model);
                if (done) { undress(g); it.remove(); continue; }
                placeHelmet(g, 1.0 - g.doffing / HELMET_ON_SECONDS);
                g.hands.setRightHold(g.grab);
            }
        }
    }

    /** The helmet {@code u} of the way on (0 = in the right hand beside the chin, 1 = on the head): over the forehead
     *  on a quadratic curve, tipping forward as it comes. */
    private static void placeHelmet(Gear g, double u) {
        if (g.model == null || !GD.isInstanceValid(g.model)) return;
        u = Math.max(0.0, Math.min(1.0, u));
        double e = u * u * (3.0 - 2.0 * u);
        double a = 1.0 - e;
        Vector3 p = HELMET_FROM.times(a * a).plus(HELMET_OVER.times(2.0 * a * e)).plus(g.fit.getOrigin().times(e * e));
        Basis tilt = new Basis(Vector3.Companion.getRIGHT(), -Math.toRadians(HELMET_FROM_TILT) * a);
        g.model.setTransform(new Transform3D(tilt.times(g.fit.getBasis()), p));
    }

    /** "Show my helmet" off (QualitySettings, GTA V's): the LOCAL player's helmet is not drawn; everyone else's is.
     *  Hidden with the head too (a first-person view is inside the helmet, looking at its liner). */
    private static void showHelmet(Gear g, Character c) {
        if (g.helmet == null || !GD.isInstanceValid(g.helmet)) return;
        com.openworld.game.QualitySettings q = com.openworld.game.QualitySettings.get();
        boolean hide = !c.headShownNow() || q != null && !q.showMyHelmet && c.isLocallyOwnedPlayer();
        if (g.helmet.isVisible() == hide) g.helmet.setVisible(!hide);
    }

    /** True while {@code c} has a weapon in hand (anything but bare fists): the one-handed drive-by's grip. */
    private static boolean holdsWeapon(Character c) {
        if (!(c.getNodeOrNull("WeaponController") instanceof com.openworld.weapon.WeaponController wc)) return false;
        com.openworld.weapon.WeaponItem w = wc.getCurrentWeaponItem();
        return w != null && !"fist".equals(w.weaponArchetype);
    }

    /** probe_rider_pose's control: every rider's hands left where the clip puts them. */
    @Register public void setHandsOnBarsNow(boolean on) { com.openworld.character.RiderHandsModifier.handsOnBars = on; }
    @Register public boolean hasGripsNow() { return gripLeft != null && gripRight != null; }

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
        // the hands LAST, after the aim modifiers: a drive-by's torso turn must not carry the left hand off the bar
        g.hands = new com.openworld.character.RiderHandsModifier();
        g.hands.setName(new godot.core.StringName(com.openworld.character.RiderHandsModifier.NAME));
        skel.addChild(g.hands);
        g.pose.setHands(g.hands);
        String head = skel.findBone("head") >= 0 ? "head" : skel.findBone("head_2") >= 0 ? "head_2" : null;
        if (head != null) {
            godot.api.BoneAttachment3D at = new godot.api.BoneAttachment3D();
            at.setName(new godot.core.StringName("RiderHelmet"));
            at.setBoneName(head);
            skel.addChild(at);
            g.helmet = at;
            Node3D model = helmetModel(c);
            if (model != null) {
                at.addChild(model);
                g.model = model;
                g.fit = model.getTransform();
                g.grab = model.findChild("grab", true, false) instanceof Node3D n ? n : null;
                placeHelmet(g, 0.0);
                return g;
            }
            // no .glb: the 3.1b sphere, on at once
            g.donning = HELMET_ON_SECONDS;
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
        }
        return g;
    }

    /** The bike's helmet .glb ({@link VehicleConfig#riderHelmet}), its {@code shell} material tinted for this rider;
     *  null when the file is missing (the sphere stands in). */
    private Node3D helmetModel(Character c) {
        VehicleConfig cfg = getConfig();
        String kind = cfg != null && cfg.riderHelmet != null && !cfg.riderHelmet.isEmpty() ? cfg.riderHelmet : "open";
        String path = "res://assets/characters/gear/Helmet_" + kind + ".glb";
        if (!godot.api.ResourceLoader.INSTANCE.exists(path, "") || !(GD.load(path) instanceof godot.api.PackedScene ps)) return null;
        if (!(ps.instantiate() instanceof Node3D root)) return null;
        root.setName(new godot.core.StringName("Helmet_" + kind));
        godot.core.Color colour = helmetColour(c);
        for (Node n : root.findChildren("*", "MeshInstance3D", true, false)) {
            if (!(n instanceof MeshInstance3D mi) || mi.getMesh() == null) continue;
            mi.setCastShadowsSetting(godot.api.GeometryInstance3D.ShadowCastingSetting.OFF);
            for (int s = 0; s < mi.getMesh().getSurfaceCount(); s++) {
                if (!(mi.getMesh().surfaceGetMaterial(s) instanceof godot.api.BaseMaterial3D m)) continue;
                if (!"shell".equals(m.getName())) continue;
                godot.api.BaseMaterial3D tint = (godot.api.BaseMaterial3D) m.duplicate();
                tint.setAlbedo(colour);
                mi.setSurfaceOverrideMaterial(s, tint);
            }
        }
        return root;
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
        if (g.hands != null && GD.isInstanceValid(g.hands)) g.hands.queueFree();
        if (g.helmet != null && GD.isInstanceValid(g.helmet)) g.helmet.queueFree();
    }

    @Register
    @Override
    public void _exitTree() {
        for (Gear g : gear.values()) undress(g);
        for (Gear g : leaving.values()) undress(g);
        gear.clear();
        leaving.clear();
        super._exitTree();
    }

    @Register public int riderGearNow() { return gear.size(); }
    /** probe_rider_pose: riders still taking a helmet off after getting off. */
    @Register public int ridersLeavingNow() { return leaving.size(); }

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
