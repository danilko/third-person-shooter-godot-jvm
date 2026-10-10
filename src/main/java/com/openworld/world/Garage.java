package com.openworld.world;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.character.CharacterInfo;
import com.openworld.character.Player;
import com.openworld.game.profile.PlayerProfile;
import com.openworld.game.profile.Profiles;
import com.openworld.game.profile.VehicleInstanceData;
import com.openworld.net.NetworkManager;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.PackedScene;
import godot.core.StringName;
import godot.core.Transform3D;
import godot.core.Vector3;
import godot.global.GD;

import java.util.HashMap;
import java.util.Map;

/**
 * The safe house's GARAGE (PLAN.md 1.4 / F4, GTA San Andreas' rule): drive a car into the bay, get out, and it is
 * YOURS -- recorded in your {@code PlayerProfile} (model, its id -- which is what its paint is derived from --,
 * condition, the garage), kept out of streaming reclaim ({@link #OWNED_GROUP}), and put back in the bay the next time
 * the world loads. Driven out, it stays yours while it exists; lost in the world (reclaimed, wrecked), the profile
 * keeps the row with no garage. One car per bay: a new car parked there replaces the old row.
 *
 * <p><b>Where it is.</b> Not authored in World.tscn (a generated scene; island_buildings.patch_start owns the start):
 * the bay is DERIVED from that generator's own output -- the starting car ({@code VehicleRoot}), parked nose-in in a
 * car-park bay -- as the neighbouring bay one {@link #BAY_PITCH} along the car's side, checked clear of static geometry
 * at runtime (else the other side, else two bays over). {@link #ensureHome} creates it once per world.
 *
 * <p><b>Authority.</b> The host stores and restores (a client's car is stored into the host's session copy of the
 * client's profile, which MSG_PROFILE carries home). Restoring is for THIS machine's own profile: a co-op guest's
 * garage cars come back when they host. A restored car is announced to clients like any spawned vehicle.
 */
@Script(className = "Garage")
public class Garage extends Node3D {

    public static final String OWNED_GROUP = "owned_vehicle";
    public static final String HOME = "home";
    /** A car park bay's width (ParkingLot4 / 8: 2.5 m). */
    public static final double BAY_PITCH = 2.5;
    /** The bay's half extents (m): across, up, along -- a car's footprint with room to stop crooked. */
    private static final double HALF_X = 1.6, HALF_Y = 2.0, HALF_Z = 3.2;
    private static final double STOPPED = 0.6;

    public String garageId = HOME;
    private double tickIn;
    private boolean restored;
    /** Car instance id -> the player last seen driving it inside the bay. */
    private final Map<Long, Player> driverInside = new HashMap<>();
    private int stores, restores;

    /** Create the home garage beside the starting car, once per world (no starting car: no garage). */
    public static Garage ensureHome(Node scene) {
        if (scene == null) return null;
        if (scene.getNodeOrNull("HomeGarage") instanceof Garage g) return g;
        if (!(scene.getNodeOrNull("VehicleRoot") instanceof Vehicle start)) return null;
        Transform3D t = start.getGlobalTransform();
        Vector3 side = t.getBasis().getColumn(0).normalized();
        Garage g = new Garage();
        g.setName("HomeGarage");
        scene.addChild(g);
        for (double off : new double[] {BAY_PITCH, -BAY_PITCH, 2 * BAY_PITCH, -2 * BAY_PITCH}) {
            Vector3 at = t.getOrigin().plus(side.times((float) off));
            if (g.clear(at, t)) {
                g.setGlobalTransform(new Transform3D(t.getBasis().orthonormalized(), at));
                GD.print("Garage: home bay " + String.format("%+.1f", off) + " m beside the starting car at " + at);
                return g;
            }
        }
        GD.print("Garage: no clear bay beside the starting car -- no home garage");
        g.queueFree();
        return null;
    }

