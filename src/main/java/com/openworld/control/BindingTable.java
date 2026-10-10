package com.openworld.control;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Keyboard / mouse REBINDING, the engine-free half (PLAN.md 1.3 / F2): which key each CONTROL row holds, and what a
 * rebind changes. A row is one key shared by several input actions -- W is both {@code forward} and {@code throttle},
 * Space is {@code jump}, {@code upright}, {@code handbrake} and {@code drift} -- because project.godot binds them to
 * the same key on purpose (on foot vs in a car are never live together). Rebinding a row moves the key on EVERY action
 * in it, so the car and the body never drift apart. A key a different row already holds is SWAPPED to the row that
 * gave it up (the CS / most PC games rule) rather than double-bound. The controller has its own rows
 * ({@link #PAD_ROWS}) on the same model.
 *
 * <p>A key is a spec string: {@code key:<physical keycode>} or {@code mouse:<button index>}. Unit-tested
 * ({@code BindingTableTest}); {@link KeyBindings} applies it to the InputMap.
 */
public final class BindingTable {

    /** One control row: its id (the settings.cfg key), the label on the page, and the actions sharing its key. */
    public record Row(String id, String label, List<String> actions) {}

    /** The rebindable rows, in the order the page lists them. Pause (Esc), the slot numbers and the wheel zoom stay. */
    public static final List<Row> ROWS = List.of(
            new Row("forward", "Move forward / throttle", List.of("forward", "throttle", "movement")),
            new Row("back", "Move back / reverse", List.of("back", "reverse", "movement")),
            new Row("left", "Move left", List.of("left", "movement")),
            new Row("right", "Move right", List.of("right", "movement")),
            new Row("sprint", "Sprint / hold breath / brake", List.of("sprint", "hold_breath", "brake", "movement")),
            new Row("walk", "Walk / crawl", List.of("walk", "crawl", "movement")),
            new Row("jump", "Jump / handbrake", List.of("jump", "upright", "handbrake", "drift")),
            new Row("crouch", "Crouch", List.of("crouch")),
            new Row("fire", "Fire", List.of("fire", "vehicle_fire")),
            new Row("aim", "Aim", List.of("aim")),
            new Row("reload", "Reload", List.of("reload")),
            new Row("interact", "Use", List.of("interact")),
            new Row("use_carrier", "Enter / leave vehicle", List.of("use_carrier")),
            new Row("radialmenu", "Weapon wheel", List.of("radialmenu")),
            new Row("holster", "Holster", List.of("holster")),
            new Row("drop", "Drop weapon", List.of("drop")),
            new Row("detonate", "Detonate", List.of("detonate")),
            new Row("map", "Map", List.of("map")),
            new Row("view", "First / third person", List.of("view")),
            new Row("shoulder", "Swap shoulder", List.of("shoulder")),
            new Row("rear_view", "Look back (vehicle)", List.of("rear_view")),
            new Row("scope_zoom", "Scope zoom", List.of("scope_zoom")));

    /**
     * The CONTROLLER's rebindable rows (user, 2026-10-10: "no game pad setting"). Its own table, because a pad groups
     * actions differently from the keyboard: RT is fire on foot and the throttle in a car, RB is the scope, the
     * detonator and the car's gun. A row's input is a button ({@code pad:<JoyButton>}) or a trigger
     * ({@code trig:<axis 4|5>}); the sticks (move, look), Start (pause) and the menus' A / B are fixed. The defaults are
     * read off project.godot, which {@code tools/input/joypad_bindings.py} writes.
     */
    public static final List<Row> PAD_ROWS = List.of(
            new Row("fire", "Fire / throttle", List.of("fire", "throttle")),
            new Row("aim", "Aim / reverse", List.of("aim", "reverse")),
            new Row("jump", "Jump / handbrake", List.of("jump", "upright", "handbrake", "drift")),
            new Row("crouch", "Crouch", List.of("crouch")),
            new Row("crawl", "Crawl", List.of("crawl")),
            new Row("reload", "Reload", List.of("reload")),
            new Row("use_carrier", "Enter / leave vehicle", List.of("use_carrier")),
            new Row("interact", "Use", List.of("interact")),
            new Row("walk", "Walk / breath / boost", List.of("walk", "hold_breath", "sprint")),
            new Row("shoulder", "Swap shoulder / look back", List.of("shoulder", "rear_view")),
            new Row("radialmenu", "Weapon wheel", List.of("radialmenu")),
            new Row("scope_zoom", "Scope / detonate / car gun", List.of("scope_zoom", "detonate", "vehicle_fire")),
            new Row("holster", "Holster", List.of("holster")),
            new Row("map", "Map", List.of("map")),
            new Row("view", "First / third person", List.of("view")));

    /** Keys nobody may take: Esc is pause / back on every page, Start is pause on a pad. */
    public static boolean reserved(String spec) { return "key:4194305".equals(spec) || "pad:6".equals(spec); }

    /** A KEYBOARD row by id. */
    public static Row row(String id) { return row(ROWS, id); }

    public static Row row(List<Row> rows, String id) {
        for (Row r : rows) if (r.id.equals(id)) return r;
        return null;
    }

    private final List<Row> rows;
    private final Map<String, String> current = new LinkedHashMap<>();

    /** The keyboard table. */
    public BindingTable() { this(ROWS); }

    public BindingTable(List<Row> rows) { this.rows = rows; }

    public List<Row> rows() { return rows; }

    /** The row's key now, or null when it has none. */
    public String keyOf(String rowId) { return current.get(rowId); }

    public void set(String rowId, String spec) {
        if (spec == null) current.remove(rowId); else current.put(rowId, spec);
    }

    /** The row holding {@code spec}, or null. */
    public String holder(String spec) {
        for (Map.Entry<String, String> e : current.entrySet()) if (e.getValue().equals(spec)) return e.getKey();
        return null;
    }

    /** A rebind's effect on one row: its key goes from {@code from} to {@code to} (either may be null). */
    public record Change(String rowId, String from, String to) {}

    /**
     * Give {@code rowId} the key {@code spec}. Returns what changed, in order (empty when nothing did: an unknown row, a
     * reserved key, or the key it already holds). A row already holding {@code spec} takes this row's old key -- a swap.
     */
    public List<Change> rebind(String rowId, String spec) {
        List<Change> out = new ArrayList<>();
        if (row(rows, rowId) == null || spec == null || reserved(spec)) return out;
        String old = current.get(rowId);
        if (spec.equals(old)) return out;
        String other = holder(spec);
        out.add(new Change(rowId, old, spec));
        current.put(rowId, spec);
        if (other != null && !other.equals(rowId)) {
            out.add(new Change(other, spec, old));
            set(other, old);
        }
        return out;
    }

    /**
     * The Kenney Steam Deck glyph name for a pad spec ({@code steamdeck_<name>.png}); the caller shows the label as
     * text when that file is not shipped.
     */
    public static String padGlyph(String spec) {
        if (spec == null) return null;
        return switch (spec) {
            case "pad:0" -> "button_a";
            case "pad:1" -> "button_b";
            case "pad:2" -> "button_x";
            case "pad:3" -> "button_y";
            case "pad:4" -> "button_view";
            case "pad:7" -> "button_l3";
            case "pad:8" -> "button_r3";
            case "pad:9" -> "button_l1";
            case "pad:10" -> "button_r1";
            case "pad:11" -> "dpad_up";
            case "pad:12" -> "dpad_down";
            case "pad:13" -> "dpad_left";
            case "pad:14" -> "dpad_right";
            case "trig:4" -> "button_l2";
            case "trig:5" -> "button_r2";
            default -> null;
        };
    }

    /** A copy of every row's key (for saving / probes). */
    public Map<String, String> snapshot() { return new LinkedHashMap<>(current); }

    /** The label a prompt shows for a key spec: the key's name, or the mouse button's. */
    public static String label(String spec, java.util.function.LongFunction<String> keyName) {
        if (spec == null) return "?";
        if (spec.startsWith("mouse:")) {
            return switch (spec.substring(6)) {
                case "1" -> "LMB";
                case "2" -> "RMB";
                case "3" -> "MMB";
                case "4" -> "Wheel up";
                case "5" -> "Wheel down";
                case "8" -> "Mouse 4";
                case "9" -> "Mouse 5";
                default -> "Mouse " + spec.substring(6);
            };
        }
        if (spec.startsWith("pad:")) {
            return switch (spec.substring(4)) {
                case "0" -> "A";
                case "1" -> "B";
                case "2" -> "X";
                case "3" -> "Y";
                case "4" -> "Back";
                case "6" -> "Start";
                case "7" -> "L3";
                case "8" -> "R3";
                case "9" -> "LB";
                case "10" -> "RB";
                case "11" -> "D-pad up";
                case "12" -> "D-pad down";
                case "13" -> "D-pad left";
                case "14" -> "D-pad right";
                default -> "Button " + spec.substring(4);
            };
        }
        if (spec.startsWith("trig:")) return "4".equals(spec.substring(5)) ? "LT" : "5".equals(spec.substring(5)) ? "RT" : "?";
        if (spec.startsWith("key:")) {
            try { return keyName.apply(Long.parseLong(spec.substring(4))); }
            catch (NumberFormatException e) { return "?"; }
        }
        return "?";
    }
}
