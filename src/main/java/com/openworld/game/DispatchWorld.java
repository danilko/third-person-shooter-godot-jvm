package com.openworld.game;

import com.openworld.character.Character;
import com.openworld.character.Player;
import com.openworld.util.CollisionLayers;
import com.openworld.world.ZoneManager;
import godot.api.Node;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.List;

import static com.openworld.game.EnforcementDispatch.*;

/**
 * The world queries of the dispatch: rays (a clear line at knee and chest, a clear ray, the ground, cover
 * overhead), the building over a point, the walk round a building to a door, whether a point is in any player's
 * view.
 *
 * <p>A part of {@link EnforcementDispatch} (PLAN.md P1e step 2, a move-only split): the state is the dispatch's
 * ({@code ed}), this holds the code.
 */
final class DispatchWorld {

    private final EnforcementDispatch ed;

    DispatchWorld(EnforcementDispatch ed) { this.ed = ed; }

    /** One world ray between two points (a helicopter's eye to a player's chest). */
    boolean clearRay(Vector3 from, Vector3 to) {
        if (ed.getViewport() == null || ed.getViewport().getWorld3d() == null) return true;
        var q = godot.api.PhysicsRayQueryParameters3D.create(from, to, CollisionLayers.WORLD,
                new godot.core.VariantArray<>(godot.core.RID.class));
        godot.core.Dictionary<Object, Object> hit = ed.getViewport().getWorld3d().getDirectSpaceState().intersectRay(q);
        return hit == null || hit.isEmpty();
    }

    /** The building whose roof is over this point (a ray up hits it within 25 m, its owner carries the `building`
     *  meta), or null outdoors. Cheap: one ray per player and per breaching unit, every tick. */
    Node buildingAround(Vector3 at) {
        if (ed.getViewport() == null || ed.getViewport().getWorld3d() == null) return null;
        var sp = ed.getViewport().getWorld3d().getDirectSpaceState();
        var q = godot.api.PhysicsRayQueryParameters3D.create(at.plus(new Vector3(0, 1.7, 0)), at.plus(new Vector3(0, 25.0, 0)),
                CollisionLayers.WORLD, new godot.core.VariantArray<>(godot.core.RID.class));
        godot.core.Dictionary<Object, Object> hit = sp.intersectRay(q);
        if (hit == null || hit.isEmpty() || !(hit.get("collider") instanceof Node n)) return null;
        StringName key = new StringName("building");
        for (Node x = n; x != null; x = x.getParent()) if (x.hasMeta(key)) return x;
        return null;
    }

    /** Every leg of a walk is clear of WORLD geometry (clearLine at knee and chest height). */
    boolean wayClear(Vector3 from, List<Vector3> way) {
        Vector3 a = from;
        for (Vector3 b : way) {
            if (!clearLine(a, b)) return false;
            a = b;
        }
        return true;
    }

    /** 2.5 m outside a door marker (its -Z points out), on the marker's height. */
    static Vector3 outsideOf(godot.api.Node3D door) {
        Vector3 o = door.getGlobalTransform().getBasis().getColumn(2).times(-1.0);
        o.setY(0);
        o = o.length() > 1e-3 ? o.normalized() : new Vector3(0, 0, 1);
        return door.getGlobalPosition().plus(o.times(2.5));
    }

    /**
     * From {@code from} to {@code to} (both outside the building): straight when nothing is in the way, else round
     * the building's footprint corners (meta `footprint_m`, its own frame, grown by {@link #CORNER_MARGIN}), the
     * shorter way round. A straight walk to a back door ran into the building's own wall and stayed there.
     * Returns the waypoints, {@code to} last.
     */
    List<Vector3> pathAround(Node building, Vector3 from, Vector3 to) {
        List<Vector3> path = new ArrayList<>();
        if (clearLine(from, to) || !(building instanceof godot.api.Node3D b)) { path.add(to); return path; }
        double hx = 0, hz = 0;
        if (b.getMeta(new StringName("building"), null) instanceof godot.core.Dictionary<?, ?> meta
                && meta.get("footprint_m") instanceof godot.core.VariantArray<?> fp && fp.size() >= 2) {
            hx = ((Number) fp.get(0)).doubleValue() / 2.0;
            hz = ((Number) fp.get(1)).doubleValue() / 2.0;
        }
        if (hx <= 0 || hz <= 0) { path.add(to); return path; }
        hx += CORNER_MARGIN;
        hz += CORNER_MARGIN;
        Vector3[] corner = {
                b.toGlobal(new Vector3(-hx, 0, -hz)), b.toGlobal(new Vector3(hx, 0, -hz)),
                b.toGlobal(new Vector3(hx, 0, hz)), b.toGlobal(new Vector3(-hx, 0, hz))};
        int ia = nearestCorner(corner, from), ib = nearestCorner(corner, to);
        List<Vector3> best = null;
        double bestLen = Double.MAX_VALUE;
        for (int dir : new int[] {1, -1}) {
            List<Vector3> p = new ArrayList<>();
            for (int i = ia; ; i = (i + dir + 4) % 4) {
                Vector3 q = corner[i];
                p.add(new Vector3(q.getX(), from.getY(), q.getZ()));
                if (i == ib) break;
            }
            p.add(to);
            double len = routeLength(from, p);
            if (len < bestLen) { bestLen = len; best = p; }
        }
        return best;
    }

