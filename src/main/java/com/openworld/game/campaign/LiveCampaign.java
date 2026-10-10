package com.openworld.game.campaign;

import com.openworld.game.WorldLedger;
import com.openworld.game.profile.PlayerProfile;

/**
 * The real thing a requirement is asked against and an effect written to (PLAN.md 2.1 / CR1, the co-op model's rule
 * 1): ONE player's profile -- personal flags, achieved variants, endings, career, money -- and the HOST's world
 * ledger -- world flags, dead story characters, place overrides. Engine-free; whoever holds the two builds one.
 */
public final class LiveCampaign implements CampaignWrite {

    private final PlayerProfile profile;
    private final WorldLedger world;

    public LiveCampaign(PlayerProfile profile, WorldLedger world) {
        this.profile = profile;
        this.world = world;
    }

    @Override public String flag(FlagKey key) {
        if (key.scope() == FlagKey.Scope.WORLD) return world.flag(key.id(), "");
        String v = profile.campaign.flags.get(key.id());
        return v == null ? "" : v;
    }

    @Override public boolean achieved(String activity, String variant) {
        if (!variant.isEmpty()) return profile.campaign.achieved.contains(CampaignGraph.achievedKey(activity, variant));
        String prefix = activity + "#";
        for (String k : profile.campaign.achieved) if (k.startsWith(prefix)) return true;
        return false;
    }

    @Override public String phase() { return profile.campaign.phase; }
    @Override public boolean endingSeen(String ending) { return profile.campaign.endingsSeen.contains(ending); }
    @Override public boolean hasCareer(String career) { return career.equals(profile.career.effective()); }
    @Override public long balance() { return profile.balance; }
    @Override public boolean storyDead(String storyId) { return world.isDead(storyId); }
    @Override public boolean stickyUnlocked(String activity) { return profile.campaign.sticky.contains(activity); }

    @Override public void setFlag(FlagKey key, String value) {
        if (key.scope() == FlagKey.Scope.WORLD) {
            if (value.isEmpty()) world.clearFlag(key.id());
            else world.setFlag(key.id(), value);
            return;
        }
        String had = profile.campaign.flags.get(key.id());
        if (value.isEmpty() ? had == null : value.equals(had)) return;
        if (value.isEmpty()) profile.campaign.flags.remove(key.id());
        else profile.campaign.flags.put(key.id(), value);
        profile.touch();
    }

    @Override public void achieve(String activity, String variant) {
        if (profile.campaign.achieved.add(CampaignGraph.achievedKey(activity, variant))) profile.touch();
    }

    @Override public void ending(String ending) {
        boolean news = profile.campaign.endingsSeen.add(ending);
        if (!CampaignGraph.POST_ENDING.equals(profile.campaign.phase)) {
            profile.campaign.phase = CampaignGraph.POST_ENDING;
            news = true;
        }
        if (news) profile.touch();
    }

    @Override public void chapter(String chapter) {
        if (chapter.equals(profile.campaign.chapter)) return;
        profile.campaign.chapter = chapter;
        profile.touch();
    }

    @Override public void markStoryDead(String storyId) { world.markDead(storyId); }

    @Override public void setPlace(String placeId, String owner, String state) { world.setPlace(placeId, owner, state); }

    @Override public void unlockSticky(String activity) {
        if (profile.campaign.sticky.add(activity)) profile.touch();
    }
}
