package com.openworld.ui;

import com.openworld.game.QualitySettings;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Button;
import godot.api.CheckButton;
import godot.api.Control;
import godot.api.HBoxContainer;
import godot.api.HSlider;
import godot.api.Label;
import godot.api.Node;
import godot.api.OptionButton;
import godot.api.PanelContainer;
import godot.api.VBoxContainer;
import godot.core.Callable;
import godot.core.MethodCallable;
import godot.core.StringName;
import godot.core.Vector2;

import java.util.ArrayList;
import java.util.List;

/**
 * The settings page (PLAN.md 1.3 / F2): every value {@link QualitySettings} owns, one row each, built in code. Opened
 * from the pause menu and the title screen ({@link #open}); Back (or ui_cancel) saves and closes. Works on a pad: the
 * first row takes focus, D-pad up/down moves, left/right moves a slider or the preset, A toggles a switch.
 * A graphics value moved by hand turns the preset to Custom; picking a preset sets the three graphics values.
 */
@Script(className = "SettingsMenu")
public class SettingsMenu extends Control {

    private Node returnFocusTo;
    private OptionButton presetBox;
    private HSlider renderScale, shadowDist, viewDist, lookSens, padLook, volume, fov;
    private CheckButton invertY, aimAssist, hudMinimal, vsync;
    private OptionButton windowMode, resolution;
    private Button keysButton;
    private boolean syncing;
    private static int opens;

    /** Open over {@code parent} (a CanvasLayer / Control); focus returns to {@code returnFocusTo} on close. */
    public static SettingsMenu open(Node parent, Node returnFocusTo) {
        SettingsMenu m = new SettingsMenu();
        m.returnFocusTo = returnFocusTo;
        m.setName("SettingsMenu");
        m.setProcessMode(Node.ProcessMode.ALWAYS);
        parent.addChild(m);
        opens++;
        return m;
    }

    @Register
    @Override
    public void _ready() {
        setAnchorsPreset(Control.LayoutPreset.PRESET_FULL_RECT, false);
        setMouseFilter(Control.MouseFilter.STOP);
        PanelContainer panel = new PanelContainer();
        panel.setAnchorsPreset(Control.LayoutPreset.PRESET_CENTER, false);
        panel.setCustomMinimumSize(new Vector2(560f, 0f));
        addChild(panel);
        VBoxContainer v = new VBoxContainer();
        panel.addChild(v);
        Label title = new Label();
        title.setText("SETTINGS");
        v.addChild(title);

        QualitySettings q = QualitySettings.get();
        presetBox = new OptionButton();
        for (QualitySettings.Preset p : QualitySettings.Preset.values()) presetBox.addItem(cap(p.name()), p.ordinal());
        row(v, "Graphics preset", presetBox);
        presetBox.connect(new StringName("item_selected"), callable("on_preset"));
        renderScale = slider(v, "Render scale", 0.5, 1.0, 0.05, "on_graphics");
        shadowDist = slider(v, "Shadow distance (m)", QualitySettings.MIN_SHADOW_DISTANCE, 600.0, 10.0, "on_graphics");
        viewDist = slider(v, "View distance (m)", QualitySettings.MIN_VIEW_DISTANCE, 500.0, 10.0, "on_graphics");
        lookSens = slider(v, "Mouse sensitivity", 0.3, 3.0, 0.1, "on_controls");
        padLook = slider(v, "Stick look speed", 0.5, 2.0, 0.1, "on_controls");
        invertY = check(v, "Invert stick Y", "on_controls");
        aimAssist = check(v, "Aim assist (pad)", "on_controls");
        volume = slider(v, "Master volume", 0.0, 1.0, 0.05, "on_controls");
        hudMinimal = check(v, "Minimal HUD", "on_controls");
        fov = slider(v, "Field of view (+deg)", QualitySettings.FOV_OFFSET_MIN, QualitySettings.FOV_OFFSET_MAX, 1.0, "on_controls");
        windowMode = new OptionButton();
        windowMode.addItem("Windowed", 0);
        windowMode.addItem("Fullscreen (borderless)", 1);
        windowMode.addItem("Fullscreen (exclusive)", 2);
        row(v, "Window", windowMode);
        windowMode.connect(new StringName("item_selected"), callable("on_display"));
        resolution = new OptionButton();
        resolution.addItem("Keep current", 0);
        for (int i = 0; i < QualitySettings.RESOLUTIONS.length; i++) resolution.addItem(QualitySettings.RESOLUTIONS[i], i + 1);
        row(v, "Window size", resolution);
        resolution.connect(new StringName("item_selected"), callable("on_display"));
        vsync = new CheckButton();
        row(v, "VSync", vsync);
        vsync.connect(new StringName("toggled"), callable("on_display_toggled"));
        Button keys = keysButton = new Button();
        keys.setName("KeyBindings");
        keys.setText("Key bindings...");
        keys.connect(new StringName("pressed"), callable("open_key_bindings"));
        v.addChild(keys);
        Button back = new Button();
        back.setText("Back");
        back.connect(new StringName("pressed"), callable("close"));
        v.addChild(back);
        if (q != null) sync(q);
        presetBox.grabFocus();
    }

