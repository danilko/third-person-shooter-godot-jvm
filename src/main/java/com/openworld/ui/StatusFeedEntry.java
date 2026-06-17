package com.openworld.ui;

import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.api.Label;
import godot.api.TextureRect;
import godot.api.Texture2D;
import godot.core.Vector2;

/**
 * Generic status-feed row: an optional icon plus a message line.
 *
 * Self-expires via {@link FeedEntry}'s countdown + fade. Built programmatically
 * (no dedicated .tscn) so callers just {@code new}, {@link #setContent}, and
 * {@code feed.push(...)} — the same single self-expiring mechanism the kill feed
 * uses, replacing the old hand-rolled pickup timer and mission-banner Timer.
 *
 * Push to the "status" {@link Feed} instance (top-of-screen) for transient toasts
 * like weapon pickups and mission start/complete/fail.
 */
@RegisterClass(className = "StatusFeedEntry")
public class StatusFeedEntry extends FeedEntry {

    private String    pendingMessage = "";
    private Texture2D pendingIcon    = null;

    /** Set before pushing to a Feed (children are built in {@code _ready} once in-tree). */
    public void setContent(String message, Texture2D icon) {
        this.pendingMessage = message != null ? message : "";
        this.pendingIcon    = icon;
    }

    @RegisterFunction
    @Override
    public void _ready() {
        super._ready();
        setCustomMinimumSize(new Vector2(0f, 24f));

        if (pendingIcon != null) {
            TextureRect icon = new TextureRect();
            icon.setTexture(pendingIcon);
            icon.setCustomMinimumSize(new Vector2(24f, 24f));
            icon.setExpandMode(TextureRect.ExpandMode.IGNORE_SIZE);
            icon.setStretchMode(TextureRect.StretchMode.KEEP_ASPECT_CENTERED);
            addChild(icon);
        }

        Label label = new Label();
        label.setText(pendingMessage);
        addChild(label);
    }
}
