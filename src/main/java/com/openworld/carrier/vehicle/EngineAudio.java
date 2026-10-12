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
 * A running car's engine sound (PLAN.md P2b / F11): looping takes of one engine at idle and at three speeds
 * ({@code assets/audio/engine/}, cut and re-timed to a steady pitch by {@code tools/audio/build_engine.py}), the two
 * nearest the engine's speed cross-faded and each PITCHED to it. Owned by its {@link Vehicle}, which calls
 * {@link #update} every frame and {@link #release} when it leaves the tree.
 *
 * <p><b>The cost rule</b> (the one that removed footsteps: a sound per body per tick is paid whether or not anyone
 * hears it). A car has an engine VOICE only while it is running (someone in it, or a brain driving it), within
 * {@link #HEAR_DISTANCE} of the camera, and one of at most {@link #MAX_VOICED} cars -- the local player's own car is
 * never refused. Everything else has no player node at all, and asks again five times a second. A voiced car plays
 * one loop, two while it is between bands. {@code OW_ENGINE_AUDIO=0} (or the console's {@code engine 0}) turns the
 * whole thing off; {@code OW_ENGINE_AUDIO=all} drops the distance and the count, which is the probe's control.
 *
 * <p>There is no gearbox in {@link Vehicle}, so the engine speed is read off the road speed through five made-up
 * gears: it climbs through each, drops at the change, and is held up by the throttle when the car is standing.
 */
final class EngineAudio {

    /** Firing frequency (Hz) of the idle / low / mid / high loops. build_engine.py --check compares this table. */
    static final float[] BAND_HZ = {31.3f, 95.0f, 150.0f, 220.0f};
    private static final Sound[] BAND = {Sound.ENGINE_IDLE, Sound.ENGINE_LOW, Sound.ENGINE_MID, Sound.ENGINE_HIGH};
    /** Band k hands over to band k + 1 between these two firing frequencies. Idle hands over early: the low loop
     *  slowed to an idle's pitch is not an engine any more, so from 62 Hz to its own 95 it plays alone. */
    private static final float[] FADE_FROM = {31.3f, 95.0f, 150.0f};
    private static final float[] FADE_TO = {62.0f, 150.0f, 220.0f};
    private static final float PITCH_MIN = 0.65f, PITCH_MAX = 1.6f;
    /** Firing frequency at the red line (a four at ~6 900 rpm). */
    private static final float REDLINE_HZ = 230.0f;
    /** Top of each made-up gear, as a share of the car's top speed. */
    private static final double[] GEAR_TOP = {0.20, 0.38, 0.58, 0.80, 1.25};

    static final double HEAR_DISTANCE = 45.0;
    /** A voiced car keeps its voice out to here, so one at the edge does not flicker. Also the players' max distance. */
    static final double RELEASE_DISTANCE = 55.0;
    static final int MAX_VOICED = 6;
    private static final double ASK_EVERY = 0.2;
    private static final float UNIT_SIZE = 5.0f;
    private static final float LEVEL_DB = -9.0f, COAST_DB = -7.0f, IDLE_DB = -3.0f;
    private static final float SILENT_DB = -60.0f;

    private static final String ENV = System.getenv("OW_ENGINE_AUDIO");
    static boolean enabled = !"0".equals(ENV);
    static boolean nearRule = !"all".equals(ENV);
    private static int voicedCars;

    /** Cars with an engine voice at this instant (probes; the console's {@code engine}). */
    static int voicedCarsNow() { return voicedCars; }

    private final Vehicle car;
    private final AudioStreamPlayer3D[] player = new AudioStreamPlayer3D[2];
    private final int[] playerBand = {-1, -1};
    private boolean voiced, wasRunning;
    private double askIn = Math.random() * ASK_EVERY;
    private Vector3 lastPos;
    private double speed, lastSpeed, accel, rpm, load, startHold;

    EngineAudio(Vehicle car) { this.car = car; }

    /** Players of this car sounding now (0, 1, or 2 between bands). */
    int playingNow() {
        int n = 0;
        for (AudioStreamPlayer3D p : player) if (p != null && GD.isInstanceValid(p) && p.isPlaying()) n++;
        return n;
    }

    /** Engine speed 0 (idle) .. 1 (red line), as last computed for a voiced car. */
    double rpmNow() { return rpm; }

    /**
     * Once a frame. {@code running}: someone is in the car or a brain drives it, and it is not a wreck.
     * {@code playerDriven}: a player is at the wheel (the starter is heard when one gets in). {@code localInside}: the
     * local player is aboard. {@code throttle} 0..1 where this peer knows it (0 on a puppet: the load is then read off
     * the acceleration).
     */
    void update(double delta, boolean running, boolean playerDriven, boolean localInside, double throttle, double topSpeed) {
        askIn -= delta;
        if (askIn <= 0.0) {
            askIn = ASK_EVERY;
            ask(running, playerDriven, localInside);
        }
        if (!voiced) return;
        Vector3 pos = car.getGlobalPosition();
        if (lastPos != null && delta > 1e-5) speed += (pos.distanceTo(lastPos) / delta - speed) * Math.min(1.0, delta * 10.0);
        lastPos = pos;
        accel += ((speed - lastSpeed) / Math.max(1e-5, delta) - accel) * Math.min(1.0, delta * 4.0);
        lastSpeed = speed;
        double wantLoad = Math.max(Math.min(1.0, Math.abs(throttle)), Math.max(0.0, Math.min(1.0, accel / 2.5)));
        load += (wantLoad - load) * Math.min(1.0, delta * 6.0);
        rpm += (targetRpm(speed / Math.max(1.0, topSpeed), wantLoad) - rpm) * Math.min(1.0, delta * 5.0);
        if (startHold > 0.0) startHold -= delta;
        float hz = BAND_HZ[0] + (float) rpm * (REDLINE_HZ - BAND_HZ[0]);
        float level = LEVEL_DB + COAST_DB * (float) (1.0 - load)
                + (startHold > 0.5 ? SILENT_DB : startHold > 0.0 ? (float) (-30.0 * startHold / 0.5) : 0f);
        int k = 0;
        while (k < FADE_FROM.length - 1 && hz >= FADE_FROM[k + 1]) k++;
        float w = Math.max(0f, Math.min(1f, (hz - FADE_FROM[k]) / (FADE_TO[k] - FADE_FROM[k])));
        sound(k, 1f - w, hz, level, k + 1);
        sound(k + 1, w, hz, level, k);
    }

    /** Engine speed 0..1 for a road speed (as a share of top speed) and a throttle: see the class comment. */
    static double targetRpm(double speedShare, double throttle) {
        double lo = 0.0;
        for (int g = 0; g < GEAR_TOP.length; g++) {
            if (speedShare <= GEAR_TOP[g] || g == GEAR_TOP.length - 1) {
                double f = Math.max(0.0, Math.min(1.0, (speedShare - lo) / (GEAR_TOP[g] - lo)));
                double bottom = g == 0 ? 0.0 : 0.42;
                return Math.max(bottom + (0.95 - bottom) * f, g == 0 ? throttle * 0.3 : 0.0);
            }
            lo = GEAR_TOP[g];
        }
        return 0.0;
    }

    /** Band {@code band} at {@code weight} (equal-power), on the player that has it or on the one not playing
     *  {@code other}. A band at no weight is stopped, not played silently. */
    private void sound(int band, float weight, float hz, float levelDb, int other) {
        int i = playerBand[0] == band ? 0 : playerBand[1] == band ? 1 : -1;
        if (weight < 0.02f) {
            if (i >= 0 && player[i] != null && player[i].isPlaying()) player[i].stop();
            return;
        }
        if (i < 0) {
            i = playerBand[0] == other ? 1 : 0;
            AudioStream st = Sounds.stream(BAND[band]);
            if (st == null) return;
            if (player[i] == null || !GD.isInstanceValid(player[i])) {
                AudioStreamPlayer3D p = new AudioStreamPlayer3D();
                p.setName(new StringName(i == 0 ? "EngineA" : "EngineB"));
                p.setUnitSize(UNIT_SIZE);
                p.setMaxDistance((float) RELEASE_DISTANCE);
                car.addChild(p);
                p.connect("tree_exiting", MethodCallable.createUnsafe(p, "stop"));   // CLAUDE.md audio rule
                player[i] = p;
            }
            player[i].stop();
            player[i].setStream(st);
            playerBand[i] = band;
        }
        AudioStreamPlayer3D p = player[i];
        p.setPitchScale(Math.max(PITCH_MIN, Math.min(PITCH_MAX, hz / BAND_HZ[band])));
        p.setVolumeDb(levelDb + (band == 0 ? IDLE_DB : 0f) + (float) (10.0 * Math.log10(weight)));
        if (!p.isPlaying()) p.play((float) (Math.random() * 0.5));
    }

    /** Should this car have a voice? Takes one or gives it back. */
    private void ask(boolean running, boolean playerDriven, boolean localInside) {
        boolean want = enabled && running;
        if (want && nearRule && !localInside) {
            Camera3D cam = car.getViewport() != null ? car.getViewport().getCamera3d() : null;
            double d = cam != null && GD.isInstanceValid(cam) ? cam.getGlobalPosition().distanceTo(car.getGlobalPosition()) : 0.0;
            want = d <= (voiced ? RELEASE_DISTANCE : HEAR_DISTANCE) && (voiced || voicedCars < MAX_VOICED);
        }
        if (want && !voiced) {
            voiced = true;
            voicedCars++;
            lastPos = null;
            speed = lastSpeed = accel = load = 0.0;
            rpm = 0.0;
            // a player getting into a standing car turns the key; traffic is born running
            if (playerDriven && !wasRunning && Sounds.stream(Sound.ENGINE_START) != null) {
                Sounds.play3D(car, Sound.ENGINE_START, car.getGlobalPosition(), UNIT_SIZE, 0f, LEVEL_DB + 3f);
                startHold = 1.9;
            }
        } else if (!want && voiced) {
            release();
        }
        wasRunning = running;
    }

    /** Gives the voice back and frees the players (the car stopped, went out of earshot, or is leaving the tree). */
    void release() {
        if (!voiced) return;
        voiced = false;
        voicedCars = Math.max(0, voicedCars - 1);
        startHold = 0.0;
        for (int i = 0; i < 2; i++) {
            if (player[i] != null && GD.isInstanceValid(player[i])) {
                player[i].stop();
                player[i].queueFree();
            }
            player[i] = null;
            playerBand[i] = -1;
        }
    }
}
