package com.openworld.game;

import com.openworld.util.DataReader;

import java.util.ArrayList;
import java.util.List;

/**
 * GTA V-STYLE RESTRICTED AREAS (PLAN.md P1e step 3, user 2026-10-15): the military reserves. A player inside a box is
 * WARNED first; still inside after {@code warn_seconds}, or more than {@code inner} metres in from every edge at any
 * time, they commit the crime {@code trespass} (crimes.json: at least 4 stars), once per visit. Region data in
 * {@code game/forces.json} {@code restricted}, not derived.
 *
 * <p>Engine-free ({@code ForcePoolsTest}): the host's dispatch reports the crime ({@link EnforcementDispatch}), every
 * peer's own area warning reads {@link #at} for its local player.
 */
public final class RestrictedAreas {
    private RestrictedAreas() {}

    /** One restricted box (world x0, z0, x1, z1). */
    public record Area(String name, double x0, double z0, double x1, double z1, double inner, double warnSeconds) {
        public boolean holds(double x, double z) { return x >= x0 && x <= x1 && z >= z0 && z <= z1; }

        /** How far in from the nearest edge (m); negative outside. */
        public double depth(double x, double z) { return Math.min(Math.min(x - x0, x1 - x), Math.min(z - z0, z1 - z)); }
    }

    /** The area holding (x, z), or null. */
    public static Area at(List<Area> areas, double x, double z) {
        for (Area a : areas) if (a.holds(x, z)) return a;
        return null;
    }

    /** What a visit has come to: still a warning, or the trespass. {@code inside} = seconds inside so far. */
    public static boolean trespass(Area a, double x, double z, double inside) {
        return a != null && a.holds(x, z) && (inside >= a.warnSeconds() || a.depth(x, z) > a.inner());
    }

    /** The areas in this world's data (empty when there are none). */
    public static List<Area> all() {
        com.openworld.game.data.Tables.Forces f = com.openworld.game.data.Tables.FORCES.get();
        return f == null ? List.of() : f.restricted();
    }

    public static List<Area> read(DataReader d) {
        List<Area> out = new ArrayList<>();
        if (d == null) return out;
        for (DataReader r : d.items("restricted")) {
            double[] b = r.nums("box");
            String name = r.reqStr("name", null);
            if (name == null || b == null || b.length != 4) continue;
            out.add(new Area(name, Math.min(b[0], b[2]), Math.min(b[1], b[3]), Math.max(b[0], b[2]), Math.max(b[1], b[3]),
                    r.num("inner", 30.0), r.num("warn_seconds", 8.0)));
        }
        return out;
    }
}
