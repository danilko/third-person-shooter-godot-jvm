package com.openworld.weapon;

import com.openworld.world.manager.ExplosionManager;
import godot.annotation.Export;
import godot.annotation.Script;
import godot.api.*;
import godot.global.GD;
import godot.annotation.Register;
import godot.core.Color;
import godot.core.Vector3;
import com.openworld.character.Character;
import com.openworld.item.AmmoRefill;
import com.openworld.item.Pickup;

/**
 * Weapon item that throws a physical projectile scene (e.g. a grenade) along the
 * aim direction with an upward arc.
 *
 * Slot: THROWABLE (slot 5). Each throw consumes one carry-count unit (magazine field).
 * No reserve / reload model — carry count is restocked by picking up more throwables
 * of the same weaponId or by visiting an AmmoRefill station.
 *
 * Pick-up stacking:
 *   When a ThrowableItem pickup is touched, if the character already has a ThrowableItem
 *   with the same weaponId in their THROWABLE slot, the carry count is merged (up to
 *   magazineSize = maxCarryCount). If the slot is free, the item is equipped normally.
 *   If no merge is possible and the slot is occupied by a different type, the standard
 *   interact-to-swap flow applies.
 *
 * Drop packaging:
 *   Dropping packages the entire remaining carry count into a single world pickup because
 *   ThrowableItem IS the pickup node. Dropping is blocked when magazine == 0 (nothing to
 *   package). The empty slot stays active so the character can pick up more grenades later.
 *
 * Single-use throwables (e.g. a one-shot signal flare):
 *   Set magazineSize = 1 in the inspector.
 *
 * Scene setup (e.g. FRG1.tscn):
 *   Node3D + ThrowableItem script
 *     CollisionShape3D   (the WORLD body's shape — lent to the PickupBody built at drop time;
 *                         the layer/mask live on that body, not here)
 *     PickupArea (Area3D)
 *       CollisionShape3D (detection sphere — layer 0 / mask character layer 2)
 *   Connections: PickupArea.body_entered → on_body_entered
 *                PickupArea.body_exited  → on_body_exited
 *
 * Configure magazine=1, magazineSize=6 (or 1 for single-use), reserve=0, reserveMax=0.
 * Set projectileScene to the projectile scene (e.g. FRG1Projectile.tscn); explosion
 * parameters live in the projectile scene itself, not here.
 */
@Script(className = "ThrowableItem")
public class ThrowableItem extends WeaponItem implements Detonatable {

    public ThrowableItem() {
        // All throwable by default should require manual throw
        auto = false;
    }

    /** Physics scene to instantiate on each throw (e.g. FRG1Projectile.tscn). */
    @Export public PackedScene projectileScene;

    /** Does a bullet set the world pickup off? False for a flashbang or smoke grenade: they carry no blast. */
    @Export public boolean detonatesWhenShot = true;
    public boolean getDetonatesWhenShot() { return detonatesWhenShot; }
    public void setDetonatesWhenShot(boolean v) { detonatesWhenShot = v; }
    /** Explosion radius when the world pickup is shot (metres). */
    @Export public float explosionRadius    = 5f;
    /** Max damage at the epicentre when the world pickup is shot. */
    @Export public float explosionMaxDamage = 80f;
    /** Push force applied to bodies in the blast when the world pickup is shot. */
    @Export public float explosionPushForce = 15f;

    /** The blast effect this explosive draws (a scene under assets/vfx/explosion/effects/; null = the manager's). */
    @Export public godot.api.PackedScene explosionVfx;
    /** Extra size multiplier on the blast effect; at 1 its shockwave ends exactly at the damage radius (ExplosionManager.playBlast). */
    @Export public float explosionVfxScale = 1.0f;

    // ── Pickup override — stack merging ───────────────────────────────────────

    /**
     * Auto-pickup when:
     *   (a) the THROWABLE slot is free — normal equip, or
     *   (b) the character already has a ThrowableItem with the same weaponId that has
     *       room below magazineSize — merge without requiring interact.
     * Any other case (different type occupying slot, or stack already full) falls
     * through to the interact-prompt path.
     */
    @Override
    protected boolean shouldAutoPickup(Node character) {
        Node wcNode = character.getNodeOrNull(WEAPON_CONTROLLER_PATH);
        if (!(wcNode instanceof WeaponController wc)) return false;
        if (wc.isSlotFreeFor(resolveSlotType())) return true;
        if (weaponId.isEmpty()) return false;
        WeaponItem existing = wc.findWeaponByIdAndType(weaponId, resolveSlotType());
        return existing instanceof ThrowableItem ti && ti.magazine < ti.magazineSize;
    }

