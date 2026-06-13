package com.environment;

import com.character.Controllable;
import com.character.WeaponController;
import com.game.EventBus;
import com.game.GameManager;
import com.game.NetworkManager;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.api.Area3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.core.NodePath;

/**
 * Static area that fills all weapons when a character enters.
 * Extends Area3D directly — no physics body needed for a fixed station.
 * Will be refactored onto Pickup base when drop/respawn behaviour is added.
 */
@RegisterClass(className = "AmmoRefill")
public class AmmoRefill extends Area3D {

  private static final NodePath WEAPON_CONTROLLER_PATH = new NodePath("WeaponController");

  @RegisterFunction
  public void onBodyEntered(Node3D body) {
    Node character = resolveCharacter(body);
    if (character == null) return;

    // Host-authoritative refill (Phase F): networked, only the HOST detects the overlap —
    // for every body including client puppets (the station area is large, so the puppet's
    // ~50-100 ms interp delay is immaterial) — applies it, and mirrors it to every peer
    // via the WORLD_EVENT seam. Single-player: isServer() is true with no connection, so
    // the local apply below runs unchanged and the broadcast no-ops.
    Node netNode = getNodeOrNull("/root/NetworkManager");
    NetworkManager net = netNode instanceof NetworkManager n ? n : null;
    if (net != null && net.isNetworked() && !net.isServer()) return;

    WeaponController wc = (WeaponController) character.getNode(WEAPON_CONTROLLER_PATH);
    wc.fillWeaponAmmo();

    if (net != null && character instanceof Controllable c && c.getCharacterInfo() != null) {
      net.broadcastWorldEvent(GameManager.WORLD_EVENT_AMMO_REFILL, c.getCharacterInfo().characterId, 0f);
    }

    Node busNode = getNodeOrNull("/root/EventBus");
    if (busNode instanceof EventBus bus) bus.ammoPickedUp.emit(0);
  }

  private Node resolveCharacter(Node3D body) {
    if (body.hasNode(WEAPON_CONTROLLER_PATH)) return body;
    Node owner = body.getOwner();
    if (owner != null && owner.hasNode(WEAPON_CONTROLLER_PATH)) return owner;
    return null;
  }

}
