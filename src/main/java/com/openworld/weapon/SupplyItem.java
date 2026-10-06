package com.openworld.weapon;

import com.openworld.character.Character;
import com.openworld.item.SupplyCatalog;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.GeometryInstance3D;
import godot.api.Material;
import godot.api.Node;
import godot.api.Texture2D;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.List;

/**
 * A healing supply (food, medical, "strange") carried as a WEAPON in the CONSUMABLE slot (user, 2026-10-06: "let these
 * health items be a weapon category, so they can be given away / used on other folks, or used by self, and show up in
 * the weapon menu"). It replaced the H key and the per-character supply counts.
 *
 * <ul>
 *   <li>One kind at a time, like a grenade stack: the magazine IS the count, the slot clears when the last one is used,
 *       picking up another kind displaces this stack (it drops as a pickup).</li>
 *   <li>FIRE uses one on yourself. Holding AIM on another living character within {@link #giveReach} and
 *       {@link #giveConeDeg} of the aim uses it on THEM; that character wears an outline while it is the target
 *       (local, this peer only -- an L4D-style rim, {@code assets/vfx/outline/target_outline.tres}).</li>
 *   <li>DROP (the ordinary drop key) gives the stack away as a pickup anyone can take.</li>
 *   <li>Health is applied on the authoritative peer: a client sends {@code MSG_SUPPLY_USE} (user, target, supply).</li>
 * </ul>
 *
 * <p>Every kind shares this ONE scene ({@code weapon/Supply.tscn}); {@link #configure} takes the kind's row from
 * {@code item/supplies.json}. {@link WeaponCatalog#instantiate} and the inventory manifest both route a supply id here,
 * so there is no per-kind scene or catalog row to keep in step.
 */
@Script(className = "SupplyItem")
public class SupplyItem extends WeaponItem {

  public static final String SCENE = "res://src/main/resources/com/openworld/weapon/Supply.tscn";
  private static final String OUTLINE = "res://assets/vfx/outline/target_outline.tres";

  /** The supply row ({@code item/supplies.json}) this stack is. */
  @Export public String supplyId = "";
  /** How close a character must be to be given one (m, chest to chest). */
  @Export public float giveReach = 2.5f;
  /** How far off the aim the other character may stand (deg). */
  @Export public float giveConeDeg = 25f;

  private float healAmount;
  private Character outlined;
  private final List<GeometryInstance3D> outlinedMeshes = new ArrayList<>();

  public SupplyItem() {
    auto = false;
    isInfiniteAmmo = false;
    autoReloadOnEmpty = false;
    slotType = WeaponSlotType.CONSUMABLE.ordinal();
    weaponArchetype = "throwable";
    holdSocket = "SocketThrowable";
    fireRate = 1.0f;          // one use a second
    switchSpeed = 3.0f;
    reserve = 0;
    reserveMax = 0;
    damage = 0f;
  }

  /** Fresh, un-parented stack of {@code supplyId}; null if the id is unknown or the scene does not load. */
  public static SupplyItem instantiate(String supplyId, int count) {
    if (SupplyCatalog.find(supplyId) == null) return null;
    if (!(GD.INSTANCE.load(SCENE) instanceof godot.api.PackedScene ps) || !(ps.instantiate() instanceof SupplyItem s)) {
      GD.INSTANCE.printErr("SupplyItem: " + SCENE + " is not a SupplyItem scene");
      return null;
    }
    s.configure(supplyId);
    if (count > 0) s.magazine = Math.min(count, s.magazineSize);
    return s;
  }

  /** Become a stack of {@code id} (full). Safe to call twice. */
  public void configure(String id) {
    SupplyCatalog.Supply row = SupplyCatalog.find(id);
    if (row == null) { GD.INSTANCE.printErr("SupplyItem: no supply '" + id + "'"); return; }
    supplyId = id;
    weaponId = id;
    weaponName = row.name();
    healAmount = row.heal();
    magazineSize = row.max();
    magazine = row.max();
    if (GD.INSTANCE.load("res://assets/ui/weapons/supply_" + row.kind() + ".png") instanceof Texture2D t) weaponIcon = t;
  }

  @Register
  @Override
  public void _ready() {
    super._ready();
    if (!supplyId.isEmpty() && healAmount <= 0f) configure(supplyId);
  }

  @Override public WeaponType getWeaponType()       { return WeaponType.THROWN; }
  @Override public WeaponSlotType resolveSlotType() { return WeaponSlotType.CONSUMABLE; }
  @Override public boolean canUse()                 { return magazine > 0 && isSemiAutoReady(); }
  @Override protected boolean launchesTowardAim()   { return false; }
  @Override public boolean autoReloadsOnEmpty()     { return false; }
  @Override public boolean shouldDropToWorld()      { return isDroppable && magazine > 0; }
  @Override public void onMagazineEmpty()           { if (weaponController != null) weaponController.clearActiveSlot(); }

  public float healAmount() { return healAmount; }

  @Register public String outlinedNow() {
    return outlined != null && outlined.characterInfo != null ? outlined.characterInfo.characterId : "";
  }

