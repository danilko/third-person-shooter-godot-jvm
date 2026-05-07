package com.character;

import com.environment.Pickup;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterProperty;
import godot.api.AudioStreamWAV;
import godot.api.Node;
import godot.api.Texture2D;
import godot.core.Vector3;

import static godot.global.GD.min;

@RegisterClass(className = "WeaponItem")
public class WeaponItem extends Pickup implements WeaponAction {

  // Internal identifier: used for marker lookup ("Marker" + weaponId), event bus payloads,
  // save keys. No spaces. If empty, falls back to weaponName for marker lookup.
  @RegisterProperty @Export public String weaponId = "";

  // Human-readable display name: HUD, kill feed, inventory, interact prompt.
  @RegisterProperty @Export public String weaponName = "";

  // WeaponSlotType ordinal: 0=PRIMARY 1=SECONDARY 2=MELEE 3=THROWABLE 4=OFFHAND
  @RegisterProperty @Export public int slotType = 0;

  // Index into the AnimationTree weapon blend nodes (WeaponAim, WeaponHold, WeaponChangeAnimation).
  // Decoupled from slot so the same animation pose is used regardless of which slot holds the weapon.
  @RegisterProperty @Export public int weaponPoseIndex = 0;

  // Icon shown in the kill feed and radial menu. Set in the inspector per weapon scene.
  @RegisterProperty @Export public Texture2D weaponIcon = null;

  @RegisterProperty @Export public float spread = 1.0f;
  @RegisterProperty @Export public float bloomPerShot = 0.4f;
  @RegisterProperty @Export public float bloomDecaySpeed = 3.0f;
  @RegisterProperty @Export public float bloomMax = 4.0f;
  @RegisterProperty @Export public float reloadSpeed = 0.8f;
  @RegisterProperty @Export public float switchSpeed = 1.2f;
  @RegisterProperty @Export public float fireRate = 8.0f;
  @RegisterProperty @Export public boolean auto = true;
  @RegisterProperty @Export public int magazine = 40;
  @RegisterProperty @Export public int magazineSize = 40;
  @RegisterProperty @Export public int reserve = 40;
  @RegisterProperty @Export public int reserveMax = 40;
  @RegisterProperty @Export public float recoil = 0.8f;
  @RegisterProperty @Export public float damage = 25.0f;
  @RegisterProperty @Export public AudioStreamWAV fireAudio;
  @RegisterProperty @Export public AudioStreamWAV reloadAudio;

  public WeaponSlotType getSlotType() {
    WeaponSlotType[] types = WeaponSlotType.values();
    if (slotType >= 0 && slotType < types.length) return types[slotType];
    return WeaponSlotType.PRIMARY;
  }

  /** Returns weaponName if set, otherwise the node name. Use everywhere a display name is needed. */
  public String getDisplayName() {
    return weaponName.isEmpty() ? getName().toString() : weaponName;
  }

  // ── Pickup callbacks ──────────────────────────────────────────────────────

  /**
   * Auto-pickup when the character's matching slot is free; otherwise show the
   * interact prompt so the player consciously chooses to swap their current weapon.
   */
  @Override
  protected boolean shouldAutoPickup(Node character) {
    Node wcNode = character.getNodeOrNull(WEAPON_CONTROLLER_PATH);
    if (wcNode instanceof WeaponController wc) return wc.isSlotFreeFor(getSlotType());
    return false;
  }

  @Override
  protected void onCharacterEntered(Node character) {
    Node wcNode = character.getNodeOrNull(WEAPON_CONTROLLER_PATH);
    if (wcNode instanceof WeaponController wc) {
      wc.equipWeapon(this);
    }
  }

  @Override
  protected String getInteractLabel() {
    return getDisplayName();
  }

  // ── WeaponAction defaults — concrete subclasses override what they need ───
  @Override public void useWeapon() {}
  @Override public void stopUseWeapon() {}
  @Override public void onReloadComplete() {}
  @Override public boolean canUse() { return false; }
  @Override public WeaponType getWeaponType() { return WeaponType.RANGED; }
  @Override public float getCurrentSpreadDeg() { return 0f; }
  @Override public void onSetStance(Stance stance) {}

  public void decrementMagazine() {
    if (magazine > 0) magazine--;
  }

  public void fillMagazine() {
    int emptySpace = magazineSize - magazine;
    magazine += min(emptySpace, reserve);
    reserve -= min(emptySpace, reserve);
  }

  public void fillAmmo() {
    reserve = reserveMax;
    magazine = magazineSize;
  }

  public float getSpread() { return spread; }
  public void setSpread(float spread) { this.spread = spread; }

  public float getBloomPerShot() { return bloomPerShot; }
  public void setBloomPerShot(float bloomPerShot) { this.bloomPerShot = bloomPerShot; }

  public float getBloomDecaySpeed() { return bloomDecaySpeed; }
  public void setBloomDecaySpeed(float bloomDecaySpeed) { this.bloomDecaySpeed = bloomDecaySpeed; }

  public float getBloomMax() { return bloomMax; }
  public void setBloomMax(float bloomMax) { this.bloomMax = bloomMax; }

  public float getReloadSpeed() { return reloadSpeed; }
  public void setReloadSpeed(float reloadSpeed) { this.reloadSpeed = reloadSpeed; }

  public float getSwitchSpeed() { return switchSpeed; }
  public void setSwitchSpeed(float switchSpeed) { this.switchSpeed = switchSpeed; }

  public float getFireRate() { return fireRate; }
  public void setFireRate(float fireRate) { this.fireRate = fireRate; }

  public boolean isAuto() { return auto; }
  public void setAuto(boolean auto) { this.auto = auto; }

  public int getMagazine() { return magazine; }
  public void setMagazine(int magazine) { this.magazine = magazine; }

  public int getMagazineSize() { return magazineSize; }
  public void setMagazineSize(int magazineSize) { this.magazineSize = magazineSize; }

  public int getReserve() { return reserve; }
  public void setReserve(int reserve) { this.reserve = reserve; }

  public int getReserveMax() { return reserveMax; }
  public void setReserveMax(int reserveMax) { this.reserveMax = reserveMax; }

  public float getRecoil() { return recoil; }
  public void setRecoil(float recoil) { this.recoil = recoil; }

  public AudioStreamWAV getFireAudio() { return fireAudio; }
  public void setFireAudio(AudioStreamWAV fireAudio) { this.fireAudio = fireAudio; }

  public AudioStreamWAV getReloadAudio() { return reloadAudio; }
  public void setReloadAudio(AudioStreamWAV reloadAudio) { this.reloadAudio = reloadAudio; }
}
