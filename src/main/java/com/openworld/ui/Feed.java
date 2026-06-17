package com.openworld.ui;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Control;
import godot.api.Node;
import godot.api.VBoxContainer;

/**
 * Generic scrolling feed container.
 *
 * Manages a vertical stack of {@link FeedEntry} rows — any subclass works.
 * Entries add themselves at the bottom; each entry removes itself when its
 * own timer expires.  When {@link #maxEntries} is reached the oldest entry
 * is evicted immediately to make room.
 *
 * This class is intentionally free of game-event knowledge.  The caller is
 * responsible for creating the right {@link FeedEntry} subclass, populating
 * it with event-specific data, and calling {@link #push}.
 *
 * Example:
 * <pre>
 *   DefeatedFeedEntry entry = (DefeatedFeedEntry) entryScene.instantiate();
 *   entry.lifespan = feed.entryLifespan;
 *   feed.push(entry);
 *   entry.populate(attackerName, attackerFaction, victimName, victimFaction, icon, headshot);
 * </pre>
 */
@RegisterClass(className = "Feed")
public class Feed extends Control {

    /** Maximum number of rows visible at once. Oldest is evicted when exceeded. */
    @RegisterProperty
    @Export
    public int maxEntries = 5;

    /** Lifespan in seconds assigned to each entry by the caller as a convenience default. */
    @RegisterProperty
    @Export
    public float entryLifespan = 4.0f;

    private VBoxContainer vBoxContainer;

    @RegisterFunction
    @Override
    public void _ready() {
        vBoxContainer = (VBoxContainer) getNode("VBoxContainer");
    }

    /**
     * Add an entry to the bottom of the feed.
     *
     * Evicts the oldest entry (index 0) with an immediate {@code removeChild}
     * if the feed is already at capacity — the entry is freed the same frame,
     * not deferred, so {@code getChildCount()} stays accurate.
     */
    public void push(FeedEntry entry) {
        if (getChildCount() >= maxEntries) {
            Node oldest = getChild(0);
            vBoxContainer.removeChild(oldest);
            oldest.queueFree();
        }
        vBoxContainer.addChild(entry);
    }
}
