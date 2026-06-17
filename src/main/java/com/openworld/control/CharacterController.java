package com.openworld.control;

import com.openworld.ai.AIState;
import com.openworld.ai.character.PatrolState;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import com.openworld.ai.AIController;
import com.openworld.character.AICharacter;
import com.openworld.net.NetworkController;

/**
 * Concrete AI controller for on-foot AICharacter bodies.
 *
 * Caches the AICharacter owner and starts the FSM from PatrolState.
 * Equivalent to L4D's SurvivorBot — can be swapped for PlayerController
 * (bot-fill / possession) or NetworkController without touching the body.
 */
@RegisterClass(className = "CharacterController")
public class CharacterController extends AIController {

    private AICharacter body;

    @RegisterFunction
    @Override
    public void _ready() {
        body = (AICharacter) getOwner();
        super._ready();
    }

    @Override
    protected AICharacter getBody() { return body; }

    @Override
    protected AIState initialState() { return PatrolState.INSTANCE; }
}
