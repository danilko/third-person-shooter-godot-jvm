package com.openworld.carrier.vehicle;

import java.util.List;

/**
 * The bounded list of vehicle scenes a client may be told to instance. {@code MSG_VEHICLE_SPAWN} carries an INDEX
 * into it, never a path (the same anti-arbitrary-resource rule as MSG_SPAWN's scene selector). Before this every
 * replicated vehicle was instanced from {@code Vehicle.tscn} on clients, whatever the host had spawned.
 *
 * <p>APPEND-ONLY: an index is on the wire.
 */
public final class VehicleModels {
    private VehicleModels() {}

    private static final String DIR = "res://src/main/resources/com/openworld/vehicle/";

    public static final List<String> SCENES = List.of(
            DIR + "Vehicle.tscn",      // 0: the box prototype - the BASE the cars inherit from; spawned by nothing now
            DIR + "SPC1.tscn",         // 1: SPC-1 sports coupe, the component-damage car
            DIR + "Motorcycle.tscn",
            DIR + "Boat.tscn",
            DIR + "Airplane.tscn",
            DIR + "KET1.tscn",         // 5: KET-1 kei truck (was PIT-1, the pack pickup, removed 2026-09-28)
            DIR + "POC1.tscn",         // 6: POC-1 patrol car, Crown class
            DIR + "MPC1.tscn",         // 7: MPC-1 mini patrol car (ミニパト)
            DIR + "CLC1.tscn",         // 8: CLC-1 classic coupe, AE86 size
            DIR + "KEC1.tscn",         // 9: KEC-1 kei car
            DIR + "TAX1.tscn",         // 10: TAX-1 taxi
            DIR + "CRT1.tscn",         // 11: CRT-1 crate truck (military / container)
            DIR + "AMB1.tscn",         // 12: AMB-1 ambulance (高規格救急車)
            DIR + "FIE1.tscn",         // 13: FIE-1 fire engine (消防ポンプ車)
            DIR + "LAT1.tscn",         // 14: LAT-1 ladder truck (はしご車)
            DIR + "FIJ1.tscn",         // 15: FIJ-1 fighter jet (flyable, inherits Airplane.tscn)
            DIR + "LIP1.tscn",         // 16: LIP-1 light plane (flyable, inherits Airplane.tscn)
            DIR + "WOB1.tscn",         // 17: WOB-1 harbour work boat (drivable, inherits Boat.tscn)
            DIR + "FIB1.tscn",         // 18: FIB-1 small fishing boat (drivable, inherits Boat.tscn)
            DIR + "COT1.tscn");        // 19: COT-1 container truck (tractor + 20 ft ISO box, one rigid body)
    // 5-14 are PLACEHOLDER block models (blender/tools/make_placeholder_cars.py), 15-18 placeholder craft
    // (blender/tools/make_placeholder_craft.py + tools/build_craft_scenes.py), until an artist models them.

    /** A model's scene by its catalog id ("POC1", "AMB1" ...), or null: what a MARK_vehicle marker names. */
    public static String sceneOfId(String id) {
        if (id == null || id.isBlank()) return null;
        String path = DIR + id.trim() + ".tscn";
        return SCENES.contains(path) ? path : null;
    }

    /** The default car - what a spawner with no scene of its own, and an unknown index, get. */
    public static final int DEFAULT = 1;
    public static final String DEFAULT_SCENE = DIR + "SPC1.tscn";

    /**
     * Civilian traffic, a Japanese street's mix (one entry = one twentieth): kei cars are the biggest share, then the
     * coupe, kei trucks, taxis, a few classics and the odd crate truck.
     */
    private static final String[] CIVILIAN = {
            DIR + "KEC1.tscn", DIR + "KEC1.tscn", DIR + "KEC1.tscn", DIR + "KEC1.tscn", DIR + "KEC1.tscn",
            DIR + "KEC1.tscn", DIR + "SPC1.tscn", DIR + "SPC1.tscn", DIR + "SPC1.tscn", DIR + "SPC1.tscn",
            DIR + "KET1.tscn", DIR + "KET1.tscn", DIR + "KET1.tscn", DIR + "TAX1.tscn", DIR + "TAX1.tscn",
            DIR + "TAX1.tscn", DIR + "CLC1.tscn", DIR + "CLC1.tscn", DIR + "CRT1.tscn", DIR + "KEC1.tscn"};
    /** Police: patrol cars, and one in four a mini patrol car. */
    private static final String[] POLICE = {DIR + "POC1.tscn", DIR + "POC1.tscn", DIR + "POC1.tscn", DIR + "MPC1.tscn"};

    /**
     * The car an ambient driver of {@code faction} gets, from {@code roll} in [0, 1): the police drive the police car,
     * everyone else a civilian car. Chosen on the host only - clients get the choice as the spawn's model index.
     */
    public static String trafficScene(String faction, double roll) {
        if ("police".equals(faction)) return POLICE[(int) Math.min(POLICE.length - 1, Math.max(0, roll) * POLICE.length)];
        if ("military".equals(faction)) return DIR + "CRT1.tscn";
        return CIVILIAN[(int) Math.min(CIVILIAN.length - 1, Math.max(0, roll) * CIVILIAN.length)];
    }

    /** The index of a scene path, or {@link #DEFAULT} for a scene not in the list. */
    public static int indexOf(String scenePath) {
        int i = scenePath == null ? -1 : SCENES.indexOf(scenePath);
        return i >= 0 ? i : DEFAULT;
    }

    /** The scene for an index off the wire; an out-of-range index is the default car. */
    public static String sceneOf(int index) {
        return index >= 0 && index < SCENES.size() ? SCENES.get(index) : SCENES.get(DEFAULT);
    }
}
