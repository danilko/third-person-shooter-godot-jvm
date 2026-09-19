package com.openworld.carrier.vehicle;

import com.openworld.carrier.vehicle.VehicleDamageRules.Kind;
import com.openworld.character.Health;
import com.openworld.util.CollisionLayers;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.*;
import godot.core.*;
import godot.global.GD;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;

import static com.openworld.carrier.vehicle.VehicleDamageRules.*;

/**
 * A car that comes apart in pieces, GTA III / San Andreas style: the node that applies {@link VehicleDamageRules}
 * to a component model (blender/VEHICLE_AUTHORING.md). A child of the {@link Vehicle} named {@code DamageModel};
 * a vehicle without one behaves exactly as before.
 *
 * <p>It finds the parts BY NAME under {@link #modelPath} (the glb's nodes {@code bonnet}, {@code door_lf}, …, each
 * with its origin on its hinge and a {@code dam} blend shape) and walks each one OK → DENTED → LOOSE → OFF:
 * <ul>
 *   <li><b>Crashes</b> arrive from {@code Vehicle._integrateForces} as contact impulses ({@link #queueImpact}); the
 *       steps of one crash are summed into one impact (a crash spans a few physics steps, and a per-step threshold
 *       would under-count it) and shared among the parts near its point. Only the peer that simulates the car sees
 *       contacts, so only it does this.</li>
 *   <li><b>Bullets</b> arrive from {@code ImpactManager} ({@link #applyHit}) on the host.</li>
 *   <li><b>Everyone else</b> gets the result through the vehicle snapshot's part mask ({@link #applyReplicatedMask}),
 *       which MAX-merges: states only rise.</li>
 * </ul>
 * What a state LOOKS like is local to every peer and needs no message: a dent is the {@code dam} weight, a loose part
 * swings on its hinge driven by the car's own motion (read from its position, so a puppet flaps its doors too), and
 * a part that comes off becomes a short-lived physics body that never blocks a car (cosmetic, like a knocked-down
 * pole). When the car is destroyed, the loose panels blow off and the wreck is this car, burnt ({@link #dressWreck})
 * instead of a grey box.
 */
@Script(className = "VehicleDamageModel")
public class VehicleDamageModel extends Node {

    /** The imported model whose children are the named parts. */
    @Export public NodePath modelPath = new NodePath("../Model");
    /** Name of the body-colour material (a surface using it is repainted per car). Empty = no repaint. */
    @Export public String paintMaterial = "car";
    /** Damage points a bullet puts into the part it hits, per point of weapon damage. */
    @Export public float bulletPointsPerDamage = 0.6f;
    /** Metres per second² per (m/s)² of forward speed lifting a loose bonnet or boot: the flutter at speed. */
    @Export public float airLift = 0.05f;
    /** Seconds a fallen part lies before it is removed. */
    @Export public float debrisLifetime = 25f;
    /** Control knob for probes: off = the car never changes (parts, dents, debris), as before this node existed. */
    @Visible public boolean damageEnabled = true;

    /** The world never holds more fallen parts than this; the oldest goes first. */
    private static final int MAX_DEBRIS = 32;
    private static final ArrayDeque<RigidBody3D> DEBRIS = new ArrayDeque<>();
    private static final Vector3 GRAVITY = new Vector3(0, -9.8, 0);
    /** Paint colours a car is sprayed with, picked from its id so every peer agrees (GTA's carcols idea). */
    private static final Color[] PAINT = {
            new Color(0.62, 0.05, 0.04, 1), new Color(0.05, 0.12, 0.45, 1), new Color(0.85, 0.85, 0.83, 1),
            new Color(0.03, 0.03, 0.035, 1), new Color(0.45, 0.46, 0.48, 1), new Color(0.9, 0.55, 0.05, 1),
            new Color(0.1, 0.35, 0.15, 1), new Color(0.75, 0.7, 0.55, 1)};

