package com.openworld.item;

import com.openworld.character.Character;
import godot.api.Input;
import godot.api.InputEventKey;
import godot.api.InputMap;
import godot.core.Key;
import godot.core.StringName;
import godot.global.GD;

/**
 * Carrying and using healing supplies (PLAN.md W3; user 2026-10-03: "before death, heal with food / medical
 * supplies"). The counts live on {@link Character#supplies} on the AUTHORITATIVE peer (single player or host),
 * where a counter grants them and health is applied; a client's use is a request to the host
 * ({@code MSG_SUPPLY_USE}). The key is {@code use_supply} (H), added to the InputMap at run time when the project
 * does not define it.
 */
public final class Supplies {

    public static final String ACTION = "use_supply";

    private Supplies() {}

    /** Polled by PlayerController; makes sure the action exists first. */
    public static boolean useKeyJustPressed() {
        StringName a = new StringName(ACTION);
        if (!InputMap.INSTANCE.hasAction(a)) {
            InputMap.INSTANCE.addAction(a, 0.5f);
            InputEventKey k = new InputEventKey();
            k.setPhysicalKeycode(Key.H);
            InputMap.INSTANCE.actionAddEvent(a, k);
        }
        return Input.INSTANCE.isActionJustPressed(ACTION, false);
    }

    /** Add one; false when already carrying the most of it. */
    public static boolean give(Character c, String id) {
        SupplyCatalog.Supply s = SupplyCatalog.find(id);
        if (c == null || s == null) return false;
        int n = c.supplies.getOrDefault(id, 0);
        if (n >= s.max()) return false;
        c.supplies.put(id, n + 1);
        return true;
    }

    public static int count(Character c, String id) {
        return c == null ? 0 : c.supplies.getOrDefault(id, 0);
    }

    /** Use the best-fitting carried supply. A client asks the host. Returns the id used ("" none). */
    public static String use(Character c) {
        if (c == null || c.healthNode == null || !c.isAlive()) return "";
        if (c.getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager net
                && net.isNetworked() && !net.isServer()) {
            if (c.characterInfo != null) net.sendSupplyUse(c.characterInfo.characterId);
            return "";
        }
        return useHere(c);
    }

    /** The authority's half of {@link #use}. */
    public static String useHere(Character c) {
        float missing = c.healthNode.maxHealth - c.healthNode.getCurrentHealth();
        if (missing <= 0.5f) return "";
        String id = SupplyCatalog.best(c.supplies, SupplyCatalog.load(), missing);
        if (id == null) return "";
        c.supplies.put(id, c.supplies.get(id) - 1);
        c.healthNode.heal(SupplyCatalog.find(id).heal());
        GD.print("Supplies: " + c.getName() + " used " + id);
        return id;
    }
}
