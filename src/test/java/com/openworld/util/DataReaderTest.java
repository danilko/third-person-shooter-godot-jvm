package com.openworld.util;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DataReaderTest {

    @Test
    void aCleanDocumentHasNoProblems() {
        DataReader d = DataReader.of("{\"note\":\"x\",\"a_note\":\"y\",\"_draft\":1,\"heat\":10,\"name\":\"n\",\"on\":true,"
                + "\"list\":[\"a\",\"b\"],\"at\":[1,2.6],\"sub\":{\"k\":1},\"rows\":{\"r1\":{\"v\":1},\"r2\":{\"v\":2}}}");
        assertEquals(10.0, d.num("heat", 0));
        assertEquals("n", d.str("name", ""));
        assertTrue(d.bool("on", false));
        assertEquals(List.of("a", "b"), d.strings("list"));
        assertEquals(3, d.ints("at")[1]);
        assertEquals(1, d.child("sub").integer("k", 0));
        assertEquals(1, d.rows("rows").get("r1").integer("v", 0));
        assertEquals(2, d.rows("rows").get("r2").integer("v", 0));
        assertEquals(List.of(), d.finish());
    }

    @Test
    void anUnknownKeyIsNamedWithItsPath() {
        DataReader d = DataReader.of("{\"crimes\":{\"gunfire\":{\"heat\":10,\"min_star\":1}},\"extra\":1}");
        for (DataReader r : d.rows("crimes").values()) {
            r.num("heat", 0);
            r.integer("min_stars", 0);
        }
        assertEquals(List.of("extra: unknown key", "crimes.gunfire.min_star: unknown key"), d.finish());
    }

    @Test
    void aWrongTypeKeepsTheDefaultAndIsReported() {
        DataReader d = DataReader.of("{\"heat\":\"ten\",\"list\":[1],\"sub\":3}");
        assertEquals(7.0, d.num("heat", 7.0));
        assertEquals(List.of(), d.strings("list"));
        assertNull(d.child("sub"));
        assertEquals(List.of("heat: expected a number, found a string", "list[0]: expected a string, found a number",
                "sub: expected an object, found a number"), d.finish());
    }

    @Test
    void aMissingRequiredValueIsReported() {
        DataReader d = DataReader.of("{}");
        assertEquals(0.0, d.reqNum("heat", 0.0));
        assertEquals(List.of("heat: missing"), d.finish());
    }

    @Test
    void twoParsersShareOneChildReader() {
        DataReader d = DataReader.of("{\"gangs\":{\"g\":{\"name\":\"G\",\"bodies\":[{\"body\":\"b\"}]}}}");
        d.rows("gangs").get("g").str("name", "");
        for (DataReader b : d.rows("gangs").get("g").items("bodies")) b.str("body", "");
        assertEquals(List.of(), d.finish());
    }

    @Test
    void textThatIsNotAnObjectIsAProblemNotACrash() {
        assertEquals(1, DataReader.of("[1,2]").finish().size());
        assertEquals(1, DataReader.of("{oops").finish().size());
        assertEquals(1, DataReader.of(null).finish().size());
    }
}