    static int nearestCorner(Vector3[] corner, Vector3 at) {
        int k = 0;
        for (int i = 1; i < corner.length; i++) if (flat(corner[i], at) < flat(corner[k], at)) k = i;
        return k;
    }

    static double routeLength(Vector3 from, List<Vector3> path) {
        double len = 0;
        Vector3 a = from;
        for (Vector3 q : path) { len += flat(a, q); a = q; }
        return len;
    }

    void forceDoorsNear(Node n, Vector3 at, double reach) {
        for (Node c : n.getChildren()) {
            if (c instanceof com.openworld.world.Door d && d.getGlobalPosition().distanceTo(at) < reach) {
                if (d.isLocked()) { d.setLocked(false); ed.doorsForced++; }
                d.autoOpen = true;
            }
            if (c.getChildCount() > 0 && !(c instanceof com.openworld.character.Character)) forceDoorsNear(c, at, reach);
        }
    }

    /** Something on the WORLD layer straight above {@code at} within {@link #HELI_COVER_UP}. */
    boolean underCover(Vector3 at) {
        if (ed.getViewport() == null || ed.getViewport().getWorld3d() == null) return false;
        var sp = ed.getViewport().getWorld3d().getDirectSpaceState();
        var q = godot.api.PhysicsRayQueryParameters3D.create(at.plus(new Vector3(0, 0.9, 0)),
                at.plus(new Vector3(0, HELI_COVER_UP, 0)), CollisionLayers.WORLD,
                new godot.core.VariantArray<>(godot.core.RID.class));
        godot.core.Dictionary<Object, Object> hit = sp.intersectRay(q);
        return hit != null && !hit.isEmpty();
    }

    /** Nothing on the WORLD layer between the door and the player (the helicopter's own body excepted). */
    boolean clearShot(Vector3 from, Vector3 to, godot.api.CollisionObject3D self) {
        if (ed.getViewport() == null || ed.getViewport().getWorld3d() == null) return true;
        var sp = ed.getViewport().getWorld3d().getDirectSpaceState();
        godot.core.VariantArray<godot.core.RID> ex = new godot.core.VariantArray<>(godot.core.RID.class);
        ex.append(self.getRid());
        var q = godot.api.PhysicsRayQueryParameters3D.create(from, to, CollisionLayers.WORLD, ex);
        godot.core.Dictionary<Object, Object> hit = sp.intersectRay(q);
        return hit == null || hit.isEmpty();
    }

    /**
     * Nothing solid between a spot and the player at knee and chest height: an officer walks to the player along that
     * line when there is no navmesh to follow (DebugWorld), and on the island it keeps units off the far side of a
     * building block. Not line of SIGHT for the camera -- the spot is already out of view.
     */
    boolean clearLine(Vector3 from, Vector3 to) {
        if (ed.getViewport() == null || ed.getViewport().getWorld3d() == null) return true;
        var sp = ed.getViewport().getWorld3d().getDirectSpaceState();
        for (double h : new double[] {0.6, 1.4}) {
            var q = godot.api.PhysicsRayQueryParameters3D.create(from.plus(new Vector3(0, h, 0)),
                    to.plus(new Vector3(0, h, 0)), CollisionLayers.WORLD,
                    new godot.core.VariantArray<>(godot.core.RID.class));
            godot.core.Dictionary<Object, Object> hit = sp.intersectRay(q);
            if (hit != null && !hit.isEmpty()) return false;
        }
        return true;
    }

    /** The first WORLD surface straight down at (x, z) from 40 m over {@code nearY}, or null. */
    Vector3 ground(double x, double z, double nearY) {
        if (ed.getViewport() == null || ed.getViewport().getWorld3d() == null) return null;
        var sp = ed.getViewport().getWorld3d().getDirectSpaceState();
        var q = godot.api.PhysicsRayQueryParameters3D.create(new Vector3(x, nearY + 40.0, z),
                new Vector3(x, nearY - 40.0, z), CollisionLayers.WORLD, new godot.core.VariantArray<>(godot.core.RID.class));
        godot.core.Dictionary<Object, Object> hit = sp.intersectRay(q);
        return hit != null && !hit.isEmpty() && hit.get("position") instanceof Vector3 v ? v : null;
    }

    boolean inView(Vector3 p) {
        ZoneManager z = ed.zm();
        return z != null && z.inLocalView(p, 1e9);
    }

    static double flat(Vector3 a, Vector3 b) {
        double dx = a.getX() - b.getX(), dz = a.getZ() - b.getZ();
        return Math.sqrt(dx * dx + dz * dz);
    }

    static double nearestPlayer(Vector3 at) {
        double best = Double.MAX_VALUE;
        for (Player p : PlayerRegistry.getPlayers()) if (GD.isInstanceValid(p)) best = Math.min(best, flat(at, p.getGlobalPosition()));
        return best;
    }
}
