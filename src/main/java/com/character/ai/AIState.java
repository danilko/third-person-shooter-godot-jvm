package com.character.ai;

import com.character.AICharacter;
import com.character.AIController;
import com.character.UserCommand;

/**
 * One state in an AI controller's finite state machine.
 *
 * States are stateless singletons. All mutable data lives on the AIController
 * (timers, memory) or AICharacter (body capabilities). Returning a different
 * AIState from update() triggers a transition.
 *
 * The explicit (body, ctrl) split makes each state's data sources unambiguous:
 *   body — hardware / sensing  (NavAgent, SightRay, weapon selection)
 *   ctrl — memory / state      (timers, last-known positions, aim targets)
 */
public interface AIState {

    /** Called once on entry. Reset per-state timer fields on ctrl here. */
    void enter(AICharacter body, AIController ctrl);

    /** Called once on exit. */
    void exit(AICharacter body, AIController ctrl);

    /**
     * Produce a UserCommand for this tick.
     * Return {@code this} to stay in the current state, or another instance to transition.
     */
    AIState update(AICharacter body, AIController ctrl, UserCommand cmd, double delta);
}
