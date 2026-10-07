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
 *   <li><b>Flown by a player</b>: with a pilot the rotor runs and the lift holds the weight; the jump key
 *   ({@code handbrake}) CLIMBS, brake DESCENDS, forward/back ({@code motor}) tilts the nose and drives it along its
 *   heading, steering YAWS. The body is kept upright (a strong level torque): it never rolls over.</li>
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
    private double orbitAngle, rotorSpin;

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
            Vector3 to = spot.minus(getGlobalPosition());
            want = to.times(0.5);
            if (want.length() > cruise) want = want.normalized().times(cruise);
            Vector3 face = tp.minus(getGlobalPosition());
            yawWant = Math.atan2(-face.getX(), -face.getZ());
        } else {
            double climb = (cmd.handbrake ? 1.0 : 0.0) - (cmd.brake ? 1.0 : 0.0);
            Vector3 h = fwd.times(cmd.motor * cruise * (cmd.boost ? 1.4 : 1.0));
            want = new Vector3(h.getX(), climb * climbRate, h.getZ());
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

    private void spinRotor(boolean run, double delta) {
        rotorSpin = run ? Math.min(1.0, rotorSpin + delta * 0.5) : Math.max(0.0, rotorSpin - delta * 0.2);
        if (rotorSpin <= 0) return;
        Node r = getNodeOrNull("Model/rotor");
        if (r instanceof Node3D n) n.rotateY((float) (rotorSpin * 40.0 * delta));
    }
}
