package com.openworld.world.manager;

import com.openworld.character.Character;
import com.openworld.weapon.Detonatable;
import com.openworld.character.Health;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;
import godot.api.Texture2D;
import godot.core.NodePath;
import godot.global.GD;
import com.openworld.character.CharacterVisuals;
import com.openworld.weapon.WeaponController;
import com.openworld.world.Breakable;
import com.openworld.world.HitInfo;
import com.openworld.world.HittableBody;
import com.openworld.world.SurfaceType;

/**
 * World-level singleton that resolves every bullet impact into its full consequences.
 *
 * WeaponController detects the hit (raycast → HitInfo) and calls processHit().
 * It knows nothing about surfaces, Health, particles, or decals.
 *
 * To add a new hit effect (sound, physics impulse, screen shake …):
 *   add a private method here and call it from processHit(). Nothing else changes.
 *
 * Network note: processHit() is a pure function of its arguments. With
 * CharacterInput.aimTargetPosition baked on the originating client (spread already
 * applied), every client replays the same call and reaches the same result.
 *
 * Discovery: registers itself in group "impact_manager".
 */
@Script(className = "ImpactManager")
public class ImpactManager extends Node {

    private ParticleManager particleManager;
    private DecalManager    decalManager;

    @Register
    @Override
    public void _ready() {
        addToGroup("impact_manager");
    }

    /**
     * Resolve one bullet impact into all its consequences.
     *
     * @param info         hit geometry: node, world point, surface normal
     * @param damage       base damage from WeaponStats
     * @param weaponName   display name for kill notifications
     * @param weaponIcon   icon shown in kill feed (may be null)
     * @param attackerName display name for kill notifications
     */
    public void processHit(HitInfo info, float damage,
                           String weaponName, Texture2D weaponIcon,
                           String attackerName, String attackerFaction) {
        processHit(info, damage, weaponName, weaponIcon, attackerName, attackerFaction, null);
    }

    /**
     * @param attackerPos world position of the shooter, threaded to {@link Health#takeDamage} so the
     *                    HUD can show a damage-direction indicator. Null when unknown.
     */
    public void processHit(HitInfo info, float damage,
                           String weaponName, Texture2D weaponIcon,
                           String attackerName, String attackerFaction,
                           godot.core.Vector3 attackerPos) {
        processHit(info, damage, weaponName, weaponIcon, attackerName, attackerFaction, attackerPos, "");
    }

    /** @param attackerId the attacker's characterId, for the hit marker ({@code EventBus.damageDealt}). */
    public void processHit(HitInfo info, float damage,
                           String weaponName, Texture2D weaponIcon,
                           String attackerName, String attackerFaction,
                           godot.core.Vector3 attackerPos, String attackerId) {
        processHit(info, damage, weaponName, weaponIcon, attackerName, attackerFaction, attackerPos, attackerId,
                com.openworld.world.DamageKind.BULLET);
    }

