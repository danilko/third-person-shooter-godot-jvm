package com.openworld.world;

import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.BaseMaterial3D;
import godot.api.BoxMesh;
import godot.api.Camera3D;
import godot.api.GeometryInstance3D;
import godot.api.Light3D;
import godot.api.Material;
import godot.api.MultiMesh;
import godot.api.MultiMeshInstance3D;
import godot.api.Node3D;
import godot.api.OmniLight3D;
import godot.api.ResourceLoader;
import godot.api.ShaderMaterial;
import godot.api.Texture2D;
import godot.core.Color;
import godot.core.PackedFloat32Array;
import godot.core.StringName;
import godot.core.Transform3D;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

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
 * <p><b>Three layers, cheapest first</b> (2026-10-02, user: "see how performance goes"):
 * <ol>
 *   <li><b>Glow</b>: the lamp glass is emissive, and at night the shared shop / window materials
 *       ({@link #GLOW}) get an emission scaled by the night. One change per MATERIAL relights every building that
 *       wears it, so the whole city's windows and konbini fascias read as lit at no per-building cost.</li>
 *   <li><b>Fake pools</b>: every standing lamp head, and every shop door in the places record, gets a soft disc of
 *       light on the ground: a box in a MultiMesh whose shader reads the depth buffer and ADDS light onto the
 *       surface behind it (`assets/vfx/night/light_pool.gdshader`). One draw per lamp batch, no light math, so
 *       the far streets read lit too. It lights a car or a person standing in it, crudely.</li>
 *   <li><b>Real lights</b>: only the {@link #maxLights} nearest lamp heads get an OmniLight3D, which is what
 *       lights a character or a car properly as it passes under a lamp.</li>
 * </ol>
 * Emission does NOT light other surfaces in this renderer (no SDFGI / VoxelGI / lightmaps), which is why the
 * pools exist at all.
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

    /** Real lights in the pool (the nearest heads); the fake pools light the rest. Measured 2026-10-02 on the island
     *  streets at night: 0, 10 and 24 real lights cost the same within noise (GPU p50 under 3 ms), so 24 it stays. */
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

    /** Fake ground pools under every lamp head and in front of every shop door (layer 2). */
    @Visible public boolean poolsEnabled = true;
    /** Night glow on the shared window / shop materials (layer 1). */
    @Visible public boolean glowEnabled = true;
    /** A lamp pool's radius on the ground (m); the luminaire is 10 m up. */
    @Export public float poolRadius = 9.0f;
    /** A shop door's pool radius (m). */
    @Export public float shopPoolRadius = 6.0f;
    /** Pool brightness at full night (added to the surface's colour, before tonemapping). */
    @Export public float poolStrength = 0.30f;
    @Export public float shopPoolStrength = 0.35f;

    static final String LAMP_POOL_MATERIAL = "res://assets/vfx/night/light_pool_lamp.tres";
    static final String SHOP_POOL_MATERIAL = "res://assets/vfx/night/light_pool_shop.tres";
    /** Height of a pool's box (m): it lights from 1.5 m below the base to 4.5 m above, so a kerb, a car roof
     *  and a pavement a step down all catch it. */
    private static final double POOL_HEIGHT = 6.0, POOL_LIFT = 1.5;

    /**
     * The shared materials that glow at night: {path, emission energy at full night}. A material with an
     * albedo texture glows with that texture (a lit interior picture, a fascia's printed band); one without
     * glows in its own colour tinted warm. Emission is switched ON once (a shader variant compiles once) and
     * only its energy follows the night, so dusk fades the windows up with no further compile.
     */
    private static final Object[][] GLOW = {
            {"res://assets/world_source/kits/quaternius_downtown_city/materials/MI_FakeInterior.tres", 0.35},
            {"res://assets/world_source/kits/quaternius_downtown_city/materials/MI_FakeInterior_1.tres", 0.9},
            {"res://assets/world_source/kits/quaternius_downtown_city/materials/MI_FakeInterior_2.tres", 0.9},
            {"res://assets/world_source/kits/quaternius_downtown_city/materials/MI_FakeInterior_3.tres", 0.9},
            {"res://assets/world_source/kits/quaternius_downtown_city/materials/MI_FakeInterior_4.tres", 0.9},
            {"res://assets/world_source/kits/library/materials/MI_FasciaKonbini.tres", 1.2},
            {"res://assets/world_source/kits/library/materials/MI_FasciaGas.tres", 1.2},
            {"res://assets/world_source/kits/quaternius_downtown_city/materials/MI_ShopBand.tres", 0.8},
    };
    /** Places that get no door pool: open ground, landmarks lit their own way, and reserved land. */
    private static final Set<String> NO_SHOP_POOL = Set.of("Park", "Temple", "Shrine", "RainbowBridge", "TokyoTower",
            "ShuriCastle", "ContainerTerminal", "WarehouseYard", "SecureMansion");

    private final List<OmniLight3D> pool = new ArrayList<>();
    private final List<double[]> found = new ArrayList<>();   // {distance, x, y, z}
    private double timer;
    private int litNow;

    /** One pool MultiMesh per streamed lamp batch, a child of that batch so it streams out with it. */
    private record LampPools(MultiMeshInstance3D node, boolean[] broken, int heads) {}
    private final Map<BreakableProps, LampPools> lampPools = new IdentityHashMap<>();
    private MultiMeshInstance3D shopPools;
    private int shopPoolsVersion = -1;
    private ShaderMaterial lampPoolMat, shopPoolMat;
    private BoxMesh lampBox, shopBox;
    private final List<BaseMaterial3D> glowMats = new ArrayList<>();
    private final List<Double> glowEnergy = new ArrayList<>();
    private boolean glowPrepared;
    private float glowApplied = -1.0f, poolsApplied = -1.0f;
    private int poolCount;

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
        refreshGlow(glowEnabled ? night : 0.0f);
        refreshPools(poolsEnabled ? night : 0.0f);
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
            int count = b.poles();
            for (int i = 0; i < count; i++) {
                if (b.poleBroken(i)) continue;
                Vector3 base = b.poleBase(i);
                double dx = base.getX() - from.getX(), dz = base.getZ() - from.getZ();
                if (dx * dx + dz * dz > r2) continue;
                for (int h = 0; h < HEAD_OFFSETS[heads].length; h++) {
                    // yaw about +Y, the basis the MultiMesh instance carries
                    double[] w = head(b, i, h, heads);
                    double d = Math.hypot(w[0] - from.getX(), w[2] - from.getZ());
                    if (d <= radius) found.add(new double[]{d, w[0], w[1], w[2]});
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

    // ── Layer 1: the shared materials' night glow ─────────────────────────────

    private void refreshGlow(float night) {
        float level = Math.round(night * 20.0f) / 20.0f;    // steps of 5 %: a uniform write, not a per-frame one
        if (level == glowApplied) return;
        if (!glowPrepared) prepareGlow();
        glowApplied = level;
        for (int i = 0; i < glowMats.size(); i++)
            glowMats.get(i).setEmissionEnergyMultiplier((float) (glowEnergy.get(i) * level));
    }

    private void prepareGlow() {
        glowPrepared = true;
        for (Object[] row : GLOW) {
            String path = (String) row[0];
            if (!ResourceLoader.exists(path)) continue;
            if (!(ResourceLoader.load(path) instanceof BaseMaterial3D m)) continue;
            Texture2D tex = m.getTexture(BaseMaterial3D.TextureParam.ALBEDO);
            m.setFeature(BaseMaterial3D.Feature.EMISSION, true);
            if (tex != null) {
                m.setTexture(BaseMaterial3D.TextureParam.EMISSION, tex);
                m.setEmission(new Color(1.0, 0.92, 0.78, 1.0));
            } else {
                Color a = m.getAlbedo();
                m.setEmission(new Color(a.getR(), a.getG() * 0.92, a.getB() * 0.78, 1.0));
            }
            m.setEmissionEnergyMultiplier(0.0f);
            glowMats.add(m);
            glowEnergy.add((Double) row[1]);
        }
    }

    // ── Layer 2: the fake pools ───────────────────────────────────────────────

    private void refreshPools(float night) {
        boolean on = night > 0.02f;
        if (on) {
            if (lampPoolMat == null) preparePools();
            syncLampPools();
            syncShopPools();
        }
        float level = on ? Math.round(night * 20.0f) / 20.0f : 0.0f;
        if (level != poolsApplied && lampPoolMat != null) {
            poolsApplied = level;
            lampPoolMat.setShaderParameter(new StringName("intensity"), poolStrength * level);
            shopPoolMat.setShaderParameter(new StringName("intensity"), shopPoolStrength * level);
        }
        for (LampPools lp : lampPools.values())
            if (GD.isInstanceValid(lp.node())) lp.node().setVisible(on);
        if (shopPools != null && GD.isInstanceValid(shopPools)) shopPools.setVisible(on);
    }

    private void preparePools() {
        lampPoolMat = (ShaderMaterial) ((Material) ResourceLoader.load(LAMP_POOL_MATERIAL)).duplicate();
        shopPoolMat = (ShaderMaterial) ((Material) ResourceLoader.load(SHOP_POOL_MATERIAL)).duplicate();
        lampBox = new BoxMesh();
        lampBox.setMaterial(lampPoolMat);
        shopBox = new BoxMesh();
        shopBox.setMaterial(shopPoolMat);
    }

    /** A pool for every lamp batch that has streamed in; its broken poles' pools collapse to nothing. */
    private void syncLampPools() {
        lampPools.entrySet().removeIf(e -> !GD.isInstanceValid(e.getKey()) || !GD.isInstanceValid(e.getValue().node()));
        poolCount = 0;
        for (BreakableProps b : BreakableProps.live()) {
            int heads = assetIndex(b.asset());
            if (heads < 0 || b.poles() == 0) continue;
            LampPools lp = lampPools.get(b);
            if (lp == null) {
                lp = buildLampPools(b, heads);
                lampPools.put(b, lp);
            } else {
                int per = HEAD_OFFSETS[heads].length;
                for (int i = 0; i < lp.broken().length; i++) {
                    boolean br = b.poleBroken(i);
                    if (br == lp.broken()[i]) continue;
                    lp.broken()[i] = br;
                    for (int h = 0; h < per; h++)
                        lp.node().getMultimesh().setInstanceTransform(i * per + h, poolTransform(b, i, h, heads, br));
                }
            }
            poolCount += lp.node().getMultimesh().getInstanceCount();
        }
    }

    private LampPools buildLampPools(BreakableProps b, int heads) {
        int per = HEAD_OFFSETS[heads].length, n = b.poles();
        MultiMesh mm = new MultiMesh();
        mm.setTransformFormat(MultiMesh.TransformFormat.TRANSFORM_3D);
        mm.setMesh(lampBox);
        mm.setInstanceCount(n * per);
        boolean[] broken = new boolean[n];
        float[] buf = new float[n * per * 12];
        for (int i = 0; i < n; i++) {
            broken[i] = b.poleBroken(i);
            for (int h = 0; h < per; h++) {
                double[] w = head(b, i, h, heads);
                put(buf, i * per + h, broken[i] ? 0.0 : poolRadius * 2.0, POOL_HEIGHT,
                        w[0], b.poleBase(i).getY() + POOL_HEIGHT * 0.5 - POOL_LIFT, w[2]);
            }
        }
        mm.setBuffer(new PackedFloat32Array(buf));
        MultiMeshInstance3D node = pooledNode("LightPools", mm);
        b.addChild(node);
        return new LampPools(node, broken, heads);
    }

    private Transform3D poolTransform(BreakableProps b, int i, int h, int heads, boolean broken) {
        double[] w = head(b, i, h, heads);
        double d = broken ? 0.0 : poolRadius * 2.0;
        return new Transform3D(new godot.core.Basis(new Vector3(d, 0, 0), new Vector3(0, broken ? 0.0 : POOL_HEIGHT, 0),
                new Vector3(0, 0, d)), new Vector3(w[0], b.poleBase(i).getY() + POOL_HEIGHT * 0.5 - POOL_LIFT, w[2]));
    }

    /** One pool per enterable shop / civic door in the places record; rebuilt when the record is. */
    private void syncShopPools() {
        Places.bind(this);
        int v = Places.version();
        if (v == shopPoolsVersion && shopPools != null && GD.isInstanceValid(shopPools)) return;
        shopPoolsVersion = v;
        if (shopPools != null && GD.isInstanceValid(shopPools)) shopPools.queueFree();
        shopPools = null;
        List<Vector3> doors = new ArrayList<>();
        for (Places.Place p : Places.all()) {
            if (p.kind().startsWith("Reserve_") || NO_SHOP_POOL.contains(p.kind())) continue;
            doors.add(p.go());
        }
        if (doors.isEmpty()) return;
        MultiMesh mm = new MultiMesh();
        mm.setTransformFormat(MultiMesh.TransformFormat.TRANSFORM_3D);
        mm.setMesh(shopBox);
        mm.setInstanceCount(doors.size());
        float[] buf = new float[doors.size() * 12];
        for (int i = 0; i < doors.size(); i++) {
            Vector3 g = doors.get(i);
            put(buf, i, shopPoolRadius * 2.0, POOL_HEIGHT, g.getX(), g.getY() + POOL_HEIGHT * 0.5 - POOL_LIFT, g.getZ());
        }
        mm.setBuffer(new PackedFloat32Array(buf));
        shopPools = pooledNode("ShopLightPools", mm);
        addChild(shopPools);
    }

    private static MultiMeshInstance3D pooledNode(String name, MultiMesh mm) {
        MultiMeshInstance3D node = new MultiMeshInstance3D();
        node.setName(new StringName(name));
        node.setMultimesh(mm);
        node.setAsTopLevel(true);                     // instance transforms are world positions
        node.setCastShadowsSetting(GeometryInstance3D.ShadowCastingSetting.OFF);
        node.setVisible(false);
        return node;
    }

    /** Row-major 3x4 instance transform: a scaled, unrotated box (a pool is round, so it needs no yaw). */
    private static void put(float[] buf, int i, double diameter, double height, double x, double y, double z) {
        int o = i * 12;
        buf[o] = (float) diameter;  buf[o + 1] = 0; buf[o + 2] = 0;                 buf[o + 3] = (float) x;
        buf[o + 4] = 0;             buf[o + 5] = (float) (diameter > 0 ? height : 0); buf[o + 6] = 0; buf[o + 7] = (float) y;
        buf[o + 8] = 0;             buf[o + 9] = 0; buf[o + 10] = (float) diameter;    buf[o + 11] = (float) z;
    }

    /** Lamp head h of pole i, world {x, y, z}. */
    private static double[] head(BreakableProps b, int i, int h, int heads) {
        Vector3 scale = b.poleScale(), base = b.poleBase(i), off = HEAD_OFFSETS[heads][h];
        double c = Math.cos(b.poleYaw(i)), s = Math.sin(b.poleYaw(i));
        double hx = off.getX() * scale.getX(), hy = off.getY() * scale.getY(), hz = off.getZ() * scale.getZ();
        return new double[]{base.getX() + hx * c + hz * s, base.getY() + hy, base.getZ() - hx * s + hz * c};
    }

    private void darken() {
        for (OmniLight3D l : pool) l.setVisible(false);
        litNow = 0;
    }

    // ── Probe readouts ────────────────────────────────────────────────────────

    /** Fake lamp pools built (one per standing-or-broken lamp head in every streamed batch). */
    @Register public int lampPoolsNow() { return poolCount; }

    /** Shop door pools built from the places record. */
    @Register public int shopPoolsNow() { return shopPools != null && GD.isInstanceValid(shopPools) ? shopPools.getMultimesh().getInstanceCount() : 0; }

    /** Are the fake pools drawn this tick? */
    @Register public boolean poolsShownNow() { return poolsApplied > 0.0f; }

    /** Emission energy currently on the i-th glow material (probe readout). */
    @Register public float glowEnergyNow(int i) { return i >= 0 && i < glowMats.size() ? glowMats.get(i).getEmissionEnergyMultiplier() : -1.0f; }

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
