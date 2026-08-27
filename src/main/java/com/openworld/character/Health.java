package com.openworld.character;

import com.openworld.game.EventBus;
import com.openworld.net.NetworkManager;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;
import godot.api.PhysicalBone3D;
import godot.api.Texture2D;
import godot.core.Signal0;
import godot.core.Signal1;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;
import com.openworld.control.Controllable;

@Script(className = "Health")
public class Health extends Node {

    @Export
    public float maxHealth = 100.0f;

    /** Display name used in kill notifications. Falls back to the owner node name if empty. */
    @Export
    public String displayName = "";

    /**
     * Optional per-mesh bone multiplier table.  Set by Character._ready() from the
     * CharacterVisuals scene's embedded MeshConfig.  When non-null and non-empty,
     * overrides the built-in GodotChan bone-name table in getDamageMultiplier().
     */
    public MeshConfig meshConfig;

    private float currentHealth;

    /**
     * Discrete "took a hit" event carrying the damage amount. Fires ONLY on authority-side
     * {@code applyDamage} and is re-broadcast to non-authority peers as a reliable hit cue
     * ({@code NetworkManager.handleDamageBroadcastMessage}). Drives momentary reactions —
     * AI aggro, escort alerts, hit feedback — NOT health-bar display. Kept deliberately
     * separate from {@link #healthChanged}: re-deriving a discrete event from the
     * continuously-replicated health value would double-fire it on clients.
     */
    public final Signal1<Float> hit = new Signal1<>(this, new StringName("hit"));

    /**
     * Fires whenever {@code currentHealth} changes from ANY source — local damage/heal
     * AND replicated updates ({@link #applyReplicatedHealth}). This is THE signal for
     * health-value display (HUD bar, nameplate); listen here, never to {@link #hit},
     * for anything that shows current health — otherwise it won't track on non-authority
     * peers (where damage arrives via replication, not local {@code takeDamage}).
     */
    public final Signal1<Float> healthChanged = new Signal1<>(this, new StringName("health_changed"));

    public final Signal0 died = new Signal0(this, new StringName("died"));

    @Register
    @Override
    public void _ready() {
        currentHealth = maxHealth;
    }

    public void takeDamage(Node hitNode, float baseDamage, String weaponName) {
        takeDamage(hitNode, baseDamage, weaponName, null, "", "", null);
    }

    public void takeDamage(Node hitNode, float baseDamage, String weaponName,
                           Texture2D weaponIcon, String attackerName, String attackerFaction) {
        takeDamage(hitNode, baseDamage, weaponName, weaponIcon, attackerName, attackerFaction, null);
    }

    /**
     * @param attackerPos world position of the damage source (shooter / blast center), or null when
     *                    the damage has no meaningful direction (fall, etc.). Drives the HUD
     *                    damage-direction indicator via {@link EventBus#characterDamagedFrom}.
     */
    public void takeDamage(Node hitNode, float baseDamage, String weaponName,
                           Texture2D weaponIcon, String attackerName, String attackerFaction,
                           Vector3 attackerPos) {
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

        applyDamage(damage, headshot, weaponName, weaponIcon, attackerName, attackerFaction, attackerPos);
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
            String attackerName, String attackerFaction, Vector3 attackerPos) {
        if (currentHealth <= 0) return;
        applyDamage(finalDamage, headshot, weaponName, null, attackerName, attackerFaction, attackerPos);
    }

    private void applyDamage(float damage, boolean headshot, String weaponName, Texture2D weaponIcon,
                             String attackerName, String attackerFaction, Vector3 attackerPos) {
        currentHealth = Math.max(0.0f, currentHealth - damage);
        hit.emit(damage);
        emitCharacterHealthChanged();
        emitDamagedFrom(attackerPos);
        // Server is the single site that broadcasts the per-hit cue + attacker source to clients
        // (covers host-originated AND client-relayed damage; the relay path flows through here too).
        maybeBroadcastDamageCue(damage, attackerPos);
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

    /**
     * Server-only: re-broadcast the per-hit cue (and attacker source for the HUD direction indicator)
     * to clients. The victim may be a Character or a Vehicle — both are Controllable with CharacterInfo.
     * Non-networked / client peers no-op (clients receive the cue via handleDamageBroadcastMessage).
     */
    private void maybeBroadcastDamageCue(float damage, Vector3 attackerPos) {
        Node owner = getOwner();
        if (!(owner instanceof Controllable ctrl) || ctrl.getCharacterInfo() == null) return;
        String id = ctrl.getCharacterInfo().characterId;
        if (id == null || id.isEmpty()) return;
        Node netNode = getNodeOrNull("/root/NetworkManager");
        if (netNode instanceof NetworkManager net && net.isNetworked() && net.isServer()) {
            net.broadcastDamage(id, damage, attackerPos != null, attackerPos);
        }
    }

    /**
     * Emit EventBus.characterDamagedFrom for the HUD damage-direction indicator. No-op when the source
     * is unknown (null — fall/world damage carry no direction) or the owner has no CharacterInfo
     * (vehicles, scenery). HUDManager filters this to the local player.
     */
    private void emitDamagedFrom(Vector3 attackerPos) {
        if (attackerPos == null) return;
        Node owner = getOwner();
        if (!(owner instanceof Character c) || c.characterInfo == null) return;
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) bus.characterDamagedFrom.emit(c.characterInfo, attackerPos);
    }

    /** Relay current health to EventBus.characterHealthChanged for the owning character. */
    private void emitCharacterHealthChanged() {
        // Local signal first — fires on every health change (local or replicated) so the
        // sibling nameplate updates on non-authority peers too. Independent of the
        // EventBus/characterInfo eligibility below.
        healthChanged.emit(currentHealth);
        Node owner = getOwner();
        if (!(owner instanceof Character c) || c.characterInfo == null) return;
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) bus.characterHealthChanged.emit(c.characterInfo, currentHealth);
    }

    @Register
    public void heal(float amount) {
        currentHealth = Math.min(maxHealth, currentHealth + amount);
        emitCharacterHealthChanged();
    }

    /**
     * Restore to full and clear the dead state. Used when a pooled body is recycled into a new
     * spawn (PLAN.md Part E / E1 SpawnPool) — a recycled AICharacter's {@code _ready()} does not
     * run again, so health must be reset explicitly. Emits healthChanged so the nameplate/HUD
     * re-read the restored value.
     */
    public void resetFull() {
        currentHealth = maxHealth;
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
