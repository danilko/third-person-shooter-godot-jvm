package com.openworld.debug;

import com.openworld.character.Player;
import com.openworld.game.PlayerRegistry;
import com.openworld.game.SaveSystem;
import com.openworld.game.mission.MissionDirector;
import com.openworld.game.mission.RaceDirector;
import com.openworld.game.mission.MissionManager;
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
                print("save [slot]                            write the campaign save (default 1)");
                print("load [slot]                            restore it (default 1)");
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
}
