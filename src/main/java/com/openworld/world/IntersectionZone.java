package com.openworld.world;

import com.openworld.ai.vehicle.VehicleAIController;
import com.openworld.carrier.vehicle.Vehicle;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Area3D;
import godot.api.Node3D;
import godot.api.Engine;
import godot.core.Callable;
import godot.core.MethodCallable;
import godot.core.StringName;
import godot.global.GD;

import java.util.ArrayList;
import java.util.List;

/**
 * Junction right-of-way arbiter (PLAN.md I3b) — an {@link Area3D} covering an intersection plus a
 * short approach, carried by the {@code Road4Way} tile so placing a 4-way junction brings its own
 * traffic control.
 *
 * <p><b>Model:</b> first-come-first-served single occupancy. Vehicles entering the area are queued in
 * arrival order; the first one holds the junction and proceeds, everyone else {@link #blocks yields}
 * (brakes) until the holder clears the area, then the next in line proceeds. This is deadlock-free
 * (there is always exactly one holder while the queue is non-empty) and prevents the T-bones you get
 * with no right-of-way. It is intentionally conservative (one car crosses at a time) — concurrent
 * non-conflicting movements + signals are the fuller lane-graph, still future work.
 *
 * <p>Only AI vehicles ({@link VehicleAIController}) are arbitrated; a player-driven vehicle is never
 * forced to yield. Set the area's {@code collision_mask} to the vehicle body layer so the
 * {@code body_entered}/{@code body_exited} signals fire.
 */
@Script(className = "IntersectionZone")
public class IntersectionZone extends Area3D {

    public static final String GROUP = "intersection";

    /** Vehicles currently inside, in arrival order. Head of the list holds the junction. */
    private final List<Vehicle> queue = new ArrayList<>();

    /**
     * A holder that has stood still this long hands the junction to the next car in line (it goes to
     * the back of the queue). Single occupancy is only deadlock-free while the holder can always move:
     * on a big pad the holder's own obstacle ray can stop it behind a car that is QUEUED inside the
     * area waiting for the holder -- each waiting on the other for ever, which is what the island's
     * 5-arm pads produced (ambient cars reclaimed as {@code stalled} 12 s after stopping at a mouth).
     * 0 turns the rule off (the old behaviour, and the control).
     */
    public static final long HOLDER_STALL_MS = 2500;
    /** Below this speed the holder counts as standing still. */
    public static final double HOLDER_STALL_SPEED = 0.5;

    private Vehicle stallHead;
    private long stallSinceFrame;

    @Register
    @Override
    public void _ready() {
        addToGroup(new StringName(GROUP));
        // godot-jvm registers @Register methods under their snake_case names.
        connect(new StringName("body_entered"), MethodCallable.createUnsafe(this, "on_body_entered"));
        connect(new StringName("body_exited"), MethodCallable.createUnsafe(this, "on_body_exited"));
    }

    @Register
    public void onBodyEntered(Node3D body) {
        if (!(body instanceof Vehicle v)) return;
        if (!(v.getController() instanceof VehicleAIController ctrl)) return; // player isn't auto-yielded
        if (!queue.contains(v)) queue.add(v);
        ctrl.enterIntersection(this);
    }

    @Register
    public void onBodyExited(Node3D body) {
        if (!(body instanceof Vehicle v)) return;
        queue.remove(v);
        if (v.getController() instanceof VehicleAIController ctrl) ctrl.exitIntersection(this);
    }

    /** True if {@code v} must yield: another vehicle holds the junction (is ahead of v in the queue). */
    public boolean blocks(Vehicle v) {
        queue.removeIf(x -> !GD.isInstanceValid(x));
        if (queue.isEmpty()) return false;
        rotateStalledHolder();
        return queue.get(0) != v;
    }

    private void rotateStalledHolder() {
        if (HOLDER_STALL_MS <= 0 || queue.size() < 2) { stallHead = null; return; }
        Vehicle head = queue.get(0);
        // The PHYSICS clock, not wall time: a headless --fixed-fps run is not real-time.
        long now = Engine.INSTANCE.getPhysicsFrames();
        long stallFrames = HOLDER_STALL_MS * Engine.INSTANCE.getPhysicsTicksPerSecond() / 1000;
        if (head != stallHead || head.getLinearVelocity().length() > HOLDER_STALL_SPEED) {
            stallHead = head;
            stallSinceFrame = now;
            return;
        }
        if (now - stallSinceFrame < stallFrames) return;
        queue.remove(0);
        queue.add(head);
        stallHead = queue.get(0);
        stallSinceFrame = now;
    }
}
