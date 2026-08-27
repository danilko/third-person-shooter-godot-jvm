package com.openworld.ui;

import com.openworld.character.Health;
import com.openworld.character.NameplateTarget;
import com.openworld.weapon.WeaponController;
import com.openworld.weapon.WeaponItem;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.*;
import godot.core.Callable;
import godot.core.MethodCallable;
import godot.core.NodePath;
import godot.core.StringNames;

/**
 * Generic floating nameplate rendered above any {@link NameplateTarget} — a character, a carrier,
 * or a future entity type. It carries no entity-specific logic: it binds to its parent purely
 * through {@link NameplateTarget} (name + effective colour + a change signal) plus two
 * conventionally-named sibling nodes it discovers itself ({@code Health}, {@code WeaponController}),
 * both of which {@code Character} and {@code Vehicle} already expose under those names. A carrier
 * therefore reuses this same scene/script and supplies its own rules (driver-derived colour, carrier
 * weapon) via its {@code NameplateTarget} implementation.
 *
 * All visual elements live inside a {@link SubViewport} rendered to a single billboard
 * {@link Sprite3D} quad (eliminates the depth-sort / parallax issues of separately-billboarded 3D
 * nodes). Scene composition (Nameplate.tscn — one SubViewport, two UI sub-scenes):
 *   SubViewport
 *     HealthUI         (CharacterHealthUI.tscn — name + health, top)
 *       DisplayNameLabel (Label, tinted by NameplateTarget.getNameplateColor())
 *       HBoxContainer/HealthBar (TextureProgressBar) + HealthPercent (Label)
 *     WeaponUI         (CharacterWeaponUI.tscn — active weapon + ammo, bottom strip)
 *       WeaponLabel    (Label)
 *   NameplateSprite    (Sprite3D, billboard=1)
 *
 * <b>Sync:</b> reflects replicated state with no extra net message by reacting to signals that
 * already fire on the puppet apply paths — {@code WeaponController.ammoChanged} (weapon/ammo) and
 * {@code NameplateTarget.getNameplateChangedSignal()} (name/colour/weapon: faction swap on a
 * character, driver enter/exit on a carrier). Visibility is decided by the owning entity
 * (e.g. {@code Character.activateCameraIfOwned} hides the locally-controlled body's own plate).
 */
@Script(className = "Nameplate")
public class Nameplate extends Node3D {

    /** Path from this node to the sibling Health node (default: parent's "Health" child). */
    @Export
    public NodePath healthNodePath = new NodePath("../Health");

    /** Path from this node to the sibling WeaponController (default: parent's "WeaponController"). */
    @Export
    public NodePath weaponControllerPath = new NodePath("../WeaponController");

    private Label       displayName;
    private TextureProgressBar healthBar;
    private Label       healthPercent;
    private Label       weaponLabel;

    private NameplateTarget  target;
    private WeaponController  weaponController;

    private float maxHealth = 100f;

    @Register
    @Override
    public void _ready() {
        displayName   = (Label)              getNodeOrNull("SubViewport/HealthUI/DisplayNameLabel");
        healthBar     = (TextureProgressBar) getNodeOrNull("SubViewport/HealthUI/HBoxContainer/HealthBar");
        healthPercent = (Label)              getNodeOrNull("SubViewport/HealthUI/HBoxContainer/HealthPercent");
        weaponLabel   = (Label)              getNodeOrNull("SubViewport/WeaponUI/WeaponLabel");

        // Entity-specific data via the NameplateTarget interface (any parent type).
        Node parent = getParent();
        if (parent instanceof NameplateTarget t) {
            target = t;
            if (displayName != null && !t.getNameplateText().isEmpty()) {
                displayName.setText(t.getNameplateText());
            }
            applyColor();
            t.getNameplateChangedSignal().connectUnsafe(
                    MethodCallable.createUnsafe(this, "onTargetChanged"),
                    godot.api.Object.ConnectFlags.DEFAULT);
        }

        // Health via the sibling Health node (healthChanged tracks replicated health on clients too).
        // Wired BEFORE the weapon block so a weapon-side hiccup can never leave the health bar
        // unconnected (the original bug: a NPE in refreshWeapon aborted _ready before this ran).
        Node healthNode = getNodeOrNull(healthNodePath);
        if (healthNode instanceof Health health) {
            maxHealth = health.maxHealth;
            updateBar(health.getCurrentHealth());
            health.healthChanged.connectUnsafe(
                    MethodCallable.createUnsafe(this, "onHealthChanged"),
                    godot.api.Object.ConnectFlags.DEFAULT);
            health.died.connectUnsafe(
                    MethodCallable.createUnsafe(this, "onDied"),
                    godot.api.Object.ConnectFlags.DEFAULT);
        }

        // Weapon/ammo via the sibling WeaponController (same node name on Character and Vehicle).
        Node wcNode = getNodeOrNull(weaponControllerPath);
        if (wcNode instanceof WeaponController wc) {
            weaponController = wc;
            wc.ammoChanged.connectUnsafe(
                    MethodCallable.createUnsafe(this, "onAmmoChanged"),
                    godot.api.Object.ConnectFlags.DEFAULT);
        }
        // The controller may not have built its slot array yet (its _ready can run after this one);
        // refreshWeapon handles the empty/not-ready case, and the equip's ammoChanged repaints it.
        refreshWeapon();
    }

    /** Health.healthChanged (fires on local damage/heal and replication). */
    @Register
    public void onHealthChanged(float currentHealth) {
        updateBar(currentHealth);
    }

    /** Health.died. */
    @Register
    public void onDied() {
        updateBar(0f);
    }

    /** WeaponController.ammoChanged (fires on fire/reload/pickup and replicated apply). */
    @Register
    public void onAmmoChanged(int magazine, int reserve) {
        refreshWeapon();
    }

    /** NameplateTarget refresh — name/colour/weapon changed (faction swap, weapon switch, driver enter/exit). */
    @Register
    public void onTargetChanged() {
        if (target != null && displayName != null) displayName.setText(target.getNameplateText());
        applyColor();
        refreshWeapon();
    }

    // ── Internal ──────────────────────────────────────────────────────────────

    private void applyColor() {
        if (displayName != null && target != null) {
            displayName.setModulate(target.getNameplateColor());
        }
    }

    /**
     * Lists every carried weapon (one slot per line) for cross-network debugging — the active slot is
     * marked with a leading ">". Iterates all slots via the WeaponController accessors rather than
     * showing only the active weapon, so a glance at any plate reveals the full inventory.
     */
    private void refreshWeapon() {
        if (weaponLabel == null) return;
        if (weaponController == null) { weaponLabel.setText("--"); return; }

        int active = weaponController.getWeapon();
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < weaponController.getSlotCount(); i++) {
            WeaponItem item = weaponController.getWeaponItem(i);
            if (item == null) continue;
            if (sb.length() > 0) sb.append('\n');
            sb.append(i == active ? "> " : "  ")
              .append(i).append(' ').append(item.getDisplayName())
              .append(' ').append(item.getMagazine()).append('/').append(item.getReserve());
        }
        weaponLabel.setText(sb.length() == 0 ? "--" : sb.toString());
    }

    private void updateBar(float current) {
        float ratio = maxHealth > 0f ? Math.max(0f, current / maxHealth) : 0f;
        int   pct   = Math.round(ratio * 100f);

        if (healthBar    != null) healthBar.setValue(pct);
        if (healthPercent != null) healthPercent.setText(pct + "%");
    }
}
