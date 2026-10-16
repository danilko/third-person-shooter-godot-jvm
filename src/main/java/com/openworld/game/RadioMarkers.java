package com.openworld.game;

import com.openworld.character.Player;
import godot.global.GD;

import java.util.ArrayList;
import java.util.List;

/**
 * The incidents a player's radio told of, on THIS peer's minimap while they last (PLAN.md P1e step 7). The host posts
 * them ({@link RadioNet}): for its own player straight in here, for a client's player as
 * {@link GameManager#WORLD_EVENT_INCIDENT} to every peer, kept only by the peer whose player it is. Local, never saved.
 */
public final class RadioMarkers {
    private RadioMarkers() {}

    /** One marker: what, where (world x, z), until when (engine ms). */
    public record Marker(String type, double x, double z, long untilMs) {}

    private static final List<Marker> markers = new ArrayList<>();
    private static int received;

    /** The host: tell {@code playerId} of an incident at (x, z) for {@code seconds}. */
    static void post(EnforcementDispatch ed, String playerId, String type, double x, double z, double seconds) {
        if (isLocal(playerId)) add(type, x, z, seconds);
        if (ed.getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager net && net.isNetworked() && net.isServer())
            net.broadcastWorldEvent(GameManager.WORLD_EVENT_INCIDENT, playerId, (float) seconds,
                    List.of(type, String.format(java.util.Locale.ROOT, "%.1f", x), String.format(java.util.Locale.ROOT, "%.1f", z)));
    }

    /** A client: the host's WORLD_EVENT_INCIDENT, kept when it is about this peer's own player. */
    public static void applyRemote(String playerId, float seconds, List<String> args) {
        if (!isLocal(playerId) || args == null || args.size() < 3) return;
        try {
            add(args.get(0), Double.parseDouble(args.get(1)), Double.parseDouble(args.get(2)), seconds);
            received++;
        } catch (NumberFormatException ignored) {
            // a garbled frame: no marker
        }
    }

    private static boolean isLocal(String playerId) {
        for (Player p : PlayerRegistry.getPlayers())
            if (GD.isInstanceValid(p) && p.getCharacterInfo() != null && p.getCharacterInfo().characterId.equals(playerId)
                    && p.isLocallyOwnedPlayer()) return true;
        return false;
    }

    private static void add(String type, double x, double z, double seconds) {
        long now = godot.api.Time.getTicksMsec();
        markers.removeIf(m -> m.untilMs() < now);
        markers.add(new Marker(type, x, z, now + (long) (seconds * 1000)));
    }

    /** Markers still live (the minimap). */
    public static List<Marker> live() {
        long now = godot.api.Time.getTicksMsec();
        markers.removeIf(m -> m.untilMs() < now);
        return List.copyOf(markers);
    }

    /** Markers received from the host (probe readout). */
    public static int receivedCount() { return received; }

    public static void clear() { markers.clear(); }
}
