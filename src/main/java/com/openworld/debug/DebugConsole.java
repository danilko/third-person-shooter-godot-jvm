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
 * available in every scene that has a {@code DebugHarness}. Opening it pushes a MENU input context on
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
        input.connect("text_submitted", MethodCallable.createUnsafe(this, "on_submit"));
        addChild(input);

        setVisible(false);
        print("debug console — type 'help'");
    }

    /** The debug HUD: the harness's where there is one (the debug scenes), this console's own in the real game. */
    private PerfDebugOverlay ownHud;

    private PerfDebugOverlay hud() {
        if (getParent() instanceof DebugHarness h) return h.hud();
        if (ownHud == null || !GD.isInstanceValid(ownHud)) {
            ownHud = new PerfDebugOverlay();
            getParent().addChild(ownHud);
            ownHud.setLevel(0);
        }
        return ownHud;
    }

    /** Where the simulated cars are round the local player: the numbers behind "I rarely see a car". */
    private void traffic() {
        com.openworld.character.Player me = null;
        for (com.openworld.character.Player q : PlayerRegistry.getPlayers()) if (GD.isInstanceValid(q) && q.isLocallyOwnedPlayer()) me = q;
        com.openworld.world.ZoneManager zm = com.openworld.world.ZoneManager.get();
        if (me == null || zm == null) { print("no player / no ZoneManager"); return; }
        Vector3 at = me.getGlobalPosition();
        // the way the CAMERA looks is what "in front" means to the person asking
        godot.api.Camera3D cam = getViewport() == null ? null : getViewport().getCamera3d();
        Vector3 fwd = cam != null ? cam.getGlobalTransform().getBasis().getColumn(2).times(-1.0) : new Vector3(0, 0, -1);
        double fx = fwd.getX(), fz = fwd.getZ(), fl = Math.max(1e-6, Math.hypot(fx, fz));
        fx /= fl; fz /= fl;
        int n60 = 0, n100 = 0, n200 = 0, all = 0, parked = 0;
        int[] side = new int[4];   // ahead, right, behind, left -- within 200 m
        for (godot.api.Node n : getTree().getNodesInGroup(new StringName("characters"))) {
            if (!(n instanceof com.openworld.carrier.vehicle.Vehicle v) || !GD.isInstanceValid(v)) continue;
            double dx = v.getGlobalPosition().getX() - at.getX(), dz = v.getGlobalPosition().getZ() - at.getZ();
            double d = Math.hypot(dx, dz);
            all++;
            // a body with no traffic brain and nobody driving it is PARKED: it is counted, never as traffic
            if (!(v.getController() instanceof com.openworld.ai.vehicle.VehicleAIController) && v.getLinearVelocity().length() < 1.0) parked++;
            if (d <= 60) n60++;
            if (d <= 100) n100++;
            if (d > 200) continue;
            n200++;
            double ahead = dx * fx + dz * fz, right = dx * -fz + dz * fx;
            side[Math.abs(ahead) >= Math.abs(right) ? (ahead >= 0 ? 0 : 2) : (right >= 0 ? 1 : 3)]++;
        }
        print("cars (every vehicle body): " + all + " loaded, " + parked + " of them parked; within 60 m " + n60
                + ", 100 m " + n100 + ", 200 m " + n200);
        // an on-rails car's body velocity reads zero: what a car is DOING comes from its brain (standingReason)
        print("ambient traffic within 200 m: " + zm.trafficStateNow(200f));
        print("within 200 m by side of the camera: ahead " + side[0] + ", right " + side[1] + ", behind " + side[2] + ", left " + side[3]);
        print("traffic: " + zm.trafficAliveNow() + " alive of a budget of " + zm.effectiveTrafficBudgetNow() + ", "
                + zm.trafficSpawnsRefusedNow() + " spawns refused near a player, " + zm.trafficRecycledNow() + " recycled, far tier "
                + zm.farTrafficCarsNow());
        print("region " + zm.trafficRegionNow() + "; models " + zm.trafficModelsNow());
        print("drivers in the world: " + zm.trafficDriversNow() + " (a far car on rails carries none)");
    }

    private void activity(String[] a) {
        com.openworld.game.activity.ActivityRuntime rt = com.openworld.game.activity.ActivityRuntime.get();
        if (rt == null) { print("no ActivityRuntime"); return; }
        if (a.length < 2) {
            String running = rt.runningIdsNow();
            print(running.isEmpty() ? "no activity is running" : "running: " + running);
            for (String id : running.isEmpty() ? new String[0] : running.split(","))
                print("  " + id + " stage " + rt.stageNow(id) + ", " + rt.participantsNow(id));
            if (!rt.offeredNow().isEmpty()) print("on offer: " + rt.offeredNow());
            if (!rt.activityCheckpointNow().isEmpty()) print("can retry: " + rt.activityCheckpointNow());
            return;
        }
        String id = a.length >= 3 ? a[2] : "";
        String r = switch (a[1]) {
            case "start" -> rt.startNow(id, "STORY");
            case "replay" -> rt.startNow(id, "REPLAY");
            case "retry" -> rt.retryNow();
            case "why" -> rt.whyNotNow(id, "STORY") + " / replay: " + rt.whyNotNow(id, "REPLAY");
            case "abort" -> { rt.abortNow(id); yield ""; }
            default -> "start | replay | retry | abort | why";
        };
        print(r.isEmpty() ? "ok" : r);
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
            if (GD.isInstanceValid(p)) p.inputContexts.set("console", com.openworld.control.InputContext.MENU, blocked);
        }
    }

    // ── Output ────────────────────────────────────────────────────────────────

    /** Run one line as if typed, and return what it printed (probes; the console need not be open). */
    public String runLine(String text) {
        on_submit(text);
        java.util.List<String> now = new java.util.ArrayList<>(lines);
        // the history is a bounded window: what is new is what follows the echoed "> line"
        int at = now.lastIndexOf("> " + text);
        return at < 0 ? "" : String.join("\n", now.subList(at + 1, now.size()));
    }

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
                print("tables [reload]                        the data tables and their problems; reload re-reads them");
                print("markers                                level-design markers loaded now, by kind");
                print("ledger [flag <id> [value]|dead <id>]   the world's ledger: show / set a world flag / mark dead");
                print("give <id>                              put a weapon in your hands (the pickup path)");
                print("drop <id>|all                          lay pickups in a row in front of you");
                print("ammo                                   refill every weapon you carry");
                print("save [slot]                            write the campaign save (default 1)");
                print("load [slot]                            restore it (default 1)");
                print("hud [0-3]                              debug HUD: off / FPS / perf + graph / + game state");
                print("traffic                                cars round you now: by distance, by side, budget, region mix");
                print("activity [start|replay|retry|abort|why <id>]   the running activities; start / replay / retry one");
                print("where                                  the bug-report line (postal code, position, zone, road)");
                print("postal <x-y[-s]> [tp]                  waypoint (or teleport) to a postal code, e.g. postal 12-7-5");
                print("tp <x> <y> <z>                         teleport the local player (host / single player)");
                print("close                                  close the console");
            }
            case "close" -> close();
            case "where" -> where();
            case "postal" -> postal(a);
            case "tp" -> tp(a);
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
            case "tables" -> {
                // PLAN.md 2.0: the data tables -- `tables` lists them with their problems, `tables reload` re-reads
                // every file (the systems that keep a derived copy re-derive it: the debug hot reload)
                com.openworld.game.data.Tables.all();
                java.util.List<String> bad = a.length >= 2 && a[1].equals("reload")
                        ? com.openworld.util.DataTable.reloadAll() : com.openworld.util.DataTable.validateAll();
                for (com.openworld.util.DataTable<?> t : com.openworld.util.DataTable.all())
                    print(t.name + "  v" + t.version() + "  " + t.path);
                print(bad.isEmpty() ? "no problems" : String.join("\n", bad));
            }
            case "markers" -> {
                // every level-design marker loaded now, by kind (world.MarkerRegistry)
                StringBuilder sb = new StringBuilder();
                for (String k : com.openworld.world.MarkerRegistry.kinds(this))
                    sb.append(k).append(' ').append(com.openworld.world.MarkerRegistry.count(this, k)).append("  ");
                print(sb.length() == 0 ? "no markers loaded" : sb.toString().trim());
            }
            case "ledger" -> {
                // the world's ledger (game.WorldLedger): `ledger`, `ledger flag <id> [value]`, `ledger dead <storyId>`
                com.openworld.game.WorldLedger l = com.openworld.game.WorldLedger.get();
                if (a.length >= 3 && a[1].equals("flag")) {
                    if (a.length >= 4) l.setFlag(a[2], a[3]); else l.clearFlag(a[2]);
                } else if (a.length >= 3 && a[1].equals("dead")) l.markDead(a[2]);
                print(com.openworld.util.MiniJson.write(l.toMap()));
            }
            case "give" -> give(a);
            case "drop" -> drop(a);
            case "ammo" -> ammo();
            case "hud" -> {
                PerfDebugOverlay hud = hud();
                if (a.length >= 2) hud.setLevel(Integer.parseInt(a[1]));
                print("hud level " + hud.levelNow());
            }
            case "traffic" -> traffic();
            case "activity" -> activity(a);
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

    // ── Postal codes and the bug-report line (PLAN.md 3.26) ─────────────────────────────────────

    private Player localPlayer() {
        for (Player p : PlayerRegistry.getPlayers()) {
            if (GD.isInstanceValid(p) && p.isLocallyOwnedPlayer()) return p;
        }
        print("no local player");
        return null;
    }

    private void where() {
        Player p = localPlayer();
        if (p == null) return;
        String line = com.openworld.world.PostalReport.line(this, p.getGlobalPosition());
        print(line);
        godot.api.DisplayServer.clipboardSet(line);
    }

    private void postal(String[] a) {
        com.openworld.world.PostalGrid.Code c = a.length >= 2 ? com.openworld.world.PostalGrid.parse(a[1]) : null;
        if (c == null) { print("usage: postal <x-y[-s]> [tp]   x, y 1-24 (west->east, north->south), s 1-9 keypad"); return; }
        Player p = a.length >= 3 && a[2].equals("tp") ? spawnPlayer() : localPlayer();
        if (p == null) return;
        double[] xz = com.openworld.world.PostalGrid.centre(c);
        Vector3 at = new Vector3(xz[0], p.getGlobalPosition().getY(), xz[1]);
        if (a.length >= 3 && a[2].equals("tp")) {
            teleport(p, at);
            print("teleported to " + c);
        } else {
            p.setWaypoint(at);
            print("waypoint at " + c + String.format(" (x %.0f z %.0f)", xz[0], xz[1]));
        }
    }

    private void tp(String[] a) {
        if (a.length < 4) { print("usage: tp <x> <y> <z>"); return; }
        Player p = spawnPlayer();
        if (p == null) return;
        try {
            teleport(p, new Vector3(Double.parseDouble(a[1]), Double.parseDouble(a[2]), Double.parseDouble(a[3])));
            print("teleported");
        } catch (NumberFormatException e) {
            print("usage: tp <x> <y> <z>");
        }
    }

    /** Put the player at `at`, lifted onto whatever surface is below-or-at a point 400 m up (so a postal centre, which
     *  carries only x/z, lands on the ground or a roof instead of inside it). */
    private void teleport(Player p, Vector3 at) {
        Vector3 to = at;
        var space = p.getWorld3d() != null ? p.getWorld3d().getDirectSpaceState() : null;
        if (space != null) {
            var q = godot.api.PhysicsRayQueryParameters3D.Companion.create(
                    new Vector3(at.getX(), 400.0, at.getZ()), new Vector3(at.getX(), -50.0, at.getZ()));
            q.setExclude(new godot.core.VariantArray<>(godot.core.RID.class));
            var hit = space.intersectRay(q);
            if (hit != null && hit.containsKey("position")) {
                Vector3 h = (Vector3) hit.get("position");
                to = new Vector3(at.getX(), h.getY() + 1.0, at.getZ());
            }
        }
        p.setVelocity(Vector3.Companion.getZERO());
        p.setGlobalPosition(to);
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
