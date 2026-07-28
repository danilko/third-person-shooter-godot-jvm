package com.openworld.debug;

import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.api.Node3D;
import godot.api.Window;
import godot.core.Callable;
import godot.core.MethodCallable;
import godot.core.StringNames;
import godot.global.GD;

/**
 * One-shot empirical check (NOT a permanent regression test): does {@code SceneTree.quit()}
 * (the path every in-game Quit button uses) actually emit {@code Window.close_requested}
 * (the signal {@code GameManager.onCloseRequested}'s audio-stop-on-quit sweep is wired to)?
 * Prints "QUITCHECK: close_requested fired" if the signal handler runs before the process exits,
 * or nothing (process just exits) if it doesn't — either way this line is the last thing printed.
 *
 * Run with: godot --headless res://src/main/resources/com/openworld/debug/QuitSignalCheck.tscn
 */
@RegisterClass(className = "QuitSignalCheckHost")
public class QuitSignalCheckHost extends Node3D {

    @RegisterFunction
    @Override
    public void _ready() {
        Window root = getTree().getRoot();
        root.getCloseRequested().connectUnsafe(
                MethodCallable.createUnsafe(this, "onCloseRequested"),
                godot.api.Object.ConnectFlags.DEFAULT);
        GD.print("QUITCHECK: about to call getTree().quit() directly (the PauseMenu/MenuManager/"
                + "GameOverMenu path)");
        getTree().quit();
        GD.print("QUITCHECK: quit() call returned (this line printing proves quit() itself "
                + "doesn't block synchronously)");
    }

    @RegisterFunction
    public void onCloseRequested() {
        GD.print("QUITCHECK: close_requested fired");
    }
}
