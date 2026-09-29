package com.openworld.carrier.vehicle;

import godot.api.*;
import godot.core.*;
import godot.global.GD;

import java.util.HashMap;
import java.util.Map;
import java.util.Random;

/**
 * What a car window looks and sounds like when it cracks and shatters (VehicleDamageModel's panes). Everything here
 * is built in code, once, and shared by every car in the game: one cracked copy per glass material, one invisible
 * material for a broken window, one shard mesh, one crack texture, one shatter sound. So a broken window costs no
 * extra draw call, no extra texture and no asset.
 */
public final class Glass {
    private Glass() {}

    private static final Map<Material, Material> CRACKED = new HashMap<>();
    private static Material hidden;
    private static ImageTexture crackTexture;
    private static Mesh shardMesh;
    private static AudioStreamWAV shatterSound;

    /** The world never holds more shard bursts than this at once; the oldest goes first. */
    private static final int MAX_BURSTS = 8;
    private static final java.util.ArrayDeque<Node3D> BURSTS = new java.util.ArrayDeque<>();

    /** The source glass with a spider-web of cracks over it: frostier, and the cracks white. */
    static Material cracked(Material source) {
        return CRACKED.computeIfAbsent(source, s -> {
            StandardMaterial3D m = s instanceof StandardMaterial3D sm ? (StandardMaterial3D) sm.duplicate() : new StandardMaterial3D();
            Color a = m.getAlbedo();
            m.setAlbedo(new Color(a.getR() + (0.85 - a.getR()) * 0.45, a.getG() + (0.87 - a.getG()) * 0.45,
                    a.getB() + (0.9 - a.getB()) * 0.45, Math.max(a.getA(), 0.6)));
            m.setTransparency(BaseMaterial3D.Transparency.ALPHA);
            m.setRoughness(0.45f);
            m.setTexture(BaseMaterial3D.TextureParam.ALBEDO, crackTexture());
            // the glass has no reliable UVs (a placeholder car's is a box): lay the cracks on in world space
            m.setFlag(BaseMaterial3D.Flags.UV1_USE_TRIPLANAR, true);
            m.setFlag(BaseMaterial3D.Flags.UV1_USE_WORLD_TRIPLANAR, true);
            m.setUv1Scale(new Vector3(1.4, 1.4, 1.4));
            return m;
        });
    }

    /** A broken window: nothing is drawn where it was. */
    static Material hidden() {
        if (hidden == null) {
            Shader sh = new Shader();
            sh.setCode("shader_type spatial;\nrender_mode unshaded, depth_draw_never, cull_disabled;\n"
                    + "void fragment() { discard; }\n");
            ShaderMaterial m = new ShaderMaterial();
            m.setShader(sh);
            hidden = m;
        }
        return hidden;
    }

    /** A spider-web crack pattern: white lines on a faint white frost, alpha in the texture. Tiles (it wraps). */
    private static ImageTexture crackTexture() {
        if (crackTexture != null) return crackTexture;
        final int n = 256;
        byte[] px = new byte[n * n * 4];
        float[] a = new float[n * n];
        java.util.Arrays.fill(a, 0.55f);
        Random r = new Random(7);
        for (int web = 0; web < 3; web++) {
            double cx = r.nextDouble() * n, cy = r.nextDouble() * n;
            int spokes = 9 + r.nextInt(5);
            double[] ang = new double[spokes];
            for (int i = 0; i < spokes; i++) ang[i] = (i + r.nextDouble() * 0.6) * 2 * Math.PI / spokes;
            for (int i = 0; i < spokes; i++) {                      // radial cracks, jagged
                double x = cx, y = cy, h = ang[i], len = 60 + r.nextDouble() * 90;
                for (double s = 0; s < len; s += 1.0) {
                    h += (r.nextDouble() - 0.5) * 0.12;
                    x += Math.cos(h); y += Math.sin(h);
                    plot(a, n, x, y);
                }
            }
            for (int ring = 1; ring <= 3; ring++) {                 // concentric cracks between the spokes
                double rad = ring * (14 + r.nextDouble() * 10);
                for (int i = 0; i < spokes; i++) {
                    double h0 = ang[i], h1 = ang[(i + 1) % spokes] + (i + 1 == spokes ? 2 * Math.PI : 0);
                    double r0 = rad * (0.85 + r.nextDouble() * 0.3), r1 = rad * (0.85 + r.nextDouble() * 0.3);
                    for (double t = 0; t <= 1; t += 1.0 / 40) {
                        double h = h0 + (h1 - h0) * t, rr = r0 + (r1 - r0) * t;
                        plot(a, n, cx + Math.cos(h) * rr, cy + Math.sin(h) * rr);
                    }
                }
            }
        }
        for (int i = 0; i < n * n; i++) {
            px[i * 4] = (byte) 255; px[i * 4 + 1] = (byte) 255; px[i * 4 + 2] = (byte) 255;
            px[i * 4 + 3] = (byte) Math.round(Math.min(1f, a[i]) * 255);
        }
        Image img = Image.createFromData(n, n, false, Image.Format.RGBA8, new PackedByteArray(px));
        img.generateMipmaps(false);
        crackTexture = ImageTexture.createFromImage(img);
        return crackTexture;
    }

    private static void plot(float[] a, int n, double x, double y) {
        int ix = Math.floorMod((int) Math.round(x), n), iy = Math.floorMod((int) Math.round(y), n);
        a[iy * n + ix] = 1f;
        a[iy * n + Math.floorMod(ix + 1, n)] = Math.max(a[iy * n + Math.floorMod(ix + 1, n)], 0.85f);
    }

