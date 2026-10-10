package com.openworld.control;

import com.openworld.character.Character;

/**
 * Something a body can USE with the interact key (PLAN.md AR4, input half, 2026-10-09): a door, a shop counter, an
 * ammo supply, a pickup. It never reads the key itself -- it offers itself by showing its prompt
 * ({@code EventBus.interactPrompt}), and {@link Interactions} calls {@link #interact} on the ONE offer the HUD shows
 * when the body's {@code UserCommand.interact} fires. So E next to a door and a pickup does one thing, the thing the
 * prompt names.
 */
public interface Interactable {
    void interact(Character actor);
}
