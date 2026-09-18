package com.openworld.debug;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.character.AICharacter;
import com.openworld.character.Character;
import com.openworld.character.Faction;
import com.openworld.character.Health;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;
import godot.core.Color;
import godot.global.GD;

/**
 * The vehicle/occupant calls a headless GDScript probe needs and Godot cannot reach: seating, killing
 * and carjacking are plain Java on {@link Vehicle} and {@link Health}, not registered methods, and
 * registering them there for a test would add engine-visible surface to gameplay classes. A probe
 * instances this node and asks it instead. Used by {@code tools/godot/probe_dead_driver.gd} (PLAN.md 0.2),
 * {@code probe_zone_trigger.gd} (F3) and {@code probe_race.gd} (R2).
 */
@Script(className = "VehicleProbeHelper")
public class VehicleProbeHelper extends Node {

    /** Seat {@code ai} at the wheel of {@code v} (the ZoneManager traffic path: the car keeps its brain). */
    @Register
    public void seatDriver(Node v, Node ai) {
        if (v instanceof Vehicle car && ai instanceof AICharacter a) car.tryEnter(a);
    }

    /** Kill {@code c} outright through its own Health, the way a shot would. */
    @Register
    public void kill(Node c) {
        if (c != null && c.getNodeOrNull("Health") instanceof Health h) h.takeDamage(null, 1.0e6f, "probe");
    }

    @Register
    public boolean isAiDriven(Node v) {
        return v instanceof Vehicle car && car.isAiDriven();
    }

    @Register
    public boolean isAiOccupied(Node v) {
        return v instanceof Vehicle car && car.isAiOccupied();
    }

    @Register
    public boolean hasDefeatedDriver(Node v) {
        return v instanceof Vehicle car && car.hasDefeatedDriver();
    }

    /** The driver-seat occupant, or null. */
    @Register
    public Node occupantOf(Node v) {
        return v instanceof Vehicle car && car.getOccupant() != null && GD.isInstanceValid(car.getOccupant())
                ? car.getOccupant() : null;
    }

    @Register
    public boolean nameplateIsNeutral(Node v) {
        if (!(v instanceof Vehicle car)) return false;
        Color c = car.getNameplateColor();
        Color n = Faction.color(Faction.NEUTRAL);
        return Math.abs(c.getR() - n.getR()) < 1e-4 && Math.abs(c.getG() - n.getG()) < 1e-4
                && Math.abs(c.getB() - n.getB()) < 1e-4;
    }

    /** Unseat whoever is at the wheel (the single-player exit). */
    @Register
    public void exitDriver(Node v) {
        if (v instanceof Vehicle car && car.getOccupant() != null) car.tryExit();
    }

    /** Seat any character (a Player included) — what a probe needs to drive a trigger volume. */
    @Register
    public void seatCharacter(Node v, Node c) {
        if (v instanceof Vehicle car && c instanceof Character ch) car.tryEnter(ch);
    }

    /** The single-player carjack a player's Enter key runs. */
    @Register
    public void carjack(Node v, Node player) {
        if (v instanceof Vehicle car && player instanceof Character p) car.requestCarjack(p);
    }

    /**
     * Attach the shipped ambient-traffic brain to {@code v}, optionally as a race entrant (R2).
     * {@code Vehicle.attachController} is plain Java — this is the same call {@code ZoneManager} makes
     * when it spawns a traffic car.
     */
    @Register
    public void attachTrafficBrain(Node v, boolean racing) {
        if (!(v instanceof Vehicle car)) return;
        com.openworld.ai.vehicle.VehicleAIController brain = new com.openworld.ai.vehicle.VehicleAIController();
        brain.racing = racing;
        car.attachController(brain);
    }

    /**
     * Flip an EXISTING brain's {@code racing} flag. Re-attaching a brain would lose its junction
     * membership (the arbiter registers a car on {@code body_entered}), so a probe measuring the
     * racing exception has to change the flag on the controller already in the junction.
     */
    @Register
    public void setRacing(Node v, boolean racing) {
        if (v instanceof Vehicle car
                && car.getController() instanceof com.openworld.ai.vehicle.VehicleAIController brain) {
            brain.racing = racing;
        }
    }

    /** Is this car's traffic brain currently yielding to a junction holder? Question-named readout. */
    @Register
    public boolean yieldingNow(Node v) {
        return v instanceof Vehicle car
                && car.getController() instanceof com.openworld.ai.vehicle.VehicleAIController brain
                && brain.shouldYield();
    }
}
