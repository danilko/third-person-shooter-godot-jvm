package com.openworld.item;

/**
 * Things a shop sells that are neither a weapon nor a supply (PLAN.md 3.2): a GADGET is owned, not carried -- bought
 * once, it is a {@code PlayerProfile.unlocks} entry for good, and buying it again is refused (the menu says OWNED).
 * Priced in economy.json's {@code gadgets}. Engine-free.
 */
public final class Gadgets {
    private Gadgets() {}

    /** The flashlight (character.Flashlight): its shop id is also its unlock. */
    public static final String FLASHLIGHT = "flashlight";

    public static boolean isGadget(String id) { return FLASHLIGHT.equals(id); }

    /** The name a shop menu shows. */
    public static String name(String id) { return FLASHLIGHT.equals(id) ? "Flashlight" : id; }

    /** The profile unlock that owning {@code id} is. */
    public static String unlock(String id) { return id; }
}
