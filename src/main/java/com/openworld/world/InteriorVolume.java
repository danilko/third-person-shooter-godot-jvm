package com.openworld.world;

import com.openworld.character.Character;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.AudioServer;
import godot.api.Area3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.core.Callable;
import godot.core.MethodCallable;
import godot.core.StringName;
import godot.global.GD;

/**
 * Marks the inside of a building as an audio-ambience region (PLAN.md I2).
 *
 * <p><b>Not a portal.</b> I2 buildings are continuous open-world geometry — you walk in through a real
 * doorway, no scene load, no teleport (see {@link Breakable} header for why). The only thing the
 * interior changes is <i>ambience</i>: when the <b>local player</b> is inside, a reverb effect on a
 * named audio bus is enabled; on exit it is disabled. This is the one piece of the old "PortalTrigger"
 * idea worth keeping, reduced to a passive, non-blocking trigger.
 *
 * <p>It is tolerant of missing content: if {@code reverbBusName} doesn't exist in the project's audio
 * layout yet, it logs once and no-ops — so the volume can be authored and walk-tested before the
 * Interior bus + reverb effect are configured. Mirrors {@link WaterVolume}'s Area3D-detects-bodies
 * pattern; a non-blocking overlap so it never affects movement or bullets.
 */
@RegisterClass(className = "InteriorVolume")
public class InteriorVolume extends Area3D {

    public static final String INTERIOR_GROUP = "interior";

    /** Audio bus whose effect is toggled while the local player is inside. */
    @Export @RegisterProperty public String reverbBusName = "Interior";

    /** Index of the effect on that bus to enable/disable (the reverb). */
    @Export @RegisterProperty public int reverbEffectIndex = 0;

    /** Overlapping local-player count (overlapping interior volumes / re-entry are handled by the count). */
    private int localOccupants = 0;
    private boolean warnedMissingBus = false;

    @RegisterFunction
    @Override
    public void _ready() {
        addToGroup(new StringName(INTERIOR_GROUP));
        connect(new StringName("body_entered"), MethodCallable.createUnsafe(this, "on_body_entered"));
        connect(new StringName("body_exited"), MethodCallable.createUnsafe(this, "on_body_exited"));
    }

    @RegisterFunction
    public void onBodyEntered(Node3D body) {
        if (!isLocalPlayer(body)) return;
        localOccupants++;
        if (localOccupants == 1) setInteriorAudio(true);
    }

    @RegisterFunction
    public void onBodyExited(Node3D body) {
        if (!isLocalPlayer(body)) return;
        localOccupants = Math.max(0, localOccupants - 1);
        if (localOccupants == 0) setInteriorAudio(false);
    }

    private void setInteriorAudio(boolean inside) {
        int bus = AudioServer.getBusIndex(reverbBusName);
        if (bus < 0) {
            if (!warnedMissingBus) {
                GD.print("InteriorVolume: audio bus '" + reverbBusName + "' not found — interior reverb "
                        + "is a no-op until it is configured (detection still works).");
                warnedMissingBus = true;
            }
            return;
        }
        AudioServer.setBusEffectEnabled(bus, reverbEffectIndex, inside);
    }

    private boolean isLocalPlayer(Node3D body) {
        Character c = (body instanceof Character ch) ? ch
                : (body.getOwner() instanceof Character ch2 ? ch2 : null);
        return c != null && c.isLocalOwnedPlayer();
    }
}
