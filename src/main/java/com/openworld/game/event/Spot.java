package com.openworld.game.event;

/** Where a {@link GameplayEvent} happened: a world position (Godot space, metres) and, when known, the place's id
 *  in the places record ("" otherwise). */
public record Spot(double x, double y, double z, String placeId) {

    public static final Spot NOWHERE = new Spot(0, 0, 0, "");

    public Spot {
        placeId = placeId == null ? "" : placeId;
    }

    public Spot(double x, double y, double z) { this(x, y, z, ""); }

    public double distanceTo(Spot o) {
        double dx = x - o.x, dy = y - o.y, dz = z - o.z;
        return Math.sqrt(dx * dx + dy * dy + dz * dz);
    }
}
