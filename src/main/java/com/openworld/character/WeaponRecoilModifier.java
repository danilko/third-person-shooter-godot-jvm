package com.openworld.character;

import com.openworld.weapon.WeaponController;
import com.openworld.weapon.WeaponItem;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Skeleton3D;
import godot.api.SkeletonModifier3D;
import godot.core.Basis;
import godot.core.Transform3D;
import godot.core.Vector3;

/**
 * The VISIBLE weapon kick (PLAN.md A3): a spring on the firing arm that pitches the muzzle up and
 * pushes the gun back on every shot, and settles.
 *
 * <h2>Why a spring and not a clip</h2>
 *
 * Recoil has three layers, each with one owner, and only the middle one was missing:
 * <ul>
 *   <li><b>aim recoil</b> — the camera kick and the spread bloom. Code, and it already exists
 *       ({@code Character.applyRecoil} → {@code ControlRotation.recoilPitch/Yaw},
 *       {@code FirearmItem}'s bloom). Owner-side only, correctly not replicated.</li>
 *   <li><b>the weapon kick</b> — THIS. A per-shot animation cannot do it: full auto at any fire rate
 *       has to STACK and settle, and a clip restarted every 0.1 s plays its first frames forever.
 *       A spring takes any number of impulses at any spacing and always comes back to rest.</li>
 *   <li><b>large discrete motion</b> — a pump, a bolt, a launcher rocking the shoulder. Animation:
 *       the weapon's own {@code AnimationPlayer} ({@code WeaponItem.fireAnimation}, W13).</li>
 * </ul>
 *
 * <p>IK is not a recoil source; it is what keeps the hands on the gun while the kick moves it. This
 * modifier runs AFTER {@link StockMountIKModifier} (which decides where the gun sits) and BEFORE
 * {@link SupportHandIKModifier} (which puts the off hand on the gun wherever it ends up), so the
 * support hand follows the kick for free -- both read the weapon through {@link HeldWeaponPose},
 * which composes it onto the firing hand's pose AS THIS PASS SEES IT.
 *
 * <h2>The motion</h2>
 *
 * Two scalar springs -- push-back (m) and muzzle pitch (deg) -- both critically damped by default.
 * A shot is a STEP on the offset, because a shot IS instantaneous; the spring is the return. The
 * firing hand is then rotated about the SHOULDER JOINT by the pitch (a shouldered rifle pivots at the
 * butt pad, which is a few centimetres from that joint) and translated back along the bore, and
 * {@link TwoBoneIK} swings the arm to follow. The hand keeps the kick's rotation, so the gun turns
 * with it rather than sliding through the grip.
 *
 * <p><b>Pitch only, deliberately, with no yaw term.</b> The horizontal half of recoil belongs to the
 * aim ({@code FirearmItem.applyRecoil} already randomises a yaw kick on the camera). A yaw kick HERE
 * would turn the gun off the aim line in the one axis {@code WeaponItem.pointsAtAim} gates firing on
 * (W21, yaw within 15 deg), so a burst would start eating its own trigger presses.
 *
 * <h2>Where the numbers live</h2>
 *
 * Per weapon, on the weapon ({@code WeaponItem.kickBack}/{@code kickPitch}/{@code kickSpring}/
 * {@code kickDamping}) -- a 12-gauge does not kick like a pistol, and the spring rate is part of how
 * heavy the gun feels. A weapon that authors none does not kick, which is the right answer for a
 * fist, a knife and a thrown grenade. {@code WeaponController} delivers the impulse at the two sites
 * W13 already uses for the weapon's own moving parts: {@code onWeaponFire} on the owner and
 * {@code playRemoteFireCue} on a puppet -- so a remote peer sees the kick with no new message.
 */
@Script(className = "WeaponRecoilModifier")
public class WeaponRecoilModifier extends SkeletonModifier3D {

    /** Shoulder end of the firing arm -- also the pivot the pitch turns the gun about. */
    @Export public String upperBone = "upperarm_r";
    /** Elbow. */
    @Export public String lowerBone = "lowerarm_r";
    /** The hand the weapon hangs from. */
    @Export public String endBone = "hand_r";

    /** Scales every kick this body takes (0 disables it -- the probe's control). */
    @Export public float weight = 1.0f;

    /** Ceiling on the accumulated push-back (m), so a long burst cannot fold the arm into the chest. */
    @Export public float maxBack = 0.10f;

    /** Ceiling on the accumulated muzzle rise (deg). */
    @Export public float maxPitch = 14.0f;

    /** Below this the spring is at rest and the whole solve is skipped (m / deg). */
    @Export public float restEpsilon = 0.0005f;

    public String getUpperBone() { return upperBone; }
    public void setUpperBone(String v) { this.upperBone = v; }
    public String getLowerBone() { return lowerBone; }
    public void setLowerBone(String v) { this.lowerBone = v; }
    public String getEndBone() { return endBone; }
    public void setEndBone(String v) { this.endBone = v; }
    public float getWeight() { return weight; }
    public void setWeight(float v) { this.weight = v; }
    public float getMaxBack() { return maxBack; }
    public void setMaxBack(float v) { this.maxBack = v; }
    public float getMaxPitch() { return maxPitch; }
    public void setMaxPitch(float v) { this.maxPitch = v; }
    public float getRestEpsilon() { return restEpsilon; }
    public void setRestEpsilon(float v) { this.restEpsilon = v; }