    private static final class Part {
        String name; Kind kind; MeshInstance3D mesh; int slot; int blend = -1;
        Transform3D rest;               // local to its parent (the model)
        double[] min, max;              // vehicle-local box, for impact attribution
        double[] lever, axis;           // vehicle-local, hinge -> centre, and the opening axis
        Vector3 axisParent;             // the same axis in the part's parent frame
        double maxOpen, damage, angle, vel, damping;
        int state = OK;
        double doorTime = -1.0;         // >= 0 while an enter/exit opening plays
        AnimatableBody3D collider;      // a door's own kinematic body, solid while the door is off its latch
        Vector3 boxCentre;              // mesh-local centre of the part's box
    }

    /** The enter/exit door: opens this far, over OPEN s, holds until HOLD s, and is shut again by END s. */
    private static final double DOOR_OPEN_DEG = 65.0, DOOR_OPEN = 0.25, DOOR_HOLD = 0.75, DOOR_END = 1.05;
    /**
     * A door's box is solid only while the door stands off its latch; closed, the hull already covers it. It is a
     * separate KINEMATIC body, never a shape on the car's RigidBody: a character stepping out stands where the door
     * opens, and a shape of the car overlapping them was resolved by throwing the CAR (measured: 100 m/s in one
     * frame). A kinematic door stops a character walking into it and is hit by bullets, and pushes the car nowhere.
     */
    private static final double COLLIDER_MIN_ANGLE = Math.toRadians(2.0);

    private Vehicle vehicle;
    private Node3D model;
    private final List<Part> parts = new ArrayList<>();
    private Part chassis;
    private int mask = 0;
    private boolean painted = false;

    // one crash = consecutive contact steps, summed
    private double crashDv = 0.0;
    private final double[] crashPoint = new double[3];
    private int quietSteps = 0;

    // the car's own motion, for the hinges (from its position, so a frozen puppet works too)
    private Vector3 lastPos, lastVel = Vector3.Companion.getZERO(), accel = Vector3.Companion.getZERO();

    @Register
    @Override
    public void _ready() {
        if (getParent() instanceof Vehicle v) vehicle = v;
        if (getNodeOrNull(modelPath) instanceof Node3D m) model = m;
        if (vehicle == null || model == null) {
            GD.printErr("[VehicleDamageModel] needs a Vehicle parent and a model at " + modelPath.getPath());
            return;
        }
        // NB godot-jvm rc1: Transform3D.times(Transform3D) MUTATES its receiver and returns it, so every product
        // here starts from a fresh getter result - a transform kept across the loop would accumulate every part.
        Basis modelBasisInv = model.getTransform().getBasis().inverse();
        for (Node child : model.getChildren()) {
            if (!(child instanceof MeshInstance3D mi)) continue;
            Kind kind = kindOf(mi.getName().toString());
            if (kind == Kind.WHEEL || kind == Kind.UNKNOWN) continue;
            Part p = new Part();
            p.name = mi.getName().toString();
            p.kind = kind;
            p.mesh = mi;
            p.slot = slotOf(p.name);
            p.blend = mi.findBlendShapeByName("dam");
            p.rest = mi.getTransform();
            Transform3D local = vehicle.getGlobalTransform().affineInverse().times(mi.getGlobalTransform());
            AABB box = mi.getAabb();
            p.min = new double[]{1e9, 1e9, 1e9};
            p.max = new double[]{-1e9, -1e9, -1e9};
            for (int i = 0; i < 8; i++) {
                Vector3 c = local.times(box.getEndpoint(i));
                double[] cc = {c.getX(), c.getY(), c.getZ()};
                for (int k = 0; k < 3; k++) { p.min[k] = Math.min(p.min[k], cc[k]); p.max[k] = Math.max(p.max[k], cc[k]); }
            }
            Vector3 hinge = local.getOrigin();
            Vector3 centre = local.times(box.getPosition().plus(box.getSize().times(0.5)));
            p.lever = new double[]{centre.getX() - hinge.getX(), centre.getY() - hinge.getY(), centre.getZ() - hinge.getZ()};
            p.axis = openAxis(kind, p.lever, centre.getX());
            if (p.axis != null) {
                Vector3 a = modelBasisInv.xform(new Vector3(p.axis[0], p.axis[1], p.axis[2]));
                p.axisParent = a.normalized();
            }
            p.maxOpen = maxOpen(kind);
            p.damping = kind == Kind.DOOR ? 1.5 : (kind == Kind.BUMPER ? 4.0 : 3.0);
            p.boxCentre = box.getPosition().plus(box.getSize().times(0.5));
            if (kind == Kind.DOOR) {
                AnimatableBody3D body = new AnimatableBody3D();
                body.setName(new StringName("DoorBody_" + p.name));
                body.setSyncToPhysics(false);
                body.setCollisionLayer(0);                                  // off until the door opens
                body.setCollisionMask(0);                                   // it is hit, it detects nothing
                CollisionShape3D cs = new CollisionShape3D();
                BoxShape3D shape = new BoxShape3D();
                shape.setSize(box.getSize());
                cs.setShape(shape);
                body.addChild(cs);
                vehicle.callDeferred(new StringName("add_child"), body);   // the car is busy readying its children
                vehicle.addCollisionExceptionWith(body);
                p.collider = body;
            }
            if (kind == Kind.CHASSIS) chassis = p; else parts.add(p);
        }
        lastPos = vehicle.getGlobalPosition();
    }