    /** @param kind what kind of hit this is: the target's Health scales it ({@code Health.multiplierFor}). */
    public void processHit(HitInfo info, float damage,
                           String weaponName, Texture2D weaponIcon,
                           String attackerName, String attackerFaction,
                           godot.core.Vector3 attackerPos, String attackerId, com.openworld.world.DamageKind kind) {
        // Walk the parent chain once to resolve surface type, health owner, and
        // character — previously done by three independent traversals per hit.
        HitContext ctx = resolveHitContext(info.hitNode);

        ParticleManager pm = getParticleManager();
        if (pm != null) pm.spawn(ctx.surface, info.hitPoint, info.hitNormal);

        boolean bullet = kind == com.openworld.world.DamageKind.BULLET;
        mark(ctx, info, kind);
        if (bullet) impactSound(ctx.surface, info.hitPoint);   // melee: MeleeItem

        if (SHOT_TRACE && attackerId != null && !attackerId.isEmpty()) traceHit(info, ctx, damage);
        if (ctx.healthOwner != null) {
            float bodyDamage = damage;
            // Tire hit (the TireHit collider under a VehicleWheel): the wheel takes the
            // damage — flats on the simulating peer, replicated via the snapshot flatMask —
            // and only a reduced passthrough continues to the vehicle body Health. The
            // vehicle counterpart of the character bone-multiplier model.
            if (ctx.wheel != null) bodyDamage = ctx.wheel.applyTireDamage(damage);
            // A body panel under the bullet dents / comes loose (GTA component damage); the car still takes the hit.
            Health health = (Health) ctx.healthOwner.getNode(new NodePath("Health"));
            float kindMult = health.multiplierFor(kind);
            // A body panel under the hit dents / comes loose (GTA component damage), as hard as the hit really is:
            // a knife (kind multiplier ~0 on a car) dents nothing
            if (ctx.wheel == null && ctx.healthOwner instanceof com.openworld.carrier.vehicle.Vehicle v
                    && v.getDamageModel() != null && kindMult > 0.05f)
                v.getDamageModel().applyHit(info.hitPoint, damage * Math.min(1f, kindMult / Math.max(1e-3f, health.hitDamageMultiplier)));
            bodyDamage *= kindMult;   // the target decides: a car soaks gunfire, ignores a knife (Health's damage kinds)
            health.takeDamage(info.hitNode, bodyDamage, weaponName, weaponIcon, attackerName, attackerFaction, attackerPos,
                    attackerId);
        }

        if (ctx.character != null && info.hitNormal != null) {
            ctx.character.applyHitImpulse(info.hitNode, info.hitNormal.times(-1f), damage);
        }

        if (ctx.detonatable != null) ctx.detonatable.detonate();

        // Destructible world geometry (breakable glass/wall — PLAN.md I2). Host-authoritative:
        // Breakable.applyDamage ignores the hit on a non-server peer and replicates the break itself.
        if (ctx.breakable != null) ctx.breakable.applyDamage(damage, attackerPos);
        // a building's window (world.PaneSet): any hit breaks it -- a melee blow included (the car's glass rule)
        com.openworld.world.GlassPanes.Pane pane = com.openworld.world.GlassPanes.paneOf(info.hitNode);
        if (pane != null && damage > 0f) pane.hit(info.hitPoint);
    }

    /**
     * Run the game with {@code OW_SHOT_TRACE=1} to print one line per bullet a player lands: what it hit, which body's
     * Health that resolves to, and that Health's state BEFORE the damage (dead, invulnerable, no owner at all). Added
     * for the 2026-10-06 report "the HUD aim is on a pedestrian and the shot does no damage", which a headless stand
     * could not reproduce -- this is the line to ask for.
     */
    public static final boolean SHOT_TRACE = System.getenv("OW_SHOT_TRACE") != null;

    private static void traceHit(HitInfo info, HitContext ctx, float damage) {
        String what = info.hitNode == null ? "nothing" : String.valueOf(info.hitNode.getPath().getPath()) + " at " + info.hitPoint;
        if (ctx.healthOwner == null) {
            GD.print("[shot] " + what + " -> no Health owner (no damage)");
            return;
        }
        Node hn = ctx.healthOwner.getNodeOrNull(new NodePath("Health"));
        String state = hn instanceof Health h
                ? String.format(java.util.Locale.ROOT, "hp %.0f%s", h.getCurrentHealth(), h.invulnerable ? " INVULNERABLE" : "")
                : "no Health node";
        GD.print(String.format(java.util.Locale.ROOT, "[shot] %s -> %s (%s), %.0f damage before multipliers",
                what, ctx.healthOwner.getName(), state, damage));
    }

