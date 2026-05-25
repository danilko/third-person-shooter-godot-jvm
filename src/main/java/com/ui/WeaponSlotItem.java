package com.ui;

import com.character.WeaponItem;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.HBoxContainer;
import godot.api.Label;
import godot.api.Node;
import godot.api.TextureRect;
import godot.core.Color;
import godot.core.NodePath;

/**
 * One weapon slot row inside WeaponSlotsUI.
 *
 * Scene layout (defined in WeaponSlotItem.tscn, fully editor-adjustable):
 *   HBoxContainer (this)
 *     KeyLabel   (Label)       — "[1]", "[Q]", etc.
 *     Icon       (TextureRect) — weapon icon; hidden when slot is empty
 *     AmmoLabel  (Label)       — "30/90" or "--"
 *
 * Call update() each time weapon state changes.
 */
@RegisterClass(className = "WeaponSlotItem")
public class WeaponSlotItem extends HBoxContainer {

    private static final Color COLOR_ACTIVE   = new Color(1.0f, 1.0f, 1.0f, 1.0f);
    private static final Color COLOR_INACTIVE = new Color(0.6f, 0.6f, 0.6f, 0.8f);
    private static final Color COLOR_EMPTY    = new Color(0.4f, 0.4f, 0.4f, 0.5f);

    @Export @RegisterProperty public NodePath keyLabelPath  = new NodePath("KeyLabel");
    @Export @RegisterProperty public NodePath iconPath      = new NodePath("Icon");
    @Export @RegisterProperty public NodePath ammoLabelPath = new NodePath("AmmoLabel");

    @RegisterFunction
    @Override
    public void _ready() {
        // Node paths are resolved lazily in update(); nothing to initialize here.
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
            tr.setTexture(item != null ? item.weaponIcon : null);
            tr.setVisible(item != null && item.weaponIcon != null);
        }

        Node an = getNodeOrNull(ammoLabelPath);
        if (an instanceof Label l) {
            l.setText(item != null ? item.getMagazine() + "/" + item.getReserve() : "--");
        }

        Color color = (item == null) ? COLOR_EMPTY
                    : isActive       ? COLOR_ACTIVE
                    :                  COLOR_INACTIVE;
        setModulate(color);
    }
}
