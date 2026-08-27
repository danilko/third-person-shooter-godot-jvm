package com.openworld.game;

import com.openworld.character.Player;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;

import java.util.ArrayList;
import java.util.List;

/**
 * Process-global registry of every live {@link Player} body — registered as an AutoLoad
 * singleton named "PlayerRegistry".
 *
 * <p>Exists purely as a performance shortcut (PLAN.md Part D, "pre-D1 quick win"). AI LOD
 * (`AICharacter.nearestPlayerDist()`) needs the distance to the closest player every couple of
 * seconds; previously that meant `getTree().getNodesInGroup("characters")` + an `instanceof Player`
 * filter — an O(characterCount) scan run by every AI. With a few players among hundreds of AIs
 * that is wasted work. This registry collapses it to O(playerCount): players add/remove themselves
 * as they enter/leave the tree.
 *
 * <p>The list is a JVM-static so callers reach it without a node lookup; that means it outlives the
 * engine, so {@link #_exitTree()} clears it on shutdown (same leak discipline as
 * {@code IconRegistry.clear()} — see CLAUDE.md "Known Quirks"). Entries are added in
 * {@code Player._ready()} and removed in {@code Player._exitTree()}, so the list only ever holds
 * in-tree bodies; a defensive {@code isInstanceValid} guard at the read site covers any gap.
 */
@Script(className = "PlayerRegistry")
public class PlayerRegistry extends Node {

    private static final List<Player> PLAYERS = new ArrayList<>();

    /** Add a player body to the registry (idempotent). Called from {@code Player._ready()}. */
    public static void register(Player player) {
        if (player != null && !PLAYERS.contains(player)) PLAYERS.add(player);
    }

    /** Remove a player body from the registry. Called from {@code Player._exitTree()}. */
    public static void deregister(Player player) {
        PLAYERS.remove(player);
    }

    /** The live player bodies. Returns the backing list directly — callers must not mutate it. */
    public static List<Player> getPlayers() {
        return PLAYERS;
    }

    /** Drop all references on engine teardown so no {@code Player} (a Godot Object) leaks past exit. */
    @Register
    @Override
    public void _exitTree() {
        PLAYERS.clear();
    }
}
