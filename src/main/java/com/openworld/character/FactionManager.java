package com.openworld.character;

import com.openworld.game.GameManager;
import com.openworld.net.NetworkManager;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;
import godot.global.GD;

import java.util.Map;

/**
 * Runtime faction relationship authority — registered as an AutoLoad singleton named
 * "FactionManager" (PLAN.md Part D / D3). Implements the long-promised "FactionRegistry lookup"
 * noted in {@link Faction}: it owns a {@link FactionTable} and answers {@link #areHostile} from it,
 * and lets missions flip relationships mid-game via {@link #setRelationship} (e.g. a previously-allied
 * gang turns hostile on betrayal).
 *
 * <p>{@link Faction#areHostile} delegates here once this AutoLoad registers itself (so every existing
 * call-site is a pure drop-in — no signature change). This class is the single owner of the hostility
 * rule: the relationship table is consulted first, and any pair the table omits resolves via the
 * inherent default baked into {@link #areHostile} (NEUTRAL is never hostile; same faction allied;
 * different factions hostile). There is no separate "legacy" rule to maintain.
 *
 * <p><b>Lifetime of runtime flips:</b> the live table is a <i>duplicate</i> of the on-disk
 * {@code DefaultFactions.tres} (so {@link #setRelationship} never mutates the shared cached resource).
 * Because this is an AutoLoad it survives {@code reloadCurrentScene}, so a flip persists across
 * scenes/missions for the whole process until {@link #reset()} restores the shipped defaults
 * (called on a full restart from {@code GameManager.restartLevel}). Scope a flip to a single mission
 * by calling {@link #reset()} at mission end.
 */
@Script(className = "FactionManager")
public class FactionManager extends Node {

    private static final String DEFAULT_TABLE_PATH =
            "res://src/main/resources/com/openworld/character/DefaultFactions.tres";

    /** The LIVE table every hostility question reads: a private copy of the active layer, plus runtime flips. */
    private FactionTable table;
    /**
     * Only the flips {@link #setRelationship} made on top of the active layer, keyed {@code "a>b"}.
     * The live table cannot answer "what did PLAY change" — it is a copy of a shipped/authored
     * {@code .tres} with the flips written into it — and that is the only half a save may carry (I7):
     * a slot that froze the shipped defaults would silently win over an edited preset on every later
     * launch. Cleared by {@link #rebuildLiveTable}, which is the documented "a layer change discards
     * runtime flips" rule, stated once.
     */
    private final java.util.LinkedHashMap<String, String> runtimeFlips = new java.util.LinkedHashMap<>();
    /**
     * The CAMPAIGN layer (PLAN.md 0.35 / CR3): relationships the story changed for good ("the police now hate
     * gang_a"), keyed {@code "a>b"}. Unlike {@link #runtimeFlips} they survive {@link #rebuildLiveTable} -- a region
     * change or a mission start / end used to discard them. Laid over the region / default layer on every rebuild;
     * an active MISSION table still wins (a mission's own sides are its business). Cleared only by {@link #reset}
     * (a new game / full restart) and replaced by a save load.
     */
    private final java.util.LinkedHashMap<String, String> campaign = new java.util.LinkedHashMap<>();
    /**
     * The ACTIVITY overlays (PLAN.md 2.1 / AR1): the rows each running activity asked for, by run. Laid over
     * everything else -- N activities at once, where the mission layer was one table swapped for the whole island --
     * and removed with their run. Rows are {factionA, factionB, relationship}, applied both ways. Host only:
     * hostility is decided where the AI is.
     */
    private final java.util.LinkedHashMap<String, java.util.List<String[]>> activityOverlays = new java.util.LinkedHashMap<>();
    /** Layer set by the nearest region (I4), or null for the shipped defaults. */
    private FactionTable regionTable;
    /** Layer set by the active mission (F2), or null. While set it wins over the region's. */
    private FactionTable missionTable;

    @Register
    @Override
    public void _ready() {
        rebuildLiveTable();
        // Route Faction.areHostile() through this manager. Done last so a half-built manager is
        // never the registry.
        Faction.setRegistry(this);
    }

