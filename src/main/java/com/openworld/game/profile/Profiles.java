package com.openworld.game.profile;

import com.openworld.character.Character;
import com.openworld.character.Player;
import com.openworld.util.MiniJson;

import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Where the profiles live at runtime (PLAN.md 1.4: AR2). A BODY never holds money; it asks for its player's profile:
 * <ul>
 *   <li>the body THIS machine plays -> {@link #local()}, this install's own, loaded from {@code user://profile.json};</li>
 *   <li>another player's body on the HOST -> the session copy that player sent at join (MSG_PROFILE), keyed by their
 *       PersistentPlayerId (which a remote body's characterId is, GameManager's rule);</li>
 *   <li>an AI -> null (no wallet; a robbed till pays the robber from the world).</li>
 * </ul>
 * The host changes a session copy (money moves on the host) and sends it back to its owner, who saves it.
 */
public final class Profiles {
    private Profiles() {}

    private static PlayerProfile local;
    private static final Map<String, PlayerProfile> REMOTE = new LinkedHashMap<>();
    private static Path file;
    private static String loadedFrom = "";
    private static long savedRevision = -1;

    /** Where this install's profile is kept. A run under {@code --script} (a probe, never the shipped game) gets its
     *  own file, so a probe granting itself 100 000 yen never lands in the player's real profile. */
    public static void configure(Path profileFile, long startingStake) {
        file = profileFile;
        stake = Math.max(0, startingStake);
    }

    /** What a profile created from nothing starts with (F3's starting_cash; 0 for a probe, which sets its own). */
    private static long stake;

    public static Path file() { return file; }

    /** This install's profile, loaded on first use (a fresh one when there is no file). */
    public static PlayerProfile local() {
        if (local == null) {
            local = load();
            // a NEW profile (with its stake) is written at the next save window; a loaded one is clean
            savedRevision = "new".equals(loadedFrom) ? -1 : local.revision();
        }
        return local;
    }

    @SuppressWarnings("unchecked")
    private static PlayerProfile load() {
        String id = com.openworld.net.session.PersistentPlayerId.getOrCreate();
        if (file != null) {
            SafeSave.Read r = SafeSave.read(file);
            if (r != null) {
                try {
                    Map<String, Object> m = SaveMigrations.migrate((Map<String, Object>) MiniJson.parse(r.payload()),
                            "version", SaveMigrations.PROFILE);
                    if (m != null) {
                        PlayerProfile p = PlayerProfile.fromMap(m);
                        p.playerId = id;   // the file belongs to this install whatever it says
                        loadedFrom = r.from();
                        return p;
                    }
                    loadedFrom = "refused (newer than this build)";
                } catch (RuntimeException e) {
                    loadedFrom = "unreadable: " + e.getMessage();
                }
            }
        }
        PlayerProfile fresh = new PlayerProfile(id);
        fresh.balance = stake;   // a NEW player's stake (economy.json starting_cash), once: it is saved from here on
        fresh.touch();
        loadedFrom = "new";
        return fresh;
    }

    /**
     * NEW GAME (user, 2026-10-11: "wipe everything except settings and key bindings"): this install's profile is
     * thrown away and a new one made -- the starting stake, no debts, no cars, no story, no career, no checkpoints.
     * The id stays (it is the install's, not the save's). Written at the next save window.
     */
    public static PlayerProfile resetLocal() {
        PlayerProfile fresh = new PlayerProfile(com.openworld.net.session.PersistentPlayerId.getOrCreate());
        fresh.balance = stake;
        fresh.touch();
        local = fresh;
        loadedFrom = "new";
        savedRevision = -1;
        return fresh;
    }

    /** Write the local profile now if it changed since the last write. */
    public static boolean saveIfDirty() {
        if (local == null || file == null || local.revision() == savedRevision) return false;
        boolean ok = SafeSave.write(file, MiniJson.write(local.toMap()));
        if (ok) savedRevision = local.revision();
        return ok;
    }

    public static boolean dirty() { return local != null && local.revision() != savedRevision; }

    /** The host's copy of a joined player's profile (created blank when they sent none). */
    public static PlayerProfile remote(String playerId) {
        return REMOTE.computeIfAbsent(playerId, PlayerProfile::new);
    }

    /** A joined player's profile arrived (MSG_PROFILE on the host). */
    public static void putRemote(String playerId, PlayerProfile p) {
        p.playerId = playerId;
        PlayerProfile have = REMOTE.get(playerId);
        if (have != null) have.copyFrom(p); else REMOTE.put(playerId, p);
    }

    public static Map<String, PlayerProfile> remotes() { return REMOTE; }

    /** The profile behind {@code body}: the local one, a session copy, or null for an AI / no player. */
    public static PlayerProfile of(Character body) {
        if (!(body instanceof Player p)) return null;
        if (p.isLocallyOwnedPlayer()) return local();
        String id = p.getCharacterInfo() != null ? p.getCharacterInfo().characterId : null;
        return id == null || id.isEmpty() ? null : remote(id);
    }

    /** The balance shown for {@code body} (0 for no profile). */
    public static long balanceOf(Character body) {
        PlayerProfile p = of(body);
        return p == null ? 0 : p.balance;
    }

    public static String loadedFrom() { return loadedFrom; }

    /** Engine teardown: drop every profile (and the next local() re-reads the file). */
    public static void clear() {
        local = null;
        REMOTE.clear();
        savedRevision = -1;
    }
}
