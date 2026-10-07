package com.openworld.ui;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.character.Player;
import com.openworld.game.PlayerRegistry;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Camera3D;
import godot.api.CollisionShape3D;
import godot.api.Control;
import godot.api.Environment;
import godot.api.Input;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.Panel;
import godot.api.StyleBox;
import godot.api.SubViewport;
import godot.api.TextureRect;
import godot.api.Viewport;
import godot.core.Basis;
import godot.core.Transform3D;
import godot.core.Vector2;
import godot.core.Vector2i;
import godot.core.Vector3;
import godot.global.GD;

/**
 * THE REAR-VIEW MIRROR while driving (user, 2026-10-07): a strip at the top centre of the screen showing what is
 * behind the car, the racing-game convention (Forza, Gran Turismo, Need for Speed). In the CHASE view it looks back
 * from over the roof; in the cockpit / bonnet views it looks back from the driver's own eye. Drawn mirror-flipped,
 * like a real mirror. Only for the local player driving with the carrier's own camera on screen; {@code rear_view}
 * (C) toggles it.
 *
 * <p>A second camera renders the scene a second time, so its cost is held down the way those games do it:
 * <ul>
 *   <li>its own {@link SubViewport} at the strip's own screen size ({@link #renderScale} 1.0: at 0.6 it was visibly
 *   blurred -- an upscaled target that also samples blurrier mips -- and pixels are not what costs here, draws are);</li>
 *   <li>refreshed every {@link #updateEvery}-th frame (UpdateMode ONCE), so at 60 fps a mirror at 30;</li>
 *   <li>a short {@link #farPlane} -- far geometry is what costs draws -- and a coarser mesh LOD threshold;</li>
 *   <li>a cheap copy of the world's Environment (no SSAO / SSIL / SSR / glow / SDFGI / volumetric fog), no MSAA
 *   (FXAA only, nearly free), no positional shadow atlas;</li>
 *   <li>nothing exists while the mirror is not shown: the viewport is DISABLED and the camera off.</li>
 * </ul>
 * Built in code by {@link HUDManager}; self-managed (not in BASE_LAYOUT).
 */
@Script(className = "RearViewMirror")
public class RearViewMirror extends Control {

    static final String PANEL = "res://src/main/resources/com/openworld/ui/hud_panel.tres";

    /** On by default; the rear_view key flips it. */
    @Export public boolean enabled = true;
    /** The strip's width as a fraction of the screen width, and its aspect (width : height). */
    @Export public float widthFraction = 0.30f;
    @Export public float aspect = 3.4f;
    /** The mirror camera renders at this fraction of the strip's on-screen pixels. */
    @Export public float renderScale = 1.0f;
    /** Render one frame in this many (2 = 30 Hz at 60 fps). */
    @Export public int updateEvery = 2;
    /** How far the mirror sees (m), and its field of view (deg). */
    @Export public float farPlane = 150.0f;
    @Export public float fovDeg = 55.0f;
    /** Mesh LOD threshold for the mirror's viewport (the main view's default is 1.0; higher = coarser). */
    @Export public float lodThreshold = 2.0f;
    /** Chase view: the camera this far over the roof (m), pitched down this much (deg). */
    @Export public float roofLift = 0.45f;
    @Export public float pitchDownDeg = 4.0f;

    private SubViewport vp;
    private Camera3D cam;
    private TextureRect pic;
    private Panel back;
    private Vehicle car;
    private double roofY = 1.4, rearZ = 2.0;
    private int frame;
    private boolean shownNow;
    private long renders;

    @Register
    @Override
    public void _ready() {
        setMouseFilter(Control.MouseFilter.IGNORE);
        back = new Panel();
        back.setMouseFilter(Control.MouseFilter.IGNORE);
        if (GD.load(PANEL) instanceof StyleBox sb) back.addThemeStyleboxOverride(new godot.core.StringName("panel"), sb);
        addChild(back);
        vp = new SubViewport();
        vp.setUpdateMode(SubViewport.UpdateMode.DISABLED);
        vp.setMsaa3d(Viewport.MSAA.DISABLED);
        vp.setScreenSpaceAa(Viewport.ScreenSpaceAA.FXAA);
        vp.setPositionalShadowAtlasSize(0);
        vp.setMeshLodThreshold(lodThreshold);
        vp.setUseDebanding(false);
        vp.setUseOcclusionCulling(true);
        addChild(vp);
        cam = new Camera3D();
        cam.setFar(farPlane);
        cam.setFov(fovDeg);
        vp.addChild(cam);
        pic = new TextureRect();
        pic.setMouseFilter(Control.MouseFilter.IGNORE);
        pic.setExpandMode(TextureRect.ExpandMode.IGNORE_SIZE);
        pic.setStretchMode(TextureRect.StretchMode.SCALE);
        pic.setFlipH(true);
        pic.setTexture(vp.getTexture());
        addChild(pic);
        setVisible(false);
    }

