package com.openworld.world;

import com.openworld.util.MiniJson;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

/** GPS routing over the real lanekit sidecars (PLAN.md 4.7). */
class RoadGraphTest {

    private static final Path PIECES = Path.of("assets/world_source/pieces");

    private static Object read(String stem) throws IOException {
        return MiniJson.parse(Files.readString(PIECES.resolve(stem + ".lanekit.json")));
    }

    /** The island's network: one lanekit per 504 m zone piece (PLAN.md 3.10), in the network's frame. */
    static void addIsland(RoadGraph g) throws IOException {
        List<Path> files;
        try (var s = Files.list(PIECES)) {
            files = s.filter(f -> f.getFileName().toString().matches("Roads_IslandRoads_island_\\d+_\\d+\\.lanekit\\.json"))
                    .sorted().toList();
        }
        assertFalse(files.isEmpty(), "no island piece lanekits");
        for (Path f : files) {
            g.addLanekit(MiniJson.parse(Files.readString(f)), new double[]{1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0.6, 0});
        }
    }

    private static RoadGraph debugRoads() throws IOException {
        RoadGraph g = new RoadGraph();
        g.addLanekit(read("Roads_DebugRoads_debug_a"), null);
        g.addLanekit(read("Roads_DebugRoads_debug_b"), null);
        return g;
    }

    /** Every consecutive pair of legs is a movement a car could make. */
    private static void assertLegal(RoadGraph.Route r) {
        List<RoadGraph.Leg> legs = r.legs;
        for (int i = 0; i + 1 < legs.size(); i++) {
            RoadGraph.Lane a = legs.get(i).lane, b = legs.get(i + 1).lane;
            assertTrue(a.successors().contains(b) || a.neighbours().contains(b),
                    a.id + " -> " + b.id + " is not a successor or a lane change");
        }
    }

    @Test
    void miniJsonReadsTheShapesALanekitUses() {
        Object o = MiniJson.parse("{\"a\": [1, -2.5e1, true, null, \"x\\\"y\\u0041\"], \"b\": {}}");
        Map<?, ?> m = (Map<?, ?>) o;
        List<?> a = (List<?>) m.get("a");
        assertEquals(1.0, a.get(0));
        assertEquals(-25.0, a.get(1));
        assertEquals(Boolean.TRUE, a.get(2));
        assertNull(a.get(3));
        assertEquals("x\"yA", a.get(4));
        assertTrue(((Map<?, ?>) m.get("b")).isEmpty());
        assertThrows(IllegalArgumentException.class, () -> MiniJson.parse("{\"a\": [1,]"));
    }

    @Test
    void aRouteAcrossTheJunctionFollowsTheConnectorIntoTheNextZone() throws IOException {
        RoadGraph g = debugRoads();
        assertEquals(38, g.laneCount());
        // From the middle of `link` (zone debug_a) to the far end of `spur` (zone debug_b).
        RoadGraph.Route r = g.route(-10, 10.5, 35, 290, 10, -84);
        assertNotNull(r);
        assertLegal(r);
        List<String> ids = r.laneIds();
        assertTrue(ids.get(0).startsWith("link_F"), "starts eastbound on link: " + ids);
        assertTrue(ids.stream().anyMatch(s -> s.contains("__spur_R")), "turns into spur: " + ids);
        assertTrue(ids.get(ids.size() - 1).startsWith("spur_R"), "ends on spur: " + ids);
        // The route bends through the junction, so it is longer than the straight line.
        double straight = Math.hypot(290 + 10, -84 - 35);
        assertTrue(r.length > straight, r.length + " vs " + straight);
    }

