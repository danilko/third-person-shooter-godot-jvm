package com.ui;

import com.game.EventBus;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Node;
import godot.api.PackedScene;
import godot.api.Texture2D;
import godot.api.VBoxContainer;
import godot.core.Callable;
import godot.core.StringNames;
import godot.global.GD;

/**
 * CS-style kill feed: a vertical stack of self-timed {@link KillFeedEntry} rows.
 *
 * Connects to {@code EventBus.characterEliminated} in {@code _ready()}.
 * Each kill appends a new entry at the bottom; entries older than
 * {@code entryLifespan} seconds remove themselves.  When the stack reaches
 * {@code maxEntries} the oldest entry is evicted immediately.
 *
 * Set {@code entryScene} in the inspector to point at KillFeedEntry.tscn,
 * or leave it null to fall back to the hard-coded resource path.
 */
@RegisterClass(className = "KillFeed")
public class KillFeed extends VBoxContainer {

    @RegisterProperty
    @Export
    public PackedScene entryScene;

    @RegisterProperty
    @Export
    public int maxEntries = 5;

    @RegisterProperty
    @Export
    public float entryLifespan = 4.0f;

    private static final String ENTRY_SCENE_PATH =
            "res://src/main/resources/com/ui/KillFeedEntry.tscn";

    @RegisterFunction
    @Override
    public void _ready() {
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) {
            bus.characterEliminated.connectUnsafe(
                    Callable.createUnsafe(this, StringNames.toGodotName("onCharacterEliminated")),
                    godot.api.Object.ConnectFlags.DEFAULT);
        }
    }

    @RegisterFunction
    public void onCharacterEliminated(String attackerName, String attackerFaction,
                                      String victimName,   String victimFaction,
                                      String weaponName,   Texture2D weaponIcon,
                                      boolean headshot) {
        PackedScene scene = resolveEntryScene();
        if (scene == null) return;

        // Evict oldest when at capacity (removeChild + queueFree for immediate removal)
        if (getChildCount() >= maxEntries) {
            Node oldest = getChild(0);
            removeChild(oldest);
            oldest.queueFree();
        }

        KillFeedEntry entry = (KillFeedEntry) scene.instantiate();
        entry.lifespan = entryLifespan;
        addChild(entry);
        entry.populate(attackerName, attackerFaction, victimName, victimFaction, weaponIcon, headshot);
    }

    private PackedScene resolveEntryScene() {
        if (entryScene != null) return entryScene;
        Object loaded = GD.load(ENTRY_SCENE_PATH);
        return (loaded instanceof PackedScene ps) ? ps : null;
    }
}