    @Register
    @Override
    public void _process(double delta) {
        if (Input.INSTANCE.isActionJustPressed("rear_view", false)) enabled = !enabled;
        Vehicle v = drivenCar();
        boolean show = enabled && v != null;
        if (show != shownNow) {
            shownNow = show;
            setVisible(show);
            vp.setUpdateMode(SubViewport.UpdateMode.DISABLED);
            cam.setCurrent(show);
            if (show) { layoutStrip(); cheapEnvironment(); }
        }
        if (!show) return;
        if (v != car) { car = v; roofY = extentOf(v, true); rearZ = extentOf(v, false); }
        layoutStrip();
        cam.setGlobalTransform(pose(v));
        if (++frame % Math.max(1, updateEvery) == 0) {
            vp.setUpdateMode(SubViewport.UpdateMode.ONCE);
            renders++;
        }
    }

    /** The car the local player is driving with the car's own camera on screen, else null. */
    private Vehicle drivenCar() {
        for (Player p : PlayerRegistry.getPlayers()) {
            if (p == null || !GD.isInstanceValid(p) || !p.isLocallyOwnedPlayer()) continue;
            if (p.currentVehicleNode instanceof Vehicle v && GD.isInstanceValid(v) && v.isDrivenViewOf(p)) return v;
        }
        return null;
    }

    /** Where the mirror camera is: the driver's eye in a first-person view, over the roof in the chase view, looking
     *  back along the car (its +Z: a car faces -Z), pitched a little down. */
    private Transform3D pose(Vehicle v) {
        Transform3D t = v.getGlobalTransform();
        Basis b = t.getBasis();
        Vector3 up = b.getColumn(1).normalized();
        Vector3 back = b.getColumn(2).normalized();
        Vector3 at;
        Node eye = v.getNodeOrNull("Seats/Seat0/CockpitCameraMount");
        if (v.isFirstPersonViewNow() && eye instanceof Node3D e) {
            // the racing-game mirror: at the driver's eye HEIGHT but just past the back of the hull, so the cabin's
            // headrests and pillars do not fill it (measured: from the eye itself they covered most of the strip)
            double eyeUp = e.getGlobalPosition().minus(t.getOrigin()).dot(up);
            at = t.getOrigin().plus(up.times(eyeUp)).plus(back.times(rearZ + 0.15));
        } else at = t.getOrigin().plus(up.times(roofY + roofLift));
        Vector3 look = back.rotated(b.getColumn(0).normalized(), -Math.toRadians(pitchDownDeg));
        Transform3D out = new Transform3D(Basis.Companion.getIDENTITY(), at);
        return out.lookingAt(at.plus(look), up, false);
    }

    /** The car's collision shapes' top over its origin (roof), or their rearmost +Z (the back of the hull), in m. */
    private static double extentOf(Vehicle v, boolean roof) {
        double best = roof ? 1.2 : 1.5;
        for (Node c : v.getChildren()) {
            if (!(c instanceof CollisionShape3D cs) || cs.getShape() == null) continue;
            var ab = cs.getShape().getDebugMesh().getAabb();
            double e = roof ? cs.getPosition().getY() + ab.getPosition().getY() + ab.getSize().getY()
                            : cs.getPosition().getZ() + ab.getPosition().getZ() + ab.getSize().getZ();
            best = Math.max(best, e);
        }
        return best;
    }

    private void layoutStrip() {
        Vector2 screen = getViewportRect().getSize();
        float w = (float) Math.max(280.0, screen.getX() * widthFraction);
        float h = w / aspect;
        float x = (float) (screen.getX() - w) * 0.5f, y = 18f;
        setPosition(new Vector2(x, y));
        setSize(new Vector2(w, h));
        float pad = 4f;
        back.setPosition(new Vector2(0, 0));
        back.setSize(new Vector2(w, h));
        pic.setPosition(new Vector2(pad, pad));
        pic.setSize(new Vector2(w - 2 * pad, h - 2 * pad));
        Vector2i want = new Vector2i((int) Math.max(64, (w - 2 * pad) * renderScale), (int) Math.max(24, (h - 2 * pad) * renderScale));
        if (!want.equals(vp.getSize())) vp.setSize(want);
    }

    /** The world's environment with the expensive passes off (sky, ambient, fog and tonemap kept). */
    private void cheapEnvironment() {
        var w = getViewport() == null ? null : getViewport().getWorld3d();
        Environment src = w == null ? null : (w.getEnvironment() != null ? w.getEnvironment() : w.getFallbackEnvironment());
        if (src == null) return;
        if (!(src.duplicate(false) instanceof Environment e)) return;
        e.setSsaoEnabled(false);
        e.setSsilEnabled(false);
        e.setSsrEnabled(false);
        e.setGlowEnabled(false);
        e.setSdfgiEnabled(false);
        e.setVolumetricFogEnabled(false);
        cam.setEnvironment(e);
    }

    // ── probe surface ──
    @Register public boolean shownNow() { return shownNow; }
    @Register public long rendersNow() { return renders; }
    /** The mirror camera's look direction against the car's forward (-1 = straight back). */
    @Register public double lookDotForwardNow() {
        if (car == null || !GD.isInstanceValid(car)) return 0;
        Vector3 f = cam.getGlobalTransform().getBasis().getColumn(2).times(-1.0).normalized();
        Vector3 cf = car.getGlobalTransform().getBasis().getColumn(2).times(-1.0).normalized();
        return f.dot(cf);
    }
    @Register public void setEnabledNow(boolean on) { enabled = on; }
}
