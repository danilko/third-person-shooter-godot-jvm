package com.openworld.weapon;

import godot.annotation.Export;
import godot.annotation.Script;
import godot.api.Resource;

/**
 * A weapon's TUNING, as a read-only shared Resource (PLAN.md 2.8 item 1). Weapon scenes used to carry their
 * numbers inline on the same node that holds live state (magazine, bloom), so balancing meant opening ten
 * scenes and a probe could not tell a tuned value from a runtime one. Every weapon now references
 * {@code weapon/stats/<id>.tres}; {@link WeaponItem#setStats} copies it onto the item's fields when assigned,
 * and the fields stay registered ({@code @Visible}) so a probe or a debug tool can still adjust one live.
 * Read-only shared config is safe under godot-jvm (the {@code VehicleConfig} precedent) — nothing writes it.
 *
 * <p>Defaults equal {@link WeaponItem}'s and {@link FirearmItem}'s field initialisers, and each .tres states
 * every value explicitly, so a stats file is the whole table for its weapon. The firearm-only rows
 * (pellets, hipfire, standing threshold) are ignored by a weapon that is not a firearm.
 */
@Script(className = "WeaponStats")
public class WeaponStats extends Resource {

    @Export public float spread = 0.0f;
    public float getSpread() { return spread; }
    public void setSpread(float v) { spread = v; }

    @Export public float bloomPerShot = 0.0f;
    public float getBloomPerShot() { return bloomPerShot; }
    public void setBloomPerShot(float v) { bloomPerShot = v; }

    @Export public float bloomDecaySpeed = 1.0f;
    public float getBloomDecaySpeed() { return bloomDecaySpeed; }
    public void setBloomDecaySpeed(float v) { bloomDecaySpeed = v; }

    @Export public float bloomMax = 0.25f;
    public float getBloomMax() { return bloomMax; }
    public void setBloomMax(float v) { bloomMax = v; }

    @Export public float reloadSpeed = 0.8f;
    public float getReloadSpeed() { return reloadSpeed; }
    public void setReloadSpeed(float v) { reloadSpeed = v; }

    @Export public float switchSpeed = 2.2f;
    public float getSwitchSpeed() { return switchSpeed; }
    public void setSwitchSpeed(float v) { switchSpeed = v; }

    @Export public float fireRate = 8.0f;
    public float getFireRate() { return fireRate; }
    public void setFireRate(float v) { fireRate = v; }

    @Export public boolean auto = true;
    public boolean isAuto() { return auto; }
    public void setAuto(boolean v) { auto = v; }

    @Export public int magazineSize = 40;
    public int getMagazineSize() { return magazineSize; }
    public void setMagazineSize(int v) { magazineSize = v; }

    @Export public int reserveMax = 40;
    public int getReserveMax() { return reserveMax; }
    public void setReserveMax(int v) { reserveMax = v; }

    @Export public float recoil = 0.8f;
    public float getRecoil() { return recoil; }
    public void setRecoil(float v) { recoil = v; }

    @Export public float damage = 25.0f;
    public float getDamage() { return damage; }
    public void setDamage(float v) { damage = v; }

    @Export public float kickBack = 0.0f;
    public float getKickBack() { return kickBack; }
    public void setKickBack(float v) { kickBack = v; }

    @Export public float kickPitch = 0.0f;
    public float getKickPitch() { return kickPitch; }
    public void setKickPitch(float v) { kickPitch = v; }

    @Export public float kickSpring = 22.0f;
    public float getKickSpring() { return kickSpring; }
    public void setKickSpring(float v) { kickSpring = v; }

    @Export public float kickDamping = 1.0f;
    public float getKickDamping() { return kickDamping; }
    public void setKickDamping(float v) { kickDamping = v; }

    @Export public float weaponRange = 50.0f;
    public float getWeaponRange() { return weaponRange; }
    public void setWeaponRange(float v) { weaponRange = v; }

    @Export public int pelletCount = 1;
    public int getPelletCount() { return pelletCount; }
    public void setPelletCount(int v) { pelletCount = v; }

    @Export public float hipfireSpreadMultiplier = 1.0f;
    public float getHipfireSpreadMultiplier() { return hipfireSpreadMultiplier; }
    public void setHipfireSpreadMultiplier(float v) { hipfireSpreadMultiplier = v; }

    @Export public float standingSpeedFraction = 0.34f;
    public float getStandingSpeedFraction() { return standingSpeedFraction; }
    public void setStandingSpeedFraction(float v) { standingSpeedFraction = v; }
}
