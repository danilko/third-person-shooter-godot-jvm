package com.openworld.game.campaign;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

/**
 * A campaign state held in memory: one player's story and one world, with nothing behind it. The lint walks these
 * ({@link CampaignLint}), unit tests assert on them, and CR6's {@code FakeActivityHost} will run activities against
 * one. By default it is OPTIMISTIC about what the graph cannot decide -- any career, unlimited money -- because a
 * player can change career and earn; set {@link #career} / {@link #balance} to pin them.
 */
public final class SimCampaign implements CampaignWrite {

    public final Map<String, String> personalFlags = new TreeMap<>();
    public final Map<String, String> worldFlags = new TreeMap<>();
    public final Set<String> achieved = new TreeSet<>();
    public final Set<String> endings = new TreeSet<>();
    public final Set<String> dead = new TreeSet<>();
    public final Map<String, String> places = new TreeMap<>();
    public final Set<String> sticky = new TreeSet<>();
    public String phase = "";
    public String chapter = "";
    /** null = any career passes. */
    public String career;
    public long balance = Long.MAX_VALUE;

    public SimCampaign copy() {
        SimCampaign c = new SimCampaign();
        c.personalFlags.putAll(personalFlags);
        c.worldFlags.putAll(worldFlags);
        c.achieved.addAll(achieved);
        c.endings.addAll(endings);
        c.dead.addAll(dead);
        c.places.putAll(places);
        c.sticky.addAll(sticky);
        c.phase = phase;
        c.chapter = chapter;
        c.career = career;
        c.balance = balance;
        return c;
    }

    /** Two states with the same key are the same state (everything is kept sorted). */
    public String key() {
        return personalFlags + "|" + worldFlags + "|" + achieved + "|" + endings + "|" + dead + "|" + places + "|"
                + sticky + "|" + phase + "|" + chapter;
    }

    /** What a designer reads in a lint report: what was done and what is set. */
    public String describe() {
        Map<String, String> f = new LinkedHashMap<>(personalFlags);
        f.putAll(worldFlags);
        return "done " + achieved + (f.isEmpty() ? "" : " flags " + f) + (dead.isEmpty() ? "" : " dead " + dead);
    }

    @Override public String flag(FlagKey key) {
        String v = (key.scope() == FlagKey.Scope.WORLD ? worldFlags : personalFlags).get(key.id());
        return v == null ? "" : v;
    }

    @Override public boolean achieved(String activity, String variant) {
        if (!variant.isEmpty()) return achieved.contains(CampaignGraph.achievedKey(activity, variant));
        String prefix = activity + "#";
        for (String k : achieved) if (k.startsWith(prefix)) return true;
        return false;
    }

    @Override public String phase() { return phase; }
    @Override public boolean endingSeen(String ending) { return endings.contains(ending); }
    @Override public boolean hasCareer(String c) { return career == null || career.equals(c); }
    @Override public long balance() { return balance; }
    @Override public boolean storyDead(String storyId) { return dead.contains(storyId); }
    @Override public boolean stickyUnlocked(String activity) { return sticky.contains(activity); }

    @Override public void setFlag(FlagKey key, String value) {
        Map<String, String> m = key.scope() == FlagKey.Scope.WORLD ? worldFlags : personalFlags;
        if (value.isEmpty()) m.remove(key.id());
        else m.put(key.id(), value);
    }

    @Override public void achieve(String activity, String variant) { achieved.add(CampaignGraph.achievedKey(activity, variant)); }

    @Override public void ending(String ending) {
        endings.add(ending);
        phase = CampaignGraph.POST_ENDING;
    }

    @Override public void chapter(String c) { chapter = c; }
    @Override public void markStoryDead(String storyId) { dead.add(storyId); }

    @Override public void setPlace(String placeId, String owner, String state) {
        if (owner.isEmpty() && state.isEmpty()) places.remove(placeId);
        else places.put(placeId, owner + "/" + state);
    }

    @Override public void unlockSticky(String activity) { sticky.add(activity); }
}
