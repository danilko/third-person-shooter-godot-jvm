package com.openworld.world;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Node;
import godot.core.Vector3;

import java.util.ArrayList;
import java.util.List;

/**
 * Spatial, poll-based channel for AI-perceptible world events (PLAN.md Part E / E2) — registered as
 * the AutoLoad singleton "StimulusManager".
 *
 * <p><b>Why not EventBus:</b> {@code EventBus} fans every signal out to every listener — fine for UI,
 * wrong for AI perception at open-world scale (every AI would wake on every gunshot anywhere). A
 * stimulus instead is dropped at a world position with an audible {@code radius}; AI <b>poll</b> their
 * own neighbourhood for stimuli in range (see {@code AICharacter.hearAlarm}). No global broadcast, no
 * per-AI subscription — the same "look only at your local cell" philosophy as {@link SpatialEntityGrid}.
 * EventBus is unchanged and keeps all UI signals; only AI-perception events live here.
 *
 * <p><b>Authority:</b> stimuli are posted from the authoritative side-effect paths (a weapon's
 * {@code useWeapon}, {@code ExplosionManager.triggerExplosion}, {@code Vehicle._integrateForces}) —
 * the same places that apply damage — so on the host (which simulates the AI) the events that matter
 * are present. The store is a plain local list per peer; nothing is networked (puppet AI don't think).
 * Networked propagation of a remote client's gunshot to host AI is a later refinement.
 *
 * <p><b>Lifecycle:</b> mirrors {@link SpatialEntityGrid}'s AutoLoad shape — JVM-static {@link #get()}
 * set in {@code _ready()} and cleared in {@code _exitTree()}. {@code _process} ages out stimuli older
 * than {@link #stimulusLifetime}. When the AutoLoad is absent (test scenes) callers no-op.
 */
@RegisterClass(className = "StimulusManager")
public class StimulusManager extends Node {

    private static StimulusManager instance;

    /** The live manager, or null if the AutoLoad isn't present (test scenes). */
    public static StimulusManager get() { return instance; }

    /** Seconds a stimulus stays perceivable before it ages out. */
    @Export @RegisterProperty public float stimulusLifetime = 5.0f;

    /** Kinds of perceptible event. GUNSHOT/EXPLOSION/VEHICLE_CRASH are emitted in E2; DEAD_BODY and
     *  PLAYER_SPOTTED are reserved for later perception features (corpse discovery, squad sighting). */
    public enum Type { GUNSHOT, EXPLOSION, VEHICLE_CRASH, DEAD_BODY, PLAYER_SPOTTED }

    /** One world event an AI may perceive. Immutable; {@code source}/{@code sourceFaction} let a
     *  listener ignore its own or friendly events. {@code radius} is how far the event is audible. */
    public static final class Stimulus {
        public final Type type;
        public final Vector3 origin;
        public final float radius;
        public final Node source;
        public final String sourceFaction;
        public final double timestamp;

        Stimulus(Type type, Vector3 origin, float radius, Node source, String sourceFaction, double timestamp) {
            this.type = type;
            this.origin = origin;
            this.radius = radius;
            this.source = source;
            this.sourceFaction = sourceFaction;
            this.timestamp = timestamp;
        }
    }

    private final List<Stimulus> stimuli = new ArrayList<>();
    /** Monotonic seconds accumulated in _process; used as the stimulus clock (no engine time dependency). */
    private double elapsed = 0.0;

    @RegisterFunction
    @Override
    public void _ready() {
        instance = this;
    }

    @RegisterFunction
    @Override
    public void _exitTree() {
        if (instance == this) instance = null;
        stimuli.clear();
    }

    @RegisterFunction
    @Override
    public void _process(double delta) {
        elapsed += delta;
        double cutoff = elapsed - stimulusLifetime;
        for (int i = stimuli.size() - 1; i >= 0; i--) {
            if (stimuli.get(i).timestamp < cutoff) stimuli.remove(i);
        }
    }

    /**
     * Drop a perceptible event into the world. {@code radius} is the audible range; {@code source} is
     * the node that produced it (so a listener can ignore its own) and {@code sourceFaction} lets a
     * listener apply faction rules (e.g. ignore allied gunfire). No-op on a null origin.
     */
    public void post(Type type, Vector3 origin, float radius, Node source, String sourceFaction) {
        if (origin == null) return;
        stimuli.add(new Stimulus(type, origin, radius, source,
                sourceFaction == null ? "" : sourceFaction, elapsed));
    }

    /**
     * The live stimulus list — callers iterate it read-only (must not mutate), the same backing-list
     * convention as {@code PlayerRegistry.getPlayers()}. Each listener applies its own range + faction
     * filtering (a stimulus carries the data needed for both).
     */
    public List<Stimulus> getStimuli() {
        return stimuli;
    }
}
