package com.ui;

import com.character.WeaponItem;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Control;
import godot.api.Label;
import godot.api.Node;
import godot.api.RichTextLabel;
import godot.api.TextureRect;
import godot.core.NodePath;

@RegisterClass(className = "RadialMenuItem")
public class RadialMenuItem extends Control {

  @Export
  @RegisterProperty
  public int index = 0;

  @RegisterProperty @Export public NodePath weaponIconPath    = new NodePath("WeaponIcon");
  @RegisterProperty @Export public NodePath weaponNamePath    = new NodePath("WeaponName");
  @RegisterProperty @Export public NodePath magazinePath           = new NodePath("Mag");
  @RegisterProperty @Export public NodePath ammoPath          = new NodePath("Ammo");

  private RadialMenu radialMenu;

  @RegisterFunction
  @Override
  public void _ready() {
    radialMenu = (RadialMenu) getOwner().getNode("RadialMenu");
  }

  /** Called by RadialMenu.showRadialMenu() to sync all weapon info for this slot. */
  public void refresh() {
    WeaponItem weapon = radialMenu.getWeaponItem(index);

    Node iconNode = getNodeOrNull(weaponIconPath);
    if (iconNode instanceof TextureRect tr) {
      tr.setTexture(weapon != null ? weapon.weaponIcon : null);
      tr.setVisible(weapon != null && weapon.weaponIcon != null);
    }

    setNodeText(getNodeOrNull(weaponNamePath), weapon != null ? weapon.getDisplayName() : "");
    setNodeText(getNodeOrNull(magazinePath),        weapon != null ? String.valueOf(weapon.getMagazine()) : "--");
    setNodeText(getNodeOrNull(ammoPath),       weapon != null ? String.valueOf(weapon.getReserve()) : "--");
  }

  private static void setNodeText(Node node, String text) {
    if (node instanceof Label l) l.setText(text);
    else if (node instanceof RichTextLabel rtl) rtl.setText(text);
  }

  @RegisterFunction
  public void onClicked() {
    int weapon = clampWeaponIndex(index);
    radialMenu.getPlayer().setWeapon(weapon);
    radialMenu.hideRadialMenu();
  }

  @RegisterFunction
  public void onHover() {
    int weapon = clampWeaponIndex(index);
    radialMenu.getPlayer().setWeapon(weapon);
  }

  private int clampWeaponIndex(int idx) {
    int maxIndex = radialMenu.getWeaponCount() - 1;
    if (idx < 0 || idx > maxIndex) return 0;
    return idx;
  }
}
