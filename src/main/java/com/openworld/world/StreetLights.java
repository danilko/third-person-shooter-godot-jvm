package com.openworld.world;

import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.Camera3D;
import godot.api.Light3D;
import godot.api.Node3D;
import godot.api.OmniLight3D;
import godot.core.Color;
import godot.core.StringName;
import godot.core.Transform3D;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.List;

/**
 * The street lamps actually light the street — registered as the AutoLoad "StreetLights".
 *
 * <p>The island stands <b>1 962 poles</b>. Giving each one an {@code OmniLight3D} is not a rendering
 * question to tune, it is an impossible one: they are MultiMesh instances precisely so a district costs one
 * draw call, and a light per instance would undo that and light half the island at once. So this is GTA's
 * answer — <b>a small POOL of lights that follows the camera</b>: every tick the nearest standing lamp heads
 * within {@link #radius} are found and the pool's lights are moved onto them, brightest-nearest first.
 * A lamp beyond the pool still reads, because its glass is emissive ({@code MI_LampGlass}), which costs
 * nothing; what the pool adds is the pool of light on the road under it.
 *
 * <p><b>Where the bulb is comes from the PIECE, and is measured, not guessed</b> ({@link #HEAD_OFFSETS}):
 * `StreetLight_JP`'s luminaire mesh spans y 10.00–10.15, z −2.69…−2.08 in the piece's own frame, so its bulb
 * is (0, 10.07, −2.39); the twin's two heads are (±2.39, 10.07, 0). They are a table here rather than in
 * `furniture.json` for one reason worth stating: the piece data reaches the game through a BAKE, so putting
 * them there would rebuild all 52 road pieces to move a light 10 cm. When a second lamp family lands, this
 * moves to the asset table with the rest of its facts.
 *
 * <p><b>A knocked-down lamp is dark.</b> {@link BreakableProps} already knows which poles are lying on the
 * ground (3.11), so the pool simply skips them — the light goes out with the pole and comes back with it, with
 * no second record of what is broken.
 *
 * <p>Nothing here is networked and nothing is saved: it is a local view of state every peer already has, the
 * rule 3.11b set for the poles themselves.
 */
@Script(className = "StreetLights")
public class StreetLights extends Node3D {

    private static StreetLights instance;

    public static StreetLights get() { return instance; }

    /** Bulb positions in each lamp piece's own frame, measured off the piece's luminaire mesh. */
    private static final String[] LAMP_ASSETS = {"StreetLight_JP", "StreetLight_JP_Twin"};
    private static final Vector3[][] HEAD_OFFSETS = {
            {new Vector3(0.0, 10.07, -2.39)},
            {new Vector3(-2.39, 10.07, 0.0), new Vector3(2.39, 10.07, 0.0)},
    };

    /** Lights in the pool. 24 covers roughly two blocks of both kerbs at {@link #radius}. */
    @Export public int maxLights = 24;
    /** Only lamps this near the camera get one of the pool's lights (m). */
    @Export public float radius = 75.0f;
    /** How far each lamp throws (m). */
    @Export public float lightRange = 20.0f;
    /** Energy at full night; scaled by {@code DayNight.nightFactor} so dusk fades them up. */
    @Export public float lightEnergy = 3.0f;
    /** Sodium-ish warm white, the colour the luminaire's own emission already uses. */
    @Export public Color lightColor = new Color(1.0, 0.93, 0.76, 1.0);
    /** Seconds between re-assignments; a lamp does not move, so this is only about the camera moving. */
    @Export public float evalInterval = 0.25f;
    /** The control knob: off is the world before this existed. */
    @Visible public boolean enabled = true;

    private final List<OmniLight3D> pool = new ArrayList<>();
    private final List<double[]> found = new ArrayList<>();   // {distance, x, y, z}
    private double timer;
    private int litNow;

    @Register
    @Override
    public void _ready() {
        instance = this;
    }

    @Register
    @Override
    public void _exitTree() {
        if (instance == this) instance = null;
        pool.clear();
    }

