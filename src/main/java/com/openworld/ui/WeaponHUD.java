package com.openworld.ui;

import com.openworld.character.Character;
import com.openworld.weapon.WeaponController;
import com.openworld.weapon.WeaponItem;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Control;
import godot.api.Label;
import godot.api.TextureRect;

/**
 * The held weapon, bottom-right (the CS2 / GTA V corner): its icon and name, the magazine large and the reserve
 * small. The magazine turns amber when a quarter or less is left and red when empty, and a weapon with no ammo (fist, melee) shows its
 * name only. The full inventory is {@link WeaponSlotsUI}, which pops up above this on a switch and fades.
 *
 * Polls the wired character's current weapon each frame and touches a label only when its value changed, so it
 * follows every source of change (a shot, a reload, a pickup, a switch, a replicated manifest) with no wiring.
 */
@Script(className = "WeaponHUD")
public class WeaponHUD extends Control {


    private WeaponController wc;
    private TextureRect icon;
    private Label name;
    private Label magazine;
    private Label reserve;
    private WeaponItem shownItem;
    private int shownMag = Integer.MIN_VALUE;
    private int shownReserve = Integer.MIN_VALUE;

    @Register
    @Override
    public void _ready() {
        setMouseFilter(MouseFilter.IGNORE);
        if (getNodeOrNull("Icon") instanceof TextureRect t) icon = t;
        if (getNodeOrNull("Name") instanceof Label l) name = l;
        if (getNodeOrNull("Ammo/Magazine") instanceof Label l) magazine = l;
        if (getNodeOrNull("Ammo/Reserve") instanceof Label l) reserve = l;
    }

    /** Called by HUDManager when the active player spawns or changes. */
    public void wireCharacter(Character c) {
        wc = c != null ? c.weaponController : null;
        shownItem = null;
        shownMag = shownReserve = Integer.MIN_VALUE;
    }

    @Register
    @Override
    public void _process(double delta) {
        if (wc == null || !godot.global.GD.isInstanceValid(wc)) return;
        WeaponItem w = wc.getCurrentWeaponItem();
        if (w != shownItem) {
            shownItem = w;
            shownMag = shownReserve = Integer.MIN_VALUE;
            if (icon != null) {
                icon.setTexture(w != null ? IconFit.cropped(w.weaponIcon) : null);   // one height for every weapon
                icon.setVisible(w != null && w.weaponIcon != null);
            }
            if (name != null) name.setText(w != null ? w.getDisplayName() : "");
        }
        boolean ammo = showsAmmo(w);
        if (magazine != null) magazine.setVisible(ammo);
        if (reserve != null) reserve.setVisible(ammo);
        if (!ammo) return;
        if (w.magazine != shownMag) {
            shownMag = w.magazine;
            magazine.setText(String.valueOf(w.magazine));
            // amber at a quarter or less, red when empty (HudPalette)
            magazine.setModulate(w.magazine <= 0 ? HudPalette.CRITICAL
                    : w.magazineSize > 0 && w.magazine * 4 <= w.magazineSize ? HudPalette.WARN : HudPalette.TEXT);
        }
        if (w.reserve != shownReserve) {
            shownReserve = w.reserve;
            reserve.setText("/ " + w.reserve);
        }
    }

    /** Whether the HUD shows a count for {@code w}: not for a fist or a melee weapon (their numbers mean nothing). */
    public static boolean showsAmmo(WeaponItem w) {
        return w != null && !w.isInfiniteAmmo && w.getWeaponType() != com.openworld.weapon.WeaponType.MELEE;
    }

    /** "SNR-1 5 / 20" (name, then the ammo if shown) for probes. */
    @Register
    public String textNow() {
        String n = name != null ? name.getText() : "";
        return magazine != null && magazine.isVisible() ? n + " " + magazine.getText() + " " + reserve.getText() : n;
    }
}
