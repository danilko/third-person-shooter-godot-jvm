package com.openworld.game.campaign;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * The campaign's static checks (PLAN.md 2.1 / CR6, TIER 1) -- the tool that replaces a graph editor. Engine-free, run
 * by {@code CampaignLintTest} on the shipped modules, so a broken graph fails {@code ./gradlew test}:
 * <ol>
 *   <li><b>Everything named is declared</b>: a requirement's flag, value, activity, variant and ending; an effect's
 *   flag, value and ending; every activity has a variant (or is {@code planned()}).</li>
 *   <li><b>Everything declared is reachable</b>: an activity no reachable state can start, an ending no variant
 *   reaches.</li>
 *   <li><b>NO DEAD END</b>: from every reachable state, an ending stays reachable (or one has been reached -- after
 *   an ending the world is open). It is a brute-force walk over every available activity x every variant from the
 *   empty state, which is what guarantees "the player can always continue".</li>
 * </ol>
 * The walk is over ONE world with its ONE player (the host playing alone). It is optimistic about what the graph
 * cannot decide: any career, enough money. NOT checked yet: a guest whose own story meets a world that disagrees
 * (the co-op model's rule 3: a failed world requirement needs an alternative node) -- that needs the cross product
 * of a personal walk and a world walk.
 */
public final class CampaignLint {
    private CampaignLint() {}

    public static final int DEFAULT_MAX_STATES = 200_000;

    public record Report(List<String> problems, List<String> notes, int statesWalked) {
        public boolean ok() { return problems.isEmpty(); }
    }

    public static Report check(CampaignGraph g) { return check(g, DEFAULT_MAX_STATES); }

    public static Report check(CampaignGraph g, int maxStates) {
        List<String> problems = new ArrayList<>(g.buildProblems());
        List<String> notes = new ArrayList<>();
        declared(g, problems, notes);
        int walked = walk(g, maxStates, problems, notes);
        return new Report(List.copyOf(problems), List.copyOf(notes), walked);
    }

    // ── 1. everything named is declared ──

    private static void declared(CampaignGraph g, List<String> problems, List<String> notes) {
        for (ActivityDef d : g.activities()) {
            String at = "activity '" + d.id + "'";
            if (d.isPlanned()) notes.add(at + " is planned, not authored: never available");
            else if (d.variants().isEmpty()) problems.add(at + " has no variant (nothing can complete it)");
            d.requirement().visit(r -> requirement(g, at + " requires", r, problems));
            for (String v : d.variants())
                for (Effect e : d.effects(v)) effect(g, at + " variant '" + v + "'", e, problems);
        }
    }

    private static void flag(CampaignGraph g, String at, FlagKey key, String value, List<String> problems) {
        FlagKey declared = g.flag(key.id());
        if (declared == null) problems.add(at + " flag '" + key.id() + "', which no module declares");
        else if (!declared.equals(key)) problems.add(at + " flag '" + key.id() + "' with another scope / values than declared");
        else if (!value.isEmpty() && !declared.allows(value))
            problems.add(at + " flag '" + key.id() + "' = '" + value + "', not one of " + declared.values());
    }

    private static void requirement(CampaignGraph g, String at, Requirement r, List<String> problems) {
        if (r instanceof Requirement.Flag f) flag(g, at, f.key(), f.value(), problems);
        else if (r instanceof Requirement.Achieved a) {
            ActivityDef d = g.activity(a.activity());
            if (d == null) problems.add(at + " activity '" + a.activity() + "', which no module declares");
            else if (!a.variant().isEmpty() && !d.isPlanned() && !d.hasVariant(a.variant()))
                problems.add(at + " '" + a.activity() + "' variant '" + a.variant() + "', which it does not have");
        } else if (r instanceof Requirement.EndingSeen e && !g.endings().contains(e.ending()))
            problems.add(at + " ending '" + e.ending() + "', which no module declares");
    }

    private static void effect(CampaignGraph g, String at, Effect e, List<String> problems) {
        if (e instanceof Effect.SetFlag s) flag(g, at + " sets", s.key(), s.value(), problems);
        else if (e instanceof Effect.Ending en && !g.endings().contains(en.ending()))
            problems.add(at + " reaches ending '" + en.ending() + "', which no module declares");
    }

    // ── 2 + 3. the walk ──

    private static int walk(CampaignGraph g, int maxStates, List<String> problems, List<String> notes) {
        Map<String, SimCampaign> states = new HashMap<>();
        Map<String, List<String>> next = new HashMap<>();
        List<String> order = new ArrayList<>();
        ArrayDeque<SimCampaign> todo = new ArrayDeque<>();
        Set<String> startable = new LinkedHashSet<>();
        Set<String> endingsReached = new LinkedHashSet<>();
        SimCampaign start = new SimCampaign();
        g.refreshSticky(start);
        states.put(start.key(), start);
        order.add(start.key());
        todo.add(start);
        boolean truncated = false;
        while (!todo.isEmpty()) {
            SimCampaign s = todo.poll();
            List<String> out = next.computeIfAbsent(s.key(), k -> new ArrayList<>());
            endingsReached.addAll(s.endings);
            for (ActivityDef d : g.available(s)) {
                startable.add(d.id);
                for (String v : d.variants()) {
                    SimCampaign n = s.copy();
                    g.complete(d.id, v, n, true);
                    String k = n.key();
                    if (k.equals(s.key())) continue;   // a repeatable job that changes nothing
                    out.add(k);
                    if (states.containsKey(k)) continue;
                    if (states.size() >= maxStates) { truncated = true; continue; }
                    states.put(k, n);
                    order.add(k);
                    todo.add(n);
                }
            }
        }
        if (truncated) problems.add("the walk stopped at " + maxStates + " states: the graph is too large to prove (split it, or raise the cap)");
        for (ActivityDef d : g.activities())
            if (!d.isPlanned() && !d.variants().isEmpty() && !startable.contains(d.id))
                problems.add("activity '" + d.id + "' can never be started: no reachable state meets its requirement");
        for (String e : g.endings())
            if (!endingsReached.contains(e)) problems.add("ending '" + e + "' is never reached");

        if (g.isOpenEnded()) {
            notes.add("open-ended campaign: the NO DEAD END check is skipped until an ending is declared");
        } else if (g.endings().isEmpty()) {
            problems.add("the campaign declares no ending (declare one, or openEnded() while it is being written)");
        } else if (!truncated) {
            // a state is fine when an ending has been reached in it, or it can still get to such a state
            Map<String, List<String>> prev = new HashMap<>();
            for (Map.Entry<String, List<String>> e : next.entrySet())
                for (String to : e.getValue()) prev.computeIfAbsent(to, k -> new ArrayList<>()).add(e.getKey());
            Set<String> fine = new HashSet<>();
            ArrayDeque<String> back = new ArrayDeque<>();
            for (SimCampaign s : states.values())
                if (CampaignGraph.POST_ENDING.equals(s.phase) && fine.add(s.key())) back.add(s.key());
            while (!back.isEmpty())
                for (String p : prev.getOrDefault(back.poll(), List.of())) if (fine.add(p)) back.add(p);
            int shown = 0, dead = 0;
            for (String k : order) {
                if (fine.contains(k)) continue;
                dead++;
                if (shown++ < 5) problems.add("DEAD END: " + states.get(k).describe() + " -- no ending can be reached from here");
            }
            if (dead > 5) problems.add("... and " + (dead - 5) + " more dead-end states");
        }
        notes.add(states.size() + " reachable states walked");
        return states.size();
    }
}
