package com.openworld.ui;

import godot.api.AtlasTexture;
import godot.api.Image;
import godot.api.Texture2D;
import godot.core.Rect2;
import godot.core.Rect2i;

import java.util.IdentityHashMap;
import java.util.Map;

/**
 * Weapon icons cropped to their visible silhouette, so a HUD can draw every weapon at one COMMON HEIGHT (the CoD /
 * Apex convention). The generated icons ({@code render_weapon_icons.py}) are each fitted to a 384x128 frame, so a
 * short, chunky grenade fills the frame's full height while a long rifle, limited by the frame's width, fills less
 * of it: drawn whole, the grenade looks as big as the rifle. Cropped, and shown in a box of fixed height with
 * keep-aspect stretch, a rifle reads long and a grenade reads small, at one height.
 */
public final class IconFit {
    private IconFit() {}

    private static final Map<Texture2D, Texture2D> CROPPED = new IdentityHashMap<>();

    /** {@code icon} cropped to its opaque pixels (cached); the icon itself if it cannot be read. */
    static Texture2D cropped(Texture2D icon) {
        if (icon == null) return null;
        return CROPPED.computeIfAbsent(icon, t -> {
            Image img = t.getImage();
            if (img == null) return t;
            if (img.isCompressed()) img.decompress();
            Rect2i used = img.getUsedRect();
            if (used.getSize().getX() <= 0 || used.getSize().getY() <= 0) return t;
            AtlasTexture a = new AtlasTexture();
            a.setAtlas(t);
            a.setRegion(new Rect2(used.getPosition().getX(), used.getPosition().getY(),
                    used.getSize().getX(), used.getSize().getY()));
            return a;
        });
    }

    /** Drop the cache (it holds textures: cleared on shutdown like IconRegistry). */
    public static void clear() { CROPPED.clear(); }
}
