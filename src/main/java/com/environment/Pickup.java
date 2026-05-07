package com.environment;

import com.character.Health;
import com.game.EventBus;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Area3D;
import godot.api.Input;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.RigidBody3D;
import godot.core.NodePath;

import java.util.ArrayList;
import java.util.List;

/**
 * World-space physics pickup. RigidBody3D provides physical presence (falls, rests on
 * surfaces). A child Area3D named "PickupArea" handles character detection.
 *
 * Scene setup:
 *   Pickup (RigidBody3D + subclass script)
 *     CollisionShape3D        ← physics body shape  (layer 3, mask layer 1)
 *     PickupArea (Area3D)
 *       CollisionShape3D      ← detection sphere    (layer 0, mask layer 2)
 *   Connect: PickupArea.body_entered → on_body_entered
 *   Connect: PickupArea.body_exited  → on_body_exited
 *
 * Post-pickup behaviour:
 *   removeOnPickup = true   → queue_free()  (one-shot consumable: health, key)
 *   pauseOnPickup  = true   → freeze + hide + disable area; resume via resumeFromPause()
 *   neither                 → stays active  (permanent station)
 *
 * Interaction modes:
 *   requireInteract = false → auto-pickup on body_entered  (default)
 *   requireInteract = true  → player must press "interact" action while in range;
 *                             EventBus.pickupInteractChanged fires to show/hide HUD prompt
 *
 * Subclasses override onCharacterEntered(Node) to apply the pickup effect and
 * getInteractLabel() to supply the HUD prompt text.
 * Re-declare @RegisterFunction onBodyEntered calling super so the method appears
 * in the subclass .gdj for scene signal connections.
 */
@RegisterClass(className = "Pickup")
public class Pickup extends RigidBody3D {

  protected static final NodePath WEAPON_CONTROLLER_PATH = new NodePath("WeaponController");
  private static final String PICKUP_AREA = "PickupArea";

  @RegisterProperty @Export public boolean removeOnPickup  = false;
  @RegisterProperty @Export public boolean pauseOnPickup   = false;
  @RegisterProperty @Export public boolean requireInteract = false;

  private final List<Node3D> overlappingBodies = new ArrayList<>();

  // ── Tick ─────────────────────────────────────────────────────────────────

  @RegisterFunction
  @Override
  public void _process(double delta) {
    if (requireInteract && !overlappingBodies.isEmpty()
        && Input.INSTANCE.isActionJustPressed("interact", false)) {
      triggerInteract();
    }
  }

  // ── Override points ───────────────────────────────────────────────────────

  protected void onCharacterEntered(Node character) {}

  /** Text shown in the HUD interact prompt. Override in subclasses. */
  protected String getInteractLabel() { return "Item"; }

  // ── Body detection (connected from PickupArea signals) ────────────────────

  @RegisterFunction
  public void onBodyEntered(Node3D body) {
    if (requireInteract) {
      Node character = resolveCharacter(body);
      if (character != null && isAlive(character)) {
        overlappingBodies.add(body);
        emitInteractPrompt(true);
      }
      return;
    }
    Node character = resolveCharacter(body);
    if (character == null || !isAlive(character)) return;
    onCharacterEntered(character);
    applyPostPickup();
  }

  @RegisterFunction
  public void onBodyExited(Node3D body) {
    overlappingBodies.remove(body);
    if (overlappingBodies.isEmpty()) emitInteractPrompt(false);
  }

  // ── Pause / resume ────────────────────────────────────────────────────────

  public void pause() {
    overlappingBodies.clear();
    emitInteractPrompt(false);
    setVisible(false);
    setFreezeEnabled(true);
    Node areaNode = getNodeOrNull(PICKUP_AREA);
    if (areaNode instanceof Area3D area) area.setMonitoring(false);
  }

  @RegisterFunction
  public void resumeFromPause() {
    setVisible(true);
    setFreezeEnabled(false);
    Node areaNode = getNodeOrNull(PICKUP_AREA);
    if (areaNode instanceof Area3D area) area.setMonitoring(true);
    onResumed();
  }

  protected void onResumed() {}

  // ── Equip / return lifecycle (used by WeaponItem) ─────────────────────────

  /** Called after this pickup is reparented into a character's inventory marker.
   *  Freezes physics and disables detection without hiding the node. */
  public void onPickedUp() {
    overlappingBodies.clear();
    emitInteractPrompt(false);
    setFreezeEnabled(true);
    Node areaNode = getNodeOrNull(PICKUP_AREA);
    if (areaNode instanceof Area3D area) area.setMonitoring(false);
  }

  /** Called after this pickup is reparented back into the world scene.
   *  Re-enables physics and detection. */
  public void onReturnedToWorld() {
    setFreezeEnabled(false);
    Node areaNode = getNodeOrNull(PICKUP_AREA);
    if (areaNode instanceof Area3D area) area.setMonitoring(true);
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  protected final Node resolveCharacter(Node3D body) {
    if (body.hasNode(WEAPON_CONTROLLER_PATH)) return body;
    Node owner = body.getOwner();
    if (owner != null && owner.hasNode(WEAPON_CONTROLLER_PATH)) return owner;
    return null;
  }

  private void triggerInteract() {
    for (Node3D body : new ArrayList<>(overlappingBodies)) {
      Node character = resolveCharacter(body);
      if (character != null && isAlive(character)) {
        onCharacterEntered(character);
        overlappingBodies.clear();
        emitInteractPrompt(false);
        applyPostPickup();
        return;
      }
    }
  }

  private void applyPostPickup() {
    if (removeOnPickup) queueFree();
    else if (pauseOnPickup) pause();
  }

  private boolean isAlive(Node character) {
    Node healthNode = character.getNodeOrNull("Health");
    if (healthNode instanceof Health h) return !h.isDead();
    return true;
  }

  private void emitInteractPrompt(boolean inRange) {
    Node busNode = getNodeOrNull("/root/EventBus");
    if (busNode instanceof EventBus bus) {
      bus.pickupInteractChanged.emit(inRange, inRange ? getInteractLabel() : "");
    }
  }
}
