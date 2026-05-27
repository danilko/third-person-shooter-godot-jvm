package com.character;

import com.vehicle.Vehicle;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Input;
import godot.api.Timer;
import godot.core.Vector3;

/**
 * Translates human keyboard/mouse input into a UserCommand each tick.
 *
 * Equivalent to Unreal's APlayerController / Source Engine's CBasePlayer command
 * generation. Lives as a child node of a Controllable (Player or Vehicle).
 * Detects the body type each tick via getControllable() and generates the
 * appropriate command fields:
 *   Player body → movement, combat, weapon, jump, stance fields
 *   Vehicle     → throttle, steering, handbrake, drift fields
 *
 * Hot-swap (Phase 5): call setTarget(newBody) before reparenting so gatherInput()
 * immediately generates the correct command type for the incoming body.
 *
 * Network (Phase 4): on the owning client this runs locally for prediction;
 * the resulting UserCommand is stamped with a monotone sequenceNumber and stored
 * in the predictionBuffer ring buffer. When the server sends back a corrected
 * state, reconcile(serverAck) discards acknowledged entries and the caller
 * replays unacknowledged commands against the snapped server state.
 */
@RegisterClass(className = "PlayerController")
public class PlayerController extends Controller {

    private static final int BUFFER_SIZE = 64;

    @Export
    @RegisterProperty
    public float minIkDist = 1.5f;

    // ── Client-side prediction state ──────────────────────────────────────────
    private int              localSequence    = 0;
    private final UserCommand[] predictionBuffer = new UserCommand[BUFFER_SIZE];

    // ── Cached body references (re-resolved when body type changes) ───────────
    private Player     cachedPlayer;
    private Timer      cachedAimStayTimer;
    private Vehicle     cachedVehicle;

    @RegisterFunction
    @Override
    public void _ready() {
        resolveBody();
    }

    private void resolveBody() {
        Controllable c = getControllable();
        if (c instanceof Player p) {
            cachedPlayer       = p;
            cachedAimStayTimer = (Timer) p.getNode("AimStayTimer");
            cachedVehicle      = null;
        } else if (c instanceof Vehicle v) {
            cachedVehicle      = v;
            cachedPlayer       = null;
            cachedAimStayTimer = null;
        } else {
            cachedPlayer  = null;
            cachedVehicle = null;
        }
    }

    @Override
    public UserCommand gatherInput(double delta) {
        // Re-resolve if the body has changed (hot-swap or first tick after reparent).
        Controllable c = getControllable();
        if (c instanceof Player p && p != cachedPlayer) resolveBody();
        else if (c instanceof Vehicle v && v != cachedVehicle) resolveBody();

        if (cachedVehicle != null) return gatherVehicleInput();
        if (cachedPlayer  != null) return gatherCharacterInput();
        return new UserCommand();
    }

    // ── Character (on-foot) input ─────────────────────────────────────────────

