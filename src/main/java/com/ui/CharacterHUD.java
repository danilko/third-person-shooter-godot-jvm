package com.ui;

import com.game.EventBus;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.*;
import godot.core.Callable;
import godot.core.NodePath;
import godot.core.StringNames;
/**
 * Per-character HUD: health bar, ammo counters, pickup notification, interact prompt.
 *
 * Global feed entries (kill feed) are owned by HUDManager so they remain
 * visible across HUD context switches (foot ↔ vehicle).
 */
@RegisterClass(className = "CharacterHUD")
public class CharacterHUD extends Control {

  @RegisterProperty
  @Export
  public NodePath healthLabelPath = new NodePath("Health/ColorRect/Health");

  @RegisterProperty @Export
  public NodePath notificationIconPath = new NodePath("Notification/WeaponIcon");

  private Label healthLabel;
  private Label magazineLabel;
  private Label reserveLabel;
  private Label pickupNotificationLabel;
  private TextureRect notificationIcon;
  private Label interactPromptLabel;
  private String playerCharacterId = "";
  private double pickupTimer = 0.0;
  private static final double PICKUP_NOTIFICATION_DURATION = 3.0;

  @RegisterFunction
  @Override
  public void _ready() {
    if (hasNode(healthLabelPath)) {
      healthLabel = (Label) getNode(healthLabelPath);
    }

    pickupNotificationLabel = (Label) getNode("Notification/EliminatedNotification");
    Node iconNode = getNodeOrNull(notificationIconPath);
    if (iconNode instanceof TextureRect tr) notificationIcon = tr;
    Node promptNode = getNodeOrNull("InteractPrompt");
    if (promptNode instanceof Label l) interactPromptLabel = l;

    Node busNode = getNodeOrNull("/root/EventBus");
    if (busNode instanceof EventBus bus) {
      bus.playerHealthChanged.connectUnsafe(
          Callable.createUnsafe(this, StringNames.toGodotName("onHealthChanged")),
          godot.api.Object.ConnectFlags.DEFAULT);
      bus.pickupInteractChanged.connectUnsafe(
          Callable.createUnsafe(this, StringNames.toGodotName("onPickupInteractChanged")),
          godot.api.Object.ConnectFlags.DEFAULT);
    }
  }

  @RegisterFunction
  @Override
  public void _process(double delta) {
    if (pickupTimer > 0) {
      pickupTimer -= delta;
      if (pickupTimer <= 0) {
        if (pickupNotificationLabel != null) pickupNotificationLabel.setVisible(false);
        if (notificationIcon != null) notificationIcon.setVisible(false);
      }
    }
  }

  /** Receive WeaponController.ammoChanged signal. */
  @RegisterFunction
  public void onAmmoChanged(int magazine, int reserve) {
    if (magazineLabel != null) {
      magazineLabel.setText(String.valueOf(magazine));
    }
    if (reserveLabel != null) {
      reserveLabel.setText(String.valueOf(reserve));
    }
  }

  /** Receive Health.damaged signal (pass currentHealth from the character). */
  @RegisterFunction
  public void onHealthChanged(float currentHealth) {
    if (healthLabel != null) {
      healthLabel.setText(String.valueOf((int) currentHealth));
    }
  }

  /** Receive EventBus.pickupInteractChanged — show/hide the "Press F to pick up" prompt. */
  @RegisterFunction
  public void onPickupInteractChanged(boolean inRange, String label) {
    if (interactPromptLabel == null) return;
    if (inRange) {
      interactPromptLabel.setText("[ E ]  " + label);
      interactPromptLabel.setVisible(true);
    } else {
      interactPromptLabel.setVisible(false);
    }
  }

  /** Called by HUDManager.wirePlayer() to bind this HUD to a specific character. */
  public void setPlayerCharacterId(String id) {
    playerCharacterId = id != null ? id : "";
  }

  /** Receive EventBus.weaponPickedUp — brief HUD notification of the item name and icon. */
  @RegisterFunction
  public void onWeaponPickedUp(String characterId, String weaponName, Texture2D weaponIcon) {
    if (!playerCharacterId.isEmpty() && !playerCharacterId.equals(characterId)) return;
    showNotification("Picked up " + weaponName, weaponIcon);
  }

  /** Show a transient pickup notification (weapon icon + item name). */
  private void showNotification(String text, Texture2D icon) {
    if (pickupNotificationLabel != null) {
      pickupNotificationLabel.setText(text);
      pickupNotificationLabel.setVisible(true);
    }
    if (notificationIcon != null) {
      notificationIcon.setTexture(icon);
      notificationIcon.setVisible(icon != null);
    }
    pickupTimer = PICKUP_NOTIFICATION_DURATION;
  }
}
