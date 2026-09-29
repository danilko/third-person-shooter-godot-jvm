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
    /** Material names of the glass surfaces (comma-separated): each one in a part is a window that breaks. */
    @Export public String glassMaterials = "window,glass";
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

    /**
     * A window: the glass surfaces of one part (a door's window, the body's glass, the windscreen), GTA III / SA
     * style. The first bullet cracks it, a second (or one heavy round) shatters it, and a broken window lets bullets
     * through to whoever sits behind it. Its triangles are the mesh's own, read once per mesh: no collider is added,
     * a shot that hits the car's hull asks the triangles instead ({@link #paneOnRay}).
     */
    private static final class Pane {
        Part part; int slot; int[] surfaces; float[] tris;   // tris: mesh-local, 9 floats a triangle
        double damage; int state = OK;
        boolean windscreen() { return part.kind == Kind.WINDSCREEN; }
    }

    /** A window a ray meets: which, and where (world). */
    public record GlassHit(java.lang.Object pane, Vector3 point) {}

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
    private final List<Pane> panes = new ArrayList<>();
    private Vector3 glassStopPoint = null;           // the point a bullet just stopped in a window (applyHit skips it)
    private double[] hullMin, hullMax;               // the hull's box, vehicle-local (where a bullet leaves the car)
    private Part chassis;
    private int mask = 0;
    private boolean painted = false;

    // one crash = consecutive contact steps, summed
    private double crashDv = 0.0;
    private final double[] crashPoint = new double[3];
    private int quietSteps = 0;
    private int crashSteps = 0;
    private Vector3 crashStartVel = Vector3.Companion.getZERO();
    private boolean syntheticCrash = false;          // crashAt: a probe's crash, scored as given

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
        findPanes();
        findHull();
    }

    private void findPanes() {
        java.util.Set<String> glass = new java.util.HashSet<>();
        for (String g : glassMaterials.split(",")) if (!g.isBlank()) glass.add(g.trim());
        List<Part> all = new ArrayList<>(parts);
        if (chassis != null) all.add(chassis);
        for (Part p : all) {
            int slot = paneSlotOf(p.name);
            Mesh mesh = p.mesh.getMesh();
            if (slot < 0 || mesh == null) continue;
            List<Integer> surf = new ArrayList<>();
            for (int s = 0; s < mesh.getSurfaceCount(); s++) {
                Material m = mesh.surfaceGetMaterial(s);
                if (m != null && glass.contains(m.getName().replaceAll("\\.\\d+$", ""))) surf.add(s);
            }
            if (surf.isEmpty()) continue;
            Pane pane = new Pane();
            pane.part = p;
            pane.slot = slot;
            pane.surfaces = surf.stream().mapToInt(Integer::intValue).toArray();
            pane.tris = trianglesOf(mesh, pane.surfaces);
            panes.add(pane);
        }
    }

    /** The triangles of some surfaces of a mesh (mesh-local), read once per mesh and shared by every car. */
    private static final java.util.Map<String, float[]> TRIS = new java.util.HashMap<>();

    /** Engine-free statics, but keyed by engine instance ids: dropped with the rest at close. */
    public static void clearCaches() { TRIS.clear(); }

    private static float[] trianglesOf(Mesh mesh, int[] surfaces) {
        String key = mesh.getInstanceId() + ":" + java.util.Arrays.toString(surfaces);
        return TRIS.computeIfAbsent(key, k -> {
            List<Float> out = new ArrayList<>();
            for (int s : surfaces) {
                VariantArray<java.lang.Object> arr = mesh.surfaceGetArrays(s);
                if (!(arr.get(0) instanceof PackedVector3Array pv)) continue;
                Vector3[] v = pv.toVector3Array();
                int[] idx = arr.get(12) instanceof PackedInt32Array pi ? pi.toIntArray() : null;
                int n = idx != null && idx.length > 0 ? idx.length : v.length;
                for (int i = 0; i + 2 < n; i += 3) {
                    for (int c = 0; c < 3; c++) {
                        Vector3 q = v[idx != null && idx.length > 0 ? idx[i + c] : i + c];
                        out.add((float) q.getX()); out.add((float) q.getY()); out.add((float) q.getZ());
                    }
                }
            }
            float[] f = new float[out.size()];
            for (int i = 0; i < f.length; i++) f[i] = out.get(i);
            return f;
        });
    }

    private void findHull() {
        hullMin = new double[]{1e9, 1e9, 1e9};
        hullMax = new double[]{-1e9, -1e9, -1e9};
        for (Node c : vehicle.getChildren()) {
            if (!(c instanceof CollisionShape3D cs) || !(cs.getShape() instanceof ConvexPolygonShape3D cp)) continue;
            Transform3D t = cs.getTransform();
            for (Vector3 q : cp.getPoints().toVector3Array()) {
                Vector3 w = t.times(q);
                double[] a = {w.getX(), w.getY(), w.getZ()};
                for (int k = 0; k < 3; k++) { hullMin[k] = Math.min(hullMin[k], a[k]); hullMax[k] = Math.max(hullMax[k], a[k]); }
            }
        }
        if (hullMin[0] > hullMax[0]) { hullMin = null; hullMax = null; }
    }

    // ── inputs ──────────────────────────────────────────────────────────────────────────────────────

    /** One physics step's crash contact (vehicle-local point, change of velocity in m/s). Simulating peer only. */
    public void queueImpact(Vector3 localPoint, double deltaV) {
        if (!damageEnabled || deltaV <= 0.0) return;
        if (crashDv <= 0.0) { crashStartVel = lastVel; crashSteps = 0; }   // the velocity before the contact
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
        if (glassStopPoint != null && glassStopPoint.distanceTo(worldPoint) < 0.01) {
            glassStopPoint = null;                                  // the window took this bullet, not the panel
            return;
        }
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
        for (Pane pane : panes) {
            if (pane.windscreen()) continue;                        // its part's slot, merged above
            int want = stateAt(remote, pane.slot);
            if (want > pane.state) {
                pane.damage = Math.max(pane.damage, want >= OFF ? glassArmor() + 1.0 : 1.0);
                setPane(pane, want, null);
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
        // the crash is still going on: score it once it goes quiet, or after MAX_CRASH_STEPS of unbroken contact
        // (a car pinned against something), when the next window starts from the velocity it has then
        if (++quietSteps < 2 && ++crashSteps < MAX_CRASH_STEPS) return;
        Vector3 v = vehicle.getLinearVelocity();
        if (syntheticCrash) syntheticCrash = false;
        else crashDv = crashDeltaV(crashDv, crashStartVel.getX(), crashStartVel.getY(), crashStartVel.getZ(),
                v.getX(), v.getY(), v.getZ());
        double points = impactPoints(crashDv);
        if (points > 0.0) {
            for (Part p : parts) {
                double s = share(p.min, p.max, crashPoint);
                if (s > 0.0) addDamage(p, points * s);
            }
            crashPanes(points);
            VehicleConfig cfg = vehicle.getConfig();
            if (cfg.crashHealthPerDv > 0f && vehicle.getNodeOrNull("Health") instanceof Health h) {
                float dmg = (float) Math.max(0.0, crashDv - MIN_IMPACT_DV) * cfg.crashHealthPerDv;
                h.takeDamage(null, dmg, Vehicle.DAMAGE_SOURCE_COLLISION);
            }
        }
        crashDv = 0.0;
    }

    /**
     * A crash reaches the windows near it: ordinary glass cracks at a dent's worth of crash points and shatters at a
     * loose door's; armoured glass needs {@code 1 + armour / 40} times that (police glass twice, the truck's four
     * times). The windscreen follows its own part's damage already.
     */
    private void crashPanes(double points) {
        double scale = 1.0 + glassArmor() / 40.0;
        for (Pane pane : panes) {
            if (pane.windscreen() || pane.state >= OFF) continue;
            double s = share(pane.part.min, pane.part.max, crashPoint);
            double got = points * s;
            if (got >= PANE_CRASH_AT * scale) {
                pane.damage = Math.max(pane.damage, glassArmor() + 1.0);
                setPane(pane, OFF, null);
            } else if (got >= DENT_AT * scale) {
                pane.damage = Math.max(pane.damage, 1.0);
                setPane(pane, DENTED, null);
            }
        }
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
        for (Pane pane : panes) {
            if (pane.part != p) continue;
            if (pane.windscreen()) setPane(pane, next, null);         // the windscreen IS its part
            else if (next >= LOOSE) setPane(pane, OFF, null);         // a door wrenched loose loses its window
        }
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
        for (Pane pane : panes) setPane(pane, OFF, null);
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

    // ── windows ─────────────────────────────────────────────────────────────────────────────────────

    /**
     * The window a shot meets where it struck the hull at {@code hullPoint}: the nearest glass triangle along the ray
     * within {@link #GLASS_REACH} of that point (glass sits on or just inside the hull). Null when the shot hit
     * paint, not glass. Every peer can ask it; it changes nothing.
     */
    public GlassHit paneOnRay(Vector3 from, Vector3 dir, Vector3 hullPoint) {
        if (vehicle == null || panes.isEmpty()) return null;
        double tHull = hullPoint.minus(from).length();
        Pane best = null;
        double bestT = Double.MAX_VALUE;
        for (Pane pane : panes) {
            if (pane.tris.length == 0) continue;
            Transform3D inv = pane.part.mesh.getGlobalTransform().affineInverse();
            Vector3 o = inv.times(from), d = inv.getBasis().xform(dir);
            double[] oo = {o.getX(), o.getY(), o.getZ()}, dd = {d.getX(), d.getY(), d.getZ()};
            float[] t = pane.tris;
            for (int i = 0; i + 8 < t.length; i += 9) {
                double h = rayTriangle(oo, dd, new double[]{t[i], t[i + 1], t[i + 2]},
                        new double[]{t[i + 3], t[i + 4], t[i + 5]}, new double[]{t[i + 6], t[i + 7], t[i + 8]});
                if (h >= 0 && Math.abs(h - tHull) <= GLASS_REACH && h < bestT) { bestT = h; best = pane; }
            }
        }
        return best == null ? null : new GlassHit(best, from.plus(dir.times(bestT)));
    }

    /** How far from the hull's surface (m) a window may lie and still be the thing a shot hit there. */
    public static final double GLASS_REACH = 0.35;

    /** True when a bullet passes this window: it is broken, or the part holding it is gone. */
    public boolean paneOpen(GlassHit g) {
        return g != null && g.pane() instanceof Pane p && (p.state >= OFF || !p.part.mesh.isVisibleInTree());
    }

    /** This car's window armour (VehicleConfig.glassArmor): 0 is ordinary glass. */
    public double glassArmor() {
        return vehicle != null && vehicle.getConfig() != null ? Math.max(0.0, vehicle.getConfig().glassArmor) : 0.0;
    }

    /**
     * The damage a round of {@code damage} carries through this window, read off its armour and what it has already
     * taken; 0 = the glass stops it. Changes nothing (a client's prediction reads this).
     */
    public float carriedThrough(GlassHit g, float damage) {
        if (!(g != null && g.pane() instanceof Pane p)) return damage;
        if (p.state >= OFF || !p.part.mesh.isVisibleInTree()) return damage;
        return (float) VehicleDamageRules.carriedThrough(p.damage, glassArmor(), damage);
    }

    /**
     * A bullet meets a whole window (host): it takes the window's armour down by the round's damage, cracking it, and
     * the round that exhausts the armour shatters it. Returns the damage the round carries on with (0 = stopped in
     * the glass, which then takes the hit instead of the panel behind it).
     */
    public float hitPane(GlassHit g, float damage, Vector3 dir) {
        if (!(g != null && g.pane() instanceof Pane p)) return damage;
        if (p.state >= OFF || !p.part.mesh.isVisibleInTree()) return damage;
        float carry = carriedThrough(g, damage);
        if (!damageEnabled) return carry;
        if (carry <= 0f) glassStopPoint = g.point();
        p.damage += Math.max(damage, 1f);
        breakPane(p, paneStateFor(p.damage, glassArmor()), dir);
        return carry;
    }

    /** Brings a window (the windscreen through its part) up to {@code st}. */
    private void breakPane(Pane p, int st, Vector3 dir) {
        if (st <= p.state) return;
        if (p.windscreen()) {
            Part w = p.part;
            w.damage = Math.max(w.damage, st >= OFF ? GLASS_OFF_AT : DENT_AT);
            if (st >= OFF) shatterEffects(p, dir);
            advance(w);
        } else {
            setPane(p, st, dir);
        }
    }

    /**
     * A melee blow on a window (host): ordinary glass breaks and the blow stops in it, the way one light round does;
     * armoured glass takes the blow's damage off its pool and never lets a blow through. Returns true when a window
     * took the blow, so the panel behind it does not.
     */
    public boolean strikePane(GlassHit g, float damage, Vector3 dir) {
        if (!(g != null && g.pane() instanceof Pane p)) return false;
        if (p.state >= OFF || !p.part.mesh.isVisibleInTree()) return false;
        if (!damageEnabled) return true;
        glassStopPoint = g.point();
        p.damage += Math.max(damage, 1f);
        breakPane(p, paneStateFor(p.damage, glassArmor()), dir);
        return true;
    }

    /**
     * A blast (host): every window whose centre is inside {@code radius} of {@code centre} takes the blast's damage
     * at that distance (quadratic falloff, the one {@code ExplosionManager} uses), so ordinary glass near a blast
     * breaks and armoured glass loses that much of its pool. The people inside are hit by the blast itself.
     */
    public void blastPanes(Vector3 centre, float radius, float maxDamage) {
        if (!damageEnabled || radius <= 0f) return;
        for (Pane p : panes) {
            if (p.state >= OFF || !p.part.mesh.isVisibleInTree()) continue;
            Vector3 c = paneCentre(p);
            if (c == null) continue;
            double d = c.distanceTo(centre);
            if (d > radius) continue;
            double f = 1.0 - d / radius;
            p.damage += Math.max(1.0, maxDamage * f * f);
            breakPane(p, paneStateFor(p.damage, glassArmor()), c.minus(centre).normalized());
        }
    }

    /** A window's centre in the world (the mean of its triangles), or null if it has none. */
    private Vector3 paneCentre(Pane p) {
        if (p.tris.length < 9) return null;
        double[] c = new double[3];
        int n = p.tris.length / 3;
        for (int i = 0; i < p.tris.length; i += 3) for (int k = 0; k < 3; k++) c[k] += p.tris[i + k];
        return p.part.mesh.getGlobalTransform().times(new Vector3(c[0] / n, c[1] / n, c[2] / n));
    }

    /** Where a shot that went through a window leaves the car again: the far side of the hull's box. */
    public double exitDistance(Vector3 from, Vector3 dir) {
        if (hullMin == null) return 3.0;
        Transform3D inv = vehicle.getGlobalTransform().affineInverse();
        Vector3 o = inv.times(from), d = inv.getBasis().xform(dir);
        return boxExit(new double[]{o.getX(), o.getY(), o.getZ()}, new double[]{d.getX(), d.getY(), d.getZ()},
                hullMin, hullMax);
    }

    /** Brings a window up to {@code state}: its look, its mask slot, and on shattering the shards and the sound. */
    private void setPane(Pane p, int state, Vector3 dir) {
        if (state <= p.state) return;
        boolean shatter = state >= OFF;
        p.state = state;
        if (!p.windscreen()) mask = withState(mask, p.slot, state);
        MeshInstance3D mi = p.part.mesh;
        Mesh mesh = mi.getMesh();
        for (int s : p.surfaces) {
            mi.setSurfaceOverrideMaterial(s, shatter ? Glass.hidden() : Glass.cracked(mesh.surfaceGetMaterial(s)));
        }
        if (shatter && !p.windscreen()) shatterEffects(p, dir);
    }

    private void shatterEffects(Pane p, Vector3 dir) {
        if (!p.part.mesh.isVisibleInTree() || !isInsideTree() || p.tris.length < 9) return;
        Node scene = getTree().getCurrentScene();
        if (scene == null) return;
        Vector3 at = paneCentre(p);
        Glass.shatter(scene, at, dir != null ? dir : at.minus(vehicle.getGlobalPosition()).normalized(), lastVel);
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

    /** A window's state by its slot name ("win_lf", "win_body", "windscreen"): 0 whole, 1 cracked, 3 broken; -1 none. */
    @Register public int paneStateNow(String slotName) {
        for (Pane p : panes) if (SLOTS[p.slot].equals(slotName)) return p.state;
        return -1;
    }

    /** The windows this car has, as slot names (probe). */
    @Register public String panesNow() {
        StringBuilder b = new StringBuilder();
        for (Pane p : panes) b.append(b.length() > 0 ? "," : "").append(SLOTS[p.slot]).append('/').append(p.tris.length / 9);
        return b.toString();
    }

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

    /**
     * Queues a crash at a vehicle-local point, as Vehicle._integrateForces does (probe). The car is standing still,
     * so the velocity bound would score it 0: the crash is marked as having taken exactly {@code deltaV} off it.
     */
    @Register public void crashAt(Vector3 localPoint, double deltaV) {
        queueImpact(localPoint, deltaV);
        syntheticCrash = true;
    }

    @Register public int debrisCountNow() {
        DEBRIS.removeIf(d -> !GD.isInstanceValid(d));
        return DEBRIS.size();
    }
}
