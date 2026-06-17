package com.openworld.character;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.*;
import godot.core.Callable;
import godot.core.NodePath;
import godot.core.StringNames;

/**
 * Floating nameplate rendered above every character.
 *
 * All visual elements (display name, health bar, percentage) live inside a
 * {@link SubViewport} that renders them to a single 2D texture.  A single
 * {@link Sprite3D} displays that texture as a billboard quad.
 *
 * Rendering everything on one quad eliminates the depth-sort / parallax
 * issues that occur when separate 3D nodes (Label3D, MeshInstance3D) are
 * individually billboarded and angle-sorted against each other.
 *
 * Scene children (CharacterNameplate.tscn):
 *   HealthUI           (SubViewport, 200×60 px, transparent)
 *     VBoxContainer
 *       DisplayNameLabel (Label, centered)
 *       HealthBar        (ProgressBar, 0-100)
 *       HealthPercent    (Label, centered)
 *   NameplateSprite    (Sprite3D, billboard=1, pixel_size=0.004)
 */
@RegisterClass(className = "CharacterNameplate")
public class CharacterNameplate extends Node3D {

    /** Path from this node to the sibling Health node. */
    @RegisterProperty
    @Export
    public NodePath healthNodePath = new NodePath("../Health");

    private Label       displayName;
    private TextureProgressBar healthBar;
    private Label       healthPercent;

    private float maxHealth = 100f;

    @RegisterFunction
    @Override
    public void _ready() {
        displayName   = (Label)       getNodeOrNull("SubViewport/HealthUI/DisplayNameLabel");
        healthBar     = (TextureProgressBar) getNodeOrNull("SubViewport/HealthUI/HBoxContainer/HealthBar");
        healthPercent = (Label)       getNodeOrNull("SubViewport/HealthUI/HBoxContainer/HealthPercent");

        // ViewportTexture → Sprite3D is wired in the .tscn via:
        //   sub_resource ViewportTexture { resource_local_to_scene=true, viewport_path="HealthUI" }
        // resource_local_to_scene causACT es Godot to clone the resource per instance,
        // setting each clone's local_scene to its own CharacterNameplate so
        // get_node("HealthUI") resolves to the correct sibling SubViewport.

        // Populate display name and faction colour from parent Character's CharacterInfo
        Node parent = getParent();
        if (parent instanceof Character c && c.characterInfo != null
                && !c.characterInfo.displayName.isEmpty()) {
            if (displayName != null) {
                displayName.setText(c.characterInfo.displayName);
                displayName.setModulate(Faction.color(c.characterInfo.faction));
            }
        }

        // Connect to Health sibling
        Node healthNode = getNodeOrNull(healthNodePath);
        if (healthNode instanceof Health health) {
            maxHealth = health.maxHealth;
            updateBar(health.getCurrentHealth());
            // healthChanged (not damaged) so the bar tracks replicated health on clients too.
            health.healthChanged.connectUnsafe(
                    Callable.createUnsafe(this, StringNames.toGodotName("onHealthChanged")),
                    godot.api.Object.ConnectFlags.DEFAULT);
            health.died.connectUnsafe(
                    Callable.createUnsafe(this, StringNames.toGodotName("onDied")),
                    godot.api.Object.ConnectFlags.DEFAULT);
        }
    }

    /** Connected to Health.healthChanged signal (fires on local damage/heal and replication). */
    @RegisterFunction
    public void onHealthChanged(float currentHealth) {
        updateBar(currentHealth);
    }

    /** Connected to Health.died signal. */
    @RegisterFunction
    public void onDied() {
        updateBar(0f);
    }

    // ── Internal ──────────────────────────────────────────────────────────────

    private void updateBar(float current) {
        float ratio = maxHealth > 0f ? Math.max(0f, current / maxHealth) : 0f;
        int   pct   = Math.round(ratio * 100f);

        if (healthBar    != null) healthBar.setValue(pct);
        if (healthPercent != null) healthPercent.setText(pct + "%");
    }
}
