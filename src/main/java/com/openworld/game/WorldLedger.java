package com.openworld.game;

import com.openworld.game.event.GameplayEvent;
import com.openworld.game.event.GameplayEvents;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * What the story changed in the WORLD for good (PLAN.md 2.0 / CR3) -- the host's, saved in the world slot, never in a
 * player's profile (the co-op model: the world is the host's, the story is each player's). The island is generated
 * and streamed, so nothing in a scene can remember that a boss is dead or that a shop changed hands; the ledger does,
 * keyed by ids that survive streaming and rebuilds:
 * <ul>
 *   <li><b>world flags</b> -- {@code flag id -> value}: facts about the place ("bridge_open"), never a player's
 *   choice (that is a PERSONAL flag, in the profile's CampaignState);</li>
 *   <li><b>dead story characters</b> -- a story character's id (its authored characterId): killed once, it is not
 *   spawned again in this world ({@code ZoneManager.spawnNamed}, {@code AICharacter._ready});</li>
 *   <li><b>place overrides</b> -- {@code place id -> owner / state} over the generated places record (a shop taken
 *   over by another gang, a building burnt out).</li>
 * </ul>
 * The fourth part of CR3's ledger, faction-baseline overrides, is {@code FactionManager}'s CAMPAIGN layer (PLAN.md
 * 0.35): it has its own owner, save key and replication already, so it is not duplicated here.
 *
 * <p>Engine-free ({@code WorldLedgerTest}). ONE current ledger per process ({@link #get}); a load or a new game
 * {@link #replace}s it. Written on the authority only -- its writers are host systems, and {@link #SUBSCRIBER} hears
 * {@link GameplayEvents}, which a client never delivers. A change bumps {@link #revision} (the save's dirty flag).
 */
public final class WorldLedger {

    /** What the story made of a place: who holds it now ("" = as generated) and its state ("" = as generated). */
    public record PlaceOverride(String owner, String state) {
        public PlaceOverride {
            owner = owner == null ? "" : owner;
            state = state == null ? "" : state;
        }
    }

    private final Map<String, String> flags = new LinkedHashMap<>();
    private final Set<String> dead = new LinkedHashSet<>();
    private final Map<String, PlaceOverride> places = new LinkedHashMap<>();
    private long revision;

    private static WorldLedger current = new WorldLedger();

    /** This world's ledger. */
    public static synchronized WorldLedger get() { return current; }

    /** A load or a new game: the world's ledger is now {@code l} (null = an empty one). */
    public static synchronized void replace(WorldLedger l) { current = l == null ? new WorldLedger() : l; }

    /**
     * The ledger's ear on the event stream (phase LEDGER): a STORY character killed is dead for good. Not inside a
     * sandbox -- a mission replay spawns its own copy of a dead boss and killing it changes nothing.
     */
    public static final GameplayEvents.Subscriber SUBSCRIBER = (e, ruling) -> {
        if (ruling.sandboxed()) return;
        if (e instanceof GameplayEvent.Killed k && !k.target().storyId().isEmpty()) get().markDead(k.target().storyId());
    };

    // ── world flags ──

    /** Set a world flag. True when it changed (and a {@code FlagChanged} event was published). */
    public boolean setFlag(String id, String value) {
        if (id == null || id.isEmpty() || value == null || value.isEmpty()) return false;
        synchronized (this) {
            if (value.equals(flags.get(id))) return false;
            flags.put(id, value);
            revision++;
        }
        GameplayEvents.publish(new GameplayEvent.FlagChanged(id, value));
        return true;
    }

    public boolean setFlag(String id, boolean on) { return on ? setFlag(id, "1") : clearFlag(id); }

    public boolean clearFlag(String id) {
        synchronized (this) {
            if (flags.remove(id) == null) return false;
            revision++;
        }
        GameplayEvents.publish(new GameplayEvent.FlagChanged(id, ""));
        return true;
    }

    /** A flag's value, {@code def} when it is not set. */
    public synchronized String flag(String id, String def) {
        String v = flags.get(id);
        return v == null ? def : v;
    }

    /** Set to anything but "0" / "false". */
    public synchronized boolean isSet(String id) {
        String v = flags.get(id);
        return v != null && !v.equals("0") && !v.equalsIgnoreCase("false");
    }

    public synchronized Map<String, String> flags() { return new LinkedHashMap<>(flags); }

    // ── dead story characters ──

    /** True when this is news. */
    public synchronized boolean markDead(String storyId) {
        if (storyId == null || storyId.isEmpty() || !dead.add(storyId)) return false;
        revision++;
        return true;
    }

    public synchronized boolean isDead(String storyId) { return storyId != null && dead.contains(storyId); }

    public synchronized List<String> deadStoryCharacters() { return new ArrayList<>(dead); }

    // ── place overrides ──

    /** Override a place (both "" = back to as generated). True when it changed. */
    public synchronized boolean setPlace(String placeId, String owner, String state) {
        if (placeId == null || placeId.isEmpty()) return false;
        PlaceOverride o = new PlaceOverride(owner, state);
        boolean blank = o.owner().isEmpty() && o.state().isEmpty();
        PlaceOverride had = places.get(placeId);
        if (blank ? had == null : o.equals(had)) return false;
        if (blank) places.remove(placeId);
        else places.put(placeId, o);
        revision++;
        return true;
    }

    /** The override on a place, or null (as generated). */
    public synchronized PlaceOverride place(String placeId) { return placeId == null ? null : places.get(placeId); }

    /** Who holds a place now: the override's owner, else {@code generated}. */
    public synchronized String ownerOf(String placeId, String generated) {
        PlaceOverride o = place(placeId);
        return o == null || o.owner().isEmpty() ? generated : o.owner();
    }

    public synchronized Map<String, PlaceOverride> places() { return new LinkedHashMap<>(places); }

    // ── state ──

    /** Counts the changes: the save writes when it moved. */
    public synchronized long revision() { return revision; }

    public synchronized boolean isEmpty() { return flags.isEmpty() && dead.isEmpty() && places.isEmpty(); }

    /** The ONE shape on disk (the world slot's {@code ledger}) and, later, on the wire (AR5's join baseline). */
    public synchronized Map<String, Object> toMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("flags", new LinkedHashMap<String, Object>(flags));
        m.put("dead", new ArrayList<Object>(dead));
        Map<String, Object> p = new LinkedHashMap<>();
        for (Map.Entry<String, PlaceOverride> e : places.entrySet()) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("owner", e.getValue().owner());
            row.put("state", e.getValue().state());
            p.put(e.getKey(), row);
        }
        m.put("places", p);
        return m;
    }

    /** From {@link #toMap}'s shape; anything missing or of the wrong type reads as empty (an old slot has none). */
    public static WorldLedger fromMap(Map<String, Object> m) {
        WorldLedger l = new WorldLedger();
        if (m == null) return l;
        if (m.get("flags") instanceof Map<?, ?> f)
            for (Map.Entry<?, ?> e : f.entrySet())
                if (e.getValue() instanceof String v && !v.isEmpty()) l.flags.put(String.valueOf(e.getKey()), v);
        if (m.get("dead") instanceof List<?> d)
            for (Object o : d) if (o instanceof String s && !s.isEmpty()) l.dead.add(s);
        if (m.get("places") instanceof Map<?, ?> p)
            for (Map.Entry<?, ?> e : p.entrySet())
                if (e.getValue() instanceof Map<?, ?> row) {
                    PlaceOverride o = new PlaceOverride(row.get("owner") instanceof String s ? s : "",
                            row.get("state") instanceof String s2 ? s2 : "");
                    if (!o.owner().isEmpty() || !o.state().isEmpty()) l.places.put(String.valueOf(e.getKey()), o);
                }
        return l;
    }
}
