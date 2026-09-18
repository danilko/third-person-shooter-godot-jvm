package com.openworld.world;

import com.openworld.util.MiniJson;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

import static org.junit.jupiter.api.Assertions.*;

/** The baked road map (PLAN.md 4.7b): the cell index, the picture and the file, on the island. */
class RoadMapBakeTest {

    /** World.tscn's WorldBounds: centre at the origin, half extent 2160 m. */
    private static final double MIN = -2160, SIZE = 4320;

    private static RoadGraph island;

    @BeforeAll
    static void load() throws IOException {
        island = new RoadGraph();
        RoadGraphTest.addIsland(island);
        island.finish();
        long t0 = System.nanoTime();
        island.setIndex(RoadIndex.build(island, MIN, MIN, SIZE, RoadIndex.DEFAULT_CELL));
        System.out.printf("index built in %.0f ms%n", (System.nanoTime() - t0) / 1e6);
    }

    private static List<String> ids(List<RoadGraph.Snap> s) {
        List<String> out = new ArrayList<>();
        for (RoadGraph.Snap x : s) out.add(x.lane.id + String.format("@%.6f", x.distance));
        return out;
    }

    /** Every point on the map, road or sea, snaps through the index exactly as through a full scan. */
    @Test
    void theIndexAgreesWithAFullScanEverywhere() {
        Random rng = new Random(5);
        int biggest = 0;
        for (int k = 0; k < 4000; k++) {
            double x = MIN + rng.nextDouble() * SIZE, z = MIN + rng.nextDouble() * SIZE;
            double y = -5 + rng.nextDouble() * 80;
            for (double yw : new double[]{0, 1}) {
                List<String> a = ids(island.snaps(x, y, z, yw)), b = ids(island.snapsBrute(x, y, z, yw));
                a.sort(null); b.sort(null);
                assertEquals(b, a, "at (" + x + ", " + y + ", " + z + ") yWeight " + yw);
            }
            biggest = Math.max(biggest, island.index().candidates(x, z).size());
        }
        // The point of the index: a cell names a few lanes, not the network.
        assertTrue(biggest < island.laneCount() / 2, "largest cell " + biggest + " of " + island.laneCount());
    }

    /** A snap on a lane sample is on the road in the picture; 60 m off every road is not. */
    @Test
    void thePictureIsTheRoad() {
        int px = RoadRaster.edgeFor(SIZE);
        assertEquals(RoadRaster.MAX_PX, px);
        byte[] a = RoadRaster.coverage(island, MIN, MIN, SIZE, px);
        double mpp = SIZE / px;
        int on = 0, total = 0;
        for (RoadGraph.Lane l : island.lanes()) {
            for (int i = 0; i < l.x.length; i++) {
                int c = (int) ((l.x[i] - MIN) / mpp), r = (int) ((l.z[i] - MIN) / mpp);
                total++;
                if ((a[r * px + c] & 0xff) == 255) on++;
            }
        }
        assertEquals(total, on, "lane samples on a fully covered pixel");
        Random rng = new Random(9);
        for (int k = 0; k < 2000; k++) {
            double x = MIN + rng.nextDouble() * SIZE, z = MIN + rng.nextDouble() * SIZE;
            if (island.snaps(x, 0, z, 0).get(0).distance < 60) continue;
            int c = (int) ((x - MIN) / mpp), r = (int) ((z - MIN) / mpp);
            assertEquals(0, a[r * px + c], "paint 60 m from every road at " + x + ", " + z);
        }
        // A divided road is ONE road: the 3 m median between chuo_dori's carriageways is painted.
        // The longest chuo_dori forward lane: its id depends on where the zone grid split the road.
        RoadGraph.Lane f = null;
        for (RoadGraph.Lane l : island.lanes()) {
            if (l.id.startsWith("chuo_dori") && l.id.endsWith("_F0") && (f == null || l.length() > f.length())) f = l;
        }
        assertNotNull(f, "a chuo_dori lane");
        String stem = f.id.substring(0, f.id.length() - 3);
        RoadGraph.Lane r = island.lane(stem + "_R0");
        double[] mf = f.at(f.length() * 0.5);
        RoadGraph.Snap sr = RoadGraph.snap(r, mf[0], mf[1], mf[2], 0);
        assertTrue(sr.distance > f.width + 1, "a real median: " + sr.distance);
        double mx = (mf[0] + sr.point[0]) * 0.5, mz = (mf[2] + sr.point[2]) * 0.5;
        assertEquals(255, a[(int) ((mz - MIN) / mpp) * px + (int) ((mx - MIN) / mpp)] & 0xff, "the median");
        // ... while the outer edge stays put: 1.5 px past the outer lane's edge is off the road.
        double nx = (mf[0] - sr.point[0]) / sr.distance, nz = (mf[2] - sr.point[2]) / sr.distance;
        double ox = mf[0] + nx * (f.width * 0.5 + 1.5 * mpp), oz = mf[2] + nz * (f.width * 0.5 + 1.5 * mpp);
        RoadGraph.Lane outer = island.lane(stem + "_F1");
        if (outer != null) {
            double[] mo = outer.at(RoadGraph.snap(outer, mf[0], mf[1], mf[2], 0).offset);
            ox = mo[0] + nx * (outer.width * 0.5 + 1.5 * mpp);
            oz = mo[2] + nz * (outer.width * 0.5 + 1.5 * mpp);
        }
        assertEquals(0, a[(int) ((oz - MIN) / mpp) * px + (int) ((ox - MIN) / mpp)] & 0xff, "past the outer edge");
        // Max mips: the whole-island view still has every road. The 1x1 level is "some road".
        byte[] la8 = RoadRaster.la8WithMaxMips(a, px);
        assertEquals((byte) 255, la8[la8.length - 1]);
        int levels = RoadRaster.levels(px);
        assertEquals(13, levels);
    }

    /** A graph written and read back routes exactly as the one it was baked from. */
    @Test
    void aBakeRoutesLikeTheLiveGraph() {
        RoadMapBake.Meta meta = new RoadMapBake.Meta("sig", MIN, MIN, SIZE, 4096);
        byte[] bytes = RoadMapBake.write(meta, island);
        RoadMapBake.Loaded back = RoadMapBake.read(bytes);
        assertEquals("sig", back.meta.signature);
        assertEquals(island.laneCount(), back.graph.laneCount());
        assertNotNull(back.graph.index());
        assertEquals("sig", RoadMapBake.readMeta(bytes).signature);
        Random rng = new Random(3);
        List<RoadGraph.Lane> all = List.copyOf(island.lanes());
        int compared = 0;
        for (int k = 0; k < 150; k++) {
            RoadGraph.Lane a = all.get(rng.nextInt(all.size())), b = all.get(rng.nextInt(all.size()));
            double[] p = a.at(a.length() * rng.nextDouble()), q = b.at(b.length() * rng.nextDouble());
            RoadGraph.Route r1 = island.route(p[0], p[1], p[2], q[0], q[1], q[2]);
            RoadGraph.Route r2 = back.graph.route(p[0], p[1], p[2], q[0], q[1], q[2]);
            assertEquals(r1 == null, r2 == null);
            if (r1 == null) continue;
            assertEquals(r1.laneIds(), r2.laneIds());
            assertEquals(r1.length, r2.length, 1e-9);
            compared++;
        }
        assertTrue(compared > 80, "routes compared: " + compared);
        System.out.printf("bake: %d bytes%n", bytes.length);
    }
}
