package com.openworld.ui;

import com.openworld.control.BindingTable;
import com.openworld.control.KeyBindings;
import com.openworld.game.QualitySettings;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Button;
import godot.api.Control;
import godot.api.HBoxContainer;
import godot.api.InputEvent;
import godot.api.InputEventKey;
import godot.api.InputEventMouseButton;
import godot.api.Label;
import godot.api.Node;
import godot.api.PanelContainer;
import godot.api.ScrollContainer;
import godot.api.VBoxContainer;
import godot.core.MethodCallable;
import godot.core.StringName;
import godot.core.Vector2;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * The key bindings page (PLAN.md 1.3 / F2), opened from the settings page: one row per {@link BindingTable} control
 * with its key on a button. Press the button, then the new key or mouse button; Esc cancels the capture (Esc itself is
 * never bindable -- it is pause / back everywhere). A key another row holds is swapped to that row. "Reset to defaults"
 * puts back project.godot's keys; Back (or Esc when not capturing) saves settings.cfg and closes. Keyboard and mouse
 * only: the pad keeps its fixed layout (docs/input.md; Steam Input remaps a pad on the Deck).
 */
@Script(className = "KeyBindingsMenu")
public class KeyBindingsMenu extends Control {

    private Node returnFocusTo;
    private final Map<String, Button> keys = new LinkedHashMap<>();
    /** The row waiting for its new key, or null. */
    private String capturing;
    private static int rebinds;

    public static KeyBindingsMenu open(Node parent, Node returnFocusTo) {
        KeyBindingsMenu m = new KeyBindingsMenu();
        m.returnFocusTo = returnFocusTo;
        m.setName("KeyBindingsMenu");
        m.setProcessMode(Node.ProcessMode.ALWAYS);
        parent.addChild(m);
        return m;
    }

    @Register
    @Override
    public void _ready() {
        setAnchorsPreset(Control.LayoutPreset.PRESET_FULL_RECT, false);
        setMouseFilter(Control.MouseFilter.STOP);
        PanelContainer panel = new PanelContainer();
        panel.setAnchorsPreset(Control.LayoutPreset.PRESET_CENTER, false);
        panel.setCustomMinimumSize(new Vector2(560f, 520f));
        addChild(panel);
        VBoxContainer outer = new VBoxContainer();
        panel.addChild(outer);
        Label title = new Label();
        title.setText("KEY BINDINGS  (press a key's button, then the new key; Esc cancels)");
        outer.addChild(title);
        ScrollContainer scroll = new ScrollContainer();
        scroll.setVerticalScrollMode(ScrollContainer.ScrollMode.AUTO);
        scroll.setHorizontalScrollMode(ScrollContainer.ScrollMode.DISABLED);
        scroll.setCustomMinimumSize(new Vector2(540f, 420f));
        outer.addChild(scroll);
        VBoxContainer v = new VBoxContainer();
        scroll.addChild(v);
        for (BindingTable.Row r : BindingTable.ROWS) {
            HBoxContainer h = new HBoxContainer();
            Label l = new Label();
            l.setText(r.label());
            l.setCustomMinimumSize(new Vector2(300f, 0f));
            h.addChild(l);
            Button b = new Button();
            b.setName(r.id());
            b.setCustomMinimumSize(new Vector2(200f, 0f));
            b.setFocusMode(Control.FocusMode.ALL);
            // one handler for every row, reading WHICH from the focus: a click or a pad press focuses the button before
            // "pressed" fires. (A bound Callable -- MethodCallable.bindUnsafe -- fails in connect() under godot-jvm rc1
            // with "Cannot call a method on a previously freed instance".)
            b.connect(new StringName("pressed"), MethodCallable.createUnsafe(this, "on_key_pressed"));
            h.addChild(b);
            v.addChild(h);
            keys.put(r.id(), b);
        }
        HBoxContainer foot = new HBoxContainer();
        Button reset = new Button();
        reset.setText("Reset to defaults");
        reset.connect(new StringName("pressed"), MethodCallable.createUnsafe(this, "reset"));
        foot.addChild(reset);
        Button back = new Button();
        back.setName("Back");
        back.setText("Back");
        back.connect(new StringName("pressed"), MethodCallable.createUnsafe(this, "close"));
        foot.addChild(back);
        outer.addChild(foot);
        refresh();
        Button first = keys.values().iterator().next();
        first.grabFocus();
    }

    private void refresh() {
        for (Map.Entry<String, Button> e : keys.entrySet())
            e.getValue().setText(e.getKey().equals(capturing) ? "press a key..." : KeyBindings.label(e.getKey()));
    }

    @Register
    public void onKeyPressed() {
        Control f = getViewport().guiGetFocusOwner();
        for (Map.Entry<String, Button> e : keys.entrySet()) {
            if (f != null && e.getValue().getInstanceId() == f.getInstanceId()) {
                capturing = e.getKey();
                refresh();
                return;
            }
        }
    }

    @Register
    @Override
    public void _input(InputEvent e) {
        if (capturing != null) {
            boolean press = (e instanceof InputEventKey k && k.isPressed() && !k.isEcho())
                    || (e instanceof InputEventMouseButton m && m.isPressed());
            if (!press) return;
            getViewport().setInputAsHandled();
            String spec = KeyBindings.specOf(e);
            if (spec != null && !BindingTable.reserved(spec) && KeyBindings.rebind(capturing, spec)) rebinds++;
            capturing = null;
            refresh();
            return;
        }
        if (e.isActionPressed("ui_cancel", false)) {
            close();
            getViewport().setInputAsHandled();
        }
    }

    @Register
    public void reset() {
        KeyBindings.resetDefaults();
        capturing = null;
        refresh();
    }

    @Register
    public void close() {
        QualitySettings q = QualitySettings.get();
        if (q != null) q.save();
        if (returnFocusTo instanceof Control c && godot.global.GD.isInstanceValid(c) && c.isVisibleInTree()) c.grabFocus();
        queueFree();
    }

    /** Probe readouts. */
    @Register public String capturingNow() { return capturing == null ? "" : capturing; }
    public static int rebindsNow() { return rebinds; }
}
