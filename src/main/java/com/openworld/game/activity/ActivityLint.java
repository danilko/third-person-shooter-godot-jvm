package com.openworld.game.activity;

import com.openworld.game.campaign.ActivityDef;
import com.openworld.game.campaign.CampaignGraph;
import com.openworld.game.campaign.FlagKey;
import com.openworld.game.campaign.Requirement;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * The lint of the activity CLASSES (PLAN.md 2.1 / CR6), beside {@code CampaignLint}'s lint of the graph: every
 * authored activity has a class that runs it and at least one stage, no two start on the same zone, and a
 * {@code replayWorld} names only WORLD state (CR7: "the graph lint checks each replayWorld"). What a class DOES --
 * that its stages reach each declared variant -- is its own tier-1 test against a {@link FakeActivityHost}.
 */
public final class ActivityLint {
    private ActivityLint() {}

    public record Report(List<String> problems, List<String> notes) {
        public boolean ok() { return problems.isEmpty(); }
    }

    public static Report check(CampaignGraph g) {
        List<String> problems = new ArrayList<>(), notes = new ArrayList<>();
        Map<String, String> zones = new LinkedHashMap<>();
        for (ActivityDef d : g.activities()) {
            String at = "activity '" + d.id + "'";
            if (d.isPlanned()) continue;
            if (!d.hasScript()) {
                notes.add(at + " has no class that runs it (.runs(..)): it cannot be started on the framework");
                continue;
            }
            Plan p = new Plan();
            try {
                d.newRun().define(p);
            } catch (RuntimeException e) {
                problems.add(at + " threw in define(): " + e);
                continue;
            }
            if (p.stages.isEmpty()) problems.add(at + " declares no stage");
            for (Stage s : p.stages.values())
                if (s.enter == null && s.tick == null && s.events.isEmpty() && s.timers.isEmpty() && s.conditions.isEmpty())
                    problems.add(at + " stage '" + s.id + "' has nothing in it: nothing can ever leave it");
            if (!p.startZone.isEmpty()) {
                String had = zones.putIfAbsent(p.startZone, d.id);
                if (had != null) problems.add(at + " starts on zone '" + p.startZone + "', which already starts '" + had + "'");
            }
            enforcement(at, p.enforcement, problems);
            for (Requirement need : p.replayWorld) {
                boolean world = need instanceof Requirement.StoryAlive
                        || (need instanceof Requirement.Flag f && f.key().scope() == FlagKey.Scope.WORLD);
                if (!world) problems.add(at + " replayWorld names " + need + ", which is not WORLD state");
                if (need instanceof Requirement.Flag f && g.flag(f.key().id()) == null)
                    problems.add(at + " replayWorld names flag '" + f.key().id() + "', which no module declares");
            }
        }
        return new Report(List.copyOf(problems), List.copyOf(notes));
    }

    /** How many bodies a force can field in this world, all stations full (-1 = not known here: the world's places
     *  are not loaded). The runtime sets it from the dispatch's pools; the unit tests leave it unknown. */
    public static java.util.function.ToIntFunction<String> forceCapacity = force -> -1;

    /** The enforcement hooks it declares (PLAN.md P1e step 5): stars in range, bounds that can both hold, forces that
     *  exist, a force not both sent and kept away, and no more reserved than the force can field. */
    static void enforcement(String at, Plan.Enforcement e, List<String> problems) {
        int max = com.openworld.game.WantedRules.MAX_STARS;
        java.util.Set<String> forces = new java.util.LinkedHashSet<>();
        try {
            com.openworld.game.data.Tables.Forces f = com.openworld.game.data.Tables.FORCES.get();
            if (f != null) forces.addAll(f.sides().keySet());
        } catch (LinkageError noEngine) {
            // a unit test with no table source: the force names are not checked
        }
        boolean knowForces = !forces.isEmpty();
        forces.add(com.openworld.character.Faction.POLICE);
        for (int v : new int[]{e.wantedAtLeast, e.wantedAtMost, e.wantedSet})
            if (v > max) problems.add(at + " asks for " + v + " stars; there are " + max);
        if (e.wantedAtLeast >= 0 && e.wantedAtMost >= 0 && e.wantedAtLeast > e.wantedAtMost)
            problems.add(at + " holds the stars at least " + e.wantedAtLeast + " and at most " + e.wantedAtMost + ": both cannot hold");
        if (e.wantedSet >= 0 && e.wantedClear) problems.add(at + " both sets and clears the stars as it starts");
        for (var s : e.squads.entrySet()) {
            if (knowForces && !forces.contains(s.getKey())) problems.add(at + " sends a squad of '" + s.getKey() + "', which is not a force (game/forces.json)");
            if (s.getValue() < 1 || s.getValue() > max) problems.add(at + " sends '" + s.getKey() + "' at " + s.getValue() + " stars (1.." + max + ")");
            if (e.noDispatchAll || e.noDispatch.contains(s.getKey()))
                problems.add(at + " both sends '" + s.getKey() + "' and keeps it from coming (noDispatch)");
        }
        for (String side : e.noDispatch)
            if (knowForces && !forces.contains(side)) problems.add(at + " keeps '" + side + "' away, which is not a force");
        for (var r : e.reserves.entrySet()) {
            if (knowForces && !forces.contains(r.getKey())) problems.add(at + " reserves '" + r.getKey() + "', which is not a force");
            if (r.getValue() < 1) problems.add(at + " reserves " + r.getValue() + " of '" + r.getKey() + "'");
            int cap = forceCapacity.applyAsInt(r.getKey());
            if (cap >= 0 && r.getValue() > cap)
                problems.add(at + " reserves " + r.getValue() + " of '" + r.getKey() + "', which fields only " + cap + " here");
        }
    }
}
