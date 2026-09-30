package com.openworld.world;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.carrier.vehicle.VehicleModels;
import com.openworld.character.CharacterInfo;
import com.openworld.net.NetworkManager;
import godot.annotation.Export;
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
import java.util.UUID;

/**
 * A PARKED VEHICLE a building holds (user, 2026-09-28: "for the car types in the yard / hospital / fire stations /
 * police station, generate a vehicle type as a placeholder or use an existing vehicle"): the fire engines in their bays,
 * the ambulance under the ER canopy, the patrol cars behind the police station, the truck at the yard's dock. Placed by
 * the scene builder at a building's {@code MARK_vehicle} marker that names a model ({@code vehicle = "FIE1"}); the
 * vehicle is an ordinary, drivable, damageable carrier from {@link VehicleModels}, unoccupied and parked.
 *
 * <p>A building is STREAMED (a cell loads and unloads), so the vehicle is NOT this node's child -- it would vanish from
 * under a player driving it away the moment the cell unloaded. It goes into the current scene, and a static registry
 * keyed by the marker's world position and model remembers it: a cell that streams in again spawns nothing while that
 * vehicle still exists (driven away or not), and spawns a fresh one once it has been destroyed or the scene changed.
 *
 * <p><b>Networking:</b> host-authoritative like the traffic: the host (or single player) spawns and announces it
 * ({@link NetworkManager#announceVehicleSpawn}, the {@link Vehicle#STREAMED_GROUP} baseline); a client spawns nothing
 * and gets the host's.
 */
@Script(className = "ParkedVehicle")
public class ParkedVehicle extends Node3D {
    /** The model's catalog id (VehicleModels): POC1, MPC1, AMB1, FIE1, LAT1, CRT1, KET1 ... */
    @Export public String vehicleId = "";
    @Export public String faction = "neutral";
    /** How far above the marker the body is set down (the suspension settles it). */
    @Export public double dropHeight = 0.3;

    private static final Map<String, Vehicle> SPAWNED = new HashMap<>();
    private static long sceneId = -1;

    @Register
    @Override
    public void _ready() {
        callDeferred(new StringName("spawn_now"));
    }

    /** Spawn the vehicle if this peer is authoritative and the one from an earlier load is gone. */
    @Register
    public void spawnNow() {
        if (!isInsideTree()) return;
        Node net = getNodeOrNull("/root/NetworkManager");
        NetworkManager nm = net instanceof NetworkManager n ? n : null;
        if (nm != null && nm.isNetworked() && !nm.isServer()) return;
        Node scene = getTree().getCurrentScene();
        if (scene == null) return;
        if (scene.getInstanceId() != sceneId) {
            SPAWNED.clear();
            sceneId = scene.getInstanceId();
        }
        Transform3D at = getGlobalTransform();
        Vector3 o = at.getOrigin();
        String key = String.format("%s@%.1f,%.1f,%.1f", vehicleId, o.getX(), o.getY(), o.getZ());
        Vehicle prev = SPAWNED.get(key);
        if (prev != null && GD.isInstanceValid(prev)) return;
        String path = VehicleModels.sceneOfId(vehicleId);
        if (path == null) {
            GD.pushWarning("ParkedVehicle: no vehicle model '" + vehicleId + "' at " + getPath());
            return;
        }
        Object loaded = GD.load(path);
        if (!(loaded instanceof PackedScene ps)) return;
        Node inst = ps.instantiate();
        if (!(inst instanceof Vehicle v)) {
            if (inst != null) inst.queueFree();
            return;
        }
        // own identity in code, never the scene's shared sub-resource (the shared-sub-resource rule)
        v.characterInfo = new CharacterInfo();
        v.characterInfo.characterId = UUID.randomUUID().toString();
        v.characterInfo.displayName = vehicleId;
        v.characterInfo.faction = faction;
        scene.addChild(v);
        v.setGlobalTransform(new Transform3D(at.getBasis().orthonormalized(), o.plus(new Vector3(0, dropHeight, 0))));
        v.addToGroup(new StringName(Vehicle.STREAMED_GROUP));
        v.addToGroup(new StringName(GROUP));
        if (nm != null) nm.announceVehicleSpawn(v);
        SPAWNED.put(key, v);
    }

    /** Every vehicle a marker spawned is in this group besides {@link Vehicle#STREAMED_GROUP} (which the network baseline
     *  needs): it is PLACED, not ambient traffic, so a traffic probe must not judge it by traffic's spawn rules. */
    public static final String GROUP = "parked_vehicle";

    /** The vehicle this marker spawned, if it still exists (probe readout). */
    @Register
    public Node spawnedNow() {
        Vector3 o = getGlobalTransform().getOrigin();
        Vehicle v = SPAWNED.get(String.format("%s@%.1f,%.1f,%.1f", vehicleId, o.getX(), o.getY(), o.getZ()));
        return v != null && GD.isInstanceValid(v) ? v : null;
    }
}