    // ── inputs ──────────────────────────────────────────────────────────────────────────────────────

    /** One physics step's crash contact (vehicle-local point, change of velocity in m/s). Simulating peer only. */
    public void queueImpact(Vector3 localPoint, double deltaV) {
        if (!damageEnabled || deltaV <= 0.0) return;
        double w = crashDv + deltaV;
        crashPoint[0] = (crashPoint[0] * crashDv + localPoint.getX() * deltaV) / w;
        crashPoint[1] = (crashPoint[1] * crashDv + localPoint.getY() * deltaV) / w;
        crashPoint[2] = (crashPoint[2] * crashDv + localPoint.getZ() * deltaV) / w;
        crashDv = w;
        quietSteps = 0;
    }

    /** A bullet (or melee) hit at a world point: the part under it takes points. Host / single player. */
    public void applyHit(Vector3 worldPoint, float damage) {
        if (!damageEnabled || vehicle == null || worldPoint == null) return;
        Vector3 l = vehicle.getGlobalTransform().affineInverse().times(worldPoint);
        double[] p = {l.getX(), l.getY(), l.getZ()};
        Part best = null;
        double bestShare = 0.0;
        for (Part part : parts) {
            double s = share(part.min, part.max, p);
            if (s > bestShare) { bestShare = s; best = part; }
        }
        if (best != null && bestShare > 0.5) addDamage(best, damage * bulletPointsPerDamage);
    }

    /** Merge a replicated part mask (the snapshot's): every part is at least as broken as it says. */
    @Register
    public void applyReplicatedMask(int remote) {
        if (vehicle == null || remote == mask) return;
        for (Part p : parts) {
            int want = stateAt(remote, p.slot);
            if (want > p.state) {
                p.damage = Math.max(p.damage, damageFor(p.kind, want));
                advance(p);
            }
        }
    }

    public int getMask() { return mask; }

    // ── the per-frame work ──────────────────────────────────────────────────────────────────────────

    @Register
    @Override
    public void _physicsProcess(double delta) {
        if (vehicle == null || delta <= 0.0) return;
        if (!painted) paint();
        flushCrash();
        trackMotion(delta);
        swing(delta);
        playDoors(delta);
        placeDoorColliders();
        if (chassis != null && chassis.blend >= 0 && vehicle.getNodeOrNull("Health") instanceof Health h
                && h.maxHealth > 0f) {
            chassis.mesh.setBlendShapeValue(chassis.blend, (float) chassisWeight(h.getCurrentHealth() / h.maxHealth));
        }
    }

