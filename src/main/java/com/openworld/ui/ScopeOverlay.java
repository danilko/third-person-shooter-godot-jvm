package com.openworld.ui;

import com.openworld.character.Character;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Control;
import godot.api.Node;
import godot.core.Color;
import godot.core.PackedVector2Array;
import godot.core.Rect2;
import godot.core.Vector2;

/**
 * The full-screen scope picture drawn while the local player is looking through a scoped weapon —
 * the black surround, the optic's ring, and its reticle (PLAN.md 2.7 piece 1).
 *
 * <p><b>A full-screen overlay, not a render-to-texture scope.</b> The decision that a scoped shot is
 * FIRST PERSON from both views (user, 2026-09-16) is what buys this: the camera is already behind the
 * shooter's eye and already zoomed to the weapon's {@code scopedFovDegrees}, so what the player sees
 * through the glass is simply what the camera renders. A {@code SubViewport} would render the world a
 * second time to produce the same picture — the CS/PUBG answer is this one, and it costs nothing.
 *
 * <p><b>Drawn, not authored.</b> There is no scope asset and no per-weapon artwork yet, so the optic
 * is generated in {@link #_draw} the way {@link WeaponProgress} generates its ring: it scales to any
 * resolution by construction, and dropping in a texture later is a change to this one node. The
 * surround is an ANNULUS of quads rather than a rectangle with a hole, because a filled polygon
 * cannot have one.
 *
 * <p><b>Self-managed, like {@link WeaponProgress}.</b> It polls the wired character's
 * {@code isScoped()} every frame instead of taking a push, so it needs no entry in
 * {@code HUDManager}'s {@code BASE_LAYOUT} situation table and — more to the point — cannot be left
 * on screen by an interruption that nobody thought to route through a handler. The state it reads is
 * itself derived (see {@code Character.isScoped()}), so death, a weapon switch, a drop and a
 * car door all take it down for free. {@link Crosshair} hides itself on the same condition.
 */
@Script(className = "ScopeOverlay")
public class ScopeOverlay extends Control {

    /** How much of the screen's shorter side the optic's glass occupies, as a fraction of it. */
    @Export public float scopeRadiusFraction = 0.42f;

    /** The blacked-out surround — the body of the scope. Opaque: the eye sees the tube, not the world. */
    @Export public Color surroundColor = new Color(0f, 0f, 0f, 1f);

    /** The glass's edge — a thin bright rim so the circle reads as an optic and not as a vignette. */
    @Export public Color ringColor = new Color(0.05f, 0.05f, 0.05f, 1f);

    /** The etched reticle. */
    @Export public Color reticleColor = new Color(0.03f, 0.03f, 0.03f, 1f);

    /** Ring thickness in px at a 1080p-tall screen; scaled with the screen like everything else. */
    @Export public float ringWidth = 6f;

    /** Reticle line thickness, px. */
    @Export public float reticleWidth = 1.6f;

    /** Gap at the centre, as a fraction of the glass radius, so the aim point itself stays clear. */
    @Export public float centerGapFraction = 0.06f;

    /** How many mil-dot ticks each arm of the reticle carries. */
    @Export public int tickCount = 4;

    /** Segments in the surround annulus. 96 is smooth at 4K and is 96 quads, once per scoped frame. */
    private static final int SEGMENTS = 96;

    /** The body whose scope this is. Asked rather than the weapon controller: it adds dead and seated. */
    private Character character;

    /**
     * Bind to the active player's weapon controller (called by {@code HUDManager.wirePlayer}).
     *
     * <p>{@code @Register}ed, unlike {@link WeaponProgress}'s equivalent, so the gate can bind this
     * node to a body without standing up a HUDManager and an EventBus AutoLoad in a bare SceneTree.
     * Takes a {@code Node}: a registered method's parameter has to be a type godot-jvm can pass.
     */
    @Register
    public void wireCharacter(Node c) {
        character = (c instanceof Character ch) ? ch : null;
    }

    @Register
    @Override
    public void _ready() {
        setMouseFilter(Control.MouseFilter.IGNORE);
        setVisible(false);
    }

    @Register
    @Override
    public void _process(double delta) {
        // Character.isScoped, the one answer the camera and the head also use: the weapon controller
        // alone does not know the body died or sat down.
        boolean scoped = character != null && character.isScoped();
        if (scoped != isVisible()) setVisible(scoped);
        // Only while it is on screen: the glass has to follow a resolution change, and later a
        // breathing sway, but an unscoped frame costs nothing at all.
        if (scoped) queueRedraw();
    }

