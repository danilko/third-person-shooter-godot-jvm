package com.openworld.item;

import com.openworld.control.Controllable;
import com.openworld.character.Health;
import com.openworld.game.EventBus;
import com.openworld.net.NetworkManager;
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
import com.openworld.character.CharacterInfo;
import com.openworld.game.GameManager;
import com.openworld.net.NetworkController;
import com.openworld.weapon.WeaponController;
import com.openworld.weapon.WeaponItem;

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

  /**
   * Stable replication identity, mirroring CharacterInfo.characterId. Scene-placed
   * pickups derive it from their scene path in _ready() — identical on every peer
   * because all peers load the same World.tscn. Runtime-spawned pickups (drops) get a
   * UUID assigned by the originating peer's drop event before any peer references it.
   */
  @RegisterProperty @Export public String pickupId = "";

  /** Group every pickup joins in _ready() — replication handlers resolve pickupId through it. */
  public static final String PICKUPS_GROUP = "pickups";

  private final List<Node3D> overlappingBodies = new ArrayList<>();
  /** True while held in a character's inventory; blocks body_entered re-triggering. */
  protected boolean equipped = false;
  private float pickupCooldown = 0f;
  private EventBus eventBus;
  /**
   * Networked host only: a collector queued in a body_entered signal, resolved in _process
   * (a safe, non-signal context) so the equip is SYNCHRONOUS and the host broadcasts the
   * resolved outcome rather than a pre-equip guess. See {@link #collectBy}.
   */
  private Node pendingCollector;

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  /** Subclass overrides MUST call super._ready() or the pickup never registers for replication. */
  @RegisterFunction
  @Override
  public void _ready() {
    addToGroup(new StringName(PICKUPS_GROUP));
    // NodePath.toString() returns "NodePath(<subnames>)" — empty for plain paths, so every
    // pickup would share the literal id "NodePath()". getPath() (the path property) is the
    // actual path string, identical on every peer for world-scene nodes.
    if (pickupId.isEmpty()) pickupId = getPath().getPath();
  }

  // ── Tick ─────────────────────────────────────────────────────────────────

  @RegisterFunction
  @Override
  public void _process(double delta) {
    if (pickupCooldown > 0f) pickupCooldown -= (float) delta;

    // Networked-host collect, resolved out of the body_entered signal (see collectBy).
    if (pendingCollector != null) {
      Node collector = pendingCollector;
      pendingCollector = null;
      resolveHostCollect(collector);
    }

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
    if (equipped || pendingCollector != null || pickupCooldown > 0f) return;
    Node character = resolveCharacter(body);
    if (character == null || !isAlive(character) || !isLocallyOwned(character)) return;

    if (shouldAutoPickup(character)) {
      collectBy(character);
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
   *  Hides immediately so the world pickup vanishes on collection, then freezes physics.
   *  WeaponItem.moveWeaponToHand calls show() afterwards for weapons with a hold socket,
   *  so the hide here is intentionally overridden for visually-held weapons. */
  public void onPickedUp() {
    equipped = true;
    overlappingBodies.clear();
    emitInteractPrompt(false);
    hide();
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
      if (character != null && isAlive(character) && isLocallyOwned(character)) {
        overlappingBodies.clear();
        emitInteractPrompt(false);
        collectBy(character);
        return;
      }
    }
  }

  /**
   * Single collection entry point — routes by network role (host-arbitrated pickups):
   *   single-player / host-owned body → collect locally, then (if hosting) broadcast
   *     MSG_PICKUP_TAKEN so every client mirrors the collect on its own copy;
   *   client-owned body → send MSG_PICKUP_REQUEST only; the host validates and the
   *     TAKEN echo performs the actual collect here (see applyReplicatedPickup).
   * The owner-gate in onBodyEntered/triggerInteract guarantees the character passed
   * here is locally owned, so "am I the host" fully determines the branch.
   */
  private void collectBy(Node character) {
    Node netNode = getNodeOrNull("/root/NetworkManager");
    if (netNode instanceof NetworkManager net && net.isNetworked()) {
      String characterId = resolveCharacterId(character);
      if (characterId.isEmpty()) return;   // unreplicatable collector — never collect silently in MP
      if (!net.isServer()) {
        net.requestPickup(pickupId, characterId);
        return;
      }
      // Networked host: defer to _process so the equip resolves SYNCHRONOUSLY (out of this
      // body_entered physics signal, where reparent is forbidden) and the broadcast carries
      // the post-merge OUTCOME. Broadcasting before the equip could announce a pickup the
      // slot-displacement guard then bounced back to the world — every client would delete an
      // item the host still has. pendingCollector blocks re-trigger until _process resolves it.
      pendingCollector = character;
      return;
    }
    // Single-player: resolve inline (no broadcast, no cross-peer convergence concern).
    onCharacterEntered(character);
    applyPostPickup();
  }

  /**
   * Networked host: resolve a queued collect synchronously, then broadcast MSG_PICKUP_TAKEN
   * only for what was actually consumed (equipped or merged). Mirrors GameManager's grant path
   * (applyReplicatedPickup → broadcast-if-taken) for the host's OWN collects, so a cluster of
   * same-type pickups merges deterministically and clients are never told an item is taken that
   * the host bounced back to the world. Runs in _process — safe context for reparent.
   */
  private void resolveHostCollect(Node character) {
    if (character == null || !character.isInsideTree()) return;
    // Capture state BEFORE collecting — a throwable merge consumes this node's magazine.
    int magazine = getReplicatedMagazine();
    int reserve = getReplicatedReserve();
    applyReplicatedPickup(character, magazine, reserve);   // synchronous equip + applyPostPickup
    Node netNode = getNodeOrNull("/root/NetworkManager");
    if (isTaken() && netNode instanceof NetworkManager net && net.isNetworked() && net.isServer()) {
      String characterId = resolveCharacterId(character);
      if (!characterId.isEmpty()) net.broadcastPickupTaken(pickupId, characterId, magazine, reserve);
    }
  }

  /**
   * Executes a host-confirmed MSG_PICKUP_TAKEN on this peer — the same collect path a
   * local pickup takes, with the item state stamped from the event first so every peer's
   * copy of the item is identical. Idempotent: a duplicate event on an already-taken
   * item is a no-op (equipped is set by onCharacterEntered/WeaponItem before any defer).
   */
  public void applyReplicatedPickup(Node character, int magazine, int reserve) {
    if (equipped) return;
    stampReplicatedAmmo(magazine, reserve);
    // Resolve the equip SYNCHRONOUSLY (this runs in NetworkManager's _process packet drain,
    // not a physics signal, so reparent is legal). Each granted/echoed pickup then fully
    // lands before the next is processed, so a cluster of same-type items merges
    // deterministically — identical on host and every client. See WeaponController.synchronousEquip.
    Node wcNode = character.getNodeOrNull(WEAPON_CONTROLLER_PATH);
    com.openworld.weapon.WeaponController wc =
        wcNode instanceof com.openworld.weapon.WeaponController w ? w : null;
    if (wc != null) wc.setSynchronousEquip(true);
    try {
      onCharacterEntered(character);
    } finally {
      if (wc != null) {
        wc.setSynchronousEquip(false);
        // Refresh the owner's HUD to the post-collect active-weapon count — a throwable
        // merge that landed on the active slot must update the displayed count immediately,
        // not stay stale until the next manual weapon switch.
        wc.refreshActiveAmmoDisplay();
      }
    }
    applyPostPickup();
  }

  /** True once collected into an inventory — the host's ALREADY_TAKEN arbitration check. */
  public boolean isTaken() { return equipped; }

  // Replication hooks — WeaponItem overrides to carry magazine/reserve; base pickups have no
  // ammo. Getters are public so the host's grant path (GameManager.processPickupRequest) can
  // sample the item state it puts on the wire.
  public int getReplicatedMagazine() { return 0; }
  public int getReplicatedReserve()  { return 0; }
  protected void stampReplicatedAmmo(int magazine, int reserve) { }

  /** The stable CharacterInfo.characterId of a collector, or "" when it has none. */
  private String resolveCharacterId(Node character) {
    if (character instanceof Controllable c && c.getCharacterInfo() != null) {
      return c.getCharacterInfo().characterId;
    }
    return "";
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

  /**
   * Only the peer that OWNS a character may process its pickup intent. Without this,
   * a NetworkController puppet walking over a pickup would collect it into its local
   * inventory — diverging inventories between peers (each peer's copy of the same
   * character collecting different items). Single-player / non-networked: always true.
   * Networked: resolves CharacterInfo.ownerPeerId against this peer's id; a body whose
   * ownership can't be established is conservatively NOT collectable.
   */
  protected final boolean isLocallyOwned(Node character) {
    Node netNode = getNodeOrNull("/root/NetworkManager");
    if (!(netNode instanceof NetworkManager net) || !net.isNetworked()) return true;
    if (!(character instanceof Controllable c) || c.getCharacterInfo() == null) return false;
    return net.isAuthorityFor(c.getCharacterInfo());
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
