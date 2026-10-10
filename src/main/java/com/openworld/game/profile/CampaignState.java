package com.openworld.game.profile;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

/**
 * CR1's per-player campaign DATA (PLAN.md 1.4 carries it; the CampaignGraph that derives unlocks from it comes with
 * AR1 in 2.1, when MissionDirector's one global copy moves here): typed-by-id flags, achieved (activity, variant)
 * keys, chapter / phase (incl. POST_ENDING), endings seen, the campaign checkpoint id, and the content version the
 * migrations run from.
 */
public final class CampaignState {
    public final Map<String, String> flags = new LinkedHashMap<>();
    public final Set<String> achieved = new LinkedHashSet<>();
    public String chapter = "";
    public String phase = "";
    public final Set<String> endingsSeen = new LinkedHashSet<>();
    public String checkpoint = "";
    public long contentVersion;

    Map<String, Object> toMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("flags", new LinkedHashMap<>(flags));
        m.put("achieved", new ArrayList<>(achieved));
        m.put("chapter", chapter);
        m.put("phase", phase);
        m.put("endings_seen", new ArrayList<>(endingsSeen));
        m.put("checkpoint", checkpoint);
        m.put("content_version", contentVersion);
        return m;
    }

    void read(Map<String, Object> m) {
        flags.clear();
        achieved.clear();
        endingsSeen.clear();
        chapter = phase = checkpoint = "";
        contentVersion = 0;
        if (m == null) return;
        Map<String, Object> f = Maps.map(m.get("flags"));
        if (f != null) for (Map.Entry<String, Object> e : f.entrySet()) flags.put(e.getKey(), String.valueOf(e.getValue()));
        for (Object o : Maps.list(m, "achieved")) if (o instanceof String s) achieved.add(s);
        for (Object o : Maps.list(m, "endings_seen")) if (o instanceof String s) endingsSeen.add(s);
        chapter = Maps.str(m, "chapter", "");
        phase = Maps.str(m, "phase", "");
        checkpoint = Maps.str(m, "checkpoint", "");
        contentVersion = Maps.lng(m, "content_version", 0);
    }
}
