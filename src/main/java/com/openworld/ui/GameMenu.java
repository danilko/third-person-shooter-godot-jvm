package com.openworld.ui;

import com.openworld.character.Player;
import com.openworld.control.BindingTable;
import com.openworld.control.KeyBindings;
import com.openworld.game.QualitySettings;
import com.openworld.game.profile.PlayerProfile;
import com.openworld.game.profile.Profiles;
import com.openworld.game.profile.VehicleInstanceData;
import com.openworld.weapon.WeaponItem;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Button;
import godot.api.CheckButton;
import godot.api.ColorRect;
import godot.api.Control;
import godot.api.HBoxContainer;
import godot.api.HSeparator;
import godot.api.HSlider;
import godot.api.InputEvent;
import godot.api.InputEventJoypadButton;
import godot.api.InputEventJoypadMotion;
import godot.api.InputEventKey;
import godot.api.InputEventMouseButton;
import godot.api.Label;
import godot.api.MarginContainer;
import godot.api.Node;
import godot.api.OptionButton;
import godot.api.ScrollContainer;
import godot.api.VBoxContainer;
import godot.core.Callable;
import godot.core.Color;
import godot.core.MethodCallable;
import godot.core.StringName;
import godot.core.Vector2;
import godot.global.GD;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * The ONE full-screen menu (user, 2026-10-10: the small centred pause / settings / key-binding windows were hard to
 * read and their transparent panels stacked over each other). One opaque backdrop, tabs along the top, each tab a
 * whole-screen page in a larger font:
 *
 * <ul>
 *   <li><b>STATUS</b> (in game only) -- the player (health, money, debt, wanted), the weapons carried with their
 *       ammunition, the cars owned;</li>
 *   <li><b>CONTROLS</b> -- two columns side by side: KEYBOARD &amp; MOUSE (sensitivity, one rebindable row per
 *       {@link BindingTable#ROWS}) and CONTROLLER (look speed, invert, aim assist, one rebindable row per
 *       {@link BindingTable#PAD_ROWS});</li>
 *   <li><b>DISPLAY</b> -- preset, render scale, shadow / view distance, window, size, vsync, field of view;</li>
 *   <li><b>GAME</b> -- volume, HUD mode, and the session buttons (resume / restart / quit to title / quit; on the
 *       title only Back).</li>
 * </ul>
 *
 * Built in code. {@link PauseMenu} is the in-game form ({@link #inGame}), {@link SettingsMenu} the title's. Tabs:
 * click, LB / RB on a pad, PageUp / PageDown on a keyboard. A binding button waits for the next key (or pad button /
 * trigger); Esc cancels the wait. Settings are written to settings.cfg when the menu is hidden or closed.
 */
@Script(className = "GameMenu")
public class GameMenu extends Control {

    static final int FONT = 22, FONT_HEAD = 28;
    static final float ROW_H = 42f;

    /** True for the pause menu: it has STATUS and the session buttons, and MenuManager owns its open / close. */
    protected boolean inGame;

    private final List<String> tabNames = new ArrayList<>();
    private final List<Control> pages = new ArrayList<>();
    private final List<Button> tabButtons = new ArrayList<>();
    private int tab;
    private boolean built, syncing;
    /** Something was changed since the last write of settings.cfg (a menu merely opened and closed writes nothing). */
    private boolean dirty;

    private VBoxContainer statusLeft, statusRight;
    private OptionButton presetBox, windowMode, resolution, worldDensity;
    private HSlider renderScale, shadowDist, viewDist, lookSens, padLook, volume, fov;
    private CheckButton invertY, aimAssist, hudMinimal, vsync;
    private final Map<HSlider, Label> sliderValues = new LinkedHashMap<>();
    /** "key_<row>" / "pad_<row>" -> its button. */
    private final Map<String, Button> bindButtons = new LinkedHashMap<>();
    /** The binding button waiting for its input ("key_interact", "pad_jump"), or null. */
    private String capturing;

    @Register
    @Override
    public void _ready() {
        build();
    }

    protected void build() {
        if (built) return;
        built = true;
        setAnchorsPreset(Control.LayoutPreset.PRESET_FULL_RECT, false);
        setMouseFilter(Control.MouseFilter.STOP);
        setProcessMode(Node.ProcessMode.ALWAYS);
        godot.api.Theme theme = new godot.api.Theme();
        theme.setDefaultFontSize(FONT);
        if (GD.load(GameClock.FONT) instanceof godot.api.Font f) theme.setDefaultFont(f);
        setTheme(theme);

        // ONE backdrop for the whole menu: nothing translucent is ever stacked on it
        ColorRect back = new ColorRect();
        back.setName("Backdrop");
        back.setAnchorsPreset(Control.LayoutPreset.PRESET_FULL_RECT, false);
        back.setColor(new Color(0.045, 0.055, 0.075, inGame ? 0.96 : 1.0));
        back.setMouseFilter(Control.MouseFilter.IGNORE);
        addChild(back);

        MarginContainer margin = new MarginContainer();
        margin.setAnchorsPreset(Control.LayoutPreset.PRESET_FULL_RECT, false);
        for (String side : new String[] {"margin_left", "margin_right"}) margin.addThemeConstantOverride(new StringName(side), 48);
        for (String side : new String[] {"margin_top", "margin_bottom"}) margin.addThemeConstantOverride(new StringName(side), 28);
        addChild(margin);
        VBoxContainer root = new VBoxContainer();
        root.addThemeConstantOverride(new StringName("separation"), 12);
        margin.addChild(root);

        HBoxContainer bar = new HBoxContainer();
        bar.setName("Tabs");
        bar.addThemeConstantOverride(new StringName("separation"), 8);
        root.addChild(bar);
        root.addChild(new HSeparator());
        Control holder = new Control();
        holder.setName("Pages");
        holder.setVSizeFlags(Control.SizeFlags.EXPAND_FILL);
        root.addChild(holder);
        Label hint = new Label();
        hint.setText("LB / RB  or  PgUp / PgDn: change tab        Esc / B: back");
        hint.addThemeColorOverride(new StringName("font_color"), new Color(1, 1, 1, 0.55));
        hint.addThemeFontSizeOverride(new StringName("font_size"), 18);
        root.addChild(hint);

        if (inGame) addTab(bar, holder, "STATUS", statusPage());
        addTab(bar, holder, "CONTROLS", controlsPage());
        addTab(bar, holder, "DISPLAY", displayPage());
        addTab(bar, holder, "GAME", gamePage());
        Control spacer = new Control();
        spacer.setHSizeFlags(Control.SizeFlags.EXPAND_FILL);
        bar.addChild(spacer);
        Label title = new Label();
        title.setText(inGame ? "PAUSED" : "SETTINGS");
        title.addThemeFontSizeOverride(new StringName("font_size"), FONT_HEAD);
        bar.addChild(title);

        QualitySettings q = QualitySettings.get();
        if (q != null) sync(q);
        refreshBindings();
        connect(new StringName("visibility_changed"), callable("on_visibility_changed"));
        selectTab(0);
    }

    private void addTab(HBoxContainer bar, Control holder, String name, Control page) {
        Button b = new Button();
        b.setName("Tab_" + name);
        b.setText("  " + name + "  ");
        b.setToggleMode(true);
        b.setCustomMinimumSize(new Vector2(190f, 52f));
        b.setFocusMode(Control.FocusMode.ALL);
        b.connect(new StringName("pressed"), callable("on_tab_pressed"));
        bar.addChild(b);
        page.setName("Page_" + name);
        page.setAnchorsPreset(Control.LayoutPreset.PRESET_FULL_RECT, false);
        holder.addChild(page);
        tabNames.add(name);
        tabButtons.add(b);
        pages.add(page);
    }

    // ── pages ──

    private Control statusPage() {
        HBoxContainer h = columns();
        statusLeft = column(h, "PLAYER");
        statusRight = column(h, "WEAPONS");
        return h;
    }

    private Control controlsPage() {
        VBoxContainer page = new VBoxContainer();
        HBoxContainer h = columns();
        h.setVSizeFlags(Control.SizeFlags.EXPAND_FILL);
        page.addChild(h);

        VBoxContainer k = column(h, "KEYBOARD & MOUSE");
        lookSens = slider(k, "Mouse sensitivity", 0.3, 3.0, 0.1, "on_controls");
        note(k, "Press a button, then the new key or mouse button.");
        bindingList(k, BindingTable.ROWS, "key_");

        VBoxContainer p = column(h, "CONTROLLER");
        padLook = slider(p, "Stick look speed", 0.5, 2.0, 0.1, "on_controls");
        invertY = check(p, "Invert stick Y");
        aimAssist = check(p, "Aim assist");
        note(p, "Sticks move and look, Start pauses. Press a button, then the new button or trigger.");
        bindingList(p, BindingTable.PAD_ROWS, "pad_");

        Button reset = new Button();
        reset.setName("ResetControls");
        reset.setText("Reset keyboard and controller to defaults");
        reset.setCustomMinimumSize(new Vector2(0f, ROW_H));
        reset.setHSizeFlags(Control.SizeFlags.SHRINK_CENTER);
        reset.connect(new StringName("pressed"), callable("reset_bindings"));
        page.addChild(reset);
        return page;
    }

    private void bindingList(VBoxContainer col, List<BindingTable.Row> rows, String prefix) {
        ScrollContainer scroll = new ScrollContainer();
        scroll.setHorizontalScrollMode(ScrollContainer.ScrollMode.DISABLED);
        scroll.setVSizeFlags(Control.SizeFlags.EXPAND_FILL);
        scroll.setFollowFocus(true);
        col.addChild(scroll);
        VBoxContainer v = new VBoxContainer();
        v.setHSizeFlags(Control.SizeFlags.EXPAND_FILL);
        scroll.addChild(v);
        for (BindingTable.Row r : rows) {
            Button b = new Button();
            b.setName(prefix + r.id());
            // one handler for every row, reading WHICH from the focus (a bound Callable fails in connect() under
            // godot-jvm rc1): a click or a pad press focuses the button before "pressed" fires
            b.connect(new StringName("pressed"), callable("on_bind_pressed"));
            row(v, r.label(), b);
            bindButtons.put(prefix + r.id(), b);
        }
    }

    private Control displayPage() {
        HBoxContainer h = columns();
        VBoxContainer g = column(h, "GRAPHICS");
        presetBox = new OptionButton();
        for (QualitySettings.Preset p : QualitySettings.Preset.values()) presetBox.addItem(cap(p.name()), p.ordinal());
        row(g, "Preset", presetBox);
        presetBox.connect(new StringName("item_selected"), callable("on_preset"));
        renderScale = slider(g, "Render scale", 0.5, 1.0, 0.05, "on_graphics");
        shadowDist = slider(g, "Shadow distance (m)", QualitySettings.MIN_SHADOW_DISTANCE, 600.0, 10.0, "on_graphics");
        viewDist = slider(g, "View distance (m)", QualitySettings.MIN_VIEW_DISTANCE, 500.0, 10.0, "on_graphics");
        fov = slider(g, "Field of view (+deg)", QualitySettings.FOV_OFFSET_MIN, QualitySettings.FOV_OFFSET_MAX, 1.0, "on_controls");

        VBoxContainer w = column(h, "WINDOW");
        windowMode = new OptionButton();
        windowMode.addItem("Windowed", 0);
        windowMode.addItem("Fullscreen (borderless)", 1);
        windowMode.addItem("Fullscreen (exclusive)", 2);
        row(w, "Mode", windowMode);
        windowMode.connect(new StringName("item_selected"), callable("on_display"));
        resolution = new OptionButton();
        resolution.addItem("Keep current", 0);
        for (int i = 0; i < QualitySettings.RESOLUTIONS.length; i++) resolution.addItem(QualitySettings.RESOLUTIONS[i], i + 1);
        row(w, "Resolution", resolution);
        resolution.connect(new StringName("item_selected"), callable("on_display"));
        vsync = new CheckButton();
        row(w, "VSync", vsync);
        vsync.connect(new StringName("toggled"), callable("on_display_toggled"));
        return h;
    }

    private Control gamePage() {
        HBoxContainer h = columns();
        VBoxContainer o = column(h, "OPTIONS");
        volume = slider(o, "Master volume", 0.0, 1.0, 0.05, "on_controls");
        hudMinimal = check(o, "Minimal HUD");
        worldDensity = new OptionButton();
        for (com.openworld.game.WorldDensity d : com.openworld.game.WorldDensity.values()) worldDensity.addItem(d.label, d.ordinal());
        worldDensity.setName("WorldDensity");
        row(o, "World density", worldDensity);
        worldDensity.connect(new StringName("item_selected"), callable("on_display"));
        note(o, "Cars, pedestrians and attackers at once. The host's choice in co-op, the same for every player. Normal is tuned for the Steam Deck.");
        VBoxContainer s = column(h, inGame ? "SESSION" : "");
        if (inGame) {
            action(s, "Resume", "Resume", "on_resume_pressed");
            action(s, "Restart", "Restart", "on_restart_pressed");
            action(s, "QuitToTitle", "Quit to title", "on_quit_to_title_pressed");
            action(s, "Quit", "Quit game", "on_quit_pressed");
        } else {
            action(s, "Back", "Back", "close");
        }
        return h;
    }

    // ── the session buttons: PauseMenu / SettingsMenu give them their meaning ──

    @Register public void onResumePressed() {}
    @Register public void onRestartPressed() {}
    @Register public void onQuitToTitlePressed() {}
    @Register public void onQuitPressed() {}
    @Register public void close() { save(); }

    // ── tabs ──

    @Register
    public void onTabPressed() {
        Control f = getViewport().guiGetFocusOwner();
        for (int i = 0; i < tabButtons.size(); i++)
            if (f != null && tabButtons.get(i).getInstanceId() == f.getInstanceId()) { selectTab(i); return; }
        selectTab(tab);   // keep the toggle state honest
    }

    public void selectTab(int index) {
        if (pages.isEmpty()) return;
        tab = Math.floorMod(index, pages.size());
        capturing = null;
        for (int i = 0; i < pages.size(); i++) {
            pages.get(i).setVisible(i == tab);
            tabButtons.get(i).setPressedNoSignal(i == tab);
        }
        if ("STATUS".equals(tabNames.get(tab))) refreshStatus();
        refreshBindings();
    }

    /** Select a tab by name and put the focus on it (also the probes' way in). */
    @Register
    public boolean selectTabNow(String name) {
        int i = tabNames.indexOf(name);
        if (i < 0) return false;
        selectTab(i);
        if (isVisibleInTree()) tabButtons.get(i).grabFocus();
        return true;
    }

    @Register public String tabNow() { return tabNames.isEmpty() ? "" : tabNames.get(tab); }
    @Register public String tabsNow() { return String.join(",", tabNames); }
    @Register public String capturingNow() { return capturing == null ? "" : capturing; }
    public boolean isCapturing() { return capturing != null; }

    @Register
    public void onVisibilityChanged() {
        if (isVisibleInTree()) {
            QualitySettings q = QualitySettings.get();
            if (q != null) sync(q);
            selectTab(0);
            tabButtons.get(0).grabFocus();
        } else {
            capturing = null;
            save();
        }
    }

    private void save() {
        QualitySettings q = QualitySettings.get();
        if (q != null && dirty && q.save()) dirty = false;
    }

    @Register
    @Override
    public void _input(InputEvent e) {
        if (!isVisibleInTree()) return;
        if (capturing != null) {
            boolean pad = capturing.startsWith("pad_");
            String row = capturing.substring(4);
            if (e instanceof InputEventKey k && k.isPressed() && !k.isEcho()) {
                String spec = KeyBindings.specOf(e);
                if (!pad && spec != null && !BindingTable.reserved(spec)) dirty |= KeyBindings.rebind(row, spec);
                finishCapture();   // any key ends a pad capture too: Esc cancels either
            } else if (!pad && e instanceof InputEventMouseButton m && m.isPressed()) {
                dirty |= KeyBindings.rebind(row, KeyBindings.specOf(e));
                finishCapture();
            } else if (pad && ((e instanceof InputEventJoypadButton b && b.isPressed()) || e instanceof InputEventJoypadMotion)) {
                String spec = KeyBindings.padSpecOf(e);
                if (spec == null) return;   // a stick, or a trigger not pulled yet
                if (!BindingTable.reserved(spec)) dirty |= KeyBindings.rebindPad(row, spec);
                finishCapture();
            }
            return;
        }
        int step = 0;
        if (e instanceof InputEventJoypadButton b && b.isPressed())
            step = b.getButtonIndex().getValue() == 9 ? -1 : b.getButtonIndex().getValue() == 10 ? 1 : 0;
        else if (e instanceof InputEventKey k && k.isPressed() && !k.isEcho())
            step = k.getKeycode() == godot.core.Key.PAGEUP ? -1 : k.getKeycode() == godot.core.Key.PAGEDOWN ? 1 : 0;
        if (step != 0) {
            selectTab(tab + step);
            tabButtons.get(tab).grabFocus();
            getViewport().setInputAsHandled();
            return;
        }
        if (!inGame && e.isActionPressed("ui_cancel", false)) {
            getViewport().setInputAsHandled();
            close();
        }
    }

    private void finishCapture() {
        capturing = null;
        refreshBindings();
        getViewport().setInputAsHandled();
    }

    // ── bindings ──

    @Register
    public void onBindPressed() {
        Control f = getViewport().guiGetFocusOwner();
        for (Map.Entry<String, Button> e : bindButtons.entrySet()) {
            if (f != null && e.getValue().getInstanceId() == f.getInstanceId()) {
                capturing = e.getKey();
                refreshBindings();
                return;
            }
        }
    }

    @Register
    public void resetBindings() {
        KeyBindings.resetDefaults();
        KeyBindings.resetPadDefaults();
        dirty = true;
        capturing = null;
        refreshBindings();
    }

    private void refreshBindings() {
        for (Map.Entry<String, Button> e : bindButtons.entrySet()) {
            String id = e.getKey(), row = id.substring(4);
            boolean pad = id.startsWith("pad_");
            e.getValue().setText(id.equals(capturing) ? (pad ? "press a button..." : "press a key...")
                    : pad ? KeyBindings.padLabel(row) : KeyBindings.label(row));
        }
    }

    // ── status ──

    private void refreshStatus() {
        if (statusLeft == null) return;
        clearRows(statusLeft);
        clearRows(statusRight);
        Player me = null;
        for (Player p : com.openworld.game.PlayerRegistry.getPlayers())
            if (GD.isInstanceValid(p) && p.isLocallyOwnedPlayer()) { me = p; break; }
        PlayerProfile prof = Profiles.local();
        if (me != null && me.getCharacterInfo() != null) {
            fact(statusLeft, "Name", me.getCharacterInfo().displayName, null);
            fact(statusLeft, "Faction", me.getCharacterInfo().faction, null);
        }
        if (me != null && me.getNodeOrNull("Health") instanceof com.openworld.character.Health h) {
            double f = h.maxHealth > 0 ? h.getCurrentHealth() / h.maxHealth : 0;
            fact(statusLeft, "Health", Math.round(h.getCurrentHealth()) + " / " + Math.round(h.maxHealth),
                    f < 0.35 ? HudPalette.CRITICAL : null);
        }
        fact(statusLeft, "Money", CashReadout.yen(prof.balance), prof.balance < 0 ? HudPalette.CRITICAL : null);
        long loans = 0;
        for (PlayerProfile.Debt d : prof.debts) loans += d.principal();
        if (loans > 0) fact(statusLeft, "Loans", CashReadout.yen(loans), HudPalette.WARN);
        var ws = com.openworld.game.WantedSystem.get();
        if (ws != null && me != null && me.getCharacterInfo() != null) {
            var shown = ws.hudOf(me.getCharacterInfo().characterId);
            fact(statusLeft, "Police", stars(shown.stars()), shown.stars() > 0 ? HudPalette.WARN : null);
            if (shown.gangStars() > 0) fact(statusLeft, "Gang (" + shown.gang() + ")", stars(shown.gangStars()), HudPalette.CRITICAL);
        }

        int weapons = 0;
        var wc = me != null ? me.weaponController : null;
        for (int i = 0; wc != null && i < wc.slotCount(); i++) {
            WeaponItem w = wc.getWeaponItem(i);
            if (w == null) continue;
            int mag = w.getReplicatedMagazine(), res = w.getReplicatedReserve();
            fact(statusRight, (i == wc.getWeapon() ? "> " : "") + w.getDisplayName(),
                    mag == 0 && res == 0 ? "" : mag + " / " + res, i == wc.getWeapon() ? HudPalette.WARN : null);
            weapons++;
        }
        if (weapons == 0) fact(statusRight, "Nothing carried", "", null);
        heading(statusRight, "CARS OWNED");
        if (prof.vehicles.isEmpty()) fact(statusRight, "None (park one in the yellow bay at home)", "", null);
        for (VehicleInstanceData v : prof.vehicles) {
            String model = v.model.substring(v.model.lastIndexOf('/') + 1).replace(".tscn", "");
            fact(statusRight, model, Math.round(v.condition * 100) + " %   " + (v.garageId.isEmpty() ? "out" : "in garage"), null);
        }
    }

    private static String stars(int n) { return n <= 0 ? "none" : "★".repeat(n); }

    /** The status page as text, "Name=..;Money=..|AR4=30 / 90;.." (probe readout). */
    @Register
    public String statusTextNow() {
        refreshStatus();
        return rowsText(statusLeft) + "|" + rowsText(statusRight);
    }

    private static String rowsText(VBoxContainer v) {
        StringBuilder b = new StringBuilder();
        if (v == null) return "";
        for (Node n : v.getChildren()) {
            if (!(n instanceof HBoxContainer h) || h.getChildCount() < 2 || h.isQueuedForDeletion()) continue;
            if (h.getChild(0) instanceof Label k && h.getChild(1) instanceof Label val)
                b.append(b.length() == 0 ? "" : ";").append(k.getText()).append('=').append(val.getText());
        }
        return b.toString();
    }

    /** Remove a column's rows but keep its heading (the first child). */
    private static void clearRows(VBoxContainer v) {
        for (Node n : v.getChildren()) {
            if (n.getIndex() == 0) continue;
            v.removeChild(n);
            n.queueFree();
        }
    }

    // ── settings <-> widgets (the handlers SettingsMenu had) ──

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
        worldDensity.select(q.worldDensity.ordinal());
        fov.setValue(q.fovOffset);
        windowMode.select(q.windowMode.ordinal());
        int r = java.util.Arrays.asList(QualitySettings.RESOLUTIONS).indexOf(q.resolution);
        resolution.select(r < 0 ? 0 : r + 1);
        vsync.setPressed(q.vsync);
        syncing = false;
        showValues();
    }

    private void showValues() {
        // a switch spells its state: the default theme's "off" is a faint dot at this size
        for (CheckButton c : new CheckButton[] {invertY, aimAssist, hudMinimal, vsync})
            if (c != null) c.setText(c.isPressed() ? "On" : "Off");
        for (Map.Entry<HSlider, Label> e : sliderValues.entrySet()) {
            double v = e.getKey().getValue(), step = e.getKey().getStep();
            e.getValue().setText(step >= 1.0 ? String.valueOf(Math.round(v)) : String.format(java.util.Locale.ROOT, "%.2f", v));
        }
    }

    @Register
    public void onPreset(long index) {
        QualitySettings q = QualitySettings.get();
        if (q == null || syncing) return;
        dirty = true;
        q.setPreset(QualitySettings.Preset.values()[(int) index]);
        q.apply();
        sync(q);
    }

    @Register
    public void onGraphics(double ignored) {
        showValues();
        QualitySettings q = QualitySettings.get();
        if (q == null || syncing) return;
        dirty = true;
        q.renderScale = renderScale.getValue();
        q.shadowDistance = shadowDist.getValue();
        q.viewDistance = viewDist.getValue();
        q.graphicsChanged();
        q.apply();
        syncing = true;
        presetBox.select(q.preset.ordinal());
        syncing = false;
    }

    @Register public void onControls(double ignored) { showValues(); readControls(); }
    @Register public void onToggled(boolean ignored) { showValues(); readControls(); }

    private void readControls() {
        QualitySettings q = QualitySettings.get();
        if (q == null || syncing) return;
        dirty = true;
        q.lookSensitivity = lookSens.getValue();
        q.padLookScale = padLook.getValue();
        q.invertY = invertY.isPressed();
        q.aimAssist = aimAssist.isPressed();
        q.masterVolume = volume.getValue();
        q.hudMinimal = hudMinimal.isPressed();
        q.fovOffset = fov.getValue();
        q.apply();
    }

    @Register public void onDisplay(long ignored) { readDisplay(); }
    @Register public void onDisplayToggled(boolean ignored) { showValues(); readDisplay(); }

    private void readDisplay() {
        QualitySettings q = QualitySettings.get();
        if (q == null || syncing) return;
        dirty = true;
        q.windowMode = QualitySettings.WindowMode.values()[Math.max(0, windowMode.getSelected())];
        int r = resolution.getSelected();
        q.resolution = r <= 0 ? "" : QualitySettings.RESOLUTIONS[r - 1];
        q.vsync = vsync.isPressed();
        q.worldDensity = com.openworld.game.WorldDensity.values()[Math.max(0, worldDensity.getSelected())];
        q.apply();
    }

    // ── builders ──

    private static HBoxContainer columns() {
        HBoxContainer h = new HBoxContainer();
        h.addThemeConstantOverride(new StringName("separation"), 56);
        return h;
    }

    private VBoxContainer column(HBoxContainer h, String title) {
        VBoxContainer v = new VBoxContainer();
        v.setHSizeFlags(Control.SizeFlags.EXPAND_FILL);
        v.addThemeConstantOverride(new StringName("separation"), 6);
        h.addChild(v);
        heading(v, title);
        return v;
    }

    private void heading(VBoxContainer v, String text) {
        Label l = new Label();
        l.setText(text);
        l.addThemeFontSizeOverride(new StringName("font_size"), FONT_HEAD);
        l.addThemeColorOverride(new StringName("font_color"), HudPalette.WARN);
        l.setCustomMinimumSize(new Vector2(0f, 48f));
        v.addChild(l);
    }

    private void note(VBoxContainer v, String text) {
        Label l = new Label();
        l.setText(text);
        l.setAutowrapMode(godot.api.TextServer.AutowrapMode.WORD_SMART);
        l.addThemeFontSizeOverride(new StringName("font_size"), 18);
        l.addThemeColorOverride(new StringName("font_color"), new Color(1, 1, 1, 0.6));
        v.addChild(l);
    }

    /** A label on the left half, the control on the right half, one tall row. */
    private HBoxContainer row(VBoxContainer v, String label, Control control) {
        HBoxContainer h = new HBoxContainer();
        h.setCustomMinimumSize(new Vector2(0f, ROW_H));
        Label l = new Label();
        l.setText(label);
        l.setHSizeFlags(Control.SizeFlags.EXPAND_FILL);
        l.setClipText(true);
        h.addChild(l);
        control.setHSizeFlags(Control.SizeFlags.EXPAND_FILL);
        control.setVSizeFlags(Control.SizeFlags.SHRINK_CENTER);
        control.setCustomMinimumSize(new Vector2(0f, ROW_H - 6f));
        control.setFocusMode(Control.FocusMode.ALL);
        h.addChild(control);
        v.addChild(h);
        return h;
    }

    private void fact(VBoxContainer v, String key, String value, Color color) {
        HBoxContainer h = new HBoxContainer();
        h.setCustomMinimumSize(new Vector2(0f, ROW_H));
        Label k = new Label();
        k.setText(key);
        k.setHSizeFlags(Control.SizeFlags.EXPAND_FILL);
        Label val = new Label();
        val.setText(value);
        val.setHSizeFlags(Control.SizeFlags.EXPAND_FILL);
        if (color != null) {
            k.addThemeColorOverride(new StringName("font_color"), color);
            val.addThemeColorOverride(new StringName("font_color"), color);
        }
        h.addChild(k);
        h.addChild(val);
        v.addChild(h);
    }

    private HSlider slider(VBoxContainer v, String label, double min, double max, double step, String handler) {
        HSlider s = new HSlider();
        s.setMin(min);
        s.setMax(max);
        s.setStep(step);
        HBoxContainer h = row(v, label, s);
        Label value = new Label();
        value.setCustomMinimumSize(new Vector2(72f, 0f));
        value.setHorizontalAlignment(godot.core.HorizontalAlignment.RIGHT);
        h.addChild(value);
        sliderValues.put(s, value);
        s.connect(new StringName("value_changed"), callable(handler));
        return s;
    }

    private CheckButton check(VBoxContainer v, String label) {
        CheckButton c = new CheckButton();
        row(v, label, c);
        c.setHSizeFlags(Control.SizeFlags.SHRINK_BEGIN);
        c.connect(new StringName("toggled"), callable("on_toggled"));
        return c;
    }

    private void action(VBoxContainer v, String name, String text, String handler) {
        Button b = new Button();
        b.setName(name);
        b.setText(text);
        b.setCustomMinimumSize(new Vector2(0f, 56f));
        b.setFocusMode(Control.FocusMode.ALL);
        b.connect(new StringName("pressed"), callable(handler));
        v.addChild(b);
    }

    private Callable callable(String method) { return MethodCallable.createUnsafe(this, method); }

    private static String cap(String s) { return s.charAt(0) + s.substring(1).toLowerCase(); }
}
