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
import godot.core.StringName;

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

  /**
   * Seconds the pickup ignores all body_entered events after being returned to the
   * world (e.g. after a character drops it). Prevents the dropping character from
   * immediately re-acquiring the item. Industry standard: 0.3–0.5 s.
   */
  @RegisterProperty @Export public float pickupCooldownAfterDrop = 0.5f;

  private final List<Node3D> overlappingBodies = new ArrayList<>();
  /** True while held in a character's inventory; blocks body_entered re-triggering. */
  protected boolean equipped = false;
  private float pickupCooldown = 0f;
  private EventBus eventBus;

  // ── Tick ─────────────────────────────────────────────────────────────────

  @RegisterFunction
  @Override
  public void _process(double delta) {
    if (pickupCooldown > 0f) pickupCooldown -= (float) delta;

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
    if (equipped || pickupCooldown > 0f) return;
    Node character = resolveCharacter(body);
    if (character == null || !isAlive(character)) return;

    if (shouldAutoPickup(character)) {
      onCharacterEntered(character);
      applyPostPickup();
    } else {
      overlappingBodies.add(body);
      emitInteractPrompt(true);
    }
  }

  /**
   * Returns true when this pickup should be collected immediately on body enter,
   * bypassing the interact prompt. Default: auto-pickup when requireInteract is false.
   * Subclasses can override for context-sensitive behaviour (e.g. WeaponItem checks
   * whether the target slot is free).
   */
  protected boolean shouldAutoPickup(Node character) {
    return !requireInteract;
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
    // setMonitoring must be deferred — this method can be called from body signals.
    Node areaNode = getNodeOrNull(PICKUP_AREA);
    if (areaNode instanceof Area3D area) area.setDeferred(new StringName("monitoring"), false);
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
   *  Freezes physics; sets the equipped flag so onBodyEntered ignores further
   *  contacts without touching Area3D monitoring (which is blocked inside body signals). */
  public void onPickedUp() {
    equipped = true;
    overlappingBodies.clear();
    emitInteractPrompt(false);
    setFreezeEnabled(true);
  }

  /** Called after this pickup is reparented back into the world scene.
   *  Re-enables physics and detection. Safe to call from _process (not a signal). */
  public void onReturnedToWorld() {
    equipped = false;
    pickupCooldown = pickupCooldownAfterDrop;
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

  private EventBus getEventBus() {
    if (eventBus == null) {
      Node n = getNodeOrNull("/root/EventBus");
      if (n instanceof EventBus eb) eventBus = eb;
    }
    return eventBus;
  }

  private void emitInteractPrompt(boolean inRange) {
    EventBus bus = getEventBus();
    if (bus != null) bus.pickupInteractChanged.emit(inRange, inRange ? "Pick up: " + getInteractLabel() : "");
  }
}
