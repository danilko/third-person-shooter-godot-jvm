package com.openworld.audio;

import godot.api.AudioStream;
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

    private static final Map<Sound, AudioStream> LOADED = new EnumMap<>(Sound.class);
    private static final Set<Sound> MISSING = EnumSet.noneOf(Sound.class);

    /** The sound's stream, or null when its file is not there (the caller then plays nothing). */
    public static AudioStream stream(Sound s) {
        AudioStream a = LOADED.get(s);
        if (a != null || MISSING.contains(s)) return a;
        for (String ext : Sound.EXTENSIONS) {
            String path = DIR + s.file + ext;
            if (ResourceLoader.INSTANCE.exists(path, "") && GD.load(path) instanceof AudioStream st) {
                LOADED.put(s, st);
                return st;
            }
        }
        MISSING.add(s);
        GD.print("[Sounds] missing audio: " + DIR + s.file + ".ogg|.wav (" + s + ") -- silent; see assets/audio/README.md");
        return null;
    }

    /**
     * Plays a sound once at {@code at}, on a player parented to {@code parent} and freed when the sound ends. Does
     * nothing when the file is missing. {@code pitchJitter} 0.1 = a random pitch in 0.9..1.1.
     */
    public static void play3D(Node parent, Sound s, Vector3 at, float unitSize, float pitchJitter) {
        AudioStream st = stream(s);
        if (st == null || parent == null || !parent.isInsideTree()) return;
        AudioStreamPlayer3D p = new AudioStreamPlayer3D();
        p.setName(new StringName("Sound_" + s.file));
        p.setStream(st);
        p.setUnitSize(unitSize);
        if (pitchJitter > 0f) p.setPitchScale((float) GD.randfRange(1f - pitchJitter, 1f + pitchJitter));
        parent.addChild(p);
        p.setGlobalPosition(at);
        p.connect(new StringName("finished"), MethodCallable.createUnsafe(p, "queue_free"));
        p.connect(new StringName("tree_exiting"), MethodCallable.createUnsafe(p, "stop"));   // CLAUDE.md audio rule
        p.play();
    }

    /** Engine-owned statics: dropped when the game closes (GameManager._exitTree), the IconRegistry rule. */
    public static void clear() {
        LOADED.clear();
        MISSING.clear();
    }
}
