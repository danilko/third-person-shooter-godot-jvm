package com.openworld.game.campaign;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** What a {@link CampaignModule} declares into; {@link #build} gives the immutable {@link CampaignGraph}. */
public final class CampaignBuilder {

    final Map<String, FlagKey> flags = new LinkedHashMap<>();
    final Map<String, ActivityDef> activities = new LinkedHashMap<>();
    final Set<String> endings = new LinkedHashSet<>();
    final List<String> problems = new ArrayList<>();
    boolean openEnded;
    private String module = "?";

    /** Declare a flag; the returned key is what requirements and effects name. */
    public FlagKey flag(FlagKey key) {
        FlagKey had = flags.putIfAbsent(key.id(), key);
        if (had != null && !had.equals(key)) problems.add(module + ": flag '" + key.id() + "' is declared twice, differently");
        return had != null ? had : key;
    }

    public FlagKey worldFlag(String id) { return flag(FlagKey.bool(id, FlagKey.Scope.WORLD)); }

    public FlagKey personalFlag(String id) { return flag(FlagKey.bool(id, FlagKey.Scope.PERSONAL)); }

    public FlagKey personalChoice(String id, String... values) { return flag(FlagKey.choice(id, FlagKey.Scope.PERSONAL, values)); }

    /** Declare an activity (an id declared twice is a problem). */
    public ActivityDef activity(String id) {
        ActivityDef d = new ActivityDef(id);
        if (activities.putIfAbsent(id, d) != null) problems.add(module + ": activity '" + id + "' is declared twice");
        return d;
    }

    /** Declare an ending; some activity's variant must reach it with {@link Effect#ending}. */
    public CampaignBuilder ending(String id) {
        endings.add(id);
        return this;
    }

    /**
     * The campaign is still being written and has no ending yet: the lint's "an ending stays reachable" check is
     * skipped (and SAYS so in its notes). Remove it with the first ending.
     */
    public CampaignBuilder openEnded() {
        openEnded = true;
        return this;
    }

    /** Run every module, in order. */
    public CampaignBuilder add(List<? extends CampaignModule> modules) {
        Set<String> ids = new LinkedHashSet<>();
        for (CampaignModule m : modules) {
            module = m.id();
            if (!ids.add(m.id())) problems.add("module id '" + m.id() + "' is used twice");
            m.define(this);
        }
        module = "?";
        return this;
    }

    public CampaignGraph build() { return new CampaignGraph(this); }
}
