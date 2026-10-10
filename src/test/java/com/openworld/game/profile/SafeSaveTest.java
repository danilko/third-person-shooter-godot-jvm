package com.openworld.game.profile;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class SafeSaveTest {
    @TempDir Path dir;

    @Test
    void writesRotateTwoBackups() throws Exception {
        Path f = dir.resolve("world.json");
        assertTrue(SafeSave.write(f, "{\"n\":1}"));
        assertTrue(SafeSave.write(f, "{\"n\":2}"));
        assertTrue(SafeSave.write(f, "{\"n\":3}"));
        assertEquals("{\"n\":3}", SafeSave.read(f).payload());
        assertEquals("{\"n\":2}", SafeSave.unwrap(Files.readString(dir.resolve("world.json.bak1"))));
        assertEquals("{\"n\":1}", SafeSave.unwrap(Files.readString(dir.resolve("world.json.bak2"))));
        assertTrue(!Files.exists(dir.resolve("world.json.tmp")));
    }

    @Test
    void aTornFileFallsBackToTheNewestGoodBackup() throws Exception {
        Path f = dir.resolve("profile.json");
        SafeSave.write(f, "{\"balance\":10}");
        SafeSave.write(f, "{\"balance\":20}");
        // a crash mid-write / a hand edit: the checksum no longer holds
        String torn = Files.readString(f).replace("20", "2");
        Files.writeString(f, torn, StandardCharsets.UTF_8);
        SafeSave.Read r = SafeSave.read(f);
        assertEquals("{\"balance\":10}", r.payload());
        assertEquals("bak1", r.from());
    }

    @Test
    void aV1FileWithNoHeaderIsReadAsIs() throws Exception {
        Path f = dir.resolve("slot0.json");
        Files.writeString(f, "{\"schema\":1}", StandardCharsets.UTF_8);
        assertEquals("{\"schema\":1}", SafeSave.read(f).payload());
        assertNull(SafeSave.unwrap("#sha256:00\n{}"));
    }
}