    @Register
    @Override
    public void _input(godot.api.InputEvent e) {
        if (getNodeOrNull("KeyBindingsMenu") != null) return;   // the sub-page has the keys
        if (e.isActionPressed("ui_cancel", false)) {
            close();
            getViewport().setInputAsHandled();
        }
    }

    private void sync(QualitySettings q) {
        syncing = true;
        presetBox.select(q.preset.ordinal());
        renderScale.setValue(q.renderScale);
        shadowDist.setValue(q.shadowDistance);
        viewDist.setValue(q.viewDistance);
        lookSens.setValue(q.lookSensitivity);
        padLook.setValue(q.padLookScale);
        invertY.setPressed(q.invertY);
        aimAssist.setPressed(q.aimAssist);
        volume.setValue(q.masterVolume);
        hudMinimal.setPressed(q.hudMinimal);
        fov.setValue(q.fovOffset);
        windowMode.select(q.windowMode.ordinal());
        int r = java.util.Arrays.asList(QualitySettings.RESOLUTIONS).indexOf(q.resolution);
        resolution.select(r < 0 ? 0 : r + 1);
        vsync.setPressed(q.vsync);
        syncing = false;
    }

    @Register
    public void onPreset(long index) {
        QualitySettings q = QualitySettings.get();
        if (q == null || syncing) return;
        q.setPreset(QualitySettings.Preset.values()[(int) index]);
        q.apply();
        sync(q);
    }

    @Register
    public void onGraphics(double ignored) {
        QualitySettings q = QualitySettings.get();
        if (q == null || syncing) return;
        q.renderScale = renderScale.getValue();
        q.shadowDistance = shadowDist.getValue();
        q.viewDistance = viewDist.getValue();
        q.graphicsChanged();
        q.apply();
        syncing = true;
        presetBox.select(q.preset.ordinal());
        syncing = false;
    }

    @Register
    public void onControls(double ignored) { readControls(); }

    @Register
    public void onToggled(boolean ignored) { readControls(); }

    private void readControls() {
        QualitySettings q = QualitySettings.get();
        if (q == null || syncing) return;
        q.lookSensitivity = lookSens.getValue();
        q.padLookScale = padLook.getValue();
        q.invertY = invertY.isPressed();
        q.aimAssist = aimAssist.isPressed();
        q.masterVolume = volume.getValue();
        q.hudMinimal = hudMinimal.isPressed();
        q.fovOffset = fov.getValue();
        q.apply();
    }

    @Register
    public void onDisplay(long ignored) { readDisplay(); }

    @Register
    public void onDisplayToggled(boolean ignored) { readDisplay(); }

    private void readDisplay() {
        QualitySettings q = QualitySettings.get();
        if (q == null || syncing) return;
        q.windowMode = QualitySettings.WindowMode.values()[Math.max(0, windowMode.getSelected())];
        int r = resolution.getSelected();
        q.resolution = r <= 0 ? "" : QualitySettings.RESOLUTIONS[r - 1];
        q.vsync = vsync.isPressed();
        q.apply();
    }

    /** The key bindings sub-page, over this one; focus comes back to its button. */
    @Register
    public void openKeyBindings() {
        if (getNodeOrNull("KeyBindingsMenu") == null) KeyBindingsMenu.open(this, keysButton);
    }

    @Register
    public void close() {
        QualitySettings q = QualitySettings.get();
        if (q != null) q.save();
        if (returnFocusTo instanceof Control c && godot.global.GD.isInstanceValid(c) && c.isVisibleInTree()) c.grabFocus();
        queueFree();
    }

    // ── row builders ──

    private void row(VBoxContainer v, String label, Control control) {
        HBoxContainer h = new HBoxContainer();
        Label l = new Label();
        l.setText(label);
        l.setCustomMinimumSize(new Vector2(240f, 0f));
        h.addChild(l);
        control.setCustomMinimumSize(new Vector2(280f, 0f));
        control.setFocusMode(Control.FocusMode.ALL);
        h.addChild(control);
        v.addChild(h);
    }

    private HSlider slider(VBoxContainer v, String label, double min, double max, double step, String handler) {
        HSlider s = new HSlider();
        s.setMin(min);
        s.setMax(max);
        s.setStep(step);
        row(v, label, s);
        s.connect(new StringName("value_changed"), callable(handler));
        return s;
    }

    private CheckButton check(VBoxContainer v, String label, String handler) {
        CheckButton c = new CheckButton();
        row(v, label, c);
        c.connect(new StringName("toggled"), callable("on_toggled"));
        return c;
    }

    private Callable callable(String method) {
        return MethodCallable.createUnsafe(this, method);
    }

    private static String cap(String s) { return s.charAt(0) + s.substring(1).toLowerCase(); }

    /** Times the page was opened (probe readout through the title / pause menu's own readouts). */
    public static int opensNow() { return opens; }
}
