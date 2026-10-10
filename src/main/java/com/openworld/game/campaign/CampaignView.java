package com.openworld.game.campaign;

/**
 * What a {@link Requirement} may ask (PLAN.md 2.1 / CR1): ONE player's story together with the world they are in --
 * "the owner must meet the requirement against their own profile + the host's world". Implemented over a real
 * profile and ledger ({@link LiveCampaign}) and over a simulated state ({@link SimCampaign}: the lint, the tests).
 */
public interface CampaignView {

    /** A flag's value, "" when it is not set. A WORLD flag is read from the world, a PERSONAL one from the story. */
    String flag(FlagKey key);

    /** Has this player completed {@code activity} with {@code variant} ("" = with any variant)? */
    boolean achieved(String activity, String variant);

    /** "" before an ending; {@link CampaignGraph#POST_ENDING} after one. */
    String phase();

    boolean endingSeen(String ending);

    /** Is the player's EFFECTIVE career (a temporary override included) this one? */
    boolean hasCareer(String career);

    long balance();

    /** Is this story character dead in this world? */
    boolean storyDead(String storyId);

    /** Was this activity ever available to this player (a STICKY activity stays open once it was)? */
    boolean stickyUnlocked(String activity);
}
