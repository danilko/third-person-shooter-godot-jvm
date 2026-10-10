package com.openworld.game.profile;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

/**
 * Crash-safe save files (PLAN.md 1.4: CR5). v1 wrote the slot IN PLACE, so a crash mid-write lost the only autosave.
 * Now a write goes to {@code <file>.tmp}, is read back and checked, the old file rotates to {@code .bak1} (and that one
 * to {@code .bak2}), and the temp file is MOVED into place. Each file starts with a {@code #sha256:<hex>} line over
 * the rest, so a torn or edited file is detected on read and the newest good backup is used instead. A file with no
 * header (a v1 slot) is read as-is. Plain java.nio on the globalized path ({@code ProjectSettings.globalizePath}),
 * so it is unit-tested against a temp directory ({@code SafeSaveTest}).
 */
public final class SafeSave {
    private SafeSave() {}

    private static final String HEADER = "#sha256:";

    public static String sha256(String s) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(s.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    /** {@code payload} with its checksum line. */
    public static String wrap(String payload) { return HEADER + sha256(payload) + "\n" + payload; }

    /** The payload when the checksum matches (or there is no header: a v1 file), else null. */
    public static String unwrap(String text) {
        if (text == null) return null;
        if (!text.startsWith(HEADER)) return text.isBlank() ? null : text;
        int nl = text.indexOf('\n');
        if (nl < 0) return null;
        String sum = text.substring(HEADER.length(), nl).trim();
        String payload = text.substring(nl + 1);
        return sum.equalsIgnoreCase(sha256(payload)) ? payload : null;
    }

    /** Write atomically with two backups. False (and the old file untouched) when anything failed. */
    public static boolean write(Path file, String payload) {
        try {
            Files.createDirectories(file.toAbsolutePath().getParent());
            Path tmp = file.resolveSibling(file.getFileName() + ".tmp");
            String text = wrap(payload);
            Files.writeString(tmp, text, StandardCharsets.UTF_8);
            if (!payload.equals(unwrap(Files.readString(tmp, StandardCharsets.UTF_8)))) return false;
            Path bak1 = file.resolveSibling(file.getFileName() + ".bak1");
            Path bak2 = file.resolveSibling(file.getFileName() + ".bak2");
            if (Files.exists(bak1)) Files.move(bak1, bak2, StandardCopyOption.REPLACE_EXISTING);
            if (Files.exists(file)) Files.copy(file, bak1, StandardCopyOption.REPLACE_EXISTING);
            try {
                Files.move(tmp, file, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException e) {
                Files.move(tmp, file, StandardCopyOption.REPLACE_EXISTING);
            }
            return true;
        } catch (IOException e) {
            return false;
        }
    }

    /** A read: the file, else {@code .bak1}, else {@code .bak2} -- the first whose checksum holds. */
    public record Read(String payload, String from) {}

    public static Read read(Path file) {
        for (String suffix : new String[] {"", ".bak1", ".bak2"}) {
            Path p = suffix.isEmpty() ? file : file.resolveSibling(file.getFileName() + suffix);
            try {
                if (!Files.exists(p)) continue;
                String payload = unwrap(Files.readString(p, StandardCharsets.UTF_8));
                if (payload != null) return new Read(payload, suffix.isEmpty() ? "file" : suffix.substring(1));
            } catch (IOException e) {
                // try the next one
            }
        }
        return null;
    }

    public static boolean exists(Path file) {
        return Files.exists(file) || Files.exists(file.resolveSibling(file.getFileName() + ".bak1"));
    }
}
