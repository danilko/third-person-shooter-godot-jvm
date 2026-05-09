package com.vehicle;

import com.character.*;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Node;
import godot.api.VehicleBody3D;
import godot.core.StringName;

/**
 * Base driveable vehicle body — the Controllable peer to Character on foot.
 *
 * Equivalent to VehicleBody3D extended with the Controller/UserCommand protocol
 * from Phase 3/4. A Controller child (VehicleAIController or PlayerController)
 * generates a UserCommand each physics tick; applyCommand() maps the vehicle
 * fields (throttle, steering, handbrake) to Godot's VehicleBody3D physics.
 *
 * Added to the "characters" group so AI targeting (AICharacter.discoverTarget)
 * and the kill-feed (CharacterHUD) treat vehicles as valid targets.
 *
 * Controller hot-swap (Phase 5):
 *   Controller ctrl = vehicle.detachController();
 *   ctrl.setTarget(otherBody);
 *   otherBody.attachController(ctrl);
 */
@RegisterClass(className = "VehicleBody")
public class VehicleBody extends VehicleBody3D implements Controllable {

    // ── Inspector exports ─────────────────────────────────────────────────────

    @RegisterProperty @Export public CharacterInfo characterInfo;

    /** Maximum engine force in Newtons applied to drive wheels. */
    @RegisterProperty @Export public float engineForce = 150.0f;

    /** Braking force applied when handbrake is engaged or vehicle is idle. */
    @RegisterProperty @Export public float brakeStrength = 6.0f;

    /** Maximum steering angle in radians (≈ 0.35 rad ≈ 20°). */
    @RegisterProperty @Export public float maxSteerAngle = 0.35f;

    /**
     * Idle drag brake — applied when throttle is zero and handbrake is off.
     * Prevents infinite rolling on slopes; tuned in the editor.
     */
    @RegisterProperty @Export public float idleBrake = 0.5f;

    // ── Runtime state ─────────────────────────────────────────────────────────

    protected Controller controller;
    protected com.character.Health healthNode;

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _ready() {
        if (characterInfo == null) characterInfo = new CharacterInfo();
        addToGroup(new StringName("characters"), false);

        Node h = getNodeOrNull("Health");
        if (h instanceof com.character.Health hn) healthNode = hn;

        for (Node child : getChildren()) {
            if (child instanceof Controller c) { controller = c; break; }
        }
    }

    @RegisterFunction
    @Override
    public void _physicsProcess(double delta) {
        if (controller == null || !controller.isAuthority()) return;
        UserCommand cmd = controller.gatherInput(delta);
        applyCommand(cmd, delta);
    }

    // ── Controllable ──────────────────────────────────────────────────────────

    @Override
    public void applyCommand(UserCommand cmd, double delta) {
        if (cmd.handbrake) {
            setEngineForce(0f);
            setBrake(brakeStrength);
        } else {
            setEngineForce(cmd.throttle * engineForce);
            setBrake(cmd.throttle == 0f ? idleBrake : 0f);
        }
        setSteering(cmd.steering * maxSteerAngle);
    }

    @Override
    public CharacterInfo getCharacterInfo() {
        return characterInfo;
    }

    // ── Controller hot-swap ───────────────────────────────────────────────────

    public Controller detachController() {
        if (controller == null) return null;
        Controller ctrl = controller;
        removeChild(ctrl);
        controller = null;
        return ctrl;
    }

    public void attachController(Controller ctrl) {
        if (controller != null) removeChild(controller);
        controller = ctrl;
        addChild(ctrl);
    }

    // ── Utility ───────────────────────────────────────────────────────────────

    public boolean isAlive() {
        return healthNode == null || !healthNode.isDead();
    }
}
