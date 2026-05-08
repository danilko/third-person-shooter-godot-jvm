package com.ui;

import com.game.EventBus;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.*;
import godot.core.Callable;
import godot.core.Key;
import godot.core.NodePath;
import godot.core.StringNames;

/**
 * Owns all in-game HUD labels (health, ammo, kill notifications).
 *
 * Kill notifications arrive via EventBus.characterEliminated — no direct
 * signal wiring to WeaponController or Health is needed.
 */
@RegisterClass(className = "CharacterHUD")
public class CharacterHUD extends Control {

  @RegisterProperty
  @Export
  public NodePath healthLabelPath = new NodePath("Health/ColorRect/Health");

  @RegisterProperty
  @Export
  public NodePath magazineLabelPath = new NodePath("Magazine/ColorRect/Magazine");

  @RegisterProperty
  @Export
  public NodePath reserveLabelPath = new NodePath("Magazine/ColorRect/Reserve");

  @RegisterProperty @Export
  public NodePath notificationIconPath = new NodePath("Notification/WeaponIcon");

  private Label healthLabel;
  private Label magazineLabel;
  private Label reserveLabel;
  private Label eliminatedNotificationLabel;
  private TextureRect notificationIcon;
  private Label interactPromptLabel;
  private String playerCharacterId = "";
  private double killNotificationTimer = 0.0;
  private static final double KILL_NOTIFICATION_DURATION = 3.0;

  @RegisterFunction
  @Override
  public void _ready() {
    if (hasNode(healthLabelPath)) {
      healthLabel = (Label) getNode(healthLabelPath);
    }
    if (hasNode(magazineLabelPath)) {
      magazineLabel = (Label) getNode(magazineLabelPath);
    }
    if (hasNode(reserveLabelPath)) {
      reserveLabel = (Label) getNode(reserveLabelPath);
    }
    eliminatedNotificationLabel = (Label) getNode("Notification/EliminatedNotification");
    Node iconNode = getNodeOrNull(notificationIconPath);
    if (iconNode instanceof TextureRect tr) notificationIcon = tr;
    Node promptNode = getNodeOrNull("InteractPrompt");
    if (promptNode instanceof Label l) interactPromptLabel = l;

    Node busNode = getNodeOrNull("/root/EventBus");
    if (busNode instanceof EventBus bus) {
      bus.playerAmmoChanged.connectUnsafe(
          Callable.createUnsafe(this, StringNames.toGodotName("onAmmoChanged")),
          godot.api.Object.ConnectFlags.DEFAULT);
      bus.playerHealthChanged.connectUnsafe(
          Callable.createUnsafe(this, StringNames.toGodotName("onHealthChanged")),
          godot.api.Object.ConnectFlags.DEFAULT);
      bus.characterEliminated.connectUnsafe(
          Callable.createUnsafe(this, StringNames.toGodotName("onCharacterEliminated")),
          godot.api.Object.ConnectFlags.DEFAULT);
      bus.pickupInteractChanged.connectUnsafe(
          Callable.createUnsafe(this, StringNames.toGodotName("onPickupInteractChanged")),
          godot.api.Object.ConnectFlags.DEFAULT);
      bus.weaponPickedUp.connectUnsafe(
          Callable.createUnsafe(this, StringNames.toGodotName("onWeaponPickedUp")),
          godot.api.Object.ConnectFlags.DEFAULT);
    }
  }

  @RegisterFunction
  @Override
  public void _process(double delta) {
    if (killNotificationTimer > 0) {
      killNotificationTimer -= delta;
      if (killNotificationTimer <= 0) {
        if (eliminatedNotificationLabel != null) eliminatedNotificationLabel.setVisible(false);
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
      interactPromptLabel.setText(String.format("[ %s ]  Pick up: %s", "E", label));
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

  /** Receive EventBus.characterEliminated — any character killed by any source. */
  @RegisterFunction
  public void onCharacterEliminated(String attackerName, String victimName,
                                    String weaponName, Texture2D weaponIcon, boolean headshot) {
    StringBuilder sb = new StringBuilder(victimName).append(" Eliminated");
    if (headshot) sb.append(" - Headshot");
    showNotification(sb.toString(), weaponIcon);
  }

  private void showNotification(String text, Texture2D icon) {
    if (eliminatedNotificationLabel != null) {
      eliminatedNotificationLabel.setText(text);
      eliminatedNotificationLabel.setVisible(true);
    }
    if (notificationIcon != null) {
      notificationIcon.setTexture(icon);
      notificationIcon.setVisible(icon != null);
    }
    killNotificationTimer = KILL_NOTIFICATION_DURATION;
  }
}
