package com.openworld.game;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

/**
 * THE INCIDENT BOARD (PLAN.md P1e steps 4-7): what has happened where, so the forces can answer it and the radio can
 * tell of it. An incident is a TYPE ("gang_attack", "shots_fired", "trespass", an activity's own ...) at a place, with
 * who was attacked ({@code victim}: a faction) and who did it ({@code attacker}); acts in the same area within
 * {@code mergeRadius} and while the incident is still fresh MERGE into it (a firefight is one incident, not one per
 * shot). It ends {@code expireSeconds} after its last act. New incidents are rate-limited ({@code maxPerMinute}):
 * with the forces' station pools that is the feedback-loop guard for AI-vs-AI fights (PLAN.md P1e design rules).
 *
 * <p>Engine-free ({@code IncidentBoardTest}); the clock is passed in. The dispatch owns one.
 */
public final class IncidentBoard {

    public static final class Incident {
        public final int id;
        public final String type, victim, attacker, source;
        public double x, z;
        public final double started;
        double lastAct;
        public int acts = 1;
        /** Set by whoever answers it (the dispatch's responders), so it is answered once. */
        public boolean answered;

        Incident(int id, String type, double x, double z, String victim, String attacker, String source, double now) {
            this.id = id; this.type = type; this.x = x; this.z = z; this.victim = victim == null ? "" : victim;
            this.attacker = attacker == null ? "" : attacker; this.source = source == null ? "" : source;
            this.started = now; this.lastAct = now;
        }

        public double lastAct() { return lastAct; }
    }

    public final double mergeRadius, expireSeconds;
    public final int maxPerMinute;
    private final List<Incident> live = new ArrayList<>();
    private final List<Double> recentStarts = new ArrayList<>();
    private int nextId = 1, refused;

    /** The board's data (game/forces.json {@code incidents}): merging, expiry, the rate limit, how near a player an
     *  AI-vs-AI act must be to count, and who answers each type. */
    public record Rules(double mergeRadius, double expireSeconds, int maxPerMinute, double nearPlayers,
                        java.util.Map<String, Responder> responders) {
        public static final Rules DEFAULT = new Rules(60.0, 45.0, 6, 150.0, java.util.Map.of());

        public static Rules read(com.openworld.util.DataReader i) {
            if (i == null) return DEFAULT;
            java.util.Map<String, Responder> resp = new java.util.LinkedHashMap<>();
            for (var e : i.rows("responders").entrySet())
                resp.put(e.getKey(), new Responder(e.getValue().reqStr("force", "victim"), e.getValue().integer("units", 2)));
            return new Rules(i.num("merge_radius", 60.0), i.num("expire_seconds", 45.0), i.integer("max_per_minute", 6),
                    i.num("near_players", 150.0), resp);
        }
    }

    /** Who answers an incident type: {@code force} ("police", a gang id, or "victim" = the attacked gang), how many. */
    public record Responder(String force, int units) {}

    public IncidentBoard(Rules r) { this(r.mergeRadius(), r.expireSeconds(), r.maxPerMinute()); }

    public IncidentBoard(double mergeRadius, double expireSeconds, int maxPerMinute) {
        this.mergeRadius = mergeRadius;
        this.expireSeconds = expireSeconds;
        this.maxPerMinute = maxPerMinute;
    }

    /**
     * An act of {@code type} at (x, z): merged into a fresh incident of the same type and victim within mergeRadius,
     * else a new one -- unless the rate limit is spent (then null). Returns the incident and whether it is NEW.
     */
    public Raised raise(String type, double x, double z, String victim, String attacker, String source, double now) {
        expire(now);
        for (Incident i : live) {
            if (!i.type.equals(type) || !i.victim.equals(victim == null ? "" : victim)) continue;
            if (Math.hypot(i.x - x, i.z - z) > mergeRadius) continue;
            i.lastAct = now;
            i.acts++;
            return new Raised(i, false);
        }
        recentStarts.removeIf(t -> t < now - 60.0);
        if (maxPerMinute > 0 && recentStarts.size() >= maxPerMinute) { refused++; return null; }
        recentStarts.add(now);
        Incident i = new Incident(nextId++, type, x, z, victim, attacker, source, now);
        live.add(i);
        return new Raised(i, true);
    }

    public record Raised(Incident incident, boolean isNew) {}

    /** Incidents still live at {@code now}. */
    public List<Incident> live(double now) {
        expire(now);
        return List.copyOf(live);
    }

    /** Live incidents within {@code r} of (x, z). */
    public List<Incident> near(double x, double z, double r, double now) {
        List<Incident> out = new ArrayList<>();
        for (Incident i : live(now)) if (Math.hypot(i.x - x, i.z - z) <= r) out.add(i);
        return out;
    }

    /** Is this incident still live? */
    public boolean isLive(Incident i, double now) {
        expire(now);
        return live.contains(i);
    }

    /** End an incident at once (its activity ended). */
    public void end(String source) {
        if (source == null || source.isEmpty()) return;
        live.removeIf(i -> source.equals(i.source));
    }

    private void expire(double now) {
        for (Iterator<Incident> it = live.iterator(); it.hasNext(); )
            if (now - it.next().lastAct > expireSeconds) it.remove();
    }

    public int refusedCount() { return refused; }

    public int startedCount() { return nextId - 1; }
}
