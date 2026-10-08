package com.openworld.character;

import com.openworld.audio.Sound;
import com.openworld.movement.character.StanceName;

import godot.core.Vector3;

/**
 * A character's sounds and splashes from how its BODY moves in WATER: a swimmer's stroke every {@link #STROKE} metres,
 * a wader's splashing step every {@link #WADE_STEP} metres (not ankle deep), each a small splash at the water line
 * ({@link com.openworld.world.Splash}). Owner, AI and network puppet alike, with no message.
 *
 * <p>Footsteps and the landing thud were REMOVED (user, 2026-10-08: rarely heard, and they cost two engine calls per
 * character per physics tick). Out of the water this is one field read and returns, so the cost is nothing; git holds
 * the footstep version (surface by down ray, Terrain3D paint id) if it is ever wanted back.
 */
public final class CharacterAudio {
    /** Metres a swimmer covers per stroke, and a wader per (splashing) step. */
    public static final double STROKE = 1.6, WADE_STEP = 0.9;

    private Vector3 last;
    private double travelled;
    private int strokes;

    /** Swim strokes / wading splashes so far (probes). */
    public int strokes() { return strokes; }

    public void tick(Character c, double delta) {
        if (!c.inWater || c.currentVehicleNode != null || !c.isAlive()) {
            last = null;
            travelled = 0;
            return;
        }
        Vector3 p = c.getGlobalPosition();
        Vector3 prev = last;
        last = p;
        if (prev == null || delta <= 0) return;
        double dx = p.getX() - prev.getX(), dz = p.getZ() - prev.getZ();
        double moved = Math.sqrt(dx * dx + dz * dz);
        if (moved > 3.0) { travelled = 0; return; }                         // a teleport, not a stroke
        if (moved / delta < 0.5) { travelled = Math.min(travelled, 0.5 * STROKE); return; }
        boolean swimming = c.currentStanceName == StanceName.SWIM;
        double len = swimming ? STROKE : WADE_STEP;
        travelled += moved;
        if (travelled < len) return;
        travelled -= len;
        if (!swimming && c.waterSurfaceY - p.getY() < 0.15) return;          // ankle deep: no splash
        Vector3 at = new Vector3(p.getX(), c.waterSurfaceY, p.getZ());
        if (com.openworld.world.Splash.at(c, at, swimming ? 0.5 : 0.35,
                swimming ? Sound.SWIM_STROKE : Sound.SPLASH_SMALL, swimming ? -4f : -8f)) strokes++;
    }
}
