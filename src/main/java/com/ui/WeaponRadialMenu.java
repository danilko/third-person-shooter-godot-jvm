package com.ui;

import com.character.Character;
import com.character.MovementType;
import com.character.WeaponController;
import com.character.WeaponItem;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.*;
import godot.core.NodePath;
import godot.core.Vector3;
import java.util.ArrayList;
import java.util.List;

/**
 * Radial weapon-selection overlay.
 *
 * Items are generated dynamically: one template node ("0" in the circle container)
 * is cloned once per weapon slot and spaced evenly at 2π/slotCount radians each.
 *
 * References (character, weaponController, camera) are injected by HUDManager
 * via wireCharacter(). The menu is context-agnostic — robot, powered armour, or
 * player on foot all work without scene changes.
 */
@RegisterClass(className = "WeaponRadialMenu")
public class WeaponRadialMenu extends Control {

  @Export @RegisterProperty public Character character;

  /** Path to the container that holds the radial items (the rotating circle). */
  @RegisterProperty @Export
  public NodePath circleContainerPath = new NodePath("Panel/Circle");

  /** Scene used to instantiate each weapon slot item. Set to WeaponRadialMenuItem.tscn. */
  @RegisterProperty @Export
  public PackedScene weaponItemTemplate;

  private WeaponController cachedWeaponController;
  private Node             cachedCamera;
  private AnimationPlayer  animationPlayer;

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  /** Set or update the active character; rebuilds items for the new slot layout. */
  public void wireCharacter(Character c) {
    character = c;
    cachedWeaponController = null;
    cachedCamera = null;
    buildItems();
  }

  @RegisterFunction
  @Override
  public void _ready() {
    animationPlayer = (AnimationPlayer) getNode("AnimationPlayer");
    buildItems();
    hide();
  }

  // ── Input / show / hide ───────────────────────────────────────────────────

  @RegisterFunction
  @Override
  public void _input(InputEvent event) {
    if (getWeaponController() == null) return;
    if (event.isActionPressed("radialmenu") && !getWeaponController().isWeaponReloading()) {
      showRadialMenu();
    } else if (event.isActionReleased("radialmenu")) {
      hideRadialMenu();
    }
  }

  public void showRadialMenu() {
    if (character == null) return;
    Input.setMouseMode(Input.MouseMode.VISIBLE);
    character.setProcessInput(false);
    character.setMovementDirection(Vector3.Companion.getZERO());
    character.setMovementState(MovementType.IDLE);
    Node cam = getCamera();
    if (cam != null) cam.setProcessInput(false);
    refreshItems();
    show();
    animationPlayer.play("Zoom");
  }

  public void hideRadialMenu() {
    if (character == null) return;
    Input.setMouseMode(Input.MouseMode.CAPTURED);
    character.setMovementState(MovementType.IDLE);
    character.setProcessInput(true);
    Node cam = getCamera();
    if (cam != null) cam.setProcessInput(true);
    hide();
  }

  // ── Dynamic item building ─────────────────────────────────────────────────

  /**
   * Clones the first WeaponRadialMenuItem in the circle container to produce
   * exactly slotCount items spaced at 2π/slotCount radians each.
   * Called on _ready() and whenever wireCharacter() provides a new controller.
   */
  public void buildItems() {
    WeaponController wc = getWeaponController();
    if (wc == null || weaponItemTemplate == null) return;

    Node circle = getNodeOrNull(circleContainerPath);
    if (circle == null) return;

    // Remove existing items synchronously so the child list is clean before adding new ones
    List<Node> toRemove = new ArrayList<>();
    for (int i = 0; i < circle.getChildCount(); i++) {
      if (circle.getChild(i) instanceof WeaponRadialMenuItem) toRemove.add(circle.getChild(i));
    }
    for (Node old : toRemove) {
      circle.removeChild(old);
      old.queueFree();
    }

    int slotCount = wc.getSlotCount();
    double step = (Math.PI * 2.0) / slotCount;

    for (int i = 0; i < slotCount; i++) {
      Node instance = weaponItemTemplate.instantiate();
      if (instance instanceof WeaponRadialMenuItem item) {
        item.setRotation((float) (i * step));
        circle.addChild(item);
      }
    }
  }

  // ── Accessors ─────────────────────────────────────────────────────────────

  public Character getCharacter() { return character; }

  public int getWeaponCount() {
    WeaponController wc = getWeaponController();
    return wc != null ? wc.getWeaponCount() : 0;
  }

  public WeaponItem getWeaponItem(int idx) {
    WeaponController wc = getWeaponController();
    return wc != null ? wc.getWeaponItem(idx) : null;
  }

  // ── Private helpers ───────────────────────────────────────────────────────

  private void refreshItems() {
    refreshItemsIn(this);
  }

  private void refreshItemsIn(Node node) {
    for (int i = 0; i < node.getChildCount(); i++) {
      Node child = node.getChild(i);
      if (child instanceof WeaponRadialMenuItem item) item.refresh();
      else refreshItemsIn(child);
    }
  }

  private WeaponController getWeaponController() {
    if (cachedWeaponController == null && character != null) {
      Node wc = character.getNodeOrNull("WeaponController");
      if (wc instanceof WeaponController w) cachedWeaponController = w;
    }
    return cachedWeaponController;
  }

  private Node getCamera() {
    if (cachedCamera == null && character != null) {
      cachedCamera = character.getNodeOrNull("CameraRoot");
    }
    return cachedCamera;
  }
}
