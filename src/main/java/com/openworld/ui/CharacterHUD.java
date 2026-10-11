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
import godot.global.GD;

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
  private godot.api.TextureRect interactKey;
  /** The key the prompt shows as a glyph ("" = shown as text); probe readout. */
  private String promptKey = "";
  @Register public String promptKeyNow() { return interactKey != null && interactKey.isVisible() ? promptKey : ""; }
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
      healthFill.setCornerRadiusAll(0);
      healthFill.setBgColor(HudPalette.TEXT);
      healthBar.addThemeStyleboxOverride(new godot.core.StringName("fill"), healthFill);
    }

    Node promptNode = getNodeOrNull("InteractPrompt");
    if (promptNode instanceof Label l) {
      interactPromptLabel = l;
      interactKey = new godot.api.TextureRect();            // the key's keycap glyph, left of the text (KeyGlyph)
      interactKey.setName(new godot.core.StringName("KeyGlyph"));
      interactKey.setExpandMode(godot.api.TextureRect.ExpandMode.IGNORE_SIZE);
      interactKey.setStretchMode(godot.api.TextureRect.StretchMode.KEEP_ASPECT_CENTERED);
      interactKey.setMouseFilter(Control.MouseFilter.IGNORE);
      interactKey.setVisible(false);
      l.addChild(interactKey);
    }

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
          godot.core.ConnectFlags.DEFAULT);
      bus.pickupInteractChanged.connectUnsafe(
          MethodCallable.createUnsafe(this, "onPickupInteractChanged"),
          godot.core.ConnectFlags.DEFAULT);
      bus.interactPromptChanged.connectUnsafe(
          MethodCallable.createUnsafe(this, "onInteractPromptChanged"),
          godot.core.ConnectFlags.DEFAULT);
      bus.playerOxygenChanged.connectUnsafe(
          MethodCallable.createUnsafe(this, "onOxygenChanged"),
          godot.core.ConnectFlags.DEFAULT);
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

  private static final java.util.Map<String, godot.api.Texture2D> GLYPHS = new java.util.HashMap<>();

  /** The keycap glyph for {@code key}, or null when none is shipped (then the prompt spells it as text). */
  private static godot.api.Texture2D glyph(String key) {
    boolean pad = com.openworld.control.InputDevice.pad();
    // a pad prompt shows the input BOUND NOW to the key's action (KeyBindings' pad table); a key shows its keycap
    String padSpec = pad ? com.openworld.control.KeyBindings.padSpecForPrompt(key) : null;
    String padName = com.openworld.control.BindingTable.padGlyph(padSpec);
    return GLYPHS.computeIfAbsent(pad ? "pad:" + padSpec : key, k -> {
      String path = !pad || padSpec == null ? KeyGlyph.texturePath(key)
          : padName != null ? "res://assets/ui/prompts/steamdeck_" + padName + ".png" : "";
      return godot.api.ResourceLoader.INSTANCE.exists(path, "") && godot.global.GD.load(path) instanceof godot.api.Texture2D t
          ? t : null;
    });
  }

  /**
   * Every prompt on offer, by the instance id of the node offering it, in the order they were offered. The HUD shows
   * the NEWEST; one source withdrawing never hides another's (a door's "out of range" used to hide a car's "Enter
   * vehicle" in the same frame). Source 0 is the legacy unkeyed signal.
   */
  private final java.util.LinkedHashMap<Long, String> prompts = new java.util.LinkedHashMap<>();
  private final java.util.HashMap<Long, Node> promptSources = new java.util.HashMap<>();
  private double promptPrune;
  private int glyphSwitches;

  /** Receive the legacy unkeyed EventBus.pickupInteractChanged (source 0). */
  @Register
  public void onPickupInteractChanged(boolean inRange, String label) { setPrompt(0L, null, inRange, label); }

  /** Receive EventBus.interactPromptChanged: {@code source} offers or withdraws its prompt. */
  @Register
  public void onInteractPromptChanged(Node source, boolean inRange, String label) {
    setPrompt(source == null ? 0L : source.getInstanceId(), source, inRange, label);
  }

  private void setPrompt(long id, Node source, boolean inRange, String label) {
    if (inRange) {
      prompts.put(id, label == null ? "" : label);   // a re-offer updates in place, no reorder
      if (source != null) promptSources.put(id, source);
    } else {
      prompts.remove(id);
      promptSources.remove(id);
    }
    refreshPrompt();
  }

  /** The prompts on offer, newest last (probe readout). */
  @Register public int promptCountNow() { return prompts.size(); }
  /** The label the prompt shows now ("" when hidden; probe readout). */
  @Register public String promptTextNow() {
    return interactPromptLabel != null && interactPromptLabel.isVisible() ? interactPromptLabel.getText() : "";
  }

  @Register
  @Override
  public void _process(double delta) {
    // a source freed without withdrawing its prompt (a pickup taken by a peer, a car despawned) must not leave it up
    // the human picked up the pad (or the mouse): redraw the shown prompt with that device's glyph
    if (glyphSwitches != com.openworld.control.InputDevice.switches()) {
      glyphSwitches = com.openworld.control.InputDevice.switches();
      if (!prompts.isEmpty()) refreshPrompt();
    }
    if (prompts.isEmpty() || (promptPrune -= delta) > 0) return;
    promptPrune = 0.5;
    boolean changed = prompts.keySet().removeIf(id -> {
      if (id == 0L) return false;
      Node n = promptSources.get(id);
      boolean gone = n == null || !GD.isInstanceValid(n) || !n.isInsideTree();
      if (gone) promptSources.remove(id);
      return gone;
    });
    if (changed) refreshPrompt();
  }

  private void refreshPrompt() {
    String newest = null;
    for (String v : prompts.values()) newest = v;
    showPrompt(newest != null, newest == null ? "" : newest);
  }

  private void showPrompt(boolean inRange, String label) {
    if (interactPromptLabel == null) return;
    if (inRange) {
      // Labels may carry their own key hint ("[ F ]  Enter vehicle", "Door (E)"); with none it is the interact
      // key, E. The key is drawn as a keycap glyph (Kenney Input Prompts) left of the text, else as "[ X ]".
      KeyGlyph.Prompt p = KeyGlyph.parse(label);
      // a pad shows the action's pad glyph (fixed layout); a keyboard shows the key BOUND NOW (KeyBindings, F2)
      boolean onPad = com.openworld.control.InputDevice.pad();
      String shown = onPad ? p.key() : com.openworld.control.KeyBindings.shownKey(p.key());
      godot.api.Texture2D glyph = glyph(shown);
      // no glyph shipped for it: spell the input -- on a pad, the button bound now ("[ LB ]"), not the keyboard letter
      String padSpec = onPad ? com.openworld.control.KeyBindings.padSpecForPrompt(p.key()) : null;
      String spelled = padSpec != null ? com.openworld.control.BindingTable.label(padSpec, k -> "?") : shown;
      interactPromptLabel.setText(glyph != null ? p.text() : "[ " + spelled + " ]  " + p.text());
      interactPromptLabel.setVisible(true);
      if (interactKey != null) {
        promptKey = shown;
        interactKey.setTexture(glyph);
        interactKey.setVisible(glyph != null);
        if (glyph != null) {
          float h = (float) interactPromptLabel.getSize().getY() + 6f;
          godot.api.Font f = interactPromptLabel.getLabelSettings() != null && interactPromptLabel.getLabelSettings().getFont() != null
              ? interactPromptLabel.getLabelSettings().getFont() : interactPromptLabel.getThemeDefaultFont();
          int fs = interactPromptLabel.getLabelSettings() != null ? interactPromptLabel.getLabelSettings().getFontSize() : 16;
          float tw = f == null ? 0f : (float) f.getStringSize(p.text(), godot.core.HorizontalAlignment.LEFT, -1f, fs).getX();
          float left = ((float) interactPromptLabel.getSize().getX() - tw) * 0.5f;
          interactKey.setSize(new godot.core.Vector2(h, h));
          interactKey.setPosition(new godot.core.Vector2(left - h - 6f, -3f));
        }
      }
    } else {
      interactPromptLabel.setVisible(false);
      if (interactKey != null) interactKey.setVisible(false);
    }
  }

  // The healing supplies are a weapon stack now (weapon.SupplyItem, the CONSUMABLE slot): the weapon panel and the
  // inventory column show what is carried, so this HUD keeps no supplies line of its own (user, 2026-10-06).
  private com.openworld.character.Character player;

  public void setPlayer(com.openworld.character.Character c) { player = c; }

  /** Called by HUDManager.wirePlayer() to bind this HUD to a specific character. */
  public void setPlayerCharacterId(String id) {
    playerCharacterId = id != null ? id : "";
  }
}
