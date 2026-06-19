package com.openworld.world;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterProperty;
import godot.api.PackedScene;
import godot.api.Resource;
import godot.core.Vector3;
import com.openworld.ai.AIBehaviorConfig;
import com.openworld.character.Faction;

/**
 * A named story AI placed in a {@link WorldZone} (PLAN.md Part E / E1).
 *
 * <p>Unlike {@link SpawnConfig}'s anonymous ambient AI, a named character always spawns with a
 * <b>stable {@link #characterId}</b> so later mission code (Part F's MissionDirector) can address
 * it by id across loads/unloads. It is never recycled through the {@code SpawnPool}: it is
 * instantiated fresh on zone load and freed on unload, re-spawning at the same id next time.
 */
@RegisterClass(className = "NamedCharacterConfig")
public class NamedCharacterConfig extends Resource {

    /** Stable id (NOT a random UUID) — mission code addresses this character by it. */
    @Export @RegisterProperty public String characterId = "";

    @Export @RegisterProperty public String displayName = "Named";

    @Export @RegisterProperty public String faction = Faction.ENEMY;

    /** Scene to instance. Null → the shared AICharacter.tscn archetype. */
    @Export @RegisterProperty public PackedScene scene;

    /** Per-AI behaviour profile. Null → AICharacter's shared DEFAULTS apply. */
    @Export @RegisterProperty public AIBehaviorConfig behaviorConfig;

    /** Weapon scene equipped on spawn. */
    @Export @RegisterProperty public String weaponScenePath =
            "res://src/main/resources/com/openworld/weapon/AR4.tscn";

    /** Spawn offset relative to the zone marker's world position. */
    @Export @RegisterProperty public Vector3 offset = new Vector3();

    public NamedCharacterConfig() { super(); }
}
