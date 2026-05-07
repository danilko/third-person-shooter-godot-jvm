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
import godot.core.Vector3;

/**
 * Radial weapon-selection overlay.
 *
 * References (character, weaponController, camera) are injected by HUDManager
 * when a controllable entity is wired in. The menu is context-agnostic: it
 * shows whatever weapons are in the active WeaponController, so the same scene
 * works for the player on foot, a robot, or powered armour.
 *
 * For a carrier with a fundamentally different UI (ship, turret) swap the
 * entire HUD context via HUDManager.activateHUD() instead.
 */
@RegisterClass(className = "WeaponRadialMenu")
public class WeaponRadialMenu extends Control {

  @Export @RegisterProperty public Character character;

  private WeaponController cachedWeaponController;
  private Node             cachedCamera;
  private AnimationPlayer  animationPlayer;

  /** Set or update the active character; clears cached weapon controller and camera. */
  public void wireCharacter(Character c) {
    character = c;
    cachedWeaponController = null;
    cachedCamera = null;
  }

  @RegisterFunction
  @Override
  public void _ready() {
    animationPlayer = (AnimationPlayer) getNode("AnimationPlayer");
    hide();
  }

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
