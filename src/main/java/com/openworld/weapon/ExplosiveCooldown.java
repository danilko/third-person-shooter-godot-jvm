package com.openworld.weapon;

import java.util.HashMap;
import java.util.Map;

/**
 * THE SHARED EXPLOSIVE COOLDOWN (PLAN.md P1e step 1, user 2026-10-15). Once any AI fires an explosive -- a launcher,
 * a grenade, an armoured vehicle's main gun -- no other AI explosive goes off within {@code area} metres for
 * {@code cooldown} seconds. Keyed by AREA, never by player: two players standing together must not draw double
 * rockets (the reviewer's correction). The players' own explosives are never gated.
 *
 * <p>Engine-free (the clock is passed in, {@code ExplosiveCooldownTest}). The area is a grid of {@code area}-sized
 * cells; a shot is refused while its own cell or any of the 8 round it is cooling, so two shooters either side of a
 * cell line cannot both fire. Process-wide static state (one world at a time); {@link #reset} clears it.
 */
public final class ExplosiveCooldown {
    private ExplosiveCooldown() {}

    /** Off = the control: every AI explosive fires as soon as its own weapon allows. */
    public static boolean enabled = true;

    private static double cooldown = -1, area = 80.0;
    private static final Map<Long, Double> until = new HashMap<>();
    private static int fired, refused;

    /** The data (item/ammo_supply.json {@code ai_ammo}), read once. */
    private static void config() {
        if (cooldown >= 0) return;
        com.openworld.game.data.Tables.AmmoSupplies t = com.openworld.game.data.Tables.AMMO_SUPPLY.get();
        com.openworld.game.data.Tables.AiAmmo a = t != null && t.ai() != null ? t.ai()
                : com.openworld.game.data.Tables.AiAmmo.DEFAULT;
        configure(a.explosiveCooldown(), a.explosiveArea());
    }

    /** Set the rules directly (tests; the data otherwise). */
    public static void configure(double cooldownSeconds, double areaMetres) {
        cooldown = Math.max(0, cooldownSeconds);
        area = Math.max(1.0, areaMetres);
    }

    private static long cell(long ix, long iz) { return (ix << 32) ^ (iz & 0xffffffffL); }

    /** May an AI explosive go off at (x, z) at time {@code now} (seconds)? Counts a refusal. */
    public static boolean ready(double x, double z, double now) {
        if (!enabled) return true;
        config();
        long ix = (long) Math.floor(x / area), iz = (long) Math.floor(z / area);
        for (long dx = -1; dx <= 1; dx++)
            for (long dz = -1; dz <= 1; dz++) {
                Double u = until.get(cell(ix + dx, iz + dz));
                if (u != null && now < u) { refused++; return false; }
            }
        return true;
    }

    /** {@link #ready} without counting a refusal (a weapon pick asks every think). */
    public static boolean readyQuiet(double x, double z, double now) {
        int r = refused;
        boolean ok = ready(x, z, now);
        refused = r;
        return ok;
    }

    /** An AI explosive went off at (x, z): its cell cools for the cooldown. */
    public static void mark(double x, double z, double now) {
        fired++;
        if (!enabled) return;
        config();
        long ix = (long) Math.floor(x / area), iz = (long) Math.floor(z / area);
        until.put(cell(ix, iz), now + cooldown);
        if (until.size() > 256) until.values().removeIf(u -> u < now);
    }

    /** Seconds since start on the engine clock (the callers' "now"). */
    public static double now() { return godot.api.Time.INSTANCE.getTicksMsec() / 1000.0; }

    /** "fired,refused" since start (probe readout). */
    public static String counts() { return fired + "," + refused; }

    public static void reset() {
        until.clear();
        fired = 0;
        refused = 0;
        cooldown = -1;
    }
}
