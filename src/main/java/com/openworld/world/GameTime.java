package com.openworld.world;

import godot.api.Node;
import godot.api.SceneTree;
import godot.global.GD;

import java.util.Map;

/**
 * The game's time of day -- ONE owner, so the HUD clock, the station boards and the screens in the trains always say
 * the same time (user, 2026-10-02: "a game time on the HUD, so it aligns with the trains and other in-game events").
 * It is Sky3D's {@code TimeOfDay} ({@code current_time} hours, at {@code minutes_per_day} real minutes a day: 48, so a
 * real second is 30 game seconds); a scene with no TimeOfDay falls back to the system's local time.
 */
public final class GameTime {

    private GameTime() { }

    private static Node timeOfDay;
    private static long scene = -1;

    private static Node find(SceneTree tree) {
        Node s = tree != null ? tree.getCurrentScene() : null;
        long id = s != null ? s.getInstanceId() : 0;
        if (id != scene || (timeOfDay != null && !GD.isInstanceValid(timeOfDay))) {
            scene = id;
            timeOfDay = s != null ? s.findChild("TimeOfDay", true, false) : null;
        }
        return timeOfDay;
    }

    /** Hours (0-24) now. */
    public static double hours(SceneTree tree) {
        Node tod = find(tree);
        if (tod != null) return num(tod.get("current_time"), 12.0);
        Map<?, ?> d = godot.api.Time.INSTANCE.getTimeDictFromSystem(false);
        return num(d.get("hour"), 12) + num(d.get("minute"), 0) / 60.0 + num(d.get("second"), 0) / 3600.0;
    }

    /**
     * A client: take the host's time of day when this peer's is more than a game minute off (the two run at the same
     * rate between syncs). No-op in a scene with no TimeOfDay.
     */
    public static void syncTo(SceneTree tree, double hostHours) {
        Node tod = find(tree);
        if (tod == null || !Double.isFinite(hostHours)) return;
        double mine = num(tod.get("current_time"), hostHours);
        double diff = Math.abs(mine - hostHours) % 24.0;
        diff = Math.min(diff, 24.0 - diff);
        if (diff > 1.0 / 60.0) tod.set("current_time", ((hostHours % 24.0) + 24.0) % 24.0);
    }

    /** Game hours per REAL second (1/3600 in real time; 24 / (48 * 60) at Sky3D's 48 minutes a day). */
    public static double hoursPerSecond(SceneTree tree) {
        Node tod = find(tree);
        if (tod == null) return 1.0 / 3600.0;
        return 24.0 / (Math.max(0.1, num(tod.get("minutes_per_day"), 48.0)) * 60.0);
    }

    /** The time of day {@code seconds} real seconds from now (hours, 0-24). */
    public static double hoursIn(SceneTree tree, double seconds) {
        double h = hours(tree) + seconds * hoursPerSecond(tree);
        return ((h % 24.0) + 24.0) % 24.0;
    }

    /** "HH:MM". */
    public static String format(double hours) {
        int m = (int) Math.floor(hours * 60.0 + 1e-6);
        return String.format("%02d:%02d", (m / 60) % 24, m % 60);
    }

    private static double num(Object o, double d) { return o instanceof Number n ? n.doubleValue() : d; }
}
