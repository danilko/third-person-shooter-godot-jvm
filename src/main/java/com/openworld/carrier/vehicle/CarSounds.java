package com.openworld.carrier.vehicle;

import com.openworld.audio.Sound;
import com.openworld.audio.Sounds;
import godot.api.AudioStream;
import godot.api.AudioStreamPlayer3D;
import godot.api.Camera3D;
import godot.core.MethodCallable;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

/**
 * A car's sounds other than the engine (PLAN.md F11): the HORN while it is held, the tyres SQUEALING while they slide,
 * and a CRASH when the car hits something hard. Owned by its {@link Vehicle} like {@link EngineAudio}, which it
 * follows on the cost rule: a looping player exists only while the car is making that sound and the camera is near
 * (the horn {@link #HORN_DISTANCE}, the squeal {@link #SKID_DISTANCE}, at most {@link #MAX_SKIDDING} cars squealing),
 * and is freed when it stops; nothing is built for a car that is silent.
 *
 * <p>The squeal is read off the car's MOTION (sideways speed, a locked brake, the handbrake at speed), so a puppet
 * squeals from the replicated velocity and brake / handbrake bits with no message of its own. The crash comes from
 * the scored crash of {@link VehicleDamageModel} (the simulating peer only: a crash a remote peer simulates is
 * silent here -- see docs/vehicles.md "Car sounds"). The horn is replicated (snapshot flag bit 7).
 */
final class CarSounds {

    static final double HORN_DISTANCE = 120.0;
    static final double SKID_DISTANCE = 60.0;
    static final double CRASH_DISTANCE = 80.0;
    static final int MAX_SKIDDING = 4;
    /** Below this change of velocity (m/s) a crash is the light one; VehicleDamageRules.MIN_IMPACT_DV is the floor. */
    static final double HEAVY_CRASH_DV = 8.0;
    private static final double CRASH_GAP = 0.15;          // s between two crash sounds of one car
    private static final float HORN_UNIT = 14f, SKID_UNIT = 8f, CRASH_UNIT = 10f;
    private static final float SKID_MIN_DB = -18f;
    /** A slide this hard is a full squeal: sideways m/s past SKID_SIDE_FROM. */
    private static final double SKID_SIDE_FROM = 1.5, SKID_SIDE_FULL = 6.0;
    /** How long a stopped squeal's player is kept, so a drift that dips for a moment does not rebuild it. */
    private static final double SKID_KEEP = 0.6;

    static boolean enabled = !"0".equals(System.getenv("OW_CAR_SOUNDS"));
    private static int skidding;

    private final Vehicle car;
    private AudioStreamPlayer3D horn, skid;
    private double skidIdle, crashGap;
    private float skidLevel;
    private int crashes;

    CarSounds(Vehicle car) { this.car = car; }

    /** Cars squealing at this instant (probes). */
    static int skiddingNow() { return skidding; }
    boolean hornPlaying() { return horn != null && GD.isInstanceValid(horn) && horn.isPlaying(); }
    boolean skidPlaying() { return skid != null && GD.isInstanceValid(skid) && skid.isPlaying(); }
    float skidLevelNow() { return skid != null ? skidLevel : 0f; }
    int crashesNow() { return crashes; }

    /** Once a frame. {@code hornOn}: held by the driver here, or by the snapshot on a puppet. */
    void update(double delta, boolean hornOn, boolean localInside) {
        crashGap = Math.max(0.0, crashGap - delta);
        if (!enabled) { release(); return; }
        double cam = localInside ? 0.0 : cameraDistance();
        // the horn
        boolean wantHorn = hornOn && cam <= HORN_DISTANCE;
        if (wantHorn && !hornPlaying()) {
            horn = start(horn, Sound.CAR_HORN, "Horn", HORN_UNIT, 0f);
        } else if (!wantHorn && horn != null) {
            horn = free(horn);
        }
        // the squeal
        double amount = slideAmount();
        boolean wantSkid = amount > 0.0 && cam <= SKID_DISTANCE && (skid != null || skidding < MAX_SKIDDING);
        if (wantSkid) {
            if (skid == null) {
                skid = start(null, Sound.CAR_SKID, "Skid", SKID_UNIT, SKID_MIN_DB);
                if (skid != null) skidding++;
            }
            skidIdle = 0.0;
            if (skid != null) {
                skidLevel = (float) (SKID_MIN_DB * (1.0 - amount));
                skid.setVolumeDb(skidLevel);
                skid.setPitchScale((float) (0.9 + 0.2 * amount));
                if (!skid.isPlaying()) skid.play((float) (Math.random() * 0.3));
            }
        } else if (skid != null) {
            if (skid.isPlaying()) skid.stop();
            skidIdle += delta;
            if (skidIdle > SKID_KEEP || cam > SKID_DISTANCE) stopSkid();
        }
    }