    private WeaponController weaponController;
    private boolean controllerResolved = false;

    // Spring state: offset and its velocity, per axis.
    private double back, backVel, pitch, pitchVel;
    // The spring the last kick asked for (a heavier gun settles slower).
    private double omega = 22.0, zeta = 1.0;
    private int kicks = 0;

    /** Current push-back (m) -- for probes. */
    @Register
    public double currentBack() { return back; }

    /** Current muzzle rise (deg) -- for probes. */
    @Register
    public double currentPitch() { return pitch; }

    /** Kicks taken since the body spawned -- for probes. */
    @Register
    public int kickCount() { return kicks; }

    /**
     * One shot's impulse. {@code spring} is the spring's angular frequency (1/s, so the settle is
     * roughly 4/spring) and {@code damping} its ratio (1 = critically damped, the default: back to
     * rest with no bounce). Called on the owner from {@code WeaponController.onWeaponFire} and on a
     * puppet from {@code playRemoteFireCue}.
     */
    @Register
    public void kick(double backMetres, double pitchDegrees, double spring, double damping) {
        if (weight <= 0.0f) return;
        if (spring > 0.0) omega = spring;
        if (damping > 0.0) zeta = damping;
        back = clamp(back + backMetres * weight, maxBack);
        pitch = clamp(pitch + pitchDegrees * weight, maxPitch);
        kicks++;
    }

    private static double clamp(double v, double limit) {
        return Math.max(-limit, Math.min(limit, v));
    }

    @Override
    public void _processModification() {
        Skeleton3D skel = getSkeleton();
        if (skel == null) return;

        // Settle first, so a weapon put away mid-recoil still comes back to rest.
        double dt = Math.min(0.1, getProcessDeltaTime());
        if (dt > 0.0 && (back != 0.0 || pitch != 0.0 || backVel != 0.0 || pitchVel != 0.0)) {
            // Sub-stepped: semi-implicit Euler goes unstable once omega*dt approaches 2, and a frame
            // hitch (or a --fixed-fps run at a low rate) can get there on a stiff weapon spring.
            int steps = Math.max(1, Math.min(8, (int) Math.ceil(dt * omega / 0.3)));
            double h = dt / steps;
            for (int i = 0; i < steps; i++) {
                backVel += (-omega * omega * back - 2.0 * zeta * omega * backVel) * h;
                back += backVel * h;
                pitchVel += (-omega * omega * pitch - 2.0 * zeta * omega * pitchVel) * h;
                pitch += pitchVel * h;
            }
            if (Math.abs(back) < restEpsilon && Math.abs(backVel) < restEpsilon) { back = 0.0; backVel = 0.0; }
            if (Math.abs(pitch) < restEpsilon && Math.abs(pitchVel) < restEpsilon) { pitch = 0.0; pitchVel = 0.0; }
        }
        if (back == 0.0 && pitch == 0.0) return;          // at rest: the arm is the clip's/the IK's

        if (!controllerResolved) {
            controllerResolved = true;
            weaponController = HeldWeaponPose.findController(this);
        }
        WeaponItem held = weaponController == null ? null : weaponController.getCurrentWeaponItem();
        // The gun's OWN frame carries the kick: +X is its lateral axis and +Z points back out of the
        // muzzle (W19's model convention), so the motion stays in the gun's plane whatever roll the
        // pose gave it. No weapon in hand (or one holstered mid-switch) -- nothing to kick.
        Transform3D gun = HeldWeaponPose.weaponInSkeleton(skel, held, endBone);
        if (gun == null) return;

        int iu = skel.findBone(upperBone);
        int il = skel.findBone(lowerBone);
        int ie = skel.findBone(endBone);
        if (iu < 0 || il < 0 || ie < 0) return;

        Basis gunBasis = gun.getBasis().orthonormalized();
        Vector3 lateral = gunBasis.getColumn(0);
        Vector3 boreBack = gunBasis.getColumn(2);
        Basis rise = new Basis(lateral, Math.toRadians(pitch));

        Transform3D hand = skel.getBoneGlobalPose(ie);
        Vector3 pivot = skel.getBoneGlobalPose(iu).getOrigin();
        Vector3 target = pivot.plus(rise.times(hand.getOrigin().minus(pivot))).plus(boreBack.times((float) back));
        Vector3 solved = TwoBoneIK.solve(skel, iu, il, ie, target, 1.0f);
        if (solved == null) return;
        // The gun turns WITH the hand: TwoBoneIK moves the hand by swinging its parents, which leaves
        // the hand's own rotation to them, so the kick's rotation is stated here explicitly.
        skel.setBoneGlobalPose(ie, new Transform3D(rise.times(hand.getBasis()), solved));
    }

    @Register
    @Override
    public void _exitTree() {
        weaponController = null;
        controllerResolved = false;
        back = 0.0; backVel = 0.0; pitch = 0.0; pitchVel = 0.0;
    }
}
