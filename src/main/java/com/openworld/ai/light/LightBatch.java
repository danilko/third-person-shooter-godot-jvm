package com.openworld.ai.light;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/**
 * MSG_LIGHT_BATCH's body (PLAN.md 2.3): the host's light combatants as a client draws them, engine-free so
 * {@code LightBatchTest} round-trips it. Unreliable and superseded by the next one (10 Hz), so it carries the whole
 * visible tier every time, compactly:
 * <pre>
 *   u8 looks, then per look: utf8 "body|outfit|weapon" (u8 length + bytes)
 *   u16 count, then per body (11 bytes):
 *     u16 id, u8 look, i16 x (0.1 m), i16 y (0.05 m), i16 z (0.1 m), u8 yaw (1/256 turn), u8 flags
 *     flags: bits 0-3 state (LightSim), bit 4 ranged, bit 5 zombie, bit 6 has a target
 * </pre>
 * x / z cover +-3.2 km (the island is +-2.3 km), y +-1.6 km. A promoted body is not in it: its full body replicates
 * as an ordinary character.
 */
public final class LightBatch {

    public static final int ENTRY_BYTES = 11;

    public record Entry(int id, int look, double x, double y, double z, double yaw, int state, boolean ranged,
                        boolean zombie, boolean hasTarget) { }

    private LightBatch() { }

    public static byte[] encode(List<String> looks, List<Entry> entries) {
        ByteArrayOutputStream out = new ByteArrayOutputStream(4 + entries.size() * ENTRY_BYTES + looks.size() * 24);
        int nl = Math.min(255, looks.size());
        out.write(nl);
        for (int i = 0; i < nl; i++) {
            byte[] s = looks.get(i).getBytes(StandardCharsets.UTF_8);
            int len = Math.min(255, s.length);
            out.write(len);
            out.write(s, 0, len);
        }
        ByteBuffer b = ByteBuffer.allocate(2 + entries.size() * ENTRY_BYTES).order(ByteOrder.LITTLE_ENDIAN);
        b.putShort((short) Math.min(65535, entries.size()));
        for (Entry e : entries) {
            b.putShort((short) (e.id() & 0xffff));
            b.put((byte) e.look());
            b.putShort(q(e.x(), 10.0));
            b.putShort(q(e.y(), 20.0));
            b.putShort(q(e.z(), 10.0));
            double turns = e.yaw() / (2 * Math.PI);
            turns -= Math.floor(turns);
            b.put((byte) ((int) Math.round(turns * 256.0) & 0xff));
            int flags = (e.state() & 0x0f) | (e.ranged() ? 0x10 : 0) | (e.zombie() ? 0x20 : 0) | (e.hasTarget() ? 0x40 : 0);
            b.put((byte) flags);
        }
        out.write(b.array(), 0, b.position());
        return out.toByteArray();
    }

    /** The looks and the entries; throws IllegalArgumentException on a short or malformed body. */
    public static List<Entry> decode(byte[] data, List<String> looksOut) {
        ByteBuffer b = ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN);
        try {
            int nl = b.get() & 0xff;
            for (int i = 0; i < nl; i++) {
                int len = b.get() & 0xff;
                byte[] s = new byte[len];
                b.get(s);
                looksOut.add(new String(s, StandardCharsets.UTF_8));
            }
            int n = b.getShort() & 0xffff;
            if (b.remaining() < n * ENTRY_BYTES) throw new IllegalArgumentException("light batch: " + n + " entries, " + b.remaining() + " bytes");
            List<Entry> out = new ArrayList<>(n);
            for (int i = 0; i < n; i++) {
                int id = b.getShort() & 0xffff;
                int look = b.get() & 0xff;
                double x = b.getShort() / 10.0, y = b.getShort() / 20.0, z = b.getShort() / 10.0;
                double yaw = (b.get() & 0xff) / 256.0 * 2 * Math.PI;
                int f = b.get() & 0xff;
                if (look >= looksOut.size()) throw new IllegalArgumentException("light batch: look " + look + " of " + looksOut.size());
                out.add(new Entry(id, look, x, y, z, yaw, f & 0x0f, (f & 0x10) != 0, (f & 0x20) != 0, (f & 0x40) != 0));
            }
            return out;
        } catch (java.nio.BufferUnderflowException e) {
            throw new IllegalArgumentException("light batch: truncated", e);
        }
    }

    private static short q(double v, double scale) {
        return (short) Math.max(-32768, Math.min(32767, Math.round(v * scale)));
    }
}
