package com.openworld.world;

import godot.annotation.Script;
import godot.api.Node3D;

/**
 * One flap of a station's automatic ticket gate (自動改札機, PLAN.md P3 "the paid area"): a {@link Door} that swings
 * aside for a character walking through the lane from either side and shuts behind them. A station's platforms are a
 * closed PAID AREA -- platform, stair / lift, gates, street, all one kit station scene -- and this flap is the only way
 * through the fare barrier inside the station building.
 *
 * <p>The fare is FREE for now: {@link #admits(Node3D)} lets every character through. It is the one place a fare
 * (an IC card, a ticket, a wanted level) will be asked, and it is asked on the sensor's enter AND exit, so a later
 * answer must be decided once per pass rather than read live.
 *
 * <p>Built by {@code tools/godot/build_building_scenes.gd} from a door-only prop with {@code door.kind = "gate"}; the
 * leaf, its collision and its sensor are the Door's own, so nothing here differs from a door but the defaults
 * (a fast, short flap) and the fare hook.
 */
@Script(className = "TicketGate")
public class TicketGate extends Door {

    public TicketGate() {
        openAngleDeg = 90.0f;
        openSpeed = 8.0f;      // a flap snaps open: a walking body must not meet it half way
        autoOpen = true;
        swingBothWays = true;
    }

    @Override
    protected boolean admits(Node3D body) {
        return true;           // fare-free; the hook for a fare later
    }
}