    /**
     * If a same-type stack exists with room, add what fits and queueFree this pickup
     * immediately — no partial remainders left in the world.
     * Otherwise falls back to standard equip via WeaponController.requestEquip().
     */
    @Override
    protected void onCharacterEntered(Node character) {
        Node wcNode = character.getNodeOrNull(WEAPON_CONTROLLER_PATH);
        if (!(wcNode instanceof WeaponController wc)) return;

        if (!weaponId.isEmpty()) {
            WeaponItem existing = wc.findWeaponByIdAndType(weaponId, resolveSlotType());
            if (existing instanceof ThrowableItem ti && ti.magazine < ti.magazineSize) {
                ti.magazine += Math.min(ti.magazineSize - ti.magazine, magazine);
                // Emit unconditionally so the slot UI / nameplate (which re-scan every slot on
                // ammoChanged) refresh the merged count immediately — even when the throwable is
                // NOT the active weapon. notifyAmmoChange(ti) no-ops on an inactive stack, which is
                // why the count previously only updated after a later fire/weapon-switch.
                wc.refreshActiveAmmoDisplay();
                wc.resetFireTimerForEquip(ti);
                equipped = true;
                queueFree();
                return;
            }
        }

        // No merge possible — standard equip (free slot or displacement via interact)
        equipped = true;
        wc.requestEquip(this);
    }

    // ── WeaponAction ──────────────────────────────────────────────────────────

    @Override public WeaponType getWeaponType()   { return WeaponType.THROWN; }
    @Override public WeaponSlotType resolveSlotType() { return WeaponSlotType.THROWABLE; }
    // Semi-auto by default (auto = false): one grenade per trigger pull. Without the
    // isSemiAutoReady() gate a held throw key spawned multiple grenades back-to-back
    // (capped only by fireRate) both locally and across LAN — the double-throw bug.
    @Override public boolean canUse()             { return magazine > 0 && isSemiAutoReady(); }
    /**
     * NOT gated on facing the aim (W21's {@code pointsAtAim}). That gate compares the HELD ITEM's model forward
     * with the aim, which is a gun barrel's direction and nothing a grenade in the hand has: its forward is
     * wherever the hold pose leaves it, so the gate never opened and no grenade could be thrown at all —
     * found by the N4 launch check (fire pressed with a ready FRG1, nothing launched, single-player included).
     * And the gate's reason does not apply: a throw's direction is body → aim point ({@link #resolveAimDir}),
     * it leaves in front of the chest, and it ignores collisions with its thrower.
     */
    @Override protected boolean launchesTowardAim() { return false; }

    @Override
    public void useWeapon() {
        isWeaponFired = true;
        decrementMagazine();
        Vector3[] in = launchInputs();
        if (in != null) {
            // N4: a client predicts a cosmetic grenade and the host throws the one that damages.
            if (NetRole.client(this)) {
                sendLaunchToHost(in[0], in[1]);
                launch(in[0], in[1], true);
            } else {
                launch(in[0], in[1], false);
            }
        }
        playThrowAudio();
        playThrowAnimation();
    }

    /**
     * The throwing arm (W35). The grenade leaves on the PRESS, so the clip is baked from the arm
     * already cocked (the library's OverhandThrow from frame 6): the release lands ~80 ms after the
     * press instead of after a quarter-second windup the grenade has already skipped. It rides the
     * melee Attack one-shot, which is the arms-only layer a throw needs.
     */
    @godot.annotation.Export
    public String throwAnimation = "attack_throw";
    @godot.annotation.Export
    public double throwAnimationSeconds = 0.8;

    public String getThrowAnimation() { return throwAnimation; }
    public void setThrowAnimation(String v) { throwAnimation = v; }
    public double getThrowAnimationSeconds() { return throwAnimationSeconds; }
    public void setThrowAnimationSeconds(double v) { throwAnimationSeconds = v; }

