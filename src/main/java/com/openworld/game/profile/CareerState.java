package com.openworld.game.profile;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * CR2's career DATA (PLAN.md 1.4 carries it; the typed state machine and its override stack come with AR1 in 2.1 and
 * 4.10 in 3.3): the base career, a record per career (rank, strikes ... as named counters), and the override
 * JOURNAL -- the activity instances that pushed a temporary career, so a load can pop the ones no longer running.
 */
public final class CareerState {
    public String base = "";
    public final Map<String, Map<String, Long>> recordByCareer = new LinkedHashMap<>();
    public final List<String> overrideJournal = new ArrayList<>();

    public long record(String career, String counter) {
        Map<String, Long> r = recordByCareer.get(career);
        Long v = r == null ? null : r.get(counter);
        return v == null ? 0 : v;
    }

    Map<String, Object> toMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("base", base);
        Map<String, Object> rec = new LinkedHashMap<>();
        for (Map.Entry<String, Map<String, Long>> e : recordByCareer.entrySet()) rec.put(e.getKey(), new LinkedHashMap<>(e.getValue()));
        m.put("records", rec);
        m.put("override_journal", new ArrayList<>(overrideJournal));
        return m;
    }

    void read(Map<String, Object> m) {
        base = "";
        recordByCareer.clear();
        overrideJournal.clear();
        if (m == null) return;
        base = Maps.str(m, "base", "");
        Map<String, Object> rec = Maps.map(m.get("records"));
        if (rec != null) {
            for (Map.Entry<String, Object> e : rec.entrySet()) {
                Map<String, Object> counters = Maps.map(e.getValue());
                if (counters == null) continue;
                Map<String, Long> out = new LinkedHashMap<>();
                for (String k : counters.keySet()) out.put(k, Maps.lng(counters, k, 0));
                recordByCareer.put(e.getKey(), out);
            }
        }
        for (Object o : Maps.list(m, "override_journal")) if (o instanceof String s) overrideJournal.add(s);
    }
}
