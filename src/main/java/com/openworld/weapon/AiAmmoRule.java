package com.openworld.weapon;

import com.openworld.game.data.Tables;

/**
 * THE AI AMMO RULE (PLAN.md P1e step 1, user 2026-10-15: "AI run dry far too easily"; supersedes "No unlimited ammo",
 * 2026-10-07). Data: item/ammo_supply.json {@code ai_ammo}.
 *
 * <ul>
 *   <li>A FIREARM held by an {@code AICharacter} never spends its reserve on a reload ({@link FirearmItem}'s
 *   {@code keepsReserveOnReload}). It still empties magazines and reloads, so the rhythm of a fight is unchanged, and
 *   a reserve that is already 0 stays 0 -- {@code EnforcementDispatch.drainUnitAmmoNow}, the dry retreat and a
 *   scripted dry unit keep working. Keyed on the HOLDER being an AICharacter, not on its controller: a disconnected
 *   player's bot body is a Player and stays finite.</li>
 *   <li>Launchers and throwables stay finite per unit (they are not FirearmItems), and every AI explosive shares
 *   {@link ExplosiveCooldown}.</li>
 *   <li>A firearm an AI lets go of (death drop or a manual one) is FINITE for whoever picks it up, locally or over the
 *   network: the magazine left in it plus 0..{@code drop_spare_mags} whole magazines, rolled ({@link #stampDropped}).
 *   The drop wire already carries magazine and reserve, so a stamped drop needs no wire change.</li>
 * </ul>
 */
public final class AiAmmoRule {
    private AiAmmoRule() {}

    /** Null = the data decides; true / false = a probe's control override. */
    public static Boolean unlimitedOverride = null;

    private static Tables.AiAmmo data() {
        Tables.AmmoSupplies t = Tables.AMMO_SUPPLY.get();
        return t != null && t.ai() != null ? t.ai() : Tables.AiAmmo.DEFAULT;
    }

    /** Does an AI's firearm keep its reserve on a reload? */
    public static boolean unlimitedReserve() {
        return unlimitedOverride != null ? unlimitedOverride : data().unlimitedReserve();
    }

    /** The reserve a dropped AI firearm keeps: 0..maxSpare whole magazines for a roll in [0, 1). Engine-free. */
    public static int dropReserve(int magazineSize, int maxSpare, double roll) {
        if (magazineSize <= 0 || maxSpare <= 0) return 0;
        int mags = (int) Math.floor(Math.max(0, Math.min(roll, 0.999999)) * (maxSpare + 1));
        return mags * magazineSize;
    }

    private static final java.util.Random rng = new java.util.Random(0xD0F1);
    private static int stamped;

    /** Make a firearm an AI is letting go of finite (only while the unlimited rule is on: otherwise its reserve is
     *  already what it really carries). */
    public static void stampDropped(WeaponItem item) {
        if (!(item instanceof FirearmItem) || item.isInfiniteAmmo || !unlimitedReserve()) return;
        item.setReserve(Math.min(item.getReserve(), dropReserve(item.getMagazineSize(), data().dropSpareMags(), rng.nextDouble())));
        stamped++;
    }

    /** AI drops made finite since start (probe readout). */
    public static int stampedCount() { return stamped; }
}
