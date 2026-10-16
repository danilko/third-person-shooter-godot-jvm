package com.openworld.character;

import com.openworld.game.profile.PlayerProfile;
import com.openworld.game.profile.Profiles;
import com.openworld.weapon.FirearmItem;
import com.openworld.weapon.WeaponController;
import com.openworld.weapon.WeaponItem;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Marker3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.Skeleton3D;
import godot.api.SpotLight3D;
import godot.core.Basis;
import godot.core.Color;
import godot.core.Transform3D;
import godot.core.Vector3;
import godot.global.GD;

/**
 * The flashlight (PLAN.md 3.2, user 2026-10-16): a GADGET, not a weapon slot -- one toggle ({@code flashlight}, T),
 * TWO mounts. On a FIREARM the light is ON THE GUN (Left 4 Dead: the beam follows the weapon, so it sways with the walk,
 * dips in a reload and kicks with the recoil): at the weapon's {@code LightPoint} marker if an artist placed one, else
 * DERIVED from its {@code Muzzle} -- {@link #AHEAD} in front of the bore and {@link #UNDER} below it, so the gun cannot
 * shadow its own beam and no weapon scene needed an art pass. With melee, fists, a throwable or empty hands it comes
 * from the BODY (CS 1.6's light, {@link #onMelee}): the chest bone, aimed at the aim point -- or, in first person, the
 * camera. One SpotLight3D per body that ever switched one on, top-level, placed every frame.
 *
 * <p>The state is {@link Character#flashlightOn}: the owner toggles it (only if their profile owns one, {@link #owned}),
 * a puppet takes it from the snapshot's flags word (bit 14), and each peer picks the mount from the weapon it already
 * sees -- no message of its own. Shadows only on the local player's light (a puppet's is a plain cone, for cost). At
 * night the authority posts a {@code LIGHT_SEEN} stimulus at the body once a second: a hostile AI near it comes to look.
 */
@Script(className = "Flashlight")
public class Flashlight extends Node3D {

    /** The profile unlock that owns one (PlayerProfile.unlocks): bought once, kept. */
    public static final String UNLOCK = com.openworld.item.Gadgets.FLASHLIGHT;
    /** The node's name under its Character. */
    public static final String NODE = "Flashlight";
    /** The derived gun mount: this far in front of the muzzle (m) -- past the barrel -- and this far under the bore. */
    static final double AHEAD = 0.04, UNDER = 0.03;
    /** The body mount: this far in front of the chest bone (m), clear of the arms. */
    static final double CHEST_AHEAD = 0.28;
    /** CS 1.6's body light on melee / fists / throwables; false = Left 4 Dead's (off while no firearm is held). */
    public static boolean onMelee = true;
    /** Beam: a hand torch's throw. */
    static final float RANGE = 30f, ANGLE_DEG = 22f, ENERGY = 4f;
    /** The beam is noticed this far away (m) at night, once a second. */
    static final float SEEN_RADIUS = 35f;
    static final double SEEN_EVERY = 1.0;

    /** Which mount the light is on now: {@code off}, {@code gun}, {@code body}, {@code camera} (probe readout). */
    private String mount = "off";
    private Character body;
    private SpotLight3D light;
    private Skeleton3D skeleton;
    private int chestBone = -2;
    private double seenIn;

    /** Does {@code c}'s player own a flashlight (its profile's unlock)? An AI never does. */
    public static boolean owned(Character c) {
        PlayerProfile p = Profiles.of(c);
        return p != null && p.unlocks.contains(UNLOCK);
    }

    /** The body's Flashlight node, made on first use. */
    public static Flashlight ensure(Character c) {
        if (c.getNodeOrNull(NODE) instanceof Flashlight f) return f;
        Flashlight f = new Flashlight();
        f.setName(NODE);
        c.addChild(f);
        return f;
    }

    @Register
    @Override
    public void _ready() {
        body = getParent() instanceof Character c ? c : null;
        setAsTopLevel(true);
        light = new SpotLight3D();
        light.setName("Beam");
        light.setParam(godot.api.Light3D.Param.RANGE, RANGE);
        light.setParam(godot.api.Light3D.Param.SPOT_ANGLE, ANGLE_DEG);
        light.setParam(godot.api.Light3D.Param.SPOT_ATTENUATION, 0.8f);
        light.setParam(godot.api.Light3D.Param.ATTENUATION, 1.2f);
        light.setParam(godot.api.Light3D.Param.ENERGY, ENERGY);
        light.setColor(new Color(1.0, 0.96, 0.86, 1.0));
        light.setVisible(false);
        addChild(light);
    }

    @Register
    @Override
    public void _process(double delta) {
        if (body == null || light == null) return;
        boolean on = body.flashlightOn && body.isAlive() && body.currentVehicleNode == null;
        Transform3D at = on ? mountTransform() : null;
        if (at == null) {
            mount = "off";
            light.setVisible(false);
            return;
        }
        setGlobalTransform(at);
        watchSkeleton();
        light.setShadow(body.isLocallyOwnedPlayer());
        light.setVisible(true);
        seenIn -= delta;
        if (seenIn <= 0.0) {
            seenIn = SEEN_EVERY;
            postSeen();
        }
    }

    /** _process runs before this frame's pose: placed only there, the beam trailed the gun by a frame -- 0.48 m on the
     *  frame a reload threw the magazine hand (probe_flashlight). The skeleton's skeleton_updated comes after the
     *  pose (and after the weapon sockets, connected first), so the beam is placed again there. */
    private boolean watching;

