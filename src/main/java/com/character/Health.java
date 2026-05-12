package com.character;

import com.game.EventBus;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.annotation.RegisterSignal;
import godot.api.Node;
import godot.api.PhysicalBone3D;
import godot.api.Texture2D;
import godot.core.Signal0;
import godot.core.Signal1;
import godot.core.StringName;

@RegisterClass(className = "Health")
public class Health extends Node {

    @Export
    @RegisterProperty
    public float maxHealth = 100.0f;

    /** Display name used in kill notifications. Falls back to the owner node name if empty. */
    @Export
    @RegisterProperty
    public String displayName = "";

    /** Network-synced mirror of currentHealth — read by MultiplayerSynchronizer on remote peers. */
    @Export
    @RegisterProperty
    public float syncHealth = 100.0f;

    private float currentHealth;

    @RegisterSignal
    public final Signal1<Float> damaged = new Signal1<>(this, new StringName("damaged"));

    @RegisterSignal
    public final Signal0 died = new Signal0(this, new StringName("died"));

    @RegisterFunction
    @Override
    public void _ready() {
        currentHealth = maxHealth;
        syncHealth = maxHealth;
    }

    public void takeDamage(Node hitNode, float baseDamage, String weaponName) {
        takeDamage(hitNode, baseDamage, weaponName, null, "", "");
    }

    public void takeDamage(Node hitNode, float baseDamage, String weaponName,
                           Texture2D weaponIcon, String attackerName, String attackerFaction) {
        if (currentHealth <= 0) return;
        boolean headshot = (hitNode instanceof PhysicalBone3D)
                && "Physical Bone neck_01".equals(hitNode.getName().toString());
        float damage = baseDamage * getDamageMultiplier(hitNode);
        currentHealth = Math.max(0.0f, currentHealth - damage);
        syncHealth = currentHealth;
        damaged.emit(damage);
        if (currentHealth <= 0) {
            Node busNode = getNodeOrNull("/root/EventBus");
            if (busNode instanceof EventBus bus) {
                Node owner = getOwner();
                String victimName;
                String victimFaction;
                if (owner instanceof Character c && c.characterInfo != null) {
                    victimName    = c.characterInfo.displayName;
                    victimFaction = c.characterInfo.faction;
                } else if (!displayName.isEmpty()) {
                    victimName    = displayName;
                    victimFaction = "";
                } else {
                    victimName    = owner != null ? owner.getName().toString() : "Unknown";
                    victimFaction = "";
                }
                bus.characterEliminated.emit(
                        attackerName, attackerFaction, victimName, victimFaction,
                        weaponName, weaponIcon, headshot);
            }
            died.emit();
        }
    }

    @RegisterFunction
    public void heal(float amount) {
        currentHealth = Math.min(maxHealth, currentHealth + amount);
        syncHealth = currentHealth;
    }

    public float getCurrentHealth() {
        return currentHealth;
    }

    public boolean isDead() {
        return currentHealth <= 0;
    }

    // ── Damage zone multipliers ───────────────────────────────────────────────
    // Node names come from the scene: "Physical Bone <bone_name>"
    private static float getDamageMultiplier(Node hitNode) {
        if (!(hitNode instanceof PhysicalBone3D)) return 1.0f;
        String nodeName = hitNode.getName().toString();
        switch (nodeName) {
            // Head — neck_01 PhysicalBone3D covers both neck capsule and head sphere
            case "Physical Bone neck_01":
                return 4.0f;
            // Upper body
            case "Physical Bone spine_03":
            case "Physical Bone clavicle_l":
            case "Physical Bone clavicle_r":
                return 1.0f;
            // Mid / lower torso
            case "Physical Bone spine_02":
            case "Physical Bone spine_01":
            case "Physical Bone pelvis":
                return 0.75f;
            // Arms
            case "Physical Bone upperarm_l": case "Physical Bone upperarm_r":
            case "Physical Bone lowerarm_l": case "Physical Bone lowerarm_r":
            case "Physical Bone hand_l":     case "Physical Bone hand_r":
                return 0.75f;
            // Legs
            case "Physical Bone thigh_l": case "Physical Bone thigh_r":
            case "Physical Bone calf_l":  case "Physical Bone calf_r":
            case "Physical Bone foot_l":  case "Physical Bone foot_r":
                return 0.5f;
            default:
                return 1.0f;
        }
    }
}
