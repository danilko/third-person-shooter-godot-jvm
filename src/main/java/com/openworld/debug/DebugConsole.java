package com.openworld.debug;

import com.openworld.character.Player;
import com.openworld.game.PlayerRegistry;
import com.openworld.game.SaveSystem;
import com.openworld.game.mission.MissionDirector;
import com.openworld.game.mission.RaceDirector;
import com.openworld.game.mission.MissionManager;
import com.openworld.weapon.WeaponCatalog;
import com.openworld.weapon.WeaponItem;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.CanvasLayer;
import godot.api.ColorRect;
import godot.api.Control;
import godot.api.Input;
import godot.api.Label;
import godot.api.LineEdit;
import godot.core.Color;
import godot.core.MethodCallable;
import godot.core.StringName;
import godot.core.Vector2;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayDeque;
import java.util.Deque;

/**
 * In-game command line (backtick via {@code DebugHarness}) — the F1 prerequisite PLAN.md names:
 * calling {@code MissionDirector.commandCharacter} at runtime without recompiling, so a story beat can
 * be iterated on in one session instead of one per restart.
 *
 * <p>Built in code (the {@code PerfDebugOverlay} convention), so it needs no scene wiring and is
 * available in every scene that has a {@code DebugHarness}. Opening it sets {@code inputBlocked} on
 * every local player and frees the mouse — the same two things every other modal overlay does
 * ({@code WorldMapManager}, {@code WeaponRadialMenu}) — because otherwise typing "state" would walk
 * the player and shoot.
 *
 * <p>The command table is deliberately small and hand-written rather than reflective: a typo in a
 * reflective console is a silent no-op, while an unknown command here says so. Everything it drives is
 * already a {@code @Register}ed method, which is the same surface a GDScript probe uses — so the
 * console can never reach further into the game than the gates can.
 */
@Script(className = "DebugConsole")
public class DebugConsole extends CanvasLayer {

    private static final int HISTORY_LINES = 14;

    private Label output;
    private LineEdit input;
    private final Deque<String> lines = new ArrayDeque<>();
    private boolean open = false;

    @Register
    @Override
    public void _ready() {
        setLayer(128);   // over the HUD

        ColorRect backdrop = new ColorRect();
        backdrop.setColor(new Color(0.0, 0.0, 0.0, 0.65));
        backdrop.setPosition(new Vector2(0, 0));
        backdrop.setSize(new Vector2(1152, 280));
        backdrop.setMouseFilter(Control.MouseFilter.IGNORE);
        addChild(backdrop);

        output = new Label();
        output.setPosition(new Vector2(12, 8));
        output.setSize(new Vector2(1128, 240));
        output.setMouseFilter(Control.MouseFilter.IGNORE);
        addChild(output);

        input = new LineEdit();
        input.setPosition(new Vector2(12, 248));
        input.setSize(new Vector2(1128, 26));
        input.connect(new StringName("text_submitted"), MethodCallable.createUnsafe(this, "on_submit"));
        addChild(input);

        setVisible(false);
        print("debug console — type 'help'");
    }

    // ── Open / close ──────────────────────────────────────────────────────────

    /** Toggle the console. Called by {@code DebugHarness} on the backtick key. */
    public void toggle() { if (open) close(); else open(); }

    public boolean isOpen() { return open; }

    private void open() {
        open = true;
        setVisible(true);
        blockPlayerInput(true);
        Input.setMouseMode(Input.MouseMode.VISIBLE);
        input.setText("");
        input.grabFocus();
    }

    private void close() {
        open = false;
        setVisible(false);
        blockPlayerInput(false);
        Input.setMouseMode(Input.MouseMode.CAPTURED);
    }

    /**
     * Block (or release) every locally-owned player's input while the console has the keyboard.
     * Asked of {@code PlayerRegistry} rather than of one cached player: a peer can own more than one
     * body over a session, and a stale reference here would leave someone's input blocked forever.
     */
    private void blockPlayerInput(boolean blocked) {
        for (Player p : PlayerRegistry.getPlayers()) {
            if (GD.isInstanceValid(p)) p.inputBlocked = blocked;
        }
    }

    // ── Output ────────────────────────────────────────────────────────────────

    private void print(String line) {
        lines.addLast(line);
        while (lines.size() > HISTORY_LINES) lines.removeFirst();
        if (output != null) output.setText(String.join("\n", lines));
        GD.print("[console] " + line);
    }

    // ── Commands ──────────────────────────────────────────────────────────────

    @Register
    public void on_submit(String text) {
        input.setText("");
        if (text == null || text.isBlank()) return;
        print("> " + text);
        try {
            run(text.trim().split("\\s+"));
        } catch (RuntimeException e) {
            // A console that closes the game on a typo is worse than no console.
            print("error: " + e);
        }
    }

