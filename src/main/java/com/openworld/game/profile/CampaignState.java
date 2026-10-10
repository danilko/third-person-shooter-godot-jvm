package com.openworld.game.profile;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

/**
 * CR1's per-player campaign DATA (PLAN.md 1.4 carries it; {@code game.campaign.CampaignGraph} derives unlocks from
 * it through {@code LiveCampaign}; MissionDirector's one global copy moves here with the Activity runtime, 2.1):
 * flags declared as {@code FlagKey}s, achieved {@code "activity#variant"} keys, the sticky unlocks, chapter / phase (incl. POST_ENDING), endings seen, the campaign checkpoint id, and the content version the
 * migrations run from.
 */
public final class CampaignState {
    public final Map<String, String> flags = new LinkedHashMap<>();
    public final Set<String> achieved = new LinkedHashSet<>();
    public String chapter = "";
    public String phase = "";
    public final Set<String> endingsSeen = new LinkedHashSet<>();
    /** STICKY activities that have been available once (CampaignGraph: they stay open). */
    public final Set<String> sticky = new LinkedHashSet<>();
    public String checkpoint = "";
    public long contentVersion;

    /** A new story: nothing done, nothing set. */
    public void reset() { read(null); }

    Map<String, Object> toMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("flags", new LinkedHashMap<>(flags));
        m.put("achieved", new ArrayList<>(achieved));
        m.put("chapter", chapter);
        m.put("phase", phase);
        m.put("endings_seen", new ArrayList<>(endingsSeen));
        m.put("sticky", new ArrayList<>(sticky));
        m.put("checkpoint", checkpoint);
        m.put("content_version", contentVersion);
        return m;
    }

    void read(Map<String, Object> m) {
        flags.clear();
        achieved.clear();
        endingsSeen.clear();
        sticky.clear();
        chapter = phase = checkpoint = "";
        contentVersion = 0;
        if (m == null) return;
        Map<String, Object> f = Maps.map(m.get("flags"));
        if (f != null) for (Map.Entry<String, Object> e : f.entrySet()) flags.put(e.getKey(), String.valueOf(e.getValue()));
        for (Object o : Maps.list(m, "achieved")) if (o instanceof String s) achieved.add(s);
        for (Object o : Maps.list(m, "endings_seen")) if (o instanceof String s) endingsSeen.add(s);
        for (Object o : Maps.list(m, "sticky")) if (o instanceof String s) sticky.add(s);
        chapter = Maps.str(m, "chapter", "");
        phase = Maps.str(m, "phase", "");
        checkpoint = Maps.str(m, "checkpoint", "");
        contentVersion = Maps.lng(m, "content_version", 0);
    }
}
