package com.openworld.world;

import com.openworld.character.Player;
import com.openworld.game.EventBus;
import com.openworld.game.PlayerRegistry;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.BaseMaterial3D;
import godot.api.CharacterBody3D;
import godot.api.GeometryInstance3D;
import godot.api.MeshInstance3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.PlaneMesh;
import godot.api.RigidBody3D;
import godot.api.StandardMaterial3D;
import godot.core.Color;
import godot.core.StringName;
import godot.core.Vector2;
import godot.core.Vector3;
import godot.global.GD;

import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * THE LOGIC WALL — the edge of the world, enforced in script rather than with a collider.
 *
 * <p>Baked from a {@code bounds_<id>} marker ({@code WorldBaker}); {@code size} gives the playable
 * square and {@code floor} the kill-Z. The island's sea floor deliberately reaches
 * {@code island_v3_terrain.SEABED_MARGIN} (288 m) FURTHER than this boundary, so the wall always
 * stands on real ground with more ground behind it.
 *
 * <p><b>Why not an invisible collider.</b> A ring of static walls collides with bullets, vehicles and
 * ragdolls as well as with the player, gives a body sliding along it no "leaving the area" moment,
 * and cannot recover a body that is already outside. A per-frame correction answers all three — the
 * same shape {@code ZoneManager.maintainTraffic} uses to reclaim a vehicle below {@code Y = -30}.
 *
 * <p><b>ONE physical rule: the hard wall</b> (PLAN.md P0 0.6, user decision 2026-09-16). Past
 * {@link #halfExtent} the position is clamped back and only the OUTWARD part of the velocity is
 * cancelled, so swimming home is unresisted. Nothing inside the wall is ever moved. There used to be
 * a soft band that pushed bodies inward, and a physical push nobody can see is indistinguishable from
 * a bug: it is exactly how P0 0.3's "invisible collision block" on DebugWorld's loop corner hid.
 *
 * <p><b>The band only WARNS.</b> Inside {@link #warnMargin} of the wall each locally-owned player gets
 * {@code EventBus.leavingArea(distanceToWall)} on entering the band and {@code returnedToArea} on
 * leaving it — edges, never per frame — and {@code ui.AreaWarning} shows it (Battlefield's "return to
 * the combat area"). Local per peer: every peer confines and warns its own player, so no message.
 *
 * <p><b>Cost.</b> Players every frame, off {@link PlayerRegistry}. Everything else in the
 * {@code "characters"} group — AI, vehicles — on a {@link #sweepInterval} tick: a car doing 30 m/s
 * covers 15 m in that window and is still turned round well before ground that does not exist.
 */
@Script(className = "WorldBounds")
public class WorldBounds extends Node3D {

    /** Half-extent of the playable square in X and Z, metres. The wall stands here. */
    @Export public float halfExtent = 2016f;

    public float getHalfExtent() { return halfExtent; }

    public void setHalfExtent(float v) { halfExtent = v; }

    /** Width of the WARNING band inside the wall, metres. No physics: it only tells the player. */
    @Export public float warnMargin = 80f;

    public float getWarnMargin() { return warnMargin; }

    public void setWarnMargin(float v) { warnMargin = v; }

    /**
     * Kill-Z. A body below this has left the world downward — through a hole, or off the seabed's
     * far edge — and is put back rather than fallen forever. The backstop for a defect.
     */
    @Export public float floorY = -64f;

    public float getFloorY() { return floorY; }

    public void setFloorY(float v) { floorY = v; }

    /**
     * UNDER THE GROUND (user, 2026-10-03: a rider was left under the island's terrain with no way back): a body whose
     * feet are more than this far (m) under the Terrain3D surface at its spot, for {@link #undergroundSeconds}, is
     * under the map -- nothing in this world is below its terrain (no tunnels, no basements; CLAUDE.md "No ground
     * below sea level"). 0 turns the check off.
     */
    @Export public float undergroundDepth = 1.0f;

    public float getUndergroundDepth() { return undergroundDepth; }

    public void setUndergroundDepth(float v) { undergroundDepth = v; }

    @Export public float undergroundSeconds = 0.5f;

    public float getUndergroundSeconds() { return undergroundSeconds; }

    public void setUndergroundSeconds(float v) { undergroundSeconds = v; }

    /** A body under the map is put back on the surface at the same spot (GTA's answer when you fall through the
     *  map): the topmost thing within this many metres over the terrain there (a road, a footway, a station floor),
     *  else the terrain. A bridge deck or a roof higher than that is not "the ground here". */
    static final double SURFACE_REACH = 8.0;

    /** Seconds between sweeps of everything that is not a player. */
    @Export public float sweepInterval = 0.5f;

    public float getSweepInterval() { return sweepInterval; }

    public void setSweepInterval(float v) { sweepInterval = v; }

    /** Draw the wall (red) and the warning band's inner edge (yellow) as translucent planes. */
    @Export public boolean showDebugVolume = false;

    public boolean getShowDebugVolume() { return showDebugVolume; }

    public void setShowDebugVolume(boolean v) {
        showDebugVolume = v;
        if (isInsideTree()) refreshDebugVolume();
    }

    /** Print each hard correction (throttled per body) and each player's warning edges. */
    @Export public boolean debugLog = false;

    public boolean getDebugLog() { return debugLog; }

    public void setDebugLog(boolean v) { debugLog = v; }

    private static final StringName CHARACTERS = new StringName("characters");
    private static final StringName PLAYER_SPAWN = new StringName("PlayerSpawn");
    private static final double LOG_THROTTLE_MS = 1000.0;

    private static WorldBounds instance;

    /** The live wall, or null in a scene without one. */
    public static WorldBounds get() { return instance; }

    private double sweepTimer = 0.0;
    /** Instance ids of the local players currently inside the warning band. */
    private final Set<Long> warned = new HashSet<>();
    private final Map<Long, Double> lastLogMs = new HashMap<>();
    private Node3D debugVolume;
    private int hardCorrections = 0;
    private int undergroundRescues = 0;
    private final Map<Long, Double> underSince = new HashMap<>();
    private Node terrain;
    private long terrainScene = -1;
    private int warningsEmitted = 0;
    private int returnsEmitted = 0;

    @Register
    @Override
    public void _ready() {
        instance = this;
        refreshDebugVolume();
    }

    @Register
    @Override
    public void _exitTree() {
        if (instance == this) instance = null;
        warned.clear();
        lastLogMs.clear();
        underSince.clear();
    }

    @Register
    @Override
    public void _physicsProcess(double delta) {
        List<Player> players = PlayerRegistry.getPlayers();
        for (Player p : players) {
            if (p == null || !GD.isInstanceValid(p)) continue;
            confine(p);
            if (p.isLocalOwnedPlayer()) updateWarning(p);
        }
        sweepTimer -= delta;
        if (sweepTimer > 0.0) return;
        sweepTimer = sweepInterval;
        if (getTree() == null) return;
        for (Node n : getTree().getNodesInGroup(CHARACTERS)) {
            if (n instanceof Node3D body && !(n instanceof Player p && players.contains(p))) confine(body);
        }
    }

    /**
     * Metres from {@code pos} to the nearer wall along X or Z, in the wall's own frame. Negative past
     * the wall. The one owner of "how far is the edge", read by the HUD warning too.
     */
    public double distanceToWall(Vector3 pos) {
        Vector3 c = getGlobalPosition();
        double ax = Math.abs(pos.getX() - c.getX()), az = Math.abs(pos.getZ() - c.getZ());
        return halfExtent - Math.max(ax, az);
    }

    /** Hard corrections applied since start — the gate reads it. */
    @Register
    public int hardCorrectionCount() { return hardCorrections; }

    @Register
    public int warningCount() { return warningsEmitted; }

    @Register
    public int returnCount() { return returnsEmitted; }

    /** Edge-triggered warning for one local player. */
    private void updateWarning(Player p) {
        long id = p.getInstanceId();
        double d = distanceToWall(p.getGlobalPosition());
        boolean inBand = warnMargin > 0f && d < warnMargin;
        boolean was = warned.contains(id);
        if (inBand == was) return;
        EventBus bus = getNodeOrNull("/root/EventBus") instanceof EventBus eb ? eb : null;
        if (inBand) {
            warned.add(id);
            warningsEmitted++;
            if (bus != null) bus.leavingArea.emit((float) d);
            if (debugLog) GD.print("WorldBounds: " + p.getName() + " is leaving the area (" + Math.round(d) + " m to the wall)");
        } else {
            warned.remove(id);
            returnsEmitted++;
            if (bus != null) bus.returnedToArea.emit();
            if (debugLog) GD.print("WorldBounds: " + p.getName() + " returned to the area");
        }
    }

    /**
     * One body, one frame. Returns true if it had to be moved. Per axis and only ever inward, so a body
     * running along the wall is corrected in X and left alone in Z.
     */
    private boolean confine(Node3D body) {
        Vector3 pos = body.getGlobalPosition();
        if (pos.getY() < floorY) {
            rescue(body);
            return true;
        }
        if (underground(body, pos)) return true;
        Vector3 c = getGlobalPosition();
        double px = pos.getX(), pz = pos.getZ();
        double dx = overshoot(px - c.getX()), dz = overshoot(pz - c.getZ());
        if (dx == 0.0 && dz == 0.0) return false;
        body.setGlobalPosition(new Vector3(px + dx, pos.getY(), pz + dz));
        cancelOutward(body, dx, dz);
        hardCorrections++;
        if (debugLog) {
            long id = body.getInstanceId();
            double now = godot.api.Time.INSTANCE.getTicksMsec();
            Double last = lastLogMs.get(id);
            if (last == null || now - last > LOG_THROTTLE_MS) {
                lastLogMs.put(id, now);
                GD.print("WorldBounds: turned back " + body.getName() + " at (" + Math.round(px) + ", "
                        + Math.round(pz) + ")" + (dx != 0.0 ? " x overshoot " + String.format("%.2f", Math.abs(dx)) : "")
                        + (dz != 0.0 ? " z overshoot " + String.format("%.2f", Math.abs(dz)) : ""));
            }
        }
        return true;
    }

    /** The Terrain3D surface height (m) at a world XZ, or NaN where there is none (no terrain, a hole, outside it). */
    @Register
    public double terrainHeight(double x, double z) {
        Node scene = getTree() != null ? getTree().getCurrentScene() : null;
        long sid = scene != null ? scene.getInstanceId() : 0;
        if (sid != terrainScene || (terrain != null && !GD.isInstanceValid(terrain))) {
            terrainScene = sid;
            terrain = scene != null ? scene.findChild("Terrain3D", true, false) : null;
        }
        if (terrain == null) return Double.NaN;
        Object data = terrain.get(new StringName("data"));
        if (!(data instanceof godot.api.Object d)) return Double.NaN;
        Object h = d.call(new StringName("get_height"), new Vector3(x, 0.0, z));
        return h instanceof Number n ? n.doubleValue() : Double.NaN;
    }

    /** Is this body under the map, and if it has been for long enough, deal with it. True when it was moved. */
    private boolean underground(Node3D body, Vector3 pos) {
        if (undergroundDepth <= 0f) return false;
        if (body instanceof com.openworld.character.Character ch && ch.currentVehicleNode != null) return false;
        long id = body.getInstanceId();
        double h = terrainHeight(pos.getX(), pos.getZ());
        if (Double.isNaN(h) || pos.getY() > h - undergroundDepth) {
            underSince.remove(id);
            return false;
        }
        double now = godot.api.Time.INSTANCE.getTicksMsec() / 1000.0;
        Double since = underSince.putIfAbsent(id, now);
        if (since == null || now - since < undergroundSeconds) return false;
        underSince.remove(id);
        undergroundRescues++;
        Vector3 to = surfaceAt(body, pos.getX(), h, pos.getZ());
        body.setGlobalPosition(to);
        cancelAll(body);
        GD.print("WorldBounds: " + body.getName() + " was under the map at (" + Math.round(pos.getX()) + ", "
                + Math.round(pos.getY()) + ", " + Math.round(pos.getZ()) + "): put back on the surface at y "
                + String.format("%.1f", to.getY()) + " [" + describe(body) + "]");
        return true;
    }

    /** What a rescued body is, for the log: a repeat rescue of one body says why it keeps going under. */
    private static String describe(Node3D body) {
        StringBuilder b = new StringBuilder(body.getClass().getSimpleName());
        if (body instanceof com.openworld.character.Character ch) {
            b.append(" id=").append(ch.getCharacterInfo() != null ? ch.getCharacterInfo().characterId : "?");
            b.append(" dead=").append(ch instanceof com.openworld.character.AICharacter ai && ai.isDead()).append(" phys=").append(ch.isPhysicsProcessing());
            b.append(" layer=").append(ch.getCollisionLayer()).append(" mask=").append(ch.getCollisionMask());
            if (ch.getController() != null) b.append(" ctrl=").append(ch.getController().getClass().getSimpleName());
            b.append(" vel=").append(ch.getVelocity());
        } else if (body instanceof godot.api.PhysicsBody3D pb) {
            b.append(" layer=").append(pb.getCollisionLayer());
        }
        return b.toString();
    }

    /** The place to stand at (x, z): the topmost collider within SURFACE_REACH over the terrain there, else the
     *  terrain itself. A bridge deck or a roof higher than that is not "the ground here". */
    private Vector3 surfaceAt(Node3D body, double x, double h, double z) {
        double lift = body instanceof RigidBody3D ? 1.0 : 0.15;
        godot.api.PhysicsDirectSpaceState3D sp = getWorld3d() != null ? getWorld3d().getDirectSpaceState() : null;
        if (sp != null) {
            godot.core.VariantArray<godot.core.RID> ex = new godot.core.VariantArray<>(godot.core.RID.class);
            if (body instanceof godot.api.CollisionObject3D co) ex.append(co.getRid());
            godot.api.PhysicsRayQueryParameters3D q = godot.api.PhysicsRayQueryParameters3D.create(
                    new Vector3(x, h + SURFACE_REACH, z), new Vector3(x, h - 0.5, z), com.openworld.util.CollisionLayers.WORLD, ex);
            godot.core.Dictionary<Object, Object> hit = sp.intersectRay(q);
            if (hit != null && !hit.isEmpty() && hit.get("position") instanceof Vector3 p) {
                return new Vector3(x, p.getY() + lift, z);
            }
        }
        return new Vector3(x, h + lift, z);
    }

    /** Bodies put back from under the map since start -- the gate reads it. */
    @Register
    public int undergroundRescueCount() { return undergroundRescues; }

    /** Inward correction for one axis (wall frame): the whole overshoot, else 0. */
    private double overshoot(double v) {
        double over = Math.abs(v) - halfExtent;
        if (over < 0.0) return 0.0;
        return (v >= 0.0 ? -1.0 : 1.0) * (over + 0.01);
    }

    /** Kill the outward part of the body's own velocity so it cannot build speed into the wall. */
    private static void cancelOutward(Node3D body, double dx, double dz) {
        if (body instanceof CharacterBody3D cb) {
            Vector3 v = cb.getVelocity();
            cb.setVelocity(new Vector3(clampSign(v.getX(), dx), v.getY(), clampSign(v.getZ(), dz)));
        } else if (body instanceof RigidBody3D rb) {
            Vector3 v = rb.getLinearVelocity();
            rb.setLinearVelocity(new Vector3(clampSign(v.getX(), dx), v.getY(), clampSign(v.getZ(), dz)));
        }
    }

    /** {@code v}, with any component pointing the opposite way to the correction removed. */
    private static double clampSign(double v, double correction) {
        if (correction > 0.0 && v < 0.0) return 0.0;
        if (correction < 0.0 && v > 0.0) return 0.0;
        return v;
    }

    /**
     * Put a body that fell out of the world back on the map: the scene's {@code PlayerSpawn}
     * marker when there is one, else the world origin at ground level.
     */
    private void rescue(Node3D body) {
        Node scene = getTree() != null ? getTree().getCurrentScene() : null;
        Node marker = scene != null ? scene.getNodeOrNull(new godot.core.NodePath(PLAYER_SPAWN.toString())) : null;
        Vector3 to = marker instanceof Node3D anchor
                ? anchor.getGlobalPosition().plus(new Vector3(0f, 2f, 0f))
                : new Vector3(0f, 4f, 0f);
        body.setGlobalPosition(to);
        cancelAll(body);
        GD.print("WorldBounds: rescued " + body.getName() + " from below " + floorY + " m");
    }

    private static void cancelAll(Node3D body) {
        Vector3 zero = Vector3.Companion.getZERO();
        if (body instanceof CharacterBody3D cb) {
            cb.setVelocity(zero);
            // A Character's fall speed is MovementController's own field: zeroing the body alone landed a
            // rescued body at the speed it fell at, with fall damage.
            if (cb.getNodeOrNull("MovementController")
                    instanceof com.openworld.movement.character.MovementController mc) mc.clearMotion();
        }
        else if (body instanceof RigidBody3D rb) { rb.setLinearVelocity(zero); rb.setAngularVelocity(zero); }
    }

    /**
     * Build or tear down the debug planes: four red walls at {@link #halfExtent} and four yellow ones
     * at the warning band's inner edge. Runtime-built children, never saved (no owner).
     */
    private void refreshDebugVolume() {
        if (debugVolume != null && GD.isInstanceValid(debugVolume)) {
            debugVolume.queueFree();
            debugVolume = null;
        }
        if (!showDebugVolume) return;
        debugVolume = new Node3D();
        debugVolume.setName(new StringName("BoundsDebugVolume"));
        addChild(debugVolume);
        addRing(halfExtent, new Color(1f, 0.1f, 0.1f, 0.25f));
        if (warnMargin > 0f) addRing(halfExtent - warnMargin, new Color(1f, 0.85f, 0.1f, 0.15f));
    }

    /** Height of the debug planes, centred on the wall node's Y. */
    private static final float DEBUG_HEIGHT = 400f;

    private void addRing(float half, Color color) {
        StandardMaterial3D mat = new StandardMaterial3D();
        mat.setTransparency(BaseMaterial3D.Transparency.ALPHA);
        mat.setShadingMode(BaseMaterial3D.ShadingMode.UNSHADED);
        mat.setCullMode(BaseMaterial3D.CullMode.DISABLED);
        mat.setAlbedo(color);
        for (int side = 0; side < 4; side++) {
            PlaneMesh plane = new PlaneMesh();
            plane.setSize(new Vector2(half * 2f, DEBUG_HEIGHT));
            plane.setOrientation(side < 2 ? PlaneMesh.Orientation.FACE_Z : PlaneMesh.Orientation.FACE_X);
            MeshInstance3D mi = new MeshInstance3D();
            mi.setMesh(plane);
            mi.setMaterialOverride(mat);
            mi.setCastShadowsSetting(GeometryInstance3D.ShadowCastingSetting.OFF);
            float s = (side % 2 == 0) ? 1f : -1f;
            mi.setPosition(side < 2 ? new Vector3(0f, 0f, s * half) : new Vector3(s * half, 0f, 0f));
            debugVolume.addChild(mi);
        }
    }
}
