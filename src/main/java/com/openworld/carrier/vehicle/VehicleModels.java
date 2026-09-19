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
            DIR + "PIT1.tscn",         // 5: PIT-1 pickup truck (model from the elbolilloduro pack, CC0)
            DIR + "POC1.tscn");        // 6: POC-1 police car (same pack)

    /** The default car - what a spawner with no scene of its own, and an unknown index, get. */
    public static final int DEFAULT = 1;
    public static final String DEFAULT_SCENE = DIR + "SPC1.tscn";

    /** Civilian traffic: the coupe and the pickup, 60/40. */
    private static final String[] CIVILIAN = {DIR + "SPC1.tscn", DIR + "SPC1.tscn", DIR + "SPC1.tscn",
                                              DIR + "PIT1.tscn", DIR + "PIT1.tscn"};

    /**
     * The car an ambient driver of {@code faction} gets, from {@code roll} in [0, 1): the police drive the police car,
     * everyone else a civilian car. Chosen on the host only - clients get the choice as the spawn's model index.
     */
    public static String trafficScene(String faction, double roll) {
        if ("police".equals(faction)) return DIR + "POC1.tscn";
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
