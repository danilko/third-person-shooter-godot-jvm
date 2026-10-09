package com.openworld.carrier.helicopter;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.carrier.vehicle.VehicleConfig;
import com.openworld.character.Player;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;
import godot.api.Node3D;
import godot.core.Vector3;
import godot.global.GD;

/**
 * A HELICOPTER carrier (PLAN.md W6, user 2026-10-06: a police helicopter that fires from the air, parked on the
 * hospital roof and at a police station). Arcade, GTA-style, a placeholder to tune:
 *
 * <ul>
 *   <li><b>Flown by a player</b>: with a pilot the rotor runs and the lift holds the weight -- let go and it HOLDS
 *   its height. Space ({@code handbrake}) CLIMBS, Ctrl ({@code descend}, the crouch key) DESCENDS, Shift boosts,
 *   forward/back ({@code motor}) tilts the nose and drives it along its heading, steering YAWS. The body is kept
 *   upright (a strong level torque): it never rolls over. Near the ground the descent is capped by the height
 *   left ({@link #landingRate}), so holding descend settles it on its skids (user 2026-10-07: no graceful
 *   landing before).</li>
 *   <li><b>Flown by the AI</b> ({@link #aiTarget} set, no player at the controls): it holds an ORBIT round the
 *   target at {@link #orbitHeight} over it and {@link #orbitRadius} out, nose on the target -- the platform a door
 *   gunner and a sniper fire from (game.EnforcementDispatch).</li>
 *   <li>With nobody aboard the rotor stops and it sits where it is (a roof helipad).</li>
 * </ul>
 * Seats, health, destruction and replication are {@link Vehicle}'s; the rotor spins the model's part named
 * {@code rotor}. The scene is the Airplane scene with this script (tools/build_craft_scenes.py HLC1).
 */
@Script(className = "Helicopter")
public class Helicopter extends Vehicle {

    /** Fly AT this (an orbit over it): the dispatch's target. Null = a pilot's controls, or parked. */
    @godot.annotation.Visible public Node3D aiTarget;
    public double orbitHeight = 38.0, orbitRadius = 55.0, orbitSpeed = 0.12;
    /** Climb / descend rate (m/s) a pilot gets at full input, and the top horizontal speed (m/s). */
    public double climbRate = 7.0, cruise = 32.0;
    /** Descent near the ground: at most {@code landingGain} x the height over the ground per second, never under
     *  {@code landingRate} (m/s) -- so a held descend arrives at about landingRate. */
    public double landingRate = 1.2, landingGain = 0.5;
    /** Height over the ground under the skids at the last tick (m), for probes; NaN with nothing within 60 m. */
    private double groundClear = Double.NaN;
    private double skidDrop = Double.NaN;
    private double orbitAngle, rotorSpin;

    /** SHOT DOWN (user 2026-10-07: "cannot shoot it down"): health ran out in the air -- no lift, the rotor winding
     *  down, a spin, and the explosion + wreck when it hits something or after {@link #FALL_MAX_SECONDS}. */
    private boolean downed;
    private double downedFor;
    private static final double FALL_MAX_SECONDS = 8.0;
    /** Below this over the ground a dying helicopter just explodes where it is (m). */
    private static final double DOWN_MIN_HEIGHT = 2.5;

    /** The AI orbit keeps at least this clear of whatever is under its orbit point -- a tower, a station roof (m). */
    public double orbitClearance = 18.0;
    private double obstacleTop = Double.NaN, obstacleIn;

    /** The rotors turn about their own hubs (the meshes' pivot is the helicopter's origin), at most this per frame:
     *  two crossed blades repeat every 90 deg, so a faster step strobes and reads as standing still or turning back. */
    private static final double ROTOR_MAX_STEP = 0.35;
    private double rotorAngle, tailAngle;
    private Vector3 rotorHub, tailHub;

    @Override
    protected boolean requiresWheels() { return false; }

    /** The rotor turns while a pilot or the AI flies it: never "idle", so it never parks mid-air. */
    @Override
    protected boolean isIdleInput() { return !flying() && super.isIdleInput(); }

    private boolean flying() {
        return (aiTarget != null && GD.isInstanceValid(aiTarget)) || occupant != null;
    }

    /** True while the AI is flying it at a target. */
    @Register public boolean aiFlyingNow() { return aiTarget != null && GD.isInstanceValid(aiTarget) && !(occupant instanceof Player); }