    /** True when the optic is on screen — the gate ({@code probe_sniper_scope.gd}) reads it. */
    @Register
    public boolean scopeShown() { return isVisible(); }

    @Register
    @Override
    public void _draw() {
        Vector2 size = getSize();
        float w = (float) size.getX();
        float h = (float) size.getY();
        if (w <= 1f || h <= 1f) return;
        Vector2 center = new Vector2(w * 0.5f, h * 0.5f);
        float radius = Math.min(w, h) * scopeRadiusFraction;
        // Past the far corner, so the annulus covers the whole screen at any aspect ratio.
        float outer = (float) Math.sqrt(w * w + h * h);
        float scale = h / 1080f;

        // Surround: one quad per segment between the glass edge and the off-screen outer radius.
        // A rect with a hole is not expressible as a filled polygon, so the ring is built instead.
        for (int i = 0; i < SEGMENTS; i++) {
            double a0 = (Math.PI * 2.0 * i) / SEGMENTS;
            double a1 = (Math.PI * 2.0 * (i + 1)) / SEGMENTS;
            PackedVector2Array quad = new PackedVector2Array();
            quad.pushBack(onCircle(center, radius, a0));
            quad.pushBack(onCircle(center, radius, a1));
            quad.pushBack(onCircle(center, outer, a1));
            quad.pushBack(onCircle(center, outer, a0));
            drawColoredPolygon(quad, surroundColor, new PackedVector2Array(), null);
        }

        // The glass rim, drawn INSIDE the surround's inner edge so the two meet with no seam.
        float rim = ringWidth * scale;
        drawArc(center, radius - rim * 0.5f, 0f, (float) (Math.PI * 2.0), SEGMENTS * 2,
                ringColor, rim, true);

        drawReticle(center, radius - rim, scale);
    }

    /** Crosshair arms with a clear centre, a dot, and mil ticks down the lower and side arms. */
    private void drawReticle(Vector2 center, float radius, float scale) {
        float cx = (float) center.getX();
        float cy = (float) center.getY();
        float gap = radius * centerGapFraction;
        float lw  = reticleWidth * scale;

        drawLine(new Vector2(cx - radius, cy), new Vector2(cx - gap, cy), reticleColor, lw, true);
        drawLine(new Vector2(cx + gap, cy), new Vector2(cx + radius, cy), reticleColor, lw, true);
        drawLine(new Vector2(cx, cy - radius), new Vector2(cx, cy - gap), reticleColor, lw, true);
        drawLine(new Vector2(cx, cy + gap), new Vector2(cx, cy + radius), reticleColor, lw, true);
        drawCircle(center, Math.max(1f, lw), reticleColor, true, -1f, true);

        float tick = radius * 0.035f;
        for (int i = 1; i <= tickCount; i++) {
            float d = radius * (i / (float) (tickCount + 1));
            drawLine(new Vector2(cx - tick, cy + d), new Vector2(cx + tick, cy + d),
                     reticleColor, lw, true);
            drawLine(new Vector2(cx - d, cy - tick), new Vector2(cx - d, cy + tick),
                     reticleColor, lw, true);
            drawLine(new Vector2(cx + d, cy - tick), new Vector2(cx + d, cy + tick),
                     reticleColor, lw, true);
        }
    }

    private static Vector2 onCircle(Vector2 c, float r, double angle) {
        return new Vector2((float) (c.getX() + Math.cos(angle) * r),
                           (float) (c.getY() + Math.sin(angle) * r));
    }

    // ── Exported-property accessor pairs (godot-jvm merges field + accessors into ONE property,
    //    so a getter without a setter would register READ_ONLY and never take the scene's value) ──

    public float getScopeRadiusFraction() { return scopeRadiusFraction; }
    public void setScopeRadiusFraction(float v) { scopeRadiusFraction = v; }

    public Color getSurroundColor() { return surroundColor; }
    public void setSurroundColor(Color v) { surroundColor = v; }

    public Color getRingColor() { return ringColor; }
    public void setRingColor(Color v) { ringColor = v; }

    public Color getReticleColor() { return reticleColor; }
    public void setReticleColor(Color v) { reticleColor = v; }

    public float getRingWidth() { return ringWidth; }
    public void setRingWidth(float v) { ringWidth = v; }

    public float getReticleWidth() { return reticleWidth; }
    public void setReticleWidth(float v) { reticleWidth = v; }

    public float getCenterGapFraction() { return centerGapFraction; }
    public void setCenterGapFraction(float v) { centerGapFraction = v; }

    public int getTickCount() { return tickCount; }
    public void setTickCount(int v) { tickCount = v; }
}
