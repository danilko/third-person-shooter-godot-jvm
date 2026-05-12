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
import godot.global.GD;

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

  /** Path to the {@link Feed} sibling node that receives kill-feed entries. */
  @RegisterProperty @Export
  public NodePath feedEntryPath = new NodePath("FeedEntry");

  /** Scene for {@link DefeatedFeedEntry} rows. Falls back to hard-coded path if null. */
  @RegisterProperty @Export
  public PackedScene defeatedEntryScene;

  private Label healthLabel;
  private Label magazineLabel;
  private Label reserveLabel;
  private Label pickupNotificationLabel;
  private TextureRect notificationIcon;
  private Label interactPromptLabel;
  private Feed feed;
  private String playerCharacterId = "";
  private double pickupTimer = 0.0;
  private static final double PICKUP_NOTIFICATION_DURATION = 3.0;
  private static final String DEFEATED_ENTRY_SCENE_PATH =
          "res://src/main/resources/com/ui/DefeatedFeedEntry.tscn";

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
    pickupNotificationLabel = (Label) getNode("Notification/EliminatedNotification");
    Node iconNode = getNodeOrNull(notificationIconPath);
    if (iconNode instanceof TextureRect tr) notificationIcon = tr;
    Node promptNode = getNodeOrNull("InteractPrompt");
    if (promptNode instanceof Label l) interactPromptLabel = l;

    // Scan children for a Feed node — more robust than a path that can be
    // cleared in the inspector (same pattern Character uses to find Controller).
    for (Node child : getChildren()) {
      if (child instanceof Feed f) { feed = f; break; }
    }

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

  /** Push a {@link DefeatedFeedEntry} row to the kill feed. */
  @RegisterFunction
  public void onCharacterEliminated(String attackerName, String attackerFaction,
                                    String victimName,   String victimFaction,
                                    String weaponName,   Texture2D weaponIcon,
                                    boolean headshot) {
    if (feed == null) return;
    PackedScene scene = resolveDefeatedEntryScene();
    if (scene == null) return;
    DefeatedFeedEntry entry = (DefeatedFeedEntry) scene.instantiate();
    entry.lifespan = feed.entryLifespan;
    feed.push(entry);
    entry.populate(attackerName, attackerFaction, victimName, victimFaction, weaponIcon, headshot);
  }

  private PackedScene resolveDefeatedEntryScene() {
    if (defeatedEntryScene != null) return defeatedEntryScene;
    godot.api.Object loaded = GD.load(DEFEATED_ENTRY_SCENE_PATH);
    return (loaded instanceof PackedScene ps) ? ps : null;
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