    /**
     * Rebuild the live table from the highest layer present — mission, then region, then the shipped
     * {@code DefaultFactions.tres}. The chosen resource is {@code duplicate(true)}'d so later
     * {@link #setRelationship} edits stay on this manager's copy and never write back to the
     * engine-cached {@code .tres} (which would leak a betrayal into the next mission/launch). A layer
     * change therefore DISCARDS runtime flips, which is the per-mission scope the flips want.
     * Missing-preset case leaves {@code table} null → the inherent default rule.
     */
    private void rebuildLiveTable() {
        FactionTable source = missionTable != null ? missionTable : regionTable;
        if (source == null) {
            Object loaded = GD.load(DEFAULT_TABLE_PATH);
            if (loaded instanceof FactionTable t) {
                source = t;
            } else {
                GD.printErr("[FactionManager] could not load " + DEFAULT_TABLE_PATH
                        + " — using inherent default faction rules only");
            }
        }
        table = source != null ? (FactionTable) source.duplicate(true) : null;
        runtimeFlips.clear();
        if (missionTable == null) {
            for (Map.Entry<String, String> e : campaign.entrySet()) {
                int split = e.getKey().indexOf('>');
                if (table == null) table = new FactionTable();
                table.setRelationship(e.getKey().substring(0, split), e.getKey().substring(split + 1), e.getValue());
            }
        }
        for (java.util.List<String[]> rows : activityOverlays.values()) {
            for (String[] r : rows) {
                if (table == null) table = new FactionTable();
                table.setRelationship(r[0], r[1], r[2]);
                table.setRelationship(r[1], r[0], r[2]);
            }
        }
    }

    /** A layer change that KEEPS the runtime flips (an activity starting or ending is not a new mission table). */
    private void rebuildKeepingFlips() {
        java.util.LinkedHashMap<String, String> flips = new java.util.LinkedHashMap<>(runtimeFlips);
        rebuildLiveTable();
        for (Map.Entry<String, String> e : flips.entrySet()) {
            int split = e.getKey().indexOf('>');
            if (table == null) table = new FactionTable();
            table.setRelationship(e.getKey().substring(0, split), e.getKey().substring(split + 1), e.getValue());
            runtimeFlips.put(e.getKey(), e.getValue());
        }
    }

    /** Lay (or, with no rows, remove) one activity run's relationships over the live table. */
    public void setActivityOverlay(String runId, java.util.List<String[]> rows) {
        if (runId == null) return;
        if (rows == null || rows.isEmpty()) {
            if (activityOverlays.remove(runId) == null) return;
        } else {
            activityOverlays.put(runId, java.util.List.copyOf(rows));
        }
        rebuildKeepingFlips();
    }

    /** How many activity runs have an overlay now -- probe readout. */
    @Register
    public int activityOverlaysNow() { return activityOverlays.size(); }

    /** Restore the shipped defaults, discarding all runtime flips AND both layers. Call on full restart. */
    @Register
    public void reset() {
        regionTable = null;
        missionTable = null;
        campaign.clear();
        activityOverlays.clear();
        rebuildLiveTable();
    }

    /**
     * Install a region's faction relationships (PLAN.md I4 {@code RegionConfig.factionTable}). A null
     * argument restores the shipped defaults (a region with no custom rules), so leaving / entering a
     * plain region cleanly reverts to baseline. While a mission table is active the region layer is
     * remembered but does not replace it. Local per-peer (the same zone loads on every peer); runtime
     * {@link #setRelationship} flips still replicate as before.
     */
    @Register
    public void applyTable(FactionTable region) {
        regionTable = region;
        if (missionTable == null) rebuildLiveTable();
    }

    /**
     * Install the active mission's relationships (PLAN.md F2, {@code MissionInfo.factionTable}); null
     * ends the mission layer and falls back to the region's table or the defaults. Called by
     * {@code MissionManager} on start / complete / fail on the host, and by the mirrored mission world
     * events on a client.
     */
    @Register
    public void applyMissionTable(FactionTable mission) {
        if (mission == null && missionTable == null) return;
        missionTable = mission;
        rebuildLiveTable();
    }

    /**
     * {@code applyTable(null)} / {@code applyMissionTable(null)} for GDScript. Since godot-jvm rc3 the registrar
     * casts an Object argument non-null ({@code args[0] as FactionTable}), so a GDScript {@code null} throws a
     * NullPointerException before the method runs -- and {@code @Nullable} on the parameter is not read.
     */
    @Register
    public void clearRegionTable() {
        applyTable(null);
    }

    @Register
    public void clearMissionTable() {
        applyMissionTable(null);
    }

    /** Which layer the live table came from: "mission", "region" or "default" (probe/debug readout). */
    @Register
    public String activeLayerNow() {
        return missionTable != null ? "mission" : regionTable != null ? "region" : "default";
    }

    /** The live table's relationship string for a pair ("" = none: the inherent default applies). */
    public String relationship(String a, String b) {
        FactionTable t = table;
        if (t == null) return "";
        String r = t.relationship(a, b);
        return r == null ? "" : r;
    }

    /** {@link #areHostile} for GDScript probes. */
    @Register
    public boolean hostileNow(String a, String b) {
        return areHostile(a, b);
    }

