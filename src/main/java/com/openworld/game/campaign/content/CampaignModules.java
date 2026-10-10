package com.openworld.game.campaign.content;

import com.openworld.game.campaign.CampaignBuilder;
import com.openworld.game.campaign.CampaignGraph;
import com.openworld.game.campaign.CampaignModule;

import java.util.List;

/**
 * THE index of content packs (PLAN.md 2.1 / CR6): a new act is a class implementing {@link CampaignModule} and one
 * line here. {@code CampaignLintTest} lints exactly this list, so what ships is what was proven.
 */
public final class CampaignModules {
    private CampaignModules() {}

    public static final List<CampaignModule> ALL = List.of(new Act1());

    private static CampaignGraph graph;

    /** The shipped campaign, built once. */
    public static synchronized CampaignGraph graph() {
        if (graph == null) graph = new CampaignBuilder().add(ALL).build();
        return graph;
    }
}