    /**
     * 0 = the tyres grip, 1 = a full squeal: a sideways slide (from the car's own motion), a locked brake or the
     * handbrake at speed. Airborne or slow: 0.
     */
    private double slideAmount() {
        Vector3 v = car.getLinearVelocity();
        double speed = Math.hypot(v.getX(), v.getZ());
        if (speed < 3.0 || Math.abs(v.getY()) > 4.0 || !car.isAlive()) return 0.0;
        double side = Math.abs(car.getGlobalBasis().getX().dot(v));
        double a = Math.max(0.0, Math.min(1.0, (side - SKID_SIDE_FROM) / (SKID_SIDE_FULL - SKID_SIDE_FROM)));
        if (car.handbrakeShownNow() && speed > 4.0) a = Math.max(a, 0.6);
        if (car.brakeShownNow() && speed > 6.0 && car.slipShownNow()) a = Math.max(a, 0.7);
        else if (car.brakeShownNow() && speed > 8.0) a = Math.max(a, 0.35);   // hard braking at speed: a short chirp
        return a;
    }

    /** A crash of {@code dv} m/s (VehicleDamageModel's scored crash) at {@code at}. */
    void crash(double dv, Vector3 at) {
        if (!enabled || dv < VehicleDamageRules.MIN_IMPACT_DV || crashGap > 0.0) return;
        if (cameraDistance() > CRASH_DISTANCE) return;
        crashGap = CRASH_GAP;
        crashes++;
        boolean heavy = dv >= HEAVY_CRASH_DV;
        float db = heavy ? (float) Math.min(4.0, (dv - HEAVY_CRASH_DV) * 0.4)
                : (float) (-8.0 + 8.0 * (dv - VehicleDamageRules.MIN_IMPACT_DV) / (HEAVY_CRASH_DV - VehicleDamageRules.MIN_IMPACT_DV));
        Sounds.play3D(car, heavy ? Sound.CAR_CRASH_HEAVY : Sound.CAR_CRASH_LIGHT, at, CRASH_UNIT, 0.08f, db);
    }

    private double cameraDistance() {
        Camera3D cam = car.getViewport() != null ? car.getViewport().getCamera3d() : null;
        return cam != null && GD.isInstanceValid(cam) ? cam.getGlobalPosition().distanceTo(car.getGlobalPosition()) : 0.0;
    }

    private AudioStreamPlayer3D start(AudioStreamPlayer3D have, Sound s, String name, float unit, float db) {
        AudioStream st = Sounds.stream(s);
        if (st == null) return have;
        AudioStreamPlayer3D p = have != null && GD.isInstanceValid(have) ? have : new AudioStreamPlayer3D();
        if (p != have) {
            p.setName(new StringName(name));
            p.setUnitSize(unit);
            car.addChild(p);
            p.connect("tree_exiting", MethodCallable.createUnsafe(p, "stop"));   // CLAUDE.md audio rule
        }
        p.setStream(st);
        p.setVolumeDb(db);
        p.play();
        return p;
    }

    private static AudioStreamPlayer3D free(AudioStreamPlayer3D p) {
        if (p != null && GD.isInstanceValid(p)) {
            p.stop();
            p.queueFree();
        }
        return null;
    }

    private void stopSkid() {
        if (skid != null) skidding = Math.max(0, skidding - 1);
        skid = free(skid);
        skidIdle = 0.0;
    }

    /** Frees every player (the car is leaving the tree, or the sounds were turned off). */
    void release() {
        horn = free(horn);
        stopSkid();
    }
}
