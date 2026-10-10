package com.openworld.game.campaign;

/**
 * What completing an activity with a variant CHANGES (PLAN.md 2.1 / CR1) -- data, like {@link Requirement}, so the
 * lint can walk it. A flag effect is a WORLD effect or a PERSONAL one by its key's scope; marking a story character
 * dead and overriding a place are world effects; an ending and a chapter are personal.
 */
public sealed interface Effect {

    void apply(CampaignWrite w);

    /** Does it change the WORLD (the host's ledger)? A replay applies none; a guest's needs the host's consent. */
    boolean world();

    /** {@code value} "" clears the flag. */
    record SetFlag(FlagKey key, String value) implements Effect {
        @Override public void apply(CampaignWrite w) { w.setFlag(key, value); }
        @Override public boolean world() { return key.scope() == FlagKey.Scope.WORLD; }
    }

    record StoryDead(String storyId) implements Effect {
        @Override public void apply(CampaignWrite w) { w.markStoryDead(storyId); }
        @Override public boolean world() { return true; }
    }

    record Place(String placeId, String owner, String state) implements Effect {
        @Override public void apply(CampaignWrite w) { w.setPlace(placeId, owner, state); }
        @Override public boolean world() { return true; }
    }

    /** The player reaches this ending: their phase becomes POST_ENDING and the world stays open. */
    record Ending(String ending) implements Effect {
        @Override public void apply(CampaignWrite w) { w.ending(ending); }
        @Override public boolean world() { return false; }
    }

    record Chapter(String chapter) implements Effect {
        @Override public void apply(CampaignWrite w) { w.chapter(chapter); }
        @Override public boolean world() { return false; }
    }

    static Effect set(FlagKey key) { return new SetFlag(key, FlagKey.ON); }
    static Effect set(FlagKey key, String value) { return new SetFlag(key, value); }
    static Effect clear(FlagKey key) { return new SetFlag(key, ""); }
    static Effect storyDead(String storyId) { return new StoryDead(storyId); }
    static Effect place(String placeId, String owner, String state) { return new Place(placeId, owner, state); }
    static Effect ending(String ending) { return new Ending(ending); }
    static Effect chapter(String chapter) { return new Chapter(chapter); }
}
