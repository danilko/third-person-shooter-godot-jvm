package com.openworld.control;

import com.openworld.character.Character;
import godot.api.Node;
import godot.global.GD;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;

/**
 * The interact key's arbitration (PLAN.md AR4, input half): which {@link Interactable} E uses. The OFFERS are the
 * prompts -- every {@code EventBus.interactPrompt(source, on, label)} passes through {@link #prompt}, and a source that
 * is an Interactable with an E-keyed label (KeyGlyph: no hint means E) is on offer until it withdraws. The HUD shows the
 * NEWEST prompt, so {@link #useBest} uses the newest live offer: what the prompt says is what E does. Prompts are only
 * shown to the local player, so the offers are this machine's player's.
 */
public final class Interactions {
    private Interactions() {}

    private static final LinkedHashMap<Long, Node> OFFERS = new LinkedHashMap<>();
    private static int uses;

    /** Called by EventBus.interactPrompt for every prompt change. */
    public static void prompt(Node source, boolean on, String label) {
        if (source == null) return;
        long id = source.getInstanceId();
        OFFERS.remove(id);   // re-offered = newest again
        if (on && source instanceof Interactable
                && "E".equals(com.openworld.ui.KeyGlyph.parse(label).key())) OFFERS.put(id, source);
    }

    /** Use the newest live offer for {@code actor}; false when nothing is on offer. */
    public static boolean useBest(Character actor) {
        OFFERS.values().removeIf(n -> !GD.isInstanceValid(n) || !n.isInsideTree());
        if (OFFERS.isEmpty() || actor == null) return false;
        List<Node> newestFirst = new ArrayList<>(OFFERS.values());
        Node n = newestFirst.get(newestFirst.size() - 1);
        uses++;
        ((Interactable) n).interact(actor);
        return true;
    }

    /** Probe readouts. */
    public static int offersNow() {
        OFFERS.values().removeIf(n -> !GD.isInstanceValid(n) || !n.isInsideTree());
        return OFFERS.size();
    }
    public static int usesNow() { return uses; }
    public static void clear() { OFFERS.clear(); }
}