    private void flushCrash() {
        if (crashDv <= 0.0) return;
        if (++quietSteps < 2) return;            // the crash is still going on
        double points = impactPoints(crashDv);
        if (points > 0.0) {
            for (Part p : parts) {
                double s = share(p.min, p.max, crashPoint);
                if (s > 0.0) addDamage(p, points * s);
            }
            VehicleConfig cfg = vehicle.getConfig();
            if (cfg.crashHealthPerDv > 0f && vehicle.getNodeOrNull("Health") instanceof Health h) {
                float dmg = (float) Math.max(0.0, crashDv - MIN_IMPACT_DV) * cfg.crashHealthPerDv;
                h.takeDamage(null, dmg, Vehicle.DAMAGE_SOURCE_COLLISION);
            }
        }
        crashDv = 0.0;
    }

    private void addDamage(Part p, double points) {
        if (points <= 0.0 || p.state >= OFF) return;
        p.damage += points;
        advance(p);
    }

    /** Brings a part's look up to its damage: dent weight always, and each new state once. */
    private void advance(Part p) {
        if (p.blend >= 0) p.mesh.setBlendShapeValue(p.blend, (float) dentWeight(p.damage));
        int next = Math.max(p.state, stateFor(p.kind, p.damage));
        if (next == p.state) return;
        if (next == LOOSE) p.vel = 1.5;                         // it gives: a small first swing
        if (next == OFF) detach(p, Vector3.Companion.getZERO());
        p.state = next;
        mask = withState(mask, p.slot, next);
    }

    private void trackMotion(double delta) {
        Vector3 pos = vehicle.getGlobalPosition();
        Vector3 vel = pos.minus(lastPos).div(delta);
        Vector3 a = vel.minus(lastVel).div(delta);
        if (a.length() > 80.0) a = a.normalized().times(80.0);   // a teleport or a respawn is not a crash
        accel = accel.lerp(a, 0.35);
        lastVel = vel;
        lastPos = pos;
    }

    private void swing(double delta) {
        Basis inv = vehicle.getGlobalBasis().inverse();
        Vector3 f = inv.xform(GRAVITY.minus(accel));                 // specific force, car frame
        Vector3 vLocal = inv.xform(lastVel);
        double fwd = -vLocal.getZ();
        double[] force = {f.getX(), f.getY(), f.getZ()};
        for (Part p : parts) {
            if (p.state != LOOSE || p.axis == null) continue;
            double acc = hingeAccel(p.axis, p.lever, force);
            if (p.kind == Kind.BONNET || p.kind == Kind.BOOT) {
                acc += airLift * fwd * Math.abs(fwd) * Math.cos(p.angle) * (p.kind == Kind.BONNET ? 1 : 0.4);
            }
            acc += (GD.randf() - 0.5) * Math.min(Math.abs(fwd), 30.0) * 0.6;   // buffeting
            double[] s = stepHinge(p.angle, p.vel, acc, p.damping, p.maxOpen, p.kind == Kind.DOOR ? 0.35 : 0.2, delta);
            p.angle = s[0];
            p.vel = s[1];
            p.mesh.setTransform(new Transform3D(new Basis(p.axisParent, (float) p.angle).times(p.rest.getBasis()),
                    p.rest.getOrigin()));
        }
    }

    // ── doors for getting in and out ────────────────────────────────────────────────────────────────