    /**
     * Cosmetic-only impact resolution — particles + decal, no damage/impulse/detonation. Used by a
     * networked client to show its own predicted bullet impact (the shooter feels instant feedback)
     * while the host owns the actual damage via the MSG_SHOT path (Round 8 — host-resolved bullets).
     */
    /** Surface a collider presents to a bullet — the same walk {@link #processHit} uses. */
    public SurfaceType surfaceOf(Node hitNode) {
        return resolveHitContext(hitNode).surface;
    }

    /**
     * Impact visuals for a hit known only by WHAT it was and WHERE — a peer replaying a host-resolved
     * shot (N1b) has no collider, only the surface the host reported.
     */
    public void processVisualImpact(SurfaceType surface, godot.core.Vector3 point, godot.core.Vector3 normal) {
        ParticleManager pm = getParticleManager();
        if (pm != null) pm.spawn(surface != null ? surface : SurfaceType.DEFAULT, point, normal);
        // a peer has no collider: one short ray along the normal finds what was hit, so a car's hole rides the car
        if (normal != null && surface != SurfaceType.FLESH) {
            Node hit = colliderAt(point, normal);
            HitContext ctx = hit != null ? resolveHitContext(hit) : null;
            if (ctx != null) mark(ctx, new HitInfo(hit, point, normal), com.openworld.world.DamageKind.BULLET);
            else {
                DecalManager dm = getDecalManager();
                if (dm != null) dm.spawn(point, normal, DecalManager.Mark.HOLE, surface, null, 0f);
            }
        }
        impactSound(surface, point);
    }

    /** A bullet's impact visuals and sound, no damage (a peer's prediction). */
    public void processVisualHit(HitInfo info) { processVisualHit(info, com.openworld.world.DamageKind.BULLET); }

    /** A hit's visuals, no damage: particles and its mark by {@code kind}; the impact sound for a bullet only (a
     *  melee weapon plays its own contact sound, MeleeItem). */
    public void processVisualHit(HitInfo info, com.openworld.world.DamageKind kind) {
        HitContext ctx = resolveHitContext(info.hitNode);
        ParticleManager pm = getParticleManager();
        if (pm != null) pm.spawn(ctx.surface, info.hitPoint, info.hitNormal);
        mark(ctx, info, kind);
        if (kind == com.openworld.world.DamageKind.BULLET) impactSound(ctx.surface, info.hitPoint);
    }

    /**
     * The mark a hit leaves (DecalManager): a bullet a hole, a blade or an axe a slash, a blunt blow none. On static
     * geometry a pooled world-space decal; on a car (not its tyre) a decal parented to the car so it rides with it; on
     * a character nothing (blood particles only).
     */
    private void mark(HitContext ctx, HitInfo info, com.openworld.world.DamageKind kind) {
        DecalManager dm = getDecalManager();
        if (dm == null || info == null || info.hitNormal == null || ctx.character != null || ctx.wheel != null) return;
        DecalManager.Mark m = switch (kind == null ? com.openworld.world.DamageKind.BULLET : kind) {
            case BULLET -> DecalManager.Mark.HOLE;
            case BLADE, HEAVY -> DecalManager.Mark.SLASH;
            default -> null;
        };
        if (m == null) return;
        godot.api.Node3D body = ctx.healthOwner instanceof com.openworld.carrier.vehicle.Vehicle v ? v : null;
        if (ctx.healthOwner != null && body == null) return;       // something else alive / moving: no mark
        if (body == null && info.hitNode instanceof godot.api.RigidBody3D) return;   // a loose prop: it would float
        dm.spawn(info.hitPoint, info.hitNormal, m, ctx.surface, body, 0f);
    }

