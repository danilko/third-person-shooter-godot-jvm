package com.character.ai;

import com.character.AICharacter;
import com.character.CharacterInput;

/**
 * One state in an AI character's finite state machine.
 *
 * States are stateless singletons; all mutable data lives on {@link AICharacter}.
 * Returning a different {@code AIState} from {@link #update} triggers a transition.
 */
public interface AIState {

    /** Called once on state entry. Reset per-state timers on the character here. */
    void enter(AICharacter c);

    /** Called once on state exit. */
    void exit(AICharacter c);

    /**
     * Produce a CharacterInput for this tick.
     * Return {@code this} to stay in the current state, or another instance to transition.
     */
    AIState update(AICharacter c, CharacterInput input, double delta);
}
