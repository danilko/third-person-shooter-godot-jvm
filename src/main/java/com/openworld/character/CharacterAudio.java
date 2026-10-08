package com.openworld.character;

import com.openworld.audio.Sound;
import com.openworld.audio.Sounds;
import com.openworld.world.HittableBody;
import com.openworld.world.SurfaceType;

import godot.api.Camera3D;
import godot.api.Node;
import godot.api.PhysicsDirectSpaceState3D;
import godot.api.PhysicsRayQueryParameters3D;
import godot.api.RigidBody3D;
import godot.core.Dictionary;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

/**
 * A character's footsteps and its landing, from how the BODY moves (its position per physics tick and its floor
 * state), so the owner, an AI and a network puppet all step the same way with no message: a puppet's floor state is
 * the snapshot's airborne bit ({@link Character#isAirborneNow()}).
 *
 * <p>A step every {@link #stride} metres of ground covered (a run strides longer: {@code stride + 0.12 s * speed}).
 * What it sounds like is the floor under the foot, asked with one downward ray at the step (never per tick): a
 * {@link HittableBody}'s surface type, a vehicle or any rigid body = metal, the Terrain3D paint at the spot (grass,
 * soil and seabed = grass, sand = the crunchy snow take, cliff and the urban block ground = concrete), anything else =
 * concrete (roads, floors, platforms). Only within {@link #RANGE} of the camera; a seated, dead or swimming body is
 * silent. Engine-free state, called from {@code Character._physicsProcess} before the authority return.
 */
public final class CharacterAudio {
    /** Footsteps and landings are heard this far from the camera (m). */
    public static final double RANGE = 35.0;
    /** Metres per footstep at walking pace. */
    public double stride = 0.75;
    /** A fall faster than this (m/s down) lands with a thud. */
    public static final double LAND_SPEED = 3.0;

    private Vector3 last;
    private double travelled;
    private double vy;
    private boolean wasAirborne;
    private int steps, landings;

    /** Footsteps / landings played so far (probes). */
    public int steps() { return steps; }
    public int landings() { return landings; }

    public void tick(Character c, double delta) {
        Vector3 p = c.getGlobalPosition();
        Vector3 prev = last;
        last = p;
        if (prev == null || delta <= 0) return;
        if (c.currentVehicleNode != null || !c.isAlive() || c.inWater) {
            travelled = 0;
            wasAirborne = false;
            return;
        }
        double dx = p.getX() - prev.getX(), dz = p.getZ() - prev.getZ(), dy = p.getY() - prev.getY();
        double moved = Math.sqrt(dx * dx + dz * dz);
        if (moved > 3.0) { travelled = 0; return; }              // a teleport, not a walk
        boolean airborne = c.isAirborneNow();
        if (airborne) {
            vy = dy / delta;
            wasAirborne = true;
            return;
        }
        double speed = moved / delta;
        if (wasAirborne) {
            wasAirborne = false;
            if (-vy > LAND_SPEED && near(c, p)) {
                float vol = (float) Math.min(4.0, -12.0 + 2.0 * (-vy));   // a jump's landing is soft, a fall is loud
                Sounds.play3D(c, Sound.LAND, p, 3f, 0.1f, vol);
                landings++;
                travelled = 0;
                return;
            }
        }
        if (speed < 0.4) { travelled = Math.min(travelled, 0.5 * stride); return; }
        travelled += moved;
        double len = stride + 0.12 * speed;
        if (travelled < len) return;
        travelled -= len;
        if (!near(c, p)) return;
        float vol = (float) Math.max(-8.0, Math.min(2.0, -8.0 + 2.2 * speed));   // a sneak is quiet, a sprint is not
        Sounds.play3D(c, footstepFor(c, p), p, 2.5f, 0.08f, vol);
        steps++;
    }

    private static boolean near(Character c, Vector3 p) {
        var vp = c.getViewport();
        Camera3D cam = vp == null ? null : vp.getCamera3d();
        return cam != null && cam.getGlobalPosition().distanceTo(p) <= RANGE;
    }

    /** The footstep sound for the floor under {@code p}. */
    static Sound footstepFor(Character c, Vector3 p) {
        var w = c.getWorld3d();
        PhysicsDirectSpaceState3D space = w == null ? null : w.getDirectSpaceState();
        if (space == null) return Sound.FOOTSTEP_CONCRETE;
        godot.core.VariantArray<godot.core.RID> ex = new godot.core.VariantArray<>(godot.core.RID.class);
        ex.append(c.getRid());
        PhysicsRayQueryParameters3D q = PhysicsRayQueryParameters3D.create(p.plus(new Vector3(0, 0.3, 0)),
                p.plus(new Vector3(0, -0.6, 0)),
                com.openworld.util.CollisionLayers.WORLD | com.openworld.util.CollisionLayers.VEHICLE, ex);
        Dictionary<Object, Object> hit = space.intersectRay(q);
        Object col = hit.isEmpty() ? null : hit.get("collider");
        if (col instanceof HittableBody hb) {
            return switch (hb.resolveSurfaceType()) {
                case METAL -> Sound.FOOTSTEP_METAL;
                case WOOD -> Sound.FOOTSTEP_WOOD;
                default -> Sound.FOOTSTEP_CONCRETE;
            };
        }
        if (col instanceof RigidBody3D) return Sound.FOOTSTEP_METAL;          // standing on a car
        if (col instanceof Node n && n.isClass("Terrain3D")) return terrainStep(n, p);
        return Sound.FOOTSTEP_CONCRETE;
    }

    /** Terrain3D's paint at {@code p}: the base texture, or the overlay where it is blended over half in. */
    private static Sound terrainStep(Node terrain, Vector3 p) {
        Object data = terrain.get(new StringName("data"));
        if (!(data instanceof godot.api.Object d)) return Sound.FOOTSTEP_GRASS;
        Object t = d.call(new StringName("get_texture_id"), p);
        int id = 0;
        if (t instanceof Vector3 v) id = (int) Math.round(v.getZ() > 0.5 ? v.getY() : v.getX());
        return switch (id) {
            case 1, 4 -> Sound.FOOTSTEP_CONCRETE;     // cliff rock, the urban block ground
            case 2 -> Sound.FOOTSTEP_SNOW;            // sand: the crunchy take
            default -> Sound.FOOTSTEP_GRASS;          // grass, seabed, soil
        };
    }

    @SuppressWarnings("unused")
    private static void log(String s) { GD.print("[CharacterAudio] " + s); }
}