    @Override
    protected boolean applyLocomotion(VehicleConfig cfg, double delta) {
        Vector3 v = getLinearVelocity();
        float mass = (float) getMass();
        float g = (float) -getGravity().getY();
        if (downed) {
            spinRotor(false, delta);
            fall(delta);
            return false;
        }
        boolean ai = aiFlyingNow();
        boolean run = ai || occupant != null;
        spinRotor(run, delta);
        setCanSleep(!run);                          // a hovering body balances its forces: the engine would sleep it
        if (!run) return v.length() < 0.5;          // rotor stopped: gravity has it (a helipad holds it)
        if (isSleeping()) setSleeping(false);

        Vector3 want;          // the velocity to hold
        Vector3 fwd = getGlobalBasis().getZ().times(-1.0);
        fwd.setY(0);
        if (fwd.length() < 1e-3) fwd = new Vector3(0, 0, -1);
        fwd = fwd.normalized();
        double yawWant;
        if (ai) {
            Vector3 tp = aiTarget.getGlobalPosition();
            orbitAngle += orbitSpeed * delta;
            Vector3 spot = tp.plus(new Vector3(Math.cos(orbitAngle) * orbitRadius, orbitHeight, Math.sin(orbitAngle) * orbitRadius));
            // over a tower or a station roof the orbit rises: never closer than orbitClearance to what is under it
            // ... and so does the way there: under itself and where it will be in AHEAD_SECONDS (it flew to the
            // orbit point in a straight line and dipped to 6 m over the roofs on the way, H1 2026-10-09)
            obstacleIn -= delta;
            if (obstacleIn <= 0) {
                obstacleIn = 0.5;
                Vector3 here = getGlobalPosition();
                Vector3 ahead = here.plus(new Vector3(v.getX(), 0, v.getZ()).times(AHEAD_SECONDS));
                obstacleTop = maxTop(maxTop(topBelow(spot), topBelow(here)), topBelow(ahead));
            }
            if (!Double.isNaN(obstacleTop) && spot.getY() < obstacleTop + orbitClearance)
                spot = new Vector3(spot.getX(), obstacleTop + orbitClearance, spot.getZ());
            Vector3 to = spot.minus(getGlobalPosition());
            want = to.times(0.5);
            if (want.length() > cruise) want = want.normalized().times(cruise);
            // too low over what is under it or ahead: climb first, at half the horizontal speed
            if (!Double.isNaN(obstacleTop) && getGlobalPosition().getY() < obstacleTop + orbitClearance)
                want = new Vector3(want.getX() * 0.5, Math.max(want.getY(), climbRate), want.getZ() * 0.5);
            Vector3 face = tp.minus(getGlobalPosition());
            yawWant = Math.atan2(-face.getX(), -face.getZ());
        } else {
            double climb = (cmd.handbrake ? 1.0 : 0.0) - (cmd.descend ? 1.0 : 0.0);
            double vy = climb * climbRate;
            groundClear = clearanceBelow();
            if (vy < 0 && !Double.isNaN(groundClear))
                vy = -Math.min(climbRate, Math.max(landingRate, groundClear * landingGain));
            Vector3 h = fwd.times(cmd.motor * cruise * (cmd.boost ? 1.4 : 1.0));
            want = new Vector3(h.getX(), vy, h.getZ());
            yawWant = Double.NaN;
        }
        // hold the wanted velocity: a force proportional to the error, plus the weight
        Vector3 err = want.minus(v);
        Vector3 f = err.times(mass * 1.6);
        f.setY(f.getY() + mass * g);
        applyCentralForce(f);
        // yaw: toward the target (AI), or by the stick (pilot)
        Vector3 up = new Vector3(0, 1, 0);
        double yawRate = getAngularVelocity().getY();
        if (!Double.isNaN(yawWant)) {
            double cur = Math.atan2(-fwd.getX(), -fwd.getZ());
            double d = Math.atan2(Math.sin(yawWant - cur), Math.cos(yawWant - cur));
            applyTorque(up.times((float) ((d * 2.0 - yawRate) * mass * 6.0)));
        } else {
            applyTorque(up.times((float) ((cmd.steering * 1.2 - yawRate) * mass * 6.0)));
        }
        // keep it level, tilted a little into its motion (the look of a helicopter, no roll-over)
        Vector3 bodyUp = getGlobalBasis().getY();
        Vector3 tiltTo = up.plus(new Vector3(want.getX(), 0, want.getZ()).times(-0.012)).normalized();
        Vector3 axis = bodyUp.cross(tiltTo);
        Vector3 av = getAngularVelocity();
        applyTorque(axis.times(mass * 40.0f).minus(new Vector3(av.getX(), 0, av.getZ()).times(mass * 8.0f)));
        return false;
    }

    /** How far ahead along its motion the AI's clearance looks (s). */
    private static final double AHEAD_SECONDS = 2.0;

    private static double maxTop(double a, double b) {
        return Double.isNaN(a) ? b : Double.isNaN(b) ? a : Math.max(a, b);
    }

    /** The highest WORLD surface straight under {@code at}, looking from 200 m above it; NaN if none. */
    private double topBelow(Vector3 at) {
        var sp = getWorld3d() != null ? getWorld3d().getDirectSpaceState() : null;
        if (sp == null) return Double.NaN;
        godot.core.VariantArray<godot.core.RID> ex = new godot.core.VariantArray<>(godot.core.RID.class);
        ex.add(getRid());
        var q = godot.api.PhysicsRayQueryParameters3D.create(at.plus(new Vector3(0, 200, 0)), at.plus(new Vector3(0, -80, 0)),
                com.openworld.util.CollisionLayers.WORLD, ex);
        godot.core.Dictionary<Object, Object> hit = sp.intersectRay(q);
        return hit != null && !hit.isEmpty() && hit.get("position") instanceof Vector3 p ? p.getY() : Double.NaN;
    }

