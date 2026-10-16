package com.openworld.game.encounter;

/**
 * The life of one Encounter (PLAN.md 2.2 / F6), engine-free ({@code EncounterWavesTest}): when its first wave stands
 * up, when it turns on the players, when the next wave comes, when it is cleared and when it resets.
 *
 * <pre>
 *   DORMANT --a player within spawnNear (or start())--> STANDING   (wave 1 stands at its spawn points, calm)
 *   STANDING --a player within triggerRadius, a player's attack on it, or start()--> ENGAGED
 *   ENGAGED --alive <= nextWaveAt and waveGap s since the last wave--> the next wave
 *   ENGAGED --every wave out and nobody left alive--> CLEARED
 *   STANDING / ENGAGED --every player past despawnFar--> DORMANT (the living are taken away; it may happen again)
 *   CLEARED --every player past despawnFar, and not once--> DORMANT
 * </pre>
 *
 * A MANUAL encounter (an activity's, a ZoneTrigger's) never stands up by itself: {@link #start} spawns wave 1 and
 * engages at once; {@link #stop} takes everyone away.
 */
public final class EncounterWaves {

    public enum State { DORMANT, STANDING, ENGAGED, CLEARED }

    /**
     * @param waves       bodies per wave (wave 1 first); an empty list is one wave of 0 (never stands up)
     * @param triggerRadius a player this close turns it on them (0 = only a hurt member or start())
     * @param nextWaveAt  the next wave comes once this few of the earlier ones are still up
     * @param waveGap     ... and no sooner than this many seconds after the last one
     * @param once        a cleared encounter stays cleared while its scene stays loaded
     */
    public record Config(int[] waves, double triggerRadius, double spawnNear, double despawnFar, int nextWaveAt,
                         double waveGap, boolean manual, boolean once) {}

    /** What the node does for it. {@code spawnWave} returns how many bodies it could stand up (the cap may refuse). */
    public interface Out {
        int spawnWave(int index, int count);
        void engage();
        void releaseAll();
        void cleared();
    }

    private final Config cfg;
    private State state = State.DORMANT;
    private int nextWave;
    private double sinceWave;
    private boolean startAsked;

    public EncounterWaves(Config cfg) { this.cfg = cfg; }

    public State state() { return state; }
    /** Waves not out yet. */
    public int wavesLeft() { return Math.max(0, cfg.waves().length - nextWave); }
    public Config config() { return cfg; }

    /** Already cleared before it ever stood up (its world flag is set: a saved world where it was won). */
    public void markCleared() {
        state = State.CLEARED;
        nextWave = cfg.waves().length;
    }

    /** An activity or a trigger starts it now: wave 1 at once, engaged. */
    public void start() { startAsked = true; }

    /** An activity ended: everyone still up is taken away and it goes dormant (a cleared one stays cleared). */
    public void stop(Out out) {
        startAsked = false;
        if (state == State.STANDING || state == State.ENGAGED) {
            out.releaseAll();
            reset();
        }
    }

    /**
     * One step. {@code nearest} = the nearest player's distance to the encounter, {@code alive} = its members still
     * up, {@code provoked} = a PLAYER attacked a member since the last step (or a member is already on a player).
     */
    public void step(double dt, double nearest, int alive, boolean provoked, Out out) {
        switch (state) {
            case DORMANT -> {
                if (startAsked || (!cfg.manual() && nearest < cfg.spawnNear())) {
                    if (!spawnNext(out)) return;
                    state = State.STANDING;
                    if (startAsked) engage(out);
                }
            }
            case STANDING -> {
                if (nearest > cfg.despawnFar() && !startAsked) {
                    out.releaseAll();
                    reset();
                } else if (startAsked || provoked || (cfg.triggerRadius() > 0 && nearest < cfg.triggerRadius())) {
                    engage(out);
                }
            }
            case ENGAGED -> {
                sinceWave += dt;
                if (nearest > cfg.despawnFar() && !startAsked) {
                    out.releaseAll();
                    reset();
                    return;
                }
                if (nextWave < cfg.waves().length) {
                    if (alive <= cfg.nextWaveAt() && sinceWave >= cfg.waveGap()) spawnNext(out);
                } else if (alive == 0) {
                    state = State.CLEARED;
                    startAsked = false;
                    out.cleared();
                }
            }
            case CLEARED -> {
                // asked again (an activity's retry) or let go (not once, everyone gone): it may happen again
                if (startAsked || (!cfg.once() && nearest > cfg.despawnFar())) reset();
            }
        }
    }

    private void engage(Out out) {
        state = State.ENGAGED;
        sinceWave = 0;
        out.engage();
    }

    /** Stand the next wave up; false when nothing could be (the cap is full) -- tried again next step. */
    private boolean spawnNext(Out out) {
        if (nextWave >= cfg.waves().length) return false;
        int want = cfg.waves()[nextWave];
        int got = want <= 0 ? 0 : out.spawnWave(nextWave, want);
        if (want > 0 && got <= 0) return false;
        nextWave++;
        sinceWave = 0;
        return true;
    }

    private void reset() {
        state = State.DORMANT;
        nextWave = 0;
        sinceWave = 0;
    }

    /** "4,3" -> {4, 3}; a bad entry is 0. */
    public static int[] parseWaves(String csv) {
        if (csv == null || csv.isBlank()) return new int[0];
        String[] parts = csv.split(",");
        int[] out = new int[parts.length];
        for (int i = 0; i < parts.length; i++) {
            try { out[i] = Math.max(0, Integer.parseInt(parts[i].trim())); } catch (NumberFormatException e) { out[i] = 0; }
        }
        return out;
    }
}
