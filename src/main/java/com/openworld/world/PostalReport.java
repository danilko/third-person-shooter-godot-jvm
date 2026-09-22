package com.openworld.world;

import godot.api.Camera3D;
import godot.api.Node;
import godot.api.ProjectSettings;
import godot.core.Vector3;
import godot.global.GD;

/**
 * THE BUG-REPORT LINE (PLAN.md 3.26 (d)): everything a developer needs to go where a player was, with no
 * screenshot --
 *
 * <pre>12-7-5 · Downtown | x -540.2 y 1.4 z 790.8 | facing 132 | zone island_3_4 (loaded) | road shuto_c1__2_F1 @ 312 m (2.1 m off) | night 0.00 | build 0.1</pre>
 *
 * The code comes from {@link PostalGrid}, the region from {@link Places#regionAt}, the streaming zone from the
 * nearest {@code island_*} road marker, and the road from {@link RoadMap}'s own lane snap, so every part is the
 * answer the game itself uses. {@code postal 12-7-5} / {@code tp x y z} in the debug console take the developer
 * straight back.
 */
public final class PostalReport {
    private PostalReport() {}

    /** "12-7-5 · Downtown" (region only where there is one). */
    public static String address(Vector3 at) {
        String code = PostalGrid.label(at.getX(), at.getZ());
        String region = Places.regionAt(at.getX(), at.getZ());
        if (region.isEmpty()) return code;
        return code + " · " + Character.toUpperCase(region.charAt(0)) + region.substring(1).replace('_', ' ');
    }

    public static String line(Node any, Vector3 at) {
        Places.bind(any);
        StringBuilder sb = new StringBuilder(address(at));
        sb.append(String.format(" | x %.1f y %.1f z %.1f", at.getX(), at.getY(), at.getZ()));
        Camera3D cam = any.getViewport() != null ? any.getViewport().getCamera3d() : null;
        if (cam != null) {
            Vector3 f = cam.getGlobalBasis().getZ().times(-1.0);
            double yaw = Math.toDegrees(Math.atan2(f.getX(), -f.getZ()));        // 0 = north, 90 = east
            sb.append(String.format(" | facing %.0f", (yaw + 360.0) % 360.0));
        }
        ZoneManager zm = ZoneManager.get();
        if (zm != null) {
            ZoneMarker best = null;
            double bd = Double.MAX_VALUE;
            for (ZoneMarker m : zm.getMarkers()) {
                if (m == null || !GD.isInstanceValid(m) || m.zone == null || m.zone.zoneId == null) continue;
                if (!m.zone.zoneId.startsWith("island_")) continue;
                Vector3 c = m.getGlobalPosition();
                double d = Math.hypot(c.getX() - at.getX(), c.getZ() - at.getZ());
                if (d < bd) { bd = d; best = m; }
            }
            if (best != null)
                sb.append(" | zone ").append(best.zone.zoneId).append(zm.isZoneLoaded(best) ? " (loaded)" : " (NOT loaded)");
        }
        RoadGraph g = RoadMap.graph();
        if (g != null) {
            java.util.List<RoadGraph.Snap> s = g.snaps(at.getX(), at.getY(), at.getZ(), 1.0);
            if (s != null && !s.isEmpty() && s.get(0).distance < 60.0)
                sb.append(String.format(" | road %s @ %.0f m (%.1f m off)", s.get(0).lane.id, s.get(0).offset,
                        s.get(0).distance));
        }
        DayNight dn = DayNight.get();
        if (dn != null) sb.append(String.format(" | night %.2f", DayNight.nightFactor()));
        Object v = ProjectSettings.getSetting("application/config/version", "dev");
        sb.append(" | build ").append(v == null || v.toString().isEmpty() ? "dev" : v.toString());
        return sb.toString();
    }
}
