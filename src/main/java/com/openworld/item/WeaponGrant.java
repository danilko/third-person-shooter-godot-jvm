package com.openworld.item;

import com.openworld.character.Character;
import com.openworld.weapon.WeaponCatalog;
import com.openworld.weapon.WeaponItem;
import godot.api.Node;

/**
 * Hand a character one catalog weapon -- the ONE grant path a shop counter uses (and the debug
 * console's {@code give} idea): a weapon already carried is REFILLED (magazine and reserve), else a fresh catalog
 * instance is put in the tree and queued into the inventory through {@code requestEquip}, so slot choice,
 * displacement and the HUD stay the weapon controller's. Call it on the authoritative peer only.
 */
public final class WeaponGrant {

    public enum Result { REFILLED, GIVEN, FAILED }

    private WeaponGrant() {}

    /** Does {@code c} already carry {@code weaponId}? (the menu says "refill" for those) */
    public static boolean carries(Character c, String weaponId) {
        if (c == null || c.weaponController == null) return false;
        var wc = c.weaponController;
        for (int i = 0; i < wc.slotCount(); i++) {
            WeaponItem w = wc.getWeaponItem(i);
            if (w != null && weaponId.equals(w.weaponId)) return true;
        }
        return false;
    }

    public static Result grant(Character c, String weaponId, Node anyInTree) {
        if (c == null || c.weaponController == null) return Result.FAILED;
        var wc = c.weaponController;
        for (int i = 0; i < wc.slotCount(); i++) {
            WeaponItem w = wc.getWeaponItem(i);
            if (w == null || !weaponId.equals(w.weaponId)) continue;
            w.magazine = w.magazineSize;
            w.reserve = w.reserveMax;
            WeaponItem cur = wc.getCurrentWeaponItem();
            if (cur != null) wc.ammoChanged.emit(cur.magazine, cur.reserve);
            return Result.REFILLED;
        }
        WeaponItem item = WeaponCatalog.instantiate(weaponId);
        if (item == null || anyInTree.getTree() == null || anyInTree.getTree().getCurrentScene() == null)
            return Result.FAILED;
        anyInTree.getTree().getCurrentScene().addChild(item);
        item.setGlobalPosition(c.getGlobalPosition());
        wc.requestEquip(item);
        return Result.GIVEN;
    }
}
