package com.openworld.game.campaign;

/**
 * A content pack (PLAN.md 2.1 / CR6): it DECLARES its part of the campaign -- flags, activities, endings -- into a
 * {@link CampaignBuilder}. Core code is never edited to add a mission: a new act is a new class here, listed in
 * {@link com.openworld.game.campaign.content.CampaignModules}. Scene nodes only provide placement for an activity id.
 */
public interface CampaignModule {

    /** A stable id ("act1"), unique among the modules. */
    String id();

    void define(CampaignBuilder b);
}
