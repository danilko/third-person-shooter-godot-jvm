package com.openworld.ui;

import com.openworld.game.GameManager;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Control;
import godot.api.Node;

/**
 * Pause-menu visual node — display only.
 *
 * All state transitions (Esc toggle, mouse mode, SceneTree pause) are owned
 * by the parent {@link MenuManager}.  This node just shows/hides itself and
 * forwards button signals upward.
 */
@Script(className = "PauseMenu")
public class PauseMenu extends Control {

    @Register
    @Override
    public void _ready() {
        hide();
        // Settings (F2): a button the scene does not author, placed above Quit
        Node box = getNodeOrNull("CenterContainer/Panel/VBoxContainer");
        Node quit = box == null ? null : box.getNodeOrNull("Quit");
        if (box != null && box.getNodeOrNull("Settings") == null) {
            godot.api.Button b = new godot.api.Button();
            b.setName("Settings");
            b.setText("Settings");
            box.addChild(b);
            if (quit != null) box.moveChild(b, quit.getIndex());
            b.connect(new godot.core.StringName("pressed"), godot.core.MethodCallable.createUnsafe(this, "on_settings_pressed"));
            godot.api.Button t = new godot.api.Button();
            t.setName("QuitToTitle");
            t.setText("Quit to title");
            box.addChild(t);
            if (quit != null) box.moveChild(t, quit.getIndex());
            t.connect(new godot.core.StringName("pressed"), godot.core.MethodCallable.createUnsafe(this, "on_quit_to_title_pressed"));
        }
    }

    /** The balance under the title, refreshed while the menu is up (a menu may be as rich as needed). */
    @Register
    @Override
    public void _process(double delta) {
        if (!isVisibleInTree()) return;
        Node box = getNodeOrNull("CenterContainer/Panel/VBoxContainer");
        if (box == null) return;
        godot.api.Label cash = box.getNodeOrNull("Cash") instanceof godot.api.Label l ? l : null;
        if (cash == null) {
            cash = new godot.api.Label();
            cash.setName("Cash");
            cash.setHorizontalAlignment(godot.core.HorizontalAlignment.CENTER);
            box.addChild(cash);
            Node title = box.getNodeOrNull("Title");
            box.moveChild(cash, title != null ? title.getIndex() + 1 : 0);
        }
        String t = CashReadout.yen(com.openworld.game.profile.Profiles.local().balance);
        if (!t.equals(cash.getText())) cash.setText(t);
    }

    @Register
    public void onQuitToTitlePressed() {
        com.openworld.audio.Sounds.ui(this, com.openworld.audio.Sound.UI_CLICK);
        hide();
        com.openworld.game.FrontEnd.toTitle(this);
    }

    @Register
    public void onSettingsPressed() {
        com.openworld.audio.Sounds.ui(this, com.openworld.audio.Sound.UI_CLICK);
        Node parent = getParent();
        if (parent != null && parent.getNodeOrNull("SettingsMenu") == null)
            SettingsMenu.open(parent, getNodeOrNull("CenterContainer/Panel/VBoxContainer/Settings"));
    }

    @Register
    public void onResumePressed() {
        com.openworld.audio.Sounds.ui(this, com.openworld.audio.Sound.UI_CLICK);
        MenuManager mm = menuManager();
        if (mm != null) mm.resume();
    }

    @Register
    public void onRestartPressed() {
        com.openworld.audio.Sounds.ui(this, com.openworld.audio.Sound.UI_CLICK);
        MenuManager mm = menuManager();
        if (mm != null) mm.restart();
    }

    @Register
    public void onQuitPressed() {
        // GameManager.prepareForQuit() -- see its javadoc: SceneTree.quit() does NOT emit
        // Window.close_requested, so the audio-stop-on-quit sweep must be called explicitly here.
        Node gm = getNodeOrNull("/root/GameManager");
        if (gm instanceof GameManager manager) manager.prepareForQuit();
        getTree().quit();
    }

    private MenuManager menuManager() {
        return (getParent() instanceof MenuManager m) ? m : null;
    }
}
