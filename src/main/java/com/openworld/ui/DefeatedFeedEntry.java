package com.openworld.ui;

import com.openworld.character.Faction;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Label;
import godot.api.Texture2D;
import godot.api.TextureRect;

/**
 * Kill-feed row for a character elimination event.
 *
 * Layout (left → right):
 *   [AttackerName]  [WeaponColumn: WeaponIcon / HeadshotIndicator]  [VictimName]
 *
 * WeaponColumn is a VBoxContainer: WeaponIcon on top, HeadshotIndicator image
 * centered beneath it — only visible when the kill was a headshot.
 * Assign a headshot icon texture via {@link #headshotIcon} in the inspector.
 *
 * Attacker and victim names are tinted by faction color.
 *
 * Extend {@link FeedEntry} for other event types (pickups, objectives, etc.)
 * and push any FeedEntry subclass to a {@link Feed} container.
 */
@Script(className = "DefeatedFeedEntry")
public class DefeatedFeedEntry extends FeedEntry {

    /** Texture displayed in the HeadshotIndicator slot when a kill was a headshot. */
    @Export
    public Texture2D headshotIcon;

    private Label       attackerLabel;
    private TextureRect weaponIconRect;
    private TextureRect headshotIndicator;
    private Label       victimLabel;

    @Register
    @Override
    public void _process(double delta) {
        super._process(delta);
    }

    @Register
    @Override
    public void _ready() {
        super._ready();
        attackerLabel     = (Label)       getNode("AttackerName");
        weaponIconRect    = (TextureRect) getNode("WeaponIcon");
        headshotIndicator = (TextureRect) getNode("HeadshotIndicator");
        victimLabel       = (Label)       getNode("VictimName");
        if (headshotIndicator != null) headshotIndicator.setVisible(false);
    }

    /**
     * Fill the row with elimination data. Call after the entry has been added
     * to the scene tree (i.e. after {@code Feed.push(this)}).
     */
    public void populate(String attackerName, String attackerFaction,
                         String victimName,   String victimFaction,
                         Texture2D weaponIcon, boolean headshot) {
        if (attackerLabel != null) {
            attackerLabel.setText(attackerName);
            attackerLabel.setModulate(Faction.color(attackerFaction));
        }
        if (weaponIconRect != null) {
            weaponIconRect.setTexture(weaponIcon);
            weaponIconRect.setVisible(weaponIcon != null);
        }
        if (headshotIndicator != null) {
            headshotIndicator.setTexture(headshotIcon);
            headshotIndicator.setVisible(headshot && headshotIcon != null);
        }
        if (victimLabel != null) {
            victimLabel.setText(victimName);
            victimLabel.setModulate(Faction.color(victimFaction));
        }
    }

}