    /**
     * Opens and shuts the door on the side of {@code seatLocal} (a seat marker's position in the car): called by
     * {@code Vehicle.tryEnter} / {@code tryExit}, which run on EVERY peer, so every peer plays its own door and no
     * message is needed. A two-door car's rear seats use the front doors: the door is chosen by side, nearest
     * first. A door that is loose (already swinging) or gone is left alone.
     */
    public void openDoorFor(Vector3 seatLocal) {
        if (vehicle == null || seatLocal == null) return;
        Part best = null;
        double bestDz = Double.MAX_VALUE;
        for (Part p : parts) {
            if (p.kind != Kind.DOOR || p.state >= LOOSE) continue;
            double cx = (p.min[0] + p.max[0]) / 2;
            if (Math.signum(cx) != Math.signum(seatLocal.getX())) continue;
            double dz = Math.abs((p.min[2] + p.max[2]) / 2 - seatLocal.getZ());
            if (dz < bestDz) { bestDz = dz; best = p; }
        }
        if (best != null) best.doorTime = 0.0;
    }

    private void playDoors(double delta) {
        for (Part p : parts) {
            if (p.doorTime < 0.0 || p.axis == null) continue;
            if (p.state >= LOOSE) { p.doorTime = -1.0; continue; }   // it came loose meanwhile: physics has it
            p.doorTime += delta;
            double t = p.doorTime, open = Math.toRadians(DOOR_OPEN_DEG);
            if (t < DOOR_OPEN) {
                double u = t / DOOR_OPEN;
                p.angle = open * (1 - (1 - u) * (1 - u));                 // ease out: swung open
            } else if (t < DOOR_HOLD) {
                p.angle = open;
            } else if (t < DOOR_END) {
                double u = (t - DOOR_HOLD) / (DOOR_END - DOOR_HOLD);
                p.angle = open * (1 - u * u);                             // ease in: slammed
            } else {
                p.angle = 0.0;
                p.doorTime = -1.0;
            }
            p.mesh.setTransform(new Transform3D(new Basis(p.axisParent, (float) p.angle).times(p.rest.getBasis()),
                    p.rest.getOrigin()));
        }
    }

    /** Each door's box follows the door and is solid only while the door is off its latch and still on the car. */
    private void placeDoorColliders() {
        for (Part p : parts) {
            if (p.collider == null || !p.collider.isInsideTree()) continue;
            boolean solid = p.state < OFF && p.angle > COLLIDER_MIN_ANGLE;
            int layer = solid ? CollisionLayers.VEHICLE : 0;
            if (p.collider.getCollisionLayer() != layer) p.collider.setCollisionLayer(layer);
            if (!solid) continue;
            // fresh products only: godot-jvm's Transform3D.times(Transform3D) mutates its receiver
            Transform3D local = vehicle.getGlobalTransform().affineInverse().times(p.mesh.getGlobalTransform());
            p.collider.setTransform(local.times(new Transform3D(Basis.Companion.getIDENTITY(), p.boxCentre)));
        }
    }

    // ── detaching ───────────────────────────────────────────────────────────────────────────────────