    private void playThrowAnimation() {
        if (weaponController == null) return;
        com.openworld.character.AnimationController ac = weaponController.animation();
        if (ac != null) ac.playMeleeAttack(throwAnimation, throwAnimationSeconds);
    }

    /**
     * Puppet replay of a remote throw (Round 11 — WeaponController.playRemoteFireCue):
     * throw audio + a COSMETIC projectile aimed at the replicated aim point, so every peer
     * sees the grenade arc and explosion. No ammo decrement, no damage — both are
     * authority-side (the thrower already spawned the real, damaging projectile).
     */
    @Override
    public void playRemoteFireCue() {
        playThrowAudio();
        playThrowAnimation();
        // N4: on the host this puppet's real grenade arrives as MSG_LAUNCH — a cue copy would be a second one.
        if (NetRole.host(this)) { com.openworld.net.NetStats.increment("launch_cue_host_skipped"); return; }
        Vector3[] in = launchInputs();
        if (in != null) launch(in[0], in[1], true);
    }

    /** Host: throw a client's validated launch as the authoritative grenade (PLAN.md N4). */
    public void launchFrom(Vector3 origin, Vector3 aim) {
        launch(origin, aim, false);
    }

    private void sendLaunchToHost(Vector3 origin, Vector3 aim) {
        com.openworld.net.NetworkManager net = NetRole.net(this);
        if (net == null || weaponController == null || !(owningCharacter instanceof Character c) || c.characterInfo == null) return;
        net.sendLaunch(c.characterInfo.characterId, weaponController.getWeapon(), weaponController.nextShotSeq(), origin, aim);
    }

    private String attackerId() {
        return owningCharacter instanceof Character c && c.characterInfo != null ? c.characterInfo.characterId : "";
    }

    private void playThrowAudio() {
        if (weaponAudio != null && fireAudio != null) {
            weaponAudio.stop();
            weaponAudio.setStream(fireAudio);
            weaponAudio.play();
        }
    }

    /**
     * Clears the THROWABLE slot when the last grenade is thrown so any other throwable
     * type can be auto-picked up immediately (no interact-to-swap required).
     * The consumed ThrowableItem node is queueFreed — it has no remaining value.
     */
    @Override
    public void onMagazineEmpty() {
        if (weaponController != null) weaponController.clearActiveSlot();
    }

    /** A thrown-out stack clears its slot (above) rather than reloading into itself. */
    @Override
    public boolean autoReloadsOnEmpty() { return false; }

    /**
     * Only create a world pickup when there are grenades to package.
     * (Manual drop of a 0-count slot is a no-op.)
     */
    @Override
    public boolean shouldDropToWorld() { return isDroppable && magazine > 0; }

    // ── Detonatable ───────────────────────────────────────────────────────────