    /** The collider within 6 cm behind {@code point} along {@code -normal} (WORLD and VEHICLE), or null. */
    private Node colliderAt(godot.core.Vector3 point, godot.core.Vector3 normal) {
        var w = getViewport() == null ? null : getViewport().getWorld3d();
        var space = w == null ? null : w.getDirectSpaceState();
        if (space == null) return null;
        godot.core.Vector3 n = normal.normalized();
        var q = godot.api.PhysicsRayQueryParameters3D.create(point.plus(n.times(0.06)), point.minus(n.times(0.06)),
                com.openworld.util.CollisionLayers.WORLD | com.openworld.util.CollisionLayers.VEHICLE,
                new godot.core.VariantArray<>(godot.core.RID.class));
        godot.core.Dictionary<Object, Object> hit = space.intersectRay(q);
        return hit != null && !hit.isEmpty() && hit.get("collider") instanceof Node c ? c : null;
    }

    /** Impact sounds are heard this far from the camera; past it a bullet lands silently (the shot itself is heard). */
    public static final double IMPACT_SOUND_RANGE = 70.0;
    /** At most this many impact sounds start in one frame: a shotgun's eight pellets read as one hit, not eight. */
    public static final int IMPACT_SOUNDS_PER_FRAME = 3;
    private long impactFrame = -1;
    private int impactSoundsThisFrame;

    /** One bullet impact sound by surface at {@code at} (audio.Sound IMPACT_*), within range and the frame budget. */
    public void impactSound(SurfaceType surface, godot.core.Vector3 at) {
        if (at == null || !isInsideTree()) return;
        long f = godot.api.Engine.INSTANCE.getProcessFrames();
        if (f != impactFrame) { impactFrame = f; impactSoundsThisFrame = 0; }
        if (impactSoundsThisFrame >= IMPACT_SOUNDS_PER_FRAME) return;
        var cam = getViewport() == null ? null : getViewport().getCamera3d();
        if (cam != null && cam.getGlobalPosition().distanceTo(at) > IMPACT_SOUND_RANGE) return;
        impactSoundsThisFrame++;
        com.openworld.audio.Sound s = switch (surface == null ? SurfaceType.DEFAULT : surface) {
            case FLESH -> com.openworld.audio.Sound.IMPACT_FLESH;
            case METAL -> com.openworld.audio.Sound.IMPACT_METAL;
            case WOOD -> com.openworld.audio.Sound.IMPACT_WOOD;
            case GLASS -> com.openworld.audio.Sound.IMPACT_GLASS;
            case WATER -> com.openworld.audio.Sound.SPLASH_SMALL;
            default -> com.openworld.audio.Sound.IMPACT_STONE;
        };
        Node parent = getTree().getCurrentScene() != null ? getTree().getCurrentScene() : this;
        com.openworld.audio.Sounds.play3D(parent, s, at, 4f, 0.12f);
    }

    // ── Hit context resolution ────────────────────────────────────────────────

    private static class HitContext {
        final Character   character;
        final Node        healthOwner;
        final SurfaceType surface;
        final Detonatable detonatable;
        final Breakable   breakable;
        final com.openworld.carrier.vehicle.VehicleWheel wheel;
        HitContext(Character c, Node h, SurfaceType s, Detonatable d, Breakable b,
                   com.openworld.carrier.vehicle.VehicleWheel w) {
            character = c; healthOwner = h; surface = s; detonatable = d; breakable = b; wheel = w;
        }
    }

    /**
     * Walks the parent chain once to collect surface type, health owner, and character.
     * On a character hit all three resolve to the same ancestor — previously done by
     * three independent traversals in resolveSurfaceType / walkToHealthOwner / applyHitImpulse.
     *
     * getOwner() is not used because CharacterVisuals is added at runtime (addChild),
     * so bones inside it report CharacterVisuals as their owner, not the Character body.
     */
    /**
     * The thing a collider BELONGS TO, as far as an attack is concerned: the Character, else the
     * node carrying the Health, else the Detonatable, else the Breakable — or null for plain world
     * geometry. It is the same walk {@link #processHit} applies damage with, so a caller that groups
     * or filters hits through it (melee cleave, which must hit each target ONCE however many of its
     * ragdoll bones the sweep overlaps) cannot disagree with where the damage actually goes.
     */
    public static Node resolveTarget(Node hitNode) {
        HitContext ctx = resolveHitContext(hitNode);
        if (ctx.character != null) return ctx.character;
        if (ctx.healthOwner != null) return ctx.healthOwner;
        if (ctx.detonatable instanceof Node d) return d;
        if (ctx.breakable != null) return ctx.breakable;
        return null;
    }

