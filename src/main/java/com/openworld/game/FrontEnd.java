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
        // NEW GAME is a new story too (PLAN.md 2.1): the campaign lives in the player's profile now, and a new world
        // with every mission already done would have nothing to start. Money, cars and career records are the
        // player's and stay. Hosting does not reset it: a player brings their story into the world they host.
        if (pending == Action.NONE) {
            var profile = com.openworld.game.profile.Profiles.local();
            profile.campaign.reset();
            profile.activityCheckpoint = null;
            profile.touch();
        }
        from.getTree().changeSceneToFile(WORLD);
    }

    @Register
    @Override
    public void _process(double delta) {
        startWarmup();
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

    private long warmedScene;

    /** The island just came up: put the loading screen over it (game.WorldWarmup), once per world load. Not under a
     *  probe (--script), not headless, not with OW_NO_WARMUP=1; OW_WARMUP=1 forces it (a probe of the screen itself). */
    private void startWarmup() {
        Node scene = getTree() != null ? getTree().getCurrentScene() : null;
        if (scene == null || scene.getInstanceId() == warmedScene) return;
        warmedScene = scene.getInstanceId();
        if (!WORLD.equals(scene.getSceneFilePath())) return;
        boolean force = "1".equals(godot.api.OS.getEnvironment("OW_WARMUP"));
        if (!force) {
            if ("1".equals(godot.api.OS.getEnvironment("OW_NO_WARMUP"))) return;
            if ("headless".equals(godot.api.DisplayServer.getName())) return;
            for (String a : godot.api.OS.getCmdlineArgs()) if ("--script".equals(a) || "-s".equals(a)) return;
            for (String a : godot.api.OS.getCmdlineUserArgs()) if ("--no-warmup".equals(a)) return;
        }
        WorldWarmup w = new WorldWarmup();
        w.setName(new godot.core.StringName("WorldWarmup"));
        scene.addChild(w);
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