    private void run(String[] a) {
        MissionDirector director = MissionDirector.get();
        switch (a[0]) {
            case "help" -> {
                print("named                                  list registered story characters");
                print("move <id> <x> <y> <z>                  walk a story character there");
                print("state <id> [NAME]                      read, or force, its FSM state");
                print("invincible <id> on|off                 scripted invulnerability");
                print("release <id>                           drop the order and the invulnerability");
                print("beat <id>                              fire a story beat");
                print("mission start <res://...tres>          start it if the graph allows");
                print("mission complete <faction> <variant>   complete the active mission");
                print("mission fail <reason>                  fail the active mission");
                print("unlock <missionId> [requiredKey]       declare / query an unlock predicate");
                print("race [add <characterId>]              race status, or enrol a racer");
                print("weapons                                list every weapon id (weapon_catalog.json)");
                print("give <id>                              put a weapon in your hands (the pickup path)");
                print("drop <id>|all                          lay pickups in a row in front of you");
                print("ammo                                   refill every weapon you carry");
                print("save [slot]                            write the campaign save (default 1)");
                print("load [slot]                            restore it (default 1)");
                print("hud [0-3]                              debug HUD: off / FPS / perf + graph / + game state");
                print("close                                  close the console");
            }
            case "close" -> close();
            case "named" -> print(director == null ? "no MissionDirector"
                    : "named: " + orNone(director.namedCharacterIds()));
            case "move" -> {
                need(a, 5);
                boolean ok = director != null && director.commandMoveTo(a[1],
                        new Vector3(f(a[2]), f(a[3]), f(a[4])));
                print(ok ? a[1] + " walking to " + a[2] + "," + a[3] + "," + a[4]
                         : "no story character '" + a[1] + "' (or it is a puppet on this peer)");
            }
            case "state" -> {
                need(a, 2);
                if (director == null) { print("no MissionDirector"); return; }
                if (a.length >= 3) print(director.commandState(a[1], a[2])
                        ? a[1] + " -> " + a[2] : "refused (unknown id or state)");
                else print(a[1] + " is in " + orNone(director.stateNameOf(a[1])));
            }
            case "invincible" -> {
                need(a, 3);
                boolean on = "on".equalsIgnoreCase(a[2]);
                print(director != null && director.commandInvincible(a[1], on)
                        ? a[1] + " invincible " + (on ? "on" : "off") : "refused");
            }
            case "release" -> {
                need(a, 2);
                print(director != null && director.releaseCharacter(a[1]) ? a[1] + " released" : "refused");
            }
            case "beat" -> {
                need(a, 2);
                if (director == null) { print("no MissionDirector"); return; }
                print("beat '" + a[1] + "' fired"
                        + (director.triggerBeat(a[1]) ? " (handler ran)" : " (no handler yet)"));
            }
            case "mission" -> mission(a, director);
            case "save" -> {
                SaveSystem saves = SaveSystem.get();
                if (saves == null) { print("no SaveSystem"); return; }
                int slot = a.length >= 2 ? (int) f(a[1]) : 1;
                print(saves.saveSlot(slot) ? "saved slot " + slot + " -> " + saves.slotPath(slot)
                        : "refused: " + saves.lastSaveMessage());
            }
            case "load" -> {
                SaveSystem saves = SaveSystem.get();
                if (saves == null) { print("no SaveSystem"); return; }
                int slot = a.length >= 2 ? (int) f(a[1]) : 1;
                print(saves.loadSlot(slot) ? "loaded slot " + slot
                        : "refused: " + saves.lastSaveMessage());
            }
            case "race" -> {
                RaceDirector race = RaceDirector.get();
                if (race == null) { print("no RaceDirector"); return; }
                if (a.length >= 3 && "add".equals(a[1])) {
                    race.addRacer(a[2]);
                    print("enrolled " + a[2]);
                }
                print(race.statusLine());
            }
            case "weapons" -> print("weapons: " + String.join(" ", WeaponCatalog.spawnableIds()));
            case "give" -> give(a);
            case "drop" -> drop(a);
            case "ammo" -> ammo();
            case "hud" -> {
                if (!(getParent() instanceof DebugHarness h)) { print("no DebugHarness"); break; }
                if (a.length >= 2) h.hud().setLevel(Integer.parseInt(a[1]));
                print("hud level " + h.hud().levelNow());
            }
            case "unlock" -> {
                need(a, 2);
                if (director == null) { print("no MissionDirector"); return; }
                if (a.length >= 3) {
                    director.declareUnlockOn(a[1], a[2]);
                    print(a[1] + " now needs " + a[2]);
                }
                print(a[1] + " unlocked: " + director.isMissionUnlocked(a[1]));
            }
            default -> print("unknown command '" + a[0] + "' — try 'help'");
        }
    }