    /**
     * A window shatters at {@code at}: a burst of glass cubes thrown along the bullet (and with the car's motion), and
     * the crash of it. Cosmetic and local to each peer; the burst frees itself.
     */
    static void shatter(Node scene, Vector3 at, Vector3 dir, Vector3 carVelocity) {
        CPUParticles3D p = new CPUParticles3D();
        p.setName(new StringName("GlassShards"));
        p.setMesh(shardMesh());
        p.setAmount(48);
        p.setLifetime(1.4);
        p.setOneShot(true);
        p.setExplosivenessRatio(1f);
        p.setLifetimeRandomness(0.4);
        p.setEmissionShape(CPUParticles3D.EmissionShape.SPHERE);
        p.setEmissionSphereRadius(0.25f);
        p.setDirection(dir.normalized());
        p.setSpread(55f);
        p.setParamMin(CPUParticles3D.Parameter.INITIAL_LINEAR_VELOCITY, 1.2f);
        p.setParamMax(CPUParticles3D.Parameter.INITIAL_LINEAR_VELOCITY, 3.5f);
        p.setParamMin(CPUParticles3D.Parameter.ANGULAR_VELOCITY, -720f);
        p.setParamMax(CPUParticles3D.Parameter.ANGULAR_VELOCITY, 720f);
        p.setParamMin(CPUParticles3D.Parameter.SCALE, 0.5f);
        p.setParamMax(CPUParticles3D.Parameter.SCALE, 1.4f);
        p.setCastShadowsSetting(GeometryInstance3D.ShadowCastingSetting.OFF);
        scene.addChild(p);
        p.setGlobalPosition(at);
        p.setEmitting(true);

        AudioStreamPlayer3D snd = new AudioStreamPlayer3D();
        snd.setName(new StringName("GlassSound"));
        snd.setStream(shatterSound());
        snd.setUnitSize(6f);
        snd.setPitchScale((float) GD.randfRange(0.9f, 1.12f));
        p.addChild(snd);
        snd.play();
        snd.connect(new StringName("tree_exiting"), MethodCallable.createUnsafe(snd, "stop"));   // CLAUDE.md audio rule

        SceneTreeTimer t = scene.getTree().createTimer(2.2, false, true, false);
        t.connect(new StringName("timeout"), MethodCallable.createUnsafe(p, "queue_free"));
        BURSTS.addLast(p);
        while (BURSTS.size() > MAX_BURSTS) {
            Node3D old = BURSTS.pollFirst();
            if (old != null && GD.isInstanceValid(old)) old.queueFree();
        }
        BURSTS.removeIf(b -> !GD.isInstanceValid(b));
    }

    private static Mesh shardMesh() {
        if (shardMesh == null) {
            BoxMesh b = new BoxMesh();
            b.setSize(new Vector3(0.035, 0.006, 0.025));
            StandardMaterial3D m = new StandardMaterial3D();
            m.setAlbedo(new Color(0.8, 0.88, 0.9, 0.7));
            m.setTransparency(BaseMaterial3D.Transparency.ALPHA);
            m.setRoughness(0.1f);
            b.setMaterial(m);
            shardMesh = b;
        }
        return shardMesh;
    }

    /**
     * The shatter, synthesised once (no asset): a sharp burst of high-passed noise that dies in a few hundredths of
     * a second, then a scatter of short high pings — the shards landing.
     */
    private static AudioStreamWAV shatterSound() {
        if (shatterSound != null) return shatterSound;
        final int rate = 22050, len = (int) (rate * 0.7);
        double[] s = new double[len];
        Random r = new Random(11);
        double prev = 0;
        for (int i = 0; i < len; i++) {
            double t = (double) i / rate;
            double noise = r.nextDouble() * 2 - 1;
            double hp = noise - prev;                                  // first difference: a crude high-pass
            prev = noise;
            s[i] = hp * 0.55 * Math.exp(-t / 0.045) + noise * 0.12 * Math.exp(-t / 0.18);
        }
        for (int k = 0; k < 26; k++) {                                 // tinkles
            int start = (int) (rate * (0.02 + Math.pow(r.nextDouble(), 1.6) * 0.55));
            double f = 2800 + r.nextDouble() * 4200, amp = 0.08 + r.nextDouble() * 0.12, tau = 0.012 + r.nextDouble() * 0.03;
            for (int i = start; i < len && i < start + rate / 8; i++) {
                double t = (double) (i - start) / rate;
                s[i] += amp * Math.sin(2 * Math.PI * f * t) * Math.exp(-t / tau);
            }
        }
        byte[] data = new byte[len * 2];
        for (int i = 0; i < len; i++) {
            int v = (int) Math.round(Math.max(-1, Math.min(1, s[i])) * 30000);
            data[i * 2] = (byte) (v & 0xff);
            data[i * 2 + 1] = (byte) ((v >> 8) & 0xff);
        }
        AudioStreamWAV w = new AudioStreamWAV();
        w.setFormat(AudioStreamWAV.Format.FORMAT_16_BITS);
        w.setMixRate(rate);
        w.setStereo(false);
        w.setData(new PackedByteArray(data));
        shatterSound = w;
        return w;
    }

    /** Engine-owned statics: dropped when the game closes (GameManager._exitTree), the IconRegistry rule. */
    public static void clearCaches() {
        CRACKED.clear();
        hidden = null;
        crackTexture = null;
        shardMesh = null;
        shatterSound = null;
        BURSTS.clear();
    }
}
