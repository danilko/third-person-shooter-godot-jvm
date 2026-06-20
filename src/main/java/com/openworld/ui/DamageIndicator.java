package com.openworld.ui;

import com.openworld.character.Character;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Camera3D;
import godot.api.Control;
import godot.api.TextureRect;
import godot.api.Texture2D;
import godot.core.Basis;
import godot.core.Color;
import godot.core.Vector2;
import godot.core.Vector3;

import java.util.ArrayList;
import java.util.List;

/**
 * HUD damage-direction indicator — the industry-standard directional hit cue (CoD/Battlefield style):
 * when the local player is damaged, a red arc appears around the crosshair, <b>rotated to the bearing
 * of the attacker</b> (top = in front, sides = left/right, bottom = behind), then fades out over
 * {@link #fadeSeconds}. Repeated hits from a similar bearing re-trigger the same arc and stack its
 * opacity, clamped to {@link #maxAlpha} (the "max per direction"). A small fixed pool of arcs
 * ({@link #POOL}) handles simultaneous multi-source hits without clutter.
 *
 * <p>Driven by {@link com.openworld.game.EventBus#characterDamagedFrom}: {@code HUDManager} filters
 * that to the local player and calls {@link #onDamagedFrom(Vector3)} with the attacker's world
 * position. The bearing is computed relative to the player camera's facing, so it stays correct as the
 * camera turns. Pure display widget — no input, no game-state mutation.
 *
 * <p>Each arc is a {@link TextureRect} parented to a zero-size pivot {@link Control} kept at screen
 * centre; rotating the pivot orbits the arc around the centre to the bearing (the same radial trick
 * {@code WeaponRadialMenu} uses for its slots). The arc texture is an exported {@link Texture2D}
 * (a red wedge); a plain white placeholder tinted red still reads as a directional mark.
 */
@RegisterClass(className = "DamageIndicator")
public class DamageIndicator extends Control {

  /** Arc texture (ideally a red radial wedge with a transparent centre). Tinted by {@link #tint}. */
  @Export @RegisterProperty public Texture2D arcTexture;

  /** Seconds for an arc at full opacity to fade to nothing. */
  @Export @RegisterProperty public float fadeSeconds = 1.5f;

  /** Maximum opacity an arc reaches — stacked hits from one direction clamp here. */
  @Export @RegisterProperty public float maxAlpha = 1.0f;

  /** Opacity added to an arc per hit (stacks up to {@link #maxAlpha}). */
  @Export @RegisterProperty public float alphaPerHit = 0.55f;

  /** Distance (px) from screen centre at which the arc sits. */
  @Export @RegisterProperty public float radius = 150f;

  /** Arc size in px (a wide, short bar reads as an arc segment). */
  @Export @RegisterProperty public Vector2 arcSize = new Vector2(120f, 22f);

  /** Hits within this many radians of an active arc's bearing stack onto it instead of opening a new arc. */
  @Export @RegisterProperty public float mergeAngleRad = 0.45f;

  /** Arc colour (alpha is driven per-frame by the fade). */
  @Export @RegisterProperty public Color tint = new Color(1f, 0.15f, 0.15f, 1f);

  /** Number of simultaneous directional arcs. */
  private static final int POOL = 6;

  private final List<Control>     pivots = new ArrayList<>();
  private final List<TextureRect> arcs   = new ArrayList<>();
  private final double[] alpha   = new double[POOL];
  private final double[] bearing = new double[POOL];

  /**
   * Kept for API compatibility / future use; the bearing now derives from the viewport's CURRENT
   * camera (correct on foot and in a vehicle alike), so no player reference is required.
   */
  public void setPlayer(Character c) { }