    private void detach(Part p, Vector3 kick) {
        if (!p.mesh.isVisible()) return;
        p.mesh.setVisible(false);
        if (p.kind == Kind.WINDSCREEN) return;                        // glass shatters; nothing falls
        RigidBody3D body = new RigidBody3D();
        body.setName(new StringName("CarPart_" + p.name));
        body.setCollisionLayer(0);                                    // debris never stops a car or a person
        body.setCollisionMask(CollisionLayers.WORLD);
        body.setMass(p.kind == Kind.DOOR ? 20f : (p.kind == Kind.BUMPER ? 8f : 14f));
        MeshInstance3D copy = (MeshInstance3D) p.mesh.duplicate();
        copy.setVisible(true);
        copy.setTransform(Transform3D.Companion.getIDENTITY());
        body.addChild(copy);
        AABB box = p.mesh.getAabb();
        CollisionShape3D cs = new CollisionShape3D();
        BoxShape3D shape = new BoxShape3D();
        Vector3 size = box.getSize();
        shape.setSize(new Vector3(Math.max(size.getX(), 0.05), Math.max(size.getY(), 0.05), Math.max(size.getZ(), 0.05)));
        cs.setShape(shape);
        cs.setPosition(box.getPosition().plus(size.times(0.5)));
        body.addChild(cs);
        Node scene = getTree().getCurrentScene();
        if (scene == null) return;
        Transform3D at = p.mesh.getGlobalTransform();
        scene.addChild(body);
        body.setGlobalTransform(at);
        Vector3 away = at.getOrigin().plus(at.getBasis().xform(cs.getPosition())).minus(vehicle.getGlobalPosition());
        away = new Vector3(away.getX(), 0, away.getZ()).normalized();
        body.setLinearVelocity(lastVel.plus(away.times(1.5)).plus(new Vector3(0, 1.2, 0)).plus(kick));
        body.setAngularVelocity(new Vector3(GD.randfRange(-3f, 3f), GD.randfRange(-3f, 3f), GD.randfRange(-3f, 3f)));
        SceneTreeTimer t = getTree().createTimer(debrisLifetime, false, true, false);
        t.connect(new StringName("timeout"), MethodCallable.createUnsafe(body, "queue_free"));
        DEBRIS.addLast(body);
        while (DEBRIS.size() > MAX_DEBRIS) {
            RigidBody3D old = DEBRIS.pollFirst();
            if (old != null && GD.isInstanceValid(old)) old.queueFree();
        }
    }

    /** The car explodes: every panel that can come off is blown off, upward and outward (GTA's burning wreck). */
    public void blowOff() {
        if (vehicle == null) return;
        for (Part p : parts) {
            if (p.kind == Kind.WING || p.state >= OFF) continue;
            if (p.kind == Kind.WINDSCREEN || p.kind == Kind.BONNET || p.kind == Kind.BOOT || GD.randf() < 0.6f) {
                p.damage = damageFor(p.kind, OFF);
                if (p.blend >= 0) p.mesh.setBlendShapeValue(p.blend, 1f);
                detach(p, new Vector3(GD.randfRange(-2f, 2f), GD.randfRange(5f, 8f), GD.randfRange(-2f, 2f)));
                p.state = OFF;
                mask = withState(mask, p.slot, OFF);
            }
        }
    }

    /**
     * Makes the wreck scene look like THIS car burnt out: a copy of the model (with its dents, and without the parts
     * already gone), every surface charred, the wheels included; the wreck's placeholder boxes are hidden and its
     * collider takes the car's own hull.
     */
    public void dressWreck(Node wreck) {
        if (model == null || !(wreck instanceof Node3D w)) return;
        StandardMaterial3D burnt = new StandardMaterial3D();
        burnt.setAlbedo(new Color(0.045, 0.04, 0.035, 1));
        burnt.setRoughness(1f);
        burnt.setMetallic(0.2f);
        Node3D shell = new Node3D();
        shell.setName(new StringName("BurntShell"));
        for (Node n : allDescendants(vehicle)) {
            if (!(n instanceof MeshInstance3D mi) || !mi.isVisibleInTree()) continue;
            if (!isModelMesh(mi)) continue;
            MeshInstance3D c = (MeshInstance3D) mi.duplicate();
            for (Node ch : c.getChildren()) c.removeChild(ch);          // no hit boxes, no nested meshes
            c.setMaterialOverride(burnt);
            c.setTransform(vehicle.getGlobalTransform().affineInverse().times(mi.getGlobalTransform()));   // fresh: times() mutates
            shell.addChild(c);
        }
        w.addChild(shell);
        for (String n : new String[]{"Shell/Body", "Shell/Cabin"}) {
            if (w.getNodeOrNull(n) instanceof Node3D box) box.setVisible(false);
        }
        if (w.getNodeOrNull("Shell/Collision") instanceof CollisionShape3D col
                && vehicle.getNodeOrNull("CollisionShape3D") instanceof CollisionShape3D own) {
            col.setShape(own.getShape());
            col.setTransform(own.getTransform());
        }
    }

