package com.openworld.world;

import com.openworld.util.CollisionLayers;
import com.openworld.util.MiniJson;
import godot.api.BaseMaterial3D;
import godot.api.BoxMesh;
import godot.api.FileAccess;
import godot.api.Label3D;
import godot.api.MeshInstance3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.StandardMaterial3D;
import godot.core.Basis;
import godot.core.Color;
import godot.core.Transform3D;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * What a passenger READS about the trains (user, 2026-10-02: "a display in each station ... incoming train / time in
 * game time, to make it more Japan-like", "labels near the train door for the upcoming station", "once a station is
 * selected on the map, each way's next time"). Owned by {@link TrainSystem}; everything is derived from the same
 * clock-driven timetable, so nothing is stored or sent.
 *
 * <ul>
 *   <li><b>発車標</b>, a departure board hung over each platform a set calls at, both faces: 先発 / 次発 (this train,
 *       the next), the time in GAME time (Sky3D's TimeOfDay) and the destination (行), "まもなく" in the last 30 s;</li>
 *   <li><b>ドア上LCD</b>, the screen over every door inside a car: 次は (next) and its arrival time, or at a stop the
 *       station and where the train goes next;</li>
 *   <li>the map's panel for a station: each way's next two times.</li>
 * </ul>
 * Station names are fictional ({@code StationNames.json}, Japanese + English); the sign font carries their glyphs
 * ({@code tools/make_jp_font.py}).
 */
final class TrainDisplays {

    static final String NAMES = "res://src/main/resources/com/openworld/world/StationNames.json";
    /** Boards are built within this of the camera (m) and freed past it + 120. */
    static final double BOARD_RADIUS = 260.0;
    /** In-car screens show text within this of the camera (m). */
    static final double SCREEN_RADIUS = 60.0;
    /** A board hangs this far over the platform top (m), this far out from the track centre (over the platform). */
    static final double BOARD_UP = 2.55, BOARD_OUT = 3.0;
    static final double SOON = 30.0;

    private final TrainSystem ts;
    private final Map<String, String[]> names = new HashMap<>();
    private final Map<String, Board> boards = new HashMap<>();
    private StandardMaterial3D boardMat;

    static final class Board {
        Node3D node;
        Label3D[] text = new Label3D[2];
        String shown = "";
        int set, stop;
        int tries;
    }

    TrainDisplays(TrainSystem ts) {
        this.ts = ts;
        loadNames();
    }

    @SuppressWarnings("unchecked")
    private void loadNames() {
        if (!FileAccess.fileExists(NAMES)) return;
        try {
            Map<String, Object> d = (Map<String, Object>) MiniJson.parse(FileAccess.getFileAsString(NAMES));
            for (Map.Entry<String, Object> e : ((Map<String, Object>) d.get("stations")).entrySet()) {
                Map<String, Object> v = (Map<String, Object>) e.getValue();
                names.put(e.getKey(), new String[]{String.valueOf(v.get("ja")), String.valueOf(v.get("en"))});
            }
        } catch (RuntimeException e) {
            GD.printErr("TrainDisplays: " + NAMES + ": " + e.getMessage());
        }
    }

    /** {Japanese, English} for a station id ({id, id} when it has no entry). */
    /** {sign language, English} of a station: the string table's `station.<id>` row (world.SignText). */
    String[] name(String id) {
        if (id == null) return new String[]{"", ""};
        String key = "station." + id;
        if (SignText.has(key)) return new String[]{SignText.local(key), SignText.en(key)};
        String[] n = names.get(id);
        return n != null ? n : new String[]{id, id};
    }

    // ── game time ────────────────────────────────────────────────────────────

    /** The game's time of day (hours) at train-clock time {@code t} (GameTime, the one owner). */
    double gameHours(double t, double now) { return GameTime.hoursIn(ts.getTree(), t - now); }

    String clock(double t, double now) { return GameTime.format(gameHours(t, now)); }

    private static double num(Object o, double d) { return o instanceof Number n ? n.doubleValue() : d; }

    // ── what each display says ───────────────────────────────────────────────

    /** The station of set {@code set}'s stop {@code stop} on its track {@code track}, or "" for none. */
    String stationOf(TrainSystem.TrainSet set, int track, int stop) {
        if (track < 0 || track >= set.stopStation.length) return "";
        int[] ss = set.stopStation[track];
        if (stop < 0 || stop >= ss.length || ss[stop] < 0) return "";
        return ts.stationId(ss[stop]);
    }

    /** Where a call's train goes (行): a circuit's terminus is the far end of the track it LEAVES on. */
    String destinationOf(TrainSystem.TrainSet set, TrainTimetable.Call c) {
        if (!set.tt.isCircuit()) return stationOf(set, 0, set.tt.terminalFor(c.dir()));
        int dt = set.tt.departureTrack(c);
        return stationOf(set, dt, set.tt.stopCount(dt) - 1);
    }

    /** Every call at the stop {@code stop} of track {@code track}, from every set on it, soonest first. */
    private List<double[]> callsAt(TrainSystem.Track track, int stop, double now, int max) {
        List<double[]> out = new ArrayList<>();                    // {arrive, depart, setIndex, call index}
        List<TrainSystem.TrainSet> sets = ts.setsNow();
        for (int si = 0; si < sets.size(); si++) {
            TrainSystem.TrainSet set = sets.get(si);
            int ti = set.trackIndex(track);
            if (ti < 0 || set.outOfService(now)) continue;
            for (TrainTimetable.Call c : set.tt.calls(now + set.phase, ti, stop, max)) {
                out.add(new double[]{c.arrive() - set.phase, c.depart() - set.phase, si, c.dir(), c.track(), c.stop()});
            }
        }
        out.sort((x, y) -> Double.compare(x[0], y[0]));
        return out.size() > max ? out.subList(0, max) : out;
    }

    private String destinationOf(double[] row) {
        TrainSystem.TrainSet set = ts.setsNow().get((int) row[2]);
        return destinationOf(set, new TrainTimetable.Call(row[0], row[1], (int) row[5], (int) row[3], (int) row[4]));
    }

    /** Two lines for the board at a track's stop: 先発 / 次発 with time and destination, from every set on it. */
    String boardText(TrainSystem.Track track, int stop, double now) {
        StringBuilder sb = new StringBuilder();
        String[] label = {SignText.local("word.train_first"), SignText.local("word.train_second")};
        int k = 0;
        for (double[] row : callsAt(track, stop, now, 2)) {
            double arrive = row[0];
            String[] dest = name(destinationOf(row));
            String when = arrive - now <= SOON && arrive >= now ? SignText.local("word.train_soon") : clock(arrive, now);
            if (arrive < now) when = SignText.local("word.train_departs", "", clock(row[1], now)).trim();
            if (k > 0) sb.append('\n');
            sb.append(label[k]).append("  ").append(when).append("  ").append(SignText.local("word.train_local"))
                    .append("  ").append(SignText.local("word.train_bound", dest[0])).append("  ").append(dest[1]);
            k++;
        }
        return sb.length() == 0 ? SignText.local("word.train_none") + "  " + SignText.en("word.train_none") : sb.toString();
    }

    /** "中央 行  For Central": a destination in the sign language and in English. */
    private static String bound(String[] dest) {
        return SignText.local("word.train_bound", dest[0]) + "  " + SignText.en("word.train_bound", dest[1]);
    }

    /** The screen over a door inside a car. */
    String screenText(TrainSystem.TrainSet set, double now) {
        TrainTimetable.Call c = set.tt.nextCall(now + set.phase);
        if (c == null) return "";
        String[] at = name(stationOf(set, c.track(), c.stop()));
        String[] dest = name(destinationOf(set, c));
        double arrive = c.arrive() - set.phase;
        if (arrive <= now) {
            // standing at a stop
            return at[0] + "  " + at[1] + "\n" + bound(dest);
        }
        return SignText.local("word.train_next_stop") + "  " + at[0] + "\n" + SignText.en("word.train_next_stop") + "  "
                + at[1] + "  " + SignText.local("word.train_arrives", "", clock(arrive, now)).trim();
    }

    /** The map's panel for the station nearest (x, z) within {@code reach} m: its name, then each way's next two
     *  times. Empty when there is no station there. */
    List<String> stationPanel(double x, double z, double reach, double now) {
        List<String> out = new ArrayList<>();
        int best = -1;
        double bd = reach;
        List<double[]> st = ts.stationPositions();
        for (int i = 0; i < st.size(); i++) {
            double d = Math.hypot(st.get(i)[0] - x, st.get(i)[1] - z);
            if (d < bd) { bd = d; best = (int) st.get(i)[2]; }
        }
        if (best < 0) return out;
        String id = ts.stationId(best);
        String[] nm = name(id);
        out.add(nm[0] + "  " + nm[1]);
        Map<String, List<Double>> byDest = new java.util.TreeMap<>();
        for (TrainSystem.TrainSet set : ts.setsNow()) {
            if (set.outOfService(now)) continue;
            for (int ti = 0; ti < set.stopStation.length; ti++) {
                for (int k = 0; k < set.stopStation[ti].length; k++) {
                    if (set.stopStation[ti][k] != best) continue;
                    for (TrainTimetable.Call c : set.tt.calls(now + set.phase, ti, k, 3)) {
                        String destId = destinationOf(set, c);
                        if (destId.equals(id)) continue;                  // terminates here
                        String[] dest = name(destId);
                        byDest.computeIfAbsent(bound(dest), q -> new ArrayList<>())
                                .add(c.depart() - set.phase);
                    }
                }
            }
        }
        for (Map.Entry<String, List<Double>> e : byDest.entrySet()) {
            List<Double> times = e.getValue();
            times.sort(Double::compare);
            StringBuilder sb = new StringBuilder(e.getKey()).append(":  ");
            for (int i = 0; i < Math.min(2, times.size()); i++) {
                if (i > 0) sb.append(",  ");
                sb.append(clock(times.get(i), now));
            }
            out.add(sb.toString());
        }
        if (out.size() == 1) out.add("No trains");
        return out;
    }

    // ── the boards in the world ──────────────────────────────────────────────

    void updateBoards(Vector3 eye, double now) {
        if (eye == null) return;
        // one board per (track, stop) a set calls at, listing every set on that track
        java.util.Set<String> seen = new java.util.HashSet<>();
        for (TrainSystem.TrainSet set : ts.setsNow()) {
            for (int ti = 0; ti < set.tracks.length; ti++) {
                TrainSystem.Track track = set.tracks[ti];
                for (int k = 0; k < set.stopStation[ti].length; k++) {
                    if (set.stopStation[ti][k] < 0) continue;
                    String key = track.id + ":" + k;
                    if (!seen.add(key)) continue;
                    double s = stopS(set, ti, k);
                    double[] p = track.at(s);
                    double d = Math.hypot(p[0] - eye.getX(), p[2] - eye.getZ());
                    Board b = boards.get(key);
                    if (d > BOARD_RADIUS + 120.0) {
                        if (b != null) {
                            if (b.node != null && GD.isInstanceValid(b.node)) b.node.queueFree();
                            boards.remove(key);
                        }
                        continue;
                    }
                    if (d > BOARD_RADIUS && b == null) continue;
                    if (b == null) {
                        b = new Board();
                        b.stop = k;
                        boards.put(key, b);
                    }
                    if (b.node == null && b.tries < 20) {
                        b.tries++;
                        b.node = build(track, s, b);
                    }
                    if (b.node == null) continue;
                    String text = boardText(track, k, now);
                    if (!text.equals(b.shown)) {
                        b.shown = text;
                        for (Label3D l : b.text) l.setText(text);
                    }
                }
            }
        }
    }

    private static double stopS(TrainSystem.TrainSet set, int track, int k) {
        for (TrainTimetable.Leg l : set.tt.legs()) if (l.dwell() && l.stop() == k && l.track() == track) return l.s0();
        return 0;
    }

    /** A board over the platform beside set's track at arclength s, or null while no platform is found there. */
    private Node3D build(TrainSystem.Track track, double s, Board board) {
        double[] a = track.at(s - 2.0), b = track.at(s + 2.0), c = track.at(s);
        Vector3 fwd = new Vector3(b[0] - a[0], 0, b[2] - a[2]).normalized();
        Vector3 right = new Vector3(-fwd.getZ(), 0, fwd.getX());
        double rail = c[1] + TrainSystem.RAIL_H;
        int side = 0;
        for (int sg : new int[]{1, -1}) {
            Vector3 at = new Vector3(c[0], 0, c[2]).plus(right.times(sg * 2.6));
            Vector3 from = new Vector3(at.getX(), rail + 3.0, at.getZ()), to = new Vector3(at.getX(), rail - 1.0, at.getZ());
            godot.api.PhysicsDirectSpaceState3D sp = ts.getWorld3d() != null ? ts.getWorld3d().getDirectSpaceState() : null;
            if (sp == null) return null;
            godot.core.Dictionary<Object, Object> hit = sp.intersectRay(
                    godot.api.PhysicsRayQueryParameters3D.create(from, to, CollisionLayers.WORLD, ts.trainRidsNow()));
            if (hit != null && !hit.isEmpty() && hit.get("position") instanceof Vector3 hp
                    && hp.getY() > rail + 0.8 && hp.getY() < rail + 1.6) {
                side = sg;
                break;
            }
        }
        if (side == 0) return null;
        if (boardMat == null) {
            boardMat = new StandardMaterial3D();
            boardMat.setAlbedo(new Color(0.04, 0.04, 0.05, 1.0));
            boardMat.setRoughness(0.6f);
        }
        Node3D n = new Node3D();
        n.setName(new godot.core.StringName("Board_" + track.id + "_" + Math.round(s)));
        MeshInstance3D box = new MeshInstance3D();
        BoxMesh bm = new BoxMesh();
        bm.setSize(new Vector3(2.4, 0.62, 0.10));
        box.setMesh(bm);
        box.setMaterialOverride(boardMat);
        box.setCastShadowsSetting(godot.api.GeometryInstance3D.ShadowCastingSetting.OFF);
        n.addChild(box);
        // two hangers to the canopy
        for (double hx : new double[]{-1.0, 1.0}) {
            MeshInstance3D rod = new MeshInstance3D();
            BoxMesh rm = new BoxMesh();
            rm.setSize(new Vector3(0.03, 0.8, 0.03));
            rod.setMesh(rm);
            rod.setMaterialOverride(boardMat);
            rod.setPosition(new Vector3(hx, 0.71, 0));
            n.addChild(rod);
        }
        godot.api.FontFile font = StreetNames.font();
        for (int f = 0; f < 2; f++) {
            Label3D l = new Label3D();
            if (font != null) l.setFont(font);
            l.setFontSize(48);
            l.setPixelSize(0.0018f);
            l.setModulate(new Color(1.0, 0.62, 0.15, 1.0));
            l.setOutlineSize(0);
            l.setDrawFlag(Label3D.DrawFlags.FLAG_DOUBLE_SIDED, false);
            l.setHorizontalAlignment(godot.core.HorizontalAlignment.CENTER);
            l.setPosition(new Vector3(0, 0, f == 0 ? 0.052 : -0.052));
            if (f == 1) l.setRotation(new Vector3(0, Math.PI, 0));
            n.addChild(l);
            board.text[f] = l;
        }
        ts.addChild(n);
        // the board's faces look along the track (read as you walk the platform); over the platform, under the canopy
        Basis basis = new Basis(new Vector3(0, 1, 0), Math.atan2(fwd.getX(), fwd.getZ()));
        Vector3 pos = new Vector3(c[0], rail + 1.1 + BOARD_UP, c[2]).plus(right.times(side * BOARD_OUT));
        n.setGlobalTransform(new Transform3D(basis, pos));
        return n;
    }

    int boardCount() {
        int n = 0;
        for (Board b : boards.values()) if (b.node != null) n++;
        return n;
    }

    /** The text a board shows (probe), the first built one's, or "". */
    String anyBoardText() {
        for (Board b : boards.values()) if (b.node != null) return b.shown;
        return "";
    }

    void clear() {
        for (Board b : boards.values()) if (b.node != null && GD.isInstanceValid(b.node)) b.node.queueFree();
        boards.clear();
    }

    // ── the screens inside a car ─────────────────────────────────────────────

    /** One Label3D per door-top screen of a car (car frame), facing into the car. */
    static List<Label3D> buildScreens(Node3D body, List<double[]> doorCentres) {
        List<Label3D> out = new ArrayList<>();
        godot.api.FontFile font = StreetNames.font();
        for (double[] d : doorCentres) {
            double side = d[0];
            Label3D l = new Label3D();
            if (font != null) l.setFont(font);
            l.setFontSize(32);
            l.setPixelSize(0.0013f);
            l.setModulate(new Color(1.0, 0.85, 0.35, 1.0));
            l.setOutlineSize(0);
            l.setDrawFlag(Label3D.DrawFlags.FLAG_DOUBLE_SIDED, false);
            l.setVisible(false);
            l.setPosition(new Vector3(side * 1.285, 3.13, d[1]));
            l.setRotation(new Vector3(0, side > 0 ? -Math.PI / 2 : Math.PI / 2, 0));
            body.addChild(l);
            out.add(l);
        }
        return out;
    }
}
