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
 * Per-character HUD: health label and interact prompt.
 *
 * Transient toasts (weapon pickups, mission events) and the kill feed are owned by
 * {@link HUDManager} and rendered through the shared {@link Feed} components, so this
 * widget stays a thin per-character status panel that survives HUD context switches.
 */
@RegisterClass(className = "CharacterHUD")
public class CharacterHUD extends Control {

  @RegisterProperty
  @Export
  public NodePath healthLabelPath = new NodePath("Health/ColorRect/Health");

  private Label healthLabel;
  private Label interactPromptLabel;
  private String playerCharacterId = "";

  @RegisterFunction
  @Override
  public void _ready() {
    if (hasNode(healthLabelPath)) {
      healthLabel = (Label) getNode(healthLabelPath);
    }

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

  /**
   * Receive WeaponController.ammoChanged (routed per-character by HUDManager's C2 path).
   * No-op today — ammo is displayed by WeaponSlotsUI / the radial menu; kept as the
   * per-character hook for a future dedicated ammo widget (e.g. co-op squad overlays).
   */
  @RegisterFunction
  public void onAmmoChanged(int magazine, int reserve) {
  }

  /** Receive Health.damaged signal (pass currentHealth from the character). */
  @RegisterFunction
  public void onHealthChanged(float currentHealth) {
    if (healthLabel != null) {
      healthLabel.setText(String.valueOf((int) currentHealth));
    }
  }

  /** Receive EventBus.pickupInteractChanged — show/hide the "Press E to pick up" prompt. */
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
}
