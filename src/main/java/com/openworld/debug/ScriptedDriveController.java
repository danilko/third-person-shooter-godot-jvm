package com.openworld.debug;

import com.openworld.control.Controller;
import com.openworld.control.UserCommand;
import godot.annotation.Script;

/**
 * Deterministic test-driver for the headless vehicle physics harness ({@link DriveTestHost}).
 * Replays a fixed throttle/steer script so stability regressions are measurable and
 * bisectable instead of "felt in the editor". Phases:
 *
 *   0–16 s    full throttle, straight            (launch + top-speed measurement)
 *   16–21 s   full throttle + full left steer    (steady max-speed turn — flip + radius case)
 *   21–25 s   slalom, ±full steer at 1 Hz        (transient weight-shift case)
 *   25–28 s   brake, straight                    (coast down to drift-entry speed)
 *   28–32 s   handbrake + full steer + throttle  (drift — a full circle ≈ 360° turnedDeg)
 *   32–35 s   brake, straight                    (stop)
 *   35–39 s   handbrake + full steer + throttle from standstill (burnout donut)
 *   39–44 s   full reverse input (gearbox: brakes the rolling car first, then backs up
 *             — maxKmh in this phase is the reverse ceiling)
 */
@Script(className = "ScriptedDriveController")
public class ScriptedDriveController extends Controller {

    private double t = 0.0;

    /** Current script phase name — the telemetry log keys off it. */
    public String phase() {
        if (t < 16.0) return "LAUNCH";
        if (t < 21.0) return "TURN";
        if (t < 25.0) return "SLALOM";
        if (t < 28.0) return "COAST";
        if (t < 32.0) return "HANDBRAKE";
        if (t < 35.0) return "BRAKE";
        if (t < 39.0) return "DONUT";
        return "REVERSE";
    }

    public boolean finished() { return t >= 44.0; }

    @Override
    public UserCommand gatherInput(double delta) {
        t += delta;
        UserCommand cmd = new UserCommand();
        switch (phase()) {
            case "LAUNCH"    -> cmd.motor = 1f;
            case "TURN"      -> { cmd.motor = 1f; cmd.steering = 1f; }
            case "SLALOM"    -> { cmd.motor = 1f; cmd.steering = (((int) (t)) % 2 == 0) ? 1f : -1f; }
            case "COAST"     -> cmd.brake = true;
            case "HANDBRAKE" -> { cmd.motor = 0.6f; cmd.steering = 1f; cmd.handbrake = true; }
            case "DONUT"     -> { cmd.motor = 1f;   cmd.steering = 1f; cmd.handbrake = true; }
            case "REVERSE"   -> cmd.motor = -1f;
            default          -> cmd.brake = true;
        }
        return cmd;
    }
}
