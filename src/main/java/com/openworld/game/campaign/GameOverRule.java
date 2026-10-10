package com.openworld.game.campaign;

import com.openworld.game.profile.PlayerProfile;

/**
 * One of the FEW designer-defined hard game overs (PLAN.md 2.1 / CR4): a state of ONE player that, held for a grace
 * period, ends in that player's game over -- "deep in debt for too long". Declared by a {@link CampaignModule}
 * ({@code b.gameOverRule(..)}) and judged by {@link GameOverWatch}; a failed mission or a missed branch is never
 * one of these.
 */
public interface GameOverRule {

    String id();

    /** Is the player in the state now? */
    boolean breached(PlayerProfile profile, CampaignView story);

    /** How long it may last before the game over. */
    double graceSeconds();

    /** What the WORLD tells the player when the grace period starts (a caller's line; the minimal HUD). */
    String warning();

    /** The player owes more than {@code yen} (loans and a negative balance together). */
    static GameOverRule debtOver(String id, long yen, double graceSeconds, String warning) {
        return new GameOverRule() {
            @Override public String id() { return id; }
            @Override public boolean breached(PlayerProfile p, CampaignView story) { return p.totalDebt() > yen; }
            @Override public double graceSeconds() { return graceSeconds; }
            @Override public String warning() { return warning; }
        };
    }
}