  // ── Picking up a stack of the SAME kind tops this one up (the grenade rule) ─────────────────────

  @Override
  protected boolean shouldAutoPickup(Node character) {
    if (!(character.getNodeOrNull(WEAPON_CONTROLLER_PATH) instanceof WeaponController wc)) return false;
    if (wc.isSlotFreeFor(resolveSlotType())) return true;
    WeaponItem existing = wc.findWeaponByIdAndType(weaponId, resolveSlotType());
    return existing instanceof SupplyItem si && si.magazine < si.magazineSize;
  }

  @Override
  protected void onCharacterEntered(Node character) {
    if (!(character.getNodeOrNull(WEAPON_CONTROLLER_PATH) instanceof WeaponController wc)) return;
    WeaponItem existing = wc.findWeaponByIdAndType(weaponId, resolveSlotType());
    if (existing instanceof SupplyItem si && si.magazine < si.magazineSize) {
      si.magazine += Math.min(si.magazineSize - si.magazine, magazine);
      wc.refreshActiveAmmoDisplay();
      equipped = true;
      queueFree();
      return;
    }
    equipped = true;
    wc.requestEquip(this);
  }

  // ── Use ────────────────────────────────────────────────────────────────────────────────────────

  @Override
  public void useWeapon() {
    isWeaponFired = true;
    if (!(owningCharacter instanceof Character user) || user.characterInfo == null) return;
    Character target = giveTarget();
    if (target == null) target = user;
    if (target.healthNode == null || !target.isAlive()) return;
    if (target == user && target.healthNode.getCurrentHealth() >= target.healthNode.maxHealth - 0.5f) {
      isWeaponFired = false;   // nothing to heal: keep it, and the press is not spent
      return;
    }
    decrementMagazine();
    com.openworld.net.NetworkManager net = NetRole.net(this);
    if (NetRole.client(this) && net != null) {
      String tid = target.characterInfo != null ? target.characterInfo.characterId : "";
      net.sendSupplyUse(user.characterInfo.characterId, tid, supplyId);
    } else {
      target.healthNode.heal(healAmount);
    }
    GD.print("SupplyItem: " + user.getName() + " used " + supplyId + " on " + target.getName());
  }

  /**
   * Whom this would be given to right now: with AIM held, the nearest other living character within {@link #giveReach}
   * of the user and within {@link #giveConeDeg} of the aim direction. Null = the user themself.
   */
  public Character giveTarget() {
    if (!(owningCharacter instanceof Character user) || weaponController == null) return null;
    if (!weaponController.scopeRequestedNow() || getTree() == null) return null;
    Vector3 from = user.getGlobalPosition();
    Vector3 aim = user.getAimTargetPosition().minus(from);
    aim = new Vector3(aim.getX(), 0f, aim.getZ());
    if (aim.lengthSquared() < 1e-4f) return null;
    aim = aim.normalized();
    Character best = null;
    double bestD = giveReach;
    for (Node n : getTree().getNodesInGroup(new StringName("characters"))) {
      if (!(n instanceof Character c) || c == user || !c.isAlive() || c.currentVehicleNode != null) continue;
      Vector3 d = c.getGlobalPosition().minus(from);
      Vector3 flat = new Vector3(d.getX(), 0f, d.getZ());
      double dist = flat.length();
      if (dist > bestD || dist < 1e-3 || Math.abs(d.getY()) > 1.5) continue;
      if (Math.toDegrees(aim.angleTo(flat)) > giveConeDeg) continue;
      best = c;
      bestD = dist;
    }
    return best;
  }

  /** The outline follows the target while this stack is in the LOCAL player's hands. */
  @Register
  @Override
  public void _process(double delta) {
    super._process(delta);
    Character want = null;
    if (equipped && owningCharacter instanceof Character user && user.isLocallyOwnedPlayer()
        && weaponController != null && weaponController.getCurrentWeaponItem() == this) {
      want = giveTarget();
    }
    if (want != outlined) setOutline(want);
  }

  @Register
  @Override
  public void _exitTree() {
    setOutline(null);   // also on a reparent (holstered / stowed): the outline is only for the stack in hand
  }

  private void setOutline(Character c) {
    for (GeometryInstance3D g : outlinedMeshes) if (GD.isInstanceValid(g)) g.setMaterialOverlay(null);
    outlinedMeshes.clear();
    outlined = c;
    if (c == null) return;
    if (!(GD.INSTANCE.load(OUTLINE) instanceof Material m)) return;
    collectMeshes(c, outlinedMeshes);
    for (GeometryInstance3D g : outlinedMeshes) g.setMaterialOverlay(m);
  }

  /** Every visible mesh of the body (the skinned meshes), never a held weapon or the nameplate. */
  private static void collectMeshes(Node n, List<GeometryInstance3D> out) {
    for (Node ch : n.getChildren(false)) {
      if (ch instanceof WeaponItem || "Nameplate".equals(ch.getName().toString())) continue;
      if (ch instanceof godot.api.MeshInstance3D mi && mi.isVisibleInTree()) out.add(mi);
      collectMeshes(ch, out);
    }
  }
}
