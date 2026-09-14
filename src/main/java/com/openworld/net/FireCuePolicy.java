package com.openworld.net;

/**
 * How many remote fire cues a changed replicated shot counter stands for (PLAN.md N3) — engine-free, tested.
 *
 * <p>Fire is replicated as STATE: a u8 {@code fireSeq} rides every snapshot and a puppet plays a cue when it
 * changes. Playing exactly ONE cue per change collapsed several shots into one sound and tracer whenever a
 * snapshot was dropped or the host re-broadcast two client snapshots in one interval — a full-auto burst
 * heard as single shots. The counter already says how many shots happened; this reads it.
 */
public final class FireCuePolicy {

    /** Most cues one counter change may replay: past this a gap is a stall or a rejoin, not a burst. */
    public static final int MAX_CUES = 4;

    private FireCuePolicy() { }

    /**
     * Cues to play for a counter that went from {@code last} to {@code now} (both u8, wrapping), capped at
     * {@code cap}; 0 when unchanged. {@code haveLast} false (the first snapshot) plays none.
     */
    public static int cuesFor(boolean haveLast, int last, int now, int cap) {
        if (!haveLast) return 0;
        int delta = (now - last) & 0xFF;
        return Math.min(delta, Math.max(0, cap));
    }
}
