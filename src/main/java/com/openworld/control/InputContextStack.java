package com.openworld.control;

import java.util.ArrayList;
import java.util.List;

/**
 * A body's input contexts, newest on top (PLAN.md AR4, input half). Replaces the one {@code Character.inputBlocked}
 * boolean that five overlays wrote: with the wheel open over the map, closing either handed the input (and a captured
 * mouse) back while the other was still up. Each overlay now pushes under its OWN name and pops that name, in any order;
 * what the body does is read off the top -- so the answer is derived from who is still open, never remembered.
 *
 * <p>Engine-free on purpose (unit-tested, {@code InputContextStackTest}); the owner is told on every change so it can
 * apply the pointer mode.
 */
public final class InputContextStack {
    private record Entry(String owner, InputContext context) {}

    private final List<Entry> entries = new ArrayList<>();
    private final Runnable onChange;

    public InputContextStack(Runnable onChange) { this.onChange = onChange; }

    /** Put {@code owner}'s context on top (an owner already on the stack moves to the top with the new context). */
    public void push(String owner, InputContext context) {
        if (owner == null || context == null) return;
        entries.removeIf(e -> e.owner.equals(owner));
        entries.add(new Entry(owner, context));
        changed();
    }

    /** Take {@code owner}'s context off, wherever it is; a no-op when it is not there. */
    public void pop(String owner) {
        if (entries.removeIf(e -> e.owner.equals(owner))) changed();
    }

    /** Push when {@code on}, pop when not -- for the overlays that have one open/close switch. */
    public void set(String owner, InputContext context, boolean on) {
        if (on) push(owner, context); else pop(owner);
    }

    /** The context on top, or null for plain gameplay. */
    public InputContext top() { return entries.isEmpty() ? null : entries.get(entries.size() - 1).context; }

    public boolean blocksGameplay() { InputContext t = top(); return t != null && t.blocksGameplay; }

    public boolean showsCursor() { InputContext t = top(); return t != null && t.showsCursor; }

    public boolean has(String owner) {
        for (Entry e : entries) if (e.owner.equals(owner)) return true;
        return false;
    }

    /** The owners bottom to top -- for probes and the bug line. */
    public String describe() {
        StringBuilder b = new StringBuilder();
        for (Entry e : entries) b.append(b.length() == 0 ? "" : ",").append(e.owner).append(':').append(e.context);
        return b.toString();
    }

    private void changed() { if (onChange != null) onChange.run(); }
}