    @Register
    @Override
    public void _process(double delta) {
        timer -= delta;
        if (timer > 0.0) return;
        timer = Math.max(0.05f, evalInterval);
        float night = DayNight.nightFactor();
        if (!enabled || night <= 0.02f) {
            darken();
            return;
        }
        Camera3D cam = getViewport() != null ? getViewport().getCamera3d() : null;
        if (cam == null || !GD.isInstanceValid(cam)) {
            darken();
            return;
        }
        gather(cam.getGlobalPosition());
        found.sort((a, b) -> Double.compare(a[0], b[0]));
        int n = Math.min(found.size(), Math.max(0, maxLights));
        for (int i = 0; i < n; i++) {
            OmniLight3D l = light(i);
            double[] f = found.get(i);
            l.setGlobalTransform(new Transform3D(l.getGlobalTransform().getBasis(), new Vector3(f[1], f[2], f[3])));
            l.setParam(Light3D.Param.ENERGY, lightEnergy * night);
            l.setVisible(true);
        }
        for (int i = n; i < pool.size(); i++) pool.get(i).setVisible(false);
        litNow = n;
    }

    /** Every standing lamp head within {@link #radius} of {@code from}, as {distance, x, y, z}. */
    private void gather(Vector3 from) {
        found.clear();
        double r2 = radius * (double) radius;
        for (BreakableProps b : BreakableProps.live()) {
            int heads = assetIndex(b.asset());
            if (heads < 0 || !b.nearBounds(from.getX(), from.getZ(), radius + 4.0)) continue;
            Vector3 scale = b.poleScale();
            int count = b.poles();
            for (int i = 0; i < count; i++) {
                if (b.poleBroken(i)) continue;
                Vector3 base = b.poleBase(i);
                double dx = base.getX() - from.getX(), dz = base.getZ() - from.getZ();
                if (dx * dx + dz * dz > r2) continue;
                double c = Math.cos(b.poleYaw(i)), s = Math.sin(b.poleYaw(i));
                for (Vector3 h : HEAD_OFFSETS[heads]) {
                    double hx = h.getX() * scale.getX(), hy = h.getY() * scale.getY(), hz = h.getZ() * scale.getZ();
                    // yaw about +Y, the basis the MultiMesh instance carries
                    double wx = base.getX() + hx * c + hz * s;
                    double wz = base.getZ() - hx * s + hz * c;
                    double wy = base.getY() + hy;
                    double d = Math.hypot(wx - from.getX(), wz - from.getZ());
                    if (d <= radius) found.add(new double[]{d, wx, wy, wz});
                }
            }
        }
    }

    private static int assetIndex(String asset) {
        for (int i = 0; i < LAMP_ASSETS.length; i++) if (LAMP_ASSETS[i].equals(asset)) return i;
        return -1;
    }

    private OmniLight3D light(int i) {
        while (pool.size() <= i) {
            OmniLight3D l = new OmniLight3D();
            l.setName(new StringName("Lamp" + pool.size()));
            l.setParam(Light3D.Param.RANGE, lightRange);
            l.setColor(lightColor);
            l.setParam(Light3D.Param.ENERGY, 0.0f);
            l.setShadow(false);                     // a lamp shadow per pole is not affordable, and reads as noise
            l.setAsTopLevel(true);
            addChild(l);
            pool.add(l);
        }
        return pool.get(i);
    }

    private void darken() {
        for (OmniLight3D l : pool) l.setVisible(false);
        litNow = 0;
    }

    // ── Probe readouts ────────────────────────────────────────────────────────

    /** Lamps lit this tick. */
    @Register public int litLampsNow() { return litNow; }

    /** Lamp heads found in range this tick, before the pool's cap. */
    @Register public int lampsInRangeNow() { return found.size(); }

    /** Distance from the camera to the nearest lit lamp head (−1 when none). */
    @Register public double nearestLampNow() { return found.isEmpty() ? -1.0 : found.get(0)[0]; }

    /** The i-th lit lamp's world position, for a probe that wants to measure where the light went. */
    @Register public Vector3 litLampPositionNow(int i) {
        return i >= 0 && i < litNow ? pool.get(i).getGlobalPosition() : Vector3.Companion.getZERO();
    }
}
