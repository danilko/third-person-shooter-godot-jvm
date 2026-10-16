package com.openworld.game;

import com.openworld.character.FactionManager;
import com.openworld.character.Health;
import com.openworld.character.Player;
import com.openworld.game.mission.MissionDirector;
import com.openworld.game.mission.MissionInfo;
import com.openworld.game.mission.MissionManager;
import com.openworld.net.NetMessageCodec.InventorySlotEntry;
import com.openworld.net.NetworkManager;
import com.openworld.net.NetStats;
import com.openworld.net.session.PersistentPlayerId;
import com.openworld.weapon.WeaponController;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.DirAccess;
import godot.api.FileAccess;
import godot.api.JSON;
import godot.api.Node;
import godot.api.Object;
import godot.core.Dictionary;
import godot.core.MethodCallable;
import godot.core.VariantArray;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Campaign persistence — registered as an AutoLoad named "SaveSystem" (PLAN.md Part I / I7).
 * One JSON document per slot under {@link #saveDir}, written and read with Godot's own
 * {@code FileAccess}, holding four things and deliberately not a fifth:
 *
 * <ol>
 *   <li><b>The campaign graph</b> ({@link MissionDirector}) — the achieved
 *       {@code (missionId, outcomeVariant)} membership set, the completed missions, the sticky
 *       unlocked set, the granted unique items and <b>the fired-beat log</b>.</li>
 *   <li><b>The faction relationship flips</b> ({@link FactionManager#getActiveRelationships}).</li>
 *   <li><b>Which mission was running</b> — its id and its {@code .tres} path.</li>
 *   <li><b>Each player</b> — position, facing, health, active slot and the slot manifest
 *       ({@code weaponId}, scene, magazine, reserve).</li>
 * </ol>
 *
 * <h3>Four rules, each of which is the reason a piece is in or out</h3>
 *
 * <p><b>Progress is saved; AUTHORING is not.</b> {@code MissionDirector.declareUnlock} rows say which
 * variants open which mission — that is content, re-declared by the same Java every launch, and a
 * saved copy of it would be a second owner that goes stale the day the campaign is edited. What is
 * saved is what only the player's play produced: the achieved set, the unlocked set and the rest.
 *
 * <p><b>The fired-beat log is campaign state, not a debug counter.</b> F3's {@code ZoneTrigger}
 * decides "has this already fired" by asking {@link MissionDirector#beatFireCount}, precisely so a
 * trigger inside a streamed zone cannot re-arm when the zone reloads. A save that omitted the log
 * would re-arm every one-shot trigger in the world on load — the ambush you already sprang, waiting
 * for you again — with nothing on screen to say why. {@link #saveFiredBeats} is the control knob the
 * gate measures that with.
 *
 * <p><b>An interrupted mission RESTARTS; it does not resume mid-flight.</b> AI bodies are not saved
 * (a streamed world respawns its crowds), so a restored "3 of 7 enemies left" counter would be
 * counted against a fresh crowd of 7 — a number that is simply untrue. So the slot records which
 * mission was active and {@link #loadSlot} starts it again through
 * {@link MissionDirector#startMissionFromPath}, which re-counts from the live world. That is also
 * what GTA does with a save taken during a mission. A mission built in code or embedded as a
 * sub-resource has no loadable path (the same limit {@code MissionManager} already documents for its
 * client mirror), so it is recorded by id and reported as unresumable rather than half-restored.
 *
 * <h3>Save v2 (PLAN.md 1.4: AR2 + CR5)</h3>
 * There are now TWO files. This slot is the WORLD's (the host's: campaign graph, factions, mission, bodies); what a
 * PLAYER owns -- money, debts, career / campaign data, owned cars, unlocks -- is their {@code PlayerProfile}, which
 * every peer keeps in its own {@code user://profile.json} ({@code game.profile.Profiles}; in co-op the host holds a
 * session copy sent at join, MSG_PROFILE, and sends it back when it changes). Both files are written crash-safe
 * ({@code game.profile.SafeSave}: .tmp -> check -> rename, .bak1 / .bak2, a checksum line; a bad file falls back to
 * the newest good backup) and an older file is MIGRATED ({@code game.profile.SaveMigrations}), not refused. Autosave
 * is coalesced: a beat writes only when the last write is {@link #autosaveMinSeconds} old (else the next window does),
 * a mission end always writes, and quitting / Quit to title flushes ({@link #flushAll}). A run under {@code --script}
 * (a probe) uses {@code user://test/} for both, so no probe ever touches the player's saves.
 *
 * <p><b>The host's WORLD save is canonical and needs no new message.</b> {@link #saveSlot} refuses on a
 * client. A load on the host reaches every client through seams that already exist: the faction
 * flips ride {@code FactionManager.setRelationship}'s world event, the mission restart rides
 * {@code MissionManager}'s {@code WORLD_EVENT_MISSION_STARTED}, and inventory converges through the
 * periodic {@code MSG_INVENTORY} manifest. Adding an RPC here would be a second way to say something
 * the wire already says.
 *
 * <h3>The player key</h3>
 * A record is keyed by the id that is stable ACROSS LAUNCHES, which is not the same field in both
 * cases: a remote player's {@code characterId} IS their {@code PersistentPlayerId} (GameManager makes
 * it so on first join), while a locally-owned body carries a per-launch UUID — so the local body is
 * keyed by {@link PersistentPlayerId#getOrCreate()}, the id this install would identify as if it were
 * the client. One rule, both cases, and the key survives host/client role swaps.
 */
@Script(className = "SaveSystem")
public class SaveSystem extends Node {

    /** The document's shape. An OLDER slot is migrated (game.profile.SaveMigrations.WORLD), a newer one refused. */
    public static final int SCHEMA = com.openworld.game.profile.SaveMigrations.WORLD_VERSION;

    /** Coalesced autosave (CR5): at most one write per this many seconds for beats; a mission end always writes. */
    @Export public double autosaveMinSeconds = 30.0;
    public double getAutosaveMinSeconds() { return autosaveMinSeconds; }
    public void setAutosaveMinSeconds(double v) { autosaveMinSeconds = v; }
    private boolean worldDirty;
    private long garageScene = -1;
    private double sinceWorldWrite = 1e9, sinceProfileWrite = 1e9;
    private int profileWrites;

    private static SaveSystem instance;

    public static SaveSystem get() { return instance; }

    /** Where slots live. {@code user://} so it is per-install and never inside the repo. */
    @Export public String saveDir = "user://saves";

    /** Autosave on every story beat and every mission completion (the F3 hook I7 asks for). */
    @Export public boolean autosaveEnabled = true;

    /** The slot autosave writes. Kept apart from the numbered slots a player chooses. */
    @Export public int autosaveSlot = 0;

    @Export public boolean debugLog = true;

    /**
     * CONTROL KNOB, always on. Off, the fired-beat log is left out of the document — the naive "only
     * missions and variants are progress" save. The gate turns it off to measure what that costs:
     * every one-shot {@code ZoneTrigger} in the world re-arms after a load.
     */
    @Visible public boolean saveFiredBeats = true;

    /** Records whose player body was not live when the slot was loaded — applied as bodies appear. */
    private final Map<String, PlayerRecord> pendingPlayers = new LinkedHashMap<>();
    /** The ledger's revision as last written (or loaded): it differs = there is something to save. */
    private long ledgerSaved;

    private int saveCount = 0;
    private int loadCount = 0;
    private String lastMessage = "";

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @Register
    @Override
    public void _ready() {
        instance = this;
        // The PLAYER's own file (AR2): this install's profile. A run under --script (a probe, never the shipped game)
        // gets its own file so it never touches the player's money.
        boolean harness = false;
        for (String a : godot.api.OS.getCmdlineArgs()) if ("--script".equals(a) || "-s".equals(a)) harness = true;
        java.nio.file.Path profile = java.nio.file.Path.of(godot.api.ProjectSettings.globalizePath(
                harness ? "user://test/profile.json" : "user://profile.json"));
        // and starts FRESH every run, so one probe's money never leaks into the next probe's exact checks
        // (persistence is gated inside one run: probe_profile reloads)
        if (harness) {
            for (String suffix : new String[] {"", ".bak1", ".bak2", ".tmp"}) {
                try { java.nio.file.Files.deleteIfExists(java.nio.file.Path.of(profile + suffix)); }
                catch (java.io.IOException ignored) { }
            }
        }
        com.openworld.game.profile.Profiles.configure(profile,
                harness ? 0 : com.openworld.game.profile.EconomyTable.get().startingCash);
        com.openworld.game.profile.Profiles.local();
        // the world slots too: a probe deleting "slot 0" (probe_save_system does) must never be the player's autosave
        if (harness && "user://saves".equals(saveDir)) saveDir = "user://test/saves";
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) {
            bus.missionBeatTriggered.connectUnsafe(
                    MethodCallable.createUnsafe(this, "onBeatTriggered"), godot.core.ConnectFlags.DEFAULT);
            bus.missionCompleted.connectUnsafe(
                    MethodCallable.createUnsafe(this, "onMissionCompleted"), godot.core.ConnectFlags.DEFAULT);
        }
    }

    @Register
    @Override
    public void _exitTree() {
        // Leak discipline (CLAUDE.md "Known Quirks"): the static back-reference and every held record.
        pendingPlayers.clear();
        com.openworld.game.profile.Profiles.saveIfDirty();
        com.openworld.game.profile.Profiles.clear();
        if (instance == this) instance = null;
    }

    @Register
    @Override
    public void _process(double delta) {
        if (!pendingPlayers.isEmpty()) applyPendingPlayers();
        // F4: the safe house's garage, derived once per world from the starting car (Garage.ensureHome)
        Node scene = getTree() != null ? getTree().getCurrentScene() : null;
        if (scene != null && scene.getInstanceId() != garageScene) {
            garageScene = scene.getInstanceId();
            com.openworld.world.Garage.ensureHome(scene);
            com.openworld.world.HomeBikes.ensure(scene);   // 3.1b: a scooter beside the starting car (after the bay)
        }
        sinceWorldWrite += delta;
        sinceProfileWrite += delta;
        // a ledger change is world state to save (a dead story character, a world flag): coalesced like a beat
        if (WorldLedger.get().revision() != ledgerSaved) worldDirty = true;
        if (worldDirty && sinceWorldWrite >= autosaveMinSeconds) autosaveNow("coalesced");
        if (com.openworld.game.profile.Profiles.dirty() && sinceProfileWrite >= autosaveMinSeconds) flushProfile();
    }

    /** Write the player's profile now if it changed (money, a car). Every peer writes its own, a client included. */
    @Register
    public boolean flushProfile() {
        sinceProfileWrite = 0;
        boolean wrote = com.openworld.game.profile.Profiles.saveIfDirty();
        if (wrote) profileWrites++;
        return wrote;
    }

    /** Quit / title: write whatever is pending (the coalesced autosave and the profile). */
    @Register
    public void flushAll() {
        if (worldDirty) autosaveNow("flush");
        flushProfile();
    }

    // ── Save ──────────────────────────────────────────────────────────────────

    /**
     * Write every slot-worthy piece of state to {@code slot}. Refused on a networked client: the
     * host's save is the canonical one, and a client writing its own would be a second campaign
     * history that nothing reconciles.
     */
    @Register
    public boolean saveSlot(int slot) {
        if (isNetworkedClient()) {
            NetStats.increment("save_refused_client");
            return fail("a client does not write the campaign save — the host's is canonical");
        }
        String dir = saveDir;
        if (DirAccess.makeDirRecursiveAbsolute(dir) != godot.core.Error.OK
                && !DirAccess.dirExistsAbsolute(dir)) {
            return fail("could not create '" + dir + "'");
        }
        String path = slotPath(slot);
        // CR5: .tmp -> checked -> rename, the old file kept as .bak1 / .bak2, a checksum line on top
        if (!com.openworld.game.profile.SafeSave.write(globalPath(path), document()))
            return fail("could not write '" + path + "'");
        saveCount++;
        if (debugLog) GD.print("SaveSystem: wrote " + path);
        lastMessage = "saved " + path;
        return true;
    }

    /** The whole document, composed here so the file's shape has exactly one owner. */
    private String document() {
        Json doc = new Json().begin();
        doc.num("schema", SCHEMA);
        doc.num("saved_at_unix", (double) (System.currentTimeMillis() / 1000L));
        doc.str("scene", currentScenePath());

        MissionDirector director = MissionDirector.get();
        doc.key("campaign").begin();
        if (director != null) {
            doc.strings("achieved", director.achievedVariantKeys());
            doc.strings("completed", director.completedMissionIds());
            doc.strings("unlocked", director.unlockedMissionIds());
            doc.strings("granted_unique", director.grantedUniqueItems());
            // See the class note: without this every one-shot ZoneTrigger re-arms on load.
            doc.strings("fired_beats", saveFiredBeats ? director.firedBeatLog() : List.of());
        }
        doc.end();

        doc.key("factions").beginArray();
        FactionManager factions = factionManager();
        if (factions != null) {
            for (String[] rel : factions.getRuntimeOverrides()) {
                if (rel == null || rel.length < 3) continue;
                doc.beginArrayItem().begin();
                doc.str("a", rel[0]);
                doc.str("b", rel[1]);
                doc.str("rel", rel[2]);
                doc.end();
            }
        }
        doc.endArray();

        // the campaign layer (PLAN.md 0.35): story relationships that survive regions and missions
        doc.key("campaign_factions").beginArray();
        if (factions != null) {
            for (String[] rel : factions.getCampaignRelationships()) {
                doc.beginArrayItem().begin();
                doc.str("a", rel[0]);
                doc.str("b", rel[1]);
                doc.str("rel", rel[2]);
                doc.end();
            }
        }
        doc.endArray();

        // the world's ledger (PLAN.md 2.0 / CR3): world flags, dead story characters, place overrides
        doc.raw("ledger", com.openworld.util.MiniJson.write(WorldLedger.get().toMap()));
        ledgerSaved = WorldLedger.get().revision();

        doc.key("mission").begin();
        MissionManager missions = missionManager();
        MissionInfo active = missions != null && missions.isActive() ? missions.getActiveMission() : null;
        doc.bool("active", active != null);
        doc.str("id", active != null ? active.missionId : "");
        doc.str("path", active != null ? loadablePath(active) : "");
        doc.end();

        doc.key("players").beginArray();
        for (Player p : PlayerRegistry.getPlayers()) {
            if (p == null || !GD.isInstanceValid(p)) continue;
            String key = playerKey(p);
            if (key.isEmpty()) continue;
            doc.beginArrayItem().begin();
            doc.str("key", key);
            doc.vec3("position", p.getGlobalPosition());
            doc.num("yaw", p.getRotation().getY());
            Node healthNode = p.getNodeOrNull("Health");
            doc.num("health", healthNode instanceof Health h ? h.getCurrentHealth() : -1.0);
            WeaponController wc = weaponControllerOf(p);
            doc.num("active_slot", wc != null ? wc.getReplicatedActiveSlot() : 0);
            doc.key("slots").beginArray();
            if (wc != null) {
                for (InventorySlotEntry e : wc.buildInventoryEntries()) {
                    doc.beginArrayItem().begin();
                    doc.num("slot", e.slot());
                    doc.str("weapon_id", e.weaponId());
                    doc.str("scene", e.scenePath());
                    doc.str("pickup_id", e.pickupId());
                    doc.num("magazine", e.magazine());
                    doc.num("reserve", e.reserve());
                    doc.end();
                }
            }
            doc.endArray();
            doc.end();
        }
        doc.endArray();
        return doc.end().toString();
    }

    // ── Load ──────────────────────────────────────────────────────────────────

    /**
     * Restore {@code slot} onto the world as it stands. Player records whose body is not live yet are
     * held and applied as those bodies appear ({@link #_process}), so loading before or while a scene
     * comes up works, and in co-op a client that joins after the load still gets its own record.
     */
    @Register
    public boolean loadSlot(int slot) {
        String path = slotPath(slot);
        // the file, else its newest good backup (a torn write / a bad checksum falls back -- CR5)
        com.openworld.game.profile.SafeSave.Read read = com.openworld.game.profile.SafeSave.read(globalPath(path));
        if (read == null) return fail("no readable save at '" + path + "'");
        java.util.Map<String, java.lang.Object> migrated;
        try {
            migrated = com.openworld.game.profile.SaveMigrations.migrate(
                    com.openworld.game.profile.Maps.map(com.openworld.util.MiniJson.parse(read.payload())),
                    "schema", com.openworld.game.profile.SaveMigrations.WORLD);
        } catch (IllegalArgumentException e) {
            return fail("'" + path + "' is not JSON: " + e.getMessage());
        }
        if (migrated == null) return fail("'" + path + "' is from a newer build (this one reads up to schema " + SCHEMA + ")");
        lastReadFrom = read.from();
        // the restore below reads Godot Dictionaries; the migrated tree goes back through Godot's parser once
        java.lang.Object parsed = JSON.parseString(com.openworld.util.MiniJson.write(migrated));
        if (!(parsed instanceof Dictionary<?, ?> doc)) return fail("'" + path + "' is not a JSON object");

        String savedScene = str(doc, "scene", "");
        if (debugLog && !savedScene.isEmpty() && !savedScene.equals(currentScenePath())) {
            GD.print("SaveSystem: slot was taken in '" + savedScene + "', loading into '"
                    + currentScenePath() + "'");
        }

        // a load REPLACES the world: whatever activity was running in the one before it is over (its checkpoint, in
        // the owner's profile, is what a retry starts from -- PLAN.md 2.1 / CR5)
        com.openworld.game.activity.ActivityRuntime activities = com.openworld.game.activity.ActivityRuntime.get();
        if (activities != null) activities.director().abortAll("a save was loaded");
        // the ledger first: what spawns while the rest restores must already know who is dead (an old slot has none)
        WorldLedger.replace(WorldLedger.fromMap(com.openworld.game.profile.Maps.map(migrated.get("ledger"))));
        ledgerSaved = WorldLedger.get().revision();
        MissionDirector dir = MissionDirector.get();
        if (dir != null) dir.removeDeadStoryCharacters(WorldLedger.get()::isDead);
        restoreCampaign(doc);
        restoreFactions(doc);
        restorePlayers(doc);
        restoreMission(doc);

        loadCount++;
        if (debugLog) GD.print("SaveSystem: loaded " + path);
        lastMessage = "loaded " + path;
        return true;
    }

    private void restoreCampaign(Dictionary<?, ?> doc) {
        MissionDirector director = MissionDirector.get();
        if (director == null || !(doc.get("campaign") instanceof Dictionary<?, ?> c)) return;
        director.restoreCampaign(strings(c, "achieved"), strings(c, "completed"),
                strings(c, "unlocked"), strings(c, "granted_unique"), strings(c, "fired_beats"));
    }

    private void restoreFactions(Dictionary<?, ?> doc) {
        FactionManager factions = factionManager();
        if (factions == null) return;
        // A load REPLACES: reset first, or a flip the slot does not carry survives from this session.
        factions.reset();
        if (doc.get("campaign_factions") instanceof VariantArray<?> camp) {
            for (java.lang.Object o : camp) {
                if (!(o instanceof Dictionary<?, ?> d)) continue;
                String a = str(d, "a", ""), b = str(d, "b", ""), rel = str(d, "rel", "");
                if (!a.isEmpty() && !b.isEmpty() && !rel.isEmpty()) factions.setCampaignRelationship(a, b, rel);
            }
        }
        if (!(doc.get("factions") instanceof VariantArray<?> arr)) return;
        for (java.lang.Object o : arr) {
            if (!(o instanceof Dictionary<?, ?> d)) continue;
            String a = str(d, "a", ""), b = str(d, "b", ""), rel = str(d, "rel", "");
            if (a.isEmpty() || b.isEmpty() || rel.isEmpty()) continue;
            // Replicates to every client through the world-event seam setRelationship already owns.
            factions.setRelationship(a, b, rel);
        }
    }

    private void restoreMission(Dictionary<?, ?> doc) {
        if (!(doc.get("mission") instanceof Dictionary<?, ?> m) || !bool(m, "active", false)) return;
        String path = str(m, "path", "");
        String id = str(m, "id", "");
        if (path.isEmpty()) {
            GD.print("SaveSystem: '" + id + "' was running but has no loadable .tres path"
                    + " — not restarted (a mission built in code cannot be restored)");
            return;
        }
        MissionDirector director = MissionDirector.get();
        // Through the DIRECTOR, not MissionManager: the unlock predicate still decides whether the
        // mission may run, so a save cannot smuggle a locked mission back into the world.
        boolean started = director != null && director.startMissionFromPath(path);
        if (debugLog) {
            GD.print("SaveSystem: mission '" + id + "' " + (started ? "restarted" : "refused")
                    + " (it restarts, it does not resume — see the class note)");
        }
    }

    private void restorePlayers(Dictionary<?, ?> doc) {
        pendingPlayers.clear();
        if (!(doc.get("players") instanceof VariantArray<?> arr)) return;
        for (java.lang.Object o : arr) {
            if (!(o instanceof Dictionary<?, ?> d)) continue;
            PlayerRecord rec = PlayerRecord.from(d);
            if (rec != null) pendingPlayers.put(rec.key, rec);
        }
        applyPendingPlayers();
    }

    /** Hand each held record to its body if that body is live; keep the rest for a later frame. */
    private void applyPendingPlayers() {
        if (pendingPlayers.isEmpty()) return;
        List<String> applied = null;
        for (Player p : PlayerRegistry.getPlayers()) {
            if (p == null || !GD.isInstanceValid(p)) continue;
            PlayerRecord rec = pendingPlayers.get(playerKey(p));
            if (rec == null) continue;
            apply(rec, p);
            if (applied == null) applied = new ArrayList<>();
            applied.add(rec.key);
        }
        if (applied != null) for (String key : applied) pendingPlayers.remove(key);
    }

    private void apply(PlayerRecord rec, Player p) {
        p.setGlobalPosition(rec.position);
        p.setRotation(new Vector3(0.0, rec.yaw, 0.0));
        if (p.getNodeOrNull("Health") instanceof Health h && rec.health > 0.0f) {
            // applyReplicatedHealth is the "set the number, fire no damage event" path — which is
            // exactly what a restore is. A save taken while dead is not resurrected into a corpse:
            // a non-positive value is left alone rather than written.
            h.applyReplicatedHealth(rec.health);
        }
        WeaponController wc = weaponControllerOf(p);
        if (wc != null) {
            // addOnly=false: a restore is a full reconcile. The owned-body guard the network path
            // needs exists because a lag-stale manifest must not fight live input; a slot document
            // read off disk has nothing to race.
            wc.applyReplicatedInventory(rec.slots, false);
            if (rec.activeSlot > 0) wc.onSetWeapon(rec.activeSlot);
        }
        if (debugLog) {
            GD.print("SaveSystem: restored player '" + rec.key + "' — " + rec.slots.size()
                    + " slot(s), health " + rec.health);
        }
    }

    // ── Slots ─────────────────────────────────────────────────────────────────

    @Register
    public String slotPath(int slot) {
        return saveDir + (saveDir.endsWith("/") ? "" : "/") + "slot" + slot + ".json";
    }

    @Register
    public boolean hasSlot(int slot) { return com.openworld.game.profile.SafeSave.exists(globalPath(slotPath(slot))); }

    /** Deletes the slot AND its backups (a deleted slot must not come back from its .bak1). */
    @Register
    public boolean deleteSlot(int slot) {
        if (!hasSlot(slot)) return false;
        boolean ok = true;
        for (String suffix : new String[] {"", ".bak1", ".bak2", ".tmp"}) {
            java.nio.file.Path p = java.nio.file.Path.of(globalPath(slotPath(slot)) + suffix);
            try { java.nio.file.Files.deleteIfExists(p); } catch (java.io.IOException e) { ok = false; }
        }
        return ok;
    }

    private static java.nio.file.Path globalPath(String resPath) {
        return java.nio.file.Path.of(godot.api.ProjectSettings.globalizePath(resPath));
    }

    private String lastReadFrom = "";

    // ── Autosave ──────────────────────────────────────────────────────────────

    /** I7's "autosave fires on mission-beat completion" hook — the F3 beat, now that it exists. */
    /** A beat: written now if the last write is older than {@link #autosaveMinSeconds}, else coalesced (CR5: a run
     *  of beats rewrote slot 0 once per beat, and a crash mid-write lost the only autosave). */
    @Register
    public void onBeatTriggered(String beatId) {
        if (sinceWorldWrite >= autosaveMinSeconds) autosaveNow("beat " + beatId);
        else worldDirty = true;
    }

    /** A mission end is a CHECKPOINT: always written, with the profile. */
    @Register
    public void onMissionCompleted(String missionId, String winningFaction, String outcomeVariant) {
        autosaveNow("mission " + missionId);
        flushProfile();
    }

    private void autosaveNow(String why) {
        worldDirty = false;
        if (!autosaveEnabled || isNetworkedClient()) {
            ledgerSaved = WorldLedger.get().revision();   // nothing will be written: do not ask again every frame
            return;
        }
        sinceWorldWrite = 0;
        if (saveSlot(autosaveSlot) && debugLog) GD.print("SaveSystem: autosaved after " + why);
    }

    // ── Probe / console readouts ──────────────────────────────────────────────

    // the world's ledger, for probes and the console (tools/godot/probe_world_ledger.gd)
    @Register public boolean ledgerSetFlagNow(String id, String value) {
        return value == null || value.isEmpty() ? WorldLedger.get().clearFlag(id) : WorldLedger.get().setFlag(id, value);
    }
    @Register public String ledgerFlagNow(String id) { return WorldLedger.get().flag(id, ""); }
    @Register public boolean ledgerDeadNow(String storyId) { return WorldLedger.get().isDead(storyId); }
    @Register public boolean ledgerMarkDeadNow(String storyId) { return WorldLedger.get().markDead(storyId); }
    @Register public boolean ledgerSetPlaceNow(String placeId, String owner, String state) {
        return WorldLedger.get().setPlace(placeId, owner, state);
    }
    @Register public String ledgerOwnerNow(String placeId, String generated) { return WorldLedger.get().ownerOf(placeId, generated); }
    @Register public String ledgerJsonNow() { return com.openworld.util.MiniJson.write(WorldLedger.get().toMap()); }
    @Register public void ledgerResetNow() { WorldLedger.replace(null); ledgerSaved = 0; }

    @Register public int savesWritten() { return saveCount; }
    @Register public int loadsApplied() { return loadCount; }
    @Register public int pendingPlayerCount() { return pendingPlayers.size(); }
    @Register public String lastSaveMessage() { return lastMessage; }
    /** Which file the last load read: "file", or "bak1" / "bak2" when the slot itself was bad. */
    @Register public String lastReadFromNow() { return lastReadFrom; }
    @Register public int profileWritesNow() { return profileWrites; }
    /** This install's balance / a grant to it (probes; the title runs before any body exists). */
    @Register public long profileBalanceNow() { return com.openworld.game.profile.Profiles.local().balance; }
    @Register public boolean grantProfileNow(long dollars) {
        return com.openworld.game.profile.Economy.transfer(null, com.openworld.game.profile.Profiles.local(), dollars,
                com.openworld.game.profile.Economy.Reason.GRANT);
    }
    /** A bill to this install's profile (may run into debt -- CR4). */
    @Register public long billProfileNow(long dollars) {
        return com.openworld.game.profile.Economy.bill(com.openworld.game.profile.Profiles.local(), dollars,
                com.openworld.game.profile.Economy.Reason.BILL_HOSPITAL);
    }
    /** A purchase from this install's profile (refused when short). */
    @Register public boolean spendProfileNow(long dollars) {
        return com.openworld.game.profile.Economy.transfer(com.openworld.game.profile.Profiles.local(), null, dollars,
                com.openworld.game.profile.Economy.Reason.PURCHASE);
    }
    /** Forget the in-memory profile and read the file again; returns where it came from ("file", "bak1", ...). */
    @Register public String reloadProfileNow() {
        com.openworld.game.profile.Profiles.clear();
        com.openworld.game.profile.Profiles.local();
        return com.openworld.game.profile.Profiles.loadedFrom();
    }
    /** The host's session copies, "id=balance;..." (probes). */
    @Register public String remoteBalancesNow() {
        StringBuilder b = new StringBuilder();
        for (var e : com.openworld.game.profile.Profiles.remotes().entrySet())
            b.append(b.length() == 0 ? "" : ";").append(e.getKey()).append('=').append(e.getValue().balance);
        return b.toString();
    }
    /** This install's owned cars, "id|model|garage|condition;..." (probes). */
    @Register public String profileVehiclesNow() {
        StringBuilder b = new StringBuilder();
        for (var v : com.openworld.game.profile.Profiles.local().vehicles)
            b.append(b.length() == 0 ? "" : ";").append(v.instanceId).append('|').append(v.model).append('|')
             .append(v.garageId).append('|').append(String.format(java.util.Locale.ROOT, "%.2f", v.condition));
        return b.toString();
    }
    @Register public String localPlayerIdNow() { return com.openworld.game.profile.Profiles.local().playerId; }
    @Register public String profilePathNow() {
        java.nio.file.Path p = com.openworld.game.profile.Profiles.file();
        return p == null ? "" : p.toString();
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private boolean fail(String message) {
        lastMessage = message;
        GD.printErr("[SaveSystem] " + message);
        return false;
    }

    private boolean isNetworkedClient() {
        return getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net
                && net.isNetworked() && !net.isServer();
    }

    private FactionManager factionManager() {
        return getNodeOrNull("/root/FactionManager") instanceof FactionManager fm ? fm : null;
    }

    private MissionManager missionManager() {
        return getNodeOrNull("/root/MissionManager") instanceof MissionManager mm ? mm : null;
    }

    private String currentScenePath() {
        Node scene = getTree() != null ? getTree().getCurrentScene() : null;
        String path = scene != null ? scene.getSceneFilePath() : null;
        return path != null ? path : "";
    }

    /** A sub-resource ("x.tres::id") or a code-built resource has no path something can re-load. */
    private static String loadablePath(godot.api.Resource res) {
        String path = res.getPath();
        return path == null || path.isEmpty() || path.contains("::") ? "" : path;
    }

    private static WeaponController weaponControllerOf(Player p) {
        return p.getNodeOrNull("WeaponController") instanceof WeaponController wc ? wc : null;
    }

    /** See the class note: stable across launches in both the local and the remote case. */
    private static String playerKey(Player p) {
        if (p.characterInfo == null) return "";
        if (p.isLocalOwnedPlayer()) return PersistentPlayerId.getOrCreate();
        String id = p.characterInfo.characterId;
        return id == null ? "" : id;
    }

    // ── One player's record ───────────────────────────────────────────────────

    private static final class PlayerRecord {
        final String key;
        final Vector3 position;
        final double yaw;
        final float health;
        final int activeSlot;
        final List<InventorySlotEntry> slots;

        PlayerRecord(String key, Vector3 position, double yaw, float health, int activeSlot,
                     List<InventorySlotEntry> slots) {
            this.key = key; this.position = position; this.yaw = yaw;
            this.health = health; this.activeSlot = activeSlot; this.slots = slots;
        }

        static PlayerRecord from(Dictionary<?, ?> d) {
            String key = str(d, "key", "");
            if (key.isEmpty()) return null;
            List<InventorySlotEntry> slots = new ArrayList<>();
            if (d.get("slots") instanceof VariantArray<?> arr) {
                for (java.lang.Object o : arr) {
                    if (!(o instanceof Dictionary<?, ?> s)) continue;
                    slots.add(new InventorySlotEntry((int) num(s, "slot", 0),
                            str(s, "weapon_id", ""), str(s, "scene", ""), str(s, "pickup_id", ""),
                            (int) num(s, "magazine", 0), (int) num(s, "reserve", 0)));
                }
            }
            return new PlayerRecord(key, vec3(d, "position"), num(d, "yaw", 0.0),
                    (float) num(d, "health", -1.0), (int) num(d, "active_slot", 0), slots);
        }
    }

    // ── JSON reading (the WorldBaker idiom: never throws, always has a default) ───

    /** godot-jvm hands a missing Dictionary key back as {@code kotlin.Unit}, not null. */
    private static boolean present(java.lang.Object v) {
        return v != null && !"kotlin.Unit".equals(v.getClass().getName());
    }

    private static String str(Dictionary<?, ?> d, String key, String def) {
        java.lang.Object v = d.get(key);
        return present(v) ? v.toString() : def;
    }

    private static double num(Dictionary<?, ?> d, String key, double def) {
        java.lang.Object v = d.get(key);
        if (!present(v)) return def;
        try { return ((Number) v).doubleValue(); } catch (RuntimeException e) { return def; }
    }

    private static boolean bool(Dictionary<?, ?> d, String key, boolean def) {
        java.lang.Object v = d.get(key);
        if (!present(v)) return def;
        if (v instanceof Boolean b) return b;
        try { return ((Number) v).doubleValue() != 0.0; } catch (RuntimeException e) { return def; }
    }

    private static Vector3 vec3(Dictionary<?, ?> d, String key) {
        java.lang.Object v = d.get(key);
        if (!(v instanceof VariantArray<?> a) || a.size() < 3) return new Vector3(0.0, 0.0, 0.0);
        try {
            return new Vector3(((Number) a.get(0)).doubleValue(), ((Number) a.get(1)).doubleValue(),
                    ((Number) a.get(2)).doubleValue());
        } catch (RuntimeException e) { return new Vector3(0.0, 0.0, 0.0); }
    }

    private static List<String> strings(Dictionary<?, ?> d, String key) {
        List<String> out = new ArrayList<>();
        if (d.get(key) instanceof VariantArray<?> arr) {
            for (java.lang.Object o : arr) if (present(o)) out.add(o.toString());
        }
        return out;
    }

    // ── JSON writing ──────────────────────────────────────────────────────────
    //
    // Composed as text rather than built as a Godot Dictionary tree: a nested typed Dictionary is
    // the one shape this binding handles badly (CLAUDE.md "Known Quirks" — a typed put() throws, and
    // a nested generic export kills the registration scanner), and the file stays diffable.

    private static final class Json {
        private final StringBuilder sb = new StringBuilder();
        private boolean firstInScope = true;

        Json begin()      { sep(); sb.append('{'); firstInScope = true; return this; }
        Json end()        { sb.append('}'); firstInScope = false; return this; }
        Json beginArray() { sb.append('['); firstInScope = true; return this; }
        Json endArray()   { sb.append(']'); firstInScope = false; return this; }
        Json beginArrayItem() { sep(); firstInScope = true; return this; }

        Json key(String k) { sep(); sb.append(quote(k)).append(':'); firstInScope = true; return this; }
        Json str(String k, String v)  { key(k); sb.append(quote(v)); firstInScope = false; return this; }
        Json bool(String k, boolean v){ key(k); sb.append(v); firstInScope = false; return this; }

        Json num(String k, double v) {
            key(k);
            sb.append(v == Math.rint(v) && !Double.isInfinite(v)
                    ? String.valueOf((long) v) : String.format(java.util.Locale.ROOT, "%.4f", v));
            firstInScope = false;
            return this;
        }

        Json vec3(String k, Vector3 v) {
            key(k);
            sb.append('[').append(fmt(v.getX())).append(',').append(fmt(v.getY())).append(',')
              .append(fmt(v.getZ())).append(']');
            firstInScope = false;
            return this;
        }

        /** {@code json} is already JSON text (an engine-free part's own shape: the ledger's). */
        Json raw(String k, String json) { key(k); sb.append(json); firstInScope = false; return this; }

        Json strings(String k, List<String> values) {
            key(k).beginArray();
            for (String v : values) { sep(); sb.append(quote(v)); firstInScope = false; }
            return endArray();
        }

        private void sep() {
            if (!firstInScope) sb.append(',');
            firstInScope = false;
        }

        private static String fmt(double v) { return String.format(java.util.Locale.ROOT, "%.4f", v); }

        private static String quote(String s) {
            StringBuilder out = new StringBuilder("\"");
            for (int i = 0; i < (s == null ? 0 : s.length()); i++) {
                char c = s.charAt(i);
                switch (c) {
                    case '"'  -> out.append("\\\"");
                    case '\\' -> out.append("\\\\");
                    case '\n' -> out.append("\\n");
                    case '\r' -> out.append("\\r");
                    case '\t' -> out.append("\\t");
                    default   -> {
                        if (c < 0x20) out.append(String.format("\\u%04x", (int) c));
                        else out.append(c);
                    }
                }
            }
            return out.append('"').toString();
        }

        @Override public String toString() { return sb.toString(); }
    }
}
