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
}
