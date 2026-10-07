package com.openworld.world;

import godot.api.NavigationMesh;
import godot.api.NavigationRegion3D;
import godot.api.NavigationServer3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.ResourceLoader;
import godot.core.RID;
import godot.core.StringName;
import godot.global.GD;

import java.util.HashMap;
import java.util.Map;

/**
 * BUILDING INTERIORS HAVE THEIR OWN NAVMESH, ON THEIR OWN MAP (PLAN.md 1d, user 2026-10-07: "use a navmesh if its
 * performance allows"). Measured before choosing ({@code tools/godot/bake_building_nav.gd}): one bake per building
 * TYPE, 1-13 KB (the department store 102 KB), 3-60 ms offline, a path query 5-60 us, adding the region ~0 ms; and
 * without it a unit dispatched into a konbini stalled 6.8 m from the player and none got into a police station.
 *
 * <ul>
 *   <li>The navmesh is baked offline per type into {@code buildings/nav/<Type>_nav.res} (the {@code _Shop} variant,
 *   door leaves left out: a door opens for whoever walks into it).</li>
 *   <li>Every enterable building ({@code _Shop} / {@code _Open}: exactly the variants that carry {@link Door}s) gets a
 *   {@link NavigationRegion3D} child the first time one of its doors is ready ({@link #attach}); a shut building
 *   gets nothing.</li>
 *   <li>The regions join ONE separate navigation map at the fine 0.175 m cell interiors need (a 1.1 m konbini aisle
 *   closes at the street map's 0.5 m), so the street map, its cell and its road-piece seams are untouched.
 *   Buildings never overlap, so one interior map holds them all.</li>
 *   <li>A unit's NavigationAgent3D is switched onto this map only while it stands inside a building that has a
 *   region ({@link #mapFor}), and back to the world map outside.</li>
 * </ul>
 */
public final class InteriorNav {
    private InteriorNav() {}

    public static final String DIR = "res://src/main/resources/com/openworld/world/buildings/nav/";
    public static final float CELL = 0.175f, CELL_HEIGHT = 0.1f;
    private static final StringName REGION = new StringName("InteriorNav");

    private static RID map;
    private static final Map<String, NavigationMesh> byType = new HashMap<>();
    private static final java.util.Set<String> missing = new java.util.HashSet<>();
    private static int attached;
    /** Off = no interior regions are attached and nothing switches onto the map (the control). */
    public static boolean enabled = true;

    /** The interior map, created on first use. */
    public static RID map() {
        if (map == null) {
            map = NavigationServer3D.INSTANCE.mapCreate();
            NavigationServer3D.INSTANCE.mapSetCellSize(map, CELL);
            NavigationServer3D.INSTANCE.mapSetCellHeight(map, CELL_HEIGHT);
            NavigationServer3D.INSTANCE.mapSetActive(map, true);
        }
        return map;
    }

    /** The building root above {@code n} (the node carrying the {@code building} meta), or null. */
    public static Node3D buildingOf(Node n) {
        StringName key = new StringName("building");
        for (Node x = n; x != null; x = x.getParent()) if (x instanceof Node3D b && x.hasMeta(key)) return b;
        return null;
    }

    /** Give {@code building} its interior region, once; nothing when its type has no baked navmesh. */
    public static void attach(Node3D building) {
        if (!enabled || building == null || building.getNodeOrNull(REGION.toString()) != null) return;
        String type = typeOf(building);
        if (type == null || missing.contains(type)) return;
        NavigationMesh nm = byType.get(type);
        if (nm == null) {
            String path = DIR + type + "_nav.res";
            if (!ResourceLoader.INSTANCE.exists(path, "")) { missing.add(type); return; }
            if (!(GD.load(path) instanceof NavigationMesh m)) { missing.add(type); return; }
            nm = m;
            byType.put(type, nm);
        }
        NavigationRegion3D r = new NavigationRegion3D();
        r.setName(REGION);
        r.setNavigationMesh(nm);
        building.addChild(r);
        r.setNavigationMap(map());
        attached++;
    }

    /** Is this point on an interior navmesh (within 0.6 m in plan, 1 m in height)? One map query. */
    public static boolean onMesh(godot.core.Vector3 p) {
        if (map == null) return false;
        godot.core.Vector3 q = NavigationServer3D.INSTANCE.mapGetClosestPoint(map, p);
        double dx = q.getX() - p.getX(), dz = q.getZ() - p.getZ();
        return dx * dx + dz * dz < 0.36 && Math.abs(q.getY() - p.getY()) < 1.0;
    }

    /** Is this RID the interior map? */
    public static boolean isInteriorMap(RID r) { return map != null && map.equals(r); }

    /** True when this building has its interior region. */
    public static boolean has(Node building) {
        return building != null && GD.isInstanceValid(building) && building.getNodeOrNull(REGION.toString()) != null;
    }

    /** The base type of a placed building: its scene's file stem without the _Shop / _Open variant suffix. */
    static String typeOf(Node3D building) {
        String p = building.getSceneFilePath();
        if (p == null || p.isEmpty()) p = building.getName().toString();
        String stem = p.substring(p.lastIndexOf('/') + 1).replace(".tscn", "").replace(".scn", "");
        if (stem.endsWith("_Shop")) return stem.substring(0, stem.length() - 5);
        if (stem.endsWith("_Open")) return stem.substring(0, stem.length() - 5);
        return null;    // a shut building: no interior to walk
    }

    /** Probe readout: interior regions attached this run. */
    public static int attachedCount() { return attached; }

    /** Engine teardown (GameManager._exitTree): free the map and the cached meshes. */
    public static void clear() {
        if (map != null) { NavigationServer3D.INSTANCE.freeRid(map); map = null; }
        byType.clear();
        missing.clear();
    }
}
