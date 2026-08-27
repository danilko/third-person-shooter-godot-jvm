package com.openworld.net;

import com.openworld.control.Controller;
import com.openworld.control.UserCommand;
import com.openworld.weapon.WeaponController;
import com.openworld.net.NetMessageCodec.DecodedVehicleSnapshot;
import com.openworld.net.Quat;
import com.openworld.net.RigidSnapshotInterpolator;
import com.openworld.net.TimestampUnwrapper;
import com.openworld.net.Vec3;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;
import godot.core.Basis;
import godot.core.Quaternion;
import godot.core.Vector3;
import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.carrier.vehicle.VehicleWheel;
import com.openworld.character.Health;

/**
 * Controller for vehicles this peer does not simulate (Round 11 N3) — the vehicle
 * counterpart of {@link com.openworld.net.NetworkController}. Attached/removed by
 * {@code Vehicle.applyAuthorityState()} whenever locomotion authority flips (driver
 * enter/exit, lazy-attach on the first received vehicle snapshot).
 *
 * isAuthority() returns false, so {@code Vehicle._physicsProcess} never gathers input;
 * the body itself is frozen ({@code setFreezeEnabled(true)}) and placed kinematically here
 * each rendered frame from the {@link RigidSnapshotInterpolator} — full quaternion
 * orientation (vehicles roll and pitch), dead-reckoned by linear + angular velocity.
 *
 * Steering/throttle/flags from the latest snapshot are cached for two consumers: wheel
 * visuals on this peer (steer angle + spin), and the host's re-broadcast of a
 * client-driven vehicle (the host's copy IS this puppet, so the batch entry reads the
 * cached values rather than dead local physics state).
 */
@Script(className = "VehicleNetworkController")
public class VehicleNetworkController extends Controller {

    private final RigidSnapshotInterpolator interpolator = new RigidSnapshotInterpolator();
    // Unwraps the wire's 32-bit senderTimeMs into a never-wrapping 64-bit timeline — same
    // rationale as NetworkController's senderClock (survives the ~24.8-day int rollover).
    private final TimestampUnwrapper senderClock = new TimestampUnwrapper();

    // Fire-as-state for the vehicle's own weapon (VEHICLE_WEAPON mode): cue on counter change,
    // with the same first-snapshot suppression as NetworkController.
    private boolean haveFireSeq = false;
    private int     lastFireSeq = 0;

    // Latest received discrete driving state — wheel visuals + host re-broadcast.
    private float   lastSteerAngle = 0f;
    private float   lastThrottle   = 0f;
    private boolean lastHandbrake  = false;
    private boolean lastBrake      = false;
    private boolean lastSlipping   = false;
    private int     lastFlatMask   = 0;

    // Discrete-state forward gate (same shape as NetworkController.latestDiscreteTimeMs).
    private long latestDiscreteTimeMs = Long.MIN_VALUE;

    @Override
    public boolean isAuthority() { return false; }

    @Override
    public UserCommand gatherInput(double delta) {
        return new UserCommand();
    }

    /** The latest raw authoritative sample — authority handback seeds the live body's velocities from it. */
    public RigidSnapshotInterpolator.Sample latestSample() { return interpolator.latestSample(); }

    public float   getLastSteerAngle() { return lastSteerAngle; }
    public float   getLastThrottle()   { return lastThrottle; }
    public boolean getLastHandbrake()  { return lastHandbrake; }
    public boolean getLastBrake()      { return lastBrake; }
    public boolean getLastSlipping()   { return lastSlipping; }
    public int     getLastFlatMask()   { return lastFlatMask; }
    public int     getLastFireSeq()    { return lastFireSeq; }

