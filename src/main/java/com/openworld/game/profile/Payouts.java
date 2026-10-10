package com.openworld.game.profile;

import com.openworld.character.Player;
import com.openworld.game.PlayerRegistry;
import godot.global.GD;

import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

/**
 * The economy's SOURCES that play pays out (PLAN.md 1.4 / F3), run where the result is decided -- the host. Amounts
 * are {@link EconomyTable}'s; every yen goes through {@link Economy#transfer} (REWARD), so a co-op player's session
 * copy changes on the host and travels back to them (MSG_PROFILE).
 */
public final class Payouts {
    private Payouts() {}

    /** A mission the PLAYERS won pays every player in the session (co-op shares a mission), once per profile. */
    public static int missionWon(String missionId) {
        long amount = EconomyTable.get().missionReward(missionId);
        if (amount <= 0) return 0;
        Set<PlayerProfile> paid = Collections.newSetFromMap(new IdentityHashMap<>());
        for (Player p : PlayerRegistry.getPlayers()) {
            if (p == null || !GD.isInstanceValid(p)) continue;
            PlayerProfile prof = Profiles.of(p);
            if (prof != null && paid.add(prof)) Economy.transfer(null, prof, amount, Economy.Reason.REWARD);
        }
        if (!paid.isEmpty()) GD.print("Payouts: '" + missionId + "' paid ¥" + amount + " to " + paid.size() + " player(s)");
        return paid.size();
    }

    /** A human racer finished at {@code place}: the table's prize for it (0 past the paid places). */
    public static long raceFinished(String characterId, int place) {
        long prize = EconomyTable.get().racePrize(place);
        if (prize <= 0 || characterId == null) return 0;
        for (Player p : PlayerRegistry.getPlayers()) {
            if (p == null || !GD.isInstanceValid(p) || p.getCharacterInfo() == null
                    || !characterId.equals(p.getCharacterInfo().characterId)) continue;
            PlayerProfile prof = Profiles.of(p);
            if (prof != null && Economy.transfer(null, prof, prize, Economy.Reason.REWARD)) {
                GD.print("Payouts: " + characterId + " finished #" + place + ", prize ¥" + prize);
                return prize;
            }
        }
        return 0;
    }
}
