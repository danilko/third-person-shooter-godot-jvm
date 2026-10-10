package com.openworld.game.profile;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * CR2's career state (PLAN.md 1.4 carried the data; 2.1 adds the OVERRIDE STACK below; the careers themselves --
 * what each allows, its ranks -- are 4.10 in 3.3): the base career, a record per career (rank, strikes ... as named
 * counters), and the override JOURNAL -- the activity instances that pushed a temporary career, so a load can pop
 * the ones no longer running. Engine-free ({@code CareerStateTest}).
 */
public final class CareerState {
    public String base = "";
    public final Map<String, Map<String, Long>> recordByCareer = new LinkedHashMap<>();
    public final List<String> overrideJournal = new ArrayList<>();

    // ── the override stack (CR2) ──

    /**
     * A TEMPORARY career an activity put the player in ("undercover as a police officer for this mission").
     * {@code real} false (the default routing, TEMP): strikes and counters earned under it go to a SCRATCH record
     * that is discarded when it pops; true (REAL): they land on the career's real record ("exposed", "fired from
     * the force" in a critical mission must say REAL).
     */
    public record Override(String instanceId, String career, boolean real) {
        String encode() { return instanceId + "|" + career + "|" + (real ? "REAL" : "TEMP"); }

        static Override decode(String s) {
            String[] p = s == null ? new String[0] : s.split("\\|", -1);
            return p.length == 3 && !p[0].isEmpty() ? new Override(p[0], p[1], p[2].equals("REAL")) : null;
        }
    }

    /** Scratch counters of each TEMP override, by activity instance. Never saved: a load pops what is not running. */
    private final Map<String, Map<String, Long>> scratch = new LinkedHashMap<>();

    /** The overrides, oldest first (the journal IS the stack: it is what the profile saves). */
    public List<Override> overrides() {
        List<Override> out = new ArrayList<>();
        for (String s : overrideJournal) {
            Override o = Override.decode(s);
            if (o != null) out.add(o);
        }
        return out;
    }

    private Override top() {
        List<Override> o = overrides();
        return o.isEmpty() ? null : o.get(o.size() - 1);
    }

    /** The career the player has NOW: the newest override's, else the base. Careers.allows() reads this. */
    public String effective() {
        Override t = top();
        return t == null ? base : t.career();
    }

    /** Only the Activity framework pushes: an activity started that puts this player in {@code career}. */
    public boolean push(String instanceId, String career, boolean real) {
        if (instanceId == null || instanceId.isEmpty() || career == null) return false;
        for (Override o : overrides()) if (o.instanceId().equals(instanceId)) return false;
        overrideJournal.add(new Override(instanceId, career, real).encode());
        return true;
    }

    /** The activity ended (complete / fail / abort / owner disconnect): its override goes, wherever it is in the
     *  stack, and its scratch record with it. */
    public boolean pop(String instanceId) {
        scratch.remove(instanceId);
        return overrideJournal.removeIf(s -> {
            Override o = Override.decode(s);
            return o == null || o.instanceId().equals(instanceId);
        });
    }

    /** After a load (a crash, a disconnect, a save taken mid-mission): pop every override whose activity is not
     *  running. Returns how many went. */
    public int reconcile(java.util.function.Predicate<String> running) {
        int n = 0;
        for (Override o : overrides()) if (!running.test(o.instanceId()) && pop(o.instanceId())) n++;
        return n;
    }

    /**
     * Add {@code n} to a counter of the EFFECTIVE career ("strikes", "arrests"): onto the scratch record under a TEMP
     * override, onto the real record otherwise. Returns true when it landed on the real record.
     */
    public boolean count(String counter, long n) {
        Override t = top();
        if (t != null && !t.real()) {
            scratch.computeIfAbsent(t.instanceId(), k -> new LinkedHashMap<>()).merge(counter, n, Long::sum);
            return false;
        }
        recordByCareer.computeIfAbsent(effective(), k -> new LinkedHashMap<>()).merge(counter, n, Long::sum);
        return true;
    }

    /** A counter as the player's CURRENT situation has it: the scratch record under a TEMP override. */
    public long effectiveCount(String counter) {
        Override t = top();
        if (t != null && !t.real()) {
            Map<String, Long> s = scratch.get(t.instanceId());
            Long v = s == null ? null : s.get(counter);
            return v == null ? 0 : v;
        }
        return record(effective(), counter);
    }

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
