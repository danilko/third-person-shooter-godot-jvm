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
    public static final int VERSION = 1;

    public String playerId = "";
    public long balance;
    public final List<Debt> debts = new ArrayList<>();
    public final CareerState career = new CareerState();
    public final CampaignState campaign = new CampaignState();
    public final List<VehicleInstanceData> vehicles = new ArrayList<>();
    public final Set<String> unlocks = new LinkedHashSet<>();
    /** Keys this build does not know, kept verbatim. */
    private final Map<String, Object> unknown = new LinkedHashMap<>();
    /** Bumped on every change (Economy, a vehicle bought); the save coalesces on it, the host sends on it. */
    private long revision;

    public PlayerProfile() {}

    public PlayerProfile(String playerId) { this.playerId = playerId == null ? "" : playerId; }

    public long revision() { return revision; }
    public void touch() { revision++; }

    /** A loan: owed to {@code lender}, {@code principal} yen, due at {@code dueAtUnix} (0 = no due date). */
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
        for (Map.Entry<String, Object> e : unknown.entrySet()) m.putIfAbsent(e.getKey(), e.getValue());
        return m;
    }

    /** Read a (migrated) profile map; missing fields keep their defaults, unknown ones are kept. */
    public static PlayerProfile fromMap(Map<String, Object> m) {
        PlayerProfile p = new PlayerProfile();
        if (m == null) return p;
        for (Map.Entry<String, Object> e : m.entrySet()) {
            switch (e.getKey()) {
                case "version", "player_id", "balance", "debts", "career", "campaign", "vehicles", "unlocks" -> { }
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
        unknown.clear();
        unknown.putAll(other.unknown);
        touch();
    }
}