    /**
     * The bay is told by the WORLD (minimal HUD): a painted yellow outline on the ground, the way a reserved space is
     * marked. Four unshaded strips, no collision; cosmetic, so built on every peer.
     */
    @Register
    @Override
    public void _ready() {
        godot.api.StandardMaterial3D paint = new godot.api.StandardMaterial3D();
        paint.setAlbedo(new godot.core.Color(0.95, 0.78, 0.12, 1.0));
        paint.setShadingMode(godot.api.BaseMaterial3D.ShadingMode.UNSHADED);
        double w = 0.12, x = HALF_X - 0.2, z = HALF_Z - 0.4;
        double[][] strips = {{-x, 0, w, 2 * z}, {x, 0, w, 2 * z}, {0, -z, 2 * x + w, w}, {0, z, 2 * x + w, w}};
        for (double[] s : strips) {
            godot.api.BoxMesh m = new godot.api.BoxMesh();
            m.setSize(new Vector3(s[2], 0.01, s[3]));
            m.setMaterial(paint);
            godot.api.MeshInstance3D mi = new godot.api.MeshInstance3D();
            mi.setMesh(m);
            mi.setCastShadowsSetting(godot.api.GeometryInstance3D.ShadowCastingSetting.OFF);
            mi.setPosition(new Vector3(s[0], 0.03, s[1]));
            addChild(mi);
        }
    }

    /** No static geometry (or another car) in the bay's box, 0.3 m above the ground. */
    private boolean clear(Vector3 at, Transform3D frame) {
        var space = getWorld3d() != null ? getWorld3d().getDirectSpaceState() : null;
        if (space == null) return true;
        godot.api.BoxShape3D box = new godot.api.BoxShape3D();
        box.setSize(new Vector3(HALF_X * 2 - 0.4, 1.2, HALF_Z * 2 - 0.6));
        godot.api.PhysicsShapeQueryParameters3D q = new godot.api.PhysicsShapeQueryParameters3D();
        q.setShape(box);
        q.setTransform(new Transform3D(frame.getBasis().orthonormalized(), at.plus(new Vector3(0, 0.9, 0))));
        q.setCollisionMask(com.openworld.util.CollisionLayers.WORLD | com.openworld.util.CollisionLayers.VEHICLE);
        return space.intersectShape(q, 4).isEmpty();
    }

    /** Whether {@code p} (world) lies in the bay. */
    public boolean contains(Vector3 p) {
        Vector3 l = getGlobalTransform().affineInverse().times(p);
        return Math.abs(l.getX()) <= HALF_X && Math.abs(l.getY()) <= HALF_Y && Math.abs(l.getZ()) <= HALF_Z;
    }

    private boolean authority() {
        return !(getNodeOrNull("/root/NetworkManager") instanceof NetworkManager n) || !n.isNetworked() || n.isServer();
    }

    @Register
    @Override
    public void _physicsProcess(double delta) {
        if ((tickIn -= delta) > 0) return;
        tickIn = 0.5;
        if (!authority()) return;
        if (!restored) {
            restored = true;
            restore();
        }
        for (Node n : getTree().getNodesInGroup(new StringName("characters"))) {
            if (!(n instanceof Vehicle v) || !GD.isInstanceValid(v) || v.getCharacterInfo() == null) continue;
            long key = v.getInstanceId();
            boolean inside = contains(v.getGlobalPosition());
            if (!inside) {
                driverInside.remove(key);
                VehicleInstanceData row = rowOf(v);
                if (row != null && garageId.equals(row.garageId)) {   // driven out: still yours, not in the garage
                    row.garageId = "";
                    ownerOf(row).touch();
                }
                continue;
            }
            if (v.getOccupant() instanceof Player p) { driverInside.put(key, p); continue; }
            Player last = driverInside.get(key);
            if (last == null || !GD.isInstanceValid(last) || v.getOccupant() != null
                    || v.getLinearVelocity().length() > STOPPED) continue;
            driverInside.remove(key);
            store(v, last);
        }
    }

