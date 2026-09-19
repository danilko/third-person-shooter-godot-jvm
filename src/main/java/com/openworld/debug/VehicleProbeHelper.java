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
 * {@code probe_zone_trigger.gd} (F3), {@code probe_race.gd} (R2) and {@code probe_explosive_damage.gd}.
 */
@Script(className = "VehicleProbeHelper")
public class VehicleProbeHelper extends Node {

    /** Seat {@code ai} (an AI, or a Player for a HUD shot) at the wheel of {@code v} (the ZoneManager traffic path: an AI car keeps its brain). */
    @Register
    public void seatDriver(Node v, Node ai) {
        if (v instanceof Vehicle car && ai instanceof Character a) car.tryEnter(a);
    }

    /** Kill {@code c} outright through its own Health, the way a shot would. */
    @Register
    public void kill(Node c) {
        if (c != null && c.getNodeOrNull("Health") instanceof Health h) h.takeDamage(null, 1.0e6f, "probe");
    }

    /**
     * One weapon hit of {@code damage} on {@code body}, through {@code ImpactManager.processHit} — the path
     * every bullet, pellet and melee swing takes, so the target's {@code hitDamageMultiplier} applies.
     * Used by {@code probe_explosive_damage.gd}.
     */
    @Register
    public void weaponHit(Node impactManager, Node body, float damage) {
        if (impactManager instanceof com.openworld.world.manager.ImpactManager im && body instanceof godot.api.Node3D b) {
            im.processHit(new com.openworld.world.HitInfo(b, b.getGlobalPosition(), new godot.core.Vector3(0, 1, 0)),
                    damage, "probe", null, "probe", "", null);
        }
    }

    /** One weapon hit on {@code body} at world point {@code at} through {@code ImpactManager.processHit} (probe_component_car.gd). */
    @Register
    public void weaponHitAt(Node impactManager, Node body, godot.core.Vector3 at, float damage) {
        if (impactManager instanceof com.openworld.world.manager.ImpactManager im && body instanceof godot.api.Node3D b) {
            im.processHit(new com.openworld.world.HitInfo(b, at, new godot.core.Vector3(0, 1, 0)),
                    damage, "probe", null, "probe", "", null);
        }
    }

    /** Flatten tire {@code index} of {@code v} (the HUD damage diagram's probe). */
    @Register
    public void flattenTire(Node v, int index) {
        if (v instanceof Vehicle car && index >= 0 && index < car.getWheels().size()) car.getWheels().get(index).setFlat(true);
    }

    /** One blast through {@code ExplosionManager.triggerExplosion} (no push, so bodies stay put). */
    @Register
    public void blast(Node explosionManager, godot.core.Vector3 at, float radius, float maxDamage) {
        if (explosionManager instanceof com.openworld.world.manager.ExplosionManager em) {
            em.triggerExplosion(at, radius, maxDamage, 0f, "probe", "", "probe", null, null);
        }
    }

    /** Set a character's view pitch in degrees (up positive) -- probe_w35_anims.gd throws at chosen angles. */
    @Register
    public void setViewPitch(Node c, double pitchDeg) {
        if (c instanceof com.openworld.character.Character ch) ch.controlRotation.pitch = pitchDeg;
    }

    /** Set a character's view yaw and pitch in degrees (world; pitch up positive) -- probe_grenade_world.gd. */
    @Register
    public void setView(Node c, double yawDeg, double pitchDeg) {
        if (c instanceof com.openworld.character.Character ch) {
            ch.controlRotation.yaw = yawDeg;
            ch.controlRotation.pitch = pitchDeg;
        }
    }

    /** A blast WITH its push — probe_w35_anims.gd measures that a body it kills is thrown, not dropped. */
    @Register
    public void blastPush(Node explosionManager, godot.core.Vector3 at, float radius, float maxDamage, float push) {
        if (explosionManager instanceof com.openworld.world.manager.ExplosionManager em) {
            em.triggerExplosion(at, radius, maxDamage, push, "probe", "", "probe", null, null);
        }
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

    /** Seat {@code c} as a PASSENGER in seat {@code seat} (>= 1) — probe_w35_anims.gd's passenger pose. */
    @Register
    public void seatPassenger(Node v, Node c, int seat) {
        if (v instanceof Vehicle car && c instanceof Character ch) car.tryEnter(ch, seat);
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