    /**
     * Health ran out. In the air it is SHOT DOWN: it falls (see {@link #fall}) and the ordinary destruction --
     * explosion, wreck, despawn -- runs on impact. On or near the ground it is destroyed where it is.
     */
    @Register
    @Override
    public void onVehicleDestruction() {
        if (downed) return;
        double clear = clearanceBelow();
        if (Double.isNaN(clear) || clear > DOWN_MIN_HEIGHT) {
            downed = true;
            downedFor = 0;
            aiTarget = null;
            setCanSleep(false);
            return;
        }
        super.onVehicleDestruction();
    }

    /** True while it is falling, shot down (probes). */
    @Register public boolean downedNow() { return downed; }

    /** A shot-down helicopter: no lift, a yaw spin, and the destruction when it lands, hits something or times out. */
    private void fall(double delta) {
        downedFor += delta;
        float mass = (float) getMass();
        applyTorque(new Vector3(0, 1, 0).times((float) ((2.5 - getAngularVelocity().getY()) * mass * 3.0)));
        double clear = clearanceBelow();
        boolean landed = !Double.isNaN(clear) && clear < 0.6;
        boolean hit = getContactCount() > 0 && downedFor > 0.3;
        if (landed || hit || downedFor > FALL_MAX_SECONDS) {
            downed = false;            // let the base run once
            super.onVehicleDestruction();
        }
    }

    /** The skids' height over whatever is under them (a ray down from the body, its own drop to the skids measured
     *  from the collision shapes' lowest point), NaN beyond 60 m. */
    private double clearanceBelow() {
        if (Double.isNaN(skidDrop)) skidDrop = bottomDrop();
        var sp = getWorld3d() != null ? getWorld3d().getDirectSpaceState() : null;
        if (sp == null) return Double.NaN;
        Vector3 o = getGlobalPosition();
        godot.core.VariantArray<godot.core.RID> ex = new godot.core.VariantArray<>(godot.core.RID.class);
        ex.add(getRid());
        var q = godot.api.PhysicsRayQueryParameters3D.create(o, o.plus(new Vector3(0, -60, 0)),
                com.openworld.util.CollisionLayers.WORLD | com.openworld.util.CollisionLayers.VEHICLE, ex);
        godot.core.Dictionary<Object, Object> hit = sp.intersectRay(q);
        if (hit == null || hit.isEmpty() || !(hit.get("position") instanceof Vector3 p)) return Double.NaN;
        return Math.max(0.0, o.getY() - p.getY() - skidDrop);
    }

    /** How far the lowest collision shape reaches below the body's origin (m). */
    private double bottomDrop() {
        double lo = 0.0;
        for (Node c : getChildren()) {
            if (!(c instanceof godot.api.CollisionShape3D cs) || cs.getShape() == null) continue;
            var aabb = cs.getShape().getDebugMesh().getAabb();
            Vector3 low = cs.getTransform().times(aabb.getPosition());
            lo = Math.min(lo, low.getY());
        }
        return -lo;
    }

    /** Probe readout: the skids' height over the ground (m), NaN when unknown. */
    @Register public double groundClearNow() { return groundClear; }

    private void spinRotor(boolean run, double delta) {
        rotorSpin = run ? Math.min(1.0, rotorSpin + delta * 0.5) : Math.max(0.0, rotorSpin - delta * 0.2);
        if (rotorSpin <= 0) return;
        double step = Math.min(rotorSpin * 40.0 * delta, ROTOR_MAX_STEP);
        rotorAngle = (rotorAngle + step) % (Math.PI * 2.0);
        tailAngle = (tailAngle + step * 1.6) % (Math.PI * 2.0);
        if (getNodeOrNull("Model/rotor") instanceof godot.api.MeshInstance3D r) {
            if (rotorHub == null) rotorHub = hubOf(r);
            r.setTransform(about(rotorHub, new Vector3(0, 1, 0), rotorAngle));
        }
        if (getNodeOrNull("Model/tail_rotor") instanceof godot.api.MeshInstance3D t) {
            if (tailHub == null) tailHub = hubOf(t);
            t.setTransform(about(tailHub, new Vector3(1, 0, 0), tailAngle));
        }
    }

    /** The centre of a part's mesh in its own frame: its hub (a placeholder part's pivot is the craft's origin). */
    private static Vector3 hubOf(godot.api.MeshInstance3D m) {
        godot.core.AABB a = m.getAabb();
        return a.getPosition().plus(a.getSize().times(0.5));
    }

    /** A rotation of {@code angle} about {@code axis} through {@code hub} (the part's rest transform is identity). */
    private static godot.core.Transform3D about(Vector3 hub, Vector3 axis, double angle) {
        godot.core.Basis b = new godot.core.Basis(axis, angle);
        return new godot.core.Transform3D(b, hub.minus(b.times(hub)));
    }
}