    /**
     * Explodes the world pickup in place when shot by a bullet.
     * Scales linearly with magazine count (capped at 4×) so a stacked pickup
     * produces a proportionally larger blast than a single grenade.
     * No-op if already equipped (in a character's inventory) or not in the tree.
     */
    @Override
    public void detonate() {
        if (equipped || !isInsideTree() || !detonatesWhenShot) return;
        Node m = getTree().getFirstNodeInGroup("explosion_manager");
        if (m instanceof ExplosionManager mgr) {
            float scale = Math.min(Math.max(magazine, 1), 4);
            mgr.triggerExplosion(getGlobalPosition(),
                                 explosionRadius    * scale,
                                 explosionMaxDamage * scale,
                                 explosionPushForce * scale,
                                 "", "", getDisplayName(), weaponIcon, null,
                                 explosionVfx, explosionVfxScale);   // sized from the (stack-scaled) radius
        }
        queueFree();
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    /**
     * Spawns the thrown projectile. {@code cosmetic} true is the puppet replay: aim comes from
     * the replicated aim point (no aimRay on a puppet) and the projectile deals no damage.
     */
    /** `[origin, aim]` of a throw now (the aim BEFORE the arc), or null — what a client reports in MSG_LAUNCH. */
    private Vector3[] launchInputs() {
        if (projectileScene == null || owningCharacter == null) return null;
        Vector3 aimDir = resolveAimDir();
        if (aimDir == null) return null;
        // Spawn near the character's shoulder, slightly forward of the body
        Vector3 spawnPos = owningCharacter.getGlobalPosition()
                .plus(new Vector3(0f, 1.4f, 0f))
                .plus(aimDir.times(0.4f));
        return new Vector3[] {spawnPos, aimDir};
    }

    private void launch(Vector3 spawnPos, Vector3 aimDir, boolean cosmetic) {
        if (projectileScene == null || owningCharacter == null || aimDir.lengthSquared() < 1e-6f) return;
        aimDir = aimDir.normalized();

        Vector3 velocity = throwVelocity(aimDir);

        Node projectile = projectileScene.instantiate();

        // Inject attacker identity before the node enters the tree.
        // Explosion parameters are scene-configured inside the projectile scene itself.
        if (projectile instanceof GrenadeProjectile gp) {
            gp.cosmetic = cosmetic;
            gp.attackerId = attackerId();
            gp.kind = weaponId;
            if (!cosmetic) {
                gp.attackerName      = resolveAttackerName();
                gp.attackerFaction   = resolveAttackerFaction();
                gp.weaponDisplayName = getDisplayName();
                gp.weaponIcon        = weaponIcon;
            }
        }

        getTree().getCurrentScene().addChild(projectile);
        if (cosmetic) ProjectileLedger.register(attackerId(), weaponId, projectile);

        if (projectile instanceof Node3D n3d) n3d.setGlobalPosition(spawnPos);
        if (projectile instanceof GrenadeProjectile gp) {
            gp.launchVelocity = velocity;
            // Never collide with the thrower: it spawns at the chest.
            if (owningCharacter instanceof Character oc) gp.ignoreRid = oc.getRid();
        }
    }

    /**
     * Aim direction, derived identically on every peer (authority and puppet) from the replicated
     * aim point (getAimTargetPosition — the same value that drives spine IK and rides in every
     * snapshot), matching FirearmItem.playRemoteFireCue. Previously authority used the precise
     * aimRay while puppets used the aim point, which diverged the throw arc between the thrower and
     * observers; deriving both from the one replicated quantity keeps the grenade consistent.
     */
    /**
     * The launch VELOCITY for an aim direction -- the one owner the real throw and the preview share:
     * CS 1.6's rule ({@link ThrowArc}), harder and higher the higher you aim.
     */
    private Vector3 throwVelocity(Vector3 aimDir) {
        Vector3 right = aimDir.cross(Vector3.Companion.getUP()).normalized();
        if (right.lengthSquared() < 0.001f) right = Vector3.Companion.getRIGHT();
        double elev = Math.toDegrees(Math.asin(Math.max(-1.0, Math.min(1.0, aimDir.getY()))));
        ThrowArc.Throw t = ThrowArc.fromAim(elev);
        return aimDir.rotated(right, (float) Math.toRadians(t.elevationDeg() - elev)).normalized().times(t.speed());
    }

    // ── Trajectory preview (W36, W38) ───────────────────────────────────────
    //
    // While the LOCAL player aims a throwable, the path it would fly is drawn, bounces included, with a
    // disc where it goes off (Apex/Fortnite/PUBG; CS2 in practice). It is not a model of the flight but
    // the flight itself: a GrenadeFlight stepped ahead from the same launch inputs and velocity the
    // real throw uses. Red-orange when the fuse runs out before it touches anything (an air burst).
    // Purely local and cosmetic: no message.

    /** Draw the predicted arc while this throwable is aimed by the local player. */
    @Export public boolean showTrajectory = true;
    public boolean getShowTrajectory() { return showTrajectory; }
    public void setShowTrajectory(boolean v) { showTrajectory = v; }

    /** The preview steps at the physics rate, so it takes the grenade's own steps. */
    private static final double PREVIEW_STEP = 1.0 / 60.0;
    /** Width of the drawn arc and ring band, metres -- a ribbon, so it reads at a distance. */
    private static final double PREVIEW_WIDTH = 0.04;
    /** ...and at least this much per metre from the camera, so a far arc stays as thick on screen. */
    private static final double PREVIEW_WIDTH_PER_M = 0.006;
    private static final double PREVIEW_RING_RADIUS = 0.6;
    /** Translucent blue; red-orange when the fuse runs out before the grenade lands. */
    private static final Color PREVIEW_COLOR = new Color(0.2, 0.6, 1.0, 0.6);
    private static final Color PREVIEW_BURST_COLOR = new Color(1.0, 0.35, 0.2, 0.6);
    private MeshInstance3D previewLine;
    private ImmediateMesh previewMesh;
    private double previewFuse = -1.0;
    private boolean previewSticks = false;
    /** Where the last drawn arc ends, and whether that is a landing (true) or an air burst. For probes. */
    private Vector3 previewEnd = null;
    private boolean previewLands = false;

    @Register
    public Vector3 previewEndNow() { return previewEnd != null ? previewEnd : new Vector3(); }
    @Register
    public boolean previewLandsNow() { return previewLands; }
    @Register
    public boolean previewShownNow() { return previewLine != null && previewLine.isVisible(); }

    @Register
    @Override
    public void _process(double delta) {
        super._process(delta);
        updatePreview();
    }

    private boolean previewWanted() {
        if (!showTrajectory || magazine <= 0 || weaponController == null) return false;
        if (!(owningCharacter instanceof Character c) || !c.isLocallyOwnedPlayer() || !c.isCombat()) return false;
        if (!c.isAlive() || c.currentVehicleNode != null) return false;
        return weaponController.getCurrentWeaponItem() == this && !weaponController.isWeaponTransitioning();
    }

    private void updatePreview() {
        if (!previewWanted()) {
            if (previewLine != null) previewLine.setVisible(false);
            return;
        }
        Vector3[] in = launchInputs();
        if (in == null) return;
        ensurePreview();
        godot.core.VariantArray<godot.core.RID> exclude = new godot.core.VariantArray<>(godot.core.RID.class);
        if (owningCharacter instanceof Character oc) exclude.add(oc.getRid());
        // The SAME flight the grenade will fly (GrenadeFlight), bounces included, to the fuse or to rest:
        // the disc marks where it goes off, which is where the damage is.
        GrenadeFlight f = new GrenadeFlight(in[0], throwVelocity(in[1].normalized()), exclude);
        PhysicsDirectSpaceState3D space = getWorld3d().getDirectSpaceState();
        double g = GrenadeProjectile.gravity();
        java.util.ArrayList<Vector3> pts = new java.util.ArrayList<>();
        pts.add(f.position);
        double fuse = fuseSeconds();
        for (double t = 0.0; t < fuse && !f.resting; t += PREVIEW_STEP) {
            f.step(space, PREVIEW_STEP, g);
            pts.add(f.position);
            if (previewSticks && f.contacts > 0) break;       // a remote charge stops where it first touches
        }
        Vector3 p = f.position;
        boolean landed = f.contacts > 0;
        Vector3 normal = Vector3.Companion.getUP();
        p = p.minus(new Vector3(0.0, GrenadeFlight.RADIUS, 0.0));   // the disc sits on the surface, not at the sphere's centre

        // The arc as a RIBBON turned to face the camera (a line is one pixel wide at any distance).
        Camera3D cam = getViewport().getCamera3d();
        Vector3 eye = cam != null ? cam.getGlobalPosition() : pts.get(0).plus(new Vector3(0.0, 2.0, 0.0));
        Color arc = landed ? PREVIEW_COLOR : PREVIEW_BURST_COLOR;
        previewMesh.clearSurfaces();
        previewMesh.surfaceBegin(Mesh.PrimitiveType.TRIANGLE_STRIP, null);
        previewMesh.surfaceSetColor(arc);
        for (int i = 0; i < pts.size(); i++) {
            Vector3 here = pts.get(i);
            Vector3 along = pts.get(Math.min(i + 1, pts.size() - 1)).minus(pts.get(Math.max(i - 1, 0)));
            Vector3 side = along.cross(eye.minus(here));
            if (side.lengthSquared() < 1e-9) side = Vector3.Companion.getRIGHT();
            // Width grows with distance so the arc keeps about the same thickness on screen.
            double w = Math.max(PREVIEW_WIDTH, here.distanceTo(eye) * PREVIEW_WIDTH_PER_M);
            side = side.normalized().times(w * 0.5);
            previewMesh.surfaceAddVertex(here.plus(side));
            previewMesh.surfaceAddVertex(here.minus(side));
        }
        previewMesh.surfaceEnd();
        // The landing marker: a translucent filled disc with a stronger rim, flat on what it lands on
        // (a thin ring is edge-on from a third-person camera and all but vanishes).
        Vector3 a = normal.cross(Math.abs(normal.getY()) < 0.9 ? Vector3.Companion.getUP() : Vector3.Companion.getRIGHT()).normalized();
        Vector3 b = normal.cross(a).normalized();
        Vector3 c0 = p.plus(normal.times(0.03));
        double rim = Math.max(PREVIEW_WIDTH, c0.distanceTo(eye) * PREVIEW_WIDTH_PER_M);
        previewMesh.surfaceBegin(Mesh.PrimitiveType.TRIANGLES, null);
        previewMesh.surfaceSetColor(new Color(arc.getR(), arc.getG(), arc.getB(), arc.getA() * 0.45));
        for (int i = 0; i < 32; i++) {
            double a0 = i * Math.PI * 2.0 / 32.0, a1 = (i + 1) * Math.PI * 2.0 / 32.0;
            previewMesh.surfaceAddVertex(c0);
            previewMesh.surfaceAddVertex(c0.plus(a.times(Math.cos(a0) * PREVIEW_RING_RADIUS)).plus(b.times(Math.sin(a0) * PREVIEW_RING_RADIUS)));
            previewMesh.surfaceAddVertex(c0.plus(a.times(Math.cos(a1) * PREVIEW_RING_RADIUS)).plus(b.times(Math.sin(a1) * PREVIEW_RING_RADIUS)));
        }
        previewMesh.surfaceEnd();
        previewMesh.surfaceBegin(Mesh.PrimitiveType.TRIANGLE_STRIP, null);
        previewMesh.surfaceSetColor(arc);
        for (int i = 0; i <= 32; i++) {
            double ang = i * Math.PI * 2.0 / 32.0;
            Vector3 dir = a.times(Math.cos(ang)).plus(b.times(Math.sin(ang)));
            previewMesh.surfaceAddVertex(c0.plus(dir.times(PREVIEW_RING_RADIUS + rim * 0.5)));
            previewMesh.surfaceAddVertex(c0.plus(dir.times(PREVIEW_RING_RADIUS - rim * 0.5)));
        }
        previewMesh.surfaceEnd();
        previewEnd = p;
        previewLands = landed;
        previewLine.setVisible(true);
    }

    /** The projectile's own fuse, read once off its scene (the one number the air-burst colour needs). */
    private double fuseSeconds() {
        if (previewFuse < 0.0) {
            previewFuse = 3.0;
            if (projectileScene != null) {
                Node n = projectileScene.instantiate();
                if (n instanceof GrenadeProjectile gp) {
                    previewSticks = gp.kindOfEffect() == GrenadeEffect.REMOTE;
                    previewFuse = previewSticks ? 10.0 : gp.fuseTime;
                }
                n.free();
            }
        }
        return previewFuse;
    }

    private void ensurePreview() {
        if (previewLine != null && GD.isInstanceValid(previewLine)) return;
        previewMesh = new ImmediateMesh();
        previewLine = new MeshInstance3D();
        previewLine.setName("TrajectoryPreview");
        previewLine.setMesh(previewMesh);
        previewLine.setAsTopLevel(true);
        previewLine.setCastShadowsSetting(GeometryInstance3D.ShadowCastingSetting.OFF);
        StandardMaterial3D m = new StandardMaterial3D();
        m.setShadingMode(BaseMaterial3D.ShadingMode.UNSHADED);
        m.setFlag(BaseMaterial3D.Flags.ALBEDO_FROM_VERTEX_COLOR, true);
        m.setTransparency(BaseMaterial3D.Transparency.ALPHA);
        m.setFlag(BaseMaterial3D.Flags.DISABLE_DEPTH_TEST, true);
        m.setCullMode(BaseMaterial3D.CullMode.DISABLED);   // the ribbon is seen from both sides
        previewLine.setMaterialOverride(m);
        addChild(previewLine);
        previewLine.setGlobalTransform(new godot.core.Transform3D());
    }

    private Vector3 resolveAimDir() {
        if (!(owningCharacter instanceof Character c)) return null;
        Vector3 from = owningCharacter.getGlobalPosition().plus(new Vector3(0f, 1.4f, 0f));
        Vector3 dir = c.getAimTargetPosition().minus(from);
        return dir.lengthSquared() < 1e-6f ? null : dir.normalized();
    }
}
