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
 * gave it up (the CS / most PC games rule) rather than double-bound. The pad is not rebound here: Steam Input remaps a
 * pad on the Deck, and the pad prompts read {@code tools/input/joypad_bindings.py}'s fixed table.
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

    /** Keys nobody may take: Esc is pause / back on every page. */
    public static boolean reserved(String spec) { return "key:4194305".equals(spec); }

    public static Row row(String id) {
        for (Row r : ROWS) if (r.id.equals(id)) return r;
        return null;
    }

    private final Map<String, String> current = new LinkedHashMap<>();

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
        if (row(rowId) == null || spec == null || reserved(spec)) return out;
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
        if (spec.startsWith("key:")) {
            try { return keyName.apply(Long.parseLong(spec.substring(4))); }
            catch (NumberFormatException e) { return "?"; }
        }
        return "?";
    }
}