  @RegisterFunction
  @Override
  public void _ready() {
    setMouseFilter(Control.MouseFilter.IGNORE);
    for (int i = 0; i < POOL; i++) {
      Control pivot = new Control();
      pivot.setMouseFilter(Control.MouseFilter.IGNORE);
      addChild(pivot);

      TextureRect arc = new TextureRect();
      arc.setMouseFilter(Control.MouseFilter.IGNORE);
      if (arcTexture != null) arc.setTexture(arcTexture);
      arc.setExpandMode(TextureRect.ExpandMode.IGNORE_SIZE);
      arc.setStretchMode(TextureRect.StretchMode.SCALE);
      arc.setSize(arcSize);
      // Sit the arc `radius` above the pivot origin, centred horizontally; rotating the pivot then
      // swings it around screen centre to the attacker's bearing.
      arc.setPosition(new Vector2(-arcSize.getX() * 0.5f, -radius - arcSize.getY()));
      pivot.addChild(arc);

      pivots.add(pivot);
      arcs.add(arc);
      alpha[i]   = 0.0;
      bearing[i] = 0.0;
      applyArc(i);
    }
  }

  /**
   * Show / refresh a directional arc toward {@code attackerWorldPos}. Called by HUDManager when the
   * local player takes damage with a known source. No-op until a player + camera are wired.
   */
  @RegisterFunction
  public void onDamagedFrom(Vector3 attackerWorldPos) {
    if (attackerWorldPos == null) return;
    // Use the viewport's CURRENT camera as the viewpoint — correct whether on foot (TPS/FPS) or in a
    // vehicle (vehicle camera), with no dependency on which body we own.
    Camera3D cam = getViewport() != null ? getViewport().getCamera3d() : null;
    if (cam == null) return;

    Vector3 d = attackerWorldPos.minus(cam.getGlobalPosition());
    d = new Vector3(d.getX(), 0f, d.getZ());
    if (d.lengthSquared() < 1e-4f) return;

    Basis b = cam.getGlobalBasis();
    Vector3 fwd   = b.getZ().times(-1f);
    Vector3 right = b.getX();
    fwd   = new Vector3(fwd.getX(),   0f, fwd.getZ());
    right = new Vector3(right.getX(), 0f, right.getZ());
    if (fwd.lengthSquared() < 1e-4f || right.lengthSquared() < 1e-4f) return;
    fwd = fwd.normalized();
    right = right.normalized();

    // 0 = in front (up), +pi/2 = right, ±pi = behind (down), -pi/2 = left.
    double bearingRad = Math.atan2(d.dot(right), d.dot(fwd));
    if (Double.isNaN(bearingRad)) return;
    triggerArc(bearingRad);
  }

  private void triggerArc(double b) {
    int slot = -1;
    for (int i = 0; i < POOL; i++) {
      if (alpha[i] > 0.0 && angleClose(bearing[i], b)) { slot = i; break; }
    }
    if (slot < 0) slot = freeOrWeakestSlot();
    bearing[slot] = b;
    alpha[slot]   = Math.min(maxAlpha, alpha[slot] + alphaPerHit);
    applyArc(slot);
  }

  private boolean angleClose(double a, double b) {
    double diff = Math.abs(Math.atan2(Math.sin(a - b), Math.cos(a - b)));
    return diff <= mergeAngleRad;
  }

  private int freeOrWeakestSlot() {
    int weakest = 0;
    for (int i = 0; i < POOL; i++) {
      if (alpha[i] <= 0.0) return i;
      if (alpha[i] < alpha[weakest]) weakest = i;
    }
    return weakest;
  }

  @RegisterFunction
  @Override
  public void _process(double delta) {
    Vector2 center = getViewportRect().getSize().times(0.5f);
    double fade = fadeSeconds > 0f ? (delta / fadeSeconds) : delta;
    for (int i = 0; i < POOL; i++) {
      pivots.get(i).setPosition(center);
      if (alpha[i] <= 0.0) continue;
      alpha[i] = Math.max(0.0, alpha[i] - fade);
      applyArc(i);
    }
  }

  private void applyArc(int i) {
    pivots.get(i).setRotation((float) bearing[i]);
    arcs.get(i).setModulate(new Color(tint.getR(), tint.getG(), tint.getB(), (float) alpha[i]));
  }
}