    private void mission(String[] a, MissionDirector director) {
        need(a, 2);
        MissionManager manager = missionManager();
        switch (a[1]) {
            case "start" -> {
                need(a, 3);
                print(director != null && director.startMissionFromPath(a[2])
                        ? "started " + a[2] : "refused (locked, or not a MissionInfo)");
            }
            case "complete" -> {
                need(a, 4);
                if (manager == null) { print("no MissionManager"); return; }
                manager.completeMission(a[2], a[3]);
                print("completed as " + a[2] + " / " + a[3]);
            }
            case "fail" -> {
                if (manager == null) { print("no MissionManager"); return; }
                manager.failMission(a.length >= 3 ? a[2] : "console");
                print("failed");
            }
            default -> print("mission start|complete|fail");
        }
    }

    private MissionManager missionManager() {
        return getNodeOrNull("/root/MissionManager") instanceof MissionManager mm ? mm : null;
    }

    private static void need(String[] a, int n) {
        if (a.length < n) throw new IllegalArgumentException("expected " + n + " arguments");
    }

    private static float f(String s) { return Float.parseFloat(s); }

    private static String orNone(String s) { return s == null || s.isEmpty() ? "(none)" : s; }

    // ── Weapon spawning (the CS `give` / Unreal `summon` idiom, driven by the catalog) ─────────

    /**
     * Host or single player only: a weapon spawned here is a local node, and on a client nothing replicates it
     * (a scene pickup's identity is its authored path), so it would exist on that peer alone.
     */
    private Player spawnPlayer() {
        if (getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager net
                && net.isNetworked() && !net.isServer()) {
            print("weapon commands are host / single player only (a client's spawn would not replicate)");
            return null;
        }
        for (Player p : PlayerRegistry.getPlayers()) {
            if (GD.isInstanceValid(p) && p.isLocallyOwnedPlayer()) return p;
        }
        print("no local player");
        return null;
    }

    private String weaponId(String[] a) {
        if (a.length < 2) { print("usage: " + a[0] + " <id> — ids: " + String.join(" ", WeaponCatalog.spawnableIds())); return null; }
        String id = WeaponCatalog.find(a[1]);
        if (id == null) print("no weapon '" + a[1] + "' — ids: " + String.join(" ", WeaponCatalog.spawnableIds()));
        return id;
    }

    private void give(String[] a) {
        String id = weaponId(a);
        Player p = id == null ? null : spawnPlayer();
        if (p == null || p.weaponController == null) return;
        WeaponItem item = WeaponCatalog.instantiate(id);
        if (item == null) { print("could not load " + id); return; }
        // the ordinary pickup path: in the tree first, then queued into the inventory
        getTree().getCurrentScene().addChild(item);
        item.setGlobalPosition(p.getGlobalPosition());
        p.weaponController.requestEquip(item);
        print("gave " + id);
    }

    private void drop(String[] a) {
        java.util.List<String> ids;
        if (a.length >= 2 && a[1].equalsIgnoreCase("all")) {
            ids = WeaponCatalog.spawnableIds();
        } else {
            String id = weaponId(a);
            if (id == null) return;
            ids = java.util.List.of(id);
        }
        Player p = spawnPlayer();
        if (p == null) return;
        // a row across the player's view, 3 m ahead, dropped from 0.6 m so each falls onto whatever is there
        Vector3 fwd = p.getNodeOrNull("ActiveCamera") instanceof godot.api.Node3D cam
                ? cam.getGlobalBasis().getZ().times(-1.0) : p.getGlobalBasis().getZ().times(-1.0);
        fwd = new Vector3(fwd.getX(), 0.0, fwd.getZ());
        if (fwd.length() < 1e-3) fwd = new Vector3(0, 0, -1);
        fwd = fwd.normalized();
        Vector3 right = new Vector3(-fwd.getZ(), 0.0, fwd.getX());
        double spacing = 0.9;
        for (int i = 0; i < ids.size(); i++) {
            WeaponItem item = WeaponCatalog.instantiate(ids.get(i));
            if (item == null) continue;
            double off = (i - (ids.size() - 1) / 2.0) * spacing;
            getTree().getCurrentScene().addChild(item);   // wraps itself in a PickupBody and falls (W15)
            item.setGlobalPosition(p.getGlobalPosition().plus(fwd.times(3.0)).plus(right.times(off))
                    .plus(new Vector3(0, 0.6, 0)));
        }
        print("dropped " + String.join(" ", ids));
    }

    private void ammo() {
        Player p = spawnPlayer();
        if (p == null || p.weaponController == null) return;
        int n = 0;
        for (int i = 0; i < p.weaponController.slotCount(); i++) {
            WeaponItem w = p.weaponController.getWeaponItem(i);
            if (w == null) continue;
            w.magazine = w.magazineSize;
            w.reserve = w.reserveMax;
            n++;
        }
        WeaponItem cur = p.weaponController.getCurrentWeaponItem();
        if (cur != null) p.weaponController.ammoChanged.emit(cur.magazine, cur.reserve);   // the HUD's readout
        print("refilled " + n + " weapon(s)");
    }
}