    /** Record {@code v} as {@code owner}'s car in this garage (one car per bay: an older row here is let go). */
    public void store(Vehicle v, Player owner) {
        PlayerProfile prof = Profiles.of(owner);
        if (prof == null || v.getSceneFilePath().isEmpty()) return;
        String id = v.getCharacterInfo().characterId;
        prof.vehicles.removeIf(x -> garageId.equals(x.garageId) && !x.instanceId.equals(id));
        VehicleInstanceData row = prof.vehicle(id);
        if (row == null) {
            row = new VehicleInstanceData();
            row.instanceId = id;
            prof.vehicles.add(row);
        }
        row.model = v.getSceneFilePath();
        row.garageId = garageId;
        row.condition = condition(v);
        prof.touch();
        v.addToGroup(new StringName(OWNED_GROUP));
        stores++;
        GD.print("Garage: " + row.model.substring(row.model.lastIndexOf('/') + 1) + " " + id + " kept in '"
                + garageId + "' for " + prof.playerId + String.format(" (condition %.2f)", row.condition));
    }

    private static double condition(Vehicle v) {
        return v.getNodeOrNull("Health") instanceof com.openworld.character.Health h && h.maxHealth > 0
                ? Math.max(0.0, Math.min(1.0, h.getCurrentHealth() / h.maxHealth)) : 1.0;
    }

    /** The profile row (any profile this machine holds) for car {@code v}, or null. */
    private static VehicleInstanceData rowOf(Vehicle v) {
        if (!v.isInGroup(new StringName(OWNED_GROUP)) || v.getCharacterInfo() == null) return null;
        String id = v.getCharacterInfo().characterId;
        VehicleInstanceData r = Profiles.local().vehicle(id);
        if (r != null) return r;
        for (PlayerProfile p : Profiles.remotes().values()) if ((r = p.vehicle(id)) != null) return r;
        return null;
    }

    private static PlayerProfile ownerOf(VehicleInstanceData row) {
        if (Profiles.local().vehicles.contains(row)) return Profiles.local();
        for (PlayerProfile p : Profiles.remotes().values()) if (p.vehicles.contains(row)) return p;
        return Profiles.local();
    }

    /** Put this machine's own car for this garage back in the bay (once per world). */
    private void restore() {
        Node scene = getTree().getCurrentScene();
        if (scene == null) return;
        for (VehicleInstanceData row : Profiles.local().vehicles) {
            if (!garageId.equals(row.garageId) || alive(row.instanceId)) continue;
            if (!(GD.load(row.model) instanceof PackedScene ps) || !(ps.instantiate() instanceof Vehicle v)) {
                GD.print("Garage: cannot restore '" + row.model + "'");
                continue;
            }
            // own identity in code (the shared-sub-resource rule); the id is the car's: its paint is derived from it
            v.characterInfo = new CharacterInfo();
            v.characterInfo.characterId = row.instanceId;
            v.characterInfo.displayName = row.model.substring(row.model.lastIndexOf('/') + 1).replace(".tscn", "");
            scene.addChild(v);
            v.setGlobalTransform(new Transform3D(getGlobalTransform().getBasis(),
                    getGlobalTransform().getOrigin().plus(new Vector3(0, 0.3, 0))));
            v.addToGroup(new StringName(OWNED_GROUP));
            if (row.condition < 1.0 && v.getNodeOrNull("Health") instanceof com.openworld.character.Health h)
                h.applyReplicatedHealth((float) (h.maxHealth * Math.max(0.05, row.condition)));
            if (getNodeOrNull("/root/NetworkManager") instanceof NetworkManager nm) nm.announceVehicleSpawn(v);
            restores++;
            GD.print("Garage: restored " + v.characterInfo.displayName + " " + row.instanceId + " to '" + garageId + "'");
            break;   // one car per bay
        }
    }

    private boolean alive(String characterId) {
        for (Node n : getTree().getNodesInGroup(new StringName("characters")))
            if (n instanceof Vehicle v && v.getCharacterInfo() != null && characterId.equals(v.getCharacterInfo().characterId))
                return true;
        return false;
    }

    /** True for a car someone owns: streaming must never reclaim it (ZoneManager, ParkedVehicle). */
    public static boolean owned(Node n) {
        return n != null && n.isInGroup(new StringName(OWNED_GROUP));
    }

    // ── probe readouts ──
    @Register public int storesNow() { return stores; }
    @Register public int restoresNow() { return restores; }
    @Register public boolean containsNow(Vector3 p) { return contains(p); }
}
