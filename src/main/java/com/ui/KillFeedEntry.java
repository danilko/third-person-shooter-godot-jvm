package com.ui;

import com.character.Faction;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.HBoxContainer;
import godot.api.Label;
import godot.api.Texture2D;
import godot.api.TextureRect;
import godot.core.Color;

/**
 * One row in the kill feed.
 *
 * Layout (left → right):
 *   [AttackerName] [WeaponIcon] [HeadshotIndicator] [VictimName]
 *
 * Attacker and victim labels are tinted by faction color.
 * The entry removes itself from the tree once its lifespan expires,
 * fading out over the final FADE_DURATION seconds.
 */
@RegisterClass(className = "KillFeedEntry")
public class KillFeedEntry extends HBoxContainer {

    @RegisterProperty
    @Export
    public float lifespan = 4.0f;

    private static final float FADE_DURATION = 0.6f;

    private double timer = 0.0;

    private Label       attackerLabel;
    private TextureRect weaponIconRect;
    private Label       headshotLabel;
    private Label       victimLabel;

    @RegisterFunction
    @Override
    public void _ready() {
        attackerLabel  = (Label)       getNode("AttackerName");
        weaponIconRect = (TextureRect) getNode("WeaponIcon");
        headshotLabel  = (Label)       getNode("HeadshotIndicator");
        victimLabel    = (Label)       getNode("VictimName");
        timer = lifespan;
    }

    @RegisterFunction
    @Override
    public void _process(double delta) {
        timer -= delta;
        if (timer <= 0.0) {
            queueFree();
            return;
        }
        if (timer < FADE_DURATION) {
            float alpha = (float)(timer / FADE_DURATION);
            setModulate(new Color(1f, 1f, 1f, alpha));
        }
    }

    /**
     * Populate all visual fields. Call after addChild() so node refs from _ready() are valid.
     */
    public void populate(String attackerName, String attackerFaction,
                         String victimName,   String victimFaction,
                         Texture2D weaponIcon, boolean headshot) {
        if (attackerLabel != null) {
            attackerLabel.setText(attackerName);
            attackerLabel.setModulate(factionColor(attackerFaction));
        }
        if (weaponIconRect != null) {
            weaponIconRect.setTexture(weaponIcon);
            weaponIconRect.setVisible(weaponIcon != null);
        }
        if (headshotLabel != null) {
            headshotLabel.setVisible(headshot);
        }
        if (victimLabel != null) {
            victimLabel.setText(victimName);
            victimLabel.setModulate(factionColor(victimFaction));
        }
    }

    private static Color factionColor(String faction) {
        if (Faction.PLAYER.equals(faction)) return new Color(0.45f, 0.78f, 1.00f, 1f); // cyan-blue
        if (Faction.ENEMY.equals(faction))  return new Color(1.00f, 0.35f, 0.35f, 1f); // red
        return new Color(0.85f, 0.85f, 0.85f, 1f);                                      // neutral grey
    }
}
