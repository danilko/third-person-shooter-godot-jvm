package com.openworld.ui;

import com.openworld.weapon.WeaponItem;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.HBoxContainer;
import godot.api.Label;
import godot.api.Node;
import godot.api.TextureRect;
import godot.core.Color;
import godot.core.NodePath;
import godot.core.StringName;

/**
 * One weapon slot row inside WeaponSlotsUI.
 *
 * Scene layout (defined in WeaponSlotItem.tscn, fully editor-adjustable):
 *   HBoxContainer (this)
 *     KeyLabel   (Label)       — "[1]", "[Q]", etc.
 *     Icon       (TextureRect) — weapon icon; hidden when slot is empty
 *       NameLabel (Label)      — the weapon's name, small, pinned to the icon's bottom-right (CS-style)
 *     AmmoLabel  (Label)       — "30/90" or "--"
 *
 * Call update() each time weapon state changes.
 */
@Script(className = "WeaponSlotItem")
public class WeaponSlotItem extends HBoxContainer {

    private boolean active;

    @Export public NodePath keyLabelPath  = new NodePath("KeyLabel");
    @Export public NodePath iconPath      = new NodePath("Icon");
    @Export public NodePath nameLabelPath = new NodePath("Icon/NameLabel");
    @Export public NodePath ammoLabelPath = new NodePath("AmmoLabel");

    @Register
    @Override
    public void _ready() {
        // Node paths are resolved lazily in update(); nothing to initialize here.
    }

    /** The ▶ selection marker before the active row. */
    @Register
    @Override
    public void _draw() {
        if (!active) return;
        float cy = 12f, t = 6f;          // on the icon's line (the top 24 px of the row; the name sits under it)
        godot.core.PackedVector2Array tri = new godot.core.PackedVector2Array();
        // in the panel's 22 px left gutter (WeaponSlotsUI)
        tri.append(new godot.core.Vector2(-15f, cy - t));
        tri.append(new godot.core.Vector2(-15f + t * 1.6f, cy));
        tri.append(new godot.core.Vector2(-15f, cy + t));
        drawColoredPolygon(tri, HudPalette.TEXT);
    }

    /**
     * Refreshes this slot's display. Safe to call before _ready() because node
     * lookup is done inside the method rather than cached at construction time.
     *
     * @param item     current WeaponItem in this slot, or null if empty
     * @param isActive true when this is the currently equipped slot
     * @param keyText  key label to display (e.g. "1", "Q") — without brackets
     */
    public void update(WeaponItem item, boolean isActive, String keyText) {
        Node kn = getNodeOrNull(keyLabelPath);
        if (kn instanceof Label l) l.setText("[" + keyText + "]");

        Node in = getNodeOrNull(iconPath);
        if (in instanceof TextureRect tr) {
            // cropped to the silhouette and drawn in a fixed-height box: every weapon at one height (IconFit).
            // The box stays even with no icon (the fist), so every row is the same height.
            tr.setTexture(item != null ? IconFit.cropped(item.weaponIcon) : null);
        }

        Node nn = getNodeOrNull(nameLabelPath);
        if (nn instanceof Label l) l.setText(item != null ? item.getDisplayName() : "");

        Node an = getNodeOrNull(ammoLabelPath);
        if (an instanceof Label l) {
            if (item == null) {
                l.setText("--");
            } else {
                String ammo = WeaponHUD.showsAmmo(item) ? item.getMagazine() + "/" + item.getReserve() : "";
                l.setText(ammo);                // the name is already under the icon (NameLabel)
            }
        }

        setVisible(item != null);          // only owned slots are listed
        // selection by SHAPE and brightness (HudPalette): a white ▶ before the active row, which is full white;
        // the other rows are 70% white. Every row keeps white text with the theme's thin outline.
        active = isActive && item != null;
        for (NodePath path : new NodePath[] {keyLabelPath, nameLabelPath, ammoLabelPath}) {
            if (getNodeOrNull(path) instanceof Label l) l.removeThemeColorOverride(new StringName("font_color"));
        }
        if (getNodeOrNull(iconPath) instanceof TextureRect tr) tr.setSelfModulate(HudPalette.TEXT);
        setModulate(active ? HudPalette.TEXT : HudPalette.TEXT_DIM);
        queueRedraw();
    }
}
