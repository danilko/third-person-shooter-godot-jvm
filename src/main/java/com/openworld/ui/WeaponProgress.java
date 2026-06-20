package com.openworld.ui;

import com.openworld.character.Character;
import com.openworld.weapon.WeaponController;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Control;
import godot.api.Image;
import godot.api.ImageTexture;
import godot.api.Texture2D;
import godot.api.TextureProgressBar;
import godot.core.Color;

/**
 * Radial switch/reload progress ring shown at the crosshair (centre of screen). Each frame it polls the
 * active player's {@link WeaponController}: while a weapon switch (deploy) or reload is in flight it
 * shows and fills 0→100%, and is hidden otherwise. Switch and reload don't overlap in practice; switch
 * takes priority. Tinted differently for the two so the cue is legible. Wired by
 * {@code HUDManager.wirePlayer} via {@link #wireCharacter}.
 *
 * <p>The ring texture is generated procedurally in {@link #_ready} (a transparent annulus) so no ring
 * asset is needed — radial fill over a ring reveals it clockwise like the CS/Apex reload circle. Reuses
 * the {@link TextureProgressBar} radial fill mode set in the scene ({@code WeaponProgress.tscn}).
 */
@RegisterClass(className = "WeaponProgress")
public class WeaponProgress extends TextureProgressBar {

  /** Diameter of the generated ring texture in px. */
  private static final int RING_PX = 64;
  /** Inner hole as a fraction of the radius (closer to 1 = thinner ring). */
  private static final float RING_INNER_FRAC = 0.78f;

  /** Tint while a weapon switch (deploy) is in progress. */
  @Export @RegisterProperty public Color switchTint = new Color(0.55f, 0.85f, 1f, 0.9f);
  /** Tint while a reload is in progress. */
  @Export @RegisterProperty public Color reloadTint = new Color(1f, 0.7f, 0.25f, 0.9f);
  /** Tint of the always-present background track ring. */
  @Export @RegisterProperty public Color trackTint = new Color(0f, 0f, 0f, 0.35f);

  /**
   * Optional ring texture. When assigned (a baked PNG) it is used as-is — cheaper than generating and
   * lets you control the exact look. When left null, a smooth ring is generated once at startup (a
   * one-time cost, then cached; runtime is identical to an asset).
   */
  @Export @RegisterProperty public Texture2D ringTexture;

  private WeaponController weaponController;

  /** Bind to the active player's weapon controller (called by HUDManager). */
  public void wireCharacter(Character c) {
    weaponController = (c != null) ? c.weaponController : null;
  }

  @RegisterFunction
  @Override
  public void _ready() {
    setMouseFilter(Control.MouseFilter.IGNORE);
    setValue(0.0);               // range 0..100 comes from the scene (max_value = 100)
    setNinePatchStretch(false);

    // Prefer an assigned asset (cheapest, crispest); otherwise generate a smooth ring once.
    Texture2D ring = ringTexture != null ? ringTexture : buildRing(RING_PX, RING_INNER_FRAC);
    if (ring != null) {
      setUnderTexture(ring);     // background track (full ring, dim)
      setProgressTexture(ring);  // filled portion (radially revealed, tinted)
    }
    setTintUnder(trackTint);
    setVisible(false);
  }

  @RegisterFunction
  @Override
  public void _process(double delta) {
    if (weaponController == null) { setVisible(false); return; }
    double sp = weaponController.getSwitchProgress();
    double rp = weaponController.getReloadProgress();
    boolean switching = sp >= 0.0;
    double p = switching ? sp : rp;
    if (p < 0.0) { setVisible(false); return; }
    setTintProgress(switching ? switchTint : reloadTint);
    setValue(p * 100.0);
    setVisible(true);
  }

  /**
   * Builds a transparent-background white ring (annulus) texture with ~1px anti-aliased edges, centred
   * exactly on the texture so the radial fill aligns with the crosshair when the control rect is
   * centred. One-time cost at startup.
   */
  private static ImageTexture buildRing(int size, float innerFrac) {
    Image img = Image.create(size, size, false, Image.Format.RGBA8);
    if (img == null) return null;
    img.fill(new Color(1f, 1f, 1f, 0f));
    float c = size / 2f;
    float outer = c - 0.5f;          // half-pixel margin keeps the outer edge inside the texture
    float inner = c * innerFrac;
    float aa = 1.0f;                 // edge softness (px)
    for (int y = 0; y < size; y++) {
      for (int x = 0; x < size; x++) {
        float dx = x + 0.5f - c;
        float dy = y + 0.5f - c;
        float d = (float) Math.sqrt(dx * dx + dy * dy);
        // Smooth alpha: 1 in the band [inner, outer], ramping to 0 over `aa` px at each edge.
        float a = Math.min((outer - d) / aa, (d - inner) / aa);
        a = a < 0f ? 0f : (a > 1f ? 1f : a);
        if (a > 0f) img.setPixel(x, y, new Color(1f, 1f, 1f, a));
      }
    }
    return ImageTexture.createFromImage(img);
  }
}