    @Register
    @Override
    public void _exitTree() {
        // Drop the static back-reference and the resource handle on shutdown (leak discipline —
        // a FactionTable is a Godot Resource; see CLAUDE.md "Known Quirks").
        Faction.clearRegistry(this);
        table = null;
    }

    /**
     * The hostility decision, over the live table. The rule itself — NEUTRAL never hostile, exact pair,
     * wildcard row, same-allied/different-hostile default — is {@link FactionRules#areHostile}.
     */
    public boolean areHostile(String a, String b) {
        FactionTable t = table;
        return FactionRules.areHostile(a, b, t != null ? t::row : k -> null);
    }

    /**
     * Flip a relationship at runtime (creates the table if a preset wasn't loaded). On a networked
     * host this also replicates the flip to every client via the world-event seam (D3 networked);
     * a client applying an inbound flip calls this too, but the {@code isServer()} gate stops it
     * echoing back.
     */
    public void setRelationship(String a, String b, String rel) {
        if (table == null) table = new FactionTable();
        table.setRelationship(a, b, rel);
        runtimeFlips.put(FactionRules.key(a, b), rel);
        Node netNode = getNodeOrNull("/root/NetworkManager");
        if (netNode instanceof NetworkManager net && net.isNetworked() && net.isServer()) {
            net.broadcastWorldEvent(GameManager.WORLD_EVENT_FACTION_RELATIONSHIP, a, 0f,
                    java.util.List.of(b, rel));
        }
    }

    /**
     * {@link #setRelationship} for probes and the debug console. Deliberately NOT {@code @Register}
     * on {@code setRelationship} itself: godot-jvm merges a JavaBean accessor with its field into one
     * property (CLAUDE.md "Known Quirks"), and a registered {@code setX} with no matching getter is
     * the shape whose generated registrar does not compile.
     */
    @Register
    public void flipRelationship(String a, String b, String rel) {
        setRelationship(a, b, rel);
    }

    /**
     * Change a relationship FOR THE CAMPAIGN (PLAN.md 0.35): it survives every region change and mission start /
     * end, and the save carries it. Applied to the live table now unless a mission table is active (then it lands
     * when the mission ends). On a networked host it replicates through the faction world event with a
     * {@code "campaign"} third argument, so a client keeps it across its own (local) region rebuilds too.
     */
    public void setCampaignRelationship(String a, String b, String rel) {
        if (a == null || b == null || rel == null || a.isEmpty() || b.isEmpty()) return;
        campaign.put(FactionRules.key(a, b), rel);
        if (missionTable == null) {
            if (table == null) table = new FactionTable();
            table.setRelationship(a, b, rel);
        }
        Node netNode = getNodeOrNull("/root/NetworkManager");
        if (netNode instanceof NetworkManager net && net.isNetworked() && net.isServer()) {
            net.broadcastWorldEvent(GameManager.WORLD_EVENT_FACTION_RELATIONSHIP, a, 0f,
                    java.util.List.of(b, rel, CAMPAIGN_ARG));
        }
    }

    /** The faction world event's third argument that marks a campaign relationship. */
    public static final String CAMPAIGN_ARG = "campaign";

    /** {@link #setCampaignRelationship} for probes and the console (see {@link #flipRelationship} for why). */
    @Register
    public void flipCampaignNow(String a, String b, String rel) {
        setCampaignRelationship(a, b, rel);
    }

    /** The campaign layer as {factionA, factionB, relationship} triples (save and late-join baseline). */
    public java.util.List<String[]> getCampaignRelationships() {
        java.util.List<String[]> out = new java.util.ArrayList<>();
        for (Map.Entry<String, String> e : campaign.entrySet()) {
            int split = e.getKey().indexOf('>');
            out.add(new String[] { e.getKey().substring(0, split), e.getKey().substring(split + 1), e.getValue() });
        }
        return out;
    }

    /** All active relationship flips as {factionA, factionB, relationship} triples — for the late-join net baseline. */
    public java.util.List<String[]> getActiveRelationships() {
        return table != null ? table.entries() : java.util.List.of();
    }

    /**
     * Only what RUNTIME changed — {@link #setRelationship} calls that are still live, as
     * {factionA, factionB, relationship} triples. This is what a save carries (I7); the rest of the
     * live table belongs to the shipped/authored preset and is loaded fresh every launch.
     */
    public java.util.List<String[]> getRuntimeOverrides() {
        java.util.List<String[]> out = new java.util.ArrayList<>();
        for (Map.Entry<String, String> e : runtimeFlips.entrySet()) {
            int split = e.getKey().indexOf('>');
            if (split <= 0) continue;
            out.add(new String[] { e.getKey().substring(0, split), e.getKey().substring(split + 1),
                    e.getValue() });
        }
        return out;
    }
}
