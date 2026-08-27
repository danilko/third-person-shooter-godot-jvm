package com.openworld.character;

import com.openworld.game.GameManager;
import com.openworld.net.NetworkManager;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;
import godot.global.GD;

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

    private FactionTable table;

    @Register
    @Override
    public void _ready() {
        loadDefaultTable();
        // Route Faction.areHostile() through this manager. Done last so a half-built manager is
        // never the registry.
        Faction.setRegistry(this);
    }

    /**
     * Load a fresh, private copy of the shipped relationship table. The on-disk resource is
     * {@code duplicate(true)}'d so later {@link #setRelationship} edits stay on this manager's copy
     * and never write back to the engine-cached {@code .tres} (which would leak a betrayal into the
     * next mission/launch). Missing-preset case leaves {@code table} null → the inherent default rule.
     */
    private void loadDefaultTable() {
        Object loaded = GD.load(DEFAULT_TABLE_PATH);
        if (loaded instanceof FactionTable t) {
            table = (FactionTable) t.duplicate(true);
        } else {
            table = null;
            GD.printErr("[FactionManager] could not load " + DEFAULT_TABLE_PATH
                    + " — using inherent default faction rules only");
        }
    }

    /** Restore the shipped defaults, discarding all runtime flips. Call on full restart / mission scope reset. */
    public void reset() {
        loadDefaultTable();
    }

    /**
     * Install a region's faction relationships (PLAN.md I4 {@code RegionConfig.factionTable}). Like
     * {@link #loadDefaultTable}, the table is <b>duplicated</b> so runtime flips (betrayals) never write
     * back into the authored {@code .tres}. A null argument restores the shipped defaults (a region with
     * no custom rules), so leaving / entering a plain region cleanly reverts to baseline. Local per-peer
     * (the same zone loads on every peer); runtime {@link #setRelationship} flips still replicate as before.
     */
    public void applyTable(FactionTable region) {
        if (region != null) table = (FactionTable) region.duplicate(true);
        else loadDefaultTable();
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
     * The single hostility rule. NEUTRAL is never hostile (a faction named "neutral" stays out of
     * all fights); then an explicit table entry wins (HOSTILE/DESPISE → hostile, FRIENDLY/NEUTRAL →
     * not); finally, any unconfigured pair defaults to "same faction allied, different factions
     * hostile" — which reproduces the previous behaviour for the stock PLAYER/ENEMY/NEUTRAL set.
     */
    public boolean areHostile(String a, String b) {
        if (a == null || b == null) return false;
        if (Faction.NEUTRAL.equals(a) || Faction.NEUTRAL.equals(b)) return false;
        if (table != null) {
            String rel = table.relationship(a, b);
            if (rel != null) {
                return FactionTable.HOSTILE.equals(rel) || FactionTable.DESPISE.equals(rel);
            }
        }
        return !a.equals(b);
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
        Node netNode = getNodeOrNull("/root/NetworkManager");
        if (netNode instanceof NetworkManager net && net.isNetworked() && net.isServer()) {
            net.broadcastWorldEvent(GameManager.WORLD_EVENT_FACTION_RELATIONSHIP, a, 0f,
                    java.util.List.of(b, rel));
        }
    }

    /** All active relationship flips as {factionA, factionB, relationship} triples — for the late-join net baseline. */
    public java.util.List<String[]> getActiveRelationships() {
        return table != null ? table.entries() : java.util.List.of();
    }
}