    private void watchSkeleton() {
        if (watching) return;
        watching = true;
        if (chestBone == -2) chestPosition();
        if (skeleton != null) skeleton.connect("skeleton_updated", godot.core.MethodCallable.createUnsafe(this, "on_skeleton_updated"));
    }

    @Register
    public void onSkeletonUpdated() {
        if (body == null || light == null || !light.isVisible() || !body.flashlightOn) return;
        Transform3D at = mountTransform();
        if (at != null) setGlobalTransform(at);
    }

    /** Where the beam starts and which way it points (-Z), or null when this body shows none. */
    private Transform3D mountTransform() {
        WeaponController wc = body.weaponController;
        WeaponItem w = wc != null && !wc.isHolstered() ? wc.getCurrentWeaponItem() : null;
        if (w instanceof FirearmItem f && GD.isInstanceValid(f) && f.isInsideTree()) {
            if (f.getNodeOrNull("LightPoint") instanceof Node3D lp) {
                mount = "gun";
                return lp.getGlobalTransform();
            }
            Marker3D m = f.muzzleMarker();
            if (m != null) {
                Transform3D t = m.getGlobalTransform();
                Basis b = t.getBasis().orthonormalized();
                Vector3 o = t.getOrigin().plus(b.getColumn(2).times(-AHEAD)).plus(b.getColumn(1).times(-UNDER));
                mount = "gun";
                return new Transform3D(b, o);
            }
        }
        if (w != null && !(w instanceof FirearmItem) && !onMelee) return null;
        if (body.isLocallyOwnedPlayer() && body.isFirstPersonView() && body.activeCamera != null
                && GD.isInstanceValid(body.activeCamera) && body.activeCamera.isInsideTree()) {
            Transform3D t = body.activeCamera.getGlobalTransform();
            Basis b = t.getBasis().orthonormalized();
            mount = "camera";
            return new Transform3D(b, t.getOrigin().plus(b.getColumn(1).times(-0.12)).plus(b.getColumn(2).times(-0.15)));
        }
        Vector3 fwd = body.getGlobalBasis().getColumn(2).times(-1.0);
        Vector3 chest = chestPosition();
        Vector3 from = chest.plus(new Vector3(fwd.getX(), 0.0, fwd.getZ()).normalized().times(CHEST_AHEAD));
        Vector3 aim = body.getAimTargetPosition();
        Vector3 dir = aim != null && aim.distanceTo(from) > 1.0 ? aim.minus(from).normalized() : fwd.normalized();
        mount = "body";
        return new Transform3D(lookBasis(dir), from);
    }

    /** The chest bone's place (spine_03, the skeleton contract's chest), else 1.35 m up the body. */
    private Vector3 chestPosition() {
        if (chestBone == -2) {
            skeleton = findSkeleton(body);
            chestBone = skeleton != null ? (int) skeleton.findBone("spine_03") : -1;
        }
        if (skeleton != null && chestBone >= 0 && GD.isInstanceValid(skeleton))
            return skeleton.getGlobalTransform().times(skeleton.getBoneGlobalPose(chestBone).getOrigin());
        return body.getGlobalPosition().plus(new Vector3(0, 1.35, 0));
    }

    private static Skeleton3D findSkeleton(Node n) {
        for (Node k : n.getChildren()) {
            if (k instanceof Skeleton3D s) return s;
            if (k instanceof Flashlight || k instanceof com.openworld.weapon.WeaponItem) continue;
            Skeleton3D s = findSkeleton(k);
            if (s != null) return s;
        }
        return null;
    }

    /** A basis whose -Z is {@code dir} (up kept near +Y). */
    private static Basis lookBasis(Vector3 dir) {
        Vector3 z = dir.times(-1.0).normalized();
        Vector3 up = Math.abs(z.getY()) > 0.98 ? new Vector3(1, 0, 0) : new Vector3(0, 1, 0);
        Vector3 x = up.cross(z).normalized();
        Vector3 y = z.cross(x).normalized();
        return new Basis(x, y, z);
    }

    /** At night the authority tells the AI where a beam is (StimulusManager is per peer; the host runs the AI). */
    private void postSeen() {
        if (!com.openworld.world.DayNight.lightsWanted()) return;
        if (getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager nm && nm.isNetworked()
                && !nm.isServer()) return;
        com.openworld.world.StimulusManager sm = com.openworld.world.StimulusManager.get();
        if (sm == null) return;
        sm.post(com.openworld.world.StimulusManager.Type.LIGHT_SEEN, body.getGlobalPosition(), SEEN_RADIUS, body,
                body.characterInfo != null ? body.characterInfo.faction : "");
        seen++;
    }

    private int seen;

    @Register public String mountNow() { return mount; }
    @Register public int seenPostsNow() { return seen; }
    @Register public Vector3 beamOriginNow() { return getGlobalPosition(); }
    @Register public Vector3 beamDirectionNow() { return getGlobalBasis().getColumn(2).times(-1.0); }
    @Register public boolean beamVisibleNow() { return light != null && light.isVisible(); }
    @Register public boolean beamShadowNow() { return light != null && light.hasShadow(); }
    @Register public void setOnMeleeNow(boolean on) { onMelee = on; }
}
