package com.openworld.audio;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;

/**
 * The audio rule: every sound is a file in assets/audio/, never generated in code, and assets/audio/README.md's
 * "Wired in code" table lists exactly the {@link Sound}s. Prints which of them still have no file.
 */
class SoundTest {

    private static final Path AUDIO = Path.of("assets/audio");
    private static final Path SRC = Path.of("src/main/java");

    @Test
    void readmeListsExactlyTheWiredSounds() throws IOException {
        String readme = Files.readString(AUDIO.resolve("README.md"));
        int a = readme.indexOf("## Wired in code");
        int b = readme.indexOf("\n## ", a + 1);
        String table = readme.substring(a, b < 0 ? readme.length() : b);
        Set<String> listed = new TreeSet<>();
        Matcher m = Pattern.compile("^\\| `([a-z0-9_]+)` \\| `([A-Z0-9_]+)` \\|", Pattern.MULTILINE).matcher(table);
        while (m.find()) {
            listed.add(m.group(1));
            assertEquals(Sound.valueOf(m.group(2)).file, m.group(1), "README row names the wrong enum");
        }
        Set<String> wired = new TreeSet<>();
        for (Sound s : Sound.values()) wired.add(s.file);
        assertEquals(wired, listed, "assets/audio/README.md 'Wired in code' table must list every Sound");

        List<String> missing = new ArrayList<>();
        for (Sound s : Sound.values()) {
            boolean there = false;
            for (String ext : Sound.EXTENSIONS) there |= Files.exists(AUDIO.resolve(s.file + ext));
            if (!there) missing.add(s.file);
        }
        System.out.println("[SoundTest] wired sounds with no file yet: " + missing);
    }

    @Test
    void noSoundIsGeneratedInCode() throws IOException {
        List<String> offenders = new ArrayList<>();
        try (Stream<Path> files = Files.walk(SRC)) {
            for (Path p : (Iterable<Path>) files.filter(f -> f.toString().endsWith(".java"))::iterator) {
                String s = Files.readString(p);
                if (s.contains("new AudioStreamWAV(") || s.contains("AudioStreamGenerator")) offenders.add(p.toString());
            }
        }
        assertTrue(offenders.isEmpty(), "sounds must be files in assets/audio/, not synthesised: " + offenders);
    }
}
