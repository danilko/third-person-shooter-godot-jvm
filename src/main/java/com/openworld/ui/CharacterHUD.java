package com.openworld.ui;

import com.openworld.game.EventBus;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.*;
import godot.core.Callable;
import godot.core.MethodCallable;
import godot.core.NodePath;
import godot.core.StringNames;
import com.openworld.character.Health;
import com.openworld.weapon.WeaponController;
import godot.core.Color;

/**
 * Per-character HUD: the bottom-left health number + bar (under the minimap), the swim air bar above it,
 * and the interact prompt just under the crosshair.
 *
 * Transient toasts (weapon pickups, mission events) and the kill feed are owned by
 * {@link HUDManager} and rendered through the shared {@link Feed} components, so this
 * widget stays a thin per-character status panel that survives HUD context switches.
 */
@Script(className = "CharacterHUD")
public class CharacterHUD extends Control {

  @Export
  public NodePath healthLabelPath = new NodePath("Health/Value");

  /** Thin health bar beside the number (bottom-left, under the minimap). */
  @Export
  public NodePath healthBarPath = new NodePath("Health/Bar");

  private Label healthLabel;
  private ProgressBar healthBar;
  private StyleBoxFlat healthFill;
  private float maxHealth = 100f;
  private Label interactPromptLabel;
  /** Swim breath meter root (shown only while submerged) + its fill bar. Optional in the scene. */
  private Control oxygenRoot;
  private ProgressBar oxygenBar;
  private String playerCharacterId = "";

  @Register
  @Override
  public void _ready() {
    if (getNodeOrNull(healthLabelPath) instanceof Label l) healthLabel = l;
    if (getNodeOrNull(healthBarPath) instanceof ProgressBar b) {
      healthBar = b;
      healthFill = new StyleBoxFlat();          // this HUD's own fill, recoloured by health
      healthFill.setCornerRadiusAll(2);
      healthFill.setBgColor(HudPalette.TEXT);
      healthBar.addThemeStyleboxOverride(new godot.core.StringName("fill"), healthFill);
    }

    Node promptNode = getNodeOrNull("InteractPrompt");
    if (promptNode instanceof Label l) interactPromptLabel = l;

    Node oxNode = getNodeOrNull("Oxygen");
    if (oxNode instanceof Control c) {
      oxygenRoot = c;
      oxygenRoot.setVisible(false);   // hidden until the swimmer submerges
      Node bar = oxNode.getNodeOrNull("Bar");
      if (bar instanceof ProgressBar pb) oxygenBar = pb;
    }

    Node busNode = getNodeOrNull("/root/EventBus");
    if (busNode instanceof EventBus bus) {
      bus.playerHealthChanged.connectUnsafe(
          MethodCallable.createUnsafe(this, "onHealthChanged"),
          godot.api.Object.ConnectFlags.DEFAULT);
      bus.pickupInteractChanged.connectUnsafe(
          MethodCallable.createUnsafe(this, "onPickupInteractChanged"),
          godot.api.Object.ConnectFlags.DEFAULT);
      bus.playerOxygenChanged.connectUnsafe(
          MethodCallable.createUnsafe(this, "onOxygenChanged"),
          godot.api.Object.ConnectFlags.DEFAULT);
    }
  }

  /**
   * Receive EventBus.playerOxygenChanged — fill the swim breath meter and show it only while air is
   * below full (i.e. the swimmer is/was submerged); a full tank hides the widget.
   */
  @Register
  public void onOxygenChanged(float current, float max) {
    if (oxygenRoot == null) return;
    oxygenRoot.setVisible(current < max);
    if (oxygenBar != null && max > 0f) oxygenBar.setValue((current / max) * 100.0);
  }

  /**
   * Receive WeaponController.ammoChanged (routed per-character by HUDManager's C2 path).
   * No-op today — ammo is displayed by WeaponSlotsUI / the radial menu; kept as the
   * per-character hook for a future dedicated ammo widget (e.g. co-op squad overlays).
   */
  @Register
  public void onAmmoChanged(int magazine, int reserve) {
  }

  /** Receive EventBus.playerHealthChanged (current health for the active player). */
  @Register
  public void onHealthChanged(float currentHealth) {
    if (healthLabel != null) {
      healthLabel.setText(String.valueOf((int) Math.ceil(Math.max(0f, currentHealth))));
    }
    if (healthBar != null) {
      healthBar.setValue(maxHealth > 0f ? 100.0 * Math.max(0f, currentHealth) / maxHealth : 0.0);
      // white, amber under 50%, red under 25% (HudPalette); the number follows the bar
      Color c = HudPalette.forFraction(maxHealth > 0f ? currentHealth / maxHealth : 0f);
      if (healthFill != null) healthFill.setBgColor(c);
      if (healthLabel != null) healthLabel.setModulate(c);
    }
  }

  /** The bar's full value, from the wired player's Health (HUDManager.wirePlayer). */
  public void setMaxHealth(float max) {
    maxHealth = max > 0f ? max : 100f;
  }

  /** Receive EventBus.pickupInteractChanged — show/hide the "Press E to pick up" prompt. */
  @Register
  public void onPickupInteractChanged(boolean inRange, String label) {
    if (interactPromptLabel == null) return;
    if (inRange) {
      // Labels may carry their own key hint (vehicles send "[ F ]  Enter vehicle" for the
      // use_carrier action); only default to the pickup "interact" key when they don't.
      interactPromptLabel.setText(label.startsWith("[") ? label : "[ E ]  " + label);
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
