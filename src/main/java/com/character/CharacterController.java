package com.character;

import com.character.ai.AIState;
import com.character.ai.PatrolState;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;

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
