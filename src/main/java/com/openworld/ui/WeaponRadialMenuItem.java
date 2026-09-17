package com.openworld.ui;

import com.openworld.weapon.WeaponItem;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.*;
import godot.core.Color;
import godot.core.NodePath;

/**
 * One UPRIGHT card in the weapon wheel (WeaponRadialCard.tscn): the weapon's icon with its name pinned to the
 * icon's bottom-right (CS-style), the slot key on the left and the ammo on the right underneath.
 *
 * <p>A card is pure display. Which slot is selected is decided by {@link WeaponRadialMenu} from the pointer's
 * ANGLE around the menu centre, not by hovering the card, so the cards' shape and the gaps between them leave no
 * dead zones — the reason the wheel moved from textured wedges with click masks to cards (2026-09-16). Text size
 * and outline come from the themes (weapon_menu_theme.tres, 10 pt; game_theme.tres, the outline), not per node.
 */
@Script(className = "WeaponRadialMenuItem")
public class WeaponRadialMenuItem extends Control {

  /** Slot index this card shows; set by WeaponRadialMenu when it builds the wheel. */
  @Export public int index = 0;

  @Export public NodePath weaponIconPath = new NodePath("Icon");
  @Export public NodePath weaponNamePath = new NodePath("Icon/Name");
  @Export public NodePath ammoPath       = new NodePath("Ammo");
  @Export public NodePath keyLabelPath   = new NodePath("Key");
  @Export public NodePath highlightPath  = new NodePath("Highlight");

  private static final Color FILLED = new Color(1f, 1f, 1f, 1f);
  private static final Color EMPTY  = new Color(1f, 1f, 1f, 0.45f);

  private String keyText = "";

  @Register
  @Override
  public void _ready() {
    keyText = slotKeyText(index);
  }

  /**
   * The key bound to slot {@code slot}, the same rule WeaponSlotsUI uses: slot 0 (the fist) is
   * {@code weapon_unequip}, slot N is {@code weapon_slot_N}. (The wedge wheel used weapon_slot_(N+1), so every
   * slot was labelled one key too high.)
   */
  static String slotKeyText(int slot) {
    return slot == 0 ? resolveKeyText("weapon_unequip", "0") : resolveKeyText("weapon_slot_" + slot, String.valueOf(slot));
  }

  /** Sync this card with its slot (called by WeaponRadialMenu when the wheel opens). */
  public void refresh(WeaponItem weapon) {
    if (keyText.isEmpty()) keyText = slotKeyText(index);
    Node iconNode = getNodeOrNull(weaponIconPath);
    if (iconNode instanceof TextureRect tr) {
      tr.setTexture(weapon != null ? weapon.weaponIcon : null);
    }
    setText(weaponNamePath, weapon != null ? weapon.getDisplayName() : "");
    setText(ammoPath, weapon == null ? "--"
        : weapon.isInfiniteAmmo ? "" : weapon.getMagazine() + "/" + weapon.getReserve());
    setText(keyLabelPath, "[" + keyText + "]");
    setModulate(weapon != null ? FILLED : EMPTY);
  }

  /** Show or hide the selection highlight. */
  public void setHighlighted(boolean on) {
    if (getNodeOrNull(highlightPath) instanceof CanvasItem h) h.setVisible(on);
  }

  /** True while highlighted — the on-screen check reads it. */
  @Register
  public boolean highlightedNow() {
    return getNodeOrNull(highlightPath) instanceof CanvasItem h && h.isVisible();
  }

  private void setText(NodePath path, String text) {
    Node n = getNodeOrNull(path);
    if (n instanceof Label l) l.setText(text);
    else if (n instanceof RichTextLabel rtl) rtl.setText(text);
  }

  private static String resolveKeyText(String action, String fallback) {
    try {
      for (InputEvent ev : InputMap.INSTANCE.actionGetEvents(action)) {
        if (ev instanceof InputEventKey iek) {
          String text = iek.asTextPhysicalKeycode();
          return text.isEmpty() ? fallback : text;
        }
      }
    } catch (Exception ignored) {
      // Action not registered yet — happens in editor headless runs.
    }
    return fallback;
  }
}
