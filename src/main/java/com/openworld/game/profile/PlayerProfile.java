package com.openworld.game.profile;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * What a PLAYER owns, as opposed to what a body carries or what the world remembers (PLAN.md 1.4: AR2). Each peer
 * keeps its own in {@code user://profile.json}; in co-op the host holds a session copy of every joined player's,
 * changes it (money moves on the host) and sends it back for the owner to save (MSG_PROFILE). Engine-free and
 * unit-tested ({@code PlayerProfileTest}); {@link #toMap} / {@link #fromMap} are its one file shape.
 *
 * <ul>
 *   <li><b>balance</b> -- SIGNED (CR4): a bill the player cannot cover leaves it negative, which is what they owe.
 *       Only {@link Economy#transfer} changes it.</li>
 *   <li><b>debts</b> -- loans with a lender and a due time (CR4; the GameOverRules that read them come with 2.1).</li>
 *   <li><b>career</b> / <b>campaign</b> -- CR2 / CR1's DATA, carried and saved; their engines (the override stack,
 *       the campaign graph) arrive with AR1 in 2.1, so nothing writes them yet.</li>
 *   <li><b>vehicles</b> -- owned cars with their per-instance upgrades ({@link VehicleInstanceData}, F4).</li>
 *   <li><b>unlocks</b> -- ids the player has earned (a completed variant, a shop line).</li>
 * </ul>
 * Unknown keys found in the file are KEPT and written back (a newer build's field survives an older build's save).
 */
public final class PlayerProfile {

    /** The shape of {@link #toMap}; bumped with a step in {@link SaveMigrations#PROFILE}. */
    public static final int VERSION = SaveMigrations.PROFILE_VERSION;

    public String playerId = "";
    public long balance;
    public final List<Debt> debts = new ArrayList<>();
    public final CareerState career = new CareerState();
    public final CampaignState campaign = new CampaignState();
    public final List<VehicleInstanceData> vehicles = new ArrayList<>();
    public final Set<String> unlocks = new LinkedHashSet<>();
    /** The checkpoint of the activity run this player OWNS (CR5, {@code ActivityCheckpoint.toMap}); null = none. */
    public Map<String, Object> activityCheckpoint;
    /** The profile as it was at the last CAMPAIGN checkpoint (CR4): what a game over rolls this player back to.
     *  Null until the first one. */
    private Map<String, Object> checkpointSnapshot;
    /** Counts the checkpoints taken. The snapshot itself never crosses the wire (a profile must fit one packet):
     *  the host's copy carries this, and the owner takes their own snapshot when it moves ({@link #copyFrom}). */
    private long checkpointSeq;
    /** Keys this build does not know, kept verbatim. */
    private final Map<String, Object> unknown = new LinkedHashMap<>();
    /** Bumped on every change (Economy, a vehicle bought); the save coalesces on it, the host sends on it. */
    private long revision;

    public PlayerProfile() {}

    public PlayerProfile(String playerId) { this.playerId = playerId == null ? "" : playerId; }

    public long revision() { return revision; }
    public void touch() { revision++; }

    /** A loan: owed to {@code lender}, {@code principal} dollars, due at {@code dueAtUnix} (0 = no due date). */
    public record Debt(String lender, long principal, long dueAtUnix) {}

    public long totalDebt() {
        long d = 0;
        for (Debt x : debts) d += x.principal();
        return d + Math.max(0, -balance);
    }

    public VehicleInstanceData vehicle(String instanceId) {
        for (VehicleInstanceData v : vehicles) if (v.instanceId.equals(instanceId)) return v;
        return null;
    }

    // ── the campaign checkpoint (CR4) ──

    /** Remember the profile as it is now: balance, debts, career, story, cars, unlocks. */
    public void takeCheckpoint() {
        Map<String, Object> m = toMap();
        m.remove("checkpoint_snapshot");
        m.remove("activity_checkpoint");
        checkpointSnapshot = m;
        checkpointSeq++;
        touch();
    }

    /** {@link #toMap} as it is SENT (MSG_PROFILE): without the checkpoint snapshot, which would double it. */
    public Map<String, Object> toWireMap() {
        Map<String, Object> m = toMap();
        m.remove("checkpoint_snapshot");
        return m;
    }

    public boolean hasCheckpoint() { return checkpointSnapshot != null; }

    /**
     * A game over: this profile goes back to its last campaign checkpoint -- the WORLD is not rolled back, and the
     * checkpoint itself stays (the next game over lands here again). False, changing nothing, when there is none.
     */
    public boolean rollbackToCheckpoint() {
        if (checkpointSnapshot == null) return false;
        Map<String, Object> keep = checkpointSnapshot;
        String id = playerId;
        long seq = checkpointSeq;
        copyFrom(fromMap(keep));
        playerId = id;
        checkpointSnapshot = keep;
        checkpointSeq = seq;
        activityCheckpoint = null;
        touch();
        return true;
    }

    // ── the file shape ──

    public Map<String, Object> toMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("version", VERSION);
        m.put("player_id", playerId);
        m.put("balance", balance);
        List<Object> ds = new ArrayList<>();
        for (Debt d : debts) {
            Map<String, Object> x = new LinkedHashMap<>();
            x.put("lender", d.lender());
            x.put("principal", d.principal());
            x.put("due_at", d.dueAtUnix());
            ds.add(x);
        }
        m.put("debts", ds);
        m.put("career", career.toMap());
        m.put("campaign", campaign.toMap());
        List<Object> vs = new ArrayList<>();
        for (VehicleInstanceData v : vehicles) vs.add(v.toMap());
        m.put("vehicles", vs);
        m.put("unlocks", new ArrayList<>(unlocks));
        if (activityCheckpoint != null) m.put("activity_checkpoint", new LinkedHashMap<>(activityCheckpoint));
        if (checkpointSnapshot != null) m.put("checkpoint_snapshot", new LinkedHashMap<>(checkpointSnapshot));
        if (checkpointSeq != 0) m.put("checkpoint_seq", checkpointSeq);
        for (Map.Entry<String, Object> e : unknown.entrySet()) m.putIfAbsent(e.getKey(), e.getValue());
        return m;
    }

    /** Read a (migrated) profile map; missing fields keep their defaults, unknown ones are kept. */
    public static PlayerProfile fromMap(Map<String, Object> m) {
        PlayerProfile p = new PlayerProfile();
        if (m == null) return p;
        for (Map.Entry<String, Object> e : m.entrySet()) {
            switch (e.getKey()) {
                case "version", "player_id", "balance", "debts", "career", "campaign", "vehicles", "unlocks",
                     "activity_checkpoint", "checkpoint_snapshot", "checkpoint_seq" -> { }
                default -> p.unknown.put(e.getKey(), e.getValue());
            }
        }
        p.playerId = Maps.str(m, "player_id", "");
        p.balance = Maps.lng(m, "balance", 0);
        for (Object o : Maps.list(m, "debts")) {
            Map<String, Object> d = Maps.map(o);
            if (d == null) continue;
            p.debts.add(new Debt(Maps.str(d, "lender", ""), Maps.lng(d, "principal", 0), Maps.lng(d, "due_at", 0)));
        }
        p.career.read(Maps.map(m.get("career")));
        p.campaign.read(Maps.map(m.get("campaign")));
        for (Object o : Maps.list(m, "vehicles")) {
            VehicleInstanceData v = VehicleInstanceData.fromMap(Maps.map(o));
            if (v != null) p.vehicles.add(v);
        }
        for (Object o : Maps.list(m, "unlocks")) if (o instanceof String s) p.unlocks.add(s);
        p.activityCheckpoint = Maps.map(m.get("activity_checkpoint"));
        p.checkpointSnapshot = Maps.map(m.get("checkpoint_snapshot"));
        p.checkpointSeq = Maps.lng(m, "checkpoint_seq", 0);
        return p;
    }

    /** Replace this profile's contents with {@code other}'s (a host's session copy arriving), keeping the object. */
    public void copyFrom(PlayerProfile other) {
        playerId = other.playerId;
        balance = other.balance;
        debts.clear();
        debts.addAll(other.debts);
        career.read(other.career.toMap());
        campaign.read(other.campaign.toMap());
        vehicles.clear();
        for (VehicleInstanceData v : other.vehicles) vehicles.add(VehicleInstanceData.fromMap(v.toMap()));
        unlocks.clear();
        unlocks.addAll(other.unlocks);
        activityCheckpoint = other.activityCheckpoint == null ? null : new LinkedHashMap<>(other.activityCheckpoint);
        // the snapshot does not travel: a copy that arrives without one keeps mine, and one whose checkpoint count
        // moved on (the host took a checkpoint of this very state) is the moment to take my own
        boolean moved = other.checkpointSeq > checkpointSeq;
        if (other.checkpointSnapshot != null) checkpointSnapshot = new LinkedHashMap<>(other.checkpointSnapshot);
        else if (moved) {
            Map<String, Object> now = toMap();
            now.remove("checkpoint_snapshot");
            now.remove("activity_checkpoint");
            checkpointSnapshot = now;
        }
        checkpointSeq = Math.max(checkpointSeq, other.checkpointSeq);
        unknown.clear();
        unknown.putAll(other.unknown);
        touch();
    }
}