    /**
     * Push a freshly-decoded vehicle snapshot into the interpolation buffer and apply its
     * discrete fields (gated on forward progress — an unreliable channel can reorder).
     *
     * <p>{@code applyHealth} mirrors NetworkController.receiveSnapshot: false when the HOST
     * applies a driving client's upstream report (the host owns vehicle health), true when a
     * client applies the host's authoritative downstream batch. applyReplicatedHealth never
     * emits {@code died}, so a puppet can never self-destruct from a snapshot — destruction
     * arrives only via the host's reliable wreck/despawn events.
     */
    public void receiveSnapshot(DecodedVehicleSnapshot snap, boolean applyHealth) {
        Vector3 pos = snap.position();
        Quaternion q = snap.orientation();
        Vector3 lin = snap.linearVelocity();
        Vector3 ang = snap.angularVelocity();
        long senderMs = senderClock.unwrap(snap.senderTimeMs());
        interpolator.addSample(senderMs / 1000.0,
                new Vec3(pos.getX(), pos.getY(), pos.getZ()),
                new Quat(q.getX(), q.getY(), q.getZ(), q.getW()),
                new Vec3(lin.getX(), lin.getY(), lin.getZ()),
                new Vec3(ang.getX(), ang.getY(), ang.getZ()));

        if (senderMs > latestDiscreteTimeMs) {
            latestDiscreteTimeMs = senderMs;
            applyDiscreteState(snap, applyHealth);
        }
    }

    private void applyDiscreteState(DecodedVehicleSnapshot snap, boolean applyHealth) {
        lastSteerAngle = snap.steerAngle();
        lastThrottle   = snap.throttle();
        lastHandbrake  = snap.handbrake();
        lastBrake      = snap.brake();
        lastSlipping   = snap.slipping();
        lastFlatMask   = snap.flatMask();

        if (!(getParent() instanceof Vehicle vehicle)) return;

        // Flat tires mirror the authority (visual squash + sag on the frozen puppet);
        // rides every snapshot, so late-join and drop-heal come for free.
        vehicle.applyReplicatedFlatMask(snap.flatMask());

        if (applyHealth) {
            Node healthNode = vehicle.getNodeOrNull(new godot.core.NodePath("Health"));
            if (healthNode instanceof com.openworld.character.Health health) {
                health.applyReplicatedHealth(snap.health());
            }
        }

        Node weaponNode = vehicle.getNodeOrNull(new godot.core.NodePath("WeaponController"));
        if (weaponNode instanceof WeaponController wc) {
            if (haveFireSeq && snap.fireSeq() != lastFireSeq) wc.playRemoteFireCue();
            wc.setReplicatedFireSeq(snap.fireSeq());
        }
        lastFireSeq = snap.fireSeq();
        haveFireSeq = true;
    }

    /** Advances the interpolation clock and places the frozen body kinematically every rendered frame. */
    @Register
    @Override
    public void _process(double delta) {
        RigidSnapshotInterpolator.Output out = interpolator.advance(delta);
        if (out == null || !(getParent() instanceof Vehicle vehicle)) return;

        Vec3 p = out.position();
        Quat q = out.orientation();
        vehicle.setGlobalPosition(new Vector3((float) p.x(), (float) p.y(), (float) p.z()));
        vehicle.setGlobalBasis(new Basis(new Quaternion(
                (float) q.x(), (float) q.y(), (float) q.z(), (float) q.w())));

        // Wheel-appearance replay from replicated state: actual steer angle, spin from the
        // replicated speed, live suspension travel, and the authority's skid condition
        // (handbrake or drift-slip) driving the same skid marks.
        Vec3 v = out.linearVelocity();
        Vector3 linVel = new Vector3((float) v.x(), (float) v.y(), (float) v.z());
        float forwardSpeed = (float) vehicle.getGlobalBasis().getZ().times(-1).dot(linVel);
        boolean skidding = lastHandbrake || lastSlipping;
        for (VehicleWheel w : vehicle.getWheels()) {
            w.applyPuppetVisuals((float) delta, lastSteerAngle, forwardSpeed, skidding);
        }
    }
}