    /** A mesh of the car's own model: under the model node, or a model wheel adopted by a VehicleWheel. */
    private boolean isModelMesh(MeshInstance3D mi) {
        if (model.isAncestorOf(mi)) return true;
        String n = mi.getName().toString();
        return kindOf(n) == Kind.WHEEL;
    }

    private static List<Node> allDescendants(Node root) {
        List<Node> out = new ArrayList<>();
        ArrayDeque<Node> stack = new ArrayDeque<>();
        stack.push(root);
        while (!stack.isEmpty()) {
            Node n = stack.pop();
            out.add(n);
            for (Node c : n.getChildren()) stack.push(c);
        }
        return out;
    }

    // ── paint ───────────────────────────────────────────────────────────────────────────────────────

    /** Sprays the body colour from the car's id, so every peer paints a car the same (no message). */
    private void paint() {
        painted = true;
        if (paintMaterial == null || paintMaterial.isEmpty() || vehicle.getCharacterInfo() == null) return;
        String id = vehicle.getCharacterInfo().characterId;
        if (id == null || id.isEmpty()) { painted = false; return; }
        Color colour = PAINT[Math.floorMod(id.hashCode(), PAINT.length)];
        StandardMaterial3D sprayed = null;
        for (Node n : allDescendants(model)) {
            if (!(n instanceof MeshInstance3D mi) || mi.getMesh() == null) continue;
            Mesh mesh = mi.getMesh();
            for (int s = 0; s < mesh.getSurfaceCount(); s++) {
                Material m = mesh.surfaceGetMaterial(s);
                if (!(m instanceof StandardMaterial3D sm) || !paintMaterial.equals(sm.getName())) continue;
                if (sprayed == null) {
                    sprayed = (StandardMaterial3D) sm.duplicate();
                    sprayed.setAlbedo(colour);
                    sprayed.setMetallic(0.55f);
                    sprayed.setRoughness(0.3f);
                }
                mi.setSurfaceOverrideMaterial(s, sprayed);
            }
        }
    }

    // ── probe readouts ──────────────────────────────────────────────────────────────────────────────

    @Register public int partStateNow(String name) {
        for (Part p : parts) if (p.name.equals(name)) return p.state;
        return -1;
    }

    @Register public double partDamageNow(String name) {
        for (Part p : parts) if (p.name.equals(name)) return p.damage;
        return -1;
    }

    @Register public double partAngleNow(String name) {
        for (Part p : parts) if (p.name.equals(name)) return Math.toDegrees(p.angle);
        return -1;
    }

    @Register public int partMaskNow() { return mask; }

    /** True while the named door's own collider is solid (probe). */
    @Register public boolean doorColliderSolidNow(String name) {
        for (Part p : parts) if (p.name.equals(name) && p.collider != null) return p.collider.getCollisionLayer() != 0;
        return false;
    }

    @Register public String partDebugNow() {
        StringBuilder b = new StringBuilder();
        for (Part p : parts) b.append(String.format("%s slot=%d state=%d dmg=%.1f min=(%.2f,%.2f,%.2f) max=(%.2f,%.2f,%.2f)%n",
                p.name, p.slot, p.state, p.damage, p.min[0], p.min[1], p.min[2], p.max[0], p.max[1], p.max[2]));
        return b.toString();
    }

    @Register public int partCountNow() { return parts.size() + (chassis != null ? 1 : 0); }

    /** Adds damage points to a named part as a crash would (probe / debug console). */
    @Register public void damagePart(String name, double points) {
        for (Part p : parts) if (p.name.equals(name)) addDamage(p, points);
    }

    /** Queues a crash at a vehicle-local point, as Vehicle._integrateForces does (probe). */
    @Register public void crashAt(Vector3 localPoint, double deltaV) {
        queueImpact(localPoint, deltaV);
    }

    @Register public int debrisCountNow() {
        DEBRIS.removeIf(d -> !GD.isInstanceValid(d));
        return DEBRIS.size();
    }
}