    private UserCommand gatherCharacterInput() {
        UserCommand cmd = new UserCommand();
        Input inp = Input.INSTANCE;
        Player body = cachedPlayer;

        boolean isFps = body.isFpsMode;

        // ── Movement ──────────────────────────────────────────────────────────
        // Signs match Godot's -Z-forward convention: W → moveZ = -1 (world -Z = forward).
        // Left/right: D (+X) = camera-right, A (-X) = camera-left.
        float moveX = inp.getActionStrength("right") - inp.getActionStrength("left");
        float moveZ = inp.getActionStrength("back")  - inp.getActionStrength("forward");
        cmd.movementDirection.setX(moveX);
        cmd.movementDirection.setZ(moveZ);

        if (cmd.movementDirection.lengthSquared() > 0.001) {
            cmd.movementType = inp.isActionPressed("walk", false)
                    ? MovementType.WALK : MovementType.SPRINT;
        }

        // ── Combat / aim ──────────────────────────────────────────────────────
        if (isFps) {
            cmd.wantCombat = true;
        } else {
            boolean aimOrFire = inp.isActionPressed("aim", false)
                             || inp.isActionPressed("fire", false);

            Timer aimStayTimer = cachedAimStayTimer;
            if (aimOrFire) {
                aimStayTimer.stop();
            } else if (body.isCombat() && (inp.isActionJustReleased("aim", false)
                                        || inp.isActionJustReleased("fire", false))) {
                aimStayTimer.start();
            }
            cmd.wantCombat = aimOrFire || (body.isCombat() && !aimStayTimer.isStopped());
        }

        // ── Aim target (IK-clamped; hitscan still uses aimRay directly) ─────────
        if (cmd.wantCombat) {
            Vector3 rayDeg = body.aimRay.getRotationDegrees();
            body.aimRay.setRotationDegrees(new Vector3(rayDeg.getX(), 0.0f, 0.0f));

            Vector3 rayOrigin = body.aimRay.getGlobalTransform().getOrigin();
            Vector3 farPoint  = body.aimRay.toGlobal(body.aimRay.getTargetPosition());

            if (body.aimRay.isColliding()) {
                Vector3 hit  = body.aimRay.getCollisionPoint();
                float   dist = (float) hit.minus(rayOrigin).length();
                if (dist >= minIkDist) {
                    cmd.aimTargetPosition = hit;
                } else {
                    // Too close: push along the ray direction to keep IK pose natural.
                    // Bullets still hit the real collision point via aimRay.
                    Vector3 dir = farPoint.minus(rayOrigin).normalized();
                    cmd.aimTargetPosition = rayOrigin.plus(dir.times(minIkDist));
                }
            } else {
                cmd.aimTargetPosition = farPoint;
            }
        }

        // ── Weapon / body actions ─────────────────────────────────────────────
        cmd.fire    = inp.isActionPressed("fire", false);
        cmd.reload  = inp.isActionJustPressed("reload", false);
        cmd.drop    = inp.isActionJustPressed("drop", false);
        cmd.jump    = inp.isActionJustPressed("jump", false);
        cmd.roll    = !isFps && inp.isActionJustPressed("roll", false);

        // Hold-to-hold crouch/crawl.
        // setStance() has a built-in toggle (same == current → UPRIGHT), so we must only
        // call it on the key-press and key-release edges — not every frame while held.
        // justPressed  → enter the stance (fires once per press, toggle goes standing→crouched)
        // justReleased → request UPRIGHT (fires once on release, toggle goes crouched→standing)
        // neither      → desiredStance stays null, applyInput skips the setStance call
        for (String stanceKey : body.stances.keys()) {
            if (StanceName.DRIVE_CARRIER.getKey().equals(stanceKey)) continue;
            String key = stanceKey.toLowerCase();
            if (inp.isActionJustPressed(key, false)) {
                cmd.desiredStance = StanceName.fromKey(stanceKey);
                break;
            }
            if (inp.isActionJustReleased(key, false)) {
                cmd.desiredStance = StanceName.UPRIGHT;
                break;
            }
        }

        // ── Weapon slot quick-switch ──────────────────────────────────────────
        // Keys 1–6 → slots 0–5 (PRIMARY×2, SECONDARY, MELEE, THROWABLE, CONSUMABLE)
        // Key 0    → slot 6 (OFFHAND) via weapon_unequip binding
        if (inp.isActionJustPressed("weapon_unequip", false)) {
            cmd.desiredWeapon = 6;
        } else {
            for (int i = 0; i < 6; i++) {
                if (inp.isActionJustPressed("weapon_slot_" + (i + 1), false)) {
                    cmd.desiredWeapon = i;
                    break;
                }
            }
        }

        // ── Vehicle enter (press "use" near a vehicle) ────────────────────────
        // Requires an "use" action in Project Settings → Input Map.
        cmd.enterExit = inp.isActionJustPressed("interact", false);

        // ── Sequence stamp + prediction buffer (Phase 4) ──────────────────────
        cmd.sequenceNumber = ++localSequence;
        predictionBuffer[cmd.sequenceNumber % BUFFER_SIZE] = cmd.copy();

        return cmd;
    }

    // ── Vehicle input ─────────────────────────────────────────────────────────

    /**
     * Maps keyboard to vehicle throttle/steering/handbrake using the same
     * directional action bindings as on-foot movement so no extra mappings
     * are needed in the input map.
     *
     *   forward / back  → throttle (+1 / -1)
     *   left / right    → steering (-1 / +1, negated to match Godot convention)
     *   jump            → handbrake
     *   drift           → drift mode (engage arcade slide)
     *   interact             → enter/exit vehicle (interact)
     */
    private UserCommand gatherVehicleInput() {
        UserCommand cmd = new UserCommand();
        Input inp = Input.INSTANCE;

        cmd.motor        = inp.getActionStrength("forward") - inp.getActionStrength("back");
        cmd.steering     = -(inp.getActionStrength("right") - inp.getActionStrength("left"));
        cmd.handbrake    = inp.isActionPressed("handbrake", false);
        cmd.brake        = inp.isActionPressed("brake", false);
        cmd.enterExit    = inp.isActionJustPressed("interact", false);
        // Weapon inputs: relayed to the occupant by Vehicle when weaponMode != NONE.
        cmd.fire         = inp.isActionPressed("fire", false);
        cmd.reload       = inp.isActionJustPressed("reload", false);
        // When there is no PASSENGER_WEAPON, "reload" doubles as a flip-upright reset.
        cmd.resetVehicle = inp.isActionJustPressed("reload", false);

        cmd.sequenceNumber = ++localSequence;
        predictionBuffer[cmd.sequenceNumber % BUFFER_SIZE] = cmd.copy();

        return cmd;
    }

    // ── Reconciliation (Phase 4) ──────────────────────────────────────────────

    /**
     * Discard prediction buffer entries confirmed by the server, then replay
     * any unacknowledged commands against the snapped server state.
     */
    public void reconcile(int serverAck) {
        for (int seq = serverAck; seq >= Math.max(0, serverAck - BUFFER_SIZE + 1); seq--) {
            predictionBuffer[seq % BUFFER_SIZE] = null;
        }
        // Phase 4 TODO: snap body to server state, then replay unacknowledged commands.
    }
}
