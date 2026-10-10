package com.openworld.ui;

import com.openworld.game.FrontEnd;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Button;
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
 */
@Script(className = "TitleScreen")
public class TitleScreen extends Control {

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
        MenuManager.focusFirstButton(v);
    }

    private Button button(VBoxContainer v, String text, String handler) {
        Button b = new Button();
        b.setName(text.replace(" ", ""));
        b.setText(text);
        v.addChild(b);
        b.connect(new StringName("pressed"), MethodCallable.createUnsafe(this, handler));
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
