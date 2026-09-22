package com.openworld.world;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class PostalGridTest {
    @Test
    void theCornersOfTheSquare() {
        assertEquals("1-1-1", PostalGrid.label(-2304.0, -2304.0));       // north-west
        assertEquals("24-1-3", PostalGrid.label(2303.9, -2304.0));       // north-east
        assertEquals("1-24-7", PostalGrid.label(-2304.0, 2303.9));       // south-west
        assertEquals("24-24-9", PostalGrid.label(2303.9, 2303.9));       // south-east
        assertEquals("12-12-9", PostalGrid.label(-0.01, -0.01));          // just north-west of the origin
        assertEquals("13-13-1", PostalGrid.label(0.0, 0.0));
    }

    @Test
    void offTheSquareClampsToTheEdge() {
        assertEquals(1, PostalGrid.of(-9000.0, 0.0).x());
        assertEquals(24, PostalGrid.of(0.0, 9000.0).y());
    }

    @Test
    void everyCentreMapsBackToItsOwnCode() {
        for (int x = 1; x <= PostalGrid.CELLS; x++)
            for (int y = 1; y <= PostalGrid.CELLS; y++)
                for (int s = 0; s <= 9; s++) {
                    PostalGrid.Code c = new PostalGrid.Code(x, y, s);
                    double[] p = PostalGrid.centre(c);
                    PostalGrid.Code back = PostalGrid.of(p[0], p[1]);
                    assertEquals(x, back.x());
                    assertEquals(y, back.y());
                    assertEquals(s == 0 ? 5 : s, back.sub(), c.toString());
                }
    }

    @Test
    void everyPointHasOneCodeAndItsSubCellIsInsideIt() {
        java.util.Random r = new java.util.Random(7);
        for (int i = 0; i < 20000; i++) {
            double x = -2304.0 + r.nextDouble() * 4608.0, z = -2304.0 + r.nextDouble() * 4608.0;
            PostalGrid.Code c = PostalGrid.of(x, z);
            double[] cc = PostalGrid.centre(c);
            assertTrue(Math.abs(cc[0] - x) <= PostalGrid.SUB / 2.0 + 1e-9);
            assertTrue(Math.abs(cc[1] - z) <= PostalGrid.SUB / 2.0 + 1e-9);
        }
    }

    @Test
    void parsesWhatItPrintsAndRefusesTheRest() {
        assertEquals(new PostalGrid.Code(12, 7, 5), PostalGrid.parse("12-7-5"));
        assertEquals(new PostalGrid.Code(12, 7, 0), PostalGrid.parse(" 12 7 "));
        assertNull(PostalGrid.parse("25-1"));
        assertNull(PostalGrid.parse("3-4-10"));
        assertNull(PostalGrid.parse("a-b"));
        assertNull(PostalGrid.parse("7"));
    }
}
