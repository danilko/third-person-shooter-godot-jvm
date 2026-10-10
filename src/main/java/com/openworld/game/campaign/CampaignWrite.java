package com.openworld.game.campaign;

/** What an {@link Effect} may change: the player's story, and the world they are in. */
public interface CampaignWrite extends CampaignView {

    /** {@code value} "" clears it. Routed by the key's scope. */
    void setFlag(FlagKey key, String value);

    void achieve(String activity, String variant);

    /** An ending is a state transition (phase = POST_ENDING), never termination. */
    void ending(String ending);

    void chapter(String chapter);

    void markStoryDead(String storyId);

    void setPlace(String placeId, String owner, String state);

    void unlockSticky(String activity);
}
