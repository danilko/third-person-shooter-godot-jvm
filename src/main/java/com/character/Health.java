package com.character;

import com.game.EventBus;
import com.game.NetworkManager;
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
import godot.global.GD;

@RegisterClass(className = "Health")
public class Health extends Node {

    @Export
    @RegisterProperty
    public float maxHealth = 100.0f;

    /** Display name used in kill notifications. Falls back to the owner node name if empty. */
    @Export
    @RegisterProperty
    public String displayName = "";

    /**
     * Optional per-mesh bone multiplier table.  Set by Character._ready() from the
     * CharacterVisuals scene's embedded MeshConfig.  When non-null and non-empty,
     * overrides the built-in GodotChan bone-name table in getDamageMultiplier().
     */
    public MeshConfig meshConfig;

    private float currentHealth;

    @RegisterSignal
    public final Signal1<Float> damaged = new Signal1<>(this, new StringName("damaged"));

    @RegisterSignal
    public final Signal0 died = new Signal0(this, new StringName("died"));

    @RegisterFunction
    @Override
    public void _ready() {
        currentHealth = maxHealth;
    }

    public void takeDamage(Node hitNode, float baseDamage, String weaponName) {
        takeDamage(hitNode, baseDamage, weaponName, null, "", "");
    }

    public void takeDamage(Node hitNode, float baseDamage, String weaponName,
                           Texture2D weaponIcon, String attackerName, String attackerFaction) {
        if (currentHealth <= 0) return;

        boolean headshot = (hitNode instanceof PhysicalBone3D)
                && "Physical Bone head_2".equals(hitNode.getName().toString());
        float damage = baseDamage * getDamageMultiplier(hitNode);

        // Authority guard: only the victim's authoritative peer may mutate health.
        // Everyone else relays the already-resolved damage/headshot — PhysicalBone3D
        // (hitNode) isn't wire-safe, so the multiplier/headshot lookup happens here,
        // where hitNode is still available, and only the *result* crosses the network.
        // Entity-generic guard (Round 11 N3): Characters AND Vehicles relay — the old
        // `instanceof Character` filter let a client apply vehicle damage locally,
        // silently diverging from the host (client-side vehicle kills never crossed
        // the wire).
        Node owner = getOwner();
        if (owner instanceof Controllable c && c.getCharacterInfo() != null) {
            Node netNode = getNodeOrNull("/root/NetworkManager");
            if (netNode instanceof NetworkManager net && net.isNetworked()
                    && !net.isServer()) {
                relayDamageToAuthority(c, damage, headshot, weaponName, attackerName, attackerFaction);
                return;
            }
        }

        applyDamage(damage, headshot, weaponName, weaponIcon, attackerName, attackerFaction);
    }

    private void relayDamageToAuthority(Controllable c, float finalDamage, boolean headshot,
            String weaponName, String attackerName, String attackerFaction) {
        Node netNode = getNodeOrNull("/root/NetworkManager");
        if (!(netNode instanceof NetworkManager net) || !net.isNetworked()) return;
        net.requestDamage(c.getCharacterInfo().characterId, finalDamage, headshot, weaponName, attackerName, attackerFaction);
    }

    /**
     * Authoritative-side entry point for NetworkManager.requestDamage — the
     * relaying peer already resolved the bone multiplier/headshot (it had the
     * real hitNode), so this applies the final number directly with no weaponIcon
     * (HUD-local concern; never crosses the wire).
     */
    public void applyNetworkDamage(float finalDamage, boolean headshot, String weaponName,
            String attackerName, String attackerFaction) {
        if (currentHealth <= 0) return;
        applyDamage(finalDamage, headshot, weaponName, null, attackerName, attackerFaction);
    }

    private void applyDamage(float damage, boolean headshot, String weaponName, Texture2D weaponIcon,
                             String attackerName, String attackerFaction) {
        currentHealth = Math.max(0.0f, currentHealth - damage);
        damaged.emit(damage);
        emitCharacterHealthChanged();
        if (currentHealth <= 0) {
            Node busNode = getNodeOrNull("/root/EventBus");
            if (busNode instanceof EventBus bus) {
                Node owner = getOwner();
                String victimName;
                String victimFaction;
                CharacterInfo victimInfo = (owner instanceof Character c) ? c.characterInfo : null;
                if (victimInfo != null) {
                    victimName    = victimInfo.displayName;
                    victimFaction = victimInfo.faction;
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
                if (victimInfo != null) bus.characterDied.emit(victimInfo);
                // Round 11 N2: death is a reliable, ordered network event — not just a
                // health==0 snapshot. Clients use it for the kill feed / mission progress /
                // forced puppet death / their own death sequence. Broadcast BEFORE died.emit()
                // so it precedes the death-drop MSG_WEAPON_DROPPED events on channel 0.
                if (victimInfo != null && !victimInfo.characterId.isEmpty()) {
                    Node netNode = getNodeOrNull("/root/NetworkManager");
                    if (netNode instanceof NetworkManager net && net.isNetworked() && net.isServer()) {
                        net.broadcastElimination(victimInfo.characterId, victimName, victimFaction,
                                attackerName, attackerFaction, weaponName, headshot);
                    }
                }
            }
            died.emit();
        }
    }

    /** Relay current health to EventBus.characterHealthChanged for the owning character. */
    private void emitCharacterHealthChanged() {
        Node owner = getOwner();
        if (!(owner instanceof Character c) || c.characterInfo == null) return;
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) bus.characterHealthChanged.emit(c.characterInfo, currentHealth);
    }

    @RegisterFunction
    public void heal(float amount) {
        currentHealth = Math.min(maxHealth, currentHealth + amount);
        emitCharacterHealthChanged();
    }

    /**
     * Applies the authoritative health value carried by MSG_SNAPSHOT on non-authority
     * peers — direct replacement for the old syncHealth mirror, except this writes the
     * field every HUD/nameplate reader actually reads (getCurrentHealth/currentHealth),
     * closing a latent gap where syncHealth was replicated but never displayed.
     *
     * Deliberately does not emit damaged/died/characterEliminated — those are discrete
     * authority-side events (Phase 5's broadcastDamage cue path); re-deriving them from
     * a continuously-replicated number would double-fire them once that lands.
     */
    public void applyReplicatedHealth(float health) {
        float clamped = Math.max(0.0f, Math.min(maxHealth, health));
        if (clamped == currentHealth) return;
        currentHealth = clamped;
        emitCharacterHealthChanged();
    }

    public float getCurrentHealth() {
        return currentHealth;
    }

    public boolean isDead() {
        return currentHealth <= 0;
    }

    // ── Damage zone multipliers ───────────────────────────────────────────────
    // Node names come from the scene: "Physical Bone <bone_name>"
    private float getDamageMultiplier(Node hitNode) {
        if (!(hitNode instanceof PhysicalBone3D)) return 1.0f;
        String nodeName = hitNode.getName().toString();
        // MeshConfig table takes priority — allows per-skin customisation.
        if (meshConfig != null && !meshConfig.boneHitMultipliers.isEmpty()) {
            Object mult = meshConfig.boneHitMultipliers.get(nodeName);
            return mult instanceof Float f ? f : 1.0f;
        }
        return getBuiltInMultiplier(nodeName);
    }

    private static float getBuiltInMultiplier(String nodeName) {
        switch (nodeName) {
            // Head — head_2 PhysicalBone3D covers both neck capsule and head sphere
            case "Physical Bone head_2":
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