    /**
     * Things that are metal by WHAT they are, with no HittableBody to say so: a vehicle (car, boat, aircraft), a train
     * car, a street pole's collider (BreakableProps' "Poles" body). Sparks, a metal impact sound and a tinted hole.
     */
    private static boolean isMetal(Node n) {
        if (n instanceof com.openworld.carrier.vehicle.Vehicle) return true;
        if (n instanceof godot.api.AnimatableBody3D a && a.isInGroup(new godot.core.StringName("train_car"))) return true;
        return n instanceof godot.api.StaticBody3D && n.getParent() instanceof com.openworld.world.BreakableProps;
    }

    private static HitContext resolveHitContext(Node hitNode) {
        if (hitNode == null) return new HitContext(null, null, SurfaceType.DEFAULT, null, null, null);
        // A world item's collider belongs to its PickupBody, and the ITEM is that body's CHILD --
        // so a walk that only goes up would pass straight over it. Shooting a dropped grenade has to
        // find the ThrowableItem's Detonatable, and the item is also where a HittableBody surface
        // type would live. Start at the item: everything above the body is above the item too.
        if (hitNode instanceof com.openworld.item.PickupBody body && body.carriedItem() != null) {
            hitNode = body.carriedItem();
        }
        Character character = null;
        Node healthOwner = null;
        SurfaceType surface = SurfaceType.DEFAULT;
        Detonatable detonatable = null;
        Breakable breakable = null;
        com.openworld.carrier.vehicle.VehicleWheel wheel = null;

        Node current = hitNode;
        while (current != null) {
            if (detonatable == null && current instanceof Detonatable d) detonatable = d;
            if (breakable == null && current instanceof Breakable b) breakable = b;
            // A TireHit collider's parent chain passes through its VehicleWheel before
            // reaching the Vehicle (which owns the Health) — capture it for tire damage.
            if (wheel == null && current instanceof com.openworld.carrier.vehicle.VehicleWheel vw) wheel = vw;
            if (surface == SurfaceType.DEFAULT) {
                if (current instanceof godot.api.StaticBody3D sb && current.getParent() instanceof com.openworld.world.PaneSet) {
                    surface = SurfaceType.GLASS;
                } else if (current instanceof Character c) {
                    surface = SurfaceType.FLESH;
                    character = c;
                } else if (current instanceof HittableBody hb) {
                    surface = hb.resolveSurfaceType();
                } else if (wheel == null && isMetal(current)) {   // a tyre is rubber: dust
                    surface = SurfaceType.METAL;
                }
            } else if (character == null && current instanceof Character c) {
                character = c;
            }
            if (healthOwner == null && current.hasNode(new NodePath("Health"))) {
                healthOwner = current;
            }
            if (character != null && healthOwner != null && surface != SurfaceType.DEFAULT
                    && detonatable != null && breakable != null) break;
            current = current.getParent();
        }
        return new HitContext(character, healthOwner, surface, detonatable, breakable, wheel);
    }

    // ── Lazy singleton lookups ────────────────────────────────────────────────

    private ParticleManager getParticleManager() {
        if (particleManager != null) return particleManager;
        Node found = getTree().getFirstNodeInGroup("particle_manager");
        if (found instanceof ParticleManager pm) particleManager = pm;
        return particleManager;
    }

    private DecalManager getDecalManager() {
        if (decalManager != null) return decalManager;
        Node found = getTree().getFirstNodeInGroup("decal_manager");
        if (found instanceof DecalManager dm) decalManager = dm;
        return decalManager;
    }
}
