package com.openworld.character;

import com.openworld.weapon.WeaponController;
import com.openworld.weapon.WeaponItem;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Skeleton3D;
import godot.api.SkeletonModifier3D;
import godot.api.Camera3D;
import godot.api.Node3D;
import godot.core.Basis;
import godot.core.Quaternion;
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

    /** The cover lift (PLAN.md 1d): how high the arm may raise the gun over low cover (m), and how fast it moves
     *  there (m/s). 0 max = never lift (the control). The TARGET comes from WeaponController every few frames. */
    @Export public float maxLift = 0.30f;
    @Export public float liftSpeed = 1.6f;
    public float getMaxLift() { return maxLift; }
    public void setMaxLift(float v) { this.maxLift = v; }
    public float getLiftSpeed() { return liftSpeed; }
    public void setLiftSpeed(float v) { this.liftSpeed = v; }
    private double lift, liftTarget;

    /** The lift to move toward (m, clamped to {@link #maxLift}). */
    public void setLiftTarget(double metres) { liftTarget = Math.max(0.0, Math.min(maxLift, metres)); }
    /** The lift the arm carries right now (m) -- for probes and for the next search's start. */
    @Register public double currentLift() { return lift; }

    /** First-person AIM DOWN SIGHTS (PLAN.md 0.43): how fast the gun comes up to the eye line (weight per second, so
     *  1/adsSpeed s to raise), how far its highest point stays UNDER the camera's centre ray (m -- "the gun must not
     *  block the crosshair", 2026-10-07), and the nearest its muzzle may come to the eye (m). 0 speed = never (the
     *  control). The TARGET comes from WeaponController every frame. */
    @Export public float adsSpeed = 7.0f;
    @Export public float adsMargin = 0.012f;
    @Export public float adsMinDepth = 0.30f;
    public float getAdsSpeed() { return adsSpeed; }
    public void setAdsSpeed(float v) { this.adsSpeed = v; }
    public float getAdsMargin() { return adsMargin; }
    public void setAdsMargin(float v) { this.adsMargin = v; }
    public float getAdsMinDepth() { return adsMinDepth; }
    public void setAdsMinDepth(float v) { this.adsMinDepth = v; }
    private double ads, adsTarget;

    /** Raise (true) or lower the gun to the eye line. */
    public void setAdsTarget(boolean on) { adsTarget = on && adsSpeed > 0.0f ? 1.0 : 0.0; }
    /** How far up the sights the gun is right now (0 = the clip's hold, 1 = on the eye line) -- for probes. */
    @Register public double currentAds() { return ads; }

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
        if (dt > 0.0 && lift != liftTarget) {
            double stepM = liftSpeed * dt;
            lift = Math.abs(liftTarget - lift) <= stepM ? liftTarget : lift + Math.signum(liftTarget - lift) * stepM;
        }
        if (dt > 0.0 && ads != adsTarget) {
            double stepA = Math.max(adsSpeed, 1.0f) * dt;
            ads = Math.abs(adsTarget - ads) <= stepA ? adsTarget : ads + Math.signum(adsTarget - ads) * stepA;
        }
        if (back == 0.0 && pitch == 0.0 && lift == 0.0 && ads == 0.0) return;   // at rest: the arm is the clip's/the IK's

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

        Transform3D hand = skel.getBoneGlobalPose(ie);
        if (ads > 0.0) {
            Transform3D[] raised = aimDownSights(skel, held, gun, hand);
            if (raised != null) { gun = raised[0]; hand = raised[1]; }
        }

        Basis gunBasis = gun.getBasis().orthonormalized();
        Vector3 lateral = gunBasis.getColumn(0);
        Vector3 boreBack = gunBasis.getColumn(2);
        Basis rise = new Basis(lateral, Math.toRadians(pitch));

        Vector3 pivot = skel.getBoneGlobalPose(iu).getOrigin();
        Vector3 target = pivot.plus(rise.times(hand.getOrigin().minus(pivot))).plus(boreBack.times((float) back));
        // The cover lift: straight up in the WORLD (the skeleton's frame may be turned), and then the gun re-pointed
        // at the aim target from its new height -- "raise against the aim target" -- so the bore still converges on
        // the crosshair instead of shooting a parallel line over it.
        Basis aimFix = null;
        if (lift > 0.0) {
            Basis toSkel = skel.getGlobalTransform().getBasis().inverse();
            Vector3 upS = toSkel.times(new Vector3(0, 1, 0)).normalized();
            Vector3 liftV = upS.times((float) lift);
            target = target.plus(liftV);
            godot.api.Node body = weaponController != null ? weaponController.getParent() : null;
            if (body instanceof Character c) {
                Vector3 aimS = skel.getGlobalTransform().affineInverse().times(c.getAimTargetPosition());
                Vector3 from = aimS.minus(gun.getOrigin());
                Vector3 to = aimS.minus(gun.getOrigin().plus(liftV));
                if (from.length() > 0.5 && to.length() > 0.5) {
                    Vector3 axis = from.cross(to);
                    double ang = from.angleTo(to);
                    if (axis.length() > 1e-6 && ang > 1e-5) aimFix = new Basis(axis.normalized(), ang);
                }
            }
        }
        Vector3 solved = TwoBoneIK.solve(skel, iu, il, ie, target, 1.0f);
        if (solved == null) return;
        // The gun turns WITH the hand: TwoBoneIK moves the hand by swinging its parents, which leaves
        // the hand's own rotation to them, so the kick's rotation is stated here explicitly.
        Basis turn = aimFix != null ? aimFix.times(rise) : rise;
        skel.setBoneGlobalPose(ie, new Transform3D(turn.times(hand.getBasis()), solved));
    }

    /**
     * First-person aim down sights: the gun turned so its bore is PARALLEL to the camera's centre ray and moved
     * (sideways and up, at the depth the clip holds it) so that ray passes just over its highest point -- the front
     * sight sits under the crosshair, never on it. In FPS the round already leaves the eye (FirearmItem
     * .eyeTraceInFirstPerson), so this is the picture, not the ballistics. Blended by {@link #ads}; the arm follows
     * through the same TwoBoneIK solve as the kick, and the support hand follows the gun as it always does.
     * Returns {gun, hand} in skeleton space, or null when there is no camera / muzzle to line up with.
     */
    private Transform3D[] aimDownSights(Skeleton3D skel, WeaponItem held, Transform3D gun, Transform3D hand) {
        if (!(held instanceof com.openworld.weapon.FirearmItem f)) return null;
        godot.api.Node body = weaponController != null ? weaponController.getParent() : null;
        Camera3D cam = body instanceof Character c ? c.activeCamera : null;
        Node3D muzzleNode = f.muzzleMarker();
        if (cam == null || muzzleNode == null || !cam.isInsideTree()) return null;
        Transform3D camS = skel.getGlobalTransform().affineInverse().times(cam.getGlobalTransform());
        Transform3D muz = HeldWeaponPose.markerInSkeleton(gun, held, muzzleNode);
        Basis camB = camS.getBasis().orthonormalized();
        // the muzzle marker's frame IS the bore's: -Z out of the barrel, +Y the top of the gun
        Quaternion full = camB.times(muz.getBasis().orthonormalized().inverse()).getRotationQuaternion();
        Basis turnFull = new Basis(full);
        Vector3 go = gun.getOrigin();
        Vector3 mzTurned = go.plus(turnFull.times(muz.getOrigin().minus(go)));
        Vector3 mc = camS.affineInverse().times(mzTurned);
        double depth = Math.max(adsMinDepth, -mc.getZ());
        Vector3 want = new Vector3(0.0, -(f.sightTopAboveBore() + adsMargin), -depth);
        Vector3 shift = camB.times(want.minus(mc)).times((float) ads);
        Basis turn = new Basis(new Quaternion().slerp(full, (float) ads));
        Transform3D g2 = new Transform3D(turn.times(gun.getBasis()), go.plus(shift));
        Transform3D h2 = new Transform3D(turn.times(hand.getBasis()),
                go.plus(turn.times(hand.getOrigin().minus(go))).plus(shift));
        return new Transform3D[] {g2, h2};
    }

    @Register
    @Override
    public void _exitTree() {
        weaponController = null;
        controllerResolved = false;
        back = 0.0; backVel = 0.0; pitch = 0.0; pitchVel = 0.0;
        lift = 0.0; liftTarget = 0.0;
        ads = 0.0; adsTarget = 0.0;
    }
}
