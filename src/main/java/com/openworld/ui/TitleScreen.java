package com.openworld.ui;

import com.openworld.game.FrontEnd;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Button;
import godot.api.CenterContainer;
import godot.api.ColorRect;
import godot.api.Control;
import godot.api.Input;
import godot.api.Label;
import godot.api.LineEdit;
import godot.api.Node;
import godot.api.VBoxContainer;
import godot.core.Color;
import godot.core.MethodCallable;
import godot.core.StringName;
import godot.core.Vector2;

/**
 * The title screen, the game's main scene (PLAN.md 1.3 / F2): Continue (the autosave), New game, Host co-op, Join
 * co-op (an address), Settings, Quit. Replaces booting straight into the world with co-op on debug keys F6 / F7 (those
 * still work in the world). Built in code; the first enabled button takes focus so a pad works at once. The world-side
 * half of each choice runs in {@link FrontEnd} once the world is up.
 *
 * <p>The first title of a run is covered by the FICTION NOTICE ({@link #NOTICE}; user, 2026-10-12): a full-screen
 * page over the menu with one button, which holds the focus until it is pressed. Once per launch, so "Quit to title"
 * does not show it again.
 */
@Script(className = "TitleScreen")
public class TitleScreen extends Control {

    /** The fiction notice, shown before the menu on the first title of a run. Wording is the user's to settle. */
    public static final String NOTICE =
            "This game is a work of fiction.\n\n"
            + "Its story, characters, organisations, places and events are imaginary. Nothing in it is intended to "
            + "depict, represent or comment on any real person, living or dead, or any real organisation, company, "
            + "religion, nation, place or event.\n\n"
            + "Any resemblance to them is coincidental and unintended.";

    /** The notice has been acknowledged in this run (process-wide: the title is rebuilt on every return to it). */
    private static boolean noticeAcknowledged;

    private LineEdit address;
    private Button first;

    @Register
    @Override
    public void _ready() {
        Input.INSTANCE.setMouseMode(Input.MouseMode.VISIBLE);
        setAnchorsPreset(Control.LayoutPreset.PRESET_FULL_RECT, false);
        ColorRect bg = new ColorRect();
        bg.setColor(new Color(0.07, 0.08, 0.11, 1.0));
        bg.setAnchorsPreset(Control.LayoutPreset.PRESET_FULL_RECT, false);
        addChild(bg);
        VBoxContainer v = new VBoxContainer();
        v.setName("Buttons");
        v.setAnchorsPreset(Control.LayoutPreset.PRESET_CENTER, false);
        v.setCustomMinimumSize(new Vector2(360f, 0f));
        addChild(v);
        Label title = new Label();
        title.setText("OPEN WORLD");
        title.setHorizontalAlignment(godot.core.HorizontalAlignment.CENTER);
        v.addChild(title);
        var save = com.openworld.game.SaveSystem.get();
        boolean canContinue = save != null && save.hasSlot(save.autosaveSlot);
        button(v, "Continue", "on_continue").setDisabled(!canContinue);
        button(v, "New game", "on_new_game");
        button(v, "Host co-op", "on_host");
        address = new LineEdit();
        address.setName("Address");
        address.setText("127.0.0.1");
        address.setPlaceholder("host address");
        v.addChild(address);
        button(v, "Join co-op", "on_join");
        button(v, "Settings", "on_settings");
        button(v, "Quit", "on_quit");
        if (noticeAcknowledged) MenuManager.focusFirstButton(v);
        else showNotice();
    }

    /** The notice page: opaque, over the whole menu (it takes the mouse), its one button focused for pad and keys. */
    private void showNotice() {
        ColorRect page = new ColorRect();
        page.setName("Notice");
        page.setColor(new Color(0.03, 0.03, 0.04, 1.0));
        page.setAnchorsPreset(Control.LayoutPreset.PRESET_FULL_RECT, false);
        addChild(page);
        CenterContainer centre = new CenterContainer();
        centre.setAnchorsPreset(Control.LayoutPreset.PRESET_FULL_RECT, false);
        page.addChild(centre);
        VBoxContainer v = new VBoxContainer();
        v.addThemeConstantOverride(new StringName("separation"), 28);
        centre.addChild(v);
        Label text = new Label();
        text.setName("Text");
        text.setText(NOTICE);
        text.setCustomMinimumSize(new Vector2(760f, 0f));
        text.setAutowrapMode(godot.api.TextServer.AutowrapMode.WORD_SMART);
        text.setHorizontalAlignment(godot.core.HorizontalAlignment.CENTER);
        text.addThemeFontSizeOverride(new StringName("font_size"), 22);
        v.addChild(text);
        Button ok = new Button();
        ok.setName("Understood");
        ok.setText("I understand");
        ok.setHSizeFlags(Control.SizeFlags.SHRINK_CENTER);
        v.addChild(ok);
        ok.connect("pressed", MethodCallable.createUnsafe(this, "on_notice_understood"));
        ok.grabFocus();
    }

    @Register
    public void onNoticeUnderstood() {
        noticeAcknowledged = true;
        click();
        if (getNodeOrNull("Notice") instanceof Control page) {
            removeChild(page);
            page.queueFree();
        }
        if (getNodeOrNull("Buttons") instanceof Control v) MenuManager.focusFirstButton(v);
    }

    private Button button(VBoxContainer v, String text, String handler) {
        Button b = new Button();
        b.setName(text.replace(" ", ""));
        b.setText(text);
        v.addChild(b);
        b.connect("pressed", MethodCallable.createUnsafe(this, handler));
        return b;
    }

    @Register public void onContinue() { click(); FrontEnd.start(this, FrontEnd.Action.CONTINUE, null); }
    @Register public void onNewGame() { click(); FrontEnd.start(this, FrontEnd.Action.NONE, null); }
    @Register public void onHost() { click(); FrontEnd.start(this, FrontEnd.Action.HOST, null); }
    @Register public void onJoin() { click(); FrontEnd.start(this, FrontEnd.Action.JOIN, address.getText()); }

    @Register
    public void onSettings() {
        click();
        if (getNodeOrNull("SettingsMenu") == null) SettingsMenu.open(this, getNodeOrNull("Buttons/Settings"));
    }

    @Register
    public void onQuit() {
        Node gm = getNodeOrNull("/root/GameManager");
        if (gm instanceof com.openworld.game.GameManager manager) manager.prepareForQuit();
        getTree().quit();
    }

    private void click() { com.openworld.audio.Sounds.ui(this, com.openworld.audio.Sound.UI_CLICK); }
}