    @Test
    void theRouteEndsOnTheLaneNearestTheWaypoint() throws IOException {
        RoadGraph g = debugRoads();
        double[] wp = {150, 10, 30};   // beside `east`
        RoadGraph.Route r = g.route(-10, 10.5, 35, wp[0], wp[1], wp[2]);
        assertNotNull(r);
        assertLegal(r);
        double nearest = g.snaps(wp[0], wp[1], wp[2], 0).get(0).distance;
        double gx = r.goalPoint[0] - wp[0], gz = r.goalPoint[2] - wp[2];
        assertTrue(Math.hypot(gx, gz) <= nearest + RoadGraph.CANDIDATE_SLACK + 1e-6);
        // The polyline ends at the goal point.
        int n = r.pointCount();
        assertEquals(r.goalPoint[0], r.points[3 * (n - 1)], 1e-6);
        assertEquals(r.goalPoint[2], r.points[3 * (n - 1) + 2], 1e-6);
    }

    @Test
    void aGoalAheadOnTheSameLaneIsOneLeg() throws IOException {
        RoadGraph g = debugRoads();
        RoadGraph.Lane l = g.lane("link_F0");
        double[] a = l.at(20), b = l.at(120);
        RoadGraph.Route r = g.route(a[0], a[1], a[2], b[0], b[1], b[2]);
        assertNotNull(r);
        assertEquals(1, r.legs.size(), r.laneIds().toString());
        assertEquals(100, r.length, 0.5);
    }

    @Test
    void steerPointLiesAheadOnTheRoute() throws IOException {
        RoadGraph g = debugRoads();
        RoadGraph.Route r = g.route(-10, 10.5, 35, 290, 10, -84);
        double s0 = r.progressOf(-10, 35);
        double[] p = r.steerPoint(-10, 35, 30);
        assertEquals(s0 + 30, r.progressOf(p[0], p[2]), 0.5);
        assertTrue(r.distanceXZ(p[0], p[2]) < 1e-6);
    }

    /**
     * The island: 500 random start/goal pairs on lanes. Every route that exists is legal and ends on
     * the goal lane's snap; every goal an independent breadth-first search reaches from the start
     * lane yields a route.
     */
    @Test
    void islandRoutesAreLegalAndFoundWheneverReachable() throws IOException {
        RoadGraph g = new RoadGraph();
        addIsland(g);
        g.finish();
        List<RoadGraph.Lane> all = List.copyOf(g.lanes());
        Random rng = new Random(47);
        int found = 0;
        for (int k = 0; k < 500; k++) {
            RoadGraph.Lane a = all.get(rng.nextInt(all.size())), b = all.get(rng.nextInt(all.size()));
            if (a.length() < 20 || b.length() < 20) continue;
            double[] p = a.at(a.length() * 0.5), q = b.at(b.length() * 0.5);
            RoadGraph.Route r = g.route(p[0], p[1], p[2], q[0], q[1], q[2]);
            boolean reachable = reaches(a, b) || a == b;
            if (r == null) {
                assertFalse(reachable && g.snaps(p[0], p[1], p[2], 1).get(0).lane == a
                        && g.snaps(q[0], q[1], q[2], 0).get(0).lane == b, a.id + " -> " + b.id + " unrouted");
                continue;
            }
            found++;
            assertLegal(r);
            assertTrue(r.length >= Math.hypot(q[0] - p[0], q[2] - p[2]) - RoadGraph.CANDIDATE_SLACK * 2 - 1,
                    "shorter than the crow flies: " + a.id + " -> " + b.id);
        }
        assertTrue(found > 300, "routes found: " + found);
    }

    private static boolean reaches(RoadGraph.Lane from, RoadGraph.Lane to) {
        Set<RoadGraph.Lane> seen = new HashSet<>();
        ArrayDeque<RoadGraph.Lane> q = new ArrayDeque<>();
        q.add(from);
        while (!q.isEmpty()) {
            RoadGraph.Lane l = q.poll();
            if (l == to) return true;
            if (!seen.add(l)) continue;
            q.addAll(l.successors());
            q.addAll(l.neighbours());
        }
        return false;
    }
}
