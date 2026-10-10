package com.openworld.game;

import com.openworld.character.Player;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;
import godot.global.GD;

/**
 * Carries the title screen's choice across the scene change (PLAN.md 1.3 / F2). AutoLoad. The title asks for the
 * world and names what to do once it is up -- continue from the autosave, host, join -- and this runs it ONCE, the
 * first frame the world's local player exists (the world's own _ready chain must have run: SaveSystem applies a
 * slot to live bodies, NetworkManager hosts from a world with a player in it).
 */
@Script(className = "FrontEnd")
public class FrontEnd extends Node {

    public static final String WORLD = "res://src/main/resources/com/openworld/world/World.tscn";
    public static final String TITLE = "res://src/main/resources/com/openworld/ui/TitleScreen.tscn";
    public static final int PORT = 7777;

    public enum Action { NONE, CONTINUE, HOST, JOIN }

    private static Action pending = Action.NONE;
    private static String joinAddress = "127.0.0.1";
    private static String lastRun = "";

    /** Start the world, then do {@code a} once it is up. */
    public static void start(Node from, Action a, String address) {
        pending = a == null ? Action.NONE : a;
        if (address != null && !address.isBlank()) joinAddress = address.trim();
        // a world STARTS with an empty ledger (PLAN.md 2.0): Continue's load replaces it, a joiner's is the host's;
        // and a NEW world (New game / Host) must not inherit the campaign of the session played before it in this
        // process -- MissionDirector is an AutoLoad and kept its sets across Quit to title
        WorldLedger.replace(null);
        if (pending == Action.NONE || pending == Action.HOST) {
            var director = com.openworld.game.mission.MissionDirector.get();
            if (director != null) director.resetCampaign();
        }
        from.getTree().changeSceneToFile(WORLD);
    }

    @Register
    @Override
    public void _process(double delta) {
        if (pending == Action.NONE) return;
        Player me = null;
        for (Player p : PlayerRegistry.getPlayers()) if (GD.isInstanceValid(p) && p.isLocalOwnedPlayer()) me = p;
        if (me == null) return;
        Action a = pending;
        pending = Action.NONE;
        var net = getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager n ? n : null;
        switch (a) {
            case CONTINUE -> {
                SaveSystem s = SaveSystem.get();
                boolean ok = s != null && s.hasSlot(s.autosaveSlot) && s.loadSlot(s.autosaveSlot);
                lastRun = "continue " + ok;
            }
            case HOST -> lastRun = "host " + (net != null && net.hostServer(PORT));
            case JOIN -> lastRun = "join " + joinAddress + " " + (net != null && net.joinServer(joinAddress, PORT));
            default -> { }
        }
        GD.print("FrontEnd: " + lastRun);
    }

    /** Back to the title (the pause menu's "Quit to title"): leave any session first. */
    public static void toTitle(Node from) {
        var net = from.getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager n ? n : null;
        if (net != null) net.leaveSession();
        SaveSystem s = SaveSystem.get();
        if (s != null) s.flushAll();
        from.getTree().setPause(false);
        from.getTree().changeSceneToFile(TITLE);
    }

    @Register public String lastRunNow() { return lastRun; }
    @Register public String pendingNow() { return pending.name(); }
}
