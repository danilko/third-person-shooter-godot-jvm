package com.openworld.control;

import godot.api.ConfigFile;
import godot.api.DisplayServer;
import godot.api.InputEvent;
import godot.api.InputEventKey;
import godot.api.InputEventMouseButton;
import godot.api.InputMap;
import godot.api.OS;
import godot.core.Key;
import godot.core.MouseButton;
import godot.core.VariantArray;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Keyboard / mouse rebinding applied to the InputMap (PLAN.md 1.3 / F2) -- the engine half of {@link BindingTable}.
 * Owned by {@code QualitySettings}, which loads {@code [bindings]} from settings.cfg and saves it; the settings page's
 * "Key bindings" sub-page calls {@link #rebind}. Only the KEYBOARD and MOUSE events of an action are rewritten; its pad
 * events are kept as project.godot has them. Each affected action is REBUILT from every row that holds it (the shared
 * {@code movement} action carries six rows' keys, so editing events one by one would lose a key in a swap).
 *
 * <p>The HUD's prompts follow the binding: a prompt is written with the DEFAULT letter ("[ F ]  Enter vehicle"), and
 * {@link #shownKey} turns it into the key that is bound now.
 */
public final class KeyBindings {
    private KeyBindings() {}

    private static final BindingTable TABLE = new BindingTable();
    private static final Map<String, String> DEFAULTS = new LinkedHashMap<>();
    private static boolean initialised;

    /** Read every row's DEFAULT key off the InputMap (project.godot), once, before any user binding is applied. */
    public static void init() {
        if (initialised) return;
        initialised = true;
        for (BindingTable.Row r : BindingTable.ROWS) {
            String spec = firstSpec(r.actions().get(0));
            DEFAULTS.put(r.id(), spec);
            TABLE.set(r.id(), spec);
        }
    }

    /** The spec of an input event that can be bound ({@code key:<physical>} / {@code mouse:<index>}), else null. */
    public static String specOf(InputEvent e) {
        if (e instanceof InputEventKey k) {
            long code = k.getPhysicalKeycode().getValue();
            if (code == 0) code = k.getKeycode().getValue();
            return code == 0 ? null : "key:" + code;
        }
        if (e instanceof InputEventMouseButton m) return "mouse:" + m.getButtonIndex().getValue();
        return null;
    }

    private static InputEvent eventOf(String spec) {
        if (spec == null) return null;
        try {
            if (spec.startsWith("key:")) {
                InputEventKey k = new InputEventKey();
                k.setPhysicalKeycode(Key.Companion.from(Long.parseLong(spec.substring(4))));
                return k;
            }
            if (spec.startsWith("mouse:")) {
                InputEventMouseButton m = new InputEventMouseButton();
                m.setButtonIndex(MouseButton.Companion.from(Long.parseLong(spec.substring(6))));
                return m;
            }
        } catch (RuntimeException e) {
            return null;
        }
        return null;
    }

    private static String firstSpec(String action) {
        if (!InputMap.hasAction(action)) return null;
        VariantArray<InputEvent> events = InputMap.actionGetEvents(action);
        for (int i = 0; i < events.size(); i++) {
            String s = specOf(events.get(i));
            if (s != null) return s;
        }
        return null;
    }

    /** Give {@code rowId} the key of {@code spec} (swapping with a row that held it). True when anything changed. */
    public static boolean rebind(String rowId, String spec) {
        init();
        List<BindingTable.Change> changes = TABLE.rebind(rowId, spec);
        if (changes.isEmpty()) return false;
        Set<String> actions = new LinkedHashSet<>();
        for (BindingTable.Change c : changes) actions.addAll(BindingTable.row(c.rowId()).actions());
        for (String a : actions) rebuild(a);
        return true;
    }

    /** An action's keyboard/mouse events = the keys of every row that holds it; its pad events are kept. */
    private static void rebuild(String action) {
        if (!InputMap.hasAction(action)) return;
        VariantArray<InputEvent> events = InputMap.actionGetEvents(action);
        List<InputEvent> keep = new ArrayList<>();
        for (int i = 0; i < events.size(); i++) if (specOf(events.get(i)) == null) keep.add(events.get(i));
        InputMap.actionEraseEvents(action);
        for (InputEvent e : keep) InputMap.actionAddEvent(action, e);
        Set<String> specs = new LinkedHashSet<>();
        for (BindingTable.Row r : BindingTable.ROWS)
            if (r.actions().contains(action) && TABLE.keyOf(r.id()) != null) specs.add(TABLE.keyOf(r.id()));
        for (String s : specs) {
            InputEvent e = eventOf(s);
            if (e != null) InputMap.actionAddEvent(action, e);
        }
    }

    /** Every row back to project.godot's key. */
    public static void resetDefaults() {
        init();
        Set<String> actions = new LinkedHashSet<>();
        for (BindingTable.Row r : BindingTable.ROWS) {
            TABLE.set(r.id(), DEFAULTS.get(r.id()));
            actions.addAll(r.actions());
        }
        for (String a : actions) rebuild(a);
    }

    /** Apply {@code [bindings]} from settings.cfg (rows the file does not name keep their default). */
    public static void load(ConfigFile cf) {
        init();
        for (BindingTable.Row r : BindingTable.ROWS) {
            Object v = cf.getValue("bindings", r.id(), "");
            String spec = v == null ? "" : String.valueOf(v);
            if (!spec.isEmpty() && eventOf(spec) != null) rebind(r.id(), spec);
        }
    }

    /** Write the rows that differ from the default into {@code [bindings]}. */
    public static void save(ConfigFile cf) {
        init();
        for (BindingTable.Row r : BindingTable.ROWS) {
            String now = TABLE.keyOf(r.id());
            if (now != null && !now.equals(DEFAULTS.get(r.id()))) cf.setValue("bindings", r.id(), now);
        }
    }

    /** The row's key now, as a label ("E", "Space", "RMB"). */
    public static String label(String rowId) {
        init();
        return BindingTable.label(TABLE.keyOf(rowId), KeyBindings::keyName);
    }

    /** Spec of a row's key now (probe readout). */
    public static String specNow(String rowId) { init(); return TABLE.keyOf(rowId); }

    private static String keyName(long physical) {
        try {
            Key k = Key.Companion.from(physical);
            Key shown = DisplayServer.keyboardGetKeycodeFromPhysical(k);
            String s = OS.getKeycodeString(shown.getValue() != 0 ? shown : k);
            return s == null || s.isEmpty() ? "?" : s;
        } catch (RuntimeException e) {
            return "?";
        }
    }

    /**
     * The key a prompt names, as BOUND NOW: prompts are written with the default letter ("[ F ]  Enter vehicle"; none
     * = E), which names an action ({@code KeyGlyph.actionOf}); its row's current key is what the player must press.
     * The letter itself when the action is unknown or has no keyboard binding.
     */
    public static String shownKey(String defaultLetter) {
        String action = com.openworld.ui.KeyGlyph.actionOf(defaultLetter);
        if (action == null) return defaultLetter;
        for (BindingTable.Row r : BindingTable.ROWS) {
            if (r.actions().contains(action)) {
                String l = label(r.id());
                return "?".equals(l) ? defaultLetter : l.length() == 1 ? l.toUpperCase() : l;
            }
        }
        return defaultLetter;
    }
}
