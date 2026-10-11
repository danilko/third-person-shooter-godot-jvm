package com.openworld.audio;

import godot.api.AudioStream;
import godot.api.AudioStreamPlayer;
import godot.api.AudioStreamPlayer3D;
import godot.api.Node;
import godot.api.ResourceLoader;
import godot.core.MethodCallable;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Map;
import java.util.Set;

/** Loads a {@link Sound} from {@code assets/audio/}, once; a missing file is silence, reported once. */
public final class Sounds {
    private Sounds() {}

    public static final String DIR = "res://assets/audio/";

    private static final Map<Sound, AudioStream[]> LOADED = new EnumMap<>(Sound.class);
    private static final Set<Sound> MISSING = EnumSet.noneOf(Sound.class);
    private static final Map<Sound, Integer> PLAYED = new EnumMap<>(Sound.class);

    /** How many times the sound has started (play2D / play3D with its file present); probes read it. */
    public static int played(Sound s) { return PLAYED.getOrDefault(s, 0); }

    /** "NAME:takes" for every Sound, comma separated (0 takes = no file); probes read it. */
    public static String report() {
        StringBuilder b = new StringBuilder();
        for (Sound s : Sound.values()) b.append(b.length() == 0 ? "" : ",").append(s.name()).append(':').append(loadedTakes(s));
        return b.toString();
    }

    /** One of the sound's takes at random, or null when no file is there (the caller then plays nothing). */
    public static AudioStream stream(Sound s) {
        AudioStream[] a = LOADED.get(s);
        if (a == null) {
            if (MISSING.contains(s)) return null;
            java.util.List<AudioStream> found = new java.util.ArrayList<>();
            for (int i = 1; i <= s.variants; i++) {
                for (String ext : Sound.EXTENSIONS) {
                    String path = DIR + s.variantFile(i) + ext;
                    if (ResourceLoader.INSTANCE.exists(path, "") && GD.load(path) instanceof AudioStream st) {
                        found.add(st);
                        break;
                    }
                }
            }
            if (found.isEmpty()) {
                MISSING.add(s);
                GD.print("[Sounds] missing audio: " + DIR + s.variantFile(1) + ".ogg|.wav (" + s
                        + ") -- silent; see assets/audio/README.md");
                return null;
            }
            a = found.toArray(new AudioStream[0]);
            LOADED.put(s, a);
        }
        return a.length == 1 ? a[0] : a[(int) (Math.random() * a.length) % a.length];
    }

    /** How many takes of the sound loaded (0 = missing); for probes. */
    public static int loadedTakes(Sound s) {
        stream(s);
        AudioStream[] a = LOADED.get(s);
        return a == null ? 0 : a.length;
    }

    /**
     * Plays a sound once at {@code at}, on a player parented to {@code parent} and freed when the sound ends. Does
     * nothing when the file is missing. {@code pitchJitter} 0.1 = a random pitch in 0.9..1.1.
     */
    public static void play3D(Node parent, Sound s, Vector3 at, float unitSize, float pitchJitter) {
        play3D(parent, s, at, unitSize, pitchJitter, 0f);
    }

    /** {@link #play3D(Node, Sound, Vector3, float, float)} at {@code volumeDb}. */
    public static void play3D(Node parent, Sound s, Vector3 at, float unitSize, float pitchJitter, float volumeDb) {
        AudioStream st = stream(s);
        if (st == null || parent == null || !parent.isInsideTree()) return;
        AudioStreamPlayer3D p = new AudioStreamPlayer3D();
        p.setName(new StringName("Sound_" + s.name()));
        p.setStream(st);
        p.setUnitSize(unitSize);
        p.setVolumeDb(volumeDb);
        if (pitchJitter > 0f) p.setPitchScale((float) GD.randfRange(1f - pitchJitter, 1f + pitchJitter));
        parent.addChild(p);
        p.setGlobalPosition(at);
        p.connect("finished", MethodCallable.createUnsafe(p, "queue_free"));
        p.connect("tree_exiting", MethodCallable.createUnsafe(p, "stop"));   // CLAUDE.md audio rule
        p.play();
        PLAYED.merge(s, 1, Integer::sum);
    }

    /**
     * Plays a sound once, not positional (UI, stingers), on a player parented to {@code parent} and freed when it
     * ends. Keeps playing while the game is paused (a menu click). Does nothing when the file is missing.
     */
    public static void play2D(Node parent, Sound s, float volumeDb) {
        AudioStream st = stream(s);
        if (st == null || parent == null || !parent.isInsideTree()) return;
        AudioStreamPlayer p = new AudioStreamPlayer();
        p.setName(new StringName("Sound_" + s.name()));
        p.setStream(st);
        p.setVolumeDb(volumeDb);
        p.setProcessMode(Node.ProcessMode.ALWAYS);
        parent.addChild(p);
        p.connect("finished", MethodCallable.createUnsafe(p, "queue_free"));
        p.connect("tree_exiting", MethodCallable.createUnsafe(p, "stop"));
        p.play();
        PLAYED.merge(s, 1, Integer::sum);
    }

    /** {@link #play2D(Node, Sound, float)} on the scene tree's root, so a node freed on the same frame (a menu
     *  closing) does not cut its own click off. */
    public static void ui(Node anyNode, Sound s) {
        if (anyNode == null || !anyNode.isInsideTree()) return;
        play2D(anyNode.getTree().getRoot(), s, 0f);
    }

    /** Engine-owned statics: dropped when the game closes (GameManager._exitTree), the IconRegistry rule. */
    public static void clear() {
        LOADED.clear();
        MISSING.clear();
        PLAYED.clear();
    }
}
