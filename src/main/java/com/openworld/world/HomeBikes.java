package com.openworld.world;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.net.NetworkManager;
import godot.api.Node;
import godot.core.Transform3D;
import godot.core.Vector3;
import godot.global.GD;

import java.util.List;

/**
 * The safe house's BIKE ROW (PLAN.md 3.1b, user 2026-10-16: "add a bike to the home car park"): a scooter parked
 * beside the starting car, the second thing a player owns at home -- and, with {@code OW_TEST_BIKES=1}, every
 * motorcycle in a row next to it, so the bikes can be tried one after another while they are being tuned.
 *
 * <p>Derived at runtime like {@link Garage#ensureHome} (NOT in World.tscn or island_buildings.patch_start, which are
 * generated): from the starting car ({@code VehicleRoot}), the row stands nose-in beside it, each bike one
 * {@link #PITCH} along the car's side, on the first offset where every slot is clear of static geometry and other
 * vehicles and outside the garage's bay. Host / single player only: a client is sent the bikes like any vehicle.
 */
public final class HomeBikes {
    private HomeBikes() {}

    /** The marker node that says this scene has had its row (made once per world). */
    public static final String NODE = "HomeBikes";
    /** One bike every 1.1 m: a 駐輪場's pitch for motorcycles, handlebars (0.7-0.8 m) clear of each other. */
    static final double PITCH = 1.1;
    /** A slot's half extents (m): across, up, along -- the supersport's 2.1 m with a little room. */
    private static final double HALF_X = 0.4, HALF_Z = 1.15;

    static List<String> row() {
        return "1".equals(System.getenv("OW_TEST_BIKES"))
                ? List.of("SCT1", "POB1", "TRB1", "SSB1", "PMB1") : List.of("SCT1");
    }

    /** Park the row beside the starting car, once per world (no starting car or no clear row: none). */
    public static void ensure(Node scene) {
        if (scene == null || scene.getNodeOrNull(NODE) != null) return;
        if (!(scene.getNodeOrNull("VehicleRoot") instanceof Vehicle start)) return;
        if (scene.getNodeOrNull("/root/NetworkManager") instanceof NetworkManager nm && nm.isNetworked() && !nm.isServer()) return;
        Node mark = new Node();
        mark.setName(NODE);
        scene.addChild(mark);
        Garage garage = scene.getNodeOrNull("HomeGarage") instanceof Garage g ? g : null;
        Transform3D t = start.getGlobalTransform();
        godot.core.Basis basis = t.getBasis().orthonormalized();
        Vector3 side = basis.getColumn(0);
        List<String> ids = row();
        // nearest first, either side: the first bike 2 m from the car's centre (a car is ~1.7 m wide)
        for (int k = 0; k <= 20; k++) {
            for (int sign : new int[] {1, -1}) {
                double first = sign * (2.0 + 0.5 * k);
                if (!rowClear(start, garage, t, side, basis, first, sign, ids.size())) continue;
                for (int i = 0; i < ids.size(); i++) {
                    Vector3 at = t.getOrigin().plus(side.times((float) (first + sign * i * PITCH)));
                    Vehicle v = ParkedVehicle.place(scene, ids.get(i), "neutral", new Transform3D(basis, at), 0.3);
                    if (v != null && scene.getNodeOrNull("/root/NetworkManager") instanceof NetworkManager nm) nm.announceVehicleSpawn(v);
                }
                GD.print("HomeBikes: " + String.join(" ", ids) + " parked from " + String.format("%+.1f", first)
                        + " m beside the starting car");
                return;
            }
        }
        GD.print("HomeBikes: no clear row beside the starting car -- no bikes at home");
    }

    private static boolean rowClear(Vehicle start, Garage garage, Transform3D t, Vector3 side, godot.core.Basis basis,
                                    double first, int sign, int n) {
        var space = start.getWorld3d() != null ? start.getWorld3d().getDirectSpaceState() : null;
        for (int i = 0; i < n; i++) {
            Vector3 at = t.getOrigin().plus(side.times((float) (first + sign * i * PITCH)));
            if (garage != null && (garage.contains(at.plus(side.times(HALF_X))) || garage.contains(at.minus(side.times(HALF_X)))))
                return false;
            if (space == null) continue;
            godot.api.BoxShape3D box = new godot.api.BoxShape3D();
            box.setSize(new Vector3(HALF_X * 2, 1.2, HALF_Z * 2));
            godot.api.PhysicsShapeQueryParameters3D q = new godot.api.PhysicsShapeQueryParameters3D();
            q.setShape(box);
            q.setTransform(new Transform3D(basis, at.plus(new Vector3(0, 0.9, 0))));
            q.setCollisionMask(com.openworld.util.CollisionLayers.WORLD | com.openworld.util.CollisionLayers.VEHICLE);
            if (!space.intersectShape(q, 4).isEmpty()) return false;
        }
        return true;
    }
}
