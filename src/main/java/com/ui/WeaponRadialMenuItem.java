package com.ui;

import com.character.WeaponItem;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.*;
import godot.core.NodePath;
import godot.global.GD;

@RegisterClass(className = "WeaponRadialMenuItem")
public class WeaponRadialMenuItem extends Control {

  @Export @RegisterProperty public int      index        = 0;

  /**
   * Control node positioned at the button's visual centre inside the item.
   * Its rotation is set to -item.rotation in _ready() so all children face
   * up in screen space while staying at the button's world position.
   */
  @RegisterProperty @Export public NodePath axisPath      = new NodePath("Axis");
  @RegisterProperty @Export public NodePath weaponIconPath = new NodePath("Axis/WeaponIcon");
  @RegisterProperty @Export public NodePath weaponNamePath = new NodePath("Axis/WeaponName");
  @RegisterProperty @Export public NodePath magazinePath   = new NodePath("Axis/Magazine");
  @RegisterProperty @Export public NodePath reservePath    = new NodePath("Axis/Reserve");
  @RegisterProperty @Export public NodePath keyLabelPath    = new NodePath("Axis/KeyLabel");

    private String[] keyTexts = new String[0];

  private WeaponRadialMenu radialMenu;

  @RegisterFunction
  @Override
  public void _ready() {
      resolveKeyTexts();

    radialMenu = findRadialMenu();
    index = deriveSiblingIndex();
    counterRotateContent();

  }

  /**
   * Counter-rotates the Axis Control by -item.rotation so its children
   * always face up in screen space. Axis must be positioned at the button's
   * visual centre in the scene so the rotation happens around that point.
   */
  private void counterRotateContent() {
    Node axisNode = getNodeOrNull(axisPath);
    if (axisNode instanceof Control axis) {
      axis.setRotation(-getRotation());
    }
  }

  /** Counts how many WeaponRadialMenuItem siblings appear before this node. */
  private int deriveSiblingIndex() {
    Node parent = getParent();
    if (parent == null) return index;
    int count = 0;
    for (int i = 0; i < parent.getChildCount(); i++) {
      Node child = parent.getChild(i);
      if (child == this) return count;
      if (child instanceof WeaponRadialMenuItem) count++;
    }
    return index;
  }

  /** Called by WeaponRadialMenu when the menu opens to sync all weapon info for this slot. */
  public void refresh() {
    WeaponRadialMenu rm = getRadialMenu();
    if (rm == null) return;

    WeaponItem weapon = rm.getWeaponItem(index);

    Node iconNode = getNodeOrNull(weaponIconPath);
    if (iconNode instanceof TextureRect tr) {
      tr.setTexture(weapon != null ? weapon.weaponIcon : null);
      tr.setVisible(weapon != null && weapon.weaponIcon != null);
    }

    setNodeText(getNodeOrNull(weaponNamePath), weapon != null ? weapon.getDisplayName() : "");
    setNodeText(getNodeOrNull(magazinePath),   weapon != null ? String.valueOf(weapon.getMagazine()) : "--");
    setNodeText(getNodeOrNull(reservePath),    weapon != null ? String.valueOf(weapon.getReserve()) : "--");
    String keyText = (index < keyTexts.length) ? keyTexts[index] : String.valueOf(index + 1);
    setNodeText(getNodeOrNull(keyLabelPath), String.format("[%s]", weapon != null ? keyText : "?"));
  }

    private void resolveKeyTexts() {
        WeaponRadialMenu rm = findRadialMenu();
        int count = (rm != null && rm.getCharacter() != null && rm.getCharacter().weaponController != null)
                ? rm.getCharacter().weaponController.getSlotCount() : 8;
        keyTexts = new String[count];
        for (int i = 0; i < count; i++) {
            keyTexts[i] = resolveKeyText("weapon_slot_" + (i + 1), String.valueOf(i + 1));
        }
    }

    private String resolveKeyText(String action, String fallback) {
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

  @RegisterFunction
  public void onClicked() {
    WeaponRadialMenu rm = getRadialMenu();
    GD.print("Click menu item " + this.getName());
    if (rm == null || rm.getCharacter() == null) return;

      GD.print("Click menu item " + this.getName() + " set weapon " + index);

    rm.getCharacter().setWeapon(index);
    rm.hideRadialMenu();
  }

  @RegisterFunction
  public void onHover() {

      WeaponRadialMenu rm = getRadialMenu();
    // visual highlight is handled by Button's texture_hover — switching on hover
      GD.print("hover menu item " + this.getName());
      if (rm == null || rm.getCharacter() == null) return;

      GD.print("hover menu item " + this.getName() + " set weapon " + index);

      rm.getCharacter().setWeapon(index);
      rm.hideRadialMenu();
  }

  // ── Private helpers ───────────────────────────────────────────────────────

  private WeaponRadialMenu getRadialMenu() {
    if (radialMenu == null) radialMenu = findRadialMenu();
    return radialMenu;
  }

  private WeaponRadialMenu findRadialMenu() {
    Node node = getParent();
    while (node != null) {
      if (node instanceof WeaponRadialMenu rm) return rm;
      node = node.getParent();
    }
    return null;
  }

  private static void setNodeText(Node node, String text) {
    if (node instanceof Label l) l.setText(text);
    else if (node instanceof RichTextLabel rtl) rtl.setText(text);
  }
}
